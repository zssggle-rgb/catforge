---
name: catforge-publish
description: Publish CatForge analysis result summaries to the XiaoAo Feishu Base workbench and open the workbench link from natural language.
---

# CatForge Publish Skill

Use this skill when a user asks to publish, sync, refresh, or open the XiaoAo Feishu Base workbench.

This skill is only a routing layer for `catforge_publish`. It must not recompute analysis, edit Base fields directly, or expose implementation details in user-facing replies.

## Commands

Run from `/opt/catforge` on 205.

Initialize or verify the workbench:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base init --category tv --base-name "小奥家电市场分析工作台" --format json
```

Sync all phase-1 tables:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync-all --category tv --batch-id latest --allow-schema-update --format json
```

Sync one scope:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope sku-overview --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope battlefield-map --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope competitor-relations --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope claim-value --category tv --batch-id latest --format json
```

Open or inspect:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base open --category tv --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base status --category tv --format json
```

## Answer Rules

Return a concise business-facing result:

- synced table names and row counts
- workbench link if available
- clean permission/configuration failure if blocked

Do not show command text, raw JSON, Base token, table IDs, field IDs, stack traces, or module names unless the user asks for debugging.
