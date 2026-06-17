"""M03 standard parameter value extraction service."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.constants import (
    CORE3_M03_PARSER_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3CategoryCode,
    Core3EvidenceStatus,
    Core3EvidenceType,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_schemas import (
    ParamConfidenceLevel,
    ParamMatchType,
    ParamParserStatus,
    ParamReviewStatus,
    ParamSourceType,
    StdParamDefinition,
    StdParamSeed,
)
from app.services.core3_real_data.param_field_matcher import ParamFieldNormalizer
from app.services.core3_real_data.param_value_parsers import (
    M03_VALUE_UNKNOWN,
    ParamValueParserContext,
    ParamValueParserRegistry,
)


PARAM_VALUE_ID_HASH_VERSION = "m03-param-value-id-v1"
PARAM_VALUE_HASH_VERSION = "m03-param-value-v1"
SOURCE_PRIORITY_RANK = {
    ParamSourceType.RAW_PARAM.value: 1,
    ParamSourceType.DERIVED_FROM_CLAIM.value: 2,
    ParamSourceType.MODEL_NAME.value: 3,
}
SOURCE_TYPE_BY_EVIDENCE_TYPE = {
    Core3EvidenceType.PARAM_RAW.value: ParamSourceType.RAW_PARAM.value,
    Core3EvidenceType.PROMO_SENTENCE.value: ParamSourceType.DERIVED_FROM_CLAIM.value,
    Core3EvidenceType.SKU_FACT.value: ParamSourceType.MODEL_NAME.value,
}
MATCH_CONFIDENCE = {
    ParamMatchType.EXACT_ALIAS.value: Decimal("0.95"),
    ParamMatchType.STANDARD_NAME.value: Decimal("0.93"),
    ParamMatchType.CONTAINS_ALIAS.value: Decimal("0.85"),
    ParamMatchType.KEYWORD.value: Decimal("0.65"),
    ParamMatchType.VALUE_PATTERN.value: Decimal("0.65"),
    ParamMatchType.UNMAPPED.value: Decimal("0.00"),
}


@dataclass(frozen=True)
class ExtractedParamValueDraft:
    param_value_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    model_name: str | None
    param_code: str
    param_name: str
    param_group: str | None
    data_type: str
    normalized_value: dict[str, Any] | list[Any] | str | int | float | bool | None
    numeric_value: Decimal | None
    value_text: str | None
    unit: str | None
    value_level: str | None
    value_presence: str
    source_type: str
    source_priority_rank: int
    raw_param_name: str | None
    raw_param_value: str | None
    match_type: str
    parser_type: str | None
    parser_status: str
    confidence: Decimal
    confidence_level: str
    evidence_ids: list[str]
    primary_evidence_id: str
    quality_flags: list[str]
    conflict_flag: bool
    conflict_id: str | None
    review_required: bool
    review_status: str
    param_value_hash: str
    seed_version: str
    parser_version: str
    rule_version: str

    def with_conflict(self, conflict_id: str, conflict_type: str) -> "ExtractedParamValueDraft":
        quality_flags = _unique_preserve_order([*self.quality_flags, conflict_type])
        confidence = min(self.confidence, Decimal("0.6000"))
        return replace(
            self,
            confidence=confidence,
            confidence_level=_confidence_level(confidence).value,
            quality_flags=quality_flags,
            conflict_flag=True,
            conflict_id=conflict_id,
            review_required=True,
            review_status=ParamReviewStatus.REVIEW_REQUIRED.value,
            param_value_hash=_build_param_value_hash(
                sku_code=self.sku_code,
                param_code=self.param_code,
                normalized_value=self.normalized_value,
                unit=self.unit,
                value_level=self.value_level,
                source_type=self.source_type,
                evidence_ids=self.evidence_ids,
                quality_flags=quality_flags,
                confidence=confidence,
                seed_version=self.seed_version,
                parser_version=self.parser_version,
                rule_version=self.rule_version,
            ),
        )

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "param_value_id": self.param_value_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "model_name": self.model_name,
            "param_code": self.param_code,
            "param_name": self.param_name,
            "param_group": self.param_group,
            "data_type": self.data_type,
            "normalized_value": self.normalized_value,
            "numeric_value": self.numeric_value,
            "value_text": self.value_text,
            "unit": self.unit,
            "value_level": self.value_level,
            "value_presence": self.value_presence,
            "source_type": self.source_type,
            "source_priority_rank": self.source_priority_rank,
            "raw_param_name": self.raw_param_name,
            "raw_param_value": self.raw_param_value,
            "match_type": self.match_type,
            "parser_type": self.parser_type,
            "parser_status": self.parser_status,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "evidence_ids": self.evidence_ids,
            "primary_evidence_id": self.primary_evidence_id,
            "quality_flags": self.quality_flags,
            "conflict_flag": self.conflict_flag,
            "conflict_id": self.conflict_id,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "param_value_hash": self.param_value_hash,
            "seed_version": self.seed_version,
            "parser_version": self.parser_version,
            "rule_version": self.rule_version,
        }


class ParamValueExtractor:
    """Extract standard parameter value candidates from matched field profiles."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        seed: StdParamSeed,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M03_SEED_VERSION,
        parser_version: str = CORE3_M03_PARSER_VERSION,
        rule_version: str = CORE3_M03_RULE_VERSION,
        parser_registry: ParamValueParserRegistry | None = None,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.seed = seed
        self.seed_version = seed_version
        self.parser_version = parser_version
        self.rule_version = rule_version
        self.parser_registry = parser_registry or ParamValueParserRegistry()
        self._standard_params_by_code = {param.param_code: param for param in seed.standard_params}

    def extract_values(
        self,
        evidence_records: Iterable[Any],
        matched_profiles: Iterable[Any],
    ) -> list[ExtractedParamValueDraft]:
        profile_lookup = _build_profile_lookup(matched_profiles)
        values: list[ExtractedParamValueDraft] = []
        for evidence_record in evidence_records:
            if not _is_current_allowed_evidence(evidence_record):
                continue
            clean_param_name = _clean_param_name(evidence_record)
            if clean_param_name is None:
                continue
            profile = profile_lookup.get(ParamFieldNormalizer.normalize(clean_param_name))
            if profile is None:
                continue
            param_code = _field_value(profile, "matched_param_code")
            if not param_code:
                continue
            standard_param = self._standard_params_by_code.get(str(param_code))
            if standard_param is None:
                continue
            values.append(self._extract_one(evidence_record, profile, standard_param, clean_param_name))
        return values

    def _extract_one(
        self,
        evidence_record: Any,
        profile: Any,
        standard_param: StdParamDefinition,
        clean_param_name: str,
    ) -> ExtractedParamValueDraft:
        raw_value = _first_existing(
            _field_value(evidence_record, "clean_value"),
            _field_value(evidence_record, "text_value"),
            _field_value(evidence_record, "normalized_value"),
            _field_value(evidence_record, "raw_value"),
        )
        source_type = _source_type_for_record(evidence_record)
        evidence_id = str(_field_value(evidence_record, "evidence_id") or "")
        sku_code = str(_field_value(evidence_record, "sku_code") or "")
        model_name = _optional_string(_field_value(evidence_record, "model_name"))
        parse_result = self.parser_registry.parse_with_context(
            raw_value,
            standard_param.value_parsers,
            ParamValueParserContext(
                param_code=standard_param.param_code,
                param_name=standard_param.param_name,
                clean_param_name=clean_param_name,
                data_type=str(standard_param.data_type),
                enum_values=standard_param.enum_values,
                keywords=standard_param.keywords,
                unit=standard_param.unit,
            ),
        )
        quality_flags = _unique_preserve_order(parse_result.quality_flags)
        confidence = _compute_confidence(
            source_type=source_type,
            match_type=str(_field_value(profile, "match_type") or ParamMatchType.UNMAPPED.value),
            parser_status=parse_result.parser_status,
            evidence_base_confidence=_decimal(
                _field_value(evidence_record, "base_confidence"),
                Decimal("1.0000"),
            ),
            quality_flags=quality_flags,
        )
        review_required = _value_requires_review(standard_param, parse_result, quality_flags)
        review_status = ParamReviewStatus.REVIEW_REQUIRED if review_required else ParamReviewStatus.AUTO_PASS
        param_value_id = _build_param_value_id(
            project_id=self.project_id,
            batch_id=self.batch_id,
            sku_code=sku_code,
            param_code=standard_param.param_code,
            source_type=source_type,
            primary_evidence_id=evidence_id,
            parser_version=self.parser_version,
        )
        param_value_hash = _build_param_value_hash(
            sku_code=sku_code,
            param_code=standard_param.param_code,
            normalized_value=parse_result.normalized_value,
            unit=parse_result.unit,
            value_level=parse_result.value_level,
            source_type=source_type,
            evidence_ids=[evidence_id],
            quality_flags=quality_flags,
            confidence=confidence,
            seed_version=self.seed_version,
            parser_version=self.parser_version,
            rule_version=self.rule_version,
        )
        return ExtractedParamValueDraft(
            param_value_id=param_value_id,
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=sku_code,
            model_name=model_name,
            param_code=standard_param.param_code,
            param_name=standard_param.param_name,
            param_group=str(standard_param.param_group),
            data_type=str(standard_param.data_type),
            normalized_value=parse_result.normalized_value,
            numeric_value=parse_result.numeric_value,
            value_text=parse_result.value_text,
            unit=parse_result.unit,
            value_level=parse_result.value_level,
            value_presence=parse_result.value_presence,
            source_type=source_type,
            source_priority_rank=SOURCE_PRIORITY_RANK[source_type],
            raw_param_name=_optional_string(_field_value(evidence_record, "evidence_field")),
            raw_param_value=_optional_string(raw_value),
            match_type=str(_field_value(profile, "match_type") or ParamMatchType.UNMAPPED.value),
            parser_type=parse_result.parser_name,
            parser_status=parse_result.parser_status.value,
            confidence=confidence,
            confidence_level=_confidence_level(confidence).value,
            evidence_ids=[evidence_id],
            primary_evidence_id=evidence_id,
            quality_flags=quality_flags,
            conflict_flag=False,
            conflict_id=None,
            review_required=review_required,
            review_status=review_status.value,
            param_value_hash=param_value_hash,
            seed_version=self.seed_version,
            parser_version=self.parser_version,
            rule_version=self.rule_version,
        )


def _build_profile_lookup(matched_profiles: Iterable[Any]) -> dict[str, Any]:
    lookup: dict[str, Any] = {}
    for profile in matched_profiles:
        clean_param_name = _field_value(profile, "clean_param_name")
        if not clean_param_name:
            continue
        lookup[ParamFieldNormalizer.normalize(clean_param_name)] = profile
    return lookup


def _is_current_allowed_evidence(evidence_record: Any) -> bool:
    evidence_status = _field_value(evidence_record, "evidence_status")
    if evidence_status is not None and _enum_value(evidence_status) != Core3EvidenceStatus.CURRENT.value:
        return False
    if _field_value(evidence_record, "is_current") is False:
        return False
    evidence_type = _enum_value(_field_value(evidence_record, "evidence_type"))
    return evidence_type in SOURCE_TYPE_BY_EVIDENCE_TYPE


def _source_type_for_record(evidence_record: Any) -> str:
    explicit_source_type = _field_value(evidence_record, "source_type")
    if explicit_source_type in SOURCE_PRIORITY_RANK:
        return str(explicit_source_type)
    evidence_type = _enum_value(_field_value(evidence_record, "evidence_type"))
    return SOURCE_TYPE_BY_EVIDENCE_TYPE[evidence_type]


def _clean_param_name(evidence_record: Any) -> str | None:
    value = _first_non_empty(
        _field_value(evidence_record, "clean_param_name"),
        _field_value(evidence_record, "clean_attr_name"),
        _field_value(evidence_record, "evidence_field"),
        _field_value(evidence_record, "clean_field"),
        _field_value(evidence_record, "raw_param_name"),
        _field_value(evidence_record, "raw_field"),
    )
    return _optional_string(value)


def _compute_confidence(
    *,
    source_type: str,
    match_type: str,
    parser_status: ParamParserStatus,
    evidence_base_confidence: Decimal,
    quality_flags: list[str],
) -> Decimal:
    if parser_status == ParamParserStatus.UNKNOWN:
        confidence = Decimal("0.3000")
    elif parser_status == ParamParserStatus.FAILED:
        confidence = Decimal("0.2000")
    elif source_type == ParamSourceType.DERIVED_FROM_CLAIM.value:
        confidence = Decimal("0.7000")
    elif source_type == ParamSourceType.MODEL_NAME.value:
        confidence = Decimal("0.6000")
    else:
        confidence = MATCH_CONFIDENCE.get(match_type, Decimal("0.0000"))

    if parser_status == ParamParserStatus.UNIT_UNCERTAIN or "unit_inferred" in quality_flags:
        confidence = min(confidence, Decimal("0.7000"))
    if parser_status == ParamParserStatus.SCOPE_UNCERTAIN or "scope_uncertain" in quality_flags:
        confidence = min(confidence, Decimal("0.7200"))
    if source_type == ParamSourceType.DERIVED_FROM_CLAIM.value:
        confidence = min(confidence, Decimal("0.7500"))
    confidence = min(confidence, evidence_base_confidence + Decimal("0.0500"))
    return _bounded_confidence(confidence)


def _value_requires_review(
    standard_param: StdParamDefinition,
    parse_result: Any,
    quality_flags: list[str],
) -> bool:
    if parse_result.parser_status in {
        ParamParserStatus.FAILED,
        ParamParserStatus.UNIT_UNCERTAIN,
        ParamParserStatus.SCOPE_UNCERTAIN,
    }:
        return True
    if parse_result.parser_status == ParamParserStatus.UNKNOWN and str(standard_param.data_type) == "boolean":
        return True
    return bool({"unit_inferred", "scope_uncertain"} & set(quality_flags))


def _build_param_value_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    param_code: str,
    source_type: str,
    primary_evidence_id: str,
    parser_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "param_code": param_code,
            "source_type": source_type,
            "primary_evidence_id": primary_evidence_id,
            "parser_version": parser_version,
        },
        version=PARAM_VALUE_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m03val_{digest[:32]}"


def _build_param_value_hash(**payload: Any) -> str:
    return stable_hash(payload, version=PARAM_VALUE_HASH_VERSION)


def _field_value(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        return value
    return None


def _first_existing(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except Exception:
        return default


def _bounded_confidence(confidence: Decimal) -> Decimal:
    if confidence < Decimal("0"):
        return Decimal("0.0000")
    if confidence > Decimal("1"):
        return Decimal("1.0000")
    return confidence.quantize(Decimal("0.0001"))


def _confidence_level(confidence: Decimal) -> ParamConfidenceLevel:
    if confidence >= Decimal("0.8500"):
        return ParamConfidenceLevel.HIGH
    if confidence >= Decimal("0.6500"):
        return ParamConfidenceLevel.MEDIUM
    if confidence > Decimal("0.0000"):
        return ParamConfidenceLevel.LOW
    return ParamConfidenceLevel.UNKNOWN


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
