# AGENTS.md — CatForge Repository Instructions

## Product identity

This repository implements **CatForge / 品铸**, the internal Category Factory for producing category semantic assets and market-analysis rules from SKU-level observable market data.

CatForge is not the customer-facing runtime system. It generates category asset packs that can be used by a separate runtime deliverable.

## Core principles

1. Evidence first: every analytical output must reference source evidence when possible.
2. Human-in-the-loop: candidate generation, review, evaluation, and release must remain separate stages.
3. Missing is unknown: never treat missing values, empty strings, `-`, or null as false.
4. Runtime boundary: do not expose factory-only scripts, prompt templates, Gold Set builders, cross-category migration tools, or internal generation methods through runtime export APIs.
5. Typed contracts: all input rows, asset definitions, and output records must be represented by typed schemas.
6. Deterministic tests: tests must pass without external LLM calls. Use mock or rule-based implementations for LLM-dependent steps.
7. Category isolation: every asset and output must include `category_code`, `project_id`, `version`, and audit metadata where applicable.
8. Traceability: preserve `evidence_id`, `source_file_id`, `raw_row_id`, `confidence`, and `review_status` fields.

## Recommended stack

- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy 2.x, Alembic
- Database: PostgreSQL; use SQLite only for unit tests if necessary
- Queue: Celery + Redis, or implement a queue abstraction with a local synchronous fallback
- Data processing: pandas, openpyxl, pyarrow
- Frontend: React, TypeScript, Vite, Ant Design
- Testing: pytest, vitest, Playwright only when necessary
- Packaging: Docker Compose for local development

## Do

- Implement small, testable services.
- Write migrations for every table.
- Create API schemas before business logic.
- Add tests for valid input, invalid input, edge cases, and export boundary enforcement.
- Use seed assets for TV only in MVP.
- Keep algorithm modules pluggable and configurable through YAML/JSON.
- Separate candidate tables from approved asset definition tables.

## Do not

- Do not implement uncontrolled “create any new category” runtime export.
- Do not place prompt templates or benchmark gold sets inside runtime export packages.
- Do not make external API calls in tests.
- Do not hard-code absolute local paths.
- Do not hide low-confidence results; send them to review queue.
- Do not generate final business conclusions without evidence references.
- Do not mix the internal factory repository with the customer-facing runtime repository.

## Naming conventions

- Use `category_code` values like `TV`, `REFRIGERATOR`, `WASHER`, `KITCHEN_APPLIANCE`.
- Use stable asset codes: `param_code`, `claim_code`, `task_code`, `battlefield_code`, `topic_code`.
- Use snake_case for database columns and Python symbols.
- Use kebab-case for frontend routes.

## Minimal acceptance for every PR

- Unit tests pass.
- New API endpoints have schema tests.
- New database tables have migrations.
- New analytical outputs include evidence and confidence fields.
- Export logic is covered by a boundary test.
