# M07 市场画像与可比池基线 SOP 需求

## 0. 单模块强化状态

本文件已按“单模块逐一强化”要求完成第一轮强化，并在第二轮补充业务可读的价格区间、尺寸区间和区间内销量位置。下一步应按本文口径优化 M07 实现，再处理 M08 SKU 综合信号画像。

## 1. 模块目标

M07 把清洗后的周量价数据转换成 SKU 市场画像、价格/销量/销额分位、业务价格区间、业务尺寸区间、区间内销量位置、市场信号和可比池基线，为后续任务、客群、价值战场、战场内卖点价值分层、候选召回和竞品评分提供市场证据。

M07 要解决六个问题：

1. 把 `26W01` 到 `26W23` 这类周销售事实，沉淀成 SKU 级市场画像。
2. 在当前只有线上渠道、2 个平台、35 个型号的样例数据下，建立可解释的可比池。
3. 输出价格带、业务价格区间、尺寸段、业务尺寸区间、平台重合、销量/销额分位、趋势和样本充分性。
4. 为 M11.5 的 PSI/SSI、M12 候选召回、M13 市场压力评分提供市场基线。
5. 保证所有市场指标可追溯到 M02 market evidence，不直接读取原始表做结论。
6. 回答业务问题：“这个 SKU 在哪个价格区间，销量在该价格区间处于什么位置；这个 SKU 在哪个尺寸区间，销量在该尺寸区间处于什么位置。”

M07 是市场事实和可比池模块，不激活卖点、不判断战场、不选择竞品。

## 2. 设计依据

本模块依据：

- `cankao/CatForge_竞品生成SOP_详细指导_v1.md` 的 M07 要求。
- `cankao/catforge_sop_md/modules/M07_市场画像与可比池基线.md`。
- M01 已强化后的 `core3_clean_market_weekly`。
- M02 已强化后的 `market_fact` evidence。
- M03 已强化后的尺寸等标准参数。
- [00 真实样例数据基线](00_real_data_baseline.md)。
- 彩电 seed 中任务、客群、战场对市场信号的需求，例如价格分位、销量分位、价格/英寸、销售额分位。

## 3. 上游输入

### 3.1 必须输入

| 输入 | 来源 | 用途 |
| --- | --- | --- |
| `core3_clean_market_weekly` | M01 | 周销量、销额、均价、渠道、平台、周期 |
| `market_fact` evidence | M02 | 市场指标证据追溯 |
| `core3_clean_sku` | M01 | SKU 主数据、品牌、品类、覆盖情况 |
| `core3_extract_param_value` | M03 | 尺寸、分辨率等可比池基础参数 |
| `core3_sku_param_profile` | M03 | SKU 级参数摘要，主要用于尺寸段 |

### 3.2 不消费的输入

| 数据 | 处理 |
| --- | --- |
| 原始 `week_sales_data` | 不直接读取 |
| 卖点激活 | M07 不消费，M11.5/M12/M13 后续使用市场画像和卖点结果组合 |
| 评论信号 | M07 不消费，评论由 M06/M08 处理 |
| 竞品结果 | M07 是竞品生成上游 |

## 4. 本模块不做什么

- 不做卖点激活。
- 不判断用户任务、目标客群或价值战场。
- 不做战场内卖点价值分层。
- 不直接选择候选竞品或核心竞品。
- 不按品牌内外过滤。当前样例全是海信，海信型号之间也可互为竞品。
- 不生成线下渠道结论。当前数据只有线上渠道。
- 不用市场销量替代评论体验或参数能力。

## 5. 时间窗口口径

当前真实样例是周数据，不是完整 12 个月数据。M07 必须使用可配置分析窗口，不能写死 12 月。

首版窗口：

| 窗口 | 说明 |
| --- | --- |
| `full_observed_window` | 当前样例全量观测周，26W01-26W23 |
| `latest_week` | 每个 SKU 最新有数据的周 |
| `recent_4w` | 最近 4 个有效周 |
| `recent_8w` | 最近 8 个有效周 |
| `recent_12w` | 最近 12 个有效周 |

如果后续数据扩展到月维度或 52 周，M07 可以新增 `rolling_26w`、`rolling_52w`，但 MVP 不应把 23 周样例伪装成 12 个月。

## 6. 市场指标设计

### 6.1 SKU 级基础指标

| 指标 | 说明 |
| --- | --- |
| `sales_volume_total` | 观察期总销量 |
| `sales_amount_total` | 观察期总销额 |
| `price_wavg` | 销额 / 销量的加权均价 |
| `price_latest` | 最新有效周加权均价 |
| `price_median` | 周均价中位数 |
| `price_min` | 观察期最低有效均价 |
| `price_max` | 观察期最高有效均价 |
| `active_week_count` | 有效销售周数 |
| `latest_week` | 最新销售周 |
| `platform_share_json` | 平台销量/销额占比 |
| `main_platform` | 主销平台 |
| `channel_type` | 渠道大类，当前为线上 |

### 6.2 趋势指标

趋势应基于周序列计算：

| 指标 | 说明 |
| --- | --- |
| `price_change_recent_4w` | 近 4 周均价变化率 |
| `sales_growth_recent_4w` | 近 4 周销量变化率 |
| `amount_growth_recent_4w` | 近 4 周销额变化率 |
| `price_volatility` | 周均价波动 |
| `sales_volatility` | 周销量波动 |
| `promotion_suspect_flag` | 价格明显下探且销量变化明显的促销疑似标记 |

趋势指标必须标记样本周数，样本不足时不能输出高置信趋势。

### 6.3 尺寸与价格效率指标

依赖 M03 的 `screen_size_inch`：

| 指标 | 说明 |
| --- | --- |
| `screen_size_inch` | 屏幕尺寸 |
| `size_segment` | 50/55/65/75/85/100 等尺寸段 |
| `price_per_inch` | 加权均价 / 尺寸 |
| `price_percentile_in_size` | 同尺寸价格分位 |
| `volume_percentile_in_size` | 同尺寸销量分位 |
| `amount_percentile_in_size` | 同尺寸销额分位 |
| `price_gap_to_size_median` | 相对同尺寸中位价差 |
| `volume_gap_to_size_median` | 相对同尺寸中位销量差 |

缺尺寸参数时，不得强行放入尺寸可比池，应进入样本不足或参数缺失复核。

### 6.4 业务区间与区间内位置指标

M07 必须同时保留两套口径：

| 口径 | 作用 | 示例 |
| --- | --- | --- |
| 动态分位价格带 | 供评分、可比池和模型计算使用 | `low/mid_low/mid/mid_high/high` |
| 业务绝对价格区间 | 供业务解释、查询和报告展示使用 | `4000-5999 元`、`6000-8999 元` |
| 精确尺寸段 | 保留真实尺寸比较 | `55`、`65`、`75`、`85` |
| 业务尺寸区间 | 支撑业务观察和跨尺寸对比 | `55-65 寸主流大屏`、`75-85 寸大屏升级` |

必须新增或等价输出以下指标：

| 指标 | 说明 |
| --- | --- |
| `business_price_bucket_code` | 业务价格区间编码 |
| `business_price_bucket_label` | 业务价格区间中文展示，例如 `6000-8999 元` |
| `business_price_bucket_floor` | 区间下界，含边界 |
| `business_price_bucket_ceiling` | 区间上界，开区间；最高档可为 null |
| `price_bucket_sku_count` | 同价格区间可比 SKU 数 |
| `volume_rank_in_price_bucket` | 同价格区间销量降序排名，1 表示最高 |
| `volume_percentile_in_price_bucket` | 同价格区间销量分位，越高销量越强 |
| `volume_gap_to_price_bucket_median` | 与同价格区间中位销量差 |
| `amount_rank_in_price_bucket` | 同价格区间销额降序排名 |
| `amount_percentile_in_price_bucket` | 同价格区间销额分位 |
| `size_bucket_code` | 业务尺寸区间编码 |
| `size_bucket_label` | 业务尺寸区间中文展示 |
| `size_bucket_sku_count` | 同尺寸区间可比 SKU 数 |
| `volume_rank_in_size_bucket` | 同尺寸区间销量降序排名 |
| `volume_percentile_in_size_bucket` | 同尺寸区间销量分位 |
| `volume_gap_to_size_bucket_median` | 与同尺寸区间中位销量差 |
| `market_position_label` | 综合市场位置标签，例如 `区间头部/区间中上/区间中位/区间尾部/样本不足` |

区间内销量位置必须以 `sales_volume_total` 为主，销额位置作为辅助。不能用价格高低替代销量强弱。

### 6.5 业务价格区间生成规则

业务价格区间不能只输出 `low/mid/high`，也不能脱离真实数据随意写死。首版规则：

1. 优先读取品类已发布的业务价格区间配置。
2. 如果品类配置不存在，则基于当前批次 `full_observed_window.price_wavg` 自动生成候选区间。
3. 自动生成时先按价格分位切出候选边界，再把边界吸附到业务可读的整数价位，例如 500、1000、2000、5000 的倍数。
4. 相邻区间若样本数过少或边界重叠，必须合并。
5. 每次运行必须保存 `price_bucket_rule_version`、区间边界、区间样本数和是否为 `candidate`。
6. 报告和查询只展示有 SKU 覆盖的价格区间；空区间可保留在规则里，但不得被解释为市场事实。

### 6.6 业务尺寸区间生成规则

业务尺寸区间按品类配置。彩电首版以 M03B `screen_size_inch` 为尺寸轴：

| 区间 | 说明 |
| --- | --- |
| `<55` | 小尺寸/入门 |
| `55-65` | 主流尺寸 |
| `70-79` | 大屏升级 |
| `80-89` | 超大屏主流 |
| `90+` | 巨幕/旗舰尺寸 |

同时保留精确尺寸段 `50/55/65/75/85/100`，用于同尺寸池和精确比较。其他品类不能复用彩电尺寸规则，应由该品类的市场尺寸轴决定，例如空调可使用匹数或制冷量区间。

## 7. 市场信号设计

M07 需要输出下游可消费的市场信号，而不是只输出指标。

| 信号编码 | 业务含义 | 下游用途 |
| --- | --- | --- |
| `PRICE_PERCENTILE_HIGH` | 同池价格偏高 | M11/M13 判断高端或上探压力 |
| `PRICE_PERCENTILE_LOW` | 同池价格偏低 | M09/M13 判断性价比或价格拦截 |
| `SALES_VOLUME_STRONG` | 同池销量强 | M09/M11/M13 |
| `SALES_AMOUNT_STRONG` | 同池销额强 | M11/M13 |
| `PRICE_BUCKET_VOLUME_LEADER` | 同业务价格区间销量靠前 | M09/M11/M13 |
| `SIZE_BUCKET_VOLUME_LEADER` | 同业务尺寸区间销量靠前 | M09/M11/M13 |
| `PRICE_PER_INCH_VALUE` | 大屏价格效率好 | M09/M11/M13 |
| `RECENT_PRICE_DROP` | 近期价格下探 | M13 价格压力 |
| `RECENT_SALES_UP` | 近期销量上升 | M13 市场压力 |
| `PLATFORM_OVERLAP_STRONG` | 平台重合强 | M12/M13 |
| `SAMPLE_INSUFFICIENT` | 市场样本不足 | M16 复核 |

这些信号只表示市场状态，不表示卖点强弱或用户任务成立。

## 8. 可比池基线

### 8.1 可比池原则

可比池用于回答“这个 SKU 应该和哪些市场样本比较”，不是核心竞品列表。

首版可比池维度：

| 可比池类型 | 条件 |
| --- | --- |
| `same_size` | 同品类 + 同尺寸 |
| `adjacent_size` | 同品类 + 相邻尺寸，例如 75/85/100 |
| `same_price_band` | 同品类 + 观察期加权均价同价格带 |
| `size_price_band` | 同品类 + 同/相邻尺寸 + 同/相邻价格带 |
| `platform_overlap` | 同品类 + 平台重合 |
| `market_active` | 同品类 + 有效销售周数达标 |

M07 不建立 `battlefield` 或 `claim` 可比池。战场池和卖点池由 M11/M11.5/M12 基于 M07 市场池继续收窄。

### 8.2 价格带与业务价格区间

M07 需要同时输出动态价格带和业务价格区间。

动态价格带必须从当前样例数据动态生成，不能写死行业价格段，主要服务规则计算和可比池：

建议首版：

- 在品类内按 `price_wavg` 分位切分。
- 在尺寸段内再计算尺寸内价格分位。
- 保存 `price_band_method`，例如 `category_quantile`、`size_quantile`。

输出价格带：

```text
low / mid_low / mid / mid_high / high / unknown
```

业务价格区间必须输出绝对金额边界和中文展示，主要服务业务解释和查询。业务价格区间可以来源于品类配置，也可以由当前批次自动生成候选区间，但必须写明规则版本和候选状态。

### 8.3 样本充分性

| 状态 | 条件 |
| --- | --- |
| `sufficient` | 可比池 SKU 数达到阈值，且有效周数充足 |
| `limited` | 可比池 SKU 数偏少，但仍可参考 |
| `insufficient` | 可比池过小、价格/销量缺失或尺寸缺失 |

当前样例只有 35 个型号，同尺寸池可能很小，M07 必须允许 `limited` 或 `insufficient`，不能强行输出高置信分位。

## 9. 输出数据契约

### 9.1 `core3_sku_market_profile`

| 字段 | 说明 |
| --- | --- |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `sku_code` | SKU |
| `model_name` | 型号 |
| `brand_name` | 品牌 |
| `analysis_window` | full_observed_window/recent_4w/recent_8w/recent_12w |
| `period_start` | 起始周期 |
| `period_end` | 结束周期 |
| `active_week_count` | 有效周数 |
| `screen_size_inch` | 尺寸 |
| `size_segment` | 尺寸段 |
| `sales_volume_total` | 总销量 |
| `sales_amount_total` | 总销额 |
| `price_wavg` | 加权均价 |
| `price_latest` | 最新均价 |
| `price_median` | 周均价中位数 |
| `price_min` | 最低均价 |
| `price_max` | 最高均价 |
| `price_per_inch` | 每英寸价格 |
| `main_channel_type` | 主渠道，当前为线上 |
| `main_platform` | 主平台 |
| `platform_share_json` | 平台占比 |
| `price_change_recent_4w` | 近 4 周价格变化 |
| `sales_growth_recent_4w` | 近 4 周销量变化 |
| `price_percentile_in_category` | 品类价格分位 |
| `volume_percentile_in_category` | 品类销量分位 |
| `amount_percentile_in_category` | 品类销额分位 |
| `price_percentile_in_size` | 同尺寸价格分位 |
| `volume_percentile_in_size` | 同尺寸销量分位 |
| `amount_percentile_in_size` | 同尺寸销额分位 |
| `business_price_bucket_label` | 业务价格区间 |
| `price_bucket_sku_count` | 同价格区间 SKU 数 |
| `volume_rank_in_price_bucket` | 同价格区间销量排名 |
| `volume_percentile_in_price_bucket` | 同价格区间销量分位 |
| `size_bucket_label` | 业务尺寸区间 |
| `size_bucket_sku_count` | 同尺寸区间 SKU 数 |
| `volume_rank_in_size_bucket` | 同尺寸区间销量排名 |
| `volume_percentile_in_size_bucket` | 同尺寸区间销量分位 |
| `market_position_label` | 业务市场位置标签 |
| `market_confidence` | 市场画像置信度 |
| `sample_status` | sufficient/limited/insufficient |
| `quality_flags` | 缺价格、缺尺寸、样本少等 |
| `evidence_ids` | market evidence |
| `rule_version` | 规则版本 |

### 9.2 `core3_market_signal`

| 字段 | 说明 |
| --- | --- |
| `signal_id` | 市场信号 ID |
| `sku_code` | SKU |
| `signal_code` | 市场信号编码 |
| `signal_name` | 中文信号名 |
| `signal_value` | 信号值 |
| `signal_strength` | 强度 |
| `basis_metric` | 来源指标 |
| `comparison_scope` | category/size/pool |
| `confidence` | 置信度 |
| `evidence_ids` | 证据 |

### 9.3 `core3_comparable_pool_baseline`

| 字段 | 说明 |
| --- | --- |
| `pool_id` | 可比池 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `target_sku_code` | 目标 SKU |
| `pool_type` | same_size/adjacent_size/same_price_band/size_price_band/platform_overlap/market_active |
| `pool_condition_json` | 可比条件 |
| `candidate_sku_codes` | 池内 SKU |
| `pool_sku_count` | SKU 数 |
| `median_price` | 池内中位价 |
| `median_volume` | 池内中位销量 |
| `median_amount` | 池内中位销额 |
| `price_distribution_json` | 价格分布 |
| `volume_distribution_json` | 销量分布 |
| `amount_distribution_json` | 销额分布 |
| `sample_status` | sufficient/limited/insufficient |
| `basis` | 中文可比依据 |
| `evidence_ids` | 市场证据 |

### 9.4 `core3_market_pool_member`

| 字段 | 说明 |
| --- | --- |
| `pool_id` | 可比池 |
| `target_sku_code` | 目标 SKU |
| `member_sku_code` | 池内 SKU |
| `size_relation` | same/adjacent/different/unknown |
| `price_band_relation` | same/adjacent/higher/lower/unknown |
| `platform_overlap_score` | 平台重合分 |
| `price_gap_to_target` | 与目标价差 |
| `volume_gap_to_target` | 与目标销量差 |
| `member_market_confidence` | 成员市场置信度 |

### 9.5 `core3_market_bucket_coverage`

M07 应新增区间覆盖汇总表，便于回答“某价格区间有哪些 SKU”“某尺寸区间销量头部是谁”。

| 字段 | 说明 |
| --- | --- |
| `bucket_coverage_id` | 稳定 ID |
| `project_id` | 项目 |
| `category_code` | 品类 |
| `batch_id` | 批次 |
| `analysis_window` | 分析窗口 |
| `bucket_type` | `business_price_bucket`、`size_bucket`、`size_price_bucket` |
| `bucket_code` | 区间编码 |
| `bucket_label` | 中文展示 |
| `bucket_floor` | 价格或尺寸下界 |
| `bucket_ceiling` | 价格或尺寸上界 |
| `sku_count` | 区间 SKU 数 |
| `total_sales_volume` | 区间总销量 |
| `total_sales_amount` | 区间总销额 |
| `median_price` | 区间中位价格 |
| `median_volume` | 区间中位销量 |
| `top_sku_codes` | 区间销量头部 SKU |
| `distribution_json` | 区间价格、销量、销额分布 |
| `sample_status` | 样本状态 |
| `rule_version` | M07 规则版本 |
| `bucket_rule_version` | 区间规则版本 |

## 10. 85E7Q 样例要求

85E7Q 的 M07 必须能输出：

- 观察期为 26W01-26W23。
- 最新周、近 4 周、全观察期市场画像。
- 加权均价、最新均价、总销量、总销额。
- 专业电商/平台电商的平台占比。
- 85 寸同尺寸可比池，至少检查 `85D30QD`、`85E3Q`、`85E52Q`、`85E52S-PRO`、`85E5Q`、`85E5Q-PRO`、`85E5S-PRO`、`85E7Q`、`85E8Q`。
- 相邻尺寸可比池，至少检查 75 寸和 100 寸相关型号。
- 不按品牌过滤，因为当前样例全是海信，海信内部型号也可形成竞品关系。
- 如果同尺寸或同价池样本少，输出 `limited` 或 `insufficient`。
- 输出 85E7Q 所在业务价格区间、业务尺寸区间，以及它在两个区间内的销量排名和销量分位。

## 11. 真实数据约束

当前 205 样例数据对 M07 的硬约束：

- `week_sales_data` 有 1326 行，35 个型号，周期 26W01-26W23。
- 当前 `category=彩电`、`brand=海信`、`channel=线上`。
- 平台只有 `专业电商` 和 `平台电商`，渠道重合首版应基于 platform，不生成线下判断。
- 当前不是 12 个月数据，不能把指标命名为 12m，除非后续真实数据达到该窗口。
- M07 必须区分无销售数据、销量为 0、价格缺失、尺寸缺失。
- 85E7Q 有 46 行周销数据，市场画像应可生成。
- 同一周只有一个平台有数据不是质量问题，说明该 SKU 当前只在该平台售卖；M07 只记录平台覆盖和平台占比，不因此降级市场画像。

## 12. 与下游模块关系

### 给 M08 的承诺

- M08 使用 `core3_sku_market_profile` 和 `core3_market_signal` 合并 SKU 画像。
- M08 必须看到市场样本状态和置信度。

### 给 M09 的承诺

- 用户任务中的性价比购买、大屏换新、家庭观影等可以使用 M07 市场信号。
- M09 不能仅凭销量高直接判断任务成立。

### 给 M10 的承诺

- 目标客群中的性价比用户、家庭换新用户等可以使用价格带和销量信号。
- 客群仍需结合任务和评论线索。

### 给 M11 的承诺

- M11 的市场分来自 M07 的价格、销量、销额、平台和样本状态。
- M07 不直接给主战场/次战场结论。

### 给 M11.5 的承诺

- M11.5 使用 M07 的可比池、价格分布、销量分布计算 PSI/SSI。
- M07 不知道卖点 with/without，只提供池内市场基线。

### 给 M12/M13 的承诺

- M12 使用可比池召回候选。
- M13 使用市场画像、平台重合、价差、销量差和市场压力分。
- 两者不能直接读取原始周销表。

### 给 M15 的承诺

- 报告可以展示市场证据，例如同尺寸价格位置、平台重合、销量压力。
- 报告可以展示“该 SKU 位于 6000-8999 元区间，在该区间销量排名第 N / 共 M，销量分位 P”的业务话术。
- 报告可以展示“该 SKU 位于 75-85 寸大屏升级区间，在该区间销量排名第 N / 共 M”的业务话术。
- 报告不能把市场信号写成参数、卖点或评论结论。

## 13. 复核触发条件

以下情况进入复核或 warning：

- SKU 有参数/评论但无市场数据。
- 价格、销量、销额无法数值化或明显异常。
- 最新周缺失，导致价格最新值不可用。
- 尺寸缺失，无法进入尺寸可比池。
- 可比池样本数过少。
- 业务价格区间或业务尺寸区间内 SKU 数过少，区间内位置只能低置信展示。
- 价格趋势样本周不足。
- 平台占比异常集中或平台字段缺失。
- 某 SKU 市场画像较上一批波动异常。

## 14. 增量重算要求

| 输入变化 | M07 动作 | 下游影响 |
| --- | --- | --- |
| `market_fact` 新增/变化 | 重算对应 SKU 市场画像 | M08-M16 |
| M03 尺寸参数变化 | 重算尺寸段、价格/英寸和可比池 | M08-M16 |
| 平台/渠道清洗规则变化 | 重算平台占比和平台可比池 | M08-M16 |
| 分位和价格带规则变化 | 重算所有受影响 SKU 分位和可比池 | M07-M16 |
| 业务价格区间或业务尺寸区间规则变化 | 重算区间、区间内销量位置和区间覆盖 | M07-M16 |

如果 `core3_sku_market_profile` 和可比池 hash 未变化，不触发下游重算。

## 15. 验收标准

| 验收项 | 标准 |
| --- | --- |
| 35 个量价型号生成市场画像 | 必须 |
| 23 周样例不伪装成 12 月数据 | 必须 |
| 价格、销量、销额、平台占比可计算 | 必须 |
| 能输出 SKU 所在业务价格区间及区间内销量位置 | 必须 |
| 能输出 SKU 所在业务尺寸区间及区间内销量位置 | 必须 |
| 能输出价格/尺寸区间覆盖的 SKU 列表和头部 SKU | 必须 |
| 同品类/同尺寸/同价/平台可比池可生成 | 必须 |
| 样本不足状态可输出 | 必须 |
| 85E7Q 市场画像和 85 寸可比池可生成 | 必须 |
| 当前只有线上渠道时不生成线下判断 | 必须 |
| 不按品牌过滤竞品可能性 | 必须 |
| 所有市场指标有 market evidence | 必须 |
| M07 不做卖点、战场或竞品判断 | 必须 |
