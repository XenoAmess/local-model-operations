# MiniMax H3 完整 BF16 Ref2VA 部署

状态（2026-11-16）：用户已明确授权部署串行的完整 H3＋本地 2K HTTP 服务，当前入口见 [2K HTTP 运维](h3-2k-http.md)，原 FastH3 已停止。下文保留独立 Base 服务配置；该独立服务未安装或启动，避免与当前 HTTP 服务争用端口和 GPU。策略记录为 `deployment/minimax-h3/activation-policy.json`。

本机部署官方 [MiniMaxAI/MiniMax-H3](https://huggingface.co/MiniMaxAI/MiniMax-H3) 的 H3-Base Ref2VA，全秩 BF16 编码器、生成模型和原版 VAE；固定 revision 为 `0919fb684102ef115126612f3fbb84d1027e7317`。配置为 50 步、CFG 1.0、密集注意力。它支持文字与参考图片、视频、音频联合生成。

官方 Context-IR 和 H3-Regenerate-2K 属于未开源的托管系统。本机部署范围是公开的完整 H3-Base Ref2VA，基础输出为 768p、24 FPS、最长约 15 秒；官方托管 2K 全流程不能仅凭公开权重在本机复现。参见 [官方仓库说明](https://github.com/MiniMax-AI/MiniMax-H3)。

完全本地 2K 重生成已纳入需求，采用另行公开的 Open-H3-Regenerate-2K-IC 路线准备权重。其新增下载、手动入口、显存及 15 秒限制见 [本地 2K 方案](minimax-h3-local-2k.md)。不使用官方云端。

## 权重下载与环境

沿用本机 `FastVideo/.venv/`、CUDA 13.2、本地编译内核和 FastVideo 固定基线，详情见 [配置恢复](deployment-git.md)。下载清单为 `deployment/minimax-h3/download-manifest.json`，包括官方 Ref2VA 所需的 63 个文件、约 134.16 GiB；无需下载重复的 FL2VA 和另一套 Diffusers 布局。相同文件只有官方 SHA-256 核对通过后才复用。

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
mkdir -p llm-lab/logs
python3 llm-lab/scripts/run_isolated.py \
  --unit llmlab-minimax-h3-download-manual --memory-gib 6 --wait -- \
  "$PWD/FastVideo/.venv/bin/python" "$PWD/tools/download_minimax_h3.py"
```

下载器固定 revision，使用两条下载通道，每条同时只处理一个文件，关闭 Xet 高性能缓冲；下载和 SHA-256 校验均在隔离服务中执行。已完成的文件可以复用，下载中断可重试。完整成功后生成 `deployment/minimax-h3/weight-verification.json`。运行服务只读取本地权重，不在线补下载。

当前下载单元为 `llmlab-minimax-h3-download-20261116.service`。一次性检查单元 `minimax-h3-download-notify-20261116-v2.service` 每 30 秒读取下载状态，在 Base 和本地 2K 包均校验成功后，通过 Paseo CLI 向原对话排入完成通知；异常退出时排入恢复下载的检查请求。它不创建新代理，不操作模型服务，通知送达后退出，也不随开机启动。脚本为 `tools/notify_minimax_h3_download.py`，交付状态保存在本机 `outputs/minimax-h3-full-20261116/notification.json`。

## 手动启动与停止

模型与 FastH3 Omni 使用相同 API 和网页端口，须先停止上一模型及网页。Qwen 和视频模型共用显卡，不同时启动。

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
mkdir -p ~/.config/systemd/user
cp deployment/systemd/minimax-h3.service deployment/systemd/minimax-h3-web.service \
  ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable minimax-h3.service minimax-h3-web.service

systemctl --user stop qwen38-coder.service fasth3-v2.service \
  fasth3-omni-web.service fasth3-omni.service
systemctl --user start minimax-h3.service minimax-h3-web.service
curl --noproxy '*' --fail http://127.0.0.1:8001/health
curl --noproxy '*' --fail http://127.0.0.1:8001/v1/models

# 停止模型和网页，释放显存；不会自动重启。
systemctl --user stop minimax-h3-web.service minimax-h3.service

# 查看加载及推理日志。
journalctl --user -u llmlab-minimax-h3.service -f
```

服务不启用开机自启。`minimax-h3.service` 通过隔离启动器运行 `llmlab-minimax-h3.service`，保留推理 80 GiB、实验总计 88 GiB 的主机内存限制和独立内存看护。

完整编码器与生成模型依次加载、使用后释放，减少同时常驻的内存。生成模型和编码器使用 BF16，视频 VAE 沿用 FastVideo 的 FP32 精度配置。AdaLN 使用本模型的 BF16 权重在主机缓存，并对请求 timestep 精确计算；不使用 FastH3 的 8 步固定表。模型和编码器均未量化，未启用稀疏注意力、低秩剪枝或 FastH3 蒸馏调度。分阶段加载会增加每次请求的权重加载时间；完整模型的生成速度须以本机实测为准。

## 局域网 HTTP 与网页

| 用途 | 地址 |
| --- | --- |
| 网页上传、生成、播放和下载 | http://192.168.1.11:7860 |
| HTTP API | http://192.168.1.11:8001/v1 |
| 交互式接口说明 | http://192.168.1.11:8001/docs |
| 模型名称 | `minimax-h3-ref2va` |

网页复用 `omni-web/app.py`，由独立启动脚本设置模型名称和 50 步。原 Omni 启动入口仍使用原名称和 8 步。输入支持最多 9 张图片、3 个视频、3 段音频，总数不超过 12 个；视频和音频的时长要求见官方模型说明。当前网页提供 5、10、15 秒及 480p/768p 画幅。

API 使用异步任务。客户端保留原始请求及素材，提交后轮询，完成后下载：

```python
import time
import requests

client = requests.Session()
client.trust_env = False  # 本例走局域网。
base = "http://192.168.1.11:8001"
with open("reference.png", "rb") as image:
    data_url = __import__("base64").b64encode(image.read()).decode()
request = {
    "model": "minimax-h3-ref2va",
    "task": "ref2va",
    "prompt": "The character in <Picture 1> waves toward the camera.",
    "image_reference": [{"image_url": "data:image/png;base64," + data_url}],
    "size": "832x480",
    "seconds": "5",
    "num_inference_steps": 50,
    "seed": 1234,
}
response = client.post(base + "/v1/videos", json=request, timeout=90)
response.raise_for_status()
job = response.json()
while job["status"] not in {"completed", "failed"}:
    time.sleep(5)
    response = client.get(base + "/v1/videos/" + job["id"], timeout=30)
    response.raise_for_status()
    job = response.json()
if job["status"] == "failed":
    raise RuntimeError(job.get("error"))
with client.get(base + "/v1/videos/" + job["id"] + "/content",
                stream=True, timeout=180) as response:
    response.raise_for_status()
    with open("result.mp4", "wb") as target:
        for chunk in response.iter_content(1024 * 1024):
            target.write(chunk)
```

视频参考使用 `video_reference: [{"video_url": ...}]`，音频使用 `audio_reference: [{"audio_url": ...}]`。提示词按素材顺序使用 `<Picture 1>`、`<Video 1>`、`<Audio 1>`。图片可使用上述数据 URL；视频与音频可通过网页上传至服务器后引用，或使用服务可访问的公网 HTTP 地址。本机路径只允许 `omni-web/uploads/` 内文件。服务默认拒绝引用私网 HTTP 素材地址。

FastVideo 的任务索引保存在内存中，服务重启后旧 ID 可能返回 404。调用方需持久化请求和下载结果，遇到失败或未知 ID 时重新提交。`/health` 仅表示服务启动，使用分阶段加载时不代表全部权重已经完成推理验证。

## 回滚到已验证的 FastH3 Omni

```bash
systemctl --user stop minimax-h3-web.service minimax-h3.service
systemctl --user start fasth3-omni.service fasth3-omni-web.service
```

原配置和完整 AdaLN 修复保存在本仓库的 `cc610ea` 提交；本机原权重和预计算表保留。回滚后 API 模型名称为 `fasth3-omni`，采用 8 步。
