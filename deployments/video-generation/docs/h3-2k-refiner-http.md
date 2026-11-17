# 独立的本地 2K 重生成 HTTP 服务

当前 8002 已接入[BF16 Omni／2K 共享队列](video-http-queue.md)，无需再手动停止 Omni 才能处理 2K；当前启停、上传与调用以该文档为准。本页保留此前独立版本的接口背景和历史验收。

2026-11-16：独立入口为 `http://192.168.1.11:8002/v1`，交互文档为 `http://192.168.1.11:8002/docs`，健康检查为 `/health`，模型别名为 `open-h3-2k`。它与 8001 的完整 H3→2K 管线使用不同的服务、上传目录、任务数据库和任务 ID；上传文件的 ID 不能跨端口使用。

核心流程是 **已有视频＋可选文字 → Open-H3-Regenerate-2K-IC → 2K 视频**。没有草稿生成阶段，允许上传 Omni 或其他来源的视频。重生成器内部仍加载完整 H3 BF16 底座及专用适配器，不会运行完整 H3 的 50 步草稿生成，也没有调用云端。没有额外图片、动作视频或音频参考字段；这些参考应先用于草稿生成。

## 请求参数

`POST /v1/videos/regenerations` 接受以下 JSON 字段：

| 字段 | 必填 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `input_video` | 是 | 无 | 推荐 `{"file_id":"file_..."}`，先上传视频 |
| `prompt` | 否 | 空字符串 | 草稿的原始提示词或对应画面描述，最多 50,000 字符 |
| `size` | 否 | `2560x1440` | 横屏 `2560x1440` 或竖屏 `1440x2560` |
| `seed` | 否 | `1234` | 随机种子，整数，范围 0 到 2^62−1 |
| `sampler` | 否 | `up3` | `up3`、`up4` 或 `hf8`；分别使用 3、4、8 步，不表示已验证的画质排名 |
| `model` | 否 | `open-h3-2k` | 本入口的模型名称 |

不接收 `seconds`、`fps`、参考图或额外参考视频等字段，未知字段返回 422，避免误以为被模型使用。时长从输入视频取得，当前约 5–15 秒，输出为 24 FPS。输入最多 512 MiB，格式支持 MP4/MOV/MKV/WebM/AVI/M4V。输入帧率和尺寸会归一化；输入与目标画幅不一致时按目标画幅居中裁剪。输入音轨存在时保留其内容并重新编码为 AAC，不重新生成音频。

本机路径只允许服务上传目录或 `omni-web/uploads`；不通过接口获取远程媒体 URL。另一台机器应始终使用上传返回的 `file_id`。

```bash
# 上传后，把返回的 file_... 填入下面的请求。
curl --fail -F 'file=@draft.mp4' http://192.168.1.11:8002/v1/files

curl --fail http://192.168.1.11:8002/v1/videos/regenerations \
  -H 'Content-Type: application/json' \
  -d '{"input_video":{"file_id":"file_..."},"prompt":"草稿原始提示词","size":"1440x2560","seed":1234,"sampler":"up3"}'

# 使用返回的任务 ID 查询、下载或取消。
curl --fail http://192.168.1.11:8002/v1/videos/video_gen_...
curl --fail -o result-2k.mp4 http://192.168.1.11:8002/v1/videos/video_gen_.../content
curl --fail -X DELETE http://192.168.1.11:8002/v1/videos/video_gen_...
```

任务异步执行，最多 8 个排队或正在运行的任务。完成后 `GET /v1/videos/{id}/content` 下载；失败时查询任务 `error` 与 `/logs`。15 秒采用重叠窗口；时间轴测试已通过，完整 15 秒模型成片与接缝画质尚未验收。已通过的实际模型验证为约 5 秒的视频，不把批处理支持当作 15 秒画质验收。

## 启动和停止

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
cp deployment/systemd/h3-2k-refiner-http.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable h3-2k-refiner-http.service
systemctl --user start h3-2k-refiner-http.service
curl --noproxy '*' --fail http://127.0.0.1:8002/health

# 停止本入口和它发起的推理任务。
systemctl --user stop h3-2k-refiner-http.service
```

HTTP 进程本身不加载模型、不常驻占用显存；任务执行时加载，进程结束后释放。无需同时启动 8001 的管线服务或网页。独立服务不启用开机自启；API 内存上限 1 GiB，推理保留原有 80 GiB 与聚合 88 GiB 主机内存限制、独立内存看护。

完整 H3 串联服务（8001）与本服务（8002）的队列使用 `outputs/h3-2k-gpu.lock` 互斥租约，同一时刻只启动一个 GPU 任务；两端队列各自按提交时间处理，不承诺跨端口的全局先来先服务。当前 8001 已切回 Omni，本服务通过检测 `llmlab-fasth3-omni.service` 等待常驻模型停止，再开始 2K；共享显卡切换需要先完成或取消上一阶段任务。两个 2K 队列共用 `outputs/h3-2k-http/inference-hold.json` 内存故障暂停标记，出现故障后先排查，不能提高上限绕过。

本入口状态保存在 `outputs/h3-2k-refiner-http/`，包括 SQLite、上传文件、请求、日志、中间窗口和结果。重启保留任务 ID，已取消的任务不会重新排队，已完成的窗口可复用。它沿用已实际生成 2K 成片的同一 worker；独立端口部署验收覆盖上传、排队、查询、取消和互斥，未为测试端口另外发起一轮模型生成。
