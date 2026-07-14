"""Typed formal/preview reader and presentation contracts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


class CompetitorProfileReadRequest(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    mode: Literal["formal", "preview"] = "formal"
    competitor_profile_version_id: str | None = None
    allow_draft_preview: bool = False

    @model_validator(mode="after")
    def validate_mode(self) -> "CompetitorProfileReadRequest":
        if self.mode == "formal" and (
            self.competitor_profile_version_id is not None
            or self.allow_draft_preview
        ):
            raise ValueError("formal reads cannot specify or enable a draft preview")
        if self.mode == "preview" and (
            not self.competitor_profile_version_id or not self.allow_draft_preview
        ):
            raise ValueError("preview reads require an explicit version and opt-in")
        return self


class CompetitorProfileBusinessDTO(CompetitorProfileBaseModel):
    目标产品: str = Field(min_length=1)
    分析结论: str = Field(min_length=1)
    结论状态: str = Field(min_length=1)
    重点竞品: list[dict[str, Any]] = Field(default_factory=list)
    本品优势: list[dict[str, Any]] = Field(default_factory=list)
    可替代价值: list[dict[str, Any]] = Field(default_factory=list)
    价格销量压力: list[dict[str, Any]] = Field(default_factory=list)
    同品牌产品线: list[dict[str, Any]] = Field(default_factory=list)
    配置决策: list[dict[str, Any]] = Field(default_factory=list)
    候选概况: dict[str, Any] = Field(default_factory=dict)
    竞品对比: list[dict[str, Any]] = Field(default_factory=list)
    问答范围: list[dict[str, Any]] = Field(default_factory=list)
    数据不足说明: dict[str, Any] = Field(default_factory=dict)


class CompetitorProfileEvidenceDTO(CompetitorProfileBaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    release_status: str = Field(min_length=1)
    preview: bool
    target_sku_code: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    candidate_evidence: list[dict[str, Any]] = Field(default_factory=list)
    source_lineage: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CompetitorProfileReaderResult(CompetitorProfileBaseModel):
    status: Literal["available", "profile_unavailable"]
    competitor_profile_version_id: str | None = None
    preview: bool = False
    business: CompetitorProfileBusinessDTO | None = None
    evidence: CompetitorProfileEvidenceDTO | None = None
    message_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_result(self) -> "CompetitorProfileReaderResult":
        if self.status == "available":
            if not self.competitor_profile_version_id or not self.business or not self.evidence:
                raise ValueError("available reads require one locked version and both DTOs")
            if self.competitor_profile_version_id != self.evidence.competitor_profile_version_id:
                raise ValueError("reader result DTOs must lock one profile version")
        elif self.competitor_profile_version_id or self.business or self.evidence:
            raise ValueError("unavailable reads cannot expose a partial profile")
        return self


__all__ = [
    "CompetitorProfileBusinessDTO",
    "CompetitorProfileEvidenceDTO",
    "CompetitorProfileReadRequest",
    "CompetitorProfileReaderResult",
]
