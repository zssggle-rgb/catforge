# M03 参数字段画像与标准参数抽取开发任务

## 1. 模块目标

M03 的开发目标是把 M02 的 `param_raw` evidence 和受控的 `promo_sentence` 派生候选转换成标准参数画像，为后续 M04a、M08、M09-M15 提供稳定的 `param_code + normalized_value + evidence_ids + confidence`。

M03 必须实现：

1. 加载并校验彩电标准参数 seed，按版本记录到输出。
2. 基于 `param_raw` evidence 生成全部原始参数字段画像。
3. 将原始字段匹配到标准参数，输出匹配方式、置信度和复核状态。
4. 严格区分 unknown、空值、`-` 与 false。
5. 解析尺寸、分辨率、刷新率、亮度、分区、HDMI、内存、存储、布尔、枚举、列表和字符串参数。
6. 对高覆盖未映射字段生成别名候选。
7. 对同 SKU 同标准参数多值、多来源、单位、口径冲突生成复核记录。
8. 生成 SKU 级参数画像，供 M08 直接消费。
9. 保留所有参数值的 `evidence_ids`，不生成新的 evidence。

M03 是参数标准化和参数画像模块，不做卖点激活、用户任务、目标客群、价值战场、竞品召回、评分或报告结论。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M02 任务 | `docs/core3_mvp/real_data_v2/development/M02_development_tasks.md` |
| M03 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M03_param_extraction_requirements.md` |
| M03 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| M02 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M02_evidence_atom_design.md` |
| M01 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M01_cleaning_quality_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认 M02 至少能输出 `param_raw`、`promo_sentence`、`quality_issue` evidence，并且 evidence 中包含 `evidence_id`、`evidence_payload_json`、`base_confidence`、`quality_flags` 和 `value_presence`。

## 3. 本次范围

### 3.1 必须实现

| 能力 | 说明 |
| --- | --- |
| 标准参数 seed 加载 | 加载 `tv_core3_mvp_seed_v0_2.json` 中 `standard_params` 并校验必填字段 |
| 字段画像 | 生成 `core3_param_field_profile`，覆盖全部原始参数字段 |
| 字段匹配 | exact alias、standard name、contains alias、keyword、value pattern、unmapped |
| 别名候选 | 生成 `core3_param_alias_candidate` |
| 参数值抽取 | 生成 `core3_extract_param_value` |
| 参数冲突 | 生成 `core3_param_value_conflict` |
| SKU 参数画像 | 生成 `core3_sku_param_profile` |
| parser 注册 | inch、resolution、hz、nits、zones、ports、gb、percentage、boolean、enum、list、string |
| unknown 语义 | unknown/null/空/`-` 不得转 false |
| 特殊口径 | 刷新率、HDMI、无单位亮度、无单位分区必须可复核 |
| 派生参数 | 仅从有 `promo_sentence` evidence 的 SKU 抽取，低于参数表优先级 |
| M03 runner | `ParamExtractionRunner.run(...)` |
| M03 查询 API | 字段画像、SKU 参数、别名候选、冲突 |
| 测试 | seed、matcher、parser、repository、runner、API、85E7Q fixture、越界 |

### 3.2 明确不做

M03 不做：

- 不读取评论 evidence 做参数抽取。
- 不读取市场 evidence。
- 不新增 evidence。
- 不生成标准卖点激活结果或 `claim_code` 判断。
- 不生成 `task_code`、`target_group_code`、`battlefield_code` 业务结论。
- 不生成竞品候选、竞品评分、三槽位或报告结论。
- 不把参数直接解释成用户任务、客群或战场。
- 不把 unknown、空值、`-`、缺字段当 false。
- 不为 85E7Q 从结构化卖点中派生参数，因为当前 85E7Q 没有结构化卖点。
- 不改前端页面。
- 不部署 205。

## 4. 要改文件

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/param_extraction_service.py
apps/api-server/app/services/core3_real_data/param_extraction_repositories.py
apps/api-server/app/services/core3_real_data/param_extraction_schemas.py
apps/api-server/app/services/core3_real_data/param_seed_loader.py
apps/api-server/app/services/core3_real_data/param_field_matcher.py
apps/api-server/app/services/core3_real_data/param_value_parsers.py
apps/api-server/app/services/core3_real_data/param_conflicts.py
apps/api-server/tests/core3_real_data/test_m03_param_seed_loader.py
apps/api-server/tests/core3_real_data/test_m03_param_field_profile.py
apps/api-server/tests/core3_real_data/test_m03_param_field_matcher.py
apps/api-server/tests/core3_real_data/test_m03_param_value_parsers.py
apps/api-server/tests/core3_real_data/test_m03_param_repositories.py
apps/api-server/tests/core3_real_data/test_m03_param_service.py
apps/api-server/tests/core3_real_data/test_m03_param_runner.py
apps/api-server/tests/core3_real_data/test_m03_param_api.py
apps/api-server/tests/core3_real_data/test_m03_no_business_outputs.py
```

### 4.2 后端可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 新增 M03 五张表模型；若 INFRA 已拆 v2 model 包，则按约定放入独立 model 文件 |
| `apps/api-server/alembic/versions/0009_core3_real_data_param_extraction.py` | 新增 M03 抽取表迁移 |
| `apps/api-server/app/schemas/core3_real_data.py` | 重新导出 M03 API schema |
| `apps/api-server/app/api/core3_real_data.py` | 增加 M03 内部/运营 API |
| `apps/api-server/app/services/core3_real_data/constants.py` | 如 INFRA 未包含 M03 枚举，可补参数状态、匹配类型、冲突类型 |
| `apps/api-server/tests/core3_real_data/conftest.py` | 增加 M03 fixture、85E7Q 参数样例和 M02 evidence 样例 |

### 4.3 预计引用文件

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
apps/api-server/app/services/core3_real_data/evidence_atom_schemas.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
```

## 5. 不允许改文件

M03 编码阶段不允许修改：

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

不允许修改：

- 原始四表结构。
- M00/M01/M02 表结构，除非先回到对应任务补设计。
- `tv_core3_mvp_seed_v0_2.json` 的业务内容，除非单独开 seed 评审任务。
- M04a-M16 的结果表。

不允许使用 `git add .`。本任务只能 stage M03 直接新增或修改的文件。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0009_core3_real_data_param_extraction.py
```

如果 M02 migration 编号不是 `0008`，以当前 Alembic 最新编号顺延。迁移内容仍只包含 M03 五张表和索引。

### 6.2 新增表

M03 migration 新增五张表：

| 表 | 用途 |
| --- | --- |
| `core3_param_field_profile` | 原始参数字段画像、标准参数匹配和复核状态 |
| `core3_extract_param_value` | SKU 标准参数值抽取结果 |
| `core3_param_alias_candidate` | 未映射或低置信字段的标准参数别名候选 |
| `core3_param_value_conflict` | 同 SKU 同参数的多值、多来源、单位、口径冲突 |
| `core3_sku_param_profile` | SKU 级参数画像，供 M08 消费 |

### 6.3 `core3_param_field_profile`

必须字段：

```text
field_profile_id
project_id
category_code
batch_id
run_id
module_run_id
raw_param_name
clean_param_name
normalized_param_name
occurrence_count
sku_coverage_count
sku_coverage_rate
unknown_count
unknown_rate
present_count
top_values_json
value_pattern_summary_json
matched_param_code
matched_param_name
param_group
match_type
alias_confidence
candidate_status
review_required
review_status
review_reason
evidence_ids
field_profile_hash
seed_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `field_profile_id` |
| 唯一键 | `batch_id, clean_param_name, seed_version, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `matched_param_code` |
| 索引 | `candidate_status` |
| 索引 | `review_required` |
| GIN | `top_values_json`、`value_pattern_summary_json`、`evidence_ids` |

### 6.4 `core3_extract_param_value`

必须字段：

```text
param_value_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
param_code
param_name
param_group
data_type
normalized_value
numeric_value
value_text
unit
value_level
value_presence
source_type
source_priority_rank
raw_param_name
raw_param_value
match_type
parser_type
parser_status
confidence
confidence_level
evidence_ids
primary_evidence_id
quality_flags
conflict_flag
conflict_id
review_required
review_status
param_value_hash
seed_version
parser_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `param_value_id` |
| 唯一键 | `batch_id, sku_code, param_code, source_type, primary_evidence_id, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, param_code` |
| 索引 | `param_group` |
| 索引 | `source_type` |
| 索引 | `review_required` |
| 索引 | `param_value_hash` |
| GIN | `normalized_value`、`evidence_ids`、`quality_flags` |

同一 SKU 同一标准参数允许多来源候选值并存，不能为“简化”而覆盖掉低优先级候选。

### 6.5 `core3_param_alias_candidate`

必须字段：

```text
alias_candidate_id
project_id
category_code
batch_id
raw_param_name
clean_param_name
sku_coverage_rate
unknown_rate
top_values_json
value_pattern_summary_json
suggested_param_code
suggestion_reason
confidence
candidate_type
review_required
review_status
review_decision_json
seed_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `alias_candidate_id` |
| 唯一键 | `batch_id, clean_param_name, seed_version` |
| 索引 | `suggested_param_code` |
| 索引 | `candidate_type` |
| 索引 | `review_status` |
| GIN | `top_values_json`、`review_decision_json` |

### 6.6 `core3_param_value_conflict`

必须字段：

```text
conflict_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
param_code
conflict_type
candidate_values_json
preferred_value_json
preferred_source_type
confidence
evidence_ids
quality_flags
review_required
review_status
review_reason
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `conflict_id` |
| 唯一键 | `batch_id, sku_code, param_code, conflict_type, rule_version` |
| 索引 | `sku_code, param_code` |
| 索引 | `conflict_type` |
| 索引 | `review_required` |
| GIN | `candidate_values_json`、`evidence_ids`、`quality_flags` |

### 6.7 `core3_sku_param_profile`

必须字段：

```text
sku_param_profile_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
param_values_json
core_picture_params_json
core_gaming_params_json
core_system_params_json
core_eye_care_params_json
param_completeness
known_param_count
unknown_param_count
conflict_count
review_required_count
evidence_ids
quality_summary_json
profile_hash
seed_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `sku_param_profile_id` |
| 唯一键 | `batch_id, sku_code, seed_version, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code` |
| 索引 | `profile_hash` |
| GIN | `param_values_json`、`quality_summary_json`、`evidence_ids` |

### 6.8 迁移验收

迁移完成后必须验证：

- Alembic upgrade/downgrade 可执行。
- SQLite 测试库可 `Base.metadata.create_all`。
- 不修改原始四表和 M00-M02 表。
- 不创建 M04a-M16 结果表。
- JSON 字段在 PostgreSQL/SQLite 测试下都可读写。
- 唯一键允许多来源参数值并存，但防止同一 evidence 重复生成同一参数值。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

必须建立：

```text
Core3ParamFieldProfile
Core3ExtractParamValue
Core3ParamAliasCandidate
Core3ParamValueConflict
Core3SkuParamProfile
```

模型要求：

- 数值字段使用 Decimal 语义。
- `normalized_value` 使用 JSON，避免 boolean、number、enum、list、string 多列膨胀。
- `evidence_ids` 使用 JSON 数组，必须能保存多个 evidence。
- `review_status`、`match_type`、`parser_status` 等使用 string + service 校验。
- 不在 model 层做参数解析。

### 7.2 Pydantic schema

`param_extraction_schemas.py` 至少定义：

```text
ParamDataType
ParamGroup
ParamSourceType
ParamMatchType
ParamCandidateStatus
ParamReviewStatus
ParamParserStatus
ParamConflictType
ParamConfidenceLevel
StdParamDefinition
StdParamSeed
ParamExtractionRunRequest
ParamExtractionRunResult
ParamFieldProfileRead
ExtractParamValueRead
ParamAliasCandidateRead
ParamValueConflictRead
SkuParamProfileRead
SkuParamQuery
```

`apps/api-server/app/schemas/core3_real_data.py` 应重新导出 API 需要的 schema，避免 API 直接引用内部 service 对象。

### 7.3 枚举值

`ParamSourceType` 至少支持：

```text
raw_param
derived_from_claim
model_name
```

`ParamMatchType` 至少支持：

```text
exact_alias
standard_name
contains_alias
keyword
value_pattern
unmapped
```

`ParamParserStatus` 至少支持：

```text
parsed
unknown
failed
scope_uncertain
unit_uncertain
conflict
```

`ParamConflictType` 至少支持：

```text
same_param_multi_value
raw_param_vs_claim_conflict
unit_uncertain
scope_uncertain
boolean_unknown
hdmi_version_count_mixed
```

## 8. repository 任务

### 8.1 读取 repository

新增或复用：

| Repository | 职责 |
| --- | --- |
| `ParamEvidenceReader` | 从 M02 读取 `param_raw`、`promo_sentence`、`quality_issue` current evidence |
| `StdParamSeedRepository` | 首版从 JSON 加载 seed；后续可替换为数据库 |
| `ParamExtractionRepository` | 写入和查询 M03 五张表 |
| `SkuParamProfileReader` | 给 M04a/M08/M13 查询 SKU 参数画像 |

读取要求：

- 默认只读取 `is_current=true` 且 `evidence_status=current` 的 M02 evidence。
- 只允许读取 `param_raw`、`promo_sentence`、`quality_issue` evidence。
- 不读取 `comment_raw`、`comment_sentence`、`market_fact`。
- `quality_issue` 只用于降权和复核，不直接生成参数值。

### 8.2 写入 repository

`ParamExtractionRepository` 必须支持：

- 批量写入字段画像。
- 批量写入参数值。
- 批量写入别名候选。
- 批量写入参数冲突。
- 批量写入 SKU 参数画像。
- 按 batch、SKU、param_code、review_required 查询。
- 同一唯一键重跑时 hash 一致可跳过，hash 不一致按项目幂等策略失败或要求新 batch。

### 8.3 下游查询

给后续模块提供：

| 查询 | 用途 |
| --- | --- |
| `list_param_values(batch_id, sku_code)` | M04a/M13 读取 SKU 标准参数 |
| `get_sku_param_profile(batch_id, sku_code)` | M08 读取 SKU 参数画像 |
| `list_field_profiles(batch_id, filters)` | 运营排查字段匹配 |
| `list_alias_candidates(batch_id, filters)` | M16 复核别名候选 |
| `list_param_conflicts(batch_id, filters)` | M16 复核冲突 |

## 9. service 任务

### 9.1 服务拆分

建议职责拆分如下：

| 服务 | 职责 |
| --- | --- |
| `StdParamSeedLoader` | 加载、校验、版本化标准参数 seed |
| `ParamFieldNormalizer` | 参数字段名规范化 |
| `ParamFieldProfiler` | 聚合字段覆盖、unknown 率、高频值和值形态 |
| `ParamAliasMatcher` | 字段到标准参数匹配 |
| `ParamValueParserRegistry` | 注册和调度 parser |
| `ParamValueExtractor` | 从 evidence 抽取标准参数值 |
| `ParamConflictDetector` | 冲突和复核项识别 |
| `SkuParamProfileBuilder` | 选择主值并生成 SKU 参数画像 |
| `ParamExtractionService` | 编排上述服务并输出写库对象 |

### 9.2 Seed 加载和校验

`StdParamSeedLoader` 必须：

- 读取 `tv_core3_mvp_seed_v0_2.json`。
- 校验存在 `standard_params`。
- 校验每个标准参数的 `param_code`、`param_name`、`data_type`、`param_group`、`aliases`、`value_parsers`。
- 校验 `param_code` 唯一。
- 输出 `seed_version=tv_core3_mvp_seed_v0_2`。
- 忽略 seed 中 `source_types` 的 `comment_text`，M03 不从评论抽参数。

### 9.3 字段画像

`ParamFieldProfiler` 必须：

- 以 `clean_param_name` 聚合。
- 输出出现次数、覆盖 SKU 数、覆盖率。
- 输出 unknown/null/空/`-` 数量和比例。
- 输出 top values。
- 输出值形态摘要：number-like、boolean-like、enum-like、unit 候选、样例值。
- 为当前 84 类属性全部生成画像。
- 对 unknown 高发字段保留画像，不丢弃。

### 9.4 字段匹配

`ParamAliasMatcher` 匹配顺序：

| 顺序 | 匹配方式 | `match_type` | 基础置信度 |
| ---: | --- | --- | ---: |
| 1 | 精确别名 | `exact_alias` | 0.95 |
| 2 | 标准名 | `standard_name` | 0.93 |
| 3 | 包含别名 | `contains_alias` | 0.82 |
| 4 | 关键词 | `keyword` | 0.70 |
| 5 | 值形态 | `value_pattern` | 0.55 |
| 6 | 未命中 | `unmapped` | 0.00 |

调整规则：

- 覆盖率 >= 80% 且值形态符合 parser，可加 0.03。
- unknown 率 > 50%，减 0.10。
- 一个字段命中多个标准参数，减 0.15 并复核。
- 命中核心战场参数但不是 exact/standard，必须 `review_required=true`。

### 9.5 parser 要求

`ParamValueParserRegistry` 必须注册：

| parser | 要求 |
| --- | --- |
| `inch` | `85`、`85英寸` -> 85 inch |
| `resolution` | `4K`、`8K`、`3840x2160` 归一 |
| `hz` | 抽取 Hz，保留原生/系统口径标记 |
| `nits` | 抽取亮度数值；字段为亮度且无单位时标记 `unit_inferred` |
| `zones` | 抽取分区数；`千级分区` 不伪造精确值 |
| `ports` | 解析端口数量；HDMI 版本和数量分开 |
| `gb` | 解析 RAM/ROM 容量 |
| `percentage` | 解析百分比和色域标准 |
| `boolean_keyword` | `是/支持/有` true，`否/不支持/无` false，缺失 unknown |
| `enum_keyword` | 按 seed enum 和关键词归一 |
| `list_keyword` | 抽取多个格式或标准 |
| `string` | 保留清洗字符串 |

### 9.6 unknown 和 false

必须固化以下规则：

| 原始值 | M03 输出 |
| --- | --- |
| null | `value_presence=unknown` |
| 空字符串 | `value_presence=unknown` |
| `-` | `value_presence=unknown` |
| `unknown`、`未知`、`暂无` | `value_presence=unknown` |
| `否`、`不支持`、`无` | 仅当字段已匹配布尔参数时可解析为 false |
| 字段缺失 | 不生成 false，进入覆盖缺口或 unknown |

示例：`MINILED` 字段为空，只能表示 `mini_led_flag=unknown`，不能表示 `mini_led_flag=false`。

### 9.7 特殊口径规则

刷新率：

- 字段或 seed 明确“原生刷新率”，写 `native_refresh_rate_hz`。
- 字段或 seed 明确“系统/倍频/动态刷新率”，写 `system_refresh_rate_hz`。
- 字段只有“屏幕刷新率/刷新率”，且值高于常见原生口径，优先写 `system_refresh_rate_hz`，加 `scope_uncertain`。
- 不允许把系统/倍频刷新率直接作为高置信原生刷新率。

HDMI：

- `HDMI参数=HDMI2.1` 只说明 HDMI2.1 能力，不说明端口数。
- `HDMI数量=4` 只说明 HDMI 总接口数量候选。
- 只有“4 个 HDMI2.1”这类同句证据时，才可派生 `hdmi_2_1_ports=4`。
- `HDMI参数=HDMI2.1` 和 `HDMI数量=4` 同时存在时，应生成 `hdmi_version_count_mixed` 复核，不得自动合成 4 个 HDMI2.1。

亮度和分区：

- `亮度=5200` 字段语义明确时可解析数值，单位标记 `unit_inferred` 或 `unit_uncertain`。
- `分区背光=3500` 可解析 `dimming_zones=3500`。
- `千级分区` 只能生成范围或等级，不伪造精确数。

### 9.8 宣传派生参数

M03 可以从 `promo_sentence` evidence 抽取派生参数候选，但必须遵守：

- `source_type=derived_from_claim`。
- 置信度默认不高于 0.75。
- 优先级低于 `raw_param`。
- 与参数表冲突时保留两边 evidence 并进入复核。
- 没有 `promo_sentence` evidence 的 SKU 不生成宣传派生参数。
- 85E7Q 当前没有结构化卖点，因此不应生成 `derived_from_claim` 参数。

### 9.9 冲突和主值选择

来源优先级：

```text
raw_param > derived_from_claim > model_name
```

主值选择：

1. 保留 unknown 记录，但主值选择时优先 present。
2. 优先选择 `raw_param`。
3. 同来源多值选择 confidence 高者。
4. 置信度接近但值不同，生成冲突。
5. 派生参数只在参数表缺失或作为补充候选时进入主值。

必须生成冲突的场景：

- 同 SKU 同参数多值。
- 参数表和宣传派生参数冲突。
- 单位不明确。
- 口径不明确。
- 布尔字段 unknown。
- HDMI 版本和数量混合。

### 9.10 SKU 参数画像

`SkuParamProfileBuilder` 必须输出：

- `param_values_json`：所有标准参数主值和关键候选。
- `core_picture_params_json`：Mini LED、亮度、分区、刷新率、HDR、色域等。
- `core_gaming_params_json`：刷新率、HDMI、VRR、ALLM、低延迟等。
- `core_system_params_json`：RAM、ROM、芯片、系统、语音、广告风险等。
- `core_eye_care_params_json`：护眼、低蓝光、无频闪、儿童模式等。
- 参数完整度、known 数、unknown 数、冲突数、待复核数。
- 核心 evidence ids 和质量摘要。

## 10. runner/API 任务

### 10.1 Runner 入口

新增 runner：

```text
ParamExtractionRunner.run(
  project_id,
  category_code,
  batch_id,
  run_id=None,
  module_run_id=None,
  seed_version="tv_core3_mvp_seed_v0_2",
  parser_version="m03_parser_v1",
  rule_version="m03_param_v1",
  mode="incremental"
)
```

返回结构：

```json
{
  "batch_id": "m00_...",
  "module_code": "M03",
  "status": "completed_with_warning",
  "field_profile_count": 84,
  "param_value_count": 1200,
  "sku_profile_count": 35,
  "alias_candidate_count": 12,
  "conflict_count": 8,
  "review_required": true
}
```

实际数量以 M02 evidence 和 M03 parser 结果为准，测试不得死绑示例中的 1200、12、8。

### 10.2 Runner 流程

Runner 必须按顺序：

1. 加载并校验标准参数 seed。
2. 校验 M02 current evidence 可读。
3. 读取 `param_raw`、`promo_sentence`、`quality_issue` evidence。
4. 生成字段画像。
5. 执行字段匹配和别名候选生成。
6. 调度 parser 抽取参数值。
7. 合并多来源候选。
8. 识别冲突、单位不明、口径不明和 unknown。
9. 写入 M03 五张表。
10. 生成 SKU 参数画像和 `profile_hash`。
11. 输出 M16 可消费的运行摘要和复核建议。

### 10.3 状态规则

| 条件 | Runner 状态 |
| --- | --- |
| 全部成功且无 warning | `completed` |
| 存在 alias candidate、冲突或口径复核 | `completed_with_warning` |
| 少量参数解析失败但有质量说明 | `completed_with_error_rows` |
| seed 无法加载或结构非法 | `failed` |
| M02 evidence 不可读 | `failed` |
| 输出表写入失败 | `failed` |
| 幂等冲突破坏唯一性 | `failed` |

状态值需与 INFRA/M16 runner 协议保持一致；如 INFRA 使用不同状态枚举，M03 按 INFRA 为准，但含义不可丢失。

### 10.4 API

M03 API 是生产线运营和数据排查接口，不是高层报告接口。

建议新增：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/params/run` | 手工触发 M03 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/params/field-profiles` | 查看字段画像 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/skus/{sku_code}/params` | 查看 SKU 参数画像 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/params/alias-candidates` | 查看别名候选 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/params/conflicts` | 查看参数冲突 |

API 响应要求：

- 运营接口可返回 `param_code`，高层报告不直接展示内部编码。
- SKU 参数接口必须返回中文参数名、展示值、置信度、质量说明和 evidence ids。
- 字段画像接口支持按 matched/unmapped/review_required 过滤。
- 冲突接口必须显示中文复核原因。
- 不返回原始大表全量明细。

## 11. 测试任务

### 11.1 Seed 测试

`test_m03_param_seed_loader.py` 覆盖：

- `standard_params` 存在。
- `param_code` 唯一。
- 必填字段齐全。
- 核心参数存在：尺寸、分辨率、刷新率、亮度、分区、Mini LED、HDMI、RAM、ROM。
- seed 中 `comment_text` 不会被 M03 当作可消费来源。

### 11.2 字段画像和匹配测试

`test_m03_param_field_profile.py` 和 `test_m03_param_field_matcher.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| 全字段画像 | fixture 中每类 `clean_attr_name` 都有画像 |
| 覆盖率 | occurrence、SKU coverage、unknown rate 正确 |
| top values | 高频值输出稳定 |
| 字段规范化 | `MINILED`、`Mini LED`、`MiniLED` 可统一 |
| exact alias | `尺寸` 匹配 `screen_size_inch` |
| standard name | 标准名直接匹配 |
| contains alias | 包含别名可低置信匹配 |
| unmapped 高覆盖 | 进入 alias candidate |
| 多命中 | 降置信并 review_required |

### 11.3 Parser 测试

`test_m03_param_value_parsers.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| 尺寸 | `85`、`85英寸` -> 85 inch |
| 分辨率 | `4K`、`3840x2160` -> 4K |
| 刷新率 | `300HZ` 不输出高置信原生刷新率 |
| 亮度 | `5200` 在亮度字段下解析数值并标记单位推断 |
| 分区 | `3500` -> zones 3500 |
| HDMI 参数 | `HDMI2.1` 不等于 4 个 HDMI2.1 |
| HDMI 数量 | `4` 只作为接口数量候选 |
| GB | `4GB`、`64GB` 正确解析 |
| 布尔 | `是` true，`不支持` false |
| unknown | null、空、`-`、unknown 不解析为 false |
| list | HDR 多格式可解析列表 |
| string | `海信星海` 保留字符串 |

### 11.4 Repository 测试

`test_m03_param_repositories.py` 覆盖：

- 字段画像唯一键。
- 参数值多来源并存。
- 冲突唯一键。
- SKU profile 唯一键。
- evidence_ids 必填。
- 按 batch、SKU、param_code、review_required 查询。
- hash 一致重跑幂等。
- hash 不一致按策略失败或要求新 batch。

### 11.5 Service 和 runner 测试

`test_m03_param_service.py` 和 `test_m03_param_runner.py` 覆盖：

| 场景 | 断言 |
| --- | --- |
| param_raw evidence 新增 | 只重算受影响 SKU 参数 |
| param_raw evidence 变化 | 参数值 hash 和 profile hash 变化 |
| promo_sentence 变化 | 派生参数候选重算 |
| seed alias 新增 | 字段画像和参数值重算 |
| profile hash 不变 | 不建议下游重算 |
| seed 加载失败 | runner failed |
| M02 evidence 不可读 | runner failed |
| 高覆盖未映射字段 | 生成 alias candidate |
| 多来源冲突 | 生成 conflict |

### 11.6 API 测试

`test_m03_param_api.py` 覆盖：

- run API 返回字段画像数、参数值数、SKU 画像数、候选数、冲突数。
- field-profiles API 支持 matched/unmapped/review_required 过滤。
- SKU params API 返回参数画像、中文参数名、展示值、置信度和 evidence ids。
- alias-candidates API 返回建议理由。
- conflicts API 返回候选值、主值、冲突原因和复核状态。
- M02 未完成时返回明确错误。

### 11.7 越界测试

`test_m03_no_business_outputs.py` 必须断言：

- M03 不读取 `comment_raw` 或 `comment_sentence` evidence。
- M03 不读取 `market_fact` evidence。
- M03 不生成 `claim_code` 激活结果。
- M03 不生成 `task_code` 结论。
- M03 不生成 `target_group_code` 结论。
- M03 不生成 `battlefield_code` 结论。
- M03 不生成竞品候选或评分。
- unknown 不被输出为 false。

所有测试不得依赖外部 LLM 调用。

## 12. 205/85E7Q 验收

### 12.1 当前样例预期

当前 205 样例数据：

| 数据事实 | M03 验收 |
| --- | --- |
| `attribute_data` 2843 行 | 参数 evidence 可被完整消费 |
| 35 个型号有参数 | 生成 35 个 SKU 参数画像 |
| 84 类属性字段 | 84 类字段全部有字段画像 |
| unknown/空值/`-` 约 961 行 | unknown 独立统计和降权，不当 false |
| 高覆盖未映射字段 | 进入字段画像和 alias candidate |

高覆盖但缺失明显的字段，如 `CPU主频`、`GPU核数`、`HDR`、`IC型号`、`全面屏`、`UI界面`、`HEVC参数`、`主芯片供应商`，必须在字段画像中可见，不允许丢弃。

### 12.2 85E7Q 参数验收

对 `85E7Q` / `TV00029115` 必须满足：

| 原始字段 | 原值 | M03 验收 |
| --- | --- | --- |
| `尺寸` | 85 | `screen_size_inch=85` |
| `清晰度2` | 4K | `resolution_class=4K` 或进入别名候选后可识别 |
| `屏幕刷新率` | 300HZ | 不输出高置信 `native_refresh_rate_hz=300` |
| `亮度` | 5200 | 数值 5200，单位推断或不确定 |
| `分区背光` | 3500 | `dimming_zones=3500` |
| `MINILED` | 是 | `mini_led_flag=true` |
| `HDMI参数` | HDMI2.1 | 记录 HDMI2.1 能力，不伪造端口数 |
| `HDMI数量` | 4 | 记录 HDMI 总接口数量候选 |
| `RAM内存` | 4GB | `ram_gb=4` |
| `ROM容量` | 64GB | `storage_gb=64` |
| `AI大模型` | 海信星海 | 智能系统字符串参数 |
| 无结构化卖点 | 不生成 `derived_from_claim` 参数 |

### 12.3 业务含义验收

M03 输出必须能被解释为：

- “这个 SKU 有哪些标准参数能力。”
- “每个参数值来自哪些 evidence。”
- “哪些参数是 unknown，不能当作不支持。”
- “哪些参数口径需要复核，例如系统刷新率和 HDMI 端口数。”
- “参数是能力事实，不直接等于卖点、任务、战场或竞品结论。”

## 13. 完成标准

M03 编码完成必须满足：

1. M03 五张表迁移、模型、schema、repository 已完成。
2. 标准参数 seed 可加载、可校验、版本可记录。
3. 84 类原始属性字段都能生成字段画像。
4. 重点参数识别率目标不低于 95%，未识别字段进入候选。
5. 85E7Q 核心参数可抽取或进入明确复核。
6. 参数值 100% 保留 `evidence_ids`。
7. unknown/null/空/`-` 不当 false。
8. 系统/原生刷新率口径可区分或复核。
9. HDMI 版本和数量不混淆。
10. 宣传派生参数低于参数表优先级。
11. 未映射高覆盖字段进入复核候选。
12. 多来源、多值、单位、口径冲突可查询。
13. `core3_sku_param_profile` 可供 M08 直接使用。
14. M03 runner 可返回字段画像数、参数值数、SKU 画像数、候选数、冲突数和复核建议。
15. M03 不生成卖点、任务、客群、战场、竞品或报告结论。
16. 后端测试通过，且测试不依赖 205 实库或外部 LLM。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 直接用原始字段名当标准参数 | 下游无法稳定消费 | 必须经过 seed 匹配和 `param_code` 输出 |
| unknown 被当 false | 卖点和竞品结论误导 | value presence、parser 和越界测试固化 |
| 85E7Q 字段被写死 | 无法泛化到其它 SKU | seed + 字段画像 + parser 组合，不按 SKU 写规则 |
| 刷新率口径误用 | 游戏体育战场被高估 | `scope_uncertain` 和复核规则 |
| HDMI 版本与数量混淆 | 游戏接口能力被伪造 | 拆分能力和数量，冲突复核 |
| 派生参数覆盖参数表事实 | 参数事实被宣传口径污染 | source priority 和置信度上限 |
| 高覆盖未映射字段被丢弃 | seed 无法演进 | alias candidate 强制输出 |
| M03 读取评论或市场 | 模块边界混乱 | repository 白名单和越界测试 |

回滚方式：

- migration downgrade 删除 M03 五张表，不触碰 M00-M02 和原始四表。
- 若 seed 加载失败，只标记 M03 module run 失败，不推进 M04a。
- 若某 batch 参数画像异常，保留失败批次供排查，不删除历史成功画像。

## 15. 下游依赖

| 下游模块 | 依赖 M03 的产物 |
| --- | --- |
| M04a | `core3_extract_param_value`、`core3_sku_param_profile`、参数 evidence 和置信度 |
| M04b | 经 M04a 后间接使用参数能力，不能绕过卖点激活 |
| M07 | 可用 `screen_size_inch` 等价格无关参数辅助可比池，不消费市场逻辑 |
| M08 | 直接消费 `core3_sku_param_profile` |
| M09-M11.5 | 引用参数能力作为任务、客群、战场推导的一个来源，必须结合卖点、评论、市场 |
| M12-M14 | 评分和选择时引用参数证据和画像 |
| M15 | 把参数转成中文业务表达，不展示内部 `param_code` |
| M16 | 使用字段画像、未映射候选、参数冲突、关键参数 unknown、`profile_hash` 做复核和增量 |

## 16. 编码子任务建议

M03 编码建议拆为以下小闭环：

| 子任务 | 内容 | 建议验收 |
| --- | --- | --- |
| M03-A | migration 和 SQLAlchemy model | 五张表 upgrade/downgrade 通过 |
| M03-B | schema 和枚举 | 参数类型、匹配、parser、冲突 schema 测试通过 |
| M03-C | seed loader | seed 结构校验和版本输出测试通过 |
| M03-D | 字段画像和 matcher | 84 类字段画像、别名匹配、候选测试通过 |
| M03-E | parser registry | 尺寸、4K、Hz、nits、zones、HDMI、GB、boolean 等测试通过 |
| M03-F | 参数值抽取和冲突 | 多来源、unknown、单位、口径、HDMI 冲突测试通过 |
| M03-G | SKU 参数画像 | `core3_sku_param_profile` 和 hash 测试通过 |
| M03-H | repository 和 runner | 幂等、增量、摘要、复核状态测试通过 |
| M03-I | API | run、field profile、SKU params、alias candidate、conflict 测试通过 |
| M03-J | 越界和 fixture 验收 | 85E7Q 核心参数通过，M03 不生成业务结论 |

编码阶段每次仍应只做一个小闭环。M03 完成并验收后，才进入 M04a 基础卖点激活开发任务。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M04a_development_tasks.md
```

M04a 文档需要基于 M03 标准参数、M02 `promo_raw/promo_sentence` evidence 和标准卖点 seed，拆清基础卖点激活、卖点来源覆盖、宣传缺失降级、参数支撑规则、卖点置信度和下游卖点画像开发任务。
