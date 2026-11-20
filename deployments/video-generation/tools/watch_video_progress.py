#!/usr/bin/env python3
"""One read-only progress sample; systemd timer schedules it every ten minutes."""

import argparse
import csv
import datetime
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.request

GIB = 2**30
TERMINAL = {"completed", "failed", "cancelled"}
FATAL = re.compile(r"CUDA out of memory|OutOfMemoryError|CUDA error:|illegal memory access|"
                   r"device-side assert|CUBLAS_STATUS_ALLOC_FAILED|Traceback \(most recent call last\)")


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def command(argv, timeout=8):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError(done.stderr.strip()[:250] or f"command exited {done.returncode}")
    return done.stdout.strip()


def get_json(opener, url):
    for attempt in range(2):
        try:
            with opener.open(url, timeout=5) as response:
                return json.load(response)
        except Exception:
            if attempt:
                raise
            time.sleep(0.5)


def collect(config):
    now = time.time()
    sample = {"time": now, "checked_at": datetime.datetime.now().astimezone().isoformat(),
              "job_id": config["job"], "errors": {}}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for name, url in (("task", config["api"].rstrip("/") + "/videos/" + config["job"]),
                      ("service", config["status_url"])):
        try:
            sample[name] = get_json(opener, url)
        except Exception as error:
            sample["errors"][name] = f"{type(error).__name__}: {error}"
    try:
        raw = command(["systemctl", "--user", "show", config["worker_unit"],
                       "-p", "ActiveState", "-p", "MainPID", "-p", "ControlGroup", "-p", "FreezerState"])
        unit = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
        sample["worker"] = unit
        group = Path("/sys/fs/cgroup") / unit.get("ControlGroup", "").lstrip("/")
        if unit.get("ControlGroup") and group.exists():
            events = group / "memory.events"
            if events.exists():
                sample["memory_events"] = {k: int(v) for k, v in (x.split() for x in events.read_text().splitlines())}
            sample["worker_memory_bytes"] = int((group / "memory.current").read_text())
    except Exception as error:
        sample["errors"]["worker"] = f"{type(error).__name__}: {error}"
    try:
        raw = command(["nvidia-smi", "--query-gpu=index,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                       "--format=csv,noheader,nounits"])
        sample["gpus"] = [{"index": int(row[0]), "utilization_percent": float(row[1]),
                           "used_mib": float(row[2]), "total_mib": float(row[3]),
                           "temperature_c": float(row[4]), "power_watts": float(row[5])}
                          for row in csv.reader(raw.splitlines())]
    except Exception as error:
        sample["errors"]["gpu"] = f"{type(error).__name__}: {error}"
    sample["host_available_bytes"] = next(int(x.split()[1]) * 1024 for x in
        Path("/proc/meminfo").read_text().splitlines() if x.startswith("MemAvailable:"))
    directory = Path(config["job_directory"])
    sample["disk_free_bytes"] = shutil.disk_usage(directory).free
    log = directory / "worker.log"
    if log.exists():
        sample["worker_log_mtime"] = log.stat().st_mtime
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 128 * 1024))
            lines = stream.read().decode("utf-8", errors="replace").splitlines()
        sample["fatal_log_lines"] = [line[:350] for line in lines if FATAL.search(line)][-3:]
    return sample


def evaluate(sample, previous, config):
    """Track true stage changes, not poll timestamps; an unchanged ten-minute poll is normal."""
    now = sample["time"]
    task = sample.get("task", {})
    status = task.get("status")
    key = [status, task.get("stage"), task.get("denoising_step"),
           task.get("transformer_block"), task.get("progress")]
    prior = dict(previous)
    if task:
        server_time = float(task.get("updated_at") or now)
        if key != previous.get("progress_key"):
            prior["last_progress_at"] = min(now, server_time)
        prior["progress_key"] = key
    prior.setdefault("last_progress_at", now)
    stale = max(0, now - prior["last_progress_at"])
    alerts = {}
    if status == "failed":
        alerts["task_failed"] = "任务已失败：" + str(task.get("error") or "请读取 worker.log 核对")[:350]
    if status in TERMINAL:
        return alerts, prior
    for name, detail in sample.get("errors", {}).items():
        alerts["probe_" + name] = f"{name} 巡检失败：{detail}；需核实，不能据此断言渲染失败"
    worker = sample.get("worker", {})
    if status == "in_progress":
        if worker and worker.get("ActiveState") not in {"active", "activating"}:
            alerts["worker_inactive"] = "HTTP 仍显示执行中，但 worker 已不处于 active 状态"
        if worker.get("FreezerState") in {"frozen", "freezing"}:
            alerts["worker_frozen"] = "worker 处于冻结状态，用户要求在途视频持续运行"
        stage = str(task.get("stage", ""))
        denoising = any(x in stage for x in ("密集", "去噪", "denois"))
        stall_after = config.get("denoise_stall_seconds", 1800) if denoising else config.get("other_stall_seconds", 2700)
        if stale >= stall_after:
            alerts["progress_stalled"] = f"进度已约 {stale/60:.0f} 分钟未更新（当前 {stage}），可能停滞，需检查"
        idle = bool(sample.get("gpus")) and all(g["utilization_percent"] < 5 for g in sample["gpus"])
        idle_streak = previous.get("idle_streak", 0) + 1 if idle and denoising else 0
        prior["idle_streak"] = idle_streak
        if idle_streak >= 2 and stale >= 600:
            alerts["gpu_idle"] = "去噪阶段连续两次巡检显卡接近空闲，且进度未推进"
        if sample.get("fatal_log_lines"):
            alerts["worker_log_error"] = "worker 日志出现错误：" + " | ".join(sample["fatal_log_lines"])
        events = sample.get("memory_events", {})
        old_events = previous.get("memory_events", {})
        if any(events.get(k, 0) > old_events.get(k, 0) for k in ("oom", "oom_kill")):
            alerts["worker_oom"] = "worker 的 cgroup OOM／OOM kill 计数增加"
        service = sample.get("service", {})
        if service.get("queue_paused") or service.get("status") in {"degraded", "unavailable"}:
            alerts["service_degraded"] = "服务／队列异常状态：" + str(service.get("reason") or service.get("status"))
        if sample.get("host_available_bytes", 99 * GIB) < 28 * GIB:
            alerts["host_memory_low"] = "主机可用内存低于现有 28 GiB 保护余量"
        if sample.get("disk_free_bytes", 99 * GIB) < 10 * GIB:
            alerts["disk_low"] = "输出磁盘剩余空间不足 10 GiB"
        if any(g["temperature_c"] >= 85 for g in sample.get("gpus", [])):
            alerts["gpu_temperature"] = "GPU 温度达到巡检告警阈值 85℃"
    prior["memory_events"] = sample.get("memory_events", prior.get("memory_events", {}))
    return alerts, prior


def notify(message):
    cli, agent = os.environ.get("PASEO_CLI"), os.environ.get("PASEO_AGENT_ID")
    if not cli or not agent:
        return False
    try:
        return subprocess.run([cli, "send", agent, "--behavior", "steer", "--no-wait", message],
                              capture_output=True, timeout=30).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    directory = Path(config["state_directory"])
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "state.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    try:
        sample = collect(config)
    except Exception as error:
        sample = {"time": time.time(), "job_id": config["job"],
                  "errors": {"monitor": f"{type(error).__name__}: {error}"}}
    alerts, state = evaluate(sample, previous, config)
    previous_alerts = previous.get("active_alerts", {})
    unsent = dict(previous.get("pending_alerts", {}))
    unsent.update({k: v for k, v in alerts.items()
                  if not previous_alerts.get(k, {}).get("notification_accepted")})
    sent = not unsent
    if unsent:
        task = sample.get("task", {})
        text = (f"[视频每10分钟巡检异常] 海边蝴蝶 S48 {config['job']} 检测到的异常（含待重发事件）：" + "；".join(unsent.values()) +
                f"。任务状态 {task.get('status', 'unknown')}，阶段 {task.get('stage', 'unknown')}。"
                f"请立即向用户说明本次发现，读取 {directory / 'latest.json'} 与任务日志核实。"
                "未变化的10分钟采样不是故障；不要根据单一资源指标宣告失败。"
                "用户要求当前视频继续跑完，不得为基准暂停、冻结或重跑；两个BF16内核短测等完整视频交付后。"
                "本巡检只读，无权自动更改采样、模型、队列或重启worker。")
        sent = notify(text)
    state.update(job_id=config["job"], checked_at=sample["time"], pending_alerts={} if sent else unsent,
                 active_alerts={k: {"message": v, "notification_accepted":
                     bool(previous_alerts.get(k, {}).get("notification_accepted") or (k in unsent and sent))}
                     for k, v in alerts.items()}, last_sample=sample)
    write_json(directory / "latest.json", {"sample": sample, "alerts": alerts, "new_alerts": list(unsent),
                                           "notification_accepted": sent if unsent else None})
    write_json(state_path, state)
    with (directory / "samples.jsonl").open("a") as stream:
        stream.write(json.dumps({"sample": sample, "alerts": alerts}, ensure_ascii=False) + "\n")
    terminal = sample.get("task", {}).get("status") in TERMINAL
    if terminal and sent:
        command(["systemctl", "--user", "stop", config["timer_unit"]])
    print(json.dumps({"job": config["job"], "status": sample.get("task", {}).get("status"),
                      "stage": sample.get("task", {}).get("stage"), "alerts": list(alerts),
                      "new_notifications": list(unsent), "terminal": terminal}, ensure_ascii=False), flush=True)
    return 0 if sent else 75


if __name__ == "__main__":
    raise SystemExit(main())
