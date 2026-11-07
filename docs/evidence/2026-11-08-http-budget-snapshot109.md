# 预算snapshot角色：组件改善，完整进程未加速（P109）

case_id：`HTTP-JAVA-BUDGET-SNAPSHOT-PERFORMANCE-109`；mode_id：`http-candidate`。观察日为2026-11-08（Asia/Shanghai），精确请求时间为2026-11-07 UTC。此处只整理已发生的源码候选与软件／测量原件，不新增HTTP、JVM或业务操作；公开元数据见[脱敏摘要](2026-11-08-http-budget-snapshot109.json)。

owner指出public budget反复编解码未消费的大snapshot历史，并给出实际budget消费者和presence／坏形状合同。原codec已有FullJsonTree大limit，当前完整输入本可接收；本单元只投影wrapper.snapshot，**不是64 KiB容量修复**，没有扩大或缩小原codec限制。inputs、四个完整domain ledgers、campaign root与state/head一致检查保持。原snapshot/request仍Java持有，角色不是完整归档或新权威。

唯一源码请求提供5份完整源码、源码消息76120个UTF-8字节，fixed system/user/user、`qwen38-coder`、max_tokens1800、temperature0、thinking=false、JSON object、SSE/include_usage。19:21:53.500748→19:22:06.144719Z，1POST／1END／0retry，200／stop／DONE／完整JSON；headers2.3374152秒、有效内容TTFT2.3682685秒、总12.6437839秒，reported输入17070／输出1710、cached未报告、实际peer为UNKNOWN。任务已给目标角色设计，是强指导实现，不是模型独立发现或能力对照。

模型核心角色语义部分采用；owner复用既有member selector／stream，未采用缺Map／ArrayList imports或冗长整方法替换，不称完整方法原样采用，也没有编跑模型原稿。新增私有budgetSnapshot保paused/map、nested actor ID、native/date/snapshot/public revision、每行war_id以及完整pending值。非法war行仍拒绝，missing/null ID仍unknown，重复ID按行数；pending false／0／[]仍非null，不能转成clear。融资角色没有为此新增pending。新增方法不授冻结Runtime的body-only热替或装载。

必要生产1TU exit0／12 class／5.2765332秒；新Test/main1TU exit0／2 class／4.5571881秒，只有3个新方法实际3P／0F／0E／0skip、7.1487441秒，无本单软件RED。30项既有budget corpus在原snapshot、加未消费139行历史及角色snapshot之间逐项比较typed Request／Policy Result／encode bytes；另验非法war、重复行、pending三态和public budget四domain全文／state head不变。资源37430 B、SHA `bd3aea63baf65c1fcbe36310d629cd3813343ca29e2f3de3b68603db8ec7b338`。30向量和四份domain文档不是额外JUnit方法，也不是实际账本准入、完整Root或保存证明；旧codec／旧case未重跑。

固定四个独立JVM A0／B0／B1／A1，A为已编P108、B为P109，仅Collector classpath前缀不同；CPU1／384MiB／45秒，各2warm+4measure，全部8warm与16measure保留，不删慢样本／强制GC／速度assert。计时为完整public budget wrapper组装、encode、decode和observe；load、oracle/setup、main、process、outer及OS峰值分开保留。

| 同输入报告值 | A：P108 | B：P109 |
| --- | ---: | ---: |
| 组件中位耗时 | 18.22445 ms | 0.2783995 ms |
| 组件均值 | 19.222762625 ms | 0.735387375 ms |
| 全部测量范围 | 16.8624–22.7528 ms | 0.1172–2.489399 ms |
| 主线程分配均值／中位数 | 51992952 B | 28872 B |
| 两个ACTUAL进程窗口合计 | 7.9696502 s | 8.1413520 s |
| 两个outer完整窗口合计 | 9.3364754 s | 9.7467725 s |

组件中位与分配下降，但**完整process和outer窗口没有更快**。两个层次都保留，不能只用组件数字宣布整个进程、HTTP或游戏日加速。主线程allocated bytes不是总进程分配或RSS／heap峰值。

完整wrapper3403002→1064 B。四JVM输入snapshot3402157 B及root各自SHA相同；结果均694 B、SHA `f463be75ab7cb0f5e5a5828f5a0fc8b25f2055bb8e645ba7f39fbb973cf45c24`。这是original-producer软件向量加未消费历史扩展的组件DATA，不冒原完整FinanceCurrent或实际Native查询。末资源19:35:04.792321Z关闭。生产wrapper保留CASH108历史标签，实际CONFIG/source／子进程绑定P109，Test/main标签在BEGIN前已更新；没有改写raw或为标签重跑。

最终资格25772 B／`3e23066e1084a44cd8c5877f5b2c8eef19234ca232dc105ae61e2c4f9f4599c8`，全样本10882 B／`e6d7c219c7d144eaaf18070793f0648c051f447b8976393460c13bb934bd9269`，独立Root复核9090 B／`71d38289d9232f40adf2ec936cec24e7ca7421fba909ff77a77ee654813b82a4`。业务6文件正常发表`c11ac8b5a2f30027fe0d397b7150cecd96184d42`，owner回执记录remote master一致及该发布切点clean；不外推发文时其它工作树状态。

没有Runtime、实际热替、运行决策TTFT或新增确认保存日信用。准备、主动审阅、纠错、协调和发布及净owner节省缺phase原件仍unknown。此有限案例发表不结束持续性能目标，后到真实调用／采用／测量继续分别记录。
