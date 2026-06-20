from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_data
from app.cli.catforge_data import _build_parser, _resolve_batch_scope
from app.models import entities
from app.services.core3_real_data.constants import Core3ReviewStatus, Core3SourceBatchStatus


def test_prepare_new_data_defaults_to_incremental_source_registration():
    parser = _build_parser()

    args = parser.parse_args(["prepare-new-data"])

    assert args.command == "prepare-new-data"
    assert args.register_source_batch == "incremental"
    assert args.batch_id == "latest"
    assert args.sku_batch_size == 50


def test_prepare_new_data_can_rerun_existing_batch_without_source_registration():
    parser = _build_parser()

    args = parser.parse_args(
        [
            "prepare-new-data",
            "--register-source-batch",
            "none",
            "--batch-id",
            "latest",
            "--limit-skus",
            "5",
        ]
    )

    assert args.register_source_batch == "none"
    assert args.batch_id == "latest"
    assert args.limit_skus == 5


def test_prepare_new_data_dry_run_does_not_register_source_batch(monkeypatch):
    parser = _build_parser()
    args = parser.parse_args(["prepare-new-data", "--dry-run"])

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fail_register(*_args, **_kwargs):
        raise AssertionError("dry-run must not register source batches")

    monkeypatch.setattr(catforge_data, "SessionLocal", DummySession)
    monkeypatch.setattr(catforge_data, "_register_source_batch", fail_register)

    result = catforge_data._prepare_new_data(args)

    assert result["status"] == "dry_run"
    assert result["source_registration"]["will_register_source_batch"] is True
    assert result["plan"]["will_run_modules"] == ["M00", "M01"]


def test_resolve_batch_scope_uses_batch_project_for_explicit_batch_id():
    session = _make_batch_scope_session()
    _seed_source_batch(
        session,
        batch_id="m00_real_project",
        project_id="real-project",
        category_code="TV",
    )

    batch_id, project_id, category_code = _resolve_batch_scope(
        session,
        project_id="core3_mvp",
        category_code="TV",
        batch_id="m00_real_project",
    )

    assert batch_id == "m00_real_project"
    assert project_id == "real-project"
    assert category_code == "TV"


def test_resolve_batch_scope_latest_falls_back_to_category_latest_batch():
    session = _make_batch_scope_session()
    _seed_source_batch(
        session,
        batch_id="m00_real_project_older",
        project_id="real-project",
        category_code="TV",
        scan_started_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
    )
    _seed_source_batch(
        session,
        batch_id="m00_real_project_latest",
        project_id="real-project",
        category_code="TV",
        scan_started_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
    )

    batch_id, project_id, category_code = _resolve_batch_scope(
        session,
        project_id="core3_mvp",
        category_code="TV",
        batch_id="latest",
    )

    assert batch_id == "m00_real_project_latest"
    assert project_id == "real-project"
    assert category_code == "TV"


def _make_batch_scope_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    entities.Core3SourceBatch.__table__.create(bind=engine, checkfirst=True)
    return Session(engine)


def _seed_source_batch(
    session: Session,
    *,
    batch_id: str,
    project_id: str,
    category_code: str,
    scan_started_at: datetime | None = None,
) -> None:
    session.add(
        entities.Core3SourceBatch(
            batch_id=batch_id,
            project_id=project_id,
            category_code=category_code,
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=scan_started_at or datetime(2026, 6, 19, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.commit()
