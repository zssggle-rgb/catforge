"""Schema initialization and validation for the Feishu Base workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.core3_real_data.publish.base_client import BaseClient
from app.services.core3_real_data.publish.base_schema import ANALYSIS_BATCH, WORKBENCH_TABLES
from app.services.core3_real_data.publish.schemas import BaseTableDefinition
from app.services.core3_real_data.publish.sync_state import extract_base_token, extract_table_id


@dataclass
class SchemaEnsureResult:
    base_token: str
    table_map: dict[str, str] = field(default_factory=dict)
    created_tables: list[str] = field(default_factory=list)
    created_fields: list[str] = field(default_factory=list)
    created_views: list[str] = field(default_factory=list)
    permission_note: str | None = None


class BaseSchemaManager:
    def __init__(self, client: BaseClient, *, actor: str = "user") -> None:
        self.client = client
        self.actor = actor

    def init_workbench(self, *, base_name: str, base_token: str | None = None, table_map: dict[str, str] | None = None) -> SchemaEnsureResult:
        table_map = dict(table_map or {})
        result = SchemaEnsureResult(base_token=base_token or "", table_map=table_map)
        if not result.base_token:
            first_table = WORKBENCH_TABLES[ANALYSIS_BATCH]
            payload = self.client.create_base(
                name=base_name,
                table_name=first_table.table_name,
                fields=[field.to_lark_json() for field in first_table.fields],
                actor=self.actor,
            )
            token = extract_base_token(payload)
            if not token:
                raise RuntimeError("飞书 Base 创建成功但返回中没有 base token。")
            result.base_token = token
            first_table_id = extract_table_id(payload, table_name=first_table.table_name)
            if first_table_id:
                result.table_map[first_table.scope] = first_table_id
                result.created_tables.append(first_table.table_name)
            permission_grant = payload.get("permission_grant")
            if permission_grant:
                result.permission_note = str(permission_grant)
        self.ensure_tables_and_fields(result.base_token, result.table_map, allow_schema_update=True, result=result)
        return result

    def ensure_tables_and_fields(
        self,
        base_token: str,
        table_map: dict[str, str],
        *,
        allow_schema_update: bool,
        result: SchemaEnsureResult | None = None,
    ) -> SchemaEnsureResult:
        ensure_result = result or SchemaEnsureResult(base_token=base_token, table_map=dict(table_map))
        existing_tables = self._table_name_map(base_token)
        for scope, table in WORKBENCH_TABLES.items():
            table_id = ensure_result.table_map.get(scope) or _table_id_by_name(existing_tables, table.table_name)
            if not table_id:
                if not allow_schema_update:
                    raise RuntimeError(f"工作台缺少表：{table.table_name}。请先执行 base init 或加 --allow-schema-update。")
                payload = self.client.create_table(
                    base_token=base_token,
                    name=table.table_name,
                    fields=[field.to_lark_json() for field in table.fields],
                    actor=self.actor,
                )
                table_id = extract_table_id(payload, table_name=table.table_name)
                if not table_id:
                    table_id = _table_id_by_name(self._table_name_map(base_token), table.table_name)
                if not table_id:
                    raise RuntimeError(f"创建表 {table.table_name} 后未能解析 table_id。")
                ensure_result.created_tables.append(table.table_name)
            ensure_result.table_map[scope] = table_id
            self._ensure_fields(base_token, table_id, table, allow_schema_update=allow_schema_update, result=ensure_result)
            self._ensure_views(base_token, table_id, table, allow_schema_update=allow_schema_update, result=ensure_result)
        return ensure_result

    def _ensure_fields(
        self,
        base_token: str,
        table_id: str,
        table: BaseTableDefinition,
        *,
        allow_schema_update: bool,
        result: SchemaEnsureResult,
    ) -> None:
        existing_names = {str(field.get("name") or field.get("field_name") or "") for field in self.client.list_fields(base_token=base_token, table_id=table_id, actor=self.actor)}
        missing = [field for field in table.fields if field.name not in existing_names]
        if missing and not allow_schema_update:
            names = "、".join(field.name for field in missing)
            raise RuntimeError(f"{table.table_name} 缺少字段：{names}。")
        for field in missing:
            self.client.create_field(base_token=base_token, table_id=table_id, field=field.to_lark_json(), actor=self.actor)
            result.created_fields.append(f"{table.table_name}.{field.name}")

    def _ensure_views(
        self,
        base_token: str,
        table_id: str,
        table: BaseTableDefinition,
        *,
        allow_schema_update: bool,
        result: SchemaEnsureResult,
    ) -> None:
        if not allow_schema_update:
            return
        existing_names = {str(view.get("name") or view.get("view_name") or "") for view in self.client.list_views(base_token=base_token, table_id=table_id, actor=self.actor)}
        for view in table.views:
            if view.name in existing_names:
                continue
            self.client.create_view(base_token=base_token, table_id=table_id, view=view.to_lark_json(), actor=self.actor)
            result.created_views.append(f"{table.table_name}.{view.name}")

    def _table_name_map(self, base_token: str) -> dict[str, dict[str, Any]]:
        tables = self.client.list_tables(base_token=base_token, actor=self.actor)
        return {str(table.get("name") or table.get("table_name")): table for table in tables}


def _table_id_by_name(tables: dict[str, dict[str, Any]], table_name: str) -> str | None:
    table = tables.get(table_name)
    if not table:
        return None
    value = table.get("table_id") or table.get("id")
    return str(value) if value else None
