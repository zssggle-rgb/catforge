# 11 契约与 Schema 规格

## 1. 目标

本文件把 `/goal` 实现中需要固定的结构契约列清，避免执行阶段临时发明字段。

契约包括：

- SQLAlchemy models。
- Pydantic request/response。
- seed v0.2 schema。
- diagnostics schema。
- evidence card schema。

## 2. SQLAlchemy Models

所有新增表放在 `apps/api-server/app/models/entities.py`，并由 `0004_tv_core3_mvp.py` 创建。

### 2.1 `Core3PipelineRun`

表名：`core3_pipeline_run`

字段：

```text
run_id String(36) pk
project_id ForeignKey(category_project.project_id) index not null
category_code String(40) not null default "TV"
status String(40) not null
scope String(40) not null
target_sku_code String(120) nullable index
input_fingerprint String(120) not null index
rule_version String(80) not null
counts JSON default {}
warnings JSON default []
diagnostics JSON default {}
started_at DateTime nullable
finished_at DateTime nullable
created_at DateTime
updated_at DateTime
```

唯一约束：

```text
project_id, scope, target_sku_code, input_fingerprint
```

状态枚举：

- `running`
- `completed`
- `failed`
- `completed_empty`

### 2.2 `Core3SkuMarketProfile`

表名：`core3_sku_market_profile`

字段：

```text
profile_id String(36) pk
run_id ForeignKey(core3_pipeline_run.run_id) index not null
project_id ForeignKey(category_project.project_id) index not null
category_code String(40) not null default "TV"
sku_code String(120) index not null
brand String(120) nullable
model_name String(160) nullable
series String(120) nullable
price_wavg_12m Float nullable
price_latest Float nullable
sales_volume_12m Float nullable
sales_amount_12m Float nullable
channel_share JSON default {}
price_drop_rate_3m Float nullable
sales_growth_3m Float nullable
price_percentile Float nullable
sales_percentile Float nullable
sales_amount_percentile Float nullable
evidence_ids JSON default []
missing_signals JSON default []
confidence Float not null default 0.0
created_at DateTime
updated_at DateTime
```

唯一约束：

```text
run_id, sku_code
```

### 2.3 `Core3SkuFeatureProfile`

表名：`core3_sku_feature_profile`

字段：

```text
feature_id String(36) pk
run_id ForeignKey(core3_pipeline_run.run_id) index not null
project_id ForeignKey(category_project.project_id) index not null
category_code String(40) not null default "TV"
sku_code String(120) index not null
standard_params JSON default {}
claim_activations JSON default []
comment_topics JSON default []
task_scores JSON default []
target_group_scores JSON default []
battlefield_scores JSON default []
feature_evidence_ids JSON default []
extraction_diagnostics JSON default {}
missing_signals JSON default []
confidence Float not null default 0.0
created_at DateTime
updated_at DateTime
```

唯一约束:

```text
run_id, sku_code
```

### 2.4 `Core3CompetitorCandidate`

表名：`core3_competitor_candidate`

字段：

```text
candidate_id String(36) pk
run_id ForeignKey(core3_pipeline_run.run_id) index not null
project_id ForeignKey(category_project.project_id) index not null
category_code String(40) not null default "TV"
target_sku_code String(120) index not null
candidate_sku_code String(120) index not null
battlefield_code String(140) nullable index
gate_status String(40) not null
gate_reasons JSON default []
component_scores JSON default {}
slot_scores JSON default {}
evidence_ids JSON default []
confidence Float not null default 0.0
created_at DateTime
updated_at DateTime
```

唯一约束：

```text
run_id, target_sku_code, candidate_sku_code
```

### 2.5 `Core3CompetitorResult`

表名：`core3_competitor_result`

字段：

```text
result_id String(36) pk
run_id ForeignKey(core3_pipeline_run.run_id) index not null
project_id ForeignKey(category_project.project_id) index not null
category_code String(40) not null default "TV"
target_sku_code String(120) index not null
role String(60) index not null
competitor_sku_code String(120) nullable index
battlefield_code String(140) nullable index
score Float not null default 0.0
component_scores JSON default {}
reason Text nullable
confidence Float not null default 0.0
confidence_level String(20) not null default "low"
review_flag Boolean not null default false
insufficient_reasons JSON default []
evidence_ids JSON default []
evidence_card JSON default {}
rule_version String(80) not null
asset_version String(80) not null default "core3-mvp-0.1.0"
created_at DateTime
updated_at DateTime
```

唯一约束：

```text
run_id, target_sku_code, role
```

服务层还要保证非空 `competitor_sku_code` 不在同一 target 中重复。

### 2.6 `Core3EvidenceCard`

表名：`core3_evidence_card`

字段：

```text
card_id String(36) pk
result_id ForeignKey(core3_competitor_result.result_id) index nullable
run_id ForeignKey(core3_pipeline_run.run_id) index not null
project_id ForeignKey(category_project.project_id) index not null
target_sku_code String(120) index not null
competitor_sku_code String(120) nullable index
role String(60) not null
evidence_categories JSON default []
card_json JSON default {}
evidence_ids JSON default []
created_at DateTime
updated_at DateTime
```

唯一约束：

```text
run_id, target_sku_code, role
```

## 3. Pydantic API Schemas

文件：`apps/api-server/app/schemas/core3_mvp.py`

### 3.1 Requests

```python
class Core3RunRequest(BaseModel):
    target_sku_code: str | None = None
    target_model: str | None = None
    batch: bool = False
    force_recompute: bool = False
```

校验：

- `batch=false` 时，`target_sku_code` 或 `target_model` 必填。
- `batch=true` 时忽略 target 字段。

### 3.2 Common

```python
class Core3SkuIdentity(BaseModel):
    sku_code: str
    brand: str | None = None
    model_name: str | None = None
    series: str | None = None
```

```python
class Core3EvidenceRef(BaseModel):
    evidence_id: str
    source_type: str
    field_name: str | None = None
    raw_value: Any = None
    normalized_value: Any = None
    confidence: float
```

### 3.3 Data Status

```python
class Core3DataStatusOut(BaseModel):
    project_id: str
    category_code: str
    sku_count: int
    brand_count: int
    channel_count: int
    market_fact_count: int
    param_row_count: int
    claim_row_count: int
    comment_row_count: int
    missing_summary: dict[str, int]
    latest_run: dict[str, Any] | None = None
```

### 3.4 Run

```python
class Core3RunOut(BaseModel):
    run_id: str
    status: str
    scope: str
    target_sku_code: str | None = None
    counts: dict[str, int | float]
    warnings: list[str]
    diagnostics: dict[str, Any] = {}
    latest_report_ref: str | None = None
```

### 3.5 Report

```python
class Core3SkuReportOut(BaseModel):
    project_id: str
    run_id: str
    target_sku: Core3SkuIdentity
    market_profile: dict[str, Any]
    standard_params: dict[str, Any]
    activated_claims: list[dict[str, Any]]
    comment_topics: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    target_groups: list[dict[str, Any]]
    battlefields: list[dict[str, Any]]
    core_competitors: list[dict[str, Any]]
    extraction_diagnostics: dict[str, Any] = {}
    confidence_level: str
    review_flag: bool
    insufficient_reasons: list[str]
```

## 4. Seed v0.2 Schema

Top level：

```json
{
  "version": "core3-mvp-0.2.0",
  "category_code": "TV",
  "standard_params": [],
  "standard_claims": [],
  "comment_topics": [],
  "user_tasks": [],
  "target_groups": [],
  "battlefields": []
}
```

### 4.1 Standard Param

Required：

```json
{
  "param_code": "screen_size_inch",
  "param_name": "屏幕尺寸",
  "param_group": "display_basic",
  "data_type": "number",
  "unit": "inch",
  "aliases": [],
  "value_parsers": [],
  "source_priority": ["raw_param", "claim_text", "model_name"],
  "evidence_requirement": ["raw_value_or_text_match"],
  "mapped_claim_codes": []
}
```

### 4.2 Standard Claim

Required：

```json
{
  "claim_code": "CLAIM_HIGH_BRIGHTNESS_HDR",
  "claim_name": "高亮 HDR",
  "claim_group": "picture",
  "definition": "",
  "supporting_param_codes": [],
  "promo_keywords": [],
  "comment_topic_codes": [],
  "activation_rule": {},
  "activation_weights": {"param": 0.55, "promo": 0.35, "comment": 0.10},
  "mapped_task_codes": [],
  "mapped_battlefield_codes": [],
  "evidence_requirement": ["param_or_promo"]
}
```

### 4.3 Comment Topic

Required：

```json
{
  "topic_code": "TOPIC_PICTURE_QUALITY",
  "topic_name": "画质体验",
  "topic_group": "product_experience",
  "keywords": [],
  "positive_keywords": [],
  "negative_keywords": [],
  "mapped_claim_codes": [],
  "mapped_task_codes": [],
  "activates_product_claim": true
}
```

### 4.4 Task

Required：

```json
{
  "task_code": "TASK_GAMING_ENTERTAINMENT",
  "task_name": "游戏娱乐",
  "definition": "",
  "positive_claim_codes": [],
  "positive_param_codes": [],
  "comment_topic_codes": [],
  "market_signals": [],
  "score_rule": {"claim": 0.4, "param": 0.25, "comment": 0.2, "market": 0.15},
  "default_target_group_codes": [],
  "battlefield_codes": []
}
```

### 4.5 Target Group

Required：

```json
{
  "target_group_code": "TG_GAMER",
  "target_group_name": "游戏用户",
  "definition": "",
  "source_task_codes": [],
  "market_fit_rule": {}
}
```

### 4.6 Battlefield

Required：

```json
{
  "battlefield_code": "BF_GAMING_SPORTS",
  "battlefield_name": "游戏体育战场",
  "definition": "",
  "core_task_codes": [],
  "core_claim_codes": [],
  "core_param_codes": [],
  "comment_topic_codes": [],
  "required_signal_rule": {},
  "semantic_market_weights": {"semantic": 0.65, "market": 0.35},
  "market_score_rule": {},
  "entry_thresholds": {"main": 0.75, "secondary": 0.55, "weak": 0.35}
}
```

## 5. Diagnostics Schema

`core3_sku_feature_profile.extraction_diagnostics`：

```json
{
  "field_mappings": [
    {
      "raw_param_name": "峰值亮度",
      "matched_param_code": "peak_brightness_nits",
      "match_type": "exact_alias",
      "confidence": 0.95,
      "coverage": 0.62,
      "examples": ["1200nits"]
    }
  ],
  "param_conflicts": [],
  "candidate_param_aliases": [],
  "candidate_claims": [],
  "candidate_comment_topics": [],
  "missing_signals": []
}
```

Candidate alias：

```json
{
  "raw_param_name": "动态补偿",
  "suggested_param_code": "motion_compensation_flag",
  "coverage": 0.24,
  "examples": ["支持MEMC"],
  "confidence": 0.72,
  "review_status": "pending"
}
```

Candidate claim：

```json
{
  "raw_phrase": "AI画质芯片",
  "suggested_claim_group": "picture",
  "coverage": 0.18,
  "example_skus": [],
  "evidence_ids": [],
  "confidence": 0.68,
  "review_status": "pending"
}
```

Candidate topic：

```json
{
  "raw_phrase": "开机广告",
  "suggested_topic_group": "product_risk",
  "coverage": 0.12,
  "sample_sentences": [],
  "sentiment_hint": "negative",
  "evidence_ids": [],
  "confidence": 0.74,
  "review_status": "pending"
}
```

## 6. Evidence Card Schema

```json
{
  "target": {
    "sku_code": "TV00029115",
    "brand": "Hisense",
    "model_name": "85E7Q"
  },
  "competitor": {
    "sku_code": "TV00030001",
    "brand": "TCL",
    "model_name": "85Q10"
  },
  "role": "direct",
  "reason_summary": "",
  "component_scores": {},
  "price_comparison": {},
  "sales_comparison": {},
  "channel_overlap": {},
  "param_comparison": {},
  "claim_comparison": {},
  "task_battlefield_similarity": {},
  "comment_evidence": {},
  "evidence_categories": ["price", "sales", "channel", "param", "claim"],
  "evidence_ids": []
}
```

Required evidence category for high confidence:

- at least 4 categories.

Required evidence category for medium confidence:

- at least 3 categories.

