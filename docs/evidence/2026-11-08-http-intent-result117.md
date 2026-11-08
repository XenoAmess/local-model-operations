# Intent精确结果复用：分配改善，墙钟性能未通过（P117）

case_id：`HTTP-JAVA-GUARDED-INTENT-RESULT-REUSE-117`；mode_id：`http-candidate`。本地及实际HTTP／编测UTC日期2026-11-08。本单已正常发表且正确性通过，但只验得累计分配改善：whole median、actor和intent median均变慢，**无墙钟性能通过**。本文0新增HTTP／JVM／业务操作；[全部样本、阶段、错误及原件pin](2026-11-08-http-intent-result117.json)保留，私有导航留执行机器。

private intent已有完整query Obj，仍总是执行DriverJson.encode(query)。只有同一NativeQuote的既有exact result cache存在且Arrays.equals(queryBytes,同quote.original())逐byte成立才复用；getter clone、6.8MB比较和原encode成本都计入。cacheempty／oldsmall／不同原query继续lazy原finalizer，不做结构相等、hash或Economy重编码替代。后续finalized parse／frame／candidate／expected／province／income／pending／canonical body验证、所有真实full CAS／cold读／header／Guard与原命令期限保持。

一次真实模型请求：5份完整源码、源码消息104117个UTF8字节，fixed system/user/user、`qwen38-coder`、max_tokens3000、temperature0、thinking=false、JSON object／SSE/include_usage。01:02:53.796378→01:03:00.373964Z，1POST／1END／0retry，200／stop／DONE／完整JSON；headers2.953233秒、有效TTFT2.9545723秒、总6.5775491秒，reported22282／564、cached未报告、actual peer UNKNOWN。精确算法与边界已由owner给出，不授独立优化发现。

**一个完整literal hunk原样采用，9add／1del**：原片段唯一替换后逐byte等正式Lifecycle49053B／`51cd62bb9d13ee0217d7c00ba28fef3c22113a5257b8b72850e50078c6650d48`。模型的`byte[] finalizedBytes = queryBytes;`冗余initializer也保留，两分支均覆盖它，未用owner清理伪称原样。源码1TU实际exit0／完整8class family／5.546034秒，其余旧绿不重编。冻结caller默认与后到literal采用分列，测试／来源证明不署模型。

首Native准备器因历史helper basename FileNotFound在claim／JVM／BEGIN前拒绝，独立执行owner错误，不是模型／javac RED。owner Test01把throws Exception的quote(true)留在IO-only writer lambda，真实javac RED／0class／0JUnit保持；Test02仅将同构造移lambda外，输入／oracle／断言／selector不变，1新TestTU必要第二编译0／4.4025814秒，同JVM3新方法3P0F0E0skip，actor12.0246114秒／XML suite10.104秒。

新3方法用actual同writer Source.preserve／cold resolveCommand获得真正Loaded，实际3arg intent完整canonical body与private pure-DATA五参cacheempty reference逐byte比较；unequal proof1A／proof2B必须fallback到B，错用A cache会失败。oldsmall／精度词法／clone／current header物理拒绝保持。反射只用于既有pure五参oracle与qualified纯DATA builder，不伪Loaded、expected或Guard issuer，不授Native verifier、canonical action membership或Root权限。

复用同Main03／P114原DATA／EXPECTED／source／绝对CAS，0Main重编／0新PREP／dataset刷新。固定四独立JVM各2warm4measure，全部8warm16measure和11不重叠phase保留；真实variant是Lifecycle完整8class first origin／source hash／ordered CP，其余P116共用21class不变。raw B0B0B1B1仍是原cache lane，外层ABBA映射透明；raw cache=true属于既有P114结果API，不是新intent hit marker。具名124pins只有Lifecycle和$Bound class hash不同，不冒称完整依赖图或Runtime资格。

| 同输入实际报告 | A：P116成功基线 | B：P117 | 当前观察 |
| --- | ---: | ---: | --- |
| whole均值 | 639.4407875 ms | 637.99885 ms | −0.2255%，近乎持平 |
| whole中位数 | 636.862 ms | 640.4039 ms | +0.5561%，更慢 |
| 全部测量范围 | 561.0901–755.5943 ms | 565.9531–728.172 ms | 重叠 |
| 主线程allocated均值 | 945644044 B | 892130767 B | −5.6589%，约53.5MB/call |
| 主线程allocated中位数 | 945644092 B | 892132124 B | 分开保留 |
| intent allocated均值 | 114648223 B | 61135660 B | 分配下降 |
| intent墙钟中位数 | 77.18775 ms | 85.6513 ms | +10.97%，更慢 |
| 完整actor均值 | 10.67553535 s | 10.937727 s | +2.456%，更慢 |

本单是复用既有retained result的累计分配权衡，不把它叫延迟成功或retained heap减少；分配不是heap／RSS／总JVM。保全部慢样本／反向phase／CPU／setup／main-before-output／actor／outer／OS峰值，无filter／forceGC／复跑挑绿，不用噪声解释掉负结果，也不叠加前轮百分比。

ABBA完整窗口47.452576秒，首次生产至末close396.433924秒含checked-exception错误、修正、source审阅和等待；四actor合43.226524699945秒分别记。末01:16:27.648816Z四main均关闭／释放。完整consumer DATA不执行Policy.evaluate／revalidate、Native fresh READ、完整SEM／evidence准入或owning publication，不外推P113公开112秒方法或游戏日。

资格43237B／`33eb979f6a093c4b13e527f9c3fbbf3cca5174e2ce03ffe16b9190f1e5fdcb1b`，raw399381B／`35202ce5a5bc6f599e58ad383cbfaa83ac51bcb53be459aac62f1a74d11a136e`，identity6593B／`d36ab293afbda415f32cca92604436be74ac6659a39386b3c4da50888f82c867`。Root77direct／73unique全匹配，proof534B／`ea7badd24428a98961e63723a57ec9f751bcffe75cb053fd11afb07c9ab6d156`；24raw及具名origin独审112138B／fff2a4fe…、49645B／2a457f87…另存。

业务5files正常发表`dbc61046b0232cb2d882ee6044d9e54be50b07c8`，HEAD／origin／remote一致且发布切点clean。主动准备／审阅／纠错／协调／发布及净owner节省缺phase仍unknown；0新增确认保存日，无有限秒／日或Runtime／Game／GET／P100信用。持续目标active，P118实际后继另记，B2设计／模型准备不授代码／采用／收益，也不设本文为主线门。
