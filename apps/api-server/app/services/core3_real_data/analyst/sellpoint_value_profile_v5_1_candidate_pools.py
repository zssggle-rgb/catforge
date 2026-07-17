"""Build V5.1 competitor/reference pools and question-local eligibility.

The saved competitor profile is authoritative and is never filtered here.
Market references remain a separate analytical pool.  Eligibility is evaluated
independently for every question, so a missing fact cannot disable a candidate
for unrelated questions.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateQuestion,
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_CANDIDATE_QUESTIONS,
    SPV_V5_1_COMPETITOR_FACT_GROUPS,
    AnalysisReferencePurpose,
    CandidateSourceType,
    CompetitorProfileCandidateRef,
    CompetitorProfileSkuMarketFacts,
    QuestionCandidateSet,
    QuestionCandidateUse,
    SellpointValueAnalysisReference,
    SellpointValueCandidatePools,
    SellpointValueCompetitorSource,
)


SPV_V5_1_CANDIDATE_POOLS_SCHEMA_VERSION = "sellpoint_value_candidate_pools_v5_1"

QUESTION_ORDER = SPV_V5_1_CANDIDATE_QUESTIONS


@dataclass(frozen=True)
class _QuestionPolicy:
    required_dimensions: tuple[str, ...] = ()
    alternative_dimension_groups: tuple[tuple[str, ...], ...] = ()
    allowed_reference_purposes: tuple[AnalysisReferencePurpose, ...] = ()

    @property
    def relevant_dimensions(self) -> set[str]:
        return {
            *self.required_dimensions,
            *(
                dimension
                for group in self.alternative_dimension_groups
                for dimension in group
            ),
        }


_ALL_MARKET_PURPOSES = tuple(
    sorted(AnalysisReferencePurpose, key=lambda row: row.value)
)

QUESTION_POLICIES: dict[CandidateQuestion, _QuestionPolicy] = {
    "current_price_support": _QuestionPolicy(
        required_dimensions=("market_price",),
        allowed_reference_purposes=_ALL_MARKET_PURPOSES,
    ),
    "value_relative_advantage": _QuestionPolicy(
        alternative_dimension_groups=(
            (
                "battlefield_facts",
                "matched_dimensions",
                "semantic_overlap",
                "value_anchor",
                "value_facts",
            ),
            (
                "candidate_purchase_reason_profile",
                "m12d_consumption",
                "market_validation",
                "target_purchase_reason_profile",
                "value_facts",
            ),
        ),
        allowed_reference_purposes=(
            AnalysisReferencePurpose.BATTLEFIELD_BENCHMARK,
            AnalysisReferencePurpose.PERFORMANCE_ARCHETYPE,
        ),
    ),
    "same_brand_role": _QuestionPolicy(
        required_dimensions=("same_brand_relation",),
        alternative_dimension_groups=(("market_price", "weekly_sales"),),
        allowed_reference_purposes=(AnalysisReferencePurpose.SAME_BRAND_SIZE_LADDER,),
    ),
    "scale_conversion": _QuestionPolicy(
        required_dimensions=("weekly_sales",),
        allowed_reference_purposes=_ALL_MARKET_PURPOSES,
    ),
    "configuration_follow": _QuestionPolicy(
        alternative_dimension_groups=(("parameter_claim_overlap", "parameter_facts"),),
        allowed_reference_purposes=(AnalysisReferencePurpose.PARAMETER_GROUP,),
    ),
    "specific_competitor": _QuestionPolicy(
        required_dimensions=("competitor_identity",),
    ),
    "parameter_conversion": _QuestionPolicy(
        alternative_dimension_groups=(
            ("parameter_claim_overlap", "parameter_facts"),
            ("market_price", "weekly_sales"),
        ),
        allowed_reference_purposes=(AnalysisReferencePurpose.PARAMETER_GROUP,),
    ),
    "battlefield_expansion": _QuestionPolicy(
        alternative_dimension_groups=(
            (
                "battlefield_facts",
                "semantic_overlap",
                "shared_business_context",
                "value_anchor",
                "value_facts",
            ),
        ),
        allowed_reference_purposes=(AnalysisReferencePurpose.BATTLEFIELD_BENCHMARK,),
    ),
}

_SHARED_DIMENSIONS = {
    "brand_identity",
    "market_price",
    "same_brand_relation",
    "weekly_sales",
}
_COMPETITOR_DIMENSIONS = {
    *_SHARED_DIMENSIONS,
    *SPV_V5_1_COMPETITOR_FACT_GROUPS,
    "competitor_identity",
}
_REFERENCE_DIMENSIONS = {
    *_SHARED_DIMENSIONS,
    "battlefield_facts",
    "market_reference_identity",
    "parameter_facts",
    "value_facts",
}


def build_sellpoint_value_candidate_pools(
    *,
    competitor_source: SellpointValueCompetitorSource,
    analysis_reference_records: Sequence[Mapping[str, Any] | BaseModel] = (),
) -> SellpointValueCandidatePools:
    """Preserve the formal manifest and assess every pool row per question."""

    source = SellpointValueCompetitorSource.model_validate(
        competitor_source.model_dump(mode="python")
    )
    formal_competitors = [row.model_copy(deep=True) for row in source.candidates]
    analysis_references = _analysis_references(
        source=source,
        records=analysis_reference_records,
    )
    question_sets = [
        _question_candidate_set(
            question_code=question_code,
            source=source,
            formal_competitors=formal_competitors,
            analysis_references=analysis_references,
        )
        for question_code in QUESTION_ORDER
    ]
    payload = {
        "schema_version": SPV_V5_1_CANDIDATE_POOLS_SCHEMA_VERSION,
        "project_id": source.project_id,
        "category_code": source.category_code,
        "target_sku_code": source.target_sku_code,
        "competitor_profile_version_id": source.competitor_profile_version_id,
        "competitor_source_result_hash": source.source_result_hash,
        "competitor_source_version_result_hash": source.source_version_result_hash,
        "formal_competitors": [
            row.model_dump(mode="json") for row in formal_competitors
        ],
        "priority_order": list(source.priority_order),
        "analysis_references": [
            row.model_dump(mode="json") for row in analysis_references
        ],
        "question_candidate_sets": [
            row.model_dump(mode="json") for row in question_sets
        ],
    }
    return SellpointValueCandidatePools(
        **payload,
        result_hash=canonical_v4_hash(payload),
    )


def _question_candidate_set(
    *,
    question_code: CandidateQuestion,
    source: SellpointValueCompetitorSource,
    formal_competitors: Sequence[CompetitorProfileCandidateRef],
    analysis_references: Sequence[SellpointValueAnalysisReference],
) -> QuestionCandidateSet:
    policy = QUESTION_POLICIES[question_code]
    uses = [
        _competitor_use(
            question_code=question_code,
            policy=policy,
            source=source,
            candidate=candidate,
        )
        for candidate in formal_competitors
    ]
    uses.extend(
        _reference_use(
            question_code=question_code,
            policy=policy,
            source=source,
            reference=reference,
        )
        for reference in analysis_references
    )
    return QuestionCandidateSet(
        question_code=question_code,
        required_dimensions=sorted(policy.required_dimensions),
        alternative_dimension_groups=[
            sorted(group) for group in policy.alternative_dimension_groups
        ],
        allowed_reference_purposes=sorted(
            policy.allowed_reference_purposes,
            key=lambda row: row.value,
        ),
        candidate_uses=uses,
    )


def _competitor_use(
    *,
    question_code: CandidateQuestion,
    policy: _QuestionPolicy,
    source: SellpointValueCompetitorSource,
    candidate: CompetitorProfileCandidateRef,
) -> QuestionCandidateUse:
    available = _competitor_dimensions(source, candidate)
    selected, usable, unavailable, reasons = _evaluate_policy(
        question_code=question_code,
        policy=policy,
        available_dimensions=available,
        applicable_dimensions=_COMPETITOR_DIMENSIONS,
        source_allowed=True,
    )
    selection_reasons: list[str] = []
    rejection_reasons: list[str] = []
    if selected:
        selection_reasons = [
            "competitor_profile_candidate_preserved",
            "question_minimum_facts_available",
        ]
        if candidate.selected_rank is not None:
            selection_reasons.append("source_top3_priority_label")
    else:
        rejection_reasons = reasons
    return QuestionCandidateUse(
        candidate_sku_code=candidate.candidate_sku_code,
        source_type=CandidateSourceType.COMPETITOR,
        source_rank=candidate.source_rank,
        priority_rank=candidate.selected_rank,
        selected=selected,
        usable_dimensions=usable,
        unavailable_dimensions=unavailable,
        selection_reasons=selection_reasons,
        rejection_reasons=rejection_reasons,
        evidence_refs=_competitor_evidence_refs(source, candidate),
    )


def _reference_use(
    *,
    question_code: CandidateQuestion,
    policy: _QuestionPolicy,
    source: SellpointValueCompetitorSource,
    reference: SellpointValueAnalysisReference,
) -> QuestionCandidateUse:
    purpose_match = bool(
        set(reference.purposes) & set(policy.allowed_reference_purposes)
    )
    available = _reference_dimensions(source, reference)
    selected, usable, unavailable, reasons = _evaluate_policy(
        question_code=question_code,
        policy=policy,
        available_dimensions=available,
        applicable_dimensions=_REFERENCE_DIMENSIONS,
        source_allowed=purpose_match,
    )
    return QuestionCandidateUse(
        candidate_sku_code=reference.reference_sku_code,
        source_type=CandidateSourceType.MARKET_REFERENCE,
        selected=selected,
        usable_dimensions=usable,
        unavailable_dimensions=unavailable,
        selection_reasons=(
            ["analysis_reference_purpose_matched", "question_minimum_facts_available"]
            if selected
            else []
        ),
        rejection_reasons=[] if selected else reasons,
        evidence_refs=deepcopy(reference.evidence_refs),
    )


def _evaluate_policy(
    *,
    question_code: CandidateQuestion,
    policy: _QuestionPolicy,
    available_dimensions: set[str],
    applicable_dimensions: set[str],
    source_allowed: bool,
) -> tuple[bool, list[str], list[str], list[str]]:
    relevant = policy.relevant_dimensions & applicable_dimensions
    usable = sorted(relevant & available_dimensions)
    unavailable = sorted(relevant - available_dimensions)
    reasons: list[str] = []
    if not source_allowed:
        reasons.append("source_not_applicable_to_question")
    required = set(policy.required_dimensions) & applicable_dimensions
    missing_required = sorted(required - available_dimensions)
    reasons.extend(f"missing_required_dimension:{item}" for item in missing_required)
    for group in policy.alternative_dimension_groups:
        applicable_group = set(group) & applicable_dimensions
        if applicable_group and not applicable_group & available_dimensions:
            reasons.append(
                f"missing_alternative_group:{'+'.join(sorted(applicable_group))}"
            )
        elif source_allowed and not applicable_group:
            reasons.append("question_has_no_applicable_dimension_for_source")
    if (
        question_code == "same_brand_role"
        and "brand_identity" in available_dimensions
        and "same_brand_relation" not in available_dimensions
    ):
        reasons.append("not_same_brand_as_target")
    selected = not reasons
    if not selected and not reasons:
        reasons.append("question_minimum_facts_unavailable")
    return selected, usable, unavailable, reasons


def _competitor_dimensions(
    source: SellpointValueCompetitorSource,
    candidate: CompetitorProfileCandidateRef,
) -> set[str]:
    dimensions = {"competitor_identity"}
    dimensions.update(candidate.pair_facts.available_fact_groups)
    dimensions.update(_market_dimensions(source.target_market, candidate.market))
    dimensions.update(
        _brand_dimensions(
            source.target_market.brand_name,
            candidate.market.brand_name,
        )
    )
    return dimensions


def _reference_dimensions(
    source: SellpointValueCompetitorSource,
    reference: SellpointValueAnalysisReference,
) -> set[str]:
    dimensions = {"market_reference_identity"}
    dimensions.update(_market_dimensions(source.target_market, reference.market))
    dimensions.update(
        _brand_dimensions(
            source.target_market.brand_name,
            reference.brand_name,
        )
    )
    if reference.parameter_facts is not None:
        dimensions.add("parameter_facts")
    if reference.battlefield_facts is not None:
        dimensions.add("battlefield_facts")
    if reference.value_facts is not None:
        dimensions.add("value_facts")
    return dimensions


def _market_dimensions(
    target: CompetitorProfileSkuMarketFacts,
    candidate: CompetitorProfileSkuMarketFacts,
) -> set[str]:
    dimensions: set[str] = set()
    if target.weighted_price is not None and candidate.weighted_price is not None:
        dimensions.add("market_price")
    if (
        target.avg_weekly_sales_volume is not None
        and candidate.avg_weekly_sales_volume is not None
    ):
        dimensions.add("weekly_sales")
    return dimensions


def _brand_dimensions(
    target_brand: str | None, candidate_brand: str | None
) -> set[str]:
    if not target_brand or not candidate_brand:
        return set()
    dimensions = {"brand_identity"}
    if target_brand.strip().casefold() == candidate_brand.strip().casefold():
        dimensions.add("same_brand_relation")
    return dimensions


def _competitor_evidence_refs(
    source: SellpointValueCompetitorSource,
    candidate: CompetitorProfileCandidateRef,
) -> list[SellpointValueEvidenceRef]:
    return [
        SellpointValueEvidenceRef(
            module_code="COMPETITOR_PROFILE_V1_1",
            record_type="profile",
            record_id=source.competitor_profile_version_id,
            result_hash=source.source_result_hash,
        ),
        SellpointValueEvidenceRef(
            module_code="COMPETITOR_PROFILE_V1_1",
            record_type="pair",
            record_id=f"{source.target_sku_code}:{candidate.candidate_sku_code}",
            result_hash=candidate.pair_result_hash,
        ),
    ]


def _analysis_references(
    *,
    source: SellpointValueCompetitorSource,
    records: Sequence[Mapping[str, Any] | BaseModel],
) -> list[SellpointValueAnalysisReference]:
    grouped: dict[str, list[SellpointValueAnalysisReference]] = defaultdict(list)
    formal_codes = {row.candidate_sku_code for row in source.candidates}
    for record in records:
        normalized = _analysis_reference(source=source, record=record)
        if normalized is None:
            continue
        grouped[normalized.reference_sku_code].append(normalized)
    return [
        _merge_analysis_references(
            source=source,
            rows=grouped[sku_code],
            also_competitor=sku_code in formal_codes,
        )
        for sku_code in sorted(grouped)
    ]


def _analysis_reference(
    *,
    source: SellpointValueCompetitorSource,
    record: Mapping[str, Any] | BaseModel,
) -> SellpointValueAnalysisReference | None:
    raw = (
        record.model_dump(mode="python")
        if isinstance(record, BaseModel)
        else dict(record)
    )
    candidate = (
        raw.get("candidate") if isinstance(raw.get("candidate"), Mapping) else raw
    )
    sku_code = (
        str(
            candidate.get("sku_code")
            or raw.get("reference_sku_code")
            or raw.get("candidate_sku_code")
            or ""
        )
        .strip()
        .upper()
    )
    if not sku_code or sku_code == source.target_sku_code:
        return None
    record_category = candidate.get("product_category") or raw.get("category_code")
    if record_category is not None and str(record_category) != source.category_code:
        raise ValueError("analysis reference crossed the competitor source category")
    purpose_values = (
        raw.get("purposes")
        or raw.get("reference_purposes")
        or candidate.get("reference_purposes")
        or [AnalysisReferencePurpose.SAME_SIZE_MARKET.value]
    )
    purposes = sorted(
        {
            AnalysisReferencePurpose(
                value.value
                if isinstance(value, AnalysisReferencePurpose)
                else str(value)
            )
            for value in purpose_values
        },
        key=lambda row: row.value,
    )
    market_raw = raw.get("market") or raw.get("market_summary") or candidate
    market = _reference_market(
        sku_code=sku_code,
        category_code=source.category_code,
        brand_name=_optional_text(candidate.get("brand_name") or raw.get("brand_name")),
        model_name=_optional_text(candidate.get("model_name") or raw.get("model_name")),
        raw=dict(market_raw) if isinstance(market_raw, Mapping) else {},
    )
    source_hashes = {
        str(key): str(value)
        for key, value in dict(raw.get("source_hashes") or {}).items()
        if value
    }
    if candidate.get("result_hash") and "M07" not in source_hashes:
        source_hashes["M07"] = str(candidate["result_hash"])
    evidence_refs = _reference_evidence_refs(
        sku_code=sku_code,
        raw=raw,
        source_hashes=source_hashes,
    )
    brand_name = market.brand_name
    same_brand = (
        None
        if not source.target_market.brand_name or not brand_name
        else source.target_market.brand_name.strip().casefold()
        == brand_name.strip().casefold()
    )
    return SellpointValueAnalysisReference(
        reference_sku_code=sku_code,
        brand_name=brand_name,
        model_name=market.model_name,
        purposes=purposes,
        also_competitor=False,
        same_brand_as_target=same_brand,
        market=market,
        parameter_facts=_optional_mapping(
            raw,
            "parameter_facts",
            "normalized_parameters",
            "param_feature",
            fallback=candidate,
        ),
        battlefield_facts=_optional_mapping(
            raw,
            "battlefield_facts",
            "value_battlefields",
            "battlefield_feature",
            fallback=candidate,
        ),
        value_facts=_optional_mapping(
            raw,
            "value_facts",
            "claim_value_facts",
            "claim_value_overlap",
            fallback=candidate,
        ),
        source_hashes=source_hashes,
        evidence_refs=evidence_refs,
    )


def _merge_analysis_references(
    *,
    source: SellpointValueCompetitorSource,
    rows: Sequence[SellpointValueAnalysisReference],
    also_competitor: bool,
) -> SellpointValueAnalysisReference:
    ordered = sorted(
        rows, key=lambda row: canonical_v4_hash(row.model_dump(mode="json"))
    )
    base = min(
        ordered,
        key=lambda row: (
            -_market_fact_count(row.market),
            canonical_v4_hash(row.model_dump(mode="json")),
        ),
    )
    purposes = sorted(
        {purpose for row in rows for purpose in row.purposes},
        key=lambda row: row.value,
    )
    source_hashes: dict[str, str] = {}
    for key in sorted({key for row in rows for key in row.source_hashes}):
        source_hashes[key] = min(
            row.source_hashes[key] for row in rows if key in row.source_hashes
        )
    evidence_by_key = {
        (
            row.module_code,
            row.record_type,
            row.record_id,
            row.result_hash,
        ): row
        for item in rows
        for row in item.evidence_refs
    }
    brand_name = next((row.brand_name for row in ordered if row.brand_name), None)
    model_name = next((row.model_name for row in ordered if row.model_name), None)
    same_brand = (
        None
        if not source.target_market.brand_name or not brand_name
        else source.target_market.brand_name.strip().casefold()
        == brand_name.strip().casefold()
    )
    return SellpointValueAnalysisReference(
        reference_sku_code=base.reference_sku_code,
        brand_name=brand_name,
        model_name=model_name,
        purposes=purposes,
        also_competitor=also_competitor,
        same_brand_as_target=same_brand,
        market=_merge_reference_market(
            base=base,
            ordered=ordered,
            brand_name=brand_name,
            model_name=model_name,
        ),
        parameter_facts=_richest_optional_mapping(rows, "parameter_facts"),
        battlefield_facts=_richest_optional_mapping(rows, "battlefield_facts"),
        value_facts=_richest_optional_mapping(rows, "value_facts"),
        source_hashes=source_hashes,
        evidence_refs=[evidence_by_key[key] for key in sorted(evidence_by_key)],
    )


def _reference_market(
    *,
    sku_code: str,
    category_code: str,
    brand_name: str | None,
    model_name: str | None,
    raw: Mapping[str, Any],
) -> CompetitorProfileSkuMarketFacts:
    return CompetitorProfileSkuMarketFacts(
        sku_code=sku_code,
        brand_name=brand_name,
        model_name=model_name,
        product_category=category_code,
        size_tier=_optional_text(raw.get("size_tier")),
        price_band_in_size_tier=_optional_text(
            raw.get("price_band_in_size_tier") or raw.get("price_band_size")
        ),
        screen_size_inch=_optional_decimal(raw.get("screen_size_inch")),
        weighted_price=_optional_decimal(
            raw.get("weighted_price")
            if raw.get("weighted_price") is not None
            else raw.get("price_wavg")
            if raw.get("price_wavg") is not None
            else raw.get("avg_price")
        ),
        avg_weekly_sales_volume=_optional_decimal(raw.get("avg_weekly_sales_volume")),
        sales_volume_total=_optional_decimal(raw.get("sales_volume_total")),
    )


def _reference_evidence_refs(
    *,
    sku_code: str,
    raw: Mapping[str, Any],
    source_hashes: Mapping[str, str],
) -> list[SellpointValueEvidenceRef]:
    explicit = raw.get("evidence_refs")
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        return sorted(
            [SellpointValueEvidenceRef.model_validate(row) for row in explicit],
            key=lambda row: (
                row.module_code,
                row.record_type,
                row.record_id,
                row.result_hash,
            ),
        )
    return [
        SellpointValueEvidenceRef(
            module_code=module_code,
            record_type="analysis_reference",
            record_id=sku_code,
            result_hash=result_hash,
        )
        for module_code, result_hash in sorted(source_hashes.items())
    ]


def _merge_reference_market(
    *,
    base: SellpointValueAnalysisReference,
    ordered: Sequence[SellpointValueAnalysisReference],
    brand_name: str | None,
    model_name: str | None,
) -> CompetitorProfileSkuMarketFacts:
    preferred = [base, *(row for row in ordered if row is not base)]

    def value(field_name: str) -> Any:
        return next(
            (
                getattr(row.market, field_name)
                for row in preferred
                if getattr(row.market, field_name) is not None
            ),
            None,
        )

    return CompetitorProfileSkuMarketFacts(
        sku_code=base.reference_sku_code,
        brand_name=brand_name,
        model_name=model_name,
        product_category=base.market.product_category,
        size_tier=value("size_tier"),
        price_band_in_size_tier=value("price_band_in_size_tier"),
        screen_size_inch=value("screen_size_inch"),
        weighted_price=value("weighted_price"),
        avg_weekly_sales_volume=value("avg_weekly_sales_volume"),
        sales_volume_total=value("sales_volume_total"),
        price_gap_to_target=value("price_gap_to_target"),
        price_gap_pct_to_target=value("price_gap_pct_to_target"),
    )


def _optional_mapping(
    raw: Mapping[str, Any],
    *keys: str,
    fallback: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    for source in (raw, fallback or {}):
        for key in keys:
            if key not in source:
                continue
            value = source[key]
            if value is None:
                return None
            if not isinstance(value, Mapping):
                raise ValueError(f"analysis reference {key} must be a mapping")
            return deepcopy(dict(value))
    return None


def _richest_optional_mapping(
    rows: Sequence[SellpointValueAnalysisReference],
    field_name: str,
) -> dict[str, Any] | None:
    values = [
        getattr(row, field_name) for row in rows if getattr(row, field_name) is not None
    ]
    if not values:
        return None
    return deepcopy(
        max(values, key=lambda value: (len(value), canonical_v4_hash(value)))
    )


def _market_fact_count(market: CompetitorProfileSkuMarketFacts) -> int:
    return sum(
        value is not None
        for value in (
            market.weighted_price,
            market.avg_weekly_sales_volume,
            market.sales_volume_total,
            market.screen_size_inch,
            market.size_tier,
            market.price_band_in_size_tier,
        )
    )


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or str(value).strip() in {"", "-"}:
        return None
    return Decimal(str(value))


__all__ = [
    "QUESTION_ORDER",
    "QUESTION_POLICIES",
    "SPV_V5_1_CANDIDATE_POOLS_SCHEMA_VERSION",
    "build_sellpoint_value_candidate_pools",
]
