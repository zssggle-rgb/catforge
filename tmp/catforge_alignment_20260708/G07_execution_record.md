# G07 AC M05C Tail Gap Audit

Date: 2026-07-08

## Status

Completed.

G07 did not write data to 205 and did not rerun M00-M02. The AC M05C gap is explained by upstream clean/M02 eligibility, not by missing M05C processing.

## Read-Only Checks

205 target:

- Host: `123.56.42.205`
- API container: `catforge-api-1`
- Product category: `AC`

Commands executed:

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new \
  deploy@123.56.42.205 \
  "docker exec -i catforge-api-1 python -"
```

```bash
ssh -i /Users/sjs/hxmvp/HX-ECS-海信.pem \
  -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new \
  deploy@123.56.42.205 \
  "docker exec catforge-api-1 sh -lc 'command -v pgrep >/dev/null && pgrep -af \"catforge_pipeline|run-claim-value-quantification|run-semantic-market-graph|run-comment-profile\" || true'"
```

Residual process check returned no running CatForge pipeline process.

## Coverage Findings

AC has two relevant batches:

| Batch | Role | SKU coverage |
| --- | --- | ---: |
| `m00_20260623020057_41b43cb5` | comment batch | `core3_clean_sku` 147 SKU |
| `m00_20260624000202_1150a669` | main AC batch | `core3_clean_sku` 155 SKU, market 155 SKU, claim 155 SKU |

Comment-layer coverage:

| Layer | AC SKU count |
| --- | ---: |
| `core3_clean_comment` active SKU | 146 |
| `core3_clean_comment` active and non-low-value SKU | 144 |
| `core3_clean_comment_sentence` SKU | 144 |
| M02 current comment evidence SKU | 144 |
| M05C current `m05c_ac_comment_fact_profile_v0.1` SKU | 144 |

M02 current comment evidence and M05C current are aligned:

| Metric | Count |
| --- | ---: |
| M02 comment evidence SKU | 144 |
| M05C current SKU | 144 |
| M02 SKU missing M05C | 0 |
| M05C SKU not in M02 | 0 |

## Excluded SKUs

The 3 SKU difference between 147 comment-batch SKU and 144 M05C SKU is explained as follows:

| SKU | Diagnosis | Evidence |
| --- | --- | --- |
| `AC00036291` | `no_active_comment_rows_after_cleaning` | 1 clean comment row exists but `record_status='skipped'`; 0 active comments, 0 sentences, 0 current comment evidence |
| `AC00039044` | `all_active_comments_low_value_no_sentence_or_m02` | 1 active comment row, all low-value, reason `默认或空评价`; 0 sentences, 0 current comment evidence |
| `AC00039082` | `all_active_comments_low_value_no_sentence_or_m02` | 5 active comment rows, all low-value, reason `默认或空评价`; 0 sentences, 0 current comment evidence |

## Decision

No M05C补跑 is needed for G07. There are no valid M02 current comment-evidence SKUs missing M05C.

For AC downstream semantic outputs, the comment-ready population is 144 SKU. The 3 excluded SKUs should not receive M09C/M10C/M11C/M11D/M12C semantic outputs unless upstream clean/M02 evidence is intentionally regenerated in a separate M00-M02 scope, which is outside this goal.

## Acceptance

- AC M05C current coverage: 144 SKU.
- Gap reason: explicit for all 3 excluded SKU.
- Downstream population: use AC comment-ready population of 144 SKU for comment-grounded semantic/value layers.

## Next

Continue with G08: AC M09C/M10C/M11C profile completeness repair.
