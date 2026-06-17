Goal 2: harden CatForge for production use after Goal 1 core engine is implemented.

Read these files first:
- AGENTS.md and this pack's AGENTS.delta.md
- docs/01_goal2_scope.md
- docs/02_job_reliability_spec.md
- docs/03_version_governance_spec.md
- docs/04_runtime_export_boundary_spec.md
- docs/05_audit_observability_spec.md
- docs/06_goal2_acceptance_tests.md
- docs/07_api_contracts_goal2.md
- docs/08_data_model_migrations_goal2.md
- docs/09_runbook.md
- schemas/*.json
- examples/manifests/runtime_asset_manifest.example.json
- examples/exports/allowed_files.txt
- examples/exports/forbidden_patterns.txt

Implement production hardening around the existing MVP and Goal 1 engine:
1. Durable job state machine with idempotency_key, input_fingerprint, retries, checkpointing, cancellation, concurrency locks, and diagnostics.
2. Asset/rule version governance with draft -> in_review -> released -> archived lifecycle, immutability, diff, release manifests, and rollback metadata.
3. Audit events for project/data/rule/evaluation/calibration/release/export/rollback actions.
4. Runtime export with strict whitelist and forbidden-pattern scanning. Export only approved runtime files.
5. Observability: structured logs, health/readiness endpoints, basic metrics, and job diagnostics.
6. Tests required by docs/06.

Constraints:
- Preserve Goal 1 core engine behavior and tests.
- Do not rebuild the core engine from scratch.
- Do not export prompt templates, Gold Set builders, raw expert annotations, rule generators, category generators, cross-category migration templates, or factory-only scripts.
- Released versions must be immutable. Any change creates a new draft version.
- Failed jobs must be explicit and recoverable; do not mark partial failures as success.

Acceptance:
- Existing app still starts.
- Goal 1 tests still pass.
- Duplicate job submission is idempotent.
- Retry/checkpoint/cancel behavior is tested.
- Released assets/rules cannot be edited in place.
- Runtime export whitelist and forbidden-pattern tests pass.
- Audit events are generated for rule edit, release, export, and rollback.
- README/runbook updated.

Create a PR-quality implementation with migrations, tests, and documentation updates.
