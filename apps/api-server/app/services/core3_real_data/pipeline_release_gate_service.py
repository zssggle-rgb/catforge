"""M16 release gate evaluation."""

from __future__ import annotations

from typing import Any

from app.models import entities
from app.services.core3_real_data.constants import Core3ReleaseGateStatus, Core3ReviewSeverity


class ReleaseGateService:
    def evaluate(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        reports: list[entities.Core3TargetReportPayload],
        cards: list[entities.Core3ReportEvidenceCard],
        reviews: list[entities.Core3V2ReviewQueue],
    ) -> list[dict[str, Any]]:
        cards_by_target: dict[str, list[entities.Core3ReportEvidenceCard]] = {}
        for card in cards:
            cards_by_target.setdefault(card.target_sku_code, []).append(card)
        reviews_by_target: dict[str, list[entities.Core3V2ReviewQueue]] = {}
        for review in reviews:
            if review.target_sku_code:
                reviews_by_target.setdefault(review.target_sku_code, []).append(review)

        gates: list[dict[str, Any]] = []
        for report in reports:
            target_reviews = reviews_by_target.get(report.target_sku_code, [])
            target_cards = cards_by_target.get(report.target_sku_code, [])
            status, reason, required_review_ids, warning_review_ids, checks = self._target_gate(
                report=report,
                cards=target_cards,
                reviews=target_reviews,
            )
            gates.append(
                {
                    "run_id": run_id,
                    "project_id": project_id,
                    "category_code": category_code,
                    "batch_id": batch_id,
                    "target_sku_code": report.target_sku_code,
                    "report_payload_id": report.target_report_payload_id,
                    "selection_run_id": report.selection_run_id,
                    "gate_status": status.value,
                    "gate_reason_cn": reason,
                    "required_review_ids": required_review_ids,
                    "warning_review_ids": warning_review_ids,
                    "data_scope_note_cn": report.data_scope_note_cn or "当前为样例数据验收结果，不能外推全市场。",
                    "display_badges_json": _display_badges(report, status, bool(warning_review_ids)),
                    "gate_check_json": checks,
                }
            )
        return gates

    def _target_gate(
        self,
        *,
        report: entities.Core3TargetReportPayload,
        cards: list[entities.Core3ReportEvidenceCard],
        reviews: list[entities.Core3V2ReviewQueue],
    ) -> tuple[Core3ReleaseGateStatus, str, list[str], list[str], dict[str, Any]]:
        open_reviews = [item for item in reviews if item.review_status == "pending"]
        blockers = [item for item in open_reviews if item.severity == Core3ReviewSeverity.BLOCKER.value]
        high_reviews = [item for item in open_reviews if item.severity == Core3ReviewSeverity.HIGH.value]
        warnings = [
            item
            for item in open_reviews
            if item.severity in {Core3ReviewSeverity.MEDIUM.value, Core3ReviewSeverity.LOW.value}
        ]
        card_coverage_ok = report.selected_count == 0 or len(cards) >= report.selected_count
        card_evidence_ok = report.selected_count == 0 or any(card.evidence_ids for card in cards)
        data_scope_ok = "当前样例数据内" in (report.data_scope_note_cn or report.data_quality_note_cn or "")
        checks = {
            "selected_count": report.selected_count,
            "empty_slot_count": report.empty_slot_count,
            "evidence_card_count": len(cards),
            "card_coverage_ok": card_coverage_ok,
            "card_evidence_ok": card_evidence_ok,
            "data_scope_ok": data_scope_ok,
            "open_blocker_count": len(blockers),
            "open_high_count": len(high_reviews),
            "open_warning_count": len(warnings),
        }
        if blockers:
            return (
                Core3ReleaseGateStatus.BLOCKED,
                "存在阻断级复核问题，不能进入高层展示。",
                [item.review_id for item in blockers],
                [item.review_id for item in warnings],
                checks,
            )
        if report.selected_count > 0 and (not card_coverage_ok or not card_evidence_ok):
            return (
                Core3ReleaseGateStatus.BLOCKED,
                "核心竞品缺少可追溯证据卡，不能发布。",
                [],
                [item.review_id for item in warnings],
                checks,
            )
        if not data_scope_ok:
            return (
                Core3ReleaseGateStatus.REVIEW_REQUIRED,
                "报告需要补充样例数据范围说明后再展示。",
                [item.review_id for item in high_reviews],
                [item.review_id for item in warnings],
                checks,
            )
        if high_reviews:
            return (
                Core3ReleaseGateStatus.REVIEW_REQUIRED,
                "存在高优先级复核问题，可查看但暂不建议正式汇报。",
                [item.review_id for item in high_reviews],
                [item.review_id for item in warnings],
                checks,
            )
        if warnings or report.empty_slot_count > 0 or report.readiness_level == "limited":
            return (
                Core3ReleaseGateStatus.RELEASABLE,
                "可用于业务预览和汇报，但需同步说明样例范围、空槽或数据覆盖限制。",
                [],
                [item.review_id for item in warnings],
                checks,
            )
        return (
            Core3ReleaseGateStatus.RELEASABLE,
            "可用于业务展示，已通过 M16 发布门禁。",
            [],
            [],
            checks,
        )


def derive_release_status(gates: list[entities.Core3V2ReleaseGate]) -> Core3ReleaseGateStatus:
    if not gates:
        return Core3ReleaseGateStatus.NOT_READY
    statuses = {gate.gate_status for gate in gates}
    if Core3ReleaseGateStatus.BLOCKED.value in statuses:
        return Core3ReleaseGateStatus.BLOCKED
    if Core3ReleaseGateStatus.REVIEW_REQUIRED.value in statuses:
        return Core3ReleaseGateStatus.REVIEW_REQUIRED
    if statuses == {Core3ReleaseGateStatus.RELEASED.value}:
        return Core3ReleaseGateStatus.RELEASED
    return Core3ReleaseGateStatus.RELEASABLE


def _display_badges(
    report: entities.Core3TargetReportPayload,
    status: Core3ReleaseGateStatus,
    has_warning: bool,
) -> list[dict[str, Any]]:
    badges = [{"label_cn": _status_label(status), "tone": status.value}]
    if "线上" in (report.data_scope_note_cn or ""):
        badges.append({"label_cn": "线上样例", "tone": "info"})
    if "同品牌" in (report.data_scope_note_cn or ""):
        badges.append({"label_cn": "同品牌样例", "tone": "info"})
    if report.empty_slot_count > 0:
        badges.append({"label_cn": "存在空槽说明", "tone": "warning"})
    if has_warning:
        badges.append({"label_cn": "需带说明", "tone": "warning"})
    return badges


def _status_label(status: Core3ReleaseGateStatus) -> str:
    return {
        Core3ReleaseGateStatus.NOT_READY: "未就绪",
        Core3ReleaseGateStatus.REVIEW_REQUIRED: "需复核",
        Core3ReleaseGateStatus.RELEASABLE: "可汇报",
        Core3ReleaseGateStatus.RELEASED: "已发布",
        Core3ReleaseGateStatus.BLOCKED: "阻断",
    }[status]
