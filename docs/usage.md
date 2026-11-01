# 使用本地模型执行源码任务

从真实、尚未完成且能独立验收的任务开始。调用器负责发送候选请求、保存传输证据和配置内的重试；读取业务材料、应用源码、执行测试及发布结果仍由拥有相应权限的执行者负责。

## 入口与配置

共享配置为 [config/executor.json](../config/executor.json)，调用器为 [scripts/call.py](../scripts/call.py)。脚本使用 Python 标准库；迁移验证实际运行于 Windows Python 3.13，不能据此声称其它平台已实测。

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

## 组织实际输入

调用器接受由源码列表和任务文件组成的 spec，也接受完整请求对象。spec 可使用有序 `source_files`，或预先拼好的 `stable_source_path`，并给出 `task_path`。文件必须真的存在且包含模型需要的内容；向没有文件工具的模型提供另一份答复的文件路径，不能替代源码正文。

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

## 消费候选

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
