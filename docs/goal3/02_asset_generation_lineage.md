# 02 Asset Generation Lineage

Every library must show its source basis. A row that does not explain where it came from is not production-ready.

## Source-to-Asset Matrix

| Asset | Primary source data | Secondary source data | Generated via | Human review focus |
|---|---|---|---|---|
| Standard parameter library | raw SKU parameter fields and values | derived params from claim text | field discovery, alias clustering, unit parsing, level inference | high-frequency unmapped fields, conflicting values, high-value low-coverage fields |
| Standard claim library | raw promotional claims | normalized params, comments, market metrics | claim splitting, entity extraction, semantic clustering, activation rule generation | new marketing terms, low-confidence clusters, high-value claims |
| Comment topic library | raw comments | claims/tasks | sentence splitting, topic classification, sentiment, product/service separation | ambiguous topics, service/product confusion, high-frequency new themes |
| User task library | claims, params, comment topics | price/channel/sales | seed ontology + co-occurrence + expert labeling | task names, boundaries, over-broad tasks |
| Target group library | task results | price/channel/comment wording | task-to-group inference | business terminology and grouping |
| Battlefield library | tasks, target groups, claim bundles | price/channel/sales/competitor density | battlefield candidate generation and scoring | battlefields too broad/too narrow |
| Mapping rules | all above | expert review | semantic graph generation | wrong direction, weak evidence, over-weighted mappings |
| SKU results | released assets + 1000-SKU facts | market facts/comments | runtime scoring | high-value SKU low confidence |
| Calibration report | SKU results + market facts + reviews | gold labels | aggregation and metric computation | interpretation and release decision |

## Lineage fields

Every generated asset must have:
- source_dataset_id
- source_batch_id
- source_row_refs or evidence_ids
- generation_method: seed | rule | cluster | llm_suggested | expert_curated | market_calibrated
- confidence
- review_status: pending | approved | rejected | needs_split | needs_merge | deprecated
- asset_version
- created_at
- updated_at

## Production rule

Do not show only final labels. Show evidence, examples, coverage, and review state.
