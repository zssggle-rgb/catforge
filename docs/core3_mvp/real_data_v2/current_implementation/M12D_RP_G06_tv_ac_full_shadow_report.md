# M12D-RP-G06 TV/AC 全量影子与发布门槛复算

- 生成时间：`2026-07-11T18:22:07.461286+00:00`
- 性质：205 当前发布范围全量只读重建；未写表、未切 current、未运行竞品智能体。

## TV

- SKU：`377`；锚点：`3542`。
- 状态：`{"ready": 335, "ready_limited": 13, "weak_expression_only": 29}`；消费能力：`{"facts_only": 32, "limited": 10, "strong": 335}`。
- 新增核心：`483` 条 / `315` SKU；删除核心：`435` 条 / `241` SKU。
- 新增核心业务审计失败：`0`；压力来源失败：`0`；压力误删成立理由：`0`；proposition 误入核心：`0`。
- 与 G04 成立度/压力漂移：`0`；未影响回归：`20` SKU。
- 发布质量：`ready`；失败门槛：`[]`。
- 重点样本：`10`，通过：`10`。
- QF15A 139：复核 `139`；形成核心 `107`；仍无核心 `32`。
- 检查项：`{"full_scope_complete": true, "new_core_business_audit": true, "pressure_sources_traceable": true, "pressure_does_not_delete_established_reason": true, "proposition_never_core": true, "g04_deterministic": true, "unaffected_regression_20": true, "focus_complete_and_passed": true, "qf15a_139_complete": true, "qf15a_expected_distribution": true, "tv_65e7q_proposition_boundary": true, "release_not_blocked": true}`。

## AC

- SKU：`155`；锚点：`1879`。
- 状态：`{"ready": 143, "ready_limited": 1, "weak_expression_only": 11}`；消费能力：`{"facts_only": 12, "strong": 143}`。
- 新增核心：`364` 条 / `123` SKU；删除核心：`103` 条 / `20` SKU。
- 新增核心业务审计失败：`0`；压力来源失败：`0`；压力误删成立理由：`0`；proposition 误入核心：`0`。
- 与 G04 成立度/压力漂移：`0`；未影响回归：`20` SKU。
- 发布质量：`ready`；失败门槛：`[]`。
- 重点样本：`18`，通过：`18`。
- 检查项：`{"full_scope_complete": true, "new_core_business_audit": true, "pressure_sources_traceable": true, "pressure_does_not_delete_established_reason": true, "proposition_never_core": true, "g04_deterministic": true, "unaffected_regression_20": true, "focus_complete_and_passed": true, "qf15a_139_complete": true, "qf15a_expected_distribution": true, "release_not_blocked": true}`。

## 总体验收

- 三张 M12D 表前后快照一致：`True`。
- G06：`通过`。
- 未通过项：`[]`。
