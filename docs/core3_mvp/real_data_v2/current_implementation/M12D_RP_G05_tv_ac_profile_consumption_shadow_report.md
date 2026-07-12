# M12D-RP-G05 TV/AC 画像与按 SKU 消费影子测算

- 生成时间：`2026-07-11T17:44:26.167637+00:00`
- 证据输入：复用 G04 全量已验收锚点；205 数据库仅用于读取当前发布基线和写入保护快照。
- 角色口径：成立状态决定角色；购买阻力不删除已成立理由。

## TV

- 当前版本质量：`legacy_unassessed`；SKU：`377`。
- 新 SKU 状态：`{"ready": 335, "ready_limited": 13, "weak_expression_only": 29}`。
- 消费能力：`{"facts_only": 32, "limited": 10, "strong": 335}`。
- 状态或核心理由迁移：`360` SKU。
- 状态迁移：`{"ready_degraded->ready": 335, "ready_degraded->ready_limited": 12, "ready_degraded->weak_expression_only": 12, "weak_expression_only->ready_limited": 1}`；核心条数变化：`{"-1": 111, "-2": 27, "-3": 7, "-4": 1, "0": 80, "1": 61, "2": 42, "3": 31}`。
- 状态与核心完全不变：`17` SKU；非目标字段回归样本：`20`。
- 入选核心且带高/严重压力：`{"high": 337}`；因普通压力丢失核心资格：`0`。
- proposition 误入核心：`0`；低于 7 分核心：`0`。

## AC

- 当前版本质量：`legacy_unassessed`；SKU：`155`。
- 新 SKU 状态：`{"ready": 143, "ready_limited": 1, "weak_expression_only": 11}`。
- 消费能力：`{"facts_only": 12, "strong": 143}`。
- 状态或核心理由迁移：`148` SKU。
- 状态迁移：`{"ready_degraded->ready": 45, "ready_degraded->ready_limited": 1, "ready_degraded->weak_expression_only": 4, "review_required->ready": 98}`；核心条数变化：`{"-4": 4, "-5": 9, "-6": 7, "0": 5, "1": 1, "2": 3, "3": 119}`。
- 状态与核心完全不变：`7` SKU；非目标字段回归样本：`20`。
- 入选核心且带高/严重压力：`{"high": 257}`；因普通压力丢失核心资格：`0`。
- proposition 误入核心：`0`；低于 7 分核心：`0`。

## 验收

- 三张 M12D 表前后快照一致：`True`。
- G05 验收：`通过`。
- 未通过项：`[]`。
