import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    Core3ModuleRunResultSchema,
    Core3ReleaseGateSchema,
    Core3ReviewIssueSchema,
    Core3RunContextSchema,
    Core3SourceBatchListOut,
    Core3SourceBatchOut,
    Core3SourceBatchRegisterApiRequest,
    Core3SourceBatchRegisterRequest,
    Core3SourceImpactedSkuListOut,
    Core3SourceImpactedSkuOut,
    Core3SourceRowRegistryListOut,
    Core3SourceRowRegistryOut,
    Core3SourceTableWatermarkOut,
    Core3TargetScopeSchema,
)
from app.services.core3_real_data.constants import (
    Core3CategoryCode,
    Core3DataDomain,
    Core3ModuleCode,
    Core3ReleaseGateStatus,
    Core3ReviewStatus,
    Core3ReviewSeverity,
    Core3RunMode,
    Core3RunStatus,
    Core3SourceBatchStatus,
    Core3SourceBatchType,
    Core3SourceImpactLevel,
    Core3SourceOperationType,
    Core3SourcePkStrategy,
    Core3TargetScopeType,
)


def test_run_context_schema_serializes_enum_values():
    context = Core3RunContextSchema(
        run_id="run-001",
        project_id="project-001",
        category_code=Core3CategoryCode.TV,
        run_mode=Core3RunMode.BOOTSTRAP_FULL,
        module_versions={Core3ModuleCode.M00.value: "source-registry-1.0.0"},
        seed_versions={"claim_seed": "tv-claim-seed-2026-06"},
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.DEMO_TARGET,
            sku_codes=["TV00029115"],
            data_domains=[Core3DataDomain.MARKET, Core3DataDomain.PARAM, Core3DataDomain.COMMENT],
            note_cn="85E7Q 单目标刷新",
        ),
    )

    payload = context.model_dump()
    assert payload["category_code"] == "TV"
    assert payload["run_mode"] == "bootstrap_full"
    assert payload["target_scope"]["scope_type"] == "demo_target"
    assert payload["target_scope"]["data_domains"] == ["market", "param", "comment"]


def test_module_run_result_schema_requires_non_negative_counts():
    issue = Core3ReviewIssueSchema(
        issue_code="claim_coverage_missing",
        issue_type="missing_structured_claim",
        severity=Core3ReviewSeverity.MEDIUM,
        source_module=Core3ModuleCode.M04A,
        object_type="claim",
        target_sku_code="TV00029115",
        message_cn="85E7Q 缺少结构化宣传卖点数据",
        confidence=0.8,
    )

    result = Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode.M04A,
        status=Core3RunStatus.REVIEW_REQUIRED,
        input_count=35,
        changed_input_count=1,
        output_count=34,
        warnings=["宣传卖点覆盖有限"],
        review_issues=[issue],
        summary_json={"target_sku_code": "TV00029115"},
    )

    assert result.model_dump()["module_code"] == "M04a"
    assert result.model_dump()["review_issues"][0]["severity"] == "medium"

    with pytest.raises(ValidationError):
        Core3ModuleRunResultSchema(
            module_code=Core3ModuleCode.M00,
            status=Core3RunStatus.SUCCESS,
            input_count=-1,
        )


def test_release_gate_schema_uses_shared_gate_status():
    gate = Core3ReleaseGateSchema(
        target_sku_code="TV00029115",
        gate_status=Core3ReleaseGateStatus.REVIEW_REQUIRED,
        reason_cn="存在宣传卖点数据缺口，需要人工复核",
        blocking_issue_codes=["claim_coverage_missing"],
    )

    assert gate.model_dump() == {
        "target_sku_code": "TV00029115",
        "gate_status": "review_required",
        "reason_cn": "存在宣传卖点数据缺口，需要人工复核",
        "blocking_issue_codes": ["claim_coverage_missing"],
        "checked_at": None,
    }


def test_core3_real_data_schemas_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        Core3TargetScopeSchema(scope_type=Core3TargetScopeType.ALL_SKU, unexpected=True)


def test_m00_source_batch_register_request_defaults_and_validates_source_tables():
    request = Core3SourceBatchRegisterRequest(project_id="core3_mvp")

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "batch_type": "full",
        "source_system": "postgresql_205",
        "source_database": "catforge_dev",
        "source_schema": "public",
        "source_tables": [
            "week_sales_data",
            "attribute_data",
            "selling_points_data",
            "comment_data",
        ],
        "ruleset_version": "tv-core3-real-data-v2-0.1.0",
        "module_version": "m00-source-registry-0.1.0",
        "hash_version": "m00_row_hash_v1",
        "triggered_by": "system",
        "note_cn": None,
    }

    with pytest.raises(ValidationError, match="unknown source_tables"):
        Core3SourceBatchRegisterRequest(project_id="core3_mvp", source_tables=["raw_sku_master"])

    with pytest.raises(ValidationError, match="source_tables must not be empty"):
        Core3SourceBatchRegisterRequest(project_id="core3_mvp", source_tables=[])


def test_m00_source_batch_register_api_request_uses_path_project_id():
    request = Core3SourceBatchRegisterApiRequest(source_tables=["week_sales_data"])

    assert request.model_dump()["source_tables"] == ["week_sales_data"]
    assert "project_id" not in request.model_dump()

    with pytest.raises(ValidationError, match="unknown source_tables"):
        Core3SourceBatchRegisterApiRequest(source_tables=["raw_sku_master"])

    with pytest.raises(ValidationError, match="source_tables must not be empty"):
        Core3SourceBatchRegisterApiRequest(source_tables=[])


def test_m00_source_batch_out_serializes_status_and_quality_payloads():
    batch = Core3SourceBatchOut(
        batch_id="m00_202606130001",
        project_id="core3_mvp",
        batch_type=Core3SourceBatchType.INCREMENTAL,
        source_system="postgresql_205",
        source_database="catforge_dev",
        source_schema="public",
        source_tables=["week_sales_data"],
        ruleset_version="tv-core3-real-data-v2-0.1.0",
        module_version="m00-source-registry-0.1.0",
        hash_version="m00_row_hash_v1",
        scan_started_at="2026-06-13T00:00:00Z",
        row_counts_json={"week_sales_data": {"insert": 3}},
        schema_snapshot_json={"week_sales_data": {"schema_status": "unchanged"}},
        impacted_sku_count=1,
        status=Core3SourceBatchStatus.REGISTERED_WITH_WARNING,
        review_required=True,
        review_status=Core3ReviewStatus.REVIEW_REQUIRED,
        review_reason={"codes": ["source_schema_changed"]},
        created_at="2026-06-13T00:00:01Z",
        updated_at="2026-06-13T00:00:02Z",
    )

    payload = batch.model_dump()
    assert payload["batch_type"] == "incremental"
    assert payload["status"] == "registered_with_warning"
    assert payload["review_status"] == "review_required"
    assert payload["row_counts_json"]["week_sales_data"]["insert"] == 3

    with pytest.raises(ValidationError):
        Core3SourceBatchOut(
            **{
                **payload,
                "impacted_sku_count": -1,
            }
        )


def test_m00_row_registry_and_impacted_sku_outputs_validate_source_contract():
    row = Core3SourceRowRegistryOut(
        row_registry_id="m00rr_001",
        batch_id="m00_202606130001",
        project_id="core3_mvp",
        source_table="attribute_data",
        source_pk="123",
        source_pk_strategy=Core3SourcePkStrategy.ID_COLUMN,
        source_row_id="attribute_data:123",
        row_hash="m00_row_hash_v1:abc",
        operation_type=Core3SourceOperationType.UPDATE,
        affected_modules=[Core3ModuleCode.M01, Core3ModuleCode.M03],
        quality_hint={"status": "ok"},
        created_at="2026-06-13T00:00:03Z",
    )

    assert row.model_dump()["operation_type"] == "update"
    assert row.model_dump()["affected_modules"] == ["M01", "M03"]
    assert row.model_dump()["source_pk_strategy"] == "id_column"

    impacted_sku = Core3SourceImpactedSkuOut(
        impacted_sku_id="m00sku_001",
        batch_id="m00_202606130001",
        project_id="core3_mvp",
        sku_code_candidate="TV00029115",
        source_tables=["attribute_data", "comment_data"],
        operation_summary_json={"total_changed_rows": 2},
        affected_modules=[Core3ModuleCode.M01, Core3ModuleCode.M08],
        impact_reason="参数和评论原始行发生变化",
        impact_level=Core3SourceImpactLevel.HIGH,
        created_at="2026-06-13T00:00:04Z",
    )

    assert impacted_sku.model_dump()["impact_level"] == "high"
    assert impacted_sku.model_dump()["needs_recompute"] is True

    with pytest.raises(ValidationError, match="unknown source_table"):
        Core3SourceRowRegistryOut(
            row_registry_id="m00rr_002",
            batch_id="m00_202606130001",
            project_id="core3_mvp",
            source_table="raw_sku_master",
            operation_type=Core3SourceOperationType.INSERT,
            created_at="2026-06-13T00:00:03Z",
        )

    with pytest.raises(ValidationError, match="unknown source_tables"):
        Core3SourceImpactedSkuOut(
            impacted_sku_id="m00sku_002",
            batch_id="m00_202606130001",
            project_id="core3_mvp",
            sku_code_candidate="TV00010001",
            source_tables=["raw_sku_master"],
            impact_reason="测试未知来源表",
            impact_level=Core3SourceImpactLevel.LOW,
            created_at="2026-06-13T00:00:04Z",
        )


def test_m00_batch_list_and_watermark_outputs_have_pagination_and_counts():
    batch = Core3SourceBatchOut(
        batch_id="m00_202606130001",
        project_id="core3_mvp",
        batch_type=Core3SourceBatchType.FULL,
        source_system="postgresql_205",
        source_database="catforge_dev",
        source_tables=["comment_data"],
        ruleset_version="tv-core3-real-data-v2-0.1.0",
        module_version="m00-source-registry-0.1.0",
        hash_version="m00_row_hash_v1",
        scan_started_at="2026-06-13T00:00:00Z",
        status=Core3SourceBatchStatus.REGISTERED,
        created_at="2026-06-13T00:00:01Z",
        updated_at="2026-06-13T00:00:02Z",
    )
    batch_list = Core3SourceBatchListOut(items=[batch], total=1, limit=20, offset=0)
    watermark = Core3SourceTableWatermarkOut(
        source_table="comment_data",
        row_count=62426,
        distinct_sku_count=35,
        schema_hash="sha256:test",
        schema_status="unchanged",
        candidate_rule="full_table_scan",
    )

    assert batch_list.model_dump()["items"][0]["batch_id"] == "m00_202606130001"
    assert watermark.model_dump()["row_count"] == 62426

    row_list = Core3SourceRowRegistryListOut(items=[], total=0, limit=20, offset=0)
    impacted_list = Core3SourceImpactedSkuListOut(items=[], total=0, limit=20, offset=0)
    assert row_list.model_dump()["items"] == []
    assert impacted_list.model_dump()["items"] == []

    with pytest.raises(ValidationError):
        Core3SourceBatchListOut(items=[], total=0, limit=0, offset=0)
    with pytest.raises(ValidationError):
        Core3SourceRowRegistryListOut(items=[], total=0, limit=0, offset=0)
    with pytest.raises(ValidationError):
        Core3SourceImpactedSkuListOut(items=[], total=0, limit=0, offset=0)
    with pytest.raises(ValidationError):
        Core3SourceTableWatermarkOut(source_table="comment_data", row_count=-1)
