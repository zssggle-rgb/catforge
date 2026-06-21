---
name: catforge-insight
description: Query CatForge SKU parameter fact profiles, standard parameters, SKU claim fact profiles, standard claims, market profiles, comparable pools, and coverage using natural language.
---

# CatForge Insight Skill

Use this skill when the user asks about:

- A SKU/model's parameter fact profile, for example "查 100A4F 的参数画像", "TV00027354 参数情况", "AC00000001 参数情况", "这个 SKU 的硬件参数是什么".
- TV/AC standard parameters, for example "彩电有哪些标准参数", "查空调标准参数表", "MiniLED 对应哪些原始字段", "新风对应哪些原始字段".
- Parameter tier coverage, for example "MiniLED 档位覆盖哪些 SKU", "旗舰画质有哪些 SKU", "一级能效覆盖 SKU", "空调新风档位覆盖哪些 SKU".
- A SKU/model's claim fact profile, for example "查 100A4F 的卖点画像", "TV00027354 卖点事实情况".
- TV standard claims, for example "彩电有哪些标准卖点", "MiniLED 卖点对应哪些参数".
- Claim position coverage, for example "MiniLED 复合画质旗舰型覆盖哪些 SKU", "AI 语音增强型有哪些 SKU".
- A SKU/model's market profile, for example "查 100A4F 的市场画像", "TV00027354 量价情况", "这个 SKU 在市场里什么位置".
- Market bucket coverage, for example "高价格带覆盖哪些 SKU", "85 寸尺寸区间有哪些 SKU", "价格区间销量头部是谁".
- Comparable-pool baselines, for example "查 100A4F 的可比池", "TV00027354 同价格带池".

Do not require the user to know module codes. In user-facing replies, call this "参数画像", "标准参数", "卖点事实画像", "标准卖点", "市场画像", "市场区间覆盖", "可比池", and "覆盖 SKU"; only mention M03B/M04C/M07 if the user asks for implementation details.

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

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的卖点画像" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电标准卖点" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 MiniLED 复合画质旗舰型覆盖哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的市场画像" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查高价格带覆盖哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的可比池" --sku-limit 100 --format json
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

Query one SKU/model's claim fact profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-claim-profile --query 100A4F --include-claim-facts --format json
```

Query TV standard claims:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight claim-taxonomy --product-category tv --format json
```

Filter standard claims:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight claim-taxonomy --product-category tv --search MiniLED --format json
```

Query claim position coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight claim-position-coverage --query "MiniLED 复合画质旗舰型覆盖 SKU" --sku-limit 100 --format json
```

Query one SKU/model's market profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-market-profile --query 100A4F --include-signals --include-pools --format json
```

Query market bucket coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight market-bucket-coverage --bucket-type price --query high --sku-limit 100 --format json
```

Query comparable pools:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight comparable-pools --query 100A4F --sku-limit 100 --format json
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

For SKU claim fact profile results, summarize:

- SKU code, model name, and brand.
- Raw claim count, matched claim count, fact-claim count, parameter-unknown count, unsupported-by-parameter count, and service-fulfillment count.
- Dimension profile and positions, especially supported positions.
- Fact claims with parameter support when `claim_facts` is included.
- Service-fulfillment claims must be described as separated, not product fact claims.

For TV standard-claim results, summarize:

- Taxonomy version and total claim count.
- Dimensions and counts.
- Relevant claim codes, Chinese names, dimensions, support parameter codes, and whether they are service separated.

For claim position coverage results, summarize:

- Batch id and whether coverage is `supported` or `claimed`.
- Dimension, position name/code, SKU count and ratio.
- Returned SKU list, noting if the list is truncated.

For SKU market profile results, summarize:

- SKU code, model name, and analysis window.
- Sales volume, sales amount, weighted average price, latest price, main platform, and platform share.
- Price position and size position: price band, size segment, category/size volume percentile, same-pool SKU count.
- Current bucket fallback fields if present. Note that persisted business absolute price buckets require the follow-up M07 implementation.
- Market signals and comparable pools when included.

For market bucket coverage results, summarize:

- Bucket type, code, and label.
- SKU count, total sales volume, total sales amount, median price, and top SKUs.
- Returned SKU list, noting if the list is truncated.
- If `bucket_source=current_m07_profile_fallback`, state that the current query uses M07 dynamic price bands and size segments until the business bucket table is implemented.

For comparable-pool results, summarize:

- Target SKU/model, pool count, pool type, sample status, SKU count, median price/volume/amount, and candidate SKUs.

If the CLI returns `ambiguous`, ask for the exact SKU code or fuller model name. If it returns `not_found`, say no profile was found in the selected batch and suggest checking whether the corresponding parameter or claim profile job has run for that batch.
