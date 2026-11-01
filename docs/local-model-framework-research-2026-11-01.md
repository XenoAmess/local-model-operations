# 本地模型调用优化与框架选型预研

日期：2026-11-01。面向维护共享调用规范和消费项目的 owner。审阅基线为 [`43d297ca930f7f9e4c9a144a46ab5b2d2e12fca8`](https://github.com/XenoAmess/local-model-operations/tree/43d297ca930f7f9e4c9a144a46ab5b2d2e12fca8)，客户端实测环境为 Windows、CPython 3.13.2、OpenCode 1.18.31。

11:26 UTC 更新：用户修复服务后，按其明确要求重测原生工具调用，基线为 [`5f5acc2b9aba9cd48e213873fe3ceccbb7dae605`](https://github.com/XenoAmess/local-model-operations/tree/5f5acc2b9aba9cd48e213873fe3ceccbb7dae605)。新结果另存[工具重测摘要](evidence/2026-11-01-native-tool-retest.json)，08:33 的拒绝记录保持原样。

建议保留现有候选调用器，修正错误重试与流终止处理，并补输入预检、输出合同和审阅记录。**OpenCode 已通过当前服务上的两文件只读工具闭环，值得进入真实任务试点。** 它的潜在价值是减少材料准备和工具衔接的人工成本；模型分析仍有错误，任务完成时间与 owner 净节省尚未计量。Aider 的文本补丁机制也值得评估；单一指定端点下，暂未出现必须增加 LiteLLM 网关或 LangGraph 编排层的需求。

本次交付为预研报告和[脱敏验证摘要](evidence/2026-11-01-framework-research.json)。生产调用器、共享配置和现行三消息规则均保持原版本。后续修复和框架试点按下述验收条件单独交付。

## 当前调用方式

[共享配置](../config/executor.json)指定 `http://192.168.1.11:8080/v1` 和 `qwen38-coder`，默认 temperature 0、thinking false、JSON object、带 usage 的流式 Chat Completions。[调用器](../scripts/call.py)组织三消息，读取实际源码和任务文件，保存请求与各次传输原件，最多进行六次总尝试。源码应用、编译、语义验证和 Git 发布由 owner 完成。

这套方式适用于输入已经齐全、目标产物有界、需要核对原始候选的工作。固定请求体、完整请求重试、半流丢弃、唯一证据目录以及 HTTP 与业务动作分离，都应继续保留。它的主要人工成本在任务依赖闭包、候选验收和后续结果登记；现有脚本没有实现这些环节。

已有公开实证分别报告过 70,998 和 91,867 输入 tokens，cached tokens 均为 null。这说明出现过大输入请求，不能证明全部上下文都有必要，也不能证明缓存有效。依赖材料遗漏、owner 夹具错误和模型语义错误已有不同案例，因此优化应同时覆盖输入质量和验收成本。[单次 SSE 实证](evidence/2026-11-01-windows-service-call.json)、[断流恢复实证](evidence/2026-11-01-windows-transient-retry.json)、[能力边界](capability-boundaries.md)保留了各自范围。

## 调用器边界验证

同一会话前序检查已运行现有 15 项离线测试，全部通过；源码未变，未为报告重跑旧绿。补充验证使用本仓库 `tests/test_call.py` 的本地 HTTP fixture，或受控的 loopback mock。下表是行为刻画，不代表生产修复已经完成。

| 观察 | 实测行为 | 判断 |
| --- | --- | --- |
| 仅使 `ATTEMPTn-RESPONSE.sse` 打开操作抛 `PermissionError`，其它文件正常写入 | 实际 6 次 POST、6 次 attempt，退出 1 | 本地证据写入失败落入传输重试分支，会重复请求模型 |
| 完整 stop / DONE，候选分别为 `null`、`[]`、占位 JSON | 三种均退出 0，`success=true` | 当前成功条件只覆盖解析，不覆盖目标输出合同；不能据此自动采用 |
| 完整 stop / DONE，候选为字面量 `NaN` | 退出 0，`candidate_complete=true` | Python 默认 JSON 解析接受该非标准值，当前校验并不严格 |
| spec 增加 `frequency_penalty=0.3` | 实际 request 无此键；无需发 HTTP 即可观察 | 参数被静默忽略，容易使参数实验归因失真 |
| 显式设置 `response_format.type=text`，返回普通文本 | 一次 POST 后以 `invalid_candidate_json` 退出 1 | 请求参数可选格式与本地固定 JSON 校验没有闭合 |
| 完整 stop / DONE 已到达，HTTP 正文尾部延迟 0.2 秒，读取超时设为 0.05 秒，总尝试设为 1 | `sse_done=true`、`finish_reason=stop`，仍因读取超时失败，约 55.61 毫秒结束 | 收到应用层终止后仍等 HTTP EOF；特定尾部延迟会丢弃已完整候选 |

表中的 `null`、`[]`、占位 JSON、权限错误与未知参数结果来自前序终端回执，其临时 fixture 目录已清理；新补充验证的执行 helper 和摘要保存在执行机器。真实服务请求和 OpenCode wire 记录则另行保留。公开摘要明确区分这些来源，不将临时 mock 回执写成长期保存的真实模型原件。

### 错误分类与流终止

[`dispatch` 的异常分支](https://github.com/XenoAmess/local-model-operations/blob/43d297ca930f7f9e4c9a144a46ab5b2d2e12fca8/scripts/call.py#L145-L221)同时覆盖网络和本地证据写入。建议把本地文件错误从 HTTP 重试判定中分离：保存失败应停止新 POST，并保留能够写出的诊断；网络错误按明确类别及共享配置重试。错误字符串名称当前只是策略描述，并不是已执行的白名单匹配。

收到 `[DONE]` 后，应按已定义的 Chat Completions 终止合同结束读取，同时保留对 finish、usage 和已收内容的校验。上述尾部延迟是 mock 兼容性场景，尚未观察到当前真实服务因此失败。修复时需要保留“缺 DONE”“缺 finish”“无 LF 的截断 JSON / UTF-8”和“完整畸形 event”之间的区别。

### 输入与输出合同

[`prepare_request`](https://github.com/XenoAmess/local-model-operations/blob/43d297ca930f7f9e4c9a144a46ab5b2d2e12fca8/scripts/call.py#L46-L87)已检查消息角色、模型和有限输出预算，但 spec 只转发固定白名单。建议增加配置与 spec 校验，未知字段立即报错，并提供不发 HTTP 的 dry run：展示最终 API 参数、材料顺序、源码字节摘要、Git 版本及输出要求。

输出合同应区分 API 参数和本地验收：JSON object 至少检查对象类型、必填字段及类型；补丁还需检查文件范围、唯一匹配和完整代码。普通文本模式若要支持，应配置对应的本地验证路径；若不支持，应在 POST 前拒绝。严格 JSON 校验还应拒绝 `NaN` 等非标准常量。

现有 `success` 已被[使用指南](usage.md#消费候选)限定为传输与格式条件。因此这里应新增可区分的结构校验状态，保留“未审”“已验证”“已采用”的独立记录，避免把格式通过提升为实现正确。占位内容的语义判断仍需要 owner；简单字段校验不能取代源审。

## 08:33 预研时的服务与 OpenCode 结果

### 服务声明与工具调用拒绝

08:31:50 UTC，`GET /v1/models` 返回 HTTP 200，包含 `qwen38-coder`，声明 `owned_by=vllm`、`max_model_len=1048576`。这是服务元数据，不是权重、后端构建版本或最大可用上下文的验证。`GET /health` 返回 HTTP 200 和空正文；owner helper 首次误按 JSON 解析，随后仅对 health 修正记录方式，不将这个解析错误归为服务异常。

08:33:58 UTC，一项尚未完成的预研源码审阅通过当前调用器发送真实请求：三消息包含当前调用器、共享配置和现有测试；任务检查完整请求参数组合的处理。请求上限为 1,800 输出 tokens，保留默认 temperature 0、thinking false、JSON object，并声明一个可选的只读研究资料工具和 `tool_choice=auto`。

服务在约 98.65 毫秒后返回 HTTP 400，错误为：

> "auto" tool choice requires --enable-auto-tool-choice and --tool-call-parser to be set

这次只有一项逻辑任务、一次 POST，没有重试、fallback、工具执行或生成候选。实际客户端区间为 08:33:58.595248–08:33:58.694506 UTC，在这一项真实 POST 的范围内峰值为 1、持续 0.099258 秒；它不是服务推理并发或容量测试。TTFT、usage 和 cached tokens 均为 null，不能把错误响应耗时当作生成延迟。

这条记录证明08:33时该请求的工具选择路径未获支持，不能据此评价模型推理能力。11:26修复后的原生只读闭环见下节；旧HTTP400不再用作当前接入障碍。后续服务变更仍需核实后端版本、模板与匹配的parser，不从模型别名推断，也不自动切换历史端口。

### OpenCode 客户端工具循环

OpenCode 1.18.31 使用自定义 `@ai-sdk/openai-compatible` provider 连接本地 mock。实验设置独立配置和数据目录、provider allowlist、相同的主模型与 small model、显式标题、两步上限、512 输出 tokens，以及仅允许 `read` 的权限；禁用分享、snapshot 和外部插件。mock 声明的 32,768 context 是客户端实验值，不是本地模型能力结论。

| 实验 | 模型 POST 与实际消息 | 结果 |
| --- | --- | --- |
| 自定义模型未声明 temperature 支持，agent 设置 temperature 0 | 两次 POST；首次 `system / user`，第二次 `system / user / assistant / tool / assistant`；均 `tool_choice=auto` | CLI 退出 0，`read` 完成一次；实际请求没有 temperature 字段 |
| 模型 metadata 增加 `temperature=true` | 同样两次 POST；实际请求均包含 `temperature=0` | CLI 退出 0，`read` 完成一次 |
| 完成 read 后，让第二次模型请求返回一次 HTTP 503 | 三次 POST；第二、三次解析后的请求 body 相等 | CLI 退出 0，read 只完成一次；观察到这一条模型 HTTP 恢复路径 |

三组中都实际发送了 `max_tokens=512`、`chat_template_kwargs.enable_thinking=false` 和 `stream_options.include_usage=true`。第三组比较的是捕获并解析后的 body，不是逐字节网络包相等。这些结果证明本机客户端可完成受控的读取和后续模型请求，并揭示了参数声明要求；回答由 mock 提供，不授真实模型的工具选择、分析或编辑能力。

初次预研观察到的OpenCode请求形状与当时服务拒绝的 `tool_choice=auto` 一致，因此当时没有继续重放。以下重测在用户报告服务修复后进行。OpenCode的六次总尝试策略、半流丢弃、取消和写操作幂等性仍需专项验证；一次mock 503后read未重放不证明其它业务动作安全。

## 修复后的原生工具调用重测

本轮使用相同端点、模型别名及OpenCode1.18.31；原生assistant/tool消息仅用于用户明确要求的工具重测，生产三消息调用器和共享配置没有改变。两次服务GET返回HTTP200；模型元数据仍只作声明保存。四个诊断场景共7次真实模型POST，全部HTTP200并有完整SSE终态，没有传输重试或fallback。

| 场景 | 实际结果 | 采用判断 |
| --- | --- | --- |
| 三消息、auto工具选择，同时保留默认JSON object输出 | 一次stop，原生工具调用0；三个配置值正确，要求由工具读取的SHA-256错误 | 证明旧HTTP400已消失；未完成工具任务，错误哈希拒绝 |
| 去掉API层JSON格式约束，并增加真实纠正诊断 | 三次均为tool_calls；实际读取配置、调用器，又重复读取调用器，达到三轮上限 | 工具选择、参数与工具结果回传可用；未自然结束 |
| 从含前两次实际工具结果的已保存请求分出有界收尾 | 增加收尾指令并设tool_choice=none，一次stop；端点、模型、最大尝试数、配置文件原始字节SHA-256四项均正确 | 四项标量核对通过；不是原auto对话自然收尾，分析正文另有源审错误 |
| OpenCode读取当前配置和使用指南的字节一致快照 | 首次响应一次发出两条原生read调用，客户端分别完成；第二次请求带两个tool结果，随后stop，CLI退出0 | 当前服务上的限定只读工具闭环通过；摘要只作部分参考 |

OpenCode这两次POST实际包含temperature0、thinking false、有限1,800输出tokens和usage请求，没有API层response_format；消息分别为 `system / user` 和 `system / user / assistant / tool / tool`。首轮首次tool delta约514.48毫秒且content TTFT为null；第二轮首次有效content约788.14毫秒。工具delta时间不冒充内容TTFT，cached tokens均为null。

这些结果支持当前模型生成原生调用、客户端执行真实读取、模型消费tool结果并完成限定任务。初轮JSON模式与后续请求还同时改变了纠正诊断，因此不能断言单一格式参数就是因果。直接auto路径的重复读取也说明客户端需要步数上限、重复动作检查和明确收尾条件。

生成文字仍须逐项验收。有界收尾虽正确使用工具哈希，却错称tool_calls终态先走JSON解析、错把spec白名单的限制扩大到完整请求对象。OpenCode摘要也需要owner澄清历史parser状态与当前能力、模型生成调用与客户端执行的区别，以及默认参数并非所有请求不可变的约束。代码采用0，不授整体审阅批准。

本次实际POST窗口为11:22:50.477410–11:26:26.119449 UTC，结束在途0、客户端峰1；峰值累计14.459854秒，最长连续3.358481秒，窗口平均约0.067055。原生工具执行共5次，均为读取。未采样服务running / waiting / KV，也没有写入、命令或真实失败注入；不从这组结果推出持续并发、恢复策略或业务动作幂等性。

对项目的价值判断从“接口受阻的候选框架”提升为“值得优先试点的源码执行工具”。最先评估资料检索、影响范围分析和窄补丁：owner提供任务目标、写权与验收，OpenCode承担文件查找和反馈衔接；真实声明闭包、语义验收、业务动作与Git发布仍由相应owner负责。只有在真实未完成任务上减少端到端时间和owner修正成本，才扩大使用。

## 框架选择

| 方案 | 能解决的主要问题 | 与当前规范的关系 | 建议 |
| --- | --- | --- | --- |
| 保留并增强当前调用器 | 有界候选请求、精确传输留证、跨机器调用 | 三消息与重试边界已明确 | 继续作为默认路径，优先修已复现问题 |
| OpenCode | 文件检索、编辑、命令执行及反馈循环；可用 SDK 接入 | 原生消息历史超出三消息；只读闭环已实测，仍需正式合同及证据适配 | 优先进入真实任务试点，随后验证限定编辑与恢复 |
| Aider | 仓库地图和文本编辑格式，减少手工组装与应用补丁 | 同样会改变提示和编辑流程；repo map 不能替代实际声明闭包 | 当目标主要是补丁交付时并列评估，尚无本机运行证据 |
| LiteLLM | 多 provider 的统一网关入口 | 增加一跳和配置层；现有策略禁止自动 fallback | 出现多端点治理需求后再评估 |
| LangGraph | 持久、有状态的自定义流程编排 | 仍需实现源码准备、工具和验收逻辑 | 出现明确的持久恢复需求后再评估 |

OpenCode 官方提供[工具](https://opencode.ai/docs/tools/)、[权限](https://opencode.ai/docs/permissions/)及 [SDK](https://opencode.ai/docs/sdk/)；这些是减少 owner 机械操作的潜在来源。它不会自动补足语义正确性，也不能仅凭会话结束证明源码采用。复杂状态、ABI 或跨回调合同仍应按实际候选和验证结果决定分工。

Aider 支持 [OpenAI compatible 端点](https://aider.chat/docs/llms/openai-compat.html)、[仓库地图](https://aider.chat/docs/repomap.html)及[文本编辑格式](https://aider.chat/docs/more/edit-formats.html)。由其编辑机制推断，它值得用于评估文本补丁流程；这不是已验证的本地模型兼容性。若试用，关闭默认的 auto commits 和 dirty commits，保留唯一 Git 写者。[选项说明](https://aider.chat/docs/config/options.html#--auto-commits)

[LiteLLM 网关](https://docs.litellm.ai/docs/simple_proxy)面向统一 provider 入口；[LangGraph](https://docs.langchain.com/oss/python/langgraph/overview)面向有状态编排。当前仓库的具体缺口可以先通过小范围客户端改动和离线汇总解决，引入这两层的维护收益尚待实际需求支持。

## 优化顺序与验收

下列项目按可独立审阅的单元实施，完成必要验证即提交推送。它们是实施建议，不是已交付功能。

| 顺序 | 改动 | 必要验收 |
| --- | --- | --- |
| 1 | 分离本地 IO 错误与可重试网络错误 | 原件保存失败停止新 POST；429 / 503 等仍按共享策略；不改变业务动作边界 |
| 2 | 按 `[DONE]` 终止合同结束读取 | 完整流的尾部延迟不再使候选失败；缺终态和截流仍失败且不拼接 |
| 3 | 配置和 spec 校验、dry run、格式合同 | 未知参数和格式冲突在 HTTP 前可见；严格 JSON / 字段校验各自可观察 |
| 4 | 材料 manifest 和追加式审阅记录 | 源码路径、Git 版本、原始字节与实际 prompt 投影哈希分开；审阅关联原候选，不回写旧快照 |
| 5 | 离线事件汇总与按需的 deadline / 取消 | 在途区间、峰值持续时间和未知终态正确；不增加每次 POST 的中央 ACK 前置 |
| 6 | 在已通过只读路径上推进OpenCode真实任务试点 | 验证限定编辑、失败恢复与收尾；参数、重试、消息合同和结果分级均有实际证据 |

材料准备可先辅助查找 `extends`、`implements`、调用者、callee 和常量声明，再由 owner 确认任务闭包。裁剪无关文件时，所选源码和合同仍需完整、当前；不能用文件名、摘要或 repo map 代替缺失成员。共享 system 也可按语言维护稳定 profile，减少当前 Java 模板在其它语言任务中的不匹配，同时维持服务配置的唯一来源。

当前 `total_seconds` 是每次尝试的行间检查，停止文件也不会立即打断睡眠或阻塞读取。如果消费项目需要严格任务截止，再增加覆盖重试与退避的总 deadline，并区分连接、空闲读取和任务墙钟；不要将既有参数改名后宣称已实现硬截止。

结果登记至少关联逻辑任务、attempt、请求哈希、输入缺口、候选错误、owner 修正、验证范围和发布 commit。编译、测试与发布回执追加保存。汇总可以异步读取各 owner 目录，不能变成所有真实请求的中央派发门槛。

## OpenCode 真实试点设计

只读工具重测通过后，使用自然到来、尚未完成且有独立写权的任务进入试点。如推广到常规源码工作，应在共享规则中明确agent模式的消息、工具及审阅合同；本轮用户授权的工具重测不自动改写生产三消息模式。不会仅为比较框架而重投已闭合任务。

接入应从共享配置生成版本绑定的适配配置，记录来源 SHA，避免维护另一个手工端点。OpenCode V1 使用 `provider`、`npm`、`options.baseURL`；V2 文档使用 `providers`、`package`、`settings`，不能混用。[V1 provider 文档](https://opencode.ai/docs/providers/#custom-provider)、[V2 model 文档](https://opencode.ai/v2/docs/models#compatible)

后续客户端版本维护按用户新增的[每日检查与AI恢复要求](client-maintenance.md)执行：每日检查latest，过低用pnpm更新；失败由宿主AI自主修复并复查。每轮试点继续记录实际版本和配置，原有1.18.31实测保持其历史范围，不把日常升级当作新版本已通过业务验证。

本次 mock 已验证的配置要点是：自定义模型显式声明 temperature 支持，才能在本组合中转发 temperature 0；通过模型 options 发送 thinking flag；设置有限输出预算；限制 provider，并固定主模型和 small model。small model 会参与标题等辅助工作，配置文件也存在合并规则，因此应审实际生效配置和 wire 请求。当前两次或三次 POST 的观察有显式标题及两步上限，不能用作所有会话的固定请求数。[配置说明](https://opencode.ai/docs/config/)、[agent 步数与参数说明](https://opencode.ai/docs/agents/)

传输适配必须能记录每次实际 REQUEST、BEGIN/END、首有效内容 TTFT、usage、错误和工具动作的独立事件。会话事件可作为补充，是否足以保留所需传输原件需要核验。若使用旁路记录代理，它只负责留证，不另加重试或 fallback；一个模型 HTTP 的重试由一个明确的策略负责。

试点先使用读取和限定文件编辑，验证后再引入实际需要的编译命令。多个会话按文件分工，禁止自动创建分支或 worktree；stage、commit、同步和 push 仍由唯一 Git 写者串行完成。模型请求重试、语义纠正和工具动作分别计数。

采用决策应按同类任务分别比较以下指标：

- 从输入准备到验收完成的墙钟，以及 owner 在准备、审阅和修正上的实际时间。
- 首轮可用程度、具体采用单位、owner 修改和输入合同遗漏。
- 每逻辑任务的模型尝试数、辅助请求、tokens、截断与真实失败原因。
- 有限验证的正负场景、最终发布结果、工具越界或业务动作重放。

不同复杂度任务之间只能作描述性比较；需要因果结论时另行设计可比条件。只有实际减少 owner 成本且保持验收和留证要求，才扩大框架使用范围。本次尚无节省比例、质量提升或吞吐收益的实证。

## 证据与复核入口

[验证摘要](evidence/2026-11-01-framework-research.json)保存源码版本、Git blob 与执行文件的独立 SHA-256、前序测试口径、新补充 mock、三组 OpenCode 捕获摘要和真实服务拒绝。原始源码请求、SSE / CLI 原件、机器状态及私有路径保存在执行机器，不作为其它机器的启动依赖。

复核调用器可使用现有 `tests/test_call.py` fixture 构造上表条件；复核 OpenCode 时使用同版本 CLI、本地 OpenAI compatible mock 和只读 fixture，分别观察首次工具请求、带 tool 结果的下一请求及一次 503 后的恢复。模型 POST 应始终指向 mock，不能把可重复的协议测试变成真实服务刷请求。

08:33的HTTP400与初次mock摘要保持冻结；11:26的原生工具重测另有[完整分级摘要](evidence/2026-11-01-native-tool-retest.json)。Aider、限定编辑、失败恢复、复杂任务语义质量、持续并发、缓存和端到端收益仍待对应真实任务验证。
