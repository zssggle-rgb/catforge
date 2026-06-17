# M06 评论下游信号抽取开发任务

## 1. 模块目标

M06 的开发目标是把 M05 的评论基础证据转换成七类下游专用评论信号，建立评论到 M04b、M08、M09、M10、M11、M11.5、M13、M15 之间的标准接口。

M06 不是“评论一次性分析并生成业务结论”。它只做信号抽取和聚合：

1. 从 M05 的去重评论单元、句级证据、弱主题和质量画像读取输入。
2. 对每条评论句抽取场景、动作、人群、对象、体验结果、约束、负向词、服务词和价格词。
3. 按七类信号分别抽取：卖点体验验证、用户任务线索、目标客群线索、价值战场支撑/削弱、痛点风险、价格价值感、服务保障。
4. 输出句级信号候选 `core3_comment_signal_candidate`。
5. 按 SKU + 信号类型 + 目标编码聚合为 `core3_comment_downstream_signal`。
6. 生成 SKU 级评论信号画像 `core3_sku_comment_signal_profile`。
7. 保留 M05/M02 evidence 追溯、去重分母、提及率、正负向率、置信度和复核标记。

M06 必须固化以下边界：

- 评论只能证明体验感知，不能证明硬规格。
- 评论任务线索不能单独生成最终用户任务。
- 评论客群线索不能单独生成最终目标客群。
- 评论战场支撑不能单独生成最终价值战场。
- 评论信号不能直接生成竞品候选、评分或核心三竞品。
- 服务、安装、物流、售后信号必须与产品体验信号隔离。
- 价格感知不能替代 M07/M13 的真实价格事实。
- M06 不直接读取原始 `comment_data`、市场原始表、参数原始表、卖点原始表。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M05 任务 | `docs/core3_mvp/real_data_v2/development/M05_development_tasks.md` |
| M06 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M06_comment_downstream_signal_requirements.md` |
| M06 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M06_comment_downstream_signal_design.md` |
| M05 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M05_comment_evidence_design.md` |
| M03 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| M04a 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M04a_base_claim_activation_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M05 已能输出 `core3_comment_unit`、`core3_comment_evidence_atom`、`core3_comment_topic_hint`、`core3_comment_quality_profile`。
- M05 profile 中有 `downstream_ready`、`comment_unit_count`、`usable_sentence_count`、低价值和服务占比等字段。
- M05 atom 中有 `sentence_text`、`comment_unit_id`、`specificity_score`、`sentiment_hint`、`domain_hints`、`primary_domain_hint`、`source_m05_evidence_ids`、`source_m02_evidence_ids`。
- M05 topic hint 中有 `topic_code`、`topic_group`、`service_guardrail_flag`、`mapped_claim_codes_snapshot`、`mapped_task_codes_snapshot`、`mapped_battlefield_codes_snapshot`。
- TV seed 中有 `standard_claims`、`user_tasks`、`target_groups`、`battlefields`、`comment_topics`。
- M03 和 M04a 作为可选辅助输入，不得成为 M06 必须运行前置，也不得产生反向依赖。

## 3. 本次范围

本次开发任务拆分覆盖 M06 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 3 张 M06 输出表 |
| schema | 新增 M06 runner、内部记录、API、复核、下游影响 schema |
| repository | 只读 M05，选读 M03/M04a，写 M06 输出 |
| seed loader | 加载标准卖点、用户任务、客群、战场、评论主题 |
| entity extractor | 抽取场景、动作、人群、对象、体验结果、约束、价格、服务、负向词 |
| signal extractor | 七类信号独立 extractor |
| aggregator | SKU 粒度聚合信号、提及率、正负向率、置信度 |
| profile builder | 生成 SKU 评论信号画像 |
| review policy | warning、review_required、blocked |
| runner/API | 运行入口和运营查询接口 |
| 测试 | 单元、集成、边界、越界、85E7Q fixture |
| 增量 | fingerprint、result_hash、is_current、下游影响登记 |

本次不做：

- 不实现 M04b 最终卖点激活。
- 不实现 M08 SKU 综合信号画像。
- 不实现 M09/M10/M11/M11.5 最终业务推导。
- 不实现 M12-M15 竞品推导和报告。
- 不实现前端页面。
- 不部署到 205。
- 不让 M06 API 直接服务高层报告结论。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/comment_downstream_signal_schemas.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_repositories.py
apps/api-server/app/services/core3_real_data/comment_signal_seed_loader.py
apps/api-server/app/services/core3_real_data/comment_signal_input_service.py
apps/api-server/app/services/core3_real_data/comment_entity_extractor.py
apps/api-server/app/services/core3_real_data/claim_validation_signal_extractor.py
apps/api-server/app/services/core3_real_data/task_cue_signal_extractor.py
apps/api-server/app/services/core3_real_data/target_group_cue_signal_extractor.py
apps/api-server/app/services/core3_real_data/battlefield_support_signal_extractor.py
apps/api-server/app/services/core3_real_data/pain_point_signal_extractor.py
apps/api-server/app/services/core3_real_data/price_perception_signal_extractor.py
apps/api-server/app/services/core3_real_data/service_signal_extractor.py
apps/api-server/app/services/core3_real_data/comment_signal_aggregator.py
apps/api-server/app/services/core3_real_data/sku_comment_signal_profile_builder.py
apps/api-server/app/services/core3_real_data/comment_signal_review_policy.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_service.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `comment_downstream_signal_schemas.py` | M06 内部 typed contracts |
| `comment_downstream_signal_repositories.py` | M06 输入读取和输出写入 |
| `comment_signal_seed_loader.py` | 加载并校验五类 seed 和内置风险/价格/服务字典 |
| `comment_signal_input_service.py` | 组装 M05/M03/M04a 输入和 fingerprint |
| `comment_entity_extractor.py` | 评论句实体、场景、动作、结果、服务、价格、风险词抽取 |
| `claim_validation_signal_extractor.py` | 卖点体验验证信号 |
| `task_cue_signal_extractor.py` | 用户任务线索 |
| `target_group_cue_signal_extractor.py` | 目标客群线索 |
| `battlefield_support_signal_extractor.py` | 价值战场支撑/削弱信号 |
| `pain_point_signal_extractor.py` | 痛点风险信号 |
| `price_perception_signal_extractor.py` | 价格价值感信号 |
| `service_signal_extractor.py` | 服务保障信号 |
| `comment_signal_aggregator.py` | candidate 到 downstream signal 聚合 |
| `sku_comment_signal_profile_builder.py` | SKU 评论信号画像 |
| `comment_signal_review_policy.py` | warning/review/block 规则 |
| `comment_downstream_signal_service.py` | M06 编排 service |
| `comment_downstream_signal_runner.py` | M06 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0012_core3_real_data_comment_downstream_signal.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0012_core3_real_data_comment_downstream_signal.py` | 新增 M06 3 张输出表 |
| `core3_real_data.py` schema | 导出 M06 API response/request |
| `core3_real_data.py` API | 增加 M06 运行和查询 API |
| `constants.py` | 补 M06 signal type、polarity、strength、policy 枚举 |
| `runner.py` | 注册 M06 runner，不改变已有模块语义 |
| `conftest.py` | 增加 M06 M05 输入 fixture、85E7Q 评论信号 fixture |

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m06_signal_seed_loader.py
apps/api-server/tests/core3_real_data/test_m06_input_service.py
apps/api-server/tests/core3_real_data/test_m06_entity_extractor.py
apps/api-server/tests/core3_real_data/test_m06_claim_validation_extractor.py
apps/api-server/tests/core3_real_data/test_m06_task_cue_extractor.py
apps/api-server/tests/core3_real_data/test_m06_target_group_cue_extractor.py
apps/api-server/tests/core3_real_data/test_m06_battlefield_support_extractor.py
apps/api-server/tests/core3_real_data/test_m06_pain_point_extractor.py
apps/api-server/tests/core3_real_data/test_m06_price_perception_extractor.py
apps/api-server/tests/core3_real_data/test_m06_service_signal_extractor.py
apps/api-server/tests/core3_real_data/test_m06_signal_aggregator.py
apps/api-server/tests/core3_real_data/test_m06_signal_profile_builder.py
apps/api-server/tests/core3_real_data/test_m06_review_policy.py
apps/api-server/tests/core3_real_data/test_m06_repositories.py
apps/api-server/tests/core3_real_data/test_m06_runner.py
apps/api-server/tests/core3_real_data/test_m06_api.py
apps/api-server/tests/core3_real_data/test_m06_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m06_85e7q_fixture.py
```

### 4.4 只读依赖文件

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_real_data/comment_evidence_repositories.py
apps/api-server/app/services/core3_real_data/comment_evidence_schemas.py
apps/api-server/app/services/core3_real_data/param_extraction_repositories.py
apps/api-server/app/services/core3_real_data/param_extraction_schemas.py
apps/api-server/app/services/core3_real_data/base_claim_activation_repositories.py
apps/api-server/app/services/core3_real_data/base_claim_activation_schemas.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
```

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

- M05 输出表结构。
- M03 参数抽取逻辑。
- M04a 基础卖点激活逻辑。
- M04b 最终卖点增强逻辑。
- M08-M16 结果表。
- 旧 `core3_mvp` 服务和页面。
- 原始四表结构。
- 前端高层报告页面。
- 205 部署配置。

不允许引入的行为：

- 直接读取原始 `comment_data`。
- 直接读取 `week_sales_data` 做价格判断。
- 直接读取原始 `attribute_data` 反推参数。
- 直接读取原始 `selling_points_data` 反推卖点。
- 输出最终任务分、客群分、战场分或竞品选择。
- 用评论证明亮度、分区数、端口数、芯片、内存、认证等硬规格。
- 用 `service_signal` 增强产品卖点。
- 用 `price_perception` 替代真实价格。
- 在测试中调用外部 LLM。
- 用 M06 API 给前端直接拼高层业务结论。

## 6. 数据库迁移任务

### 6.1 迁移文件

新增迁移：

```text
apps/api-server/alembic/versions/0012_core3_real_data_comment_downstream_signal.py
```

迁移只新增 M06 输出表，不修改 M05/M03/M04a 表。

### 6.2 新增表

| 表 | 粒度 | 说明 |
| --- | --- | --- |
| `core3_comment_signal_candidate` | 评论句 + 信号类型 + 目标编码 | 句级信号候选和证据明细 |
| `core3_comment_downstream_signal` | SKU + 信号类型 + 目标编码 + 极性 | 下游可消费的聚合评论信号 |
| `core3_sku_comment_signal_profile` | SKU + 批次 | SKU 评论信号画像 |

### 6.3 通用字段

3 张表均应包含：

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
| `rule_version` | 非空，建议首版 `m06_comment_downstream_signal_v1` |
| `asset_version` | 非空，由 seed loader 生成 |
| `input_fingerprint` | 非空 |
| `result_hash` | 非空 |
| `is_current` | 默认 true |
| `processing_status` | `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_status` | `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| JSON 字段 | PostgreSQL 使用 `JSONB` |
| 时间字段 | 使用 timezone aware |

### 6.4 `core3_comment_signal_candidate`

#### 6.4.1 字段

```text
signal_candidate_id
signal_candidate_key
comment_unit_id
comment_evidence_id
comment_text_hash
sentence_hash
sentence_text
signal_type
target_code_hint
target_name_hint
target_group_hint
polarity
signal_strength
signal_strength_level
confidence
confidence_level
specificity_score
sentiment_hint
domain_hints
primary_domain_hint
topic_hints_json
matched_entities_json
matched_rules_json
cue_basis
hard_spec_policy
service_guardrail_flag
eligible_for_product_claim
eligible_for_service_claim
eligible_for_task
eligible_for_group
eligible_for_battlefield
low_value_flag
duplicate_group_id
quality_flags
blocked_reasons
source_m05_evidence_ids
source_m02_evidence_ids
optional_param_context_json
optional_claim_context_json
```

#### 6.4.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `signal_candidate_id` |
| 唯一键 | `project_id, category_code, batch_id, signal_candidate_key, rule_version, asset_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, signal_type` |
| 索引 | `sku_code, target_code_hint` |
| 索引 | `comment_evidence_id` |
| 索引 | `comment_unit_id` |
| 索引 | `signal_strength_level` |
| 索引 | `polarity` |
| 索引 | `review_required` |
| GIN | `topic_hints_json`、`matched_entities_json`、`matched_rules_json`、`quality_flags`、`blocked_reasons` |

#### 6.4.3 约束

| 字段 | 约束 |
| --- | --- |
| `signal_type` | 七类固定值 |
| `target_code_hint` | 按 signal type 使用正确前缀 |
| `polarity` | `support`、`weaken`、`mixed`、`neutral`、`unknown` |
| `signal_strength` | 0-1 |
| `signal_strength_level` | `strong`、`medium`、`weak`、`blocked` |
| `confidence` | 0-1 |
| `cue_basis` | M06 枚举 |
| `hard_spec_policy` | M06 枚举 |
| `sentence_text` | 非空 |
| `source_m05_evidence_ids` | 非空 JSON 数组 |

### 6.5 `core3_comment_downstream_signal`

#### 6.5.1 字段

```text
signal_id
signal_key
signal_type
target_code_hint
target_name_hint
target_group_hint
polarity
mention_count
sentence_count
valid_comment_unit_count
usable_sentence_count
mention_rate
sentence_mention_rate
positive_count
negative_count
neutral_count
positive_rate
negative_rate
mixed_flag
signal_score
signal_level
specificity_avg
evidence_quality_score
sample_status
comment_quality_flags
representative_phrases
top_candidate_ids
evidence_ids
service_guardrail_flag
hard_spec_policy
downstream_usage_policy_json
quality_summary
confidence
confidence_level
```

#### 6.5.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `signal_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, signal_type, target_code_hint, polarity, rule_version, asset_version` |
| 索引 | `sku_code, signal_type` |
| 索引 | `signal_type, target_code_hint` |
| 索引 | `signal_level` |
| 索引 | `confidence_level` |
| 索引 | `service_guardrail_flag` |
| 索引 | `review_required` |
| GIN | `comment_quality_flags`、`representative_phrases`、`evidence_ids`、`downstream_usage_policy_json` |

#### 6.5.3 约束

| 字段 | 约束 |
| --- | --- |
| `mention_count` | >= 0，按去重 `comment_unit_id` 计算 |
| `sentence_count` | >= 0 |
| `valid_comment_unit_count` | >= 0，来自 M05 分母 |
| `mention_rate` | 0-1 |
| `positive_rate` | 0-1 |
| `negative_rate` | 0-1 |
| `signal_score` | 0-1 |
| `signal_level` | `strong`、`medium`、`weak`、`blocked` |
| `representative_phrases` | 最多保留配置上限，避免大字段 |
| `downstream_usage_policy_json` | 必须描述 M04b/M09/M10/M11/M13 允许范围 |

### 6.6 `core3_sku_comment_signal_profile`

#### 6.6.1 字段

```text
sku_comment_signal_profile_id
profile_key
comment_signal_summary_json
claim_validation_summary_json
task_cue_summary_json
target_group_cue_summary_json
battlefield_support_summary_json
pain_risk_summary_json
price_perception_summary_json
service_signal_summary_json
strong_signal_count
medium_signal_count
weak_signal_count
blocked_signal_count
claim_validation_ready
task_cue_ready
target_group_cue_ready
battlefield_support_ready
comment_signal_confidence
confidence_level
quality_flags
review_issue_summary_json
evidence_ids
```

#### 6.6.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `sku_comment_signal_profile_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, rule_version, asset_version` |
| 索引 | `sku_code` |
| 索引 | `comment_signal_confidence` |
| 索引 | `claim_validation_ready` |
| 索引 | `task_cue_ready` |
| 索引 | `battlefield_support_ready` |
| 索引 | `review_required` |
| GIN | `comment_signal_summary_json`、`quality_flags`、`review_issue_summary_json`、`evidence_ids` |

### 6.7 迁移回滚

`downgrade` 按依赖反向删除：

1. `core3_sku_comment_signal_profile`
2. `core3_comment_downstream_signal`
3. `core3_comment_signal_candidate`

回滚不得删除 M05/M03/M04a 产物。

## 7. model/schema 任务

### 7.1 内部 schema

在 `comment_downstream_signal_schemas.py` 中定义：

```text
M06RunRequest
M06RunResult
M06SkuInputBundle
M06SignalSeedBundle
M06CommentAtomInput
M06TopicHintInput
M06QualityProfileInput
M06OptionalParamContext
M06OptionalClaimContext
CommentEntityExtraction
SignalExtractionContext
CommentSignalCandidateRecord
CommentDownstreamSignalRecord
SkuCommentSignalProfileRecord
SignalTargetDefinition
SignalExtractorResult
CommentSignalReviewIssue
M06DownstreamImpact
```

### 7.2 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 中导出：

```text
M06RunResponse
CommentSignalCandidateResponse
CommentSignalCandidateDetailResponse
CommentSignalCandidateListResponse
CommentDownstreamSignalResponse
CommentDownstreamSignalListResponse
SkuCommentSignalProfileResponse
CommentSignalEvidenceTraceResponse
```

API response 要业务化，不要把内部字段裸给高层页面。

| 内部字段 | API 展示字段 |
| --- | --- |
| `signal_type='claim_validation'` | `卖点体验验证` |
| `signal_type='task_cue'` | `用户任务线索` |
| `signal_type='battlefield_support'` | `战场体验支撑` |
| `hard_spec_policy='experience_only'` | `仅证明体验感知` |
| `hard_spec_policy='market_fact_required'` | `需要价格事实复核` |
| `service_guardrail_flag=true` | `仅可用于服务保障` |
| `polarity='weaken'` | `削弱证据` |

### 7.3 枚举和常量

如 `constants.py` 尚未包含，需要补：

```text
M06_RULE_VERSION = "m06_comment_downstream_signal_v1"
COMMENT_SIGNAL_TYPE
COMMENT_SIGNAL_POLARITY
COMMENT_SIGNAL_STRENGTH_LEVEL
COMMENT_SIGNAL_CUE_BASIS
COMMENT_HARD_SPEC_POLICY
COMMENT_DOWNSTREAM_MODULE
COMMENT_SIGNAL_REVIEW_REASON_CODE
COMMENT_SIGNAL_TARGET_PREFIX
```

`COMMENT_SIGNAL_TYPE` 固定：

```text
claim_validation
task_cue
target_group_cue
battlefield_support
pain_point
price_perception
service_signal
```

### 7.4 目标编码前缀校验

schema 或 service 必须校验：

| `signal_type` | `target_code_hint` 前缀 |
| --- | --- |
| `claim_validation` | `CLAIM_` |
| `task_cue` | `TASK_` |
| `target_group_cue` | `TG_` |
| `battlefield_support` | `BF_` |
| `pain_point` | `RISK_` |
| `price_perception` | `PRICE_` |
| `service_signal` | `SERVICE_` |

允许服务型卖点 `CLAIM_INSTALLATION_SERVICE_ASSURANCE` 进入 `claim_validation`，但必须满足：

- `service_guardrail_flag=true`
- `eligible_for_product_claim=false`
- `eligible_for_service_claim=true`
- M04b 不得把它用于产品卖点增强。

### 7.5 schema 校验规则

| 对象 | 校验 |
| --- | --- |
| `M06RunRequest` | `project_id/category_code/batch_id` 非空，`signal_types` 只能是七类枚举 |
| `M06SkuInputBundle` | M05 profile 存在，atom 可为空但要写空 profile |
| `CommentEntityExtraction` | 每个实体列表去重，字段都允许空数组 |
| `CommentSignalCandidateRecord` | `comment_evidence_id`、`signal_type`、`target_code_hint`、`sentence_text` 非空 |
| `CommentDownstreamSignalRecord` | 分母、提及率、正负向率一致 |
| `SkuCommentSignalProfileRecord` | 七类摘要 JSON 必须都有 key，缺失则为空摘要 |

### 7.6 序列化要求

- JSONB 字段使用 `dict` 或 `list[dict]`。
- `sentence_text` 和 `representative_phrases` 允许保留原句，但 API 必须分页和限制长度。
- 分数输出保留 2-4 位即可。
- API 不输出大段内部 JSON 给高层展示页；只给运营接口和证据钻取接口使用。

## 8. repository 任务

### 8.1 Repository 文件

新增：

```text
apps/api-server/app/services/core3_real_data/comment_downstream_signal_repositories.py
```

### 8.2 Repository 类

```text
M06CommentInputRepository
M06OptionalContextRepository
CommentSignalCandidateRepository
CommentDownstreamSignalRepository
SkuCommentSignalProfileRepository
CommentDownstreamSignalReadRepository
```

### 8.3 `M06CommentInputRepository`

只读 M05 输出。

方法：

| 方法 | 说明 |
| --- | --- |
| `assert_m05_completed(project_id, category_code, batch_id)` | 检查 M05 是否完成 |
| `list_ready_sku_codes(project_id, category_code, batch_id, sku_scope)` | 读取 `downstream_ready=true` SKU |
| `get_comment_quality_profile(project_id, category_code, batch_id, sku_code)` | 读取 M05 profile |
| `list_usable_comment_atoms(project_id, category_code, batch_id, sku_code, limit, offset)` | 分页读取可用句级证据 |
| `list_topic_hints_for_atoms(comment_evidence_ids)` | 批量读取 topic hints |
| `get_comment_unit_denominators(project_id, category_code, batch_id, sku_code)` | 读取去重分母 |
| `get_m05_input_hashes(project_id, category_code, batch_id, sku_code)` | 读取 M05 result hashes |

限制：

- 不读取原始 `comment_data`。
- 不读取 M02 原始 evidence 做二次清洗。
- 不在 repository 中做信号业务判断。

### 8.4 `M06OptionalContextRepository`

只读 M03/M04a 当前版本。

方法：

| 方法 | 说明 |
| --- | --- |
| `get_sku_param_profile(project_id, category_code, batch_id, sku_code)` | 可选读取 M03 参数画像 |
| `list_claim_activation_base(project_id, category_code, batch_id, sku_code)` | 可选读取 M04a 基础卖点 |
| `get_optional_context_hashes(project_id, category_code, batch_id, sku_code)` | 计算 fingerprint 使用 |

限制：

- M03/M04a 缺失时 M06 仍可运行。
- 只用于冲突标记和 claim 上下文，不生成硬规格结论。

### 8.5 `CommentSignalCandidateRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `get_current_by_fingerprint(project_id, category_code, batch_id, sku_code, input_fingerprint)` | 判断是否可跳过 |
| `mark_previous_inactive(project_id, category_code, batch_id, sku_code, rule_version)` | 将旧版本置为非当前 |
| `bulk_upsert_candidates(records)` | 批量写句级 candidate |
| `list_current_candidates(project_id, category_code, batch_id, sku_code, filters, limit, offset)` | 查询 candidate |
| `list_candidates_for_signal(signal_id, limit, offset)` | API 查聚合信号明细 |
| `count_by_signal_type(project_id, category_code, batch_id, sku_code)` | profile 聚合 |

### 8.6 `CommentDownstreamSignalRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_signals(records)` | 批量写聚合 signal |
| `list_current_signals(project_id, category_code, batch_id, sku_code, filters)` | 下游读取 |
| `list_by_signal_type(project_id, category_code, batch_id, sku_code, signal_type)` | M04b/M09/M10/M11 定向消费 |
| `get_signal(signal_id)` | API 查单条 |
| `mark_previous_inactive(...)` | 版本切换 |

### 8.7 `SkuCommentSignalProfileRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `upsert_profile(record)` | 写 SKU 评论信号画像 |
| `get_current_profile(project_id, category_code, batch_id, sku_code)` | M08/API 读取 |
| `list_profiles(project_id, category_code, batch_id, filters, limit, offset)` | 运营查看 |
| `list_review_required_profiles(project_id, category_code, batch_id)` | M16 复核入口 |

### 8.8 `CommentDownstreamSignalReadRepository`

用于 API 聚合查询，不承载业务计算。

方法：

| 方法 | 说明 |
| --- | --- |
| `get_comment_signal_profile_response(...)` | 返回业务化 SKU signal profile |
| `list_comment_signals_response(...)` | 返回聚合 signals |
| `list_signal_candidates_response(...)` | 返回候选明细 |
| `get_candidate_detail_response(...)` | 返回单条候选证据追溯 |

### 8.9 Repository 测试要求

必须覆盖：

- 只读取 M05/M03/M04a，不读取原始表。
- candidate 批量写入幂等。
- signal 聚合版本切换正确。
- profile 只返回 current。
- 按 `signal_type` 查询只返回对应信号。
- API 分页不会一次返回所有 candidate。
- `mention_rate` 分母来自 M05 去重评论单元。

## 9. service 任务

### 9.1 `CommentSignalSeedLoader`

职责：

1. 读取 TV seed 的 `standard_claims`、`user_tasks`、`target_groups`、`battlefields`、`comment_topics`。
2. 构建 topic -> claim/task/group/battlefield 的映射。
3. 构建 keyword -> target 的映射。
4. 校验 M06 必须覆盖的目标字典。
5. 加载 MVP 内置风险、价格、服务字典。
6. 生成 `asset_version` 和 seed content hash。

必须校验的 seed：

| seed | 必须包含 |
| --- | --- |
| `standard_claims` | 产品体验和服务卖点目标 |
| `user_tasks` | M06 需求列出的 10 类任务 |
| `target_groups` | M06 需求列出的 9 类客群 |
| `battlefields` | M06 需求列出的 10 类战场 |
| `comment_topics` | M05 主题和映射快照 |

内置字典首版必须覆盖：

```text
RISK_PICTURE_NEGATIVE
RISK_MOTION_LAG
RISK_SYSTEM_ADS_LAG
RISK_AUDIO_NEGATIVE
RISK_EYE_DISCOMFORT
RISK_SERVICE_DELIVERY
RISK_DURABILITY_QUALITY
RISK_PRICE_OVERPAY
PRICE_VALUE_POSITIVE
PRICE_VALUE_NEGATIVE
PRICE_PROMOTION_SENSITIVE
PRICE_BIG_SCREEN_VALUE
PRICE_DROP_RISK
SERVICE_INSTALL_POSITIVE
SERVICE_DELIVERY_POSITIVE
SERVICE_SUPPORT_POSITIVE
SERVICE_INSTALL_NEGATIVE
SERVICE_DELIVERY_NEGATIVE
SERVICE_SUPPORT_NEGATIVE
```

seed 缺失时：

- runner 返回 `blocked`。
- 不使用临时硬编码代替 seed。
- 不生成部分目标后假装成功。

### 9.2 `CommentSignalInputService`

职责：

1. 校验 M05 已完成。
2. 读取 `downstream_ready=true` 的 M05 profile。
3. 分页读取 M05 可用句级 atom。
4. 关联 M05 topic hints。
5. 读取 M05 comment unit 分母。
6. 可选读取 M03 参数画像和 M04a 基础卖点激活。
7. 计算 SKU + signal types 级 `input_fingerprint`。
8. 识别 blocked、empty profile、可降级场景。

输入处理策略：

| 场景 | 处理 |
| --- | --- |
| M05 未完成 | M06 blocked |
| M05 profile 缺失 | 当前 SKU blocked |
| M05 `downstream_ready=false` | 当前 SKU blocked |
| 可用 atom 为空 | 写空 profile，`comment_signal_confidence=0` |
| M05 topic hint 缺失 | 可运行，降低置信度 |
| M03 缺失 | 可运行，缺少参数冲突校验 |
| M04a 缺失 | 可运行，缺少基础卖点上下文 |
| M05 服务占比高 | 可运行，增加服务隔离 warning |

### 9.3 `CommentEntityExtractor`

职责：

1. 从 `sentence_text` 抽取结构化实体。
2. 结合 M05 `domain_hints`、`topic_hints_json` 和 seed 关键词。
3. 输出统一 `matched_entities_json`。
4. 保留命中词和规则来源。

实体类别：

| 类别 | 字段 | 示例 |
| --- | --- | --- |
| 场景 | `scenarios` | 客厅、卧室、白天、晚上、装修、看球、电影、游戏 |
| 动作 | `actions` | 看球、追剧、打游戏、投屏、语音控制、安装、配送 |
| 人群 | `people` | 家人、父母、老人、孩子、全家 |
| 对象 | `objects` | PS5、Switch、球赛、电影、机顶盒 |
| 体验结果 | `experience_results` | 清晰、流畅、震撼、方便、护眼、划算 |
| 约束条件 | `constraints` | 价格、空间、光线、操作复杂、广告、售后 |
| 负向词 | `negative_terms` | 卡顿、拖影、刺眼、故障、贵、不值 |
| 服务词 | `service_terms` | 安装、师傅、配送、客服、售后 |
| 价格词 | `price_terms` | 性价比、优惠、贵、划算、降价 |

首版规则实现：

- 使用 seed keywords/aliases。
- 使用固定中文词典。
- 不调用外部 LLM。
- 输出空数组而不是 null。
- 保留 `matched_terms` 供证据解释。

### 9.4 七类信号 extractor 通用接口

每个 extractor 使用同一接口：

```text
extract(context: SignalExtractionContext) -> list[CommentSignalCandidateRecord]
```

`SignalExtractionContext` 包含：

- M05 atom。
- M05 topic hints。
- M05 profile。
- entity extraction。
- seed bundle。
- optional M03 context。
- optional M04a context。
- rule version。

每个 extractor 必须：

1. 只处理自己的 `signal_type`。
2. 只输出合法 `target_code_hint` 前缀。
3. 计算 `signal_strength`、`confidence`、`polarity`、`cue_basis`。
4. 设置 eligibility flags。
5. 设置 hard spec policy。
6. 设置 service guardrail。
7. 保留 source M05/M02 evidence。
8. 不写下游最终结论字段。

### 9.5 `ClaimValidationSignalExtractor`

目标：生成 `claim_validation`，供 M04b 消费。

输入目标：

- seed `standard_claims`
- M05 topic hints
- 可选 M04a 基础卖点
- 可选 M03 参数画像

抽取规则：

| 评论表达 | 可生成信号 | 禁止事项 |
| --- | --- | --- |
| 画质清晰、色彩好 | 支持画质体验类 claim | 不证明亮度、色域具体值 |
| 暗场细节好 | 支持控光体验 | 不证明分区数 |
| 看球不卡 | 支持运动流畅体验 | 不证明原生刷新率 |
| 游戏流畅、接主机方便 | 支持游戏体验和连接体验 | 不证明 HDMI 2.1 端口数 |
| 语音方便、老人会用 | 支持智能易用体验 | 不证明芯片/内存 |
| 安装快、师傅好 | 只可进入服务 claim 或 service_signal | 不增强产品 claim |

阻断规则：

| 条件 | 阻断原因 |
| --- | --- |
| 服务句目标是产品 claim | `service_to_product_claim_blocked` |
| 只有评论证明硬规格 | `hard_spec_not_proven` |
| 低价值评论 | `low_value_comment` |
| claim 不在 seed | `unknown_claim_code` |

输出要求：

- 产品类 claim：`hard_spec_policy='experience_only'`。
- 服务类 claim：`service_guardrail_flag=true`、`eligible_for_product_claim=false`。
- 技术型 claim 只能作为体验验证候选，M04b 必须结合 M04a。
- 85E7Q 无结构化卖点时，不能补造宣传证据。

### 9.6 `TaskCueSignalExtractor`

目标：生成 `task_cue`，供 M09 使用。

目标来自 seed `user_tasks`。

强信号最低条件：

- 至少满足“场景、动作、人群、对象、结果、约束”中的两类。
- 句子非低价值。
- 目标 task 来自 seed。
- 不只是单个 topic 词。

任务目标：

```text
TASK_LIVING_ROOM_CINEMA
TASK_PREMIUM_PICTURE_AV
TASK_GAMING_ENTERTAINMENT
TASK_SPORTS_WATCHING
TASK_LARGE_SCREEN_REPLACEMENT
TASK_CHILD_EYE_CARE
TASK_SENIOR_EASY_USE
TASK_VALUE_PURCHASE
TASK_NEW_HOME_DECORATION
TASK_BEDROOM_SECOND_TV
```

规则示例：

| 评论 | 输出 |
| --- | --- |
| “看球很流畅” | `TASK_SPORTS_WATCHING` |
| “接 PS5 很方便” | `TASK_GAMING_ENTERTAINMENT` |
| “给爸妈买的，语音操作简单” | `TASK_SENIOR_EASY_USE` |
| “这个价买 85 吋很值” | `TASK_VALUE_PURCHASE` |
| “新家装修挂墙正合适” | `TASK_NEW_HOME_DECORATION` |

输出约束：

- `task_cue` 只是评论线索。
- M09 必须结合参数、卖点、市场和 SKU 画像。
- 单个主题词命中最高只能是 weak。

### 9.7 `TargetGroupCueSignalExtractor`

目标：生成 `target_group_cue`，供 M10 使用。

目标来自 seed `target_groups`。

客群目标：

```text
TG_FAMILY_UPGRADE
TG_AV_QUALITY_SEEKER
TG_GAMER
TG_SPORTS_FAN
TG_SENIOR_FAMILY
TG_CHILD_FAMILY
TG_VALUE_BUYER
TG_NEW_HOME_DECORATOR
TG_BEDROOM_SECOND_TV
```

`cue_basis` 规则：

| cue_basis | 条件 | 置信度 |
| --- | --- | --- |
| `explicit_people` | 明确人群词，例如老人、孩子、父母 | 最高 |
| `purchase_motivation` | 给父母买、给新家买等动机 | 高 |
| `scenario_inference` | 客厅、卧室、装修等场景推断 | 中 |
| `topic_mapping` | 仅主题映射 | 低 |

输出约束：

- 客群线索不能单独生成高置信客群结论。
- 只有场景推断时，最高不超过 medium。
- 只有 topic 映射时，最高不超过 weak。

### 9.8 `BattlefieldSupportSignalExtractor`

目标：生成 `battlefield_support`，供 M11/M13 使用。

目标来自 seed `battlefields`。

战场目标：

```text
BF_PREMIUM_PICTURE
BF_FAMILY_VIEWING_UPGRADE
BF_GAMING_SPORTS
BF_LARGE_SCREEN_VALUE
BF_FAMILY_EYE_CARE
BF_SENIOR_EASE_OF_USE
BF_SMART_SYSTEM_EXPERIENCE
BF_CINEMA_AUDIO_IMMERSION
BF_DESIGN_HOME_FIT
BF_SERVICE_ASSURANCE
```

规则：

| 评论 | 输出 |
| --- | --- |
| “画质清晰，暗场也好” | 支撑 `BF_PREMIUM_PICTURE` |
| “看球不卡，游戏也流畅” | 支撑 `BF_GAMING_SPORTS` |
| “价格划算，大屏值” | 支撑 `BF_LARGE_SCREEN_VALUE` |
| “老人语音就会用” | 支撑 `BF_SENIOR_EASE_OF_USE` |
| “系统广告多，还卡” | 削弱 `BF_SMART_SYSTEM_EXPERIENCE` |
| “安装师傅专业” | 支撑 `BF_SERVICE_ASSURANCE` |

服务隔离：

- 服务类评论只能支撑 `BF_SERVICE_ASSURANCE`。
- 在 `TASK_NEW_HOME_DECORATION` 相关上下文中可作为服务侧辅助。
- 不得支撑高端画质、游戏体育、家庭护眼等产品战场。

### 9.9 `PainPointSignalExtractor`

目标：生成 `pain_point`，供 M08/M11/M13 使用。

风险目标：

```text
RISK_PICTURE_NEGATIVE
RISK_MOTION_LAG
RISK_SYSTEM_ADS_LAG
RISK_AUDIO_NEGATIVE
RISK_EYE_DISCOMFORT
RISK_SERVICE_DELIVERY
RISK_DURABILITY_QUALITY
RISK_PRICE_OVERPAY
```

严重度：

| `risk_severity` | 条件 |
| --- | --- |
| `low` | 单句弱负向或情感不明确 |
| `medium` | 明确负向体验，具体程度达标 |
| `high` | 多个去重评论单元集中负向，或涉及核心体验 |

严重度公式：

```text
risk_severity_score =
  0.35 * negative_term_strength
+ 0.25 * specificity_score
+ 0.20 * core_experience_weight
+ 0.20 * repeated_unit_concentration
```

`repeated_unit_concentration` 必须按去重评论单元计算，不按原始行数。

### 9.10 `PricePerceptionSignalExtractor`

目标：生成 `price_perception`，供 M09/M13 使用。

价格感知目标：

```text
PRICE_VALUE_POSITIVE
PRICE_VALUE_NEGATIVE
PRICE_PROMOTION_SENSITIVE
PRICE_BIG_SCREEN_VALUE
PRICE_DROP_RISK
```

规则：

| 评论 | 输出 |
| --- | --- |
| “性价比高，很划算” | `PRICE_VALUE_POSITIVE` |
| “太贵了，不值” | `PRICE_VALUE_NEGATIVE` |
| “活动优惠很大” | `PRICE_PROMOTION_SENSITIVE` |
| “85 吋这个价很值” | `PRICE_BIG_SCREEN_VALUE` |
| “刚买就降价” | `PRICE_DROP_RISK` |

输出约束：

- `hard_spec_policy='market_fact_required'`。
- 不读取真实价格。
- M13 必须用 M07 价格、价格带、销量复核。

### 9.11 `ServiceSignalExtractor`

目标：生成 `service_signal`，供 M10/M11/M15 使用。

服务目标：

```text
SERVICE_INSTALL_POSITIVE
SERVICE_DELIVERY_POSITIVE
SERVICE_SUPPORT_POSITIVE
SERVICE_INSTALL_NEGATIVE
SERVICE_DELIVERY_NEGATIVE
SERVICE_SUPPORT_NEGATIVE
```

输出要求：

- `service_guardrail_flag=true`
- `eligible_for_product_claim=false`
- `eligible_for_service_claim=true`
- 可支撑 `BF_SERVICE_ASSURANCE`
- 可作为 M15 服务证据展示
- 不增强画质、游戏、护眼等产品卖点

### 9.12 `CommentSignalAggregator`

职责：

1. 按 SKU + `signal_type` + `target_code_hint` + `polarity` 聚合 candidates。
2. 计算去重 `mention_count`。
3. 计算 `sentence_count`。
4. 使用 M05 `valid_comment_unit_count` 和 `usable_sentence_count` 作为分母。
5. 计算正负向率、signal score、confidence、signal level。
6. 选择代表短句和 top candidate ids。
7. 生成 downstream usage policy。

分母规则：

```text
mention_count = count(distinct comment_unit_id)
mention_rate = mention_count / max(valid_comment_unit_count, 1)
sentence_mention_rate = sentence_count / max(usable_sentence_count, 1)
positive_rate = positive_count / max(mention_count, 1)
negative_rate = negative_count / max(mention_count, 1)
```

聚合分数：

```text
signal_score =
  0.35 * mention_rate_score
+ 0.25 * positive_or_negative_rate
+ 0.20 * specificity_avg
+ 0.20 * evidence_quality_score
```

`mention_rate_score` 使用平滑：

```text
mention_rate_score = min(1, log(1 + mention_count) / log(1 + min(valid_comment_unit_count, 500)))
```

强信号最低条件：

- `mention_count >= 5`，或重点目标 `mention_count >= 3` 且具体程度高。
- strong/medium candidate 占多数。
- 非低价值和非高度重复。
- 目标编码合法。
- 服务/产品域没有冲突。

### 9.13 `SkuCommentSignalProfileBuilder`

职责：

1. 按七类信号生成摘要 JSON。
2. 统计 strong/medium/weak/blocked 数量。
3. 记录主要正向支撑、负向风险和服务占比。
4. 记录样本不足、低价值、unknown、服务占比高等质量问题。
5. 生成 M08 可消费的 SKU 评论信号画像。

每类摘要必须存在，即使为空：

```text
claim_validation_summary_json
task_cue_summary_json
target_group_cue_summary_json
battlefield_support_summary_json
pain_risk_summary_json
price_perception_summary_json
service_signal_summary_json
```

### 9.14 `CommentSignalReviewPolicy`

warning 条件：

| 条件 | warning |
| --- | --- |
| `unknown_signal_rate > 0.35` | 高频评论无法映射到信号 |
| `service_signal_share > 0.50` | 服务信号占比过高 |
| `low_value_candidate_rate > 0.20` | 低价值候选过多 |
| `mixed_polarity_rate > 0.25` | 同一目标正负混合明显 |
| `claim_validation_count=0` 且 M04a 有体验型基础卖点 | 评论无法验证基础卖点 |
| `task_cue_count=0` 且评论样本充足 | 任务线索抽取可能过严 |
| `price_perception` 强但没有市场事实 | 提醒 M13 复核 |

review 条件：

| 条件 | 处理 |
| --- | --- |
| 服务信号误入产品 claim_validation | 必须复核 |
| 低价值评论被判为 strong signal | 必须复核 |
| 同一句评论命中多个关键目标且分数接近 | 进入复核 |
| 评论信号与 M03 参数明显冲突 | 进入复核 |
| 评论信号与 M04a 基础卖点冲突 | 进入复核 |
| 重点 SKU 评论信号太少 | 进入复核 |
| 85E7Q 无法拆出画质、价格、智能、服务等基本信号 | 进入复核 |
| 负向风险集中且影响核心卖点 | 进入复核 |

blocked 条件：

| 条件 | 处理 |
| --- | --- |
| M05 未完成 | M06 blocked |
| M05 profile `downstream_ready=false` | 当前 SKU blocked |
| seed 无法加载 | M06 blocked |
| 所有可用评论句为空 | 当前 SKU blocked 或空 profile |
| 输出表写入失败 | M06 failed |
| evidence 追溯链断裂 | 当前信号 blocked |

### 9.15 `CommentDownstreamSignalService`

主流程：

```text
load signal seed bundle
load M05 input bundle
load optional M03/M04a context
check reusable by input_fingerprint
extract entities for each atom
run seven signal extractors independently
write signal candidates
aggregate downstream signals
build sku comment signal profile
apply review policy
mark previous records inactive
upsert current records
return M06RunResult and downstream impacts
```

幂等规则：

| 情况 | 动作 |
| --- | --- |
| fingerprint 未变且未 force | 跳过 |
| fingerprint 未变但 `force=true` | 重算 |
| candidate result hash 未变 | 复用当前记录 |
| signal result hash 未变 | 复用当前记录 |
| hash 变化 | 旧记录 `is_current=false`，插入新记录 |
| 上游 M05 signal 来源消失 | 当前 M06 对象置为 inactive |

### 9.16 下游影响登记

M06 不直接调用下游，只返回影响范围：

| M06 输出变化 | 下游影响 |
| --- | --- |
| `claim_validation` 变化 | M04b、M08、M11.5、M13-M16 |
| `task_cue` 变化 | M08、M09-M16 |
| `target_group_cue` 变化 | M08、M10-M16 |
| `battlefield_support` 变化 | M08、M11-M16 |
| `pain_point` 变化 | M08、M11、M13-M16 |
| `price_perception` 变化 | M08、M09、M13-M16 |
| `service_signal` 变化 | M08、M10、M11、M15-M16 |
| SKU profile ready 状态变化 | M08-M16 |

## 10. runner/API 任务

### 10.1 Runner 入口

新增：

```text
run_core3_m06_comment_downstream_signal(
  project_id: str,
  category_code: str,
  batch_id: str,
  sku_scope: list[str] | None,
  signal_types: list[str] | None,
  force: bool = False,
  run_id: str | None = None
) -> M06RunResult
```

`signal_types` 为空时运行全部七类信号。非空时只允许七类枚举。

### 10.2 Runner 返回

```json
{
  "module": "M06",
  "status": "completed_with_warning",
  "processed_sku_count": 33,
  "changed_sku_codes": ["TV00029115"],
  "changed_signal_types": ["claim_validation", "task_cue", "battlefield_support"],
  "blocked_sku_codes": [],
  "review_required_sku_codes": ["TV00029115"],
  "downstream_impacts": [
    {"sku_code": "TV00029115", "next_modules": ["M04b", "M08", "M09", "M11"]}
  ],
  "metrics": {
    "candidate_count": 120000,
    "downstream_signal_count": 2500,
    "profile_count": 33
  }
}
```

状态规则：

| 条件 | status |
| --- | --- |
| 全部 SKU 成功且无 warning | `completed` |
| 有 warning 或 review | `completed_with_warning` |
| 部分 SKU blocked | `partial_blocked` |
| seed/M05 缺失导致无法运行 | `blocked` |
| 写库失败 | `failed` |

### 10.3 API

在 `apps/api-server/app/api/core3_real_data.py` 增加：

| API | 用途 |
| --- | --- |
| `POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/run-m06-comment-downstream-signal` | 手动运行 M06 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comment-signals` | 查询 SKU 聚合评论信号 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comment-signal-profile` | 查询 SKU 评论信号画像 |
| `GET /api/mvp/core3/v2/projects/{project_id}/comment-signals/{signal_id}/candidates` | 查询聚合信号候选明细 |
| `GET /api/mvp/core3/v2/projects/{project_id}/comment-signal-candidates/{candidate_id}` | 查询单条候选详情 |

### 10.4 API 边界

API 可以返回：

- 信号中文名称。
- 下游目标编码和中文名称。
- 代表评论短句。
- 提及数、提及率、正负向率。
- 置信度。
- 硬规格边界说明。
- 服务隔离说明。
- 证据追溯 ID。

API 不得返回：

- 最终用户任务分。
- 最终目标客群分。
- 最终价值战场分。
- 核心竞品选择。
- 竞品评分。
- 业务报告结论。
- 大段内部 JSON 给高层页面。
- prompt、模型过程或 AI 话术。

### 10.5 API filters

`comment-signals` 支持：

```text
signal_type
target_code_hint
polarity
signal_level
confidence_level
service_guardrail_flag
limit
offset
```

`comment-signals/{signal_id}/candidates` 支持：

```text
polarity
signal_strength_level
cue_basis
low_value_flag
limit
offset
```

### 10.6 API 测试

必须覆盖：

- run API 返回 M06 runner status。
- profile API 返回七类摘要。
- signals API 可按 signal_type 过滤。
- candidates API 可追溯到 M05/M02 evidence。
- response 不包含最终任务、客群、战场、竞品字段。
- `service_guardrail_flag=true` 的信号展示“仅用于服务保障”。
- `hard_spec_policy='experience_only'` 的信号展示“仅证明体验感知”。

## 11. 测试任务

### 11.1 seed loader 测试

`test_m06_signal_seed_loader.py`：

| 场景 | 期望 |
| --- | --- |
| seed 正常 | 加载五类 seed 和内置字典 |
| 缺 `standard_claims` | blocked |
| 缺 `user_tasks` | blocked |
| 缺 `target_groups` | blocked |
| 缺 `battlefields` | blocked |
| 缺 `comment_topics` | blocked |
| target 前缀错误 | 校验失败 |
| seed hash | 内容变化 hash 变化 |

### 11.2 input service 测试

`test_m06_input_service.py`：

| 场景 | 期望 |
| --- | --- |
| M05 profile ready | 正常组装输入 |
| M05 profile 缺失 | 当前 SKU blocked |
| `downstream_ready=false` | 当前 SKU blocked |
| atom 为空 | 写空 profile |
| topic hint 缺失 | 可运行但降置信 |
| M03/M04a 缺失 | 可运行 |
| fingerprint | M05/seed/M03/M04a 变化时变化 |

### 11.3 entity extractor 测试

`test_m06_entity_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “客厅看电影很震撼” | 场景、动作、结果 |
| “看球不卡” | 场景/动作、结果 |
| “给爸妈买，语音简单” | 人群、购买动机、结果 |
| “接 PS5 很方便” | 对象、动作、结果 |
| “安装师傅专业” | 服务词 |
| “太贵不值” | 价格词、负向词 |
| 空文本 | 空实体，不异常 |

### 11.4 claim validation 测试

`test_m06_claim_validation_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “画质很清晰” | 画质相关 `claim_validation` |
| “暗场细节好” | 控光体验候选，不证明分区数 |
| “看球不卡” | 体育运动流畅体验候选，不证明刷新率 |
| “接 PS5 很方便” | 游戏连接体验，不证明 HDMI 2.1 端口数 |
| “安装师傅专业” | 不生成产品 claim |
| 服务型 claim | `service_guardrail_flag=true` |
| 低价值评论 | 不生成 strong signal |

### 11.5 task cue 测试

`test_m06_task_cue_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “客厅看电影很震撼” | `TASK_LIVING_ROOM_CINEMA` |
| “画质清晰，暗场好” | `TASK_PREMIUM_PICTURE_AV` |
| “玩 PS5 很流畅” | `TASK_GAMING_ENTERTAINMENT` |
| “看球不卡” | `TASK_SPORTS_WATCHING` |
| “85 吋换新很满意” | `TASK_LARGE_SCREEN_REPLACEMENT` |
| “孩子看不刺眼” | `TASK_CHILD_EYE_CARE` |
| “老人语音就会用” | `TASK_SENIOR_EASY_USE` |
| “价格很划算” | `TASK_VALUE_PURCHASE` |
| 单个词“游戏” | 最高 weak |

### 11.6 target group 测试

`test_m06_target_group_cue_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “全家客厅看电影” | `TG_FAMILY_UPGRADE` |
| “画质党很满意” | `TG_AV_QUALITY_SEEKER` |
| “主机游戏很流畅” | `TG_GAMER` |
| “看球很好” | `TG_SPORTS_FAN` |
| “给爸妈买” | `TG_SENIOR_FAMILY` |
| “孩子看护眼” | `TG_CHILD_FAMILY` |
| “性价比高” | `TG_VALUE_BUYER` |
| “新家装修用” | `TG_NEW_HOME_DECORATOR` |
| 仅场景推断 | 最高 medium |

### 11.7 battlefield 支撑测试

`test_m06_battlefield_support_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “画质清晰，色彩好” | 支撑 `BF_PREMIUM_PICTURE` |
| “大屏看电影震撼” | 支撑 `BF_FAMILY_VIEWING_UPGRADE` |
| “看球不卡，游戏流畅” | 支撑 `BF_GAMING_SPORTS` |
| “价格划算，大屏值” | 支撑 `BF_LARGE_SCREEN_VALUE` |
| “孩子看不累眼” | 支撑 `BF_FAMILY_EYE_CARE` |
| “老人语音会用” | 支撑 `BF_SENIOR_EASE_OF_USE` |
| “系统广告多” | 削弱 `BF_SMART_SYSTEM_EXPERIENCE` |
| “音质好，有影院感” | 支撑 `BF_CINEMA_AUDIO_IMMERSION` |
| “安装师傅专业” | 只支撑 `BF_SERVICE_ASSURANCE` |

### 11.8 pain point 测试

`test_m06_pain_point_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “画质模糊” | `RISK_PICTURE_NEGATIVE` |
| “看球拖影” | `RISK_MOTION_LAG` |
| “系统广告多还卡” | `RISK_SYSTEM_ADS_LAG` |
| “声音小，有杂音” | `RISK_AUDIO_NEGATIVE` |
| “看久刺眼” | `RISK_EYE_DISCOMFORT` |
| “配送慢，安装差” | `RISK_SERVICE_DELIVERY` |
| “有坏点，做工差” | `RISK_DURABILITY_QUALITY` |
| “太贵不值” | `RISK_PRICE_OVERPAY` |

### 11.9 price perception 测试

`test_m06_price_perception_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “性价比高，划算” | `PRICE_VALUE_POSITIVE` |
| “太贵，不值” | `PRICE_VALUE_NEGATIVE` |
| “活动优惠大” | `PRICE_PROMOTION_SENSITIVE` |
| “85 吋这个价很值” | `PRICE_BIG_SCREEN_VALUE` |
| “刚买就降价” | `PRICE_DROP_RISK` |
| 任意价格信号 | `hard_spec_policy='market_fact_required'` |

### 11.10 service signal 测试

`test_m06_service_signal_extractor.py`：

| 输入 | 期望 |
| --- | --- |
| “安装快，师傅专业” | `SERVICE_INSTALL_POSITIVE` |
| “送货快，物流好” | `SERVICE_DELIVERY_POSITIVE` |
| “客服响应快” | `SERVICE_SUPPORT_POSITIVE` |
| “安装慢，不专业” | `SERVICE_INSTALL_NEGATIVE` |
| “配送慢，包装破” | `SERVICE_DELIVERY_NEGATIVE` |
| “售后差，不处理” | `SERVICE_SUPPORT_NEGATIVE` |
| 任意服务信号 | `service_guardrail_flag=true`，不进入产品 claim |

### 11.11 aggregator 测试

`test_m06_signal_aggregator.py`：

| 场景 | 期望 |
| --- | --- |
| 多句同 comment_unit 命中同 target | `mention_count` 按 1 计 |
| 多 comment_unit 命中同 target | `mention_count` 去重累加 |
| `mention_rate` | 使用 `valid_comment_unit_count` 分母 |
| 正负混合 | `polarity='mixed'` 或分 polarity 聚合 |
| 服务信号 | `downstream_usage_policy_json` 阻断产品 claim |
| 代表短句 | 选高强度、高具体度候选 |
| 低价值候选 | 不推高 strong signal |

### 11.12 profile builder 测试

`test_m06_signal_profile_builder.py`：

| 场景 | 期望 |
| --- | --- |
| 七类都有信号 | 七类 summary 全部生成 |
| 某类无信号 | summary 为空数组，不缺 key |
| 服务占比高 | quality flag |
| strong/medium/weak 统计 | 计数正确 |
| claim validation ready | 有产品 claim_validation 且无阻断 |
| blocked profile | confidence 低且 ready=false |

### 11.13 review policy 测试

`test_m06_review_policy.py`：

| 条件 | 期望 |
| --- | --- |
| unknown signal rate 高 | warning |
| service share > 0.50 | warning |
| low value candidate rate > 0.20 | warning |
| 服务误入产品 claim | review |
| 低价值 strong signal | review |
| M05 blocked | blocked |
| 85E7Q 无法拆出基本信号 | review |

### 11.14 repository 测试

`test_m06_repositories.py`：

| 场景 | 期望 |
| --- | --- |
| bulk insert candidates | 成功 |
| hash 未变 | 幂等 |
| hash 变化 | 旧记录 inactive |
| signal type 查询 | 只返回对应类型 |
| candidate 追溯 | 可查 M05/M02 evidence |
| profile current | 只返回当前版本 |
| 不读原始表 | 测试失败保护 |

### 11.15 runner 测试

`test_m06_runner.py`：

| 场景 | 期望 |
| --- | --- |
| 正常 SKU | 输出 candidate、signal、profile |
| `signal_types=['task_cue']` | 只生成任务线索 |
| fingerprint 未变 | 跳过重算 |
| `force=true` | 强制重算 |
| 部分 SKU blocked | `partial_blocked` |
| seed 缺失 | `blocked` |
| 返回 downstream impacts | 按变化 signal type 返回 |

### 11.16 API 测试

`test_m06_api.py`：

| API | 期望 |
| --- | --- |
| run M06 | 返回 runner status |
| profile | 返回七类摘要 |
| signals | 支持 signal_type 过滤 |
| candidates | 支持分页和证据追溯 |
| candidate detail | 返回句级明细 |
| 越界字段 | 不返回最终任务、客群、战场、竞品结论 |

### 11.17 越界测试

`test_m06_no_business_outputs.py` 必须验证：

- M06 不读取原始 `comment_data`。
- M06 不读取市场原始表做价格判断。
- M06 不输出最终任务分。
- M06 不输出最终客群分。
- M06 不输出最终战场分。
- M06 不输出竞品候选、竞品评分或核心三竞品选择。
- `service_signal` 不进入产品 `claim_validation`。
- 评论不能证明 nits、分区数、端口数、芯片、内存、认证等硬规格。
- M13/M15 不能绕过 M06 直接读 M05 或原始评论生成竞品理由。

### 11.18 85E7Q fixture 测试

`test_m06_85e7q_fixture.py`：

| 数据事实 | 验收 |
| --- | --- |
| 85E7Q 有 3621 行评论 | M06 聚合不使用原始行数作为分母 |
| 85E7Q 有 1648 个去重 comment_id | mention_rate 使用 M05 去重评论单元 |
| 85E7Q 无结构化卖点 | M06 不失败，不补造宣传证据 |
| 画质评论 | 输出画质 `claim_validation` 和 `BF_PREMIUM_PICTURE` 支撑 |
| 看球评论 | 输出 `TASK_SPORTS_WATCHING` 和 `BF_GAMING_SPORTS` |
| 游戏评论 | 输出 `TASK_GAMING_ENTERTAINMENT`，不证明 HDMI 2.1 端口数 |
| 音质评论 | 输出音效体验 claim 和 `BF_CINEMA_AUDIO_IMMERSION` |
| 智能/语音评论 | 输出 `TASK_SENIOR_EASY_USE` 和智能系统战场支撑 |
| 性价比评论 | 输出 `PRICE_VALUE_POSITIVE`，不替代真实价格 |
| 安装服务评论 | 只输出 service_signal 或 `BF_SERVICE_ASSURANCE` |

## 12. 205/85E7Q 验收

### 12.1 全量样例验收

当前 205 样例约束：

| 指标 | 基线 | M06 验收 |
| --- | ---: | --- |
| 原始评论行 | 62426 | 不作为提及率主分母 |
| 不同 `comment_id` | 34438 | M06 使用 M05 去重评论单元 |
| 不同正文 hash | 13514 | 重复正文不放大 signal |
| 空维度 | 15766 | 文本具体仍可抽信号 |
| 空情感 | 15766 | unknown 降置信，不当 neutral |
| 服务安装占比较高 | 不进入产品 claim |

全量预期：

- 低价值和默认评价不形成 strong signal。
- 服务安装类评论进入 `service_signal` 和 `BF_SERVICE_ASSURANCE`。
- 高频产品体验评论形成对应 `claim_validation`、`task_cue`、`battlefield_support`。
- 价格价值感进入 `price_perception`，等待 M07/M13 价格事实复核。

### 12.2 85E7Q 验收

85E7Q `model_code=TV00029115`：

| 评论方向 | 应输出信号 | 边界 |
| --- | --- | --- |
| 画面清晰、色彩好、细节好 | `claim_validation` 支持画质体验；`battlefield_support=BF_PREMIUM_PICTURE/BF_FAMILY_VIEWING_UPGRADE` | 不能证明亮度 5200 或分区 3500 |
| 看球清晰、运动画面顺 | `task_cue=TASK_SPORTS_WATCHING`；`battlefield_support=BF_GAMING_SPORTS` | 不能证明原生刷新率 |
| 游戏流畅、接主机方便 | `task_cue=TASK_GAMING_ENTERTAINMENT`；`claim_validation` 体验验证 | 不能证明 HDMI 2.1 端口数 |
| 音质好、听觉棒 | `claim_validation` 支持音效体验；`battlefield_support=BF_CINEMA_AUDIO_IMMERSION` | 不能证明喇叭功率 |
| 语音方便、运行流畅 | `task_cue=TASK_SENIOR_EASY_USE`；`battlefield_support=BF_SMART_SYSTEM_EXPERIENCE` | 不能证明芯片/内存规格 |
| 性价比高、买得值 | `price_perception=PRICE_VALUE_POSITIVE` | 不能替代真实价格 |
| 安装快、师傅专业 | `service_signal`；可支持 `BF_SERVICE_ASSURANCE` | 不能增强画质或游戏卖点 |

### 12.3 不达标处理

| 现象 | 处理 |
| --- | --- |
| 85E7Q 无法拆出画质/价格/智能/服务基本信号 | review |
| 85E7Q 服务评论进入产品 claim | 测试失败 |
| 85E7Q claim_validation 被写成硬规格证明 | 测试失败 |
| mention_rate 使用 3621 原始行分母 | 测试失败 |
| `task_cue` 被下游当最终任务 | 越界测试失败 |
| API 返回竞品结论 | 越界测试失败 |

## 13. 完成标准

编码任务完成时必须满足：

1. `0012_core3_real_data_comment_downstream_signal.py` 可升级、可回滚。
2. 3 张 M06 输出表字段、主键、唯一键、索引、JSONB 字段与详细设计一致。
3. M06 默认只读 M05 输出和 seed。
4. M06 可选读取 M03/M04a，但缺失时可降级运行。
5. M06 不直接读取原始 `comment_data`。
6. M06 不读取市场原始表做价格判断。
7. M06 可输出 `core3_comment_signal_candidate`。
8. M06 可输出 `core3_comment_downstream_signal`。
9. M06 可输出 `core3_sku_comment_signal_profile`。
10. 七类信号独立抽取、独立聚合、独立下游消费。
11. 每条 candidate 可追溯 M05/M02 evidence。
12. 聚合 mention rate 使用 M05 去重评论单元分母。
13. 低价值评论不形成 strong signal。
14. 服务信号不进入产品 claim validation。
15. 评论不能证明硬规格。
16. 价格感知不替代真实价格。
17. M06 不输出最终任务、客群、战场或竞品结论。
18. 85E7Q 可拆出画质、看球、音效、价格、智能、服务信号。
19. M05/seed/M03/M04a 变化能触发正确下游影响范围。
20. warning/review/block 条件可落入 M16 所需字段。
21. 所有 M06 单元、集成、边界、越界、85E7Q fixture 测试通过。

建议测试命令：

```bash
cd apps/api-server && .venv/bin/pytest tests/core3_real_data/test_m06_*.py
```

如项目当前测试命令不同，以仓库实际配置为准，但必须能单独运行 M06 测试。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 把 M05 topic 直接当任务/战场 | 方法论越界 | M06 每类 signal 重新判断，越界测试固化 |
| 评论证明硬规格 | 业务误导 | `hard_spec_policy` 和 hard spec 越界测试 |
| 服务信号增强产品卖点 | 竞品理由失真 | `service_guardrail_flag`、eligibility flags |
| 原始行数做提及率分母 | 声量被维度拆行放大 | 使用 M05 去重 comment unit |
| 价格感知替代真实价格 | 价格判断错误 | `market_fact_required`，M13 必须复核 |
| 同一句多信号互相覆盖 | 下游漏证据 | candidate 按 signal_type + target 独立 |
| 低价值评论形成 strong signal | 噪声污染 | 低价值降权和 review |
| M03/M04a 缺失阻断 M06 | 链路过硬 | 辅助输入可缺省 |
| seed 缺失后临时写死标签 | 口径不可评审 | seed loader blocked |
| API 被前端拿去拼最终结论 | 高层页面误导 | API response 和前端边界测试 |

回滚方式：

1. Alembic downgrade 删除 M06 3 张输出表。
2. 移除 M06 API router 注册。
3. 移除 M06 runner 注册。
4. 不影响 M00-M05 产物。
5. 不影响 M04a 产物。
6. 不影响旧 `core3_mvp` 页面。

## 15. 下游依赖

| 下游模块 | 依赖 M06 的内容 |
| --- | --- |
| M04b | 只消费 `signal_type='claim_validation'` 的 `core3_comment_downstream_signal` |
| M08 | 消费 `core3_sku_comment_signal_profile` 和必要 signal |
| M09 | 消费 `task_cue`、`price_perception`、任务相关 `pain_point` |
| M10 | 消费 `target_group_cue`、服务敏感相关 `service_signal`、人群相关 `task_cue` |
| M11 | 消费 `battlefield_support`、`pain_point`、必要 `service_signal` |
| M11.5 | 使用评论正负向提及计算 CPI，但只是证据之一 |
| M13 | 使用评论信号作为评分组件，不得绕过 M06 |
| M15 | 展示代表评论短句，但不能包装成最终结论 |
| M16 | 使用 review/block/impact 信息生成复核和增量计划 |

M06 给下游的边界承诺：

| 下游 | 承诺 |
| --- | --- |
| M04b | `service_guardrail_flag=true` 不得增强产品卖点 |
| M04b | `hard_spec_policy='experience_only'` 不证明硬规格 |
| M09 | `task_cue` 只是任务线索，不能单独高置信成立 |
| M10 | `target_group_cue` 只是客群线索，不能单独高置信成立 |
| M11 | `battlefield_support` 只是评论支撑，战场仍需任务、客群、卖点、市场 |
| M13 | `price_perception` 必须结合 M07 真实价格 |
| M15 | 代表短句必须作为证据，不是最终业务结论 |

正确链路：

```text
M05 评论基础证据
-> M06 下游专用评论信号
-> M04b/M08/M09/M10/M11/M11.5/M13
-> M12-M15 竞品推导和报告
```

明确禁止：

```text
M06 task_cue -> 最终用户任务
M06 target_group_cue -> 最终客群
M06 battlefield_support -> 最终价值战场
M06 claim_validation -> 硬规格证明
M06 service_signal -> 产品卖点增强
M06 price_perception -> 真实低价判断
M06 signal -> 核心竞品选择
```

## 16. 编码子任务建议

如果正式编码继续按小任务执行，建议拆为：

| 子任务 | 内容 | 完成标准 |
| --- | --- | --- |
| M06-A | Alembic 迁移 | 3 表、索引、约束、回滚 |
| M06-B | schema 和枚举 | typed contracts、API schema、枚举 |
| M06-C | seed loader | 五类 seed、风险/价格/服务字典 |
| M06-D | input service | 只读 M05、选读 M03/M04a、fingerprint |
| M06-E | entity extractor | 场景/动作/人群/对象/结果/价格/服务/风险词 |
| M06-F | claim validation extractor | 卖点体验验证、硬规格边界 |
| M06-G | task/group/battlefield extractors | 三类线索独立抽取 |
| M06-H | pain/price/service extractors | 风险、价格感知、服务保障 |
| M06-I | aggregator | 去重分母、提及率、正负向率、signal score |
| M06-J | profile + review policy | SKU 评论信号画像、warning/review/block |
| M06-K | runner + API | 运行入口、查询 API、分页 |
| M06-L | tests + 85E7Q fixture | 单元、集成、越界、样例验收 |

每个子任务都应保持可测试，不建议在一个编码任务里一次性完成 M06-A 到 M06-L。

## 17. 下次任务

下一个开发任务文档：

```text
docs/core3_mvp/real_data_v2/development/M04b_development_tasks.md
```

M04b 需要基于 M04a 的基础卖点激活和 M06 的 `claim_validation` 信号，生成评论验证增强后的最终卖点激活。M04b 必须处理 85E7Q 无结构化卖点的降级场景，明确评论只能增强体验感知，不能补造宣传证据或硬规格证据。
