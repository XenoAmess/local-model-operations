# 可复用经验

整理日期：2026-11-01。这里保留会改变操作方法的实测与勘误；完整探索过程见 [历史档案](history/README.md)，采用口径见 [能力边界](capability-boundaries.md)。模型案例使用服务别名 `qwen38-coder`，权重、量化和服务构建版本未固定；性能诊断和调用器测试另列，不冒充模型推理实测。

## 2026-11-02：两种模式长期分别运营

用户明确要求普通HTTP与OpenCode两种模式分别追踪能力边界，并长期运营。现维护[HTTP独立记录](capability-http.md)、[OpenCode独立记录](capability-opencode.md)和[运营prompt](../prompts/capability-operations.md)，AGENTS规定每个真实结果、环境变化及交接时续记，不以三任务阶段结束为停止依据。

按实际生成流程归属案例，不能把OpenCode生成的HTTP调用器修复记成HTTP模型源码成功。分别记录模型语义错误、输入/配置问题、owner fixture与发布流程成本；交付成功不追授模型原稿，也没有严格对照证明某模式整体更省。初始分账只整理已发布证据，没有新模型请求、重测、版本认证或业务动作。今后从真实未完任务更新，不刷请求或重跑旧绿。

## 2026-11-02：按完整产物结构分配有限输出预算

两项真实有限见证共8 POST：一项首轮5500/6000、第二轮各4500，四份都length；另一项首轮4500/5000、第二轮各3500，一份完整stop语义拒绝、三份length。七份截断正文未作语义阅读，整份丢弃且无拼接；两项都转owner完成，没有第三轮或为本记录重投。[HTTP-OUTPUT-001精确请求/终态摘要](evidence/2026-11-02-http-output-budget.json)分开保存预算、完整stop与截断，owner工时未知为null。

第二轮确有缩范围或换DATA：其中一个方法仍要求两个实际场景的完整Java，另一个改为单场景DATA，但有限循环、回调、完整有序观察和最终字节义务仍在。不能写成完全未缩范围，也不能从短提示推断所需输出已足够小；这不是严格预算A/B，更不证明加tokens即可正确。新的完整测试/复杂方法先按实际产物结构估6k–12k有限预算，或在首轮把真实独立方法拆开并复用机械夹具；不能先机械压预算，再把未读length算成语义或永久能力失败。小修改仍按真实产物给窄输出。

随后一个真正新任务在首轮各10000、纠正轮10000/12000下得到四份完整stop，实际completion4182/4662/1984/2019，均未耗尽预算，却全部源审语义拒绝：有稿不调用目标而直接调probe，有稿缺实际输入映射或只作trace包含检查，未实现完整预期状态。两次partial reset由原caller自动重试，半流整弃，不能混入四份完整错误。[HTTP-OUTPUT-002](evidence/2026-11-02-http-complete-witness-rejection.json)记录6 POST、0 length、0采用和owner接管，保留“完整输出”和“语义可用”两项条件；不同任务与新增机械支持不是严格预算对照，也不证明放大预算造成改善。

OpenCode已获不限总步的会话与单回复有限输出是两层控制；不限迭代不会自动补全截断工具参数，也不授权拼接半截源码。按本次真实授权及工具错误恢复，不把某次不限总步观察变成所有客户端的默认政策。此规则仅更新owner操作提示，稳定system、活跃caller和配置未改。

## 请求合同先核实际发送内容

| 日期与观察 | 可复用操作 | 限制与来源 |
| --- | --- | --- |
| 2026-10-31整理：provider 曾因缺少 tool parser 拒绝自动或强制工具选择 | 使用已获支持的普通候选接口；工具循环需要另外实现和验证 | 文本 SSE 成功不授文件读取、测试执行或业务动作能力。[原指南](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L1-L47) |
| 2026-10-31整理：spec 写了 `frequency_penalty=0.3`，实际 REQUEST 没有该键 | 参数实验必须审实际 payload；小 spec 白名单外的参数通过完整请求对象提供 | 该单不能称已执行的0.3实验；服务默认及效果未知，未为补统计重发。[原勘误](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L87-L89) |
| 2026-10-31整理：同三消息的 thinking false / true 请求同时改变了输出预算，SSE 仅见 role / content | 保存实际 flag、预算、并发环境与可见字段；模式实验先定义可观察证据 | 未见 reasoning 不证明内部没有推理；耗时差不是模式或缓存因果，不能补称严格 A/B。[实际对照](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L50-L54) |
| 2026-10-31整理：输出示例中的 `completeJava` / `completecpp` 被逐字回显，无实现 | 只给一种活动输出合同，用文字说明字段装完整源码，不给可照抄占位值 | 记录 owner 提示成本，也保留回答未完成的事实；其它独立语义失败不因此抹去。[占位回显原件说明](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L121-L129) |

长输入不自动需要长回答。曾有完整整类输出重复正文直到 length，改成真正尚未完成的方法或有限 old/new edits 才能控制产物范围；只能采用完整终态的目标单位，不能续拼截断文本。[输出范围与类型角色](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L164-L182)

## 先核每条审计问题，再统计结论

2026-11-01 的两份完整源码审计暴露了独立误报：一份给9个条目标严重等级，后文却逐项自撤为 None / N/A 或说明行为正确，最终确认的可执行模型发现为0；另一份以缓存 key 缺 maximum 为漏洞，却漏看每次 hit 对当前大小限制的校验，还把源码中明确存在的成对句柄预算 guard 说成未检查。这些不是9个缺陷，也不构成“全部正确”的证明。机械流程观察可部分采用，整体批准、源码采用及软件结果分别记录。

每条发现至少给出具体触发序列、被违反的合同、实际源码依据和后果；严重等级、自相矛盾或自行撤回的条目不能替代这些证据。评估缓存时联查 key 身份、每次 hit 前提和当前值域，不只看字段清单；不同语义 profile 或权限仍可能需要独立验证，本例不授权合并所有缓存。依据为执行者保管的 `PORTABLE-AUDIT-FINDING-RULE224.json` 及精确版本源审，见[来源说明](source-origins.md)；没有新的编译、OS 行为或性能结论。

## 声明、预算与状态必须闭合到真实消费者

2026-11-01 的继承闭包案例中，实际前缀漏祖接口，owner 又误写“三方法”；模型按这个合同作答后，首编发现第四个方法缺失，独立源审也曾漏掉。应逐角色、逐纠正轮沿 `extends` / `implements` 找到直接声明者，包含所有成员及名义返回类型，不能只看文件数或 fully qualified 名称。后续 owner 补实现的成本归 owner；输入已补齐后的模型 hunk 则独立署名。[公开继承案例](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L262-L266)

2026-11-01 新增预算案例：caller 将64MiB作为预算参数传给只允许最大8MiB的 callee。callee 先校验参数，小包尚未进入实际大小校验就被拒绝。模型的17文件前缀仍漏了这个 callee，多个 owner 静态审阅和 strict / DTO 验证也未发现问题。迁移后的检查步骤为：

1. 将真实 caller、callee 与 MAX 常量直接声明放进本角色的实际请求。
2. 分别验证参数是否在 callee 的允许范围，以及实际 body 字节是否不超过获准预算。
3. 除纯 DTO 外，通过真实公开捕获入口做一条窄回归，保留原参数拒绝与输入缺口。

这不支持放大所有默认限制、跳过证据校验或宣称性能收益。来源为执行者保管的 `PORTABLE-BUDGET-RULE220.json` 独立摘要，原件 SHA 与公开范围见 [来源说明](source-origins.md)。

同日另一类源审教训是多个不可变 V 快照不会自动共享后续回调更新：必须显式传递实际返回的当前 V / N / DF，不能把入口值当作回调后的已知值。有限投影中的未知字段不填0；没有写入、没有使用返回值，也不能据此删除实际可观察的内存读写。`AND [mem],0` 包含读取和写入，不能任意缩成只写0。[当前状态](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L268-L272)、[可观察的读改写](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L248-L252)

## 沿实际实例和动态调用链审作用域

2026-11-01 的两项真实覆盖审阅中，owner 沿构造、委托与同步回调确认：不同 facade 仍访问同一个 Store 实例及其实例级 ThreadLocal，原指定入口的调用链已经位于有效范围内。不能凭 wrapper、参数或局部变量名称不同就判作用域丢失。逐入口核实际共享实例、当前线程、进入和退出位置，以及消费者是否在这段动态生命周期内执行。

两份模型回答仅部分分析可用；“缓存 hit 仍读完整 payload”、伪造行号及全项目已覆盖的断言被 owner 源审纠正。本例 hit 保留实际身份、权限与边界检查，但不重新读、哈希已保留的完整 payload；metadata 读取、完整读取与缓存 DATA 必须沿实际实现区分，不能由方法名或启动仍慢反推。作用域覆盖也不证明底层 OS 安全或墙钟收益。

原入口已覆盖，不代表新增入口同样覆盖。owner 独立定位另一新增入口的只读遍历在范围外；截至摘要封存，本次交付仅提出最窄文本候选，未采用或编测，不能记成模型发现或性能修复。输入中沿用的旧“待采用”标签另归 owner 版本说明成本；源码相同不证明运行产物已部署。依据为[脱敏摘要](evidence/2026-11-01-scope-callchain-audit.json)及[来源限制](source-origins.md)，不公开业务源码。

## 先审 fixture，再用它评价候选

准确数据形状不能替代有符号比较、字节宽度、物理栈位置和分支可达性。先从原始合同冻结 oracle，再读新目标输出；若向模型提供了逐步期待，署名为“owner oracle → 模型编码”。检查 literal 是十六进制值还是十进制值、宽度单位是 bit 还是 byte，核完整调用帧和 effects 在同一 RAM 上消费一次。不要让实现和测试共享同一错误推导后相互证明。

2026-11-01 的预算回归又暴露了 fixture 的前置合同：原本要复现总包超过1MiB，旧实现却先拒绝了非整数 JSON 值；修正后，单个巨大字符串又先被32,768码点的文本限制拒绝。这两次非零退出都没有到达所称的总字节预算错误。应沿实际委托校验核对合法值域，再用合法短值聚合跨越总量边界，检查真实异常及到达位置；更宽的文本或数字域另作场景。保留原 oracle、原失败与修正依据，不能把任意异常当作指定负例通过。

修正后的同一纯数据 Probe 在冻结旧类上准确触发总预算错误，在新类上通过78项断言：小包773字节、合法短串聚合的大包1,101,610字节、中间包200,935字节，另核单个巨大字符串及负零完整保留。五次 Probe 编译和前两次错误值域的 JVM 失败均保留，未重编生产类；这不是一次原样模型产物通过，也不授真实捕获链、线上或性能结论。模型可见候选生产源码，不能署名为盲生产见证。依据为执行者保管的 `PORTABLE-FIXTURE-BOUNDARIES220.json`，见[来源说明](source-origins.md)。

整数值的比较也要服从实际合同：Jackson 的 primitive int / long 节点与 BigInteger 节点可能表达同一数学整数，却不满足节点存储类型的 `equals`。要求 typed JSON 整数值相等时，先将两侧投影为同一值表示；要求原始字节或数字 token 不变时，仍分别检查，不能用正规化抹去负零或 token 差异。

历史负例也限制“看起来通过”的含义：`byte[].equals` 是对象身份；typed JSON 值相等与原始字节不可变是不同合同；109个 checks 可能只含27个数据 fixture及一个结构断言。正链后追加非法 UTF-8 / duplicate-key 负例，曾找到4个公开异常映射回归。通过时写真实 case、checks、旧红与失败项重跑范围，不能把不同 JVM 的结果改成一次全绿。[实际负合同传播](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L21-L25)、[比较与独立进程问题](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L193-L206)

## 运营证据保留时间与字节口径

一次历史客户端峰14只持续3.540034秒，对应十分钟平均2.0054；它不能替代持续达到并发目标的证据。请求真正结束但迟读、外目录未纳索引、旧 attempt 无终态，都应核目录与截止点后另附重建，不能靠中央表更新时刻判断真实活性。具体区间、峰持续、服务 metrics 与重试口径见 [并发页](concurrency-and-retries.md)。

错误封包也独立计成本：CRLF → LF、缺 EOF、原始 Git blob、实际 prompt 归一文本的哈希分别保存，不能用一个哈希冒充另一个字节对象。已冻结文件被误覆盖时，恢复内容不等于恢复丢失的原始时间戳或原件；保事故、恢复方法与未知。后到回执另附，不改旧“尚未验证”的快照。[换行封包经验](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L164-L182)、[冻结记录与覆盖事故](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L220-L224)

## 2026-11-01：JFR 单个异常权重的敏感度

一次60秒 JFR 记录的数据丢失为0。独立 allocation 摘要含16674个 `ObjectAllocationSample`；其中2026-11-01 05:54:14.780087 UTC 的一个 `boolean[]` 样本 reported weight 为555943805096，占全部采样权重的93.142%。同一 digest / regex 栈另外22个样本的权重合计103069184。这个极端权重必须单列，不能解释为一个数组的实际大小，也不能写成该方法占93% CPU或精确总分配量。

原始样本与完整聚合都保留，再另算排除最大1项的敏感度，明确改变后的分母。用样本数、权重分布、中位数、分位数和其它栈交叉检查；排除一项用于检验排序稳健性，不证明该样本无效。CPU 采样、allocation weight、GC pause 与端到端墙钟是不同指标。

同一记录中122个顶层 pause 事件的区间并集为1.589672秒，约占60秒的2.64945%；98个 GC 事件的总 duration 不能当作停顿。这里 pause raw sum 恰与 union 相等，处理其它记录时仍需显式去重重叠区间。任何性能修改仍需结合真实热路径、等价行为与受控后测；一条样本或候选叙述不授速度提升。

本项由执行者保管的 `ROOT-SHORT219`、`GC-ALLOCATION-SUMMARY219` 与 `WEIGHT-SENSITIVITY219` 小摘要交叉核对；本仓库未上传原始 JFR 或数百MB过滤数据，也没有伪造公开下载链接。摘要 SHA 和来源限制见 [来源说明](source-origins.md)。这是诊断方法经验，不是模型生成正确性实验。

## 2026-11-01：便携调用器迁移的实际验证

本仓库调用器迁移由 owner 实现。一次独立旧源审计请求完整 HTTP200/stop，却错称 length 会走传输重试，并错称6次尝试会越界读取第6个退避项；这两项均由实际控制流和本地 HTTP mock 否定，模型整审计与源码片段采用均为0。不能因为审计响应完整就授正确性，也不能把 owner 的迁移实现算作模型整份代码。

初版13项本地 mock 通过后，Root 继续源审发现无LF尾行中的截断 JSON / UTF-8 被当成一般解析失败。后续明确修订为不完整响应，保本次 partial，下一次从完整请求重发；完整LF畸形 JSON 仍不重试。修订03实际15项通过，独立 JSON / UTF-8 断流子场景核下一候选全来自第二次响应，原13项记录未回写。[已发表调用器与测试版本](https://github.com/XenoAmess/local-model-operations/commit/aa12e525d5f6cb842cae71dabe33071a91794933)

验证范围为 Windows Python3.13、标准库本地 HTTP / SSE mock；迁移验证没有访问真实模型服务或业务系统，没有 POSIX 实跑。当前900秒检查只发生在响应行之间，停止文件也不即时打断睡眠或在途 HTTP；未增加 watchdog。保留这些限制比把一次绿写成完整跨平台、实时或服务兼容性结论更有用。

## 2026-11-01：一次真实服务调用的兼容性证据

离线迁移验证后，新调用器在 Windows / Python3.13.2 对当前指定服务和 `qwen38-coder` 完成一次尚未闭合业务的源码审阅请求，没有为验证补发探针。实际为 `system / user / user` 三消息、`max_tokens=5500`、temperature0、thinking false、JSON输出和带usage的SSE；07:10:20.612664→07:10:39.052066 UTC，一次attempt得到HTTP200、stop和完整SSE终态。响应头9.288958秒、首有效内容9.290448秒、总耗时18.438819秒分别保留；reported prompt70,998 / completion1,347 / total72,345，cached为null。

本项只证明当前调用器在这一环境与参数下完成一次真实服务交换，不证明所有平台或server、最大上下文、缓存效果、通用工具闭环或业务答复正确性。源码审阅及采用仍由业务owner独立判断。公开的[2,211字节脱敏摘要](evidence/2026-11-01-windows-service-call.json)已核实际REQUEST参数、角色和终态标量；未上传原始源码、任务、答复、机器身份或私有路径。摘要哈希见[来源说明](source-origins.md)，原15项离线mock记录不回填。

## 2026-11-01：调用器边界与 OpenCode 接入预研

Windows / Python3.13.2 的补充 mock 表明，本地 SSE 原件写入的 `PermissionError` 会触发最多六次 POST；完整 stop / DONE 后仍等待 HTTP 尾部，也可能使候选因读取超时失败。前者应将本地 IO 与网络错误分离，后者应明确应用层终止合同。JSON 可解析、字段合同合格和语义可用继续分别判断；这些是已观察缺口，本次预研没有修改生产调用器。[报告与优化顺序](local-model-framework-research-2026-11-01.md#调用器边界验证)保留触发条件和来源范围。

08:33:58 UTC时，指定端点对一项三消息预研源码审阅的 `tool_choice=auto` 返回HTTP400，明确要求auto tool choice与tool parser，未重试或fallback。OpenCode1.18.31在本地mock完成只读工具循环；该自定义模型需声明 `temperature=true` 才实际发送配置的temperature0。read之后的一次503恢复只重发模型请求，read未再次完成，但不授其它工具动作幂等性。[初次脱敏摘要](evidence/2026-11-01-framework-research.json)保留当时结果，后续真实工具闭环见下项，不回填旧证据。

## 2026-11-01：服务修复后的原生工具重测

用户明确要求重测后，OpenCode1.18.31在指定端点实际完成两文件只读工具闭环。首轮生成两条原生read调用并分别执行，下一轮包含两个tool结果且stop；共两次POST，CLI退出0。模型负责生成调用，客户端负责执行，二者都不能由回答文字代填。现有三消息源码调用器不具备该执行循环，本次原生消息仅属受控重测。

另有三个诊断场景：JSON object加auto虽HTTP200却没有工具调用且伪填哈希；取消格式约束并给真实诊断后能调用，但三轮内重复读取；从实际工具结果分支设none并要求收尾，四项标量核对通过。参数和诊断同时改变，不授格式单因素因果；最终分析仍含错误，owner仅采用已核事实。合计7次真实POST、5次只读工具动作、传输重试0、代码采用0；峰值与usage另列[脱敏摘要](evidence/2026-11-01-native-tool-retest.json)。这支持OpenCode进入限定任务试点，收益仍以真实任务完成与owner成本衡量。[更新预研](local-model-framework-research-2026-11-01.md#修复后的原生工具调用重测)保留试点建议。

## 2026-11-01：每日客户端维护与 AI 自主恢复

用户要求每个客户端每日首次使用前检查OpenCode，版本过低先用pnpm更新；后续明确修订为失败时由宿主AI自主排障修复、真实复查后恢复原任务。共享检查器、CLI入口与[接入合同](client-maintenance.md)已落实成功缓存、更新锁、AI回调/驱动和结构化恢复交接；维护修复本身不依赖版本预检先成功。

Windows / CPython3.13.2 / pnpm11.7.0实际将OpenCode1.18.31更新到1.19.5，随后独立CLI从其它工作目录复用当日记录，未执行新的维护命令。最终27项离线测试覆盖更新、缓存、并发和模拟AI恢复，含修复后复查、仅一次业务派发及拒绝未经核实的修复声称。真实更新未失败，所以没有实授AI诊断能力；升级也不追授1.19.5工具或业务能力。[脱敏摘要](evidence/2026-11-01-opencode-daily-update.json)区分真实维护与mock恢复，原命令日志和状态留在执行机器。

## 2026-11-02：Civ6 项目经验汇入

[迁移整理](civ6-experience-2026-11-02.md)保留真实 UI/Core API、原生类型、身份复用、持久化未知不重放、事件坐标和诊断清理边界。三份[历史原文](history/civ6-2026-11-02/README.md)精确归档，旧129次P6请求不追认每日维护合规。新3项迁移任务通过共享CLI与每日成功缓存，3 stop/DONE、0重试；候选仅部分分析参考，owner仍需实现验证适配器。完整候选和最终业务效果分别记录，不据此宣布节省成本。

## 2026-11-02：共享入口的消费者与失败门禁

Civ6已用薄适配委托共享CLI，14项必要边界检查通过；其中用真实prepare_request消费实际请求，并用真实main模拟维护失败，确认dispatch未被调用。后到一次模型审计却忽略该控制流，提出重复preflight；owner拒绝，不因审计标高危或完整stop便改代码。调用链证据、业务system覆盖、原子claim、候选就绪/adopted=null各自验证，旧HTTP/SSE实现与8个内部测试退役。精确采用源及本轮未测范围见[后到回执](evidence/2026-11-02-civ6-adapter-delivery.json)，不能把适配测试当作游戏效果或模型自主交付。

## 2026-11-02：HOI4 Windows入口占位文本

迁入一份已有公开历史：OpenCode入口实际是479字节shell文本，pnpm仅拒绝该包的构建脚本；同版本原生依赖已安装。先检查真实PE/架构、许可及候选程序版本，再修复入口并逐个CLI读回，比只相信安装退出码更有诊断依据。只按包修正许可，不能扩成全局开放。

此例限定Windows10/pnpm12.6/OpenCode1.19.4；help写stderr、同版本硬链接及真实字节哈希分别保留。它没有模型调用，不授予当前模型或OpenCode工具生成能力。[原文与来源](source-origins.md#2026-11-02hoi4-windows客户端经验迁移)、[操作经验](hoi4-windows-client-experience.md)与[当前每日维护](client-maintenance.md)分别维护。

## 2026-11-02：输入发送ACK不能证明原生动作

Civ6实际军队Delete首试中，前台与单位均正确，按键工具返回后原生InputActionTriggered、提示入口和确认框却均0。检查本机PyDirectInput映射和扩展键处理后，改用实际Windows扩展Delete；此时action15、原生提示、军队原生确认与文职guard拒绝分别可见，手动取消后位置/行动/完整ID不变。首次无反应保留，不能算军队功能故障或成功负例。owner编排与工具修正成本独立于两份模型length失败；三消息完整135也没有满足所需具体观察合同。[实际输入与采用记录](evidence/2026-11-02-civ6-input-acceptance.json)。


## 2026-11-12：Civ6余粮供粮678／679

678输入17148／输出6500 length整弃未读，整三文件输出预算不合亦记owner尺寸限制。679完整17246+1192=18438tokens／11686.3716ms，原12方法在旧131已有11过／1Lua断言unittest error；虚用sourceWorked、用目标缺粮代替供粮负例、不真实reload，整拒／0rawNative。Owner11新Lua51方法、43相关，全1921项1920pass1SDKskip，97Lua／119包；初5前导分号夹具错误与raw679计数误期望单列。UI食物2／Core1须保上下文差异，正式132同304冷验待做。两POST峰2／重叠11.689638秒，累计679／631完整45length3transport709HTTP30extra；Nov12同机同用户1.19.5维护缓存复用，OpenCode原生0、未知缓存成本净收益null。[固定业务反链](evidence/2026-11-12-civ6-food-donor678679.json)。


## 2026-11-12：Civ6实际部分换格与680—682

132真实换2133后上海净−2→−1／源城仍+6，原UI2粮转入后1粮；只有一次请求、ARMED保持、不重发，保存304。680/681/682均完整stop/DONE/VALID，分别25284/25143/23618tokens、35879.517/34608.8496/23824.2616ms。680拒−0.5／重复写负回执／同plot再Prepare三反例，681nil字符串别名经独立Lua断言捕获，均仅部分hunk经owner纠正采用；682十方法1过9errors／接线丢失等整拒。Owner12新方法／55相关及全1933项1932pass1SDKskip，97Lua／119包；首10owner双格fixture/旧期望错误单列。三POST峰3／重叠23.816935秒，累计682／634完整45length3transport712HTTP30extra。Nov12同机同用户1.19.5维护缓存复用，OpenCode原生0／未知成本净收益null；133游戏仍待同部分生效档冷验。[固定业务反链](evidence/2026-11-12-civ6-partial-food680682.json)。


## 2026-11-12：133后见Native救粮与独立人口失败

Owner修正部分680/681后实际冷验：已转入旧许可不重发，另一新计划使目标净粮0、15人口跨两普通回合保持；另城也自然新救粮。33食品／忠诚城帧过，但306另一供粮城人口−1单独触发停止，正库存／自有燃烧森林及原生事件损失支持灾害推断，缺逐城原因码不冒全窗口通过；Core/UI净粮差异分别记。新完成态重载另待，0新HTTP／through682不重计，0OpenCode原生、未知成本净收益null。原始候选整份采用并未追授。[固定Native业务反链](evidence/2026-11-12-civ6-native133-food-fire306.json)。


## 2026-11-12：133完成态重载后见

同一保存306一次官方重载／一次继续，旧两OBSERVED与serial4保持；严格旧日志前缀后新增救粮请求／回执均0。11城身份人口库存保持、食品／忠诚合格；完整World/建筑/区域/地块同，但1Builder成本、同演员续行、多城产出／宜居重算差异另记，原因未隔离，不报whole-world invariance。初次过宽CITY整行保护拒绝后先分域检查、0依赖输入；四旧人口损失及六停止记录保留，明确新范围继续工厂。0新HTTP／through682不重计／OpenCode原生0，未知成本净收益null。[固定完成态反链](evidence/2026-11-12-civ6-completed-food133-reload306.json)。


## 2026-11-12：Civ6当前交易煤元数据683／684

683完整13328tokens／15516.5028ms，但合同行外otherPlayerID使合法阳性UNKNOWN；仅隔离补镜像后八缺口（稀疏／额外key／分数量／metatable／末态inactive／错对象ID／缺煤Index／getter漂移）仍KNOWN，整拒／0rawNative。68416677tokens含输出5000 length未读整弃。Owner只读当前原版可见deal模块12Lua51方法首过0.137s；禁止UI/交易mutation、对方from四参数、完整密集列表和最终状态绑定，不授实际metadata／煤交易／正燃料项目效果。两HTTP峰2／重叠15.516009秒，累计684／635完整46length3transport714HTTP30extra，维护缓存复用／OpenCode原生0／未知成本净收益null。另原版END只处理队列后留回合，fresh普通下一步才实际换回合；308工厂／海港已修、项目保留，新人口损失与自有火灾传播边界单记。[固定双业务反链](evidence/2026-11-12-civ6-trade-coal683684.json)。


## 2026-11-12：Civ6煤诊断Owner模块实机后见

隐藏原版deal UNKNOWN／当前Canada KNOWN，列表max100而单项max25；40保护在写前拒绝、原版25合法编辑。报价双方六行只含25煤及279金币+29GPT30回合，原版一次成交后库存0→25／金币−279；不授后台资源获取或正燃料生产。Owner首只读Items key/value错因单返回修正，旧截图／未关场景保护先拒绝；成交后旧INCOMING validation不代替库存。0新HTTP，through684及OpenCode原生0不重计，成本收益null。[固定实机反链](evidence/2026-11-12-civ6-native-coal-trade308.json)。


## 2026-11-12：Civ6正燃料实际供电与685分析拒用

685完整stop/DONE/JSON，16224+1484=17708tokens、12453.2812ms，峰1；把保留143当项目队首、>=0当正、娱乐区作工业前提、猜项目缺电等五项反例，整稿拒用／0代码或Native采用。Owner分开已有维修优先级与真实新决策。独立煤25→20后11城全供电、娱乐区修好接斗兽场，新项目请求0，正燃料缺电选项目仍开；新2574救粮OBSERVED，309人口损失及自有火点只支持火灾推断，保存停。Cities:Members与Deal:Items不同迭代合同，Owner只读错误0操作修正。累计685／636完整46length3transport715HTTP30extra，维护缓存复用／OpenCode原生0／未知成本null。[固定逐项反链](evidence/2026-11-12-civ6-native-coal309-model685.json)。


## 2026-11-12：Civ6686未用燃料条件与原版交易

686完整7990+857=8847tokens／7354.0739ms，峰1。只采用有条件逻辑相容性，Owner修正powered否定、零耗能项目、维修当前队列优先级、双CanProduce/新鲜BUILD资格四处；0代码Native。独立现场修好斗兽场/动物园并转发电站，143仍保留；原版Canada无油、Brazil metadata valid却拒价、Spain无，Rome1油报价六行核验后一次接受，实际油0→1/煤8/金币−14另1GPT30。交易准备不授后台能力或缺电新项目通过。累计686／637完整46length3transport716HTTP30extra，维护复用原生0／未知成本null。[固定本项目反链](evidence/2026-11-12-civ6-original-oil311-model686.json)。


## 2026-11-12：Civ6687／688完成通知只读观察

687完整6506tokens／21844.1917ms，漏动态身份／名单／漂移未知，失败Remove谎报恢复、失败Add漏清理，整拒／0rawNative；独立11方法实际14failure11error含subTest。6888893tokens/length5000正文未读整弃。Owner整体模块与fixture11方法首过0.099s，己方双完成事件两次读电力/燃料/队列、不写游戏；未知和精确撤销边界另记，不授Native或规划输入。Owner原任务来源误称Controller订两事件，实际项目端来自已装XP2教程，纠正不算模型错。两HTTP峰2／重叠21.844057秒，累计688／638完整47length3transport718HTTP30extra，维护复用／原生0／未知成本null。[固定观察器审阅反链](evidence/2026-11-12-civ6-power-completion687688.json)。


## 2026-11-12：Civ6正库存缺电后的新项目实效

武汉316完成回调真实缺电req2/temp1/煤3油1/q空，随后BG新工业项目请求/回执，317100/168+activeProject全供电，318152/170保持；通知不冒私有规划输入/原子或油消费因果。25双事件样本0错丢，317exact撤、318新完成后计数/样本仍原样。七正常回合77城次food/vitals人口无新损失，旧六损失八停止保持；发电站33修完仍改造体育场，旧143没接续，列真实缺口修复；住房三城不足另域记录。0新HTTP/冻结through688不重计，689690另包，OpenCode原生0/未知成本null。[固定实机序列反链](evidence/2026-11-12-civ6-positive-fuel-native318.json)。


## 2026-11-12：Civ6项目投资接续134与689／690

689完整27324tokens／30177.3274ms，仅纯ResumeProjectScore窄hunk部分采用；原两Controller hunk各匹配一次，独立12方法5failure，Owner重写特殊项目独立接续、预算前保留／去重与最终资格。690 length5000／29146tokens／42384.0964ms正文未读整弃。Owner首次11/12过，合法校园抢先属隔离夹具，纠正后12过7.960s；旧133对新12方法15failure1error含subTest。冻结全1968项1967pass1SDKskip、97Lua51／119包逐字节，417.642s不是净节省或实机性能；软件切点仍133／318，134实效后见另记。两HTTP峰2／重叠30.176518秒，累计through690为690／639完整48length3transport720HTTP30extra，Nov12维护缓存复用、原生0／未知成本null。[固定续建软件反链](evidence/2026-11-12-civ6-project-resume134-model689690.json)。


## 2026-11-12：Civ6691住房需求和重复社区

691完整10455tokens／7976.6551ms／TTFT1620.8209ms，只采用有界调查方向，Owner纠正负缺口算术、需求不等于排序、先计扫描预算及未审原因表；漏答重复社区由实际OnePerCityfalse、邯郸已有社区仍双CanProduce真补证。133／318北京15/20、邯郸18/20、上海14/15，需求／双生产均真，原生可放置4／2／5不授ClearPlot／资产／粮食／保留或最终操作资格，0游戏动作，不归因政体。累计691／640完整48length3transport721HTTP30extra，新峰1；同机Nov12维护缓存复用、原生0／未知成本null。[固定住房诊断反链](evidence/2026-11-12-civ6-housing691-native318.json)。


## 2026-11-12：Civ6692住房选址与严格JSON拒绝

692 HTTP200完整stop/DONE，13644tokens／11835.7839ms／TTFT1867.2277ms；共享报JSON VALID，项目递归重复observation键拒绝／exit1／candidate=null，整份0采用，不修补重试。641完整流计数不等于641严格候选通过。Owner实际134／319十一原生社区候选均被ClearPlot挡住：3可见资源、8其他地貌；提高分数不能单独解决，邯郸HasDistrict真而HasBeenPlaced假。只读APPEND资格不授活动队列写入，0游戏动作。累计692／641完整stop流含此次严格JSON拒绝、48length3transport722HTTP30extra，维护缓存复用／OpenCode原生0／未知成本null。[固定资源地貌与JSON拒绝反链](evidence/2026-11-12-civ6-housing692-protection319.json)。


## 2026-11-12：Civ6134保留项目投资自然完成

119冷装／新鲜后台离线后原318实际一次加载，所采七组与food/vitals同。体育场59→115→174→230自然完工，322唯一BACKGROUND resume_project=true请求0:322:76和队列匹配，143/173原生接续；323双完成事件／进度0与另一次新项目分列。七普通END／五实际推进／35军SKIP，66城帧／五人口区间无新损失；319队列未换回合后新鲜空闲／阻塞和军SKIP资格再授一次普通END，不重放未知。三通知0错丢、exact撤两自有引用，323已存未载。0新增HTTP，689690软件与691692诊断／693694候选不重计或互授；OpenCode原生0，未知成本null。[固定143续建完成实机反链](evidence/2026-11-12-civ6-native134-project-completed323.json)。


## 2026-11-12：Civ6缺房林地社区135与693／694

693完整13805tokens／19564.2580ms，5旧hunk各匹配一次，独立14方法4failure；整数误限住房小数、新元数据读取在pcall外可停Controller，Owner修后仅部分采用。694完整20328tokens／17540.1387ms，原8方法在raw693下2failure2error（全局w／字符串API数字参数／雨林错拒／假竞争），缺test_的方法未运行不冒执行数，原测试整拒。Owner14新集成方法预验17.693s／实际针对全过，冻结全1982中1981pass1SDKskip、97Lua51／119包；249.396s不推净节省或实机性能。只真实住房不足可允许已知可移除普通森林／雨林社区并给93，原资源／粮食／队列和native门保留；135实机后见另记。两HTTP峰2／重叠17.532383秒，累计694／643完整stop流（前692含1严格JSON拒绝）48length3transport724HTTP30extra，Nov12维护缓存复用／原生0／未知成本null。[固定住房135软件反链](evidence/2026-11-12-civ6-housing135-model693694.json)。


## 2026-11-12：Civ6135实际社区开工324

119冷装／新鲜离线后原134323一次加载，七快照组相同，但4food和6vitals派生行不同，人口／库存／忠诚保持；初未提交保持措辞已纠正，不归因135或宣称全部一致。324原队列自然完成后，后台邯郸2867／上海2055各一次社区请求、队列回执和实际区域10；北京港口保持。邯郸施工中总住房18→17／区域6→5保留，未授住房改善，观察器有界继续待真实完成。单普通END7军SKIP／无人损／22城帧合格，324已存未载。0新增HTTP，不重计693694，OpenCode原生0／未知成本null。[固定135冷读与两城开工反链](evidence/2026-11-12-civ6-native135-housing-started324.json)。


## 2026-11-13：Civ6135三社区实际完成329

邯郸326／上海327／北京329原生自然完工，三次BACKGROUND请求／回执／实际地块配对。区域住房邯郸5→9、上海0→3、北京0→4；邯郸同期改良1→3，总+6不能全归社区。北京19/20与西安23/24仍不足，继续真实合法替代，不授全城充足或全验收。六实际推进／八普通结束输入＋一次议会提交END／42军SKIP、77城帧与六人口区间无新损失，13观察全KNOWN且exact撤掉。329已存未载；0新HTTP，693694软件和695审计另包，OpenCode原生0／未知成本null。[固定135三社区完成与剩余缺口反链](evidence/2026-11-13-civ6-native135-housing-completed329.json)。


## 2026-11-13：Civ6审计695、泛滥平原696／697与同版重载

695完整18160tokens／15152.5647ms却混淆发表切点与后到证据、重复过时B_delta缺口、把未证MOVE混作旧FOUND失败，整拒。Owner纠正：TC038的74／8／1029确已提供，初筛误认缺源由前置断言发现，不归模型。67四数值预算／25配对和105106特定长局证据保留，未冒授完整矩阵。[695固定反链](evidence/2026-11-13-civ6-695-housing-audit.json)。

696原样采用纯helper一hunk，真实19房／20人且原生合法的不可移除泛滥平原需独立于森林清除资格；不发新清地貌命令、不绕资源／粮格／队列／原生门。Owner7方法旧135有13失败／原696七过8.795s。697自称组合却继承14旧方法，实际20项20失败；另一个exact旧fixture替换LuaSyntaxError。其测试整拒，Owner7新方法加旧14语义维护，实际21全过／冻结全1989中1988pass1SDKskip、97Lua51／119包。两完整HTTP21564和22523tokens、7338.3960和12185.9957ms，峰2／重叠7.325417秒；软件耗时不推净节省、包成不授Native。[136软件固定反链](evidence/2026-11-13-civ6-696697-housing-audit.json)。

135完成329同版正式冷载，三城住房／地块保持，191建筑69区域222地块52单位相等、11人口／队列目标投入保持；世界收入、Builder成本、4粮食／8vitals行有差异，因果未隔离，不称全字段保持或归136。同版也出现差异只能限制归因，不能授具体引擎原因。0END／新HTTP，旧六人口损失与八停止保留。[重载固定反链](evidence/2026-11-13-civ6-135reload-housing-audit.json)。

Nov13由695入口实际canonical检查OpenCode1.19.5／registry1.19.5无升级，696697同机同用户缓存复用；普通HTTP累计697逻辑／646完整stop流（前692含严格JSON拒绝）／48length／3最终transport／727HTTP／30extra。OpenCode原生生成0，未知缓存／Owner总成本／净节省null。继续真实136冷装实效及未闭验收，不制造补位请求。


## 2026-11-13：136自然补房332与698／699审阅边界

同329分别冷载135和136，四组快照／粮食／vitals／住房行全相同；西安Builder自然完成后330森林社区0→127/200→332完工，住房23→27／24人。北京改良住房3→7先解除赤字，不能冒授136新增泛滥平原施工。332当前11城均不缺房仅瞬时，三实际推进／五普通END／一议会所含END／21军队SKIP分开，44城帧、三人口区间无新损失；4观察exact撤、332已存未载。0本Native新HTTP，泛滥平原独立324对照另继续。[Native固定反链](evidence/2026-11-13-civ6-native136332.json)。

698完整19801tokens／7277.8312ms未形成新Capture缺陷，正确CHARGING冻结既有；把mock throwAfterTransfer/failCharge混作P4实机拒收。Owner包只给P4/P5，漏27/74/75和独立恢复测试，不能把“待补”做全项目缺失盘点或归模型忽略已供数据。699完整9993tokens／13369.4700ms保留67已测范围，但69文件、4096内存／丢弃门和>1000候选义务无据；原建议CLI实际exit2，0输出目录／0安装，store_true单flag与带true区分。Owner未提供候选生产者／512配置也单列，不重投已闭旧绿或假称136性能已测。[候选与Owner输入限制](evidence/2026-11-13-civ6-models698699.json)。

两HTTP峰2／重叠7.277938秒，stop/DONE／严格JSON；累计699逻辑／648完整stop流（含前692严格JSON拒绝）／48length／3最终transport／729HTTP／30extra。Nov13canonical1.19.5成功缓存复用，OpenCode原生0；未知缓存、Owner总成本与净收益null。继续原协议真正压力夹具和当前风险独立验证，不把软件、历史Native、当前集成与模型采用合并成PASS。


## 2026-11-13：700候选领域纠正、136私有配对准备与泛滥平原开工

Owner先前698699及本共享摘要的“候选512”没有充分限定领域，现明确纠正：ProcessCity/Add的checked512限制该资格计数，不限制全部外层枚举／工作，更不限制移民全图城址。699的>1000要求无合同依据，不能用跨领域512作不可能性证明。700完整71992tokens／15431.6745ms／TTFT9363.4108ms，仅生产／城址领域不同部分采用；其引擎硬12、遗漏旧preferred目标、ProcessSettler→RecruitAllowed调用边均拒收。源码只是请求GetSettlementRecommendations(12)并pairs遍历，返回硬上限未实测；旧目标可额外合并，招募由ProcessCity调用RecruitAllowed。[固定纠错反链](evidence/2026-11-13-civ6-model700-domain-correction.json)。旧JSON／blob和原始请求保留，本段只纠正域界与来源，不重写历史。

Owner按正确单flag生成普通136的enabled／control私有119文件配对，各97Lua51编译、ZIP逐字一致、计时前缀SHA相同，源码未变，0安装／Native性能／压力夹具PASS。control12文件词法差异列明，仍待独立运行覆盖／时钟验证，不把可构建当有效全局对照。[私有准备反链](evidence/2026-11-13-civ6-perf136-private-preparation.json)。一次DIRECT Git连接失败后使用既有环境代理正常push并读回远端，未改全局代理或Steam模式。

独立135324存档下普通136两自然推进到326，北京后台唯一0:326:31请求、队列回执和2568区域10匹配，原生普通泛滥平原feature0仍在、农场由原版BUILD移除，净粮15／20人口无新损失；无需排除另一个森林。这里只授新增分支实际开工，完工／住房增益／重载后见另记；保护136主332，分支进度不叠加主线。[Native开工固定反链](evidence/2026-11-13-civ6-native136-flood-start326.json)。

累计700逻辑／649完整stop流（前692含严格JSON拒绝）／48length／3最终transport／730HTTP／30extra；700新峰1。Nov13canonical1.19.5成功缓存复用，OpenCode原生0，未知缓存／Owner总成本／净节省null。明确源码任务、私有构建、游戏阶段与模型采用分开，继续真实未闭验收。


### 2026-11-14：Civ6候选必须对齐实际消费合同

[738—741与Owner141](https://github.com/XenoAmess/civ6_dev/blob/1affcfe51b15ea72d99cad33736cb7bf5e45d79a/docs/research/baiqi-source141-settler-J738741-2026-11-14.json)重复支持检查可用实际Controller方法计数验证，未知Forget后只保留否定proposalID，最终发单仍新鲜。模型给错GameInfo可调用形状、请求记录shape、空测试或额外ACK字段不能授采用；原稿失败与Owner修正分列。Source版本适配不得悄改历史证据。Owner关于锚点的初始猜测也需逐项计数修正（本例全1），不能把负责人错误转嫁候选。四次完整流、实际两组峰2和成本null分别记录；141 Native／性能仍待。


### 2026-11-14：空批次续行要检查实际消费者

[745746／Owner142](https://github.com/XenoAmess/civ6_dev/blob/e8353103eacb980484806eef137d0351d2c85716/docs/research/baiqi-source142-support-budget745746-2026-11-14.json)限定函数＋调用前先确认消费者是否处理空结果more；本例Owner误以为会传递，原稿虽返回more仍提前SKIP。预算应基于被测昂贵工作，廉价已变外国地块应过滤后同回调继续；现有oracle发现Owner过度限制后修实现，不改断言。候选新测试不可用Pythonlist冒Lua原生表，也不能用继承旧测试数抵新合同验证。2220含1SDK跳过为软件证据，142仍无Native／速度信用。


### 2026-11-14：启动诊断原件和无因果恢复分列

[M747748](https://github.com/XenoAmess/civ6_dev/blob/20a04e16be3507eacef6f7edcc96aa9f0f0ce05e/docs/research/baiqi-startup-M747748-recovery-2026-11-14.json)主界面前挂起的自有实例先保线程与普通dump，转储私密；不能把Ghost焦点不匹配绕成截图或GameCMD权限。合法UnusedStream0允许重复，关键流才要求唯一；单PC映射不冒调用栈或根因。相同产物N恢复不追认M采样，Owner错误也记在真正失败前／后边界，不转嫁模型或计作Steam操作。


### 2026-11-14：表名和运行token不能替代来源证据

[749750／N](https://github.com/XenoAmess/civ6_dev/blob/111258bd622dcac7026703cd82b9f1ae272333a8/docs/research/baiqi-stageA142-N749750-2026-11-14.json)：通用本地化表名无法确定资产归属，直接核错误文件路径和实际文本键；路径能指向报错插入者，仍未确定首次重复来源或启动根因。运行token只能确定一次运行，源版本另核实际manifest／buildmode／所有文件哈希和新进程。模型应识别已支持的版本，不为迁移而迁移；旧PID必须换为新的PID／birth／exe三元组。新正式142规划预算通过不追认旧140／141、不扩授全脚本或五组配对。


### 2026-11-14：旧玩家消费者也要检查原生动作兜底

[751752／142](https://github.com/XenoAmess/civ6_dev/blob/9d429c2223b60e06aeb17a7c894dc50e403f0718/docs/research/baiqi-allscript142-pair751752-2026-11-14.json)：只在Python层限制child模式还不够，实际旧军队待命Lua尾部可能DoEndTurn。匹配计时只允许最终已确认端点发令，去除该尾路并测试失去选中资格时零动作。函数源码完整／Python编译成功不能替代缺导入、外交插入时机和穷尽循环的行为测试；HTTPstop也不授采用。Owner给错文件名造成模型缺上下文须一起记录。全脚本累计调用与保留行分别记账；1735保留／37509零成功并未突破4096上限。


### 2026-11-14：先确认日志导出是否有顺序语义

[753／142E1](https://github.com/XenoAmess/civ6_dev/blob/061899ea4c61266bb5c169bb4abae78c07aef333/docs/research/baiqi-pair142-E1-cold753-2026-11-14.json)：记录map使用pairs输出，顺序不是时间线，严格比较应校验唯一键／计数／已知包络后对完整多重集比较，不能用set掩盖重复。历史导出只给字段子集就只授该子集。Owner提示哈希笔误须标明真实回执权威、不能改写原请求或把候选正确纠正抹掉。真实跨UI普通时钟完成一侧不等于对照／整组，必须保留原始耗时与外交停留，不提前算净收益。


### 2026-11-14：监听绑定异常也可能已经绑定

[754755／142首组](https://github.com/XenoAmess/civ6_dev/blob/0c7640c1d2f05db12b82bb7a1445dd346a913d74/docs/research/baiqi-pair142-C1-event754755-2026-11-14.json)：绑定尝试必须在Add前记；若Add绑定后抛错，只能针对同一自有回调清理一次，不能把subscribed=false当成事实。Remove未知保持未知且停止采集，不重复移除。Lua固定形参加ipairs(varargs)会丢nil尾且伪造argc，真实select数量与有界类型列表应分开；代码编译过仍可能把块内local时间写成nil全局。读实际API消费者后再选探针，不重复已完成阴性读数或凭无待办猜全局队列为空。


### 2026-11-14：未知签名要能采集且不伪装合格

[756／实际4参](https://github.com/XenoAmess/civ6_dev/blob/a42e3d2533a1cd0ecb27ce2308cfe2683b970fba/docs/research/baiqi-event142-A756-fourargs-2026-11-14.json)：声明形参个数只是消费前缀，不能当作发出数量。新结构错误与unexpectedArity计数可区分未知诊断，但旧invalid不回写、qualified不放宽。未知额外参数仍保留完整argc、最多8项类型／基础值，长文本记录截断前缀与原长度；只存类型会丢掉下一步所需原值。新采集会话保持已尝试输入台账，不能因改诊断重新跳过同单位或重发未知命令。


### 2026-11-14：事件缺席和普通结束不能消除未知队列

[142实机](https://github.com/XenoAmess/civ6_dev/blob/9e528974790b16f18e4b3840ad52dcd15d266e9d/docs/research/baiqi-event142B-normal334-757-2026-11-14.json)：实际军队MOVE执行但被动Started未新增，六SKIP事件第四值0也未知语义。以未见事件判断无动作／安全重放不成立。已验证UI GetQueuedDestination实际可返回数字plot index；先核真实返回形状，不把无x/y当队列空。普通END能先处理已有队列而留原回合，也能下一回合仍保留排队目的地；调用返回、实际回合、位置／行动／pending／目的地分别读回。新鲜明确新队列可支撑下一次普通输入，未知动作不得盲重试。
