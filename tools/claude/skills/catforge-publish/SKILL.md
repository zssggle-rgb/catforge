---
name: catforge-publish
description: Publish CatForge analysis result summaries to the XiaoAo Feishu Base workbench and open the workbench link from natural language.
---

# CatForge Publish Skill

Use this skill when the user asks to:

- "同步最新电视分析结果到工作台"
- "把小奥分析结果发布到多维表格"
- "重新发布用户卖点价值结果"
- "同步竞品关系到工作台"
- "打开小奥家电市场分析工作台"
- "查看工作台同步状态"

This skill only routes natural language to the `catforge_publish` CLI. It must not read or rewrite Base fields directly, and it must not recompute M00-M12C analysis results.

## Working Directory

Run commands from the deployed CatForge repository:

```bash
cd /opt/catforge
```

Prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish ...
```

## Stable Commands

Initialize or verify the workbench schema:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base init --category tv --base-name "小奥家电市场分析工作台" --format json
```

Sync all phase-1 tables:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync-all --category tv --batch-id latest --allow-schema-update --format json
```

Sync a single table:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope sku-overview --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope battlefield-map --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope competitor-relations --category tv --batch-id latest --format json
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync --scope claim-value --category tv --batch-id latest --format json
```

Check status:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base status --category tv --format json
```

Open the workbench:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base open --category tv --format json
```

Dry run before writing:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_publish base sync-all --category tv --batch-id latest --dry-run --format json
```

## Response Rules

Reply in business language:

- Say which tables were synced and how many rows were created or updated.
- Provide the workbench link when available.
- If configuration is missing, say the workbench Base token is not configured and initialization or environment setup is required.
- If permissions fail, say the current account or bot lacks write permission to the workbench.

Do not expose shell commands, stack traces, Base token, table IDs, field IDs, raw JSON, or internal module names in the final user-facing answer unless the user explicitly asks for debugging detail.
