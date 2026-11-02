# 受控只读OpenCode接入

本页来自[真实只读审计](evidence/2026-11-02-opencode-readonly-audit.json)，实测Windows/OpenCode 1.19.5。工具读取和配置隔离已执行；该业务审计最终没有完整答案或采用，不能把入口可用写成模型完成任务。其它版本、POSIX客户端和symlink逃逸未验证。

## 零编辑权限的配置

[独立生成器](../scripts/opencode_readonly_config.py)提供`build_readonly_config(executor, *, source_root, max_output_tokens=16000)`，不要求伪造owned文件。原[编辑配置入口](../scripts/opencode_config.py)仍要求非空owned_files，行为不变。新生成器只读executor、输出配置，不执行维护、模型请求、工具、数据库复制或启动。

```text
python scripts/opencode_readonly_config.py --executor config/executor.json --source-root D:/project/java
```

这里的路径是机器映射示例。保存输出配置后，从另一个空、非Git目录启动实际客户端；不要从整个源码Git根启动后把external_directory deny当作源码子目录沙箱。

| 实际1.19.5求值 | 本次接线 |
| --- | --- |
| read请求worktree-relative路径 | 非Git原始worktree为`/` sentinel；Windows本次读权限键相对盘根，如`project/java/**`。 |
| glob/grep请求的是查询pattern | 允许这两个查询工具；目录边界由external_directory处理，不拿查询pattern冒目录过滤器。 |
| external_directory只在instance目录/worktree之外询问 | 独立空cwd使目标源码走外部目录检查，仅allow指定可信源码根。真实Git worktree可能直接放行同树其它目录。 |
| 默认deny | 仅read/glob/grep和内部纯诊断invalid获准；没有edit/write/bash、Git、网络、委派或业务工具。invalid不一定出现在发给模型的visible tools里。 |

范围依赖当前版本的实际求值及可信文件树，词法路径和成功读取都不是通用文件系统沙箱证明。[read](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/read.ts)、[glob](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/glob.ts)、[grep](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/grep.ts)和[目录检查](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/external-directory.ts)是本次版本依据。

## 启动与同会话恢复

真实入口先执行[当天维护](client-maintenance.md)。为一次新任务选择独立config/data/state目录，package cache可以复用已安装的非证据缓存；不复制源码树或整套cache来构造会话。`isolated_environment(...)`返回供子进程使用的环境覆盖，不修改宿主环境或启动程序。

必须设置`OPENCODE_DISABLE_PROJECT_CONFIG=true`，并清空继承的`OPENCODE_CONFIG_CONTENT`和`OPENCODE_PERMISSION`。`OPENCODE_CONFIG`不是最高优先级：1.19.5在它之后还合并项目配置。本次同cwd恢复读到了父目录的冻结旧config，旧relay端口覆盖新端口，产生0 upstream POST的本地ECONNREFUSED；这是owner接入故障。[合并顺序](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/config/config.ts)、[开关](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/core/src/flag/flag.ts)与修复后的实际请求共同支持该结论。

启动前在同一cwd和环境运行`opencode --pure debug config`，读取实际合并后的endpoint、model、权限、agent和预算，不能只看exit0。本次prepare曾通过解析却没有核effective endpoint，仍把旧端口带入正式启动。

```text
opencode --pure run --agent pilot --format json "本次获准的只读源码任务"
opencode --pure run --session ACTUAL_SESSION_ID --agent pilot --format json "真实技术诊断"
```

命令需在上述已隔离环境执行。只有实际授权续行才用第二条；先核原CLI已结束，仅用SQLite backup保存必要的已结束数据库，复用真实session ID和原cwd，原config/REQUEST/SSE/DB证据保留。本次原DB/WAL在备份前后字节相同，没有移动旧配置来绕过合并故障。

模型alias/服务仍取共享executor。原生循环不强加三消息或API JSON模式；本次实际wire为9字段，有限max_tokens16000/T0/usage/thinking=false、真实assistant/tool历史。总steps/POST/wall限制按用户当前授权分别记录。本次单HTTP180秒由独立记录relay实施；本配置生成器不提供网络超时或传输捕获，不把模型limit元数据当超时保障。新公共helper只有4项针对性离线检查，未为发布再开live模型任务；真实执行证据来自本次私有适配器的配置形状。

## 识别无信息循环

本次Grep声明只有pattern/path/include，wire schema未声明additionalProperties=false。模型传入output_mode/-C后实际工具未报参数错，也未扩大上下文；[工具实现](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/grep.ts)只消费三个声明字段，[通用校验](https://github.com/anomalyco/opencode/blob/v1.19.5/packages/opencode/src/tool/tool.ts)存在，但本轮没有把多余字段拒绝或反馈为错误。先核实际schema和结果，用read的filePath/offset/limit取上下文。

现有日志可先用[纯只读 trace 审计器](opencode-trace-audit.md)提取重复参数/结果 SHA、每份 REQUEST 的角色和 ID 配对、grep 文件归属及读取范围。它不设循环总帽或自动停止，也不从同结果推断模型根因；中断与最终文本仍分别保留，公开结果先经 owner 审阅。

首段有186次连续相同受支持query及输出SHA；owner说明工具参数后确实读取了新callee，随后又27次重复完全相同的合法query和输出。两次均依据具体无进展证据获准精准停止owned CLI，未设置总步数封顶；中断请求保UNKNOWN，不造END，不授模型fatal或自然完成。可在自有适配器中严格检查未知参数或明确反馈忽略字段；本次没有修改OpenCode内置工具。记录重复输入/输出、读取区间、工具错误和人工纠正成本，比累计请求数更能解释结果。
