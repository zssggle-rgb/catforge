# G07 产品经理业务答案、报告与显式入口进度

- Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`
- Goal 状态：`completed`
- 定时器：`catforge-v4-g07-10`
- 前置 G06 artifact commit：`ce1b4eb`
- 前置 G06 closure commit：`c3b52b3`
- 允许修改：V4 schemas/answer、薄编排、CLI、G07 tests/fixture/回执
- 禁止事项：数据库/205 写入、默认自然语言路由切换、renderer 重新计算、自动产品动作

## 当前门禁

| 门禁 | 状态 |
| --- | --- |
| 复核 G02 报告合同和七列主表 | completed |
| 复核 V2 answer/Feishu/CLI 三类模式 | completed |
| ProductValueStructureRow/Report 合同 | completed |
| 同源业务 DTO builder | completed |
| 固定七列主表与卖点组合下钻 | completed |
| 短答/Markdown/飞书同源渲染 | completed |
| 主表禁止词与无工作清单 | completed |
| 双链接载荷 | completed |
| 显式 CLI/default-off flag | completed |
| 65E7Q/边界样例与 V2 回归 | completed |

## 硬边界

1. 主表只回答产品经理的业务问题，不展示内部模块、量化等级、隔离等级、SQL 或证据 ID；
2. “用户价值是否成立”和“价值能否量化”分开，无法量化不能写成零价值；
3. 不推测购买前宣传心智，只陈述当前数据支持的购后实际价值；
4. 不生成涨降价、增减配、验证清单或通用工作清单；
5. JSON、短答、Markdown、飞书卡片消费同一个报告对象，renderer 不得计算选择或 WTP；
6. 内部审计只允许在 QA appendix，不能泄漏到产品经理主表；
7. `查看用户选择对比` 与 `查看分析依据` 分开传递；
8. V4 只能由显式命令和显式 flag 启用，默认自然语言仍走 V2；
9. G07 不修改数据库，不连接或部署 205。

## 实现结果

1. 新增 `ProductValueStructureRow` 与 `SkuProductValueRealizationReport`，字段和 required 集合与 G02 frozen contract 精确一致；
2. 新增唯一业务 DTO builder：每行固定为战场、采购理由、用户实际价值、卖点组合、反事实、选择/价格兑现、产品角色；
3. 同一报告对象生成 JSON、短答、七列 Markdown 主表、下钻和飞书卡片，delivery URL 不进入结果 hash；
4. 主表只展示中文业务结论；内部量化等级、隔离等级、模块码、relation hash 和 source authority 只保留在 QA appendix；
5. renderer 只做字段翻译与排版，不调用 pair curve、选择或 WTP 函数；
6. 无法量化明确写成市场/对照边界，不写成没有价值；负向体验与事实版本冲突分开呈现；
7. 支持 `查看用户选择对比` 与 `查看分析依据` 两个独立链接，短答、Markdown 和卡片保持一致；
8. 新增显式命令 `sellpoint-value-pm-v4 --enable-v4`；CLI 和 SOP 两层都默认关闭，未显式启用时在加载上下文前停止；
9. 自然语言路由未切到 V4，旧 V2 命令、答案和飞书发送路径保持不变；
10. 65E7Q 脱敏 fixture 因没有原始评论/逐周 cell 且版本冲突，报告显示 partial、用户价值未观察、金额为空；
11. 未生成产品动作、工作清单或购买前心智；未修改数据库、205 或默认线上路由。

## 验证结果

| 验证 | 结果 |
| --- | --- |
| G07 answer/CLI tests | 17 passed |
| G03-G07 + V2 answer/service 定向回归 | 96 passed |
| 既有 analyst CLI 全量回归 | 88 passed |
| 本 Goal 总回归 | 184 passed |
| V4 answer coverage | 93% |
| G07 runtime schema vs G02 contract | exact match |
| 七列主表禁止词扫描 | passed |
| JSON/短答/Markdown/飞书同源 | result hash 与业务行一致 |
| 65E7Q fixture | partial；value not observed；WTP null |
| Ruff / py_compile / diff check | passed |

## 下一步

G07 已完成，允许进入 G08。本地综合验收将覆盖完整链路、性能/查询预算、需求追溯、fixture hash、跨载体一致性，以及方法、工程和产品经理业务语言的独立评审；发现核心合同问题时另建修复 Goal。
