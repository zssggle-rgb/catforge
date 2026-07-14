"""Typed orchestration and failure-isolation contracts for competitor profiles."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection_schemas import (
    KeyCompetitorSelectionConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileBaseModel,
    CompetitorProfileDraftBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionConfig,
)


COMPETITOR_PROFILE_MATERIALIZER_SCHEMA_VERSION = "competitor_profile_materializer_v1"


class CompetitorProfileMaterializationConfig(CompetitorProfileBaseModel):
    config_version: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    recall: CandidateRecallConfig
    eligibility: CandidateEligibilityConfig
    purchase_pool: PurchasePoolSemanticConfig
    value_substitution: ValueSubstitutionConfig
    price_volume: PriceVolumePressureConfig
    relation: CompetitorRelationConfig
    key_selection: KeyCompetitorSelectionConfig

    @model_validator(mode="after")
    def validate_category(self) -> "CompetitorProfileMaterializationConfig":
        category_configs = (
            self.purchase_pool,
            self.value_substitution,
            self.price_volume,
            self.relation,
            self.key_selection,
        )
        if any(
            row.product_category != self.product_category for row in category_configs
        ):
            raise ValueError(
                "all materialization configs must use one product category"
            )
        return self


class MaterializedCompetitorProfile(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_materializer_v1"] = (
        COMPETITOR_PROFILE_MATERIALIZER_SCHEMA_VERSION
    )
    target_sku_code: str = Field(min_length=1)
    product_category: Literal["TV", "AC"]
    draft: CompetitorProfileDraftBundle
    stage_result_hashes: dict[str, str] = Field(min_length=1)
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_materialized(self) -> "MaterializedCompetitorProfile":
        if self.target_sku_code != self.draft.profile.target_sku_code:
            raise ValueError("materialized target must match profile")
        if self.product_category != self.draft.profile.category_code:
            raise ValueError("materialized category must match profile")
        required = {
            "candidate_pipeline",
            "pair_feature",
            "purchase_pool",
            "value_substitution",
            "price_volume_pressure",
            "relation_evaluation",
            "key_selection",
            "profile",
        }
        if set(self.stage_result_hashes) != required:
            raise ValueError(
                "materialized stage hashes must cover the full G12-G20 chain"
            )
        if self.stage_result_hashes["profile"] != self.draft.profile.result_hash:
            raise ValueError("materialized profile hash must match stage hash")
        return self


class TargetMaterializationStatus(CompetitorProfileBaseModel):
    target_sku_code: str = Field(min_length=1)
    status: Literal["generated", "failed"]
    profile_result_hash: str | None = None
    stage_result_hashes: dict[str, str] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "TargetMaterializationStatus":
        if self.status == "generated":
            if not self.profile_result_hash or self.error_code or self.error_message:
                raise ValueError("generated targets require a hash and no error")
        elif not self.error_code or not self.error_message or self.profile_result_hash:
            raise ValueError(
                "failed targets require a safe error without a profile hash"
            )
        return self


class CompetitorProfileBatchMaterializationResult(CompetitorProfileBaseModel):
    schema_version: Literal["competitor_profile_materializer_v1"] = (
        COMPETITOR_PROFILE_MATERIALIZER_SCHEMA_VERSION
    )
    product_category: Literal["TV", "AC"]
    requested_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    statuses: list[TargetMaterializationStatus]
    materialized_profiles: list[MaterializedCompetitorProfile]
    config_version: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_batch(self) -> "CompetitorProfileBatchMaterializationResult":
        if self.requested_count != len(self.statuses):
            raise ValueError("batch requested count must match statuses")
        if self.succeeded_count + self.failed_count != self.requested_count:
            raise ValueError(
                "batch success and failure counts must match requested count"
            )
        if self.succeeded_count != len(self.materialized_profiles):
            raise ValueError("batch successes must match materialized profiles")
        codes = [row.target_sku_code for row in self.statuses]
        if codes != sorted(set(codes)):
            raise ValueError("batch statuses must be sorted and unique")
        profile_codes = [row.target_sku_code for row in self.materialized_profiles]
        if profile_codes != sorted(set(profile_codes)):
            raise ValueError("materialized profiles must be sorted and unique")
        generated_codes = {
            row.target_sku_code for row in self.statuses if row.status == "generated"
        }
        if generated_codes != set(profile_codes):
            raise ValueError("generated statuses must match materialized profiles")
        return self


__all__ = [
    "COMPETITOR_PROFILE_MATERIALIZER_SCHEMA_VERSION",
    "CompetitorProfileBatchMaterializationResult",
    "CompetitorProfileMaterializationConfig",
    "MaterializedCompetitorProfile",
    "TargetMaterializationStatus",
]
