"""Read the saved competitor-agent profile for sellpoint-value V5.1.

This adapter has one dependency: the immutable competitor profile repository.
It does not recall candidates, run pair analysis, or invoke M12/M13/M14.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_repository import (
    CompetitorProfileAgentSnapshotRepository,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
    AGENT_SNAPSHOT_RULE_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_COMPETITOR_FACT_GROUPS,
    CompetitorProfileCandidateRef,
    CompetitorProfilePairFacts,
    CompetitorProfileSkuMarketFacts,
    SellpointValueCompetitorSource,
)


_PAIR_FACT_SOURCE_FIELDS = {
    **{group: group for group in SPV_V5_1_COMPETITOR_FACT_GROUPS},
    "parameter_claim_overlap": "param_claim_overlap",
}

_AC_LEGACY_TV_PARAMETER_ROLE_LABELS = frozenset(
    {
        "core_picture",
        "core_gaming",
        "core_system",
        "core_eye_care",
    }
)
_PARAMETER_ROLE_KEYS = frozenset({"roles", "target_roles", "candidate_roles"})


class SellpointValueCompetitorSourceIntegrityError(RuntimeError):
    """Raised when one saved competitor graph crosses its immutable boundary."""


class SellpointValueCompetitorReadRequest(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    target_sku_code: str = Field(min_length=1)
    access_mode: Literal["formal", "preview"] = "formal"
    release_scope_key: str | None = Field(default=None, min_length=1)
    competitor_profile_version_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_request(self) -> "SellpointValueCompetitorReadRequest":
        if self.access_mode == "formal" and self.competitor_profile_version_id:
            raise ValueError("formal competitor reads cannot select a version")
        if self.access_mode == "preview" and (
            not self.release_scope_key or not self.competitor_profile_version_id
        ):
            raise ValueError(
                "preview competitor reads require an explicit scope and version"
            )
        return self


class SellpointValueCompetitorReadResult(SellpointValueProfileBaseModel):
    status: Literal["available", "profile_unavailable"]
    source: SellpointValueCompetitorSource | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "SellpointValueCompetitorReadResult":
        if (self.status == "available") != (self.source is not None):
            raise ValueError("available competitor reads require exactly one source")
        return self


class SellpointValueCompetitorProfileAdapter:
    """Map a validated saved agent snapshot into the SPV V5.1 source contract."""

    def __init__(
        self,
        repository: CompetitorProfileAgentSnapshotRepository,
    ) -> None:
        self.repository = repository

    def read(
        self,
        request: SellpointValueCompetitorReadRequest,
    ) -> SellpointValueCompetitorReadResult:
        request = SellpointValueCompetitorReadRequest.model_validate(
            request.model_dump(mode="python")
        )
        repository_category = _enum_value(self.repository.category_code)
        if request.project_id != self.repository.project_id:
            raise ValueError("competitor adapter project does not match repository")
        if request.category_code != repository_category:
            raise ValueError("competitor adapter category does not match repository")

        target_sku_code = request.target_sku_code.strip().upper()
        read = self.repository.read_agent_profile_payload(
            target_sku_code=target_sku_code,
            access_mode=request.access_mode,
            competitor_profile_version_id=request.competitor_profile_version_id,
            release_scope_key=request.release_scope_key,
        )
        if read.status == "profile_unavailable":
            return SellpointValueCompetitorReadResult(status="profile_unavailable")
        if (
            read.status != "available"
            or read.full is None
            or read.competitor_profile_version_id is None
        ):
            raise SellpointValueCompetitorSourceIntegrityError(
                "available competitor read does not contain one full snapshot"
            )

        version = self.repository.get_version_by_id(read.competitor_profile_version_id)
        _assert_source_integrity(
            request=request,
            target_sku_code=target_sku_code,
            read=read,
            version=version,
        )
        full = read.full
        candidates = [
            _candidate_ref(row, category_code=request.category_code)
            for row in sorted(full.candidates, key=lambda item: item.source_rank)
        ]
        source = SellpointValueCompetitorSource(
            source=AGENT_SNAPSHOT_METHOD_VERSION,
            access_mode=request.access_mode,
            competitor_profile_version_id=version.competitor_profile_version_id,
            profile_version=version.profile_version,
            method_version=version.method_version,
            release_status=_enum_value(version.release_status),
            is_current=version.is_current,
            project_id=version.project_id,
            category_code=version.category_code,
            release_scope_key=version.release_scope_key,
            target_sku_code=target_sku_code,
            target_market=_target_market(full.target),
            candidates=candidates,
            priority_order=list(full.priority_order),
            source_version_result_hash=version.result_hash,
            source_result_hash=full.result_hash,
        )
        return SellpointValueCompetitorReadResult(
            status="available",
            source=source,
        )


def _assert_source_integrity(
    *,
    request: SellpointValueCompetitorReadRequest,
    target_sku_code: str,
    read: Any,
    version: Any,
) -> None:
    full = read.full
    assert full is not None
    identities = {
        read.competitor_profile_version_id,
        full.competitor_profile_version_id,
        version.competitor_profile_version_id,
    }
    if len(identities) != 1:
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor version identity changed during read"
        )
    if (
        version.project_id != request.project_id
        or full.project_id != request.project_id
        or version.category_code != request.category_code
        or full.category_code != request.category_code
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor source crossed project or category scope"
        )
    if (
        full.target.sku_code != target_sku_code
        or full.profile_version != version.profile_version
        or full.release_scope_key != version.release_scope_key
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor profile identity differs from its version"
        )
    if request.release_scope_key and (
        request.release_scope_key != version.release_scope_key
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor source differs from requested release scope"
        )
    if (
        version.schema_version != COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
        or version.rule_version != AGENT_SNAPSHOT_RULE_VERSION
        or version.method_version != AGENT_SNAPSHOT_METHOD_VERSION
        or full.method_version != AGENT_SNAPSHOT_METHOD_VERSION
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor source is not an agent snapshot v2 graph"
        )
    if bool(read.preview) != (request.access_mode == "preview"):
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor source preview marker differs from request"
        )
    release_status = _enum_value(version.release_status)
    if request.access_mode == "formal" and (
        release_status != "published" or not version.is_current
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "formal competitor source is not current published"
        )
    if request.access_mode == "preview" and not (
        (release_status == "draft" and not version.is_current)
        or (release_status == "published" and version.is_current)
    ):
        raise SellpointValueCompetitorSourceIntegrityError(
            "preview competitor source is not an allowed locked version"
        )
    if not version.result_hash or not full.result_hash:
        raise SellpointValueCompetitorSourceIntegrityError(
            "competitor source is missing immutable result hashes"
        )


def _candidate_ref(row: Any, *, category_code: Literal["TV", "AC"]):
    analysis = row.analysis
    pair_values: dict[str, Any] = {}
    available: list[str] = []
    unavailable: list[str] = []
    for group, source_field in _PAIR_FACT_SOURCE_FIELDS.items():
        value = getattr(analysis, source_field, None)
        if value is None:
            pair_values[group] = (
                []
                if group in {"ranking_gate_reasons", "shared_business_context"}
                else {}
            )
            unavailable.append(group)
        else:
            pair_values[group] = _pair_fact_value(
                value,
                category_code=category_code,
            )
            available.append(group)
    return CompetitorProfileCandidateRef(
        candidate_sku_code=row.candidate_sku_code,
        source_rank=row.source_rank,
        selected_rank=row.selected_rank,
        role=analysis.role,
        role_cn=analysis.role_cn,
        business_score=analysis.business_score,
        pair_result_hash=row.result_hash,
        market=_candidate_market(analysis.candidate, category_code=category_code),
        pair_facts=CompetitorProfilePairFacts(
            **pair_values,
            available_fact_groups=available,
            unavailable_fact_groups=unavailable,
        ),
    )


def _pair_fact_value(
    value: Any,
    *,
    category_code: Literal["TV", "AC"],
    field_name: str | None = None,
) -> Any:
    """Remove legacy TV bucket labels from AC parameter facts only.

    The saved competitor profile can contain correct AC parameter codes inside
    historical generic storage buckets named ``core_picture``/``core_gaming``.
    Those bucket labels are not AC facts and must not be copied into a new AC
    sellpoint-value profile. Actual parameter codes, values, evidence, and the
    immutable source pair hash remain unchanged.
    """

    if isinstance(value, dict):
        return {
            key: _pair_fact_value(
                item,
                category_code=category_code,
                field_name=str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        items = [
            _pair_fact_value(
                item,
                category_code=category_code,
                field_name=field_name,
            )
            for item in value
        ]
        if category_code == "AC" and field_name in _PARAMETER_ROLE_KEYS:
            return [
                item
                for item in items
                if item not in _AC_LEGACY_TV_PARAMETER_ROLE_LABELS
            ]
        return items
    return deepcopy(value)


def _target_market(identity: Any) -> CompetitorProfileSkuMarketFacts:
    return CompetitorProfileSkuMarketFacts(
        sku_code=identity.sku_code,
        brand_name=identity.brand_name,
        model_name=identity.model_name,
        product_category=identity.product_category,
        size_tier=identity.size_tier,
        price_band_in_size_tier=identity.price_band_in_size_tier,
        screen_size_inch=identity.screen_size_inch,
        weighted_price=identity.weighted_price,
        avg_weekly_sales_volume=identity.avg_weekly_sales_volume,
        sales_volume_total=identity.sales_volume_total,
    )


def _candidate_market(
    market: Any,
    *,
    category_code: Literal["TV", "AC"],
) -> CompetitorProfileSkuMarketFacts:
    return CompetitorProfileSkuMarketFacts(
        sku_code=market.sku_code,
        brand_name=market.brand_name,
        model_name=market.model_name,
        product_category=category_code,
        size_tier=market.size_tier,
        price_band_in_size_tier=market.price_band_in_size_tier,
        screen_size_inch=market.screen_size_inch,
        weighted_price=market.price_wavg,
        avg_weekly_sales_volume=market.avg_weekly_sales_volume,
        sales_volume_total=market.sales_volume_total,
        price_gap_to_target=market.price_gap_to_target,
        price_gap_pct_to_target=market.price_gap_pct_to_target,
    )


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


__all__ = [
    "SellpointValueCompetitorProfileAdapter",
    "SellpointValueCompetitorReadRequest",
    "SellpointValueCompetitorReadResult",
    "SellpointValueCompetitorSourceIntegrityError",
]
