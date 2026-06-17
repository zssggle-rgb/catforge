from datetime import datetime, timezone

import pytest

from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    Core3CategoryCode,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunMode,
    Core3TargetScopeType,
)
from app.services.core3_real_data.run_context import Core3RunContext, build_run_context


def _target_scope() -> Core3TargetScopeSchema:
    return Core3TargetScopeSchema(
        scope_type=Core3TargetScopeType.DEMO_TARGET,
        sku_codes=["TV00029115"],
        include_related_targets=True,
        data_domains=[Core3DataDomain.MARKET, Core3DataDomain.PARAM, Core3DataDomain.COMMENT],
        note_cn="85E7Q 单目标验证",
    )


def test_run_context_builds_with_defaults_and_round_trips_schema():
    context = build_run_context(
        run_id="run-001",
        project_id="project-001",
        run_mode=Core3RunMode.BOOTSTRAP_FULL,
        target_scope=_target_scope(),
        module_versions={"M00": "source-registry-1.0.0"},
        seed_versions={"task_seed": "tv-task-seed-2026-06"},
        input_watermarks={"week_sales_data": {"last_id": 1326}},
        triggered_by="pytest",
    )

    schema = context.to_schema()
    restored = Core3RunContext.from_schema(schema)

    assert context.category_code == Core3CategoryCode.TV
    assert context.ruleset_version == CORE3_DEFAULT_RULESET_VERSION
    assert schema.model_dump()["run_mode"] == "bootstrap_full"
    assert restored == context


def test_run_context_created_at_can_be_supplied_for_deterministic_tests():
    created_at = datetime(2026, 6, 12, 15, 32, 11, tzinfo=timezone.utc)
    context = Core3RunContext(
        run_id="run-001",
        project_id="project-001",
        run_mode=Core3RunMode.ACCEPTANCE_ONLY,
        target_scope=_target_scope(),
        created_at=created_at,
    )

    assert context.created_at == created_at


def test_run_context_module_version_helpers_do_not_mutate_original():
    context = build_run_context(
        run_id="run-001",
        project_id="project-001",
        run_mode=Core3RunMode.SINGLE_TARGET_REFRESH,
        target_scope=_target_scope(),
    )

    updated = context.with_module_version(Core3ModuleCode.M08, "sku-profile-1.0.0")

    assert context.module_version(Core3ModuleCode.M08) is None
    assert updated.module_version("M08") == "sku-profile-1.0.0"


def test_run_context_requires_run_id_and_project_id():
    with pytest.raises(ValueError, match="run_id"):
        Core3RunContext(run_id="", project_id="project-001", run_mode=Core3RunMode.BOOTSTRAP_FULL, target_scope=_target_scope())

    with pytest.raises(ValueError, match="project_id"):
        Core3RunContext(run_id="run-001", project_id=" ", run_mode=Core3RunMode.BOOTSTRAP_FULL, target_scope=_target_scope())

