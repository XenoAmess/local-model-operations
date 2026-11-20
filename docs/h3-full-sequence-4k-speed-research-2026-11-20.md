# 14 秒整段 4K 为什么接近八小时，以及可实施的加速路线

2026-11-20，单张 RTX 6000D／SM120。对象是正式 `open-h3-2k` 服务的 Open-H3-Regenerate-2K-IC，BF16 Ref2VA、未合并 IC／HyperFlow／Sharp LoRA、up3 三步及原版 36 层 FP32 VAE。本文最初记录只读研究；下文保留当时观察与候选取舍。随后按用户授权，在 S48 完整交付后完成了 GPU 短测，正式后端保持不变。

**后续实测结论：S48 已完成，实际耗时约 8 小时 7 分钟。cuDNN 仅快约 0.4%，FlashInfer 通用 FA2 约慢 3.6% 且超长 HND 路径数值检查失败；继续保留现用内核。** 详见[完整视频与短测](h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)。以下原始研究不代表候选已采用，也不代表稀疏路线已获画质验收。

研究记录、依赖版本、源码提交与文件摘要见[机器可读记录](../deployments/video-generation/deployment/minimax-h3/full-sequence-speed-research-20261120.json)。队列管理、维护状态及原 124 帧分流边界见[调用管理文档](video-queue-management.md)。

## 本机证据：主要时间花在全局注意力

S48 海边蝴蝶源片是 336 帧／24 FPS／14 秒。为覆盖完整 VAE 时间网格，内部处理 345 帧、102 个 latent 帧，最终裁回 336 帧。实际拼合文字、参考草稿、音频占位和目标视频后，每层有 **949,232 token**，56 个注意力头、每头 128 维。残差宽度为 5376，Q/K/V 投影宽度才是 7168。

| 对照 | 已有实测或观测 | 能说明什么 |
| --- | --- | --- |
| 原 5 秒、120 帧、原生 4K 的 S41 | up3 采样 3971.7 秒，36L 解码 363 秒 | 同为 4K 时，原路线采样已经约 66 分钟，不能拿 768p Omni 或 2K 的时间直接对比 |
| 历史单窗口 4K 注意力基准 | 345,843 token，一次完整注意力约 23.85 秒 | 是注意力调用成绩，不是全片时间 |
| 新整段容量准入 | 960,000 个 K/V、16,384 个 Q，一次约 3.155 秒 | 只证明一次长 K/V 调用的容量和有限输出，不等于全视频或全部索引正确性验收 |
| S48 实际第 5→10 层 | 933.34 秒，约 186.67 秒／层 | 50 层×3 步外推采样约 7.78 小时，还要加解码和封装；不是已经完成的全片计时 |

旧 S41 日志在执行机器 `outputs/video-queue/jobs/video_gen_90f5a5d1b73048d18e73facd5add3068/worker.log`；S48 与准入数据索引见[整段验收记录](../deployments/video-generation/deployment/video-queue/full-sequence-validation.json)及[已有 4K 注意力实测](../deployments/video-generation/deployment/framework-comparison-20261117/4k-attention-concurrency.json)。原始媒体和大日志不提交 Git。

密集注意力的主要计算随序列长度平方增长：

```text
序列长度比 = 949232 / 345843 ≈ 2.745
注意力计算量比 ≈ 2.745² = 7.53
每层查询批数 = ceil(949232 / 16384) = 58
准入调用粗略外推 = 58 × 3.155 ≈ 183 秒／层
实际近期层耗时 ≈ 187 秒／层
```

这几项独立证据吻合，说明主要问题是近百万 token 的密集全局注意力计算。查询分批只是减少显存，每批仍看全部 K/V，没有减少这些配对运算；它也没有重新变成独立时间窗口。不能据此严格断言本次全片注意力占比，因为尚未对正在运行的 worker 做侵入式逐算子 profiling。

只读抽样显示 GPU 利用率 100%、约 63 GiB 已用、P0、PCIe 5.0×16、无时钟限制原因、温度约 52℃。功耗约 284 W／600 W 不足以证明限功耗或 Tensor Core 吞吐已达上限；SM120 内核实现仍值得测。没有证据表明是 GPU 空闲、内存交换或冷启动造成八小时。主内存里有大量可回收文件缓存，不能把 cgroup 总量误当成全部不可回收匿名内存。

## 候选优先级与真正的接入限制

| 顺序 | 候选 | 保留完整密集注意力吗 | 本次查到的关键事实 | 当前结论 |
| --- | --- | --- | --- | --- |
| 1 | cuDNN BF16 SDPA；必要时验证 SM120 FROST 路径 | 是 | 官方支持 BF16、非因果、D128；SM120 有专用实现，TE 当前优先尝试 cuDNN | 优先验证，不能从选择顺序推断本机一定更快 |
| 2 | FlashInfer 通用 FA2 `single_prefill_with_kv_cache` | 是 | 已安装；接口支持 `causal=False`、HND K/V 及不同 Q/K 长度 | 很适合当前查询分批接口；必须测真实长 K/V，不是换库名就有收益 |
| 3 | FlashAttention-4 CuTe SM120 | 是 | 当前有 SM120 分派，但继承 SM80 MMA 路径和约 99 KiB SMEM 约束 | 可作对照，不套用 B200 的 FA4 性能宣传 |
| 独立画质候选 | NVlabs SoL-Attn BF16 SM120 | 否，近似部分注意力 | 有 CuTe SM120 与 Triton 路径，支持精确保留条件 K/V | 最值得继续研究的数倍提速方向之一；需要 IC 保护和完整视频对比 |
| 独立画质候选 | SGLang SubBlock BF16 SM120 | 否，选择部分块 | H3 专用、SM120 FlashInfer blk64；默认前 10 步不稀疏 | up3 只有 3 步，默认配置完全不会加速，必须重新设计三步调度 |

密集后端保留的是同一个数学注意力算子。不同内核的累加、softmax 和舍入顺序可能不同，**数学等价不代表逐元素相同，更不代表无需画质验收**。现有“同运算结果”要求继续约束正式替换，不能把 BF16 三个字当成位级一致证明。

依据：[NVIDIA TE 后端选择](https://docs.nvidia.com/deeplearning/transformer-engine/examples/attention/attention.html)、[cuDNN SDPA](https://docs.nvidia.com/cudnn/operations/Attention/)、[SM120 FROST／AOT 说明](https://docs.nvidia.com/cudnn/operations/Attention/aot_sm120_attention)、[FlashInfer 通用接口](https://github.com/flashinfer-ai/flashinfer/blob/b966a5b24c6c942247000abd335c9a3cff83db6a/flashinfer/prefill.py)、[FA4 SM120 实现](https://github.com/Dao-AILab/flash-attention/blob/dbabcc788590e793eee11566d7253906187e612e/flash_attn/cute/flash_fwd_sm120.py)。最新文档可能要求比本机 cuDNN 9.20 更新的版本，应在隔离候选环境确认，不能直接升级正在运行 worker 的环境。

### FlashInfer 的新 H3 专用密集内核不能直接用

当前 `minimax_h3_dense_attention` 确实支持 SM120、BF16、56 头和 D128，但源码限定 **1≤tokens≤131072**，要求 Q/K/V 等长、连续 `[tokens,7168]`。本次是 949,232 token，不能直接接入。它还把 Q 预乘 BF16 化的缩放常数，与当前 SDPA 的缩放／舍入顺序不同。

把 95 万 token 切成多个 13 万并各自调用，会丢失分段之间的 K/V，是改变注意力的方案。即使分 K/V 后用在线 softmax 合并可以恢复完整数学算子，也需要内核输出 LSE／部分和等合同，这个公开函数没有提供，不能简单拼接输出冒充等价。[固定版本源码](https://github.com/flashinfer-ai/flashinfer/blob/b966a5b24c6c942247000abd335c9a3cff83db6a/flashinfer/diffusion_ops/cake_minimax_h3_dense_attention.py)

### SoL-Attn：保留整段时间轴，有接入工作和近似误差

官方最新代码已经有 SM120 实现，不能沿用“只支持 B200／H100”的旧结论。其方法在整段序列里选择精算块，并用代理量近似其它块。它可以避免独立时间窗口拼接，但不会保持密集基准的全部运算结果。[官方代码与接口](https://github.com/NVlabs/Sana/tree/cf67a3acad7511acb85053e56a05e5dd24c82ba0/techniques/sparse_backends)、[论文](https://arxiv.org/abs/2607.24027)

本机接入至少有三项工作：

1. 官方接口要求等长、连续 BTHD 的 Q/K/V；当前路径是分批 Q、全长 K/V，不能直接替换函数。可研究逐组注意力头、每组保留完整时间长度，以限制峰值；注意力头独立，但切分投影的 GEMM 形状和 LoRA 实现也要核对。
2. IC 的干净参考、文字和音频占位 K/V 应保持精确；条件自身的查询行也要走密集路径，避免参考反馈先被近似。官方 sink 只保证相应 K/V，不能自动代替密集条件查询行。
3. `strict` 验证必须确认实际调用了候选内核，记录精算块比例和 fallback；不能把悄悄回退密集的成功运行报告成加速。

社区 [r-vage 的 H3 集成](https://github.com/r-vage/ComfyUI-sol-attn/tree/69d2e4009313e5cc3a1a70ab092ed6bb54fd5cd3) 已提供 `exact_kv_and_rows`、指定密集层、按采样阶段切换等接入参考。它的公开微基准主要在 4K–65K token，另有低分辨率 H3 成片对照；均不能推成我们的 95 万 token、14 秒原生 4K 成绩。默认“保留条件 K/V”与“同时保留条件查询行”也应区分。

### SubBlock：三步调度、条件布局和路由内存都要处理

[SGLang 当前实现](https://github.com/sgl-project/sglang/blob/f6726b4caa0ea8215aa12acae3f00847cad4f97a/python/sglang/multimodal_gen/runtime/layers/attention/backends/subblock_sparse_attn.py) 的默认 `skip_first_steps=10` 来自另一套 H3 采样实验。不能用在 up3 后仍期待加速；直接改成零则会把全部去噪交给近似注意力，也不能保证质量。

源码用分头控制每次路由分数和索引的内存上限，支持不同 Q/K 长度。以全长 Q/K、64-token 块估算，一个头约 2.20 亿块对，FP32 路由分数约 0.82 GiB；56 头一次物化接近 46 GiB，所以必须保持路由预算，不能只计算稀疏注意力本体的显存。沿用当前分批 Q 可降低单次路由规模，但布局、绝对查询偏移、条件行掩码及索引正确性需要适配。

可以研究只在后两步开启保守稀疏，先保留第一步全密集。假设后两步各加速三倍，三步合计理论上是 `3/(1+1/3+1/3)=1.8×`，而不是整片三倍；尚未包含路由和解码。该数字只是算术情景，不是性能预测。

## 哪些办法不值得作为本轮主攻

- **再改 Python 服务、排队、冷启动或 CPU 搬运：**这些不会消除 `N²`。已有权重搬运优化继续保留，但不能期待靠它将八小时降至一小时。
- **再加内存或更激进卸载：**有助容量，通常增加传输；当前主要耗时是显卡计算，不能当成提速按钮。保留 80／88 GiB 限制。
- **并发跑两条 4K：**已有真实尺寸注意力对照显示吞吐没有收益；只会争用当前卡，不并发启动完整模型。
- **只换 24 层 VAE：**会改变用户指定的原版 36L 解码器；即使解码免费，也省不掉接近八小时的采样。
- **SageAttention 自动 FP8 PV：**上游有 SM120＋H3 长于约 160K token 后输出噪声的未关闭报告，我们接近 950K。报告环境和版本与本机不完全一致，不能断言所有新内核都有该问题，但必须做长序列验证后再考虑。[问题 #388](https://github.com/thu-ml/SageAttention/issues/388)
- **MXFP8／NVFP4、减少三步、合并 LoRA、缓存跨步输出：**都可能改变结果；三步本来就少，缓存方案的收益和误差更不能从 50 步模型外推。
- **整段 2K 后普通超分到 4K：**可以保留完整时间轴并明显减少扩散 token，但不是原生 4K IC 重生成；只可作为另一个质量档，不替换当前请求。

NVlabs 非 IC 的 B200 优化拆分中，密集内核／编译是 87.26→81.38 秒，加入稀疏后到 41.38 秒；最终 22.45 秒还用了 FP8、CUDA graphs 和 24L 快速 VAE。该公开实验没有测本机硬件、当前 IC、14 秒或相同解码配置，不能把“3.9×”作为本站保证。[官方方法和计时范围](https://nvlabs.github.io/Sana/Open-H3-Regenerate-2K/)

## 补充：网上有没有 H3 的实际画质与速度经验？

2026-11-20 继续搜索后，找到了更直接的公开记录。它们支持把 cuDNN 列为优先验证的密集候选，但没有建立“cuDNN 或 FlashInfer 的 BF16 成片画质必然高于当前 FlashAttention”的排名。

| 原始资料 | 实际报告 | 对本机的含义和限制 |
| --- | --- | --- |
| [FastVideo 官方 H3 cuDNN 选项](https://haoailab.com/FastVideo/inference/optimizations/#cudnn-sdpa-for-h3-dense-attention-opt-in) | BF16 输入／FP32 softmax 与累加／BF16 输出；37.7K、109K 单算子与 FA4 差异在计时噪声内，一个 GB200 的模型前向快 2.2%；明确不承诺精确一致 | 有正式可选实现，收益可能很小；不是 SM120／950K IC 成绩。该环境变量控制 FastVideo 自己的 H3 路径，不会自动改变本站独立 IC worker |
| [两台 DGX Spark 的 H3 作者实测](https://github.com/joeynyc/MiniMax-H3-2x-DGX-Spark/blob/main/docs/RESULTS.md) | 768×448／20 步预热请求，Torch SDPA eager 64.226 秒，cuDNN eager 52.872 秒，延迟少约 17.7%。另一个 1344×768／50 步的 cuDNN＋局部编译对照，作者报告画面相近，视频 SSIM 0.9134／PSNR 28.56 dB，但像素不同 | 两台 SM121、FL2VA／vLLM-Omni 配方；不能照搬到单张 SM120 BF16 IC。高分辨率成绩混入编译，不能全部归因于 cuDNN；未独立取得该作者成片复核 |
| [RTX 5070 Ti／SM120 的 H3 算子实测](https://github.com/jayleaton/minimax-h3-tensorfold-rtx/blob/main/docs/RESULTS.md) | H56×D128、39,936 token：cuDNN BF16 相对 FP32 参考的余弦相似度 0.999997，耗时 478 ms；量化候选更快但数值偏差更大 | 说明该 BF16 密集算子在一个 H3 形状下误差很小；没有与本机现用 FlashAttention 做同条件完整视频画质比较，不能据此称 cuDNN 画质第一 |

SSIM、PSNR、余弦相似度在这些对照中衡量的是与某个参考输出的接近程度，**不是用户审美或最终画质的优劣排名**。同种子生成画面不同，也不能仅凭这一点判定谁更差。NVIDIA Open-H3 页面把 cuDNN＋编译列为 “Lossless kernels”，与 FastVideo 的“不承诺 exact parity”应分别理解：前者是该报告的优化分类，不能替代本站逐元素一致验收。

因此目前有外部经验支持“密集 cuDNN 可以实际使用并可能提速”，没有找到足够匹配的公开证据支持“换它一定画质更好／更差”，也没有找到本站 95 万 token、14 秒 4K IC、原版 36L 条件下 cuDNN、FlashInfer FA2 与现用 FlashAttention 的公平完整视频三方对照。正式选择仍应以本机预热后速度、数值及成片验收为准。

## 验证步骤与采用标准

用户已要求实际快速对比 cuDNN、FlashInfer 通用 BF16 与现用内核，随后明确要求**等 S48 完整成片并交付后再测**。该短测已在成功交付后的维护边界完成，后续队列已恢复；结果见[最新实测](h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)。没有暂停、冻结或重跑 S48，也没有自动替换正式后端。[待测安排](../deployments/video-generation/deployment/video-queue/dense-kernel-quick-benchmark-plan.json)

当前 S48 密集整段继续作为参考，完成后先做完整 HTTP 下载、SHA、帧数／音轨／解码和画面检查。候选 GPU 验证只在安全任务边界进行，不与当前 worker 争卡；不自动恢复此前已取消的框架基准。

1. **先检查候选合同。**固定依赖和源码版本，明确实际选中的内核、BF16／FP32 累加、无稀疏／无量化、Q/K 长度、布局和工作区。禁止不知情的 backend fallback。
2. **先做代表性调用。**同一输入比较当前强制 Flash SDPA、cuDNN、FlashInfer FA2，再测 FA4；使用 16,384 Q×949,232 K/V、56×128 形状及真实 strides，预热后计时，记录显存和主内存。
3. **检查长索引正确性。**加入序列首尾特殊 K/V、多个位置的查询样本，使用稳定 FP32 分块参考核对。有限输出只是必要条件；本次全 Q/K/V 单份有约 68 亿元素，必须核对跨 32 位偏移边界，不能只看有没有异常。
4. **再比较真实层和完整视频。**保持输入、caption、seed、up3、未合并 LoRA、36L decoder；位级比较通过才可按“同结果”替换。存在舍入差异的密集候选、稀疏候选分别报告误差与全片画质，不能混为一类。
5. **稀疏候选另建实验配置。**先测试条件保护、三步调度与路由容量，再用 S48 检查运动速度、蝴蝶振翅、参考保持、细节和闪烁；重点查看原接缝附近及首中尾，同时审看全片。不得恢复独立时间片生成后拼接。

最终建议是保留现有正式 API 和队列，优先优化 IC 的注意力执行；无需为了尝试一个内核把 Omni 从 FastVideo 换到 SGLang。若密集后端收益有限，下一项有实质意义的研究是**保留完整时间轴、保护 IC 条件的 BF16 稀疏模式**，其画质验收与是否采用单独记录。目前没有已验证的“零画质变化、数倍加速”结果。
