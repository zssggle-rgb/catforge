"""Configuration helpers for CatForge Base workbench publishing."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class BaseWorkbenchConfig:
    base_token: str | None = None
    table_map: dict[str, str] = field(default_factory=dict)
    actor: str = "user"
    cli_bin: str = "lark-cli"
    chunk_size: int = 100

    @property
    def normalized_chunk_size(self) -> int:
        return min(max(int(self.chunk_size), 1), 200)


def load_base_workbench_config() -> BaseWorkbenchConfig:
    table_map_raw = os.getenv("CATFORGE_BASE_WORKBENCH_TABLE_MAP") or "{}"
    try:
        table_map = json.loads(table_map_raw)
    except json.JSONDecodeError:
        table_map = {}
    if not isinstance(table_map, dict):
        table_map = {}
    return BaseWorkbenchConfig(
        base_token=os.getenv("CATFORGE_BASE_WORKBENCH_TOKEN") or None,
        table_map={str(key): str(value) for key, value in table_map.items() if value},
        actor=(os.getenv("CATFORGE_BASE_WORKBENCH_AS") or "user").strip() or "user",
        cli_bin=os.getenv("CATFORGE_FEISHU_CLI_BIN") or "lark-cli",
        chunk_size=_int_env("CATFORGE_BASE_SYNC_CHUNK_SIZE", default=100),
    )


def _int_env(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def extract_base_token(payload: dict[str, Any]) -> str | None:
    for candidate in _walk_dicts(payload):
        for key in ("app_token", "base_token", "token"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def extract_table_id(payload: dict[str, Any], *, table_name: str | None = None) -> str | None:
    for candidate in _walk_dicts(payload):
        name = candidate.get("name") or candidate.get("table_name")
        table_id = candidate.get("table_id") or candidate.get("id")
        if isinstance(table_id, str) and table_id.startswith("tbl"):
            if table_name is None or name == table_name:
                return table_id
    return None


def _walk_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        found.append(payload)
        for value in payload.values():
            found.extend(_walk_dicts(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_walk_dicts(item))
    return found

