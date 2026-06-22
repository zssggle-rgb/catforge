---
name: catforge-insight
description: Query read-only CatForge SKU parameter fact profiles, standard parameters, SKU claim fact profiles, standard claims, market profiles, comparable pools, comment fact profiles, user task profiles, target group profiles, value battlefield profiles, semantic market maps, sales allocation, and coverage using natural language.
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
- A SKU/model's comment fact profile, for example "查 100A4F 的评论事实画像", "TV00027354 用户评价事实情况".
- TV standard comment fact taxonomy, for example "查彩电评论事实维度", "电视评论应该看哪些维度".
- Comment dimension coverage, for example "品牌力评论覆盖哪些 SKU", "哪些 SKU 评论提到索尼", "游戏用途评论覆盖哪些 SKU".
- A SKU/model's TV user task profile, for example "查 100A4F 的用户任务", "这个 SKU 的主任务是什么".
- TV user task taxonomy, for example "查彩电用户任务预设", "电视用户任务怎么分".
- User task coverage, for example "大屏换新升级有哪些 SKU", "哪些 SKU 的游戏任务是拖后腿".
- A SKU/model's TV target group profile, for example "查 100A4F 的目标客群", "这个 SKU 的目标客户是谁".
- TV target group taxonomy, for example "查彩电目标客群预设", "电视目标客群怎么分".
- Target group coverage, for example "性价比理性用户有哪些 SKU", "哪些 SKU 是未满足长辈友好需求".
- A SKU/model's TV value battlefield profile, for example "查 100A4F 的价值战场", "TV00027354 战场画像".
- TV value battlefield taxonomy, for example "查彩电价值战场预设", "电视价值战场怎么分".
- Value battlefield coverage, for example "大屏换新性价比战场有哪些 SKU", "拖后腿战场有哪些 SKU".
- Value battlefield graph, for example "查彩电价值战场图谱".
- Semantic market map and sales allocation, for example "某个价值战场有多少销量", "目标客群图谱有哪些 SKU", "用户任务图谱销量怎么分", "查 100A4F 的销量分配", "这个 SKU 在多个战场里销量怎么切".

This is a read-only fact and coverage query skill. It should return facts, taxonomy, coverage, profiles, maps, and allocation records. It should not produce higher-level business reasoning by itself.

Use XiaoAo / `catforge_analyst` instead when the user asks:

- "这个 SKU 的竞品是谁", "和谁竞争", "直接竞品".
- "A 为什么比 B 卖得好/差", "销量差异原因".
- "哪些卖点支撑用户选择", "哪些卖点是溢价卖点".
- "这个 SKU 能不能进入更多价值战场", "怎么扩大销量", "怎么抢竞品市场".
- "这个 SKU 的综合业务画像", "目标客户是什么", "商业机会是什么".
- Any question that asks for business conclusion, competitor reasoning, sales-difference reasoning, premium-claim reasoning, battlefield opportunity, or recommended action.

In Claude Code, the stable handoff command is:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_analyst ask "海信65E7Q和谁竞争？" --batch-id latest --product-category tv --format json
```

In OpenClaw, use `xiaoao-home-appliance-market-analysis` and the XiaoAo agent when available.

Do not require the user to know module codes. In user-facing replies, call this "参数画像", "标准参数", "卖点事实画像", "标准卖点", "市场画像", "市场区间覆盖", "可比池", "评论事实画像", "评论事实维度", "用户任务画像", "用户任务预设", "目标客群画像", "目标客群预设", "价值战场画像", "价值战场预设", "价值战场图谱", "语义市场图谱", "销量分配", and "覆盖 SKU"; only mention M03B/M04C/M05C/M07/M09C/M10C/M11C/M11D if the user asks for implementation details.

If you do use this skill to answer a factual question, do not over-interpret the result. For example, semantic market graph `estimated_sales_volume` and `allocated_sales_volume` are explanatory allocation values, not causal attribution; cumulative sales are context only and must not be used as the basis for pairwise sales winner/loser conclusions.

M05C-B, sometimes called `m05b` in business discussion, is the LLM-based comment profile generation stage. This skill is M05C-C read-only query and never calls an LLM.

M09C is the deterministic TV user task profile stage. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, M07 weighted prices, and M01 clean weekly market rows. M07 prices derive the size-tier price band; market validation uses same-size peer overlap weeks and average weekly volume/amount. Cumulative sales are display-only and must not be used for task judgment. It uses comments as the strongest evidence for user purpose; claims are manufacturer intent; parameters are capability support. Negative comments still count as task demand, but are reported as `drag_factor_task`. This skill only queries M09C outputs and never writes data.

M10C is the deterministic TV target group profile stage. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, M07 weighted prices, and M01 clean weekly market rows. It uses M03B's five size tiers and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier. Market validation uses same-size peer overlap weeks and average weekly volume/amount; cumulative sales are display-only and must not be used for target-group judgment. This skill only queries M10C outputs and never writes data.

M11C is the deterministic TV value battlefield profile stage. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, M07 weighted prices, and M01 clean weekly market rows. It uses M03B's five size tiers and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier. Market validation uses same-size peer overlap weeks and average weekly volume/amount; cumulative sales are display-only and must not be used for battlefield judgment. This skill only queries M11C outputs and never writes data. TV value battlefield taxonomy `m11c_tv_value_battlefield_taxonomy_v0.2` has 13 battlefields and adds `BF_GIANT_SCREEN_VALUE_DOWNTRADE` to separate low/mid/mid_high 98+ inch giant-screen value-downtrade SKUs from `BF_GIANT_HOME_THEATER_FLAGSHIP`.

M11D is the deterministic semantic market graph and sales-allocation result layer. It reads current M05C, M09C, M10C, M11C, and M07 outputs. It does not call an LLM and does not rejudge a SKU's user task, target group, or battlefield. Default population is `fact_complete_with_comment`, so business-facing market maps only include SKUs with comment facts and complete semantic profiles. It outputs user-task, target-group, and battlefield maps, SKU contribution rows, and SKU-level sales allocation. Use M11D when the question asks market size, SKU contribution within a dimension, or how one SKU's sales are split across multiple tasks/groups/battlefields. It reports total allocated sales and average weekly allocated sales; cumulative sales are context only.

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

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的评论事实画像" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电评论事实维度" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "品牌力评论覆盖哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的用户任务" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电用户任务预设" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "大屏换新升级有哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的目标客群" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电目标客群预设" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "性价比理性用户有哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的价值战场" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电价值战场预设" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "大屏换新性价比战场有哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电价值战场图谱" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查彩电语义市场图谱" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight ask "查 100A4F 的销量分配" --format json
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

Query one SKU/model's comment fact profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-comment-profile --query 100A4F --include-comment-facts --format json
```

Query TV comment fact taxonomy:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight comment-taxonomy --product-category tv --format json
```

Query comment dimension or signal coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight comment-dimension-coverage --query "品牌力覆盖哪些 SKU" --sku-limit 100 --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight comment-dimension-coverage --coverage-type competitor --query 索尼 --sku-limit 100 --format json
```

Query one SKU/model's user task profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-user-task --query 100A4F --include-scores --format json
```

Query TV user task taxonomy:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight user-task-taxonomy --product-category tv --format json
```

Query user task SKU coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight user-task-skus --query "大屏换新升级有哪些 SKU" --sku-limit 100 --format json
```

Query one SKU/model's target group profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-target-group --query 100A4F --include-scores --format json
```

Query TV target group taxonomy:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight target-group-taxonomy --product-category tv --format json
```

Query target group SKU coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight target-group-skus --query "性价比理性用户有哪些 SKU" --sku-limit 100 --format json
```

Query one SKU/model's value battlefield profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-value-battlefield --query 100A4F --include-scores --format json
```

Query TV value battlefield taxonomy:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight value-battlefield-taxonomy --product-category tv --format json
```

Query value battlefield SKU coverage:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight value-battlefield-skus --query "大屏换新性价比战场有哪些 SKU" --sku-limit 100 --format json
```

Query value battlefield graph:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight value-battlefield-graph --product-category tv --format json
```

Query semantic market map across all dimensions:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight semantic-market-map --product-category tv --batch-id latest --sku-limit 100 --format json
```

Query one semantic dimension map:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight semantic-market-map --product-category tv --batch-id latest --dimension-type battlefield --dimension-code BF_LARGE_SCREEN_VALUE_UPGRADE --sku-limit 100 --format json
```

Query one SKU/model's sales allocation:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-sales-allocation --product-category tv --batch-id latest --query 100A4F --format json
```

Query one SKU/model's battlefield-only allocation:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight sku-sales-allocation --product-category tv --batch-id latest --query 100A4F --dimension-type battlefield --format json
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

For SKU comment fact profile results, summarize:

- SKU code, model name, brand, comment sentence count, usable sentence count, comment fact count, and review issue count.
- Positive and negative product experience dimensions.
- Parameters and claims supported or contradicted by this SKU's own comments.
- Audience, use-case, size/space, price/value, brand-power, and competitor signals.
- Typical evidence sentences when returned.

For comment taxonomy results, summarize taxonomy version, total dimension/subdimension counts, and relevant dimension definitions.

For comment dimension coverage results, summarize coverage type/key, SKU count, polarity counts, returned SKU examples, and evidence examples. Brand-power signals must not be mixed with competitor mentions.

For SKU user task profile results, summarize:

- Primary user task, secondary user tasks, comment-observed tasks, brand-claimed tasks, latent capability tasks, and drag-factor tasks.
- Whether each important user task is supported by comments, seller claims, parameters, size/price, and market validation.
- Negative comments as user demand that the product did not satisfy, not as exclusion.
- No-primary reason if no primary user task is established.

For user task taxonomy results, summarize taxonomy version and relevant user task definitions, including size-tier fit, price-band fit, comment subdimensions, claim codes, and parameter codes.

For user task SKU coverage results, summarize user task name/code, relation status filter, SKU count, returned SKU examples, and whether the list is truncated.

For SKU value battlefield profile results, summarize:

- SKU code, model name, and brand.
- Size tier and price band within that size tier.
- Primary value battlefield, secondary battlefields, opportunity battlefields, and drag-factor battlefields.
- Whether each important battlefield is supported by user comments, seller claims, parameters, and market gate.
- No-primary reason if no primary battlefield is established.

For SKU target group profile results, summarize:

- Primary target group, secondary target groups, comment-observed groups, brand-claimed groups, latent groups, and unmet group needs.
- Whether each important target group is supported by comments, task proxy, size/price, claims, and parameters.
- No-primary reason if no primary target group is established.

For target group taxonomy results, summarize taxonomy version and relevant target group definitions, including source task codes, size-tier fit, price-band fit, comment subdimensions, claim codes, and parameter codes.

For target group SKU coverage results, summarize target group name/code, relation status filter, SKU count, returned SKU examples, and whether the list is truncated.

For value battlefield taxonomy results, summarize taxonomy version and the relevant battlefield definitions, including size-tier gate, price-band gate, task codes, target group codes, comment subdimensions, claim codes, and parameter codes.

For value battlefield SKU coverage results, summarize battlefield name/code, relation status filter, SKU count, returned SKU examples, and whether the list is truncated.

For value battlefield graph results, summarize graph snapshot id, batch id, battlefield count, SKU count, edge count, and top coverage distribution.

For semantic market map results, summarize:

- Analysis population and market window.
- Dimension type/name/code.
- Relation SKU count, allocated SKU count, primary/secondary/observed/brand/drag counts.
- Estimated sales volume and estimated average weekly sales volume.
- Estimated sales amount and estimated average weekly sales amount.
- Allocation coverage rate and confidence average.
- Top contributing SKUs, noting allocation weight and allocated sales.

For SKU sales allocation results, summarize:

- SKU code, model name, brand, analysis population, and market window.
- Allocation weight sum by dimension type; each dimension type should usually sum to 1 when allocated.
- For each user task, target group, and battlefield allocation: relation status, allocation role, weight, allocated sales volume, allocated average weekly volume, confidence, and evidence ids when returned.
- If a dimension type is not found, explain it may be a no-allocation diagnostic rather than a data loss issue.

If the CLI returns `ambiguous`, ask for the exact SKU code or fuller model name. If it returns `not_found`, say no profile was found in the selected batch and suggest checking whether the corresponding generation job has run for that batch.
