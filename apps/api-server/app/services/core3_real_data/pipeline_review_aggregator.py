"""M16 review queue aggregation."""

from __future__ import annotations

import re
from typing import Any

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS,
    Core3ModuleCode,
    Core3PipelineReviewStatus,
    Core3ReviewSeverity,
    Core3RunStatus,
)
from app.services.core3_real_data.pipeline_dependency_graph import PipelineDependencyGraph


class ReviewAggregator:
    def __init__(self, graph: PipelineDependencyGraph | None = None) -> None:
        self.graph = graph or PipelineDependencyGraph()
        self._forbidden_patterns = tuple(re.compile(pattern, re.IGNORECASE) for pattern in CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS)

    def collect(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
        m15_review_issues: list[entities.Core3ReportReviewIssue],
        report_payloads: list[entities.Core3TargetReportPayload],
        report_cards: list[entities.Core3ReportEvidenceCard],
        guardrail_issues: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        items.extend(
            self._from_m15_issue(
                issue,
                run_id=run_id,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                source_module_run_id=module_runs.get(Core3ModuleCode.M15).module_run_id if module_runs.get(Core3ModuleCode.M15) else None,
            )
            for issue in m15_review_issues
        )
        items.extend(
            self._guardrail_issue(
                issue,
                run_id=run_id,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                source_module_run_id=module_runs.get(Core3ModuleCode.M15).module_run_id if module_runs.get(Core3ModuleCode.M15) else None,
            )
            for issue in guardrail_issues
        )
        items.extend(
            self._dependency_issues(
                run_id=run_id,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                module_runs=module_runs,
            )
        )
        items.extend(
            self._report_payload_guardrails(
                run_id=run_id,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                module_run_id=module_runs.get(Core3ModuleCode.M15).module_run_id if module_runs.get(Core3ModuleCode.M15) else None,
                reports=report_payloads,
            )
        )
        items.extend(
            self._missing_card_issues(
                run_id=run_id,
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                module_run_id=module_runs.get(Core3ModuleCode.M15).module_run_id if module_runs.get(Core3ModuleCode.M15) else None,
                reports=report_payloads,
                cards=report_cards,
            )
        )
        return _dedupe(items)

    def _from_m15_issue(
        self,
        issue: entities.Core3ReportReviewIssue,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        source_module_run_id: str | None,
    ) -> dict[str, Any]:
        severity = _normalize_m15_severity(issue.issue_level)
        return {
            "run_id": run_id,
            "source_module_run_id": source_module_run_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "module_code": Core3ModuleCode.M15.value,
            "target_type": "report",
            "target_id": issue.target_sku_code,
            "target_sku_code": issue.target_sku_code,
            "candidate_sku_code": None,
            "object_type": issue.issue_scope,
            "object_id": issue.report_review_issue_id,
            "issue_type": issue.issue_type,
            "severity": severity,
            "issue_title_cn": "M15 报告复核问题",
            "issue_detail_cn": issue.issue_message_cn,
            "evidence_ids": issue.evidence_ids or [],
            "risk_flags_json": [issue.issue_type],
            "suggested_action_cn": issue.suggested_action_cn or "请复核报告证据、语气和展示边界。",
            "review_status": Core3PipelineReviewStatus.PENDING.value,
            "is_blocking_release": severity == Core3ReviewSeverity.BLOCKER.value,
            "source_issue_table": entities.Core3ReportReviewIssue.__tablename__,
            "source_issue_id": issue.report_review_issue_id,
        }

    def _guardrail_issue(
        self,
        issue: dict[str, Any],
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        source_module_run_id: str | None,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "source_module_run_id": source_module_run_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "module_code": issue["module_code"],
            "target_type": "report",
            "target_id": issue["target_sku_code"],
            "target_sku_code": issue["target_sku_code"],
            "candidate_sku_code": None,
            "object_type": issue["object_type"],
            "object_id": issue["object_id"],
            "issue_type": issue["issue_type"],
            "severity": issue["severity"],
            "issue_title_cn": issue["issue_title_cn"],
            "issue_detail_cn": issue["issue_detail_cn"],
            "evidence_ids": [],
            "risk_flags_json": [issue["issue_type"]],
            "suggested_action_cn": issue["suggested_action_cn"],
            "review_status": Core3PipelineReviewStatus.PENDING.value,
            "is_blocking_release": issue["severity"] == Core3ReviewSeverity.BLOCKER.value,
            "source_issue_table": "m16_guardrail",
            "source_issue_id": issue["object_id"],
        }

    def _dependency_issues(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_runs: dict[Core3ModuleCode, entities.Core3V2ModuleRun],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for module_code in self.graph.topological_order():
            if module_code in {Core3ModuleCode.M00, Core3ModuleCode.M16}:
                continue
            module_run = module_runs.get(module_code)
            if module_run is None or module_run.status in {
                Core3RunStatus.BLOCKED.value,
                Core3RunStatus.FAILED.value,
                Core3RunStatus.SKIPPED_BY_DEPENDENCY.value,
            }:
                items.append(
                    {
                        "run_id": run_id,
                        "source_module_run_id": module_run.module_run_id if module_run else None,
                        "project_id": project_id,
                        "category_code": category_code,
                        "batch_id": batch_id,
                        "module_code": module_code.value,
                        "target_type": "batch",
                        "target_id": batch_id,
                        "target_sku_code": None,
                        "candidate_sku_code": None,
                        "object_type": "module_run",
                        "object_id": module_run.module_run_id if module_run else "",
                        "issue_type": "dependency_hash_missing",
                        "severity": Core3ReviewSeverity.BLOCKER.value,
                        "issue_title_cn": "模块链路产物缺失",
                        "issue_detail_cn": f"{module_code.value} 缺少可验收的上游或输出产物，不能发布依赖它的报告。",
                        "evidence_ids": [],
                        "risk_flags_json": ["missing_module_output"],
                        "suggested_action_cn": "补齐上游模块真实运行结果后重新执行 M16 验收。",
                        "review_status": Core3PipelineReviewStatus.PENDING.value,
                        "is_blocking_release": True,
                        "source_issue_table": "core3_v2_module_run",
                        "source_issue_id": module_run.module_run_id if module_run else "",
                    }
                )
        return items

    def _report_payload_guardrails(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_run_id: str | None,
        reports: list[entities.Core3TargetReportPayload],
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for report in reports:
            text = "\n".join(
                [
                    report.report_title_cn or "",
                    report.executive_conclusion_cn or "",
                    report.target_profile_summary_cn or "",
                    report.data_quality_note_cn or "",
                    report.data_scope_note_cn or "",
                ]
            )
            if any(pattern.search(text) for pattern in self._forbidden_patterns):
                issues.append(
                    self._report_issue(
                        run_id=run_id,
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        module_run_id=module_run_id,
                        report=report,
                        issue_type="internal_field_exposed",
                        severity=Core3ReviewSeverity.BLOCKER.value,
                        title_cn="报告主屏存在内部字段或技术痕迹",
                        detail_cn=f"{report.target_sku_code} 的报告主屏命中内部字段、UUID、SQL 或过程性话术。",
                        action_cn="返回 M15 修正高层展示文案后重新验收。",
                    )
                )
            if "当前样例数据内" not in (report.data_scope_note_cn or ""):
                issues.append(
                    self._report_issue(
                        run_id=run_id,
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        module_run_id=module_run_id,
                        report=report,
                        issue_type="sample_scope_missing",
                        severity=Core3ReviewSeverity.HIGH.value,
                        title_cn="样例数据范围说明不足",
                        detail_cn=f"{report.target_sku_code} 的报告没有清楚说明当前只基于样例数据。",
                        action_cn="报告需明确样例范围、线上渠道和同品牌样例限制。",
                    )
                )
        return issues

    def _missing_card_issues(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_run_id: str | None,
        reports: list[entities.Core3TargetReportPayload],
        cards: list[entities.Core3ReportEvidenceCard],
    ) -> list[dict[str, Any]]:
        card_count_by_target: dict[str, int] = {}
        for card in cards:
            card_count_by_target[card.target_sku_code] = card_count_by_target.get(card.target_sku_code, 0) + 1
        issues: list[dict[str, Any]] = []
        for report in reports:
            if report.selected_count > 0 and card_count_by_target.get(report.target_sku_code, 0) <= 0:
                issues.append(
                    self._report_issue(
                        run_id=run_id,
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        module_run_id=module_run_id,
                        report=report,
                        issue_type="evidence_card_missing",
                        severity=Core3ReviewSeverity.BLOCKER.value,
                        title_cn="核心竞品缺少证据卡",
                        detail_cn=f"{report.target_sku_code} 已有核心竞品选择，但没有对应证据卡。",
                        action_cn="补齐 M15 证据卡后重新验收。",
                    )
                )
        return issues

    def _report_issue(
        self,
        *,
        run_id: str,
        project_id: str,
        category_code: str,
        batch_id: str,
        module_run_id: str | None,
        report: entities.Core3TargetReportPayload,
        issue_type: str,
        severity: str,
        title_cn: str,
        detail_cn: str,
        action_cn: str,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "source_module_run_id": module_run_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "module_code": Core3ModuleCode.M16.value,
            "target_type": "report",
            "target_id": report.target_sku_code,
            "target_sku_code": report.target_sku_code,
            "candidate_sku_code": None,
            "object_type": "report_payload",
            "object_id": report.target_report_payload_id,
            "issue_type": issue_type,
            "severity": severity,
            "issue_title_cn": title_cn,
            "issue_detail_cn": detail_cn,
            "evidence_ids": [],
            "risk_flags_json": [issue_type],
            "suggested_action_cn": action_cn,
            "review_status": Core3PipelineReviewStatus.PENDING.value,
            "is_blocking_release": severity == Core3ReviewSeverity.BLOCKER.value,
            "source_issue_table": entities.Core3TargetReportPayload.__tablename__,
            "source_issue_id": report.target_report_payload_id,
        }


def _normalize_m15_severity(issue_level: str) -> str:
    return {
        "warning": Core3ReviewSeverity.MEDIUM.value,
        "review": Core3ReviewSeverity.HIGH.value,
        "blocker": Core3ReviewSeverity.BLOCKER.value,
        "low": Core3ReviewSeverity.LOW.value,
        "medium": Core3ReviewSeverity.MEDIUM.value,
        "high": Core3ReviewSeverity.HIGH.value,
    }.get(str(issue_level), Core3ReviewSeverity.MEDIUM.value)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for item in items:
        key = (
            item["run_id"],
            item["module_code"],
            item["target_type"],
            item["target_id"],
            item["issue_type"],
            item.get("object_id") or "",
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result
