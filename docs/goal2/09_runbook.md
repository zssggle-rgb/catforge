# Production Runbook

## Normal release flow
1. Run analysis.
2. Run evaluation.
3. Review quality gates.
4. Submit assets to review.
5. Approve release.
6. Export runtime package.
7. Verify export manifest.

### API sequence
1. `POST /api/jobs` with `job_type=analysis_run` and an `idempotency_key`.
2. `POST /api/jobs` with `job_type=evaluation_run`, or `POST /api/projects/{project_id}/evaluation/run`.
3. `POST /api/assets/versions` to create a draft release manifest.
4. `POST /api/assets/{asset_id}/submit-review`.
5. `POST /api/assets/{asset_id}/approve`.
6. `POST /api/assets/{asset_id}/release`.
7. `POST /api/projects/{project_id}/runtime-export` with the released `asset_version_id`.
8. `GET /api/exports/{export_id}` and inspect `manifest_json.files`.

## Failed job recovery
- Check diagnostics endpoint.
- If transient, retry.
- If data contract error, fix data and submit new job with new input fingerprint.
- If partial writes occurred, rely on idempotent upserts or checkpoint recovery.

### Diagnostics checklist
- `GET /api/jobs/{job_id}/diagnostics` for checkpoint, retry history, error summary, and stage timing.
- Contract errors use `error_code=contract_error` and should not be retried in place.
- Transient errors record `retry_after_seconds` in `job_attempt`.
- Cancel a queued/running job through `POST /api/jobs/{job_id}/cancel`.

## Rollback
- Identify prior released manifest.
- Create rollback release referencing prior manifest.
- Export rollback runtime package.
- Audit event must record rollback reason.

### Rollback API
Use `POST /api/assets/{asset_id}/rollback` with `target_version_id` and `reason`.
Rollback creates a new released `asset_version` and does not mutate the old release.

## Archive
Use `POST /api/assets/{asset_id}/archive` with a `reason` after a version should no longer be used for new jobs.
Archived versions are read-only and cannot be edited, approved, or released.

## Export security check
Before sharing an export, verify whitelist and forbidden-pattern tests pass.

### Export boundary checks
- Allowed file names are versioned in `examples/goal2/exports/allowed_files.txt`.
- Forbidden content patterns are versioned in `examples/goal2/exports/forbidden_patterns.txt`.
- The export endpoint refuses unreleased asset versions unless `allow_draft=true` is explicitly passed for development.
- Every runtime export writes an audit event with action `runtime_export_created`.

## Observability
- `GET /healthz` checks process liveness.
- `GET /readyz` checks database readiness.
- `GET /api/metrics` returns basic job/export counters.
- Structured job logs are emitted by the job service as JSON strings under logger `catforge.jobs`.

## Audit
- Query audit events through `GET /api/audit`.
- Rule edits, Gold Set imports, evaluation, calibration, release, export, rollback, archive, project creation, and dataset import are written automatically.
- Permission changes can be recorded through `POST /api/audit/permission-change` with `user_id`, `before`, `after`, and `reason`.
