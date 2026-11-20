#!/usr/bin/env python3
"""Build a small LAN-downloadable client and documentation bundle; no media or credentials."""

import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "omni-web/outputs/video-http-client-20261120.zip"
SOURCES = ["docs/video-http-api.md", "docs/video-http-queue.md", "tools/video_http_client.py",
           "docs/video-queue-management.md", "deployment/video-queue/full-sequence-validation.json",
           "deployment/video-queue/recovery-verification-20261118.json",
           "deployment/video-queue/validation.json", "docs/open-h3-4k-http.md",
           "deployment/video-queue/4k-validation.json", "docs/open-h3-exact-performance.md",
           "deployment/video-queue/4k-exact-performance.json",
           "deployment/video-queue/performance/gpu-4k.json",
           "deployment/video-queue/performance/gpu-2k.json",
           "deployment/video-queue/performance/real-input-parity.json"]


def main():
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    temporary = DESTINATION.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in SOURCES:
            bundle.write(ROOT / name, arcname=name)
        bundle.writestr("README.txt", "调用手册：docs/video-http-api.md\n"
                        "安装依赖：python3 -m pip install requests\n"
                        "客户端：python3 tools/video_http_client.py --help\n"
                        "BF16: http://192.168.1.11:8001/v1  model=fasth3-omni-bf16\n"
                        "2K/4K: http://192.168.1.11:8002/v1  model=open-h3-2k\n"
                        "4K: add --size 3840x2160; see docs/open-h3-4k-http.md\n"
                        "实时队列：http://192.168.1.11:8001/v1/queue\n"
                        "独立状态：http://192.168.1.11:8004/v1/service/status\n"
                        "插队、取消、优先级、分页和维护：docs/video-queue-management.md\n"
                        "4K: <=124 frames use original route; >124 use full-sequence IC, no window fallback.\n"
                        "管理恢复：POST http://192.168.1.11:8001/v1/queue/resume，JSON {}；8002 同效。\n"
                        "202 表示恢复请求已接受；轮询队列直到 paused=false，失败任务不会重试。\n"
                        "验收快照以打包时为准；服务运行状态请查询 /health 和 /v1/queue。\n")
    with zipfile.ZipFile(temporary) as bundle:
        assert bundle.testzip() is None
    temporary.replace(DESTINATION)
    report = {"path": str(DESTINATION), "bytes": DESTINATION.stat().st_size,
              "sha256": hashlib.sha256(DESTINATION.read_bytes()).hexdigest(), "sources": SOURCES,
              "download_url": "http://192.168.1.11:7860/gradio_api/file=" + str(DESTINATION)}
    (ROOT / "deployment/video-queue/client-package.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
