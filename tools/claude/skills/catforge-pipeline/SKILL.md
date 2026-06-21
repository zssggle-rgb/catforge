---
name: catforge-pipeline
description: Run CatForge data-preparation, SKU parameter profile, SKU claim fact profile, SKU market profile, SKU comment fact profile, SKU user task, SKU target group, and SKU value battlefield jobs from natural language.
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
- "重新生成彩电用户任务画像"
- "重跑 TV00027354 的主用户任务分析"
- "新数据来了，把彩电用户任务准备好"
- "重新生成彩电目标客群画像"
- "重跑 TV00027354 的目标客户分析"
- "新数据来了，把彩电目标客群准备好"
- "重新生成彩电价值战场画像"
- "重跑 TV00027354 的价值战场画像"
- "更新彩电价值战场图谱"

This is an execution skill. For read-only questions like "查某个 SKU 的参数画像", "查彩电标准卖点", or "查某个 SKU 的卖点画像", use `catforge-insight` instead.
For read-only market questions like "查某个 SKU 的市场画像", "查价格区间覆盖哪些 SKU", or "查某个 SKU 的可比池", also use `catforge-insight`.
For read-only comment questions like "查某个 SKU 的评论事实画像", "查品牌力覆盖哪些 SKU", or "评论里是否提到索尼", use `catforge-insight` instead.
For read-only user-task questions like "查某个 SKU 的用户任务", "查彩电用户任务预设", or "大屏换新升级有哪些 SKU", use `catforge-insight` instead.
For read-only target-group questions like "查某个 SKU 的目标客群", "查彩电目标客群预设", or "性价比理性用户有哪些 SKU", use `catforge-insight` instead.
For read-only value battlefield questions like "查某个 SKU 的价值战场", "查彩电价值战场预设", or "大屏换新战场有哪些 SKU", use `catforge-insight` instead.

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

M09C user task profiles currently have a published TV taxonomy only. It is deterministic and does not call an LLM. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, and M07 `full_observed_window` market profiles. It uses comments as the strongest evidence for user purpose; claims are manufacturer intent; parameters are capability support. Negative comments still count as task demand, but become `drag_factor_task`.

- TV user task profile: `taxonomy_version=m09c_tv_user_task_taxonomy_v0.1`, `rule_version=m09c_tv_user_task_profile_v0.1`
- AC user task profile: not available until AC user-task taxonomy is published.

M10C target group profiles currently have a published TV taxonomy only. It is deterministic and does not call an LLM. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, and M07 `full_observed_window` market profiles. It uses the M03B five-tier size policy and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier.

- TV target group profile: `taxonomy_version=m10c_tv_target_group_taxonomy_v0.1`, `rule_version=m10c_tv_target_group_profile_v0.1`
- AC target group profile: not available until AC target-group taxonomy is published.

M11C value battlefield profiles currently have a published TV taxonomy only. It is deterministic and does not call an LLM. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, and M07 `full_observed_window` market profiles. It uses the M03B five-tier size policy and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier.

- TV value battlefield profile: `taxonomy_version=m11c_tv_value_battlefield_taxonomy_v0.1`, `rule_version=m11c_tv_value_battlefield_profile_v0.1`
- AC value battlefield profile: not available until AC task/group/battlefield taxonomies are published.

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

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电用户任务画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电目标客群画像" --force-rebuild --format json
```

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline ask "重新生成彩电价值战场画像" --force-rebuild --format json
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

Continue or accelerate TV SKU comment fact profiles with bounded SKU parallelism:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-comment-profile-batch --product-category tv --batch-id latest --llm-mode required --parallelism 2 --limit 10 --max-sentences-per-sku 500 --format json
```

After the 205 smoke run is stable, remove `--limit` and keep `--parallelism 2` or raise to `3-4` only after observing CPU, memory, and LLM timeout behavior. This batch command skips existing M05C SKU profiles by default, runs each pending SKU with coverage skipped, and rebuilds M05C coverage once at the end.

Run one TV SKU comment fact profile with LLM:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --sku-code TV00027354 --llm-mode required --max-sentences-per-sku 500 --format json
```

Run TV user task profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --force-rebuild --format json
```

Run one TV SKU user task profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --sku-code TV00027354 --format json
```

Run one TV user-task subset:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --user-task-code TASK_VALUE_FOR_MONEY_PURCHASE --force-rebuild --format json
```

Run TV target group profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --force-rebuild --format json
```

Run one TV SKU target group profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --sku-code TV00027354 --format json
```

Run one TV target-group subset:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --target-group-code TG_VALUE_MAXIMIZER --force-rebuild --format json
```

Run TV value battlefield profiles:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --force-rebuild --format json
```

Run one TV SKU value battlefield profile:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --sku-code TV00027354 --graph-mode inline --format json
```

Run one TV battlefield subset:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --battlefield-code BF_LARGE_SCREEN_VALUE_UPGRADE --force-rebuild --format json
```

Use `--input-source auto` by default. It reads M02 selling-point evidence first, then M01 cleaned claims, then raw `selling_points_data` only if needed. Use `--input-source raw` only when the current deployment has new raw selling points but M01/M02 have not been rerun yet.

Use `--batch-id latest` unless the user gives a specific batch id. Use `--force-rebuild` when source data or taxonomy/rules have changed and existing profile business keys should be refreshed.
For M07 market profiles, omit `--analysis-window` to run all windows. The CLI executes windows sequentially and splits TV SKUs into chunks, committing after each chunk to keep the 205 memory peak below the API container limit. The default `--sku-chunk-size` is 50; lower it for safer execution, raise it only after observing memory. Because the current 205 source batch can contain mixed TV/AC evidence under source `category_code=TV`, the CLI defaults to TV-prefixed SKU scope when no `--sku-code` is supplied. The current implementation writes market profiles, market signals, comparable pools, and pool members. Business absolute price-bucket persistence from the updated M07 design requires the follow-up M07 service/table implementation.
For M05C-B comment fact profiles, use `--llm-mode required` on 205 validation, `--llm-mode off` only for deterministic local tests, and lower `--llm-batch-size` if the LLM provider times out. For large batches, prefer `run-comment-profile-batch` over a single unscoped `run-comment-profile`: it schedules pending SKUs with bounded parallelism, skips existing profiles by default, and rebuilds coverage once after SKU workers finish. Do not run multiple workers for the same SKU. This command does not generate the category comment taxonomy; it only uses an already published taxonomy.
For M09C user task profiles, confirm the same batch already has current M03B, M04C, M05C, and M07 outputs. Use repeated `--sku-code` for scoped reruns and repeated `--user-task-code` for a user-task subset. This stage is deterministic and does not call an LLM.
For M10C target group profiles, confirm the same batch already has current M03B, M04C, M05C, and M07 outputs. Use repeated `--sku-code` for scoped reruns and repeated `--target-group-code` for a target-group subset. This stage is deterministic and does not call an LLM.
For M11C value battlefield profiles, confirm the same batch already has current M03B, M04C, M05C, and M07 outputs. Use `--graph-mode inline` to write the graph snapshot, `--graph-mode skip` to write only SKU profiles and score rows, repeated `--sku-code` for scoped reruns, and repeated `--battlefield-code` for a battlefield subset.

## Response Rules

After execution, summarize:

- Product category and batch id.
- Input evidence count and output count.
- SKU profile count, parameter value count, dimension tier count, and tier coverage count.
- For claim profiles, summarize SKU claim profile count, claim fact count, parameter-supported fact-claim count, service-fulfillment count, dimension position count, and position coverage count.
- For market profiles, summarize market profile count, market signal count, comparable-pool count, pool-member count, and review-required count.
- For comment profiles, summarize SKU comment profile count, comment fact count, coverage count, service-excluded sentence count, review-required count, and LLM mode/call/model status.
- For user task profiles, summarize SKU profile count, score count, coverage count, primary user-task distribution, relation status distribution, drag-factor task count, and any warnings about missing fact-layer inputs.
- For target group profiles, summarize SKU profile count, score count, coverage count, primary target-group distribution, relation status distribution, and any warnings about missing fact-layer inputs.
- For value battlefield profiles, summarize SKU profile count, score count, graph snapshot count, primary battlefield distribution, relation status distribution, and any warnings about missing fact-layer inputs.
- Warnings, especially empty input, parameter conflicts, or failed status.

If the CLI returns `error`, report the error and do not claim the job completed. If the job succeeds with warnings, state that outputs were written but review may be needed.
