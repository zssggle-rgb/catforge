# M05 评论基础证据层开发任务

## 1. 模块目标

M05 的开发目标是把 M02 生成的评论类 evidence 转换成可复用、可追溯、可增量重跑的评论基础证据层。

本模块要解决的工程问题：

1. 把原始评论行、多维度拆行、重复正文和默认评价合并为稳定的去重评论单元。
2. 把评论正文和分段转换成句级评论基础证据，作为 M06 唯一评论句输入。
3. 保留原始维度、原始情感、低价值、重复、质量问题等弱标签。
4. 生成产品体验、产品风险、价格价值感、服务体验、物流安装等弱域提示。
5. 基于 TV seed 的 `comment_topics` 生成弱主题提示。
6. 聚合 SKU 粒度评论质量画像，供 M06/M08/M15/M16 判断评论证据是否可用。
7. 固化真实样例数据约束，尤其 85E7Q 评论可以形成可用画像，但不能因为无结构化卖点而失败。

M05 的边界必须清楚：

- M05 只输出评论基础证据、弱域、弱主题和质量画像。
- M05 不直接生成用户任务、目标客群、价值战场、卖点激活、竞品判断或报告结论。
- M05 的主题提示只是“这句话可能涉及某主题”，不是业务结论。
- M05 不直接读取原始 `comment_data`，首版默认只读 M02 evidence。
- M05 不能把服务、安装、物流好评误用于产品卖点高置信验证。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M02 任务 | `docs/core3_mvp/real_data_v2/development/M02_development_tasks.md` |
| M04a 任务 | `docs/core3_mvp/real_data_v2/development/M04a_development_tasks.md` |
| M05 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M05_comment_evidence_requirements.md` |
| M05 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M05_comment_evidence_design.md` |
| M02 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M02_evidence_atom_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M02 可以输出 `comment_raw`、`comment_sentence`、`comment_dimension`、comment 相关 `quality_issue` evidence。
- M02 evidence 中保留 `source_row_id`、`clean_record_key`、`comment_id`、`comment_text_hash`、`segment_text_hash`、`sentence_seq` 等追溯字段。
- TV seed 中存在 `comment_topics`，且包含 M05 需求列出的首版主题。
- INFRA 的 hash、分页、runner 结果、审计字段和 fixture 规范已经可用。

## 3. 本次范围

本次开发任务拆分覆盖 M05 的全部后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 5 张 M05 输出表 |
| schema | 新增 M05 输入、输出、API、runner、统计、复核 schema |
| repository | 只读 M02 evidence 和 seed，写 M05 输出表 |
| service | 评论单元、证据 link、句级 atom、弱域、情感、弱主题、质量画像 |
| runner | `run_core3_m05_comment_evidence` |
| API | M05 运营查看和证据钻取 API |
| 测试 | 单元、集成、边界、越界、85E7Q fixture |
| 增量 | fingerprint、result_hash、is_current、下游影响登记 |

本次不做：

- 不实现 M06 下游信号抽取。
- 不实现 M04b 评论验证增强。
- 不实现 M09 用户任务、M10 客群、M11 战场。
- 不实现 M12-M15 竞品、评分、报告。
- 不改前端高层展示页。
- 不部署到 205。
- 不把 M05 API 输出直接作为业务高层页面结论。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/comment_evidence_schemas.py
apps/api-server/app/services/core3_real_data/comment_evidence_repositories.py
apps/api-server/app/services/core3_real_data/comment_evidence_input_service.py
apps/api-server/app/services/core3_real_data/comment_unit_builder.py
apps/api-server/app/services/core3_real_data/comment_unit_link_builder.py
apps/api-server/app/services/core3_real_data/comment_sentence_atom_builder.py
apps/api-server/app/services/core3_real_data/comment_domain_hint_service.py
apps/api-server/app/services/core3_real_data/comment_sentiment_hint_service.py
apps/api-server/app/services/core3_real_data/comment_topic_hint_matcher.py
apps/api-server/app/services/core3_real_data/comment_quality_profile_service.py
apps/api-server/app/services/core3_real_data/comment_evidence_review_policy.py
apps/api-server/app/services/core3_real_data/comment_evidence_service.py
apps/api-server/app/services/core3_real_data/comment_evidence_runner.py
apps/api-server/app/services/core3_real_data/comment_topic_seed_loader.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `comment_evidence_schemas.py` | M05 内部 dataclass/Pydantic typed contracts |
| `comment_evidence_repositories.py` | M05 表读写 repository |
| `comment_evidence_input_service.py` | 读取 M02 evidence、seed、计算输入 fingerprint |
| `comment_unit_builder.py` | 构建去重评论单元 |
| `comment_unit_link_builder.py` | 构建评论单元到 M02 evidence 的 link |
| `comment_sentence_atom_builder.py` | 构建 M05 句级评论基础证据 |
| `comment_domain_hint_service.py` | 生成弱域提示和服务隔离 guardrail |
| `comment_sentiment_hint_service.py` | 生成情感弱标签和冲突标记 |
| `comment_topic_hint_matcher.py` | 基于 seed 生成弱主题提示 |
| `comment_quality_profile_service.py` | 聚合 SKU 评论质量画像 |
| `comment_evidence_review_policy.py` | warning/review/block 规则 |
| `comment_evidence_service.py` | M05 模块编排 service |
| `comment_evidence_runner.py` | 模块入口和 runner result |
| `comment_topic_seed_loader.py` | 加载并校验 TV `comment_topics` seed |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0011_core3_real_data_comment_evidence.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0011_core3_real_data_comment_evidence.py` | 新增 M05 输出表、索引、约束 |
| `core3_real_data.py` | 导出 M05 API schema |
| `core3_real_data.py` API | 增加 M05 运营查看和证据钻取 API |
| `constants.py` | 如 INFRA 未包含，补 M05 枚举 |
| `runner.py` | 注册 M05 runner，不改变已有模块逻辑 |
| `conftest.py` | 增加 M05 fixture、85E7Q 评论样例、seed fixture |

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m05_comment_topic_seed_loader.py
apps/api-server/tests/core3_real_data/test_m05_comment_unit_builder.py
apps/api-server/tests/core3_real_data/test_m05_comment_unit_link_builder.py
apps/api-server/tests/core3_real_data/test_m05_sentence_atom_builder.py
apps/api-server/tests/core3_real_data/test_m05_domain_hint_service.py
apps/api-server/tests/core3_real_data/test_m05_sentiment_hint_service.py
apps/api-server/tests/core3_real_data/test_m05_topic_hint_matcher.py
apps/api-server/tests/core3_real_data/test_m05_quality_profile_service.py
apps/api-server/tests/core3_real_data/test_m05_review_policy.py
apps/api-server/tests/core3_real_data/test_m05_repositories.py
apps/api-server/tests/core3_real_data/test_m05_runner.py
apps/api-server/tests/core3_real_data/test_m05_api.py
apps/api-server/tests/core3_real_data/test_m05_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m05_85e7q_fixture.py
```

### 4.4 只读依赖文件

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
apps/api-server/app/services/core3_real_data/evidence_atom_schemas.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
```

首版不要修改 `tv_core3_mvp_seed_v0_2.json`。如果 seed 缺主题或主题内容不完整，应新增独立 seed 评审任务，不在 M05 编码任务里顺手补业务口径。

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
```

不允许改动的业务对象：

- 原始四表结构。
- 旧 `core3_mvp` 粗粒度页面和服务。
- M04a 表结构和卖点激活逻辑。
- M06 及之后模块的输出表。
- 前端高层报告页面。
- 205 部署配置。

不允许引入的行为：

- 直接读取原始 `comment_data`。
- 使用 M05 弱主题直接生成 `task_code`。
- 使用 M05 弱主题直接生成 `target_group_code`。
- 使用 M05 弱主题直接生成 `battlefield_code`。
- 使用 M05 弱主题直接生成竞品理由。
- 写入 `core3_sku_claim_activation` 或 M04b 最终卖点表。
- 在测试里调用外部 LLM。
- 把情感空值当成 neutral。
- 把 `TOPIC_INSTALLATION_SERVICE` 当作产品卖点高置信证据。

## 6. 数据库迁移任务

### 6.1 迁移文件

新增迁移：

```text
apps/api-server/alembic/versions/0011_core3_real_data_comment_evidence.py
```

迁移只新增 M05 所需表，不修改上游和下游表。

### 6.2 新增表

| 表 | 粒度 | 说明 |
| --- | --- | --- |
| `core3_comment_unit` | SKU + 去重评论单元 | 评论去重后的计数和追溯单元 |
| `core3_comment_unit_evidence_link` | 评论单元 + M02 evidence | 评论单元与 M02 evidence 多对多关系 |
| `core3_comment_evidence_atom` | 评论单元 + 句子 | M05 句级评论基础证据 |
| `core3_comment_topic_hint` | 句级证据 + topic | 基础弱主题提示 |
| `core3_comment_quality_profile` | SKU + 批次 | SKU 评论质量画像 |

### 6.3 通用字段

5 张表均应包含：

```text
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
brand_name
rule_version
asset_version
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

字段要求：

| 字段 | 要求 |
| --- | --- |
| `project_id` | 非空 |
| `category_code` | 非空，MVP 为 `TV` |
| `batch_id` | 非空 |
| `rule_version` | 非空，建议首版 `m05_comment_evidence_v1` |
| `asset_version` | 非空，来自 seed loader |
| `input_fingerprint` | 非空 |
| `result_hash` | 非空 |
| `is_current` | 默认 true |
| `processing_status` | 限定 `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_status` | 限定 `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| JSON 字段 | PostgreSQL 使用 `JSONB` |
| 时间字段 | `created_at`、`updated_at` 使用 timezone aware |

### 6.4 `core3_comment_unit`

#### 6.4.1 字段

```text
comment_unit_id
comment_unit_key
dedup_strategy
comment_id
comment_text_hash
canonical_comment_text
canonical_text_length
source_row_count
source_sentence_count
source_dimension_count
source_quality_issue_count
source_comment_evidence_ids
source_sentence_evidence_ids
source_dimension_evidence_ids
source_quality_evidence_ids
raw_dimension_paths
sentiment_raw_set
sentiment_hint
sentiment_conflict_flag
low_value_flag
low_value_reasons
duplicate_group_id
duplicate_source_count
comment_unit_status
quality_flags
confidence
confidence_level
```

#### 6.4.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `comment_unit_id` |
| 唯一键 | `project_id, category_code, batch_id, comment_unit_key, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, comment_id` |
| 索引 | `sku_code, comment_text_hash` |
| 索引 | `duplicate_group_id` |
| 索引 | `comment_unit_status` |
| 索引 | `review_required` |
| GIN | `raw_dimension_paths`、`quality_flags`、`low_value_reasons` |

#### 6.4.3 约束

| 约束 | 说明 |
| --- | --- |
| `dedup_strategy` | `comment_id`、`text_hash`、`source_row_fallback` |
| `comment_unit_status` | `usable`、`low_value`、`duplicate_only`、`blocked` |
| `sentiment_hint` | `positive`、`negative`、`neutral`、`unknown`、`conflict` |
| `confidence` | 0-1 |
| `source_row_count` | >= 0 |
| `canonical_text_length` | >= 0 |

### 6.5 `core3_comment_unit_evidence_link`

#### 6.5.1 字段

```text
unit_link_id
comment_unit_id
source_evidence_id
source_evidence_type
link_role
source_row_id
comment_id
comment_text_hash
sentence_hash
dimension_path_raw
quality_issue_type
```

加通用字段时，`sku_code`、`batch_id` 等字段也保留，便于分页查询和追溯。

#### 6.5.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `unit_link_id` |
| 唯一键 | `comment_unit_id, source_evidence_id, link_role, rule_version` |
| 索引 | `source_evidence_id` |
| 索引 | `source_evidence_type` |
| 索引 | `sku_code, comment_id` |
| 索引 | `comment_text_hash` |

#### 6.5.3 约束

| 约束 | 说明 |
| --- | --- |
| `source_evidence_type` | `comment_raw`、`comment_sentence`、`comment_dimension`、`quality_issue` |
| `link_role` | `raw_source`、`sentence_source`、`dimension_weak_label`、`quality_flag` |

### 6.6 `core3_comment_evidence_atom`

#### 6.6.1 字段

```text
comment_evidence_id
comment_evidence_key
comment_unit_id
comment_id
comment_text_hash
sentence_hash
sentence_seq
sentence_source_priority
sentence_text
normalized_sentence_text
sentence_length
source_sentence_evidence_ids
source_comment_evidence_ids
source_dimension_evidence_ids
source_quality_evidence_ids
raw_dimension_paths
domain_hints
primary_domain_hint
domain_conflict_flag
sentiment_hint
sentiment_source
sentiment_conflict_flag
low_value_flag
low_value_reasons
duplicate_group_id
sentence_duplicate_group_id
specificity_score
representative_phrase
representative_phrase_rule
usable_for_downstream
downstream_block_reasons
confidence
confidence_level
```

#### 6.6.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `comment_evidence_id` |
| 唯一键 | `project_id, category_code, batch_id, comment_evidence_key, rule_version` |
| 索引 | `sku_code, comment_unit_id` |
| 索引 | `sku_code, sentence_hash` |
| 索引 | `primary_domain_hint` |
| 索引 | `sentiment_hint` |
| 索引 | `low_value_flag` |
| 索引 | `usable_for_downstream` |
| 索引 | `review_required` |
| GIN | `domain_hints`、`raw_dimension_paths`、`low_value_reasons`、`downstream_block_reasons` |

#### 6.6.3 约束

| 约束 | 说明 |
| --- | --- |
| `sentence_source_priority` | `system_split`、`source_segment`、`raw_fallback` |
| `primary_domain_hint` | `product_experience`、`product_risk`、`market_perception`、`service_experience`、`logistics_installation`、`unknown` |
| `sentiment_source` | `raw_only`、`text_rule`、`raw_text_combined`、`unknown` |
| `specificity_score` | 0-1 |
| `confidence` | 0-1 |

### 6.7 `core3_comment_topic_hint`

#### 6.7.1 字段

```text
topic_hint_id
comment_evidence_id
comment_unit_id
topic_code
topic_name
topic_group
topic_definition
match_method
matched_terms
match_source_json
polarity_hint
topic_confidence
is_weak_hint
activates_product_claim
service_guardrail_flag
mapped_claim_codes_snapshot
mapped_task_codes_snapshot
mapped_battlefield_codes_snapshot
topic_hint_status
```

#### 6.7.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `topic_hint_id` |
| 唯一键 | `comment_evidence_id, topic_code, match_method, rule_version` |
| 索引 | `sku_code, topic_code` |
| 索引 | `topic_group` |
| 索引 | `polarity_hint` |
| 索引 | `topic_hint_status` |
| GIN | `matched_terms`、`match_source_json`、`mapped_claim_codes_snapshot`、`mapped_task_codes_snapshot`、`mapped_battlefield_codes_snapshot` |

#### 6.7.3 约束

| 约束 | 说明 |
| --- | --- |
| `is_weak_hint` | 必须为 true |
| `match_method` | `keyword`、`positive_keyword`、`negative_keyword`、`dimension_path`、`phrase`、`seed_rule` |
| `polarity_hint` | `positive`、`negative`、`neutral`、`unknown` |
| `topic_hint_status` | `matched`、`low_confidence`、`blocked_low_value`、`blocked_service_guardrail` |
| `topic_confidence` | 0-1 |

### 6.8 `core3_comment_quality_profile`

#### 6.8.1 字段

```text
comment_quality_profile_id
profile_key
raw_comment_row_count
comment_unit_count
distinct_comment_id_count
distinct_comment_text_count
sentence_count
usable_sentence_count
low_value_unit_count
low_value_sentence_count
duplicate_text_rate
duplicate_row_rate
empty_dimension_count
empty_dimension_rate
sentiment_distribution_json
sentiment_unknown_rate
sentiment_conflict_rate
domain_distribution_json
topic_distribution_json
service_installation_share
product_experience_share
negative_sentence_rate
sample_status
comment_usability_score
quality_summary
warning_flags
blocked_reasons
downstream_ready
```

#### 6.8.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `comment_quality_profile_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, rule_version, asset_version` |
| 索引 | `sku_code, sample_status` |
| 索引 | `downstream_ready` |
| 索引 | `review_required` |
| GIN | `sentiment_distribution_json`、`domain_distribution_json`、`topic_distribution_json`、`warning_flags`、`blocked_reasons` |

#### 6.8.3 约束

| 约束 | 说明 |
| --- | --- |
| `sample_status` | `sufficient`、`limited`、`insufficient`、`unknown` |
| 比率字段 | 0-1 |
| 计数字段 | >= 0 |
| `downstream_ready` | 无评论或 blocked 时 false |

### 6.9 迁移回滚

`downgrade` 按依赖反向删除：

1. `core3_comment_topic_hint`
2. `core3_comment_evidence_atom`
3. `core3_comment_unit_evidence_link`
4. `core3_comment_quality_profile`
5. `core3_comment_unit`

回滚不得删除上游 M02 evidence 表。

## 7. model/schema 任务

### 7.1 内部 schema

在 `comment_evidence_schemas.py` 中定义：

```text
M05RunRequest
M05RunResult
M05SkuInputBundle
M05EvidenceInput
CommentTopicSeed
CommentTopicSeedIndex
CommentUnitCandidate
CommentUnitRecord
CommentUnitEvidenceLinkRecord
CommentSentenceCandidate
CommentEvidenceAtomRecord
DomainHint
SentimentHint
TopicHintRecord
CommentQualityProfileRecord
M05ReviewIssue
M05DownstreamImpact
```

### 7.2 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 中导出：

```text
CommentQualityProfileResponse
CommentEvidenceAtomResponse
CommentEvidenceAtomListResponse
CommentTopicHintResponse
CommentTopicHintListResponse
CommentUnitSourceResponse
CommentUnitSourceListResponse
M05RunResponse
```

API schema 要使用业务中文字段别名或业务化解释字段，避免把内部枚举裸露给高层页面。

示例：

| 内部字段 | API 展示字段 |
| --- | --- |
| `sample_status='sufficient'` | `样本充足` |
| `primary_domain_hint='service_experience'` | `服务体验` |
| `topic_hint_status='low_confidence'` | `弱提示，需谨慎使用` |
| `is_weak_hint=true` | `基础线索` |

### 7.3 枚举和常量

如 `constants.py` 尚未包含 M05 枚举，需要补：

```text
M05_RULE_VERSION = "m05_comment_evidence_v1"
COMMENT_UNIT_STATUS
COMMENT_DEDUP_STRATEGY
COMMENT_DOMAIN_HINT
COMMENT_SENTIMENT_HINT
COMMENT_SENTIMENT_SOURCE
COMMENT_LOW_VALUE_REASON
COMMENT_TOPIC_MATCH_METHOD
COMMENT_TOPIC_HINT_STATUS
COMMENT_SAMPLE_STATUS
COMMENT_REVIEW_REASON_CODE
```

禁止使用裸字符串散落在 service 中。

### 7.4 schema 校验规则

| 对象 | 校验 |
| --- | --- |
| `M05RunRequest` | `project_id/category_code/batch_id` 非空，`sku_scope` 可为空 |
| `M05EvidenceInput` | evidence type 必须是 M05 允许类型 |
| `CommentUnitRecord` | `comment_id`、`comment_text_hash`、`source_row_id` 至少一个可追溯 |
| `CommentEvidenceAtomRecord` | `sentence_text` 非空，`source_evidence_ids` 非空，低价值句可 `usable_for_downstream=false` |
| `TopicHintRecord` | `is_weak_hint=true`，`topic_code` 必须来自 seed |
| `CommentQualityProfileRecord` | 计数和比率一致，`downstream_ready=false` 时必须有原因 |

### 7.5 序列化要求

- JSONB 字段在 schema 中使用 `dict` 或 `list[dict]`。
- `confidence`、比率、分数使用 `Decimal` 或 float，但输出保留 2-4 位即可。
- `sentence_text` 可保留原文，但 API 返回应支持分页和最大长度限制。
- API 不返回 UUID 大段列表给高层页面；证据钻取 API 可以返回短证据编号和明细。

## 8. repository 任务

### 8.1 Repository 文件

新增：

```text
apps/api-server/app/services/core3_real_data/comment_evidence_repositories.py
```

### 8.2 Repository 类

```text
CommentEvidenceInputRepository
CommentUnitRepository
CommentUnitEvidenceLinkRepository
CommentEvidenceAtomRepository
CommentTopicHintRepository
CommentQualityProfileRepository
CommentEvidenceReadRepository
```

### 8.3 `CommentEvidenceInputRepository`

只读 M02 evidence。

方法：

| 方法 | 说明 |
| --- | --- |
| `list_comment_evidence(project_id, category_code, batch_id, sku_scope, evidence_types, page_size)` | 分页读取 M02 评论 evidence |
| `list_sku_codes_with_comment_evidence(project_id, category_code, batch_id)` | 找出有评论 evidence 的 SKU |
| `get_evidence_result_hashes(evidence_ids)` | 读取上游 evidence hash |
| `assert_m02_completed(project_id, category_code, batch_id)` | 检查 M02 是否完成 |

限制：

- 不读取原始 `comment_data`。
- 不读取 `week_sales_data`、`attribute_data`、`selling_points_data`。
- 不在 repository 中做业务判定。

### 8.4 `CommentUnitRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `get_current_by_fingerprint(project_id, category_code, batch_id, sku_code, input_fingerprint)` | 判断是否可跳过 |
| `mark_previous_inactive(project_id, category_code, batch_id, sku_code, rule_version)` | 将旧版本置为非当前 |
| `bulk_upsert_comment_units(records)` | 批量写入评论单元 |
| `list_current_units(project_id, category_code, batch_id, sku_code)` | 下游读取当前单元 |
| `get_unit(comment_unit_id)` | API 查单元 |

### 8.5 `CommentUnitEvidenceLinkRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `delete_current_links_for_sku(project_id, category_code, batch_id, sku_code, rule_version)` | 重跑前清理当前 link |
| `bulk_insert_links(records)` | 批量插入 link |
| `list_links_by_unit(comment_unit_id, limit, offset)` | API 分页追溯 |
| `list_links_by_source_evidence(source_evidence_id)` | 从 M02 evidence 反查 M05 单元 |

### 8.6 `CommentEvidenceAtomRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_atoms(records)` | 批量写句级 atom |
| `list_current_atoms(project_id, category_code, batch_id, sku_code, filters, limit, offset)` | M06 和 API 读取 |
| `count_usable_atoms(project_id, category_code, batch_id, sku_code)` | 画像和 runner 统计 |
| `mark_previous_inactive(...)` | 版本切换 |

API filters 至少支持：

- `primary_domain_hint`
- `sentiment_hint`
- `low_value_flag`
- `usable_for_downstream`
- `topic_code`，通过 topic hint join 或二次查询实现

### 8.7 `CommentTopicHintRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_topic_hints(records)` | 批量写 topic hint |
| `list_current_topic_hints(project_id, category_code, batch_id, sku_code, filters, limit, offset)` | API 和 M06 读取 |
| `aggregate_topic_distribution(project_id, category_code, batch_id, sku_code)` | 质量画像聚合 |
| `mark_previous_inactive(...)` | 版本切换 |

### 8.8 `CommentQualityProfileRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `upsert_profile(record)` | 写 SKU 评论质量画像 |
| `get_current_profile(project_id, category_code, batch_id, sku_code)` | M06/M08/M16 读取 |
| `list_profiles(project_id, category_code, batch_id, filters, limit, offset)` | 运营查看 |
| `list_review_required_profiles(project_id, category_code, batch_id)` | M16 复核入口 |

### 8.9 `CommentEvidenceReadRepository`

用于 API 聚合查询，不承载业务计算。

方法：

| 方法 | 说明 |
| --- | --- |
| `get_quality_profile_response(...)` | 返回业务化 profile |
| `list_atom_response(...)` | 返回句级证据列表 |
| `list_topic_hint_response(...)` | 返回弱主题提示列表 |
| `list_unit_source_response(...)` | 返回来源 evidence link |

### 8.10 Repository 测试要求

必须覆盖：

- 批量插入和二次运行幂等。
- `is_current=false` 版本不会被下游读取。
- link 表可从 comment unit 查回 M02 evidence。
- API 分页不会一次返回所有评论。
- 不存在读取原始 `comment_data` 的 repository 方法。

## 9. service 任务

### 9.1 `CommentTopicSeedLoader`

职责：

1. 读取 `tv_core3_mvp_seed_v0_2.json.comment_topics`。
2. 校验 16 个首版主题存在。
3. 构建 keyword、positive_keyword、negative_keyword、alias、dimension path 索引。
4. 生成 `asset_version` 和 seed content hash。
5. 输出 `CommentTopicSeedIndex`。

必须覆盖的主题：

```text
TOPIC_PICTURE_QUALITY
TOPIC_BRIGHTNESS_HDR
TOPIC_DARK_SCENE_CONTRAST
TOPIC_SPORTS_WATCHING
TOPIC_GAMING_SMOOTHNESS
TOPIC_EYE_COMFORT
TOPIC_EASE_OF_USE
TOPIC_SENIOR_FRIENDLY
TOPIC_CHILD_FAMILY
TOPIC_INTERFACE_CONNECTIVITY
TOPIC_AUDIO_QUALITY
TOPIC_SYSTEM_ADS_PERFORMANCE
TOPIC_SIZE_SPACE_FIT
TOPIC_PRICE_VALUE
TOPIC_INSTALLATION_SERVICE
TOPIC_DURABILITY_QUALITY
```

seed 缺失时：

- runner 返回 `blocked`。
- 不生成 topic hint。
- 不静默使用临时硬编码主题。

### 9.2 `CommentEvidenceInputService`

职责：

1. 校验 M02 当前批次已完成。
2. 按 SKU 分页读取 `comment_raw`、`comment_sentence`、`comment_dimension`、`quality_issue` evidence。
3. 按 `sku_code` 组装 `M05SkuInputBundle`。
4. 计算 SKU 级 `input_fingerprint`。
5. 识别输入缺失、追溯缺失和可降级场景。

输入处理策略：

| 场景 | 处理 |
| --- | --- |
| 无 `comment_raw` | 写 profile，`sample_status='unknown'`，`downstream_ready=false` |
| 有 raw 无 sentence | 用 M02 raw payload 降级切句，`sentence_source_priority='raw_fallback'`，review |
| 无 dimension | 不阻断，画像记录维度缺失 |
| 无 quality_issue | 不阻断，低价值仅靠 M05 规则 |
| evidence 无法追溯 M01 clean key | 当前 SKU `blocked` |
| evidence 缺 `comment_id` 和 `comment_text_hash` | 尝试 `source_row_id` 降级，review |

### 9.3 `CommentUnitBuilder`

职责：

1. 按去重键生成 `comment_unit_key`。
2. 合并同评论多维度拆行。
3. 汇总 raw、sentence、dimension、quality evidence ID。
4. 识别低价值评论单元。
5. 计算 `sentiment_raw_set`、`sentiment_hint`、`sentiment_conflict_flag`。
6. 生成 `duplicate_group_id`。
7. 计算评论单元置信度。

去重优先级：

| 优先级 | 条件 | `dedup_strategy` | 影响 |
| ---: | --- | --- | --- |
| 1 | 有 `comment_id` | `comment_id` | 标准 |
| 2 | 无 comment_id，有 `comment_text_hash` | `text_hash` | 置信度降低 0.08 |
| 3 | 二者缺失，有 `source_row_id` | `source_row_fallback` | 置信度降低 0.25 且 review |
| 4 | 全缺 | 不生成单元 | blocked |

低价值原因：

| 原因 | 规则 |
| --- | --- |
| `empty_text` | 文本为空 |
| `default_positive` | 包含“此用户没有填写评价”“默认好评”等 |
| `punctuation_only` | 去标点后无有效字符 |
| `too_short_generic` | 过短且只有“很好”“不错”“满意”等泛化词 |
| `template_duplicate` | 同 SKU 同正文重复来源超过阈值 |
| `service_only_for_product_use` | 只描述送装服务，不能作为产品体验信号 |
| `quality_issue_flagged` | M02 quality evidence 已标记 |

### 9.4 `CommentUnitLinkBuilder`

职责：

1. 为每个评论单元生成 source evidence link。
2. 根据 evidence type 设置 `link_role`。
3. 保留 `source_row_id`、`comment_id`、`sentence_hash`、`dimension_path_raw`、`quality_issue_type`。
4. 支持 API 分页追溯。

link role 规则：

| evidence type | link role |
| --- | --- |
| `comment_raw` | `raw_source` |
| `comment_sentence` | `sentence_source` |
| `comment_dimension` | `dimension_weak_label` |
| `quality_issue` | `quality_flag` |

### 9.5 `CommentSentenceAtomBuilder`

职责：

1. 从评论单元和 sentence evidence 构建句级 atom。
2. 同一单元内相同 `sentence_hash` 只生成一个 atom。
3. 缺 sentence evidence 时，从 M02 raw payload 降级切句。
4. 保留 source evidence ID 数组。
5. 计算句级低价值、具体程度、代表短语和下游可用性。

句源优先级：

| 优先级 | 来源 | `sentence_source_priority` |
| ---: | --- | --- |
| 1 | M01 系统切句对应 M02 `comment_sentence` | `system_split` |
| 2 | 原始 `comments_segments` 对应 evidence | `source_segment` |
| 3 | M02 `comment_raw` payload 降级切句 | `raw_fallback` |

下游可用性：

| 条件 | `usable_for_downstream` |
| --- | --- |
| 低价值句 | false |
| 句长过短且无业务词 | false |
| 只有安装服务词 | true，但只可进入 M06 `service_signal` |
| 有产品体验词且非低价值 | true |
| 情感 unknown 但文本具体 | true |
| 维度为空但文本具体 | true |

具体程度公式首版按详细设计实现，分项可以在 `specificity_debug_json` 内部调试，但不必须落表。

### 9.6 `CommentDomainHintService`

职责：

1. 基于文本关键词生成弱域提示。
2. 基于原始维度路径给弱域加权。
3. 处理产品和服务冲突。
4. 输出 `domain_hints` 和 `primary_domain_hint`。

弱域：

| 弱域 | 中文 |
| --- | --- |
| `product_experience` | 产品体验 |
| `product_risk` | 产品风险 |
| `market_perception` | 价格价值感 |
| `service_experience` | 服务体验 |
| `logistics_installation` | 物流安装 |
| `unknown` | 未知 |

服务隔离规则：

1. 主体是安装师傅、物流、客服、售后时，主弱域是服务或物流。
2. 主体是画质、音质、系统、游戏时，服务词只作为次弱域。
3. 服务弱域必须带 `guardrail='service_only'`。
4. 服务类句子不能在 M04b 中直接增强产品卖点。

### 9.7 `CommentSentimentHintService`

职责：

1. 将原始情感和文本规则合并为弱情感。
2. 空情感落为 `unknown`。
3. 原始情感和文本强冲突时落为 `conflict`。
4. 低价值文本降低置信度。

输出规则：

| 原始情感 | 文本规则 | 输出 |
| --- | --- | --- |
| 正面 | 正向词 | `positive` |
| 负面 | 负向词 | `negative` |
| 中立 | 无明显正负 | `neutral` |
| 空 | 无明显正负 | `unknown` |
| 空 | 正向词 | `positive` |
| 空 | 负向词 | `negative` |
| 正面 | 强负向词 | `conflict` |
| 负面 | 强正向词 | `conflict` |

### 9.8 `CommentTopicHintMatcher`

职责：

1. 使用 seed 的关键词、正向词、负向词、别名、主题组。
2. 对每个句级 atom 生成 0-N 条 topic hint。
3. 不落 `TOPIC_UNKNOWN` 主题，只在 profile 中统计 unknown。
4. 低价值句不生成强主题，只可生成 `blocked_low_value` 状态。
5. 服务主题必须设置 `service_guardrail_flag=true`。

匹配顺序：

1. 低价值句先阻断强主题。
2. 命中 `negative_keywords`，`polarity_hint='negative'`。
3. 命中 `positive_keywords`，`polarity_hint='positive'`。
4. 命中 `keywords` 或 aliases，结合句子情感生成 polarity。
5. 原始维度只加权，不单独生成高置信主题。
6. 多主题并存，但每条都要保留命中词和来源。

topic confidence：

```text
topic_confidence =
  0.45 * keyword_match_score
+ 0.20 * polarity_match_score
+ 0.15 * domain_consistency_score
+ 0.10 * dimension_support_score
+ 0.10 * specificity_score
- 0.30 * low_value_penalty
- 0.20 * service_product_conflict_penalty
```

阈值：

| 置信度 | 状态 |
| --- | --- |
| >= 0.75 | `matched` |
| 0.50-0.75 | `low_confidence` |
| < 0.50 | 不写 topic hint，计入 unknown |

### 9.9 `CommentQualityProfileService`

职责：

1. 聚合 SKU 评论行数、评论单元数、正文数和句数。
2. 聚合低价值、重复、空维度、情感 unknown、情感冲突。
3. 聚合弱域分布和弱主题分布。
4. 计算服务安装占比、产品体验占比、负向句占比。
5. 生成 `sample_status`、`comment_usability_score`、`downstream_ready`。
6. 生成中文 `quality_summary`。

核心公式：

```text
duplicate_text_rate = 1 - distinct_comment_text_count / max(raw_comment_row_count, 1)
duplicate_row_rate = 1 - comment_unit_count / max(raw_comment_row_count, 1)
sentiment_unknown_rate = unknown_sentiment_sentence_count / max(sentence_count, 1)
service_installation_share = service_or_logistics_sentence_count / max(usable_sentence_count, 1)
product_experience_share = product_experience_sentence_count / max(usable_sentence_count, 1)
```

样本状态：

| 条件 | `sample_status` |
| --- | --- |
| `comment_unit_count >= 300` 且 `usable_sentence_count >= 500` | `sufficient` |
| `comment_unit_count >= 80` 且 `usable_sentence_count >= 120` | `limited` |
| `comment_unit_count > 0` | `insufficient` |
| 无评论 | `unknown` |

### 9.10 `CommentEvidenceReviewPolicy`

warning 条件：

| 条件 | warning |
| --- | --- |
| `duplicate_text_rate > 0.65` | 正文重复过高 |
| `low_value_sentence_count / sentence_count > 0.40` | 低价值评论占比高 |
| `empty_dimension_rate > 0.50` | 原始维度缺失高 |
| `sentiment_unknown_rate > 0.40` | 情感 unknown 高 |
| `service_installation_share > 0.50` | 服务安装评论可能淹没产品体验 |
| `topic_unknown_rate > 0.45` | 高频未知主题 |
| `domain_conflict_rate > 0.20` | 维度和文本域冲突明显 |

review 条件：

| 条件 | 处理 |
| --- | --- |
| 重点 SKU `sample_status='insufficient'` | 进入复核 |
| 85E7Q 去重后评论单元数明显低于 1648 合理范围 | 进入复核 |
| 服务类评论被主题匹配为产品体验高置信 | 进入复核 |
| 原始正面但文本负面冲突率高 | 进入复核 |
| 负面评论集中且 `negative_sentence_rate > 0.15` | 进入复核 |
| 新高频词未命中任何 seed topic | 进入 seed 复核 |
| M02 evidence 追溯链缺失但仍可降级生成 | 进入复核 |

blocked 条件：

| 条件 | 处理 |
| --- | --- |
| seed 无法加载 | M05 blocked |
| M02 未完成 | M05 blocked |
| SKU 的 M02 comment_raw evidence 无法追溯清洗记录 | 当前 SKU blocked |
| comment_raw 全部缺少 comment_id、text_hash、source_row_id | 当前 SKU blocked |
| 数据库写入核心表失败 | M05 failed |

### 9.11 `CommentEvidenceService`

主流程：

```text
load seed
load sku input bundle
check reusable by input_fingerprint
build comment units
build evidence links
build sentence atoms
apply domain hints
apply sentiment hints
match topic hints
build quality profile
apply review policy
write new current records
mark old records inactive
return M05RunResult and downstream impacts
```

幂等规则：

| 情况 | 动作 |
| --- | --- |
| input fingerprint 未变且当前记录 success/warning | 跳过重算 |
| input fingerprint 未变但 `force=true` | 重算 |
| result hash 相同 | 可更新时间和 module run id |
| result hash 不同 | 旧记录 `is_current=false`，插入新记录 |
| 上游 evidence 失效 | 当前输出 warning 或 inactive |

### 9.12 下游影响登记

M05 不直接调用 M06/M04b，只返回影响范围：

| M05 变化对象 | 下游影响 |
| --- | --- |
| 评论单元新增/删除 | M06 当前 SKU 全量重算 |
| 句级 atom 变化 | M06 当前 SKU 增量重算 |
| topic hint 变化 | M06 当前 SKU 相关 signal type 重算 |
| profile ready 变 blocked | 阻断 M06，并通知 M16 |
| profile warning 变化 | M06 可继续，M16 记录复核 |

## 10. runner/API 任务

### 10.1 Runner 入口

新增：

```text
run_core3_m05_comment_evidence(
  project_id: str,
  category_code: str,
  batch_id: str,
  sku_scope: list[str] | None,
  force: bool = False,
  run_id: str | None = None
) -> M05RunResult
```

### 10.2 Runner 返回

```json
{
  "module": "M05",
  "status": "completed_with_warning",
  "processed_sku_count": 33,
  "changed_sku_codes": ["TV00029115"],
  "blocked_sku_codes": [],
  "review_required_sku_codes": ["TV00029115"],
  "downstream_impacts": [
    {"sku_code": "TV00029115", "next_modules": ["M06", "M04b", "M08"]}
  ],
  "metrics": {
    "comment_unit_count": 34438,
    "comment_evidence_atom_count": 20916,
    "topic_hint_count": 56000
  }
}
```

状态规则：

| 条件 | status |
| --- | --- |
| 全部 SKU 成功且无 warning | `completed` |
| 有 warning 或 review | `completed_with_warning` |
| 部分 SKU blocked | `partial_blocked` |
| seed/M02 缺失导致无法运行 | `blocked` |
| 写库失败 | `failed` |

### 10.3 API

在 `apps/api-server/app/api/core3_real_data.py` 增加：

| API | 用途 |
| --- | --- |
| `POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/run-m05-comment-evidence` | 手动运行 M05 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comment-quality-profile` | 查看 SKU 评论质量画像 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comment-evidence-atoms` | 查看句级评论证据 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comment-topic-hints` | 查看弱主题提示 |
| `GET /api/mvp/core3/v2/projects/{project_id}/comment-units/{comment_unit_id}/sources` | 查看评论单元来源 evidence |

### 10.4 API 边界

API 必须返回：

- 中文业务名称。
- 分页信息。
- 证据短编号或可钻取 ID。
- 弱提示标识。
- 服务隔离标识。
- 质量画像摘要。

API 不得返回：

- 用户任务最终结论。
- 目标客群最终结论。
- 价值战场最终结论。
- 竞品判断。
- 卖点激活最终分。
- 大段 JSON 作为高层展示字段。
- prompt、模型过程或 AI 话术。

### 10.5 API filters

`comment-evidence-atoms` 支持：

```text
primary_domain_hint
sentiment_hint
low_value_flag
usable_for_downstream
topic_code
limit
offset
```

`comment-topic-hints` 支持：

```text
topic_code
topic_group
polarity_hint
topic_hint_status
service_guardrail_flag
limit
offset
```

### 10.6 API 测试

必须覆盖：

- profile API 无数据时返回业务化 empty 状态。
- atom API 分页有效。
- topic API 明确 `is_weak_hint=true`。
- source API 可追溯 M02 evidence。
- API response 不包含 `task_code`、`target_group_code`、`battlefield_code`、`competitor` 等越界字段。

## 11. 测试任务

### 11.1 seed loader 测试

`test_m05_comment_topic_seed_loader.py`：

| 场景 | 期望 |
| --- | --- |
| seed 正常 | 加载 16 个首版 topic |
| 缺 `comment_topics` | blocked error |
| topic 缺 code/name/group | 校验失败 |
| keyword 索引 | 可通过“画质”“游戏”“安装”查到主题 |
| seed hash | 内容变化 hash 变化 |

### 11.2 评论单元测试

`test_m05_comment_unit_builder.py`：

| 场景 | 期望 |
| --- | --- |
| 同 SKU 同 comment_id 多行 | 生成一个 comment unit |
| comment_id 缺失但 text_hash 相同 | 生成一个 comment unit，置信度降级 |
| comment_id 和 hash 缺失但 source_row_id 存在 | fallback 单元，review |
| 多维度拆行 | `raw_dimension_paths` 合并 |
| 默认好评 | `low_value_flag=true` |
| 空文本 | `comment_unit_status='low_value'` |
| 情感空 | `sentiment_hint='unknown'` |
| 情感冲突 | `sentiment_hint='conflict'` |

### 11.3 link builder 测试

`test_m05_comment_unit_link_builder.py`：

| 场景 | 期望 |
| --- | --- |
| raw evidence | `link_role='raw_source'` |
| sentence evidence | `link_role='sentence_source'` |
| dimension evidence | `link_role='dimension_weak_label'` |
| quality evidence | `link_role='quality_flag'` |
| 同 evidence 重复输入 | 幂等去重 |
| API 分页 | 可按 unit 查来源 |

### 11.4 句级 atom 测试

`test_m05_sentence_atom_builder.py`：

| 场景 | 期望 |
| --- | --- |
| 有系统切句 | 优先 `system_split` |
| 有原始 segment | 可补充 `source_segment` |
| 无 sentence evidence | raw fallback 切句并 review |
| 同句 hash 重复 | 只生成一个 atom，source ids 合并 |
| 低价值句 | `usable_for_downstream=false` |
| 具体产品体验句 | `specificity_score` 高 |
| “很好满意” | `specificity_score` 低 |
| 维度为空但文本具体 | atom 保留且可用 |

### 11.5 弱域测试

`test_m05_domain_hint_service.py`：

| 输入 | 期望 |
| --- | --- |
| “画质清晰，看球不卡” | `product_experience` |
| “系统卡顿，广告多” | `product_risk` |
| “价格划算，优惠大” | `market_perception` |
| “安装师傅服务好” | `service_experience`，`service_only` |
| “物流很快，送货上门” | `logistics_installation` |
| “电视画质好，安装也快” | 产品为主，服务为次 |
| 空维度但文本具体 | 仍可判断弱域 |
| 维度产品但文本服务 | `domain_conflict_flag=true` |

### 11.6 情感测试

`test_m05_sentiment_hint_service.py`：

| 场景 | 期望 |
| --- | --- |
| raw 正面 + 正向词 | `positive` |
| raw 负面 + 负向词 | `negative` |
| raw 空 + 无情绪 | `unknown` |
| raw 空 + “卡顿严重” | `negative` |
| raw 正面 + “广告多卡顿” | `conflict` |
| 默认好评 | 情感降权，不形成强正向 |

### 11.7 主题提示测试

`test_m05_topic_hint_matcher.py`：

| 输入 | 期望 |
| --- | --- |
| “画质清晰” | `TOPIC_PICTURE_QUALITY` |
| “亮度高 HDR 效果好” | `TOPIC_BRIGHTNESS_HDR` |
| “暗场细节不错” | `TOPIC_DARK_SCENE_CONTRAST` |
| “看球不卡” | `TOPIC_SPORTS_WATCHING` |
| “游戏流畅” | `TOPIC_GAMING_SMOOTHNESS` |
| “护眼不刺眼” | `TOPIC_EYE_COMFORT` |
| “老人也会用” | `TOPIC_SENIOR_FRIENDLY` |
| “安装师傅服务好” | `TOPIC_INSTALLATION_SERVICE`，`service_guardrail_flag=true` |
| 低价值句 | 不生成 `matched` 强主题 |
| 未命中主题 | 不落 `TOPIC_UNKNOWN` |

### 11.8 质量画像测试

`test_m05_quality_profile_service.py`：

| 场景 | 期望 |
| --- | --- |
| 评论充足 | `sample_status='sufficient'` |
| 评论有限 | `sample_status='limited'` |
| 无评论 | `sample_status='unknown'`，`downstream_ready=false` |
| 低价值高占比 | warning |
| 服务安装高占比 | warning，不阻断 |
| 情感 unknown 高 | warning |
| 主题 unknown 高 | review |
| 85E7Q 1648 去重评论 | 不应低于 limited |

### 11.9 review policy 测试

`test_m05_review_policy.py`：

| 条件 | 期望 |
| --- | --- |
| `duplicate_text_rate > 0.65` | warning |
| `low_value_sentence_count / sentence_count > 0.40` | warning |
| `service_installation_share > 0.50` | warning |
| 85E7Q 去重数明显低于 1648 | review |
| seed 缺失 | blocked |
| M02 未完成 | blocked |
| evidence 追溯缺失 | blocked 或 review |

### 11.10 repository 测试

`test_m05_repositories.py`：

| 场景 | 期望 |
| --- | --- |
| bulk insert units | 成功写入 |
| 二次写同 result_hash | 幂等 |
| result hash 变化 | 旧记录 `is_current=false` |
| link 查询 | 可追溯 source evidence |
| atom filters | 弱域、情感、可用性过滤正确 |
| topic filters | topic、group、polarity 过滤正确 |
| profile 查询 | 只返回 current |

### 11.11 runner 测试

`test_m05_runner.py`：

| 场景 | 期望 |
| --- | --- |
| 正常 SKU | 输出 unit、link、atom、topic、profile |
| 输入 hash 未变 | 跳过重算 |
| `force=true` | 强制重算 |
| 部分 SKU blocked | `partial_blocked` |
| seed 缺失 | `blocked` |
| 返回 downstream impacts | 包含 M06 |

### 11.12 API 测试

`test_m05_api.py`：

| API | 期望 |
| --- | --- |
| run M05 | 返回 runner status |
| profile | 返回业务化摘要 |
| atoms | 支持分页和过滤 |
| topic hints | 返回弱提示标记 |
| sources | 返回 M02 evidence 来源 |
| 越界字段 | 不返回任务、客群、战场、竞品 |

### 11.13 越界测试

`test_m05_no_business_outputs.py` 必须验证：

- M05 不读取原始 `comment_data`。
- M05 不读取市场表、参数表、卖点表做业务判断。
- M05 不输出 `task_code`。
- M05 不输出 `target_group_code`。
- M05 不输出 `battlefield_code`。
- M05 不输出 `competitor_sku_code`。
- M05 不写 `core3_sku_claim_activation`。
- `TOPIC_INSTALLATION_SERVICE` 不能作为产品卖点高置信证据。
- 情感空值不能被当成 neutral。

### 11.14 85E7Q fixture 测试

`test_m05_85e7q_fixture.py`：

| 数据事实 | 验收 |
| --- | --- |
| 85E7Q 有 3621 行评论 | `raw_comment_row_count` 接近 3621 |
| 85E7Q 有 1648 个去重 comment_id | `comment_unit_count` 不应明显低于 1648 |
| 85E7Q 无结构化卖点 | M05 不失败，不伪造卖点 |
| 服务安装评论较多 | 服务/物流弱域隔离 |
| 画质/音质/价格/智能易用评论 | 拆成句级 atom 和弱主题 |
| 评论证据可用 | `downstream_ready=true` 或 warning 后 true |

## 12. 205/85E7Q 验收

### 12.1 全量样例验收

当前 205 样例约束：

| 指标 | 基线 | M05 验收 |
| --- | ---: | --- |
| 原始评论行 | 62426 | 全量运行时 `raw_comment_row_count` 汇总接近该数 |
| 不同 `comment_id` | 34438 | `comment_unit_count` 不应大幅低于该数 |
| 不同正文 hash | 13514 | `distinct_comment_text_count` 接近该数 |
| 不同 `comments_segments` | 20916 | 句级 atom 至少覆盖有效分段 |
| 空维度 | 15766 | 不丢弃，计入 `empty_dimension_count` |
| 正面情感 | 42560 | 进入情感分布，但默认好评降权 |
| 空情感 | 15766 | 计入 `unknown`，不当 neutral |

### 12.2 85E7Q 验收

85E7Q `model_code=TV00029115`：

| 数据域 | 基线 | M05 验收 |
| --- | ---: | --- |
| 评论行 | 3621 | 全部可追溯到 M02 `comment_raw` |
| 去重评论 ID | 1648 | 形成去重评论单元 |
| 结构化卖点 | 0 | 不影响 M05，不伪造卖点 |
| 服务安装评论 | 较多 | 进入服务/物流弱域，不用于产品卖点高置信 |
| 画质/音质/价格/智能易用 | 存在评论线索 | 形成句级 atom 和弱主题提示 |

85E7Q 的 profile 必须能回答：

1. 评论证据是否足够支撑 M06。
2. 产品体验和服务安装评论各占多少。
3. 画质、游戏、体育、价格、安装服务是否只是弱提示。
4. 哪些评论片段可以作为 M15 证据卡候选原句。

### 12.3 不达标处理

| 现象 | 处理 |
| --- | --- |
| 85E7Q `comment_unit_count` 明显低于 1648 | review，检查去重规则过严 |
| 85E7Q `downstream_ready=false` | review 或 blocked，说明原因 |
| 服务句进入产品卖点强证据 | 测试失败 |
| 空情感变 neutral | 测试失败 |
| 直接读取原始 `comment_data` | 测试失败 |
| M05 输出任务/客群/战场字段 | 测试失败 |

## 13. 完成标准

编码任务完成时必须满足：

1. `0011_core3_real_data_comment_evidence.py` 可升级、可回滚。
2. 5 张 M05 输出表字段、主键、唯一键、索引、JSONB 字段与详细设计一致。
3. M05 service 默认只读 M02 evidence 和 TV seed。
4. M05 不直接读取原始 `comment_data`。
5. M05 可构建 `core3_comment_unit`。
6. M05 可构建 `core3_comment_unit_evidence_link`。
7. M05 可构建 `core3_comment_evidence_atom`。
8. M05 可构建 `core3_comment_topic_hint`。
9. M05 可构建 `core3_comment_quality_profile`。
10. 评论行数、去重评论数、正文数、句级证据数可区分。
11. 任一 M05 atom 可回溯到 M02 evidence。
12. 空情感为 `unknown`，不当 neutral。
13. 默认好评、空文本、模板重复不形成强信号。
14. 服务/安装/物流评论不能增强产品卖点高置信。
15. topic hint 固定 `is_weak_hint=true`，不是业务结论。
16. 85E7Q 评论可形成可用句级证据和质量画像。
17. 输入 hash 未变时不重复写当前记录。
18. seed 变化时 topic hint hash 变化并登记 M06 重算范围。
19. warning/review/block 条件可落入 M16 所需字段。
20. API 不返回任务、客群、战场、竞品等越界字段。
21. 所有 M05 单元、集成、边界、越界、85E7Q fixture 测试通过。

建议测试命令：

```bash
cd apps/api-server && .venv/bin/pytest tests/core3_real_data/test_m05_*.py
```

如项目当前测试命令不同，以仓库实际配置为准，但必须能单独运行 M05 测试。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 直接按原始行统计评论 | 评论声量虚高 | 先建 comment unit，profile 同时展示 raw/unit/text/sentence |
| 多维度拆行被当成多条独立评论 | 下游误判主题声量 | `comment_unit_key` 合并，link 保留来源 |
| 情感空值当中立 | 情感分布失真 | schema 和测试固化 unknown |
| 默认好评形成强正向 | 产品体验被噪声污染 | 低价值规则和 topic 阻断 |
| 服务安装被当产品卖点 | 竞品理由不可信 | `service_guardrail_flag` 和越界测试 |
| 弱主题被下游当最终任务/战场 | 方法论越界 | API 和 schema 禁止输出最终业务字段 |
| seed 缺失后硬编码临时主题 | 口径不可评审 | seed loader blocked，不做临时补丁 |
| 评论量大导致查询慢 | API 和 runner 慢 | 分页读取、批量写入、必要索引 |
| link 表过大 | 存储增加 | 首版接受，换取证据追溯和分页 |
| 85E7Q 去重过严 | 演示 SKU 评论不可用 | 1648 去重 ID sanity check |

回滚方式：

1. Alembic downgrade 删除 M05 5 张输出表。
2. 移除 M05 API router 注册。
3. 移除 M05 runner 注册。
4. 不影响 M00-M04a 产物。
5. 不影响旧 `core3_mvp` 页面。

## 15. 下游依赖

| 下游模块 | 依赖 M05 的内容 |
| --- | --- |
| M06 | `core3_comment_evidence_atom`、`core3_comment_topic_hint`、`core3_comment_quality_profile` |
| M04b | 通过 M06 的 `claim_validation` 信号间接使用 M05，不直接消费 M05 topic |
| M08 | 使用 M06 汇总信号和 M05 质量画像约束评论贡献 |
| M09 | 通过 M06 的 `task_clue` 使用评论线索 |
| M10 | 通过 M06 的 `target_group_clue` 使用评论线索 |
| M11 | 通过 M06 的 `battlefield_support` 使用评论线索 |
| M15 | 可引用 M05 代表评论短句，但必须由 M06-M14 聚合结论支撑 |
| M16 | 使用 warning/review/block 字段生成复核和增量计划 |

M05 给 M06 的核心字段：

| 字段 | 下游用途 |
| --- | --- |
| `sentence_text` | 信号抽取文本 |
| `primary_domain_hint` | 选择信号类型 |
| `domain_hints` | 多域线索和服务隔离 |
| `sentiment_hint` | 正负向判断 |
| `specificity_score` | 过滤泛化评价 |
| `topic_code` | 主题线索 |
| `service_guardrail_flag` | 防止误用服务评论 |
| `source_evidence_ids` | 证据追溯 |

明确禁止：

```text
M05 topic hint -> M04b 最终卖点验证
M05 topic hint -> M09 最终用户任务
M05 topic hint -> M10 最终客群
M05 topic hint -> M11 最终价值战场
M05 topic hint -> M12/M13/M14 竞品评分
```

正确链路：

```text
M05 评论基础证据 -> M06 下游专用评论信号 -> M04b/M08/M09/M10/M11/M11.5 -> M12-M15
```

## 16. 编码子任务建议

如果正式编码继续按小任务执行，建议拆为：

| 子任务 | 内容 | 完成标准 |
| --- | --- | --- |
| M05-A | Alembic 迁移 | 5 表、索引、约束、回滚 |
| M05-B | schema 和枚举 | typed contracts、API schema、枚举 |
| M05-C | seed loader | 16 topic 校验、索引、hash |
| M05-D | input repository/service | 只读 M02 evidence、fingerprint |
| M05-E | comment unit + link | 去重单元、来源追溯 |
| M05-F | sentence atom | 句级证据、低价值、具体程度 |
| M05-G | domain + sentiment | 弱域、服务隔离、情感 unknown/conflict |
| M05-H | topic matcher | 弱主题、service guardrail、不落 unknown topic |
| M05-I | quality profile + review policy | SKU 质量画像、warning/review/block |
| M05-J | runner + API | 运行入口、查询 API、分页 |
| M05-K | tests + 85E7Q fixture | 单元、集成、越界、样例验收 |

每个子任务都应保持可测试，不建议在一个编码任务里一次性完成 M05-A 到 M05-K。

## 17. 下次任务

下一个开发任务文档：

```text
docs/core3_mvp/real_data_v2/development/M06_development_tasks.md
```

M06 需要基于 M05 的评论基础证据，按下游目标分别抽取：

- 卖点验证信号。
- 用户任务线索。
- 目标客群线索。
- 价值战场支撑。
- 痛点风险。
- 价格价值感。
- 服务信号。

M06 必须保持边界：评论只是信号，不直接形成最终任务、客群、战场或竞品结论。
