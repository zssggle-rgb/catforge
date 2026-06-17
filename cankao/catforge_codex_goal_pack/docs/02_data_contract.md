# 02. Data Contract

This document defines the first MVP input contract. All imports must retain source provenance fields.

## Common required columns

Every imported record must include or be assigned:

| Field | Type | Required | Description |
|---|---|---:|---|
| project_id | uuid | yes | Category project ID |
| category_code | string | yes | Example: TV |
| source_file_id | uuid | yes | Uploaded file ID |
| raw_row_id | string | yes | Row ID inside source file |
| import_batch_id | uuid | yes | Import batch ID |

## 1. SKU master

Logical table: `raw_sku_master`

| Field | Type | Required | Notes |
|---|---|---:|---|
| sku_code | string | yes | Stable SKU/model code |
| brand | string | yes | Brand name |
| model_name | string | yes | Model name |
| series | string | no | Product series |
| category_name | string | yes | Raw category name |
| launch_date | date | no | Optional |
| product_url | string | no | Source URL if available |

## 2. SKU parameters

Logical table: `raw_sku_param`

Long-form is preferred.

| Field | Type | Required | Notes |
|---|---|---:|---|
| sku_code | string | yes | SKU code |
| raw_param_name | string | yes | Original field name |
| raw_param_value | string | no | Original value |
| raw_unit | string | no | Original unit if separate |
| source_channel | string | no | Channel/source |
| observed_at | datetime | no | Observation time |

Wide-form Excel may be accepted and normalized to long-form.

## 3. Marketing claims

Logical table: `raw_sku_claim`

| Field | Type | Required | Notes |
|---|---|---:|---|
| sku_code | string | yes | SKU code |
| claim_title | string | no | Claim title or bullet title |
| claim_text | string | yes | Raw marketing text |
| claim_order | integer | no | Display order |
| source_channel | string | no | Channel/source |
| observed_at | datetime | no | Observation time |

## 4. User comments

Logical table: `raw_sku_comment`

| Field | Type | Required | Notes |
|---|---|---:|---|
| sku_code | string | yes | SKU code |
| platform | string | no | JD/Tmall/Douyin/etc. |
| comment_id | string | no | Platform comment ID |
| comment_text | string | yes | Raw comment text |
| rating | number | no | Rating if available |
| comment_time | datetime | no | Comment time |
| dimension_1 | string | no | Existing dimension, if provided |
| dimension_2 | string | no | Existing dimension, if provided |
| dimension_3 | string | no | Existing dimension, if provided |

## 5. Market facts: channel, price, sales

Logical table: `raw_market_fact`

| Field | Type | Required | Notes |
|---|---|---:|---|
| sku_code | string | yes | SKU code |
| period | string | yes | Week/month, example: 2026W21 or 2026-05 |
| period_type | enum | yes | week/month |
| channel_group | string | yes | Online/offline |
| channel_type | string | yes | Professional e-commerce, content e-commerce, offline chain, etc. |
| channel_name | string | no | JD/Tmall/etc. |
| sales_volume | number | no | Units sold |
| sales_amount | number | no | Gross merchandise value or sales amount |
| avg_price | number | no | Average transaction price |
| promotion_flag | boolean | no | Promotion indicator if available |

## Data-quality rules

1. `sku_code`, `brand`, `model_name`, `category_code` must not be empty for SKU master.
2. Duplicate `(sku_code, brand, model_name)` rows should be flagged.
3. Numeric parsing failures must be flagged but must not abort the whole import.
4. Empty, `-`, `unknown`, null values must be represented as `unknown`, not `false`.
5. All rows must preserve source provenance.
