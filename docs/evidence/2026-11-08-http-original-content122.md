# original内容比较：literal采用、metadata勘误与完整DATA分布（P122）

case_id：HTTP-JAVA-ORIGINAL-CONTENT-COMPARE-122；mode_id：http-candidate。[全部24样本、阶段、采用和原件pin](2026-11-08-http-original-content122.json)保留，私有来源索引留执行机器。软件和固定DATA实际已闭，业务已正常发表；这里只记录有限DATA分布。

只增NativeQuote.originalContentEquals(byte[] expected)布尔DATA方法，用Arrays.equals(expected, private original)避开一个只为比较而做的original() getter clone；原getter继续clone给其它caller。expected仍逻辑左侧，null仍false，不保留caller array、不暴露原件、不加缓存/新字段/校验或source权，也不承诺外部mutable probe的新原子快照。

唯一intent调用点保持DriverJson.encode在先、cachedQuote.isPresent()短路、逐byte比较、cache赋值和lazy原finalizer fallback；oldsmall/cacheempty不调用新比较。所有public B2/private pair/P120 token/构造器/finance、下游proof/candidate/expected/income/cash/body及真实CAS/header/cold/Guard/hash/旧deadline保持，不假定DriverJson与FullTree对任意opaque值同编码。

强owner已给精确两处算法，3完整源72818B含只读RawJson比较先例；实际三消息UTF8为301/73664/3448B，max2500/temperature0/thinkingfalse/JSON/SSE/include_usage。primary attempt.started03:02:20.596461Z与POST_BEGIN03:02:20.597082Z分列，END03:02:26.858860Z；headers2.2185431s、有效TTFT2.2199283s、total6.261943s，reported15755/654、cachednull、peerUNKNOWN。1POST/0retry/200stop/DONE/JSONvalid不等采用。

两edit原anchor均1匹配，直接替换逐byte等candidate与正式源，reverse恢复全部原bytes；literal5add/1del、owner代码修正0。来源/owner边界证明不署模型独立发现；冻结caller adoptedfalse/NOT_YET_REVIEWED为当时字段，后到literal采用另记。

实际生产仅2TU/20class=NativeQuote outer12+Lifecycle8，无新class，首次exit0/19.5094797s。原ACTUAL source_tu_count沿模板错写3；原件不改，独立metadata_errata按真实javac两token/CONFIG/两SourceFile和12+8输出证2，0额外JVM；metadata_mislabel1与compiler/JUniterror0、gate拒绝0分开，不写所有metadata无错。

只重验受影响既有P117 fullLoaded exact canonical intent和mismatched raw/proof fallback两meaningful方法，同JVM2P0F0E0skip、actor19.3261638s/XMLsuite15.824s；case12.943/2.847s分列。原Test复用0编译/newunique0，未新建只镜像Arrays.equals的测试或重跑不受影响旧绿。

固定同Main03/原P114 DATA02/warmCAS/source/Q1/Q2/EXPECTED，0Main/Test/PREP重编或刷新；P121三pass不替本cohort。四独立JVM各2warm4measure，8warm16measure和11phase全保；外ABBA与raw B0B0B1B1透明，真variant按两目标完整20class/family/firstorigin/orderedCP，公用SDK/carrier/token保持，cachetrue不是新比较命中计数。Root184具名pin与51direct/48unique全match，11个物理文件/旧cards保持、四新card分列。

| 全部当前测量数据 | A | B | 观察 |
| --- | ---: | ---: | --- |
| whole均值 | 783.496675 ms | 678.252425 ms | −13.432635% |
| whole中位数 | 745.26925 ms | 661.02810 ms | −11.30345% |
| 主线程allocated均值 | 711341801 B | 704523144 B | −0.95856% |
| intent allocated均值 | 61135112 B | 54316456 B | 少6818656B，符合一次clone |
| 完整actor均值 | 13.33278225 s | 12.68614640 s | 仅有限cohort |

| 真实四个进程测量均值 | A0 | B0 | B1 | A1 |
| --- | ---: | ---: | ---: | ---: |
| whole ms | 679.4587 | 710.83795 | 645.6669 | 887.53465 |

**B0比A0更慢，A1保留1087.9297/967.3439ms两个慢样本。** A范围629.88–1087.9297ms/B563.2345–822.1759ms重叠，次序/进程分布显著；不能把汇总13.43%墙钟差因果归于不足1%的whole allocation减少。保所有warm/慢点/反向phase/CPU/setup/load/main/classinit/JIT/GC/actor/outer/OSpeak，无filter/forceGC/额外重跑或P121后pass替换，不叠加前轮百分比。allocation为mainthread累计分配，不是heap/RSS或retained内存。

ABBA完整58.073156s；首生产→末close385.398892s含编译/受影响验证/准备/审阅/等待，四actor合52.03785730013624s另保。末03:12:45.906651Z全部closed/heldfalse。全部queryencode/memcmp/clonegetter/真实physical流程成本均保，不授persistentworker/Policy/NativeREAD/SEM/owningpub/Runtime/fullpublicchain或保存日性能。

资格36297B/730bacb43e2ed0c00ed941372b499346d9eacf8f125840f5601f6f6e59d62de7；allraw417057B/7c1af7b64d5ee144f95c6b694ba4fea1e8c95c0e988b0af4b292c66cf9012f47；identity6593B/ce7ca0bc31b2f86e3037bfdd47b8f11f2eb468bd35b4b3e09e7218b7c2b341d3。Root source/count勘误/affected/24raw/named/physical独审各有pin，历史原件不改。

业务5files正常发表9c4786aff3ad7205532c778d83269bc44f020bc1，HEAD/origin/lsremote一致；PUBLISHED2035B/fd8f8fade805165657b3d0e62d96559be1bb950f0f6d06ab31cfb3c5fbcc0e82。发表切点另有Root授权P123单源dirty，已排除于本5files，不称当时全树clean，也不外推后继状态。owner主动准备/审阅/纠错/协调/净节省缺phase仍null；0文档新增HTTP/JVM/业务源写入、0Runtime/Game/P100/新保存日信用，持续goal active。P121无HTTP不造模型case，病例不是P123或其它后继执行门。
