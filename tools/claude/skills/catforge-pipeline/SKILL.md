---
name: catforge-pipeline
description: Run CatForge data-preparation and SKU parameter profile jobs from natural language, including TV and AC parameter profile generation.
---

# CatForge Pipeline Skill

Use this skill when the user asks Claude Code to execute preparation/profile work, for example:

- "重新生成彩电 SKU 参数画像"
- "电视新增 SKU 了，更新参数画像"
- "生成空调 SKU 参数画像"
- "把空调参数事实准备好可以分析"

This is an execution skill. For read-only questions like "查某个 SKU 的参数画像" or "查空调标准参数", use `catforge-insight` instead.

## Working Directory

Run commands from the deployed repository on 205:

```bash
cd /opt/catforge
```

Prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ...
```

The current 205 raw-data batch stores TV and AC evidence under source `category_code=TV`; product category isolation is handled by SKU prefix and taxonomy/rule version:

- TV: `sku_code_prefix=TV`, `taxonomy_version=tv_param_taxonomy_manual_v0.1`, `rule_version=m03b_tv_param_profile_v0.1`
- AC: `sku_code_prefix=AC`, `taxonomy_version=ac_param_taxonomy_manual_v0.1`, `rule_version=m03b_ac_param_profile_v0.1`

## Natural Language Entry

Use `ask` first for free-form execution requests:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 参数画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "生成空调 SKU 参数画像" --force-rebuild --format json
```

## Stable Atomic Commands

Run TV SKU parameter profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
```

Run AC SKU parameter profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-param-profile --product-category ac --batch-id latest --force-rebuild --format json
```

Use `--batch-id latest` unless the user gives a specific batch id. Use `--force-rebuild` when source data or taxonomy/rules have changed and existing profile business keys should be refreshed.

## Response Rules

After execution, summarize:

- Product category and batch id.
- Input evidence count and output count.
- SKU profile count, parameter value count, dimension tier count, and tier coverage count.
- Warnings, especially empty input, parameter conflicts, or failed status.

If the CLI returns `error`, report the error and do not claim the job completed. If the job succeeds with warnings, state that outputs were written but review may be needed.
