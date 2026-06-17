Build the first runnable MVP vertical slice of `catforge`, an internal Category Factory product.

Read and follow: `AGENTS.md`, `docs/00_context.md`, `docs/01_engineering_tasks.md`, `docs/02_data_contract.md`, `docs/03_asset_schema.md`, `docs/04_acceptance_tests.md`, `docs/05_export_boundary.md`, `docs/06_technical_architecture.md`.

Implement a monorepo with FastAPI backend, React/Vite frontend, PostgreSQL, Redis/Celery or local task fallback, SQLAlchemy/Alembic, tests, Docker Compose.

MVP scope: TV category only. Support project creation, file upload/import, data-quality profiling, TV parameter normalization, claim mapping, comment topic mapping, task/battlefield scoring, market metrics, review queue, and runtime asset export. Use deterministic rule-based logic first. Do not require external LLM calls.

Critical boundary: export only approved runtime asset files. Do not export prompt templates, generation scripts, Gold Set builders, cross-category migration templates, or factory-only logic.

Acceptance: sample files import; data quality report works; parameter/claim/comment mappings work; task and battlefield scores include evidence references; review queue is generated; runtime export passes whitelist test; backend tests pass; README explains local run.
