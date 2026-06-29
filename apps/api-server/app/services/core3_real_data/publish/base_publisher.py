"""Publish CatForge analysis summaries to the XiaoAo Feishu Base workbench."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.services.core3_real_data.publish.base_client import BaseClient, LarkCliBaseClient
from app.services.core3_real_data.publish.base_schema import ANALYSIS_BATCH, SYNC_SCOPES, table_definition
from app.services.core3_real_data.publish.base_schema_manager import BaseSchemaManager, SchemaEnsureResult
from app.services.core3_real_data.publish.extractors import PublishExtractors
from app.services.core3_real_data.publish.mappers import BaseRecordMapper
from app.services.core3_real_data.publish.schemas import PublishResult, ScopeSyncResult
from app.services.core3_real_data.publish.sync_state import BaseWorkbenchConfig, load_base_workbench_config


class BaseWorkbenchPublisher:
    def __init__(
        self,
        db: Session,
        *,
        project_id: str,
        category_code: str,
        product_category: str = "tv",
        market_window: str = "full_observed_window",
        analysis_population: str = "fact_complete_with_comment",
        claim_analysis_population: str = "claim_value_ready_with_comment",
        config: BaseWorkbenchConfig | None = None,
        client: BaseClient | None = None,
        extractor: PublishExtractors | None = None,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.category_code = category_code.upper()
        self.product_category = product_category
        self.market_window = market_window
        self.analysis_population = analysis_population
        self.claim_analysis_population = claim_analysis_population
        self.config = config or load_base_workbench_config()
        self.client = client or LarkCliBaseClient(cli_bin=self.config.cli_bin)
        self.extractor = extractor or PublishExtractors(
            db,
            project_id=project_id,
            category_code=self.category_code,
            product_category=product_category,
            market_window=market_window,
            analysis_population=analysis_population,
            claim_analysis_population=claim_analysis_population,
        )
        self.mapper = BaseRecordMapper()

    @property
    def base_url(self) -> str | None:
        return base_url(self.config.base_token)

    def init_base(self, *, base_name: str, base_token: str | None = None) -> PublishResult:
        manager = BaseSchemaManager(self.client, actor=self.config.actor)
        result = manager.init_workbench(
            base_name=base_name,
            base_token=base_token or self.config.base_token,
            table_map=self.config.table_map,
        )
        self.config = replace(self.config, base_token=result.base_token, table_map=result.table_map)
        message = "已初始化小奥家电市场分析工作台。"
        if result.permission_note:
            message = f"{message} 权限提示：{result.permission_note}"
        return PublishResult(
            status="ok",
            category_code=self.category_code,
            batch_id="",
            base_url=base_url(result.base_token),
            message_cn=message,
            scopes=[
                ScopeSyncResult(
                    scope="schema",
                    status="ok",
                    created_count=len(result.created_tables),
                    updated_count=len(result.created_fields),
                    message_cn=f"表：{len(result.table_map)}；新增表：{len(result.created_tables)}；新增字段：{len(result.created_fields)}",
                )
            ],
        )

    def sync_scope(
        self,
        *,
        scope: str,
        batch_id: str,
        dry_run: bool = False,
        limit: int | None = None,
        allow_schema_update: bool = False,
    ) -> ScopeSyncResult:
        table = table_definition(scope)
        resolved_batch_id = self.extractor.resolve_batch_id(batch_id)
        records = self.extractor.extract(scope, batch_id=resolved_batch_id, limit=limit)
        if dry_run:
            return ScopeSyncResult(
                scope=scope,
                status="dry_run",
                extracted_count=len(records),
                table_name=table.table_name,
                message_cn=f"将同步 {len(records)} 行到 {table.table_name}，未写入飞书。",
            )
        ensure_result = self._ensure_target(allow_schema_update=allow_schema_update)
        table_id = ensure_result.table_map.get(scope)
        if not table_id:
            raise RuntimeError(f"工作台缺少表映射：{scope}。")
        mapped_records = self.mapper.map_records(table, records)
        _ensure_unique(mapped_records)
        existing = self._existing_unique_key_index(base_token=ensure_result.base_token, table_id=table_id)
        created = 0
        updated = 0
        for mapped in mapped_records:
            unique_key = str(mapped.get("unique_key") or "")
            record_id = existing.get(unique_key)
            payload = {key: value for key, value in mapped.items() if value is not None}
            result = self.client.upsert_record(
                base_token=ensure_result.base_token,
                table_id=table_id,
                fields=payload,
                record_id=record_id,
                actor=self.config.actor,
            )
            if record_id:
                updated += 1
            else:
                created += 1
                new_record_id = _record_id(result)
                if new_record_id:
                    existing[unique_key] = new_record_id
        return ScopeSyncResult(
            scope=scope,
            status="ok",
            extracted_count=len(records),
            created_count=created,
            updated_count=updated,
            table_name=table.table_name,
            table_id=table_id,
            message_cn=f"{table.table_name} 同步完成：新增 {created} 行，更新 {updated} 行。",
        )

    def sync_all(
        self,
        *,
        batch_id: str,
        dry_run: bool = False,
        limit: int | None = None,
        allow_schema_update: bool = False,
    ) -> PublishResult:
        resolved_batch_id = self.extractor.resolve_batch_id(batch_id)
        scopes: list[ScopeSyncResult] = []
        status = "ok"
        message = "已同步小奥家电市场分析工作台。"
        for scope in SYNC_SCOPES:
            try:
                scopes.append(
                    self.sync_scope(
                        scope=scope,
                        batch_id=resolved_batch_id,
                        dry_run=dry_run,
                        limit=limit,
                        allow_schema_update=allow_schema_update,
                    )
                )
            except Exception as exc:
                status = "failed"
                message = f"{scope} 同步失败：{exc}"
                scopes.append(ScopeSyncResult(scope=scope, status="failed", message_cn=str(exc)))
                break
        if not dry_run and status == "ok":
            try:
                scopes.append(
                    self._sync_final_batch_status(
                        batch_id=resolved_batch_id,
                        scope_results=scopes,
                        allow_schema_update=allow_schema_update,
                    )
                )
            except Exception as exc:
                status = "failed"
                message = f"分析批次最终状态更新失败：{exc}"
                scopes.append(ScopeSyncResult(scope=ANALYSIS_BATCH, status="failed", message_cn=str(exc)))
        return PublishResult(
            status=status,
            category_code=self.category_code,
            batch_id=resolved_batch_id,
            base_url=self.base_url,
            scopes=scopes,
            message_cn=message,
        )

    def status(self) -> PublishResult:
        configured = bool(self.config.base_token)
        scopes: list[ScopeSyncResult] = []
        if configured:
            ensure_result = self._ensure_target(allow_schema_update=False)
            for scope in SYNC_SCOPES:
                table = table_definition(scope)
                scopes.append(
                    ScopeSyncResult(
                        scope=scope,
                        status="configured" if ensure_result.table_map.get(scope) else "missing",
                        table_name=table.table_name,
                        table_id=ensure_result.table_map.get(scope),
                    )
                )
        return PublishResult(
            status="ok" if configured else "blocked",
            category_code=self.category_code,
            batch_id="",
            base_url=self.base_url,
            scopes=scopes,
            message_cn="工作台已配置。" if configured else "缺少 CATFORGE_BASE_WORKBENCH_TOKEN，请先执行 base init 或配置 token。",
        )

    def open(self) -> PublishResult:
        if not self.config.base_token:
            return PublishResult(
                status="blocked",
                category_code=self.category_code,
                batch_id="",
                message_cn="缺少 CATFORGE_BASE_WORKBENCH_TOKEN，无法打开工作台。",
            )
        return PublishResult(
            status="ok",
            category_code=self.category_code,
            batch_id="",
            base_url=self.base_url,
            message_cn="工作台链接已生成。",
        )

    def _sync_final_batch_status(
        self,
        *,
        batch_id: str,
        scope_results: list[ScopeSyncResult],
        allow_schema_update: bool,
    ) -> ScopeSyncResult:
        records = self.extractor.extract_analysis_batch(batch_id=batch_id)
        if records:
            records[0]["sync_status"] = "成功"
            records[0]["note_cn"] = "；".join(result.message_cn or result.scope for result in scope_results if result.status == "ok")[:800]
        table = table_definition(ANALYSIS_BATCH)
        ensure_result = self._ensure_target(allow_schema_update=allow_schema_update)
        table_id = ensure_result.table_map[ANALYSIS_BATCH]
        mapped = self.mapper.map_record(table, records[0])
        existing = self._existing_unique_key_index(base_token=ensure_result.base_token, table_id=table_id)
        record_id = existing.get(str(mapped.get("unique_key") or ""))
        self.client.upsert_record(
            base_token=ensure_result.base_token,
            table_id=table_id,
            fields={key: value for key, value in mapped.items() if value is not None},
            record_id=record_id,
            actor=self.config.actor,
        )
        return ScopeSyncResult(
            scope=ANALYSIS_BATCH,
            status="ok",
            extracted_count=1,
            updated_count=1 if record_id else 0,
            created_count=0 if record_id else 1,
            table_name=table.table_name,
            table_id=table_id,
            message_cn="分析批次最终状态已更新为成功。",
        )

    def _ensure_target(self, *, allow_schema_update: bool) -> SchemaEnsureResult:
        if not self.config.base_token:
            raise RuntimeError("缺少 CATFORGE_BASE_WORKBENCH_TOKEN，请先执行 base init 或配置工作台 Base token。")
        manager = BaseSchemaManager(self.client, actor=self.config.actor)
        result = manager.ensure_tables_and_fields(
            self.config.base_token,
            self.config.table_map,
            allow_schema_update=allow_schema_update,
        )
        self.config = replace(self.config, table_map=result.table_map)
        return result

    def _existing_unique_key_index(self, *, base_token: str, table_id: str) -> dict[str, str]:
        existing: dict[str, str] = {}
        offset = 0
        limit = self.config.normalized_chunk_size
        while True:
            rows = self.client.list_records(
                base_token=base_token,
                table_id=table_id,
                field_names=["unique_key"],
                actor=self.config.actor,
                limit=limit,
                offset=offset,
            )
            for row in rows:
                record_id = _record_id(row)
                fields = row.get("fields") if isinstance(row, dict) else None
                if not record_id or not isinstance(fields, dict):
                    continue
                unique_key = fields.get("unique_key")
                if unique_key:
                    existing[str(unique_key)] = record_id
            if len(rows) < limit:
                break
            offset += limit
        return existing


def base_url(base_token: str | None) -> str | None:
    return f"https://my.feishu.cn/base/{base_token}" if base_token else None


def _ensure_unique(records: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for record in records:
        unique_key = str(record.get("unique_key") or "")
        if unique_key in seen:
            duplicates.add(unique_key)
        seen.add(unique_key)
    if duplicates:
        sample = "、".join(sorted(duplicates)[:5])
        raise RuntimeError(f"发布数据存在重复 unique_key：{sample}")


def _record_id(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("record_id", "id"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    record = payload.get("record")
    if isinstance(record, dict):
        return _record_id(record)
    return None
