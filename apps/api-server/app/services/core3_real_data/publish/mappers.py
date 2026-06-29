"""Map internal CatForge publish records to Feishu Base cell values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.core3_real_data.publish.schemas import BaseTableDefinition


class BaseRecordMapper:
    def map_record(self, table: BaseTableDefinition, values: dict[str, Any]) -> dict[str, Any]:
        record = dict(values)
        record["unique_key"] = table.unique_key(record)
        mapped: dict[str, Any] = {}
        for field in table.fields:
            value = record.get(field.key)
            mapped[field.name] = _cell_value(value, field_type=field.field_type)
        return mapped

    def map_records(self, table: BaseTableDefinition, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self.map_record(table, record) for record in records]


def _cell_value(value: Any, *, field_type: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        value = float(value)
    if field_type == "number":
        if value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    if field_type == "datetime":
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return f"{value.isoformat()} 00:00:00"
        return str(value) if value else None
    if field_type == "select":
        return str(value) if value else None
    if isinstance(value, (dict, list, tuple, set)):
        if isinstance(value, dict):
            return "；".join(f"{key}:{val}" for key, val in value.items())
        return "、".join(str(item) for item in value)
    return str(value)

