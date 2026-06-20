---
name: catforge-insight
description: Query CatForge SKU parameter fact profiles, TV/AC standard parameters, and parameter tier SKU coverage using natural language.
---

# CatForge Insight Skill

Use this skill when the user asks about:

- A SKU/model's parameter fact profile, for example "查 100A4F 的参数画像", "TV00027354 参数情况", "AC00000001 参数情况", "这个 SKU 的硬件参数是什么".
- TV/AC standard parameters, for example "彩电有哪些标准参数", "查空调标准参数表", "MiniLED 对应哪些原始字段", "新风对应哪些原始字段".
- Parameter tier coverage, for example "MiniLED 档位覆盖哪些 SKU", "旗舰画质有哪些 SKU", "一级能效覆盖 SKU", "空调新风档位覆盖哪些 SKU".

Do not require the user to know module codes. In user-facing replies, call this "参数画像", "标准参数", and "档位覆盖"; only mention M03B if the user asks for implementation details.

## Working Directory

Run commands from the deployed repository on 205:

```bash
cd /opt/catforge
```

Prefer running inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ...
```

Default project and category are already set in the CLI for the current 205 TV project. Use `--batch-id latest` unless the user specifies a batch.

## Natural Language Entry

For free-form questions, use `ask` first:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的参数画像" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电标准参数" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查空调标准参数" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 MiniLED 档位覆盖哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查空调新风档位覆盖哪些 SKU" --sku-limit 100 --format json
```

## Stable Atomic Commands

Use these when you can confidently map the user's intent.

Query one SKU/model's parameter profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-param-profile --query 100A4F --format json
```

For AC, either ask naturally or specify the product category:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-param-profile --sku-code AC00000001 --product-category ac --format json
```

Include all extracted standard parameter values:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-param-profile --sku-code TV00027354 --include-param-values --format json
```

Query TV standard parameters:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight tv-param-taxonomy --format json
```

Query AC standard parameters:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ac-param-taxonomy --format json
```

Filter standard parameters:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight tv-param-taxonomy --group picture --search MINILED --format json
```

Query tier coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight tier-coverage --dimension-code display_tech --tier-code miniled --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight tier-coverage --query "旗舰画质覆盖 SKU" --sku-limit 100 --format json
```

## Response Rules

For SKU parameter profile results, summarize:

- SKU code and model name.
- Parameter completeness, known/unknown count, conflict count, review-required count.
- Dimension tier profile: size, display tech, picture overall, local dimming, performance, ports, smart, appearance, energy.
- Important core parameters when relevant to the question.
- Review warnings when `conflict_count` or `review_required_count` is greater than zero.

For TV standard parameter results, summarize:

- Taxonomy version and total parameter count.
- Groups and counts.
- Relevant parameter codes, Chinese names, raw field mappings, missing policy, and whether each is core or auxiliary.

For AC standard parameter results, summarize the same fields. Remember the current 205 source batch still stores AC evidence under source `category_code=TV`, but the AC parameter asset and profile outputs are separated by `sku_code_prefix=AC`, `taxonomy_version=ac_param_taxonomy_manual_v0.1`, and `rule_version=m03b_ac_param_profile_v0.1`.

For tier coverage results, summarize:

- Batch id.
- Dimension and tier name/code.
- SKU count and ratio.
- Returned SKU list, noting if the list is truncated.

If the CLI returns `ambiguous`, ask for the exact SKU code or fuller model name. If it returns `not_found`, say no parameter profile was found in the selected batch and suggest checking whether M03B has run for that batch.
