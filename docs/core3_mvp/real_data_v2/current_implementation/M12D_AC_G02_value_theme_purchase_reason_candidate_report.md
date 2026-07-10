# M12D AC-G02 价值主题与购买理由候选提炼报告

- 生成时间 UTC：2026-07-08T14:18:58.470290+00:00
- 数据源：205 `catforge_dev` / `d8d2245b-358b-4a64-95cc-9d7f2341bd26` / `AC`
- 批次：`m00_20260624000202_1150a669`
- 脚本性质：只读 SELECT；不发布 taxonomy；不生成 M12D 画像；不修改竞品智能体。

## 1. 覆盖摘要

| 模块 | SKU 数 | 行数 |
| --- | ---: | ---: |
| M03B | 155 | 155 |
| M04C | 155 | 155 |
| M05C | 144 | 144 |
| M07 | 155 | 155 |
| M09C | 144 | 144 |
| M10C | 144 | 144 |
| M11C | 144 | 144 |
| M11D | 140 | 1489 |
| M12C | 140 | 6303 |

## 2. 就绪分层

| 分层 | SKU 数 |
| --- | ---: |
| `ready_strong_candidate` | 140 |
| `facts_market_only_comment_missing` | 11 |
| `other_degraded` | 4 |

## 3. M12C 角色分布

| role | 行数 | SKU 数 | claim 数 |
| --- | ---: | ---: | ---: |
| `high_price_competitor_intercept` | 1686 | 134 | 9 |
| `opportunity_gap` | 1132 | 131 | 9 |
| `weak_user_perception_claim` | 972 | 131 | 9 |
| `basic_threshold` | 889 | 128 | 5 |
| `drag_factor` | 672 | 98 | 9 |
| `price_up_opportunity` | 547 | 91 | 9 |
| `sales_driver_estimated` | 405 | 101 | 8 |

## 4. AC 标准价值主题候选

| code | 中文名 | 命中 SKU | 审阅建议 | 状态分布 | 主要证据域 | 样本 SKU |
| --- | --- | ---: | --- | --- | --- | --- |
| `cooling_heating_capacity_assurance` | 冷暖能力确定感 | 155 | `draft_accept` | theme_review:11, theme_strong_candidate:144 | claim:152, claim_value:121, comment:141, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `energy_cost_efficiency` | 长期用电成本效率 | 155 | `draft_accept` | theme_review:13, theme_strong_candidate:142 | claim:154, claim_value:136, comment:137, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `sleep_quiet_comfort` | 睡眠静音舒适感 | 155 | `draft_accept` | theme_review:15, theme_strong_candidate:140 | claim:150, claim_value:130, comment:139, param:155, semantic_reference:144 | AC00039073, AC00035278, AC00032705, AC00038813, AC00036328 |
| `comfortable_airflow_health` | 舒适风与健康空气 | 155 | `draft_accept` | theme_review:14, theme_strong_candidate:141 | claim:154, claim_value:140, comment:126, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00038813, AC00036328 |
| `large_space_coverage` | 大空间覆盖感 | 155 | `draft_accept` | theme_review:13, theme_strong_candidate:142 | claim:146, comment:131, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `installation_space_fit` | 安装与空间适配 | 155 | `draft_accept` | theme_review:21, theme_strong_candidate:134 | claim:145, comment:141, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `operation_maintenance_convenience` | 操作维护省心 | 155 | `draft_accept` | theme_review:13, theme_strong_candidate:142 | claim:155, claim_value:138, comment:141, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `budget_configuration_efficiency` | 预算配置效率 | 155 | `draft_accept` | theme_review:50, theme_strong_candidate:100, theme_weak_boundary:5 | claim:109, claim_value:140, comment:143, market:155 | AC00039073, AC00039563, AC00035278, AC00038813, AC00036328 |
| `seasonal_reliability` | 季节和极端天气可靠性 | 155 | `draft_accept` | theme_review:16, theme_strong_candidate:139 | claim:150, comment:143, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |

## 5. AC 标准购买理由候选

| code | 中文名 | 命中 SKU | 审阅建议 | 状态分布 | 主要证据域 | 样本 SKU |
| --- | --- | ---: | --- | --- | --- | --- |
| `room_size_capacity_match_reduces_risk` | 匹数空间匹配降低买小风险 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:153, comment:137, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `cooling_heating_performance_justifies_price` | 冷暖效果解释更高价格 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:151, claim_value:121, comment:135, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `long_term_energy_saving_offsets_price` | 长期省电抵消更高价格 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:154, claim_value:136, comment:137, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `same_price_efficiency_capacity_gain` | 同价位能效/能力获得感 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:155, claim_value:140, comment:144, market:155, param:155 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `sleep_room_quiet_comfort_assurance` | 卧室睡眠更安静舒适 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:150, claim_value:130, comment:139, param:155, semantic_reference:144 | AC00039073, AC00035278, AC00032705, AC00038813, AC00036328 |
| `elderly_child_soft_wind_comfort` | 老人儿童房柔风不直吹 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:150, claim_value:130, comment:132, semantic_reference:144 | AC00039073, AC00035278, AC00038813, AC00036328, AC00039131 |
| `fresh_air_health_reduces_stuffy_risk` | 新风/净化减少闷和空气担忧 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:129, claim_value:139, comment:102, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00038813, AC00036328 |
| `small_room_installation_fit` | 小房间/租房安装适配 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:152, comment:141, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `smart_remote_control_less_friction` | 远程/智能控制减少操作摩擦 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:155, claim_value:138, comment:141, param:155, semantic_reference:140 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `low_price_core_ac_experience_intact` | 低价不明显牺牲核心冷暖体验 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:5, review:4, risk_review:131 | claim:155, claim_value:140, comment:144, market:155, param:155 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `large_space_one_step_cooling_heating` | 大空间冷暖一步到位 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:4, review:5, risk_review:131 | claim:146, comment:131, market:155, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `self_cleaning_reduces_maintenance_risk` | 自清洁/防霉降低维护风险 | 155 | `review` | degraded_missing_m12c_or_m11d:15, draft_accept:3, review:6, risk_review:131 | claim:152, comment:97, param:155, semantic_reference:144 | AC00039073, AC00039563, AC00035278, AC00032705, AC00038813 |
| `humidity_dehumidification_reassurance` | 潮湿环境除湿更安心 | 147 | `review` | degraded_missing_m12c_or_m11d:7, review:2, risk_review:131, weak_boundary:7 | claim:39, comment:38, semantic_reference:144 | AC00035278, AC00035277, AC00038445, AC00034716, AC00033721 |

## 6. 样本 SKU 矩阵

| SKU | 品牌 | 型号 | 价格带 | 销量 | 缺失模块 | M12C role 摘要 |
| --- | --- | --- | --- | ---: | --- | --- |
| `AC00038063` | 美的 | KFR-88LW/N8KS1-1U | high/unknown | 13916.0 | - | basic_threshold:9 |
| `AC00028640` | 小米 | KFR-72LW/N1A1 | mid_high/mid_low | 15353.0 | - | basic_threshold:11, high_price_competitor_intercept:12, opportunity_gap:14, price_up_opportunity:4, sales_driver_estimated:3, weak_user_perception_claim:8 |
| `AC00029751` | 格力 | KFR-72LW/NHAJ1BGJ | high/high | 8534.0 | - | basic_threshold:4, drag_factor:15, opportunity_gap:6, price_up_opportunity:12, sales_driver_estimated:7, weak_user_perception_claim:3 |
| `AC00036139` | 华凌 | KFR-35GW/N8HA1III-P | low/low | 1131790.0 | - | basic_threshold:5, high_price_competitor_intercept:9, opportunity_gap:15, sales_driver_estimated:3, weak_user_perception_claim:6 |
| `AC00038662` | 美的 | KFR-35GW/KS2 | mid_low/mid | 723648.0 | - | basic_threshold:11, drag_factor:11, high_price_competitor_intercept:33, opportunity_gap:9, sales_driver_estimated:2, weak_user_perception_claim:10 |
| `AC00028642` | 小米 | KFR-35GW/N1A1 | low/low | 789265.0 | - | basic_threshold:5, drag_factor:5, high_price_competitor_intercept:2, opportunity_gap:11, price_up_opportunity:4, sales_driver_estimated:2, weak_user_perception_claim:7 |
| `AC00036739` | 格力 | KFR-35GW/NHMA1BG | mid/mid_high | 433372.0 | - | basic_threshold:7, drag_factor:7, high_price_competitor_intercept:17, opportunity_gap:1, price_up_opportunity:9, sales_driver_estimated:7, weak_user_perception_claim:9 |
| `AC00036333` | 美的 | KFR-72LW/N8KS1-1U | high/mid | 121406.0 | - | basic_threshold:4, drag_factor:3, high_price_competitor_intercept:7, opportunity_gap:6, price_up_opportunity:13, sales_driver_estimated:7, weak_user_perception_claim:3 |
| `AC00035996` | TCL | KFR-35GW/JD21+B1 | low/low | 523790.0 | - | basic_threshold:5, drag_factor:3, high_price_competitor_intercept:9, opportunity_gap:5, price_up_opportunity:2, sales_driver_estimated:1, weak_user_perception_claim:13 |
| `AC00036020` | 华凌 | KFR-35GW/N8HE1IIPRO | mid_low/mid | 236964.0 | - | basic_threshold:4, drag_factor:14, high_price_competitor_intercept:21, opportunity_gap:8, price_up_opportunity:15, sales_driver_estimated:1, weak_user_perception_claim:4 |
| `AC00038680` | 美的 | KFR-26GW/KS2 | mid_low/mid | 489318.0 | - | drag_factor:7, high_price_competitor_intercept:32, opportunity_gap:9, sales_driver_estimated:4 |
| `AC00034731` | 格力 | KFR-35GW/NHAE1BAJ | mid/high | 185591.0 | - | basic_threshold:5, high_price_competitor_intercept:19, opportunity_gap:6, sales_driver_estimated:7, weak_user_perception_claim:11 |
| `AC00039165` | 美的 | KFR-72GW/KS2 | high/unknown | 15356.0 | M11D, M12C | - |
| `AC00038066` | 澳柯玛 | KFR-35GW/BPYT-1 | low/low | 60022.0 | M11D, M12C | - |
| `AC00034959` | 美的 | KFR-72LW/QJ201-1 | high/mid_high | 30227.0 | M05C, M09C, M10C, M11C, M11D, M12C | - |

## 7. G03 使用建议

- `draft_accept` 只表示证据覆盖足够进入人审草案，不等于标准 taxonomy 已发布。
- `review` 和 `risk_review` 需要在 G03 中人工判断是否拆分、合并或降级。
- `weak_boundary` 主要用于定义弱表达上限，不应直接进入核心购买理由。
- G03 应优先处理覆盖广、区分度够、业务解释清楚的购买理由。

## 8. 边界说明

- G02 只提炼候选，不发布标准 taxonomy。
- M03B 查询必须限定 category_code=AC，避免 AC 前缀旧 TV 批次污染。
- 只有 price_value、补贴、服务履约、安装售后或认证背书时，候选必须停留在 weak_boundary。
- M12C 缺失或只有 weak/risk role 时，不得作为后续 core_payment 的正向证明。
- 当前 AC M12C 正向角色主要是 sales_driver_estimated，应作为销量转化证据而非高价支付理由。
