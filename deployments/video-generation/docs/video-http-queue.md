# BF16 Omni 与本地 2K 的 HTTP 服务和共享队列

2026-11-18：第一次 OOM 清理 worker、冷却 60 秒并检查资源后自动继续后续任务；连续两次 OOM 才进入人工熔断。管理恢复入口为两个端口的 `POST /v1/queue/resume`，完整参数、返回码与轮询见[HTTP 接口文档](video-http-api.md#oom-自动恢复与管理恢复接口)。失败任务保持失败，模型配置和资源上限不变。

2026-11-17：原生 4K 已接入同一模型与队列，使用 `size: "3840x2160"`；4K 初期单任务、单窗口，完整成片状态与示例见 [4K 专项文档](open-h3-4k-http.md)。

本机 5.167 秒原生 4K 已完成 GPU、局域网下载、音轨和完整解码验收。IC worker 随后默认启用通过位级一致核对的数据搬运优化，接口与排队规则不变；测得 4K／2K 单层耗时分别减少约 2.0%／6.6%，不是优化后整段视频的实测比例。[测评、验证范围和回滚](open-h3-exact-performance.md)。

2026-11-16：两个 HTTP 入口同时运行，GPU 由一个持久队列调度。NVFP4 与完整 H3 教师模型保持停止；禁止云端，所有服务关闭开机自启。

| 用途 | API 根地址 | 请求的 `model` |
| --- | --- | --- |
| 图片／文字／视频生成草稿 | `http://192.168.1.11:8001/v1` | `fasth3-omni-bf16` |
| 已有视频的本地 2K／4K 重生成 | `http://192.168.1.11:8002/v1` | `open-h3-2k` |
| BF16 网页 | `http://192.168.1.11:7860` | 网页已配置 BF16 名称 |

两个 API 的 `/docs` 可查看请求格式，`GET /v1/models` 可核对实际名称。模型名明确区分 BF16 与旧 `fasth3-omni` 量化部署；原生 FastVideo 推理后端改为仅监听本机 `127.0.0.1:8003`，由调度器管理，客户端使用上表入口。

## 从另一台机器调用

推荐复制 [video_http_client.py](../tools/video_http_client.py)，只依赖 `requests`：

```bash
python3 -m pip install requests
scp ubuntu@192.168.1.11:/home/ubuntu/workspace/xenoamess_bake_videos/tools/video_http_client.py .

# 默认提交后立即返回任务 JSON；加入 --wait 可等待并下载。
python3 video_http_client.py omni \
  --image ./character.png --video ./motion.mp4 \
  --prompt '保持 <Picture 1> 的角色外观，参考 <Video 1> 的动作。' \
  --size 1344x768 --seconds 5 --seed 1234

# 使用上一条返回的 id；草稿未完成时也可提前提交。
python3 video_http_client.py 2k --source-job video_gen_替换为草稿任务ID \
  --prompt '保持角色、动作和场景，补充清晰细节。' \
  --wait --output ./result-2k.mp4

# 也可直接提交本地已有视频，不经过 Omni。
python3 video_http_client.py 2k --video ./draft.mp4 \
  --wait --output ./result-2k.mp4
```

客户端将本地文件上传到对应 API 的 `POST /v1/files`，使用返回的 `file_id`，不要求素材事先存在服务器。两个入口共享上传记录，单个文件上限 512 MiB。`--wait` 没有固定的整任务超时；关闭客户端不会取消服务器任务。

直接 HTTP 调用时，先上传，再提交：

```bash
curl --noproxy '*' --fail-with-body \
  -F 'file=@./character.png' http://192.168.1.11:8001/v1/files
curl --noproxy '*' --fail-with-body \
  -F 'file=@./motion.mp4' http://192.168.1.11:8001/v1/files
```

将两次返回的 `id` 填入 JSON：

```json
{
  "model": "fasth3-omni-bf16",
  "task": "ref2va",
  "prompt": "保持 <Picture 1> 的外观，参考 <Video 1> 的动作。",
  "image_reference": [{"file_id": "file_图片上传ID"}],
  "video_reference": [{"file_id": "file_视频上传ID"}],
  "size": "1344x768",
  "seconds": 5,
  "num_inference_steps": 8,
  "seed": 1234
}
```

把它保存为 `request.json`，调用：

```bash
curl --noproxy '*' --fail-with-body http://192.168.1.11:8001/v1/videos \
  -H 'Content-Type: application/json' --data-binary @request.json
```

服务立即返回 HTTP 202 和任务 `id`。用 `GET /v1/videos/{id}` 查询，`completed` 后用 `GET /v1/videos/{id}/content` 下载 MP4；`failed` 查看 `error` 和 `/logs`，`DELETE /v1/videos/{id}` 取消。2K 查询、下载使用 8002。

2K 的提交入口为 `POST http://192.168.1.11:8002/v1/videos/regenerations`：

```json
{
  "model": "open-h3-2k",
  "input_video": {"job_id": "video_gen_草稿任务ID"},
  "prompt": "保持角色、动作和场景。",
  "size": "2560x1440",
  "sampler": "up3",
  "seed": 1234
}
```

已有视频先上传，再把 `input_video` 换成 `{"file_id":"file_上传ID"}`。2K 只接受视频和可选文字；参考图片用于前面的 Omni 生成。`job_id` 依赖会等待草稿完成，失败或取消的草稿不会继续重生成。

## 自动重排序与加载边界

- 全局状态：`GET /v1/queue`，任意一个端口均可。包含正在执行、重排序后的就绪队列、等待草稿的任务、当前模型和调度器心跳。
- 同模型内部保持提交顺序；有另一模型等待时，默认连续执行同模型最多 3 个任务。另一模型已等待 30 分钟时，在下一任务或已派发小批次边界优先切换。运行中的推理不会强行中断，因此这不是硬性的 30 分钟完成承诺。
- 队列各模型最多 32 个未完成任务，满时返回 429。任务、上传记录和调度事件落盘在 `outputs/video-queue/queue.sqlite3`；API 重启不重派正在推理的任务。
- BF16 连续任务复用同一个推理后端进程。其 BF16 编码器、DiT 和原版 36 层 VAE 无法同时放进本机显存，内部按阶段加载与释放仍然必要；不能把同模型分组等同于全部权重永久常驻。
- 2K 将相同 `seed`、尺寸、采样器的相邻任务组成最多 2 个任务的小批次，再以每次最多 2 个窗口调用官方批量 `--jobs` 路径。每对窗口共用一轮编码、DiT 计算和解码的模型加载，VAE 在编码、解码两个阶段分别加载；逐片段计算，不合并注意力序列，不降低采样步数或解码精度。
- 空闲 120 秒后释放后台模型进程，两个 HTTP 入口与网页继续在线。任何时候只允许一个 GPU 工作负载。
- 主动取消 2K 小批次中的一个任务时，停止该批次，其他未完成任务保留已验证窗口、重新入队。第一次内存失败会短暂暂停并自动恢复后续任务；连续 OOM 需管理接口人工确认，失败任务不重试。

BF16 默认最大原生横屏 1344×768，也提供 768×1344、832×480、768×768；固定 8 次前向、VSA 0.9、原版 36 层 VAE。接口接受 5–15 秒；本机 BF16 最大尺寸已实测的是 5 秒，15 秒显存可用性尚未验收。重生成输出支持 2560×1440、1440×2560 和新增的 3840×2160，沿用全本地 NVlabs/Sana 开源替代路线，不是官方云端闭源模块。4K 单任务、单窗口执行，完整 GPU 成片验收以 [4K 记录](../deployment/video-queue/4k-validation.json)为准。15 秒采用重叠窗口，其真实长片质量验收仍需单独完成。

## 启动、停止与恢复

项目目录为 `/home/ubuntu/workspace/xenoamess_bake_videos`，以 `ubuntu` 用户运行：

```bash
# 启动两个 HTTP 入口、调度器与 BF16 网页。
systemctl --user start video-gpu-scheduler.service \
  fasth3-omni-bf16.service h3-2k-refiner-http.service fasth3-omni-bf16-web.service

# 只停止 GPU 调度与后台模型；HTTP 保持在线，可查询和下载。
systemctl --user stop video-gpu-scheduler.service

# 全部停止。
systemctl --user stop fasth3-omni-bf16-web.service fasth3-omni-bf16.service \
  h3-2k-refiner-http.service video-gpu-scheduler.service

# 再次启动调度器，恢复队列；取消或失败任务不自动重试。
systemctl --user start video-gpu-scheduler.service
```

只停止 HTTP 服务会停止接单，已入队任务仍由调度器处理。停止调度器会停止其 GPU worker；未完成任务保留 ID 与检查点，在下次手动启动后恢复。BF16 从头重新计算，2K 复用已验证窗口。仅停止网页不会停止任务。

服务定义保存于 `deployment/systemd/`，恢复时：

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
cp deployment/systemd/video-gpu-scheduler.service \
  deployment/systemd/fasth3-omni-bf16*.service \
  deployment/systemd/h3-2k-refiner-http.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable video-gpu-scheduler.service fasth3-omni-bf16.service \
  fasth3-omni-bf16-worker.service fasth3-omni-bf16-web.service h3-2k-refiner-http.service
```

实际模型始终由 `run_isolated.py` 放入 80 GiB 推理 unit，`llmlab.slice` 聚合上限 88 GiB、swap 1 GiB，并保留独立内存看护。前端各 1 GiB、调度器 512 MiB、网页 2 GiB；前端和调度器不导入模型。

检查：

```bash
curl --noproxy '*' http://192.168.1.11:8001/health
curl --noproxy '*' http://192.168.1.11:8002/health
curl --noproxy '*' http://192.168.1.11:8001/v1/queue
journalctl --user -u video-gpu-scheduler.service -n 80 --no-pager
journalctl --user -u llmlab-fasth3-omni-bf16-worker.service -n 80 --no-pager
```

恢复状态、连续 OOM 计数和恢复请求保存在共享队列数据库 `state.memory_recovery`，事件保存于同一数据库的 `events`；`GET /v1/queue` 的 `recovery` 可查看。首次 OOM 后检查 worker 已停止、主机可用内存至少 28 GiB、GPU 无计算进程且空闲显存至少 95%，并在清理后冷却 60 秒，满足条件后恢复后续任务。连续两次 OOM（中间没有成功任务）进入人工熔断。探测失败或资源不满足时继续暂停，不修改模型、内存上限或请求参数。

人工恢复：

```bash
curl --noproxy '*' --fail-with-body -sS \
  -X POST http://192.168.1.11:8001/v1/queue/resume \
  -H 'Content-Type: application/json' -d '{"reason":"已检查故障，继续后续队列"}'
curl --noproxy '*' --fail-with-body -sS http://192.168.1.11:8001/v1/queue
```

两个端口操作同一恢复状态；202 表示请求已落盘，仍须等待 `paused: false`。未暂停时返回 200 且无副作用；调度器离线返回 503，须先手动启动调度器。接口不会重试失败任务、停止正常任务或跳过资源检查。旧版 `outputs/h3-2k-http/inference-hold.json` 会作为需要人工确认的历史暂停导入，恢复后归档；正常运维使用接口，无须删除文件。

## 验收记录

调度策略、同模型顺序、等待上限、跨端口文件与任务依赖、取消、持久化、并发提交、批次原子派发和 OOM 暂停均有 CPU 回归测试：`tests/test_video_queue.py`。这些测试不代表真实模型成片验收。

真实 GPU 验收过程和成片暂存于 `outputs/video-queue-validation-20261116/`，最终结论以 `deployment/video-queue/validation.json` 为准。[此前 BF16 768p 速度测评](omni-bf16-benchmark.md)仍是独立历史基准，包含加载的总耗时为 759.21 秒，不把两种加载策略的差异解释为纯精度倍率。

本轮一次性收尾服务 `video-queue-validation-watch-20261116.service` 只查询已有验收任务、下载核对并更新验收记录，不提交或重启模型。`video-queue-idle-reload-20261116.service` 在验收结束后的空闲任务边界应用已测试的调度清理修复；若调度器被操作者停止或存在派发暂停标记，它不会重新启动服务。两者均为临时 unit，无开机自启。

验收期间若需连同一次性助手停止，可执行：

```bash
systemctl --user stop video-queue-validation-watch-20261116.service \
  video-queue-idle-reload-20261116.service
```

2026-11-17 的原生 4K 验收观察器为 `h3-4k-validation-watch-20261117.service`，同样是无开机自启的一次性 CPU 服务。它只跟踪已经提交的验收任务，完成后从局域网下载，核对 SHA-256、实际分辨率、帧数和音轨，完整解码并制作检查图，更新 `deployment/video-queue/4k-validation.json` 和客户端文档包。它不会提交、重启、取消模型或自动重试失败任务。停止它不会取消 GPU 任务：

```bash
systemctl --user stop h3-4k-validation-watch-20261117.service
journalctl --user -u h3-4k-validation-watch-20261117.service -n 50 --no-pager
```
