"""M08 SKU signal profile assembly service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M08_FEATURE_VERSION,
    CORE3_M08_FORBIDDEN_OUTPUT_FIELDS,
    CORE3_M08_RULE_VERSION,
    CORE3_M08_VIEW_SCHEMA_VERSION,
    M08CoverageStatus,
    M08ForModule,
    M08ProfileScope,
    M08ProfileStatus,
    M08SignalDomain,
    M08ViewRole,
    M08_DOWNSTREAM_MODULES,
    M08_REQUIRED_MATRIX_ROWS,
    Core3ConfidenceLevel,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.sku_signal_profile_repositories import M08SkuSignalRepository
from app.services.core3_real_data.sku_signal_profile_schemas import (
    M08QualityIssue,
    M08SkuDownstreamFeatureViewRecord,
    M08SkuSignalEvidenceMatrixRecord,
    M08SkuSignalProfileRecord,
    m08_confidence_level,
)


D0 = Decimal("0")
D1 = Decimal("1")
FULL_WINDOW = "full_observed_window"


@dataclass(frozen=True)
class M08ServiceResult:
    profiles: list[M08SkuSignalProfileRecord]
    matrices: list[M08SkuSignalEvidenceMatrixRecord]
    views: list[M08SkuDownstreamFeatureViewRecord]
    summary: dict[str, Any]
    warnings: list[str]
    review_issues: list[M08QualityIssue]
    status: Core3RunStatus
    input_count: int
    output_count: int
    created_output_count: int


@dataclass(frozen=True)
class _SkuBuildContext:
    sku_code: str
    clean_sku: entities.Core3CleanSku | None
    param_values: list[entities.Core3ExtractParamValue]
    param_profile: entities.Core3SkuParamProfile | None
    claim_activations: list[entities.Core3SkuClaimActivation]
    claim_validations: list[entities.Core3SkuClaimCommentValidation]
    comment_profile: entities.Core3SkuCommentSignalProfile | None
    comment_signals: list[entities.Core3CommentDownstreamSignal]
    market_profiles: list[entities.Core3SkuMarketProfile]
    market_signals: list[entities.Core3MarketSignal]
    pools: list[entities.Core3ComparablePoolBaseline]
    pool_members: list[entities.Core3MarketPoolMember]
    evidence_atoms: list[entities.Core3EvidenceAtom]


@dataclass(frozen=True)
class _SkuBuildResult:
    profile: M08SkuSignalProfileRecord
    matrices: list[M08SkuSignalEvidenceMatrixRecord]
    views: list[M08SkuDownstreamFeatureViewRecord]
    review_issues: list[M08QualityIssue]
    warnings: list[str]


class SkuSignalProfileService:
    def __init__(self, repository: M08SkuSignalRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M08_RULE_VERSION,
        feature_version: str = CORE3_M08_FEATURE_VERSION,
        view_schema_version: str = CORE3_M08_VIEW_SCHEMA_VERSION,
    ) -> M08ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        sku_scope = tuple(sorted({code for code in sku_scope if code}))
        inputs = _InputIndex(
            clean_skus=self.repository.list_clean_skus(batch_id),
            param_values=self.repository.list_param_values(batch_id),
            param_profiles=self.repository.list_param_profiles(batch_id),
            claim_activations=self.repository.list_claim_activations(batch_id),
            claim_validations=self.repository.list_claim_validations(batch_id),
            comment_profiles=self.repository.list_comment_profiles(batch_id),
            comment_signals=self.repository.list_comment_signals(batch_id),
            market_profiles=self.repository.list_market_profiles(batch_id),
            market_signals=self.repository.list_market_signals(batch_id),
            comparable_pools=self.repository.list_comparable_pools(batch_id),
            pool_members=self.repository.list_pool_members(batch_id),
            evidence_atoms=self.repository.list_evidence_atoms(batch_id),
        )
        sku_codes = _sku_universe(inputs, sku_scope)
        build_results = [
            self._build_sku(
                _SkuBuildContext(
                    sku_code=sku_code,
                    clean_sku=inputs.clean_by_sku.get(sku_code),
                    param_values=inputs.param_values_by_sku.get(sku_code, []),
                    param_profile=inputs.param_profile_by_sku.get(sku_code),
                    claim_activations=inputs.claim_activations_by_sku.get(sku_code, []),
                    claim_validations=inputs.claim_validations_by_sku.get(sku_code, []),
                    comment_profile=inputs.comment_profile_by_sku.get(sku_code),
                    comment_signals=inputs.comment_signals_by_sku.get(sku_code, []),
                    market_profiles=inputs.market_profiles_by_sku.get(sku_code, []),
                    market_signals=inputs.market_signals_by_sku.get(sku_code, []),
                    pools=inputs.pools_by_sku.get(sku_code, []),
                    pool_members=inputs.pool_members_by_sku.get(sku_code, []),
                    evidence_atoms=inputs.evidence_by_sku.get(sku_code, []),
                ),
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                feature_version=feature_version,
                view_schema_version=view_schema_version,
                evidence_confidence_by_id=inputs.evidence_confidence_by_id,
            )
            for sku_code in sku_codes
        ]

        profiles = [item.profile for item in build_results]
        matrices = [matrix for item in build_results for matrix in item.matrices]
        views = [view for item in build_results for view in item.views]
        for payload in [profile.model_dump(mode="python") for profile in profiles]:
            _assert_no_forbidden_fields(payload)
        for payload in [view.feature_payload_json for view in views]:
            _assert_no_forbidden_fields(payload)

        profile_write = self.repository.save_profiles(profiles)
        matrix_write = self.repository.save_matrices(matrices)
        view_write = self.repository.save_views(views)

        warnings = _dedupe([warning for item in build_results for warning in item.warnings])
        review_issues = [issue for item in build_results for issue in item.review_issues]
        status = Core3RunStatus.WARNING if warnings or review_issues else Core3RunStatus.SUCCESS
        output_count = len(profiles) + len(matrices) + len(views)
        created_count = profile_write.created_count + matrix_write.created_count + view_write.created_count
        profile_status_counts = Counter(profile.profile_status for profile in profiles)
        coverage_status_counts = Counter(matrix.coverage_status for matrix in matrices)
        ready_view_count = sum(1 for view in views if view.ready_for_module)
        summary = {
            "batch_id": batch_id,
            "rule_version": rule_version,
            "feature_version": feature_version,
            "view_schema_version": view_schema_version,
            "sku_count": len(sku_codes),
            "sku_signal_profile_count": len(profiles),
            "evidence_matrix_count": len(matrices),
            "downstream_feature_view_count": len(views),
            "ready_view_count": ready_view_count,
            "review_required_count": len(review_issues),
            "profile_status_counts": dict(profile_status_counts),
            "coverage_status_counts": dict(coverage_status_counts),
            "downstream_modules": [module.value for module in M08_DOWNSTREAM_MODULES],
            "required_matrix_row_count_per_sku": len(M08_REQUIRED_MATRIX_ROWS),
            "created_output_count": created_count,
            "updated_output_count": profile_write.updated_count + matrix_write.updated_count + view_write.updated_count,
            "reused_output_count": profile_write.reused_count + matrix_write.reused_count + view_write.reused_count,
            "boundary_note": (
                "M08 只整合 SKU 主数据、参数、卖点、评论、市场和可比池信号，"
                "不生成任务、客群、战场、候选竞品、评分排序或报告结论。"
            ),
            "downstream_support": {
                "M08.4": "消费统一信号画像和可用评论发现原生业务维度",
                "M08.5": "消费原生维度发现结果校准业务维度本体",
                "M09": "消费统一信号画像生成用户任务候选",
                "M10": "消费评论与市场特征生成目标客群候选",
                "M11": "消费参数、卖点、评论、市场特征生成价值战场候选",
                "M12": "消费市场和可比池特征做候选召回输入",
                "M13": "消费统一特征做候选解释和质量复核输入",
                "M14": "消费画像完整度和风险信息做排序前约束",
                "M15": "消费证据矩阵准备业务展示素材",
            },
        }
        return M08ServiceResult(
            profiles=profiles,
            matrices=matrices,
            views=views,
            summary=summary,
            warnings=warnings,
            review_issues=review_issues[:100],
            status=status,
            input_count=inputs.input_count,
            output_count=output_count,
            created_output_count=created_count,
        )

    def _build_sku(
        self,
        context: _SkuBuildContext,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        feature_version: str,
        view_schema_version: str,
        evidence_confidence_by_id: Mapping[str, str],
    ) -> _SkuBuildResult:
        clean_sku = context.clean_sku
        model_name = _first_value(
            clean_sku.model_name if clean_sku else None,
            context.param_profile.model_name if context.param_profile else None,
            *(row.model_name for row in context.claim_activations[:1]),
            *(row.model_name for row in context.comment_signals[:1]),
            *(row.model_name for row in context.market_profiles[:1]),
        )
        brand_name = _first_value(
            clean_sku.brand_name if clean_sku else None,
            *(row.brand_name for row in context.claim_activations[:1]),
            *(row.brand_name for row in context.comment_signals[:1]),
            *(row.brand_name for row in context.market_profiles[:1]),
        )
        sku_master = _sku_master_json(context.sku_code, clean_sku)
        core_params = _core_params_json(context.param_profile, context.param_values)
        param_profile = _param_profile_json(context.param_profile)
        claim_summary = _claim_activation_summary(context.claim_activations)
        claim_breakdown = _claim_evidence_breakdown(context.claim_activations, context.claim_validations)
        comment_summary = _comment_signal_summary(context.comment_profile, context.comment_signals)
        comment_quality = _comment_quality_json(context.comment_profile)
        market_summary = _market_summary(context.market_profiles)
        recent_windows = _market_recent_windows(context.market_profiles)
        market_signal_summary = _market_signal_summary(context.market_signals)
        pool_summary = _pool_summary(context.pools, context.pool_members)
        coverage = _source_coverage(
            clean_sku=clean_sku,
            param_profile=context.param_profile,
            param_values=context.param_values,
            claim_activations=context.claim_activations,
            claim_validations=context.claim_validations,
            comment_profile=context.comment_profile,
            comment_signals=context.comment_signals,
            market_profiles=context.market_profiles,
            pools=context.pools,
        )
        domain_completeness = _domain_completeness(coverage)
        domain_confidence = _domain_confidence(
            param_profile=context.param_profile,
            claim_activations=context.claim_activations,
            comment_profile=context.comment_profile,
            market_profiles=context.market_profiles,
            pools=context.pools,
        )
        completeness_score = _weighted_completeness(domain_completeness)
        confidence = _weighted_confidence(domain_confidence, completeness_score)
        missing_signals = _missing_signals(coverage)
        risk_signals = _risk_signals(
            context=context,
            coverage=coverage,
            completeness_score=completeness_score,
        )
        profile_status = _profile_status(completeness_score, risk_signals, missing_signals)
        review_required = profile_status == M08ProfileStatus.REVIEW_REQUIRED.value or any(
            risk.get("severity") in {"high", "medium"} for risk in risk_signals
        )
        evidence_ids = _dedupe(
            [
                *list(clean_sku.representative_source_row_ids or [] if clean_sku else []),
                *_evidence_ids_from_param_values(context.param_values),
                *list(context.param_profile.evidence_ids or [] if context.param_profile else []),
                *_evidence_ids_from_claims(context.claim_activations),
                *_evidence_ids_from_claim_validations(context.claim_validations),
                *list(context.comment_profile.evidence_ids or [] if context.comment_profile else []),
                *_evidence_ids_from_comment_signals(context.comment_signals),
                *_evidence_ids_from_market_profiles(context.market_profiles),
                *_evidence_ids_from_market_signals(context.market_signals),
                *_evidence_ids_from_pools(context.pools),
            ]
        )
        source_refs = _source_profile_refs(context)
        business_index = _business_signal_index(
            context=context,
            core_params=core_params,
            claim_summary=claim_summary,
            comment_summary=comment_summary,
            market_summary=market_summary,
            market_signal_summary=market_signal_summary,
            pool_summary=pool_summary,
            risk_signals=risk_signals,
        )
        downstream_ready = _downstream_ready(coverage, profile_status, missing_signals)
        input_fingerprint = stable_hash(source_refs, version="m08_sku_input_fingerprint_v1")
        profile_hash = _record_id("m08_profile_hash", context.sku_code, input_fingerprint, feature_version)
        profile_id = _record_id("m08p", batch_id, context.sku_code, feature_version)
        profile_payload = {
            "sku_code": context.sku_code,
            "model_name": model_name,
            "brand_name": brand_name,
            "coverage": coverage,
            "core_params": core_params,
            "claim_summary": claim_summary,
            "comment_summary": comment_summary,
            "market_summary": market_summary,
            "pool_summary": pool_summary,
            "business_index": business_index,
            "missing_signals": missing_signals,
            "risk_signals": risk_signals,
            "downstream_ready": downstream_ready,
            "input_fingerprint": input_fingerprint,
        }
        result_hash = stable_hash(profile_payload, version="m08_sku_signal_profile_v1")
        profile = M08SkuSignalProfileRecord(
            sku_signal_profile_id=profile_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=context.sku_code,
            model_code=context.sku_code,
            model_name=model_name,
            brand_name=brand_name,
            profile_scope=M08ProfileScope.SKU_DEFAULT,
            analysis_window=FULL_WINDOW,
            source_coverage_json=coverage,
            source_profile_refs_json=source_refs,
            sku_master_json=sku_master,
            core_params_json=core_params,
            param_profile_json=param_profile,
            claim_activation_summary_json=claim_summary,
            claim_evidence_breakdown_json=claim_breakdown,
            comment_signal_summary_json=comment_summary,
            comment_quality_json=comment_quality,
            market_summary_json=market_summary,
            market_recent_windows_json=recent_windows,
            market_signal_summary_json=market_signal_summary,
            comparable_pool_summary_json=pool_summary,
            business_signal_index_json=business_index,
            missing_signals_json=missing_signals,
            risk_signals_json=risk_signals,
            domain_completeness_json=domain_completeness,
            data_completeness_score=completeness_score,
            domain_confidence_json=domain_confidence,
            confidence=confidence,
            confidence_level=m08_confidence_level(confidence),
            profile_status=profile_status,
            downstream_ready_json=downstream_ready,
            evidence_summary_json=_evidence_summary(context.evidence_atoms, evidence_ids),
            representative_evidence_ids=evidence_ids[:100],
            input_fingerprint=input_fingerprint,
            profile_hash=profile_hash,
            result_hash=result_hash,
            rule_version=rule_version,
            feature_version=feature_version,
            review_required=review_required,
            review_status="pending_review" if review_required else "auto_pass",
            review_reason_json={"risk_signals": risk_signals[:10], "missing_signals": missing_signals[:10]},
        )
        matrices = _matrix_records(
            profile,
            context=context,
            coverage=coverage,
            domain_confidence=domain_confidence,
            evidence_confidence_by_id=evidence_confidence_by_id,
            rule_version=rule_version,
            feature_version=feature_version,
        )
        views = _downstream_views(
            profile,
            matrices=matrices,
            view_schema_version=view_schema_version,
            rule_version=rule_version,
            feature_version=feature_version,
        )
        issues = [
            M08QualityIssue(
                issue_code=str(risk["risk_code"]),
                sku_code=context.sku_code,
                severity=str(risk.get("severity") or "medium"),
                message_cn=str(risk.get("message_cn") or "SKU 信号画像存在质量风险。"),
                suggestion_cn=str(risk.get("suggestion_cn") or "补充上游数据后重跑 M08。"),
                evidence_ids=evidence_ids[:20],
            )
            for risk in risk_signals
            if risk.get("severity") in {"high", "medium"}
        ]
        warnings = [
            f"{context.sku_code} SKU 信号画像完整度较低：{completeness_score}"
            for _ in [0]
            if profile_status in {M08ProfileStatus.INSUFFICIENT.value, M08ProfileStatus.REVIEW_REQUIRED.value}
        ]
        return _SkuBuildResult(profile=profile, matrices=matrices, views=views, review_issues=issues, warnings=warnings)


class _InputIndex:
    def __init__(
        self,
        *,
        clean_skus: list[entities.Core3CleanSku],
        param_values: list[entities.Core3ExtractParamValue],
        param_profiles: list[entities.Core3SkuParamProfile],
        claim_activations: list[entities.Core3SkuClaimActivation],
        claim_validations: list[entities.Core3SkuClaimCommentValidation],
        comment_profiles: list[entities.Core3SkuCommentSignalProfile],
        comment_signals: list[entities.Core3CommentDownstreamSignal],
        market_profiles: list[entities.Core3SkuMarketProfile],
        market_signals: list[entities.Core3MarketSignal],
        comparable_pools: list[entities.Core3ComparablePoolBaseline],
        pool_members: list[entities.Core3MarketPoolMember],
        evidence_atoms: list[entities.Core3EvidenceAtom],
    ) -> None:
        self.clean_skus = clean_skus
        self.param_values = param_values
        self.param_profiles = param_profiles
        self.claim_activations = claim_activations
        self.claim_validations = claim_validations
        self.comment_profiles = comment_profiles
        self.comment_signals = comment_signals
        self.market_profiles = market_profiles
        self.market_signals = market_signals
        self.comparable_pools = comparable_pools
        self.pool_members = pool_members
        self.evidence_atoms = evidence_atoms
        self.clean_by_sku = {row.sku_code: row for row in clean_skus}
        self.param_values_by_sku = _group_by_sku(param_values)
        self.param_profile_by_sku = {row.sku_code: row for row in param_profiles}
        self.claim_activations_by_sku = _group_by_sku(claim_activations)
        self.claim_validations_by_sku = _group_by_sku(claim_validations)
        self.comment_profile_by_sku = {row.sku_code: row for row in comment_profiles}
        self.comment_signals_by_sku = _group_by_sku(comment_signals)
        self.market_profiles_by_sku = _group_by_sku(market_profiles)
        self.market_signals_by_sku = _group_by_sku(market_signals)
        self.pools_by_sku = _group_by_attr(comparable_pools, "target_sku_code")
        self.pool_members_by_sku = _group_by_attr(pool_members, "target_sku_code")
        self.evidence_by_sku = _group_by_sku([row for row in evidence_atoms if row.sku_code])
        self.evidence_confidence_by_id = {row.evidence_id: row.confidence_level for row in evidence_atoms}
        self.input_count = (
            len(clean_skus)
            + len(param_values)
            + len(param_profiles)
            + len(claim_activations)
            + len(claim_validations)
            + len(comment_profiles)
            + len(comment_signals)
            + len(market_profiles)
            + len(market_signals)
            + len(comparable_pools)
            + len(pool_members)
        )


def _sku_universe(inputs: _InputIndex, sku_scope: Sequence[str]) -> list[str]:
    if sku_scope:
        return sorted(set(sku_scope))
    return sorted(
        set(inputs.clean_by_sku)
        | set(inputs.param_profile_by_sku)
        | set(inputs.param_values_by_sku)
        | set(inputs.claim_activations_by_sku)
        | set(inputs.comment_profile_by_sku)
        | set(inputs.market_profiles_by_sku)
        | set(inputs.pools_by_sku)
    )


def _sku_master_json(sku_code: str, row: entities.Core3CleanSku | None) -> dict[str, Any]:
    if row is None:
        return {"sku_code": sku_code, "identity_status": "missing_clean_sku"}
    return {
        "sku_code": sku_code,
        "model_name": row.model_name,
        "brand_name": row.brand_name,
        "category_name": row.category_name,
        "source_tables": list(row.source_tables or []),
        "coverage": dict(row.coverage_json or {}),
        "field_conflicts": dict(row.field_conflicts_json or {}),
        "quality_status": row.quality_status,
        "quality_flags": list(row.quality_flags or []),
        "clean_sku_id": row.clean_sku_id,
        "clean_hash": row.clean_hash,
    }


def _core_params_json(
    profile: entities.Core3SkuParamProfile | None,
    param_values: list[entities.Core3ExtractParamValue],
) -> dict[str, Any]:
    values: dict[str, dict[str, Any]] = {}
    for row in sorted(param_values, key=lambda item: (item.param_code, item.source_priority_rank)):
        if row.param_code in values and float(values[row.param_code].get("confidence") or 0) >= float(row.confidence or 0):
            continue
        values[row.param_code] = {
            "param_name": row.param_name,
            "param_group": row.param_group,
            "value": row.normalized_value if row.normalized_value is not None else row.value_text,
            "numeric_value": row.numeric_value,
            "unit": row.unit,
            "value_presence": row.value_presence,
            "source_type": row.source_type,
            "confidence": row.confidence,
            "evidence_ids": list(row.evidence_ids or []),
            "quality_flags": list(row.quality_flags or []),
        }
    return {
        "param_values": values,
        "core_picture_params": dict(profile.core_picture_params_json or {}) if profile else {},
        "core_gaming_params": dict(profile.core_gaming_params_json or {}) if profile else {},
        "core_system_params": dict(profile.core_system_params_json or {}) if profile else {},
        "core_eye_care_params": dict(profile.core_eye_care_params_json or {}) if profile else {},
    }


def _param_profile_json(profile: entities.Core3SkuParamProfile | None) -> dict[str, Any]:
    if profile is None:
        return {"profile_status": "missing"}
    return {
        "sku_param_profile_id": profile.sku_param_profile_id,
        "param_completeness": profile.param_completeness,
        "known_param_count": profile.known_param_count,
        "unknown_param_count": profile.unknown_param_count,
        "conflict_count": profile.conflict_count,
        "review_required_count": profile.review_required_count,
        "quality_summary": dict(profile.quality_summary_json or {}),
        "profile_hash": profile.profile_hash,
        "evidence_ids": list(profile.evidence_ids or []),
    }


def _claim_activation_summary(rows: list[entities.Core3SkuClaimActivation]) -> dict[str, Any]:
    activation_counts = Counter(row.activation_level for row in rows)
    basis_counts = Counter(row.activation_basis for row in rows)
    type_counts = Counter(row.m04b_claim_type for row in rows)
    sorted_rows = sorted(rows, key=lambda row: (row.final_activation_score or D0, row.confidence or D0), reverse=True)
    return {
        "claim_count": len(rows),
        "activation_level_counts": dict(activation_counts),
        "activation_basis_counts": dict(basis_counts),
        "claim_type_counts": dict(type_counts),
        "missing_structured_claim_count": sum(1 for row in rows if row.missing_structured_claim_flag),
        "comment_only_count": sum(1 for row in rows if row.comment_only_flag),
        "param_only_count": sum(1 for row in rows if row.param_only_flag),
        "top_claims": [
            {
                "claim_code_hint": row.claim_code,
                "claim_name": row.claim_name,
                "claim_group": row.claim_group,
                "activation_level": row.activation_level,
                "activation_basis": row.activation_basis,
                "final_activation_score": row.final_activation_score,
                "perception_status": row.perception_status,
                "confidence": row.confidence,
            }
            for row in sorted_rows[:12]
        ],
    }


def _claim_evidence_breakdown(
    activations: list[entities.Core3SkuClaimActivation],
    validations: list[entities.Core3SkuClaimCommentValidation],
) -> dict[str, Any]:
    return {
        "activation_count": len(activations),
        "validation_count": len(validations),
        "param_evidence_count": len(_dedupe([item for row in activations for item in list(row.param_evidence_ids or [])])),
        "promo_evidence_count": len(_dedupe([item for row in activations for item in list(row.promo_evidence_ids or [])])),
        "comment_evidence_count": len(_dedupe([item for row in activations for item in list(row.comment_evidence_ids or [])])),
        "comment_signal_count": len(_dedupe([item for row in activations for item in list(row.comment_signal_ids or [])])),
        "claim_validation_effect_counts": dict(Counter(row.comment_effect for row in validations)),
        "perception_status_counts": dict(Counter(row.perception_status for row in validations)),
        "conflict_flags": _dedupe([item for row in activations for item in list(row.conflict_flags or [])]),
    }


def _comment_signal_summary(
    profile: entities.Core3SkuCommentSignalProfile | None,
    signals: list[entities.Core3CommentDownstreamSignal],
) -> dict[str, Any]:
    signals_by_type = _group_by_attr(signals, "signal_type")
    type_payload = {}
    for signal_type, rows in sorted(signals_by_type.items()):
        type_payload[signal_type] = {
            "signal_count": len(rows),
            "strong_count": sum(1 for row in rows if row.signal_level == "strong"),
            "medium_count": sum(1 for row in rows if row.signal_level == "medium"),
            "polarity_counts": dict(Counter(row.polarity for row in rows)),
            "target_code_hints": [row.target_code_hint for row in rows[:12]],
            "top_phrases": _dedupe([phrase for row in rows for phrase in list(row.representative_phrases or [])])[:12],
        }
    return {
        "profile_id": profile.sku_comment_signal_profile_id if profile else None,
        "comment_signal_confidence": profile.comment_signal_confidence if profile else D0,
        "confidence_level": profile.confidence_level if profile else Core3ConfidenceLevel.UNKNOWN.value,
        "ready_flags": {
            "claim_validation_ready": bool(profile.claim_validation_ready) if profile else False,
            "task_cue_ready": bool(profile.task_cue_ready) if profile else False,
            "target_group_cue_ready": bool(profile.target_group_cue_ready) if profile else False,
            "battlefield_support_ready": bool(profile.battlefield_support_ready) if profile else False,
        },
        "signal_level_counts": {
            "strong": profile.strong_signal_count if profile else 0,
            "medium": profile.medium_signal_count if profile else 0,
            "weak": profile.weak_signal_count if profile else 0,
            "blocked": profile.blocked_signal_count if profile else 0,
        },
        "signal_type_summary": type_payload,
        "signal_count": len(signals),
        "profile_hash": profile.result_hash if profile else None,
    }


def _comment_quality_json(profile: entities.Core3SkuCommentSignalProfile | None) -> dict[str, Any]:
    if profile is None:
        return {"quality_status": "missing_comment_signal_profile"}
    return {
        "quality_flags": list(profile.quality_flags or []),
        "review_issue_summary": dict(profile.review_issue_summary_json or {}),
        "review_required": profile.review_required,
        "review_status": profile.review_status,
        "evidence_ids": list(profile.evidence_ids or []),
    }


def _market_summary(rows: list[entities.Core3SkuMarketProfile]) -> dict[str, Any]:
    full = _full_market_profile(rows)
    if full is None:
        return {"market_status": "missing_full_observed_window"}
    return {
        "sku_market_profile_id": full.sku_market_profile_id,
        "analysis_window": full.analysis_window,
        "period_start_raw": full.period_start_raw,
        "period_end_raw": full.period_end_raw,
        "active_week_count": full.active_week_count,
        "market_row_count": full.market_row_count,
        "screen_size_inch": full.screen_size_inch,
        "size_segment": full.size_segment,
        "screen_size_class": getattr(full, "screen_size_class", "unknown"),
        "market_pool_key": getattr(full, "market_pool_key", None),
        "sales_volume_total": full.sales_volume_total,
        "sales_amount_total": full.sales_amount_total,
        "price_wavg": full.price_wavg,
        "price_per_inch": full.price_per_inch,
        "price_per_inch_percentile": getattr(full, "price_per_inch_percentile", None),
        "price_latest": full.price_latest,
        "price_median": full.price_median,
        "main_channel_type": full.main_channel_type,
        "main_platform": full.main_platform,
        "price_band_category": full.price_band_category,
        "price_band_size": full.price_band_size,
        "same_pool_price_percentile": getattr(full, "same_pool_price_percentile", None),
        "same_pool_volume_percentile": getattr(full, "same_pool_volume_percentile", None),
        "same_pool_amount_percentile": getattr(full, "same_pool_amount_percentile", None),
        "same_pool_sku_count": getattr(full, "same_pool_sku_count", 0),
        "market_confidence": full.market_confidence,
        "sample_status": full.sample_status,
        "quality_flags": list(full.quality_flags or []),
        "evidence_ids": list(full.evidence_ids or []),
        "result_hash": full.result_hash,
    }


def _market_recent_windows(rows: list[entities.Core3SkuMarketProfile]) -> dict[str, Any]:
    windows = []
    for row in rows:
        if row.analysis_window == FULL_WINDOW:
            continue
        windows.append(
            {
                "analysis_window": row.analysis_window,
                "active_week_count": row.active_week_count,
                "sales_volume_total": row.sales_volume_total,
                "sales_amount_total": row.sales_amount_total,
                "price_wavg": row.price_wavg,
                "price_latest": row.price_latest,
                "sample_status": row.sample_status,
                "market_confidence": row.market_confidence,
                "quality_flags": list(row.quality_flags or []),
            }
        )
    return {"windows": windows, "window_count": len(windows)}


def _market_signal_summary(rows: list[entities.Core3MarketSignal]) -> dict[str, Any]:
    full_rows = [row for row in rows if row.analysis_window == FULL_WINDOW]
    source_rows = full_rows or rows
    return {
        "market_signal_count": len(source_rows),
        "signal_code_counts": dict(Counter(row.signal_code for row in source_rows)),
        "signal_level_counts": dict(Counter(row.signal_level for row in source_rows)),
        "top_signals": [
            {
                "signal_code_hint": row.signal_code,
                "signal_name": row.signal_name,
                "signal_strength": row.signal_strength,
                "signal_level": row.signal_level,
                "basis_metric": row.basis_metric,
                "polarity": row.polarity,
                "confidence": row.confidence,
            }
            for row in sorted(source_rows, key=lambda item: item.signal_strength or D0, reverse=True)[:12]
        ],
    }


def _pool_summary(
    pools: list[entities.Core3ComparablePoolBaseline],
    members: list[entities.Core3MarketPoolMember],
) -> dict[str, Any]:
    full_pools = [row for row in pools if row.analysis_window == FULL_WINDOW]
    source_pools = full_pools or pools
    members_by_pool = _group_by_attr(members, "pool_id")
    pool_items = []
    for pool in source_pools:
        pool_items.append(
            {
                "pool_id": pool.pool_id,
                "pool_type": pool.pool_type,
                "pool_sku_codes": list(pool.candidate_sku_codes or []),
                "pool_sku_count": pool.pool_sku_count,
                "valid_member_count": pool.valid_member_count,
                "target_included": pool.target_included,
                "target_size_segment": pool.target_size_segment,
                "target_price_band": pool.target_price_band,
                "median_price": pool.median_price,
                "median_volume": pool.median_volume,
                "median_amount": pool.median_amount,
                "pool_confidence": pool.pool_confidence,
                "sample_status": pool.sample_status,
                "quality_flags": list(pool.quality_flags or []),
                "member_count": len(members_by_pool.get(pool.pool_id, [])),
            }
        )
    return {
        "pool_count": len(source_pools),
        "pool_type_counts": dict(Counter(pool.pool_type for pool in source_pools)),
        "pool_items": pool_items,
    }


def _source_coverage(
    *,
    clean_sku: entities.Core3CleanSku | None,
    param_profile: entities.Core3SkuParamProfile | None,
    param_values: list[entities.Core3ExtractParamValue],
    claim_activations: list[entities.Core3SkuClaimActivation],
    claim_validations: list[entities.Core3SkuClaimCommentValidation],
    comment_profile: entities.Core3SkuCommentSignalProfile | None,
    comment_signals: list[entities.Core3CommentDownstreamSignal],
    market_profiles: list[entities.Core3SkuMarketProfile],
    pools: list[entities.Core3ComparablePoolBaseline],
) -> dict[str, Any]:
    full_market = _full_market_profile(market_profiles)
    return {
        "sku_master": _coverage(clean_sku is not None, False),
        "param": _coverage(param_profile is not None and param_profile.known_param_count > 0, bool(param_values)),
        "claim": _coverage(bool(claim_activations), bool(claim_validations)),
        "claim_comment_validation": _coverage(bool(claim_validations), bool(claim_activations)),
        "comment": _coverage(comment_profile is not None and bool(comment_signals), comment_profile is not None),
        "market": _coverage(full_market is not None, bool(market_profiles)),
        "pool": _coverage(bool([pool for pool in pools if pool.analysis_window == FULL_WINDOW]), bool(pools)),
        "quality": _coverage(True, False),
    }


def _coverage(covered: bool, partial: bool) -> dict[str, str]:
    if covered:
        return {"status": M08CoverageStatus.COVERED.value}
    if partial:
        return {"status": M08CoverageStatus.PARTIALLY_COVERED.value}
    return {"status": M08CoverageStatus.MISSING.value}


def _domain_completeness(coverage: Mapping[str, Any]) -> dict[str, Any]:
    return {
        domain: {
            "score": _coverage_score(str(item.get("status"))),
            "status": item.get("status"),
        }
        for domain, item in coverage.items()
    }


def _domain_confidence(
    *,
    param_profile: entities.Core3SkuParamProfile | None,
    claim_activations: list[entities.Core3SkuClaimActivation],
    comment_profile: entities.Core3SkuCommentSignalProfile | None,
    market_profiles: list[entities.Core3SkuMarketProfile],
    pools: list[entities.Core3ComparablePoolBaseline],
) -> dict[str, Any]:
    full_market = _full_market_profile(market_profiles)
    return {
        "sku_master": {"score": Decimal("0.9000")},
        "param": {"score": _clamp(param_profile.param_completeness if param_profile else D0)},
        "claim": {"score": _average([row.confidence for row in claim_activations])},
        "claim_comment_validation": {"score": _average([row.confidence for row in claim_activations])},
        "comment": {"score": _clamp(comment_profile.comment_signal_confidence if comment_profile else D0)},
        "market": {"score": _clamp(full_market.market_confidence if full_market else D0)},
        "pool": {"score": _average([row.pool_confidence for row in pools if row.analysis_window == FULL_WINDOW] or [row.pool_confidence for row in pools])},
        "quality": {"score": Decimal("0.8000")},
    }


def _weighted_completeness(domain_completeness: Mapping[str, Any]) -> Decimal:
    weights = {
        "sku_master": Decimal("0.10"),
        "param": Decimal("0.18"),
        "claim": Decimal("0.14"),
        "claim_comment_validation": Decimal("0.08"),
        "comment": Decimal("0.18"),
        "market": Decimal("0.20"),
        "pool": Decimal("0.10"),
        "quality": Decimal("0.02"),
    }
    value = sum(weights[domain] * _decimal(item.get("score")) for domain, item in domain_completeness.items())
    return _round4(value)


def _weighted_confidence(domain_confidence: Mapping[str, Any], completeness_score: Decimal) -> Decimal:
    scores = [_decimal(item.get("score")) for item in domain_confidence.values() if _decimal(item.get("score")) > D0]
    if not scores:
        return D0
    return _round4((sum(scores) / Decimal(len(scores))) * Decimal("0.65") + completeness_score * Decimal("0.35"))


def _missing_signals(coverage: Mapping[str, Any]) -> list[dict[str, str]]:
    messages = {
        "sku_master": "缺少 SKU 主数据，无法稳定识别商品。",
        "param": "缺少参数画像，后续任务/战场推导缺少硬规格依据。",
        "claim": "缺少卖点激活结果，后续价值层判断缺少结构化卖点依据。",
        "claim_comment_validation": "缺少卖点评论验证，无法判断用户感知是否支撑卖点。",
        "comment": "缺少评论信号画像，用户任务、客群和战场体验证据不足。",
        "market": "缺少市场画像，价格、销量、渠道和可比池分析不足。",
        "pool": "缺少可比池基线，后续候选召回缺少市场对照范围。",
    }
    return [
        {"domain": domain, "reason_code": f"missing_{domain}", "message_cn": messages[domain]}
        for domain, item in coverage.items()
        if item.get("status") == M08CoverageStatus.MISSING.value and domain in messages
    ]


def _risk_signals(
    *,
    context: _SkuBuildContext,
    coverage: Mapping[str, Any],
    completeness_score: Decimal,
) -> list[dict[str, str]]:
    risks: list[dict[str, str]] = []
    if completeness_score < Decimal("0.5500"):
        risks.append(
            {
                "risk_code": "m08_profile_completeness_low",
                "severity": "high",
                "message_cn": "SKU 综合信号画像完整度不足，不能直接进入后续业务结论。",
                "suggestion_cn": "补充参数、评论、市场或可比池数据后重跑。",
            }
        )
    if context.param_profile and context.param_profile.conflict_count > 0:
        risks.append(
            {
                "risk_code": "m08_param_conflict",
                "severity": "medium",
                "message_cn": "参数画像存在冲突，需要复核关键硬规格。",
                "suggestion_cn": "检查 M03 参数冲突和原始属性记录。",
            }
        )
    if context.comment_profile and context.comment_profile.blocked_signal_count > context.comment_profile.strong_signal_count:
        risks.append(
            {
                "risk_code": "m08_comment_signal_weak",
                "severity": "medium",
                "message_cn": "评论信号偏弱或阻断较多，下游任务/客群/战场推导需谨慎。",
                "suggestion_cn": "补充更高质量评论或复核 M06 主题命中。",
            }
        )
    full_market = _full_market_profile(context.market_profiles)
    if full_market and full_market.sample_status in {"limited", "insufficient"}:
        risks.append(
            {
                "risk_code": "m08_market_sample_limited",
                "severity": "medium",
                "message_cn": "市场观察样本有限，价格和销量信号需带样本限制说明。",
                "suggestion_cn": "补充更多周销周期后重跑 M07/M08。",
            }
        )
    if coverage.get("pool", {}).get("status") != M08CoverageStatus.COVERED.value:
        risks.append(
            {
                "risk_code": "m08_comparable_pool_insufficient",
                "severity": "medium",
                "message_cn": "可比池不完整，后续候选召回的市场对照范围有限。",
                "suggestion_cn": "补充同尺寸、同价位或平台重合 SKU 市场数据。",
            }
        )
    return risks


def _profile_status(
    completeness_score: Decimal,
    risks: list[Mapping[str, Any]],
    missing_signals: list[Mapping[str, Any]],
) -> str:
    if completeness_score < Decimal("0.3500"):
        return M08ProfileStatus.INSUFFICIENT.value
    if any(risk.get("severity") == "high" for risk in risks):
        return M08ProfileStatus.REVIEW_REQUIRED.value
    if completeness_score >= Decimal("0.7800") and not missing_signals:
        return M08ProfileStatus.READY.value
    if completeness_score >= Decimal("0.5500"):
        return M08ProfileStatus.LIMITED.value
    return M08ProfileStatus.REVIEW_REQUIRED.value


def _business_signal_index(
    *,
    context: _SkuBuildContext,
    core_params: Mapping[str, Any],
    claim_summary: Mapping[str, Any],
    comment_summary: Mapping[str, Any],
    market_summary: Mapping[str, Any],
    market_signal_summary: Mapping[str, Any],
    pool_summary: Mapping[str, Any],
    risk_signals: list[Mapping[str, Any]],
) -> dict[str, Any]:
    comment_type_summary = dict(comment_summary.get("signal_type_summary") or {})
    product_anchor_index = _product_anchor_index(
        core_params=core_params,
        claim_summary=claim_summary,
        market_summary=market_summary,
    )
    return {
        "param_signal_codes": sorted(core_params.get("param_values", {}).keys()),
        "claim_code_hints": [item.get("claim_code_hint") for item in claim_summary.get("top_claims", []) if item.get("claim_code_hint")],
        "comment_signal_types": sorted(comment_type_summary.keys()),
        "comment_task_hint_codes": _target_hints(context.comment_signals, "task_cue"),
        "comment_target_group_hint_codes": _target_hints(context.comment_signals, "target_group_cue"),
        "comment_battlefield_hint_codes": _target_hints(context.comment_signals, "battlefield_support"),
        "market_signal_codes": sorted(market_signal_summary.get("signal_code_counts", {}).keys()),
        "market_pool_key": market_summary.get("market_pool_key"),
        "screen_size_class": market_summary.get("screen_size_class"),
        "same_pool_position": {
            "price_percentile": market_summary.get("same_pool_price_percentile"),
            "volume_percentile": market_summary.get("same_pool_volume_percentile"),
            "amount_percentile": market_summary.get("same_pool_amount_percentile"),
            "price_per_inch_percentile": market_summary.get("price_per_inch_percentile"),
            "sample_count": market_summary.get("same_pool_sku_count"),
        },
        "product_anchor_index": product_anchor_index,
        "pool_types": sorted(pool_summary.get("pool_type_counts", {}).keys()),
        "risk_codes": [risk.get("risk_code") for risk in risk_signals],
    }


def _product_anchor_index(
    *,
    core_params: Mapping[str, Any],
    claim_summary: Mapping[str, Any],
    market_summary: Mapping[str, Any],
) -> dict[str, Any]:
    param_values = dict(core_params.get("param_values") or {})
    claims = list(claim_summary.get("top_claims") or [])
    groups = {
        "display_picture": _anchor_group(
            name_cn="显示画质锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(
                ("screen_size_inch", None, "screen_size"),
                ("peak_brightness_nits", Decimal("500"), "brightness"),
                ("backlight_type", None, "backlight"),
                ("panel_type", None, "panel"),
                ("local_dimming_zones", Decimal("1"), "dimming"),
                ("dimming_zone_count", Decimal("1"), "dimming"),
                ("color_gamut_percent", Decimal("90"), "color"),
                ("hdr_support_flag", None, "hdr"),
            ),
            claim_keywords=("PICTURE", "DISPLAY", "MINI", "HDR", "QLED", "OLED", "BRIGHTNESS", "DIMMING", "COLOR"),
        ),
        "motion_gaming": _anchor_group(
            name_cn="高刷游戏运动锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(
                ("native_refresh_rate_hz", Decimal("120"), "refresh"),
                ("refresh_rate_hz", Decimal("120"), "refresh"),
                ("system_refresh_rate_hz", Decimal("120"), "refresh_proxy"),
                ("hdmi_2_1_ports", None, "hdmi"),
                ("hdmi_2_1_port_count", Decimal("1"), "hdmi"),
                ("vrr_support_flag", None, "vrr"),
                ("allm_support_flag", None, "allm"),
                ("motion_compensation_flag", None, "motion"),
                ("memc_support_flag", None, "motion"),
            ),
            claim_keywords=("REFRESH", "GAMING", "HDMI", "LOW_LATENCY", "SPORTS", "MOTION"),
        ),
        "audio_immersion": _anchor_group(
            name_cn="声场沉浸锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(
                ("speaker_power_w", Decimal("10"), "speaker_power"),
                ("speaker_power_total_w", Decimal("10"), "speaker_power"),
                ("speaker_channel", None, "speaker_channel"),
                ("speaker_channel_count", Decimal("2"), "speaker_channel"),
                ("audio_system", None, "audio_system"),
                ("sound_system", None, "audio_system"),
                ("dolby_audio_flag", None, "dolby"),
                ("dolby_atmos_flag", None, "dolby"),
                ("dts_support_flag", None, "dts"),
            ),
            claim_keywords=("AUDIO", "SOUND", "DOLBY", "DTS", "IMMERSIVE"),
        ),
        "eye_care": _anchor_group(
            name_cn="护眼舒适锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(
                ("eye_care_flag", None, "eye_care"),
                ("eye_protection_flag", None, "eye_care"),
                ("eye_protection_mode_flag", None, "eye_care"),
                ("low_blue_light_flag", None, "low_blue_light"),
                ("flicker_free_flag", None, "flicker_free"),
                ("tuv_certification", None, "certification"),
                ("child_mode_flag", None, "child_mode"),
            ),
            claim_keywords=("EYE", "BLUE", "FLICKER", "CHILD", "COMFORT"),
        ),
        "smart_easy_use": _anchor_group(
            name_cn="智能易用锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(
                ("voice_control_flag", None, "voice"),
                ("far_field_voice_flag", None, "voice"),
                ("ram_gb", Decimal("2"), "memory"),
                ("memory_gb", Decimal("2"), "memory"),
                ("storage_gb", Decimal("16"), "storage"),
                ("chipset_name", None, "chip"),
                ("cpu_name", None, "chip"),
            ),
            claim_keywords=("SMART", "VOICE", "ELDER", "NO_AD", "SYSTEM"),
        ),
        "screen_value_market": _anchor_group(
            name_cn="尺寸价格市场锚点",
            param_values=param_values,
            claims=claims,
            market_summary=market_summary,
            param_rules=(("screen_size_inch", Decimal("50"), "screen_size"),),
            claim_keywords=("VALUE", "PRICE", "COST", "PROMOTION", "LARGE_SCREEN"),
            include_market_value=True,
        ),
    }
    valid_groups = {
        code: payload
        for code, payload in groups.items()
        if payload["overall_score"] > 0 or payload["param_hits"] or payload["claim_hits"] or payload["market_hits"]
    }
    return {
        "anchor_schema_version": "m08_product_anchor_index_v1",
        "anchor_groups": valid_groups,
        "anchor_group_count": len(valid_groups),
        "strong_anchor_groups": [
            code
            for code, payload in valid_groups.items()
            if payload["overall_score"] >= Decimal("0.3000") and payload["source_status"] not in {"claim_only", "market_only"}
        ],
        "market_pool_key": market_summary.get("market_pool_key"),
        "screen_size_class": market_summary.get("screen_size_class"),
    }


def _anchor_group(
    *,
    name_cn: str,
    param_values: Mapping[str, Any],
    claims: Sequence[Mapping[str, Any]],
    market_summary: Mapping[str, Any],
    param_rules: Sequence[tuple[str, Decimal | None, str]],
    claim_keywords: Sequence[str],
    include_market_value: bool = False,
) -> dict[str, Any]:
    param_hits = _param_anchor_hits(param_values, param_rules)
    claim_hits = _claim_anchor_hits(claims, claim_keywords)
    market_hits = _market_value_hits(market_summary) if include_market_value else []
    param_score = min(Decimal("0.6000"), Decimal("0.2000") * Decimal(len(param_hits)))
    claim_score = min(Decimal("0.3000"), Decimal("0.1200") * Decimal(len(claim_hits)))
    market_score = min(Decimal("0.2000"), Decimal("0.1000") * Decimal(len(market_hits)))
    overall_score = _round4(min(Decimal("1.0000"), param_score + claim_score + market_score))
    return {
        "name_cn": name_cn,
        "overall_score": overall_score,
        "param_anchor_score": _round4(param_score),
        "claim_anchor_score": _round4(claim_score),
        "market_anchor_score": _round4(market_score),
        "source_status": _anchor_source_status_from_counts(len(param_hits), len(claim_hits), len(market_hits)),
        "param_hits": param_hits,
        "claim_hits": claim_hits,
        "market_hits": market_hits,
    }


def _param_anchor_hits(
    param_values: Mapping[str, Any],
    param_rules: Sequence[tuple[str, Decimal | None, str]],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for param_code, min_numeric, anchor_role in param_rules:
        raw = param_values.get(param_code)
        if not isinstance(raw, Mapping) or not _param_value_present(raw):
            continue
        numeric_value = _decimal_optional(raw.get("numeric_value"))
        if min_numeric is not None and (numeric_value is None or numeric_value < min_numeric):
            continue
        quality_flags = [str(item) for item in list(raw.get("quality_flags") or [])]
        if any("cannot_support" in flag or "scope_blocked" in flag for flag in quality_flags):
            continue
        hits.append(
            {
                "param_code": param_code,
                "anchor_role": anchor_role,
                "value": raw.get("value"),
                "numeric_value": numeric_value,
                "unit": raw.get("unit"),
                "confidence": raw.get("confidence"),
                "evidence_ids": list(raw.get("evidence_ids") or [])[:10],
                "quality_flags": quality_flags,
            }
        )
    return hits


def _claim_anchor_hits(claims: Sequence[Mapping[str, Any]], claim_keywords: Sequence[str]) -> list[dict[str, Any]]:
    normalized_keywords = tuple(keyword.upper() for keyword in claim_keywords)
    hits: list[dict[str, Any]] = []
    for claim in claims:
        claim_code = str(claim.get("claim_code_hint") or "").upper()
        claim_name = str(claim.get("claim_name") or "").upper()
        if not any(keyword in claim_code or keyword in claim_name for keyword in normalized_keywords):
            continue
        hits.append(
            {
                "claim_code": claim.get("claim_code_hint"),
                "claim_name": claim.get("claim_name"),
                "claim_group": claim.get("claim_group"),
                "activation_level": claim.get("activation_level"),
                "activation_basis": claim.get("activation_basis"),
                "score": claim.get("final_activation_score"),
                "confidence": claim.get("confidence"),
            }
        )
    return hits


def _market_value_hits(market_summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    price_percentile = _decimal_optional(market_summary.get("same_pool_price_percentile"))
    price_per_inch_percentile = _decimal_optional(market_summary.get("price_per_inch_percentile"))
    volume_percentile = _decimal_optional(market_summary.get("same_pool_volume_percentile"))
    amount_percentile = _decimal_optional(market_summary.get("same_pool_amount_percentile"))
    if price_percentile is not None and price_percentile <= Decimal("0.4000"):
        hits.append({"market_signal": "same_pool_price_value", "percentile": price_percentile})
    if price_per_inch_percentile is not None and price_per_inch_percentile <= Decimal("0.4000"):
        hits.append({"market_signal": "same_pool_price_per_inch_value", "percentile": price_per_inch_percentile})
    if volume_percentile is not None and volume_percentile >= Decimal("0.6000"):
        hits.append({"market_signal": "same_pool_volume_validation", "percentile": volume_percentile})
    if amount_percentile is not None and amount_percentile >= Decimal("0.6000"):
        hits.append({"market_signal": "same_pool_amount_validation", "percentile": amount_percentile})
    return hits


def _decimal_optional(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    return _decimal(value)


def _param_value_present(value: Mapping[str, Any]) -> bool:
    presence = str(value.get("value_presence") or "present")
    raw_value = value.get("value")
    return presence not in {"missing", "unknown"} and raw_value not in (None, "", "-", "未知")


def _anchor_source_status_from_counts(param_count: int, claim_count: int, market_count: int) -> str:
    if param_count and claim_count:
        return "claim_plus_param"
    if param_count and market_count:
        return "param_plus_market"
    if param_count:
        return "param_only"
    if claim_count:
        return "claim_only"
    if market_count:
        return "market_only"
    return "no_anchor"


def _downstream_ready(
    coverage: Mapping[str, Any],
    profile_status: str,
    missing_signals: list[Mapping[str, Any]],
) -> dict[str, Any]:
    requirements = {
        M08ForModule.M08_4: ("param", "claim", "comment", "market"),
        M08ForModule.M09: ("param", "claim", "comment", "market"),
        M08ForModule.M10: ("comment", "market"),
        M08ForModule.M11: ("param", "claim", "comment", "market"),
        M08ForModule.M11_5: ("claim", "claim_comment_validation", "comment", "market", "pool"),
        M08ForModule.M08_5: ("param", "claim", "comment", "market"),
        M08ForModule.M12: ("market", "pool"),
        M08ForModule.M13: ("market", "pool", "quality"),
        M08ForModule.M14: ("sku_master", "param", "claim", "comment", "market", "pool"),
        M08ForModule.M15: ("sku_master", "param", "claim", "comment", "market", "pool"),
    }
    result = {}
    blocked_status = profile_status in {M08ProfileStatus.INSUFFICIENT.value, M08ProfileStatus.BLOCKED.value}
    for module, required_domains in requirements.items():
        missing = [
            domain
            for domain in required_domains
            if coverage.get(domain, {}).get("status") == M08CoverageStatus.MISSING.value
        ]
        result[module.value] = {
            "ready": not blocked_status and not missing,
            "required_domains": list(required_domains),
            "missing_domains": missing,
            "missing_signal_count": len(missing_signals),
        }
    return result


def _matrix_records(
    profile: M08SkuSignalProfileRecord,
    *,
    context: _SkuBuildContext,
    coverage: Mapping[str, Any],
    domain_confidence: Mapping[str, Any],
    evidence_confidence_by_id: Mapping[str, str],
    rule_version: str,
    feature_version: str,
) -> list[M08SkuSignalEvidenceMatrixRecord]:
    evidence_by_row = _matrix_evidence(context)
    source_refs_by_row = _matrix_source_refs(context)
    records: list[M08SkuSignalEvidenceMatrixRecord] = []
    for domain, sub_domain in M08_REQUIRED_MATRIX_ROWS:
        key = (domain.value, sub_domain)
        evidence_ids = _dedupe(evidence_by_row.get(key, []))[:100]
        source_refs = source_refs_by_row.get(key, {})
        coverage_status = _row_coverage_status(domain, sub_domain, coverage, evidence_ids, source_refs)
        counts = Counter(evidence_confidence_by_id.get(item, "unknown") for item in evidence_ids)
        missing_flag = coverage_status == M08CoverageStatus.MISSING.value
        domain_score = _decimal(domain_confidence.get(domain.value, {}).get("score"))
        payload = {
            "profile_hash": profile.profile_hash,
            "sku_code": profile.sku_code,
            "domain": domain.value,
            "sub_domain": sub_domain,
            "evidence_ids": evidence_ids,
            "source_refs": source_refs,
            "coverage_status": coverage_status,
        }
        records.append(
            M08SkuSignalEvidenceMatrixRecord(
                sku_signal_evidence_matrix_id=_record_id("m08m", profile.sku_signal_profile_id, domain.value, sub_domain, feature_version),
                sku_signal_profile_id=profile.sku_signal_profile_id,
                project_id=profile.project_id,
                category_code=profile.category_code,
                batch_id=profile.batch_id,
                run_id=profile.run_id,
                module_run_id=profile.module_run_id,
                sku_code=profile.sku_code,
                domain=domain,
                sub_domain=sub_domain,
                feature_code=f"{domain.value}.{sub_domain}",
                evidence_role="representative",
                coverage_status=coverage_status,
                evidence_count=len(evidence_ids),
                high_confidence_count=counts.get(Core3ConfidenceLevel.HIGH.value, 0),
                medium_confidence_count=counts.get(Core3ConfidenceLevel.MEDIUM.value, 0),
                low_confidence_count=counts.get(Core3ConfidenceLevel.LOW.value, 0),
                representative_evidence_ids=evidence_ids,
                evidence_query_json={"upstream_modules": _upstream_modules_for_domain(domain.value), "raw_table_access": False},
                source_record_refs_json=source_refs,
                missing_flag=missing_flag,
                missing_reason_code=f"missing_{domain.value}_{sub_domain}" if missing_flag else None,
                risk_flags_json=[item.get("risk_code") for item in profile.risk_signals_json if item.get("risk_code")],
                domain_confidence=domain_score,
                review_required=missing_flag or profile.review_required,
                review_reason_json={"missing_flag": missing_flag, "coverage_status": coverage_status},
                rule_version=rule_version,
                feature_version=feature_version,
                input_fingerprint=stable_hash(payload, version="m08_matrix_input_v1"),
                result_hash=stable_hash(payload, version="m08_matrix_result_v1"),
            )
        )
    return records


def _downstream_views(
    profile: M08SkuSignalProfileRecord,
    *,
    matrices: list[M08SkuSignalEvidenceMatrixRecord],
    view_schema_version: str,
    rule_version: str,
    feature_version: str,
) -> list[M08SkuDownstreamFeatureViewRecord]:
    matrix_refs = [
        matrix.sku_signal_evidence_matrix_id
        for matrix in matrices
        if not matrix.missing_flag
    ]
    views: list[M08SkuDownstreamFeatureViewRecord] = []
    for module in M08_DOWNSTREAM_MODULES:
        ready = bool(profile.downstream_ready_json.get(module.value, {}).get("ready"))
        required_missing = list(profile.downstream_ready_json.get(module.value, {}).get("missing_domains") or [])
        payload = _view_payload(profile, module)
        _assert_no_forbidden_fields(payload)
        view_hash = stable_hash(payload, version=f"m08_{module.value.lower()}_view_v1")
        views.append(
            M08SkuDownstreamFeatureViewRecord(
                sku_downstream_feature_view_id=_record_id("m08v", profile.sku_signal_profile_id, module.value, view_schema_version),
                sku_signal_profile_id=profile.sku_signal_profile_id,
                project_id=profile.project_id,
                category_code=profile.category_code,
                batch_id=profile.batch_id,
                run_id=profile.run_id,
                module_run_id=profile.module_run_id,
                sku_code=profile.sku_code,
                for_module=module,
                view_role=_view_role(module),
                view_schema_version=view_schema_version,
                required_feature_codes_json=_required_features(module),
                optional_feature_codes_json=_optional_features(module),
                feature_payload_json=payload,
                feature_quality_flags_json=[risk.get("risk_code") for risk in profile.risk_signals_json],
                required_missing_fields_json=required_missing,
                optional_missing_fields_json=[],
                evidence_ids=list(profile.representative_evidence_ids or [])[:100],
                evidence_matrix_refs_json=matrix_refs[:80],
                profile_hash=profile.profile_hash,
                view_hash=view_hash,
                dependency_hash_json={
                    "profile_hash": profile.profile_hash,
                    "matrix_result_hashes": [matrix.result_hash for matrix in matrices],
                },
                ready_for_module=ready,
                block_reason_json=required_missing if not ready else [],
                review_required=profile.review_required or not ready,
                review_reason_json={"profile_status": profile.profile_status, "required_missing": required_missing},
                rule_version=rule_version,
                feature_version=feature_version,
                input_fingerprint=stable_hash(
                    {"profile_hash": profile.profile_hash, "module": module.value, "schema": view_schema_version},
                    version="m08_view_input_v1",
                ),
                result_hash=view_hash,
            )
        )
    return views


def _view_payload(profile: M08SkuSignalProfileRecord, module: M08ForModule) -> dict[str, Any]:
    base = {
        "sku_code": profile.sku_code,
        "model_name": profile.model_name,
        "brand_name": profile.brand_name,
        "profile_status": profile.profile_status,
        "source_coverage": profile.source_coverage_json,
        "evidence_summary": profile.evidence_summary_json,
        "missing_signals": profile.missing_signals_json,
        "risk_signals": profile.risk_signals_json,
        "business_signal_index": profile.business_signal_index_json,
        "market_pool_key": profile.business_signal_index_json.get("market_pool_key"),
        "screen_size_class": profile.business_signal_index_json.get("screen_size_class"),
        "same_pool_position": profile.business_signal_index_json.get("same_pool_position", {}),
        "product_anchor_index": profile.business_signal_index_json.get("product_anchor_index", {}),
    }
    module_payloads = {
        M08ForModule.M08_4: {
            "core_params": profile.core_params_json,
            "claim_activation_summary": profile.claim_activation_summary_json,
            "claim_evidence_breakdown": profile.claim_evidence_breakdown_json,
            "comment_signal_summary": profile.comment_signal_summary_json,
            "comment_quality": profile.comment_quality_json,
            "market_summary": profile.market_summary_json,
            "market_signal_summary": profile.market_signal_summary_json,
            "domain_confidence": profile.domain_confidence_json,
            "product_anchor_index": profile.business_signal_index_json.get("product_anchor_index", {}),
        },
        M08ForModule.M09: {
            "core_params": profile.core_params_json,
            "claim_activation_summary": profile.claim_activation_summary_json,
            "comment_signal_summary": _pick_comment_types(profile.comment_signal_summary_json, ["task_cue", "claim_validation"]),
            "market_summary": profile.market_summary_json,
        },
        M08ForModule.M10: {
            "comment_signal_summary": _pick_comment_types(
                profile.comment_signal_summary_json,
                ["target_group_cue", "pain_point", "price_perception", "service_signal"],
            ),
            "market_summary": profile.market_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
        },
        M08ForModule.M11: {
            "core_params": profile.core_params_json,
            "claim_activation_summary": profile.claim_activation_summary_json,
            "comment_signal_summary": _pick_comment_types(profile.comment_signal_summary_json, ["battlefield_support", "claim_validation"]),
            "market_signal_summary": profile.market_signal_summary_json,
            "market_summary": profile.market_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
            "product_anchor_index": profile.business_signal_index_json.get("product_anchor_index", {}),
        },
        M08ForModule.M11_5: {
            "claim_activation_summary": profile.claim_activation_summary_json,
            "claim_evidence_breakdown": profile.claim_evidence_breakdown_json,
            "comment_signal_summary": _pick_comment_types(profile.comment_signal_summary_json, ["claim_validation", "price_perception"]),
            "market_summary": profile.market_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
        },
        M08ForModule.M08_5: {
            "core_params": profile.core_params_json,
            "claim_activation_summary": profile.claim_activation_summary_json,
            "claim_evidence_breakdown": profile.claim_evidence_breakdown_json,
            "comment_signal_summary": profile.comment_signal_summary_json,
            "market_summary": profile.market_summary_json,
            "market_signal_summary": profile.market_signal_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
            "domain_confidence": profile.domain_confidence_json,
            "product_anchor_index": profile.business_signal_index_json.get("product_anchor_index", {}),
        },
        M08ForModule.M12: {
            "market_summary": profile.market_summary_json,
            "market_signal_summary": profile.market_signal_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
        },
        M08ForModule.M13: {
            "market_summary": profile.market_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
            "domain_completeness": profile.domain_completeness_json,
            "domain_confidence": profile.domain_confidence_json,
        },
        M08ForModule.M14: {
            "profile_hash": profile.profile_hash,
            "domain_completeness": profile.domain_completeness_json,
            "domain_confidence": profile.domain_confidence_json,
            "data_completeness_score": profile.data_completeness_score,
            "confidence": profile.confidence,
        },
        M08ForModule.M15: {
            "sku_master": profile.sku_master_json,
            "core_params": profile.core_params_json,
            "claim_activation_summary": profile.claim_activation_summary_json,
            "comment_signal_summary": profile.comment_signal_summary_json,
            "market_summary": profile.market_summary_json,
            "pool_summary": profile.comparable_pool_summary_json,
            "evidence_ids": profile.representative_evidence_ids,
        },
    }
    return {**base, **module_payloads[module]}


def _pick_comment_types(summary: Mapping[str, Any], signal_types: Sequence[str]) -> dict[str, Any]:
    type_summary = dict(summary.get("signal_type_summary") or {})
    return {
        "profile_id": summary.get("profile_id"),
        "comment_signal_confidence": summary.get("comment_signal_confidence"),
        "signal_type_summary": {key: type_summary.get(key, {}) for key in signal_types},
    }


def _matrix_evidence(context: _SkuBuildContext) -> dict[tuple[str, str], list[str]]:
    claim_ids = _evidence_ids_from_claims(context.claim_activations)
    validation_ids = _evidence_ids_from_claim_validations(context.claim_validations)
    comment_by_type = _group_by_attr(context.comment_signals, "signal_type")
    market_ids = _dedupe([*_evidence_ids_from_market_profiles(context.market_profiles), *_evidence_ids_from_market_signals(context.market_signals)])
    pool_ids = _evidence_ids_from_pools(context.pools)
    return {
        (M08SignalDomain.SKU_MASTER.value, "identity"): [row.evidence_id for row in context.evidence_atoms if row.evidence_type == "sku_fact"],
        (M08SignalDomain.PARAM.value, "core_params"): _evidence_ids_from_param_values(context.param_values),
        (M08SignalDomain.PARAM.value, "param_quality"): list(context.param_profile.evidence_ids or [] if context.param_profile else []),
        (M08SignalDomain.CLAIM.value, "structured_claim"): claim_ids,
        (M08SignalDomain.CLAIM.value, "final_claim_activation"): claim_ids,
        (M08SignalDomain.CLAIM_COMMENT_VALIDATION.value, "perception_validation"): validation_ids,
        (M08SignalDomain.COMMENT.value, "claim_validation"): _evidence_ids_from_comment_signals(comment_by_type.get("claim_validation", [])),
        (M08SignalDomain.COMMENT.value, "task_cue"): _evidence_ids_from_comment_signals(comment_by_type.get("task_cue", [])),
        (M08SignalDomain.COMMENT.value, "target_group_cue"): _evidence_ids_from_comment_signals(comment_by_type.get("target_group_cue", [])),
        (M08SignalDomain.COMMENT.value, "battlefield_support"): _evidence_ids_from_comment_signals(comment_by_type.get("battlefield_support", [])),
        (M08SignalDomain.COMMENT.value, "pain_point"): _evidence_ids_from_comment_signals(comment_by_type.get("pain_point", [])),
        (M08SignalDomain.COMMENT.value, "price_perception"): _evidence_ids_from_comment_signals(comment_by_type.get("price_perception", [])),
        (M08SignalDomain.COMMENT.value, "service_signal"): _evidence_ids_from_comment_signals(comment_by_type.get("service_signal", [])),
        (M08SignalDomain.MARKET.value, "price"): market_ids,
        (M08SignalDomain.MARKET.value, "sales"): market_ids,
        (M08SignalDomain.MARKET.value, "platform"): market_ids,
        (M08SignalDomain.MARKET.value, "trend"): market_ids,
        (M08SignalDomain.POOL.value, "same_size"): pool_ids,
        (M08SignalDomain.POOL.value, "adjacent_size"): pool_ids,
        (M08SignalDomain.POOL.value, "same_price_band"): pool_ids,
        (M08SignalDomain.QUALITY.value, "profile_risk"): _dedupe([*_evidence_ids_from_param_values(context.param_values), *claim_ids, *validation_ids, *market_ids]),
    }


def _matrix_source_refs(context: _SkuBuildContext) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (M08SignalDomain.SKU_MASTER.value, "identity"): {
            "clean_sku_id": context.clean_sku.clean_sku_id if context.clean_sku else None,
            "source_row_ids": list(context.clean_sku.representative_source_row_ids or [] if context.clean_sku else []),
        },
        (M08SignalDomain.PARAM.value, "core_params"): {
            "param_value_ids": [row.param_value_id for row in context.param_values],
            "sku_param_profile_id": context.param_profile.sku_param_profile_id if context.param_profile else None,
        },
        (M08SignalDomain.CLAIM.value, "structured_claim"): {
            "claim_activation_ids": [row.claim_activation_id for row in context.claim_activations],
        },
        (M08SignalDomain.CLAIM.value, "final_claim_activation"): {
            "claim_activation_ids": [row.claim_activation_id for row in context.claim_activations],
        },
        (M08SignalDomain.CLAIM_COMMENT_VALIDATION.value, "perception_validation"): {
            "claim_comment_validation_ids": [row.claim_comment_validation_id for row in context.claim_validations],
        },
        (M08SignalDomain.COMMENT.value, "claim_validation"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "claim_validation"],
        },
        (M08SignalDomain.COMMENT.value, "task_cue"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "task_cue"],
        },
        (M08SignalDomain.COMMENT.value, "target_group_cue"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "target_group_cue"],
        },
        (M08SignalDomain.COMMENT.value, "battlefield_support"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "battlefield_support"],
        },
        (M08SignalDomain.COMMENT.value, "pain_point"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "pain_point"],
        },
        (M08SignalDomain.COMMENT.value, "price_perception"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "price_perception"],
        },
        (M08SignalDomain.COMMENT.value, "service_signal"): {
            "signal_ids": [row.signal_id for row in context.comment_signals if row.signal_type == "service_signal"],
        },
        (M08SignalDomain.MARKET.value, "price"): {"sku_market_profile_ids": [row.sku_market_profile_id for row in context.market_profiles]},
        (M08SignalDomain.MARKET.value, "sales"): {"sku_market_profile_ids": [row.sku_market_profile_id for row in context.market_profiles]},
        (M08SignalDomain.MARKET.value, "platform"): {"market_signal_ids": [row.market_signal_id for row in context.market_signals]},
        (M08SignalDomain.MARKET.value, "trend"): {"market_signal_ids": [row.market_signal_id for row in context.market_signals]},
        (M08SignalDomain.POOL.value, "same_size"): {"pool_ids": [row.pool_id for row in context.pools if row.pool_type == "same_size"]},
        (M08SignalDomain.POOL.value, "adjacent_size"): {"pool_ids": [row.pool_id for row in context.pools if row.pool_type == "adjacent_size"]},
        (M08SignalDomain.POOL.value, "same_price_band"): {"pool_ids": [row.pool_id for row in context.pools if row.pool_type == "same_price_band"]},
        (M08SignalDomain.QUALITY.value, "profile_risk"): {"risk_source": "assembled_from_upstream_quality_flags"},
    }


def _row_coverage_status(
    domain: M08SignalDomain,
    sub_domain: str,
    coverage: Mapping[str, Any],
    evidence_ids: Sequence[str],
    source_refs: Mapping[str, Any],
) -> str:
    if evidence_ids:
        return M08CoverageStatus.COVERED.value
    if source_refs and any(value for value in source_refs.values() if value):
        domain_status = str(coverage.get(domain.value, {}).get("status") or M08CoverageStatus.UNKNOWN.value)
        return M08CoverageStatus.PARTIALLY_COVERED.value if domain_status != M08CoverageStatus.MISSING.value else domain_status
    if domain == M08SignalDomain.QUALITY and sub_domain == "profile_risk":
        return M08CoverageStatus.COVERED.value
    return str(coverage.get(domain.value, {}).get("status") or M08CoverageStatus.MISSING.value)


def _source_profile_refs(context: _SkuBuildContext) -> dict[str, Any]:
    return {
        "clean_sku_id": context.clean_sku.clean_sku_id if context.clean_sku else None,
        "clean_hash": context.clean_sku.clean_hash if context.clean_sku else None,
        "sku_param_profile_id": context.param_profile.sku_param_profile_id if context.param_profile else None,
        "param_profile_hash": context.param_profile.profile_hash if context.param_profile else None,
        "claim_activation_ids": [row.claim_activation_id for row in context.claim_activations],
        "claim_validation_ids": [row.claim_comment_validation_id for row in context.claim_validations],
        "comment_signal_profile_id": context.comment_profile.sku_comment_signal_profile_id if context.comment_profile else None,
        "comment_signal_profile_hash": context.comment_profile.result_hash if context.comment_profile else None,
        "comment_signal_ids": [row.signal_id for row in context.comment_signals],
        "market_profile_ids": [row.sku_market_profile_id for row in context.market_profiles],
        "market_signal_ids": [row.market_signal_id for row in context.market_signals],
        "pool_ids": [row.pool_id for row in context.pools],
        "pool_member_ids": [row.pool_member_id for row in context.pool_members],
    }


def _evidence_summary(evidence_atoms: Sequence[entities.Core3EvidenceAtom], evidence_ids: Sequence[str]) -> dict[str, Any]:
    atoms_by_type = Counter(row.evidence_type for row in evidence_atoms)
    confidence_counts = Counter(row.confidence_level for row in evidence_atoms if row.evidence_id in set(evidence_ids))
    return {
        "representative_evidence_count": len(evidence_ids),
        "m02_evidence_type_counts": dict(atoms_by_type),
        "representative_confidence_counts": dict(confidence_counts),
    }


def _required_features(module: M08ForModule) -> list[str]:
    mapping = {
        M08ForModule.M08_4: ["core_params", "claim_activation_summary", "comment_signal_summary", "market_summary"],
        M08ForModule.M09: ["core_params", "claim_activation_summary", "comment_task_cue", "market_summary"],
        M08ForModule.M10: ["comment_target_group_cue", "comment_pain_point", "market_summary"],
        M08ForModule.M11: ["core_params", "claim_activation_summary", "comment_battlefield_support", "market_signal_summary"],
        M08ForModule.M11_5: ["claim_activation_summary", "claim_evidence_breakdown", "market_summary", "pool_summary"],
        M08ForModule.M08_5: ["core_params", "claim_activation_summary", "comment_signal_summary", "market_summary"],
        M08ForModule.M12: ["market_summary", "pool_summary"],
        M08ForModule.M13: ["market_summary", "pool_summary", "domain_confidence"],
        M08ForModule.M14: ["profile_hash", "domain_completeness", "domain_confidence"],
        M08ForModule.M15: ["sku_master", "evidence_ids", "core_params", "claim_activation_summary", "market_summary"],
    }
    return mapping[module]


def _optional_features(module: M08ForModule) -> list[str]:
    mapping = {
        M08ForModule.M08_4: ["claim_evidence_breakdown", "comment_quality", "market_signal_summary", "domain_confidence", "product_anchor_index"],
        M08ForModule.M09: ["comment_claim_validation", "pool_summary"],
        M08ForModule.M10: ["service_signal", "pool_summary"],
        M08ForModule.M11: ["price_perception", "pool_summary", "market_pool_key", "product_anchor_index"],
        M08ForModule.M11_5: ["comment_price_perception", "market_signal_summary"],
        M08ForModule.M08_5: ["claim_evidence_breakdown", "market_signal_summary", "pool_summary", "domain_confidence", "product_anchor_index"],
        M08ForModule.M12: ["comment_target_group_cue", "param_summary"],
        M08ForModule.M13: ["comment_quality", "risk_signals"],
        M08ForModule.M14: ["missing_signals", "risk_signals"],
        M08ForModule.M15: ["comment_signal_summary", "pool_summary"],
    }
    return mapping[module]


def _view_role(module: M08ForModule) -> M08ViewRole:
    if module == M08ForModule.M15:
        return M08ViewRole.REPORT_INPUT
    if module in {M08ForModule.M12, M08ForModule.M13, M08ForModule.M14}:
        return M08ViewRole.SCORING_INPUT
    return M08ViewRole.PRIMARY_INPUT


def _target_hints(rows: Sequence[entities.Core3CommentDownstreamSignal], signal_type: str) -> list[str]:
    return _dedupe([row.target_code_hint for row in rows if row.signal_type == signal_type])[:30]


def _upstream_modules_for_domain(domain: str) -> list[str]:
    mapping = {
        "sku_master": ["M01", "M02"],
        "param": ["M03"],
        "claim": ["M04b"],
        "claim_comment_validation": ["M04b"],
        "comment": ["M05", "M06"],
        "market": ["M07"],
        "pool": ["M07"],
        "quality": ["M03", "M04b", "M06", "M07"],
    }
    return mapping.get(domain, [])


def _full_market_profile(rows: Sequence[entities.Core3SkuMarketProfile]) -> entities.Core3SkuMarketProfile | None:
    for row in rows:
        if row.analysis_window == FULL_WINDOW:
            return row
    return rows[0] if rows else None


def _evidence_ids_from_param_values(rows: Iterable[entities.Core3ExtractParamValue]) -> list[str]:
    return _dedupe([item for row in rows for item in list(row.evidence_ids or [])])


def _evidence_ids_from_claims(rows: Iterable[entities.Core3SkuClaimActivation]) -> list[str]:
    return _dedupe(
        [
            item
            for row in rows
            for item in [
                *list(row.evidence_ids or []),
                *list(row.param_evidence_ids or []),
                *list(row.promo_evidence_ids or []),
                *list(row.comment_evidence_ids or []),
            ]
        ]
    )


def _evidence_ids_from_claim_validations(rows: Iterable[entities.Core3SkuClaimCommentValidation]) -> list[str]:
    return _dedupe(
        [
            item
            for row in rows
            for item in [
                *list(row.comment_evidence_ids or []),
                *list(row.base_evidence_ids or []),
            ]
        ]
    )


def _evidence_ids_from_comment_signals(rows: Iterable[entities.Core3CommentDownstreamSignal]) -> list[str]:
    return _dedupe([item for row in rows for item in list(row.evidence_ids or [])])


def _evidence_ids_from_market_profiles(rows: Iterable[entities.Core3SkuMarketProfile]) -> list[str]:
    return _dedupe([item for row in rows for item in list(row.evidence_ids or [])])


def _evidence_ids_from_market_signals(rows: Iterable[entities.Core3MarketSignal]) -> list[str]:
    return _dedupe([item for row in rows for item in list(row.evidence_ids or [])])


def _evidence_ids_from_pools(rows: Iterable[entities.Core3ComparablePoolBaseline]) -> list[str]:
    return _dedupe([item for row in rows for item in list(row.evidence_ids or [])])


def _group_by_sku(rows: Iterable[Any]) -> dict[str, list[Any]]:
    return _group_by_attr(rows, "sku_code")


def _group_by_attr(rows: Iterable[Any], attr_name: str) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        key = getattr(row, attr_name, None)
        if key is not None:
            result[str(key)].append(row)
    return dict(result)


def _coverage_score(status: str) -> Decimal:
    if status == M08CoverageStatus.COVERED.value:
        return D1
    if status == M08CoverageStatus.PARTIALLY_COVERED.value:
        return Decimal("0.5000")
    return D0


def _average(values: Iterable[Decimal | float | int | None]) -> Decimal:
    normalized = [_clamp(value) for value in values if value is not None]
    if not normalized:
        return D0
    return _round4(sum(normalized) / Decimal(len(normalized)))


def _clamp(value: Decimal | float | int | None) -> Decimal:
    decimal_value = _decimal(value)
    if decimal_value < D0:
        return D0
    if decimal_value > D1:
        return D1
    return _round4(decimal_value)


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return D0
    return Decimal(str(value))


def _round4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _record_id(prefix: str, *parts: Any) -> str:
    digest = stable_hash({"prefix": prefix, "parts": list(parts)}, version="m08_record_id_v1").split(":")[-1][:32]
    return f"{prefix}_{digest}"


def _dedupe(values: Iterable[Any]) -> list[Any]:
    result: list[Any] = []
    for value in values:
        if value in (None, ""):
            continue
        if value not in result:
            result.append(value)
    return result


def _assert_no_forbidden_fields(value: Any) -> None:
    forbidden = set(CORE3_M08_FORBIDDEN_OUTPUT_FIELDS)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in forbidden:
                raise ValueError(f"M08 output must not contain forbidden downstream field: {key}")
            _assert_no_forbidden_fields(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_forbidden_fields(item)
