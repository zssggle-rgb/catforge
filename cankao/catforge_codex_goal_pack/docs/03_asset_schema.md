# 03. Asset Schema

This document defines the MVP asset schemas. Store definitions in tables and support export to CSV/YAML/JSON.

## Standard parameter definition: `std_param_def`

| Field | Type | Required | Description |
|---|---|---:|---|
| param_id | uuid | yes | Internal ID |
| project_id | uuid | yes | Project ID |
| category_code | string | yes | Category code |
| param_code | string | yes | Stable code, e.g. screen_size_inch |
| param_name | string | yes | Human readable name |
| param_group | string | yes | Display/backlight/gaming/audio/smart/etc. |
| data_type | enum | yes | number/string/enum/boolean/text |
| unit | string | no | inch/Hz/nits/GB/etc. |
| raw_aliases | json array | yes | Raw field aliases |
| normalize_rule | json | yes | Parsing and normalization rule |
| level_rule | json | no | Banding rule |
| business_meaning | text | no | Meaning for analysis |
| mapped_claim_codes | json array | no | Related claim codes |
| evidence_weight | number | yes | Default evidence weight 0-1 |
| status | enum | yes | candidate/approved/deprecated |
| version | string | yes | Asset version |

## Standard claim definition: `std_claim_def`

| Field | Type | Required | Description |
|---|---|---:|---|
| claim_id | uuid | yes | Internal ID |
| project_id | uuid | yes | Project ID |
| category_code | string | yes | Category code |
| claim_code | string | yes | Stable code |
| claim_name | string | yes | Human readable name |
| claim_group | string | yes | picture/gaming/eye-care/audio/smart/design/price/etc. |
| definition | text | yes | Business definition |
| activation_rule | json | yes | Rule to activate this claim for a SKU |
| raw_keywords | json array | yes | Keywords and aliases |
| supporting_param_codes | json array | no | Parameter evidence |
| comment_topic_codes | json array | no | Comment evidence |
| mapped_task_codes | json array | no | Related tasks |
| mapped_battlefield_codes | json array | no | Related battlefields |
| default_layer_hint | enum | no | baseline/performance/premium_signal/weak_perception |
| confidence_rule | json | no | Confidence scoring rule |
| status | enum | yes | candidate/approved/deprecated |
| version | string | yes | Asset version |

## Comment topic definition: `comment_topic_def`

| Field | Type | Required | Description |
|---|---|---:|---|
| topic_code | string | yes | Stable code |
| topic_name | string | yes | Topic name |
| topic_group | string | yes | product_experience/service_experience/price/logistics/etc. |
| keywords | json array | yes | Keywords and phrases |
| sentiment_hint | enum | no | positive/negative/neutral/mixed |
| mapped_claim_codes | json array | no | Related claims |
| mapped_task_codes | json array | no | Related tasks |
| activates_product_claim | boolean | yes | False for service/logistics topics |
| status | enum | yes | candidate/approved/deprecated |
| version | string | yes | Asset version |

## User task definition: `user_task_def`

| Field | Type | Required | Description |
|---|---|---:|---|
| task_code | string | yes | Stable code |
| task_name | string | yes | User task name |
| definition | text | yes | Business definition |
| positive_claim_codes | json array | yes | Claims that support the task |
| positive_param_codes | json array | no | Parameters that support the task |
| comment_topic_codes | json array | no | Comment topics that support the task |
| default_target_group_codes | json array | no | Related target groups |
| battlefield_codes | json array | no | Related battlefields |
| score_rule | json | yes | Weighting rule |
| status | enum | yes | candidate/approved/deprecated |
| version | string | yes | Asset version |

## Battlefield definition: `battlefield_def`

| Field | Type | Required | Description |
|---|---|---:|---|
| battlefield_code | string | yes | Stable code |
| battlefield_name | string | yes | Name |
| definition | text | yes | Business definition |
| required_signal_rule | json | no | Required signal rule |
| score_rule | json | yes | Weighted scoring rule |
| entry_thresholds | json | yes | main/secondary/opportunity/weak thresholds |
| competitor_rule_ref | string | no | Rule set reference |
| status | enum | yes | candidate/approved/deprecated |
| version | string | yes | Asset version |

## Review queue item: `review_queue`

| Field | Type | Required | Description |
|---|---|---:|---|
| review_id | uuid | yes | Review item ID |
| project_id | uuid | yes | Project ID |
| category_code | string | yes | Category code |
| item_type | enum | yes | param/claim/comment_topic/task/battlefield/competitor/export |
| item_key | string | yes | Entity key |
| reason_code | string | yes | conflict/low_confidence/new_term/high_value_sku/insufficient_sample/etc. |
| evidence_ids | json array | no | Evidence references |
| candidate_payload | json | yes | Candidate object |
| confidence | number | yes | 0-1 |
| priority | enum | yes | low/medium/high/critical |
| status | enum | yes | pending/approved/rejected/edited |
| reviewer | string | no | Reviewer |
| decision_payload | json | no | Approved/edited object |

## Runtime asset package whitelist

The export package may include only:

- `std_param_def.csv`
- `std_claim_def.csv`
- `comment_topic_def.csv`
- `user_task_def.csv`
- `target_group_def.csv`
- `battlefield_def.csv`
- `mapping_rules.csv`
- `scoring.yaml`
- `competitor_rule.yaml`
- `sample_sku_results.parquet` or `.csv`
- `sample_evidence_cards.jsonl`
- `asset_readme.md`
- `release_note.md`

It must not include:

- Generation scripts
- Prompt templates
- Gold Set builder code
- Evaluation datasets unless explicitly approved
- Cross-category migration templates
- Internal factory configs
