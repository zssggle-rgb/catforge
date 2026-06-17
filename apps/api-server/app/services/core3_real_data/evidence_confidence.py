"""M02 evidence confidence rules."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping

from app.services.core3_real_data.constants import Core3ConfidenceLevel, Core3EvidenceType
from app.services.core3_real_data.evidence_mappers import MappedEvidenceDraft


CONFIDENCE_QUANT = Decimal("0.0001")


@dataclass(frozen=True)
class EvidenceConfidence:
    base_confidence: Decimal
    confidence_level: Core3ConfidenceLevel
    reasons: list[str]


class EvidenceConfidenceService:
    def calculate(
        self,
        draft: MappedEvidenceDraft,
        *,
        evidence_payload: Mapping[str, Any] | None = None,
    ) -> EvidenceConfidence:
        source_payload = draft.source_payload or {}
        payload = evidence_payload or {}
        base, reasons = self._base_score(draft, source_payload, payload)
        capped, cap_reasons = self._apply_caps(base, draft, source_payload, payload)
        score = _quantize(capped)
        return EvidenceConfidence(
            base_confidence=score,
            confidence_level=_confidence_level(score),
            reasons=[*reasons, *cap_reasons],
        )

    def _base_score(
        self,
        draft: MappedEvidenceDraft,
        source_payload: Mapping[str, Any],
        evidence_payload: Mapping[str, Any],
    ) -> tuple[Decimal, list[str]]:
        if draft.evidence_type == Core3EvidenceType.MARKET_FACT:
            if _has_any(source_payload, "sales_volume", "sales_amount", "avg_price"):
                return Decimal("0.9500"), ["market_numeric_available"]
            return Decimal("0.5500"), ["market_numeric_missing"]

        if draft.evidence_type == Core3EvidenceType.PARAM_RAW:
            if _value_presence(source_payload, draft) == "present":
                return Decimal("0.9000"), ["param_present"]
            return Decimal("0.3500"), ["param_not_present"]

        if draft.evidence_type == Core3EvidenceType.PROMO_RAW:
            if _text_present(source_payload.get("clean_claim_text") or source_payload.get("raw_claim_text")):
                return Decimal("0.8500"), ["promo_text_available"]
            return Decimal("0.3500"), ["promo_text_missing"]

        if draft.evidence_type == Core3EvidenceType.PROMO_SENTENCE:
            if _text_present(source_payload.get("sentence_text")):
                return Decimal("0.8000"), ["promo_sentence_available"]
            return Decimal("0.2500"), ["promo_sentence_missing"]

        if draft.evidence_type == Core3EvidenceType.SKU_FACT:
            return Decimal("0.8000"), ["sku_clean_coverage"]

        if draft.evidence_type == Core3EvidenceType.COMMENT_RAW:
            if _truthy(source_payload.get("low_value_flag")):
                return Decimal("0.2500"), ["low_value_comment"]
            if _text_present(source_payload.get("clean_comment_text") or source_payload.get("raw_comment_text")):
                return Decimal("0.7500"), ["comment_text_available"]
            return Decimal("0.2500"), ["comment_text_missing"]

        if draft.evidence_type == Core3EvidenceType.COMMENT_SENTENCE:
            if _truthy(source_payload.get("low_value_flag")):
                return Decimal("0.2500"), ["low_value_comment_sentence"]
            if _text_present(source_payload.get("sentence_text")):
                return Decimal("0.7000"), ["comment_sentence_available"]
            return Decimal("0.2500"), ["comment_sentence_missing"]

        if draft.evidence_type == Core3EvidenceType.COMMENT_DIMENSION:
            return Decimal("0.5500"), ["comment_dimension_raw_label"]

        if draft.evidence_type == Core3EvidenceType.QUALITY_ISSUE:
            severity = str(source_payload.get("severity") or evidence_payload.get("severity") or "").lower()
            if severity == "error":
                return Decimal("0.2000"), ["quality_issue_error"]
            if severity == "warning":
                return Decimal("0.3500"), ["quality_issue_warning"]
            return Decimal("0.4500"), ["quality_issue_info"]

        return Decimal("0.0000"), ["unsupported_evidence_type"]

    def _apply_caps(
        self,
        base: Decimal,
        draft: MappedEvidenceDraft,
        source_payload: Mapping[str, Any],
        evidence_payload: Mapping[str, Any],
    ) -> tuple[Decimal, list[str]]:
        score = base
        reasons: list[str] = []

        quality_status = str(draft.quality_status or source_payload.get("quality_status") or "").lower()
        score, reasons = _cap(score, reasons, "quality_warning_cap", Decimal("0.7000"), quality_status == "warning")
        score, reasons = _cap(score, reasons, "quality_error_cap", Decimal("0.3000"), quality_status == "error")

        value_presence = _value_presence(source_payload, draft)
        score, reasons = _cap(
            score,
            reasons,
            "value_not_present_cap",
            Decimal("0.3500"),
            value_presence is not None and value_presence != "present",
        )

        score, reasons = _cap(
            score,
            reasons,
            "low_value_comment_cap",
            Decimal("0.2500"),
            _truthy(source_payload.get("low_value_flag") or evidence_payload.get("low_value_flag")),
        )

        price_check_status = str(source_payload.get("price_check_status") or evidence_payload.get("price_check_status") or "").lower()
        score, reasons = _cap(
            score,
            reasons,
            "price_check_mismatch_cap",
            Decimal("0.7000"),
            price_check_status == "mismatch",
        )

        dimension_quality_flag = str(
            source_payload.get("dimension_quality_flag") or evidence_payload.get("dimension_quality_flag") or ""
        ).lower()
        score, reasons = _cap(
            score,
            reasons,
            "dimension_missing_cap",
            Decimal("0.2500"),
            dimension_quality_flag == "missing",
        )
        return score, reasons


def _cap(score: Decimal, reasons: list[str], reason: str, limit: Decimal, condition: bool) -> tuple[Decimal, list[str]]:
    if condition and score > limit:
        return limit, [*reasons, reason]
    return score, reasons


def _has_any(payload: Mapping[str, Any], *keys: str) -> bool:
    return any(payload.get(key) is not None for key in keys)


def _value_presence(source_payload: Mapping[str, Any], draft: MappedEvidenceDraft) -> str | None:
    value = source_payload.get("value_presence") or draft.value_presence
    if value is None:
        return None
    return str(value).lower()


def _text_present(value: Any) -> bool:
    return value is not None and str(value).strip() not in {"", "-", "unknown", "UNKNOWN", "null", "NULL"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in {"1", "true", "yes", "y"}


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(CONFIDENCE_QUANT, rounding=ROUND_HALF_UP)


def _confidence_level(score: Decimal) -> Core3ConfidenceLevel:
    if score >= Decimal("0.8000"):
        return Core3ConfidenceLevel.HIGH
    if score >= Decimal("0.5500"):
        return Core3ConfidenceLevel.MEDIUM
    if score > Decimal("0.0000"):
        return Core3ConfidenceLevel.LOW
    return Core3ConfidenceLevel.UNKNOWN
