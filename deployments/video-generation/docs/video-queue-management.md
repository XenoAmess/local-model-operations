# 视频 HTTP：队列管理、插队与升级状态

[当前 S48 每十分钟巡检](video-progress-monitor.md)：检查进度、worker、错误日志与资源；异常通知同一会话，正常采样只记录，不暂停在途视频。

2026-11-20，API 3.0。BF16 Omni 为 `192.168.1.11:8001`／`fasth3-omni-bf16`，重生成为 2K／4K 为 `192.168.1.11:8002`／`open-h3-2k`。两个端口共享同一持久队列；下列 `/v1/queue/*` 管理操作可以从任一端口管理两个模型。接口无 API Key，与原 LAN 服务一致。

独立状态入口是 **`http://192.168.1.11:8004/v1/service/status`**。它由单独的 CPU 服务提供，主 API 更新／重启期间仍可访问，不加载 GPU 模型。S48 已完成完整 14 秒 4K，局域网下载、SHA、帧数和全片解码通过，抽帧未见明显场景跳变；对端审核待反馈，见[成片与短测结果](h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)和[验收记录](../deployment/video-queue/full-sequence-validation.json)。

## 接口一览

| 方法和路径 | 功能 |
| --- | --- |
| `GET /v1/queue` | 全局运行任务、预计派发顺序、依赖等待、维护及 OOM 状态 |
| `GET /v1/queue/jobs` | 两个模型全部任务，支持状态／模型筛选和分页 |
| `GET /v1/queue/jobs/{id}` | 跨模型查询一个任务 |
| `POST /v1/queue/jobs/{id}/promote` | 将一个尚未开始的任务插到当前可执行队列最前 |
| `PATCH /v1/queue/jobs/{id}/priority` | 调整一个排队任务的优先级 |
| `POST /v1/queue/jobs/{id}/cancel` | 取消一个任务；终态任务保持原状态 |
| `GET /v1/videos` | 保留原模型端口的任务列表，新增分页与状态筛选 |
| `DELETE /v1/videos/{id}` | 保留原取消入口，仅管理该模型端口的任务 |
| `GET /v1/service/status` | 可用、忙碌、排空、升级或降级／不可用；两个主 API 和 8004 均提供 |
| `GET /ready` | 准备好时 200，否则 503 与 `Retry-After: 30`；三个端口均提供 |
| `POST /v1/service/maintenance` | 启用／退出维护，两个主 API 提供 |
| `POST /v1/queue/resume` | 原有 OOM 管理恢复，独立于维护开关 |

## 插队与优先级

在客户端 Bash 中替换真实任务 ID：

```bash
VIDEO_JOB_ID=video_gen_实际任务ID
curl --noproxy '*' --fail-with-body -sS -X POST \
  "http://192.168.1.11:8002/v1/queue/jobs/$VIDEO_JOB_ID/promote" \
  -H 'Content-Type: application/json' -d '{"reason":"优先输出供审核"}'

curl --noproxy '*' --fail-with-body -sS -X PATCH \
  "http://192.168.1.11:8002/v1/queue/jobs/$VIDEO_JOB_ID/priority" \
  -H 'Content-Type: application/json' -d '{"priority":100,"reason":"提高优先级"}'
```

`priority` 是 **-1000～1000 的整数**，默认 0，越大越先执行。提交 Omni 或重生成任务时也可以附加 `"priority":100`，它仅参与调度，不传给推理模型。

顺序是：优先级降序 → 插队序号降序 → 同组内按模型亲和及等待公平性选择。`promote` 设置优先级 1000，并赋予最新插队序号，所以后一次明确插队排在前一次之前。普通 `PATCH priority` 清除该任务插队序号。同一优先级／插队组内保留原来的同模型分组、3 个连续任务及另一模型等待 30 分钟的切换规则；显式更高优先级可以越过该组，故连续高优先级任务可能延迟普通任务。

**插队不打断正在运行的任务或已派发小批次。** 依赖尚未完成的任务仍等待依赖，不能跳过草稿生成。返回 `queue_position` 是当前可执行队列中的预计位置；任务列表分页顺序不是派发顺序。对运行中或终态任务插队／调优先级返回 409；未知任务返回 404。队列变更与派发使用事务和版本校验，防止插队成功后仍以过期选择派发其他任务。

## 取消与分页浏览

```bash
curl --noproxy '*' --fail-with-body -sS -X POST \
  "http://192.168.1.11:8002/v1/queue/jobs/$VIDEO_JOB_ID/cancel" \
  -H 'Content-Type: application/json' -d '{"reason":"不再需要"}'

curl --noproxy '*' --fail-with-body -sS \
  'http://192.168.1.11:8002/v1/queue/jobs?model=open-h3-2k&status=queued&status=in_progress&limit=20'
```

排队任务取消返回 200，立即退出可执行队列。运行中任务返回 202、`status: "cancelled"`、`worker_stop_pending: true`，调度器随后停止 worker；202 不表示显存已经释放。重复取消是幂等的。已经完成／失败的任务维持 completed／failed，不删除媒体，也不恢复失败任务。

取消 2K 小批次中的一个任务会停止批次，其他未完成成员保留有效检查点后重新排队。4K 一次只派发一个任务。客户端断开连接或停止轮询本身不会取消生成。

列表参数：`model` 可省略；`status` 可重复；`limit` 为 1～100，默认 20。按创建时间和 ID 倒序分页，响应中的 `has_more` 真实反映是否有下一页。将 `next_after` 放入下一次的 `after` 参数，其余筛选条件保持一致：

```bash
curl --noproxy '*' --fail-with-body -sS \
  'http://192.168.1.11:8002/v1/queue/jobs?model=open-h3-2k&status=queued&limit=20&after=video_gen_上一页的next_after'
```

任务包含 `priority`、`front_order`、`queue_position`；重生成任务还显示上传时的 `input_filename`。依赖等待或已运行／结束的任务，列表中的预计排队位置为 null。查看实际下一任务请用 `/v1/queue` 的 `queued` 数组。Omni 和 IC 各最多 1024 个 `queued`／`in_progress` 任务，含依赖等待，满时返回 429。2K／4K 共用 IC 额度。

本机隔离测试用 2048 个模拟任务，每条请求约 32 KiB。队列概览的 CPU 时间中位数由约 469 ms 降至 12 ms，独立测试进程峰值 RSS 由约 163 MiB 降至 27 MiB，返回的任务顺序和状态一致。概览不读取素材或任务文件。分页接口最多展开请求的 100 条记录。

## 对端如何判断能否提交

推荐先请求独立 8004 状态：

```bash
curl --noproxy '*' -sS http://192.168.1.11:8004/v1/service/status
```

| `status` | 含义 |
| --- | --- |
| `available` | 调度器在线、空闲，可以提交 |
| `busy` | 调度器正在处理任务，可以入队；不是临时不可用 |
| `draining` | 正在完成维护前已运行任务，新生成提交被拒绝 |
| `upgrading` | 维护已生效，暂不派发，新生成提交被拒绝 |
| `degraded` | 如 OOM 恢复／熔断，或 8004 检查发现主 API 未就绪 |
| `unavailable` | 调度器离线或队列数据库不可读 |

响应还包含 `ready`、`accepting_jobs`、`scheduler_online`、`scheduler_phase`、`running_jobs`、`queue_counts`、`queue_paused`、`maintenance.reason`、`retry_after_seconds`。8004 额外探测两个主 API 的 HTTP 健康，返回 `endpoints`。主 API 的同名状态入口主要反映共享数据库与调度器；需要同时确认两个 HTTP 入口时用 8004。

`ready: true` 表示当前调度服务就绪，仍可能需要排队。`accepting_jobs: true` 表示允许新任务入队；OOM 恢复时可能允许入队但 `ready: false`，客户端可以选择等待恢复。维护或调度器离线时，新生成请求返回 **503 和 `Retry-After: 30`**，此时稍后重试；503 不会创建任务。上传、查询、下载、取消和管理操作在 API 进程在线时继续可用。8004 无法连接时，应按状态服务不可达处理，不能推断模型空闲。

原 `/health` 保持进程存活检查的兼容行为，HTTP 200 不代表 GPU 就绪；查看其新增 `service` 对象，或者使用 `/ready`。状态响应不应缓存。生成提交返回 202 后应保存任务 ID，通过该 ID 轮询，不要因为排队而重复提交。

## 安全进入／退出维护

```bash
# 完成当前已派发任务后暂停；不取消它，也不重派已有任务。
curl --noproxy '*' --fail-with-body -sS -X POST \
  http://192.168.1.11:8002/v1/service/maintenance \
  -H 'Content-Type: application/json' -d '{"enabled":true,"reason":"更新推理服务"}'

# 等 /v1/service/status 从 draining 变为 upgrading，核对成片已交付后进行更新。
# 更新并检查后解除维护。不会顺便解除 OOM 熔断，也不会重试失败任务。
curl --noproxy '*' --fail-with-body -sS -X POST \
  http://192.168.1.11:8002/v1/service/maintenance \
  -H 'Content-Type: application/json' -d '{"enabled":false,"reason":"升级与检查完成"}'
```

启用维护返回 202，表示已接受排空；退出返回 200。调度器不在线时，退出维护后仍是 unavailable，须先启动调度器。OOM 恢复仍按原来的 `/v1/queue/resume` 及资源／冷却规则执行。

状态监测服务为 `video-service-status.service`，按需手动启动，无开机自启；主 API 重启时不需要停止它。服务端会记录完整 `/content` 响应发送完成事件、字节数及来源，用于核对交付；这不代表已经核对接收端文件 SHA-256，也不等于人眼审核通过。

## 4K 新旧路线严格边界

按输入归一化到 24 FPS 后的帧数，使用原机制单窗口上限 **124 帧（约 5.166667 秒）**：

| UHD 4K 输出输入帧数 | 路线 |
| --- | --- |
| 小于等于 124 帧，包括 120、121、123、124 | 原来的单窗口 IC 路线 |
| 严格大于 124 帧，如 125、336、362 | 整段时间轴 IC，完整上下文密集注意力，原版 36L FP32 流式解码 |

**不以“超过 5 秒”作判断。** 5 秒／120 帧与原上限不同；124 帧仍走旧路线。这个分流适用于 `size: "3840x2160"`，现有 2K 输出路线保持原配置。输入范围继续是约 4.7～15.1 秒。14 秒／336 帧处理时只在末尾补到 345 帧／102 个 latent 帧，结束后裁回 336 帧，原音轨按完整源片保留。

调用字段、模型名和端口不变，无需额外开启整段参数。超过上限的 4K 失败时保持失败，**禁止静默回落到独立窗口拼接**。整段仍保留 up3 三步或请求指定的采样器，性能可能明显降低；完整 GPU 成片验收与接口／容量测试分别记录。[4K 接口与当前验收](open-h3-4k-http.md)、[整段路线源码与研究](open-h3-seam-solutions-2026-11-20.md)
