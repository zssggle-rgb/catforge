---
name: catforge-data
description: Prepare newly uploaded CatForge category data for analysis and inspect preliminary data quality using business-language commands.
---

# CatForge Data Skill

Use this skill when the user asks to:

- "先初步处理一下", "预处理新数据", "初步清洗", "把数据准备好分析", or similar.
- Check whether newly uploaded CatForge data is ready for later analysis.
- Inspect SKU weekly market coverage, preliminary comment quality, missing data, or quality warnings.
- Inspect one SKU's preliminary cleaning result, such as "这个 SKU 清理情况" or "这个 SKU 评论还有多少有效内容".

Do not require the user to know module codes. Treat M00/M01/M02/M05 as internal implementation details in user-facing replies.

## Execution Rules

- Preliminary processing defaults to analysis-ready data preparation: create an incremental source batch, run cleaning, then prepare traceable evidence for later fact analysis.
- Run one product category at a time. `--category-code TV` processes raw TV categories only; AC data must be prepared in a separate AC run before AC-specific downstream work.
- To rerun cleaning for an existing source batch, explicitly use `--register-source-batch none --batch-id <explicit_batch_id>`.
- Never use `--register-source-batch none --batch-id latest` for newly uploaded data. That skips M00 source registration and can silently rerun an old batch.
- Preliminary processing must not run comment semantic or business-profile stages such as M05 and later modules.
- Run cleaning and evidence preparation by SKU chunks by default to avoid high CPU and memory pressure on 205.
- Empty, default, and obvious low-value comments are filtered from sentence/evidence preparation in M01 and counted in the preliminary summary.
- Service-fulfillment comments such as customer service, logistics, installation, after-sales, refund, and repair are identified in M01, kept for preliminary statistics, and blocked from downstream product/comment sentence analysis. Do not describe this as a separate product-quality defect.
- Single-platform data in one SKU-week is normal and should be explained as single-channel sales or platform special supply, not as missing coverage.
- Leading missing weeks should be explained as possible new product or late entry into the sample. Trailing missing weeks should be explained as possible delisting or leaving the sample. Only gaps between the first and last observed week are soft warnings.

## Commands

From the deployed CatForge repository on 205, prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 50 --evidence-sku-batch-size 1 --format json
```

If a source batch already exists and the user explicitly wants to rerun that exact batch for analysis, pass the explicit batch id:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --register-source-batch none --batch-id <explicit_batch_id> --sku-batch-size 10 --evidence-sku-batch-size 1 --format json
```

Inspect current preliminary quality without rerunning:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data inspect-data-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --format json
```

Inspect one SKU's preliminary quality:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data inspect-sku-quality --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --batch-id latest --sku-code TV00029115 --format json
```

For a non-writing plan check before running:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 --category-code TV --sku-batch-size 10 --evidence-sku-batch-size 1 --dry-run --format json
```

When checking whether a previous run finished, inspect by the explicit `batch_id` when available. If CLI counts are empty or inconsistent with the run log, cross-check `core3_clean_*`, `core3_source_batch`, and `core3_data_quality_issue` in PostgreSQL before replying.

## Response Shape

When reporting results to the user, summarize:

- batch id
- processed SKU count and chunk count
- evidence preparation status
- clean row counts
- weekly market coverage summary
- low-value comment count/rate
- service-fulfillment count/rate, clearly saying those comments were blocked from downstream product/comment sentence analysis
- review-required quality issues, if any

For SKU-level results, summarize whether the SKU exists in the batch, market weekly coverage, single-platform weeks, attribute unknown count, claim count, raw comments, low-value comments, service-fulfillment comments, candidate comments after filtering, and SKU-level review-required issues.

Use business language and avoid exposing internal module numbers unless the user asks for implementation details.
