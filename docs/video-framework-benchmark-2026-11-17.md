# H3 框架性能实测、两个 Strata 与4K并发

最终选型（用户已确认）：正式 Omni 继续 FastVideo；2K／4K 保留当前优化 IC 后端。全部调研入口见[研究索引](video-framework-research-index-2026-11-17.md)，另见[FastVideo／SGLang 全面对比](fastvideo-vs-sglang-2026-11-17.md)与[PDD／注意力实现说明](h3-pdd-attention-implementation-2026-11-17.md)。本次文档整理没有新增推理或恢复下述已取消的稳态补测。

2026-11-17，RTX6000D（85,651MiB，SM120）。截至19:54 CST：**完整2K对照没有显示Diffusers或Accelerate更快；三条最终latent和全部像素完全一致。FastVideo、SGLang与UniServe均已有完整Omni成片，但公平的预热后量产对照尚未完成，不能断言UniServe量产更慢或最快。两个Strata不支持现有H3入口。**

用户指出量产应比较预热后的连续耗时，这一口径正确；撤回用冷启动总时间判断UniServe不值得推进的结论。追加稳态补测已按用户“不测了，先给现有结论”的最新指令取消。正式8001／8002／7860、GPU队列已恢复，局域网只读状态均200，GPU无实验占用。线上框架未替换，全部关闭开机自启、禁止云端，保留80／88GiB主内存上限。

## 完整IC视频：同运算结果对比

相同5.167秒、124帧输入草稿、caption、seed1234、2560×1440、up3三步、50层DiT、HyperFlow＋Sharp＋未合并IC LoRA，原版36层FP32 tiled VAE。只替换搬运控制器，保留正式优化版的BF16 LoRA计算缓存与2048-token FFN分块。计时含编码、模型加载、去噪与解码落盘；不含HTTP排队、外部窗口切分及最终服务封装。

| 实现 | 完整墙钟 | 相对当前优化版 | 最终latent | 全部解码RGB像素 |
| --- | ---: | ---: | --- | --- |
| 当前优化版，只读CPU存储＋单向H2D | 1498.407秒（24分58秒） | 基准 | 基准 | 基准 |
| Accelerate cpu_offload | 1506.335秒（25分6秒） | 慢0.529% | 逐元素完全相同 | SHA256完全相同 |
| Diffusers group offload，无stream | 1562.786秒（26分3秒） | 慢4.296% | 逐元素完全相同 | SHA256完全相同 |

三条结果均完整解码并核对2560×1440、124帧、24fps。最终latent为[24,37,90,160] BF16，SHA256 `aaf430793662150746d0a77d69fd7d8b1e66bbe1c47f66287ddf2c02d7285fdf`；所有RGB帧SHA256 `5426989348bdbd124dafe3fbb0d4fa9dcd2e7e9b20dbd7c936ec2d42abf33a2a`。基线抽查第0、60、123帧完整；另两条全部像素一致。

每种完整路径一次测量，不能把0.529%的差异视为统计显著。**当前证据支持保留现有优化版，没有观察到替换官方搬运控制器的速度收益。** 三种完整路径最大PyTorch allocated显存均68.80GiB；这是跨全部阶段的计数，不能与历史间隔采样的4K显存直接横比。[完整记录](../deployments/video-generation/deployment/framework-comparison-20261117/ic-complete-verification.json)

## 单block对照与stream未采用项

同一真实block0、正式适配权重；每个实现一次预热、两次测量，中位数如下。两种长度都检查了全部输出元素，均bitwise相同。此表不能替代完整视频计时。

| 搬运控制器 | 174080 tokens，2K长度 | 344064 tokens，4K长度 |
| --- | ---: | ---: |
| 当前优化版 | 7.3476秒 | 26.0977秒 |
| Accelerate | 7.3859秒 | 26.1794秒 |
| Diffusers，无stream | 7.8127秒 | 26.5698秒 |

Diffusers stream＋低CPU内存接入在4096-token检查未通过逐元素一致性，未进入大尺寸和完整视频测试，未采用。原因尚未定位，不据此宣称上游所有stream实现有缺陷。

## Omni完整视频：已完成请求，不作量产排名

相同图片、带音轨参考视频、prompt、seed1234，1344×768、124帧、24fps、8次PDD前向，保留训练用逻辑VSA tile128、稀疏度0.9、参考保留率0.1、BF16 DiT／文本编码器、原版36L FP32 VAE与原生autocast。不是NVFP4、8L decoder、跳步缓存或降低参考分辨率的测试。

SGLang上游设备选择器默认拒绝SM120的H3 VSA，原始准入结果保留。随后加显式实验开关：允许真实SM120使用其VSA内核，将dense token-refiner的FA2 fallback改用SGLang自带SDPA。DiT每次前向保留24层，编译关闭；未改变硬件身份或正式服务。它属于**本地实验适配版**，不能称为上游开箱即用。[补丁](../deployments/video-generation/patches/sglang-h3-sm120-experimental.patch)

| 整套候选部署 | 请求至可下载 | 服务启动另计 | 启动＋第一条 |
| --- | ---: | ---: | ---: |
| 当前FastVideo历史相同任务 | 759.213秒 | 6.007秒 | 765.220秒 |
| SGLang适配，第一次独立启动 | 667.679秒 | 52.183秒 | 719.862秒 |
| SGLang适配，另一次独立启动，显式参考缩放 | 661.582秒 | 52.289秒 | 713.872秒 |
| SGLang同进程重复相同输入 | 613.511秒 | 不重复计 | 条件缓存可能命中，不能当作公平量产成绩 |
| UniServe适配，完整实际请求 | 643.547秒 | 158.467秒 | 802.014秒，仅附列启动成本 |

独立重启且显式 `reference_resize_mode=diffusers` 的MP4与第一条默认请求SHA256完全相同。最初根据通用H3类默认max怀疑缩放不同，随后源码与实测确认**FastH3OmniSamplingParams已经覆盖为diffusers**，撤回该判断。实际图片均为2048×2464。

三条完整MP4均下载、全解码，视频与音轨存在。SGLang抽查帧完整，但由FastVideo基线的全身景别变为面部近景；**任务和画质等价没有证明，数值也非bitwise相同，因此不替换线上。** **冷启动时间只单列，不用于量产排名。** SGLang重复任务613.511秒含缓存条件，不能与UniServe首条643.547秒直接判定稳态胜负。样本少，加载、算子预热、PDD融合、注意力、解码器存储精度与环境不同，不能宣称公平稳态对比已经完成。[显式复测](../deployments/video-generation/deployment/framework-comparison-20261117/sglang-full-video-explicit-reference.json)，[首次与重复请求](../deployments/video-generation/deployment/framework-comparison-20261117/sglang-full-video-adapted.json)

## UniServe：完整成片已跑通，稳态对照未完成

固定UniServe提交d58bee14b46475c690ead7540f9f2bbab7790195；独立构建原生CUDA扩展、Rust HTTP服务和Python worker成功。meta预算约94.69GiB参数，超过本卡83GiB可用显存，直接全常驻不适用。本地实验适配将host-weight组件直接在CPU加载，再用上游原生LayerWeights流送到GPU，避免先全部加载GPU。没有换量化权重或降低生成配置。[候选补丁](../deployments/video-generation/patches/uniserve-h3-cpu-load-experimental.patch)

10层CPU加载流送检查，以及前8层流送、后2层常驻的混合检查：各三次完整前向、一次中断再重开均与GPU常驻输出逐元素相同。完整H3已经实际加载、50层DiT和36层decoder流送成功；这本身不等于完整生成成功。原生quality档使用原版36层VAE，但投影权重存为FP16，区别于正式FP32权重＋FP16 autocast，不能当作同数值结果替代。

| 完整接入检查 | 实际结果 |
| --- | --- |
| 队列深度2 | 自建候选配置不满足每请求3个queue positions；已修正为3 |
| 原预算0.62／0.37 | 文本worker预备工作区1407188992字节超过剩余1096933643字节；调整份额 |
| 预算调整后 | 显存预算通过；发现本地CPU加载适配遗漏后处理常量设备，已修正 |
| 诊断与服务同一父进程 | 父诊断CUDA上下文额外约684MiB，实际CUDA OOM；保留证据，未原样重试 |
| 独立诊断子进程＋预留更多运行空间 | HTTP健康检查成功，实际请求11102 tokens超过8192 profile，扩至11264，不截断 |
| 11264 profile、文本全常驻 | 与DiT实际工作区合计超过本卡容量，保留OOM证据 |
| 文本前16层原生流送，其余34层及vision常驻 | 本地适配已加载并通过服务warmup；静态主存权重上界60.014GiB，给输入和运行时留余量 |
| 同一真实请求的条件容量 | 实际47744行，恢复49152容量后准入通过，8轮去噪及完整成片已完成 |

前三项分别是本地配置／适配问题，不据此宣称上游H3不支持。第四次的OOM已明确定位与调整；11264-token profile的新峰值又超限，因此采用有meta预算和混合小模型一致性检查的16层部分流送。当前候选保持80／88GiB主内存上限，禁止无变化重投。最后一次完整请求643.547秒，服务报告内部推理641.421秒（准备105.717、去噪518.150、解码2.362、编码3.750、收尾11.442秒）。结果1344×768、124帧、24fps，含音轨，完整下载与FFmpeg解码通过；抽查第0、60、123帧完整、角色和场景可辨。其PDD／注意力数值实现与36L decoder投影FP16存储不同，未通过同结果替换验收。[完整结果](../deployments/video-generation/deployment/framework-comparison-20261117/uniserve-full-video-adapted.json)

它的单次请求比SGLang该次661.582秒少约2.7%，比历史FastVideo759.213秒少约15.2%，但**这些不是控制算子预热和素材缓存后的量产结果，不据此判稳态胜负**。用户随后要求先停止测试，稳态补测在完成前取消，不继续优化、不自动部署。[取消记录](../deployments/video-generation/deployment/framework-comparison-20261117/steady-comparison-cancelled.json)

接入过程诊断仅解释本地配置与适配的修复，不等于上游框架整体故障。[工作区记录](../deployments/video-generation/deployment/framework-comparison-20261117/uniserve-native-startup-r2.json)，[后处理记录](../deployments/video-generation/deployment/framework-comparison-20261117/uniserve-native-startup-r3.json)，[OOM记录](../deployments/video-generation/deployment/framework-comparison-20261117/uniserve-native-startup-r4.json)，[HTTP成功与实际准入](../deployments/video-generation/deployment/framework-comparison-20261117/uniserve-native-startup-r5.json)

## Omni稀疏注意力内核

相同保存的BF16 Q/K/V，65536 tokens、56 heads、D128，逻辑tile128拆为64执行，相同10% key集合和两个dense query tiles；一次预热、三次测量。输入SHA256 `3c3ef10be27b2a6fc7f238da578676d1a043bcb2f4d7a780c5d488ca4ff1af42`。不含投影、top-k、gate、加载或解码。

| 内核 | 中位数 | 耗时降低 | 对FastVideo bitwise相同 | RMS差异 |
| --- | ---: | ---: | --- | ---: |
| 当前FastVideo SM120 Triton | 92.479ms | 基准 | 是 | 0 |
| UniServe SM120／FlashInfer | 89.687ms | 3.02% | 否 | 6.22e-5 |
| SGLang Triton descriptor | 90.702ms | 1.92% | 否 | 1.94e-7 |

这些分项百分比不代表整片收益，也未证明画质相同或下降；不满足此前同运算结果的直接替换要求。

## 两个Strata：分别实际尝试

**Niko1221/Strata**，提交c77572806996349b49995e4f98d41b5294d36a21：对现有BF16 Omni与Open-H3 IC目录执行官方models import --plan --output json，两次均退出5，提示没有GGUF；H3启动计划退出2，型号不在目录。进一步核查[模型目录](https://github.com/Niko1221/Strata/blob/c77572806996349b49995e4f98d41b5294d36a21/docs/MODELS.md)与[H3请求#5741](https://github.com/Niko1221/Strata/issues/5741)，没有H3 DiT＋PDD＋VSA＋视频VAE路径。换文件格式不能补齐该架构。**导入／启动未通过，无视频速度。**[实际记录](../deployments/video-generation/deployment/framework-comparison-20261117/strata-niko-import.json)

**ro99/strata**，提交015b075079c51a7aec670ee24924f920f5e7bb2b：CUDA版strata-chat和strata-server均实际编译成功（CUDA13.2.86／GCC15.2／最多2并行）。独立补齐profiler-api13.2.86头文件；GCC jump-threading内部错误通过-fno-thread-jumps绕开，未改模型代码。随后分别以现有Omni／IC权重执行--model-type minimax-h3 --devices0 --dry-run，均退出2；聊天端明确unknown model-type，服务端打印已注册类型。其[注册模型](https://github.com/ro99/strata/blob/015b075079c51a7aec670ee24924f920f5e7bb2b/README.md#supported-models)没有该视频架构。**原生二进制构建和执行完成，H3准入失败，无视频速度。**[构建](../deployments/video-generation/deployment/framework-comparison-20261117/strata-ro99-build.json)，[准入](../deployments/video-generation/deployment/framework-comparison-20261117/strata-ro99-admission.json)

两个项目的RAM／VRAM／NVMe分层可供参考，不能把Qwen等语言模型tokens/s当作H3视频性能。没有为了测Strata下载或恢复旧Qwen。

## 4K并发：容量与主计算测试

使用已验收4K任务的实际packed长度345843，56 heads、D128、BF16、原生PyTorch Flash Attention，两份不同输入；一次预热、两次测量，各自对串行参考逐元素相同。

| 主注意力执行方式 | 两份总时间中位数 | 相对串行吞吐 | 第一份可用 |
| --- | ---: | ---: | ---: |
| 串行 | 47.6977秒 | 1.0000x | 约23.85秒 |
| 两个CUDA streams | 47.6943秒 | 1.00007x | 约23.85秒 |
| batch2 | 47.6909秒 | 1.00014x | 约47.69秒 |

吞吐差异小于0.02%，没有可见收益；batch2还推迟第一份。测试最大allocated显存约46.25／46.32GiB，包含输入与保留参考，**不是两个完整模型的显存。**

历史单条完整4K、5.167秒成片4666.787秒，间隔采样GPU63825MiB、主内存接近79GiB。两个独立worker不符合本机80／88GiB预算；共享权重多请求需要另做激活与工作区设计，不能从单路采样断言绝对不可能。但主计算并发无收益，当前不值得冒容量风险去启动两条完整4K。因此保留**HTTP可并发提交，4K在GPU串行排队**。两条完整4K、15秒4K并发均未验收。[注意力记录](../deployments/video-generation/deployment/framework-comparison-20261117/4k-attention-concurrency.json)，[历史4K](../deployments/video-generation/deployment/video-queue/4k-validation.json)

## 复现与证据

正式环境PyTorch2.12.0+cu130／Diffusers0.42.0／Accelerate1.0.1；SGLang提交8e737da037ddf967d9b1bab778f48fb35275d7ee使用PyTorch2.14.1；UniServe使用PyTorch2.13.0。[完整依赖差异](../deployments/video-generation/deployment/framework-comparison-20261117/full-video-environments.json)

追加的tools/run_omni_steady_suite.py与tools/run_fastvideo_omni_candidate.py仅完成语法检查，因用户取消未完成推理验收，不能作为已验证稳态成绩。

完整IC入口tools/run_ic_framework_full.py，策略current／diffusers／accelerate；验证入口tools/verify_framework_full_clips.py。Omni候选使用tools/run_sglang_omni_candidate.py或tools/run_uniserve_omni_candidate.py，仅绑定loopback；tools/measure_sglang_omni_http.py提交同一私有任务。所有入口须通过llm-lab/scripts/run_isolated.py，保持单卡独占lease，不能与正式worker重叠。准备脚本、候选补丁和脱敏结果落在普通部署子目录内。

原始请求、素材、生成媒体、日志、模型权重和大型张量仅保留本机outputs/framework-comparison-20261117/，不提交；公开[机器结果与范围](../deployments/video-generation/deployment/framework-comparison-20261117/results.json)。
