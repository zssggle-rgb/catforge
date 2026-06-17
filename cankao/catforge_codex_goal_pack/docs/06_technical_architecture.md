# 06. Technical Architecture

## MVP stack

- Backend: Python 3.11+, FastAPI, Pydantic, SQLAlchemy, Alembic
- Database: PostgreSQL
- Queue: Celery + Redis; local synchronous fallback accepted for MVP
- Data processing: pandas, openpyxl, pyarrow
- Frontend: React + TypeScript + Vite + Ant Design
- Testing: pytest, vitest
- Local dev: Docker Compose

## Backend modules

```text
apps/api-server/
  app/main.py
  app/api/
    health.py
    projects.py
    files.py
    imports.py
    profiling.py
    assets.py
    review.py
    evaluation.py
    export.py
  app/core/
    config.py
    database.py
    security.py
  app/models/
  app/schemas/
  app/services/
    ingestion_service.py
    profiling_service.py
    param_factory.py
    claim_factory.py
    comment_topic_factory.py
    task_battlefield_factory.py
    market_metrics_engine.py
    competitor_engine.py
    review_service.py
    evaluation_service.py
    asset_exporter.py
  app/rules/
    tv_seed_params.yaml
    tv_seed_claims.yaml
    tv_seed_tasks.yaml
    tv_seed_battlefields.yaml
  tests/
```

## Frontend modules

```text
apps/factory-web/
  src/
    pages/
      ProjectsPage.tsx
      ProjectDashboard.tsx
      DataImportPage.tsx
      DataQualityPage.tsx
      ParameterFactoryPage.tsx
      ClaimFactoryPage.tsx
      CommentTopicPage.tsx
      TaskBattlefieldPage.tsx
      ReviewQueuePage.tsx
      EvaluationPage.tsx
      RuntimeExportPage.tsx
    api/
    components/
    routes/
    types/
```

## API endpoints MVP

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Health check |
| POST | `/projects` | Create category project |
| GET | `/projects` | List projects |
| GET | `/projects/{project_id}` | Get project |
| POST | `/projects/{project_id}/files` | Upload file |
| POST | `/projects/{project_id}/imports` | Import uploaded source file |
| GET | `/projects/{project_id}/data-quality` | Data-quality report |
| POST | `/projects/{project_id}/profile` | Run data profiling |
| POST | `/projects/{project_id}/pipeline/{step}` | Run one pipeline step |
| GET | `/projects/{project_id}/assets/{asset_type}` | List candidate/approved assets |
| GET | `/projects/{project_id}/review-queue` | List review items |
| POST | `/review-queue/{review_id}/decision` | Approve/reject/edit review item |
| POST | `/projects/{project_id}/evaluate` | Run evaluation |
| POST | `/projects/{project_id}/release` | Release asset version |
| POST | `/projects/{project_id}/export-runtime` | Export runtime asset package |

## Pipeline steps

| Step | Service |
|---|---|
| ingest | ingestion_service |
| profile | profiling_service |
| generate_params | param_factory |
| generate_claims | claim_factory |
| generate_comment_topics | comment_topic_factory |
| score_tasks_battlefields | task_battlefield_factory |
| calculate_market_metrics | market_metrics_engine |
| generate_competitor_rules | competitor_engine |
| build_review_queue | review_service |
| evaluate | evaluation_service |
| export_runtime | asset_exporter |

## Evidence model

Every derived output should reference `evidence_item` records:

- `evidence_id`
- `project_id`
- `category_code`
- `sku_code`
- `source_type`: param / claim / comment / market_fact / derived
- `source_file_id`
- `raw_row_id`
- `field_name`
- `raw_value`
- `normalized_value`
- `confidence`
