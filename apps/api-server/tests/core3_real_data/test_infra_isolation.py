import ast
from pathlib import Path

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = API_SERVER_ROOT / "app"

V2_TABLES = {
    "core3_v2_pipeline_run",
    "core3_v2_module_run",
    "core3_v2_module_dependency_snapshot",
    "core3_v2_pipeline_watermark",
}
LEGACY_CORE3_TABLES = {
    "core3_pipeline_run",
    "core3_sku_market_profile",
    "core3_sku_feature_profile",
    "core3_competitor_candidate",
    "core3_competitor_result",
    "core3_evidence_card",
}


def python_sources_under(relative_path: str) -> list[Path]:
    return sorted((APP_ROOT / relative_path).glob("*.py"))


def imported_modules(source_path: Path) -> set[str]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def assert_no_import_prefix(source_paths: list[Path], forbidden_prefixes: tuple[str, ...]) -> None:
    offenders: list[str] = []
    for source_path in source_paths:
        for module_name in imported_modules(source_path):
            if module_name.startswith(forbidden_prefixes):
                offenders.append(f"{source_path.relative_to(API_SERVER_ROOT)} imports {module_name}")
    assert offenders == []


def test_core3_real_data_does_not_import_legacy_core3_mvp_namespace():
    assert_no_import_prefix(
        [
            *python_sources_under("services/core3_real_data"),
            APP_ROOT / "schemas" / "core3_real_data.py",
        ],
        (
            "app.services.core3_mvp",
            "app.schemas.core3_mvp",
            "app.api.core3_mvp",
        ),
    )


def test_legacy_core3_mvp_does_not_import_core3_real_data_namespace():
    assert_no_import_prefix(
        [
            *python_sources_under("services/core3_mvp"),
            APP_ROOT / "schemas" / "core3_mvp.py",
            APP_ROOT / "api" / "core3_mvp.py",
        ],
        (
            "app.services.core3_real_data",
            "app.schemas.core3_real_data",
            "app.api.core3_real_data",
        ),
    )


def test_infra_phase_does_not_pre_register_missing_v2_api_router():
    main_source = (APP_ROOT / "main.py").read_text(encoding="utf-8")
    v2_api_module = APP_ROOT / "api" / "core3_real_data.py"

    assert "core3_mvp" in main_source
    if not v2_api_module.exists():
        assert "core3_real_data" not in main_source


def test_v2_models_are_registered_without_reusing_legacy_core3_table_names():
    # Access the model classes so static analyzers and import registration checks
    # cover the Alembic-facing entities module.
    assert entities.Core3V2PipelineRun.__tablename__ == "core3_v2_pipeline_run"
    assert entities.Core3V2ModuleRun.__tablename__ == "core3_v2_module_run"
    assert entities.Core3V2ModuleDependencySnapshot.__tablename__ == (
        "core3_v2_module_dependency_snapshot"
    )
    assert entities.Core3V2PipelineWatermark.__tablename__ == "core3_v2_pipeline_watermark"

    table_names = set(Base.metadata.tables)
    assert V2_TABLES.issubset(table_names)
    assert LEGACY_CORE3_TABLES.issubset(table_names)
    assert V2_TABLES.isdisjoint(LEGACY_CORE3_TABLES)


def test_v2_foundation_tables_do_not_depend_on_legacy_core3_mvp_tables():
    allowed_external_tables = {"category_project"}

    for table_name in V2_TABLES:
        table = Base.metadata.tables[table_name]
        for foreign_key in table.foreign_keys:
            referred_table_name = foreign_key.column.table.name
            assert referred_table_name.startswith("core3_v2_") or referred_table_name in allowed_external_tables
