# 工程化提速调研结论：保留一条内核验证主线，其余降级

**后续实测已完成：[S42 交付后的工程优化实测](h3-engineering-optimization-tests-2026-11-21.md)。FROST 在5秒／14秒代表形状约1137／3107 ms，现用约1134／3102 ms，均基本打平；仅 SDPA CUDA Graph 也没有有效收益。正式后端未更换，队列已恢复。** 以下保留实验开始前的研究依据和候选筛选过程，候选去留以后续实测为准，不能把建议门槛当作已获收益。

2026-11-21。针对用户要求，核查了现有实现、已完成 GPU 数据、官方内存／图捕获约束及最新 SM120 密集内核源码，并补做了一个 16 帧 4K 的隔离 CPU 编码探针。**没有重跑模型、启动新 GPU 推理或改动正式配置，原服务继续处理后续任务。**

**结论：不建议同时重构预取、CUDA Graphs、常驻模型和整个输出流程。现有证据下，这些不是八小时长片的主要提速来源。值得继续投入的主线只有：在安全任务边界分析一个真实长序列调用／层，再对新的 SM120 BF16 密集内核做有门槛的短测。当前没有已验证的同结果、单卡数倍加速方案。**

## 逐项去留

| 方案 | 结论 | 核查依据 |
| --- | --- | --- |
| Nsight 时间线与算子分析 | **下一步首选验证工具** | 识别真正的 Tensor Core／访存／同步限制，避免仅凭 GPU 100% 利用率推断。先用最小代表性调用或一个真实层，不重做八小时视频 |
| 新 SM120 BF16 密集内核／FROST | **唯一保留的主要提速候选，尚未采用** | 有 D128、BF16、无掩码与 64 位 stride 接口；但默认调优表的 K/V 上限与 SM 数不匹配本机，需要显式调参与超长正确性检查 |
| 去掉中间 FFV1、直出 MP4 | **可作为低优先级小修，不作为主线** | 16 帧 CPU 测试显示编码不是主瓶颈；更改流水线能减少中间 I/O／转码，但只有分钟级空间，完整像素和音轨验收仍需做 |
| 双缓冲权重预取 | **暂不投入大改；等 profiling 证明拷贝等待明显再做** | 当前已经单向搬运、无重复 D2H。直接套官方流式 offload 还可能显著增加 CPU 内存；自定义小缓冲虽可研究，但收益未证实 |
| 固定缓冲＋整模型 CUDA Graphs | **不建议当前投入** | 主注意力单次约 3.1 秒，CPU 发射开销很小；逐层 `.data` 换地址与图重放固定地址不兼容，需额外重构，难以回收成本 |
| 阶段常驻／批量复用／缓存 | **保留现有功能，不扩为本轮性能主线** | 4K 当前为单任务／单窗口，2K 已有最多两个窗口复用。当前七个排队任务没有完全相同的生成键；复用不能省掉各自的去噪 |
| 全局 `torch.compile`／不保留舍入的融合 | **不按同结果优化采用** | 工程改写也会影响数值；FastVideo 的 H3 公开实验明确出现与 eager 不同的成片，不能仅凭“只改代码”称为无损 |

以上是研究后的去留判断，不是新增已实测加速成绩。新内核、预取或图捕获均没有在本轮做 GPU 对照。

## 本机时间预算决定优先级

S48 实际端到端 29,247.78 秒：采样 27,987.1 秒，占 **95.69%**；36L 解码及无损输出 989.7 秒，占 **3.38%**；其它加载、封装等约 270.98 秒，占 **0.93%**。[已完成成片与密集短测](h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)

采样中也包括投影、LoRA、FFN 与搬运。把代表性注意力调用按查询量及 150 层次外推约占总时长 92%，但这不是完整 profiler 实测占比。它足以确定主攻方向，不足以精确给每个小优化分配收益。

即使把整个解码阶段假想为免费，也只省约 16.5 分钟；解码快一倍只省约 8.25 分钟。把余下所有加载、封装开销都假想去掉，只省约 4.5 分钟。这些是理论时间预算，不是预计能达到的优化幅度；纯 GPU VAE 计算与编码回压的贡献仍需分开测。

## 新补的 CPU 编码探针

从 S48 的 2.31 GB FFV1 中间文件读取前 16 帧，解为相同 RGB24 像素，分别按当前 FFV1 level3／2 threads 和 libx264 medium／CRF16／4 threads 编码，两次取中位数：

| 操作 | 16 帧实际时间 |
| --- | ---: |
| FFV1 解码并写出 RGB 样本 | 3.05 秒（单次） |
| FFV1 编码 | 2.22 秒 |
| libx264 编码 | 1.88 秒 |

作为粗略尺度比较，989.7 秒／336 帧的 VAE＋无损输出，平均每 16 帧约 47 秒。FFV1 的独立编码速率快得多，**没有证据支持把八小时主要归因于这个中间编码器**。可以减少中间文件和最终重复读取，但不应把 16 帧线性外推当成完整 14 秒编码实测，短片 GOP／缓存／并行和 GPU 回压都会影响最终结果。

探针只用了 CPU，nice 15，6 GiB 工作内存、88 GiB 聚合限制，约 11 秒结束，unit 内存峰值约 1.8 GiB；没有争用显卡，也没有改变 S48 成片。原始 RGB 临时文件已删除，样本媒体仅留执行机器，不入 Git。[原始结果](../deployment/minimax-h3/cpu-codec-probe-20261121.json)、[探针脚本](../tools/benchmark_h3_output_codecs.py)。这不是不同输出流水线的完整像素等价测试。

## FROST 为什么只列为候选

核查 NVIDIA `cudnn-frontend` 默认 `develop` 分支提交 `9638468d752dbc97fc252be3a973855a0c4e9651`：

- `aot/sm120/variants.py` 有 BF16、D128、nomask，MHA 的 G=1 和非 PackGQA 路径可以进入选择表；不是只有量化或 GQA 才能使用。
- 默认 `GRID_SKV` 只到 **131,072**，超过时选择表会 clamp 到最后一格。**这是默认选择表覆盖范围，不是已经证明的 kernel 长度硬上限**；不能误解为 949,232 一定不能运行，也不能称已获最佳调度。
- 默认 SM 选择表按 **170／188 SM** 生成。本机通过 CUDA Driver 的无 context 属性查询得到 **SM120、156 SM**；匹配架构不等于匹配调优配置。
- ABI 的序列长度是 int32，stride 是 int64；现有长度本身在 int32 范围内，但完整张量跨大偏移，仍须验证末头／末尾 K/V，不能凭字段类型保证无错误。
- 构建脚本要求 CuTe DSL 至少 4.8，并要求导入当前源码 checkout 的 `cudnn`。本机已有 Cutlass DSL 4.8.1／cudnn frontend 1.32.0，不代表已经安装或编译了这份最新实现。构建默认并行较高，若后续试验必须显式限制 jobs 并隔离。

来源：[固定源码矩阵](https://github.com/NVIDIA/cudnn-frontend/blob/9638468d752dbc97fc252be3a973855a0c4e9651/aot/sm120/variants.py)、[ABI](https://github.com/NVIDIA/cudnn-frontend/blob/9638468d752dbc97fc252be3a973855a0c4e9651/include/cudnn_frontend/experimental/sm120_aot_attention_abi.h)、[构建入口](https://github.com/NVIDIA/cudnn-frontend/blob/9638468d752dbc97fc252be3a973855a0c4e9651/aot/sm120/build.py)、[官方 AOT 说明](https://docs.nvidia.com/cudnn/operations/Attention/aot_sm120_attention)。

AOT 主要提前编译和加载代码；**不能把它减少的冷准备时间当作预热后的吞吐收益**。本次 cuDNN 9.20 路径的 0.4% 结果也不能代表尚未实测的新内核。

## 其它方向为什么降级

CUDA Graphs 主要减少 CPU 调度。NVIDIA 建议优先选择大量短 kernel 与明显 CPU 空洞，而不是长时间占用 GPU 的大 kernel；本机注意力 CUDA event 与调用墙钟只差几十微秒。现有 `h3_ic_exact.py` 每层 onload 会重新赋 `parameter.data`，重放图则要求固定指针；不能直接加开关而保持原卸载行为。[NVIDIA CUDA Graph 最佳实践](https://docs.nvidia.com/dl-cuda-graph/latest/torch-cuda-graph/best-practices.html)、[PyTorch 约束](https://docs.pytorch.org/docs/2.12/notes/cuda.html#cuda-graphs)

预取也不是直接开启 `non_blocking=True`：现有代码已经这样写，但同一 stream 的拷贝与计算仍串行。真正重叠需要 pinned staging、独立 stream、事件依赖和正确生命周期。Diffusers 官方提醒流式 group offload 可能需要约两倍模型主内存；本机 block CPU 存储约 63.84 GiB，简单按两倍准备约 127.68 GiB，超过 80 GiB 限制及本机约 122 GiB 主内存。可以自定义少量层的 staging，但没有收益证据前不值得大改。[Diffusers 内存与流式卸载说明](https://huggingface.co/docs/diffusers/main/en/optimization/memory)

缓存与常驻对重复输入及批量吞吐有价值，但当前观察到的七个 queued 任务，素材内容、提示词、seed、sampler、size 的组合键均不同；不能把结果缓存作为这批任务的推理提速。阶段复用目前在 2K 已实现，扩大 4K cohort 需要重新验内存，不能绕过已有上限。BF16 LoRA 缓存、只读 CPU 存储、单向搬运和输出预分配已经部署，不重复列作新收益。

## 明确的后续门槛

建议将下一轮限定为一条主线：**最小代表性调用／真实层的性能分析 → FROST 的无掩码 BF16 大偏移准入 → 预热后短测**。数值或末尾 K/V 检查失败立即淘汰；若要求逐位相同，任何输出差异都不能按同结果方案采用。若算子延迟减少不到约 10%，建议不投入完整服务接入；10% 是建议的投入门槛，不是预计收益，更不是已经达到的成绩。只有算子和真实层收益明确后才值得安排完整视频质量与时间对照。

当前正式服务与队列保持原样，没有自动编译或部署新 GPU 后端，也没有恢复已取消的框架基准。机器可读证据见[本轮研究记录](../deployment/minimax-h3/engineering-optimization-conclusions-20261121.json)。
