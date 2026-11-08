# Readback比较试验：软件通过，延迟变差，最终拒收（P123）

case_id：HTTP-JAVA-READBACK-CONTENT-COMPARE-REJECTED-123；mode_id：http-candidate。**最终not_adopted_after_negative_latency，原源码已恢复；不是保留的allocation优化。** [全部24样本、阶段、格式与采用时序](2026-11-08-http-readback-rejected123.json)保留，私有导航只留执行机器。

强owner精确窄任务：仅把preserve第二次Arrays.equals(full,reopened.bytes())换既有reopened.contentEquals(full)。首句fresh physical loadFullMaterial→exact(reference,reopened.bytes())长度/SHA clone逐byte不变且仍在先，原require失败消息保持。RawJson final/owned bytes和full本地稳定引用，无新API/字段/类型、hash/Guard/来源许可；物理I/O/custody/CAS/header/caps/cold/full/small一律保持，不把约124MB preserve全阶段都称被省。

3完整源26122B，实际消息301/26986/2620B；max1500/temperature0/thinkingfalse/JSON/SSE/include_usage。primary attempt.started03:17:56.406120Z与POST_BEGIN03:17:56.406799Z分列，END03:17:59.978319Z；headers1.1794947s、有效TTFT1.1805411s、total3.5716317s，reported6515/358、cachednull/peerUNKNOWN。1POST/0retry/200stop/DONE/完整JSON，强指导不授独立发现。

输出有格式偏差：要求object含edits数组，却是单顶层path/old/new/explanation/risks。首owner extractor按edits取值KeyError，发生在candidate写入前/0JVM；随后仅投影原唯一hunk、无代码改写或第二HTTP。code anchor1/1，literal1add/1del后逐byte等试验源并reverse恢复旧源；这只授代码hunk试验采用，不是完整格式合规或最终生产采用。

历史formal Ready adopted=true记录当时试验源，后到Root最终not-adopted分列。1SourceTU首次0/3class/4.8839481s，无新class/RawJson或其它SDK/Main重编；唯一受影响旧large custody/caller mutation/cold missing/corrupt-original方法1P0F0E0skip，actor12.7500616s/XMLsuite9.816s/case9.772s，0TestTU/newunique0。不新建镜像比较测试，也不以这些绿补授延迟。

复用同Main03/原DATA02/warmphysicalCAS/source/EXPECTED/currentP122B20+oldSource3，0PREP/刷新/P121替代。四独立JVM各2warm4measure，全部8warm16measure/11phase/CP完整family/firstorigin保留；外ABBA与raw B0B0B1B1映射透明，cachetrue不是新比较route计数。

| 当前有限DATA观察 | A：原Source | B：试验Source | 结果 |
| --- | ---: | ---: | --- |
| whole均值 | 762.602800 ms | 857.4797125 ms | +12.4412%，变慢 |
| whole中位数 | 766.5117 ms | 861.0573 ms | +12.3345%，变慢 |
| 主线程allocated均值 | 704496019 B | 697691649 B | −0.965849% |
| preserve allocated均值 | 124026940 B | 117194940 B | 少6832000B，与一次clone相符 |
| 完整actor均值 | 13.75948440 s | 14.68833950 s | 变慢 |

| 四进程measured均值 | A0 | B0 | B1 | A1 |
| --- | ---: | ---: | ---: | ---: |
| whole ms | 762.46405 | 788.7744 | 926.185025 | 762.74155 |

两A均值稳定、两B均慢且actor反向，Root判不足1%的分配下降不支持当前延迟目标而拒收。保全部慢点/反向phase/CPU/setup/load/main/classinit/JIT/GC/actor/outer/OSpeak，不归唯一因果、不删点、不复跑挑绿、不叠加前轮百分比；allocation是mainthread累计分配，非heap/RSS/retained内存。

完整ABBA63.136461s；首prod→末close188.324067s含编测/正确性/准备与等待，四actor合56.89564779982902s另保，末03:26:40.782503Z四main closed/heldfalse。所有原encode/readback/exact/physical成本未跳过。

时序分账：03:28:17.557030Z Native先写allocation_only_retained=true（914B/7eaa7f747a0a2dcc4fa424c02e641e2c895c73f401502f06d89cc8da33cb5e41），原件不改。03:29:33.470165Z Root正式not-adopted（3522B/7cdb6210f89548e93c3c06b5214a01e741da3185d08010c38a211505a3fd5444），当时source恢复观察仍false/9559B候选；不能倒称已经恢复。

03:30:17.684770Z独立后到观察才确认原Source9567B/ab1083f2d2d4b3486e901758f423cade7ea331aeae98ad6ced5dbf53af26ff79恢复（1389B/346a…），Root03:30:28独审706B/a96ae689c9bae05d9e156debea9f14c98d286e2ff4ab9e1dcede404c6b4d0444证同HEAD。0恢复JVM/compile/Test；effective baseline回P122B20+oldSource3（51409B/7256cf0d76ed7a2df157ca0563fdef5286bd795a363ea62a7ded008cf0a6c3ba），P123 candidatebaseline/classes只保反例，非当前。

软件资格40055B/4d38576847646fbea3c356e6f6e43c8bcd22a767008aee5c2754ad1b323c5f47和allraw394409B/2800e4c06cdafaa587ebe8724c296138b3b5742898be16fd2bf593e44f8c10b1保持；Root67direct/66unique全match，proof526B/6475be91cc160ad725b5d05cd81e2b3c0a46dcfe38ab61cae3c6382533691be7。软件成功、格式偏差、性能负结果、最终拒收和源码恢复互不追认。

业务cf504f73406aada03317f354dc90571287cd911e正常发表且HEAD/origin/lsremote一致/发布切点clean，仅负结果3docs，生产候选不在commit；PUBLISHED1270B/23c9685ba879eb33fcdd65440f80f604c69a3653ebf05cbed3487554346657a6。不外推后继树状态；owner主动准备/审阅/格式处理/协调/净节省缺phase仍null。

0文档新增HTTP/JVM/业务源写入，0Runtime/Native/SEM/owningpub/Game/P100/新保存日或性能目标信用。持续goal active，P124无模型不造case，P125独立，不设本文为主线执行门。
