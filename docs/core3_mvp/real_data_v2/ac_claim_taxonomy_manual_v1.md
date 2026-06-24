# AC 标准卖点资产人工归纳草案 v0.1

生成日期：2026-06-24

数据来源：205 `/opt/catforge`，`core3_clean_claim` 与 `core3_evidence_atom`，`project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`，`batch_id=m00_20260624000202_1150a669`。

## 1. 数据边界

本草案只使用 AC SKU 的真实结构化卖点，不复用 TV 标准卖点。

| 指标 | 数量 |
| --- | ---: |
| AC SKU | 155 |
| AC 品牌 | 17 |
| AC 型号 | 155 |
| 清洗后卖点行 | 1,994 |
| 去重卖点文本 | 1,963 |
| M02 `promo_raw` 证据 | 1,994 |
| M02 `promo_sentence` 证据 | 2,189 |

清洗后的卖点标题分布显示，AC 卖点源同时包含通用叙事标题和真实功能标题：

| 标题 | 卖点行 | SKU |
| --- | ---: | ---: |
| 其他卖点 | 523 | 155 |
| 功能价值 | 155 | 155 |
| 情感价值 | 155 | 155 |
| 便捷体验 | 155 | 155 |
| 差异化定位 | 155 | 155 |
| 核心定位 | 155 | 155 |
| 行业地位 | 146 | 146 |
| 56°C净菌自洁 | 23 | 23 |
| AI省电算法 | 10 | 10 |
| 第二代冷酷外机 | 8 | 8 |
| 10年整机包修 | 8 | 8 |
| 独立除湿 | 6 | 6 |

这些通用标题不能直接成为标准卖点。标准卖点应从标题和正文共同归纳，并按 TV M04C 方法拆成“产品事实卖点”“市场/价格价值表达”“行业背书”“服务履约”。

## 2. 归纳方法

参照 TV M04C 首版标准卖点方法，本草案按以下口径处理：

1. 每个标准卖点必须有稳定 `claim_code`、中文名、一级维度、二级子类、原始表达模式、参数支撑规则和下游使用策略。
2. 产品事实卖点必须尽量由 AC M03B 标准参数支撑；当前参数体系缺字段时，先保留标准卖点，但标记为 `param_gap`，运行时不能伪造参数支撑。
3. 服务履约、行业背书、价格补贴、情感价值不作为产品事实卖点，单独隔离，供展示或解释使用。
4. AC 和 TV 不共享 taxonomy。AC 不能复用 TV 的 Mini LED、高刷、HDMI2.1、音响影院等 taxonomy。
5. 缺失是未知。除 AC 参数资产中明确 `false_by_absence` 的能力标记外，不因未提及而判定卖点不存在。

## 3. 候选卖点覆盖

以下覆盖来自清洗卖点文本的人工规则预归类，用于解释为什么纳入标准卖点，不等同于最终 M04C 命中结果。

| 候选卖点 | 卖点行 | SKU | 品牌 | 典型表达 |
| --- | ---: | ---: | ---: | --- |
| 能效/APF/省电 | 572 | 154 | 17 | 巨省电、新一级能效、APF、节能 |
| AI 省电算法 | 244 | 86 | 10 | AI动态节能、酷省算法、Air Magic、灵云节能 |
| 速冷速热 | 151 | 81 | 16 | 15秒速冷、30秒速热、快速制冷制热 |
| 宽温域可靠运行 | 194 | 87 | 15 | -35°C 制热、60°C/65°C 制冷、严寒酷暑稳定运行 |
| 大风量/全域送风 | 192 | 103 | 16 | 大循环风量、广角送风、上下出风、全屋覆盖 |
| 柔风/防直吹 | 141 | 66 | 13 | 柔风、无风感、不直吹、防冷风、舒适风 |
| 静音睡眠 | 248 | 106 | 16 | 18dB、22dB、静音、低噪、整夜安睡 |
| 精准控温 | 115 | 73 | 14 | 0.5°C 控温、精准控温、恒温、衡温 |
| 除湿/温湿双控 | 75 | 39 | 12 | 独立除湿、个性除湿、温湿双控 |
| 新风 | 13 | 6 | 4 | 新风换气、双翼新风、室外鲜氧 |
| 净化/除菌/抗菌 | 191 | 81 | 13 | 净菌、抗菌防霉、PM2.5、抗病毒 |
| 自清洁/自洁 | 338 | 121 | 17 | 56°C 高温自洁、水洗、内外机自清洁 |
| APP/语音/IoT 智控 | 272 | 116 | 15 | APP远程、语音、米家、小爱、WiFi、蓝牙 |
| 外观/空间适配 | 29 | 27 | 12 | 贴合式、节省空间、简约外观、融入家居 |
| 耐用品质/核心材料 | 205 | 108 | 15 | 铜管、压缩机、液冷散热、冷媒环、缺氟保护 |
| 包修/安装/售后 | 414 | 136 | 16 | 10年包修、基础安装免费、售后保障 |
| 行业背书/认证/销量 | 244 | 151 | 17 | 行业领先、认证、热销、TOP、满意度 |
| 价格/补贴/性价比 | 191 | 109 | 17 | 补贴、省钱、电费、入门、同价位 |

组合覆盖显示 AC 的主链路不是单点能力，而是复合价值：

| 组合 | SKU |
| --- | ---: |
| 能效 + 速冷速热 | 81 |
| 能效 + AI 省电 | 86 |
| 大风量 + 柔风 | 44 |
| 自清洁 + 净化/除菌 | 75 |
| 宽温域 + 速冷速热 | 47 |
| 静音 + 柔风 | 39 |
| 智控 + 能效 | 116 |

## 4. AC 首版标准卖点维度

| 维度 | 说明 | 是否产品主链路 |
| --- | --- | --- |
| `energy_efficiency` | 能效等级、APF、省电算法、长期电费价值 | 是 |
| `temperature_performance` | 制冷制热速度、宽温域、极端环境稳定运行 | 是 |
| `airflow_comfort` | 大风量、送风覆盖、柔风、防直吹、静音睡眠、精准控温 | 是 |
| `health_clean_air` | 自清洁、净化、除菌、抗菌、新风、除湿控湿 | 是 |
| `smart_control` | APP、语音、IoT 生态、智能感应和远程控制 | 是 |
| `installation_design` | 安装形态、空间占用、外观家居适配 | 是，弱产品事实 |
| `durability_quality` | 压缩机、铜管、冷媒、保护机制、耐用品质 | 是，但当前参数缺口较多 |
| `price_value` | 补贴、省钱、同价位、性价比 | 部分产品/市场价值，价值判断延后 |
| `authority` | 行业地位、认证、销量背书、专利 | 非产品主事实，单独保留 |
| `service_fulfillment` | 安装、售后、包修、质保、以旧换新 | 否，服务履约隔离 |

## 5. AC 标准卖点定义

### 5.1 产品事实卖点

| claim_code | 标准卖点 | 维度 | 子类 | 表达模式 | 参数支撑 | 处理说明 |
| --- | --- | --- | --- | --- | --- | --- |
| `ac_claim_energy_efficiency_apf` | 高能效/APF/省电 | `energy_efficiency` | `apf_energy_grade` | 巨省电、省电、节能、新一级能效、APF、能效比 | `energy_grade_normalized`、`energy_efficiency_ratio`、`inverter_flag` | AC 最高覆盖卖点，作为能效事实主锚点。 |
| `ac_claim_ai_energy_saving` | AI 省电算法 | `energy_efficiency` | `ai_energy_algorithm` | AI动态节能、AI省电、酷省算法、灵云节能、Air Magic | 当前用 `energy_efficiency_ratio`、`inverter_flag` 辅助；缺 `ai_energy_algorithm_flag` | 算法名来自卖点文本，参数体系暂不能完全证明。 |
| `ac_claim_fast_cooling_heating` | 速冷速热 | `temperature_performance` | `fast_response` | 速冷、速热、15秒速冷、30秒速热、60秒速热、高频速冷热 | `cooling_capacity_w`、`heating_capacity_w`、`horsepower_hp`、`heat_cool_mode` | 需要结合匹数和制冷/制热量判断是否强支撑。 |
| `ac_claim_wide_temperature_operation` | 宽温域可靠运行 | `temperature_performance` | `wide_temperature` | 宽温域、极寒、极热、-35°C 制热、60°C/65°C 制冷 | 当前仅有 `heat_cool_mode` 辅助；缺 `operation_temperature_min_c/max_c` | 应纳入标准卖点，但首版多为 `param_unknown` 或 `partially_supported`。 |
| `ac_claim_large_airflow_coverage` | 大风量/全域送风 | `airflow_comfort` | `airflow_coverage` | 大风量、循环风量、广角送风、宽幅送风、全域送风、上下出风 | `airflow_volume_m3h`、`installation_type`、`horsepower_hp` | 以循环风量数值和安装形态作为主要支撑。 |
| `ac_claim_soft_wind_no_direct` | 柔风/防直吹 | `airflow_comfort` | `soft_wind` | 柔风、无风感、不直吹、防直吹、防冷风、舒适风、自然风 | `comfort_airflow_flag`、`airflow_volume_m3h` | `comfort_airflow_flag=true` 为强支撑；仅文本提及时可部分支撑。 |
| `ac_claim_quiet_sleep` | 静音睡眠 | `airflow_comfort` | `quiet_sleep` | 静音、低噪、轻音、18dB、22dB、睡眠、安睡、静眠 | 当前缺 `noise_db`；可用 `inverter_flag` 辅助但不能证明 | 首版保留，建议补充噪音参数。 |
| `ac_claim_precision_temperature_control` | 精准控温/恒温 | `airflow_comfort` | `temperature_precision` | 0.5°C、±0.5°C、精准控温、恒温、衡温 | 当前缺 `temperature_precision_c`；可用 `inverter_flag` 辅助 | 需要新增控温精度参数才能强支撑。 |
| `ac_claim_humidity_dehumidification` | 除湿/温湿双控 | `health_clean_air` | `humidity_control` | 独立除湿、个性除湿、温湿双控、控湿、防潮、干爽 | 当前缺 `dehumidification_flag`、`humidity_control_flag` | 样本覆盖不高但场景价值明确，应作为 AC 独立卖点。 |
| `ac_claim_fresh_air` | 新风换气 | `health_clean_air` | `fresh_air` | 新风、鲜氧、换气 | `fresh_air_flag` | 覆盖低但有明确参数支撑，不能并入净化。 |
| `ac_claim_purification_antibacterial` | 净化/除菌/抗菌 | `health_clean_air` | `purification_antibacterial` | 净化、除 PM2.5、抗病毒、除菌、杀菌、抗菌、防霉、净菌 | `purification_flag` | 与自清洁分开：一个是空气健康/滤网净化，一个是机器自洁。 |
| `ac_claim_self_cleaning` | 自清洁/自洁 | `health_clean_air` | `self_cleaning` | 自清洁、自洁、56°C、高温烘干、水洗、内外机自清洁 | `self_cleaning_flag` | AC 高频卖点，应作为健康清洁主锚点。 |
| `ac_claim_smart_app_voice_iot` | APP/语音/IoT 智控 | `smart_control` | `remote_voice_iot` | APP远程、语音、小爱、米家、WiFi、蓝牙、智控、IoT、OTA | `wifi_control_flag`、`voice_control_flag`、`smart_sensing_flag` | 区分远程控制、语音控制和智能感应可在后续细分。 |
| `ac_claim_installation_space_design` | 外观/空间适配 | `installation_design` | `space_design` | 贴合式、节省空间、简约外观、高颜值、融入家居 | `installation_type`、`indoor_unit_dimensions_mm`、`product_type_combo` | 覆盖不高，适合作为弱产品事实和展示补充。 |
| `ac_claim_durability_core_material` | 耐用品质/核心材料 | `durability_quality` | `core_material` | 铜管、压缩机、液冷散热、冷媒环、缺氟保护、真材实料、耐腐蚀 | `refrigerant_type` 辅助；缺 `compressor_type`、`condenser_material`、`copper_pipe_flag` | 当前参数支撑不足，保留但需复核。 |

### 5.2 非产品主事实卖点

| claim_code | 标准卖点 | 维度 | claim_kind | 表达模式 | 处理说明 |
| --- | --- | --- | --- | --- | --- |
| `ac_claim_warranty_install_service` | 包修/安装/售后服务 | `service_fulfillment` | `service_fulfillment` | 10年包修、6年包修、基础安装免费、售后、质保、以旧换新 | 服务履约隔离，不作为产品事实卖点。 |
| `ac_claim_authority_sales_certification` | 行业背书/认证/销量 | `authority` | `authority` | 行业领先、认证、热销、TOP、满意度、专利、国家认证 | 可用于解释，不参与产品能力判断。 |
| `ac_claim_price_value_subsidy` | 价格/补贴/性价比 | `price_value` | `market_position` | 补贴、性价比、省钱、电费、同价位、入门、价格 | 价值判断需要市场价位和销量，不直接作为事实卖点。 |

## 6. 参数支撑规则草案

| 标准卖点 | 支撑策略 | 强支撑条件 | 弱支撑/待补参数 |
| --- | --- | --- | --- |
| 高能效/APF/省电 | `required_any` | `energy_grade_normalized=1` 或 `energy_efficiency_ratio` 有效 | `inverter_flag=true` 只能弱支撑 |
| AI 省电算法 | `weighted` | 暂无直接参数；卖点文本命中 + 能效参数强 | 建议新增 `ai_energy_algorithm_flag`、`ai_energy_algorithm_name` |
| 速冷速热 | `weighted` | `cooling_capacity_w`、`heating_capacity_w`、`horsepower_hp` 与产品匹数匹配 | 建议新增 `fast_cooling_time_sec`、`fast_heating_time_sec` |
| 宽温域可靠运行 | `required_any` | 暂无直接参数 | 建议新增 `operation_temperature_min_c`、`operation_temperature_max_c` |
| 大风量/全域送风 | `required_any` | `airflow_volume_m3h` 有效，且按匹数/安装形态分档较高 | 送风角度、导风板结构暂只能文本支撑 |
| 柔风/防直吹 | `required_any` | `comfort_airflow_flag=true` | 防冷风、无风感、自然风细分参数待补 |
| 静音睡眠 | `required_any` | 暂无直接参数 | 建议新增 `indoor_noise_min_db`、`sleep_mode_flag` |
| 精准控温/恒温 | `required_any` | 暂无直接参数 | 建议新增 `temperature_control_precision_c` |
| 除湿/温湿双控 | `required_any` | 暂无直接参数 | 建议新增 `dehumidification_flag`、`humidity_control_flag` |
| 新风换气 | `required_any` | `fresh_air_flag=true` | 新风量待补 |
| 净化/除菌/抗菌 | `required_any` | `purification_flag=true` | 抗菌、防霉、病毒灭活率可后续细分 |
| 自清洁/自洁 | `required_any` | `self_cleaning_flag=true` | 56°C、水洗、内外机自洁可后续细分 |
| APP/语音/IoT 智控 | `required_any` | `wifi_control_flag=true`、`voice_control_flag=true`、`smart_sensing_flag=true` 任一 | 生态品牌和 OTA 能力待补 |
| 外观/空间适配 | `weighted` | `installation_type`、`indoor_unit_dimensions_mm` 能解释安装形态和体积 | 外观颜色、厚度、占地面积待补 |
| 耐用品质/核心材料 | `weighted` | 当前仅 `refrigerant_type` 辅助 | 建议新增 `copper_pipe_flag`、`compressor_type`、`condenser_material` |

## 7. AC 卖点位置规则草案

M04C 除标准卖点明细外，还需要维度位置，供后续竞品召回和价值战场使用。

### 7.1 能效位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `energy_ai_saving_leader` | AI 省电领先型 | 命中 AI 省电算法，且能效/APF 卖点或一级能效参数存在 |
| `energy_high_efficiency` | 高能效型 | 命中能效/APF/省电，且参数显示一级能效或 APF 有效 |
| `energy_basic_saving_mentioned` | 基础节能提及型 | 只出现节能/省电表达，参数支撑不足 |

### 7.2 温控性能位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `temperature_extreme_fast` | 宽温速冷热型 | 同时命中宽温域和速冷速热 |
| `temperature_fast_response` | 快速冷暖型 | 命中速冷速热，且制冷/制热量或匹数有支撑 |
| `temperature_wide_reliable` | 极端环境可靠型 | 命中宽温域，但速冷速热不足 |
| `temperature_basic` | 基础冷暖提及型 | 只出现普通制冷制热表达 |

### 7.3 送风舒适位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `airflow_comfort_full` | 大风量柔风静音复合型 | 大风量、柔风、防直吹、静音中至少三类出现 |
| `airflow_large_coverage` | 大风量全屋覆盖型 | 命中大风量/全域送风，并有循环风量参数 |
| `airflow_soft_sleep` | 柔风静音睡眠型 | 柔风/防直吹与静音睡眠同时出现 |
| `airflow_basic` | 基础送风提及型 | 有送风表达但缺少复合支撑 |

### 7.4 健康清洁位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `health_self_clean_purify` | 自清洁净化复合型 | 自清洁与净化/除菌同时出现 |
| `health_fresh_air` | 新风健康型 | 命中新风换气 |
| `health_self_clean` | 自清洁型 | 只命中自清洁/自洁 |
| `health_purification` | 净化抗菌型 | 只命中净化/除菌/抗菌 |
| `health_humidity_control` | 除湿控湿型 | 命中除湿或温湿双控 |

### 7.5 智能控制位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `smart_iot_voice_full` | IoT 语音全链路型 | 同时命中 APP/远程、语音、生态联动 |
| `smart_remote_control` | 远程智控型 | 命中 APP/WiFi/蓝牙远程控制 |
| `smart_basic` | 基础智能提及型 | 只有普通智能/智控表达 |

### 7.6 服务和背书隔离位置

| position_code | 位置名称 | 判断规则 |
| --- | --- | --- |
| `service_long_warranty_install` | 长保修安装服务型 | 命中包修/安装/售后服务 |
| `authority_certified_sales` | 认证销量背书型 | 命中认证、销量、TOP、满意度、行业领先 |
| `price_subsidy_value` | 补贴性价比表达型 | 命中补贴、性价比、同价位、省钱 |

这些位置只用于解释和召回，不应被误写成产品能力。

## 8. 首版发布建议

建议首版 AC M04C taxonomy 先发布 18 个标准卖点：

- 15 个产品事实卖点：能效/APF、AI 省电、速冷速热、宽温域、大风量、柔风/防直吹、静音睡眠、精准控温、除湿/温湿双控、新风、净化除菌、自清洁、智能智控、外观空间、耐用品质。
- 3 个隔离卖点：服务履约、行业背书、价格价值。

首版运行时建议：

1. 对 `ac_claim_energy_efficiency_apf`、`ac_claim_large_airflow_coverage`、`ac_claim_soft_wind_no_direct`、`ac_claim_fresh_air`、`ac_claim_purification_antibacterial`、`ac_claim_self_cleaning`、`ac_claim_smart_app_voice_iot` 使用现有 AC 参数强支撑。
2. 对 AI 省电、宽温域、静音、精准控温、除湿、耐用品质标记参数缺口，先允许生成宣传命中，但不能标成强事实支撑。
3. 服务、行业、价格价值使用 `not_param_applicable`，并设置 `fact_claim_flag=false`。
4. 发布代码前，需要补测试：AC taxonomy 查询可用、AC M04C 不再阻断、服务隔离不进入产品事实、参数缺口输出 `param_unknown` 或 `partially_supported`。
