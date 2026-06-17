"""M14 three-slot core competitor selection service.

M14 consumes M12 candidate pairs and M13 scores. It does not read raw source
tables, does not recall new candidates, and does not build the final report.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    CORE3_M14_RULE_VERSION,
    Core3RunStatus,
    M13IssueLevel,
    M13RoleCode,
    M14AuditDecision,
    M14EmptyReasonCode,
    M14IssueLevel,
    M14IssueScope,
    M14PressureLevel,
    M14ReviewIssueType,
    M14SelectionSlot,
    M14SelectionStatus,
    M14SlotDecisionStatus,
)
from app.services.core3_real_data.core3_selection_repositories import (
    Core3SelectionRepository,
    M14CandidateInput,
    M14InputBlockedError,
    M14TargetInput,
)
from app.services.core3_real_data.core3_selection_schemas import (
    M14BuildArtifacts,
    M14CompetitorSelectionRecord,
    M14CompetitorSelectionRunRecord,
    M14SelectionAuditRecord,
    M14SelectionReviewIssueRecord,
    M14ServiceResult,
    M14SlotDecisionRecord,
)
from app.services.core3_real_data.hash_utils import stable_hash


BOUNDARY_NOTE_CN = (
    "M14 只在 M12 召回且 M13 已评分的候选中做三槽位核心竞品选择；"
    "不是 M13 总分 TopN，不强行凑满三个槽，且允许同品牌 SKU 入选。"
)

ROLE_SCORE_CANDIDATE_THRESHOLD = Decimal("0.6000")
AUTO_SELECT_CONFIDENCE_THRESHOLD = Decimal("0.5000")
AUTO_SELECT_EVIDENCE_THRESHOLD = Decimal("0.5000")
SLOT_SELECTION_AUTO_THRESHOLD = Decimal("0.6000")
MAX_SELECTED_PER_TARGET = 3


@dataclass(frozen=True)
class _SlotConfig:
    slot: M14SelectionSlot
    name_cn: str
    role_code: M13RoleCode


SLOT_CONFIGS: tuple[_SlotConfig, ...] = (
    _SlotConfig(M14SelectionSlot.DIRECT_FIGHT, "正面对打竞品", M13RoleCode.DIRECT_FIGHT),
    _SlotConfig(M14SelectionSlot.PRICE_VOLUME_PRESSURE, "价格/销量挤压竞品", M13RoleCode.PRICE_VOLUME_PRESSURE),
    _SlotConfig(M14SelectionSlot.BENCHMARK_POTENTIAL, "高端标杆/潜在下探竞品", M13RoleCode.BENCHMARK_POTENTIAL),
)


@dataclass(frozen=True)
class _SlotCandidate:
    item: M14CandidateInput
    config: _SlotConfig
    role_score: Decimal
    slot_selection_score: Decimal
    market_validity_score: Decimal
    business_distinctiveness_score: Decimal
    strategic_value_score: Decimal
    risk_penalty: Decimal
    candidate_gate_passed: bool
    auto_select_eligible: bool
    failed_conditions: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class _TargetDecision:
    artifacts: M14BuildArtifacts
    slot_candidates: dict[M14SelectionSlot, tuple[_SlotCandidate, ...]]


class Core3SelectionService:
    def __init__(self, repository: Core3SelectionRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M14_RULE_VERSION,
        max_targets: int | None = None,
        resume_unselected_only: bool = True,
    ) -> M14ServiceResult:
        total_target_count = self.repository.count_current_score_targets(batch_id, sku_scope=sku_scope)
        selected_target_count_before = self.repository.count_current_selection_run_targets(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_target_count_before = max(total_target_count - selected_target_count_before, 0)
        target_inputs = self.repository.list_target_inputs(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
            max_targets=max_targets,
            only_unselected=resume_unselected_only,
        )
        if not target_inputs:
            if total_target_count == 0:
                raise M14InputBlockedError("M14 没有可选择的 M13 当前评分候选。")
            selected_target_count_after = self.repository.count_current_selection_run_targets(
                batch_id,
                sku_scope=sku_scope,
                rule_version=rule_version,
            )
            return M14ServiceResult(
                status=Core3RunStatus.SUCCESS,
                input_count=0,
                output_count=0,
                created_output_count=0,
                warnings=[],
                selection_runs=[],
                selections=[],
                slot_decisions=[],
                audits=[],
                review_issues=[],
                summary={
                    "module_code": "M14",
                    "batch_id": batch_id,
                    "target_sku_count": 0,
                    "candidate_count": 0,
                    "selection_run_count": 0,
                    "selection_count": 0,
                    "slot_decision_count": 0,
                    "audit_count": 0,
                    "review_issue_count": 0,
                    "empty_slot_count": 0,
                    "review_slot_count": 0,
                    "selected_target_count": 0,
                    "total_target_count": total_target_count,
                    "selected_target_count_before": selected_target_count_before,
                    "pending_target_count_before": pending_target_count_before,
                    "processed_target_count": 0,
                    "selected_target_count_after": selected_target_count_after,
                    "pending_target_count_after": max(total_target_count - selected_target_count_after, 0),
                    "max_targets": max_targets,
                    "resume_unselected_only": resume_unselected_only,
                    "batch_limited": False,
                    "batch_completed": True,
                    "boundary_note": BOUNDARY_NOTE_CN,
                    "source_modules": ["M12", "M13"],
                    "selection_policy": _selection_policy(),
                },
            )

        decisions = [
            self._build_target_decision(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                target=target,
            )
            for target in target_inputs
        ]
        selection_runs = [decision.artifacts.selection_run for decision in decisions]
        selections = [record for decision in decisions for record in decision.artifacts.selections]
        slot_decisions = [record for decision in decisions for record in decision.artifacts.slot_decisions]
        audits = [record for decision in decisions for record in decision.artifacts.audits]
        review_issues = [record for decision in decisions for record in decision.artifacts.review_issues]

        run_result = self.repository.save_selection_runs(selection_runs)
        selection_result = self.repository.save_selections(selections)
        slot_result = self.repository.save_slot_decisions(slot_decisions)
        audit_result = self.repository.save_audits(audits)
        issue_result = self.repository.save_review_issues(review_issues)
        selected_target_count_after = self.repository.count_current_selection_run_targets(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_target_count_after = max(total_target_count - selected_target_count_after, 0)

        created_output_count = (
            run_result.created_count
            + selection_result.created_count
            + slot_result.created_count
            + audit_result.created_count
            + issue_result.created_count
        )
        output_count = len(selection_runs) + len(selections) + len(slot_decisions) + len(audits) + len(review_issues)
        empty_slot_count = sum(1 for row in slot_decisions if row.decision_status == M14SlotDecisionStatus.EMPTY)
        review_slot_count = sum(1 for row in slot_decisions if row.decision_status == M14SlotDecisionStatus.REVIEW_REQUIRED)
        blocker_count = sum(1 for issue in review_issues if issue.issue_level == M14IssueLevel.BLOCKER)

        warnings: list[str] = []
        if empty_slot_count:
            warnings.append(f"M14 有 {empty_slot_count} 个槽位为空，已输出空槽原因，未强行补弱竞品。")
        if review_slot_count:
            warnings.append(f"M14 有 {review_slot_count} 个槽位候选需要复核后才能自动入选。")
        if blocker_count:
            warnings.append(f"M14 有 {blocker_count} 个阻断类复核问题。")
        if pending_target_count_after > 0:
            warnings.append(
                f"M14 本次处理 {len(target_inputs)} 个目标 SKU，仍有 {pending_target_count_after} 个目标 SKU 待选择；请继续执行 M14 直到待选择为 0。"
            )

        status = Core3RunStatus.SUCCESS
        if blocker_count:
            status = Core3RunStatus.WARNING
        elif review_issues or empty_slot_count:
            status = Core3RunStatus.WARNING
        if pending_target_count_after > 0:
            status = Core3RunStatus.WARNING

        summary = {
            "module_code": "M14",
            "batch_id": batch_id,
            "target_sku_count": len(target_inputs),
            "candidate_count": sum(len(target.candidates) for target in target_inputs),
            "selection_run_count": len(selection_runs),
            "selection_count": len(selections),
            "slot_decision_count": len(slot_decisions),
            "audit_count": len(audits),
            "review_issue_count": len(review_issues),
            "empty_slot_count": empty_slot_count,
            "review_slot_count": review_slot_count,
            "selected_target_count": len({row.target_sku_code for row in selections}),
            "total_target_count": total_target_count,
            "selected_target_count_before": selected_target_count_before,
            "pending_target_count_before": pending_target_count_before,
            "processed_target_count": len(target_inputs),
            "selected_target_count_after": selected_target_count_after,
            "pending_target_count_after": pending_target_count_after,
            "max_targets": max_targets,
            "resume_unselected_only": resume_unselected_only,
            "batch_limited": pending_target_count_after > 0,
            "batch_completed": pending_target_count_after == 0,
            "boundary_note": BOUNDARY_NOTE_CN,
            "source_modules": ["M12", "M13"],
            "selection_policy": _selection_policy(),
            "created_counts": {
                "selection_runs": run_result.created_count,
                "selections": selection_result.created_count,
                "slot_decisions": slot_result.created_count,
                "audits": audit_result.created_count,
                "review_issues": issue_result.created_count,
            },
            "reused_counts": {
                "selection_runs": run_result.reused_count,
                "selections": selection_result.reused_count,
                "slot_decisions": slot_result.reused_count,
                "audits": audit_result.reused_count,
                "review_issues": issue_result.reused_count,
            },
            "downstream_usage": {
                "M15": "读取三槽位入选、空槽说明和候选审计生成高层证据卡。",
                "M16": "读取 M14 复核问题、空槽和高风险候选进入人工复核队列。",
            },
        }
        return M14ServiceResult(
            status=status,
            input_count=sum(len(target.candidates) for target in target_inputs),
            output_count=output_count,
            created_output_count=created_output_count,
            warnings=warnings,
            selection_runs=selection_runs,
            selections=selections,
            slot_decisions=slot_decisions,
            audits=audits,
            review_issues=review_issues,
            summary=summary,
        )

    def _build_target_decision(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        target: M14TargetInput,
    ) -> _TargetDecision:
        selection_run_id = _record_id("m14run", batch_id, target.target_sku_code, rule_version)
        candidates_by_slot = {
            config.slot: tuple(
                sorted(
                    (self._score_candidate_for_slot(item, config) for item in target.candidates),
                    key=lambda candidate: (
                        candidate.candidate_gate_passed,
                        candidate.auto_select_eligible,
                        candidate.slot_selection_score,
                        candidate.role_score,
                        candidate.item.component_score.component_total_score,
                    ),
                    reverse=True,
                )
            )
            for config in SLOT_CONFIGS
        }

        selected_candidate_codes: set[str] = set()
        selections: list[M14CompetitorSelectionRecord] = []
        slot_decisions: list[M14SlotDecisionRecord] = []
        selected_by_candidate: dict[str, M14CompetitorSelectionRecord] = {}
        review_issues: list[M14SelectionReviewIssueRecord] = []

        for rank, config in enumerate(SLOT_CONFIGS, start=1):
            slot_candidates = list(candidates_by_slot[config.slot])
            top = slot_candidates[0] if slot_candidates else None
            selected = next(
                (
                    candidate
                    for candidate in slot_candidates
                    if candidate.auto_select_eligible and candidate.item.pool.candidate_sku_code not in selected_candidate_codes
                ),
                None,
            )
            selection_record: M14CompetitorSelectionRecord | None = None
            if selected is not None and len(selected_candidate_codes) < MAX_SELECTED_PER_TARGET:
                selection_record = self._selection_record(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    target=target,
                    slot_candidate=selected,
                    selection_rank=rank,
                )
                selections.append(selection_record)
                selected_by_candidate[selected.item.pool.candidate_sku_code] = selection_record
                selected_candidate_codes.add(selected.item.pool.candidate_sku_code)

            slot_decision = self._slot_decision_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                selection_run_id=selection_run_id,
                target=target,
                config=config,
                top=top,
                selected=selected if selection_record else None,
                selection_record=selection_record,
                slot_candidates=slot_candidates,
                selected_candidate_codes=selected_candidate_codes,
            )
            slot_decisions.append(slot_decision)
            review_issues.extend(
                self._slot_review_issues(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    slot_decision_id=slot_decision.slot_decision_id,
                    target=target,
                    config=config,
                    top=top,
                    decision=slot_decision,
                )
            )

        audits = [
            self._audit_record(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                selection_run_id=selection_run_id,
                target=target,
                item=item,
                slot_candidates=_candidates_for_item(candidates_by_slot, item),
                selected=selected_by_candidate.get(item.pool.candidate_sku_code),
                selected_candidate_codes=selected_candidate_codes,
            )
            for item in target.candidates
        ]
        review_issues.extend(
            self._candidate_review_issues(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                selection_run_id=selection_run_id,
                target=target,
                audits=audits,
            )
        )
        if not target.candidates:
            review_issues.append(
                _review_issue_record(
                    batch_id=batch_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code.value,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    target_sku_code=target.target_sku_code,
                    issue_scope=M14IssueScope.RUN,
                    issue_type=M14ReviewIssueType.EMPTY_CANDIDATE_POOL.value,
                    issue_level=M14IssueLevel.BLOCKER,
                    message_cn="该目标没有 M12/M13 可用候选，M14 不能绕过候选池补选。",
                    suggested_action_cn="先补齐上游候选召回和评分结果，再重新运行 M14。",
                )
            )
        if not selections:
            review_issues.append(
                _review_issue_record(
                    batch_id=batch_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code.value,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    target_sku_code=target.target_sku_code,
                    issue_scope=M14IssueScope.RUN,
                    issue_type=M14ReviewIssueType.ALL_SLOTS_EMPTY.value,
                    issue_level=M14IssueLevel.REVIEW,
                    message_cn="三槽位均未达到自动入选条件，不能为了页面完整而强行凑满。",
                    suggested_action_cn="业务复核候选池证据，或继续补充真实数据后重跑。",
                )
            )

        empty_slots = [
            {
                "slot_code": decision.slot_code.value if isinstance(decision.slot_code, M14SelectionSlot) else decision.slot_code,
                "slot_name_cn": decision.slot_name_cn,
                "empty_reason_code": decision.empty_reason_code,
                "empty_reason_cn": decision.empty_reason_cn,
            }
            for decision in slot_decisions
            if decision.decision_status == M14SlotDecisionStatus.EMPTY
        ]
        review_candidate_count = sum(1 for audit in audits if audit.audit_decision == M14AuditDecision.REVIEW)
        blocked_candidate_count = sum(1 for audit in audits if audit.audit_decision == M14AuditDecision.BLOCKED)
        run_status = _selection_status(len(selections), len(empty_slots), review_candidate_count, blocked_candidate_count)
        run_input = {
            "target_sku_code": target.target_sku_code,
            "candidate_ids": [item.pool.candidate_pool_id for item in target.candidates],
            "score_hashes": [item.component_score.result_hash for item in target.candidates],
            "rule_version": rule_version,
        }
        run_result = {
            "selected": [
                {
                    "slot_code": row.slot_code,
                    "candidate_sku_code": row.candidate_sku_code,
                    "slot_selection_score": row.slot_selection_score,
                }
                for row in selections
            ],
            "empty_slots": empty_slots,
            "audits": [
                {"candidate_sku_code": row.candidate_sku_code, "decision": row.audit_decision, "best_slot": row.best_slot_code}
                for row in audits
            ],
        }
        selection_run = M14CompetitorSelectionRunRecord(
            selection_run_id=selection_run_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=target.target_sku_code,
            target_model_name=target.target_model_name,
            target_brand_name=target.target_brand_name,
            candidate_count=len(target.candidates),
            scored_candidate_count=len(target.candidates),
            selected_count=len(selections),
            empty_slot_count=len(empty_slots),
            review_candidate_count=review_candidate_count,
            blocked_candidate_count=blocked_candidate_count,
            selection_status=run_status,
            selection_summary_cn=_run_summary_cn(target, selections, empty_slots, review_candidate_count),
            empty_slots_json=empty_slots,
            selection_policy_json=_selection_policy(),
            target_profile_hash=target.target_profile_hash,
            m12_recall_fingerprint=stable_hash(
                [item.pool.result_hash for item in target.candidates],
                version="m14_m12_recall_fingerprint_v1",
            ),
            m13_score_fingerprint=stable_hash(
                [item.component_score.result_hash for item in target.candidates],
                version="m14_m13_score_fingerprint_v1",
            ),
            rule_version=rule_version,
            input_fingerprint=stable_hash(run_input, version="m14_selection_run_input_v1"),
            result_hash=stable_hash({**run_input, **run_result}, version="m14_selection_run_result_v1"),
            processing_status="warning" if run_status != M14SelectionStatus.SUCCESS else "success",
            review_required=bool(review_candidate_count or blocked_candidate_count or not selections),
            review_status="review_required" if (review_candidate_count or blocked_candidate_count or not selections) else "auto_pass",
            review_reason_json={
                "empty_slots": empty_slots,
                "review_candidate_count": review_candidate_count,
                "blocked_candidate_count": blocked_candidate_count,
            }
            if (empty_slots or review_candidate_count or blocked_candidate_count)
            else {},
        )
        return _TargetDecision(
            artifacts=M14BuildArtifacts(
                selection_run=selection_run,
                selections=tuple(selections),
                slot_decisions=tuple(slot_decisions),
                audits=tuple(audits),
                review_issues=tuple(review_issues),
            ),
            slot_candidates=candidates_by_slot,
        )

    def _score_candidate_for_slot(self, item: M14CandidateInput, config: _SlotConfig) -> _SlotCandidate:
        score = item.component_score
        role = item.role_scores.get(config.role_code.value)
        role_score = _decimal(role.role_score if role else getattr(score, f"{config.slot.value}_score", Decimal("0")))
        evidence_score = _decimal(score.evidence_completeness_score)
        confidence = _decimal(score.confidence)
        market_validity = _market_validity_score(item, config.slot)
        distinctiveness = Decimal("0.8000")
        strategic_value = _strategic_value_score(item, config.slot)
        risk_penalty = _risk_penalty(item)
        slot_score = _clamp_decimal(
            role_score * Decimal("0.45")
            + evidence_score * Decimal("0.15")
            + market_validity * Decimal("0.15")
            + distinctiveness * Decimal("0.15")
            + strategic_value * Decimal("0.10")
            - risk_penalty
        )
        failed_conditions = _slot_failed_conditions(item, config.slot, role_score, confidence, evidence_score, market_validity)
        candidate_gate_passed = not failed_conditions and role_score >= ROLE_SCORE_CANDIDATE_THRESHOLD
        auto_select_eligible = (
            candidate_gate_passed
            and slot_score >= SLOT_SELECTION_AUTO_THRESHOLD
            and confidence >= AUTO_SELECT_CONFIDENCE_THRESHOLD
            and evidence_score >= AUTO_SELECT_EVIDENCE_THRESHOLD
            and not _has_blocker(item)
        )
        return _SlotCandidate(
            item=item,
            config=config,
            role_score=role_score,
            slot_selection_score=slot_score,
            market_validity_score=market_validity,
            business_distinctiveness_score=distinctiveness,
            strategic_value_score=strategic_value,
            risk_penalty=risk_penalty,
            candidate_gate_passed=candidate_gate_passed,
            auto_select_eligible=auto_select_eligible,
            failed_conditions=tuple(failed_conditions),
        )

    def _selection_record(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        selection_run_id: str,
        target: M14TargetInput,
        slot_candidate: _SlotCandidate,
        selection_rank: int,
    ) -> M14CompetitorSelectionRecord:
        item = slot_candidate.item
        pool = item.pool
        score = item.component_score
        role = item.role_scores.get(slot_candidate.config.role_code.value)
        battlefield = _primary_battlefield(item)
        input_payload = _selection_input_payload(selection_run_id, item, slot_candidate.config.slot, rule_version)
        result_payload = _slot_candidate_payload(slot_candidate)
        return M14CompetitorSelectionRecord(
            competitor_selection_id=_record_id("m14sel", batch_id, target.target_sku_code, pool.candidate_sku_code, slot_candidate.config.slot.value, rule_version),
            selection_run_id=selection_run_id,
            candidate_pool_id=pool.candidate_pool_id,
            candidate_component_score_id=score.candidate_component_score_id,
            candidate_role_score_id=role.candidate_role_score_id if role else None,
            project_id=pool.project_id,
            category_code=pool.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=target.target_sku_code,
            target_model_name=target.target_model_name,
            target_brand_name=target.target_brand_name,
            candidate_sku_code=pool.candidate_sku_code,
            candidate_model_name=pool.candidate_model_name,
            candidate_brand_name=pool.candidate_brand_name,
            same_brand_flag=bool(pool.same_brand_flag),
            slot_code=slot_candidate.config.slot,
            slot_name_cn=slot_candidate.config.name_cn,
            selection_rank=selection_rank,
            primary_battlefield_code=battlefield.get("battlefield_code"),
            primary_battlefield_name=battlefield.get("battlefield_name_cn"),
            slot_selection_score=slot_candidate.slot_selection_score,
            role_score=slot_candidate.role_score,
            component_total_score=_decimal(score.component_total_score),
            confidence=_decimal(score.confidence),
            evidence_completeness_score=_decimal(score.evidence_completeness_score),
            pressure_level=_pressure_level(slot_candidate),
            selection_reason_cn=_selection_reason_cn(target, slot_candidate, battlefield),
            selection_reason_short_cn=_selection_reason_short_cn(slot_candidate),
            business_conclusion_cn=_business_conclusion_cn(target, slot_candidate),
            strategy_hint_cn=_strategy_hint_cn(slot_candidate),
            risk_summary_cn=_risk_summary_cn(slot_candidate),
            component_scores_json=dict(score.component_scores_json or {}),
            role_scores_json=_role_scores_payload(item),
            selection_evidence_json=_selection_evidence_payload(slot_candidate, battlefield),
            selected_by_rules_json=[
                "槽位角色分达到阈值",
                "选择分达到自动入选线",
                "置信度和证据完整度达到自动入选线",
            ],
            review_required=bool(score.review_required),
            review_reason=score.review_reason,
            positive_evidence_ids=list(score.positive_evidence_ids or ()),
            weakening_evidence_ids=list(score.weakening_evidence_ids or ()),
            evidence_ids=_candidate_evidence_ids(item),
            target_profile_hash=target.target_profile_hash,
            candidate_profile_hash=pool.candidate_profile_hash,
            m13_score_hash=score.result_hash,
            rule_version=rule_version,
            input_fingerprint=stable_hash(input_payload, version="m14_selection_input_v1"),
            result_hash=stable_hash({**input_payload, **result_payload}, version="m14_selection_result_v1"),
            processing_status="warning" if score.review_required else "success",
            review_status="review_required" if score.review_required else "auto_pass",
            review_reason_json={"m13_review_reason": score.review_reason} if score.review_required else {},
        )

    def _slot_decision_record(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        selection_run_id: str,
        target: M14TargetInput,
        config: _SlotConfig,
        top: _SlotCandidate | None,
        selected: _SlotCandidate | None,
        selection_record: M14CompetitorSelectionRecord | None,
        slot_candidates: Sequence[_SlotCandidate],
        selected_candidate_codes: set[str],
    ) -> M14SlotDecisionRecord:
        top_item = top.item if top else None
        reason_code, reason_cn = _empty_reason(top, selected, selected_candidate_codes)
        decision_status = M14SlotDecisionStatus.SELECTED if selected else (
            M14SlotDecisionStatus.REVIEW_REQUIRED if top and top.candidate_gate_passed else M14SlotDecisionStatus.EMPTY
        )
        review_reason = None
        if decision_status == M14SlotDecisionStatus.REVIEW_REQUIRED:
            review_reason = "top_candidate_not_auto_selectable"
        input_payload = {
            "selection_run_id": selection_run_id,
            "target_sku_code": target.target_sku_code,
            "slot_code": config.slot.value,
            "top_candidate": top_item.pool.candidate_sku_code if top_item else None,
            "rule_version": rule_version,
        }
        result_payload = {
            "decision_status": decision_status.value,
            "selected_candidate": selected.item.pool.candidate_sku_code if selected else None,
            "empty_reason_code": reason_code,
        }
        return M14SlotDecisionRecord(
            slot_decision_id=_record_id("m14slot", batch_id, target.target_sku_code, config.slot.value, rule_version),
            selection_run_id=selection_run_id,
            selected_competitor_selection_id=selection_record.competitor_selection_id if selection_record else None,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=target.target_sku_code,
            target_model_name=target.target_model_name,
            candidate_sku_code=selected.item.pool.candidate_sku_code if selected else None,
            candidate_model_name=selected.item.pool.candidate_model_name if selected else None,
            slot_code=config.slot,
            slot_name_cn=config.name_cn,
            decision_status=decision_status,
            selected_candidate_count=1 if selected else 0,
            slot_candidate_count=sum(1 for candidate in slot_candidates if candidate.candidate_gate_passed),
            empty_reason_code=reason_code,
            empty_reason_cn=reason_cn,
            review_reason=review_reason,
            top_candidate_sku_code=top_item.pool.candidate_sku_code if top_item else None,
            top_candidate_model_name=top_item.pool.candidate_model_name if top_item else None,
            top_candidate_score=top.slot_selection_score if top else Decimal("0.0000"),
            decision_confidence=_decimal(selected.item.component_score.confidence if selected else (top.item.component_score.confidence if top else Decimal("0"))),
            decision_summary_cn=_slot_decision_summary_cn(config, selected, top, reason_cn),
            decision_payload_json={
                "boundary_note": BOUNDARY_NOTE_CN,
                "top_candidate": _slot_candidate_payload(top) if top else None,
                "candidate_count": len(slot_candidates),
                "eligible_candidate_count": sum(1 for candidate in slot_candidates if candidate.auto_select_eligible),
                "empty_reason_code": reason_code,
            },
            evidence_ids=_candidate_evidence_ids(selected.item if selected else top_item),
            rule_version=rule_version,
            input_fingerprint=stable_hash(input_payload, version="m14_slot_decision_input_v1"),
            result_hash=stable_hash({**input_payload, **result_payload}, version="m14_slot_decision_result_v1"),
            processing_status="warning" if decision_status != M14SlotDecisionStatus.SELECTED else "success",
            review_required=decision_status == M14SlotDecisionStatus.REVIEW_REQUIRED,
            review_status="review_required" if decision_status == M14SlotDecisionStatus.REVIEW_REQUIRED else "auto_pass",
            review_reason_json={"review_reason": review_reason} if review_reason else {},
        )

    def _audit_record(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        selection_run_id: str,
        target: M14TargetInput,
        item: M14CandidateInput,
        slot_candidates: Mapping[M14SelectionSlot, _SlotCandidate],
        selected: M14CompetitorSelectionRecord | None,
        selected_candidate_codes: set[str],
    ) -> M14SelectionAuditRecord:
        score = item.component_score
        slot_scores = {slot.value: _slot_candidate_payload(candidate) for slot, candidate in slot_candidates.items()}
        best = max(slot_candidates.values(), key=lambda candidate: candidate.slot_selection_score, default=None)
        failed_conditions = _audit_failed_conditions(item, best, selected_candidate_codes, selected)
        decision = M14AuditDecision.SELECTED if selected else _audit_decision(item, best)
        input_payload = {
            "selection_run_id": selection_run_id,
            "candidate_pool_id": item.pool.candidate_pool_id,
            "component_score_id": score.candidate_component_score_id,
            "rule_version": rule_version,
        }
        result_payload = {
            "audit_decision": decision.value,
            "selected_slot_code": selected.slot_code if selected else None,
            "best_slot_code": best.config.slot.value if best else None,
            "slot_scores": slot_scores,
        }
        return M14SelectionAuditRecord(
            selection_audit_id=_record_id("m14audit", batch_id, target.target_sku_code, item.pool.candidate_sku_code, rule_version),
            selection_run_id=selection_run_id,
            candidate_pool_id=item.pool.candidate_pool_id,
            candidate_component_score_id=score.candidate_component_score_id,
            project_id=item.pool.project_id,
            category_code=item.pool.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=target.target_sku_code,
            target_model_name=target.target_model_name,
            candidate_sku_code=item.pool.candidate_sku_code,
            candidate_model_name=item.pool.candidate_model_name,
            candidate_brand_name=item.pool.candidate_brand_name,
            evaluated_slot_codes_json=[slot.value for slot in slot_candidates],
            audit_decision=decision,
            selected_slot_code=selected.slot_code if selected else None,
            best_slot_code=best.config.slot.value if best else None,
            decision_reason_cn=_audit_reason_cn(item, best, selected, failed_conditions),
            failed_conditions_json=failed_conditions,
            slot_scores_json=slot_scores,
            candidate_total_score=_decimal(score.component_total_score),
            best_role_score=best.role_score if best else Decimal("0.0000"),
            evidence_completeness_score=_decimal(score.evidence_completeness_score),
            confidence=_decimal(score.confidence),
            risk_flags_json=list(score.risk_flags_json or ()),
            duplicate_with_candidate_sku_code=item.pool.candidate_sku_code if item.pool.candidate_sku_code in selected_candidate_codes and not selected else None,
            business_distinctiveness_score=best.business_distinctiveness_score if best else Decimal("0.8000"),
            strategic_value_score=best.strategic_value_score if best else Decimal("0.0000"),
            evidence_ids=_candidate_evidence_ids(item),
            rule_version=rule_version,
            input_fingerprint=stable_hash(input_payload, version="m14_audit_input_v1"),
            result_hash=stable_hash({**input_payload, **result_payload}, version="m14_audit_result_v1"),
            processing_status="warning" if decision in {M14AuditDecision.REVIEW, M14AuditDecision.BLOCKED} else "success",
            review_required=decision in {M14AuditDecision.REVIEW, M14AuditDecision.BLOCKED},
            review_status="review_required" if decision in {M14AuditDecision.REVIEW, M14AuditDecision.BLOCKED} else "auto_pass",
            review_reason_json={"failed_conditions": failed_conditions} if failed_conditions else {},
        )

    def _slot_review_issues(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        selection_run_id: str,
        slot_decision_id: str,
        target: M14TargetInput,
        config: _SlotConfig,
        top: _SlotCandidate | None,
        decision: M14SlotDecisionRecord,
    ) -> list[M14SelectionReviewIssueRecord]:
        issues: list[M14SelectionReviewIssueRecord] = []
        if decision.decision_status == M14SlotDecisionStatus.EMPTY:
            issues.append(
                _review_issue_record(
                    batch_id=batch_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code.value,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    slot_decision_id=slot_decision_id,
                    target_sku_code=target.target_sku_code,
                    slot_code=config.slot.value,
                    issue_scope=M14IssueScope.SLOT,
                    issue_type=(decision.empty_reason_code or M14EmptyReasonCode.NO_CANDIDATE.value),
                    issue_level=M14IssueLevel.WARNING,
                    message_cn=decision.empty_reason_cn or f"{config.name_cn}没有达到自动入选条件。",
                    suggested_action_cn="保留空槽说明，不要用低置信候选补齐页面。",
                    evidence_ids=decision.evidence_ids,
                )
            )
        if decision.decision_status == M14SlotDecisionStatus.REVIEW_REQUIRED and top is not None:
            issues.append(
                _review_issue_record(
                    batch_id=batch_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code.value,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    selection_run_id=selection_run_id,
                    slot_decision_id=slot_decision_id,
                    target_sku_code=target.target_sku_code,
                    slot_code=config.slot.value,
                    candidate_sku_code=top.item.pool.candidate_sku_code,
                    issue_scope=M14IssueScope.SLOT,
                    issue_type=M14ReviewIssueType.LOW_CONFIDENCE_TOP_CANDIDATE.value,
                    issue_level=M14IssueLevel.REVIEW,
                    message_cn=f"{config.name_cn}存在候选，但置信度、证据完整度或选择分未达到自动入选线。",
                    suggested_action_cn="进入 M16 人工复核，或补齐证据后重跑 M12-M14。",
                    evidence_ids=_candidate_evidence_ids(top.item),
                    source_payload_json=_slot_candidate_payload(top),
                )
            )
        return issues

    def _candidate_review_issues(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        selection_run_id: str,
        target: M14TargetInput,
        audits: Sequence[M14SelectionAuditRecord],
    ) -> list[M14SelectionReviewIssueRecord]:
        issues: list[M14SelectionReviewIssueRecord] = []
        for audit in audits:
            if audit.audit_decision == M14AuditDecision.BLOCKED:
                issues.append(
                    _review_issue_record(
                        batch_id=batch_id,
                        project_id=self.repository.project_id,
                        category_code=self.repository.category_code.value,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        selection_run_id=selection_run_id,
                        selection_audit_id=audit.selection_audit_id,
                        target_sku_code=target.target_sku_code,
                        candidate_sku_code=audit.candidate_sku_code,
                        issue_scope=M14IssueScope.CANDIDATE,
                        issue_type=M14EmptyReasonCode.BLOCKED_BY_REVIEW_ISSUE.value,
                        issue_level=M14IssueLevel.REVIEW,
                        message_cn="该候选存在上游阻断或证据严重不足，M14 未自动入选。",
                        suggested_action_cn="先处理 M13 评分复核问题，再决定是否人工保留。",
                        evidence_ids=audit.evidence_ids,
                    )
                )
            if audit.candidate_total_score >= Decimal("0.6500") and audit.evidence_completeness_score < AUTO_SELECT_EVIDENCE_THRESHOLD:
                issues.append(
                    _review_issue_record(
                        batch_id=batch_id,
                        project_id=self.repository.project_id,
                        category_code=self.repository.category_code.value,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        selection_run_id=selection_run_id,
                        selection_audit_id=audit.selection_audit_id,
                        target_sku_code=target.target_sku_code,
                        candidate_sku_code=audit.candidate_sku_code,
                        issue_scope=M14IssueScope.CANDIDATE,
                        issue_type=M14ReviewIssueType.HIGH_SCORE_LOW_EVIDENCE.value,
                        issue_level=M14IssueLevel.REVIEW,
                        message_cn="候选总分较高但证据完整度不足，不能直接作为核心竞品展示。",
                        suggested_action_cn="补齐市场、卖点或评论证据后重跑，或进入人工复核。",
                        evidence_ids=audit.evidence_ids,
                    )
                )
        return issues


def _selection_policy() -> dict[str, Any]:
    return {
        "slot_order": [config.slot.value for config in SLOT_CONFIGS],
        "role_score_candidate_threshold": _float(ROLE_SCORE_CANDIDATE_THRESHOLD),
        "auto_select_confidence_threshold": _float(AUTO_SELECT_CONFIDENCE_THRESHOLD),
        "auto_select_evidence_threshold": _float(AUTO_SELECT_EVIDENCE_THRESHOLD),
        "slot_selection_auto_threshold": _float(SLOT_SELECTION_AUTO_THRESHOLD),
        "max_selected_per_target": MAX_SELECTED_PER_TARGET,
        "same_brand_allowed": True,
        "not_top_n": True,
        "force_fill_empty_slot": False,
    }


def _slot_failed_conditions(
    item: M14CandidateInput,
    slot: M14SelectionSlot,
    role_score: Decimal,
    confidence: Decimal,
    evidence_score: Decimal,
    market_validity: Decimal,
) -> list[dict[str, Any]]:
    score = item.component_score
    failures: list[dict[str, Any]] = []
    if role_score < ROLE_SCORE_CANDIDATE_THRESHOLD:
        failures.append({"code": "role_score_below_threshold", "reason_cn": "槽位角色分未达到候选线。"})
    if confidence < AUTO_SELECT_CONFIDENCE_THRESHOLD:
        failures.append({"code": M14EmptyReasonCode.LOW_CONFIDENCE.value, "reason_cn": "整体置信度不足。"})
    if evidence_score < AUTO_SELECT_EVIDENCE_THRESHOLD:
        failures.append({"code": "evidence_below_threshold", "reason_cn": "证据完整度不足。"})
    if _has_blocker(item):
        failures.append({"code": M14EmptyReasonCode.BLOCKED_BY_REVIEW_ISSUE.value, "reason_cn": "上游评分存在阻断问题。"})
    if _service_only(item):
        failures.append({"code": M14EmptyReasonCode.SERVICE_ONLY.value, "reason_cn": "候选主要体现服务参照价值，不进入产品核心三槽位。"})
    if slot == M14SelectionSlot.DIRECT_FIGHT:
        comparable_dimensions = sum(
            1
            for value in (
                score.battlefield_fit_score,
                score.price_position_score,
                score.size_fit_score,
                score.channel_overlap_score,
                max(_decimal(score.task_overlap_score), _decimal(score.audience_overlap_score)),
                max(_decimal(score.claim_confrontation_score), _decimal(score.param_similarity_score)),
            )
            if _decimal(value) >= Decimal("0.5000")
        )
        if comparable_dimensions < 2:
            failures.append({"code": M14ReviewIssueType.MISSING_DIRECT_BATTLEFIELD.value, "reason_cn": "正面对打至少需要两个以上可比维度，不能只凭同尺寸判断。"})
    elif slot == M14SelectionSlot.PRICE_VOLUME_PRESSURE and market_validity < Decimal("0.5500"):
        failures.append({"code": M14ReviewIssueType.MISSING_PRESSURE_SIGNAL.value, "reason_cn": "缺少价格、销量或市场压力信号。"})
    elif slot == M14SelectionSlot.BENCHMARK_POTENTIAL and market_validity < Decimal("0.5500"):
        failures.append({"code": M14ReviewIssueType.MISSING_BENCHMARK_SIGNAL.value, "reason_cn": "缺少参数、卖点或高端标杆压力信号。"})
    return failures


def _market_validity_score(item: M14CandidateInput, slot: M14SelectionSlot) -> Decimal:
    score = item.component_score
    if slot == M14SelectionSlot.DIRECT_FIGHT:
        return _avg_decimal([score.price_position_score, score.size_fit_score, score.channel_overlap_score])
    if slot == M14SelectionSlot.PRICE_VOLUME_PRESSURE:
        return max(
            _decimal(score.price_advantage_score),
            _decimal(score.market_threat_score),
            _decimal(score.sales_amount_strength_score),
            _decimal(score.price_trend_score),
        )
    return max(
        _decimal(score.param_superiority_score),
        _decimal(score.claim_superiority_score),
        _decimal(score.sales_amount_strength_score),
        _decimal(score.price_trend_score),
    )


def _strategic_value_score(item: M14CandidateInput, slot: M14SelectionSlot) -> Decimal:
    score = item.component_score
    if slot == M14SelectionSlot.DIRECT_FIGHT:
        return _avg_decimal([score.battlefield_fit_score, score.claim_confrontation_score, score.task_overlap_score])
    if slot == M14SelectionSlot.PRICE_VOLUME_PRESSURE:
        return _avg_decimal([score.price_advantage_score, score.market_threat_score, score.sales_amount_strength_score])
    return _avg_decimal([score.param_superiority_score, score.claim_superiority_score, score.benchmark_potential_score])


def _risk_penalty(item: M14CandidateInput) -> Decimal:
    score = item.component_score
    penalty = Decimal("0.0000")
    if bool(score.review_required):
        penalty += Decimal("0.0800")
    if _decimal(score.evidence_completeness_score) < AUTO_SELECT_EVIDENCE_THRESHOLD:
        penalty += Decimal("0.1000")
    core_max = max(_decimal(score.direct_fight_score), _decimal(score.price_volume_pressure_score), _decimal(score.benchmark_potential_score))
    if _decimal(score.service_reference_score) > core_max:
        penalty += Decimal("0.1000")
    if str(score.sample_status) in {"insufficient", "unknown"}:
        penalty += Decimal("0.0600")
    return _clamp_decimal(penalty)


def _slot_candidate_payload(candidate: _SlotCandidate | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    item = candidate.item
    return {
        "candidate_sku_code": item.pool.candidate_sku_code,
        "candidate_model_name": item.pool.candidate_model_name,
        "slot_code": candidate.config.slot.value,
        "role_score": _float(candidate.role_score),
        "slot_selection_score": _float(candidate.slot_selection_score),
        "component_total_score": _float(item.component_score.component_total_score),
        "confidence": _float(item.component_score.confidence),
        "evidence_completeness_score": _float(item.component_score.evidence_completeness_score),
        "market_validity_score": _float(candidate.market_validity_score),
        "strategic_value_score": _float(candidate.strategic_value_score),
        "risk_penalty": _float(candidate.risk_penalty),
        "candidate_gate_passed": candidate.candidate_gate_passed,
        "auto_select_eligible": candidate.auto_select_eligible,
        "failed_conditions": list(candidate.failed_conditions),
    }


def _candidates_for_item(
    candidates_by_slot: Mapping[M14SelectionSlot, Sequence[_SlotCandidate]],
    item: M14CandidateInput,
) -> dict[M14SelectionSlot, _SlotCandidate]:
    return {
        slot: candidate
        for slot, candidates in candidates_by_slot.items()
        for candidate in candidates
        if candidate.item.pool.candidate_pool_id == item.pool.candidate_pool_id
    }


def _primary_battlefield(item: M14CandidateInput) -> dict[str, Any]:
    source = _snapshot_source(item.snapshot)
    overlap = _dict(source.get("battlefield_overlap"))
    items = list(overlap.get("matched_items") or ())
    if items:
        return dict(items[0])
    codes = list(overlap.get("matched_codes") or ())
    if codes:
        return {"battlefield_code": codes[0], "battlefield_name_cn": codes[0]}
    return {}


def _selection_reason_cn(target: M14TargetInput, candidate: _SlotCandidate, battlefield: Mapping[str, Any]) -> str:
    item = candidate.item
    bf = battlefield.get("battlefield_name_cn") or battlefield.get("battlefield_code") or "共同价值战场"
    return (
        f"{item.pool.candidate_model_name or item.pool.candidate_sku_code} 被选为{candidate.config.name_cn}，"
        f"不是因为总分排名靠前，而是该槽位角色分 {candidate.role_score:.2f}、选择分 {candidate.slot_selection_score:.2f}。"
        f"主要支撑来自{bf}、价位/渠道可比和 M13 证据完整度 {item.component_score.evidence_completeness_score:.2f}。"
        f"{'该候选与目标同属' + str(target.target_brand_name) + '，同品牌内部竞争允许入选。' if item.pool.same_brand_flag else ''}"
    )


def _selection_reason_short_cn(candidate: _SlotCandidate) -> str:
    item = candidate.item
    return f"{candidate.config.name_cn}：角色分 {candidate.role_score:.2f}，选择分 {candidate.slot_selection_score:.2f}。"


def _business_conclusion_cn(target: M14TargetInput, candidate: _SlotCandidate) -> str:
    model = candidate.item.pool.candidate_model_name or candidate.item.pool.candidate_sku_code
    target_model = target.target_model_name or target.target_sku_code
    if candidate.config.slot == M14SelectionSlot.DIRECT_FIGHT:
        return f"{model} 是 {target_model} 当前最值得正面对打解释的核心竞品，需要优先说明双方同战场、同价位或同渠道比较关系。"
    if candidate.config.slot == M14SelectionSlot.PRICE_VOLUME_PRESSURE:
        return f"{model} 对 {target_model} 的主要威胁来自价格、销量或渠道挤压，应在策略上关注价格拦截和成交权重。"
    return f"{model} 对 {target_model} 体现高端标杆或潜在下探压力，应重点关注参数、卖点和高价值战场的领先表达。"


def _strategy_hint_cn(candidate: _SlotCandidate) -> str:
    if candidate.config.slot == M14SelectionSlot.DIRECT_FIGHT:
        return "建议围绕共同价值战场拆解对打卖点，避免只用尺寸或品牌做解释。"
    if candidate.config.slot == M14SelectionSlot.PRICE_VOLUME_PRESSURE:
        return "建议关注价格带、销量权重和渠道重合，判断是否需要价格或权益防守。"
    return "建议关注候选领先参数与高端卖点，判断是否会形成下探压力或用户心智牵引。"


def _risk_summary_cn(candidate: _SlotCandidate) -> str | None:
    if not candidate.failed_conditions and not candidate.item.component_score.review_required:
        return None
    reasons = [str(condition.get("reason_cn")) for condition in candidate.failed_conditions[:3]]
    if candidate.item.component_score.review_required and candidate.item.component_score.review_reason:
        reasons.append(f"M13 标记为 {candidate.item.component_score.review_reason}")
    return "；".join(reasons) or None


def _selection_evidence_payload(candidate: _SlotCandidate, battlefield: Mapping[str, Any]) -> dict[str, Any]:
    item = candidate.item
    return {
        "primary_battlefield": dict(battlefield),
        "component_strengths": list(item.component_score.main_strengths_json or ())[:5],
        "component_gaps": list(item.component_score.main_gaps_json or ())[:5],
        "role_scores": _role_scores_payload(item),
        "m12_recall_reason_cn": item.pool.business_reason_cn,
        "evidence_count": len(_candidate_evidence_ids(item)),
    }


def _role_scores_payload(item: M14CandidateInput) -> dict[str, Any]:
    return {
        role_code: {
            "role_score": _float(role.role_score),
            "role_confidence": _float(role.role_confidence),
            "role_name_cn": role.role_name_cn,
            "auto_select_eligible": bool(role.auto_select_eligible),
            "role_business_reason_short_cn": role.role_business_reason_short_cn,
        }
        for role_code, role in sorted(item.role_scores.items())
    }


def _slot_decision_summary_cn(
    config: _SlotConfig,
    selected: _SlotCandidate | None,
    top: _SlotCandidate | None,
    empty_reason_cn: str | None,
) -> str:
    if selected is not None:
        model = selected.item.pool.candidate_model_name or selected.item.pool.candidate_sku_code
        return f"{config.name_cn}已选择 {model}，选择分 {selected.slot_selection_score:.2f}。"
    if top is not None:
        model = top.item.pool.candidate_model_name or top.item.pool.candidate_sku_code
        return f"{config.name_cn}最高候选为 {model}，但未达到自动入选条件：{empty_reason_cn or '需要复核'}。"
    return f"{config.name_cn}当前没有满足候选线的 SKU，保留空槽。"


def _empty_reason(
    top: _SlotCandidate | None,
    selected: _SlotCandidate | None,
    selected_candidate_codes: set[str],
) -> tuple[str | None, str | None]:
    if selected is not None:
        return None, None
    if top is None:
        return M14EmptyReasonCode.NO_CANDIDATE.value, "该槽位没有候选达到角色分候选线。"
    if top.item.pool.candidate_sku_code in selected_candidate_codes:
        return M14EmptyReasonCode.DUPLICATE_WITH_SELECTED.value, "该槽位最高候选已占用其他槽位，不重复占位。"
    if _service_only(top.item):
        return M14EmptyReasonCode.SERVICE_ONLY.value, "最高候选主要体现服务参照价值，不占用产品核心槽位。"
    if _decimal(top.item.component_score.evidence_completeness_score) < AUTO_SELECT_EVIDENCE_THRESHOLD:
        return M14EmptyReasonCode.INSUFFICIENT_SEMANTIC_EVIDENCE.value, "最高候选证据完整度不足，不能自动入选。"
    if _decimal(top.item.component_score.confidence) < AUTO_SELECT_CONFIDENCE_THRESHOLD:
        return M14EmptyReasonCode.LOW_CONFIDENCE.value, "最高候选置信度不足，需人工复核。"
    if str(top.item.component_score.sample_status) in {"limited", "insufficient", "unknown"}:
        return M14EmptyReasonCode.SAMPLE_LIMITED.value, "样本有限，暂不自动入选。"
    return M14EmptyReasonCode.LOW_CONFIDENCE.value, "最高候选选择分未达到自动入选线。"


def _audit_failed_conditions(
    item: M14CandidateInput,
    best: _SlotCandidate | None,
    selected_candidate_codes: set[str],
    selected: M14CompetitorSelectionRecord | None,
) -> list[dict[str, Any]]:
    failures = list(best.failed_conditions if best else ())
    if best is None:
        failures.append({"code": M14EmptyReasonCode.NO_CANDIDATE.value, "reason_cn": "该候选没有任何槽位达到候选线。"})
    elif not best.auto_select_eligible and not failures:
        failures.append({"code": "slot_selection_score_below_threshold", "reason_cn": "最佳槽位选择分未达到自动入选线。"})
    if item.pool.candidate_sku_code in selected_candidate_codes and selected is None:
        failures.append({"code": M14EmptyReasonCode.DUPLICATE_WITH_SELECTED.value, "reason_cn": "该候选已被其他槽位占用，不能重复入选。"})
    return failures


def _audit_decision(item: M14CandidateInput, best: _SlotCandidate | None) -> M14AuditDecision:
    if _has_blocker(item):
        return M14AuditDecision.BLOCKED
    if best is not None and (best.candidate_gate_passed or best.slot_selection_score >= Decimal("0.5500")):
        return M14AuditDecision.REVIEW
    return M14AuditDecision.REJECTED


def _audit_reason_cn(
    item: M14CandidateInput,
    best: _SlotCandidate | None,
    selected: M14CompetitorSelectionRecord | None,
    failed_conditions: Sequence[Mapping[str, Any]],
) -> str:
    model = item.pool.candidate_model_name or item.pool.candidate_sku_code
    if selected is not None:
        return f"{model} 入选 {selected.slot_name_cn}，因为该槽位选择分和证据完整度达到自动入选线。"
    if best is None:
        return f"{model} 未进入任何槽位候选，当前只保留为候选池审计记录。"
    reason = "；".join(str(condition.get("reason_cn")) for condition in failed_conditions[:3])
    return f"{model} 最接近 {best.config.name_cn}，但未自动入选：{reason or '未达到自动选择阈值'}。"


def _selection_status(
    selected_count: int,
    empty_slot_count: int,
    review_candidate_count: int,
    blocked_candidate_count: int,
) -> M14SelectionStatus:
    if blocked_candidate_count and selected_count == 0:
        return M14SelectionStatus.BLOCKED
    if selected_count == 0:
        return M14SelectionStatus.REVIEW_REQUIRED
    if review_candidate_count:
        return M14SelectionStatus.REVIEW_REQUIRED
    if empty_slot_count:
        return M14SelectionStatus.LIMITED
    return M14SelectionStatus.SUCCESS


def _run_summary_cn(
    target: M14TargetInput,
    selections: Sequence[M14CompetitorSelectionRecord],
    empty_slots: Sequence[Mapping[str, Any]],
    review_candidate_count: int,
) -> str:
    target_model = target.target_model_name or target.target_sku_code
    if selections:
        selected_text = "、".join(f"{row.slot_name_cn}：{row.candidate_model_name or row.candidate_sku_code}" for row in selections)
        suffix = f"；{len(empty_slots)} 个槽位为空" if empty_slots else ""
        review = f"；{review_candidate_count} 个候选需复核" if review_candidate_count else ""
        return f"{target_model} 当前选出 {len(selections)} 个核心竞品，{selected_text}{suffix}{review}。"
    return f"{target_model} 当前没有达到自动入选线的核心竞品，三槽位均需补证或人工复核。"


def _pressure_level(candidate: _SlotCandidate) -> M14PressureLevel:
    score = candidate.slot_selection_score
    if score >= Decimal("0.7600"):
        return M14PressureLevel.HIGH
    if score >= Decimal("0.6600"):
        return M14PressureLevel.MEDIUM_HIGH
    if score >= Decimal("0.5500"):
        return M14PressureLevel.MEDIUM
    return M14PressureLevel.REVIEW_REQUIRED


def _selection_input_payload(
    selection_run_id: str,
    item: M14CandidateInput,
    slot: M14SelectionSlot,
    rule_version: str,
) -> dict[str, Any]:
    return {
        "selection_run_id": selection_run_id,
        "candidate_pool_id": item.pool.candidate_pool_id,
        "candidate_component_score_id": item.component_score.candidate_component_score_id,
        "slot_code": slot.value,
        "component_score_hash": item.component_score.result_hash,
        "rule_version": rule_version,
    }


def _candidate_evidence_ids(item: M14CandidateInput | None) -> list[str]:
    if item is None:
        return []
    return _unique_evidence_ids(
        [
            item.pool.evidence_ids or (),
            item.snapshot.evidence_ids if item.snapshot else (),
            item.component_score.evidence_ids or (),
            item.component_score.positive_evidence_ids or (),
            *(explanation.supporting_evidence_ids or () for explanation in item.explanations),
        ]
    )


def _snapshot_source(snapshot: Any | None) -> dict[str, Any]:
    if snapshot is None:
        return {}
    source = _dict(getattr(snapshot, "m13_component_input_json", None))
    fallbacks = {
        "battlefield_overlap": getattr(snapshot, "battlefield_overlap_json", None),
        "market_feature": getattr(snapshot, "market_feature_json", None),
        "param_feature": getattr(snapshot, "param_feature_json", None),
        "claim_value_overlap": getattr(snapshot, "claim_value_overlap_json", None),
    }
    for key, value in fallbacks.items():
        source.setdefault(key, value or {})
    return source


def _has_blocker(item: M14CandidateInput) -> bool:
    return any(str(issue.issue_level) == M13IssueLevel.BLOCKER.value for issue in item.score_issues)


def _service_only(item: M14CandidateInput) -> bool:
    score = item.component_score
    core_max = max(_decimal(score.direct_fight_score), _decimal(score.price_volume_pressure_score), _decimal(score.benchmark_potential_score))
    relation_types = {str(value) for value in item.pool.relation_types_json or ()}
    return (
        "service_reference" in relation_types
        and _decimal(score.service_reference_score) > core_max
        and core_max < Decimal("0.6200")
    )


def _record_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash(parts, version=prefix).split(':')[-1][:48]}"


def _review_issue_record(
    *,
    batch_id: str,
    project_id: str,
    category_code: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    selection_run_id: str | None,
    target_sku_code: str,
    issue_scope: M14IssueScope,
    issue_type: str,
    issue_level: M14IssueLevel,
    message_cn: str,
    suggested_action_cn: str,
    slot_code: str = "",
    candidate_sku_code: str = "",
    competitor_selection_id: str | None = None,
    slot_decision_id: str | None = None,
    selection_audit_id: str | None = None,
    source_payload_json: Mapping[str, Any] | None = None,
    evidence_ids: Sequence[str] = (),
) -> M14SelectionReviewIssueRecord:
    input_payload = {
        "selection_run_id": selection_run_id,
        "target_sku_code": target_sku_code,
        "slot_code": slot_code,
        "candidate_sku_code": candidate_sku_code,
        "issue_scope": issue_scope.value,
        "issue_type": issue_type,
        "message_cn": message_cn,
        "source_payload": dict(source_payload_json or {}),
    }
    fingerprint = stable_hash(input_payload, version="m14_review_issue_input_v1")
    return M14SelectionReviewIssueRecord(
        selection_review_issue_id=_record_id("m14issue", batch_id, target_sku_code, candidate_sku_code, slot_code, issue_scope.value, issue_type, fingerprint),
        selection_run_id=selection_run_id,
        competitor_selection_id=competitor_selection_id,
        slot_decision_id=slot_decision_id,
        selection_audit_id=selection_audit_id,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        target_sku_code=target_sku_code,
        slot_code=slot_code,
        candidate_sku_code=candidate_sku_code,
        issue_scope=issue_scope,
        issue_type=issue_type,
        issue_level=issue_level,
        issue_message_cn=message_cn,
        suggested_action_cn=suggested_action_cn,
        source_payload_json=dict(source_payload_json or {}),
        evidence_ids=list(evidence_ids),
        rule_version=rule_version,
        input_fingerprint=fingerprint,
        result_hash=stable_hash({**input_payload, "suggested_action_cn": suggested_action_cn}, version="m14_review_issue_result_v1"),
        processing_status="warning" if issue_level != M14IssueLevel.BLOCKER else "blocked",
        review_required=True,
        review_status="review_required",
        review_reason_json={"issue_type": issue_type, "issue_scope": issue_scope.value},
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _avg_decimal(values: Iterable[Any]) -> Decimal:
    decimals = [_decimal(value) for value in values]
    if not decimals:
        return Decimal("0.0000")
    return _clamp_decimal(sum(decimals, Decimal("0")) / Decimal(len(decimals)))


def _clamp_decimal(value: Any) -> Decimal:
    decimal = _decimal(value)
    if decimal < 0:
        decimal = Decimal("0")
    if decimal > 1:
        decimal = Decimal("1")
    return _quantize(decimal)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _float(value: Any) -> float:
    return float(_decimal(value))


def _unique_evidence_ids(groups: Iterable[Iterable[Any] | Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for group in groups:
        if group is None:
            continue
        values = group if isinstance(group, (list, tuple, set)) else (group,)
        for value in values:
            if value is None or value == "":
                continue
            normalized = str(value)
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result
