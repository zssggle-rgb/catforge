# M02 Evidence 原子层开发任务

## 1. 模块目标

M02 的开发目标是把 M01 清洗事实和质量问题转换成全链路可复用的 evidence 原子，让后续每一个参数、卖点、评论、画像、竞品和报告结论都能追溯到真实数据、清洗事实和质量状态。

M02 必须实现：

1. 为 SKU、市场、参数、卖点、评论、评论维度、质量问题生成统一 evidence。
2. 建立稳定的 `evidence_key` 和版本化的 `evidence_id`。
3. 保存 M00 原始行、M01 清洗行、原值、清洗值、质量标记和基础置信度。
4. 生成 evidence 之间的关系，特别是评论原文、评论句、评论维度、重复正文、质量问题之间的关系。
5. 支持 clean hash 变化后的旧 evidence 失效、新 evidence current，并保留历史。
6. 提供下游可查询的 current evidence 入口。
7. 固化证据层边界：M02 只生成事实证据和质量证据，不生成业务结论。

M02 是数据底座的最后一层。M02 完成后，M03-M15 才能开始基于 evidence 做业务推导。

## 2. 设计引用

| 类型 | 文件 |
| --- | --- |
| 开发总纲 | `docs/core3_mvp/real_data_v2/development/00_development_execution_plan.md` |
| 总任务拆分 | `docs/core3_mvp/real_data_v2/development/00_development_task_breakdown.md` |
| INFRA 任务 | `docs/core3_mvp/real_data_v2/development/INFRA_development_tasks.md` |
| M00 任务 | `docs/core3_mvp/real_data_v2/development/M00_development_tasks.md` |
| M01 任务 | `docs/core3_mvp/real_data_v2/development/M01_development_tasks.md` |
| M02 需求 | `docs/core3_mvp/real_data_v2/sop_requirements/M02_evidence_atom_requirements.md` |
| M02 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M02_evidence_atom_design.md` |
| M01 详细设计 | `docs/core3_mvp/real_data_v2/sop_detailed_design/M01_cleaning_quality_design.md` |
| 真实数据基线 | `docs/core3_mvp/real_data_v2/sop_requirements/00_real_data_baseline.md` |

编码前必须确认 M00、M01 至少具备可测试的批次登记、清洗事实表、质量问题表和 `clean_hash`。

## 3. 本次范围

### 3.1 必须实现

| 能力 | 说明 |
| --- | --- |
| evidence atom 表 | `core3_evidence_atom` |
| evidence link 表 | `core3_evidence_link` |
| current evidence 视图或查询 | `is_current=true` 且 `evidence_status=current` |
| evidence ID | `evidence_key` 稳定、`evidence_id` 随 clean hash 版本化 |
| 类型映射 | M01 九类清洗表映射到 evidence 类型 |
| payload 构造 | 按 evidence 类型生成结构化 `evidence_payload_json` |
| 基础置信度 | 按证据类型、质量状态、unknown、低价值、异常降权 |
| 失效策略 | clean hash 变化后 superseded，清洗记录失效后 inactive |
| evidence link | 生成 comment/sentence/dimension/quality/重复关系 |
| M02 runner | `EvidenceAtomRunner.run(...)` |
| M02 查询 API | evidence 生成、摘要、单条证据、证据关系、SKU 证据查询 |
| 测试 | ID、映射、payload、置信度、link、增量、fixture、越界 |

### 3.2 明确不做

M02 不做：

- 不读取原始四表做业务判断。
- 不修改 M00/M01 表。
- 不标准化参数，不生成 `param_code`。
- 不激活卖点，不生成 `claim_code`。
- 不解释评论任务、客群、战场、痛点或购买动机。
- 不把评论维度直接转换成业务标签。
- 不把质量问题当成商品能力事实。
- 不生成市场画像、SKU 画像、候选、评分、核心三竞品或报告结论。
- 不改前端页面。
- 不部署 205。

## 4. 要改文件

### 4.1 后端新增文件

```text
apps/api-server/app/services/core3_real_data/evidence_atom_service.py
apps/api-server/app/services/core3_real_data/evidence_atom_repositories.py
apps/api-server/app/services/core3_real_data/evidence_atom_schemas.py
apps/api-server/app/services/core3_real_data/evidence_mappers.py
apps/api-server/app/services/core3_real_data/evidence_confidence.py
apps/api-server/app/services/core3_real_data/evidence_links.py
apps/api-server/tests/core3_real_data/test_m02_evidence_ids.py
apps/api-server/tests/core3_real_data/test_m02_evidence_mapping.py
apps/api-server/tests/core3_real_data/test_m02_evidence_repositories.py
apps/api-server/tests/core3_real_data/test_m02_evidence_service.py
apps/api-server/tests/core3_real_data/test_m02_evidence_runner.py
apps/api-server/tests/core3_real_data/test_m02_evidence_api.py
apps/api-server/tests/core3_real_data/test_m02_no_business_outputs.py
```

### 4.2 后端可能修改文件

| 文件 | 修改原因 |
| --- | --- |
| `apps/api-server/app/models/entities.py` | 新增 M02 两张表模型；若 INFRA 已拆 v2 model 包，则按约定放入独立 model 文件 |
| `apps/api-server/alembic/versions/0008_core3_real_data_evidence.py` | 新增 M02 evidence 表迁移 |
| `apps/api-server/app/schemas/core3_real_data.py` | 重新导出 M02 API schema |
| `apps/api-server/app/api/core3_real_data.py` | 增加 M02 内部/运营 API |
| `apps/api-server/app/services/core3_real_data/constants.py` | 如 INFRA 未包含 M02 枚举，可补 evidence 类型、状态、link 类型 |
| `apps/api-server/tests/core3_real_data/conftest.py` | 增加 M02 fixture、M01 清洗表样例和 85E7Q evidence 断言工具 |

### 4.3 预计引用文件

```text
apps/api-server/app/services/core3_real_data/hash_utils.py
apps/api-server/app/services/core3_real_data/run_context.py
apps/api-server/app/services/core3_real_data/runner.py
apps/api-server/app/services/core3_real_data/cleaning_repositories.py
apps/api-server/app/services/core3_real_data/cleaning_schemas.py
apps/api-server/app/services/core3_real_data/source_registry_repositories.py
```

## 5. 不允许改文件

M02 编码阶段不允许修改：

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
- M00 批次登记表结构，除非先回到 M00 任务补设计。
- M01 清洗表结构，除非先回到 M01 任务补设计。
- M03-M16 的业务结果表。

不允许使用 `git add .`。本任务只能 stage M02 直接新增或修改的文件。

## 6. 数据库迁移任务

### 6.1 migration 文件

建议新增：

```text
apps/api-server/alembic/versions/0008_core3_real_data_evidence.py
```

如果 M01 migration 编号不是 `0007`，以当前 Alembic 最新编号顺延。迁移内容仍只包含 M02 evidence 表、索引和可选视图。

### 6.2 新增表和视图

M02 migration 新增：

| 对象 | 用途 |
| --- | --- |
| `core3_evidence_atom` | 统一事实证据和质量证据 |
| `core3_evidence_link` | 证据之间的从属、重复、质量和替代关系 |
| `core3_current_evidence_atom` | 可选只读视图，方便下游读取当前证据 |

如果首版因工期不落 `core3_evidence_link`，必须在本任务评审时显式降级，并确保 `core3_evidence_atom` 保留能重建 link 的字段。默认建议落 link 表。

### 6.3 `core3_evidence_atom`

必须字段：

```text
evidence_id
evidence_key
project_id
category_code
batch_id
run_id
module_run_id
sku_code
model_name
brand_name
evidence_type
evidence_grain
evidence_field
evidence_title
source_table
source_pk
source_row_id
source_row_hash
clean_table
clean_record_key
clean_hash
clean_version
raw_field
raw_value
clean_field
clean_value
value_presence
numeric_value
numeric_values_json
unit_value
text_value
text_hash
evidence_time
period_raw
period_week_index
channel_type
platform_type
comment_id
comment_text_hash
segment_text_hash
sentence_seq
dimension_path_raw
quality_status
quality_flags
base_confidence
confidence_level
sample_status
evidence_payload_json
evidence_status
inactive_reason
is_current
evidence_version
confidence_rule_version
asset_version
review_required
review_status
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `evidence_id` |
| 唯一键 | `evidence_key, clean_hash, evidence_version` |
| 当前唯一约束 | PostgreSQL partial unique：`evidence_key where is_current = true` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `sku_code, evidence_type` |
| 索引 | `source_row_id` |
| 索引 | `clean_table, clean_record_key` |
| 索引 | `evidence_key, is_current` |
| 索引 | `evidence_status` |
| 索引 | `comment_id` |
| 索引 | `comment_text_hash` |
| 索引 | `segment_text_hash` |
| GIN | `quality_flags`、`evidence_payload_json` |

SQLite 测试库如不支持 partial unique，必须在 repository/service 层测试 current 唯一性。

### 6.4 `core3_evidence_link`

必须字段：

```text
link_id
project_id
category_code
batch_id
from_evidence_id
to_evidence_id
from_evidence_key
to_evidence_key
link_type
link_payload_json
confidence
link_status
created_at
updated_at
```

约束和索引：

| 类型 | 字段 |
| --- | --- |
| 主键 | `link_id` |
| 唯一键 | `from_evidence_id, to_evidence_id, link_type` |
| 索引 | `project_id, category_code, batch_id` |
| 索引 | `from_evidence_id` |
| 索引 | `to_evidence_id` |
| 索引 | `link_type` |
| GIN | `link_payload_json` |

### 6.5 `core3_current_evidence_atom` 视图

可选只读视图：

```sql
select *
from core3_evidence_atom
where is_current = true
  and evidence_status = 'current'
```

下游 M03-M15 可以使用 repository 查询 current evidence，但不能忽略 evidence 状态直接扫描历史 evidence。

### 6.6 迁移验收

迁移完成后必须验证：

- Alembic upgrade/downgrade 可执行。
- SQLite 测试库可 `Base.metadata.create_all`。
- PostgreSQL JSONB 和索引定义符合项目兼容方式。
- 不修改 M00/M01 表和原始四表。
- 不创建 M03-M16 业务结果表。
- current 唯一性在 PostgreSQL 或 service 层有明确保障。

## 7. model/schema 任务

### 7.1 SQLAlchemy model

必须建立：

```text
Core3EvidenceAtom
Core3EvidenceLink
```

模型要求：

- `base_confidence` 和 link `confidence` 使用 Decimal 语义。
- JSON 字段兼容 PostgreSQL JSONB 和 SQLite 测试。
- 长文本字段不在 model 层截断，列表接口截断展示由 API/schema 处理。
- `is_current` 必须有默认值，插入时由 service 显式赋值。
- `evidence_status`、`link_status` 使用 string 枚举加 service 校验，避免数据库 enum 迁移复杂。

### 7.2 Pydantic schema

`evidence_atom_schemas.py` 至少定义：

```text
EvidenceType
EvidenceGrain
EvidenceStatus
EvidenceInactiveReason
EvidenceLinkType
EvidenceLinkStatus
ConfidenceLevel
EvidenceRunRequest
EvidenceRunResult
EvidenceCounts
EvidenceSummary
EvidenceAtomRead
EvidenceAtomListItem
EvidenceLinkRead
SkuEvidenceQuery
SkuEvidenceResponse
EvidenceTraceResponse
```

`apps/api-server/app/schemas/core3_real_data.py` 应重新导出 API 需要的 schema，避免 API 直接引用内部 service 对象。

### 7.3 枚举值

`EvidenceType` 至少支持：

```text
sku_fact
market_fact
param_raw
promo_raw
promo_sentence
comment_raw
comment_sentence
comment_dimension
quality_issue
```

`EvidenceGrain` 至少支持：

```text
sku
row
field
sentence
dimension
quality
```

`EvidenceStatus` 支持：

```text
current
inactive
superseded
skipped
```

`EvidenceLinkType` 支持：

```text
same_source_row
same_clean_record
has_sentence
has_dimension
has_quality_issue
same_comment
same_comment_text
same_segment
supersedes
```

## 8. repository 任务

### 8.1 读取 repository

新增或复用：

| Repository | 职责 |
| --- | --- |
| `CleanFactReader` | 读取 M01 九类清洗事实和质量问题 |
| `SourceRegistryReader` | 补充 M00 `source_row_hash`、原始表、原始主键 |
| `EvidenceAtomRepository` | 写入、失效、查询 `core3_evidence_atom` |
| `EvidenceLinkRepository` | 写入、失效、查询 `core3_evidence_link` |
| `CurrentEvidenceReader` | 给下游读取 current evidence |

`CleanFactReader` 必须按 batch 和 mode 读取：

```text
core3_clean_sku
core3_clean_market_weekly
core3_clean_attribute
core3_clean_claim
core3_clean_claim_sentence
core3_clean_comment
core3_clean_comment_sentence
core3_clean_comment_dimension
core3_data_quality_issue
```

### 8.2 写入规则

`EvidenceAtomRepository` 必须支持：

- 按 `evidence_id` 幂等插入。
- 查找同一 `evidence_key` 的 current evidence。
- 将旧 current 标记为 `superseded`。
- 将清洗记录失效对应 evidence 标记为 `inactive`。
- 查询单条 evidence 和 SKU evidence。
- 返回 evidence 类型计数、低置信计数、缺失域摘要。

`EvidenceLinkRepository` 必须支持：

- link 幂等插入。
- 按 `from_evidence_id` / `to_evidence_id` 查询。
- 按 evidence 失效 link。
- 防止同一 `from/to/type` 重复。

### 8.3 current 唯一性

同一 `evidence_key` 只能有一条 `is_current=true`。

实现要求：

1. 写入新 evidence 前查询 current。
2. 如果 current 的 `evidence_id` 相同，不重复插入。
3. 如果 current 的 `evidence_id` 不同，先 supersede 旧 evidence，再插入新 current。
4. 如果发现多条 current，runner 必须失败并要求复核。

## 9. service 任务

### 9.1 服务拆分

建议职责拆分如下，不要把全部逻辑塞进 runner：

| 服务 | 职责 |
| --- | --- |
| `EvidenceMapper` | 清洗表到 evidence 类型、粒度、字段映射 |
| `EvidenceIdService` | 生成 `evidence_key` 和 `evidence_id` |
| `EvidencePayloadBuilder` | 构造类型专用 payload |
| `EvidenceConfidenceService` | 计算 `base_confidence` 和 `confidence_level` |
| `EvidenceInvalidationService` | 处理 superseded/inactive |
| `EvidenceLinkBuilder` | 生成证据关系 |
| `EvidenceAtomService` | 编排读取、映射、写入、link、摘要 |

### 9.2 Evidence ID 规则

`evidence_key`：

```text
hash(
  project_id,
  category_code,
  evidence_type,
  clean_table,
  clean_record_key,
  evidence_field,
  evidence_version
)
```

`evidence_id`：

```text
hash(
  evidence_key,
  clean_hash,
  source_row_hash,
  evidence_version
)
```

测试必须证明：

- 同一 clean record、同一 evidence field 重复生成 `evidence_key` 一致。
- clean hash 变化后 `evidence_key` 不变、`evidence_id` 变化。
- 下游引用旧 `evidence_id` 仍可追溯旧 raw/clean 值。

### 9.3 Evidence 映射规则

| 清洗表 | evidence 类型 | 粒度 | 关键字段 |
| --- | --- | --- | --- |
| `core3_clean_sku` | `sku_fact` | `sku` | 覆盖、冲突、缺失信号 |
| `core3_clean_market_weekly` | `market_fact` | `row` | 周期、渠道、平台、销量、销额、均价 |
| `core3_clean_attribute` | `param_raw` | `field` | 属性名、属性值、presence、数字和单位候选 |
| `core3_clean_claim` | `promo_raw` | `row` | 卖点序号、宣传原文、清洗文本 |
| `core3_clean_claim_sentence` | `promo_sentence` | `sentence` | 卖点句、句角色弱提示 |
| `core3_clean_comment` | `comment_raw` | `row` | 评论正文、正文 hash、分段 hash、情感、低价值 |
| `core3_clean_comment_sentence` | `comment_sentence` | `sentence` | 评论句、句来源、句序号 |
| `core3_clean_comment_dimension` | `comment_dimension` | `dimension` | 原始维度路径、维度质量 |
| `core3_data_quality_issue` | `quality_issue` | `quality` | 问题类型、严重度、中文说明、下游建议 |

### 9.4 类型专用 payload

`EvidencePayloadBuilder` 必须生成稳定 JSON，至少覆盖：

| evidence 类型 | payload 必含 |
| --- | --- |
| `sku_fact` | `coverage_json`、`field_conflicts_json`、`missing_signals_json` |
| `market_fact` | `period_raw`、`channel_type`、`platform_type`、`sales_volume`、`sales_amount`、`avg_price`、`price_check_status` |
| `param_raw` | `raw_attr_name`、`clean_attr_name`、`raw_attr_value`、`clean_attr_value`、`value_presence`、`number_candidates`、`unit_candidates` |
| `promo_raw` | `claim_seq`、`raw_claim_text`、`clean_claim_text`、`title_hint` |
| `promo_sentence` | `claim_seq`、`sentence_seq`、`sentence_text`、`sentence_role_hint` |
| `comment_raw` | `comment_id`、`clean_comment_text`、`comment_text_hash`、`segment_text_hash`、`sentiment_clean`、`low_value_flag`、`duplicate_group_key` |
| `comment_sentence` | `comment_id`、`sentence_source`、`sentence_seq`、`sentence_text`、`sentiment_clean`、`low_value_flag` |
| `comment_dimension` | `primary_dim_raw`、`secondary_dim_raw`、`third_dim_raw`、`dimension_path_raw`、`dimension_quality_flag` |
| `quality_issue` | `domain`、`issue_type`、`severity`、`issue_detail`、`suggested_downstream_action` |

长文本可以在列表 schema 中截断摘要，但完整文本必须保存在 `evidence_payload_json` 或字段中。

### 9.5 基础置信度

`EvidenceConfidenceService` 首版规则：

| 证据情况 | 基础置信度 |
| --- | ---: |
| 结构化市场量价，数值解析成功且均价校验通过 | 0.95 |
| 结构化参数，非 unknown，字段来源明确 | 0.90 |
| 结构化卖点原文，来源明确 | 0.85 |
| 卖点句级文本，切句清晰 | 0.80 |
| SKU 覆盖事实，无跨表冲突 | 0.80 |
| 评论原文有效，非低价值，非明显重复 | 0.75 |
| 评论句级文本有效，非低价值 | 0.70 |
| 评论原始维度弱标签 | 0.55 |
| 参数 unknown 或缺失质量 evidence | 0.35 |
| 默认评价、空评价、低价值评论 | 0.25 |
| 数值异常、跨表冲突等 error 质量 evidence | 0.20 |

降权上限：

| 条件 | 上限 |
| --- | ---: |
| `quality_status=warning` | 0.70 |
| `quality_status=error` | 0.30 |
| `value_presence != present` | 0.35 |
| `low_value_flag=true` | 0.25 |
| `price_check_status=mismatch` | 0.70 |
| `dimension_quality_flag=missing` | 0.25 |

`base_confidence` 只代表证据可用性，不代表业务结论正确性。

### 9.6 失效策略

`EvidenceInvalidationService` 必须实现：

| 输入变化 | 行为 |
| --- | --- |
| 新 clean record | 生成 current evidence |
| 同 `clean_record_key` 但 `clean_hash` 变化 | 旧 evidence `superseded`，新 evidence `current` |
| clean record inactive | 旧 evidence `inactive` |
| quality issue 新增 | 生成 quality evidence |
| quality issue 解决 | 旧 quality evidence `inactive` |
| 同一 `evidence_key` 多条 current | runner 失败，要求复核 |

不得物理删除旧 evidence。

### 9.7 Link 生成规则

`EvidenceLinkBuilder` 必须实现：

| link 类型 | 规则 | 置信度 |
| --- | --- | ---: |
| `has_sentence` | 同一 source row 的 comment/promo 原文到句子 | 1.0 |
| `has_dimension` | 同一 source row 的 comment 原文到维度 | 0.55 |
| `same_comment` | 同一 `sku_code + comment_id` | 0.80 |
| `same_comment_text` | 同一 `comment_text_hash` | 0.70 |
| `same_segment` | 同一 `segment_text_hash` | 0.70 |
| `has_quality_issue` | 事实 evidence 关联可定位质量问题 | 1.0 |
| `supersedes` | 新 evidence 替代旧 evidence | 1.0 |

link 只表达数据关系，不代表业务观点强度。

## 10. runner/API 任务

### 10.1 Runner 入口

新增 runner：

```text
EvidenceAtomRunner.run(
  project_id,
  category_code,
  batch_id,
  run_id=None,
  module_run_id=None,
  evidence_version="m02_evidence_v1",
  confidence_rule_version="m02_confidence_v1",
  mode="incremental"
)
```

返回结构：

```json
{
  "batch_id": "m00_...",
  "module_code": "M02",
  "status": "completed_with_warning",
  "evidence_counts": {
    "sku_fact": 35,
    "market_fact": 1326,
    "param_raw": 2843,
    "promo_raw": 65,
    "promo_sentence": 220,
    "comment_raw": 62426,
    "comment_sentence": 90000,
    "comment_dimension": 62426,
    "quality_issue": 1500
  },
  "link_counts": {
    "has_sentence": 0,
    "has_dimension": 0,
    "same_comment": 0,
    "same_comment_text": 0,
    "same_segment": 0,
    "has_quality_issue": 0,
    "supersedes": 0
  },
  "low_confidence_count": 1800,
  "review_required": true
}
```

实际数量以 fixture 和清洗结果为准，测试不得死绑示例中的 90000 或 1500。

### 10.2 Runner 流程

Runner 必须按顺序：

1. 校验 M01 清洗表可读且 batch 可消费。
2. 读取 M01 清洗事实和质量问题。
3. 补齐 M00 source row 信息。
4. 按清洗表映射 evidence type 和 grain。
5. 生成 `evidence_key` 和 `evidence_id`。
6. 构造 evidence payload。
7. 计算基础置信度。
8. 幂等写入 evidence atom。
9. 处理旧 current evidence 的 superseded/inactive。
10. 生成 evidence link。
11. 检查 current 唯一性和低置信比例。
12. 写入或更新模块运行摘要。
13. 返回 M16 可消费的运行结果。

### 10.3 状态规则

| 条件 | Runner 状态 |
| --- | --- |
| 全部 evidence/link 成功生成且无 warning | `completed` |
| 存在低置信或缺域 warning 但不阻断 | `completed_with_warning` |
| 少量清洗事实跳过且有原因 | `completed_with_error_rows` |
| M01 清洗表不可读 | `failed` |
| evidence ID 规则缺失 | `failed` |
| 写入 evidence 失败 | `failed` |
| 同一 `evidence_key` 多条 current | `blocked` 或 `failed`，不得继续下游 |

状态值需与 INFRA/M16 runner 协议保持一致；如 INFRA 使用不同状态枚举，M02 按 INFRA 为准，但含义不可丢失。

### 10.4 API

M02 API 是证据查询和排查接口，不是高层报告接口。

建议新增：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/evidence/run` | 手工触发 M02 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/batches/{batch_id}/evidence/summary` | 查看 evidence 生成摘要 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/evidence/{evidence_id}` | 查看单条 evidence |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/evidence/{evidence_id}/links` | 查看 evidence 关联 |
| `GET` | `/api/mvp/core3/v2/projects/{project_id}/skus/{sku_code}/evidence` | 按 SKU 查询 evidence |

API 响应要求：

- 运营接口可以返回 `evidence_id`，但高层展示页不直接展示 UUID/hash。
- 列表响应应包含中文 evidence title、证据类型、质量状态、置信度和摘要。
- 单条接口必须能返回 M00/M01 追溯信息。
- SKU 查询必须支持 evidence type、confidence level、current only 过滤。
- 不返回原始大表全量明细。

## 11. 测试任务

### 11.1 ID 测试

`test_m02_evidence_ids.py` 覆盖：

| 测试 | 断言 |
| --- | --- |
| `evidence_key` 稳定 | 同一 clean record 同一字段重复生成一致 |
| `evidence_id` 版本化 | clean hash 变化后 ID 变化 |
| source hash 变化 | 原始行 hash 变化后 ID 变化 |
| evidence version 变化 | 新规则版本生成新 key/id |
| stable JSON | payload 字段顺序不影响 ID |

### 11.2 映射和 payload 测试

`test_m02_evidence_mapping.py` 覆盖：

- `core3_clean_sku` -> `sku_fact`。
- `core3_clean_market_weekly` -> `market_fact`。
- `core3_clean_attribute` -> `param_raw`。
- `core3_clean_claim` -> `promo_raw`。
- `core3_clean_claim_sentence` -> `promo_sentence`。
- `core3_clean_comment` -> `comment_raw`。
- `core3_clean_comment_sentence` -> `comment_sentence`。
- `core3_clean_comment_dimension` -> `comment_dimension`。
- `core3_data_quality_issue` -> `quality_issue`。
- 每种 payload 都包含必要字段。

### 11.3 Repository 测试

`test_m02_evidence_repositories.py` 覆盖：

- evidence atom 幂等插入。
- 同一 `evidence_key` current 唯一。
- clean hash 变化后旧 evidence superseded。
- inactive evidence 不物理删除。
- link 幂等插入和查询。
- 按 SKU、类型、source row、comment id、正文 hash 查询。
- current view 或 current 查询只返回 current evidence。

### 11.4 Service 和 runner 测试

`test_m02_evidence_service.py` 和 `test_m02_evidence_runner.py` 覆盖：

| 场景 | 断言 |
| --- | --- |
| 新 clean record | 生成 current evidence |
| clean hash 不变 | 不重复生成新 evidence |
| clean hash 变化 | 旧 evidence superseded，新 evidence current，并有 supersedes link |
| clean record inactive | evidence inactive |
| quality issue 新增 | 生成 quality evidence |
| quality issue resolved | quality evidence inactive |
| comment sentence 新增 | comment_raw 与新 sentence link 正确 |
| 低价值评论 | confidence 低且不删除 |
| unknown 参数 | 低置信 evidence，不当 false |
| 卖点未覆盖 | 不生成 promo evidence，只生成 quality evidence |

### 11.5 API 测试

`test_m02_evidence_api.py` 覆盖：

- run API 返回 evidence/link 数量和低置信数量。
- summary API 可按 batch 查询。
- 单条 evidence API 返回 source/clean 追溯信息。
- links API 返回 has_sentence、has_dimension、same_comment 等关系。
- SKU evidence API 支持 type、confidence、current only 过滤。
- M01 batch 不存在或未完成时返回明确错误。

### 11.6 禁止越界测试

`test_m02_no_business_outputs.py` 必须断言：

- M02 不生成 `param_code`。
- M02 不生成 `claim_code`。
- M02 不生成 `task_code`。
- M02 不生成 `target_group_code`。
- M02 不生成 `battlefield_code`。
- M02 不生成候选、评分、三槽位或报告结论。
- M02 不把 quality evidence 当业务事实。
- M02 不把 comment_dimension 转成任务、客群、战场或卖点。

所有测试不得依赖外部 LLM 调用。

## 12. 205/85E7Q 验收

### 12.1 当前样例预期

以当前 205 样例数据为首次 full，M02 应能表达：

| 数据域 | 预期 |
| --- | --- |
| 市场 | 1326 条左右 `market_fact` |
| 参数 | 2843 条左右 `param_raw`，unknown/空值/`-` 降低置信度 |
| 卖点 | 65 条左右 `promo_raw`，并生成对应 `promo_sentence` |
| 评论 | 62426 条左右 `comment_raw`，并生成系统切句和 source segment evidence |
| 评论维度 | 62426 条左右 `comment_dimension`，空维度低置信或质量标记 |
| 质量问题 | 参数缺失、卖点覆盖缺失、评论重复、维度缺失等 quality evidence |

“左右”表示真实数量由 M01 清洗结果决定，验收应验证数量合理、覆盖完整和缺口解释准确，而不是固定死值。

### 12.2 85E7Q 验收

对 `85E7Q` / `TV00029115` 必须满足：

| 输入事实 | M02 验收 |
| --- | --- |
| 46 行周销 | 约 46 条 `market_fact` |
| 81 行属性 | 约 81 条 `param_raw`，unknown 降权 |
| 0 行结构化卖点 | 0 条 `promo_raw` 和 `promo_sentence` |
| 0 行结构化卖点 | 存在 `claim_coverage_missing` 的 `quality_issue` evidence |
| 3621 行评论 | 生成 `comment_raw`、`comment_sentence`、`comment_dimension` evidence |
| 评论重复 | 保留 `comment_id`、`comment_text_hash`、`segment_text_hash` 和重复 link |

M02 不得为 85E7Q 伪造宣传卖点 evidence。

### 12.3 评论关系验收

当前评论数据存在拆行和重复，M02 必须保留：

- `comment_id`
- `comment_text_hash`
- `segment_text_hash`
- `has_sentence` link
- `has_dimension` link
- `same_comment` link
- `same_comment_text` link
- `same_segment` link

去重、代表评论选择和观点聚合由 M05 负责。

### 12.4 业务含义验收

M02 输出必须能被解释为：

- “这条结论未来可以引用哪几条真实证据。”
- “这条证据来自哪张清洗表和哪条原始行。”
- “这条证据质量如何，是否低置信。”
- “卖点覆盖缺失是数据缺口，不是商品没有卖点。”
- “评论维度是弱标签，不是直接业务任务或战场。”

## 13. 完成标准

M02 编码完成必须满足：

1. `core3_evidence_atom`、`core3_evidence_link` 迁移、模型、schema、repository 已完成。
2. `evidence_key` 稳定，`evidence_id` 能表达 clean hash 版本。
3. M01 清洗事实有 evidence 或明确跳过原因。
4. evidence 可追溯到 M01 清洗行和 M00 来源行。
5. unknown evidence 与 false 证据严格区分。
6. quality evidence 只表达数据限制，不表达业务能力强弱。
7. 评论原文、评论句、评论维度、重复正文、质量问题之间 link 可查询。
8. 旧 evidence 逻辑失效，不物理删除。
9. 同一 `evidence_key` 只有一条 current evidence。
10. M02 runner 可返回 evidence 数量、link 数量、低置信数量和复核建议。
11. 85E7Q 不生成伪造卖点 evidence，有卖点缺失质量 evidence。
12. M02 不生成参数码、卖点码、任务、客群、战场、候选、评分或报告结论。
13. 后端测试通过，且测试不依赖 205 实库或外部 LLM。

## 14. 风险和回滚

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 只做 evidence atom 不做 link | 评论追溯关系不足 | 默认落 `core3_evidence_link`，若降级必须保留可重建字段 |
| `evidence_id` 设计成永远稳定 | clean hash 变化后历史不可追溯 | 区分 `evidence_key` 和版本化 `evidence_id` |
| quality evidence 被下游当业务事实 | 报告误导 | schema、service 和越界测试固化质量证据边界 |
| unknown 被当 false | 参数和卖点判断错误 | value_presence、低置信和单元测试固化 |
| current 多版本并存 | 下游引用混乱 | partial unique 或 service 检查 current 唯一 |
| comment link 数量过大 | 写入慢或查询慢 | 首版按必要 link 类型生成，必要时分批写入和索引优化 |
| M02 API 暴露 UUID 给高层页 | 界面不符合业务表达 | M02 只提供运营接口，M15 负责短证据编号 |
| 过早接入 M03-M15 | 证据不稳定造成返工 | M02 验收前不开发正式业务结论 |

回滚方式：

- migration downgrade 删除 M02 两张表和 current 视图，不触碰 M00/M01/原始四表。
- 若 M02 runner 失败，只标记 M02 module run 失败，不推进 M03。
- 若某 batch evidence 异常，保留失败批次供排查，不删除历史成功 evidence。

## 15. 下游依赖

| 下游模块 | 依赖 M02 的产物 |
| --- | --- |
| M03 | `param_raw` evidence、value presence、数字和单位候选、质量标记 |
| M04a | `promo_raw`、`promo_sentence`、`param_raw`、卖点缺失 quality evidence |
| M05 | `comment_raw`、`comment_sentence`、`comment_dimension` 和 comment links |
| M06 | M05 代表评论 evidence 和句级 evidence，不直接使用维度做结论 |
| M07 | `market_fact` evidence 的周期、渠道、平台、量价和质量状态 |
| M08 | 各域 current evidence、低置信和缺口信息 |
| M09-M11.5 | 经 M06/M08 转换后的业务信号，同时保留 evidence 引用 |
| M12-M14 | 候选、评分、选择结果必须保存 `evidence_ids` |
| M15 | 将 `evidence_id` 转成业务短编号和中文证据卡 |
| M16 | evidence 数量、current 唯一性、低置信比例、quality evidence、失效关系 |

## 16. 编码子任务建议

M02 编码建议拆为以下小闭环：

| 子任务 | 内容 | 建议验收 |
| --- | --- | --- |
| M02-A | migration 和 SQLAlchemy model | 两张表和 current 视图 upgrade/downgrade 通过 |
| M02-B | schema 和枚举 | evidence 类型、状态、link 类型 schema 测试通过 |
| M02-C | ID service 和 mapper | key/id、清洗表映射测试通过 |
| M02-D | payload builder 和 confidence service | 各 evidence 类型 payload 和置信度测试通过 |
| M02-E | repository | 幂等、current 唯一、superseded、inactive、link 查询测试通过 |
| M02-F | link builder | sentence、dimension、quality、duplicate link 测试通过 |
| M02-G | runner | 增量、失效、摘要、复核状态测试通过 |
| M02-H | API | run、summary、detail、links、sku evidence 测试通过 |
| M02-I | 越界和 fixture 验收 | 85E7Q 无伪造卖点 evidence，M02 不生成业务结论 |

编码阶段每次仍应只做一个小闭环。M02 完成并验收后，才进入 M03 参数字段画像与标准参数抽取开发任务。

## 17. 下次任务

下次应生成：

```text
docs/core3_mvp/real_data_v2/development/M03_development_tasks.md
```

M03 文档需要基于 `param_raw` evidence 和 M01 参数清洗事实，拆清参数字段画像、标准参数本体、参数值抽取、unknown/false 区分、单位规范化、参数证据置信度和下游 SKU 参数画像开发任务。
