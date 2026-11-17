# Open-H3 原生 4K HTTP

2026-11-17：现有本地 IC 服务新增 UHD 横屏 **3840×2160**。名称仍为 `open-h3-2k`，API 仍为 `http://192.168.1.11:8002/v1`；默认 2K 和已有调用保持不变。完整 GPU 成片验收状态见 [4K 验收记录](../deployment/video-queue/4k-validation.json)。

本机首条 124 帧／24 fps／5.167 秒原生 4K 已完整生成并通过局域网下载、哈希、音轨和完整解码核对。基线端到端 **4666.79 秒（77 分 47 秒）**，其中去噪 4039.2 秒、原版 VAE 解码及无损窗口写入 366 秒。已抽看首、中、尾帧，未见明显空白或损坏；15 秒 4K 尚未完成真实成片验收。保持运算结果的性能优化另见 [性能说明](open-h3-exact-performance.md)，不能把候选单层速度当作完整视频加速比。

## 调用

使用现有 [Python 客户端](../tools/video_http_client.py)，增加 `--size 3840x2160`：

```bash
python3 video_http_client.py 2k --video ./draft.mp4 \
  --prompt '保留人物、动作、镜头和场景，补充清晰细节。' \
  --size 3840x2160 --sampler up3 --seed 1234 \
  --wait --output ./result-4k.mp4

python3 video_http_client.py 2k --source-job video_gen_实际草稿任务ID \
  --size 3840x2160 --wait --output ./result-4k.mp4
```

直接 HTTP：先用 `POST /v1/files` 上传视频，再向 `POST /v1/videos/regenerations` 提交：

```json
{
  "model": "open-h3-2k",
  "input_video": {"file_id": "file_实际视频上传ID"},
  "prompt": "保留人物、动作、镜头和场景。",
  "size": "3840x2160",
  "sampler": "up3",
  "seed": 1234
}
```

`input_video` 也可为 `{"job_id":"video_gen_实际草稿任务ID"}`，支持等待尚未完成的 Omni 草稿。提交返回 202；通过 `GET /v1/videos/{id}` 查询，完成后从 `GET /v1/videos/{id}/content` 下载。上传、轮询、取消范例见 [跨机器调用文档](video-http-api.md)。

4K 与 BF16 Omni、2K 共用同一 GPU 队列，提交成功后仍可能排队。实时状态为 `/v1/queue`，不是同步等待整段推理的 HTTP 接口。

## 原生路线与资源

- 沿用已下载的 Open-H3-Regenerate-2K-IC 权重，直接调用上游 `--resolution 4k`。
- 模型计算 3840×2176 的对齐画面，按官方逻辑上下各裁 8 行，输出 3840×2160；最终拼接不做空间放大。
- 保持 BF16 DiT、原版 36 层 FP32 tiled VAE、默认 `up3` 三步采样和完整音轨处理。
- 4K 单任务、单窗口执行；2K 原有每次最多两个窗口保持不变。4K 不与另一 GPU 模型同时推理。
- 4K 使用上游 `--save-latent`，在解码前保存精确去噪潜变量到 `window-XX-4k.latent.pt`，便于保留昂贵的去噪结果。
- 当前自动续跑复用的是已验证完成的视频窗口；潜变量检查点保留供故障恢复使用，尚不支持自动从该文件跳过采样、单独续解码。
- 保留推理 unit 80 GiB、聚合 slice 88 GiB、swap 1 GiB 上限及独立内存看护；OOM 后暂停队列，不自动重试或放宽限制。
- 输入沿用约 4.7–15.1 秒范围，长片使用重叠窗口；真实 4K／15 秒成片尚未验收，不能由参数范围推断所有组合均已验证。

4K 窗口命名为 `window-XX-4k.mkv`；2K 检查点文件名保持原样。模型、端口、服务 unit 和启停方式保持不变，见 [队列运维文档](video-http-queue.md)。

首条完整 4K 验收任务为 `video_gen_8aa9ab4652a14d608c20db3c4cde7798`，输入为此前已验收的 1344×768、124 帧视频。可从局域网查询：

```bash
curl --noproxy '*' http://192.168.1.11:8002/v1/videos/video_gen_8aa9ab4652a14d608c20db3c4cde7798
```

提交返回 202、GPU 已开始采样，均不代表完整成片验收通过。一次性观察器将在任务结束后自动核对局域网下载、3840×2160／124 帧／24 fps、音轨、完整解码和原生计算路径，将真实耗时及成败写入上方验收记录；不会自动重试失败任务。人眼画质检查另行记录。
