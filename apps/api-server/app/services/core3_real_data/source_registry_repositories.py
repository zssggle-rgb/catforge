"""M00 raw source read repositories and schema inspection."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

from sqlalchemy import bindparam, inspect, select, text

from app.models.entities import Core3SourceBatch, Core3SourceImpactedSku, Core3SourceRowRegistry
from app.schemas.core3_real_data import Core3SourceBatchRegisterRequest
from app.services.core3_real_data.constants import (
    CORE3_RAW_SOURCE_TABLES,
    Core3ReviewStatus,
    Core3SourceBatchStatus,
    Core3SourceImpactLevel,
    Core3SourceBatchType,
    Core3CategoryCode,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
    RawSourceReadOnlyMixin,
)


RAW_SOURCE_BUSINESS_KEY_COLUMNS: dict[str, tuple[str, ...]] = {
    "week_sales_data": ("date_value", "channel", "platform"),
    "attribute_data": ("attr_name", "attr_value"),
    "selling_points_data": ("variable", "selling_point"),
    "comment_data": (
        "comment_id",
        "comment_content",
        "comments_segments",
        "primary_dim",
        "secondary_dim",
        "third_dim",
        "sentiment",
    ),
}

RAW_SOURCE_HASH_COLUMNS: dict[str, tuple[str, ...]] = {
    "week_sales_data": (
        "model_code",
        "category",
        "brand",
        "model",
        "date_value",
        "channel",
        "platform",
        "sales_volume",
        "sales_amount",
        "avg_price",
        "write_time",
    ),
    "attribute_data": (
        "model_code",
        "category",
        "brand",
        "model",
        "attr_name",
        "attr_value",
        "write_time",
    ),
    "selling_points_data": (
        "model_code",
        "category",
        "brand",
        "model",
        "variable",
        "selling_point",
        "write_time",
    ),
    "comment_data": (
        "model_code",
        "category",
        "brand",
        "model",
        "comment_id",
        "comment_content",
        "comments_segments",
        "primary_dim",
        "secondary_dim",
        "third_dim",
        "sentiment",
        "write_time",
    ),
}
RAW_CATEGORY_VALUES_BY_CATEGORY_CODE: dict[Core3CategoryCode, tuple[str, ...]] = {
    Core3CategoryCode.TV: ("彩电", "电视", "TV"),
    Core3CategoryCode.AC: ("空调", "空气调节器", "AC"),
}


@dataclass(frozen=True)
class SourceTableConfig:
    source_table: str
    source_pk_column: str = "id"
    sku_column: str = "model_code"
    model_column: str = "model"
    brand_column: str = "brand"
    category_column: str = "category"
    write_time_column: str = "write_time"
    business_key_columns: tuple[str, ...] = field(default_factory=tuple)
    hash_columns: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceColumnSchema:
    name: str
    type: str
    nullable: bool | None


@dataclass(frozen=True)
class SourceTableSchemaSnapshot:
    source_table: str
    columns: tuple[SourceColumnSchema, ...]
    schema_hash: str
    schema_status: str = "observed"

    def to_json(self) -> dict[str, Any]:
        return {
            "columns": [
                {"name": column.name, "type": column.type, "nullable": column.nullable}
                for column in self.columns
            ],
            "schema_hash": self.schema_hash,
            "schema_status": self.schema_status,
        }


@dataclass(frozen=True)
class SourceTableWatermark:
    source_table: str
    row_count: int
    min_source_pk: str | None = None
    max_source_pk: str | None = None
    min_write_time: datetime | None = None
    max_write_time: datetime | None = None
    distinct_sku_count: int = 0


@dataclass(frozen=True)
class SourceScanPlan:
    source_table: str
    batch_type: Core3SourceBatchType = Core3SourceBatchType.FULL
    min_source_pk: str | None = None
    min_source_pk_exclusive: str | None = None
    max_source_pk: str | None = None
    min_write_time_exclusive: datetime | None = None
    max_write_time_inclusive: datetime | None = None
    combine_filters_with_or: bool = False
    limit: int | None = None
    offset: int = 0


class SourceSchemaInspector:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    def inspect_table(self, source_table: str) -> SourceTableSchemaSnapshot:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        bind = self.context.db.get_bind()
        inspector = inspect(bind)
        if not inspector.has_table(table_name):
            raise ValueError(f"raw source table not found: {table_name}")

        columns = tuple(
            SourceColumnSchema(
                name=str(column["name"]),
                type=str(column["type"]),
                nullable=column.get("nullable"),
            )
            for column in inspector.get_columns(table_name)
        )
        schema_hash = stable_hash(
            [
                {"name": column.name, "type": column.type, "nullable": column.nullable}
                for column in columns
            ],
            version="m00_schema_v1",
        )
        return SourceTableSchemaSnapshot(
            source_table=table_name,
            columns=columns,
            schema_hash=schema_hash,
        )


class RawSourceRepository(Core3BaseRepository, RawSourceReadOnlyMixin):
    def __init__(
        self,
        context: Core3RepositoryContext,
        source_table_configs: Mapping[str, SourceTableConfig] | None = None,
    ) -> None:
        super().__init__(context)
        self.source_table_configs = dict(source_table_configs or default_source_table_configs())
        self.schema_inspector = SourceSchemaInspector(context)

    @staticmethod
    def ensure_source_table_name(source_table: str) -> str:
        normalized = RawSourceReadOnlyMixin.raw_source_guard.ensure_raw_source_table(source_table)
        return _quote_identifier(normalized, return_unquoted=True)

    def list_source_tables(self) -> tuple[SourceTableConfig, ...]:
        return tuple(self.source_table_configs[table_name] for table_name in CORE3_RAW_SOURCE_TABLES)

    def inspect_table(self, source_table: str) -> SourceTableSchemaSnapshot:
        return self.schema_inspector.inspect_table(source_table)

    def get_table_watermark(self, source_table: str) -> SourceTableWatermark:
        config = self._config(source_table)
        columns = self._column_names(config.source_table)
        sql, params = _watermark_sql(config, columns, raw_category_values=self._raw_category_values())
        row = self._execute_one(sql, params)
        return SourceTableWatermark(
            source_table=config.source_table,
            row_count=int(row.get("row_count") or 0),
            min_source_pk=_string_or_none(row.get("min_source_pk")),
            max_source_pk=_string_or_none(row.get("max_source_pk")),
            min_write_time=row.get("min_write_time"),
            max_write_time=row.get("max_write_time"),
            distinct_sku_count=int(row.get("distinct_sku_count") or 0),
        )

    def iter_rows(self, source_table: str, scan_plan: SourceScanPlan) -> Iterable[dict[str, Any]]:
        config = self._config(source_table)
        if scan_plan.source_table != config.source_table:
            raise ValueError("scan_plan source_table does not match requested source_table")
        columns = self._column_names(config.source_table)
        sql, params = _scan_sql(config, columns, scan_plan, raw_category_values=self._raw_category_values())
        result = self.db.execute(text(sql), params)
        for row in result.mappings():
            yield dict(row)

    def iter_row_chunks(
        self,
        source_table: str,
        scan_plan: SourceScanPlan,
        *,
        chunk_size: int,
    ) -> Iterable[list[dict[str, Any]]]:
        config = self._config(source_table)
        normalized_chunk_size = max(int(chunk_size), 1)
        remaining = scan_plan.limit
        next_min_source_pk_exclusive = scan_plan.min_source_pk_exclusive

        while remaining is None or remaining > 0:
            current_limit = normalized_chunk_size if remaining is None else min(normalized_chunk_size, remaining)
            current_plan = replace(
                scan_plan,
                min_source_pk_exclusive=next_min_source_pk_exclusive,
                limit=current_limit,
                offset=0,
            )
            rows = list(self.iter_rows(source_table, current_plan))
            if not rows:
                break

            yield rows

            if remaining is not None:
                remaining -= len(rows)
            last_source_pk = rows[-1].get(config.source_pk_column)
            if last_source_pk in (None, "") or len(rows) < current_limit:
                break
            next_min_source_pk_exclusive = str(last_source_pk)

    def get_row_by_source_ref(self, source_table: str, source_pk: str) -> dict[str, Any] | None:
        config = self._config(source_table)
        sql = (
            f"SELECT * FROM {_quote_identifier(config.source_table)} "
            f"WHERE {_quote_identifier(config.source_pk_column)} = :source_pk LIMIT 1"
        )
        self.raw_source_guard.ensure_read_only_sql(sql)
        row = self.db.execute(text(sql), {"source_pk": source_pk}).mappings().first()
        return dict(row) if row else None

    def get_rows_by_source_refs(self, source_table: str, source_pks: Sequence[str]) -> dict[str, dict[str, Any]]:
        config = self._config(source_table)
        normalized_source_pks = tuple(
            dict.fromkeys(str(source_pk) for source_pk in source_pks if source_pk not in (None, ""))
        )
        if not normalized_source_pks:
            return {}

        sql = (
            f"SELECT * FROM {_quote_identifier(config.source_table)} "
            f"WHERE {_quote_identifier(config.source_pk_column)} IN :source_pks"
        )
        self.raw_source_guard.ensure_read_only_sql(sql)
        statement = text(sql).bindparams(bindparam("source_pks", expanding=True))
        rows_by_source_pk: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(normalized_source_pks, 1000):
            for row in self.db.execute(statement, {"source_pks": tuple(chunk)}).mappings():
                source_pk = row.get(config.source_pk_column)
                if source_pk not in (None, ""):
                    rows_by_source_pk[str(source_pk)] = dict(row)
        return rows_by_source_pk

    def _config(self, source_table: str) -> SourceTableConfig:
        table_name = self.ensure_source_table_name(source_table)
        if table_name not in self.source_table_configs:
            raise ValueError(f"unknown raw source table: {source_table}")
        return self.source_table_configs[table_name]

    def _column_names(self, source_table: str) -> frozenset[str]:
        snapshot = self.inspect_table(source_table)
        return frozenset(column.name for column in snapshot.columns)

    def _raw_category_values(self) -> tuple[str, ...]:
        return RAW_CATEGORY_VALUES_BY_CATEGORY_CODE.get(self.category_code, ())

    def _execute_one(self, sql: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        self.raw_source_guard.ensure_read_only_sql(sql)
        row = self.db.execute(text(sql), dict(params or {})).mappings().one()
        return dict(row)


class SourceBatchRepository(Core3BaseRepository):
    def find_latest_successful_batch(
        self,
        *,
        source_system: str,
        source_database: str,
        source_schema: str | None,
        hash_version: str,
    ) -> Core3SourceBatch | None:
        stmt = (
            select(Core3SourceBatch)
            .where(Core3SourceBatch.project_id == self.project_id)
            .where(Core3SourceBatch.category_code == self.category_code.value)
            .where(Core3SourceBatch.source_system == source_system)
            .where(Core3SourceBatch.source_database == source_database)
            .where(Core3SourceBatch.source_schema == source_schema)
            .where(Core3SourceBatch.hash_version == hash_version)
            .where(
                Core3SourceBatch.status.in_(
                    [
                        Core3SourceBatchStatus.REGISTERED.value,
                        Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value,
                    ]
                )
            )
            .order_by(Core3SourceBatch.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def create_running_batch(
        self,
        request: Core3SourceBatchRegisterRequest,
        *,
        scan_started_at: datetime | None = None,
    ) -> Core3SourceBatch:
        started_at = scan_started_at or _now_utc()
        batch = Core3SourceBatch(
            batch_id=_new_m00_batch_id(started_at),
            project_id=request.project_id,
            category_code=request.category_code,
            run_id=request.run_id,
            module_run_id=request.module_run_id,
            batch_type=request.batch_type,
            source_system=request.source_system,
            source_database=request.source_database,
            source_schema=request.source_schema,
            source_tables=list(request.source_tables),
            ruleset_version=request.ruleset_version,
            module_version=request.module_version,
            hash_version=request.hash_version,
            scan_started_at=started_at,
            input_watermark_json={},
            row_counts_json={},
            write_time_range_json={},
            source_pk_range_json={},
            schema_snapshot_json={},
            impacted_sku_count=0,
            affected_module_summary_json={},
            quality_summary_json={},
            status=Core3SourceBatchStatus.RUNNING,
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS,
        )
        self.db.add(batch)
        self.db.flush()
        return batch

    def finish_batch(
        self,
        batch: Core3SourceBatch,
        *,
        status: Core3SourceBatchStatus,
        schema_snapshot_json: Mapping[str, Any],
        input_watermark_json: Mapping[str, Any],
        row_counts_json: Mapping[str, Any],
        write_time_range_json: Mapping[str, Any],
        source_pk_range_json: Mapping[str, Any],
        affected_module_summary_json: Mapping[str, Any],
        quality_summary_json: Mapping[str, Any],
        impacted_sku_count: int = 0,
        review_required: bool = False,
        review_reason: Mapping[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> Core3SourceBatch:
        batch.status = status.value
        batch.scan_finished_at = _now_utc()
        batch.schema_snapshot_json = dict(schema_snapshot_json)
        batch.input_watermark_json = dict(input_watermark_json)
        batch.row_counts_json = dict(row_counts_json)
        batch.write_time_range_json = dict(write_time_range_json)
        batch.source_pk_range_json = dict(source_pk_range_json)
        batch.affected_module_summary_json = dict(affected_module_summary_json)
        batch.quality_summary_json = dict(quality_summary_json)
        batch.impacted_sku_count = impacted_sku_count
        batch.review_required = review_required
        batch.review_status = (
            Core3ReviewStatus.REVIEW_REQUIRED.value if review_required else Core3ReviewStatus.AUTO_PASS.value
        )
        batch.review_reason = dict(review_reason) if review_reason else None
        batch.error_code = error_code
        batch.error_message = error_message
        batch.updated_at = _now_utc()
        self.db.flush()
        return batch

    def mark_failed(
        self,
        batch: Core3SourceBatch,
        *,
        error_code: str,
        error_message: str,
    ) -> Core3SourceBatch:
        return self.finish_batch(
            batch,
            status=Core3SourceBatchStatus.FAILED,
            schema_snapshot_json=batch.schema_snapshot_json or {},
            input_watermark_json=batch.input_watermark_json or {},
            row_counts_json=batch.row_counts_json or {},
            write_time_range_json=batch.write_time_range_json or {},
            source_pk_range_json=batch.source_pk_range_json or {},
            affected_module_summary_json=batch.affected_module_summary_json or {},
            quality_summary_json=batch.quality_summary_json or {"status": "failed", "warnings": []},
            review_required=True,
            review_reason={"codes": [error_code]},
            error_code=error_code,
            error_message=error_message,
        )


class SourceRowRegistryRepository(Core3BaseRepository):
    def find_latest_by_source(
        self,
        *,
        source_table: str,
        source_pk: str,
        hash_version: str,
    ) -> Core3SourceRowRegistry | None:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        stmt = (
            select(Core3SourceRowRegistry)
            .join(Core3SourceBatch, Core3SourceBatch.batch_id == Core3SourceRowRegistry.batch_id)
            .where(Core3SourceRowRegistry.project_id == self.project_id)
            .where(Core3SourceRowRegistry.category_code == self.category_code.value)
            .where(Core3SourceRowRegistry.source_table == table_name)
            .where(Core3SourceRowRegistry.source_pk == source_pk)
            .where(Core3SourceRowRegistry.hash_version == hash_version)
            .where(
                Core3SourceBatch.status.in_(
                    [
                        Core3SourceBatchStatus.REGISTERED.value,
                        Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value,
                    ]
                )
            )
            .order_by(Core3SourceRowRegistry.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def find_latest_by_sources(
        self,
        *,
        source_table: str,
        source_pks: Sequence[str],
        hash_version: str,
    ) -> dict[str, Core3SourceRowRegistry]:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        normalized_source_pks = tuple(
            dict.fromkeys(str(source_pk) for source_pk in source_pks if source_pk not in (None, ""))
        )
        if not normalized_source_pks:
            return {}

        stmt = (
            select(Core3SourceRowRegistry)
            .join(Core3SourceBatch, Core3SourceBatch.batch_id == Core3SourceRowRegistry.batch_id)
            .where(Core3SourceRowRegistry.project_id == self.project_id)
            .where(Core3SourceRowRegistry.category_code == self.category_code.value)
            .where(Core3SourceRowRegistry.source_table == table_name)
            .where(Core3SourceRowRegistry.source_pk.in_(normalized_source_pks))
            .where(Core3SourceRowRegistry.hash_version == hash_version)
            .where(
                Core3SourceBatch.status.in_(
                    [
                        Core3SourceBatchStatus.REGISTERED.value,
                        Core3SourceBatchStatus.REGISTERED_WITH_WARNING.value,
                    ]
                )
            )
            .order_by(Core3SourceRowRegistry.source_pk.asc(), Core3SourceRowRegistry.created_at.desc())
        )
        latest_by_source: dict[str, Core3SourceRowRegistry] = {}
        for row in self.db.execute(stmt).scalars():
            if row.source_pk is not None and row.source_pk not in latest_by_source:
                latest_by_source[row.source_pk] = row
        return latest_by_source

    def create_row_registry(
        self,
        *,
        batch_id: str,
        source_table: str,
        source_pk: str | None,
        source_pk_strategy: str,
        source_row_id: str | None,
        row_hash: str | None,
        hash_version: str,
        previous_row: Core3SourceRowRegistry | None,
        sku_code_candidate: str | None,
        model_name_raw: str | None,
        brand_raw: str | None,
        category_raw: str | None,
        write_time: datetime | str | None,
        business_key_json: Mapping[str, Any],
        source_field_presence_json: Mapping[str, Any],
        operation_type: str,
        change_reason: str | None,
        affected_modules: Sequence[Mapping[str, Any]],
        quality_hint: Mapping[str, Any],
        review_required: bool,
        review_status: str,
    ) -> Core3SourceRowRegistry:
        row = Core3SourceRowRegistry(
            row_registry_id=_new_m00_row_registry_id(),
            batch_id=batch_id,
            project_id=self.project_id,
            category_code=self.category_code.value,
            source_table=source_table,
            source_pk=source_pk,
            source_pk_strategy=source_pk_strategy,
            source_row_id=source_row_id,
            row_hash=row_hash,
            hash_version=hash_version,
            previous_batch_id=previous_row.batch_id if previous_row else None,
            previous_row_hash=previous_row.row_hash if previous_row else None,
            previous_operation_type=previous_row.operation_type if previous_row else None,
            sku_code_candidate=sku_code_candidate,
            model_name_raw=model_name_raw,
            brand_raw=brand_raw,
            category_raw=category_raw,
            write_time=_coerce_datetime(write_time),
            business_key_json=_jsonable(business_key_json),
            source_field_presence_json=_jsonable(source_field_presence_json),
            operation_type=operation_type,
            change_reason=change_reason,
            affected_modules=_jsonable(list(affected_modules)),
            quality_hint=_jsonable(quality_hint),
            review_required=review_required,
            review_status=review_status,
        )
        self.db.add(row)
        return row


class SourceImpactedSkuRepository(Core3BaseRepository):
    def create_impacted_sku(
        self,
        *,
        batch_id: str,
        sku_code_candidate: str,
        model_name_raw: str | None,
        brand_raw: str | None,
        source_tables: Sequence[str],
        operation_summary_json: Mapping[str, Any],
        affected_modules: Sequence[str],
        impact_reason: str,
        impact_level: Core3SourceImpactLevel = Core3SourceImpactLevel.MEDIUM,
        review_required: bool = False,
        review_reason: Mapping[str, Any] | None = None,
    ) -> Core3SourceImpactedSku:
        impacted_sku = Core3SourceImpactedSku(
            impacted_sku_id=_new_m00_impacted_sku_id(),
            batch_id=batch_id,
            project_id=self.project_id,
            category_code=self.category_code.value,
            sku_code_candidate=sku_code_candidate,
            model_name_raw=model_name_raw,
            brand_raw=brand_raw,
            source_tables=list(source_tables),
            operation_summary_json=_jsonable(operation_summary_json),
            affected_modules=_jsonable(list(affected_modules)),
            impact_reason=impact_reason,
            impact_level=impact_level.value,
            needs_recompute=True,
            review_required=review_required,
            review_status=(
                Core3ReviewStatus.REVIEW_REQUIRED.value if review_required else Core3ReviewStatus.AUTO_PASS.value
            ),
            review_reason=dict(review_reason) if review_reason else None,
        )
        self.db.add(impacted_sku)
        self.db.flush()
        return impacted_sku


def default_source_table_configs() -> dict[str, SourceTableConfig]:
    return {
        source_table: SourceTableConfig(
            source_table=source_table,
            business_key_columns=RAW_SOURCE_BUSINESS_KEY_COLUMNS[source_table],
            hash_columns=RAW_SOURCE_HASH_COLUMNS[source_table],
        )
        for source_table in CORE3_RAW_SOURCE_TABLES
    }


def _watermark_sql(
    config: SourceTableConfig,
    columns: frozenset[str],
    *,
    raw_category_values: Sequence[str] = (),
) -> tuple[str, dict[str, Any]]:
    table_name = _quote_identifier(config.source_table)
    source_pk = _nullable_aggregate("MIN", config.source_pk_column, columns, "min_source_pk")
    max_source_pk = _nullable_aggregate("MAX", config.source_pk_column, columns, "max_source_pk")
    min_write_time = _nullable_aggregate("MIN", config.write_time_column, columns, "min_write_time")
    max_write_time = _nullable_aggregate("MAX", config.write_time_column, columns, "max_write_time")
    distinct_sku_count = (
        f"COUNT(DISTINCT {_quote_identifier(config.sku_column)}) AS distinct_sku_count"
        if config.sku_column in columns
        else "0 AS distinct_sku_count"
    )
    where_sql, params = _raw_category_where_sql(config, columns, raw_category_values)
    sql = (
        "SELECT COUNT(*) AS row_count, "
        f"{source_pk}, {max_source_pk}, {min_write_time}, {max_write_time}, {distinct_sku_count} "
        f"FROM {table_name}{where_sql}"
    )
    return sql, params


def _scan_sql(
    config: SourceTableConfig,
    columns: frozenset[str],
    scan_plan: SourceScanPlan,
    *,
    raw_category_values: Sequence[str] = (),
) -> tuple[str, dict[str, Any]]:
    table_name = _quote_identifier(config.source_table)
    ordered_columns = ", ".join(_quote_identifier(column) for column in sorted(columns))
    scan_where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if config.source_pk_column in columns:
        if scan_plan.min_source_pk is not None:
            scan_where_clauses.append(f"{_quote_identifier(config.source_pk_column)} >= :min_source_pk")
            params["min_source_pk"] = scan_plan.min_source_pk
        if scan_plan.min_source_pk_exclusive is not None:
            scan_where_clauses.append(f"{_quote_identifier(config.source_pk_column)} > :min_source_pk_exclusive")
            params["min_source_pk_exclusive"] = scan_plan.min_source_pk_exclusive
        if scan_plan.max_source_pk is not None:
            scan_where_clauses.append(f"{_quote_identifier(config.source_pk_column)} <= :max_source_pk")
            params["max_source_pk"] = scan_plan.max_source_pk

    if config.write_time_column in columns:
        if scan_plan.min_write_time_exclusive is not None:
            scan_where_clauses.append(f"{_quote_identifier(config.write_time_column)} > :min_write_time_exclusive")
            params["min_write_time_exclusive"] = scan_plan.min_write_time_exclusive
        if scan_plan.max_write_time_inclusive is not None:
            scan_where_clauses.append(f"{_quote_identifier(config.write_time_column)} <= :max_write_time_inclusive")
            params["max_write_time_inclusive"] = scan_plan.max_write_time_inclusive

    joiner = " OR " if scan_plan.combine_filters_with_or else " AND "
    where_clauses: list[str] = []
    category_where_sql, category_params = _raw_category_where_sql(config, columns, raw_category_values)
    if category_where_sql:
        where_clauses.append(category_where_sql.removeprefix(" WHERE "))
        params.update(category_params)
    if scan_where_clauses:
        scan_where_sql = joiner.join(scan_where_clauses)
        where_clauses.append(f"({scan_where_sql})" if scan_plan.combine_filters_with_or else scan_where_sql)
    where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    order_column = config.source_pk_column if config.source_pk_column in columns else sorted(columns)[0]
    limit_sql = ""
    if scan_plan.limit is not None:
        limit_sql = " LIMIT :limit OFFSET :offset"
        params["limit"] = max(scan_plan.limit, 1)
        params["offset"] = max(scan_plan.offset, 0)

    sql = f"SELECT {ordered_columns} FROM {table_name}{where_sql} ORDER BY {_quote_identifier(order_column)}{limit_sql}"
    RawSourceReadOnlyMixin.raw_source_guard.ensure_read_only_sql(sql)
    return sql, params


def _raw_category_where_sql(
    config: SourceTableConfig,
    columns: frozenset[str],
    raw_category_values: Sequence[str],
) -> tuple[str, dict[str, Any]]:
    if config.category_column not in columns or not raw_category_values:
        return "", {}
    normalized_values = tuple(str(value).strip() for value in raw_category_values if str(value).strip())
    if not normalized_values:
        return "", {}
    params = {f"raw_category_{index}": value for index, value in enumerate(normalized_values)}
    placeholders = ", ".join(f":{key}" for key in params)
    return f" WHERE {_quote_identifier(config.category_column)} IN ({placeholders})", params


def _nullable_aggregate(function_name: str, column_name: str, columns: frozenset[str], alias: str) -> str:
    if column_name not in columns:
        return f"NULL AS {alias}"
    return f"{function_name}({_quote_identifier(column_name)}) AS {alias}"


def _quote_identifier(identifier: str, *, return_unquoted: bool = False) -> str:
    if not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise ValueError(f"unsafe SQL identifier: {identifier}")
    if return_unquoted:
        return identifier
    return f'"{identifier}"'


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _chunks(values: Sequence[Any], size: int) -> Iterable[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _new_m00_batch_id(started_at: datetime) -> str:
    timestamp = started_at.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"m00_{timestamp}_{uuid4().hex[:8]}"


def _new_m00_row_registry_id() -> str:
    return f"m00rr_{uuid4().hex}"


def _new_m00_impacted_sku_id() -> str:
    return f"m00sku_{uuid4().hex}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(value: datetime | str | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    return value
