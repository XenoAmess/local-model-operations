# OpenCode原生工具模式：长期能力记录

mode_id：`opencode-native`。2026-11-02（Asia/Shanghai）建档，初始证据截至2026-11-01已发布三任务及后到成本；没有为建档新开会话或重跑测试。长期更新规则见[能力证据总入口](capability-boundaries.md)和[运营prompt](../prompts/capability-operations.md)。

## 范围与当前判断

OpenCode保存真实assistant/tool历史；模型可在本次获准文件内检索、读取、编辑并消费工具反馈。它也经HTTP请求模型，但与[三消息候选流程](capability-http.md)分别记账。下面结论绑定Windows、指定服务别名`qwen38-coder`及实际版本；1.18.31有只读闭环，1.19.5有源码试点。这些是历史实测版本，不是对当前最新版本的认证。

受控工具工作流有价值，继续保留用于窄源码任务；自主交付与失败恢复仍不稳定。三项真实任务都已交付、验证和正式发表，也都需要owner纠错；尚未证明降低owner准备/修正成本，不据此把主力流程全面切换。版本或参数、权限变化后的能力必须另取证，不能把模型语义错误全部归因OpenCode。

## 基线案例

| case_id / 实测版本 | 实际工具与模型过程 | 交付、采用与剩余边界 |
| --- | --- | --- |
| OC-READ-001 / 1.18.31 | OpenCode子案例实际2 POST：模型生成两个read，客户端执行两个文件读取、回传tool结果，下一响应stop/CLI0。 | 限定只读循环通过，分析仅部分参考/代码采用0；不授编辑、命令或恢复策略。整个重测7 POST还包含直接原生工具探针，不能全算OpenCode请求或任务。[证据](evidence/2026-11-01-native-tool-retest.json)。 |
| OC-GROWTH-001 / 1.19.5 | 4个CLI阶段/56 POST。初轮12步预算只读，续行权限误拦；后两轮取消总步数/POST/wall上限，8次真实编辑成功，仍缺Book实现且13次length。 | owner修正Data/Host并完整编写Book，117有序事件的软件增长场景通过，正式[aa44e50](https://github.com/XenoAmess/ck3_eternal_recurrence/commit/aa44e5040394c429fd1307c049092358c3247c7f)。模型部分采用，不授自主完成或Game结果。[软件回执](evidence/2026-11-01-opencode-task1-owner-validation.json)、[正式回执](evidence/2026-11-01-opencode-task1-formal.json)。 |
| OC-CONFIG-001 / 1.19.5 | fresh会话后沿真实历史修正，2 CLI/112 POST；无总步数/POST/wall上限。模型完成配置主体和多数测试，根路径/URL/fixture多轮仍错。 | owner重写路径、URL校验并纠正fixture，38新增测试通过，实际debug config通过，正式[2d6dfa9](https://github.com/XenoAmess/local-model-operations/commit/2d6dfa9d06b0988f49e6601c98090b1782a63830)。新生成器未再开live会话；debug只授schema/合并配置，不授实际权限匹配或wire。[采用/成本](evidence/2026-11-01-opencode-config-delivery.json)。 |
| OC-LOCALIO-001 / 1.19.5 | fresh会话及2次真实历史修正，3 CLI/127 POST；无总步数/POST/wall上限。三轮后仍有生产/测试矛盾，owner接管。 | owner完成本地I/O分类、共同收尾、句柄生命周期、POST计数及fixture；发布者再发现双输出故障漏并修复。4个新增离线方法分期通过，正式[761ef26](https://github.com/XenoAmess/local-model-operations/commit/761ef26d8dab26cc08442457040a1025f1448571)。只授有限客户端行为，不授模型原稿正确或业务恢复。[采用/验证](evidence/2026-11-01-caller-local-evidence-delivery.json)、[后到成本](evidence/2026-11-01-caller-local-evidence-cost.json)。 |

三源码任务共9个CLI阶段、295 POST/295 END；这是模型往返数，不是295个任务。[阶段元数据](evidence/2026-11-01-opencode-three-task-stage.json)保留当时pending状态，后来验证和发布以上述单独回执为准，不回填旧冻结点。

## 成本基线

| 案例 | 模型CLI区间合计 | 已知任务墙钟与owner成本 |
| --- | --- | --- |
| OC-GROWTH-001 | 1015.947460s | 客户端准备、权限修正、审阅和owner补实现另计；早期工作起点不全，净节省未知。[阶段报告](opencode-pilot-2026-11-01.md)。 |
| OC-CONFIG-001 | 673.019182s | Ready到debug结束2397.861057s，约40分钟，含通知/审阅/纠错/等待；更早准备起点未知。owner纠错区间208.260234s也不是连续人工工时。 |
| OC-LOCALIO-001 | 483.028688s | workspace准备到末次必要测试3705.808984s，约62分钟，含协调、设计、修正及等待；更早阅读与owner持续工作总量未知。 |

CLI区间总和2171.995330s（约36分12秒），跨任务有并行，不等于端到端或持续人工工时。任务二、三的约40/62分钟也不能相加当项目关键路径。无固定条件对照或净节省证据；tokens重复计算历史上下文，cached tokens未报告时保持null。

## 接入故障、模型错误与owner错误分列

| 类别 | 已观察事实与现状 |
| --- | --- |
| 配置/参数 | 自定义模型缺temperature能力元数据、NGit worktree-relative编辑权限误配、SDK把maxOutputTokens/maxRetries额外传到API；已分别修正，新两任务实际wire只有审定9字段、max_tokens16000/T0/usage/thinkingfalse，无API JSON模式。[实际参数](evidence/2026-11-01-opencode-three-task-stage.json)。 |
| 诊断反馈 | 默认deny误禁内部invalid，显式allow后两次实际执行；巨大失败参数又被通用输出截成323B指针，关键parse错误仍不可见，属于部分修复，完整恢复待验证。 |
| 模型输出 | 具体任务出现角色/栈坐标混淆、路径/URL合同错误、生产与测试不一致、重复编辑和length；任务二失败参数实际重复assertNotIn1206/1207次。该退化证据不泛化到所有截断或永久模型上限。 |
| 终态解释 | 两次不限步CLI自然退出0，但最后响应为length、未完成目标；stop、工具应用及CLI0均不等于验收。没有因总量预算kill这两轮。 |
| owner/流程 | 权限误配、整缓存复制、误报已结束会话为在途、Popen guard导致0tests、fixture重复注入以及重复等待聊天冻结确认均有记录；不能算模型耗时或模型语义失败。 |

后两项各响应16000输出tokens、每HTTP180s；无限总步数不取消单响应有限输出和实际文件/业务权限。普通三消息接口保留；这轮没有验证由模型工具执行测试、Git或Game动作，也没有验证原生SDK所有网络故障下的重试策略。

## 继续跟踪的问题

| 下一项真实任务触发条件 | 验证目标 |
| --- | --- |
| 新窄源码任务已有owner认可的离线验收 | 更早返回限定测试反馈，记录能否减少诊断搬运及修正成本；当前还没有这个自主测试闭环的live证据。 |
| 出现参数/工具执行失败 | 验证紧凑错误能否真实回传，记录重复读取、重复编辑、无效循环及自然终态；保留原件，不扩权限来掩盖配置缺陷。 |
| OpenCode/SDK/provider/模型或工作树布局变化 | 按实际新任务核wire、权限求值和工具结果；旧版两文件通过不自动覆盖新版、跨平台或symlink场景。 |
| 有真实传输失败或恢复需求 | 区分模型HTTP重试和会话续行，验证不会重放工具副作用/业务动作；未测恢复与SDK重试保持未知。 |
| 有可比的真实普通HTTP任务 | 按共同协议比较实际交付及owner成本，记录顺序、参考答案暴露和失败；不为凑数据重做已完成任务。 |

运营owner在每次真实结果和交接后更新本页；阶段报告、模型退出或当前无请求都不等于停止长期跟踪。
