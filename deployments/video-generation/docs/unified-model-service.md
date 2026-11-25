# 局域网统一模型服务

统一入口为 `http://192.168.1.11:8080`。`GET /v1/models` 列出 `qwen38-coder`、`fasth3-omni-bf16`、`open-h3-2k` 和 `blender-review`。一个 SQLite 队列和同一个 GPU 调度器负责执行。网关、任务查询和下载在 GPU 忙时照常工作。

| 功能 | HTTP 路径 |
| --- | --- |
| Qwen | `POST /v1/chat/completions`、`/v1/completions`、`/v1/responses` |
| Qwen 长等待 | `POST /v1/async/chat/completions`，再 `GET /v1/async/chat/completions/{id}` |
| Omni | `POST /v1/videos`，`model=fasth3-omni-bf16` |
| IC 2K／4K | `POST /v1/videos/regenerations`，`model=open-h3-2k` |
| 图片、音频和视频上传 | `POST /v1/files` |
| Blender 资源与任务 | `PUT /v1/render/assets/{sha256}`、`POST /v1/render/jobs`、`GET /v1/render/jobs/{id}` |
| Blender ZIP 下载 | `GET /v1/render/jobs/{id}/result`，支持 `Range` |
| 任务队列 | `GET /v1/queue`、`GET /v1/queue/jobs`、`GET /v1/queue/jobs/{id}` |
| 修改优先级、插队和取消 | `PATCH /v1/queue/jobs/{id}/priority`、`POST /v1/queue/jobs/{id}/promote`、`POST /v1/queue/jobs/{id}/cancel` |
| 服务状态和维护 | `GET /v1/service/status`、`POST /v1/service/maintenance`、`POST /v1/queue/resume` |
| 一小时驻留偏好 | `GET` / `PUT /v1/queue/preferences` |
| 用量与费用 | `GET /v1/usage` 查看任务用量，8080 根路径打开 Bifrost 费用页 |

Omni 参考图、参考视频和音频仍用 `image_reference`、`video_reference`、`audio_reference`。IC 沿用 `input_video`、`size`、`seed`、`sampler`。新视频的 Bifrost ID 可能带 `:openai`。IC 的 `input_video.job_id` 可用这个 ID，也可用旧 `video_gen_…`。两个旧视频端口仍可访问同一任务库，通过 8080 提交才走统一的 Bifrost 计量路径。旧 ID 和已生成内容可通过统一入口读取。[既有媒体字段和参数](video-http-api.md)

例如把队列中已有的草稿转成 4K：

```bash
curl -X POST http://192.168.1.11:8080/v1/videos/regenerations \
  -H 'Content-Type: application/json' \
  -d '{"model":"open-h3-2k","input_video":{"job_id":"video_gen_换成草稿任务ID"},"size":"3840x2160","sampler":"up3"}'
```

用 `GET /v1/videos/{id}` 查询终态并记录实际输出时长和尺寸，再用 `GET /v1/videos/{id}/content` 下载。4K 仍按 24 FPS 归一化后的 124 帧边界分流。[4K 实际分流与文件输入](open-h3-4k-http.md)

## 队列和 GPU 切换

默认保护 `3600` 秒。Qwen 和 Omni 从后端就绪起算，按任务启动的 IC 在进入实际计算阶段起算，Blender 从进渲染阶段起算。还有当前模型的可执行任务时，保护期内优先同模型，普通插队不跨越这条规则。任务做完后可以提前换。只有依赖还未完的任务不会占住 GPU。

保护期结束且其它模型有可运行任务时，等当前 GPU 工作自然结束再切。Qwen 最多派发 32 路，开始排空后不再补发。视频按既有原生路线和并发运行，整段长 4K 不会被一小时计时器打断。空闲时约 120 秒后释放。GPU 锁、故障冷却和 OOM 人工熔断继续共用。

例如把默认保护设为 3600 秒，并将默认值应用到所有模型：

```bash
curl -X PUT http://192.168.1.11:8080/v1/queue/preferences \
  -H 'Content-Type: application/json' \
  -d '{"default_seconds":3600,"models":{}}'
```

`models` 可包含诸如 `"blender-review":600` 的单模型覆盖。整数范围为 0 至 86400。设置写入 SQLite，修改后影响安全边界处的调度。模型注册表定义 worker 地址、适配器、并发和能力。同协议新模型可注册，在新端口启动独立 worker。新协议需要实现适配器及验收。[模型注册表](../deployment/video-queue/model-registry.json)

## Blender 白绮动作验收

运行 Blender 5.3.0 EEVEE、固定的 PBZ `fb7e7cf` 脚本与固定版本 UEFormat。上传的 ZIP 包含 `manifest.json` 和它引用的素材。每个候选 `.blend` 需打包纹理。供体旁边带原始 `sampling_report.json`，其套组哈希必须匹配服务端。示例：

```json
{
  "forms": {"coat_on": "forms/coat_on.blend", "coat_off": "forms/coat_off.blend"},
  "donor": "donor/Delta_SelfTest.blend",
  "cc0_control": "Base_Female.blend",
  "animations": {"Hun_BaiShanDual_Attack_A": "animations/Hun_BaiShanDual_Attack_A.ueanim"}
}
```

使用 `sha256sum review.zip` 取得 SHA-256，然后上传：

```bash
curl -X PUT "http://192.168.1.11:8080/v1/render/assets/$digest" \
  -H 'Content-Type: application/zip' --data-binary @review.zip
```

提交 `POST /v1/render/jobs` 时设置 `Idempotency-Key`。同键同请求返回同一任务，换了请求则返回 409。任务示例：

```json
{
  "kind": "blender_review",
  "input_sha256": "把此处换成 ZIP 的 SHA-256",
  "source_commit": "fb7e7cf",
  "params": {
    "forms": ["coat_on", "coat_off"],
    "cases": ["arms_forward", "arms_abduction", "Hun_BaiShanDual_Attack_A"],
    "sample_indices": [0, 2, 4],
    "views": ["front", "oblique"],
    "resolution": [1280, 1280],
    "samples": 32,
    "engine": "EEVEE",
    "timeout_seconds": 1800
  }
}
```

此组合计划输出 72 张 PNG。`GET /v1/render/jobs/{id}` 返回实际进度、排队和运行耗时，以及 ZIP SHA-256。结果含每个形态的 `motion_report.json`、PNG、文件哈希清单与运行日志。下载走 `/result`，取消用 `DELETE /v1/render/jobs/{id}`。`completed` 代表文件交付成功，动作报告的 `pending_review` 或 `failed` 仍按 PBZ 的人工验收规则处理。[PBZ 渲染提案与放行规则](https://github.com/XenoAmess/PBZ_vivhite_mod/blob/fb7e7cf/qa/MAINTENANCE.md#6000d-渲染节点-http-接口提案)

单个 ZIP 上限 2 GiB，解包上限 6 GiB，每任务最多 512 张图。分辨率每边 128 至 4096，样本 1 至 128。上传只允许相对路径数据文件，Blender 禁用自动执行，worker 在隔离 GPU 单元内运行。

## Blender 是否适合 Bifrost 计价

适合按交付图片记账。Bifrost 2.6 的 `image_generation` 支持每张图片价格、分辨率档位、像素价格和固定请求费 `cost_per_request`。固定费可以和用量价格叠加。异步图片入口等 Blender 生成真实 PNG 后回传图片列表。排队和轮询不增加输出张数。[Bifrost 自定义价格](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/docs/providers/custom-pricing.mdx) · [异步图片路由](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/transports/bifrost-http/handlers/asyncinference.go)

要经过 Bifrost 记录，向 `POST /v1/async/images/generations` 提交带有前述任务 JSON 的 `render` 对象，顶层添加 `"model":"blender-review"`、`"prompt":"PBZ motion review"` 和稳定的 `render_idempotency_key`。提示词用作日志标签。用 `GET /v1/async/images/generations/{id}` 查询 Bifrost 异步任务，PNG 下载 URL 里带共享队列的 `render_…` ID，ZIP 可用该 ID 下载。同一渲染任务只允许一次成功返回给图像计价通道。直接调用 `/v1/render/jobs` 的任务也进统一队列，用量在 `/v1/usage` 中可查。

Bifrost 的自定义价格基于已支持的请求类型。按 GPU 占用时长、采样量或复杂度计费时，节点可按确认后的规则计算金额，在图片响应中回传 `usage.cost.total_cost`，Bifrost 会使用该金额。当前 `run_seconds` 是渲染流程墙钟时间，包含本地处理，排队时间另记。若需按 GPU 独占时段结算，需要定义并记录相应计时区间。[图片用量结构](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/core/schemas/images.go) · [Bifrost 费用计算](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/framework/modelcatalog/datasheet/cost.go#L568)

同一 Bifrost 二进制在隔离实验中，请求 `n=1`、实际返回 72 张图，测试单价 0.01 USD／张时只记一次 0.72 USD。另一笔由上游报告 0.123 USD，日志采用 0.123 USD。重复轮询未增加费用。生产 Blender 和视频尚无新费率。

## 本机验收

| 测试 | 结果 |
| --- | --- |
| Qwen | 8080 常规聊天与 SSE 均真实响应，Bifrost 按已有规则记账 |
| Omni | 新生成 832×480、124 帧；经 8080 下载、SHA-256 与全片解码通过，Bifrost 记录实际尺寸和 API 时长 |
| IC 4K | 已有整段成片经 8080 断点下载返回 206，4K 提交字段已做隔离转发验证 |
| PBZ Blender | 5.3.0 EEVEE 实际渲染两个形态、两个动作，其中一个为游戏原生 UE 动作。8 张 128×128 PNG，两份动作报告，ZIP 和文件哈希、HTTP 206、Bifrost `image_generation` 日志均通过。两份动作报告为 `pending_review` |

PBZ 测试用公开发布的两个候选形态，从原始参考素材重建供体和 CC0 对照。验收只运行了上述 8 图配置。[技术验收摘要](../deployment/video-queue/unified-model-verification-20261125.json)

## 启动、停止和恢复

```bash
systemctl --user start video-gpu-scheduler.service fasth3-omni-bf16.service h3-2k-refiner-http.service
systemctl --user start unified-model-http.service bifrost-lan.service bifrost-edge.service
```

Qwen worker 由调度器按需启动，监听 loopback 8005。网关内部 8006 是 CPU 适配层。8080 的 Bifrost 使用 [修复分支提交 b8eedb4](https://github.com/XenoAmess/bifrost/commit/b8eedb4bc3b466ffbcd256da6525c84965a64740) 构建的完整费用页。现有本机 OpenAI provider 地址为 `http://127.0.0.1:8006`，启用 `openai_config.video_generation_json`，并将三个媒体模型加入允许列表。provider 超时为 18 小时，自动重试为 0。依赖与二进制版本见[技术验收摘要](../deployment/video-queue/unified-model-verification-20261125.json)。

停止前，通过 `POST /v1/service/maintenance` 提交 `{"enabled":true,"reason":"planned shutdown"}` 停接新任务。等 `GET /v1/service/status` 的 `running_jobs` 清空后，再停止：

```bash
systemctl --user stop video-gpu-scheduler.service
systemctl --user stop fasth3-omni-bf16.service h3-2k-refiner-http.service
systemctl --user stop bifrost-edge.service bifrost-lan.service unified-model-http.service
```

重新启动后用同一维护接口发送 `{"enabled":false}` 恢复接单。通过 `GET /v1/service/status` 确认已恢复；OOM 人工熔断由 `POST /v1/queue/resume` 单独处理。上次运行的二进制、配置、SQLite 和 Caddy 文件保存在本机 `outputs/unified-model-activation-20261125/before/`。全部服务按需启动，无开机自启。[Bifrost 参数适配历史](bifrost-local-video-json-2026-11-25.md)
