# Gold Set, Evaluation, and Calibration

## Gold Set types
Support expert labels for:
- standard claim activation
- user task score class
- battlefield membership
- competitor Top-N and competitor type

## Import format
See `schemas/gold_label.schema.json` and `examples/goldset/tv_gold_labels.csv`.

## Evaluation metrics
- Claim activation: precision, recall, F1.
- Task/battlefield classification: accuracy, macro F1, confusion matrix.
- Competitor ranking: Top-K hit rate, MRR, NDCG@K when enough labels exist.
- Competitor type: precision/recall/F1 per type.

## Calibration
Implement simple deterministic calibration:
- grid search over configured thresholds and component weights within bounded ranges.
- report before/after metrics.
- generate candidate YAML patch or new draft rule version.

## Guardrails
- Do not auto-release calibrated rules.
- If Gold Set is too small, output `insufficient_goldset` and only provide diagnostics.
- Keep raw expert labels internal; do not include them in runtime export.
