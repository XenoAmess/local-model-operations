# Prior-Life 历史闭包与独立 generation20 取消两项审阅

两项真实 P0 源审分别读取 owner 的 Source17 历史闭包新稿、Source16 独立取消完整两 TU 与旧 generation14 BASE／patch，重叠进行，不作 Java／Native／Runtime 的门。它们不是 publication 任务重投，也没有让模型重放原 Life 或执行取消。

| 任务 | 输入／输出 tokens | 有效 TTFT（秒） | 总耗时（秒） | 终态 |
| --- | ---: | ---: | ---: | --- |
| 01 | 104176／1373 | 28.930482 | 38.554914 | 200 / stop / DONE / VALID |
| 02 | 124634／254 | 28.930209 | 30.993966 | 200 / stop / DONE / VALID |

首 POST 2026-11-11T22:56:46.317723+00:00，末 END 2026-11-11T22:57:24.872724+00:00；峰 2 连续 30.993975 秒，完整波次 38.555001 秒。总输入228810、输出1627；0length／transport／retry。

所有请求均首尝试 200／stop／DONE／合法 JSON；模型候选完整与源码正确、软件通过、正式采用、实机结果分别记录。服务未报告 cached tokens，保持 null；socket peer 保持 UNKNOWN。

01 返回 FINDINGS，两条均不采用。第一条假定旧授权 material 丢失便称历史重放源码缺陷，建议捕获 IOException 或改成 require 失败。当前及 BASE capture 已明确 preserve authorizationBytes；这不等于本岗实查旧27物理 CAS。若必要原件缺失，应保留失败和原 I/O 原因，不能把未持原件说成合法旁路或源码修复。模型自己也把该实际 material 是否存在列为 NOT_PROVEN。

第二条要求把严格 command.source() 相等放宽成逻辑 operation／部分 build 字段，违背同一 original source 的明确合同。ActionCommand／G2Source 完整声明未进这次前缀，是 owner 输入限界，不能倒填模型已读。owner 后读实际 G2Source(machineId, observedAtUtc, exactBuild, sourceRef)，确认需保严格值相等；不因类型名猜测或假设跨 build 合法而放松。Source17 仅单个插入块的文本逆差由 owner 独立核，不授模型实现信用。

02 返回 NO_CONCRETE_FINDING，仅为辅助。其 not_proven 把冻结 parent486 误叫 generation14，应为本次 generation20；旧14 BASE 是对照源码。它没有证明 HELLO 当前能力、取消成功、旧 Life 已结算或现场健康。

请求中的 486／485 是冻结 UNKNOWN 切点。审阅在途时 owner 后到报告原 resume487 已 APPLIED、parent488 仍 UNKNOWN，以及独立 cancel20 成功／IDLE／paused143／event12；这是独立现场结果，不是模型准入或采用。没有为切点变化改前缀、重投或更新旧 deadline。SourceReady 切点尚未发行新请求，后续发行归 Runtime 的实际回执；旧27只能历史验证，不能变成新 capture。

共享干净 main fetch／ff-only 同步到 c6dd849，规范／usage／config／caller 哈希不变；复用当日本机 OpenCode 1.19.5 成功缓存，无重复维护或活跃配置切换。固定三消息、temperature=0、thinking=false、每项 max_tokens=2600，实际 REQUEST 参数及源前缀 SHA 已核。0 模型代码／修复采用，0 本岗 JVM、业务源码／Git、Game／Native live 或账本操作。

历史 UNKNOWN／子向量／reservation／旧编码、严格来源、原期限及 writer／Game／episode 边界保持；独立 operator 取消不补原 child 或 NoEffect 证明。普通 Life 遇事件后的正常收束根因是另一个仍需完整 Java／Native 链的义务，不把本轮取消代码当该修复，也不为补满并发重跑已完成任务。

[逐请求成本、指纹和采用分级](2026-11-12-ck3-prior-life17-and-cancel20-two-source-http.json)。原始源码、请求、响应和游戏材料仅留执行机器。
