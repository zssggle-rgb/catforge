from app.services.core3_real_data.constants import (
    CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS,
    CORE3_DATA_DOMAIN_LABEL_CN,
    CORE3_DATA_DOMAIN_START_MODULE,
    CORE3_M00_MODULE_VERSION,
    CORE3_M00_ROW_HASH_VERSION,
    CORE3_MODULE_DAG_EDGES,
    CORE3_MODULE_LABEL_CN,
    CORE3_MODULE_ORDER,
    CORE3_RAW_SOURCE_TABLES,
    CORE3_TARGET_BRAND_85E7Q,
    CORE3_TARGET_MODEL_85E7Q,
    CORE3_TARGET_SKU_85E7Q,
    Core3DataDomain,
    Core3FieldPresenceStatus,
    Core3ModuleCode,
    Core3ReviewStatus,
    Core3SourceBatchStatus,
    Core3SourceBatchType,
    Core3SourceImpactLevel,
    Core3SourceOperationType,
    Core3SourcePkStrategy,
)


def test_module_order_matches_sop_sequence():
    assert [module.value for module in CORE3_MODULE_ORDER] == [
        "M00",
        "M01",
        "M02",
        "M03",
        "M04a",
        "M05",
        "M06",
        "M04b",
        "M07",
        "M08",
        "M08.4",
        "M08.5",
        "M09",
        "M10",
        "M11",
        "M11.5",
        "M11.6",
        "M11.7",
        "M12",
        "M13",
        "M14",
        "M15",
        "M16",
    ]


def test_module_dag_edges_only_reference_known_modules():
    known_modules = set(CORE3_MODULE_ORDER)

    assert CORE3_MODULE_DAG_EDGES
    assert all(source in known_modules and target in known_modules for source, target in CORE3_MODULE_DAG_EDGES)
    assert (Core3ModuleCode.M00, Core3ModuleCode.M01) in CORE3_MODULE_DAG_EDGES
    assert (Core3ModuleCode.M14, Core3ModuleCode.M15) in CORE3_MODULE_DAG_EDGES
    assert (Core3ModuleCode.M15, Core3ModuleCode.M16) in CORE3_MODULE_DAG_EDGES


def test_data_domain_mapping_and_labels_are_complete():
    assert set(CORE3_DATA_DOMAIN_START_MODULE) == set(Core3DataDomain)
    assert set(CORE3_DATA_DOMAIN_LABEL_CN) == set(Core3DataDomain)
    assert set(CORE3_MODULE_LABEL_CN) == set(Core3ModuleCode)
    assert CORE3_DATA_DOMAIN_START_MODULE[Core3DataDomain.COMMENT] == Core3ModuleCode.M05
    assert CORE3_DATA_DOMAIN_START_MODULE[Core3DataDomain.REPORT] == Core3ModuleCode.M15


def test_85e7q_fixture_identity_constants_are_business_values():
    assert CORE3_TARGET_MODEL_85E7Q == "85E7Q"
    assert CORE3_TARGET_SKU_85E7Q == "TV00029115"
    assert CORE3_TARGET_BRAND_85E7Q == "海信"


def test_business_display_forbidden_patterns_cover_internal_leakage_classes():
    joined_patterns = "\n".join(CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS)

    assert "SELECT" in joined_patterns
    assert "core3_" in joined_patterns
    assert "review_required" in joined_patterns
    assert "AI 认为" in joined_patterns


def test_m00_source_registry_constants_match_real_source_contract():
    assert CORE3_RAW_SOURCE_TABLES == (
        "week_sales_data",
        "attribute_data",
        "selling_points_data",
        "comment_data",
    )
    assert CORE3_M00_MODULE_VERSION == "m00-source-registry-0.1.0"
    assert CORE3_M00_ROW_HASH_VERSION == "m00_row_hash_v1"

    assert [item.value for item in Core3SourceBatchType] == ["full", "incremental"]
    assert [item.value for item in Core3SourceBatchStatus] == [
        "running",
        "registered",
        "registered_with_warning",
        "failed",
    ]
    assert [item.value for item in Core3SourceOperationType] == [
        "insert",
        "update",
        "no_change",
        "not_seen_in_current_scan",
        "skipped",
    ]
    assert [item.value for item in Core3SourceImpactLevel] == ["none", "low", "medium", "high"]
    assert [item.value for item in Core3SourcePkStrategy] == [
        "id_column",
        "business_key_hash",
        "composite_key",
    ]
    assert [item.value for item in Core3ReviewStatus] == [
        "auto_pass",
        "review_required",
        "approved",
        "rejected",
        "waived",
    ]
    assert [item.value for item in Core3FieldPresenceStatus] == [
        "present",
        "null",
        "empty_string",
        "dash",
        "unknown_literal",
        "missing_column",
    ]
