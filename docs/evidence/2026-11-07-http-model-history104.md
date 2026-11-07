# HTTP 候选：模型输入历史去重的字节身份修复（P104）

case_id：`HTTP-JAVA-MODEL-HISTORY-BYTE-IDENTITY-104`；mode_id：`http-candidate`。时间统一为2026-11-07 UTC。请求服务于当时尚未完成的真实Java自动游玩输入修复，不是连通探针，也没有为记录案例增加HTTP。原始请求、SSE、源码与编测材料留执行机器；公开可核元数据见[脱敏摘要](2026-11-07-http-model-history104.json)。

三个模型输入消费者原来根据JSON结构相等，省略snapshot中的重复历史。对象结构相等忽略成员顺序，但实际wire编码保留成员顺序，因此结构相等不足以证明字节身份。owner已定位这三个调用点、给出成员顺序反例并要求固定codec字节相等；后续反馈又明确提示`Arrays.equals`、64 MiB材料预算和typed数组复制。这是强指导的实现任务，不是模型独立发现缺陷或设计方案。`1.0`与`1.00`在所供原数字节点上已经按原token严格比较，不是本案观察到的结构比较错误，只作为保真回归域。

两轮都提供5份完整源码，稳定源码消息为114491个UTF-8字节。实际REQUEST为system/user/user、`qwen38-coder`、temperature0、thinking=false、JSON object、SSE/include_usage，输出预算分别2600与2300。每轮1 POST/1 END/0传输重试，均HTTP200/stop/DONE/完整JSON，顺序执行且没有第三轮。

| 轮次 | POST_BEGIN → END（UTC） | headers秒 | 有效内容TTFT秒 | 总秒 | reported输入/输出tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | 14:24:26.005541 → 14:24:36.230524 | 3.4495859 | 3.4509824 | 10.2249099 | 25003 / 1110 |
| 2 | 14:26:19.267927 → 14:26:26.868143 | 0.9514751 | 0.9523932 | 7.6001316 | 25199 / 1131 |

两轮cached tokens均未报告，实际socket peer为UNKNOWN；别名没有固定权重、量化或服务构建版本，不能从TTFT差值归因缓存。OpenCode本轮没有原生工具任务，客户端每日维护与HTTP生成分开记录。

首稿使用`byte[].equals`比较新生成的数组，得到的是引用相等；又误选256 MiB Driver预算，并把不兼容的typed列表直接传入数组值构造器。该完整候选源审拒收，没有编译它，也不把源审类型错误记作javac失败。第二稿改用元素字节比较、64 MiB预算与typed复制；这些核心方向部分采用，三个最终修改块仍由owner调整，没有完整方法或完整hunk原样采用，也不按相同行数计算贡献率。

第二稿新增三个吞掉运行期异常的catch，owner删除，保留既有诊断及外层fallback。compact分支还选用了32层的旧codec，owner与独立源审改为实际wire使用的64层固定codec，不修改codec本身。上述调整、类型和装配成本属于owner，后续通过不能追认模型原稿。caller终态原件保留当时“未审／adopted=false”的自动字段；owner后到partial决定单独记录，不回写原件，也不把自动默认字段误作最终全拒收。

人工codec转换曾多写一个右括号：首个真实2 TU编译exit1、0 class、6.5569381秒，于14:32:26.999206资源关闭。该RED是owner整合错误，独立保留，不能归入模型的三个首稿错误；更早的临时源码未编译。修正只删除该多余括号，随后同一最终组合的2生产TU编译exit0、5 class、7.2270825秒；新Test 1 TU编译exit0、2 class、4.8803968秒，既有fixture复用。

唯一新Test的三个DATA方法在同一JVM实际3P／0F／0E／0skip，exit0、5.4034823秒：核实际generic／Council／compact payload的成员顺序差异保留、精确重复才省略及合法深层历史不获得更窄codec限制。实际XML为42935 B、SHA-256 `7b7b8202f20d6f2c2012b17fb9bf2fac677b05d78fded9b90837a4aceb9c5b84`；资源于14:38:41.209503关闭。旧绿编译和旧方法RUN均0。公开摘要固定最终源码、原RED、各阶段ACTUAL／关闭回执和薄资格pin；这些通过只授owner修正后的混合源码及有限DATA，不授模型原稿原样通过、运行采用或游戏收益。

14:40:37.6341069Z业务owner正式发表回执确认commit `c856485023f2daeb85fd287eca7781f235e5398e`、remote master一致及clean切点。生产源码和新DATA正式发布；Runtime采用仍false，没有新的确认保存日或性能信用。这里只读核该具名回执，未为共享文档查询或启动业务。

首POST_BEGIN至第二END为120.862602秒，含两轮间的反馈和其它可能工作，不是人工活跃工时。准备、审阅、纠错、协调、测试与发布缺少完整独立phase记录时写unknown；不从HTTP、编译时间或源码最终通过推算净节省。下一真实任务继续逐消费者核对实际wire codec、调用顺序及原fallback，不为改写采用结论重投本案，也不从两轮表现推永久能力上限或HTTP/OpenCode模式优劣。
