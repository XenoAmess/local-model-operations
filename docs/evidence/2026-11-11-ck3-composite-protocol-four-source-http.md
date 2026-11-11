# CK3：新终态协议首批四项源码 HTTP

本批是在用户明确恢复新协议工作后，对完整正式 Git 源、source307 快照、原方案及 Runtime 冻结全链材料做的四项独立分析：settlement-null 前的专用验证、独立 codec 路由、历史 sourceproof 缺口、domain／worker 续行。正式 Git 与 source307 存在实际不同，磁盘快照不授历史装载证明；请求没有尚未落地的新实现。

4 POST 均 HTTP200／stop／DONE／合法 JSON，峰4持续54.153677秒；首POST至末END61.486561秒。输入351163／输出5739 tokens，有效内容 TTFT16.500–42.593秒，cached tokens 未报告。0length／transport／provider拒绝／重试；完整成本保留，主动准备、人工审阅及净节时未知。

模型复述了一些已给合同，但未形成可采用代码或新缺陷证明。第一项误称 settlement-null 跳过所有 Guard，实际 composite Guard 已在前回放；第二项建议改旧普通编码分支，违反独立 codec 与旧算法冻结边界，并假设当前 helper 已认识未来 type。第三项把 latest projection 想成能抹掉曾有 child，实际 lookup 从完整 historical 按 ID 查找；历史 issuer 不足仍只支持拒绝 NoDispatch／NoEffect。第四项建议只改 Outcome 就不用改 controller，不足以证明 domain／worker 续行，也不能产生 schedulerSuccess。

请求发出后方案转向 OperatorQuarantined：这是保留 UNKNOWN 效果的 operator 授权终态，不是 NoEffect 证明。首4没有该新实现，不能追认已审；历史 memory 证明缺口不充当 operator 授权来源的门。保留原 UNKNOWN、reservation、期限及禁止原 ID 重放的边界；事故记录的后续处置仅由相应 owner 执行，本岗未删除或修改任何记录。

本批模型代码采用0，本岗业务源码／JVM／live／账本操作0。已有合同提示不授模型独立发现信用，HTTP 完整不等于语义正确或采用。当前在途0，按完整新源和真实未闭义务再决定后继任务，不维持配额，主目标仍 ACTIVE。

[实际请求成本、版本与逐项分级](2026-11-11-ck3-composite-protocol-four-source-http.json)。此前实际栈诊断见[新栈与业务 codec 记录](2026-11-11-ck3-new-stack-business-codec-http.md)。
