"""Compare purchase friction without changing purchase-reason establishment."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.services.core3_real_data.constants import (
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamAnchorContract,
    M12DDownstreamReadContract,
)


PRESSURE_LEVEL_RANK = {
    M12DPurchasePressureLevel.UNASSESSED.value: -1,
    M12DPurchasePressureLevel.NONE.value: 0,
    M12DPurchasePressureLevel.LOW.value: 1,
    M12DPurchasePressureLevel.MEDIUM.value: 2,
    M12DPurchasePressureLevel.HIGH.value: 3,
    M12DPurchasePressureLevel.CRITICAL.value: 4,
}

PRESSURE_LEVEL_CN = {
    M12DPurchasePressureLevel.UNASSESSED.value: "尚未评估",
    M12DPurchasePressureLevel.NONE.value: "当前未观察到明确阻力",
    M12DPurchasePressureLevel.LOW.value: "较低阻力",
    M12DPurchasePressureLevel.MEDIUM.value: "中等阻力",
    M12DPurchasePressureLevel.HIGH.value: "较高阻力",
    M12DPurchasePressureLevel.CRITICAL.value: "严重阻力",
}

PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION = "purchase_pressure_comparator_v1"
PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION = (
    "purchase_pressure_established_shared_anchor_v1"
)


@dataclass(frozen=True)
class PurchasePressureAnchorComparison:
    anchor_code: str
    anchor_cn: str
    target_pressure_level: str
    candidate_pressure_level: str
    target_summary_cn: str
    candidate_summary_cn: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_code": self.anchor_code,
            "anchor_cn": self.anchor_cn,
            "target_pressure_level": self.target_pressure_level,
            "target_pressure_level_cn": _pressure_level_cn(self.target_pressure_level),
            "candidate_pressure_level": self.candidate_pressure_level,
            "candidate_pressure_level_cn": _pressure_level_cn(
                self.candidate_pressure_level
            ),
            "target_summary_cn": self.target_summary_cn,
            "candidate_summary_cn": self.candidate_summary_cn,
        }


@dataclass(frozen=True)
class PurchasePressureComparisonResult:
    comparison_allowed: bool
    target_highest_pressure_level: str
    candidate_highest_pressure_level: str
    shared_anchor_comparisons: list[PurchasePressureAnchorComparison] = field(
        default_factory=list
    )
    summary_cn: str = ""
    limitation_cn: str | None = None

    def to_business_payload(self) -> dict[str, Any]:
        return {
            "comparison_allowed": self.comparison_allowed,
            "target_highest_pressure_level": self.target_highest_pressure_level,
            "target_highest_pressure_level_cn": _pressure_level_cn(
                self.target_highest_pressure_level
            ),
            "candidate_highest_pressure_level": self.candidate_highest_pressure_level,
            "candidate_highest_pressure_level_cn": _pressure_level_cn(
                self.candidate_highest_pressure_level
            ),
            "shared_anchor_comparisons": [
                row.to_dict() for row in self.shared_anchor_comparisons
            ],
            "summary_cn": self.summary_cn,
            "limitation_cn": self.limitation_cn,
        }


class PurchasePressureComparator:
    """Compare pressure on reasons that are independently established for both SKUs."""

    def compare(
        self,
        *,
        target_contract: M12DDownstreamReadContract,
        candidate_contract: M12DDownstreamReadContract,
    ) -> PurchasePressureComparisonResult:
        if not _pressure_comparison_allowed(target_contract, candidate_contract):
            limitation = "目标或候选 SKU 的购买阻力画像当前不可比较；其他参数、卖点和市场维度仍按各自消费能力判断。"
            return PurchasePressureComparisonResult(
                comparison_allowed=False,
                target_highest_pressure_level=_highest_pressure_level(target_contract),
                candidate_highest_pressure_level=_highest_pressure_level(
                    candidate_contract
                ),
                summary_cn=limitation,
                limitation_cn=limitation,
            )

        target_anchors = _established_anchor_index(target_contract)
        candidate_anchors = _established_anchor_index(candidate_contract)
        rows = [
            PurchasePressureAnchorComparison(
                anchor_code=anchor_code,
                anchor_cn=target_anchors[anchor_code].anchor_cn,
                target_pressure_level=_value(
                    target_anchors[anchor_code].pressure_level
                ),
                candidate_pressure_level=_value(
                    candidate_anchors[anchor_code].pressure_level
                ),
                target_summary_cn=str(
                    target_anchors[anchor_code].pressure_summary_cn or ""
                ),
                candidate_summary_cn=str(
                    candidate_anchors[anchor_code].pressure_summary_cn or ""
                ),
            )
            for anchor_code in sorted(target_anchors.keys() & candidate_anchors.keys())
        ]
        target_highest = _highest_pressure_level(target_contract)
        candidate_highest = _highest_pressure_level(candidate_contract)
        if rows:
            names = "、".join(row.anchor_cn for row in rows[:4])
            summary = (
                f"双方共同成立的购买理由包括{names}。本品最高为{_pressure_level_cn(target_highest)}，"
                f"竞品最高为{_pressure_level_cn(candidate_highest)}；购买阻力只说明成交时可能遇到的顾虑，不改变理由是否成立。"
            )
        else:
            summary = "双方暂无共同成立的购买理由，不能做同理由购买阻力比较。"
        return PurchasePressureComparisonResult(
            comparison_allowed=True,
            target_highest_pressure_level=target_highest,
            candidate_highest_pressure_level=candidate_highest,
            shared_anchor_comparisons=rows,
            summary_cn=summary,
        )


def _pressure_comparison_allowed(
    target_contract: M12DDownstreamReadContract,
    candidate_contract: M12DDownstreamReadContract,
) -> bool:
    return bool(
        target_contract.found
        and candidate_contract.found
        and target_contract.profile is not None
        and candidate_contract.profile is not None
        and target_contract.capabilities.pressure_comparison_allowed
        and candidate_contract.capabilities.pressure_comparison_allowed
    )


def _established_anchor_index(
    contract: M12DDownstreamReadContract,
) -> dict[str, M12DDownstreamAnchorContract]:
    profile = contract.profile
    if profile is None:
        return {}
    return {
        anchor.anchor_code: anchor
        for anchor in profile.anchors
        if _is_established_reason(anchor)
    }


def _highest_pressure_level(contract: M12DDownstreamReadContract) -> str:
    anchors = _established_anchor_index(contract).values()
    levels = [_value(anchor.pressure_level) for anchor in anchors]
    return max(
        levels or [M12DPurchasePressureLevel.UNASSESSED.value],
        key=lambda level: PRESSURE_LEVEL_RANK.get(level, -1),
    )


def _is_established_reason(anchor: M12DDownstreamAnchorContract) -> bool:
    return _value(anchor.establishment_status) in {
        M12DReasonEstablishmentStatus.UNASSESSED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED.value,
        M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
    }


def _pressure_level_cn(level: str) -> str:
    return PRESSURE_LEVEL_CN.get(level, "尚未评估")


def _value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


__all__ = [
    "PURCHASE_PRESSURE_COMPARATOR_CONFIG_VERSION",
    "PURCHASE_PRESSURE_COMPARATOR_METHOD_VERSION",
    "PurchasePressureAnchorComparison",
    "PurchasePressureComparator",
    "PurchasePressureComparisonResult",
]
