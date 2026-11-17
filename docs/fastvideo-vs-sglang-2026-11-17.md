# FastVideo 与 SGLang Diffusion：本机全面对比

2026-11-17。针对当前单张 RTX 6000D、BF16 FastH3 Omni 8 步、原版 36 层解码器、图片／文字／视频参考及后续本地 2K／4K 的生产环境，**推荐继续使用 FastVideo；SGLang 保留为有提速迹象的候选**。用户已确认此选型。

比较对象是 SGLang 的 `multimodal_gen`／Diffusion 视频管线，不把语言模型的 tokens/s、连续批处理或 KV cache 性能当成 H3 视频成绩。本次仅整理既有结果，没有重启已取消的性能测试或替换服务。

## 能力和运维

| 维度 | FastVideo | SGLang Diffusion | 本机判断 |
| --- | --- | --- | --- |
| 定位 | 视频推理、训练、微调、蒸馏 | 图像、视频、音频等统一生成推理服务 | 专注当前 H3 时 FastVideo 合适；扩展更多生成模型时 SGLang 值得考虑 |
| FastH3 Omni | FastH3 所属项目的原生实现 | 已有明确的 Ref2VA、8 步 PDD 配方 | 使用同一个学生检查点，无须重新训练 |
| 参考输入 | 文字与有序图片、视频、音频参考 | 同样支持多模态参考 | 更换框架不自动增强模型本身的参考能力 |
| 精度与解码 | 正式 BF16 DiT／文本编码器，原版 36L FP32 VAE masters，原生 FP16 decode autocast | 本机候选保留同类配置 | 相同权重精度与层数不等于全部算子和输出逐像素相同 |
| 本卡 SM120 | 当前正式部署已经可用，也有本地部署配置及补丁 | 固定测试版本的 H3 VSA 设备选择器拒绝 SM120，需本地实验补丁 | 不能把候选称为本卡上游开箱即用；也不把 FastVideo 称为零维护 |
| 显存策略 | 当前 `lazy_module_load=true`，分阶段加载和释放 | 组件常驻／卸载／快照、逐层流送等配置；本次候选部分 DiT 层常驻 | 放置策略会改变搬运、主内存和解码性能，没有证据证明某框架天然更省显存 |
| HTTP | 有 OpenAI 风格视频任务服务；本机接现有共享队列 | 有 HTTP、CLI、Python SDK 与多种集成 | 两者均可局域网调用；请求字段及返回格式仍须由适配层逐项保持 |
| 持久队列 | 本机已有任务落盘、依赖、按模型分组、等待上限、取消与 GPU 独占 | 可继续放在现有调度之后 | 框架切换不自动替代本机的跨模型持久调度 |
| 并发／批处理 | 正式单 GPU 工作负载 | 通用动态批处理依模型／任务／形状支持 | 没有本机 Omni 并发吞吐验收，不承诺并发更快 |
| 多 GPU | 有序列并行 | H3 配方有 Ulysses 等拓扑 | 本机只有一张卡，官方多卡数字不能直接使用 |
| 2K／4K IC | 当前独立后端来自 NVlabs/Sana IC，使用 PyTorch／Diffusers 和已验收搬运优化 | 本次 Omni 配方没有验证替代这条 IC 管线 | 切换 Omni 不自动加速 IC |
| 维护 | 当前服务、调用文档与资源控制已有实际记录 | 需维护 SM120 适配、派生模型布局、依赖与输出验证 | 当前迁移收益尚不足以覆盖验证和维护成本 |

官方定位与功能来源：[FastVideo](https://github.com/hao-ai-lab/FastVideo)、[SGLang Diffusion](https://github.com/sgl-project/sglang/tree/main/python/sglang/multimodal_gen)、[SGLang H3 配方](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3)、[组件放置 CLI](https://docs.sglang.io/docs/sglang-diffusion/api/cli)。官方最新文档与本机固定测试提交分别看待，不默认后续上游版本已经在本机验收。

SGLang 官方明确其主要组件源自 FastVideo 的早期分支；两者目前仍使用 Python、PyTorch 与 GPU 内核。Python HTTP 层或项目名称不能直接决定 GPU 推理效率；这次实际差异包含模型放置、算子、解码实现和依赖环境。

## 本机速度证据

同一图片、带音轨视频参考、prompt、seed1234；1344×768，124 帧，24 fps，约 5.167 秒，8 次 PDD 前向。保留 BF16、训练用 VSA 0.9／逻辑 tile128／参考视频保留率 0.1、原版 36L VAE。请求耗时含各推理阶段和必要加载，不含服务进程启动及外部 HTTP 排队。

| 完成的请求 | 请求至可下载 | 可得结论 |
| --- | ---: | --- |
| 当前 FastVideo 历史基线 | 759.213 秒 | 已有完整成片；一次历史样本 |
| SGLang 本地适配，第一次独立启动后的请求 | 667.679 秒 | 已有完整成片，少约 12.1% |
| SGLang 再次独立启动、显式参考缩放 | 661.582 秒 | 已有完整成片，少约 12.9% |
| SGLang 同进程重复相同输入 | 613.511 秒 | 存在条件缓存命中，适用于重复素材分析 |

数据见[完整实测报告](video-framework-benchmark-2026-11-17.md)及部署证据：[FastVideo 基线](../deployments/video-generation/deployment/omni-bf16/benchmark-result.json)、[SGLang 首条及重复请求](../deployments/video-generation/deployment/framework-comparison-20261117/sglang-full-video-adapted.json)、[显式复测](../deployments/video-generation/deployment/framework-comparison-20261117/sglang-full-video-explicit-reference.json)。

这些数据支持“SGLang 有提速迹象”，没有建立公平的预热后量产排名。FastVideo 与 SGLang 使用不同 PyTorch 版本、放置策略和实现；历史 FastVideo 还有 profiling 配置差异。原计划的完整预热后连续对照在完成前取消，[取消记录](../deployments/video-generation/deployment/framework-comparison-20261117/steady-comparison-cancelled.json)明确 `steady_comparison_completed=false`。

SGLang 同进程重复素材的 613.511 秒是真实结果，条件编码缓存也是实际功能；但应分别测量缓存关闭、首次输入与重复素材，不与其它实现的首条请求混在一起排序。不同 seed 仍可能复用同一条件编码，去噪和解码每条都要执行。[官方缓存说明](https://docs.sglang.io/docs/sglang-diffusion/caching-acceleration)

冷启动不作为持续量产排名依据。另一方面，本卡容量要求内部按阶段或逐层加载；这些每条请求仍发生的加载与搬运属于量产成本，不能因为服务进程已预热就从计时中扣掉。

## 质量与数值

两边使用相同 Omni 检查点、8 次前向与原版 36L，不能仅据框架名判谁画质更好。SGLang 成片完整、角色和场景可辨，但抽查景别与 FastVideo 历史基线不同：后者偏全身，前者偏面部近景。不同输出既不证明质量下降，也没有证明任务与质量等价。

FastVideo 本身已有 PDD 头融合。SGLang 的离线融合与 FastVideo 的运行时融合、注意力归约和其它算子并非相同数值路径；种子相同也不保证跨实现逐像素一致。没有单因素实验将景别变化归因于 PDD 或注意力。[详细源码解释](h3-pdd-attention-implementation-2026-11-17.md)

若要求逐元素完全一致，当前 SGLang 候选未达到替换标准。若以后允许视觉质量相当，应单独评估人物一致性、动作、构图、细节、时间稳定性、音画同步和参考遵循；不能用一次抽帧或微小内核误差代替这些指标。

## 服务功能的实际边界

- SGLang 动态批处理默认关闭，且不同于 LLM 连续批处理。官方兼容表没有给出 FastH3 Omni 的已验证支持；本机也没有验证 Omni 多请求合批。支持其它文生视频模型不能外推为本任务吞吐收益。[动态批处理](https://docs.sglang.io/docs/sglang-diffusion/dynamic_batching)
- SGLang 官方 H3 配方对 VSA 路径的 `torch.compile`、部分 CUDA Graph 和并行组合有专门限制。全框架存在某开关不等于 Omni 可以直接启用并受益。[H3 配方](https://docs.sglang.io/cookbook/diffusion/MiniMax/MiniMax-H3)
- 当前 FastVideo 分阶段释放模块；SGLang 候选逐层流送并保留 24 层 DiT。服务常驻与全部模型权重常驻是两件事，现有 GPU／主内存限制须继续保留。
- Omni 与 IC 共用单卡的分组、依赖和公平调度属于现有服务层。保留同模型进程可以减少重复启动，但不能取消必要的内部阶段搬运，也不能由此承诺两模型同时驻留。

## 正式采用理由与未来重评条件

现阶段选 FastVideo，是因为它已经满足当前服务接入和运行要求，而 SGLang 的公平持续吞吐、质量等价与本卡上游兼容性尚未闭合。这个选择不等于 FastVideo 已被证明更快。

SGLang 若以后具备本卡可维护的 H3 VSA 支持，并在相同精度、解码器、参考预处理和缓存口径下证明稳定的量产收益，再通过任务质量验收，才有充分依据重新评估迁移。此处列出重评条件，不恢复本次已经取消的基准。

正式部署保持 Omni `fasth3-omni-bf16`／8001、IC `open-h3-2k`／8002 与当前共享队列；IC 的优化和能力边界见[研究总入口](video-framework-research-index-2026-11-17.md)。
