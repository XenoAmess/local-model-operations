#!/usr/bin/env python3
"""Wait for an authorized render boundary, verify delivery, then wake its owner.

This CPU-only watcher never starts a GPU test or changes a production backend.
The existing scheduler's validation_job gate reserves the boundary atomically.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

ROOT = Path(__file__).resolve().parents[1]
TERMINAL = {"completed", "failed", "cancelled"}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def boundary_ready(task, queue, plan):
    control = queue.get("maintenance", {})
    scheduler = queue.get("scheduler", {})
    return (task.get("status") == "completed"
            and control.get("enabled") is True
            and control.get("upgrade_id") == plan["id"]
            and not queue.get("running")
            and not scheduler.get("running_jobs")
            and scheduler.get("phase") == "upgrading"
            and queue.get("recovery", {}).get("paused") is False)


def arm(plan):
    """Reserve exactly the current render, without pausing it or closing intake."""
    sys.path.insert(0, str(ROOT / "tools"))
    from video_queue import QueueStore
    store = QueueStore()
    with store.connection(immediate=True) as db:
        control = store._state_value(db, "service_control", {})
        if control.get("enabled") or control.get("validation_job"):
            raise RuntimeError("Another maintenance reservation already owns the boundary")
        row = db.execute("SELECT status FROM jobs WHERE id=?", (plan["trigger_job_id"],)).fetchone()
        running = [r[0] for r in db.execute("SELECT id FROM jobs WHERE status='in_progress'")]
        if row is None or row[0] != "in_progress" or running != [plan["trigger_job_id"]]:
            raise RuntimeError("Current render changed; do not silently reserve a later job")
        control.update(enabled=False, validation_job=plan["trigger_job_id"],
                       drain_job_id=plan["trigger_job_id"], upgrade_id=plan["id"],
                       reason="Optimization tests reserved after current S42 delivery; render continues",
                       requested_at=time.time(), updated_at=time.time())
        db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", ("service_control", json.dumps(control)))
        store._bump_revision(db)
        store._event(db, "optimization_boundary_reserved", job=plan["trigger_job_id"], plan=plan["id"])
    return control


def verify_delivery(client, api, task, directory):
    receipt = task.get("result", {})
    if not receipt.get("sha256"):
        raise RuntimeError("Completed render has no checksum receipt")
    destination = directory / "current-render.mp4"
    temporary = destination.with_suffix(".partial")
    digest, count = hashlib.sha256(), 0
    url = api + "/videos/" + task["id"] + "/content"
    with client.get(url, stream=True, timeout=(10, 120), allow_redirects=False) as response:
        if response.status_code != 200:
            raise RuntimeError("Content endpoint did not return a direct HTTP 200")
        with temporary.open("wb") as stream:
            for block in response.iter_content(1024 * 1024):
                stream.write(block)
                digest.update(block)
                count += len(block)
        if count != int(response.headers["Content-Length"]) or digest.hexdigest() != receipt["sha256"]:
            raise RuntimeError("Downloaded content length or SHA-256 mismatch")
    temporary.replace(destination)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(destination)
    ], text=True, timeout=30))
    video = next(s for s in probe["streams"] if s["codec_type"] == "video")
    width, height = (int(n) for n in task["size"].split("x"))
    if (video["width"], video["height"]) != (width, height):
        raise RuntimeError("Downloaded geometry differs from the completed request")
    if receipt.get("frames") is not None and int(video["nb_frames"]) != receipt["frames"]:
        raise RuntimeError("Downloaded frame count differs from the render receipt")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(destination),
                    "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
    return {"status": "lan_download_sha_geometry_full_decode_verified", "bytes": count,
            "sha256": digest.hexdigest(), "download_url": url, "probe": probe,
            "full_decode": True, "client_visual_review": "pending", "peer_checksum_verified": False}


def notify(message):
    result = subprocess.run([os.environ["PASEO_CLI"], "send", os.environ["PASEO_AGENT_ID"],
                             "--behavior", "steer", "--no-wait", message],
                            capture_output=True, timeout=45)
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--arm", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    if args.arm:
        print(json.dumps(arm(plan), ensure_ascii=False))
        return
    sys.path.insert(0, str(ROOT / "llm-lab/scripts"))
    from resource_guard import require_isolation
    isolation = require_isolation()
    if not os.environ.get("PASEO_CLI") or not os.environ.get("PASEO_AGENT_ID"):
        raise RuntimeError("Same-conversation notification context is missing")
    directory = ROOT / plan["state_directory"]
    directory.mkdir(parents=True, exist_ok=True)
    state_path = directory / "state.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    if previous.get("notification_accepted"):
        return
    client = requests.Session()
    client.trust_env = False
    api = plan["api_base"]
    while True:
        current_plan = json.loads(args.plan.read_text())
        if current_plan.get("status") in {"cancelled", "completed"}:
            return
        try:
            response = client.get(api + "/videos/" + plan["trigger_job_id"], timeout=15, allow_redirects=False)
            response.raise_for_status()
            task = response.json()
            response = client.get(api + "/queue", timeout=15, allow_redirects=False)
            response.raise_for_status()
            queue = response.json()
            state = {"checked_at": time.time(), "job_id": plan["trigger_job_id"], "task_status": task["status"],
                     "stage": task.get("stage"), "progress": task.get("progress"), "isolation": isolation,
                     "status": "waiting_current_render", "gpu_tests_started": False}
            control = queue.get("maintenance", {})
            if control.get("upgrade_id") != plan["id"]:
                state.update(status="reservation_superseded_no_tests", notification_accepted=False)
                ready = True
            elif task["status"] in TERMINAL - {"completed"}:
                state.update(status="render_failed_or_cancelled_no_tests")
                ready = True
            else:
                ready = boundary_ready(task, queue, plan)
                if ready:
                    try:
                        verification = verify_delivery(client, api, task, directory)
                        write_json(directory / "delivery-verification.json", verification)
                        state.update(status="delivery_verified_tests_pending", verification=verification)
                    except Exception as error:
                        state.update(status="delivery_verification_failed_no_tests", error=type(error).__name__ + ": " + str(error))
            write_json(state_path, state)
            if ready:
                message = (f"[渲染后工程优化测试事件] 用户授权等当前 S42 成片完成后开展优化测试。"
                    f"绑定任务 {plan['trigger_job_id']}，当前 {task['status']}，边界状态 {state['status']}。"
                    f"读取 {args.plan} 和 {state_path}。仅当 delivery_verified_tests_pending 时，先向用户交付完整 HTTP 视频链接，"
                    "核对 /v1/queue 的本轮 maintenance、无在跑任务、GPU 无其他进程，并取得 outputs/h3-2k-gpu.lock，"
                    "在 80/88GiB 隔离下执行新的已授权测试：代表性真实层／调用的 GPU 时间分析；固定源码的 SM120 BF16 FROST "
                    "单独构建、正确性及末头末尾 K/V 检查；5秒和14秒形状预热后短测。数值差异与画质影响分开报告，"
                    "严格同结果须逐元素完全一致，不自动切正式后端。预取仅在分析证明 H2D 等待明显时小范围测试，"
                    "CUDA Graphs／输出路径不因列表存在就全面重构；不重复已完成 cuDNN／FlashInfer FA2 对照或旧框架基准。"
                    "本轮测试窗口最多60分钟，超时或无收益保留证据，退出本轮维护并恢复原后端后续队列，继续编写 docs／提交推送。"
                    "若渲染失败、取消、交付失败、预留被覆盖或有更新的用户取消／停机指令，不启动 GPU 测试，先报告与安全处理；"
                    "失败任务保持失败，不复活、不重跑用户片子。禁止云端／开机自启，测试完成或失败均恢复属于本轮的维护，"
                    "不解除 OOM 人工熔断或覆盖其他维护。此次事件只启动新优化实验，不是候选已通过或正式部署授权。")
                if notify(message):
                    state.update(notification_accepted=True, notification_at=time.time())
                    write_json(state_path, state)
                    return
        except (OSError, ValueError, requests.RequestException, subprocess.SubprocessError) as error:
            write_json(state_path, {"checked_at": time.time(), "status": "retrying_observation_or_notification",
                                    "job_id": plan["trigger_job_id"], "error": type(error).__name__ + ": " + str(error),
                                    "gpu_tests_started": False})
        time.sleep(30)


if __name__ == "__main__":
    main()
