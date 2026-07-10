"""Read-only M12D profile access for competitor analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.purchase_reason_profile_contract import (
    build_downstream_read_contract,
    get_downstream_read_contract,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import PurchaseReasonProfileRepository
from app.services.core3_real_data.purchase_reason_profile_schemas import M12DDownstreamReadContract
from app.services.core3_real_data.repositories import Core3RepositoryContext

M12D_G09_CONTRACT_FIXTURE = "docs/core3_mvp/real_data_v2/current_implementation/M12D_G09_published_contract_fixture.json"
CURRENT_PUBLISHED_VERSION = "current_published"


@dataclass(frozen=True)
class PurchaseReasonProfileLookupKey:
    project_id: str
    category_code: Core3CategoryCode | str
    batch_id: str
    sku_code: str
    m12d_profile_version: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("project_id", "batch_id", "sku_code"):
            value = getattr(self, field_name)
            if not str(value).strip():
                raise ValueError(f"{field_name} is required")
            object.__setattr__(self, field_name, str(value).strip())
        object.__setattr__(self, "category_code", Core3CategoryCode(self.category_code))
        if self.m12d_profile_version is not None:
            version = str(self.m12d_profile_version).strip()
            object.__setattr__(self, "m12d_profile_version", version or None)

    @classmethod
    def from_mapping(cls, payload: dict[str, str]) -> "PurchaseReasonProfileLookupKey":
        return cls(
            project_id=payload["project_id"],
            category_code=payload["category_code"],
            batch_id=payload["batch_id"],
            sku_code=payload["sku_code"],
            m12d_profile_version=payload.get("m12d_profile_version"),
        )

    def to_contract_lookup_key(self, *, default_m12d_profile_version: str | None = None) -> dict[str, str]:
        return {
            "project_id": self.project_id,
            "category_code": self.category_code.value,
            "batch_id": self.batch_id,
            "m12d_profile_version": self.m12d_profile_version or default_m12d_profile_version or CURRENT_PUBLISHED_VERSION,
            "sku_code": self.sku_code,
        }

    def index_tuple(self, *, default_m12d_profile_version: str | None = None) -> tuple[str, str, str, str, str]:
        lookup_key = self.to_contract_lookup_key(default_m12d_profile_version=default_m12d_profile_version)
        return (
            lookup_key["project_id"],
            lookup_key["category_code"],
            lookup_key["batch_id"],
            lookup_key["m12d_profile_version"],
            lookup_key["sku_code"],
        )


class PurchaseReasonProfileReader(Protocol):
    def read(self, lookup_key: PurchaseReasonProfileLookupKey) -> M12DDownstreamReadContract:
        """Read a frozen M12D downstream contract without generating M12D."""


@dataclass(frozen=True)
class RepositoryPurchaseReasonProfileReader:
    db: Session

    def read(self, lookup_key: PurchaseReasonProfileLookupKey) -> M12DDownstreamReadContract:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=self.db,
                project_id=lookup_key.project_id,
                category_code=lookup_key.category_code,
            )
        )
        return get_downstream_read_contract(
            repository,
            batch_id=lookup_key.batch_id,
            sku_code=lookup_key.sku_code,
            m12d_profile_version=lookup_key.m12d_profile_version,
        )


class FixturePurchaseReasonProfileReader:
    def __init__(
        self,
        contracts: list[M12DDownstreamReadContract],
        *,
        default_m12d_profile_version: str | None = None,
    ) -> None:
        self.default_m12d_profile_version = default_m12d_profile_version
        self._contracts_by_key = {
            _contract_index_tuple(contract): contract
            for contract in contracts
        }

    @classmethod
    def from_default_fixture(cls) -> "FixturePurchaseReasonProfileReader":
        return cls.from_path(default_m12d_contract_fixture_path())

    @classmethod
    def from_path(cls, fixture_path: str | Path) -> "FixturePurchaseReasonProfileReader":
        path = Path(fixture_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        contracts: list[M12DDownstreamReadContract] = []
        for item in payload.get("sample_contracts") or []:
            contracts.append(M12DDownstreamReadContract.model_validate(item))
        for key in ("missing_contract_fixture", "unpublished_version_contract_fixture"):
            item = payload.get(key)
            if item:
                contracts.append(M12DDownstreamReadContract.model_validate(item))
        return cls(
            contracts,
            default_m12d_profile_version=payload.get("m12d_profile_version"),
        )

    def read(self, lookup_key: PurchaseReasonProfileLookupKey) -> M12DDownstreamReadContract:
        indexed_key = lookup_key.index_tuple(default_m12d_profile_version=self.default_m12d_profile_version)
        contract = self._contracts_by_key.get(indexed_key)
        if contract is not None:
            return contract
        return _not_found_contract(
            lookup_key,
            default_m12d_profile_version=self.default_m12d_profile_version,
        )


@dataclass(frozen=True)
class PurchaseReasonProfileUsageDecision:
    subject_role: Literal["target", "candidate"]
    action: Literal[
        "normal_pair_scoring",
        "degraded_pair_scoring",
        "block_strong_ranking",
        "drop_candidate_or_review",
    ]
    pair_scoring_allowed: bool
    strong_ranking_allowed: bool
    top3_eligible: bool
    requires_review: bool
    confidence_state: Literal["normal", "degraded", "blocked"]
    message_cn: str
    reasons: tuple[str, ...] = ()


def decide_target_m12d_usage(contract: M12DDownstreamReadContract) -> PurchaseReasonProfileUsageDecision:
    if _is_blocked(contract):
        return PurchaseReasonProfileUsageDecision(
            subject_role="target",
            action="block_strong_ranking",
            pair_scoring_allowed=False,
            strong_ranking_allowed=False,
            top3_eligible=False,
            requires_review=True,
            confidence_state="blocked",
            message_cn="目标 SKU 成交理由画像待生成/置信度不足，不能输出强排序结论。",
            reasons=_contract_reasons(contract),
        )
    if contract.consumption_state == "published_degraded":
        return PurchaseReasonProfileUsageDecision(
            subject_role="target",
            action="degraded_pair_scoring",
            pair_scoring_allowed=True,
            strong_ranking_allowed=False,
            top3_eligible=False,
            requires_review=True,
            confidence_state="degraded",
            message_cn="目标 SKU 成交理由画像可降级消费，必须展示置信度和复核原因，不能输出无条件强结论。",
            reasons=_contract_reasons(contract),
        )
    return PurchaseReasonProfileUsageDecision(
        subject_role="target",
        action="normal_pair_scoring",
        pair_scoring_allowed=True,
        strong_ranking_allowed=True,
        top3_eligible=False,
        requires_review=False,
        confidence_state="normal",
        message_cn="目标 SKU 成交理由画像可正常用于竞品排序。",
        reasons=_contract_reasons(contract),
    )


def decide_candidate_m12d_usage(contract: M12DDownstreamReadContract) -> PurchaseReasonProfileUsageDecision:
    if _is_blocked(contract):
        return PurchaseReasonProfileUsageDecision(
            subject_role="candidate",
            action="drop_candidate_or_review",
            pair_scoring_allowed=False,
            strong_ranking_allowed=False,
            top3_eligible=False,
            requires_review=True,
            confidence_state="blocked",
            message_cn="候选 SKU 成交理由画像缺失或未发布，不能依赖关键价值锚点进入 Top 3。",
            reasons=_contract_reasons(contract),
        )
    if contract.consumption_state == "published_degraded":
        return PurchaseReasonProfileUsageDecision(
            subject_role="candidate",
            action="degraded_pair_scoring",
            pair_scoring_allowed=True,
            strong_ranking_allowed=False,
            top3_eligible=True,
            requires_review=True,
            confidence_state="degraded",
            message_cn="候选 SKU 成交理由画像可降级消费，锚点可替代性必须降置信度；依赖该维度入选 Top 3 时需复核。",
            reasons=_contract_reasons(contract),
        )
    return PurchaseReasonProfileUsageDecision(
        subject_role="candidate",
        action="normal_pair_scoring",
        pair_scoring_allowed=True,
        strong_ranking_allowed=True,
        top3_eligible=True,
        requires_review=False,
        confidence_state="normal",
        message_cn="候选 SKU 成交理由画像可正常用于锚点可替代性比较。",
        reasons=_contract_reasons(contract),
    )


def default_m12d_contract_fixture_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / M12D_G09_CONTRACT_FIXTURE
        if candidate.exists():
            return candidate
    return Path(M12D_G09_CONTRACT_FIXTURE)


def _not_found_contract(
    lookup_key: PurchaseReasonProfileLookupKey,
    *,
    default_m12d_profile_version: str | None,
) -> M12DDownstreamReadContract:
    return build_downstream_read_contract(
        None,
        lookup_key=lookup_key.to_contract_lookup_key(default_m12d_profile_version=default_m12d_profile_version),
    )


def _contract_index_tuple(contract: M12DDownstreamReadContract) -> tuple[str, str, str, str, str]:
    return PurchaseReasonProfileLookupKey.from_mapping(contract.lookup_key).index_tuple()


def _is_blocked(contract: M12DDownstreamReadContract) -> bool:
    return (
        not contract.found
        or contract.consumption_state in {"not_found", "published_unusable"}
        or contract.downstream_action == "block_target_or_drop_candidate"
    )


def _contract_reasons(contract: M12DDownstreamReadContract) -> tuple[str, ...]:
    reasons: list[str] = [contract.consumption_state, contract.downstream_action]
    if contract.profile is not None:
        reasons.extend(contract.profile.degradation_reasons)
    return tuple(_dedupe(reasons))


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
    "FixturePurchaseReasonProfileReader",
    "PurchaseReasonProfileLookupKey",
    "PurchaseReasonProfileReader",
    "PurchaseReasonProfileUsageDecision",
    "RepositoryPurchaseReasonProfileReader",
    "decide_candidate_m12d_usage",
    "decide_target_m12d_usage",
    "default_m12d_contract_fixture_path",
]
