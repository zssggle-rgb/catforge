# G11 TV/AC Agent Consumption Acceptance

Date: 2026-07-08

## Status

Completed.

G11 verified that the current analyst/agent consumption entry points can read the aligned TV and AC semantic-market graph and claim-value data.

## Incident During Acceptance

During G11, the 205 API/Postgres containers were found recreated at 2026-07-08 17:35-17:36 Asia/Shanghai with a generated `/opt/catforge/docker-compose.yml` that pointed API to a local empty Postgres database:

- Wrong runtime DB: `postgres:5432/catforge`
- Correct runtime DB from `/opt/catforge/.env`: external `catforge_dev`

Impact:

- The temporary local Postgres tables were empty.
- The external `catforge_dev` data remained available.

Recovery:

```bash
cd /opt/catforge && docker compose --env-file .env -f docker-compose.cloud.yml up -d api web
```

Post-recovery checks:

- API env points to `host.docker.internal:5432/catforge_dev`.
- `host.docker.internal` resolves inside the API container.
- Core data tables are present again.
- AC M12C current coverage is 140 SKU / 6303 rows.

The rebuilt API image had older source files, so the running container was hot-updated again with the committed G08-G10 runtime files:

- `catforge_pipeline.py`
- `m05c_comment_fact_profile_service.py`
- `m11c_value_battlefield_service.py`
- `semantic_market_graph_service.py`
- `m12c_claim_value_quantification_service.py`

`/opt/catforge` source could not be updated by `deploy` because the code subdirectories are owned by uid 501 and `deploy` has no sudo. The durable fix is to sync/deploy the local commits through the normal privileged deployment path.

## Runtime Code Check

After hot update:

- AC semantic market rule is enabled: `m11d_semantic_market_allocation_v0.1`
- AC M12C rule is enabled: `m12c_claim_value_quantification_v0.1`
- M11D has AC input rules.
- M12C has AC input rules.
- M12C AC claim rule: `m04c_ac_claim_fact_profile_v0.1`
- AC airflow claim fallback includes `airflow_volume_m3h`, `horsepower_hp`, `installation_type`.

## Acceptance Commands

TV competitor question:

```bash
python -m app.cli.catforge_analyst ask \
  "TV00026228 的竞品有哪些" \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --sku-code TV00026228 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- routed command: `competitor-set`
- `category_code=TV`
- `product_category=TV`
- batch: `m00_20260619084551_857df63b`
- target source: `M07`
- answer outline: generated 3 competitor candidates by purchase pool, semantic overlap, value-anchor substitution pressure, and market validation.

TV premium claim question:

```bash
python -m app.cli.catforge_analyst ask \
  "TV00026228 哪些卖点是溢价卖点" \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --sku-code TV00026228 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- routed command: `premium-claim-drivers`
- `category_code=TV`
- `product_category=TV`
- batch: `m00_20260619084551_857df63b`
- answer outline references M12C claim payment value, fact claims, comment support, battlefields, and price pressure signals.

AC target-group question:

```bash
python -m app.cli.catforge_analyst ask \
  "AC00038662 的目标客群是什么" \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --sku-code AC00038662 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- routed command: `sku-business-brief`
- `category_code=AC`
- `product_category=AC`
- batch: `m00_20260624000202_1150a669`
- target source: `M07`
- limitation reported: missing `semantic_dimension_positions`, not a silent false conclusion.

AC claim-sales question:

```bash
python -m app.cli.catforge_analyst ask \
  "AC00038662 哪些卖点支撑销量" \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --sku-code AC00038662 \
  --limit 3 \
  --format json
```

Result:

- `status=ok`
- routed command: `claim-contribution`
- `category_code=AC`
- `product_category=AC`
- batch: `m00_20260624000202_1150a669`
- answer outline: returned claim business value analysis for `AC00038662`.

TV battlefield-space:

```bash
python -m app.cli.catforge_analyst battlefield-space \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code TV \
  --batch-id latest \
  --product-category tv \
  --limit 2 \
  --format json
```

Result:

- `status=ok`
- `category_code=TV`
- `product_category=TV`
- `summary_count=13`
- first battlefield: `BF_LARGE_SCREEN_VALUE_UPGRADE` / `大屏换新性价比战场`

AC battlefield-space:

```bash
python -m app.cli.catforge_analyst battlefield-space \
  --project-id d8d2245b-358b-4a64-95cc-9d7f2341bd26 \
  --category-code AC \
  --batch-id latest \
  --product-category ac \
  --limit 2 \
  --format json
```

Result:

- `status=ok`
- `category_code=AC`
- `product_category=AC`
- `summary_count=11`
- first battlefield: `BF_WALL_1_5_MAINSTREAM_VALUE` / `1.5匹挂机主流性价比战场`

## Acceptance

- No command read raw tables for business conclusions.
- TV commands stayed in `category_code=TV` / `product_category=TV`.
- AC commands stayed in `category_code=AC` / `product_category=AC`.
- Business-answer targets cite derived sources such as M07/M12C, not raw tables.
- Missing data was surfaced as a limitation instead of being treated as false.
- TV and AC battlefield-space both read current semantic-market graph outputs.
- AC claim contribution and SKU claim value data are readable by agent entry points.

## Follow-Up Risk

The running 205 container is correct now, and local changes are committed. However, `/opt/catforge` source on 205 is still stale because `deploy` cannot write uid-501-owned code paths. A later container rebuild from that source will lose the runtime hot updates unless the privileged deployment path syncs these commits first.
