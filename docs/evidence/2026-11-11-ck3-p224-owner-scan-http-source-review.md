# CK3 P224：owner ledger 单次完整扫描的三项源码审阅

使用正式 Git 的完整 BattleRetreatPolicy、Codec、原 whole Test 和32向量资源，三项真实义务同时 POST，均 HTTP200、完整 stop/DONE、合法 JSON，0length／传输错误／重试。峰值3路持续20.864114秒，首POST至末END23.746125秒；有效内容TTFT为10.7569–15.6552秒，输入124518／输出2249tokens，cached tokens未报告。

唯一候选是把有序 immutable ledger 的 stream/filter/toList 换成同序完整 for 扫描、局部计数和唯一行引用。三个响应支持源码级候选、无具体 finding；全序遍历、0或多匹配先拒绝、null后signum与预算比较的原顺序保持，公有直接构造与 BigInteger 子类域不能缩窄。没有早停、索引、缓存、helper 或后续 policy 变更授权。

owner 核原件纠正了覆盖描述：duplicate／missing／null／negative 的真实下标为19／20／21／22，模型写13–16；这不是原测试缺少覆盖。多匹配时临时行引用是否覆盖无关，须先 count!=1 短路；完整遍历是本次合同要求，不是所有唯一性判断的数学必要条件。共享空列表、List.copyOf 复用和 JIT 都限制物理分配推断。

真实调用源是原 Test 的 decode→public assess→encodeDecision，Codec 没有 evaluate。原32向量数不等于实测软件调用次数或 Runtime 热频。两种扫描仍为 O(n)，分配、延迟与实际收益待独立证据。

Java 的15123B owner-original 候选独立推进，本轮0模型代码采用，未重投该候选。完整结果已直接交源码 owner，不作必要增编／原测试前置；本岗新增 JVM／live 操作0，主目标继续 ACTIVE。

[实际成本、源身份与采用分级](2026-11-11-ck3-p224-owner-scan-http-source-review.json)。
