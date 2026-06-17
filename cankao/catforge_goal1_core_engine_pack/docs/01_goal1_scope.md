# Goal 1 Scope — Core Analysis Engine

## Current gap
The MVP has UI and workflow shells, but production-critical logic is shallow:
- Claim/task/battlefield rules are mostly hard-coded heuristics.
- Competitor engine is not really implemented.
- Rule weights and thresholds are not calibrated with expert labels.
- Outputs are not consistently evidence-backed and versioned.

## Required outcome
After Goal 1, CatForge must run a deterministic TV category pipeline:

`raw SKU data -> normalized features -> claim activation -> task/battlefield scores -> competitor results -> evidence cards -> evaluation report`

## Acceptance summary
- Modify YAML rules and observe score changes without code changes.
- Import fixture data and generate parameter/claim/comment evidence.
- Generate standard claim activations with scores and evidence IDs.
- Generate task and battlefield scores.
- Generate ranked direct/substitute/benchmark/potential competitors.
- Import expert Gold Set labels and output evaluation metrics.
- Generate a calibration report and candidate rule threshold updates.
