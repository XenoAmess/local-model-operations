# FastH3 Omni 的 PDD 头融合与注意力实现差异

2026-11-17。本文解释本轮 FastVideo 与 SGLang 候选的源码差异，记录已纠正说法及数值边界。它不修改正式模型、权重或服务。

## 先澄清：两边都已有 PDD 头融合

PDD 是 Parallel Decoding Distillation。这里的“头”是 DiT 最后的输出投影头，预测视频／音频的流速度；它不是注意力头，也不是原版 36 层视频 VAE 解码器。

Omni 发布的是为 PDD 训练的学生模型：细网格有 32 个区间，标准配置每 4 个区间组成一块，用 8 次骨干前向完成生成。不能理解为拿普通完整 H3 的 32 次独立前向直接删成 8 次。

**FastVideo 已经做融合。** SGLang 的差异主要是准备模型时离线生成每块的融合头，不能把它描述为“只有 SGLang 新增融合，所以省去 FastVideo 的 32 次前向”。两边本次均为 8 次骨干前向。

## 融合为何成立

同一个 PDD 块内，各输出头共享隐藏状态 `h`，头是线性投影：

```text
v_i = W_i h + b_i
alpha_i = delta_sigma_i / sum_j(delta_sigma_j)

sum_i(alpha_i v_i)
  = (sum_i alpha_i W_i) h + sum_i(alpha_i b_i)
```

因此可以先按区间噪声宽度加权融合权重，再做一次输出投影。调度器用块的总噪声宽度完成更新。权重不是简单算术平均；视频和音频的 shift 分别为 12、3，使用发布模型的固定采样网格与 0.999 上界。

此推导依赖共享的 `h`、线性输出以及该采样路径不额外注入随机噪声的 eta0／Euler 更新。它不能推广成任意扩散模型连续四次前向都能这样合并。

## 两边的具体实现

| 项目 | FastVideo 固定版本 | SGLang 固定候选版本 |
| --- | --- | --- |
| 融合时机 | 采样块运行时选择对应头并融合 | 模型布局准备时离线生成 8 组融合头，运行时选择 |
| 加权计算 | scheduler 输入精度下归一化，再以 FP32 等指定精度累计；`torch.einsum` 归约 | 工具以 float64 构造 sigma 网格，权重转入头的精度，FP32 乘法后 `sum(0)` |
| 原权重 | 读取原始参数 | 生成派生文件，公共组件链接复用；没有覆盖原始检查点 |
| 理想实数公式 | 加权线性头 | 加权线性头 |
| 浮点逐位一致性 | 本实现的基线 | 与左侧未证明逐位一致 |

运行目录源码定位：

- FastVideo：`fastvideo/layers/pdd.py` 的 `PDDReplicatedLinear._fused_params()`，以及 `fastvideo/pipelines/basic/minimax_h3/stages/minimax_h3_denoising.py` 的块融合调用。
- SGLang：`python/sglang/multimodal_gen/tools/fuse_minimax_h3_pdd_heads.py` 的 `sigma_grid()`／`fuse()`，以及 `models/dits/minimax_h3.py` 的融合头加载。
- 本机模型准备入口：[prepare_sglang_omni_checkpoint.py](../tools/prepare_sglang_omni_checkpoint.py)。

固定源码：[FastVideo PDD](https://github.com/hao-ai-lab/FastVideo/blob/a0e6cf1f5086c9af735d73e6c0b80dbc1d5817b3/fastvideo/layers/pdd.py)、[SGLang PDD 工具](https://github.com/sgl-project/sglang/blob/8e737da037ddf967d9b1bab778f48fb35275d7ee/python/sglang/multimodal_gen/tools/fuse_minimax_h3_pdd_heads.py)。

数学公式等价不保证浮点逐位相同。归一化精度、CPU／GPU 归约、求和顺序与算子融合都会影响舍入。它们本身也不证明视觉质量有下降；本轮没有隔离 PDD 融合做完整成片归因。

## 注意力中保留了什么

Omni 的 VSA 是与学生模型一起训练的 Video Sparse Attention。正式配置的逻辑 tile 为 128，生成视频区域使用 0.9 稀疏度，每段参考视频按独立区域保留 0.1 的候选 tile。文本、图片参考和音频等前缀仍有密集注意力路径。

这不是对全模型任意删掉 90% 内容，也不能据此声称总计算减少 90%。视频稀疏精细分支之外还有压缩／门控等计算，以及其它模块和必要的数据搬运。

两边都可以把 128-token 逻辑 tile 展开成两个 64-token 执行 tile；这是内核执行布局，不是将训练的逻辑稀疏策略改成另一套 64-token 策略，也不是 SGLang 独有的变化。

本机 FastVideo 使用已部署的 SM120 BF16 Triton 路径。SGLang 候选使用其 Triton descriptor 等实现；打包布局、softmax 与矩阵累计顺序可能不同。使用相同 Q/K/V 和相同选择集合，也不自动得到逐位相同的结果。

## 本地 SGLang 补丁实际改了什么

针对固定提交 `8e737da037ddf967d9b1bab778f48fb35275d7ee`，上游 H3 VSA 设备白名单不接受本机真实 SM120。实验补丁只在显式 `H3_FRAMEWORK_EXPERIMENTAL_SM120=1` 时：

1. 将真实 `(12, 0)` 加入该后端的允许集合，没有伪造设备身份。
2. 将 dense token-refiner 的 FlashAttention fallback 换为 SGLang 自带的 PyTorch SDPA 路径，处理本环境 FA2 不可用的问题。

主视频计算仍保留 VSA，并没有把整条管线改为 dense SDPA。补丁没有改模型结构、采样步数、目标尺寸、权重精度或 36L decoder。[完整补丁](../patches/sglang-h3-sm120-experimental.patch)

SDPA 是 PyTorch 的注意力接口，会按环境选择实现；不能把接口名当成固定 CUDA 内核或数值一致保证。[PyTorch SDPA 文档](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html)

## 相同输入的注意力微基准

保存同一份 BF16 Q/K/V，65536 tokens、56 heads、D128，相同 10% key 集合和两个 dense query tiles；逻辑 tile128；一次预热、三次测量中位数。

| 内核 | 中位数 | 相对 FastVideo 耗时减少 | 与 FastVideo 逐位相同 | 最大绝对差 | RMS 差 |
| --- | ---: | ---: | --- | ---: | ---: |
| FastVideo SM120 Triton | 92.479 ms | 基准 | 是 | 0 | 0 |
| SGLang Triton descriptor | 90.702 ms | 1.92% | 否 | 0.00048828125 | 1.94e-7 |
| UniServe SM120／FlashInfer | 89.687 ms | 3.02% | 否 | 0.0009765625 | 6.22e-5 |

这只测注意力内核，不包括投影、top-k、gate、模型加载或编码解码；不是整片收益，更不是最终视频误差上界。扩散迭代可能放大细小差异，但还存在 RNG、其它算子和环境差异，本轮没有单因素归因。[完整实测](video-framework-benchmark-2026-11-17.md)

## 质量判断和正式采用边界

- 完整成片：SGLang 已跑通、下载和完整解码。相同输入的独立复测输出相同，但与 FastVideo 历史基线景别不同；这既不证明质量下降，也没有证明质量等价。
- 预处理纠正：SGLang 的通用 H3 类默认值曾引发参考缩放怀疑；其 Omni 子类实际已覆盖为 `diffusers`。显式设置后与原请求 MP4 SHA 相同，不能继续以该项解释输出差异。
- 当前 IC 优化是另一回事：保留原运算、未合并 LoRA 与原注意力，只优化转换缓存和数据搬运；其完整 2K 控制器对照通过了最终 latent 及全部 RGB 像素一致性。
- 用户已确认正式 Omni 保留 FastVideo，2K／4K 保留当前优化 IC；SGLang／UniServe 的实验实现不自动上线。

建议同时阅读[全面对比](fastvideo-vs-sglang-2026-11-17.md)与[全部调研结果入口](video-framework-research-index-2026-11-17.md)。
