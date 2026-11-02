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

## 后到回执：Civ6 薄适配已发表

此前“待实现/待验证”冻结点保留。后到版本 [b2cf367](https://github.com/XenoAmess/civ6_dev/commit/b2cf36744fa9ed7de89cc220f2d19f89002f3492)已推送并核对远端：AGENTS强制共享入口，连接策略来自共享实时配置，Civ6只保留业务system覆盖和来源；薄适配直接调用canonical CLI，每日维护在真实HTTP之前。14项适配边界检查0.492秒通过，含真实prepare_request消费与真实CLI模拟维护失败先于dispatch；8项旧内部传输测试退役，未冒充新增游戏测试。241条本地链接及UTF-8/LF、28需求/40用例追溯通过。

实际新入口又完成HTTP-CIV6-ADAPTER-REVIEW133：一POST，7.649869秒、stop/DONE/JSON对象。模型错误地指称未维护、忽略共享原子claim，并否定明确业务提示覆盖；三项意见均拒绝，代码采用0。实际CLI链与测试已否定其论断，没有照候选添加重复维护。新4项请求累计4完整/0重试，峰仍3；不是4个独立代码交付，也没有效率收益证明。[后到脱敏回执](evidence/2026-11-02-civ6-adapter-delivery.json)给出精确源、哈希、结果与未知成本。下一步回到尚未完成的42版游戏入口对照，历史原始HTTP脚本不再直接复用。

## 后到：127正确控件方向的原生回执

2026-11-02，Civ6 [44f7c7c](https://github.com/XenoAmess/civ6_dev/commit/44f7c7c7b5be6cc9548a4b6c62bb9ac855ef5ce8)发表42版冷启动同档对照，精确模组源码76a41d8、63文件逐字相等。127候选的真实控件名方向已由owner核原生XML、实际消费者和旧41失败后采用；新42两个控件均禁用，实际点击各0开页事件，购买面板不出现，资源、人口、生产队列进度及市民焦点不变。原生资格true／受保护界面false，未调用原始背景写入。

这是原窄采用范围的后到游戏证据，不回填迁移时的“42待验”，也不授127整份方案或全40项通过。原观察器在断言前移除，Steam仍离线，当前未测完整快捷键及其他领袖原生对照。[脱敏原生证据](https://github.com/XenoAmess/civ6_dev/blob/44f7c7c7b5be6cc9548a4b6c62bb9ac855ef5ce8/docs/research/baiqi-p6-city-purchase-native42-evidence-2026-11-02.json)。下一真实问题转为剩余城市／军队输入边界与特殊文职覆盖；没有为本次记录额外发模型请求。

## 后到：真实输入边界与输入工具反例

2026-11-02新增134–136三个尚未完成的原生快捷键、城市入口与宗教缺口任务，3 POST、1完整stop/JSON对象、2 length整份丢弃、0传输重试。峰3维持43.843055秒。134/136截断稿没有读作语义候选，不追授最终owner实现；135仅既有控件分类分析参考，原生观察与清理由owner编写。成本未完整计时，保持null。

owner已发表两个窄原生结果：军队Delete打开原生确认，文职建造者同键拒绝，取消后两对象不变；9个城市生产/买地/市民/焦点控件物理点击均0写入，而真实城市详情可打开关闭。首次PyDirectInput Delete没有产生原生action事件，不能据此判军队被禁；查本机库mapping1235和扩展键处理后，改发Windows扩展Delete并独立观察action15才取证。所有代理先还原再断言。精确源、输入、截断、指纹、后态与仍未验证范围见[脱敏摘要](evidence/2026-11-02-civ6-input-acceptance.json)。下一问题是宗教文职接口与自动化，不把这两个通过样本扩大成全40项。

## 2026-11-02：Civ6传教士窄方法137–142

6个真实未完成任务，经共享每日维护缓存后发出6 POST，全部200/stop/DONE/JSON对象、0重试；实际峰2，两个独立峰值区间与持续时间见[逐项回执](evidence/2026-11-02-civ6-missionary-delivery.json)。137目标谓词和139严格journal校验整方法原样采用；138 Core快照加owner必需成员检查后部分采用。140整方法因跨上下文API、调用位置、身份与基线错误整拒，owner全部重写；141测试在Controller前预先Prepare，实际没有触发待验的授权后突变，owner换为内部hook并核调用次数。142只读诊断需修正虚构leader getter及nil guard后部分采用，实机读取通过。

正式source43已[发布](https://github.com/XenoAmess/civ6_dev/commit/437030cfdf93a85e64b1c3955c45dab91b3e00fd)，354项软件检查通过；不授全功能实机或模型自主实现。原生42的真实手动传播暴露强制托管缺口；43当前测试创建的新传教士有4移动力且原生允许传播，但IsReadyToMovefalse，2410次真实回调0后台命令，先保存重载区分Debug初始化。此冻结点自动传播、手动guard、未知意图冷重启仍待验证。原始候选与后到游戏结果分列，准备/纠错/净节省未知；OpenCode本轮只维护，未新增native生成。下一项继续实际43效果，不重跑已绿软件配额。

## 2026-11-02：Civ6待命阻断与窄请求143–146

4个真实任务分别是普通领袖对照准备、传播回合时序诊断、未知能力安全待命helper、资格回调后身份再检测试。4个不相交POST区间，3完整stop/JSON对象、1 length1600整弃、0传输重试，峰1；不是4并发。143仅在owner补早期slot guard后准备，原生尚未运行。144只有既有idle门控思路部分参考，未测Busy flags不能推出已确认竞态；145竟禁止任务要求保留的persistent pending，完整helper拒绝；146截断稿未采用、不拼接。owner曾在确认终态前误打开raw，保留流程错误，不作语义能力定性。

owner实测43自主传播有效但次回合被受托单位需命令阻断；最终44安全SKIP待命、回执保留与busy停发由owner实现，9新边界方法加全套363PASS/60.310s。owner首测夹具重名覆盖老项目待机测试，已按原HEAD恢复，独立命名新夹具；过宽busy门还曾阻止既有事实读回，修正后保留读回和pending计时。拒绝/截断与owner修正成本分别记录，44原生仍待验，不能从软件绿追授模型或行动费用通过。[逐请求与正式采用回执](evidence/2026-11-02-civ6-standby-delivery.json)。OpenCode本轮仅每日维护缓存，0native生成；净收益与模式比较未知。
