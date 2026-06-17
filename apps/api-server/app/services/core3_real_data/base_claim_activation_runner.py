"""M04a base claim activation runner."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.base_claim_activation_repositories import (
    ClaimActivationRepository,
    ClaimActivationRepositoryHashConflictError,
    ClaimActivationRepositoryWriteResult,
    ClaimEvidenceReader,
    SkuParamProfileReader,
)
from app.services.core3_real_data.base_claim_activation_schemas import ClaimActivationBasis, ClaimSourceStatus
from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader
from app.services.core3_real_data.claim_activation_scorer import ClaimActivationBaseScorer
from app.services.core3_real_data.claim_source_status_builder import ClaimSourceStatusBuilder, ClaimSourceStatusInput
from app.services.core3_real_data.claim_support_scorer import ClaimSupportScorer
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M04A_MODULE_VERSION,
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.promo_claim_matcher import PromoClaimMatcher
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


@dataclass(frozen=True)
class BaseClaimActivationServiceResult:
    input_count: int
    source_status_count: int
    claim_hit_count: int
    activation_base_count: int
    param_only_count: int
    missing_structured_claim_sku_count: int
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


class BaseClaimActivationRunner:
    module_code = Core3ModuleCode.M04A

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
                message_cn="M04a 缺少 M00 batch_id，无法确定基础卖点激活范围。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )

        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            seed_version=str(target.metadata.get("seed_version") or CORE3_M04A_SEED_VERSION),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M04A_RULE_VERSION),
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
        seed_version: str = CORE3_M04A_SEED_VERSION,
        rule_version: str = CORE3_M04A_RULE_VERSION,
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
                service_result = BaseClaimActivationService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    seed_version=seed_version,
                    rule_version=rule_version,
                    target_sku_codes=target_sku_codes,
                    force_rebuild=force_rebuild,
                )
        except ClaimActivationRepositoryHashConflictError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m04a_claim_activation_hash_conflict",
                message_cn="M04a 基础卖点结果与既有同批次业务键结果 hash 不一致，已停止以避免覆盖旧结果。",
                error_message=str(exc),
            )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m04a_claim_activation_failed",
                message_cn="M04a 基础卖点激活失败，请检查 M02 evidence、M03 参数画像或标准卖点 seed。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M04A_MODULE_VERSION,
            "seed_version": seed_version,
            "rule_version": rule_version,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m04a_claim_activation_summary_v1")
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M04A,
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


class BaseClaimActivationService:
    """Build M04a outputs from M02 evidence and M03 SKU parameter profiles."""

    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        seed_version: str = CORE3_M04A_SEED_VERSION,
        rule_version: str = CORE3_M04A_RULE_VERSION,
        target_sku_codes: Sequence[str] = (),
        force_rebuild: bool = False,
    ) -> BaseClaimActivationServiceResult:
        seed = StdClaimSeedLoader().load_seed()
        evidence_records = ClaimEvidenceReader(self.context).list_claim_evidence(
            batch_id,
            target_sku_codes=target_sku_codes,
        )
        sku_param_profiles = SkuParamProfileReader(self.context).list_sku_param_profiles(
            batch_id,
            target_sku_codes=target_sku_codes,
        )
        evidence_by_sku = _group_by_sku(evidence_records)
        profiles_by_sku = _latest_profile_by_sku(sku_param_profiles)
        sku_codes = _sku_codes(target_sku_codes, evidence_by_sku, profiles_by_sku)

        source_status_builder = ClaimSourceStatusBuilder(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed_version=seed_version,
            rule_version=rule_version,
        )
        preliminary_source_statuses = source_status_builder.build_many(
            [
                ClaimSourceStatusInput(
                    sku_code=sku_code,
                    model_name=_model_name_for_sku(sku_code, profiles_by_sku, evidence_by_sku),
                    evidence_records=tuple(evidence_by_sku.get(sku_code, ())),
                    param_profile=profiles_by_sku.get(sku_code),
                )
                for sku_code in sku_codes
            ]
        )
        source_status_by_sku = {status.sku_code: status for status in preliminary_source_statuses}

        claim_hits = PromoClaimMatcher(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed=seed,
            seed_version=seed_version,
            rule_version=rule_version,
        ).match(evidence_records)
        hits_by_sku = _group_by_sku(claim_hits)

        support_scorer = ClaimSupportScorer()
        activation_scorer = ClaimActivationBaseScorer(
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            seed_version=seed_version,
            rule_version=rule_version,
        )
        claims_by_code = {claim.claim_code: claim for claim in seed.standard_claims}
        activation_bases = []
        for sku_code in sku_codes:
            profile = profiles_by_sku.get(sku_code)
            sku_hits = hits_by_sku.get(sku_code, [])
            supports = support_scorer.score_all(seed, sku_param_profile=profile, claim_hits=sku_hits)
            activation_bases.extend(
                activation_scorer.score_many(
                    claims_by_code,
                    supports,
                    sku_code=sku_code,
                    model_name=_model_name_for_sku(sku_code, profiles_by_sku, evidence_by_sku),
                    source_status=source_status_by_sku.get(sku_code),
                )
            )

        param_only_count_by_sku = Counter(
            activation.sku_code
            for activation in activation_bases
            if activation.activation_basis == ClaimActivationBasis.PARAM_ONLY.value
        )
        source_statuses = source_status_builder.build_many(
            [
                ClaimSourceStatusInput(
                    sku_code=sku_code,
                    model_name=_model_name_for_sku(sku_code, profiles_by_sku, evidence_by_sku),
                    evidence_records=tuple(evidence_by_sku.get(sku_code, ())),
                    param_profile=profiles_by_sku.get(sku_code),
                    param_only_claim_count=param_only_count_by_sku.get(sku_code, 0),
                )
                for sku_code in sku_codes
            ]
        )

        repository = ClaimActivationRepository(self.context)
        write_results = {
            "source_statuses": repository.save_source_statuses(
                source_statuses,
                replace_on_hash_conflict=force_rebuild,
            ),
            "claim_hits": repository.save_claim_hits(
                claim_hits,
                replace_on_hash_conflict=force_rebuild,
            ),
            "activation_bases": repository.save_activation_bases(
                activation_bases,
                replace_on_hash_conflict=force_rebuild,
            ),
        }
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        missing_structured_claim_sku_count = sum(
            1
            for status in source_statuses
            if status.claim_source_status == ClaimSourceStatus.MISSING_STRUCTURED_CLAIM.value
        )
        param_only_count = sum(
            1 for activation in activation_bases if activation.activation_basis == ClaimActivationBasis.PARAM_ONLY.value
        )
        review_required_count = (
            sum(1 for status in source_statuses if status.review_required)
            + sum(1 for hit in claim_hits if hit.review_required)
            + sum(1 for activation in activation_bases if activation.review_required)
        )
        warnings = _warnings(
            input_count=len(evidence_records) + len(sku_param_profiles),
            source_status_count=len(source_statuses),
            claim_hit_review_count=sum(1 for hit in claim_hits if hit.review_required),
            activation_review_count=sum(1 for activation in activation_bases if activation.review_required),
            param_only_count=param_only_count,
            missing_structured_claim_sku_count=missing_structured_claim_sku_count,
        )
        summary = {
            "input_evidence_count": len(evidence_records),
            "sku_param_profile_count": len(sku_param_profiles),
            "source_status_count": len(source_statuses),
            "claim_hit_count": len(claim_hits),
            "activation_base_count": len(activation_bases),
            "param_only_count": param_only_count,
            "missing_structured_claim_sku_count": missing_structured_claim_sku_count,
            "review_required_count": review_required_count,
            "write_summary": write_summary,
            "by_evidence_type": _count_by(_field(record, "evidence_type") for record in evidence_records),
            "by_claim_source_status": _count_by(status.claim_source_status for status in source_statuses),
            "by_claim_group": _count_by(activation.claim_group for activation in activation_bases),
            "by_activation_basis": _count_by(activation.activation_basis for activation in activation_bases),
            "by_activation_level": _count_by(activation.activation_level for activation in activation_bases),
            "review_summary": {
                "source_status_review_required_count": sum(1 for status in source_statuses if status.review_required),
                "claim_hit_review_required_count": sum(1 for hit in claim_hits if hit.review_required),
                "activation_review_required_count": sum(
                    1 for activation in activation_bases if activation.review_required
                ),
            },
        }
        return BaseClaimActivationServiceResult(
            input_count=len(evidence_records) + len(sku_param_profiles),
            source_status_count=len(source_statuses),
            claim_hit_count=len(claim_hits),
            activation_base_count=len(activation_bases),
            param_only_count=param_only_count,
            missing_structured_claim_sku_count=missing_structured_claim_sku_count,
            review_required_count=review_required_count,
            warnings=warnings,
            write_summary=write_summary,
            summary=summary,
        )


def _group_by_sku(records: Sequence[Any]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for record in records:
        sku_code = _field(record, "sku_code")
        if sku_code:
            grouped[str(sku_code)].append(record)
    return dict(grouped)


def _latest_profile_by_sku(records: Sequence[Any]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for record in records:
        sku_code = _field(record, "sku_code")
        if sku_code and str(sku_code) not in profiles:
            profiles[str(sku_code)] = record
    return profiles


def _sku_codes(
    target_sku_codes: Sequence[str],
    evidence_by_sku: Mapping[str, Sequence[Any]],
    profiles_by_sku: Mapping[str, Any],
) -> list[str]:
    if target_sku_codes:
        return sorted(str(sku_code) for sku_code in target_sku_codes if str(sku_code).strip())
    return sorted(set(evidence_by_sku) | set(profiles_by_sku))


def _model_name_for_sku(
    sku_code: str,
    profiles_by_sku: Mapping[str, Any],
    evidence_by_sku: Mapping[str, Sequence[Any]],
) -> str | None:
    profile_model_name = _field(profiles_by_sku.get(sku_code), "model_name")
    if profile_model_name:
        return str(profile_model_name)
    for record in evidence_by_sku.get(sku_code, ()):
        model_name = _field(record, "model_name")
        if model_name:
            return str(model_name)
    return None


def _warnings(
    *,
    input_count: int,
    source_status_count: int,
    claim_hit_review_count: int,
    activation_review_count: int,
    param_only_count: int,
    missing_structured_claim_sku_count: int,
) -> list[str]:
    warnings: list[str] = []
    if input_count == 0 or source_status_count == 0:
        warnings.append("m04a_empty_claim_inputs")
    if missing_structured_claim_sku_count > 0:
        warnings.append("m04a_structured_claim_missing")
    if param_only_count > 0:
        warnings.append("m04a_param_only_review_required")
    if claim_hit_review_count > 0:
        warnings.append("m04a_claim_hit_review_required")
    if activation_review_count > 0:
        warnings.append("m04a_claim_activation_review_required")
    return warnings


def _write_summary(result: ClaimActivationRepositoryWriteResult) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "total_count": len(result.records),
    }


def _output_count(result: BaseClaimActivationServiceResult) -> int:
    return result.source_status_count + result.claim_hit_count + result.activation_base_count


def _downstream_impacts(result: BaseClaimActivationServiceResult) -> list[dict[str, Any]]:
    if _output_count(result) == 0:
        return []
    return [
        {
            "module_code": Core3ModuleCode.M04B.value,
            "reason_cn": "基础卖点激活结果需要进入评论验证，判断卖点是否被用户真实感知。",
        },
        {
            "module_code": Core3ModuleCode.M08.value,
            "reason_cn": "基础卖点画像会影响 SKU 综合信号画像。",
        },
        {
            "module_code": Core3ModuleCode.M11_5.value,
            "reason_cn": "标准卖点激活强弱会影响战场内卖点价值分层。",
        },
        {
            "module_code": Core3ModuleCode.M13.value,
            "reason_cn": "基础卖点证据会进入核心竞品评分组件。",
        },
        {
            "module_code": Core3ModuleCode.M16.value,
            "reason_cn": "M04a 复核项和输出变化需要进入增量编排和验收看板。",
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
        module_code=Core3ModuleCode.M04A,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=None,
        warnings=["m04a_batch_not_consumable"],
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
        module_code=Core3ModuleCode.M04A,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m04a_claim_activation_failed_v1"),
        warnings=[error_code],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _count_by(values: Sequence[str] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _field(record: Any, field_name: str) -> Any:
    if record is None:
        return None
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)
