"""M15 executive evidence report service.

M15 is a presentation and traceability module. It consumes M14 selections and
upstream derived profiles only; it does not recall candidates or change scores.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M15_FORBIDDEN_OUTPUT_FIELDS,
    CORE3_M15_REPORT_SECTION_ORDER,
    CORE3_M15_RULE_VERSION,
    Core3RunStatus,
    M15ReadinessLevel,
    M15ReportExportStatus,
    M15ReportExportType,
    M15ReportIssueLevel,
    M15ReportIssueScope,
    M15ReportReviewIssueType,
    M15ReportSectionCode,
    M15ReportSectionDisplayStatus,
)
from app.services.core3_real_data.evidence_report_repositories import (
    EvidenceReportRepository,
    M15InputBlockedError,
    M15TargetReportInput,
)
from app.services.core3_real_data.evidence_report_schemas import (
    M15BuildArtifacts,
    M15EvidenceCardRecord,
    M15ReportExportRecord,
    M15ReportReviewIssueRecord,
    M15ReportSectionRecord,
    M15ServiceResult,
    M15TargetReportPayloadRecord,
)
from app.services.core3_real_data.hash_utils import stable_hash


DATA_SCOPE_NOTE_CN = (
    "当前样例数据内，仅覆盖线上渠道 26W01-26W23 观察窗口；"
    "同品牌 SKU 允许作为竞品进入比较，结论不代表全市场、全渠道或全年周期。"
)
CLAIM_GAP_NOTE_CN = "宣传卖点数据缺口：当前样例数据未形成完整结构化卖点证据，不能据此判断卖点弱。"
SERVICE_GUARD_NOTE_CN = "服务、物流、安装类评论只作为履约风险参考，不作为产品核心竞争力判断依据。"

CONFIDENCE_LABELS_CN = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "review_required": "待复核",
}

SECTION_TITLE_CN: dict[M15ReportSectionCode, str] = {
    M15ReportSectionCode.EXECUTIVE: "结论先行",
    M15ReportSectionCode.TARGET_PROFILE: "目标商品画像",
    M15ReportSectionCode.COMPETITOR_CARDS: "核心竞品证据卡",
    M15ReportSectionCode.BATTLEFIELD_CONTEXT: "价值战场判断",
    M15ReportSectionCode.WHY_COMPETITOR: "为什么是竞品",
    M15ReportSectionCode.EVIDENCE_MATRIX: "证据矩阵",
    M15ReportSectionCode.STRATEGY: "业务动作建议",
    M15ReportSectionCode.CANDIDATE_AUDIT: "候选池审计",
    M15ReportSectionCode.SOP_TRACE: "推导链路",
    M15ReportSectionCode.DATA_QUALITY: "数据口径与缺口",
    M15ReportSectionCode.EXPORT: "导出内容",
}

UUID_PATTERN = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")


@dataclass(frozen=True)
class _EvidenceRef:
    short_ref: str
    evidence_id: str
    domain_cn: str
    title_cn: str
    source_cn: str
    snippet_cn: str


@dataclass(frozen=True)
class _TargetArtifacts:
    report_payload: M15TargetReportPayloadRecord
    evidence_cards: tuple[M15EvidenceCardRecord, ...]
    report_sections: tuple[M15ReportSectionRecord, ...]
    report_exports: tuple[M15ReportExportRecord, ...]
    review_issues: tuple[M15ReportReviewIssueRecord, ...]


class EvidenceReportService:
    def __init__(self, repository: EvidenceReportRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        sku_scope: Sequence[str] = (),
        rule_version: str = CORE3_M15_RULE_VERSION,
        max_targets: int | None = None,
        resume_unreported_only: bool = True,
    ) -> M15ServiceResult:
        total_target_count = self.repository.count_current_selection_targets(batch_id, sku_scope=sku_scope)
        reported_target_count_before = self.repository.count_current_report_payload_targets(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_target_count_before = max(total_target_count - reported_target_count_before, 0)
        target_inputs = self.repository.list_report_inputs(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
            max_targets=max_targets,
            only_unreported=resume_unreported_only,
        )
        if not target_inputs:
            if total_target_count == 0:
                raise M15InputBlockedError("M15 没有可生成报告的 M14 当前选择结果。")
            reported_target_count_after = self.repository.count_current_report_payload_targets(
                batch_id,
                sku_scope=sku_scope,
                rule_version=rule_version,
            )
            return M15ServiceResult(
                status=Core3RunStatus.SUCCESS,
                input_count=0,
                output_count=0,
                created_output_count=0,
                summary={
                    "module_code": "M15",
                    "batch_id": batch_id,
                    "target_sku_count": 0,
                    "target_report_count": 0,
                    "evidence_card_count": 0,
                    "section_count": 0,
                    "export_count": 0,
                    "review_issue_count": 0,
                    "data_scope_note_cn": DATA_SCOPE_NOTE_CN,
                    "total_target_count": total_target_count,
                    "reported_target_count_before": reported_target_count_before,
                    "pending_target_count_before": pending_target_count_before,
                    "processed_target_count": 0,
                    "reported_target_count_after": reported_target_count_after,
                    "pending_target_count_after": max(total_target_count - reported_target_count_after, 0),
                    "max_targets": max_targets,
                    "resume_unreported_only": resume_unreported_only,
                    "batch_limited": False,
                    "batch_completed": True,
                    "source_modules": ["M08", "M09", "M10", "M11", "M11.5", "M12", "M13", "M14"],
                    "downstream_usage": {
                        "M16": "读取报告复核问题、低置信证据卡和数据缺口，进入人工复核工作台。",
                        "API": "读取报告 payload、章节、证据卡和导出产物，提供中文业务展示接口。",
                        "FRONTEND": "直接展示高层汇报页首屏、竞品卡、推导链路和数据口径说明。",
                    },
                },
                warnings=[],
                review_issues=(),
                artifacts=M15BuildArtifacts(),
            )

        target_artifacts = tuple(
            self._build_target_artifacts(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                target=target,
            )
            for target in target_inputs
        )
        evidence_cards = tuple(card for item in target_artifacts for card in item.evidence_cards)
        report_payloads = tuple(item.report_payload for item in target_artifacts)
        report_sections = tuple(section for item in target_artifacts for section in item.report_sections)
        report_exports = tuple(export for item in target_artifacts for export in item.report_exports)
        review_issues = tuple(issue for item in target_artifacts for issue in item.review_issues)

        card_result = self.repository.save_evidence_cards(evidence_cards)
        payload_result = self.repository.save_report_payloads(report_payloads)
        section_result = self.repository.save_report_sections(report_sections)
        export_result = self.repository.save_report_exports(report_exports)
        issue_result = self.repository.save_review_issues(review_issues)
        reported_target_count_after = self.repository.count_current_report_payload_targets(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
        )
        pending_target_count_after = max(total_target_count - reported_target_count_after, 0)

        created_output_count = (
            card_result.created_count
            + payload_result.created_count
            + section_result.created_count
            + export_result.created_count
            + issue_result.created_count
        )
        output_count = (
            len(evidence_cards)
            + len(report_payloads)
            + len(report_sections)
            + len(report_exports)
            + len(review_issues)
        )
        blocker_count = sum(1 for issue in review_issues if issue.issue_level == M15ReportIssueLevel.BLOCKER)
        review_count = sum(1 for issue in review_issues if issue.issue_level == M15ReportIssueLevel.REVIEW)
        warning_count = sum(1 for issue in review_issues if issue.issue_level == M15ReportIssueLevel.WARNING)

        warnings: list[str] = []
        if review_issues:
            warnings.append(f"M15 生成 {len(review_issues)} 条报告复核问题，其中复核 {review_count} 条、提示 {warning_count} 条。")
        if any(payload.empty_slot_count for payload in report_payloads):
            warnings.append("M15 已保留 M14 空槽原因，没有强行补齐三竞品。")
        if any("宣传卖点数据缺口" in payload.data_quality_note_cn for payload in report_payloads):
            warnings.append("M15 已将结构化卖点不足表达为数据缺口，不等同于卖点弱。")
        if pending_target_count_after > 0:
            warnings.append(
                f"M15 本次生成 {len(target_inputs)} 个目标 SKU 报告，仍有 {pending_target_count_after} 个目标 SKU 待生成；请继续执行 M15 直到待生成为 0。"
            )

        status = Core3RunStatus.SUCCESS
        if blocker_count or review_count or warnings:
            status = Core3RunStatus.WARNING

        summary = {
            "module_code": "M15",
            "batch_id": batch_id,
            "target_sku_count": len(target_inputs),
            "target_report_count": len(report_payloads),
            "evidence_card_count": len(evidence_cards),
            "section_count": len(report_sections),
            "export_count": len(report_exports),
            "review_issue_count": len(review_issues),
            "data_scope_note_cn": DATA_SCOPE_NOTE_CN,
            "total_target_count": total_target_count,
            "reported_target_count_before": reported_target_count_before,
            "pending_target_count_before": pending_target_count_before,
            "processed_target_count": len(target_inputs),
            "reported_target_count_after": reported_target_count_after,
            "pending_target_count_after": pending_target_count_after,
            "max_targets": max_targets,
            "resume_unreported_only": resume_unreported_only,
            "batch_limited": pending_target_count_after > 0,
            "batch_completed": pending_target_count_after == 0,
            "source_modules": ["M08", "M09", "M10", "M11", "M11.5", "M12", "M13", "M14"],
            "downstream_usage": {
                "M16": "读取报告复核问题、低置信证据卡和数据缺口，进入人工复核工作台。",
                "API": "读取报告 payload、章节、证据卡和导出产物，提供中文业务展示接口。",
                "FRONTEND": "直接展示高层汇报页首屏、竞品卡、推导链路和数据口径说明。",
            },
            "created_counts": {
                "evidence_cards": card_result.created_count,
                "report_payloads": payload_result.created_count,
                "report_sections": section_result.created_count,
                "report_exports": export_result.created_count,
                "review_issues": issue_result.created_count,
            },
            "reused_counts": {
                "evidence_cards": card_result.reused_count,
                "report_payloads": payload_result.reused_count,
                "report_sections": section_result.reused_count,
                "report_exports": export_result.reused_count,
                "review_issues": issue_result.reused_count,
            },
            "updated_counts": {
                "evidence_cards": card_result.updated_count,
                "report_payloads": payload_result.updated_count,
                "report_sections": section_result.updated_count,
                "report_exports": export_result.updated_count,
                "review_issues": issue_result.updated_count,
            },
        }
        return M15ServiceResult(
            status=status,
            input_count=sum(len(target.selections) for target in target_inputs),
            output_count=output_count,
            created_output_count=created_output_count,
            summary=summary,
            warnings=warnings,
            review_issues=review_issues,
            artifacts=M15BuildArtifacts(
                evidence_cards=evidence_cards,
                report_payloads=report_payloads,
                report_sections=report_sections,
                report_exports=report_exports,
                review_issues=review_issues,
            ),
        )

    def _build_target_artifacts(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        target: M15TargetReportInput,
    ) -> _TargetArtifacts:
        evidence_map = _build_short_evidence_map(target.evidence_atoms)
        cards = tuple(
            self._build_card(
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                target=target,
                selection=selection,
                evidence_map=evidence_map,
            )
            for selection in target.selections
        )
        payload = self._build_report_payload(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            target=target,
            cards=cards,
            evidence_map=evidence_map,
        )
        sections = self._build_sections(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            payload=payload,
            cards=cards,
        )
        exports = self._build_exports(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            payload=payload,
            cards=cards,
            sections=sections,
        )
        review_issues = self._build_review_issues(
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            target=target,
            payload=payload,
            cards=cards,
            sections=sections,
            exports=exports,
        )
        return _TargetArtifacts(
            report_payload=payload,
            evidence_cards=cards,
            report_sections=sections,
            report_exports=exports,
            review_issues=review_issues,
        )

    def _build_card(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        target: M15TargetReportInput,
        selection: entities.Core3CompetitorSelection,
        evidence_map: Mapping[str, _EvidenceRef],
    ) -> M15EvidenceCardRecord:
        score = target.component_scores.get(selection.candidate_component_score_id)
        explanation_rows = target.explanations_by_selection.get(selection.competitor_selection_id, ())
        recall_rows = target.recall_reasons_by_candidate.get(selection.candidate_sku_code, ())
        target_profile = target.profiles_by_sku.get(selection.target_sku_code)
        candidate_profile = target.profiles_by_sku.get(selection.candidate_sku_code)
        target_tasks = target.task_scores_by_sku.get(selection.target_sku_code, ())
        candidate_tasks = target.task_scores_by_sku.get(selection.candidate_sku_code, ())
        target_groups = target.target_group_scores_by_sku.get(selection.target_sku_code, ())
        candidate_groups = target.target_group_scores_by_sku.get(selection.candidate_sku_code, ())
        target_battlefields = target.battlefield_scores_by_sku.get(selection.target_sku_code, ())
        candidate_battlefields = target.battlefield_scores_by_sku.get(selection.candidate_sku_code, ())
        target_claims = _claim_layers_for_battlefield(
            target.claim_layers_by_sku.get(selection.target_sku_code, ()),
            selection.primary_battlefield_code,
        )
        candidate_claims = _claim_layers_for_battlefield(
            target.claim_layers_by_sku.get(selection.candidate_sku_code, ()),
            selection.primary_battlefield_code,
        )
        evidence_ids = _unique_ids(
            selection.evidence_ids,
            selection.positive_evidence_ids,
            selection.weakening_evidence_ids,
            getattr(score, "evidence_ids", []) if score is not None else [],
            *(row.supporting_evidence_ids for row in explanation_rows),
            *(row.evidence_ids for row in recall_rows),
            getattr(target_profile, "representative_evidence_ids", []) if target_profile is not None else [],
            getattr(candidate_profile, "representative_evidence_ids", []) if candidate_profile is not None else [],
            *(_row_evidence_ids(row) for row in target_tasks[:2]),
            *(_row_evidence_ids(row) for row in candidate_tasks[:2]),
            *(_row_evidence_ids(row) for row in target_groups[:2]),
            *(_row_evidence_ids(row) for row in candidate_groups[:2]),
            *(_row_evidence_ids(row) for row in target_battlefields[:2]),
            *(_row_evidence_ids(row) for row in candidate_battlefields[:2]),
            *(_row_evidence_ids(row) for row in target_claims[:2]),
            *(_row_evidence_ids(row) for row in candidate_claims[:2]),
        )[:30]
        short_refs = _short_refs(evidence_ids, evidence_map)[:8]
        confidence_label = _confidence_label(selection.confidence, selection.evidence_completeness_score)
        readiness = _readiness(selection.review_required, evidence_ids, confidence_label)
        primary_battlefield_name = selection.primary_battlefield_name or _top_battlefield_name(target_battlefields) or "主战场待确认"
        target_display = _display_name(selection.target_brand_name, selection.target_model_name, selection.target_sku_code)
        competitor_display = _display_name(selection.candidate_brand_name, selection.candidate_model_name, selection.candidate_sku_code)
        price_evidence = _price_evidence(score)
        channel_evidence = _channel_evidence(score)
        param_evidence = _param_evidence(score, explanation_rows)
        claim_value_evidence = _claim_value_evidence(target_claims, candidate_claims)
        task_audience_evidence = _task_audience_evidence(target_tasks, candidate_tasks, target_groups, candidate_groups)
        market_evidence = _market_evidence(score, recall_rows)
        comment_evidence = _comment_evidence(score, target_profile, candidate_profile)
        risk_note = _risk_note(selection, score, target_claims, candidate_claims)
        evidence_matrix = _evidence_matrix(
            price_evidence=price_evidence,
            channel_evidence=channel_evidence,
            param_evidence=param_evidence,
            claim_value_evidence=claim_value_evidence,
            task_audience_evidence=task_audience_evidence,
            market_evidence=market_evidence,
            comment_evidence=comment_evidence,
            short_refs=short_refs,
        )
        one_sentence = (
            f"{competitor_display} 与 {target_display} 在{primary_battlefield_name}中重合，"
            f"{selection.selection_reason_short_cn}"
        )
        display_payload = {
            "竞品": competitor_display,
            "槽位": selection.slot_name_cn,
            "主战场": primary_battlefield_name,
            "结论": one_sentence,
            "证据": evidence_matrix,
            "风险提示": risk_note,
        }
        export_payload = {
            "标题": f"{selection.slot_name_cn}：{competitor_display}",
            "摘要": selection.business_conclusion_cn,
            "证据短号": [item["short_ref"] for item in short_refs],
        }
        input_payload = {
            "selection": selection.result_hash,
            "score": getattr(score, "result_hash", None),
            "evidence_ids": evidence_ids,
            "rule_version": rule_version,
        }
        result_payload = {
            "display": display_payload,
            "export": export_payload,
            "evidence_matrix": evidence_matrix,
        }
        input_fingerprint = stable_hash(input_payload, version="m15_card_input_v1")
        result_hash = stable_hash(result_payload, version="m15_card_result_v1")
        return M15EvidenceCardRecord(
            evidence_card_id=_record_id("m15card", batch_id, selection.target_sku_code, selection.candidate_sku_code, selection.slot_code, rule_version),
            card_id=_record_id("m15card_display", batch_id, selection.competitor_selection_id, rule_version),
            selection_run_id=selection.selection_run_id,
            selection_id=selection.competitor_selection_id,
            component_score_id=selection.candidate_component_score_id,
            candidate_pool_id=selection.candidate_pool_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=selection.target_sku_code,
            target_model_name=selection.target_model_name,
            target_display_name_cn=target_display,
            competitor_sku_code=selection.candidate_sku_code,
            competitor_model_name=selection.candidate_model_name,
            competitor_brand_name=selection.candidate_brand_name,
            competitor_display_name_cn=competitor_display,
            slot_code=selection.slot_code,
            slot_name_cn=selection.slot_name_cn,
            primary_battlefield_code=selection.primary_battlefield_code,
            primary_battlefield_name_cn=primary_battlefield_name,
            pressure_level_cn=_pressure_label(selection.pressure_level),
            readiness_level=readiness,
            confidence_label_cn=CONFIDENCE_LABELS_CN[confidence_label],
            headline_cn=f"{selection.slot_name_cn}：{competitor_display}",
            summary_cn=selection.business_conclusion_cn,
            one_sentence_reason_cn=one_sentence,
            price_evidence_cn=price_evidence,
            channel_evidence_cn=channel_evidence,
            param_evidence_cn=param_evidence,
            claim_value_evidence_cn=claim_value_evidence,
            task_audience_evidence_cn=task_audience_evidence,
            market_evidence_cn=market_evidence,
            comment_evidence_cn=comment_evidence,
            evidence_matrix_json=evidence_matrix,
            key_difference_cn=_key_difference(score),
            target_advantage_cn=_target_advantage(target_claims, target_battlefields),
            competitor_advantage_cn=_competitor_advantage(candidate_claims, candidate_battlefields),
            strategy_implication_cn=selection.strategy_hint_cn or "建议在该槽位持续跟踪价格、卖点和评论反馈变化。",
            risk_note_cn=risk_note,
            short_evidence_refs_json=short_refs,
            evidence_ids=evidence_ids,
            display_payload_json=display_payload,
            export_payload_json=export_payload,
            selection_result_hash=selection.result_hash,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
            result_hash=result_hash,
            processing_status="success",
            review_required=readiness != M15ReadinessLevel.READY,
            review_status="review_required" if readiness != M15ReadinessLevel.READY else "auto_pass",
            review_reason_json={"readiness": readiness.value, "confidence": confidence_label},
        )

    def _build_report_payload(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        target: M15TargetReportInput,
        cards: Sequence[M15EvidenceCardRecord],
        evidence_map: Mapping[str, _EvidenceRef],
    ) -> M15TargetReportPayloadRecord:
        run = target.selection_run
        profile = target.profiles_by_sku.get(run.target_sku_code)
        target_display = _display_name(run.target_brand_name, run.target_model_name, run.target_sku_code)
        selected_count = len(cards)
        empty_slots = _business_empty_slots(target.slot_decisions)
        readiness = _target_readiness(run, cards)
        confidence_label = _target_confidence(cards)
        data_quality_note = _data_quality_note(target)
        executive = _executive_conclusion(target_display, selected_count, len(empty_slots), cards)
        battlefield_summary = _battlefield_summary(target.battlefield_scores_by_sku.get(run.target_sku_code, ()))
        task_group_summary = _task_group_summary(
            target.task_scores_by_sku.get(run.target_sku_code, ()),
            target.target_group_scores_by_sku.get(run.target_sku_code, ()),
        )
        target_signal_cards = _target_signal_cards(profile)
        competitors_payload = [_card_business_payload(card) for card in cards]
        why_logic = [_why_logic(card) for card in cards]
        evidence_matrix = [item for card in cards for item in card.evidence_matrix_json]
        strategy_hints = [_strategy_hint(card) for card in cards]
        candidate_pool_summary = _candidate_pool_summary(run, target.audits)
        review_questions = _review_questions(run, cards, target.selection_issues, data_quality_note)
        sop_trace = _sop_trace(target, cards)
        short_evidence_map = _referenced_evidence_ref_payloads(evidence_map, cards)
        export_payload = {
            "标题": f"{target_display} 核心三竞品报告",
            "结论": executive,
            "竞品": competitors_payload,
            "数据口径": DATA_SCOPE_NOTE_CN,
        }
        guardrail = _guardrail_result(
            {
                "executive": executive,
                "target_signal_cards": target_signal_cards,
                "core_competitors": competitors_payload,
                "why": why_logic,
                "strategy": strategy_hints,
                "data_quality": data_quality_note,
            }
        )
        input_payload = {
            "selection_run": run.result_hash,
            "cards": [card.result_hash for card in cards],
            "empty_slots": empty_slots,
            "data_scope": DATA_SCOPE_NOTE_CN,
            "rule_version": rule_version,
        }
        result_payload = {
            "executive": executive,
            "competitors": competitors_payload,
            "sop_trace": sop_trace,
            "quality": data_quality_note,
        }
        input_fingerprint = stable_hash(input_payload, version="m15_report_input_v1")
        result_hash = stable_hash(result_payload, version="m15_report_result_v1")
        review_required = readiness != M15ReadinessLevel.READY or bool(guardrail["blocked_terms"])
        return M15TargetReportPayloadRecord(
            target_report_payload_id=_record_id("m15report", batch_id, run.target_sku_code, run.selection_run_id, rule_version),
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=run.target_sku_code,
            target_display_name_cn=target_display,
            report_title_cn=f"{target_display} 核心三竞品报告",
            executive_conclusion_cn=executive,
            readiness_level=readiness,
            confidence_label_cn=CONFIDENCE_LABELS_CN[confidence_label],
            data_scope_note_cn=DATA_SCOPE_NOTE_CN,
            target_profile_summary_cn=_target_profile_summary(profile, battlefield_summary, task_group_summary),
            selection_run_id=run.selection_run_id,
            selected_count=selected_count,
            empty_slot_count=len(empty_slots),
            battlefield_summary_json=battlefield_summary,
            task_group_summary_json=task_group_summary,
            target_signal_cards_json=target_signal_cards,
            core_competitors_json=competitors_payload,
            empty_slots_json=empty_slots,
            why_competitor_logic_json=why_logic,
            evidence_matrix_json=evidence_matrix,
            key_difference_json=[{"竞品": card.competitor_display_name_cn, "差异": card.key_difference_cn} for card in cards],
            strategy_hint_json=strategy_hints,
            sop_trace_json=sop_trace,
            candidate_pool_summary_json=candidate_pool_summary,
            review_questions_json=review_questions,
            data_quality_note_cn=data_quality_note,
            short_evidence_map_json=short_evidence_map,
            export_payload_json=export_payload,
            ui_guardrail_result_json=guardrail,
            m14_selection_fingerprint=run.result_hash,
            evidence_revision=run.evidence_revision,
            rule_version=rule_version,
            input_fingerprint=input_fingerprint,
            result_hash=result_hash,
            processing_status="success",
            review_required=review_required,
            review_status="review_required" if review_required else "auto_pass",
            review_reason_json={"guardrail": guardrail, "readiness": readiness.value},
        )

    def _build_sections(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        payload: M15TargetReportPayloadRecord,
        cards: Sequence[M15EvidenceCardRecord],
    ) -> tuple[M15ReportSectionRecord, ...]:
        section_payloads = {
            M15ReportSectionCode.EXECUTIVE: {"结论": payload.executive_conclusion_cn, "置信口径": payload.confidence_label_cn},
            M15ReportSectionCode.TARGET_PROFILE: {
                "目标商品": payload.target_display_name_cn,
                "画像摘要": payload.target_profile_summary_cn,
                "信号卡": payload.target_signal_cards_json,
            },
            M15ReportSectionCode.COMPETITOR_CARDS: {"竞品证据卡": [card.display_payload_json for card in cards]},
            M15ReportSectionCode.BATTLEFIELD_CONTEXT: payload.battlefield_summary_json,
            M15ReportSectionCode.WHY_COMPETITOR: {"推导逻辑": payload.why_competitor_logic_json},
            M15ReportSectionCode.EVIDENCE_MATRIX: {"证据矩阵": payload.evidence_matrix_json},
            M15ReportSectionCode.STRATEGY: {"业务建议": payload.strategy_hint_json},
            M15ReportSectionCode.CANDIDATE_AUDIT: payload.candidate_pool_summary_json,
            M15ReportSectionCode.SOP_TRACE: {"链路": payload.sop_trace_json},
            M15ReportSectionCode.DATA_QUALITY: {
                "数据口径": payload.data_scope_note_cn,
                "数据缺口": payload.data_quality_note_cn,
            },
            M15ReportSectionCode.EXPORT: payload.export_payload_json,
        }
        records: list[M15ReportSectionRecord] = []
        for order, code in enumerate(CORE3_M15_REPORT_SECTION_ORDER, start=1):
            section_payload = section_payloads[code]
            guardrail = _guardrail_result(section_payload)
            result_hash = stable_hash(section_payload, version="m15_section_result_v1")
            records.append(
                M15ReportSectionRecord(
                    report_section_id=_record_id("m15section", batch_id, payload.target_sku_code, payload.selection_run_id, code.value, rule_version),
                    target_report_payload_id=payload.target_report_payload_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    target_sku_code=payload.target_sku_code,
                    selection_run_id=payload.selection_run_id,
                    section_code=code,
                    section_title_cn=SECTION_TITLE_CN[code],
                    section_order=order,
                    section_payload_json=section_payload,
                    display_status=_section_display_status(code),
                    readiness_level=payload.readiness_level,
                    contains_internal_field_flag=bool(guardrail["blocked_terms"]),
                    contains_uuid_flag=bool(guardrail["uuid_count"]),
                    evidence_ids=[] if code != M15ReportSectionCode.EVIDENCE_MATRIX else _unique_ids(*(card.evidence_ids for card in cards)),
                    short_evidence_refs_json=[] if code != M15ReportSectionCode.EVIDENCE_MATRIX else [ref for card in cards for ref in card.short_evidence_refs_json],
                    rule_version=rule_version,
                    input_fingerprint=stable_hash(
                        {"payload": payload.result_hash, "code": code.value},
                        version="m15_section_input_v1",
                    ),
                    result_hash=result_hash,
                    review_required=bool(guardrail["blocked_terms"] or guardrail["uuid_count"]),
                    review_status="review_required" if guardrail["blocked_terms"] or guardrail["uuid_count"] else "auto_pass",
                    review_reason_json={"guardrail": guardrail},
                )
            )
        return tuple(records)

    def _build_exports(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        payload: M15TargetReportPayloadRecord,
        cards: Sequence[M15EvidenceCardRecord],
        sections: Sequence[M15ReportSectionRecord],
    ) -> tuple[M15ReportExportRecord, ...]:
        json_payload = _safe_json(
            {
                "标题": payload.report_title_cn,
                "结论": payload.executive_conclusion_cn,
                "目标商品": payload.target_display_name_cn,
                "竞品": payload.core_competitors_json,
                "推导链路": payload.sop_trace_json,
                "数据口径": payload.data_scope_note_cn,
            }
        )
        markdown_payload = _markdown_report(payload, cards)
        summary_payload = f"{payload.report_title_cn}\n{payload.executive_conclusion_cn}\n{payload.data_scope_note_cn}"
        cards_payload = _safe_json([card.export_payload_json for card in cards])
        export_map = {
            M15ReportExportType.JSON: ("结构化报告", json_payload, {"格式": "结构化", "字段": ["标题", "结论", "竞品", "推导链路"]}),
            M15ReportExportType.MARKDOWN: ("汇报稿", markdown_payload, {"格式": "汇报稿"}),
            M15ReportExportType.REPORT_SUMMARY: ("报告摘要", summary_payload, {"格式": "摘要"}),
            M15ReportExportType.EVIDENCE_CARDS: ("证据卡包", cards_payload, {"格式": "证据卡"}),
        }
        page_payload_hash = payload.result_hash
        records: list[M15ReportExportRecord] = []
        for export_type, (title, export_payload, export_payload_json) in export_map.items():
            checksum = stable_hash(export_payload, version="m15_export_payload_v1")
            guardrail = _guardrail_result({"payload": export_payload, "meta": export_payload_json})
            status = M15ReportExportStatus.REVIEW_REQUIRED if guardrail["blocked_terms"] or guardrail["uuid_count"] else M15ReportExportStatus.READY
            records.append(
                M15ReportExportRecord(
                    report_export_id=_record_id("m15export", batch_id, payload.target_sku_code, payload.selection_run_id, export_type.value, rule_version),
                    target_report_payload_id=payload.target_report_payload_id,
                    project_id=self.repository.project_id,
                    category_code=self.repository.category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    target_sku_code=payload.target_sku_code,
                    selection_run_id=payload.selection_run_id,
                    export_type=export_type,
                    export_title_cn=title,
                    export_payload=export_payload,
                    export_payload_json=export_payload_json,
                    data_scope_note_cn=payload.data_scope_note_cn,
                    readiness_level=payload.readiness_level,
                    checksum=checksum,
                    page_payload_hash=page_payload_hash,
                    export_status=status,
                    failure_reason="展示内容含内部字段或 UUID，需要复核。" if status != M15ReportExportStatus.READY else None,
                    rule_version=rule_version,
                    input_fingerprint=stable_hash(
                        {"payload": payload.result_hash, "sections": [section.result_hash for section in sections], "type": export_type.value},
                        version="m15_export_input_v1",
                    ),
                    result_hash=stable_hash(
                        {"checksum": checksum, "type": export_type.value},
                        version="m15_export_result_v1",
                    ),
                    review_required=status != M15ReportExportStatus.READY,
                    review_status="review_required" if status != M15ReportExportStatus.READY else "auto_pass",
                    review_reason_json={"guardrail": guardrail},
                )
            )
        return tuple(records)

    def _build_review_issues(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        target: M15TargetReportInput,
        payload: M15TargetReportPayloadRecord,
        cards: Sequence[M15EvidenceCardRecord],
        sections: Sequence[M15ReportSectionRecord],
        exports: Sequence[M15ReportExportRecord],
    ) -> tuple[M15ReportReviewIssueRecord, ...]:
        issues: list[M15ReportReviewIssueRecord] = []
        if not cards:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    payload=payload,
                    scope=M15ReportIssueScope.REPORT,
                    section_code="",
                    issue_type=M15ReportReviewIssueType.ALL_SLOTS_EMPTY.value,
                    level=M15ReportIssueLevel.REVIEW,
                    message="M14 没有形成入选竞品，报告不能展示为核心三竞品结论。",
                    suggestion="补充样例数据或人工确认是否允许空槽报告。",
                    source_payload={"selected_count": payload.selected_count, "empty_slot_count": payload.empty_slot_count},
                )
            )
        if "当前样例数据内" not in payload.data_scope_note_cn:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    payload=payload,
                    scope=M15ReportIssueScope.REPORT,
                    section_code="",
                    issue_type=M15ReportReviewIssueType.MISSING_DATA_SCOPE_NOTE.value,
                    level=M15ReportIssueLevel.BLOCKER,
                    message="报告缺少当前样例数据范围说明。",
                    suggestion="首屏必须说明样例数据、线上渠道和 26W01-26W23 时间窗口。",
                    source_payload={"data_scope_note_cn": payload.data_scope_note_cn},
                )
            )
        if _has_claim_gap(target) and "宣传卖点数据缺口" not in payload.data_quality_note_cn:
            issues.append(
                self._issue(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    payload=payload,
                    scope=M15ReportIssueScope.REPORT,
                    section_code=M15ReportSectionCode.DATA_QUALITY.value,
                    issue_type=M15ReportReviewIssueType.CLAIM_GAP_NOT_DISCLOSED.value,
                    level=M15ReportIssueLevel.REVIEW,
                    message="上游宣传卖点证据不足，但报告没有按数据缺口说明。",
                    suggestion="使用“宣传卖点数据缺口”表述，不要写成卖点弱。",
                    source_payload={"data_quality_note_cn": payload.data_quality_note_cn},
                )
            )
        for card in cards:
            if not card.short_evidence_refs_json:
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        payload=payload,
                        scope=M15ReportIssueScope.CARD,
                        section_code=M15ReportSectionCode.COMPETITOR_CARDS.value,
                        issue_type=M15ReportReviewIssueType.MISSING_EVIDENCE.value,
                        level=M15ReportIssueLevel.REVIEW,
                        message=f"{card.competitor_display_name_cn} 证据卡缺少可展示证据短号。",
                        suggestion="补充上游参数、市场、评论或卖点证据后重新生成。",
                        source_payload={"competitor": card.competitor_display_name_cn},
                        evidence_card_id=card.evidence_card_id,
                    )
                )
            if _guardrail_result(card.display_payload_json)["blocked_terms"]:
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        payload=payload,
                        scope=M15ReportIssueScope.CARD,
                        section_code=M15ReportSectionCode.COMPETITOR_CARDS.value,
                        issue_type=M15ReportReviewIssueType.INTERNAL_FIELD_EXPOSED.value,
                        level=M15ReportIssueLevel.BLOCKER,
                        message=f"{card.competitor_display_name_cn} 证据卡含内部字段或过程性表达。",
                        suggestion="只保留业务语言和证据短号。",
                        source_payload=card.display_payload_json,
                        evidence_card_id=card.evidence_card_id,
                    )
                )
        for section in sections:
            if section.contains_internal_field_flag or section.contains_uuid_flag:
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        payload=payload,
                        scope=M15ReportIssueScope.SECTION,
                        section_code=str(section.section_code),
                        issue_type=M15ReportReviewIssueType.INTERNAL_FIELD_EXPOSED.value if section.contains_internal_field_flag else M15ReportReviewIssueType.UUID_EXPOSED.value,
                        level=M15ReportIssueLevel.BLOCKER,
                        message=f"{section.section_title_cn} 含内部字段或 UUID，不适合业务页展示。",
                        suggestion="业务页只展示中文结论、证据短号和数据口径。",
                        source_payload={"section": section.section_title_cn},
                        report_section_id=section.report_section_id,
                    )
                )
        for export in exports:
            if export.export_status != M15ReportExportStatus.READY:
                issues.append(
                    self._issue(
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        payload=payload,
                        scope=M15ReportIssueScope.EXPORT,
                        section_code=M15ReportSectionCode.EXPORT.value,
                        issue_type=M15ReportReviewIssueType.EXPORT_PAYLOAD_MISMATCH.value,
                        level=M15ReportIssueLevel.REVIEW,
                        message=f"{export.export_title_cn} 需要复核后再对外展示。",
                        suggestion="检查导出内容是否含内部字段、UUID 或技术表达。",
                        source_payload={"export_type": str(export.export_type), "failure_reason": export.failure_reason},
                        report_export_id=export.report_export_id,
                    )
                )
        return tuple(issues)

    def _issue(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        payload: M15TargetReportPayloadRecord,
        scope: M15ReportIssueScope,
        section_code: str,
        issue_type: str,
        level: M15ReportIssueLevel,
        message: str,
        suggestion: str,
        source_payload: dict[str, Any],
        evidence_card_id: str | None = None,
        report_section_id: str | None = None,
        report_export_id: str | None = None,
    ) -> M15ReportReviewIssueRecord:
        fingerprint = stable_hash(
            {
                "target": payload.target_sku_code,
                "selection_run": payload.selection_run_id,
                "scope": scope.value,
                "section": section_code,
                "issue_type": issue_type,
                "source": source_payload,
            },
            version="m15_issue_input_v1",
        )
        return M15ReportReviewIssueRecord(
            report_review_issue_id=_record_id("m15issue", batch_id, payload.target_sku_code, payload.selection_run_id, scope.value, section_code, issue_type, fingerprint),
            target_report_payload_id=payload.target_report_payload_id,
            evidence_card_id=evidence_card_id,
            report_section_id=report_section_id,
            report_export_id=report_export_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            target_sku_code=payload.target_sku_code,
            selection_run_id=payload.selection_run_id,
            issue_scope=scope,
            section_code=section_code,
            issue_type=issue_type,
            issue_level=level,
            issue_message_cn=message,
            suggested_action_cn=suggestion,
            source_payload_json=source_payload,
            evidence_ids=[],
            rule_version=rule_version,
            input_fingerprint=fingerprint,
            result_hash=stable_hash({"message": message, "suggestion": suggestion}, version="m15_issue_result_v1"),
        )


def _build_short_evidence_map(evidence_atoms: Mapping[str, entities.Core3EvidenceAtom]) -> dict[str, _EvidenceRef]:
    result: dict[str, _EvidenceRef] = {}
    for index, evidence_id in enumerate(sorted(evidence_atoms.keys()), start=1):
        atom = evidence_atoms[evidence_id]
        result[evidence_id] = _EvidenceRef(
            short_ref=f"证据{index}",
            evidence_id=evidence_id,
            domain_cn=_evidence_domain_cn(atom),
            title_cn=_clean_text(atom.evidence_title) or _field_label_cn(atom.evidence_field),
            source_cn=_source_label_cn(atom.clean_table or atom.source_table),
            snippet_cn=_clean_text(atom.clean_value or atom.text_value or atom.raw_value)[:120] or "证据内容待补充",
        )
    return result


def _short_refs(evidence_ids: Iterable[str], evidence_map: Mapping[str, _EvidenceRef]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for evidence_id in evidence_ids:
        ref = evidence_map.get(evidence_id)
        if ref is None:
            continue
        refs.append(
            {
                "short_ref": ref.short_ref,
                "evidence_domain_cn": ref.domain_cn,
                "evidence_title_cn": ref.title_cn,
                "source_cn": ref.source_cn,
                "snippet_cn": ref.snippet_cn,
            }
        )
    return refs


def _referenced_evidence_ref_payloads(
    evidence_map: Mapping[str, _EvidenceRef],
    cards: Sequence[M15EvidenceCardRecord],
) -> list[dict[str, Any]]:
    referenced_short_refs = {
        str(item.get("short_ref"))
        for card in cards
        for item in card.short_evidence_refs_json
        if isinstance(item, dict) and item.get("short_ref")
    }
    return [
        _evidence_ref_payload(ref)
        for ref in evidence_map.values()
        if ref.short_ref in referenced_short_refs
    ]


def _evidence_ref_payload(ref: _EvidenceRef) -> dict[str, Any]:
    return {
        "short_ref": ref.short_ref,
        "evidence_domain_cn": ref.domain_cn,
        "evidence_title_cn": ref.title_cn,
        "source_cn": ref.source_cn,
        "snippet_cn": ref.snippet_cn,
        "evidence_id": ref.evidence_id,
    }


def _display_name(brand: str | None, model_name: str | None, sku_code: str) -> str:
    parts = [part for part in (brand, model_name or sku_code) if part]
    return " ".join(parts) if parts else sku_code


def _claim_layers_for_battlefield(rows: Sequence[entities.Core3SkuClaimValueLayer], battlefield_code: str | None) -> tuple[entities.Core3SkuClaimValueLayer, ...]:
    if not battlefield_code:
        return tuple(rows[:3])
    matched = tuple(row for row in rows if row.battlefield_code == battlefield_code)
    return matched[:3] if matched else tuple(rows[:3])


def _price_evidence(score: entities.Core3CandidateComponentScore | None) -> str:
    if score is None:
        return "价格带证据不足，需结合后续样例补齐。"
    return f"价格位置接近度为 {_pct(score.price_position_score)}，价格优势信号为 {_pct(score.price_advantage_score)}。"


def _channel_evidence(score: entities.Core3CandidateComponentScore | None) -> str:
    if score is None:
        return "渠道重合证据不足。"
    return f"渠道重合度为 {_pct(score.channel_overlap_score)}，说明当前样例内具备可比较渠道基础。"


def _param_evidence(score: entities.Core3CandidateComponentScore | None, explanations: Sequence[entities.Core3CandidateComponentExplanation]) -> str:
    if score is None:
        return "参数证据不足。"
    detail = next((row.business_explanation_cn for row in explanations if row.component_code in {"base_comparability", "param_similarity"}), "")
    prefix = f"参数相似度为 {_pct(score.param_similarity_score)}，参数压制信号为 {_pct(score.param_superiority_score)}。"
    return f"{prefix}{detail}" if detail else prefix


def _claim_value_evidence(
    target_claims: Sequence[entities.Core3SkuClaimValueLayer],
    candidate_claims: Sequence[entities.Core3SkuClaimValueLayer],
) -> str:
    if not target_claims and not candidate_claims:
        return CLAIM_GAP_NOTE_CN
    target_names = "、".join(row.claim_name_cn for row in target_claims[:2]) or "目标商品卖点不足"
    candidate_names = "、".join(row.claim_name_cn for row in candidate_claims[:2]) or "竞品卖点不足"
    return f"目标商品主要卖点线索为 {target_names}；竞品主要卖点线索为 {candidate_names}。"


def _task_audience_evidence(
    target_tasks: Sequence[entities.Core3SkuTaskScore],
    candidate_tasks: Sequence[entities.Core3SkuTaskScore],
    target_groups: Sequence[entities.Core3SkuTargetGroupScore],
    candidate_groups: Sequence[entities.Core3SkuTargetGroupScore],
) -> str:
    target_task = _top_name(target_tasks, "task_name_cn", "用户任务待确认")
    candidate_task = _top_name(candidate_tasks, "task_name_cn", "用户任务待确认")
    target_group = _top_name(target_groups, "target_group_name_cn", "客群待确认")
    candidate_group = _top_name(candidate_groups, "target_group_name_cn", "客群待确认")
    return f"目标商品集中在“{target_task} / {target_group}”；竞品集中在“{candidate_task} / {candidate_group}”。"


def _market_evidence(score: entities.Core3CandidateComponentScore | None, recall_rows: Sequence[entities.Core3CandidateRecallReason]) -> str:
    recall_summary = "；".join(row.reason_summary_cn for row in recall_rows[:2])
    if score is None:
        return recall_summary or "市场证据不足。"
    base = f"市场威胁信号为 {_pct(score.market_threat_score)}，销售额强度信号为 {_pct(score.sales_amount_strength_score)}。"
    return f"{base}{recall_summary}" if recall_summary else base


def _comment_evidence(
    score: entities.Core3CandidateComponentScore | None,
    target_profile: entities.Core3SkuSignalProfile | None,
    candidate_profile: entities.Core3SkuSignalProfile | None,
) -> str:
    comment_score = _pct(score.comment_perception_score) if score is not None else "不足"
    target_comment = _comment_summary(target_profile)
    candidate_comment = _comment_summary(candidate_profile)
    return f"评论感知信号为 {comment_score}。目标商品：{target_comment}；竞品：{candidate_comment}。{SERVICE_GUARD_NOTE_CN}"


def _comment_summary(profile: entities.Core3SkuSignalProfile | None) -> str:
    if profile is None or not profile.comment_signal_summary_json:
        return "评论样本待补充"
    summary = profile.comment_signal_summary_json
    if isinstance(summary, dict):
        for key in ("summary_cn", "business_summary_cn", "comment_summary_cn"):
            if summary.get(key):
                return str(summary[key])
        return f"评论线索 {len(summary)} 类"
    return "评论线索已形成"


def _risk_note(
    selection: entities.Core3CompetitorSelection,
    score: entities.Core3CandidateComponentScore | None,
    target_claims: Sequence[entities.Core3SkuClaimValueLayer],
    candidate_claims: Sequence[entities.Core3SkuClaimValueLayer],
) -> str:
    notes = []
    if selection.review_required:
        notes.append(selection.review_reason or "该竞品需要人工复核。")
    if score is not None and score.service_reference_score > max(score.direct_fight_score, score.price_volume_pressure_score, score.benchmark_potential_score):
        notes.append(SERVICE_GUARD_NOTE_CN)
    if not target_claims or not candidate_claims:
        notes.append(CLAIM_GAP_NOTE_CN)
    return "；".join(notes) if notes else "当前样例证据可支撑业务展示，仍需随新增数据持续复核。"


def _evidence_matrix(**kwargs: Any) -> list[dict[str, Any]]:
    labels = {
        "price_evidence": "价格位置",
        "channel_evidence": "渠道重合",
        "param_evidence": "参数能力",
        "claim_value_evidence": "卖点价值",
        "task_audience_evidence": "任务客群",
        "market_evidence": "市场验证",
        "comment_evidence": "评论感知",
    }
    short_refs = kwargs.get("short_refs") or []
    refs = [item["short_ref"] for item in short_refs[:3]]
    return [
        {"维度": label, "判断": value, "证据短号": refs}
        for key, label in labels.items()
        for value in [kwargs.get(key)]
        if value
    ]


def _key_difference(score: entities.Core3CandidateComponentScore | None) -> str:
    if score is None:
        return "差异证据不足，需要补齐组件评分。"
    if score.param_superiority_score > score.param_similarity_score:
        return "竞品在部分参数能力上形成压迫，需要重点对比参数表达。"
    if score.claim_superiority_score > score.claim_confrontation_score:
        return "竞品卖点表达更强，需要复核卖点对位关系。"
    return "双方差异主要来自价格、渠道、任务客群和价值战场组合。"


def _target_advantage(claims: Sequence[entities.Core3SkuClaimValueLayer], battlefields: Sequence[entities.Core3SkuBattlefieldScore]) -> str:
    battlefield = _top_battlefield_name(battlefields)
    claim = _top_name(claims, "claim_name_cn", "")
    if battlefield and claim:
        return f"目标商品在{battlefield}中已有“{claim}”卖点支撑。"
    if battlefield:
        return f"目标商品在{battlefield}中有战场信号，但宣传卖点仍需补齐。"
    return "目标商品优势需要结合新增样例继续确认。"


def _competitor_advantage(claims: Sequence[entities.Core3SkuClaimValueLayer], battlefields: Sequence[entities.Core3SkuBattlefieldScore]) -> str:
    battlefield = _top_battlefield_name(battlefields)
    claim = _top_name(claims, "claim_name_cn", "")
    if battlefield and claim:
        return f"竞品在{battlefield}中以“{claim}”形成可对位表达。"
    if battlefield:
        return f"竞品在{battlefield}中有战场信号，但卖点证据不足。"
    return "竞品优势需要结合新增样例继续确认。"


def _card_business_payload(card: M15EvidenceCardRecord) -> dict[str, Any]:
    return {
        "槽位": card.slot_name_cn,
        "竞品": card.competitor_display_name_cn,
        "主战场": card.primary_battlefield_name_cn,
        "结论": card.one_sentence_reason_cn,
        "置信": card.confidence_label_cn,
        "证据短号": [item["short_ref"] for item in card.short_evidence_refs_json],
    }


def _why_logic(card: M15EvidenceCardRecord) -> dict[str, Any]:
    return {
        "竞品": card.competitor_display_name_cn,
        "第一步": f"先确认目标商品主战场：{card.primary_battlefield_name_cn}",
        "第二步": f"再看槽位定位：{card.slot_name_cn}",
        "第三步": card.one_sentence_reason_cn,
        "证据": [item["short_ref"] for item in card.short_evidence_refs_json[:5]],
    }


def _strategy_hint(card: M15EvidenceCardRecord) -> dict[str, Any]:
    return {
        "竞品": card.competitor_display_name_cn,
        "动作建议": card.strategy_implication_cn,
        "风险提示": card.risk_note_cn,
    }


def _business_empty_slots(slot_decisions: Sequence[entities.Core3CompetitorSlotDecision]) -> list[dict[str, Any]]:
    return [
        {
            "槽位": row.slot_name_cn,
            "原因": row.empty_reason_cn or row.review_reason or row.decision_summary_cn,
            "处理建议": "保留空槽，等待新增真实样例或人工复核，不强行补弱竞品。",
        }
        for row in slot_decisions
        if row.decision_status in {"empty", "review_required", "blocked"} and not row.selected_competitor_selection_id
    ]


def _target_readiness(run: entities.Core3CompetitorSelectionRun, cards: Sequence[M15EvidenceCardRecord]) -> M15ReadinessLevel:
    if run.selected_count == 0:
        return M15ReadinessLevel.INSUFFICIENT
    if run.review_required or any(card.readiness_level != M15ReadinessLevel.READY for card in cards):
        return M15ReadinessLevel.REVIEW_REQUIRED
    return M15ReadinessLevel.READY


def _target_confidence(cards: Sequence[M15EvidenceCardRecord]) -> str:
    if not cards:
        return "review_required"
    labels = {card.confidence_label_cn for card in cards}
    if "待复核" in labels:
        return "review_required"
    if "低" in labels:
        return "low"
    if labels == {"高"}:
        return "high"
    return "medium"


def _executive_conclusion(target_display: str, selected_count: int, empty_slot_count: int, cards: Sequence[M15EvidenceCardRecord]) -> str:
    if selected_count == 0:
        return f"当前样例数据内，{target_display} 暂未形成可对外汇报的核心竞品结论，建议先补齐候选和证据。"
    names = "、".join(card.competitor_display_name_cn for card in cards[:3])
    suffix = f"；另有 {empty_slot_count} 个槽位保持空槽" if empty_slot_count else ""
    return f"当前样例数据内，{target_display} 已形成 {selected_count} 个核心竞品：{names}{suffix}。这些结论来自三槽位选择和上游证据链，不是简单总分排名。"


def _battlefield_summary(rows: Sequence[entities.Core3SkuBattlefieldScore]) -> dict[str, Any]:
    top_rows = list(rows[:3])
    return {
        "主战场": [
            {
                "名称": row.battlefield_name_cn,
                "关系": row.relation_level,
                "业务原因": row.business_reason_cn,
            }
            for row in top_rows
        ],
        "说明": "价值战场来自任务、客群、卖点、参数、评论和市场信号综合判断。",
    }


def _task_group_summary(
    task_rows: Sequence[entities.Core3SkuTaskScore],
    group_rows: Sequence[entities.Core3SkuTargetGroupScore],
) -> dict[str, Any]:
    return {
        "核心任务": [{"名称": row.task_name_cn, "原因": row.business_reason_cn} for row in task_rows[:3]],
        "核心客群": [{"名称": row.target_group_name_cn, "原因": row.business_reason_cn} for row in group_rows[:3]],
    }


def _target_signal_cards(profile: entities.Core3SkuSignalProfile | None) -> list[dict[str, Any]]:
    if profile is None:
        return [{"名称": "数据画像", "判断": "目标商品画像缺失，需要补齐 M08 结果。"}]
    return [
        {"名称": "数据完整度", "判断": f"当前画像完整度 {_pct(profile.data_completeness_score)}，置信度 {_pct(profile.confidence)}。"},
        {"名称": "市场信号", "判断": _summarize_json(profile.market_signal_summary_json, "市场信号已形成。")},
        {"名称": "评论信号", "判断": _comment_summary(profile)},
    ]


def _target_profile_summary(
    profile: entities.Core3SkuSignalProfile | None,
    battlefield_summary: Mapping[str, Any],
    task_group_summary: Mapping[str, Any],
) -> str:
    if profile is None:
        return "目标商品画像缺失，暂不能做完整高层汇报。"
    battlefield_names = "、".join(item["名称"] for item in battlefield_summary.get("主战场", [])[:2]) or "主战场待确认"
    task_names = "、".join(item["名称"] for item in task_group_summary.get("核心任务", [])[:2]) or "核心任务待确认"
    return f"目标商品当前画像完整度 {_pct(profile.data_completeness_score)}，主要围绕 {battlefield_names}，核心任务为 {task_names}。"


def _candidate_pool_summary(run: entities.Core3CompetitorSelectionRun, audits: Sequence[entities.Core3CompetitorSelectionAudit]) -> dict[str, Any]:
    return {
        "候选总数": run.candidate_count,
        "已评分候选": run.scored_candidate_count,
        "入选": run.selected_count,
        "待复核": run.review_candidate_count,
        "阻断": run.blocked_candidate_count,
        "审计摘要": [
            {
                "商品": _display_name(row.candidate_brand_name, row.candidate_model_name, row.candidate_sku_code),
                "判断": _audit_decision_cn(row.audit_decision),
                "原因": row.decision_reason_cn,
            }
            for row in audits[:10]
        ],
    }


def _review_questions(
    run: entities.Core3CompetitorSelectionRun,
    cards: Sequence[M15EvidenceCardRecord],
    upstream_issues: Sequence[entities.Core3CompetitorSelectionReviewIssue],
    data_quality_note: str,
) -> list[dict[str, Any]]:
    questions = []
    if run.empty_slot_count:
        questions.append({"问题": "是否接受空槽", "建议": "若业务必须展示三竞品，需要人工确认补位规则。"})
    if "宣传卖点数据缺口" in data_quality_note:
        questions.append({"问题": "卖点证据是否足够", "建议": "补充结构化宣传卖点后再强化卖点对位。"})
    questions.extend({"问题": issue.issue_message_cn, "建议": issue.suggested_action_cn} for issue in upstream_issues[:5])
    if not questions and any(card.review_required for card in cards):
        questions.append({"问题": "低置信证据卡", "建议": "优先复核待复核证据卡。"})
    return questions


def _sop_trace(target: M15TargetReportInput, cards: Sequence[M15EvidenceCardRecord]) -> list[dict[str, Any]]:
    run = target.selection_run
    return [
        {"步骤": 1, "名称": "SKU 信号画像", "结论": "汇总参数、卖点、评论和市场信号，形成目标与候选商品画像。"},
        {"步骤": 2, "名称": "用户任务识别", "结论": "从卖点、参数、评论主题和市场共现中识别核心购买任务。"},
        {"步骤": 3, "名称": "目标客群判断", "结论": "结合任务、价格带、渠道和评论线索判断目标客群。"},
        {"步骤": 4, "名称": "价值战场判定", "结论": "把任务、客群、卖点、参数与市场验证合并为价值战场。"},
        {"步骤": 5, "名称": "候选池召回", "结论": f"当前候选池共 {run.candidate_count} 个候选，允许同品牌 SKU 进入比较。"},
        {"步骤": 6, "名称": "组件评分", "结论": "对候选做可比性、战场适配、任务客群、卖点、参数、市场和评论组件评分。"},
        {"步骤": 7, "名称": "三槽位选择", "结论": f"最终形成 {len(cards)} 个入选竞品；空槽保留原因，不强行补齐。"},
    ]


def _data_quality_note(target: M15TargetReportInput) -> str:
    notes = [DATA_SCOPE_NOTE_CN]
    if _has_claim_gap(target):
        notes.append(CLAIM_GAP_NOTE_CN)
    notes.append(SERVICE_GUARD_NOTE_CN)
    return "；".join(notes)


def _has_claim_gap(target: M15TargetReportInput) -> bool:
    target_code = target.selection_run.target_sku_code
    target_claims = target.claim_layers_by_sku.get(target_code, ())
    if not target_claims:
        return True
    return any("claim" in str(item).lower() or "卖点" in str(item) for item in getattr(target.profiles_by_sku.get(target_code), "missing_signals_json", []) or [])


def _guardrail_result(payload: Any) -> dict[str, Any]:
    text = _safe_json(payload)
    blocked_terms = [term for term in CORE3_M15_FORBIDDEN_OUTPUT_FIELDS if term and term in text]
    return {
        "passed": not blocked_terms and not UUID_PATTERN.search(text),
        "blocked_terms": blocked_terms,
        "uuid_count": len(UUID_PATTERN.findall(text)),
    }


def _readiness(review_required: bool, evidence_ids: Sequence[str], confidence_label: str) -> M15ReadinessLevel:
    if not evidence_ids:
        return M15ReadinessLevel.REVIEW_REQUIRED
    if review_required or confidence_label in {"low", "review_required"}:
        return M15ReadinessLevel.REVIEW_REQUIRED
    return M15ReadinessLevel.READY


def _confidence_label(*scores: Any) -> str:
    values = [_decimal(score) for score in scores if score is not None]
    if not values:
        return "review_required"
    minimum = min(values)
    if minimum >= Decimal("0.7500"):
        return "high"
    if minimum >= Decimal("0.4500"):
        return "medium"
    if minimum > Decimal("0.0000"):
        return "low"
    return "review_required"


def _pressure_label(value: str | None) -> str:
    return {
        "high": "高压力",
        "medium_high": "中高压力",
        "medium": "中等压力",
        "review_required": "需复核",
    }.get(str(value or ""), "中等压力")


def _audit_decision_cn(value: str | None) -> str:
    return {
        "selected": "入选",
        "review": "待复核",
        "blocked": "阻断",
        "rejected": "未选",
    }.get(str(value or ""), "未选")


def _section_display_status(code: M15ReportSectionCode) -> M15ReportSectionDisplayStatus:
    if code in {
        M15ReportSectionCode.EXECUTIVE,
        M15ReportSectionCode.COMPETITOR_CARDS,
        M15ReportSectionCode.WHY_COMPETITOR,
    }:
        return M15ReportSectionDisplayStatus.VISIBLE
    if code == M15ReportSectionCode.EXPORT:
        return M15ReportSectionDisplayStatus.HIDDEN
    return M15ReportSectionDisplayStatus.COLLAPSED


def _markdown_report(payload: M15TargetReportPayloadRecord, cards: Sequence[M15EvidenceCardRecord]) -> str:
    lines = [
        f"# {payload.report_title_cn}",
        "",
        payload.executive_conclusion_cn,
        "",
        "## 核心竞品",
    ]
    for card in cards:
        lines.extend(
            [
                f"- {card.slot_name_cn}：{card.competitor_display_name_cn}",
                f"  - {card.one_sentence_reason_cn}",
                f"  - 证据：{'、'.join(item['short_ref'] for item in card.short_evidence_refs_json[:5]) or '待补充'}",
            ]
        )
    lines.extend(["", "## 数据口径", payload.data_scope_note_cn, payload.data_quality_note_cn])
    return "\n".join(lines)


def _evidence_domain_cn(atom: entities.Core3EvidenceAtom) -> str:
    text = " ".join(str(value or "") for value in (atom.evidence_type, atom.clean_table, atom.source_table, atom.evidence_field)).lower()
    if "comment" in text or "评论" in text:
        return "评论证据"
    if "claim" in text or "promo" in text or "卖点" in text:
        return "卖点证据"
    if "param" in text or "attribute" in text or "参数" in text:
        return "参数证据"
    if "market" in text or "sales" in text or "price" in text:
        return "市场证据"
    return "综合证据"


def _source_label_cn(value: str | None) -> str:
    text = str(value or "").lower()
    if "comment" in text:
        return "用户评论"
    if "claim" in text or "promo" in text:
        return "宣传卖点"
    if "market" in text or "sales" in text or "price" in text:
        return "市场数据"
    if "attribute" in text or "param" in text:
        return "参数数据"
    return "样例数据"


def _field_label_cn(value: str | None) -> str:
    text = str(value or "")
    return {
        "price": "价格",
        "sales": "销量",
        "comment": "评论",
        "claim": "卖点",
        "param": "参数",
    }.get(text.lower(), text or "证据")


def _top_battlefield_name(rows: Sequence[entities.Core3SkuBattlefieldScore]) -> str:
    return _top_name(rows, "battlefield_name_cn", "")


def _top_name(rows: Sequence[Any], field_name: str, fallback: str) -> str:
    return str(getattr(rows[0], field_name, "") or fallback) if rows else fallback


def _summarize_json(value: Any, fallback: str) -> str:
    if not value:
        return fallback
    if isinstance(value, dict):
        for key in ("summary_cn", "business_summary_cn", "reason_cn"):
            if value.get(key):
                return str(value[key])
        return fallback
    return str(value)


def _unique_ids(*groups: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not group:
            continue
        for value in group:
            text = str(value)
            if text and text not in seen:
                seen.add(text)
                result.append(text)
    return result


def _row_evidence_ids(row: Any) -> list[str]:
    result: list[str] = []
    for field_name in (
        "evidence_ids",
        "representative_evidence_ids",
        "supporting_evidence_ids",
        "positive_evidence_ids",
        "weakening_evidence_ids",
    ):
        values = getattr(row, field_name, None)
        if values:
            result.extend(str(value) for value in values if value)
    return result


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _pct(value: Any) -> str:
    return f"{(_decimal(value) * Decimal('100')).quantize(Decimal('1'))}%"


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _record_id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{stable_hash(parts, version=prefix).split(':')[-1][:48]}"
