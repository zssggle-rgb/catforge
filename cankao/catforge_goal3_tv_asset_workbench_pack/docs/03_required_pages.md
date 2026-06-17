# 03 Required Pages

The current dashboard cards are insufficient. Add these production workbench pages.

## 1. Data Overview

Show:
- SKU count
- brand count
- channel count
- time range
- raw parameter row count
- raw claim row count
- raw comment row count
- market fact row count
- missing field rates
- duplicate SKU/model counts
- unmapped parameter fields
- unmapped claim clusters

## 2. Standard Parameter Library

Table columns:
- param_code, param_name, group, type, unit
- raw_aliases
- normalize_rule
- level_rule
- coverage_rate
- unknown_rate
- mapped_claims
- examples
- confidence
- review_status
- version

Actions:
- approve/reject
- merge aliases
- split parameter
- edit level rule
- view evidence
- publish to draft asset version

## 3. Standard Claim Library

Table columns:
- claim_code, claim_name, group
- activation_rule
- raw_keywords
- supporting_params
- mapped_tasks
- mapped_battlefields
- coverage_rate
- PSI/SSI/CPI
- sample_sufficiency
- example raw claims
- confidence
- review_status

Actions:
- approve/reject
- merge/split claim cluster
- edit activation rule
- map to task/battlefield
- view evidence and example SKUs

## 4. Comment Topic Library

Show topics, product/service separation, sentiment, examples, mention rates, mapped claims/tasks.

## 5. User Task Library

Show task definitions, positive/negative signals, mapped target groups, mapped battlefields, scoring rule, example SKUs.

## 6. Target Group Library

Show group definitions, source tasks, price/channel/comment signals, example SKUs.

## 7. Value Battlefield Library

Show battlefield definitions, core tasks, core claims, entry rules, thresholds, market density, example SKUs.

## 8. Mapping Rules Workbench

Graph/table view for:
- param -> claim
- claim -> task
- comment_topic -> claim/task
- task -> target_group
- task/claim -> battlefield

Every edge must have weight, evidence basis, confidence, and review status.

## 9. SKU Analysis Results

Table across all 1000 SKUs:
- sku_code, brand, model
- price band, channels, sales volume, sales amount
- top activated claims
- top user tasks
- target groups
- battlefield assignments
- claim value layers
- direct competitor count
- review flags
- confidence

Drill down to single SKU.

## 10. Single SKU Detail

Sections:
- SKU signal card
- normalized parameters
- activated claims
- comment evidence
- task scores
- target group scores
- battlefield scores
- claim value layers
- competitor relationships
- evidence cards
- report preview

## 11. Competitor Results

Per battlefield:
- direct competitors
- substitute competitors
- benchmark competitors
- potential competitors
- score components
- evidence cards

## 12. Market Calibration Report

Show:
- parameter coverage
- claim coverage
- comment topic coverage
- PSI price support
- SSI sales support
- CPI comment perception
- sample sufficiency
- expert review summary
- evaluation metrics
- release recommendation

## 13. Runtime Asset Export Preview

Show export manifest and file list. Must enforce export whitelist.
