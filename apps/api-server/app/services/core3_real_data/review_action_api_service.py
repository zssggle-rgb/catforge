"""Business API aliases for review and release actions."""

from __future__ import annotations

from app.models import entities
from app.services.core3_real_data.api_response_schemas import (
    ApiQueryError,
    Core3V2ReleaseActionRequest,
    Core3V2ReviewDecisionAliasRequest,
)
from app.services.core3_real_data.pipeline_repositories import PipelineRepository


class ReviewActionApiService:
    def __init__(self, repository: PipelineRepository) -> None:
        self.repository = repository

    def decide_review(self, review_id: str, payload: Core3V2ReviewDecisionAliasRequest) -> entities.Core3V2ReviewDecision:
        review = self.repository.db.get(entities.Core3V2ReviewQueue, review_id)
        if review is None or review.project_id != self.repository.project_id:
            raise ApiQueryError(
                status_code=404,
                error_code="review_item_not_found",
                message_cn="没有找到需要处理的复核项。",
            )
        return self.repository.insert_review_decision(
            review_id,
            {
                "decision_type": payload.decision_type,
                "decision_reason_cn": payload.decision_reason_cn,
                "impact_scope_json": payload.impact_scope,
                "need_recompute": payload.need_recompute,
                "recompute_mode": payload.recompute_mode,
                "decided_by": payload.decided_by,
            },
        )

    def release_gate(self, gate_id: str, payload: Core3V2ReleaseActionRequest) -> entities.Core3V2ReleaseGate:
        gate = self.repository.db.get(entities.Core3V2ReleaseGate, gate_id)
        if gate is None or gate.project_id != self.repository.project_id:
            raise ApiQueryError(
                status_code=404,
                error_code="release_gate_not_found",
                message_cn="没有找到发布门禁。",
            )
        return self.repository.mark_release_gate_released(gate_id, released_by=payload.released_by)
