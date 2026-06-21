# CatForge Insight CLI and Claude Skill Manual

This manual documents the read-only insight interface for parameter profiles and claim fact profiles.

## Purpose

`catforge_insight` lets an agent or external caller query:

1. One SKU/model's parameter fact profile.
2. The TV or AC standard parameter taxonomy.
3. SKU coverage for a parameter tier.
4. One SKU/model's TV claim fact profile.
5. The TV standard claim taxonomy.
6. SKU coverage for a TV claim position.

It does not generate or mutate data. It reads M03B outputs from:

- `core3_sku_param_profile`
- `core3_extract_param_value`
- `core3_sku_param_dimension_tier`
- `core3_param_tier_coverage`

It reads M04C outputs from:

- `core3_sku_claim_fact_profile`
- `core3_sku_claim_fact`
- `core3_sku_claim_dimension_position`
- `core3_claim_position_coverage`

## Runtime

On 205, run from `/opt/catforge` inside the API container:

```bash
docker compose -f docker-compose.cloud.yml exec -T api python -m app.cli.catforge_insight <command>
```

Defaults:

- `project_id`: `d8d2245b-358b-4a64-95cc-9d7f2341bd26`
- `category_code`: `TV`
- `batch_id`: `latest`, resolved to the latest batch that has M03B SKU parameter profiles.
- `product_category`: `auto` for natural-language `ask`, otherwise `tv` or `ac`.

Current 205 data note: AC evidence is still stored under the same source `category_code=TV` batch. The read interface separates AC from TV by product category rule version and taxonomy version, not by source `category_code`.

## Commands

### Natural-language router

```bash
python -m app.cli.catforge_insight ask "查 100A4F 的参数画像" --format json
python -m app.cli.catforge_insight ask "查彩电标准参数" --format json
python -m app.cli.catforge_insight ask "查空调标准参数" --format json
python -m app.cli.catforge_insight ask "查 MiniLED 档位覆盖哪些 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查空调新风档位覆盖哪些 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight ask "查 100A4F 的卖点画像" --format json
python -m app.cli.catforge_insight ask "查彩电标准卖点" --format json
python -m app.cli.catforge_insight ask "查 MiniLED 复合画质旗舰型覆盖哪些 SKU" --sku-limit 100 --format json
```

The router is deterministic and only maps common user wording to one of the atomic commands.

### SKU parameter profile

```bash
python -m app.cli.catforge_insight sku-param-profile --query 100A4F --format json
python -m app.cli.catforge_insight sku-param-profile --sku-code TV00027354 --include-param-values --format json
python -m app.cli.catforge_insight sku-param-profile --sku-code AC00000001 --product-category ac --include-param-values --format json
```

Output includes:

- SKU code and model name.
- Parameter completeness and known/unknown/conflict/review counts.
- Dimension tier profile.
- Dimension tier explanations and basis values.
- Core picture/gaming/system/eye-care parameter sections.
- Optional full extracted parameter values.

### Standard parameter taxonomy

```bash
python -m app.cli.catforge_insight tv-param-taxonomy --format json
python -m app.cli.catforge_insight tv-param-taxonomy --group picture --search MINILED --format json
python -m app.cli.catforge_insight ac-param-taxonomy --format json
python -m app.cli.catforge_insight param-taxonomy --product-category ac --group health --format json
```

Output includes:

- Taxonomy version.
- Standard parameter definitions.
- Parameter group counts.
- Raw field to standard parameter mapping.
- Dimension tier definitions.

### Tier coverage

```bash
python -m app.cli.catforge_insight tier-coverage --dimension-code display_tech --tier-code miniled --sku-limit 100 --format json
python -m app.cli.catforge_insight tier-coverage --query "旗舰画质覆盖 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight tier-coverage --product-category ac --dimension-code health --tier-code health_fresh_air --sku-limit 100 --format json
```

Output includes:

- Dimension and tier code/name.
- Rule summary.
- SKU count and ratio.
- SKU list, limited by `--sku-limit`; use `--sku-limit 0` to return all.

### SKU claim fact profile

```bash
python -m app.cli.catforge_insight sku-claim-profile --query 100A4F --include-claim-facts --format json
python -m app.cli.catforge_insight sku-claim-profile --sku-code TV00027354 --format json
```

Output includes:

- SKU code, model name, and brand name.
- Raw claim count, matched claim count, fact claim count, unsupported-by-parameter count, parameter-unknown count, and service-fulfillment count.
- Standard claim codes and parameter-supported fact claim codes.
- Dimension profile and claim positions.
- Optional claim fact rows, including parameter support explanation.

Service-fulfillment claims are separated and are not counted as product fact claims.

### Standard claim taxonomy

```bash
python -m app.cli.catforge_insight claim-taxonomy --product-category tv --format json
python -m app.cli.catforge_insight claim-taxonomy --product-category tv --search MiniLED --format json
python -m app.cli.catforge_insight claim-taxonomy --product-category tv --dimension 画质 --format json
```

Output includes:

- Claim taxonomy version.
- Standard claim definitions.
- Claim dimension counts.
- Support parameter mapping.
- Claim position definitions.

### Claim position coverage

```bash
python -m app.cli.catforge_insight claim-position-coverage --query "MiniLED 复合画质旗舰型覆盖 SKU" --sku-limit 100 --format json
python -m app.cli.catforge_insight claim-position-coverage --dimension-code 画质 --position-source supported --sku-limit 100 --format json
python -m app.cli.catforge_insight claim-position-coverage --query "AI 语音增强型有哪些 SKU" --sku-limit 100 --format json
```

Output includes:

- Dimension and position code/name.
- `position_source`: `supported` by default, meaning the position is based on parameter-supported fact claims.
- Rule summary.
- SKU count and ratio.
- SKU list, limited by `--sku-limit`; use `--sku-limit 0` to return all.

## Claude Code Skill

The corresponding Claude Code skill is stored in:

```text
tools/claude/skills/catforge-insight/SKILL.md
```

Install it to Claude Code by copying the directory to:

```text
/root/.claude/skills/catforge-insight
/home/deploy/.claude/skills/catforge-insight
```

The skill instructs Claude Code to use natural-language `ask` first, then use atomic commands when the intent is clear.

## Error Semantics

- `not_found`: no matching SKU/model profile exists in the selected batch.
- `ambiguous`: multiple SKU/model candidates matched; caller should ask for a fuller model name or exact SKU code.
- `error`: CLI usage or data access error.

All commands are read-only. They are safe to run repeatedly.
