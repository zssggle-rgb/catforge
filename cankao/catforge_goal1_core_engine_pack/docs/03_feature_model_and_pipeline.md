# Feature Model and Pipeline

## Feature extraction
The engine must create a normalized feature record per SKU, containing:
- `sku_identity`: sku_code, brand, model, category.
- `param_features`: normalized parameters.
- `claim_features`: raw claim fragments and extracted numeric facts.
- `comment_features`: topic counts, sentiment, product/service split.
- `market_features`: per-channel price, volume, amount, trend.
- `evidence`: source-level evidence items.

## Evidence model
Every extracted fact must have:
- `evidence_id`
- `source_type`: `param`, `claim`, `comment`, `market`, `derived`
- `source_ref`: file/row/column or imported source ID
- `raw_value`
- `normalized_value`
- `confidence`
- `created_at`

## Pipeline order
1. Normalize parameters.
2. Extract claim fragments and numeric facts.
3. Map comments to topics and sentiment.
4. Activate standard claims via rule DSL.
5. Score user tasks via rule DSL.
6. Score value battlefields via rule DSL.
7. Run competitor engine.
8. Write analytical results and evidence cards.

## Missing values
Missing means unknown. Do not treat missing boolean fields as false unless explicitly provided as false.
