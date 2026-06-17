from decimal import Decimal

from app.services.core3_real_data.cleaning_normalizers import (
    CleanHashService,
    MISSING_COLUMN,
    NumberParser,
    PeriodParser,
    SentenceSplitter,
    TextNormalizer,
    ValuePresenceClassifier,
    check_average_price,
    extract_claim_seq,
    extract_number_candidates,
    is_low_value_comment,
)
from app.services.core3_real_data.constants import Core3QualityIssueType, Core3ValuePresenceStatus


def test_text_normalizer_performs_minimal_normalization_without_business_mapping():
    raw = "\ufeff <b> 海信\u200b  ８５E７Q </b>\n 游戏  体育 "

    normalized = TextNormalizer.normalize(raw)

    assert normalized == "海信 85E7Q 游戏 体育"
    assert "游戏体育战场" not in normalized


def test_value_presence_classifier_keeps_missing_like_values_distinct():
    assert ValuePresenceClassifier.classify(MISSING_COLUMN) == Core3ValuePresenceStatus.MISSING_COLUMN
    assert ValuePresenceClassifier.classify(None) == Core3ValuePresenceStatus.NULL
    assert ValuePresenceClassifier.classify("   ") == Core3ValuePresenceStatus.EMPTY
    assert ValuePresenceClassifier.classify("-") == Core3ValuePresenceStatus.DASH
    assert ValuePresenceClassifier.classify("UNKNOWN") == Core3ValuePresenceStatus.UNKNOWN_LITERAL
    assert ValuePresenceClassifier.classify("暂无") == Core3ValuePresenceStatus.UNKNOWN_LITERAL
    assert ValuePresenceClassifier.classify("0") == Core3ValuePresenceStatus.PRESENT
    assert ValuePresenceClassifier.classify(False) == Core3ValuePresenceStatus.PRESENT


def test_number_parser_supports_decimal_strings_and_reports_quality_issue_type():
    parsed = NumberParser.parse("1,234.50")
    invalid = NumberParser.parse("8千元")
    negative = NumberParser.parse("-2")
    dash = NumberParser.parse("-")
    missing = NumberParser.parse(MISSING_COLUMN)

    assert parsed.value == Decimal("1234.50")
    assert parsed.issue_type is None
    assert invalid.value is None
    assert invalid.issue_type == Core3QualityIssueType.INVALID_NUMBER
    assert negative.value == Decimal("-2")
    assert negative.issue_type == Core3QualityIssueType.NEGATIVE_NUMBER
    assert dash.issue_type == Core3QualityIssueType.UNKNOWN_VALUE
    assert missing.issue_type is None


def test_price_check_flags_material_average_price_mismatch_only():
    ok = check_average_price(
        sales_amount=Decimal("96000"),
        sales_volume=Decimal("12"),
        avg_price=Decimal("8000.5"),
    )
    mismatch = check_average_price(
        sales_amount=Decimal("96000"),
        sales_volume=Decimal("12"),
        avg_price=Decimal("8200"),
    )
    uncheckable = check_average_price(sales_amount=Decimal("96000"), sales_volume=Decimal("0"), avg_price=Decimal("8000"))

    assert ok.status == "ok"
    assert ok.issue_type is None
    assert mismatch.status == "mismatch"
    assert mismatch.expected_price == Decimal("8000")
    assert mismatch.issue_type == Core3QualityIssueType.PRICE_CHECK_MISMATCH
    assert uncheckable.status == "uncheckable"


def test_period_parser_handles_week_code_without_inferring_calendar_date():
    parsed = PeriodParser.parse("26W01")
    parsed_with_full_year = PeriodParser.parse("2026-W9")
    failed = PeriodParser.parse("2026-01-01")

    assert parsed.period_type == "week"
    assert parsed.period_year_hint == 2026
    assert parsed.period_week_index == 1
    assert parsed.period_parse_status == "parsed"
    assert parsed_with_full_year.period_year_hint == 2026
    assert parsed_with_full_year.period_week_index == 9
    assert failed.period_type is None
    assert failed.period_parse_status == "failed"


def test_sentence_splitter_is_deterministic_and_does_not_infer_topics():
    sentences = SentenceSplitter.split("1、画质清晰；2、游戏延迟低。体育赛事拖影少！")

    assert sentences == ["画质清晰", "游戏延迟低", "体育赛事拖影少"]
    assert all("战场" not in sentence for sentence in sentences)


def test_claim_seq_and_attribute_number_candidates_are_raw_signal_helpers_only():
    assert extract_claim_seq("卖点13") == 13
    assert extract_claim_seq("核心定位") is None

    candidates = extract_number_candidates("刷新率 300HZ，峰值亮度 1600nits")

    assert candidates == [
        {"number": "300", "unit": "HZ"},
        {"number": "1600", "unit": "nits"},
    ]


def test_low_value_comment_marks_defaults_but_keeps_business_comments():
    assert is_low_value_comment("")
    assert is_low_value_comment("此用户没有填写评价")
    assert is_low_value_comment("默认好评")
    assert is_low_value_comment("好评")
    assert not is_low_value_comment("画质很好，游戏模式延迟低，值得好评")


def test_clean_hash_ignores_volatile_fields_but_keeps_quality_changes():
    payload_a = {
        "batch_id": "m00_1",
        "sku_code": "TV00029115",
        "clean_attr_name": "刷新率",
        "clean_attr_value": "300HZ",
        "quality_status": "ok",
        "created_at": "2026-06-12T00:00:00Z",
    }
    payload_b = {
        "created_at": "2026-06-13T00:00:00Z",
        "quality_status": "ok",
        "clean_attr_value": "300HZ",
        "clean_attr_name": "刷新率",
        "sku_code": "TV00029115",
        "batch_id": "m00_2",
    }
    payload_c = {**payload_a, "quality_status": "warning"}

    assert CleanHashService.clean_hash("attribute", payload_a) == CleanHashService.clean_hash("attribute", payload_b)
    assert CleanHashService.clean_hash("attribute", payload_a) != CleanHashService.clean_hash("attribute", payload_c)
    assert CleanHashService.clean_record_key("attribute", "attribute_data:2") == "attribute:attribute_data:2"


def test_clean_hash_preserves_null_empty_dash_and_unknown_as_distinct():
    values = [None, "", "-", "unknown"]
    hashes = {
        CleanHashService.clean_hash("attribute", {"clean_attr_value": value, "quality_status": "ok"})
        for value in values
    }

    assert len(hashes) == len(values)
