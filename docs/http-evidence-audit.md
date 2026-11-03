# 普通 HTTP 证据离线审计

运行 `python scripts/audit_http_evidence.py EVIDENCE_DIR`，读取现有 `call.py` 的单个任务目录，向 stdout 输出脱敏 JSON。它不调用模型、不导入 caller、不重发请求、不执行记录中的代码或业务动作，也不修改原件。OpenCode 的 assistant/tool 历史继续使用[原生 trace 审计器](opencode-trace-audit.md)。

只识别当前目录的 `REQUEST.json`、`EVENTS.jsonl`、`ATTEMPTn-RESPONSE.sse`、`ATTEMPTn-CONTENT.txt`、`ATTEMPTn-RESULT.json`。不递归，不使用原件中记录的路径，不打开源码清单或其它任意文件。链接或 Windows reparse 文件被拒读；这只是格式读取器，不是 OS 沙箱。

报告分开保留以下机械事实：

- 实际 REQUEST 参数、三消息形状、每条消息 UTF-8 字节数/SHA 和源码前缀 SHA；不重新装配请求，也不据文件数宣称依赖闭包完整。
- 每个 attempt 独立的原始 artifact 字节数/SHA、SSE finish reason、`[DONE]`、解析异常和完整性；不拼接重试片段。
- 完整文本的严格 `json.loads` 结果 `VALID` / `INVALID` / `UNKNOWN`，以及顶层类型。拒绝非 JSON 的 NaN/Infinity；解析器资源限制保持 UNKNOWN。语法错误只输出位置和异常类别，不输出包含正文的错误消息。
- RESULT、ATTEMPT_END、FIRST_CONTENT、HEADERS 的数值分别保留来源，缺失为 UNKNOWN、冲突显式列出。TTFT 只取已记录的首有效内容字段，不用响应头、SSE 次序或 UTC 相减估算。未报告 cached tokens 保持 null。
- CONTENT 与 SSE 重建文本的原样比较，以及单独的 LF 投影比较。历史 Windows caller 的文本写入可能改变物理行尾；当前共享 caller 对新 CONTENT 使用 UTF-8 二进制保存。历史原件不被改写，投影相等不冒充原字节相同，也不放宽原样不等时的严格 eligibility。消费项目的旧 caller 副本须由其 owner 另行明确同步，不随共享 Git 自动切换。

`VALID` 只说明外层 JSON 语法合法。`REVIEW_ELIGIBLE` 只说明完整 STOP 流、合法语法且未发现所核对的冲突；所有候选始终标记 `OWNER_REVIEW_REQUIRED`，不判断字段合同、论证、代码或业务正确性。length 一律 `DISCARD_LENGTH`，即使其 JSON 合法。缺 finish/DONE、坏 SSE 或原样内容冲突不获 review eligibility。只有 CONTENT 时仍可判语法，但流完整性与 eligibility 保持 UNKNOWN。顶层数组或标量的语法合法也不证明请求的对象合同通过。

默认读取界限为每 artifact 8 MiB、总计 64 MiB、10,000 个非空事件行、64 个 attempt、512 个直接目录项。可分别用 `--max-artifact-bytes`、`--max-total-bytes`、`--max-events`、`--max-attempts`、`--max-directory-entries` 显式调整为正整数。超限会报出具体类别，拒绝把截取片段当完整证据；检测文件增长时最多额外读一个 sentinel 字节。它们是这次离线读取的界限，不是模型任务总 steps/POST/wall 上限。

默认不输出 raw 正文、业务路径、task ID、未知模型名、未知枚举或原始 failure 文本。只允许已知参数枚举、数值和摘要；报告中的 SHA 仍可能属于私有证据，是否公开须由 source owner 决定。CLI 发现缺失、不可读、无效或超限 artifact 时返回 1；语法错误、length、内容不等和冲突也要读取对应分类字段，不能只看进程退出码。

验证命令：`python -m unittest discover -s tests -p test_http_evidence_audit.py -v`。独立合成测试覆盖语法合法但内容错误、length 残片与合法 length、有效最终 JSON、缺事件、CONTENT-only、无 DONE、坏流、冲突、重试隔离、隐私和有限读取。真实 symlink 创建在首次执行机受权限限制，拒读分支以合成 Windows reparse 属性验证，不冒充跨平台链接集成验收。真实机器材料只在执行机核对，不作为公开 fixture。
