# 04 API Contracts

Add APIs if not already present.

## Asset Library APIs

GET /api/projects/{project_id}/assets/parameters
GET /api/projects/{project_id}/assets/claims
GET /api/projects/{project_id}/assets/comment-topics
GET /api/projects/{project_id}/assets/tasks
GET /api/projects/{project_id}/assets/target-groups
GET /api/projects/{project_id}/assets/battlefields
GET /api/projects/{project_id}/assets/mappings

PATCH /api/projects/{project_id}/assets/{asset_type}/{asset_id}/review
PATCH /api/projects/{project_id}/assets/{asset_type}/{asset_id}
POST /api/projects/{project_id}/assets/{asset_type}/merge
POST /api/projects/{project_id}/assets/{asset_type}/split

## SKU Results APIs

GET /api/projects/{project_id}/sku-results
GET /api/projects/{project_id}/sku-results/{sku_code}
GET /api/projects/{project_id}/sku-results/{sku_code}/evidence
GET /api/projects/{project_id}/sku-results/{sku_code}/competitors
GET /api/projects/{project_id}/sku-results/{sku_code}/report-preview

## Calibration Report APIs

GET /api/projects/{project_id}/calibration/summary
GET /api/projects/{project_id}/calibration/claims
GET /api/projects/{project_id}/calibration/battlefields
GET /api/projects/{project_id}/calibration/review-summary

## Export APIs

GET /api/projects/{project_id}/runtime-export/preview
POST /api/projects/{project_id}/runtime-export
GET /api/projects/{project_id}/runtime-export/{export_id}/manifest
