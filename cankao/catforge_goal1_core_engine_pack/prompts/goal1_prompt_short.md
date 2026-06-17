Goal 1: turn CatForge MVP into a real TV analysis engine.

Implement configurable Rule DSL, evidence-backed feature pipeline, real competitor engine, Gold Set evaluation/calibration, and tests. Use this pack's docs, schemas, rules, fixture, and expected output. Do not redesign UI or add external LLM dependency. Every analytical output needs evidence_ids, confidence, rule_version, asset_version. Missing values are unknown. Acceptance: fixture runs end-to-end; TV00029115 gets claim/task/battlefield results and ranked direct/benchmark/substitute competitors; Gold Set report works; tests pass.
