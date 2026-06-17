"""M11.5 claim value layer service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.claim_value_layer_repositories import ClaimValueLayerRepository, M115InputBundle
from app.services.core3_real_data.claim_value_layer_schemas import (
    M115ServiceResult,
    M115SkuBattlefieldClaimCandidateRecord,
    M115SkuBattlefieldClaimValueSummaryRecord,
    M115SkuClaimValueEvidenceBreakdownRecord,
    M115SkuClaimValueLayerRecord,
    M115SkuClaimValueReviewIssueRecord,
)
from app.services.core3_real_data.claim_value_seed_loader import M115ClaimValueSeed, M115ClaimValueSeedLoader
from app.services.core3_real_data.constants import (
    CORE3_M11_5_EVIDENCE_DOMAINS,
    CORE3_M11_5_RULE_VERSION,
    Core3ConfidenceLevel,
    Core3RunStatus,
    M115BattlefieldRelevanceRole,
    M115ClaimCandidateSource,
    M115ClaimCandidateStatus,
    M115ClaimValueEvidenceDomain,
    M115ClaimValueLayer,
    M115ClaimValueReviewIssueType,
    M115ClaimValueSupportLevel,
    M115SampleSufficiency,
    M11BattlefieldRelationLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash


SERVICE_BATTLEFIELDS = {"BF_SERVICE_ASSURANCE", "BF_DESIGN_HOME_FIT"}
PRODUCT_CORE_BATTLEFIELDS = {
    "BF_PREMIUM_PICTURE",
    "BF_GAMING_SPORTS",
    "BF_FAMILY_VIEWING_UPGRADE",
    "BF_LARGE_SCREEN_VALUE",
    "BF_FAMILY_EYE_CARE",
    "BF_SENIOR_EASE_OF_USE",
    "BF_SMART_SYSTEM_EXPERIENCE",
    "BF_CINEMA_AUDIO_IMMERSION",
}
LAYER_ORDER = {
    M115ClaimValueLayer.PREMIUM_TENDENCY.value: 0,
    M115ClaimValueLayer.COMPETITIVE_PERFORMANCE.value: 1,
    M115ClaimValueLayer.BASIC_THRESHOLD.value: 2,
    M115ClaimValueLayer.WEAK_PERCEPTION.value: 3,
    M115ClaimValueLayer.INSUFFICIENT_SAMPLE.value: 4,
    M115ClaimValueLayer.NOT_APPLICABLE.value: 5,
    M115ClaimValueLayer.BLOCKED.value: 6,
}


@dataclass(frozen=True)
class ClaimFeature:
    claim_code: str
    claim_name: str
    claim_group: str | None
    activation_level: str
    activation_basis: str
    final_activation_score: Decimal
    perception_status: str
    confidence: Decimal


@dataclass(frozen=True)
class PoolMetrics:
    pool_id: str | None
    pool_type: str | None
    pool_sku_codes: tuple[str, ...]
    pool_sku_count: int
    with_claim_count: int
    without_claim_count: int
    coverage_rate: Decimal | None
    psi: Decimal | None
    ssi: Decimal | None
    sai: Decimal | None
    sample_sufficiency: M115SampleSufficiency
    sample_sufficiency_json: dict[str, Any]


class ClaimValueLayerService:
    def __init__(self, repository: ClaimValueLayerRepository, seed_loader: M115ClaimValueSeedLoader | None = None) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M115ClaimValueSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M11_5_RULE_VERSION,
    ) -> M115ServiceResult:
        seed = self.seed_loader.load()
        self.repository.assert_inputs_ready(batch_id)
        bundles = self.repository.list_input_bundles(batch_id, sku_scope)
        if not bundles:
            return M115ServiceResult(
                status=Core3RunStatus.WARNING,
                input_count=0,
                warnings=["M11.5 没有找到可处理的 M08 SKU 画像。"],
                summary={"batch_id": batch_id, "rule_version": rule_version, "sku_count": 0},
            )

        profile_by_sku = {bundle.profile.sku_code: bundle.profile for bundle in bundles}
        feature_by_sku = {bundle.profile.sku_code: _claim_features(bundle) for bundle in bundles}
        candidates: list[M115SkuBattlefieldClaimCandidateRecord] = []
        layers: list[M115SkuClaimValueLayerRecord] = []
        breakdowns: list[M115SkuClaimValueEvidenceBreakdownRecord] = []
        summaries: list[M115SkuBattlefieldClaimValueSummaryRecord] = []
        review_issues: list[M115SkuClaimValueReviewIssueRecord] = []

        for bundle in bundles:
            if bundle.feature_view is None:
                review_issues.append(
                    _blocked_review_issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        bundle=bundle,
                        seed=seed,
                        rule_version=rule_version,
                        issue_type=M115ClaimValueReviewIssueType.MISSING_FEATURE_VIEW,
                        message_cn="M08 未生成 M11.5 卖点价值特征视图，本 SKU 暂不能做战场内卖点分层。",
                    )
                )
                continue
            if not bundle.battlefield_scores:
                review_issues.append(
                    _blocked_review_issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        bundle=bundle,
                        seed=seed,
                        rule_version=rule_version,
                        issue_type=M115ClaimValueReviewIssueType.MISSING_BATTLEFIELD_RESULT,
                        message_cn="M11 未生成价值战场结果，本 SKU 不能绕过战场直接做卖点分层。",
                    )
                )
                continue

            build_result = self._build_bundle_outputs(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                seed=seed,
                bundle=bundle,
                profile_by_sku=profile_by_sku,
                feature_by_sku=feature_by_sku,
            )
            candidates.extend(build_result["candidates"])
            layers.extend(build_result["layers"])
            breakdowns.extend(build_result["breakdowns"])
            summaries.extend(build_result["summaries"])
            review_issues.extend(build_result["review_issues"])

        candidate_write = self.repository.save_candidates(candidates)
        layer_write = self.repository.save_layers(layers)
        breakdown_write = self.repository.save_breakdowns(breakdowns)
        summary_write = self.repository.save_summaries(summaries)
        review_write = self.repository.save_review_issues(review_issues)

        created = (
            candidate_write.created_count
            + layer_write.created_count
            + breakdown_write.created_count
            + summary_write.created_count
            + review_write.created_count
        )
        updated = (
            candidate_write.updated_count
            + layer_write.updated_count
            + breakdown_write.updated_count
            + summary_write.updated_count
            + review_write.updated_count
        )
        reused = (
            candidate_write.reused_count
            + layer_write.reused_count
            + breakdown_write.reused_count
            + summary_write.reused_count
            + review_write.reused_count
        )
        layer_counts = Counter(str(row.layer) for row in layers)
        sample_counts = Counter(str(row.sample_sufficiency) for row in layers)
        warnings = []
        if review_issues:
            warnings.append(f"M11.5 生成 {len(review_issues)} 条复核问题，主要来自样本不足、卖点证据缺口或服务卖点边界。")
        status = Core3RunStatus.WARNING if review_issues else Core3RunStatus.SUCCESS
        return M115ServiceResult(
            status=status,
            input_count=len(bundles),
            candidates=tuple(candidates),
            layers=tuple(layers),
            breakdowns=tuple(breakdowns),
            summaries=tuple(summaries),
            review_issues=tuple(review_issues),
            warnings=warnings,
            created_output_count=created,
            updated_output_count=updated,
            reused_output_count=reused,
            summary={
                "batch_id": batch_id,
                "rule_version": rule_version,
                "claim_seed_version": seed.claim_seed_version,
                "battlefield_seed_version": seed.battlefield_seed_version,
                "seed_file_version": seed.file_version,
                "claim_seed_hash": seed.claim_seed_hash,
                "battlefield_seed_hash": seed.battlefield_seed_hash,
                "claim_seed_count": seed.claim_count,
                "battlefield_seed_count": seed.battlefield_count,
                "sku_count": len(bundles),
                "battlefield_scope_count": len({(row.sku_code, row.battlefield_code) for row in summaries}),
                "claim_candidate_count": len(candidates),
                "claim_value_layer_count": len(layers),
                "claim_value_evidence_breakdown_count": len(breakdowns),
                "battlefield_claim_value_summary_count": len(summaries),
                "claim_value_review_issue_count": len(review_issues),
                "layer_counts": dict(layer_counts),
                "sample_sufficiency_counts": dict(sample_counts),
                "created_output_count": created,
                "updated_output_count": updated,
                "reused_output_count": reused,
                "boundary_note": "M11.5 只在 M11 已给出的价值战场内做标准卖点价值分层，不生成候选 SKU、核心竞品、组件评分或高层报告。",
                "downstream_support": {
                    "M12": "消费战场内绩效、溢价、门槛和弱感知卖点做候选召回提示",
                    "M13": "消费卖点价值层级和指标快照做目标-候选 pair 评分",
                    "M14": "消费战场内卖点组合支持三槽位选择解释",
                    "M15": "消费业务解释和分域证据卡展示卖点价值",
                },
            },
        )

    def _build_bundle_outputs(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        seed: M115ClaimValueSeed,
        bundle: M115InputBundle,
        profile_by_sku: Mapping[str, entities.Core3SkuSignalProfile],
        feature_by_sku: Mapping[str, Mapping[str, ClaimFeature]],
    ) -> dict[str, list[Any]]:
        scoped_scores = _scoped_battlefields(bundle, feature_by_sku.get(bundle.profile.sku_code, {}), seed)
        candidates: list[M115SkuBattlefieldClaimCandidateRecord] = []
        layers: list[M115SkuClaimValueLayerRecord] = []
        breakdowns: list[M115SkuClaimValueEvidenceBreakdownRecord] = []
        summaries: list[M115SkuBattlefieldClaimValueSummaryRecord] = []
        review_issues: list[M115SkuClaimValueReviewIssueRecord] = []
        for score in scoped_scores:
            battlefield = seed.battlefields_by_code.get(score.battlefield_code)
            if battlefield is None:
                continue
            battlefield_candidates = _build_candidates(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                seed=seed,
                bundle=bundle,
                score=score,
                battlefield=battlefield,
                features=feature_by_sku.get(bundle.profile.sku_code, {}),
            )
            battlefield_layers: list[M115SkuClaimValueLayerRecord] = []
            for candidate in battlefield_candidates:
                claim = seed.claims_by_code[candidate.claim_code]
                feature = feature_by_sku.get(bundle.profile.sku_code, {}).get(candidate.claim_code)
                pool = _build_pool_metrics(
                    claim_code=candidate.claim_code,
                    bundle=bundle,
                    profile_by_sku=profile_by_sku,
                    feature_by_sku=feature_by_sku,
                )
                layer = _build_layer(
                    candidate=candidate,
                    claim=claim,
                    battlefield=battlefield,
                    score=score,
                    feature=feature,
                    pool=pool,
                    seed=seed,
                    bundle=bundle,
                    rule_version=rule_version,
                )
                layer_breakdowns = _build_breakdowns(layer=layer, claim=claim, feature=feature, pool=pool, bundle=bundle)
                layer_reviews = _build_review_issues(layer=layer, candidate=candidate, seed=seed, bundle=bundle)
                candidates.append(candidate)
                layers.append(layer)
                breakdowns.extend(layer_breakdowns)
                review_issues.extend(layer_reviews)
                battlefield_layers.append(layer)
            if battlefield_layers:
                summaries.append(
                    _build_summary(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        seed=seed,
                        bundle=bundle,
                        score=score,
                        battlefield=battlefield,
                        layers=battlefield_layers,
                    )
                )
        return {
            "candidates": candidates,
            "layers": layers,
            "breakdowns": breakdowns,
            "summaries": summaries,
            "review_issues": review_issues,
        }


def _scoped_battlefields(
    bundle: M115InputBundle,
    features: Mapping[str, ClaimFeature],
    seed: M115ClaimValueSeed,
) -> list[entities.Core3SkuBattlefieldScore]:
    active_claims = {code for code, feature in features.items() if feature.final_activation_score >= Decimal("0.3000")}
    result: list[entities.Core3SkuBattlefieldScore] = []
    for score in bundle.battlefield_scores:
        relation = str(score.relation_level)
        if relation in {M11BattlefieldRelationLevel.MAIN.value, M11BattlefieldRelationLevel.SECONDARY.value, M11BattlefieldRelationLevel.OPPORTUNITY.value}:
            result.append(score)
            continue
        if relation == M11BattlefieldRelationLevel.WEAK.value:
            core_claims = set(seed.battlefield_claim_codes.get(score.battlefield_code, ()))
            if active_claims & core_claims:
                result.append(score)
    return result


def _claim_features(bundle: M115InputBundle) -> dict[str, ClaimFeature]:
    payload = _feature_payload(bundle)
    summary = _dict(payload.get("claim_activation_summary")) or _dict(bundle.profile.claim_activation_summary_json)
    result: dict[str, ClaimFeature] = {}
    for item in summary.get("top_claims") or []:
        claim_code = str(item.get("claim_code_hint") or item.get("claim_code") or "")
        if not claim_code:
            continue
        result[claim_code] = ClaimFeature(
            claim_code=claim_code,
            claim_name=str(item.get("claim_name") or claim_code),
            claim_group=item.get("claim_group"),
            activation_level=str(item.get("activation_level") or "unknown"),
            activation_basis=str(item.get("activation_basis") or "unknown"),
            final_activation_score=_round4(_decimal(item.get("final_activation_score"))),
            perception_status=str(item.get("perception_status") or "unknown"),
            confidence=_round4(_decimal(item.get("confidence"))),
        )
    return result


def _build_candidates(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    seed: M115ClaimValueSeed,
    bundle: M115InputBundle,
    score: entities.Core3SkuBattlefieldScore,
    battlefield: Mapping[str, Any],
    features: Mapping[str, ClaimFeature],
) -> list[M115SkuBattlefieldClaimCandidateRecord]:
    battlefield_code = str(battlefield["battlefield_code"])
    core_claims = set(seed.battlefield_claim_codes.get(battlefield_code, ()))
    active_mapped = {
        claim_code
        for claim_code, feature in features.items()
        if feature.final_activation_score >= Decimal("0.2500") and battlefield_code in seed.mapped_battlefields_by_claim.get(claim_code, ())
    }
    claim_codes = sorted(core_claims | active_mapped, key=lambda code: seed.standard_claims.index(seed.claims_by_code[code]))
    candidates: list[M115SkuBattlefieldClaimCandidateRecord] = []
    for claim_code in claim_codes:
        claim = seed.claims_by_code[claim_code]
        feature = features.get(claim_code)
        sources: list[str] = []
        if claim_code in core_claims:
            sources.append(M115ClaimCandidateSource.BATTLEFIELD_CORE_CLAIM.value)
        if battlefield_code in seed.mapped_battlefields_by_claim.get(claim_code, ()):
            sources.append(M115ClaimCandidateSource.CLAIM_BATTLEFIELD_MAPPING.value)
        if feature is not None and feature.final_activation_score > 0:
            sources.append(M115ClaimCandidateSource.CLAIM_ACTIVATION.value)
            if "param" in feature.activation_basis:
                sources.append(M115ClaimCandidateSource.PARAM.value)
            if "comment" in feature.activation_basis or feature.perception_status == "validated":
                sources.append(M115ClaimCandidateSource.COMMENT.value)
            if claim.get("claim_group") == "service":
                sources.append(M115ClaimCandidateSource.SERVICE.value)
        sources = _dedupe(sources)
        initial_score = _clamp(
            max(
                Decimal("0.4800") if claim_code in core_claims else Decimal("0.0000"),
                feature.final_activation_score if feature is not None else Decimal("0.0000"),
            )
            + min(Decimal(len(sources)) * Decimal("0.0400"), Decimal("0.1600"))
        )
        risk_flags = []
        if claim.get("claim_group") == "service" and battlefield_code in PRODUCT_CORE_BATTLEFIELDS:
            risk_flags.append({"issue_type": M115ClaimValueReviewIssueType.SERVICE_MISUSE.value, "reason_cn": "服务类卖点不能增强产品核心战场。"})
        candidate_status = M115ClaimCandidateStatus.REVIEW_REQUIRED if risk_flags else M115ClaimCandidateStatus.ACTIVE
        evidence_ids = _dedupe([*getattr(score, "evidence_ids", []), *_profile_evidence_ids(bundle)])[:80]
        input_fingerprint = stable_hash(
            {
                "profile_hash": bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(bundle),
                "battlefield_score_hash": score.result_hash,
                "claim_code": claim_code,
                "sources": sources,
                "seed": seed.claim_seed_hash,
                "rule_version": rule_version,
            },
            version="m11_5_candidate_input_v1",
        )
        result_hash = stable_hash(
            {
                "sources": sources,
                "score": str(initial_score),
                "status": candidate_status.value,
                "risk": risk_flags,
            },
            version="m11_5_candidate_result_v1",
        )
        candidates.append(
            M115SkuBattlefieldClaimCandidateRecord(
                sku_battlefield_claim_candidate_id=_record_id("m115c", batch_id, bundle.profile.sku_code, battlefield_code, claim_code, seed.claim_seed_hash),
                project_id=bundle.profile.project_id,
                category_code=bundle.profile.category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                sku_signal_profile_id=bundle.profile.sku_signal_profile_id,
                sku_downstream_feature_view_id=bundle.feature_view.sku_downstream_feature_view_id if bundle.feature_view else None,
                sku_battlefield_score_id=score.sku_battlefield_score_id,
                sku_code=bundle.profile.sku_code,
                model_code=(bundle.profile.sku_master_json or {}).get("model_code"),
                model_name=bundle.profile.model_name,
                brand_name=bundle.profile.brand_name,
                battlefield_code=battlefield_code,
                battlefield_name_cn=str(battlefield.get("battlefield_name") or battlefield_code),
                battlefield_relation_level=str(score.relation_level),
                claim_code=claim_code,
                claim_name_cn=str(claim.get("claim_name") or claim_code),
                claim_group=claim.get("claim_group"),
                candidate_source_json=sources,
                candidate_source_count=len(sources),
                candidate_initial_score=initial_score,
                candidate_reason_cn=_candidate_reason(battlefield, claim, feature, sources),
                candidate_status=candidate_status,
                risk_flags_json=risk_flags,
                evidence_ids=evidence_ids,
                evidence_matrix_refs_json=_matrix_refs(bundle, ("claim", "market", "pool", "comment")),
                profile_hash=bundle.profile.profile_hash,
                feature_view_hash=_feature_view_hash(bundle),
                battlefield_score_fingerprint=bundle.battlefield_score_fingerprint,
                claim_seed_file_version=seed.file_version,
                claim_seed_hash=seed.claim_seed_hash,
                battlefield_seed_file_version=seed.file_version,
                battlefield_seed_hash=seed.battlefield_seed_hash,
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                result_hash=result_hash,
                processing_status="warning" if risk_flags else "success",
                review_required=bool(risk_flags),
                review_status="review_required" if risk_flags else "auto_pass",
                review_reason_json={"issues": risk_flags},
            )
        )
    return candidates


def _build_pool_metrics(
    *,
    claim_code: str,
    bundle: M115InputBundle,
    profile_by_sku: Mapping[str, entities.Core3SkuSignalProfile],
    feature_by_sku: Mapping[str, Mapping[str, ClaimFeature]],
) -> PoolMetrics:
    pool = _select_pool(bundle)
    pool_codes = tuple(str(code) for code in (pool.get("pool_sku_codes") if pool else (bundle.profile.sku_code,)) if code in profile_by_sku)
    with_codes = []
    without_codes = []
    for sku_code in pool_codes:
        feature = feature_by_sku.get(sku_code, {}).get(claim_code)
        if feature is not None and feature.final_activation_score >= Decimal("0.3500"):
            with_codes.append(sku_code)
        else:
            without_codes.append(sku_code)
    with_prices = [_decimal(_market(profile_by_sku[sku]).get("price_wavg")) for sku in with_codes]
    without_prices = [_decimal(_market(profile_by_sku[sku]).get("price_wavg")) for sku in without_codes]
    with_volume = [_decimal(_market(profile_by_sku[sku]).get("sales_volume_total")) for sku in with_codes]
    without_volume = [_decimal(_market(profile_by_sku[sku]).get("sales_volume_total")) for sku in without_codes]
    with_amount = [_decimal(_market(profile_by_sku[sku]).get("sales_amount_total")) for sku in with_codes]
    without_amount = [_decimal(_market(profile_by_sku[sku]).get("sales_amount_total")) for sku in without_codes]
    pool_count = len(pool_codes)
    with_count = len(with_codes)
    without_count = len(without_codes)
    sample = M115SampleSufficiency.INSUFFICIENT
    if pool_count >= 8 and with_count >= 3 and without_count >= 3:
        sample = M115SampleSufficiency.SUFFICIENT
    elif pool_count >= 3 and with_count >= 1 and without_count >= 1:
        sample = M115SampleSufficiency.LIMITED
    coverage = _round4(_decimal(with_count) / _decimal(pool_count)) if pool_count else None
    return PoolMetrics(
        pool_id=str(pool.get("pool_id")) if pool else None,
        pool_type=str(pool.get("pool_type")) if pool else None,
        pool_sku_codes=pool_codes,
        pool_sku_count=pool_count,
        with_claim_count=with_count,
        without_claim_count=without_count,
        coverage_rate=coverage,
        psi=_ratio_delta(with_prices, without_prices) if sample != M115SampleSufficiency.INSUFFICIENT else None,
        ssi=_ratio_delta(with_volume, without_volume) if sample != M115SampleSufficiency.INSUFFICIENT else None,
        sai=_ratio_delta(with_amount, without_amount) if sample != M115SampleSufficiency.INSUFFICIENT else None,
        sample_sufficiency=sample,
        sample_sufficiency_json={
            "pool_sku_count": pool_count,
            "with_claim_count": with_count,
            "without_claim_count": without_count,
            "sample_status": sample.value,
            "pool_sku_codes": list(pool_codes),
        },
    )


def _build_layer(
    *,
    candidate: M115SkuBattlefieldClaimCandidateRecord,
    claim: Mapping[str, Any],
    battlefield: Mapping[str, Any],
    score: entities.Core3SkuBattlefieldScore,
    feature: ClaimFeature | None,
    pool: PoolMetrics,
    seed: M115ClaimValueSeed,
    bundle: M115InputBundle,
    rule_version: str,
) -> M115SkuClaimValueLayerRecord:
    activation = feature.final_activation_score if feature else Decimal("0.0000")
    relevance_role = _relevance_role(candidate, claim)
    relevance_score = {
        M115BattlefieldRelevanceRole.CORE: Decimal("0.8500"),
        M115BattlefieldRelevanceRole.AUXILIARY: Decimal("0.6200"),
        M115BattlefieldRelevanceRole.SERVICE: Decimal("0.5200"),
        M115BattlefieldRelevanceRole.RISK: Decimal("0.2500"),
        M115BattlefieldRelevanceRole.NOT_APPLICABLE: Decimal("0.0000"),
    }[relevance_role]
    coverage_position = _coverage_position_score(pool.coverage_rate)
    price_score = _support_score_from_delta(pool.psi)
    sales_score = _support_score_from_delta(_max_delta(pool.ssi, pool.sai))
    cpi, positive, negative, neutral = _comment_metrics(feature)
    comment_score = _clamp(Decimal("0.5000") + cpi)
    risks = list(candidate.risk_flags_json)
    missing = []
    if pool.pool_sku_count < 3:
        risks.append({"issue_type": M115ClaimValueReviewIssueType.INSUFFICIENT_POOL.value, "reason_cn": "战场可比池样本不足，不能做强分层。"})
    if pool.with_claim_count < 1:
        risks.append({"issue_type": M115ClaimValueReviewIssueType.INSUFFICIENT_WITH_CLAIM.value, "reason_cn": "池内具备该卖点的样本不足。"})
    if pool.without_claim_count < 1:
        risks.append({"issue_type": M115ClaimValueReviewIssueType.INSUFFICIENT_WITHOUT_CLAIM.value, "reason_cn": "池内缺少不具备该卖点的对照样本。"})
    if feature is None or feature.activation_basis == "insufficient":
        missing.append({"signal": "claim_activation", "reason_cn": "该 SKU 没有稳定卖点激活。"})
    if feature is not None and "promo" not in feature.activation_basis:
        risks.append({"issue_type": M115ClaimValueReviewIssueType.PROMO_MISSING.value, "reason_cn": "结构化宣传证据不足，不能表达为宣传侧充分验证。"})
    if feature is None or feature.perception_status == "insufficient_comment":
        risks.append({"issue_type": M115ClaimValueReviewIssueType.COMMENT_MISSING.value, "reason_cn": "评论感知样本不足或未充分验证。"})
    risk_penalty = min(Decimal(len(risks)) * Decimal("0.0400"), Decimal("0.2200"))
    score_raw = (
        activation * Decimal("0.2500")
        + relevance_score * Decimal("0.2000")
        + coverage_position * Decimal("0.1500")
        + price_score * Decimal("0.1500")
        + sales_score * Decimal("0.1500")
        + comment_score * Decimal("0.1000")
        - risk_penalty
    )
    claim_value_score = _clamp(score_raw)
    layer = _classify_layer(
        activation=activation,
        relevance_role=relevance_role,
        pool=pool,
        psi=pool.psi,
        ssi=pool.ssi,
        sai=pool.sai,
        cpi=cpi,
        risk_flags=risks,
        claim_value_score=claim_value_score,
        coverage_rate=pool.coverage_rate,
    )
    confidence = _confidence(
        claim_value_score=claim_value_score,
        sample_sufficiency=pool.sample_sufficiency,
        feature=feature,
        risk_count=len(risks),
        evidence_ids=candidate.evidence_ids,
    )
    confidence_level = _confidence_level(confidence, layer)
    parts = _business_reason_parts(
        battlefield=battlefield,
        claim=claim,
        relevance_role=relevance_role,
        feature=feature,
        pool=pool,
        layer=layer,
        cpi=cpi,
        risks=risks,
    )
    layer_id = _record_id("m115l", candidate.batch_id, candidate.sku_code, candidate.battlefield_code, candidate.claim_code, seed.claim_seed_hash)
    result_hash = stable_hash(
        {
            "score": str(claim_value_score),
            "layer": layer.value,
            "confidence": str(confidence),
            "pool": pool.sample_sufficiency_json,
            "risks": risks,
        },
        version="m11_5_layer_result_v1",
    )
    return M115SkuClaimValueLayerRecord(
        sku_claim_value_layer_id=layer_id,
        sku_battlefield_claim_candidate_id=candidate.sku_battlefield_claim_candidate_id,
        sku_signal_profile_id=candidate.sku_signal_profile_id,
        sku_downstream_feature_view_id=candidate.sku_downstream_feature_view_id,
        sku_battlefield_score_id=candidate.sku_battlefield_score_id,
        project_id=candidate.project_id,
        category_code=candidate.category_code,
        batch_id=candidate.batch_id,
        run_id=candidate.run_id,
        module_run_id=candidate.module_run_id,
        sku_code=candidate.sku_code,
        model_code=candidate.model_code,
        model_name=candidate.model_name,
        brand_name=candidate.brand_name,
        battlefield_code=candidate.battlefield_code,
        battlefield_name_cn=candidate.battlefield_name_cn,
        battlefield_relation_level=candidate.battlefield_relation_level,
        claim_code=candidate.claim_code,
        claim_name_cn=candidate.claim_name_cn,
        claim_group=candidate.claim_group,
        claim_activation_score=activation,
        activation_basis_json={
            "activation_level": feature.activation_level if feature else "unknown",
            "activation_basis": feature.activation_basis if feature else "missing",
            "perception_status": feature.perception_status if feature else "missing",
            "confidence": float(feature.confidence) if feature else 0,
        },
        battlefield_relevance_role=relevance_role,
        comparable_pool_id=pool.pool_id,
        pool_type=pool.pool_type,
        pool_sku_count=pool.pool_sku_count,
        with_claim_count=pool.with_claim_count,
        without_claim_count=pool.without_claim_count,
        coverage_rate=pool.coverage_rate,
        coverage_position_score=coverage_position,
        psi=pool.psi,
        ssi=pool.ssi,
        sai=pool.sai,
        cpi=cpi,
        positive_mention_rate=positive,
        negative_mention_rate=negative,
        neutral_mention_rate=neutral,
        price_support_score=price_score,
        sales_support_score=sales_score,
        comment_perception_score=comment_score,
        risk_penalty=risk_penalty,
        claim_value_score=claim_value_score,
        layer=layer,
        layer_reason_json={
            "rule_version": rule_version,
            "coverage_rate": float(pool.coverage_rate) if pool.coverage_rate is not None else None,
            "psi": float(pool.psi) if pool.psi is not None else None,
            "ssi": float(pool.ssi) if pool.ssi is not None else None,
            "sai": float(pool.sai) if pool.sai is not None else None,
            "cpi": float(cpi),
            "risk_count": len(risks),
        },
        confidence=confidence,
        confidence_level=confidence_level,
        sample_sufficiency=pool.sample_sufficiency,
        sample_sufficiency_json=pool.sample_sufficiency_json,
        missing_signals_json=missing,
        risk_flags_json=risks,
        business_reason_cn=_compact_reason(parts),
        business_reason_parts_json=parts,
        next_module_payload_json={
            "source_module": "M11.5",
            "battlefield_code": candidate.battlefield_code,
            "claim_code": candidate.claim_code,
            "layer": layer.value,
            "claim_value_score": float(claim_value_score),
            "sample_sufficiency": pool.sample_sufficiency.value,
        },
        evidence_ids=candidate.evidence_ids,
        evidence_matrix_refs_json=candidate.evidence_matrix_refs_json,
        profile_hash=candidate.profile_hash,
        feature_view_hash=candidate.feature_view_hash,
        battlefield_score_fingerprint=candidate.battlefield_score_fingerprint,
        claim_seed_file_version=seed.file_version,
        claim_seed_hash=seed.claim_seed_hash,
        battlefield_seed_file_version=seed.file_version,
        battlefield_seed_hash=seed.battlefield_seed_hash,
        rule_version=rule_version,
        input_fingerprint=candidate.input_fingerprint,
        result_hash=result_hash,
        processing_status="warning" if risks else "success",
        review_required=bool(risks),
        review_status="review_required" if risks else "auto_pass",
        review_reason_json={"issues": risks},
    )


def _build_breakdowns(
    *,
    layer: M115SkuClaimValueLayerRecord,
    claim: Mapping[str, Any],
    feature: ClaimFeature | None,
    pool: PoolMetrics,
    bundle: M115InputBundle,
) -> list[M115SkuClaimValueEvidenceBreakdownRecord]:
    weights = {
        M115ClaimValueEvidenceDomain.ACTIVATION: Decimal("0.25"),
        M115ClaimValueEvidenceDomain.PARAM: Decimal("0.10"),
        M115ClaimValueEvidenceDomain.PROMO: Decimal("0.10"),
        M115ClaimValueEvidenceDomain.COMMENT: Decimal("0.10"),
        M115ClaimValueEvidenceDomain.PRICE: Decimal("0.15"),
        M115ClaimValueEvidenceDomain.SALES: Decimal("0.15"),
        M115ClaimValueEvidenceDomain.POOL: Decimal("0.07"),
        M115ClaimValueEvidenceDomain.MARKET: Decimal("0.03"),
        M115ClaimValueEvidenceDomain.SERVICE: Decimal("0.02"),
        M115ClaimValueEvidenceDomain.RISK: Decimal("0.03"),
        M115ClaimValueEvidenceDomain.SEED: Decimal("0.00"),
        M115ClaimValueEvidenceDomain.PROFILE: Decimal("0.00"),
    }
    rows: list[M115SkuClaimValueEvidenceBreakdownRecord] = []
    for domain in CORE3_M11_5_EVIDENCE_DOMAINS:
        score, level, summary, source_values, missing = _domain_evidence(domain, layer, claim, feature, pool, bundle)
        weight = weights[domain]
        result_hash = stable_hash(
            {
                "layer": layer.sku_claim_value_layer_id,
                "domain": domain.value,
                "score": str(score),
                "level": level.value,
                "summary": summary,
            },
            version="m11_5_breakdown_result_v1",
        )
        rows.append(
            M115SkuClaimValueEvidenceBreakdownRecord(
                sku_claim_value_evidence_breakdown_id=_record_id("m115b", layer.sku_claim_value_layer_id, domain.value),
                sku_claim_value_layer_id=layer.sku_claim_value_layer_id,
                project_id=layer.project_id,
                category_code=layer.category_code,
                batch_id=layer.batch_id,
                run_id=layer.run_id,
                module_run_id=layer.module_run_id,
                sku_code=layer.sku_code,
                model_code=layer.model_code,
                model_name=layer.model_name,
                brand_name=layer.brand_name,
                battlefield_code=layer.battlefield_code,
                battlefield_name_cn=layer.battlefield_name_cn,
                claim_code=layer.claim_code,
                claim_name_cn=layer.claim_name_cn,
                evidence_domain=domain,
                support_level=level,
                support_score=score,
                domain_weight=weight,
                weighted_contribution=_round4(score * weight),
                support_summary_cn=summary,
                source_signal_codes_json=_source_signal_codes(domain, claim),
                source_values_json=source_values,
                representative_evidence_ids=layer.evidence_ids[:20],
                evidence_matrix_refs_json=layer.evidence_matrix_refs_json,
                missing_reason_code=missing,
                risk_flags_json=layer.risk_flags_json if domain == M115ClaimValueEvidenceDomain.RISK else [],
                confidence=layer.confidence,
                profile_hash=layer.profile_hash,
                feature_view_hash=layer.feature_view_hash,
                battlefield_score_fingerprint=layer.battlefield_score_fingerprint,
                claim_seed_file_version=layer.claim_seed_file_version,
                claim_seed_hash=layer.claim_seed_hash,
                battlefield_seed_file_version=layer.battlefield_seed_file_version,
                battlefield_seed_hash=layer.battlefield_seed_hash,
                rule_version=layer.rule_version,
                input_fingerprint=layer.input_fingerprint,
                result_hash=result_hash,
            )
        )
    return rows


def _build_summary(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    seed: M115ClaimValueSeed,
    bundle: M115InputBundle,
    score: entities.Core3SkuBattlefieldScore,
    battlefield: Mapping[str, Any],
    layers: Sequence[M115SkuClaimValueLayerRecord],
) -> M115SkuBattlefieldClaimValueSummaryRecord:
    by_layer: dict[str, list[M115SkuClaimValueLayerRecord]] = defaultdict(list)
    for layer in sorted(layers, key=lambda item: (LAYER_ORDER.get(str(item.layer), 99), item.claim_value_score), reverse=False):
        by_layer[str(layer.layer)].append(layer)
    def pack(layer_name: str) -> list[dict[str, Any]]:
        return [_summary_item(item) for item in sorted(by_layer.get(layer_name, ()), key=lambda row: row.claim_value_score, reverse=True)]

    premium = pack(M115ClaimValueLayer.PREMIUM_TENDENCY.value)
    performance = pack(M115ClaimValueLayer.COMPETITIVE_PERFORMANCE.value)
    threshold = pack(M115ClaimValueLayer.BASIC_THRESHOLD.value)
    weak = pack(M115ClaimValueLayer.WEAK_PERCEPTION.value)
    insufficient = pack(M115ClaimValueLayer.INSUFFICIENT_SAMPLE.value)
    not_applicable = pack(M115ClaimValueLayer.NOT_APPLICABLE.value)
    focus = [*premium, *performance, *threshold][:8]
    confidence = _round4(_average([item.confidence for item in layers]))
    evidence_ids = _dedupe([eid for item in layers for eid in item.evidence_ids])[:120]
    risk_flags = _dedupe_dicts([risk for item in layers for risk in item.risk_flags_json])
    profile_cn = _summary_cn(battlefield, premium, performance, threshold, weak, insufficient)
    result_hash = stable_hash(
        {
            "premium": premium,
            "performance": performance,
            "threshold": threshold,
            "weak": weak,
            "insufficient": insufficient,
            "focus": focus,
            "confidence": str(confidence),
        },
        version="m11_5_summary_result_v1",
    )
    return M115SkuBattlefieldClaimValueSummaryRecord(
        sku_battlefield_claim_value_summary_id=_record_id("m115s", batch_id, bundle.profile.sku_code, score.battlefield_code, seed.claim_seed_hash),
        sku_signal_profile_id=bundle.profile.sku_signal_profile_id,
        sku_downstream_feature_view_id=bundle.feature_view.sku_downstream_feature_view_id if bundle.feature_view else None,
        sku_battlefield_score_id=score.sku_battlefield_score_id,
        project_id=bundle.profile.project_id,
        category_code=bundle.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_code=bundle.profile.sku_code,
        model_code=(bundle.profile.sku_master_json or {}).get("model_code"),
        model_name=bundle.profile.model_name,
        brand_name=bundle.profile.brand_name,
        battlefield_code=score.battlefield_code,
        battlefield_name_cn=str(battlefield.get("battlefield_name") or score.battlefield_code),
        battlefield_relation_level=str(score.relation_level),
        premium_claims_json=premium,
        performance_claims_json=performance,
        threshold_claims_json=threshold,
        weak_claims_json=weak,
        insufficient_claims_json=insufficient,
        not_applicable_claims_json=not_applicable,
        claim_value_profile_cn=profile_cn,
        comparison_focus_claims_json=focus,
        summary_confidence=confidence,
        summary_risk_flags_json=risk_flags,
        claim_value_layer_refs_json=[
            {
                "sku_claim_value_layer_id": item.sku_claim_value_layer_id,
                "claim_code": item.claim_code,
                "layer": item.layer,
                "claim_value_score": float(item.claim_value_score),
                "result_hash": item.result_hash,
            }
            for item in layers
        ],
        evidence_ids=evidence_ids,
        profile_hash=bundle.profile.profile_hash,
        feature_view_hash=_feature_view_hash(bundle),
        battlefield_score_fingerprint=bundle.battlefield_score_fingerprint,
        claim_seed_file_version=seed.file_version,
        claim_seed_hash=seed.claim_seed_hash,
        battlefield_seed_file_version=seed.file_version,
        battlefield_seed_hash=seed.battlefield_seed_hash,
        rule_version=rule_version,
        input_fingerprint=stable_hash(
            {
                "profile_hash": bundle.profile.profile_hash,
                "feature_view_hash": _feature_view_hash(bundle),
                "battlefield_score_hash": score.result_hash,
                "layer_hashes": [item.result_hash for item in layers],
                "rule_version": rule_version,
            },
            version="m11_5_summary_input_v1",
        ),
        result_hash=result_hash,
        processing_status="warning" if risk_flags else "success",
        review_required=bool(risk_flags),
        review_status="review_required" if risk_flags else "auto_pass",
        review_reason_json={"issues": risk_flags},
    )


def _build_review_issues(
    *,
    layer: M115SkuClaimValueLayerRecord,
    candidate: M115SkuBattlefieldClaimCandidateRecord,
    seed: M115ClaimValueSeed,
    bundle: M115InputBundle,
) -> list[M115SkuClaimValueReviewIssueRecord]:
    issues: list[M115SkuClaimValueReviewIssueRecord] = []
    seen_issue_types: set[str] = set()
    for risk in layer.risk_flags_json:
        if isinstance(risk, str):
            issue_type = risk
            reason = risk
        else:
            issue_type = str(risk.get("issue_type") or "upstream_review")
            reason = str(risk.get("reason_cn") or issue_type)
        if issue_type in seen_issue_types:
            continue
        seen_issue_types.add(issue_type)
        input_fingerprint = stable_hash(
            {"layer": layer.sku_claim_value_layer_id, "issue_type": issue_type, "profile_hash": layer.profile_hash},
            version="m11_5_review_input_v1",
        )
        issues.append(
            M115SkuClaimValueReviewIssueRecord(
                sku_claim_value_review_issue_id=_record_id(
                    "m115r",
                    layer.batch_id,
                    layer.sku_code,
                    layer.battlefield_code,
                    layer.claim_code,
                    issue_type,
                    input_fingerprint,
                ),
                related_layer_id=layer.sku_claim_value_layer_id,
                related_candidate_id=candidate.sku_battlefield_claim_candidate_id,
                related_battlefield_score_id=layer.sku_battlefield_score_id,
                project_id=layer.project_id,
                category_code=layer.category_code,
                batch_id=layer.batch_id,
                run_id=layer.run_id,
                module_run_id=layer.module_run_id,
                sku_code=layer.sku_code,
                model_code=layer.model_code,
                model_name=layer.model_name,
                brand_name=layer.brand_name,
                battlefield_code=layer.battlefield_code,
                battlefield_name_cn=layer.battlefield_name_cn,
                claim_code=layer.claim_code,
                claim_name_cn=layer.claim_name_cn,
                issue_type=issue_type,
                issue_level="warning",
                issue_message_cn=reason,
                issue_context_json={"layer": layer.layer, "claim_value_score": float(layer.claim_value_score)},
                evidence_ids=layer.evidence_ids,
                profile_hash=layer.profile_hash,
                feature_view_hash=layer.feature_view_hash,
                battlefield_score_fingerprint=layer.battlefield_score_fingerprint,
                claim_seed_file_version=seed.file_version,
                claim_seed_hash=seed.claim_seed_hash,
                battlefield_seed_file_version=seed.file_version,
                battlefield_seed_hash=seed.battlefield_seed_hash,
                rule_version=layer.rule_version,
                input_fingerprint=input_fingerprint,
                result_hash=stable_hash(
                    {"message": reason, "layer": layer.layer, "issue_type": issue_type},
                    version="m11_5_review_result_v1",
                ),
            )
        )
    return issues


def _blocked_review_issue(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    bundle: M115InputBundle,
    seed: M115ClaimValueSeed,
    rule_version: str,
    issue_type: M115ClaimValueReviewIssueType,
    message_cn: str,
) -> M115SkuClaimValueReviewIssueRecord:
    fingerprint = stable_hash(
        {"profile_hash": bundle.profile.profile_hash, "issue_type": issue_type.value, "rule_version": rule_version},
        version="m11_5_blocked_review_input_v1",
    )
    return M115SkuClaimValueReviewIssueRecord(
        sku_claim_value_review_issue_id=_record_id("m115r", batch_id, bundle.profile.sku_code, issue_type.value),
        project_id=bundle.profile.project_id,
        category_code=bundle.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_code=bundle.profile.sku_code,
        model_code=(bundle.profile.sku_master_json or {}).get("model_code"),
        model_name=bundle.profile.model_name,
        brand_name=bundle.profile.brand_name,
        issue_type=issue_type.value,
        issue_level="blocker",
        issue_message_cn=message_cn,
        issue_context_json={"source_module": "M11.5"},
        profile_hash=bundle.profile.profile_hash,
        feature_view_hash=_feature_view_hash(bundle),
        battlefield_score_fingerprint=bundle.battlefield_score_fingerprint,
        claim_seed_file_version=seed.file_version,
        claim_seed_hash=seed.claim_seed_hash,
        battlefield_seed_file_version=seed.file_version,
        battlefield_seed_hash=seed.battlefield_seed_hash,
        rule_version=rule_version,
        input_fingerprint=fingerprint,
        result_hash=stable_hash({"message": message_cn, "issue_type": issue_type.value}, version="m11_5_blocked_review_result_v1"),
        processing_status="blocked",
    )


def _classify_layer(
    *,
    activation: Decimal,
    relevance_role: M115BattlefieldRelevanceRole,
    pool: PoolMetrics,
    psi: Decimal | None,
    ssi: Decimal | None,
    sai: Decimal | None,
    cpi: Decimal,
    risk_flags: Sequence[Any],
    claim_value_score: Decimal,
    coverage_rate: Decimal | None,
) -> M115ClaimValueLayer:
    if relevance_role == M115BattlefieldRelevanceRole.NOT_APPLICABLE:
        return M115ClaimValueLayer.NOT_APPLICABLE
    if relevance_role == M115BattlefieldRelevanceRole.RISK:
        return M115ClaimValueLayer.WEAK_PERCEPTION
    if pool.sample_sufficiency == M115SampleSufficiency.INSUFFICIENT and activation < Decimal("0.5000"):
        return M115ClaimValueLayer.INSUFFICIENT_SAMPLE
    if (
        pool.sample_sufficiency == M115SampleSufficiency.SUFFICIENT
        and (psi or Decimal("0")) >= Decimal("0.0500")
        and activation >= Decimal("0.6500")
        and (ssi is None or ssi >= Decimal("-0.1000"))
        and claim_value_score >= Decimal("0.6800")
    ):
        return M115ClaimValueLayer.PREMIUM_TENDENCY
    if coverage_rate is not None and coverage_rate >= Decimal("0.7000") and _max_delta(psi, ssi, sai) < Decimal("0.0500"):
        return M115ClaimValueLayer.BASIC_THRESHOLD
    if activation >= Decimal("0.5500") and claim_value_score >= Decimal("0.5600"):
        return M115ClaimValueLayer.COMPETITIVE_PERFORMANCE
    if activation >= Decimal("0.3500") and cpi >= Decimal("0.0500"):
        return M115ClaimValueLayer.WEAK_PERCEPTION
    if pool.sample_sufficiency == M115SampleSufficiency.INSUFFICIENT:
        return M115ClaimValueLayer.INSUFFICIENT_SAMPLE
    return M115ClaimValueLayer.WEAK_PERCEPTION


def _relevance_role(candidate: M115SkuBattlefieldClaimCandidateRecord, claim: Mapping[str, Any]) -> M115BattlefieldRelevanceRole:
    if claim.get("claim_group") == "service" and candidate.battlefield_code not in SERVICE_BATTLEFIELDS:
        return M115BattlefieldRelevanceRole.RISK
    if M115ClaimCandidateSource.BATTLEFIELD_CORE_CLAIM.value in candidate.candidate_source_json:
        return M115BattlefieldRelevanceRole.CORE
    if claim.get("claim_group") == "service":
        return M115BattlefieldRelevanceRole.SERVICE
    if M115ClaimCandidateSource.CLAIM_BATTLEFIELD_MAPPING.value in candidate.candidate_source_json:
        return M115BattlefieldRelevanceRole.AUXILIARY
    return M115BattlefieldRelevanceRole.NOT_APPLICABLE


def _select_pool(bundle: M115InputBundle) -> dict[str, Any]:
    summary = _dict(bundle.profile.comparable_pool_summary_json)
    items = list(summary.get("pool_items") or [])
    if not items:
        return {}
    rank = {"size_price_band": 5, "same_size": 4, "platform_overlap": 3, "market_active": 2, "same_price_band": 1}
    status_rank = {"sufficient": 3, "limited": 2, "insufficient": 1}
    return max(
        items,
        key=lambda item: (
            status_rank.get(str(item.get("sample_status")), 0),
            rank.get(str(item.get("pool_type")), 0),
            int(item.get("pool_sku_count") or 0),
        ),
    )


def _candidate_reason(battlefield: Mapping[str, Any], claim: Mapping[str, Any], feature: ClaimFeature | None, sources: Sequence[str]) -> str:
    source_cn = []
    if M115ClaimCandidateSource.BATTLEFIELD_CORE_CLAIM.value in sources:
        source_cn.append("战场核心卖点")
    if M115ClaimCandidateSource.CLAIM_ACTIVATION.value in sources:
        source_cn.append("SKU 已激活")
    if M115ClaimCandidateSource.PARAM.value in sources:
        source_cn.append("参数支撑")
    if M115ClaimCandidateSource.COMMENT.value in sources:
        source_cn.append("评论感知")
    basis = "、".join(source_cn) if source_cn else "seed 映射"
    activation = f"，当前激活分 {feature.final_activation_score:.2f}" if feature else "，当前未形成稳定激活"
    return f"在「{battlefield.get('battlefield_name')}」中，{claim.get('claim_name')}来自{basis}{activation}，需要进入战场内价值分层。"


def _business_reason_parts(
    *,
    battlefield: Mapping[str, Any],
    claim: Mapping[str, Any],
    relevance_role: M115BattlefieldRelevanceRole,
    feature: ClaimFeature | None,
    pool: PoolMetrics,
    layer: M115ClaimValueLayer,
    cpi: Decimal,
    risks: Sequence[Any],
) -> dict[str, str]:
    role_cn = {
        M115BattlefieldRelevanceRole.CORE: "核心卖点",
        M115BattlefieldRelevanceRole.AUXILIARY: "辅助卖点",
        M115BattlefieldRelevanceRole.SERVICE: "服务侧卖点",
        M115BattlefieldRelevanceRole.RISK: "边界风险卖点",
        M115BattlefieldRelevanceRole.NOT_APPLICABLE: "不适用卖点",
    }[relevance_role]
    layer_cn = _layer_cn(layer)
    return {
        "battlefield_relevance_cn": f"战场相关性：{claim.get('claim_name')}在「{battlefield.get('battlefield_name')}」中属于{role_cn}。",
        "activation_basis_cn": f"激活依据：{_activation_cn(feature)}。",
        "pool_status_cn": f"可比池表现：池内 {pool.pool_sku_count} 个 SKU，具备该卖点 {pool.with_claim_count} 个，样本状态为{_sample_cn(pool.sample_sufficiency)}。",
        "price_support_cn": f"价格支撑：{_delta_cn(pool.psi, '价格')}。",
        "sales_support_cn": f"销量支撑：{_delta_cn(_max_delta(pool.ssi, pool.sai), '销量/销额')}。",
        "comment_perception_cn": f"评论感知：CPI {cpi:.2f}，{_comment_cn(feature)}。",
        "review_points_cn": f"待复核点：{_risk_cn(risks)}。",
        "layer_cn": f"分层结论：{layer_cn}。",
    }


def _compact_reason(parts: Mapping[str, str]) -> str:
    return " ".join(
        [
            parts["battlefield_relevance_cn"],
            parts["activation_basis_cn"],
            parts["pool_status_cn"],
            parts["layer_cn"],
            parts["review_points_cn"],
        ]
    )


def _domain_evidence(
    domain: M115ClaimValueEvidenceDomain,
    layer: M115SkuClaimValueLayerRecord,
    claim: Mapping[str, Any],
    feature: ClaimFeature | None,
    pool: PoolMetrics,
    bundle: M115InputBundle,
) -> tuple[Decimal, M115ClaimValueSupportLevel, str, dict[str, Any], str | None]:
    if domain == M115ClaimValueEvidenceDomain.ACTIVATION:
        score = layer.claim_activation_score
        return score, _support_level(score), _activation_cn(feature), layer.activation_basis_json, None if score > 0 else "missing_claim_activation"
    if domain == M115ClaimValueEvidenceDomain.PARAM:
        has_param = "param" in (feature.activation_basis if feature else "")
        score = layer.claim_activation_score if has_param else Decimal("0.0000")
        return score, _support_level(score), "参数侧有支撑。" if has_param else "参数侧未形成稳定支撑。", {"supporting_param_codes": claim.get("supporting_param_codes") or []}, None if has_param else "param_missing"
    if domain == M115ClaimValueEvidenceDomain.PROMO:
        has_promo = "promo" in (feature.activation_basis if feature else "")
        score = layer.claim_activation_score if has_promo else Decimal("0.0000")
        return score, _support_level(score), "宣传侧有结构化或文本支撑。" if has_promo else "宣传侧证据不足，不能当作宣传卖点已充分验证。", {}, None if has_promo else "promo_missing"
    if domain == M115ClaimValueEvidenceDomain.COMMENT:
        score = layer.comment_perception_score
        return score, _support_level(score), _comment_cn(feature), {"cpi": float(layer.cpi or 0)}, None if feature and feature.perception_status == "validated" else "comment_missing"
    if domain == M115ClaimValueEvidenceDomain.PRICE:
        score = layer.price_support_score
        return score, _support_level(score), _delta_cn(pool.psi, "价格"), {"psi": float(pool.psi) if pool.psi is not None else None}, None if pool.psi is not None else "price_sample_missing"
    if domain == M115ClaimValueEvidenceDomain.SALES:
        score = layer.sales_support_score
        return score, _support_level(score), _delta_cn(_max_delta(pool.ssi, pool.sai), "销量/销额"), {"ssi": float(pool.ssi) if pool.ssi is not None else None, "sai": float(pool.sai) if pool.sai is not None else None}, None if pool.ssi is not None or pool.sai is not None else "sales_sample_missing"
    if domain == M115ClaimValueEvidenceDomain.POOL:
        sample_value = _enum_value(layer.sample_sufficiency)
        score = {
            M115SampleSufficiency.SUFFICIENT.value: Decimal("0.9000"),
            M115SampleSufficiency.LIMITED.value: Decimal("0.5500"),
            M115SampleSufficiency.INSUFFICIENT.value: Decimal("0.2000"),
            M115SampleSufficiency.UNKNOWN.value: Decimal("0.0000"),
        }.get(sample_value, Decimal("0.0000"))
        return score, _support_level(score), f"可比池包含 {pool.pool_sku_count} 个 SKU，样本状态为{_sample_cn(pool.sample_sufficiency)}。", pool.sample_sufficiency_json, None if score >= Decimal("0.5") else "insufficient_pool"
    if domain == M115ClaimValueEvidenceDomain.MARKET:
        market = _market(bundle.profile)
        score = _decimal(market.get("market_confidence"))
        return score, _support_level(score), "市场画像提供价格、销量和渠道参考。", market, None if market else "market_missing"
    if domain == M115ClaimValueEvidenceDomain.SERVICE:
        is_service = claim.get("claim_group") == "service"
        score = layer.claim_activation_score if is_service else Decimal("0.0000")
        return score, _support_level(score) if is_service else M115ClaimValueSupportLevel.NOT_APPLICABLE, "服务侧卖点只进入服务保障或家居美学语境。" if is_service else "非服务卖点，不使用服务域增强。", {}, None
    if domain == M115ClaimValueEvidenceDomain.RISK:
        score = Decimal("1.0000") - min(Decimal(len(layer.risk_flags_json)) * Decimal("0.1500"), Decimal("1.0000"))
        level = M115ClaimValueSupportLevel.WEAK if layer.risk_flags_json else M115ClaimValueSupportLevel.STRONG
        return score, level, _risk_cn(layer.risk_flags_json), {"risks": layer.risk_flags_json}, None
    if domain == M115ClaimValueEvidenceDomain.SEED:
        return Decimal("1.0000"), M115ClaimValueSupportLevel.STRONG, "标准卖点和战场映射来自 TV MVP seed，本记录不预置 SKU 结论。", {"mapped_battlefield_codes": claim.get("mapped_battlefield_codes") or []}, None
    return layer.confidence, _support_level(layer.confidence), "SKU 综合画像提供统一输入和证据索引。", {"profile_hash": layer.profile_hash}, None


def _source_signal_codes(domain: M115ClaimValueEvidenceDomain, claim: Mapping[str, Any]) -> list[str]:
    if domain == M115ClaimValueEvidenceDomain.PARAM:
        return [str(item) for item in claim.get("supporting_param_codes") or []]
    if domain == M115ClaimValueEvidenceDomain.COMMENT:
        return [str(item) for item in claim.get("comment_topic_codes") or []]
    if domain == M115ClaimValueEvidenceDomain.SEED:
        return [str(item) for item in claim.get("mapped_battlefield_codes") or []]
    return []


def _summary_item(layer: M115SkuClaimValueLayerRecord) -> dict[str, Any]:
    return {
        "claim_code": layer.claim_code,
        "claim_name_cn": layer.claim_name_cn,
        "claim_group": layer.claim_group,
        "layer": _enum_value(layer.layer),
        "claim_value_score": float(layer.claim_value_score),
        "confidence": float(layer.confidence),
        "sample_sufficiency": _enum_value(layer.sample_sufficiency),
        "reason_cn": layer.business_reason_cn,
    }


def _summary_cn(
    battlefield: Mapping[str, Any],
    premium: Sequence[Mapping[str, Any]],
    performance: Sequence[Mapping[str, Any]],
    threshold: Sequence[Mapping[str, Any]],
    weak: Sequence[Mapping[str, Any]],
    insufficient: Sequence[Mapping[str, Any]],
) -> str:
    battlefield_name = str(battlefield.get("battlefield_name") or "该战场")
    if premium:
        return f"在「{battlefield_name}」中，{_claim_names(premium)}具备溢价倾向，应作为高端对比重点。"
    if performance:
        return f"在「{battlefield_name}」中，{_claim_names(performance)}形成竞争绩效，是后续竞品对打的主要卖点。"
    if threshold:
        return f"在「{battlefield_name}」中，{_claim_names(threshold)}更像基础门槛，后续要比较价格和销量压力。"
    if weak:
        return f"在「{battlefield_name}」中，{_claim_names(weak)}已有线索但感知偏弱，需要谨慎用于竞品解释。"
    return f"在「{battlefield_name}」中，当前卖点样本不足，后续只能作为弱召回或复核线索。"


def _claim_names(items: Sequence[Mapping[str, Any]]) -> str:
    return "、".join(str(item.get("claim_name_cn") or item.get("claim_code")) for item in items[:4])


def _feature_payload(bundle: M115InputBundle) -> dict[str, Any]:
    if bundle.feature_view is None:
        return {}
    return _dict(bundle.feature_view.feature_payload_json)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _feature_view_hash(bundle: M115InputBundle) -> str:
    return bundle.feature_view.view_hash if bundle.feature_view is not None else "missing_feature_view"


def _profile_evidence_ids(bundle: M115InputBundle) -> list[str]:
    return [str(item) for item in getattr(bundle.profile, "representative_evidence_ids", []) or []]


def _matrix_refs(bundle: M115InputBundle, domains: Sequence[str]) -> list[dict[str, Any]]:
    domain_set = set(domains)
    return [
        {
            "domain": row.domain,
            "sub_domain": row.sub_domain,
            "evidence_count": row.evidence_count,
            "matrix_id": row.sku_signal_evidence_matrix_id,
        }
        for row in bundle.evidence_matrices
        if row.domain in domain_set
    ][:30]


def _market(profile: entities.Core3SkuSignalProfile) -> dict[str, Any]:
    return _dict(profile.market_summary_json)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _round4(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, low: Decimal = Decimal("0.0000"), high: Decimal = Decimal("1.0000")) -> Decimal:
    return _round4(max(low, min(high, value)))


def _average(values: Sequence[Decimal]) -> Decimal:
    values = [value for value in values if value is not None]
    if not values:
        return Decimal("0.0000")
    return _round4(sum(values, Decimal("0")) / Decimal(len(values)))


def _ratio_delta(left: Sequence[Decimal], right: Sequence[Decimal]) -> Decimal | None:
    left = [item for item in left if item > 0]
    right = [item for item in right if item > 0]
    if not left or not right:
        return None
    return _round4(_decimal(median(left)) / _decimal(median(right)) - Decimal("1"))


def _max_delta(*values: Decimal | None) -> Decimal:
    return max((value for value in values if value is not None), default=Decimal("0"))


def _support_score_from_delta(value: Decimal | None) -> Decimal:
    if value is None:
        return Decimal("0.4000")
    return _clamp(Decimal("0.5000") + value)


def _coverage_position_score(coverage: Decimal | None) -> Decimal:
    if coverage is None:
        return Decimal("0.0000")
    if coverage >= Decimal("0.7000"):
        return Decimal("0.6500")
    if coverage >= Decimal("0.2000"):
        return Decimal("0.8000")
    if coverage > Decimal("0.0000"):
        return Decimal("0.4500")
    return Decimal("0.0000")


def _comment_metrics(feature: ClaimFeature | None) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    if feature is None:
        return Decimal("0.0000"), Decimal("0.0000"), Decimal("0.0000"), Decimal("0.0000")
    if feature.perception_status == "validated":
        positive = min(Decimal("0.3000"), feature.confidence * Decimal("0.2500"))
        negative = Decimal("0.0000")
    elif feature.perception_status == "weakened":
        positive = Decimal("0.0000")
        negative = Decimal("0.1500")
    else:
        positive = Decimal("0.0500")
        negative = Decimal("0.0000")
    neutral = max(Decimal("0.0000"), Decimal("1.0000") - positive - negative)
    return _round4(positive - negative), _round4(positive), _round4(negative), _round4(neutral)


def _confidence(
    *,
    claim_value_score: Decimal,
    sample_sufficiency: M115SampleSufficiency,
    feature: ClaimFeature | None,
    risk_count: int,
    evidence_ids: Sequence[str],
) -> Decimal:
    sample_score = {
        M115SampleSufficiency.SUFFICIENT: Decimal("0.9000"),
        M115SampleSufficiency.LIMITED: Decimal("0.6200"),
        M115SampleSufficiency.INSUFFICIENT: Decimal("0.3500"),
        M115SampleSufficiency.UNKNOWN: Decimal("0.2000"),
    }[sample_sufficiency]
    feature_conf = feature.confidence if feature else Decimal("0.2000")
    evidence_score = Decimal("0.7500") if evidence_ids else Decimal("0.2500")
    risk_penalty = min(Decimal(risk_count) * Decimal("0.0500"), Decimal("0.2500"))
    return _clamp(claim_value_score * Decimal("0.30") + sample_score * Decimal("0.25") + evidence_score * Decimal("0.20") + feature_conf * Decimal("0.25") - risk_penalty)


def _confidence_level(confidence: Decimal, layer: M115ClaimValueLayer) -> Core3ConfidenceLevel:
    if layer == M115ClaimValueLayer.BLOCKED or confidence < Decimal("0.3500"):
        return Core3ConfidenceLevel.UNKNOWN
    if confidence >= Decimal("0.8000"):
        return Core3ConfidenceLevel.HIGH
    if confidence >= Decimal("0.6000"):
        return Core3ConfidenceLevel.MEDIUM
    return Core3ConfidenceLevel.LOW


def _support_level(score: Decimal) -> M115ClaimValueSupportLevel:
    if score >= Decimal("0.7500"):
        return M115ClaimValueSupportLevel.STRONG
    if score >= Decimal("0.5000"):
        return M115ClaimValueSupportLevel.MEDIUM
    if score > Decimal("0.0000"):
        return M115ClaimValueSupportLevel.WEAK
    return M115ClaimValueSupportLevel.MISSING


def _layer_cn(layer: M115ClaimValueLayer) -> str:
    return {
        M115ClaimValueLayer.BASIC_THRESHOLD: "基础门槛",
        M115ClaimValueLayer.COMPETITIVE_PERFORMANCE: "竞争绩效",
        M115ClaimValueLayer.PREMIUM_TENDENCY: "溢价倾向",
        M115ClaimValueLayer.WEAK_PERCEPTION: "弱感知",
        M115ClaimValueLayer.INSUFFICIENT_SAMPLE: "样本不足",
        M115ClaimValueLayer.NOT_APPLICABLE: "不适用",
        M115ClaimValueLayer.BLOCKED: "输入阻塞",
    }[layer]


def _sample_cn(sample: M115SampleSufficiency) -> str:
    return {
        M115SampleSufficiency.SUFFICIENT: "样本充分",
        M115SampleSufficiency.LIMITED: "样本有限",
        M115SampleSufficiency.INSUFFICIENT: "样本不足",
        M115SampleSufficiency.UNKNOWN: "样本未知",
    }[sample]


def _activation_cn(feature: ClaimFeature | None) -> str:
    if feature is None:
        return "没有稳定卖点激活，只能作为 seed 或弱线索处理"
    return f"{feature.claim_name} 激活分 {feature.final_activation_score:.2f}，依据为 {feature.activation_basis}，评论状态为 {feature.perception_status}"


def _delta_cn(value: Decimal | None, name: str) -> str:
    if value is None:
        return f"{name}样本不足，暂不做强判断"
    if value >= Decimal("0.0500"):
        return f"{name}方向为正，但只表示相关性"
    if value <= Decimal("-0.0500"):
        return f"{name}方向偏弱，需要结合定位和样本复核"
    return f"{name}未体现明显差异"


def _comment_cn(feature: ClaimFeature | None) -> str:
    if feature is None:
        return "评论没有形成该卖点的稳定感知"
    if feature.perception_status == "validated":
        return "评论感知有正向验证"
    if feature.perception_status == "insufficient_comment":
        return "评论样本不足，不能强判用户感知"
    return f"评论状态为{feature.perception_status}"


def _risk_cn(risks: Sequence[Any]) -> str:
    if not risks:
        return "暂无关键复核点"
    reasons = []
    for risk in risks[:4]:
        if isinstance(risk, str):
            reasons.append(risk)
        else:
            reasons.append(str(risk.get("reason_cn") or risk.get("issue_type") or "需复核"))
    return "；".join(reasons)


def _dedupe(values: Sequence[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _dedupe_dicts(values: Sequence[Any]) -> list[Any]:
    seen = set()
    result = []
    for value in values:
        key = stable_hash(value, version="m11_5_dedupe_v1")
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _record_id(prefix: str, *parts: object) -> str:
    return stable_hash([str(part) for part in parts], version=f"{prefix}_id_v1").replace("sha256:", f"{prefix}_", 1)[:120]
