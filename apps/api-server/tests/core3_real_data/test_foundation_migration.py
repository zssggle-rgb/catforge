import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0005_core3_real_data_foundation.py"

FOUNDATION_TABLES = {
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
RAW_SOURCE_TABLES = {
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_foundation_migration():
    spec = importlib.util.spec_from_file_location("core3_real_data_foundation_migration", MIGRATION_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )


def test_foundation_models_are_registered_under_v2_table_names():
    assert entities.Core3V2PipelineRun.__tablename__ == "core3_v2_pipeline_run"
    assert entities.Core3V2ModuleRun.__tablename__ == "core3_v2_module_run"
    assert entities.Core3V2ModuleDependencySnapshot.__tablename__ == (
        "core3_v2_module_dependency_snapshot"
    )
    assert entities.Core3V2PipelineWatermark.__tablename__ == "core3_v2_pipeline_watermark"

    for table_name in FOUNDATION_TABLES:
        assert table_name in Base.metadata.tables


def test_foundation_tables_can_be_created_from_metadata():
    engine = make_sqlite_engine()

    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())
    assert FOUNDATION_TABLES.issubset(table_names)


def test_foundation_migration_imports_with_expected_revision_chain():
    migration = load_foundation_migration()

    assert migration.revision == "0005_core3_foundation"
    assert migration.down_revision == "0004_tv_core3_mvp"


def test_foundation_migration_only_mentions_v2_foundation_tables():
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert FOUNDATION_TABLES.issubset(set(Base.metadata.tables))
    for table_name in RAW_SOURCE_TABLES | LEGACY_CORE3_TABLES:
        assert table_name not in source


def test_foundation_migration_creates_and_drops_v2_foundation_tables_only():
    migration = load_foundation_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection, checkfirst=True)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            table_names_after_upgrade = set(inspect(connection).get_table_names())

            assert FOUNDATION_TABLES.issubset(table_names_after_upgrade)
            assert not LEGACY_CORE3_TABLES.intersection(table_names_after_upgrade)
            assert not RAW_SOURCE_TABLES.intersection(table_names_after_upgrade)

            migration.downgrade()
            table_names_after_downgrade = set(inspect(connection).get_table_names())

            assert not FOUNDATION_TABLES.intersection(table_names_after_downgrade)
            assert "category_project" in table_names_after_downgrade
        finally:
            migration.op = original_op
