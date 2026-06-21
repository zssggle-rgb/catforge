---
name: catforge-pipeline
description: Run CatForge data-preparation, SKU parameter profile, SKU claim fact profile, and SKU market profile jobs from natural language.
---

# CatForge Pipeline Skill

Use this skill when the user asks Claude Code to execute preparation/profile work, for example:

- "重新生成彩电 SKU 参数画像"
- "电视新增 SKU 了，更新参数画像"
- "生成空调 SKU 参数画像"
- "把空调参数事实准备好可以分析"
- "重新生成彩电 SKU 卖点事实画像"
- "电视新增 SKU 了，更新卖点画像"
- "把彩电卖点事实准备好可以分析"
- "重新生成彩电市场画像"
- "重跑 TV00027354 的量价市场画像"
- "更新彩电价格区间和尺寸区间的市场画像"
- "重新生成彩电评论事实画像"
- "重跑 TV00027354 的评论画像"
- "新数据来了，把彩电评论事实准备好"

This is an execution skill. For read-only questions like "查某个 SKU 的参数画像", "查彩电标准卖点", or "查某个 SKU 的卖点画像", use `catforge-insight` instead.
For read-only market questions like "查某个 SKU 的市场画像", "查价格区间覆盖哪些 SKU", or "查某个 SKU 的可比池", also use `catforge-insight`.
For read-only comment questions like "查某个 SKU 的评论事实画像", "查品牌力覆盖哪些 SKU", or "评论里是否提到索尼", use `catforge-insight` instead.

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

M04C claim fact profiles currently have a published TV taxonomy only:

- TV claim profile: `taxonomy_version=tv_claim_taxonomy_manual_v0.1`, `rule_version=m04c_tv_claim_fact_profile_v0.1`
- AC claim profile: not available until an AC standard-claim taxonomy is published.

M05C-B comment fact profiles currently have a published TV taxonomy only. In business conversation this stage may be called `m05b`; in this codebase it is implemented as M05C-B. It uses an LLM to classify M02 comment sentences into comment facts. M05C-C is read-only query and does not call an LLM.

- TV comment profile: `taxonomy_version=tv_comment_fact_taxonomy_manual_v0.1`, `rule_version=m05c_tv_comment_fact_profile_v0.1`
- AC comment profile: not available until an AC comment taxonomy is published.

LLM credentials must come from environment variables. Never write API keys into skill files, committed docs, or command transcripts. On 205 validation, use `--llm-mode required` so failure to call the LLM is visible.

## Natural Language Entry

Use `ask` first for free-form execution requests:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 参数画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "生成空调 SKU 参数画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 卖点事实画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电市场画像" --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电评论事实画像" --llm-mode required --force-rebuild --format json
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

Run TV SKU claim fact profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-claim-profile --product-category tv --batch-id latest --input-source auto --force-rebuild --format json
```

Run TV market profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --format json
```

Run TV market profiles with an explicit SKU chunk size:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --sku-chunk-size 50 --format json
```

Run one SKU/window market profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --analysis-window full_observed_window --sku-code TV00027354 --format json
```

Run TV SKU comment fact profiles with LLM:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --llm-mode required --force-rebuild --format json
```

Run one TV SKU comment fact profile with LLM:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --sku-code TV00027354 --llm-mode required --max-sentences-per-sku 500 --format json
```

Use `--input-source auto` by default. It reads M02 selling-point evidence first, then M01 cleaned claims, then raw `selling_points_data` only if needed. Use `--input-source raw` only when the current deployment has new raw selling points but M01/M02 have not been rerun yet.

Use `--batch-id latest` unless the user gives a specific batch id. Use `--force-rebuild` when source data or taxonomy/rules have changed and existing profile business keys should be refreshed.
For M07 market profiles, omit `--analysis-window` to run all windows. The CLI executes windows sequentially and splits TV SKUs into chunks, committing after each chunk to keep the 205 memory peak below the API container limit. The default `--sku-chunk-size` is 50; lower it for safer execution, raise it only after observing memory. Because the current 205 source batch can contain mixed TV/AC evidence under source `category_code=TV`, the CLI defaults to TV-prefixed SKU scope when no `--sku-code` is supplied. The current implementation writes market profiles, market signals, comparable pools, and pool members. Business absolute price-bucket persistence from the updated M07 design requires the follow-up M07 service/table implementation.
For M05C-B comment fact profiles, use `--llm-mode required` on 205 validation, `--llm-mode off` only for deterministic local tests, and lower `--llm-batch-size` if the LLM provider times out. This command does not generate the category comment taxonomy; it only uses an already published taxonomy.

## Response Rules

After execution, summarize:

- Product category and batch id.
- Input evidence count and output count.
- SKU profile count, parameter value count, dimension tier count, and tier coverage count.
- For claim profiles, summarize SKU claim profile count, claim fact count, parameter-supported fact-claim count, service-fulfillment count, dimension position count, and position coverage count.
- For market profiles, summarize market profile count, market signal count, comparable-pool count, pool-member count, and review-required count.
- For comment profiles, summarize SKU comment profile count, comment fact count, coverage count, service-excluded sentence count, review-required count, and LLM mode/call/model status.
- Warnings, especially empty input, parameter conflicts, or failed status.

If the CLI returns `error`, report the error and do not claim the job completed. If the job succeeds with warnings, state that outputs were written but review may be needed.
