# M01 清洗规范化与质量诊断开发任务

## 1. 模块目标

M01 的开发目标是把 M00 登记过的原始行转换成后续模块可稳定消费的清洗事实层，并输出可查询、可复核、可增量判断的数据质量诊断。

M01 必须实现：

1. 读取 M00 的批次、来源行登记和受影响 SKU，不绕过 M00 直接决定清洗范围。
2. 按 `source_table + source_pk` 只读回查四张原始表。
3. 生成统一 SKU、市场、参数、卖点、卖点句、评论、评论句、评论维度和质量问题九类表。
4. 同时保存原始值、清洗值、来源定位、质量状态和 `clean_hash`。
5. 明确区分 null、空字符串、`-`、`unknown`、缺字段等 unknown 状态，不把缺失解释成 false。
6. 对重复、缺失、冲突、低价值评论、卖点覆盖缺失、量价异常生成质量问题。
7. 为 M02-M16 提供可追溯输入和下游触发依据。

M01 不生成业务 evidence，不抽取标准参数、标准卖点、用户任务、目标客群、价值战场或竞品结论。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| INFRA 任务 | `docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md` |
| M00 任务 | `docs/core3_mvp/real_data_v2/development/M00_development_tasks.md` |
| M01 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M01_cleaning_quality_requirements.md` |
| M01 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M01_cleaning_quality_design.md` |
| M00 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M00_source_batch_registry_design.md` |
| 总体架构 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |

编码前必须确认 INFRA 和 M00 已经完成到可运行状态，至少具备通用 hash、run context、runner 协议、M00 三张表和原始表只读 repository。

## 3. 本次范围

### 3.1 必须实现

| 能力 | 说明 |
| --- | --- |
| SKU 清洗 | 生成 `core3_clean_sku`，表达跨表覆盖、缺失和冲突 |
| 市场清洗 | 生成 `core3_clean_market_weekly`，解析周、渠道、平台、销量、销额、均价 |
| 参数清洗 | 生成 `core3_clean_attribute`，保留参数原名、原值、清洗值、数字和单位候选 |
| 卖点清洗 | 生成 `core3_clean_claim`，解析 `卖点1..13`、保留标题弱提示 |
| 卖点句表 | 生成 `core3_clean_claim_sentence`，供 M02/M04a 使用 |
| 评论清洗 | 生成 `core3_clean_comment`，保留正文、分段、情感、低价值和重复依据 |
| 评论句表 | 生成 `core3_clean_comment_sentence`，区分系统切句和原始分段 |
| 评论维度弱标签 | 生成 `core3_clean_comment_dimension`，只保存原始维度路径 |
| 质量问题 | 生成 `core3_data_quality_issue`，覆盖行级、SKU 级、批次级问题 |
| clean hash | 每条清洗事实有 `clean_record_key` 和 `clean_hash` |
| M01 runner | `CleaningQualityRunner.run(...)` 编排全流程 |
| M01 查询 API | 提供运营排查接口，不作为高层报告接口 |
| 测试 | 单元、repository、service、runner、API、fixture、越界测试 |

### 3.2 明确不做

M01 不做：

- 不修改 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- 不生成 `evidence_id` 或 evidence 原子。
- 不生成 `param_code`、`claim_code`、`task_code`、`target_group_code`、`battlefield_code`。
- 不把评论原始维度直接变成任务、客群、战场或卖点结论。
- 不判断竞品、角色、三槽位、分数或报告文案。
- 不改前端页面。
- 不部署 205。
- 不把 85E7Q 无结构化卖点解释为“没有卖点”或“卖点弱”。

## 4. 要改文件

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/cleaning_quality_service.py
apps/api-server/app/services/core3_real_data/cleaning_repositories.py
apps/api-server/app/services/core3_real_data/cleaning_schemas.py
apps/api-server/tests/core3_real_data/test_m01_cleaning_normalizers.py
apps/api-server/tests/core3_real_data/test_m01_cleaning_repositories.py
apps/api-server/tests/core3_real_data/test_m01_cleaning_service.py
apps/api-server/tests/core3_real_data/test_m01_cleaning_runner.py
apps/api-server/tests/core3_real_data/test_m01_cleaning_api.py
apps/api-server/tests/core3_real_data/test_m01_no_business_outputs.py
```

### 4.2 后端可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 新增 M01 九张表模型；若项目已拆 model 包，则按 INFRA 约定放入 v2 model 文件 |
| `apps/api-server/alembic/versions/0007_core3_real_data_cleaning.py` | 新增 M01 清洗层迁移 |
| `apps/api-server/app/schemas/core3_real_data.py` | 增加 M01 请求、响应、摘要和质量问题 schema |
| `apps/api-server/app/api/core3_real_data.py` | 增加 M01 内部/运营 API |
| `apps/api-server/tests/core3_real_data/conftest.py` | 增加 M01 fixture、mock M00 数据和 85E7Q 样例断言工具 |
| `apps/api-server/app/services/core3_real_data/constants.py` | 如 INFRA 未包含 M01 枚举，可补充值存在性、质量问题类型等枚举 |

### 4.3 预计引用 INFRA 和 M00 文件

```text
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/app/services/core3_real_data/repositories.py
apps/api-server/app/services/core3_real_data/source_registry_repositories.py
apps/api-server/app/services/core3_real_data/source_registry_schemas.py
```

## 5. 不允许改文件

M01 编码阶段不允许修改：

```text
apps/api-server/app/services/core3_mvp/*
apps/factory-web/src/pages/core3/*
apps/factory-web/src/pages/core3RealData/*
apps/factory-web/src/App.tsx
apps/factory-web/src/styles.css
docker-compose.yml
docker-compose.cloud.yml
scripts/deploy.sh
```

不允许修改原始四表结构：

```text
week_sales_data
attribute_data
selling_points_data
comment_data
```

不允许把 M02-M16 的业务结果表混入 M01 migration。不允许使用 `git add .`，只能 stage 本任务直接新增或修改的文件。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0007_core3_real_data_cleaning.py
```

如果 M00 migration 编号不是 `0006`，以当前 Alembic 最新编号顺延，但迁移内容仍只包含 M01 表和索引。

### 6.2 新增表

M01 migration 新增九张表：

| 表 | 用途 |
| --- | --- |
| `core3_clean_sku` | SKU 主数据、覆盖、缺失和跨表冲突 |
| `core3_clean_market_weekly` | 周销量价清洗事实 |
| `core3_clean_attribute` | 参数清洗事实 |
| `core3_clean_claim` | 结构化卖点清洗事实 |
| `core3_clean_claim_sentence` | 卖点句级切分 |
| `core3_clean_comment` | 评论正文、分段、情感、重复和低价值标记 |
| `core3_clean_comment_sentence` | 评论系统切句和原始分段句 |
| `core3_clean_comment_dimension` | 评论原始维度弱标签 |
| `core3_data_quality_issue` | M01 质量问题和复核提示 |

### 6.3 通用字段要求

除特殊说明外，清洗事实表必须包含：

```text
project_id
category_code
batch_id
run_id
module_run_id
source_table
source_pk
source_row_id
source_row_hash
source_operation_type
clean_record_key
clean_hash
clean_version
hash_version
record_status
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

`record_status` 必须支持：

```text
active
inactive_candidate
skipped
```

`quality_status` 必须支持：

```text
ok
warning
error
```

`review_status` 至少支持：

```text
auto_pass
review_required
approved
rejected
waived
```

### 6.4 `core3_clean_sku`

必须字段：

```text
clean_sku_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
sku_code_raw_values
model_name
model_name_raw_values
brand_name
brand_raw_values
category_name
source_tables
first_seen_source_row_id
representative_source_row_ids
coverage_json
field_conflicts_json
missing_signals_json
clean_record_key
clean_hash
clean_version
hash_version
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `clean_sku_id` |
| 唯一键 | `batch_id, sku_code` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code` |
| 索引 | `quality_status` |
| GIN | `coverage_json`、`missing_signals_json`、`field_conflicts_json` |

### 6.5 `core3_clean_market_weekly`

必须字段：

```text
clean_market_id
project_id
category_code
batch_id
run_id
module_run_id
source_table
source_pk
source_row_id
source_row_hash
source_operation_type
sku_code
model_name
brand_name
category_name_raw
period_raw
period_type
period_year_hint
period_week_index
period_parse_status
channel_raw
channel_type
platform_raw
platform_type
sales_volume_raw
sales_volume
sales_amount_raw
sales_amount
avg_price_raw
avg_price
avg_price_expected
price_check_status
price_check_delta
clean_record_key
clean_hash
clean_version
hash_version
record_status
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `clean_market_id` |
| 唯一键 | `batch_id, source_row_id` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, period_raw` |
| 索引 | `channel_type, platform_type` |
| 索引 | `price_check_status` |
| 索引 | `clean_hash` |

### 6.6 `core3_clean_attribute`

必须字段：

```text
clean_attribute_id
project_id
category_code
batch_id
run_id
module_run_id
source_table
source_pk
source_row_id
source_row_hash
source_operation_type
sku_code
model_name
brand_name
raw_attr_name
clean_attr_name
raw_attr_value
clean_attr_value
value_presence
value_number_candidates
value_unit_candidates
raw_value_token_count
conflict_group_key
clean_record_key
clean_hash
clean_version
hash_version
record_status
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `clean_attribute_id` |
| 唯一键 | `batch_id, source_row_id` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, clean_attr_name` |
| 索引 | `value_presence` |
| 索引 | `conflict_group_key` |
| GIN | `value_number_candidates`、`value_unit_candidates`、`quality_flags` |

### 6.7 `core3_clean_claim` 和 `core3_clean_claim_sentence`

`core3_clean_claim` 必须字段：

```text
clean_claim_id
project_id
category_code
batch_id
run_id
module_run_id
source_table
source_pk
source_row_id
source_row_hash
source_operation_type
sku_code
model_name
brand_name
claim_seq_raw
claim_seq
raw_claim_text
clean_claim_text
claim_text_presence
title_hint
structure_hints
clean_record_key
clean_hash
clean_version
hash_version
record_status
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

`core3_clean_claim_sentence` 必须字段：

```text
claim_sentence_id
project_id
category_code
batch_id
source_row_id
clean_claim_id
sku_code
claim_seq
sentence_seq
sentence_text
sentence_text_hash
sentence_role_hint
split_rule
clean_record_key
clean_hash
clean_version
hash_version
quality_status
quality_flags
created_at
```

约束和索引：

| 表 | 类型 | 字段 |
| --- | --- | --- |
| `core3_clean_claim` | 主键 | `clean_claim_id` |
| `core3_clean_claim` | 唯一键 | `batch_id, source_row_id` |
| `core3_clean_claim` | 索引 | `sku_code, claim_seq` |
| `core3_clean_claim` | GIN | `structure_hints`、`quality_flags` |
| `core3_clean_claim_sentence` | 主键 | `claim_sentence_id` |
| `core3_clean_claim_sentence` | 唯一键 | `batch_id, source_row_id, sentence_seq` |
| `core3_clean_claim_sentence` | 索引 | `sku_code, claim_seq` |
| `core3_clean_claim_sentence` | 索引 | `sentence_text_hash` |

### 6.8 `core3_clean_comment`、`core3_clean_comment_sentence` 和 `core3_clean_comment_dimension`

`core3_clean_comment` 必须字段：

```text
clean_comment_id
project_id
category_code
batch_id
run_id
module_run_id
source_table
source_pk
source_row_id
source_row_hash
source_operation_type
sku_code
model_name
brand_name
platform_raw
url_id
comment_id
comment_time_raw
comment_time
comment_time_parse_status
raw_comment_text
clean_comment_text
comment_text_presence
comment_text_hash
segment_text_raw
segment_text_clean
segment_text_hash
sentiment_raw
sentiment_clean
low_value_flag
low_value_reason
duplicate_group_key
dimension_available
clean_record_key
clean_hash
clean_version
hash_version
record_status
quality_status
quality_flags
review_required
review_status
created_at
updated_at
```

`core3_clean_comment_sentence` 必须字段：

```text
comment_sentence_id
project_id
category_code
batch_id
source_row_id
clean_comment_id
sku_code
comment_id
sentence_source
sentence_seq
sentence_text
sentence_text_hash
source_segment_text
is_from_existing_segment
split_rule
clean_record_key
clean_hash
clean_version
hash_version
quality_status
quality_flags
created_at
```

`core3_clean_comment_dimension` 必须字段：

```text
comment_dimension_id
project_id
category_code
batch_id
source_row_id
clean_comment_id
sku_code
comment_id
primary_dim_raw
secondary_dim_raw
third_dim_raw
dimension_path_raw
dimension_available
dimension_quality_flag
clean_record_key
clean_hash
clean_version
hash_version
quality_status
quality_flags
created_at
```

约束和索引：

| 表 | 类型 | 字段 |
| --- | --- | --- |
| `core3_clean_comment` | 主键 | `clean_comment_id` |
| `core3_clean_comment` | 唯一键 | `batch_id, source_row_id` |
| `core3_clean_comment` | 索引 | `sku_code, comment_id` |
| `core3_clean_comment` | 索引 | `comment_text_hash` |
| `core3_clean_comment` | 索引 | `segment_text_hash` |
| `core3_clean_comment` | 索引 | `duplicate_group_key` |
| `core3_clean_comment` | 索引 | `sentiment_clean` |
| `core3_clean_comment` | 索引 | `low_value_flag` |
| `core3_clean_comment_sentence` | 主键 | `comment_sentence_id` |
| `core3_clean_comment_sentence` | 唯一键 | `batch_id, source_row_id, sentence_source, sentence_seq` |
| `core3_clean_comment_sentence` | 索引 | `sku_code, comment_id` |
| `core3_clean_comment_sentence` | 索引 | `sentence_text_hash` |
| `core3_clean_comment_dimension` | 主键 | `comment_dimension_id` |
| `core3_clean_comment_dimension` | 唯一键 | `batch_id, source_row_id` |
| `core3_clean_comment_dimension` | 索引 | `sku_code, comment_id` |
| `core3_clean_comment_dimension` | 索引 | `dimension_available` |

### 6.9 `core3_data_quality_issue`

必须字段：

```text
issue_id
project_id
category_code
batch_id
run_id
module_run_id
module_code
domain
source_table
source_row_id
clean_table
clean_record_key
sku_code
issue_type
severity
issue_detail
issue_payload_json
suggested_downstream_action
review_required
review_status
created_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `issue_id` |
| 幂等唯一键 | `batch_id, domain, issue_type, source_row_id, clean_record_key, sku_code` 的空值规范化组合 |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code` |
| 索引 | `domain, issue_type` |
| 索引 | `severity` |
| 索引 | `review_required` |
| GIN | `issue_payload_json` |

### 6.10 迁移验收

迁移完成后必须验证：

- SQLite 测试库可 `Base.metadata.create_all`。
- Alembic migration 可导入、可 upgrade、可 downgrade。
- 不创建、修改或删除原始四表。
- 不创建 M02-M16 的结果表。
- 表名不和旧 `core3_mvp` 冲突。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

必须为九张表建立模型，字段名和数据库列名保持 snake_case。

模型约束：

- 所有 JSON 字段使用 JSON/JSONB 兼容类型，SQLite 测试要可运行。
- 金额、销量、均价使用 Decimal 语义，不在 model 层转 float。
- 时间字段使用 timezone aware 类型。
- 枚举字段首版可用 `String` + service 校验，避免 Alembic enum 修改困难。
- 每张表模型要有清晰注释或 `__tablename__`，便于后续 M02-M16 引用。

### 7.2 Pydantic schema

`cleaning_schemas.py` 至少定义：

```text
ValuePresence
CleanRecordStatus
CleanQualityStatus
ReviewStatus
QualityIssueSeverity
QualityIssueType
CleaningRunRequest
CleaningRunResult
CleaningCounts
QualityIssueCounts
CleanSkuSummary
CleanCoverageSummary
CleanQualityIssueRead
CleanMarketRead
CleanAttributeRead
CleanClaimRead
CleanCommentRead
```

`core3_real_data.py` 可重新导出 API 需要的 schema，避免 API 层直接引用 service 内部对象。

### 7.3 枚举值

`value_presence` 必须支持：

```text
present
null
empty
dash
unknown_literal
missing_column
```

`source_operation_type` 必须承接 M00：

```text
insert
update
no_change
not_seen_in_current_scan
skipped
```

`issue_type` 至少支持：

```text
missing_required_field
invalid_number
negative_number
price_check_mismatch
unknown_value
cross_table_conflict
claim_coverage_missing
claim_seq_parse_failed
low_value_comment
duplicate_comment_text
comment_dimension_missing
comment_split_row_suspected
schema_changed
clean_hash_changed_high
```

## 8. repository 任务

### 8.1 读取 repository

新增或复用 M00 repository：

| Repository | 职责 |
| --- | --- |
| `SourceBatchReader` | 读取并校验 `core3_source_batch` |
| `SourceRowRegistryReader` | 按 batch 和 operation type 读取 M00 来源行 |
| `SourceImpactedSkuReader` | 读取受影响 SKU，用于覆盖摘要参考 |
| `RawSourceRepository` | 按 `source_table + source_pk` 回读原始行，只读 |

读取规则：

- 默认只处理 `insert`、`update`、`not_seen_in_current_scan`、`skipped`。
- `no_change` 默认跳过，全量重建模式才处理。
- `not_seen_in_current_scan` 不强制回读原始行，应生成 inactive candidate 和质量提示。
- 原始表回读失败不能静默忽略，必须进入质量问题或模块失败判断。

### 8.2 写入 repository

新增 repository：

| Repository | 写入范围 |
| --- | --- |
| `CleanSkuRepository` | `core3_clean_sku` |
| `CleanMarketRepository` | `core3_clean_market_weekly` |
| `CleanAttributeRepository` | `core3_clean_attribute` |
| `CleanClaimRepository` | `core3_clean_claim`、`core3_clean_claim_sentence` |
| `CleanCommentRepository` | `core3_clean_comment`、`core3_clean_comment_sentence`、`core3_clean_comment_dimension` |
| `DataQualityIssueRepository` | `core3_data_quality_issue` |

写入规则：

- 同一 `batch_id + source_row_id` 的主事实不得重复。
- 同一 `batch_id + source_row_id + sentence_seq` 的句级事实不得重复。
- 质量问题用幂等 key 写入，重跑不得重复插入同一问题。
- 如果同一 batch 已存在记录且 `clean_hash` 相同，可跳过。
- 如果同一 batch 已存在记录但 `clean_hash` 不同，runner 必须失败，提示重建 batch 或清理失败批次，不能静默覆盖。

### 8.3 查询 repository

为运营 API 和测试提供查询：

| 查询 | 用途 |
| --- | --- |
| `get_clean_summary(batch_id)` | 返回九类清洗数量、质量数量和覆盖摘要 |
| `list_clean_skus(batch_id, filters)` | 查询 SKU 覆盖、缺失和冲突 |
| `list_quality_issues(batch_id, filters)` | 按 SKU、domain、issue_type、severity 查询质量问题 |
| `get_sku_clean_drilldown(batch_id, sku_code)` | 供排查查看该 SKU 清洗覆盖 |

## 9. service 任务

### 9.1 服务拆分

`cleaning_quality_service.py` 建议拆为以下类或函数。实现时可以按项目风格调整，但职责边界必须保持：

| 服务 | 职责 |
| --- | --- |
| `TextNormalizer` | 文本最小规范化，去空白、不可见字符、HTML、全半角 |
| `ValuePresenceClassifier` | 标记 null、empty、dash、unknown_literal、missing_column |
| `NumberParser` | Decimal 数值解析，保留 raw，输出错误标记 |
| `PeriodParser` | 解析 `26W01` 等周字段 |
| `SentenceSplitter` | 卖点和评论句级切分 |
| `CleanHashService` | 基于稳定 JSON 计算 `clean_hash` |
| `CleanSkuBuilder` | 聚合 SKU 主数据、覆盖和冲突 |
| `MarketCleaner` | 清洗 `week_sales_data` |
| `AttributeCleaner` | 清洗 `attribute_data` |
| `ClaimCleaner` | 清洗 `selling_points_data` 和句表 |
| `CommentCleaner` | 清洗 `comment_data`、句表和维度弱标签 |
| `QualityIssueBuilder` | 生成质量问题 |
| `CleaningQualityService` | 编排上述 domain cleaner，返回待写入对象和摘要 |

### 9.2 文本最小规范化

必须做：

- 去除首尾空白。
- 合并连续空白。
- 去不可见控制字符。
- 去 HTML 标签。
- 规范全角英数字和常见标点。
- 保留中文业务表达。

禁止做：

- 不做同义词替换。
- 不做标准参数映射。
- 不做卖点价值判断。
- 不做评论主题、任务、客群、战场推断。

### 9.3 数值和周期解析

数值解析要求：

- 支持整数、小数、千分位和字符串数字。
- 解析失败时 raw 保留，数值字段为 null，质量问题为 `invalid_number`。
- 负销量、负销额、负均价为 `negative_number`。
- 均价校验在销量大于 0 时计算 `sales_amount / sales_volume`。
- 差异超过 1% 且超过 1 元时标记 `price_check_mismatch`。

周期解析要求：

- `26W01` 解析为 `period_type=week`、`period_year_hint=2026`、`period_week_index=1`。
- 不强行推断自然日期。
- 解析失败标记 `period_parse_status=failed`。

### 9.4 SKU 覆盖和缺失表达

`CleanSkuBuilder` 必须聚合四张表的覆盖：

```json
{
  "market": {"row_count": 46, "covered": true},
  "attribute": {"row_count": 81, "covered": true, "unknown_count": 0},
  "claim": {"row_count": 0, "covered": false},
  "comment": {"row_count": 3621, "covered": true, "distinct_comment_id_count": 1648}
}
```

当 SKU 无结构化卖点时，必须写入：

```json
{
  "claim_structured": {
    "missing": true,
    "reason": "本批 selling_points_data 未覆盖该 SKU",
    "business_interpretation": "结构化卖点数据缺失，不代表该 SKU 没有卖点"
  }
}
```

### 9.5 参数清洗

`AttributeCleaner` 必须：

- 保留 `raw_attr_name` 和 `raw_attr_value`。
- 输出 `clean_attr_name` 和 `clean_attr_value`。
- 为 null、空、`-`、`unknown`、`未知`、`暂无` 输出对应 `value_presence`。
- 提取数字候选和单位候选，例如 `300HZ` -> `300`、`HZ`。
- 对同一 SKU 同一属性名多值生成 `conflict_group_key` 和质量问题。
- 不生成标准参数编码。

### 9.6 卖点清洗

`ClaimCleaner` 必须：

- 解析 `variable=卖点1..卖点13` 到 `claim_seq`。
- 解析失败时保留原值，生成 `claim_seq_parse_failed`。
- 去 HTML、去多余空白，保留业务文本。
- 提取标题、冒号、编号、括号等 `structure_hints`。
- 生成卖点句表。
- 不在无卖点 SKU 上伪造 `core3_clean_claim` 行。
- 不把“核心定位、功能价值、情感价值、差异化定位”等标题直接当标准卖点。

### 9.7 评论清洗

`CommentCleaner` 必须：

- 保留 `comment_content` 原文和清洗正文。
- 生成 `comment_text_hash`。
- 保留 `comments_segments` 原文、清洗分段和 `segment_text_hash`。
- 空情感输出 `sentiment_clean=unknown`，不得转中立。
- “此用户没有填写评价”“默认好评”等标记 `low_value_flag=true`，不删除。
- 同一 `comment_id` 多行、同一正文多行、同一分段多行都保留清洗事实。
- 生成系统切句和 source segment 两类句记录。
- 原始维度写入 `core3_clean_comment_dimension`，只作为弱标签。
- 不生成评论主题、任务、客群、战场或竞品结论。

### 9.8 质量问题生成

`QualityIssueBuilder` 必须覆盖：

| 问题类型 | 触发 |
| --- | --- |
| `missing_required_field` | SKU、来源主键、核心事实字段缺失 |
| `invalid_number` | 量价字段无法数值化 |
| `negative_number` | 销量、销额、均价为负 |
| `price_check_mismatch` | 均价与销额/销量不一致 |
| `unknown_value` | 参数值为空、`unknown`、`-` 等 |
| `cross_table_conflict` | 同一 SKU 品牌、型号、品类冲突 |
| `claim_coverage_missing` | SKU 无结构化卖点 |
| `claim_seq_parse_failed` | 卖点序号无法解析 |
| `low_value_comment` | 默认评价、空评价等低价值文本 |
| `duplicate_comment_text` | 评论正文重复 |
| `comment_dimension_missing` | 原始评论维度为空 |
| `comment_split_row_suspected` | 评论拆行明显 |
| `schema_changed` | M00 发现 schema 变化 |
| `clean_hash_changed_high` | 清洗 hash 大面积变化 |

质量问题必须写表，不允许只写日志。

## 10. runner/API 任务

### 10.1 Runner 入口

新增 runner：

```text
CleaningQualityRunner.run(
  project_id,
  category_code,
  batch_id,
  run_id=None,
  module_run_id=None,
  clean_version="m01_clean_v1",
  hash_version="m01_clean_hash_v1",
  mode="incremental"
)
```

返回结构：

```json
{
  "batch_id": "m00_...",
  "module_code": "M01",
  "status": "completed_with_warning",
  "clean_counts": {
    "sku": 35,
    "market": 1326,
    "attribute": 2843,
    "claim": 65,
    "claim_sentence": 0,
    "comment": 62426,
    "comment_sentence": 0,
    "comment_dimension": 62426,
    "quality_issue": 0
  },
  "issue_counts": {
    "info": 0,
    "warning": 0,
    "error": 0
  },
  "review_required": true
}
```

实际 `claim_sentence`、`comment_sentence` 和 `quality_issue` 数量以 fixture 和服务输出为准，测试不得写死为 0。

### 10.2 Runner 流程

Runner 必须按顺序：

1. 校验 M00 batch 可消费。
2. 获取本次清洗范围。
3. 按 source 引用回读原始行。
4. 构建 SKU 覆盖和冲突。
5. 分域清洗市场、参数、卖点、评论。
6. 生成句表和评论维度弱标签。
7. 生成质量问题。
8. 计算 `clean_record_key` 和 `clean_hash`。
9. 幂等写入清洗表和质量问题表。
10. 写入或更新模块运行摘要。
11. 返回运行结果给 M16。

### 10.3 状态规则

| 条件 | Runner 状态 |
| --- | --- |
| 全部成功且无 warning/error | `completed` |
| 存在 warning 但不阻断 | `completed_with_warning` |
| 存在少量行级 error 但模块可继续 | `completed_with_error_rows` |
| M00 batch 不可消费 | `blocked` |
| 清洗表写入失败 | `failed` |
| 同 batch 幂等冲突 | `failed` |

状态值需与 INFRA/M16 runner 协议保持一致；如 INFRA 使用不同状态枚举，M01 按 INFRA 为准，但含义不可丢失。

### 10.4 API

M01 API 是生产线运营和数据排查接口，不是高层报告接口。

建议新增：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/run` | 手工触发 M01 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/summary` | 查看清洗摘要 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/cleaning/skus` | 查看 SKU 覆盖 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/quality-issues` | 查看质量问题 |

API 响应要求：

- 返回中文可读的质量摘要字段。
- 可以包含技术字段供运营排查，但不得作为高层展示页 payload。
- 不返回原始大表全量明细。
- 支持按 `sku_code`、`domain`、`issue_type`、`severity` 过滤质量问题。

## 11. 测试任务

### 11.1 单元测试

`test_m01_cleaning_normalizers.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| 文本规范化 | 去 HTML、不可见字符、首尾空白，保留中文语义 |
| 值存在性 | null、空字符串、`-`、`unknown` 分别标记，均不转 false |
| 数值解析 | 销量、销额、均价转 Decimal |
| 数值异常 | 非法数字和负数输出错误标记 |
| 周期解析 | `26W01` 解析为 week、2026、1 |
| 参数候选 | `300HZ` 提取数字和单位候选 |
| 卖点序号 | `卖点13` 解析为 13 |
| 情感清洗 | 空情感为 `unknown`，不是 `中立` |
| 低价值评论 | 默认评价被标记但不删除 |
| clean hash | 字段顺序不影响 hash，质量状态变化影响 hash |

### 11.2 Repository 测试

`test_m01_cleaning_repositories.py` 覆盖：

- 九张表可插入、查询、按 batch 查询。
- 主事实表唯一键生效。
- 句级表唯一键生效。
- 质量问题幂等唯一键生效。
- 原始表只读 repository 不执行写操作。
- 按 SKU、batch、hash、quality、issue_type 可查询。

### 11.3 Service 测试

`test_m01_cleaning_service.py` 覆盖：

- 市场清洗能解析周期、渠道、平台、量价和均价校验。
- 参数清洗能保留 unknown，不生成标准参数码。
- 卖点清洗能生成 claim 和 sentence，不在无卖点 SKU 上造行。
- 评论清洗能生成 comment、sentence、dimension，保留重复依据。
- SKU 覆盖能表达市场、参数、卖点、评论四域覆盖。
- 质量问题能覆盖缺失、非法、冲突、重复、低价值和覆盖不足。

### 11.4 Runner 测试

`test_m01_cleaning_runner.py` 覆盖：

| 场景 | 断言 |
| --- | --- |
| M00 insert | 生成新清洗事实 |
| M00 update | 生成新清洗事实，clean hash 可变化 |
| M00 no_change | 默认不处理 |
| M00 not_seen | 生成 inactive candidate 或质量问题 |
| M00 skipped | 生成质量问题，不造业务清洗事实 |
| 同 batch 重跑 hash 一致 | 不重复插入 |
| 同 batch 重跑 hash 不一致 | runner 失败 |
| M00 batch failed | M01 blocked |

### 11.5 API 测试

`test_m01_cleaning_api.py` 覆盖：

- 触发 M01 返回 runner 结果。
- summary API 返回清洗数量、质量数量、覆盖摘要。
- skus API 可按 batch 查询 SKU 覆盖。
- quality-issues API 可按 SKU、domain、issue_type、severity 过滤。
- M00 batch 不存在时返回明确错误。
- API 不返回高层报告 payload。

### 11.6 越界测试

`test_m01_no_business_outputs.py` 必须断言：

- M01 不生成 `evidence_id`。
- M01 不生成 `param_code`。
- M01 不生成 `claim_code`。
- M01 不生成 `task_code`。
- M01 不生成 `target_group_code`。
- M01 不生成 `battlefield_code`。
- M01 不生成竞品候选、评分、角色或报告结论。
- M01 不把评论维度直接映射成业务任务。

所有测试不得依赖外部 LLM 调用。

## 12. 205/85E7Q 验收

### 12.1 当前 205 样例硬约束

M01 必须能表达当前真实样例数据限制：

| 数据事实 | M01 表达 |
| --- | --- |
| `week_sales_data` 1326 行、35 个型号 | 市场清洗事实和 SKU 覆盖 |
| `attribute_data` 2843 行、35 个型号 | 参数清洗事实和 unknown 统计 |
| `attribute_data` unknown/空/`-` 约 961 行 | `value_presence` 和 `unknown_value` issue |
| `selling_points_data` 65 行、5 个型号 | 卖点清洗事实和覆盖不足提示 |
| `comment_data` 62426 行、33 个型号 | 评论清洗事实、重复和拆行提示 |
| 当前品牌均为海信 | 只登记事实，不做内外部竞品判断 |
| 当前渠道只有线上 | 只保留线上，不推导线下渠道 |

### 12.2 85E7Q 验收

对 `85E7Q` / `TV00029115` 必须满足：

| 输入事实 | 验收 |
| --- | --- |
| 46 行周销 | `core3_clean_market_weekly` 有对应清洗事实，周期和平台保留 |
| 81 行属性 | `core3_clean_attribute` 有对应清洗事实，unknown 不当 false |
| 0 行结构化卖点 | 不造卖点事实；`core3_clean_sku.coverage_json` 标记 claim 未覆盖 |
| 0 行结构化卖点 | `core3_data_quality_issue` 有 `claim_coverage_missing` |
| 3621 行评论 | `core3_clean_comment` 保留评论行、正文 hash、分段 hash |
| 1648 个不同评论 | 重复依据可供 M05 使用 |

### 12.3 业务含义验收

M01 输出必须能被解释为：

- “85E7Q 可分析，有市场、参数和评论数据。”
- “85E7Q 缺结构化卖点数据，不代表没有卖点。”
- “评论重复、空维度、空情感是数据质量背景，不是直接业务结论。”
- “参数 unknown 是未知，不是能力不存在。”

## 13. 完成标准

M01 编码完成必须满足：

1. 九张 M01 表迁移、模型、schema、repository 已完成。
2. M01 runner 可基于 M00 batch 运行。
3. 清洗事实均保留 `source_row_id`、原始值、清洗值、质量状态和 `clean_hash`。
4. null、空字符串、`-`、`unknown`、缺字段被区分记录，不当 false。
5. 市场量价数值化，均价校验可查询。
6. 参数输出数字候选和单位候选，但不输出标准参数码。
7. 卖点输出原文、清洗文本、句级切分和弱结构提示，但不输出标准卖点码。
8. 评论输出正文 hash、分段 hash、句级文本、维度弱标签、低价值和重复依据。
9. 质量问题可按 batch、SKU、domain、issue_type、severity 查询。
10. 85E7Q 无结构化卖点能稳定跑通，不伪造卖点。
11. M01 不生成 evidence、任务、客群、战场、候选、评分或报告结论。
12. 后端测试通过，且测试不依赖 205 实库或外部 LLM。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 九张表一次性实现过大 | 评审和测试压力大 | 编码时按 migration、model/schema、repository、service、runner/API、测试拆小闭环 |
| unknown 被误判为 false | 后续参数、卖点和竞品结论误导 | 值存在性枚举、单元测试和越界测试固化 |
| 评论维度被直接拿去做业务标签 | 任务、客群、战场推导失真 | M01 只输出弱标签，M06/M09-M11 独立推导 |
| 卖点缺失被解释成产品弱 | 85E7Q 报告误导高层 | `coverage_json`、质量问题和 M15 表达约束共同控制 |
| clean hash 不稳定 | 增量重算混乱 | 复用 INFRA 稳定 JSON/hash 工具，增加字段顺序测试 |
| 同 batch 重跑覆盖旧数据 | 追溯链断裂 | 幂等冲突直接失败，不静默覆盖 |
| 表和旧 MVP 混用 | 旧页面或旧接口受影响 | 独立 v2 表名、service 包和测试目录 |

回滚方式：

- migration downgrade 删除 M01 九张表，不触碰原始四表和 M00 表。
- 若 service 失败，仅标记 M01 module run 失败，不推进 M02。
- 若单个 batch 清洗产物异常，保留失败批次供排查，不用删除历史成功批次。

## 15. 下游依赖

| 下游模块 | 依赖 M01 的产物 |
| --- | --- |
| M02 | 所有清洗事实表、质量状态、原始值、清洗值、`source_row_id` |
| M03 | `core3_clean_attribute` 的属性名、属性值、存在性、数字候选、单位候选、冲突组 |
| M04a | `core3_clean_claim`、`core3_clean_claim_sentence`、卖点覆盖质量问题 |
| M04b | 间接依赖 M04a 和 M05/M06，不直接用 M01 评论维度下结论 |
| M05 | `core3_clean_comment`、`core3_clean_comment_sentence`、hash、低价值、重复依据 |
| M06 | 评论清洗、句表、维度弱标签和情感 unknown 状态 |
| M07 | `core3_clean_market_weekly` 的量价、周期、渠道、平台和校验状态 |
| M08 | SKU 覆盖、参数、卖点、评论、市场清洗基础 |
| M09-M11.5 | 经 M03-M08/M06 转换后的画像，不直接消费原始维度做结论 |
| M12-M15 | 通过上游画像和 evidence 间接依赖 M01 质量和覆盖 |
| M16 | clean hash、质量问题、覆盖摘要、review_required |

## 16. 编码子任务建议

M01 编码不建议一次性完成，应拆成以下小闭环：

| 子任务 | 内容 | 建议验收 |
| --- | --- | --- |
| M01-A | migration 和 SQLAlchemy model | 九张表 create/drop 通过 |
| M01-B | schema 和枚举 | 类型校验和 API schema 测试通过 |
| M01-C | normalizer/parser/hash 单元 | 文本、值存在性、数值、周期、hash 测试通过 |
| M01-D | repository | 插入、查询、幂等、只读边界测试通过 |
| M01-E | market/attribute/claim/comment cleaner | domain service 测试通过 |
| M01-F | SKU coverage 和 quality issue builder | 85E7Q 覆盖和质量问题测试通过 |
| M01-G | runner | 增量状态和幂等重跑测试通过 |
| M01-H | API | run、summary、skus、quality-issues 测试通过 |
| M01-I | 越界和 fixture 验收 | 不生成业务结论，85E7Q 样例跑通 |

编码阶段每次仍应只做一个小闭环，避免一次提交九张表、全部服务和所有 API。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M02_development_tasks.md
```

M02 文档需要基于 M01 清洗事实层设计 evidence 原子层开发任务，重点拆清 evidence 类型、来源引用、短编号、置信度、证据 link、质量降权、追溯查询和禁止业务结论越界。
