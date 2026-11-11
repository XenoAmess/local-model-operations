# CK3：三项有限纯源码 HTTP 审阅

本轮针对正式 Git 对象中的三个完整生产类及原测试，使用共享 DIRECT 调用器并行发出三项独立真实任务。三项均 HTTP200、完整 stop/DONE、合法 JSON，0length／传输错误／重试。峰值3路持续8.813972秒，首POST至末END11.568909秒；有效内容TTFT为1.5601363–2.5597015秒，输入16832／输出2369tokens，cached tokens未报告。

Defender 的五常量临时列表可作为同序五次 add 的局部源码候选继续审阅；owned TreeSet、比较器和最后顺序保持，尚无实现、动态频率或性能资格。Projected 的单元素比较虽有局部等价讨论，但后到 owner 明确它属于冻结 require 边界，归 NO-CODE-AUTH，不实施、不为此重发。Declaration 建议只把共享空 List.of() 改成 null，却虚构每次创建空 ArrayList／wrapper 的收益，建议拒绝。

完整响应已交规划岗。三个 CANDIDATE 标签不等于三个有效优化；源码采用0，新增编译、测试、测量和 Runtime 操作0。原测试只提供源码上下文，未新运行。源级候选、授权边界、实际分配和端到端收益分别验收；主持续目标仍 ACTIVE。

[实际请求成本、源身份与采用分级](2026-11-11-ck3-military-pure-source-http-scout.json)。
