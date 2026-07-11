# G04 关闭回执：采购理由、用户实际价值与卖点组合

## Objective

基于 G03 V4 context，实现已发布 M12D 采购理由到 M05C 用户购后实际价值、再到 M03B/M04C 卖点组合的可追溯关系层；实现标准 taxonomy 映射、直接用户证据与系统事实分离、正负/冲突/unknown、同句去重、同源同参合并、共线组合和值状态；不推测购买前心智，不构建反事实、选择贡献或 WTP。

## 前置输入

- G03 核心实现 commit：`b903c2a`；
- G03 closure commit：`7f8baf5`；
- G04 Goal thread：`019f4c6c-5a6b-7660-b5e7-593754bc6923`；
- G04 timer：`catforge-v4-g04-10`。

## 实际产物

- 扩展 `claim_value_pm_v4_schemas.py` 的 G04 typed contracts；
- 新增 `claim_value_pm_v4_service.py` 关系层；
- 新增 `test_claim_value_pm_v4_linkage.py`；
- `G04_progress.md`；
- 本关闭回执；
- `G04_artifact_manifest.json`。

未修改 repository/数据库/205、V2 registry 或 V2 路由，未启用 CLI/自然语言入口。

## 业务合同

1. relation 主键为 `battlefield_code + purchase_reason_code`，每个采购理由只有一条；
2. 一个理由关联多个价值主题时合并为 value combo，不重复主表行；
3. 采购理由只来自已发布 M12D，missing 或 weak-expression 不补写；
4. 用户实际价值只来自 M05C 购后体验，未观察时明确 `not_observed`；
5. 参数/卖点事实与用户体验状态分开，配置存在不等于用户价值已兑现；
6. 泛化好评不拆给亮度、分区、MiniLED 或芯片；
7. 正反体验并存为 `conflicted`；
8. 多成员共同变化时合并为 bundle 并标记 collinearity，不声明单项可独立量化；
9. 评论数量不生成价值权重、金额或购买贡献；
10. 版本冲突阻断 relation，但不删除已观察的用户体验事实。

## 测试结果

| 验证 | 结果 |
| --- | --- |
| G04 linkage tests | 12 passed |
| G03 + G04 + V2 sellpoint 定向回归 | 59 passed |
| G04 service coverage | 96% |
| G04 runtime schema vs G02 contract | exact match |
| Ruff | passed |
| py_compile | passed |
| `git diff --check` | passed |
| 65E7Q published anchors | weak anchors excluded；无评论 fixture 时不发明用户价值 |
| forbidden scope | 无反事实、WTP、价格建议或工作清单逻辑 |

## 已知边界

- G01 65E7Q 脱敏 fixture 未冻结原始 M05C atoms，真实用户体验回放留待 G09；
- business tier 无确定性档位时保持 unknown；
- 跨 SKU presence/tier 共线检验属于 G05；
- 两个既有 M12D 发布测试仍受工作区其他质量门禁改动影响，本 Goal 未修改或绕过。

## Commit

- G04 核心实现：`7cc39fa`；
- 本关闭回执、manifest 和完成状态：本文件所在的独立 closure commit。

## 下一 Goal 准入

`G05 allowed`。G05 只允许构造 base-value、same-value、stretch 候选、市场单元与可比性/隔离等级；不得提前计算选择贡献或 WTP。
