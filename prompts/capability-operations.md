# 两种模式的长期运营prompt

供拥有本地文件、验证及发布权限的运营owner/接班worker使用。此prompt随仓库AGENTS生效，作为持续工作指令；不替换[scripts/call.py](../scripts/call.py)注入给源码候选模型的固定system，也不自动修改运行中业务客户端。

## 任务与持续责任

你负责长期跟踪、长期运营本地模型的两种执行模式：`http-candidate`（普通HTTP三消息候选）和`opencode-native`（OpenCode原生assistant/tool循环）。这不是一次性预研或三任务试点：阶段任务交付后继续保留跟踪责任，带着未验证项与可复用经验交接给下一owner。用户后续的业务优先级和授权优先。

开始时先安全同步干净main，阅读[AGENTS](../AGENTS.md)、[使用指南](../docs/usage.md)、[共享配置](../config/executor.json)、[共同证据规则](../docs/capability-boundaries.md)及两个独立记录：[HTTP](../docs/capability-http.md)、[OpenCode](../docs/capability-opencode.md)。保留本地改动/分叉，按唯一Git写者协作，不reset/force覆盖。每台客户端当天实际接入模型前完成现行每日维护；纯文档整理不伪造模型调用或维护通过。

## 持续执行方法

1. 围绕真实、尚未完成的业务工作选择模式，先检索当前源码与影响范围，明确生产者、消费者、祖声明、输出范围和独立验收。准备、模型HTTP、其它任务审阅可重叠，不等中央封包ACK或整批研究。
2. 普通HTTP保留固定三消息和有限完整候选，owner负责应用及验证；OpenCode使用本次真实许可的文件/工具范围和实际assistant/tool历史。按实际流程归档，不按产物用途归档。模型HTTP重试只重发模型请求，不重放文件发布、Game或其它业务副作用。
3. 核实际REQUEST参数、版本、权限和预算。记录重复读取/编辑、length、无效循环、工具错误与恢复；配置可解析不等于实际权限通过，HTTP200/stop/CLI0不等于验收。沿用当前明确授权，不擅自把本次权限、迭代限制或无限步观察变成所有未来业务的默认。
4. 尽早做与改动相称的必要验收，让真实诊断指导修正。反复语义错误时owner接管，保留模型原件及采用0/partial/原样的真实边界；不为了证明框架有价值延长失败循环，不重跑旧绿或拼半截输出。
5. 每次真实交付、拒绝、接管、重试故障、版本/配置/权限变化后，在对应模式页追加case_id、可追溯证据、采用、验证、成本和下一真实问题。既有冻结证据不回写，后到回执另增。跨模式公共经验补总入口；客户端保障和模型生成能力分列。
6. 准备、源审、纠错、测试、协调等待和发布分别计时，未知写unknown/null而非0。后续新任务从首次实际准备当场记UTC phase events：`PREP_BEGIN`/`PREP_END`、`REVIEW_BEGIN`/`REVIEW_END`、`CORRECTION_BEGIN`/`CORRECTION_END`；沿现有事件工具记录即可，不为记时开发新框架或发模型请求。BEGIN须在独立且已完成的工具调用中落盘，早于新代码或修正文本的起草；若与已写好脚本同批执行，短区间只能记机械应用，先前authoring另记或unknown，不能冒完整owner阶段。模型/编验等待另列，跨任务切出时暂停当前主动区间，返回时再记录续入；与其它任务交错时标明区间和中断，保全墙钟，不把交错区间当独占主动工时。过去未记录的阶段保持unknown，不从compiler/HTTP/全wall倒推或补造事件。单记CLI耗时不能证明owner准备/修正减少；逐轮保留可比的实际阶段及未知项。区间重叠、POST数、tokens、编译绿或最终业务成功都不能替代净owner收益。无合适真实对照时不宣布模式优劣；权重/后端身份不明时不能从模型别名认定可复现配置。
7. 一个可审阅单元必要检查通过后，唯一Git写者精确stage/commit并正常push main，核远端SHA。任何已要求的raw/working/staged内容或hash核对返回非0，立即停止该发布单元；不得用try/finally、未检查退出码的后续步骤或并行Git继续commit/push。修复后重新完成全部必要核对才发布，原失败及additive修复分别留证。成熟pin/实际回执足够时不再等重复聊天ACK或独立长报告；成本后到可另追加。原始REQUEST/SSE、私有源码、机器账本与大证据留执行机器，公共仓库只放获准脱敏材料。
8. 每个阶段结束交接两模式的最新case、适用版本、已证与未知、owner成本、残余故障和下一真实触发条件。没有未完成真实需求时保持待验证，不造任务或刷并发。恢复工作时从这些记录续行；阶段报告或当前0在途不是停止长期运营的依据。

同时落实用户的两项并发要求：60个实际RUNNING云端智能体与60个实际POST未结束的本地模型请求分开报告、同时推进。云端capacity/turn错误不归本地HTTP；保留用户选定云端型号续行，不为此探测或重启本地服务。source-ready、排队、CLI与旧峰均不补算两种实数。

完整输入一齐就直接执行下一真实任务。优先沿已有caller的有序`source_files`自动封包，不再人工手拼同一前缀；已明确转移执行权的owner将唯一冻结记录发布给现有sole intake，由它串行注册并交滚动dispatcher，作者不再双发。不把准备-only交付、个人回执、整波源审、软件窗口或Git发布设为POST终点或前置。原实现、独立原源反审和新的公共Test可在有不同未闭目标时并行；已闭绿或已接管写完的实现不追投凑数。

入队写者和来源owner须明确。多owner各写唯一不可变记录，只有sole intake写共享READY；compare-before-replace不等于并发锁，manual registrar不能与它并跑。缺claim/存在旧Ready都不是重放许可，崩溃及重复冲突须保历史并核实际REQUEST/EVENTS。每个截面分别列出源齐未入队、READY未POST、具名POST未END和覆盖未知项；Runtime预留1仅客户端准入，不冒充服务推理slot。准备到BEGIN的人工等待与HTTP总时、TTFT、主动工时分开，自动化不能回填抹去原协调成本。

宿主若区分“发送消息”和“启动任务”，给 completed worker 的普通消息只算通知，不能报告已在并行工作。先核实际状态；对 completed worker 使用能触发新 turn 的续派 API（本次宿主为 `followup_task`），再消费实际 START/状态或新源码出生回执。`send_message`、排队消息、旧 Ready 和准备目录均不是启动证明；running worker 也不等于 HTTP 在途。一次误用普通消息造成约39分钟协调延误，[实际起点及撤回记录](../docs/evidence/2026-11-03-completed-worker-notification-without-start.json)保留原通知精确UTC未知，不能补造精确工时或归模型/HTTP/CPU。状态核实不增加每 POST 中央 ACK；输入齐全的真实任务继续由唯一 owner 直接执行。

原生工具出现重复时核实际受支持参数、输出SHA和读取区间：未知字段可能未报错却被忽略，合法参数也可能形成同输入/同输出循环。以具体无新信息证据决定获准的精准owner干预，保留中断请求UNKNOWN；不设隐蔽总步封顶，也不靠连续提示喂业务答案。先分清模型循环与配置合并、旧relay地址等launcher故障；debug exit0必须再核effective配置。[实际案例及只读接入](../docs/opencode-readonly.md)。

## 按交付价值选择任务单位

完整输入不意味着适合把全部预期交给模型。多组真实复合RAM/ABI见证在完整stop或高预算下仍因API、调用角色、状态传播和完整queue错误拒绝；owner接管、审阅和等待成本均保留。[分别冻结的采用与成本](../docs/evidence/2026-11-02-http-task-routing.json)同时包含可原样采用的薄binding、提示后的有限API/诊断代码，以及复杂见证失败，不能合算采用率。

- 大而复杂的全RAM、全ABI、多callee trace oracle由owner依据原始输入独立冻结。不要对每个相似的新任务都强制从零让模型再生成约20KB expected/Test；必要机械夹具和真实验收由owner负责，不能让模型研究成为业务前置。
- 复杂全ABI producer也按交付单位路由：优先一个真实basicblock、typed API、薄binding、有限反例audit或小机械段，owner保留完整控制流/状态编排与独立验收；不要只拆大Test、仍反复索取整段复杂producer。已有整稿length和完整ABI错误分别留证，owner接管后不R3洗绿；新的具名边界仍允许有依据的有限探索。[完整候选与owner成本](../docs/evidence/2026-11-02-http-complex-producer.json)。
- 模型优先承担仍未完成的typed API、成熟接口薄binding、窄诊断、具体源反证或小机械片段。先明确产物和验收范围，保留owner签名/设计/真实API提示程度；独立审稿也可能错，必须逐源核对，不能仅因角色名是audit就接受结论。
- 汇编偏移、字段地址和栈坐标逐项显式写`0x`，十进制计数/长度注明单位；将任务文字、原ASM与同源actual helper声明/正文对齐，不把名称或注释中的`+40`当无歧义事实。owner原提示的数值歧义与候选中独立可证的fresh读取/API/状态错误分账，订正不回写旧REQUEST，也不据此声称订正后已重试、通过或有收益。
- 审有多个函数式接口重载的构造器/调用时，逐个核实际实参静态类型、适用重载、SAM返回类型和构造器实际写入的回调字段。方法调用表达式lambda在void目标下可丢弃返回值；看到返回表达式或compile0不证明预期回调已接入。有既存class descriptor可只读复核，不能借此默认新开JVM/业务探针，也不能把live catalogue替为List快照或加宽cast来凑绿。[已纠正的owner/模型/正式审漏项](../docs/evidence/2026-11-02-http-constructor-overload-erratum.json)。
- 反审声称候选缺少校验、提前返回或顺序错误时，必须实际定位候选语句与执行路径，并对照所供编码入口/调用者；不能把已存在的调用视而不见，也不能借另一入口的合同制造缺陷。反审完整stop或角色独立不等于结论正确，未命中实际语句的finding逐源拒绝并保留owner复核成本。[同引用编码案例](../docs/evidence/2026-11-03-http-guided-identity-encoding.md)。
- 阴性NO_PATCH或“无法优化”同样逐源核实际调用边、触发条件和后果，不能把已供完整static codec或普通文件边界当未供外部callback，也不能由字段名猜过滤。未闭transitive域仍写未知；有重复工作不自动授权删除当前资格点，两份阴性答复一致也不构成不可能性证明。
- 新能力边界仍可做有限、具名的真实探索，说明新分支、未知项和可完整交付的单位。相似任务已有连续反例时，先调整分工或接管，不凭请求数、R2或采用配额继续大稿；已闭题不重投。准备、HTTP、审阅可重叠，把并发用于真实有交付价值的需求。
- 判断缺少诊断前先核既有dispatch、ACK、custody、unavailable与实际保存/throw次序，再决定是否需要新工具或新观测。已有负向原件纠正owner推断不算模型新能力；缺少有效状态帧仍保持未知，另行授权的新功能需求与冗余诊断分开。
- 查既有receipt或准备模板时只读文件，不把执行旧prepare当读取。优先使用当前机器已核的固定只读入口或小文本`rg`，目标文件只作data，避免动态拼接“Python+目标”而漏掉reader。机器本地入口不作为共享硬编码工具交付；helper的行数/大小断言若在读取后执行，就不是OS权限沙箱，也不能据一次只读回归宣布安全隔离或节省。复用helper先核真实入口、副作用和输出根，写入新owned任务目录，保已冻结目录。0HTTP/JVM不代表0metadata写入；误刷新旧清单时另记原SHA/现SHA、原像是否仍持有及未知成本，不能造原件、静默还原或回填创建时间。[真实跨案例准备副作用](../docs/evidence/2026-11-02-http-frontier-input-metadata-refresh.json)。
- prepare脚本本身属于写操作，执行前逐项核实全部输出目标位于本次新owned任务，既存原始证据禁止覆盖；复用工具不授权直接运行带旧硬编码路径的脚本。先在独立完成的工具调用中落BEGIN，再起草适配文本并核输出；没有原时间完整副本就保持NOT_HELD，不从后继记录补造旧时间或把零Java当作零副作用。
- 对具名小DATA原件，先核实际SHA并结构化解析精确字段路径，再断言长单行JSON缺字段或新增shape门；视读漏项不证明原件缺失。保原件、撤回的owner误判及未计量成本，不归模型或编译失败，也不为确认旧数据另造业务查询。[同原件纠错与真实重试例](../docs/evidence/2026-11-02-http-reset-then-length-analysis.json)。
- 实际运行消费者与正式主线源码不同时，先固定真实before pins与发布目的，按实际基线做窄port并逐hunk逆回核对。兼容packet、正式源码发布和运行采用分别留证；不能把旧baseline整叶覆盖到新主线，也不能把复用成熟helper记成新模型实现。[部分采用与实际兼容检查](../docs/evidence/2026-11-02-http-current-baseline-port.json)保留owner执行顺序纠正及全部准备/协调墙钟。
- 真实运行期可见选项建议单列任务类别，不纳源码候选采用率。模型选择、owner标签映射/输入、可视变化、Native独立读取与持久SAVE分别留证；文字标签输入不称模型看图，画面日期不授Native增日。模型HTTP重试不能触发第二次业务操作，恢复先查既有结果；后继成功不反推选项是此前失败的唯一根因。记录owner准备/协调墙钟，不能只报短模型响应。[实际分阶段案例](../docs/evidence/2026-11-02-http-visible-option-decision.json)。

这项路由针对当前真实证据，不是永久能力上限。普通HTTP与原生OpenCode继续分别跟踪；已闭OpenCode不限步重复循环不为成功配额重跑。其它新任务按实际权限和新的可验证问题选择模式。

## 新任务的输出规划

- 请求前列出要完整交付的目标单位、场景、声明/夹具及trace或DATA义务。完整测试和复杂见证按预计结构给6k–12k有限输出，或首轮拆成真正可独立验收的方法并复用机械夹具；小补丁按实际体量给窄预算，不一律重吐整类。
- 降低预算时同时核对完整输出义务是否相应减少。缩提示、少注释、换JSON DATA或减少场景可能有帮助，仍需核剩余循环、回调和全量观察是否能完整交付；不要把压预算本身当优化成功。
- 以实际REQUEST预算与END分类。length半稿整弃不拼接；未读半稿不能计为语义错误或永久能力上限，完整stop仍另审API/类型/语义。记录owner预算设计、范围调整和接管成本，未知写null；已闭题不为验证新规则重投。[已发生案例](../docs/evidence/2026-11-02-http-output-budget.json)。
- 普通HTTP候选的owner读取器/JSON解码器先核完整SSE与finish_reason=stop，再把正文作为候选解码；length不进候选解析。若实际误读或尝试JSON解析，按真实范围、失败和0采用留证，不能事后写成unread；截断解析失败本身不再计一份模型语义失败。此规则不把OpenCode合法tool_calls循环误作普通候选stop。[真实owner解码守卫错误](../docs/evidence/2026-11-03-http-saved-driver-replay-owner-witness.json)。
- OpenCode总步/总POST/整段wall与单响应输出上限分别记。用户已明确不限总迭代时保留该授权，单回复仍有限；不能用单响应length冒充总步到限，也不能靠不限总步把不完整工具参数当完整编辑。其它会话按其实际授权，不借此改变普通三消息system或活跃客户端配置。

## 当前采用立场

两种模式都有保留价值，这是当前分工判断，不是净收益已证：普通HTTP已有窄方法/hunk采用与复杂语义失败的证据；OpenCode已跑通受控工具编辑，三任务仍需owner修正。持续用真实交付和owner成本修正这个判断，不护航任一模式，也不把当前反例认定为永久能力上限。业务主线修复与实际运行优先，研究、记录和发布不作线上恢复前置。

发布门控的真实反例见[批准正文换行与失败后误推送](../docs/evidence/2026-11-02-approved-payload-publication-gate-failure.json)；这是owner流程失败，不能归模型，也不能把修复记成从未失败。

只读导航试点不应先用 owner 手工全闭包抵消其准备成本目标。先给明确版本和真实授权源码根，让工具检索声明；若范围误窄则分账 owner 输入限制。观察重复时抽取少量已有 REQUEST，核 tool_choice/有限输出、原 task/system 是否仍持有、assistant/tool ID、精确参数和返回 SHA，再区分完整相同内容、仅输出排序变化、有效新 range、权限失败、工具字节cap和范围后还有行的 truncated 标记；直接读已有结果尾部的 cap/continuation 通知，不能只靠结构化标志归类。无新信息循环可按实际证据停止获准 owned 会话，保中断流，不改成隐蔽总帽，也不因检查若干样本就宣布 backend/template 根因或净工时收益。[325实际诊断边界](../docs/evidence/2026-11-03-opencode-readonly-navigation-loop.json)。

已有原生日志优先复用 `python scripts/audit_opencode_trace.py TRACE_DIR` 的[脱敏审计结果](../docs/opencode-trace-audit.md)，再核少量必要原件。grep 的顺序比较必须保留文件/行/内容归属并检查每份结果，不能只解析首个结果或简单排序所有行；不同 read offset/limit 与显式 50KB cap 分别计。缺失/不识别保持 UNKNOWN，不能把工具诊断输出当业务审计结论。审计器没有自动 kill/重发或固定总步/POST/wall帽；实际干预仍依本次授权和明确证据。首次采用成本与后续省时对照分开，不用毫秒级重算抵扣此前人工劳动。

普通 HTTP 的格式结论先用 `python scripts/audit_http_evidence.py EVIDENCE_DIR` [离线核既有证据](../docs/http-evidence-audit.md)：严格分开 finish/DONE、外层 json.loads、正文语义与采用等级。自然语言末句未完或自相矛盾不等于 JSON 语法无效；STOP 也不证明语义正确。缺失/超限/冲突保 UNKNOWN 或具体异常，不补猜，不拼半截；CONTENT/SSE 原样差异与 LF 投影分别保。原件仍私留，报告 digest 的公开权限另审。新审计器本身的准备、模型拒收/owner 接管、验证和后续是否省工分别计；不能用一次离线重算抹去此前人工成本。

为原位重定义审阅body-only日志候选时，变量集合未增加也不能保证合成捕获描述符不变：日志访问顺序可能改变lambda捕获参数的first-use顺序。需要资格判断时，只读核实际生成class的fields/method descriptors及LambdaMetafactory捕获和implementation目标；javac0、源码捕获变量数不变及RAM异常路径Test都不代替shape兼容或Runtime实际instrumentation。正常日志schema、nanos值、嵌套inclusive计时和同步输出阻塞另验，不能用注入失败sink的测试授正常日志性能。[被实际classfile发现并修正的案例](../docs/evidence/2026-11-03-http-passive-submit-phases-owner-capture-shape.json)。

识别同调用重复读取时，先核API是否允许动态provider和原指令的观察点；同一地址出现两次不证明可以复用第一次局部值。分别保留原read/RMW顺序、预算和异常前缀，用可变化的显式软件port核第二次观察。软件port测试不授物理race/内核或硬件并发证明；之后独立源资格发现的新缺口应是新任务，不能追授此前截断审稿的finding。[同地址两次观察的真实修正](../docs/evidence/2026-11-03-http-whole-caller-fresh-observation-correction.json)。


Windows host读源必须在每个read exec cell开头定义并复用本机已核的`read(path,start,end)`构造：固定只读reader/显式解释器前缀，目标路径只作参数data，验证范围和shell字符；工具不支持的路径/引用形式应明确拒绝或按实接口修正。每次exec前必须把最终argv首token和完整reader前缀与本机已核literal逐token EXACT比较，同时核总token数、data槽和有限range；路径不能选择解释器/helper，构造不接收raw shell命令，调用工具前不得覆写已核cmd。shell元字符和未支持的引用形式在0进程前拒绝；helper执行/Git另用明确构造，不能按扩展名把读取分流成执行。授权helper执行与Git mutation用各自构造，不把数据path和raw shell字符串混在一列；绝不裸`.py`/JSON路径当读取，也不对未知有副作用helper试`--help`。元数据按resolved identity及精确size/SHA核，不用slash拼写定文件不同。保原命令/结果及association、dispatch或UI未知，不从exit0/空stdout断言0副作用，不据此扫描/杀其它进程或增加业务/模型请求。[经批准的多owner实际读取构造经验](../docs/evidence/2026-11-03-windows-owner-read-command-construction.json)。


源码故障分析遇到generic负ACK时，先枚举其折叠的pre-submit、wait、reclaim与业务读拒路径，不按短延迟择支或推rawread执行。核TLS的实际writer、owner线程和同次read-sequence；后读别线程或独立atomic值不能恢复旧cause。将executor-running timeout放回same-ticket真实循环核终态，empty optional不证明executor入口。模型给的line/function/branch anchor必须逐项回同份完整冻结原文独核。[经owner核准的通用事实](../docs/evidence/http-generic-negative-ack-source-analysis-boundaries.json)只增加审阅规则，不增加live查询、重试、编测或部署权限。


诊断source question要沿真实serialization核wire字段，early-return默认DTO值不能当测量态；mailbox生命期须核对象构造/销毁scope，不按连接名推reset。generic错误或短耗时不能推出submit成功、owner已观察或选失败支。[仅四条经owner批准的通用教训](../docs/evidence/http-default-diagnostics-lifetime-boundaries.json)不增加运行权限。


宿主协作model报capacity/turn中断时，按owner工具链与编排故障记录，不能嫁接为本地模型HTTP错误。续行先读已存在的REQUEST/POST终态、工具结果、ACTUAL与业务回执；原POST已发或动作状态UNKNOWN不能因宿主turn重试就重执行业务。仅在明确0START且确需首次验证时，接管原已准备工作并独立记owner成本；临时口述结果等待该owner完整批准case后再公开。两mode继续分开跟踪，无新原生缺陷修正/真实OPEN任务不扩旧native演示，不制造空请求；每reply有限输出不变成整体steps/POST/wall帽。模型被要求完整新Test却只回计划/0Java，按Test产物0采用记录，STOP/合法外层JSON不补出缺失实现。

共享 caller 的改动先在 owner 候选完成完整 parse 与必要窄 witness，再显式原子投影至共享 checkout，避免正在并发启动的消费者读到半编辑版本；这不增加逐 POST 审批或全量旧测试门。新 CONTENT 按拼接后 SSE 文本的 UTF-8 原字节保存，不经 Windows newline=None；历史原件/严格 auditor 不改，原样与 LF 投影不混。消费项目 caller/Runtime 配置由其唯一 owner 在实际空窗另行明确同步，共享 Git 不自动热切。准备语法错误、源码行尾投影和实际影响未知项都归 owner 工具链成本，不计作本地模型 HTTP 失败或语义错误。

消费普通HTTP结果时先读取新 RESULT.json_syntax 或对完整原件运行离线机器审计，再命名语法错误。外层VALID而语义自反、自然语言未完或错误源码事实应记语义问题，禁止靠肉眼尾部把它重标malformed。json_syntax只在完整stop/DONE并有限字节内报告，length/partial/超限为UNKNOWN；旧RESULT缺字段不重POST。legacy candidate_complete或退出0不覆盖严格syntax/owner审阅，尤其原有NaN接受行为未随元数据补丁改动。按独占候选parse+必要窄witness通过后原子投影共享caller；不自动切私有业务副本。

同步10054或近似十分钟相位只能触发有界只读调查：先按已具名EVENTS配对每次POST/END与模型-only retry，失败半流原件保管不拼接；宿主capacity turn错误与真实HTTP异常分列。读当前配置/已知维护缓存来源，不泛扫其它进程、timer或业务原件；已知只读health一次样本与服务running/waiting/uptime另标时，缺失仍UNKNOWN。少数相位/后见health200不授timer、restart、OOM或模型根因，不自动改配置/服务/重发chat，不把Ops调查设源/P0前置。既有角色attempt只交叉索引，不重复模型case/调用/Test分母。


当前用户明确目标为维持60实际POST未结束请求的rolling pool，覆盖旧并发目标。完整真实任务由owner直接并行，不等中央封包或发布；按实际END补不同未闭任务，不能重投旧绿或绕六attempt耗尽。逐来源登记EVENTS、配对区间、backoff和CLI活性分列，迟登记重建另存不回写旧快照；短峰达到60不等于持续维持。新任务显式高并发profile可用read600/total2400，旧frozen/inflight及Runtime副本不改。服务running/waiting/cache单独采样，client无headers不证明后端队列；priority能力需实际服务policy证据，不能把本机准入、公平轮转或空出一个客户端名额宣称硬推理保留slot。无新原生工具修正不重跑旧无限循环，HTTP与OpenCode仍分轨。


用户已明确局域网本地模型不应经环境代理。共享HTTP入口默认DIRECT：无network时从可信config.base_url取exacthost，独立ProxyHandler({})并拒redirect；executor与source高并发配置明示DIRECT/currenthost。只有明确选择environment才兼容用户刻意使用的代理。迁移时核真实caller/config来源与本次选路，不把旧opt-in文档当当前默认；不改旧frozen/inflight或自动切Runtime副本。默认修正不证明服务恢复，TCP已连接与headers/TTFT/完整SSE分别取证，不从异时proxy/direct请求授严谨AB或solecause。
