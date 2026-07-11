# V5-G07 关闭回执

## 结论

`PASSED — V5-G08 ALLOWED`。

V5 已具备面向产品经理的唯一用户价值账 DTO、四类载体和显式默认关闭入口；默认自然语言路由仍为 V2。

## 验收结果

- 第一屏固定输出 0—3 条证据门禁亮点、价格承接、销量承接、已有战场增强和真实新战场；
- 用户价值账按“战场 × 用户价值组合”组织，不按孤立参数罗列；
- 市场合成基线、高/低表现组合和目标差异进入同一市场参照；
- opportunity/user-observed 永远属于已有战场，unknown excluded 不冒充拓展；
- JSON、短答、Markdown、飞书卡片消费同一 result hash；
- 双链接为“查看用户选择对比”和“查看分析依据”；
- 产品经理载体无内部模块码、战场编码、英文状态、因果销量、个人最高接受价或泛化工作清单；
- CLI 和 orchestrator 双默认关闭门禁，未显式开启时数据库 session/context load 均为 0；
- 自然语言默认路由不进入 V5；
- G07 15 passed、V5 68 passed、V4 related 40 passed、analyst CLI 88 passed；
- overall coverage 92%、answer 85%、ruff/compileall passed；
- 主提交：`cad1bd48eae865111438c897884f2fd4cd94b19d`；
- database/205 writes：0/0。

## G08 入口

G08 先做本地完整门禁和不可变 RC，再在 205 以默认关闭方式部署；必须记录真数候选覆盖、合成 donor、query count、性能、两次重跑 hash、报告/卡片 readback、V2/V4 回归和回滚证据。
