# 02 持久化分层与增量数据模型

## 1. 分层总览

真实数据版不能只把结果写进报告表。建议至少保留以下层：

| 层级 | 表前缀 | 作用 | 是否可重算 |
| --- | --- | --- | --- |
| 原始登记层 | `core3_source_*` | 登记原始表行、批次、hash、水位 | 可重建，但建议保留 |
| 清洗规范层 | `core3_clean_*` | 保存清洗后的 canonical facts | 可重算 |
| 剖析画像层 | `core3_profile_*` | 字段覆盖、文本短语、数据质量 | 可重算 |
| 抽取事实层 | `core3_extract_*` | 参数、卖点、评论主题等句级/事实级抽取 | 可重算 |
| 资产候选层 | `core3_candidate_*` 或 `category_asset_*` | 新字段、新卖点、新主题、新映射候选 | 半可重算，保留复核状态 |
| SKU 画像层 | `core3_sku_*` | 市场、参数、卖点、评论、任务、客群、战场 | 可重算 |
| 竞品结果层 | `core3_competitor_*` | 候选池、组件分、三竞品、证据卡 | 可重算 |

## 2. 原始登记层

### 2.1 `core3_source_batch`

记录一次扫描或导入批次。

字段：

```text
batch_id
project_id
category_code
source_mode              -- real_table_scan / upload / manual_import
source_tables_json       -- week_sales_data 等
watermark_json           -- 各表 write_time 最大值、行数、hash
status                   -- running/completed/failed
started_at
finished_at
created_at
```

### 2.2 `core3_source_row_registry`

记录原始行指纹，支持增量。

字段：

```text
registry_id
batch_id
project_id
category_code
source_table             -- week_sales_data / attribute_data / selling_points_data / comment_data
source_row_key
source_row_hash
sku_code
model_name
write_time
row_status               -- new/changed/unchanged/deleted_or_missing/skipped
quality_status           -- ok/warning/error
quality_issue_codes_json
first_seen_at
last_seen_at
processed_at
```

唯一约束：

```text
source_table, source_row_key
```

增量判断：

- `source_row_key` 不存在：新增。
- `source_row_key` 存在但 hash 变化：变化。
- hash 未变化：跳过后续清洗。
- 原始表删除通常不物理删除下游表，而是标记当前批次不再可见，MVP 阶段可暂不处理删除。

## 3. 清洗规范层

### 3.1 `core3_clean_market_fact`

来源：`week_sales_data`

字段：

```text
clean_id
batch_id
source_table
source_row_key
source_row_hash
project_id
category_code
sku_code
brand
model_name
period
period_type
period_year
period_week
channel_group
channel_type
sales_volume
sales_amount
avg_price
price_calc_delta
is_valid
quality_issue_codes_json
evidence_id
pipeline_version
created_at
updated_at
```

唯一约束：

```text
source_table, source_row_key, pipeline_version
```

### 3.2 `core3_clean_param_fact`

来源：`attribute_data`

字段：

```text
clean_id
batch_id
source_row_key
sku_code
brand
model_name
raw_param_name
raw_param_name_norm
raw_param_value
raw_param_value_norm
raw_unit
unknown_flag
numeric_candidates_json
is_valid
quality_issue_codes_json
evidence_id
pipeline_version
created_at
updated_at
```

### 3.3 `core3_clean_claim_fact`

来源：`selling_points_data`

字段：

```text
clean_id
batch_id
source_row_key
sku_code
brand
model_name
claim_title
claim_text
claim_order
unknown_flag
is_valid
quality_issue_codes_json
evidence_id
pipeline_version
created_at
updated_at
```

### 3.4 `core3_clean_claim_sentence`

字段：

```text
sentence_id
clean_id
sku_code
sentence_index
sentence_text
sentence_hash
token_count
numeric_entities_json
tech_entities_json
is_template
evidence_id
pipeline_version
created_at
```

### 3.5 `core3_clean_comment_fact`

来源：`comment_data`

字段：

```text
clean_id
batch_id
source_row_key
sku_code
brand
model_name
platform
comment_id
comment_text
comment_text_hash
comment_time
rating
is_duplicate_text
is_default_review
is_valid
quality_issue_codes_json
evidence_id
pipeline_version
created_at
updated_at
```

### 3.6 `core3_clean_comment_sentence`

字段：

```text
sentence_id
clean_comment_id
sku_code
comment_id
sentence_index
sentence_text
sentence_hash
is_product_like
is_service_like
is_price_like
evidence_id
pipeline_version
created_at
```

### 3.7 `core3_clean_comment_dimension_fact`

保留上传表中的一级/二级/三级维度，作为弱标签和对照，不直接作为最终主题。

字段：

```text
dimension_id
clean_comment_id
sku_code
raw_dimension_1
raw_dimension_2
raw_dimension_3
dimension_path_norm
source_row_key
created_at
```

## 4. 剖析画像层

### 4.1 `core3_data_quality_snapshot`

字段：

```text
snapshot_id
batch_id
project_id
category_code
sku_count
market_row_count
param_row_count
claim_row_count
comment_row_count
valid_comment_count
claim_covered_sku_count
comment_covered_sku_count
param_unknown_rate
comment_duplicate_rate
quality_summary_json
created_at
```

### 4.2 `core3_param_field_profile`

字段：

```text
profile_id
batch_id
raw_param_name
raw_param_name_norm
row_count
sku_count
coverage_rate
non_empty_rate
unknown_rate
top_values_json
numeric_shape_json
matched_param_code
match_confidence
candidate_status
evidence_ids_json
created_at
```

### 4.3 `core3_text_token`

字段：

```text
token_id
batch_id
source_domain          -- claim/comment
sku_code
sentence_id
token_text
token_norm
token_type             -- word/ngram/number/tech_entity/sentiment_word
position
created_at
```

### 4.4 `core3_phrase_profile`

字段：

```text
phrase_id
batch_id
source_domain
phrase_text
phrase_norm
sku_coverage
sentence_count
positive_count
negative_count
cooccur_param_codes_json
cooccur_claim_codes_json
cooccur_topic_codes_json
market_lift_json
example_sentence_ids_json
candidate_type
created_at
```

## 5. 抽取事实层

### 5.1 `core3_extract_param_value`

字段：

```text
extract_id
batch_id
sku_code
param_code
param_name
normalized_value
normalized_unit
value_level
source_domain          -- param/claim/model/comment
source_id
match_type
parser_name
confidence
conflict_group_id
evidence_id
rule_version
created_at
```

### 5.2 `core3_extract_claim_hit`

字段：

```text
hit_id
batch_id
sku_code
claim_code
claim_name
source_domain          -- claim_sentence/param/comment
source_id
matched_keywords_json
numeric_entities_json
param_support_json
confidence
evidence_id
rule_version
created_at
```

### 5.3 `core3_extract_comment_topic_hit`

字段：

```text
hit_id
batch_id
sku_code
sentence_id
topic_code
topic_name
product_service_type
sentiment
sentiment_score
matched_keywords_json
raw_dimension_support_json
confidence
evidence_id
rule_version
created_at
```

## 6. 资产候选层

候选资产可以复用 `category_asset_*` 表并设置 `review_status=pending`，也可以先使用 `core3_candidate_*` 表。MVP 推荐先使用专用候选表，避免污染正式资产库；后续复核通过后再提升到 `category_asset_*`。

### 6.1 `core3_candidate_asset`

字段：

```text
candidate_id
batch_id
project_id
category_code
asset_type             -- param_alias/param/claim/comment_topic/task/target_group/battlefield/mapping
candidate_code
candidate_name
candidate_payload_json
coverage_rate
sample_sku_codes_json
example_evidence_ids_json
generation_method      -- field_profile/phrase_mining/cooccur/seed_mapping/manual
confidence
review_status          -- pending/approved/rejected/needs_merge/needs_split
review_priority
created_at
updated_at
```

## 7. SKU 画像层

### 7.1 `core3_sku_market_profile`

保留现有表，补充 `source_batch_id`、`profile_version`、`comparable_pool_json`。

### 7.2 `core3_sku_semantic_profile`

建议新增或等价落入 `core3_sku_feature_profile`。

字段：

```text
profile_id
batch_id
project_id
category_code
sku_code
standard_params_json
claim_activations_json
comment_topics_json
missing_signals_json
conflicts_json
profile_confidence
evidence_ids_json
rule_version
created_at
updated_at
```

### 7.3 `core3_sku_task_score`

字段：

```text
score_id
batch_id
sku_code
task_code
task_name
score
relation_level
component_scores_json
missing_signals_json
evidence_ids_json
rule_version
created_at
```

### 7.4 `core3_sku_target_group_score`

字段类似任务得分，存客群得分。

### 7.5 `core3_sku_battlefield_score`

字段：

```text
score_id
batch_id
sku_code
battlefield_code
battlefield_name
final_score
semantic_score
market_score
relation_level
component_scores_json
missing_signals_json
evidence_ids_json
rule_version
created_at
```

## 8. 竞品结果层

沿用现有：

- `core3_competitor_candidate`
- `core3_competitor_result`
- `core3_evidence_card`

需要补充：

- `source_batch_id`
- `profile_version`
- `asset_version`
- `rule_version`
- 候选池收敛阶段字段，例如 `recall_reasons_json`、`gate_stage_json`

## 9. 增量重算机制

### 9.1 受影响 SKU 计算

每次扫描原始表后得到：

```text
impacted_sku_codes =
  changed market sku
  union changed param sku
  union changed claim sku
  union changed comment sku
```

还要计算全局受影响：

- 参数字段画像变化可能影响多个 SKU 的参数映射。
- 新卖点候选批准后可能影响多个 SKU 的卖点激活。
- 评分权重或 seed 版本变化会影响所有 SKU。

### 9.2 任务级增量策略

| 变化类型 | 最小重算范围 |
| --- | --- |
| 新增周销行 | 对应 SKU 市场画像；所有以该 SKU 为候选或目标的竞品分 |
| 新增参数行 | 对应 SKU 参数抽取、卖点激活、任务/战场、竞品分 |
| 新增卖点行 | 对应 SKU 卖点抽取、候选卖点、任务/战场、竞品分 |
| 新增评论行 | 对应 SKU 评论主题、卖点评论分、任务/战场、竞品分 |
| 参数 alias 复核通过 | 使用该 raw_param_name 的所有 SKU |
| 新标准卖点复核通过 | 命中该短语或参数规则的所有 SKU |
| 规则版本变化 | 全量 SKU |

### 9.3 幂等写入

每个下游表写入时使用：

```text
natural_key + pipeline_version + rule_version + source_batch_id
```

同一输入重复执行不重复产出。需要更新当前版本时，优先使用 upsert，保留历史版本或通过 `is_current` 标记当前。

### 9.4 执行模式

```text
incremental
  只处理 source_row_registry 中 new/changed 行及受影响 SKU

full_refresh
  当前原始表全量重新清洗和重算

rule_refresh
  原始清洗不动，从抽取或评分阶段开始重算

asset_refresh
  资产复核结果变化后，从资产应用阶段开始重算
```

