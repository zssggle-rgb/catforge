# Goal 1 API Contracts

Implement or adapt existing endpoints as needed.

## Rule APIs
- `POST /api/rule-sets/validate`
- `POST /api/rule-sets`
- `GET /api/rule-sets/{id}`
- `POST /api/rule-sets/{id}/activate`

## Analysis APIs
- `POST /api/projects/{project_id}/run-analysis`
- `GET /api/projects/{project_id}/analysis-runs/{run_id}`
- `GET /api/projects/{project_id}/sku/{sku_code}/analysis`
- `GET /api/projects/{project_id}/sku/{sku_code}/competitors`
- `GET /api/projects/{project_id}/evidence/{evidence_id}`

## Evaluation APIs
- `POST /api/projects/{project_id}/gold-labels/import`
- `POST /api/projects/{project_id}/evaluation/run`
- `GET /api/projects/{project_id}/evaluation/{evaluation_id}`
- `POST /api/projects/{project_id}/calibration/run`

Return structured validation errors. Do not return generic 500s for user-fixable rule/data contract errors.
