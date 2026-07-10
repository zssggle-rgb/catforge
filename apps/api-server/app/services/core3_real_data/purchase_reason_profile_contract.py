"""Published M12D downstream consumption contract."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

from app.services.core3_real_data.constants import M12DProfileStatus
from app.services.core3_real_data.purchase_reason_profile_repositories import PurchaseReasonProfileRepository
from app.services.core3_real_data.purchase_reason_profile_schemas import (
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
    anchors = [
        _anchor_contract(anchor)
        for anchor in published.anchors
    ]
    degradation_reasons = _degradation_reasons(profile)
    status = _value(profile.status)
    if status in UNUSABLE_PROFILE_STATUSES:
        consumption_state = "published_unusable"
        downstream_action = "block_target_or_drop_candidate"
        message_cn = "已发布 M12D 画像不可用；目标 SKU 应阻断强排序，候选 SKU 应退出强替代判断。"
    elif degradation_reasons:
        consumption_state = "published_degraded"
        downstream_action = "degraded_pair_scoring"
        message_cn = "已发布 M12D 画像可降级消费；下游必须展示置信度和复核原因，不能输出无条件强结论。"
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
        evidence_domains=list(anchor.evidence_domains_json or []),
        support_summary_cn=anchor.support_summary_cn,
        weakness_summary_cn=anchor.weakness_summary_cn,
        risk_flags=list(anchor.risk_flags_json or []),
        source_refs=list(anchor.source_refs_json or []),
    )


def _degradation_reasons(profile: Any) -> list[str]:
    reasons: list[str] = []
    status = _value(profile.status)
    confidence = Decimal(str(profile.profile_confidence or "0"))
    if bool(profile.review_required):
        reasons.append("review_required")
    if status in {
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
    "get_downstream_read_contract",
]
