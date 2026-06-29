"""Contracts for publishing CatForge analysis results to external workbenches."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

BaseFieldType = Literal["text", "number", "select", "datetime"]


@dataclass(frozen=True)
class BaseFieldDefinition:
    key: str
    name: str
    field_type: BaseFieldType = "text"
    multiple: bool = False
    options: tuple[str, ...] = ()
    description: str | None = None

    def to_lark_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "type": self.field_type}
        if self.description:
            payload["description"] = self.description
        if self.field_type == "number":
            payload["style"] = {"type": "plain", "precision": 2, "thousands_separator": True}
        elif self.field_type == "datetime":
            payload["style"] = {"format": "yyyy/MM/dd HH:mm"}
        elif self.field_type == "select":
            payload["multiple"] = self.multiple
            if self.options:
                payload["options"] = [{"name": option} for option in self.options]
        return payload


@dataclass(frozen=True)
class BaseViewDefinition:
    name: str
    view_type: str = "grid"

    def to_lark_json(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.view_type}


@dataclass(frozen=True)
class BaseTableDefinition:
    scope: str
    table_name: str
    unique_key_fields: tuple[str, ...]
    fields: tuple[BaseFieldDefinition, ...]
    views: tuple[BaseViewDefinition, ...] = ()

    @property
    def field_by_key(self) -> dict[str, BaseFieldDefinition]:
        return {field.key: field for field in self.fields}

    def unique_key(self, record: dict[str, Any]) -> str:
        return "|".join(str(record.get(key) or "") for key in self.unique_key_fields)


@dataclass(frozen=True)
class PublishRecord:
    scope: str
    values: dict[str, Any]


@dataclass
class ScopeSyncResult:
    scope: str
    status: str
    extracted_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    table_name: str | None = None
    table_id: str | None = None
    message_cn: str | None = None


@dataclass
class PublishResult:
    status: str
    category_code: str
    batch_id: str
    base_url: str | None = None
    scopes: list[ScopeSyncResult] = field(default_factory=list)
    message_cn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "base_url": self.base_url,
            "message_cn": self.message_cn,
            "scopes": [scope.__dict__ for scope in self.scopes],
        }

