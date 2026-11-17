# FastH3 V2 启动与停止

本机使用用户级 systemd 服务 `fasth3-v2.service` 管理 FastH3 V2。以下命令以 `ubuntu` 用户执行，可在任意目录运行。

当前采用按需手动启动，已关闭开机自启。服务运行时，模型和推理缓存会持续占用显存；不用时停止服务即可释放这些显存。

2026-10-30 更新：当前提供参考生成的是另行部署的 [FastH3 Omni](fasth3-omni.md)，网页端口 7860、API 端口 8001。V2 保持停止；本页 V2 的旧端口 8000 现由文本模型网关占用，重新启用 V2 前需调整端口配置和客户端地址。不要同时启动两个视频模型占用同一块 GPU。

## 启动服务

```bash
systemctl --user start fasth3-v2
```

启动后需要等待模型加载。查看状态和日志：

```bash
systemctl --user status fasth3-v2 --no-pager
journalctl --user -u fasth3-v2 -f
```

日志出现 `Application startup complete` 后，可检查 API：

```bash
curl --noproxy '*' --fail http://127.0.0.1:8000/health
```

返回 `{"status":"ok"}` 表示服务已就绪。网页入口：http://127.0.0.1:8000/playground/。

`start` 只启动本次服务，不会开启开机自启。

## 停止服务

```bash
systemctl --user stop fasth3-v2
```

停止后会结束正在运行的生成任务，并释放该服务占用的 GPU 显存。下次使用时再次执行启动命令，服务会重新加载模型。

确认停止状态和显存占用：

```bash
systemctl --user is-active fasth3-v2
nvidia-smi
```

停止状态应显示 `inactive`。

## 关闭开机自启

```bash
systemctl --user disable --now fasth3-v2
```

此命令同时停止服务并关闭开机自启。确认设置：

```bash
systemctl --user is-enabled fasth3-v2
```

应显示 `disabled`。关闭开机自启后，仍可使用 `systemctl --user start fasth3-v2` 手动启动。

## 重启与配置

修改配置后重启服务：

```bash
systemctl --user restart fasth3-v2
```

`restart` 会启动已停止的服务，适合准备立即使用时执行。

- 项目目录：`/home/ubuntu/workspace/xenoamess_bake_videos`
- 配置文件：[fasth3-v2.yaml](../fasth3-v2.yaml)
- 启动脚本：[start-fasth3.sh](../start-fasth3.sh)
- 用户服务文件：`/home/ubuntu/.config/systemd/user/fasth3-v2.service`
- 生成视频与部署详情：[项目说明](../README.md)
