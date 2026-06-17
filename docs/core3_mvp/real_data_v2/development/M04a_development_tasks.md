# M04a 基础卖点激活开发任务

## 1. 模块目标

M04a 的开发目标是基于“标准参数 + 结构化宣传卖点”计算 SKU 的标准卖点基础激活分，形成不含评论验证、不含市场价值分层的卖点能力底座。

M04a 必须实现：

1. 加载并校验彩电标准卖点 seed 中的 `standard_claims`。
2. 判断每个 SKU 的结构化卖点来源状态。
3. 将 `promo_raw`、`promo_sentence` evidence 映射到标准卖点候选。
4. 从宣传句中抽取技术实体和数值实体。
5. 使用 M03 标准参数和 SKU 参数画像计算技术型卖点的参数支撑。
6. 使用宣传 evidence 计算宣传支撑。
7. 合成 `param_score`、`promo_score` 和 `base_activation_score`。
8. 对缺结构化卖点、抽象宣传、参数 unknown、口径不明、参数宣传冲突输出缺失和复核标记。
9. 为 M04b、M08、M09-M15 提供可追溯的基础卖点激活结果。

M04a 不消费评论、不输出最终卖点、不做战场内卖点价值分层、不做任务/客群/战场/竞品判断。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| M02 任务 | `docs/core3_mvp/real_data_v2/development/M02_development_tasks.md` |
| M03 任务 | `docs/core3_mvp/real_data_v2/development/M03_development_tasks.md` |
| M04a 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M04a_base_claim_activation_requirements.md` |
| M04a 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M04a_base_claim_activation_design.md` |
| M02 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M02_evidence_atom_design.md` |
| M03 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M03_param_extraction_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |
| 彩电 seed | `apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json` |

编码前必须确认 M02 已能输出 `promo_raw`、`promo_sentence`、`param_raw`、`quality_issue` evidence，M03 已能输出 `core3_extract_param_value` 和 `core3_sku_param_profile`。

## 3. 本次范围

### 3.1 必须实现

| 能力 | 说明 |
| --- | --- |
| 标准卖点 seed 加载 | 加载 `standard_claims`，校验 20 类 MVP 卖点 |
| 卖点来源状态 | 生成 `core3_sku_claim_source_status` |
| 宣传命中明细 | 生成 `core3_extract_claim_hit` |
| 基础激活结果 | 生成 `core3_sku_claim_activation_base` |
| 宣传句匹配 | aliases、keywords、promo keywords、标题弱提示 |
| 实体抽取 | Mini LED、OLED、QLED、HDR、Hz、nits、分区、HDMI2.1、VRR、ALLM、杜比、语音等 |
| 参数支撑 | 基于 M03 标准参数计算 `param_score` |
| 宣传支撑 | 基于 M02 宣传 evidence 计算 `promo_score` |
| param-only 降级 | 无结构化卖点时，技术型卖点允许参数基础激活但降级 |
| 缺失与冲突 | 结构化卖点缺失、缺关键参数、抽象宣传、口径不明、参数宣传冲突 |
| M04a runner | `BaseClaimActivationRunner.run(...)` |
| M04a 查询 API | 来源状态、基础卖点、命中明细 |
| 测试 | seed、matcher、entity、scorer、repository、runner、API、85E7Q fixture、越界 |

### 3.2 明确不做

M04a 不做：

- 不读取 `comment_raw`、`comment_sentence`、`comment_dimension`。
- 不读取 M05/M06 评论结果。
- 不读取市场量价或市场画像。
- 不输出最终 `core3_sku_claim_activation`。
- 不计算 `comment_score`。
- 不做战场内卖点价值分层。
- 不生成 `task_code`、`target_group_code`、`battlefield_code` 业务结论。
- 不生成竞品候选、评分、三槽位或报告结论。
- 不因为 SKU 没有结构化卖点就输出“无卖点”。
- 不为未覆盖 SKU 伪造 `promo_evidence_ids`。
- 不把 `param_only` 写成“宣传明确”。
- 不改前端页面。
- 不部署 205。

## 4. 要改文件

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/base_claim_activation_service.py
apps/api-server/app/services/core3_real_data/base_claim_activation_repositories.py
apps/api-server/app/services/core3_real_data/base_claim_activation_schemas.py
apps/api-server/app/services/core3_real_data/claim_seed_loader.py
apps/api-server/app/services/core3_real_data/claim_promo_matcher.py
apps/api-server/app/services/core3_real_data/claim_entity_extractor.py
apps/api-server/app/services/core3_real_data/claim_support_scorers.py
apps/api-server/tests/core3_real_data/test_m04a_claim_seed_loader.py
apps/api-server/tests/core3_real_data/test_m04a_claim_source_status.py
apps/api-server/tests/core3_real_data/test_m04a_promo_matcher.py
apps/api-server/tests/core3_real_data/test_m04a_entity_extractor.py
apps/api-server/tests/core3_real_data/test_m04a_support_scorers.py
apps/api-server/tests/core3_real_data/test_m04a_repositories.py
apps/api-server/tests/core3_real_data/test_m04a_runner.py
apps/api-server/tests/core3_real_data/test_m04a_api.py
apps/api-server/tests/core3_real_data/test_m04a_no_business_outputs.py
```

### 4.2 后端可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 新增 M04a 三张表模型；若 INFRA 已拆 v2 model 包，则按约定放入独立 model 文件 |
| `apps/api-server/alembic/versions/0010_core3_real_data_base_claim_activation.py` | 新增 M04a 基础卖点激活迁移 |
| `apps/api-server/app/schemas/core3_real_data.py` | 重新导出 M04a API schema |
| `apps/api-server/app/api/core3_real_data.py` | 增加 M04a 内部/运营 API |
| `apps/api-server/app/services/core3_real_data/constants.py` | 如 INFRA 未包含 M04a 枚举，可补卖点状态、命中方式、激活等级 |
| `apps/api-server/tests/core3_real_data/conftest.py` | 增加 M04a fixture、85E7Q 参数-only 样例和有结构化卖点 SKU 样例 |

### 4.3 预计引用文件

```text
apps/api-server/app/rules/tv_core3_mvp_seed_v0_2.json
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
apps/api-server/app/services/core3_real_data/evidence_atom_schemas.py
apps/api-server/app/services/core3_real_data/param_extraction_repositories.py
apps/api-server/app/services/core3_real_data/param_extraction_schemas.py
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
```

## 5. 不允许改文件

M04a 编码阶段不允许修改：

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
- M00-M03 表结构，除非先回到对应任务补设计。
- `tv_core3_mvp_seed_v0_2.json` 的业务内容，除非单独开 seed 评审任务。
- M04b-M16 的结果表。

不允许使用 `git add .`。本任务只能 stage M04a 直接新增或修改的文件。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0010_core3_real_data_base_claim_activation.py
```

如果 M03 migration 编号不是 `0009`，以当前 Alembic 最新编号顺延。迁移内容仍只包含 M04a 三张表和索引。

### 6.2 新增表

M04a migration 新增三张表：

| 表 | 用途 |
| --- | --- |
| `core3_extract_claim_hit` | 宣传句、宣传原文、参数支撑命中的标准卖点候选明细 |
| `core3_sku_claim_source_status` | SKU 结构化卖点来源覆盖状态 |
| `core3_sku_claim_activation_base` | SKU 标准卖点基础激活结果，不含评论验证 |

### 6.3 `core3_extract_claim_hit`

必须字段：

```text
claim_hit_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
claim_code
claim_name
claim_group
hit_source_type
source_sentence_key
claim_seq
sentence_seq
claim_fragment
matched_keywords
title_hint
extracted_entity_json
matched_param_codes
match_method
promo_evidence_ids
param_evidence_ids
quality_evidence_ids
match_confidence
quality_flags
review_required
review_status
hit_hash
seed_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `claim_hit_id` |
| 唯一键 | `batch_id, sku_code, claim_code, hit_source_type, source_sentence_key, rule_version` 的空值规范化组合 |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, claim_code` |
| 索引 | `hit_source_type` |
| 索引 | `review_required` |
| GIN | `matched_keywords`、`extracted_entity_json`、`promo_evidence_ids`、`param_evidence_ids`、`quality_flags` |

### 6.4 `core3_sku_claim_source_status`

必须字段：

```text
claim_source_status_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
claim_source_status
structured_claim_count
claim_sentence_count
promo_evidence_count
param_only_claim_count
quality_evidence_ids
missing_signals
conflict_summary_json
status_note
review_required
review_status
status_hash
seed_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `claim_source_status_id` |
| 唯一键 | `batch_id, sku_code, seed_version, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code` |
| 索引 | `claim_source_status` |
| 索引 | `review_required` |
| GIN | `quality_evidence_ids`、`missing_signals`、`conflict_summary_json` |

### 6.5 `core3_sku_claim_activation_base`

必须字段：

```text
claim_activation_base_id
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
claim_code
claim_name
claim_group
claim_type
param_score
promo_score
base_activation_score
activation_level
activation_basis
param_support_json
promo_support_json
missing_signals
conflict_flags
confidence
confidence_level
evidence_ids
param_evidence_ids
promo_evidence_ids
quality_evidence_ids
claim_hit_ids
review_required
review_status
review_reason
activation_hash
seed_version
rule_version
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `claim_activation_base_id` |
| 唯一键 | `batch_id, sku_code, claim_code, seed_version, rule_version` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, claim_code` |
| 索引 | `claim_group` |
| 索引 | `activation_level` |
| 索引 | `activation_basis` |
| 索引 | `review_required` |
| 索引 | `activation_hash` |
| GIN | `evidence_ids`、`missing_signals`、`conflict_flags`、`param_support_json`、`promo_support_json` |

### 6.6 迁移验收

迁移完成后必须验证：

- Alembic upgrade/downgrade 可执行。
- SQLite 测试库可 `Base.metadata.create_all`。
- 不修改原始四表和 M00-M03 表。
- 不创建 M04b-M16 结果表。
- JSON 字段在 PostgreSQL/SQLite 测试下都可读写。
- 唯一键允许 param-only 和 promo 命中明细并存，但防止同一句同 claim 重复命中。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

必须建立：

```text
Core3ExtractClaimHit
Core3SkuClaimSourceStatus
Core3SkuClaimActivationBase
```

模型要求：

- 分数字段使用 Decimal 语义。
- `evidence_ids`、`param_evidence_ids`、`promo_evidence_ids`、`quality_evidence_ids` 使用 JSON 数组。
- `param_support_json`、`promo_support_json`、`missing_signals`、`conflict_flags` 使用 JSON。
- `claim_source_status`、`activation_basis`、`activation_level` 等使用 string + service 校验。
- 不在 model 层做打分和匹配逻辑。

### 7.2 Pydantic schema

`base_claim_activation_schemas.py` 至少定义：

```text
ClaimGroup
ClaimType
ClaimHitSourceType
ClaimMatchMethod
ClaimSourceStatus
ClaimActivationBasis
ClaimActivationLevel
ClaimConfidenceLevel
ClaimReviewStatus
StdClaimDefinition
StdClaimSeed
BaseClaimActivationRunRequest
BaseClaimActivationRunResult
ClaimHitRead
ClaimSourceStatusRead
ClaimActivationBaseRead
SkuClaimBaseResponse
ClaimHitQuery
ClaimSourceStatusQuery
```

`apps/api-server/app/schemas/core3_real_data.py` 应重新导出 API 需要的 schema，避免 API 直接引用内部 service 对象。

### 7.3 枚举值

`ClaimHitSourceType` 至少支持：

```text
promo_raw
promo_sentence
param_support
quality_gap
```

`ClaimSourceStatus` 至少支持：

```text
has_structured_claim
missing_structured_claim
claim_data_insufficient
claim_conflict
```

`ClaimActivationBasis` 至少支持：

```text
param_and_promo
param_only
promo_only
insufficient
```

`ClaimActivationLevel` 至少支持：

```text
high
medium
low
unknown
```

`ClaimMatchMethod` 至少支持：

```text
exact_alias
keyword
entity
param_support
quality_gap
```

## 8. repository 任务

### 8.1 读取 repository

新增或复用：

| Repository | 职责 |
| --- | --- |
| `ClaimEvidenceReader` | 从 M02 读取 `promo_raw`、`promo_sentence`、`param_raw`、`quality_issue` current evidence |
| `SkuParamProfileReader` | 从 M03 读取 `core3_extract_param_value`、`core3_sku_param_profile` |
| `StdClaimSeedRepository` | 首版从 JSON 加载 `standard_claims`；后续可替换为数据库 |
| `ClaimActivationRepository` | 写入和查询 M04a 三张表 |
| `SkuClaimBaseReader` | 给 M04b/M08/M11.5 查询基础卖点激活 |

读取要求：

- 默认只读取 `is_current=true` 且 `evidence_status=current` 的 M02 evidence。
- 只允许读取 `promo_raw`、`promo_sentence`、`param_raw`、`quality_issue` evidence。
- 不允许读取任何 `comment_*` evidence。
- 不允许读取市场 evidence 或市场画像。
- M03 参数画像必须按 batch/SKU/current 读取，不能绕过 M03 直接解析参数。

### 8.2 写入 repository

`ClaimActivationRepository` 必须支持：

- 批量写入 SKU 来源状态。
- 批量写入 claim hit。
- 批量写入基础激活。
- 按 batch、SKU、claim_code、activation_basis、review_required 查询。
- 同一唯一键重跑时 hash 一致可跳过，hash 不一致按项目幂等策略失败或要求新 batch。

### 8.3 下游查询

给后续模块提供：

| 查询 | 用途 |
| --- | --- |
| `list_base_claims(batch_id, sku_code)` | M04b/M08 读取 SKU 基础卖点 |
| `get_claim_source_status(batch_id, sku_code)` | M08/M15 解释卖点覆盖缺口 |
| `list_claim_hits(batch_id, filters)` | 运营排查宣传命中 |
| `list_param_only_claims(batch_id, sku_code)` | M16 复核 param-only 影响 |
| `list_claims_requiring_review(batch_id)` | M16 复核低置信和冲突 |

## 9. service 任务

### 9.1 服务拆分

建议职责拆分如下：

| 服务 | 职责 |
| --- | --- |
| `StdClaimSeedLoader` | 加载、校验、版本化标准卖点 seed |
| `ClaimSourceStatusBuilder` | 判断 SKU 卖点来源状态 |
| `PromoClaimMatcher` | 宣传句到标准卖点匹配 |
| `ClaimEntityExtractor` | 技术实体和数值实体抽取 |
| `ParamSupportScorer` | 参数支撑打分 |
| `PromoSupportScorer` | 宣传支撑打分 |
| `ClaimActivationBaseScorer` | 基础激活分、等级、置信度计算 |
| `ClaimReviewRuleEngine` | 缺失、冲突和复核规则 |
| `BaseClaimActivationService` | 编排上述服务并输出写库对象 |

### 9.2 Seed 加载和校验

`StdClaimSeedLoader` 必须：

- 读取 `tv_core3_mvp_seed_v0_2.json`。
- 校验存在 `standard_claims`。
- 校验 20 类 MVP 标准卖点存在。
- 校验每个 claim 的 `claim_code`、`claim_name`、`claim_group`。
- 校验 `mapped_param_codes`、`supporting_param_codes`、`mapped_task_codes`、`mapped_battlefield_codes` 为数组或可兼容空值。
- 输出 `seed_version=tv_core3_mvp_seed_v0_2`。
- 若 seed 声明 `comment_text`，M04a 必须忽略并记录“评论验证待 M04b”。

### 9.3 SKU 卖点来源状态

`ClaimSourceStatusBuilder` 必须输出：

| 条件 | 状态 |
| --- | --- |
| `promo_raw` 或 `promo_sentence` 数量 > 0 且质量可用 | `has_structured_claim` |
| 宣传 evidence 数量 = 0，但 M03 参数画像存在 | `missing_structured_claim` |
| 宣传 evidence 存在但文本为空、低质量或全部 skipped | `claim_data_insufficient` |
| 宣传命中与关键参数明显冲突 | `claim_conflict` |

85E7Q 当前必须输出 `missing_structured_claim`，并在 `status_note` 中说明“结构化宣传卖点数据缺失，不代表没有卖点”。

### 9.4 宣传匹配

`PromoClaimMatcher` 必须：

- 使用 `aliases`、`keywords`、`promo_keywords` 匹配标准卖点。
- 识别 `claim_seq`、`sentence_seq`、`title_hint`。
- 支持一个宣传句命中多个标准卖点。
- 对命中多个标准卖点且分数接近的句子设置 `review_required=true`。
- 将“核心定位、功能价值、情感价值、便捷体验、差异化定位、行业地位”等标题结构只作为弱提示。
- 对“旗舰体验”“行业领先”“震撼升级”等无实体抽象词降权。

### 9.5 实体抽取

`ClaimEntityExtractor` 必须抽取：

| 实体类型 | 示例 |
| --- | --- |
| 显示技术 | Mini LED、OLED、QLED、ULED |
| 画质 | HDR、XDR、高亮、色域、控黑 |
| 背光控光 | 分区、局部调光、光晕控制 |
| 游戏连接 | Hz、HDMI2.1、VRR、ALLM、低延迟 |
| 护眼 | 低蓝光、无频闪、高频调光 |
| 音频 | Dolby、Atmos、W、声道、低音 |
| 智能 | AI、语音、内存、系统流畅 |
| 服务 | 安装、送装、售后 |

数值实体必须保留 raw、value、unit 和不确定性标记，不能把宣传数值直接覆盖 M03 参数事实。

### 9.6 参数支撑打分

`ParamSupportScorer` 必须基于 M03 参数值和 seed 的 `supporting_param_codes`、`mapped_param_codes` 计算 `param_score`。

典型规则：

| 卖点 | 参数支撑 |
| --- | --- |
| Mini LED 背光 | `mini_led_flag=true`、`backlight_type=MiniLED` |
| 高亮 HDR | `peak_brightness_nits >= 1000`、`hdr_format_list` |
| 精细分区控光 | `dimming_zones >= 100`、`local_dimming_flag=true` |
| 高刷新率 | `native_refresh_rate_hz >= 120` 或 `system_refresh_rate_hz >= 120` |
| HDMI 2.1 游戏接口 | `hdmi_2_1_ports >= 1`、`full_bandwidth_hdmi_flag=true` |
| 低延迟游戏 | `input_lag_ms <= 20`、`vrr_flag=true`、`allm_flag=true` |
| 护眼舒适 | `eye_dimming_freq_hz >= 1000`、`low_blue_light_flag=true`、`flicker_free_flag=true` |
| 智能语音易用 | `voice_control_flag=true`、`far_field_voice_flag=true`、`ram_gb >= 3` |
| 沉浸音效 | `speaker_power_w >= 40`、`speaker_channel`、`subwoofer_flag=true` |

口径不明确参数必须降权，例如 `system_refresh_rate_hz=300` 不能作为高置信原生刷新率。

### 9.7 宣传支撑打分

`PromoSupportScorer` 必须计算：

```text
promo_score = weighted_sum(
  exact_alias_hit,
  keyword_hit,
  entity_hit,
  numeric_entity_hit,
  title_hint_bonus,
  promo_quality_penalty
)
```

规则：

- 精确命中 aliases，高宣传支撑。
- 命中多个关键词并有实体，中高宣传支撑。
- 只有抽象词，低宣传支撑。
- 有数值实体但参数冲突，宣传支撑保留但降权。
- 无结构化宣传，`promo_score=0`，不伪造 evidence。

### 9.8 基础激活计算

M04a 不使用 `comment_score`。

技术型卖点：

```text
base_activation_score =
  param_score * 0.65
  + promo_score * 0.35
  - conflict_penalty
  - missing_signal_penalty
```

体验/设计/服务/价值型卖点：

```text
base_activation_score =
  param_score * 0.35
  + promo_score * 0.65
  - conflict_penalty
  - missing_signal_penalty
```

若 seed 的权重包含 comment：

- M04a 必须剔除 comment 权重。
- 将剩余 param/promo 权重归一。
- 在 support JSON 中保留 seed weight snapshot，供 M04b 接续。

### 9.9 激活等级和 param-only

激活等级：

| 等级 | 分数 | 说明 |
| --- | ---: | --- |
| `high` | `>= 0.75` | 参数和/或宣传支撑强 |
| `medium` | `>= 0.55` | 有一定支撑，但可能缺宣传或口径待复核 |
| `low` | `>= 0.35` | 弱支撑或证据不足 |
| `unknown` | `< 0.35` | 不足以激活 |

`activation_basis=param_only` 时默认最高等级不超过 `medium`，除非后续业务评审调整。

允许 param-only 的技术型卖点：

- `CLAIM_LARGE_SCREEN_IMMERSION`
- `CLAIM_MINI_LED_BACKLIGHT`
- `CLAIM_OLED_SELF_LIT`
- `CLAIM_QLED_WIDE_COLOR`
- `CLAIM_HIGH_BRIGHTNESS_HDR`
- `CLAIM_FINE_LOCAL_DIMMING`
- `CLAIM_HIGH_REFRESH_RATE`
- `CLAIM_HDMI_2_1_GAMING`
- `CLAIM_EYE_CARE_COMFORT`
- `CLAIM_IMMERSIVE_AUDIO`
- `CLAIM_DOLBY_CINEMA_AUDIO`

不允许仅靠参数强激活的卖点：

- `CLAIM_SPORTS_MOTION_SMOOTH`
- `CLAIM_ELDER_FRIENDLY_SMART`
- `CLAIM_NO_AD_OR_CLEAN_SYSTEM`
- `CLAIM_THIN_DESIGN`
- `CLAIM_VALUE_FOR_MONEY`
- `CLAIM_INSTALLATION_SERVICE_ASSURANCE`

### 9.10 缺失和复核

常见 `missing_signals`：

```text
missing_structured_claim
missing_promo_evidence
missing_required_param
param_unknown
scope_uncertain
unit_uncertain
comment_validation_pending
market_value_pending
```

必须进入复核：

- 新营销词高频出现但未匹配标准卖点。
- 一个宣传句命中多个标准卖点且分数接近。
- 技术型卖点只有宣传没有参数支撑。
- 参数和宣传冲突。
- 核心 SKU 结构化卖点缺失，例如 85E7Q。
- `param_only` 卖点会影响核心竞品判断。
- 体验/服务/价值型卖点只有弱宣传或无宣传。

## 10. runner/API 任务

### 10.1 Runner 入口

新增 runner：

```text
BaseClaimActivationRunner.run(
  project_id,
  category_code,
  batch_id,
  run_id=None,
  module_run_id=None,
  seed_version="tv_core3_mvp_seed_v0_2",
  rule_version="m04a_claim_base_v1",
  mode="incremental"
)
```

返回结构：

```json
{
  "batch_id": "m00_...",
  "module_code": "M04a",
  "status": "completed_with_warning",
  "sku_source_status_count": 35,
  "claim_hit_count": 120,
  "activation_base_count": 420,
  "param_only_count": 80,
  "missing_structured_claim_sku_count": 30,
  "review_required": true
}
```

实际数量以 M02/M03 输出和 M04a 规则为准，测试不得死绑示例中的 120、420、80。

### 10.2 Runner 流程

Runner 必须按顺序：

1. 加载并校验标准卖点 seed。
2. 校验 M02 current evidence 可读。
3. 校验 M03 参数画像可读。
4. 读取 `promo_raw`、`promo_sentence`、`param_raw`、`quality_issue` evidence。
5. 读取 `core3_extract_param_value` 和 `core3_sku_param_profile`。
6. 生成 SKU 卖点来源状态。
7. 执行宣传句匹配和实体抽取。
8. 计算参数支撑分。
9. 计算宣传支撑分。
10. 合成基础激活分、等级、置信度和 basis。
11. 生成缺失、冲突和复核状态。
12. 写入 M04a 三张表。
13. 输出 M16 可消费的运行摘要和下游影响建议。

### 10.3 状态规则

| 条件 | Runner 状态 |
| --- | --- |
| 全部成功且无 warning | `completed` |
| 存在结构化卖点缺失、param-only、复核项 | `completed_with_warning` |
| 少量宣传句解析失败但有质量说明 | `completed_with_error_rows` |
| seed 无法加载或结构非法 | `failed` |
| M02 evidence 不可读 | `failed` |
| M03 参数画像不可读 | `failed` |
| 输出表写入失败 | `failed` |
| 同一 SKU/claim 基础激活唯一性破坏 | `failed` 或 `blocked` |

状态值需与 INFRA/M16 runner 协议保持一致；如 INFRA 使用不同状态枚举，M04a 按 INFRA 为准，但含义不可丢失。

### 10.4 API

M04a API 是生产线运营和数据排查接口，不是高层报告接口。

建议新增：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claims/base/run` | 手工触发 M04a |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claims/source-status` | 查看 SKU 卖点来源覆盖 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/skus/{sku_code}/claims/base` | 查看 SKU 基础卖点 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/claims/hits` | 查看宣传命中明细 |

API 响应要求：

- 运营接口可返回 `claim_code`，高层报告不直接展示内部编码。
- SKU 基础卖点接口必须返回中文卖点名、基础分、basis、置信度、缺失信号和 evidence ids。
- 来源状态接口必须用中文说明结构化卖点缺失的业务含义。
- 命中明细接口支持按 claim、SKU、hit source、review_required 过滤。
- 不返回原始大表全量明细。

## 11. 测试任务

### 11.1 Seed 测试

`test_m04a_claim_seed_loader.py` 覆盖：

- `standard_claims` 存在。
- 20 类 MVP 标准卖点存在。
- `claim_code` 唯一。
- 必填字段齐全。
- `mapped_param_codes` / `supporting_param_codes` 可读取。
- seed 中 `comment_text` 不会被 M04a 当作可消费来源。

### 11.2 来源状态测试

`test_m04a_claim_source_status.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| 有 promo evidence | `has_structured_claim` |
| 无 promo、有参数画像 | `missing_structured_claim` |
| promo 为空或低质量 | `claim_data_insufficient` |
| 宣传与参数冲突 | `claim_conflict` |
| 85E7Q | 必须是 `missing_structured_claim`，不是“无卖点” |

### 11.3 宣传匹配和实体抽取测试

`test_m04a_promo_matcher.py` 和 `test_m04a_entity_extractor.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| 宣传关键词命中 | promo sentence 命中 claim hit |
| 标题弱提示 | “核心定位/功能价值”等只进入 `title_hint` |
| 技术实体 | Mini LED、OLED、QLED、HDMI2.1、VRR、ALLM 可抽取 |
| 数值实体 | Hz、nits、分区、GB、W、ms、百分比可抽取 |
| 抽象宣传 | “旗舰体验”无实体不高置信 |
| 多卖点命中 | 一个句子命中多个 claim 时可复核 |

### 11.4 支撑打分测试

`test_m04a_support_scorers.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| Mini LED 参数 | `mini_led_flag=true` 支撑 `CLAIM_MINI_LED_BACKLIGHT` |
| 亮度参数 | `peak_brightness_nits=5200` 支撑高亮 HDR，单位推断降权 |
| 分区参数 | `dimming_zones=3500` 支撑精细分区控光 |
| 高刷口径 | `system_refresh_rate_hz=300` 支撑高刷但带口径不明 |
| HDMI | HDMI2.1 能力不伪造 4 个 HDMI2.1 端口 |
| param-only | 无 promo evidence 时技术型卖点最高不超过 medium |
| 服务/价值型 | 不能仅靠参数强激活 |
| comment 权重 | seed comment 权重被剔除并归一化 |

### 11.5 Repository 测试

`test_m04a_repositories.py` 覆盖：

- claim hit 唯一键。
- source status 唯一键。
- activation base 唯一键。
- evidence ids 必填。
- 按 batch、SKU、claim_code、basis、review_required 查询。
- hash 一致重跑幂等。
- hash 不一致按策略失败或要求新 batch。

### 11.6 Runner 和 API 测试

`test_m04a_runner.py` 和 `test_m04a_api.py` 覆盖：

| 场景 | 断言 |
| --- | --- |
| promo evidence 新增 | 只重算对应 SKU 宣传命中 |
| param profile 变化 | 只重算对应 SKU 参数支撑 |
| seed 新增 claim | 受影响卖点重算 |
| 评论变化 | 不触发 M04a |
| activation_hash 不变 | 不建议下游重算 |
| run API | 返回 source status、hit、activation、param-only、缺失数 |
| source-status API | 可查询卖点来源状态 |
| SKU claims API | 返回基础卖点、basis、缺失信号和 evidence ids |
| hits API | 可过滤命中明细 |

### 11.7 越界测试

`test_m04a_no_business_outputs.py` 必须断言：

- M04a 不读取 `comment_raw`、`comment_sentence`、`comment_dimension`。
- M04a 不读取 M06 评论信号。
- M04a 不读取 `market_fact` 或市场画像。
- M04a 不生成最终 `core3_sku_claim_activation`。
- M04a 不生成 `task_code` 结论。
- M04a 不生成 `target_group_code` 结论。
- M04a 不生成 `battlefield_code` 结论。
- M04a 不生成竞品候选或评分。
- M04a 不为无卖点 SKU 伪造 `promo_evidence_ids`。

所有测试不得依赖外部 LLM 调用。

## 12. 205/85E7Q 验收

### 12.1 当前样例预期

当前 205 样例数据：

| 数据事实 | M04a 验收 |
| --- | --- |
| `selling_points_data` 65 行 | 可为 5 个覆盖型号生成宣传命中 |
| 卖点只覆盖 5 个型号 | 5 个 `has_structured_claim`，其它参数覆盖 SKU 多为 `missing_structured_claim` |
| 每个覆盖型号 13 条卖点 | `claim_seq`、`sentence_seq` 可追溯 |
| 卖点标题结构明显 | 标题只作弱提示，不当最终业务结论 |
| 35 个参数 SKU | 技术型卖点可按参数基础激活 |

### 12.2 85E7Q 验收

对 `85E7Q` / `TV00029115` 必须满足：

| 数据事实 | M04a 验收 |
| --- | --- |
| 0 行结构化卖点 | `claim_source_status=missing_structured_claim` |
| 无结构化卖点 | 不生成任何伪造 `promo_evidence_ids` |
| 尺寸 85 | 可支撑大屏沉浸基础激活 |
| Mini LED 是 | 可支撑 Mini LED 背光基础激活 |
| 亮度 5200 | 可支撑高亮 HDR，保留单位推断质量标记 |
| 分区背光 3500 | 可支撑精细分区控光 |
| 屏幕刷新率 300HZ | 可支撑高刷新率基础激活，但带系统/倍频口径降权 |
| HDMI参数 HDMI2.1 | 可支撑 HDMI2.1 能力，不伪造端口数 |
| 评论 3621 行 | M04a 不消费、不改变输出 |

### 12.3 不应强激活的 85E7Q 卖点

M04a 不应对 85E7Q 强激活：

- 安装服务保障。
- 高性价比。
- 体育运动流畅的用户感知。
- 长辈友好智能的用户感知。
- 清爽系统/少广告。

这些需要评论、市场或宣传证据，由 M04b、M07、M11.5 或后续模块处理。

### 12.4 业务含义验收

M04a 输出必须能被解释为：

- “这个 SKU 有哪些基础卖点候选。”
- “这个基础卖点是参数支撑、宣传支撑，还是参数+宣传共同支撑。”
- “结构化宣传缺失不代表 SKU 没有卖点。”
- “param-only 是降级判断，不能写成宣传明确。”
- “评论验证尚未发生，最终卖点强弱要等 M04b。”

## 13. 完成标准

M04a 编码完成必须满足：

1. M04a 三张表迁移、模型、schema、repository 已完成。
2. 标准卖点 seed 可加载、可校验、版本可记录。
3. 20 类 MVP 标准卖点均可参与匹配或参数支撑。
4. 有结构化卖点的 SKU 可生成宣传命中。
5. 技术型卖点可基于 M03 参数形成基础支撑。
6. 85E7Q 输出 `missing_structured_claim`。
7. 85E7Q 不生成伪造宣传 evidence。
8. 体验/服务/价值型卖点不由参数强行激活。
9. 每个激活卖点保留 `evidence_ids`，且区分参数、宣传、质量 evidence。
10. 参数和宣传冲突可复核。
11. `param_only` 最高等级默认不超过 medium。
12. M04a runner 可返回来源状态数、命中数、基础激活数、param-only 数和缺失数。
13. M04a 输出可被 M04b/M08 消费。
14. M04a 不消费评论、不读取市场、不生成任务/战场/竞品/报告结论。
15. 后端测试通过，且测试不依赖 205 实库或外部 LLM。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 把结构化卖点缺失写成无卖点 | 误导业务和报告 | 来源状态、missing_signals 和 fixture 测试固化 |
| 为 85E7Q 伪造 promo evidence | 证据链失真 | promo_evidence_ids 必须来自 M02，越界测试固化 |
| 参数-only 过强 | 把能力事实写成宣传明确 | param-only 最高 medium，M15 需转译限制 |
| 评论提前进入 M04a | 与 M04b 边界混乱 | repository 白名单和越界测试 |
| 服务/价值型靠参数强激活 | 业务含义错误 | claim_type 策略限制 |
| seed comment 权重未处理 | 基础分混入评论权重 | comment 权重剔除并归一化 |
| 刷新率/HDMI 口径误用 | 游戏体育卖点被高估 | scope/HDMI 复核规则 |
| 抽象宣传高置信 | 宣传噪声变成卖点 | 抽象词降权和实体要求 |

回滚方式：

- migration downgrade 删除 M04a 三张表，不触碰 M00-M03 和原始四表。
- 若 seed 加载失败，只标记 M04a module run 失败，不推进 M04b。
- 若某 batch 基础卖点异常，保留失败批次供排查，不删除历史成功结果。

## 15. 下游依赖

| 下游模块 | 依赖 M04a 的产物 |
| --- | --- |
| M04b | 从 `core3_sku_claim_activation_base` 开始做评论验证增强 |
| M08 | 使用基础卖点作为 SKU 综合画像的一部分 |
| M09-M11 | 使用基础卖点作为任务、客群、战场推导的一个来源，但必须结合评论和市场 |
| M11.5 | 在战场上下文中做卖点价值分层，不能用 M04a 替代 |
| M12-M14 | 评分和选择时区分参数支撑、宣传支撑、评论验证 |
| M15 | 把基础卖点转成业务表达，明确 param-only、宣传缺失和评论待验证 |
| M16 | 使用来源状态、param-only 数、冲突、低置信和 `activation_hash` 做复核和增量 |

## 16. 编码子任务建议

M04a 编码建议拆为以下小闭环：

| 子任务 | 内容 | 建议验收 |
| --- | --- | --- |
| M04a-A | migration 和 SQLAlchemy model | 三张表 upgrade/downgrade 通过 |
| M04a-B | schema 和枚举 | 卖点状态、命中方式、basis、level schema 测试通过 |
| M04a-C | seed loader | 20 类标准卖点结构校验和版本输出测试通过 |
| M04a-D | 来源状态 builder | has/missing/insufficient/conflict 状态测试通过 |
| M04a-E | promo matcher 和 entity extractor | 关键词、标题、实体、抽象词测试通过 |
| M04a-F | 参数/宣传支撑打分 | param_score、promo_score、param-only 和限制策略测试通过 |
| M04a-G | 基础激活 scorer | score、level、basis、missing、conflict 测试通过 |
| M04a-H | repository 和 runner | 幂等、增量、摘要、复核状态测试通过 |
| M04a-I | API | run、source-status、SKU claims、hits 测试通过 |
| M04a-J | 越界和 fixture 验收 | 85E7Q 缺卖点降级通过，M04a 不消费评论 |

编码阶段每次仍应只做一个小闭环。M04a 完成并验收后，才进入 M05 评论基础证据层开发任务。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M05_development_tasks.md
```

M05 文档需要基于 M02 评论 evidence 和 M01 评论清洗事实，拆清去重评论单元、评论专用句级证据、弱主题提示、评论质量画像，并为 M06 的评论下游信号抽取提供可靠输入。
