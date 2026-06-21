# CatForge Pipeline CLI and Claude Skill Manual

This manual documents the execution CLI for agent-driven data preparation, SKU parameter profile generation, SKU claim fact profile generation, and SKU market profile generation.

## Purpose

`catforge_pipeline` lets an agent or external caller run write actions without requiring the user to know module codes. The current implemented actions are:

1. Generate or rerun SKU parameter fact profiles for TV.
2. Generate or rerun SKU parameter fact profiles for AC.
3. Generate or rerun SKU claim fact profiles for TV.
4. Generate or rerun SKU market profiles, market signals, and comparable-pool baselines for TV.

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

## Commands

### Natural-language router

```bash
python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 参数画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "生成空调 SKU 参数画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 卖点事实画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "重新生成彩电市场画像" --format json
python -m app.cli.catforge_pipeline ask "重新生成 TV00027354 的市场画像" --format json
```

The router is deterministic. It maps "彩电/电视/TV" to TV and "空调/AC" to AC. Requests that mention "卖点" route to claim fact profile generation; parameter requests route to parameter profile generation.
Requests that mention "市场画像", "量价画像", "价格区间", or "尺寸区间" route to M07 market-profile generation. The M07 CLI currently supports TV.

### Atomic command

```bash
python -m app.cli.catforge_pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-param-profile --product-category ac --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-claim-profile --product-category tv --batch-id latest --input-source auto --force-rebuild --format json
python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --format json
python -m app.cli.catforge_pipeline run-market-profile --batch-id latest --analysis-window full_observed_window --sku-code TV00027354 --format json
```

`--force-rebuild` replaces same business-key outputs when output hashes changed. Use it when source data, taxonomy, or rules have changed.

For `run-claim-profile`, use `--input-source auto` by default. It reads M02 selling-point evidence first, then M01 cleaned claims, then raw `selling_points_data` only if needed. Use `--input-source raw` only when raw selling points are current but M01/M02 have not been rerun.

For `run-market-profile`, omit `--analysis-window` to run all M07 windows. The CLI executes those windows sequentially and commits after each window to keep the 205 memory peak lower than a single all-window in-process run. Use repeated `--analysis-window` or repeated `--sku-code` for scoped reruns. Because the current 205 source batch can contain mixed TV/AC evidence under source `category_code=TV`, the CLI defaults to TV-prefixed SKU scope when no `--sku-code` is supplied. M07 currently writes existing market profiles, market signals, comparable pools, and pool members. Business absolute price-bucket fields from the updated M07 design require the follow-up M07 service/table implementation.

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
