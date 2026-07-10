# M12D 上游证据审计与样本确认

日期：2026-07-08

本审计用于启动 M12D「SKU 成交理由画像」。审计只做只读查询和规则边界确认，不实现 M12D 生产逻辑。

## 1. 审计结论

205 `catforge_dev` 在 2026-07-08 14:31 CST 的只读查询显示：

- TV 事实层已经足够启动 M12D：M03B 377、M04C 328、M05C 348、M07 377。
- TV 语义层仍未覆盖完整 serving scope：M09C/M10C/M11C 当前各 293，低于 market/param 377。
- TV M11D/M12C 当前只有 182 个 SKU，可支撑强支付价值判断的 SKU 子集仍明显小于事实层。
- M12D 必须生成 SKU 级画像状态，不能只输出强结论；M12C 缺失或语义层缺失时要降级为 `supporting`、`weak_expression` 或 `insufficient`。
- `tv_claim_value_price` 在海信 65E7Q 的 M04C `claim_codes` 中存在，但不在 `fact_claim_codes` 中，M12C 也没有该 claim 的量化行；因此只能作为价格价值弱表达候选，不能直接成为 `core_payment`。
- M04C 在 TV serving scope 中存在同 SKU 多批次重复行。6/23 增量批次有部分 SKU 的 `fact_claim_codes=[]`，但 6/19 批次有事实卖点。M12D ContextBuilder 必须按 SKU 合并或择优读取证据，不能机械取最新批次覆盖事实。

## 2. 上游覆盖矩阵

TV serving scope 批次：

1. `m00_20260623014631_c8630747`
2. `m00_20260619084551_857df63b`
3. `m00_20260613004311_d548f6dc`

| 模块 | 当前规则版本 | 当前 SKU 覆盖 | 输入参照 | 缺口 | 对 M12D 的含义 |
| --- | --- | ---: | ---: | ---: | --- |
| M03B 参数事实 | `m03b_tv_param_profile_v0.1` | 377 | market/param 377 | 0 | 可作为全量硬参数证据。 |
| M04C 卖点事实 | `m04c_tv_claim_fact_profile_v0.1` | 328 | claim 328 | 0 | 可作为有卖点 SKU 的事实/表达证据，但需处理多批合并。 |
| M05C 评论事实 | `m05c_tv_comment_fact_profile_v0.1` | 348 | comment evidence 348 | 0 | 可作为用户感知和负向冲突证据。 |
| M07 市场画像 | `m07_market_profile_v1` | 377 | market 377 | 0 | 可作为价格、销量、尺寸和市场承接证据。 |
| M09C 用户任务 | `m09c_tv_user_task_profile_v0.2` | 293 | market/param 377 | 84 | 缺失 SKU 不得强行输出任务型核心理由。 |
| M10C 目标客群 | `m10c_tv_target_group_profile_v0.2` | 293 | market/param 377 | 84 | 缺失 SKU 降低场景/人群置信度。 |
| M11C 价值战场 | `m11c_tv_value_battlefield_profile_v0.3` | 293 | market/param 377 | 84 | 缺失 SKU 不能计算战场强匹配。 |
| M11D 语义市场图谱 | `m11d_semantic_market_allocation_v0.1` | 182 | comment-ready 348 | 166 | 只对 182 个 SKU 支撑空间/销量分配。 |
| M12C 用户卖点支付价值 | `m12c_claim_value_quantification_v0.1` | 182 | comment-ready 348 | 166 | 只对 182 个 SKU 支撑强支付价值判断。 |

## 3. 固定小批量验证 SKU

| 样本 | SKU code | 样本角色 | 当前证据状态 |
| --- | --- | --- | --- |
| 海信 65E7Q | `TV00029112` | 目标样本；验证高端画质、游戏流畅、预算价值弱表达边界 | M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 都有；M12C 152 行，22 个 claim。 |
| 创维 65A7H PRO | `TV00029936` | 直接竞品；验证高端画质、家装/场景型体验 | M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 都有；M12C 155 行，22 个 claim。 |
| TCL 65Q9L PRO | `TV00027801` | 配置标杆；验证高端画质和游戏流畅强证据 | M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 都有；M12C 169 行，22 个 claim。 |
| 小米 L65MC-SP | `TV00029020` | 缺失降级样本；验证事实层有但语义/M12C 不足 | M03B/M04C/M05C/M07 有；M09C/M10C/M11C/M11D/M12C 缺失。 |
| 创维 65A6F ULTRA | `TV00028829` | 下探分流样本；验证低价高销和核心体验保留 | M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D/M12C 都有；M12C 178 行，22 个 claim。 |

关键市场事实快照：

| 样本 | 均价 | 销量 | 活跃周 | 65 寸价格带 | 同池价格分位 | 同池销量分位 |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| 海信 65E7Q | 5949.39 | 6023 | 24 | high | 0.9630 | 0.5802 |
| 创维 65A7H PRO | 5637.05 | 5199 | 24 | high | 0.9506 | 0.7037 |
| TCL 65Q9L PRO | 7088.00 | 4268 | 22 | high | 0.9753 | 0.1481 |
| 小米 L65MC-SP | 5852.58 | 3756 | 24 | high | 0.9506 | 0.4074 |
| 创维 65A6F ULTRA | 4415.49 | 7735 | 24 | high | 0.9136 | 0.7160 |

## 4. 样本证据摘要

| 样本 | M04C 事实卖点 | 服务类卖点 | M05C 评论句 | M11C 主战场 | M12C 角色分布摘要 |
| --- | ---: | ---: | ---: | --- | --- |
| 海信 65E7Q | 12 | 1 | 52 | `BF_PREMIUM_PICTURE_UPGRADE` | `premium_driver_estimated:3`, `sales_driver_estimated:9`, `basic_threshold:29`, `brand_claim_only:21`, `weak_user_perception_claim:31`, `opportunity_gap:34`, `price_up_opportunity:25` |
| 创维 65A7H PRO | 8 | 2 | 138 | `BF_PREMIUM_PICTURE_UPGRADE` | `premium_driver_estimated:6`, `sales_driver_estimated:3`, `basic_threshold:5`, `brand_claim_only:10`, `weak_user_perception_claim:20`, `drag_factor:18`, `opportunity_gap:64` |
| TCL 65Q9L PRO | 9 | 1 | 161 | `BF_PREMIUM_PICTURE_UPGRADE` | `premium_driver_estimated:4`, `sales_driver_estimated:8`, `basic_threshold:4`, `brand_claim_only:7`, `weak_user_perception_claim:20`, `drag_factor:28`, `opportunity_gap:63` |
| 小米 L65MC-SP | 13 | 0 | 40 | 缺失 | M12C 缺失 |
| 创维 65A6F ULTRA | 10 | 0 | 126 | `BF_PREMIUM_PICTURE_UPGRADE` | `premium_driver_estimated:3`, `sales_driver_estimated:26`, `basic_threshold:24`, `brand_claim_only:2`, `weak_user_perception_claim:31`, `opportunity_gap:53` |

说明：

- M12C 是 SKU-卖点-上下文粒度，不能按行数直接等同于“成交理由数”。
- `brand_claim_only`、`weak_user_perception_claim`、`drag_factor`、`opportunity_gap`、`price_up_opportunity` 必须先被 M12D 聚合和角色转换，不能直接进入 `core_payment`。
- 小米 L65MC-SP 用于验证 M12D 的缺失降级路径：它有事实层和市场层，但没有语义层/M12C 支撑。

## 5. 边界规则

### 5.1 可进入 `core_payment` 的证据

首版 M12D 中，一个锚点要成为 `core_payment`，必须同时满足：

1. 至少两个证据域有效支撑。
2. 至少一个强证据域成立：参数事实、M12C 正向支付价值、评论正向感知、市场承接。
3. 场景匹配不低：M09C/M10C/M11C 或 M11D 中能证明它服务主/辅任务、客群或价值战场。
4. 没有硬冲突：明显负向评论、服务类误用、M12C `drag_factor` 或高价弱销压力不得被忽略。

M12C 正向角色建议映射：

| M12C role | M12D 初始处理 |
| --- | --- |
| `premium_driver_estimated` | 可作为强支付价值证据。 |
| `sales_driver_estimated` | 可作为强选择/销量转化证据。 |
| `value_bundle_claim` | 只能在参数、评论、市场同时支撑时升级；默认不单独强判。 |
| `basic_threshold` | 支撑 `supporting` 或门槛解释，不单独支撑 `core_payment`。 |

### 5.2 只能进入 `weak_expression` 的证据

以下情况首版封顶为 `weak_expression`：

- 只有 `value_price`、`price_value`、价格价值表达、同价位、值得买等表达。
- 只有 M04C `claim_codes`，但不在 `fact_claim_codes`。
- 只有 `dimension_position_profile_json` 里的位置标签，例如 `price_value_mentioned`。
- M12C role 为 `brand_claim_only` 或 `weak_user_perception_claim`。
- 厂家主张、行业背书、认证表达缺少专属参数或用户/市场验证。
- M12C 缺失，且只剩卖点表达或语义标签。

### 5.3 服务信号和弱评论

- 服务履约、送装、售后、权益、补贴不进入产品核心成交理由。
- 服务类信号可以作为购买辅助或风险上下文，但不能成为 `core_payment`。
- 评论弱正向只能补充置信度；评论负向明显时要降低锚点角色，必要时进入 `risk_drag`。
- M05C 中 `service_excluded_sentence_count` 不得被当成产品体验正向证据。

### 5.4 M12C 缺失降级

当 SKU 缺少 M12C 时：

1. `claim_value_status=missing`。
2. 不输出 `core_payment`。
3. 参数、卖点、评论、市场足够时，最多输出 `supporting`。
4. 只有厂家表达、位置标签或泛化价格价值时，输出 `weak_expression`。
5. 缺 M09C/M10C/M11C 时，同步降低场景/人群/战场置信度。

小米 L65MC-SP 是本规则的验证样本。

## 6. 65E7Q 的 `value_price` 事实

海信 65E7Q 的 M04C 当前存在两条 serving scope 行：

| batch_id | raw_claim_count | fact_claim_count | has `tv_claim_value_price` | `fact_claim_codes` 中是否包含 |
| --- | ---: | ---: | --- | --- |
| `m00_20260619084551_857df63b` | 15 | 12 | 是 | 否 |
| `m00_20260623014631_c8630747` | 13 | 0 | 是 | 否 |

6/23 行的 `dimension_profile_json.energy_value` 显示：

```json
{
  "claim_codes": ["tv_claim_value_price"],
  "fact_claim_codes": [],
  "fact_claim_count": 0,
  "matched_claim_count": 1,
  "support_status_counts": {"not_param_applicable": 1}
}
```

6/23 行的 `dimension_position_profile_json` 显示：

```json
{
  "position_code": "price_value_mentioned",
  "position_name": "价格价值表达型",
  "basis_claim_codes": ["tv_claim_value_price"],
  "basis_fact_claim_codes": []
}
```

结论：65E7Q 的“同价位 / 值得买 / 价格价值”表达是真实被识别到的卖点表达，但不是事实卖点，也没有 M12C 量化行。M12D 中只能生成 `budget_value` 的 `weak_expression` 候选，不能生成 `core_payment`。

## 7. 规则问题清单

| 编号 | 问题 | 影响 | M12D 后续处理 |
| --- | --- | --- | --- |
| R1 | M04C 多批次同 SKU 重复，6/23 增量批次 `fact_claim_codes=[]` | Naive latest 读取会丢失 6/19 事实卖点 | ContextBuilder 必须按证据域合并/择优，而不是整行覆盖。 |
| R2 | M09C/M10C/M11C 只覆盖 293/377 | 84 个 SKU 缺任务、人群、战场证据 | Schema 要记录 `semantic_profile_status` 和降级原因。 |
| R3 | M11D/M12C 只覆盖 182/348 comment-ready SKU | 大量 SKU 缺支付价值和空间分配 | Schema 要记录 `claim_value_status`，缺失时禁止 `core_payment`。 |
| R4 | `tv_claim_value_price` 只在表达层成立 | 容易误写成“预算价值成交理由” | `budget_value` 需要价格位置、配置事实、评论价值感或 M12C 补强；否则封顶弱表达。 |
| R5 | M12C 一 claim 多上下文多行 | 行数不能直接解释为理由强度 | Scorer 要按 anchor 聚合 role、证据域和上下文，避免重复计数。 |
| R6 | 服务类卖点与产品卖点并存 | 可能误把服务履约当产品核心价值 | 服务类只进入 `weak_expression` 或风险/辅助，不进 `core_payment`。 |
| R7 | `opportunity_gap`、`price_up_opportunity`、`high_price_competitor_intercept` 语义不同 | 容易混成正向理由 | M12D 要区分机会、补强点、竞品拦截和风险，不直接进入核心成交理由。 |

## 8. 对 M12D-G02 的要求

M12D-G02 做 schema、存储和发布版本时，必须包含以下状态字段或等价结构：

- `param_profile_status`
- `claim_fact_status`
- `comment_profile_status`
- `market_profile_status`
- `semantic_profile_status`
- `semantic_market_status`
- `claim_value_status`
- `source_batch_ids_json`
- `source_merge_strategy`
- `missing_input_reasons_json`
- `role_downgrade_reasons_json`

首版发布质量统计至少要按以下口径分层：

| 分层 | 统计目标 |
| --- | --- |
| `ready_strong` | 有 M12C、语义层、评论和市场承接，允许出现 `core_payment`。 |
| `ready_degraded` | 缺 M12C 或语义层，但事实/评论/市场可输出辅助画像。 |
| `weak_expression_only` | 只有厂家表达、位置标签或价格价值弱表达。 |
| `missing_input` | 事实层不足，不能生成可靠画像。 |
| `review_required` | 证据冲突、多批合并异常、服务误用或高风险降级。 |

M12D-G02 可以继续推进。G01 的验收条件已经满足：`core_payment`、`weak_expression` 和 M12C 缺失降级边界均已明确。
