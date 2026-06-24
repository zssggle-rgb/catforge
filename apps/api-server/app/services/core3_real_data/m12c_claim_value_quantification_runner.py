"""M12C claim value quantification runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M12C_MODULE_VERSION,
    CORE3_M12C_RULE_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.m12c_claim_value_quantification_service import (
    ANALYSIS_POPULATION_READY_WITH_COMMENT,
    MARKET_WINDOW_FULL_OBSERVED,
    M12CClaimValueQuantificationService,
    M12CRepository,
    M12CServiceResult,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class M12CClaimValueQuantificationRunner:
    module_code = Core3ModuleCode.M12C

    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        batch_id = str(target.metadata.get("batch_id") or context.batch_id or "")
        if not batch_id:
            return _blocked_result(
                project_id=context.project_id,
                category_code=context.category_code.value,
                batch_id=None,
                run_id=context.run_id,
                message_cn="M12C 缺少 M00 batch_id，无法生成卖点价值量化结果。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            product_category=str(target.metadata.get("product_category") or "TV"),
            analysis_population=str(target.metadata.get("analysis_population") or ANALYSIS_POPULATION_READY_WITH_COMMENT),
            market_window=str(target.metadata.get("market_window") or MARKET_WINDOW_FULL_OBSERVED),
            target_sku_codes=target.target_ids,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M12C_RULE_VERSION),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        product_category: str = "TV",
        analysis_population: str = ANALYSIS_POPULATION_READY_WITH_COMMENT,
        market_window: str = MARKET_WINDOW_FULL_OBSERVED,
        target_sku_codes: Sequence[str] = (),
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M12C_RULE_VERSION,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
        try:
            SourceBatchReader(context).get_consumable_batch(batch_id)
        except ValueError as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
        try:
            service_result = M12CClaimValueQuantificationService(M12CRepository(context)).run_batch(
                batch_id=batch_id,
                product_category=product_category,
                market_window=market_window,
                analysis_population=analysis_population,
                target_sku_codes=target_sku_codes,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
            )
        except Exception as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_message=str(exc),
            )
        summary_json = {
            "project_id": project_id,
            "category_code": category_code,
            "run_id": run_id,
            "module_version": CORE3_M12C_MODULE_VERSION,
            "target_sku_codes": list(target_sku_codes),
            **service_result.summary,
        }
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M12C,
            status=service_result.status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.output_count,
            output_hash=stable_hash(summary_json, version="m12c-claim-value-summary-v1"),
            warnings=service_result.warnings,
            review_issues=_review_issues(service_result),
            downstream_impacts=_downstream_impacts(service_result),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


def _review_issues(result: M12CServiceResult) -> list[Core3ReviewIssueSchema]:
    return [
        Core3ReviewIssueSchema(
            issue_code="m12c_review_issue",
            issue_type="m12c_claim_value_review",
            severity="medium",
            source_module=Core3ModuleCode.M12C,
            object_type="claim_value_quantification",
            object_id=None,
            evidence_refs=[],
            message_cn=warning,
            suggestion_cn="检查 M12C 样本量、可比池和上下游事实层是否完整。",
            review_required=True,
        )
        for warning in result.warnings[:20]
    ]


def _downstream_impacts(result: M12CServiceResult) -> list[dict[str, object]]:
    if result.output_count == 0:
        return []
    return [
        {
            "module_codes": ["catforge_analyst", "xiaoao-home-appliance-market-analysis", "feishu-report"],
            "reason_cn": "M12C 卖点价值量化结果发生变化，可影响竞品、卖点溢价和机会分析回答。",
        }
    ]


def _blocked_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    message_cn: str,
    started_at: datetime,
    finished_at: datetime,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M12C,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        output_count=0,
        warnings=[message_cn],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "blocked_reason_cn": message_cn,
        },
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    started_at: datetime,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M12C,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=[error_message],
        summary_json={
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "error_message": error_message,
        },
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )
