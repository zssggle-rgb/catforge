# G09 AC M11D Semantic Market Graph Adaptation

Date: 2026-07-08

## Status

Completed.

G09 adapted AC into the M11D semantic market graph pipeline and generated both business and diagnostic populations:

- `fact_complete_with_comment`: 140 SKU
- `all_semantic_profiles`: 144 SKU

The business population uses the G08 primary-profile gate: a SKU must have M05C comment facts, M07 market facts, and primary M09C/M10C/M11C profiles. The diagnostic population keeps all comment-ready semantic profiles for review and coverage inspection.

## Code Change

Files changed:

- `apps/api-server/app/services/core3_real_data/semantic_market_graph_service.py`
- `apps/api-server/app/cli/catforge_pipeline.py`
- `apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py`

Implementation:

- Added AC `PRODUCT_CATEGORY_INPUT_RULES` for M05C, M09C, M10C, M11C, and M07.
- Opened `PRODUCT_CATEGORY_CONFIGS["AC"]["semantic_market_rule_version"]`.
- Tightened `fact_complete_with_comment` to require primary user task, primary target group, and primary battlefield profiles.
- Kept `all_semantic_profiles` as a diagnostic population for comment-ready SKU that have profile rows but may still need review.
- Added exclusion diagnostics for missing primary profile dimensions.

## Verification

Local tests:

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py -q --tb=short
python -m pytest apps/api-server/tests/core3_real_data/test_m09c_user_task_profile.py apps/api-server/tests/core3_real_data/test_m10c_target_group_profile.py apps/api-server/tests/core3_real_data/test_m11c_value_battlefield_profile.py apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py -q --tb=short
```

Result:

- M11D target tests: 8 passed
- M09C/M10C/M11C/M11D target tests: 27 passed

205 hot update:

```bash
scp -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  apps/api-server/app/services/core3_real_data/semantic_market_graph_service.py \
  apps/api-server/app/cli/catforge_pipeline.py \
  deploy@123.56.42.205:/tmp/

ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem deploy@123.56.42.205 \
  "docker cp /tmp/semantic_market_graph_service.py catforge-api-1:/app/app/services/core3_real_data/semantic_market_graph_service.py && docker cp /tmp/catforge_pipeline.py catforge-api-1:/app/app/cli/catforge_pipeline.py && docker exec catforge-api-1 python -m py_compile /app/app/services/core3_real_data/semantic_market_graph_service.py /app/app/cli/catforge_pipeline.py"
```

205 smoke:

```bash
python -m app.cli.catforge_pipeline run-semantic-market-graph \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --analysis-population fact_complete_with_comment \
  --sku-code AC00028640 \
  --force-rebuild \
  --format json
```

Result:

- `input_count=1`
- `allocation_count=13`
- `summary_count=18`
- `graph_snapshot_count=1`
- `check_count=12`, all passed

## 205 Full Runs

Business population:

```bash
python -m app.cli.catforge_pipeline run-semantic-market-graph \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --analysis-population fact_complete_with_comment \
  --force-rebuild \
  --format json
```

Result:

- `input_count=140`
- `allocation_count=1489`
- `summary_count=33`
- `contribution_count=1489`
- `graph_snapshot_count=1`
- `check_count=1263`, all passed
- Excluded SKU: 15
  - 11 no M05C/comment-ready semantic input
  - 1 missing primary user task
  - 3 missing primary target group
  - 2 missing primary battlefield

Diagnostic population:

```bash
python -m app.cli.catforge_pipeline run-semantic-market-graph \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --analysis-population all_semantic_profiles \
  --force-rebuild \
  --format json
```

Result:

- `input_count=144`
- `allocation_count=1506`
- `summary_count=33`
- `contribution_count=1506`
- `graph_snapshot_count=1`
- `check_count=1289`
- `check_status_counts={"diagnostic": 5, "passed": 1284}`
- Excluded SKU: 11 no M05C/comment-ready semantic input

## Current DB Coverage

Read-only coverage query on 205:

| Table group | Population | SKU count | Rows |
| --- | --- | ---: | ---: |
| graph snapshot | `fact_complete_with_comment` | 140 | 1 |
| allocation | `fact_complete_with_comment` | 140 | 1489 |
| dimension summary | `fact_complete_with_comment` | - | 33 |
| contribution | `fact_complete_with_comment` | 140 | 1489 |
| reconciliation checks | `fact_complete_with_comment` | 140 actual SKU | 1263 passed |
| graph snapshot | `all_semantic_profiles` | 144 | 1 |
| allocation | `all_semantic_profiles` | 144 | 1506 |
| dimension summary | `all_semantic_profiles` | - | 33 |
| contribution | `all_semantic_profiles` | 144 | 1506 |
| reconciliation checks | `all_semantic_profiles` | 144 actual SKU | 1284 passed, 5 diagnostic |

The reconciliation table has one extra empty `sku_code` in the fact-complete distinct count. The allocation and contribution tables remain at 140 actual SKU.

## Analyst Read Check

`semantic-dimension-space`:

```bash
python -m app.cli.catforge_analyst semantic-dimension-space \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --dimension-type battlefield \
  --limit 1 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `analysis_population=fact_complete_with_comment`
- `batch_id=m00_20260624000202_1150a669`
- `summary_count=11`
- first battlefield: `BF_WALL_1_5_MAINSTREAM_VALUE` / `1.5匹挂机主流性价比战场`

`battlefield-space`:

```bash
python -m app.cli.catforge_analyst battlefield-space \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --limit 1 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `analysis_population=fact_complete_with_comment`
- `summary_count=11`
- first battlefield: `BF_WALL_1_5_MAINSTREAM_VALUE`
- first battlefield primary SKU count: 56
- first battlefield allocated SKU count: 57
- first battlefield sales amount share: 0.40103

## Acceptance

- AC M11D has explicit product-category input rules.
- AC does not read TV M05C/M09C/M10C/M11C rule versions.
- No-comment SKU are excluded from the semantic graph.
- `fact_complete_with_comment` only includes SKU with primary M09C/M10C/M11C profiles.
- `all_semantic_profiles` remains available as a review/diagnostic population.
- `catforge_analyst` can read AC battlefield graph outputs with `product_category=ac`.

## Next

Continue with G10: AC M12C adaptation and generation.
