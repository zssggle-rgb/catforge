# M07 市场画像与可比池基线开发任务

## 1. 模块目标

M07 的开发目标是把 M01/M02 形成的清洗周销量价事实和市场 evidence，结合 M03 的尺寸参数，转换成 SKU 市场画像、标准市场信号、可比池基线和可比池成员关系。

M07 要解决的工程问题：

1. 把 `26W01` 到 `26W23` 的周销量、销额、均价、渠道、平台数据，沉淀成 SKU + 分析窗口的市场画像。
2. 在当前 205 样例只有线上渠道、2 个平台、35 个量价型号的前提下，建立可解释、可复核、可追溯的市场可比池。
3. 计算价格、销量、销额、平台占比、价格/英寸、趋势、分位、价格带和样本充分性。
4. 输出下游可消费的标准市场信号，例如价格分位高、价格分位低、销量强、销额强、近期价格下探、样本不足。
5. 为 M08、M09、M10、M11、M11.5、M12、M13、M15、M16 提供市场事实和可比关系输入。
6. 保证市场画像、市场信号、可比池和池成员都能追溯到 M02 `market_fact` evidence，不直接读取原始 `week_sales_data` 做结论。

M07 必须固化以下边界：

- M07 是市场事实和可比池基线模块，不是竞品选择模块。
- M07 不消费 M04a/M04b 卖点激活。
- M07 不消费 M05/M06 评论信号。
- M07 不判断用户任务、目标客群或价值战场。
- M07 不做战场内卖点价值分层。
- M07 不召回候选竞品，不计算竞品评分，不输出核心三竞品。
- M07 不按品牌内外过滤。当前样例全是海信，海信型号之间也可进入可比池。
- M07 不输出线下渠道判断。当前样例只有线上渠道，平台差异只能基于 `专业电商`、`平台电商`。
- M07 不把 23 周样例伪装成 12 个月数据，不生成 `price_wavg_12m`、`sales_volume_12m` 等 12 月口径字段。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M07 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M07_market_profile_requirements.md` |
| M07 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M07_market_profile_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M01 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M01_cleaning_quality_design.md` |
| M02 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M02_evidence_atom_design.md` |
| M03 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M07_市场画像与可比池基线.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M01 已能输出 `core3_clean_sku` 和 `core3_clean_market_weekly`。
- M01 `core3_clean_market_weekly` 包含 `sku_code`、`model_name`、`brand_name`、`category_code`、`period_raw`、`period_type`、`period_week_index`、`period_parse_status`、`channel_type`、`platform_type`、`sales_volume`、`sales_amount`、`avg_price`、`price_check_status`、`clean_hash`、`record_status`。
- M02 已能输出 `core3_evidence_atom`，且 `evidence_type='market_fact'` 可按 SKU、周期、平台追溯市场事实。
- M03 已能输出 `core3_sku_param_profile`，且 `param_values_json` 或等价字段可提供 `screen_size_inch`、尺寸置信度、尺寸 evidence。
- INFRA 已提供 run context、hash 工具、runner 协议、状态枚举、复核 issue schema 和下游影响结构。

## 3. 本次范围

本次开发任务拆分覆盖 M07 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 4 张 M07 输出表 |
| model/schema | 新增市场画像、市场信号、可比池、池成员、runner、API、复核和下游影响 schema |
| repository | 只读 M01/M02/M03，写 M07 输出 |
| input service | 读取清洗 SKU、清洗周销量价、market evidence、尺寸参数 |
| window service | 构建 `full_observed_window`、`latest_week`、`recent_4w`、`recent_8w`、`recent_12w` |
| metric calculator | 计算加权均价、最新价、销量、销额、平台占比、趋势、价格/英寸 |
| percentile service | 计算品类、尺寸、可比池分位和动态价格带 |
| market signal builder | 生成标准市场信号 |
| comparable pool builder | 生成同尺寸、相邻尺寸、同价格带、尺寸价格带、平台重合、市场活跃池 |
| pool member builder | 生成目标 SKU 与池成员 SKU 的关系强度和价量差 |
| quality policy | 生成 warning、review_required、blocked |
| runner/API | 运行入口、运营查询接口和证据钻取接口 |
| 测试 | 单元、集成、边界、越界、85E7Q fixture |
| 增量 | input_fingerprint、result_hash、is_current、下游影响登记 |

本次不做：

- 不实现 M08 SKU 综合信号画像。
- 不实现 M09 用户任务。
- 不实现 M10 目标客群。
- 不实现 M11 价值战场。
- 不实现 M11.5 战场内卖点价值分层。
- 不实现 M12 候选召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 三槽位选择。
- 不实现 M15 证据卡和高层报告。
- 不实现前端页面。
- 不部署到 205。
- 不让 M07 API 直接服务高层页面的竞品结论。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/market_profile_schemas.py
apps/api-server/app/services/core3_real_data/market_profile_repositories.py
apps/api-server/app/services/core3_real_data/market_input_service.py
apps/api-server/app/services/core3_real_data/market_window_service.py
apps/api-server/app/services/core3_real_data/sku_market_metric_calculator.py
apps/api-server/app/services/core3_real_data/market_percentile_service.py
apps/api-server/app/services/core3_real_data/market_signal_builder.py
apps/api-server/app/services/core3_real_data/comparable_pool_builder.py
apps/api-server/app/services/core3_real_data/market_pool_member_builder.py
apps/api-server/app/services/core3_real_data/market_quality_policy.py
apps/api-server/app/services/core3_real_data/market_downstream_impact_service.py
apps/api-server/app/services/core3_real_data/market_profile_service.py
apps/api-server/app/services/core3_real_data/market_profile_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `market_profile_schemas.py` | M07 内部 typed contracts、runner 输入输出、复核对象 |
| `market_profile_repositories.py` | M07 输入读取和输出写入 |
| `market_input_service.py` | 组装 M01/M02/M03 输入和 input fingerprint |
| `market_window_service.py` | 构建分析窗口、最新周、窗口边界 |
| `sku_market_metric_calculator.py` | SKU + 窗口基础市场指标计算 |
| `market_percentile_service.py` | 分位、价格带、样本状态计算 |
| `market_signal_builder.py` | 标准市场信号生成 |
| `comparable_pool_builder.py` | 可比池条件、池统计、池样本状态 |
| `market_pool_member_builder.py` | 池成员关系、平台重合、价量差、关系强度 |
| `market_quality_policy.py` | warning、review_required、blocked 规则 |
| `market_downstream_impact_service.py` | M07 变化到 M08-M16 的影响登记 |
| `market_profile_service.py` | M07 模块编排 service |
| `market_profile_runner.py` | M07 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0014_core3_real_data_market_profile.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0014_core3_real_data_market_profile.py` | 新增 M07 4 张输出表 |
| `core3_real_data.py` schema | 导出 M07 API request/response |
| `core3_real_data.py` API | 增加 M07 运行、查询、证据钻取 API |
| `constants.py` | 补 M07 窗口、价格带、池类型、市场信号、样本状态枚举 |
| `runner.py` | 注册 M07 runner，不改变已有模块逻辑 |
| `conftest.py` | 增加 M07 M01/M02/M03 输入 fixture、85E7Q 市场 fixture |

如果 Alembic 当前最新编号不是 `0013`，M07 编码时按最新编号顺延，但 migration 内容仍只能包含 M07 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m07_market_input_service.py
apps/api-server/tests/core3_real_data/test_m07_market_window_service.py
apps/api-server/tests/core3_real_data/test_m07_metric_calculator.py
apps/api-server/tests/core3_real_data/test_m07_percentile_service.py
apps/api-server/tests/core3_real_data/test_m07_market_signal_builder.py
apps/api-server/tests/core3_real_data/test_m07_comparable_pool_builder.py
apps/api-server/tests/core3_real_data/test_m07_pool_member_builder.py
apps/api-server/tests/core3_real_data/test_m07_quality_policy.py
apps/api-server/tests/core3_real_data/test_m07_repositories.py
apps/api-server/tests/core3_real_data/test_m07_runner.py
apps/api-server/tests/core3_real_data/test_m07_api.py
apps/api-server/tests/core3_real_data/test_m07_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m07_85e7q_fixture.py
apps/api-server/tests/core3_real_data/test_m07_no_12m_fields.py
```

### 4.4 只读依赖文件

```text
apps/api-server/app/services/core3_real_data/cleaning_repositories.py
apps/api-server/app/services/core3_real_data/cleaning_schemas.py
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
apps/api-server/app/services/core3_real_data/evidence_atom_schemas.py
apps/api-server/app/services/core3_real_data/param_extraction_repositories.py
apps/api-server/app/services/core3_real_data/param_extraction_schemas.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
```

M07 repository 可以引用上述 M01/M02/M03 repository，但不能绕过它们直接访问原始表。

## 5. 不允许改文件

除非用户单独授权，本任务不允许修改：

```text
apps/api-server/app/services/core3_mvp/*
apps/factory-web/src/pages/*
apps/factory-web/src/routes/*
apps/factory-web/src/components/*
deployment/*
docker-compose*
nginx*
scripts/deploy.sh
```

不允许改动的业务对象：

- 原始四表结构。
- M00/M01/M02/M03 输出表结构。
- M04a/M04b 卖点激活逻辑。
- M05/M06 评论逻辑。
- M08-M16 结果表。
- 旧 `core3_mvp` 服务和页面。
- 前端高层报告页面。
- 205 部署配置。

不允许引入的行为：

- 直接读取原始 `week_sales_data`。
- 直接读取原始 `attribute_data` 获取尺寸。
- 读取 M04b 卖点激活来建立可比池。
- 读取 M06 评论信号来建立可比池。
- 输出 `task_code`、`target_group_code`、`battlefield_code`、`candidate_sku_code`、`competitor_role` 或核心三竞品结论。
- 按品牌内外过滤可比成员。
- 输出线下渠道判断。
- 输出 `price_wavg_12m`、`sales_volume_12m`、`sales_amount_12m` 等 12 月字段。
- 在测试中调用外部 LLM。
- 用 M07 API 给前端拼接“正面对打竞品”“主战场”等业务结论。

## 6. 数据库迁移任务

### 6.1 迁移文件

新增迁移：

```text
apps/api-server/alembic/versions/0014_core3_real_data_market_profile.py
```

迁移只新增 M07 输出表，不修改 M01/M02/M03 表，不修改旧 MVP 表。

### 6.2 新增表

| 表 | 粒度 | 说明 |
| --- | --- | --- |
| `core3_sku_market_profile` | SKU + 分析窗口 | SKU 市场画像 |
| `core3_market_signal` | SKU + 分析窗口 + 信号 | 下游可消费的标准市场信号 |
| `core3_comparable_pool_baseline` | 目标 SKU + 可比池类型 + 分析窗口 | 可比池定义和池统计 |
| `core3_market_pool_member` | 可比池 + 目标 SKU + 成员 SKU | 池成员市场关系 |

### 6.3 通用字段

4 张表必须包含：

```text
project_id
category_code
batch_id
run_id
module_run_id
rule_version
input_fingerprint
result_hash
is_current
processing_status
review_required
review_status
review_reason_json
created_at
updated_at
```

通用约束：

- `category_code` MVP 固定为 `TV`，但字段不能省略。
- `rule_version` 首版建议 `m07_market_profile_v1`。
- `processing_status` 使用 INFRA 枚举：`success`、`warning`、`review_required`、`blocked`、`failed`。
- `review_status` 使用 INFRA 枚举：`auto_pass`、`review_required`、`approved`、`rejected`、`waived`。
- 历史版本不删除，旧记录通过 `is_current=false` 失效。

### 6.4 `core3_sku_market_profile`

必须字段：

```text
sku_market_profile_id
profile_key
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
brand_name
category_name
analysis_window
period_start_raw
period_end_raw
period_start_week_index
period_end_week_index
global_latest_week_index
sku_latest_week_index
latest_week_gap
active_week_count
market_row_count
platform_count
screen_size_inch
size_segment
size_param_confidence
sales_volume_total
sales_amount_total
price_wavg
price_latest
price_median
price_min
price_max
price_per_inch
main_channel_type
main_platform
channel_share_json
platform_share_json
price_change_recent_4w
sales_growth_recent_4w
amount_growth_recent_4w
price_volatility
sales_volatility
promotion_suspect_flag
price_band_category
price_band_size
price_band_method
price_percentile_in_category
volume_percentile_in_category
amount_percentile_in_category
price_percentile_in_size
volume_percentile_in_size
amount_percentile_in_size
price_gap_to_category_median
price_gap_to_size_median
volume_gap_to_size_median
amount_gap_to_size_median
market_confidence
confidence_level
sample_status
quality_flags
evidence_ids
market_evidence_ids
param_evidence_ids
rule_version
input_fingerprint
result_hash
is_current
processing_status
review_required
review_status
review_reason_json
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `sku_market_profile_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, analysis_window, rule_version` |
| 普通索引 | `sku_code, analysis_window` |
| 普通索引 | `analysis_window, size_segment` |
| 普通索引 | `price_band_category` |
| 普通索引 | `price_band_size` |
| 普通索引 | `sample_status` |
| 普通索引 | `market_confidence` |
| 普通索引 | `review_required` |
| GIN 索引 | `channel_share_json`、`platform_share_json`、`quality_flags`、`evidence_ids` |

### 6.5 `core3_market_signal`

必须字段：

```text
market_signal_id
signal_key
sku_market_profile_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
analysis_window
signal_code
signal_name
signal_value
signal_strength
signal_level
basis_metric
basis_value_json
comparison_scope
comparison_scope_key
polarity
downstream_usage_json
confidence
confidence_level
sample_status
quality_flags
evidence_ids
rule_version
input_fingerprint
result_hash
is_current
processing_status
review_required
review_status
review_reason_json
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `market_signal_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, analysis_window, signal_code, comparison_scope, rule_version` |
| 普通索引 | `sku_code, signal_code` |
| 普通索引 | `analysis_window, signal_code` |
| 普通索引 | `signal_level` |
| 普通索引 | `comparison_scope` |
| 普通索引 | `review_required` |
| GIN 索引 | `basis_value_json`、`downstream_usage_json`、`quality_flags`、`evidence_ids` |

### 6.6 `core3_comparable_pool_baseline`

必须字段：

```text
pool_id
pool_key
project_id
category_code
batch_id
run_id
module_run_id
target_sku_code
target_model_name
analysis_window
pool_type
pool_condition_json
candidate_sku_codes
pool_sku_count
valid_member_count
target_included
target_size_segment
target_price_band
median_price
median_volume
median_amount
price_distribution_json
volume_distribution_json
amount_distribution_json
platform_distribution_json
pool_confidence
sample_status
basis
quality_flags
evidence_ids
rule_version
input_fingerprint
result_hash
is_current
processing_status
review_required
review_status
review_reason_json
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `pool_id` |
| 唯一键 | `project_id, category_code, batch_id, target_sku_code, analysis_window, pool_type, rule_version` |
| 普通索引 | `target_sku_code, pool_type` |
| 普通索引 | `analysis_window, pool_type` |
| 普通索引 | `sample_status` |
| 普通索引 | `pool_sku_count` |
| GIN 索引 | `pool_condition_json`、`candidate_sku_codes`、`price_distribution_json`、`quality_flags`、`evidence_ids` |

### 6.7 `core3_market_pool_member`

必须字段：

```text
pool_member_id
pool_id
project_id
category_code
batch_id
run_id
module_run_id
target_sku_code
member_sku_code
analysis_window
member_model_name
member_brand_name
is_target_self
size_relation
price_band_relation
platform_overlap_score
channel_overlap_score
price_gap_to_target
price_gap_pct_to_target
volume_gap_to_target
amount_gap_to_target
member_price_percentile_in_pool
member_volume_percentile_in_pool
member_amount_percentile_in_pool
member_market_confidence
relation_strength
quality_flags
evidence_ids
rule_version
input_fingerprint
result_hash
is_current
processing_status
review_required
review_status
review_reason_json
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `pool_member_id` |
| 唯一键 | `pool_id, target_sku_code, member_sku_code, rule_version` |
| 普通索引 | `target_sku_code, member_sku_code` |
| 普通索引 | `pool_id` |
| 普通索引 | `size_relation` |
| 普通索引 | `price_band_relation` |
| 普通索引 | `platform_overlap_score` |
| GIN 索引 | `quality_flags`、`evidence_ids` |

### 6.8 downgrade 要求

`downgrade()` 只删除 M07 四张表和对应索引，不触碰 M00-M06、M08-M16、旧 MVP 表和原始四表。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

如果项目仍集中使用 `apps/api-server/app/models/entities.py`，则新增 M07 四张表 model；如果 INFRA 已拆 `core3_real_data` 独立 model 文件，则按 INFRA 约定放置。

model 要求：

- 字段名与 migration 一致。
- JSON 字段使用 PostgreSQL JSONB。
- 数值字段使用可控精度 Numeric，不使用 float 存储金额。
- 时间字段使用 timezone-aware `DateTime(timezone=True)`。
- `is_current`、`review_required`、`promotion_suspect_flag`、`target_included`、`is_target_self` 明确默认值。

### 7.2 Pydantic/internal schema

`market_profile_schemas.py` 必须定义：

```text
M07AnalysisWindow
M07PriceBand
M07PoolType
M07SampleStatus
M07MarketSignalCode
M07SignalLevel
M07Polarity
M07MarketInputRow
M07MarketEvidenceRef
M07SkuSizeInput
M07AnalysisWindowSpec
M07SkuMarketMetrics
M07PercentileResult
M07MarketSignalRecord
M07ComparablePoolRecord
M07MarketPoolMemberRecord
M07QualityIssue
M07DownstreamImpact
M07RunRequest
M07RunResult
```

### 7.3 API schema

`apps/api-server/app/schemas/core3_real_data.py` 导出：

```text
Core3M07RunRequest
Core3M07RunResponse
Core3SkuMarketProfileResponse
Core3MarketSignalResponse
Core3ComparablePoolResponse
Core3MarketPoolMemberResponse
Core3M07QualityIssueResponse
```

API response 必须使用中文业务字段或清晰中文说明字段，不能把内部枚举直接暴露给高层页面。运营 API 可以返回技术字段，但必须保留 `display_name`、`business_note` 或 `basis`。

## 8. repository 任务

### 8.1 Repository 划分

`market_profile_repositories.py` 建议包含：

| Repository | 访问表 |
| --- | --- |
| `M07CleanSkuRepository` | 只读 `core3_clean_sku` |
| `M07CleanMarketWeeklyRepository` | 只读 `core3_clean_market_weekly` |
| `M07MarketEvidenceRepository` | 只读 M02 `core3_evidence_atom` where `evidence_type='market_fact'` |
| `M07SkuParamProfileRepository` | 只读 M03 `core3_sku_param_profile` |
| `M07MarketProfileRepository` | 写 `core3_sku_market_profile` |
| `M07MarketSignalRepository` | 写 `core3_market_signal` |
| `M07ComparablePoolRepository` | 写 `core3_comparable_pool_baseline` |
| `M07MarketPoolMemberRepository` | 写 `core3_market_pool_member` |

### 8.2 输入读取要求

读取规则：

1. 只读取当前 `project_id + category_code + batch_id`。
2. 只读取 `record_status='active'` 的 `core3_clean_market_weekly`。
3. 只读取当前有效的 M02 `market_fact` evidence。
4. 只读取 M03 当前 `core3_sku_param_profile`，使用其尺寸画像，不回读原始属性表。
5. 查询必须支持 `sku_scope`，但分位和可比池若依赖全局分布，必须读取同批次全体 SKU profile 作为上下文。

### 8.3 写入要求

写入规则：

1. 每张输出表按稳定逻辑键计算 ID。
2. 重跑时先用 `input_fingerprint` 和 `result_hash` 判断是否可复用。
3. 内容变化时旧 current 记录置为 `is_current=false`，插入新记录。
4. 不允许删除历史记录实现 current。
5. 同一逻辑唯一键出现多条 current 时，runner 必须失败并生成 blocked 复核问题。

## 9. service 任务

### 9.1 `MarketInputService`

职责：

- 读取清洗 SKU、清洗市场周事实、market evidence、M03 尺寸参数。
- 将 `sku_code + period_raw + platform_type` 与 market evidence 建立索引。
- 生成 `input_fingerprint`。
- 校验上游模块是否完成。

输入 fingerprint 必须至少包含：

```text
sorted(clean_market_weekly.clean_hash)
sorted(market_fact.evidence_id/evidence_hash)
screen_size_inch profile_hash
window_rule_version
price_band_rule_version
pool_rule_version
```

### 9.2 `MarketWindowService`

必须支持窗口：

```text
full_observed_window
latest_week
recent_4w
recent_8w
recent_12w
```

窗口规则：

- `full_observed_window` 使用当前批次最小到最大有效周。
- `latest_week` 使用每个 SKU 的最新有效周。
- `recent_4w/8w/12w` 使用全局最新周向前回溯。
- 周期无法解析的行可参与全量汇总，但不能参与趋势。
- SKU 在窗口内无有效行时仍生成 profile，`sample_status='unknown'`。

### 9.3 `SkuMarketMetricCalculator`

必须计算：

```text
sales_volume_total = sum(valid sales_volume)
sales_amount_total = sum(valid sales_amount)
price_wavg = sales_amount_total / sales_volume_total
price_latest = latest_week sales_amount / latest_week sales_volume
price_median = median(weekly avg_price)
price_min = min(weekly avg_price)
price_max = max(weekly avg_price)
price_per_inch = price_wavg / screen_size_inch
platform_share_json
channel_share_json
main_platform
main_channel_type
price_change_recent_4w
sales_growth_recent_4w
amount_growth_recent_4w
price_volatility
sales_volatility
promotion_suspect_flag
```

特殊规则：

- `sales_volume is null`：该行不参与销量和价格计算，标记 `missing_sales_volume`。
- `sales_volume=0 and sales_amount=0`：保留为有效零销量周，不参与价格分母。
- `sales_volume=0 and sales_amount>0`：标记 `market_amount_without_volume`，价格不可计算。
- `avg_price` 与 `sales_amount/sales_volume` 不一致时，以 M01 `price_check_status` 为准，保留 quality flag 并降置信。
- `price_wavg` 必须用销额/销量计算，不使用简单周均价平均。

### 9.4 `MarketPercentileService`

必须计算三个 scope：

| scope | 指标 |
| --- | --- |
| 品类 | 价格、销量、销额分位 |
| 同尺寸 | 价格、销量、销额分位 |
| 可比池 | 池成员价格、销量、销额分位 |

分位规则：

```text
percentile_rank = count(values <= target_value) / count(valid values)
```

价格带规则：

| 价格带 | 分位范围 |
| --- | --- |
| `low` | `0.00-0.20` |
| `mid_low` | `0.20-0.40` |
| `mid` | `0.40-0.60` |
| `mid_high` | `0.60-0.80` |
| `high` | `0.80-1.00` |
| `unknown` | 样本不足或价格缺失 |

样本规则：

- scope 内有效 SKU 数 `< 3`：`sample_status='insufficient'`。
- scope 内有效 SKU 数 `3-5`：`sample_status='limited'`。
- scope 内有效 SKU 数 `>= 6` 且有效周数充足：可为 `sufficient`。

### 9.5 `MarketSignalBuilder`

必须生成以下信号：

| 信号编码 | 中文名 | 触发条件 |
| --- | --- | --- |
| `PRICE_PERCENTILE_HIGH` | 价格分位高 | 品类或同尺寸价格分位 `>=0.75` |
| `PRICE_PERCENTILE_LOW` | 价格分位低 | 品类或同尺寸价格分位 `<=0.25` |
| `SALES_VOLUME_STRONG` | 销量强 | 销量分位 `>=0.75` |
| `SALES_AMOUNT_STRONG` | 销额强 | 销额分位 `>=0.75` |
| `PRICE_PER_INCH_VALUE` | 每英寸价格效率好 | 价格/英寸分位 `<=0.30` |
| `RECENT_PRICE_DROP` | 近期价格下探 | 近 4 周价格下降超过阈值 |
| `RECENT_SALES_UP` | 近期销量上升 | 近 4 周销量增长超过阈值 |
| `PLATFORM_OVERLAP_STRONG` | 平台重合强 | 平台重合 `>=0.70` |
| `SAMPLE_INSUFFICIENT` | 样本不足 | 样本 insufficient 或关键指标缺失 |

信号等级：

| 等级 | 分数 |
| --- | --- |
| `strong` | `>=0.75` |
| `medium` | `0.55-0.75` |
| `weak` | `0.35-0.55` |
| `blocked` | 样本不足或证据不可用 |

`downstream_usage_json` 必须明确：

- M09 可作为任务市场支撑，但不能单独决定任务。
- M10 可作为客群市场线索，但不能单独决定客群。
- M11 可作为战场市场分，但不能单独决定战场。
- M13 可作为市场压力组件。
- M15 只能展示为市场证据。

### 9.6 `ComparablePoolBuilder`

必须生成以下 `pool_type`：

| pool_type | 条件 |
| --- | --- |
| `same_size` | 同品类 + 同尺寸段 |
| `adjacent_size` | 同品类 + 相邻尺寸段 |
| `same_price_band` | 同品类 + 同品类价格带 |
| `size_price_band` | 同/相邻尺寸 + 同/相邻价格带 |
| `platform_overlap` | 同品类 + 平台重合强 |
| `market_active` | 同品类 + 有效销售周数达标 |

禁止生成：

```text
battlefield
claim
task
target_group
competitor
```

相邻尺寸规则：

| 目标尺寸 | 相邻尺寸 |
| --- | --- |
| 50 | 55 |
| 55 | 50、65 |
| 65 | 55、75 |
| 75 | 65、85 |
| 85 | 75、100 |
| 100 | 85 |

可比池允许包含目标 SKU 本身，用于池分布计算；M12 召回候选时再排除目标本身。

### 9.7 `MarketPoolMemberBuilder`

必须计算：

```text
platform_overlap_score = sum(min(target_platform_amount_share[p], member_platform_amount_share[p]))
channel_overlap_score = sum(min(target_channel_amount_share[c], member_channel_amount_share[c]))
price_gap_to_target = member_price_wavg - target_price_wavg
price_gap_pct_to_target = price_gap_to_target / target_price_wavg
volume_gap_to_target = member_sales_volume_total - target_sales_volume_total
amount_gap_to_target = member_sales_amount_total - target_sales_amount_total
relation_strength =
  0.30 * size_relation_score
+ 0.25 * price_band_relation_score
+ 0.20 * platform_overlap_score
+ 0.15 * market_activity_score
+ 0.10 * confidence_score
```

评分规则：

| 子项 | 规则 |
| --- | --- |
| `size_relation_score` | same=1.0, adjacent=0.7, different=0.2, unknown=0 |
| `price_band_relation_score` | same=1.0, adjacent=0.7, higher/lower=0.4, unknown=0 |
| `platform_overlap_score` | 平台份额交集 |
| `market_activity_score` | 有效周数和销量可用性 |
| `confidence_score` | 成员市场画像置信度 |

### 9.8 `MarketQualityPolicy`

warning 条件：

| 条件 | 质量标记 |
| --- | --- |
| 观察窗口少于 52 周 | `observed_window_less_than_52w` |
| 当前只有线上渠道 | `online_only_channel` |
| `latest_week_gap > 2` | `latest_week_gap` |
| 均价校验不一致 | `price_check_mismatch` |
| 同尺寸池样本 3-5 | `size_pool_limited` |
| 趋势窗口有效周不足 | `trend_sample_insufficient` |
| 平台字段缺失 | `platform_missing` |

review_required 条件：

| 条件 | issue_type |
| --- | --- |
| SKU 有参数/评论但无市场数据 | `missing_market` |
| 销量、销额、均价明显异常 | `market_metric_anomaly` |
| 尺寸缺失导致无法进入尺寸池 | `size_missing` |
| 可比池样本数 `<3` 且下游需要强判断 | `pool_insufficient` |
| 市场画像较上一批波动异常 | `market_profile_drift` |
| 85E7Q 无法生成市场画像或 85 寸可比池 | `demo_sku_market_profile_failed` |

blocked 条件：

| 条件 | 状态 |
| --- | --- |
| M01 市场清洗未完成 | M07 blocked |
| M02 market evidence 未完成 | M07 blocked |
| 所有 SKU 均无有效市场事实 | M07 blocked |
| 价格/销量核心字段全部不可用 | SKU blocked |
| 输出表写入失败 | M07 failed |

### 9.9 `MarketDownstreamImpactService`

输出变化到下游影响：

| M07 输出变化 | 触发模块 |
| --- | --- |
| SKU market profile 变化 | M08-M16 |
| market signal 变化 | M08、M09、M10、M11、M13-M16 |
| comparable pool 变化 | M11.5、M12、M13-M16 |
| pool member 变化 | M12、M13-M16 |
| 仅 evidence 展示变化 | M15、M16 |
| 样本状态变为 insufficient | M16，必要时阻断下游 |

## 10. runner/API 任务

### 10.1 Runner

建议入口：

```text
run_core3_m07_market_profile(
  project_id: str,
  category_code: str,
  batch_id: str,
  sku_scope: list[str] | None,
  analysis_windows: list[str] | None,
  force: bool = False,
  run_id: str | None = None
) -> M07RunResult
```

Runner 流程：

1. 校验上游 M01/M02/M03 状态。
2. 读取输入和 evidence。
3. 构建分析窗口。
4. 计算 SKU market profile。
5. 计算分位和价格带。
6. 生成 market signals。
7. 生成 comparable pools。
8. 生成 pool members。
9. 执行质量和复核规则。
10. 幂等写入。
11. 登记下游影响。
12. 返回模块运行摘要。

返回结构必须包含：

```text
module
status
processed_sku_count
analysis_windows
changed_sku_codes
review_required_sku_codes
blocked_sku_codes
downstream_impacts
metrics.market_profile_count
metrics.market_signal_count
metrics.pool_count
metrics.pool_member_count
warnings
review_issues
```

### 10.2 API

新增或扩展 API：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m07-market-profile` | 运行 M07 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/market-profile` | 查询 SKU 市场画像 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/market-signals` | 查询 SKU 市场信号 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comparable-pools` | 查询目标 SKU 可比池 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/market-pools/{pool_id}/members` | 查询池成员 |

API 边界：

- 查询 API 可以给运营和后续模块联调使用。
- API 不输出最终任务、客群、战场或竞品结论。
- 可比池 API 必须明确 `pool_is_not_competitor_list=true` 或等价中文说明。
- API response 中不得出现 `12m` 字段。

## 11. 增量策略

### 11.1 触发条件

| 输入变化 | M07 动作 | 下游影响 |
| --- | --- | --- |
| `core3_clean_market_weekly` 新增/变化 | 重算对应 SKU 市场画像 | M08-M16 |
| M02 `market_fact` evidence 变化 | 重算 evidence 引用和相关画像 | M08-M16 |
| M03 `screen_size_inch` 变化 | 重算尺寸段、价格/英寸、尺寸可比池 | M08-M16 |
| 平台/渠道清洗规则变化 | 重算平台占比、平台重合和相关池 | M08-M16 |
| 分位/价格带规则变化 | 重算同窗口分位、价格带和池 | M07-M16 |
| 可比池规则变化 | 重算池和成员关系 | M11.5-M16 |

### 11.2 幂等规则

1. profile 按 SKU + 分析窗口计算 fingerprint。
2. fingerprint 未变且非 force 时跳过 profile 重算。
3. 分位和价格带依赖全体 SKU，需要在窗口级判断是否全局重算。
4. profile 变化后重算 signals、pools、pool members。
5. result hash 未变时复用当前记录。
6. result hash 变化时旧 current 置为 false，插入新版本。
7. 输入消失时对应输出置为非 current，并记录 `inactive_reason` 到 `review_reason_json`。

### 11.3 hash 输入

| 对象 | hash 输入 |
| --- | --- |
| `sku_market_profile` | `sku_code + analysis_window + market_row_hashes + market_metrics + screen_size + rule_version` |
| `market_signal` | `profile_hash + signal_code + basis_metric + signal_strength + sample_status + rule_version` |
| `comparable_pool_baseline` | `target_sku + analysis_window + pool_type + pool_condition + member_sku_codes + distributions + rule_version` |
| `market_pool_member` | `pool_id + target_sku + member_sku + relation_metrics + rule_version` |

## 12. 测试任务

### 12.1 单元测试

| 测试文件 | 必测点 |
| --- | --- |
| `test_m07_market_input_service.py` | 输入读取、evidence 索引、fingerprint |
| `test_m07_market_window_service.py` | 5 类窗口、最新周、周解析失败处理 |
| `test_m07_metric_calculator.py` | 加权均价、零销量、平台占比、趋势、价格/英寸 |
| `test_m07_percentile_service.py` | 品类/尺寸/池分位、价格带、样本状态 |
| `test_m07_market_signal_builder.py` | 9 类市场信号、强度、等级、下游使用提示 |
| `test_m07_comparable_pool_builder.py` | 6 类可比池、相邻尺寸、同品牌不排除 |
| `test_m07_pool_member_builder.py` | 平台重合、价量差、关系强度 |
| `test_m07_quality_policy.py` | warning、review_required、blocked |
| `test_m07_repositories.py` | 写入、current 失效、唯一键、hash 复用 |
| `test_m07_runner.py` | 运行摘要、增量跳过、下游影响 |
| `test_m07_api.py` | API schema、404、边界错误 |

### 12.2 边界测试

必须覆盖：

- SKU 无市场数据：输出 unknown profile 和 `SAMPLE_INSUFFICIENT`。
- SKU 有市场无尺寸：可生成市场画像，不生成尺寸池。
- SKU 仅一个有效周：可生成 `latest_week`，趋势样本不足。
- 平台为空：平台重合不可用。
- 销额有值但销量为空：价格不可计算，进入复核。
- 同尺寸池只有目标自己：pool insufficient。
- 价格全相同：分位稳定，不能除零或产生 NaN。
- 23 周样例：不出现 `12m` 字段和 12 月展示口径。

### 12.3 禁止越界测试

必须验证：

- M07 不读取原始 `week_sales_data`。
- M07 不读取 M04b 卖点激活。
- M07 不读取 M06 评论信号。
- M07 不输出任务、客群、战场、候选或竞品结论。
- M07 不按品牌内外过滤。
- M07 不生成线下渠道判断。
- M07 不生成 `price_wavg_12m`、`sales_volume_12m`、`sales_amount_12m`。
- M07 不调用外部 LLM。

### 12.4 fixture 验收

M07 fixture 必须覆盖 205 样例事实：

| 数据事实 | fixture 要求 |
| --- | --- |
| `week_sales_data` 1326 行 | 用小型 fixture 模拟 35 型号、23 周结构 |
| 35 个量价型号 | full window 至少生成 35 个 profile |
| 周期 `26W01-26W23` | 输出观测窗口，不输出 12 月字段 |
| 渠道 `线上` | 输出 `online_only_channel`，不输出线下判断 |
| 平台 `专业电商`、`平台电商` | 输出平台占比和平台重合 |
| 品牌全为海信 | 同品牌成员保留在可比池 |
| 85E7Q 周销 46 行 | 生成 full/recent/latest 市场画像 |
| 85E7Q 尺寸 85 | 进入 85 寸同尺寸池 |

85E7Q fixture 必须检查：

```text
target model: 85E7Q
target sku/model_code: TV00029115
analysis window: full_observed_window, latest_week, recent_4w
same_size pool includes:
  85D30QD
  85E3Q
  85E52Q
  85E52S-PRO
  85E5Q
  85E5Q-PRO
  85E5S-PRO
  85E7Q
  85E8Q
adjacent_size pool checks 75 inch and 100 inch models
platform share includes 专业电商 and 平台电商
brand filter is none
```

## 13. 开发子任务拆分

| 子任务 | 类型 | 内容 | 完成标准 |
| --- | --- | --- | --- |
| M07-A | migration/model | 新增 4 张表和 SQLAlchemy model | upgrade/downgrade 通过 |
| M07-B | schema/constants | M07 枚举、内部 schema、API schema | schema 单测通过 |
| M07-C | repository | 输入读取、输出写入、current/hash | repository 单测通过 |
| M07-D | window/metric | 窗口和市场指标计算 | 单元测试通过 |
| M07-E | percentile/signal | 分位、价格带、市场信号 | 单元测试通过 |
| M07-F | pool/member | 可比池和池成员关系 | 单元测试通过 |
| M07-G | quality/impact | 复核规则和下游影响 | 单元测试通过 |
| M07-H | runner/API | runner 和查询 API | runner/API 测试通过 |
| M07-I | fixture/越界 | 85E7Q、35 型号、禁止越界 | 集成和越界测试通过 |

编码时仍应继续拆小任务执行，不能在一个编码任务里一次性完成 M07-A 到 M07-I。

## 14. 完成标准

M07 编码完成必须满足：

1. `0014_core3_real_data_market_profile.py` 可升级、可回滚。
2. 4 张 M07 输出表字段、唯一键、索引与设计一致。
3. M07 runner 可基于 M01/M02/M03 fixture 生成 profile、signal、pool、member。
4. full window 下 35 个量价型号能生成市场画像。
5. 85E7Q 能生成市场画像、平台占比、85 寸同尺寸池和相邻尺寸池。
6. 当前 23 周样例不生成任何 `12m` 字段或 12 月结论。
7. 当前只有线上渠道时不输出线下判断。
8. 可比池不按海信品牌过滤。
9. 所有 profile/signal/pool/member 都有 evidence IDs 或明确 evidence 缺失复核原因。
10. M07 API 不输出任务、客群、战场、候选或竞品结论。
11. 增量重跑不会重复插入 current 记录。
12. 单元、集成、边界、越界测试通过。

## 15. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 23 周数据被误写成 12 月口径 | 高层报告误导 | 字段和测试禁止 `12m` |
| 可比池被误当竞品列表 | 业务理解错误 | API 和字段明确可比池不是竞品 |
| 同品牌过滤导致样例无候选 | 当前全海信无法分析 | M07 不做品牌过滤 |
| 尺寸缺失仍进入尺寸池 | 可比关系错误 | 缺尺寸时不生成尺寸池，进入复核 |
| 分位样本太少仍高置信 | 下游评分失真 | `sample_status` 和 confidence 降级 |
| 直接读原始周销表 | 破坏分层追溯 | repository 越界测试 |
| 可比池规模过大 | 写入和查询慢 | 索引、sku_scope、窗口级重算 |
| profile 变化未触发下游 | M08-M16 使用旧市场事实 | downstream impact 测试 |

回滚策略：

- migration downgrade 只删除 M07 四张表。
- M07 服务出错时不影响 M00-M06 已有结果。
- 若 M07 规则错误，提升 `rule_version` 并重跑，不覆盖历史版本。
- 若某窗口异常，可通过 runner `analysis_windows` 限制重跑范围。

## 16. 下游依赖

M07 给下游的承诺：

| 下游 | 消费内容 | 边界 |
| --- | --- | --- |
| M08 | `core3_sku_market_profile`、`core3_market_signal` | 合并 SKU 综合画像 |
| M09 | 价格低、价格效率、销量强、价格下探等市场信号 | 不能单独决定任务 |
| M10 | 价格带、销量、平台等线索 | 不能单独决定客群 |
| M11 | 价格、销量、销额、平台和样本状态 | 不能单独决定战场 |
| M11.5 | 可比池价格、销量、销额分布 | PSI/SSI 在 M11.5 计算 |
| M12 | 可比池和池成员 | M12 再召回候选 |
| M13 | 价差、销量差、销额差、平台重合、分位 | M13 再计算市场压力分 |
| M15 | 市场证据展示 | 只能展示为市场证据 |
| M16 | 运行状态、复核问题、下游影响 | 门禁和复核编排 |

下次任务：

```text
docs/core3_mvp/real_data_v2/development/M08_development_tasks.md
```

M08 需要把 M03 参数画像、M04b 最终卖点激活、M06 评论信号画像、M07 市场画像合并为 SKU 综合信号画像，作为 M09-M14 的统一上游特征接口。M08 不能回读原始表，也不能重新推导任务、客群、战场或竞品。
