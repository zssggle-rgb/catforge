# M12D AC 上游证据审计与样本确认

日期：2026-07-08

本审计用于启动 AC M12D「SKU 成交理由画像」。审计只做 205 `catforge_dev` 只读查询和规则边界确认，不实现 AC M12D 生产逻辑，不生成 taxonomy，不修改竞品智能体。

## 1. 审计结论

205 `catforge_dev` 在 2026-07-08 21:59 CST 的只读查询显示：

- AC 当前 serving scope 使用 `category_code=AC`，当前 AC market scope 为 155 个 SKU，批次为 `m00_20260624000202_1150a669`。
- AC 事实层已经足够启动 M12D-G02/G03：M03B 155、M04C 155、M07 155；M05C 有 144 个评论画像。
- AC 语义层覆盖 144 个 SKU：M09C/M10C/M11C 各 144；M11D `all_semantic_profiles` 覆盖 144，`fact_complete_with_comment` 覆盖 140。
- AC M12C 覆盖 140 个 SKU，6303 行 SKU-claim-context 量化记录，可支撑一部分强选择/销量转化证据，但不能覆盖全量 155 个 SKU。
- 当前可作为「强候选」进入后续画像生成的 SKU 为 140 个；11 个 SKU 只有事实/市场层、缺评论与语义；另有 4 个 SKU 有评论/部分语义但缺 M11D/M12C。
- M03B 当前存在 AC SKU 前缀的历史重复：`category_code=TV` 的旧批次和 `category_code=AC` 的当前批次各 155 行。后续 AC M12D 必须按 `category_code=AC` 和当前批次读取，不能只靠 `sku_code like 'AC%'`。
- 当前 AC M12C 正向角色只有 `sales_driver_estimated`，没有出现 `premium_driver_estimated`。因此首版 AC M12D 不能简单写“高价由卖点解释”，必须结合参数、评论、场景和市场承接。

结论：AC M12D 可以继续推进到 G02「AC 价值主题/购买理由候选提炼脚本」。但画像生成必须显式记录缺失状态，M12C 缺失或只有弱/风险角色时不得生成 `core_payment`。

## 2. 上游覆盖矩阵

AC current scope：

- `project_id=d8d2245b-358b-4a64-95cc-9d7f2341bd26`
- `category_code=AC`
- `batch_id=m00_20260624000202_1150a669`
- `market_window=full_observed_window`

| 模块 | 当前规则版本 | 当前 AC SKU 覆盖 | 行数 | 输入参照 | 缺口 | 对 AC M12D 的含义 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| M03B 参数事实 | `m03b_ac_param_profile_v0.1` | 155 | 155 | market 155 | 0 | 可作为全量硬参数证据；读取时必须过滤 `category_code=AC`。 |
| M04C 卖点事实 | `m04c_ac_claim_fact_profile_v0.1` | 155 | 155 | market 155 | 0 | 可作为全量卖点事实和厂家表达证据。 |
| M05C 评论事实 | `m05c_ac_comment_fact_profile_v0.1` | 144 | 144 | market 155 | 11 | 缺失 SKU 不得强写用户感知型购买理由。 |
| M07 市场画像 | `m07_market_profile_v1` | 155 | 155 | market 155 | 0 | 可作为全量价格、销量、价格带和市场承接证据。 |
| M09C 用户任务 | `m09c_ac_user_task_profile_v0.1` | 144 | 144 | market 155 | 11 | 缺失 SKU 不得强写任务型核心理由。 |
| M10C 目标客群 | `m10c_ac_target_group_profile_v0.1` | 144 | 144 | market 155 | 11 | 缺失 SKU 降低客群解释置信度。 |
| M11C 价值战场 | `m11c_ac_value_battlefield_profile_v0.1` | 144 | 144 | market 155 | 11 | 缺失 SKU 不能强判战场适配。 |
| M11D 语义市场图谱 | `m11d_semantic_market_allocation_v0.1` | 140 | 1489 | market 155 | 15 | 只对 140 个 SKU 支撑 fact-complete 语义市场分配。 |
| M12C 用户卖点支付价值 | `m12c_claim_value_quantification_v0.1` | 140 | 6303 | market 155 | 15 | 只对 140 个 SKU 支撑支付/销量转化价值判断。 |

补充说明：

- M11D 另有 `all_semantic_profiles` 口径覆盖 144 个 SKU、1506 行；M12D 首版用于强支付理由时应优先看 `fact_complete_with_comment`。
- M09C/M10C/M11C 表中另有 11 个 `is_current=false` 的 AC 记录；当前画像只能读取 `is_current=true`。

## 3. 画像就绪分层

| 分层 | SKU 数 | 处理方式 |
| --- | ---: | --- |
| `ready_strong_candidate` | 140 | 有事实、评论、语义、M11D 和 M12C，可进入 AC M12D 小批量强候选验证。 |
| `facts_market_only_comment_missing` | 11 | 有事实和市场，但缺评论/语义/M12C；只能生成降级画像或弱表达。 |
| `other_degraded` | 4 | 有评论或部分语义，但缺 M11D/M12C；不能生成强支付理由。 |

## 4. 缺失清单

### 4.1 缺 M05C/M09C/M10C/M11C 的 11 个 SKU

这些 SKU 有事实和市场，但当前缺评论事实、用户任务、目标客群和价值战场。

| SKU code | 品牌 | 型号 |
| --- | --- | --- |
| `AC00034959` | 美的 | KFR-72LW/QJ201-1 |
| `AC00036098` | TCL | KFR-35GW/JD61+B1 |
| `AC00036116` | 美的 | KFR-35GW/MJD2-1 |
| `AC00036291` | 奥克斯 | KFR-35GW/BPR3AEG28(B1) |
| `AC00036763` | 美的 | KFR-35GW/MJ1P |
| `AC00036792` | 美的 | KFR-72LW/MJ1P |
| `AC00036924` | 美的 | KFR-35GW/JY1 |
| `AC00038686` | 美的 | KFR-72LW/MJ2 |
| `AC00039044` | 统帅 | KFR-35GW/LTB2-1 |
| `AC00039082` | 晶弘 | KFR-35GW/JH5K1FNHAEB1 |
| `AC00039655` | 小米 | KFR-35GW-PG15/N2A1 |

### 4.2 额外缺 M11D/M12C 的 4 个 SKU

这些 SKU 不在上面的 11 个缺评论/语义清单里，但缺 fact-complete M11D 和 M12C。

| SKU code | 品牌 | 型号 | 边界 |
| --- | --- | --- | --- |
| `AC00038066` | 澳柯玛 | KFR-35GW/BPYT-1 | 评论样本极少，仅可做降级样本。 |
| `AC00038478` | 晶弘 | KFR-35GW/JHFNHAA1BT | 缺 M11D/M12C。 |
| `AC00038751` | 美的 | KFR-72LW/MWD2 | 缺 M11D/M12C。 |
| `AC00039165` | 美的 | KFR-72GW/KS2 | 有评论和任务，但缺 M11D/M12C，可验证降级。 |

## 5. AC M12C 角色分布

| M12C role | 行数 | SKU 数 | claim 数 | M12D 初始处理 |
| --- | ---: | ---: | ---: | --- |
| `high_price_competitor_intercept` | 1686 | 134 | 9 | 风险/竞品拦截，不直接正向。 |
| `opportunity_gap` | 1132 | 131 | 9 | 机会缺口，不直接正向。 |
| `weak_user_perception_claim` | 972 | 131 | 9 | 弱用户感知，封顶弱表达或辅助。 |
| `basic_threshold` | 889 | 128 | 5 | 基础门槛，不单独支撑核心理由。 |
| `drag_factor` | 672 | 98 | 9 | 拖累风险。 |
| `price_up_opportunity` | 547 | 91 | 9 | 加价机会，不等于已成立支付理由。 |
| `sales_driver_estimated` | 405 | 101 | 8 | 可作为正向销量转化证据，但仍需参数/评论/场景补证。 |

关键边界：

- 当前 AC M12C 没有 `premium_driver_estimated`；不能把高价 AC SKU 直接写成“贵得值”。
- `sales_driver_estimated` 是正向证据，但它只说明卖点和销量转化有关，仍需 M03B/M04C/M05C/M09C-M11D 和 M07 共同支撑。
- `high_price_competitor_intercept`、`opportunity_gap`、`price_up_opportunity` 不能被误读成核心成交理由。

## 6. AC 卖点事实维度分布

| M04C claim_dimension | 事实行数 | SKU 数 | M12D 边界 |
| --- | ---: | ---: | --- |
| `energy_efficiency` | 833 | 154 | 可进入长期用电成本主题；无 APF/评论/M12C 补证时封顶弱表达。 |
| `authority` | 302 | 151 | 认证/背书类，不能单独成为购买理由。 |
| `airflow_comfort` | 696 | 150 | 可进入舒适风主题；需风感评论/任务/参数补证。 |
| `service_fulfillment` | 420 | 136 | 服务履约，只能辅助或风险，不进产品核心理由。 |
| `health_clean_air` | 647 | 129 | 可进入健康空气主题；需新风量/净化参数/评论/M12C 补证。 |
| `temperature_performance` | 332 | 119 | 可进入冷暖能力主题；需能力参数、评论和市场承接补证。 |
| `smart_control` | 273 | 116 | 可进入操作省心主题；无场景/评论补证时弱化。 |
| `price_value` | 192 | 109 | 低价/性价比表达，必须有核心能力和市场承接补证。 |
| `durability_quality` | 207 | 108 | 品质/可靠性，需评论或长期使用任务补证。 |
| `installation_design` | 29 | 27 | 安装/空间适配可辅助，不单独强判核心理由。 |

## 7. 固定小批量验证 SKU

当前固定 15 个 AC 小批量验证 SKU，覆盖挂机、柜机/大匹数、高销量低价、高价舒适、低价智能、负向评论、缺 M12C 和缺评论语义等场景。

| 样本角色 | SKU code | 品牌 | 型号 | 价格带 | 销量 | 事实/评论/M12C 状态 |
| --- | --- | --- | --- | --- | ---: | --- |
| 任务起点：大空间高价 | `AC00038063` | 美的 | KFR-88LW/N8KS1-1U | high | 13916 | M03B/M04C/M05C/M09C/M10C/M11C/M11D/M12C 均有；M12C 9 行/3 claims。 |
| 任务起点：柜机价值型 | `AC00028640` | 小米 | KFR-72LW/N1A1 | mid_high | 15353 | 全链路均有；M12C 52 行/9 claims。 |
| 任务起点：高价舒适 | `AC00029751` | 格力 | KFR-72LW/NHAJ1BGJ | high | 8534 | 全链路均有；主任务为柔风不直吹；M12C 47 行/9 claims。 |
| 高销量低价挂机 | `AC00036139` | 华凌 | KFR-35GW/N8HA1III-P | low | 1131790 | 全链路均有；低价高销，验证低价不牺牲核心体验。 |
| 高销量中价挂机 | `AC00038662` | 美的 | KFR-35GW/KS2 | mid_low | 723648 | 全链路均有；验证主流能力/能效获得感。 |
| 低价智能挂机 | `AC00028642` | 小米 | KFR-35GW/N1A1 | low | 789265 | 全链路均有；验证智能/低价表达边界。 |
| 格力中高价挂机 | `AC00036739` | 格力 | KFR-35GW/NHMA1BG | mid | 433372 | 全链路均有；服务类卖点较多，验证服务不进核心理由。 |
| 柜机大空间高销量 | `AC00036333` | 美的 | KFR-72LW/N8KS1-1U | high | 121406 | 全链路均有；主任务为大空间覆盖。 |
| 低价且负向评论较多 | `AC00035996` | TCL | KFR-35GW/JD21+B1 | low | 523790 | 全链路均有；负向评论 13 条，验证风险降级。 |
| 中低价负向评论更多 | `AC00036020` | 华凌 | KFR-35GW/N8HE1IIPRO | mid_low | 236964 | 全链路均有；负向评论 21 条。 |
| 小匹数高销量 | `AC00038680` | 美的 | KFR-26GW/KS2 | mid_low | 489318 | 全链路均有；验证小房间/租房适配。 |
| 高价挂机 | `AC00034731` | 格力 | KFR-35GW/NHAE1BAJ | mid | 185591 | 全链路均有；高价/智能/舒适边界。 |
| 缺 M11D/M12C 样本 | `AC00039165` | 美的 | KFR-72GW/KS2 | high | 15356 | 有评论和任务，缺 M11D/M12C；验证强理由降级。 |
| 缺 M11D/M12C 且评论极少 | `AC00038066` | 澳柯玛 | KFR-35GW/BPYT-1 | low | 60022 | 评论 2 条，缺 M11D/M12C；验证低置信画像。 |
| 缺评论/语义/M12C 柜机 | `AC00034959` | 美的 | KFR-72LW/QJ201-1 | high | 30227 | 有参数/卖点/市场，缺评论/语义/M12C；验证弱表达路径。 |

说明：早期任务文档中的部分建议型号名是占位描述；本表以 205 当前 DB 读取到的 brand/model 为准。

## 8. 边界规则

### 8.1 可进入 `core_payment` 的证据

AC 首版中，一个购买理由要成为 `core_payment`，必须同时满足：

1. 至少两个证据域有效支撑。
2. 至少一个强证据域成立：参数事实、评论正向感知、M12C 正向销量/支付价值或市场承接。
3. 场景匹配成立：M09C/M10C/M11C 或 M11D 能证明它服务主/辅任务、客群或价值战场。
4. 没有硬冲突：明显负向评论、服务类误用、M12C `drag_factor`、高价弱销或竞品拦截不得被忽略。

### 8.2 只能进入 `weak_expression` 或 `supporting` 的证据

以下情况首版不得进入 `core_payment`：

- 只有一级能效/省电卖点，缺 APF/能效参数、评论、M12C 或市场承接补证。
- 只有新风/净化/除菌卖点，缺新风量/净化参数、评论或场景补证。
- 只有静音、柔风、防直吹表达，缺噪音/风感参数、卧室/老人儿童场景或评论补证。
- 只有低价、性价比、补贴或 `price_value` 表达，缺核心冷暖能力和市场承接。
- M04C `service_fulfillment`、安装、售后、权益、补贴、认证背书单独成立。
- M12C role 为 `weak_user_perception_claim`、`basic_threshold`、`opportunity_gap`、`price_up_opportunity`、`high_price_competitor_intercept` 或 `drag_factor`。

### 8.3 M12C 缺失降级

当 SKU 缺少 M12C 时：

1. `claim_value_status=missing`。
2. 不输出 `core_payment`。
3. 参数、卖点、评论、市场足够时，最多输出 `supporting`。
4. 只有厂家表达、位置标签或泛化价格价值时，输出 `weak_expression`。
5. 缺 M09C/M10C/M11C 时，同步降低场景/人群/战场置信度。

## 9. 规则问题清单

| 编号 | 问题 | 影响 | AC M12D 后续处理 |
| --- | --- | --- | --- |
| R1 | M03B 中 AC SKU 前缀同时存在 `category_code=TV` 旧批次和 `category_code=AC` 当前批次 | 只靠 SKU 前缀会把参数画像重复读入 | G02/G04 后续脚本和 ContextBuilder 必须过滤 `category_code=AC` 与当前批次。 |
| R2 | 11 个 SKU 缺 M05C/M09C/M10C/M11C | 不能支撑用户感知、任务、客群、战场理由 | 作为降级样本，最多弱表达/辅助，不强判核心理由。 |
| R3 | 额外 4 个 SKU 缺 M11D/M12C | 有事实/评论但缺支付价值和语义市场分配 | 画像要标 `claim_value_status=missing`，不得输出 `core_payment`。 |
| R4 | 当前 AC M12C 正向角色只有 `sales_driver_estimated` | 容易把销量转化证据误写成高价支付理由 | `sales_driver_estimated` 只能作为一类正向证据，必须组合参数/评论/场景/市场。 |
| R5 | `service_fulfillment` 覆盖 136 个 SKU | 服务履约容易被误当产品核心价值 | 服务/安装/售后/补贴只做辅助或风险，不进 `core_payment`。 |
| R6 | `energy_efficiency`、`airflow_comfort`、`health_clean_air` 覆盖广 | 广覆盖卖点区分度不足 | G02 需要按参数、评论、任务、M12C 和市场承接补证，不能只按命中率生成标准购买理由。 |
| R7 | 早期建议样本的型号名与 205 当前 DB 不完全一致 | 可能导致人工验证拿错型号 | 后续任务以 `sku_code` 为主键，以当前 DB brand/model 为展示。 |

## 10. 对 AC-M12D-G02 的要求

AC-M12D-G02 做候选提炼脚本时，必须满足：

- 只读 SELECT，不写库。
- 使用 `category_code=AC`、`product_category=AC` 和批次 `m00_20260624000202_1150a669`。
- M03B 必须排除 `category_code=TV` 的历史 AC 前缀记录。
- 候选提炼要覆盖参数、卖点、评论、语义、市场和 M12C 角色，而不是只统计卖点命中率。
- 输出候选报告时显式区分：
  - 可支撑核心支付理由的证据组合。
  - 只能支撑辅助理由的证据组合。
  - 只能支撑弱表达或风险的表达。
  - M12C/语义/评论缺失导致的降级。
- 不混入 TV 标准价值主题或 TV 标准购买理由。

AC-M12D-G02 可以继续推进。G01 的验收条件已经满足：AC M12D 能否启动、M12C 缺失降级边界、弱表达边界和小批量样本均已明确。
