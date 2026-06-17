"""Pipeline status query service for Core3 API module."""

from __future__ import annotations

from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_schemas import ApiQueryError, Core3V2PipelineRunListResponse


class PipelineStatusQueryService:
    def __init__(self, repository: Core3RealDataApiRepository) -> None:
        self.repository = repository

    def list_runs(self, *, limit: int = 20, offset: int = 0) -> Core3V2PipelineRunListResponse:
        rows = self.repository.list_pipeline_runs(limit=limit, offset=offset)
        total = self.repository.count_pipeline_runs()
        return Core3V2PipelineRunListResponse(
            items=self.repository.rows_as_dicts(rows),
            total=total,
            limit=limit,
            offset=offset,
            summary_cn=f"当前项目共有 {total} 次生产线运行记录。",
        )

    def latest_run_id(self) -> str:
        latest = self.repository.latest_run()
        if latest is None:
            raise ApiQueryError(
                status_code=404,
                error_code="pipeline_run_not_found",
                message_cn="当前项目尚未生成生产线运行记录。",
            )
        return latest.run_id
