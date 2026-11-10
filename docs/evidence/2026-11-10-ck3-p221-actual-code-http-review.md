# P221：实际Code输入与未来程序候选

本单元新增11次真实POST，10份完整stop、1份length整件弃用，0传输错误和重试。与[此前29次](2026-11-10-ck3-p221-http-concurrency-output-budget.md)合计40次HTTP200、32完整、8截断。前单元峰12持续58.643748秒；本单元峰9持续61.924035秒，不能相加或说全窗口持续高并发。

输入从Source-only推进到独立编译回执中的实际6类／57方法：Main37、Counters5、Loader2、Fixture9、Side1、Caller3。复用既有纯Python class reader，按义务提供完整相关方法的resolved Code、分支、catch及BSM，并保全当前生产者、消费者和合同。没有启动Java或反射，没有新解析平台。Caller710B源仍是唯一模型原样采用；其独立编译产物为1030B，三方法Code字节数为5／12／9。不能把这当作模型主文件或实际测量通过。

9个大Code请求实际输入36,998–208,289tokens，TTFT最大148.594秒；无超时但接近配置180秒读窗。没有继续叠加大请求，server running/waiting/KV仍NOT_HELD。5份辅助静态PASS保留了运行和实际绑定的未知项。Counters审阅提出无反例且自行推翻的缺陷：其所称pc182目标为类名，实际ifnull目标250，pc189已调用support探测。owner拒绝错误finding，独立完整57程序核验另有具名原件，不由HTTP标签发放资格。failure审阅达到length，整件未读、未拼接或重投。

最初两个future reader/checker任务虽然完整stop，却只回答“没有实际report无法验收”，没有交付程序。这一证据边界判断正确，任务义务仍未完成。新请求只保留完整当前Main、成熟reader/checker及合同，明确要求写未来输入程序、不要求现在运行；输入降到19,163／20,912tokens，TTFT3.405／3.660秒，分别19.016／21.275秒完整产代码。这是不同工作量的客户端观察，不是模型服务容量或缩上下文因果实验。

两程序仅AST语法可解析，源码审仍拒用。数学reader未把signed pair numerator除128就与已按per-call记录的median比较；每pair numerator128应为1，它会错比128。它还遗漏部分全局输入／cleanup及CPU、enclosing、POST重算。checker遗漏original_oracles五精确计数和no-firstA，部分声明的Main/tail绑定未消费，身份、最终输入及清理核验不完整。没有执行候选程序，也没有让AST或HTTP200变成验收PASS。连续完整validator失效后由owner接管，不再第三轮同源派发。

逐请求tokens、TTFT、耗时、峰值和完整失败均见[证据JSON](2026-11-10-ck3-p221-actual-code-http-review.json)。原件及绝对私有索引留执行机器。请求时没有提供measurementCFG或actual report；未来真实运行、收益、Runtime及保存日仍须独立原件。仅此有限模型单元结束，主目标持续。
