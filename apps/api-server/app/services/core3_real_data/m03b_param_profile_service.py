"""M03B SKU parameter fact profiles and tier coverage.

M03B is intentionally deterministic. It consumes only M02 ``param_raw`` evidence
and a published/manual TV parameter taxonomy asset. It does not read claims,
comments, market facts, or quality text.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M03B_MODULE_VERSION,
    CORE3_M03B_PARSER_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_extraction_repositories import (
    ParamExtractionRepository,
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.repositories import Core3BaseRepository, Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


M03B_PARAM_VALUE_ID_HASH_VERSION = "m03b-param-value-id-v1"
M03B_PARAM_VALUE_HASH_VERSION = "m03b-param-value-v1"
M03B_SKU_PROFILE_ID_HASH_VERSION = "m03b-sku-param-profile-id-v1"
M03B_SKU_PROFILE_HASH_VERSION = "m03b-sku-param-profile-v1"
M03B_DIMENSION_TIER_ID_HASH_VERSION = "m03b-dimension-tier-id-v1"
M03B_DIMENSION_TIER_HASH_VERSION = "m03b-dimension-tier-v1"
M03B_TIER_COVERAGE_ID_HASH_VERSION = "m03b-tier-coverage-id-v1"
M03B_TIER_COVERAGE_HASH_VERSION = "m03b-tier-coverage-v1"

VALUE_PRESENT = "present"
VALUE_UNKNOWN = "unknown"
VALUE_DERIVED_FALSE = "derived_false"
SOURCE_RAW_PARAM = "raw_param"
SOURCE_TAXONOMY_RULE = "taxonomy_rule"
MATCH_EXACT_MANUAL = "manual_taxonomy_mapping"

UNKNOWN_LITERALS = frozenset({"", "-", "--", "---", "unknown", "unk", "null", "none", "n/a", "na", "暂无", "未知", "不详"})
FALSE_LITERALS = frozenset({"否", "无", "不支持", "false", "no", "n", "0", "非miniled", "非mini led", "非全面屏"})
TRUE_LITERALS = frozenset({"是", "有", "支持", "true", "yes", "y", "1"})
NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
RESOLUTION_PATTERN = re.compile(r"(?P<width>\d{3,5})\s*[x×*]\s*(?P<height>\d{3,5})", re.IGNORECASE)
HDMI_PATTERN = re.compile(r"HDMI\s*(?P<version>2\.1|2\.0|1\.4)(?:\s*[*x×]\s*(?P<count>\d+))?", re.IGNORECASE)
USB_PATTERN = re.compile(r"USB\s*(?P<version>3\.0|2\.0)(?:\s*[*x×]\s*(?P<count>\d+))?", re.IGNORECASE)


@dataclass(frozen=True)
class M03BParamDefinition:
    param_code: str
    param_name: str
    param_group: str
    data_type: str
    raw_fields: tuple[str, ...]
    parser: str
    unit: str | None = None
    missing_policy: str = "unknown"
    required_for_core: bool = False
    profile_sections: tuple[str, ...] = ()


@dataclass(frozen=True)
class M03BTierDefinition:
    dimension_code: str
    tier_code: str
    tier_name: str
    tier_rank: int | None
    rule_summary: str


@dataclass(frozen=True)
class M03BTaxonomy:
    taxonomy_version: str
    category_code: str
    standard_params: tuple[M03BParamDefinition, ...]
    excluded_raw_fields: dict[str, str]
    dimension_tiers: tuple[M03BTierDefinition, ...]

    @property
    def params_by_code(self) -> dict[str, M03BParamDefinition]:
        return {param.param_code: param for param in self.standard_params}

    @property
    def params_by_raw_field(self) -> dict[str, tuple[M03BParamDefinition, ...]]:
        result: dict[str, list[M03BParamDefinition]] = {}
        for param in self.standard_params:
            for raw_field in param.raw_fields:
                result.setdefault(raw_field, []).append(param)
        return {raw_field: tuple(params) for raw_field, params in result.items()}

    @property
    def false_by_absence_params(self) -> tuple[M03BParamDefinition, ...]:
        return tuple(param for param in self.standard_params if param.missing_policy == "false_by_absence")

    def tier_lookup(self) -> dict[tuple[str, str], M03BTierDefinition]:
        return {(tier.dimension_code, tier.tier_code): tier for tier in self.dimension_tiers}


@dataclass(frozen=True)
class M03BParsedValue:
    value_presence: str
    normalized_value: Any
    numeric_value: Decimal | None
    value_text: str | None
    unit: str | None
    parser_status: str
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class M03BParamValue:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M03BSkuProfile:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M03BDimensionTier:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M03BTierCoverage:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M03BServiceResult:
    input_count: int
    param_value_count: int
    sku_profile_count: int
    dimension_tier_count: int
    tier_coverage_count: int
    false_by_absence_count: int
    conflict_count: int
    ignored_raw_field_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())

    @property
    def reused_output_count(self) -> int:
        return sum(item["reused_count"] for item in self.write_summary.values())


class M03BParamEvidenceReader(Core3BaseRepository):
    """Read only M02 param_raw evidence for M03B."""

    def list_param_raw_evidence(
        self,
        batch_id: str,
        *,
        target_sku_codes: Sequence[str] = (),
        sku_code_prefix: str | None = None,
        limit: int = 200000,
        offset: int = 0,
    ) -> list[entities.Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=200000)
        stmt = (
            select(entities.Core3EvidenceAtom)
            .where(entities.Core3EvidenceAtom.project_id == self.project_id)
            .where(entities.Core3EvidenceAtom.category_code == self.category_code.value)
            .where(entities.Core3EvidenceAtom.batch_id == batch_id)
            .where(entities.Core3EvidenceAtom.is_current.is_(True))
            .where(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(entities.Core3EvidenceAtom.evidence_type == Core3EvidenceType.PARAM_RAW.value)
            .order_by(
                entities.Core3EvidenceAtom.sku_code,
                entities.Core3EvidenceAtom.evidence_field,
                entities.Core3EvidenceAtom.evidence_id,
            )
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if target_sku_codes:
            stmt = stmt.where(entities.Core3EvidenceAtom.sku_code.in_(tuple(target_sku_codes)))
        if sku_code_prefix:
            stmt = stmt.where(entities.Core3EvidenceAtom.sku_code.like(f"{sku_code_prefix}%"))
        return list(self.db.execute(stmt).scalars())


class M03BParamProfileRepository(ParamExtractionRepository):
    def save_dimension_tiers(
        self,
        tiers: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3SkuParamDimensionTier,
            tiers,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "sku_code",
                "dimension_code",
                "is_current",
            ),
            hash_field="profile_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def save_tier_coverages(
        self,
        coverages: Sequence[Any],
        *,
        replace_on_hash_conflict: bool = False,
    ) -> ParamRepositoryWriteResult:
        return self._save_many(
            entities.Core3ParamTierCoverage,
            coverages,
            unique_fields=(
                "batch_id",
                "taxonomy_version",
                "dimension_code",
                "tier_code",
                "is_current",
            ),
            hash_field="coverage_hash",
            replace_existing=replace_on_hash_conflict,
        )

    def list_dimension_tiers(
        self,
        batch_id: str,
        *,
        sku_code: str | None = None,
        dimension_code: str | None = None,
        tier_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3SkuParamDimensionTier]:
        stmt = (
            self._base_query(entities.Core3SkuParamDimensionTier, batch_id)
            .where(entities.Core3SkuParamDimensionTier.is_current.is_(True))
            .order_by(
                entities.Core3SkuParamDimensionTier.sku_code,
                entities.Core3SkuParamDimensionTier.dimension_code,
                entities.Core3SkuParamDimensionTier.dimension_tier_id,
            )
        )
        if sku_code is not None:
            stmt = stmt.where(entities.Core3SkuParamDimensionTier.sku_code == sku_code)
        if dimension_code is not None:
            stmt = stmt.where(entities.Core3SkuParamDimensionTier.dimension_code == dimension_code)
        if tier_code is not None:
            stmt = stmt.where(entities.Core3SkuParamDimensionTier.tier_code == tier_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_tier_coverages(
        self,
        batch_id: str,
        *,
        dimension_code: str | None = None,
        tier_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ParamTierCoverage]:
        stmt = (
            self._base_query(entities.Core3ParamTierCoverage, batch_id)
            .where(entities.Core3ParamTierCoverage.is_current.is_(True))
            .order_by(
                entities.Core3ParamTierCoverage.dimension_code,
                entities.Core3ParamTierCoverage.tier_rank,
                entities.Core3ParamTierCoverage.tier_code,
            )
        )
        if dimension_code is not None:
            stmt = stmt.where(entities.Core3ParamTierCoverage.dimension_code == dimension_code)
        if tier_code is not None:
            stmt = stmt.where(entities.Core3ParamTierCoverage.tier_code == tier_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)


class M03BTaxonomyLoader:
    """Load the currently reviewed TV taxonomy asset."""

    def load(self, taxonomy_version: str = CORE3_M03B_TAXONOMY_VERSION, *, category_code: str = "TV") -> M03BTaxonomy:
        if category_code != "TV":
            raise ValueError(f"M03B bundled taxonomy only supports TV, got {category_code}")
        if taxonomy_version != CORE3_M03B_TAXONOMY_VERSION:
            raise ValueError(f"unsupported M03B taxonomy_version: {taxonomy_version}")
        return TV_PARAM_TAXONOMY_V0_1


class M03BRunner:
    module_code = Core3ModuleCode.M03B

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M03B 缺少 M00 batch_id，无法生成 SKU 参数画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            taxonomy_version=str(target.metadata.get("taxonomy_version") or CORE3_M03B_TAXONOMY_VERSION),
            parser_version=str(target.metadata.get("parser_version") or CORE3_M03B_PARSER_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M03B_RULE_VERSION),
            target_sku_codes=target.target_ids,
            force_rebuild=bool(target.metadata.get("force_rebuild")),
            sku_code_prefix=str(target.metadata.get("sku_code_prefix") or "TV"),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        taxonomy_version: str = CORE3_M03B_TAXONOMY_VERSION,
        parser_version: str = CORE3_M03B_PARSER_VERSION,
        rule_version: str = CORE3_M03B_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
        sku_code_prefix: str | None = "TV",
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        repository_context = Core3RepositoryContext(
            db=self.db,
            project_id=project_id,
            category_code=category_code,
        )
        try:
            SourceBatchReader(repository_context).get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        try:
            with self.db.begin_nested():
                service_result = M03BService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    taxonomy_version=taxonomy_version,
                    parser_version=parser_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    force_rebuild=force_rebuild,
                    sku_code_prefix=sku_code_prefix,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m03b_param_hash_conflict",
                message_cn="M03B 参数画像结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m03b_param_profile_failed",
                message_cn="M03B 参数画像生成失败，请检查 M02 参数 evidence 或 taxonomy 配置。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M03B_MODULE_VERSION,
            "taxonomy_version": taxonomy_version,
            "parser_version": parser_version,
            "rule_version": rule_version,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m03b_param_profile_summary_v1")
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M03B,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=_output_count(service_result),
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=_downstream_impacts(service_result),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M03BService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        taxonomy_version: str = CORE3_M03B_TAXONOMY_VERSION,
        parser_version: str = CORE3_M03B_PARSER_VERSION,
        rule_version: str = CORE3_M03B_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
        sku_code_prefix: str | None = "TV",
    ) -> M03BServiceResult:
        taxonomy = M03BTaxonomyLoader().load(taxonomy_version, category_code=self.context.category_code.value)
        evidence_records = M03BParamEvidenceReader(self.context).list_param_raw_evidence(
            batch_id,
            target_sku_codes=target_sku_codes,
            sku_code_prefix=sku_code_prefix,
        )
        param_values, sku_profiles, dimension_tiers, tier_coverages, summary = M03BProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            taxonomy=taxonomy,
            parser_version=parser_version,
            rule_version=rule_version,
            sku_code_prefix=sku_code_prefix,
        ).build(evidence_records)

        repository = M03BParamProfileRepository(self.context)
        write_results = {
            "param_values": repository.save_param_values(
                param_values,
                replace_on_hash_conflict=force_rebuild,
            ),
            "sku_param_profiles": repository.save_sku_param_profiles(
                sku_profiles,
                replace_on_hash_conflict=force_rebuild,
            ),
            "dimension_tiers": repository.save_dimension_tiers(
                dimension_tiers,
                replace_on_hash_conflict=force_rebuild,
            ),
            "tier_coverages": repository.save_tier_coverages(
                tier_coverages,
                replace_on_hash_conflict=force_rebuild,
            ),
        }
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        warnings = _warnings(summary)
        return M03BServiceResult(
            input_count=len(evidence_records),
            param_value_count=len(param_values),
            sku_profile_count=len(sku_profiles),
            dimension_tier_count=len(dimension_tiers),
            tier_coverage_count=len(tier_coverages),
            false_by_absence_count=int(summary["false_by_absence_count"]),
            conflict_count=int(summary["conflict_count"]),
            ignored_raw_field_count=int(summary["ignored_raw_field_count"]),
            warnings=warnings,
            write_summary=write_summary,
            summary={**summary, "write_summary": write_summary},
        )


class M03BProfileBuilder:
    def __init__(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        taxonomy: M03BTaxonomy,
        run_id: str | None = None,
        module_run_id: str | None = None,
        parser_version: str = CORE3_M03B_PARSER_VERSION,
        rule_version: str = CORE3_M03B_RULE_VERSION,
        sku_code_prefix: str | None = "TV",
    ) -> None:
        self.project_id = project_id
        self.category_code = category_code
        self.batch_id = batch_id
        self.run_id = run_id
        self.module_run_id = module_run_id
        self.taxonomy = taxonomy
        self.parser_version = parser_version
        self.rule_version = rule_version
        self.sku_code_prefix = sku_code_prefix
        self.params_by_code = taxonomy.params_by_code
        self.params_by_raw_field = taxonomy.params_by_raw_field
        self.tier_lookup = taxonomy.tier_lookup()

    def build(
        self,
        evidence_records: Iterable[Any],
    ) -> tuple[list[M03BParamValue], list[M03BSkuProfile], list[M03BDimensionTier], list[M03BTierCoverage], dict[str, Any]]:
        records = [record for record in evidence_records if _sku_allowed(record, self.sku_code_prefix)]
        records_by_sku = _group_records_by_sku(records)
        param_values: list[M03BParamValue] = []
        sku_profiles: list[M03BSkuProfile] = []
        dimension_tiers: list[M03BDimensionTier] = []
        false_by_absence_count = 0
        ignored_raw_fields: Counter[str] = Counter()
        conflict_count = 0

        for sku_code in sorted(records_by_sku):
            sku_records = records_by_sku[sku_code]
            result = self._build_sku(sku_code, sku_records)
            param_values.extend(result["param_values"])
            sku_profiles.append(result["sku_profile"])
            dimension_tiers.extend(result["dimension_tiers"])
            false_by_absence_count += int(result["false_by_absence_count"])
            conflict_count += int(result["conflict_count"])
            ignored_raw_fields.update(result["ignored_raw_fields"])

        tier_coverages = self._build_tier_coverages(dimension_tiers, total_sku_count=len(records_by_sku))
        summary = {
            "input_param_raw_count": len(records),
            "sku_profile_count": len(sku_profiles),
            "param_value_count": len(param_values),
            "dimension_tier_count": len(dimension_tiers),
            "tier_coverage_count": len(tier_coverages),
            "false_by_absence_count": false_by_absence_count,
            "conflict_count": conflict_count,
            "ignored_raw_field_count": sum(ignored_raw_fields.values()),
            "ignored_raw_fields": dict(sorted(ignored_raw_fields.items())),
            "category_boundary_filter": f"sku_code_prefix_{self.sku_code_prefix}" if self.sku_code_prefix else None,
            "tier_distribution": _tier_distribution(dimension_tiers),
            "taxonomy_hash": stable_hash(_taxonomy_summary(self.taxonomy), version="m03b_taxonomy_asset_hash_v1"),
        }
        return param_values, sku_profiles, dimension_tiers, tier_coverages, summary

    def _build_sku(self, sku_code: str, records: list[Any]) -> dict[str, Any]:
        model_name = _first_present(_field_value(record, "model_name") for record in records)
        brand_name = _first_present(_field_value(record, "brand_name") for record in records)
        values_by_param: dict[str, list[dict[str, Any]]] = {}
        param_value_payloads: list[M03BParamValue] = []
        ignored_raw_fields: Counter[str] = Counter()

        for record in records:
            raw_field = _record_raw_field(record)
            if raw_field in self.taxonomy.excluded_raw_fields:
                ignored_raw_fields[raw_field] += 1
                continue
            for param in self.params_by_raw_field.get(raw_field, ()):
                parsed = _parse_param_value(param, _record_value(record), raw_field)
                if parsed.value_presence == VALUE_UNKNOWN and param.missing_policy == "unknown":
                    quality_flags = tuple([*parsed.quality_flags, "unknown_value"])
                else:
                    quality_flags = parsed.quality_flags
                payload = self._param_value_payload(record, param, parsed, source_priority_rank=_source_rank(param, raw_field), quality_flags=quality_flags)
                entry = _profile_entry_from_param_payload(payload, required_for_core=param.required_for_core)
                values_by_param.setdefault(param.param_code, []).append(entry)
                if payload["value_presence"] == VALUE_PRESENT:
                    param_value_payloads.append(M03BParamValue(payload))

        self._add_derived_profile_values(values_by_param, records)
        false_by_absence_count = self._add_false_by_absence_values(values_by_param, records)
        main_values = {
            param_code: _select_main_profile_entry(candidates)
            for param_code, candidates in values_by_param.items()
            if candidates
        }
        conflict_count = sum(1 for candidates in values_by_param.values() if _has_conflict(candidates))
        dimension_tiers = self._build_dimension_tiers(sku_code, model_name, main_values)
        dimension_tier_profile = {tier.payload["dimension_code"]: tier.payload["tier_code"] for tier in dimension_tiers}
        tier_explanation = {tier.payload["dimension_code"]: tier.payload["explanation"] for tier in dimension_tiers}
        evidence_ids = _unique_preserve_order(
            evidence_id
            for entry in main_values.values()
            for evidence_id in entry.get("evidence_ids", [])
            if evidence_id
        )
        known_param_count = sum(1 for entry in main_values.values() if entry.get("value_presence") in {VALUE_PRESENT, VALUE_DERIVED_FALSE})
        unknown_param_count = sum(1 for entry in main_values.values() if entry.get("value_presence") == VALUE_UNKNOWN)
        core_param_codes = [param.param_code for param in self.taxonomy.standard_params if param.required_for_core]
        known_core_count = sum(1 for code in core_param_codes if code in main_values and main_values[code].get("value_presence") in {VALUE_PRESENT, VALUE_DERIVED_FALSE})
        completeness = _ratio(known_core_count, len(core_param_codes))
        param_values_json = {
            **{param_code: entry for param_code, entry in sorted(main_values.items())},
            "_metadata": {
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "parser_version": self.parser_version,
                "rule_version": self.rule_version,
            },
            "dimension_tier_profile": dimension_tier_profile,
            "tier_explanation": tier_explanation,
        }
        quality_summary_json = {
            "taxonomy_version": self.taxonomy.taxonomy_version,
            "parser_version": self.parser_version,
            "rule_version": self.rule_version,
            "known_core_param_count": known_core_count,
            "core_param_count": len(core_param_codes),
            "param_completeness": str(completeness),
            "known_param_count": known_param_count,
            "unknown_param_count": unknown_param_count,
            "false_by_absence_count": false_by_absence_count,
            "excluded_raw_fields": sorted(ignored_raw_fields),
            "conflict_count": conflict_count,
            "parse_warning_count": sum(1 for entry in main_values.values() if entry.get("quality_flags")),
            "category_boundary_filter": f"sku_code_prefix_{self.sku_code_prefix}" if self.sku_code_prefix else None,
        }
        profile_payload = {
            "sku_param_profile_id": _sku_profile_id(self.project_id, self.batch_id, sku_code, self.taxonomy.taxonomy_version, self.rule_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": sku_code,
            "model_name": model_name,
            "param_values_json": param_values_json,
            "core_picture_params_json": _core_summary(main_values, CORE_PICTURE_CODES),
            "core_gaming_params_json": _core_summary(main_values, CORE_GAMING_CODES),
            "core_system_params_json": _core_summary(main_values, CORE_SYSTEM_CODES),
            "core_eye_care_params_json": _core_summary(main_values, CORE_COMFORT_CODES),
            "param_completeness": completeness,
            "known_param_count": known_param_count,
            "unknown_param_count": unknown_param_count,
            "conflict_count": conflict_count,
            "review_required_count": conflict_count,
            "evidence_ids": evidence_ids,
            "quality_summary_json": quality_summary_json,
            "profile_hash": stable_hash(
                {
                    "sku_code": sku_code,
                    "values": param_values_json,
                    "quality_summary": quality_summary_json,
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "rule_version": self.rule_version,
                },
                version=M03B_SKU_PROFILE_HASH_VERSION,
            ),
            "seed_version": self.taxonomy.taxonomy_version,
            "rule_version": self.rule_version,
        }
        return {
            "param_values": param_value_payloads,
            "sku_profile": M03BSkuProfile(profile_payload),
            "dimension_tiers": dimension_tiers,
            "false_by_absence_count": false_by_absence_count,
            "conflict_count": conflict_count,
            "ignored_raw_fields": ignored_raw_fields,
        }

    def _param_value_payload(
        self,
        record: Any,
        param: M03BParamDefinition,
        parsed: M03BParsedValue,
        *,
        source_priority_rank: int,
        quality_flags: tuple[str, ...],
    ) -> dict[str, Any]:
        evidence_id = str(_field_value(record, "evidence_id") or "")
        sku_code = str(_field_value(record, "sku_code") or "")
        raw_field = _record_raw_field(record)
        raw_value = _record_value(record)
        confidence = _confidence_for(parsed, _decimal(_field_value(record, "base_confidence"), Decimal("0.9000")))
        payload = {
            "param_value_id": _param_value_id(self.project_id, self.batch_id, sku_code, param.param_code, evidence_id, self.parser_version),
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "sku_code": sku_code,
            "model_name": _field_value(record, "model_name"),
            "param_code": param.param_code,
            "param_name": param.param_name,
            "param_group": param.param_group,
            "data_type": param.data_type,
            "normalized_value": parsed.normalized_value,
            "numeric_value": parsed.numeric_value,
            "value_text": parsed.value_text,
            "unit": parsed.unit,
            "value_level": None,
            "value_presence": parsed.value_presence,
            "source_type": SOURCE_RAW_PARAM,
            "source_priority_rank": source_priority_rank,
            "raw_param_name": raw_field,
            "raw_param_value": None if raw_value is None else str(raw_value),
            "match_type": MATCH_EXACT_MANUAL,
            "parser_type": param.parser,
            "parser_status": parsed.parser_status,
            "confidence": confidence,
            "confidence_level": _confidence_level(confidence),
            "evidence_ids": [evidence_id] if evidence_id else [],
            "primary_evidence_id": evidence_id,
            "quality_flags": list(quality_flags),
            "conflict_flag": False,
            "conflict_id": None,
            "review_required": False,
            "review_status": "auto_pass",
            "param_value_hash": stable_hash(
                {
                    "sku_code": sku_code,
                    "param_code": param.param_code,
                    "normalized_value": parsed.normalized_value,
                    "numeric_value": parsed.numeric_value,
                    "source_type": SOURCE_RAW_PARAM,
                    "evidence_id": evidence_id,
                    "quality_flags": list(quality_flags),
                    "taxonomy_version": self.taxonomy.taxonomy_version,
                    "parser_version": self.parser_version,
                    "rule_version": self.rule_version,
                },
                version=M03B_PARAM_VALUE_HASH_VERSION,
            ),
            "seed_version": self.taxonomy.taxonomy_version,
            "parser_version": self.parser_version,
            "rule_version": self.rule_version,
        }
        return payload

    def _add_derived_profile_values(self, values_by_param: dict[str, list[dict[str, Any]]], records: list[Any]) -> None:
        by_field = {_record_raw_field(record): record for record in records}
        size = _main_numeric(values_by_param.get("screen_size_inch", []))
        if size is not None:
            values_by_param.setdefault("screen_size_segment", []).append(
                _derived_profile_entry(
                    param_code="screen_size_segment",
                    param_name="尺寸段",
                    param_group="size",
                    data_type="enum",
                    normalized_value=_size_tier_by_number(size),
                    value_text=_size_tier_by_number(size),
                    basis_param_codes=["screen_size_inch"],
                    rule="derive_size_segment",
                )
            )
        display_class, display_basis = _display_tech_class(by_field)
        if display_class != "unknown":
            values_by_param.setdefault("display_tech_class", []).append(
                _derived_profile_entry(
                    param_code="display_tech_class",
                    param_name="显示技术分类",
                    param_group="picture",
                    data_type="enum",
                    normalized_value=display_class,
                    value_text=display_class,
                    basis_param_codes=list(display_basis.keys()),
                    rule="derive_display_tech_class",
                    evidence_ids=[_field_value(record, "evidence_id") for record in display_basis.values()],
                )
            )

    def _add_false_by_absence_values(self, values_by_param: dict[str, list[dict[str, Any]]], records: list[Any]) -> int:
        count = 0
        raw_fields_present = {_record_raw_field(record): record for record in records}
        for param in self.taxonomy.false_by_absence_params:
            if param.param_code in values_by_param and any(entry.get("value_presence") == VALUE_PRESENT for entry in values_by_param[param.param_code]):
                continue
            evidence_ids = [
                str(_field_value(raw_fields_present[field], "evidence_id"))
                for field in param.raw_fields
                if field in raw_fields_present and _field_value(raw_fields_present[field], "evidence_id")
            ]
            values_by_param.setdefault(param.param_code, []).append(
                _derived_profile_entry(
                    param_code=param.param_code,
                    param_name=param.param_name,
                    param_group=param.param_group,
                    data_type=param.data_type,
                    normalized_value=False,
                    value_text="false",
                    basis_param_codes=list(param.raw_fields),
                    rule="false_by_absence",
                    evidence_ids=evidence_ids,
                    value_presence=VALUE_DERIVED_FALSE,
                    quality_flags=["false_by_absence"],
                )
            )
            count += 1
        return count

    def _build_dimension_tiers(
        self,
        sku_code: str,
        model_name: str | None,
        values: dict[str, dict[str, Any]],
    ) -> list[M03BDimensionTier]:
        tier_results = [
            _size_dimension(values),
            _display_tech_dimension(values),
            _local_dimming_dimension(values),
            _picture_overall_dimension(values),
            _performance_dimension(values),
            _smart_dimension(values),
            _ports_dimension(values),
            _appearance_dimension(values),
            _energy_dimension(values),
        ]
        tiers: list[M03BDimensionTier] = []
        for result in tier_results:
            definition = self.tier_lookup.get((result["dimension_code"], result["tier_code"]))
            tier_name = definition.tier_name if definition else result["tier_code"]
            tier_rank = definition.tier_rank if definition else None
            rule_summary = definition.rule_summary if definition else result.get("rule_summary", "")
            evidence_ids = _unique_preserve_order(
                evidence_id
                for param_code in result["basis_param_codes"]
                for evidence_id in values.get(param_code, {}).get("evidence_ids", [])
                if evidence_id
            )
            payload = {
                "dimension_tier_id": _dimension_tier_id(
                    self.project_id,
                    self.batch_id,
                    sku_code,
                    self.taxonomy.taxonomy_version,
                    result["dimension_code"],
                    self.rule_version,
                ),
                "project_id": self.project_id,
                "category_code": self.category_code,
                "batch_id": self.batch_id,
                "run_id": self.run_id,
                "module_run_id": self.module_run_id,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "sku_code": sku_code,
                "model_name": model_name,
                "dimension_code": result["dimension_code"],
                "tier_code": result["tier_code"],
                "tier_name": tier_name,
                "tier_rank": tier_rank,
                "basis_param_codes": result["basis_param_codes"],
                "basis_values_json": _basis_values(values, result["basis_param_codes"]),
                "rule_snapshot_json": {"rule_summary": rule_summary, "rule_version": self.rule_version},
                "explanation": result["explanation"],
                "evidence_ids": evidence_ids,
                "confidence": result.get("confidence", Decimal("0.9000")),
                "quality_flags": result.get("quality_flags", []),
                "profile_hash": stable_hash(
                    {
                        "sku_code": sku_code,
                        "dimension_code": result["dimension_code"],
                        "tier_code": result["tier_code"],
                        "basis": _basis_values(values, result["basis_param_codes"]),
                        "taxonomy_version": self.taxonomy.taxonomy_version,
                        "rule_version": self.rule_version,
                    },
                    version=M03B_DIMENSION_TIER_HASH_VERSION,
                ),
                "is_current": True,
                "rule_version": self.rule_version,
            }
            tiers.append(M03BDimensionTier(payload))
        return tiers

    def _build_tier_coverages(self, dimension_tiers: list[M03BDimensionTier], *, total_sku_count: int) -> list[M03BTierCoverage]:
        by_dimension_tier: dict[tuple[str, str], list[M03BDimensionTier]] = {}
        for tier in dimension_tiers:
            payload = tier.payload
            by_dimension_tier.setdefault((payload["dimension_code"], payload["tier_code"]), []).append(tier)

        coverages: list[M03BTierCoverage] = []
        for definition in self.taxonomy.dimension_tiers:
            members = sorted(
                by_dimension_tier.get((definition.dimension_code, definition.tier_code), []),
                key=lambda item: item.payload["sku_code"],
            )
            sku_codes = [item.payload["sku_code"] for item in members]
            sku_count = len(sku_codes)
            status = "covered" if sku_count > 0 else "empty_current_batch"
            if 0 < sku_count < 3:
                status = "insufficient_sample"
            payload = {
                "tier_coverage_id": _tier_coverage_id(
                    self.project_id,
                    self.batch_id,
                    self.taxonomy.taxonomy_version,
                    definition.dimension_code,
                    definition.tier_code,
                    self.rule_version,
                ),
                "project_id": self.project_id,
                "category_code": self.category_code,
                "batch_id": self.batch_id,
                "run_id": self.run_id,
                "module_run_id": self.module_run_id,
                "taxonomy_version": self.taxonomy.taxonomy_version,
                "dimension_code": definition.dimension_code,
                "tier_code": definition.tier_code,
                "tier_name": definition.tier_name,
                "tier_rank": definition.tier_rank,
                "rule_summary": definition.rule_summary,
                "sku_count": sku_count,
                "sku_ratio": _ratio(sku_count, total_sku_count),
                "sku_codes": sku_codes,
                "sample_sku_codes": sku_codes[:10],
                "coverage_status": status,
                "coverage_hash": stable_hash(
                    {
                        "dimension_code": definition.dimension_code,
                        "tier_code": definition.tier_code,
                        "sku_codes": sku_codes,
                        "taxonomy_version": self.taxonomy.taxonomy_version,
                        "rule_version": self.rule_version,
                    },
                    version=M03B_TIER_COVERAGE_HASH_VERSION,
                ),
                "is_current": True,
                "rule_version": self.rule_version,
            }
            coverages.append(M03BTierCoverage(payload))
        return coverages


CORE_PICTURE_CODES = (
    "screen_size_inch",
    "resolution_label",
    "resolution_pixels",
    "declared_refresh_rate_hz",
    "declared_brightness_nit_or_band",
    "hdr_support_flag",
    "color_gamut_ratio",
    "high_color_gamut_flag",
    "display_technology_family",
    "display_tech_class",
    "backlight_source",
    "backlight_subtype",
    "mini_led_flag",
    "mini_led_type",
    "local_dimming_zone_count",
    "quantum_dot_flag",
)
CORE_GAMING_CODES = ("declared_refresh_rate_hz", "hdmi_version_mix", "hdmi_2_1_port_count", "hdmi_port_count", "usb_version_mix", "usb_port_count")
CORE_SYSTEM_CODES = (
    "cpu_core_count",
    "cpu_frequency_ghz",
    "gpu_core_count",
    "processor_chip_model",
    "processor_vendor",
    "ram_gb",
    "storage_gb",
    "os_family",
    "os_distribution",
    "os_version_detail",
    "ai_model_name",
    "ai_model_capability_flag",
    "ai_capability_flag",
    "voice_engine",
    "voice_recognition_flag",
    "far_field_voice_flag",
    "camera_flag",
    "whole_home_control_flag",
    "wifi_builtin_flag",
)
CORE_COMFORT_CODES = ("hdr_support_flag", "declared_brightness_nit_or_band", "declared_refresh_rate_hz")


def tv_param_taxonomy_v0_1() -> M03BTaxonomy:
    params = (
        _param("ai_model_name", "AI 大模型名称", "smart", "string", ("AI大模型",), "string"),
        _param("ai_model_capability_flag", "AI 大模型能力", "smart", "boolean", ("AI大模型",), "feature_presence", missing_policy="false_by_absence"),
        _param("cpu_frequency_ghz", "CPU 主频", "performance", "number", ("CPU主频",), "number", unit="GHz"),
        _param("cpu_core_count", "CPU 核数", "performance", "string", ("CPU核数",), "string", required_for_core=True),
        _param("gpu_core_count", "GPU 核数", "performance", "string", ("GPU核数",), "string"),
        _param("hdmi_version_mix", "HDMI 版本组合", "ports", "object", ("HDMI参数",), "hdmi_mix", required_for_core=True),
        _param("hdmi_2_1_port_count", "HDMI2.1 端口数", "ports", "number", ("HDMI参数",), "hdmi_2_1_count"),
        _param("hdmi_port_count", "HDMI 数量", "ports", "number", ("HDMI数量",), "integer", required_for_core=True),
        _param("hdr_support_flag", "HDR 支持", "picture", "boolean", ("HDR",), "feature_presence"),
        _param("processor_chip_model", "芯片型号", "performance", "string", ("IC型号",), "string"),
        _param("mini_led_flag", "MiniLED 标记", "picture", "boolean", ("MINILED",), "boolean"),
        _param("mini_led_type", "MiniLED 类型", "picture", "string", ("MINILED2",), "string", required_for_core=True),
        _param("ram_gb", "RAM 内存", "performance", "number", ("RAM内存",), "gb", unit="GB", required_for_core=True),
        _param("rgb_structure_flag", "RGB 结构", "picture", "boolean", ("RGB",), "feature_presence"),
        _param("storage_gb", "ROM 容量", "performance", "number", ("ROM容量",), "gb", unit="GB", required_for_core=True),
        _param("slim_design_label", "轻薄标签", "appearance", "string", ("SLIM",), "string"),
        _param("slim_design_flag", "超薄设计", "appearance", "boolean", ("SLIM", "超轻薄"), "feature_presence", missing_policy="false_by_absence"),
        _param("usb_version_mix", "USB 版本组合", "ports", "object", ("USB参数",), "usb_mix"),
        _param("usb_3_0_flag", "USB3.0 标记", "ports", "boolean", ("USB参数",), "usb_3_flag"),
        _param("usb_port_count", "USB 数量", "ports", "number", ("USB数量",), "integer"),
        _param("three_d_mode", "三维电视模式", "picture", "string", ("三维电视",), "string"),
        _param("processor_vendor", "主芯片供应商", "performance", "string", ("主芯片供应商",), "string"),
        _param("brand_type_internet_flag", "互联网品牌", "identity", "boolean", ("互联网品牌",), "internet_brand"),
        _param("display_technology_family", "显示技术大类", "picture", "string", ("产品技术",), "string"),
        _param("declared_brightness_nit_or_band", "标称亮度", "picture", "object", ("亮度",), "nits_or_band", unit="nits", required_for_core=True),
        _param("ai_capability_flag", "人工智能", "smart", "boolean", ("人工智能",), "feature_presence"),
        _param("whole_home_control_flag", "全屋智控", "smart", "boolean", ("全屋智控",), "feature_presence", missing_policy="false_by_absence"),
        _param("color_gamut_ratio", "全色域", "picture", "number", ("全色域",), "percentage_ratio", unit="%", required_for_core=True),
        _param("full_screen_design_flag", "全面屏", "appearance", "boolean", ("全面屏",), "feature_presence", missing_policy="false_by_absence"),
        _param("content_license_provider", "内容运营商", "content", "string", ("内容运营商",), "string"),
        _param("wifi_builtin_flag", "内置 WiFi", "smart", "boolean", ("内置WIFI",), "feature_presence", missing_policy="false_by_absence"),
        _param("local_dimming_zone_count", "分区背光", "picture", "number", ("分区背光",), "integer", unit="zones", required_for_core=True),
        _param("resolution_pixels", "分辨率像素", "picture", "object", ("分辨率",), "resolution", required_for_core=True),
        _param("screen_size_inch", "屏幕尺寸", "size", "number", ("尺寸",), "inch", unit="inch", required_for_core=True),
        _param("screen_size_segment", "尺寸段", "size", "enum", ("尺寸段",), "string"),
        _param("declared_refresh_rate_hz", "标称屏幕刷新率", "picture", "number", ("屏幕刷新率",), "declared_hz", unit="Hz", required_for_core=True),
        _param("aspect_ratio", "屏幕比例", "picture", "string", ("屏幕比例",), "string"),
        _param("smart_tv_flag", "智能电视", "smart", "boolean", ("广义智能电视",), "feature_presence"),
        _param("camera_flag", "摄像头", "smart", "boolean", ("摄像头",), "feature_presence", missing_policy="false_by_absence"),
        _param("streaming_platform_bundle", "播控平台", "content", "list", ("播控平台",), "text_list"),
        _param("os_family", "操作系统", "system", "string", ("操作系统",), "string", required_for_core=True),
        _param("os_distribution", "操作系统企业版", "system", "string", ("操作系统企业版",), "string"),
        _param("os_version_detail", "操作系统细分", "system", "string", ("操作系统细分",), "string"),
        _param("flush_wall_mount_flag", "无缝贴墙", "appearance", "boolean", ("无缝贴墙",), "feature_presence", missing_policy="false_by_absence"),
        _param("body_thickness_mm", "机身厚度", "appearance", "number", ("机身厚度",), "mm", unit="mm"),
        _param("brand_name_standard", "标准品牌", "identity", "string", ("标准品牌",), "string"),
        _param("resolution_class", "清晰度", "picture", "string", ("清晰度",), "resolution_label"),
        _param("resolution_label", "清晰度标签", "picture", "string", ("清晰度2",), "resolution_label", required_for_core=True),
        _param("portable_tv_flag", "移动电视", "appearance", "boolean", ("移动电视",), "feature_presence", missing_policy="false_by_absence"),
        _param("product_series", "系列", "identity", "string", ("系列",), "string"),
        _param("network_tv_flag", "网络电视", "smart", "boolean", ("网络电视",), "feature_presence"),
        _param("backlight_source", "背光源", "picture", "string", ("背光源",), "string"),
        _param("backlight_subtype", "背光源细分", "picture", "string", ("背光源细分",), "string"),
        _param("energy_efficiency_index", "能效指数", "energy", "number", ("能效指数",), "energy_index"),
        _param("energy_efficiency_grade", "能效等级", "energy", "string", ("能效等级",), "string", required_for_core=True),
        _param("standby_power_w", "被动待机功率", "energy", "number", ("被动待机功率",), "watt", unit="W"),
        _param("vod_flag", "视频点播", "content", "boolean", ("视频点播",), "feature_presence"),
        _param("voice_engine", "语音技术", "smart", "string", ("语音技术",), "string", missing_policy="false_by_absence"),
        _param("voice_recognition_flag", "语音识别", "smart", "boolean", ("语音识别",), "feature_presence", missing_policy="false_by_absence"),
        _param("far_field_voice_flag", "远场语音", "smart", "boolean", ("远场语音",), "feature_presence", missing_policy="false_by_absence"),
        _param("quantum_dot_flag", "量子点", "picture", "boolean", ("量子点",), "feature_presence", missing_policy="false_by_absence"),
        _param("product_color", "颜色", "identity", "string", ("颜色",), "string"),
        _param("high_color_gamut_flag", "高色域", "picture", "boolean", ("高色域",), "feature_presence"),
    )
    excluded = {
        "HEVC参数": "empty_field",
        "HEVC视频压缩": "empty_field",
        "UI界面": "empty_field",
        "三维技术": "empty_field",
        "三维技术细分": "empty_field",
        "分体": "empty_field",
        "前框材质": "empty_field",
        "响应时间": "empty_field",
        "对比度": "empty_field",
        "屏幕尺寸": "all_zero_invalid",
        "屏幕边框": "empty_field",
        "屏幕面积": "all_zero_invalid",
        "应用程序": "low_value_app_only",
        "手势识别": "empty_field",
        "接口技术": "empty_field",
        "数字信号方式": "empty_field",
        "数字电视": "empty_field",
        "数字电视类型": "empty_field",
        "整机厚度": "all_zero_invalid",
        "整机宽度": "all_zero_invalid",
        "曲面": "empty_field",
        "曲面弧度": "all_zero_invalid",
        "水平/垂直视角": "all_zero_invalid",
        "灯珠数量": "all_zero_invalid",
    }
    tiers = (
        _tier("size", "small_32_45", "小屏 32-45", 10, "<=45 英寸"),
        _tier("size", "medium_46_59", "中屏 46-59", 20, "46-59 英寸"),
        _tier("size", "large_60_69", "大屏 60-69", 30, "60-69 英寸"),
        _tier("size", "xlarge_70_85", "超大屏 70-85", 40, "70-85 英寸"),
        _tier("size", "xxlarge_86_97", "超大屏 86-97", 50, "86-97 英寸"),
        _tier("size", "giant_98_plus", "巨幕 98+", 60, ">=98 英寸"),
        _tier("display_tech", "lcd_led", "LCD/LED", 10, "LCD + LED 背光，非 MiniLED"),
        _tier("display_tech", "qled_lcd", "QLED/LCD", 20, "非 MiniLED 但有 QD/Q-LED 标记"),
        _tier("display_tech", "miniled", "MiniLED", 30, "LCD + MiniLED 背光"),
        _tier("display_tech", "qd_miniled", "QD-MiniLED", 40, "MiniLED + QD/SQD 增强"),
        _tier("display_tech", "rgb_miniled", "RGB-MiniLED", 50, "RGB MiniLED"),
        _tier("display_tech", "laser", "LASER", 60, "激光电视"),
        _tier("display_tech", "oled", "OLED", 70, "OLED 显示技术"),
        _tier("display_tech", "unknown", "显示技术未知", None, "缺少显示技术输入"),
        _tier("local_dimming", "z_none_0", "无分区", 0, "分区背光 = 0"),
        _tier("local_dimming", "z_entry_1_499", "入门分区", 10, "1-499 分区"),
        _tier("local_dimming", "z_mid_500_999", "中档分区", 20, "500-999 分区"),
        _tier("local_dimming", "z_high_1000_1999", "高分区", 30, "1000-1999 分区"),
        _tier("local_dimming", "z_premium_2000_3999", "旗舰分区", 40, "2000-3999 分区"),
        _tier("local_dimming", "z_flagship_4000_plus", "超旗舰分区", 50, ">=4000 分区"),
        _tier("local_dimming", "unknown", "分区未知", None, "缺少分区背光输入"),
        _tier("picture_overall", "picture_basic", "基础画质", 10, "HD/FHD、60Hz 或明显低规格"),
        _tier("picture_overall", "picture_mainstream", "主流画质", 20, "4K 但亮度、刷新率、控光无明显增强"),
        _tier("picture_overall", "picture_enhanced", "增强画质", 30, "有高刷、HDR、高色域或亮度增强，但未达到高端控光组合"),
        _tier("picture_overall", "picture_premium", "高端画质", 40, "MiniLED/QD/RGB MiniLED，且亮度或分区有明显支撑"),
        _tier("picture_overall", "picture_flagship", "旗舰画质", 50, "QD/RGB MiniLED + 高亮度 + 高分区控光组合成立"),
        _tier("performance", "perf_low", "低配性能", 10, "RAM <=1.5GB 或 ROM <=16GB"),
        _tier("performance", "perf_basic", "基础性能", 20, "RAM <=2GB 或 ROM <=32GB"),
        _tier("performance", "perf_mainstream", "主流性能", 30, "RAM 3GB 左右，ROM 64GB 左右"),
        _tier("performance", "perf_main_plus", "主流增强性能", 40, "RAM >=4GB 且 ROM >=64GB"),
        _tier("performance", "perf_high", "高配性能", 50, "RAM >=6GB 或 ROM >=128GB"),
        _tier("performance", "perf_unknown", "性能未知", None, "RAM 或 ROM 关键输入缺失"),
        _tier("smart", "smart_basic", "基础智能", 10, "仅智能电视/网络电视基础标签"),
        _tier("smart", "smart_voice_ai_basic", "语音/AI 基础", 20, "有人工智能或语音/远场语音基础能力"),
        _tier("smart", "smart_ai_voice", "AI 语音增强", 30, "有 AI 大模型 + 语音/远场语音"),
        _tier("smart", "smart_interaction_iot", "交互/全屋联动增强", 40, "有摄像头或全屋智控"),
        _tier("ports", "ports_weak", "弱接口", 10, "HDMI <=1 或 USB <=1"),
        _tier("ports", "ports_basic", "基础接口", 20, "HDMI/USB 有基础数量，无 HDMI2.1 增强"),
        _tier("ports", "ports_main_hdmi21", "HDMI2.1 主流接口", 30, "有 HDMI2.1，但数量不丰富"),
        _tier("ports", "ports_main_plus", "接口主流增强", 40, "HDMI 数量较多，或 HDMI2.1 + USB3.0 组合"),
        _tier("ports", "ports_rich", "丰富接口", 50, "HDMI >=4 且有 HDMI2.1 和 USB3.0"),
        _tier("ports", "ports_unknown", "接口未知", None, "HDMI 或 USB 关键输入缺失"),
        _tier("appearance", "appearance_wall_flush", "无缝贴墙", 70, "有无缝贴墙"),
        _tier("appearance", "appearance_ultra_slim", "超薄", 60, "明确超轻薄，或厚度 <=50mm"),
        _tier("appearance", "appearance_slim_fullscreen", "薄型全面屏", 50, "全面屏且厚度 <=60mm"),
        _tier("appearance", "appearance_slim", "薄型", 40, "厚度 <=60mm"),
        _tier("appearance", "appearance_standard", "普通厚度", 30, "60-75mm"),
        _tier("appearance", "appearance_thick", "偏厚", 20, "75-90mm"),
        _tier("appearance", "appearance_heavy", "厚重", 10, ">90mm"),
        _tier("appearance", "appearance_unknown", "厚度未知", None, "厚度缺失且无外观特性"),
        _tier("energy", "energy_grade_1", "一级能效", 30, "能效等级一级"),
        _tier("energy", "energy_grade_2", "二级能效", 20, "能效等级二级"),
        _tier("energy", "energy_grade_3_4", "三级/四级能效", 10, "能效等级三级或四级"),
        _tier("energy", "energy_unknown", "能效未知", None, "能效等级缺失"),
    )
    return M03BTaxonomy(
        taxonomy_version=CORE3_M03B_TAXONOMY_VERSION,
        category_code="TV",
        standard_params=params,
        excluded_raw_fields=excluded,
        dimension_tiers=tiers,
    )


def _param(
    param_code: str,
    param_name: str,
    param_group: str,
    data_type: str,
    raw_fields: tuple[str, ...],
    parser: str,
    *,
    unit: str | None = None,
    missing_policy: str = "unknown",
    required_for_core: bool = False,
    profile_sections: tuple[str, ...] = (),
) -> M03BParamDefinition:
    return M03BParamDefinition(
        param_code=param_code,
        param_name=param_name,
        param_group=param_group,
        data_type=data_type,
        raw_fields=raw_fields,
        parser=parser,
        unit=unit,
        missing_policy=missing_policy,
        required_for_core=required_for_core,
        profile_sections=profile_sections,
    )


def _tier(dimension_code: str, tier_code: str, tier_name: str, tier_rank: int | None, rule_summary: str) -> M03BTierDefinition:
    return M03BTierDefinition(
        dimension_code=dimension_code,
        tier_code=tier_code,
        tier_name=tier_name,
        tier_rank=tier_rank,
        rule_summary=rule_summary,
    )


TV_PARAM_TAXONOMY_V0_1 = tv_param_taxonomy_v0_1()


def _sku_allowed(record: Any, sku_code_prefix: str | None) -> bool:
    sku_code = str(_field_value(record, "sku_code") or "")
    return bool(sku_code) and (not sku_code_prefix or sku_code.startswith(sku_code_prefix))


def _group_records_by_sku(records: Iterable[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = {}
    for record in records:
        sku_code = str(_field_value(record, "sku_code") or "")
        if sku_code:
            grouped.setdefault(sku_code, []).append(record)
    return grouped


def _record_raw_field(record: Any) -> str:
    return str(_field_value(record, "clean_field") or _field_value(record, "raw_field") or _field_value(record, "evidence_field") or "").strip()


def _record_value(record: Any) -> Any:
    value = _field_value(record, "clean_value")
    if value is not None:
        return value
    return _field_value(record, "raw_value")


def _field_value(record: Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _first_present(values: Iterable[Any]) -> str | None:
    for value in values:
        if _present(value):
            return str(value).strip()
    return None


def _present(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip()
    if _normalize_text(text) in UNKNOWN_LITERALS:
        return False
    return True


def _normalize_text(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "")


def _numbers(value: Any) -> list[Decimal]:
    numbers: list[Decimal] = []
    for match in NUMBER_PATTERN.findall(str(value or "")):
        try:
            numbers.append(Decimal(match))
        except InvalidOperation:
            continue
    return numbers


def _first_decimal(value: Any) -> Decimal | None:
    numbers = _numbers(value)
    return numbers[0] if numbers else None


def _decimal(value: Any, default: Decimal | None = None) -> Decimal | None:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _json_number(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _parse_param_value(param: M03BParamDefinition, raw_value: Any, raw_field: str) -> M03BParsedValue:
    if not _present(raw_value):
        return M03BParsedValue(
            value_presence=VALUE_UNKNOWN,
            normalized_value=None,
            numeric_value=None,
            value_text=None,
            unit=param.unit,
            parser_status="empty_or_unknown",
        )

    text = str(raw_value).strip()
    parser = param.parser
    if parser == "string":
        return _parsed_present(text, value_text=text, unit=param.unit)
    if parser == "text_list":
        items = [item.strip() for item in re.split(r"[,，/、;；|]+", text) if item.strip()]
        return _parsed_present(items or [text], value_text=text, unit=param.unit)
    if parser in {"number", "gb", "mm", "watt", "inch"}:
        number = _first_decimal(text)
        if number is None:
            return _parsed_unknown_text(text, param.unit, "parse_failed")
        return _parsed_present(_json_number(number), numeric_value=number, value_text=text, unit=param.unit)
    if parser in {"integer", "energy_index"}:
        number = _first_decimal(text)
        if number is None:
            return _parsed_unknown_text(text, param.unit, "parse_failed")
        integer = int(number)
        return _parsed_present(integer, numeric_value=Decimal(integer), value_text=text, unit=param.unit)
    if parser == "resolution":
        return _parse_resolution(text)
    if parser == "resolution_label":
        return _parse_resolution_label(text)
    if parser == "declared_hz":
        return _parse_declared_hz(text)
    if parser == "nits_or_band":
        return _parse_nits_or_band(text)
    if parser == "percentage_ratio":
        return _parse_percentage_ratio(text)
    if parser == "feature_presence":
        return _parse_feature_presence(text, param.unit)
    if parser == "boolean":
        return _parse_boolean(text, param.unit)
    if parser == "hdmi_mix":
        return _parse_hdmi_mix(text)
    if parser == "hdmi_2_1_count":
        return _parse_hdmi_2_1_count(text)
    if parser == "usb_mix":
        return _parse_usb_mix(text)
    if parser == "usb_3_flag":
        return _parse_usb_3_flag(text)
    if parser == "internet_brand":
        normalized = _normalize_text(text)
        value = "非互联网" not in text and normalized not in FALSE_LITERALS
        return _parsed_present(value, value_text=text)

    return _parsed_present(text, value_text=text, unit=param.unit, quality_flags=("unsupported_parser_fallback",))


def _parsed_present(
    normalized_value: Any,
    *,
    numeric_value: Decimal | None = None,
    value_text: str | None = None,
    unit: str | None = None,
    parser_status: str = "parsed",
    quality_flags: tuple[str, ...] = (),
) -> M03BParsedValue:
    return M03BParsedValue(
        value_presence=VALUE_PRESENT,
        normalized_value=_json_value(normalized_value),
        numeric_value=numeric_value,
        value_text=value_text,
        unit=unit,
        parser_status=parser_status,
        quality_flags=quality_flags,
    )


def _parsed_unknown_text(value_text: str, unit: str | None, parser_status: str) -> M03BParsedValue:
    return M03BParsedValue(
        value_presence=VALUE_UNKNOWN,
        normalized_value=None,
        numeric_value=None,
        value_text=value_text,
        unit=unit,
        parser_status=parser_status,
        quality_flags=("parse_failed",),
    )


def _parse_resolution(text: str) -> M03BParsedValue:
    match = RESOLUTION_PATTERN.search(text)
    if match:
        width = int(match.group("width"))
        height = int(match.group("height"))
        label = _resolution_label_from_text(text)
        if label == "unknown":
            label = "4K" if width >= 3840 or height >= 2160 else "FHD" if width >= 1920 or height >= 1080 else "HD"
        return _parsed_present(
            {"width": width, "height": height, "resolution_label": label},
            numeric_value=Decimal(width * height),
            value_text=text,
            unit="pixels",
        )
    label = _resolution_label_from_text(text)
    if label != "unknown":
        return _parsed_present({"resolution_label": label}, value_text=text, unit="pixels")
    return _parsed_unknown_text(text, "pixels", "parse_failed")


def _parse_resolution_label(text: str) -> M03BParsedValue:
    label = _resolution_label_from_text(text)
    if label == "unknown":
        return _parsed_unknown_text(text, None, "parse_failed")
    return _parsed_present(label, value_text=text)


def _resolution_label_from_text(text: str) -> str:
    upper = text.upper()
    if "8K" in upper:
        return "8K"
    if "4K" in upper or "UHD" in upper or "超高清" in text:
        return "4K"
    if "FHD" in upper or "1080" in upper or "全高清" in text:
        return "FHD"
    if "HD" in upper or "720" in upper or "高清" in text:
        return "HD"
    return "unknown"


def _parse_declared_hz(text: str) -> M03BParsedValue:
    number = _first_decimal(text)
    if number is None:
        return _parsed_unknown_text(text, "Hz", "parse_failed")
    flags = ["declared_metric"]
    if number > Decimal("240"):
        flags.append("may_be_marketing_refresh")
    return _parsed_present(_json_number(number), numeric_value=number, value_text=text, unit="Hz", quality_flags=tuple(flags))


def _parse_nits_or_band(text: str) -> M03BParsedValue:
    numbers = _numbers(text)
    if not numbers:
        return _parsed_unknown_text(text, "nits", "parse_failed")
    flags = ("declared_metric", "unit_inferred_nits")
    if len(numbers) >= 2:
        low, high = min(numbers[:2]), max(numbers[:2])
        midpoint = (low + high) / Decimal("2")
        return _parsed_present(
            {"min": _json_number(low), "max": _json_number(high), "midpoint": _json_number(midpoint), "unit": "nits"},
            numeric_value=midpoint,
            value_text=text,
            unit="nits",
            quality_flags=flags,
        )
    return _parsed_present(
        {"value": _json_number(numbers[0]), "unit": "nits"},
        numeric_value=numbers[0],
        value_text=text,
        unit="nits",
        quality_flags=flags,
    )


def _parse_percentage_ratio(text: str) -> M03BParsedValue:
    number = _first_decimal(text)
    if number is None:
        return _parsed_unknown_text(text, "%", "parse_failed")
    normalized = number * Decimal("100") if number <= Decimal("1.5") else number
    flags = ("unit_inferred_percent",)
    return _parsed_present(_json_number(normalized), numeric_value=normalized, value_text=text, unit="%", quality_flags=flags)


def _parse_feature_presence(text: str, unit: str | None = None) -> M03BParsedValue:
    normalized = _normalize_text(text)
    if normalized in FALSE_LITERALS:
        return _parsed_present(False, value_text=text, unit=unit)
    if normalized in TRUE_LITERALS:
        return _parsed_present(True, value_text=text, unit=unit)
    if normalized.startswith("非") or "不支持" in text or "无" == text.strip():
        return _parsed_present(False, value_text=text, unit=unit)
    return _parsed_present(True, value_text=text, unit=unit)


def _parse_boolean(text: str, unit: str | None = None) -> M03BParsedValue:
    normalized = _normalize_text(text)
    if normalized in FALSE_LITERALS or normalized.startswith("非"):
        return _parsed_present(False, value_text=text, unit=unit)
    if normalized in TRUE_LITERALS:
        return _parsed_present(True, value_text=text, unit=unit)
    return _parsed_unknown_text(text, unit, "parse_failed")


def _parse_hdmi_mix(text: str) -> M03BParsedValue:
    matches = list(HDMI_PATTERN.finditer(text))
    versions = sorted({match.group("version") for match in matches})
    count_by_version = {
        match.group("version"): int(match.group("count") or 1)
        for match in matches
        if match.group("version")
    }
    has_21 = "2.1" in versions or "2.1" in text
    return _parsed_present(
        {
            "raw": text,
            "versions": versions,
            "has_hdmi_2_1": has_21,
            "hdmi_2_1_port_count": count_by_version.get("2.1"),
        },
        numeric_value=Decimal(count_by_version["2.1"]) if "2.1" in count_by_version else None,
        value_text=text,
    )


def _parse_hdmi_2_1_count(text: str) -> M03BParsedValue:
    match = HDMI_PATTERN.search(text)
    if match and match.group("version") == "2.1":
        count = int(match.group("count") or 1)
        return _parsed_present(count, numeric_value=Decimal(count), value_text=text)
    if "2.1" in text:
        return _parsed_present(1, numeric_value=Decimal("1"), value_text=text, quality_flags=("count_inferred",))
    return _parsed_present(0, numeric_value=Decimal("0"), value_text=text)


def _parse_usb_mix(text: str) -> M03BParsedValue:
    matches = list(USB_PATTERN.finditer(text))
    versions = sorted({match.group("version") for match in matches})
    count_by_version = {
        match.group("version"): int(match.group("count") or 1)
        for match in matches
        if match.group("version")
    }
    return _parsed_present(
        {"raw": text, "versions": versions, "has_usb_3_0": "3.0" in versions or "3.0" in text},
        numeric_value=Decimal(count_by_version["3.0"]) if "3.0" in count_by_version else None,
        value_text=text,
    )


def _parse_usb_3_flag(text: str) -> M03BParsedValue:
    return _parsed_present("3.0" in text or "USB3" in text.upper(), value_text=text)


def _source_rank(param: M03BParamDefinition, raw_field: str) -> int:
    try:
        return param.raw_fields.index(raw_field) + 1
    except ValueError:
        return 99


def _profile_entry_from_param_payload(payload: Mapping[str, Any], *, required_for_core: bool) -> dict[str, Any]:
    return {
        "param_value_id": payload.get("param_value_id"),
        "param_code": payload["param_code"],
        "param_name": payload["param_name"],
        "param_group": payload.get("param_group"),
        "data_type": payload.get("data_type"),
        "normalized_value": _json_value(payload.get("normalized_value")),
        "numeric_value": None if payload.get("numeric_value") is None else str(payload.get("numeric_value")),
        "value_text": payload.get("value_text"),
        "unit": payload.get("unit"),
        "value_presence": payload.get("value_presence"),
        "source_type": payload.get("source_type"),
        "source_priority_rank": payload.get("source_priority_rank", 99),
        "raw_param_name": payload.get("raw_param_name"),
        "raw_param_value": payload.get("raw_param_value"),
        "parser_status": payload.get("parser_status"),
        "confidence": str(payload.get("confidence")),
        "evidence_ids": list(payload.get("evidence_ids") or []),
        "quality_flags": list(payload.get("quality_flags") or []),
        "required_for_core": required_for_core,
    }


def _derived_profile_entry(
    *,
    param_code: str,
    param_name: str,
    param_group: str,
    data_type: str,
    normalized_value: Any,
    value_text: str | None,
    basis_param_codes: list[str],
    rule: str,
    evidence_ids: list[Any] | None = None,
    value_presence: str = VALUE_PRESENT,
    quality_flags: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "param_value_id": None,
        "param_code": param_code,
        "param_name": param_name,
        "param_group": param_group,
        "data_type": data_type,
        "normalized_value": _json_value(normalized_value),
        "numeric_value": None,
        "value_text": value_text,
        "unit": None,
        "value_presence": value_presence,
        "source_type": SOURCE_TAXONOMY_RULE,
        "source_priority_rank": 100,
        "raw_param_name": None,
        "raw_param_value": None,
        "parser_status": "derived",
        "confidence": "1.0000",
        "evidence_ids": _unique_preserve_order(str(item) for item in (evidence_ids or []) if item),
        "quality_flags": quality_flags or [],
        "required_for_core": False,
        "basis_param_codes": basis_param_codes,
        "rule": rule,
    }


def _select_main_profile_entry(candidates: Sequence[dict[str, Any]]) -> dict[str, Any]:
    def sort_key(entry: dict[str, Any]) -> tuple[int, int, Decimal]:
        presence_rank = {VALUE_PRESENT: 0, VALUE_DERIVED_FALSE: 1, VALUE_UNKNOWN: 2}.get(str(entry.get("value_presence")), 9)
        confidence = _decimal(entry.get("confidence"), Decimal("0")) or Decimal("0")
        return (presence_rank, int(entry.get("source_priority_rank") or 99), -confidence)

    return sorted(candidates, key=sort_key)[0]


def _has_conflict(candidates: Sequence[dict[str, Any]]) -> bool:
    values = {
        stable_hash(entry.get("normalized_value"), version="m03b_conflict_value_v1")
        for entry in candidates
        if entry.get("value_presence") == VALUE_PRESENT
    }
    return len(values) > 1


def _main_numeric(candidates: Sequence[dict[str, Any]] | None) -> Decimal | None:
    if not candidates:
        return None
    entry = _select_main_profile_entry(candidates)
    numeric = _decimal(entry.get("numeric_value"))
    if numeric is not None:
        return numeric
    value = entry.get("normalized_value")
    if isinstance(value, Mapping):
        for key in ("midpoint", "value", "count", "width"):
            numeric = _decimal(value.get(key))
            if numeric is not None:
                return numeric
    return _decimal(value)


def _main_value(values: Mapping[str, dict[str, Any]], param_code: str) -> Any:
    entry = values.get(param_code)
    if not entry:
        return None
    return entry.get("normalized_value")


def _main_text(values: Mapping[str, dict[str, Any]], param_code: str) -> str | None:
    value = _main_value(values, param_code)
    if value is None:
        entry = values.get(param_code)
        return str(entry.get("value_text")).strip() if entry and entry.get("value_text") else None
    if isinstance(value, Mapping):
        for key in ("resolution_label", "raw", "value"):
            if value.get(key) is not None:
                return str(value[key])
        return str(value)
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _main_bool(values: Mapping[str, dict[str, Any]], param_code: str) -> bool:
    value = _main_value(values, param_code)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    normalized = _normalize_text(value)
    return normalized in TRUE_LITERALS


def _display_tech_class(by_field: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    def text_for(field: str) -> str:
        record = by_field.get(field)
        return str(_record_value(record) or "") if record is not None else ""

    basis = {field: record for field, record in by_field.items() if field in {"产品技术", "背光源", "背光源细分", "MINILED", "MINILED2", "RGB", "量子点"}}
    joined = " ".join(text_for(field) for field in basis)
    upper = joined.upper()
    if "OLED" in upper:
        return "oled", basis
    if "激光" in joined or "LASER" in upper:
        return "laser", basis

    def compact(value: str) -> str:
        return _normalize_text(value).replace("-", "").replace("_", "")

    def has_miniled(value: str) -> bool:
        value_compact = compact(value)
        return "miniled" in value_compact or "mini-led" in _normalize_text(value)

    def is_miniled_negative(value: str) -> bool:
        value_normalized = _normalize_text(value)
        value_compact = compact(value)
        return value_normalized in FALSE_LITERALS or value_compact in {"非miniled", "nominiled"} or "非miniled" in value_compact

    mini_flag_text = text_for("MINILED")
    mini_type_text = text_for("MINILED2")
    backlight_source_text = text_for("背光源")
    backlight_subtype_text = text_for("背光源细分")
    product_tech_text = text_for("产品技术")
    quantum_dot_text = text_for("量子点")

    specific_type_text = " ".join((mini_type_text, backlight_subtype_text, product_tech_text))
    specific_type_upper = specific_type_text.upper()
    specific_type_compact = compact(specific_type_text)
    mini_flag_normalized = _normalize_text(mini_flag_text)
    mini_flag_positive = mini_flag_normalized in TRUE_LITERALS or (has_miniled(mini_flag_text) and not is_miniled_negative(mini_flag_text))
    subtype_positive_mini = any(has_miniled(value) and not is_miniled_negative(value) for value in (mini_type_text, backlight_subtype_text, product_tech_text))
    source_positive_mini = has_miniled(backlight_source_text) and not is_miniled_negative(backlight_source_text)
    mini = subtype_positive_mini or mini_flag_positive or source_positive_mini
    if is_miniled_negative(mini_type_text) and not (mini_flag_positive or source_positive_mini):
        mini = False
    if is_miniled_negative(mini_flag_text) and not (subtype_positive_mini or source_positive_mini):
        mini = False

    rgb_miniled = "rgbminiled" in specific_type_compact or "RGB-MINILED" in specific_type_upper or "RGB MINI" in specific_type_upper
    qd = (
        any(token in specific_type_upper for token in ("QD", "QLED", "QUANTUM"))
        or "量子点" in specific_type_text
        or any(token in upper for token in ("QLED", "QUANTUM"))
        or ("QD" in upper and not rgb_miniled)
        or (_present(quantum_dot_text) and _normalize_text(quantum_dot_text) not in FALSE_LITERALS)
    )
    if mini and rgb_miniled:
        return "rgb_miniled", basis
    if mini and qd:
        return "qd_miniled", basis
    if mini:
        return "miniled", basis
    if qd:
        return "qled_lcd", basis
    if "LCD" in upper or "LED" in upper:
        return "lcd_led", basis
    return ("unknown", basis) if basis else ("unknown", {})


def _size_tier_by_number(size: Decimal) -> str:
    if size <= Decimal("45"):
        return "small_32_45"
    if size <= Decimal("59"):
        return "medium_46_59"
    if size <= Decimal("69"):
        return "large_60_69"
    if size <= Decimal("85"):
        return "xlarge_70_85"
    if size <= Decimal("97"):
        return "xxlarge_86_97"
    return "giant_98_plus"


def _size_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    size = _decimal(values.get("screen_size_inch", {}).get("numeric_value")) if values.get("screen_size_inch") else None
    if size is None:
        return _dimension_result("size", "unknown", [], "缺少尺寸参数，无法判断尺寸段。", quality_flags=["missing_screen_size"])
    return _dimension_result("size", _size_tier_by_number(size), ["screen_size_inch"], f"尺寸 {size} 英寸，归入 {_size_tier_by_number(size)}。")


def _display_tech_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    display_class = _main_text(values, "display_tech_class") or "unknown"
    basis = ["display_tech_class", "display_technology_family", "backlight_source", "backlight_subtype", "mini_led_flag", "mini_led_type", "rgb_structure_flag", "quantum_dot_flag"]
    if display_class == "unknown":
        return _dimension_result("display_tech", "unknown", basis, "缺少可识别的显示技术、背光或 MiniLED/QD/RGB 标记。", quality_flags=["missing_display_tech"])
    return _dimension_result("display_tech", display_class, basis, f"显示技术识别为 {display_class}。")


def _local_dimming_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    zones = _decimal(values.get("local_dimming_zone_count", {}).get("numeric_value")) if values.get("local_dimming_zone_count") else None
    if zones is None:
        return _dimension_result("local_dimming", "unknown", ["local_dimming_zone_count"], "缺少分区背光数量。", quality_flags=["missing_local_dimming"])
    if zones <= 0:
        tier = "z_none_0"
    elif zones <= 499:
        tier = "z_entry_1_499"
    elif zones <= 999:
        tier = "z_mid_500_999"
    elif zones <= 1999:
        tier = "z_high_1000_1999"
    elif zones <= 3999:
        tier = "z_premium_2000_3999"
    else:
        tier = "z_flagship_4000_plus"
    return _dimension_result("local_dimming", tier, ["local_dimming_zone_count"], f"分区背光 {int(zones)}，归入 {tier}。")


def _picture_overall_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    basis = [
        "resolution_label",
        "resolution_pixels",
        "declared_refresh_rate_hz",
        "declared_brightness_nit_or_band",
        "hdr_support_flag",
        "color_gamut_ratio",
        "high_color_gamut_flag",
        "display_tech_class",
        "local_dimming_zone_count",
    ]
    resolution = (_main_text(values, "resolution_label") or _main_text(values, "resolution_class") or "").upper()
    refresh = _decimal(values.get("declared_refresh_rate_hz", {}).get("numeric_value")) if values.get("declared_refresh_rate_hz") else None
    brightness = _decimal(values.get("declared_brightness_nit_or_band", {}).get("numeric_value")) if values.get("declared_brightness_nit_or_band") else None
    zones = _decimal(values.get("local_dimming_zone_count", {}).get("numeric_value")) if values.get("local_dimming_zone_count") else None
    display_class = _main_text(values, "display_tech_class") or "unknown"
    hdr = _main_bool(values, "hdr_support_flag")
    color = _decimal(values.get("color_gamut_ratio", {}).get("numeric_value")) if values.get("color_gamut_ratio") else None
    high_color = _main_bool(values, "high_color_gamut_flag") or (color is not None and color >= Decimal("95"))

    if resolution in {"HD", "FHD"} or (refresh is not None and refresh <= Decimal("60") and display_class in {"lcd_led", "qled_lcd"}):
        tier = "picture_basic"
    elif display_class in {"qd_miniled", "rgb_miniled"} and (brightness or Decimal("0")) >= Decimal("1500") and (zones or Decimal("0")) >= Decimal("1000"):
        tier = "picture_flagship"
    elif display_class in {"miniled", "qd_miniled", "rgb_miniled"} and ((brightness or Decimal("0")) >= Decimal("600") or (zones or Decimal("0")) >= Decimal("500")):
        tier = "picture_premium"
    elif refresh and refresh >= Decimal("120") or hdr or high_color or (brightness and brightness >= Decimal("500")):
        tier = "picture_enhanced"
    elif resolution in {"4K", "8K"}:
        tier = "picture_mainstream"
    else:
        tier = "picture_basic"
    return _dimension_result("picture_overall", tier, basis, f"画质档位由清晰度 {resolution or '未知'}、刷新率 {refresh or '未知'}、亮度 {brightness or '未知'}、显示技术 {display_class} 与分区 {zones if zones is not None else '未知'} 综合判断。")


def _performance_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    ram = _decimal(values.get("ram_gb", {}).get("numeric_value")) if values.get("ram_gb") else None
    storage = _decimal(values.get("storage_gb", {}).get("numeric_value")) if values.get("storage_gb") else None
    basis = ["ram_gb", "storage_gb", "cpu_core_count", "cpu_frequency_ghz", "processor_chip_model", "processor_vendor"]
    if ram is None or storage is None:
        return _dimension_result("performance", "perf_unknown", basis, "RAM 或 ROM 关键性能输入缺失。", quality_flags=["missing_performance_core"])
    if ram <= Decimal("1.5") or storage <= Decimal("16"):
        tier = "perf_low"
    elif ram <= Decimal("2") or storage <= Decimal("32"):
        tier = "perf_basic"
    elif ram >= Decimal("6") or storage >= Decimal("128"):
        tier = "perf_high"
    elif ram >= Decimal("4") and storage >= Decimal("64"):
        tier = "perf_main_plus"
    else:
        tier = "perf_mainstream"
    return _dimension_result("performance", tier, basis, f"RAM {ram}GB，ROM {storage}GB，归入 {tier}。")


def _smart_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    basis = ["ai_model_name", "ai_model_capability_flag", "ai_capability_flag", "voice_engine", "voice_recognition_flag", "far_field_voice_flag", "camera_flag", "whole_home_control_flag", "smart_tv_flag", "network_tv_flag"]
    ai_model = _main_bool(values, "ai_model_capability_flag") or bool(_main_text(values, "ai_model_name"))
    voice = _main_bool(values, "voice_recognition_flag") or _main_bool(values, "far_field_voice_flag") or bool(_main_text(values, "voice_engine"))
    camera_or_iot = _main_bool(values, "camera_flag") or _main_bool(values, "whole_home_control_flag")
    ai_basic = _main_bool(values, "ai_capability_flag") or ai_model
    if camera_or_iot:
        tier = "smart_interaction_iot"
    elif ai_model and voice:
        tier = "smart_ai_voice"
    elif ai_basic or voice:
        tier = "smart_voice_ai_basic"
    else:
        tier = "smart_basic"
    return _dimension_result("smart", tier, basis, f"智能档位由 AI 大模型、语音/远场语音、摄像头和全屋智控综合判断，结果为 {tier}。")


def _ports_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    basis = ["hdmi_version_mix", "hdmi_2_1_port_count", "hdmi_port_count", "usb_version_mix", "usb_3_0_flag", "usb_port_count"]
    hdmi = _decimal(values.get("hdmi_port_count", {}).get("numeric_value")) if values.get("hdmi_port_count") else None
    usb = _decimal(values.get("usb_port_count", {}).get("numeric_value")) if values.get("usb_port_count") else None
    hdmi_mix = _main_value(values, "hdmi_version_mix")
    has_hdmi21 = bool(hdmi_mix.get("has_hdmi_2_1")) if isinstance(hdmi_mix, Mapping) else False
    usb3 = _main_bool(values, "usb_3_0_flag")
    if hdmi is None or usb is None:
        return _dimension_result("ports", "ports_unknown", basis, "HDMI 或 USB 数量缺失。", quality_flags=["missing_ports_core"])
    if hdmi <= 1 or usb <= 1:
        tier = "ports_weak"
    elif hdmi >= 4 and has_hdmi21 and usb3:
        tier = "ports_rich"
    elif hdmi >= 3 or (has_hdmi21 and usb3):
        tier = "ports_main_plus"
    elif has_hdmi21:
        tier = "ports_main_hdmi21"
    else:
        tier = "ports_basic"
    return _dimension_result("ports", tier, basis, f"HDMI {hdmi} 个，USB {usb} 个，HDMI2.1={has_hdmi21}，USB3.0={usb3}，归入 {tier}。")


def _appearance_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    basis = ["body_thickness_mm", "slim_design_flag", "full_screen_design_flag", "flush_wall_mount_flag", "portable_tv_flag"]
    thickness = _decimal(values.get("body_thickness_mm", {}).get("numeric_value")) if values.get("body_thickness_mm") else None
    if _main_bool(values, "flush_wall_mount_flag"):
        return _dimension_result("appearance", "appearance_wall_flush", basis, "有无缝贴墙特性。")
    if _main_bool(values, "slim_design_flag") or (thickness is not None and thickness <= Decimal("50")):
        return _dimension_result("appearance", "appearance_ultra_slim", basis, f"超薄标签成立或厚度 {thickness or '未知'}mm。")
    if _main_bool(values, "full_screen_design_flag") and thickness is not None and thickness <= Decimal("60"):
        return _dimension_result("appearance", "appearance_slim_fullscreen", basis, f"全面屏且厚度 {thickness}mm。")
    if thickness is None:
        return _dimension_result("appearance", "appearance_unknown", basis, "缺少机身厚度且无外观特性。", quality_flags=["missing_appearance_core"])
    if thickness <= Decimal("60"):
        tier = "appearance_slim"
    elif thickness <= Decimal("75"):
        tier = "appearance_standard"
    elif thickness <= Decimal("90"):
        tier = "appearance_thick"
    else:
        tier = "appearance_heavy"
    return _dimension_result("appearance", tier, basis, f"机身厚度 {thickness}mm，归入 {tier}。")


def _energy_dimension(values: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    grade_text = (_main_text(values, "energy_efficiency_grade") or "").strip()
    basis = ["energy_efficiency_grade", "energy_efficiency_index", "standby_power_w"]
    if not grade_text:
        return _dimension_result("energy", "energy_unknown", basis, "缺少能效等级。", quality_flags=["missing_energy_grade"])
    if "1" in grade_text or "一" in grade_text:
        tier = "energy_grade_1"
    elif "2" in grade_text or "二" in grade_text:
        tier = "energy_grade_2"
    elif any(token in grade_text for token in ("3", "4", "三", "四")):
        tier = "energy_grade_3_4"
    else:
        tier = "energy_unknown"
    return _dimension_result("energy", tier, basis, f"能效等级为 {grade_text}，归入 {tier}。")


def _dimension_result(
    dimension_code: str,
    tier_code: str,
    basis_param_codes: list[str],
    explanation: str,
    *,
    quality_flags: list[str] | None = None,
    confidence: Decimal = Decimal("0.9000"),
) -> dict[str, Any]:
    return {
        "dimension_code": dimension_code,
        "tier_code": tier_code,
        "basis_param_codes": basis_param_codes,
        "explanation": explanation,
        "quality_flags": quality_flags or [],
        "confidence": confidence,
    }


def _basis_values(values: Mapping[str, dict[str, Any]], param_codes: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for param_code in param_codes:
        entry = values.get(param_code)
        if not entry:
            continue
        result[param_code] = {
            "normalized_value": _json_value(entry.get("normalized_value")),
            "numeric_value": entry.get("numeric_value"),
            "value_text": entry.get("value_text"),
            "value_presence": entry.get("value_presence"),
            "evidence_ids": list(entry.get("evidence_ids") or []),
        }
    return result


def _core_summary(values: Mapping[str, dict[str, Any]], param_codes: Sequence[str]) -> dict[str, Any]:
    return _basis_values(values, param_codes)


def _unique_preserve_order(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _param_value_id(project_id: str, batch_id: str, sku_code: str, param_code: str, evidence_id: str, parser_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "param_code": param_code,
            "evidence_id": evidence_id,
            "parser_version": parser_version,
        },
        version=M03B_PARAM_VALUE_ID_HASH_VERSION,
    )


def _sku_profile_id(project_id: str, batch_id: str, sku_code: str, taxonomy_version: str, rule_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "taxonomy_version": taxonomy_version,
            "rule_version": rule_version,
        },
        version=M03B_SKU_PROFILE_ID_HASH_VERSION,
    )


def _dimension_tier_id(project_id: str, batch_id: str, sku_code: str, taxonomy_version: str, dimension_code: str, rule_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "sku_code": sku_code,
            "taxonomy_version": taxonomy_version,
            "dimension_code": dimension_code,
            "rule_version": rule_version,
        },
        version=M03B_DIMENSION_TIER_ID_HASH_VERSION,
    )


def _tier_coverage_id(project_id: str, batch_id: str, taxonomy_version: str, dimension_code: str, tier_code: str, rule_version: str) -> str:
    return stable_hash(
        {
            "project_id": project_id,
            "batch_id": batch_id,
            "taxonomy_version": taxonomy_version,
            "dimension_code": dimension_code,
            "tier_code": tier_code,
            "rule_version": rule_version,
        },
        version=M03B_TIER_COVERAGE_ID_HASH_VERSION,
    )


def _confidence_for(parsed: M03BParsedValue, base_confidence: Decimal | None) -> Decimal:
    confidence = base_confidence or Decimal("0.9000")
    if parsed.value_presence == VALUE_UNKNOWN:
        confidence -= Decimal("0.2000")
    if parsed.parser_status != "parsed":
        confidence -= Decimal("0.0500")
    return max(Decimal("0.0000"), min(confidence, Decimal("1.0000")))


def _confidence_level(confidence: Decimal) -> str:
    if confidence >= Decimal("0.8500"):
        return "high"
    if confidence >= Decimal("0.6000"):
        return "medium"
    return "low"


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"))


def _tier_distribution(dimension_tiers: Sequence[M03BDimensionTier]) -> dict[str, dict[str, int]]:
    result: dict[str, Counter[str]] = {}
    for tier in dimension_tiers:
        payload = tier.payload
        result.setdefault(payload["dimension_code"], Counter())[payload["tier_code"]] += 1
    return {dimension: dict(sorted(counter.items())) for dimension, counter in sorted(result.items())}


def _taxonomy_summary(taxonomy: M03BTaxonomy) -> dict[str, Any]:
    return {
        "taxonomy_version": taxonomy.taxonomy_version,
        "category_code": taxonomy.category_code,
        "standard_params": [
            {
                "param_code": param.param_code,
                "raw_fields": list(param.raw_fields),
                "parser": param.parser,
                "missing_policy": param.missing_policy,
                "required_for_core": param.required_for_core,
            }
            for param in taxonomy.standard_params
        ],
        "excluded_raw_fields": taxonomy.excluded_raw_fields,
        "dimension_tiers": [
            {
                "dimension_code": tier.dimension_code,
                "tier_code": tier.tier_code,
                "tier_rank": tier.tier_rank,
                "rule_summary": tier.rule_summary,
            }
            for tier in taxonomy.dimension_tiers
        ],
    }


def _write_summary(result: ParamRepositoryWriteResult) -> dict[str, int]:
    return {"created_count": result.created_count, "reused_count": result.reused_count}


def _warnings(summary: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if int(summary.get("input_param_raw_count") or 0) == 0:
        warnings.append("m03b_empty_param_raw_evidence")
    if int(summary.get("conflict_count") or 0) > 0:
        warnings.append("m03b_param_value_conflicts_need_review")
    return warnings


def _output_count(result: M03BServiceResult) -> int:
    return result.param_value_count + result.sku_profile_count + result.dimension_tier_count + result.tier_coverage_count


def _downstream_impacts(result: M03BServiceResult) -> list[dict[str, Any]]:
    return [
        {
            "module_code": "M04A",
            "impact_level": "medium",
            "reason_cn": "SKU 参数事实画像更新后，可为卖点事实画像提供参数证据。",
            "changed_input_count": result.sku_profile_count,
        },
        {
            "module_code": "M08",
            "impact_level": "medium",
            "reason_cn": "参数档位覆盖更新后，可支撑后续任务、客群、战场和竞品候选池筛选。",
            "changed_input_count": result.dimension_tier_count,
        },
    ]


def _blocked_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    message_cn: str,
    started_at: datetime,
    finished_at: datetime,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M03B,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(
            {"project_id": project_id, "category_code": category_code, "batch_id": batch_id, "run_id": run_id, "message": message_cn},
            version="m03b_blocked_v1",
        ),
        warnings=[message_cn],
        review_issues=[],
        downstream_impacts=[],
        summary_json={"project_id": project_id, "category_code": category_code, "batch_id": batch_id, "message_cn": message_cn},
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    started_at: datetime,
    error_code: str,
    message_cn: str,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M03B,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(
            {"project_id": project_id, "category_code": category_code, "batch_id": batch_id, "run_id": run_id, "error_code": error_code, "error": error_message},
            version="m03b_failed_v1",
        ),
        warnings=[message_cn],
        review_issues=[{"issue_code": error_code, "message_cn": message_cn, "error_message": error_message}],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "error_code": error_code,
            "message_cn": message_cn,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
