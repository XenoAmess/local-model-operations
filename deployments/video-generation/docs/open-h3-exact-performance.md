# Open-H3 IC 保持运算结果的性能优化

2026-11-17 用户要求：优化本机原生 4K 的速度，保持同运算结果。作用范围为 `open-h3-2k` 的本地 IC 重生成路径；此前暂停的完整 H3 教师性能实验继续暂停。

数据搬运优化已部署，后续 IC worker 默认启用；客户端调用不变。真实单层实测如下，均排除首次热身，使用随后两次的中位数：

| 序列规模 | 原执行方式 | 新执行方式 | 单层耗时减少 | 输出位级一致 |
| --- | --- | --- | --- | --- |
| 4K 代表序列，344,064 tokens | 26.633 秒 | 26.101 秒 | 2.0% | 是，1,849,688,064 个值 |
| 2K 代表序列，174,080 tokens | 7.866 秒 | 7.348 秒 | 6.6% | 是，935,854,080 个值 |

完整模型和真实 4K 输入也已核对：312 个 IC LoRA 全部完成缓存，实际序列为 345,843 tokens；将第一层恢复为原 FP32 LoRA masters 和原 FFN 分块执行方式重算，1,859,251,968 个 BF16 输出逐元素完全一致。该诊断在核对后主动结束，没有生成另一条视频。

4K 单层的原生 SDPA 实测约 23.629 秒，占整层约 88.7%，是主要瓶颈。三种长 query 分块都没有更快，128-token 小规模分块还有数值差异，因此均未启用。缓存实际 BF16 转换结果可减少约 3.87 GiB 常态主内存存储；初始化峰值仍受原权重加载影响，真实输入诊断峰值 79 GiB，仍保留 80 GiB 上限。

完整视频基线任务 `video_gen_8aa9ab4652a14d608c20db3c4cde7798` 已在不中断的情况下完成，5.167 秒原生 4K 总耗时 77 分 47 秒。**优化前后完整 4K 尚未重新测时，也未做该项全片逐帧比较**；不能将上述单层比值当成整段视频加速比或大幅提速承诺。[测评及运行记录](../deployment/video-queue/4k-exact-performance.json)、[4K 原始数据](../deployment/video-queue/performance/gpu-4k.json)、[2K 原始数据](../deployment/video-queue/performance/gpu-2k.json)、[真实输入核对](../deployment/video-queue/performance/real-input-parity.json)。

后续补充（2026-11-17）：已完成当前优化版、Accelerate 与 Diffusers 三条完整 **2K** 控制器对照，分别为 1498.407、1506.335、1562.786 秒，最终 latent 与全部 RGB 像素完全一致；该比较没有重跑优化前实现，不能据此计算原优化的完整视频收益。[完整框架实测](video-framework-benchmark-2026-11-17.md)。用户已确认正式 2K／4K 继续使用当前优化版，不替换后端；[全部调研及选型](video-framework-research-index-2026-11-17.md)。

## 一致性要求

保留原权重及适配器顺序、未合并 IC LoRA 的 A 再 B 运算、BF16 DiT、原版 36 层 FP32 tiled VAE、采样器和步数、种子、FFN 的 2048-token GEMM 分块形状、原生注意力后端和视频音轨处理。不把误差阈值内接近称为结果一致；候选优化须通过 `torch.equal` 逐元素完全一致检查。

更换注意力后端、合并 IC LoRA、修改 GEMM 分块形状和算子融合均可能改变浮点舍入。本轮不以这些方式换取速度。参见 [PyTorch 数值精度说明](https://docs.pytorch.org/docs/stable/notes/numerical_accuracy.html)及 [SDPA 文档](https://docs.pytorch.org/docs/main/generated/torch.nn.functional.scaled_dot_product_attention.html)。

## 数据搬运候选

1. 原 IC `LoRALinear` 在每次调用时将 FP32 A、B 转为输入的 BF16 类型。优化版在原 CUDA 设备上执行同样的转换一次，将实际参与运算的 BF16 数值缓存于 CPU；仍然分别计算 `W x`、`A x`、`B(A x)` 和加法，不合并权重。输入类型不符时拒绝执行，不静默采用不同计算。
2. 层权重在推理中不变。优化版保留原 CPU 存储，加载到 CUDA 后计算，结束时恢复 CPU 存储引用，省去把同样权重从 CUDA 复制回 CPU。所有复制与计算使用同一 CUDA stream，CPU 源数据始终存活且不修改；不额外固定一整份模型到 pinned memory。
3. FFN 逐块输出写入预分配的最终张量，减少同时保存全部分块再拼接的内存。每次 GEMM 的输入、形状和顺序不变。

另测同一非因果 SDPA 内核的 query 分块；它保留全部 key/value，不减少注意力范围。只有实测完全一致且更快才可能采用，不能仅凭理论独立性启用。

代码为 [h3_ic_exact.py](../tools/h3_ic_exact.py)，GPU 基准为 [benchmark_h3_ic_exact.py](../tools/benchmark_h3_ic_exact.py)。在线入口不改名、不改变调用参数。[worker 启动脚本](../start-h3-2k-worker.sh)默认设置 `H3_IC_EXACT_IO=1`；直接执行 runtime 时也可使用 `--exact-io`。需要恢复原执行方式时，将该脚本中的默认值 `${H3_IC_EXACT_IO:-1}` 改为 `${H3_IC_EXACT_IO:-0}`，从下一次 worker 启动生效，不会修改运行中的任务；无须重启 CPU HTTP 入口或强行打断队列。

## 验收边界与资源

- CPU 回归：分块尾段与不同 batch 的位级结果、LoRA 原运算、输入类型拒绝、异常后的存储恢复。
- GPU 基准：使用真实第 0 层、实际 HyperFlow／Sharp／IC 权重、代表本次 4K 的约 34.4 万 token 序列（检查点为 37 个潜帧，目标与参考视频已占 339,216 tokens，另有文字／视觉上下文和音频）；分开记录注意力、FFN、AdaLN 和整层耗时，并核对基线自身重复与优化结果。单层比值不能直接当作整段视频加速比。
- 完整 4K 服务验收另见 [成片记录](../deployment/video-queue/4k-validation.json)，不与单层算子测试混淆。
- 真实输入诊断使用 [run_h3_ic_real_diagnostic.py](../tools/run_h3_ic_real_diagnostic.py) 取得独占 GPU 锁；runtime 的 `--verify-first-block 报告路径` 是诊断参数，只验证第一层后退出，不可把其退出成功当作视频生成成功。
- 测试在当前任务结束后取得 GPU 独占锁，不停止用户任务、不同时运行两个 GPU 模型。继续保留 80 GiB 推理、88 GiB 聚合限制、独立内存看护、禁止云端和无开机自启。
