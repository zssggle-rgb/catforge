# Goal 2 Scope — Production Hardening and Governance

## Current expected state
Goal 1 has produced a working deterministic core engine: DSL rules, competitor computation, and Gold Set evaluation.

## Required outcome
After Goal 2, CatForge can be used for production-style batch analysis with reliable jobs, traceable versions, audit logs, safe runtime exports, and operational diagnostics.

## Acceptance summary
- Duplicate job submission is idempotent.
- Job failure can be retried or resumed from checkpoint.
- Contract/data errors fail fast and do not retry indefinitely.
- Released assets/rules are immutable.
- Asset diff and rollback metadata exist.
- Runtime export only contains whitelist files.
- Forbidden export tests pass.
- Audit events exist for sensitive operations.
