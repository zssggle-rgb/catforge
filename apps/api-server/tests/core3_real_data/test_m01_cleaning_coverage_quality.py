from app.services.core3_real_data.cleaning_quality_service import CleanSkuBuilder, QualityIssueBuilder


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"
RUN_ID = "run-m01-f"
MODULE_RUN_ID = "module-run-m01-f"
SKU_CODE = "TV00029115"


def base_payload(domain: str, source_table: str, source_pk: str, **overrides):
    payload = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "source_table": source_table,
        "source_pk": source_pk,
        "source_row_id": f"{source_table}:{source_pk}",
        "source_row_hash": f"sha256:m00_row_hash_v1:{source_pk}",
        "source_operation_type": "insert",
        "sku_code": SKU_CODE,
        "model_name": "85E7Q",
        "brand_name": "海信",
        "clean_record_key": f"{domain}:{source_table}:{source_pk}",
        "clean_hash": f"sha256:m01_clean_hash_v1:{domain}:{source_pk}",
        "clean_version": "m01_clean_v1",
        "hash_version": "m01_clean_hash_v1",
        "quality_status": "ok",
        "quality_flags": [],
    }
    payload.update(overrides)
    return payload


def test_clean_sku_builder_aggregates_four_domain_coverage_and_missing_claim_signal():
    markets = [
        base_payload("market", "week_sales_data", "1", category_name_raw="彩电"),
        base_payload("market", "week_sales_data", "2", category_name_raw="彩电"),
    ]
    attributes = [
        base_payload(
            "attribute",
            "attribute_data",
            "10",
            clean_attr_name="刷新率",
            value_presence="present",
        ),
        base_payload(
            "attribute",
            "attribute_data",
            "11",
            clean_attr_name="亮度",
            value_presence="dash",
            quality_status="warning",
            quality_flags=["unknown_value"],
        ),
    ]
    comments = [
        base_payload(
            "comment",
            "comment_data",
            "20",
            comment_id="c-1",
            clean_comment_text="画质很好",
        ),
        base_payload(
            "comment",
            "comment_data",
            "21",
            comment_id="c-2",
            clean_comment_text="游戏低延迟",
        ),
        base_payload(
            "comment",
            "comment_data",
            "22",
            comment_id="c-2",
            clean_comment_text="重复 comment_id 也保留事实",
        ),
    ]

    result = CleanSkuBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        markets=markets,
        attributes=attributes,
        claims=[],
        comments=comments,
    )

    assert len(result.skus) == 1
    sku = result.skus[0]
    assert sku["sku_code"] == SKU_CODE
    assert sku["model_name"] == "85E7Q"
    assert sku["brand_name"] == "海信"
    assert sku["coverage_json"] == {
        "market": {"row_count": 2, "covered": True},
        "attribute": {"row_count": 2, "covered": True, "unknown_count": 1},
        "claim": {"row_count": 0, "covered": False},
        "comment": {"row_count": 3, "covered": True, "distinct_comment_id_count": 2},
    }
    assert sku["missing_signals_json"]["claim_structured"] == {
        "missing": True,
        "reason": "本批 selling_points_data 未覆盖该 SKU",
        "business_interpretation": "结构化卖点数据缺失，不代表该 SKU 没有卖点",
    }
    assert sku["quality_status"] == "warning"
    assert sku["quality_flags"] == ["claim_coverage_missing"]
    assert sku["review_required"] is True
    assert sku["clean_record_key"] == f"sku:{SKU_CODE}"
    assert sku["clean_hash"].startswith("sha256:m01_clean_hash_v1:")
    assert "task_code" not in sku
    assert "battlefield_code" not in sku


def test_clean_sku_builder_detects_cross_table_brand_conflict_without_business_conclusion():
    markets = [base_payload("market", "week_sales_data", "1", brand_name="海信")]
    attributes = [base_payload("attribute", "attribute_data", "10", brand_name="Vidda", value_presence="present")]
    claims = [base_payload("claim", "selling_points_data", "30", brand_name="海信", clean_claim_text="游戏低延迟")]

    sku = CleanSkuBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        markets=markets,
        attributes=attributes,
        claims=claims,
    ).skus[0]

    assert sku["coverage_json"]["claim"]["covered"] is True
    assert sku["field_conflicts_json"]["brand"] == {"has_conflict": True, "values": ["海信", "Vidda"]}
    assert sku["quality_flags"] == ["cross_table_conflict"]
    assert sku["missing_signals_json"] == {}
    assert "competitor_sku_code" not in sku


def test_quality_issue_builder_outputs_coverage_and_domain_quality_issues():
    market = base_payload(
        "market",
        "week_sales_data",
        "1",
        quality_status="warning",
        quality_flags=["price_check_mismatch"],
        avg_price="8200",
        avg_price_expected="8000",
        price_check_delta="200",
    )
    attribute = base_payload(
        "attribute",
        "attribute_data",
        "10",
        raw_attr_name="刷新率",
        raw_attr_value="-",
        value_presence="dash",
        quality_status="warning",
        quality_flags=["unknown_value"],
    )
    clean_sku = CleanSkuBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        markets=[market],
        attributes=[attribute],
        claims=[],
        comments=[],
    ).skus[0]

    issues = QualityIssueBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_id=RUN_ID,
        module_run_id=MODULE_RUN_ID,
        clean_skus=[clean_sku],
        markets=[market],
        attributes=[attribute],
    ).issues

    issue_types = [issue["issue_type"] for issue in issues]
    assert issue_types == ["claim_coverage_missing", "price_check_mismatch", "unknown_value"]
    claim_issue = issues[0]
    assert claim_issue["domain"] == "claim"
    assert claim_issue["severity"] == "warning"
    assert claim_issue["review_required"] is True
    assert claim_issue["issue_detail"] == "结构化卖点数据缺失，不代表该 SKU 没有卖点"
    assert claim_issue["suggested_downstream_action"] == "M04a 不得伪造卖点事实，后续只能按未知处理"
    assert issues[1]["issue_payload_json"] == {
        "avg_price": "8200",
        "avg_price_expected": "8000",
        "price_check_delta": "200",
    }
    assert issues[2]["suggested_downstream_action"] == "下游必须按 unknown 处理，不能解释为 false"


def test_quality_issue_builder_detects_duplicate_comments_and_dimension_missing():
    comment_a = base_payload(
        "comment",
        "comment_data",
        "20",
        comment_id="c-20",
        clean_comment_text="画质很好",
        comment_text_hash="same-hash",
    )
    comment_b = base_payload(
        "comment",
        "comment_data",
        "21",
        comment_id="c-21",
        clean_comment_text="画质很好",
        comment_text_hash="same-hash",
    )
    dimension = base_payload(
        "comment_dimension",
        "comment_data",
        "20",
        comment_id="c-20",
        clean_record_key="comment_dimension:comment_data:20",
        dimension_available=False,
        dimension_path_raw=None,
        quality_status="warning",
        quality_flags=["comment_dimension_missing"],
    )

    issues = QualityIssueBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        comments=[comment_a, comment_b],
        comment_dimensions=[dimension],
    ).issues

    assert [issue["issue_type"] for issue in issues] == [
        "comment_dimension_missing",
        "duplicate_comment_text",
        "duplicate_comment_text",
    ]
    assert issues[0]["suggested_downstream_action"] == "M05/M06 不得把缺失维度解释为无对应主题"
    assert issues[1]["issue_payload_json"] == {"comment_text_hash": "same-hash", "duplicate_count": 2}
    assert all("task_code" not in issue for issue in issues)


def test_quality_issue_builder_dedupes_same_quality_issue_key():
    attribute = base_payload(
        "attribute",
        "attribute_data",
        "10",
        value_presence="dash",
        quality_status="warning",
        quality_flags=["unknown_value", "unknown_value"],
    )

    issues = QualityIssueBuilder().build(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        attributes=[attribute],
    ).issues

    assert len(issues) == 1
    assert issues[0]["issue_type"] == "unknown_value"
