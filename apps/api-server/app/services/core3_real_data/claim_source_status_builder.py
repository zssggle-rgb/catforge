"""M04a SKU claim-source status builder."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.base_claim_activation_schemas import (
    ClaimReviewStatus,
    ClaimSourceStatus,
)
from app.services.core3_real_data.constants import (
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3CategoryCode,
    Core3EvidenceStatus,
    Core3EvidenceType,
)
from app.services.core3_real_data.hash_utils import stable_hash


CLAIM_SOURCE_STATUS_ID_HASH_VERSION = "m04a-claim-source-status-id-v1"
CLAIM_SOURCE_STATUS_HASH_VERSION = "m04a-claim-source-status-v1"
PROMO_EVIDENCE_TYPES = {
    Core3EvidenceType.PROMO_RAW.value,
    Core3EvidenceType.PROMO_SENTENCE.value,
}
QUALITY_EVIDENCE_TYPE = Core3EvidenceType.QUALITY_ISSUE.value
UNUSABLE_PROMO_QUALITY_FLAGS = {
    "unknown_value",
    "promo_text_empty",
    "claim_text_empty",
    "claim_data_insufficient",
    "low_value_claim",
}
CONFLICT_QUALITY_FLAGS = {
    "cross_table_conflict",
    "claim_conflict",
    "claim_param_conflict",
    "promo_param_conflict",
}


@dataclass(frozen=True)
class ClaimSourceStatusInput:
    sku_code: str
    model_name: str | None = None
    evidence_records: tuple[Any, ...] = field(default_factory=tuple)
    param_profile: Any | None = None
    param_only_claim_count: int = 0


@dataclass(frozen=True)
class ClaimSourceStatusDraft:
    claim_source_status_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    model_name: str | None
    claim_source_status: str
    structured_claim_count: int
    claim_sentence_count: int
    promo_evidence_count: int
    param_only_claim_count: int
    quality_evidence_ids: list[str]
    missing_signals: list[str]
    conflict_summary_json: dict[str, Any]
    status_note: str
    review_required: bool
    review_status: str
    status_hash: str
    seed_version: str
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "claim_source_status_id": self.claim_source_status_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "claim_source_status": self.claim_source_status,
            "structured_claim_count": self.structured_claim_count,
            "claim_sentence_count": self.claim_sentence_count,
            "promo_evidence_count": self.promo_evidence_count,
            "param_only_claim_count": self.param_only_claim_count,
            "quality_evidence_ids": self.quality_evidence_ids,
            "missing_signals": self.missing_signals,
            "conflict_summary_json": self.conflict_summary_json,
            "status_note": self.status_note,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "status_hash": self.status_hash,
            "seed_version": self.seed_version,
            "rule_version": self.rule_version,
        }


class ClaimSourceStatusBuilder:
    """Build M04a claim-source coverage status for each SKU."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M04A_SEED_VERSION,
        rule_version: str = CORE3_M04A_RULE_VERSION,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed_version = seed_version
        self.rule_version = rule_version

    def build_many(self, inputs: Iterable[ClaimSourceStatusInput]) -> list[ClaimSourceStatusDraft]:
        return [self.build(item) for item in sorted(inputs, key=lambda item: item.sku_code)]

    def build(self, item: ClaimSourceStatusInput) -> ClaimSourceStatusDraft:
        evidence_records = list(item.evidence_records)
        promo_records = [record for record in evidence_records if _evidence_type(record) in PROMO_EVIDENCE_TYPES]
        quality_records = [
            record
            for record in evidence_records
            if _evidence_type(record) == QUALITY_EVIDENCE_TYPE and _is_current(record)
        ]
        usable_promo_records = [record for record in promo_records if _is_usable_promo(record)]
        conflict_records = [record for record in quality_records if _is_conflict_quality(record)]
        missing_issue_records = [record for record in quality_records if _quality_issue_type(record) == "claim_coverage_missing"]
        quality_evidence_ids = _unique_preserve_order(
            _evidence_id(record) for record in [*quality_records, *conflict_records] if _evidence_id(record)
        )
        structured_claim_count = sum(1 for record in usable_promo_records if _evidence_type(record) == "promo_raw")
        claim_sentence_count = sum(1 for record in usable_promo_records if _evidence_type(record) == "promo_sentence")
        promo_evidence_count = len(usable_promo_records)
        invalid_promo_summary = _invalid_promo_summary(promo_records)

        if conflict_records:
            status = ClaimSourceStatus.CLAIM_CONFLICT.value
            missing_signals = []
            conflict_summary_json = _conflict_summary(conflict_records)
            status_note = "该 SKU 的宣传卖点与参数或质量证据存在明显冲突，需要人工复核后再进入基础卖点激活。"
            review_required = True
        elif usable_promo_records:
            status = ClaimSourceStatus.HAS_STRUCTURED_CLAIM.value
            missing_signals = []
            conflict_summary_json = {}
            status_note = "该 SKU 本批有可用结构化宣传卖点，可进入标准卖点基础命中。"
            review_required = False
        elif promo_records:
            status = ClaimSourceStatus.CLAIM_DATA_INSUFFICIENT.value
            missing_signals = _missing_signals_for_invalid_promos(invalid_promo_summary, missing_issue_records)
            conflict_summary_json = {}
            status_note = "该 SKU 本批存在宣传卖点记录，但文本为空、低质量或已被跳过，暂不能视为可用结构化宣传卖点。"
            review_required = True
        elif _has_param_profile(item.param_profile):
            status = ClaimSourceStatus.MISSING_STRUCTURED_CLAIM.value
            missing_signals = _unique_preserve_order(["structured_claim_missing", *_missing_issue_signals(missing_issue_records)])
            conflict_summary_json = {}
            status_note = "该 SKU 本批没有结构化宣传卖点数据，但参数画像存在；后续技术型卖点只能基于参数降级判断，不能视为宣传明确，也不代表没有卖点。"
            review_required = True
        else:
            status = ClaimSourceStatus.CLAIM_DATA_INSUFFICIENT.value
            missing_signals = _unique_preserve_order(["structured_claim_missing", "param_profile_missing"])
            conflict_summary_json = {}
            status_note = "该 SKU 本批缺少结构化宣传卖点和参数画像，基础卖点激活输入不足，需要补齐数据或人工复核。"
            review_required = True

        status_hash = _build_status_hash(
            sku_code=item.sku_code,
            status=status,
            structured_claim_count=structured_claim_count,
            claim_sentence_count=claim_sentence_count,
            promo_evidence_count=promo_evidence_count,
            param_only_claim_count=item.param_only_claim_count,
            quality_evidence_ids=quality_evidence_ids,
            missing_signals=missing_signals,
            conflict_summary_json=conflict_summary_json,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )
        return ClaimSourceStatusDraft(
            claim_source_status_id=_build_status_id(
                project_id=self.project_id,
                batch_id=self.batch_id,
                sku_code=item.sku_code,
                seed_version=self.seed_version,
                rule_version=self.rule_version,
            ),
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=item.sku_code,
            model_name=item.model_name,
            claim_source_status=status,
            structured_claim_count=structured_claim_count,
            claim_sentence_count=claim_sentence_count,
            promo_evidence_count=promo_evidence_count,
            param_only_claim_count=item.param_only_claim_count,
            quality_evidence_ids=quality_evidence_ids,
            missing_signals=missing_signals,
            conflict_summary_json=conflict_summary_json,
            status_note=status_note,
            review_required=review_required,
            review_status=(
                ClaimReviewStatus.REVIEW_REQUIRED.value if review_required else ClaimReviewStatus.AUTO_PASS.value
            ),
            status_hash=status_hash,
            seed_version=self.seed_version,
            rule_version=self.rule_version,
        )


def _build_status_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    seed_version: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "seed_version": seed_version,
            "rule_version": rule_version,
        },
        version=CLAIM_SOURCE_STATUS_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m04asrc_{digest[:32]}"


def _build_status_hash(**payload: Any) -> str:
    return stable_hash(payload, version=CLAIM_SOURCE_STATUS_HASH_VERSION)


def _is_usable_promo(record: Any) -> bool:
    if not _is_current(record):
        return False
    if _is_low_quality_promo(record):
        return False
    return bool(_promo_text(record))


def _is_current(record: Any) -> bool:
    evidence_status = _field_value(record, "evidence_status")
    if evidence_status is not None and _enum_value(evidence_status) != Core3EvidenceStatus.CURRENT.value:
        return False
    if _field_value(record, "is_current") is False:
        return False
    return True


def _is_low_quality_promo(record: Any) -> bool:
    quality_flags = set(_list_value(_field_value(record, "quality_flags")))
    if quality_flags & UNUSABLE_PROMO_QUALITY_FLAGS:
        return True
    quality_status = _enum_value(_field_value(record, "quality_status") or "").lower()
    if quality_status == "error":
        return True
    confidence_level = _enum_value(_field_value(record, "confidence_level") or "").lower()
    if confidence_level == "unknown":
        return True
    base_confidence = _decimal_or_none(_field_value(record, "base_confidence"))
    return base_confidence is not None and base_confidence < Decimal("0.2500")


def _promo_text(record: Any) -> str | None:
    payload = _payload(record)
    return _first_non_empty(
        _field_value(record, "text_value"),
        _field_value(record, "clean_value"),
        _field_value(record, "raw_value"),
        payload.get("clean_claim_text"),
        payload.get("raw_claim_text"),
        payload.get("sentence_text"),
    )


def _invalid_promo_summary(promo_records: list[Any]) -> dict[str, int]:
    summary = {
        "not_current": 0,
        "empty_text": 0,
        "low_quality": 0,
    }
    for record in promo_records:
        if not _is_current(record):
            summary["not_current"] += 1
        elif not _promo_text(record):
            summary["empty_text"] += 1
        elif _is_low_quality_promo(record):
            summary["low_quality"] += 1
    return {key: value for key, value in summary.items() if value}


def _missing_signals_for_invalid_promos(
    invalid_promo_summary: dict[str, int],
    missing_issue_records: list[Any],
) -> list[str]:
    signals: list[str] = []
    if invalid_promo_summary.get("not_current"):
        signals.append("promo_evidence_not_current")
    if invalid_promo_summary.get("empty_text"):
        signals.append("promo_text_empty")
    if invalid_promo_summary.get("low_quality"):
        signals.append("promo_evidence_low_quality")
    signals.extend(_missing_issue_signals(missing_issue_records))
    return _unique_preserve_order(signals or ["promo_evidence_unusable"])


def _missing_issue_signals(records: list[Any]) -> list[str]:
    return ["claim_coverage_missing" for record in records if _evidence_id(record)]


def _is_conflict_quality(record: Any) -> bool:
    issue_type = _quality_issue_type(record)
    if issue_type in CONFLICT_QUALITY_FLAGS:
        return True
    flags = set(_list_value(_field_value(record, "quality_flags"))) | set(_list_value(_payload(record).get("quality_flags")))
    if flags & CONFLICT_QUALITY_FLAGS:
        return True
    evidence_field = str(_field_value(record, "evidence_field") or "").lower()
    return "conflict" in evidence_field


def _quality_issue_type(record: Any) -> str | None:
    payload = _payload(record)
    value = _first_non_empty(
        _field_value(record, "issue_type"),
        payload.get("issue_type"),
    )
    return value.lower() if value else None


def _conflict_summary(records: list[Any]) -> dict[str, Any]:
    issue_type_counts: dict[str, int] = {}
    evidence_ids: list[str] = []
    for record in records:
        issue_type = _quality_issue_type(record) or "claim_conflict"
        issue_type_counts[issue_type] = issue_type_counts.get(issue_type, 0) + 1
        evidence_id = _evidence_id(record)
        if evidence_id:
            evidence_ids.append(evidence_id)
    return {
        "issue_type_counts": dict(sorted(issue_type_counts.items())),
        "quality_evidence_ids": _unique_preserve_order(evidence_ids),
        "conflict_level": "review_required",
    }


def _has_param_profile(param_profile: Any | None) -> bool:
    if param_profile is None:
        return False
    known_count = _field_value(param_profile, "known_param_count")
    if isinstance(known_count, int) and known_count > 0:
        return True
    param_values = _field_value(param_profile, "param_values_json")
    if isinstance(param_values, Mapping) and bool(param_values):
        return True
    return bool(param_profile)


def _evidence_type(record: Any) -> str:
    return _enum_value(_field_value(record, "evidence_type") or "")


def _evidence_id(record: Any) -> str | None:
    return _optional_string(_field_value(record, "evidence_id"))


def _payload(record: Any) -> dict[str, Any]:
    value = _field_value(record, "evidence_payload_json")
    return dict(value) if isinstance(value, Mapping) else {}


def _field_value(record: Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    if hasattr(record, "model_dump"):
        return record.model_dump().get(field_name)
    return getattr(record, field_name, None)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set | frozenset):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value) else []


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _optional_string(value)
        if text:
            return text
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
