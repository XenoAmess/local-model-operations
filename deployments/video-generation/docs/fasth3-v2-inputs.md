# FastH3 V2 输入参数与参考素材支持

调查日期：2026-10-27。本文针对本机部署的 `FastVideo/FastVideo-FastH3-8-Step-V2-NVFP4-Consumer`，FastVideo 源码版本 `a0e6cf1f5086c9af735d73e6c0b80dbc1d5817b3`。

## 结论与验证范围

本机已实际验证的是文字生成视频和同步音频。V2 模型卡将其支持范围定义为 T2AV，并明确说明 FL2VA（首尾帧生成）和 Ref2VA（参考素材生成）未做蒸馏。本地模型的 `fastvideo_inference.json` 也声明 `task: t2av`。

通用 API 的字段比当前模型的已验证能力更广。代码中存在首尾帧图片处理路径，不能仅凭字段存在就承诺当前 V2 的图生视频效果。

| 输入方式 | 本机代码与模型支持范围 |
| --- | --- |
| 文字提示词 | 支持；已完成本机视频及音频生成验证 |
| 一张图片作为首帧 | 请求适配器接受，进入首帧处理路径；当前 V2 官方未蒸馏 FL2VA，本机尚未进行生成效果验证 |
| 两张图片作为首帧、尾帧 | 请求适配器接受，最多两张；同样属于尚未验证的 FL2VA 路径 |
| 任意多图作为人物、场景或风格参考 | 当前 V2 没有已验证的 Ref2VA 支持；需要相应参考模型和管线 |
| 参考视频 | 当前请求适配器拒绝，要求 Ref2VA 管线 |
| 参考音频 | 当前请求适配器拒绝，要求 Ref2VA 管线 |

官方另一项目 UniServe 的能力表将 V2 列为同时支持 `t2va` 和 `fl2va`。这表明首尾帧路径存在于官方运行框架中，但它与 V2 模型卡的蒸馏范围是两种口径；也不能替代本机 FastVideo Consumer 配置的生成验证。

本次只做源码、模型配置和离线请求适配检查，没有启动服务或加载模型。检查结果见 [parameter-audit.json](../outputs/parameter-audit.json)，它验证的是引用字段如何被映射或拒绝，不包含素材下载、端到端生成及质量测试。

## 每次生成可设置的主要参数

接口为 `POST /v1/videos`（异步任务）或 `POST /v1/videos/sync`（同步返回 MP4），支持 JSON 请求。

| 参数 | 作用 | 本机默认值及限制 |
| --- | --- | --- |
| `prompt` | 描述画面、动作、镜头、声音或对白 | 必填，非空字符串 |
| `model` | 选择服务已加载的模型 | `fasth3`，可以省略；传入其他模型名会被拒绝 |
| `size` | 输出宽×高 | 默认 `1344x768`；宽高为 32 的倍数，总像素不超过 1,032,192 |
| `width`、`height` | 分别指定宽高 | 与 `size` 二选一使用；同时存在时 `size` 优先 |
| `seconds` | 请求的视频时长 | 默认 5，整数 5–15；会对齐到合法帧数 |
| `num_frames` | 精确指定帧数 | 默认 124；124–362，且满足 `17n+5`；例如 124、243、362。与 `seconds` 同时传时优先使用帧数 |
| `seed` | 随机种子 | 默认 1234，整数 |
| `aspect_ratio` | 按宽高比计算画布 | 例如 `16:9`、`9:16`、`1:1`，范围 1:4–4:1；设置后会重新计算宽高，因此建议不要同时指定 `size` |
| `short_edge` | 与 `aspect_ratio` 配合的短边参数 | 此路径固定为 768；生成 480p 时直接使用 `size: 832x480` |
| `video_params` | 嵌套传递 `width`、`height`、`num_frames`、`fps` | 通用兼容形式，通常直接使用上面的顶层参数即可 |

采样限制：

| 参数 | 当前模型要求 |
| --- | --- |
| `fps` | 固定为 24 |
| `num_inference_steps` | 保持默认 9：9 个采样点对应 8 次模型计算；改变数值会与训练时的采样阶梯不符 |
| `guidance_scale` | 固定为 1.0，不支持 CFG 调节 |
| `negative_prompt` | 省略或空字符串；非空负面提示词会被拒绝 |
| `n` / `num_outputs_per_prompt` | 固定为 1，每次请求只生成一个视频 |
| `generate_sound` | H3 本身联合生成同步音频，此通用开关不会控制本模型的音频生成 |
| `lora` | 当前服务没有加载 LoRA，因此不能通过请求临时选择 LoRA |

通用协议还定义了 `quality`、`max_sequence_length`、`enable_teacache`、插帧等字段；本次未确认它们能有效调节当前 H3 部署，因此不将其列为已验证的模型参数。`quality: hd` 不会通过当前请求适配器改变输出尺寸。

GPU 数量、NVFP4 量化、CPU offload、VSA 稀疏率、解码后端等属于 [fasth3-v2.yaml](../fasth3-v2.yaml) 中的服务启动配置。当前配置采用 VSA 0.8 和固定的 V2 八次去噪阶梯。

## 首尾帧图片字段

以下仅说明接口结构，尚未进行当前 V2 的图生视频验证：

```json
{
  "model": "fasth3",
  "task": "fl2va",
  "prompt": "A person turns toward the camera.",
  "image_reference": [
    {"image_url": "https://example.com/first.png"},
    {"image_url": "https://example.com/last.png"}
  ],
  "size": "1344x768",
  "seconds": "5",
  "seed": 1234
}
```

一张图为首帧，两张图依次为首帧和尾帧。`input_reference` / `reference_url` 是单张图片的旧字段，不能与 `image_reference` 混用；`file_id` 引用不受支持。显式选择 `task: t2va` 时传图片会被拒绝；`task: ref2va` 在当前管线下也会被拒绝。

素材传输层支持图片 HTTP(S) URL 和图片 Data URL。当前未配置 `server.media_roots`，直接传本机文件路径会被媒体策略拒绝；本机和私网 HTTP URL 默认也被拒绝。这些是当前素材读取配置，与模型是否具备参考生成能力是两个问题。

当前网页 playground 以及项目的 `generate.py` 只提供文字生成入口，没有参考图片和参考视频选项。

## 图片、视频和音频参考生成

需要加载 FastH3 OmniRef / Omni 等专门的参考模型，并配置 `MiniMaxH3Ref2VAModularPipeline`。官方 OmniRef 文档描述的输入为文字加有序参考素材：最多 9 张图片、3 个视频、3 段音频，总计不超过 12 个素材。

当前 V2 服务没有部署该能力。2026-10-30 已另行部署 FastH3 Omni NVFP4 QAD，并在本机 RTX 6000D 上通过图片＋视频参考的实际生成验证。它使用独立的权重、Ref2VA 管线、端口和网页，操作见 [Omni 运维文档](fasth3-omni.md)。

## 依据

- [FastH3 V2 模型卡 Scope](https://huggingface.co/FastVideo/FastVideo-FastH3-8-Step-V2#scope)
- [本机 Consumer 模型卡](https://huggingface.co/FastVideo/FastVideo-FastH3-8-Step-V2-NVFP4-Consumer)
- [UniServe H3 支持表](https://github.com/hao-ai-lab/uniserve/blob/main/docs/minimax_h3/minimax_h3.md)
- [FastH3 OmniRef 官方说明](https://github.com/hao-ai-lab/FastVideo/blob/main/docs/inference/fasth3_omniref.md)
- 本机源码：`FastVideo/fastvideo/entrypoints/openai/protocol.py`、`request_adapter.py`、`media_policy.py`，以及 `FastVideo/fastvideo/pipelines/basic/minimax_h3/stages/`。
