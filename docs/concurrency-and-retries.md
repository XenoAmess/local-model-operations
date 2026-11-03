# 并发、重试与传输证据

并发用于缩短真实工作的排队和衔接空档。任务输入齐全且写权独立时，owner 可直接发出请求，让准备、源审和必要验证与其它请求重叠；不等待中央逐单 ACK、整波审阅或正式发布，也不为达到数字制造任务。

## 调度与计数

每个任务只有一个源码写者、一个唯一输出目录。运营协调记录任务与服务状态，不替代实际 owner。执行者完成或 idle 标签不是 HTTP 在途；对已结束岗位的消息投递，也不能当作请求已经启动。

用户当前明确要求维持 **60个真实未结束HTTP请求的rolling pool**，覆盖历史12–16及24–32目标。owner以完整输入的不同未闭实现、反审或新Test切片持续补位，完成即补；不重投已闭题或绕过配置六次尝试。目标与实际分别报告，不擅自降低目标、切换端点或无限重试。当前共享caller本身仍不提供自动补位、全服务配额或硬预留推理slot；Ops调度模块正在真实源码任务中开发，不能把已发任务写成工具已可用。多个机器不得各自把本机目标当全局成果。

源码 HTTP 与下游编译、重 IO、发布和线上运行的资源约束分开。已点名的小材料读取不应仅因无关编译暂停而被冻结；确有冲突或高优先级任务时，暂停相应未开始阶段，记录具体范围。依据真实开始、结束和释放调整，不沿用过期暂停，也不按预计结束时刻自行开始受限工作。

计数以实际尝试为单位：

- 用机器、端点、输出目录、task ID、attempt 共同标识请求。一次语义纠正可以是新逻辑任务；一次连接重试是同任务的新 attempt。
- 完整尝试的客户端在途区间为半开区间 `[POST_BEGIN, ATTEMPT_END)`。准备、排队等编译、已结束但未读结果、监控 GET、普通 Git 操作均不算模型请求。
- 同 task 在另一目录的 END，不能关闭本目录的请求；新 attempt 也不能让旧中断 attempt 再次计活。同一时刻结束与开始的两个半开区间不算交叠。
- 只有 POST 而无 END 的日志先列为“未闭合”，不永久计作当前推理。核实调用者已经消失时，保留未知终止时刻及观察上界，另记中断，不能补造 END。

固定统计窗口须公布起止时间、时区、端点、机器集合、目录覆盖和截止点。窗口内 POST 数与 END 数可能不同，因为请求跨越窗口边界；它们不是采用率。计算峰值时包含窗口开始前已在途的请求，并将区间裁切到统计窗口。

至少分别报告：

| 指标 | 含义 |
| --- | --- |
| 当前已核在途 / 未闭合未知项 | 当前真实活性与缺终态的诊断分别列出 |
| 客户端区间峰值及持续时间 | 峰值出现过多久，不能仅报最高一个数 |
| 达到指定阈值的总时长 | 说明目标是否持续达到 |
| 窗口平均在途 | 窗口内并发曲线面积除以完整窗口时长，含空闲时段 |
| 服务 running / waiting / KV | 另带采样时间，不能从客户端区间推导 |
| POST / END / 重试 / 截断 | 传输运营事实，仍需逐候选审阅 |

不同机器的 UTC 时钟偏差也应保留；单机单调时钟耗时不能直接当跨机器时间轴。事件扫描和后续 metrics GET 不是原子快照。迟登记的外目录、迟读的 END 或索引缺漏，另存同截止点的重建与依据，不改旧快照。

历史实测例：`qwen38-coder` 在指定新端点于 2026-10-31 07:39:58.637575–07:40:02.177609 UTC 出现客户端峰 14，持续 3.540034 秒；对应十分钟平均在途 2.0054，至少 12 在途共 9.803132 秒。07:40:27 的独立服务采样为 running 10 / waiting 0。它支持“出现过短峰”，不能写成持续 12–16、服务推理峰 14 或服务容量上限。[公开原指南，第88–92行](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L88-L92)

## 重试分类

当前策略读取 [共享配置](../config/executor.json)：最多 **6次总尝试**，因此最多5次退避，基准依次为10、20、40、60、60秒，抖动为±20%。这不是“首次加6次重试”。最后一次失败直接结束，不再取第六个退避项。

| 实际情况 | 当前调用器处理 |
| --- | --- |
| HTTP 429 / 502 / 503 / 504 | 按配置退避后重发完整请求 |
| 连接拒绝、重置、超时、缺 DONE 或 finish 等不完整响应 | 作为传输失败，保留本次原件后按配置重试 |
| 无LF的EOF尾行出现 JSON / UTF-8 解码错误 | 视为不完整流，整次重发；不补尾、不拼候选 |
| 完整LF行中的畸形 SSE JSON | 当前实现记录失败，不自动重试 |
| 完整协议结束但 `finish_reason=length` | 输出截断失败，不走传输重试 |
| `stop` 但拼出的候选不是合法 JSON | 候选格式失败，不走传输重试 |
| 本地证据文件打开、写入、flush、close 或日志输出失败 | 立即停止，不当作网络错误重发；尽力保留仍可写的失败证据，无法落盘则保留诊断并以非0退出 |
| 永久请求、schema 或认证错误 | 先修请求或配置，不盲重发 |
| 可解析候选中的 API、类型或业务语义错误 | owner 源审与有限语义纠正，另记任务与采用等级 |

配置中的 transport 错误名称描述预期类别；当前 Python 实现使用具体异常类型捕获，网络调用仍保留较宽的 `URLError` / `OSError` 分支。本地证据操作先归为独立的`LocalEvidenceIOError`，不能仅凭同属`OSError`而重发请求。这不是逐字符串匹配错误名称的通用策略引擎。更改错误分类需要明确的新版本和验证，不能在报表里静默改归因。

每次瞬时重试发送完整、未改变的请求。失败 SSE 和已收到的片段只作原件保管，不能与下一次内容拼接，也不能因为开头看似正确就采用截断源码。内容层纠正则使用本轮完整当前源码、准确诊断和一种活动输出合同；“same API”不能替代再次提供声明。

### 2026-11-01：一次真实服务断流后的自动恢复

一次真实源码审阅使用本仓库调用器、Windows / Python3.13.2、`qwen38-coder`、三消息和4,500输出 tokens 上限。首个尝试07:37:39.648003→07:38:10.510465 UTC，HTTP200但部分 SSE 后连接 reset10054，没有 finish、DONE 或usage，整段候选未采用。调用器记录10.875069秒自动退避，第二个尝试07:38:21.388563→07:38:42.614660得到stop、DONE和reported usage91,867 + 2,474，cached为null。它是一项逻辑任务的两次 HTTP 尝试，没有手工另发任务、fallback或内容拼接；另一独立角色的请求未混入这次重试。

同请求证据由两个 POST 事件指向同一 task / REQUEST，以及[已发表调用器控制流](https://github.com/XenoAmess/local-model-operations/blob/aa12e525d5f6cb842cae71dabe33071a91794933/scripts/call.py#L104-L147)中循环外建立的不可变 body、每次 `data=body` 共同支持；这不是逐次 wire-body 抓包或派发时执行体鉴证，也不证明服务端只生成过一次。此例补充离线 mock 与先前的单次 SSE 成功，只支持这一真实连接重置路径，不能扩成所有错误、六次尝试边界或缓存加速结论。后续源审仅部分流程观察可用，源码采用0；传输恢复不授整体审计、软件、性能或业务完成。[脱敏实证](evidence/2026-11-01-windows-transient-retry.json)与[来源限制](source-origins.md)保留实际字段。

## SSE、时限与停止

当前解析器将每条 `data:` 行视为一个 JSON chunk，不提供多行 SSE event 的重组。TCP 层分割 UTF-8 已有本地 mock 覆盖，不能据此声称任意多行 SSE 格式都已支持。

默认 `read_seconds=180` 传给底层 socket 调用，`total_seconds=900` 在收到响应行后检查。后者不是独立 watchdog 或严格900秒总墙钟截止，也不覆盖整个多次重试任务；阻塞读取仍受读取超时约束。

停止文件在每次 POST 前检查，也在失败后进入退避前检查。如果退避睡眠期间才出现停止文件，下次 POST 前才会检测；不承诺立即打断睡眠或正在进行的 HTTP。停止或重启调用器不执行任何下游业务恢复。

证据目录以原子、持久 `DISPATCH.claim` 防止并行覆盖，已有事件目录也拒绝复用。调用器不会自动恢复旧目录或删除 claim；需要重新处理仍未完成的真实任务时，用新唯一目录保留前次失败链。

## 延迟与使用量

记录 headers 延迟、首个非空 `content` delta 的 TTFT、总耗时及实际报告的 prompt / completion / total tokens。headers、首字节或 reasoning delta 的时间均不能冒充内容 TTFT。

usage 可能在无有效 content 的 chunk 中出现，即使 `choices` 非空也应保存。cached 字段缺失或为 null 时保持未知；明确报告0与未报告不同。不从耗时、输入字节数、context宣告或相邻请求推算缓存命中、内部 thinking 模式或吞吐收益。

每次保留实际 REQUEST、BEGIN/END、headers、原始SSE、候选正文、usage与错误，再由 owner 另记源审、编译、行为和采用。机器证据默认留在执行环境；公开仓库发布规则、脱敏摘要与固定版本反链，不上传原始私有请求或业务账本。


## 同步连接 reset 的有限调查

多个角色接近同一UTC报10054时，先按各自EVENTS核实际POST、headers/content、END、finish/DONE和retry.scope，区分传输异常与宿主协作模型capacity/turn中断。客户端END时间不是上游包时间；少量近似固定间隔只是相关线索，不能命名服务timer、模型故障、重启或OOM根因。

只读现有配置和已知维护来源，明确覆盖范围。当前每日检查是任务入口缓存，不是周期唤醒器；这不排除别处的OS、代理或远端服务任务。已有明确只读health/metrics路由才作有界、带时间的采样；health200不证明历史健康/uptime，未报告的running/waiting/uptime保持UNKNOWN。不猜路由、不发示例chat、不重放业务、不因猜测调大超时或重启服务。根因未证时保UNKNOWN，源owner继续真实工作。见[三对同步reset有限记录](evidence/2026-11-03-http-synchronized-resets-limited-attribution.json)。


## 新任务的显式高并发时限配置

[config/source-high-concurrency.json](../config/source-high-concurrency.json)是当前共享executor的独立完整投影，仅将新源码任务的`read_seconds`设为600、`total_seconds`设为2400。新任务显式`--config`选择并记录实际配置SHA；后续executor改变时另行审阅投影，不动态继承。旧frozen/在途请求及活跃Runtime副本不改，不为耗尽重试的同题改参数重开。它不添加priority/id_slot、端点fallback或新重试。

600秒仍是socket读取超时；2400秒仍在收到SSE行后检查，并非严格独立watchdog，也不是整个六attempt任务总墙钟。较长有界等待不证明服务有容量或能满足业务deadline。业务优先pending准入、服务priority scheduling与硬保留执行slot是不同能力，未核实际部署policy时不盲传priority。

[首个60窗口及源码工具任务](evidence/2026-11-03-http-rolling60-first-window.json)仅证明迟登记重建的短窗口；后见metrics与客户端未闭合数分别标时，不将无headers直接判为后端排队。


## 显式客户端路由

Python默认urllib可从当前环境代理表选择路由；局域网地址未进入bypass时，不能先验认定请求直达模型服务。新[direct源码profile](../config/source-high-concurrency-direct.json)仅为显式后继请求禁用该独立opener的代理并拒绝redirect，不更换endpoint，不修改全局环境/urllib opener或旧任务。历史environment模式保留；request/RESULT附加字段兼容原消费者，fixed3/SSE/finish/语法/采用/重试条件不变。

代理选择、真实TCPpeer、服务可达与应用响应是分别的证据。默认代理存在加上无响应仅是具体可核线索；新直连无headers时同样保UNKNOWN，不从异时请求做严谨AB或归唯一根因。服务/Runtime实际caller仍由各owner控制，不为源码路由修复重发旧业务。


### 后续用户纠正：共享默认必须DIRECT

上段历史opt-in切点已被用户新指令覆盖。当前无network配置也默认独立DIRECT opener到可信base_url的exacthost，拒绝所有redirect；`executor.json`和`source-high-concurrency.json`明示DIRECT/currenthost，独立direct profile保留。只有显式`proxy_mode=environment`才继承环境代理。不硬编码路由目的地、不改endpoint、不修改全局环境；旧frozen原件/在途进程与Runtime副本不回写或自动迁移。首次DIRECT实际TCP peer已见指定LAN端点，但两请求仍600秒无headers超时，因此默认接入修复和服务响应问题继续分别记录。
