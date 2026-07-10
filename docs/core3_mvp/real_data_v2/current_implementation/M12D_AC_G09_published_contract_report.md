# AC-M12D-G09 发布版本与下游契约冻结报告

- 生成时间 UTC：2026-07-08T15:37:02.392614+00:00
- 项目：d8d2245b-358b-4a64-95cc-9d7f2341bd26 / AC
- 批次：m00_20260624000202_1150a669
- 版本：m12d_ac_purchase_reason_profile_v0_1_draft
- 发布模式：publish
- 版本状态：published / current=True
- Profile：155/155 已发布 current
- Anchor：1879/1879 已发布 current

## 发布质量口径

- 发布决策：publish_current_with_degraded_consumption_contract
- 发布说明：发布为 current 仅表示下游可以读取冻结契约；低置信、需复核或缺核心理由的 SKU 必须以 published_degraded 降级消费，不得作为无条件强替代结论。
- 需复核 SKU：155
- 低置信 SKU：136
- 核心成交理由缺失 SKU：136

## 下游读取契约

- 读取键：`category_code + project_id + batch_id + m12d_profile_version + sku_code`
- 目标 SKU `not_found` 或 `published_unusable`：阻断强排序，不临时生成成交理由。
- 候选 SKU `not_found` 或 `published_unusable`：退出强替代判断或退出 Top 3。
- `published_degraded`：可降级消费，但必须展示置信度和降级原因。
- 下游不得修改 M12D 原始锚点角色。

## Fixture 样本

| SKU | 产品 | 状态 | 下游动作 | 置信度 | 核心锚点 | 降级原因 |
| --- | --- | --- | --- | ---: | --- | --- |
| AC00026378 | 小米 KFR-26GW/V1A1 | published_degraded | degraded_pair_scoring | 0.5000 | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、low_price_core_ac_experience_intact、small_room_installation_fit、smart_remote_control_less_friction | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| AC00032338 | 格力 KFR-35GW/(35551)FNHAA-B1 | published_degraded | degraded_pair_scoring | 0.5000 | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、cooling_heating_performance_justifies_price、long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、low_price_core_ac_experience_intact、small_room_installation_fit、smart_remote_control_less_friction | review_required、profile_status_ready_degraded、missing_or_partial_inputs |
| AC00028640 | 小米 KFR-72LW/N1A1 | published_degraded | degraded_pair_scoring | 0.3000 | - | review_required、profile_status_ready_degraded、low_profile_confidence、core_payment_missing、missing_or_partial_inputs |
| AC00028642 | 小米 KFR-35GW/N1A1 | published_degraded | degraded_pair_scoring | 0.0500 | - | review_required、profile_status_review_required、low_profile_confidence、core_payment_missing、risk_drag_anchor_present、missing_or_partial_inputs |

## 缺失/未发布 Fixture

- 缺失 SKU：not_found / block_target_or_drop_candidate
- 未发布版本：not_found / block_target_or_drop_candidate

## 下一步

- AC-CA-G01 可以基于本 fixture 验收竞品智能体读取 AC M12D。
- AC-CA-G01 不得在竞品智能体中生成或修正 AC M12D。
