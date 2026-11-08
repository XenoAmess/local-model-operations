# 精确融资wrapper：部分采用、accepted-set纠正与完整DATA成本（P116）

case_id：`HTTP-JAVA-EXACT-FINANCING-HEADER-116`；mode_id：`http-candidate`。本地及实际HTTP／编测UTC日期2026-11-08。本文整理既有模型与有限软件／DATA对照，0新增HTTP／JVM／业务操作；[全部样本、错误、阶段与原件pin](2026-11-08-http-financing-header116.json)可追溯，私有source-index／CAS路径留执行机器。

ObservedRequest full factory在同一owned FullJsonTree上派生精确单字段financing wrapper，只保byte[]并防御clone，不留JsonNode或接受public任意raw／typed／header三元组。null融资是present wrapper-null，区别于old-small/no-cache／overflow；保数字token、strings、order。仅LARGE Source.preserve可lazy解析小wrapper，否则走原fullparse。small、实际same Session／FullMaterial publish+load／lenSHA／每byte、cold独立重解析／header／Guard／source／命令期限保持，cache不授来源权限。

一次真实请求：源码消息58760个UTF8字节、fixed system/user/user、`qwen38-coder`、max_tokens5000、temperature0、thinking=false、JSON object／SSE/include_usage；200／stop／DONE／完整JSON、1POST／0retry。有效TTFT1.9834396秒，总16.3057455秒，reported13594／2442、cached未报告、actual peer UNKNOWN。owner给精确算法与先前热点，是强指导实现，不授独立性能发现。

核心partial采用；owner拒绝宽catch(Exception)，修正把Value/Nil赋给Obj的静态类型错误及JsonNodeFactory缺import，改用已有StrictJson.object／Value及私有owned byte[]，原坏稿未编。最初任务与owner production01让optional派生encode只用64MiB，未考虑合法raw字符串的编码膨胀，**此accepted-set缺口归owner初始设计，不归模型budget错误**。source审查后production02仅将派生encode改用现有256MiB lease，不扩大raw/parse64MiB、retention262144B、command1MiB或全局限额，不catch语义／原件错误。

实际near反例：raw67108863B，含literal UTF8 emoji使派生wrapper67150800B，而SDK normalized25931B；正确full factory接受、cache=false，过retention后保原fallback。它没有授67MB manifest成功，旧command门仍在。near独立CPU1／1024MiB／90s JVM实际1P、5.5578267秒；OS峰值working set1090727936B／pagefile1153990656B属于该child生命周期，不是Java heap。该大case不进普通ABBA分母。

| 有限软件阶段 | 实际结果 |
| --- | --- |
| production01 | 两叶2TU首次green，5class／4.752528秒 |
| production02 | 仅变更Codec必要1TU；Source不重编，最终完整target5class |
| Test01 | owner漏static obj fixture import，真实javac RED／0class／0JUnit |
| Test02 | 3P0F1E，deep40误经既有NativeEffects→EffectJson32域 |
| Test03仅原failed方法 | 同deep40改为实际Source64 preserve／coldresolve／header域，1P，未改Native32或重跑其它三绿 |
| Test03独立new near方法 | 1P，raw／wrapper／cachefalse边界如上 |

最终是**5个unique方法跨3个JUnit JVM保留通过，不是同JVM5P**。生产3次必要TU执行／2独立源路径；同一新Test三次变源编译，首RED及原1E保持。深40只授Source64 DATA，不授深40 command／Native准入；custody verifier spy不授Native正向或canonicalAction membership。两次Native准备器metadata键／路径错误均在BEGIN／JVM前，单独留件，不算模型或编译RED。

测量复用原Main03字节和P114原DATA／EXPECTED／同source61B与绝对CAS root，0Main重编／0新PREP／dataset刷新。仍固定A0／B0／B1／A1四独立JVM、各2warm4measure，全部8warm16measure保留。逻辑顺序透明映射raw B0／B0／B1／B1，原report不改；真正variant按完整Codec2+Source3五class first origin／hash／ordered CP区分。内部cache=true是共用P114精确结果API lane，不是每call新header均retained的证明。全部output／args／body／source markers等原EXPECTED，whole等11个不重叠阶段之和。

| 同输入实际报告 | A：P115成功基线 | B：P116 |
| --- | ---: | ---: |
| whole DATA均值 | 730.0337375 ms | 631.3798 ms |
| whole中位数 | 722.61945 ms | 622.43395 ms |
| 全部测量范围 | 624.1953–844.9462 ms | 565.0922–716.3436 ms |
| 主线程allocated均值 | 1041765402 B | 945644769 B |
| 主线程allocated中位数 | 1041763556 B | 945644780 B |
| 完整actor均值 | 11.2068362 s | 10.53680915 s |

当前样本whole均值下降13.51%、中位下降13.86%、主线程分配均值下降9.23%、actor均值下降5.98%，分别记账。B preserve中位86.4378ms／124024624B，但construct额外30064B、cold resolve额外26652B、distinct Q2额外30064B，以及overflow临时派生encode均计入；不只摘缓存hit，也不把所有wall变化归单一phase。范围重叠、样本有限，不作普遍速度或额外因果推断，分配不是heap／RSS／总JVM。

ABBA窗口47.112489秒；从首次生产实际开始到末CLOSE为739.117687秒，包含原RED、1E、accepted-set评审、编测与等待，二者不是净owner主动成本。near独立资源／耗时保留但不并入普通cohort。末01:02:36.845659Z四main实际关闭／释放。完整consumer DATA包括真实factory／CAS物理重读／distinct固定Q2／包内intent与canonical，**不执行Policy.evaluate／revalidate、fresh Native READ、完整SEM／evidence准入或owning publication**，不外推实机保存日。

最终资格67246B／`c4e58eaa32a9657089a21aff08de5b5e0f6e3d101d727ec6f1a0d983c223af7c`，raw395511B／`a26e5f9c8b0148f633fe6d4327d6b92173ad8c71b2b36c079ab69b19776ad300`，identity6593B／`0fc52656dffe8e8daca604a0ff066af7f81bbe3009b109cb05c139be0e64499b`。Root145 direct pins／131 unique路径全匹配，复核478B／`70da01c1828d6b658bb295ba867284037131e60aec66ee67877f00350aa35f13`；24call与具名origin独核另有原件，不是全依赖图／Runtime证明。

业务6files正常发表`1a85e42f76c5d002fac406546a6d4923ded8c135`，HEAD／origin／remote一致、发布切点clean。主动准备／审阅／纠错／协调／发布与净owner节省缺phase仍unknown；0新增确认保存日，无有限秒／日、Runtime／Game／GET／P100信用。持续目标active，P117实际后继独立记账，不以文档作为执行门。
