"""M02 evidence ID and clean-fact mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M02_CLEAN_SOURCE_TABLES,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    Core3CategoryCode,
    Core3CleanQualityStatus,
    Core3EvidenceGrain,
    Core3EvidenceType,
)
from app.services.core3_real_data.hash_utils import stable_hash


class EvidenceMappingError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceIdentity:
    evidence_key: str
    evidence_id: str


@dataclass(frozen=True)
class EvidenceMappingRule:
    clean_table: str
    evidence_type: Core3EvidenceType
    evidence_grain: Core3EvidenceGrain
    default_evidence_field: str
    title_cn: str


@dataclass(frozen=True)
class MappedEvidenceDraft:
    project_id: str
    category_code: str
    batch_id: str
    evidence_type: Core3EvidenceType
    evidence_grain: Core3EvidenceGrain
    evidence_field: str
    evidence_title: str
    clean_table: str
    clean_record_key: str
    clean_hash: str
    clean_version: str
    evidence_key: str
    evidence_id: str
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    source_table: str | None = None
    source_pk: str | None = None
    source_row_id: str | None = None
    source_row_hash: str | None = None
    raw_field: str | None = None
    raw_value: Any | None = None
    clean_field: str | None = None
    clean_value: Any | None = None
    value_presence: str | None = None
    numeric_value: Decimal | None = None
    numeric_values_json: list[Any] | None = None
    unit_value: str | None = None
    text_value: str | None = None
    text_hash: str | None = None
    evidence_time: Any | None = None
    period_raw: str | None = None
    period_week_index: int | None = None
    channel_type: str | None = None
    platform_type: str | None = None
    comment_id: str | None = None
    comment_text_hash: str | None = None
    segment_text_hash: str | None = None
    sentence_seq: int | None = None
    dimension_path_raw: str | None = None
    quality_status: str = Core3CleanQualityStatus.OK.value
    quality_flags: list[str] | None = None
    source_payload: dict[str, Any] | None = None

    def to_base_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "brand_name": self.brand_name,
            "evidence_type": self.evidence_type.value,
            "evidence_grain": self.evidence_grain.value,
            "evidence_field": self.evidence_field,
            "evidence_title": self.evidence_title,
            "source_table": self.source_table,
            "source_pk": self.source_pk,
            "source_row_id": self.source_row_id,
            "source_row_hash": self.source_row_hash,
            "clean_table": self.clean_table,
            "clean_record_key": self.clean_record_key,
            "clean_hash": self.clean_hash,
            "clean_version": self.clean_version,
            "evidence_key": self.evidence_key,
            "evidence_id": self.evidence_id,
            "raw_field": self.raw_field,
            "raw_value": self.raw_value,
            "clean_field": self.clean_field,
            "clean_value": self.clean_value,
            "value_presence": self.value_presence,
            "numeric_value": self.numeric_value,
            "numeric_values_json": self.numeric_values_json or [],
            "unit_value": self.unit_value,
            "text_value": self.text_value,
            "text_hash": self.text_hash,
            "evidence_time": self.evidence_time,
            "period_raw": self.period_raw,
            "period_week_index": self.period_week_index,
            "channel_type": self.channel_type,
            "platform_type": self.platform_type,
            "comment_id": self.comment_id,
            "comment_text_hash": self.comment_text_hash,
            "segment_text_hash": self.segment_text_hash,
            "sentence_seq": self.sentence_seq,
            "dimension_path_raw": self.dimension_path_raw,
            "quality_status": self.quality_status,
            "quality_flags": self.quality_flags or [],
        }


M02_EVIDENCE_MAPPING_RULES: dict[str, EvidenceMappingRule] = {
    "core3_clean_sku": EvidenceMappingRule(
        clean_table="core3_clean_sku",
        evidence_type=Core3EvidenceType.SKU_FACT,
        evidence_grain=Core3EvidenceGrain.SKU,
        default_evidence_field="sku_coverage",
        title_cn="SKU 清洗覆盖证据",
    ),
    "core3_clean_market_weekly": EvidenceMappingRule(
        clean_table="core3_clean_market_weekly",
        evidence_type=Core3EvidenceType.MARKET_FACT,
        evidence_grain=Core3EvidenceGrain.ROW,
        default_evidence_field="market_weekly",
        title_cn="周度市场量价证据",
    ),
    "core3_clean_attribute": EvidenceMappingRule(
        clean_table="core3_clean_attribute",
        evidence_type=Core3EvidenceType.PARAM_RAW,
        evidence_grain=Core3EvidenceGrain.FIELD,
        default_evidence_field="param_raw",
        title_cn="参数原始证据",
    ),
    "core3_clean_claim": EvidenceMappingRule(
        clean_table="core3_clean_claim",
        evidence_type=Core3EvidenceType.PROMO_RAW,
        evidence_grain=Core3EvidenceGrain.ROW,
        default_evidence_field="promo_raw",
        title_cn="卖点原文证据",
    ),
    "core3_clean_claim_sentence": EvidenceMappingRule(
        clean_table="core3_clean_claim_sentence",
        evidence_type=Core3EvidenceType.PROMO_SENTENCE,
        evidence_grain=Core3EvidenceGrain.SENTENCE,
        default_evidence_field="promo_sentence",
        title_cn="卖点句级证据",
    ),
    "core3_clean_comment": EvidenceMappingRule(
        clean_table="core3_clean_comment",
        evidence_type=Core3EvidenceType.COMMENT_RAW,
        evidence_grain=Core3EvidenceGrain.ROW,
        default_evidence_field="comment_raw",
        title_cn="评论原文证据",
    ),
    "core3_clean_comment_sentence": EvidenceMappingRule(
        clean_table="core3_clean_comment_sentence",
        evidence_type=Core3EvidenceType.COMMENT_SENTENCE,
        evidence_grain=Core3EvidenceGrain.SENTENCE,
        default_evidence_field="comment_sentence",
        title_cn="评论句级证据",
    ),
    "core3_clean_comment_dimension": EvidenceMappingRule(
        clean_table="core3_clean_comment_dimension",
        evidence_type=Core3EvidenceType.COMMENT_DIMENSION,
        evidence_grain=Core3EvidenceGrain.DIMENSION,
        default_evidence_field="comment_dimension",
        title_cn="评论原始维度证据",
    ),
    "core3_data_quality_issue": EvidenceMappingRule(
        clean_table="core3_data_quality_issue",
        evidence_type=Core3EvidenceType.QUALITY_ISSUE,
        evidence_grain=Core3EvidenceGrain.QUALITY,
        default_evidence_field="quality_issue",
        title_cn="数据质量问题证据",
    ),
}


class EvidenceIdService:
    def build_evidence_key(
        self,
        *,
        project_id: str,
        category_code: Core3CategoryCode | str,
        batch_id: str,
        evidence_type: Core3EvidenceType | str,
        clean_table: str,
        clean_record_key: str,
        evidence_field: str,
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
    ) -> str:
        category_value = _enum_value(category_code)
        evidence_type_value = _enum_value(evidence_type)
        for field_name, value in {
            "project_id": project_id,
            "category_code": category_value,
            "batch_id": batch_id,
            "evidence_type": evidence_type_value,
            "clean_table": clean_table,
            "clean_record_key": clean_record_key,
            "evidence_field": evidence_field,
            "evidence_version": evidence_version,
        }.items():
            _require_non_empty(field_name, value)
        if clean_table not in CORE3_M02_CLEAN_SOURCE_TABLES:
            raise EvidenceMappingError(f"unknown clean_table: {clean_table}")

        return stable_hash(
            {
                "project_id": project_id,
                "category_code": category_value,
                "batch_id": batch_id,
                "evidence_type": evidence_type_value,
                "clean_table": clean_table,
                "clean_record_key": clean_record_key,
                "evidence_field": evidence_field,
                "evidence_version": evidence_version,
            },
            version=f"{evidence_version}_key",
        )

    def build_evidence_id(
        self,
        *,
        evidence_key: str,
        clean_hash: str,
        source_row_hash: str | None,
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
    ) -> str:
        for field_name, value in {
            "evidence_key": evidence_key,
            "clean_hash": clean_hash,
            "evidence_version": evidence_version,
        }.items():
            _require_non_empty(field_name, value)

        return stable_hash(
            {
                "evidence_key": evidence_key,
                "clean_hash": clean_hash,
                "source_row_hash": source_row_hash,
                "evidence_version": evidence_version,
            },
            version=f"{evidence_version}_id",
        )

    def build_identity(
        self,
        *,
        project_id: str,
        category_code: Core3CategoryCode | str,
        batch_id: str,
        evidence_type: Core3EvidenceType | str,
        clean_table: str,
        clean_record_key: str,
        evidence_field: str,
        clean_hash: str,
        source_row_hash: str | None,
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
    ) -> EvidenceIdentity:
        evidence_key = self.build_evidence_key(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            evidence_type=evidence_type,
            clean_table=clean_table,
            clean_record_key=clean_record_key,
            evidence_field=evidence_field,
            evidence_version=evidence_version,
        )
        evidence_id = self.build_evidence_id(
            evidence_key=evidence_key,
            clean_hash=clean_hash,
            source_row_hash=source_row_hash,
            evidence_version=evidence_version,
        )
        return EvidenceIdentity(evidence_key=evidence_key, evidence_id=evidence_id)


class EvidenceMapper:
    def __init__(self, id_service: EvidenceIdService | None = None) -> None:
        self.id_service = id_service or EvidenceIdService()

    @property
    def mapping_rules(self) -> dict[str, EvidenceMappingRule]:
        return dict(M02_EVIDENCE_MAPPING_RULES)

    def map_clean_record(
        self,
        record: Mapping[str, Any] | Any,
        *,
        clean_table: str | None = None,
        evidence_version: str = CORE3_M02_EVIDENCE_VERSION,
    ) -> MappedEvidenceDraft:
        payload = _record_payload(record)
        source_clean_table = self._resolve_clean_table(record, clean_table)
        rule = M02_EVIDENCE_MAPPING_RULES.get(source_clean_table)
        if rule is None:
            raise EvidenceMappingError(f"unknown clean_table: {source_clean_table}")

        base = self._base_fields(payload, rule.clean_table)
        evidence_field = self._evidence_field(rule, payload)
        identity = self.id_service.build_identity(
            project_id=base["project_id"],
            category_code=base["category_code"],
            batch_id=base["batch_id"],
            evidence_type=rule.evidence_type,
            clean_table=rule.clean_table,
            clean_record_key=base["clean_record_key"],
            evidence_field=evidence_field,
            clean_hash=base["clean_hash"],
            source_row_hash=base.get("source_row_hash"),
            evidence_version=evidence_version,
        )
        mapped_fields = self._mapped_fields(rule.clean_table, payload, rule)
        return MappedEvidenceDraft(
            **base,
            evidence_type=rule.evidence_type,
            evidence_grain=rule.evidence_grain,
            evidence_field=evidence_field,
            evidence_title=self._evidence_title(rule, payload),
            evidence_key=identity.evidence_key,
            evidence_id=identity.evidence_id,
            source_payload=payload,
            **mapped_fields,
        )

    def _resolve_clean_table(self, record: Mapping[str, Any] | Any, clean_table: str | None) -> str:
        if clean_table is not None:
            return clean_table
        table = getattr(getattr(record, "__table__", None), "name", None)
        if table is not None:
            return table
        if isinstance(record, Mapping):
            source_clean_table = record.get("source_clean_table")
            if source_clean_table:
                return str(source_clean_table)
        raise EvidenceMappingError("clean_table is required for mapping payload records")

    def _base_fields(self, payload: Mapping[str, Any], clean_table: str) -> dict[str, Any]:
        required_fields = ("project_id", "batch_id", "clean_record_key", "clean_hash", "clean_version")
        for field_name in required_fields:
            _require_non_empty(field_name, payload.get(field_name))

        source_table = _optional_str(payload.get("source_table"))
        if source_table is not None and source_table not in CORE3_RAW_SOURCE_TABLES:
            raise EvidenceMappingError(f"unknown source_table: {source_table}")

        return {
            "project_id": str(payload["project_id"]),
            "category_code": str(payload.get("category_code") or Core3CategoryCode.TV.value),
            "batch_id": str(payload["batch_id"]),
            "run_id": _optional_str(payload.get("run_id")),
            "module_run_id": _optional_str(payload.get("module_run_id")),
            "sku_code": _optional_str(payload.get("sku_code")),
            "model_name": _optional_str(payload.get("model_name")),
            "brand_name": _optional_str(payload.get("brand_name")),
            "source_table": source_table,
            "source_pk": _optional_str(payload.get("source_pk")),
            "source_row_id": _optional_str(payload.get("source_row_id")),
            "source_row_hash": _optional_str(payload.get("source_row_hash")),
            "clean_table": clean_table,
            "clean_record_key": str(payload["clean_record_key"]),
            "clean_hash": str(payload["clean_hash"]),
            "clean_version": str(payload["clean_version"]),
            "quality_status": str(payload.get("quality_status") or Core3CleanQualityStatus.OK.value),
            "quality_flags": _list_value(payload.get("quality_flags")),
        }

    def _evidence_field(self, rule: EvidenceMappingRule, payload: Mapping[str, Any]) -> str:
        if rule.clean_table == "core3_clean_attribute":
            return _first_non_empty(payload.get("clean_attr_name"), payload.get("raw_attr_name"), rule.default_evidence_field)
        if rule.clean_table == "core3_clean_claim":
            claim_seq = payload.get("claim_seq")
            return f"promo_raw:{claim_seq}" if claim_seq is not None else rule.default_evidence_field
        if rule.clean_table == "core3_clean_claim_sentence":
            return f"promo_sentence:{_safe_part(payload.get('claim_seq'))}:{_safe_part(payload.get('sentence_seq'))}"
        if rule.clean_table == "core3_clean_comment_sentence":
            return f"comment_sentence:{_safe_part(payload.get('sentence_source'))}:{_safe_part(payload.get('sentence_seq'))}"
        if rule.clean_table == "core3_data_quality_issue":
            return f"quality_issue:{_safe_part(payload.get('domain'))}:{_safe_part(payload.get('issue_type'))}"
        return rule.default_evidence_field

    def _evidence_title(self, rule: EvidenceMappingRule, payload: Mapping[str, Any]) -> str:
        if rule.clean_table == "core3_clean_attribute":
            attr_name = _first_non_empty(payload.get("clean_attr_name"), payload.get("raw_attr_name"), "")
            return f"{attr_name}参数原始证据" if attr_name else rule.title_cn
        return rule.title_cn

    def _mapped_fields(
        self,
        clean_table: str,
        payload: Mapping[str, Any],
        rule: EvidenceMappingRule,
    ) -> dict[str, Any]:
        if clean_table == "core3_clean_sku":
            return {
                "raw_field": "sku_code",
                "raw_value": payload.get("sku_code"),
                "clean_field": "coverage",
                "clean_value": payload.get("sku_code"),
            }
        if clean_table == "core3_clean_market_weekly":
            return {
                "raw_field": "market_row",
                "clean_field": "market_weekly",
                "numeric_value": payload.get("avg_price"),
                "numeric_values_json": [
                    {"field": "sales_volume", "value": payload.get("sales_volume")},
                    {"field": "sales_amount", "value": payload.get("sales_amount")},
                    {"field": "avg_price", "value": payload.get("avg_price")},
                ],
                "period_raw": _optional_str(payload.get("period_raw")),
                "period_week_index": payload.get("period_week_index"),
                "channel_type": _optional_str(payload.get("channel_type")),
                "platform_type": _optional_str(payload.get("platform_type")),
            }
        if clean_table == "core3_clean_attribute":
            return {
                "raw_field": _optional_str(payload.get("raw_attr_name")),
                "raw_value": payload.get("raw_attr_value"),
                "clean_field": _optional_str(payload.get("clean_attr_name")),
                "clean_value": payload.get("clean_attr_value"),
                "value_presence": _optional_str(payload.get("value_presence")),
                "numeric_values_json": _list_value(payload.get("value_number_candidates")),
                "unit_value": _first_unit(payload.get("value_unit_candidates")),
                "text_value": payload.get("clean_attr_value"),
            }
        if clean_table == "core3_clean_claim":
            return {
                "raw_field": "raw_claim_text",
                "raw_value": payload.get("raw_claim_text"),
                "clean_field": "clean_claim_text",
                "clean_value": payload.get("clean_claim_text"),
                "value_presence": _optional_str(payload.get("claim_text_presence")),
                "text_value": payload.get("clean_claim_text"),
            }
        if clean_table == "core3_clean_claim_sentence":
            return {
                "raw_field": "sentence_text",
                "raw_value": payload.get("sentence_text"),
                "clean_field": "sentence_text",
                "clean_value": payload.get("sentence_text"),
                "text_value": payload.get("sentence_text"),
                "text_hash": _optional_str(payload.get("sentence_text_hash")),
                "sentence_seq": payload.get("sentence_seq"),
            }
        if clean_table == "core3_clean_comment":
            return {
                "raw_field": "raw_comment_text",
                "raw_value": payload.get("raw_comment_text"),
                "clean_field": "clean_comment_text",
                "clean_value": payload.get("clean_comment_text"),
                "value_presence": _optional_str(payload.get("comment_text_presence")),
                "text_value": payload.get("clean_comment_text"),
                "comment_id": _optional_str(payload.get("comment_id")),
                "comment_text_hash": _optional_str(payload.get("comment_text_hash")),
                "segment_text_hash": _optional_str(payload.get("segment_text_hash")),
                "evidence_time": payload.get("comment_time"),
            }
        if clean_table == "core3_clean_comment_sentence":
            return {
                "raw_field": "sentence_text",
                "raw_value": payload.get("sentence_text"),
                "clean_field": "sentence_text",
                "clean_value": payload.get("sentence_text"),
                "text_value": payload.get("sentence_text"),
                "text_hash": _optional_str(payload.get("sentence_text_hash")),
                "comment_id": _optional_str(payload.get("comment_id")),
                "sentence_seq": payload.get("sentence_seq"),
            }
        if clean_table == "core3_clean_comment_dimension":
            return {
                "raw_field": "dimension_path_raw",
                "raw_value": payload.get("dimension_path_raw"),
                "clean_field": "dimension_path_raw",
                "clean_value": payload.get("dimension_path_raw"),
                "comment_id": _optional_str(payload.get("comment_id")),
                "dimension_path_raw": _optional_str(payload.get("dimension_path_raw")),
            }
        if clean_table == "core3_data_quality_issue":
            return {
                "raw_field": "issue_type",
                "raw_value": payload.get("issue_type"),
                "clean_field": "issue_detail",
                "clean_value": payload.get("issue_detail"),
                "text_value": payload.get("issue_detail"),
            }
        raise EvidenceMappingError(f"unknown clean_table: {clean_table}")


def _record_payload(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    table = getattr(record, "__table__", None)
    if table is not None:
        return {column.name: getattr(record, column.name) for column in table.columns}
    return dict(vars(record))


def _enum_value(value: Enum | str) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _require_non_empty(field_name: str, value: Any) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise EvidenceMappingError(f"{field_name} is required")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _safe_part(value: Any) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        return "unknown"
    return str(value)


def _list_value(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _first_unit(value: Any) -> str | None:
    units = _list_value(value)
    if not units:
        return None
    return _optional_str(units[0])
