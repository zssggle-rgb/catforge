---
name: catforge-data
description: Prepare newly uploaded CatForge category data and inspect preliminary data quality using business-language commands.
---

# CatForge Data Skill

Use this skill when the user asks to:

- "先初步处理一下", "预处理新数据", "初步清洗", or similar.
- Check whether newly uploaded CatForge data is ready for later analysis.
- Inspect SKU weekly market coverage, preliminary comment quality, missing data, or quality warnings.

Do not require the user to know module codes. Treat M00/M01/M02/M05 as internal implementation details in user-facing replies.

## Execution Rules

- Preliminary processing defaults to source registration plus preliminary cleaning: create an incremental source batch, then run M01 cleaning only.
- To rerun cleaning for an existing source batch, explicitly use `--register-source-batch none --batch-id <batch_id-or-latest>`.
- Preliminary processing must not run evidence/comment semantic stages such as M02 or M05.
- Run M01 by SKU chunks by default to avoid high CPU and memory pressure on 205.
- Empty, default, and obvious low-value comments are filtered from sentence/evidence preparation in M01 and counted in the preliminary summary.
- Service-fulfillment comments such as customer service, logistics, installation, after-sales, refund, and repair are marked as low-value in M01, kept for quality statistics, and blocked from downstream product/comment sentence analysis.
- Single-platform data in one SKU-week is normal and should be explained as single-channel sales or platform special supply, not as missing coverage.
- Leading missing weeks should be explained as possible new product or late entry into the sample. Trailing missing weeks should be explained as possible delisting or leaving the sample. Only gaps between the first and last observed week are soft warnings.

## Commands

From the deployed CatForge repository on 205, prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --sku-batch-size 50 --format json
```

If a source batch already exists and the user only wants to rerun preliminary cleaning:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --register-source-batch none --batch-id latest --sku-batch-size 50 --format json
```

Inspect current preliminary quality without rerunning:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data inspect-data-quality --batch-id latest --format json
```

For a small smoke test:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --register-source-batch none --batch-id latest --limit-skus 5 --sku-batch-size 2 --format json
```

## Response Shape

When reporting results to the user, summarize:

- batch id
- processed SKU count and chunk count
- clean row counts
- weekly market coverage summary
- low-value comment count/rate
- service-fulfillment low-value count/rate, clearly saying those comments were blocked from downstream product/comment sentence analysis
- review-required quality issues, if any

Use business language and avoid exposing internal module numbers unless the user asks for implementation details.
