from app.services.core3_real_data.constants import (
    CORE3_M00_ROW_HASH_VERSION,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3SourceOperationType,
)
from app.services.core3_real_data.source_registry_service import (
    PreviousSourceRow,
    SourceFieldPresenceService,
    SourceImpactPlanner,
    SourceOperationClassifier,
    SourceRowAnalyzer,
    SourceRowHashService,
    SourceRowIdentity,
    SourceRowIdentityService,
)


def week_sales_row(**overrides):
    row = {
        "id": 123,
        "model_code": "TV00029115",
        "category": "彩电",
        "brand": "海信",
        "model": "85E7Q",
        "date_value": "26W01",
        "channel": "线上",
        "platform": "专业电商",
        "sales_volume": 10,
        "sales_amount": 59990,
        "avg_price": 5999,
        "write_time": "2026-06-11T10:00:00+08:00",
    }
    row.update(overrides)
    return row


def test_source_row_identity_is_stable_and_requires_source_pk():
    service = SourceRowIdentityService()

    identity = service.build_identity("week_sales_data", week_sales_row())

    assert identity.source_pk == "123"
    assert identity.source_row_id == "week_sales_data:123"
    assert service.build_identity("week_sales_data", week_sales_row(id=None)).source_row_id is None


def test_row_hash_is_independent_of_input_field_order():
    hash_service = SourceRowHashService()
    ordered_row = week_sales_row()
    reversed_row = dict(reversed(list(ordered_row.items())))

    assert hash_service.compute_row_hash("week_sales_data", ordered_row) == hash_service.compute_row_hash(
        "week_sales_data",
        reversed_row,
    )


def test_row_hash_preserves_missing_like_values_and_missing_columns():
    hash_service = SourceRowHashService()
    null_hash = hash_service.compute_row_hash("attribute_data", {"id": 1, "attr_value": None})
    empty_hash = hash_service.compute_row_hash("attribute_data", {"id": 1, "attr_value": ""})
    dash_hash = hash_service.compute_row_hash("attribute_data", {"id": 1, "attr_value": "-"})
    unknown_hash = hash_service.compute_row_hash("attribute_data", {"id": 1, "attr_value": "unknown"})
    missing_column_hash = hash_service.compute_row_hash("attribute_data", {"id": 1})

    assert len({null_hash, empty_hash, dash_hash, unknown_hash, missing_column_hash}) == 5
    assert null_hash.startswith(f"sha256:{CORE3_M00_ROW_HASH_VERSION}:")


def test_field_presence_distinguishes_raw_presence_states():
    service = SourceFieldPresenceService()
    row = {
        "id": 1,
        "model_code": "",
        "model": "-",
        "brand": "unknown",
        "category": None,
        "write_time": "2026-06-11T10:00:00+08:00",
        "comment_id": "c1",
        "comment_content": "",
        "comments_segments": "unknown",
        "primary_dim": "-",
        "secondary_dim": None,
    }

    presence = service.build_field_presence("comment_data", row)

    assert presence["source_pk"] == "present"
    assert presence["model_code"] == "empty_string"
    assert presence["model"] == "dash"
    assert presence["brand"] == "unknown_literal"
    assert presence["category"] == "null"
    assert presence["business_fields"]["third_dim"] == "missing_column"


def test_operation_classifier_covers_insert_update_no_change_skipped_and_not_seen():
    classifier = SourceOperationClassifier()
    identity = SourceRowIdentity(source_table="week_sales_data", source_pk="123", source_row_id="week_sales_data:123")

    assert classifier.classify(identity, "hash-new").operation_type == Core3SourceOperationType.INSERT
    assert (
        classifier.classify(identity, "hash-old", PreviousSourceRow(batch_id="m00_old", row_hash="hash-old")).operation_type
        == Core3SourceOperationType.NO_CHANGE
    )
    assert (
        classifier.classify(identity, "hash-new", PreviousSourceRow(batch_id="m00_old", row_hash="hash-old")).operation_type
        == Core3SourceOperationType.UPDATE
    )

    skipped = classifier.classify(
        SourceRowIdentity(source_table="week_sales_data", source_pk=None, source_row_id=None),
        None,
    )
    assert skipped.operation_type == Core3SourceOperationType.SKIPPED
    assert skipped.review_required is True
    assert "missing_source_pk" in skipped.quality_hint["codes"]

    not_seen = classifier.classify_not_seen(PreviousSourceRow(batch_id="m00_old", row_hash="hash-old"))
    assert not_seen.operation_type == Core3SourceOperationType.NOT_SEEN_IN_CURRENT_SCAN
    assert not_seen.review_required is True


def test_source_impact_planner_maps_tables_to_downstream_modules_without_m16():
    planner = SourceImpactPlanner()

    week_modules = planner.affected_module_codes("week_sales_data", Core3SourceOperationType.UPDATE)
    comment_modules = planner.affected_module_codes("comment_data", Core3SourceOperationType.INSERT)

    assert Core3ModuleCode.M07 in week_modules
    assert Core3ModuleCode.M05 in comment_modules
    assert Core3ModuleCode.M16 not in week_modules
    assert planner.affected_module_codes("week_sales_data", Core3SourceOperationType.NO_CHANGE) == ()
    assert planner.affected_modules("attribute_data", Core3SourceOperationType.UPDATE)[0]["module_code"] == "M01"


def test_source_row_analyzer_combines_identity_hash_presence_operation_and_quality():
    analyzer = SourceRowAnalyzer()

    analysis = analyzer.analyze("week_sales_data", week_sales_row())

    assert analysis.source_row_id == "week_sales_data:123"
    assert analysis.row_hash is not None
    assert analysis.operation_type == Core3SourceOperationType.INSERT
    assert analysis.business_key_json == {
        "date_value": "26W01",
        "channel": "线上",
        "platform": "专业电商",
    }
    assert analysis.quality_hint == {"status": "ok", "codes": []}
    assert analysis.review_required is False
    assert analysis.review_status == Core3ReviewStatus.AUTO_PASS
    assert any(module["module_code"] == "M07" for module in analysis.affected_modules)

    skipped = analyzer.analyze("week_sales_data", week_sales_row(id=""))
    assert skipped.operation_type == Core3SourceOperationType.SKIPPED
    assert skipped.review_required is True
    assert skipped.review_status == Core3ReviewStatus.REVIEW_REQUIRED
    assert "missing_source_pk" in skipped.quality_hint["codes"]


def test_source_row_analyzer_marks_missing_sku_and_write_time_as_quality_hints():
    analyzer = SourceRowAnalyzer()

    analysis = analyzer.analyze("week_sales_data", week_sales_row(model_code="", write_time=None))

    assert analysis.operation_type == Core3SourceOperationType.INSERT
    assert analysis.review_required is True
    assert analysis.quality_hint["status"] == "review"
    assert "missing_sku_code_candidate" in analysis.quality_hint["codes"]
    assert "missing_write_time" in analysis.quality_hint["codes"]
