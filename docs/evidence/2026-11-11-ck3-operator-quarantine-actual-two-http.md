# CK3：OperatorQuarantined 实际源码后到两项 HTTP

本批与此前四项方案分析分开：输入是 owner 后到的 core Source01 完整实际文件、必要 BASE／接口，以及 midlayer Source02 DRAFT 的相关完整文件。两项分别核 operator 指令／CAS／新 append 与归档 replay／独立 codec，以及旧 parent／child ID admission 与同 Game／episode 的 Sway 采集前隔离。没有把首4倒填为已审新实现，也未扩大到尚未齐备的完整安装、Driver、worker 或 cycle 恢复。

2 POST 均 HTTP200／stop／DONE／合法 JSON，峰2持续22.965886秒；首POST至末END23.019071秒。输入156855／输出659 tokens，有效内容 TTFT18.6183684／20.1514983秒，cached tokens未报告；0length／transport／provider拒绝／重试。准备、人工核验及净节时未知，完整请求和成本留原件。

两返回均 PASS_SOURCE_REVIEW、findings为空，只作为本版本静态辅助。第一项泛称 logical correctness，不能超出已给源码授完整 policy／Root 安装证明；第二项称 gate 位于任何 preparation 前，实际原 requireOutsideReadOnlyScope、collectPhysical、body hash 与旧 same-ID 返回都先于新 ID gate。该文字错误已纠正，未据此修改成熟步骤或误报重放。Sway 的独立 predicate 在 collector 前，仍不授安装已完成或真实行为通过。

事后参数核验另发现 owner 封包元数据问题：计划前缀 SHA 取自写盘前字符串，Windows 换行转换后与实际 REQUEST 不同。原文件、计划及请求均保留；已逐文件证明只差换行格式、代码字符与声明完整，补记实际 SHA，不重投、不归模型错误。后续应以 caller 最终读入文本计算前缀身份。

OperatorQuarantined 的结果是 OPERATOR_ABANDONED_UNKNOWN_EFFECT，保留原未知效果、完整 reservation／命令／期限及禁止原 ID 重放，不冒称 NoEffect、Applied、schedulerSuccess 或 SAVE。历史 loaded-issuer 证明缺口不替代 operator 授权来源，也不构成其等待许可门。当前源码版本冻结后若 owner 改动，另标差额，不重写已发请求。

本批0模型代码建议采用／0已证新缺陷；本岗0业务源码、JVM、live或账本操作。当前HTTP0，不为凑数追加同源审阅，Java／Native／Runtime正常推进不等模型绿，主目标仍ACTIVE。

[逐项成本、实际源版本和采用分级](2026-11-11-ck3-operator-quarantine-actual-two-http.json)。此前不同协议切点见[首4源码分析](2026-11-11-ck3-composite-protocol-four-source-http.md)。
