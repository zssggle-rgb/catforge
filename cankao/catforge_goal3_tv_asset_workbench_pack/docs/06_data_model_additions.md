# 06 Data Model Additions

Add tables or equivalent persisted models.

## category_asset_parameter
- id
- project_id
- param_code
- param_name
- param_group
- data_type
- unit
- raw_aliases_json
- normalize_rule_json
- level_rule_json
- business_meaning
- mapped_claim_codes_json
- coverage_rate
- unknown_rate
- example_raw_fields_json
- example_raw_values_json
- evidence_ids_json
- generation_method
- confidence
- review_status
- asset_version

## category_asset_claim
- id
- project_id
- claim_code
- claim_name
- claim_group
- definition
- activation_rule_json
- raw_keywords_json
- supporting_param_codes_json
- comment_topic_codes_json
- mapped_task_codes_json
- mapped_battlefield_codes_json
- coverage_rate
- psi_price_support
- ssi_sales_support
- cpi_comment_perception
- sample_sufficiency
- example_raw_claims_json
- evidence_ids_json
- generation_method
- confidence
- review_status
- asset_version

## category_asset_comment_topic
similar fields for topics.

## category_asset_user_task
similar fields for tasks.

## category_asset_target_group
similar fields for target groups.

## category_asset_battlefield
similar fields for battlefields.

## category_asset_mapping
- source_type
- source_code
- target_type
- target_code
- relation_type
- weight
- condition_json
- evidence_basis_json
- confidence
- review_status
- asset_version

## sku_analysis_result
- sku_code
- top_claims_json
- task_scores_json
- target_group_scores_json
- battlefield_scores_json
- claim_value_layers_json
- competitor_summary_json
- evidence_ids_json
- confidence
- review_flags_json
- rule_version
- asset_version

## sku_competitor_result
- target_sku_code
- competitor_sku_code
- battlefield_code
- competitor_type
- rank
- score
- component_scores_json
- evidence_ids_json
- confidence
- rule_version
- asset_version

## market_calibration_report
- project_id
- asset_version
- parameter_coverage_json
- claim_coverage_json
- psi_json
- ssi_json
- cpi_json
- sample_sufficiency_json
- review_summary_json
- evaluation_metrics_json
- release_recommendation
