# 来源与迁移记录

本仓库从公开项目 [ck3_eternal_recurrence](https://github.com/XenoAmess/ck3_eternal_recurrence) 抽取本地模型运营方法。历史快照保留探索过程；当前调用方式、路径和配置以本仓库的现行文件为准。迁移没有复制业务源码、运行账本、原始请求、模型响应、JFR 或二进制证据。

## 原文快照

迁移基线为原项目已正式发表的提交 [`0958f36720a2cf75d1e3ede84ff3ae7fa730d91d`](https://github.com/XenoAmess/ck3_eternal_recurrence/commit/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d)。下列三份文件直接复制该提交中的 Git blob，未改正文、链接、换行或文件末尾；SHA-256 针对归档文件的实际字节。

| 本仓库归档 | 原公开路径 | 字节数 | SHA-256 |
| --- | --- | ---: | --- |
| [worker 指南原文](history/local-model-worker-guide.md) | [docs/local-model-worker-guide.md](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md) | 50,663 | `7060ed951b7b765b95babf407ef7ea60ec37729a3c0ff2a366acd44d0da32762` |
| [执行者可行性原文](history/local-model-executor-feasibility-2026-10-28.md) | [docs/local-model-executor-feasibility-2026-10-28.md](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-executor-feasibility-2026-10-28.md) | 36,796 | `6c51f1d2dfc34218ae15060cd624849cdd394cb5ec6e74b85daeb91bdcf18429` |
| [能力边界探索原文](history/local-model-capability-boundary-2026-10-28.md) | [docs/local-model-capability-boundary-2026-10-28.md](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md) | 28,980 | `bb0a73af3d2f54eb2476f12db54d2079d17b82b766b991143647dda78a3454a8` |

指南在该基线前最后一次修改的提交是 [`2d37c70751b3d1c28b20254a14afeb824573a489`](https://github.com/XenoAmess/ck3_eternal_recurrence/commit/2d37c70751b3d1c28b20254a14afeb824573a489)，可行性文档为 [`133514d9ce02c08a4900b974690e5ab48afd858b`](https://github.com/XenoAmess/ck3_eternal_recurrence/commit/133514d9ce02c08a4900b974690e5ab48afd858b)，能力边界文档为 [`c2b7ad84e9602de22c938d6f42b3729decd79fe1`](https://github.com/XenoAmess/ck3_eternal_recurrence/commit/c2b7ad84e9602de22c938d6f42b3729decd79fe1)。这里采用同一已发表基线，便于复核它们当时共同存在的版本。

原执行机器的指南工作树使用 CRLF，50,935 字节，SHA-256 为 `238f9e176faeb80370527ee5f2aae980e6af99be05e89453b01037513d4dc338`；它规范化为 LF 后与上述公开 Git blob 相等。本仓库归档的是公开 Git blob 的 50,663 字节，未把工作树哈希标成归档哈希。稀疏工作树未展开的文件从同一提交读取，不据文件未落盘推断源缺失。

归档中的旧地址、机器名、盘符、工具约定、业务术语及早期产品预研均保留其历史含义。原相对链接也保持原样，部分应回到原项目对应提交查看；它们不是新 worker 必须取得的文件，也不覆盖本仓库后来的规则。历史产品接口说明不构成当前兼容性承诺。

## 配置与补充依据

配置和调用脚本由独立迁移单元维护，不在上述原文快照内替换。

| 依据 | 原公开版本 | 迁移用途 |
| --- | --- | --- |
| 执行器配置 | [原配置](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-executor-config.json)，7,379 字节，SHA-256 `fa854f62ae217b7012c93e5ba31b5b4f4914def7e2db9e7184feab7a47c0704c` | 提取指定服务、模型、固定 system、默认参数和重试策略；机器目录与执行者身份改为本仓库的可配置接口。 |

能力边界档案用于核对上下文规模、实际改写范围、提示程度、owner 修正及有限验证；现行整理不复制整个项目进展日志，也不从旧结果新增通用能力结论。

现行规范从这些资料中归纳可复用步骤，不继承原项目的游戏、原生接口、发布或运行权限。原文中本机证据路径只标识当时的保管位置；新任务使用执行机器自己的目录和身份。精确原请求及大证据仍由原执行环境保管，本仓库只公开已审的规则、必要脱敏事实与公开反链。

## 2026-11-01新增经验与调用器迁移

当前便携调用器及15项本地 mock 的源码版本为 [`aa12e525d5f6cb842cae71dabe33071a91794933`](https://github.com/XenoAmess/local-model-operations/commit/aa12e525d5f6cb842cae71dabe33071a91794933)。owner 的迁移说明保留旧13项通过与后续无LF断流分类修订，实际修订03验证为15项通过；其 `MIGRATION-NOTES03.json` 为2,318字节，SHA-256 `84bf8b56d7edf36de59853f3e30f3fd38ef9b7904c97ffbc09912f91bd238a09`。说明与实际回执仍由执行者保管，公开源码和测试可直接复核；未把模型审计答复计作迁移源码采用。

下表为新经验的具名独立摘要，已读核相关字段并核实际字节哈希，未复制私有业务原件。它们**尚未公开**，文件名用于证据辨识，不能当作其它 worker 的依赖或公共下载地址。经验页的事实限定于这些摘要及其原执行记录；摘要本身不是独立复现实验。

| 执行者保管记录 | 字节数 | SHA-256 | 本次公开范围 |
| --- | ---: | --- | --- |
| `PORTABLE-BUDGET-RULE220.json` | 1,629 | `71135723f79319b9a57ae49a7894faf959a40db0f0bf8890fbbdaa57cbbff46b` | caller64MiB / callee最大8MiB，参数门与实际包体分别验证，模型输入漏callee及多owner审漏成本 |
| `ROOT-SHORT219.json` | 8,275 | `f9c9d4c70e4f85c68129a6217235a5918dbf48969048733edc79bf291cf83d19` | GC事件、pause并集与allocation样本聚合的有限摘要 |
| `GC-ALLOCATION-SUMMARY219.json` | 22,778 | `978616e387d00ba3c189724aa8e20b3cb30239944307e10d9639ae645338de5d` | 同一次60秒JFR的独立GC/allocation过滤摘要 |
| `WEIGHT-SENSITIVITY219.json` | 52,024 | `32238640a5426efcbd83708a97eee64753d827d08f52552e0a9f878632c51834` | 最大单样本权重、分布及排除最大项的敏感度；不授CPU或精确总分配结论 |

JFR记录时长及DataLoss0由原执行者的小summary核实；本次整理没有重新采样、读取原始JFR或大过滤文件。新增预算与诊断教训写入现行文档，未回填上面的三份历史原文。

## 后续经验的来源要求

新增经验至少注明日期、服务或模型标识、真实任务范围、实际输入是否齐全、owner 提示和修正、验证状态、结论限制及可复核来源。公开源码优先使用固定提交的路径链接；本机回执未公开时，明确说明证据由执行者保管，不伪造公共下载地址。

新的实际结果另增记录，不回写冻结快照。准备、分派、HTTP 结束、源审、编译、有限行为验证、正式发表和真实业务效果分别标明。输入缺失、工具或夹具错误与模型在齐全输入下的错误分别归责；不从不同口径的结果拼出统一成功率、净节省比例或永久能力上限。
