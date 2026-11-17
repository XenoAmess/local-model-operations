# BF16 Omni 本机速度对照

本页为历史测速记录。后续已按用户要求部署 [BF16 Omni 与 2K 共享队列 HTTP 服务](video-http-queue.md)，当前运行状态、模型名称和启停以该文档为准。

用户于 2026-11-16 要求实际测量 BF16 Omni。测试使用与刚恢复的 NVFP4 QAD 相同的图片、带音轨视频、提示词、种子 1234、1344×768、5 秒请求和 8 次前向计算。它不是完整 MiniMax H3 的 50 步测试，也不包含后续 2K 重生成。

## 实测结果

2026-11-16 17:40 已生成完整视频并通过局域网下载校验。RTX 6000D 单卡上，**BF16 Omni 生成耗时 759.21 秒，约 12 分 39 秒**；同素材 NVFP4 QAD 对照为 **350.32 秒，约 5 分 50 秒**。本次两套实际配置的整体耗时比为 **2.17 倍**。

| 阶段 | BF16 Omni | NVFP4 QAD Omni |
| --- | ---: | ---: |
| 文字与参考条件编码 | 44.07 秒 | 4.23 秒 |
| 图片／视频／音频潜变量准备 | 54.62 秒 | 40.75 秒 |
| 去噪阶段 | 641.97 秒 | 298.84 秒 |
| 视频解码 | 16.26 秒 | 5.24 秒 |
| 模型生成总耗时 | **759.21 秒** | **350.32 秒** |

BF16 按需加载区间合计 78.09 秒，其中编码器 37.59 秒、视频 VAE 12.51 秒、音频 VAE 1.36 秒、DiT 26.63 秒，均已包含在上表阶段中，不重复相加。去噪阶段扣除日志中的 DiT 加载区间后为 **615.33 秒（10 分 15 秒）**；八次前向的 CUDA block 计时合计 614.66 秒，首次约 77.96 秒，后续约 76.66～76.68 秒。因此本次差距主要在计算，不能用首次加载解释全部差距。API 启动另为 6.01 秒；API 就绪时模型仍待按需加载。

两次都实际输出 1344×768、124 帧、24 FPS、5.167 秒的视频，含音轨。BF16 成片约 3.04 MB，API 与网页的局域网实际下载均与服务器 SHA-256 一致，抽查第 0、60、123 帧人物与场景完整、没有黑帧或损坏。此项不构成动作精确复现或画质优劣排名。

- [BF16 本次成片下载](http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/omni-bf16-768p-5s-20261116.mp4)
- [NVFP4 对照成片下载](http://192.168.1.11:7860/gradio_api/file=/home/ubuntu/workspace/xenoamess_bake_videos/omni-web/outputs/omni-restored-768p-5s-20261116.mp4)
- [完整测量与恢复记录](../deployment/omni-bf16/benchmark-result.json)

显存实占采样峰值 81,539 MiB（约 79.6 GiB；10 秒采样），框架各阶段最大张量分配峰值 73.88 GiB。模型进程的主机内存峰值 79.00 GiB，swap 峰值 0.743 GiB，没有 OOM；内存压力累计约 1.11 秒。API 返回的 `peak_memory_mb=1146.92` 是最后阶段重置后的计数，不能用作整次生成的峰值，记录中已明确标注。

17:41 已停止临时 BF16 测试模型，恢复 NVFP4 API 8001 与网页 7860；2K HTTP 8002 保持待机，全部关闭开机自启。BF16 权重保留，未切换为长期服务。本轮只有一条 5 秒任务，不外推 15 秒或 2K 耗时。

## 权重与精度

- 官方 BF16 Omni：`FastVideo/FastVideo-FastH3-Omni-8-Step-V1@53e0d26a1691aa473b6262d8196a8feb2c297df0`。专用导出约 65.33 GiB、14 个权重分片，逐一核对发布者 LFS SHA-256。
- 共享组件：按 Omni 采样约定固定的 `MiniMaxAI/MiniMax-H3@9bfb6693f2cf6de171db46d1aa586f67d773a1da`。约 72.4 GiB 大权重与本机已验证文件相同，以硬链接复用；小文件匹配发布者 Git blob ID 后复用。
- 完整模型目录为 `models/FastH3-Omni-BF16/`，由 `tools/prepare_omni_bf16.py` 组合导出和共享组件，不把 NVFP4 权重改标签充当 BF16。
- BF16 路径使用未量化的生成模型与编码器、原版 36 层 VAE（本机 FastVideo 加载 FP32 权重，沿用发布版 FP16 解码混合精度），保持检查点训练配套的 VSA 0.9、128-token tile、参考保留率 0.1、8 次前向。SM120 的注意力使用经过预检查的 BF16 Triton 稀疏内核，`quantize=False`。
- 不复用 NVFP4 QAD 的 AdaLN 表。BF16 模型使用其自身投影与精确 timestep 缓存。

模型说明：[BF16 Omni](https://huggingface.co/FastVideo/FastVideo-FastH3-Omni-8-Step-V1)、[NVFP4 QAD](https://huggingface.co/FastVideo/FastH3-Omni-NVFP4-QAD)、[FastVideo 参考推理说明](https://github.com/hao-ai-lab/FastVideo/blob/main/docs/inference/fasth3_omniref.md)。本机测量使用现有 FastVideo，不代表 UniServe 在其他硬件上的最优吞吐。

## 计时口径

NVFP4 对照已实测：总生成 350.32 秒，参考准备 40.75 秒、去噪 298.84 秒、视频解码 5.24 秒，最终为 124 帧、24 FPS、5.167 秒，含音频。记录见 `deployment/omni-restored-20261116.json`。

NVFP4 的编码器、DiT 和解码器在请求前已常驻显卡。BF16 全栈无法采用同样的同时常驻策略，使用分阶段按需加载和释放以适应本机显存与 80 GiB 主机内存上限。必须分别报告 API 启动、加载在内的首次生成、去噪、解码与峰值资源；不能仅以两种加载策略的总耗时比值声称纯计算精度带来的倍率。

BF16 原始结果保存于 `outputs/omni-bf16-benchmark/run-status.json`、`job-status.json`、`worker.log`、`resource-samples.jsonl` 与完整成片。提交到 Git 的精简记录为 `deployment/omni-bf16/benchmark-result.json`。测试开启阶段日志与 CUDA event 计时，每次前向末尾同步一次；数据代表这套本机配置的单次实测，不代表其他推理引擎的极限速度。

## 重现与恢复

先在隔离下载服务中准备权重，固定最多两条下载通道、6 GiB 内存；脚本支持断点续传。镜像只承担公开权重传输，禁用隐式 HF token，最终仍核对官方提交与哈希。

```bash
cd /home/ubuntu/workspace/xenoamess_bake_videos
python3 llm-lab/scripts/run_isolated.py \
  --unit llmlab-omni-bf16-download-manual --memory-gib 6 --wait -- \
  /usr/bin/env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    -u http_proxy -u https_proxy -u all_proxy \
    HF_ENDPOINT=https://hf-mirror.com HF_HUB_DISABLE_IMPLICIT_TOKEN=1 \
    llm-lab/.venv/bin/python tools/prepare_omni_bf16.py

python3 llm-lab/scripts/run_isolated.py \
  --unit llmlab-omni-bf16-attention-manual --memory-gib 4 --wait -- \
  FastVideo/.venv/bin/python tools/check_omni_bf16_attention.py

# 控制脚本只做调度；实际模型始终在另一个 80 GiB 隔离 unit 内运行。
python3 tools/run_omni_bf16_benchmark.py
```

控制脚本等待已有 Omni 请求结束，持有与 2K 队列共用的 GPU 互斥租约，然后停止 NVFP4 API/网页，在 8001 临时启动 BF16。实际模型 unit 为 `llmlab-h3-2k-omni-bf16-benchmark-20261116.service`，模型名 `fasth3-omni-bf16`，不会启用开机自启。正常结束或失败后停止测试模型并恢复原有 NVFP4 API/网页；发生错误后不自动重试 BF16。

主动中断控制脚本时，会停止测试模型且不自动重启模型；也可先创建 `outputs/omni-bf16-benchmark/do-not-restore` 阻止恢复。显式停止模型后的用户新指令优先。独立 2K HTTP 8002 保留在线，期间任务等待显卡释放。此前完整 H3 的性能优化仍暂停，不随本次测试自动恢复。

本次结果用于比较当前两套实际运行配置的速度，不凭单条视频宣布任一版本的画质绝对更好。
