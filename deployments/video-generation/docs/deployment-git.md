# 部署配置保存与恢复

用户 2026-11-17 明确：部署资料应作为主仓库的普通子目录统一管理。权威位置为 `XenoAmess/local-model-operations` 的 `deployments/video-generation/`，不使用 Git 子模块、不复制 `.git`。本机 `/home/ubuntu/workspace/xenoamess_bake_videos` 保持原运行位置；其中的本地 Git 仅用于运行目录回溯，不能代替主仓库发布。模型、环境和运行输出继续留在本机。

当前 BF16 Omni 与 2K 的服务定义、共享队列、客户端和启动停止方法见 [HTTP 共享队列部署](video-http-queue.md)。下文同时保存此前 NVFP4 与上游补丁的恢复资料。

本项目目录保存本机部署方式。2026-11-16 首次建立 Git 版本记录；目录原先没有 `.git`。模型权重、CUDA 工具、虚拟环境、生成视频及用户上传素材不提交。

FastVideo 是独立上游源码，基线为 `a0e6cf1f5086c9af735d73e6c0b80dbc1d5817b3`。本仓库通过 `deployment/fastvideo/source.json` 固定版本，并保存完整补丁 `deployment/fastvideo/adaln-reference-subsets.patch`，包含修复、9 项回归测试及 CI 注册。不得向 FastVideo 官方远端推送本机部署配置。

恢复源码：

```bash
git clone https://github.com/hao-ai-lab/FastVideo.git
git -C FastVideo checkout a0e6cf1f5086c9af735d73e6c0b80dbc1d5817b3
git -C FastVideo apply --check ../deployment/fastvideo/adaln-reference-subsets.patch
git -C FastVideo apply ../deployment/fastvideo/adaln-reference-subsets.patch
mkdir -p llm-lab/logs outputs omni-web/uploads omni-web/outputs omni-web/cache
```

环境版本见 `requirements-omni-deployed.txt`。本机原有 `.venv` 和 CUDA 内核已经安装；新机器需按 FastVideo 官方文档安装依赖并编译相应 GPU 内核。CUDA 13.2 工具用于兼容本机 Ubuntu 26.04 头文件。服务模板包含本机绝对路径，迁移时须修改。

Omni 权重固定在 `f01e6a23ac6066aa9eb622cf94b6259442e70ec2`，完整下载和 SHA-256 清单保存在 `deployment/fastvideo/model-download-manifest.json` 与 `model-verification.json`。预计算表约 300 MB，留在本机模型目录；SHA-256 为 `1acc433f4956f8b5b45e064f70c342e16b8bd7490b1d637cf21280474851cd1f`，元数据副本为 `adaln-table-metadata.json`。

AdaLN 修复从已存储的精确 timestep 投影中取子集，拒绝未知 timestep；不进行插值或修改权重。验收记录为 `deployment/fastvideo/adaln-verification-20261116.json`：9 项回归测试、400 项真实表投影核对，以及 API 和网页各一次参考图生成。

恢复 Omni 服务、启动、停止见 [FastH3 Omni 运维](fasth3-omni.md)。保持所有模型和网页服务禁用开机自启；下载和推理必须使用 `llm-lab/scripts/run_isolated.py`，保留 88 GiB 聚合内存上限、80 GiB 推理上限和独立内存看护。

本机 Git 提交可用于回滚配置。远端推送只在为本项目配置正确远端且认证可用后执行；本机提交不表示已经上传 GitHub。
