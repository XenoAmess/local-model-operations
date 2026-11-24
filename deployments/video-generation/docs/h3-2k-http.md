# 完整 H3＋本地 2K 的局域网 HTTP 服务

2026-11-24整理说明：本页是完整教师串联服务的历史配置，当前未运行。正式使用BF16 Omni／8001及IC／8002共享队列；模型关系、加载与速度经验见[系列部署总览](minimax-h3-deployment-experience.md)，现行调用见[HTTP文档](video-http-api.md)。

已有视频单独做 2K，现另设独立的 **8002** 入口，参数与启停见 [独立 2K HTTP 服务](h3-2k-refiner-http.md)。它不依赖本页的 8001 服务运行；两个入口使用共享 GPU 互斥租约串行推理。

2026-11-16 16:33：用户要求先恢复 Omni，本页描述的完整 H3→2K 串联 HTTP 与网页现已停止，8001／7860 当前由 [Omni](fasth3-omni.md) 使用。以下是串联服务的保留配置，不代表当前在线模型；手动启用前需先停止 Omni。约 5 秒的串联任务已生成 2560×1440 成片，尚未完成独立的下载与画面验收；不能仅凭 `/health` 或任务完成状态认定整体验收完成。

本服务将官方完整 BF16 H3-Base Ref2VA 与 [Open-H3-Regenerate-2K-IC](https://huggingface.co/Efficient-Large-Model/Open-H3-Regenerate-2K-IC) 串为一个任务，先生成 768p 草稿，再执行本地 2K 扩散重生成。两个阶段顺序使用同一张 RTX 6000D，阶段进程结束即释放模型和显存。没有调用 MiniMax 云端，2K 模块是 NVlabs/Sana 开源替代实现。固定权重与校验见 [本地 2K 准备](minimax-h3-local-2k.md)。

## 地址和输入

| 用途 | 局域网地址 |
| --- | --- |
| 网页上传、生成、播放、下载 | http://192.168.1.11:7860 |
| HTTP API | http://192.168.1.11:8001/v1 |
| OpenAPI 交互文档 | http://192.168.1.11:8001/docs |
| 健康状态与队列 | http://192.168.1.11:8001/health |
| 模型别名 | `minimax-h3-2k` |

文字＋参考图片和／或参考视频生成，亦可附加音频参考。最多 9 张图片、3 个视频、3 段音频，总数不超过 12。至少提供一张图片或一个视频，并填写提示词。素材在提示词中按类型与顺序使用 `<Picture 1>`、`<Video 1>`、`<Audio 1>`。

输出选项：`2560x1440` 横屏或 `1440x2560` 竖屏，24 FPS，5–15 秒；网页提供 5、10、15 秒。长视频以重叠窗口执行重生成，并按源帧号合并；不会把重叠帧重复拼入。窗口之间的视觉连续性仍需检查实际成片。

完整 Base 固定 50 步、CFG 1、BF16 权重与密集注意力；精确 AdaLN 主机缓存不复用 FastH3 的固定表。重生成默认 `up3`，可选 `up4` 或 `hf8`，保留完整 IC LoRA。采用逐块 CPU/GPU 搬运与 FFN 分块控制资源；没有剪枝基础模型或将完整模型替换为 FastH3。解码使用原版完整 36 层 VAE（FP32、空间分块），未启用另行下载的 24 层快速解码器。

## HTTP 调用

端点：

| 请求 | 行为 |
| --- | --- |
| `POST /v1/files` | multipart `file` 上传，返回 `file_id`，单文件最多 512 MiB |
| `POST /v1/videos` | 图片／视频参考 → 完整 H3 → 本地 2K，返回异步任务 |
| `POST /v1/videos/regenerations` | 已有草稿视频 → 本地 2K，跳过 Base 阶段 |
| `GET /v1/videos/{id}` | 状态、阶段、进度及完成后的输出信息 |
| `GET /v1/videos/{id}/content` | 下载 MP4，支持浏览器范围读取 |
| `GET /v1/videos/{id}/logs` | 该任务末尾的运行日志 |
| `DELETE /v1/videos/{id}` | 取消排队或正在执行的任务 |

外部调用方先上传文件，随后在对应引用中使用 `file_id`。网页上传的服务器本机路径也可在允许目录内引用；不允许任意主机路径或通过接口抓取外部媒体 URL。

```python
import json
import time
import requests

api = "http://192.168.1.11:8001"
client = requests.Session()
client.trust_env = False

def upload(path):
    with open(path, "rb") as stream:
        response = client.post(api + "/v1/files", files={"file": stream}, timeout=180)
    response.raise_for_status()
    return response.json()["id"]

image_id = upload("character.png")
video_id = upload("motion.mp4")
response = client.post(api + "/v1/videos", json={
    "model": "minimax-h3-2k",
    "prompt": "Use the character in <Picture 1> and follow the motion in <Video 1>.",
    "image_reference": [{"file_id": image_id}],
    "video_reference": [{"file_id": video_id}],
    "seconds": 15,
    "size": "1440x2560",
    "seed": 1234,
}, timeout=30)
response.raise_for_status()
job = response.json()
with open("job.json", "w") as stream:
    json.dump(job, stream)
while job["status"] not in {"completed", "failed", "cancelled"}:
    print(job["status"], job.get("stage"), job.get("progress"))
    time.sleep(5)
    response = client.get(api + "/v1/videos/" + job["id"], timeout=30)
    response.raise_for_status()
    job = response.json()
if job["status"] != "completed":
    raise RuntimeError(job.get("error") or job["status"])
with client.get(api + "/v1/videos/" + job["id"] + "/content", stream=True, timeout=180) as response:
    response.raise_for_status()
    with open("result-2k.mp4", "wb") as stream:
        for chunk in response.iter_content(1024 * 1024):
            stream.write(chunk)
```

已有草稿视频直接重生成：先通过 `/v1/files` 上传，然后向 `/v1/videos/regenerations` 提交 `{"input_video":{"file_id":"file_..."},"prompt":"原始生成提示词","size":"2560x1440"}`。约 4.7–15.1 秒的输入在 24 FPS 时间轴上处理；更长输入不会作为本服务的支持范围。

任务和上传记录保存在 SQLite，重启后任务 ID 保留。重启时恢复未完成任务；已验证的草稿和窗口不会重复推理。队列串行执行，最多 8 个未完成任务；客户端断线不取消任务。取消后不会在重启时重新排队。

## 启动、停止与回滚

目录为 `/home/ubuntu/workspace/xenoamess_bake_videos`，使用 `ubuntu` 用户的 systemd 服务，不需要 `sudo`。

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
python3 tools/setup_h3_2k_env.py
cp deployment/systemd/h3-2k-http.service deployment/systemd/h3-2k-web.service \
  ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable h3-2k-http.service h3-2k-web.service

systemctl --user stop qwen38-coder.service fasth3-v2.service \
  fasth3-omni-web.service fasth3-omni.service minimax-h3-web.service minimax-h3.service
systemctl --user start h3-2k-http.service h3-2k-web.service

curl --noproxy '*' --fail http://127.0.0.1:8001/health
journalctl --user -u h3-2k-http.service -f

# 停止网页、API 和正在执行的模型任务，释放显存。
systemctl --user stop h3-2k-web.service h3-2k-http.service

# 如需回滚到原 FastH3 Omni，先停止上面两个服务，再手动启动：
systemctl --user start fasth3-omni.service fasth3-omni-web.service
```

不启用开机自启。普通启停不删除任务或成品。模型推理由 `run_isolated.py` 在独立 `llmlab-h3-2k-job-*.service` 中执行，保持单任务 80 GiB、聚合 88 GiB 主机内存上限与独立内存看护。出现 OOM 后暂停后续排队推理，保留证据；先检查原因、完成修复，再删除 `outputs/h3-2k-http/inference-hold.json` 解除暂停，不能直接提高上限绕过故障。

## 文件与恢复

- `tools/serve_h3_2k_http.py`：HTTP、上传、SQLite 任务和串行隔离调度。
- `tools/h3_2k_worker.py`：Base 草稿、窗口、重生成、拼接、成片检查和断点文件。
- `tools/h3_base_runtime.py`：完整 BF16 H3 Ref2VA 的单次进程。
- `tools/h3_ic_runtime.py`：固定 IC 源码的显存搬运、FFN 分块与无损中间视频适配；不修改已校验的下载包。
- `tools/setup_h3_2k_env.py`：建立独立 Python 入口，共享原环境的只读包与 FastVideo 源码，不升级原环境；版本见 `deployment/minimax-h3/2k-environment.json`。
- `outputs/h3-2k-http/jobs/{id}/`：请求、阶段状态、日志、草稿、中间窗口、`result.mp4` 和校验摘要。
- `outputs/h3-2k-http/jobs.sqlite3`、`uploads/`：恢复任务 ID 和素材时必须保留。

服务配置含本机绝对路径，迁移用户或目录时需修改。原始权重通过硬链接共享，只在内存中合并适配器；不得把合并后的权重原地写回共享文件。
