# Open-H3 长视频接缝：现成实现与整段重生成路线

后续实施：用户已授权队列 API 与完整时间轴 IC 候选部署，S48 已完成完整 14 秒原生 4K 的 LAN／完整解码与抽帧验收，见[成片与短测结果](h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)。4K 严格以原单窗口 124 帧划分，等于上限保留旧路线，大于上限才用整段；最新状态见[管理与使用说明](video-queue-management.md)和[验收记录](../deployments/video-generation/deployment/video-queue/full-sequence-validation.json)。以下为此前研究及候选取舍记录。

2026-11-20。用户目标是改善接缝，尽量一次重生成完整视频，可以接受性能损失。本文优先研究 14 秒源片的整段 IC 重生成，再比较无法整段执行时的替代办法。只进行了网络搜索、八个社区仓库及 ComfyUI 核心源码核查、标准库帧数／内存计算；未安装候选、下载新模型权重、运行 GPU 推理或调整线上服务。

## 结论与优先级

**有现成代码值得采用，但没有查到与本机“单张约 83 GiB 显卡、完整 IC／BF16、up3、原版 36L FP32 VAE”一致且已验收的 14 秒原生 4K 即插即用方案。** 搜索范围与固定版本列在文末，不把未找到等同于不存在。

1. **首选：同一套 IC 权重整段去噪。** 保持完整时间轴、整段参考、完整注意力上下文，通过计算和存储调度降低峰值。允许变慢后，这条路线更符合目标；目前需要适配，尚未在本机验证。
2. **次选：整段共享 latent／噪声，每一步融合窗口结果。** Sandpies 已有支持 IC 的实现，最值得借鉴。仍然分窗口前向，不能称为全长全局注意力，但没有“各段全部生成完才拼接”的固定硬切。
3. 最后才考虑独立片段的选缝、多频段融合或交叉淡化；这些只能缓解已经产生的差异，不能恢复缺失的全片上下文。

“整段一次生成”指不拆成多个独立采样任务，**不是把 up3 三步去噪减成一次前向**。原有三步可以保留，VAE 原生内部小块编解码也可以保留。

## 为什么当前方案容易有接缝

现有 `plan_h3_2k_windows.py` 对 336 帧规划四个 124 帧窗口，起点为 0、71、141、212；`h3_2k_worker.py::stitch_command` 在重叠区中点裁切后 concat，最终接点约为 4.042、7.000、9.917 秒。重叠素材存在，但没有逐步共享生成状态，也没有最终渐变融合。由此推断：两段对同一时刻的小纹理、表情或颜色作出不同重建，硬切会把差异直接显露出来；尚未对具体失败素材作逐帧归因。

还需排查两个来源：各窗口相同 seed 不等于同一全局时刻具有相同噪声；独立从非 17 帧相位起点重新编码，也可能改变重叠区 VAE latent。不能只增加重叠长度就承诺解决。[当前窗口规划](../deployments/video-generation/tools/plan_h3_2k_windows.py)、[当前拼接](../deployments/video-generation/tools/h3_2k_worker.py)、[批处理入口](../deployments/video-generation/tools/h3_2k_batch_worker.py)

## 找到的现成方案

| 实现 | 实际做法 | 是否整段／适合当前 IC |
| --- | --- | --- |
| NVlabs 原版 Open-H3 | 官方展示整段 15 秒／360 帧／2K，原生高分辨率去噪 | 真正整段的公开依据；展示属于非 IC，不能证明当前 IC 的 14 秒 4K |
| Sandpies H3 Video Upsampler | `stepped`：共享全片噪声及状态，每个 sigma 步汇总所有时间／空间窗口结果 | **已有 IC 代码路径，最合适的窗口备选**；每次前向仍只见窗口 |
| ComfyUI 核心 H3 Context Windows | 一个采样轨迹内执行重叠窗口，融合预测；H3 专用时间网格，默认 pyramid、FreeNoise | 核心已有实现；不是全长密集注意力，当前 Sandpies 在 IC 下主动回退 stepped |
| Slmonker OpenH3Regenerate2KIC | Prepare Draft 可选择 124–362 帧，步进 17；动态匹配音频占位 | 有长输入准备代码；不是这台机器完整长片推理的验证证据 |
| ehsrzv H3 Temporal Sampler | 全长噪声切片、低运动边界、多频段／自适应融合、可选 seam lock | 有可借鉴代码；**实际逐段完成所有去噪步后融合**，不是逐步同步 |
| Olm Open-H3 | 最多 124 帧默认窗口，长片独立窗口 | README 明确没有时间融合，不作为本次接缝方案 |
| ThomasUK888 IC | 全秩 IC LoRA 映射、FFN 分块、原始草稿 latent 切片，切片偏移要求 17 帧对齐 | 可借鉴相位和映射；本次所读入口准备 113–124 帧，没有证明整段 14 秒 |
| DaSiWa Hi-Res Regenerate | 共享空间噪声、每步空间预测融合；时间分块按 H3 相位，支持边界条件 | 主要是旧版重生成配方，不能当成 IC 的已验证替代 |

### 1. 真正整段：官方已经展示过，但版本与资源必须分开

NVlabs 项目页的旧版部分有 15 秒 2K 单次处理展示，也介绍原生 4K 输出。IC 部分则强调低分辨率草稿始终作为干净参考，减少五官、嘴形与文字漂移。这说明“消除独立采样边界”的方向有依据，但不能把旧版的时长展示、IC 的 4K 示例和 B200 的速度拼成当前单卡的能力证明。[NVlabs 原始项目页](https://nvlabs.github.io/Sana/Open-H3-Regenerate-2K/)

Slmonker 的节点源码已允许 `frame_count=124..362`、步长 17，说明社区不都把 IC 的输入准备写死在 124 帧。但其 `_fit_silence` 对更长音频采用零填充，不能仅凭该实现认定任意时长的模型内部音频语义正确。长片仍需核对完整 conditioning、位置编码和输出，不能只看控件上限。[Slmonker 节点源码](https://github.com/slmonker/ComfyUI-OpenH3Regenerate2KIC/blob/a85bd9664a752637c5ec88bf4b1930b4688fc251/nodes.py)

可借鉴的显存办法包括密集注意力按 head 分组、FFN 按 token 分块和流式输出。Sandpies 的 `head_chunked_attention` 保留完整序列，但接收的已经是完整 Q/K/V；**它本身不会消除整段 QKV 的驻留成本**。因此这不是一个打开即能保证 14 秒 4K 跑通的选项。当前服务已经有权重卸载和 FFN 分块；还需要处理投影、归一化／RoPE 临时张量、残差和 VAE 像素峰值。分组改变内核形状时也不能未经验证称为位级相同。[密集 head 分组实现](https://github.com/sandpies/ComfyUI-H3-Video-Upsampler/blob/44db226f25f55955b3d3362a10c4de530711cd1b/sparse_attn.py#L273)

### 2. 最值得借鉴的窗口备选：Sandpies stepped

核对的是 GitHub `44db226f25f55955b3d3362a10c4de530711cd1b` 与作者 HF 镜像 `667ef0efd825ac0645b81e85c1786d8f852254aa`；三个核心 Python 文件逐字节一致。

`redraw_stepped` 先维护一条完整 latent 时间轴和全长噪声；循环顺序是“去噪步 → 时间窗口／空间 tile → 加权合并 → 下一步”。`_redraw_ic` 把逐段草稿参考和 IC 模型接入同一后端，因此不是仅靠旧版标题推断支持 IC。相邻区域在下一步开始前已经共享结果，机制上比当前独立生成后硬切更直接。[逐步合并源码](https://github.com/sandpies/ComfyUI-H3-Video-Upsampler/blob/44db226f25f55955b3d3362a10c4de530711cd1b/tiled_upsampler.py#L2096)、[IC 调用路径](https://github.com/sandpies/ComfyUI-H3-Video-Upsampler/blob/44db226f25f55955b3d3362a10c4de530711cd1b/video_upsampler.py#L850)

重要限制：共享状态不等于每次前向能看见整段，仍可能有局部结构分歧或融合重影。代码还可能在容量不足时从 `stepped` 回落为 `crossfade`；`chunking=false` 也有预算触发的重新分段，不能只看用户配置判断实际路径。[实际分支](https://github.com/sandpies/ComfyUI-H3-Video-Upsampler/blob/44db226f25f55955b3d3362a10c4de530711cd1b/tiled_upsampler.py#L2462)

作者默认示例用 INT8 基座、压缩 IC LoRA、可选快速 VAE／稀疏注意力，音频条件也与本服务不同。**不能整包照搬并称为当前质量设置。** 可取其调度与融合方法，保留本机完整权重、BF16、up3、密集注意力和原版解码器，另做实际验收。其算法代码为 MIT；模型沿用各自许可。[作者说明](https://github.com/sandpies/ComfyUI-H3-Video-Upsampler#two-ways-to-re-draw-method)

### 3. 更成熟的公共基础：ComfyUI 核心 H3 Context Windows

PR #17425 已合入核心。H3 专用节点默认 124 帧上下文、39 帧重叠，窗口按 17 帧块起步，提供 pyramid 融合和 FreeNoise。其价值是统一采样轨迹与正确的多模态时间映射，不是将局部窗口变成全局注意力。[合入提交](https://github.com/Comfy-Org/ComfyUI/commit/6651247a8b50cefd1436c834f704bdf7767722e9)、[当前节点源码](https://github.com/Comfy-Org/ComfyUI/blob/4ee8e523ba01b0335a5cd20ce9c1e2b684f69521/comfy_extras/nodes_context_windows.py#L139)

Sandpies 的 `windowed` 模式在发现 IC 条件时明确退回 `stepped`。因此“ComfyUI 核心支持 H3 窗口”不能直接推成“此 IC 插件已通过该窗口路径”。两者适配与画质验证仍是独立工作。普通 H3 长视频的社区问题也不能自动套用为 IC 重生成的已证缺陷。

### 4. 没有选作主路线的实现与反例

ehsrzv 提供实用的边界选择和融合算法。但该版本类注释称 MultiDiffusion-style，实际 `sample()` 循环是逐个 segment 调用完整 `sigmas`，然后 `_merge_next`，没有每个 sigma 后回写全部窗口的外层循环。README／注释／实际代码存在差别，应按代码分级。它是改善独立窗口接缝的候选，不能作为真正整段方案。[固定版本源码](https://github.com/ehsrzv/comfyui-h3_temporal_sampler/blob/7d39f8eba7230e72548ad38ffc0392977c4945eb/h3_temporal_sampler.py#L621)

Olm 明说长片独立窗口且无 temporal blending；换成它不能直接解决当前问题。Thomas 的草稿 latent 相位检查可取，但完整工作流的时间范围仍须区分。[Olm 使用说明](https://github.com/o-l-l-i/ComfyUI-Olm-Open-H3-Regenerate-2K#usage)、[Thomas IC 节点说明](https://github.com/ThomasUK888/ComfyUI-OpenH3-Regenerate-IC#open-h3-ic-conditioning)

MMH3Tools 记录过同一 362 帧源片：整段正确，分段后偏离；将上一段生成的高分辨率头帧硬锁，与低分辨率参考冲突，是作者尚未验证的原因假设。它不是本机 IC 的实验，也不是“关闭锁定已修复”的证据，但说明不能把 seam lock 当成必然改进。[作者问题记录 §6](https://github.com/ckinpdx/ComfyUI-MMH3Tools/blob/5bf2f5bdef5040aeb71cbc334b10da478c9cef83/docs/regenerate-2k.md#6-open-divergence-past-one-chunk)

DaSiWa 的空间逐步融合和相位规划有借鉴价值；作者同时明确 chunked upscale 的卷积／归一化／上下文可能造成差异，且没有承诺解决曝光跳变。RDH 的旧版工作流支持保留完整 latent 后独立解码，但其非 IC、量化及稀疏配置的成绩不作为本机同效果证明。[DaSiWa 边界说明](https://github.com/darksidewalker/ComfyUI-DaSiWa-Nodes/blob/dd85a39f1ed0ffded50c0ac3fe38566126c31bab/docs/minimax_h3_tiled_upscale.md)、[RDH 工作流](https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate/tree/46ff77854417ed6d6f99d10ee4430faa7e9e72bf)

## 14 秒整段的帧数修正与容量判断

上一份报告直接按 336 帧编码得到 97 个 latent 帧计算了预算，遗漏了**解码后必须覆盖全部 336 帧**。本机 VAE 的合法时间网格是 `17n+5` 像素帧对应 `5n+2` latent 帧。97 个 latent 帧只覆盖 328 帧；应将源片末尾补到 **345 帧／102 个 latent 帧**，整段处理后裁回 336 帧，保留全部 14 秒内容。不能为了网格把源片缩到 328 帧。

这是读取本机 Diffusers `AutoencoderKLMiniMaxH3._encode/_decode` 并按其几何规则计算的结果，不是实际模型输出测试。原报告已同步修正。4K 对齐 3840×2176、参考 1344×768 时，不含文字／音频：目标 832,320 token、参考 102,816 token；残差 hidden 宽度为 5376，单份 BF16 约 9.36 GiB；Q/K/V 投影宽度为 7168，单份约 12.49 GiB，QKV 合计约 **37.46 GiB**。它们只是部分张量，不能据此断言约 83 GiB 显存能跑通；345 帧的单份 FP32 RGB 像素约 32.22 GiB 也要求控制解码输出峰值。

整段密集注意力的计算规模约为一个 124 帧窗口的 `(102/37)^2≈7.60` 倍、四窗口合计的约 **1.90 倍**；这只是注意力项估算，不是端到端时间。省掉重复加载和重叠工作可能抵消一部分成本。用户已接受性能损失，因此该估算不再是淘汰整段路线的理由。[修正后的整段容量研究](h3-single-pass-14s-4k-feasibility-2026-11-20.md)

## 建议的实施与验收顺序（本轮未执行）

1. 先适配同模型全长输入、345 帧时间网格、完整参考／目标布局及长度匹配的干净音频占位。2K 与 4K 的容量分别判断，不能用整段 2K 成功代替整段 4K 验收。
2. 优先减少驻留中间量：已有 FFN 分块与权重卸载继续复用；密集注意力的 query／head 计算分组必须保留完整 K/V 时间范围，再考虑受预算约束的激活搬运。保留原版 36L 的计算与原生块边界，以流式输出压低像素峰值。慢可以接受，但不能越过 80／88 GiB 主内存限制。
3. 真正整段路径无法在本机满足容量时，再研究移植 Sandpies 的 IC `stepped`，使用尽量少、尽量大的窗口，统一噪声与 VAE 时间相位；禁止静默回落为独立片段硬切。使用的是同一三步调度，增加的是窗口前向次数。
4. 短片先核对数值与视觉变化，长片检查原三个接点及全片运动、脸、文字、亮度、音轨和准确帧数；记录实际去噪范围、窗口数、峰值、耗时及 fallback。以源片作依据，不仅检查两个生成片段是否互相接得上。

验收不能只看接点瞬间：淡化重影、脸逐渐变形和接点后数十帧的漂移都要检查。真正整段去噪能消除独立窗口的硬切来源，仍不能保证消除源片或 VAE 引入的全部闪烁。**本轮交付是研究与候选排序，线上仍运行原配置，尚未宣布接缝已修复。**

## 补充：显存不足时，使用系统内存保留整段上下文

用户进一步询问分步卸载及内存参与计算。**可以把主内存作为权重和中间张量的暂存区，由 GPU 分批执行完整序列；显存不足不等于必须拆成独立视频片段。** 但“内存暂存”和“CPU 执行模型运算”是两种不同办法，后者也可研究，通常先保留 GPU 主算。

本机当前 IC 已有 `readonly_block_offload`：完整 BF16 权重保留在 CPU，每次把一个 transformer block 传上 GPU，完成后恢复 CPU 存储；FFN 也已有 2048-token 分块。新增工作应针对长序列**激活／中间结果**和解码输出，不能把现有权重卸载再次当成新功能。[现有只读权重卸载](../deployments/video-generation/tools/h3_ic_exact.py)、[运行入口](../deployments/video-generation/tools/h3_ic_runtime.py)

| 办法 | 对整段 14 秒的帮助 | 代价／适配边界 |
| --- | --- | --- |
| 更细粒度的权重卸载 | 继续减少当前层以外的 GPU 权重占用 | 已有逐 block 卸载，进一步收益要量测；不能解决当前算子自身工作集过大的问题 |
| 激活暂存 CPU | 把暂时不用的残差、投影中间量、输出暂存内存，需要时取回 | 增加 PCIe 传输；需要修改推理张量生命周期，普通 group-offload 开关不自动实现 |
| 全长注意力分批计算 | 分批生成 Q、投影及输出，每批 query 仍访问全片 K/V；必要时再研究 K/V 分页 | 保持整段上下文；若 K/V 也分批，必须正确维护跨块 softmax，不能各块独立归一化后简单拼接；可能显著变慢 |
| 36L VAE 流式输出 | 保持原生解码块和重叠合成顺序，完成的像素尽早转 CPU／写文件并释放 | 避免约 32.22 GiB 的整段 FP32 像素常驻 GPU，也不能在 CPU 无限制积累同样缓冲；应测解码一致性 |
| NVMe 权重分层存储 | 主内存也受限时，按需映射／读取权重，减少长期驻留 | 有现成框架接口但本机 IC 尚未适配；增加磁盘 I/O，不直接解决单次算子激活峰值 |
| 部分模型改用 CPU 运算 | CPU 可实际承担部分投影、层或 VAE 计算 | 需核对 CPU 内核、精度及完整耗时；暂不优先把全片密集注意力搬到 CPU |

Diffusers 已提供 block／leaf 级权重卸载和 `offload_to_disk_path`，说明权重存储分层有成熟基础；其文档同时说明模型兼容性及 CPU 内存代价。异步预取可能增加锁页内存，不能为追求传输重叠而突破本机预算，也不能把这些权重接口当作自动的激活分页器。[Diffusers 官方内存与卸载说明](https://huggingface.co/docs/diffusers/main/en/optimization/memory#group-offloading)

FlashAttention 的分块／在线归一化提供保持完整密集注意力的算法依据，但论文中的 GPU HBM／SRAM 分块**不是现成的本机 CPU-RAM 分页实现**。迁移到 GPU／主内存协作仍需工程实现与验证。[FlashAttention 原论文](https://arxiv.org/abs/2205.14135)

本机主内存约 122 GiB，推理上限仍为 80 GiB、聚合 88 GiB；CPU 权重、激活暂存、锁页和进程缓冲共用这些额度，不能再把 80 GiB 全部算成可新增的激活空间。单纯保持 dtype 的 CPU↔GPU 拷贝不需要损失精度；分组计算若改变浮点累加顺序／内核形状，则仍须核对数值和实际画面，不能提前称为逐位相同。

因此后续优先研究**完整 IC 时间轴＋有界激活暂存／全长注意力分批＋原版 VAE 流式输出**，允许用额外搬运换取容量；仍不能仅凭内存总量保证 14 秒原生 4K 一定跑通。本次仅补充研究，未启用新卸载策略或模型测试。

## 源码范围与版本

| 仓库／来源 | 本次固定版本 |
| --- | --- |
| Sandpies H3 Video Upsampler GitHub／HF | `44db226f25f55955b3d3362a10c4de530711cd1b`／`667ef0efd825ac0645b81e85c1786d8f852254aa` |
| ComfyUI 核心 | `4ee8e523ba01b0335a5cd20ce9c1e2b684f69521`；H3 窗口合入 `6651247a8b50cefd1436c834f704bdf7767722e9` |
| Slmonker IC | `a85bd9664a752637c5ec88bf4b1930b4688fc251` |
| ehsrzv temporal sampler | `7d39f8eba7230e72548ad38ffc0392977c4945eb` |
| Olm | `29e5ca9680648797011c4ddc06d38b7f04f1f78d` |
| ThomasUK888 IC | `3efcc7c769b5ae3d82e7a8034d1d16f87022a9d2` |
| MMH3Tools | `5bf2f5bdef5040aeb71cbc334b10da478c9cef83` |
| DaSiWa | `dd85a39f1ed0ffded50c0ac3fe38566126c31bab` |
| RDH | `46ff77854417ed6d6f99d10ee4430faa7e9e72bf` |

搜索覆盖 Open-H3／IC 的 single pass、15s／360f、overlap、noise、chunk、seam、stepped、windowed、offload；第三方目录只用于发现项目，技术结论回到作者源码。未运行这些外部项目。核查位置、SHA-256 和计算结果见[脱敏研究记录](../deployments/video-generation/deployment/minimax-h3/seam-research-sources-20261120.json)。
