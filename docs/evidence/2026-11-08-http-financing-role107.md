# HTTP 候选：融资snapshot角色的字段闭合（P107）

case_id：`HTTP-JAVA-FINANCING-SNAPSHOT-ROLE-107`；mode_id：`http-candidate`。观察日为2026-11-08（Asia/Shanghai），精确时刻以下均为2026-11-07 UTC。此案整理真实源码任务、采用和软件验证，没有为记录案例增加HTTP／JVM。原始请求、源码及私有材料留执行机器，公开元数据见[脱敏摘要](2026-11-08-http-financing-role107.json)。

原producer把数MB完整snapshot历史传给只接受65536 B的融资角色，而该角色不读取历史，导致进入typed判断前先撞容量门。owner先给出Gap／Emergency消费者及明确字段、presence／类型／错误行合同；后续实际发现Loan wrapper也经过同一容量边界，第二轮增加Loan／RawCash完整声明与字段并集。这是后到真实合同扩展，不能把第一轮未覆盖后来才加入的Loan需求算模型遗漏。两轮都是强指导实现，不称模型独立发现完整闭包。

| 轮次 | POST_BEGIN → END（UTC） | max_tokens | 完整源码数／源码消息UTF-8字节 | 有效内容TTFT秒／总秒 | reported输入／输出tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 18:52:01.297155 → 18:52:12.621943 | 3500 | 9／145427 | 4.1723146／11.3246599 | 31479／1206 |
| 2 | 18:53:05.191259 → 18:53:17.394985 | 4000 | 11／187255 | 2.2872804／12.2036912 | 41538／1706 |

两轮均system/user/user、temperature0、thinking=false、JSON object、SSE/include_usage，1 POST／1 END／0传输重试，200／stop／DONE／完整JSON；cached tokens均未报告，实际socket peer为UNKNOWN。输入和任务范围同时改变，TTFT差不能归因缓存；模型别名没有固定权重或后端版本。没有OpenCode原生工具生成。

首稿缺实际imports，又在war行缺ID时把父数组当回退值，未保原行错误语义，源审拒收且未编跑该稿。第二稿的字段union与两处接线方向部分采用；owner用更小的copy-present／原顺序helper完成实现，并未采用遗漏imports或扩范围代码，不称完整方法原样采用。

最终角色保frame、actor／alive、gold、逐行war_id、paused／map_ready、PID／connection generation，以及hello的expected_ck3_version／expected_ck3_sha256／game_version／executable_sha256；只复制实际存在成员，缺失、显式null及错误scalar／array／object形状保持。expected build键即使null仍优先于fallback键。root、priority、construction ledger、完整cap表、cash_resources和cash_source_frame保持；source extra仍由原全对象比较拒绝。原snapshot／history留Java，角色不是完整归档或新权威。新增两个私有helper属于软件结构变化，没有实际装载或redefine信用。

输入来源明确为软件DATA：已qualified Driver1475的前139行只是无关、未消费的大history扩展，不声称与FinanceCurrent同一实际世界。肯定Loan取原producer软件向量ordinal314，本身标为synthetic episode／cash source；不是实机Loan许可。原holyloan gzip 20361 B／`4d0b61ac6ce05b16b78b3ff4bf51891b9780ba348edff7d8c8c6da09780c3539`及Gap corpus 68264 B／`36133fdf1f0da339cf31f453c7c162a3e909d63ab5b7152adda1d9d1cee0dee3`留原处，未上传游戏历史。

必要生产1 TU编译exit0／12 class／6.3407652秒。新Test首3方法为1P／0F／2E：两个公共接线路径在owner夹具的大写machine ID构造处失败，尚未到Collector；31-vector方法已绿。只改夹具为原小写合同，生产Guard不改，增编改变的Test并仅重跑两error方法，实际2P／0F／0E／0skip、7.1471883秒。原1P保留未重跑，不能称最后同JVM一次3P，也不能把夹具错误算模型或生产错误。所有阶段和原错误均保留，最终19:17:46.829631Z资源关闭。

软件覆盖为实际public Gap／Emergency／loanFromCash链路及既有registered软件packet；Loan Projected的frame／observation／encoded bytes对原小输入相同，原packet／request／cash／source保持。31个既有向量在一个新方法中作角色对照：28个typed结果相同，3个原拒绝保异常类型／消息；这不是31个新JUnit方法。另保build-null优先、source extra、浮点revision、actor和坏war行等原拒绝／unknown语义。

| 同输入软件扩展 | 原完整角色输入 | 新typed角色 |
| --- | ---: | ---: |
| Gap | 3404665 B | 2662 B |
| Loan wrapper | 3406815 B | 4881 B |

这些数字证明该组件的容量及角色保真，不是CPU计时、实机速度、完整Construction恢复或融资到账。源码和新软件验证以6文件正常发表`38e024f468f7c6e67c18a0fe8aecf130ec63d399`，owner回执记录origin／remote master一致；没有Runtime、实际资金或新增确认保存日信用。准备、主动审阅、纠错、协调、编测和发布成本缺完整phase原件时均为unknown，不能由两次HTTP或最终通过推算净节省。此有限case发表不完成持续性能目标，后续真实单元另行记录。
