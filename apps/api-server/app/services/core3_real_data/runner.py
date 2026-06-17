"""Runner protocol and registry for Core3 real-data v2."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.schemas.core3_real_data import Core3ModuleRunResultSchema
from app.services.core3_real_data.constants import (
    Core3DataDomain,
    Core3ModuleCode,
    Core3ModuleTargetScope,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.run_context import Core3RunContext


@dataclass(frozen=True)
class Core3ModuleTarget:
    scope: Core3ModuleTargetScope
    target_ids: tuple[str, ...] = ()
    data_domains: tuple[Core3DataDomain, ...] = ()
    reason_cn: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_summary(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "target_ids": list(self.target_ids),
            "data_domains": [domain.value for domain in self.data_domains],
            "reason_cn": self.reason_cn,
            "metadata": dict(self.metadata),
        }


class Core3ModuleRunner(Protocol):
    module_code: Core3ModuleCode

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        ...


class Core3RunnerRegistryError(ValueError):
    pass


class Core3RunnerRegistry:
    def __init__(self) -> None:
        self._runners: dict[Core3ModuleCode, Core3ModuleRunner] = {}

    def register(self, runner: Core3ModuleRunner, *, replace: bool = False) -> None:
        module_code = Core3ModuleCode(runner.module_code)
        if module_code in self._runners and not replace:
            raise Core3RunnerRegistryError(f"runner already registered for {module_code.value}")
        self._runners[module_code] = runner

    def get(self, module_code: Core3ModuleCode | str) -> Core3ModuleRunner:
        normalized = Core3ModuleCode(module_code)
        try:
            return self._runners[normalized]
        except KeyError as exc:
            raise Core3RunnerRegistryError(f"runner not registered for {normalized.value}") from exc

    def has(self, module_code: Core3ModuleCode | str) -> bool:
        return Core3ModuleCode(module_code) in self._runners

    def registered_modules(self) -> tuple[Core3ModuleCode, ...]:
        return tuple(self._runners)

    def run(
        self,
        module_code: Core3ModuleCode | str,
        context: Core3RunContext,
        target: Core3ModuleTarget,
    ) -> Core3ModuleRunResultSchema:
        return self.get(module_code).run(context, target)


@dataclass(frozen=True)
class NoopModuleRunner:
    module_code: Core3ModuleCode
    status: Core3RunStatus = Core3RunStatus.SUCCESS

    def run(self, context: Core3RunContext, target: Core3ModuleTarget) -> Core3ModuleRunResultSchema:
        output_hash = stable_hash(
            {
                "module_code": self.module_code.value,
                "run_id": context.run_id,
                "target": target.to_summary(),
            },
            version=f"noop-{self.module_code.value}",
        )
        return Core3ModuleRunResultSchema(
            module_code=self.module_code,
            status=self.status,
            input_count=len(target.target_ids),
            changed_input_count=0,
            output_count=0,
            output_hash=output_hash,
            warnings=[],
            review_issues=[],
            downstream_impacts=[],
            summary_json={
                "runner": "noop",
                "target": target.to_summary(),
            },
        )

