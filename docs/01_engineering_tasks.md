# 01. Engineering Tasks and Milestones

## Milestone 0 — Repository scaffold

Goal: create the runnable monorepo skeleton.

Tasks:

1. Create backend app with FastAPI.
2. Create frontend app with React + TypeScript + Vite + Ant Design.
3. Add PostgreSQL, Redis, backend, frontend to Docker Compose.
4. Add SQLAlchemy and Alembic baseline.
5. Add pytest and vitest.
6. Add `/healthz` endpoint.
7. Add README local startup instructions.
8. Add CI workflow to run lint and tests.

Acceptance:

- `docker compose up` starts backend, frontend, postgres, redis.
- Backend `/healthz` returns `{ "status": "ok" }`.
- Backend tests pass.
- Frontend starts and shows CatForge navigation.

## Milestone 1 — Data contract and import pipeline

Goal: accept source data for one category project and generate data-quality reports.

Tasks:

1. Implement project model and APIs.
2. Implement source file upload metadata.
3. Implement CSV/XLSX parser.
4. Import SKU master, parameter, claim, comment, and market fact rows.
5. Generate data-quality issues.
6. Return profiling statistics.

Acceptance:

- Import sample files from `examples/`.
- Store raw rows with `project_id`, `category_code`, `source_file_id`, `raw_row_id`.
- Quality report includes row count, missing required fields, duplicate SKU count, invalid numeric fields.
- Tests cover valid and invalid files.

## Milestone 2 — Parameter factory MVP

Goal: produce candidate standard parameter definitions from raw SKU parameter rows.

Tasks:

1. Field discovery: raw parameter names, counts, coverage.
2. Alias grouping: rule-based initial grouping for TV seed aliases.
3. Value normalization: unit parsing for inch, Hz, nits, GB, ports, boolean.
4. Leveling: simple TV thresholds from seed config.
5. Conflict detection: parameter table vs claim-derived values.
6. Candidate parameter definitions and review queue.

Acceptance:

- From sample parameters, produce `screen_size_inch`, `native_refresh_rate_hz`, `mini_led_flag`, `ram_gb`, `storage_gb`.
- Missing values are `unknown`, not false.
- Conflicting refresh-rate evidence enters review queue.

## Milestone 3 — Claim and comment factory MVP

Goal: map raw marketing claims and comments to standard claim and topic candidates.

Tasks:

1. Marketing claim segmentation.
2. Numeric/entity extraction: nits, Hz, zones, HDMI 2.1, DCI-P3, DeltaE, Mini LED.
3. Standard claim mapping from seed rules.
4. Comment sentence splitting.
5. Comment topic classification using keyword rules.
6. Product-experience vs service-experience separation.
7. Low-confidence mapping review queue.

Acceptance:

- `Mini LED`, `5200nits`, `3500 zones`, `HDMI 2.1`, `high refresh` are mapped correctly.
- Comment “老人也能上手” maps to ease-of-use / senior-friendly topic.
- Installation/service comments do not activate product claims.

## Milestone 4 — Task, battlefield, market metrics, and value layer MVP

Goal: calculate user task scores, battlefield scores, and claim value layers for TV.

Tasks:

1. Claim activation score per SKU.
2. User task score using claim, parameter, comment, and market evidence.
3. Battlefield score using task and claim combinations.
4. Coverage rate per standard claim.
5. PSI price support index.
6. SSI sales support index.
7. CPI comment perception index.
8. Claim value layer classification.

Acceptance:

- A TV with Mini LED, high brightness, zones, and positive picture comments enters premium-picture battlefield.
- A high-refresh TV enters gaming/sports battlefield with evidence.
- Claim value layer does not output premium/price support if comparable sample size is insufficient.

## Milestone 5 — Competitor rule MVP

Goal: identify direct, substitute, benchmark, and potential competitors by battlefield.

Tasks:

1. Candidate pool filtering by category, channel, time window, size band, price band.
2. Similarity scoring: battlefield overlap, price, claims, parameters, channel, sales.
3. Competitor type classification.
4. Evidence card generation.

Acceptance:

- Direct competitors share battlefield, price band, channel, and key claims.
- Benchmark competitors have stronger specs, higher price, stronger sales, or stronger brand proxy.
- Potential competitors can be flagged by recent price decrease or promotion metadata when available.

## Milestone 6 — Review, evaluation, and runtime export

Goal: support human approval, evaluation, and runtime asset package export.

Tasks:

1. Review queue UI and APIs.
2. Approve/reject/edit candidate assets.
3. Gold Set case model and evaluation runner.
4. Asset versioning and release workflow.
5. Runtime export whitelist.
6. Boundary tests to ensure factory-only assets are not exported.

Acceptance:

- Approved assets can be versioned and released.
- Runtime export contains only whitelist files.
- Runtime export does not contain prompts, generation scripts, Gold Set builders, or cross-category migration templates.
