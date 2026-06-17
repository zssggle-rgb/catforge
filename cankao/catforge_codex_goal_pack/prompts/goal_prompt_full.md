# Codex Goal Mode Prompt — CatForge MVP Vertical Slice

You are working in a new GitHub repository named `catforge`.

Read the following files first and follow them strictly:

- `AGENTS.md`
- `docs/00_context.md`
- `docs/01_engineering_tasks.md`
- `docs/02_data_contract.md`
- `docs/03_asset_schema.md`
- `docs/04_acceptance_tests.md`
- `docs/05_export_boundary.md`
- `docs/06_technical_architecture.md`
- Upstream PRD and detailed design documents if present under `docs/source/`

## Goal

Create the first runnable MVP vertical slice of CatForge / 品铸, the internal category asset production tool.

The MVP must support TV category data import, data-quality profiling, seed-rule based parameter normalization, claim mapping, comment topic classification, basic user-task and battlefield scoring, basic market metrics, review queue generation, and runtime asset package export with strict boundary protection.

This is an internal factory product. Do not build the customer runtime repository. Do not export factory-only capabilities.

## Tech stack

Use:

- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic
- Database: PostgreSQL
- Queue: Celery + Redis, with a synchronous local fallback if Celery setup is too much for the first pass
- Data processing: pandas, openpyxl
- Frontend: React + TypeScript + Vite + Ant Design
- Tests: pytest for backend, vitest for frontend
- Local dev: Docker Compose

## Required repository output

Create this structure or an equivalent clean monorepo structure:

```text
catforge/
  README.md
  AGENTS.md
  docker-compose.yml
  apps/
    api-server/
    factory-web/
  docs/
  examples/
  contracts/
  infra/
  scripts/
```

## Backend requirements

Implement:

1. Health endpoint
   - `GET /healthz`

2. Project APIs
   - `POST /projects`
   - `GET /projects`
   - `GET /projects/{project_id}`

3. File and import APIs
   - `POST /projects/{project_id}/files`
   - `POST /projects/{project_id}/imports`
   - `GET /projects/{project_id}/data-quality`

4. Pipeline APIs
   - `POST /projects/{project_id}/profile`
   - `POST /projects/{project_id}/pipeline/{step}`
   - supported steps: `generate_params`, `generate_claims`, `generate_comment_topics`, `score_tasks_battlefields`, `calculate_market_metrics`, `build_review_queue`

5. Asset and review APIs
   - `GET /projects/{project_id}/assets/{asset_type}`
   - `GET /projects/{project_id}/review-queue`
   - `POST /review-queue/{review_id}/decision`

6. Export API
   - `POST /projects/{project_id}/export-runtime`

## Database requirements

Use SQLAlchemy + Alembic. Create tables for at least:

- `category_project`
- `source_file`
- `import_batch`
- `raw_sku_master`
- `raw_sku_param`
- `raw_sku_claim`
- `raw_sku_comment`
- `raw_market_fact`
- `data_quality_issue`
- `evidence_item`
- `std_param_def`
- `std_claim_def`
- `comment_topic_def`
- `user_task_def`
- `target_group_def`
- `battlefield_def`
- `sku_param_normalized`
- `sku_claim_result`
- `sku_comment_topic_result`
- `sku_task_score`
- `sku_battlefield_score`
- `claim_value_layer_result`
- `review_queue`
- `asset_package`

Keep schemas minimal but include IDs, `project_id`, `category_code`, `version`, status, confidence, evidence references, and timestamps where appropriate.

## Seed rule requirements

Add TV seed rules in YAML or JSON for:

- Standard params:
  - `screen_size_inch`
  - `native_refresh_rate_hz`
  - `system_refresh_rate_hz`
  - `mini_led_flag`
  - `peak_brightness_nits`
  - `dimming_zones`
  - `hdmi_2_1_ports`
  - `ram_gb`
  - `storage_gb`
  - `eye_dimming_freq_hz`

- Standard claims:
  - `CLAIM_LARGE_SCREEN_IMMERSION`
  - `CLAIM_MINI_LED_BACKLIGHT`
  - `CLAIM_HIGH_BRIGHTNESS_HDR`
  - `CLAIM_FINE_LOCAL_DIMMING`
  - `CLAIM_HIGH_REFRESH_RATE`
  - `CLAIM_HDMI_2_1_GAMING`
  - `CLAIM_EYE_CARE_COMFORT`
  - `CLAIM_SMART_VOICE_EASE`
  - `CLAIM_IMMERSIVE_AUDIO`

- Comment topics:
  - `TOPIC_PICTURE_QUALITY`
  - `TOPIC_SPORTS_WATCHING`
  - `TOPIC_GAMING_SMOOTHNESS`
  - `TOPIC_EASE_OF_USE`
  - `TOPIC_SENIOR_FRIENDLY`
  - `TOPIC_INTERFACE_CONNECTIVITY`
  - `TOPIC_AUDIO_QUALITY`
  - `TOPIC_INSTALLATION_SERVICE`

- User tasks:
  - `TASK_LIVING_ROOM_CINEMA`
  - `TASK_PREMIUM_PICTURE_AV`
  - `TASK_GAMING_ENTERTAINMENT`
  - `TASK_SPORTS_WATCHING`
  - `TASK_LARGE_SCREEN_REPLACEMENT`
  - `TASK_SENIOR_EASY_USE`
  - `TASK_CHILD_EYE_CARE`

- Battlefields:
  - `BF_FAMILY_VIEWING_UPGRADE`
  - `BF_PREMIUM_PICTURE`
  - `BF_GAMING_SPORTS`
  - `BF_LARGE_SCREEN_REPLACEMENT`
  - `BF_FAMILY_EYE_CARE`
  - `BF_SENIOR_EASE_OF_USE`

## Algorithm MVP requirements

Implement deterministic, testable rule-based versions first. Do not require external LLM calls.

1. Parameter normalization:
   - Parse inch, Hz, nits, zones, GB, HDMI port count, boolean values.
   - Treat missing or `-` as `unknown`, not false.
   - Create evidence records.

2. Claim mapping:
   - Segment claim text.
   - Extract nits, zones, Hz, HDMI 2.1, Mini LED, RAM/ROM.
   - Activate standard claims with confidence and evidence.

3. Comment topics:
   - Split comments into sentences/phrases.
   - Map keyword phrases to comment topics.
   - Installation/service topics must not activate product claims.

4. User task and battlefield scoring:
   - Use activated claims, normalized params, comment topics, and market signals.
   - Output score, relation level, confidence, evidence references.

5. Market metrics:
   - Compute claim coverage rate.
   - Compute PSI = median price with claim / median price without claim - 1, with minimum comparable sample guard.
   - Compute SSI = sales share with claim / sales share without claim - 1, with guard.
   - Compute CPI from positive vs negative comment topic counts if available.

6. Review queue:
   - Create review items for low-confidence mappings, conflicts, unknown high-frequency fields, insufficient samples, and high-value SKU outputs.

7. Runtime export:
   - Export only whitelist files in `docs/05_export_boundary.md`.
   - Add an automated test that fails if forbidden factory files are exported.

## Frontend MVP requirements

Implement a simple but usable admin UI:

- Project list and create project
- Project dashboard
- File upload/import page
- Data-quality report page
- Asset list page with tabs for parameters, claims, topics, tasks, battlefields
- Review queue page with approve/reject/edit action placeholders
- Runtime export page

The UI can be basic; prioritize working API integration and clear state.

## Example data and tests

Use files under `examples/`. If sample files are missing, create minimal sample files in `examples/` that cover:

- Hisense 85E7Q-like TV with Mini LED, high brightness, dimming zones, high refresh, HDMI 2.1, senior-friendly comment.
- At least 4 competitor TVs with different claims, prices, sales, and channels.

Implement tests from `docs/04_acceptance_tests.md` as much as possible in the first pass.

## Non-goals

Do not implement:

- Real external LLM integration.
- Cross-category migration automation.
- Prompt lab.
- Gold Set builder beyond a minimal schema placeholder.
- Customer runtime repository.
- Authentication beyond a simple placeholder.
- Advanced embedding clustering; create interfaces/stubs only.

## Acceptance criteria

The generated repository is acceptable if:

1. `docker compose up` starts backend, frontend, postgres, and redis or documents a working local fallback.
2. `/healthz` returns OK.
3. Sample files can be imported.
4. Data-quality report is returned.
5. TV parameter normalization works for sample data.
6. TV claim mapping works for sample data.
7. TV comment topic mapping works for sample data.
8. User task and battlefield scores are generated with evidence references.
9. Review queue is populated for low-confidence or conflict cases.
10. Runtime export produces only whitelist files.
11. Backend tests pass.
12. README explains how to run and test the project.

## Implementation style

Prefer clean, minimal, working code over over-engineering.
Keep modules small and typed.
Add TODOs where future LLM/embedding functionality will be implemented.
