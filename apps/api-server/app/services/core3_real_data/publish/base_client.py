"""Feishu Base client adapter used by the CatForge publish layer."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Protocol


class BaseClientError(RuntimeError):
    pass


class BaseClient(Protocol):
    def create_base(self, *, name: str, table_name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]: ...

    def list_tables(self, *, base_token: str, actor: str) -> list[dict[str, Any]]: ...

    def create_table(self, *, base_token: str, name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]: ...

    def list_fields(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]: ...

    def create_field(self, *, base_token: str, table_id: str, field: dict[str, Any], actor: str) -> dict[str, Any]: ...

    def list_views(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]: ...

    def create_view(self, *, base_token: str, table_id: str, view: dict[str, Any], actor: str) -> dict[str, Any]: ...

    def list_records(
        self,
        *,
        base_token: str,
        table_id: str,
        field_names: list[str],
        actor: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]: ...

    def upsert_record(
        self,
        *,
        base_token: str,
        table_id: str,
        fields: dict[str, Any],
        actor: str,
        record_id: str | None = None,
    ) -> dict[str, Any]: ...


class LarkCliBaseClient:
    def __init__(self, *, cli_bin: str = "lark-cli") -> None:
        self.cli_bin = cli_bin

    def create_base(self, *, name: str, table_name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]:
        return self._run(
            "base",
            "+base-create",
            "--name",
            name,
            "--table-name",
            table_name,
            "--fields",
            json.dumps(fields, ensure_ascii=False),
            "--as",
            actor,
            "--format",
            "json",
        )

    def list_tables(self, *, base_token: str, actor: str) -> list[dict[str, Any]]:
        payload = self._run("base", "+table-list", "--base-token", base_token, "--as", actor, "--format", "json", "--limit", "100")
        return _extract_items(payload, item_keys=("tables", "items", "data"))

    def create_table(self, *, base_token: str, name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]:
        return self._run(
            "base",
            "+table-create",
            "--base-token",
            base_token,
            "--name",
            name,
            "--fields",
            json.dumps(fields, ensure_ascii=False),
            "--as",
            actor,
            "--format",
            "json",
        )

    def list_fields(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]:
        payload = self._run(
            "base",
            "+field-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            actor,
            "--format",
            "json",
            "--limit",
            "200",
        )
        return _extract_items(payload, item_keys=("fields", "items", "data"))

    def create_field(self, *, base_token: str, table_id: str, field: dict[str, Any], actor: str) -> dict[str, Any]:
        return self._run(
            "base",
            "+field-create",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(field, ensure_ascii=False),
            "--as",
            actor,
            "--format",
            "json",
        )

    def list_views(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]:
        payload = self._run(
            "base",
            "+view-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            actor,
            "--format",
            "json",
            "--limit",
            "200",
        )
        return _extract_items(payload, item_keys=("views", "items", "data"))

    def create_view(self, *, base_token: str, table_id: str, view: dict[str, Any], actor: str) -> dict[str, Any]:
        return self._run(
            "base",
            "+view-create",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(view, ensure_ascii=False),
            "--as",
            actor,
            "--format",
            "json",
        )

    def list_records(
        self,
        *,
        base_token: str,
        table_id: str,
        field_names: list[str],
        actor: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        cmd = [
            "base",
            "+record-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--as",
            actor,
            "--format",
            "json",
            "--limit",
            str(limit),
            "--offset",
            str(offset),
        ]
        for field_name in field_names:
            cmd.extend(["--field-id", field_name])
        payload = self._run(*cmd)
        return _extract_items(payload, item_keys=("records", "items", "data"))

    def upsert_record(
        self,
        *,
        base_token: str,
        table_id: str,
        fields: dict[str, Any],
        actor: str,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        cmd = [
            "base",
            "+record-upsert",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps(fields, ensure_ascii=False),
            "--as",
            actor,
            "--format",
            "json",
        ]
        if record_id:
            cmd.extend(["--record-id", record_id])
        return self._run(*cmd)

    def _run(self, *args: str) -> dict[str, Any]:
        completed = subprocess.run(
            [self.cli_bin, *args],
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"lark-cli failed: {' '.join(args)}"
            raise BaseClientError(message)
        stdout = completed.stdout.strip()
        if not stdout:
            return {}
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise BaseClientError(f"lark-cli returned non-json output for {' '.join(args[:2])}: {stdout[:300]}") from exc
        if isinstance(payload, dict):
            return payload
        return {"data": payload}


@dataclass
class InMemoryBaseClient:
    base_token: str = "base_test_token"
    tables: dict[str, dict[str, Any]] = field(default_factory=dict)
    fields: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    records: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    views: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def create_base(self, *, name: str, table_name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]:
        table_id = self._table_id(table_name)
        self.tables[table_id] = {"table_id": table_id, "name": table_name}
        self.fields[table_id] = list(fields)
        return {"base": {"app_token": self.base_token, "name": name}, "table": self.tables[table_id]}

    def list_tables(self, *, base_token: str, actor: str) -> list[dict[str, Any]]:
        return list(self.tables.values())

    def create_table(self, *, base_token: str, name: str, fields: list[dict[str, Any]], actor: str) -> dict[str, Any]:
        table_id = self._table_id(name)
        self.tables[table_id] = {"table_id": table_id, "name": name}
        self.fields[table_id] = list(fields)
        return {"table": self.tables[table_id]}

    def list_fields(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]:
        return list(self.fields.get(table_id, []))

    def create_field(self, *, base_token: str, table_id: str, field: dict[str, Any], actor: str) -> dict[str, Any]:
        self.fields.setdefault(table_id, []).append(dict(field))
        return {"field": field}

    def list_views(self, *, base_token: str, table_id: str, actor: str) -> list[dict[str, Any]]:
        return list(self.views.get(table_id, []))

    def create_view(self, *, base_token: str, table_id: str, view: dict[str, Any], actor: str) -> dict[str, Any]:
        self.views.setdefault(table_id, []).append(dict(view))
        return {"view": view}

    def list_records(
        self,
        *,
        base_token: str,
        table_id: str,
        field_names: list[str],
        actor: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        rows = list(self.records.get(table_id, {}).values())
        return rows[offset : offset + limit]

    def upsert_record(
        self,
        *,
        base_token: str,
        table_id: str,
        fields: dict[str, Any],
        actor: str,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        record_id = record_id or f"rec_{len(self.records.setdefault(table_id, {})) + 1}"
        record = {"record_id": record_id, "fields": dict(fields)}
        self.records.setdefault(table_id, {})[record_id] = record
        return {"record": record}

    @staticmethod
    def _table_id(name: str) -> str:
        return f"tbl_{abs(hash(name)) % 10_000_000}"


def _extract_items(payload: dict[str, Any], *, item_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    candidates: list[Any] = [payload]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.append(data)
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        for key in item_keys:
            value = candidate.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []
