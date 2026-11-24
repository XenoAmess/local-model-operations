# 完全本地的 H3 2K 重生成准备

2026-11-24整理说明：下文为2026-11-16的下载和早期准备记录，其中“未实测／拒绝长片／重叠窗口”等不能代替当前状态。IC已正式提供2K／4K，4K严格大于124帧走整段，已有10秒和14秒真实成片；2K长片仍保留重叠窗口。请先读[部署经验总览](minimax-h3-deployment-experience.md)和[当前4K接口](open-h3-4k-http.md)，再按需查下方历史实现。

2026-11-16 用户要求：包含 2K 重生成，必须完全本地，暂不使用官方云端。两套权重已于 12:15 前全部下载、校验完成。16:33 用户要求先部署 Omni，现已恢复 [Omni API 与网页](fasth3-omni.md)；[完整 H3 串联服务](h3-2k-http.md) 停止，[独立 2K HTTP](h3-2k-refiner-http.md) 保留在 8002，等待 Omni 释放显卡后处理已生成的草稿。

## 官方路线与选定的本地路线

[MiniMax 官方](https://github.com/MiniMax-AI/MiniMax-H3#full-2k-workflow) 将系统分为 Context-IR、H3-Base、H3-Regenerate-2K。官方说明后两阶段中的 2K 重生成利用 H3 的生成能力，但该重生成模块的实现尚未公开；官方示例通过云端 API 执行 Context-IR 和 2K。公开基础权重到齐不代表官方完整 2K 工作流可在本机运行。

本项目准备 [NVlabs/Sana 的 Open-H3-Regenerate-2K-IC](https://nvlabs.github.io/Sana/Open-H3-Regenerate-2K/#ic) 作为全本地替代。它有专门训练的 Ref2VA IC LoRA，保留低清草稿作为干净参考，配合 HyperFlow、LMS Sharp 和潜空间放大器，在目标分辨率进行扩散重生成。它是另一个项目发布的开放实现，不是 MiniMax 官方闭源 2K 模块。

计划链路：

```text
文字＋图片／视频参考
  → 本地官方 H3-Base Ref2VA BF16 生成草稿
  → 本地 H3 VAE 编码草稿
  → 3D 潜空间放大器＋IC LoRA 的 3／4／8 步重生成
  → 本地 VAE 解码为 2560×1440，保留草稿音轨
```

本路线不调用官方 Context-IR。基础阶段使用用户提示词和原始参考素材；重生成沿用生成草稿的提示词，并把草稿本身放入上下文。该实现并不自动继承原始图片、参考视频和音频的全部独立输入，不能宣称与官方三阶段系统等价。

## 固定版本与下载

- 基础权重：`MiniMaxAI/MiniMax-H3@0919fb684102ef115126612f3fbb84d1027e7317`，约 134.16 GiB，12:05:59 完成校验。
- 本地 2K 包：`Efficient-Large-Model/Open-H3-Regenerate-2K-IC@54a7104b204fb46486cf85c2f600942118186d57`。
- 对照源码：`NVlabs/Sana@cf67a3acad7511acb85053e56a05e5dd24c82ba0`，`models/Open-H3-Regenerate-2K/IC/`；下载包自带 `infer/` 源码，并逐文件校验。
- IC 包的基础权重文件虽然标注源自官方另一 revision，经官方 LFS SHA-256 清单比较，与当前下载中的大权重完全相同；约 133.56 GiB 可校验后硬链接复用，新增约 18.19 GiB。

新增组件包括：完整 FP32 rank-384 IC LoRA（约 7.73 GiB）、HyperFlow（2.60 GiB）、LMS Sharp（1.15 GiB）、3D 潜空间放大器（0.64 GiB）、静音音频 latent、配置和源代码，以及可选 24 层快速 VAE（6.03 GiB）。另按作者给定 SHA-256 通过字节范围读取 Sharp 的 32,800 字节 timestep 曲线，不下载其整套额外模型。

清单见 `deployment/minimax-h3/open-2k-download-manifest.json`。队列服务 `minimax-h3-2k-download-queue-20261116.service` 等当前 Base 下载和校验结束后，才启动 `llmlab-open-h3-2k-download-20261116.service`；下载仍最多两条通道、6 GiB 隔离内存。没有停止或重建现有 Base 下载任务。

Base 共 63 个文件，2K 包共 94 个文件。分别核验 32 和 37 个 LFS 文件的发布者 SHA-256，并通过分片索引检查；31 个大权重以硬链接共享，Sharp 的 32,800 字节曲线也匹配作者 SHA-256。2K 包于 12:14:57 完成校验，12:15:08 已触发对话通知，未运行模型推理。

完成标记分别是：

- `deployment/minimax-h3/weight-verification.json`：Base。
- `deployment/minimax-h3/open-2k-weight-verification.json`：本地 2K 包。

一次性通知服务 `minimax-h3-download-notify-20261116-v2.service` 等两套均校验完成后通知原对话；异常则通知检查恢复，不启动推理。下载器使用同一工具和不同清单：

```bash
python3 llm-lab/scripts/run_isolated.py \
  --unit llmlab-open-h3-2k-download-manual --memory-gib 6 --wait -- \
  "$PWD/FastVideo/.venv/bin/python" "$PWD/tools/download_minimax_h3.py" \
  --manifest deployment/minimax-h3/open-2k-download-manifest.json \
  --report deployment/minimax-h3/open-2k-weight-verification.json
```

只有当前下载任务结束后才手动执行补下载，避免超过两条下载通道。全部验证成功后保留原文件的硬链接；对共享权重不得原地覆盖或保存已合并 LoRA 的内容。

## 部署入口与需要完成的验收

已准备 `tools/run_open_h3_2k.py`，仅在隔离服务内运行；检测到其他模型在线就拒绝执行，不自动停止模型。入口固定单卡、`--attention native`、`--vae standard`，默认选择 `up3`。`standard` 使用未替换的原版完整 VAE；24L 权重只是备用，当前 FastH3 Omni 的 quality-36L 配置未改动。

2026-11-16 用户已明确授权部署 HTTP 服务。已建立 `.venv-h3-2k/` 独立入口，通过 `.pth` 只读复用原环境依赖，不升级或改写生产包。实际导入检查已确认 `diffusers==0.42.0` 包含 MiniMax-H3 Transformer、VAE、模块化编码器和布局实现，所有 IC 运行时模块已成功导入。先前“本机包缺少实现”的判断来自文件搜索忽略了虚拟环境目录，已经更正。作者给出的依赖基线与本机版本不同，因此仍以本机实际导入和成片验收为准。

以下是未来的手动运行模板，环境和权重验证通过、且用户明确要求切换后才执行：

```bash
python3 llm-lab/scripts/run_isolated.py \
  --unit llmlab-open-h3-2k-infer-manual --memory-gib 80 --wait -- \
  "$PWD/.venv-h3-2k/bin/python" "$PWD/tools/run_open_h3_2k.py" \
  --input "$PWD/draft.mp4" --output "$PWD/outputs/draft-2k.mp4" \
  --caption-file "$PWD/draft-prompt.txt" --sampler up3
```

目前尚未在 RTX 6000D 上运行或测量该路线。作者支持 1、2、4、7、8 GPU，但其单卡数据中心显卡结果不能作为本机显存或速度保证。需验证阶段加载、LoRA 合并时主机内存、2K 激活显存和 VAE 解码；保留 80 GiB 推理及 88 GiB 聚合主机内存上限。必要时添加 offload 或精确 AdaLN 缓存，不能提高上限绕过故障。

**时长限制：**固定源码的 `ref2va_ic/media.py` 只读取 124 帧，输入超过约 5.17 秒会截断；本机入口主动拒绝更长视频。项目页面展示了长视频结果，但不能据此认定当前 IC 脚本已经支持整段 15 秒。正式支持 15 秒需要适配帧数、音频 latent 与采样布局，并验收整段输出；当前未声称完成。

### 15 秒兼容方案：重叠窗口

已准备 `tools/plan_h3_2k_windows.py`，对 15 秒、24 FPS 的 360 帧规划 4 个窗口，每个读 124 帧。源帧区间为 `[0,124)`、`[79,203)`、`[157,281)`、`[236,360)`；重叠区保留充足的相同草稿上下文。所有区间均为左闭右开。

逐段运行现有 IC 重生成后，按原始帧号合并，只保留各段负责的时间区间，恢复同一条 24 FPS 时间轴；音频取完整原草稿并按整段时长封装。规划器为每段给出本地保留区间与全局对应帧号，因此不会将重叠帧重复拼入，或把视频缩短到前 5 秒。FastH3 的 362 帧对齐输出也有完整覆盖规划，不丢弃尾部。

CPU 测试已检查 113–362 帧的每一种长度：窗口长度符合上游读取要求，全部输出帧恰好保留一次，相邻窗口至少重叠 24 帧。15 秒和 362 帧版本均为 4 个窗口。测试文件为 `tests/test_h3_2k_windows.py`。

这只是已经验证的分段与时间轴规划。实际视频拆分、模型调用和最终封装现已接入运行入口；15 秒 FFmpeg 时间轴与音频测试通过，完整 15 秒模型推理与接缝画质仍需验收。手动入口和 HTTP worker 已接入该分段处理。后续需检查窗口之间的亮度、纹理与人物连续性；重叠区域可试验融合，但不能仅凭覆盖测试声称无接缝。每次推理仍处理 5 秒档，单卡显存是否够用也尚待模型实测。原生单次处理整段 15 秒的路径仍未适配和验证。

**HTTP：**`8001/v1` 与 `7860` 已切换至完整 H3＋本地 2K 的异步任务服务，模型名为 `minimax-h3-2k`。2K 单独重生成已出片并验证局域网下载，完整参考生成链路正在验收；运行说明与当前状态见 [HTTP 运维文档](h3-2k-http.md)。
