# 局域网统一模型服务

统一入口为 `http://192.168.1.11:8080`。`GET /v1/models` 列出 `qwen38-coder`、`fasth3-omni-bf16`、`open-h3-2k` 和 `blender-review`。一个 SQLite 队列和同一个 GPU 调度器负责执行。网关、任务查询和下载在 GPU 忙时照常工作。

| 功能 | HTTP 路径 |
| --- | --- |
| Qwen | `POST /v1/chat/completions`、`/v1/completions`、`/v1/responses` |
| Qwen 长等待 | `POST /v1/async/chat/completions`，再 `GET /v1/async/chat/completions/{id}` |
| Omni | `POST /v1/videos`，`model=fasth3-omni-bf16` |
| IC 2K／4K | `POST /v1/videos/regenerations`，`model=open-h3-2k` |
| 图片、音频和视频上传 | `POST /v1/files` |
| Blender 素材上传 | `PUT /v1/render/assets/{sha256}` |
| Blender 正式提交（计入 Bifrost） | `POST /v1/async/images/generations`，再 `GET /v1/async/images/generations/{id}` |
| Blender 渲染进度和回执 | `GET /v1/render/jobs/{render_id}` |
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

用 `GET /v1/videos/{id}` 查询终态和实际输出规格，再用 `GET /v1/videos/{id}/content` 下载。本机 8080 的进度查询直接读取共享队列。通过本机内置 `openai` provider 提交的作业由 Bifrost 后台在终态自动结算一次，客户端停止轮询也可结算。单独部署命名自定义 provider 时，应通过该 Bifrost 实例轮询视频查询接口直到终态来触发结算。4K 仍按 24 FPS 归一化后的 124 帧边界分流。[4K 实际分流与文件输入](open-h3-4k-http.md) · [Bifrost 参数适配与结算](bifrost-local-video-json-2026-11-25.md)

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

**正式作业用 Bifrost 异步图片接口提交。** 即使同样请求 8080，`POST /v1/render/jobs` 也只走直连队列，费用估值可在 `/v1/usage` 查询，该作业不会出现在 Bifrost 费用页。素材上传和结果下载使用各自的渲染接口。

运行 Blender 5.3.0 EEVEE、固定的 PBZ `fb7e7cf` 脚本与固定版本 UEFormat。上传的 ZIP 包含 `manifest.json` 和它引用的素材。每个候选 `.blend` 需打包纹理。供体旁边带原始 `sampling_report.json`，其套组哈希必须匹配服务端。示例：

```json
{
  "forms": {"coat_on": "forms/coat_on.blend", "coat_off": "forms/coat_off.blend"},
  "donor": "donor/Delta_SelfTest.blend",
  "cc0_control": "Base_Female.blend",
  "animations": {"Hun_BaiShanDual_Attack_A": "animations/Hun_BaiShanDual_Attack_A.ueanim"}
}
```

### 上传素材

```bash
base=http://192.168.1.11:8080
digest=$(sha256sum review.zip | cut -d ' ' -f 1)
curl -fsS -X PUT "$base/v1/render/assets/$digest" \
  -H 'Content-Type: application/zip' --data-binary @review.zip
```

### 提交并计入 Bifrost

将下面的请求保存为 `render-request.json`。用上传得到的 SHA-256 替换 `input_sha256`，每次逻辑作业使用一个固定且唯一的 `render_idempotency_key`。提示词用于费用日志标签，动作和画面由 `render` 决定。

```json
{
  "model": "blender-review",
  "prompt": "PBZ 白绮动作验收",
  "render_idempotency_key": "把此处换成稳定的作业键",
  "render": {
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
}
```

下面的命令使用 Bash 和 `jq`。提交返回 HTTP 202，保存应答里的 Bifrost 异步 ID 和 `request_id`，分别用于查询与费用日志对账。

```bash
curl -fsS -X POST "$base/v1/async/images/generations" \
  -H 'Content-Type: application/json' --data-binary @render-request.json \
  -o render-submission.json
bifrost_id=$(jq -er '.id' render-submission.json)
```

重复查询同一个异步 ID，直到状态为 `completed` 或 `failed`。收到 202 后，直接查询已保存的 ID。同一个作业键约束底层渲染去重，重复 POST 仍可能产生另一个异步 ID。

```bash
curl -fsS "$base/v1/async/images/generations/$bifrost_id" -o render-status.json
jq -r '.status' render-status.json
```

### 下载和对账

完成时，`result.data[].url` 列出 PNG，URL 中的 `render_…` 是底层渲染 ID。Bifrost 的异步结果默认在完成后保留一小时。请保存渲染 ID，之后也可用它查询回执和下载完整 ZIP。

```bash
render_id=$(jq -er '.result.data[0].url | capture("/v1/render/jobs/(?<id>render_[0-9a-f]+)/images/").id' render-status.json)
curl -fsS "$base/v1/render/jobs/$render_id"
curl -fsS "$base/v1/render/jobs/$render_id/result" -o "$render_id.zip"
```

上面的配置计划交付 72 张 PNG。完整 ZIP 含每种形态的 `motion_report.json`、PNG、文件哈希清单和运行日志。作业状态 `completed` 表示文件交付成功；动作报告的 `pending_review` 或 `failed` 仍按 PBZ 的人工验收规则处理。费用页按模型 `blender-review` 查找该提交的 `request_id`。[PBZ 渲染提案与放行规则](https://github.com/XenoAmess/PBZ_vivhite_mod/blob/fb7e7cf/qa/MAINTENANCE.md#6000d-渲染节点-http-接口提案) · [Bifrost 费用日志](http://192.168.1.11:8080/workspace/logs)

### 渲染管理和直连兼容

`GET /v1/render/jobs/{render_id}` 返回进度、排队和运行耗时及 ZIP SHA-256，`DELETE /v1/render/jobs/{render_id}` 取消渲染。管理接口使用底层 `render_…` ID。Bifrost 提交应答使用自己的异步 ID，运行中可通过 `GET /v1/queue/jobs?model=blender-review` 查看渲染队列。

需要提交后立即取得渲染 ID 的旧客户端可继续用 `POST /v1/render/jobs`。请求体取上例的 `render` 对象，作业键通过 `Idempotency-Key` 请求头传递。同键同请求返回相同渲染作业，换了请求返回 409。**这条直连兼容路径只记录本机用量和估值。**

单个 ZIP 上限 2 GiB，解包上限 6 GiB，每任务最多 512 张图。分辨率每边 128 至 4096，样本 1 至 128。上传只允许相对路径数据文件，Blender 禁用自动执行，worker 在隔离 GPU 单元内运行。

## Blender 是否适合 Bifrost 计价

适合按交付图片记账。Bifrost 2.6 的 `image_generation` 支持每张图片价格、分辨率档位、像素价格和固定请求费 `cost_per_request`。固定费可以和用量价格叠加。异步图片入口等 Blender 生成真实 PNG 后回传图片列表。排队和轮询不增加输出张数。[Bifrost 自定义价格](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/docs/providers/custom-pricing.mdx) · [异步图片路由](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/transports/bifrost-http/handlers/asyncinference.go)

正式调用使用上面的[提交并计入 Bifrost](#提交并计入-bifrost)。同一渲染任务只允许一次成功返回给图像计价通道。

Bifrost 的自定义价格基于已支持的请求类型。按 GPU 占用时长、采样量或复杂度计费时，节点可按确认后的规则计算金额，在图片响应中回传 `usage.cost.total_cost`，Bifrost 会使用该金额。当前 `run_seconds` 是渲染流程墙钟时间，包含本地处理，排队时间另记。若需按 GPU 独占时段结算，需要定义并记录相应计时区间。[图片用量结构](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/core/schemas/images.go) · [Bifrost 费用计算](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/framework/modelcatalog/datasheet/cost.go#L568)

同一 Bifrost 二进制在隔离实验中，请求 `n=1`、实际返回 72 张图，测试单价 0.01 USD／张时只记一次 0.72 USD。另一笔由上游报告 0.123 USD，日志采用 0.123 USD。重复轮询未增加费用。

## 当前费率

2026-11-25 已在 8080 启用下表费率，币种为 USD。公开平台只用于比价；Bifrost 记录的是本机用量的折算价值，所有推理和渲染仍在本机执行。

| 服务 | Bifrost 单价 | 对标 |
| --- | --- | --- |
| `qwen38-coder` | 每百万 token，输入 $0.1275、缓存命中输入 $0.032、输出 $0.3995 | 本机采用 ISTA 剪枝量化版，采用其原版 Qwen3.8 Flash Next 的公开按请求价格。[Anex API 价格表](https://anex.sh/docs/pricing) |
| `fasth3-omni-bf16` | 每秒成片 $0.025 | Reactor 实时定价接口的 FastH3 Omni 会话秒单价。本机按交付时长计量，适用于所有 Omni 画幅。[Reactor 实时价格](https://api.reactor.inc/pricing) · [Reactor 模型与规格](https://www.reactor.inc/models/fast-h3-omni/info) |
| `open-h3-2k`，2560×1440 | 每秒成片 $0.10 | MiniMax 官方 H3 2K 重生成，源片 $0.05／秒、输出 $0.05／秒。本机保留时长，合并为一个输出秒费率。[MiniMax 价格](https://platform.minimax.io/subscribe/token-plan?tab=api-enterprise) |
| `open-h3-2k`，3840×2160 | 每秒成片 $0.288 | Runway 的 4K 创意视频放大 $0.012／输出帧，按本机 24 FPS 换算。[Runway 4K 放大价格](https://docs.dev.runwayml.com/guides/pricing/#video-upscale-pricing) |
| `blender-review` | 每渲染小时 $3，按实际秒数比例计算 | blender.farm 的 EEVEE 标准小包价格，平台使用 RTX 5090。本机按渲染进程时间线性计量。[Blender EEVEE 渲染农场价格](https://www.blender.farm/pricing) |

Qwen 的客户端别名和原模型名使用同一费率。缓存折扣按实际报告的缓存命中 token 计算。本机视频终态按 API 报告的整数秒与实际尺寸记账，排队、失败、输入素材和重复查询不另计。Blender 以 worker 启动 Blender 前至生成验收图结束的墙钟时间计量，包含场景加载，排队、上传、下载与 ZIP 打包不计费。通过 Bifrost 完成的任务写入费用日志，直接提交的 Blender 任务在 `/v1/usage` 显示估值。

取价时 Reactor 的模型介绍还显示较早的 $0.0125／会话秒，实时价格接口返回 $0.025／会话秒，采用后者。本机 Blender 现场验收 8.168 秒、2 张 PNG，Bifrost 日志为 $0.00680667。与线上相同版本 Bifrost 的隔离测试使用生产费率和模拟作业，5 秒 Omni 为 $0.125，14 秒 IC 2K／4K 为 $1.40／$4.032，失败视频为 $0。

视频提交记录的 `cost_status=settles_on_completion` 表示费用按成片结算。任务运行时提交记录没有最终金额。生成结束后，费用页以独立结算记录保存金额，和原提交关联。开启「分组」后，可在提交行查看其结算总额。历史进度查询显示零费用。[Bifrost 分组费用日志](http://192.168.1.11:8080/workspace/logs?period=this_month&grouped=true&limit=100)

费率可用 [配置清单](../deployment/bifrost/market-pricing.json) 恢复。通过 Bifrost 的 `/api/governance/pricing-overrides` 新增或更新前四条（两条 Qwen 别名、两条视频规则），并同步部署配置 `governance.pricing_overrides`。Blender 在新作业完成时保存计算单据，供 Bifrost 读取。历史已结算的金额保留，缺金额的终态按原始使用量补录。

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

Qwen worker 由调度器按需启动，监听 loopback 8005。网关内部 8006 是 CPU 适配层。8080 的 Bifrost 运行由 PR #10467 的 `cf2fb48` 构建的网关和费用页。本机内置 `openai` provider 地址为 `http://127.0.0.1:8006`，启用 `openai_config.video_generation_json`，并将三个媒体模型加入允许列表。provider 超时为 18 小时，自动重试为 0。[本次 Bifrost 上线验收](../deployment/bifrost/pr10467-verification-2026-11-26.json) · [统一系统技术验收](../deployment/video-queue/unified-model-verification-20261125.json)

停止前，通过 `POST /v1/service/maintenance` 提交 `{"enabled":true,"reason":"planned shutdown"}` 停接新任务。等 `GET /v1/service/status` 的 `running_jobs` 清空后，再停止：

```bash
systemctl --user stop video-gpu-scheduler.service
systemctl --user stop fasth3-omni-bf16.service h3-2k-refiner-http.service
systemctl --user stop bifrost-edge.service bifrost-lan.service unified-model-http.service
```

重新启动后用同一维护接口发送 `{"enabled":false}` 恢复接单。通过 `GET /v1/service/status` 确认已恢复；OOM 人工熔断由 `POST /v1/queue/resume` 单独处理。上次运行的二进制、配置、SQLite 和 Caddy 文件保存在本机 `outputs/unified-model-activation-20261125/before/`。全部服务按需启动，无开机自启。[Bifrost 参数适配历史](bifrost-local-video-json-2026-11-25.md)
