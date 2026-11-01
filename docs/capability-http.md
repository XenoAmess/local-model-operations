# 普通HTTP候选模式：长期能力记录

mode_id：`http-candidate`。2026-11-02（Asia/Shanghai）建档，初始证据来自已发布历史及2026-11-01摘要；建档没有新模型请求或测试。此页持续追加，阶段结束不停止运营。共同记录字段、比较约束见[能力证据总入口](capability-boundaries.md)，执行者先读[长期运营prompt](../prompts/capability-operations.md)。

## 范围与当前判断

owner把稳定system、完整当前源码/合同、变化的任务/诊断组成三消息；模型返回有限候选。文件读取、应用、编测、业务与Git由owner控制。共享入口是[scripts/call.py](../scripts/call.py)，配置来自[config/executor.json](../config/executor.json)；完整请求规范见[使用指南](usage.md)。旧业务caller版本与共享caller版本分别按案例记录，不能视为相同实现。

保留此模式用于源码和调用合同已闭合的窄方法、消费者修复及独立诊断候选。有原样方法/hunk采用的证据，也有完整输入下反复语义错误、最终模型采用0的反例。候选接口可复用、可并行，不证明owner准备和纠错成本已降低；尚无与OpenCode固定条件下的效率比较。

## 基线案例

| case_id / 观察 | 输入与实际结果 | 采用、验证及边界 |
| --- | --- | --- |
| HTTP-PARSE-001 / 2026-10-31整理的历史窄修 | 确切栈、相邻API和完整reader声明，目标为typed parser/ref两行预算修复；首轮目标修改原样。 | 指定实际链与两个正负场景通过。支持完整合同下的窄修，不授整个恢复图。[公开原记录](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L6-L25)；此摘录没有固定精确caller可执行版本。 |
| HTTP-CONSUMER-001 / 同批历史 | 13文件、138201字符，两个parse消费者；owner补2 imports，负例再暴露4处异常映射回归，精确诊断后7个完整edits原样。 | 实际链、6负例及既有10项通过；最终通过不抹去前轮回归和owner反馈成本。文件数不是整项目自主实现范围。[同一原记录](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L6-L25)。 |
| HTTP-FRAME-001 / 2026-11-01 UTC | 完整当前API与算法，实际源码消息52886B；两轮各9000输出tokens，3 POST含1次reset，2份完整stop。 | 两稿源审拒绝，模型Java采用0，owner完整实现后有限软件验证通过。错误包括实际成员/帧布局、寄存器状态、读事件与回调状态混淆；不是length或缺API导致。[证据](evidence/2026-11-01-stateful-frame-bridge.json)。 |
| HTTP-AUDIT-001 / 2026-11-01 UTC | 两项21/24文件作用域审阅，实际源码消息1222924/1325283B；各一次POST完整stop，无HTTP交叠。 | 仅部分分析参考，模型源码采用0、无编测；出现缓存hit语义、行号和局部链外推错误，旧标签部分来自owner输入。大输入被接收不证明整图审计正确。[证据](evidence/2026-11-01-scope-callchain-audit.json)。 |
| HTTP-SSE-001 / 2026-11-01 UTC | Windows/Python3.13.2共享caller，13份源码、第二消息345139B，5500输出预算；真实SSE 200/stop/DONE，18.438819s。 | 只授传输与参数兼容；答复正确性、源码采用、其它平台和服务容量未由本单证明。cached tokens未报告，保持null。[证据](evidence/2026-11-01-windows-service-call.json)。 |
| HTTP-RETRY-001 / 2026-11-01 UTC | 一个真实源码审计任务先HTTP200半截SSE/reset，退避后同逻辑任务第二POST完整stop。 | 半截流整丢弃、无拼接/回退/业务重放；调用器构建同body，未声称每轮独立wire-body抓包。仅部分流程分析可用，模型发现拒绝/代码采用0；传输恢复不是语义恢复。[证据](evidence/2026-11-01-windows-transient-retry.json)。 |

以上不是可合并的采用率：两行、完整方法、hunk、分析和HTTP尝试的分母不同。历史案例的准备/审阅总成本未完整计时，保留未知，不用最终通过倒推“省时”。

## 后到案例

| case_id / 观察 | 输入与实际过程 | 采用、验证及边界 |
| --- | --- | --- |
| HTTP-SESSION-001 / 2026-11-02 Asia/Shanghai | 一个真实只读回调入口，要求暂挂实际可写调用者并恢复原作用域。实现与独立原源审计各一次三消息请求，第二消息均484893B，输出上限6500/4200；2 POST、2 stop/DONE、0重试，客户端峰2连续29.206204s。 | 新方法严重错用接收者、TLS及回调参数，由owner完整重写；只保留私有暂挂字段/检查形状，审计对只读guard必然拒绝的论断也被拒。owner首1TU严格编译0，后到4个方法通过；不追授模型方法成功、Game或性能。[脱敏实证](evidence/2026-11-02-http-scoped-callback.json)。 |
| HTTP-IMMUTABLE-001 / 2026-11-02 Asia/Shanghai | owner给定私有不可变基线字段、构造初始化和四处固定编码操作数替换方案；5份当前完整源，前缀文件119236B、实际第二消息117840B。实现/独审各限2200输出，2 POST完整stop，耗时11.631/12.172s。 | 五个有序替换块文字全采，owner按实际匹配数[1,2,2,1,1]逐次应用并核整源inverse，没有语义改字；首1TU严格编译0。审计仅不可变性主题部分可用，索引伪反例、equals推测与IO收益拒绝；没有行为测试、部署或提速证明。[脱敏实证](evidence/2026-11-02-http-immutable-baseline.json)。 |
| HTTP-SCOPE-001 / 2026-11-02 Asia/Shanghai | owner预选两个回调内的有限历史读取作用域；8份源，实际第二消息各391423B。实现/独审上限3600/2800，2 POST完整stop、0重试，耗时33.037/30.963s，客户端峰2连续30.962808s。 | 四个literal替换块原文保留，owner补两个缺失import；首1TU严格编译0，分级为partial加owner。审计混淆实际内外层session，并误判预算满时抛错，否定结论拒绝；未验证行为、并发或提速。[脱敏实证](evidence/2026-11-02-http-bounded-scope.json)。 |
| HTTP-OUTPUT-001 / 2026-11-02 Asia/Shanghai | 两个真实有限见证案例，各有两个独立方法/角色、最多两轮；8 POST/8 END、0传输重试。A预算5500/6000→各4500，4份全length；B预算4500/5000→各3500，1 stop、3 length。 | 七份截断正文均未作语义阅读、整份丢弃；唯一完整stop另因API/类型/语义错误拒绝，模型采用0，owner按先冻结oracle完成。缩范围/换DATA确有尝试，预算是否与剩余完整义务相称未证；不重投闭题。[脱敏实证](evidence/2026-11-02-http-output-budget.json)。 |
| HTTP-OUTPUT-002 / 2026-11-02 Asia/Shanghai | 新的两个独立有限方法复用机械夹具，首轮各10000输出、纠正轮10000/12000；4次逻辑调用、6 POST。纠正轮两份partial SSE/reset自动重试后完整stop；4份最终completion为4182/4662/1984/2019，0 length。 | 四份完整方法仍因实际地址/读序、类型、绕开目标和弱trace/最终状态断言等源审错误整份拒绝，采用0；owner whole源在冻结时未编RUN。不是预算耗尽失败；任务及修正输入不同，不从无length推预算因果，也不重投前案。[脱敏实证](evidence/2026-11-02-http-complete-witness-rejection.json)。 |
| HTTP-LIFECYCLE-001 / 2026-11-02 Asia/Shanghai | 私有bootstrap→live资格的方案与独立反例两任务，9份当前源，实际第二消息各720311B，上限8000/5000。两首attempt收到有效内容后reset10054，分别自动重试一次；共4 POST，最终2 stop，23.760/19.383s。 | 源码采用0，仅有限现有链事实/checklist参考。跨包私有调用、public boolean自证资格、把Core返回当成Host安装完成、整体跳动态guard等方案错误拒绝；审计旧head等式也会拒正常推进。owner两阶段资格合同尚未实现、编测或运行，不授节省工时。[脱敏实证](evidence/2026-11-02-http-lifecycle-handoff.json)。 |

HTTP-SESSION-001的实际REQUEST参数与hash已核；owner记录两份请求均包含32份冻结源码的全部非空行，但CRLF组装增加空行，并非逐字节嵌入。这个覆盖检查不等于所有必要依赖闭包已独立证明，后者仍记unknown。验证使用owner已见实现的有限场景；首次测试启动因漏既有JNA目录参数在目标前失败，仅改argv后通过，原失败保留。准备、源审、纠错和协调成本未完整计量，不填0，也没有模式比较或净省时结论。

HTTP-IMMUTABLE-001授予的是明确方案下的有限代码生成，不授模型独立发现热点或设计优化。复用仅针对私有固定材料的编码字节，四处fresh current编码和全部实际读取/hash/pin/资格检查保留，record equals替换未采用。它与上一例的整方法接管分别记录，不合算采用率。owner机械应用、审阅与部署成本尚未完整计时，未知不填0；静态少做固定编码不等于减少IO或获得运行收益，后到接受/装载与实测另加。

HTTP-IMMUTABLE-001的[后到采用和运行阶段](evidence/2026-11-02-http-immutable-baseline-late-runtime.json)独立追加，原冻结记录不改。实际源副本、正式blob与选定候选按LF一致；复用构建6.234652s、exit0，随后精确producer编译回执和首解析检查用于装载核对。实际运行163.229660s、exit1，越过较早领域阶段后停在鲜开局的持久规划门，未到LOOP、新确认保存日0，秒/新增保存日保持null。同批还有其它源修改；这些回执不证明该编码改动带来IO、CPU、延迟收益，也不把越门或后续失败归因于它。

HTTP-SCOPE-001核对的是实际只读接收者创建的旧inner session；可写outer暂挂，历史作用域在该inner关闭、原outer恢复前结束。共享Store与ThreadLocal链、全部原资格检查保留，有限缓存不能接纳时回退实际完整读取，不跨作用域缓存结果或权限。不能凭变量名把inner当成new mutable session，也不能把缓存预算满读成必然抛错。这里实际提供的8份源与源码消息已核，所有传递依赖是否完整仍为unknown；准备、审阅与补import成本未量化，原截止时Main采用、运行和收益尚无回执。

HTTP-SCOPE-001的[后到采用、运行与必要行为验证](evidence/2026-11-02-http-bounded-scope-late-validation.json)另加阶段，原冻结记录不改。正式源与候选按LF一致，复用构建5.852557s、exit0，实际装载编译回执/类pin已核；运行174.395440s到真实LOOP，223.483124s后因opening snapshot结构故障exit4，新确认保存日0。另一个owner完整测试首1TU编译0、两个新方法2P0skip，覆盖实际只读入口与历史scope的成功/poison退出及原outer恢复；测试模型原稿整份拒绝，不能把owner验证追授为模型测试成功。这两个方法也没有直接调用完整Root消费者；缓存命中率、全部保存材料传递覆盖及性能仍未知。同批其它源改动使运行窗口不能与上一轮直接归因比较，工时保持null。

## 已知边界与操作方法

- 输入由owner封装，模型无法仅凭一个路径自行取得未提供的声明；检查真实REQUEST，包含祖接口、callee、MAX值、消费者和名义返回类型。输入缺口与齐全输入下的模型错误分别归因。
- 完整stop不保证实现完整。复杂帧/ABI、跨回调当前状态和多对象作用域仍需owner逐项核对，反复语义错误后接管，保留原始失败。
- 作用域候选和审计都要核实际接收对象、TLS归属、回调收到的参数，以及主异常与恢复异常的顺序。旧入口拒绝普通嵌套，不足以证明一个新受控入口不可设计；guard的条件检查也不能读成无条件抛错。
- 缓存预算的接纳、回退和失败路径分别按实际callee核对；预算满不自动等于业务失败。源审中对并发安全的肯定或否定都需真实对象、线程和生命周期证据。
- 大上下文接收成功不证明理解覆盖、最大有效上下文或缓存效果；别名不是已核实权重版本。实际参数未转发时，不记成该参数实验。
- 普通caller不执行assistant/tool循环，`tool_calls`终态不能作为完整源码候选；其工具能力不能从OpenCode闭环继承。
- 修正轮更新真实源码和完整合同。只采用完整目标单位，不拼length/reset半流，不因HTTP重试重放业务动作。详见[并发与重试](concurrency-and-retries.md)。
- 给新的完整测试/复杂见证预算时，先估必需方法、场景、夹具和完整trace/数据体量；按实际结构给6k–12k有限输出，或拆成可独立验收的方法并复用机械夹具。缩短提示或改DATA不保证完整产物等量缩小；降预算也需相应减少完整输出义务。length只证明该预算内未完成，未读截断稿不计语义失败；预算放大也不保证正确。[实际反例与owner成本](evidence/2026-11-02-http-output-budget.json)。
- 跨层资格设计沿真实调用次序核每个完成点：Core返回、Host字段已赋值和后续安装准备全部成功是不同事实。保留实际当前所有权/动态校验，不能用public boolean或旧head不变代替私有完成资格；性能热路也不自动是合法提前发资格的位置。HTTP-LIFECYCLE-001只记录源审与owner未实现合同，不证明该合同已安全可用。

## 客户端保障与生成能力分开

共享caller已增加本地证据I/O分类：RAW预开失败不调用网络，也不记POST_BEGIN；写入/flush/close及输出失败不当成网络重试，503/不完整SSE仍保留重试。`post_invoked`只表示进入网络调用，不证明服务端收到。

这项改动有4个新增离线方法的分期验证，是[OpenCode案例OC-LOCALIO-001](capability-opencode.md)产物经owner修正后的客户端能力，不能计为普通HTTP模型的代码生成成功。[采用/验证](evidence/2026-11-01-caller-local-evidence-delivery.json)、[发布版本](https://github.com/XenoAmess/local-model-operations/commit/761ef26d8dab26cc08442457040a1025f1448571)。有限Windows离线测试不证明所有本地I/O故障或其它平台。

## 继续跟踪的问题

| 下一项真实任务触发条件 | 要补的证据 |
| --- | --- |
| 新的依赖闭合窄方法/消费者需要修复 | 记录封包、审阅、owner改动与必要验证成本；区分首轮原样和反馈后的采用。 |
| 新的复杂状态或整图审阅任务 | 按原始合同独立冻结必要见证，记录输入是否齐全、具体错误及接管范围；不复跑已完成的反例。 |
| 新的真实作用域/只读回调入口变更 | 在读候选前冻结合法双角色及拒绝场景，逐项核接收者、TLS、回调参数和异常恢复；记录完整方法与有限字段采用的区别及owner成本，不重投HTTP-SESSION-001。 |
| HTTP-IMMUTABLE-001已有源采用/装载记录，后续自然产生必要行为或性能观察 | 对精确版本追加实际窗口、零保存或失败耗时，区分固定编码工作与实际读取/hash/pin；不从classpath核对推收益，不为证明收益重启健康运行或重投旧任务。 |
| HTTP-SCOPE-001已有采用和两个owner组合测试，后续业务独立需要验证预算/回退或运行 | 追加精确版本的实际行为、反例及完整窗口；区分有限API组合验证与完整消费者/保存材料传递覆盖，不重投闭题或重跑已绿方法求证。 |
| 真实业务需要实现跨层私有资格，且前置功能源码已独立闭合 | 重新pin实际调用链；核后阶段失败不能发资格、精确owner退役/替换与合法head推进，保留锁序及可见性审阅。模型方案、owner设计、源码实现和运行各按回执记录，不复投HTTP-LIFECYCLE-001两闭题。 |
| caller、服务、模型或执行平台变化 | 只在实际新需求中核参数、SSE、重试和错误分类，版本变化不自动继承旧结论。 |
| 有适当的真实模式比较机会 | 按共同条件记录交付、owner成本、失败和顺序/答案暴露；没有对照不填相对效率或净节省。 |

每个触发点追加case_id和证据链接，完成可审阅单元及时推送main；没有真实任务时保持待验证状态，交接给下一owner继续维护。
