# M12D AC SKU成交理由画像需求

## 1. 模块定位

本文定义空调品类的 M12D SKU成交理由画像。它是 M12D 在 AC 品类上的独立扩展，不是 TV taxonomy 的复制，也不是竞品分析智能体内部的临时评分逻辑。

AC M12D 的目标是回答：

- 单个空调 SKU 凭什么被用户选择。
- 哪些理由能成为核心支付理由，哪些只是宣传表达、辅助理由或风险拖累。
- 竞品分析在比较本品和候选 SKU 时，应该读取哪些已发布的 AC M12D 结果。

## 2. 当前状态

截至本设计编写时：

- TV M12D 已完成从标准购买理由 taxonomy、单 SKU 画像、小批量验证、全量 TV batch 到下游竞品智能体消费的链路。
- AC 标准价值主题和标准购买理由尚未固化。
- AC SKU 尚未生成 M12D 画像版本。
- 竞品分析智能体可以分析空调候选集，但在 AC M12D 发布前不得把 TV M12D taxonomy 或 TV 画像逻辑当作 AC 成交理由来源。

因此，AC 竞品分析只有在 AC M12D 发布版本可读后，才能消费 `关键价值锚点可替代性` 维度；否则必须降级或明确缺失。

## 3. 业务问题

空调购买理由和电视不同。电视的高端画质、游戏流畅、客厅沉浸等价值主题不能直接解释空调成交。

AC M12D 需要解决四类问题：

1. 把空调参数、卖点、评论和市场承接翻译成用户购买理由，而不是参数清单。
2. 区分核心冷暖能力、长期电费、睡眠舒适、健康空气、安装适配、维护省心和预算效率。
3. 防止把一级能效、新风、静音、柔风、自清洁等厂家表达直接写成核心支付理由。
4. 给竞品分析提供可比较的 SKU 级成交理由画像，而不是在 pair 分析里临时生成锚点。

## 4. 上游输入

AC M12D 继续消费已发布的真实数据资产，不直接用原始四张表生成最终结论。

| 输入 | AC 用途 |
| --- | --- |
| M03B SKU 参数事实画像 | 识别匹数、安装形态、制冷量、制热量、循环风量、APF、能效等级、噪音、新风量、除湿、自清洁、柔风、防直吹和智能能力。 |
| M04C SKU 卖点事实画像 | 读取一级能效、变频、静音、新风、净化/除菌、防直吹、自清洁、大风量、速冷/速热、智控等卖点，并判断参数支撑等级。 |
| M05C SKU 评论事实画像 | 判断制冷快、制热效果、省电、噪音、直吹、异味、安装、售后、风感、房间大小匹配等用户感知。 |
| M07 SKU 市场画像 | 获取安装形态、匹数/能力段、价格带、均价、周均销量、销额、平台和观察窗口。 |
| M09C 用户任务画像 | 判断卧室睡眠、客厅大空间、老人儿童房、租房小房间、换新、极端天气等任务。 |
| M10C 目标客群画像 | 判断家庭、老人儿童、租房、改善型、预算敏感、品质升级等客群。 |
| M11C 价值战场画像 | 判断 SKU 落在冷暖能力、节能、舒适风、健康空气、静音、安装适配等战场的位置。 |
| M11D 语义市场图谱 | 获取任务、客群和战场的市场空间与销量权重。 |
| M12C 用户卖点支付价值 | 判断卖点是否形成高溢价、份额转化、客户获得价值、门槛、待激活、竞品拦截或价格压力。 |

缺失规则：

- M12C 缺失时可以生成降级画像，但不得把相关理由强判为 `core_payment`。
- M09C/M10C/M11C/M11D 缺失时，场景适配和人群解释必须降级。
- 参数缺失不等于能力不存在；只能标记 unknown，并降低置信度。

## 5. AC 标准价值主题

标准价值主题回答“用户获得什么可感知价值”。它用于解释和证据归因，不直接等同购买理由。

首版 AC 标准价值主题如下：

| value_theme_code | 中文名 | 业务含义 | 主要证据 |
| --- | --- | --- | --- |
| `cooling_heating_capacity_assurance` | 冷暖能力确定感 | 用户相信这台空调能覆盖目标空间，冷得快、热得稳，不容易买小或不够用。 | 匹数、制冷量、制热量、电辅热、循环风量、冷暖评论、极端天气任务。 |
| `energy_cost_efficiency` | 长期用电成本效率 | 用户相信长期使用电费更可控，一级能效/APF 能解释后续成本。 | APF、能效等级、变频、省电评论、M12C 客户获得价值、同价位能效差异。 |
| `sleep_quiet_comfort` | 睡眠静音舒适感 | 用户在卧室或夜间使用时更安静、不扰眠、温控稳定。 | 噪音 dB、睡眠模式、卧室任务、静音评论、风感评论。 |
| `comfortable_airflow_health` | 舒适风与健康空气 | 用户减少直吹、闷、异味或空气健康担忧。 | 防直吹、柔风、上下左右扫风、新风量、净化/除菌、异味/闷/空气评论。 |
| `large_space_coverage` | 大空间覆盖感 | 用户相信客厅、大卧室或大面积空间能被快速覆盖。 | 大匹数、柜机、循环风量、大空间任务、客厅评论和销量承接。 |
| `installation_space_fit` | 安装与空间适配 | 用户相信房型、安装位置和预算条件下能装得下、用得上。 | 挂机/柜机、内外机尺寸、安装评论、租房/小户型任务。 |
| `operation_maintenance_convenience` | 操作维护省心 | 用户减少清洁、控制、调温和日常维护成本。 | 自清洁、防霉、智控、App、语音、滤网提醒、维护评论。 |
| `budget_configuration_efficiency` | 预算配置效率 | 用户在预算内获得足够的核心冷暖、能效或舒适配置。 | 同匹数/同形态价格位置、核心配置、销量、性价比评论、M12C 客户获得价值。 |
| `seasonal_reliability` | 季节和极端天气可靠性 | 用户相信夏季高温、冬季低温、梅雨潮湿等季节压力下更稳定。 | 高温制冷、低温制热、除湿、极端天气任务、季节评论。 |

## 6. AC 标准购买理由

标准购买理由回答“用户为什么选择这个 SKU”。它必须是用户决策语言，不能只是参数名、卖点名或价值主题名。

首版 AC 标准购买理由如下：

| purchase_reason_code | 中文名 | 关联价值主题 |
| --- | --- | --- |
| `room_size_capacity_match_reduces_risk` | 匹数空间匹配降低买小风险 | `cooling_heating_capacity_assurance`, `installation_space_fit` |
| `large_space_one_step_cooling_heating` | 大空间冷暖一步到位 | `large_space_coverage`, `cooling_heating_capacity_assurance` |
| `cooling_heating_performance_justifies_price` | 冷暖效果解释更高价格 | `cooling_heating_capacity_assurance`, `seasonal_reliability` |
| `long_term_energy_saving_offsets_price` | 长期省电抵消更高价格 | `energy_cost_efficiency`, `budget_configuration_efficiency` |
| `same_price_efficiency_capacity_gain` | 同价位能效/能力获得感 | `budget_configuration_efficiency`, `energy_cost_efficiency`, `cooling_heating_capacity_assurance` |
| `sleep_room_quiet_comfort_assurance` | 卧室睡眠更安静舒适 | `sleep_quiet_comfort`, `comfortable_airflow_health` |
| `elderly_child_soft_wind_comfort` | 老人儿童房柔风不直吹 | `comfortable_airflow_health`, `sleep_quiet_comfort` |
| `fresh_air_health_reduces_stuffy_risk` | 新风/净化减少闷和空气担忧 | `comfortable_airflow_health`, `operation_maintenance_convenience` |
| `humidity_dehumidification_reassurance` | 潮湿环境除湿更安心 | `seasonal_reliability`, `comfortable_airflow_health` |
| `self_cleaning_reduces_maintenance_risk` | 自清洁/防霉降低维护风险 | `operation_maintenance_convenience`, `comfortable_airflow_health` |
| `small_room_installation_fit` | 小房间/租房安装适配 | `installation_space_fit`, `budget_configuration_efficiency` |
| `smart_remote_control_less_friction` | 远程/智能控制减少操作摩擦 | `operation_maintenance_convenience` |
| `low_price_core_ac_experience_intact` | 低价不明显牺牲核心冷暖体验 | `budget_configuration_efficiency`, `cooling_heating_capacity_assurance` |

## 7. 证据门槛

AC M12D 的核心原则是：卖点本身不是购买理由，只有被事实、评论、场景、市场或 M12C 支撑后，才可能升级。

| 表达 | 必要补证 | 不足时角色上限 |
| --- | --- | --- |
| 一级能效/省电 | APF 或能效等级、同价位能效差、用电成本评论、M12C 客户获得价值或市场承接。 | `weak_expression` |
| 新风/净化/除菌 | 新风量、滤网/净化参数、闷/异味/空气评论、健康空气任务或 M12C 支付价值。 | `weak_expression` |
| 静音/睡眠 | 噪音参数、睡眠模式、卧室任务、静音评论或夜间使用正反馈。 | `supporting` 或 `weak_expression` |
| 防直吹/柔风 | 风感技术、扫风能力、老人儿童房任务、风感评论或直吹负向对照。 | `supporting` 或 `weak_expression` |
| 大匹数/大风量 | 匹数、制冷/制热量、循环风量、大空间任务、客厅/大卧室评论和市场承接。 | `supporting` |
| 自清洁/防霉 | 自清洁参数、维护评论、异味/霉味评论或健康空气场景。 | `supporting` 或 `weak_expression` |
| 低价/性价比 | 同形态同匹数价格位置、核心能力不缺口、销量承接、评论价值感或 M12C 客户获得价值。 | `weak_expression` |
| 安装/售后/补贴 | 只能作为辅助、风险或购买摩擦，不得单独成为产品核心理由。 | 不得为 `core_payment` |

`core_payment` 必须满足：

- 至少两个证据域支撑。
- 至少一个强证据域来自参数事实、评论感知、M12C 支付价值或市场承接。
- 没有主导性负向评论或强价格压力冲突。
- 能用用户决策语言解释“为什么选择这个 SKU”。

## 8. 输出要求

AC M12D 输出沿用 M12D 通用画像结构，并增加 AC 品类约束：

| 输出 | 要求 |
| --- | --- |
| 基础信息 | `category_code=AC`、`project_id`、`version`、`batch_id`、`sku_code`、品牌型号、生成时间和 taxonomy 版本。 |
| 核心成交理由 | 最多 3 条，必须来自 AC 标准购买理由。 |
| 关键价值锚点 | 每个锚点包含购买理由 code、中文名、角色、证据强度、证据域、置信度、关联价值主题和解释。 |
| 弱表达与风险 | 标注只有厂家表达、参数缺失、评论冲突、安装/售后风险、价格压力或市场未承接。 |
| 下游消费字段 | `core_payment_anchors`、`supporting_anchors`、`weak_expression_anchors`、`risk_drag_anchors`。 |

不得输出 TV 价值主题、TV 购买理由或 TV 术语作为 AC 成交理由。

## 9. 与竞品智能体边界

AC M12D 负责：

- 生成单 SKU 的 AC 成交理由画像。
- 发布 AC taxonomy 版本和 AC M12D profile 版本。
- 标记每个 AC SKU 的核心支付理由、辅助理由、弱表达和风险拖累。

竞品分析智能体负责：

- 在 AC M12D 发布后读取目标 SKU 与候选 SKU 的已发布画像。
- 计算 pair 级关键价值锚点可替代性和替代压力。
- 当 AC M12D 不可用时，在报告中明确降级，不临时生成 AC M12D。

## 10. 验收标准

- AC 标准价值主题和标准购买理由以独立 taxonomy 固化，不复用 TV taxonomy。
- 小批量 AC SKU 能生成可读的成交理由画像，且核心理由都有证据链。
- 一级能效、新风、静音、柔风、低价等表达在无补证时不会被判为 `core_payment`。
- AC 全量 batch 有成功数、失败数、低置信画像数和需复核清单。
- 竞品分析智能体只消费已发布 AC M12D，不把 M12D 生产逻辑写进自身流程。
