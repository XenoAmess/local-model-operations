# 不可变full结果复用：有限consumer DATA对照（P114）

case_id：`HTTP-JAVA-IMMUTABLE-FULL-RESULT-CACHE-114`；mode_id：`http-candidate`。观察日2026-11-08（Asia/Shanghai），源码HTTP发生于11月7日UTC，软件／测量跨11月7–8日UTC。这里整理既有模型、正确性和完整声明consumer DATA的有限对照，0新增HTTP／JVM／业务操作；[参数、全部24样本和原件pin](2026-11-08-http-immutable-full-result114.json)随案例保存，私有导航留执行机器。

SELECTED full NativeQuote构造时已经得到第一份fixed-codec finalized bytes，Policy同一对象提取时又对完整原件重做finalize。owner明确要求只在该full实例保留已有精确bytes，getter防御clone、Policy单点lazy fallback，不能借decoded Economy quote重编码替代精度／未知数值词法。旧small构造、unselected／过门full保持空sentinel，所有CAS保全／重开／长度SHA、distinct Q2、source／header、args／ActionId／bodySHA与原deadline保持，不加constructor finalizer或跨调用cache。

一次真实请求：7份完整源码、源码消息115576个UTF8字节，fixed system/user/user、`qwen38-coder`、max_tokens6000、temperature0、thinking=false、JSON object、SSE/include_usage。23:36:36.891818→23:36:52.304673Z，1POST／1END／0retry，200／stop／DONE／完整JSON；headers3.5864263秒、有效TTFT3.5878828秒、总15.4117106秒，reported输入25752／输出2045、cached未报告、actual peer UNKNOWN。精确算法已给，是强指导实现，不是模型独立发现热点。

模型核心部分采用，但原稿把old-small也缓存，超出范围；owner使用独立D稿的正确full-only实现，未编原坏稿，不称整稿原样采用。实际2生产TU exit0／16 class／5.1504935秒；新Cache Test1TU exit0／3.9187143秒，只有4新方法实际4P／0F／0E／0skip、5.0055077秒。覆盖fixed输出精度／opaque顺序、139行完整原件、input/getter array防御、不同存活实例隔离、old-small与unselected空cache／lazy fallback。其它旧@Test未重跑。

比较边界是实际factory／compose／提取／同writer physical CAS preserve+load+resolve／distinct固定DATA Q2+sameQuote／实际package Lifecycle.intent与canonical codec，Policy args按声明DATA组装。**没有执行Policy.evaluate／revalidate、fresh Native READ、完整SEM／evidence准入或owning publication**。A复用P113成功的完整SDK+Policy class families，B为P114两叶完整families16，其余有序CP和Main03相同；不是任意旧缓存或当前Runtime对照。

原P113阳性软件plan／receipt仅作DATA来源：large变体以已qualified139行历史替换两段opaque大字符串，small control仅删那些字符串，其余字段保留。Q1为6831978B／`fe413956e14af2487bbec3b900e7ef6f08e653fc405ad5b71466eaa9e2cb9cdd`；Q2为独立固定DATA，不是真READ。原expired command prototype不刷新期限，新未执行args／identity只按精确CAS ref派生。source原件61B，四JVM用完全相同的source与CAS绝对路径；这些路径不公开。

Main02／data01首PREP真实exit1、5.9625245秒：owner错误要求canonical command roundtrip后的small inline仍等于pre-canonical bytes。Main03只改small的legacy oracle与失败Trace finally保留，full CAS逐byte断言不变；旧data01及失败时间保持，原finally缺失的详细Trace不补造。新data02一次成功PREP8.6686718秒后才开始ABBA；它是新的显式cohort，不清空或重试覆盖旧根。两个必要Main源码编译、PREP、纠错与等待另列，不能删除或折入steady-call提速。

固定A0／B0／B1／A1四独立JVM，各2warm＋4measure，全部8warm／16measure保留，无过滤／强制GC／速度assert。每次要求CAS existed-before-preserve、相同source／input／args／command／action／body／result markers及正确cache route；11个不重叠阶段之和与whole一致。首次冷发布、setup、main-before-output、actor／outer、OS峰值独立保留。Python在计时外核具名ledger／head／anchor／lock／input／prototype／payload／commit的stat身份与bytes/SHA在PREP和四JVM前后相同；新每进程software allocation card是明确例外，不称全文件系统相同。

| 同输入实际报告 | A：P113 | B：P114 |
| --- | ---: | ---: |
| whole consumer DATA均值 | 947.99135 ms | 907.3915375 ms |
| whole中位数 | 951.43385 ms | 862.08805 ms |
| 全部测量范围 | 844.4701–1045.9419 ms | 789.7663–1085.3583 ms |
| 主线程allocated均值 | 1284101930 B | 1216951378 B |
| 主线程allocated中位数 | 1284099924 B | 1216949556 B |
| 完整actor均值 | 12.21972205 s | 11.86151175 s |
| main-before-output均值 | 9.81586045 s | 9.5620939 s |
| 未改distinct Q2阶段中位数 | 114.88235 ms | 146.2695 ms |

whole均值下降4.28%、中位数下降9.39%，主线程分配中位数下降5.23%、actor均值下降2.93%，分别报告。范围重叠且样本有限，只是当前DATA点估计；未改Q2反而更慢也完整保留，不凭无证据GC／代码归因解释。主线程累计allocated bytes不是heap／RSS或整个JVM分配，阶段局部改善不等于真实Policy或Native延迟改善。

Root从首实际BEGIN到末CLOSE窗口190.727833秒，四actor合48.1624676秒；Native从更早OPERATOR startedUtc到同一末CLOSE为191.163224秒，两个起点不同，均保留。第一次失败PREP的operator起点到末close为473.568004秒，包含修正／准备／等待；这仍不是完整HTTP开始以来的全部owner成本。末00:13:28.982641Z P114四个进程均已关闭／释放。0 saved days，无有限秒／保存日指标。

资格51499B／`d6fe25b94afbc6d8ff56758006fe87c993713575c651f43b8d04a81f9dd01c14`，全部samples215155B／`83d16824ba878ee759c0d71a376bd2b0f7dda94c31fa8a4cbedbc57e32627c59`，identity6775B／`62458e4b62d81f6887de46e0169f7d551fb1a9b37fd4216e890572a3c2930d8e`；Root原24call复核51499B／`c02ddf0996635f684c66358d828f7c99537fad2f501760157da476e6c0150d03`是另一份文件，不与同尺寸Native资格混淆。

业务7files正常发表`fbb026b6a34491bfdd4da8c69a135f5191c0d45d`，HEAD／origin／remote一致且发布切点clean。主动准备／审阅／纠错／协调／发布和净owner节省缺phase仍unknown，不用HTTP短或最终绿倒推。无Runtime装载、Game／GET／P100或新增确认保存日信用；持续目标active，P115独立结果另记，不以本案例发表作其执行门。
