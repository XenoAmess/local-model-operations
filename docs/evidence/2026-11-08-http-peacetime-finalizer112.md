# 和平finalizer：两轮拒收、owner接管与有限binary对照（P112）

case_id：`HTTP-JAVA-PEACETIME-FINALIZER-112`；mode_id：`http-candidate`。观察日2026-11-08（Asia/Shanghai），请求实际发生于2026-11-07 UTC。此处只整理已经发生的源码、验证和发表，0新增HTTP／JVM／Game；[脱敏元数据](2026-11-08-http-peacetime-finalizer112.json)保留两候选、全部样本与原件pin。

旧和平finalizer把starting／ending两份完整snapshot送入原262144 B SDK lane，未消费的大历史使合法无候选来源先因大小拒绝。owner给出完整直接声明、精确13个snapshot字段、hello四键、原顺序及presence／错误父类型合同，要求仅计算副本投影，完整native envelope与持久query不裁。两轮均9份完整源码、源码消息107724个UTF-8字节，fixed system/user/user、`qwen38-coder`、max_tokens5000、temperature0、thinking=false、JSON object、SSE/include_usage；属于强指导任务。

| 真实语义轮 | UTC POST→END | 有效内容TTFT | 总时 | reported输入／输出 | 源审结果 |
| --- | --- | ---: | ---: | ---: | --- |
| 01 | 20:27:08.654429→20:27:19.552695 | 3.3361592 s | 10.8981936 s | 23854／1183 | Value误调Obj API、缺Map import、按allowlist重排原成员，拒收 |
| 02 | 20:28:04.790820→20:28:15.627538 | 0.8151125 s | 10.8366777 s | 24035／1651 | 修类型／import／顺序后仍丢null/scalar父、擅裁完整played_character及hello非Obj值，拒收 |

每轮1POST／1END／0传输重试，均200／stop／DONE／完整JSON，cached未报告、actual peer UNKNOWN；headers分别3.3348228秒和0.8138118秒。两原稿均未编译／运行，代码采用0，由owner接管最小copy-present实现。调用器冻结的`NOT_YET_REVIEWED`／`adopted=false`保留，后到拒收另列，不把最终软件绿追授模型。

最终只临时投影starting／ending的13个present字段；diagnostics为Obj时只选hello，hello为Obj时保四个expected／fallback build键；scalar/null/missing父保原样，expected:null不会变absent触发fallback。played_character、active_wars、player_armies完整保留，成员顺序不变，active_event／pending值保持。原query、完整native_envelope含opaque world/result、PlanningRequest、Complete、read receipts、stableReceipt／SEM和原守卫保持，不扩大codec cap或裁持久query_observation。只授和平finalization／assembly，不授完整Construction quote／action／material或Runtime热替。

owner生产29941 B／`f7cbd02be9a7bc17bf00c408712d79945df99bed81f4747dec3ce1f7c49de4d2`，1TU exit0／22 class／4.4718553秒；新Test/main14422 B／`9562ef119b93c41bb2448dd8a0f12dc8c090321ec0e06cc051dff18388842a5d`，1TU exit0／1 class／5.2698124秒，仅3新方法3P／0F／0E／0skip、5.0974169秒。Test01／02均未BEGIN：owner预审把opaque world的比较改为原固定SDK emission，而非finalizer之前的decimal lexeme；原完整query bytes断言保持。Root另要求main自入口计入setup、warm、全部sample与校验，均在最终Test首次编跑前纠正，无本单实际software RED。

大功能DATA由既有authored peaceful input加同源未消费139行历史构成：原query6805700 B／`63f2bb92a2ecb12ff7629d73ac24ae3552741eb554499297109b3568602fffb3`，旧SDK拒绝，新finalizer／assembly完整742 B输出与原小输入固定codec结果逐byte相同，原query及完整native envelope不变。另验expected键presence／null优先级、错误父类型、flags／schema／episode／request ID拒绝，以及native envelope或消费数组本身过cap仍拒。**该大DATA不进入性能分母**，也不是实际Native查询、真实intent或Runtime资格。

速度对照A仅为具名first-classpath缓存Collector的22份原bytecopy binary，B为本次新编Collector；基线`existing_binary_only=true`，**没有完整旧源码谱系或与当前Runtime等价证明**。复用既有assembly，其余有序classpath、同一Test/main/DATA保持。共同输入198482 B／`78c89b02d505075d21b3c9acfc475e9a8ef3b1c28afb25ba50c1f5efb204971a`在原cap内，共同输出689 B／`017c81c921f6dcf907e316192d27e494e25efa3a1f02c8d1262d24cd66edc9e3`在全部warm/sample固定。

固定A0／B0／B1／A1四独立JVM，CPU1／384 MiB／45秒，各2warm＋4measure，全部8warm／16measure保留；不删慢样本／强制GC／做速度assert。per-call计完整static finalizer含投影与SDK encode/decode，输出canonicalization／校验在计时外；完整setup／main／process／outer与OS峰值回执分别保留。

| 同输入报告值 | A：具名旧binary | B：owner候选 |
| --- | ---: | ---: |
| 组件中位耗时 | 3.7886 ms | 2.83575 ms |
| 组件均值 | 6.0843375 ms | 3.64805025 ms |
| 全部测量范围 | 2.452399–15.8379 ms | 1.353401–7.480001 ms |
| 主线程分配均值 | 1984696 B | 64936 B |
| 两个完整setup合计 | 3.1754384 s | 3.2021271 s |
| 两个完整main合计（写出前） | 3.3759619 s | 3.3797185 s |
| 两个ACTUAL进程合计 | 4.7575663 s | 4.7378597 s |
| 两个outer完整窗口合计 | 6.0660970 s | 6.1626870 s |

组件中位下降约25.15%，主线程分配下降约96.73%，但**完整main与outer没有更快**，进程总时差也不等于组件提速率或端到端业务收益。主线程allocated bytes不是全进程分配／RSS／heap峰值。所有24次实际warm/sample和setup成本均保留，不能用大包old拒/new成功或短子窗冒充速度对照。

末资源20:46:39.667224Z关闭。最终资格26946 B／`eca779cf1622cf23ce44628c4c0b38ee54f35b4c0aac2bcab06bb446fe51cb63`，全样本11362 B／`a8402fee3b3b30116244066e09a6ed4315057e6cc696ab6668f7f16ed1994a25`，Root独核11557 B／`c25eaadd7cd92d3bc5aa55a647ccce339fd5dd73e821afeeba21d85718aa6471`。业务6文件正常发表`f6c2b638c5cf9e729cff378ade663c966b29a080`，HEAD／origin／remote一致；P111独立dirty未混入，不称业务全树clean或P111完整验证已通过。

主动准备、审阅、纠错、协调和发布成本缺phase原件仍unknown，不从HTTP／编译时间反推净owner节省。无HTTP／TTFT、完整规划、Game或新增确认保存日收益；持续性能目标保持active，后到P111／P113真实集成独立记账。
