"""M11D semantic market graph and sales allocation.

M11D consumes current M09C/M10C/M11C semantic profiles plus market facts. It
does not call an LLM and does not reuse old M11.6/M11.7 outputs.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Mapping, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import entities
from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.cleaning_repositories import SourceBatchReader
from app.services.core3_real_data.constants import (
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_MODULE_VERSION,
    CORE3_M11D_RULE_VERSION,
    Core3ModuleCode,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3BaseRepository, Core3RepositoryContext
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.runner import Core3ModuleTarget


ANALYSIS_POPULATION_FACT_COMPLETE = "fact_complete_with_comment"
ANALYSIS_POPULATION_ALL_SEMANTIC = "all_semantic_profiles"
SUPPORTED_ANALYSIS_POPULATIONS = (ANALYSIS_POPULATION_FACT_COMPLETE, ANALYSIS_POPULATION_ALL_SEMANTIC)
MARKET_WINDOW_FULL_OBSERVED = "full_observed_window"
SUPPORTED_MARKET_WINDOWS = (MARKET_WINDOW_FULL_OBSERVED, "recent_12w", "custom_week_range")

PRODUCT_CATEGORY_INPUT_RULES = {
    "TV": {
        "comment_rule_version": CORE3_M05C_TV_RULE_VERSION,
        "comment_taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
        "user_task_rule_version": CORE3_M09C_TV_RULE_VERSION,
        "user_task_taxonomy_version": CORE3_M09C_TV_TAXONOMY_VERSION,
        "target_group_rule_version": CORE3_M10C_TV_RULE_VERSION,
        "target_group_taxonomy_version": CORE3_M10C_TV_TAXONOMY_VERSION,
        "battlefield_rule_version": CORE3_M11C_TV_RULE_VERSION,
        "battlefield_taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
        "market_rule_version": CORE3_M07_RULE_VERSION,
    }
}

DIM_USER_TASK = "user_task"
DIM_TARGET_GROUP = "target_group"
DIM_BATTLEFIELD = "battlefield"
DIMENSION_TYPES = (DIM_USER_TASK, DIM_TARGET_GROUP, DIM_BATTLEFIELD)

ROLE_PRIMARY = "primary_value"
ROLE_SECONDARY = "secondary_value"
ROLE_OBSERVED = "observed_need"
ROLE_DRAG = "drag_risk"
ROLE_BRAND = "brand_claim"
ROLE_LATENT = "latent_capability"
ROLE_OPPORTUNITY = "opportunity"
ROLE_EXCLUDED = "excluded"

VALUE_POSITIVE = "positive_value"
VALUE_OBSERVED = "observed_need"
VALUE_DIAGNOSTIC = "diagnostic_only"

RELATION_ROLE_BY_STATUS = {
    "primary_user_task": ROLE_PRIMARY,
    "secondary_user_task": ROLE_SECONDARY,
    "comment_observed_task": ROLE_OBSERVED,
    "drag_factor_task": ROLE_DRAG,
    "brand_claimed_task": ROLE_BRAND,
    "latent_capability_task": ROLE_LATENT,
    "primary_target_group": ROLE_PRIMARY,
    "secondary_target_group": ROLE_SECONDARY,
    "comment_observed_group": ROLE_OBSERVED,
    "unmet_group_need": ROLE_DRAG,
    "brand_claimed_group": ROLE_BRAND,
    "latent_group": ROLE_LATENT,
    "primary_battlefield": ROLE_PRIMARY,
    "secondary_battlefield": ROLE_SECONDARY,
    "user_observed_battlefield": ROLE_OBSERVED,
    "drag_factor_battlefield": ROLE_DRAG,
    "brand_claimed_battlefield": ROLE_BRAND,
    "opportunity_battlefield": ROLE_OPPORTUNITY,
}

RELATION_FACTOR = {
    ROLE_PRIMARY: Decimal("1.0000"),
    ROLE_SECONDARY: Decimal("0.7000"),
    ROLE_OBSERVED: Decimal("0.4500"),
}

ZERO = Decimal("0")
ONE = Decimal("1")
Q4 = Decimal("0.0001")
Q6 = Decimal("0.000001")
Q8 = Decimal("0.00000001")
Q_MONEY = Decimal("0.0001")


@dataclass(frozen=True)
class M11DSemanticInputs:
    user_task_profiles: tuple[entities.Core3M09cSkuUserTaskProfile, ...]
    user_task_scores: tuple[entities.Core3M09cSkuUserTaskScore, ...]
    target_group_profiles: tuple[entities.Core3M10cSkuTargetGroupProfile, ...]
    target_group_scores: tuple[entities.Core3M10cSkuTargetGroupScore, ...]
    battlefield_profiles: tuple[entities.Core3SkuValueBattlefieldProfile, ...]
    battlefield_scores: tuple[entities.Core3SkuValueBattlefieldScore, ...]
    market_profiles: tuple[entities.Core3SkuMarketProfile, ...]
    comment_profiles: tuple[entities.Core3SkuCommentFactProfile, ...]


@dataclass(frozen=True)
class M11DSkuMarket:
    sku_code: str
    brand_name: str | None
    model_name: str | None
    size_tier: str
    price_band_in_size_tier: str
    price_percentile_in_size_tier: Decimal | None
    sales_volume_total: Decimal
    sales_amount_total: Decimal
    avg_weekly_sales_volume: Decimal
    avg_weekly_sales_amount: Decimal
    active_week_count: int
    window_start_week: int | None
    window_end_week: int | None
    confidence: Decimal
    market_source_json: dict[str, Any]
    evidence_ids_json: list[str]


@dataclass(frozen=True)
class M11DRelationCandidate:
    dimension_type: str
    dimension_code: str
    dimension_name: str
    taxonomy_version: str
    sku_code: str
    brand_name: str | None
    model_name: str | None
    size_tier: str
    price_band_in_size_tier: str
    price_percentile_in_size_tier: Decimal | None
    relation_status: str
    allocation_role: str
    source_profile_id: str | None
    source_score_id: str | None
    final_score: Decimal
    user_or_comment_signal: Decimal
    product_support_signal: Decimal
    market_validation_signal: Decimal
    risk_penalty: Decimal
    confidence: Decimal
    evidence_ids_json: list[str]
    score_breakdown_json: dict[str, Any]

    @property
    def allocation_value_type(self) -> str:
        if self.allocation_role in {ROLE_PRIMARY, ROLE_SECONDARY}:
            return VALUE_POSITIVE
        if self.allocation_role == ROLE_OBSERVED:
            return VALUE_OBSERVED
        return VALUE_DIAGNOSTIC

    @property
    def relation_factor(self) -> Decimal:
        return RELATION_FACTOR.get(self.allocation_role, ZERO)

    @property
    def allocation_eligible(self) -> bool:
        if self.allocation_role in {ROLE_PRIMARY, ROLE_SECONDARY}:
            return self.final_score > ZERO and self.confidence >= Decimal("0.2500")
        if self.allocation_role == ROLE_OBSERVED:
            return (
                self.final_score >= Decimal("0.5500")
                and self.confidence >= Decimal("0.5000")
                and self.user_or_comment_signal >= Decimal("0.5000")
            )
        return False

    @property
    def allocation_basis(self) -> Decimal:
        basis = (
            self.final_score * Decimal("0.4500")
            + self.user_or_comment_signal * Decimal("0.2000")
            + self.product_support_signal * Decimal("0.1500")
            + self.market_validation_signal * Decimal("0.1000")
            + self.confidence * Decimal("0.1000")
            - self.risk_penalty
        )
        return _q6(max(basis, ZERO))


@dataclass(frozen=True)
class M11DWritePayload:
    payload: dict[str, Any]

    def to_record_payload(self) -> dict[str, Any]:
        return self.payload


@dataclass(frozen=True)
class M11DWriteResult:
    records: tuple[Any, ...]
    created_count: int
    reused_count: int
    updated_count: int


@dataclass(frozen=True)
class M11DServiceResult:
    input_count: int
    allocation_count: int
    summary_count: int
    contribution_count: int
    graph_snapshot_count: int
    check_count: int
    warnings: list[str]
    write_summary: dict[str, dict[str, int]]
    summary: dict[str, Any]

    @property
    def changed_output_count(self) -> int:
        return sum(item["created_count"] + item["updated_count"] for item in self.write_summary.values())

    @property
    def output_count(self) -> int:
        return self.allocation_count + self.summary_count + self.contribution_count + self.graph_snapshot_count + self.check_count


class M11DSemanticMarketRepository(Core3BaseRepository):
    def load_inputs(
        self,
        batch_id: str,
        *,
        product_category: str,
        market_window: str,
        target_sku_codes: Sequence[str] = (),
    ) -> M11DSemanticInputs:
        sku_scope = tuple(sorted({code for code in target_sku_codes if code}))
        input_rules = PRODUCT_CATEGORY_INPUT_RULES.get(product_category.upper(), {})
        return M11DSemanticInputs(
            user_task_profiles=tuple(
                self._list_current(
                    entities.Core3M09cSkuUserTaskProfile,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("user_task_rule_version"),
                    taxonomy_version=input_rules.get("user_task_taxonomy_version"),
                )
            ),
            user_task_scores=tuple(
                self._list_current(
                    entities.Core3M09cSkuUserTaskScore,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("user_task_rule_version"),
                    taxonomy_version=input_rules.get("user_task_taxonomy_version"),
                )
            ),
            target_group_profiles=tuple(
                self._list_current(
                    entities.Core3M10cSkuTargetGroupProfile,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("target_group_rule_version"),
                    taxonomy_version=input_rules.get("target_group_taxonomy_version"),
                )
            ),
            target_group_scores=tuple(
                self._list_current(
                    entities.Core3M10cSkuTargetGroupScore,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("target_group_rule_version"),
                    taxonomy_version=input_rules.get("target_group_taxonomy_version"),
                )
            ),
            battlefield_profiles=tuple(
                self._list_current(
                    entities.Core3SkuValueBattlefieldProfile,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("battlefield_rule_version"),
                    taxonomy_version=input_rules.get("battlefield_taxonomy_version"),
                )
            ),
            battlefield_scores=tuple(
                self._list_current(
                    entities.Core3SkuValueBattlefieldScore,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("battlefield_rule_version"),
                    taxonomy_version=input_rules.get("battlefield_taxonomy_version"),
                )
            ),
            market_profiles=tuple(self._list_market_profiles(batch_id, market_window=market_window, sku_scope=sku_scope, rule_version=input_rules.get("market_rule_version"))),
            comment_profiles=tuple(
                self._list_current(
                    entities.Core3SkuCommentFactProfile,
                    batch_id,
                    product_category=product_category,
                    sku_scope=sku_scope,
                    rule_version=input_rules.get("comment_rule_version"),
                    taxonomy_version=input_rules.get("comment_taxonomy_version"),
                )
            ),
        )

    def mark_outputs_stale(
        self,
        *,
        batch_id: str,
        analysis_population: str,
        market_window: str,
        rule_version: str,
    ) -> None:
        for model_cls in (
            entities.Core3SemanticMarketAllocation,
            entities.Core3SemanticMarketDimensionSummary,
            entities.Core3SemanticMarketSkuContribution,
            entities.Core3SemanticMarketGraphSnapshot,
            entities.Core3SemanticMarketReconciliationCheck,
        ):
            stmt = (
                update(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
                .where(model_cls.analysis_population == analysis_population)
                .where(model_cls.market_window == market_window)
                .where(model_cls.rule_version == rule_version)
                .where(model_cls.is_current.is_(True))
                .values(is_current=False)
            )
            self.db.execute(stmt)
        self.db.flush()

    def save_allocations(self, records: Sequence[M11DWritePayload]) -> M11DWriteResult:
        return self._save_many(
            entities.Core3SemanticMarketAllocation,
            records,
            unique_fields=(
                "batch_id",
                "analysis_population",
                "market_window",
                "dimension_type",
                "sku_code",
                "dimension_code",
                "rule_version",
                "is_current",
            ),
        )

    def save_summaries(self, records: Sequence[M11DWritePayload]) -> M11DWriteResult:
        return self._save_many(
            entities.Core3SemanticMarketDimensionSummary,
            records,
            unique_fields=(
                "batch_id",
                "analysis_population",
                "market_window",
                "dimension_type",
                "dimension_code",
                "rule_version",
                "is_current",
            ),
        )

    def save_contributions(self, records: Sequence[M11DWritePayload]) -> M11DWriteResult:
        return self._save_many(
            entities.Core3SemanticMarketSkuContribution,
            records,
            unique_fields=(
                "batch_id",
                "analysis_population",
                "market_window",
                "dimension_type",
                "dimension_code",
                "sku_code",
                "rule_version",
                "is_current",
            ),
        )

    def save_graph_snapshots(self, records: Sequence[M11DWritePayload]) -> M11DWriteResult:
        return self._save_many(
            entities.Core3SemanticMarketGraphSnapshot,
            records,
            unique_fields=("batch_id", "analysis_population", "market_window", "rule_version", "is_current"),
            hash_field="graph_hash",
        )

    def save_checks(self, records: Sequence[M11DWritePayload]) -> M11DWriteResult:
        return self._save_many(
            entities.Core3SemanticMarketReconciliationCheck,
            records,
            unique_fields=(
                "batch_id",
                "analysis_population",
                "market_window",
                "check_type",
                "sku_code",
                "dimension_type",
                "dimension_code",
                "input_fingerprint",
            ),
        )

    def _list_current(
        self,
        model_cls: Any,
        batch_id: str,
        *,
        product_category: str,
        sku_scope: Sequence[str],
        rule_version: str | None = None,
        taxonomy_version: str | None = None,
    ) -> list[Any]:
        stmt = self._current_query(model_cls, batch_id)
        if hasattr(model_cls, "product_category"):
            stmt = stmt.where(model_cls.product_category == product_category)
        if rule_version and hasattr(model_cls, "rule_version"):
            stmt = stmt.where(model_cls.rule_version == rule_version)
        if taxonomy_version and hasattr(model_cls, "taxonomy_version"):
            stmt = stmt.where(model_cls.taxonomy_version == taxonomy_version)
        if sku_scope:
            stmt = stmt.where(model_cls.sku_code.in_(tuple(sku_scope)))
        return self._paged_scalars(stmt.order_by(model_cls.sku_code), limit=100000, offset=0)

    def _list_market_profiles(
        self,
        batch_id: str,
        *,
        market_window: str,
        sku_scope: Sequence[str],
        rule_version: str | None = None,
    ) -> list[entities.Core3SkuMarketProfile]:
        stmt = (
            self._current_query(entities.Core3SkuMarketProfile, batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .order_by(entities.Core3SkuMarketProfile.sku_code)
        )
        if rule_version:
            stmt = stmt.where(entities.Core3SkuMarketProfile.rule_version == rule_version)
        if sku_scope:
            stmt = stmt.where(entities.Core3SkuMarketProfile.sku_code.in_(tuple(sku_scope)))
        return self._paged_scalars(stmt, limit=100000, offset=0)

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
            .where(model_cls.is_current.is_(True))
        )

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[M11DWritePayload],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> M11DWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            record, status = self._save_one(model_cls, payload, unique_fields=unique_fields, hash_field=hash_field)
            records.append(record)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                reused_count += 1
        return M11DWriteResult(tuple(records), created_count, reused_count, updated_count)

    def _save_one(self, model_cls: Any, payload: M11DWritePayload, *, unique_fields: tuple[str, ...], hash_field: str) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is None:
            existing = self._find_by_primary_key(model_cls, normalized_payload)
        if existing is None:
            record = model_cls(**_jsonable_payload(normalized_payload))
            self.db.add(record)
            self.db.flush()
            return record, "created"
        if normalized_payload.get(hash_field) == getattr(existing, hash_field):
            _refresh_existing(existing, normalized_payload)
            self.db.flush()
            return existing, "reused"
        _refresh_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: M11DWritePayload) -> dict[str, Any]:
        raw_payload = payload.to_record_payload()
        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        return {key: value for key, value in raw_payload.items() if key in model_fields}

    def _find_by_primary_key(self, model_cls: Any, payload: Mapping[str, Any]) -> Any | None:
        primary_keys = tuple(model_cls.__mapper__.primary_key)
        if not primary_keys:
            return None
        stmt = select(model_cls)
        for column in primary_keys:
            value = payload.get(column.name)
            if value is None:
                return None
            stmt = stmt.where(column == value)
        return self.db.execute(stmt).scalars().first()

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = select(model_cls).where(model_cls.project_id == self.project_id).where(model_cls.category_code == self.category_code.value)
        for field_name in unique_fields:
            value = payload.get(field_name)
            if value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required")
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return self.db.execute(stmt).scalars().first()


class M11DSemanticMarketRunner:
    module_code = Core3ModuleCode.M11D

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
                message_cn="M11D 缺少 M00 batch_id，无法生成语义市场图谱。",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
            )
        return self.run_batch(
            project_id=context.project_id,
            category_code=context.category_code.value,
            batch_id=batch_id,
            run_id=context.run_id,
            module_run_id=target.metadata.get("module_run_id"),
            product_category=str(target.metadata.get("product_category") or "TV"),
            analysis_population=str(target.metadata.get("analysis_population") or ANALYSIS_POPULATION_FACT_COMPLETE),
            market_window=str(target.metadata.get("market_window") or MARKET_WINDOW_FULL_OBSERVED),
            target_sku_codes=target.target_ids,
            dimension_types=target.metadata.get("dimension_types") or (),
            force_rebuild=bool(target.metadata.get("force_rebuild")),
        )

    def run_batch(
        self,
        *,
        project_id: str,
        batch_id: str,
        category_code: str = "TV",
        run_id: str | None = None,
        module_run_id: str | None = None,
        product_category: str = "TV",
        analysis_population: str = ANALYSIS_POPULATION_FACT_COMPLETE,
        market_window: str = MARKET_WINDOW_FULL_OBSERVED,
        target_sku_codes: Sequence[str] = (),
        dimension_types: Sequence[str] = (),
        rule_version: str = CORE3_M11D_RULE_VERSION,
        force_rebuild: bool = False,
    ) -> Core3ModuleRunResultSchema:
        started_at = datetime.now(timezone.utc)
        if analysis_population not in SUPPORTED_ANALYSIS_POPULATIONS:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11d_invalid_population",
                message_cn=f"M11D 不支持 analysis_population={analysis_population}。",
                error_message="invalid analysis_population",
            )
        if market_window not in SUPPORTED_MARKET_WINDOWS:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11d_invalid_market_window",
                message_cn=f"M11D 不支持 market_window={market_window}。",
                error_message="invalid market_window",
            )
        selected_dimension_types = tuple(sorted({item for item in dimension_types if item})) or DIMENSION_TYPES
        invalid_dimensions = [item for item in selected_dimension_types if item not in DIMENSION_TYPES]
        if invalid_dimensions:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11d_invalid_dimension_type",
                message_cn=f"M11D 不支持 dimension_type={','.join(invalid_dimensions)}。",
                error_message="invalid dimension_type",
            )

        repository_context = Core3RepositoryContext(db=self.db, project_id=project_id, category_code=category_code)
        try:
            SourceBatchReader(repository_context).get_consumable_batch(batch_id)
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
                service_result = M11DSemanticMarketService(repository_context).build_batch(
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    analysis_population=analysis_population,
                    market_window=market_window,
                    target_sku_codes=target_sku_codes,
                    dimension_types=selected_dimension_types,
                    rule_version=rule_version,
                    force_rebuild=force_rebuild,
                )
        except ValueError as exc:
            return _failed_result(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                started_at=started_at,
                error_code="m11d_semantic_market_failed",
                message_cn="M11D 语义市场图谱生成失败，请检查 M05C/M09C/M10C/M11C/M07 是否已生成。",
                error_message=str(exc),
            )

        summary_json = {
            "batch_id": batch_id,
            "module_version": CORE3_M11D_MODULE_VERSION,
            "rule_version": rule_version,
            "product_category": product_category,
            "analysis_population": analysis_population,
            "market_window": market_window,
            "target_sku_codes": list(target_sku_codes),
            "dimension_types": list(selected_dimension_types),
            **service_result.summary,
        }
        status = Core3RunStatus.WARNING if service_result.warnings else Core3RunStatus.SUCCESS
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M11D,
            status=status,
            input_count=service_result.input_count,
            changed_input_count=service_result.changed_output_count,
            output_count=service_result.output_count,
            output_hash=stable_hash(summary_json, version="m11d_semantic_market_summary_v1"),
            warnings=service_result.warnings,
            review_issues=[],
            downstream_impacts=[
                {"module_code": "catforge_analyst", "reason": "新版语义市场图谱会影响市场空间、竞品判断和销量切分查询。"},
                {"module_code": "小奥", "reason": "小奥需要消费 M11D 结果回答战场/客群/任务市场图谱问题。"},
            ],
            summary_json=summary_json,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
        )


class M11DSemanticMarketService:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def build_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None,
        module_run_id: str | None,
        product_category: str,
        analysis_population: str,
        market_window: str,
        target_sku_codes: Sequence[str],
        dimension_types: Sequence[str],
        rule_version: str,
        force_rebuild: bool,
    ) -> M11DServiceResult:
        repository = M11DSemanticMarketRepository(self.context)
        inputs = repository.load_inputs(
            batch_id,
            product_category=product_category,
            market_window=market_window,
            target_sku_codes=target_sku_codes,
        )
        sku_markets = _build_sku_market_map(inputs.market_profiles)
        included_skus, population_summary = _resolve_population(
            inputs,
            sku_markets=sku_markets,
            analysis_population=analysis_population,
            target_sku_codes=target_sku_codes,
        )
        selected_dimension_types = tuple(dimension_types)
        candidates = _build_relation_candidates(inputs, included_skus=included_skus, dimension_types=selected_dimension_types)
        allocations, checks = _build_allocations_and_checks(
            candidates,
            sku_markets=sku_markets,
            included_skus=included_skus,
            dimension_types=selected_dimension_types,
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
        )
        summaries, contributions = _build_summaries_and_contributions(
            candidates,
            allocations,
            sku_markets=sku_markets,
            included_skus=included_skus,
            dimension_types=selected_dimension_types,
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
        )
        graph_snapshot = _build_graph_snapshot(
            candidates,
            allocations,
            checks,
            sku_markets=sku_markets,
            included_skus=included_skus,
            project_id=self.context.project_id,
            category_code=self.context.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            population_summary=population_summary,
        )

        if force_rebuild:
            repository.mark_outputs_stale(
                batch_id=batch_id,
                analysis_population=analysis_population,
                market_window=market_window,
                rule_version=rule_version,
            )
        write_results = {
            "semantic_market_allocations": repository.save_allocations(allocations),
            "semantic_market_summaries": repository.save_summaries(summaries),
            "semantic_market_contributions": repository.save_contributions(contributions),
            "semantic_market_graphs": repository.save_graph_snapshots([graph_snapshot] if graph_snapshot else []),
            "semantic_market_checks": repository.save_checks(checks),
        }
        warnings: list[str] = []
        if not included_skus:
            warnings.append("M11D 没有符合 population 和市场事实要求的 SKU，未生成有效图谱。")
        if analysis_population == ANALYSIS_POPULATION_FACT_COMPLETE and population_summary["excluded_reason_counts"].get("missing_comment_profile"):
            warnings.append("部分 SKU 因缺少 M05C 评论事实画像未进入默认语义市场图谱。")
        if any(item.payload["status"] != "passed" and item.payload["severity"] == "blocking" for item in checks):
            warnings.append("M11D 存在阻断级对账问题，请查看 semantic market reconciliation checks。")
        summary = {
            "population_summary": population_summary,
            "dimension_types": list(selected_dimension_types),
            "relation_candidate_count": len(candidates),
            "allocation_count": len(allocations),
            "summary_count": len(summaries),
            "contribution_count": len(contributions),
            "graph_snapshot_count": 1 if graph_snapshot is not None else 0,
            "check_count": len(checks),
            "check_status_counts": dict(sorted(Counter(item.payload["status"] for item in checks).items())),
            "allocation_status": "generated" if allocations else "empty",
        }
        return M11DServiceResult(
            input_count=len(included_skus),
            allocation_count=len(allocations),
            summary_count=len(summaries),
            contribution_count=len(contributions),
            graph_snapshot_count=1 if graph_snapshot is not None else 0,
            check_count=len(checks),
            warnings=warnings,
            write_summary={
                key: {
                    "created_count": value.created_count,
                    "reused_count": value.reused_count,
                    "updated_count": value.updated_count,
                }
                for key, value in write_results.items()
            },
            summary=summary,
        )


def _resolve_population(
    inputs: M11DSemanticInputs,
    *,
    sku_markets: Mapping[str, M11DSkuMarket],
    analysis_population: str,
    target_sku_codes: Sequence[str],
) -> tuple[tuple[str, ...], dict[str, Any]]:
    user_skus = {row.sku_code for row in inputs.user_task_profiles}
    group_skus = {row.sku_code for row in inputs.target_group_profiles}
    battlefield_skus = {row.sku_code for row in inputs.battlefield_profiles}
    market_skus = set(sku_markets)
    comment_skus = {row.sku_code for row in inputs.comment_profiles}
    semantic_skus = user_skus & group_skus & battlefield_skus
    if analysis_population == ANALYSIS_POPULATION_FACT_COMPLETE:
        included = semantic_skus & market_skus & comment_skus
    else:
        included = semantic_skus & market_skus
    if target_sku_codes:
        included &= set(target_sku_codes)

    candidate_skus = set().union(user_skus, group_skus, battlefield_skus, market_skus, comment_skus)
    if target_sku_codes:
        candidate_skus |= set(target_sku_codes)
    excluded_reason_counts: Counter[str] = Counter()
    for sku_code in candidate_skus:
        if target_sku_codes and sku_code not in set(target_sku_codes):
            continue
        if sku_code in included:
            continue
        if sku_code not in user_skus:
            excluded_reason_counts["missing_user_task_profile"] += 1
        if sku_code not in group_skus:
            excluded_reason_counts["missing_target_group_profile"] += 1
        if sku_code not in battlefield_skus:
            excluded_reason_counts["missing_battlefield_profile"] += 1
        if sku_code not in market_skus:
            excluded_reason_counts["missing_market_profile"] += 1
        if analysis_population == ANALYSIS_POPULATION_FACT_COMPLETE and sku_code not in comment_skus:
            excluded_reason_counts["missing_comment_profile"] += 1
    return tuple(sorted(included)), {
        "analysis_population": analysis_population,
        "candidate_sku_count": len(candidate_skus),
        "included_sku_count": len(included),
        "excluded_sku_count": max(len(candidate_skus) - len(included), 0),
        "excluded_reason_counts": dict(sorted(excluded_reason_counts.items())),
        "input_counts": {
            "user_task_profiles": len(inputs.user_task_profiles),
            "target_group_profiles": len(inputs.target_group_profiles),
            "battlefield_profiles": len(inputs.battlefield_profiles),
            "market_profiles": len(inputs.market_profiles),
            "comment_profiles": len(inputs.comment_profiles),
        },
    }


def _build_sku_market_map(market_profiles: Sequence[entities.Core3SkuMarketProfile]) -> dict[str, M11DSkuMarket]:
    result: dict[str, M11DSkuMarket] = {}
    for row in market_profiles:
        sales_volume = _decimal(row.sales_volume_total)
        sales_amount = _decimal(row.sales_amount_total)
        active_weeks = int(row.active_week_count or 0)
        if sales_volume is None or sales_amount is None or active_weeks <= 0:
            continue
        avg_volume = sales_volume / Decimal(active_weeks)
        avg_amount = sales_amount / Decimal(active_weeks)
        result[row.sku_code] = M11DSkuMarket(
            sku_code=row.sku_code,
            brand_name=row.brand_name or row.brand,
            model_name=row.model_name,
            size_tier=_normalize_size_tier(row.market_pool_key, row.size_segment, row.screen_size_class, row.screen_size_inch),
            price_band_in_size_tier=str(row.price_band_size or row.price_band_category or "unknown"),
            price_percentile_in_size_tier=_decimal(row.price_percentile_in_size),
            sales_volume_total=_q4(sales_volume),
            sales_amount_total=_q4(sales_amount),
            avg_weekly_sales_volume=_q6(avg_volume),
            avg_weekly_sales_amount=_q6(avg_amount),
            active_week_count=active_weeks,
            window_start_week=row.period_start_week_index,
            window_end_week=row.period_end_week_index,
            confidence=_q4(_decimal(row.market_confidence) or Decimal(str(row.confidence or 0)) or ZERO),
            market_source_json={
                "source": "M07",
                "analysis_window": row.analysis_window,
                "market_profile_id": row.profile_id,
                "sku_market_profile_id": row.sku_market_profile_id,
                "rule_version": row.rule_version,
                "price_band_rule_version": row.price_band_rule_version,
                "active_week_count": active_weeks,
            },
            evidence_ids_json=_string_list(row.evidence_ids or row.market_evidence_ids or []),
        )
    return result


def _build_relation_candidates(
    inputs: M11DSemanticInputs,
    *,
    included_skus: Sequence[str],
    dimension_types: Sequence[str],
) -> list[M11DRelationCandidate]:
    included = set(included_skus)
    selected = set(dimension_types)
    candidates: list[M11DRelationCandidate] = []
    if DIM_USER_TASK in selected:
        user_profiles_by_sku = {row.sku_code: row for row in inputs.user_task_profiles if row.sku_code in included}
        for row in inputs.user_task_scores:
            if row.sku_code in included:
                candidate = _candidate_from_user_task(row, user_profiles_by_sku.get(row.sku_code))
                if candidate is not None:
                    candidates.append(candidate)
    if DIM_TARGET_GROUP in selected:
        group_profiles_by_sku = {row.sku_code: row for row in inputs.target_group_profiles if row.sku_code in included}
        for row in inputs.target_group_scores:
            if row.sku_code in included:
                candidate = _candidate_from_target_group(row, group_profiles_by_sku.get(row.sku_code))
                if candidate is not None:
                    candidates.append(candidate)
    if DIM_BATTLEFIELD in selected:
        battlefield_profiles_by_sku = {row.sku_code: row for row in inputs.battlefield_profiles if row.sku_code in included}
        for row in inputs.battlefield_scores:
            if row.sku_code in included:
                candidate = _candidate_from_battlefield(row, battlefield_profiles_by_sku.get(row.sku_code))
                if candidate is not None:
                    candidates.append(candidate)
    return candidates


def _candidate_from_user_task(
    row: entities.Core3M09cSkuUserTaskScore,
    profile: entities.Core3M09cSkuUserTaskProfile | None,
) -> M11DRelationCandidate | None:
    role = RELATION_ROLE_BY_STATUS.get(row.relation_status, ROLE_EXCLUDED)
    if role == ROLE_EXCLUDED:
        return None
    return M11DRelationCandidate(
        dimension_type=DIM_USER_TASK,
        dimension_code=row.user_task_code,
        dimension_name=row.user_task_name,
        taxonomy_version=row.taxonomy_version,
        sku_code=row.sku_code,
        brand_name=row.brand_name,
        model_name=row.model_name,
        size_tier=row.size_tier,
        price_band_in_size_tier=row.price_band_in_size_tier,
        price_percentile_in_size_tier=_decimal(row.price_percentile_in_size_tier),
        relation_status=row.relation_status,
        allocation_role=role,
        source_profile_id=profile.profile_id if profile else None,
        source_score_id=row.score_id,
        final_score=_q4(_decimal(row.user_task_score) or ZERO),
        user_or_comment_signal=_q4(_decimal(row.comment_task_need_score) or ZERO),
        product_support_signal=_q4(max(_decimal(row.claim_task_alignment_score) or ZERO, _decimal(row.param_capability_score) or ZERO)),
        market_validation_signal=_q4(_decimal(row.market_validation_score) or ZERO),
        risk_penalty=_q4((_decimal(row.negative_drag_score) or ZERO) * Decimal("0.2000")),
        confidence=_q4(_decimal(row.confidence) or ZERO),
        evidence_ids_json=_string_list(row.evidence_ids_json or []),
        score_breakdown_json=row.score_breakdown_json or {},
    )


def _candidate_from_target_group(
    row: entities.Core3M10cSkuTargetGroupScore,
    profile: entities.Core3M10cSkuTargetGroupProfile | None,
) -> M11DRelationCandidate | None:
    role = RELATION_ROLE_BY_STATUS.get(row.relation_status, ROLE_EXCLUDED)
    if role == ROLE_EXCLUDED:
        return None
    product_support = max(
        _decimal(row.task_support_score) or ZERO,
        _decimal(row.claim_alignment_score) or ZERO,
        _decimal(row.param_capability_score) or ZERO,
    )
    return M11DRelationCandidate(
        dimension_type=DIM_TARGET_GROUP,
        dimension_code=row.target_group_code,
        dimension_name=row.target_group_name,
        taxonomy_version=row.taxonomy_version,
        sku_code=row.sku_code,
        brand_name=row.brand_name,
        model_name=row.model_name,
        size_tier=row.size_tier,
        price_band_in_size_tier=row.price_band_in_size_tier,
        price_percentile_in_size_tier=_decimal(row.price_percentile_in_size_tier),
        relation_status=row.relation_status,
        allocation_role=role,
        source_profile_id=profile.profile_id if profile else None,
        source_score_id=row.score_id,
        final_score=_q4(_decimal(row.target_group_score) or ZERO),
        user_or_comment_signal=_q4(_decimal(row.comment_audience_motivation_score) or ZERO),
        product_support_signal=_q4(product_support),
        market_validation_signal=_q4(_decimal(row.market_validation_score) or ZERO),
        risk_penalty=ZERO,
        confidence=_q4(_decimal(row.confidence) or ZERO),
        evidence_ids_json=_string_list(row.evidence_ids_json or []),
        score_breakdown_json=row.score_breakdown_json or {},
    )


def _candidate_from_battlefield(
    row: entities.Core3SkuValueBattlefieldScore,
    profile: entities.Core3SkuValueBattlefieldProfile | None,
) -> M11DRelationCandidate | None:
    role = RELATION_ROLE_BY_STATUS.get(row.relation_status, ROLE_EXCLUDED)
    if role == ROLE_EXCLUDED:
        return None
    product_support = max(
        _decimal(row.task_group_fit_score) or ZERO,
        _decimal(row.claim_alignment_score) or ZERO,
        _decimal(row.param_capability_score) or ZERO,
    )
    risk_penalty = Decimal("0.2000") if row.value_effect in {"drag_factor", "unmet_need"} else ZERO
    return M11DRelationCandidate(
        dimension_type=DIM_BATTLEFIELD,
        dimension_code=row.battlefield_code,
        dimension_name=row.battlefield_name,
        taxonomy_version=row.taxonomy_version,
        sku_code=row.sku_code,
        brand_name=row.brand_name,
        model_name=row.model_name,
        size_tier=row.size_tier,
        price_band_in_size_tier=row.price_band_in_size_tier,
        price_percentile_in_size_tier=_decimal(row.price_percentile_in_size_tier),
        relation_status=row.relation_status,
        allocation_role=role,
        source_profile_id=profile.profile_id if profile else None,
        source_score_id=row.score_id,
        final_score=_q4(_decimal(row.battlefield_score) or ZERO),
        user_or_comment_signal=_q4(_decimal(row.user_voice_score) or ZERO),
        product_support_signal=_q4(product_support),
        market_validation_signal=_q4(_decimal(row.market_validation_score) or ZERO),
        risk_penalty=_q4(risk_penalty),
        confidence=_q4(_decimal(row.confidence) or ZERO),
        evidence_ids_json=_string_list(row.evidence_ids_json or []),
        score_breakdown_json={**(row.score_breakdown_json or {}), "value_effect": row.value_effect, "market_gate_status": row.market_gate_status},
    )


def _build_allocations_and_checks(
    candidates: Sequence[M11DRelationCandidate],
    *,
    sku_markets: Mapping[str, M11DSkuMarket],
    included_skus: Sequence[str],
    dimension_types: Sequence[str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
) -> tuple[list[M11DWritePayload], list[M11DWritePayload]]:
    candidates_by_sku_type: dict[tuple[str, str], list[M11DRelationCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.allocation_eligible and candidate.sku_code in sku_markets:
            candidates_by_sku_type[(candidate.sku_code, candidate.dimension_type)].append(candidate)

    allocations: list[M11DWritePayload] = []
    checks: list[M11DWritePayload] = []
    allocations_by_sku_type: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for sku_code in included_skus:
        market = sku_markets.get(sku_code)
        if market is None:
            continue
        for dimension_type in dimension_types:
            sku_candidates = candidates_by_sku_type.get((sku_code, dimension_type), [])
            weighted = [
                (candidate, candidate.allocation_basis * candidate.relation_factor)
                for candidate in sku_candidates
                if candidate.allocation_basis > ZERO and candidate.relation_factor > ZERO
            ]
            total_raw = sum((raw for _, raw in weighted), ZERO)
            if total_raw <= ZERO:
                checks.append(
                    _check_payload(
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        product_category=product_category,
                        analysis_population=analysis_population,
                        market_window=market_window,
                        rule_version=rule_version,
                        check_type="no_allocation_eligible_dimension",
                        sku_code=sku_code,
                        dimension_type=dimension_type,
                        dimension_code="",
                        expected=market.sales_volume_total,
                        actual=ZERO,
                        tolerance=ZERO,
                        status="diagnostic",
                        severity="info",
                        failure_reason_code="no_allocation_eligible_dimension",
                        failure_reason_cn="该 SKU 在该维度类型没有足够证据进入销量解释分配。",
                        payload={"sales_volume_total": str(market.sales_volume_total), "dimension_type": dimension_type},
                    )
                )
                continue
            weight_sum = ZERO
            volume_sum = ZERO
            amount_sum = ZERO
            for index, (candidate, raw_weight) in enumerate(weighted):
                weight = _q6(raw_weight / total_raw)
                if index == len(weighted) - 1:
                    weight = _q6(ONE - weight_sum)
                weight_sum += weight
                allocated_volume = _q4(market.sales_volume_total * weight)
                allocated_amount = _q4(market.sales_amount_total * weight)
                allocated_avg_volume = _q6(market.avg_weekly_sales_volume * weight)
                allocated_avg_amount = _q6(market.avg_weekly_sales_amount * weight)
                volume_sum += allocated_volume
                amount_sum += allocated_amount
                allocation_confidence = _allocation_confidence(candidate, market)
                allocation_id = _record_id(
                    "m11d_allocation",
                    batch_id,
                    analysis_population,
                    market_window,
                    dimension_type,
                    sku_code,
                    candidate.dimension_code,
                    rule_version,
                )
                payload = {
                    "allocation_id": allocation_id,
                    "project_id": project_id,
                    "category_code": category_code,
                    "batch_id": batch_id,
                    "run_id": run_id,
                    "module_run_id": module_run_id,
                    "product_category": product_category,
                    "analysis_population": analysis_population,
                    "market_window": market_window,
                    "window_start_week": market.window_start_week,
                    "window_end_week": market.window_end_week,
                    "active_week_count": market.active_week_count,
                    "dimension_type": dimension_type,
                    "dimension_code": candidate.dimension_code,
                    "dimension_name": candidate.dimension_name,
                    "sku_code": sku_code,
                    "brand_name": candidate.brand_name or market.brand_name,
                    "model_name": candidate.model_name or market.model_name,
                    "size_tier": candidate.size_tier or market.size_tier,
                    "price_band_in_size_tier": candidate.price_band_in_size_tier or market.price_band_in_size_tier,
                    "price_percentile_in_size_tier": candidate.price_percentile_in_size_tier or market.price_percentile_in_size_tier,
                    "relation_status": candidate.relation_status,
                    "allocation_role": candidate.allocation_role,
                    "allocation_value_type": candidate.allocation_value_type,
                    "source_profile_id": candidate.source_profile_id,
                    "source_score_id": candidate.source_score_id,
                    "final_score": candidate.final_score,
                    "allocation_basis": candidate.allocation_basis,
                    "relation_factor": candidate.relation_factor,
                    "allocation_weight": weight,
                    "sales_volume_total": market.sales_volume_total,
                    "sales_amount_total": market.sales_amount_total,
                    "avg_weekly_sales_volume": market.avg_weekly_sales_volume,
                    "avg_weekly_sales_amount": market.avg_weekly_sales_amount,
                    "allocated_sales_volume": allocated_volume,
                    "allocated_sales_amount": allocated_amount,
                    "allocated_avg_weekly_sales_volume": allocated_avg_volume,
                    "allocated_avg_weekly_sales_amount": allocated_avg_amount,
                    "allocation_confidence": allocation_confidence,
                    "allocation_basis_json": {
                        "final_score": str(candidate.final_score),
                        "user_or_comment_signal": str(candidate.user_or_comment_signal),
                        "product_support_signal": str(candidate.product_support_signal),
                        "market_validation_signal": str(candidate.market_validation_signal),
                        "confidence": str(candidate.confidence),
                        "risk_penalty": str(candidate.risk_penalty),
                        "raw_weight": str(_q6(raw_weight)),
                        "formula": "final*0.45 + user/comment*0.20 + support*0.15 + market*0.10 + confidence*0.10 - risk",
                    },
                    "evidence_ids_json": _unique_strings([*candidate.evidence_ids_json, *market.evidence_ids_json]),
                    "market_source_json": market.market_source_json,
                    "rule_version": rule_version,
                    "input_fingerprint": stable_hash(
                        {
                            "sku_code": sku_code,
                            "dimension_type": dimension_type,
                            "dimension_code": candidate.dimension_code,
                            "score_id": candidate.source_score_id,
                            "market": market.market_source_json,
                        },
                        version="m11d-allocation-input-v1",
                    ),
                    "result_hash": stable_hash(
                        {
                            "weight": str(weight),
                            "volume": str(allocated_volume),
                            "amount": str(allocated_amount),
                            "confidence": str(allocation_confidence),
                        },
                        version="m11d-allocation-result-v1",
                    ),
                    "is_current": True,
                }
                allocations.append(M11DWritePayload(payload))
                allocations_by_sku_type[(sku_code, dimension_type)].append(payload)
            checks.extend(
                _allocation_closure_checks(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    product_category=product_category,
                    analysis_population=analysis_population,
                    market_window=market_window,
                    rule_version=rule_version,
                    sku_code=sku_code,
                    dimension_type=dimension_type,
                    market=market,
                    weight_sum=weight_sum,
                    volume_sum=volume_sum,
                    amount_sum=amount_sum,
                )
            )
    checks.extend(
        _dimension_total_checks(
            allocations_by_sku_type,
            sku_markets=sku_markets,
            included_skus=included_skus,
            dimension_types=dimension_types,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
        )
    )
    return allocations, checks


def _build_summaries_and_contributions(
    candidates: Sequence[M11DRelationCandidate],
    allocations: Sequence[M11DWritePayload],
    *,
    sku_markets: Mapping[str, M11DSkuMarket],
    included_skus: Sequence[str],
    dimension_types: Sequence[str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
) -> tuple[list[M11DWritePayload], list[M11DWritePayload]]:
    candidates_by_dimension: dict[tuple[str, str], list[M11DRelationCandidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_dimension[(candidate.dimension_type, candidate.dimension_code)].append(candidate)
    allocations_by_dimension: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for allocation in allocations:
        payload = allocation.payload
        allocations_by_dimension[(payload["dimension_type"], payload["dimension_code"])].append(payload)

    total_market_volume = sum((sku_markets[sku].sales_volume_total for sku in included_skus if sku in sku_markets), ZERO)
    total_market_amount = sum((sku_markets[sku].sales_amount_total for sku in included_skus if sku in sku_markets), ZERO)
    allocated_skus_by_type: dict[str, set[str]] = defaultdict(set)
    for allocation in allocations:
        allocated_skus_by_type[allocation.payload["dimension_type"]].add(allocation.payload["sku_code"])

    summaries: list[M11DWritePayload] = []
    contributions: list[M11DWritePayload] = []
    dimension_keys = sorted(set(candidates_by_dimension) | set(allocations_by_dimension))
    for dimension_type, dimension_code in dimension_keys:
        if dimension_type not in set(dimension_types):
            continue
        dimension_candidates = candidates_by_dimension.get((dimension_type, dimension_code), [])
        dimension_allocations = allocations_by_dimension.get((dimension_type, dimension_code), [])
        if not dimension_candidates and not dimension_allocations:
            continue
        dimension_name = (dimension_allocations[0]["dimension_name"] if dimension_allocations else dimension_candidates[0].dimension_name)
        taxonomy_version = dimension_candidates[0].taxonomy_version if dimension_candidates else "unknown"
        relation_skus = {item.sku_code for item in dimension_candidates}
        allocated_skus = {item["sku_code"] for item in dimension_allocations}
        role_skus: dict[str, set[str]] = defaultdict(set)
        status_counts: Counter[str] = Counter()
        brand_counts: Counter[str] = Counter()
        size_price_counts: Counter[str] = Counter()
        drag_market_volume = ZERO
        drag_market_amount = ZERO
        for candidate in dimension_candidates:
            role_skus[candidate.allocation_role].add(candidate.sku_code)
            status_counts[candidate.relation_status] += 1
            brand_counts[candidate.brand_name or "unknown"] += 1
            size_price_counts[f"{candidate.size_tier}:{candidate.price_band_in_size_tier}"] += 1
            if candidate.allocation_role == ROLE_DRAG and candidate.sku_code in sku_markets:
                drag_market_volume += sku_markets[candidate.sku_code].sales_volume_total
                drag_market_amount += sku_markets[candidate.sku_code].sales_amount_total

        positive_allocations = [item for item in dimension_allocations if item["allocation_value_type"] == VALUE_POSITIVE]
        observed_allocations = [item for item in dimension_allocations if item["allocation_value_type"] == VALUE_OBSERVED]
        estimated_volume = sum((_decimal(item["allocated_sales_volume"]) or ZERO for item in positive_allocations), ZERO)
        estimated_amount = sum((_decimal(item["allocated_sales_amount"]) or ZERO for item in positive_allocations), ZERO)
        estimated_avg_volume = sum((_decimal(item["allocated_avg_weekly_sales_volume"]) or ZERO for item in positive_allocations), ZERO)
        estimated_avg_amount = sum((_decimal(item["allocated_avg_weekly_sales_amount"]) or ZERO for item in positive_allocations), ZERO)
        observed_volume = sum((_decimal(item["allocated_sales_volume"]) or ZERO for item in observed_allocations), ZERO)
        observed_amount = sum((_decimal(item["allocated_sales_amount"]) or ZERO for item in observed_allocations), ZERO)
        allocated_market_volume = sum((sku_markets[sku].sales_volume_total for sku in allocated_skus_by_type[dimension_type] if sku in sku_markets), ZERO)
        allocated_market_amount = sum((sku_markets[sku].sales_amount_total for sku in allocated_skus_by_type[dimension_type] if sku in sku_markets), ZERO)
        unallocated_market_volume = max(total_market_volume - allocated_market_volume, ZERO)
        unallocated_market_amount = max(total_market_amount - allocated_market_amount, ZERO)
        confidence_values = [_decimal(item["allocation_confidence"]) or ZERO for item in dimension_allocations]
        confidence_avg = _q4(sum(confidence_values, ZERO) / Decimal(len(confidence_values))) if confidence_values else ZERO
        top_allocations = sorted(dimension_allocations, key=lambda item: (_decimal(item["allocated_sales_volume"]) or ZERO), reverse=True)
        top_skus = [
            {
                "sku_code": item["sku_code"],
                "brand_name": item.get("brand_name"),
                "model_name": item.get("model_name"),
                "allocation_weight": _float(item["allocation_weight"]),
                "allocated_sales_volume": _float(item["allocated_sales_volume"]),
                "allocated_sales_amount": _float(item["allocated_sales_amount"]),
                "relation_status": item["relation_status"],
                "allocation_role": item["allocation_role"],
            }
            for item in top_allocations[:20]
        ]
        summary_id = _record_id("m11d_summary", batch_id, analysis_population, market_window, dimension_type, dimension_code, rule_version)
        summary_payload = {
            "summary_id": summary_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "analysis_population": analysis_population,
            "market_window": market_window,
            "dimension_type": dimension_type,
            "dimension_code": dimension_code,
            "dimension_name": dimension_name,
            "taxonomy_version": taxonomy_version,
            "sku_relation_count": len(relation_skus),
            "allocated_sku_count": len(allocated_skus),
            "primary_sku_count": len(role_skus[ROLE_PRIMARY]),
            "secondary_sku_count": len(role_skus[ROLE_SECONDARY]),
            "observed_need_sku_count": len(role_skus[ROLE_OBSERVED]),
            "brand_claim_sku_count": len(role_skus[ROLE_BRAND]),
            "opportunity_sku_count": len(role_skus[ROLE_OPPORTUNITY]),
            "drag_risk_sku_count": len(role_skus[ROLE_DRAG]),
            "estimated_sales_volume": _q4(estimated_volume),
            "estimated_sales_amount": _q4(estimated_amount),
            "estimated_avg_weekly_sales_volume": _q6(estimated_avg_volume),
            "estimated_avg_weekly_sales_amount": _q6(estimated_avg_amount),
            "observed_need_sales_volume": _q4(observed_volume),
            "observed_need_sales_amount": _q4(observed_amount),
            "drag_risk_market_volume": _q4(drag_market_volume),
            "drag_risk_market_amount": _q4(drag_market_amount),
            "total_market_sales_volume": _q4(total_market_volume),
            "total_market_sales_amount": _q4(total_market_amount),
            "allocated_market_sales_volume": _q4(allocated_market_volume),
            "allocated_market_sales_amount": _q4(allocated_market_amount),
            "unallocated_market_sales_volume": _q4(unallocated_market_volume),
            "unallocated_market_sales_amount": _q4(unallocated_market_amount),
            "sales_volume_share": _safe_share(estimated_volume + observed_volume, allocated_market_volume),
            "sales_amount_share": _safe_share(estimated_amount + observed_amount, allocated_market_amount),
            "allocation_coverage_rate": _safe_share(allocated_market_volume, total_market_volume),
            "brand_distribution_json": dict(sorted(brand_counts.items())),
            "size_price_distribution_json": dict(sorted(size_price_counts.items())),
            "relation_status_counts_json": dict(sorted(status_counts.items())),
            "top_skus_json": top_skus,
            "confidence_avg": confidence_avg,
            "business_summary_cn": _summary_text(dimension_name, dimension_type, len(relation_skus), len(allocated_skus), estimated_volume + observed_volume),
            "rule_version": rule_version,
            "input_fingerprint": stable_hash(
                {
                    "dimension_type": dimension_type,
                    "dimension_code": dimension_code,
                    "candidates": [item.source_score_id for item in dimension_candidates],
                    "allocations": [item["allocation_id"] for item in dimension_allocations],
                },
                version="m11d-summary-input-v1",
            ),
            "result_hash": stable_hash(
                {
                    "summary": {
                        "volume": str(estimated_volume),
                        "amount": str(estimated_amount),
                        "observed_volume": str(observed_volume),
                        "sku_count": len(relation_skus),
                        "allocated_count": len(allocated_skus),
                    }
                },
                version="m11d-summary-result-v1",
            ),
            "is_current": True,
        }
        summaries.append(M11DWritePayload(summary_payload))
        total_dimension_volume = estimated_volume + observed_volume
        total_dimension_amount = estimated_amount + observed_amount
        for rank, item in enumerate(top_allocations, start=1):
            allocated_volume = _decimal(item["allocated_sales_volume"]) or ZERO
            allocated_amount = _decimal(item["allocated_sales_amount"]) or ZERO
            contribution_id = _record_id("m11d_contribution", batch_id, analysis_population, market_window, dimension_type, dimension_code, item["sku_code"], rule_version)
            contribution_payload = {
                "contribution_id": contribution_id,
                "summary_id": summary_id,
                "allocation_id": item["allocation_id"],
                "project_id": project_id,
                "category_code": category_code,
                "batch_id": batch_id,
                "run_id": run_id,
                "module_run_id": module_run_id,
                "product_category": product_category,
                "analysis_population": analysis_population,
                "market_window": market_window,
                "dimension_type": dimension_type,
                "dimension_code": dimension_code,
                "dimension_name": dimension_name,
                "sku_code": item["sku_code"],
                "brand_name": item.get("brand_name"),
                "model_name": item.get("model_name"),
                "allocation_weight": item["allocation_weight"],
                "allocated_sales_volume": allocated_volume,
                "allocated_sales_amount": allocated_amount,
                "allocated_avg_weekly_sales_volume": item["allocated_avg_weekly_sales_volume"],
                "allocated_avg_weekly_sales_amount": item["allocated_avg_weekly_sales_amount"],
                "sku_share_in_dimension_volume": _safe_share(allocated_volume, total_dimension_volume),
                "sku_share_in_dimension_amount": _safe_share(allocated_amount, total_dimension_amount),
                "sku_rank_in_dimension": rank,
                "is_primary_dimension": item["allocation_role"] == ROLE_PRIMARY,
                "allocation_role": item["allocation_role"],
                "relation_status": item["relation_status"],
                "allocation_confidence": item["allocation_confidence"],
                "contribution_reason_cn": f"{item.get('brand_name') or ''} {item.get('model_name') or item['sku_code']} 以 {item['relation_status']} 关系贡献该维度估算销量。",
                "evidence_ids_json": item["evidence_ids_json"],
                "rule_version": rule_version,
                "input_fingerprint": stable_hash(
                    {"allocation_id": item["allocation_id"], "summary_id": summary_id},
                    version="m11d-contribution-input-v1",
                ),
                "result_hash": stable_hash(
                    {"rank": rank, "volume": str(allocated_volume), "amount": str(allocated_amount)},
                    version="m11d-contribution-result-v1",
                ),
                "is_current": True,
            }
            contributions.append(M11DWritePayload(contribution_payload))
    return summaries, contributions


def _build_graph_snapshot(
    candidates: Sequence[M11DRelationCandidate],
    allocations: Sequence[M11DWritePayload],
    checks: Sequence[M11DWritePayload],
    *,
    sku_markets: Mapping[str, M11DSkuMarket],
    included_skus: Sequence[str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
    population_summary: Mapping[str, Any],
) -> M11DWritePayload | None:
    allocation_by_key = {
        (item.payload["sku_code"], item.payload["dimension_type"], item.payload["dimension_code"]): item.payload
        for item in allocations
    }
    sku_nodes = [
        {
            "node_type": "sku",
            "sku_code": sku,
            "brand_name": sku_markets[sku].brand_name,
            "model_name": sku_markets[sku].model_name,
            "size_tier": sku_markets[sku].size_tier,
            "price_band_in_size_tier": sku_markets[sku].price_band_in_size_tier,
            "sales_volume_total": _float(sku_markets[sku].sales_volume_total),
            "avg_weekly_sales_volume": _float(sku_markets[sku].avg_weekly_sales_volume),
        }
        for sku in included_skus
        if sku in sku_markets
    ]
    dimension_nodes_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for candidate in candidates:
        dimension_key = (candidate.dimension_type, candidate.dimension_code)
        dimension_nodes_by_key.setdefault(
            dimension_key,
            {
                "node_type": "dimension",
                "dimension_type": candidate.dimension_type,
                "dimension_code": candidate.dimension_code,
                "dimension_name": candidate.dimension_name,
                "taxonomy_version": candidate.taxonomy_version,
            },
        )
        allocation = allocation_by_key.get((candidate.sku_code, candidate.dimension_type, candidate.dimension_code))
        edges.append(
            {
                "sku_code": candidate.sku_code,
                "dimension_type": candidate.dimension_type,
                "dimension_code": candidate.dimension_code,
                "dimension_name": candidate.dimension_name,
                "relation_status": candidate.relation_status,
                "allocation_role": candidate.allocation_role,
                "score": _float(candidate.final_score),
                "allocation_weight": _float(allocation["allocation_weight"]) if allocation else 0.0,
                "allocated_sales_volume": _float(allocation["allocated_sales_volume"]) if allocation else 0.0,
                "allocation_confidence": _float(allocation["allocation_confidence"]) if allocation else _float(candidate.confidence),
            }
        )
    check_counts = Counter(item.payload["status"] for item in checks)
    allocation_counts = Counter(item.payload["dimension_type"] for item in allocations)
    graph_json = {"nodes": [*sku_nodes, *dimension_nodes_by_key.values()], "edges": edges}
    coverage_summary = {
        "population": dict(population_summary),
        "dimension_count": len(dimension_nodes_by_key),
        "edge_count": len(edges),
        "relation_status_counts": dict(sorted(Counter(edge["relation_status"] for edge in edges).items())),
    }
    allocation_summary = {
        "allocation_count": len(allocations),
        "allocation_counts_by_dimension_type": dict(sorted(allocation_counts.items())),
    }
    unallocated_summary = {
        "check_status_counts": dict(sorted(check_counts.items())),
        "no_allocation_count": sum(1 for item in checks if item.payload["check_type"] == "no_allocation_eligible_dimension"),
    }
    graph_hash = stable_hash(
        {
            "graph": graph_json,
            "coverage": coverage_summary,
            "allocation": allocation_summary,
            "unallocated": unallocated_summary,
        },
        version="m11d-graph-result-v1",
    )
    return M11DWritePayload(
        {
            "graph_snapshot_id": _record_id("m11d_graph", batch_id, analysis_population, market_window, rule_version),
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "analysis_population": analysis_population,
            "market_window": market_window,
            "node_count": len(sku_nodes) + len(dimension_nodes_by_key),
            "edge_count": len(edges),
            "dimension_count": len(dimension_nodes_by_key),
            "sku_count": len(sku_nodes),
            "graph_json": graph_json,
            "coverage_summary_json": coverage_summary,
            "allocation_summary_json": allocation_summary,
            "unallocated_summary_json": unallocated_summary,
            "rule_version": rule_version,
            "input_fingerprint": stable_hash(
                {"candidate_count": len(candidates), "allocation_count": len(allocations), "population": population_summary},
                version="m11d-graph-input-v1",
            ),
            "graph_hash": graph_hash,
            "is_current": True,
        }
    )


def _allocation_closure_checks(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
    sku_code: str,
    dimension_type: str,
    market: M11DSkuMarket,
    weight_sum: Decimal,
    volume_sum: Decimal,
    amount_sum: Decimal,
) -> list[M11DWritePayload]:
    return [
        _numeric_check(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            check_type="allocation_weight_normalized",
            sku_code=sku_code,
            dimension_type=dimension_type,
            dimension_code="",
            expected=ONE,
            actual=weight_sum,
            tolerance=Decimal("0.0001"),
            failure_reason_code="allocation_weight_not_normalized",
            failure_reason_cn="SKU 在同一维度类型内 allocation weight 未归一。",
        ),
        _numeric_check(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            check_type="allocated_volume_closed",
            sku_code=sku_code,
            dimension_type=dimension_type,
            dimension_code="",
            expected=market.sales_volume_total,
            actual=volume_sum,
            tolerance=max(Decimal("1.0000"), market.sales_volume_total * Decimal("0.0001")),
            failure_reason_code="allocated_volume_gap",
            failure_reason_cn="SKU 分配销量与市场窗口总销量不闭合。",
        ),
        _numeric_check(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=product_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            check_type="allocated_amount_closed",
            sku_code=sku_code,
            dimension_type=dimension_type,
            dimension_code="",
            expected=market.sales_amount_total,
            actual=amount_sum,
            tolerance=max(Decimal("1.0000"), market.sales_amount_total * Decimal("0.0001")),
            failure_reason_code="allocated_amount_gap",
            failure_reason_cn="SKU 分配销额与市场窗口总销额不闭合。",
        ),
    ]


def _dimension_total_checks(
    allocations_by_sku_type: Mapping[tuple[str, str], Sequence[dict[str, Any]]],
    *,
    sku_markets: Mapping[str, M11DSkuMarket],
    included_skus: Sequence[str],
    dimension_types: Sequence[str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
) -> list[M11DWritePayload]:
    checks: list[M11DWritePayload] = []
    for dimension_type in dimension_types:
        allocated_skus = {sku_code for sku_code in included_skus if allocations_by_sku_type.get((sku_code, dimension_type))}
        expected_volume = sum((sku_markets[sku].sales_volume_total for sku in allocated_skus if sku in sku_markets), ZERO)
        actual_volume = sum(
            (_decimal(item["allocated_sales_volume"]) or ZERO)
            for sku in allocated_skus
            for item in allocations_by_sku_type.get((sku, dimension_type), [])
        )
        checks.append(
            _numeric_check(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                product_category=product_category,
                analysis_population=analysis_population,
                market_window=market_window,
                rule_version=rule_version,
                check_type="dimension_type_allocated_volume_closed",
                sku_code="",
                dimension_type=dimension_type,
                dimension_code="",
                expected=expected_volume,
                actual=actual_volume,
                tolerance=max(Decimal("1.0000"), expected_volume * Decimal("0.0001")),
                failure_reason_code="dimension_total_gap",
                failure_reason_cn="该维度类型的 allocation 明细与已分配 SKU 市场总量不闭合。",
            )
        )
    return checks


def _numeric_check(**kwargs: Any) -> M11DWritePayload:
    expected = _decimal(kwargs["expected"]) or ZERO
    actual = _decimal(kwargs["actual"]) or ZERO
    tolerance = _decimal(kwargs["tolerance"]) or ZERO
    gap = abs(expected - actual)
    status = "passed" if gap <= tolerance else "failed"
    severity = "info" if status == "passed" else "blocking"
    return _check_payload(
        expected=expected,
        actual=actual,
        gap=gap,
        tolerance=tolerance,
        status=status,
        severity=severity,
        payload={"expected": str(expected), "actual": str(actual), "gap": str(gap), "tolerance": str(tolerance)},
        **{key: value for key, value in kwargs.items() if key not in {"expected", "actual", "tolerance"}},
    )


def _check_payload(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    analysis_population: str,
    market_window: str,
    rule_version: str,
    check_type: str,
    sku_code: str,
    dimension_type: str,
    dimension_code: str,
    expected: Decimal,
    actual: Decimal,
    tolerance: Decimal,
    status: str,
    severity: str,
    failure_reason_code: str,
    failure_reason_cn: str,
    payload: Mapping[str, Any],
    gap: Decimal | None = None,
) -> M11DWritePayload:
    gap_value = abs((_decimal(expected) or ZERO) - (_decimal(actual) or ZERO)) if gap is None else gap
    fingerprint = stable_hash(
        {
            "check_type": check_type,
            "sku_code": sku_code,
            "dimension_type": dimension_type,
            "dimension_code": dimension_code,
            "analysis_population": analysis_population,
            "market_window": market_window,
            "payload": payload,
        },
        version="m11d-check-input-v1",
    )
    return M11DWritePayload(
        {
            "check_id": _record_id("m11d_check", batch_id, analysis_population, market_window, check_type, sku_code, dimension_type, dimension_code, fingerprint),
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "analysis_population": analysis_population,
            "market_window": market_window,
            "check_type": check_type,
            "sku_code": sku_code,
            "dimension_type": dimension_type,
            "dimension_code": dimension_code,
            "expected_value": _q6(_decimal(expected) or ZERO),
            "actual_value": _q6(_decimal(actual) or ZERO),
            "gap_value": _q6(gap_value),
            "tolerance_value": _q6(_decimal(tolerance) or ZERO),
            "status": status,
            "severity": severity,
            "failure_reason_code": "" if status == "passed" else failure_reason_code,
            "failure_reason_cn": "" if status == "passed" else failure_reason_cn,
            "check_payload_json": dict(payload),
            "rule_version": rule_version,
            "input_fingerprint": fingerprint,
            "result_hash": stable_hash(
                {"status": status, "gap": str(_q6(gap_value)), "severity": severity},
                version="m11d-check-result-v1",
            ),
            "is_current": True,
            "processing_status": "success" if status == "passed" else "diagnostic" if status == "diagnostic" else "failed",
            "review_required": severity == "blocking",
            "review_status": "review_required" if severity == "blocking" else "auto_pass",
            "review_reason_json": {"failure_reason_code": failure_reason_code} if severity == "blocking" else {},
        }
    )


def _allocation_confidence(candidate: M11DRelationCandidate, market: M11DSkuMarket) -> Decimal:
    evidence_score = Decimal("1.0000") if candidate.evidence_ids_json else Decimal("0.4000")
    value = candidate.confidence * Decimal("0.5000") + evidence_score * Decimal("0.2500") + market.confidence * Decimal("0.2500")
    if candidate.allocation_role == ROLE_SECONDARY:
        value = min(value, Decimal("0.8500"))
    elif candidate.allocation_role == ROLE_OBSERVED:
        value = min(value, Decimal("0.7000"))
    return _q4(min(max(value, ZERO), ONE))


def _summary_text(name: str, dimension_type: str, relation_count: int, allocation_count: int, volume: Decimal) -> str:
    type_label = {DIM_USER_TASK: "用户任务", DIM_TARGET_GROUP: "目标客群", DIM_BATTLEFIELD: "价值战场"}.get(dimension_type, dimension_type)
    return f"{type_label}“{name}”覆盖 {relation_count} 个 SKU，其中 {allocation_count} 个 SKU 进入销量解释分配，估算承接销量 { _q4(volume) }。"


def _safe_share(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= ZERO:
        return ZERO
    return _q6(max(min(numerator / denominator, ONE), ZERO))


def _normalize_size_tier(
    market_pool_key: str | None,
    size_segment: str | None,
    screen_size_class: str | None,
    screen_size: Decimal | None,
) -> str:
    for value in (market_pool_key, size_segment, screen_size_class):
        text = str(value or "")
        for token in ("small_32_45", "medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"):
            if token in text:
                return token
    size = _decimal(screen_size)
    if size is None:
        return "unknown"
    if size <= Decimal("45"):
        return "small_32_45"
    if size <= Decimal("59"):
        return "medium_46_59"
    if size <= Decimal("69"):
        return "large_60_69"
    if size <= Decimal("85"):
        return "xlarge_70_85"
    if size >= Decimal("98"):
        return "giant_98_plus"
    return "unknown"


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
    summary_json = {"project_id": project_id, "category_code": category_code, "batch_id": batch_id, "message_cn": message_cn}
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M11D,
        status=Core3RunStatus.BLOCKED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m11d-blocked-v1"),
        warnings=[message_cn],
        review_issues=[],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=finished_at,
    )


def _failed_result(
    *,
    project_id: str,
    category_code: str,
    batch_id: str | None,
    run_id: str | None,
    started_at: datetime,
    error_code: str,
    message_cn: str,
    error_message: str,
) -> Core3ModuleRunResultSchema:
    summary_json = {
        "project_id": project_id,
        "category_code": category_code,
        "batch_id": batch_id,
        "error_code": error_code,
        "message_cn": message_cn,
        "error_message": error_message,
    }
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M11D,
        status=Core3RunStatus.FAILED,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        output_hash=stable_hash(summary_json, version="m11d-failed-v1"),
        warnings=[message_cn],
        review_issues=[summary_json],
        downstream_impacts=[],
        summary_json=summary_json,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
    )


def _record_id(prefix: str, *parts: Any) -> str:
    digest = stable_hash([str(part) for part in parts], version=f"{prefix}-id-v1")
    return f"{prefix}_{digest.split(':')[-1][:32]}"


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _q4(value: Decimal) -> Decimal:
    return value.quantize(Q4, rounding=ROUND_HALF_UP)


def _q6(value: Decimal) -> Decimal:
    return value.quantize(Q6, rounding=ROUND_HALF_UP)


def _float(value: Any) -> float:
    decimal = _decimal(value)
    return float(decimal) if decimal is not None else 0.0


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if item is not None and str(item)]


def _unique_strings(values: Sequence[str]) -> list[str]:
    return sorted({str(value) for value in values if value})


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable_value(value, nested=False) for key, value in payload.items()}


def _jsonable_value(value: Any, *, nested: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value) if nested else value
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item, nested=True) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_value(item, nested=True) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item, nested=True) for item in value]
    return value


def _refresh_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for field_name, value in _jsonable_payload(payload).items():
        if field_name in primary_keys or field_name == "created_at":
            continue
        setattr(existing, field_name, value)
