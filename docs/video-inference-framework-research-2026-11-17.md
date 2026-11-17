# 本地视频服务：推理代码与开源框架选型

2026-11-17。范围是当前 BF16 FastH3 Omni 与 Open-H3-Regenerate-2K-IC 的 2K／4K 服务，调查代码可维护性和性能替代，不迁移线上框架。用户已取消回滚，继续采用已验证的数据搬运优化。

## 结论

**有更完整的开源实现可以减少手写代码，但没有找到已经证明能在这台单卡上，以当前全部计算设置直接替换整套服务并显著加速的方案。**

- **替换手写 Python 搬运层：优先研究 Diffusers 原生 group offload／Accelerate。** 维护收益明确，不能把它当作 4K 去噪大幅提速方案。
- **Omni 专用性能候选：UniServe。** 同一 FastH3 团队的 BF16 发布页推荐它；但当前是 preview，公开单卡 Omni 数据主要在 GB200，不能当成本机 RTX 6000D 的成绩。
- **成熟服务框架候选：SGLang Diffusion。** 已有该 BF16 Omni 的明确配方；2K／4K IC 仍需独立后端或新适配。
- **覆盖完整可视工作流的候选：ComfyUI＋IC 社区节点。** 支持现有模型家族，生态更完整，但 IC 插件本身较新，默认工作流也不等同当前精度与采样合同。

以上为源码与官方文档调查结论，未在本机安装或验收这些候选。已有服务继续运行。

## 本机基线与替换边界

| 层 | 当前实现 | 可替换范围 |
| --- | --- | --- |
| HTTP 与网页 | FastAPI、Gradio | 成熟通用框架已在使用；改 HTTP 语言不会减少 DiT 的注意力计算 |
| 排队与显卡生命周期 | Python 调度器、SQLite、systemd、GPU 独占锁 | 任务持久化、依赖、按模型分组、等待公平性和故障暂停需逐项保留 |
| Omni | FastVideo，固定上游 `a0e6cf1` | 可比较 SGLang、UniServe、vLLM-Omni、ComfyUI |
| 2K／4K IC | NVlabs/Sana IC 入口，PyTorch＋Diffusers | 可比较官方 offload 工具、ComfyUI IC 节点；不是普通 H3 文生视频配方 |
| 底层算子 | CUDA、PyTorch SDPA、BF16 DiT、原版 36 层 FP32 VAE | 内核、精度和解码器差异会影响数值或质量，需单独核对 |

实际环境：RTX 6000D，85,651 MiB 显存，PyTorch `2.12.0+cu130`，Diffusers `0.42.0`。96 GB RTX PRO 6000 或 GB200 的配方不能直接视为相同显存条件。继续保留 80 GiB 单任务、88 GiB 聚合限制，完全本地且无开机自启。

本机测得：4K 单层 26.633 秒中 SDPA 为 23.629 秒，约 88.7%。数据搬运优化后为 26.101 秒，2K 为 7.866→7.348 秒；真实输入第一层约 18.59 亿个 BF16 输出完全一致。原生 5.167 秒 4K 基线全流程为 77 分 47 秒，优化后全片未重新测时。证据见 [性能记录](../deployments/video-generation/deployment/video-queue/4k-exact-performance.json)与 [4K 验收](../deployments/video-generation/deployment/video-queue/4k-validation.json)。

因此，**减少 Python glue code 有维护价值；解决主要耗时需要验证注意力／模型执行路径，不能只替换 HTTP 包装。** 这是基于本机分项计时的判断。

## 1. Python 搬运层：Diffusers／Accelerate

Diffusers 提供 `enable_group_offload`／`apply_group_offloading`，支持按 block／leaf 搬运、CUDA stream 预取和 `record_stream`。Accelerate 的 `cpu_offload` 能保留一份 CPU state dict 并按需装载，`cpu_offload_with_hook` 适合阶段循环。这些是当前手写 hooks 最直接的上游替代。[Diffusers 文档](https://huggingface.co/docs/diffusers/main/en/optimization/memory)、[Accelerate 文档](https://huggingface.co/docs/accelerate/main/en/package_reference/big_modeling)。

适用性仍要核对 IC 的未合并 `LoRALinear`、Sharp 曲线 buffers、动态 timestep 和 tiled VAE。Diffusers 官方特别提示 stream 预取可能显著增加 CPU 内存；本机不能照抄可能需要约两倍模型内存的配置。`low_cpu_mem_usage` 会改变内存与速度取舍。

判断：优先用于减少自维护代码和获得上游修复。未找到此模型、本卡、此内存限制下的可复用性能对照；基于 88.7% 注意力占比，不能预期仅搬运层就带来数量级加速。

## 2. Omni 专用候选：UniServe

[FastH3 Omni BF16 模型页](https://huggingface.co/FastVideo/FastVideo-FastH3-Omni-8-Step-V1)推荐服务端使用 UniServe。[UniServe](https://github.com/hao-ai-lab/uniserve)由 Rust 服务负责接入、调度和响应，Python worker 执行模型；源码提供 `ref2va`、图片／视频／音频参考和一至八卡配置。

关键边界：

- 发布定位为 preview，不能因为与模型同团队就认定比 SGLang 更成熟。
- 官方已验证 Omni 配方包括单 GB200 和八卡 RTX PRO 6000；不是本机单 RTX 6000D。官方单 GB200 的部分 5 秒参考任务为 22.1–55.35 秒，不是本机预测值。[Serving guide](https://github.com/hao-ai-lab/uniserve/blob/main/docs/minimax_h3/minimax_h3.md)、[Omni 评测](https://github.com/hao-ai-lab/uniserve/blob/main/docs/minimax_h3/evaluation.md)。
- `quality` 默认 DiT／编码器 BF16、视频 VAE FP16；与当前 IC 的原版 FP32 解码合同不同。检查点表没有现成的 Open-H3 4K IC 服务。
- 宣传中的部分加速比来自 FastH3 V2 和多卡测试，不能转用为 Omni 或 4K IC 的成绩。[官方性能文章](https://haoailab.com/blogs/uniserve-fasth3/)。

判断：值得优先做 Omni 性能对照；显存、阶段卸载、解码精度与单卡参考规模必须先核对。尚不能直接替换当前整个双模型服务。

## 3. 整体服务候选：SGLang Diffusion

官方 cookbook 明确支持 `FastVideo/FastVideo-FastH3-Omni-8-Step-V1`：Ref2VA、八次 PDD 前向、tile-128 VSA，并说明检查点映射及图像／视频／音频条件。公开 Omni 数字包括 2×H200 常驻 39.0 秒、开启三项 offload 后 43.8 秒，以及 4×B200 10.3／15.3 秒；这些是参考图、768 短边、124 帧的暖请求数据，不是本机成绩。[官方 Omni 配方](https://github.com/sgl-project/sglang/blob/main/docs/cookbook/diffusion/MiniMax/MiniMax-H3.mdx#fasth3-omni-ref2va-8-step-pdd)。

判断：成熟服务化生态中值得优先验证的候选。调查的 H3 cookbook 没有 Open-H3-Regenerate-2K-IC 配方；保留当前 IC 后端比把普通 Ref2VA 误当作 4K IC 更实际。迁移还要验证既有异步任务、上传 ID、跨服务依赖和单卡排队语义。

## 4. vLLM-Omni

已有 FastH3 Omni 及单卡指南；支持模型表将这条 BF16 Omni 路线标为 **Experimental**。vLLM 本体的成熟度不能直接等同该新扩散模型适配的成熟度。[模型支持表](https://docs.vllm.ai/projects/vllm-omni/en/latest/models/supported_models/)。

公开 RTX PRO 6000／5090 单卡示例默认是 NVFP4 QAD 和 fast-8L 解码器；4090 示例采用在线 FP8。可切 quality-36L，但该示例仍是量化解码器，与当前 BF16 DiT＋原版 FP32 VAE 不同。[单卡指南](https://github.com/vllm-project/vllm-omni/blob/main/recipes/FastVideo/FastH3%20RefOmni%20Single%20Card.md)。

判断：有现成 HTTP API 和单卡工程支持，但不是当前质量合同的即插即用替代，调查配方也没有当前 4K IC 的同条件成绩。

## 5. 完整工作流候选：ComfyUI＋IC 节点

FastVideo 官方提供 BF16 Omni 的 ComfyUI 格式权重及原生参考生成工作流；官方也明确指出 ComfyUI 的布局、采样器和内核可能导致输出与 FastVideo／UniServe 不同。[官方 ComfyUI 模型说明](https://huggingface.co/FastVideo/FastH3-Omni-Comfy)。

IC 社区实现至少有两类值得核查：

| 实现 | 已提供的功能 | 对本机对照的限制 |
| --- | --- | --- |
| [slmonker/ComfyUI-OpenH3Regenerate2KIC](https://github.com/slmonker/ComfyUI-OpenH3Regenerate2KIC) | IC `up3/up4/hf8`、草稿转 2K、API 工作流、4K 参数说明、LoRA 转换工具 | 示例包含转换 BF16 LoRA、量化编码器和 fast VAE；不能直接当成原运算相同 |
| [ThomasUK888/ComfyUI-OpenH3-Regenerate-IC](https://github.com/ThomasUK888/ComfyUI-OpenH3-Regenerate-IC) | 原始 IC LoRA 映射、非裁剪 Ref2VA＋HyperFlow、FFN 分块、4K 两次潜变量放大 | 默认 2-step；公开 2K 约 215 秒采用 2-step＋稀疏注意力，和当前 3-step dense 合同不同；也不是其已验证的本机 4K 数据 |

另一个 [rdh9616/ComfyUI-Open-H3-Regenerate](https://github.com/rdh9616/ComfyUI-Open-H3-Regenerate)主要是非 IC 的 FL2VA refiner＋Turbo＋Sharp，并提供 24 层蒸馏 fast VAE。它虽然也能输出 4K，不能被误认为当前 Ref2VA IC 管线的同模型替代。

判断：如果目标是统一网页、可视流程、模型管理与现成节点，ComfyUI 最接近现成功能组合。IC 插件仍是近期社区适配，整体框架成熟不代表插件同等成熟。还需保持完整 BF16 编码器、原版 36 层 FP32 VAE、`up3` 和密集注意力再比较；当前 API 的模型名和自动按模型分组规则也需要适配。

## 6. 其它推理实现

- [LightX2V H3](https://github.com/ModelTC/LightX2V/tree/main/scripts/minimax_h3)：已有完整 H3、Ref2VA、单卡 block offload、未量化示例和 HTTP 服务。文档支持 LoRA `separate`，也说明合并舍入、参考预处理及注意力内核差异。未在本次文档检查中找到该 Omni PDD／4K IC 的完整现成配方，不视为可直接替换。
- [DiffSynth-Studio](https://github.com/modelscope/DiffSynth-Studio)：已有 H3 基础生成、参考生成与低显存支持，适合进一步核对；NF4 等数字不能用来推断当前 BF16 模型速度。尚未找到这套 IC 的同条件基准。
- [NVlabs/Sana Sol-Engine](https://github.com/NVlabs/Sana/tree/sol-engine/models/minimax_h3)：硬件优化配方公开 3.56–4.52 倍等结果，结合 Sol-Attn、缓存和解码优化。这不是纯 HTTP 包装收益，也不是本机 IC 对照。当前 IC 本来就来自同仓库的 [IC 实现](https://github.com/NVlabs/Sana/tree/sol-engine/models/Open-H3-Regenerate-2K/IC)，不能用另一模型／配方的速度冒充 IC 升级效果。

## 建议的验证顺序

1. 保留当前服务合同与已采用优化，框架切换另做隔离候选，不改线上名称。
2. Omni：比较 UniServe 与 SGLang 的同 BF16 权重、同参考预处理、同八次前向和匹配解码设置；先完成本机显存和 80／88 GiB 内存准入核对。
3. IC：比较 ComfyUI IC 插件与当前官方路径，使用相同输入、`up3`、密集注意力和原版 36 层 FP32 VAE。把 4K 支持、实际速度、画面保持及 15 秒窗口成片分别验收。
4. 如果要求仍是逐元素完全相同，任何更换内核、融合 QKV、LoRA 转换、解码精度或缓存跳步都先做原运算对照；“同 BF16”不能替代位级验证。若以后只要求视觉质量相当，应另定义质量基准，不追认成计算结果相同。

调研资料来自以上维护者的仓库、模型页和官方文档；未使用帖子或转述数字作为本机性能证据。当前可直接使用的部署代码在 [主仓库普通子目录](../deployments/video-generation/README.md)。
