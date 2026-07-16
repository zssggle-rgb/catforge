"""Build one lossless, version-shared V1.1 analysis snapshot per SKU.

The builder consumes only the frozen category input bundle.  It does not query
repositories, call external services, compare SKU pairs, or produce business
conclusions.  Missing and conflicting modules remain local availability states.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    COMPETITOR_PROFILE_SOURCE_MODULES,
    CompetitorProfileCategoryInputBundle,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    AnalysisItem,
    ClaimAttributionRecord,
    ClaimContributionRecord,
    ClaimContributionSnapshot,
    ClaimFactItem,
    ClaimValueFactItem,
    ClaimValueRecord,
    ClaimValueSnapshot,
    FactSectionsSnapshot,
    IdentityMarketSnapshot,
    ModuleAvailabilitySnapshot,
    NormalizedSourceFact,
    NormalizedSourceOccurrence,
    ProductFormFacts,
    PurchasePressureReasonRecord,
    PurchaseReasonAnchorFact,
    PurchaseReasonAnchorRecord,
    PurchaseReasonSnapshot,
    ReviewItem,
    SkuLevelClaimValueRecord,
    SkuMarketSnapshot,
    TypedFactValue,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.hash_utils import stable_hash


SNAPSHOT_BUILDER_VERSION = "competitor_profile_v1_1_sku_snapshot_builder_v1"
SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION = (
    "competitor_profile_v1_1_sku_snapshot_authoritative_projection_v2"
)

_REVIEW_STATUSES = {
    "blocked",
    "failed",
    "needs_review",
    "pending_review",
    "review_required",
}
_CONFLICT_STATUSES = {"ambiguous", "conflict", "invalid", "mismatch"}
_POSITIVE_CLAIM_ROLES = {
    "basic_threshold",
    "brand_claim_only",
    "premium_driver_estimated",
    "sales_driver_estimated",
    "unique_payment_potential",
    "user_validated_need",
    "value_bundle_claim",
    "weak_user_perception_claim",
}
_OPPORTUNITY_CLAIM_ROLES = {
    "high_price_competitor_intercept",
    "opportunity_gap",
    "price_up_opportunity",
}
_ANCHOR_LIST_ROLES = {
    "core_payment_anchors_json": "core_payment",
    "established_anchors_json": "established",
    "proposition_anchors_json": "proposition",
    "supporting_anchors_json": "supporting",
    "weak_expression_anchors_json": "weak_expression",
    "risk_drag_anchors_json": "risk_drag",
}
_M12C_BUSINESS_TYPE_PRIORITY = {
    "高溢价卖点": 0,
    "份额转化卖点": 1,
    "客户获得价值卖点": 2,
    "人无我有型支付价值卖点": 3,
    "待激活卖点": 4,
    "门槛卖点": 5,
    "厂家主张卖点": 6,
    "竞品拦截卖点": 7,
    "价格压力卖点": 8,
    "样本不足待复核": 9,
}
_SINGLE_RECORD_SOURCE_MODULES = {
    "M03B",
    "M04C",
    "M05C",
    "M07",
    "M09C",
    "M10C",
    "M11C",
    "M12D",
}


class VersionSkuAnalysisSnapshotBuildError(RuntimeError):
    """Raised when a requested SKU or version scope is inconsistent."""


class VersionSkuAnalysisSnapshotBuilder:
    """Create deterministic shared SKU snapshots without pair-level analysis."""

    def build(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        *,
        competitor_profile_version_id: str,
        sku_code: str,
    ) -> VersionSkuAnalysisSnapshot:
        return self._build(
            category_bundle,
            competitor_profile_version_id=competitor_profile_version_id,
            sku_code=sku_code,
            authoritative_only=False,
        )

    def build_authoritative(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        *,
        competitor_profile_version_id: str,
        sku_code: str,
    ) -> VersionSkuAnalysisSnapshot:
        """Build the typed production projection without materializing raw bags."""

        return self._build(
            category_bundle,
            competitor_profile_version_id=competitor_profile_version_id,
            sku_code=sku_code,
            authoritative_only=True,
        )

    def _build(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        *,
        competitor_profile_version_id: str,
        sku_code: str,
        authoritative_only: bool,
    ) -> VersionSkuAnalysisSnapshot:
        normalized_sku = sku_code.strip().upper()
        if not competitor_profile_version_id.strip():
            raise ValueError("competitor profile version ID cannot be empty")
        if normalized_sku not in category_bundle.authoritative_sku_codes:
            raise VersionSkuAnalysisSnapshotBuildError(
                f"SKU is outside the locked authoritative manifest: {normalized_sku}"
            )

        records = {
            module_code: tuple(
                category_bundle.modules[module_code].records_by_sku.get(
                    normalized_sku,
                    [],
                )
            )
            for module_code in COMPETITOR_PROFILE_SOURCE_MODULES
        }
        evidence_refs = _dedupe_refs(
            _evidence_ref(row)
            for module_code in COMPETITOR_PROFILE_SOURCE_MODULES
            for row in records[module_code]
        )
        module_availability = [
            _module_availability(category_bundle, module_code, records[module_code])
            for module_code in sorted(COMPETITOR_PROFILE_SOURCE_MODULES)
        ]
        limitations = sorted(
            {
                limitation
                for row in module_availability
                for limitation in _module_limitations(row)
            }
        )
        source_facts = (
            _normalized_source_record_facts(normalized_sku, records)
            if authoritative_only
            else _normalized_source_facts(normalized_sku, records)
        )
        identity_market, market_snapshot = _market_snapshots(
            category_bundle,
            normalized_sku,
            records["M07"],
        )
        product_form = _product_form_facts(
            category_bundle,
            records["M03B"],
            market_snapshot,
        )
        fact_sections = _fact_sections(records, module_availability)
        claim_value, claim_contribution, claim_limitations = _claim_snapshots(
            category_bundle,
            normalized_sku,
            records["M12C"],
            authoritative_only=authoritative_only,
        )
        purchase_reason, purchase_limitations = _purchase_reason_snapshot(
            records["M12D"],
            include_legacy_payload=not authoritative_only,
        )
        limitations = sorted(
            set(limitations) | set(claim_limitations) | set(purchase_limitations)
        )
        semantic_profiles = (
            {}
            if authoritative_only
            else {
                module_code: [
                    row.model_dump(mode="json")["facts"]
                    for row in records[module_code]
                ]
                for module_code in ("M09C", "M10C", "M11C", "M11D")
            }
        )
        source_lineage = _source_lineage(category_bundle, records)
        input_fingerprint = stable_hash(
            {
                "builder_version": SNAPSHOT_BUILDER_VERSION,
                "competitor_profile_version_id": competitor_profile_version_id,
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "sku_code": normalized_sku,
                "module_record_hashes": {
                    module_code: [row.result_hash for row in records[module_code]]
                    for module_code in sorted(records)
                },
            },
            version="competitor_profile_v1_1_sku_snapshot_input_v1",
        )
        snapshot_ref = stable_hash(
            {
                "competitor_profile_version_id": competitor_profile_version_id,
                "sku_code": normalized_sku,
                "input_fingerprint": input_fingerprint,
            },
            version="competitor_profile_v1_1_sku_snapshot_ref_v1",
        )
        payload = {
            "competitor_profile_version_id": competitor_profile_version_id,
            "project_id": category_bundle.serving_scope.project_id,
            "category_code": category_bundle.serving_scope.category_code,
            "release_scope_key": category_bundle.serving_scope.release_scope_key,
            "snapshot_ref": snapshot_ref,
            "identity_market": identity_market.model_dump(mode="json"),
            "product_form_facts": product_form.model_dump(mode="json"),
            "market_snapshot": market_snapshot.model_dump(mode="json"),
            "fact_sections": fact_sections.model_dump(mode="json"),
            "claim_value_snapshot": (
                claim_value.model_dump(mode="json") if claim_value else None
            ),
            "claim_contribution_snapshot": (
                claim_contribution.model_dump(mode="json")
                if claim_contribution
                else None
            ),
            "purchase_reason_snapshot": (
                purchase_reason.model_dump(mode="json") if purchase_reason else None
            ),
            "semantic_profiles": semantic_profiles,
            "source_facts": [row.model_dump(mode="json") for row in source_facts],
            "module_availability": [
                row.model_dump(mode="json") for row in module_availability
            ],
            "source_lineage": source_lineage,
            "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
            "limitations": limitations,
            "input_fingerprint": input_fingerprint,
        }
        if authoritative_only:
            _strip_snapshot_duplicate_payloads(payload)
            fact_sections_payload = payload.get("fact_sections")
            if isinstance(fact_sections_payload, dict):
                fact_sections_payload.update(
                    {
                        "evidence_sources": [],
                        "sections": {},
                        "sku": {},
                        "legacy_payload": {},
                    }
                )
            payload.update(
                {
                    "storage_projection_mode": "authoritative_typed",
                    "source_full_result_hash": stable_hash(
                        {
                            "builder_version": SNAPSHOT_BUILDER_VERSION,
                            "input_fingerprint": input_fingerprint,
                            "snapshot_ref": snapshot_ref,
                            "record_result_hashes": {
                                module_code: [
                                    row.result_hash for row in records[module_code]
                                ]
                                for module_code in sorted(records)
                            },
                        },
                        version=(
                            "competitor_profile_v1_1_sku_snapshot_source_authority_v1"
                        ),
                    ),
                }
            )
        return VersionSkuAnalysisSnapshot.model_validate(
            {
                **payload,
                "result_hash": stable_hash(
                    payload,
                    version="competitor_profile_v1_1_sku_snapshot_result_v1",
                ),
            }
        )

    def build_many(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        *,
        competitor_profile_version_id: str,
        sku_codes: Sequence[str] | None = None,
    ) -> list[VersionSkuAnalysisSnapshot]:
        requested = (
            category_bundle.authoritative_sku_codes
            if sku_codes is None
            else sorted({value.strip().upper() for value in sku_codes})
        )
        return [
            self.build(
                category_bundle,
                competitor_profile_version_id=competitor_profile_version_id,
                sku_code=sku_code,
            )
            for sku_code in requested
        ]


def build_authoritative_snapshot_projection(
    snapshot: VersionSkuAnalysisSnapshot,
    *,
    retained_fact_ids: Iterable[str] = (),
) -> VersionSkuAnalysisSnapshot:
    """Retain typed SKU facts and lineage without legacy/raw duplicate bags."""

    payload = snapshot.model_dump(
        mode="json",
        exclude={
            "schema_version",
            "storage_projection_mode",
            "source_full_result_hash",
            "result_hash",
        },
    )
    _strip_snapshot_duplicate_payloads(payload)
    payload["semantic_profiles"] = {}
    retained = {str(value) for value in retained_fact_ids}
    payload["source_facts"] = [
        row
        for row in payload.get("source_facts", [])
        if isinstance(row, dict) and str(row.get("fact_id")) in retained
    ]
    fact_sections = payload.get("fact_sections")
    if isinstance(fact_sections, dict):
        for key in ("evidence_sources", "sections", "sku", "legacy_payload"):
            fact_sections[key] = [] if key == "evidence_sources" else {}
    payload.update(
        {
            "storage_projection_mode": "authoritative_typed",
            "source_full_result_hash": (
                snapshot.result_hash
                if snapshot.storage_projection_mode == "full"
                else snapshot.source_full_result_hash
            ),
        }
    )
    return VersionSkuAnalysisSnapshot.model_validate(
        {
            **payload,
            "result_hash": stable_hash(
                payload,
                version="competitor_profile_v1_1_sku_snapshot_result_v1",
            ),
        }
    )


def snapshot_expected_result_hash(snapshot: VersionSkuAnalysisSnapshot) -> str:
    exclude = {"schema_version", "result_hash"}
    if snapshot.storage_projection_mode == "full":
        exclude.update({"storage_projection_mode", "source_full_result_hash"})
    return stable_hash(
        snapshot.model_dump(mode="json", exclude=exclude),
        version="competitor_profile_v1_1_sku_snapshot_result_v1",
    )


def _strip_snapshot_duplicate_payloads(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            normalized = str(key).lower()
            if normalized == "raw_details" or normalized == "legacy_payload" or (
                normalized.startswith("legacy_")
                and normalized.endswith("_payload")
            ):
                value[key] = {}
            else:
                _strip_snapshot_duplicate_payloads(child)
    elif isinstance(value, list):
        for child in value:
            _strip_snapshot_duplicate_payloads(child)


def _market_snapshots(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
    records: Sequence[UpstreamRecordSnapshot],
) -> tuple[IdentityMarketSnapshot, SkuMarketSnapshot]:
    facts = _first_facts(records)
    total_volume = _decimal(facts.get("sales_volume_total"))
    active_weeks = _int(facts.get("active_week_count"))
    weekly_volume = _decimal(
        _first_not_none(facts.get("avg_weekly_volume"), facts.get("weekly_volume"))
    )
    if weekly_volume is None and total_volume is not None and active_weeks and active_weeks > 0:
        weekly_volume = total_volume / Decimal(active_weeks)
    weighted_price = _decimal(
        _first_not_none(facts.get("price_wavg"), facts.get("weighted_price"))
    )
    sales_amount = _decimal(
        _first_not_none(facts.get("sales_amount_total"), facts.get("sales_amount"))
    )
    screen_size = (
        _decimal(facts.get("screen_size_inch"))
        if bundle.serving_scope.product_category == "TV"
        else None
    )
    identity = IdentityMarketSnapshot(
        sku_code=sku_code,
        brand_name=_known_text(
            _first_not_none(facts.get("brand_name"), facts.get("brand"))
        ),
        model_name=_known_text(facts.get("model_name")),
        product_category=bundle.serving_scope.product_category,
        screen_size_inch=screen_size,
        size_tier=_known_text(facts.get("size_segment")),
        price_band_in_size_tier=_known_text(facts.get("price_band_size")),
        weighted_price=weighted_price,
        avg_weekly_sales_volume=weekly_volume,
        total_sales_volume=total_volume,
        total_sales_amount=sales_amount,
        source="M07" if records else None,
        legacy_payload=facts,
    )
    market = SkuMarketSnapshot(
        market_window=bundle.serving_scope.market_window,
        weighted_price=weighted_price,
        avg_weekly_sales_volume=weekly_volume,
        total_sales_volume=total_volume,
        total_sales_amount=sales_amount,
        price_band_in_size_tier=_known_text(facts.get("price_band_size")),
        source="M07" if records else None,
        legacy_payload=facts,
    )
    return identity, market


def _product_form_facts(
    bundle: CompetitorProfileCategoryInputBundle,
    parameter_records: Sequence[UpstreamRecordSnapshot],
    market: SkuMarketSnapshot,
) -> ProductFormFacts:
    category = bundle.serving_scope.product_category
    if category == "TV":
        screen_size = _decimal(market.legacy_payload.get("screen_size_inch"))
        unknown = []
        size_segment = _known_text(market.legacy_payload.get("size_segment"))
        if screen_size is None and size_segment is None:
            unknown.append("tv_size_unknown")
        return ProductFormFacts(
            product_category="TV",
            screen_size_inch=screen_size,
            size_segment=size_segment,
            unknown_reason_codes=unknown,
        )

    params = _parameter_map(parameter_records)
    ac_form, ac_form_conflict = _resolve_parameter(
        params,
        ("ac_product_form", "product_form", "air_conditioner_form"),
    )
    capacity, capacity_conflict = _resolve_parameter(
        params,
        (
            "cooling_capacity_segment",
            "ac_capacity_segment",
            "cooling_capacity",
        ),
    )
    unknown = []
    if ac_form_conflict:
        unknown.append("ac_product_form_conflict")
    elif ac_form is None:
        unknown.append("ac_product_form_unknown")
    if capacity_conflict:
        unknown.append("ac_cooling_capacity_segment_conflict")
    elif capacity is None:
        unknown.append("ac_cooling_capacity_segment_unknown")
    return ProductFormFacts(
        product_category="AC",
        ac_product_form=ac_form,
        cooling_capacity_segment=capacity,
        unknown_reason_codes=sorted(unknown),
    )


def _fact_sections(
    records: Mapping[str, Sequence[UpstreamRecordSnapshot]],
    availability: Sequence[ModuleAvailabilitySnapshot],
) -> FactSectionsSnapshot:
    parameters = _parameter_items(records["M03B"])
    claims = _claim_items(records["M04C"], records["M05C"])
    battlefields = _semantic_items(
        records["M11C"],
        records["M11D"],
        kind="battlefield",
    )
    tasks = _semantic_items(records["M09C"], (), kind="task")
    audiences = _semantic_items(records["M10C"], (), kind="audience")
    claim_values = _claim_value_items(records["M12C"])
    purchase_reasons = _purchase_reason_items(records["M12D"])
    return FactSectionsSnapshot(
        parameter_items=parameters,
        claim_items=claims,
        battlefield_items=battlefields,
        task_items=tasks,
        audience_items=audiences,
        claim_value_items=claim_values,
        purchase_reason_anchors=purchase_reasons,
        evidence_sources=[
            {
                "module_code": row.module_code,
                "availability": row.availability,
                "record_count": len(records[row.module_code]),
                "evidence_ref_count": len(row.evidence_refs),
            }
            for row in availability
        ],
        missing_sections=[
            row.module_code for row in availability if row.availability == "unknown"
        ],
        sections={
            row.module_code: {
                "availability": row.availability,
                "review_required": row.review_required,
            }
            for row in availability
        },
    )


def _parameter_items(records: Sequence[UpstreamRecordSnapshot]) -> list[AnalysisItem]:
    observations: dict[str, list[tuple[Any, EvidenceRef, str]]] = defaultdict(list)
    for row in records:
        facts = row.facts
        ref = _evidence_ref(row)
        code = _known_text(facts.get("param_code"))
        value = _first_not_none(
            facts.get("normalized_value"),
            facts.get("param_value"),
            facts.get("value"),
        )
        if code and value is not None:
            observations[code].append((value, ref, f"facts.{code}"))
        for field_name in (
            "param_values_json",
            "core_picture_params_json",
            "core_gaming_params_json",
            "core_system_params_json",
            "core_eye_care_params_json",
        ):
            payload = facts.get(field_name)
            if isinstance(payload, dict):
                for nested_code in sorted(payload):
                    nested_value = _parameter_scalar(payload[nested_code])
                    observations[str(nested_code)].append(
                        (nested_value, ref, f"facts.{field_name}.{nested_code}")
                    )
    return [
        _analysis_item(code, observations[code], roles=["parameter"])
        for code in sorted(observations)
    ]


def _claim_items(
    claim_records: Sequence[UpstreamRecordSnapshot],
    realization_records: Sequence[UpstreamRecordSnapshot],
) -> list[ClaimFactItem]:
    observations: dict[str, list[tuple[Any, EvidenceRef, str]]] = defaultdict(list)
    roles: dict[str, set[str]] = defaultdict(set)
    support: dict[str, set[str]] = defaultdict(set)
    mappings = {
        "claim_codes": "expressed",
        "fact_claim_codes": "fact_supported",
        "service_claim_codes": "service_separate",
        "supported_claim_codes": "supported",
        "unsupported_claim_codes": "unsupported",
    }
    for row in claim_records:
        facts = row.facts
        ref = _evidence_ref(row)
        for field_name, role in mappings.items():
            for code in _text_values(facts.get(field_name)):
                observations[code].append((role, ref, f"facts.{field_name}"))
                roles[code].add(role)
                if role == "supported" or role == "fact_supported":
                    support[code].add("supported")
                elif role == "unsupported":
                    support[code].add("unsupported")
        code = _known_text(facts.get("claim_code"))
        status = _known_text(facts.get("claim_status"))
        if code and status:
            observations[code].append((status, ref, "facts.claim_status"))
            roles[code].add(status)
    realization_map = {
        "supported_claim_codes": ("user_supported", "supported"),
        "contradicted_claim_codes": ("user_contradicted", "contradicted"),
        "unmentioned_claim_codes": ("user_unmentioned", "unknown"),
    }
    for row in realization_records:
        facts = row.facts
        ref = _evidence_ref(row)
        for field_name, (role, status) in realization_map.items():
            for code in _text_values(facts.get(field_name)):
                observations[code].append((role, ref, f"facts.{field_name}"))
                roles[code].add(role)
                support[code].add(status)
    result = []
    for code in sorted(observations):
        statuses = support[code]
        if "contradicted" in statuses:
            support_status = "contradicted"
        elif "supported" in statuses:
            support_status = "supported"
        elif "unsupported" in statuses:
            support_status = "unsupported"
        else:
            support_status = "unknown"
        base = _analysis_item(
            code,
            observations[code],
            roles=sorted(roles[code]),
            support_status=support_status,
        )
        result.append(
            ClaimFactItem.model_validate(
                {**base.model_dump(mode="json"), "supporting_parameter_codes": []}
            )
        )
    return result


def _semantic_items(
    primary_records: Sequence[UpstreamRecordSnapshot],
    secondary_records: Sequence[UpstreamRecordSnapshot],
    *,
    kind: str,
) -> list[AnalysisItem]:
    observations: dict[str, list[tuple[Any, EvidenceRef, str]]] = defaultdict(list)
    roles: dict[str, set[str]] = defaultdict(set)
    key_maps = {
        "task": {
            "primary_user_task_code": "primary",
            "secondary_user_task_codes_json": "secondary",
            "comment_observed_task_codes_json": "user_observed",
            "latent_capability_task_codes_json": "latent",
        },
        "audience": {
            "primary_target_group_code": "primary",
            "secondary_target_group_codes_json": "secondary",
            "comment_observed_group_codes_json": "user_observed",
            "latent_group_codes_json": "latent",
        },
        "battlefield": {
            "primary_battlefield_code": "primary",
            "secondary_battlefield_codes_json": "secondary",
            "opportunity_battlefield_codes_json": "opportunity",
            "drag_factor_battlefield_codes_json": "drag",
        },
    }
    for row in primary_records:
        facts = row.facts
        ref = _evidence_ref(row)
        for field_name, role in key_maps[kind].items():
            for code in _text_values(facts.get(field_name)):
                observations[code].append((role, ref, f"facts.{field_name}"))
                roles[code].add(role)
    for row in secondary_records:
        facts = row.facts
        ref = _evidence_ref(row)
        code = _known_text(facts.get("dimension_code"))
        role = _known_text(facts.get("allocation_role"))
        if code and role:
            observations[code].append((role, ref, "facts.allocation_role"))
            roles[code].add(role)
    return [
        _analysis_item(code, observations[code], roles=sorted(roles[code]))
        for code in sorted(observations)
    ]


def _claim_value_items(
    records: Sequence[UpstreamRecordSnapshot],
) -> list[ClaimValueFactItem]:
    result = []
    for row in records:
        facts = row.facts
        code = _known_text(facts.get("claim_code"))
        if not code:
            continue
        ref = _evidence_ref(row)
        role = _known_text(
            _first_not_none(
                facts.get("claim_value_role"),
                facts.get("claim_role"),
                facts.get("allocation_role"),
            )
        )
        value = role or "role_unknown"
        base = _analysis_item(
            code,
            [(value, ref, "facts.claim_value_role")],
            roles=[role] if role else [],
        )
        result.append(
            ClaimValueFactItem.model_validate(
                {
                    **base.model_dump(mode="json"),
                    "value_role": role,
                    "market_summary": _claim_market_summary(facts),
                    "user_realization": _claim_user_realization(facts),
                }
            )
        )
    return sorted(result, key=lambda row: (row.code, row.fact_id))


def _purchase_reason_items(
    records: Sequence[UpstreamRecordSnapshot],
) -> list[PurchaseReasonAnchorFact]:
    result = []
    for row in records:
        facts = row.facts
        ref = _evidence_ref(row)
        for field_name, default_role in _ANCHOR_LIST_ROLES.items():
            for index, raw in enumerate(_as_list(facts.get(field_name))):
                payload = raw if isinstance(raw, dict) else {"anchor_cn": raw}
                code = _known_text(
                    _first_not_none(
                        payload.get("anchor_code"),
                        payload.get("anchor_cn"),
                        payload.get("anchor_name"),
                    )
                )
                if not code:
                    continue
                role = _known_text(payload.get("role")) or default_role
                value = _first_not_none(
                    payload.get("anchor_cn"),
                    payload.get("anchor_name"),
                    code,
                )
                base = _analysis_item(
                    code,
                    [(value, ref, f"facts.{field_name}[{index}]")],
                    roles=[role],
                )
                result.append(
                    PurchaseReasonAnchorFact.model_validate(
                        {
                            **base.model_dump(mode="json"),
                            "anchor_role": role,
                            "establishment": {
                                key: payload[key]
                                for key in (
                                    "establishment_score",
                                    "establishment_status",
                                    "core_eligible",
                                )
                                if key in payload
                            },
                            "user_validation": {
                                key: payload[key]
                                for key in ("user_validation_status", "evidence_strength")
                                if key in payload
                            },
                            "purchase_pressure": {
                                key: payload[key]
                                for key in ("pressure_level", "pressure_summary_cn")
                                if key in payload
                            },
                        }
                    )
                )
    return sorted(result, key=lambda row: (row.code, row.anchor_role, row.fact_id))


def _analysis_item(
    code: str,
    observations: Sequence[tuple[Any, EvidenceRef, str]],
    *,
    roles: list[str],
    support_status: str = "unknown",
) -> AnalysisItem:
    ordered = sorted(
        observations,
        key=lambda row: (
            row[1].module_code,
            row[1].record_id,
            row[2],
            _canonical_json(row[0]),
        ),
    )
    refs = _dedupe_refs(row[1] for row in ordered)
    values = [_typed_value(row[0], row[2], [row[1]]) for row in ordered]
    payload = {
        "code": code,
        "roles": sorted(set(roles)),
        "values": [row.model_dump(mode="json") for row in values],
        "support_status": support_status,
        "evidence_refs": [row.model_dump(mode="json") for row in refs],
    }
    return AnalysisItem(
        fact_id=stable_hash(payload, version="competitor_profile_v1_1_fact_item_v1"),
        **payload,
    )


def _claim_snapshots(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
    records: Sequence[UpstreamRecordSnapshot],
    *,
    authoritative_only: bool = False,
) -> tuple[
    ClaimValueSnapshot | None,
    ClaimContributionSnapshot | None,
    list[str],
]:
    if not records:
        return None, None, []
    rows = []
    for record in records:
        source = (
            dict(record.facts)
            if authoritative_only
            else record.model_dump(mode="json")["facts"]
        )
        projected = _project_m12c_row(source)
        if authoritative_only:
            projected["raw_details"] = {}
            _strip_snapshot_duplicate_payloads(projected)
            projected = _json_compatible(projected)
        rows.append(projected)
    claim_values = [
        _claim_value_record(row)
        for row in rows
        if _known_text(row.get("claim_code"))
    ]
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        authoritative_attribution = row.get("authoritative_attribution")
        confidence = _decimal(row.get("attribution_confidence"))
        if confidence is None and isinstance(authoritative_attribution, Mapping):
            confidence = _decimal(authoritative_attribution.get("confidence"))
        if _known_text(row.get("claim_code")) and confidence is not None:
            grouped[
                (
                    _known_text(row.get("context_type")) or "unknown",
                    _known_text(row.get("context_code")) or "unknown",
                    _known_text(row.get("brand_name")) or "",
                    _known_text(row.get("model_name")) or "",
                    _known_text(row.get("price_band_group")) or "unknown",
                    _known_text(row.get("size_tier")) or "unknown",
                )
            ].append(row)
    attributions = [
        _claim_attribution(sku_code, key, grouped[key]) for key in sorted(grouped)
    ]
    role_counts = Counter(
        _known_text(row.get("claim_value_role")) or "unknown" for row in rows
    )
    analysis_population = _known_text(rows[0].get("analysis_population")) or (
        bundle.serving_scope.analysis_population
    )
    market_window = _known_text(rows[0].get("market_window")) or (
        bundle.serving_scope.market_window
    )
    method_note = "由锁定的 M12C published/current SKU claim-value records 标准化生成。"
    claim_value = ClaimValueSnapshot(
        sku_code=sku_code,
        analysis_population=analysis_population,
        market_window=market_window,
        filters={
            "contexts": sorted(
                {
                    f"{_known_text(row.get('context_type')) or 'unknown'}:"
                    f"{_known_text(row.get('context_code')) or 'unknown'}"
                    for row in rows
                }
            )
        },
        role_counts=dict(sorted(role_counts.items())),
        attributions=attributions,
        claim_values=claim_values,
        sku_level_claim_values=_sku_level_claim_values(rows),
        method_note_cn=method_note,
        legacy_payload={"record_count": len(rows)},
    )
    limitations = (
        ["m12c_attribution_confidence_missing"]
        if claim_values and not attributions
        else []
    )
    contribution = (
        None
        if limitations
        else ClaimContributionSnapshot(
            sku_code=sku_code,
            analysis_population=analysis_population,
            market_window=market_window,
            attribution_count=len(attributions),
            attributions=attributions,
            filters=claim_value.filters,
            method_note_cn=method_note,
            legacy_payload={"record_count": len(rows)},
        )
    )
    return claim_value, contribution, limitations


def _project_m12c_row(row: dict[str, Any]) -> dict[str, Any]:
    """Promote the frozen M12C row into the G29 authoritative typed shape."""

    supporting = (
        dict(row.get("supporting_dimensions_json") or {})
        if isinstance(row.get("supporting_dimensions_json"), Mapping)
        else {}
    )
    scorecard = (
        dict(supporting.get("scorecard") or {})
        if isinstance(supporting.get("scorecard"), Mapping)
        else {}
    )
    pool_source = _first_mapping(
        row.get("pool_effect"),
        supporting.get("pool_effect"),
    )
    pool_effect = {
        key: _first_not_none(pool_source.get(key), row.get(key))
        for key in (
            "pool_claim_price_delta_abs",
            "pool_claim_weekly_sales_delta_abs",
            "pool_claim_weekly_sales_amount_delta_abs",
            "with_claim_sku_count",
            "without_claim_sku_count",
            "effect_confidence",
        )
    }
    role = _known_text(row.get("claim_value_role")) or "sample_insufficient"
    pool_price_delta = _decimal(pool_effect.get("pool_claim_price_delta_abs"))
    business_claim_type = _known_text(
        _first_not_none(
            row.get("business_claim_type"),
            supporting.get("business_claim_type"),
        )
    ) or _m12c_business_claim_type(role, pool_price_delta)
    business_claim_type_cn = _known_text(
        _first_not_none(
            row.get("business_claim_type_cn"),
            supporting.get("business_claim_type_cn"),
        )
    ) or _m12c_business_claim_type_cn(business_claim_type)
    business_definition = _known_text(
        _first_not_none(
            row.get("business_claim_type_definition_cn"),
            supporting.get("business_claim_type_definition_cn"),
        )
    ) or _m12c_business_claim_type_meaning_cn(business_claim_type)
    evidence_ids = _text_values(
        _first_not_none(row.get("evidence_ids"), row.get("evidence_ids_json"))
    )
    claim_strength = _decimal(row.get("claim_evidence_strength"))
    explicit_target_has_claim = _first_not_none(
        row.get("target_has_claim"),
        supporting.get("target_has_claim"),
    )
    target_has_claim = (
        explicit_target_has_claim
        if isinstance(explicit_target_has_claim, bool)
        else bool(evidence_ids and claim_strength is not None and claim_strength > 0)
    )
    claim_source_type = _known_text(
        _first_not_none(
            row.get("claim_source_type"),
            supporting.get("claim_source_type"),
        )
    ) or _m12c_claim_source_type(
        target_has_claim=target_has_claim,
        business_claim_type_cn=business_claim_type_cn,
    )
    claim_value_score = _decimal(
        _first_not_none(
            row.get("claim_value_score"),
            supporting.get("claim_value_score"),
            scorecard.get("total_score"),
        )
    )
    business_value_label = _known_text(
        _first_not_none(
            row.get("business_value_label"),
            supporting.get("business_value_label"),
        )
    ) or _m12c_business_value_label(role, pool_price_delta)
    business_value_meaning = _known_text(
        _first_not_none(
            row.get("business_value_meaning_cn"),
            supporting.get("business_value_meaning_cn"),
        )
    ) or _m12c_business_value_meaning_cn(role, pool_price_delta)
    parameter_competitiveness = _first_mapping(
        row.get("parameter_competitiveness"),
        supporting.get("parameter_competitiveness"),
    )
    market_source = _first_mapping(
        row.get("market_position"),
        supporting.get("market_position"),
    )
    market_type = _known_text(
        _first_not_none(
            market_source.get("type"),
            row.get("market_position_type"),
            supporting.get("market_position_type"),
            scorecard.get("market_position_type"),
        )
    )
    market_summary = _known_text(
        _first_not_none(
            market_source.get("summary_cn"),
            row.get("market_position_cn"),
            supporting.get("market_position_cn"),
        )
    )
    market_position = (
        {"type": market_type, "summary_cn": market_summary}
        if market_type and market_summary
        else None
    )
    price_explained = _decimal(
        _first_not_none(
            row.get("sku_excess_price_explained_abs"),
            row.get("estimated_price_premium_abs"),
        )
    )
    sales_explained = _decimal(
        _first_not_none(
            row.get("sku_excess_weekly_sales_explained_abs"),
            row.get("estimated_weekly_sales_lift_abs"),
        )
    )
    amount_explained = _decimal(
        _first_not_none(
            row.get("sku_excess_weekly_sales_amount_explained_abs"),
            row.get("estimated_weekly_sales_amount_lift_abs"),
        )
    )
    contribution_share = _decimal(row.get("contribution_share_in_sku"))
    sku_excess = {
        "sku_excess_price_explained_abs": price_explained,
        "sku_excess_weekly_sales_explained_abs": sales_explained,
        "sku_excess_weekly_sales_amount_explained_abs": amount_explained,
        "contribution_share_in_sku": contribution_share,
    }
    attribution_source = _first_mapping(
        row.get("claim_contribution_attribution"),
        supporting.get("claim_contribution_attribution"),
    )
    return {
        "claim_code": row.get("claim_code"),
        "claim_name": row.get("claim_name"),
        "sku_code": row.get("sku_code"),
        "brand_name": row.get("brand_name"),
        "model_name": row.get("model_name"),
        "claim_dimension": row.get("claim_dimension"),
        "claim_source_type": claim_source_type,
        "claim_source_type_cn": _m12c_claim_source_type_cn(claim_source_type),
        "claim_value_role": role,
        "claim_value_score": claim_value_score,
        "business_claim_type": business_claim_type,
        "business_claim_type_cn": business_claim_type_cn,
        "business_claim_type_definition_cn": business_definition,
        "business_value_label": business_value_label,
        "business_value_meaning_cn": business_value_meaning,
        "context_code": row.get("context_code"),
        "context_name": row.get("context_name"),
        "context_type": row.get("context_type"),
        "target_has_claim": target_has_claim,
        "attribution_confidence": row.get("attribution_confidence"),
        "evidence_id_count": len(evidence_ids),
        "evidence_strength": {
            "claim": row.get("claim_evidence_strength"),
            "param": row.get("param_support_strength"),
            "comment": row.get("comment_support_strength"),
            "semantic": row.get("semantic_support_strength"),
        },
        "supporting_dimensions": supporting,
        "estimated_contribution": {
            "price_premium_abs": _json_decimal(price_explained),
            "weekly_sales_lift_abs": _json_decimal(sales_explained),
            "weekly_sales_amount_lift_abs": _json_decimal(amount_explained),
            "contribution_share_in_sku": _json_decimal(contribution_share),
        },
        "pool_effect": pool_effect,
        "parameter_competitiveness": parameter_competitiveness,
        "market_position": market_position,
        "sku_excess_explanation": sku_excess,
        "sku_excess_price_explained_abs": price_explained,
        "sku_excess_weekly_sales_explained_abs": sales_explained,
        "price_band_group": row.get("price_band_group"),
        "size_tier": row.get("size_tier"),
        "scorecard": scorecard,
        "quality_flags": _text_values(row.get("quality_flags_json")),
        "reason_cn": row.get("reason_cn"),
        "contribution_share_in_sku": contribution_share,
        "estimated_price_premium_abs": price_explained,
        "estimated_weekly_sales_lift_abs": sales_explained,
        "estimated_weekly_sales_amount_lift_abs": amount_explained,
        "pool_claim_price_delta_abs": pool_effect["pool_claim_price_delta_abs"],
        "pool_claim_weekly_sales_delta_abs": pool_effect[
            "pool_claim_weekly_sales_delta_abs"
        ],
        "pool_claim_weekly_sales_amount_delta_abs": pool_effect[
            "pool_claim_weekly_sales_amount_delta_abs"
        ],
        "attribution_baseline": _first_mapping(
            row.get("baseline"),
            attribution_source.get("baseline"),
        ),
        "attribution_sku_observed": _first_mapping(
            row.get("sku_observed"),
            attribution_source.get("sku_observed"),
        ),
        "attribution_sku_gap_vs_baseline": _first_mapping(
            row.get("sku_gap_vs_baseline"),
            attribution_source.get("sku_gap_vs_baseline"),
        ),
        "attribution_summary_cn": _first_not_none(
            row.get("attribution_summary_cn"),
            attribution_source.get("attribution_summary_cn"),
        ),
        "authoritative_attribution": attribution_source,
        "raw_details": row,
    }


def _claim_value_record(row: dict[str, Any]) -> ClaimValueRecord:
    fields = (
        "claim_code",
        "claim_name",
        "sku_code",
        "brand_name",
        "model_name",
        "claim_dimension",
        "claim_source_type",
        "claim_source_type_cn",
        "claim_value_role",
        "claim_value_score",
        "business_claim_type",
        "business_claim_type_cn",
        "business_claim_type_definition_cn",
        "business_value_label",
        "business_value_meaning_cn",
        "context_code",
        "context_name",
        "context_type",
        "target_has_claim",
        "attribution_confidence",
        "evidence_id_count",
        "pool_effect",
        "parameter_competitiveness",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
        "price_band_group",
        "size_tier",
        "reason_cn",
    )
    payload = {key: row[key] for key in fields if key in row}
    payload.update(
        {
            "evidence_strength": row.get("evidence_strength") or {},
            "supporting_dimensions": row.get("supporting_dimensions") or {},
            "estimated_contribution": row.get("estimated_contribution") or {},
            "scorecard": row.get("scorecard") or {},
            "quality_flags": _text_values(row.get("quality_flags")),
            "raw_details": row.get("raw_details") or {},
        }
    )
    return ClaimValueRecord.model_validate(payload)


def _claim_contribution_record(row: dict[str, Any]) -> ClaimContributionRecord:
    fields = (
        "claim_code",
        "claim_name",
        "sku_code",
        "brand_name",
        "model_name",
        "claim_value_role",
        "claim_value_score",
        "business_claim_type",
        "business_claim_type_cn",
        "business_claim_type_definition_cn",
        "business_value_label",
        "business_value_meaning_cn",
        "attribution_confidence",
        "contribution_share_in_sku",
        "estimated_price_premium_abs",
        "estimated_weekly_sales_lift_abs",
        "estimated_weekly_sales_amount_lift_abs",
        "pool_claim_price_delta_abs",
        "pool_claim_weekly_sales_delta_abs",
        "pool_claim_weekly_sales_amount_delta_abs",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
        "reason_cn",
    )
    return ClaimContributionRecord.model_validate(
        {
            **{key: row[key] for key in fields if key in row},
            "scorecard": row.get("scorecard") or {},
            "raw_details": row.get("raw_details") or {},
        }
    )


def _claim_attribution(
    sku_code: str,
    key: tuple[str, ...],
    rows: Sequence[dict[str, Any]],
) -> ClaimAttributionRecord:
    context_type, context_code, brand, model, price_band, size_tier = key
    authoritative_sources = {
        _canonical_json(source): source
        for source in (
            row.get("authoritative_attribution") for row in rows
        )
        if isinstance(source, Mapping) and source
    }
    if len(authoritative_sources) > 1:
        raise VersionSkuAnalysisSnapshotBuildError(
            f"M12C attribution conflicts in {context_type}:{context_code}"
        )
    source = next(iter(authoritative_sources.values()), None)
    fallback_rows = {
        code: row
        for row in rows
        if (code := _known_text(row.get("claim_code")))
    }
    if source is not None:
        positive = _authoritative_attribution_claims(
            source.get("positive_claims"),
            fallback_rows,
        )
        drag = _authoritative_attribution_claims(
            source.get("drag_claims"),
            fallback_rows,
        )
        opportunity = _authoritative_attribution_claims(
            source.get("opportunity_claims"),
            fallback_rows,
        )
    else:
        positive = []
        drag = []
        opportunity = []
        for row in rows:
            contribution = _claim_contribution_record(row)
            role = _known_text(row.get("claim_value_role")) or "unknown"
            if role in _OPPORTUNITY_CLAIM_ROLES:
                opportunity.append(contribution)
            elif "drag" in role:
                drag.append(contribution)
            elif role in _POSITIVE_CLAIM_ROLES:
                positive.append(contribution)
    confidences = [
        value
        for value in (_decimal(row.get("attribution_confidence")) for row in rows)
        if value is not None
    ]
    source_confidence = (
        _decimal(source.get("confidence")) if source is not None else None
    )
    confidence = (
        source_confidence if source_confidence is not None else min(confidences)
    )
    return ClaimAttributionRecord(
        sku_code=sku_code,
        brand_name=(
            _known_text(source.get("brand_name")) if source is not None else None
        )
        or brand
        or None,
        model_name=(
            _known_text(source.get("model_name")) if source is not None else None
        )
        or model
        or None,
        price_band_group=(
            _known_text(source.get("price_band_group"))
            if source is not None
            else None
        )
        or price_band,
        size_tier=(
            _known_text(source.get("size_tier")) if source is not None else None
        )
        or size_tier,
        context_code=(
            _known_text(source.get("context_code")) if source is not None else None
        )
        or context_code,
        context_name=(
            _known_text(source.get("context_name")) if source is not None else None
        )
        or _known_text(rows[0].get("context_name")),
        context_type=(
            _known_text(source.get("context_type")) if source is not None else None
        )
        or context_type,
        confidence=confidence,
        baseline=(
            _first_mapping(source.get("baseline"))
            if source is not None
            else _first_nonempty_mapping(rows, "attribution_baseline")
        ),
        sku_observed=(
            _first_mapping(source.get("sku_observed"))
            if source is not None
            else _first_nonempty_mapping(rows, "attribution_sku_observed")
        ),
        sku_gap_vs_baseline=(
            _first_mapping(source.get("sku_gap_vs_baseline"))
            if source is not None
            else _first_nonempty_mapping(rows, "attribution_sku_gap_vs_baseline")
        ),
        positive_claims=positive,
        drag_claims=drag,
        opportunity_claims=opportunity,
        attribution_summary_cn=(
            _known_text(source.get("attribution_summary_cn"))
            if source is not None
            else next(
                (
                    text
                    for text in (
                        _known_text(row.get("attribution_summary_cn"))
                        for row in rows
                    )
                    if text
                ),
                None,
            )
        ),
        raw_details={
            "record_count": len(rows),
            "source": "published_m12c_attribution" if source else "claim_row_fallback",
        },
    )


def _authoritative_attribution_claims(
    raw_claims: Any,
    fallback_rows: Mapping[str, dict[str, Any]],
) -> list[ClaimContributionRecord]:
    result = []
    for raw in _as_list(raw_claims):
        payload = dict(raw) if isinstance(raw, Mapping) else {"claim_code": raw}
        claim_code = _known_text(payload.get("claim_code"))
        if not claim_code:
            raise VersionSkuAnalysisSnapshotBuildError(
                "M12C authoritative attribution claim has no claim_code"
            )
        fallback = fallback_rows.get(claim_code)
        base = (
            _claim_contribution_record(fallback).model_dump(mode="python")
            if fallback is not None
            else {"claim_code": claim_code}
        )
        allowed = set(ClaimContributionRecord.model_fields)
        for field_name in allowed:
            if field_name in payload and field_name != "raw_details":
                base[field_name] = payload[field_name]
        pool_effect = _first_mapping(payload.get("pool_effect"))
        for target_field, source_field in (
            ("pool_claim_price_delta_abs", "pool_claim_price_delta_abs"),
            ("pool_claim_weekly_sales_delta_abs", "pool_claim_weekly_sales_delta_abs"),
            (
                "pool_claim_weekly_sales_amount_delta_abs",
                "pool_claim_weekly_sales_amount_delta_abs",
            ),
        ):
            if source_field in pool_effect:
                base[target_field] = pool_effect[source_field]
        estimated = _first_mapping(payload.get("estimated_contribution"))
        for target_field, source_field in (
            ("estimated_price_premium_abs", "price_premium_abs"),
            ("estimated_weekly_sales_lift_abs", "weekly_sales_lift_abs"),
            (
                "estimated_weekly_sales_amount_lift_abs",
                "weekly_sales_amount_lift_abs",
            ),
            ("contribution_share_in_sku", "contribution_share_in_sku"),
        ):
            if source_field in estimated:
                base[target_field] = estimated[source_field]
        base["claim_code"] = claim_code
        base["raw_details"] = payload
        result.append(ClaimContributionRecord.model_validate(base))
    return result


def _sku_level_claim_values(
    rows: Sequence[dict[str, Any]],
) -> list[SkuLevelClaimValueRecord]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        code = _known_text(row.get("claim_code"))
        if code:
            grouped[code].append(row)
    result = []
    for code in sorted(grouped):
        values = grouped[code]
        preferred = [
            row for row in values if _known_text(row.get("context_type")) == "battlefield"
        ] or values
        ordered = sorted(
            preferred,
            key=lambda row: (
                -_m12c_row_strength(row),
                _canonical_json(row.get("raw_details") or {}),
            ),
        )
        first = ordered[0]
        business_type_cn = min(
            (
                _known_text(row.get("business_claim_type_cn")) or "未分类卖点"
                for row in ordered
            ),
            key=lambda value: (_M12C_BUSINESS_TYPE_PRIORITY.get(value, 99), value),
        )
        business_type = next(
            (
                _known_text(row.get("business_claim_type"))
                for row in ordered
                if _known_text(row.get("business_claim_type_cn"))
                == business_type_cn
                and _known_text(row.get("business_claim_type"))
            ),
            "sample_insufficient_claim",
        )
        target_has_claim = any(row.get("target_has_claim") is True for row in ordered)
        source_type = _best_claim_source_type(
            ordered,
            target_has_claim=target_has_claim,
            business_claim_type_cn=business_type_cn,
        )
        price_total = sum(
            (
                _decimal(
                    (row.get("estimated_contribution") or {}).get(
                        "price_premium_abs"
                    )
                )
                or Decimal("0")
            )
            for row in ordered
        )
        sales_total = sum(
            (
                _decimal(
                    (row.get("estimated_contribution") or {}).get(
                        "weekly_sales_lift_abs"
                    )
                )
                or Decimal("0")
            )
            for row in ordered
        )
        amount_total = sum(
            (
                _decimal(
                    (row.get("estimated_contribution") or {}).get(
                        "weekly_sales_amount_lift_abs"
                    )
                )
                or Decimal("0")
            )
            for row in ordered
        )
        contribution_share = sum(
            (_decimal(row.get("contribution_share_in_sku")) or Decimal("0"))
            for row in ordered
        )
        market_position = next(
            (
                row.get("market_position")
                for row in ordered
                if isinstance(row.get("market_position"), Mapping)
            ),
            None,
        )
        result.append(
            SkuLevelClaimValueRecord(
                claim_code=code,
                claim_name=_known_text(first.get("claim_name")),
                claim_value_score=_average_decimal(
                    [
                        value
                        for value in (
                            _decimal(row.get("claim_value_score")) for row in ordered
                        )
                        if value is not None
                    ]
                ),
                claim_source_type=source_type,
                claim_source_type_cn=_m12c_claim_source_type_cn(source_type),
                business_claim_type=business_type,
                business_claim_type_cn=business_type_cn,
                business_claim_type_definition_cn=(
                    _known_text(first.get("business_claim_type_definition_cn"))
                    or _m12c_business_claim_type_meaning_cn(business_type)
                ),
                business_value_label=_known_text(first.get("business_value_label")),
                business_value_meaning_cn=_known_text(
                    first.get("business_value_meaning_cn")
                ),
                target_has_claim=target_has_claim,
                main_contexts=sorted(
                    {
                        _known_text(row.get("context_name"))
                        or (
                            f"{_known_text(row.get('context_type')) or 'unknown'}:"
                            f"{_known_text(row.get('context_code')) or 'unknown'}"
                        )
                        for row in ordered
                    }
                ),
                context_values=[
                    _claim_value_record(row).model_dump(
                        mode="json",
                        exclude={"raw_details"},
                    )
                    for row in ordered
                ],
                parameter_competitiveness=_best_parameter_competitiveness(
                    ordered
                ),
                sku_level_user_payment_value_abs=price_total,
                sku_level_weekly_sales_lift_abs=sales_total,
                sku_level_weekly_sales_amount_lift_abs=amount_total,
                market_position=market_position,
                sku_excess_explanation={
                    "contribution_share_in_sku": contribution_share,
                    "sku_excess_price_explained_abs": price_total,
                    "sku_excess_weekly_sales_explained_abs": sales_total,
                    "sku_excess_weekly_sales_amount_explained_abs": amount_total,
                },
                sku_excess_price_explained_abs=price_total,
                sku_excess_weekly_sales_explained_abs=sales_total,
                evidence_summary_cn=_m12c_evidence_summary(ordered),
                raw_details={"context_count": len(values)},
            )
        )
    return result


def _purchase_reason_snapshot(
    records: Sequence[UpstreamRecordSnapshot],
    *,
    include_legacy_payload: bool = True,
) -> tuple[PurchaseReasonSnapshot | None, list[str]]:
    if not records:
        return None, []
    facts = (
        records[0].model_dump(mode="json")["facts"]
        if include_legacy_payload
        else records[0].facts
    )
    confidence = _decimal(facts.get("profile_confidence"))
    status = _known_text(facts.get("status"))
    raw_anchors = []
    for field_name, default_role in _ANCHOR_LIST_ROLES.items():
        for raw in _as_list(facts.get(field_name)):
            payload = raw if isinstance(raw, dict) else {"anchor_cn": raw}
            raw_anchors.append((payload, default_role))
    if confidence is None or status is None:
        return None, ["m12d_typed_purchase_reason_incomplete"]
    anchors = []
    pressure_reasons = []
    incomplete_anchor_count = 0
    for payload, default_role in raw_anchors:
        anchor = _parse_m12d_anchor(
            payload,
            default_role,
            include_raw_details=include_legacy_payload,
        )
        if anchor is None:
            incomplete_anchor_count += 1
            continue
        anchors.append(anchor)
        if anchor.pressure_level not in {"unassessed", "none"}:
            pressure_reasons.append(
                PurchasePressureReasonRecord(
                    anchor_cn=anchor.anchor_cn,
                    pressure_level=anchor.pressure_level,
                    pressure_summary_cn=anchor.pressure_summary_cn,
                    raw_details=payload if include_legacy_payload else {},
                )
            )
    by_role: dict[str, list[str]] = defaultdict(list)
    for row in anchors:
        by_role[row.role].append(row.anchor_cn)
    input_status = facts.get("input_status_json") or {}
    return (
        PurchaseReasonSnapshot(
            found=bool(anchors),
            comparison_mode=(
                _known_text(input_status.get("comparison_mode"))
                if isinstance(input_status, dict)
                else None
            )
            or "published_profile",
            consumption_state=status,
            profile_confidence=confidence,
            anchors=sorted(anchors, key=lambda row: (row.role, row.anchor_cn)),
            core_reasons_cn=_reason_texts(facts.get("core_reasons_json")),
            established_reasons_cn=sorted(set(by_role["established"])),
            proposition_reasons_cn=sorted(set(by_role["proposition"])),
            supporting_reasons_cn=sorted(set(by_role["supporting"])),
            weak_expression_reasons_cn=sorted(set(by_role["weak_expression"])),
            risk_drag_reasons_cn=sorted(set(by_role["risk_drag"])),
            purchase_pressure_reasons=sorted(
                pressure_reasons,
                key=lambda row: row.anchor_cn,
            ),
            legacy_payload=facts if include_legacy_payload else {},
        ),
        (
            ["m12d_typed_purchase_reason_incomplete"]
            if incomplete_anchor_count
            else []
        ),
    )


def _m12d_has_incomplete_typed_anchor(
    records: Sequence[UpstreamRecordSnapshot],
) -> bool:
    if not records:
        return False
    facts = records[0].facts
    if _decimal(facts.get("profile_confidence")) is None or not _known_text(
        facts.get("status")
    ):
        return True
    for field_name, default_role in _ANCHOR_LIST_ROLES.items():
        for raw in _as_list(facts.get(field_name)):
            payload = raw if isinstance(raw, dict) else {"anchor_cn": raw}
            if _parse_m12d_anchor(payload, default_role) is None:
                return True
    return False


def _parse_m12d_anchor(
    payload: Mapping[str, Any],
    default_role: str,
    *,
    include_raw_details: bool = True,
) -> PurchaseReasonAnchorRecord | None:
    required = {
        "core_eligible",
        "establishment_score",
        "establishment_status",
        "evidence_strength",
        "user_validation_status",
        "pressure_level",
    }
    if not (
        required.issubset(payload)
        and isinstance(payload.get("core_eligible"), bool)
    ):
        return None
    anchor_cn = _known_text(
        _first_not_none(
            payload.get("anchor_cn"),
            payload.get("anchor_name"),
            payload.get("anchor_code"),
        )
    )
    if not anchor_cn:
        return None
    try:
        return PurchaseReasonAnchorRecord.model_validate(
            {
                **{
                    key: payload.get(key)
                    for key in (
                        "establishment_score",
                        "establishment_status",
                        "evidence_strength",
                        "user_validation_status",
                        "support_summary_cn",
                        "weakness_summary_cn",
                        "pressure_level",
                        "pressure_summary_cn",
                    )
                },
                "anchor_cn": anchor_cn,
                "role": _known_text(payload.get("role")) or default_role,
                "core_eligible": payload["core_eligible"],
                "evidence_domains": _text_values(payload.get("evidence_domains")),
                "raw_details": dict(payload) if include_raw_details else {},
            }
        )
    except ValueError:
        return None


def _module_availability(
    bundle: CompetitorProfileCategoryInputBundle,
    module_code: str,
    records: Sequence[UpstreamRecordSnapshot],
) -> ModuleAvailabilitySnapshot:
    authority = bundle.modules[module_code].authority
    refs = _dedupe_refs(_evidence_ref(row) for row in records)
    review_codes, conflict_codes = _quality_codes(records)
    if (
        module_code in _SINGLE_RECORD_SOURCE_MODULES
        and _records_have_conflicting_known_values(records)
    ):
        conflict_codes.append(f"{module_code.lower()}_source_value_conflict")
    if module_code == "M12D" and _m12d_has_incomplete_typed_anchor(records):
        review_codes.append("m12d_typed_purchase_reason_incomplete")
    if not records:
        availability = "unknown"
    elif conflict_codes:
        availability = "conflict"
    elif review_codes:
        availability = "partial"
    else:
        availability = "available"
    review_items = [
        ReviewItem(
            review_code=code,
            reason_cn=f"{module_code} 上游记录标记为需复核或存在冲突：{code}",
            evidence_refs=refs,
        )
        for code in sorted(set(review_codes) | set(conflict_codes))
    ]
    return ModuleAvailabilitySnapshot(
        module_code=module_code,
        availability=availability,
        authority=authority.model_dump(mode="json"),
        source_lineage={
            "record_ids": [row.record_id for row in records],
            "record_result_hashes": [row.result_hash for row in records],
            "source_batch_ids": sorted({row.source_batch_id for row in records}),
        },
        review_required=bool(review_items),
        review_items=review_items,
        evidence_refs=refs,
    )


def _module_limitations(row: ModuleAvailabilitySnapshot) -> list[str]:
    if row.availability == "unknown":
        return [f"{row.module_code.lower()}_sku_not_covered_by_locked_authority"]
    if row.availability == "conflict":
        return [f"{row.module_code.lower()}_source_conflict"]
    if row.availability == "partial":
        return [f"{row.module_code.lower()}_review_required"]
    return []


def _normalized_source_record_facts(
    sku_code: str,
    records: Mapping[str, Sequence[UpstreamRecordSnapshot]],
) -> list[NormalizedSourceFact]:
    """Represent source authority once per record without copying its raw JSON tree."""

    result: list[NormalizedSourceFact] = []
    source_path = "record_result_hash"
    for module_code in sorted(records):
        for record in records[module_code]:
            ref = _evidence_ref(record)
            raw_value = record.result_hash
            occurrence_key = f"{record.record_id}:{source_path}#0"
            typed = _typed_value(raw_value, source_path, [ref])
            occurrence = NormalizedSourceOccurrence(
                occurrence_key=occurrence_key,
                ordinal=0,
                raw_value=raw_value,
                typed_value=typed,
            )
            entity_key = f"{sku_code}:{record.record_id}"
            hash_payload = [
                {"occurrence_key": occurrence_key, "raw_value": raw_value}
            ]
            fact_payload = {
                "entity_key": entity_key,
                "source_atom": module_code,
                "source_path": source_path,
                "occurrences": hash_payload,
                "record_result_hashes": [record.result_hash],
            }
            result.append(
                NormalizedSourceFact(
                    fact_id=stable_hash(
                        fact_payload,
                        version=(
                            "competitor_profile_v1_1_normalized_source_fact_v1"
                        ),
                    ),
                    code=f"{module_code}.{source_path}",
                    roles=["normalized_upstream_source"],
                    values=[typed],
                    support_status="unknown",
                    confidence=ref.confidence,
                    evidence_refs=[ref],
                    entity_key=entity_key,
                    source_atom=module_code,
                    source_path=source_path,
                    normalized_target_path=(
                        f"sku_snapshots[{sku_code}].source_facts["
                        f"{entity_key}.{module_code}.{source_path}]"
                    ),
                    source_occurrences=[occurrence],
                    occurrence_count=1,
                    resolved_value=typed,
                    source_value_hash=hashlib.sha256(
                        _canonical_json(hash_payload).encode("utf-8")
                    ).hexdigest(),
                )
            )
    return sorted(
        result,
        key=lambda row: (row.source_atom, row.entity_key, row.fact_id),
    )


def _normalized_source_facts(
    sku_code: str,
    records: Mapping[str, Sequence[UpstreamRecordSnapshot]],
) -> list[NormalizedSourceFact]:
    grouped: dict[
        tuple[str, str, str],
        list[tuple[UpstreamRecordSnapshot, Any, EvidenceRef]],
    ] = defaultdict(list)
    for module_code in sorted(records):
        for record in records[module_code]:
            facts = record.model_dump(mode="json")["facts"]
            ref = _evidence_ref(record)
            entity_key = _source_fact_entity_key(sku_code, module_code, facts, record)
            for source_path, raw_value in _iter_json_leaves(facts, prefix="facts"):
                grouped[(module_code, entity_key, source_path)].append(
                    (record, raw_value, ref)
                )
    result = []
    for (module_code, entity_key, source_path), entries in sorted(grouped.items()):
        occurrences = []
        hash_payload = []
        refs = _dedupe_refs(entry[2] for entry in entries)
        for ordinal, (record, raw_value, ref) in enumerate(entries):
            occurrence_key = f"{record.record_id}:{source_path}#{ordinal}"
            typed = _typed_value(raw_value, source_path, [ref])
            occurrences.append(
                NormalizedSourceOccurrence(
                    occurrence_key=occurrence_key,
                    ordinal=ordinal,
                    raw_value=raw_value,
                    typed_value=typed,
                )
            )
            hash_payload.append(
                {"occurrence_key": occurrence_key, "raw_value": raw_value}
            )
        resolved_value = _resolve_source_value(occurrences, source_path, refs)
        confidences = [row.confidence for row in refs if row.confidence is not None]
        fact_payload = {
            "entity_key": entity_key,
            "source_atom": module_code,
            "source_path": source_path,
            "occurrences": hash_payload,
            "record_result_hashes": [entry[0].result_hash for entry in entries],
        }
        result.append(
            NormalizedSourceFact(
                fact_id=stable_hash(
                    fact_payload,
                    version="competitor_profile_v1_1_normalized_source_fact_v1",
                ),
                code=f"{module_code}.{source_path}",
                roles=["normalized_upstream_source"],
                values=[row.typed_value for row in occurrences],
                support_status=(
                    "contradicted"
                    if resolved_value.presence == "conflict"
                    else "unknown"
                ),
                confidence=min(confidences) if confidences else None,
                evidence_refs=refs,
                entity_key=entity_key,
                source_atom=module_code,
                source_path=source_path,
                normalized_target_path=(
                    f"sku_snapshots[{sku_code}].source_facts["
                    f"{entity_key}.{module_code}.{source_path}]"
                ),
                source_occurrences=occurrences,
                occurrence_count=len(occurrences),
                resolved_value=resolved_value,
                source_value_hash=hashlib.sha256(
                    _canonical_json(hash_payload).encode("utf-8")
                ).hexdigest(),
            )
        )
    return sorted(result, key=lambda row: (row.source_atom, row.source_path, row.fact_id))


def _source_fact_entity_key(
    sku_code: str,
    module_code: str,
    facts: Mapping[str, Any],
    record: UpstreamRecordSnapshot,
) -> str:
    if module_code == "M12C":
        parts = [
            _known_text(facts.get("claim_code")),
            _known_text(facts.get("context_type")),
            _known_text(facts.get("context_code")),
            _known_text(facts.get("size_tier")),
            _known_text(facts.get("price_band_group")),
        ]
        if any(parts):
            return f"{sku_code}:M12C:" + ":".join(value or "unknown" for value in parts)
    if module_code == "M11D":
        parts = [
            _known_text(facts.get("dimension_type")),
            _known_text(facts.get("dimension_code")),
            _known_text(facts.get("allocation_role")),
        ]
        if any(parts):
            return f"{sku_code}:M11D:" + ":".join(value or "unknown" for value in parts)
    if module_code in {"M11D", "M12C"}:
        return f"{sku_code}:{module_code}:{record.record_id}"
    return sku_code


def _resolve_source_value(
    occurrences: Sequence[NormalizedSourceOccurrence],
    source_path: str,
    refs: list[EvidenceRef],
) -> TypedFactValue:
    distinct_known: dict[str, Any] = {}
    for occurrence in occurrences:
        typed = occurrence.typed_value
        if typed.presence != "known":
            continue
        distinct_known.setdefault(_canonical_json(typed.value), typed.value)
    if len(distinct_known) > 1:
        return TypedFactValue(
            presence="conflict",
            conflicting_values=[
                distinct_known[key] for key in sorted(distinct_known)
            ],
            unknown_reason_code="source_value_conflict",
            source_path=source_path,
            evidence_refs=refs,
        )
    if len(distinct_known) == 1:
        return TypedFactValue(
            presence="known",
            value=next(iter(distinct_known.values())),
            source_path=source_path,
            evidence_refs=refs,
        )
    return occurrences[0].typed_value.model_copy(deep=True)


def _source_lineage(
    bundle: CompetitorProfileCategoryInputBundle,
    records: Mapping[str, Sequence[UpstreamRecordSnapshot]],
) -> dict[str, Any]:
    return {
        "builder_version": SNAPSHOT_BUILDER_VERSION,
        "category_input_fingerprint": bundle.input_fingerprint,
        "source_module_versions": {
            code: bundle.modules[code].authority.profile_version
            for code in sorted(bundle.modules)
        },
        "source_result_hashes": {
            code: bundle.modules[code].authority.result_hash
            for code in sorted(bundle.modules)
        },
        "source_record_hashes": {
            code: [row.result_hash for row in records[code]]
            for code in sorted(records)
        },
        "source_batch_ids": bundle.serving_scope.source_batch_ids,
    }


def _evidence_ref(record: UpstreamRecordSnapshot) -> EvidenceRef:
    evidence_ids, source_file_ids, raw_row_ids, confidence = _trace_fields(record.facts)
    return EvidenceRef(
        module_code=record.module_code,
        profile_version=record.profile_version,
        rule_version=record.rule_version,
        taxonomy_version=record.taxonomy_version,
        record_type=record.record_type,
        record_id=record.record_id,
        result_hash=record.result_hash,
        source_batch_id=record.source_batch_id,
        evidence_ids=evidence_ids,
        source_file_ids=source_file_ids,
        raw_row_ids=raw_row_ids,
        confidence=confidence,
    )


def _trace_fields(
    facts: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], Decimal | None]:
    evidence: set[str] = set()
    files: set[str] = set()
    rows: set[str] = set()
    confidences: list[Decimal] = []

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in {"evidence_id", "evidence_ids", "evidence_ids_json"}:
                    evidence.update(_text_values(child))
                elif normalized in {"source_file_id", "source_file_ids", "source_file_ids_json"}:
                    files.update(_text_values(child))
                elif normalized in {"raw_row_id", "raw_row_ids", "raw_row_ids_json"}:
                    rows.update(_text_values(child))
                elif normalized in {
                    "confidence",
                    "confidence_score",
                    "market_confidence",
                    "profile_confidence",
                }:
                    parsed = _decimal(child)
                    if parsed is not None and Decimal("0") <= parsed <= Decimal("1"):
                        confidences.append(parsed)
                elif normalized in {
                    "evidence_refs",
                    "evidence_refs_json",
                    "source_lineage",
                    "source_lineage_json",
                }:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(facts)
    return sorted(evidence), sorted(files), sorted(rows), min(confidences) if confidences else None


def _quality_codes(
    records: Sequence[UpstreamRecordSnapshot],
) -> tuple[list[str], list[str]]:
    reviews: set[str] = set()
    conflicts: set[str] = set()
    for record in records:
        for key, value in _walk_items(record.facts):
            text = _known_text(value)
            if key == "review_required" and value is True:
                reviews.add(f"{record.module_code.lower()}_review_required")
            elif key == "review_required_count" and (_decimal(value) or 0) > 0:
                reviews.add(f"{record.module_code.lower()}_review_count_positive")
            elif key in {"processing_status", "review_status", "status"} and text in _REVIEW_STATUSES:
                reviews.add(f"{record.module_code.lower()}_{key}_{text}")
            elif key == "conflict_count" and (_decimal(value) or 0) > 0:
                conflicts.add(f"{record.module_code.lower()}_conflict_count_positive")
            elif key in {
                "evidence_lineage_status",
                "lineage_status",
                "source_lineage_status",
            } and text in _CONFLICT_STATUSES:
                conflicts.add(f"{record.module_code.lower()}_lineage_{text}")
            elif key in {"quality_flags", "quality_flags_json", "risk_flags", "risk_flags_json"}:
                for flag in _text_values(value):
                    if "lineage_conflict" in flag or "source_mismatch" in flag:
                        conflicts.add(f"{record.module_code.lower()}_{flag}")
    return sorted(reviews), sorted(conflicts)


def _records_have_conflicting_known_values(
    records: Sequence[UpstreamRecordSnapshot],
) -> bool:
    if len(records) < 2:
        return False
    known_by_path: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for source_path, raw_value in _iter_json_leaves(
            record.model_dump(mode="json")["facts"],
            prefix="facts",
        ):
            if raw_value is None or (
                isinstance(raw_value, str) and raw_value.strip() in {"", "-"}
            ):
                continue
            known_by_path[source_path].add(_canonical_json(raw_value))
            if len(known_by_path[source_path]) > 1:
                return True
    return False


def _typed_value(
    value: Any,
    source_path: str,
    refs: list[EvidenceRef],
) -> TypedFactValue:
    if value is None:
        return TypedFactValue(
            presence="explicit_null",
            source_path=source_path,
            evidence_refs=refs,
        )
    if isinstance(value, str) and value.strip() in {"", "-"}:
        return TypedFactValue(
            presence="missing",
            unknown_reason_code="legacy_missing_marker",
            source_path=source_path,
            evidence_refs=refs,
        )
    return TypedFactValue(
        presence="known",
        value=value,
        source_path=source_path,
        evidence_refs=refs,
    )


def _iter_json_leaves(value: Any, *, prefix: str) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        if not value:
            yield prefix, {}
            return
        for key in sorted(value):
            yield from _iter_json_leaves(value[key], prefix=f"{prefix}.{key}")
        return
    if isinstance(value, list):
        if not value:
            yield prefix, []
            return
        for index, child in enumerate(value):
            yield from _iter_json_leaves(child, prefix=f"{prefix}[{index}]")
        return
    yield prefix, value


def _parameter_map(
    records: Sequence[UpstreamRecordSnapshot],
) -> dict[str, list[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in records:
        facts = row.facts
        code = _known_text(facts.get("param_code"))
        value = _known_text(
            _first_not_none(
                facts.get("normalized_value"),
                facts.get("param_value"),
                facts.get("value"),
            )
        )
        if code and value:
            result[code].add(value)
        payload = facts.get("param_values_json")
        if isinstance(payload, dict):
            for nested_code, nested_value in payload.items():
                text = _known_text(_parameter_scalar(nested_value))
                if text:
                    result[str(nested_code)].add(text)
    return {code: sorted(values) for code, values in sorted(result.items())}


def _resolve_parameter(
    params: Mapping[str, Sequence[str]],
    codes: Sequence[str],
) -> tuple[str | None, bool]:
    values = {
        value
        for code in codes
        for value in params.get(code, [])
    }
    if len(values) > 1:
        return None, True
    return (next(iter(values)), False) if values else (None, False)


def _parameter_scalar(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return value
    return _first_not_none(
        value.get("normalized_value"),
        value.get("param_value"),
        value.get("value"),
        value.get("raw_value"),
    )


def _claim_market_summary(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_decimal(_decimal(facts[key]))
        for key in (
            "estimated_price_premium_abs",
            "estimated_weekly_sales_lift_abs",
            "estimated_weekly_sales_amount_lift_abs",
            "contribution_share_in_sku",
        )
        if key in facts
    }


def _claim_user_realization(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _json_decimal(_decimal(facts[key]))
        for key in (
            "claim_evidence_strength",
            "param_support_strength",
            "comment_support_strength",
            "semantic_support_strength",
        )
        if key in facts
    }


def _consistent_decimal(
    rows: Sequence[Mapping[str, Any]],
    key: str,
) -> Decimal | None:
    values = {_decimal(row.get(key)) for row in rows if row.get(key) is not None}
    values.discard(None)
    return next(iter(values)) if len(values) == 1 else None


def _reason_texts(value: Any) -> list[str]:
    result = []
    for row in _as_list(value):
        if isinstance(row, dict):
            text = _known_text(
                _first_not_none(
                    row.get("reason_cn"),
                    row.get("anchor_cn"),
                    row.get("anchor_name"),
                    row.get("anchor_code"),
                )
            )
        else:
            text = _known_text(row)
        if text:
            result.append(text)
    return sorted(set(result))


def _first_facts(records: Sequence[UpstreamRecordSnapshot]) -> dict[str, Any]:
    return records[0].model_dump(mode="json")["facts"] if records else {}


def _first_not_none(*values: Any) -> Any:
    return next((value for value in values if value is not None), None)


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _first_nonempty_mapping(
    rows: Sequence[Mapping[str, Any]],
    key: str,
) -> dict[str, Any]:
    return _first_mapping(*(row.get(key) for row in rows))


def _average_decimal(values: Sequence[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _json_decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _m12c_row_strength(row: Mapping[str, Any]) -> Decimal:
    estimated = row.get("estimated_contribution") or {}
    return (
        (_decimal(row.get("claim_value_score")) or Decimal("0"))
        + max(
            _decimal(estimated.get("weekly_sales_amount_lift_abs"))
            or Decimal("0"),
            Decimal("0"),
        )
        / Decimal("100000")
        + max(
            _decimal(estimated.get("price_premium_abs")) or Decimal("0"),
            Decimal("0"),
        )
        / Decimal("100")
    )


def _best_claim_source_type(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_has_claim: bool,
    business_claim_type_cn: str,
) -> str:
    source_types = {
        text
        for text in (_known_text(row.get("claim_source_type")) for row in rows)
        if text
    }
    for preferred in (
        "target_fact_claim",
        "target_param_capability",
        "competitor_opportunity_gap",
        "non_target_signal",
    ):
        if preferred in source_types:
            return preferred
    return _m12c_claim_source_type(
        target_has_claim=target_has_claim,
        business_claim_type_cn=business_claim_type_cn,
    )


def _best_parameter_competitiveness(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    snapshots = [
        dict(value)
        for value in (row.get("parameter_competitiveness") for row in rows)
        if isinstance(value, Mapping) and value
    ]
    return (
        max(
            snapshots,
            key=lambda item: _decimal(
                item.get("overall_parameter_competitiveness_score")
            )
            or Decimal("0"),
        )
        if snapshots
        else {}
    )


def _m12c_evidence_summary(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    best = max(rows, key=_m12c_row_strength)
    evidence = best.get("evidence_strength") or {}
    parameter = _best_parameter_competitiveness(rows)
    parts = []
    parameter_label = _known_text(
        parameter.get("overall_parameter_competitiveness_level_cn")
    )
    if parameter_label:
        parts.append(f"参数竞争力{parameter_label}")
    for key, label in (("param", "参数"), ("comment", "评论"), ("semantic", "战场相关")):
        if key == "param" and parameter_label:
            continue
        value = _decimal(evidence.get(key))
        if value is None:
            continue
        level = "强" if value >= Decimal("0.75") else "中等" if value >= Decimal("0.45") else "弱"
        parts.append(f"{label}{level}")
    return f"证据结构：{'、'.join(parts) if parts else '证据待补充'}。"


def _m12c_business_claim_type(role: str, pool_price_delta: Decimal | None) -> str:
    if role == "premium_driver_estimated":
        return (
            "premium_payment_claim"
            if (pool_price_delta or Decimal("0")) > 0
            else "customer_value_claim"
        )
    return {
        "sales_driver_estimated": "share_conversion_claim",
        "value_bundle_claim": "customer_value_claim",
        "unique_payment_potential": "unique_payment_potential_claim",
        "basic_threshold": "threshold_claim",
        "weak_user_perception_claim": "pending_activation_claim",
        "user_validated_need": "pending_activation_claim",
        "brand_claim_only": "brand_claim",
        "high_price_competitor_intercept": "competitor_intercept_claim",
        "price_up_opportunity": "competitor_intercept_claim",
        "opportunity_gap": "competitor_intercept_claim",
        "drag_factor": "price_pressure_claim",
    }.get(role, "sample_insufficient_claim")


def _m12c_business_claim_type_cn(claim_type: str) -> str:
    return {
        "premium_payment_claim": "高溢价卖点",
        "share_conversion_claim": "份额转化卖点",
        "customer_value_claim": "客户获得价值卖点",
        "unique_payment_potential_claim": "人无我有型支付价值卖点",
        "threshold_claim": "门槛卖点",
        "pending_activation_claim": "待激活卖点",
        "brand_claim": "厂家主张卖点",
        "competitor_intercept_claim": "竞品拦截卖点",
        "price_pressure_claim": "价格压力卖点",
        "sample_insufficient_claim": "样本不足待复核",
    }.get(claim_type, "未分类卖点")


def _m12c_business_claim_type_meaning_cn(claim_type: str) -> str:
    return {
        "premium_payment_claim": "用户愿意为该卖点支付更高价格，并且参数、评论和市场验证共同成立。",
        "share_conversion_claim": "该卖点不一定抬高价格，但能解释同价或相近价格下的销量或份额优势。",
        "customer_value_claim": "该卖点让用户觉得产品更值，主要体现为价格压力更小或销量承接更强。",
        "unique_payment_potential_claim": "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿，但当前缺少稳定对照样本，不能量化金额。",
        "threshold_claim": "该卖点是进入购买清单的基础要求，有了不加价，缺了会掉队。",
        "pending_activation_claim": "本品有参数或厂家表达，但用户评论或市场验证还不足，需要继续激活。",
        "brand_claim": "当前主要是厂家主张，尚未形成稳定用户支付价值。",
        "competitor_intercept_claim": "竞品具备并形成市场验证，本品缺失或表达弱，会影响购买转化。",
        "price_pressure_claim": "卖点表达、参数或用户反馈没有支撑当前价格，可能削弱成交理由。",
        "sample_insufficient_claim": "样本或对照组不足，只能作为观察线索。",
    }.get(claim_type, "当前分类尚未定义。")


def _m12c_claim_source_type(
    *,
    target_has_claim: bool,
    business_claim_type_cn: str,
) -> str:
    if target_has_claim:
        return "target_fact_claim"
    if business_claim_type_cn == "竞品拦截卖点":
        return "competitor_opportunity_gap"
    return "non_target_signal"


def _m12c_claim_source_type_cn(source_type: str) -> str:
    return {
        "target_fact_claim": "本品已成立卖点",
        "target_param_capability": "本品参数能力待激活",
        "competitor_opportunity_gap": "竞品拦截或机会缺口",
        "non_target_signal": "非本品已成立卖点",
    }.get(source_type, "来源待确认")


def _m12c_business_value_label(
    role: str,
    pool_price_delta: Decimal | None,
) -> str:
    if role == "premium_driver_estimated":
        return (
            "强溢价卖点"
            if (pool_price_delta or Decimal("0")) > 0
            else "组合型增值卖点"
        )
    return {
        "sales_driver_estimated": "强销量卖点",
        "basic_threshold": "基础门槛卖点",
        "value_bundle_claim": "组合型增值卖点",
        "unique_payment_potential": "人无我有型支付价值卖点",
        "weak_user_perception_claim": "用户感知不足卖点",
        "high_price_competitor_intercept": "高价竞品拦截卖点",
        "price_up_opportunity": "价格上探机会卖点",
        "drag_factor": "拖后腿卖点",
        "opportunity_gap": "机会缺口",
        "brand_claim_only": "厂家主张卖点",
        "user_validated_need": "用户验证需求",
    }.get(role, "样本不足")


def _m12c_business_value_meaning_cn(
    role: str,
    pool_price_delta: Decimal | None,
) -> str:
    if role == "premium_driver_estimated" and (
        pool_price_delta or Decimal("0")
    ) > 0:
        return "同尺寸、同价格带、同语义市场中，有该卖点且证据成立的一组 SKU 价格更高。"
    if role == "premium_driver_estimated":
        return "单点不一定独立溢价，但与一组高价值卖点组合后参与高端价值解释。"
    return {
        "sales_driver_estimated": "价格不一定更高，但更能解释同池周均销量或销额优势。",
        "basic_threshold": "同池普遍具备，有了不加价，缺了会掉队。",
        "value_bundle_claim": "单点不一定独立溢价，但与一组高价值卖点组合后参与高端价值解释。",
        "unique_payment_potential": "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿；当前对照样本不足，只输出潜力和证据链，不输出金额。",
        "weak_user_perception_claim": "参数或卖点存在，但评论验证弱、负向明显，或弱于高价竞品。",
        "high_price_competitor_intercept": "同池高价竞品具备并能成交，本品缺失、表达弱或评论弱。",
        "price_up_opportunity": "高价 SKU 反复具备且有市场价值，本品补强后可能提升上探空间。",
        "drag_factor": "厂家主张、参数或评论之间不一致，削弱关键战场、任务或客群。",
        "opportunity_gap": "同池强竞品或高价值 SKU 具备，本品缺失或表达弱。",
        "brand_claim_only": "卖点文本存在，但参数、评论或市场验证不足。",
        "user_validated_need": "评论中存在需求，但本品卖点或参数支撑不足。",
    }.get(role, "可比池、对照组或评论样本不足，不能稳定判断。")


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _int(value: Any) -> int | None:
    parsed = _decimal(value)
    return int(parsed) if parsed is not None and parsed == parsed.to_integral_value() else None


def _known_text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    return text if text not in {"", "-", "n/a", "none", "null", "unknown"} else None


def _text_values(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    return sorted({text for row in values if (text := _known_text(row))})


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _walk_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key).lower(), child
            yield from _walk_items(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_items(child)


def _dedupe_refs(refs: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {
        (
            row.module_code,
            row.profile_version,
            row.record_type,
            row.record_id,
            row.result_hash,
        ): row
        for row in refs
    }
    return [by_key[key] for key in sorted(by_key)]


def _json_compatible(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_compatible(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(child) for child in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION",
    "SNAPSHOT_BUILDER_VERSION",
    "VersionSkuAnalysisSnapshotBuildError",
    "VersionSkuAnalysisSnapshotBuilder",
    "build_authoritative_snapshot_projection",
    "snapshot_expected_result_hash",
]
