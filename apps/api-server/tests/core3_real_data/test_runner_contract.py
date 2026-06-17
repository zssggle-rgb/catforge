import pytest

from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    Core3DataDomain,
    Core3ModuleCode,
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3RunStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import (
    Core3ModuleTarget,
    Core3RunnerRegistry,
    Core3RunnerRegistryError,
    NoopModuleRunner,
)


def _context():
    return build_run_context(
        run_id="run-001",
        project_id="project-001",
        run_mode=Core3RunMode.BOOTSTRAP_FULL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.DEMO_TARGET, sku_codes=["TV00029115"]),
    )


def _target() -> Core3ModuleTarget:
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.TARGET_SKU,
        target_ids=("TV00029115",),
        data_domains=(Core3DataDomain.MARKET, Core3DataDomain.PARAM),
        reason_cn="85E7Q 单目标验证",
        metadata={"source": "pytest"},
    )


def test_module_target_summary_uses_plain_values():
    summary = _target().to_summary()

    assert summary == {
        "scope": "target_sku",
        "target_ids": ["TV00029115"],
        "data_domains": ["market", "param"],
        "reason_cn": "85E7Q 单目标验证",
        "metadata": {"source": "pytest"},
    }


def test_noop_module_runner_returns_complete_result_contract():
    result = NoopModuleRunner(Core3ModuleCode.M00).run(_context(), _target())
    payload = result.model_dump()

    assert payload["module_code"] == "M00"
    assert payload["status"] == "success"
    assert payload["input_count"] == 1
    assert payload["changed_input_count"] == 0
    assert payload["output_count"] == 0
    assert payload["output_hash"].startswith("sha256:noop-M00:")
    assert payload["warnings"] == []
    assert payload["review_issues"] == []
    assert payload["downstream_impacts"] == []
    assert payload["summary_json"]["runner"] == "noop"


def test_runner_registry_registers_gets_and_runs_module_runner():
    registry = Core3RunnerRegistry()
    runner = NoopModuleRunner(Core3ModuleCode.M01, status=Core3RunStatus.WARNING)

    registry.register(runner)

    assert registry.has("M01")
    assert registry.get(Core3ModuleCode.M01) is runner
    assert registry.registered_modules() == (Core3ModuleCode.M01,)
    assert registry.run("M01", _context(), _target()).status == "warning"


def test_runner_registry_rejects_duplicate_unless_replace_is_explicit():
    registry = Core3RunnerRegistry()
    first = NoopModuleRunner(Core3ModuleCode.M02)
    second = NoopModuleRunner(Core3ModuleCode.M02, status=Core3RunStatus.BLOCKED)

    registry.register(first)
    with pytest.raises(Core3RunnerRegistryError, match="already registered"):
        registry.register(second)

    registry.register(second, replace=True)
    assert registry.get("M02") is second


def test_runner_registry_reports_missing_runner():
    registry = Core3RunnerRegistry()

    with pytest.raises(Core3RunnerRegistryError, match="not registered"):
        registry.get(Core3ModuleCode.M16)

