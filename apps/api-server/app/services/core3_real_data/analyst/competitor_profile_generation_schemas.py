"""Typed draft-generation contracts for competitor profiles."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileInputRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    CompetitorProfileMaterializationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileReadBundle,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
)


class CompetitorProfileGenerationRequest(CompetitorProfileBaseModel):
    input_request: CompetitorProfileInputRequest
    profile_version: str = Field(min_length=1)
    config: CompetitorProfileMaterializationConfig
    generated_by: str = Field(default="system", min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "CompetitorProfileGenerationRequest":
        if self.input_request.product_category != self.config.product_category:
            raise ValueError("generation input and materialization config must share a category")
        return self


class CompetitorProfileGenerationReadback(CompetitorProfileBaseModel):
    status: Literal["generated", "reused"]
    persisted: CompetitorProfileReadBundle


class CompetitorProfileSkuGenerationStatus(CompetitorProfileBaseModel):
    target_sku_code: str = Field(min_length=1)
    status: Literal["generated", "reused", "skipped", "failed"]
    profile_result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "CompetitorProfileSkuGenerationStatus":
        if self.status == "failed":
            if not self.error_code or not self.error_message or self.profile_result_hash:
                raise ValueError("failed generation status requires only a safe error")
        elif self.error_code or self.error_message:
            raise ValueError("successful generation status cannot carry an error")
        return self


class CompetitorProfileBatchGenerationResult(CompetitorProfileBaseModel):
    version: CompetitorProfileVersionRecord
    requested_sku_count: int = Field(ge=0)
    remaining_sku_count: int = Field(ge=0)
    generated_count: int = Field(ge=0)
    reused_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    checkpoint_sku_code: str | None = None
    statuses: list[CompetitorProfileSkuGenerationStatus]

    @model_validator(mode="after")
    def validate_counts(self) -> "CompetitorProfileBatchGenerationResult":
        actual = {
            status: sum(row.status == status for row in self.statuses)
            for status in ("generated", "reused", "skipped", "failed")
        }
        for status, count in actual.items():
            if getattr(self, f"{status}_count") != count:
                raise ValueError(f"{status} count must match generation statuses")
        if len(self.statuses) > self.requested_sku_count:
            raise ValueError("generation statuses cannot exceed the authoritative manifest")
        return self


__all__ = [
    "CompetitorProfileBatchGenerationResult",
    "CompetitorProfileGenerationReadback",
    "CompetitorProfileGenerationRequest",
    "CompetitorProfileSkuGenerationStatus",
]
