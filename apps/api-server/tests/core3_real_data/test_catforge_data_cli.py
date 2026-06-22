from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.cli import catforge_data
from app.cli.catforge_data import _build_parser, _resolve_batch_scope
from app.models import entities
from app.services.core3_real_data.constants import Core3CleanRecordStatus, Core3ReviewStatus, Core3SourceBatchStatus


def test_prepare_new_data_defaults_to_incremental_source_registration():
    parser = _build_parser()

    args = parser.parse_args(["prepare-new-data"])

    assert args.command == "prepare-new-data"
    assert args.register_source_batch == "incremental"
    assert args.batch_id == "latest"
    assert args.sku_batch_size == 50
    assert args.evidence_sku_batch_size == 1


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


def test_project_args_work_before_or_after_subcommand():
    parser = _build_parser()

    before_args = parser.parse_args(
        [
            "--project-id",
            "real-project",
            "--category-code",
            "TV",
            "inspect-data-quality",
            "--batch-id",
            "latest",
        ]
    )
    after_args = parser.parse_args(
        [
            "inspect-data-quality",
            "--project-id",
            "real-project",
            "--category-code",
            "TV",
            "--batch-id",
            "latest",
        ]
    )

    assert before_args.project_id == "real-project"
    assert before_args.category_code == "TV"
    assert after_args.project_id == "real-project"
    assert after_args.category_code == "TV"


def test_inspect_data_quality_handles_summary_without_preliminary_summary(monkeypatch):
    session = _make_sku_quality_session()
    _seed_sku_quality_rows(session)
    parser = _build_parser()
    args = parser.parse_args(
        [
            "inspect-data-quality",
            "--batch-id",
            "m00_real_project",
            "--limit-skus",
            "1",
        ]
    )
    monkeypatch.setattr(catforge_data, "SessionLocal", lambda: session)

    result = catforge_data._inspect_data_quality(args)

    assert result["status"] == "success"
    assert result["market_coverage_summary"] == {}
    assert result["comment_preliminary_summary"] == {}
    assert result["clean_counts"]["sku"] == 1
    assert len(result["sample_skus"]) == 1


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
    assert result["plan"]["will_run_modules"] == ["M00", "M01", "M02"]
    assert result["plan"]["will_not_run_modules"] == ["M05"]


def test_inspect_sku_quality_summarizes_one_sku(monkeypatch):
    session = _make_sku_quality_session()
    _seed_sku_quality_rows(session)
    parser = _build_parser()
    args = parser.parse_args(
        [
            "inspect-sku-quality",
            "--batch-id",
            "m00_real_project",
            "--sku-code",
            "TV00010001",
        ]
    )
    monkeypatch.setattr(catforge_data, "SessionLocal", lambda: session)

    result = catforge_data._inspect_sku_quality(args)

    assert result["status"] == "success"
    assert result["project_id"] == "real-project"
    assert result["sku"]["model_name"] == "85Q6N"
    assert result["row_counts"] == {
        "sku": 1,
        "market": 1,
        "attribute": 1,
        "claim": 1,
        "claim_sentence": 1,
        "comment": 2,
        "comment_sentence": 1,
        "comment_dimension": 2,
        "quality_issue": 1,
    }
    assert result["market_summary"]["platform_counts"] == {"平台电商": 1}
    assert result["attribute_summary"]["unknown_count"] == 1
    assert result["comment_summary"]["low_value_comment_count"] == 1
    assert result["comment_summary"]["candidate_after_low_value_count"] == 1
    assert result["comment_summary"]["service_candidate_count"] == 1
    assert result["comment_summary"]["service_candidate_after_low_value_count"] == 0
    assert result["quality_issue_summary"]["info"] == 1
    assert result["quality_issue_summary"]["by_type"] == {"unknown_value": 1}


def test_inspect_sku_quality_excludes_skipped_service_comments_from_product_candidates(monkeypatch):
    session = _make_sku_quality_session()
    _seed_sku_quality_rows(session)
    _add_clean_comment(
        session,
        {
            "project_id": "real-project",
            "category_code": "TV",
            "batch_id": "m00_real_project",
            "run_id": None,
            "module_run_id": None,
        },
        source_pk="6",
        comment_id="c-service",
        low_value=False,
        record_status=Core3CleanRecordStatus.SKIPPED.value,
        clean_comment_text="安装师傅很专业",
    )
    session.commit()
    parser = _build_parser()
    args = parser.parse_args(
        [
            "inspect-sku-quality",
            "--batch-id",
            "m00_real_project",
            "--sku-code",
            "TV00010001",
        ]
    )
    monkeypatch.setattr(catforge_data, "SessionLocal", lambda: session)

    result = catforge_data._inspect_sku_quality(args)

    summary = result["comment_summary"]
    assert summary["raw_row_count"] == 3
    assert summary["low_value_comment_count"] == 1
    assert summary["product_comment_candidate_count"] == 1
    assert summary["service_fulfillment_count"] == 2
    assert summary["service_fulfillment_blocked_count"] == 2
    assert summary["service_candidate_not_blocked"] is False


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


def _make_sku_quality_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.Core3SourceBatch.__table__,
        entities.Core3CleanSku.__table__,
        entities.Core3CleanMarketWeekly.__table__,
        entities.Core3CleanAttribute.__table__,
        entities.Core3CleanClaim.__table__,
        entities.Core3CleanClaimSentence.__table__,
        entities.Core3CleanComment.__table__,
        entities.Core3CleanCommentSentence.__table__,
        entities.Core3CleanCommentDimension.__table__,
        entities.Core3DataQualityIssue.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)
    return Session(engine)


def _seed_sku_quality_rows(session: Session) -> None:
    _seed_source_batch(
        session,
        batch_id="m00_real_project",
        project_id="real-project",
        category_code="TV",
    )
    common = {
        "project_id": "real-project",
        "category_code": "TV",
        "batch_id": "m00_real_project",
        "run_id": None,
        "module_run_id": None,
    }
    session.add(
        entities.Core3CleanSku(
            **common,
            sku_code="TV00010001",
            model_name="85Q6N",
            brand_name="海信",
            category_name="彩电",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            coverage_json={
                "market": {
                    "covered": True,
                    "row_count": 1,
                    "weekly_coverage": {
                        "covered": True,
                        "active_week_count": 1,
                        "single_platform_week_count": 1,
                        "internal_gap_week_count": 0,
                    },
                },
                "attribute": {"covered": True, "row_count": 1, "unknown_count": 1},
                "comment": {"covered": True, "row_count": 2},
            },
            clean_record_key="sku:TV00010001",
            clean_hash="sha256:test:sku",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="warning",
            quality_flags=["unknown_value"],
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.add(
        entities.Core3CleanMarketWeekly(
            **common,
            source_table="week_sales_data",
            source_pk="1",
            source_row_id="week_sales_data:1",
            source_operation_type="insert",
            sku_code="TV00010001",
            model_name="85Q6N",
            brand_name="海信",
            period_raw="26W01",
            period_type="week",
            period_year_hint=2026,
            period_week_index=1,
            period_parse_status="parsed",
            channel_type="线上",
            platform_type="平台电商",
            sales_volume=Decimal("10"),
            sales_amount=Decimal("59990"),
            avg_price=Decimal("5999"),
            avg_price_expected=Decimal("5999"),
            price_check_status="ok",
            clean_record_key="market:week_sales_data:1",
            clean_hash="sha256:test:market",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.add(
        entities.Core3CleanAttribute(
            **common,
            source_table="attribute_data",
            source_pk="2",
            source_row_id="attribute_data:2",
            source_operation_type="insert",
            sku_code="TV00010001",
            model_name="85Q6N",
            brand_name="海信",
            raw_attr_name="刷新率",
            clean_attr_name="刷新率",
            raw_attr_value="-",
            value_presence="unknown",
            clean_record_key="attribute:attribute_data:2",
            clean_hash="sha256:test:attribute",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="warning",
            quality_flags=["unknown_value"],
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.add(
        entities.Core3CleanClaim(
            **common,
            source_table="selling_points_data",
            source_pk="3",
            source_row_id="selling_points_data:3",
            source_operation_type="insert",
            sku_code="TV00010001",
            model_name="85Q6N",
            brand_name="海信",
            claim_seq=1,
            clean_claim_text="画质清晰",
            claim_text_presence="present",
            clean_record_key="claim:selling_points_data:3",
            clean_hash="sha256:test:claim",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.add(
        entities.Core3CleanClaimSentence(
            project_id="real-project",
            category_code="TV",
            batch_id="m00_real_project",
            source_row_id="selling_points_data:3",
            clean_claim_id="claim-1",
            sku_code="TV00010001",
            claim_seq=1,
            sentence_seq=1,
            sentence_text="画质清晰",
            sentence_text_hash="sha256:test:claim_sentence_text",
            split_rule="punctuation",
            clean_record_key="claim_sentence:selling_points_data:3:1",
            clean_hash="sha256:test:claim_sentence",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
        )
    )
    _add_clean_comment(session, common, source_pk="4", comment_id="c-1", low_value=True)
    _add_clean_comment(session, common, source_pk="5", comment_id="c-2", low_value=False)
    session.add(
        entities.Core3CleanCommentSentence(
            project_id="real-project",
            category_code="TV",
            batch_id="m00_real_project",
            source_row_id="comment_data:5",
            clean_comment_id="comment-5",
            sku_code="TV00010001",
            comment_id="c-2",
            sentence_source="system_split",
            sentence_seq=1,
            sentence_text="画质很好",
            sentence_text_hash="sha256:test:comment_sentence_text",
            split_rule="punctuation",
            clean_record_key="comment_sentence:comment_data:5:1",
            clean_hash="sha256:test:comment_sentence",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="ok",
        )
    )
    for source_pk, available in [("4", False), ("5", True)]:
        session.add(
            entities.Core3CleanCommentDimension(
                project_id="real-project",
                category_code="TV",
                batch_id="m00_real_project",
                source_row_id=f"comment_data:{source_pk}",
                clean_comment_id=f"comment-{source_pk}",
                sku_code="TV00010001",
                comment_id=f"c-{source_pk}",
                dimension_available=available,
                clean_record_key=f"comment_dimension:comment_data:{source_pk}",
                clean_hash=f"sha256:test:comment_dimension:{source_pk}",
                clean_version="m01_clean_v1",
                hash_version="m01_clean_hash_v1",
                quality_status="ok",
            )
        )
    session.add(
        entities.Core3DataQualityIssue(
            project_id="real-project",
            category_code="TV",
            batch_id="m00_real_project",
            module_code="M01",
            domain="param",
            source_table="attribute_data",
            source_row_id="attribute_data:2",
            clean_table="core3_clean_attribute",
            clean_record_key="attribute:attribute_data:2",
            sku_code="TV00010001",
            issue_type="unknown_value",
            severity="info",
            issue_detail="TV00010001 存在空值、unknown 或横杠等未知值",
            issue_payload_json={"attribute": {"unknown": True}},
            suggested_downstream_action="按 unknown 处理，不能解释为 false",
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )
    session.commit()


def _add_clean_comment(
    session: Session,
    common: dict,
    *,
    source_pk: str,
    comment_id: str,
    low_value: bool,
    record_status: str = Core3CleanRecordStatus.ACTIVE.value,
    clean_comment_text: str | None = None,
) -> None:
    reason = "服务履约评价" if low_value else None
    session.add(
        entities.Core3CleanComment(
            **common,
            source_table="comment_data",
            source_pk=source_pk,
            source_row_id=f"comment_data:{source_pk}",
            source_operation_type="insert",
            sku_code="TV00010001",
            model_name="85Q6N",
            brand_name="海信",
            comment_id=comment_id,
            clean_comment_text=clean_comment_text or ("安装很快" if low_value else "画质很好"),
            comment_text_presence="present",
            comment_text_hash=f"sha256:test:comment_text:{source_pk}",
            sentiment_clean="positive",
            low_value_flag=low_value,
            low_value_reason=reason,
            duplicate_group_key="dup-service" if low_value else None,
            dimension_available=not low_value,
            clean_record_key=f"comment:comment_data:{source_pk}",
            clean_hash=f"sha256:test:comment:{source_pk}",
            clean_version="m01_clean_v1",
            hash_version="m01_clean_hash_v1",
            quality_status="warning" if low_value else "ok",
            record_status=record_status,
            review_required=False,
            review_status=Core3ReviewStatus.AUTO_PASS.value,
        )
    )


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
