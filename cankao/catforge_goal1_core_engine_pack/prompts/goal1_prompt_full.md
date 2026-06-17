We already have a CatForge MVP with a running UI/scaffold. It is not production-ready because the analysis engine is shallow.

Goal 1: implement the production-grade core analysis engine vertical slice for TV category.

Read these files first:
- AGENTS.md and this pack's AGENTS.delta.md
- docs/01_goal1_scope.md
- docs/02_rule_dsl_spec.md
- docs/03_feature_model_and_pipeline.md
- docs/04_competitor_engine_spec.md
- docs/05_goldset_calibration_spec.md
- docs/06_goal1_acceptance_tests.md
- docs/07_api_contracts_goal1.md
- docs/08_data_model_migrations_goal1.md
- schemas/*.json
- examples/rules/*.yaml
- examples/fixtures/tv_market_fixture.csv
- examples/goldset/tv_gold_labels.csv
- examples/expected/goal1_expected_min.json

Implement:
1. A validated configurable YAML/JSON Rule DSL engine to replace hard-coded heuristics.
2. A normalized feature and evidence model for SKU parameters, claims, comments, market facts, claim activations, tasks, and battlefields.
3. A real competitor engine that computes candidate pools, component scores, direct/substitute/benchmark/potential competitor types, rankings, and evidence cards.
4. Gold Set label import, evaluation metrics, and simple bounded grid-search calibration for weights and thresholds.
5. Backend APIs and persistence required by docs/07 and docs/08.
6. Tests required by docs/06.

Constraints:
- Do not redesign the UI as the main deliverable.
- Do not require external LLM calls; deterministic rules first.
- Do not implement cross-category generation.
- Do not export factory-only logic.
- Every analytical output must include evidence_ids, confidence, rule_version, asset_version, and review_status when applicable.
- Missing values are unknown, not false.
- Insufficient comparable samples must return insufficient_sample or explicit insufficient_reasons, not strong conclusions.
- Preserve the existing app startup flow.

Acceptance:
- Existing app still starts.
- Rule DSL validates and executes.
- Sample fixture imports and runs end-to-end for TV00029115.
- Claim/task/battlefield outputs match examples/expected/goal1_expected_min.json at minimum.
- Competitor engine outputs ranked direct, benchmark, and substitute competitors with component_scores and evidence_ids.
- Gold Set evaluation report is generated.
- Tests pass.

Create a PR-quality implementation with clear commits, migration scripts, tests, and README updates.
