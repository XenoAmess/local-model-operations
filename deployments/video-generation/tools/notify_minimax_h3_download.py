#!/usr/bin/env python3
"""Notify the existing Paseo conversation once a download finishes; never activate a model."""

import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "outputs/minimax-h3-full-20261116/notification.json"
DOWNLOADS = (
    ("llmlab-minimax-h3-download-20261116.service", "download-manifest.json", "weight-verification.json"),
    ("minimax-h3-2k-download-queue-20261116.service", "open-2k-download-manifest.json",
     "open-2k-weight-verification.json"),
)


def main():
    cli = os.environ["PASEO_CLI"]
    agent = os.environ["PASEO_AGENT_ID"]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    while True:
        complete, failed = True, False
        for unit_name, manifest_name, report_name in DOWNLOADS:
            manifest = json.loads((ROOT / "deployment/minimax-h3" / manifest_name).read_text())
            unit = subprocess.run(
                ["systemctl", "--user", "show", unit_name, "-p", "ActiveState", "-p", "Result"],
                capture_output=True, text=True, check=True,
            )
            properties = dict(line.split("=", 1) for line in unit.stdout.splitlines() if "=" in line)
            verified = False
            try:
                report = json.loads((ROOT / "deployment/minimax-h3" / report_name).read_text())
                verified = (report.get("status") == "verified"
                            and report.get("revision") == manifest["revision"]
                            and len(report.get("files", [])) == len(manifest["files"]))
            except (OSError, ValueError):
                pass
            complete = complete and verified
            failed = failed or properties.get("ActiveState") == "failed" or properties.get("Result", "success") != "success"
        if not complete and not failed:
            time.sleep(30)
            continue
        if complete:
            message = (
                "[自动下载完成事件，来自本机一次性检查] 官方 H3-Base Ref2VA 与全本地 Open-H3-Regenerate-2K-IC 的权重下载和校验已完成。"
                "请核对 deployment/minimax-h3/weight-verification.json、open-2k-weight-verification.json 和 FastH3 在线状态，"
                "然后通知用户权重已齐；说明本地 2K 是 NVlabs/Sana 开源替代路线，尚未在本机验收推理。"
                "用户禁止官方云端，要求下载后不自动部署；本事件不授权启动、安装或停止任何模型。"
                "如果用户后来明确改变了部署要求，以用户最新指令为准。"
            )
        else:
            message = (
                "[自动下载异常事件，来自本机一次性检查] 完整 MiniMax H3 权重下载服务未正常完成。"
                "请检查 Base 下载、minimax-h3-2k-download-queue-20261116.service 和 llmlab-open-h3-2k-download-20261116.service 日志，"
                "按用户继续下载的授权恢复断点下载。"
                "保留 FastH3 Omni 在线，不自动安装或启动完整 H3，并向用户报告实际情况。"
            )
        sent = subprocess.run(
            [cli, "send", agent, "--behavior", "steer", "--no-wait", message],
            capture_output=True, text=True, timeout=30,
        )
        STATE.write_text(json.dumps({"time": time.time(), "download_complete": complete,
                                     "notification_sent": sent.returncode == 0,
                                     "activation_performed": False}, indent=2) + "\n")
        if sent.returncode == 0:
            print("Download notification queued to the existing conversation", flush=True)
            return
        print("Notification delivery unavailable; retrying in 60 seconds", flush=True)
        time.sleep(60)


if __name__ == "__main__":
    main()
