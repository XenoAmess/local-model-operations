# 客户端每日 OpenCode 检查

每台客户端在本机自然日首次使用本地模型前，检查OpenCode版本。目标为pnpm registry的 `opencode-ai@latest` 稳定版与[共享配置](../config/executor.json)中 `client_maintenance.opencode.minimum_version` 的较高者。最低版本是兼容基线，不是长期冻结版本；当前值为1.18.31。

在共享仓库运行：

```text
python -X utf8 scripts/check_opencode.py
```

检查器先执行 `opencode --version` 和 `pnpm view opencode-ai@latest version --json`。未安装或低于目标时，执行 `pnpm add --global opencode-ai@<本次解析的目标版本>`，随后重新解析PATH并执行 `opencode --version`，核实生效版本不低于目标。只更新这个包；较新安装不降级。OpenCode官方列出了[pnpm安装方式](https://opencode.ai/docs/#install)，pnpm支持[按包和版本全局安装](https://pnpm.io/cli/add)及[查询registry元数据](https://pnpm.io/cli/view)。

## 各种客户端的接入

[共享调用器](../scripts/call.py)的CLI已经在派发前调用每日检查。维护发生在模型HTTP重试循环之外；失败进入AI排障，实际复查成功后继续派发。调用器的源码消息、服务端点和模型重试策略保持各自职责。

OpenCode及其它直接HTTP客户端，应在启动任务前运行上面的检查命令，成功后再启动客户端。长驻客户端在跨日的下一个任务入口重新检查；已经在途的HTTP和工具动作不因维护而重放。

Python嵌入式客户端可调用：

```python
from scripts.check_opencode import ensure_current, read_json

config = read_json("config/executor.json")
ensure_current(config)
# 检查成功后，进入本业务实际的模型任务入口。
```

已有AI客户端可向 `ensure_current` 传入 `repair=repair_environment` 同步回调；回调由本业务现有AI能力实现，接收结构化诊断并实际修复环境。检查器在回调返回后重新执行检查，不能只信任“已经修复”的文字回执。内嵌回调最多自动进行三轮修复，仍未恢复则返回新的诊断，由宿主AI继续判断后续修复或具体外部阻塞。

需要命令接口时，设置 `LOCAL_MODEL_AI_REPAIR_COMMAND` 为JSON argv数组，指向本业务已有的AI修复驱动。驱动从stdin接收诊断JSON，执行排障后返回；日志留在 `repair-driver.jsonl`。子驱动不继承这个启动变量，避免嵌套检查递归启动自身。检查器不默认选择其它模型provider或新建一套agent系统。

没有绑定回调或驱动时，检查器以退出码75输出 `AI_REPAIR_REQUIRED` 及 `request_path`。这表示向承载它的AI会话交接恢复工作，不是业务终止：AI读取请求与诊断日志，使用现有工具自主修复，重新运行检查，通过后继续原任务。`call.py`同样透传该恢复请求。纯非AI程序应先接入修复驱动或由宿主AI管理这个交接。

直接调用 `scripts.call.dispatch` 是传输层接口，不会自动维护全局软件；嵌入式owner必须在入口执行 `ensure_current`。消费项目同步检查器、调用器和共享配置时，记录本仓库来源commit；已有本机配置缺少维护字段时，检查器使用其所在共享仓库的维护配置，不能借缺字段绕过要求。

## 每日状态与并发

成功记录按客户端本地日期缓存，同一台机器、同一用户的多个业务共用。当天有效记录命中时，不再执行pnpm或OpenCode子进程；策略或PATH解析出的命令路径改变时重新检查。配置或安装发生变化后的复查属于新的有效性检查。

默认状态目录为Windows的用户 `LOCALAPPDATA/local-model-operations/opencode`，或其它平台的 `XDG_STATE_HOME/local-model-operations/opencode`，后者未设置时使用用户 `.local/state`。可通过 `LOCAL_MODEL_CLIENT_STATE_DIR` 或独立CLI的 `--state-dir` 指定本机目录。目录应留在执行机器，不在项目、机器或用户之间共享成功记录，也不提交到公共仓库。

`daily.json`记录检查日期、registry版本、目标、安装前后版本及命令路径；`checks.jsonl`保存实际维护命令和结果。输出中的 `cached` 表示本次复用成功记录，`updated` 表示该记录对应的检查是否进行了更新，不表示缓存命中又更新了一次。

跨进程文件锁保证同机多个客户端只有一个实际检查和更新者，其余客户端等待并复用成功结果。进程退出会释放系统锁，不删除锁文件来抢占更新。命令、更新及等待时限读取共享配置，默认分别为30、300、420秒；每日检查不是按时自动唤醒的计划任务，没有使用本地模型的当天不需要额外联网。

## 失败处理与验证范围

缺少pnpm、registry查询失败、更新失败、超时或更新后PATH仍指向旧版本，均生成结构化AI修复请求，记录实际错误和诊断日志位置，不保存当天成功状态。AI按错误检查命令遮蔽、pnpm全局bin、registry/网络/代理、安装脚本或文件占用等原因，执行具体修复，再做真实复查并恢复原任务。更新仍使用pnpm，服务端点和模型不自动切换。

修复使用宿主AI现有能力，允许在OpenCode版本未达标时进行维护诊断，避免“必须先升级才能修复升级”的循环。业务派发等待维护核实，但AI修复本身继续工作；修复不重放先前业务动作。AI客户端应保留已尝试办法，只有确实仍受外部条件限制时才向用户报告阻塞。

27项离线测试使用模拟的pnpm和OpenCode命令及模拟AI修复处理器，覆盖每日缓存、并发、失败交接、修复后复查与仅一次业务派发；这些测试不授真实AI诊断能力。2026-11-01在Windows / CPython3.13.2 / pnpm11.7.0实际完成1.18.31至1.19.5更新并核实CLI版本，同日从其它工作目录运行独立入口命中缓存且未执行维护命令；[验证摘要](evidence/2026-11-01-opencode-daily-update.json)另记真实结果。其它平台尚无运行回执，CLI版本更新也不追授新版本的工具循环或业务正确性。
