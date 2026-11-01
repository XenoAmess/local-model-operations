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

## 已知边界与操作方法

- 输入由owner封装，模型无法仅凭一个路径自行取得未提供的声明；检查真实REQUEST，包含祖接口、callee、MAX值、消费者和名义返回类型。输入缺口与齐全输入下的模型错误分别归因。
- 完整stop不保证实现完整。复杂帧/ABI、跨回调当前状态和多对象作用域仍需owner逐项核对，反复语义错误后接管，保留原始失败。
- 大上下文接收成功不证明理解覆盖、最大有效上下文或缓存效果；别名不是已核实权重版本。实际参数未转发时，不记成该参数实验。
- 普通caller不执行assistant/tool循环，`tool_calls`终态不能作为完整源码候选；其工具能力不能从OpenCode闭环继承。
- 修正轮更新真实源码和完整合同。只采用完整目标单位，不拼length/reset半流，不因HTTP重试重放业务动作。详见[并发与重试](concurrency-and-retries.md)。

## 客户端保障与生成能力分开

共享caller已增加本地证据I/O分类：RAW预开失败不调用网络，也不记POST_BEGIN；写入/flush/close及输出失败不当成网络重试，503/不完整SSE仍保留重试。`post_invoked`只表示进入网络调用，不证明服务端收到。

这项改动有4个新增离线方法的分期验证，是[OpenCode案例OC-LOCALIO-001](capability-opencode.md)产物经owner修正后的客户端能力，不能计为普通HTTP模型的代码生成成功。[采用/验证](evidence/2026-11-01-caller-local-evidence-delivery.json)、[发布版本](https://github.com/XenoAmess/local-model-operations/commit/761ef26d8dab26cc08442457040a1025f1448571)。有限Windows离线测试不证明所有本地I/O故障或其它平台。

## 继续跟踪的问题

| 下一项真实任务触发条件 | 要补的证据 |
| --- | --- |
| 新的依赖闭合窄方法/消费者需要修复 | 记录封包、审阅、owner改动与必要验证成本；区分首轮原样和反馈后的采用。 |
| 新的复杂状态或整图审阅任务 | 按原始合同独立冻结必要见证，记录输入是否齐全、具体错误及接管范围；不复跑已完成的反例。 |
| caller、服务、模型或执行平台变化 | 只在实际新需求中核参数、SSE、重试和错误分类，版本变化不自动继承旧结论。 |
| 有适当的真实模式比较机会 | 按共同条件记录交付、owner成本、失败和顺序/答案暴露；没有对照不填相对效率或净节省。 |

每个触发点追加case_id和证据链接，完成可审阅单元及时推送main；没有真实任务时保持待验证状态，交接给下一owner继续维护。
