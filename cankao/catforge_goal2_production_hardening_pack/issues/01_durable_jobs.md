# Issue 01 — Durable Jobs and Idempotency

Implement job_run/job_attempt persistence, idempotency, retries, checkpoints, cancellation, and diagnostics.

Acceptance: duplicate job submission does not duplicate results; transient failure retries; data contract failure does not retry indefinitely.
