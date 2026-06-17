import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    CleanAttributeRead,
    CleanClaimRead,
    CleanCommentRead,
    CleanCoverageSummary,
    CleanMarketRead,
    CleanQualityIssueRead,
    CleanQualityStatus,
    CleanRecordStatus,
    CleanSkuSummary,
    CleaningCounts,
    CleaningRunRequest,
    CleaningRunResult,
    QualityIssueCounts,
    QualityIssueSeverity,
    QualityIssueType,
    ReviewStatus,
    ValuePresence,
)
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    CORE3_M01_MODULE_VERSION,
    Core3DataDomain,
    Core3ModuleCode,
    Core3RunStatus,
    Core3SourceOperationType,
)


def test_m01_cleaning_enums_match_sop_contract():
    assert [item.value for item in ValuePresence] == [
        "present",
        "null",
        "empty",
        "dash",
        "unknown_literal",
        "missing_column",
    ]
    assert [item.value for item in CleanRecordStatus] == ["active", "inactive_candidate", "skipped"]
    assert [item.value for item in CleanQualityStatus] == ["ok", "warning", "error"]
    assert [item.value for item in ReviewStatus] == [
        "auto_pass",
        "review_required",
        "approved",
        "rejected",
        "waived",
    ]
    assert [item.value for item in QualityIssueSeverity] == ["info", "warning", "error"]
    assert {item.value for item in QualityIssueType} >= {
        "missing_required_field",
        "invalid_number",
        "negative_number",
        "price_check_mismatch",
        "unknown_value",
        "cross_table_conflict",
        "claim_coverage_missing",
        "claim_seq_parse_failed",
        "low_value_comment",
        "duplicate_comment_text",
        "comment_dimension_missing",
        "comment_split_row_suspected",
        "schema_changed",
        "clean_hash_changed_high",
    }


def test_cleaning_run_request_defaults_to_m01_versions():
    request = CleaningRunRequest(project_id="core3_mvp", batch_id="m00_202606130001")

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "mode": "incremental",
        "module_version": CORE3_M01_MODULE_VERSION,
        "clean_version": CORE3_M01_CLEAN_VERSION,
        "hash_version": CORE3_M01_CLEAN_HASH_VERSION,
        "triggered_by": "system",
        "force_rebuild": False,
    }

    with pytest.raises(ValidationError):
        CleaningRunRequest(project_id="", batch_id="m00_202606130001")


def test_cleaning_counts_and_issue_counts_validate_non_negative_values():
    counts = CleaningCounts(sku=35, market=46, attribute=81, claim=0, comment=3621)
    issues = QualityIssueCounts(
        warning=1,
        by_type={
            QualityIssueType.CLAIM_COVERAGE_MISSING.value: 1,
        },
    )
    result = CleaningRunResult(
        batch_id="m00_202606130001",
        status=Core3RunStatus.WARNING,
        clean_counts=counts,
        issue_counts=issues,
        review_required=True,
    )

    payload = result.model_dump()
    assert payload["module_code"] == "M01"
    assert payload["status"] == "warning"
    assert payload["clean_counts"]["comment"] == 3621
    assert payload["issue_counts"]["by_type"] == {"claim_coverage_missing": 1}

    with pytest.raises(ValidationError):
        CleaningCounts(sku=-1)
    with pytest.raises(ValidationError, match="unknown issue_type"):
        QualityIssueCounts(by_type={"future_business_score_issue": 1})
    with pytest.raises(ValidationError, match="negative issue count"):
        QualityIssueCounts(by_type={"missing_required_field": -1})


def test_clean_sku_summary_keeps_cleaning_boundary_without_business_outputs():
    sku = CleanSkuSummary(
        clean_sku_id="m01sku_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        model_name="85E7Q",
        brand_name="海信",
        source_tables=["week_sales_data", "attribute_data", "comment_data"],
        coverage=CleanCoverageSummary(
            market={"row_count": 46, "covered": True},
            attribute={"row_count": 81, "covered": True},
            claim={"row_count": 0, "covered": False},
            comment={"row_count": 3621, "covered": True},
            missing_signals={"claim_structured": True},
        ),
        quality_status=CleanQualityStatus.WARNING,
        quality_flags=["claim_coverage_missing"],
        review_required=True,
        review_status=ReviewStatus.REVIEW_REQUIRED,
        clean_hash="sha256:m01_clean_hash_v1:abc",
    )

    payload = sku.model_dump()
    assert payload["quality_status"] == "warning"
    assert payload["coverage"]["claim"]["covered"] is False
    assert "evidence_ids" not in payload
    assert "task_scores" not in payload
    assert "battlefield_scores" not in payload

    with pytest.raises(ValidationError, match="unknown source_tables"):
        CleanSkuSummary(
            clean_sku_id="m01sku_002",
            project_id="core3_mvp",
            batch_id="m00_202606130001",
            sku_code="TV00010001",
            source_tables=["raw_business_score"],
            clean_hash="sha256:m01_clean_hash_v1:def",
        )


def test_clean_fact_read_schemas_serialize_m01_contracts():
    market = CleanMarketRead(
        clean_market_id="m01market_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        source_table="week_sales_data",
        source_pk="1",
        source_row_id="week_sales_data:1",
        source_operation_type=Core3SourceOperationType.INSERT,
        sku_code="TV00029115",
        period_raw="2026W01",
        period_parse_status="parsed",
        sales_volume="12.0",
        sales_amount="96000.0",
        avg_price="8000.0",
        price_check_status="ok",
        clean_record_key="market:week_sales_data:1",
        clean_hash="sha256:m01_clean_hash_v1:market",
        created_at="2026-06-13T00:00:00Z",
    )
    attribute = CleanAttributeRead(
        clean_attribute_id="m01attr_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        source_table="attribute_data",
        source_pk="2",
        source_row_id="attribute_data:2",
        source_operation_type=Core3SourceOperationType.UPDATE,
        sku_code="TV00029115",
        raw_attr_name="刷新率",
        clean_attr_name="刷新率",
        raw_attr_value="-",
        clean_attr_value=None,
        value_presence=ValuePresence.DASH,
        clean_record_key="attribute:attribute_data:2",
        clean_hash="sha256:m01_clean_hash_v1:attr",
        created_at="2026-06-13T00:00:00Z",
    )
    claim = CleanClaimRead(
        clean_claim_id="m01claim_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        source_table="selling_points_data",
        source_pk="3",
        source_row_id="selling_points_data:3",
        source_operation_type=Core3SourceOperationType.INSERT,
        sku_code="TV00029115",
        claim_text_presence=ValuePresence.EMPTY,
        clean_record_key="claim:selling_points_data:3",
        clean_hash="sha256:m01_clean_hash_v1:claim",
        created_at="2026-06-13T00:00:00Z",
    )
    comment = CleanCommentRead(
        clean_comment_id="m01comment_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        source_table="comment_data",
        source_pk="4",
        source_row_id="comment_data:4",
        source_operation_type=Core3SourceOperationType.INSERT,
        sku_code="TV00029115",
        comment_time_parse_status="missing",
        comment_text_presence=ValuePresence.UNKNOWN_LITERAL,
        clean_record_key="comment:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:comment",
        created_at="2026-06-13T00:00:00Z",
    )

    assert market.model_dump()["sales_volume"] == market.sales_volume
    assert attribute.model_dump()["value_presence"] == "dash"
    assert claim.model_dump()["claim_text_presence"] == "empty"
    assert comment.model_dump()["comment_text_presence"] == "unknown_literal"

    with pytest.raises(ValidationError, match="unknown source_table"):
        CleanMarketRead(
            **{
                **market.model_dump(),
                "source_table": "future_profile_table",
            }
        )


def test_clean_quality_issue_read_validates_m01_issue_contract():
    issue = CleanQualityIssueRead(
        issue_id="m01issue_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        domain=Core3DataDomain.CLAIM,
        source_table="selling_points_data",
        source_row_id="selling_points_data:3",
        clean_table="core3_clean_sku",
        clean_record_key="sku:TV00029115",
        sku_code="TV00029115",
        issue_type=QualityIssueType.CLAIM_COVERAGE_MISSING,
        severity=QualityIssueSeverity.WARNING,
        issue_detail="85E7Q 缺少结构化卖点来源，只能在下游作为未知处理",
        issue_payload_json={"coverage": {"claim": {"covered": False}}},
        suggested_downstream_action="M04a 不得伪造卖点事实",
        review_required=True,
        review_status=ReviewStatus.REVIEW_REQUIRED,
        created_at="2026-06-13T00:00:00Z",
    )

    payload = issue.model_dump()
    assert payload["module_code"] == Core3ModuleCode.M01.value
    assert payload["issue_type"] == "claim_coverage_missing"
    assert payload["severity"] == "warning"
    assert payload["domain"] == "claim"

    with pytest.raises(ValidationError, match="unknown source_table"):
        CleanQualityIssueRead(
            **{
                **payload,
                "source_table": "future_business_output",
            }
        )
