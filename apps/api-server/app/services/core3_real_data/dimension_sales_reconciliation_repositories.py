"""M11.7 dimension sales reconciliation repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M117InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M117Inputs:
    profiles: tuple[entities.Core3SkuBusinessProfile, ...]
    dimensions: tuple[entities.Core3SkuBusinessProfileDimension, ...]
    allocations: tuple[entities.Core3SkuBusinessProfileSalesAllocation, ...]
    m08_profile_count: int


@dataclass(frozen=True)
class DimensionSalesReconciliationWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class DimensionSalesReconciliationRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M08 SKU 综合信号画像": self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
            "M11.6 SKU 业务画像": self._count_current_rows(entities.Core3SkuBusinessProfile, batch_id),
            "M11.6 SKU 维度销量分配": self._count_current_rows(entities.Core3SkuBusinessProfileSalesAllocation, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M117InputBlockedError(f"M11.7 需要先完成上游产物：{', '.join(missing)}。")

    def assert_ready_for_m12(self, batch_id: str) -> None:
        check_count = self._count_current_rows(entities.Core3BusinessSalesReconciliationCheck, batch_id)
        if check_count == 0:
            raise M117InputBlockedError("M12 前必须先执行 M11.7 销量分配对账。")
        blocking_issue_count = self._count_current_rows(
            entities.Core3BusinessSalesReconciliationIssue,
            batch_id,
            resolved_status="open",
            severity="blocker",
        )
        if blocking_issue_count:
            raise M117InputBlockedError(f"M11.7 仍有 {blocking_issue_count} 条阻断级销量对账问题，M12 暂不能继续。")
        failed_check_count = self._count_current_rows(
            entities.Core3BusinessSalesReconciliationCheck,
            batch_id,
            status="failed",
        )
        if failed_check_count:
            raise M117InputBlockedError(f"M11.7 仍有 {failed_check_count} 条失败对账检查，M12 暂不能继续。")

    def load_inputs(self, batch_id: str, sku_scope: Sequence[str] = ()) -> M117Inputs:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        profile_stmt = self._current_query(entities.Core3SkuBusinessProfile, batch_id).order_by(
            entities.Core3SkuBusinessProfile.sku_code
        )
        if sku_scope_tuple:
            profile_stmt = profile_stmt.where(entities.Core3SkuBusinessProfile.sku_code.in_(sku_scope_tuple))
        profiles = tuple(self._paged_scalars(profile_stmt, limit=100000, offset=0))
        sku_codes = tuple(sorted({profile.sku_code for profile in profiles}))

        dimension_stmt = self._current_query(entities.Core3SkuBusinessProfileDimension, batch_id).order_by(
            entities.Core3SkuBusinessProfileDimension.sku_code,
            entities.Core3SkuBusinessProfileDimension.dimension_type,
            entities.Core3SkuBusinessProfileDimension.dimension_rank,
        )
        allocation_stmt = self._current_query(entities.Core3SkuBusinessProfileSalesAllocation, batch_id).order_by(
            entities.Core3SkuBusinessProfileSalesAllocation.sku_code,
            entities.Core3SkuBusinessProfileSalesAllocation.dimension_type,
            entities.Core3SkuBusinessProfileSalesAllocation.dimension_code,
        )
        if sku_codes:
            dimension_stmt = dimension_stmt.where(entities.Core3SkuBusinessProfileDimension.sku_code.in_(sku_codes))
            allocation_stmt = allocation_stmt.where(entities.Core3SkuBusinessProfileSalesAllocation.sku_code.in_(sku_codes))
        return M117Inputs(
            profiles=profiles,
            dimensions=tuple(self._paged_scalars(dimension_stmt, limit=100000, offset=0)),
            allocations=tuple(self._paged_scalars(allocation_stmt, limit=100000, offset=0)),
            m08_profile_count=self._count_current_rows(entities.Core3SkuSignalProfile, batch_id),
        )

    def mark_outputs_stale(self, *, batch_id: str, rule_version: str) -> None:
        for model_cls in (
            entities.Core3BusinessDimensionSalesSummary,
            entities.Core3BusinessDimensionSkuContribution,
            entities.Core3BusinessSalesReconciliationCheck,
            entities.Core3BusinessSalesReconciliationIssue,
        ):
            stmt = (
                update(model_cls)
                .where(model_cls.project_id == self.project_id)
                .where(model_cls.category_code == self.category_code.value)
                .where(model_cls.batch_id == batch_id)
                .where(model_cls.rule_version == rule_version)
                .where(model_cls.is_current.is_(True))
                .values(is_current=False)
            )
            self.db.execute(stmt)
        self.db.flush()

    def save_summaries(self, records: Sequence[Any]) -> DimensionSalesReconciliationWriteResult:
        return self._save_many(
            entities.Core3BusinessDimensionSalesSummary,
            records,
            unique_fields=("batch_id", "dimension_type", "dimension_code", "rule_version"),
        )

    def save_contributions(self, records: Sequence[Any]) -> DimensionSalesReconciliationWriteResult:
        return self._save_many(
            entities.Core3BusinessDimensionSkuContribution,
            records,
            unique_fields=("batch_id", "dimension_type", "dimension_code", "sku_code", "rule_version"),
        )

    def save_checks(self, records: Sequence[Any]) -> DimensionSalesReconciliationWriteResult:
        return self._save_many(
            entities.Core3BusinessSalesReconciliationCheck,
            records,
            unique_fields=("batch_id", "check_type", "sku_code", "dimension_type", "dimension_code", "input_fingerprint"),
        )

    def save_issues(self, records: Sequence[Any]) -> DimensionSalesReconciliationWriteResult:
        return self._save_many(
            entities.Core3BusinessSalesReconciliationIssue,
            records,
            unique_fields=(
                "batch_id",
                "issue_scope",
                "sku_code",
                "dimension_type",
                "dimension_code",
                "issue_code",
                "input_fingerprint",
            ),
        )

    def list_current_summaries(
        self,
        batch_id: str,
        *,
        dimension_type: str | None = None,
        dimension_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3BusinessDimensionSalesSummary]:
        stmt = self._current_query(entities.Core3BusinessDimensionSalesSummary, batch_id).order_by(
            entities.Core3BusinessDimensionSalesSummary.dimension_type,
            entities.Core3BusinessDimensionSalesSummary.standard_dimension_rank,
            entities.Core3BusinessDimensionSalesSummary.dimension_code,
        )
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3BusinessDimensionSalesSummary.dimension_type == dimension_type)
        if dimension_code is not None:
            stmt = stmt.where(entities.Core3BusinessDimensionSalesSummary.dimension_code == dimension_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_contributions(
        self,
        batch_id: str,
        *,
        dimension_type: str | None = None,
        dimension_code: str | None = None,
        sku_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3BusinessDimensionSkuContribution]:
        stmt = self._current_query(entities.Core3BusinessDimensionSkuContribution, batch_id).order_by(
            entities.Core3BusinessDimensionSkuContribution.dimension_type,
            entities.Core3BusinessDimensionSkuContribution.dimension_code,
            entities.Core3BusinessDimensionSkuContribution.allocated_sales_volume.desc(),
            entities.Core3BusinessDimensionSkuContribution.sku_code,
        )
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3BusinessDimensionSkuContribution.dimension_type == dimension_type)
        if dimension_code is not None:
            stmt = stmt.where(entities.Core3BusinessDimensionSkuContribution.dimension_code == dimension_code)
        if sku_code is not None:
            stmt = stmt.where(entities.Core3BusinessDimensionSkuContribution.sku_code == sku_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_checks(
        self,
        batch_id: str,
        *,
        status: str | None = None,
        check_type: str | None = None,
        dimension_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3BusinessSalesReconciliationCheck]:
        stmt = self._current_query(entities.Core3BusinessSalesReconciliationCheck, batch_id).order_by(
            entities.Core3BusinessSalesReconciliationCheck.status.desc(),
            entities.Core3BusinessSalesReconciliationCheck.check_type,
            entities.Core3BusinessSalesReconciliationCheck.sku_code,
            entities.Core3BusinessSalesReconciliationCheck.dimension_type,
        )
        if status is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationCheck.status == status)
        if check_type is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationCheck.check_type == check_type)
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationCheck.dimension_type == dimension_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_issues(
        self,
        batch_id: str,
        *,
        severity: str | None = None,
        issue_code: str | None = None,
        sku_code: str | None = None,
        dimension_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3BusinessSalesReconciliationIssue]:
        stmt = self._current_query(entities.Core3BusinessSalesReconciliationIssue, batch_id).order_by(
            entities.Core3BusinessSalesReconciliationIssue.severity.desc(),
            entities.Core3BusinessSalesReconciliationIssue.issue_code,
            entities.Core3BusinessSalesReconciliationIssue.sku_code,
        )
        if severity is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationIssue.severity == severity)
        if issue_code is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationIssue.issue_code == issue_code)
        if sku_code is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationIssue.sku_code == sku_code)
        if dimension_type is not None:
            stmt = stmt.where(entities.Core3BusinessSalesReconciliationIssue.dimension_type == dimension_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def count_current_rows(self, model_cls: Any, batch_id: str, **filters: Any) -> int:
        return self._count_current_rows(model_cls, batch_id, **filters)

    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return self._base_query(model_cls, batch_id).where(model_cls.is_current.is_(True))

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _count_current_rows(self, model_cls: Any, batch_id: str, **filters: Any) -> int:
        stmt = (
            select(func.count())
            .select_from(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
            .where(model_cls.is_current.is_(True))
        )
        for field_name, value in filters.items():
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return int(self.db.execute(stmt).scalar_one())

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> DimensionSalesReconciliationWriteResult:
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
        return DimensionSalesReconciliationWriteResult(tuple(records), created_count, reused_count, updated_count)

    def _save_one(self, model_cls: Any, payload: Any, *, unique_fields: tuple[str, ...], hash_field: str) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
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

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M11.7 repository payload must be a mapping or Pydantic model")
        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        result = {key: value for key, value in raw_payload.items() if key in model_fields}
        for audit_field in ("created_at", "updated_at"):
            if result.get(audit_field) is None:
                result.pop(audit_field, None)
        return result

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        for field_name in unique_fields:
            value = payload.get(field_name)
            if value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required")
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return self.db.execute(stmt).scalars().first()


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
