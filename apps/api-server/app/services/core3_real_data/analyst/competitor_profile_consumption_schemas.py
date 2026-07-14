"""Typed one-version context shared by competitor-profile consumers."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileBusinessDTO,
    CompetitorProfileEvidenceDTO,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


CompetitorProfileConsumerCode = Literal[
    "competitor_agent",
    "feishu_card",
    "pm_report",
    "evidence_report",
    "qa",
    "sellpoint_value_profile",
]

COMPETITOR_PROFILE_CONSUMERS: tuple[CompetitorProfileConsumerCode, ...] = (
    "competitor_agent",
    "evidence_report",
    "feishu_card",
    "pm_report",
    "qa",
    "sellpoint_value_profile",
)


class CompetitorProfileConsumptionContext(CompetitorProfileBaseModel):
    """One immutable read result that every downstream consumer must share."""

    status: Literal["available", "profile_unavailable"]
    competitor_profile_version_id: str | None = None
    preview: bool = False
    consumers: list[CompetitorProfileConsumerCode] = Field(default_factory=list)
    business: CompetitorProfileBusinessDTO | None = None
    evidence: CompetitorProfileEvidenceDTO | None = None
    message_cn: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_context(self) -> "CompetitorProfileConsumptionContext":
        if self.status == "available":
            if (
                not self.competitor_profile_version_id
                or not self.business
                or not self.evidence
            ):
                raise ValueError("available consumption requires one complete reader result")
            if self.consumers != list(COMPETITOR_PROFILE_CONSUMERS):
                raise ValueError("available consumption must enable the frozen consumer set")
            if (
                self.evidence.competitor_profile_version_id
                != self.competitor_profile_version_id
            ):
                raise ValueError("all consumers must lock the reader profile version")
            if self.evidence.preview != self.preview:
                raise ValueError("consumer preview state must match the reader evidence")
        elif (
            self.competitor_profile_version_id
            or self.consumers
            or self.business
            or self.evidence
        ):
            raise ValueError("unavailable consumption cannot expose partial profile data")
        return self


__all__ = [
    "COMPETITOR_PROFILE_CONSUMERS",
    "CompetitorProfileConsumerCode",
    "CompetitorProfileConsumptionContext",
]
