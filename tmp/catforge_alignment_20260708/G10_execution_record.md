# G10 AC M12C Claim Value Quantification Adaptation

Date: 2026-07-08

## Status

Completed with pool-level sample review warnings.

G10 adapted AC into M12C claim value quantification and generated the full AC business population:

- Comparable / eligible SKU: 140
- SKU claim value rows: 6303
- Claim contribution attribution rows: 2491
- Pool-level review issues: 405 `sample_insufficient`

## Code Change

Files changed:

- `apps/api-server/app/services/core3_real_data/m12c_claim_value_quantification_service.py`
- `apps/api-server/app/cli/catforge_pipeline.py`
- `apps/api-server/tests/core3_real_data/test_m12c_product_category_rules.py`

Implementation:

- Added `M12C_PRODUCT_CATEGORY_INPUT_RULES` for TV and AC.
- M12C repository now selects M03B/M04C/M05C/M09C/M10C/M11C/M11D input rule versions by `product_category`.
- AC pipeline now enables `claim_value_quantification_rule_version`.
- Added AC claim-to-param fallback and aliases for:
  - energy efficiency / APF
  - large airflow / coverage
  - fast cooling / heating
  - soft wind / no direct blowing
  - self-cleaning
  - purification / antibacterial
  - smart app / voice / IoT
  - installation / space design
  - fresh air
- M12C run summary now records `input_rule_versions`, so AC results are traceable to AC M04C/M05C/M09C/M10C/M11C/M11D rules.

Decision:

- M12C output `rule_version` remains `m12c_claim_value_quantification_v0.1` for now to preserve current `catforge_analyst` and publish readers, which already filter by this rule. AC isolation is enforced by `product_category=AC`, `category_code=AC`, and recorded AC input rule versions.

## Verification

Local tests:

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_m12c_product_category_rules.py apps/api-server/tests/core3_real_data/test_m12c_param_value_parsing.py -q --tb=short
python -m pytest apps/api-server/tests/core3_real_data/test_m12c_product_category_rules.py apps/api-server/tests/core3_real_data/test_m12c_param_value_parsing.py apps/api-server/tests/core3_real_data/test_m11d_semantic_market_graph_allocation.py -q --tb=short
```

Result:

- M12C product-category + param parsing tests: 17 passed
- M12C + M11D regression tests: 25 passed

205 read-only precheck:

| Input | SKU count | Rows |
| --- | ---: | ---: |
| M07 AC market | 155 | - |
| M04C AC claim profile | 155 | - |
| M04C AC claim fact | 155 | 3931 |
| M05C AC comment profile | 144 | - |
| M11D AC fact_complete contribution | 140 | - |
| Existing AC M12C current | 0 | 0 |
| M12C ready intersection | 140 | - |

205 hot update:

```bash
scp -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  apps/api-server/app/services/core3_real_data/m12c_claim_value_quantification_service.py \
  apps/api-server/app/cli/catforge_pipeline.py \
  deploy@123.56.42.205:/tmp/

ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem deploy@123.56.42.205 \
  "docker cp /tmp/m12c_claim_value_quantification_service.py catforge-api-1:/app/app/services/core3_real_data/m12c_claim_value_quantification_service.py && docker cp /tmp/catforge_pipeline.py catforge-api-1:/app/app/cli/catforge_pipeline.py && docker exec catforge-api-1 python -m py_compile /app/app/services/core3_real_data/m12c_claim_value_quantification_service.py /app/app/cli/catforge_pipeline.py"
```

205 smoke:

```bash
python -m app.cli.catforge_pipeline run-claim-value-quantification \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --analysis-population claim_value_ready_with_comment \
  --sku-code AC00028640 \
  --format json
```

Result:

- `input_count=1`
- `comparable_sku_count=140`
- `claim_pool_count=902`
- `pool_metric_count=902`
- `sku_claim_value_count=52`
- `sku_attribution_count=19`
- `dimension_summary_count=52`
- `review_issue_count=405`
- `input_rule_versions` uses AC M03B/M04C/M05C/M09C/M10C/M11C/M11D rules.

## 205 Full Run

```bash
python -m app.cli.catforge_pipeline run-claim-value-quantification \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --analysis-population claim_value_ready_with_comment \
  --format json
```

Result:

- `status=warning`
- `input_count=140`
- `output_count=11517`
- `eligible_sku_count=140`
- `comparable_sku_count=140`
- `claim_pool_count=902`
- `pool_metric_count=902`
- `sku_claim_value_count=6303`
- `sku_attribution_count=2491`
- `dimension_summary_count=514`
- `review_issue_count=405`
- `sample_status_counts={"insufficient": 405, "sufficient": 497}`
- `role_counts={"basic_threshold": 889, "drag_factor": 672, "high_price_competitor_intercept": 1686, "opportunity_gap": 1132, "price_up_opportunity": 547, "sales_driver_estimated": 405, "weak_user_perception_claim": 972}`

Warning interpretation:

- The single warning is expected review routing: `M12C 生成 405 条样本或可比池复核问题。`
- Review issue aggregation: 405 rows, all `issue_scope=pool`, `issue_code=sample_insufficient`.
- No SKU-level silent M12C failure was found.

## Current DB Coverage

Read-only coverage query on 205:

| Table group | SKU count | Rows | Claim count |
| --- | ---: | ---: | ---: |
| context pool | - | 902 | 18 |
| pool metric | - | 902 | 18 |
| SKU claim value | 140 | 6303 | 9 |
| contribution attribution | 140 | 2491 | - |
| dimension summary | - | 514 | 9 |
| review issue | pool-level | 405 | - |

Claim value role distribution:

| Role | Rows | SKU count |
| --- | ---: | ---: |
| `high_price_competitor_intercept` | 1686 | 134 |
| `opportunity_gap` | 1132 | 131 |
| `weak_user_perception_claim` | 972 | 131 |
| `basic_threshold` | 889 | 128 |
| `drag_factor` | 672 | 98 |
| `price_up_opportunity` | 547 | 91 |
| `sales_driver_estimated` | 405 | 101 |

## Analyst Read Check

`sku-claim-value`:

```bash
python -m app.cli.catforge_analyst sku-claim-value \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --sku-code AC00028640 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `sku_code=AC00028640`
- returned claim values: 3
- SKU-level claim values: 9
- attributions: 3
- first returned claim: `ac_claim_smart_app_voice_iot` / `APP/语音/IoT 智控`

`claim-value-space`:

```bash
python -m app.cli.catforge_analyst claim-value-space \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `summary_count=3`
- first returned claim: `ac_claim_self_cleaning` / `自清洁/自洁`

`claim-contribution`:

```bash
python -m app.cli.catforge_analyst claim-contribution \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --sku-code AC00028640 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `sku_code=AC00028640`
- returned attributions: 3

## Acceptance

- AC M12C is enabled in the pipeline.
- AC M12C reads AC M03B/M04C/M05C/M09C/M10C/M11C/M11D input rule versions.
- No-comment SKU remain excluded through the G09 fact-complete boundary.
- M12C generated pool metric, SKU claim value, dimension summary, and contribution attribution rows.
- `catforge_analyst sku-claim-value --product-category ac` can read the results.

## Next

Continue with G11: TV/AC intelligent-agent consumption acceptance.
