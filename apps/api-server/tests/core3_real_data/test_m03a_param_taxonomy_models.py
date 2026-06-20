import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import entities


API_SERVER_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_PATH = API_SERVER_ROOT / "alembic" / "versions" / "0031_core3_real_data_param_taxonomy.py"

M03A_TABLES = {
    "core3_param_taxonomy_version",
    "core3_param_raw_field_inventory",
    "core3_param_field_cluster",
    "core3_param_concept_candidate",
    "core3_param_definition",
    "core3_param_field_mapping_rule",
    "core3_param_taxonomy_review_item",
}


class BoundOp:
    def __init__(self, bind):
        self.bind = bind

    def get_bind(self):
        return self.bind


def load_m03a_migration():
    spec = importlib.util.spec_from_file_location("core3_param_taxonomy_migration", MIGRATION_PATH)
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


def test_m03a_models_are_registered():
    assert entities.Core3ParamTaxonomyVersion.__tablename__ == "core3_param_taxonomy_version"
    assert entities.Core3ParamRawFieldInventory.__tablename__ == "core3_param_raw_field_inventory"
    assert entities.Core3ParamFieldCluster.__tablename__ == "core3_param_field_cluster"
    assert entities.Core3ParamConceptCandidate.__tablename__ == "core3_param_concept_candidate"
    assert entities.Core3ParamDefinition.__tablename__ == "core3_param_definition"
    assert entities.Core3ParamFieldMappingRule.__tablename__ == "core3_param_field_mapping_rule"
    assert entities.Core3ParamTaxonomyReviewItem.__tablename__ == "core3_param_taxonomy_review_item"

    assert M03A_TABLES.issubset(set(Base.metadata.tables))


def test_m03a_taxonomy_version_columns_match_contract():
    expected_columns = {
        "taxonomy_version_id",
        "taxonomy_version",
        "project_id",
        "category_code",
        "status",
        "source_batch_ids",
        "source_field_count",
        "active_param_count",
        "review_required_count",
        "blocking_review_count",
        "llm_model_snapshot",
        "llm_prompt_version",
        "rule_version",
        "taxonomy_hash",
        "published_at",
        "created_by",
        "created_at",
        "updated_at",
    }

    table_columns = set(Base.metadata.tables["core3_param_taxonomy_version"].columns.keys())

    assert expected_columns.issubset(table_columns)


def test_m03a_migration_imports_with_expected_revision_chain():
    migration = load_m03a_migration()

    assert migration.revision == "0031_core3_param_taxonomy"
    assert migration.down_revision == "0030_core3_market_pool_v2"


def test_m03a_migration_creates_and_drops_only_param_taxonomy_tables():
    migration = load_m03a_migration()
    engine = make_sqlite_engine()
    original_op = migration.op

    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection, checkfirst=True)
        migration.op = BoundOp(connection)
        try:
            migration.upgrade()
            inspector = inspect(connection)
            table_names_after_upgrade = set(inspector.get_table_names())

            assert M03A_TABLES.issubset(table_names_after_upgrade)
            assert "core3_extract_param_value" not in table_names_after_upgrade
            assert "core3_sku_param_profile" not in table_names_after_upgrade

            migration.downgrade()
            inspector = inspect(connection)
            table_names_after_downgrade = set(inspector.get_table_names())

            assert not M03A_TABLES.intersection(table_names_after_downgrade)
            assert "category_project" in table_names_after_downgrade
        finally:
            migration.op = original_op
