# M08 SKU 综合信号画像开发任务

## 1. 模块目标

M08 的开发目标是把 M03 参数画像、M04b 最终卖点激活、M06 评论下游信号、M07 市场画像与可比池基线装配成 SKU 级统一信号画像，作为 M09-M15 的默认特征入口。

M08 要解决的工程问题：

1. 下游模块不再各自回读参数、卖点、评论、市场散表，而是优先消费统一 SKU 画像。
2. 每个 SKU 的主数据、参数、卖点、评论、市场、可比池、证据、缺失和风险集中表达。
3. 对 85E7Q 这类“参数强、评论多、市场有、结构化卖点缺失”的 SKU，画像必须同时表达强项和证据缺口。
4. 为 M09、M10、M11、M11.5、M12、M13、M14、M15 生成裁剪后的下游特征视图，避免下游重新拼装口径。
5. 用 `profile_hash`、`view_hash` 和 `input_fingerprint` 支撑增量重算，只有画像或下游视图变化才触发后续模块。
6. 输出证据矩阵，让下游和报告能判断每个推断是否有足够证据、哪些域缺失、哪些域需要复核。

M08 必须固化以下边界：

- M08 是统一特征装配层，不是业务结论层。
- M08 不读取原始 `week_sales_data`、`attribute_data`、`selling_points_data`、`comment_data`。
- M08 不重新抽取参数。
- M08 不重新激活卖点。
- M08 不重新解析评论。
- M08 不重新计算市场画像或可比池。
- M08 不生成最终用户任务、目标客群、价值战场、卖点价值层级、候选 SKU、竞品评分或核心三竞品。
- M08 不把数据缺失解释为业务能力弱。缺失只表示证据缺口或样本不足。
- M08 不把 `unknown`、空值、`-` 当成 false。
- M08 不伪造 85E7Q 的结构化卖点证据。
- M08 不输出 12 月口径字段。当前市场窗口仍是 `26W01-26W23` 观测周。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M08 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M08_sku_signal_profile_requirements.md` |
| M08 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M08_sku_signal_profile_design.md` |
| 总体架构和数据字典 | `docs/core3_mvp/real_data_v2/sop_detailed_design/00_architecture_data_dictionary_design.md` |
| M03 任务 | `docs/core3_mvp/real_data_v2/development/M03_development_tasks.md` |
| M04b 任务 | `docs/core3_mvp/real_data_v2/development/M04b_development_tasks.md` |
| M06 任务 | `docs/core3_mvp/real_data_v2/development/M06_development_tasks.md` |
| M07 任务 | `docs/core3_mvp/real_data_v2/development/M07_development_tasks.md` |
| M03 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| M04b 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M04b_claim_comment_enhancement_design.md` |
| M06 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M06_comment_downstream_signal_design.md` |
| M07 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M07_market_profile_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| SOP 参考模块 | `cankao/catforge_sop_md/modules/M08_SKU 综合信号画像.md` |

编码前必须确认：

- M03 已能输出 `core3_extract_param_value`、`core3_sku_param_profile`。
- M04b 已能输出 `core3_sku_claim_activation`、`core3_sku_claim_comment_validation`。
- M06 已能输出 `core3_sku_comment_signal_profile`、`core3_comment_downstream_signal`。
- M07 已能输出 `core3_sku_market_profile`、`core3_market_signal`、`core3_comparable_pool_baseline`、`core3_market_pool_member`。
- M02 evidence 可用，且 M03-M07 输出中保留 evidence ID 或 source record refs。
- INFRA 已提供 run context、hash 工具、runner 协议、复核 issue schema、下游影响结构和 current 版本约定。

## 3. 本次范围

本次开发任务拆分覆盖 M08 的后端实现准备：

| 范围 | 说明 |
| --- | --- |
| 数据迁移 | 新增 3 张 M08 输出表 |
| model/schema | 新增 SKU 画像、证据矩阵、下游视图、runner、API、复核和增量 schema |
| repository | 只读 M01/M02/M03/M04b/M06/M07，写 M08 输出 |
| SKU universe | 以 M01 为主，合并 M03/M04b/M06/M07 中额外出现的 SKU |
| input loader | 读取各上游 current 记录、hash、版本、状态和代表证据 |
| contract validator | 校验上游唯一 current、feature_version、hash、状态和 evidence 可回溯 |
| domain assembler | 装配主数据、参数、卖点、评论、市场、可比池、质量风险 |
| evidence matrix | 生成分域证据覆盖、缺失、风险和代表 evidence |
| completeness/confidence | 计算完整度、置信度、profile_status |
| risk evaluator | 统一风险码、缺失码和复核原因 |
| downstream view builder | 生成 M09-M15 的裁剪特征视图 |
| invalidation | profile/view hash 变化时登记 M09-M16 下游影响 |
| runner/API | 运行入口、画像查询、证据矩阵查询、feature view 查询 |
| 测试 | 单元、集成、边界、越界、85E7Q fixture |

本次不做：

- 不实现 M09 用户任务。
- 不实现 M10 目标客群。
- 不实现 M11 价值战场。
- 不实现 M11.5 战场内卖点价值分层。
- 不实现 M12 候选池召回。
- 不实现 M13 竞品组件评分。
- 不实现 M14 三槽位选择。
- 不实现 M15 高层报告。
- 不实现前端页面。
- 不部署到 205。
- 不让 M08 API 直接给高层页面展示内部 JSON 字段名。

## 4. 要改文件

### 4.1 新增后端服务文件

```text
apps/api-server/app/services/core3_real_data/sku_signal_profile_schemas.py
apps/api-server/app/services/core3_real_data/sku_signal_profile_repositories.py
apps/api-server/app/services/core3_real_data/sku_universe_builder.py
apps/api-server/app/services/core3_real_data/sku_signal_input_loader.py
apps/api-server/app/services/core3_real_data/sku_signal_contract_validator.py
apps/api-server/app/services/core3_real_data/sku_master_domain_assembler.py
apps/api-server/app/services/core3_real_data/param_domain_assembler.py
apps/api-server/app/services/core3_real_data/claim_domain_assembler.py
apps/api-server/app/services/core3_real_data/comment_domain_assembler.py
apps/api-server/app/services/core3_real_data/market_domain_assembler.py
apps/api-server/app/services/core3_real_data/pool_domain_assembler.py
apps/api-server/app/services/core3_real_data/sku_signal_evidence_matrix_builder.py
apps/api-server/app/services/core3_real_data/sku_signal_completeness_calculator.py
apps/api-server/app/services/core3_real_data/sku_signal_risk_evaluator.py
apps/api-server/app/services/core3_real_data/sku_signal_confidence_calculator.py
apps/api-server/app/services/core3_real_data/downstream_feature_view_builder.py
apps/api-server/app/services/core3_real_data/sku_signal_invalidation_publisher.py
apps/api-server/app/services/core3_real_data/sku_signal_profile_service.py
apps/api-server/app/services/core3_real_data/sku_signal_profile_runner.py
```

文件职责：

| 文件 | 职责 |
| --- | --- |
| `sku_signal_profile_schemas.py` | M08 内部 typed contracts |
| `sku_signal_profile_repositories.py` | M08 输入读取和输出写入 |
| `sku_universe_builder.py` | 构建 SKU 画像全集 |
| `sku_signal_input_loader.py` | 读取 M01-M07 current 输入 |
| `sku_signal_contract_validator.py` | 校验上游唯一性、状态、hash、证据回溯 |
| `sku_master_domain_assembler.py` | 主数据和覆盖装配 |
| `param_domain_assembler.py` | 参数摘要和参数风险装配 |
| `claim_domain_assembler.py` | 最终卖点、证据拆分、结构化卖点缺口装配 |
| `comment_domain_assembler.py` | 七类评论信号和评论质量装配 |
| `market_domain_assembler.py` | 市场画像、窗口、信号装配 |
| `pool_domain_assembler.py` | 可比池摘要和池样本状态装配 |
| `sku_signal_evidence_matrix_builder.py` | 证据矩阵生成 |
| `sku_signal_completeness_calculator.py` | 分域完整度和整体完整度 |
| `sku_signal_risk_evaluator.py` | 风险、缺失、复核规则 |
| `sku_signal_confidence_calculator.py` | 画像置信度和状态判定 |
| `downstream_feature_view_builder.py` | M09-M15 裁剪视图 |
| `sku_signal_invalidation_publisher.py` | 下游重算影响登记 |
| `sku_signal_profile_service.py` | M08 编排 service |
| `sku_signal_profile_runner.py` | M08 runner 入口 |

### 4.2 允许修改的共享文件

```text
apps/api-server/alembic/versions/0015_core3_real_data_sku_signal_profile.py
apps/api-server/app/schemas/core3_real_data.py
apps/api-server/app/api/core3_real_data.py
apps/api-server/app/services/core3_real_data/constants.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/tests/core3_real_data/conftest.py
```

| 文件 | 允许改动 |
| --- | --- |
| `0015_core3_real_data_sku_signal_profile.py` | 新增 M08 3 张输出表 |
| `core3_real_data.py` schema | 导出 M08 API request/response |
| `core3_real_data.py` API | 增加 M08 运行、画像、证据矩阵、feature view 查询 API |
| `constants.py` | 补 M08 profile status、signal domain、coverage status、for_module 等枚举 |
| `runner.py` | 注册 M08 runner，不改变已有模块逻辑 |
| `conftest.py` | 增加 M08 M03/M04b/M06/M07 输入 fixture、85E7Q 画像 fixture |

如果 Alembic 当前最新编号不是 `0014`，M08 编码时按最新编号顺延，但 migration 内容仍只能包含 M08 表、索引、约束。

### 4.3 新增测试文件

```text
apps/api-server/tests/core3_real_data/test_m08_sku_universe_builder.py
apps/api-server/tests/core3_real_data/test_m08_input_loader.py
apps/api-server/tests/core3_real_data/test_m08_contract_validator.py
apps/api-server/tests/core3_real_data/test_m08_sku_master_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_param_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_claim_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_comment_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_market_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_pool_domain_assembler.py
apps/api-server/tests/core3_real_data/test_m08_evidence_matrix_builder.py
apps/api-server/tests/core3_real_data/test_m08_completeness_calculator.py
apps/api-server/tests/core3_real_data/test_m08_risk_evaluator.py
apps/api-server/tests/core3_real_data/test_m08_confidence_calculator.py
apps/api-server/tests/core3_real_data/test_m08_downstream_feature_view_builder.py
apps/api-server/tests/core3_real_data/test_m08_repositories.py
apps/api-server/tests/core3_real_data/test_m08_runner.py
apps/api-server/tests/core3_real_data/test_m08_api.py
apps/api-server/tests/core3_real_data/test_m08_no_business_outputs.py
apps/api-server/tests/core3_real_data/test_m08_85e7q_fixture.py
```

### 4.4 只读依赖文件

```text
apps/api-server/app/services/core3_real_data/param_extraction_repositories.py
apps/api-server/app/services/core3_real_data/param_extraction_schemas.py
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_repositories.py
apps/api-server/app/services/core3_real_data/claim_comment_enhancement_schemas.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_repositories.py
apps/api-server/app/services/core3_real_data/comment_downstream_signal_schemas.py
apps/api-server/app/services/core3_real_data/market_profile_repositories.py
apps/api-server/app/services/core3_real_data/market_profile_schemas.py
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
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
scripts/deploy.sh
```

不允许改动的业务对象：

- 原始四表结构。
- M00-M07 输出表结构。
- M03 参数解析逻辑。
- M04b 卖点激活逻辑。
- M06 评论信号抽取逻辑。
- M07 市场画像和可比池逻辑。
- M09-M16 结果表。
- 旧 `core3_mvp` 服务和页面。
- 前端高层报告页面。
- 205 部署配置。

不允许引入的行为：

- 直接读取原始四张业务表。
- 重新解析参数、评论或卖点。
- 重新计算市场分位、价格带或可比池。
- 输出最终 `task_code`、`target_group_code`、`battlefield_code`、`candidate_sku_code`、`component_score`、`competitor_role`、核心三竞品。
- 把 `missing_structured_claim` 改写成“无卖点”。
- 把 `unknown` 改写成 false。
- 把评论线索升级为最终任务、客群或战场。
- 把可比池成员升级为候选竞品。
- 输出 `12m` 市场字段。
- 在测试中调用外部 LLM。

## 6. 数据库迁移任务

### 6.1 迁移文件

新增迁移：

```text
apps/api-server/alembic/versions/0015_core3_real_data_sku_signal_profile.py
```

迁移只新增 M08 输出表，不修改 M00-M07 表，不修改旧 MVP 表。

### 6.2 新增表

| 表 | 粒度 | 说明 |
| --- | --- | --- |
| `core3_sku_signal_profile` | SKU + 画像范围 + 特征版本 | SKU 统一信号画像 |
| `core3_sku_signal_evidence_matrix` | SKU 画像 + 证据域 + 子域 | 证据覆盖、缺失、风险和代表 evidence |
| `core3_sku_downstream_feature_view` | SKU 画像 + 下游模块 + 视图角色 | M09-M15 裁剪特征视图 |

### 6.3 通用字段

3 张表必须包含：

```text
project_id
category_code
batch_id
run_id
module_run_id
rule_version
feature_version
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
- `rule_version` 首版建议 `m08_sku_signal_profile_v1`。
- `feature_version` 首版建议 `core3_mvp_real_data_v2_m08_v1`。
- 历史版本不删除，旧记录通过 `is_current=false` 失效。
- current 唯一性必须通过部分唯一索引保证。

### 6.4 `core3_sku_signal_profile`

必须字段：

```text
sku_signal_profile_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_code
model_name
brand_name
profile_scope
analysis_window
source_coverage_json
source_profile_refs_json
sku_master_json
core_params_json
param_profile_json
claim_activation_summary_json
claim_evidence_breakdown_json
comment_signal_summary_json
comment_quality_json
market_summary_json
market_recent_windows_json
market_signal_summary_json
comparable_pool_summary_json
business_signal_index_json
missing_signals_json
risk_signals_json
domain_completeness_json
data_completeness_score
domain_confidence_json
confidence
confidence_level
profile_status
downstream_ready_json
evidence_summary_json
representative_evidence_ids
input_fingerprint
profile_hash
result_hash
rule_version
feature_version
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
| 主键 | `sku_signal_profile_id` |
| 唯一键 | `project_id, category_code, batch_id, sku_code, profile_scope, feature_version, profile_hash` |
| current 唯一索引 | `project_id, category_code, batch_id, sku_code, profile_scope, feature_version where is_current=true` |
| 普通索引 | `project_id, category_code, batch_id, sku_code` |
| 普通索引 | `project_id, category_code, batch_id, profile_status, review_required` |
| 普通索引 | `project_id, category_code, batch_id, profile_hash` |
| GIN 索引 | `business_signal_index_json` |
| GIN 索引 | `risk_signals_json`、`missing_signals_json` |

### 6.5 `core3_sku_signal_evidence_matrix`

必须字段：

```text
sku_signal_evidence_matrix_id
sku_signal_profile_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
domain
sub_domain
feature_code
evidence_role
coverage_status
evidence_count
high_confidence_count
medium_confidence_count
low_confidence_count
representative_evidence_ids
evidence_query_json
source_record_refs_json
missing_flag
missing_reason_code
risk_flags_json
domain_confidence
review_required
review_reason_json
rule_version
feature_version
input_fingerprint
result_hash
is_current
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `sku_signal_evidence_matrix_id` |
| 唯一键 | `sku_signal_profile_id, domain, sub_domain, evidence_role, feature_version` |
| 普通索引 | `sku_signal_profile_id, domain, sub_domain` |
| 普通索引 | `project_id, category_code, batch_id, sku_code, domain` |
| 普通索引 | `project_id, category_code, batch_id, missing_flag, review_required` |
| GIN 索引 | `representative_evidence_ids` |
| GIN 索引 | `risk_flags_json` |

最低矩阵行要求：

| domain | sub_domain |
| --- | --- |
| `sku_master` | `identity` |
| `param` | `core_params` |
| `param` | `param_quality` |
| `claim` | `structured_claim` |
| `claim` | `final_claim_activation` |
| `claim_comment_validation` | `perception_validation` |
| `comment` | `claim_validation` |
| `comment` | `task_cue` |
| `comment` | `target_group_cue` |
| `comment` | `battlefield_support` |
| `comment` | `pain_point` |
| `comment` | `price_perception` |
| `comment` | `service_signal` |
| `market` | `price` |
| `market` | `sales` |
| `market` | `platform` |
| `market` | `trend` |
| `pool` | `same_size` |
| `pool` | `adjacent_size` |
| `pool` | `same_price_band` |
| `quality` | `profile_risk` |

缺失域也必须输出矩阵行，不能因为缺数据就不写。

### 6.6 `core3_sku_downstream_feature_view`

必须字段：

```text
sku_downstream_feature_view_id
sku_signal_profile_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
for_module
view_role
view_schema_version
required_feature_codes_json
optional_feature_codes_json
feature_payload_json
feature_quality_flags_json
required_missing_fields_json
optional_missing_fields_json
evidence_ids
evidence_matrix_refs_json
profile_hash
view_hash
dependency_hash_json
ready_for_module
block_reason_json
review_required
review_reason_json
rule_version
feature_version
input_fingerprint
result_hash
is_current
created_at
updated_at
```

键和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `sku_downstream_feature_view_id` |
| 唯一键 | `sku_signal_profile_id, for_module, view_role, view_schema_version, view_hash` |
| current 唯一索引 | `project_id, category_code, batch_id, sku_code, for_module, view_role, view_schema_version where is_current=true` |
| 普通索引 | `project_id, category_code, batch_id, for_module, ready_for_module` |
| 普通索引 | `project_id, category_code, batch_id, profile_hash, view_hash` |
| GIN 索引 | `feature_payload_json` |
| GIN 索引 | `required_missing_fields_json` |

MVP 必须生成：

```text
M09
M10
M11
M11_5
M12
M13
M14
M15
```

M16 视图可选，但 schema 必须预留。

### 6.7 downgrade 要求

`downgrade()` 只删除 M08 三张表和对应索引，不触碰 M00-M07、M09-M16、旧 MVP 表和原始四表。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

如果项目仍集中使用 `apps/api-server/app/models/entities.py`，则新增 M08 三张表 model；如果 INFRA 已拆 `core3_real_data` 独立 model 文件，则按 INFRA 约定放置。

model 要求：

- 字段名与 migration 一致。
- JSON 字段使用 PostgreSQL JSONB。
- ID 类型与项目现有风格一致；如 M08 详细设计使用 uuid，需与 INFRA ID 策略对齐。
- `representative_evidence_ids` 和 `evidence_ids` 使用 PostgreSQL array 或 JSONB，按项目现有迁移风格统一。
- 数值字段如 `confidence`、`data_completeness_score`、`domain_confidence` 使用 Numeric。
- current 唯一索引必须在 migration 中实现。

### 7.2 内部 schema

`sku_signal_profile_schemas.py` 必须定义：

```text
M08ProfileScope
M08ProfileStatus
M08SignalDomain
M08CoverageStatus
M08ForModule
M08ViewRole
M08ConfidenceLevel
M08DomainInputRefs
M08SkuUniverseItem
M08SkuSignalInputs
M08ContractValidationResult
M08DomainPayload
M08EvidenceMatrixRow
M08CompletenessResult
M08RiskSignal
M08ProfileRecord
M08DownstreamFeatureViewRecord
M08RunRequest
M08RunSummary
```

### 7.3 API schema

`apps/api-server/app/schemas/core3_real_data.py` 导出：

```text
Core3M08RunRequest
Core3M08RunResponse
Core3SkuSignalProfileListItem
Core3SkuSignalProfileResponse
Core3SkuSignalEvidenceMatrixResponse
Core3SkuDownstreamFeatureViewResponse
Core3M08RiskSignalResponse
```

API response 面向运营和下游联调，可以包含技术字段；面向高层页面的正式报告不能直接展示 M08 内部 JSON 字段名。

## 8. repository 任务

### 8.1 Repository 划分

`sku_signal_profile_repositories.py` 建议包含：

| Repository | 访问表 |
| --- | --- |
| `M08CleanSkuRepository` | 只读 M01 `core3_clean_sku` |
| `M08EvidenceRepository` | 只读 M02 `core3_evidence_atom` |
| `M08ParamRepository` | 只读 M03 `core3_extract_param_value`、`core3_sku_param_profile` |
| `M08ClaimRepository` | 只读 M04b `core3_sku_claim_activation`、`core3_sku_claim_comment_validation` |
| `M08CommentRepository` | 只读 M06 `core3_sku_comment_signal_profile`、`core3_comment_downstream_signal` |
| `M08MarketRepository` | 只读 M07 `core3_sku_market_profile`、`core3_market_signal`、`core3_comparable_pool_baseline`、`core3_market_pool_member` |
| `M08SkuSignalProfileRepository` | 写 `core3_sku_signal_profile` |
| `M08EvidenceMatrixRepository` | 写 `core3_sku_signal_evidence_matrix` |
| `M08DownstreamFeatureViewRepository` | 写 `core3_sku_downstream_feature_view` |

### 8.2 输入读取要求

读取规则：

1. 只读取当前 `project_id + category_code + batch_id`。
2. 默认只读取 `is_current=true` 的上游画像和抽取结果。
3. 读取 M03/M04b/M06/M07 的 hash、rule_version、feature_version、processing_status、review_required。
4. 对 `sku_scope` 内 SKU 运行时，仍要能读取必要的全局状态，例如当前批次 SKU universe 和 M07 可比池摘要。
5. 不直接读取 M05，除非 M06 profile 未包含评论质量字段且 M05 quality profile 已被设计为 M08 只读输入；首版优先要求 M06 `core3_sku_comment_signal_profile` 携带 M05 去重和质量口径。

### 8.3 写入要求

写入规则：

1. `profile_hash` 不变时不插入新业务版本。
2. `profile_hash` 变化时旧 profile 置为 `is_current=false`，插入新 profile。
3. profile 变化时重新写当前证据矩阵；旧矩阵置为非 current 或由新 profile ID 隔离。
4. 每个 `for_module` 的 `view_hash` 单独比较；只有该模块视图变化才登记该模块下游重算。
5. 同一 current 唯一键出现多条 current 时，runner 必须失败并生成 `source_profile_conflict`。

## 9. service 任务

### 9.1 `SkuUniverseBuilder`

SKU universe 使用以下并集：

1. M01 `core3_clean_sku` 当前批次有效 SKU。
2. M03 有参数画像但 M01 主数据缺失的 SKU。
3. M04b 有卖点激活但 M01 主数据缺失的 SKU。
4. M06 有评论画像但 M01 主数据缺失的 SKU。
5. M07 有市场画像或可比池但 M01 主数据缺失的 SKU。

规则：

- 正常情况以 M01 为主。
- 只出现在上游抽取表但不在 M01 的 SKU，仍生成 `blocked` 或 `review_required` 画像，用于暴露数据链路问题。
- 当前样例预期至少覆盖 35 个市场/参数型号。
- 评论只覆盖 33 个型号时，缺评论 SKU 也要生成画像。

### 9.2 `SkuSignalInputLoader`

职责：

- 读取单 SKU 的 M01-M07 current 输入。
- 读取上游 source profile refs 和 hash。
- 读取代表 evidence IDs 和 evidence 状态。
- 生成输入结构 `M08SkuSignalInputs`。

必须读取的来源：

| 域 | 来源 |
| --- | --- |
| 主数据 | M01 `core3_clean_sku` |
| 参数 | M03 `core3_sku_param_profile`、`core3_extract_param_value` |
| 卖点 | M04b `core3_sku_claim_activation`、`core3_sku_claim_comment_validation` |
| 评论 | M06 `core3_sku_comment_signal_profile`、`core3_comment_downstream_signal` |
| 市场 | M07 `core3_sku_market_profile`、`core3_market_signal` |
| 可比池 | M07 `core3_comparable_pool_baseline`、`core3_market_pool_member` |
| 证据 | M02 `core3_evidence_atom` |

### 9.3 `SkuSignalContractValidator`

校验规则：

| 校验 | 异常处理 |
| --- | --- |
| 每个上游表最多一个 current 主画像 | 多条 current 进入 `source_profile_conflict` |
| 上游 feature_version 可识别 | 不可识别则 `review_required` |
| 上游 hash 非空 | 非空失败则 `review_required` |
| 上游 processing_status 非 failed | failed 则该域 `missing` 或 `blocked` |
| evidence 可回溯 | 回溯失败则 `evidence_low_confidence` |
| SKU 主键稳定 | 不稳定则 `blocked` |

### 9.4 domain assembler

#### 主数据装配

`sku_master_json` 必须包含：

```text
sku_code
model_code
model_name
brand_name
category_code
source_tables
source_coverage
sku_identity_confidence
```

规则：

- 当前数据全为海信，M08 只记录品牌事实，不做内部/外部竞品判断。
- 主数据冲突进入 `sku_master_conflict`。

#### 参数装配

`core_params_json` 必须尽量覆盖：

```text
screen_size_inch
size_segment
resolution
mini_led
oled_qled
brightness_nits
local_dimming_zones
refresh_rate
hdmi_2_1
hdmi_count
audio_power
ram
rom
ai_model
voice_assistant
eye_care
```

规则：

- 不从原始属性文本重新解析参数。
- `unknown` 参数保留 unknown，不转 false。
- 参数冲突继承 M03 状态。
- 对 85E7Q 必须表达 85 英寸、4K、300HZ、Mini LED、5200 亮度、3500 分区、HDMI2.1、4GB/64GB、海信星海。

#### 卖点装配

`claim_activation_summary_json` 必须包含：

```text
activated_claim_count
high_confidence_claim_count
medium_confidence_claim_count
low_confidence_claim_count
unknown_claim_count
top_claims
activation_basis_distribution
perception_status_distribution
missing_structured_claim
claim_profile_status
```

`claim_evidence_breakdown_json` 必须保留：

| 证据类型 | 来源 | 说明 |
| --- | --- | --- |
| 参数支撑 | M03/M04b | 参数能支撑技术能力 |
| 结构化卖点支撑 | M04a/M04b | 原始卖点文本和标准卖点激活 |
| 评论体验验证 | M04b/M06 | 用户评论是否感知或验证卖点 |

规则：

- `missing_structured_claim` 必须显式输出。
- `param_only` 可以进入画像，但必须说明缺少结构化卖点支撑。
- `comment_only_hint` 不能在 M08 升级成强卖点。
- 85E7Q 不得伪造结构化卖点证据。

#### 评论装配

`comment_signal_summary_json` 必须保留七类信号：

```text
claim_validation
task_cue
target_group_cue
battlefield_support
pain_point
price_perception
service_signal
```

`comment_quality_json` 必须包含：

```text
raw_comment_row_count
dedup_comment_id_count
dedup_body_hash_count
effective_sentence_count
low_value_ratio
service_signal_ratio
sentiment_distribution
empty_sentiment_count
comment_quality_status
```

规则：

- 只消费 M05/M06 去重后的评论口径。
- 原始评论维度只作为弱标签，不直接生成任务、客群或战场。
- 情感为空保留 unknown，不当中立。
- 对 85E7Q，必须表达 3621 行评论、1648 个去重评论 ID，并区分画质、看球/运动、音效、价格、智能、服务等线索。

#### 市场装配

`market_summary_json` 必须包含：

```text
analysis_window
week_range
valid_week_count
price_weighted_avg
price_latest
sales_volume_total
sales_amount_total
platform_share
price_percentile
sales_volume_percentile
sales_amount_percentile
trend_status
sample_status
```

规则：

- 当前真实数据只表达 `26W01-26W23`，不输出 12 月结论。
- 当前渠道只有线上，只表达线上和平台事实。
- 市场样本不足、最新周缺口、销量或销额缺失进入风险。

#### 可比池装配

`comparable_pool_summary_json` 必须包含：

```text
same_size_pool
adjacent_size_pool
same_price_band_pool
size_price_band_pool
platform_overlap_pool
market_active_pool
pool_sample_status
representative_pool_member_refs
```

规则：

- 可比池不等于候选竞品池。
- 当前样例全为海信，同品牌 SKU 也保留在池中。
- 对 85E7Q，必须表达 85 寸同尺寸池和 75/100 相邻尺寸池。

### 9.5 `SkuSignalEvidenceMatrixBuilder`

职责：

- 对每个 SKU 输出最低矩阵行。
- 为每个分域统计 evidence count、置信度、缺失标记、风险码。
- 限制代表 evidence 数量，避免主画像过大。
- 缺失域也输出 missing 行。

证据角色：

```text
source
support
validation
risk
gap
representative
```

覆盖状态：

```text
covered
partially_covered
missing
unknown
conflict
not_applicable
```

### 9.6 `SkuSignalCompletenessCalculator`

首版公式：

```text
data_completeness_score =
  sku_master_completeness * 0.10
  + param_completeness * 0.25
  + claim_completeness * 0.20
  + comment_completeness * 0.20
  + market_completeness * 0.25
```

`claim_completeness` 特别规则：

```text
claim_completeness =
  structured_claim_availability * 0.35
  + final_claim_activation_availability * 0.30
  + comment_validation_availability * 0.20
  + claim_evidence_breakdown_integrity * 0.15
```

无结构化卖点但参数和评论充分的 SKU，`claim_completeness` 应降低但不为 0。

### 9.7 `SkuSignalRiskEvaluator`

标准风险码：

| 风险码 | 来源 | 触发条件 |
| --- | --- | --- |
| `missing_structured_claim` | M04a/M04b | 结构化卖点行数为 0 |
| `param_unknown_high` | M03 | 核心参数 unknown 率高 |
| `param_conflict` | M03 | 同一标准参数多值冲突 |
| `comment_low_value_high` | M05/M06 | 低价值评论占比高 |
| `comment_service_dominant` | M05/M06 | 服务评论占比过高 |
| `comment_signal_insufficient` | M06 | 有效信号类型不足 |
| `market_sample_limited` | M07 | 有效周数或关键指标不足 |
| `market_missing` | M07 | 无有效市场画像 |
| `comparable_pool_insufficient` | M07 | 可比池成员少于阈值 |
| `evidence_low_confidence` | M02-M07 | 核心证据低置信占比高 |
| `source_profile_conflict` | M08 | 上游 current 记录重复或 hash 冲突 |

风险解释原则：

- 缺结构化卖点表示宣传卖点证据缺口，不表示产品无卖点。
- 参数 unknown 表示参数未知，不表示能力不存在。
- 评论缺失表示体验证据不足，不表示用户不关注。
- 市场缺失表示该渠道/窗口无可用数据，不表示卖得不好。
- 可比池不足表示样本覆盖有限，不表示没有竞品。

### 9.8 `SkuSignalConfidenceCalculator`

首版公式：

```text
confidence =
  data_completeness_score * 0.45
  + weighted_domain_confidence * 0.35
  + evidence_quality_score * 0.20
  - risk_penalty
```

`risk_penalty` 上限 0.20。

置信等级：

| 等级 | 条件 |
| --- | --- |
| `high` | `confidence >= 0.80` |
| `medium` | `0.60 <= confidence < 0.80` |
| `low` | `0.35 <= confidence < 0.60` |
| `unknown` | `confidence < 0.35` 或关键输入不可用 |

profile status：

| 状态 | 判定条件 |
| --- | --- |
| `ready` | 完整度 >= 0.80，置信度 >= 0.75，无阻塞风险 |
| `limited` | 完整度 0.60-0.80，或缺一个非关键域，但下游可用 |
| `review_required` | 高销量/目标 SKU 缺结构化卖点、关键参数冲突、评论/市场风险明显 |
| `insufficient` | 完整度 < 0.45，或两个以上关键域缺失 |
| `blocked` | 无稳定 SKU 主键、上游失败、证据无法回溯 |
| `failed` | 任务执行异常 |

85E7Q 预期应为 `limited` 或 `review_required`，不能因为结构化卖点缺失而 blocked。

### 9.9 `DownstreamFeatureViewBuilder`

必须生成 M09-M15 视图。

#### M09 用户任务视图

必需特征：

```text
task_relevant_params
activated_claims
task_cue_comment_signals
price_perception_signals
market_position
risk_signals
evidence_refs
```

M09 不能直接读取 M03/M04b/M06/M07 散表，除非通过 M08 evidence 回溯审计。

#### M10 目标客群视图

必需特征：

```text
sku_master
target_group_cue_comment_signals
price_band
platform_share
service_signal
risk_signals
```

M08 不生成最终客群。

#### M11 价值战场视图

必需特征：

```text
activated_claims
battlefield_support_comment_signals
market_signal_summary
param_capability_summary
risk_signals
evidence_refs
```

M08 只能提供战场支撑信号，不能输出最终战场。

#### M11.5 卖点价值分层视图

必需特征：

```text
activated_claims
claim_evidence_breakdown
comment_validation
market_baseline
comparable_pool_summary
risk_signals
```

M08 不输出 PSI、SSI 或卖点价值层级。

#### M12 候选召回视图

必需特征：

```text
sku_comparable_keys
param_similarity_basis
claim_similarity_basis
comment_similarity_basis
market_similarity_basis
comparable_pool_summary
risk_signals
```

M08 不生成候选 SKU。

#### M13 竞品评分视图

必需特征：

```text
param_profile
claim_profile
comment_signal_summary
market_summary
pool_membership_summary
evidence_completeness
risk_signals
```

M08 不生成 pair，也不生成评分。

#### M14 核心三选择视图

必需特征：

```text
sku_profile_summary
evidence_completeness
risk_signals
market_and_pool_basis
```

M08 只提供画像和证据背景。

#### M15 展示报告视图

必需特征：

```text
business_readable_sku_profile
evidence_matrix_summary
missing_and_risk_summary
representative_evidence_refs
source_coverage_summary
```

M15 展示时不得直接展示 M08 内部字段名。

### 9.10 `SkuSignalInvalidationPublisher`

下游影响规则：

| M08 变化 | 触发模块 |
| --- | --- |
| `profile_hash` 变化 | M09-M16 |
| M09 `view_hash` 变化 | M09-M16 |
| M10 `view_hash` 变化 | M10-M16 |
| M11 `view_hash` 变化 | M11-M16 |
| M11_5 `view_hash` 变化 | M11.5-M16 |
| M12 `view_hash` 变化 | M12-M16 |
| M13 `view_hash` 变化 | M13-M16 |
| M14 `view_hash` 变化 | M14-M16 |
| M15 `view_hash` 变化 | M15-M16 |
| evidence matrix 仅展示变化 | M15、M16 |

## 10. runner/API 任务

### 10.1 Runner

建议入口：

```text
run_m08_sku_signal_profile(
  project_id: str,
  category_code: str,
  batch_id: str,
  sku_codes: list[str] | None = None,
  force: bool = False,
  profile_scope: str = "sku_default",
  analysis_window: str = "full_observed_window",
  feature_version: str = "core3_mvp_real_data_v2_m08_v1",
  run_id: str | None = None
) -> M08RunSummary
```

Runner 流程：

1. 加载 M08 规则、完整度公式和 view schema。
2. 构建 SKU universe。
3. 读取 M01-M07 current 输入。
4. 校验上游唯一性、状态、hash、evidence。
5. 装配主数据、参数、卖点、评论、市场、可比池。
6. 生成证据矩阵。
7. 计算完整度、置信度、风险和 profile status。
8. 生成 M09-M15 下游 feature views。
9. 计算 profile_hash 和 view_hash。
10. 幂等写入 profile、matrix、views。
11. 登记下游重算影响。
12. 返回运行摘要。

返回摘要必须包含：

```text
module
status
total_sku_count
created_profile_count
reused_profile_count
updated_profile_count
blocked_profile_count
review_required_count
changed_view_count_by_module
downstream_invalidation_events
warnings
review_issues
```

### 10.2 API

新增或扩展 API：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| POST | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/runs/m08-sku-signal-profile` | 运行 M08 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/sku-signal-profiles` | 查询 SKU 画像列表 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/sku-signal-profile` | 查询单 SKU 画像 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/sku-signal-evidence-matrix` | 查询证据矩阵 |
| GET | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/downstream-feature-view` | 按 `for_module` 查询 feature view |

API 边界：

- API 不暴露抽取提示词、Gold Set、内部生成方法。
- API 不输出 M09-M14 的业务结论。
- API 可以返回内部 JSON 给运营联调，但高层页面必须由 M15/API 聚合层转成业务语言。
- 查询 `for_module` 必须校验枚举，避免任意 JSON 透出。

## 11. 增量策略

### 11.1 input_fingerprint

`input_fingerprint` 由以下内容稳定 hash：

```text
M01 SKU 主数据 hash
M02 代表 evidence hash 和 evidence 状态 hash
M03 参数画像 hash 和核心参数值 hash
M04b 卖点激活 hash 和卖点评论验证 hash
M06 评论信号画像 hash 和下游信号 hash
M07 市场画像 hash、市场信号 hash、可比池 hash
M08 规则版本、完整度公式版本、下游视图 schema 版本
```

### 11.2 profile_hash

`profile_hash` 覆盖：

- 主数据摘要。
- 分域画像 JSON。
- 完整度、置信度、状态。
- 风险和缺失。
- 证据矩阵摘要。
- 下游 ready 状态。

`created_at`、`updated_at`、`module_run_id` 不参与 `profile_hash`。

### 11.3 view_hash

`view_hash` 覆盖：

- `for_module`
- `view_role`
- `view_schema_version`
- `feature_payload_json`
- `feature_quality_flags_json`
- `required_missing_fields_json`
- `ready_for_module`
- `block_reason_json`
- `profile_hash`

### 11.4 版本写入规则

1. 查询当前 `is_current=true` 画像。
2. 若 `input_fingerprint` 和 `profile_hash` 均未变，复用当前画像。
3. 若 `profile_hash` 变化，将旧画像 `is_current=false`。
4. 插入新 profile。
5. 插入新 evidence matrix。
6. 按模块生成 feature view。
7. 逐个比较 `view_hash`。
8. 只对 `view_hash` 变化的模块发出下游重算事件。

### 11.5 输入变化传播

| 输入变化 | M08 动作 | 下游影响 |
| --- | --- | --- |
| M01 SKU 主数据变化 | 重算主数据和覆盖 | M08-M16 |
| M02 evidence 状态变化 | 更新证据矩阵、置信度、代表证据 | M09-M16 |
| M03 参数画像变化 | 重算参数摘要、完整度、下游视图 | M09-M16 |
| M04b 卖点激活变化 | 重算卖点摘要和证据拆分 | M09-M16 |
| M06 评论信号变化 | 重算评论摘要、风险、下游视图 | M09-M16 |
| M07 市场画像或可比池变化 | 重算市场摘要、池摘要、视图 | M09-M16 |
| M08 规则版本变化 | 全量重算 M08 | M09-M16 |

## 12. 测试任务

### 12.1 单元测试

| 测试文件 | 必测点 |
| --- | --- |
| `test_m08_sku_universe_builder.py` | 35 市场/参数 SKU、33 评论 SKU、只在散表出现 SKU |
| `test_m08_input_loader.py` | M01-M07 current 输入、hash、版本、证据 |
| `test_m08_contract_validator.py` | 多 current、failed 上游、hash 缺失、evidence 不可回溯 |
| `test_m08_param_domain_assembler.py` | 核心参数、unknown 不转 false、冲突继承 |
| `test_m08_claim_domain_assembler.py` | `missing_structured_claim`、`param_only`、证据拆分 |
| `test_m08_comment_domain_assembler.py` | 七类评论信号、去重口径、情感 unknown |
| `test_m08_market_domain_assembler.py` | `26W01-26W23`、线上平台、无 12m |
| `test_m08_pool_domain_assembler.py` | 同尺寸、相邻尺寸、同价池摘要，可比池不是候选 |
| `test_m08_evidence_matrix_builder.py` | 最低矩阵行、缺失行、代表 evidence 限制 |
| `test_m08_completeness_calculator.py` | 完整度公式、卖点缺失不归零 |
| `test_m08_risk_evaluator.py` | 标准风险码、缺失不是负向结论 |
| `test_m08_confidence_calculator.py` | 置信度、profile_status、85E7Q limited/review |
| `test_m08_downstream_feature_view_builder.py` | M09-M15 视图边界和 ready 状态 |
| `test_m08_repositories.py` | current 失效、hash 复用、view_hash 差异 |
| `test_m08_runner.py` | 运行摘要、增量影响、复用 |
| `test_m08_api.py` | API schema、for_module 校验、404 |

### 12.2 集成测试

必须覆盖：

- M03-M08 集成：参数摘要与 M03 一致。
- M04b-M08 集成：卖点证据拆分保留。
- M06-M08 集成：七类评论信号进入画像。
- M07-M08 集成：市场和可比池摘要进入画像。
- M08-M09 集成：M09 可通过 `for_module='M09'` feature view 获取任务输入。
- M08-M15 集成：报告可读取画像和证据矩阵，但不展示内部 JSON 字段名。

### 12.3 边界测试

必须覆盖：

- SKU 无评论：仍生成画像，comment 域 missing 行。
- SKU 无结构化卖点：`missing_structured_claim`，但不输出“无卖点”。
- SKU 有参数 unknown：保留 unknown，不转 false。
- SKU 市场缺失：market 域 missing，M12/M13 视图可能 block。
- 上游多条 current：M08 blocked 或 failed，不静默选择。
- 下游必需特征缺失：对应 feature view `ready_for_module=false`。
- 同输入重复运行：`profile_hash` 和 `view_hash` 稳定。
- 参数变化：`profile_hash` 变化并触发 M09-M16。

### 12.4 禁止越界测试

必须验证：

- M08 不读取原始四张表。
- M08 不重新解析参数、评论或卖点。
- M08 不重新计算市场指标。
- M08 不输出最终任务、客群、战场、候选、评分或核心三竞品。
- M08 不把评论线索升级为最终业务结论。
- M08 不把可比池成员升级为候选竞品。
- M08 不按品牌内外过滤。
- M08 不输出 `12m` 字段。
- M08 不调用外部 LLM。

### 12.5 fixture 验收

M08 fixture 必须覆盖当前 205 样例事实：

| 数据事实 | fixture 要求 |
| --- | --- |
| 市场 35 个型号 | 有效 SKU 至少 35 个生成画像 |
| 参数 35 个型号 | 参数域覆盖 35 个 SKU |
| 评论 33 个型号 | 缺评论 SKU 仍生成画像 |
| 卖点 5 个型号 | 缺结构化卖点 SKU 标记缺口 |
| 品牌全为海信 | 不做品牌内外判断 |
| 渠道只有线上 | 不输出线下结论 |
| 周期 `26W01-26W23` | 不输出 12 月字段 |
| 85E7Q 无结构化卖点 | `missing_structured_claim=true` |

85E7Q fixture 必须检查：

```text
model_code = TV00029115
model_name = 85E7Q
screen_size = 85
resolution = 4K
refresh_rate = 300HZ
mini_led = 是
brightness = 5200
local_dimming_zones = 3500
hdmi = HDMI2.1
ram_rom = 4GB/64GB
ai_model = 海信星海
raw_comment_rows = 3621
dedup_comment_id_count = 1648
market_window = 26W01-26W23
channel = 线上
platforms = 专业电商 / 平台电商
same_size_pool = 85 寸池
adjacent_size_pool = 75/100 相邻尺寸池
risk includes missing_structured_claim
profile_status in limited/review_required
```

## 13. 开发子任务拆分

| 子任务 | 类型 | 内容 | 完成标准 |
| --- | --- | --- | --- |
| M08-A | migration/model | 新增 3 张表和 SQLAlchemy model | upgrade/downgrade 通过 |
| M08-B | schema/constants | M08 枚举、内部 schema、API schema | schema 单测通过 |
| M08-C | repository | M01-M07 输入读取、M08 输出写入、current/hash | repository 单测通过 |
| M08-D | universe/input | SKU universe、input loader、contract validator | 单元测试通过 |
| M08-E | domain assembler | 主数据、参数、卖点、评论、市场、池装配 | 单元测试通过 |
| M08-F | evidence matrix | 最低矩阵行、缺失行、代表证据 | 单元测试通过 |
| M08-G | completeness/risk/confidence | 完整度、风险、置信度、状态 | 单元测试通过 |
| M08-H | downstream views | M09-M15 feature view | 视图边界测试通过 |
| M08-I | runner/API | runner、API、增量影响 | runner/API 测试通过 |
| M08-J | fixture/越界 | 85E7Q、35 SKU、禁止越界 | 集成和越界测试通过 |

编码时仍应继续拆小任务执行，不能在一个编码任务里一次性完成 M08-A 到 M08-J。

## 14. 完成标准

M08 编码完成必须满足：

1. `0015_core3_real_data_sku_signal_profile.py` 可升级、可回滚。
2. 3 张 M08 输出表字段、唯一键、current 唯一索引和 JSONB 索引与设计一致。
3. M08 runner 可基于 M03/M04b/M06/M07 fixture 生成 profile、evidence matrix、feature views。
4. 当前样例有效 SKU 至少 35 个能生成画像。
5. 评论缺失、卖点缺失、市场缺失都能用 missing/risk 表达，不阻断其他域画像。
6. 85E7Q 能表达强参数、评论多、市场有、结构化卖点缺失和可比池摘要。
7. `missing_structured_claim` 不被写成“无卖点”。
8. unknown、空值、`-` 不被写成 false。
9. 每个 SKU 至少输出最低证据矩阵行。
10. M09-M15 均有独立 feature view、ready 状态、缺失字段和 evidence refs。
11. `profile_hash`、`view_hash` 稳定可复用。
12. M08 不输出最终任务、客群、战场、候选、评分或核心三。
13. 单元、集成、边界、越界测试通过。

## 15. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| M08 变成巨型业务结论层 | 破坏 SOP 分层 | 禁止输出 M09-M14 结论 |
| 下游继续回读散表 | 口径分裂 | feature view 成为默认输入 |
| 缺结构化卖点被误判为无卖点 | 误导 85E7Q 等 SKU | 风险码和测试固化 |
| unknown 被转 false | 参数判断失真 | unknown 测试 |
| 画像 JSON 过大 | 查询慢、报告难用 | evidence 只存代表 ID，payload 裁剪 |
| view_hash 粒度过粗 | 下游重算过多 | 每个模块单独 view_hash |
| view_hash 粒度过细 | 无意义重算 | 审计字段不参与业务 hash |
| 上游多 current 静默选择 | 画像不可信 | contract validator 阻塞 |
| M08 API 被高层页面直接展示 | 出现内部字段和 JSON | M15/API 聚合层转业务语言 |

回滚策略：

- migration downgrade 只删除 M08 三张表。
- M08 服务出错时不影响 M00-M07 已有结果。
- 若 M08 规则错误，提升 `rule_version` 或 `feature_version` 并重跑，不覆盖历史版本。
- 若某个下游 view schema 错误，只提升对应 `view_schema_version` 并重建该视图。

## 16. 下游依赖

M08 给下游的承诺：

| 下游 | 消费内容 | 边界 |
| --- | --- | --- |
| M09 | `for_module='M09'` feature view | M09 生成用户任务，M08 不生成 |
| M10 | `for_module='M10'` feature view | M10 结合 M09 结果推客群 |
| M11 | `for_module='M11'` feature view | M11 判断价值战场 |
| M11.5 | `for_module='M11_5'` feature view | M11.5 结合战场做卖点价值分层 |
| M12 | `for_module='M12'` feature view | M12 召回候选 |
| M13 | `for_module='M13'` feature view | M13 对 pair 评分 |
| M14 | `for_module='M14'` feature view | M14 做三槽位选择 |
| M15 | `for_module='M15'` feature view、evidence matrix | M15 转成高层报告业务语言 |
| M16 | profile status、review issues、hash、downstream impacts | M16 编排、复核、验收 |

下次任务：

```text
docs/core3_mvp/real_data_v2/development/M09_development_tasks.md
```

M09 用户任务模块必须以 `core3_sku_downstream_feature_view where for_module='M09'` 为默认输入，并通过 M08 evidence matrix 回溯证据。M09 可以使用 seed 本体、高频卖点组合、高频评论主题组合、同价格带/同渠道高销量 SKU 共性推导用户任务，但不能绕过 M08 直接读取原始表或散表拼装 SKU 基础画像。
