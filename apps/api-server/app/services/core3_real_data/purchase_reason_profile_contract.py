"""Published M12D downstream consumption contract."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from app.services.core3_real_data.constants import (
    M12DProfileStatus,
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
    M12DReleaseQualityStatus,
    M12DUserValidationStatus,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import (
    PurchaseReasonProfileRepository,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DConsumptionCapabilities,
    M12DDownstreamAnchorContract,
    M12DDownstreamProfileContract,
    M12DDownstreamReadContract,
    M12DPublishedProfile,
)

LOW_CONFIDENCE_THRESHOLD = Decimal("0.5000")
UNUSABLE_PROFILE_STATUSES = {
    M12DProfileStatus.FAILED.value,
    M12DProfileStatus.MISSING_INPUT.value,
}


def get_downstream_read_contract(
    repository: PurchaseReasonProfileRepository,
    *,
    batch_id: str,
    sku_code: str,
    m12d_profile_version: str | None = None,
) -> M12DDownstreamReadContract:
    """Read a published M12D profile and return the frozen downstream contract."""

    lookup_key = _lookup_key(
        repository=repository,
        batch_id=batch_id,
        sku_code=sku_code,
        m12d_profile_version=m12d_profile_version,
    )
    published = repository.get_published_profile(
        batch_id=batch_id,
        sku_code=sku_code,
        m12d_profile_version=m12d_profile_version,
    )
    return build_downstream_read_contract(published, lookup_key=lookup_key)


def build_downstream_read_contract(
    published: M12DPublishedProfile | None,
    *,
    lookup_key: dict[str, str],
) -> M12DDownstreamReadContract:
    if published is None:
        return M12DDownstreamReadContract(
            found=False,
            lookup_key=lookup_key,
            consumption_state="not_found",
            downstream_action="block_target_or_drop_candidate",
            message_cn="未找到已发布的 M12D SKU成交理由画像；下游不得临时生成或补写成交理由。",
            profile=None,
        )

    profile = published.profile
    release_quality_status = _release_quality_status(published.version)
    anchors = [_anchor_contract(anchor) for anchor in published.anchors]
    degradation_reasons = _degradation_reasons(
        profile,
        release_quality_status=release_quality_status,
    )
    status = _value(profile.status)
    capabilities = _consumption_capabilities(
        status=status,
        profile=profile,
        anchors=anchors,
        release_quality_status=release_quality_status,
    )
    if release_quality_status == M12DReleaseQualityStatus.BLOCKED.value:
        consumption_state = "published_unusable"
        downstream_action = "block_target_or_drop_candidate"
        message_cn = "M12D 版本质量已阻断；下游不得读取该版本进行竞品排序。"
    elif status in UNUSABLE_PROFILE_STATUSES:
        consumption_state = "published_unusable"
        downstream_action = "block_target_or_drop_candidate"
        message_cn = (
            "已发布 M12D 画像不可用；目标 SKU 应阻断强排序，候选 SKU 应退出强替代判断。"
        )
    elif capabilities.comparison_mode != "strong":
        consumption_state = "published_degraded"
        downstream_action = "degraded_pair_scoring"
        message_cn = (
            "已发布 M12D SKU 可继续消费事实维度；"
            "购买理由比较必须按该 SKU 的成立理由和产品价值主张能力执行。"
        )
    else:
        consumption_state = "published_ready"
        downstream_action = "normal_pair_scoring"
        message_cn = "已发布 M12D 画像可正常消费。"

    return M12DDownstreamReadContract(
        found=True,
        lookup_key=lookup_key,
        consumption_state=consumption_state,
        downstream_action=downstream_action,
        message_cn=message_cn,
        release_quality_status=release_quality_status,
        version_quality_notes=_version_quality_notes(release_quality_status),
        capabilities=capabilities,
        profile=M12DDownstreamProfileContract(
            project_id=profile.project_id,
            category_code=profile.category_code,
            batch_id=profile.batch_id,
            product_category=profile.product_category,
            m12d_profile_version=profile.m12d_profile_version,
            schema_version=profile.schema_version,
            rule_version=profile.rule_version,
            sku_code=profile.sku_code,
            model_code=profile.model_code,
            model_name=profile.model_name,
            brand_name=profile.brand_name,
            display_name_cn=profile.display_name_cn,
            status=profile.status,
            profile_confidence=profile.profile_confidence,
            confidence_level=profile.confidence_level,
            core_reasons_cn=list(profile.core_reasons_json or []),
            core_payment_anchors=list(profile.core_payment_anchors_json or []),
            supporting_anchors=list(profile.supporting_anchors_json or []),
            weak_expression_anchors=list(profile.weak_expression_anchors_json or []),
            risk_drag_anchors=list(profile.risk_drag_anchors_json or []),
            established_anchors=list(
                getattr(profile, "established_anchors_json", None) or []
            ),
            proposition_anchors=list(
                getattr(profile, "proposition_anchors_json", None) or []
            ),
            pressure_summary=dict(
                getattr(profile, "pressure_summary_json", None) or {}
            ),
            comparison_limitations=list(
                getattr(profile, "comparison_limitations_json", None) or []
            ),
            anchors=anchors,
            review_required=bool(profile.review_required),
            review_status=profile.review_status,
            review_reasons=_review_reasons(profile.review_reason_json),
            degradation_reasons=degradation_reasons,
            evidence_summary=dict(profile.evidence_summary_json or {}),
            source_batch_ids=list(profile.source_batch_ids_json or []),
            source_refs=list(profile.source_refs_json or []),
        ),
    )


def _anchor_contract(anchor: Any) -> M12DDownstreamAnchorContract:
    return M12DDownstreamAnchorContract(
        anchor_code=anchor.anchor_code,
        anchor_cn=anchor.anchor_cn,
        anchor_family_code=anchor.anchor_family_code,
        anchor_rank=anchor.anchor_rank,
        role=anchor.role,
        evidence_strength=anchor.evidence_strength,
        confidence=anchor.confidence,
        establishment_status=_compat_enum_value(
            getattr(anchor, "establishment_status", None),
            M12DReasonEstablishmentStatus,
            M12DReasonEstablishmentStatus.UNASSESSED.value,
        ),
        establishment_score=getattr(anchor, "establishment_score", None),
        establishment_domains=list(
            getattr(anchor, "establishment_domains_json", None) or []
        ),
        user_validation_status=_compat_enum_value(
            getattr(anchor, "user_validation_status", None),
            M12DUserValidationStatus,
            M12DUserValidationStatus.UNASSESSED.value,
        ),
        core_eligible=getattr(anchor, "core_eligible", None),
        core_ineligible_reasons=list(
            getattr(anchor, "core_ineligible_reasons_json", None) or []
        ),
        proposition_evidence=list(
            getattr(anchor, "proposition_evidence_json", None) or []
        ),
        user_support_evidence=list(
            getattr(anchor, "user_support_evidence_json", None) or []
        ),
        pressure_level=_compat_enum_value(
            getattr(anchor, "pressure_level", None),
            M12DPurchasePressureLevel,
            M12DPurchasePressureLevel.UNASSESSED.value,
        ),
        pressure_tags=list(getattr(anchor, "pressure_tags_json", None) or []),
        pressure_summary_cn=str(getattr(anchor, "pressure_summary_cn", None) or ""),
        comparison_limitations=list(
            getattr(anchor, "comparison_limitations_json", None) or []
        ),
        evidence_domains=list(anchor.evidence_domains_json or []),
        support_summary_cn=anchor.support_summary_cn,
        weakness_summary_cn=anchor.weakness_summary_cn,
        risk_flags=list(anchor.risk_flags_json or []),
        source_refs=list(anchor.source_refs_json or []),
    )


def _degradation_reasons(
    profile: Any,
    *,
    release_quality_status: str,
) -> list[str]:
    reasons: list[str] = []
    status = _value(profile.status)
    confidence = Decimal(str(profile.profile_confidence or "0"))
    if bool(profile.review_required):
        reasons.append("review_required")
    if release_quality_status == M12DReleaseQualityStatus.BLOCKED.value:
        reasons.append("release_quality_status_blocked")
    if status in {
        M12DProfileStatus.READY_LIMITED.value,
        M12DProfileStatus.READY_DEGRADED.value,
        M12DProfileStatus.REVIEW_REQUIRED.value,
        M12DProfileStatus.WEAK_EXPRESSION_ONLY.value,
        M12DProfileStatus.MISSING_INPUT.value,
        M12DProfileStatus.FAILED.value,
    }:
        reasons.append(f"profile_status_{status}")
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        reasons.append("low_profile_confidence")
    if not list(profile.core_payment_anchors_json or []):
        reasons.append("core_payment_missing")
    reasons.extend(_review_reasons(profile.review_reason_json))
    return _dedupe(reasons)


def _consumption_capabilities(
    *,
    status: str,
    profile: Any,
    anchors: list[M12DDownstreamAnchorContract],
    release_quality_status: str,
) -> M12DConsumptionCapabilities:
    if (
        release_quality_status == M12DReleaseQualityStatus.BLOCKED.value
        or status in UNUSABLE_PROFILE_STATUSES
    ):
        return M12DConsumptionCapabilities()

    established_statuses = {
        M12DReasonEstablishmentStatus.ESTABLISHED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
    }
    established = [
        anchor
        for anchor in anchors
        if _value(anchor.establishment_status) in established_statuses
    ]
    propositions = [
        anchor
        for anchor in anchors
        if _value(anchor.establishment_status)
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    ]
    legacy_unassessed = bool(anchors) and all(
        _value(anchor.establishment_status)
        == M12DReasonEstablishmentStatus.UNASSESSED.value
        for anchor in anchors
    )
    core_codes = set(
        getattr(profile, "core_payment_anchors_json", None)
        or getattr(profile, "core_payment_anchors", None)
        or []
    )
    established_core = any(anchor.anchor_code in core_codes for anchor in established)
    strong = (
        status == M12DProfileStatus.READY.value
        and bool(core_codes)
        and (established_core or legacy_unassessed)
    )
    established_allowed = bool(established) or (legacy_unassessed and bool(core_codes))
    if strong:
        comparison_mode = "strong"
    elif established_allowed:
        comparison_mode = "limited"
    else:
        comparison_mode = "facts_only"
    return M12DConsumptionCapabilities(
        comparison_mode=comparison_mode,
        fact_dimensions_allowed=True,
        proposition_comparison_allowed=bool(propositions),
        established_reason_comparison_allowed=established_allowed,
        strong_reason_comparison_allowed=strong,
        pressure_comparison_allowed=bool(established),
    )


def _version_quality_notes(release_quality_status: str) -> list[str]:
    if release_quality_status == M12DReleaseQualityStatus.LIMITED.value:
        return ["版本覆盖质量有限；该 SKU 仍按自身画像状态和维度能力消费。"]
    if release_quality_status == M12DReleaseQualityStatus.BLOCKED.value:
        return ["版本质量已阻断，所有 SKU 均不可消费。"]
    return []


def derive_consumption_capabilities(
    *,
    profile: Any,
    anchors: list[M12DDownstreamAnchorContract],
    release_quality_status: M12DReleaseQualityStatus | str,
) -> M12DConsumptionCapabilities:
    return _consumption_capabilities(
        status=_value(profile.status),
        profile=profile,
        anchors=anchors,
        release_quality_status=_value(release_quality_status),
    )


def _release_quality_status(version: Any) -> str:
    value = _value(
        getattr(
            version,
            "release_quality_status",
            M12DReleaseQualityStatus.UNASSESSED.value,
        )
    )
    if value in {
        M12DReleaseQualityStatus.READY.value,
        M12DReleaseQualityStatus.LIMITED.value,
        M12DReleaseQualityStatus.BLOCKED.value,
        M12DReleaseQualityStatus.UNASSESSED.value,
    }:
        return value
    return M12DReleaseQualityStatus.UNASSESSED.value


def _review_reasons(review_reason_json: Any) -> list[str]:
    if not isinstance(review_reason_json, dict):
        return []
    reasons = review_reason_json.get("reasons") or []
    return [str(reason) for reason in reasons if str(reason).strip()]


def _lookup_key(
    *,
    repository: PurchaseReasonProfileRepository,
    batch_id: str,
    sku_code: str,
    m12d_profile_version: str | None,
) -> dict[str, str]:
    return {
        "project_id": repository.project_id,
        "category_code": repository.category_code.value,
        "batch_id": batch_id,
        "m12d_profile_version": m12d_profile_version or "current_published",
        "sku_code": sku_code,
    }


def _value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _compat_enum_value(value: Any, enum_type: type[Enum], default: str) -> str:
    normalized = _value(value) if value is not None else default
    allowed = {_value(item) for item in enum_type}
    return normalized if normalized in allowed else default


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


__all__ = [
    "build_downstream_read_contract",
    "derive_consumption_capabilities",
    "get_downstream_read_contract",
]
