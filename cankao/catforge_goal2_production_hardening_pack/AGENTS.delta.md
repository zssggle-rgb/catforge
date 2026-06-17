# AGENTS Delta for Goal 2

Apply these instructions in addition to the repository AGENTS.md.

## Do
- Preserve Goal 1 engine behavior and tests.
- Add production reliability around existing pipelines.
- Make long-running jobs idempotent and recoverable.
- Keep released assets immutable.
- Write export boundary tests that fail if forbidden files are exported.
- Add audit logs and structured operational diagnostics.

## Do not
- Do not reintroduce hard-coded business heuristics.
- Do not export prompts, Gold Set builders, calibration internals, or cross-category templates.
- Do not allow released rule/asset versions to be modified in place.
- Do not hide failed jobs as successful.
