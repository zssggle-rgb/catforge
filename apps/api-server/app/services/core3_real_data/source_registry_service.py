"""M00 source row hashing, presence, operation and impact services."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.models.entities import Core3SourceBatch
from app.schemas.core3_real_data import Core3ModuleRunResultSchema, Core3SourceBatchRegisterRequest
from app.services.core3_real_data.constants import (
    CORE3_M00_ROW_HASH_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    Core3FieldPresenceStatus,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3RunStatus,
    Core3SourceBatchStatus,
    Core3SourceBatchType,
    Core3SourceImpactLevel,
    Core3SourceOperationType,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.runner import Core3ModuleTarget
from app.services.core3_real_data.run_context import Core3RunContext
from app.services.core3_real_data.source_registry_repositories import (
    RAW_SOURCE_BUSINESS_KEY_COLUMNS,
    RAW_SOURCE_HASH_COLUMNS,
    RawSourceRepository,
    SourceBatchRepository,
    SourceImpactedSkuRepository,
    SourceRowRegistryRepository,
    SourceScanPlan,
    SourceTableConfig,
    default_source_table_configs,
)


SOURCE_TABLE_AFFECTED_MODULES: dict[str, tuple[Core3ModuleCode, ...]] = {
    "week_sales_data": (
        Core3ModuleCode.M01,
        Core3ModuleCode.M02,
        Core3ModuleCode.M07,
        Core3ModuleCode.M08,
        Core3ModuleCode.M09,
        Core3ModuleCode.M10,
        Core3ModuleCode.M11,
        Core3ModuleCode.M11_5,
        Core3ModuleCode.M12,
        Core3ModuleCode.M13,
        Core3ModuleCode.M14,
        Core3ModuleCode.M15,
        Core3ModuleCode.M08_4,
        Core3ModuleCode.M08_5,
    ),
    "attribute_data": (
        Core3ModuleCode.M01,
        Core3ModuleCode.M02,
        Core3ModuleCode.M03,
        Core3ModuleCode.M04A,
        Core3ModuleCode.M08,
        Core3ModuleCode.M08_4,
        Core3ModuleCode.M08_5,
        Core3ModuleCode.M09,
        Core3ModuleCode.M10,
        Core3ModuleCode.M11,
        Core3ModuleCode.M11_5,
        Core3ModuleCode.M12,
        Core3ModuleCode.M13,
        Core3ModuleCode.M14,
        Core3ModuleCode.M15,
    ),
    "selling_points_data": (
        Core3ModuleCode.M01,
        Core3ModuleCode.M02,
        Core3ModuleCode.M04A,
        Core3ModuleCode.M04B,
        Core3ModuleCode.M08,
        Core3ModuleCode.M08_4,
        Core3ModuleCode.M08_5,
        Core3ModuleCode.M09,
        Core3ModuleCode.M10,
        Core3ModuleCode.M11,
        Core3ModuleCode.M11_5,
        Core3ModuleCode.M12,
        Core3ModuleCode.M13,
        Core3ModuleCode.M14,
        Core3ModuleCode.M15,
    ),
    "comment_data": (
        Core3ModuleCode.M01,
        Core3ModuleCode.M02,
        Core3ModuleCode.M05,
        Core3ModuleCode.M06,
        Core3ModuleCode.M04B,
        Core3ModuleCode.M08,
        Core3ModuleCode.M08_4,
        Core3ModuleCode.M08_5,
        Core3ModuleCode.M09,
        Core3ModuleCode.M10,
        Core3ModuleCode.M11,
        Core3ModuleCode.M11_5,
        Core3ModuleCode.M12,
        Core3ModuleCode.M13,
        Core3ModuleCode.M14,
        Core3ModuleCode.M15,
    ),
}

SOURCE_TABLE_IMPACT_REASON_CN: dict[str, str] = {
    "week_sales_data": "该型号本批次存在周销量价数据新增或变化，建议更新市场画像及后续竞品评分。",
    "attribute_data": "该型号本批次存在参数属性新增或变化，建议更新参数画像、卖点激活和后续竞品评分。",
    "selling_points_data": "该型号本批次存在结构化卖点新增或变化，建议更新卖点激活和评论验证。",
    "comment_data": "该型号本批次存在评论数据新增或变化，建议更新评论证据、评论信号和后续画像。",
}

M00_DEFAULT_ROW_CHUNK_SIZE = 5_000


@dataclass(frozen=True)
class PreviousSourceRow:
    batch_id: str
    row_hash: str | None
    operation_type: Core3SourceOperationType | str | None = None


@dataclass(frozen=True)
class SourceRowIdentity:
    source_table: str
    source_pk: str | None
    source_row_id: str | None
    source_pk_strategy: str = "id_column"


@dataclass(frozen=True)
class SourceOperationDecision:
    operation_type: Core3SourceOperationType
    change_reason: str
    review_required: bool = False
    quality_hint: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceRowAnalysis:
    source_table: str
    source_pk: str | None
    source_row_id: str | None
    row_hash: str | None
    source_field_presence_json: dict[str, Any]
    business_key_json: dict[str, Any]
    operation_type: Core3SourceOperationType
    change_reason: str
    affected_modules: list[dict[str, str]]
    quality_hint: dict[str, Any]
    review_required: bool
    review_status: Core3ReviewStatus


@dataclass
class ImpactedSkuDraft:
    sku_code_candidate: str
    model_name_raw: str | None = None
    brand_raw: str | None = None
    source_tables: set[str] = field(default_factory=set)
    operation_summary: dict[str, Counter[str]] = field(default_factory=dict)
    affected_modules: dict[str, str] = field(default_factory=dict)
    review_required: bool = False
    review_codes: set[str] = field(default_factory=set)


class SourceRowIdentityService:
    def __init__(self, source_table_configs: Mapping[str, SourceTableConfig] | None = None) -> None:
        self.source_table_configs = dict(source_table_configs or default_source_table_configs())

    def build_identity(self, source_table: str, raw_row: Mapping[str, Any]) -> SourceRowIdentity:
        config = self._config(source_table)
        source_pk_value = raw_row.get(config.source_pk_column)
        if _is_missing_source_pk(source_pk_value):
            return SourceRowIdentity(
                source_table=config.source_table,
                source_pk=None,
                source_row_id=None,
            )
        source_pk = str(source_pk_value)
        return SourceRowIdentity(
            source_table=config.source_table,
            source_pk=source_pk,
            source_row_id=f"{config.source_table}:{source_pk}",
        )

    def _config(self, source_table: str) -> SourceTableConfig:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        return self.source_table_configs[table_name]


class SourceFieldPresenceService:
    def __init__(self, source_table_configs: Mapping[str, SourceTableConfig] | None = None) -> None:
        self.source_table_configs = dict(source_table_configs or default_source_table_configs())

    @staticmethod
    def field_presence(raw_row: Mapping[str, Any], column_name: str) -> Core3FieldPresenceStatus:
        if column_name not in raw_row:
            return Core3FieldPresenceStatus.MISSING_COLUMN
        value = raw_row[column_name]
        if value is None:
            return Core3FieldPresenceStatus.NULL
        if isinstance(value, str):
            if value == "":
                return Core3FieldPresenceStatus.EMPTY_STRING
            if value.strip() == "-":
                return Core3FieldPresenceStatus.DASH
            if value.strip().lower() == "unknown":
                return Core3FieldPresenceStatus.UNKNOWN_LITERAL
        return Core3FieldPresenceStatus.PRESENT

    def build_field_presence(self, source_table: str, raw_row: Mapping[str, Any]) -> dict[str, Any]:
        config = self._config(source_table)
        return {
            "source_pk": self.field_presence(raw_row, config.source_pk_column),
            "model_code": self.field_presence(raw_row, config.sku_column),
            "model": self.field_presence(raw_row, config.model_column),
            "brand": self.field_presence(raw_row, config.brand_column),
            "category": self.field_presence(raw_row, config.category_column),
            "write_time": self.field_presence(raw_row, config.write_time_column),
            "business_fields": {
                column_name: self.field_presence(raw_row, column_name)
                for column_name in config.business_key_columns
            },
        }

    def build_business_key(self, source_table: str, raw_row: Mapping[str, Any]) -> dict[str, Any]:
        config = self._config(source_table)
        return {
            column_name: raw_row.get(column_name)
            for column_name in config.business_key_columns
            if column_name in raw_row
        }

    def _config(self, source_table: str) -> SourceTableConfig:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        return self.source_table_configs[table_name]


class SourceRowHashService:
    def compute_row_hash(
        self,
        source_table: str,
        raw_row: Mapping[str, Any],
        hash_version: str = CORE3_M00_ROW_HASH_VERSION,
    ) -> str:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        hash_columns = RAW_SOURCE_HASH_COLUMNS[table_name]
        payload = {
            column_name: _value_for_hash(raw_row, column_name)
            for column_name in sorted(hash_columns)
        }
        return stable_hash(
            {
                "source_table": table_name,
                "columns": payload,
            },
            version=hash_version,
        )


class SourceOperationClassifier:
    def classify(
        self,
        identity: SourceRowIdentity,
        current_row_hash: str | None,
        previous_row: PreviousSourceRow | None = None,
    ) -> SourceOperationDecision:
        if identity.source_pk is None or identity.source_row_id is None:
            return SourceOperationDecision(
                operation_type=Core3SourceOperationType.SKIPPED,
                change_reason="来源主键为空，无法稳定登记该原始行。",
                review_required=True,
                quality_hint={
                    "status": "blocked",
                    "codes": ["missing_source_pk"],
                    "review_status": Core3ReviewStatus.REVIEW_REQUIRED,
                },
            )
        if current_row_hash is None:
            return SourceOperationDecision(
                operation_type=Core3SourceOperationType.SKIPPED,
                change_reason="行 hash 为空，无法判断原始行变化。",
                review_required=True,
                quality_hint={
                    "status": "blocked",
                    "codes": ["missing_row_hash"],
                    "review_status": Core3ReviewStatus.REVIEW_REQUIRED,
                },
            )
        if previous_row is None:
            return SourceOperationDecision(
                operation_type=Core3SourceOperationType.INSERT,
                change_reason="历史批次未登记过该来源行，本批次标记为新增。",
            )
        if previous_row.row_hash == current_row_hash:
            return SourceOperationDecision(
                operation_type=Core3SourceOperationType.NO_CHANGE,
                change_reason="该来源行与上一成功批次 hash 一致，本批次标记为未变化。",
            )
        return SourceOperationDecision(
            operation_type=Core3SourceOperationType.UPDATE,
            change_reason="该来源行与上一成功批次 hash 不一致，本批次标记为变化。",
        )

    def classify_not_seen(self, previous_row: PreviousSourceRow) -> SourceOperationDecision:
        return SourceOperationDecision(
            operation_type=Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN,
            change_reason=f"上一成功批次 {previous_row.batch_id} 存在该来源行，本次全量扫描未见。",
            review_required=True,
            quality_hint={
                "status": "review",
                "codes": ["not_seen_in_current_scan"],
                "review_status": Core3ReviewStatus.REVIEW_REQUIRED,
            },
        )


class SourceRowQualityService:
    def build_quality_hint(
        self,
        identity: SourceRowIdentity,
        source_field_presence_json: Mapping[str, Any],
        operation_decision: SourceOperationDecision,
    ) -> dict[str, Any]:
        codes = list(operation_decision.quality_hint.get("codes", []))
        status = operation_decision.quality_hint.get("status", "ok")
        if identity.source_pk is None and "missing_source_pk" not in codes:
            codes.append("missing_source_pk")
            status = "blocked"
        if source_field_presence_json.get("model_code") in (
            Core3FieldPresenceStatus.NULL,
            Core3FieldPresenceStatus.EMPTY_STRING,
            Core3FieldPresenceStatus.DASH,
            Core3FieldPresenceStatus.UNKNOWN_LITERAL,
            Core3FieldPresenceStatus.MISSING_COLUMN,
        ):
            codes.append("missing_sku_code_candidate")
            if status == "ok":
                status = "review"
        if source_field_presence_json.get("write_time") in (
            Core3FieldPresenceStatus.NULL,
            Core3FieldPresenceStatus.EMPTY_STRING,
            Core3FieldPresenceStatus.DASH,
            Core3FieldPresenceStatus.UNKNOWN_LITERAL,
            Core3FieldPresenceStatus.MISSING_COLUMN,
        ):
            codes.append("missing_write_time")
            if status == "ok":
                status = "warning"
        return {
            "status": status,
            "codes": sorted(set(codes)),
        }


class SourceImpactPlanner:
    def affected_module_codes(
        self,
        source_table: str,
        operation_type: Core3SourceOperationType,
    ) -> tuple[Core3ModuleCode, ...]:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        if operation_type in (Core3SourceOperationType.NO_CHANGE, Core3SourceOperationType.SKIPPED):
            return ()
        return SOURCE_TABLE_AFFECTED_MODULES[table_name]

    def affected_modules(
        self,
        source_table: str,
        operation_type: Core3SourceOperationType,
    ) -> list[dict[str, str]]:
        table_name = RawSourceRepository.ensure_source_table_name(source_table)
        reason = SOURCE_TABLE_IMPACT_REASON_CN[table_name]
        return [
            {
                "module_code": module_code.value,
                "reason": reason,
            }
            for module_code in self.affected_module_codes(table_name, operation_type)
        ]


class SourceRowAnalyzer:
    def __init__(
        self,
        identity_service: SourceRowIdentityService | None = None,
        presence_service: SourceFieldPresenceService | None = None,
        hash_service: SourceRowHashService | None = None,
        classifier: SourceOperationClassifier | None = None,
        quality_service: SourceRowQualityService | None = None,
        impact_planner: SourceImpactPlanner | None = None,
    ) -> None:
        self.identity_service = identity_service or SourceRowIdentityService()
        self.presence_service = presence_service or SourceFieldPresenceService()
        self.hash_service = hash_service or SourceRowHashService()
        self.classifier = classifier or SourceOperationClassifier()
        self.quality_service = quality_service or SourceRowQualityService()
        self.impact_planner = impact_planner or SourceImpactPlanner()

    def analyze(
        self,
        source_table: str,
        raw_row: Mapping[str, Any],
        previous_row: PreviousSourceRow | None = None,
        hash_version: str = CORE3_M00_ROW_HASH_VERSION,
    ) -> SourceRowAnalysis:
        identity = self.identity_service.build_identity(source_table, raw_row)
        row_hash = None
        if identity.source_pk is not None:
            row_hash = self.hash_service.compute_row_hash(source_table, raw_row, hash_version=hash_version)
        field_presence = self.presence_service.build_field_presence(source_table, raw_row)
        business_key = self.presence_service.build_business_key(source_table, raw_row)
        operation_decision = self.classifier.classify(identity, row_hash, previous_row=previous_row)
        quality_hint = self.quality_service.build_quality_hint(identity, field_presence, operation_decision)
        review_required = operation_decision.review_required or quality_hint["status"] in {"blocked", "review"}
        return SourceRowAnalysis(
            source_table=identity.source_table,
            source_pk=identity.source_pk,
            source_row_id=identity.source_row_id,
            row_hash=row_hash,
            source_field_presence_json=field_presence,
            business_key_json=business_key,
            operation_type=operation_decision.operation_type,
            change_reason=operation_decision.change_reason,
            affected_modules=self.impact_planner.affected_modules(
                identity.source_table,
                operation_decision.operation_type,
            ),
            quality_hint=quality_hint,
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
        )


def _is_missing_source_pk(value: Any) -> bool:
    return value is None or value == ""


class SourceRegistryRunner:
    module_code = Core3ModuleCode.M00

    def __init__(
        self,
        db: Session,
        row_analyzer: SourceRowAnalyzer | None = None,
        row_chunk_size: int = M00_DEFAULT_ROW_CHUNK_SIZE,
    ) -> None:
        self.db = db
        self.row_analyzer = row_analyzer or SourceRowAnalyzer()
        self.row_chunk_size = max(int(row_chunk_size), 1)

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        request = Core3SourceBatchRegisterRequest(
            project_id=context.project_id,
            category_code=context.category_code,
            run_id=context.run_id,
            batch_type=target.metadata.get("batch_type", Core3SourceBatchType.FULL),
            source_tables=target.metadata.get("source_tables") or list(CORE3_RAW_SOURCE_TABLES),
            ruleset_version=context.ruleset_version,
            module_version=context.module_versions.get(Core3ModuleCode.M00.value, "m00-source-registry-0.1.0"),
            hash_version=context.input_watermarks.get("hash_version", CORE3_M00_ROW_HASH_VERSION),
            triggered_by=context.triggered_by,
        )
        return self.register_batch(request)

    def register_batch(self, request: Core3SourceBatchRegisterRequest) -> Core3ModuleRunResultSchema:
        context = Core3RepositoryContext(
            db=self.db,
            project_id=request.project_id,
            category_code=request.category_code,
        )
        raw_repository = RawSourceRepository(context)
        batch_repository = SourceBatchRepository(context)
        row_repository = SourceRowRegistryRepository(context)
        impacted_sku_repository = SourceImpactedSkuRepository(context)

        requested_batch_type = Core3SourceBatchType(request.batch_type)
        previous_success_batch = batch_repository.find_latest_successful_batch(
            source_system=request.source_system,
            source_database=request.source_database,
            source_schema=request.source_schema,
            hash_version=request.hash_version,
        )
        effective_batch_type = (
            Core3SourceBatchType.FULL
            if requested_batch_type == Core3SourceBatchType.INCREMENTAL and previous_success_batch is None
            else requested_batch_type
        )
        batch_request = (
            request.model_copy(update={"batch_type": effective_batch_type.value})
            if effective_batch_type != requested_batch_type
            else request
        )

        scan_started_at = datetime.now(timezone.utc)
        batch = batch_repository.create_running_batch(batch_request, scan_started_at=scan_started_at)
        batch_id = batch.batch_id
        schema_snapshot_json: dict[str, Any] = {}
        input_watermark_json: dict[str, Any] = {}
        row_counts_json: dict[str, dict[str, int]] = {}
        write_time_range_json: dict[str, Any] = {}
        source_pk_range_json: dict[str, Any] = {}
        affected_module_summary: dict[str, dict[str, Any]] = {}
        impacted_skus: dict[str, ImpactedSkuDraft] = {}
        source_table_watermarks: dict[str, Any] = {}
        quality_counter: Counter[str] = Counter()
        total_input_count = 0
        total_changed_input_count = 0
        total_output_count = 0
        review_required = False
        total_chunk_count = 0

        try:
            self.db.commit()
            for source_table in batch_request.source_tables:
                snapshot = raw_repository.inspect_table(source_table)
                watermark = raw_repository.get_table_watermark(source_table)
                previous_state = _previous_table_state(previous_success_batch, source_table)
                scan_plans = _build_scan_plans(
                    source_table=source_table,
                    batch_type=effective_batch_type,
                    previous_state=previous_state,
                )
                source_table_watermarks[source_table] = watermark
                schema_snapshot_json[source_table] = snapshot.to_json()
                input_watermark_json[source_table] = {
                    "requested_batch_type": requested_batch_type.value,
                    "scan_mode": effective_batch_type.value,
                    "previous_success_batch_id": previous_success_batch.batch_id if previous_success_batch else None,
                    "previous_max_id": previous_state["previous_max_id"],
                    "previous_max_write_time": previous_state["previous_max_write_time"],
                    "current_min_id": watermark.min_source_pk,
                    "current_max_id": watermark.max_source_pk,
                    "current_min_write_time": _datetime_to_iso(watermark.min_write_time),
                    "current_max_write_time": _datetime_to_iso(watermark.max_write_time),
                    "candidate_rule": _candidate_rule(scan_plans, previous_state),
                    "scan_plan_count": len(scan_plans),
                    "row_chunk_size": self.row_chunk_size,
                    "fallback_reason": (
                        "no_previous_success_batch"
                        if requested_batch_type == Core3SourceBatchType.INCREMENTAL and previous_success_batch is None
                        else None
                    ),
                    "overlap_window_hours": None,
                }
                write_time_range_json[source_table] = {
                    "min_write_time": _datetime_to_iso(watermark.min_write_time),
                    "max_write_time": _datetime_to_iso(watermark.max_write_time),
                }
                source_pk_range_json[source_table] = {
                    "min_source_pk": watermark.min_source_pk,
                    "max_source_pk": watermark.max_source_pk,
                }
                table_counts: Counter[str] = Counter()
                schema_quality_codes = _table_schema_quality_codes(snapshot, previous_state)
                for quality_code in schema_quality_codes:
                    quality_counter[quality_code] += 1
                    review_required = True
                if _write_time_watermark_regressed(watermark.max_write_time, previous_state):
                    quality_counter["write_time_watermark_regressed"] += 1

                table_chunk_count = 0
                for scan_plan in scan_plans:
                    should_lookup_previous = _scan_plan_requires_previous_lookup(
                        scan_plan,
                        previous_state=previous_state,
                        previous_success_batch=previous_success_batch,
                    )
                    for raw_rows in raw_repository.iter_row_chunks(
                        source_table,
                        scan_plan,
                        chunk_size=self.row_chunk_size,
                    ):
                        previous_rows_by_source: dict[str, Any] = {}
                        if should_lookup_previous:
                            previous_rows_by_source = row_repository.find_latest_by_sources(
                                source_table=source_table,
                                source_pks=[
                                    str(raw_row.get("id"))
                                    for raw_row in raw_rows
                                    if raw_row.get("id") not in (None, "")
                                ],
                                hash_version=request.hash_version,
                            )

                        for raw_row in raw_rows:
                            total_input_count += 1
                            source_pk_value = raw_row.get("id")
                            previous_row = (
                                previous_rows_by_source.get(str(source_pk_value))
                                if source_pk_value not in (None, "")
                                else None
                            )
                            analysis = self.row_analyzer.analyze(
                                source_table,
                                raw_row,
                                previous_row=_previous_source_row(previous_row),
                                hash_version=request.hash_version,
                            )
                            row_repository.create_row_registry(
                                batch_id=batch_id,
                                source_table=analysis.source_table,
                                source_pk=analysis.source_pk,
                                source_pk_strategy="id_column",
                                source_row_id=analysis.source_row_id,
                                row_hash=analysis.row_hash,
                                hash_version=request.hash_version,
                                previous_row=previous_row,
                                sku_code_candidate=_string_or_none(raw_row.get("model_code")),
                                model_name_raw=_string_or_none(raw_row.get("model")),
                                brand_raw=_string_or_none(raw_row.get("brand")),
                                category_raw=_string_or_none(raw_row.get("category")),
                                write_time=raw_row.get("write_time"),
                                business_key_json=analysis.business_key_json,
                                source_field_presence_json=analysis.source_field_presence_json,
                                operation_type=analysis.operation_type.value,
                                change_reason=analysis.change_reason,
                                affected_modules=analysis.affected_modules,
                                quality_hint=analysis.quality_hint,
                                review_required=analysis.review_required,
                                review_status=analysis.review_status.value,
                            )
                            table_counts["scanned"] += 1
                            table_counts["registered"] += 1
                            table_counts[analysis.operation_type.value] += 1
                            if analysis.operation_type in (
                                Core3SourceOperationType.INSERT,
                                Core3SourceOperationType.UPDATE,
                                Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN,
                            ):
                                total_changed_input_count += 1
                                _accumulate_impacted_sku(impacted_skus, raw_row, analysis)
                            if analysis.operation_type != Core3SourceOperationType.SKIPPED:
                                total_output_count += 1
                            for quality_code in analysis.quality_hint.get("codes", []):
                                quality_counter[quality_code] += 1
                            if analysis.review_required:
                                review_required = True
                            _accumulate_affected_module_summary(
                                affected_module_summary,
                                source_table,
                                analysis.affected_modules,
                            )

                        table_chunk_count += 1
                        total_chunk_count += 1
                        self.db.flush()
                        self.db.commit()

                row_counts_json[source_table] = _row_count_payload(table_counts)
                input_watermark_json[source_table]["processed_chunk_count"] = table_chunk_count

            for quality_code in _cross_table_quality_codes(source_table_watermarks):
                quality_counter[quality_code] += 1

            impacted_sku_count = _write_impacted_skus(
                impacted_sku_repository,
                batch_id=batch.batch_id,
                impacted_skus=impacted_skus,
            )
            status = (
                Core3SourceBatchStatus.REGISTERED_WITH_WARNING
                if review_required or quality_counter
                else Core3SourceBatchStatus.REGISTERED
            )
            quality_summary_json = _quality_summary(review_required, quality_counter)
            batch_repository.finish_batch(
                batch,
                status=status,
                schema_snapshot_json=schema_snapshot_json,
                input_watermark_json=input_watermark_json,
                row_counts_json=row_counts_json,
                write_time_range_json=write_time_range_json,
                source_pk_range_json=source_pk_range_json,
                affected_module_summary_json=affected_module_summary,
                quality_summary_json=quality_summary_json,
                impacted_sku_count=impacted_sku_count,
                review_required=review_required,
                review_reason={"codes": sorted(quality_counter)} if review_required else None,
            )
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            failed_batch = self.db.get(Core3SourceBatch, batch_id)
            if failed_batch is not None:
                batch_repository.mark_failed(
                    failed_batch,
                    error_code="m00_source_registration_failed",
                    error_message=str(exc),
                )
                self.db.commit()
            raise

        summary_json = {
            "batch_id": batch.batch_id,
            "batch_status": batch.status,
            "requested_batch_type": requested_batch_type.value,
            "effective_batch_type": effective_batch_type.value,
            "source_tables": list(batch_request.source_tables),
            "row_counts": row_counts_json,
            "affected_module_summary": affected_module_summary,
            "quality_summary": batch.quality_summary_json,
            "impacted_sku_count": batch.impacted_sku_count,
            "impacted_sku_aggregation_deferred": False,
            "processed_chunk_count": total_chunk_count,
            "row_chunk_size": self.row_chunk_size,
        }
        return Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M00,
            status=Core3RunStatus.WARNING if quality_counter else Core3RunStatus.SUCCESS,
            input_count=total_input_count,
            changed_input_count=total_changed_input_count,
            output_count=total_output_count,
            output_hash=stable_hash(summary_json, version="m00_source_registry_summary_v1"),
            warnings=sorted(quality_counter),
            review_issues=[],
            downstream_impacts=[],
            summary_json=summary_json,
            started_at=scan_started_at,
            finished_at=batch.scan_finished_at,
        )


def _value_for_hash(raw_row: Mapping[str, Any], column_name: str) -> Any:
    if column_name not in raw_row:
        return {"__m00_presence": Core3FieldPresenceStatus.MISSING_COLUMN}
    return raw_row[column_name]


def _previous_source_row(row: Any | None) -> PreviousSourceRow | None:
    if row is None:
        return None
    return PreviousSourceRow(
        batch_id=row.batch_id,
        row_hash=row.row_hash,
        operation_type=row.operation_type,
    )


def _previous_table_state(previous_batch: Any | None, source_table: str) -> dict[str, Any]:
    if previous_batch is None:
        return {
            "previous_max_id": None,
            "previous_max_write_time": None,
            "previous_schema_hash": None,
            "previous_row_count": None,
        }
    input_watermark = (previous_batch.input_watermark_json or {}).get(source_table, {})
    source_pk_range = (previous_batch.source_pk_range_json or {}).get(source_table, {})
    write_time_range = (previous_batch.write_time_range_json or {}).get(source_table, {})
    schema_snapshot = (previous_batch.schema_snapshot_json or {}).get(source_table, {})
    row_counts = (previous_batch.row_counts_json or {}).get(source_table, {})
    return {
        "previous_max_id": input_watermark.get("current_max_id") or source_pk_range.get("max_source_pk"),
        "previous_max_write_time": (
            input_watermark.get("current_max_write_time") or write_time_range.get("max_write_time")
        ),
        "previous_schema_hash": schema_snapshot.get("schema_hash"),
        "previous_row_count": row_counts.get("scanned"),
    }


def _build_scan_plans(
    *,
    source_table: str,
    batch_type: Core3SourceBatchType,
    previous_state: Mapping[str, Any],
) -> tuple[SourceScanPlan, ...]:
    if batch_type == Core3SourceBatchType.FULL:
        return (SourceScanPlan(source_table=source_table, batch_type=Core3SourceBatchType.FULL),)

    previous_max_write_time = _parse_datetime(previous_state.get("previous_max_write_time"))
    min_source_pk_exclusive = _string_or_none(previous_state.get("previous_max_id"))
    plans: list[SourceScanPlan] = []
    if min_source_pk_exclusive:
        plans.append(
            SourceScanPlan(
                source_table=source_table,
                batch_type=Core3SourceBatchType.INCREMENTAL,
                min_source_pk_exclusive=min_source_pk_exclusive,
            )
        )
    if previous_max_write_time:
        plans.append(
            SourceScanPlan(
                source_table=source_table,
                batch_type=Core3SourceBatchType.INCREMENTAL,
                max_source_pk=min_source_pk_exclusive,
                min_write_time_exclusive=previous_max_write_time,
            )
        )
    if plans:
        return tuple(plans)
    return (SourceScanPlan(source_table=source_table, batch_type=Core3SourceBatchType.INCREMENTAL),)


def _candidate_rule(scan_plans: tuple[SourceScanPlan, ...], previous_state: Mapping[str, Any]) -> str:
    scan_plan = scan_plans[0] if scan_plans else SourceScanPlan(source_table="", batch_type=Core3SourceBatchType.FULL)
    if scan_plan.batch_type == Core3SourceBatchType.FULL:
        if previous_state.get("previous_max_id") is None and previous_state.get("previous_max_write_time") is None:
            return "full_table_scan"
        return "explicit_full_table_scan"
    if _has_incremental_new_id_plan(scan_plans) and _has_incremental_existing_write_time_plan(scan_plans):
        return "incremental_id_watermark_and_existing_write_time"
    if scan_plan.min_source_pk_exclusive:
        return "incremental_id_watermark"
    if scan_plan.min_write_time_exclusive:
        return "incremental_write_time_watermark"
    return "incremental_no_watermark_full_scan"


def _has_incremental_new_id_plan(scan_plans: tuple[SourceScanPlan, ...]) -> bool:
    return any(
        scan_plan.batch_type == Core3SourceBatchType.INCREMENTAL
        and scan_plan.min_source_pk_exclusive
        and scan_plan.max_source_pk is None
        and scan_plan.min_write_time_exclusive is None
        for scan_plan in scan_plans
    )


def _has_incremental_existing_write_time_plan(scan_plans: tuple[SourceScanPlan, ...]) -> bool:
    return any(
        scan_plan.batch_type == Core3SourceBatchType.INCREMENTAL
        and scan_plan.max_source_pk is not None
        and scan_plan.min_write_time_exclusive is not None
        for scan_plan in scan_plans
    )


def _scan_plan_requires_previous_lookup(
    scan_plan: SourceScanPlan,
    *,
    previous_state: Mapping[str, Any],
    previous_success_batch: Any | None,
) -> bool:
    if previous_success_batch is None:
        return False
    previous_max_id = _string_or_none(previous_state.get("previous_max_id"))
    if (
        previous_max_id
        and scan_plan.min_source_pk_exclusive == previous_max_id
        and scan_plan.max_source_pk is None
        and scan_plan.min_write_time_exclusive is None
    ):
        return False
    return True


def _table_schema_quality_codes(snapshot: Any, previous_state: Mapping[str, Any]) -> list[str]:
    previous_schema_hash = previous_state.get("previous_schema_hash")
    if previous_schema_hash and previous_schema_hash != snapshot.schema_hash:
        return ["source_schema_changed"]
    return []


def _write_time_watermark_regressed(current_max_write_time: Any, previous_state: Mapping[str, Any]) -> bool:
    previous_max_write_time = _parse_datetime(previous_state.get("previous_max_write_time"))
    current_max = _parse_datetime(current_max_write_time)
    return bool(current_max and previous_max_write_time and current_max < previous_max_write_time)


def _cross_table_quality_codes(source_table_watermarks: Mapping[str, Any]) -> list[str]:
    week_sales = source_table_watermarks.get("week_sales_data")
    selling_points = source_table_watermarks.get("selling_points_data")
    if not week_sales or not selling_points or week_sales.distinct_sku_count <= 0:
        return []
    coverage_ratio = selling_points.distinct_sku_count / week_sales.distinct_sku_count
    if coverage_ratio < 0.3:
        return ["selling_points_sparse_coverage"]
    return []


def _accumulate_impacted_sku(
    impacted_skus: dict[str, ImpactedSkuDraft],
    raw_row: Mapping[str, Any],
    analysis: SourceRowAnalysis,
) -> None:
    sku_code_candidate = _string_or_none(raw_row.get("model_code"))
    if not sku_code_candidate:
        return

    draft = impacted_skus.setdefault(
        sku_code_candidate,
        ImpactedSkuDraft(
            sku_code_candidate=sku_code_candidate,
            model_name_raw=_string_or_none(raw_row.get("model")),
            brand_raw=_string_or_none(raw_row.get("brand")),
        ),
    )
    if draft.model_name_raw is None:
        draft.model_name_raw = _string_or_none(raw_row.get("model"))
    if draft.brand_raw is None:
        draft.brand_raw = _string_or_none(raw_row.get("brand"))
    draft.source_tables.add(analysis.source_table)
    table_summary = draft.operation_summary.setdefault(analysis.source_table, Counter())
    table_summary[analysis.operation_type.value] += 1
    table_summary["changed_rows"] += 1
    for affected_module in analysis.affected_modules:
        draft.affected_modules[affected_module["module_code"]] = affected_module["reason"]
    if analysis.review_required:
        draft.review_required = True
        draft.review_codes.update(analysis.quality_hint.get("codes", []))


def _write_impacted_skus(
    impacted_sku_repository: SourceImpactedSkuRepository,
    *,
    batch_id: str,
    impacted_skus: Mapping[str, ImpactedSkuDraft],
) -> int:
    for sku_code_candidate, draft in sorted(impacted_skus.items()):
        operation_summary_json = {
            "total_changed_rows": sum(counter["changed_rows"] for counter in draft.operation_summary.values()),
            "by_source_table": {
                source_table: dict(sorted(counter.items()))
                for source_table, counter in sorted(draft.operation_summary.items())
            },
        }
        affected_module_codes = sorted(draft.affected_modules)
        source_tables = sorted(draft.source_tables)
        impacted_sku_repository.create_impacted_sku(
            batch_id=batch_id,
            sku_code_candidate=sku_code_candidate,
            model_name_raw=draft.model_name_raw,
            brand_raw=draft.brand_raw,
            source_tables=source_tables,
            operation_summary_json=operation_summary_json,
            affected_modules=affected_module_codes,
            impact_reason=_impacted_sku_reason(source_tables, affected_module_codes),
            impact_level=(
                Core3SourceImpactLevel.HIGH if draft.review_required else Core3SourceImpactLevel.MEDIUM
            ),
            review_required=draft.review_required,
            review_reason={"codes": sorted(draft.review_codes)} if draft.review_codes else None,
        )
    return len(impacted_skus)


def _impacted_sku_reason(source_tables: list[str], affected_module_codes: list[str]) -> str:
    return (
        "本批次原始数据在 "
        + "、".join(source_tables)
        + " 存在新增或变化，需重算 "
        + "、".join(affected_module_codes)
        + " 相关链路。"
    )


def _row_count_payload(table_counts: Counter[str]) -> dict[str, int]:
    return {
        "scanned": table_counts["scanned"],
        "registered": table_counts["registered"],
        "insert": table_counts[Core3SourceOperationType.INSERT.value],
        "update": table_counts[Core3SourceOperationType.UPDATE.value],
        "no_change": table_counts[Core3SourceOperationType.NO_CHANGE.value],
        "not_seen_in_current_scan": table_counts[Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN.value],
        "skipped": table_counts[Core3SourceOperationType.SKIPPED.value],
    }


def _quality_summary(review_required: bool, quality_counter: Counter[str]) -> dict[str, Any]:
    if not quality_counter:
        return {
            "status": "ok",
            "warnings": [],
            "review_required": review_required,
            "code_counts": {},
        }
    return {
        "status": "review" if review_required else "warning",
        "warnings": [
            {"code": code, "count": count}
            for code, count in sorted(quality_counter.items())
        ],
        "review_required": review_required,
        "code_counts": dict(sorted(quality_counter.items())),
    }


def _accumulate_affected_module_summary(
    summary: dict[str, dict[str, Any]],
    source_table: str,
    affected_modules: list[dict[str, str]],
) -> None:
    for affected_module in affected_modules:
        module_code = affected_module["module_code"]
        item = summary.setdefault(module_code, {"row_count": 0, "source_tables": []})
        item["row_count"] += 1
        if source_table not in item["source_tables"]:
            item["source_tables"].append(source_table)


def _datetime_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
