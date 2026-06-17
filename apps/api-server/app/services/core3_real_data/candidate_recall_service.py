"""M12 candidate recall service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.candidate_recall_repositories import CandidateRecallRepository, M12SkuBundle
from app.services.core3_real_data.candidate_recall_schemas import (
    M12BuildArtifacts,
    M12CandidateFeatureSnapshotRecord,
    M12CandidatePoolRecord,
    M12CandidateRecallReasonRecord,
    M12CandidateRecallReviewIssueRecord,
    M12CandidateRecallRunRecord,
    M12ServiceResult,
)
from app.services.core3_real_data.constants import (
    CORE3_M08_FEATURE_VERSION,
    CORE3_M11_5_RULE_VERSION,
    CORE3_M11_RULE_VERSION,
    CORE3_M12_RULE_VERSION,
    CORE3_M12_RECALL_SOURCES,
    CORE3_M12_MODULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09_RULE_VERSION,
    CORE3_M10_RULE_VERSION,
    Core3RunStatus,
    M11BattlefieldRelationLevel,
    M12PriceRelation,
    M12RecallSource,
    M12RecallStatus,
    M12RecallStrength,
    M12RelationType,
    M12ReviewIssueType,
    M12SampleStatus,
    M12SizeRelation,
    M12SupportLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash


BOUNDARY_NOTE_CN = "M12 只生成可解释候选池、入池理由和 M13 可消费快照，不生成最终竞品排序、不选择核心三竞品、不生成高层报告。"


@dataclass(frozen=True)
class _ReasonDraft:
    source: M12RecallSource
    relation_type: M12RelationType
    reason_code: str
    support_score: Decimal
    confidence: Decimal
    summary_cn: str
    payload: dict[str, Any]
    evidence_ids: tuple[str, ...] = ()
    risk_flags: tuple[dict[str, Any] | str, ...] = ()


@dataclass(frozen=True)
class _PairContext:
    target: M12SkuBundle
    candidate: M12SkuBundle
    target_market: entities.Core3SkuMarketProfile | None
    candidate_market: entities.Core3SkuMarketProfile | None
    pool_member: entities.Core3MarketPoolMember | None
    price_relation: M12PriceRelation
    size_relation: M12SizeRelation
    sample_status: M12SampleStatus
    battlefield_overlap: dict[str, Any]
    task_overlap: dict[str, Any]
    audience_overlap: dict[str, Any]
    claim_value_overlap: dict[str, Any]
    param_feature: dict[str, Any]
    market_feature: dict[str, Any]
    channel_feature: dict[str, Any]
    quality_feature: dict[str, Any]


class CandidateRecallService:
    def __init__(self, repository: CandidateRecallRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M12_RULE_VERSION,
    ) -> M12ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        all_bundles = self.repository.list_all_input_bundles(batch_id)
        target_codes = tuple(sorted({code for code in sku_scope if code}))
        target_bundles = [bundle for bundle in all_bundles if not target_codes or bundle.profile.sku_code in target_codes]
        artifacts = self._build_artifacts(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_bundles=target_bundles,
            all_bundles=all_bundles,
            rule_version=rule_version,
        )
        run_save = self.repository.save_run(artifacts.run)
        run_record = run_save.records[0]
        run_id_value = run_record.candidate_recall_run_id
        pools = [pool.model_copy(update={"candidate_recall_run_id": run_id_value}) for pool in artifacts.pools]
        reasons = [reason.model_copy(update={"candidate_recall_run_id": run_id_value}) for reason in artifacts.reasons]
        snapshots = [snapshot.model_copy(update={"candidate_recall_run_id": run_id_value}) for snapshot in artifacts.snapshots]
        review_issues = [issue.model_copy(update={"candidate_recall_run_id": run_id_value}) for issue in artifacts.review_issues]
        pool_save = self.repository.save_pools(pools)
        reason_save = self.repository.save_reasons(reasons)
        snapshot_save = self.repository.save_snapshots(snapshots)
        review_save = self.repository.save_review_issues(review_issues)
        warnings = list(artifacts.run.warning_json)
        if review_issues:
            warnings.append(f"M12 生成 {len(review_issues)} 条候选召回复核问题。")
        status = Core3RunStatus.WARNING if warnings else Core3RunStatus.SUCCESS
        if artifacts.run.recall_status in {M12RecallStatus.REVIEW_REQUIRED, M12RecallStatus.LIMITED}:
            status = Core3RunStatus.WARNING
        summary = dict(artifacts.run.summary_json)
        summary.update(
            {
                "candidate_recall_run_id": run_id_value,
                "module_version": CORE3_M12_MODULE_VERSION,
                "rule_version": rule_version,
                "candidate_pair_count": len(pools),
                "reason_count": len(reasons),
                "feature_snapshot_count": len(snapshots),
                "review_issue_count": len(review_issues),
                "created_counts": {
                    "run": run_save.created_count,
                    "candidate_pool": pool_save.created_count,
                    "reason": reason_save.created_count,
                    "snapshot": snapshot_save.created_count,
                    "review_issue": review_save.created_count,
                },
                "boundary_note": BOUNDARY_NOTE_CN,
            }
        )
        return M12ServiceResult(
            status=status,
            input_count=len(target_bundles),
            output_count=len(pools) + len(reasons) + len(snapshots) + len(review_issues) + 1,
            created_output_count=(
                run_save.created_count
                + pool_save.created_count
                + reason_save.created_count
                + snapshot_save.created_count
                + review_save.created_count
            ),
            warnings=warnings,
            run=artifacts.run.model_validate(run_record, from_attributes=True),
            pools=pools,
            reasons=reasons,
            snapshots=snapshots,
            review_issues=review_issues,
            summary=summary,
        )

    def _build_artifacts(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        target_bundles: Sequence[M12SkuBundle],
        all_bundles: Sequence[M12SkuBundle],
        rule_version: str,
    ) -> M12BuildArtifacts:
        pools: list[M12CandidatePoolRecord] = []
        reasons: list[M12CandidateRecallReasonRecord] = []
        snapshots: list[M12CandidateFeatureSnapshotRecord] = []
        review_issues: list[M12CandidateRecallReviewIssueRecord] = []
        warnings: list[str] = []
        bundle_by_sku = {bundle.profile.sku_code: bundle for bundle in all_bundles}
        for target in target_bundles:
            target_pools: list[M12CandidatePoolRecord] = []
            if target.feature_view is None:
                warnings.append(f"{target.profile.sku_code} 缺少 M12 特征视图，召回降级。")
            if not target.battlefield_scores:
                review_issues.append(
                    _target_issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        target=target,
                        issue_type=M12ReviewIssueType.MISSING_BATTLEFIELD_RESULT.value,
                        message_cn="目标 SKU 缺少 M11 价值战场结果，M12 不能形成可靠候选池。",
                        rule_version=rule_version,
                    )
                )
                continue
            candidates = [bundle for bundle in all_bundles if bundle.profile.sku_code != target.profile.sku_code]
            for candidate in candidates:
                pair_context = _pair_context(target, candidate)
                reason_drafts = _recall_reasons(pair_context)
                if not reason_drafts:
                    continue
                pool, snapshot, pair_reasons, pair_issues = _build_pair_records(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    context=pair_context,
                    reasons=reason_drafts,
                )
                pools.append(pool)
                target_pools.append(pool)
                snapshots.append(snapshot)
                reasons.extend(pair_reasons)
                review_issues.extend(pair_issues)
            if len(target_pools) < 3:
                review_issues.append(
                    _target_issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        target=target,
                        issue_type=M12ReviewIssueType.SMALL_CANDIDATE_POOL.value,
                        message_cn=f"{target.profile.sku_code} 当前候选池只有 {len(target_pools)} 个 SKU，后续三竞品选择需要复核样本覆盖。",
                        rule_version=rule_version,
                        issue_context={"candidate_count": len(target_pools), "available_sku_count": len(bundle_by_sku)},
                    )
                )
        strength_counts = Counter(pool.recall_strength for pool in pools)
        source_counts = Counter(source for pool in pools for source in pool.recall_sources_json)
        relation_counts = Counter(pool.primary_relation_type for pool in pools)
        recall_status = M12RecallStatus.SUCCESS
        if review_issues:
            recall_status = M12RecallStatus.REVIEW_REQUIRED
        if not pools:
            recall_status = M12RecallStatus.BLOCKED
            warnings.append("M12 未生成任何候选 pair，请检查 M07-M11.5 上游产物。")
        run_fingerprint = stable_hash(
            {
                "batch_id": batch_id,
                "targets": [bundle.profile.sku_code for bundle in target_bundles],
                "profile_hashes": [bundle.profile.profile_hash for bundle in target_bundles],
                "all_profile_hashes": [bundle.profile.profile_hash for bundle in all_bundles],
                "pool_hashes": [pool.result_hash for pool in pools],
                "rule_version": rule_version,
            },
            version="m12_run_input_v1",
        )
        summary_json = {
            "target_sku_count": len(target_bundles),
            "available_sku_count": len(all_bundles),
            "candidate_pair_count": len(pools),
            "reason_count": len(reasons),
            "feature_snapshot_count": len(snapshots),
            "review_issue_count": len(review_issues),
            "strength_counts": dict(strength_counts),
            "source_counts": dict(source_counts),
            "relation_counts": dict(relation_counts),
            "same_brand_pair_count": sum(1 for pool in pools if pool.same_brand_flag),
            "boundary_note": BOUNDARY_NOTE_CN,
            "downstream_usage": {
                "M13": "使用候选 pair、入池理由和 m13_component_input_json 评分",
                "M14": "只在 M12/M13 候选范围内做三槽位选择",
                "M15": "展示候选进入池证据和未入选解释",
            },
            "source_modules": _source_module_versions(),
        }
        run = M12CandidateRecallRunRecord(
            candidate_recall_run_id=_record_id("m12run", batch_id, run_fingerprint, rule_version),
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            run_key=_record_id("m12runkey", batch_id, ",".join(sorted(bundle.profile.sku_code for bundle in target_bundles))),
            target_sku_count=len(target_bundles),
            candidate_pair_count=len(pools),
            reason_count=len(reasons),
            feature_snapshot_count=len(snapshots),
            review_issue_count=len(review_issues),
            strong_pair_count=int(strength_counts.get(M12RecallStrength.STRONG.value, 0)),
            medium_pair_count=int(strength_counts.get(M12RecallStrength.MEDIUM.value, 0)),
            weak_pair_count=int(strength_counts.get(M12RecallStrength.WEAK.value, 0)),
            review_only_pair_count=int(strength_counts.get(M12RecallStrength.REVIEW_ONLY.value, 0)),
            recall_status=recall_status,
            target_scope_json=[bundle.profile.sku_code for bundle in target_bundles],
            source_module_versions_json=_source_module_versions(),
            summary_json=summary_json,
            warning_json=warnings,
            boundary_note_cn=BOUNDARY_NOTE_CN,
            rule_version=rule_version,
            input_fingerprint=run_fingerprint,
            result_hash=stable_hash(summary_json, version="m12_run_result_v1"),
            processing_status="warning" if warnings or review_issues else "success",
            review_required=bool(review_issues),
            review_status="review_required" if review_issues else "auto_pass",
            review_reason_json={"issue_count": len(review_issues)} if review_issues else {},
        )
        return M12BuildArtifacts(
            run=run,
            pools=tuple(pools),
            reasons=tuple(reasons),
            snapshots=tuple(snapshots),
            review_issues=tuple(review_issues),
        )


def _build_pair_records(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    context: _PairContext,
    reasons: Sequence[_ReasonDraft],
) -> tuple[
    M12CandidatePoolRecord,
    M12CandidateFeatureSnapshotRecord,
    list[M12CandidateRecallReasonRecord],
    list[M12CandidateRecallReviewIssueRecord],
]:
    target = context.target.profile
    candidate = context.candidate.profile
    source_values = sorted({reason.source.value for reason in reasons})
    relation_values = sorted({reason.relation_type.value for reason in reasons})
    source_count = len(source_values)
    score_parts = _score_parts(context, reasons)
    priority = _weighted_score(score_parts)
    evidence_quality = _evidence_quality(context, reasons)
    strength = _recall_strength(priority, source_values, relation_values)
    primary_relation = _primary_relation(context, reasons, priority)
    feature_hash = stable_hash(
        {
            "target_profile": target.profile_hash,
            "candidate_profile": candidate.profile_hash,
            "sources": source_values,
            "relations": relation_values,
            "score_parts": score_parts,
            "rule_version": rule_version,
        },
        version="m12_feature_snapshot_v1",
    )
    pool_id = _record_id("m12pool", batch_id, target.sku_code, candidate.sku_code, rule_version)
    pool_input = {
        "target_profile_hash": target.profile_hash,
        "candidate_profile_hash": candidate.profile_hash,
        "feature_snapshot_hash": feature_hash,
        "reason_hashes": [stable_hash(reason.payload, version="m12_reason_payload_v1") for reason in reasons],
    }
    review_required = strength == M12RecallStrength.REVIEW_ONLY or len(reasons) == 1
    risk_flags = _pair_risk_flags(context, reasons, strength)
    pool = M12CandidatePoolRecord(
        candidate_pool_id=pool_id,
        project_id=target.project_id,
        category_code=target.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=target.sku_code,
        target_model_name=target.model_name,
        target_brand_name=target.brand_name,
        candidate_sku_code=candidate.sku_code,
        candidate_model_name=candidate.model_name,
        candidate_brand_name=candidate.brand_name,
        same_brand_flag=bool(target.brand_name and target.brand_name == candidate.brand_name),
        primary_relation_type=primary_relation,
        relation_types_json=relation_values,
        recall_sources_json=source_values,
        source_count=source_count,
        recall_strength=strength,
        recall_priority_score=priority,
        evidence_quality_score=evidence_quality,
        price_relation=context.price_relation,
        size_relation=context.size_relation,
        sample_status=context.sample_status,
        role_hints_json=_role_hints(primary_relation, strength, context),
        business_reason_cn=_pool_reason_cn(target, candidate, primary_relation, strength, reasons),
        score_parts_json=score_parts,
        missing_signals_json=_missing_signals(context),
        risk_flags_json=risk_flags,
        evidence_ids=_unique_evidence_ids(reason.evidence_ids for reason in reasons),
        target_profile_hash=target.profile_hash,
        candidate_profile_hash=candidate.profile_hash,
        feature_snapshot_hash=feature_hash,
        rule_version=rule_version,
        input_fingerprint=stable_hash(pool_input, version="m12_pool_input_v1"),
        result_hash=stable_hash({**pool_input, "score_parts": score_parts, "priority": priority}, version="m12_pool_result_v1"),
        processing_status="warning" if review_required else "success",
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        review_reason_json={"risk_flags": risk_flags} if review_required else {},
    )
    snapshot = _feature_snapshot(
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        rule_version=rule_version,
        context=context,
        pool_id=pool_id,
        feature_hash=feature_hash,
        pool=pool,
    )
    reason_records = [
        _reason_record(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            context=context,
            pool_id=pool_id,
            reason=reason,
        )
        for reason in reasons
    ]
    review_issues = _pair_review_issues(
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        rule_version=rule_version,
        context=context,
        pool=pool,
        snapshot=snapshot,
        reasons=reasons,
    )
    return pool, snapshot, reason_records, review_issues


def _pair_context(target: M12SkuBundle, candidate: M12SkuBundle) -> _PairContext:
    pool_member = next((row for row in target.pool_members if row.member_sku_code == candidate.profile.sku_code), None)
    price_relation = _price_relation(target.market_profile, candidate.market_profile)
    size_relation = _size_relation(target.market_profile, candidate.market_profile, pool_member)
    sample_status = _sample_status(target.market_profile, candidate.market_profile, pool_member)
    battlefield_overlap = _battlefield_overlap(target, candidate)
    task_overlap = _task_overlap(target, candidate)
    audience_overlap = _audience_overlap(target, candidate)
    claim_overlap = _claim_value_overlap(target, candidate)
    param_feature = _param_feature(target, candidate)
    market_feature = _market_feature(target, candidate, pool_member)
    channel_feature = _channel_feature(target.market_profile, candidate.market_profile, pool_member)
    quality_feature = _quality_feature(target, candidate)
    return _PairContext(
        target=target,
        candidate=candidate,
        target_market=target.market_profile,
        candidate_market=candidate.market_profile,
        pool_member=pool_member,
        price_relation=price_relation,
        size_relation=size_relation,
        sample_status=sample_status,
        battlefield_overlap=battlefield_overlap,
        task_overlap=task_overlap,
        audience_overlap=audience_overlap,
        claim_value_overlap=claim_overlap,
        param_feature=param_feature,
        market_feature=market_feature,
        channel_feature=channel_feature,
        quality_feature=quality_feature,
    )


def _recall_reasons(context: _PairContext) -> list[_ReasonDraft]:
    reasons: list[_ReasonDraft] = []
    if context.pool_member is not None:
        member = context.pool_member
        relation_type = M12RelationType.DIRECT_FIGHT
        if str(member.price_band_relation) == "lower":
            relation_type = M12RelationType.PRICE_VOLUME_PRESSURE
        elif str(member.price_band_relation) == "higher":
            relation_type = M12RelationType.PREMIUM_BENCHMARK
        reasons.append(
            _ReasonDraft(
                source=M12RecallSource.COMPARABLE_POOL,
                relation_type=relation_type,
                reason_code="m07_pool_member",
                support_score=_clamp_decimal(member.relation_strength or Decimal("0")),
                confidence=_clamp_decimal(member.member_market_confidence or Decimal("0")),
                summary_cn="M07 可比池已经把该 SKU 放入目标 SKU 的可比范围，说明价格、尺寸或渠道具备同场比较基础。",
                payload={
                    "pool_id": member.pool_id,
                    "size_relation": member.size_relation,
                    "price_band_relation": member.price_band_relation,
                    "platform_overlap_score": _float(member.platform_overlap_score),
                    "channel_overlap_score": _float(member.channel_overlap_score),
                },
                evidence_ids=tuple(member.evidence_ids or ()),
            )
        )
    if context.battlefield_overlap["matched_codes"]:
        score = _decimal(context.battlefield_overlap["overlap_score"])
        if context.battlefield_overlap.get("opportunity_only_match"):
            relation = M12RelationType.SCENARIO_SUBSTITUTE
            score = min(score, Decimal("0.3000"))
        elif context.battlefield_overlap.get("main_match") and context.price_relation in {M12PriceRelation.SIMILAR, M12PriceRelation.LOWER}:
            relation = M12RelationType.DIRECT_FIGHT
        else:
            relation = M12RelationType.SCENARIO_SUBSTITUTE
        reasons.append(
            _ReasonDraft(
                source=M12RecallSource.BATTLEFIELD,
                relation_type=relation,
                reason_code="battlefield_overlap",
                support_score=score,
                confidence=_clamp_decimal(score * Decimal("0.80") + Decimal("0.10")),
                summary_cn=_battlefield_reason_cn(context.battlefield_overlap),
                payload=context.battlefield_overlap,
                evidence_ids=tuple(context.battlefield_overlap.get("evidence_ids") or ()),
            )
        )
    if context.task_overlap["matched_codes"]:
        score = _decimal(context.task_overlap["overlap_score"])
        reasons.append(
            _ReasonDraft(
                source=M12RecallSource.TASK,
                relation_type=M12RelationType.SCENARIO_SUBSTITUTE,
                reason_code="task_overlap",
                support_score=score,
                confidence=_clamp_decimal(score * Decimal("0.75") + Decimal("0.10")),
                summary_cn=f"双方共同覆盖 {len(context.task_overlap['matched_codes'])} 个用户任务，可能被同一购买任务放在一起比较。",
                payload=context.task_overlap,
                evidence_ids=tuple(context.task_overlap.get("evidence_ids") or ()),
            )
        )
    if context.audience_overlap["matched_codes"]:
        score = _decimal(context.audience_overlap["overlap_score"])
        reasons.append(
            _ReasonDraft(
                source=M12RecallSource.AUDIENCE,
                relation_type=M12RelationType.SCENARIO_SUBSTITUTE,
                reason_code="audience_overlap",
                support_score=score,
                confidence=_clamp_decimal(score * Decimal("0.70") + Decimal("0.10")),
                summary_cn=f"双方面向 {len(context.audience_overlap['matched_codes'])} 个相同目标客群，存在同客群替代关系。",
                payload=context.audience_overlap,
                evidence_ids=tuple(context.audience_overlap.get("evidence_ids") or ()),
            )
        )
    if context.claim_value_overlap["matched_claims"]:
        score = _decimal(context.claim_value_overlap["overlap_score"])
        relation = M12RelationType.CONFIGURATION_PRESSURE
        if context.claim_value_overlap.get("candidate_stronger_count", 0) > context.claim_value_overlap.get("target_stronger_count", 0):
            relation = M12RelationType.PREMIUM_BENCHMARK
        reasons.append(
            _ReasonDraft(
                source=M12RecallSource.CLAIM_VALUE,
                relation_type=relation,
                reason_code="battlefield_claim_value_overlap",
                support_score=score,
                confidence=_clamp_decimal(score * Decimal("0.80") + Decimal("0.10")),
                summary_cn=f"双方在战场内卖点价值上有 {len(context.claim_value_overlap['matched_claims'])} 个可比卖点，适合进入候选池做后续评分。",
                payload=context.claim_value_overlap,
                evidence_ids=tuple(context.claim_value_overlap.get("evidence_ids") or ()),
            )
        )
    market_reason = _market_pressure_reason(context)
    if market_reason is not None:
        reasons.append(market_reason)
    service_reason = _scenario_service_reason(context)
    if service_reason is not None:
        reasons.append(service_reason)
    return _dedupe_reasons(reasons)


def _feature_snapshot(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    context: _PairContext,
    pool_id: str,
    feature_hash: str,
    pool: M12CandidatePoolRecord,
) -> M12CandidateFeatureSnapshotRecord:
    m13_input = {
        "target_sku_code": pool.target_sku_code,
        "candidate_sku_code": pool.candidate_sku_code,
        "candidate_relation_types": pool.relation_types_json,
        "candidate_role_hints": pool.role_hints_json,
        "recall_strength": pool.recall_strength,
        "recall_priority_score": _float(pool.recall_priority_score),
        "evidence_quality_score": _float(pool.evidence_quality_score),
        "price_feature": _without_forbidden_market_keys(_dict(context.market_feature.get("price") or {})),
        "market_feature": _without_forbidden_market_keys(context.market_feature),
        "size_feature": context.param_feature.get("size", {}),
        "channel_feature": context.channel_feature,
        "param_feature": context.param_feature,
        "battlefield_overlap": context.battlefield_overlap,
        "task_overlap": context.task_overlap,
        "audience_overlap": context.audience_overlap,
        "claim_value_overlap": context.claim_value_overlap,
        "quality_feature": context.quality_feature,
    }
    payload = {
        "m13_component_input_json": m13_input,
        "feature_hash": feature_hash,
        "rule_version": rule_version,
    }
    return M12CandidateFeatureSnapshotRecord(
        candidate_feature_snapshot_id=_record_id("m12snap", pool_id, feature_hash),
        candidate_pool_id=pool_id,
        project_id=context.target.profile.project_id,
        category_code=context.target.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=context.target.profile.sku_code,
        candidate_sku_code=context.candidate.profile.sku_code,
        size_feature_json=context.param_feature.get("size", {}),
        price_feature_json=_without_forbidden_market_keys(_dict(context.market_feature.get("price") or {})),
        channel_feature_json=context.channel_feature,
        market_feature_json=_without_forbidden_market_keys(context.market_feature),
        param_feature_json=context.param_feature,
        battlefield_overlap_json=context.battlefield_overlap,
        task_overlap_json=context.task_overlap,
        audience_overlap_json=context.audience_overlap,
        claim_value_overlap_json=context.claim_value_overlap,
        quality_feature_json=context.quality_feature,
        m13_component_input_json=m13_input,
        evidence_ids=pool.evidence_ids,
        target_profile_hash=context.target.profile.profile_hash,
        candidate_profile_hash=context.candidate.profile.profile_hash,
        feature_snapshot_hash=feature_hash,
        rule_version=rule_version,
        input_fingerprint=stable_hash(payload, version="m12_snapshot_input_v1"),
        result_hash=stable_hash(payload, version="m12_snapshot_result_v1"),
    )


def _reason_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    context: _PairContext,
    pool_id: str,
    reason: _ReasonDraft,
) -> M12CandidateRecallReasonRecord:
    payload = {
        "pool_id": pool_id,
        "source": reason.source.value,
        "relation": reason.relation_type.value,
        "code": reason.reason_code,
        "support": reason.support_score,
        "payload": reason.payload,
    }
    return M12CandidateRecallReasonRecord(
        candidate_recall_reason_id=_record_id("m12reason", pool_id, reason.source.value, reason.relation_type.value, reason.reason_code),
        candidate_pool_id=pool_id,
        project_id=context.target.profile.project_id,
        category_code=context.target.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=context.target.profile.sku_code,
        candidate_sku_code=context.candidate.profile.sku_code,
        recall_source=reason.source,
        relation_type=reason.relation_type,
        reason_code=reason.reason_code,
        support_level=_support_level(reason.support_score),
        support_score=reason.support_score,
        confidence=reason.confidence,
        reason_summary_cn=reason.summary_cn,
        source_payload_json=reason.payload,
        evidence_ids=list(reason.evidence_ids),
        risk_flags_json=list(reason.risk_flags),
        rule_version=rule_version,
        input_fingerprint=stable_hash(payload, version="m12_reason_input_v1"),
        result_hash=stable_hash({**payload, "summary": reason.summary_cn}, version="m12_reason_result_v1"),
    )


def _pair_review_issues(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    context: _PairContext,
    pool: M12CandidatePoolRecord,
    snapshot: M12CandidateFeatureSnapshotRecord,
    reasons: Sequence[_ReasonDraft],
) -> list[M12CandidateRecallReviewIssueRecord]:
    issues: list[M12CandidateRecallReviewIssueRecord] = []
    if len(reasons) == 1:
        issues.append(
            _pair_issue(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                context=context,
                pool=pool,
                snapshot=snapshot,
                issue_type=M12ReviewIssueType.SINGLE_SOURCE_CANDIDATE.value,
                message_cn="该候选只有一个召回入口，后续评分和三竞品选择必须降低确定性。",
            )
        )
    if pool.recall_strength == M12RecallStrength.REVIEW_ONLY:
        issues.append(
            _pair_issue(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                context=context,
                pool=pool,
                snapshot=snapshot,
                issue_type=M12ReviewIssueType.ONLY_SERVICE_SIGNAL.value,
                message_cn="该候选主要来自服务或场景弱信号，只能作为复核候选，不能被直接表达为正面竞品。",
            )
        )
    if not any(reason.source in {M12RecallSource.COMPARABLE_POOL, M12RecallSource.MARKET_PRESSURE} for reason in reasons):
        issues.append(
            _pair_issue(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                context=context,
                pool=pool,
                snapshot=snapshot,
                issue_type=M12ReviewIssueType.MARKET_EVIDENCE_MISSING.value,
                message_cn="该候选缺少市场或可比池证据，只能作为语义候选进入后续复核。",
            )
        )
    if not any(reason.source in {M12RecallSource.BATTLEFIELD, M12RecallSource.TASK, M12RecallSource.AUDIENCE, M12RecallSource.CLAIM_VALUE} for reason in reasons):
        issues.append(
            _pair_issue(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                context=context,
                pool=pool,
                snapshot=snapshot,
                issue_type=M12ReviewIssueType.SEMANTIC_EVIDENCE_MISSING.value,
                message_cn="该候选缺少任务、客群、战场或卖点价值证据，后续不能只凭价格销量判定竞品。",
            )
        )
    if not context.claim_value_overlap["matched_claims"]:
        issues.append(
            _pair_issue(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                context=context,
                pool=pool,
                snapshot=snapshot,
                issue_type=M12ReviewIssueType.CLAIM_VALUE_MISSING.value,
                message_cn="该候选缺少战场内卖点价值重合，M13 评分时不能把卖点优势写成已验证事实。",
                level="info",
            )
        )
    return issues


def _target_issue(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    target: M12SkuBundle,
    issue_type: str,
    message_cn: str,
    rule_version: str,
    issue_context: dict[str, Any] | None = None,
) -> M12CandidateRecallReviewIssueRecord:
    payload = {
        "target_sku_code": target.profile.sku_code,
        "issue_type": issue_type,
        "context": issue_context or {},
        "profile_hash": target.profile.profile_hash,
    }
    input_fingerprint = stable_hash(payload, version="m12_target_issue_input_v1")
    return M12CandidateRecallReviewIssueRecord(
        candidate_recall_review_issue_id=_record_id(
            "m12review",
            batch_id,
            target.profile.sku_code,
            "",
            issue_type,
            input_fingerprint,
        ),
        project_id=target.profile.project_id,
        category_code=target.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=target.profile.sku_code,
        candidate_sku_code="",
        issue_type=issue_type,
        issue_level="blocking" if issue_type == M12ReviewIssueType.MISSING_BATTLEFIELD_RESULT.value else "warning",
        issue_message_cn=message_cn,
        suggested_action_cn="补齐上游画像、战场、市场或样本后重新运行 M12。",
        issue_context_json=issue_context or {},
        evidence_ids=list(target.profile.representative_evidence_ids or ()),
        rule_version=rule_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash({**payload, "message": message_cn}, version="m12_target_issue_result_v1"),
    )


def _pair_issue(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    context: _PairContext,
    pool: M12CandidatePoolRecord,
    snapshot: M12CandidateFeatureSnapshotRecord,
    issue_type: str,
    message_cn: str,
    level: str = "warning",
) -> M12CandidateRecallReviewIssueRecord:
    payload = {
        "candidate_pool_id": pool.candidate_pool_id,
        "issue_type": issue_type,
        "target_profile": pool.target_profile_hash,
        "candidate_profile": pool.candidate_profile_hash,
    }
    input_fingerprint = stable_hash(payload, version="m12_pair_issue_input_v1")
    return M12CandidateRecallReviewIssueRecord(
        candidate_recall_review_issue_id=_record_id(
            "m12review",
            batch_id,
            pool.target_sku_code,
            pool.candidate_sku_code,
            issue_type,
            input_fingerprint,
        ),
        candidate_pool_id=pool.candidate_pool_id,
        candidate_feature_snapshot_id=snapshot.candidate_feature_snapshot_id,
        project_id=context.target.profile.project_id,
        category_code=context.target.profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=pool.target_sku_code,
        candidate_sku_code=pool.candidate_sku_code,
        issue_type=issue_type,
        issue_level=level,
        issue_message_cn=message_cn,
        suggested_action_cn="进入 M13 时按复核标记降权或要求人工复核，不要直接写成核心竞品结论。",
        issue_context_json={"recall_sources": pool.recall_sources_json, "relation_types": pool.relation_types_json},
        evidence_ids=pool.evidence_ids,
        rule_version=rule_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash({**payload, "message": message_cn}, version="m12_pair_issue_result_v1"),
    )


def _battlefield_overlap(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    target_map = _battlefield_comparison_map(target)
    candidate_map = _battlefield_comparison_map(candidate)
    matched = sorted(set(target_map) & set(candidate_map))
    intersection_weight = sum(min(_decimal(target_map[code]["comparison_weight"]), _decimal(candidate_map[code]["comparison_weight"])) for code in matched)
    union_codes = sorted(set(target_map) | set(candidate_map))
    union_weight = sum(max(_decimal(target_map.get(code, {}).get("comparison_weight")), _decimal(candidate_map.get(code, {}).get("comparison_weight"))) for code in union_codes)
    items = [
        {
            "battlefield_code": code,
            "battlefield_name_cn": target_map[code]["battlefield_name_cn"],
            "target_score": _float(target_map[code]["battlefield_score"]),
            "candidate_score": _float(candidate_map[code]["battlefield_score"]),
            "target_relation": target_map[code]["relation_level"],
            "candidate_relation": candidate_map[code]["relation_level"],
            "target_allocation_weight": _float(target_map[code]["allocation_weight"]),
            "candidate_allocation_weight": _float(candidate_map[code]["allocation_weight"]),
            "target_comparison_weight": _float(target_map[code]["comparison_weight"]),
            "candidate_comparison_weight": _float(candidate_map[code]["comparison_weight"]),
            "target_market_pool_key": target_map[code].get("market_pool_key"),
            "candidate_market_pool_key": candidate_map[code].get("market_pool_key"),
            "target_product_anchor_score": _float(target_map[code].get("product_anchor_score")),
            "candidate_product_anchor_score": _float(candidate_map[code].get("product_anchor_score")),
        }
        for code in matched
    ]
    strong_items = [
        item
        for item in items
        if item["target_relation"] in {"main", "secondary"} and item["candidate_relation"] in {"main", "secondary"}
    ]
    main_match = any(item["target_relation"] == "main" and item["candidate_relation"] == "main" for item in items)
    main_secondary_match = any(
        {item["target_relation"], item["candidate_relation"]} == {"main", "secondary"}
        for item in items
    )
    score = _clamp_decimal(intersection_weight / union_weight) if union_weight > 0 else Decimal("0.0000")
    if main_match:
        score = max(score, Decimal("0.6200"))
    return {
        "matched_codes": matched,
        "matched_items": items,
        "target_primary_codes": _primary_battlefield_codes(target),
        "candidate_primary_codes": _primary_battlefield_codes(candidate),
        "target_battlefield_weights": _battlefield_weight_payload(target_map),
        "candidate_battlefield_weights": _battlefield_weight_payload(candidate_map),
        "main_match": main_match,
        "main_secondary_match": main_secondary_match,
        "opportunity_only_match": bool(matched) and not strong_items,
        "weighted_intersection": _float(intersection_weight),
        "weighted_union": _float(union_weight),
        "overlap_score": _float(score),
        "evidence_ids": _unique_evidence_ids([item.get("evidence_ids") or [] for code in matched for item in (target_map[code], candidate_map[code])]),
    }


def _task_overlap(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    target_map = _task_map(target.task_scores)
    candidate_map = _task_map(candidate.task_scores)
    matched = sorted(set(target_map) & set(candidate_map))
    score = _avg_decimal([_decimal(target_map[code].task_score) * _decimal(candidate_map[code].task_score) for code in matched])
    return {
        "matched_codes": matched,
        "matched_items": [
            {
                "task_code": code,
                "task_name_cn": target_map[code].task_name_cn,
                "target_score": _float(target_map[code].task_score),
                "candidate_score": _float(candidate_map[code].task_score),
                "target_relation": target_map[code].relation_level,
                "candidate_relation": candidate_map[code].relation_level,
            }
            for code in matched
        ],
        "overlap_score": _float(score),
        "evidence_ids": _unique_evidence_ids([_payload_evidence(row.next_module_payload_json) for code in matched for row in (target_map[code], candidate_map[code])]),
    }


def _audience_overlap(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    target_map = _target_group_map(target.target_group_scores)
    candidate_map = _target_group_map(candidate.target_group_scores)
    matched = sorted(set(target_map) & set(candidate_map))
    score = _avg_decimal([_decimal(target_map[code].target_group_score) * _decimal(candidate_map[code].target_group_score) for code in matched])
    return {
        "matched_codes": matched,
        "matched_items": [
            {
                "target_group_code": code,
                "target_group_name_cn": target_map[code].target_group_name_cn,
                "target_score": _float(target_map[code].target_group_score),
                "candidate_score": _float(candidate_map[code].target_group_score),
                "target_relation": target_map[code].relation_level,
                "candidate_relation": candidate_map[code].relation_level,
            }
            for code in matched
        ],
        "overlap_score": _float(score),
        "evidence_ids": _unique_evidence_ids([row.evidence_ids for code in matched for row in (target_map[code], candidate_map[code])]),
    }


def _claim_value_overlap(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    target_map = _claim_value_map(target.claim_value_layers)
    candidate_map = _claim_value_map(candidate.claim_value_layers)
    matched_keys = sorted(set(target_map) & set(candidate_map))
    matched_claims: list[dict[str, Any]] = []
    target_stronger = 0
    candidate_stronger = 0
    scores: list[Decimal] = []
    for key in matched_keys:
        target_layer = target_map[key]
        candidate_layer = candidate_map[key]
        target_score = _decimal(target_layer.claim_value_score)
        candidate_score = _decimal(candidate_layer.claim_value_score)
        if candidate_score > target_score + Decimal("0.0500"):
            candidate_stronger += 1
        elif target_score > candidate_score + Decimal("0.0500"):
            target_stronger += 1
        scores.append(min(target_score, candidate_score))
        matched_claims.append(
            {
                "battlefield_code": target_layer.battlefield_code,
                "battlefield_name_cn": target_layer.battlefield_name_cn,
                "claim_code": target_layer.claim_code,
                "claim_name_cn": target_layer.claim_name_cn,
                "target_layer": target_layer.layer,
                "candidate_layer": candidate_layer.layer,
                "target_score": _float(target_score),
                "candidate_score": _float(candidate_score),
            }
        )
    return {
        "matched_claims": matched_claims,
        "matched_count": len(matched_claims),
        "target_stronger_count": target_stronger,
        "candidate_stronger_count": candidate_stronger,
        "overlap_score": _float(_avg_decimal(scores)),
        "evidence_ids": _unique_evidence_ids([row.evidence_ids for key in matched_keys for row in (target_map[key], candidate_map[key])]),
    }


def _param_feature(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    target_params = _dict(target.profile.core_params_json)
    candidate_params = _dict(candidate.profile.core_params_json)
    shared_keys = sorted(set(target_params) & set(candidate_params))
    exact_match = [key for key in shared_keys if target_params.get(key) == candidate_params.get(key)]
    return {
        "shared_param_codes": shared_keys,
        "same_value_param_codes": exact_match,
        "size": {
            "target_size": _market_size(target.market_profile),
            "candidate_size": _market_size(candidate.market_profile),
        },
        "target_core_params": {key: target_params.get(key) for key in shared_keys[:20]},
        "candidate_core_params": {key: candidate_params.get(key) for key in shared_keys[:20]},
    }


def _market_feature(
    target: M12SkuBundle,
    candidate: M12SkuBundle,
    pool_member: entities.Core3MarketPoolMember | None,
) -> dict[str, Any]:
    target_market = target.market_profile
    candidate_market = candidate.market_profile
    return {
        "price": {
            "target_price": _float(_market_price(target_market)),
            "candidate_price": _float(_market_price(candidate_market)),
            "price_relation": _price_relation(target_market, candidate_market).value,
            "price_gap_to_target": _float(pool_member.price_gap_to_target) if pool_member else None,
            "price_gap_pct_to_target": _float(pool_member.price_gap_pct_to_target) if pool_member else None,
        },
        "sales": {
            "target_volume": _float(target_market.sales_volume_total) if target_market else None,
            "candidate_volume": _float(candidate_market.sales_volume_total) if candidate_market else None,
            "target_amount": _float(target_market.sales_amount_total) if target_market else None,
            "candidate_amount": _float(candidate_market.sales_amount_total) if candidate_market else None,
            "volume_gap_to_target": _float(pool_member.volume_gap_to_target) if pool_member else None,
            "amount_gap_to_target": _float(pool_member.amount_gap_to_target) if pool_member else None,
        },
        "market_confidence": {
            "target": _float(target_market.market_confidence) if target_market else 0,
            "candidate": _float(candidate_market.market_confidence) if candidate_market else 0,
        },
        "sample_status": _sample_status(target_market, candidate_market, pool_member).value,
    }


def _channel_feature(
    target_market: entities.Core3SkuMarketProfile | None,
    candidate_market: entities.Core3SkuMarketProfile | None,
    pool_member: entities.Core3MarketPoolMember | None,
) -> dict[str, Any]:
    return {
        "target_main_channel": target_market.main_channel_type if target_market else None,
        "candidate_main_channel": candidate_market.main_channel_type if candidate_market else None,
        "target_main_platform": target_market.main_platform if target_market else None,
        "candidate_main_platform": candidate_market.main_platform if candidate_market else None,
        "channel_overlap_score": _float(pool_member.channel_overlap_score) if pool_member else None,
        "platform_overlap_score": _float(pool_member.platform_overlap_score) if pool_member else None,
        "channel_note_cn": "当前样例只使用线上专业电商/平台电商重合，不生成线下渠道结论。",
    }


def _quality_feature(target: M12SkuBundle, candidate: M12SkuBundle) -> dict[str, Any]:
    return {
        "target_profile_status": target.profile.profile_status,
        "candidate_profile_status": candidate.profile.profile_status,
        "target_confidence": _float(target.profile.confidence),
        "candidate_confidence": _float(candidate.profile.confidence),
        "target_missing_signals": list(target.profile.missing_signals_json or ()),
        "candidate_missing_signals": list(candidate.profile.missing_signals_json or ()),
        "target_risk_signals": list(target.profile.risk_signals_json or ()),
        "candidate_risk_signals": list(candidate.profile.risk_signals_json or ()),
        "m12_view_ready": bool(target.feature_view and target.feature_view.ready_for_module and candidate.feature_view and candidate.feature_view.ready_for_module),
    }


def _market_pressure_reason(context: _PairContext) -> _ReasonDraft | None:
    target_price = _market_price(context.target_market)
    candidate_price = _market_price(context.candidate_market)
    if target_price is None or candidate_price is None:
        return None
    target_volume = _decimal(context.target_market.sales_volume_total) if context.target_market and context.target_market.sales_volume_total is not None else None
    candidate_volume = _decimal(context.candidate_market.sales_volume_total) if context.candidate_market and context.candidate_market.sales_volume_total is not None else None
    score = Decimal("0.4500")
    relation = M12RelationType.SCENARIO_SUBSTITUTE
    reason = "market_comparable"
    if candidate_price <= target_price * Decimal("0.9000"):
        relation = M12RelationType.POTENTIAL_DOWNWARD_PRESSURE
        reason = "lower_price_pressure"
        score = Decimal("0.6200")
        if target_volume is not None and candidate_volume is not None and candidate_volume >= target_volume * Decimal("0.9000"):
            relation = M12RelationType.PRICE_VOLUME_PRESSURE
            reason = "lower_price_volume_pressure"
            score = Decimal("0.7600")
    elif candidate_price >= target_price * Decimal("1.1200"):
        relation = M12RelationType.PREMIUM_BENCHMARK
        reason = "higher_price_benchmark"
        score = Decimal("0.6100")
    elif abs(candidate_price - target_price) <= target_price * Decimal("0.1200"):
        relation = M12RelationType.DIRECT_FIGHT
        reason = "similar_price_direct_fight"
        score = Decimal("0.7000")
    if context.size_relation in {M12SizeRelation.ADJACENT_LARGER, M12SizeRelation.LARGER_CROSS} and candidate_price <= target_price * Decimal("1.1500"):
        relation = M12RelationType.CONFIGURATION_PRESSURE
        reason = "larger_size_configuration_pressure"
        score = max(score, Decimal("0.6800"))
    if reason == "market_comparable" and not context.battlefield_overlap["matched_codes"]:
        return None
    return _ReasonDraft(
        source=M12RecallSource.MARKET_PRESSURE,
        relation_type=relation,
        reason_code=reason,
        support_score=_clamp_decimal(score),
        confidence=_clamp_decimal(_avg_decimal([
            _decimal(context.target_market.market_confidence) if context.target_market else Decimal("0"),
            _decimal(context.candidate_market.market_confidence) if context.candidate_market else Decimal("0"),
        ])),
        summary_cn="价格、销量、尺寸或渠道表现构成市场比较压力，适合进入候选池由 M13 进一步评分。",
        payload=_without_forbidden_market_keys(context.market_feature),
        evidence_ids=tuple(_unique_evidence_ids([context.target_market.evidence_ids if context.target_market else [], context.candidate_market.evidence_ids if context.candidate_market else []])),
    )


def _scenario_service_reason(context: _PairContext) -> _ReasonDraft | None:
    matched_bf = set(context.battlefield_overlap.get("matched_codes") or [])
    if "BF_SERVICE_ASSURANCE" in matched_bf:
        return _ReasonDraft(
            source=M12RecallSource.SCENARIO_SERVICE,
            relation_type=M12RelationType.SERVICE_REFERENCE,
            reason_code="service_assurance_overlap",
            support_score=Decimal("0.4200"),
            confidence=Decimal("0.4500"),
            summary_cn="双方均有服务保障战场信号，该候选可作为服务口碑参照，但不能单独证明产品正面对打。",
            payload={"matched_battlefield_code": "BF_SERVICE_ASSURANCE", "guardrail": "service_only_not_core_competition"},
            evidence_ids=tuple(context.battlefield_overlap.get("evidence_ids") or ()),
            risk_flags=({"issue_type": M12ReviewIssueType.ONLY_SERVICE_SIGNAL.value, "reason_cn": "服务保障只能作为参照或复核入口。"},),
        )
    return None


def _score_parts(context: _PairContext, reasons: Sequence[_ReasonDraft]) -> dict[str, float]:
    by_source = {reason.source: reason.support_score for reason in reasons}
    return {
        "base_comparability": _float(max(by_source.get(M12RecallSource.COMPARABLE_POOL, Decimal("0")), _decimal(context.market_feature.get("market_confidence", {}).get("candidate") or 0))),
        "battlefield_fit": _float(by_source.get(M12RecallSource.BATTLEFIELD, Decimal("0"))),
        "task_audience_overlap": _float(max(by_source.get(M12RecallSource.TASK, Decimal("0")), by_source.get(M12RecallSource.AUDIENCE, Decimal("0")))),
        "claim_value_fit": _float(by_source.get(M12RecallSource.CLAIM_VALUE, Decimal("0"))),
        "market_pressure": _float(by_source.get(M12RecallSource.MARKET_PRESSURE, Decimal("0"))),
        "service_reference": _float(by_source.get(M12RecallSource.SCENARIO_SERVICE, Decimal("0"))),
        "evidence_quality": _float(_evidence_quality(context, reasons)),
    }


def _weighted_score(score_parts: Mapping[str, Any]) -> Decimal:
    score = (
        _decimal(score_parts.get("base_comparability")) * Decimal("0.20")
        + _decimal(score_parts.get("battlefield_fit")) * Decimal("0.25")
        + _decimal(score_parts.get("task_audience_overlap")) * Decimal("0.15")
        + _decimal(score_parts.get("claim_value_fit")) * Decimal("0.15")
        + _decimal(score_parts.get("market_pressure")) * Decimal("0.15")
        + _decimal(score_parts.get("evidence_quality")) * Decimal("0.10")
    )
    return _clamp_decimal(score)


def _evidence_quality(context: _PairContext, reasons: Sequence[_ReasonDraft]) -> Decimal:
    source_score = min(Decimal(str(len({reason.source for reason in reasons}) / max(len(CORE3_M12_RECALL_SOURCES), 1))) * Decimal("1.60"), Decimal("1.0000"))
    evidence_count = len(_unique_evidence_ids(reason.evidence_ids for reason in reasons))
    evidence_score = min(Decimal(evidence_count) / Decimal("12"), Decimal("1.0000"))
    profile_score = _avg_decimal([_decimal(context.target.profile.confidence), _decimal(context.candidate.profile.confidence)])
    return _clamp_decimal(source_score * Decimal("0.35") + evidence_score * Decimal("0.30") + profile_score * Decimal("0.35"))


def _recall_strength(priority: Decimal, sources: Sequence[str], relations: Sequence[str]) -> M12RecallStrength:
    if sources and set(sources) <= {M12RecallSource.SCENARIO_SERVICE.value}:
        return M12RecallStrength.REVIEW_ONLY
    if priority >= Decimal("0.6500") and len(sources) >= 3 and (
        M12RecallSource.BATTLEFIELD.value in sources or M12RecallSource.MARKET_PRESSURE.value in sources
    ):
        return M12RecallStrength.STRONG
    if priority >= Decimal("0.4800") and (len(sources) >= 2 or M12RecallSource.BATTLEFIELD.value in sources):
        return M12RecallStrength.MEDIUM
    if M12RelationType.SERVICE_REFERENCE.value in relations and len(sources) <= 2:
        return M12RecallStrength.REVIEW_ONLY
    return M12RecallStrength.WEAK


def _primary_relation(context: _PairContext, reasons: Sequence[_ReasonDraft], priority: Decimal) -> M12RelationType:
    relation_scores: dict[M12RelationType, Decimal] = defaultdict(lambda: Decimal("0.0000"))
    for reason in reasons:
        relation_scores[reason.relation_type] = max(relation_scores[reason.relation_type], reason.support_score)
    if (
        context.price_relation == M12PriceRelation.SIMILAR
        and context.battlefield_overlap.get("main_match")
        and not context.battlefield_overlap.get("opportunity_only_match")
        and priority >= Decimal("0.5000")
    ):
        relation_scores[M12RelationType.DIRECT_FIGHT] = max(relation_scores[M12RelationType.DIRECT_FIGHT], Decimal("0.7200"))
    return max(relation_scores.items(), key=lambda item: (item[1], item[0].value))[0]


def _pool_reason_cn(
    target: entities.Core3SkuSignalProfile,
    candidate: entities.Core3SkuSignalProfile,
    relation: M12RelationType,
    strength: M12RecallStrength,
    reasons: Sequence[_ReasonDraft],
) -> str:
    relation_cn = _relation_cn(relation)
    strength_cn = _strength_cn(strength)
    source_names = "、".join(_source_cn(reason.source) for reason in reasons[:4])
    return (
        f"{candidate.model_name or candidate.sku_code} 进入 {target.model_name or target.sku_code} 的候选池，"
        f"关系判断为{relation_cn}，召回强度为{strength_cn}；主要依据为{source_names}。"
        f"该结论只说明值得进入候选池，后续仍需 M13-M14 评分和选择。"
    )


def _role_hints(relation: M12RelationType, strength: M12RecallStrength, context: _PairContext) -> list[dict[str, Any]]:
    role = {
        M12RelationType.DIRECT_FIGHT: "正面对打候选",
        M12RelationType.PRICE_VOLUME_PRESSURE: "价格销量压力候选",
        M12RelationType.CONFIGURATION_PRESSURE: "配置压力候选",
        M12RelationType.PREMIUM_BENCHMARK: "高端标杆候选",
        M12RelationType.POTENTIAL_DOWNWARD_PRESSURE: "下探拦截候选",
        M12RelationType.UPGRADE_SUBSTITUTE: "升级替代候选",
        M12RelationType.DOWNGRADE_SUBSTITUTE: "降级替代候选",
        M12RelationType.SCENARIO_SUBSTITUTE: "场景替代候选",
        M12RelationType.SERVICE_REFERENCE: "服务参照候选",
    }[relation]
    return [
        {
            "role_hint_cn": role,
            "strength": strength.value,
            "basis": {
                "price_relation": context.price_relation.value,
                "size_relation": context.size_relation.value,
                "battlefield_overlap": context.battlefield_overlap.get("matched_codes") or [],
                "battlefield_main_match": bool(context.battlefield_overlap.get("main_match")),
                "battlefield_opportunity_only": bool(context.battlefield_overlap.get("opportunity_only_match")),
                "battlefield_overlap_score": context.battlefield_overlap.get("overlap_score"),
            },
        }
    ]


def _pair_risk_flags(context: _PairContext, reasons: Sequence[_ReasonDraft], strength: M12RecallStrength) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if context.target.feature_view is None or context.candidate.feature_view is None:
        flags.append({"issue_type": M12ReviewIssueType.MISSING_FEATURE_VIEW.value, "reason_cn": "目标或候选缺少 M12 特征视图。"})
    if len(reasons) == 1:
        flags.append({"issue_type": M12ReviewIssueType.SINGLE_SOURCE_CANDIDATE.value, "reason_cn": "只有一个召回入口。"})
    if strength == M12RecallStrength.REVIEW_ONLY:
        flags.append({"issue_type": M12ReviewIssueType.ONLY_SERVICE_SIGNAL.value, "reason_cn": "仅适合作为复核或服务参照。"})
    if context.target_market is None or context.candidate_market is None:
        flags.append({"issue_type": M12ReviewIssueType.MARKET_EVIDENCE_MISSING.value, "reason_cn": "缺少目标或候选市场画像。"})
    return flags


def _missing_signals(context: _PairContext) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if context.target.feature_view is None:
        missing.append({"sku_code": context.target.profile.sku_code, "missing": "m12_feature_view"})
    if context.candidate.feature_view is None:
        missing.append({"sku_code": context.candidate.profile.sku_code, "missing": "m12_feature_view"})
    if context.target_market is None:
        missing.append({"sku_code": context.target.profile.sku_code, "missing": "market_profile"})
    if context.candidate_market is None:
        missing.append({"sku_code": context.candidate.profile.sku_code, "missing": "market_profile"})
    if not context.claim_value_overlap["matched_claims"]:
        missing.append({"sku_code": context.candidate.profile.sku_code, "missing": "battlefield_claim_value_overlap"})
    return missing


def _battlefield_reason_cn(overlap: Mapping[str, Any]) -> str:
    matched_count = len(overlap.get("matched_codes") or [])
    if overlap.get("main_match"):
        return f"双方主战场一致，共同命中 {matched_count} 个价值战场，说明核心购买场景和竞品搜索语境重叠。"
    if overlap.get("main_secondary_match"):
        return f"双方主辅战场交叉，共同命中 {matched_count} 个价值战场，说明存在场景替代或配置比较关系。"
    if overlap.get("opportunity_only_match"):
        return f"双方仅在机会战场有交集，共同命中 {matched_count} 个价值战场，只作为候选监控信号，不单独证明正面对打。"
    return f"双方共同命中 {matched_count} 个价值战场，说明用户选择场景和比较语境重叠。"


def _battlefield_comparison_map(bundle: M12SkuBundle) -> dict[str, dict[str, Any]]:
    portfolio_map = _battlefield_portfolio_map(bundle)
    if portfolio_map:
        return portfolio_map
    score_map = _battlefield_map(bundle.battlefield_scores)
    result: dict[str, dict[str, Any]] = {}
    relation_weights = {"main": Decimal("0.6500"), "secondary": Decimal("0.3500"), "opportunity": Decimal("0.1200")}
    for code, row in score_map.items():
        relation_level = str(row.relation_level)
        score = _clamp_decimal(row.battlefield_score)
        comparison_weight = min(score, relation_weights.get(relation_level, Decimal("0.1000")))
        result[code] = {
            "battlefield_code": code,
            "battlefield_name_cn": row.battlefield_name_cn,
            "battlefield_score": score,
            "relation_level": relation_level,
            "allocation_weight": Decimal("0.0000"),
            "comparison_weight": comparison_weight,
            "market_pool_key": None,
            "product_anchor_score": None,
            "evidence_ids": list(row.evidence_ids or ()),
        }
    return result


def _battlefield_portfolio_map(bundle: M12SkuBundle) -> dict[str, dict[str, Any]]:
    portfolio = bundle.battlefield_portfolio
    if portfolio is None:
        return {}
    score_rows = {row.battlefield_code: row for row in bundle.battlefield_scores}
    result: dict[str, dict[str, Any]] = {}
    for relation_level, items in (
        ("main", portfolio.main_battlefields_json or ()),
        ("secondary", portfolio.secondary_battlefields_json or ()),
        ("opportunity", portfolio.opportunity_battlefields_json or ()),
    ):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            code = str(item.get("battlefield_code") or "")
            if not code:
                continue
            score_row = score_rows.get(code)
            score = _clamp_decimal(item.get("battlefield_score") or (score_row.battlefield_score if score_row is not None else Decimal("0")))
            allocation_weight = _clamp_decimal(item.get("allocation_weight")) if relation_level in {"main", "secondary"} else Decimal("0.0000")
            if relation_level in {"main", "secondary"}:
                comparison_weight = allocation_weight if allocation_weight > 0 else score * Decimal("0.5000")
            else:
                comparison_weight = min(score * Decimal("0.2200"), Decimal("0.1800"))
            result[code] = {
                "battlefield_code": code,
                "battlefield_name_cn": str(item.get("battlefield_name_cn") or (score_row.battlefield_name_cn if score_row is not None else code)),
                "battlefield_score": score,
                "relation_level": relation_level,
                "allocation_weight": allocation_weight,
                "comparison_weight": _clamp_decimal(comparison_weight),
                "market_pool_key": item.get("market_pool_key"),
                "screen_size_class": item.get("screen_size_class"),
                "product_anchor_score": item.get("product_anchor_score"),
                "evidence_ids": list(score_row.evidence_ids or ()) if score_row is not None else list(portfolio.evidence_ids or ()),
            }
    return result


def _battlefield_weight_payload(items: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "battlefield_code": code,
            "relation_level": item.get("relation_level"),
            "allocation_weight": _float(item.get("allocation_weight")),
            "comparison_weight": _float(item.get("comparison_weight")),
            "market_pool_key": item.get("market_pool_key"),
            "product_anchor_score": _float(item.get("product_anchor_score")),
        }
        for code, item in sorted(items.items())
    ]


def _battlefield_map(rows: Sequence[entities.Core3SkuBattlefieldScore]) -> dict[str, entities.Core3SkuBattlefieldScore]:
    allowed = {
        M11BattlefieldRelationLevel.MAIN.value,
        M11BattlefieldRelationLevel.SECONDARY.value,
        M11BattlefieldRelationLevel.OPPORTUNITY.value,
    }
    result: dict[str, entities.Core3SkuBattlefieldScore] = {}
    for row in rows:
        if row.relation_level in allowed and _decimal(row.battlefield_score) >= Decimal("0.3500"):
            result[row.battlefield_code] = row
    return result


def _task_map(rows: Sequence[entities.Core3SkuTaskScore]) -> dict[str, entities.Core3SkuTaskScore]:
    result: dict[str, entities.Core3SkuTaskScore] = {}
    for row in rows:
        if row.relation_level in {"main", "secondary"} and _decimal(row.task_score) >= Decimal("0.4000"):
            result[row.task_code] = row
    return result


def _target_group_map(rows: Sequence[entities.Core3SkuTargetGroupScore]) -> dict[str, entities.Core3SkuTargetGroupScore]:
    result: dict[str, entities.Core3SkuTargetGroupScore] = {}
    for row in rows:
        if row.relation_level in {"main", "secondary"} and _decimal(row.target_group_score) >= Decimal("0.4000"):
            result[row.target_group_code] = row
    return result


def _claim_value_map(rows: Sequence[entities.Core3SkuClaimValueLayer]) -> dict[tuple[str, str], entities.Core3SkuClaimValueLayer]:
    allowed_layers = {"basic_threshold", "competitive_performance", "premium_tendency"}
    result: dict[tuple[str, str], entities.Core3SkuClaimValueLayer] = {}
    for row in rows:
        if row.layer in allowed_layers and _decimal(row.claim_value_score) >= Decimal("0.4200"):
            key = (row.battlefield_code, row.claim_code)
            if key not in result or _decimal(row.claim_value_score) > _decimal(result[key].claim_value_score):
                result[key] = row
    return result


def _primary_battlefield_codes(bundle: M12SkuBundle) -> list[str]:
    if bundle.battlefield_portfolio is not None:
        return list(bundle.battlefield_portfolio.primary_search_battlefield_codes_json or ())
    return [row.battlefield_code for row in bundle.battlefield_scores if row.relation_level == M11BattlefieldRelationLevel.MAIN.value]


def _price_relation(
    target_market: entities.Core3SkuMarketProfile | None,
    candidate_market: entities.Core3SkuMarketProfile | None,
) -> M12PriceRelation:
    target_price = _market_price(target_market)
    candidate_price = _market_price(candidate_market)
    if target_price is None or candidate_price is None or target_price <= 0:
        return M12PriceRelation.UNKNOWN
    gap_rate = (candidate_price - target_price) / target_price
    if abs(gap_rate) <= Decimal("0.1200"):
        return M12PriceRelation.SIMILAR
    if gap_rate < 0:
        return M12PriceRelation.LOWER
    return M12PriceRelation.HIGHER


def _size_relation(
    target_market: entities.Core3SkuMarketProfile | None,
    candidate_market: entities.Core3SkuMarketProfile | None,
    pool_member: entities.Core3MarketPoolMember | None,
) -> M12SizeRelation:
    if pool_member is not None:
        relation = str(pool_member.size_relation)
        if relation == "same":
            return M12SizeRelation.SAME
        if relation in {"adjacent_larger", "larger_adjacent"}:
            return M12SizeRelation.ADJACENT_LARGER
        if relation in {"adjacent_smaller", "smaller_adjacent"}:
            return M12SizeRelation.ADJACENT_SMALLER
    target_size = _market_size(target_market)
    candidate_size = _market_size(candidate_market)
    if target_size is None or candidate_size is None:
        return M12SizeRelation.UNKNOWN
    diff = candidate_size - target_size
    if abs(diff) <= Decimal("0.5"):
        return M12SizeRelation.SAME
    if Decimal("0.5") < diff <= Decimal("15"):
        return M12SizeRelation.ADJACENT_LARGER
    if Decimal("-15") <= diff < Decimal("-0.5"):
        return M12SizeRelation.ADJACENT_SMALLER
    return M12SizeRelation.LARGER_CROSS if diff > 0 else M12SizeRelation.SMALLER_CROSS


def _sample_status(
    target_market: entities.Core3SkuMarketProfile | None,
    candidate_market: entities.Core3SkuMarketProfile | None,
    pool_member: entities.Core3MarketPoolMember | None,
) -> M12SampleStatus:
    statuses = [str(row.sample_status) for row in (target_market, candidate_market) if row is not None]
    if pool_member is not None and _decimal(pool_member.relation_strength) > Decimal("0.6000"):
        statuses.append(M12SampleStatus.SUFFICIENT.value)
    if not statuses:
        return M12SampleStatus.UNKNOWN
    if "insufficient" in statuses:
        return M12SampleStatus.INSUFFICIENT
    if "limited" in statuses:
        return M12SampleStatus.LIMITED
    if "sufficient" in statuses:
        return M12SampleStatus.SUFFICIENT
    return M12SampleStatus.UNKNOWN


def _market_price(market: entities.Core3SkuMarketProfile | None) -> Decimal | None:
    if market is None:
        return None
    for value in (market.price_wavg, market.price_median, market.price_latest):
        if value is not None:
            return _decimal(value)
    return None


def _market_size(market: entities.Core3SkuMarketProfile | None) -> Decimal | None:
    if market is None or market.screen_size_inch is None:
        return None
    return _decimal(market.screen_size_inch)


def _support_level(score: Decimal) -> M12SupportLevel:
    if score >= Decimal("0.7200"):
        return M12SupportLevel.STRONG
    if score >= Decimal("0.5000"):
        return M12SupportLevel.MEDIUM
    if score > Decimal("0.0000"):
        return M12SupportLevel.WEAK
    return M12SupportLevel.MISSING


def _dedupe_reasons(reasons: Sequence[_ReasonDraft]) -> list[_ReasonDraft]:
    best: dict[tuple[str, str, str], _ReasonDraft] = {}
    for reason in reasons:
        key = (reason.source.value, reason.relation_type.value, reason.reason_code)
        if key not in best or reason.support_score > best[key].support_score:
            best[key] = reason
    return sorted(best.values(), key=lambda item: (item.source.value, item.relation_type.value, item.reason_code))


def _source_module_versions() -> dict[str, str]:
    return {
        "M07": CORE3_M07_RULE_VERSION,
        "M08": CORE3_M08_FEATURE_VERSION,
        "M09": CORE3_M09_RULE_VERSION,
        "M10": CORE3_M10_RULE_VERSION,
        "M11": CORE3_M11_RULE_VERSION,
        "M11.5": CORE3_M11_5_RULE_VERSION,
        "M12": CORE3_M12_RULE_VERSION,
    }


def _without_forbidden_market_keys(value: Mapping[str, Any]) -> dict[str, Any]:
    forbidden = {"price_wavg_12m", "sales_volume_12m", "sales_amount_12m"}
    result: dict[str, Any] = {}
    for key, item in value.items():
        if str(key) in forbidden:
            continue
        if isinstance(item, Mapping):
            result[str(key)] = _without_forbidden_market_keys(item)
        elif isinstance(item, list):
            result[str(key)] = [_without_forbidden_market_keys(child) if isinstance(child, Mapping) else child for child in item]
        else:
            result[str(key)] = item
    return result


def _unique_evidence_ids(items: Iterable[Iterable[str] | tuple[str, ...] | list[str]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for values in items:
        for value in values or ():
            text = str(value)
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def _payload_evidence(payload: Mapping[str, Any] | None) -> list[str]:
    if not payload:
        return []
    values = payload.get("evidence_ids") or payload.get("representative_evidence_ids") or []
    return [str(value) for value in values]


def _avg_decimal(values: Sequence[Decimal | int | float | str | None]) -> Decimal:
    normalized = [_decimal(value) for value in values if value is not None]
    if not normalized:
        return Decimal("0.0000")
    return _clamp_decimal(sum(normalized, Decimal("0.0000")) / Decimal(len(normalized)))


def _clamp_decimal(value: Decimal | int | float | str | None) -> Decimal:
    decimal_value = _decimal(value)
    if decimal_value < 0:
        decimal_value = Decimal("0")
    if decimal_value > 1:
        decimal_value = Decimal("1")
    return decimal_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _float(value: Any) -> float:
    if value is None:
        return 0.0
    return float(_decimal(value))


def _dict(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _record_id(prefix: str, *parts: Any) -> str:
    digest = stable_hash([str(part) for part in parts], version=f"{prefix}_id_v1").split(":")[-1][:32]
    return f"{prefix}_{digest}"


def _source_cn(source: M12RecallSource) -> str:
    return {
        M12RecallSource.COMPARABLE_POOL: "可比池",
        M12RecallSource.BATTLEFIELD: "价值战场",
        M12RecallSource.TASK: "用户任务",
        M12RecallSource.AUDIENCE: "目标客群",
        M12RecallSource.CLAIM_VALUE: "战场内卖点价值",
        M12RecallSource.MARKET_PRESSURE: "市场压力",
        M12RecallSource.SCENARIO_SERVICE: "服务/场景参照",
    }[source]


def _relation_cn(relation: M12RelationType) -> str:
    return {
        M12RelationType.DIRECT_FIGHT: "正面对打",
        M12RelationType.PRICE_VOLUME_PRESSURE: "价格销量压力",
        M12RelationType.CONFIGURATION_PRESSURE: "配置压力",
        M12RelationType.PREMIUM_BENCHMARK: "高端标杆",
        M12RelationType.POTENTIAL_DOWNWARD_PRESSURE: "下探拦截",
        M12RelationType.UPGRADE_SUBSTITUTE: "升级替代",
        M12RelationType.DOWNGRADE_SUBSTITUTE: "降级替代",
        M12RelationType.SCENARIO_SUBSTITUTE: "场景替代",
        M12RelationType.SERVICE_REFERENCE: "服务参照",
    }[relation]


def _strength_cn(strength: M12RecallStrength) -> str:
    return {
        M12RecallStrength.STRONG: "强",
        M12RecallStrength.MEDIUM: "中",
        M12RecallStrength.WEAK: "弱",
        M12RecallStrength.REVIEW_ONLY: "仅复核",
    }[strength]
