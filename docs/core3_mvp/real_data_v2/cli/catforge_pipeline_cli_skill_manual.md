# CatForge Pipeline CLI and Claude Skill Manual

This manual documents the execution CLI for agent-driven data preparation and SKU parameter profile generation.

## Purpose

`catforge_pipeline` lets an agent or external caller run write actions without requiring the user to know module codes. The current implemented action is:

1. Generate or rerun SKU parameter fact profiles for TV.
2. Generate or rerun SKU parameter fact profiles for AC.

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

## Commands

### Natural-language router

```bash
python -m app.cli.catforge_pipeline ask "重新生成彩电 SKU 参数画像" --force-rebuild --format json
python -m app.cli.catforge_pipeline ask "生成空调 SKU 参数画像" --force-rebuild --format json
```

The router is deterministic. It maps "彩电/电视/TV" to TV and "空调/AC" to AC. It only executes parameter profile generation.

### Atomic command

```bash
python -m app.cli.catforge_pipeline run-param-profile --product-category tv --batch-id latest --force-rebuild --format json
python -m app.cli.catforge_pipeline run-param-profile --product-category ac --batch-id latest --force-rebuild --format json
```

`--force-rebuild` replaces same business-key outputs when output hashes changed. Use it when source data, taxonomy, or rules have changed.

## Outputs

Output includes:

- Product category and source batch id.
- SKU prefix boundary.
- Taxonomy/parser/rule versions.
- Input evidence count.
- Output count.
- SKU profile count, parameter value count, dimension tier count, and tier coverage count.
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
