# HTTP 单行采用与有界测量：cash重复snapshot编解码（P108）

case_id：`HTTP-JAVA-CASH-SNAPSHOT-PERFORMANCE-108`；mode_id：`http-candidate`。本地观察日为2026-11-08（Asia/Shanghai），精确请求时间为2026-11-07 UTC。此处只读已有原件并发表脱敏记录，不新发HTTP／JVM／业务操作；公开元数据见[脱敏摘要](2026-11-08-http-cash-snapshot108.json)。

owner已指定唯一修改：public cash调用RawCash.normalize时，将第二个完整snapshot参数换成P107已经闭合的融资角色，第一参完整现金资源不变。完整RawCash源码与独审已闭合frame／actor／alive／paused／map_ready及hello build键的presence优先级。任务给出确切目标表达式，属于强指导窄实现；不是模型独立发现依赖或算法。原snapshot／request、软件READ packet、source、Guard、查询及codec预算均保持。

实际5份完整源码，源码消息94467个UTF-8字节；fixed system/user/user、`qwen38-coder`、max_tokens1000、temperature0、thinking=false、JSON object、SSE/include_usage。唯一POST为19:12:29.617692→19:12:35.730908Z，200／stop／DONE／完整JSON、0重试；headers2.8492552秒、有效内容TTFT2.8512367秒、总6.1132815秒，reported输入21394／输出456、cached tokens未报告、实际peer为UNKNOWN。没有OpenCode原生生成。

单行hunk在最终源中逐字采用；不是完整方法或文件原样采用。模型额外说明误把未读的snapshot.player_armies等列为依赖，并声称角色保留它；owner按完整codec与独审拒绝该说明，没有为说明扩helper。代码采用与解释正确性分账。该行依赖P107新增私有helper，相对冻结Runtime不能据“小改动”授body-only热替或实际装载。

必要生产1 TU exit0／12 class／5.8104523秒；新Test/main 1 TU exit0／2 class／4.77816秒，仅2个新方法实际2P／0F／0E／0skip、7.662193秒，无本单RED。覆盖32项既有Loan normalize向量、7项rawContext及unpaused／dead_actor两个原拒绝，并核NormalizedCurrentCash全部typed getters、encoded bytes和真实public cash纯软件packet不变。这些向量不是32或41个新JUnit方法；肯定输入来自既有synthetic original-producer软件案例，额外139行历史只作未消费扩展，不授同世界或实机许可。旧fixture仅复用加载器／软件READ producer，不跑旧@Test或重编旧codec。

四独立JVM固定A0／B0／B1／A1，仅P107／P108 Collector classpath前缀不同；CPU1／384 MiB／45秒，每次2预热、4测量，全部8预热与16测量保留，无删慢样本／强制GC／速度assert。计时包含完整public cash软件READ解码、输入组装／encode、normalize和原完整现金来源检查；独立oracle／load／setup／main／process及outer窗口另保。

| 每模式8个测量值 | A：P107 | B：P108 |
| --- | ---: | ---: |
| public cash中位耗时 | 26.075399 ms | 9.7960495 ms |
| public cash均值 | 27.430274625 ms | 10.24948725 ms |
| 测量范围 | 21.055099–38.9299 ms | 3.1893–20.6737 ms |
| 主线程分配中位数 | 53363560 B | 572224 B |
| 主线程分配均值 | 53364058 B | 572362 B |

描述性组件中位耗时约减少62.4318%，主线程分配均值约减少98.9274%；后者不是全进程分配、heap或RSS峰值。两个模式的完整outer窗口合计为A12.0043524秒／B11.0969114秒，不能把组件变化当完整进程或HTTP／游戏日吞吐收益。

四run输入snapshot均3402368 B、SHA `4c6ccb4bf0e573f3aba5f5ac81660e0f17bbbf1fa88f5b5bacb35d9c72c45c83`，角色434 B。raw cash为4134 B／`0d77b4f11c585ecd16c3c544731aa98eda507ecdb5e966fce81d2c1dcdde4e0d`，normalized输出也为4134 B但SHA是`a3adf5888633a292b85514cd23c6c486f0cbb3555c044ed056e9ddcd90330d11`；它们不是同一字节对象，分别跨四run一致。软件packet的SHA为`757bc2af2b1e6951401193f8d051ef7f2cef98f278274fc932e98f853781c867`且跨run一致。没有通过删现金或改原件取得差异。

历史wrapper仍有LIFE106 schema／event标签，原件不回写；实际CONFIG、FQN、source、mode和子进程记录明确绑定P108，不把它计作另一P106运行，也不为标签重跑。末资源于19:30:40.975409Z关闭。最终资格25182 B／`702d0ee82242a76392e160e8f41b6c10606561cbaa470230b38587eb7a3dea01`，全样本12093 B／`e1ba25a5c4ce560bbac3d00e8fdaa75ded2aaf8a358b0ec24653de389a0f6192`，独立Root复核7282 B／`1261eb8a3f9d58691cefa3506c56ef4dd951fada7266b8def1df58376825be1b`。

业务5文件正常发表`e4568300d1d34e5e69b34d891cb5a14cd642cfb9`，remote master一致；P109独立dirty保留未混入，不称业务整树clean。没有Runtime、Native实查、运行决策TTFT或新增确认保存日信用。主动准备／审阅／纠错／协调／发布及净owner节省缺phase原件仍unknown。此case发表仅关闭有限记录单元，持续性能目标仍进行。
