# M12D AC 标准价值主题与购买理由 taxonomy v0.1 人审草案

日期：2026-07-08

本文件是 AC-M12D-G03 的人审草案产物，用来固化空调品类第一版两层 taxonomy。它基于 G01 上游证据审计和 G02 候选提炼报告生成，不是程序自动发布结果，也不是竞品智能体里的临时评分逻辑。

## 1. 标准定位

AC taxonomy 分为两层：

| 层级 | 回答的问题 | 后续用途 |
| --- | --- | --- |
| 标准价值主题 | 用户获得什么可感知价值 | 解释、归因和证据聚合，不直接输出成交理由。 |
| 标准购买理由 | 用户为什么选择这个 SKU | 进入 G04/G05 的候选生成、证据评分和角色判定。 |

运行时程序后续只读取本标准并匹配 SKU 证据，不负责创造标准锚点族。G03 只固化草案，G04 才允许实现 loader 和 candidate generator，G05 才允许做 `core_payment`、`supporting`、`weak_expression` 和 `risk_drag` 角色判定。

## 2. 版本边界

| 字段 | 值 |
| --- | --- |
| `category_code` | `AC` |
| `product_category_label_cn` | 空调 |
| `taxonomy_version` | `m12d_ac_purchase_reason_anchor_taxonomy_v0.1` |
| `taxonomy_status` | `human_review_draft` |
| 数据源批次 | `m00_20260624000202_1150a669` |
| 证据窗口 | `full_observed_window` |
| G03 Markdown 产物 | `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.md` |
| G03 JSON 草案 | `docs/core3_mvp/real_data_v2/current_implementation/M12D_AC_standard_anchor_taxonomy_v0_1.json` |

品类隔离规则：

- 不复用 TV 的画质、游戏、客厅沉浸、护眼和家装审美 taxonomy。
- 不把 AC SKU 前缀当作 AC 依据，后续读取必须过滤 `category_code=AC`、`product_category=AC` 和当前批次。
- 不把安装、售后、补贴、认证背书单独判为产品核心购买理由。
- AC M12D 发布前，竞品智能体不得消费本草案作为已发布画像。

## 3. 证据基础

G01/G02 的只读证据显示：

| 证据项 | 结论 | 对 taxonomy 的影响 |
| --- | --- | --- |
| AC market scope | 155 SKU | taxonomy 要覆盖全量事实和市场池。 |
| M03B/M04C/M07 | 155 SKU | 参数、卖点和市场位置可作为基础证据。 |
| M05C/M09C/M10C/M11C | 144 SKU | 用户感知、任务、客群和价值战场有 11 SKU 缺失，场景型理由必须支持降级。 |
| M11D/M12C | 140 SKU | 强支付理由只能在 140 个 fact-complete SKU 上验证；其余 SKU 不得强判 `core_payment`。 |
| M12C 正向角色 | `sales_driver_estimated` 405 行/101 SKU | 可作为销量转化证据，但不是高价支付理由的充分条件。 |
| M12C 风险/弱角色 | `high_price_competitor_intercept`、`opportunity_gap`、`weak_user_perception_claim` 等占比较高 | 购买理由草案必须保留弱表达上限、竞品拦截和风险降级。 |

G02 候选结论：

- 9 个价值主题均可进入草案。
- 13 个购买理由均进入 `review`，不是自动发布。
- 购买理由必须用用户决策语言表达，不能是参数名、卖点名或价值主题名。

## 4. 标准价值主题

价值主题只说明“用户获得什么价值”，不直接进入角色判定。排序用于后续配置稳定性，不表达业务优先级。

| 排序 | value_theme_code | 中文名 | 定义 | 主要证据域 | 边界 |
| ---: | --- | --- | --- | --- | --- |
| 10 | `cooling_heating_capacity_assurance` | 冷暖能力确定感 | 用户相信这台空调能覆盖目标空间，冷得快、热得稳，不容易买小或不够用。 | 匹数、制冷量、制热量、循环风量、冷暖评论、空间任务、市场承接。 | 只有匹数或型号字样不足以成为购买理由。 |
| 20 | `energy_cost_efficiency` | 长期用电成本效率 | 用户相信长期使用电费更可控，能效、APF 和变频可以解释后续成本。 | APF、能效等级、变频、省电评论、同价位能效差、M12C 销量转化。 | 只有一级能效口号时封顶弱表达。 |
| 30 | `sleep_quiet_comfort` | 睡眠静音舒适感 | 用户在卧室或夜间使用时更安静、不扰眠、温控更舒适。 | 噪音参数、睡眠模式、卧室任务、静音评论、风感评论。 | 只有静音卖点时封顶辅助或弱表达。 |
| 40 | `comfortable_airflow_health` | 舒适风与健康空气 | 用户减少直吹、闷、异味或空气健康担忧。 | 柔风、防直吹、扫风、新风量、净化/除菌、风感和空气评论。 | 新风、净化、除菌单独出现不等于健康空气购买理由。 |
| 50 | `large_space_coverage` | 大空间覆盖感 | 用户相信客厅、大卧室或大面积空间能被快速覆盖。 | 大匹数、柜机、循环风量、大空间任务、客厅评论、市场承接。 | 只有柜机或大匹数标签时不能强判。 |
| 60 | `installation_space_fit` | 安装与空间适配 | 用户相信房型、安装位置和预算条件下能装得下、用得上。 | 挂机/柜机、内外机尺寸、安装评论、租房/小户型任务。 | 安装、送装、售后只能做辅助或风险。 |
| 70 | `operation_maintenance_convenience` | 操作维护省心 | 用户减少清洁、控制、调温和日常维护成本。 | 自清洁、防霉、App、语音、远程控制、维护评论。 | 只有智能或自清洁口号时封顶弱表达。 |
| 80 | `budget_configuration_efficiency` | 预算配置效率 | 用户在预算内获得足够的核心冷暖、能效或舒适配置。 | 同形态同匹数价格位置、核心配置、销量、性价比评论、M12C 销量转化。 | 只有价格、补贴或 `price_value` 时只能弱表达。 |
| 90 | `seasonal_reliability` | 季节和极端天气可靠性 | 用户相信夏季高温、冬季低温、梅雨潮湿等季节压力下更稳定。 | 高温制冷、低温制热、除湿、季节任务、潮湿/冬夏评论。 | 泛化品质宣传不能单独支撑季节可靠性。 |

## 5. 标准购买理由

购买理由回答“用户为什么选择这个 SKU”。后续 G04/G05 只对购买理由层做候选生成、证据强度和角色判定。

| 排序 | purchase_reason_code | 中文名 | 对应价值主题 | 成立逻辑 | 弱表达上限 | 冲突降级 |
| ---: | --- | --- | --- | --- | --- | --- |
| 10 | `room_size_capacity_match_reduces_risk` | 匹数空间匹配降低买小风险 | `cooling_heating_capacity_assurance`, `installation_space_fit` | 需要能力参数或安装形态，加上房间/空间任务、评论或市场参照，证明不容易买小或买错。 | 只有型号、匹数字样或大风量口号时不能成立。 | 缺 M09C/M10C/M11C 时场景置信度下降；缺 M12C 时最多 supporting。 |
| 20 | `large_space_one_step_cooling_heating` | 大空间冷暖一步到位 | `large_space_coverage`, `cooling_heating_capacity_assurance` | 面向客厅或大空间，SKU 用大匹数、柜机/大风量、评论或市场承接解释一步到位。 | 只有柜机、大匹数或客厅宣传时不能强判。 | 大空间负向评论、制冷慢或高价竞品拦截时降级。 |
| 30 | `cooling_heating_performance_justifies_price` | 冷暖效果解释更高价格 | `cooling_heating_capacity_assurance`, `seasonal_reliability` | 在中高/高价格位置，冷暖能力、稳定性、评论和市场承接共同解释多花钱。 | 只有高价、品牌或冷暖口号，没有体验/市场补证时不能成立。 | 当前 AC 无 `premium_driver_estimated`，若 M12C 以拦截/机会/弱感知为主，不能直接判 `core_payment`。 |
| 40 | `long_term_energy_saving_offsets_price` | 长期省电抵消更高价格 | `energy_cost_efficiency`, `budget_configuration_efficiency` | 用户愿意为高能效多花钱，因为 APF/能效、长期使用任务、省电评论或 M12C 证据解释长期电费。 | 只有一级能效或省电口号时封顶弱表达。 | 耗电负评、APF 缺失或高价无市场承接时降级。 |
| 50 | `same_price_efficiency_capacity_gain` | 同价位能效/能力获得感 | `budget_configuration_efficiency`, `energy_cost_efficiency`, `cooling_heating_capacity_assurance` | 在同价位池里，用能效、冷暖能力、销量或评论证明选它更划算。 | 只有 `price_value`、补贴、低价表达时封顶弱表达。 | 核心能力缺口、销量不承接或 M12C 弱感知时降级。 |
| 60 | `low_price_core_ac_experience_intact` | 低价不明显牺牲核心冷暖体验 | `budget_configuration_efficiency`, `cooling_heating_capacity_assurance` | 在低/中低价位置，用冷暖能力、能效、评论或销量证明低价不是明显牺牲核心体验。 | 只有低价、补贴或性价比表达时不能进入产品核心理由。 | 制冷慢、噪音大、安装差或评论负向集中时转为风险。 |
| 70 | `sleep_room_quiet_comfort_assurance` | 卧室睡眠更安静舒适 | `sleep_quiet_comfort`, `comfortable_airflow_health` | 卧室睡眠场景下，低噪、睡眠模式、风感和评论证明夜间更安静舒适。 | 只有静音卖点，没有噪音参数、卧室任务或评论时封顶辅助/弱表达。 | 噪音负评、风感不适或缺评论时降级。 |
| 80 | `elderly_child_soft_wind_comfort` | 老人儿童房柔风不直吹 | `comfortable_airflow_health`, `sleep_quiet_comfort` | 老人儿童或家庭舒适场景下，柔风、防直吹和风感评论降低不适风险。 | 只有柔风或防直吹表达，缺场景/评论时封顶辅助。 | 直吹、风大、不舒适等负向评论时转为风险。 |
| 90 | `fresh_air_health_reduces_stuffy_risk` | 新风/净化减少闷和空气担忧 | `comfortable_airflow_health`, `operation_maintenance_convenience` | 新风、净化或除菌事实与空气评论、健康空气任务或 M12C 共同降低闷、异味和空气担忧。 | 只有新风、净化、除菌口号，没有风量/滤网/评论时封顶弱表达。 | 空气感知弱、异味负评或无参数补证时降级。 |
| 100 | `humidity_dehumidification_reassurance` | 潮湿环境除湿更安心 | `seasonal_reliability`, `comfortable_airflow_health` | 梅雨或潮湿环境下，除湿事实、潮湿评论和季节任务降低使用担忧。 | 只有除湿字样而无评论/场景补证时不能强判。 | G02 命中低于其他候选，后续小批量需重点复核；缺评论时降级。 |
| 110 | `self_cleaning_reduces_maintenance_risk` | 自清洁/防霉降低维护风险 | `operation_maintenance_convenience`, `comfortable_airflow_health` | 自清洁、防霉、维护评论或健康空气场景降低清洁、异味和长期维护风险。 | 只有自清洁口号时封顶辅助/弱表达。 | 异味、霉味、清洁无感或服务履约误用时降级。 |
| 120 | `small_room_installation_fit` | 小房间/租房安装适配 | `installation_space_fit`, `budget_configuration_efficiency` | 小房间、租房或安装受限场景下，挂机/小匹数/尺寸/价格和安装适配降低选择摩擦。 | 只有安装服务、低价或小巧宣传时不能强判。 | 安装投诉、外机限制、缺任务语义时降级。 |
| 130 | `smart_remote_control_less_friction` | 远程/智能控制减少操作摩擦 | `operation_maintenance_convenience` | App、远程、语音或智能控制减少日常开关、调温和家庭协同成本。 | 只有智能口号时封顶弱表达。 | 评论无感、系统难用或只有连接卖点时降级。 |

## 6. 证据域口径

| 证据域 | 说明 | 强证据条件 |
| --- | --- | --- |
| `param_fact` | M03B 参数事实，例如匹数、制冷量、制热量、循环风量、APF、噪音、新风量。 | 与购买理由直接相关，且不是 unknown。 |
| `fact_claim` | M04C 产品事实卖点，例如一级能效、速冷速热、防直吹、自清洁、智控。 | 有参数支撑或非纯服务/权益表达。 |
| `comment_perception` | M05C 用户评论感知，例如制冷快、省电、静音、风感、异味、安装。 | 正向感知和理由一致，负向评论不主导。 |
| `semantic_scene` | M09C/M10C/M11C 用户任务、目标客群和价值战场。 | 能证明卧室、客厅、老人儿童、租房、季节等场景适配。 |
| `semantic_market` | M11D 语义市场贡献。 | 同任务/客群/战场下有市场空间和 SKU 贡献。 |
| `market_acceptance` | M07 价格、销量、价格带和同池位置。 | 同形态/同匹数/同价位下有销量或价格位置承接。 |
| `claim_value` | M12C 用户卖点支付价值。 | `sales_driver_estimated` 可正向加分；弱/风险角色不能当正向充分条件。 |

## 7. 全局角色上限

| 情况 | 后续角色上限 |
| --- | --- |
| 缺 M12C 或 M11D | 不得直接输出 `core_payment`，最多 `supporting`，并标记缺失。 |
| 缺 M05C/M09C/M10C/M11C | 场景型、评论型和人群型理由必须降级。 |
| 只有一级能效、省电、新风、净化、静音、柔风、防直吹、自清洁、智能等厂家表达 | `weak_expression` 或 `supporting`，不得 `core_payment`。 |
| 只有低价、补贴、性价比或 `price_value` | `weak_expression`，除非同时有核心冷暖/能效证据和市场承接。 |
| 只有安装、售后、送装、权益、认证背书 | 不得进入产品核心购买理由。 |
| M12C 以 `high_price_competitor_intercept`、`opportunity_gap`、`weak_user_perception_claim`、`basic_threshold`、`price_up_opportunity` 或 `drag_factor` 为主 | 不得作为正向核心支付理由，需转入风险、机会或弱表达。 |
| 评论集中在噪音大、制冷慢、安装差、异味、耗电高 | 降低角色或生成 `risk_drag`。 |

## 8. G04 配置转换要求

G04 将本草案转成 loader/candidate generator 时必须满足：

- `category_code=AC` 能加载 AC taxonomy。
- TV taxonomy 不会污染 AC，AC taxonomy 也不会影响 TV。
- 候选生成只输出 value theme candidates 和 purchase reason candidates，不输出最终角色。
- 每个购买理由至少配置必要证据组、弱表达上限和冲突降级规则。
- G04 不得根据运行数据自动新增标准购买理由；新增或删除标准理由必须通过新的 taxonomy 版本。

## 9. G07 后续修订规则

G07 小批量验证后，如果发现主题或购买理由过宽、过窄、误命中或漏命中，应新增 taxonomy 版本，而不是覆盖历史版本。修订记录必须包含：

- 修订原因。
- 受影响 value_theme_code 或 purchase_reason_code。
- 受影响 SKU 样本。
- 新旧版本的匹配差异。
- 对竞品智能体消费契约的影响。
