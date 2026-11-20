# 当前视频每十分钟巡检与异常通知

本次 S48 已于 2026-11-20 23:54 完成，巡检 timer 已按设计停止；以下保留部署机制和按需运维说明。

2026-11-20 用户要求：当前 S48 海边蝴蝶 14 秒整段 4K 每十分钟观察一次，异常时通知；让在途视频继续运行，两个 BF16 内核的短测等完整视频交付后再做。

已部署 `video-s48-progress.timer`，每 600 秒调用一次轻量 CPU 服务 `video-s48-progress.service`。正常检查只记日志和本机采样文件；出现异常通过已配置的 Paseo CLI 通知**同一用户会话**，由助手核实并向用户说明。没有通知其它人，也没有模型推理、CUDA 内存分配、任务暂停或自动修复动作。

## 看什么，以及何时通知

| 检查项 | 判定 |
| --- | --- |
| HTTP 任务与独立状态 | 请求失败会再试一次；持续失败时报告“状态待核实”，不据此断言视频失败 |
| 任务失败 | `failed` 发出通知，保留失败证据 |
| worker | HTTP 仍显示执行中，但 unit 退出或被冻住时通知 |
| 进度 | 去噪阶段至少 30 分钟没有真实阶段／层／步推进；其它阶段至少 45 分钟。单次 10 分钟没更新不算卡死 |
| GPU 空闲 | 去噪阶段连续两次采样低于 5% 利用率，而且进度至少 10 分钟未推进 |
| 错误日志与 OOM | 识别 CUDA OOM、非法访存、device assert、traceback；检查 worker cgroup OOM 计数增加。普通文档警告和高显存占用不单独当作失败 |
| 资源余量 | 主机可用内存低于 28 GiB、输出盘剩余不足 10 GiB、GPU 温度达到巡检阈值 85℃时提示检查 |

当前全序列每五层报告一次进度，约需要十五分钟，因此停滞阈值必须大于常规报告间隔。巡检每十分钟运行，异常的发现延迟受采样间隔影响；这不是秒级监控。

同一持续异常只通知一次，恢复后再次出现才重新通知。通知发送失败保留待发事件，服务一分钟后重试；即使异常后来恢复，也保留待通知事件。任务正常完成或取消后自动停止 timer；失败则在通知被 Paseo 接受后停止。最终成片下载、SHA／帧数／音轨／完整解码和画面审核仍由原有 `video-full-sequence-validation-20261120.service` 接续。

## 查询、启动和停止

```bash
systemctl --user list-timers video-s48-progress.timer
systemctl --user status video-s48-progress.timer
journalctl --user -u video-s48-progress.service -n 10 --no-pager

# 当前任务的采样记录；不含权重或视频
cat outputs/video-queue/s48-progress-monitor-20261120/latest.json

# 已准备本机配置后，立即检查一次并开启每十分钟检查
systemctl --user start video-s48-progress.service video-s48-progress.timer

# 只停止巡检
systemctl --user stop video-s48-progress.timer video-s48-progress.service
```

本机配置位于 `~/.config/local-video/progress-monitor.json`，包含目标任务、worker unit、状态 URL、采样目录、阈值和 timer 名称；同目录 `progress-monitor.env` 只提供 Paseo CLI 与当前会话标识。两者权限为 0600，不提交 Git。迁移机器或检查另一任务时，需要明确配置这些值。

两个 unit 的模板没有开机启用关系，`UnitFileState=static`；只执行 `start`，不执行 `enable`，未开启开机自启。CPU 服务内存上限 256 MiB、禁用 swap。异常只触发通知，不改变正式服务、队列、GPU worker 或 80／88 GiB 限制。

实现：[巡检脚本](../tools/watch_video_progress.py)、[service](../deployment/systemd/video-s48-progress.service)、[timer](../deployment/systemd/video-s48-progress.timer)。十项软件测试覆盖正常慢进度、真实停滞、终态、进程退出／冻结、OOM 增量、通知去重和失败重发；部署时实际采样与 timer 证据见[部署记录](../deployment/video-queue/progress-monitor-verification-20261120.json)。这些测试没有向用户发送模拟故障通知。
