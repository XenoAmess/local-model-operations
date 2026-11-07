# HTTP 候选与有界测量：大Life输入的技术registry投影（P106）

case_id：`HTTP-JAVA-LARGE-LIFE-PAYLOAD-106`；mode_id：`http-candidate`。本地观察日为2026-11-08（Asia/Shanghai），下列精确时间使用UTC，实际请求在2026-11-07。这里只整理已发生的源码候选及后到软件／测量，不发新HTTP、JVM或业务操作。原始请求、源码、私有游戏材料和测量原件留执行机器，公开元数据见[脱敏摘要](2026-11-08-http-large-life-payload106.json)。

owner提供给模型的实际纯DATA观察为：两个现有compact资格都成立，但原完整compact输出65913 B，超过原65536 B启发阈值而回到完整formatter输出1537575 B。技术capability数组有134项，与observations中的registry按集合相同；当前Life意图需要6项。任务同时提供user59757 B／policy920 B及仅投影技术registry后预计60559 B的观察。这些是提示中的既有DATA观测与设计依据，不是本例后继A／B结果或Runtime测量。旧运行REQUEST的2784926 B来自另一来源，不能作为P106对照基线。

实际请求提供5份完整源码，稳定源码消息108992个UTF-8字节。REQUEST为system/user/user、`qwen38-coder`、max_tokens2300、temperature0、thinking=false、JSON object、SSE/include_usage。唯一POST为2026-11-07T18:39:06.684080→18:39:15.229576Z，200／stop／DONE／完整JSON，0传输重试；headers3.3356001秒、有效内容TTFT3.3368900秒、总8.5454961秒。reported输入24006、输出841，cached tokens未报告、实际socket peer为UNKNOWN；模型别名没有固定权重或后端版本。没有OpenCode原生生成任务。

任务已完整给出overflow-only分支、全部资格判断、精确marker／policy suffix和两次原64 KiB判定，属于强设计指导实现。模型提供局部validation／mutation核心，owner部分采用并调整已有Set import、直接复用required List、命名、注释与分行，不为required项另建多余HashSet。没有已证模型业务错误，不称完整方法或整个diff原样采用。

源码只在原完整compact超过阈值后检查技术数组：类型必须正确、每项文本、与当前observations registry集合一致并覆盖当前意图全部依赖；通过后只在本次私有snapshot树中用排序的required subset替换该数组，添加明确投影marker及policy，再按原阈值判断。原小输入先返回同一完整输出；未知、类型不符、registry不匹配、缺依赖或仍超限走既有generic fallback。其它原资格、unknown siblings、完整proposal、已有trace／facts、command、原deadline及authority不改变。这里有意投影技术registry，不能笼统称完整generic输入逐字无损。

最终生产源88546 B、SHA-256 `817857e4fac372f13ac5807a1c7d881070175330f9f49a4181ebfe5cb4d8ebae`，基线为P105正式源码`0a8878ce9566a2c835bb8a1cd4e5cd8792a88e4a`。必要生产编译始终只有1 TU，exit0／4 class／6.9278569秒，18:42:19.547408Z资源关闭；后续只增编改变的Test变体，没有为测试修改生产codec。

来源边界：最初probe01的fact-before／evidence原件未导出，使用已经省去native history的约45 KiB snapshot，只称DATA reconstruction，不冒充原内部Root对象。后继Test／测量按已审producer规则，从具名已qualified Driver的同一139行originalRow恢复snapshot.native_command_history与request.history；原被删成员在snapshot中的插入位置未知，仍明确标为重建变体。A／B使用相同变体，计时包含完整requestPayload、失败的初次compact编码及P104共同历史字节比较。没有把旧2784926 B运行REQUEST或漏掉历史比较负担的初始probe当A基准。格式器完整输出和实际模型HTTP REQUEST字节分别记录。

验证首轮为3个新方法2P／1F；大输入60559 B长度已过，但测试错误地要求跨JVM保持原prospective的全局候选SHA，失败发生在独立完整oracle断言之前。diagnostic02先核完整oracle，actual与oracle在同一JVM逐字相同，随后同一全局marker断言仍1F。Root独立diff定位到唯一`/bounded_stop_intent/advance_plan/campaign_deadline`：8个Map.of成员的跨JVM顺序不同，外层、user前后字节以及精确数字token／值相同。原RED、实际wire和diff均保留；这是owner测试假设错误，不归模型候选或生产语义。

test03只去掉不成立的跨JVM候选全局SHA假设，保留完整独立byte oracle，候选marker在每个JVM内固定；原A基线SHA从未修改。只重跑原失败方法，实际1P。最终三个新方法的通过由首轮保留的两绿加修正后一绿组成，不能称最终一组在同JVM一次3P。三个必要Test变体各自编译及2P1F／1F／1P窗口均保留，旧绿与原probe／生产未重跑。

实际有界实验为四个独立JVM，顺序A0／B0／B1／A1；每JVM CPU1、384 MiB、45秒预算，各2次预热和4次测量。每模式8个测量值，全部8次预热与16次测量保留，无删慢样本、强制GC或速度断言。仅Selector的原P105／新P106二进制前缀不同，其余输入、依赖和资源参数相同。

| 同一重建输入的报告值 | A：原P105 | B：P106 | 描述性变化 |
| --- | ---: | ---: | ---: |
| 完整formatter时间中位数 | 140.26505 ms | 47.0638495 ms | −66.4465% |
| 完整formatter时间均值 | 141.813125 ms | 47.86178725 ms | 保留全部样本 |
| 主线程分配字节中位数 | 192894264 B | 61160740 B | −68.2931% |
| 主线程分配字节均值 | 192894234 B | 61160648 B | 非全进程分配量 |
| 完整formatter输出 | 1537575 B | 60559 B | −96.0614% |

四个实际进程窗口分别为A0 7.3081617、B0 6.5738208、B1 6.5374365、A1 6.8021172秒。完整main、load、oracle setup、预热、outer窗口及OS进程峰值另保；不拿formatter子窗冒充完整进程提速，也不从计时子项精确扣除启动。主线程allocated bytes不是总进程分配或RSS／heap峰值。

每个候选JVM均与自身独立完整oracle逐字一致，所有本JVM样本保持该marker。跨JVM的候选SHA可因上述既有Map.of顺序而不同，原A的`1c1e7c0f…`全局基线保持。最终原件为完整样本分析25343 B／`6b31c8430ddfb47bd5fe300e62b7ab0f0e53a967834e0fc5ec4593004da8184c`及独立Root复核7051 B／`a6998fa87a683270b3619e742287d2eb06cc187ac2c529c6cbaaa1c817a65f7f`，所有资源于19:07:14.448230Z关闭。

业务正式发表为`94d85256583ac226f62c5638220c16315bae962a`，7个文件，owner／Root确认与remote master一致；P107独立dirty文件保留未混入，不能写业务整树clean。以上是同输入离线组件结果，没有新运行决策HTTP、Runtime装载、Game推进、SAVE或端到端秒／保存日收益。

准备、主动审阅、纠错、协调、编测与发布成本缺少独立phase原件时为unknown；源码生成TTFT不代表运行决策TTFT改善。持续优化目标仍由业务owner推进，一个案例发表只关闭本有限记录单元，不自动宣告端到端目标完成；下一真实call／验收出现时继续追加，不能为连续性制造调用。
