# FastH3 Omni 视频渲染部署与运维

跨版本经验见[MiniMax H3／FastH3部署总览](minimax-h3-deployment-experience.md)：特别区分本页NVFP4历史流程、当前BF16服务、36L解码和后级IC重生成，不把历史15秒结果外推到BF16显存可用性。

当前 BF16 Omni 和 2K 使用[共享队列部署](video-http-queue.md)：模型名称分别为 `fasth3-omni-bf16`、`open-h3-2k`，8001／8002 同时接单、自动切换 GPU。本页保留旧 NVFP4 部署与历史渲染流程；旧服务已停止，当前启停以共享队列文档为准。

2026-11-16 16:33 用户要求先部署 Omni，现已恢复 Omni API 8001 与网页 7860，保留 quality-36L，默认草稿 768p；[完整 H3＋本地 2K 串联服务](h3-2k-http.md) 已停止。[独立 2K HTTP 服务](h3-2k-refiner-http.md) 保留在 8002，Omni 常驻时队列等待显卡释放。处理完草稿后，先停止 Omni 模型，再让 2K 队列执行，当前不自动切换两个模型。

更新：2026-11-16。本机用户 `ubuntu`，项目目录 `/home/ubuntu/workspace/xenoamess_bake_videos`。以下 `systemctl --user` 命令无需 `sudo`，可在任意目录运行；其他相对路径命令在项目目录执行。

当前使用官方 [FastH3 Omni NVFP4 QAD](https://huggingface.co/FastVideo/FastH3-Omni-NVFP4-QAD)，固定权重版本 `f01e6a23ac6066aa9eb622cf94b6259442e70ec2`，FastVideo 基线版本 `a0e6cf1f5086c9af735d73e6c0b80dbc1d5817b3`，包含本机 2026-11-16 AdaLN 参考模态子集匹配修复。它与仅验证文字生成的 V2 是独立部署。

这套流程为：**imagegen 重绘角色参考 → Omni 根据图片、文字、视频生成 → FFmpeg/OpenCV 完成白框出框、裁秒、原配乐和 GIF → Gradio 提供局域网下载**。角色比例需要改变时使用完整重绘并确认的参考图，保留原图作为模型输入。

快速定位：[启动](#手动启动)、[停止和释放显存](#停止和释放显存)、[服务恢复](#部署组成与服务恢复)、[完整渲染流程](#完整渲染流程-v4)、[显存与速度](#本机验证和文件)。

## 部署组成与服务恢复

本节记录本机已落地的环境及恢复方式。2026-11-16 已按用户要求停止 Qwen Coder 及对应巡检，启动支持参考图片、视频的 Omni API，局域网网页与模型状态检查通过；旧 V2 保持停止。模型和网页均禁用开机自启；[本次切换记录](../outputs/model-switch-to-omni-20261116.json)。

| 组件 | 本机配置 |
| --- | --- |
| 系统 / GPU | Ubuntu 26.04.1 LTS；RTX 6000D，Blackwell / SM 12.0，总显存 85,651 MiB |
| Python / PyTorch | `FastVideo/.venv/`，Python 3.12.16，PyTorch 2.12.0+cu130 |
| CUDA 编译工具 | `tools/cuda`，13.2.86，兼容本机系统头文件 |
| FlashInfer / Transformers | 0.7.2.post1 / 5.15.1 |
| 网页 | Gradio 5.32.0，gradio_client 1.10.2 |
| GPU 内核 | 本机按 `sm_120a` 源码编译的 `fastvideo-kernel==0.3.5`，提供稀疏 FP4 接口；先前通过八项官方 GPU 数值测试 |
| 模型管线 | `MiniMaxH3Ref2VAModularPipeline`，单卡、TP=SP=1，NVFP4 `h3_dit_vsa` profile |
| 采样与注意力 | Omni 八次 PDD 计算，VSA 0.9，128-token tile，FP4 注意力及 FP8 前缀 |
| 视频解码 | 36 层质量解码器，`vae_decoder_nvfp4/decoder-nvfp4.safetensors` |
| 分块 / Offload | Gate 8192 行、FFN 16384 tokens；YAML 中组件 CPU offload、torch compile 关闭；使用专用预计算 AdaLN 表 |
| 后期 | FFmpeg 8.0.1；OpenCV、NumPy 使用 FastVideo 虚拟环境中的版本 |

本机部署顺序是：固定源码和 Python/CUDA 环境 → 编译稀疏 FP4 内核 → 下载并校验完整 Omni 权重 → 使用短参考生成准备并校验 AdaLN 表 → 安装隔离 API 和网页服务 → 验证图片＋视频生成及局域网下载。

权重目录为 `models/FastH3-Omni-NVFP4-QAD/`，完整组件约 68.9 GB，包含参考 transformer、Qwen3-VL 编码器、视频/音频 VAE 和解码器；`transformer/` 软链接指向 `transformer_ref/`。[下载清单](../models/FastH3-Omni-NVFP4-QAD.download-manifest.json)和[校验报告](../models/FastH3-Omni-NVFP4-QAD.verification.json)保存了版本、大小和 SHA-256。报告中的 `inference_run: false` 是 2026-10-27 下载阶段的记录；后续生成验证见本文末尾。

启动脚本设置 `HF_HUB_OFFLINE=1` 和 `TRANSFORMERS_OFFLINE=1`；恢复时须准备完整本地权重，启动过程不会自动补下载缺失文件。

恢复本机时应一并保留：

- `FastVideo/` 及其 `.venv/`、本机编译内核和 `tools/cuda` 配套文件。
- `models/FastH3-Omni-NVFP4-QAD/`，包括 `adaln_tables-local.pt` 和 [完成标记](../models/FastH3-Omni-NVFP4-QAD/adaln_tables-local.complete.json)。本机表约 300 MB，50 个 block，每个八条 timestep 记录。
- `llm-lab/.venv/`、`llm-lab/scripts/run_isolated.py`、同目录的 `resource_guard.py`、`memory_watchdog.py` 和 `llm-lab/systemd/llmlab.slice`。
- 下表中的配置、启动脚本和服务文件副本；完整包版本见 [requirements-omni-deployed.txt](../requirements-omni-deployed.txt)。

| 文件 | 作用 |
| --- | --- |
| [fasth3-omni.yaml](../fasth3-omni.yaml) | 模型路径、解码器、采样、API 8001 及素材允许目录 |
| [start-fasth3-omni.sh](../start-fasth3-omni.sh) | 本机 CUDA、FP4/VSA、分块、AdaLN 表、离线加载及编译线程环境 |
| [tools/serve_fasth3_omni.py](../tools/serve_fasth3_omni.py) | 检查资源隔离后启动原生 API |
| [omni-web/app.py](../omni-web/app.py)、[网页启动脚本](../start-fasth3-omni-web.sh) | Gradio 上传、提交、轮询、播放和下载 |
| [API 服务副本](../deployment/systemd/fasth3-omni.service) | `fasth3-omni.service`，包装隔离启动器 |
| [网页服务副本](../deployment/systemd/fasth3-omni-web.service) | `fasth3-omni-web.service`，监听 7860 |

服务文件实际安装于 `/home/ubuntu/.config/systemd/user/`。定义丢失或需要恢复时执行：

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
mkdir -p ~/.config/systemd/user
cp deployment/systemd/fasth3-omni.service deployment/systemd/fasth3-omni-web.service \
  ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable fasth3-omni.service fasth3-omni-web.service
```

然后按下文手动启动。unit 和 YAML 使用本机绝对路径；迁移目录或更换用户时需修改相应路径。

API 启动链路为 `fasth3-omni.service` → `llm-lab/.venv/bin/python run_isolated.py` → 临时 `llmlab-fasth3-omni.service` → `start-fasth3-omni.sh` → `FastVideo/.venv/bin/python tools/serve_fasth3_omni.py` → Ref2VA API。启动器自动准备资源 slice 并启动独立内存看护；主机至少有 28 GiB 可用内存才启动。`start-fasth3-omni.sh` 应在隔离链路内使用，直接在普通交互进程中运行会被检查拒绝。

AdaLN 完成标记存在时，启动脚本使用预计算表；没有标记时使用主机缓存并在推理中写出表。表需验证完整性和模型 revision 后才添加完成标记。恢复时优先保留已校验的表与标记。

## 访问和生成

| 用途 | 地址 |
| --- | --- |
| 局域网网页 | http://192.168.1.11:7860 |
| 本机网页 | http://127.0.0.1:7860 |
| HTTP API | http://192.168.1.11:8001/v1 |
| API 交互文档 | http://192.168.1.11:8001/docs |
| 健康检查 | http://127.0.0.1:8001/health |

API 和网页均监听 `0.0.0.0`。局域网 IP 变化后可用 `hostname -I` 查询，并选择与客户端同网段的地址；端口保持不变。8000 和 8080 仍是已有文本模型网关。

网页采用 Gradio，与[官方 Omni 演示](https://huggingface.co/spaces/FastVideo/FastH3-Omni)使用相同的界面框架；本机界面单独连接原生 FastVideo HTTP API，直接使用已下载的 FastVideo 格式权重。没有使用需要另一套权重的 ComfyUI 工作流。

1. 上传参考图片、参考视频和可选参考音频。
2. 用文字说明保留什么、改变什么。图片按顺序标记为 `<Picture 1>`、`<Picture 2>`；视频为 `<Video 1>`；独立音频为 `<Audio 1>`。视频内的音轨也会被模型读取。
3. 选择分辨率、时长和种子，点击“生成视频”。完成后可以播放和下载 MP4。浏览器需保持连接以接收结果。

例如：`将 <Video 1> 中唯一的人物替换为 <Picture 1> 中的角色。保留视频的动作、镜头、背景与节奏，保持参考人物的发型、眼镜和服装特征。`

参考生成会重新合成画面；动作、脸部和背景能否精确保持，需要检查每个结果。它不保证像素级人物替换或逐帧动作复制。去水印需求应同时清理参考素材，并检查最终输出。

## 输入和输出范围

- 图片最多 9 张、视频最多 3 个、独立音频最多 3 段，素材合计最多 12 个；当前网页至少需要一张图片或一个视频。
- 网页提供 `832x480`、`1344x768`、`768x1344` 和 `768x768`。当前 API 最大画幅面积为 1,032,192 像素，宽高须为 32 的倍数。本次竖屏最大档为 768×1344，不把插值放大当作模型原生分辨率。
- 网页提供 5、10、15 秒，API 支持整数 5–15 秒；24 FPS。帧数按 `17n+5` 对齐，15 秒请求为 362 帧，实际约 15.083 秒。
- 当前模型最短生成约五秒；一秒预览也要先生成最短片段再裁剪。
- `seed` 可控制随机种子。每次生成一个带同步音频的 MP4。
- 服务固定 Omni 八次 PDD 计算、VSA 0.9、NVFP4 主模型、FP8 注意力前缀和 36 层质量解码器。不要套用 V2 的九采样点配置，也不要复用 V2 的 AdaLN 表。
- API 未指定尺寸时默认 1344×768，网页默认同一尺寸；竖屏最大档为 768×1344。480p 仍可手动选择，但不再是默认值。2K 成片通过独立 8002 重生成入口处理，不把 Omni 草稿本身称为 2K。
- 上传单个文件上限 512 MB。参考素材、生成结果会保留在磁盘，使用后可自行清理无需保留的文件。

`omni-web/uploads/` 是 API 明确允许读取的本机素材目录；任意其他本机路径不能直接读取。网页会把上传文件复制到该目录。API 不默认允许私网 HTTP 素材地址。

八步是此 Omni 权重配套的 PDD 采样约定，不是可随意增加到五十步的质量等级。[官方模型卡](https://huggingface.co/FastVideo/FastH3-Omni-NVFP4-QAD) 将 36 层解码器标为质量档、8 层标为快速档；本机使用 36 层。NVFP4 QAD 是为量化推理训练的独立版本，输出可能与 [BF16 Omni](https://huggingface.co/FastVideo/FastVideo-FastH3-Omni-8-Step-V1) 不同，未对各版本作画质排名；不将当前量化版称为所有变体的绝对最佳，也不随意改变训练配套的注意力与采样参数。

## 手动启动

各服务保持禁用开机自启。启动前停止占用同一块 GPU 的其他模型：

```bash
systemctl --user stop llmlab-tool-quality-monitor.timer llmlab-real-quality-audit.timer
systemctl --user stop llmlab-tool-quality-monitor.service llmlab-real-quality-audit.service
systemctl --user stop qwen38-coder.service fasth3-v2.service
systemctl --user stop h3-2k-web.service h3-2k-http.service
# 手动切换前结束独立 2K 的推理；启动 Omni 后可再启动 8002 等待队列。
systemctl --user stop h3-2k-refiner-http.service
systemctl --user start fasth3-omni.service fasth3-omni-web.service
systemctl --user start h3-2k-refiner-http.service
```

`start` 返回后模型可能仍在加载。检查：

```bash
systemctl --user status fasth3-omni.service fasth3-omni-web.service --no-pager
journalctl --user -u llmlab-fasth3-omni.service -f
curl --noproxy '*' --fail http://127.0.0.1:8001/health
```

返回 `{"status":"ok"}` 表示 API 就绪。网页也会更新模型状态。

## 停止和释放显存

```bash
systemctl --user stop fasth3-omni-web.service fasth3-omni.service
systemctl --user is-active fasth3-omni.service llmlab-fasth3-omni.service
nvidia-smi
```

停止 API 会中断正在生成的任务并释放其显存。仅关闭浏览器或仅停止网页不会卸载模型；API 运行期间，模型和推理缓存会常驻显存。生成完大任务后显存缓存也可能继续保留。

若网页已经在线，只停止模型，可继续下载已有文件：

```bash
systemctl --user stop fasth3-omni.service
```

网页 unit 有 `Wants=fasth3-omni.service`，重新启动网页时会同时请求启动模型。停止网页后，其 HTTP 下载链接也停止提供访问，磁盘文件仍保留。

确认没有开机自启：

```bash
systemctl --user is-enabled fasth3-omni.service fasth3-omni-web.service
```

两项都应为 `disabled`。若以后被手动改动，需要关闭自启但保持当次服务在线，可执行 `systemctl --user disable fasth3-omni.service fasth3-omni-web.service`。

切换回 Qwen：

```bash
systemctl --user stop fasth3-omni-web.service fasth3-omni.service
systemctl --user start coder-admission.service qwen38-coder.service
```

Qwen 健康检查通过后，可手动启动 `llmlab-tool-quality-monitor.timer` 与 `llmlab-real-quality-audit.timer`。不需要重启已有 Bifrost 面板或更改 Qwen 固定参数。

## HTTP 调用

上传素材到 `omni-web/uploads/` 后，可以异步提交：

```bash
curl --noproxy '*' http://127.0.0.1:8001/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "fasth3-omni",
    "task": "ref2va",
    "prompt": "Use the character in <Picture 1> and the dance motion in <Video 1>.",
    "image_reference": [{"image_url": "/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/uploads/reference.jpg"}],
    "video_reference": [{"video_url": "/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/uploads/reference.mp4"}],
    "size": "768x1344",
    "seconds": "15",
    "seed": 1234
  }'
```

返回任务 `id` 后，查询 `GET /v1/videos/{id}`；`status` 为 `completed` 时下载 `GET /v1/videos/{id}/content`。`failed` 时检查返回的 `error` 和服务日志。模型只会串行执行生成任务；请求耗时会受输出画幅、时长、参考视频长度及首次内核编译影响。

本次完整参数和提示词见 [V4 请求](../outputs/person-replacement-v4-request.json)。下面会提交一个新的生成任务：

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
curl --noproxy '*' --fail-with-body http://127.0.0.1:8001/v1/videos \
  -H 'Content-Type: application/json' \
  --data-binary @outputs/person-replacement-v4-request.json -o outputs/omni-job.json

OMNI_JOB_ID=$(python3 -c 'import json; print(json.load(open("outputs/omni-job.json"))["id"])')
curl --noproxy '*' --fail-with-body "http://127.0.0.1:8001/v1/videos/$OMNI_JOB_ID"
```

确认 `completed` 后下载原始视频：

```bash
curl --noproxy '*' --fail \
  "http://127.0.0.1:8001/v1/videos/$OMNI_JOB_ID/content" -o outputs/omni-raw.mp4
```

当前 H3 接口的 `progress` 可能持续为 0，完成才变为 100；应看最终状态和阶段日志。原始文件同时在 `outputs/omni-api/videos/{任务id}.mp4`；应保留请求 JSON、任务结果 JSON 和 MP4，便于重启后查找和重现。

## 完整渲染流程 V4

### 人物参考与源视频

二头身角色参考应使用 **imagegen 技能重绘的完整角色图**，先给用户看图，再使用确认版本。脸、服装和四肢应统一绘制，不用代码裁剪、缩放成人头身并拼接成角色参考。

本次确认的 [imagegen 重绘图](../omni-web/uploads/person-replacement-v3-20261031/character-two-head-imagegen-v1.png) 作为唯一图片参考，整张原样提交；[绘制提示词](../outputs/character-two-head-imagegen-v1.prompt.txt)和[参考图记录](../outputs/character-two-head-imagegen-v1.json)均已保存。PNG SHA-256 为 `472d633ea178e30cd3395a3f7290257a6dbbbbe0f6b2fbc653706d1a251c570a`。

源视频为 `omni-web/uploads/person-replacement-20261030/视频1.mkv`。本次取主视频流，规范为 768×1344、24 FPS、前 362 帧，并清理右上角水印。已准备好的模型输入为 `reference-video-clean.mp4`，位于同一目录。重建同一素材的示例：

```bash
ffmpeg -hide_banner -y \
  -i omni-web/uploads/person-replacement-20261030/视频1.mkv \
  -map 0:v:0 -map '0:a:0?' \
  -vf 'scale=768:1344:flags=lanczos,fps=24,delogo=x=502:y=18:w=252:h=60' \
  -frames:v 362 -t 15.083333 \
  -c:v libx264 -crf 18 -preset fast -c:a aac -b:a 192k -movflags +faststart \
  omni-web/uploads/person-replacement-20261030/reference-video-clean-rebuilt.mp4
```

水印坐标只适用于这组规范化后的素材。`delogo` 是局部背景插值，新视频或人物覆盖水印区域时应重新确定处理方式并检查画面。

随后按上一节的 HTTP 方式生成，或从网页提交同样素材和要求。模型会重新合成画面和同步音频，需要检查人物、比例、动作和背景的实际效果。网页提交完成的是模型原始生成，下面的后期命令制作交付版本。

### 白框、草穗出框和原配乐

[composite_foxtail_frame.py](../tools/composite_foxtail_frame.py) 为本次 15 秒素材准备：小幅等比重构图去掉模型细框，提取浅绿色草穗、茎和绒毛，将固定白框放在前景草穗之后，并添加柔和阴影。先检查分段效果，再导出：

```bash
FastVideo/.venv/bin/python tools/composite_foxtail_frame.py \
  outputs/omni-api/videos/video_gen_e5b6cc5d64314a1da88ea0031d0efe86.mp4 \
  outputs/foxtail-frame-check.jpg \
  --preview --border 80 --vertical-offset -80

FastVideo/.venv/bin/python tools/composite_foxtail_frame.py \
  outputs/omni-api/videos/video_gen_e5b6cc5d64314a1da88ea0031d0efe86.mp4 \
  outputs/person-replacement-v4-imagegen-768x1344-15s.mp4 \
  --audio omni-web/uploads/person-replacement-20261030/视频1.mkv \
  --border 80 --vertical-offset -80
```

- `--border 80`：四边固定 80 像素白框，草穗覆盖框边。
- `--vertical-offset -80`：整体画面上移 80 像素，给靴子留出框内空间；偏移绝对值不得大于边框宽度。
- `--audio`：恢复原片前 15 秒配乐。
- 输出为 H.264 + AAC、24 FPS、360 帧、**15.000 秒**；编码为 CRF 18，音频 192 kbps。
- 同时写出 `.compositing.json`，记录构图和前景覆盖白框的帧数。

脚本固定处理 15 秒，预览取 2、3、6、8、12 秒，输入须有足够帧数。它依赖浅绿色前景的颜色特征；换成其他前景或绿色服装场景时需要检查/调整抠像方式。

无需白框，仅裁成精确 15 秒并恢复原配乐时，可用：

```bash
ffmpeg -hide_banner -y -i outputs/omni-raw.mp4 \
  -i omni-web/uploads/person-replacement-20261030/视频1.mkv \
  -map 0:v:0 -map 1:a:0 -t 15 -c:v copy -c:a aac -b:a 192k \
  -movflags +faststart outputs/omni-final-15s.mp4
```

### GIF 小于 20 MB

保持完整 15 秒、12 FPS 和循环播放，使用 128 色调色板与有序抖动。以下是本次实际采用的 512×896 配置：

```bash
ffmpeg -hide_banner -y -threads 4 \
  -i outputs/person-replacement-v4-imagegen-768x1344-15s.mp4 \
  -filter_complex_threads 2 \
  -filter_complex '[0:v]fps=12,scale=512:896:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle' \
  -an -loop 0 omni-web/outputs/person-replacement-v4-imagegen-under20mb.gif

python3 - <<'PY'
from pathlib import Path
p = Path('omni-web/outputs/person-replacement-v4-imagegen-under20mb.gif')
size = p.stat().st_size
print(f'{size} bytes, {size / 1_000_000:.2f} MB')
assert size < 20_000_000, 'GIF exceeds 20 MB; reduce dimensions and encode again'
PY
```

本次结果为 **19,062,175 字节，约 19.06 MB**。其他视频须检查实际字节数；超限时依次尝试 `480:840`、`448:784`、`416:728`，这些尺寸保持本次 4:7 画幅。GIF 不包含音频。

### 局域网发布和验收

把要分享的成片放入网页允许的 `omni-web/outputs/`，无需重启网页：

```bash
cp outputs/person-replacement-v4-imagegen-768x1344-15s.mp4 omni-web/outputs/
```

下载链接格式为：

```text
http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/文件名
```

本次实际链接：[MP4](http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/person-replacement-v4-imagegen-768x1344-15s.mp4)、[GIF](http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/person-replacement-v4-imagegen-under20mb.gif)。

检查文件规格、完整解码和下载：

```bash
ffprobe -v error -show_entries format=duration,size:stream=codec_name,width,height,nb_frames,r_frame_rate \
  -of json outputs/person-replacement-v4-imagegen-768x1344-15s.mp4
ffmpeg -hide_banner -loglevel error \
  -i outputs/person-replacement-v4-imagegen-768x1344-15s.mp4 -f null -
curl --noproxy '*' --fail --range 0-31 --dump-header - --output /dev/null \
  'http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/person-replacement-v4-imagegen-under20mb.gif'
```

范围下载应返回 `206 Partial Content`。同时检查逐秒画面和草穗过框的放大画面，确认人物、头身比、动作、水印和遮挡；文件格式正确不能代替画面验收。

## 本机验证和文件

2026-11-16 16:47 恢复后的实测：API 不指定尺寸，采用新默认 1344×768、5 秒请求、一张图片与带音轨的视频参考，固定 8 次前向和 quality-36L。模型耗时 **350.3 秒，约 5 分 50 秒**，其中参考潜变量准备 40.8 秒、去噪 298.8 秒、视频解码 5.2 秒。实际输出 124 帧、24 FPS、5.167 秒，含音轨；局域网下载 SHA-256 与服务器文件一致，抽查第 0、60、123 帧没有黑帧或损坏。此项是部署与生成验证，不是 BF16／NVFP4 画质排名或精确动作复现验收。[恢复验证记录](../deployment/omni-restored-20261116.json)。此前约一分钟的测试为 480p、仅图片参考，不能代表本次高规格输入的耗时。

2026-11-16 17:40 完成同素材 BF16 Omni 对照：1344×768、5 秒、8 次前向、原版 36 层解码器，生成耗时 **759.21 秒（12 分 39 秒）**，去噪阶段 641.97 秒、视频解码 16.26 秒。BF16 使用按需分阶段加载，不能把整体 2.17 倍耗时直接解释为纯精度计算倍率。[测评、加载口径与成片](omni-bf16-benchmark.md)。测试后已恢复本页 NVFP4 服务。

2026-10-30 已通过本机和 LAN 地址的网页、健康检查与模型列表检查，并通过 Gradio 客户端实际完成“图片＋视频”端到端生成。480p、124 帧、短视频参考的预热任务服务耗时约 96.9 秒，网页全程约 100 秒；这是小输入测试，不能代表最大规格的生成速度。记录见 `outputs/omni-ui-warmup.json`，任务 `video_gen_739eec439af941f18991fcacda852e2f`。

同日最初的“图1角色替换视频1人物、去右上角水印”任务使用一张参考图及完整 15 秒视频参考，原生输出 768×1344、362 帧，单卡耗时 1210.8 秒，约 20 分 11 秒。

交付视频以原视频配乐替换生成音轨，并无损裁剪视频流到 360 帧、**15.000 秒**。已逐秒抽查角色和右上角，未见原水印，并通过完整音视频解码及 LAN 下载检查。[最终视频](../outputs/person-replacement-768x1344-15s.mp4)、[预览](../outputs/person-replacement-final-preview.jpg)、[验证记录](../outputs/person-replacement-validation.json)、[原始任务结果](../outputs/person-replacement-status.json)。上述耗时仅代表这组完整参考素材，参考长度和输出画幅变化会改变耗时。

2026-10-31 的确认重绘图版本（V4）使用一张 imagegen PNG 和完整 15 秒视频参考，模型耗时 **1267.5 秒，约 21 分 8 秒**，其中去噪 1142.1 秒、参考潜变量准备 103.2 秒、视频解码 15.2 秒。最终 MP4 为 768×1344、360 帧、15.000 秒、约 8.17 MB；GIF 为 512×896、180 帧、15 秒、约 19.06 MB。记录：[任务结果](../outputs/person-replacement-v4-status.json)、[交付验证](../outputs/person-replacement-v4-validation.json)、[逐秒预览](../outputs/person-replacement-v4-final-preview.jpg)、[GIF 压缩记录](../outputs/person-replacement-v4-gif-compression.json)。

V4 阶段日志显示峰值已分配 GPU 显存约 **66.30 GiB**，PyTorch 保留峰值约 **77.85 GiB**。结束后实测 GPU 利用率为 0%，但 `nvidia-smi` 仍为 **80,411 MiB，约 78.5 GiB**；较早一次空闲约 36 GiB。显存缓存随任务变化，不是固定值，不用时停止 API 才释放。

| 文件 | 用途 |
| --- | --- |
| `fasth3-omni.yaml` | API、模型、解码器与素材允许目录 |
| `start-fasth3-omni.sh` | CUDA 环境、显存分块及专用 AdaLN 表 |
| `tools/serve_fasth3_omni.py` | 资源隔离检查及 API 入口 |
| `omni-web/app.py` | 网页、上传、提交、轮询和下载 |
| `start-fasth3-omni-web.sh` | 网页启动入口 |
| `deployment/systemd/fasth3-omni*.service` | 两个已安装服务的项目内恢复副本 |
| `tools/composite_foxtail_frame.py` | 15 秒白框、草穗前景、原配乐与成片导出 |
| `outputs/omni-api/videos/` | API 生成结果 |
| `omni-web/outputs/` | 网页下载结果 |
| `models/FastH3-Omni-NVFP4-QAD/adaln_tables-local.complete.json` | 本机 AdaLN 表的摘要和生成依据 |
| `deployment-omni.json`、`requirements-omni-deployed.txt` | 部署配置摘要、文件校验及 Python 依赖快照 |

用户服务文件位于 `/home/ubuntu/.config/systemd/user/`。API 包装服务 `fasth3-omni.service` 自身上限 256 MiB，实际推理进程在 `llmlab-fasth3-omni.service`，主机内存上限 80 GiB；实验 slice 总上限 88 GiB、swap 总上限 1 GiB，并使用独立内存看护。网页上限 2 GiB。这些是主机内存限制，不是 GPU 显存上限。编译并行度固定为 `MAX_JOBS=2`，NVCC、FlashInfer NVCC 和 Inductor 编译线程各为 1。遇到内存失败应保留日志和请求，继续保留资源限制。

查看网页日志：`journalctl --user -u fasth3-omni-web.service -f`。修改 Python 网页后重启 `fasth3-omni-web.service`；修改模型配置后重启 `fasth3-omni.service`，会中断当前生成任务。

## 故障检查

```bash
journalctl --user -u llmlab-fasth3-omni.service -n 100 --no-pager
journalctl --user -u fasth3-omni.service -n 80 --no-pager
journalctl --user -u fasth3-omni-web.service -n 80 --no-pager
systemctl --user show llmlab-fasth3-omni.service -p MemoryCurrent -p MemoryPeak -p MemoryMax
ss -ltnp '( sport = :7860 or sport = :8001 )'
```

| 现象 | 检查和处理 |
| --- | --- |
| 网页可打开但模型不可用 | 检查 8001 `/health`、实际推理 unit 和模型加载日志；网页与模型是两个进程 |
| 8000 返回文本模型网关结果 | Omni API 使用 8001，保留原有 8000/8080 网关 |
| 包装服务启动但没有推理进程 | 查看包装和实际推理 unit 的失败日志；启动器已有 `reset-failed`，旧临时 unit 冲突时先停止 Omni 再根据日志处理 |
| 任务进度一直为 0 | 当前接口完成时才更新为 100，查看阶段日志和最终状态 |
| 本机素材路径被拒绝 | 把文件放在 `omni-web/uploads/` 下，传绝对路径 |
| 下载 404 | 确认文件位于 `omni-web/outputs/`，路径正确且网页在线 |
| 关闭浏览器后显存仍被占用 | 停止 `fasth3-omni.service`，仅停止网页不会释放 GPU |


## 2026-11-16 仅图片参考的 AdaLN 修复

原服务虽能正常加载并返回健康状态，但仅参考图片的生成会报 `No precomputed AdaLN modulation ... table only covers the checkpoint's fixed ladder`。本机表与当前固定权重 revision、文件摘要一致；原表是在包含音频参考时记录的，其唯一时间步集合包含额外的 1.0。仅图片参考会少这一行，旧代码按整组键匹配而错误拒绝。

现已修复 `MiniMaxH3AdaLayerNormModulation`：在时间值、嵌入维度和 dtype 完全匹配时，从已有表中精确选择并排序所需行。完整原键继续直接命中，真正未知的时间步继续报错。原表与权重文件保持原值。

客户端不需要新增配置，继续使用 `task: ref2va`、`num_inference_steps: 8`；网页默认值保持八步。已通过 9 项回归测试，并核对 50 个 block、400 组实际表的子集投影，所选行逐比特一致。HTTP 和 Gradio 网页分别完成仅图片参考、5 秒请求的实际生成与下载，视频为 832×480、24 FPS、124 帧，含同步音频。[完整修复和生成验收记录](../outputs/omni-adaln-repair-20261116/verification.json)，[已验证请求](../outputs/omni-adaln-repair-20261116/api-request.json)。

服务当前的任务索引保存在内存，重启后旧任务 ID 会返回 404。可续跑客户端应保存完整请求、参考文件及已下载成品；对 failed 或重启后未知的任务重新提交。生成视频磁盘文件不会因索引重置被删除。局域网长连接测试应直连本机地址，避免代理中断 Gradio 的 SSE 回传。
