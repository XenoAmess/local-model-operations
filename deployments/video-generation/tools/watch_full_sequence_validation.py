#!/usr/bin/env python3
"""Validate the authorized S48 job over LAN, then wake this same conversation for visual review/publication."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    directory = ROOT / "outputs/video-queue/full-sequence-validation-20261120"
    directory.mkdir(parents=True, exist_ok=True)
    result_path = directory / "verification.json"
    client = requests.Session()
    client.trust_env = False
    api = "http://192.168.1.11:8002/v1"
    while True:
        try:
            r = client.get(api + "/videos/" + args.job, timeout=15)
            r.raise_for_status()
            task = r.json()
            if task["status"] in {"completed", "failed", "cancelled"}:
                break
        except (requests.RequestException, ValueError):
            pass
        time.sleep(20)
    report = {"job_id": args.job, "task_status": task["status"], "observed_at": time.time(),
              "visual_review": "pending", "client_review": "pending", "client_checksum_verified": False}
    try:
        if task["status"] != "completed":
            raise RuntimeError(str(task.get("error") or task["status"]))
        receipt = task["result"]
        if (receipt.get("temporal_strategy") != "full_sequence" or receipt.get("windows") != 1
                or receipt.get("hard_cuts") != 0 or receipt.get("global_attention") is not True
                or receipt.get("frames") != 336 or receipt.get("processing_frames") != 345
                or receipt.get("independent_window_fallback") is not False):
            raise RuntimeError("Completed task does not prove the requested complete timeline")
        video = directory / "S48-full-sequence-4k.mp4"
        temporary = video.with_suffix(".partial")
        sha = hashlib.sha256()
        count = 0
        with client.get(api + "/videos/" + args.job + "/content", stream=True, timeout=300,
                        headers={"User-Agent": "LocalFullSequenceValidation/1"}) as response:
            response.raise_for_status()
            with temporary.open("wb") as stream:
                for block in response.iter_content(1024 * 1024):
                    stream.write(block)
                    sha.update(block)
                    count += len(block)
            if int(response.headers["Content-Length"]) != count:
                raise RuntimeError("LAN download ended before Content-Length")
        if sha.hexdigest() != receipt["sha256"]:
            raise RuntimeError("LAN SHA-256 mismatch")
        temporary.replace(video)
        probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,width,height,nb_frames,r_frame_rate:format=duration", "-of", "json", str(video)], text=True))
        v = next(s for s in probe["streams"] if s["codec_type"] == "video")
        if (v["width"], v["height"], int(v["nb_frames"]), v["r_frame_rate"]) != (3840, 2160, 336, "24/1"):
            raise RuntimeError("Incorrect downloaded video geometry")
        if abs(float(probe["format"]["duration"]) - 14) > 0.06:
            raise RuntimeError("Incorrect complete video duration")
        db = sqlite3.connect(f"file:{ROOT / 'outputs/video-queue/queue.sqlite3'}?mode=ro", uri=True)
        request = json.loads(db.execute("SELECT payload FROM jobs WHERE id=?", (args.job,)).fetchone()[0])
        db.close()
        source_probe = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type", "-of", "json", request["input_video"]], text=True))
        source_audio = any(s["codec_type"] == "audio" for s in source_probe["streams"])
        output_audio = any(s["codec_type"] == "audio" for s in probe["streams"])
        if source_audio != output_audio:
            raise RuntimeError("Source soundtrack presence was not preserved")
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-threads", "2", "-i", str(video),
                        "-f", "null", "-"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        indices = [0, 48, 95, 96, 97, 167, 168, 169, 237, 238, 239, 288, 335]
        choose = "+".join(f"eq(n\\,{i})" for i in indices)
        sheet = directory / "S48-review-contact-sheet.jpg"
        subprocess.run(["ffmpeg", "-nostdin", "-y", "-v", "error", "-threads", "2", "-i", str(video),
            "-vf", f"select={choose},scale=480:-1,tile=4x4", "-frames:v", "1", "-q:v", "2", str(sheet)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        report.update(status="lan_sha_geometry_audio_full_decode_verified_visual_review_pending",
                      bytes=count, sha256=sha.hexdigest(), probe=probe, source_audio_present=source_audio,
                      full_decode=True, local_download=str(video), contact_sheet=str(sheet), sampled_frame_indices=indices,
                      receipt=receipt, download_url=api + "/videos/" + args.job + "/content")
    except Exception as error:
        report.update(status="verification_failed_evidence_retained", error=type(error).__name__ + ": " + str(error))
    write(result_path, report)
    message = (f"[整段 4K 自动验收事件] 用户授权的海边蝴蝶 S48 14 秒任务 {args.job} 已到达 {task['status']}。"
        f"局域网验证状态：{report['status']}。请继续本项原授权工作，读取 "
        "outputs/video-queue/full-sequence-validation-20261120/verification.json、任务日志与 result.json；"
        "成功时查看接缝附近及首中尾画面，向用户提供完整 HTTP 视频链接供对端审核，更新 docs／验收记录并提交推送。"
        "本次计划在 canary 结束后自动维护；请先读 /v1/queue 确认当前维护状态及没有其他在跑任务，"
        "deployment/video-queue/full-sequence-validation.json 中的 "
        "scheduler_restart_required_after_canary 为 true 时，须在安全边界重启调度器加载完整任务 OOM 日志修正，"
        "用户最新另要求：S48 成功完整交付之后再快速实测 cuDNN、FlashInfer 通用 BF16 密集内核与现用 Flash SDPA，"
        "待办见 deployment/video-queue/dense-kernel-quick-benchmark-plan.json。"
        "成功交付时先保留维护状态，在空闲 GPU 上完成这项已授权的短算子对照并汇报性能排名，"
        "不自动切换正式后端；完成后调用 POST /v1/service/maintenance enabled=false 恢复后续任务；"
        "若失败，保留失败状态和证据并修复，不能复活失败 ID 或静默退回窗口拼接。"
        "4K 分流严格按原单窗口上限124帧：<=124原路线，>124整段。80/88GiB、禁止云端、无开机自启继续有效。"
        "用户后续取消或停机指令优先；本事件不授权恢复任何旧基准。")
    while True:
        try:
            sent = subprocess.run([os.environ["PASEO_CLI"], "send", os.environ["PASEO_AGENT_ID"],
                                   "--behavior", "steer", "--no-wait", message], capture_output=True, text=True, timeout=45)
            success = sent.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            success = False
        write(directory / "notification.json", {"job": args.job, "sent": success, "time": time.time()})
        if success:
            return
        time.sleep(45)


if __name__ == "__main__":
    main()
