# 本地视频服务部署

2026-11-24：[MiniMax H3／FastH3系列部署经验总览](docs/minimax-h3-deployment-experience.md)汇总V2、两套Omni、完整Base与IC的选型、环境恢复、AdaLN故障、解码器、显存保护、整段4K、计时口径与未采用优化，并附已有任务核对证据。本轮只读整理，没有启动模型或改动正式配置。

本目录是 `local-model-operations` 的普通子目录，统一随主仓库提交；不是 Git 子仓库或子模块。源码版本及文件校验见 [source-origin.json](source-origin.json)。模型权重、虚拟环境、CUDA 工具、用户上传和生成媒体不入库。

2026-11-17 用户确认正式选型：Omni 继续 FastVideo；2K／4K 保留当前优化 IC 后端。SGLang／UniServe 保留实验资料，不恢复已取消的量产补测。[全部调研入口](docs/video-framework-research-index-2026-11-17.md)、[FastVideo／SGLang 全面对比](docs/fastvideo-vs-sglang-2026-11-17.md)、[PDD 与注意力实现](docs/h3-pdd-attention-implementation-2026-11-17.md)。

| 服务 | 局域网入口 | 模型名称 |
| --- | --- | --- |
| 图片、文字、视频参考生成 | `http://192.168.1.11:8001/v1` | `fasth3-omni-bf16` |
| 已有视频的本地 2K／4K 重生成 | `http://192.168.1.11:8002/v1` | `open-h3-2k` |
| 网页 | `http://192.168.1.11:7860` | BF16 Omni |
| 独立升级／可用性状态 | `http://192.168.1.11:8004/v1/service/status` | CPU 状态服务 |

- [OOM 自动恢复与管理接口](docs/video-http-api.md#oom-自动恢复与管理恢复接口)：首次 OOM 清理、冷却和检查资源后自动继续；连续两次 OOM 需 `POST /v1/queue/resume`，失败任务不重试。
- [API 3.0 队列与维护管理](docs/video-queue-management.md)：插队、优先级、取消、分页、独立状态；4K 小于等于原 124 帧上限用旧路线，严格大于用完整时间轴。S48 完整 14 秒已完成 LAN／解码和抽帧验收，对端审核待反馈。
- [S48 成片与密集内核短测](docs/h3-full-sequence-validation-and-dense-benchmark-2026-11-21.md)：14 秒原生 4K 完整交付；cuDNN 基本打平，FlashInfer 超长路径校验失败，保留现用后端并恢复队列。
- [当前视频每十分钟巡检](docs/video-progress-monitor.md)：正常采样静默、异常通知同一用户会话；不暂停在途视频，完成后停止巡检，无开机自启。
- [Open-H3 接缝与整段方案](docs/open-h3-seam-solutions-2026-11-20.md)：保留原始只读研究；后续整段 IC 已完成 S48 的完整 14 秒成片验收。
- [14 秒整段原生 4K 可行性分析](docs/h3-single-pass-14s-4k-feasibility-2026-11-20.md)：原始形状与资源预算；实现、容量准入与完整成片验收分别记录。
- [整段 4K 的耗时与加速调查](docs/h3-full-sequence-4k-speed-research-2026-11-20.md)：近百万 token 的密集注意力瓶颈，BF16 密集内核与整段稀疏候选；未切换后端或打断当前 S48。
- [跨机器 HTTP 调用](docs/video-http-api.md)：上传、异步提交、依赖、轮询、取消、下载。
- [启动、停止与队列运维](docs/video-http-queue.md)：同卡共享、自动模型分组、等待上限和故障恢复。
- [原生 4K](docs/open-h3-4k-http.md)：`3840x2160`，保留原版 36 层 FP32 VAE。
- [已采用的数据搬运优化与实测](docs/open-h3-exact-performance.md)：4K／2K 单层耗时减少约 2.0%／6.6%；后续已完成三条控制器完整 2K 同结果对照，优化前后完整 4K 对照尚未重测。
- [部署恢复与上游版本](docs/deployment-git.md)。

运行目录仍为 `/home/ubuntu/workspace/xenoamess_bake_videos`，发布源码不会移动正在使用的模型或改变在线服务路径。服务模板是该机器的部署配置；迁移主机时需修改模板中的用户、绝对路径和局域网地址，准备固定版本的 FastVideo、对应权重和依赖。

全部服务按需启动，无开机自启；完全本地，禁止云端。GPU 工作负载通过 `llm-lab/scripts/run_isolated.py` 隔离，推理上限 80 GiB、聚合 88 GiB，并保留独立内存看护。HTTP 与网页不直接装载 GPU 模型。

5.167 秒／124 帧的原生 4K 已通过生成、局域网下载、SHA-256、音轨、完整解码和首中尾抽帧核对；15 秒 4K 尚未完成真实模型成片验收。软件时间轴测试、单层位级核对和完整成片验收分别记录。
