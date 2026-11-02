# 只读分析原生工具日志

`python scripts/audit_opencode_trace.py TRACE_DIR` 读取已有记录，将脱敏 JSON 输出到 stdout。它不启动 OpenCode、不发 HTTP、不执行工具、不跟随工具参数里的业务路径，也不停止进程或修改日志。可在自有目录重定向报告；原始记录仍留执行机器。

```text
python scripts/audit_opencode_trace.py /path/to/owned-trace
```

该路径只是形状示例。Python API 为 `audit_trace(pathlib.Path) -> dict`，仅用标准库。读取范围是根目录的 `CLI-EVENTS.jsonl`、可选 `CLI-ACTUAL.json`、`OWNER-STOP.json` / `STOP-REQUEST.json`，以及一层 `http-*/REQUEST.json` 和 `SUMMARY.json`。数字后缀按数值排序，其它后缀随后按名称排序；不递归源快照，不读 RAW-SSE。忽略所选记录文件或子目录的 symlink，不因此宣称通用 OS 沙箱。

报告 schema 为 `local-model-operations.opencode-trace-audit/v1`。有缺失、损坏或无法读取的记录时保留可分析结果并记录类别，CLI 返回 1；否则返回 0。正在写入的记录可能暂时无法解析，此时保持未知，工具不会等待、重试请求或补造终态。

| 部分 | 实际含义 |
| --- | --- |
| `requests` | 实际预算、温度、tool_choice 类别、stream/usage/thinking/JSON 模式、角色计数、原 system/首 user 是否变化，以及每份 REQUEST 的工具 ID 配对计数。|
| `tools.repetition_groups` | 相同工具和 canonical JSON 参数 SHA 的重复组；分别列原结果 SHA 变体、完全相同结果组和 grep 顺序等价组。只对 completed 且有字符串结果的工具计算重复；其它状态仍计数。|
| `tools.reads` | 请求 offset/limit、实际 display 范围、metadata truncated、显式字节 cap 与续读 offset。不同读取区间不合并为重复查询。|
| `termination` | tool_calls、stop、length、缺失终态 UNKNOWN、存在 owner 停止记录且发生未完整传输的分类；另列文本事件存在与 CLI exit，互不代替。|

原消息、参数、结果、错误正文、目录名和 call/session ID 均不输出。只显示已知工具/角色/终态标签；未知标签不原样转发，未知工具名以 SHA 区分。模型别名只明文显示共享已知 `qwen38-coder`，其它别名只给 SHA。参数仅输出经过类型检查的标量。它不是任意第三方日志格式的通用脱敏器，公开报告仍需 owner 审阅。

grep 归一化只识别完整 `Found N matches`、绝对文件标题及缩进或不缩进的 `Line N: content`。每个结果都按文件、行号、内容与重复次数归一；不把所有行简单排序，否则同一行移到另一文件会被误判等价。格式不识别、声明计数不符或结果被截断时，归一化保持未知。完全相同结果或仅顺序变化是无新增信息线索，不证明模型/模板根因，也不自动触发停止。

read 的 `truncated=true` 可能仅表示请求区间后还有行。只有结果明确写出 `Output capped at ... KB` 才计字节 cap；`totalLines` 可能只是可见输出范围，不能据此证明已读完整文件。工具不打开 `filePath` 来核内容，`source_parity` 始终为 UNKNOWN。owner-stop 记录与不完整流的关联也不证明网络故障根因；stop 本身不代表出现文本，更不代表业务答案正确。

没有固定总步数、POST 或 wall 上限，没有自动 kill、重发或业务动作。7 项针对性 Python 检查涵盖独立合成场景及隐私/异常形状；另对既有两组真实只读日志完成适配核对，见[采用与成本](evidence/2026-11-03-http-readonly-trace-auditor.json)。生成模式是普通三消息 HTTP，产物用于 OpenCode 日志，不能算一轮新的原生模型任务或宣称节省了 owner 工时。
