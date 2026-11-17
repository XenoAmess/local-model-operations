# H3 框架实测、两个 Strata 与 4K 并发

2026-11-17，RTX 6000D，`nvidia-smi` 显存总量 85,651 MiB。推理／编译均使用隔离 cgroup，保留单任务 80 GiB、聚合 88 GiB 内存限制。候选环境与正式环境分开，正式推理代码未替换，关闭开机自启。基础轮结束时服务已恢复；下述补测期间 HTTP 保持在线、GPU 调度器暂暂停，整套补测控制器在结束或异常退出时恢复调度器。

这是实际执行记录。分项计时、模型准入与完整视频计时分别列出；没有候选的合格整片成绩时，不填写推测的速度。

## IC 搬运：相同真实 block、权重与运算

加载真实 H3 block 0，按正式顺序加入 HyperFlow、Sharp 与未合并 IC LoRA。候选仅改变搬运控制器，保留已验证的 BF16 LoRA 缓存与 2048-token FFN 分块。每种执行一次预热、两次测量，下表为后两次的中位数。

| 搬运实现 | 2K 长度：174,080 tokens | 4K 长度：344,064 tokens | 输出 |
| --- | ---: | ---: | --- |
| 当前优化版 | 7.3476 秒 | 26.0977 秒 | 与原始执行逐元素完全一致 |
| Accelerate `cpu_offload` | 7.3859 秒 | 26.1794 秒 | 完全一致 |
| Diffusers group offload，不开 stream | 7.8127 秒 | 26.5698 秒 | 完全一致 |
| Diffusers stream＋低 CPU 内存模式 | 未进入大尺寸测试 | 未进入大尺寸测试 | 4096-token 检查未通过逐元素一致性 |

环境为 PyTorch 2.12.0+cu130、Diffusers 0.42.0、Accelerate 1.0.1。当前实现的两个尺寸分别比较了 935,854,080 与 1,849,688,064 个 BF16 输出元素。此轮没有显示官方搬运控制器比当前优化版更快；小于 1% 的差异不作显著性判断。stream 失败只说明这次接入未通过验收，未将原因归咎于上游全部实现。

**以上均为一个 block 的结果，不是完整 2K／4K 成片加速比。** 历史 5.167 秒 4K 基线为 4666.787 秒；本轮没有重跑整片。[原始验收](../deployment/video-queue/4k-validation.json)

## Omni：实际内核与完整接入的边界

三套实现使用同一份保存的 BF16 Q/K/V 输入，同样的 65,536 tokens、56 heads、128 head dimension、逻辑 tile=128、10% 稀疏选择与两个密集 query tiles。保留相同被选 key 集合，记录跨环境输入 SHA256。每个内核一次预热、三次测量。计时不含 QKV 投影、top-k 选择、压缩 gate、模型加载与整片解码。

| 稀疏注意力实现 | 中位数 | 相对 FastVideo 的耗时降低 | 与 FastVideo 完全一致 | RMS 差异 |
| --- | ---: | ---: | --- | ---: |
| FastVideo 当前 SM120 split-64 Triton | 92.479 ms | 基准 | 是 | 0 |
| UniServe SM120／FlashInfer | 89.687 ms | 3.02% | 否 | 6.22e-5 |
| SGLang Triton descriptor 内核 | 90.702 ms | 1.92% | 否 | 1.94e-7 |

这些小幅内核差异不能当作整片收益，也没有证明画质下降或相同。按此前“保持同运算结果”的要求，不能直接采用数值有差异的内核。

| 完整 Omni 接入 | 实际执行及结论 |
| --- | --- |
| 当前 FastVideo | 历史相同图片＋带音频参考视频、1344×768、124 帧、8 步基线 759.213 秒，已成片验收。本轮没有用内核计时替代该结果。 |
| SGLang | 独立安装、转换本地权重布局，HTTP 已接受同一参考请求并执行到去噪。其 SM120 默认选择密集注意力；显式指定训练用 VSA 后，当前上游选择器以 compute capability 12.0 拒绝启动。不能把密集注意力试跑作为同训练配置成绩，故无合格整片时间。 |
| UniServe | 独立安装并编译原生 CUDA 扩展成功，真实 GPU 可解析 tile-128 SM120 后端，已执行上表内核。meta 模型按默认 quality 精度预算约 94.69 GiB 参数，超过本卡；默认 decoder 还是 FP16 投影。未以超过容量的全组件常驻配置启动，也未完成分阶段加载后的完整参考生成，因此没有整片速度结论。 |

SGLang 的低层 Triton 内核能单独运行，不等于完整服务已支持该设备。以上是未修改候选的基础轮结论；后续本地实验适配结果单列于下，不覆盖上游默认不支持的事实。PDD 输出头融合带来的浮点舍入差异不能称为 bitwise 相同。

候选固定提交：UniServe `d58bee14b46475c690ead7540f9f2bbab7790195`；SGLang `8e737da037ddf967d9b1bab778f48fb35275d7ee`。分别安装 PyTorch 2.13.0 和 2.14.1，区别于正式环境；完整依赖锁与原始日志留本机 `outputs/framework-comparison-20261117/`。

## 两个 Strata：分别研究、分别实际尝试

### Niko1221/Strata

固定提交 `c77572806996349b49995e4f98d41b5294d36a21`。执行官方 `bin/strata models import <模型目录> --plan --output json`，分别传入现有 BF16 Omni 与 Open-H3 IC 目录。两次都返回退出码 5，提示目录内没有 GGUF；另一次 H3 启动计划返回退出码 2，提示型号不在目录内。

格式拒绝本身不足以证明换成 GGUF 后仍不能运行；进一步核查其模型族、引擎配置与 sampler 路径，当前面向 Qwen3.8-Flash-Next／Qwen3.6 等语言模型，没有这套 H3 DiT＋PDD＋VSA＋视频 VAE 执行入口。H3 的张量流式搬运适配仍是开放中的[上游功能请求 #5741](https://github.com/Niko1221/Strata/issues/5741)，[官方模型目录](https://github.com/Niko1221/Strata/blob/c77572806996349b49995e4f98d41b5294d36a21/docs/MODELS.md)也未提供 H3 路线。

**结论：现有权重导入与 H3 启动计划均未通过，无视频生成速度成绩。** 它可以作为语言模型服务驱动另外的视频引擎；那种组合的渲染速度应归于实际视频引擎。

### ro99/strata

固定提交 `015b075079c51a7aec670ee24924f920f5e7bb2b`。独立尝试编译 CUDA 版 `strata-chat`／`strata-server`，使用 CUDA 13.2.86、GCC 15.2、最多两个编译任务。补充独立的 `nvidia-cuda-profiler-api==13.2.86` 头文件，未改变正式 CUDA 工具目录。

CUDA 版两个程序最终均编译成功。GCC 15 在 DeepSeek 源文件的 jump-threading pass 出现内部错误，在 Release 构建增加 `-fno-thread-jumps` 后通过；未修改上游模型代码，也没有以此构建报告语言模型性能。

随后分别执行 `strata-chat --model <Omni目录> --model-type minimax-h3 --devices 0 --dry-run` 和 `strata-server --model <IC目录> --model-type minimax-h3 --devices 0 --dry-run`。两者均退出码 2；聊天端明确报告 `unknown --model-type: minimax-h3`，服务端拒绝准入并打印其已注册类型。其[注册模型](https://github.com/ro99/strata/blob/015b075079c51a7aec670ee24924f920f5e7bb2b/README.md#supported-models)为语言模型，没有 H3／Ref2VA／IC 视频采样路线。

**结论：原生 CUDA 二进制已实际构建和执行，H3 未通过准入，无视频生成速度成绩。** 编译成功不作为模型生成成功。

**两个项目的 VRAM／RAM／NVMe 分层思路可供工程参考，不能直接把语言模型 tokens/s 当作视频生成速度，也不能靠改变文件扩展名补齐模型架构。**

## 4K 并发：本卡实际测了什么

使用已验收 4K 任务的实际 packed 长度 345,843，56 heads、128 head dimension、BF16、原生 PyTorch Flash Attention。为两份不同输入比较串行、两个 CUDA streams 和 batch=2；一次预热、两次测量，每种模式均与各自串行参考逐元素一致。

| 执行方式 | 两份计算总时间中位数 | 相对串行吞吐 | 第一份结果 |
| --- | ---: | ---: | --- |
| 串行 | 47.6977 秒 | 1.0000× | 约 23.85 秒完成 |
| 两个 streams | 47.6943 秒 | 1.00007× | 约 23.85 秒完成 |
| batch=2 | 47.6909 秒 | 1.00014× | 约 47.69 秒完成 |

没有可见吞吐收益；batch=2 还推迟第一份结果。峰值已分配显存约 46.25／46.32 GiB，包含公共测试输入与保留的参考输出，不是完整视频任务的显存。

真实单路 4K 历史采样显存峰值 63,825 MiB，主内存接近 79 GiB。两个独立完整 worker 不符合本机容量预算；共享权重的多请求并发需要另做激活与工作区预算，不能单靠两倍显存采样值证明其绝对不可能。但此轮最重计算的实测没有支持值得改造的吞吐收益，因此保持当前 **HTTP 可同时提交、4K 在 GPU 上串行**。两条完整 4K 视频同时推理未验收，15 秒 4K 整片并发更未验收。

脱敏机器记录：[结果与范围](../deployment/framework-comparison-20261117/results.json)。原始用户请求、素材、生成媒体、环境、上游 checkout 与大型张量均不提交。


## 完整视频补测：进行中，不能宣称全部完成

2026-11-17 17:26 CST：两个 Strata 的实际准入尝试与分项测试已经完成；完整 IC 搬运对比、UniServe 完整生成仍在补测。4K 双整片并发未验收，维持有边界的内核测试与容量结论。

SGLang 增加显式 `H3_FRAMEWORK_EXPERIMENTAL_SM120=1` 的本地适配：放行 SM120 的训练用 VSA，dense token-refiner 的 FA2 fallback 改用其自带 SDPA。硬件身份不变，逻辑 tile=128、稀疏度0.9、参考保留率0.1、8次 PDD 前向、BF16 DiT／文本编码器与原版36L FP32 VAE 保留。DiT 每次前向保留24层，保留80／88 GiB限制。补丁见 [SGLang 适配](../patches/sglang-h3-sm120-experimental.patch)。这是候选适配版，尚未采用到正式服务。

| 完整 1344×768、124帧、带音频、相同参考和seed | 时间 | 范围 |
| --- | ---: | --- |
| FastVideo 历史基线 | 759.213秒 | 请求内部懒加载；API启动另6.007秒 |
| SGLang 本地适配，默认参考缩放，第一条 | 667.679秒 | 提交至可下载；服务预先加载，启动等待另52.183秒 |
| SGLang 本地适配，默认参考缩放，第二条 | 613.511秒 | 相同输入重复请求，可使用条件缓存 |

两条 MP4 均下载并通过完整 FFmpeg 解码，均有124帧及音轨。第一条抽查第0、60、123帧无黑屏或破损，角色与场景可辨；这不能证明画质相同或数值等价。最初根据通用H3默认 `max` 怀疑参考缩放不同，随后核查 **`FastH3OmniSamplingParams` 自身已覆盖为 `diffusers`**，与通用类不同；显式设置该参数的独立服务重启补测又得到与第一条默认请求完全相同的MP4 SHA256。因此撤回“参考缩放不匹配”的判断，实际图片均为2048×2464。候选画面从基线全身景别变成更近的面部景别仍是事实，不能以画面完整就宣称任务和质量等价。加载位置、条件缓存、PyTorch版本和具体算法不同，未将请求时间比值当作同数值结果加速比。第二条也不称为纯模型推理时间。完成下载后停止候选，2秒 shutdown deadline 导致剩余服务子进程被清理，unit 的 timeout 是停止阶段事件，不能误记为生成失败。

UniServe 原生 Rust HTTP＋Python worker 已在独立环境编译成功。尝试通过其原生 host-weight streaming 接入单卡；本地候选补丁使标记 `weights=host` 的组件直接在 CPU 加载，再构建原生分层GPU staging，避免先把超过显存容量的权重全部加载到GPU。首次正式请求前必须通过多层CPU加载流送的逐元素一致性检查。它的默认 quality 模式将原版36L VAE投影权重存为FP16，与正式FP32权重＋FP16 autocast路径不同，完整结果即使成功也须单独标注，不能视为保持同运算结果的替代。

原始完整视频记录保留在本机 `outputs/framework-comparison-20261117/full-video/`；公开记录：[SGLang完整补测](../deployment/framework-comparison-20261117/sglang-full-video-adapted.json)。IC完整对比将另记录最终 latent 与像素一致性，不能用先前单block一致性替代。


2026-11-17 18:03 CST 补测更新：

- 当前IC优化版完整2K、124帧完成，墙钟1498.407秒，其中三轮去噪1152.2秒，原版VAE解码约175秒。抽查第0、60、123帧完整。其余控制器尚待完整对照，不能单凭这个基线下结论。[记录](../deployment/framework-comparison-20261117/ic-full-current.json)
- SGLang显式 `reference_resize_mode=diffusers` 的独立重启完整生成661.582秒，服务启动另52.289秒，8轮去噪563.232秒；MP4与第一条默认请求SHA256完全相同。计入服务启动后约713.872秒；FastVideo历史对应启动＋请求约765.220秒，观察到约6.7%墙钟降低，但样本很少、环境不同、输出构图不同，未通过同运算结果或质量等价验收，**不替换线上**。[记录](../deployment/framework-comparison-20261117/sglang-full-video-explicit-reference.json)
- UniServe CPU直接加载＋原生分层流送的小模型检查通过：10层、3次完整前向、一次中断后重开均逐元素一致。首次服务启动因部署配置 `queue_depth=2` 不足而拒绝，运行时要求每个请求至少3个queue positions；修正为3后安排重试。此配置失败不算框架不支持，也不算完整H3成功。
