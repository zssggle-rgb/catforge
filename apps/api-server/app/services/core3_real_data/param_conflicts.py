"""M03 parameter conflict detection."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.constants import CORE3_M03_RULE_VERSION, Core3CategoryCode
from app.services.core3_real_data.hash_utils import canonicalize_json, stable_hash
from app.services.core3_real_data.param_extraction_schemas import (
    ParamConflictType,
    ParamReviewStatus,
    ParamSourceType,
)
from app.services.core3_real_data.param_extraction_service import ExtractedParamValueDraft


PARAM_CONFLICT_ID_HASH_VERSION = "m03-param-conflict-id-v1"
PARAM_VALUE_PRESENT = "present"
PARAM_VALUE_UNKNOWN = "unknown"
HDMI_CONFLICT_PARAM_CODE = "hdmi_2_1_ports"


@dataclass(frozen=True)
class ParamValueConflictDraft:
    conflict_id: str
    project_id: str
    category_code: str
    batch_id: str
    run_id: str | None
    module_run_id: str | None
    sku_code: str
    param_code: str
    conflict_type: str
    candidate_values_json: list[dict[str, Any]]
    preferred_value_json: dict[str, Any] | list[Any] | str | int | float | bool | None
    preferred_source_type: str | None
    confidence: Decimal
    evidence_ids: list[str]
    quality_flags: list[str]
    review_required: bool
    review_status: str
    review_reason: dict[str, Any]
    rule_version: str

    def to_record_payload(self) -> dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": self.sku_code,
            "param_code": self.param_code,
            "conflict_type": self.conflict_type,
            "candidate_values_json": self.candidate_values_json,
            "preferred_value_json": self.preferred_value_json,
            "preferred_source_type": self.preferred_source_type,
            "confidence": self.confidence,
            "evidence_ids": self.evidence_ids,
            "quality_flags": self.quality_flags,
            "review_required": self.review_required,
            "review_status": self.review_status,
            "review_reason": self.review_reason,
            "rule_version": self.rule_version,
        }


class ParamConflictDetector:
    """Detect review-required conflicts across extracted M03 parameter values."""

    def __init__(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M03_RULE_VERSION,
    ) -> None:
        self.project_id = project_id
        self.batch_id = batch_id
        self.category_code = _enum_value(category_code)
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.rule_version = rule_version

    def detect_conflicts(self, values: Iterable[ExtractedParamValueDraft]) -> list[ParamValueConflictDraft]:
        value_list = list(values)
        conflicts: list[ParamValueConflictDraft] = []
        grouped_values = _group_by_sku_param(value_list)
        for (sku_code, param_code), group in sorted(grouped_values.items()):
            conflicts.extend(self._detect_group_conflicts(sku_code, param_code, group))
        conflicts.extend(self._detect_hdmi_mixed_conflicts(value_list))
        return _dedupe_conflicts(conflicts)

    def apply_conflicts(
        self,
        values: Iterable[ExtractedParamValueDraft],
    ) -> tuple[list[ExtractedParamValueDraft], list[ParamValueConflictDraft]]:
        value_list = list(values)
        conflicts = self.detect_conflicts(value_list)
        conflict_by_sku_param: dict[tuple[str, str], ParamValueConflictDraft] = {}
        for conflict in conflicts:
            conflict_by_sku_param.setdefault((conflict.sku_code, conflict.param_code), conflict)

        updated_values: list[ExtractedParamValueDraft] = []
        for value in value_list:
            conflict = conflict_by_sku_param.get((value.sku_code, value.param_code))
            if conflict is None:
                updated_values.append(value)
            else:
                updated_values.append(value.with_conflict(conflict.conflict_id, conflict.conflict_type))
        return updated_values, conflicts

    def _detect_group_conflicts(
        self,
        sku_code: str,
        param_code: str,
        group: list[ExtractedParamValueDraft],
    ) -> list[ParamValueConflictDraft]:
        conflicts: list[ParamValueConflictDraft] = []
        present_values = [value for value in group if _is_present_value(value)]
        distinct_present_values = {
            canonicalize_json(_comparable_value(value.normalized_value))
            for value in present_values
            if value.normalized_value is not None
        }
        source_types = {value.source_type for value in present_values}

        if len(distinct_present_values) > 1:
            if {
                ParamSourceType.RAW_PARAM.value,
                ParamSourceType.DERIVED_FROM_CLAIM.value,
            }.issubset(source_types):
                conflicts.append(
                    self._build_conflict(
                        sku_code,
                        param_code,
                        group,
                        ParamConflictType.RAW_PARAM_VS_CLAIM_CONFLICT,
                    )
                )
            else:
                conflicts.append(
                    self._build_conflict(
                        sku_code,
                        param_code,
                        group,
                        ParamConflictType.SAME_PARAM_MULTI_VALUE,
                    )
                )

        if any(_has_quality(value, "unit_inferred") or value.parser_status == "unit_uncertain" for value in group):
            conflicts.append(
                self._build_conflict(sku_code, param_code, group, ParamConflictType.UNIT_UNCERTAIN)
            )
        if any(_has_quality(value, "scope_uncertain") or value.parser_status == "scope_uncertain" for value in group):
            conflicts.append(
                self._build_conflict(sku_code, param_code, group, ParamConflictType.SCOPE_UNCERTAIN)
            )
        if any(
            value.data_type == "boolean" and value.value_presence == PARAM_VALUE_UNKNOWN
            for value in group
        ):
            conflicts.append(
                self._build_conflict(sku_code, param_code, group, ParamConflictType.BOOLEAN_UNKNOWN)
            )
        return conflicts

    def _detect_hdmi_mixed_conflicts(
        self,
        values: list[ExtractedParamValueDraft],
    ) -> list[ParamValueConflictDraft]:
        conflicts: list[ParamValueConflictDraft] = []
        values_by_sku: dict[str, list[ExtractedParamValueDraft]] = {}
        for value in values:
            values_by_sku.setdefault(value.sku_code, []).append(value)

        for sku_code, sku_values in sorted(values_by_sku.items()):
            hdmi_values = [
                value
                for value in sku_values
                if value.param_code == HDMI_CONFLICT_PARAM_CODE or "hdmi" in value.param_code.lower()
            ]
            version_only = [
                value
                for value in hdmi_values
                if isinstance(value.normalized_value, Mapping)
                and value.normalized_value.get("hdmi_version")
                and value.normalized_value.get("port_count") is None
            ]
            count_only = [
                value
                for value in hdmi_values
                if isinstance(value.normalized_value, Mapping)
                and value.normalized_value.get("port_count") is not None
                and value.normalized_value.get("hdmi_version") is None
            ]
            if version_only and count_only:
                conflicts.append(
                    self._build_conflict(
                        sku_code,
                        HDMI_CONFLICT_PARAM_CODE,
                        [*version_only, *count_only],
                        ParamConflictType.HDMI_VERSION_COUNT_MIXED,
                    )
                )
        return conflicts

    def _build_conflict(
        self,
        sku_code: str,
        param_code: str,
        values: list[ExtractedParamValueDraft],
        conflict_type: ParamConflictType,
    ) -> ParamValueConflictDraft:
        preferred_value = _preferred_value(values)
        evidence_ids = _unique_preserve_order(
            evidence_id
            for value in values
            for evidence_id in value.evidence_ids
            if evidence_id
        )
        quality_flags = _unique_preserve_order(
            [conflict_type.value, *[flag for value in values for flag in value.quality_flags]]
        )
        conflict_id = _build_conflict_id(
            project_id=self.project_id,
            batch_id=self.batch_id,
            sku_code=sku_code,
            param_code=param_code,
            conflict_type=conflict_type.value,
            rule_version=self.rule_version,
        )
        return ParamValueConflictDraft(
            conflict_id=conflict_id,
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_id=self.run_id,
            module_run_id=self.module_run_id,
            sku_code=sku_code,
            param_code=param_code,
            conflict_type=conflict_type.value,
            candidate_values_json=[_candidate_value_payload(value) for value in values],
            preferred_value_json=preferred_value.normalized_value if preferred_value is not None else None,
            preferred_source_type=preferred_value.source_type if preferred_value is not None else None,
            confidence=min(preferred_value.confidence if preferred_value is not None else Decimal("0"), Decimal("0.6000")),
            evidence_ids=evidence_ids,
            quality_flags=quality_flags,
            review_required=True,
            review_status=ParamReviewStatus.REVIEW_REQUIRED.value,
            review_reason={
                "reason_code": conflict_type.value,
                "message_cn": _review_message(conflict_type),
            },
            rule_version=self.rule_version,
        )


def _group_by_sku_param(
    values: list[ExtractedParamValueDraft],
) -> dict[tuple[str, str], list[ExtractedParamValueDraft]]:
    grouped: dict[tuple[str, str], list[ExtractedParamValueDraft]] = {}
    for value in values:
        grouped.setdefault((value.sku_code, value.param_code), []).append(value)
    return grouped


def _is_present_value(value: ExtractedParamValueDraft) -> bool:
    return value.value_presence == PARAM_VALUE_PRESENT and value.normalized_value is not None


def _comparable_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: item for key, item in value.items() if item is not None}
    return value


def _has_quality(value: ExtractedParamValueDraft, quality_flag: str) -> bool:
    return quality_flag in set(value.quality_flags)


def _preferred_value(values: list[ExtractedParamValueDraft]) -> ExtractedParamValueDraft | None:
    present_values = [value for value in values if _is_present_value(value)]
    candidates = present_values or values
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda value: (
            value.source_priority_rank,
            -value.confidence,
            value.param_value_id,
        ),
    )[0]


def _candidate_value_payload(value: ExtractedParamValueDraft) -> dict[str, Any]:
    return {
        "param_value_id": value.param_value_id,
        "sku_code": value.sku_code,
        "param_code": value.param_code,
        "normalized_value": value.normalized_value,
        "numeric_value": str(value.numeric_value) if value.numeric_value is not None else None,
        "value_text": value.value_text,
        "value_presence": value.value_presence,
        "source_type": value.source_type,
        "parser_status": value.parser_status,
        "confidence": str(value.confidence),
        "evidence_ids": value.evidence_ids,
        "quality_flags": value.quality_flags,
    }


def _review_message(conflict_type: ParamConflictType) -> str:
    return {
        ParamConflictType.SAME_PARAM_MULTI_VALUE: "同一 SKU 同一标准参数存在多个不同取值，需确认主值。",
        ParamConflictType.RAW_PARAM_VS_CLAIM_CONFLICT: "参数表与宣传派生参数取值不一致，默认原始参数优先，需复核。",
        ParamConflictType.UNIT_UNCERTAIN: "参数值单位不明确或由字段语义推断，需复核。",
        ParamConflictType.SCOPE_UNCERTAIN: "参数口径不明确，需复核原生、系统或动态口径。",
        ParamConflictType.BOOLEAN_UNKNOWN: "布尔参数为空或未知，只能标记 unknown，不能当作 false。",
        ParamConflictType.HDMI_VERSION_COUNT_MIXED: "HDMI 版本和接口数量来自不同证据，不能合成为 HDMI2.1 接口数。",
    }[conflict_type]


def _build_conflict_id(
    *,
    project_id: str,
    batch_id: str,
    sku_code: str,
    param_code: str,
    conflict_type: str,
    rule_version: str,
) -> str:
    digest = stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "param_code": param_code,
            "conflict_type": conflict_type,
            "rule_version": rule_version,
        },
        version=PARAM_CONFLICT_ID_HASH_VERSION,
    ).split(":")[-1]
    return f"m03conf_{digest[:32]}"


def _dedupe_conflicts(conflicts: list[ParamValueConflictDraft]) -> list[ParamValueConflictDraft]:
    result: list[ParamValueConflictDraft] = []
    seen_keys: set[tuple[str, str, str]] = set()
    for conflict in conflicts:
        key = (conflict.sku_code, conflict.param_code, conflict.conflict_type)
        if key in seen_keys:
            continue
        result.append(conflict)
        seen_keys.add(key)
    return result


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
