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

- Preliminary processing runs source registration only when requested or needed, then runs M01 cleaning only.
- Preliminary processing must not run evidence/comment semantic stages such as M02 or M05.
- Run M01 by SKU chunks by default to avoid high CPU and memory pressure on 205.
- Empty, default, and obvious low-value comments are filtered from sentence/evidence preparation in M01 and counted in the preliminary summary.
- Service-related comments are only counted as candidates at this stage. Do not block them before the user decides based on the measured volume.
- Single-platform data in one SKU-week is normal and should be explained as single-channel sales or platform special supply, not as missing coverage.
- Leading missing weeks should be explained as possible new product or late entry into the sample. Trailing missing weeks should be explained as possible delisting or leaving the sample. Only gaps between the first and last observed week are soft warnings.

## Commands

From the deployed CatForge repository on 205, prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --register-source-batch incremental --sku-batch-size 50 --format json
```

If a source batch already exists and the user only wants to rerun preliminary cleaning:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --batch-id latest --sku-batch-size 50 --format json
```

Inspect current preliminary quality without rerunning:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data inspect-data-quality --batch-id latest --format json
```

For a small smoke test:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_data prepare-new-data --batch-id latest --limit-skus 5 --sku-batch-size 2 --format json
```

## Response Shape

When reporting results to the user, summarize:

- batch id
- processed SKU count and chunk count
- clean row counts
- weekly market coverage summary
- low-value comment count/rate
- service-candidate comment count/rate, clearly saying it was not blocked
- review-required quality issues, if any

Use business language and avoid exposing internal module numbers unless the user asks for implementation details.
