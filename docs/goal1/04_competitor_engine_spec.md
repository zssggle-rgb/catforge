# Real Competitor Engine Specification

## Purpose
Implement real competitor computation, not just configuration export.

## Input
- Target SKU.
- Market SKU pool.
- Normalized parameters.
- Activated standard claims.
- Task scores.
- Battlefield scores.
- Market facts by channel and time window.
- Competitor rules from `examples/rules/tv_competitor.yaml`.

## Candidate pool filtering
For each target SKU and battlefield:
1. Same category.
2. Exclude same SKU.
3. Include same or comparable channel.
4. Include a configurable price window, e.g. target avg_price ±20%.
5. Include comparable screen size bucket or configured parameter similarity.
6. Include recent active market window.
7. Include sufficient market facts; otherwise mark `insufficient_sample`.

## Component scores
All component scores must be 0-1:
- `price_similarity`
- `channel_overlap`
- `core_param_similarity`
- `standard_claim_similarity`
- `task_similarity`
- `battlefield_similarity`
- `sales_strength`
- `price_trend_risk`

## Final score
Weighted sum from configurable competitor rule.

## Competitor types
- `direct`: same battlefield, similar price/channel/core claims/tasks.
- `substitute`: same user task but different technology route, lower/higher price, or different claim composition.
- `benchmark`: stronger parameters, higher price, higher sales, or stronger battlefield score.
- `potential`: price trend/promotion/new SKU causes it to enter the target battlefield or price band.

## Output fields
- `target_sku_code`
- `competitor_sku_code`
- `battlefield_code`
- `competitor_type`
- `rank`
- `score`
- `component_scores`
- `evidence_ids`
- `confidence`
- `rule_version`
- `asset_version`
- `insufficient_reasons`

## Evidence card
For every competitor relation, generate a card containing price, channel, parameters, claims, task overlap, battlefield overlap, volume, and evidence references.
