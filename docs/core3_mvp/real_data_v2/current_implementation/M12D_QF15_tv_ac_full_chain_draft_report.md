# M12D-QF-15 TV/AC 全链路 Draft 重跑与验收

- 生成时间：`2026-07-11T13:43:14.702843+00:00`
- 全链路执行一致性：`True`
- 发布质量门槛：`False`
- 调度决定：`stop_before_qf16`

## 1. 模块重跑

| 模块 | 业务摘要稳定 | 与批准结果完全一致 | 仅 lineage digest 刷新 | 下游守卫 |
| --- | --- | --- | --- | --- |
| M03B | True | True | False | True |
| M04C | True | True | False | True |
| M05C | True | True | False | True |
| M07 | True | True | False | True |
| M09C | True | False | True | True |
| M10C | True | False | True | True |
| M11C | True | False | True | True |
| M12C | True | True | False | True |

### M07 运行恢复

- 首次退出：`137`，阶段：`post_write_full_capture`。
- 根因：后置验收把约 140 万市场池成员再次整体载入内存，触发容器 OOM。
- 恢复：未重复写 draft；使用批准影子收据执行 validate-persisted-only 紧凑校验。
- 紧凑校验：`True`。

## 2. 双品类发布质量

| 品类 | SKU | ready | limited | weak | 无核心 | ready率 | ready+limited率 | 无核心率 | 发布质量 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TV | 377 | 238 | 94 | 45 | 139 | 0.6313 | 0.8806 | 0.3687 | limited |
| AC | 155 | 130 | 23 | 2 | 25 | 0.8387 | 0.9871 | 0.1613 | limited |

### TV 未通过项

- 发布失败项：`['ready_rate', 'ready_or_limited_rate', 'core_payment_missing_rate']`
- 无核心归因：`{'all_anchor_evidence_weak_or_insufficient': 20, 'price_value_core_evidence_missing': 92, 'risk_drag_present': 32, 'supporting_evidence_below_core_gate': 16}`
- 弱画像归因：`{'all_anchor_evidence_weak_or_insufficient': 20, 'price_value_core_evidence_missing': 28, 'risk_drag_present': 12, 'supporting_evidence_below_core_gate': 3}`
- 价格价值门槛观察：`239`；误升核心：`0`

### AC 未通过项

- 发布失败项：`['ready_rate', 'core_payment_missing_rate']`
- 无核心归因：`{'ac_claim_value_risk_role_dominant': 11, 'price_value_core_evidence_missing': 14, 'risk_drag_present': 3, 'weak_expression_role_cap_present': 11}`
- 弱画像归因：`{'ac_claim_value_risk_role_dominant': 1, 'price_value_core_evidence_missing': 1}`
- 价格价值门槛观察：`46`；误升核心：`0`

## 3. 结论

- 全链路重跑一致，但 TV/AC 发布质量均为 limited；按 QF15 验收契约停在 QF16 前。
- M12D 重跑前后业务结果一致，当前发布画像/锚点/版本未变化。
- 未降低门槛、未加入白名单、未发布 current、未运行竞品智能体。
