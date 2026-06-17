# Goal 1 Data Model Additions

Add migrations or equivalent persistence for:

## rule_set
- id
- rule_set_id
- category
- rule_type
- version
- status
- content_yaml
- content_hash
- validation_status
- created_at
- created_by

## evidence_item
- evidence_id
- project_id
- sku_code
- source_type
- source_ref
- raw_value
- normalized_value
- confidence
- created_at

## sku_claim_result
- project_id
- sku_code
- claim_code
- score
- confidence
- evidence_ids
- rule_version
- asset_version
- review_status

## sku_task_score
- project_id
- sku_code
- task_code
- score
- confidence
- evidence_ids
- rule_version
- asset_version

## sku_battlefield_score
- project_id
- sku_code
- battlefield_code
- score
- relationship_type
- confidence
- evidence_ids
- rule_version
- asset_version

## sku_competitor_result
- project_id
- target_sku_code
- competitor_sku_code
- battlefield_code
- competitor_type
- rank
- score
- component_scores
- evidence_ids
- confidence
- rule_version
- asset_version

## gold_label
- project_id
- label_type
- target_sku_code
- candidate_code
- expected_label
- expected_score_class
- expert_id
- notes

## evaluation_run
- project_id
- evaluation_type
- metric_json
- input_rule_versions
- created_at
