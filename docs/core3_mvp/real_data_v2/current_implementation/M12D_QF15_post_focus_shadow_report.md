# M12D-QF-14 TV/AC 重点与边界 SKU 影子验证

- 生成时间：`2026-07-11T13:35:17.199358+00:00`
- 范围：只读重算 QF11 锚点角色和 QF12 画像决策；不改规则、不写 current、不改变竞品 Top 3。
- 总体验收：`通过`

## 1. 双品类结果

| 品类 | SKU | ready | limited | weak | 无核心 | 重点/边界样本 | 价格弱表达误升核心 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TV | 377 | 238 | 94 | 45 | 139 | 10 | 0 |
| AC | 155 | 130 | 23 | 2 | 25 | 18 | 0 |

## 2.1 TV 重点与边界 SKU

| SKU | 产品 | 选择原因 | 当前状态 -> 影子状态 | 影子核心理由 | 影子支持理由 |
| --- | --- | --- | --- | --- | --- |
| TV00009549 | 康佳 LED32E330CE | 最小尺寸边界 | weak_expression_only -> weak_expression_only | - | - |
| TV00027039 | 小米 L100MB-SP | 最大尺寸边界 | ready_degraded -> ready | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | same_size_picture_step_up、av_user_willing_to_pay_for_picture、gaming_device_fit_reduces_risk、sports_motion_stability、big_screen_cinema_substitution |
| TV00027801 | TCL 65Q9L PRO | TCL 65Q9L PRO | ready_degraded -> ready | living_room_upgrade_one_step | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、gaming_device_fit_reduces_risk、sports_motion_stability、big_screen_cinema_substitution、new_home_aesthetic_fit |
| TV00028829 | 创维 65A6F ULTRA | 创维 65A6F ULTRA | ready_degraded -> ready | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | same_price_core_config_gain、same_size_picture_step_up、av_user_willing_to_pay_for_picture、gaming_device_fit_reduces_risk、sports_motion_stability、big_screen_cinema_substitution、new_home_aesthetic_fit |
| TV00029020 | 小米 L65MC-SP | 小米 L65MC-SP | ready_degraded -> ready | living_room_upgrade_one_step、gaming_device_fit_reduces_risk | sports_motion_stability、big_screen_cinema_substitution、family_operation_less_friction、new_home_aesthetic_fit |
| TV00029031 | 酷开 32K3 | 最低均价边界 | weak_expression_only -> weak_expression_only | - | - |
| TV00029112 | 海信 65E7Q | 海信 65E7Q | ready_degraded -> ready | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | same_price_core_config_gain、same_size_picture_step_up、av_user_willing_to_pay_for_picture、gaming_device_fit_reduces_risk、sports_motion_stability、big_screen_cinema_substitution |
| TV00029344 | 华为 VISION智慧屏 5 SE优享版 65 | 华为品牌重点样本 | ready_degraded -> ready_limited | - | same_size_picture_step_up、av_user_willing_to_pay_for_picture、gaming_device_fit_reduces_risk、sports_motion_stability、living_room_upgrade_one_step、family_operation_less_friction |
| TV00029936 | 创维 65A7H PRO | 创维 65A7H PRO | ready_degraded -> ready_limited | - | picture_upgrade_justifies_price、same_size_picture_step_up、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step、new_home_aesthetic_fit |
| TV00030079 | TCL 98Q10M PRO | 最高均价边界 | ready_degraded -> ready | picture_upgrade_justifies_price、worth_paying_more_for_experience_upgrade、living_room_upgrade_one_step | same_price_core_config_gain、same_size_picture_step_up、av_user_willing_to_pay_for_picture、gaming_device_fit_reduces_risk、sports_motion_stability、big_screen_cinema_substitution、new_home_aesthetic_fit |

### TV 无核心/弱画像归因

- 无核心 SKU：`139`；归因：`{'all_anchor_evidence_weak_or_insufficient': 20, 'price_value_core_evidence_missing': 92, 'risk_drag_present': 32, 'supporting_evidence_below_core_gate': 16}`
- 归因复核桶：`{'evidence_or_business_gate_insufficient': 139}`
- 弱画像 SKU：`45`；归因：`{'all_anchor_evidence_weak_or_insufficient': 20, 'price_value_core_evidence_missing': 28, 'risk_drag_present': 12, 'supporting_evidence_below_core_gate': 3}`
- 价格弱表达/核心证据不足门槛观察：`239`；误升核心：`0`

## 2.2 AC 重点与边界 SKU

| SKU | 产品 | 选择原因 | 当前状态 -> 影子状态 | 影子核心理由 | 影子支持理由 |
| --- | --- | --- | --- | --- | --- |
| AC00028640 | 小米 KFR-72LW/N1A1 | 既有重点样本 | ready_degraded -> ready | long_term_energy_saving_offsets_price、cooling_heating_performance_justifies_price、fresh_air_health_reduces_stuffy_risk | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、self_cleaning_reduces_maintenance_risk、smart_remote_control_less_friction |
| AC00028642 | 小米 KFR-35GW/N1A1 | 既有重点样本 | review_required -> ready | long_term_energy_saving_offsets_price、fresh_air_health_reduces_stuffy_risk、smart_remote_control_less_friction | self_cleaning_reduces_maintenance_risk |
| AC00029751 | 格力 KFR-72LW/NHAJ1BGJ | 既有重点样本；最高均价边界 | review_required -> ready | long_term_energy_saving_offsets_price、cooling_heating_performance_justifies_price、same_price_efficiency_capacity_gain | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、self_cleaning_reduces_maintenance_risk、small_room_installation_fit |
| AC00034731 | 格力 KFR-35GW/NHAE1BAJ | 既有重点样本 | ready_degraded -> ready | cooling_heating_performance_justifies_price、long_term_energy_saving_offsets_price、room_size_capacity_match_reduces_risk | large_space_one_step_cooling_heating、same_price_efficiency_capacity_gain、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、self_cleaning_reduces_maintenance_risk、small_room_installation_fit |
| AC00034959 | 美的 KFR-72LW/QJ201-1 | M12C 缺失重点样本 | weak_expression_only -> ready_limited | - | long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、low_price_core_ac_experience_intact |
| AC00035996 | TCL KFR-35GW/JD21+B1 | 评论负向重点样本 | review_required -> ready | long_term_energy_saving_offsets_price、smart_remote_control_less_friction | sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort |
| AC00036020 | 华凌 KFR-35GW/N8HE1IIPRO | 评论负向重点样本 | review_required -> ready | same_price_efficiency_capacity_gain | long_term_energy_saving_offsets_price、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、humidity_dehumidification_reassurance、self_cleaning_reduces_maintenance_risk、small_room_installation_fit、smart_remote_control_less_friction |
| AC00036139 | 华凌 KFR-35GW/N8HA1III-P | 既有重点样本 | ready_degraded -> ready | same_price_efficiency_capacity_gain、long_term_energy_saving_offsets_price、small_room_installation_fit | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、self_cleaning_reduces_maintenance_risk、smart_remote_control_less_friction |
| AC00036211 | 海尔 KFR-50LW/E1-1 | floor 最小匹数边界 | review_required -> ready | cooling_heating_performance_justifies_price、long_term_energy_saving_offsets_price、room_size_capacity_match_reduces_risk | large_space_one_step_cooling_heating |
| AC00036333 | 美的 KFR-72LW/N8KS1-1U | 既有重点样本；floor 最大匹数边界 | review_required -> ready | cooling_heating_performance_justifies_price、long_term_energy_saving_offsets_price、room_size_capacity_match_reduces_risk | large_space_one_step_cooling_heating、same_price_efficiency_capacity_gain、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、self_cleaning_reduces_maintenance_risk、smart_remote_control_less_friction |
| AC00036739 | 格力 KFR-35GW/NHMA1BG | 既有重点样本 | review_required -> ready | long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、cooling_heating_performance_justifies_price | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、small_room_installation_fit |
| AC00038063 | 美的 KFR-88LW/N8KS1-1U | 既有重点样本 | ready_degraded -> ready | cooling_heating_performance_justifies_price、room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating | long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、self_cleaning_reduces_maintenance_risk、small_room_installation_fit |
| AC00038066 | 澳柯玛 KFR-35GW/BPYT-1 | M12C 缺失重点样本 | ready_degraded -> ready | same_price_efficiency_capacity_gain | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、long_term_energy_saving_offsets_price、low_price_core_ac_experience_intact、small_room_installation_fit、smart_remote_control_less_friction |
| AC00038662 | 美的 KFR-35GW/KS2 | 既有重点样本 | review_required -> ready | same_price_efficiency_capacity_gain、fresh_air_health_reduces_stuffy_risk | long_term_energy_saving_offsets_price、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、self_cleaning_reduces_maintenance_risk、small_room_installation_fit、smart_remote_control_less_friction |
| AC00038680 | 美的 KFR-26GW/KS2 | 既有重点样本 | review_required -> ready | same_price_efficiency_capacity_gain、long_term_energy_saving_offsets_price、room_size_capacity_match_reduces_risk | large_space_one_step_cooling_heating、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、small_room_installation_fit、smart_remote_control_less_friction |
| AC00038856 | 万宝 KFR-35GW/BPWL7-W1 | 最低均价边界 | review_required -> ready | long_term_energy_saving_offsets_price、smart_remote_control_less_friction | sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort |
| AC00039165 | 美的 KFR-72GW/KS2 | M12C 缺失重点样本；wall 最大匹数边界 | ready_degraded -> ready | cooling_heating_performance_justifies_price | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、smart_remote_control_less_friction |
| AC00039204 | 格力 KFR-26GW/NHGS1BGT | wall 最小匹数边界 | review_required -> ready_limited | - | room_size_capacity_match_reduces_risk、large_space_one_step_cooling_heating、cooling_heating_performance_justifies_price、long_term_energy_saving_offsets_price、same_price_efficiency_capacity_gain、low_price_core_ac_experience_intact、sleep_room_quiet_comfort_assurance、elderly_child_soft_wind_comfort、fresh_air_health_reduces_stuffy_risk、small_room_installation_fit |

### AC 无核心/弱画像归因

- 无核心 SKU：`25`；归因：`{'ac_claim_value_risk_role_dominant': 11, 'price_value_core_evidence_missing': 14, 'risk_drag_present': 3, 'weak_expression_role_cap_present': 11}`
- 归因复核桶：`{'evidence_or_business_gate_insufficient': 25}`
- 弱画像 SKU：`2`；归因：`{'ac_claim_value_risk_role_dominant': 1, 'price_value_core_evidence_missing': 1}`
- 价格弱表达/核心证据不足门槛观察：`46`；误升核心：`0`

## 3. 门禁结论

- 持久化表未变化：`True`
- 检查项：`{'persisted_tables_unchanged': True, 'tv_distribution_matches_qf12': True, 'tv_price_weak_cap_never_core': True, 'tv_fixed_focus_complete': True, 'tv_unaffected_samples_20': True, 'ac_distribution_matches_qf12': True, 'ac_price_weak_cap_never_core': True, 'ac_fixed_focus_complete': True, 'ac_unaffected_samples_20': True, 'tv_65e7q_budget_value_not_core': True, 'tv_65e7q_budget_value_gate_observed': True}`
- 本报告中的 `requires_scene_gate_review` 只表示 QF15 前需复核场景门槛，不等同于数据缺失，也未在 QF14 修改规则。
- QF14 未发布版本、未运行竞品智能体、未修改线上 Top 3。
