# Runtime Export Boundary Specification

## Purpose
Protect factory-only IP while allowing delivery of single-category runtime assets.

## Allowed runtime export files
- `asset_manifest.json`
- `release_note.md`
- `std_param_def.csv`
- `std_claim_def.csv`
- `comment_topic_def.csv`
- `user_task_def.csv`
- `target_group_def.csv`
- `battlefield_def.csv`
- `mapping_rules.csv`
- `scoring_rules.yaml`
- `competitor_runtime_rules.yaml`
- `sku_analysis_results.parquet` or `.csv`
- `evidence_cards.jsonl`
- `quality_report.json`

## Forbidden export content
- prompt templates
- LLM traces
- rule generator source
- calibration optimizer internals
- Gold Set builder
- raw expert annotations
- cross-category migration templates
- category generator scripts
- secrets, API keys, environment files
- internal factory run logs that expose prompts or generation chain

## Required export tests
- Export contains only whitelist file names.
- Export scans file contents for forbidden keywords and patterns.
- Export manifest includes hashes for all files.
- Export refuses unreleased asset versions unless explicitly `--allow-draft` in dev mode.
