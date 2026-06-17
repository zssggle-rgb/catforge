"""Repository boundaries for Core3 real-data v2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.services.core3_real_data.constants import CORE3_RAW_SOURCE_TABLES, Core3CategoryCode

RAW_SOURCE_MUTATION_PREFIXES: tuple[str, ...] = (
    "add",
    "alter",
    "create",
    "delete",
    "drop",
    "insert",
    "merge",
    "remove",
    "save",
    "truncate",
    "update",
    "upsert",
    "write",
)

RAW_SOURCE_MUTATION_SQL_KEYWORDS: tuple[str, ...] = (
    "ALTER",
    "CREATE",
    "DELETE",
    "DROP",
    "INSERT",
    "MERGE",
    "TRUNCATE",
    "UPDATE",
)


class RawSourceMutationNotAllowed(RuntimeError):
    pass


@dataclass(frozen=True)
class Core3RepositoryContext:
    db: Session
    project_id: str
    category_code: Core3CategoryCode = Core3CategoryCode.TV

    def __post_init__(self) -> None:
        if not self.project_id.strip():
            raise ValueError("project_id is required")
        object.__setattr__(self, "category_code", Core3CategoryCode(self.category_code))


class Core3BaseRepository:
    def __init__(self, context: Core3RepositoryContext) -> None:
        self.context = context

    @property
    def db(self) -> Session:
        return self.context.db

    @property
    def project_id(self) -> str:
        return self.context.project_id

    @property
    def category_code(self) -> Core3CategoryCode:
        return self.context.category_code

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def pagination(limit: int = 100, offset: int = 0, *, max_limit: int = 1000) -> tuple[int, int]:
        normalized_limit = min(max(limit, 1), max_limit)
        normalized_offset = max(offset, 0)
        return normalized_limit, normalized_offset

    def audit_fields(self, actor: str = "system") -> dict[str, Any]:
        now = self.now_utc()
        return {
            "created_at": now,
            "updated_at": now,
            "created_by": actor,
            "updated_by": actor,
        }


class RawSourceReadOnlyGuard:
    raw_source_tables = frozenset(CORE3_RAW_SOURCE_TABLES)
    mutation_prefixes = RAW_SOURCE_MUTATION_PREFIXES
    mutation_sql_keywords = RAW_SOURCE_MUTATION_SQL_KEYWORDS

    @classmethod
    def ensure_raw_source_table(cls, table_name: str) -> str:
        normalized = table_name.strip()
        if normalized not in cls.raw_source_tables:
            raise ValueError(f"unknown raw source table: {table_name}")
        return normalized

    @classmethod
    def ensure_select_method(cls, method_name: str) -> str:
        normalized = method_name.strip().lower()
        if any(normalized == prefix or normalized.startswith(f"{prefix}_") for prefix in cls.mutation_prefixes):
            raise RawSourceMutationNotAllowed(f"raw source repository method is not read-only: {method_name}")
        return method_name

    @classmethod
    def ensure_read_only_sql(cls, sql: str) -> str:
        normalized = sql.strip()
        upper_sql = normalized.upper()
        if any(keyword in upper_sql.split() for keyword in cls.mutation_sql_keywords):
            raise RawSourceMutationNotAllowed("raw source SQL must be read-only")
        if not upper_sql.startswith(("SELECT", "WITH", "EXPLAIN")):
            raise RawSourceMutationNotAllowed("raw source SQL must start with SELECT, WITH or EXPLAIN")
        return sql

    @classmethod
    def assert_repository_interface_read_only(cls, repository: object) -> None:
        for attribute_name in dir(repository):
            if attribute_name.startswith("_"):
                continue
            attribute = getattr(repository, attribute_name)
            if callable(attribute):
                cls.ensure_select_method(attribute_name)


class RawSourceReadOnlyMixin:
    raw_source_guard = RawSourceReadOnlyGuard

    def ensure_raw_source_table(self, table_name: str) -> str:
        return self.raw_source_guard.ensure_raw_source_table(table_name)

    def ensure_select_method(self, method_name: str) -> str:
        return self.raw_source_guard.ensure_select_method(method_name)
