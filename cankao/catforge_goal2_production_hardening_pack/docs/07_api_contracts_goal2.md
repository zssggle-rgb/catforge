# Goal 2 API Contracts

## Job APIs
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/cancel`
- `POST /api/jobs/{job_id}/retry`
- `GET /api/jobs/{job_id}/diagnostics`

## Version APIs
- `POST /api/assets/{asset_id}/submit-review`
- `POST /api/assets/{asset_id}/approve`
- `POST /api/assets/{asset_id}/release`
- `GET /api/assets/{asset_id}/versions`
- `GET /api/assets/diff?from_version=&to_version=`
- `POST /api/assets/{asset_id}/rollback`

## Export APIs
- `POST /api/projects/{project_id}/runtime-export`
- `GET /api/exports/{export_id}`
- `GET /api/exports/{export_id}/download`

## Audit APIs
- `GET /api/audit?project_id=&object_type=&object_id=&action=`
