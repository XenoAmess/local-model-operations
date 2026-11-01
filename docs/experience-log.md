# 可复用经验

整理日期：2026-11-01。这里保留会改变操作方法的实测与勘误；完整探索过程见 [历史档案](history/README.md)，采用口径见 [能力边界](capability-boundaries.md)。模型案例使用服务别名 `qwen38-coder`，权重、量化和服务构建版本未固定；性能诊断和调用器测试另列，不冒充模型推理实测。

## 请求合同先核实际发送内容

| 日期与观察 | 可复用操作 | 限制与来源 |
| --- | --- | --- |
| 2026-10-31整理：provider 曾因缺少 tool parser 拒绝自动或强制工具选择 | 使用已获支持的普通候选接口；工具循环需要另外实现和验证 | 文本 SSE 成功不授文件读取、测试执行或业务动作能力。[原指南](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L1-L47) |
| 2026-10-31整理：spec 写了 `frequency_penalty=0.3`，实际 REQUEST 没有该键 | 参数实验必须审实际 payload；小 spec 白名单外的参数通过完整请求对象提供 | 该单不能称已执行的0.3实验；服务默认及效果未知，未为补统计重发。[原勘误](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L87-L89) |
| 2026-10-31整理：同三消息的 thinking false / true 请求同时改变了输出预算，SSE 仅见 role / content | 保存实际 flag、预算、并发环境与可见字段；模式实验先定义可观察证据 | 未见 reasoning 不证明内部没有推理；耗时差不是模式或缓存因果，不能补称严格 A/B。[实际对照](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L50-L54) |
| 2026-10-31整理：输出示例中的 `completeJava` / `completecpp` 被逐字回显，无实现 | 只给一种活动输出合同，用文字说明字段装完整源码，不给可照抄占位值 | 记录 owner 提示成本，也保留回答未完成的事实；其它独立语义失败不因此抹去。[占位回显原件说明](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L121-L129) |

长输入不自动需要长回答。曾有完整整类输出重复正文直到 length，改成真正尚未完成的方法或有限 old/new edits 才能控制产物范围；只能采用完整终态的目标单位，不能续拼截断文本。[输出范围与类型角色](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L164-L182)

## 声明、预算与状态必须闭合到真实消费者

2026-11-01 的继承闭包案例中，实际前缀漏祖接口，owner 又误写“三方法”；模型按这个合同作答后，首编发现第四个方法缺失，独立源审也曾漏掉。应逐角色、逐纠正轮沿 `extends` / `implements` 找到直接声明者，包含所有成员及名义返回类型，不能只看文件数或 fully qualified 名称。后续 owner 补实现的成本归 owner；输入已补齐后的模型 hunk 则独立署名。[公开继承案例](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L262-L266)

2026-11-01 新增预算案例：caller 将64MiB作为预算参数传给只允许最大8MiB的 callee。callee 先校验参数，小包尚未进入实际大小校验就被拒绝。模型的17文件前缀仍漏了这个 callee，多个 owner 静态审阅和 strict / DTO 验证也未发现问题。迁移后的检查步骤为：

1. 将真实 caller、callee 与 MAX 常量直接声明放进本角色的实际请求。
2. 分别验证参数是否在 callee 的允许范围，以及实际 body 字节是否不超过获准预算。
3. 除纯 DTO 外，通过真实公开捕获入口做一条窄回归，保留原参数拒绝与输入缺口。

这不支持放大所有默认限制、跳过证据校验或宣称性能收益。来源为执行者保管的 `PORTABLE-BUDGET-RULE220.json` 独立摘要，原件 SHA 与公开范围见 [来源说明](source-origins.md)。

同日另一类源审教训是多个不可变 V 快照不会自动共享后续回调更新：必须显式传递实际返回的当前 V / N / DF，不能把入口值当作回调后的已知值。有限投影中的未知字段不填0；没有写入、没有使用返回值，也不能据此删除实际可观察的内存读写。`AND [mem],0` 包含读取和写入，不能任意缩成只写0。[当前状态](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L268-L272)、[可观察的读改写](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L248-L252)

## 先审 fixture，再用它评价候选

准确数据形状不能替代有符号比较、字节宽度、物理栈位置和分支可达性。先从原始合同冻结 oracle，再读新目标输出；若向模型提供了逐步期待，署名为“owner oracle → 模型编码”。检查 literal 是十六进制值还是十进制值、宽度单位是 bit 还是 byte，核完整调用帧和 effects 在同一 RAM 上消费一次。不要让实现和测试共享同一错误推导后相互证明。

2026-11-01 的预算回归又暴露了 fixture 的前置合同：原本要复现总包超过1MiB，旧实现却先拒绝了非整数 JSON 值；修正后，单个巨大字符串又先被32,768码点的文本限制拒绝。这两次非零退出都没有到达所称的总字节预算错误。应沿实际委托校验核对合法值域，再用合法短值聚合跨越总量边界，检查真实异常及到达位置；更宽的文本或数字域另作场景。保留原 oracle、原失败与修正依据，不能把任意异常当作指定负例通过。

修正后的同一纯数据 Probe 在冻结旧类上准确触发总预算错误，在新类上通过78项断言：小包773字节、合法短串聚合的大包1,101,610字节、中间包200,935字节，另核单个巨大字符串及负零完整保留。五次 Probe 编译和前两次错误值域的 JVM 失败均保留，未重编生产类；这不是一次原样模型产物通过，也不授真实捕获链、线上或性能结论。模型可见候选生产源码，不能署名为盲生产见证。依据为执行者保管的 `PORTABLE-FIXTURE-BOUNDARIES220.json`，见[来源说明](source-origins.md)。

整数值的比较也要服从实际合同：Jackson 的 primitive int / long 节点与 BigInteger 节点可能表达同一数学整数，却不满足节点存储类型的 `equals`。要求 typed JSON 整数值相等时，先将两侧投影为同一值表示；要求原始字节或数字 token 不变时，仍分别检查，不能用正规化抹去负零或 token 差异。

历史负例也限制“看起来通过”的含义：`byte[].equals` 是对象身份；typed JSON 值相等与原始字节不可变是不同合同；109个 checks 可能只含27个数据 fixture及一个结构断言。正链后追加非法 UTF-8 / duplicate-key 负例，曾找到4个公开异常映射回归。通过时写真实 case、checks、旧红与失败项重跑范围，不能把不同 JVM 的结果改成一次全绿。[实际负合同传播](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-capability-boundary-2026-10-28.md#L21-L25)、[比较与独立进程问题](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L193-L206)

## 运营证据保留时间与字节口径

一次历史客户端峰14只持续3.540034秒，对应十分钟平均2.0054；它不能替代持续达到并发目标的证据。请求真正结束但迟读、外目录未纳索引、旧 attempt 无终态，都应核目录与截止点后另附重建，不能靠中央表更新时刻判断真实活性。具体区间、峰持续、服务 metrics 与重试口径见 [并发页](concurrency-and-retries.md)。

错误封包也独立计成本：CRLF → LF、缺 EOF、原始 Git blob、实际 prompt 归一文本的哈希分别保存，不能用一个哈希冒充另一个字节对象。已冻结文件被误覆盖时，恢复内容不等于恢复丢失的原始时间戳或原件；保事故、恢复方法与未知。后到回执另附，不改旧“尚未验证”的快照。[换行封包经验](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L164-L182)、[冻结记录与覆盖事故](https://github.com/XenoAmess/ck3_eternal_recurrence/blob/0958f36720a2cf75d1e3ede84ff3ae7fa730d91d/docs/local-model-worker-guide.md#L220-L224)

## 2026-11-01：JFR 单个异常权重的敏感度

一次60秒 JFR 记录的数据丢失为0。独立 allocation 摘要含16674个 `ObjectAllocationSample`；其中2026-11-01 05:54:14.780087 UTC 的一个 `boolean[]` 样本 reported weight 为555943805096，占全部采样权重的93.142%。同一 digest / regex 栈另外22个样本的权重合计103069184。这个极端权重必须单列，不能解释为一个数组的实际大小，也不能写成该方法占93% CPU或精确总分配量。

原始样本与完整聚合都保留，再另算排除最大1项的敏感度，明确改变后的分母。用样本数、权重分布、中位数、分位数和其它栈交叉检查；排除一项用于检验排序稳健性，不证明该样本无效。CPU 采样、allocation weight、GC pause 与端到端墙钟是不同指标。

同一记录中122个顶层 pause 事件的区间并集为1.589672秒，约占60秒的2.64945%；98个 GC 事件的总 duration 不能当作停顿。这里 pause raw sum 恰与 union 相等，处理其它记录时仍需显式去重重叠区间。任何性能修改仍需结合真实热路径、等价行为与受控后测；一条样本或候选叙述不授速度提升。

本项由执行者保管的 `ROOT-SHORT219`、`GC-ALLOCATION-SUMMARY219` 与 `WEIGHT-SENSITIVITY219` 小摘要交叉核对；本仓库未上传原始 JFR 或数百MB过滤数据，也没有伪造公开下载链接。摘要 SHA 和来源限制见 [来源说明](source-origins.md)。这是诊断方法经验，不是模型生成正确性实验。

## 2026-11-01：便携调用器迁移的实际验证

本仓库调用器迁移由 owner 实现。一次独立旧源审计请求完整 HTTP200/stop，却错称 length 会走传输重试，并错称6次尝试会越界读取第6个退避项；这两项均由实际控制流和本地 HTTP mock 否定，模型整审计与源码片段采用均为0。不能因为审计响应完整就授正确性，也不能把 owner 的迁移实现算作模型整份代码。

初版13项本地 mock 通过后，Root 继续源审发现无LF尾行中的截断 JSON / UTF-8 被当成一般解析失败。后续明确修订为不完整响应，保本次 partial，下一次从完整请求重发；完整LF畸形 JSON 仍不重试。修订03实际15项通过，独立 JSON / UTF-8 断流子场景核下一候选全来自第二次响应，原13项记录未回写。[已发表调用器与测试版本](https://github.com/XenoAmess/local-model-operations/commit/aa12e525d5f6cb842cae71dabe33071a91794933)

验证范围为 Windows Python3.13、标准库本地 HTTP / SSE mock；迁移验证没有访问真实模型服务或业务系统，没有 POSIX 实跑。当前900秒检查只发生在响应行之间，停止文件也不即时打断睡眠或在途 HTTP；未增加 watchdog。保留这些限制比把一次绿写成完整跨平台、实时或服务兼容性结论更有用。
