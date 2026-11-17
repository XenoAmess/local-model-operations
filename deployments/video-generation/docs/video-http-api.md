# 从其他机器调用 BF16 Omni 与 2K 视频接口

服务器局域网地址：`192.168.1.11`。本机与客户端须能互通。当前接口不需要 API Key。

| 服务 | API 根地址 | `model` 的准确名称 |
| --- | --- | --- |
| 图片＋文字＋视频参考生成 | `http://192.168.1.11:8001/v1` | `fasth3-omni-bf16` |
| 已有视频重生成为 2K／4K | `http://192.168.1.11:8002/v1` | `open-h3-2k` |

网页为 `http://192.168.1.11:7860`。接口文档分别为 `http://192.168.1.11:8001/docs`、`http://192.168.1.11:8002/docs`。不要把旧量化模型名称 `fasth3-omni` 填入 BF16 请求；实际名称也可用 `GET /v1/models` 核对。

**两个服务同时接单、共用一张显卡。HTTP 上线表示可以提交任务；如果 GPU 正在处理其他任务，新请求仍须排队。** 提交返回 HTTP 202 和任务 ID，客户端随后查询状态、完成后下载，不要让一个同步 HTTP 连接一直等整段推理。

4K 继续使用 `open-h3-2k`，仅需指定 `size: "3840x2160"`；[4K 调用与验收状态](open-h3-4k-http.md)。

## 最快调用：Python 客户端

客户端源码为 [tools/video_http_client.py](../tools/video_http_client.py)，只依赖 Python 3 与 `requests`，可在 Linux、macOS、Windows 上运行。将脚本复制到调用机器，安装依赖：

[文档＋Python 客户端 ZIP 局域网下载](http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/video-http-client-20261116.zip)。解压后手册位于 `docs/video-http-api.md`，客户端位于 `tools/video_http_client.py`。

```bash
python3 -m pip install requests
```

Linux/macOS 可通过 SSH 复制脚本：

```bash
scp ubuntu@192.168.1.11:/home/ubuntu/workspace/xenoamess_bake_videos/tools/video_http_client.py .
```

提交图片＋视频参考任务：

```bash
python3 video_http_client.py omni \
  --image ./character.png \
  --video ./motion.mp4 \
  --prompt '保持 <Picture 1> 的人物外观，参考 <Video 1> 的动作和镜头。' \
  --size 1344x768 --seconds 5 --seed 1234
```

立即返回包含 `id` 的 JSON。脚本会自动上传客户端本地文件；只传图片或只传视频也可以。重复 `--image`／`--video` 可上传多份参考，独立音频用 `--audio`。

直接等待并下载草稿，在上述命令后增加：

```bash
--wait --output ./draft.mp4
```

将草稿交给 2K；草稿仍在排队时也能提交，替换实际任务 ID：

```bash
python3 video_http_client.py 2k \
  --source-job video_gen_替换为草稿任务ID \
  --prompt '保留人物、动作、镜头与场景，补充清晰细节。' \
  --wait --output ./final-2k.mp4
```

已有视频直接做 2K：

```bash
python3 video_http_client.py 2k --video ./existing.mp4 \
  --prompt '保留人物与运动，恢复清晰细节。' \
  --wait --output ./final-2k.mp4
```

`--wait` 会持续轮询，包含排队时间；关闭客户端不会取消服务器任务。默认提交后立即返回，适合批量接入。服务器 IP 变化时用 `--api http://新IP:8001` 或 `--api http://新IP:8002` 覆盖地址。Windows 可把 `python3` 换成 `python`，并将命令写成一行。

## 直接 HTTP：上传、提交、查询、下载

下列示例使用 Bash、curl 和 jq；在**客户端机器**执行。素材路径是客户端本地文件，通过上传转成 `file_id`。把另一台机器上的磁盘路径直接填入 `image_url` 或 `video_url`，服务器无法读取。

### 1. 上传参考图片和视频

```bash
curl --noproxy '*' --fail-with-body -sS \
  -F 'file=@./character.png' \
  http://192.168.1.11:8001/v1/files -o image-upload.json

curl --noproxy '*' --fail-with-body -sS \
  -F 'file=@./motion.mp4' \
  http://192.168.1.11:8001/v1/files -o video-upload.json

OMNI_IMAGE_ID=$(jq -er '.id' image-upload.json)
OMNI_VIDEO_ID=$(jq -er '.id' video-upload.json)
```

返回示例：`{"id":"file_...","object":"file","filename":"character.png","bytes":12345}`。单个文件上限 512 MiB。两个端口共享上传记录，同一个 `file_id` 可以在相应类型的请求中复用。

### 2. 提交 BF16 Omni

```bash
jq -n --arg image "$OMNI_IMAGE_ID" --arg video "$OMNI_VIDEO_ID" '{
  model: "fasth3-omni-bf16",
  task: "ref2va",
  prompt: "保持 <Picture 1> 的人物外观，参考 <Video 1> 的动作和镜头。",
  image_reference: [{file_id: $image}],
  video_reference: [{file_id: $video}],
  size: "1344x768",
  seconds: 5,
  num_inference_steps: 8,
  seed: 1234
}' > omni-request.json

curl --noproxy '*' --fail-with-body -sS \
  http://192.168.1.11:8001/v1/videos \
  -H 'Content-Type: application/json' --data-binary @omni-request.json \
  -o omni-task.json

OMNI_JOB_ID=$(jq -er '.id' omni-task.json)
```

返回任务形如 `{"id":"video_gen_...","model":"fasth3-omni-bf16","status":"queued",...}`。图片用 `<Picture 1>`、视频用 `<Video 1>`、独立音频用 `<Audio 1>` 引用，序号从各自类型的 1 开始。`audio_reference` 格式同样为 `[{"file_id":"file_..."}]`。

### 3. 提前提交依赖该草稿的 2K 任务

```bash
jq -n --arg draft "$OMNI_JOB_ID" '{
  model: "open-h3-2k",
  input_video: {job_id: $draft},
  prompt: "保留人物、动作、镜头与场景，补充清晰细节。",
  size: "2560x1440",
  sampler: "up3",
  seed: 1234
}' > refine-request.json

curl --noproxy '*' --fail-with-body -sS \
  http://192.168.1.11:8002/v1/videos/regenerations \
  -H 'Content-Type: application/json' --data-binary @refine-request.json \
  -o refine-task.json

REFINE_JOB_ID=$(jq -er '.id' refine-task.json)
```

2K 任务会等待草稿成功；若草稿失败或取消，它会标记失败，不会处理缺失输入。

已有视频直接重生成时，先用 `POST http://192.168.1.11:8002/v1/files` 上传视频，再将 `input_video` 改为 `{"file_id":"file_实际视频上传ID"}`；其余字段及提交地址相同。2K 不需要重新上传参考图片，沿用输入视频的时长与音轨，可附加文字。

### 4. 查询任务和全局队列

```bash
curl --noproxy '*' --fail-with-body -sS \
  "http://192.168.1.11:8001/v1/videos/$OMNI_JOB_ID" | jq

curl --noproxy '*' --fail-with-body -sS \
  "http://192.168.1.11:8002/v1/videos/$REFINE_JOB_ID" | jq

curl --noproxy '*' --fail-with-body -sS \
  http://192.168.1.11:8001/v1/queue | jq
```

建议每 5～10 秒查询一次任务。状态含义：

| `status` | 含义 |
| --- | --- |
| `queued` | 等待 GPU，或等待源草稿完成 |
| `in_progress` | 已派发到模型或小批次，正在处理 |
| `completed` | 成片已保存，可以下载 |
| `failed` | 处理失败，查看 `error.message` 和日志 |
| `cancelled` | 已取消，不会自动重试 |

`progress` 是阶段进度，可能较长时间不变。全局队列中的 `running`、`queued`、`waiting_for_source` 分别表示已派发、重排序后的就绪队列和等待草稿的任务。同批两条 2K 均可显示 `in_progress`，GPU 内部仍逐片段计算。

HTTP 健康检查是 `/health`；`scheduler_online` 表示 GPU 调度器心跳是否有效，`queue_paused` 表示是否暂停派发。仅有 `status: ok` 代表 HTTP 前端在线。

### 5. 下载成片

确认相应任务 `status` 为 `completed` 后执行：

```bash
curl --noproxy '*' --fail-with-body \
  "http://192.168.1.11:8001/v1/videos/$OMNI_JOB_ID/content" -o draft.mp4

curl --noproxy '*' --fail-with-body \
  "http://192.168.1.11:8002/v1/videos/$REFINE_JOB_ID/content" -o final-2k.mp4
```

完成后的任务 JSON 在 `result.sha256` 给出文件校验值。任务 ID、上传文件和结果落盘；重启 HTTP 前端不会让正在推理的任务重新排队。

### 6. 取消或查看日志

```bash
curl --noproxy '*' --fail-with-body -X DELETE \
  "http://192.168.1.11:8001/v1/videos/$OMNI_JOB_ID"

curl --noproxy '*' --fail-with-body \
  "http://192.168.1.11:8002/v1/videos/$REFINE_JOB_ID/logs"
```

查询、取消、下载均使用该任务所属模型的端口。取消执行中的 2K 小批次成员会停止该批次；未取消的其他任务保留已验证窗口并重新排队。

## 参数、排队与性能边界

| 项目 | BF16 Omni | 本地 2K |
| --- | --- | --- |
| 提交入口 | `POST /v1/videos` | `POST /v1/videos/regenerations` |
| 输入 | 必需文字；图片／视频至少一种；可选音频 | 输入视频或 Omni 草稿任务 ID；文字可选 |
| 数量 | 最多 9 图片、3 视频、3 音频，合计最多 12 | 一个输入视频 |
| 默认尺寸 | 1344×768 | 2560×1440 |
| 其他尺寸 | 768×1344、832×480、768×768 | 1440×2560、3840×2160（4K） |
| 时长 | `seconds` 为整数 5–15，默认 5；24 FPS，帧数自动对齐 | 继承输入视频，约 4.7–15.1 秒；24 FPS |
| 采样 | 固定 `num_inference_steps: 8` | `sampler: up3`，也支持 `up4`、`hf8` |
| 随机种子 | `seed`，默认 1234 | `seed`，默认 1234 |

本机 BF16 最大原生尺寸已实测的是 5 秒；BF16 768p／15 秒的显存可用性尚未验收。2K 长片使用重叠窗口，真正 15 秒成片的接缝质量仍需单独验收。不要由接口参数范围推断所有组合已完成本机质量测试。

队列按模型分组，同模型内部保持顺序。有其他模型等待时，最多连续处理 3 个同模型任务；等待另一模型达到 30 分钟时，在下一任务或已派发小批次边界优先切换。正在计算的任务或批次不抢占，因此新请求可能需要等待整个当前批次完成。每模型最多 32 个未完成任务，满时返回 HTTP 429。

4K 使用单任务、单窗口；2K 的兼容任务按相同尺寸、种子、采样器合并，每次最多 2 个窗口，共用一轮编码、DiT 计算和解码的模型加载，VAE 在编码、解码阶段分别加载。BF16 连续任务复用后端进程，但内部大组件仍需分阶段加载。本机此前 768p／5 秒／图片＋视频 BF16 总耗时约 12 分 39 秒；单段本地 2K 实测约 25 分钟，均不包含在前面任务后排队的时间。

常见错误：400／422 为模型名或参数、素材引用不符合要求；404 为任务／文件 ID 不存在或查询端口不符；409 为视频尚未完成；413 为文件过大；415 为不支持的文件格式；429 为队列已满。收到失败后保留任务 ID 和错误内容，避免无条件重复提交。

启动、停止、恢复与资源限制见 [共享队列运维说明](video-http-queue.md)。GPU 长验收结果见 [验收记录](../deployment/video-queue/validation.json)，其中进行中和已完成项目明确区分。
