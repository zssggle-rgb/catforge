"""Run context contracts for Core3 real-data v2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from app.schemas.core3_real_data import Core3RunContextSchema, Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    Core3CategoryCode,
    Core3ModuleCode,
    Core3RunMode,
)


@dataclass(frozen=True)
class Core3RunContext:
    run_id: str
    project_id: str
    run_mode: Core3RunMode
    target_scope: Core3TargetScopeSchema
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION
    module_versions: dict[str, str] | None = None
    seed_versions: dict[str, str] | None = None
    input_watermarks: dict[str, Any] | None = None
    triggered_by: str = "system"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id is required")
        if not self.project_id.strip():
            raise ValueError("project_id is required")
        object.__setattr__(self, "category_code", Core3CategoryCode(self.category_code))
        object.__setattr__(self, "run_mode", Core3RunMode(self.run_mode))
        object.__setattr__(self, "module_versions", dict(self.module_versions or {}))
        object.__setattr__(self, "seed_versions", dict(self.seed_versions or {}))
        object.__setattr__(self, "input_watermarks", dict(self.input_watermarks or {}))
        object.__setattr__(self, "created_at", self.created_at or datetime.now(timezone.utc))

    @classmethod
    def from_schema(cls, schema: Core3RunContextSchema) -> "Core3RunContext":
        return cls(
            run_id=schema.run_id,
            project_id=schema.project_id,
            category_code=Core3CategoryCode(schema.category_code),
            batch_id=schema.batch_id,
            run_mode=Core3RunMode(schema.run_mode),
            ruleset_version=schema.ruleset_version,
            module_versions=dict(schema.module_versions),
            seed_versions=dict(schema.seed_versions),
            target_scope=schema.target_scope,
            input_watermarks=dict(schema.input_watermarks),
            triggered_by=schema.triggered_by,
            created_at=schema.created_at,
        )

    def to_schema(self) -> Core3RunContextSchema:
        return Core3RunContextSchema(
            run_id=self.run_id,
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=self.batch_id,
            run_mode=self.run_mode,
            ruleset_version=self.ruleset_version,
            module_versions=dict(self.module_versions or {}),
            seed_versions=dict(self.seed_versions or {}),
            target_scope=self.target_scope,
            input_watermarks=dict(self.input_watermarks or {}),
            triggered_by=self.triggered_by,
            created_at=self.created_at,
        )

    def module_version(self, module_code: Core3ModuleCode | str) -> str | None:
        return (self.module_versions or {}).get(Core3ModuleCode(module_code).value)

    def with_module_version(self, module_code: Core3ModuleCode | str, version: str) -> "Core3RunContext":
        module_versions = dict(self.module_versions or {})
        module_versions[Core3ModuleCode(module_code).value] = version
        return replace(self, module_versions=module_versions)


def build_run_context(
    *,
    run_id: str,
    project_id: str,
    run_mode: Core3RunMode,
    target_scope: Core3TargetScopeSchema,
    category_code: Core3CategoryCode = Core3CategoryCode.TV,
    batch_id: str | None = None,
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION,
    module_versions: dict[str, str] | None = None,
    seed_versions: dict[str, str] | None = None,
    input_watermarks: dict[str, Any] | None = None,
    triggered_by: str = "system",
) -> Core3RunContext:
    return Core3RunContext(
        run_id=run_id,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_mode=run_mode,
        ruleset_version=ruleset_version,
        module_versions=module_versions,
        seed_versions=seed_versions,
        target_scope=target_scope,
        input_watermarks=input_watermarks,
        triggered_by=triggered_by,
    )

