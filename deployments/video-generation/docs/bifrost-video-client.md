# 对端视频 API 接入与 Bifrost 对账

需要在 Bifrost 看到费用的客户端，统一在 `http://192.168.1.11:8080` 上传、提交、查询和下载。推理接口无需 API Key。已有程序只需把视频服务地址改成 `http://192.168.1.11:8080`，保存提交响应中的完整 `id`，并延用原有字段。直连 8001 或 8002、使用 7860 网页提交的任务可在共享队列查询，提交不经过 Bifrost 计量。

| 操作 | 方法与路径 | 模型 |
| --- | --- | --- |
| 上传本地文件 | `POST /v1/files`，multipart 字段 `file` | 两个模型共用上传 |
| 参考素材生成 | `POST /v1/videos`，JSON | `fasth3-omni-bf16` |
| 2K／4K 重生成 | `POST /v1/videos/regenerations`，JSON | `open-h3-2k` |
| 查询状态 | `GET /v1/videos/{id}` | 返回实际成片状态与规格 |
| 下载 MP4 | `GET /v1/videos/{id}/content` | 使用同一个完整 ID |

## 提交请求

以下示例需要 Bash、curl 和 jq。客户端本地素材先上传，返回的 `file_id` 可以复用。

```bash
video_base=http://192.168.1.11:8080
lan() { curl --noproxy 192.168.1.11 -fsS "$@"; }

image_id=$(lan -F 'file=@character.png' "$video_base/v1/files" | jq -er .id)
motion_id=$(lan -F 'file=@motion.mp4' "$video_base/v1/files" | jq -er .id)

jq -n --arg image "$image_id" --arg video "$motion_id" '{
  model: "fasth3-omni-bf16",
  task: "ref2va",
  prompt: "使用 <Picture 1> 的人物外观，参考 <Video 1> 的动作与镜头。",
  image_reference: [{file_id: $image}],
  video_reference: [{file_id: $video}],
  size: "1344x768",
  seconds: 5,
  num_inference_steps: 8,
  seed: 1234
}' | lan -H 'Content-Type: application/json' --data-binary @- \
  "$video_base/v1/videos" > omni-task.json

omni_id=$(jq -er .id omni-task.json)
echo "$omni_id"
```

用同一个 Omni ID 提交 4K，可以在草稿尚未完成时提交。队列会等源片就绪。输出 2K 时将 `size` 改为 `2560x1440`。直接重生成已有 MP4 时先上传，再将 `input_video` 改为 `{"file_id":"file_…"}`。

```bash
jq -n --arg draft "$omni_id" '{
  model: "open-h3-2k",
  input_video: {job_id: $draft},
  size: "3840x2160",
  sampler: "up3",
  seed: 1234
}' | lan -H 'Content-Type: application/json' --data-binary @- \
  "$video_base/v1/videos/regenerations" > ic-task.json

ic_id=$(jq -er .id ic-task.json)
echo "$ic_id"
```

成功提交以 2xx 和 JSON `id` 为准。统一网关可返回 HTTP 200，内部视频后端使用 202。生产入口生成的 ID 形如 `video_gen_…:openai`。对端应保存完整 ID、模型、请求提交时间和本地业务编号。遇到提交超时，先查共享队列确认是否已经接收，再决定是否重试，以免生成和结算两份作业。

## 查询与下载

```bash
video_id="$omni_id"   # 重生成时换成 "$ic_id"
lan "$video_base/v1/videos/$video_id" | jq '{id, model, status, size, seconds, error}'
# 状态为 completed 后执行
lan "$video_base/v1/videos/$video_id/content" -o result.mp4
```

- `queued` 或 `in_progress` 时可每 30–60 秒查一次。客户端退出后，可用已保存的 ID 继续查询。
- `completed` 时下载。响应中的 `seconds` 与 `size` 是核对费用的口径。公共视频查询会把已取消作业显示为 `failed`，错误码为 `cancelled`。
- `failed` 时保留任务 ID 和错误。提交 503 按 `Retry-After` 退避；查询、下载和管理在维护期间继续可用。需要查看节点是否接单时查询 `GET /v1/service/status`。

已使用仓库 Python 客户端的对端，在现有命令中加 `--api http://192.168.1.11:8080`。这个参数填写主机和端口，脚本会拼接 `/v1`。[客户端源码](../tools/video_http_client.py)

## 在费用页确认结算

在 [Bifrost 日志](http://192.168.1.11:8080/workspace/logs) 按模型筛选，打开「分组」，展开目标视频的提交记录。在结算详情里核对完整视频 ID、计费秒数、分辨率和费用。关闭分组后，独立结算行的类型显示为「获取视频」，详情带视频结算用量。

| 看到的记录 | 含义 |
| --- | --- |
| 「视频生成」提交行费用为空或 N/A | 已受理，最终金额在独立的终态结算行 |
| 正在排队或渲染 | 等成片，发送查询不会增加费用 |
| 终态结算行有金额 | 每个成功视频 ID 记一次。Omni 5 个计费秒为 `$0.125` |
| 终态结算行是 `$0` | 失败或取消，无成片费 |

本机每分钟从共享队列批量读取未结算作业。正常排队和渲染会一直跟踪，进入终态后才交给 Bifrost 结算。无异常时，成片通常在 1–2 分钟内入账。客户端可以在后台继续轮询，也可以等需要下载时再查。若成片完成后分组中仍无结算行，请提供完整视频 ID、模型、提交时间及所用 URL。保留原作业供节点查账。

首次修复已补录因旧版轮询次数耗尽而遗漏的作业。切换到批量跟踪后，已有在途任务按原 ID 继续运行和结算。节点运维和价格见[统一模型服务](unified-model-service.md)。
