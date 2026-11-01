# OpenCode 真实源码试点：2026-11-01 阶段记录

首阶段冻结截至13:07:58 UTC已核实的两轮结果；后到的不限步运行另附在本页末尾，不改首阶段证据。环境为Windows、OpenCode **1.19.5**、当前共享端点和模型别名。此前1.18.31的[只读重测](local-model-framework-research-2026-11-01.md#修复后的原生工具调用重测)保持原记录；版本升级本身不追授新版本的编辑或业务能力。[脱敏证据](evidence/2026-11-01-opencode-business-pilot-stage.json)保存阶段起止、有效内容TTFT范围、工具delta时间及reported usage汇总，逐POST原件留在执行机器。

## 真实目标与权限

用户授权在一项尚未完成的组合增长测试上试用文件检索、影响分析和窄编辑。只允许修改三个指定测试文件；实际生产者、接口祖先及原始源码引用只读。命令、Git、外部目录、网络工具和业务动作均被拒绝，禁用外部插件、分享和snapshot。必要编译与测试仍由源码owner独立执行。

本试点使用原生assistant/tool历史，没有API层`response_format`。实际请求已核`temperature=0`、`enable_thinking=false`、SSE及`include_usage=true`；第一轮每次最多4,500输出tokens，第二轮8,000。CLI的JSON事件格式只用于本机留证，不是API JSON输出约束。共享三消息调用器及其生产合同没有改变。

完整顶层字段审计还发现SDK把`maxOutputTokens`和`maxRetries`作为额外wire字段转发；标准`max_tokens`也存在。服务返回200只证明接受了这些请求，不能证明额外字段被服务使用，或`maxRetries: 0`控制了客户端的所有重试。代理本身没有重试或回退；实际未出现传输故障也不能证明其它失败场景的策略。

## 两轮已经发生的结果

| 阶段 | 实际请求与工具 | 结果与归属 |
| --- | --- | --- |
| 初轮，CLI墙钟39.562698秒 | 12次POST均HTTP200/DONE；11次tool_calls终态、最后一次stop；6次glob和9次read完成，无重复文件读取 | 配置的12步预算消耗于检索和读取，没有编辑。最终分析中的回调归属、内外层栈坐标和寄存器域建议有源审错误，未采用 |
| 唯一有界语义续行，CLI墙钟21.296830秒 | 4次POST均HTTP200/DONE；3次tool_calls、最后一次stop；原15项tool调用及结果均保留在实际上下文 | 模型尝试编辑，但前两次授权文件调用被owner权限配置误拦；随后外部路径调用被正确拒绝。源码前后字节不变 |

两轮没有代理重试、回退或传输失败。HTTP数包含一次会话中的多次模型往返，不能写成16个独立业务任务。tool_calls是一次完整工具请求，仍需实际工具执行及源码验收；stop和CLI退出0也不代表目标已经实现。

## 接入缺口与修正

第一份适配配置缺少自定义模型的`temperature: true`能力元数据。即使agent设为0，该组合也可能不发送temperature；独立审阅在首个POST前发现并修正，实际wire随后确认了0。旧通用命令shim还曾指向过期安装，本机帮助命令失败后改用实际已安装版本。这些属于客户端准备成本。

编辑受阻的直接原因由实际权限日志确认：无Git工作区的权限模式相对OpenCode的worktree根求值，既不是相对启动工作目录，也不是输入的绝对路径。适配器只允许了后两种形式，因此实际模式落入默认deny。**这不是Windows斜杠本身的问题**，该版本的匹配器会归一化分隔符。

修正应从实际求值模式生成三个文件的精确allow，继续拒绝其它路径；不能用放开整个目录、外部目录或所有编辑来解决。配置解析成功只证明schema合法，不能证明权限匹配正确。[1.19.5编辑入口](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/edit.ts)、[权限求值](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/permission/index.ts)及[匹配器](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/core/src/util/wildcard.ts)与执行机器日志共同支持这一定位。

## 成本及当前授权

客户端首次可核准备至初次Ready为309秒；独立审阅和接入修正至下一Ready为121秒。源码owner另报告131.527773秒准备区间；权限定位后的新客户端恢复观察区间为116秒。Root更早的准备起点为12:42:12 UTC，部分此前读取、通知等待没有精确起点，不能记为0。这些区间有重叠，描述的是墙钟跨度，不能相加冒充持续人工工时或关键路径。

用户随后明确要求撤掉迭代步数、总POST数和整个会话的墙钟硬停止，观察自然工具闭环。新的恢复配置已准备：不含steps或maxSteps、不设总POST和整体wall上限，保留每次响应8,000输出tokens、每个HTTP180秒超时，以及原三文件权限和零代理重试/回退。实际重复或错误按观察处理，不用另一种总量cap替代12步。新用户授权与技术恢复单列；本阶段冻结时，后续自然闭环结果仍待观察。

截至本阶段，已证明传输、文件发现、读取和真实上下文续行；**没有成功编辑、源码采用、编测或速度收益**。权限误拦不能作为完整正确接入下的模型实现失败。候选、工具执行、owner源审和软件结果继续分级，最终结果另增记录，不回写本阶段。

## 后到记录：两轮不限步运行均已自然结束

用户的新明确授权取消了steps、总POST数和整个会话的墙钟停止；第三、四轮均未设置这些上限，也没有被人工kill。第三轮保留每次8,000输出tokens、第四轮16,000，每个HTTP仍为180秒。第四轮从已经结束的第三轮实际session继续，保留前面已执行的编辑；这次恢复与诊断单列，不是传输重试。两轮所有HTTP均200/DONE，没有代理重试、回退或传输错误。

| 阶段与实际CLI区间（UTC） | 实际模型往返 | 实际工具与未完成部分 |
| --- | --- | --- |
| 第三轮，13:08:07.813829–13:17:37.519212；569.705383秒 | 27次POST/27次END；17次tool_calls、10次length，没有stop | 6次编辑工具成功：数据fixture4次、host fixture2次；Book未变 |
| 第四轮，13:27:16.160712–13:33:41.543261；385.382549秒 | 13次POST/13次END；10次tool_calls、3次length，没有stop | 另有2次数据fixture编辑成功，8次read完成；Book仍未变 |

八次成功编辑是工具实际应用的候选，**尚不等于八处源码被验收**。截至本次追加冻结点，源码owner获准在另一集成目录接管缺失的Book和必要纠错，独立源审、diff及编测仍待完成。没有模型产出的完整Book，没有业务动作或速度收益；目前也没有证明净节省owner时间。[第二份脱敏证据](evidence/2026-11-01-opencode-business-pilot-unlimited.json)保留各轮usage、TTFT、工具执行状态和权限范围。

四轮合计56次实际POST/56次END：41次tool_calls、2次stop、13次length；本次冻结时在途0。四个CLI区间相加为1,015.947460秒，约17分钟，包含重复会话上下文的reported usage另列。这不是56个业务任务，也不是整项任务的端到端耗时或持续人工工时；准备、审阅、恢复和验收不能从成本中省掉。

两次CLI均自然退出0，最后一个HTTP均为length且没有工具delta，不能称完整收尾。该版本[会话循环](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/prompt.ts#L1047-L1072)允许非工具响应在finish不是tool-calls或unknown时结束，源码没有排除length；实际终态与此分支吻合。我们没有记录到实际执行分支，不能据此猜测隐藏步数上限或doom-loop原因。

## 默认deny也可能遮住内部错误反馈

截断的工具参数没有被拼成候选。第四轮最近一次带工具delta的length实际请求是对Book的`edit`：参数24,183字节，未闭的`newString`约254行，未观察到完整`oldString`。它不是已完成的小hunk；所查长行没有精确重复，仍不足以证明是重复退化或语义正确的大实现。最终一次length连工具delta也没有。这里只在同一原始SSE内组装参数作诊断，不补引号、闭括号或跨回答拼代码。

模型实际收到的错误却是内置`invalid`工具不可用，原JSON解析错误没有回传。本次配置使用默认deny，却没有单独允许这个纯诊断工具。版本源码表明：[registry始终注册invalid](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/registry.ts#L198-L237)，[权限过滤](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/permission/index.ts#L185-L198)与[请求工具准备](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/llm/request.ts#L194-L200)会按该默认deny移除它；[LLM修复回调](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/session/llm.ts#L281-L308)又把失败参数改交给invalid。于是修复目标也不可执行，解析错误被二次“工具不可用”覆盖。

这是由实际日志和版本源码共同支持的**owner接入配置缺陷**，不能写成OpenCode固有无法反馈详细错误。`activeTools`本来就从发给模型的列表中隐藏invalid，因此wire没列它不是故障证据；内部工具表需保留它。[该工具的实现](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/invalid.ts)只返回传入诊断，不操作文件或业务。下一次配置应仅显式允许这个诊断工具，同时保留默认deny和三个文件的精确编辑权限；此项修复目前只有源码依据，**没有新live验证**。本任务不再发第五次笼统CLI续行。

两轮实际REQUEST的完整顶层字段仍包含标准`max_tokens`和额外的`maxOutputTokens`、`maxRetries`，后两者不是凭配置推测。服务200只说明接受请求，不证明额外字段的含义；实际零重试不能验证所有SDK失败路径。cached tokens仍未报告，保持null。原生工具历史增长也不改变普通三消息调用器的合同。

## 后到成本与状态勘误

第三轮准备观察区间为13:05:23–13:07:19的116秒，已在首阶段记过，不能重复累计。第四轮准备为13:24:45–13:26:33的108秒，其中包含不必要的完整隔离缓存复制；后续恢复应保留结束后的DB证据，复用不属于证据的包缓存。准备中曾在慢复制结束前读取依赖文件，产生三次本地缺文件错误；精确进程查询也有一次本地命令语法错误，均属owner成本，不归模型。

13:18的错误侧观察没有先读已存在的CLI终态，误把第三轮说成仍在运行；13:23核终态后已纠正。真实END是13:17:37.519212，拟议的精确停止没有执行，kill为0。旧观察原件保持，END之后的通知和排查延误不计模型在途。后续报告先读真实terminal，再核每个POST的BEGIN/END，不能用目录数量或旧“在途”消息续算。

准备、独立审阅、诊断、复制和通知等待分别记墙钟区间；缺精确起点的部分保持未知。这些区间重叠，不相加冒充持续人工工时或关键路径。接下来按实际交付推进owner集成和必要验证，模型已应用部分与owner新写部分分别署名，后到结果另附，不追认本阶段完成。
