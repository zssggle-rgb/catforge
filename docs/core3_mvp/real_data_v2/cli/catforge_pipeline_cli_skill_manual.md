# CatForge Pipeline CLI and Claude Skill Manual

This manual documents the execution CLI for agent-driven data preparation, SKU parameter profile generation, SKU claim fact profile generation, SKU market profile generation, and SKU comment fact profile generation.

## Purpose

`catforge_pipeline` lets an agent or external caller run write actions without requiring the user to know module codes. The current implemented actions are:

1. Generate or rerun SKU parameter fact profiles for TV.
2. Generate or rerun SKU parameter fact profiles for AC.
3. Generate or rerun SKU claim fact profiles for TV.
4. Generate or rerun SKU market profiles, market signals, and comparable-pool baselines for TV.
5. Generate or rerun SKU comment fact profiles for TV with LLM-based comment semantic extraction.

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
```

The router is deterministic. It maps "彩电/电视/TV" to TV and "空调/AC" to AC. Requests that mention "卖点" route to claim fact profile generation; parameter requests route to parameter profile generation.
Requests that mention "市场画像", "量价画像", "价格区间", or "尺寸区间" route to M07 market-profile generation. The M07 CLI currently supports TV.
Requests that mention "评论事实画像", "评论画像", or "用户评价画像" route to M05C-B comment fact profile generation. This generation stage uses LLM extraction; the read-only query stage is handled by `catforge_insight`.

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
```

`--force-rebuild` replaces same business-key outputs when output hashes changed. Use it when source data, taxonomy, or rules have changed.

For `run-claim-profile`, use `--input-source auto` by default. It reads M02 selling-point evidence first, then M01 cleaned claims, then raw `selling_points_data` only if needed. Use `--input-source raw` only when raw selling points are current but M01/M02 have not been rerun.

For `run-market-profile`, omit `--analysis-window` to run all M07 windows. The CLI executes windows sequentially and splits TV SKUs into chunks, committing after each chunk to keep the 205 memory peak below the API container limit. The default `--sku-chunk-size` is 50; lower it for safer execution, raise it only after observing memory. Use repeated `--analysis-window` or repeated `--sku-code` for scoped reruns. Because the current 205 source batch can contain mixed TV/AC evidence under source `category_code=TV`, the CLI defaults to TV-prefixed SKU scope when no `--sku-code` is supplied. M07 currently writes existing market profiles, market signals, comparable pools, and pool members. Business absolute price-bucket fields from the updated M07 design require the follow-up M07 service/table implementation.

For `run-comment-profile`, use `--llm-mode required` on 205 when validating the real TV run. `--llm-batch-size` controls how many M02 comment sentences are sent per LLM request; lower it if the provider times out. `--max-sentences-per-sku` caps comment sentences per SKU for scoped validation and should be raised or omitted for full production-style runs. The command reads M02 comment sentences and existing M03B/M04C context; it does not regenerate M05C-A taxonomy.

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
