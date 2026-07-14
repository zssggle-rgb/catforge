"""Orchestrate G12-G19 and assemble deterministic SKU competitor-profile drafts."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
    CandidatePipelineRun,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection import (
    KeyCompetitorSelector,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection_schemas import (
    KeyCompetitorSelectionBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    CompetitorProfileBatchMaterializationResult,
    CompetitorProfileMaterializationConfig,
    MaterializedCompetitorProfile,
    TargetMaterializationStatus,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureBundle,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure import (
    PriceVolumePressureEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureAssessment,
    PriceVolumePressureBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation import (
    CompetitorRelationEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationEvaluationBundle,
    CompetitorRelationPairEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    CompetitorPairDraft,
    CompetitorProfileDraftBundle,
    EvidenceRef,
    KeyCompetitorSummary,
    SkuCompetitorDecisionProfileDraft,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvidenceEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidenceBundle,
)
from app.services.core3_real_data.hash_utils import stable_hash


_CONFIDENCE = {
    "high": Decimal("0.9000"),
    "medium": Decimal("0.7500"),
    "low": Decimal("0.5500"),
    "unknown": Decimal("0.3000"),
}
_FORMAL_STATUSES = {"passed", "limited"}
_VALUE_RELATIONS = {
    "direct_substitute",
    "downtrade_diversion",
    "uptrade_alternative",
    "same_value_substitute",
}
_SAFE_ERROR_MESSAGES = {
    "category_scope_mismatch": "目标 SKU 与当前品类或 serving scope 不一致。",
    "target_not_authoritative": "目标 SKU 不在当前权威 SKU 清单中。",
    "materialization_failed": "该 SKU 画像生成失败，已隔离并继续处理其他 SKU。",
}


class CompetitorProfileMaterializationError(RuntimeError):
    """Raised for invalid materializer inputs or duplicate batch targets."""


class CompetitorProfileMaterializer:
    """Build one complete in-memory draft or an isolated deterministic batch."""

    def materialize(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        config: CompetitorProfileMaterializationConfig,
    ) -> MaterializedCompetitorProfile:
        _assert_materialization_scope(category_bundle, target_bundle, config)
        if target_bundle.analysis_state == "blocked":
            return _materialize_blocked_target(category_bundle, target_bundle, config)
        pipeline = CandidatePipelineDeterminismGuard().run(
            category_bundle,
            target_bundle,
            recall_config=config.recall,
            eligibility_config=config.eligibility,
        )
        features = PairFeatureBuilder().build(pipeline)
        pool = PurchasePoolSemanticEvaluator().evaluate(
            features,
            config.purchase_pool,
        )
        value = ValueSubstitutionEvidenceEvaluator().evaluate(
            features,
            pool,
            config.value_substitution,
        )
        pressure = PriceVolumePressureEvaluator().evaluate(
            features,
            pool,
            value,
            config.price_volume,
        )
        relations = CompetitorRelationEvaluator().evaluate(
            features,
            pool,
            value,
            pressure,
            config.relation,
        )
        selection = KeyCompetitorSelector().select(
            relations,
            config.key_selection,
        )
        _assert_stage_conservation(
            pipeline,
            features,
            pool,
            value,
            pressure,
            relations,
            selection,
        )
        draft = _assemble_draft(
            pipeline,
            features,
            pool,
            pressure,
            relations,
            selection,
            config,
        )
        stage_hashes = {
            "candidate_pipeline": pipeline.receipt.result_hash,
            "pair_feature": features.result_hash,
            "purchase_pool": pool.result_hash,
            "value_substitution": value.result_hash,
            "price_volume_pressure": pressure.result_hash,
            "relation_evaluation": relations.result_hash,
            "key_selection": selection.result_hash,
            "profile": draft.profile.result_hash,
        }
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "config": config.model_dump(mode="json"),
                "stage_result_hashes": stage_hashes,
            },
            version="competitor_profile_materializer_input_v1",
        )
        return MaterializedCompetitorProfile(
            target_sku_code=target_bundle.target_sku_code,
            product_category=category_bundle.serving_scope.product_category,
            draft=draft,
            stage_result_hashes=stage_hashes,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "target_sku_code": target_bundle.target_sku_code,
                    "product_category": category_bundle.serving_scope.product_category,
                    "stage_result_hashes": stage_hashes,
                    "config_version": config.config_version,
                    "input_fingerprint": input_fingerprint,
                },
                version="competitor_profile_materializer_result_v1",
            ),
        )

    def materialize_batch(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundles: Sequence[CompetitorProfileTargetInputBundle],
        config: CompetitorProfileMaterializationConfig,
    ) -> CompetitorProfileBatchMaterializationResult:
        target_codes = [row.target_sku_code for row in target_bundles]
        if len(target_codes) != len(set(target_codes)):
            raise CompetitorProfileMaterializationError(
                "batch target SKU codes must be unique"
            )
        ordered = sorted(target_bundles, key=lambda row: row.target_sku_code)
        profiles: list[MaterializedCompetitorProfile] = []
        statuses: list[TargetMaterializationStatus] = []
        for target in ordered:
            try:
                result = self.materialize(category_bundle, target, config)
            except Exception as exc:  # noqa: BLE001 - target isolation boundary
                error_code = _safe_error_code(exc)
                statuses.append(
                    TargetMaterializationStatus(
                        target_sku_code=target.target_sku_code,
                        status="failed",
                        error_code=error_code,
                        error_message=_SAFE_ERROR_MESSAGES[error_code],
                    )
                )
                continue
            profiles.append(result)
            statuses.append(
                TargetMaterializationStatus(
                    target_sku_code=target.target_sku_code,
                    status="generated",
                    profile_result_hash=result.result_hash,
                    stage_result_hashes=result.stage_result_hashes,
                )
            )
        succeeded = len(profiles)
        failed = len(statuses) - succeeded
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_input_fingerprints": {
                    row.target_sku_code: row.input_fingerprint for row in ordered
                },
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_batch_materializer_input_v1",
        )
        return CompetitorProfileBatchMaterializationResult(
            product_category=category_bundle.serving_scope.product_category,
            requested_count=len(ordered),
            succeeded_count=succeeded,
            failed_count=failed,
            statuses=statuses,
            materialized_profiles=profiles,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "statuses": [row.model_dump(mode="json") for row in statuses],
                    "profile_hashes": [row.result_hash for row in profiles],
                },
                version="competitor_profile_batch_materializer_result_v1",
            ),
        )


def _assert_materialization_scope(
    category_bundle: CompetitorProfileCategoryInputBundle,
    target_bundle: CompetitorProfileTargetInputBundle,
    config: CompetitorProfileMaterializationConfig,
) -> None:
    scope = category_bundle.serving_scope
    if target_bundle.serving_scope != scope or config.product_category != (
        scope.product_category
    ):
        raise CompetitorProfileMaterializationError(
            "category_scope_mismatch: target, category, and config scopes must match"
        )
    if target_bundle.target_sku_code not in category_bundle.authoritative_sku_codes:
        raise CompetitorProfileMaterializationError(
            "target_not_authoritative: target is outside the authoritative SKU manifest"
        )


def _assert_stage_conservation(
    pipeline: CandidatePipelineRun,
    features: PairFeatureBundle,
    pool: PurchasePoolSemanticBundle,
    value: ValueSubstitutionEvidenceBundle,
    pressure: PriceVolumePressureBundle,
    relations: CompetitorRelationEvaluationBundle,
    selection: KeyCompetitorSelectionBundle,
) -> None:
    expected = [row.candidate.sku_code for row in features.pairs]
    candidate_lists = [
        [row.candidate.sku_code for row in pipeline.eligibility_manifest.candidates],
        [row.candidate.sku_code for row in pool.pairs],
        [row.candidate.sku_code for row in value.pairs],
        [row.candidate.sku_code for row in pressure.pairs],
        [row.candidate.sku_code for row in relations.pairs],
        [row.candidate.sku_code for row in selection.pair_decisions],
    ]
    if any(rows != expected for rows in candidate_lists):
        raise CompetitorProfileMaterializationError(
            "candidate conservation failed across materialization stages"
        )


def _materialize_blocked_target(
    category_bundle: CompetitorProfileCategoryInputBundle,
    target_bundle: CompetitorProfileTargetInputBundle,
    config: CompetitorProfileMaterializationConfig,
) -> MaterializedCompetitorProfile:
    scope = category_bundle.serving_scope
    identity = CandidateIdentity(
        sku_code=target_bundle.target_sku_code,
        brand_name=target_bundle.target_identity.get("brand_name"),
        model_name=target_bundle.target_identity.get("model_name"),
        display_name_cn=(
            " ".join(
                value
                for value in (
                    target_bundle.target_identity.get("brand_name"),
                    target_bundle.target_identity.get("model_name"),
                )
                if value
            )
            or target_bundle.target_sku_code
        ),
        product_category=scope.product_category,
    )
    limitations = sorted(
        set(target_bundle.hard_block_reasons)
        | set(target_bundle.limitations)
        | {"materialization_stages_not_run_target_blocked"}
    )
    profile_input = stable_hash(
        {
            "target_input_fingerprint": target_bundle.input_fingerprint,
            "config_version": config.config_version,
            "blocked_reasons": target_bundle.hard_block_reasons,
        },
        version="competitor_profile_blocked_sku_profile_input_v1",
    )
    profile_payload = {
        "project_id": scope.project_id,
        "category_code": scope.category_code,
        "target_sku_code": target_bundle.target_sku_code,
        "analysis_state": "blocked",
        "conclusion_state": "insufficient_evidence",
        "profile_confidence": Decimal("0.3000"),
        "no_conclusion_reason": {
            "reason_code": "target_hard_blocked",
            "reason_cn": "目标 SKU 的关键上游或品类范围存在阻断，当前不能形成竞品结论。",
        },
        "limitations": limitations,
        "review_required": True,
        "input_fingerprint": profile_input,
    }
    profile = SkuCompetitorDecisionProfileDraft(
        project_id=scope.project_id,
        category_code=scope.category_code,
        target_sku_code=target_bundle.target_sku_code,
        brand_name=identity.brand_name,
        model_name=identity.model_name,
        display_name_cn=identity.display_name_cn,
        target_market_summary=_target_market_summary(target_bundle),
        analysis_state="blocked",
        conclusion_state="insufficient_evidence",
        freshness_status="current",
        profile_confidence=Decimal("0.3000"),
        no_conclusion_reason=profile_payload["no_conclusion_reason"],
        source_lineage=_source_lineage_from_scope(scope),
        evidence_refs=target_bundle.evidence_refs,
        limitations=limitations,
        review_required=True,
        review_status="review_required",
        input_fingerprint=profile_input,
        result_hash=stable_hash(
            profile_payload,
            version="competitor_profile_blocked_sku_profile_result_v1",
        ),
    )
    draft = CompetitorProfileDraftBundle(profile=profile, pairs=[], selections=[])
    skipped_hashes = {
        stage: stable_hash(
            {
                "target_sku_code": target_bundle.target_sku_code,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "stage": stage,
                "status": "not_run_target_blocked",
            },
            version="competitor_profile_blocked_stage_v1",
        )
        for stage in (
            "candidate_pipeline",
            "pair_feature",
            "purchase_pool",
            "value_substitution",
            "price_volume_pressure",
            "relation_evaluation",
            "key_selection",
        )
    }
    stage_hashes = {**skipped_hashes, "profile": profile.result_hash}
    input_fingerprint = stable_hash(
        {
            "category_input_fingerprint": category_bundle.input_fingerprint,
            "target_input_fingerprint": target_bundle.input_fingerprint,
            "config": config.model_dump(mode="json"),
            "stage_result_hashes": stage_hashes,
        },
        version="competitor_profile_materializer_input_v1",
    )
    return MaterializedCompetitorProfile(
        target_sku_code=target_bundle.target_sku_code,
        product_category=scope.product_category,
        draft=draft,
        stage_result_hashes=stage_hashes,
        config_version=config.config_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            {
                "target_sku_code": target_bundle.target_sku_code,
                "product_category": scope.product_category,
                "stage_result_hashes": stage_hashes,
                "config_version": config.config_version,
                "input_fingerprint": input_fingerprint,
            },
            version="competitor_profile_materializer_result_v1",
        ),
    )


def _assemble_draft(
    pipeline: CandidatePipelineRun,
    features: PairFeatureBundle,
    pool: PurchasePoolSemanticBundle,
    pressure: PriceVolumePressureBundle,
    relations: CompetitorRelationEvaluationBundle,
    selection: KeyCompetitorSelectionBundle,
    config: CompetitorProfileMaterializationConfig,
) -> CompetitorProfileDraftBundle:
    feature_by_sku = {row.candidate.sku_code: row for row in features.pairs}
    pool_by_sku = {row.candidate.sku_code: row for row in pool.pairs}
    pressure_by_sku = {row.candidate.sku_code: row for row in pressure.pairs}
    relation_by_sku = {row.candidate.sku_code: row for row in relations.pairs}
    eligibility_by_sku = {
        row.candidate.sku_code: row for row in pipeline.eligibility_manifest.candidates
    }
    decision_by_sku = {row.candidate.sku_code: row for row in selection.pair_decisions}
    pairs = [
        _materialize_pair(
            pipeline.category_bundle.serving_scope.project_id,
            feature_by_sku[sku_code],
            pool_by_sku[sku_code],
            relation_by_sku[sku_code],
            eligibility_by_sku[sku_code],
            decision_by_sku[sku_code],
            config,
        )
        for sku_code in sorted(feature_by_sku)
    ]
    profile = _profile(
        pipeline,
        features,
        pressure_by_sku,
        relation_by_sku,
        selection,
        pairs,
        config,
    )
    return CompetitorProfileDraftBundle(
        profile=profile,
        pairs=pairs,
        selections=selection.selections,
    )


def _materialize_pair(
    project_id: str,
    feature: PairFeatureRecord,
    pool: PurchasePoolSemanticPairAssessment,
    relation: CompetitorRelationPairEvaluation,
    eligibility,
    decision,
    config: CompetitorProfileMaterializationConfig,
) -> CompetitorPairDraft:
    confidence_level = relation.overall_confidence_level
    competitor_member = relation.candidate_status in {"eligible", "limited"}
    review_required = relation.review_required or relation.candidate_status in {
        "review_required",
        "blocked",
    }
    if competitor_member and confidence_level in {"low", "unknown"}:
        review_required = True
    evidence_refs = _merge_refs(
        feature.evidence_refs,
        pool.evidence_refs,
        relation.evidence_refs,
    )
    input_fingerprint = stable_hash(
        {
            "pair_feature_result_hash": feature.result_hash,
            "purchase_pool_result_hash": pool.result_hash,
            "relation_evaluation_result_hash": relation.result_hash,
            "selection_decision_result_hash": decision.result_hash,
            "config_version": config.config_version,
        },
        version="competitor_profile_materialized_pair_input_v1",
    )
    payload = {
        "candidate_sku_code": feature.candidate.sku_code,
        "candidate_status": relation.candidate_status,
        "competitor_member": competitor_member,
        "reference_member": relation.reference_member,
        "recall_sources": feature.recall_sources,
        "purchase_pool_result_hash": pool.purchase_pool.result_hash,
        "relation_hashes": [row.result_hash for row in relation.relation_assessments],
        "question_hashes": [row.result_hash for row in relation.question_eligibility],
        "selected": decision.selected,
        "selection_rank": decision.selection_rank,
        "non_selection_reason_code": decision.non_selection_reason_code,
        "confidence_level": confidence_level,
        "review_required": review_required,
        "input_fingerprint": input_fingerprint,
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
    }
    return CompetitorPairDraft(
        project_id=project_id,
        category_code=feature.target.product_category,
        target_sku_code=feature.target.sku_code,
        candidate=feature.candidate,
        recall_sources=feature.recall_sources,
        recall_facts={
            "source_count": len(feature.recall_sources),
            "product_form_status": feature.product_form_facts.compatibility_status,
        },
        manifest_order_key=feature.candidate.sku_code,
        competitor_member=competitor_member,
        reference_member=relation.reference_member,
        candidate_status=relation.candidate_status,
        purchase_pool=pool.purchase_pool,
        evidence_family_assessments=relation.evidence_family_assessments,
        market_comparison=feature.market_comparison,
        relation_assessments=relation.relation_assessments,
        question_eligibility=relation.question_eligibility,
        reference_purposes=eligibility.reference_purposes,
        selected=decision.selected,
        non_selection_reason_code=decision.non_selection_reason_code,
        non_selection_reason_cn=decision.non_selection_reason_cn,
        confidence_level=confidence_level,
        confidence=_CONFIDENCE[confidence_level],
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        evidence_refs=evidence_refs,
        limitations=sorted(
            set(feature.unknown_reason_codes)
            | set(feature.review_reason_codes)
            | set(relation.limitations)
        ),
        risk_flags=sorted(relation.review_reason_codes),
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_materialized_pair_result_v1",
        ),
    )


def _profile(
    pipeline: CandidatePipelineRun,
    features: PairFeatureBundle,
    pressure_by_sku: dict[str, PriceVolumePressureAssessment],
    relation_by_sku: dict[str, CompetitorRelationPairEvaluation],
    selection: KeyCompetitorSelectionBundle,
    pairs: Sequence[CompetitorPairDraft],
    config: CompetitorProfileMaterializationConfig,
) -> SkuCompetitorDecisionProfileDraft:
    target_bundle = pipeline.target_bundle
    target = features.target
    analysis_state = _analysis_state(target_bundle, relation_by_sku, selection)
    conclusion_state = _conclusion_state(selection, analysis_state)
    review_required = (
        analysis_state == "blocked"
        or analysis_state == "partial"
        or selection.selection_state == ("review_required")
        or any(row.review_required for row in pairs)
    )
    confidence = _profile_confidence(selection, analysis_state, review_required)
    candidate_counts = Counter(row.candidate_status for row in pairs)
    relation_counts = Counter(
        row.status for pair in pairs for row in pair.relation_assessments
    )
    key_summary = [
        KeyCompetitorSummary(
            candidate_sku_code=row.candidate_sku_code,
            display_name_cn=next(
                pair.candidate.display_name_cn
                for pair in pairs
                if pair.candidate.sku_code == row.candidate_sku_code
            ),
            selection_rank=row.selection_rank,
            primary_decision_topic=row.primary_decision_topic,
            primary_relation_code=row.primary_relation_code,
            conclusion_cn=row.selection_reason_cn,
        )
        for row in selection.selections
    ]
    advantages = _competitive_advantages(relation_by_sku)
    substitutable = _substitutable_values(relation_by_sku)
    price_pressures = _price_scale_pressures(pressure_by_sku, relation_by_sku)
    same_brand = _same_brand_findings(relation_by_sku)
    configuration = _configuration_decisions(features, relation_by_sku)
    no_conclusion = _no_conclusion(selection, target_bundle)
    qa_index = _qa_index(relation_by_sku)
    evidence_refs = _merge_refs(
        target_bundle.evidence_refs,
        *(row.evidence_refs for row in pairs),
    )
    limitations = sorted(
        set(target_bundle.limitations)
        | set(target_bundle.hard_block_reasons)
        | set(selection.limitations)
        | {item for row in pairs for item in row.limitations}
    )
    source_lineage = _source_lineage(pipeline)
    target_market_summary = _target_market_summary(target_bundle)
    input_fingerprint = stable_hash(
        {
            "target_input_fingerprint": target_bundle.input_fingerprint,
            "pair_hashes": [row.result_hash for row in pairs],
            "selection_result_hash": selection.result_hash,
            "config_version": config.config_version,
        },
        version="competitor_profile_sku_profile_input_v1",
    )
    payload = {
        "project_id": pipeline.category_bundle.serving_scope.project_id,
        "category_code": pipeline.category_bundle.serving_scope.category_code,
        "target_sku_code": target.sku_code,
        "analysis_state": analysis_state,
        "conclusion_state": conclusion_state,
        "profile_confidence": confidence,
        "candidate_status_counts": dict(sorted(candidate_counts.items())),
        "relation_status_counts": dict(sorted(relation_counts.items())),
        "key_competitor_summary": [row.model_dump(mode="json") for row in key_summary],
        "competitive_advantages": advantages,
        "substitutable_values": substitutable,
        "price_scale_pressures": price_pressures,
        "same_brand_findings": same_brand,
        "configuration_decisions": configuration,
        "no_conclusion_reason": no_conclusion,
        "source_lineage": source_lineage,
        "qa_index": qa_index,
        "limitations": limitations,
        "review_required": review_required,
        "input_fingerprint": input_fingerprint,
    }
    return SkuCompetitorDecisionProfileDraft(
        project_id=pipeline.category_bundle.serving_scope.project_id,
        category_code=pipeline.category_bundle.serving_scope.category_code,
        target_sku_code=target.sku_code,
        brand_name=target.brand_name,
        model_name=target.model_name,
        display_name_cn=target.display_name_cn,
        target_market_summary=target_market_summary,
        analysis_state=analysis_state,
        conclusion_state=conclusion_state,
        freshness_status="current",
        profile_confidence=confidence,
        candidate_status_counts=dict(sorted(candidate_counts.items())),
        relation_status_counts=dict(sorted(relation_counts.items())),
        key_competitor_summary=key_summary,
        competitive_advantages=advantages,
        substitutable_values=substitutable,
        price_scale_pressures=price_pressures,
        same_brand_findings=same_brand,
        configuration_decisions=configuration,
        no_conclusion_reason=no_conclusion,
        source_lineage=source_lineage,
        qa_index=qa_index,
        evidence_refs=evidence_refs,
        limitations=limitations,
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_sku_profile_result_v1",
        ),
    )


def _analysis_state(target_bundle, relation_by_sku, selection) -> str:
    if target_bundle.analysis_state == "blocked":
        return "blocked"
    if target_bundle.analysis_state == "partial":
        return "partial"
    if selection.selection_state in {"insufficient_evidence", "review_required"}:
        return "partial"
    if any(
        row.candidate_status in {"review_required", "blocked"}
        or any(rel.status == "unassessable" for rel in row.relation_assessments)
        for row in relation_by_sku.values()
    ):
        return "partial"
    return "ready"


def _conclusion_state(
    selection: KeyCompetitorSelectionBundle,
    analysis_state: str,
) -> str:
    if selection.selection_state == "selected":
        return "available"
    if (
        selection.selection_state == "no_priority_competitor"
        and analysis_state == "ready"
    ):
        return "no_priority_competitor"
    return "insufficient_evidence"


def _profile_confidence(selection, analysis_state, review_required) -> Decimal:
    if analysis_state == "blocked":
        return Decimal("0.3000")
    if selection.selections:
        value = min(_CONFIDENCE[row.confidence_level] for row in selection.selections)
    elif selection.selection_state == "no_priority_competitor":
        value = Decimal("0.7500")
    else:
        value = Decimal("0.5000")
    return min(value, Decimal("0.5500")) if review_required else value


def _competitive_advantages(relations) -> list[dict[str, Any]]:
    result = []
    for sku_code, pair in sorted(relations.items()):
        if not any(row.status in _FORMAL_STATUSES for row in pair.relation_assessments):
            continue
        for family in pair.evidence_family_assessments:
            if family.direction != "target_stronger" or not family.matched_codes:
                continue
            result.append(
                {
                    "candidate_sku_code": sku_code,
                    "evidence_family": family.family,
                    "value_codes": family.matched_codes,
                    "conclusion_cn": "本品在该用户价值证据上强于该候选。",
                }
            )
    return result


def _substitutable_values(relations) -> list[dict[str, Any]]:
    result = []
    for sku_code, pair in sorted(relations.items()):
        formal = [
            row
            for row in pair.relation_assessments
            if row.relation_code in _VALUE_RELATIONS and row.status in _FORMAL_STATUSES
        ]
        if not formal:
            continue
        value_codes = sorted(
            {
                code
                for family in pair.evidence_family_assessments
                if family.family in {"F1_purchase_reason", "F4_user_realization"}
                for code in family.matched_codes
            }
        )
        if value_codes:
            result.append(
                {
                    "candidate_sku_code": sku_code,
                    "value_codes": value_codes,
                    "relation_codes": sorted(row.relation_code for row in formal),
                    "causal_wtp_claim": False,
                }
            )
    return result


def _price_scale_pressures(pressure_by_sku, relations) -> list[dict[str, Any]]:
    result = []
    for sku_code, market in sorted(pressure_by_sku.items()):
        formal = [
            row
            for row in relations[sku_code].relation_assessments
            if row.status in _FORMAL_STATUSES
        ]
        if not formal or market.pressure_direction in {
            "unassessable",
            "reference_only",
            "no_observed_pressure",
        }:
            continue
        result.append(
            {
                "candidate_sku_code": sku_code,
                "pressure_direction": market.pressure_direction,
                "target_weighted_price": market.target_weighted_price,
                "candidate_weighted_price": market.candidate_weighted_price,
                "price_gap_pct": market.price_gap_pct,
                "target_avg_weekly_volume": market.target_avg_weekly_volume,
                "candidate_avg_weekly_volume": market.candidate_avg_weekly_volume,
                "weekly_volume_ratio": market.weekly_volume_ratio,
                "causal_claim": False,
                "price_change_sales_increment_claim": False,
            }
        )
    return result


def _same_brand_findings(relations) -> list[dict[str, Any]]:
    result = []
    for sku_code, pair in sorted(relations.items()):
        row = next(
            item
            for item in pair.relation_assessments
            if item.relation_code == "same_brand_ladder"
        )
        if row.status in _FORMAL_STATUSES:
            result.append(
                {
                    "candidate_sku_code": sku_code,
                    "relation_status": row.status,
                    "business_effect": row.business_effect,
                }
            )
    return result


def _configuration_decisions(features, relations) -> list[dict[str, Any]]:
    result = []
    for feature in features.pairs:
        pair = relations[feature.candidate.sku_code]
        if not any(row.status in _FORMAL_STATUSES for row in pair.relation_assessments):
            continue
        question = next(
            row
            for row in pair.question_eligibility
            if row.question_code == "configuration_follow"
        )
        differences = sorted(
            row.feature_code
            for row in feature.aligned_features
            if row.feature_group in {"parameter", "claim_expression"}
            and row.comparison_status != "shared"
        )
        if not differences:
            continue
        result.append(
            {
                "candidate_sku_code": feature.candidate.sku_code,
                "decision": (
                    "evaluate_follow"
                    if question.availability == "eligible"
                    else "do_not_follow_without_value_evidence"
                ),
                "feature_codes": differences,
                "question_availability": question.availability,
            }
        )
    return result


def _no_conclusion(selection, target_bundle) -> dict[str, Any]:
    if selection.selection_state == "selected":
        return {}
    reason_code = selection.selection_state
    if reason_code == "no_priority_competitor" and target_bundle.analysis_state != (
        "ready"
    ):
        reason_code = "insufficient_evidence"
    reason_cn = {
        "no_priority_competitor": "当前数据已完成比较，但没有候选达到重点竞品门槛。",
        "insufficient_evidence": "当前关键关系证据不足，暂时无法形成重点竞品结论。",
        "review_required": "关键候选证据需要复核，复核前不形成重点竞品结论。",
    }[reason_code]
    return {
        "reason_code": reason_code,
        "reason_cn": reason_cn,
        "target_analysis_state": target_bundle.analysis_state,
    }


def _qa_index(relations) -> list[dict[str, Any]]:
    question_codes = sorted(
        {
            row.question_code
            for pair in relations.values()
            for row in pair.question_eligibility
        }
    )
    return [
        {
            "question_code": code,
            "eligible_candidate_sku_codes": sorted(
                sku_code
                for sku_code, pair in relations.items()
                if next(
                    row
                    for row in pair.question_eligibility
                    if row.question_code == code
                ).availability
                == "eligible"
            ),
            "limited_candidate_sku_codes": sorted(
                sku_code
                for sku_code, pair in relations.items()
                if next(
                    row
                    for row in pair.question_eligibility
                    if row.question_code == code
                ).availability
                == "limited"
            ),
            "boundary": "只回答已保存关系和证据支持的业务问题。",
        }
        for code in question_codes
    ]


def _source_lineage(pipeline) -> list[dict[str, Any]]:
    return _source_lineage_from_scope(pipeline.category_bundle.serving_scope)


def _source_lineage_from_scope(scope) -> list[dict[str, Any]]:
    return [
        {
            "module_code": module_code,
            "profile_version": authority.profile_version,
            "rule_version": authority.rule_version,
            "taxonomy_version": authority.taxonomy_version,
            "source_batch_ids": authority.source_batch_ids,
            "result_hash": authority.result_hash,
        }
        for module_code, authority in sorted(scope.source_authorities.items())
    ]


def _target_market_summary(target_bundle) -> dict[str, Any]:
    rows = target_bundle.modules["M07"].records
    if not rows:
        return {"availability": "unknown"}
    facts = rows[0].facts
    allowed = (
        "price_wavg",
        "sales_volume_total",
        "active_week_count",
        "screen_size_inch",
        "size_segment",
        "market_pool_key",
        "price_band_size",
    )
    return {
        "availability": "present",
        **{key: facts.get(key) for key in allowed if facts.get(key) is not None},
    }


def _safe_error_code(exc: Exception) -> str:
    message = str(exc)
    if "category_scope_mismatch" in message:
        return "category_scope_mismatch"
    if "target_not_authoritative" in message:
        return "target_not_authoritative"
    return "materialization_failed"


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {}
    for group in groups:
        for ref in group:
            key = (
                ref.module_code,
                ref.source_batch_id or "",
                ref.record_type,
                ref.record_id,
                ref.result_hash,
            )
            by_key[key] = ref
    return [by_key[key] for key in sorted(by_key)]


__all__ = ["CompetitorProfileMaterializationError", "CompetitorProfileMaterializer"]
