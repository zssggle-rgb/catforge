"""M11.7 dimension sales reconciliation service."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.battlefield_seed_loader import M11BattlefieldSeedLoader
from app.services.core3_real_data.claim_value_seed_loader import M115ClaimValueSeedLoader
from app.services.core3_real_data.constants import CORE3_M11_7_RULE_VERSION, Core3RunStatus
from app.services.core3_real_data.dimension_sales_reconciliation_repositories import (
    DimensionSalesReconciliationRepository,
)
from app.services.core3_real_data.dimension_sales_reconciliation_schemas import (
    M117BuildArtifacts,
    M117BusinessDimensionSalesSummaryRecord,
    M117BusinessDimensionSkuContributionRecord,
    M117BusinessSalesReconciliationCheckRecord,
    M117BusinessSalesReconciliationIssueRecord,
    M117ServiceResult,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.target_group_seed_loader import M10TargetGroupSeedLoader
from app.services.core3_real_data.task_seed_loader import M09TaskSeedLoader


BOUNDARY_NOTE_CN = "M11.7 只校验 M11.6 的销量分配是否横纵一致，不重新分配权重、不生成候选竞品、不输出最终业务结论。"
DIMENSION_TYPES = ("claim", "task", "target_group", "battlefield")
WEIGHT_TOLERANCE = Decimal("0.0001")
RATIO_TOLERANCE = Decimal("0.0001")
ZERO = Decimal("0")


@dataclass(frozen=True)
class StandardDimension:
    dimension_type: str
    code: str
    name: str
    rank: int


@dataclass(frozen=True)
class ContributionDraft:
    allocation: entities.Core3SkuBusinessProfileSalesAllocation
    profile: entities.Core3SkuBusinessProfile
    dimension: entities.Core3SkuBusinessProfileDimension | None
    dimension_name: str
    is_primary: bool


class DimensionSalesReconciliationService:
    def __init__(self, repository: DimensionSalesReconciliationRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M11_7_RULE_VERSION,
    ) -> M117ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        inputs = self.repository.load_inputs(batch_id, sku_scope)
        if not inputs.profiles:
            return M117ServiceResult(
                status=Core3RunStatus.WARNING,
                input_count=0,
                output_count=0,
                created_output_count=0,
                updated_output_count=0,
                reused_output_count=0,
                warnings=["M11.7 没有找到可校验的 M11.6 SKU 业务画像。"],
                summaries=(),
                contributions=(),
                checks=(),
                issues=(),
                summary={"batch_id": batch_id, "rule_version": rule_version, "sku_count": 0},
            )

        artifacts = self._build_artifacts(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_scope=tuple(sku_scope),
            profiles=inputs.profiles,
            dimensions=inputs.dimensions,
            allocations=inputs.allocations,
            m08_profile_count=inputs.m08_profile_count,
            rule_version=rule_version,
        )
        self.repository.mark_outputs_stale(batch_id=batch_id, rule_version=rule_version)
        summary_write = self.repository.save_summaries(artifacts.summaries)
        contributions = _remap_contribution_summary_ids(artifacts.contributions, summary_write.records)
        contribution_write = self.repository.save_contributions(contributions)
        check_write = self.repository.save_checks(artifacts.checks)
        issue_write = self.repository.save_issues(artifacts.issues)

        created = summary_write.created_count + contribution_write.created_count + check_write.created_count + issue_write.created_count
        updated = summary_write.updated_count + contribution_write.updated_count + check_write.updated_count + issue_write.updated_count
        reused = summary_write.reused_count + contribution_write.reused_count + check_write.reused_count + issue_write.reused_count
        issue_counts = Counter(issue.issue_code for issue in artifacts.issues)
        severity_counts = Counter(issue.severity for issue in artifacts.issues)
        blocker_count = severity_counts.get("blocker", 0)
        failed_check_count = sum(1 for check in artifacts.checks if check.status == "failed")
        warnings: list[str] = []
        if artifacts.issues:
            warnings.append(f"M11.7 生成 {len(artifacts.issues)} 条销量对账问题，其中阻断级 {blocker_count} 条。")
        if failed_check_count:
            warnings.append(f"M11.7 有 {failed_check_count} 条对账检查未通过，M12 需等待修复后再执行。")
        status = Core3RunStatus.BLOCKED if blocker_count else (Core3RunStatus.WARNING if artifacts.issues else Core3RunStatus.SUCCESS)
        dimension_type_totals = _dimension_type_totals(artifacts.summaries)
        return M117ServiceResult(
            status=status,
            input_count=len(inputs.profiles),
            output_count=len(artifacts.summaries) + len(contributions) + len(artifacts.checks) + len(artifacts.issues),
            created_output_count=created,
            updated_output_count=updated,
            reused_output_count=reused,
            warnings=warnings,
            summaries=artifacts.summaries,
            contributions=contributions,
            checks=artifacts.checks,
            issues=artifacts.issues,
            summary={
                "batch_id": batch_id,
                "rule_version": rule_version,
                "sku_count": len(inputs.profiles),
                "dimension_sales_summary_count": len(artifacts.summaries),
                "sku_contribution_count": len(contributions),
                "reconciliation_check_count": len(artifacts.checks),
                "reconciliation_issue_count": len(artifacts.issues),
                "failed_check_count": failed_check_count,
                "blocking_issue_count": blocker_count,
                "review_issue_counts": dict(issue_counts),
                "review_issue_severity_counts": dict(severity_counts),
                "m12_admission_status": "blocked" if blocker_count or failed_check_count else "allowed",
                "standard_dimension_counts": dict(Counter(summary.dimension_type for summary in artifacts.summaries)),
                "dimension_type_totals": dimension_type_totals,
                "created_output_count": created,
                "updated_output_count": updated,
                "reused_output_count": reused,
                "boundary_note": BOUNDARY_NOTE_CN,
                "downstream_support": {
                    "M12": "只有 M11.7 无阻断问题时，候选竞品召回才能消费画像维度和销量口径。",
                    "M15": "可展示各价值战场、客群、任务和卖点的估算销量结构。",
                    "M16": "复核 M11.6-M11.7 是否满足全局销量守恒。",
                },
            },
        )

    def _build_artifacts(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        sku_scope: tuple[str, ...],
        profiles: Sequence[entities.Core3SkuBusinessProfile],
        dimensions: Sequence[entities.Core3SkuBusinessProfileDimension],
        allocations: Sequence[entities.Core3SkuBusinessProfileSalesAllocation],
        m08_profile_count: int,
        rule_version: str,
    ) -> M117BuildArtifacts:
        standard_dimensions = _standard_dimensions()
        standard_by_key = {(item.dimension_type, item.code): item for item in standard_dimensions}
        profiles_by_sku = {profile.sku_code: profile for profile in profiles}
        dimensions_by_key = {
            (dimension.sku_code, dimension.dimension_type, dimension.dimension_code): dimension
            for dimension in dimensions
        }
        source_m11_6_module_run_id = next((profile.module_run_id for profile in profiles if profile.module_run_id), None)
        total_volume = _q4(sum((_decimal(profile.sales_volume_total) or ZERO) for profile in profiles))
        total_amount = _q4(sum((_decimal(profile.sales_amount_total) or ZERO) for profile in profiles))
        contribution_drafts: list[ContributionDraft] = []
        checks: list[M117BusinessSalesReconciliationCheckRecord] = []
        issues: list[M117BusinessSalesReconciliationIssueRecord] = []

        checks.append(
            _check(
                project_id=self.repository.project_id,
                category_code=self.repository.category_code.value,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                source_m11_6_module_run_id=source_m11_6_module_run_id,
                check_type="sku_scope_consistency",
                expected=m08_profile_count if not sku_scope else len(sku_scope),
                actual=len(profiles),
                tolerance=Decimal("0"),
                issue_scope="global",
                failure_reason_code="sku_scope_not_aligned",
                failure_reason_cn="M11.7 可校验 SKU 数与上游 SKU 数不一致。",
                suggestion_cn="确认是否为局部重跑；若不是局部重跑，请先重跑 M11.6 后再执行 M11.7。",
                payload={"m08_profile_count": m08_profile_count, "m11_6_profile_count": len(profiles), "sku_scope": list(sku_scope)},
                rule_version=rule_version,
            )
        )

        for allocation in allocations:
            profile = profiles_by_sku.get(allocation.sku_code)
            if profile is None:
                checks.append(
                    _failed_check(
                        project_id=self.repository.project_id,
                        category_code=self.repository.category_code.value,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        source_m11_6_module_run_id=source_m11_6_module_run_id,
                        check_type="allocation_profile_link",
                        sku_code=allocation.sku_code,
                        dimension_type=allocation.dimension_type,
                        dimension_code=allocation.dimension_code,
                        failure_reason_code="allocation_without_profile",
                        failure_reason_cn="存在 M11.6 销量分配记录，但找不到对应 SKU 业务画像。",
                        payload={"sales_allocation_id": allocation.sales_allocation_id},
                        rule_version=rule_version,
                    )
                )
                continue
            standard = standard_by_key.get((allocation.dimension_type, allocation.dimension_code))
            if standard is None:
                checks.append(
                    _failed_check(
                        project_id=self.repository.project_id,
                        category_code=self.repository.category_code.value,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        source_m11_6_module_run_id=source_m11_6_module_run_id,
                        check_type="standard_dimension_code",
                        sku_code=allocation.sku_code,
                        dimension_type=allocation.dimension_type,
                        dimension_code=allocation.dimension_code,
                        failure_reason_code="dimension_code_not_in_seed",
                        failure_reason_cn="M11.6 分配结果中出现标准全集之外的维度编码。",
                        payload={"dimension_code": allocation.dimension_code, "dimension_type": allocation.dimension_type},
                        rule_version=rule_version,
                    )
                )
                continue
            dimension = dimensions_by_key.get((allocation.sku_code, allocation.dimension_type, allocation.dimension_code))
            contribution_drafts.append(
                ContributionDraft(
                    allocation=allocation,
                    profile=profile,
                    dimension=dimension,
                    dimension_name=standard.name,
                    is_primary=_is_primary(profile, allocation.dimension_type, allocation.dimension_code, dimension),
                )
            )

        checks.extend(
            _sku_checks(
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            run_id=run_id,
                module_run_id=module_run_id,
                source_m11_6_module_run_id=source_m11_6_module_run_id,
                profiles=profiles,
                allocations=allocations,
                standard_by_key=standard_by_key,
                rule_version=rule_version,
            )
        )
        grouped_contributions: dict[tuple[str, str], list[ContributionDraft]] = defaultdict(list)
        for draft in contribution_drafts:
            grouped_contributions[(draft.allocation.dimension_type, draft.allocation.dimension_code)].append(draft)

        type_volume_actual: dict[str, Decimal] = defaultdict(lambda: ZERO)
        type_amount_actual: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for draft in contribution_drafts:
            type_volume_actual[draft.allocation.dimension_type] += _decimal(draft.allocation.allocated_sales_volume) or ZERO
            type_amount_actual[draft.allocation.dimension_type] += _decimal(draft.allocation.allocated_sales_amount) or ZERO
        global_status_by_type: dict[str, str] = {}
        for dimension_type in DIMENSION_TYPES:
            volume_check = _check(
                project_id=self.repository.project_id,
                category_code=self.repository.category_code.value,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                source_m11_6_module_run_id=source_m11_6_module_run_id,
                check_type="global_dimension_volume_total",
                dimension_type=dimension_type,
                expected=total_volume,
                actual=type_volume_actual[dimension_type],
                tolerance=_volume_tolerance(total_volume),
                issue_scope="dimension_type",
                failure_reason_code="global_dimension_volume_not_conserved",
                failure_reason_cn="该维度类型的估算销量合计与全 SKU 总销量不一致。",
                suggestion_cn="检查 M11.6 是否对每个 SKU 在该维度类型下分配了完整权重。",
                payload={"dimension_type": dimension_type},
                rule_version=rule_version,
            )
            amount_check = _check(
                project_id=self.repository.project_id,
                category_code=self.repository.category_code.value,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                source_m11_6_module_run_id=source_m11_6_module_run_id,
                check_type="global_dimension_amount_total",
                dimension_type=dimension_type,
                expected=total_amount,
                actual=type_amount_actual[dimension_type],
                tolerance=_amount_tolerance(total_amount),
                issue_scope="dimension_type",
                failure_reason_code="global_dimension_amount_not_conserved",
                failure_reason_cn="该维度类型的估算销额合计与全 SKU 总销额不一致。",
                suggestion_cn="检查 M11.6 是否对每个 SKU 在该维度类型下分配了完整权重。",
                payload={"dimension_type": dimension_type},
                rule_version=rule_version,
            )
            checks.extend([volume_check, amount_check])
            global_status_by_type[dimension_type] = "matched" if volume_check.status == "passed" and amount_check.status == "passed" else "mismatched"

        summaries: list[M117BusinessDimensionSalesSummaryRecord] = []
        summary_id_by_key: dict[tuple[str, str], str] = {}
        contributions: list[M117BusinessDimensionSkuContributionRecord] = []
        for standard in standard_dimensions:
            key = (standard.dimension_type, standard.code)
            drafts = grouped_contributions.get(key, [])
            estimated_volume = _q4(sum((_decimal(draft.allocation.allocated_sales_volume) or ZERO) for draft in drafts))
            estimated_amount = _q4(sum((_decimal(draft.allocation.allocated_sales_amount) or ZERO) for draft in drafts))
            avg_confidence = _average(draft.allocation.allocation_confidence for draft in drafts)
            summary_fingerprint = stable_hash(
                {
                    "batch_id": batch_id,
                    "dimension_type": standard.dimension_type,
                    "dimension_code": standard.code,
                    "volume": str(estimated_volume),
                    "amount": str(estimated_amount),
                    "sku_count": len(drafts),
                    "rule_version": rule_version,
                },
                version="m117_summary_input_v1",
            )
            summary_id = _record_id("m117_summary", standard.dimension_type, standard.code, summary_fingerprint)
            summary_id_by_key[key] = summary_id
            top_skus = _top_sku_contribution(drafts)
            evidence_quality_summary = _evidence_quality_summary(drafts)
            if standard.dimension_type == "battlefield":
                evidence_quality_summary["battlefield_v2_summary"] = _battlefield_v2_summary(drafts)
            summary = M117BusinessDimensionSalesSummaryRecord(
                dimension_sales_summary_id=summary_id,
                project_id=self.repository.project_id,
                category_code=self.repository.category_code.value,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                source_m11_6_module_run_id=source_m11_6_module_run_id,
                dimension_type=standard.dimension_type,
                dimension_code=standard.code,
                dimension_name=standard.name,
                standard_dimension_rank=standard.rank,
                sku_count=len({draft.profile.sku_code for draft in drafts}),
                primary_sku_count=sum(1 for draft in drafts if draft.is_primary),
                estimated_sales_volume=estimated_volume,
                estimated_sales_amount=estimated_amount,
                total_market_sales_volume=total_volume,
                total_market_sales_amount=total_amount,
                sales_volume_share=_ratio(estimated_volume, total_volume),
                sales_amount_share=_ratio(estimated_amount, total_amount),
                avg_allocation_confidence=avg_confidence,
                evidence_quality_summary_json=evidence_quality_summary,
                top_sku_contribution_json=top_skus,
                reconciliation_status=global_status_by_type[standard.dimension_type],
                business_summary_cn=_summary_cn(
                    standard=standard,
                    drafts=drafts,
                    estimated_volume=estimated_volume,
                    total_volume=total_volume,
                ),
                input_fingerprint=summary_fingerprint,
                result_hash=stable_hash(
                    {"summary_id": summary_id, "top_skus": top_skus, "status": global_status_by_type[standard.dimension_type]},
                    version="m117_summary_result_v1",
                ),
                processing_status="success" if global_status_by_type[standard.dimension_type] == "matched" else "warning",
                review_required=global_status_by_type[standard.dimension_type] != "matched",
                review_status="auto_pass" if global_status_by_type[standard.dimension_type] == "matched" else "review_required",
                review_reason_json={"global_reconciliation_status": global_status_by_type[standard.dimension_type]},
                rule_version=rule_version,
            )
            summaries.append(summary)

        for draft in contribution_drafts:
            key = (draft.allocation.dimension_type, draft.allocation.dimension_code)
            dimension_total_volume = _q4(
                sum((_decimal(item.allocation.allocated_sales_volume) or ZERO) for item in grouped_contributions.get(key, ()))
            )
            dimension_total_amount = _q4(
                sum((_decimal(item.allocation.allocated_sales_amount) or ZERO) for item in grouped_contributions.get(key, ()))
            )
            fingerprint = stable_hash(
                {
                    "batch_id": batch_id,
                    "sku_code": draft.profile.sku_code,
                    "dimension_type": draft.allocation.dimension_type,
                    "dimension_code": draft.allocation.dimension_code,
                    "sales_allocation_id": draft.allocation.sales_allocation_id,
                    "allocation_hash": draft.allocation.result_hash,
                    "rule_version": rule_version,
                },
                version="m117_contribution_input_v1",
            )
            contributions.append(
                M117BusinessDimensionSkuContributionRecord(
                    dimension_sku_contribution_id=_record_id("m117_contribution", draft.profile.sku_code, draft.allocation.dimension_type, draft.allocation.dimension_code, fingerprint),
                    dimension_sales_summary_id=summary_id_by_key.get(key),
                    sku_business_profile_id=draft.profile.sku_business_profile_id,
                    sales_allocation_id=draft.allocation.sales_allocation_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code.value,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    dimension_type=draft.allocation.dimension_type,
                    dimension_code=draft.allocation.dimension_code,
                    dimension_name=draft.dimension_name,
                    sku_code=draft.profile.sku_code,
                    brand_name=draft.profile.brand_name,
                    model_name=draft.profile.model_name,
                    allocation_weight=_q6(_decimal(draft.allocation.allocation_weight) or ZERO),
                    allocated_sales_volume=_q4(_decimal(draft.allocation.allocated_sales_volume) or ZERO),
                    allocated_sales_amount=_q4(_decimal(draft.allocation.allocated_sales_amount) or ZERO),
                    sku_share_in_dimension_volume=_ratio(_decimal(draft.allocation.allocated_sales_volume) or ZERO, dimension_total_volume),
                    sku_share_in_dimension_amount=_ratio(_decimal(draft.allocation.allocated_sales_amount) or ZERO, dimension_total_amount),
                    is_primary_dimension=draft.is_primary,
                    allocation_confidence=_q4(_decimal(draft.allocation.allocation_confidence) or ZERO),
                    evidence_level=draft.dimension.evidence_level if draft.dimension is not None else "unknown",
                    contribution_reason_cn=(
                        f"{draft.profile.model_name or draft.profile.sku_code} 对“{draft.dimension_name}”贡献 "
                        f"{_q4(_decimal(draft.allocation.allocated_sales_volume) or ZERO)} 估算销量，"
                        f"来自 M11.6 的 SKU 内权重 {(_q6(_decimal(draft.allocation.allocation_weight) or ZERO) * Decimal('100')).quantize(Decimal('0.01'))}%。"
                    ),
                    evidence_ids=list(draft.dimension.evidence_ids if draft.dimension is not None else []),
                    input_fingerprint=fingerprint,
                    result_hash=stable_hash({"fingerprint": fingerprint, "share": str(_ratio(_decimal(draft.allocation.allocated_sales_volume) or ZERO, dimension_total_volume))}, version="m117_contribution_result_v1"),
                    rule_version=rule_version,
                )
            )

        issues.extend(_issues_from_checks(checks, batch_id=batch_id, run_id=run_id, module_run_id=module_run_id, rule_version=rule_version))
        return M117BuildArtifacts(
            summaries=tuple(summaries),
            contributions=tuple(contributions),
            checks=tuple(checks),
            issues=tuple(issues),
        )


def _standard_dimensions() -> tuple[StandardDimension, ...]:
    claim_seed = M115ClaimValueSeedLoader().load()
    task_seed = M09TaskSeedLoader().load()
    group_seed = M10TargetGroupSeedLoader().load()
    battlefield_seed = M11BattlefieldSeedLoader().load()
    result: list[StandardDimension] = []
    result.extend(
        StandardDimension("claim", str(item["claim_code"]), str(item["claim_name"]), index + 1)
        for index, item in enumerate(claim_seed.standard_claims)
    )
    result.extend(
        StandardDimension("task", str(item["task_code"]), str(item["task_name"]), index + 1)
        for index, item in enumerate(task_seed.tasks)
    )
    result.extend(
        StandardDimension("target_group", str(item["target_group_code"]), str(item["target_group_name"]), index + 1)
        for index, item in enumerate(group_seed.target_groups)
    )
    result.extend(
        StandardDimension("battlefield", str(item["battlefield_code"]), str(item["battlefield_name"]), index + 1)
        for index, item in enumerate(battlefield_seed.battlefields)
    )
    return tuple(result)


def _sku_checks(
    *,
    batch_id: str,
    project_id: str,
    category_code: str,
    run_id: str | None,
    module_run_id: str | None,
    source_m11_6_module_run_id: str | None,
    profiles: Sequence[entities.Core3SkuBusinessProfile],
    allocations: Sequence[entities.Core3SkuBusinessProfileSalesAllocation],
    standard_by_key: Mapping[tuple[str, str], StandardDimension],
    rule_version: str,
) -> list[M117BusinessSalesReconciliationCheckRecord]:
    checks: list[M117BusinessSalesReconciliationCheckRecord] = []
    allocations_by_sku_type: dict[tuple[str, str], list[entities.Core3SkuBusinessProfileSalesAllocation]] = defaultdict(list)
    for allocation in allocations:
        if (allocation.dimension_type, allocation.dimension_code) in standard_by_key:
            allocations_by_sku_type[(allocation.sku_code, allocation.dimension_type)].append(allocation)
    for profile in profiles:
        missing_fields = _missing_market_fields(profile)
        if missing_fields:
            checks.append(
                _failed_check(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    source_m11_6_module_run_id=source_m11_6_module_run_id,
                    check_type="sku_market_required_fields",
                    sku_code=profile.sku_code,
                    failure_reason_code="missing_market_required_field",
                    failure_reason_cn="SKU 缺少销量、销额或价格字段，不能进入确定性销量对账。",
                    payload={"missing_fields": missing_fields},
                    rule_version=rule_version,
                )
            )
        expected_volume = _decimal(profile.sales_volume_total) or ZERO
        expected_amount = _decimal(profile.sales_amount_total) or ZERO
        for dimension_type in DIMENSION_TYPES:
            sku_allocations = allocations_by_sku_type.get((profile.sku_code, dimension_type), [])
            if not sku_allocations:
                checks.append(
                    _failed_check(
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        source_m11_6_module_run_id=source_m11_6_module_run_id,
                        check_type="sku_dimension_allocation_presence",
                        sku_code=profile.sku_code,
                        dimension_type=dimension_type,
                        failure_reason_code="missing_sku_dimension_allocation",
                        failure_reason_cn="SKU 在该维度类型下缺少 M11.6 销量分配。",
                        payload={"dimension_type": dimension_type},
                        rule_version=rule_version,
                    )
                )
                continue
            weight_sum = sum((_decimal(item.allocation_weight) or ZERO) for item in sku_allocations)
            volume_sum = sum((_decimal(item.allocated_sales_volume) or ZERO) for item in sku_allocations)
            amount_sum = sum((_decimal(item.allocated_sales_amount) or ZERO) for item in sku_allocations)
            checks.append(
                _check(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    source_m11_6_module_run_id=source_m11_6_module_run_id,
                    check_type="sku_dimension_weight_sum",
                    sku_code=profile.sku_code,
                    dimension_type=dimension_type,
                    expected=Decimal("1.000000"),
                    actual=weight_sum,
                    tolerance=WEIGHT_TOLERANCE,
                    issue_scope="sku",
                    failure_reason_code="sku_dimension_weight_not_closed",
                    failure_reason_cn="SKU 在该维度类型下的权重合计不等于 100%。",
                    suggestion_cn="检查 M11.6 维度权重归一化逻辑和上游是否缺少该维度候选。",
                    payload={"sku_code": profile.sku_code, "dimension_type": dimension_type},
                    rule_version=rule_version,
                )
            )
            checks.append(
                _check(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    source_m11_6_module_run_id=source_m11_6_module_run_id,
                    check_type="sku_dimension_volume_sum",
                    sku_code=profile.sku_code,
                    dimension_type=dimension_type,
                    expected=expected_volume,
                    actual=volume_sum,
                    tolerance=_volume_tolerance(expected_volume),
                    issue_scope="sku",
                    failure_reason_code="sku_dimension_volume_not_conserved",
                    failure_reason_cn="SKU 在该维度类型下的估算销量合计与 SKU 总销量不一致。",
                    suggestion_cn="检查 M11.6 销量分配是否完整覆盖该 SKU。",
                    payload={"sku_code": profile.sku_code, "dimension_type": dimension_type},
                    rule_version=rule_version,
                )
            )
            checks.append(
                _check(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    source_m11_6_module_run_id=source_m11_6_module_run_id,
                    check_type="sku_dimension_amount_sum",
                    sku_code=profile.sku_code,
                    dimension_type=dimension_type,
                    expected=expected_amount,
                    actual=amount_sum,
                    tolerance=_amount_tolerance(expected_amount),
                    issue_scope="sku",
                    failure_reason_code="sku_dimension_amount_not_conserved",
                    failure_reason_cn="SKU 在该维度类型下的估算销额合计与 SKU 总销额不一致。",
                    suggestion_cn="检查 M11.6 销额分配是否完整覆盖该 SKU。",
                    payload={"sku_code": profile.sku_code, "dimension_type": dimension_type},
                    rule_version=rule_version,
                )
            )
    return checks


def _issues_from_checks(
    checks: Sequence[M117BusinessSalesReconciliationCheckRecord],
    *,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[M117BusinessSalesReconciliationIssueRecord]:
    issues: list[M117BusinessSalesReconciliationIssueRecord] = []
    for check in checks:
        if check.status != "failed":
            continue
        severity = "blocker" if check.failure_reason_code in {
            "missing_market_required_field",
            "missing_sku_dimension_allocation",
            "dimension_code_not_in_seed",
            "allocation_without_profile",
            "global_dimension_volume_not_conserved",
            "global_dimension_amount_not_conserved",
            "sku_dimension_weight_not_closed",
            "sku_dimension_volume_not_conserved",
            "sku_dimension_amount_not_conserved",
            "sku_scope_not_aligned",
        } else "warning"
        fingerprint = stable_hash(
            {
                "check_id": check.reconciliation_check_id,
                "issue_code": check.failure_reason_code,
                "sku_code": check.sku_code,
                "dimension_type": check.dimension_type,
                "dimension_code": check.dimension_code,
                "gap": str(check.gap_value),
            },
            version="m117_issue_input_v1",
        )
        issues.append(
            M117BusinessSalesReconciliationIssueRecord(
                reconciliation_issue_id=_record_id("m117_issue", check.failure_reason_code, check.sku_code, check.dimension_type, check.dimension_code, fingerprint),
                reconciliation_check_id=check.reconciliation_check_id,
                project_id=check.project_id,
                category_code=check.category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                issue_scope=check.check_payload_json.get("issue_scope") or ("sku" if check.sku_code else "dimension_type" if check.dimension_type else "global"),
                sku_code=check.sku_code,
                dimension_type=check.dimension_type,
                dimension_code=check.dimension_code,
                issue_code=check.failure_reason_code or "reconciliation_check_failed",
                severity=severity,
                issue_message_cn=check.failure_reason_cn or "销量对账检查未通过。",
                suggested_action_cn=check.check_payload_json.get("suggestion_cn") or "先修复上游数据或 M11.6 分配结果，再重跑 M11.7。",
                issue_context_json={"check_payload": check.check_payload_json, "gap_value": str(check.gap_value), "gap_ratio": str(check.gap_ratio)},
                input_fingerprint=fingerprint,
                result_hash=stable_hash({"fingerprint": fingerprint, "severity": severity}, version="m117_issue_result_v1"),
                rule_version=rule_version,
            )
        )
    return issues


def _check(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    source_m11_6_module_run_id: str | None,
    check_type: str,
    expected: int | Decimal,
    actual: int | Decimal,
    tolerance: Decimal,
    issue_scope: str,
    failure_reason_code: str,
    failure_reason_cn: str,
    suggestion_cn: str,
    payload: dict[str, Any],
    rule_version: str,
    sku_code: str = "",
    dimension_type: str = "",
    dimension_code: str = "",
) -> M117BusinessSalesReconciliationCheckRecord:
    expected_value = _q6(Decimal(str(expected)))
    actual_value = _q6(Decimal(str(actual)))
    gap_value = _q6(actual_value - expected_value)
    status = "passed" if abs(gap_value) <= tolerance else "failed"
    fingerprint = stable_hash(
        {
            "batch_id": batch_id,
            "check_type": check_type,
            "sku_code": sku_code,
            "dimension_type": dimension_type,
            "dimension_code": dimension_code,
            "expected": str(expected_value),
            "actual": str(actual_value),
            "tolerance": str(tolerance),
            "rule_version": rule_version,
        },
        version="m117_check_input_v1",
    )
    return M117BusinessSalesReconciliationCheckRecord(
        reconciliation_check_id=_record_id("m117_check", check_type, sku_code, dimension_type, dimension_code, fingerprint),
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        source_m11_6_module_run_id=source_m11_6_module_run_id,
        check_type=check_type,
        sku_code=sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        expected_value=expected_value,
        actual_value=actual_value,
        gap_value=gap_value,
        gap_ratio=_ratio(abs(gap_value), abs(expected_value)),
        tolerance_value=_q6(tolerance),
        status=status,
        failure_reason_code="" if status == "passed" else failure_reason_code,
        failure_reason_cn="" if status == "passed" else failure_reason_cn,
        check_payload_json={**payload, "issue_scope": issue_scope, "suggestion_cn": suggestion_cn},
        input_fingerprint=fingerprint,
        result_hash=stable_hash({"fingerprint": fingerprint, "status": status, "gap": str(gap_value)}, version="m117_check_result_v1"),
        processing_status="success" if status == "passed" else "warning",
        review_required=status != "passed",
        review_status="auto_pass" if status == "passed" else "review_required",
        review_reason_json={} if status == "passed" else {"failure_reason_code": failure_reason_code},
        rule_version=rule_version,
    )


def _failed_check(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    source_m11_6_module_run_id: str | None,
    check_type: str,
    failure_reason_code: str,
    failure_reason_cn: str,
    payload: dict[str, Any],
    rule_version: str,
    sku_code: str = "",
    dimension_type: str = "",
    dimension_code: str = "",
) -> M117BusinessSalesReconciliationCheckRecord:
    return _check(
        batch_id=batch_id,
        project_id=project_id,
        category_code=category_code,
        run_id=run_id,
        module_run_id=module_run_id,
        source_m11_6_module_run_id=source_m11_6_module_run_id,
        check_type=check_type,
        sku_code=sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        expected=Decimal("1"),
        actual=Decimal("0"),
        tolerance=Decimal("0"),
        issue_scope="sku" if sku_code else "global",
        failure_reason_code=failure_reason_code,
        failure_reason_cn=failure_reason_cn,
        suggestion_cn="修复上游数据或 M11.6 产物后重跑 M11.7。",
        payload=payload,
        rule_version=rule_version,
    )


def _is_primary(
    profile: entities.Core3SkuBusinessProfile,
    dimension_type: str,
    dimension_code: str,
    dimension: entities.Core3SkuBusinessProfileDimension | None,
) -> bool:
    if dimension is not None and int(dimension.dimension_rank or 0) == 1:
        return True
    if dimension_type == "task":
        return profile.primary_task_code == dimension_code
    if dimension_type == "target_group":
        return profile.primary_target_group_code == dimension_code
    if dimension_type == "battlefield":
        return profile.primary_battlefield_code == dimension_code
    if dimension_type == "claim":
        claims = list(profile.core_claims_json or [])
        return bool(claims and str(claims[0].get("claim_code") or "") == dimension_code)
    return False


def _remap_contribution_summary_ids(
    contributions: Sequence[M117BusinessDimensionSkuContributionRecord],
    saved_summaries: Sequence[entities.Core3BusinessDimensionSalesSummary],
) -> tuple[M117BusinessDimensionSkuContributionRecord, ...]:
    summary_id_by_key = {
        (summary.batch_id, summary.dimension_type, summary.dimension_code, summary.rule_version): summary.dimension_sales_summary_id
        for summary in saved_summaries
    }
    return tuple(
        contribution.model_copy(
            update={
                "dimension_sales_summary_id": summary_id_by_key.get(
                    (
                        contribution.batch_id,
                        contribution.dimension_type,
                        contribution.dimension_code,
                        contribution.rule_version,
                    ),
                    contribution.dimension_sales_summary_id,
                )
            }
        )
        for contribution in contributions
    )


def _missing_market_fields(profile: entities.Core3SkuBusinessProfile) -> list[str]:
    missing: list[str] = []
    if _decimal(profile.sales_volume_total) is None:
        missing.append("sales_volume_total")
    if _decimal(profile.sales_amount_total) is None:
        missing.append("sales_amount_total")
    if _decimal(profile.price_wavg) is None and _decimal(profile.price_latest) is None:
        missing.append("price_wavg_or_price_latest")
    return missing


def _evidence_quality_summary(drafts: Sequence[ContributionDraft]) -> dict[str, Any]:
    level_counts = Counter((draft.dimension.evidence_level if draft.dimension is not None else "unknown") for draft in drafts)
    confidence_values = [_decimal(draft.allocation.allocation_confidence) or ZERO for draft in drafts]
    return {
        "evidence_level_counts": dict(level_counts),
        "avg_allocation_confidence": str(_average(confidence_values)),
        "sku_count": len({draft.profile.sku_code for draft in drafts}),
    }


def _battlefield_v2_summary(drafts: Sequence[ContributionDraft]) -> dict[str, Any]:
    support_rows = [_dimension_support_breakdown(draft) for draft in drafts]
    role_counts = Counter(str(row.get("portfolio_role") or ("primary_battlefield" if draft.is_primary else "allocated_battlefield")) for row, draft in zip(support_rows, drafts))
    pool_counts = Counter(str(row.get("market_pool_key") or "unknown") for row in support_rows)
    size_counts = Counter(str(row.get("screen_size_class") or "unknown") for row in support_rows)
    anchor_scores = [_decimal(row.get("product_anchor_score")) or ZERO for row in support_rows if row.get("product_anchor_score") is not None]
    primary_skus = [draft.profile.sku_code for draft in drafts if draft.is_primary]
    secondary_skus = [
        draft.profile.sku_code
        for draft, row in zip(drafts, support_rows)
        if not draft.is_primary and "secondary" in str(row.get("portfolio_role") or "")
    ]
    return {
        "allocation_policy": "m11_v2_portfolio",
        "portfolio_role_counts": dict(role_counts),
        "market_pool_counts": dict(pool_counts),
        "screen_size_class_counts": dict(size_counts),
        "avg_product_anchor_score": str(_average(anchor_scores)),
        "primary_sku_codes": primary_skus,
        "secondary_sku_codes": secondary_skus,
    }


def _top_sku_contribution(drafts: Sequence[ContributionDraft], limit: int = 5) -> list[dict[str, Any]]:
    sorted_drafts = sorted(
        drafts,
        key=lambda draft: (_decimal(draft.allocation.allocated_sales_volume) or ZERO, _decimal(draft.allocation.allocated_sales_amount) or ZERO),
        reverse=True,
    )
    result: list[dict[str, Any]] = []
    for draft in sorted_drafts[:limit]:
        support_breakdown = _dimension_support_breakdown(draft)
        result.append(
            {
                "sku_code": draft.profile.sku_code,
                "brand_name": draft.profile.brand_name,
                "model_name": draft.profile.model_name,
                "allocated_sales_volume": str(_q4(_decimal(draft.allocation.allocated_sales_volume) or ZERO)),
                "allocated_sales_amount": str(_q4(_decimal(draft.allocation.allocated_sales_amount) or ZERO)),
                "allocation_weight": str(_q6(_decimal(draft.allocation.allocation_weight) or ZERO)),
                "is_primary_dimension": draft.is_primary,
                "portfolio_role": support_breakdown.get("portfolio_role"),
                "market_pool_key": support_breakdown.get("market_pool_key"),
                "screen_size_class": support_breakdown.get("screen_size_class"),
                "product_anchor_score": str(_q4(_decimal(support_breakdown.get("product_anchor_score")) or ZERO)),
            }
        )
    return result


def _summary_cn(
    *,
    standard: StandardDimension,
    drafts: Sequence[ContributionDraft],
    estimated_volume: Decimal,
    total_volume: Decimal,
) -> str:
    sku_count = len({draft.profile.sku_code for draft in drafts})
    share_pct = (_ratio(estimated_volume, total_volume) * Decimal("100")).quantize(Decimal("0.01"))
    if standard.dimension_type != "battlefield":
        return f"{standard.name} 当前由 {sku_count} 个 SKU 贡献，估算销量 {estimated_volume}，占全量 {share_pct}%。"
    primary_count = sum(1 for draft in drafts if draft.is_primary)
    pool_count = len(
        {
            str(_dimension_support_breakdown(draft).get("market_pool_key") or "")
            for draft in drafts
            if _dimension_support_breakdown(draft).get("market_pool_key")
        }
    )
    return (
        f"{standard.name} 当前由 {sku_count} 个 SKU 贡献，其中 {primary_count} 个为主战场 SKU，"
        f"覆盖 {pool_count} 个市场池，估算销量 {estimated_volume}，占全量 {share_pct}%。"
    )


def _dimension_support_breakdown(draft: ContributionDraft) -> dict[str, Any]:
    if draft.dimension is None:
        return {}
    value = draft.dimension.support_breakdown_json or {}
    return dict(value) if isinstance(value, Mapping) else {}


def _dimension_type_totals(summaries: Sequence[M117BusinessDimensionSalesSummaryRecord]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for dimension_type in DIMENSION_TYPES:
        rows = [summary for summary in summaries if summary.dimension_type == dimension_type]
        result[dimension_type] = {
            "estimated_sales_volume": str(_q4(sum(summary.estimated_sales_volume for summary in rows))),
            "estimated_sales_amount": str(_q4(sum(summary.estimated_sales_amount for summary in rows))),
            "dimension_count": str(len(rows)),
        }
    return result


def _average(values: Iterable[Any]) -> Decimal:
    decimals = [_decimal(value) or ZERO for value in values]
    if not decimals:
        return Decimal("0.0000")
    return _q4(sum(decimals) / Decimal(len(decimals)))


def _volume_tolerance(total: Decimal) -> Decimal:
    return max(Decimal("1.0000"), abs(total) * RATIO_TOLERANCE)


def _amount_tolerance(total: Decimal) -> Decimal:
    return abs(total) * RATIO_TOLERANCE


def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0.000000")
    return _q6(numerator / denominator)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _q4(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _q6(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _record_id(prefix: str, *parts: object) -> str:
    return f"{prefix}_{stable_hash([str(part) for part in parts], version='m117_record_id_v1')[:32]}"
