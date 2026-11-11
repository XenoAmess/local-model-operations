# CK3：新实际栈与后到业务 codec 候选的六项 HTTP

本轮输入是新的首 Throwable 栈、完整 source307、Runtime 冻结的新原件，以及随后才落地的 owner 原作两文件，未把旧四项请求重投或倒填为已审候选。实际失败在 ImportRequest 构造器对 producerInput 做 continuity canonical；旧 StrictJson.canonical 已能编码 native wide，实际路径为 change.target.native_body.container_generation。该栈与边界由 Root／Native 提供，不授模型发现信用。

先4项真实独立任务，再2项后到候选窄审，共6 POST／6 HTTP200：5完整stop／1length，0transport／重试／provider拒绝。前波峰4持续42.724384秒，后波峰2持续24.740531秒，未出现6路同在途。首POST至末END417.521079秒，含两波间隔；输入355286／输出9933tokens，有效TTFT8.586–27.504秒，cached tokens未报告。主动准备、净节时与首POST前完整成本未知，不从这个窗口推性能收益。

前4项虽标 SOURCE_SUPPORTED，仍混淆旧编码与后续 ImportRequest canonical、建议与已有v3冲突、漏判transition分支或发明API，未采修复。实际候选codec审命中2800token上限，整件保留、正文未读、不拼接、不续投，属owner输出范围／预算问题。另一项候选审漏看新旧schema hash条件，建议把新outer请求hash改为inner，反会破坏实际请求一致性，已拒。

封包另有owner错误：二进制传输原件被当UTF-8导致本地准备失败，4次missing-SPEC CLI前检均0POST。原二进制字节／SHA保留，改用Runtime已冻结的完整decoded JSON和二进制身份元数据，没有新decoder、替换字符或改写原件。这与6次真实模型请求、语义错误分别记账。

本轮模型修复代码采用0，不放宽parser／Guard，不改旧encode／hash，不造回执或刷新期限。本岗新增JVM／live／账本／业务源码操作0；Java／Native真实最小修复与Runtime采用独立验收，当前HTTP0，不派第7项，主目标仍ACTIVE。

[完整成本、源版本与拒收分级](2026-11-11-ck3-new-stack-business-codec-http.json)。此前切点见[授权冻结原件源审](2026-11-11-ck3-authorized-frozen-p0-http-diagnosis.md)。
