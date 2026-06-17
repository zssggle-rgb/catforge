"""M11.6 SKU business profile aggregation service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.constants import CORE3_M11_6_RULE_VERSION, Core3ConfidenceLevel, Core3RunStatus
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.sku_business_profile_repositories import M116SkuBundle, SkuBusinessProfileRepository
from app.services.core3_real_data.sku_business_profile_schemas import (
    M116BuildArtifacts,
    M116ServiceResult,
    M116SkuBusinessProfileDimensionRecord,
    M116SkuBusinessProfileRecord,
    M116SkuBusinessProfileReviewIssueRecord,
    M116SkuBusinessProfileSalesAllocationRecord,
)


BOUNDARY_NOTE_CN = "M11.6 只聚合 SKU 级业务画像和 SKU 内维度销量分配，不做全局销量守恒、不召回候选 SKU、不输出核心三竞品。"
DIMENSION_TYPES = ("claim", "task", "target_group", "battlefield")
CLAIM_INFERENCE_SOURCE_MODULE = "M08/M04b inferred"
CLAIM_INFERENCE_MIN_SCORE = Decimal("0.1500")
CLAIM_INFERENCE_MIN_CONFIDENCE = Decimal("0.3500")
CLAIM_INFERENCE_PARAM_ONLY_MIN_SCORE = Decimal("0.3000")
CLAIM_INFERENCE_MAX_SCORE = Decimal("0.5200")
CLAIM_INFERENCE_LIMIT = 6
ALLOCATABLE_RELATIONS = {"main", "secondary"}
BATTLEFIELD_FALLBACK_RELATIONS = {"opportunity", "weak"}
TASK_GROUP_FALLBACK_RELATIONS = {"weak"}
TASK_ALLOCATION_LIMIT = 3
TARGET_GROUP_ALLOCATION_LIMIT = 3
BATTLEFIELD_ALLOCATION_LIMIT = 3
DIMENSION_FALLBACK_MIN_SCORE = Decimal("0.3500")
NON_PRODUCT_BATTLEFIELD_CODES = {"BF_SERVICE_ASSURANCE"}


@dataclass(frozen=True)
class MarketSnapshot:
    source: str
    screen_size_inch: Decimal | None
    size_segment: str
    price_band: str
    main_platform: str | None
    sales_volume_total: Decimal | None
    sales_amount_total: Decimal | None
    price_wavg: Decimal | None
    price_latest: Decimal | None
    price_percentile: Decimal | None
    sales_percentile: Decimal | None
    amount_percentile: Decimal | None
    price_gap_to_pool_median: Decimal | None
    sample_status: str
    confidence: Decimal
    missing: tuple[str, ...]


@dataclass(frozen=True)
class DimensionDraft:
    dimension_type: str
    code: str
    name: str
    score: Decimal
    confidence: Decimal
    relation_level: str
    value_layer: str | None
    source_module: str
    source_record_refs: tuple[dict[str, Any], ...]
    support_breakdown: dict[str, Any]
    evidence_ids: tuple[str, ...]
    business_reason_cn: str
    normalized_weight: Decimal = Decimal("0.000000")
    rank: int = 0


class SkuBusinessProfileService:
    def __init__(self, repository: SkuBusinessProfileRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M11_6_RULE_VERSION,
    ) -> M116ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        bundles = self.repository.list_input_bundles(batch_id, sku_scope)
        if not bundles:
            return M116ServiceResult(
                status=Core3RunStatus.WARNING,
                input_count=0,
                output_count=0,
                created_output_count=0,
                updated_output_count=0,
                reused_output_count=0,
                warnings=["M11.6 没有找到可处理的 M08 SKU 画像。"],
                profiles=(),
                dimensions=(),
                allocations=(),
                review_issues=(),
                summary={"batch_id": batch_id, "rule_version": rule_version, "sku_count": 0},
            )

        artifacts = self._build_artifacts(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            bundles=bundles,
            rule_version=rule_version,
        )
        self.repository.mark_child_outputs_stale(
            batch_id=batch_id,
            rule_version=rule_version,
            sku_codes=[profile.sku_code for profile in artifacts.profiles],
        )
        profile_write = self.repository.save_profiles(artifacts.profiles)
        persisted_artifacts = _remap_persisted_profile_ids(artifacts, profile_write.records)
        dimension_write = self.repository.save_dimensions(persisted_artifacts.dimensions)
        persisted_artifacts = _remap_persisted_dimension_ids(persisted_artifacts, dimension_write.records)
        allocation_write = self.repository.save_allocations(persisted_artifacts.allocations)
        review_write = self.repository.save_review_issues(persisted_artifacts.review_issues)

        created = (
            profile_write.created_count
            + dimension_write.created_count
            + allocation_write.created_count
            + review_write.created_count
        )
        updated = (
            profile_write.updated_count
            + dimension_write.updated_count
            + allocation_write.updated_count
            + review_write.updated_count
        )
        reused = (
            profile_write.reused_count
            + dimension_write.reused_count
            + allocation_write.reused_count
            + review_write.reused_count
        )
        warnings = []
        if persisted_artifacts.review_issues:
            warnings.append(f"M11.6 生成 {len(persisted_artifacts.review_issues)} 条 SKU 业务画像复核问题，主要来自量价缺失或维度证据不足。")
        status = Core3RunStatus.WARNING if persisted_artifacts.review_issues else Core3RunStatus.SUCCESS
        issue_counts = Counter(issue.issue_type for issue in persisted_artifacts.review_issues)
        dimension_counts = Counter(item.dimension_type for item in persisted_artifacts.dimensions)
        allocation_summary = _allocation_totals(persisted_artifacts.allocations)
        return M116ServiceResult(
            status=status,
            input_count=len(bundles),
            output_count=(
                len(persisted_artifacts.profiles)
                + len(persisted_artifacts.dimensions)
                + len(persisted_artifacts.allocations)
                + len(persisted_artifacts.review_issues)
            ),
            created_output_count=created,
            updated_output_count=updated,
            reused_output_count=reused,
            warnings=warnings,
            profiles=persisted_artifacts.profiles,
            dimensions=persisted_artifacts.dimensions,
            allocations=persisted_artifacts.allocations,
            review_issues=persisted_artifacts.review_issues,
            summary={
                "batch_id": batch_id,
                "rule_version": rule_version,
                "sku_count": len(bundles),
                "business_profile_count": len(persisted_artifacts.profiles),
                "business_dimension_count": len(persisted_artifacts.dimensions),
                "sales_allocation_count": len(persisted_artifacts.allocations),
                "review_issue_count": len(persisted_artifacts.review_issues),
                "dimension_counts": dict(dimension_counts),
                "review_issue_counts": dict(issue_counts),
                "allocation_totals_by_dimension_type": allocation_summary,
                "created_output_count": created,
                "updated_output_count": updated,
                "reused_output_count": reused,
                "boundary_note": BOUNDARY_NOTE_CN,
                "downstream_support": {
                    "M12": "优先消费 SKU 业务画像、主任务/主客群/主战场、竞争角色提示和召回优先级",
                    "M13": "消费 SKU 画像中的维度权重和卖点价值强度作为 pair 评分解释输入",
                    "M14": "消费市场角色、竞争角色和业务摘要支持三槽位选择解释",
                    "M15": "消费业务画像中文摘要和分配表展示 SKU 定位逻辑",
                    "M11.7": "消费四类维度销量分配做全局销量守恒和市场结构校验",
                },
            },
        )

    def _build_artifacts(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        bundles: Sequence[M116SkuBundle],
        rule_version: str,
    ) -> M116BuildArtifacts:
        profiles: list[M116SkuBusinessProfileRecord] = []
        dimensions: list[M116SkuBusinessProfileDimensionRecord] = []
        allocations: list[M116SkuBusinessProfileSalesAllocationRecord] = []
        review_issues: list[M116SkuBusinessProfileReviewIssueRecord] = []
        for bundle in bundles:
            bundle_profiles, bundle_dimensions, bundle_allocations, bundle_issues = self._build_bundle(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                bundle=bundle,
                rule_version=rule_version,
            )
            profiles.append(bundle_profiles)
            dimensions.extend(bundle_dimensions)
            allocations.extend(bundle_allocations)
            review_issues.extend(bundle_issues)
        return M116BuildArtifacts(
            profiles=tuple(profiles),
            dimensions=tuple(dimensions),
            allocations=tuple(allocations),
            review_issues=tuple(review_issues),
        )

    def _build_bundle(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        bundle: M116SkuBundle,
        rule_version: str,
    ) -> tuple[
        M116SkuBusinessProfileRecord,
        list[M116SkuBusinessProfileDimensionRecord],
        list[M116SkuBusinessProfileSalesAllocationRecord],
        list[M116SkuBusinessProfileReviewIssueRecord],
    ]:
        profile = bundle.profile
        market = _market_snapshot(bundle)
        input_fingerprint = _input_fingerprint(bundle, market, rule_version)
        profile_id = _record_id("m116_profile", profile.sku_code, input_fingerprint)
        issues: list[M116SkuBusinessProfileReviewIssueRecord] = []
        if market.missing:
            issues.append(
                _review_issue(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    project_id=profile.project_id,
                    category_code=profile.category_code,
                    profile_id=profile_id,
                    sku_code=profile.sku_code,
                    issue_type="blocked_missing_market",
                    issue_level="blocker",
                    issue_message_cn="SKU 缺少销量、销额或价格字段，业务画像可生成但销量分配不能作为下游确定性结论。",
                    suggested_action_cn="补齐 M07/M08 量价字段后重跑 M11.6；在此之前下游只可参考非销量口径画像。",
                    issue_context={"missing_market_fields": list(market.missing), "market_source": market.source},
                    input_fingerprint=input_fingerprint,
                    rule_version=rule_version,
                )
            )

        dimension_drafts = _rank_dimensions(_dimension_drafts(bundle))
        by_type = _group_dimensions(dimension_drafts)
        inferred_claims = [draft for draft in by_type.get("claim", ()) if draft.source_module == CLAIM_INFERENCE_SOURCE_MODULE]
        if inferred_claims:
            issues.append(
                _review_issue(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    project_id=profile.project_id,
                    category_code=profile.category_code,
                    profile_id=profile_id,
                    sku_code=profile.sku_code,
                    dimension_type="claim",
                    issue_type="inferred_claim_dimension_review",
                    issue_level="warning",
                    issue_message_cn="SKU 缺少 M11.5 卖点价值层，已使用 M08/M04b 卖点激活结果补充低置信卖点维度。",
                    suggested_action_cn="复核参数、评论和宣传证据；若真实卖点成立，应补强 M04b/M11.5 证据后重跑。",
                    issue_context={
                        "claim_codes": [draft.code for draft in inferred_claims],
                        "source_module": CLAIM_INFERENCE_SOURCE_MODULE,
                        "fallback_policy": "claim_activation_to_low_confidence_dimension",
                    },
                    input_fingerprint=input_fingerprint,
                    rule_version=rule_version,
                )
            )
        for dimension_type in DIMENSION_TYPES:
            if not by_type.get(dimension_type):
                issues.append(
                    _review_issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        project_id=profile.project_id,
                        category_code=profile.category_code,
                        profile_id=profile_id,
                        sku_code=profile.sku_code,
                        dimension_type=dimension_type,
                        issue_type=f"missing_{dimension_type}_dimension",
                        issue_level="warning",
                        issue_message_cn=f"SKU 缺少 {dimension_type} 维度候选，业务画像会降低该维度置信度。",
                        suggested_action_cn="检查对应上游模块是否已有当前产物，必要时补充样例或真实数据后重跑。",
                        issue_context={"dimension_type": dimension_type},
                        input_fingerprint=input_fingerprint,
                        rule_version=rule_version,
                    )
                )

        primary_task = _first(by_type.get("task", ()))
        primary_group = _first(by_type.get("target_group", ()))
        primary_battlefield = _first(by_type.get("battlefield", ()))
        claim_drafts = list(by_type.get("claim", ()))
        claim_strength = _avg_top_scores(claim_drafts, limit=3)
        premium = _premium_profile(market, claim_strength, claim_drafts)
        market_role, market_role_reason = _market_role(market)
        confidence = _overall_confidence(profile, market, primary_task, primary_group, primary_battlefield, claim_strength, issues)
        evidence_strength = _evidence_level(confidence)
        allocation_summary = _sku_allocation_summary(dimension_drafts, market)
        business_summary_cn = _business_summary(profile, primary_task, primary_group, primary_battlefield, market_role, premium)
        result_payload = {
            "sku_code": profile.sku_code,
            "primary_task": primary_task.code if primary_task else None,
            "primary_group": primary_group.code if primary_group else None,
            "primary_battlefield": primary_battlefield.code if primary_battlefield else None,
            "claim_strength": str(claim_strength),
            "premium": premium,
            "market_role": market_role,
            "confidence": str(confidence),
            "allocation_summary": allocation_summary,
            "issues": [issue.issue_type for issue in issues],
        }
        profile_record = M116SkuBusinessProfileRecord(
            sku_business_profile_id=profile_id,
            sku_signal_profile_id=profile.sku_signal_profile_id,
            project_id=profile.project_id,
            category_code=profile.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=profile.sku_code,
            model_code=profile.model_code,
            model_name=profile.model_name,
            brand_name=profile.brand_name,
            series_name=_series_name(bundle),
            screen_size_inch=market.screen_size_inch,
            size_segment=market.size_segment,
            price_band=market.price_band,
            main_platform=market.main_platform,
            sales_volume_total=market.sales_volume_total,
            sales_amount_total=market.sales_amount_total,
            price_wavg=market.price_wavg,
            price_latest=market.price_latest,
            price_percentile_in_pool=market.price_percentile,
            sales_percentile_in_pool=market.sales_percentile,
            amount_percentile_in_pool=market.amount_percentile,
            price_gap_to_pool_median=market.price_gap_to_pool_median,
            market_sample_status=market.sample_status,
            market_source=market.source,
            primary_task_code=primary_task.code if primary_task else None,
            primary_task_name=primary_task.name if primary_task else None,
            primary_task_score=primary_task.score if primary_task else Decimal("0.0000"),
            primary_task_evidence_level=_evidence_level(primary_task.confidence if primary_task else Decimal("0")),
            primary_task_confidence=primary_task.confidence if primary_task else Decimal("0.0000"),
            primary_target_group_code=primary_group.code if primary_group else None,
            primary_target_group_name=primary_group.name if primary_group else None,
            primary_target_group_score=primary_group.score if primary_group else Decimal("0.0000"),
            primary_target_group_evidence_level=_evidence_level(primary_group.confidence if primary_group else Decimal("0")),
            primary_target_group_confidence=primary_group.confidence if primary_group else Decimal("0.0000"),
            primary_battlefield_code=primary_battlefield.code if primary_battlefield else None,
            primary_battlefield_name=primary_battlefield.name if primary_battlefield else None,
            primary_battlefield_score=primary_battlefield.score if primary_battlefield else Decimal("0.0000"),
            primary_battlefield_evidence_level=_evidence_level(primary_battlefield.confidence if primary_battlefield else Decimal("0")),
            primary_battlefield_confidence=primary_battlefield.confidence if primary_battlefield else Decimal("0.0000"),
            secondary_tasks_json=_dimension_refs(by_type.get("task", ())[1:5]),
            secondary_target_groups_json=_dimension_refs(by_type.get("target_group", ())[1:5]),
            secondary_battlefields_json=_dimension_refs(by_type.get("battlefield", ())[1:5]),
            core_claims_json=_dimension_refs(claim_drafts[:8], include_value_layer=True),
            claim_value_summary_json=_claim_value_summary(claim_drafts),
            claim_value_strength=claim_strength,
            premium_position=premium["premium_position"],
            premium_type=premium["premium_type"],
            premium_support_level=premium["premium_support_level"],
            premium_score=premium["premium_score"],
            premium_reason_cn=premium["premium_reason_cn"],
            premium_risk_json=premium["premium_risk_json"],
            market_role=market_role,
            market_role_reason_cn=market_role_reason,
            competitive_role_hints_json=_competitive_role_hints(market_role, primary_battlefield, premium),
            candidate_recall_priority_json=_candidate_recall_priority(primary_task, primary_group, primary_battlefield, claim_strength, confidence),
            same_brand_competition_policy="allow",
            sales_allocation_summary_json=allocation_summary,
            evidence_strength=evidence_strength,
            confidence=confidence,
            confidence_level=_confidence_level(confidence),
            missing_signals_json=_missing_signals(profile, market, issues),
            risk_signals_json=list(profile.risk_signals_json or []) + list(premium["premium_risk_json"]),
            representative_evidence_ids=_representative_evidence_ids(profile, dimension_drafts),
            business_summary_cn=business_summary_cn,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(result_payload, version="m116_profile_result_v1"),
            processing_status="review_required" if issues else "success",
            review_required=bool(issues),
            review_status="review_required" if issues else "auto_pass",
            review_reason_json={"issue_count": len(issues), "issue_types": [issue.issue_type for issue in issues]},
        )

        dimension_records = [
            _dimension_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                profile=profile,
                profile_id=profile_id,
                draft=draft,
                input_fingerprint=input_fingerprint,
                rule_version=rule_version,
            )
            for draft in dimension_drafts
        ]
        dimension_id_by_key = {
            (row.dimension_type, row.dimension_code): row.profile_dimension_id
            for row in dimension_records
        }
        allocation_records = [
            _allocation_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                profile=profile,
                profile_id=profile_id,
                dimension_id=dimension_id_by_key[(draft.dimension_type, draft.code)],
                draft=draft,
                market=market,
                input_fingerprint=input_fingerprint,
                rule_version=rule_version,
            )
            for draft in dimension_drafts
            if draft.normalized_weight > 0
        ]
        for index, issue in enumerate(issues):
            issues[index] = issue.model_copy(update={"sku_business_profile_id": profile_id})
        return profile_record, dimension_records, allocation_records, issues


def _remap_persisted_profile_ids(artifacts: M116BuildArtifacts, persisted_profiles: Sequence[Any]) -> M116BuildArtifacts:
    profile_id_map: dict[str, str] = {}
    for generated, persisted in zip(artifacts.profiles, persisted_profiles, strict=True):
        _assert_same_record_key(generated, persisted, ("batch_id", "sku_code", "rule_version"), "M11.6 profile")
        profile_id_map[generated.sku_business_profile_id] = persisted.sku_business_profile_id
    if all(original_id == persisted_id for original_id, persisted_id in profile_id_map.items()):
        return artifacts
    return M116BuildArtifacts(
        profiles=tuple(
            profile.model_copy(
                update={"sku_business_profile_id": profile_id_map.get(profile.sku_business_profile_id, profile.sku_business_profile_id)}
            )
            for profile in artifacts.profiles
        ),
        dimensions=tuple(
            row.model_copy(
                update={"sku_business_profile_id": profile_id_map.get(row.sku_business_profile_id or "", row.sku_business_profile_id)}
            )
            for row in artifacts.dimensions
        ),
        allocations=tuple(
            row.model_copy(
                update={"sku_business_profile_id": profile_id_map.get(row.sku_business_profile_id or "", row.sku_business_profile_id)}
            )
            for row in artifacts.allocations
        ),
        review_issues=tuple(
            row.model_copy(
                update={"sku_business_profile_id": profile_id_map.get(row.sku_business_profile_id or "", row.sku_business_profile_id)}
            )
            for row in artifacts.review_issues
        ),
    )


def _remap_persisted_dimension_ids(artifacts: M116BuildArtifacts, persisted_dimensions: Sequence[Any]) -> M116BuildArtifacts:
    dimension_id_map: dict[str, str] = {}
    for generated, persisted in zip(artifacts.dimensions, persisted_dimensions, strict=True):
        _assert_same_record_key(
            generated,
            persisted,
            ("batch_id", "sku_code", "dimension_type", "dimension_code", "rule_version"),
            "M11.6 dimension",
        )
        dimension_id_map[generated.profile_dimension_id] = persisted.profile_dimension_id
    if all(original_id == persisted_id for original_id, persisted_id in dimension_id_map.items()):
        return artifacts
    return M116BuildArtifacts(
        profiles=artifacts.profiles,
        dimensions=tuple(
            row.model_copy(update={"profile_dimension_id": dimension_id_map.get(row.profile_dimension_id, row.profile_dimension_id)})
            for row in artifacts.dimensions
        ),
        allocations=tuple(
            row.model_copy(update={"profile_dimension_id": dimension_id_map.get(row.profile_dimension_id or "", row.profile_dimension_id)})
            for row in artifacts.allocations
        ),
        review_issues=tuple(
            row.model_copy(update={"profile_dimension_id": dimension_id_map.get(row.profile_dimension_id or "", row.profile_dimension_id)})
            for row in artifacts.review_issues
        ),
    )


def _assert_same_record_key(generated: Any, persisted: Any, fields: Sequence[str], label: str) -> None:
    for field_name in fields:
        generated_value = getattr(generated, field_name)
        persisted_value = getattr(persisted, field_name)
        if generated_value != persisted_value:
            raise ValueError(
                f"{label} persisted key mismatch on {field_name}: generated={generated_value!r}, persisted={persisted_value!r}"
            )


def _dimension_drafts(bundle: M116SkuBundle) -> list[DimensionDraft]:
    drafts: list[DimensionDraft] = []
    drafts.extend(_task_drafts(bundle.task_scores))
    drafts.extend(_target_group_drafts(bundle.target_group_scores))
    battlefield_drafts = _battlefield_drafts_from_portfolio(bundle)
    if not battlefield_drafts:
        battlefield_drafts = _battlefield_drafts(bundle.battlefield_scores)
    drafts.extend(battlefield_drafts)
    claim_drafts = _claim_drafts(bundle.claim_value_layers)
    if not claim_drafts:
        claim_drafts = _inferred_claim_drafts(bundle)
    drafts.extend(claim_drafts)
    return drafts


def _task_drafts(rows: Sequence[entities.Core3SkuTaskScore]) -> list[DimensionDraft]:
    return [
        DimensionDraft(
            dimension_type="task",
            code=row.task_code,
            name=row.task_name_cn,
            score=_q4(row.task_score),
            confidence=_q4(row.confidence),
            relation_level=row.relation_level,
            value_layer=None,
            source_module="M09",
            source_record_refs=({"table": "core3_sku_task_score", "id": row.sku_task_score_id},),
            support_breakdown=dict(row.evidence_domain_coverage_json or {}),
            evidence_ids=(),
            business_reason_cn=row.business_reason_cn,
        )
        for row in _select_allocatable_task_rows(rows)
    ]


def _target_group_drafts(rows: Sequence[entities.Core3SkuTargetGroupScore]) -> list[DimensionDraft]:
    return [
        DimensionDraft(
            dimension_type="target_group",
            code=row.target_group_code,
            name=row.target_group_name_cn,
            score=_q4(row.target_group_score),
            confidence=_q4(row.confidence),
            relation_level=row.relation_level,
            value_layer=None,
            source_module="M10",
            source_record_refs=({"table": "core3_sku_target_group_score", "id": row.sku_target_group_score_id},),
            support_breakdown=dict(row.score_breakdown_json or {}),
            evidence_ids=tuple(row.evidence_ids or ()),
            business_reason_cn=row.business_reason_cn,
        )
        for row in _select_allocatable_target_group_rows(rows)
    ]


def _battlefield_drafts(rows: Sequence[entities.Core3SkuBattlefieldScore]) -> list[DimensionDraft]:
    return [
        DimensionDraft(
            dimension_type="battlefield",
            code=row.battlefield_code,
            name=row.battlefield_name_cn,
            score=_q4(row.battlefield_score),
            confidence=_q4(row.confidence),
            relation_level=row.relation_level,
            value_layer=None,
            source_module="M11",
            source_record_refs=({"table": "core3_sku_battlefield_score", "id": row.sku_battlefield_score_id},),
            support_breakdown=dict(row.score_breakdown_json or {}),
            evidence_ids=tuple(row.evidence_ids or ()),
            business_reason_cn=row.business_reason_cn,
        )
        for row in _select_allocatable_battlefield_rows(rows)
    ]


def _battlefield_drafts_from_portfolio(bundle: M116SkuBundle) -> list[DimensionDraft]:
    portfolio = getattr(bundle, "battlefield_portfolio", None)
    if portfolio is None:
        return []
    scores_by_code = {row.battlefield_code: row for row in bundle.battlefield_scores}
    rows: list[tuple[str, Mapping[str, Any]]] = []
    for relation_level, items in (
        ("main", portfolio.main_battlefields_json or []),
        ("secondary", portfolio.secondary_battlefields_json or []),
    ):
        for item in items:
            if isinstance(item, Mapping) and item.get("allocation_eligible", True):
                rows.append((relation_level, item))
    result: list[DimensionDraft] = []
    for relation_level, item in rows:
        code = str(item.get("battlefield_code") or "")
        if not code or code in NON_PRODUCT_BATTLEFIELD_CODES:
            continue
        row = scores_by_code.get(code)
        refs: list[dict[str, Any]] = [{"table": "core3_sku_battlefield_portfolio", "id": portfolio.sku_battlefield_portfolio_id}]
        if row is not None:
            refs.append({"table": "core3_sku_battlefield_score", "id": row.sku_battlefield_score_id})
        score = _q4(item.get("battlefield_score") or (row.battlefield_score if row is not None else Decimal("0")))
        confidence = _q4(item.get("confidence") or (row.confidence if row is not None else Decimal("0")))
        preset_weight = _q6(item.get("allocation_weight"))
        support_breakdown = dict(row.score_breakdown_json if row is not None else {})
        support_breakdown.update(
            {
                "allocation_policy": "m11_v2_portfolio",
                "portfolio_role": item.get("allocation_role") or f"{relation_level}_battlefield",
                "portfolio_allocation_weight": str(preset_weight),
                "market_pool_key": item.get("market_pool_key"),
                "screen_size_class": item.get("screen_size_class"),
                "price_position": item.get("price_position"),
                "product_anchor_score": item.get("product_anchor_score"),
                "product_anchor_groups": item.get("product_anchor_groups") or [],
                "battlefield_v2": item.get("battlefield_v2") or {},
            }
        )
        result.append(
            DimensionDraft(
                dimension_type="battlefield",
                code=code,
                name=str(item.get("battlefield_name_cn") or (row.battlefield_name_cn if row is not None else code)),
                score=score,
                confidence=confidence,
                relation_level=relation_level,
                value_layer=None,
                source_module="M11 portfolio",
                source_record_refs=tuple(refs),
                support_breakdown=support_breakdown,
                evidence_ids=tuple(row.evidence_ids or ()) if row is not None else (),
                business_reason_cn=str(item.get("business_reason_cn") or (row.business_reason_cn if row is not None else "来自 M11 新版战场组合。")),
                normalized_weight=preset_weight,
            )
        )
    return result


def _select_allocatable_task_rows(rows: Sequence[entities.Core3SkuTaskScore]) -> list[entities.Core3SkuTaskScore]:
    return _select_allocatable_rows(
        rows,
        score_getter=lambda row: _q4(row.task_score),
        relation_getter=lambda row: str(row.relation_level),
        limit=TASK_ALLOCATION_LIMIT,
        fallback_relations=TASK_GROUP_FALLBACK_RELATIONS,
    )


def _select_allocatable_target_group_rows(
    rows: Sequence[entities.Core3SkuTargetGroupScore],
) -> list[entities.Core3SkuTargetGroupScore]:
    return _select_allocatable_rows(
        rows,
        score_getter=lambda row: _q4(row.target_group_score),
        relation_getter=lambda row: str(row.relation_level),
        limit=TARGET_GROUP_ALLOCATION_LIMIT,
        fallback_relations=TASK_GROUP_FALLBACK_RELATIONS,
    )


def _select_allocatable_battlefield_rows(
    rows: Sequence[entities.Core3SkuBattlefieldScore],
) -> list[entities.Core3SkuBattlefieldScore]:
    product_rows = [row for row in rows if row.battlefield_code not in NON_PRODUCT_BATTLEFIELD_CODES]
    return _select_allocatable_rows(
        product_rows,
        score_getter=lambda row: _q4(row.battlefield_score),
        relation_getter=lambda row: str(row.relation_level),
        limit=BATTLEFIELD_ALLOCATION_LIMIT,
        fallback_relations=BATTLEFIELD_FALLBACK_RELATIONS,
    )


def _select_allocatable_rows(
    rows: Sequence[Any],
    *,
    score_getter: Any,
    relation_getter: Any,
    limit: int,
    fallback_relations: set[str],
) -> list[Any]:
    scored_rows = [row for row in rows if score_getter(row) > 0]
    if not scored_rows:
        return []
    ordered = sorted(scored_rows, key=lambda row: (score_getter(row), relation_getter(row)), reverse=True)
    eligible = [row for row in ordered if relation_getter(row) in ALLOCATABLE_RELATIONS]
    if eligible:
        return eligible[:limit]
    fallback = [
        row
        for row in ordered
        if relation_getter(row) in fallback_relations and score_getter(row) >= DIMENSION_FALLBACK_MIN_SCORE
    ]
    if fallback:
        return fallback[:1]
    return ordered[:1]


def _claim_drafts(rows: Sequence[entities.Core3SkuClaimValueLayer]) -> list[DimensionDraft]:
    grouped: dict[str, list[entities.Core3SkuClaimValueLayer]] = defaultdict(list)
    for row in rows:
        if _q4(row.claim_value_score) > 0:
            grouped[row.claim_code].append(row)
    drafts: list[DimensionDraft] = []
    for claim_code, claim_rows in grouped.items():
        best = max(claim_rows, key=lambda item: (_q4(item.claim_value_score), _layer_priority(item.layer)))
        score = _q4(max(_q4(row.claim_value_score) for row in claim_rows))
        confidence = _q4(max(_q4(row.confidence) for row in claim_rows))
        refs = tuple({"table": "core3_sku_claim_value_layer", "id": row.sku_claim_value_layer_id} for row in claim_rows[:5])
        evidence_ids = tuple(dict.fromkeys(eid for row in claim_rows for eid in (row.evidence_ids or [])))
        drafts.append(
            DimensionDraft(
                dimension_type="claim",
                code=claim_code,
                name=best.claim_name_cn,
                score=score,
                confidence=confidence,
                relation_level=best.battlefield_relevance_role,
                value_layer=best.layer,
                source_module="M11.5",
                source_record_refs=refs,
                support_breakdown={
                    "battlefield_count": len({row.battlefield_code for row in claim_rows}),
                    "best_battlefield_code": best.battlefield_code,
                    "best_battlefield_name": best.battlefield_name_cn,
                    "layer_counts": dict(Counter(row.layer for row in claim_rows)),
                },
                evidence_ids=evidence_ids,
                business_reason_cn=best.business_reason_cn,
            )
        )
    return drafts


def _inferred_claim_drafts(bundle: M116SkuBundle) -> list[DimensionDraft]:
    summary = dict(bundle.profile.claim_activation_summary_json or {})
    top_claims = list(summary.get("top_claims") or [])
    if not top_claims:
        return []

    drafts: list[DimensionDraft] = []
    seen: set[str] = set()
    for item in top_claims:
        claim_code = str(item.get("claim_code_hint") or item.get("claim_code") or "").strip()
        if not claim_code or claim_code in seen:
            continue
        score = _q4(_decimal_or_none(item.get("final_activation_score")) or Decimal("0.0000"))
        confidence = _q4(_decimal_or_none(item.get("confidence")) or Decimal("0.0000"))
        activation_basis = str(item.get("activation_basis") or "unknown")
        perception_status = str(item.get("perception_status") or "unknown")
        activation_level = str(item.get("activation_level") or "unknown")
        if not _is_usable_inferred_claim(
            score=score,
            confidence=confidence,
            activation_basis=activation_basis,
            perception_status=perception_status,
        ):
            continue
        inferred_score = _inferred_claim_score(
            activation_score=score,
            confidence=confidence,
            activation_basis=activation_basis,
            perception_status=perception_status,
        )
        if inferred_score <= 0:
            continue
        value_layer = _inferred_value_layer(activation_basis=activation_basis, perception_status=perception_status)
        evidence_ids = _inferred_claim_evidence_ids(bundle, item)
        business_reason_cn = _inferred_claim_reason(
            claim_name=str(item.get("claim_name") or claim_code),
            activation_score=score,
            confidence=confidence,
            activation_basis=activation_basis,
            perception_status=perception_status,
        )
        drafts.append(
            DimensionDraft(
                dimension_type="claim",
                code=claim_code,
                name=str(item.get("claim_name") or claim_code),
                score=inferred_score,
                confidence=_q4(min(confidence, Decimal("0.6200"))),
                relation_level="inferred",
                value_layer=value_layer,
                source_module=CLAIM_INFERENCE_SOURCE_MODULE,
                source_record_refs=(
                    {
                        "table": "core3_sku_signal_profile",
                        "id": bundle.profile.sku_signal_profile_id,
                        "feature": "claim_activation_summary.top_claims",
                    },
                ),
                support_breakdown={
                    "inference_policy": "m11_6_claim_activation_fallback",
                    "activation_score": float(score),
                    "activation_level": activation_level,
                    "activation_basis": activation_basis,
                    "perception_status": perception_status,
                    "confidence": float(confidence),
                    "has_m11_5_layer": False,
                },
                evidence_ids=evidence_ids,
                business_reason_cn=business_reason_cn,
            )
        )
        seen.add(claim_code)
        if len(drafts) >= CLAIM_INFERENCE_LIMIT:
            break
    return drafts


def _is_usable_inferred_claim(
    *,
    score: Decimal,
    confidence: Decimal,
    activation_basis: str,
    perception_status: str,
) -> bool:
    if score < CLAIM_INFERENCE_MIN_SCORE or confidence < CLAIM_INFERENCE_MIN_CONFIDENCE:
        return False
    if activation_basis == "insufficient":
        return False
    if "param" in activation_basis and "comment" not in activation_basis and perception_status != "validated":
        return score >= CLAIM_INFERENCE_PARAM_ONLY_MIN_SCORE
    return True


def _inferred_claim_score(
    *,
    activation_score: Decimal,
    confidence: Decimal,
    activation_basis: str,
    perception_status: str,
) -> Decimal:
    source_bonus = Decimal("0.0000")
    if "param" in activation_basis:
        source_bonus += Decimal("0.0500")
    if "comment" in activation_basis or perception_status == "validated":
        source_bonus += Decimal("0.0700")
    raw = activation_score * Decimal("0.7000") + confidence * Decimal("0.2000") + min(source_bonus, Decimal("0.1000"))
    return _q4(min(raw, CLAIM_INFERENCE_MAX_SCORE))


def _inferred_value_layer(*, activation_basis: str, perception_status: str) -> str:
    if "param" in activation_basis and ("comment" in activation_basis or perception_status == "validated"):
        return "param_comment_inferred"
    if "param" in activation_basis:
        return "param_inferred"
    if "comment" in activation_basis or perception_status == "validated":
        return "comment_inferred"
    return "activation_inferred"


def _inferred_claim_reason(
    *,
    claim_name: str,
    activation_score: Decimal,
    confidence: Decimal,
    activation_basis: str,
    perception_status: str,
) -> str:
    source_cn = []
    if "param" in activation_basis:
        source_cn.append("参数证据")
    if "comment" in activation_basis or perception_status == "validated":
        source_cn.append("评论验证")
    if not source_cn:
        source_cn.append("卖点激活")
    return (
        f"{claim_name} 未形成 M11.5 战场内价值层，但 M08/M04b 已有{'、'.join(source_cn)}；"
        f"激活分 {activation_score}、置信度 {confidence}，作为低置信卖点维度参与 SKU 画像和销量解释，需复核。"
    )


def _inferred_claim_evidence_ids(bundle: M116SkuBundle, item: Mapping[str, Any]) -> tuple[str, ...]:
    evidence_ids: list[str] = []
    for key in ("evidence_ids", "param_evidence_ids", "promo_evidence_ids", "comment_evidence_ids", "comment_signal_ids"):
        values = item.get(key) or []
        if isinstance(values, list):
            evidence_ids.extend(str(value) for value in values if value)
    evidence_ids.extend(str(value) for value in list(bundle.profile.representative_evidence_ids or [])[:20] if value)
    return tuple(list(dict.fromkeys(evidence_ids))[:80])


def _rank_dimensions(drafts: Sequence[DimensionDraft]) -> list[DimensionDraft]:
    result: list[DimensionDraft] = []
    grouped = _group_dimensions(drafts)
    for dimension_type in DIMENSION_TYPES:
        items = sorted(
            _dedupe_dimension_drafts(grouped.get(dimension_type, ())),
            key=lambda item: (item.score, item.confidence, item.code),
            reverse=True,
        )
        preset_weights = [_preset_normalized_weight(item) for item in items]
        use_preset_weights = dimension_type == "battlefield" and any(weight > 0 for weight in preset_weights)
        total = sum((preset_weights if use_preset_weights else [item.score for item in items]), Decimal("0"))
        for index, item in enumerate(items, start=1):
            base_weight = _preset_normalized_weight(item) if use_preset_weights else item.score
            weight = _q6(base_weight / total) if total > 0 else Decimal("0.000000")
            result.append(
                DimensionDraft(
                    dimension_type=item.dimension_type,
                    code=item.code,
                    name=item.name,
                    score=item.score,
                    confidence=item.confidence,
                    relation_level=item.relation_level,
                    value_layer=item.value_layer,
                    source_module=item.source_module,
                    source_record_refs=item.source_record_refs,
                    support_breakdown=item.support_breakdown,
                    evidence_ids=item.evidence_ids,
                    business_reason_cn=item.business_reason_cn,
                    normalized_weight=weight,
                    rank=index,
                )
            )
    return result


def _dedupe_dimension_drafts(items: Sequence[DimensionDraft]) -> list[DimensionDraft]:
    grouped: dict[str, list[DimensionDraft]] = defaultdict(list)
    for item in items:
        grouped[item.code].append(item)
    result: list[DimensionDraft] = []
    for code, duplicates in grouped.items():
        if len(duplicates) == 1:
            result.append(duplicates[0])
            continue
        best = max(duplicates, key=lambda item: (item.score, item.confidence, item.relation_level, item.name))
        evidence_ids = tuple(dict.fromkeys(evidence_id for item in duplicates for evidence_id in item.evidence_ids))
        merged_refs = _dedupe_source_refs(ref for item in duplicates for ref in item.source_record_refs)
        result.append(
            DimensionDraft(
                dimension_type=best.dimension_type,
                code=code,
                name=best.name,
                score=max(item.score for item in duplicates),
                confidence=max(item.confidence for item in duplicates),
                relation_level=best.relation_level,
                value_layer=best.value_layer,
                source_module=best.source_module,
                source_record_refs=merged_refs[:12],
                support_breakdown={
                    "dedupe_policy": "same_sku_dimension_code_max_score",
                    "duplicate_count": len(duplicates),
                    "source_modules": sorted({item.source_module for item in duplicates}),
                    "best_support_breakdown": best.support_breakdown,
                },
                evidence_ids=evidence_ids[:80],
                business_reason_cn=best.business_reason_cn,
                normalized_weight=best.normalized_weight,
            )
        )
    return result


def _preset_normalized_weight(item: DimensionDraft) -> Decimal:
    if item.normalized_weight > 0:
        return _q6(item.normalized_weight)
    return _q6(item.support_breakdown.get("portfolio_allocation_weight"))


def _dedupe_source_refs(refs: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        key = stable_hash(dict(ref), version="m116_source_ref_dedupe_v1")
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(ref))
    return tuple(result)


def _dimension_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    profile: entities.Core3SkuSignalProfile,
    profile_id: str,
    draft: DimensionDraft,
    input_fingerprint: str,
    rule_version: str,
) -> M116SkuBusinessProfileDimensionRecord:
    payload = {
        "sku": profile.sku_code,
        "dimension_type": draft.dimension_type,
        "dimension_code": draft.code,
        "score": str(draft.score),
        "weight": str(draft.normalized_weight),
        "confidence": str(draft.confidence),
        "refs": draft.source_record_refs,
    }
    return M116SkuBusinessProfileDimensionRecord(
        profile_dimension_id=_record_id("m116_dimension", profile.sku_code, draft.dimension_type, draft.code, input_fingerprint),
        sku_business_profile_id=profile_id,
        project_id=profile.project_id,
        category_code=profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_code=profile.sku_code,
        dimension_type=draft.dimension_type,
        dimension_code=draft.code,
        dimension_name=draft.name,
        dimension_rank=draft.rank,
        dimension_score=draft.score,
        normalized_weight=draft.normalized_weight,
        evidence_level=_evidence_level(draft.confidence),
        relation_level=draft.relation_level,
        value_layer=draft.value_layer,
        source_module=draft.source_module,
        source_record_refs_json=list(draft.source_record_refs),
        support_breakdown_json=draft.support_breakdown,
        evidence_ids=list(draft.evidence_ids),
        confidence=draft.confidence,
        business_reason_cn=draft.business_reason_cn,
        rule_version=rule_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(payload, version="m116_dimension_result_v1"),
    )


def _allocation_record(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    profile: entities.Core3SkuSignalProfile,
    profile_id: str,
    dimension_id: str,
    draft: DimensionDraft,
    market: MarketSnapshot,
    input_fingerprint: str,
    rule_version: str,
) -> M116SkuBusinessProfileSalesAllocationRecord:
    allocated_volume = _q4(market.sales_volume_total * draft.normalized_weight) if market.sales_volume_total is not None else None
    allocated_amount = _q4(market.sales_amount_total * draft.normalized_weight) if market.sales_amount_total is not None else None
    payload = {
        "sku": profile.sku_code,
        "dimension_type": draft.dimension_type,
        "dimension_code": draft.code,
        "weight": str(draft.normalized_weight),
        "allocated_volume": str(allocated_volume),
        "allocated_amount": str(allocated_amount),
    }
    return M116SkuBusinessProfileSalesAllocationRecord(
        sales_allocation_id=_record_id("m116_allocation", profile.sku_code, draft.dimension_type, draft.code, input_fingerprint),
        sku_business_profile_id=profile_id,
        profile_dimension_id=dimension_id,
        project_id=profile.project_id,
        category_code=profile.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_code=profile.sku_code,
        dimension_type=draft.dimension_type,
        dimension_code=draft.code,
        dimension_name=draft.name,
        allocation_weight=draft.normalized_weight,
        allocated_sales_volume=allocated_volume,
        allocated_sales_amount=allocated_amount,
        allocation_confidence=_q4((draft.confidence + market.confidence) / Decimal("2")),
        allocation_basis_json={
            "dimension_score": float(draft.score),
            "market_source": market.source,
            "method_note_cn": "在 SKU 内按维度分数归一后分配该 SKU 的销量和销额；全局维度守恒由 M11.7 校验。",
        },
        rule_version=rule_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(payload, version="m116_allocation_result_v1"),
    )


def _review_issue(
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    project_id: str,
    category_code: str,
    profile_id: str | None = None,
    sku_code: str,
    issue_type: str,
    issue_level: str,
    issue_message_cn: str,
    suggested_action_cn: str,
    issue_context: Mapping[str, Any],
    input_fingerprint: str,
    rule_version: str,
    dimension_type: str = "",
    dimension_code: str = "",
) -> M116SkuBusinessProfileReviewIssueRecord:
    payload = {
        "sku": sku_code,
        "dimension_type": dimension_type,
        "dimension_code": dimension_code,
        "issue_type": issue_type,
        "issue_context": dict(issue_context),
    }
    return M116SkuBusinessProfileReviewIssueRecord(
        sku_business_profile_review_issue_id=_record_id("m116_review", sku_code, dimension_type, dimension_code, issue_type, input_fingerprint),
        sku_business_profile_id=profile_id,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        sku_code=sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        issue_type=issue_type,
        issue_level=issue_level,
        issue_message_cn=issue_message_cn,
        suggested_action_cn=suggested_action_cn,
        issue_context_json=dict(issue_context),
        rule_version=rule_version,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(payload, version="m116_review_result_v1"),
    )


def _market_snapshot(bundle: M116SkuBundle) -> MarketSnapshot:
    profile = bundle.profile
    summary = dict(profile.market_summary_json or {})
    market = bundle.market_profile
    source = "M08"

    def get_value(field: str) -> Any:
        nonlocal source
        if summary.get(field) not in (None, "", "-"):
            return summary.get(field)
        if market is not None and getattr(market, field, None) not in (None, "", "-"):
            source = "M07_fallback"
            return getattr(market, field)
        return None

    price_wavg = _decimal_or_none(get_value("price_wavg"))
    price_latest = _decimal_or_none(get_value("price_latest"))
    sales_volume = _decimal_or_none(get_value("sales_volume_total"))
    sales_amount = _decimal_or_none(get_value("sales_amount_total"))
    price = price_wavg or price_latest
    missing = []
    if sales_volume is None:
        missing.append("sales_volume_total")
    if sales_amount is None:
        missing.append("sales_amount_total")
    if price is None:
        missing.append("price_wavg_or_price_latest")
    price_percentile = _decimal_or_none(
        summary.get("price_percentile_in_pool")
        or summary.get("price_percentile")
        or (market.price_percentile_in_size if market is not None else None)
        or (market.price_percentile_in_category if market is not None else None)
    )
    sales_percentile = _decimal_or_none(
        summary.get("sales_percentile_in_pool")
        or summary.get("sales_percentile")
        or (market.volume_percentile_in_size if market is not None else None)
        or (market.volume_percentile_in_category if market is not None else None)
    )
    amount_percentile = _decimal_or_none(
        summary.get("amount_percentile_in_pool")
        or summary.get("sales_amount_percentile")
        or (market.amount_percentile_in_size if market is not None else None)
        or (market.amount_percentile_in_category if market is not None else None)
    )
    confidence = _decimal_or_none(summary.get("market_confidence") or summary.get("confidence")) or (
        _q4(market.market_confidence) if market is not None else Decimal("0.0000")
    )
    return MarketSnapshot(
        source=source,
        screen_size_inch=_decimal_or_none(summary.get("screen_size_inch") or (market.screen_size_inch if market is not None else None)),
        size_segment=str(summary.get("size_segment") or (market.size_segment if market is not None else "unknown") or "unknown"),
        price_band=str(
            summary.get("price_band")
            or summary.get("price_band_size")
            or (market.price_band_size if market is not None else None)
            or (market.price_band_category if market is not None else None)
            or "unknown"
        ),
        main_platform=summary.get("main_platform") or (market.main_platform if market is not None else None),
        sales_volume_total=sales_volume,
        sales_amount_total=sales_amount,
        price_wavg=price_wavg,
        price_latest=price_latest,
        price_percentile=_pct(price_percentile),
        sales_percentile=_pct(sales_percentile),
        amount_percentile=_pct(amount_percentile),
        price_gap_to_pool_median=_decimal_or_none(
            summary.get("price_gap_to_pool_median")
            or (market.price_gap_to_size_median if market is not None else None)
            or (market.price_gap_to_category_median if market is not None else None)
        ),
        sample_status=str(summary.get("sample_status") or (market.sample_status if market is not None else "unknown") or "unknown"),
        confidence=_pct(confidence),
        missing=tuple(missing),
    )


def _premium_profile(market: MarketSnapshot, claim_strength: Decimal, claim_drafts: Sequence[DimensionDraft]) -> dict[str, Any]:
    price_percentile = market.price_percentile or Decimal("0.5000")
    amount_percentile = market.amount_percentile or Decimal("0.5000")
    score = _q4(price_percentile * Decimal("0.45") + claim_strength * Decimal("0.35") + amount_percentile * Decimal("0.20"))
    premium_position = _premium_position(price_percentile)
    premium_claims = [item for item in claim_drafts if item.value_layer == "premium_tendency"]
    if price_percentile >= Decimal("0.75") and claim_strength >= Decimal("0.55") and amount_percentile >= Decimal("0.45"):
        premium_type = "value_supported_premium"
        support_level = "supported"
    elif price_percentile >= Decimal("0.65") and (claim_strength >= Decimal("0.45") or premium_claims):
        premium_type = "claim_led_premium_potential"
        support_level = "partially_supported"
    elif price_percentile >= Decimal("0.65") and claim_strength < Decimal("0.35"):
        premium_type = "price_high_value_weak"
        support_level = "unsupported"
    elif claim_strength >= Decimal("0.60") and price_percentile < Decimal("0.55"):
        premium_type = "value_underpriced"
        support_level = "potential"
    else:
        premium_type = "mass_value_position"
        support_level = "unknown"
    risks: list[dict[str, Any] | str] = []
    if market.missing:
        risks.append({"risk": "market_missing", "fields": list(market.missing)})
    if price_percentile >= Decimal("0.75") and claim_strength < Decimal("0.45"):
        risks.append("价格较高但卖点价值支撑偏弱")
    reason = f"价格位置为{premium_position}，卖点价值强度{claim_strength}，销额分位{amount_percentile}，综合溢价支撑分{score}。"
    return {
        "premium_position": premium_position,
        "premium_type": premium_type,
        "premium_support_level": support_level,
        "premium_score": score,
        "premium_reason_cn": reason,
        "premium_risk_json": risks,
    }


def _market_role(market: MarketSnapshot) -> tuple[str, str]:
    price = market.price_percentile or Decimal("0.5000")
    volume = market.sales_percentile or Decimal("0.5000")
    amount = market.amount_percentile or Decimal("0.5000")
    if amount >= Decimal("0.70") and price >= Decimal("0.65"):
        return "premium_volume_anchor", "销额和价格位置都高，是高价值量价锚点。"
    if volume >= Decimal("0.70") and price <= Decimal("0.50"):
        return "volume_driver", "销量分位高但价格不高，主要承担走量角色。"
    if price >= Decimal("0.75") and volume < Decimal("0.40"):
        return "premium_niche", "价格分位高但销量暂不突出，更像高端小众或形象款。"
    if volume < Decimal("0.30") and amount < Decimal("0.30"):
        return "long_tail", "销量和销额分位都偏低，当前更像长尾 SKU。"
    return "balanced_competitor", "量价位置居中，可作为常规对比和竞品召回对象。"


def _competitive_role_hints(market_role: str, battlefield: DimensionDraft | None, premium: Mapping[str, Any]) -> list[dict[str, Any]]:
    hints = [{"role": "scenario_substitute", "reason_cn": "同任务、同客群或同战场可进入替代候选。"}]
    if market_role in {"premium_volume_anchor", "premium_niche"} or premium.get("premium_support_level") in {"supported", "partially_supported"}:
        hints.append({"role": "benchmark_potential", "reason_cn": "具备高价或高价值卖点，可作为标杆参照。"})
    if market_role == "volume_driver":
        hints.append({"role": "price_volume_pressure", "reason_cn": "具备走量压力，可作为价格/销量挤压对象。"})
    if battlefield is not None:
        hints.append({"role": "battlefield_primary", "battlefield_code": battlefield.code, "reason_cn": "主战场是后续候选召回的优先边界。"})
    return hints


def _candidate_recall_priority(
    task: DimensionDraft | None,
    group: DimensionDraft | None,
    battlefield: DimensionDraft | None,
    claim_strength: Decimal,
    confidence: Decimal,
) -> dict[str, Any]:
    return {
        "priority_score": float(_q4(((task.score if task else Decimal("0")) + (group.score if group else Decimal("0")) + (battlefield.score if battlefield else Decimal("0")) + claim_strength + confidence) / Decimal("5"))),
        "preferred_task_code": task.code if task else None,
        "preferred_target_group_code": group.code if group else None,
        "preferred_battlefield_code": battlefield.code if battlefield else None,
        "claim_value_strength": float(claim_strength),
    }


def _sku_allocation_summary(drafts: Sequence[DimensionDraft], market: MarketSnapshot) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "allocation_method": "score_normalized_with_market_volume",
        "market_source": market.source,
        "sku_sales_volume_total": float(market.sales_volume_total) if market.sales_volume_total is not None else None,
        "sku_sales_amount_total": float(market.sales_amount_total) if market.sales_amount_total is not None else None,
        "dimension_types": {},
    }
    grouped = _group_dimensions(drafts)
    for dimension_type, items in grouped.items():
        summary["dimension_types"][dimension_type] = {
            "dimension_count": len(items),
            "weight_sum": float(_q6(sum(item.normalized_weight for item in items))),
            "top_dimensions": _dimension_refs(items[:5], include_value_layer=True),
        }
    return summary


def _allocation_totals(allocations: Sequence[M116SkuBusinessProfileSalesAllocationRecord]) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, Decimal]] = {}
    for row in allocations:
        bucket = result.setdefault(row.dimension_type, {"weight_sum": Decimal("0"), "sales_volume": Decimal("0"), "sales_amount": Decimal("0")})
        bucket["weight_sum"] += row.allocation_weight
        if row.allocated_sales_volume is not None:
            bucket["sales_volume"] += row.allocated_sales_volume
        if row.allocated_sales_amount is not None:
            bucket["sales_amount"] += row.allocated_sales_amount
    return {
        key: {
            "weight_sum": float(_q6(value["weight_sum"])),
            "sales_volume": float(_q4(value["sales_volume"])),
            "sales_amount": float(_q4(value["sales_amount"])),
        }
        for key, value in result.items()
    }


def _overall_confidence(
    profile: entities.Core3SkuSignalProfile,
    market: MarketSnapshot,
    task: DimensionDraft | None,
    group: DimensionDraft | None,
    battlefield: DimensionDraft | None,
    claim_strength: Decimal,
    issues: Sequence[M116SkuBusinessProfileReviewIssueRecord],
) -> Decimal:
    values = [
        _q4(profile.confidence),
        market.confidence,
        task.confidence if task else Decimal("0.0000"),
        group.confidence if group else Decimal("0.0000"),
        battlefield.confidence if battlefield else Decimal("0.0000"),
        claim_strength,
    ]
    confidence = _q4(sum(values) / Decimal(len(values)))
    if any(issue.issue_level == "blocker" for issue in issues):
        confidence = min(confidence, Decimal("0.4900"))
    return confidence


def _business_summary(
    profile: entities.Core3SkuSignalProfile,
    task: DimensionDraft | None,
    group: DimensionDraft | None,
    battlefield: DimensionDraft | None,
    market_role: str,
    premium: Mapping[str, Any],
) -> str:
    task_name = task.name if task else "任务证据不足"
    group_name = group.name if group else "客群证据不足"
    battlefield_name = battlefield.name if battlefield else "战场证据不足"
    return (
        f"{profile.brand_name or ''}{profile.model_name or profile.sku_code} 当前主任务为{task_name}，"
        f"主客群为{group_name}，主战场为{battlefield_name}；市场角色为{market_role}，"
        f"溢价判断为{premium['premium_support_level']}。"
    )


def _input_fingerprint(bundle: M116SkuBundle, market: MarketSnapshot, rule_version: str) -> str:
    return stable_hash(
        {
            "sku_profile": bundle.profile.result_hash,
            "market": {
                "source": market.source,
                "volume": str(market.sales_volume_total),
                "amount": str(market.sales_amount_total),
                "price": str(market.price_wavg or market.price_latest),
            },
            "task_hashes": [row.result_hash for row in bundle.task_scores],
            "group_hashes": [row.result_hash for row in bundle.target_group_scores],
            "battlefield_hashes": [row.result_hash for row in bundle.battlefield_scores],
            "portfolio_hash": bundle.battlefield_portfolio.result_hash if bundle.battlefield_portfolio is not None else None,
            "claim_layer_hashes": [row.result_hash for row in bundle.claim_value_layers],
            "claim_summary_hashes": [row.result_hash for row in bundle.claim_value_summaries],
            "rule_version": rule_version,
        },
        version="m116_input_fingerprint_v1",
    )


def _group_dimensions(drafts: Sequence[DimensionDraft]) -> dict[str, tuple[DimensionDraft, ...]]:
    result: dict[str, list[DimensionDraft]] = defaultdict(list)
    for draft in drafts:
        result[draft.dimension_type].append(draft)
    return {key: tuple(value) for key, value in result.items()}


def _dimension_refs(drafts: Sequence[DimensionDraft], *, include_value_layer: bool = False) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for draft in drafts:
        payload = {
            "dimension_type": draft.dimension_type,
            "dimension_code": draft.code,
            "dimension_name": draft.name,
            "rank": draft.rank,
            "score": float(draft.score),
            "weight": float(draft.normalized_weight),
            "confidence": float(draft.confidence),
        }
        if include_value_layer and draft.value_layer is not None:
            payload["value_layer"] = draft.value_layer
        refs.append(payload)
    return refs


def _claim_value_summary(claims: Sequence[DimensionDraft]) -> dict[str, Any]:
    return {
        "claim_count": len(claims),
        "layer_counts": dict(Counter(item.value_layer or "unknown" for item in claims)),
        "top_claims": _dimension_refs(claims[:8], include_value_layer=True),
    }


def _representative_evidence_ids(profile: entities.Core3SkuSignalProfile, drafts: Sequence[DimensionDraft]) -> list[str]:
    evidence_ids = list(profile.representative_evidence_ids or [])
    for draft in drafts[:20]:
        evidence_ids.extend(draft.evidence_ids[:5])
    return list(dict.fromkeys(evidence_ids))[:80]


def _missing_signals(
    profile: entities.Core3SkuSignalProfile,
    market: MarketSnapshot,
    issues: Sequence[M116SkuBusinessProfileReviewIssueRecord],
) -> list[dict[str, Any] | str]:
    result: list[dict[str, Any] | str] = list(profile.missing_signals_json or [])
    if market.missing:
        result.append({"signal": "market_required_fields", "missing_fields": list(market.missing)})
    result.extend({"signal": issue.issue_type, "level": issue.issue_level} for issue in issues)
    return result


def _first(items: Sequence[DimensionDraft] | None) -> DimensionDraft | None:
    return items[0] if items else None


def _avg_top_scores(items: Sequence[DimensionDraft], *, limit: int) -> Decimal:
    top_scores = [item.score for item in items[:limit]]
    if not top_scores:
        return Decimal("0.0000")
    return _q4(sum(top_scores) / Decimal(len(top_scores)))


def _layer_priority(layer: str) -> int:
    return {
        "premium_tendency": 5,
        "competitive_performance": 4,
        "basic_threshold": 3,
        "weak_perception": 2,
        "insufficient_sample": 1,
    }.get(layer, 0)


def _premium_position(price_percentile: Decimal) -> str:
    if price_percentile < Decimal("0.25"):
        return "discount"
    if price_percentile < Decimal("0.50"):
        return "mass"
    if price_percentile < Decimal("0.75"):
        return "upper_mass"
    if price_percentile < Decimal("0.90"):
        return "premium"
    return "super_premium"


def _evidence_level(value: Decimal) -> str:
    if value >= Decimal("0.75"):
        return "strong"
    if value >= Decimal("0.55"):
        return "medium"
    if value > Decimal("0.00"):
        return "weak"
    return "unknown"


def _confidence_level(value: Decimal) -> str:
    if value >= Decimal("0.75"):
        return Core3ConfidenceLevel.HIGH.value
    if value >= Decimal("0.55"):
        return Core3ConfidenceLevel.MEDIUM.value
    if value > Decimal("0.00"):
        return Core3ConfidenceLevel.LOW.value
    return Core3ConfidenceLevel.UNKNOWN.value


def _series_name(bundle: M116SkuBundle) -> str | None:
    master = dict(bundle.profile.sku_master_json or {})
    return master.get("series") or (bundle.market_profile.series if bundle.market_profile is not None else None)


def _record_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{stable_hash([str(part) for part in parts], version=prefix)[:32]}"


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _pct(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value > 1:
        value = value / Decimal("100")
    return min(max(_q4(value), Decimal("0.0000")), Decimal("1.0000"))


def _q4(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.0000")
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _q6(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.000000")
    return Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
