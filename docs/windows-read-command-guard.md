# Windows 只读命令：V8 cell 接线

[factory](../scripts/snippets/windows_safe_read_prelude.js.txt) 是供宿主 `functions.exec` V8 cell 逐段复制的完整函数正文，没有 import、eval、文件读取、Node CLI 或 export。不要把源码文件路径作为 shell 命令执行。机器上的只读 reader 由本机 owner 审阅并配置；共享片段不携带某台机器的 reader 默认值。

将完整 factory 定义放在本次 cell 开头，再建立本机 binding。以下路径只展示形状，并非已安装入口：

```javascript
const safeReader = createSafeReadCaller(
  request => tools.exec_command(request),
  Object.freeze(["D:/tools/read-lines.cmd"])
);
const R = safeReader.read;
// 本机 owner 先替换为实际已审 reader 与获准数据路径，再调用 R(path,start,end,maxOutputTokens)。
```

`prepareRead` 只构造不可变 prefix、argv、command 和工具参数；`validatePlan` 只接受同一 factory 产生的不可变计划，逐项重建核对完整命令及工具参数。`read` 在回调前立即执行这两步，传给宿主的对象恰含 `cmd`、`shell:"cmd.exe"`、`login:false`、`max_output_tokens`。API 不提供 raw cmd 或额外工具参数的覆盖入口。失败抛出固定消息与大写 `code`，不构造备用命令。

本入口支持一个绝对 `.cmd` reader token，以及 ASCII 盘符绝对数据路径。数据扩展名 `.py`、`.java`、`.json`、`.md` 仍是参数。空白、引用、Unicode、shell 字符、ADS、重复或尾分隔符、点目录及设备名均不支持；不尝试自动引用或规范化。范围为最多 300 行、行号不超过 2147483647，输出预算为 1..20000，完整命令最多 4096 字符。

已验证的是实际 V8：4 组主见证与 3 组独立见证首次通过，测试回调只捕获参数，没有执行真实工具或 reader。原 peer v3 曾因默认参数函数内的 `use strict` 指令产生 SyntaxError，所有函数体均未进入；删去该一行后的 v4 完成必要首次执行。原失败保留。随后两个具名消费 cell 分别完成一次真实只读操作；其中一个消费 cell 的 factory 正文与冻结源码逐字核对相同。这些结果只授对应 cell 的接线。

公开[主见证](../tests/fixtures/windows_read_cell_primary.no-exec.js.txt)保留原字节，入口为 `runReadCallerFixtures(createSafeReadCaller)`。公开[独立见证](../tests/fixtures/windows_read_cell_independent.no-exec.js.txt)来自已验 v4，但保留历史函数名 `runReadPreludeIndependentWitnessesV3`；显式第二参数 `true` 才选择全部三组。其两个机器 reader/data 字符串已换为合成路径，其余正文不变；这份 portable 投影没有为发布重跑，不追授为原样实测。见证文件仅有函数定义，不会自动执行，也没有虚构的 Node 测试入口。

独立源审还修复了 owner 初稿的普通数组 `slice` 覆盖问题：接收数组自有 `slice` 可替换 reader。现版先核一元素长度、直接捕获该元素、统一处理取值异常，再冻结新的字面量数组；不调用输入 slice、iterator 或 species。模型完整实现稿源审拒收，最终 factory 与主见证由 owner 编写；工具闭环成功不代表模型代码已采用或准备成本下降。

这不是全局拦截器。其它直接 `tools.exec_command` 调用仍可绕开本片段；不证明跨 worker 接入、文件身份、只读代码、reparse/symlink 安全或 OS 沙箱。历史文件关联副作用继续为 UNKNOWN。另一个纯 Python guard 的九项测试属于独立 source-utility 层；当前 V8 cell 没有 import 它，本次可移植发布也不将它当作此消费者。
