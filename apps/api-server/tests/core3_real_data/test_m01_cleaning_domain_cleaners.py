from decimal import Decimal

from app.services.core3_real_data.cleaning_quality_service import (
    AttributeCleaner,
    ClaimCleaner,
    CleaningSourceContext,
    CommentCleaner,
    MarketCleaner,
)
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    Core3SourceOperationType,
)


def source_context(source_table: str, source_pk: str = "1") -> CleaningSourceContext:
    return CleaningSourceContext(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        run_id="run-m01-e",
        module_run_id="module-run-m01-e",
        source_table=source_table,
        source_pk=source_pk,
        source_row_id=f"{source_table}:{source_pk}",
        source_row_hash=f"sha256:m00_row_hash_v1:{source_pk}",
        source_operation_type=Core3SourceOperationType.INSERT,
    )


def assert_no_business_outputs(payload: dict) -> None:
    forbidden_fields = {
        "evidence_id",
        "evidence_ids",
        "param_code",
        "claim_code",
        "task_code",
        "target_group_code",
        "battlefield_code",
        "competitor_sku_code",
        "score",
        "rank",
        "report_payload",
    }
    assert forbidden_fields.isdisjoint(payload)


def test_market_cleaner_parses_week_numbers_decimals_and_price_check():
    result = MarketCleaner().clean(
        {
            "id": 10,
            "model_code": "TV00029115",
            "category": "彩电",
            "brand": "海信",
            "model": "85E7Q",
            "date_value": "26W01",
            "channel": "线上",
            "platform": "专业电商",
            "sales_volume": "12",
            "sales_amount": "96,000",
            "avg_price": "8200",
        },
        source_context("week_sales_data", "10"),
    )

    payload = result.market
    assert payload["source_table"] == "week_sales_data"
    assert payload["sku_code"] == "TV00029115"
    assert payload["period_type"] == "week"
    assert payload["period_year_hint"] == 2026
    assert payload["period_week_index"] == 1
    assert payload["sales_volume"] == Decimal("12")
    assert payload["sales_amount"] == Decimal("96000")
    assert payload["avg_price_expected"] == Decimal("8000")
    assert payload["price_check_status"] == "mismatch"
    assert payload["quality_status"] == "warning"
    assert "price_check_mismatch" in payload["quality_flags"]
    assert payload["clean_record_key"] == "market:week_sales_data:10"
    assert payload["clean_hash"].startswith(f"sha256:{CORE3_M01_CLEAN_HASH_VERSION}:")
    assert_no_business_outputs(payload)


def test_attribute_cleaner_preserves_unknown_value_without_false_mapping():
    result = AttributeCleaner().clean(
        {
            "id": 20,
            "model_code": "TV00029115",
            "category": "彩电",
            "brand": "海信",
            "model": "85E7Q",
            "attr_name": "刷新率",
            "attr_value": "-",
        },
        source_context("attribute_data", "20"),
    )

    payload = result.attribute
    assert payload["raw_attr_name"] == "刷新率"
    assert payload["clean_attr_name"] == "刷新率"
    assert payload["raw_attr_value"] == "-"
    assert payload["clean_attr_value"] is None
    assert payload["value_presence"] == "dash"
    assert payload["quality_status"] == "warning"
    assert payload["quality_flags"] == ["unknown_value"]
    assert payload["conflict_group_key"] == "TV00029115:刷新率"
    assert_no_business_outputs(payload)


def test_attribute_cleaner_extracts_number_and_unit_candidates_without_standard_param_code():
    result = AttributeCleaner().clean(
        {
            "id": 21,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "attr_name": "屏幕刷新率",
            "attr_value": "300HZ",
        },
        source_context("attribute_data", "21"),
    )

    payload = result.attribute
    assert payload["value_presence"] == "present"
    assert payload["value_number_candidates"] == [{"number": "300", "unit": "HZ"}]
    assert payload["value_unit_candidates"] == ["HZ"]
    assert payload["quality_status"] == "ok"
    assert "param_code" not in payload


def test_claim_cleaner_generates_claim_and_sentences_but_not_standard_claims():
    result = ClaimCleaner().clean(
        {
            "id": 30,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "variable": "卖点1",
            "selling_point": "<b>游戏体验：</b>低延迟；体育赛事拖影少。",
        },
        source_context("selling_points_data", "30"),
    )

    assert result.claim is not None
    payload = result.claim
    assert payload["claim_seq"] == 1
    assert payload["clean_claim_text"] == "游戏体验: 低延迟;体育赛事拖影少。"
    assert payload["title_hint"] == "游戏体验"
    assert payload["structure_hints"]["has_colon_title"] is True
    assert payload["quality_status"] == "ok"
    assert [sentence["sentence_text"] for sentence in result.sentences] == ["游戏体验: 低延迟", "体育赛事拖影少"]
    assert all(sentence["clean_hash"].startswith(f"sha256:{CORE3_M01_CLEAN_HASH_VERSION}:") for sentence in result.sentences)
    assert_no_business_outputs(payload)
    assert "claim_code" not in payload


def test_claim_cleaner_does_not_create_fake_claim_for_empty_source_text():
    result = ClaimCleaner().clean(
        {
            "id": 31,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "variable": "核心定位",
            "selling_point": "",
        },
        source_context("selling_points_data", "31"),
    )

    assert result.claim is None
    assert result.sentences == []


def test_claim_cleaner_flags_unparseable_claim_seq_without_turning_title_into_claim_code():
    result = ClaimCleaner().clean(
        {
            "id": 32,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "variable": "核心定位",
            "selling_point": "高端家庭影院定位",
        },
        source_context("selling_points_data", "32"),
    )

    assert result.claim is not None
    assert result.claim["claim_seq"] is None
    assert result.claim["quality_flags"] == ["claim_seq_parse_failed"]
    assert "claim_code" not in result.claim


def test_comment_cleaner_preserves_comment_segment_and_raw_dimension_as_weak_label():
    result = CommentCleaner().clean(
        {
            "id": 40,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "platform": "京东",
            "comment_id": "c-40",
            "comment_time": "2026-06-12T10:00:00+08:00",
            "comment_content": "画质很好！游戏模式延迟低。",
            "comments_segments": "画质很好；游戏模式延迟低",
            "sentiment": "正面",
            "primary_dim": "产品体验",
            "secondary_dim": "画质",
            "third_dim": "清晰度",
        },
        source_context("comment_data", "40"),
    )

    payload = result.comment
    assert payload["comment_text_presence"] == "present"
    assert payload["sentiment_clean"] == "positive"
    assert payload["low_value_flag"] is False
    assert payload["dimension_available"] is True
    assert payload["comment_text_hash"].startswith(f"sha256:{CORE3_M01_CLEAN_HASH_VERSION}:")
    assert [sentence["sentence_source"] for sentence in result.sentences] == [
        "system_split",
        "system_split",
        "source_segment",
        "source_segment",
    ]
    assert result.dimension is not None
    assert result.dimension["dimension_path_raw"] == "产品体验/画质/清晰度"
    assert result.dimension["dimension_available"] is True
    assert_no_business_outputs(payload)
    assert_no_business_outputs(result.dimension)


def test_comment_cleaner_marks_default_comment_low_value_but_keeps_fact():
    result = CommentCleaner().clean(
        {
            "id": 41,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "comment_id": "c-41",
            "comment_content": "此用户没有填写评价",
            "comments_segments": "",
            "sentiment": "",
            "primary_dim": "",
            "secondary_dim": "",
            "third_dim": "",
        },
        source_context("comment_data", "41"),
    )

    payload = result.comment
    assert payload["clean_comment_text"] == "此用户没有填写评价"
    assert payload["sentiment_clean"] == "unknown"
    assert payload["low_value_flag"] is True
    assert payload["quality_status"] == "warning"
    assert "low_value_comment" in payload["quality_flags"]
    assert result.sentences == []
    assert result.dimension is not None
    assert result.dimension["dimension_available"] is False
    assert result.dimension["quality_flags"] == ["comment_dimension_missing"]
    assert "task_code" not in payload
    assert "target_group_code" not in payload
    assert "battlefield_code" not in payload


def test_comment_cleaner_blocks_service_fulfillment_comment_as_low_value():
    result = CommentCleaner().clean(
        {
            "id": 42,
            "model_code": "TV00029115",
            "brand": "海信",
            "model": "85E7Q",
            "comment_id": "c-42",
            "comment_content": "物流很快，客服回复也很及时",
            "comments_segments": "物流很快；客服回复及时",
            "sentiment": "正面",
            "primary_dim": "服务体验",
            "secondary_dim": "物流配送",
            "third_dim": "",
        },
        source_context("comment_data", "42"),
    )

    payload = result.comment
    assert payload["low_value_flag"] is True
    assert payload["low_value_reason"] == "服务履约评价"
    assert "low_value_comment" in payload["quality_flags"]
    assert payload["_service_candidate"] is True
    assert result.sentences == []
    assert result.dimension is not None
    assert result.dimension["dimension_path_raw"] == "服务体验/物流配送"


def test_common_context_versions_are_applied_to_all_domain_payloads():
    result = MarketCleaner().clean(
        {
            "model_code": "TV00029115",
            "date_value": "26W01",
            "sales_volume": "1",
            "sales_amount": "100",
            "avg_price": "100",
        },
        source_context("week_sales_data", "50"),
    )

    assert result.market["clean_version"] == CORE3_M01_CLEAN_VERSION
    assert result.market["hash_version"] == CORE3_M01_CLEAN_HASH_VERSION
    assert result.market["project_id"] == "core3_mvp"
    assert result.market["category_code"] == "TV"
