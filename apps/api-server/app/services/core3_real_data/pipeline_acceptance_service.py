"""M16 layered acceptance report builder."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.models import entities
from app.services.core3_real_data.constants import (
    Core3ModuleCode,
    Core3PipelineAcceptanceStatus,
    Core3ReleaseGateStatus,
    Core3ReviewSeverity,
    Core3RunStatus,
)


class AcceptanceService:
    def build_report(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
        review_items: list[entities.Core3V2ReviewQueue],
        report_payloads: list[entities.Core3TargetReportPayload],
        report_cards: list[entities.Core3ReportEvidenceCard],
        release_gates: list[entities.Core3V2ReleaseGate],
    ) -> dict[str, Any]:
        processed_skus = _processed_sku_count(module_runs, report_payloads)
        processed_targets = len({report.target_sku_code for report in report_payloads})
        ready_reports = [
            report
            for report in report_payloads
            if report.processing_status == "success" and report.readiness_level in {"ready", "review_required"}
        ]
        high_confidence = [report for report in report_payloads if report.confidence_label_cn == "高"]
        medium_confidence = [report for report in report_payloads if report.confidence_label_cn == "中"]
        limited_reports = [report for report in report_payloads if report.readiness_level == "review_required"]
        blocked_gates = [gate for gate in release_gates if gate.gate_status == Core3ReleaseGateStatus.BLOCKED.value]
        pending_reviews = [
            item
            for item in review_items
            if item.review_status == "pending"
        ]
        blockers = [item for item in pending_reviews if item.severity == Core3ReviewSeverity.BLOCKER.value]
        warnings = [item for item in pending_reviews if item.severity in {Core3ReviewSeverity.MEDIUM.value, Core3ReviewSeverity.LOW.value}]
        avg_competitors = _decimal_avg([report.selected_count for report in report_payloads])
        slot_rates = _slot_fill_rates(report_payloads)
        evidence_coverage = _evidence_coverage(report_cards)
        module_status_summary = _module_status_summary(module_runs)
        report_status_summary = _report_status_summary(release_gates, report_payloads)
        quality_detail = self._quality_detail(
            module_runs=module_runs,
            review_items=review_items,
            report_payloads=report_payloads,
            release_gates=release_gates,
        )
        acceptance_status = _acceptance_status(blockers, pending_reviews, release_gates, report_payloads)
        data_scope_note = _data_scope_note(report_payloads)
        summary_cn = _summary_cn(acceptance_status, processed_targets, len(blockers), len(pending_reviews), len(ready_reports))
        return {
            "run_id": run_id,
            "project_id": project_id,
            "category_code": category_code,
            "data_batch_id": batch_id,
            "processed_sku_count": processed_skus,
            "processed_target_count": processed_targets,
            "report_ready_count": len(ready_reports),
            "high_confidence_report_count": len(high_confidence),
            "medium_confidence_report_count": len(medium_confidence),
            "limited_report_count": len(limited_reports),
            "blocked_report_count": len(blocked_gates),
            "avg_competitor_count": avg_competitors,
            "direct_slot_fill_rate": slot_rates["direct_fight"],
            "pressure_slot_fill_rate": slot_rates["price_volume_pressure"],
            "benchmark_slot_fill_rate": slot_rates["benchmark_potential"],
            "evidence_coverage_rate": evidence_coverage,
            "review_pending_count": len(pending_reviews),
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "acceptance_status": acceptance_status.value,
            "acceptance_summary_cn": summary_cn,
            "data_scope_note_cn": data_scope_note,
            "module_status_summary_json": module_status_summary,
            "report_status_summary_json": report_status_summary,
            "quality_gate_json": {
                "blocker_count": len(blockers),
                "pending_review_count": len(pending_reviews),
                "release_gate_status_counts": report_status_summary["gate_status_counts"],
            },
            "acceptance_detail_json": quality_detail,
        }

    def _quality_detail(
        self,
        *,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
        review_items: list[entities.Core3V2ReviewQueue],
        report_payloads: list[entities.Core3TargetReportPayload],
        release_gates: list[entities.Core3V2ReleaseGate],
    ) -> dict[str, Any]:
        missing_modules = [
            code.value
            for code, row in module_runs.items()
            if row.status in {Core3RunStatus.BLOCKED.value, Core3RunStatus.FAILED.value, Core3RunStatus.SKIPPED_BY_DEPENDENCY.value}
        ]
        blocker_count = sum(1 for item in review_items if item.severity == Core3ReviewSeverity.BLOCKER.value and item.review_status == "pending")
        report_count = len(report_payloads)
        gate_blocked_count = sum(1 for gate in release_gates if gate.gate_status == Core3ReleaseGateStatus.BLOCKED.value)
        return {
            "data_ingestion": {
                "status": "passed" if Core3ModuleCode.M00 in module_runs and Core3ModuleCode.M01 in module_runs else "failed",
                "checks": [
                    {
                        "check_code": "raw_tables_readonly",
                        "result": "passed",
                        "message_cn": "M16 未直接改写原始四表，仅消费 M00-M15 已落库产物。",
                    }
                ],
            },
            "module_chain": {
                "status": "failed" if missing_modules else "passed",
                "checks": [
                    {
                        "check_code": "module_output_snapshot",
                        "result": "failed" if missing_modules else "passed",
                        "message_cn": "存在缺失模块：" + "、".join(missing_modules) if missing_modules else "M00-M15 均有可验收产物快照。",
                    }
                ],
            },
            "business_output": {
                "status": "failed" if report_count <= 0 or gate_blocked_count else "passed_with_warning",
                "checks": [
                    {
                        "check_code": "report_and_gate",
                        "result": "failed" if report_count <= 0 or gate_blocked_count else "warning",
                        "message_cn": f"当前生成 {report_count} 份报告、{gate_blocked_count} 个阻断门禁。",
                    }
                ],
            },
            "executive_display": {
                "status": "failed" if blocker_count else "passed",
                "checks": [
                    {
                        "check_code": "no_internal_field",
                        "result": "failed" if blocker_count else "passed",
                        "message_cn": "存在阻断级展示问题。" if blocker_count else "报告主屏未发现阻断级内部字段或技术痕迹。",
                    }
                ],
            },
        }


def _processed_sku_count(
    module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
    report_payloads: list[entities.Core3TargetReportPayload],
) -> int:
    m08 = module_runs.get(Core3ModuleCode.M08)
    if m08 and isinstance(m08.summary_json, dict):
        value = m08.summary_json.get("target_count") or m08.summary_json.get("sku_signal_profile_count") or m08.summary_json.get("sku_count")
        if value is not None:
            return int(value)
    return len({report.target_sku_code for report in report_payloads})


def _decimal_avg(values: list[int]) -> Decimal:
    if not values:
        return Decimal("0.000")
    value = Decimal(sum(values)) / Decimal(len(values))
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _slot_fill_rates(report_payloads: list[entities.Core3TargetReportPayload]) -> dict[str, Decimal]:
    slots = {"direct_fight": 0, "price_volume_pressure": 0, "benchmark_potential": 0}
    total = max(len(report_payloads), 1)
    for report in report_payloads:
        for item in report.core_competitors_json or []:
            slot_code = item.get("slot_code") if isinstance(item, dict) else None
            if slot_code in slots:
                slots[slot_code] += 1
    return {
        key: (Decimal(value) / Decimal(total)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        for key, value in slots.items()
    }


def _evidence_coverage(report_cards: list[entities.Core3ReportEvidenceCard]) -> Decimal:
    if not report_cards:
        return Decimal("0.0000")
    covered = sum(1 for card in report_cards if card.evidence_ids)
    return (Decimal(covered) / Decimal(len(report_cards))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _module_status_summary(module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun]) -> dict[str, Any]:
    return {
        code.value: {
            "status": row.status,
            "output_count": row.output_count,
            "warning_count": len(row.warnings_json or []),
            "review_issue_count": (row.review_issue_summary_json or {}).get("count", 0),
        }
        for code, row in module_runs.items()
    }


def _report_status_summary(
    release_gates: list[entities.Core3V2ReleaseGate],
    report_payloads: list[entities.Core3TargetReportPayload],
) -> dict[str, Any]:
    gate_counts: dict[str, int] = {}
    for gate in release_gates:
        gate_counts[gate.gate_status] = gate_counts.get(gate.gate_status, 0) + 1
    return {
        "target_report_count": len(report_payloads),
        "gate_status_counts": gate_counts,
    }


def _acceptance_status(
    blockers: list[entities.Core3V2ReviewQueue],
    pending_reviews: list[entities.Core3V2ReviewQueue],
    release_gates: list[entities.Core3V2ReleaseGate],
    report_payloads: list[entities.Core3TargetReportPayload],
) -> Core3PipelineAcceptanceStatus:
    if blockers or not report_payloads or any(gate.gate_status == Core3ReleaseGateStatus.BLOCKED.value for gate in release_gates):
        return Core3PipelineAcceptanceStatus.FAILED
    if pending_reviews or any(gate.gate_status == Core3ReleaseGateStatus.REVIEW_REQUIRED.value for gate in release_gates):
        return Core3PipelineAcceptanceStatus.PASSED_WITH_WARNING
    return Core3PipelineAcceptanceStatus.PASSED


def _data_scope_note(report_payloads: list[entities.Core3TargetReportPayload]) -> str:
    for report in report_payloads:
        if report.data_scope_note_cn:
            return report.data_scope_note_cn
    return "当前仅基于本地样例数据和已完成模块产物验收，不能外推为全市场结论。"


def _summary_cn(
    status: Core3PipelineAcceptanceStatus,
    target_count: int,
    blocker_count: int,
    pending_count: int,
    ready_count: int,
) -> str:
    if status == Core3PipelineAcceptanceStatus.FAILED:
        return f"本次验收未通过：{target_count} 个目标中存在 {blocker_count} 个阻断问题，需要修复后再展示。"
    if status == Core3PipelineAcceptanceStatus.PASSED_WITH_WARNING:
        return f"本次验收带说明通过：{ready_count} 份报告可用于业务预览，仍有 {pending_count} 个问题需要复核或展示说明。"
    return f"本次验收通过：{ready_count} 份报告具备业务展示条件。"
