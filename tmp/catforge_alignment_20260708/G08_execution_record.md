# G08 AC M09C/M10C/M11C Profile Completeness Repair

Date: 2026-07-08

## Status

Completed with explicit review downgrades.

G08 used the G07 comment-ready population as the semantic input boundary:

- AC serving SKU scope: 155
- AC M05C comment-ready SKU: 144
- AC no-comment semantic-ineligible SKU: 11

The 11 SKUs without current M05C are no longer current in M09C/M10C/M11C. They are excluded with `missing_m05c_comment_fact_profile_semantic_ineligible`.

## Code Change

M11C AC primary selection was too strict for sparse AC comparable pools. High-confidence AC value battlefield scores with `market_gate_status='adjacent'` stayed as `opportunity_battlefield`, even when user voice, claim support, and parameter support were strong.

Local change:

- File: `apps/api-server/app/services/core3_real_data/m11c_value_battlefield_service.py`
- Added AC-only promotion rule:
  - `relation_status='opportunity_battlefield'`
  - `market_gate_status='adjacent'`
  - `battlefield_score >= 0.6800`
  - `user_voice_score >= 0.5500`
  - `claim_alignment_score >= 0.3000`
  - `param_capability_score >= 0.5500`
- TV behavior remains unchanged.

Tests added:

- `test_m11c_ac_adjacent_opportunity_can_be_primary_when_evidence_is_strong`
- `test_m11c_tv_does_not_promote_adjacent_opportunity_to_primary`

## Verification

Local tests:

```bash
python -m pytest apps/api-server/tests/core3_real_data/test_m11c_value_battlefield_profile.py -q --tb=short
python -m pytest apps/api-server/tests/core3_real_data/test_m09c_user_task_profile.py apps/api-server/tests/core3_real_data/test_m10c_target_group_profile.py apps/api-server/tests/core3_real_data/test_m11c_value_battlefield_profile.py -q --tb=short
```

Result:

- M11C target tests: 11 passed
- M09C/M10C/M11C target tests: 19 passed

205 hot update:

```bash
scp -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  apps/api-server/app/services/core3_real_data/m11c_value_battlefield_service.py \
  deploy@123.56.42.205:/tmp/m11c_value_battlefield_service.py

ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem deploy@123.56.42.205 \
  "docker cp /tmp/m11c_value_battlefield_service.py catforge-api-1:/app/app/services/core3_real_data/m11c_value_battlefield_service.py && docker exec catforge-api-1 python -m py_compile /app/app/services/core3_real_data/m11c_value_battlefield_service.py"
```

205 smoke:

```bash
python -m app.cli.catforge_pipeline run-value-battlefield \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --sku-code AC00028640 \
  --graph-mode skip \
  --force-rebuild \
  --format json
```

Result: `AC00028640` generated `primary_battlefield_counts={"BF_FLOOR_3_LIVING_VALUE_UPGRADE": 1}`.

## 205 Full Runs

M09C:

```bash
python -m app.cli.catforge_pipeline run-user-task \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --force-rebuild \
  --format json
```

M10C:

```bash
python -m app.cli.catforge_pipeline run-target-group \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --force-rebuild \
  --format json
```

M11C:

```bash
python -m app.cli.catforge_pipeline run-value-battlefield \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id m00_20260624000202_1150a669 \
  --product-category ac \
  --graph-mode inline \
  --force-rebuild \
  --format json
```

## Final Coverage

| Module | Current profiles | Primary SKU | Profile without M05C | Missing profile among M05C | Missing primary with reason |
| --- | ---: | ---: | ---: | ---: | ---: |
| M09C | 144 | 143 | 0 | 0 | 1 |
| M10C | 144 | 141 | 0 | 0 | 3 |
| M11C | 144 | 142 | 0 | 0 | 2 |

Remaining explicit review downgrades:

| Module | SKU | Reason |
| --- | --- | --- |
| M09C | `AC00038751` | 厂家卖点和参数有任务指向，但缺少用户评论验证，未形成主用户任务。 |
| M10C | `AC00038066` | 有评论观察、厂家表达或潜在适配，但尚未形成用户声音、卖点和参数共同支撑的主目标客群。 |
| M10C | `AC00038478` | 有评论观察、厂家表达或潜在适配，但尚未形成用户声音、卖点和参数共同支撑的主目标客群。 |
| M10C | `AC00038751` | 有评论观察、厂家表达或潜在适配，但尚未形成用户声音、卖点和参数共同支撑的主目标客群。 |
| M11C | `AC00038066` | top relation `brand_claimed_battlefield`, no user voice; keep review. |
| M11C | `AC00039165` | top relation `brand_claimed_battlefield`, no user voice; keep review. |

G09 downstream population:

- `all_semantic_profiles`: 144 comment-ready SKU
- `fact_complete_with_comment`: 140 SKU with primary user task, primary target group, and primary battlefield
- Review/downgrade SKU: `AC00038066`, `AC00038478`, `AC00038751`, `AC00039165`

## Acceptance

- No-comment SKU are excluded from current semantic profiles.
- Every comment-ready SKU has current M09C/M10C/M11C profile rows.
- Missing primary codes are not silent; every remaining case has explicit `review_required` and review reason.
- AC M11C high-confidence adjacent opportunities now become primary battlefields when supported by user voice, claim evidence, and param evidence.

## Next

Continue with G09: AC M11D adaptation and generation.
