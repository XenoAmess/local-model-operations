#!/usr/bin/env python3
"""Return this conversation to final HTTP validation when a long GPU task finishes."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = requests.Session()
    client.trust_env = False
    while True:
        try:
            response = client.get("http://127.0.0.1:8001/v1/videos/" + args.job, timeout=10)
            response.raise_for_status()
            job = response.json()
        except requests.RequestException:
            time.sleep(30)
            continue
        if job["status"] not in {"completed", "failed", "cancelled"}:
            time.sleep(20)
            continue
        message = (
            f"[自动 HTTP 验收事件] 本地 H3 2K 任务 {args.job} 状态为 {job['status']}。"
            "请按用户部署完整 H3＋全本地 2K HTTP 服务的授权继续完成验收：读取任务状态、worker.log、"
            "result.json，成功时通过局域网实际下载并核对成片、检查画面，更新 docs 和 Git；失败时保留证据并修复。"
            "当前服务 h3-2k-http.service 与 h3-2k-web.service，地址 192.168.1.11:8001/v1 和 :7860。"
            "严禁云端与开机自启，保留80/88 GiB内存限制。15秒使用重叠窗口，尚需明确区分时间轴软件测试"
            "与真正15秒模型成片验收。用户后续的新指令优先；本事件不授权违背用户停机或取消要求。"
        )
        result = subprocess.run([os.environ["PASEO_CLI"], "send", os.environ["PASEO_AGENT_ID"],
                                 "--behavior", "steer", "--no-wait", message], capture_output=True, text=True, timeout=30)
        record = {"time": time.time(), "job": args.job, "status": job["status"], "sent": result.returncode == 0}
        (root / "outputs/h3-2k-deployment-20261116/http-validation-notification.json").write_text(
            json.dumps(record, indent=2) + "\n")
        if result.returncode == 0:
            return
        time.sleep(60)


if __name__ == "__main__":
    main()
