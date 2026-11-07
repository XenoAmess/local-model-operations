# 完整规划归档：模型部分采用与逐阶段集成证据（P111）

case_id：`HTTP-JAVA-FINANCE-FULL-PLANNING-ARCHIVE-111`；mode_id：`http-candidate`。观察日2026-11-08（Asia/Shanghai），请求实际发生于2026-11-07 UTC。此处只整理既有源码、错误与软件原件，0新增HTTP／JVM／Game；[脱敏元数据](2026-11-08-http-finance-full-plan111.json)保留15个实际阶段及各自回执。

旧Finance quote v2把完整PlanningRequest嵌入1 MiB manifest，无法承载带大历史的合法全文。新v3仅当完整PlanningWire编码本身超过1 MiB时改用`planning_request_ref`，全文通过同一held writer已有FullMaterial CAS保存，实际重开读回并核长度／SHA／每一byte；既有上限仍64 MiB，PlanningWire的256 MiB能力不授更大归档。小请求保原v2且不增加CAS材料，别的字段导致manifest过门仍按原规则拒绝，不catch失败升级格式。

manifest自身仍限1 MiB，原ordinary材料lane不改；v2／v3各自严格字段集、显式文本schema、同一版本dispatcher与全文loader供verify／originalRequest使用，每次需要时实际重开FullMaterial，不凭reference metadata、缓存或ordinary lane fallback冒充读取。旧v2 SCHEMA／FIELDS／quoteObject／quoteBytes及decimal／cap合同保持。全文source／head／Session／SEM／四read／owning decoder／六份document的原件检查不裁；P110角色只在核验后供SDK计算。新格式只影响后继quote，不改写原命令、hash、回执或UNKNOWN。

两轮均9份完整源码、源码消息145062个UTF-8字节，fixed system/user/user、`qwen38-coder`、max_tokens6000、temperature0、thinking=false、JSON object、SSE/include_usage。owner已给两reader／writer、实际FullMaterial声明与精确格式设计；返工又逐项指出缺口，是强指导实现。

| 真实语义轮 | UTC POST→END | 有效内容TTFT | 总时 | reported输入／输出 | 后到源审 |
| --- | --- | ---: | ---: | ---: | --- |
| 01 | 20:06:28.937036→20:06:40.889271 | 4.189712 s | 11.9522039 s | 31593／1311 | 写ref却未接通v3字段集、manifest writer及两reader版本分派，拒收 |
| 02 | 20:08:41.104085→20:08:58.848363 | 0.963776 s | 17.7443027 s | 31485／2952 | 版本／共享全文loader／实际读回核心部分采用；owner修括号、保留旧helper并收窄装配 |

每轮1POST／1END／0传输重试，均200／stop／DONE／完整JSON；headers分别4.1884176秒和0.9416905秒，cached未报告、actual peer UNKNOWN。两原始候选均未编跑，不把owner Test的后继失败算模型javac失败；调用器冻结默认与后到partial决定分别保留。

业务Archive32472 B／`3e626327bb264ac9fde4638b025b20a74e4d512eb1f7d5c03a959c527357f6c2`只编1TU／4 class，未重编P110 Collector。实际公共链使用真实软件writer、collector、read coordinator、continuity与archive对象，在自有临时目录内导入七领域并生产四个Guarded reads；Archive要求的六领域含child-default marriage单列。checkpoint明确为软件标记，0 Native action writes，不是SAVE、当前Game或真实Root权限。

| 实际阶段 | 必要编译秒 | JUnit进程秒 | 真实结果／归因 |
| --- | ---: | ---: | --- |
| Archive生产1TU | 5.3175682 | — | exit0／4 class |
| 两个既有public fixture首次编译 | 11.9714544 | — | exit0／39 class，无旧测试执行 |
| Test02 | 7.1663984 | — | owner checked-IOException编译RED，0 class／0 JUnit |
| Test03 | 6.0415469 | 4.3027088 | 1P／0F／2E；Native runner漏显式JNA tmpdir，codec新方法通过 |
| JNA04仅两error方法 | — | 5.0805418 | 0P／0F／2E；owner fixture误传StrictJson不支持的预算 |
| Test05 | 6.3726446 | 38.0679968 | 0P／2F／0E；实测first-CP旧缓存拒绝合法faction0 |
| diagnostic06仅small | 6.2648904 | 22.2921655 | 0P／1F／0E；精确诊断旧缓存／当前源码差异 |
| 当前已发表CandidateCodec必要1TU | 3.6971659 | — | exit0／1 class，后继FullJsonTree源码实际已不同 |
| Test07 | 6.4868049 | 63.1965108 | small 1P，large 1E；原capture freshness真实超期1.9739644秒 |
| Test08仅large | 6.3734819 | 42.1415376 | exit0／4 test class，1P／0F／0E／0skip |

所有错误保留。首次源01未BEGIN；只有1个新Test TU，共六次必要变源编译，首RED／五次green，不是六个新Test。最终三个unique方法分别来自Test03 codec 1P、Test07 small v2 1P、Test08 large v3 1P，**不是同JVM 3P**；已经通过的方法没有再跑。最终4个test class含test-only ArchiveWork，不算新增业务生产类。

旧缓存缺当前NativeFactionId合同；没有把合法0改成非零或放宽policy。具名P090十二源码比较为十一份原record/current一致、一份当前CandidateCodec后继改变；只必要增编该1TU。九个被消费的P090同源family加具名NativeCharacterId source/method谱系，共10 family／77 class按原字节复制，未重编十二旧绿或未用的GiftOutcome family。Root独核partial导航的202个具名file pins与后到final的56个pins。该窄依赖来源不授整图或Runtime等价。

Test07在large归档断言与打印之后因外层physical capture超期仍是error，不能追认为通过。Test08仅把大只读冷／负例归档重放移到capture正常关闭之后，仍用同held writer；真实current→gift→bind保留在原capture内。原25秒窗口、command／read期限规则与值以及生产Guard／freshness均未改，所有冷读／负例保持；未冷启真实writer。

最终large完整PlanningWire为1060851 B／`96e5502c07617103fb4debc7a05169111878d3ce624ecec8ec70c83f4f43009a`，manifest13737 B，**manifest SHA未报告，保持null**。未知成员顺序和1.00／-0.0词法的完整原byte在FullMaterial回读／重解码后保持。实际bind→verify→originalRequest、重建Archive对象冷读、严格full lane及无full lane拒绝、未知／缺／null／非文本／混合schema、超64 MiB引用、缺件／错SHA／错误全文和foreign alias等具名负例通过。大小只是功能资格，全文仍另存，manifest缩小不是存储压缩或速度改善。

末large actor42.1415376秒、outer42.8581214秒、控制台runner40.409秒、XML suite40.165秒／testcase40.134秒分别记录；20:59:20.715767Z资源实际关闭。旧partial30114 B／`717442f12b1c3e24b61199ad3b6938b46e9f4411f6c2ea8070e1e9af9dfc4301`仍保留large=false的历史。原final17694 B／`19752cf5fddd64e6736f00449ab2b72f32b5677a0b3b076f1e48b24a2e01f80a`把完整PlanningWire SHA误名为manifest SHA，原件不改；更正02为18384 B／`d622728027ecdc0683e8c32da9ae43e970021de7d41e32fa32d41b89d61324f2`，metadata勘误950 B／`b10202b9215923e9cb9cdb9226ece2b193591b617ce49e37d166996531d9ffe1`。稳定源码附录4606 B／`5814f716e8ffdf3a70a2c45cd7359c36e705f9dfd3e0c635984a99ffee5aa45d`将随开发自然变化的旧formal路径指向字节相同的external Test03／07／08原件；这些更正均0新JVM。

业务6文件正常发表`fbc8cafb59977735ee13d3021409c1f14daa9eab`，HEAD／origin／remote一致且发布切点clean；后到纯文档`ef9c87a122a22b68dbf965d66ef84cab6c4f7d1d`更正runner／XML时间标签并引用02，不amend历史或重跑软件。准备、主动审阅、纠错、协调与发布成本缺phase仍unknown，不把HTTP或多轮编验总时冒成净owner节省。未做性能对照、Runtime装载、Game／GET或新增确认保存日验收；持续目标active，P113等真实后继独立推进。
