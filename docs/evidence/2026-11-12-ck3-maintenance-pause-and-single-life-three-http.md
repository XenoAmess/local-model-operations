# CK3：独立维护 pause 与单 Life 退役的三项 HTTP

本批输入为当前完整 transport／ManagedGameSession／attachment 调用组、失败与 custody 实现、Life／reconciliation 及现有 operator 协议相关源码，以及已冻结原件。新维护入口尚未落地到本批输入，因此三个结果都是 source proposal／分析，不是对后来实际实现的审阅。Root 后到的 Life 非 POLLED 结算边界与单动作退役问题在首个 task3 前缀中加入，未重投。

3 POST 均 HTTP200／stop／DONE／合法 JSON，峰3持续48.037333秒；首POST至末END55.196058秒。输入293348／输出4244 tokens，有效内容 TTFT16.5606008–39.1174605秒，cached tokens未报告；0length／transport／provider拒绝／retry。共享 main 已快进到81b08d8，仅文档变化，规范及配置不变；复用本机当日1.19.5成功维护缓存。准备、人工核对及净节时未知。

第一项识别现有 ordinary 权限不能直接代用，只给新的独立 owner-bound 权限接口提案；没有实现、完整 durability 设计或采用。第二项虽列出五个回归场景，却把 SubmissionPermit 的 AtomicBoolean 称为 durable gate，并建议借新 SubmissionPermit，违反独立 operator authority 边界。该类型本来明确为 in-memory／never serializable。其零写叙述还漏了原条件 !writeReturned；响应阶段的 TransferFailure 不证明之前没写。原 outbound 保存完整拟发送包，也不证明部分写时全包已送达，重启后内存 map 的 custody 不能凭文字补回。整份安全／持久性结论拒收，五标题不算已实现或已通过测试。

第三项又从冻结子 UNKNOWN 推出永远不能结算，漏掉 coordinator 先同 ID 协调子动作，以及 Life.observe 最先检查 child 是否仍 settled 的顺序。它还把允许未来新 Life ID 当成 policy 缺陷，建议封整个 Life 域，违背本任务只退役原单动作和 reserved IDs 的目标。这些结论均拒绝。维护 pause 本身不授原 sentinel TRIGGERED 或合法原 cancel 结算条件，这个边界由 Root 事前给定，不授模型发现信用。

已有独立 state／receipt 路由、原 ID 禁重放与明确新 scope／exact-operation verifier 是可继续核验的结构义务，不是模型已完成修复。原 request 的 scope 为 optional-sway-episode，不能改旧常量或忽略 scope 冒作 Life；必须明确兼容新业务路线。最终 LifeAdvanceRootReplay 正文未加入本批 task3，其实现行为保持 NOT_PROVEN；模型对此的猜测不计已证缺陷，输入闭合限制与其它齐全源码下的错误分账。

模型代码采用0，新增已证缺陷采用0，本岗业务源码／JVM／Game／Native live／账本操作0。原 Life 的 ACK／UNKNOWN／observed、ARM、期限和旧 ID 保留，不授 target／SAVE／新 credits。完整新入口若后到，只对其新版本和未闭义务另审，不倒填此3项已审过，不凑并发或把模型作为现场前置。

[完整成本、源版本、输入限制和逐项分级](2026-11-12-ck3-maintenance-pause-and-single-life-three-http.json)。
