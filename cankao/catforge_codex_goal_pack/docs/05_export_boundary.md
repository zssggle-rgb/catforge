# 05. Factory vs Runtime Export Boundary

CatForge contains internal factory capabilities. A customer-facing runtime deliverable must not include factory-only capabilities unless a separate factory license is explicitly purchased.

## Exportable runtime assets

A released runtime package may include:

| File | Description |
|---|---|
| `std_param_def.csv` | Approved standard parameter definitions for one authorized category |
| `std_claim_def.csv` | Approved standard claim definitions |
| `comment_topic_def.csv` | Approved comment topic definitions |
| `user_task_def.csv` | Approved user task definitions |
| `target_group_def.csv` | Approved target group definitions |
| `battlefield_def.csv` | Approved value battlefield definitions |
| `mapping_rules.csv` | Approved mapping rules |
| `scoring.yaml` | Runtime scoring config |
| `competitor_rule.yaml` | Runtime competitor scoring config |
| `sample_sku_results.csv` | Optional sample results |
| `sample_evidence_cards.jsonl` | Optional sample evidence cards |
| `asset_readme.md` | Asset usage notes |
| `release_note.md` | Version release notes |

## Non-exportable factory assets

Do not export:

| Asset | Reason |
|---|---|
| Parameter auto-discovery scripts | They enable new-category construction |
| Parameter alias clustering tools | Factory capability |
| Claim semantic clustering tools | Factory capability |
| User task generation logic | Core methodology |
| Battlefield generation logic | Core methodology |
| Rule auto-calibration scripts | Internal optimization capability |
| Prompt templates and prompt lab | Factory-only IP |
| Gold Set builder | Evaluation methodology |
| Benchmark datasets / Gold Set unless approved | Can be used to replace vendor |
| Cross-category migration templates | Enables copying to new categories |
| Asset pack exporter internals | Factory packaging capability |

## Required automated boundary test

Every implementation must include a test that:

1. Generates a runtime export package.
2. Lists all files in package.
3. Fails if filenames or content paths include forbidden patterns:
   - `prompt`
   - `gold_set_builder`
   - `category_builder`
   - `migration_template`
   - `rule_generator`
   - `semantic_clustering`
   - `factory_internal`
   - `benchmark_builder`

## Product wording

Use this wording in customer-facing docs:

> This package contains approved runtime assets for the authorized category. It does not include category factory generation tools, prompt templates, benchmark builders, cross-category migration templates, or methods for generating assets for unauthorized categories.
