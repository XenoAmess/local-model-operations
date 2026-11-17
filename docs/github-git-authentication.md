# 本机 GitHub 推送认证排障

2026-11-17，执行机器为当前 Ubuntu 主机。目标仓库为 `https://github.com/XenoAmess/local-model-operations.git`，主分支为 `main`。

## 恢复验收

用户完成设备授权后，GitHub CLI 已登录 `XenoAmess`，令牌保存在系统 keyring；仓库 API 确认该账号有 push 权限。已配置持久的 GitHub credential helper 为 `~/.local/bin/gh auth git-credential`，后续 Git 推送通过该助手取得凭据。

远端有其它客户端同时提交，首次同步后的推送被 fast-forward 检查拒绝；重新 fetch、检查远端仅涉及其它业务文档后，安全 rebase 并成功推送。研究、配置、补丁、实测证据及本文的首次发布提交为 `2199dd13c72cd5463db263e03e009e2d70120e4d`，实际 `git ls-remote` 已核对远端 SHA。没有强推、覆盖他人提交或调整模型服务。

以下为修复前的历史证据和今后的恢复流程，不表示当前仍缺少认证。

## 实际故障与证据

- 当前工作副本于当天 14:25 从公开 HTTPS 地址克隆；本机 `origin/main` reflog 记录的是 fetch，没有成功 push 记录。读取公开仓库成功不能证明写入认证可用。
- 实际推送访问 `info/refs?service=git-receive-pack`，网络代理 CONNECT 与 TLS 成功，GitHub 返回 `HTTP/2 401` 并要求认证。
- 当前工作副本及用户／系统配置没有 credential helper；没有 GitHub CLI 登录文件、GitHub token 环境变量或可用的 HTTPS 凭据文件。
- SSH agent 没有身份，用户 SSH 目录也没有出站私钥；桌面 Secret Service 的 session／login 集合均未锁定，但没有凭据条目。
- 普通尝试报 `unable to get password from user`；屏蔽桌面 askpass 后，明确报 `could not read Username for 'https://github.com': terminal prompts disabled`。这两条来自同一个未提供凭据的认证缺口，不是 Git 提交、模型服务或显卡故障。

以上证据说明当前会话没有写入认证，不能证明旧令牌过期、凭据曾被删除，或此前成功推送发生在哪个环境。不能将“以前能推”的原因擅自归为过期或远端权限撤销。

排障只查看了相关配置、身份列表和 keyring 元数据；没有导出凭据、读取浏览器会话或把令牌写入仓库。代理设置保持原状，视频服务与模型配置没有改动。

## 恢复准备与正常流程

本机原先没有 `gh`。已从 Ubuntu 已配置仓库获取 GitHub CLI `2.46.0-4`，解包到用户目录，并建立 `~/.local/bin/gh` 入口，不需要 sudo，也没有安装到模型虚拟环境。

```bash
# 首次恢复认证需要账号持有人在 GitHub 网页完成设备授权。
~/.local/bin/gh auth login --hostname github.com --git-protocol https --web

# 授权成功后配置 GitHub 凭据助手；不重复索取或复制令牌。
~/.local/bin/gh auth setup-git --hostname github.com

cd /home/ubuntu/workspace/local-model-operations
git fetch origin main
git rebase origin/main
git push origin main
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

设备验证码只在当次登录会话使用，不保存到文档。登录与恢复步骤遵循 [GitHub CLI auth login](https://cli.github.com/manual/gh_auth_login) 和 [auth setup-git](https://cli.github.com/manual/gh_auth_setup-git)。认证后仍须核对实际账户与仓库写权限；命令准备完成不等于授权或推送成功。

同步前保留工作区实际改动，Git 写入由唯一 owner 串行执行；只解决本次拥有文件的冲突，不强推、不覆盖远端其它人的提交。最终以 push 成功及远端主线包含本次研究提交为发布验收。
