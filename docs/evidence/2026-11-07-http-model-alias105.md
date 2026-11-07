# HTTP 候选：ROOT与完整WAR历史别名的顺序保真（P105）

case_id：`HTTP-JAVA-MODEL-HISTORY-ALIAS-105`；mode_id：`http-candidate`。以下均为2026-11-07 UTC。本案是P104以外另一项真实模型输入修复，目标是两个历史别名的inverse保真；不是P104重试，没有为记录案例增加HTTP。请求消费P104修正源，实际HTTP与P104编测收尾、发表交错，不能把P105请求时间推后到P104正式发表之后。原始请求、源码、响应和编测材料留执行机器，公开元数据见[脱敏摘要](2026-11-07-http-model-alias105.json)。

owner已指出：ROOT去掉两处revision stamp后的facts，以及完整WAR数组，原来按对象结构相等归入同一别名；结构比较忽略成员顺序，可能把有序A／B／A错误还原为A／A／A。任务明确指定同调用局部字典、每个当前体只做一次固定编码、原索引角色和64 MiB预算，还给出ROOT refs应为0／1／0及完整WAR行还原形状。这是有算法设计与预期暴露的实现，不是模型独立发现或推导。任务同时给出family实际输入先经排序codec的既有调用链结论；不可达的私有helper乱序反例没有据此扩成family修改。

实际提供4份完整源码，稳定源码消息为104631个UTF-8字节；REQUEST为system/user/user、`qwen38-coder`、max_tokens4500、temperature0、thinking=false、JSON object、SSE/include_usage。一轮1 POST／1 END／0传输重试，14:35:40.259706→14:35:54.619928，HTTP200／stop／DONE／完整JSON。headers3.2559977秒、有效内容TTFT3.2574418秒、总14.3602321秒分别保留；reported输入23056、输出1985、cached tokens未报告、实际socket peer为UNKNOWN。没有第二轮，也没有OpenCode原生工具生成。

模型交付ROOT局部字典及private helper传参、完整WAR局部字典，并用固定编码每次建立当前值的key。owner保留这些核心代码，将两个“编码字节经UTF-8解码为字符串”的key表达式改为已有Base64精确字节key。这是owner选择的保守接线，不记为已证的模型业务缺陷或UTF-8反例。

采用范围已作机械对比：模型的ROOT字典setup／call修改块，在最终源码的LF投影中逐字出现一次；两个helper整块没有原样采用。对实际REQUEST中的原源应用三个模型edit，再仅替换上述两个key表达式，与最终源码LF投影整件相等。这里明确区分一个完整有限hunk采用与两个helper部分采用，不称整份原样、完整方法原样或按行数计算采用率。原始caller终态的“未审／adopted=false”保留，后到owner partial单列，不回写原件。

最终生产源86681 B，SHA-256 `057f6749c1070f9ca022ddff30550076ef8828137b375ed8038b369350952483`。只改局部字典和既有私有helper；private descriptor新增Map参数，不能据“没有新增字段或类型”声称已验证仅方法体热替。family、原schema、碰撞处理、技术字段移除、stamp和原P104谓词均保持。

必要软件实际闭合：只编译改动的Selector 1 TU，exit0／4 class／6.1407942秒；新Test 1 TU，exit0／1 class／3.5679268秒，三个新inverse方法实际3P／0F／0E／0skip，3.5978985秒。ROOT refs、完整WAR原历史位置的逆还原、占用别名名时的原fallback、原输入及数字token等只按该有限DATA范围授信。

私有helper改为三参后，源审发现一个既有Oracle夹具反射仍取两参；owner仅同步适配器、保留原断言。该实际改动的existing Test另编1 TU，exit0／1 class／4.2502457秒，只执行受影响的一例，实际1P／0F／0E／0skip，3.2926611秒。两个JUnit进程分别为3 new与1 affected existing，不能写4 new或旧方法RUN0；其它旧／P104方法均未重跑。最终14:50:05.598401资源全闭。反射适配在源审时同步，没有先跑一次旧case RED。

执行器owner的CONFIG摘要参数抄错被原runner在JVM／资源槽／BEGIN之前拒绝；具名metadata保留当时值，随后使用未变CONFIG的正确参数。它属于参数准备错误，不是模型失败、javac RED、HTTP重试或业务执行；不把owner补充metadata当原始compiler stderr。上述成功属于owner key接线后的最终组合，未编跑模型原稿。

14:53:39.8955533Z业务owner发表回执确认commit `0a8878ce9566a2c835bb8a1cd4e5cd8792a88e4a`、remote master一致和clean切点，接续P104正式基线。该回执已只读核对，源码和必要新／受影响DATA已发表；Runtime采用、实际热替及新增确认保存日仍没有信用。

准备、审阅、纠错、协调、测试与发布没有完整独立phase原件时均为unknown；14.3602321秒HTTP不代表人工成本或节省。下一真实任务继续核确实可达的别名消费者和inverse，不为已闭题再请求模型，也不从一个部分采用案例推永久能力或模式优劣。当前记录不授实际运行采用、热替、端到端速度或新增确认保存日。
