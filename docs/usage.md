# 使用本地模型执行源码任务

从真实、尚未完成且能独立验收的任务开始。调用器负责发送候选请求、保存传输证据和配置内的重试；读取业务材料、应用源码、执行测试及发布结果仍由拥有相应权限的执行者负责。

2026-11-04 当前优先级：用户要求“不用强行维持60并发了，以项目推进为准”。HTTP、OpenCode和云端岗位按真实积压、owner成本、服务负载与Runtime资源窗动态并行；不为数字补位，阶段完成正常END。历史60记录不改，现有capacity/profile/活跃caller不自动切换，详见[并发规则](concurrency-and-retries.md)。

能力边界按实际执行流程长期分开维护：[普通HTTP候选模式](capability-http.md)与[OpenCode原生工具模式](capability-opencode.md)。运营owner和接班worker使用[长期运营prompt](../prompts/capability-operations.md)，每个真实任务及环境变化后追加证据、采用和成本，不在三任务试点结束后停止跟踪。模型端点和模型别名仍只取共享配置；运营prompt用于有相应工具和业务权限的owner，不替换普通调用器的固定源码候选system模板。

## 入口与配置

共享配置为 [config/executor.json](../config/executor.json)，调用器为 [scripts/call.py](../scripts/call.py)。脚本使用 Python 标准库；迁移验证实际运行于 Windows Python 3.13，不能据此声称其它平台已实测。

新 `ATTEMPTn-CONTENT.txt` 按最终 SSE `delta.content` 拼接文本的 UTF-8 字节用二进制模式保存，保留 LF、CRLF 和 Unicode，不经过平台文本换行转换。原始 SSE、固定三消息、瞬时重试和半截流弃置规则照旧；历史 CONTENT 不重写，旧 Windows 行尾差异继续由[离线审计器](http-evidence-audit.md)严格分开报告原样与 LF 投影。修复及 witness 见[客户端字节保存记录](evidence/2026-11-03-http-content-utf8-byte-preservation.json)。

修改共享 caller 时，先在 owner 的候选中完成完整语法解析和与改动相称的必要 witness，通过后再显式原子投影至共享 checkout，避免并发启动的消费者读到半编辑或语法错误。这不要求新审批、逐 POST ACK 或重跑全量旧测试。消费项目的运行 caller/配置由其唯一 owner 在实际空窗按明确来源同步；更新共享仓库不自动修改活跃业务副本。Git 源码行尾与物理 checkout 也可能不同，消费前记录本次实际字节版本，不把规范化后的 Git SHA 当作每份副本 raw SHA。

客户端每天首次使用本地模型前必须完成[OpenCode每日版本检查](client-maintenance.md)：版本低于registry最新稳定版或共享最低版本时，先通过pnpm更新并核实。当前调用器CLI已接入；OpenCode和其它直接HTTP或嵌入式客户端需在自己的任务入口调用共享检查器。同日成功缓存共用；失败由宿主AI自主排障修复，复查通过后继续原任务，维护修复本身不受版本前置限制。

当前指定服务为 `http://192.168.1.11:8080/v1`，模型别名 `qwen38-coder`，使用 `POST /chat/completions` 与流式 SSE。该地址属于指定局域网；各机器自行满足路由与代理条件，不自动回退历史地址或端口。模型别名是服务报告的标识，不是已核实的权重版本、量化方式或硬件配置。

共享服务无需密钥，调用器默认不发送认证头。第三方客户端强制要求 API key 时可用 `local`；若服务后来启用认证，通过配置指定的环境变量提供凭据，当前为 `LOCAL_MODEL_API_KEY`。调用器只将其用于 Authorization 请求头，不把密钥写入 REQUEST。不要把密钥放入源码前缀、示例文件或版本库。

在仓库根目录，先看帮助与示例：

```text
python scripts/call.py --help
```

准备好获准的真实任务文件后，使用新任务标识与唯一输出目录：

```text
python scripts/call.py examples/task.json example --output .local-model-evidence/example --machine-id my-worker --owner worker
```

这条命令展示 CLI 形状。发出真实 HTTP 前，将示例内容、任务名和身份改为本次真实工作；不要为连通率或调用配额反复请求示例。示例材料见 [examples/task.json](../examples/task.json)。

| 项目 | 选择顺序或默认值 |
| --- | --- |
| 配置文件 | `--config` → `LOCAL_MODEL_CONFIG` → 脚本所在仓库的 `config/executor.json` |
| 任务证据目录 | `--output` → 兼容的第三个位置参数；未指定时为输出根下的 task ID 目录 |
| 输出根 | `--output-root` → `LOCAL_MODEL_OUTPUT_ROOT` → 当前工作目录下 `.local-model-evidence` |
| 机器标识 | `--machine-id` → `LOCAL_MODEL_MACHINE_ID` → 当前主机名 |
| owner 标识 | `--owner` → `LOCAL_MODEL_OWNER` → 兼容的第四个位置参数 → 当前用户名 |
| 停止文件 | `--stop-file` → `LOCAL_MODEL_STOP_FILE` → 输出根下 `STOP-NEW-HTTP.json` |

显式配置、请求文件和输出路径按命令的工作目录解释；spec 内的 `source_files`、`stable_source_path`、`task_path` 等材料路径则相对 **spec 文件目录**。默认配置从脚本所在仓库定位，不受当前工作目录影响。复制其它机器的绝对路径、解释器位置或证据根，不是跨机器配置方式。

旧的 `REQUEST TASK OUTPUT OWNER` 位置参数形式仍兼容。新任务应显式选择本机身份和目录；已有 `EVENTS.jsonl` 或持久 `DISPATCH.claim` 的目录拒绝再次派发，不能通过删除证据文件来覆盖或恢复任务。一次调用器内部的传输重试使用本任务目录，重新启动一个逻辑任务则选择新的目录。

本地证据写入失败会停止调用，不作为网络重试理由。RAW文件成功打开后才记录本次`POST_BEGIN`并调用网络；结果的`post_invoked`只表示已进入网络调用，不证明服务端收到请求。RAW失败而其它目的可写时仍尽力保存失败RESULT/SUMMARY；若这些证据也不能保存，则以诊断和非0结束，不能视为成功或重新派发业务。具体分类见[重试规则](concurrency-and-retries.md#重试分类)。

## 组织实际输入

调用器接受由源码列表和任务文件组成的 spec，也接受完整请求对象。spec 可使用有序 `source_files`，或预先拼好的 `stable_source_path`，并给出 `task_path`。文件必须真的存在且包含模型需要的内容；向没有文件工具的模型提供另一份答复的文件路径，不能替代源码正文。

`source_files`已按给定顺序读取每个完整文件并加入文件边界标记，不必再手拼同一份大前缀。`stable_source_path`适用于已有完整前缀；两者同时提供时，当前实现优先读取`stable_source_path`，不会合并`source_files`。只有路径、SHA或文件清单的manifest不能替代实际源码正文。调用器保存实际REQUEST及尝试证据；逐文件冻结/SHA可使用owner已有manifest，当前不会自动生成依赖闭包或替owner选择直接声明者。

准备成本先区分材料发现、影响/声明闭合与机械装配。[一个真实准备案](evidence/2026-11-02-source-preparation-cost.json)的495.262745s包含过宽初筛和旧导航missing；所选11文件用现有调用器离线重装后与原REQUEST完全一致。毫秒级重装已排除发现工作，不能拿它减去原墙钟宣称节省；先在下一真实任务测出机械瓶颈，再决定是否改现有工具，避免重复封包器或自动递归收全仓。

实际请求固定为三消息：

1. `system`：配置中的逐字固定 `system_template`，由调用器归一。
2. `user`：确定顺序的完整当前源码和合同，通常依次为共享声明、相关生产者与消费者、目标源码。
3. `user`：本次具体任务、允许的修改范围、真实诊断及唯一输出要求。

源码改变时更新真实前缀。复用真正未变的材料，不为缓存保留旧实现、填充无关文件或混入时间戳等无关元数据。执行者身份、尝试号和证据目录通常留在请求外的日志中。

发出请求前核实本次角色的输入闭包：

- 沿目标类型的 `extends` / `implements` 找到要实现或调用成员的直接声明者，把完整继承声明、方法签名、返回类型、record accessor 和相关重载放进实际源码消息。manifest 列出文件名不代表请求已经包含内容。
- 提供真正的当前生产者、调用者和消费者。名字相近、同文件中的另一接口或另一角色的完整前缀，不能替代本次接口。
- 明确目标是整类、一个完整方法、有限 JSON 数据还是有界补丁；精确说明 fully qualified 类型与产物角色。纠正轮也保留完整当前声明，不依赖上一轮聊天历史。
- 明确观察范围、未知字段、合法分支、数值宽度和验收条件。十六进制写 `0x`；不能从窄返回值恢复未知高位，或为未知状态填默认值。

独立见证应先从原始输入和合同冻结预期，再与候选核对。若已向模型提供 owner 的 oracle、目标实现或逐步期待矩阵，记录提示程度，不能再称为独立推导。已有成熟机械框架可以复用，但本次实际生成的方法和 owner 支持部分分别计量。

## 输出与实际参数

每次指定有限整数 `max_tokens`；当前调用器校验范围为 `1..16000`，拒绝布尔值。这是调用器约束，不是模型能力上限。小修改优先请求精确方法或有界 old/new edits；不要求重吐全部未变文件。

默认请求为 `temperature=0`、`enable_thinking=false`、`response_format.type=json_object`，并强制开启 `stream=true` 与 `stream_options.include_usage=true`。以实际配置及保存的 `REQUEST.json` 为准。

spec 只转发调用器明确列出的参数。额外 API 参数需使用完整请求对象，并检查实际 REQUEST 是否包含该字段；不能因为输入 spec 写了某参数，就宣称服务已收到或参数已生效。

输出合同只保留一种活动要求。JSON 外壳与任务中“不要 JSON”相互冲突时，先修 owner 的请求。用文字描述字段必须包含的真实实现，不放可被原样回显的 `completeJava`、`completecpp` 或文件名占位示例。完整类的声明也不能带无方法体的 private 构造器原型。

在冻结 SPEC、发布 metadata 或 POST 前，把任务文字与本次实际 `response_format` 对齐。普通 HTTP 使用默认 JSON 对象时，新的完整 Java 任务须明确要求一个 JSON 对象，其中 `complete_java` 字符串包含完整源码及所需 package、imports、类和方法体；其它语言指定相应的源码字段。多文件任务明确每个文件的路径和完整源码字段，或采用有界 old/new edits。此时不能同时要求 raw-only 或“不要 JSON”。这是 owner 的准备检查；现有 metadata publisher 的字段校验不等于已实现任务文字的语义检查。

若冲突在实际 POST 后才发现，保留原 Task、REQUEST 和尝试，不为格式订正回写原件或重发已闭请求。完整 stop/DONE 的 JSON 中若有完整源码字段，可按实际字段提取后另作源码审阅；格式张力与独立可证的代码错误分别记录。length 仍整份丢弃，不提取半稿或续接。OpenCode 原生 assistant/tool 模式按其实际接口交付，不套用普通 HTTP 的 JSON 源码字段要求。

## 消费候选

每个新 RESULT（及 SUMMARY/ATTEMPT_END 同份结果）含 `json_syntax`：只有完整收取的 `stop`/DONE 才给严格 `VALID`/`INVALID`，length 或部分流为 `UNKNOWN`。附加分类最多读取1MiB UTF8；字节超限、解析资源上限或不可编码文本为 UNKNOWN。拒绝 NaN/Infinity；错误仅固定 class、line/column 与零基 Unicode 字符 offset，不含正文或异常消息。top-level 类型只描述语法，不检查任务所需 schema，`semantic_review` 始终为 `OWNER_REVIEW_REQUIRED`。

旧 failure/success/candidate_complete、adopted 和重试条件保持原行为；例如旧解析器接受 NaN 时 candidate_complete 可为 true，而新严格元数据为 INVALID。任何字段都不授语义或采用许可。旧 RESULT 缺该字段时记 UNKNOWN，需要时对原件运行现有离线审计，禁止因元数据缺失重发已闭请求。先读机械字段/完整文件机器解析，再作语义审阅；显示尾段或自然语言未完不能作为 JSON 语法错误证据。

先核完整 SSE 终止、`finish_reason=stop`、可解析输出以及真实代码内容。只有路径、蓝图、占位值、被截断的源码或不符合目标角色的类，都不能按完成实现采用。HTTP 200 和调用器退出 0 仅证明本次传输及候选格式条件，不证明源码正确。

随后按实际改动复核 API、分支、状态传播、副作用及验证代码本身。拒绝恒真比较、未调用目标的模拟、吞异常后成功、假读值与跳过必要分支。应用有界补丁时核唯一匹配、声明作用域、名义类型和最终字节；编译通过也不能替代语义检查。

保留原请求、各次尝试、审阅与 owner diff。分别标明原样采用、部分采用、owner 修正、拒绝、未编测、有限验证和正式发布；之后的新回执另加记录，不改冻结证据。完成与改动相称的必要验证后，不为统计重复旧绿或补发已闭合任务。

## 权限与实现边界

共享服务曾因缺少tool parser拒绝自动或强制工具选择。2026-11-01 11:26 UTC，用户修复服务后，OpenCode1.18.31实际完成两文件只读原生工具闭环：模型生成两条read调用、客户端执行并回传两个tool结果、下一次响应stop。该新结果补充历史拒绝，范围和重复读取等限制见[工具重测](local-model-framework-research-2026-11-01.md#修复后的原生工具调用重测)。

`scripts/call.py`仍是三消息候选调用器，不解析delta.tool_calls，也不接受tool_calls终态为完整源码候选，不提供assistant/tool多轮执行。工具重测使用独立受控客户端和明确的本轮授权；普通源码调用仍按本页合同准备实际材料。JSON输出约束与原生工具选择应分别验证，不把一次HTTP200、正确标量或CLI退出0当成整体源审通过。

OpenCode1.19.5已进入[真实源码试点](opencode-pilot-2026-11-01.md)，使用独立原生assistant/tool适配，不向API强加JSON模式。权限需按该版本实际求值的worktree-relative路径核对，不能只验证配置解析。初轮只读和续行的权限误拦均保留；用户随后授权该试点取消steps、总POST及整段wall上限，继续有限单次输出和单HTTP超时。此授权不改变普通三消息HTTP调用器，也不授编测、Git或业务操作。

默认deny还需核内置诊断是否被误禁：该版本参数修复会调用`invalid`，内部可执行工具表应保留它，不能仅因发给模型的工具列表没有它就判故障。后续真实任务中，显式允许后已执行两次invalid；但巨大的原参数嵌入错误文本，又被通用工具输出截成文件指针，关键parse错误仍未出现在可见结果。因此这是[部分修复的实际证据](opencode-pilot-2026-11-01.md#扩展三个真实任务后到阶段记录)，不是完整诊断闭环恢复。继续保留命令、外部目录和业务deny；CLI退出0或stop不代表任务正确，报告活跃状态先核实际terminal，编辑仍需owner源审和必要验证。

源码生成、运行期决策、外部动作和发布各自服从消费项目的 owner 与权限。模型 HTTP 的重试只重发候选请求，不能重放业务动作。公共日志不提交原始私有材料；执行细节保存在执行机器，公开规则与脱敏证据。

### 生成原生OpenCode配置

[scripts/opencode_config.py](../scripts/opencode_config.py)提供纯函数`build_config(executor, *, workspace, worktree, owned_files, max_output_tokens=16000)`，也可只读取共享executor并把配置输出到stdout：

```text
python scripts/opencode_config.py --executor config/executor.json --workspace D:/review/task --worktree D:/ --owned-file src/change.py
```

这里的路径是形状示例。调用者提供本次实际可信的绝对workspace/worktree及精确相对文件名；脚本不发现Git、不启动OpenCode、不发HTTP、不执行每日维护或写生成文件。维护仍由真实模型入口执行。它计算相对worktree的精确编辑模式，拒绝越界、跨盘、遍历和模式扩张，显式保留invalid诊断及默认deny，不转发SDK控制项。

38项新离线测试及OpenCode1.19.5实际`--pure debug config`已通过，但只证明纯生成逻辑和配置解析/合并；不证明该生成配置在新会话中的wire或权限执行。Windows主机上的PurePOSIX用例也不代表POSIX CLI实测。词法验证不证明symlink安全，raw非Git`/`上下文与Windows路径坐标`D:/`的边界含义需按当前客户端核对，详见模块docstring和[采用/成本回执](evidence/2026-11-01-opencode-config-delivery.json)。现行普通调用器和活跃业务配置没有自动切换。

配置迁移及历史来源见 [来源与迁移记录](source-origins.md)。

零owned文件的只读审计使用独立的[只读配置生成器](../scripts/opencode_readonly_config.py)与[接入步骤](opencode-readonly.md)，不把原编辑入口放宽为空scope。实测恢复时项目父配置可覆盖显式配置；须隔离环境、禁止项目配置并核实际合并结果。读取工具已执行不等于分析完成，该新案例没有最终审计答案或采用。

已有原生记录可离线运行 `python scripts/audit_opencode_trace.py TRACE_DIR`，自动核 REQUEST 参数、工具 ID 配对、同参数/同结果重复、grep 顺序变化和 read 范围/显式字节 cap。默认不输出正文或业务路径，不重发 HTTP、不停止进程；格式与未知项见[只读日志审计器](opencode-trace-audit.md)。

已有普通三消息 HTTP 证据使用 `python scripts/audit_http_evidence.py EVIDENCE_DIR` 的[离线审计入口](http-evidence-audit.md)。它按固定文件名和显式读取界限核实际参数/消息 SHA、逐 attempt 的 finish/DONE、外层 JSON 语法及记录的 TTFT/总耗时；缺失为 UNKNOWN，冲突与原始行尾差异单列。外层 JSON 有效、STOP、语义完整和 owner 采纳分别记录；不再按肉眼看到的末句判断 JSON 格式，也不把有效 JSON 当分析正确。默认无 raw 正文/业务路径，不重发或执行任何请求。


宿主只有shell本地读入口时，每个read exec cell先定义本机已核的固定reader/显式解释器argv前缀，数据路径只作参数。构造后执行前强核首token、完整前缀、总长度、data槽和有限range完全相等，拒绝shell字符及工具尚不支持的引用形式；不得再用raw命令或覆写cmd绕过检查。授权helper/Git另构造，不把JSON/MD/PY数据路径当执行入口。这个[本机构造及负例记录](evidence/2026-11-03-owner-read-command-prefix-guard.json)只说明19个不合法构造未启动进程及一次JSON正确打印，不是跨机shell安全框架/业务审批。


新源码任务需要高并发有界等待时，可显式选择`--config config/source-high-concurrency.json`（read600/total2400），保留实际REQUEST、配置SHA与每次BEGIN/END。该完整投影只用于后继新任务，不更新已冻结/在途请求、耗尽同题或活跃业务caller；共享默认仍不变。具体时限并非独立总墙钟watchdog，见[并发和时限](concurrency-and-retries.md#新任务的显式高并发时限配置)。当前用户目标为60真实在途rolling，CLI启动、退避与已排队任务分别计；新工具源码候选尚须owner审阅及必要离线验收。


后继新源码任务可显式选择`--config config/source-high-concurrency-direct.json`：同一endpoint/model/三消息与六次重试，read600/total2400，并使用独立`ProxyHandler({})`禁用该opener的环境代理。`network.proxy_mode=direct`必须提供与base_url hostname相等的`direct_host`，不带URL凭据/query/fragment；该模式拒绝所有redirect。当前缺network默认DIRECT，host从可信base_url取得；只有显式environment才兼容环境代理。共享executor与高并发profile均已明示DIRECT/currenthost；旧冻结证据和在途进程保留原行为。REQUEST-PREPARATION、POST_BEGIN和RESULT记录所选network_routing，actual_peer仍UNKNOWN；选定直连策略不证明socket peer、服务健康或旧失败根因。

直连选择在dispatch创建证据目录前校验，按owner候选完整parse和5项新无网络mock后原子投影。旧在途进程/REQUEST/重试body、Runtime与消费项目副本不改；只有未来新任务显式选新profile。真实两项未闭源码任务用于首网络验证，响应/语义另审，不能把离线mock当服务恢复。[源码、验证与当时切点](evidence/2026-11-03-http-explicit-direct-routing.json)。


用户后续明确指出局域网模型不应默认经过代理，因此DIRECT现已是共享入口和配置默认。消费项目更新caller/配置时显式记录来源；旧进程、旧frozen REQUEST/profile和Runtime副本不自动热切。仅旧HTTP测试的mock/loopback夹具显式选择environment以保留原验证范围，不代表业务默认仍走代理。默认修正新增3项无网络case与2项改变的配置/兼容case通过，未重旧全量绿；实际DIRECT首两请求仍600秒无headers超时，未证明应用服务恢复或代理唯一根因。[默认修正后见](evidence/2026-11-03-http-default-direct-routing-correction.json)。


## 只读具名 HTTP 事件观察器

[scripts/pool_observer.py](../scripts/pool_observer.py) 是纯离线观察器，只读明确给出的 EVENTS.jsonl，不导入 caller，也不读取 REQUEST、SSE 或候选正文。它不派发请求、不补位、不取消请求；目前不能作为持久 rolling dispatcher 使用。

准备一个不超过64 KiB的 JSON 数组，每项明确给出唯一 `id` 与 `events_path`，例如：

```json
[{"id":"source-a","events_path":".local-model-evidence/source-a/EVENTS.jsonl"}]
```

然后运行 `python scripts/pool_observer.py registry.json`。相对事件路径按当前工作目录解释。每个文件默认最多读取1 MiB、5000行；最多256个具名流，不扫描目录。退出0表示事件证据完整可配对，退出2表示缺失、截断或冲突使汇总未知，均不授模型语义或采用许可。API为 `observe_stream(path)` 与 `observe_registry(records)`。

报告按实际 POST_BEGIN／ATTEMPT_END 构造半开区间，单列退避、开始前取消、headers、有效内容TTFT、finish/DONE及语法元数据。同一时刻END与新BEGIN不双计。缺END只记未配对证据，进程是否仍存活、服务是否收到请求均UNKNOWN；不能据进程结束补造END。缺文件、重复、冲突、无时区、乱序或未完整换行的最后一行会令当前与峰值汇总UNKNOWN。全局区间截止于最早的逐文件观察时刻；读取非原子且未证明各机器时钟同步，不能用它宣称整个服务或未登记请求的状态。

[本次来源与验证](evidence/2026-11-03-http-pool-observer-length-owner-implementation.json)：模型observer输出length整弃未读，owner独立实现；11个新无网络测试，另4份现成具名日志18POST/18END原件不改。其他dispatcher组件尚未交付，不把观察器发布当作持续60已实现。


## 纯待派任务准入选择

[scripts/pool_admission.py](../scripts/pool_admission.py) 提供 `select_pending(pending, occupied_source=..., occupied_runtime=..., capacity=60, reserve_runtime=1, last_owner=None)`。它不执行任务，也不读写文件、发HTTP或传服务priority。输入是至多256条明确任务记录，每条恰含 `id/owner/spec_path/task_id/output_path/config_path/machine_id/lane`；lane仅source或runtime，id须唯一，计数不接受bool或负数。返回selected、保原输入顺序的remaining和limits；输入不修改。

先选择待派runtime，再按source owner轮转，保各owner内部顺序；last_owner之后的owner先取。两lane共用一个剩余容量预算，默认source最多59个客户端准入保留，即使runtime当前未排队也留一个未来位置。已有runtime占用此位置，不再重复扣除。现有超容量只报告并停止新增，不取消已POST请求或改原deadline。

这些占用数是集成方提供的客户端准入保留，不是事件观察器的实际HTTP数。纯函数也不是跨进程锁；真正派发仍需独立原子lease/claim与Runtime owner显式接线。它不保证服务执行slot、抢占或业务延迟。[独立验证记录](evidence/2026-11-03-http-pool-admission-owner-capacity-fairness.json)保模型三项反例与owner7个新离线测试/384种有限容量组合，不重跑旧caller测试。


## 持久客户端准入 lease

[scripts/pool_leases.py](../scripts/pool_leases.py)提供`LeaseStore(absolute_db_path, capacity=60, reserve_runtime=1, max_records=10000)`。使用专用本机 SQLite 数据库与已存在父目录；共享同一数据库的进程由`BEGIN IMMEDIATE`串行核容量，持久配置不一致即拒绝。模块不发HTTP、不启动或停止进程，不自动接入caller或Runtime。

`acquire(token, owner, lane="source", now=..., ttl=...)`返回`LeaseDecision`；只有`newly_acquired is True`代表新准入。相同owner/lane的ACTIVE token只返回EXISTING且不续TTL；bool(decision)会拒绝，避免把幂等结果当第二次派发。到期转UNKNOWN仍占容量，不能重取；`mark_unknown`记录不确定启动。`release(..., verified_no_live_post=True)`仅接受owner对已无实际POST的明确断言，模块本身不能验证此事实。RELEASED token永久留在有限历史中，不再新准入；满历史显式报`LeaseStoreFull`，不清墓碑绕过once。

所有source准入都保留未来Runtime位置，不需先排一个Runtime任务。`get(token)`返回单条有限metadata；`snapshot(now=...)`只给聚合数量并标记CLIENT_ADMISSION_ONLY。时间是integrator输入，不是网络观测；容量不等同实际POST区间、后端slot、服务priority或抢占。持久logical-task claim、准确事件观察及一次派发仍需后续dispatcher显式组合。[本次源码、模型反例与8项新离线验证](evidence/2026-11-03-http-pool-leases-owner-transaction-boundaries.json)不授持续60或实际业务收益。


`snapshot()`另给`occupied_source`与`occupied_runtime`：同一事务中到期转换后，各lane的ACTIVE+UNKNOWN计数，二者和等于occupied，RELEASED排除。它们仍是client admission数据；预留Runtime容量不预留有限history条目，max_records满时仍会拒绝新Runtime。见[新增1项必要离线验证](evidence/2026-11-03-http-client-lane-snapshot.json)，不重跑原8项，不授服务slot或持续60。


## 显式 ready 队列的一次派发与滚动回补

[scripts/pool_dispatcher.py](../scripts/pool_dispatcher.py) 将既有 admission、lease 和 EVENTS observer 接成显式队列。每行恰有 `id/owner/spec_path/task_id/output_path/config_path/machine_id/lane`，绝对路径由可信 owner 提供并冻结；队列最多256行/64 KiB。`id` 是准入 token，`task_id` 是 caller 任务身份，两者分别唯一；输出目录也永久唯一。每个逻辑任务只创建一个 canonical caller CLI，其内部保留全部六次模型 HTTP 尝试。dispatcher 不预建 caller 的 `DISPATCH.claim`，不自行重启失败或 UNKNOWN CLI。

使用独立的 dispatch SQLite 与 lease SQLite 文件，并让全部参与者共享这同一对数据库。`--once` 排空本次 ready 快照，`--queue` 默认循环重新读取显式文件并回补；stop file 同时传给 caller，停止新启动/下一次 POST并收尾本实例已持有的子进程。它不搜索或终止其它进程。空队列循环由 owner 明确 stop 结束。示例 argv 形状：

```text
python scripts/pool_dispatcher.py --queue READY.json --db /absolute/dispatch.db --lease-db /absolute/leases.db --python /absolute/python --caller /absolute/call.py --stop-file /absolute/STOP --capacity 60 --reserve-runtime 1
```

这些路径只是形状示例；Windows 使用本机实际绝对路径。`tick(ready)` 是一次选择/回收，`run_once(ready)` 排空当前快照，`run_file(path)` 持续刷新。仅本实例持有的 Popen handle 与实际 KNOWN、身份匹配、无未配对 POST 的终态可释放准入；退出码本身不是零 POST 证明。进程丢失、缺 EVENTS、半行或不确定派发保守记 UNKNOWN并保留容量，人工核实不能删除墓碑重发。不同进程必须共用持久库，有限历史满与容量不足分别报告。

示例`--capacity 60`和`--reserve-runtime 1`是客户端上限/准入配置，不是固定60目标或必须占满的名额。本次调度优先级更新不修改既有持久库配置、在途参数或Runtime副本；需要调整时由owner另行审阅并明确采用，不为规则文档暂停Runtime/JFR。

源任务保留一个未来 Runtime 客户端准入位置，但未接入活跃 Runtime caller，也不保证后端 slot、抢占或延迟。spec/config/源码内容由可信 owner 冻结；校验路径至子进程读取之间不是原子字节交接。实际源码 canary 已一次完整返回并释放准入，19个主见证是分版本增量通过，另4项在最终选定源码首验通过；不称最终19项一次全绿或持续60已达。原生38次工具请求、模型首失败、owner修正、完整成本和普通HTTP canary分别见[交付记录](evidence/2026-11-03-ready-dispatcher-native-and-first-source-canary.json)。

HTTPError 的响应体读取若发生 OSError/IncompleteRead，现继续写本 attempt 的 RESULT/END/SUMMARY并保留原HTTP状态的重试判断；本地写失败仍不重试。5项新增无网见证与原基线故障分别保留。可按显式入口运行 `python -B scripts/witness_http_error_read.py --source scripts/call.py --result-dir .local-model-evidence/new-http-error-read-witness`；结果目录须为仓库内尚不存在的新目录。已通过的见证不为运营统计重跑。


Windows宿主逐cell只读命令可复用[已验证的V8 factory与显式本机binding](windows-read-command-guard.md)。目标路径只作数据；该片段不自动接入其它worker，也不替代reader源码、文件身份或OS权限核实。


任务spec优先只保留有序`source_files`（或`stable_source_path`）、`task_path`和有限`max_tokens`。文件数、消息条数、SHA清单等业务元数据另放manifest；`messages`是实际消息数组的保留字段，不能写成`messages: 3`计数。前端schema错误发生在POST前时，保原spec和失败记录，修正canonical投影后仍按原唯一逻辑任务首次派发，不把准备失败算模型尝试。

终态读取使用实际`EVENTS.jsonl`中的`ATTEMPT_END`、`ATTEMPTn-RESULT.json`与`SUMMARY.json`；不要因为没有根目录`RESULT.json`就把已结束请求报告为仍在途。先核stop／DONE／完整性再读正文；length整份弃置，不续接或据未读半稿作语义评分。
