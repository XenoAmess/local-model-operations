# Local Model Operations

本地模型的使用方式、执行规范、能力边界探索和实际经验的独立维护仓库。内容从 [ck3_eternal_recurrence](https://github.com/XenoAmess/ck3_eternal_recurrence) 的实际运营资料抽取；业务源码、运行账本和大证据继续由原项目保管。

## 快速使用

脚本仅依赖 Python 标准库，需要 Python 3.10+；当前离线验证环境为 Windows / Python 3.13。

```sh
git clone https://github.com/XenoAmess/local-model-operations.git
cd local-model-operations
python -X utf8 scripts/call.py examples/task.json task-001 --machine-id workstation-a --owner worker-a
```

这条命令会发送真实模型请求。调度实际工作时，将示例的完整源码和任务替换成尚未完成的真实需求。每个任务使用唯一输出目录；默认写入当前目录下已忽略的 `.local-model-evidence/<task-id>/`，不自动执行模型生成的代码或外部业务动作。

共享配置是 [config/executor.json](config/executor.json)：`http://192.168.1.11:8080/v1`、`qwen38-coder`、无需密钥。该地址需要执行机器能访问指定局域网。不同机器设置自己的身份和证据目录；可通过 `--config` 或 `LOCAL_MODEL_CONFIG` 使用显式本机配置，不自动尝试旧地址。

完整参数和跨机器示例见[使用指南](docs/usage.md)。

## 文档入口

| 内容 | 入口 |
| --- | --- |
| worker 协作、单主线、及时提交推送 | [AGENTS.md](AGENTS.md) |
| 调用方式、配置覆盖、机器身份和输出 | [使用指南](docs/usage.md) |
| 真实并发、SSE、退避重试和证据 | [并发与重试规范](docs/concurrency-and-retries.md) |
| 能力范围、失败分类和探索方法 | [能力边界](docs/capability-boundaries.md) |
| 已验证经验、反例和适用限制 | [经验记录](docs/experience-log.md) |
| 迁移来源、精确版本和 SHA-256 | [来源记录](docs/source-origins.md) |
| 原始 worker 指南及两份探索档案 | [历史快照](docs/history/README.md) |

当前规则与冻结历史分别维护。旧地址、机器目录和项目权限仅保留其历史含义，不是新 worker 的启动要求。

## 验证

```sh
python -X utf8 -m unittest discover -s tests -v
```

当前 15 项离线 HTTP/SSE mock 测试覆盖配置与相对路径、有效内容 TTFT、usage 缺失、截流丢弃与整次重试、末尾 JSON/UTF-8 截断、六次尝试边界、永久错误及输出目录防覆盖。测试不向指定局域网服务发请求，不证明模型能力或真实业务完成。调用器总耗时检查是行间检查，不是硬总截止；详细限制见使用指南。

另有2026-11-01在 Windows / Python3.13.2、当前指定服务上的[一次真实业务 SSE 调用摘要](docs/evidence/2026-11-01-windows-service-call.json)：HTTP200、stop、SSE完成且保留usage。它补充离线 mock，限于这一环境和请求；不证明其它平台或服务、业务答复正确性及源码采用，详见[经验记录](docs/experience-log.md)。

## 协作方式

唯一长期分支是 `main`。按文件分工并行处理源码、模型请求和审阅；Git 写入由同一时刻唯一写者串行执行。每完成一个可审阅单元并做相称检查，就及时提交、推送 `origin/main`，不积压到整批任务结束。

源码候选、HTTP 完成、软件验证、正式采用和真实业务结果分别记录。能力结论必须标明实际输入、提示程度、owner 修正、验证范围及尚未知部分。密钥、本机配置、原始请求与大证据不入仓库。
