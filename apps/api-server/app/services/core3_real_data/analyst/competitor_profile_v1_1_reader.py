"""Formal/current and explicit-preview reader for competitor profile V1.1."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AgentCompetitorProfileReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_persistence_schemas import (
    CompetitorProfileV11ReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11Repository,
    ReadMode,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    CompetitorProfileV11BaseModel,
    QuestionCode,
)


class CompetitorProfileV11ReadRequest(CompetitorProfileV11BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str | None = Field(default=None, min_length=1)
    target_sku_code: str = Field(min_length=1)
    access_mode: Literal["formal", "preview"] = "formal"
    read_mode: ReadMode = "full"
    question_code: QuestionCode | None = None
    competitor_profile_version_id: str | None = None
    allow_draft_preview: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "CompetitorProfileV11ReadRequest":
        if self.access_mode == "formal" and (
            self.competitor_profile_version_id is not None
            or self.allow_draft_preview
        ):
            raise ValueError("formal reads cannot select or enable a draft version")
        if self.access_mode == "preview" and (
            not self.release_scope_key
            or not self.competitor_profile_version_id
            or not self.allow_draft_preview
        ):
            raise ValueError(
                "preview reads require an explicit scope, version, and opt-in"
            )
        if self.read_mode == "question_specific" and self.question_code is None:
            raise ValueError("question_specific reads require question_code")
        if self.read_mode != "question_specific" and self.question_code is not None:
            raise ValueError("question_code is only valid for question_specific reads")
        return self


class CompetitorProfileV11Reader:
    """Read saved V1.1 data only; never invoke analysis or legacy materializers."""

    def __init__(self, repository: CompetitorProfileV11Repository) -> None:
        self.repository = repository

    def read(
        self,
        request: CompetitorProfileV11ReadRequest,
    ) -> CompetitorProfileV11ReadResult | AgentCompetitorProfileReadResult:
        if request.project_id != self.repository.project_id:
            raise ValueError("reader project scope does not match repository")
        if request.category_code != self.repository.category_code.value:
            raise ValueError("reader category scope does not match repository")
        if isinstance(self.repository, CompetitorProfileAgentSnapshotRepository):
            if request.read_mode in {"full", "compact"}:
                agent_result = self.repository.read_agent_snapshot(
                    target_sku_code=request.target_sku_code,
                    read_mode=request.read_mode,
                    access_mode=request.access_mode,
                    competitor_profile_version_id=(
                        request.competitor_profile_version_id
                    ),
                    release_scope_key=request.release_scope_key,
                )
                if agent_result.status == "available":
                    return agent_result
        if request.access_mode == "formal":
            if request.release_scope_key is None:
                result = self.repository.get_serving_current_published_profile(
                    target_sku_code=request.target_sku_code,
                    read_mode=request.read_mode,
                    question_code=request.question_code,
                )
            else:
                result = self.repository.get_current_published_profile(
                    release_scope_key=request.release_scope_key,
                    target_sku_code=request.target_sku_code,
                    read_mode=request.read_mode,
                    question_code=request.question_code,
                )
        else:
            result = self.repository.get_profile(
                competitor_profile_version_id=str(
                    request.competitor_profile_version_id
                ),
                target_sku_code=request.target_sku_code,
                read_mode=request.read_mode,
                question_code=request.question_code,
                preview=True,
            )
            if result is not None:
                payload = result.full or result.compact or result.question
                assert payload is not None
                if payload.profile_version.release_scope_key != request.release_scope_key:
                    raise ValueError(
                        "preview version does not belong to the requested release scope"
                    )
        if result is not None:
            return result
        return CompetitorProfileV11ReadResult(
            status="profile_unavailable",
            read_mode=request.read_mode,
            preview=request.access_mode == "preview",
        )


__all__ = [
    "CompetitorProfileV11ReadRequest",
    "CompetitorProfileV11Reader",
]
