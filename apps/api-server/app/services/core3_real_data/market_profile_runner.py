"""M07 market profile runner."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3ReviewIssueSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.market_profile_repositories import M07InputBlockedError, M07MarketRepository
from app.services.core3_real_data.market_profile_schemas import M07QualityIssue
from app.services.core3_real_data.market_profile_service import M07ServiceResult, MarketProfileService
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


class MarketProfileRunner:
    module_code = Core3ModuleCode.M07

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
                message_cn="M07 缺少 M00 batch_id，无法生成市场画像。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            batch_id=batch_id,
            category_code=context.category_code.value,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            rule_version=str(target.metadata.get("rule_version") or CORE3_M07_RULE_VERSION),
            price_band_rule_version=str(
                target.metadata.get("price_band_rule_version") or CORE3_M07_PRICE_BAND_RULE_VERSION
            ),
            pool_rule_version=str(target.metadata.get("pool_rule_version") or CORE3_M07_POOL_RULE_VERSION),
            sku_scope=target.target_ids,
            analysis_windows=tuple(target.metadata.get("analysis_windows") or ()),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M07_RULE_VERSION,
        price_band_rule_version: str = CORE3_M07_PRICE_BAND_RULE_VERSION,
        pool_rule_version: str = CORE3_M07_POOL_RULE_VERSION,
        sku_scope: Sequence[str] = (),
        analysis_windows: Sequence[str] = (),
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
            with self.db.begin_nested():
                service_result = MarketProfileService(M07MarketRepository(context)).run_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_scope=sku_scope,
                    analysis_windows=analysis_windows,
                    rule_version=rule_version,
                    price_band_rule_version=price_band_rule_version,
                    pool_rule_version=pool_rule_version,
                )
        except (M07InputBlockedError, ValueError) as exc:
            return _blocked_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                message_cn=str(exc),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
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
            "target_sku_codes": list(sku_scope),
            **service_result.summary,
        }
        output_hash = stable_hash(summary_json, version="m07-market-profile-summary-v1")
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M07,
            status=service_result.status,
            input_count=service_result.input_count,
            changed_input_count=service_result.created_output_count,
            output_count=service_result.output_count,
            output_hash=output_hash,
            warnings=service_result.warnings,
            review_issues=_review_issues(service_result),
            downstream_impacts=_downstream_impacts(service_result),
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


def _review_issues(result: M07ServiceResult) -> list[Core3ReviewIssueSchema]:
    issues: list[M07QualityIssue] = []
    for profile in result.profiles:
        if profile.review_required:
            issues.append(
                M07QualityIssue(
                    issue_code="m07_market_profile_review",
                    sku_code=profile.sku_code,
                    severity="medium",
                    message_cn=f"{profile.model_name or profile.sku_code} 市场画像样本或关键字段不足，需要复核后再高置信使用。",
                    suggestion_cn="补充周销、价格或尺寸数据后重跑 M07。",
                    evidence_ids=profile.evidence_ids,
                    review_required=True,
                )
            )
    for pool in result.pools:
        if pool.review_required:
            issues.append(
                M07QualityIssue(
                    issue_code="m07_comparable_pool_insufficient",
                    sku_code=pool.target_sku_code,
                    severity="medium",
                    message_cn=f"{pool.target_model_name or pool.target_sku_code} 的 {pool.pool_type} 可比池样本不足。",
                    suggestion_cn="补充同尺寸、相邻尺寸或同价位市场数据后重跑 M07。",
                    evidence_ids=pool.evidence_ids,
                    review_required=True,
                )
            )
    return [
        Core3ReviewIssueSchema(
            issue_code=issue.issue_code,
            issue_type="m07_market_profile_quality",
            severity=issue.severity,
            source_module=Core3ModuleCode.M07,
            object_type="market_profile",
            target_sku_code=issue.sku_code,
            evidence_refs=issue.evidence_ids,
            message_cn=issue.message_cn,
            suggestion_cn=issue.suggestion_cn,
            review_required=issue.review_required,
        )
        for issue in issues[:50]
    ]


def _downstream_impacts(result: M07ServiceResult) -> list[dict[str, object]]:
    sku_codes = sorted({profile.sku_code for profile in result.profiles})
    return [
        {
            "sku_code": sku_code,
            "module_codes": ["M08", "M09", "M10", "M11", "M11.5", "M12", "M13", "M14", "M15", "M16"],
            "data_domains": [Core3DataDomain.MARKET.value, Core3DataDomain.PROFILE.value],
            "reason_cn": "M07 市场画像、市场信号或可比池基线发生变化",
        }
        for sku_code in sku_codes
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
        module_code=Core3ModuleCode.M07,
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
        module_code=Core3ModuleCode.M07,
        status=Core3RunStatus.FAILED,
        input_count=0,
        output_count=0,
        warnings=["M07 市场画像与可比池基线生成失败", error_message],
        review_issues=[
            Core3ReviewIssueSchema(
                issue_code="m07_market_profile_failed",
                issue_type="module_failed",
                severity="blocker",
                source_module=Core3ModuleCode.M07,
                object_type="module",
                evidence_refs=[],
                message_cn="M07 市场画像生成失败，请检查 M01/M02/M03 产物和本地 fixture。",
                suggestion_cn="确认清洗周销、market_fact 证据、屏幕尺寸参数后重跑。",
                review_required=True,
            )
        ],
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
