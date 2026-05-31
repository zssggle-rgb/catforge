# Goal 2 Acceptance Tests

## Required tests
1. Submitting the same job twice with same idempotency key returns same job/result and does not duplicate rows.
2. Transient failure is retried with backoff.
3. Data contract failure is marked failed and not retried indefinitely.
4. Checkpointed job can resume or safely recompute without duplicate analytical results.
5. Concurrent release jobs for same project/category/version are locked.
6. Released rule/asset cannot be edited in place.
7. Changing a released asset creates a new draft version.
8. Runtime export of released asset produces only allowed files.
9. Export fails if forbidden file/pattern is included.
10. Audit events are created for rule edit, release, export, and rollback.
11. Rollback creates a new release manifest referencing a prior release.
12. Existing Goal 1 tests still pass.
