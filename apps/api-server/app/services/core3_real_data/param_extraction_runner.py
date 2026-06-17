"""M03 parameter extraction runner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M03_MODULE_VERSION,
    CORE3_M03_PARSER_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_conflicts import ParamConflictDetector
from app.services.core3_real_data.param_extraction_repositories import (
    ParamEvidenceReader,
    ParamExtractionRepository,
    ParamRepositoryHashConflictError,
    ParamRepositoryWriteResult,
)
from app.services.core3_real_data.param_extraction_schemas import ParamCandidateStatus, ParamReviewStatus
from app.services.core3_real_data.param_extraction_service import ParamValueExtractor
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_profile_builder import SkuParamProfileBuilder
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


ALIAS_CANDIDATE_ID_HASH_VERSION = "m03-alias-candidate-id-v1"


@dataclass(frozen=True)
class ParamExtractionServiceResult:
    input_count: int
    field_profile_count: int
    param_value_count: int
    sku_profile_count: int
    alias_candidate_count: int
    conflict_count: int
    review_required_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def created_output_count(self) -> int:
        return sum(item["created_count"] for item in self.write_summary.values())

    @property
    def reused_output_count(self) -> int:
        return sum(item["reused_count"] for item in self.write_summary.values())


class ParamExtractionRunner:
    module_code = Core3ModuleCode.M03

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
                message_cn="M03 缺少 M00 batch_id，无法确定参数抽取范围。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )

        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            seed_version=str(target.metadata.get("seed_version") or CORE3_M03_SEED_VERSION),
            parser_version=str(target.metadata.get("parser_version") or CORE3_M03_PARSER_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M03_RULE_VERSION),
            target_sku_codes=target.target_ids,
            force_rebuild=bool(target.metadata.get("force_rebuild")),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M03_SEED_VERSION,
        parser_version: str = CORE3_M03_PARSER_VERSION,
        rule_version: str = CORE3_M03_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
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
                service_result = ParamExtractionService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    seed_version=seed_version,
                    parser_version=parser_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    force_rebuild=force_rebuild,
                )
        except ParamRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m03_param_hash_conflict",
                message_cn="M03 参数抽取结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m03_param_extraction_failed",
                message_cn="M03 参数抽取失败，请检查 M02 evidence、参数 seed 或字段匹配规则。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M03_MODULE_VERSION,
            "seed_version": seed_version,
            "parser_version": parser_version,
            "rule_version": rule_version,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m03_param_extraction_summary_v1")
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M03,
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


class ParamExtractionService:
    """Build M03 outputs from M02 current evidence and write them transactionally."""

    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M03_SEED_VERSION,
        parser_version: str = CORE3_M03_PARSER_VERSION,
        rule_version: str = CORE3_M03_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> ParamExtractionServiceResult:
        seed = StdParamSeedLoader().load_seed()
        evidence_records = ParamEvidenceReader(self.context).list_param_evidence(
            batch_id,
            target_sku_codes=target_sku_codes,
        )
        total_sku_count = _count_distinct_sku(evidence_records)
        field_profiles = ParamFieldProfiler(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed_version=seed_version,
            rule_version=rule_version,
        ).build_profiles(evidence_records, total_sku_count=total_sku_count)
        matched_field_profiles = ParamAliasMatcher(seed).apply_matches(field_profiles)
        param_values = ParamValueExtractor(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed=seed,
            seed_version=seed_version,
            parser_version=parser_version,
            rule_version=rule_version,
        ).extract_values(evidence_records, matched_field_profiles)
        param_values, conflicts = ParamConflictDetector(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        ).apply_conflicts(param_values)
        sku_profiles = SkuParamProfileBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed=seed,
            seed_version=seed_version,
            rule_version=rule_version,
        ).build_profiles(param_values, conflicts)
        alias_candidates = [
            _alias_candidate_payload(
                profile,
                project_id=self.context.project_id,
                category_code=self.context.category_code.value,
                batch_id=batch_id,
                seed_version=seed_version,
            )
            for profile in matched_field_profiles
            if _needs_alias_candidate(profile)
        ]

        repository = ParamExtractionRepository(self.context)
        write_results = {
            "field_profiles": repository.save_field_profiles(
                matched_field_profiles,
                replace_on_hash_conflict=force_rebuild,
            ),
            "param_values": repository.save_param_values(
                param_values,
                replace_on_hash_conflict=force_rebuild,
            ),
            "alias_candidates": repository.save_alias_candidates(
                alias_candidates,
                replace_existing=force_rebuild,
            ),
            "param_conflicts": repository.save_param_conflicts(
                conflicts,
                replace_existing=force_rebuild,
            ),
            "sku_param_profiles": repository.save_sku_param_profiles(
                sku_profiles,
                replace_on_hash_conflict=force_rebuild,
            ),
        }
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        warnings = _warnings(
            input_count=len(evidence_records),
            alias_candidate_count=len(alias_candidates),
            conflict_count=len(conflicts),
            value_review_count=sum(1 for value in param_values if value.review_required),
            field_review_count=sum(1 for profile in matched_field_profiles if profile.review_required),
        )
        review_required_count = (
            sum(1 for profile in matched_field_profiles if profile.review_required)
            + sum(1 for value in param_values if value.review_required)
            + len(alias_candidates)
            + sum(1 for conflict in conflicts if conflict.review_required)
        )
        summary = {
            "input_evidence_count": len(evidence_records),
            "field_profile_count": len(matched_field_profiles),
            "param_value_count": len(param_values),
            "sku_profile_count": len(sku_profiles),
            "alias_candidate_count": len(alias_candidates),
            "conflict_count": len(conflicts),
            "review_required_count": review_required_count,
            "write_summary": write_summary,
            "by_evidence_type": _count_by(getattr(record, "evidence_type", "") for record in evidence_records),
            "by_param_group": _count_by(str(getattr(value, "param_group", "") or "unknown") for value in param_values),
            "conflict_type_counts": _count_by(conflict.conflict_type for conflict in conflicts),
            "review_summary": {
                "field_review_required_count": sum(1 for profile in matched_field_profiles if profile.review_required),
                "value_review_required_count": sum(1 for value in param_values if value.review_required),
                "alias_candidate_count": len(alias_candidates),
                "conflict_review_required_count": sum(1 for conflict in conflicts if conflict.review_required),
            },
        }
        return ParamExtractionServiceResult(
            input_count=len(evidence_records),
            field_profile_count=len(matched_field_profiles),
            param_value_count=len(param_values),
            sku_profile_count=len(sku_profiles),
            alias_candidate_count=len(alias_candidates),
            conflict_count=len(conflicts),
            review_required_count=review_required_count,
            warnings=warnings,
            write_summary=write_summary,
            summary=summary,
        )


def _alias_candidate_payload(
    profile: Any,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    seed_version: str,
) -> dict[str, Any]:
    clean_param_name = str(_field(profile, "clean_param_name") or "")
    digest = stable_hash(
        {
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "clean_param_name": clean_param_name,
            "seed_version": seed_version,
        },
        version=ALIAS_CANDIDATE_ID_HASH_VERSION,
    ).split(":")[-1]
    return {
        "alias_candidate_id": f"m03alias_{digest[:32]}",
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "raw_param_name": _field(profile, "raw_param_name"),
        "clean_param_name": clean_param_name,
        "sku_coverage_rate": _decimal(_field(profile, "sku_coverage_rate"), Decimal("0.000000")),
        "unknown_rate": _decimal(_field(profile, "unknown_rate"), Decimal("0.000000")),
        "top_values_json": _field(profile, "top_values_json") or [],
        "value_pattern_summary_json": _field(profile, "value_pattern_summary_json") or {},
        "suggested_param_code": None,
        "suggestion_reason": "高覆盖未映射参数字段，需人工判断是否补充标准参数或别名。",
        "confidence": Decimal("0.0000"),
        "candidate_type": "unmatched_field",
        "review_required": True,
        "review_status": ParamReviewStatus.REVIEW_REQUIRED.value,
        "review_decision_json": {},
        "seed_version": seed_version,
    }


def _needs_alias_candidate(profile: Any) -> bool:
    candidate_status = str(_field(profile, "candidate_status") or "")
    return (
        _field(profile, "matched_param_code") is None
        and candidate_status == ParamCandidateStatus.CANDIDATE.value
        and bool(_field(profile, "review_required"))
    )


def _warnings(
    *,
    input_count: int,
    alias_candidate_count: int,
    conflict_count: int,
    value_review_count: int,
    field_review_count: int,
) -> list[str]:
    warnings: list[str] = []
    if input_count == 0:
        warnings.append("m03_empty_param_evidence")
    if field_review_count > 0:
        warnings.append("m03_param_field_review_required")
    if alias_candidate_count > 0:
        warnings.append("m03_alias_candidate_review_required")
    if value_review_count > 0:
        warnings.append("m03_param_value_review_required")
    if conflict_count > 0:
        warnings.append("m03_param_conflict_review_required")
    return warnings


def _write_summary(result: ParamRepositoryWriteResult) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "total_count": len(result.records),
    }


def _output_count(result: ParamExtractionServiceResult) -> int:
    return (
        result.field_profile_count
        + result.param_value_count
        + result.sku_profile_count
        + result.alias_candidate_count
        + result.conflict_count
    )


def _downstream_impacts(result: ParamExtractionServiceResult) -> list[dict[str, Any]]:
    if _output_count(result) == 0:
        return []
    return [
        {
            "module_code": Core3ModuleCode.M04A.value,
            "reason_cn": "参数标准化结果可用于卖点参数证明和参数型卖点激活。",
        },
        {
            "module_code": Core3ModuleCode.M08.value,
            "reason_cn": "SKU 参数画像变化会影响后续综合信号画像。",
        },
        {
            "module_code": Core3ModuleCode.M13.value,
            "reason_cn": "参数画像和冲突复核结果会影响竞品评分组件。",
        },
        {
            "module_code": Core3ModuleCode.M16.value,
            "reason_cn": "M03 复核项需要进入增量编排和验收看板。",
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
        module_code=Core3ModuleCode.M03,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=["m03_batch_not_consumable"],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "message_cn": message_cn,
        },
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
    summary_json = {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "run_id": run_id,
        "error_code": error_code,
        "message_cn": message_cn,
        "error_message": error_message,
    }
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M03,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m03_param_failed_v1"),
        warnings=[error_code],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _count_distinct_sku(records: Sequence[Any]) -> int:
    return len({str(record.sku_code) for record in records if getattr(record, "sku_code", None)})


def _count_by(values: Sequence[str] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _field(record: Any, field_name: str) -> Any:
    if isinstance(record, dict):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _decimal(value: Any, default: Decimal) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
