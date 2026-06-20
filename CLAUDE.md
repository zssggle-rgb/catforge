# CatForge Claude Code Guide

This repository is CatForge / 品铸, the internal Category Factory for category semantic assets and market-analysis rules.

Claude Code should act as an execution agent, not as a free-form analyst. Prefer deterministic CLI/API/database-backed checks over assumptions.

## Project Boundaries

- CatForge is the internal factory, not the customer-facing runtime.
- Do not expose factory-only scripts, prompt templates, Gold Set builders, or internal generation methods through runtime export surfaces.
- Missing values are unknown. Never treat missing, empty, "-", or null values as false.
- Keep candidate generation, review, evaluation, and release as separate stages.
- Preserve traceability fields such as `evidence_id`, `source_file_id`, `raw_row_id`, `confidence`, and `review_status`.

## 205 Server Conventions

- Deployed repository path: `/opt/catforge`.
- Run repo and Claude Code operations as user `deploy`.
- Docker Compose file: `docker-compose.cloud.yml`.
- API container service: `api`.
- Production database: `catforge_dev`; app user is `catforge_app`.
- Current 205 real-data project id: `d8d2245b-358b-4a64-95cc-9d7f2341bd26`; category code: `TV`.
- Do not run destructive SQL against raw or clean tables unless the user explicitly asks and the exact impact is clear.

Useful commands:

```bash
docker compose -f docker-compose.cloud.yml ps
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data inspect-data-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --format json
```

## Business Command Routing

Use the `catforge-data` skill when the user asks to preprocess new uploaded data, inspect data quality, or check preliminary SKU/comment coverage.

For "先初步处理一下" or "初步清洗":

1. Register a new incremental source batch by default.
2. Run preliminary cleaning by SKU chunks.
3. Do not run downstream evidence/comment semantic stages unless the user asks for full processing.
4. Inspect the resulting batch by explicit `batch_id`; if the CLI output is empty or suspicious, verify counts directly in PostgreSQL before answering.
5. Report batch id, processed SKU count, clean row counts, weekly market coverage, low-value comment count/rate, service-fulfillment blocked count/rate, and review-required issues.

Do not require business users to know internal module names. Internal module codes may be mentioned only when explaining implementation details.

## M01 Interpretation Rules

- SKU-week coverage is present if at least one platform has data in that week.
- A SKU-week with only one platform is normal; explain it as single-platform sales or platform-special supply.
- Leading missing weeks are usually new product or late entry into the sample.
- Trailing missing weeks are usually delisting or leaving the sample.
- Only gaps between the first and last observed week are internal-gap soft warnings.
- TV attributes can have missing values; do not overstate attribute missingness as a blocker.
- Empty/default/obvious low-value comments should be filtered quickly.
- Service-fulfillment comments such as customer service, logistics, installation, after-sales, refund, and repair should be marked as low-value in M01, kept for quality statistics, and blocked from downstream product/comment sentence analysis.

## Engineering Rules

- Check `git status --short --branch` before editing.
- Do not revert unrelated changes.
- Use hotfix branches for urgent data-processing fixes.
- Use narrow commits and stage only files changed for the current task.
- Run targeted tests after changes. For M01/CLI changes, use:

```bash
cd apps/api-server
python -m pytest tests/core3_real_data/test_m01_cleaning_coverage_quality.py tests/core3_real_data/test_m01_cleaning_runner.py tests/core3_real_data/test_m01_cleaning_api.py
```

## User-Facing Replies

- Reply in Chinese by default.
- Use business language for analysis status and data quality findings.
- Include concrete counts, batch ids, and command results.
- Keep technical details concise unless the user asks for implementation detail.
