"""M02 evidence payload builder."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from app.services.core3_real_data.constants import Core3EvidenceType
from app.services.core3_real_data.evidence_mappers import MappedEvidenceDraft


class EvidencePayloadError(ValueError):
    pass


class EvidencePayloadBuilder:
    def build_payload(self, draft: MappedEvidenceDraft) -> dict[str, Any]:
        source_payload = draft.source_payload or {}
        builders = {
            Core3EvidenceType.SKU_FACT: self._sku_fact_payload,
            Core3EvidenceType.MARKET_FACT: self._market_fact_payload,
            Core3EvidenceType.PARAM_RAW: self._param_raw_payload,
            Core3EvidenceType.PROMO_RAW: self._promo_raw_payload,
            Core3EvidenceType.PROMO_SENTENCE: self._promo_sentence_payload,
            Core3EvidenceType.COMMENT_RAW: self._comment_raw_payload,
            Core3EvidenceType.COMMENT_SENTENCE: self._comment_sentence_payload,
            Core3EvidenceType.COMMENT_DIMENSION: self._comment_dimension_payload,
            Core3EvidenceType.QUALITY_ISSUE: self._quality_issue_payload,
        }
        builder = builders.get(draft.evidence_type)
        if builder is None:
            raise EvidencePayloadError(f"unsupported evidence_type: {draft.evidence_type}")
        payload = builder(source_payload)
        return _json_safe_dict(payload)

    def build_atom_values(self, draft: MappedEvidenceDraft) -> dict[str, Any]:
        values = draft.to_base_payload()
        values["evidence_payload_json"] = self.build_payload(draft)
        return _json_safe_dict(values)

    def _sku_fact_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "coverage_json": payload.get("coverage_json") or {},
            "field_conflicts_json": payload.get("field_conflicts_json") or {},
            "missing_signals_json": payload.get("missing_signals_json") or {},
        }

    def _market_fact_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "period_raw": payload.get("period_raw"),
            "channel_type": payload.get("channel_type"),
            "platform_type": payload.get("platform_type"),
            "sales_volume": payload.get("sales_volume"),
            "sales_amount": payload.get("sales_amount"),
            "avg_price": payload.get("avg_price"),
            "price_check_status": payload.get("price_check_status"),
        }

    def _param_raw_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "raw_attr_name": payload.get("raw_attr_name"),
            "clean_attr_name": payload.get("clean_attr_name"),
            "raw_attr_value": payload.get("raw_attr_value"),
            "clean_attr_value": payload.get("clean_attr_value"),
            "value_presence": payload.get("value_presence"),
            "number_candidates": payload.get("value_number_candidates") or [],
            "unit_candidates": payload.get("value_unit_candidates") or [],
        }

    def _promo_raw_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "claim_seq": payload.get("claim_seq"),
            "raw_claim_text": payload.get("raw_claim_text"),
            "clean_claim_text": payload.get("clean_claim_text"),
            "title_hint": payload.get("title_hint"),
        }

    def _promo_sentence_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "claim_seq": payload.get("claim_seq"),
            "sentence_seq": payload.get("sentence_seq"),
            "sentence_text": payload.get("sentence_text"),
            "sentence_role_hint": payload.get("sentence_role_hint"),
        }

    def _comment_raw_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "comment_id": payload.get("comment_id"),
            "clean_comment_text": payload.get("clean_comment_text"),
            "comment_text_hash": payload.get("comment_text_hash"),
            "segment_text_hash": payload.get("segment_text_hash"),
            "sentiment_clean": payload.get("sentiment_clean"),
            "low_value_flag": payload.get("low_value_flag") or False,
            "duplicate_group_key": payload.get("duplicate_group_key"),
        }

    def _comment_sentence_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "comment_id": payload.get("comment_id"),
            "sentence_source": payload.get("sentence_source"),
            "sentence_seq": payload.get("sentence_seq"),
            "sentence_text": payload.get("sentence_text"),
            "sentiment_clean": payload.get("sentiment_clean"),
            "low_value_flag": payload.get("low_value_flag") or False,
        }

    def _comment_dimension_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "primary_dim_raw": payload.get("primary_dim_raw"),
            "secondary_dim_raw": payload.get("secondary_dim_raw"),
            "third_dim_raw": payload.get("third_dim_raw"),
            "dimension_path_raw": payload.get("dimension_path_raw"),
            "dimension_quality_flag": payload.get("dimension_quality_flag"),
        }

    def _quality_issue_payload(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "domain": payload.get("domain"),
            "issue_type": payload.get("issue_type"),
            "severity": payload.get("severity"),
            "issue_detail": payload.get("issue_detail"),
            "suggested_downstream_action": payload.get("suggested_downstream_action"),
        }


def _json_safe_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(payload[key]) for key in sorted(payload)}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return _json_safe_dict(value)
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value
