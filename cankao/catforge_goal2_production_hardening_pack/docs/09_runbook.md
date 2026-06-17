# Production Runbook

## Normal release flow
1. Run analysis.
2. Run evaluation.
3. Review quality gates.
4. Submit assets to review.
5. Approve release.
6. Export runtime package.
7. Verify export manifest.

## Failed job recovery
- Check diagnostics endpoint.
- If transient, retry.
- If data contract error, fix data and submit new job with new input fingerprint.
- If partial writes occurred, rely on idempotent upserts or checkpoint recovery.

## Rollback
- Identify prior released manifest.
- Create rollback release referencing prior manifest.
- Export rollback runtime package.
- Audit event must record rollback reason.

## Export security check
Before sharing an export, verify whitelist and forbidden-pattern tests pass.
