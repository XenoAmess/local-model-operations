# Publication 刷新热点：两项完整源审阅

从真实 batch8 尾段的发布与重规划记录提出两个新义务：核调用闭包和 current proposal 边界；寻找同调用纯重复及有意义反例。输入为 19 个完整当前源码文件、Core.withBorrowed 完整成员与明确标为片段的安装调用上下文、冻结 END 和 24 条结构化行。新 P0 原件另保，没有混进这轮性能输入，也未作为现场恢复的前置。

先前“预算不足后一直空等”的假设由 owner 在 HTTP 前否定：实际 batch 上限 1800 秒，下一 Life 的预留门 900 秒，延期时仍余 867.0764901 秒；Controller 已立即 End，worker 已有一次全新 batch 规则。两个 Life 已实际执行，no INTENT 只指下一条延期命令。C17 后态观察时间与真正 SETTLE 分开；最后 completion RETURN 到 batch end 只有 0.5604531 秒，不能把六分钟尾段归为延期后的空等。

四个独立 planning scope 分别为 113.9542234／94.1328891／93.4922231／66.48544 秒，各 3／2／2／2 个 work pass；多次 READ／domain 发布后要求 current proposal。每个 scope 内 policy／phase 是 inclusive，不能重复相加成 self CPU 或收益。最终业务 HTTP 为不同的 62367B 请求、TTFT 2.466 秒／总耗时 3.291 秒，不与本轮源码审阅的长前缀作速度对比。真实 Native revision 变化不能仅据 Published 标签归因于 READ 提交。

| 任务 | 输入／输出 tokens | 有效 TTFT（秒） | 总耗时（秒） | 终态与采用 |
| --- | ---: | ---: | ---: | --- |
| 01 | 145477／667 | 36.389889 | 42.898677 | 200 / stop / DONE / VALID；0代码采用 |
| 02 | 145496／787 | 37.476121 | 43.745892 | 200 / stop / DONE / VALID；0代码采用 |

首 POST 2026-11-11T22:36:27.216473+00:00，末 END 2026-11-11T22:37:10.962489+00:00；峰 2 连续 42.898707 秒，完整波次 43.746016 秒。总输入 290973、输出 1454；cached tokens 均 null，0 length／transport／retry。

01 返回 FACTUAL_MAP，大体调用方向可作辅助；但它声称 PreparedSelection 为空且 readPublication 已存在时仍须调用 downstream.afterPlanning。实际 RootReadPublicationCompletion 186–189 直接返回该 Published，只有没有 READ publication 才委托 downstream。该反例拒收，输出的 ~1050／~150 等估计行号不作实际定位。具体 domain publisher 身份、每次 Native receiver 变化原因以及九次 pass 是否全可省仍未证明。

02 返回 CANDIDATE，整份拒收。原 GovernancePlanCompletion.beforeModel 的 changed 分支只在 switch 中调用一次 afterPlanning；Root 对同请求 Published／Blocked 已有缓存。模型声称消除的第二次调用不存在，新稿反在 Unchanged 时新增一次调用，并将静态 PlanningDisposition 变量或方法返回值直接作为 SelectionDisposition 返回，类型不兼容。未应用、未编译，不记 compiler RED；四条回归建议建立在错误重复调用假设上，不当作已执行测试或既有覆盖缺口。

干净 main fetch／ff-only 同步到 0044c52，变更仅其它消费者文档；规范、config、caller 哈希不变，复用当日本机 OpenCode 1.19.5 成功缓存。固定三消息、共享 DIRECT、temperature=0、thinking=false、预算 2400／3000；所有实际 REQUEST 已核。最新已持业务日志是本机空窗切点，不能证明全服务队列为空；研究仅小并行两项，无凑数第三项。首发后完整收尾，无重投。

0 模型代码／新优化采用，0 本岗编测／生产源码／业务 Git／Game／Native live／账本动作。保持 fresh proposal、同 writer／Session／Actor／source／frame／epoch、READ 原件与 Driver CAS，不跨轮缓存 PreparedSelection、不造伪 proposal 或合并越过变更 head 的发布。来源不足记 NOT_PROVEN，不新增准入审计门；无秒数收益或 LOOP／SAVE 结论。

[逐请求参数、成本、指纹与分级](2026-11-12-ck3-publication-refresh-two-source-http.json)。源码、请求、响应和游戏材料只留执行机器，未公开。
