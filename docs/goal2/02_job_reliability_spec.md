# Durable Job Reliability Specification

## Job types
- data_import
- data_profile
- analysis_run
- competitor_run
- evaluation_run
- calibration_run
- asset_release
- runtime_export

## Job state machine
- `queued`
- `running`
- `retrying`
- `succeeded`
- `failed`
- `cancel_requested`
- `cancelled`
- `blocked`

## Required job fields
- `job_id`
- `job_type`
- `project_id`
- `idempotency_key`
- `input_fingerprint`
- `status`
- `attempt_count`
- `max_attempts`
- `checkpoint_json`
- `error_code`
- `error_message`
- `created_at`
- `started_at`
- `finished_at`
- `created_by`

## Idempotency
If a job with the same `project_id`, `job_type`, `idempotency_key`, and `input_fingerprint` already succeeded, return the existing result. Do not duplicate writes.

## Retry policy
- Retry transient errors: database timeout, worker restart, temporary file IO.
- Do not retry user/data contract errors: invalid schema, missing required column, invalid rule DSL.
- Use exponential backoff.

## Checkpoints
Long-running jobs must write checkpoints after major stages. Re-run must resume or safely recompute without duplicating analytical results.

## Concurrency locks
Only one release/export job per project/category/version can run at a time.
