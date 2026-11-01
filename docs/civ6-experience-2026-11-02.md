# Civ6 本地模型经验迁移（2026-11-02）

用户要求将 Civ6 的本地模型经验迁入共享仓库。机器 BF-202609141645；原项目截止提交 [76a41d8](https://github.com/XenoAmess/civ6_dev/commit/76a41d8d2c23806a20a4d98aa3ba251d598f054b)，来源是已发表指南、配置、经验和项目脱敏证据。三份完整原文见[精确档案](history/civ6-2026-11-02/README.md)，没有复制原始模型或游戏材料。

以下是 owner 对真实证据的整理；本轮 migrationlessons131 只提供分类参考，没有逐字采用。它把未测的重放事故、类型范围和部分模型贡献写成事实，已拒绝；也不能声称 Civ6 全部代码都是 owner 写的。原文中的历史条件不覆盖共享当前规则。

| 经验 | 原观察与边界 | 可复用做法 |
| --- | --- | --- |
| [实际消费者与 UI 控件名](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-city-purchase-source42-evidence-2026-11-02.json) | 旧代码使用不存在的 PurchaseGoldCheck/PurchaseFaithCheck，原生 XML、事件注册和实机控件均为 ProduceWithGoldCheck/ProduceWithFaithCheck。原生背景购买资格 true、受保护面板资格 false，实际点击只打开空购买页，资金及城市状态不变。127 候选中的正确名字被部分采用，其原始背景写入负例被拒绝。 | 控件查找不报错也可能无效；验证真实调用者、注册名和路径。原生资格、策略拒绝、界面入口和实际副作用分别取证。42 只有333项软件通过，冷启动实机复核仍待完成。 |
| [跨上下文 API 与原生类型](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-government-native38-evidence-2026-11-02.json) | Civ6 UI/Core 的可用 API 和状态视图不同；通知拦截的普通 Lua table 不能代替 hmake NotificationType 的原生 struct。 | 给模型实际上下文的声明与原生类型；软件夹具可调用不证明真实绑定可调用。此条只授 Civ6 观察，不外推全部 Lua 引擎。 |
| [查询命中不等于原对象](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-neutral-gp-native40-evidence-2026-11-02.json) | 原商人 ID 851975 的 FindID 返回另一个完整 ID 983047。新对象的零次数和 individual=-1 不能证明旧商人耗尽。 | 每次用完整身份重新核验查询对象；非 nil 查询与某个字段的零值不是原对象仍在的证明。 |
| [未知动作不能按失败重放](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-gp-intent-native36-evidence-2026-11-02.json) | 正次数伟人的持久化意图在未知结果冷载窗口保持等待；没有凭回调或新回合重发。41 创作意图在 ARMED 冷载分支也保留未知，2577次回调零命令、零操作、零事件。 | HTTP 重试与业务动作恢复分开。持久化 ARMED、核心事件回执、UI 可见新资产是不同证据；未知不凭超时自动重放。此处不是观测到重复执行后的补救，也不是所有故障已通过。 |
| [事件位置与行动者位置](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-creative-second-native41-evidence-2026-11-02.json) | 第二件 Homer 作品时单位在16,6，实际 GreatWorkCreated 载荷城市在15,5；作品落在该城市剧院，而第一件宫殿作品保留。 | 按真实事件字段合同解释坐标，不能用目标城市坐标代替单位位置。 |
| [零次数与类专属语义](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-creative-classes-native41-evidence-2026-11-02.json) | 作家、艺术家、音乐家分别在零运行次数时创作成功；三类各自独立存档分支，不是连续三次同一局，也不证明每类多作品闭环。 | 次数、人物身份、动作事件、新资产和持久状态分别验证；不要用正次数职业的耗尽规则处理不同语义的类型。 |
| [诊断夹具必须可靠收尾](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-creative-classes-native41-evidence-2026-11-02.json) | 126候选混淆 UI GetType 并漏存清理引用，负责人改写诊断：保存原指针、保护执行，先恢复指针和事件观察者再断言。 | 源审测试自身的调用合同及失败收尾，不能把夹具错误记成产品错误。最终通过不追授被拒模型代码。 |
| [完整输出仍需逐项核验](https://github.com/XenoAmess/civ6_dev/blob/76a41d8d2c23806a20a4d98aa3ba251d598f054b/docs/research/baiqi-p6-city-purchase-source42-evidence-2026-11-02.json) | P6截止129次HTTP，124完整、5次length整份丢弃、0传输重试；128候选仍混淆operation/command，129猜测原生玩家ID及测试API。 | stop和JSON合法只证明候选完整性。保留错误归因、采用单位与未知缓存；累计请求不是并发，历史客户端峰13的持续时间未知。 |

## 当前接入与后续

Civ6 以前的候选流程没有接入共享每日维护，不追认历史合规。2026-11-02迁移入口前，实际共享检查复用了同机同用户的成功缓存，核实记录版本1.19.5；缓存记录中的 updated=true 是先前维护结果，本次没有执行升级。OpenCode只用于维护，这轮3个任务的 mode_id 均为 http-candidate。

本轮通过共享 CLI 完成 migration130（适配方案）、migrationlessons131（经验候选）、migrationtests132（验证边界）：3 POST/3 stop/DONE/合法JSON对象，0重试，实际客户端峰3。采用及耗时详见[脱敏记录](evidence/2026-11-02-civ6-migration.json)。候选没有自动执行权限，后续适配实现和测试仍由 owner 完成；测试/正式采用后另加回执，不能提前记成已发布。

下一真实任务是完成 Civ6 薄适配器并验证共享实际请求构造消费者，随后继续42版原生购买入口对照及其它未完成验收。新任务、拒绝或后到验证更新共享 HTTP 案例和此来源链；不为记录重跑旧绿。owner准备、审阅、纠错及发布成本未完整计时，保持null，没有相对收益结论。
