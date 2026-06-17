# Audit and Observability Specification

## Audit events
Create immutable audit events for:
- project creation
- dataset import
- rule creation/edit/activation
- Gold Set import
- evaluation run
- calibration run
- asset review approval/rejection
- release
- export
- rollback
- user permission change

## Audit fields
- `audit_id`
- `actor_id`
- `action`
- `object_type`
- `object_id`
- `project_id`
- `before_hash`
- `after_hash`
- `metadata_json`
- `created_at`

## Observability
- Structured JSON logs for jobs.
- Health endpoints: `/healthz`, `/readyz`.
- Metrics: job duration, failure count, retry count, rows processed, analysis throughput, export count.
- Job diagnostics endpoint returns stage timings, error summaries, checkpoint, and retry history.
