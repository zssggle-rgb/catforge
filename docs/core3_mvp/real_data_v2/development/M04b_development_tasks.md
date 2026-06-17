# M04b 评论验证增强开发任务

## 1. 模块目标

M04b 的开发目标是在 M04a 基础卖点激活之后，只使用 M06 的 `claim_validation` 评论信号，对标准卖点做体验验证、削弱、风险标记和最终置信度调整，生成下游可消费的最终卖点激活结果。

M04b 必须解决的工程问题：

1. 把“参数 + 宣传”的基础卖点能力和“用户评论是否感知到该体验”分开保存。
2. 为每个 SKU + 标准卖点生成评论验证聚合结果。
3. 按卖点类型使用不同评论权重，计算最终激活分和激活等级。
4. 识别评论增强、评论削弱、弱感知、评论冲突、服务错配、硬规格越权等复核问题。
5. 为 M08、M09、M10、M11、M11.5、M12-M15 提供最终可引用的 `core3_sku_claim_activation`。
6. 对 85E7Q 这种无结构化卖点但有参数和评论的 SKU，保留 `missing_structured_claim`、`param_only` 风险，不把评论伪造成宣传证据或硬规格证据。

M04b 必须固化以下边界：

- M04b 只消费 M04a 基础卖点和 M06 `claim_validation`。
- M04b 不重新解析原始评论。
- M04b 不直接读取 M05 topic hint。
- M04b 不消费 M06 的 `task_cue`、`target_group_cue`、`battlefield_support`、`pain_point`、`price_perception`、`service_signal`，除非这些已在 M06 被映射为 `claim_validation`。
- M04b 不重新计算参数分和宣传分。
- M04b 不用评论证明 nits、分区数、端口数、原生刷新率、芯片、内存、认证等硬规格。
- M04b 不把安装、物流、售后评论用于增强画质、游戏、护眼、音效、智能等产品卖点。
- M04b 不做战场内卖点价值分层，不判断任务、客群、战场、竞品。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M04a 任务 | `docs/core3_mvp/real_data_v2/development/M04a_development_tasks.md` |
| M06 任务 | `docs/core3_mvp/real_data_v2/development/M06_development_tasks.md` |
| M04b 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M04b_claim_comment_enhancement_requirements.md` |
| M04b 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M04b_claim_comment_enhancement_design.md` |
| M04a 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M04a_base_claim_activation_design.md` |
| M06 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M06_comment_downstream_signal_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认：

- M04a 已能输出 `core3_sku_claim_source_status` 和 `core3_sku_claim_activation_base`。
- M04a `core3_sku_claim_activation_base` 有 `claim_code`、`claim_name`、`claim_group`、`param_score`、`promo_score`、`base_activation_score`、`activation_basis`、`missing_signals`、`conflict_flags`、`evidence_ids`。
- M04a `core3_sku_claim_source_status` 能识别 `has_structured_claim`、`missing_structured_claim`、`param_only` 等来源状态。
- M06 已能输出 `core3_comment_downstream_signal`，且 M04b 只读取 `signal_type='claim_validation'`。
- M06 signal 包含 `target_code_hint`、`mention_count`、`mention_rate`、`positive_rate`、`negative_rate`、`signal_score`、`specificity_avg`、`evidence_quality_score`、`service_guardrail_flag`、`hard_spec_policy`、`representative_phrases`、`evidence_ids`。
- `standard_claims` seed 可用于判断卖点类型、卖点分组、技术硬规格边界和服务型卖点。

## 3. 本次范围

本次开发任务拆分覆盖 M04b 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 3 张 M04b 输出表 |
| schema | 新增 M04b runner、内部记录、API、复核、下游影响 schema |
| repository | 只读 M04a/M06/seed，写 M04b 输出 |
| input service | 读取 M04a 基础卖点、来源状态和 M06 claim_validation |
| type policy | 标准卖点类型映射、权重策略和封顶策略 |
| validation builder | 生成评论验证聚合结果 |
| scorer | 计算评论验证分、评论风险分、最终激活分 |
| guardrail | 硬规格、服务、param_only、comment_only、value market 校验 |
| review policy | 生成复核问题和下游策略 |
| runner/API | 运行入口和运营查询接口 |
| 测试 | 单元、集成、边界、越界、85E7Q fixture |
| 增量 | fingerprint、result_hash、is_current、下游影响登记 |

本次不做：

- 不实现 M07 市场画像。
- 不实现 M08 SKU 综合信号画像。
- 不实现 M09/M10/M11/M11.5 最终业务推导。
- 不实现 M12-M15 竞品推导和报告。
- 不实现前端页面。
- 不部署到 205。
- 不把 M04b API 直接用于高层页面的最终竞品结论。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_schemas.py
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_repositories.py
apps/api-server/app/services/core3_real_data/claim_comment_seed_loader.py
apps/api-server/app/services/core3_real_data/claim_base_input_service.py
apps/api-server/app/services/core3_real_data/claim_validation_signal_input_service.py
apps/api-server/app/services/core3_real_data/claim_type_policy_service.py
apps/api-server/app/services/core3_real_data/claim_comment_validation_builder.py
apps/api-server/app/services/core3_real_data/claim_activation_final_scorer.py
apps/api-server/app/services/core3_real_data/claim_guardrail_service.py
apps/api-server/app/services/core3_real_data/claim_comment_review_policy.py
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_service.py
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `claim_comment_enhancement_schemas.py` | M04b 内部 typed contracts |
| `claim_comment_enhancement_repositories.py` | M04b 输入读取和输出写入 |
| `claim_comment_seed_loader.py` | 加载 `standard_claims` seed 和类型映射 |
| `claim_base_input_service.py` | 读取 M04a 基础卖点和来源状态 |
| `claim_validation_signal_input_service.py` | 读取 M06 `claim_validation` |
| `claim_type_policy_service.py` | 卖点类型、权重、封顶和下游策略 |
| `claim_comment_validation_builder.py` | 生成评论验证聚合 |
| `claim_activation_final_scorer.py` | 计算最终激活分和等级 |
| `claim_guardrail_service.py` | 硬规格、服务、param_only、comment_only 保护 |
| `claim_comment_review_policy.py` | 生成复核问题和 review/block 状态 |
| `claim_comment_enhancement_service.py` | M04b 模块编排 |
| `claim_comment_enhancement_runner.py` | M04b runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0013_core3_real_data_claim_comment_enhancement.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0013_core3_real_data_claim_comment_enhancement.py` | 新增 M04b 3 张输出表 |
| `core3_real_data.py` schema | 导出 M04b API response/request |
| `core3_real_data.py` API | 增加 M04b 运行、查询和证据钻取 API |
| `constants.py` | 补 M04b 类型、作用、状态、问题枚举 |
| `runner.py` | 注册 M04b runner，不改变已有模块逻辑 |
| `conftest.py` | 增加 M04a/M06 输入 fixture、85E7Q M04b fixture |

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m04b_seed_loader.py
apps/api-server/tests/core3_real_data/test_m04b_base_input_service.py
apps/api-server/tests/core3_real_data/test_m04b_claim_validation_signal_input.py
apps/api-server/tests/core3_real_data/test_m04b_claim_type_policy.py
apps/api-server/tests/core3_real_data/test_m04b_comment_validation_builder.py
apps/api-server/tests/core3_real_data/test_m04b_final_scorer.py
apps/api-server/tests/core3_real_data/test_m04b_guardrail_service.py
apps/api-server/tests/core3_real_data/test_m04b_review_policy.py
apps/api-server/tests/core3_real_data/test_m04b_repositories.py
apps/api-server/tests/core3_real_data/test_m04b_runner.py
apps/api-server/tests/core3_real_data/test_m04b_api.py
apps/api-server/tests/core3_real_data/test_m04b_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m04b_85e7q_fixture.py
```

### 4.4 只读依赖文件

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_real_data/base_claim_activation_repositories.py
apps/api-server/app/services/core3_real_data/base_claim_activation_schemas.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_repositories.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_schemas.py
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

- M04a 输出表结构和基础激活逻辑。
- M06 输出表结构和 signal 抽取逻辑。
- M05 评论基础证据逻辑。
- M07-M16 结果表。
- 原始四表结构。
- 旧 `core3_mvp` 服务和页面。
- 前端高层报告页面。
- 205 部署配置。

不允许引入的行为：

- 直接读取原始 `comment_data`。
- 直接读取 M05 `core3_comment_topic_hint` 做卖点验证。
- 读取 M06 非 `claim_validation` 信号来增强卖点。
- 直接读取市场量价。
- 输出最终用户任务、目标客群、价值战场或竞品判断。
- 用评论证明 nits、分区数、端口数、原生刷新率、芯片、内存、认证等硬规格。
- 用服务评论增强产品卖点。
- 用评论补齐 `promo_evidence_ids`。
- 把 `param_only` 或 `missing_structured_claim` 静默升级成完整证据。
- 在测试中调用外部 LLM。

## 6. 数据库迁移任务

### 6.1 迁移文件

新增迁移：

```text
apps/api-server/alembic/versions/0013_core3_real_data_claim_comment_enhancement.py
```

迁移只新增 M04b 输出表，不修改 M04a/M06 表。

### 6.2 新增表

| 表 | 粒度 | 说明 |
| --- | --- | --- |
| `core3_sku_claim_comment_validation` | SKU + 标准卖点 | 评论对卖点的体验验证、削弱和风险 |
| `core3_sku_claim_activation` | SKU + 标准卖点 | 最终卖点激活结果，下游唯一主表 |
| `core3_claim_comment_review_issue` | SKU + 标准卖点 + 问题 | 评论增强复核和风险问题 |

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
seed_version
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
| `rule_version` | 非空，建议首版 `m04b_claim_comment_enhancement_v1` |
| `seed_version` | 非空，来自 `standard_claims` seed |
| `input_fingerprint` | 非空 |
| `result_hash` | 非空 |
| `is_current` | 默认 true |
| `processing_status` | `success`、`warning`、`review_required`、`blocked`、`failed` |
| `review_status` | `auto_pass`、`review_required`、`approved`、`rejected`、`waived` |
| JSON 字段 | PostgreSQL 使用 `JSONB` |
| 时间字段 | 使用 timezone aware |

### 6.4 `core3_sku_claim_comment_validation`

#### 6.4.1 字段

```text
claim_comment_validation_id
validation_key
claim_activation_base_id
claim_source_status_id
claim_code
claim_name
claim_group
m04b_claim_type
base_activation_score
base_activation_level
base_activation_basis
param_score
promo_score
claim_source_status
mention_count
sentence_count
valid_comment_unit_count
mention_rate
positive_count
negative_count
positive_rate
negative_rate
specificity_avg
evidence_quality_score
domain_match_score
comment_validation_score
comment_risk_score
comment_effect
perception_status
hard_spec_protection_flag
service_guardrail_flag
comment_only_flag
weak_perception_flag
contradiction_flag
representative_phrases
comment_signal_ids
comment_candidate_ids
comment_evidence_ids
base_evidence_ids
quality_flags
confidence
confidence_level
```

#### 6.4.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `claim_comment_validation_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, claim_code, rule_version, seed_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, claim_code` |
| 索引 | `claim_code, comment_effect` |
| 索引 | `perception_status` |
| 索引 | `claim_source_status` |
| 索引 | `m04b_claim_type` |
| 索引 | `service_guardrail_flag` |
| 索引 | `review_required` |
| GIN | `representative_phrases`、`comment_signal_ids`、`comment_evidence_ids`、`quality_flags` |

#### 6.4.3 约束

| 字段 | 约束 |
| --- | --- |
| `m04b_claim_type` | `technical_hard`、`technical_experience_mixed`、`experience_scenario`、`service`、`value`、`unknown` |
| `comment_effect` | `enhance`、`weaken`、`neutral`、`contradict`、`comment_only_hint`、`blocked` |
| `perception_status` | `validated`、`weak_perception`、`contradicted`、`insufficient_comment`、`not_applicable`、`service_guarded`、`comment_only_pending` |
| 分数和比率 | 0-1 |
| `mention_count`、`sentence_count` | >= 0 |
| `claim_code` | `CLAIM_*` |

### 6.5 `core3_sku_claim_activation`

#### 6.5.1 字段

```text
claim_activation_id
activation_key
claim_activation_base_id
claim_comment_validation_id
claim_source_status_id
claim_code
claim_name
claim_group
m04b_claim_type
param_score
promo_score
base_activation_score
comment_validation_score
comment_risk_score
final_activation_score
base_activation_level
activation_level
activation_basis
perception_status
claim_source_status
comment_effect
hard_spec_protection_flag
service_guardrail_flag
missing_structured_claim_flag
param_only_flag
promo_only_flag
comment_only_flag
weak_perception_flag
contradiction_flag
value_requires_market_validation
downstream_usage_policy_json
score_breakdown_json
missing_signals
conflict_flags
quality_flags
evidence_ids
param_evidence_ids
promo_evidence_ids
comment_evidence_ids
comment_signal_ids
representative_phrases
confidence
confidence_level
```

#### 6.5.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `claim_activation_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, claim_code, rule_version, seed_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, claim_code` |
| 索引 | `claim_code, activation_level` |
| 索引 | `m04b_claim_type` |
| 索引 | `activation_basis` |
| 索引 | `perception_status` |
| 索引 | `missing_structured_claim_flag` |
| 索引 | `param_only_flag` |
| 索引 | `comment_only_flag` |
| 索引 | `review_required` |
| GIN | `downstream_usage_policy_json`、`score_breakdown_json`、`evidence_ids`、`missing_signals`、`conflict_flags`、`quality_flags` |

#### 6.5.3 约束

| 字段 | 约束 |
| --- | --- |
| `activation_level` | `high`、`medium`、`low`、`unknown`、`review_required` |
| `activation_basis` | M04a basis + M04b 扩展 basis |
| `final_activation_score` | 0-1，评分后 clamp |
| `comment_only_flag=true` | `activation_level` 最高 `low` 或 `review_required` |
| `param_only_flag=true` | 默认最高 `medium` |
| `missing_structured_claim_flag=true` | M15 必须提示数据缺口 |
| `value_requires_market_validation=true` | M11.5/M13 必须补市场证据 |

### 6.6 `core3_claim_comment_review_issue`

#### 6.6.1 字段

```text
issue_id
issue_key
claim_activation_id
claim_comment_validation_id
claim_activation_base_id
claim_code
claim_name
issue_type
severity
business_note
technical_note
suggested_action
downstream_policy
evidence_ids
comment_signal_ids
quality_flags
issue_status
```

#### 6.6.2 主键、唯一键、索引

| 类型 | 字段 |
| --- | --- |
| 主键 | `issue_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, claim_code, issue_type, rule_version, seed_version` |
| 索引 | `sku_code, claim_code` |
| 索引 | `issue_type` |
| 索引 | `severity` |
| 索引 | `issue_status` |
| 索引 | `review_required` |
| GIN | `evidence_ids`、`comment_signal_ids`、`quality_flags` |

#### 6.6.3 约束

| 字段 | 约束 |
| --- | --- |
| `issue_type` | M04b 固定问题类型 |
| `severity` | `info`、`warning`、`review_required`、`blocked` |
| `downstream_policy` | `continue_with_warning`、`require_approval`、`block_downstream` |
| `issue_status` | `open`、`approved`、`rejected`、`waived`、`closed` |
| `business_note` | 必须中文，面向业务复核 |

### 6.7 迁移回滚

`downgrade` 按依赖反向删除：

1. `core3_claim_comment_review_issue`
2. `core3_sku_claim_activation`
3. `core3_sku_claim_comment_validation`

回滚不得删除 M04a/M06 产物。

## 7. model/schema 任务

### 7.1 内部 schema

在 `claim_comment_enhancement_schemas.py` 中定义：

```text
M04bRunRequest
M04bRunResult
M04bSkuInputBundle
M04bClaimBaseInput
M04bClaimSourceStatusInput
M04bClaimValidationSignalInput
M04bClaimTypePolicy
ClaimCommentValidationRecord
SkuClaimActivationRecord
ClaimCommentReviewIssueRecord
ClaimCommentScoreBreakdown
ClaimDownstreamUsagePolicy
M04bReviewIssue
M04bDownstreamImpact
```

### 7.2 API schema

在 `apps/api-server/app/schemas/core3_real_data.py` 中导出：

```text
M04bRunResponse
SkuClaimActivationResponse
SkuClaimActivationListResponse
ClaimCommentValidationResponse
ClaimCommentValidationListResponse
ClaimActivationEvidenceResponse
ClaimCommentReviewIssueResponse
ClaimCommentReviewIssueListResponse
```

API response 必须提供业务化解释字段：

| 内部字段 | API 展示字段 |
| --- | --- |
| `param_only_flag=true` | `参数支撑，宣传卖点缺失` |
| `missing_structured_claim_flag=true` | `缺结构化宣传卖点数据` |
| `hard_spec_protection_flag=true` | `评论仅验证体验，不能证明硬规格` |
| `service_guardrail_flag=true` | `仅可用于服务保障` |
| `comment_only_flag=true` | `仅评论线索，待复核` |
| `value_requires_market_validation=true` | `需结合市场价格验证` |
| `perception_status='weak_perception'` | `用户感知偏弱` |

### 7.3 枚举和常量

如 `constants.py` 尚未包含，需要补：

```text
M04B_RULE_VERSION = "m04b_claim_comment_enhancement_v1"
M04B_CLAIM_TYPE
M04B_COMMENT_EFFECT
M04B_PERCEPTION_STATUS
M04B_ACTIVATION_BASIS
M04B_ACTIVATION_LEVEL
M04B_ISSUE_TYPE
M04B_ISSUE_SEVERITY
M04B_DOWNSTREAM_POLICY
```

`M04B_CLAIM_TYPE`：

```text
technical_hard
technical_experience_mixed
experience_scenario
service
value
unknown
```

`M04B_ISSUE_TYPE`：

```text
comment_only
spec_claimed_by_comment
service_mismatch
comment_contradiction
weak_perception
missing_structured_claim_enhanced
param_only_core_claim
promo_only_param_missing
value_requires_market_validation
low_quality_comment_signal
```

### 7.4 schema 校验规则

| 对象 | 校验 |
| --- | --- |
| `M04bRunRequest` | `project_id/category_code/batch_id` 非空，`claim_scope` 可为空 |
| `M04bClaimBaseInput` | `claim_code` 必须 `CLAIM_*`，分数字段 0-1 |
| `M04bClaimValidationSignalInput` | `signal_type` 必须是 `claim_validation` |
| `ClaimCommentValidationRecord` | `comment_effect` 和 `perception_status` 合法 |
| `SkuClaimActivationRecord` | `final_activation_score` 0-1，basis/level/flags 一致 |
| `ClaimCommentReviewIssueRecord` | `business_note` 和 `suggested_action` 必填 |

### 7.5 一致性规则

必须在 schema 或 service 中校验：

| 规则 | 处理 |
| --- | --- |
| `comment_only_flag=true` 且 `activation_level='high'` | 校验失败 |
| `param_only_flag=true` 且自动 `activation_level='high'` | 校验失败，除非人工 approved |
| `service_guardrail_flag=true` 且产品 claim 增强 | blocked |
| `hard_spec_protection_flag=true` 且 `activation_basis='comment_enhanced'` 试图补硬规格 | review/block |
| `value_requires_market_validation=true` 但下游策略未提示 M13 | 校验失败 |
| `missing_structured_claim_flag=true` 但 M15 策略未提示数据缺口 | 校验失败 |

## 8. repository 任务

### 8.1 Repository 文件

新增：

```text
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_repositories.py
```

### 8.2 Repository 类

```text
M04bClaimBaseRepository
M04bClaimValidationSignalRepository
SkuClaimCommentValidationRepository
SkuClaimActivationRepository
ClaimCommentReviewIssueRepository
ClaimCommentEnhancementReadRepository
```

### 8.3 `M04bClaimBaseRepository`

只读 M04a 输出。

方法：

| 方法 | 说明 |
| --- | --- |
| `assert_m04a_completed(project_id, category_code, batch_id)` | 检查 M04a 是否完成 |
| `list_claim_source_status(project_id, category_code, batch_id, sku_scope)` | 读取来源状态 |
| `list_claim_activation_base(project_id, category_code, batch_id, sku_scope, claim_scope)` | 读取基础卖点激活 |
| `get_base_hashes(project_id, category_code, batch_id, sku_code)` | 读取 M04a hash 用于 fingerprint |

限制：

- 不写 M04a 表。
- 不重新计算参数分或宣传分。

### 8.4 `M04bClaimValidationSignalRepository`

只读 M06 输出。

方法：

| 方法 | 说明 |
| --- | --- |
| `assert_m06_completed(project_id, category_code, batch_id)` | 检查 M06 是否完成 |
| `list_claim_validation_signals(project_id, category_code, batch_id, sku_scope, claim_scope)` | 只读 `signal_type='claim_validation'` |
| `list_candidate_phrases_for_signals(signal_ids, limit)` | 可选读取代表句级 candidate |
| `get_claim_validation_hashes(project_id, category_code, batch_id, sku_code)` | 读取 M06 signal hashes |

限制：

- 强制过滤 `signal_type='claim_validation'`。
- 不读取 M06 非 claim signals。
- 不读取 M05 topic hint。
- 不读取原始评论。

### 8.5 `SkuClaimCommentValidationRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_validations(records)` | 批量写评论验证聚合 |
| `list_current_validations(project_id, category_code, batch_id, sku_code, filters)` | 查询当前验证 |
| `get_validation(validation_id)` | API 查单条 |
| `mark_previous_inactive(project_id, category_code, batch_id, sku_code, rule_version)` | 版本切换 |

### 8.6 `SkuClaimActivationRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_activations(records)` | 批量写最终卖点激活 |
| `list_current_activations(project_id, category_code, batch_id, sku_code, filters)` | M08/API 读取 |
| `list_by_claim(project_id, category_code, batch_id, claim_code)` | 下游对比读取 |
| `get_activation(claim_activation_id)` | API 证据钻取 |
| `mark_previous_inactive(...)` | 版本切换 |

### 8.7 `ClaimCommentReviewIssueRepository`

方法：

| 方法 | 说明 |
| --- | --- |
| `bulk_upsert_issues(records)` | 批量写复核问题 |
| `list_open_issues(project_id, category_code, batch_id, filters)` | M16/API 读取 |
| `list_issues_for_claim(project_id, category_code, batch_id, sku_code, claim_code)` | 查某 SKU/claim 问题 |
| `update_issue_status(issue_id, status, reviewer)` | 后续 M16 可用 |
| `mark_resolved_by_new_run(...)` | 重跑后关闭旧问题 |

### 8.8 `ClaimCommentEnhancementReadRepository`

用于 API 聚合查询，不承载业务计算。

方法：

| 方法 | 说明 |
| --- | --- |
| `list_claim_activation_response(...)` | 返回业务化最终卖点激活 |
| `list_claim_comment_validation_response(...)` | 返回评论验证结果 |
| `get_claim_activation_evidence_response(...)` | 返回参数/宣传/评论证据 |
| `list_review_issue_response(...)` | 返回复核问题 |

### 8.9 Repository 测试要求

必须覆盖：

- 只读 M04a/M06，不读原始表。
- M06 查询强制过滤 `claim_validation`。
- M06 非 `claim_validation` 变化不触发 M04b。
- activation 只返回 current。
- validation、activation、issue 批量写入幂等。
- hash 变化时旧记录 inactive。
- API 可按 `param_only_flag`、`missing_structured_claim_flag`、`review_required` 过滤。

## 9. service 任务

### 9.1 `ClaimCommentSeedLoader`

职责：

1. 读取 TV seed 的 `standard_claims`。
2. 构建 `claim_code -> claim definition`。
3. 推断 M04b claim type。
4. 生成评论权重策略。
5. 生成 hard spec protection map。
6. 生成 service claim allowlist。
7. 输出 `seed_version` 和 seed hash。

必须覆盖的类型：

| M04b 类型 | 示例 |
| --- | --- |
| `technical_hard` | Mini LED、OLED、QLED、高亮、分区、HDMI2.1 |
| `technical_experience_mixed` | 高刷新率、低延迟、护眼、音效、智能语音 |
| `experience_scenario` | 大屏沉浸、体育运动流畅、长辈友好、超薄美学 |
| `service` | 安装服务保障 |
| `value` | 高性价比、节能省电 |

seed 缺失时：

- runner 返回 `blocked`。
- 不临时硬编码补 seed。
- 不生成最终激活。

### 9.2 `ClaimBaseInputService`

职责：

1. 校验 M04a 已完成。
2. 读取 `core3_sku_claim_source_status`。
3. 读取 `core3_sku_claim_activation_base`。
4. 按 SKU + claim 组装基础输入。
5. 计算 M04a 输入 hash。
6. 标记 `missing_structured_claim`、`param_only`、`promo_only` 等风险。

输入处理策略：

| 场景 | 处理 |
| --- | --- |
| M04a 未完成 | M04b blocked |
| M04a 无某 SKU 基础卖点 | 只允许 comment-only hint 进入复核 |
| `missing_structured_claim` | 输出 final 时保留 flag |
| `param_only` | 默认最高 medium，进入复核候选 |
| `promo_only` 且参数缺失 | 降置信并 review |
| M04a 基础冲突 | 继承 conflict flags |

### 9.3 `ClaimValidationSignalInputService`

职责：

1. 校验 M06 已完成或按降级策略处理。
2. 只读取 M06 `core3_comment_downstream_signal` 中 `signal_type='claim_validation'` 的记录。
3. 按 `sku_code + target_code_hint` 对齐 `claim_code`。
4. 可选读取 `core3_comment_signal_candidate` 选择代表评论短句。
5. 过滤 blocked/unknown/服务错配信号。
6. 计算 M06 输入 hash。

过滤规则：

| 条件 | 处理 |
| --- | --- |
| `target_code_hint` 不是 `CLAIM_*` | 忽略并 warning |
| `signal_level='blocked'` | 不增强，只生成 issue |
| `confidence_level='unknown'` | 降低验证置信度 |
| `service_guardrail_flag=true` 且 claim 不是服务型 | 阻断，生成 `service_mismatch` |
| `hard_spec_policy='experience_only'` | 只能作为体验验证 |
| M06 缺失 | final 继承 M04a，`insufficient_comment` |

### 9.4 `ClaimTypePolicyService`

职责：

1. 为 claim 判定 `m04b_claim_type`。
2. 返回基础分权重、评论权重、风险扣分上限和增强上限。
3. 返回 hard spec protection。
4. 返回 activation level 封顶。
5. 返回下游使用策略。

权重策略：

| 类型 | 基础权重 | 评论权重 | 风险扣分上限 | 备注 |
| --- | ---: | ---: | ---: | --- |
| `technical_hard` | 0.85 | 0.15 | 0.20 | 评论只增强体验置信 |
| `technical_experience_mixed` | 0.70 | 0.30 | 0.25 | 评论可验证体验 |
| `experience_scenario` | 0.55 | 0.45 | 0.30 | 评论影响较大 |
| `service` | 0.40 | 0.60 | 0.35 | 服务评论可作为核心证据 |
| `value` | 0.70 | 0.30 | 0.20 | 需市场验证 |

封顶规则：

| 条件 | 封顶 |
| --- | --- |
| `param_only` | 默认最高 medium |
| `comment_only_hint` | 最高 low 或 review_required |
| `missing_structured_claim` | 不能隐藏数据缺口 |
| `technical_hard` 无参数支撑 | blocked 或 review_required |
| `value` 评论强但无市场验证 | 不给商业高置信 |

### 9.5 `ClaimCommentValidationBuilder`

职责：

1. 对齐 M04a base claim 和 M06 claim_validation。
2. 为每个 SKU + claim 生成评论验证聚合。
3. 计算 domain match。
4. 计算 comment validation score。
5. 计算 comment risk score。
6. 判定 comment effect 和 perception status。
7. 生成代表评论短句。

评论验证分：

```text
comment_validation_score =
  0.30 * mention_rate_score
+ 0.25 * positive_rate_score
+ 0.20 * specificity_score
+ 0.15 * evidence_quality_score
+ 0.10 * domain_match_score
```

评论风险分：

```text
comment_risk_score =
  0.40 * negative_rate_score
+ 0.30 * risk_specificity_score
+ 0.20 * evidence_quality_score
+ 0.10 * repeated_issue_score
```

comment effect 判定：

| 条件 | `comment_effect` | `perception_status` |
| --- | --- | --- |
| 正向提及、具体程度和证据质量达标 | `enhance` | `validated` |
| 负向提及集中且对应同一体验 | `weaken` | `contradicted` |
| M04a 基础强但评论几乎无感知 | `neutral` | `weak_perception` |
| 评论与 M04a 方向冲突 | `contradict` | `contradicted` |
| 评论命中但无 M04a 基础候选 | `comment_only_hint` | `comment_only_pending` |
| 服务评论命中产品 claim | `blocked` | `service_guarded` |
| 评论不足或低置信 | `neutral` | `insufficient_comment` |

### 9.6 `ClaimActivationFinalScorer`

职责：

1. 按 claim type 计算最终激活分。
2. 应用风险扣分。
3. 应用 conflict penalty。
4. clamp 到 0-1。
5. 计算 activation level。
6. 计算 confidence 和 confidence level。
7. 生成 score breakdown JSON。

最终激活公式：

`technical_hard`：

```text
final_activation_score =
  base_activation_score * 0.85
+ comment_validation_score * 0.15
- comment_risk_score * 0.20
- conflict_penalty
```

`technical_experience_mixed`：

```text
final_activation_score =
  base_activation_score * 0.70
+ comment_validation_score * 0.30
- comment_risk_score * 0.25
- conflict_penalty
```

`experience_scenario`：

```text
final_activation_score =
  base_activation_score * 0.55
+ comment_validation_score * 0.45
- comment_risk_score * 0.30
- conflict_penalty
```

`service`：

```text
final_activation_score =
  base_activation_score * 0.40
+ comment_validation_score * 0.60
- comment_risk_score * 0.35
```

`value`：

```text
final_activation_score =
  base_activation_score * 0.70
+ comment_validation_score * 0.30
- comment_risk_score * 0.20
```

激活等级：

| 等级 | 条件 |
| --- | --- |
| `high` | 基础证据强、评论无冲突、非 param-only/comment-only、evidence 完整 |
| `medium` | 基础成立但存在缺口，或评论验证中等 |
| `low` | 单侧证据、评论弱、低置信或 comment-only hint |
| `unknown` | evidence 不足或冲突严重 |
| `review_required` | 影响下游核心判断但存在证据冲突或保护规则命中 |

最终置信度：

```text
confidence =
  0.35 * base_confidence
+ 0.20 * comment_confidence
+ 0.15 * evidence_completeness
+ 0.10 * source_status_score
+ 0.10 * domain_consistency_score
+ 0.10 * review_risk_inverse
```

### 9.7 `ClaimGuardrailService`

职责：

1. 应用 hard spec protection。
2. 阻断服务评论增强产品卖点。
3. 保留 param_only 和 missing_structured_claim 风险。
4. 识别 comment_only hint。
5. 识别 value requires market validation。
6. 生成 downstream usage policy。

保护规则：

| 条件 | 处理 |
| --- | --- |
| `technical_hard` 且无参数支撑 | 评论不能激活，生成 `spec_claimed_by_comment` |
| `hard_spec_policy='experience_only'` | 只能增强体验置信 |
| `service_guardrail_flag=true` 且非服务 claim | blocked |
| `activation_basis='param_only'` | 最高 medium，保留 `param_only_flag=true` |
| `claim_source_status='missing_structured_claim'` | 保留 `missing_structured_claim_flag=true` |
| `comment_only_hint` | 最高 low/review_required |
| 价值型评论强 | `value_requires_market_validation=true` |
| `promo_only` 且参数缺失 | 降置信并 review |

下游策略必须明确：

| 下游 | 策略 |
| --- | --- |
| M08 | 可作为 SKU claim signal，但保留 flags |
| M09/M10 | param_only/comment_only 不得单独高置信 |
| M11 | 战场仍需任务、客群、市场共同支撑 |
| M11.5 | 需要做卖点价值分层 |
| M13 | 必须保留证据风险 |
| M15 | 展示评论为体验验证，不展示为硬规格证明 |

### 9.8 `ClaimCommentReviewPolicy`

warning 条件：

| 条件 | warning |
| --- | --- |
| `claim_source_status='missing_structured_claim'` | 结构化卖点缺失，报告需提示 |
| `activation_basis='param_only'` | 参数-only，不可当完整宣传卖点 |
| `activation_basis='promo_only'` 且参数缺失 | 宣传缺参数支撑 |
| 评论验证样本不足 | 评论不改变基础激活 |
| 价值型评论强 | 需 M07/M13 市场验证 |
| 评论验证弱但基础激活强 | 弱感知候选 |

review 条件：

| 条件 | issue_type |
| --- | --- |
| 评论单独命中某卖点但 M04a 无基础候选 | `comment_only` |
| 技术规格被评论信号单独支撑 | `spec_claimed_by_comment` |
| 服务评论被映射到产品卖点 | `service_mismatch` |
| M04a 基础强但评论负向集中 | `comment_contradiction` |
| 宣传强但评论很弱 | `weak_perception` |
| `param_only` 卖点影响核心竞品选择 | `param_only_core_claim` |
| 重点 SKU 缺结构化卖点但评论增强强 | `missing_structured_claim_enhanced` |
| 价值型卖点评论强但缺市场验证 | `value_requires_market_validation` |
| 低质量评论信号影响最终分 | `low_quality_comment_signal` |

blocked 条件：

| 条件 | 处理 |
| --- | --- |
| M04a 未完成 | M04b blocked |
| seed 无法加载 | M04b blocked |
| 服务评论增强产品卖点 | 对该 claim blocked |
| 评论-only 试图激活技术硬规格 | 对该 claim blocked |
| evidence 追溯链断裂 | review_required 或 blocked |
| 输出写入失败 | M04b failed |

### 9.9 `ClaimCommentEnhancementService`

主流程：

```text
load standard_claims seed
load M04a base claims and source status
load M06 claim_validation signals
check reusable by input_fingerprint
build claim type policy
build comment validation records
score final activations
apply guardrails
build review issues
mark previous records inactive
upsert validation/activation/issues
return M04bRunResult and downstream impacts
```

幂等规则：

| 情况 | 动作 |
| --- | --- |
| fingerprint 未变且未 force | 跳过 |
| fingerprint 未变但 `force=true` | 重算 |
| validation result hash 未变 | 复用当前记录 |
| activation result hash 未变 | 复用当前记录 |
| issue hash 未变 | 复用当前记录 |
| hash 变化 | 旧记录 `is_current=false`，插入新记录 |
| claim 不再有基础或评论来源 | 旧记录 inactive |

### 9.10 下游影响登记

M04b 不直接调用下游，只返回影响范围：

| M04b 输出变化 | 下游影响 |
| --- | --- |
| final score/level 变化 | M08、M09、M10、M11、M11.5、M12-M16 |
| activation_basis 变化 | M08-M16 |
| perception_status 变化 | M08、M11、M13、M15、M16 |
| representative_phrases 变化 | M15、M16 |
| review_issue 变化 | M16，必要时阻断 M08-M15 |
| missing_structured_claim_flag 变化 | M08、M15、M16 |
| value_requires_market_validation 变化 | M11.5、M13、M15、M16 |

## 10. runner/API 任务

### 10.1 Runner 入口

新增：

```text
run_core3_m04b_claim_comment_enhancement(
  project_id: str,
  category_code: str,
  batch_id: str,
  sku_scope: list[str] | None,
  claim_scope: list[str] | None,
  force: bool = False,
  run_id: str | None = None
) -> M04bRunResult
```

### 10.2 Runner 返回

```json
{
  "module": "M04b",
  "status": "completed_with_warning",
  "processed_sku_count": 35,
  "changed_sku_codes": ["TV00029115"],
  "changed_claim_count": 18,
  "review_required_count": 6,
  "blocked_claim_count": 1,
  "downstream_impacts": [
    {"sku_code": "TV00029115", "next_modules": ["M08", "M09", "M11", "M11_5", "M13", "M15"]}
  ],
  "metrics": {
    "validation_count": 420,
    "final_activation_count": 510,
    "issue_count": 32
  }
}
```

状态规则：

| 条件 | status |
| --- | --- |
| 全部 SKU/claim 成功且无 warning | `completed` |
| 有 warning 或 review | `completed_with_warning` |
| 部分 claim blocked | `partial_blocked` |
| M04a/seed 缺失导致无法运行 | `blocked` |
| 写库失败 | `failed` |

### 10.3 API

在 `apps/api-server/app/api/core3_real_data.py` 增加：

| API | 用途 |
| --- | --- |
| `POST /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/run-m04b-claim-comment-enhancement` | 手动运行 M04b |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/claim-activations` | 查询 SKU 最终卖点激活 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/claim-comment-validations` | 查询评论验证聚合 |
| `GET /api/mvp/core3/v2/projects/{project_id}/claim-activations/{claim_activation_id}/evidence` | 查询参数/宣传/评论证据 |
| `GET /api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claim-comment-review-issues` | 查看 M04b 复核问题 |

### 10.4 API 边界

API 可以返回：

- 最终卖点激活分和等级。
- 参数分、宣传分、评论验证分、评论风险分。
- 结构化卖点缺失、param-only、comment-only、弱感知、冲突等风险。
- 评论代表短句。
- 参数、宣传、评论 evidence ID。
- 业务化说明。

API 不得返回：

- 最终用户任务分。
- 最终目标客群分。
- 最终价值战场分。
- 核心竞品选择。
- 竞品评分。
- 战场内卖点价值层级。
- “评论证明硬规格”的文案。
- prompt、模型过程或 AI 话术。

### 10.5 API filters

`claim-activations` 支持：

```text
claim_code
activation_level
activation_basis
perception_status
missing_structured_claim_flag
param_only_flag
comment_only_flag
review_required
limit
offset
```

`claim-comment-validations` 支持：

```text
claim_code
comment_effect
perception_status
service_guardrail_flag
hard_spec_protection_flag
limit
offset
```

`claim-comment-review-issues` 支持：

```text
sku_code
claim_code
issue_type
severity
issue_status
limit
offset
```

### 10.6 API 测试

必须覆盖：

- run API 返回 M04b runner status。
- claim activations API 返回最终激活和风险 flags。
- validations API 明确评论只是体验验证。
- evidence API 返回参数、宣传、评论分层 evidence。
- review issues API 可过滤 issue type。
- response 不包含任务、客群、战场、竞品结论。
- 85E7Q response 明确“缺结构化宣传卖点数据”。

## 11. 测试任务

### 11.1 seed loader 测试

`test_m04b_seed_loader.py`：

| 场景 | 期望 |
| --- | --- |
| seed 正常 | 加载 `standard_claims` |
| 缺 `standard_claims` | blocked |
| claim 缺 code/name/group | 校验失败 |
| 技术硬规格 claim | 映射到 `technical_hard` |
| 服务 claim | 映射到 `service` |
| 价值 claim | 映射到 `value` |
| seed hash | 内容变化 hash 变化 |

### 11.2 base input 测试

`test_m04b_base_input_service.py`：

| 场景 | 期望 |
| --- | --- |
| M04a 完成 | 正常读取 base 和 source status |
| M04a 未完成 | M04b blocked |
| `missing_structured_claim` | 输入保留 status |
| `param_only` | 输入保留 basis |
| `promo_only` 参数缺失 | 标记 review 候选 |
| 基础 conflict | 继承 conflict flags |

### 11.3 claim validation signal input 测试

`test_m04b_claim_validation_signal_input.py`：

| 场景 | 期望 |
| --- | --- |
| M06 claim_validation | 正常读取 |
| M06 `task_cue` | 不读取 |
| M06 `battlefield_support` | 不读取 |
| `target_code_hint` 非 `CLAIM_*` | 忽略并 warning |
| service guardrail + 产品 claim | 阻断 |
| hard spec policy | 只作为体验验证 |
| M06 缺失 | 继承 M04a，`insufficient_comment` |

### 11.4 claim type policy 测试

`test_m04b_claim_type_policy.py`：

| claim | 期望 |
| --- | --- |
| `CLAIM_MINI_LED_BACKLIGHT` | `technical_hard` |
| `CLAIM_HIGH_BRIGHTNESS_HDR` | `technical_hard` |
| `CLAIM_FINE_LOCAL_DIMMING` | `technical_hard` |
| `CLAIM_HDMI_2_1_GAMING` | `technical_hard` |
| `CLAIM_HIGH_REFRESH_RATE` | `technical_experience_mixed` |
| `CLAIM_EYE_CARE_COMFORT` | `technical_experience_mixed` |
| `CLAIM_LARGE_SCREEN_IMMERSION` | `experience_scenario` |
| `CLAIM_SPORTS_MOTION_SMOOTH` | `experience_scenario` |
| `CLAIM_VALUE_FOR_MONEY` | `value` |
| `CLAIM_INSTALLATION_SERVICE_ASSURANCE` | `service` |

### 11.5 comment validation builder 测试

`test_m04b_comment_validation_builder.py`：

| 场景 | 期望 |
| --- | --- |
| 正向评论充足 | `comment_effect='enhance'` |
| 负向评论集中 | `comment_effect='weaken'` |
| 基础强但评论弱 | `weak_perception` |
| 评论和基础冲突 | `contradict` |
| 有评论无基础 | `comment_only_hint` |
| 服务评论命中产品 claim | `blocked` + `service_guarded` |
| 无评论 | `insufficient_comment` |

### 11.6 final scorer 测试

`test_m04b_final_scorer.py`：

| 场景 | 期望 |
| --- | --- |
| technical_hard | 使用 0.85/0.15 权重 |
| technical_experience_mixed | 使用 0.70/0.30 权重 |
| experience_scenario | 使用 0.55/0.45 权重 |
| service | 使用 0.40/0.60 权重 |
| value | 使用 0.70/0.30 权重 |
| comment risk 高 | 扣减 final score |
| score 越界 | clamp 到 0-1 |
| confidence | flags 会降置信 |

### 11.7 guardrail 测试

`test_m04b_guardrail_service.py`：

| 场景 | 期望 |
| --- | --- |
| `param_only` | 自动最高 medium |
| `comment_only_hint` | 最高 low/review_required |
| `technical_hard` 无参数支撑 | blocked/review |
| 服务评论增强产品 claim | blocked |
| 价值评论强 | `value_requires_market_validation=true` |
| `missing_structured_claim` | M15 policy 展示数据缺口 |
| promo_only 参数缺失 | review |

### 11.8 review policy 测试

`test_m04b_review_policy.py`：

| 条件 | 期望 |
| --- | --- |
| comment-only | `comment_only` issue |
| 评论证明硬规格 | `spec_claimed_by_comment` issue |
| 服务错配 | `service_mismatch` issue |
| 基础强但负评集中 | `comment_contradiction` issue |
| 宣传强但感知弱 | `weak_perception` issue |
| param_only 影响核心判断 | `param_only_core_claim` issue |
| 85E7Q 缺卖点但评论增强强 | `missing_structured_claim_enhanced` issue |
| 价值评论强无市场 | `value_requires_market_validation` issue |

### 11.9 repository 测试

`test_m04b_repositories.py`：

| 场景 | 期望 |
| --- | --- |
| bulk insert validation | 成功 |
| bulk insert activation | 成功 |
| bulk insert issues | 成功 |
| hash 未变 | 幂等 |
| hash 变化 | 旧记录 inactive |
| M06 非 claim signal | 不被读取 |
| current 查询 | 只返回当前版本 |
| evidence 查询 | 参数/宣传/评论分层返回 |

### 11.10 runner 测试

`test_m04b_runner.py`：

| 场景 | 期望 |
| --- | --- |
| 正常 SKU | 输出 validation、activation、issue |
| `claim_scope` | 只处理指定 claim |
| fingerprint 未变 | 跳过重算 |
| `force=true` | 强制重算 |
| M04a 缺失 | blocked |
| M06 缺失 | 继承 M04a 或 warning |
| 返回 downstream impacts | M08-M16 |

### 11.11 API 测试

`test_m04b_api.py`：

| API | 期望 |
| --- | --- |
| run M04b | 返回 runner status |
| claim activations | 返回最终卖点激活 |
| validations | 返回评论验证聚合 |
| evidence | 返回分层证据 |
| review issues | 支持 issue type 过滤 |
| 越界字段 | 不返回任务、客群、战场、竞品结论 |

### 11.12 越界测试

`test_m04b_no_business_outputs.py` 必须验证：

- M04b 不读取原始 `comment_data`。
- M04b 不读取 M05 `core3_comment_topic_hint`。
- M04b 不消费 M06 非 `claim_validation` 信号。
- M04b 不读取市场量价。
- M04b 不输出最终任务分。
- M04b 不输出最终客群分。
- M04b 不输出最终战场分。
- M04b 不输出竞品候选、竞品评分或核心三竞品选择。
- 服务评论不能增强产品卖点。
- 评论不能证明 nits、分区数、端口数、原生刷新率、芯片、内存、认证等硬规格。
- 评论不能补造 `promo_evidence_ids`。

### 11.13 85E7Q fixture 测试

`test_m04b_85e7q_fixture.py`：

| 数据事实 | 验收 |
| --- | --- |
| 85E7Q 无结构化卖点 | `missing_structured_claim_flag=true` |
| M04a 输出技术型 `param_only` 候选 | M04b 保留 `param_only_flag=true` |
| 画质正向评论 | 可增强画质体验，不证明 5200 nits/3500 分区 |
| 看球流畅评论 | 可增强体育运动流畅，不证明原生刷新率 |
| 智能语音评论 | 可增强智能易用，不证明芯片/内存 |
| 安装服务评论 | 只增强 `CLAIM_INSTALLATION_SERVICE_ASSURANCE` |
| 性价比评论 | `value_requires_market_validation=true` |
| 最终输出 | 不生成伪造宣传 evidence，不把评论补成结构化卖点 |

## 12. 205/85E7Q 验收

### 12.1 全量样例验收

当前 205 样例约束：

| 指标 | 基线 | M04b 验收 |
| --- | ---: | --- |
| `selling_points_data` 覆盖型号 | 5 个型号 | 支持大量 SKU `missing_structured_claim` |
| 85E7Q 评论行 | 3621 | 只通过 M06 聚合信号消费，不直接读原始评论 |
| 85E7Q 去重评论 ID | 1648 | 只使用 M06 mention 分母 |
| 服务安装评论 | 占比较高 | 只影响服务 claim |
| 低价值/重复评论 | 存在 | 由 M06 降权后进入 M04b |

全量预期：

- 有 M04a 基础激活的 SKU/claim 生成最终 `core3_sku_claim_activation`。
- 有评论信号但无 M04a 基础候选的 SKU/claim 只生成 `comment_only_hint` 和复核问题。
- 服务安装评论只影响服务型 claim。
- 价值型评论不直接转成价格竞争结论。
- final activation 保留参数、宣传、评论三类 evidence。

### 12.2 85E7Q 验收

85E7Q `model_code=TV00029115`：

| 数据事实 | M04b 处理 |
| --- | --- |
| 无结构化卖点 | `missing_structured_claim_flag=true` |
| M04a 基于参数输出 Mini LED、高亮、分区、高刷、HDMI 等候选 | 保留 `param_only_flag=true`，评论只增强体验侧 |
| 评论“画面清晰、色彩好、细节好” | 增强画质体验相关 claim，不证明 5200 nits 或 3500 分区 |
| 评论“看球不卡、运动画面顺” | 增强体育运动流畅体验，不证明原生刷新率 |
| 评论“语音控制方便、运行流畅” | 增强智能/易用体验，不证明芯片或内存 |
| 评论“安装快、师傅专业” | 只增强 `CLAIM_INSTALLATION_SERVICE_ASSURANCE` |
| 评论“性价比高、买得值” | 价值感增强，但 `value_requires_market_validation=true` |

85E7Q 最终报告需要能说明：

```text
该 SKU 的部分核心卖点来自参数基础和评论体验验证，当前缺结构化宣传卖点数据，因此不能把评论当成宣传证据或硬规格证据。
```

### 12.3 不达标处理

| 现象 | 处理 |
| --- | --- |
| 85E7Q 评论被写入 `promo_evidence_ids` | 测试失败 |
| 85E7Q `missing_structured_claim_flag=false` | 测试失败 |
| 85E7Q param_only 自动 high | 测试失败，除非人工 approved |
| 画质评论证明 nits 或分区 | 测试失败 |
| 安装服务增强画质/游戏 claim | 测试失败 |
| comment-only 技术 claim 高置信 | 测试失败 |
| API 返回竞品结论 | 越界测试失败 |

## 13. 完成标准

编码任务完成时必须满足：

1. `0013_core3_real_data_claim_comment_enhancement.py` 可升级、可回滚。
2. 3 张 M04b 输出表字段、主键、唯一键、索引、JSONB 字段与详细设计一致。
3. M04b 默认只读 M04a、M06 `claim_validation` 和 `standard_claims` seed。
4. M04b 不直接读取原始 `comment_data`。
5. M04b 不直接读取 M05 topic hint。
6. M04b 不消费 M06 非 `claim_validation` 信号。
7. M04b 可输出 `core3_sku_claim_comment_validation`。
8. M04b 可输出 `core3_sku_claim_activation`。
9. M04b 可输出 `core3_claim_comment_review_issue`。
10. 技术硬规格、技术体验、体验场景、服务、价值型卖点使用不同权重。
11. 评论不能证明硬规格。
12. 服务评论不能增强产品卖点。
13. `param_only` 默认最高 medium。
14. `comment_only_hint` 最高 low/review_required。
15. `missing_structured_claim` 不被隐藏。
16. 价值型评论强时标记 `value_requires_market_validation`。
17. final activation 保留参数、宣传、评论 evidence IDs。
18. 85E7Q 保留 `missing_structured_claim` 和 `param_only` 风险。
19. M04a/M06/seed 变化能触发正确下游影响范围。
20. warning/review/block 条件可落入 M16 所需字段。
21. M04b 不输出任务、客群、战场或竞品结论。
22. 所有 M04b 单元、集成、边界、越界、85E7Q fixture 测试通过。

建议测试命令：

```bash
cd apps/api-server && .venv/bin/pytest tests/core3_real_data/test_m04b_*.py
```

如项目当前测试命令不同，以仓库实际配置为准，但必须能单独运行 M04b 测试。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 评论被当成宣传证据 | 证据链失真 | 禁止写入伪造 `promo_evidence_ids` |
| 评论证明硬规格 | 业务误导 | hard spec protection 和越界测试 |
| 服务评论增强产品卖点 | 竞品理由失真 | service guardrail 和 blocked issue |
| param_only 被自动 high | 误导下游 | 默认 highest medium，人工 approved 才能突破 |
| comment-only 技术 claim 高置信 | 无基础证据 | `comment_only_hint` 最高 low/review |
| 价值评论替代价格事实 | 价格竞争判断错误 | `value_requires_market_validation` |
| M04b 消费 M06 非 claim 信号 | 模块边界混乱 | repository 强制过滤 |
| M04b 直接读 M05 topic | 绕过专用信号层 | 越界测试 |
| M04b 输出任务/战场/竞品结论 | 方法论越界 | API/schema 测试 |
| 85E7Q 缺卖点被隐藏 | 高层报告误导 | `missing_structured_claim_flag` 和 M15 策略 |

回滚方式：

1. Alembic downgrade 删除 M04b 3 张输出表。
2. 移除 M04b API router 注册。
3. 移除 M04b runner 注册。
4. 不影响 M00-M06 产物。
5. 不影响旧 `core3_mvp` 页面。

## 15. 下游依赖

| 下游模块 | 依赖 M04b 的内容 |
| --- | --- |
| M08 | 消费 `core3_sku_claim_activation`，作为 SKU 综合画像的一部分 |
| M09 | 使用最终卖点激活推导任务，但必须读取 `activation_basis` |
| M10 | 使用最终卖点激活推导客群，但不能忽略风险 flags |
| M11 | 使用最终卖点激活判断战场语义支撑 |
| M11.5 | 使用最终卖点激活、市场和评论感知做战场内卖点价值分层 |
| M12-M14 | 使用最终卖点激活参与召回/评分/选择，同时读取风险字段 |
| M15 | 展示卖点证据、评论体验验证和数据缺口 |
| M16 | 使用 issue、review、impact 信息生成复核和增量计划 |

M04b 给下游的边界承诺：

| 下游 | 承诺 |
| --- | --- |
| M08 | 能区分参数支撑、宣传支撑、评论验证和证据缺口 |
| M09/M10 | `comment_only_hint` 不得单独支撑高置信任务或客群 |
| M09/M10 | `param_only` 默认最高中置信 |
| M11 | 战场仍需任务、客群、卖点、市场共同支撑 |
| M11.5 | M04b 不输出价值层级，必须继续分层 |
| M13 | 评论验证不能替代参数和市场证据 |
| M15 | 评论可展示为体验验证，不可写成硬规格证明 |

正确链路：

```text
M04a 基础卖点激活
+ M06 claim_validation
-> M04b 最终卖点激活
-> M08/M09/M10/M11/M11.5/M12-M15
```

明确禁止：

```text
M04b comment_validation -> 硬规格证明
M04b service comment -> 产品卖点增强
M04b final activation -> 最终任务/客群/战场结论
M04b final activation -> 核心竞品选择
M04b comment-only -> 高置信技术卖点
M04b param-only -> 自动高置信完整卖点
```

## 16. 编码子任务建议

如果正式编码继续按小任务执行，建议拆为：

| 子任务 | 内容 | 完成标准 |
| --- | --- | --- |
| M04b-A | Alembic 迁移 | 3 表、索引、约束、回滚 |
| M04b-B | schema 和枚举 | typed contracts、API schema、枚举 |
| M04b-C | seed loader 和类型策略 | claim type、权重、hard spec、service allowlist |
| M04b-D | input service | 只读 M04a、M06 claim_validation、fingerprint |
| M04b-E | validation builder | 评论验证聚合、effect、perception status |
| M04b-F | final scorer | final score、activation level、confidence |
| M04b-G | guardrail service | hard spec、service、param_only、comment_only、value |
| M04b-H | review policy | issue 生成、downstream policy |
| M04b-I | repository | validation/activation/issues 幂等和 current |
| M04b-J | runner + API | 运行入口、查询 API、证据钻取 |
| M04b-K | tests + 85E7Q fixture | 单元、集成、越界、样例验收 |

每个子任务都应保持可测试，不建议在一个编码任务里一次性完成 M04b-A 到 M04b-K。

## 17. 下次任务

下一个开发任务文档：

```text
docs/core3_mvp/real_data_v2/development/M07_development_tasks.md
```

M07 需要基于清洗后的周销、价格、渠道和可比池口径生成 SKU 市场画像，为 M08、M11.5、M12、M13 提供价格带、销量、销售额、渠道平台和可比池基线。M07 不能与评论、卖点逻辑混在一起，也不能用评论替代真实市场事实。
