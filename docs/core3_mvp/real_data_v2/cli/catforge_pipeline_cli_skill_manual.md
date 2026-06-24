# CatForge Pipeline CLI and Claude Skill Manual

This manual documents the execution CLI for agent-driven data preparation, SKU parameter profile generation, SKU claim fact profile generation, SKU market profile generation, SKU comment fact profile generation, SKU user task generation, SKU target group generation, SKU value battlefield generation, semantic market graph generation, and claim-value quantification.

## Purpose

`catforge_pipeline` lets an agent or external caller run write actions without requiring the user to know module codes. The current implemented actions are:

1. Generate or rerun SKU parameter fact profiles for TV.
2. Generate or rerun SKU parameter fact profiles for AC.
3. Generate or rerun SKU claim fact profiles for TV.
4. Generate or rerun SKU market profiles, market signals, and comparable-pool baselines for TV.
5. Generate or rerun SKU comment fact profiles for TV with LLM-based comment semantic extraction.
6. Generate or rerun SKU user task profiles, SKU x user-task scores, and user-task coverage for TV.
7. Generate or rerun SKU target group profiles, SKU x target-group scores, and target-group coverage for TV.
8. Generate or rerun SKU value battlefield profiles, SKU x battlefield scores, and value battlefield graph snapshots for TV.
9. Generate or rerun semantic market graph and sales allocation for TV.
10. Generate or rerun claim-value quantification and claim-contribution attribution for TV.

For read-only questions, use `catforge_insight` instead.

## Runtime

On 205, run from `/opt/catforge` inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_pipeline <command>
```

Defaults:

- `project_id`: `d8d2245b-358b-4a64-95cc-9d7f2341bd26`
- source `category_code`: `TV`
- `batch_id`: `latest`, resolved to the latest source batch.

Current 205 data note: TV and AC evidence are in the same source batch. The CLI isolates product categories with SKU prefixes and taxonomy/rule versions:

| Product category | SKU prefix | Taxonomy version | Rule version |
|---|---|---|---|
| TV | `TV` | `tv_param_taxonomy_manual_v0.1` | `m03b_tv_param_profile_v0.1` |
| AC | `AC` | `ac_param_taxonomy_manual_v0.1` | `m03b_ac_param_profile_v0.1` |

M04C claim fact profiles currently have a published TV taxonomy only:

| Product category | SKU prefix | Claim taxonomy version | Claim rule version |
|---|---|---|---|
| TV | `TV` | `tv_claim_taxonomy_manual_v0.1` | `m04c_tv_claim_fact_profile_v0.1` |
| AC | `AC` | not published | not available |

M05C-B comment fact profiles currently have a published TV taxonomy only. In business discussion this stage may also be called `m05b`; in this implementation it is the M05C-B SKU comment fact profile generator. It uses an LLM to map M02 comment sentences into comment facts. M05C-C is read-only query and does not call an LLM.

| Product category | SKU prefix | Comment taxonomy version | Comment rule version |
|---|---|---|---|
| TV | `TV` | `tv_comment_fact_taxonomy_manual_v0.1` | `m05c_tv_comment_fact_profile_v0.1` |
| AC | `AC` | not published | not available |

M10C target group profiles currently have a published TV taxonomy only. M10C does not call an LLM. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, M07 weighted prices, and M01 clean weekly market rows. It uses the M03B five-tier size policy and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier. Market validation uses same-size peer overlap weeks and average weekly volume/amount; cumulative sales are display-only and must not be used for target-group judgment.

| Product category | SKU prefix | Target group taxonomy version | Target group rule version |
|---|---|---|---|
| TV | `TV` | `m10c_tv_target_group_taxonomy_v0.1` | `m10c_tv_target_group_profile_v0.1` |
| AC | `AC` | not published | not available |

M11C value battlefield profiles currently have a published TV taxonomy only. M11C does not call an LLM. It reads M03B parameter profiles, M04C claim fact profiles, M05C comment fact profiles, M07 weighted prices, and M01 clean weekly market rows. It uses the M03B five-tier size policy and derives `low/mid_low/mid/mid_high/high` price bands inside each size tier. Market validation uses same-size peer overlap weeks and average weekly volume/amount; cumulative sales are display-only and must not be used for battlefield judgment.

| Product category | SKU prefix | Value battlefield taxonomy version | Value battlefield rule version |
|---|---|---|---|
| TV | `TV` | `m11c_tv_value_battlefield_taxonomy_v0.1` | `m11c_tv_value_battlefield_profile_v0.1` |
| AC | `AC` | not published | not available |

M11D semantic market graph and sales allocation is deterministic. It reads M05C, M09C, M10C, M11C, and M07 outputs and writes user-task, target-group, and value-battlefield market maps plus SKU sales allocation. Use `fact_complete_with_comment` for business-facing graph outputs.

M12C claim-value quantification and contribution attribution is deterministic. It reads M03B, M04C, M05C, M07, M09C, M10C, M11C, and M11D outputs and writes claim comparable pools, pool metrics, SKU claim-value roles, SKU claim-contribution attribution, claim dimension summaries, and review issues. Use `claim_value_ready_with_comment` for business-facing claim-value outputs. M12C values are observable contribution estimates, not causal proof.

LLM configuration is read only from environment variables. Do not write API keys into code, docs, shell history, or committed files.

```bash
export CATFORGE_M05C_LLM_BASE_URL=https://api.deepseek.com
export CATFORGE_M05C_LLM_MODEL=deepseek-v4-pro
export CATFORGE_M05C_LLM_API_KEY=***
```

Use `--llm-mode required` for 205 validation so the run fails if the LLM is not configured or cannot be called. Use `--llm-mode off` only for deterministic local tests.

## Commands

### Natural-language router

```bash
python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 参数画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "生成空调 SKU 参数画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 卖点事实画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电市场画像" --format json
python -m app.cli.catforge_pipeline ask "重新生成 TV00027354 的市场画像" --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电评论事实画像" --llm-mode required --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重跑 TV00027354 的评论画像" --llm-mode required --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电目标客群画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重跑 TV00027354 的目标客户分析" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电价值战场画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重跑 TV00027354 的价值战场画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电语义市场图谱和销量分配" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "生成彩电卖点价值量化和贡献归因" --format json
```

The router is deterministic. It maps "彩电/电视/TV" to TV and "空调/AC" to AC. Requests that mention "卖点" route to claim fact profile generation; parameter requests route to parameter profile generation.
Requests that mention "市场画像", "量价画像", "价格区间", or "尺寸区间" route to M07 market-profile generation. The M07 CLI currently supports TV.
Requests that mention "评论事实画像", "评论画像", or "用户评价画像" route to M05C-B comment fact profile generation. This generation stage uses LLM extraction; the read-only query stage is handled by `catforge_insight`.
Requests that mention "目标客群", "目标客户", "目标用户", or "客群画像" route to M10C target group profile generation. This stage is deterministic and does not call an LLM.
Requests that mention "价值战场", "战场画像", or "战场图谱" route to M11C value battlefield profile generation. This stage is deterministic and does not call an LLM.
Requests that mention "语义市场图谱", "销量分配", "市场空间" route to M11D semantic market graph generation.
Requests that mention "卖点价值量化", "卖点贡献归因", "溢价卖点量化", or "哪些卖点值钱" with execution verbs route to M12C claim-value quantification.

### Atomic command

```bash
python -m app.cli.catforge_pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-param-profile --product-category ac --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-claim-profile --product-category tv --batch-id latest --input-source auto --force-rebuild --format json
python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --format json
python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --analysis-window full_observed_window --sku-code TV00027354 --format json
python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --sku-chunk-size 50 --format json
python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --llm-mode required --force-rebuild --format json
python -m app.cli.catforge_pipeline run-comment-profile --product-category tv --batch-id latest --sku-code TV00027354 --llm-mode required --max-sentences-per-sku 500 --format json
python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-user-task --product-category tv --batch-id latest --sku-code TV00027354 --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --sku-code TV00027354 --force-rebuild --format json
python -m app.cli.catforge_pipeline run-target-group --product-category tv --batch-id latest --target-group-code TG_VALUE_MAXIMIZER --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --sku-code TV00027354 --graph-mode inline --force-rebuild --format json
python -m app.cli.catforge_pipeline run-value-battlefield --product-category tv --batch-id latest --battlefield-code BF_LARGE_SCREEN_VALUE_UPGRADE --force-rebuild --format json
python -m app.cli.catforge_pipeline run-semantic-market-graph --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-claim-value-quantification --product-category tv --batch-id latest --analysis-population claim_value_ready_with_comment --market-window full_observed_window --format json
python -m app.cli.catforge_pipeline run-claim-value-quantification --product-category tv --batch-id latest --sku-code TV00027354 --analysis-population claim_value_ready_with_comment --format json
```

`--force-rebuild` replaces same business-key outputs when output hashes changed. Use it when source data, taxonomy, or rules have changed.

For `run-claim-profile`, use `--input-source auto` by default. It reads M02 selling-point evidence first, then M01 cleaned claims, then raw `selling_points_data` only if needed. Use `--input-source raw` only when raw selling points are current but M01/M02 have not been rerun.

For `run-market-profile`, omit `--analysis-window` to run all M07 windows. The CLI executes windows sequentially and splits TV SKUs into chunks, committing after each chunk to keep the 205 memory peak below the API container limit. The default `--sku-chunk-size` is 50; lower it for safer execution, raise it only after observing memory. Use repeated `--analysis-window` or repeated `--sku-code` for scoped reruns. Because the current 205 source batch can contain mixed TV/AC evidence under source `category_code=TV`, the CLI defaults to TV-prefixed SKU scope when no `--sku-code` is supplied. M07 currently writes existing market profiles, market signals, comparable pools, and pool members. Business absolute price-bucket fields from the updated M07 design require the follow-up M07 service/table implementation.

For `run-comment-profile`, use `--llm-mode required` on 205 when validating the real TV run. `--llm-batch-size` controls how many M02 comment sentences are sent per LLM request; lower it if the provider times out. `--max-sentences-per-sku` caps comment sentences per SKU for scoped validation and should be raised or omitted for full production-style runs. The command reads M02 comment sentences and existing M03B/M04C context; it does not regenerate M05C-A taxonomy.

For `run-target-group`, make sure M03B, M04C, M05C, M07 price outputs, and M01 clean weekly market rows are current for the same batch. Use repeated `--sku-code` for scoped reruns and repeated `--target-group-code` to limit scoring to specific target-group definitions. Because M10C derives price bands inside the M03B size tier and validates market strength by same-size overlap weekly averages, it should be rerun after market prices, weekly market rows, parameter size tiers, claim facts, or comment facts change.

For `run-value-battlefield`, make sure M03B, M04C, M05C, M07 price outputs, and M01 clean weekly market rows are current for the same batch. Use repeated `--sku-code` for scoped reruns and repeated `--battlefield-code` to limit scoring to specific battlefield definitions. `--graph-mode inline` writes a graph snapshot with coverage statistics; `--graph-mode skip` only writes SKU profiles and score rows. Because M11C derives price bands inside the M03B size tier and validates market strength by same-size overlap weekly averages, it should be rerun after market prices, weekly market rows, parameter size tiers, claim facts, or comment facts change.

For `run-semantic-market-graph`, make sure M05C, M09C, M10C, M11C, and M07 are current for the same batch. Keep `--analysis-population fact_complete_with_comment` for business-facing graph outputs. Use repeated `--dimension-type user_task|target_group|battlefield` for scoped graph reruns.

For `run-claim-value-quantification`, make sure M03B, M04C, M05C, M07, M09C, M10C, M11C, and M11D are current for the same batch. Keep `--analysis-population claim_value_ready_with_comment` for business-facing claim-value outputs. Use `claim_value_ready` only for diagnostics that intentionally include SKUs without comment facts. Use repeated `--sku-code` for scoped reruns. Report M12C outputs as observable price, weekly-sales, and weekly-amount contribution estimates, not strict causality.

## Outputs

Output includes:

- Product category and source batch id.
- SKU prefix boundary.
- Taxonomy/parser/rule versions.
- Input evidence count.
- Output count.
- SKU profile count, parameter value count, dimension tier count, and tier coverage count.
- For claim profiles: SKU profile count, claim fact count, parameter-supported fact claim count, service-fulfillment count, dimension position count, and position coverage count.
- For market profiles: market profile count, market signal count, comparable-pool count, pool-member count, and review-required count.
- For comment profiles: SKU comment profile count, comment fact count, coverage count, service-excluded sentence count, review-required count, and LLM mode/call/model status.
- For target group profiles: SKU profile count, SKU x target-group score count, coverage count, primary target-group counts, relation status counts, and size-price counts.
- For value battlefield profiles: SKU profile count, SKU x battlefield score count, graph snapshot count, primary battlefield counts, relation status counts, and size-price counts.
- For semantic market graph: analysis population, included SKU count, allocation count, dimension summary count, contribution count, graph snapshot count, and check count.
- For claim-value quantification: analysis population, market window, comparable-pool count, pool-metric count, SKU claim-value count, contribution-attribution count, dimension-summary count, review-issue count, and role distribution.
- Warnings.

## Claude Code Skill

The corresponding Claude Code skill is stored in:

```text
tools/claude/skills/catforge-pipeline/SKILL.md
```

Install it to Claude Code by copying the directory to:

```text
/root/.claude/skills/catforge-pipeline
/home/deploy/.claude/skills/catforge-pipeline
```

## Error Semantics

- `ok`: outputs were written successfully.
- `warning`: outputs were written but review may be needed.
- `error`: the job failed or the natural-language request was outside the implemented execution scope.

Do not claim completion when the CLI returns `error`.
