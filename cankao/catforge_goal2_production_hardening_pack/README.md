# CatForge Goal 2 — Production Hardening and Governance

This pack is for the second Codex Goal run. Run it after Goal 1 has implemented the core analysis engine.

## Goal
Harden CatForge for production use: durable jobs, idempotency, retries, checkpoints, version governance, audit, runtime export boundary, observability, and operational runbooks.

## Scope
Implement:
1. Durable job state machine with idempotency, fingerprints, retries, cancellation, checkpoints, concurrency locks.
2. Immutable asset/rule/version lifecycle: draft -> review -> released -> archived.
3. Audit events for data import, rule edits, evaluation, calibration, release, export, and rollback.
4. Runtime export strict whitelist and forbidden-pattern tests.
5. Observability: structured logs, metrics, health checks, job diagnostics.
6. Rollback metadata and runbook.

## Explicit non-goals for Goal 2
Do not rebuild the core engine from scratch. Do not implement cross-category generation. Do not expose factory-only tools in exports.

## Recommended branch
`goal-2-production-hardening`
