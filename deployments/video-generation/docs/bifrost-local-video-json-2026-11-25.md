# Bifrost 2.6.0 升级与本地视频参数转发

2026-11-26，局域网 8080 已切换到 PR #10467 rebase 后的 `cf2fb48`。仪表盘可读历史费用，原有任务跨网关重启继续运行。前一次切换期间在跑的 Omni 作业正常完成，后台只写入一条终态结算。现行调用见[统一模型服务](unified-model-service.md)。[本次上线验收](../deployment/bifrost/pr10467-verification-2026-11-26.json)

2026-11-25，局域网 8080 的 Bifrost 已从 2.3.2 升级到官方 HTTP 2.6.0。8080 和内部 8081 的健康检查通过，8080 仪表盘可打开，升级前的费用日志仍可读取，两条既有计价规则保留。旧二进制、systemd 单元、配置与 SQLite 数据已在本机留存备份。切换耗时约 7 秒。网关维持 16 GiB 硬上限、14 GiB `MemoryHigh` 和 12 GiB Go 内存目标，开机自启仍关闭。[官方 HTTP 2.6.0](https://github.com/maximhq/bifrost/releases/tag/transports/v2.6.0)

11 月 25 日首次升级使用官方 Linux amd64 二进制，SHA-256 为 `bf2da45a4246605af199a21ba313992864835b16872cc62efbad4e62fe8645b3`，与官方 `.sha256` 一致。当时正式视频接口仍在 8001 和 8002，Qwen 的历史 8002 路由冲突见[统一网关预研](unified-model-gateway-queue-feasibility-2026-11-25.md)。

## 官方 2.6.0 可用的转发方式

`image_reference`、`input_video` 和 `sampler` 是本地视频 API 的字段。官方 2.6.0 的普通 `/v1/videos` 仍使用 OpenAI 视频 multipart 适配器。把字段放在顶层，或放在 `extra_params` 并设 `x-bf-passthrough-extra-params: true`，都不能让这三个字段通过。`input_reference` 可传单图，不能代替 Omni 的多素材列表。[官方 2.6.0 视频适配源码](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/core/providers/openai/videos.go)

官方版可以用原始透传。先为本地视频后端创建 OpenAI 类型的自定义 provider，在 `passthrough.allowed_routes` 开放所需的提交、查询和下载路径。调用时用 `x-model-provider` 选择 provider，JSON 的 `model` 填后端自身接受的名称，参考素材和采样字段都保留在顶层。[透传接口](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/docs/integrations/passthrough.mdx)

例如，将已经配置好的 IC provider 命名为 `local-ic` 后，可以这样提交。`file_id` 来自 IC 服务的文件上传，也可以用同一队列中的 `job_id` 指定草稿。

```bash
curl -X POST 'http://192.168.1.11:8080/openai_passthrough/v1/videos/regenerations' \
  -H 'Content-Type: application/json' \
  -H 'x-model-provider: local-ic' \
  -d '{
    "model": "open-h3-2k",
    "input_video": {"file_id": "file_已上传的源片"},
    "size": "3840x2160",
    "sampler": "up3"
  }'
```

Omni 使用 `/openai_passthrough/v1/videos` 和指向 Omni 的 provider，JSON 保留 `image_reference`、`video_reference` 和现有请求格式。Bifrost 2.6.0 的本地模拟测试已验证 `x-model-provider` 自定义路由、HTTP 202、未带提示词的源片请求、原样 4K 尺寸和参考字段。上述 provider 名称供部署时配置，尚未在生产 8080 开通。

原始透传的费用日志按提交请求计价。本地模拟任务仍为 `queued` 时就出现虚拟费用，完成后的轮询只有普通透传日志。要求等成片确认实际时长和分辨率再结算时，使用下面的候选方案。[原始透传用量提取](https://github.com/maximhq/bifrost/blob/172617bb045c6f43d697843c115e64f0155ed143/core/providers/openai/passthrough_usage.go)

## 原生视频结算的修复

修复代码由 `XenoAmess/bifrost:openai-json-video-generation` 提交至 `maximhq/bifrost:dev`。首轮验证使用 `b8eedb4`。11 月 26 日 rebase 至上游 `4469d747`，合入审计修改后的版本为 `cf2fb48`。[上游 PR #10467](https://github.com/maximhq/bifrost/pull/10467) · [问题 #10466](https://github.com/maximhq/bifrost/issues/10466)

修复版为 OpenAI 兼容后端增加显式配置 `openai_config.video_generation_json: true`。配置了该选项的 provider 通过 JSON 送出标准视频字段，保留实际尺寸，并接受后端返回的 202 任务。`request_path_overrides.video_generation` 可把 IC 的提交发到 `/v1/videos/regenerations`。对外调用方法如下。

| 入口 | 扩展字段放法 |
| --- | --- |
| `POST /v1/videos` | 请求头 `x-bf-passthrough-extra-params: true`，扩展字段放在顶层，可用 `local-ic/open-h3-2k` 指定路由和模型 |
| `POST /openai/v1/videos` | 同一请求头，扩展字段放在 `extra_params` 对象里 |

没有提示词的源片型任务通过 `/v1/videos` 提交，提供 `video_uri` 表明输入来源，同时继续传本地后端使用的 `input_video`。扩展参数无法覆盖 Bifrost 已解析的模型、尺寸和其他已知字段。

隔离验证覆盖普通入口、OpenAI 兼容入口、失败任务和不带提示词的源片任务。四种场景都保留了参考列表、草稿任务 ID、采样预设、seed 和 4K 尺寸。成功任务按终态尺寸结算，失败记零，三次重复轮询仍每任务只生成一条结算记录。费用为测试数据。测试使用本地模拟后端，没有运行真实视频生成。

旧 multipart 的提供方回归通过。请求体序列化独立短测的默认模式保持每次 72 次分配，耗时中位约 2.54 → 2.52 微秒。显式 JSON 路径约 1.87 微秒、50 次分配。短测只量序列化，不能用于估计渲染速度。

命名自定义 provider（例如 `local-ic`）应在 Bifrost 上用返回的完整 ID 轮询 `GET /v1/videos/{id}`，直到任务返回终态。Bifrost 在读到终态时结算。后台结算覆盖包括 `openai` 在内的受支持内置 provider，本机 8080 使用内置 `openai`。11 月 26 日的隔离 HTTP 对照验证了两种结算行为及重复轮询的去重。[PR 审计讨论](https://github.com/maximhq/bifrost/pull/10467#discussion_r4694013181)

仪表盘保存 OpenAI 的 `disable_store` 时会同时保留现有 `video_generation_json`。新增回归测试覆盖这一操作，两条视频用例可以用 `--feature 10466` 选中。[设置保存审计](https://github.com/maximhq/bifrost/pull/10467#discussion_r4703262459) · [用例命名审计](https://github.com/maximhq/bifrost/pull/10467#discussion_r4703278668)
