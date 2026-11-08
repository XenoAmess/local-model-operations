# LARGE保存阶段单行复用：原样hunk与有限DATA对照（P115）

case_id：`HTTP-JAVA-LARGE-PRESERVE-REDUNDANT-FACTORY-115`；mode_id：`http-candidate`。本地2026-11-08，实际HTTP／编测UTC同日。这里只整理已发生的源码、正确性与测量原件，0新增HTTP／JVM／业务操作；[原件pin、全部24样本与逻辑映射](2026-11-08-http-large-preserve115.json)可追溯，私有source-index／CAS路径不公开，原P114案例不改写。

完整ObservedRequest的factory先clone owned raw再解码，private pair由该factory产生、original()返回clone。Source.preserve在LARGE分支又调用一次`ObservedRequest.fromFullMaterial(full)`并丢弃结果，重复纯DATA分配；本次只删这一句。old-small构造是decode后clone，存在调用者并发修改窗口，**small原重验逐字保留**；数组长度不变，成功small不能进入LARGE。owner核实际构造／别名／异常顺序证明该窄范围，typed DATA不授来源权限。DriverJson、bounds、sameSession／withSession、物理CAS publish／load、len／SHA／逐byte、header／cold resolve／distinct Q2／Guard／命令期限不改，不新增cache或API。

唯一模型请求给3份完整源码、源码消息41554个UTF8字节，fixed system/user/user、`qwen38-coder`、max_tokens3000、temperature0、thinking=false、JSON object／SSE/include_usage。00:16:16.851522→00:16:21.906688Z，1POST／1END／0retry、200／stop／DONE／完整JSON；headers1.5284599秒、有效TTFT1.5298693秒、总5.055228秒，reported9658／519、cached未报告、actual peer UNKNOWN。任务已指出准确语句和证明边界，是强指导source audit／edit，不授独立热点发现。

**一个literal hunk原样采用**：独立核对old9410B／`026b64538e6b9a6401708b1bc2cd199cc971093a00ff3eb6415db0acf0f6be39`唯一old片段替换后，逐byte等于正式9358B／`8f3cc5b990feca7d0ec1ee0d82e3494b107b42dfd983c65bfff6b336b7af111d`，只有一行差异；不把owner的immutability证明和测试署给模型。冻结caller默认与后到采用另记，不声称整任务原样交付或净owner节省。

必要1生产TU exit0／3 class／4.0177273秒；此前Native prerequisite别名p114_prod与实际phase不符，在claim／JVM／BEGIN前被拒，修执行owner配置后首次编译，0javac RED／0模型失败。新Test1TU exit0／4.8627683秒，只有2新方法同JVM2P0F0E0skip，actor10.1716732秒。覆盖caller/getter数组变更、同writer preserve两次与全文读回、canonical header／缺件／foreign同bytes路径拒绝、恢复原件、small inline／canonical合同及head不变；cold verifier delegate明确为DATA spy，不是Native verifier正向或canonical action membership证明。0旧@Test重跑。

复用P114同一Main03字节、DATA／EXPECTED／Q1／Q2／source及绝对shared-CAS root，0Main重编、0新PREP／dataset刷新；不是零setup或零准备成本。双方均保P114缓存完整SDK+Policy families16，所以Main03内部raw report label仍为cache lane B0／B1。外层逻辑**A0→B0、B0→B0、B1→B1、A1→B1**，真实A/B由OriginalSource完整三class family hash／strict first origin／有序CP区分。raw标签不改写，不从B0/B1臆测优化variant。

固定四个独立JVM各2warm＋4measure，全部8warm／16measure保留。24call均cache=true、CAS existed-before-preserve=true，markers等原EXPECTED；11不重叠阶段和whole一致。实际writer acquire/close、mutable CAS preserve命中核验、physical完整重读、header／frame、distinct固定DATA Q2和实际package intent／canonical仍计入；Policy args是声明DATA适配，**非Policy.evaluate／revalidate、Native fresh READ、完整SEM／evidence准入或owning publication**。具名外部文件身份在前后核验保持，新每进程allocation card明确例外，不称全文件系统相同。

| 同输入实际报告 | A：P114成功基线 | B：P115 |
| --- | ---: | ---: |
| whole墙钟均值 | 913.822675 ms | 705.3617625 ms |
| whole墙钟中位数 | 861.3643 ms | 694.91825 ms |
| 全部测量范围 | 808.8722–1116.6381 ms | 603.2668–835.6193 ms |
| 主线程allocated均值 | 1216925041 B | 1041739137 B |
| 主线程allocated中位数 | 1216926060 B | 1041740136 B |
| preserve阶段墙钟中位数 | 287.222 ms | 147.72655 ms |
| preserve阶段allocated中位数 | 395396252 B | 220210304 B |
| 完整actor均值 | 12.16565385 s | 11.32841445 s |

当前样本whole均值下降22.81%、中位数下降19.32%、主线程分配均值下降14.40%，actor均值下降6.88%，各自分开。全部慢样本／阶段CPU与分配、setup／main-before-output／actor／outer／OS峰值保持，无forcedGC／过滤／绿色复跑。分配是累计主线程bytes，不是heap／RSS／全JVM；有限且重叠样本不作普遍速度或额外阶段因果结论，不把P114与本轮不同cohort百分比相加。

四actor合46.9881366秒；首实际BEGIN00:34:18.141494Z至末CLOSE00:35:08.240640Z为50.099146秒，从更早operator起点的全窗口为50.553755秒。配置纠正、编译、两正确性方法、setup及等待另存，窗口不是完整HTTP开始以来的owner成本，也不是保存日分母。P114失败PREP／原窗口另案保持。

最终资格38145B／`9f943260b7ae30b43639f0e54999ab11e3ce2ebc14f0f3413070993f20839a78`，全部raw392596B／`f0585319d83d71d45491bf6ba0ef34de0dfb235f38b4526e59c5b8bf1f55b891`，身份6593B／`b1d294378ce9ac84986b1a73003c04d466e2e3a8f3731eb16c49827f3c8844af`。Root64／64 direct pins复核688B／`aaadd6848679d8d1eb73b7b01ff02c4415aa126d212bfb9104eee94d1b1a08d6`；全24call独审89958B／`a0dd4742773108a1d3c603c08419216efe15a456c40651284af2d15a66027d3b`。末00:35:08.240640Z四进程均已关闭／释放。

业务5files正常发表`ba7e5888b202b1bd278a57f70defe8c37e58a262`，HEAD／origin／remote一致且发布切点clean，不外推后继状态。主动准备／审阅／纠错／协调／发布和净owner收益缺phase仍unknown。0新增确认保存日，无有限秒／保存日、Runtime／Game／GET／P100信用；P116实际后继另记，不从可行性授代码／采用／收益，持续目标不因本单发表结束。
