from datetime import datetime
from decimal import Decimal

from app.services.core3_real_data.constants import Core3ConfidenceLevel, Core3EvidenceType
from app.services.core3_real_data.evidence_confidence import EvidenceConfidenceService
from app.services.core3_real_data.evidence_mappers import EvidenceMapper
from app.services.core3_real_data.evidence_payloads import EvidencePayloadBuilder
from app.services.core3_real_data.hash_utils import canonicalize_json


BASE_RECORD = {
    "project_id": "core3_mvp",
    "category_code": "TV",
    "batch_id": "m00_202606130001",
    "run_id": "run_001",
    "module_run_id": "module_run_m01",
    "sku_code": "TV00029115",
    "model_name": "85E7Q",
    "brand_name": "海信",
    "source_table": "attribute_data",
    "source_pk": "123",
    "source_row_id": "attribute_data:123",
    "source_row_hash": "sha256:m00_row_hash_v1:source",
    "clean_record_key": "attribute:attribute_data:123",
    "clean_hash": "sha256:m01_clean_hash_v1:attr",
    "clean_version": "m01_clean_v1",
    "quality_status": "ok",
    "quality_flags": [],
}


def _draft(clean_table: str, **overrides):
    return EvidenceMapper().map_clean_record({**BASE_RECORD, **overrides}, clean_table=clean_table)


def test_payload_builder_generates_required_payload_for_each_evidence_type():
    builder = EvidencePayloadBuilder()
    drafts = [
        _draft(
            "core3_clean_sku",
            clean_record_key="sku:TV00029115",
            clean_hash="sha256:m01_clean_hash_v1:sku",
            source_table=None,
            coverage_json={"market": {"covered": True}},
            field_conflicts_json={"brand": []},
            missing_signals_json={"claim": True},
        ),
        _draft(
            "core3_clean_market_weekly",
            source_table="week_sales_data",
            clean_record_key="market:week_sales_data:1",
            clean_hash="sha256:m01_clean_hash_v1:market",
            period_raw="2026W01",
            channel_type="线上",
            platform_type="京东",
            sales_volume=Decimal("12.0000"),
            sales_amount=Decimal("95988.0000"),
            avg_price=Decimal("7999.0000"),
            price_check_status="ok",
        ),
        _draft(
            "core3_clean_attribute",
            raw_attr_name="刷新率",
            clean_attr_name="刷新率",
            raw_attr_value="144Hz",
            clean_attr_value="144Hz",
            value_presence="present",
            value_number_candidates=[{"value": Decimal("144.0000"), "unit": "Hz"}],
            value_unit_candidates=["Hz"],
        ),
        _draft(
            "core3_clean_claim",
            source_table="selling_points_data",
            clean_record_key="claim:selling_points_data:3",
            clean_hash="sha256:m01_clean_hash_v1:claim",
            claim_seq=1,
            raw_claim_text="游戏更流畅",
            clean_claim_text="游戏更流畅",
            title_hint="游戏",
        ),
        _draft(
            "core3_clean_claim_sentence",
            source_table="selling_points_data",
            clean_record_key="claim_sentence:selling_points_data:3:1",
            clean_hash="sha256:m01_clean_hash_v1:claim_sentence",
            claim_seq=1,
            sentence_seq=1,
            sentence_text="游戏更流畅",
            sentence_role_hint="benefit",
        ),
        _draft(
            "core3_clean_comment",
            source_table="comment_data",
            clean_record_key="comment:comment_data:4",
            clean_hash="sha256:m01_clean_hash_v1:comment",
            comment_id="cmt-001",
            clean_comment_text="打游戏很流畅",
            comment_text_hash="sha256:text:comment",
            segment_text_hash="sha256:text:segment",
            sentiment_clean="positive",
            low_value_flag=False,
            duplicate_group_key="dup-001",
            comment_time=datetime(2026, 6, 13, 8, 0, 0),
        ),
        _draft(
            "core3_clean_comment_sentence",
            source_table="comment_data",
            clean_record_key="comment_sentence:comment_data:4:1",
            clean_hash="sha256:m01_clean_hash_v1:comment_sentence",
            comment_id="cmt-001",
            sentence_source="segment",
            sentence_seq=1,
            sentence_text="打游戏很流畅",
            sentiment_clean="positive",
            low_value_flag=False,
        ),
        _draft(
            "core3_clean_comment_dimension",
            source_table="comment_data",
            clean_record_key="comment_dimension:comment_data:4",
            clean_hash="sha256:m01_clean_hash_v1:dimension",
            primary_dim_raw="产品体验",
            secondary_dim_raw="画质",
            third_dim_raw="流畅度",
            dimension_path_raw="产品体验/画质/流畅度",
            dimension_quality_flag="ok",
        ),
        EvidenceMapper().map_clean_record(
            {
                **BASE_RECORD,
                "source_clean_table": "core3_data_quality_issue",
                "source_table": "selling_points_data",
                "clean_record_key": "quality:claim_coverage_missing:TV00029115",
                "clean_hash": "sha256:m01_clean_hash_v1:issue",
                "domain": "claim",
                "issue_type": "claim_coverage_missing",
                "severity": "warning",
                "issue_detail": "缺少结构化卖点来源",
                "suggested_downstream_action": "M04a 不得伪造卖点事实",
            }
        ),
    ]

    required_keys = {
        Core3EvidenceType.SKU_FACT: {"coverage_json", "field_conflicts_json", "missing_signals_json"},
        Core3EvidenceType.MARKET_FACT: {
            "period_raw",
            "channel_type",
            "platform_type",
            "sales_volume",
            "sales_amount",
            "avg_price",
            "price_check_status",
        },
        Core3EvidenceType.PARAM_RAW: {
            "raw_attr_name",
            "clean_attr_name",
            "raw_attr_value",
            "clean_attr_value",
            "value_presence",
            "number_candidates",
            "unit_candidates",
        },
        Core3EvidenceType.PROMO_RAW: {"claim_seq", "raw_claim_text", "clean_claim_text", "title_hint"},
        Core3EvidenceType.PROMO_SENTENCE: {"claim_seq", "sentence_seq", "sentence_text", "sentence_role_hint"},
        Core3EvidenceType.COMMENT_RAW: {
            "comment_id",
            "clean_comment_text",
            "comment_text_hash",
            "segment_text_hash",
            "sentiment_clean",
            "low_value_flag",
            "duplicate_group_key",
        },
        Core3EvidenceType.COMMENT_SENTENCE: {
            "comment_id",
            "sentence_source",
            "sentence_seq",
            "sentence_text",
            "sentiment_clean",
            "low_value_flag",
        },
        Core3EvidenceType.COMMENT_DIMENSION: {
            "primary_dim_raw",
            "secondary_dim_raw",
            "third_dim_raw",
            "dimension_path_raw",
            "dimension_quality_flag",
        },
        Core3EvidenceType.QUALITY_ISSUE: {
            "domain",
            "issue_type",
            "severity",
            "issue_detail",
            "suggested_downstream_action",
        },
    }
    forbidden_keys = {"task_code", "target_group_code", "battlefield_code", "competitor_sku_code", "score", "report"}

    for draft in drafts:
        payload = builder.build_payload(draft)
        assert required_keys[draft.evidence_type].issubset(payload)
        assert not forbidden_keys.intersection(payload)
        canonicalize_json(payload)


def test_payload_builder_returns_json_safe_atom_values():
    draft = _draft(
        "core3_clean_market_weekly",
        source_table="week_sales_data",
        clean_record_key="market:week_sales_data:1",
        clean_hash="sha256:m01_clean_hash_v1:market",
        period_raw="2026W01",
        sales_volume=Decimal("12.0000"),
        sales_amount=Decimal("95988.0000"),
        avg_price=Decimal("7999.0000"),
        price_check_status="ok",
    )

    atom_values = EvidencePayloadBuilder().build_atom_values(draft)

    assert atom_values["numeric_value"] == "7999.0000"
    assert atom_values["numeric_values_json"][0]["value"] == "12.0000"
    assert atom_values["evidence_payload_json"]["avg_price"] == "7999.0000"
    assert atom_values["evidence_payload_json"]["sales_amount"] == "95988.0000"


def test_confidence_service_applies_base_scores_and_levels():
    service = EvidenceConfidenceService()
    builder = EvidencePayloadBuilder()
    market = _draft(
        "core3_clean_market_weekly",
        source_table="week_sales_data",
        clean_record_key="market:week_sales_data:1",
        clean_hash="sha256:m01_clean_hash_v1:market",
        sales_volume=Decimal("12.0000"),
        sales_amount=Decimal("95988.0000"),
        avg_price=Decimal("7999.0000"),
        price_check_status="ok",
    )
    param = _draft(
        "core3_clean_attribute",
        raw_attr_name="刷新率",
        clean_attr_name="刷新率",
        raw_attr_value="144Hz",
        clean_attr_value="144Hz",
        value_presence="present",
    )
    promo_sentence = _draft(
        "core3_clean_claim_sentence",
        source_table="selling_points_data",
        clean_record_key="claim_sentence:selling_points_data:3:1",
        clean_hash="sha256:m01_clean_hash_v1:claim_sentence",
        sentence_text="游戏更流畅",
    )
    comment_dimension = _draft(
        "core3_clean_comment_dimension",
        source_table="comment_data",
        clean_record_key="comment_dimension:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:dimension",
        dimension_quality_flag="ok",
    )

    market_confidence = service.calculate(market, evidence_payload=builder.build_payload(market))
    param_confidence = service.calculate(param, evidence_payload=builder.build_payload(param))
    promo_sentence_confidence = service.calculate(promo_sentence, evidence_payload=builder.build_payload(promo_sentence))
    comment_dimension_confidence = service.calculate(
        comment_dimension,
        evidence_payload=builder.build_payload(comment_dimension),
    )

    assert market_confidence.base_confidence == Decimal("0.9500")
    assert market_confidence.confidence_level == Core3ConfidenceLevel.HIGH
    assert param_confidence.base_confidence == Decimal("0.9000")
    assert param_confidence.confidence_level == Core3ConfidenceLevel.HIGH
    assert promo_sentence_confidence.base_confidence == Decimal("0.8000")
    assert promo_sentence_confidence.confidence_level == Core3ConfidenceLevel.HIGH
    assert comment_dimension_confidence.base_confidence == Decimal("0.5500")
    assert comment_dimension_confidence.confidence_level == Core3ConfidenceLevel.MEDIUM


def test_confidence_service_applies_quality_and_presence_caps():
    service = EvidenceConfidenceService()
    warning_param = _draft(
        "core3_clean_attribute",
        raw_attr_name="刷新率",
        clean_attr_name="刷新率",
        raw_attr_value="144Hz",
        clean_attr_value="144Hz",
        value_presence="present",
        quality_status="warning",
    )
    missing_param = _draft(
        "core3_clean_attribute",
        raw_attr_name="刷新率",
        clean_attr_name="刷新率",
        raw_attr_value="-",
        clean_attr_value=None,
        value_presence="dash",
    )
    mismatch_market = _draft(
        "core3_clean_market_weekly",
        source_table="week_sales_data",
        clean_record_key="market:week_sales_data:1",
        clean_hash="sha256:m01_clean_hash_v1:market",
        sales_volume=Decimal("12.0000"),
        sales_amount=Decimal("1000.0000"),
        avg_price=Decimal("7999.0000"),
        price_check_status="mismatch",
    )
    low_value_comment = _draft(
        "core3_clean_comment",
        source_table="comment_data",
        clean_record_key="comment:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:comment",
        clean_comment_text="默认好评",
        low_value_flag=True,
    )
    missing_dimension = _draft(
        "core3_clean_comment_dimension",
        source_table="comment_data",
        clean_record_key="comment_dimension:comment_data:4",
        clean_hash="sha256:m01_clean_hash_v1:dimension",
        dimension_quality_flag="missing",
    )

    warning_confidence = service.calculate(warning_param)
    missing_param_confidence = service.calculate(missing_param)
    mismatch_market_confidence = service.calculate(mismatch_market)
    low_value_comment_confidence = service.calculate(low_value_comment)
    missing_dimension_confidence = service.calculate(missing_dimension)

    assert warning_confidence.base_confidence == Decimal("0.7000")
    assert "quality_warning_cap" in warning_confidence.reasons
    assert missing_param_confidence.base_confidence == Decimal("0.3500")
    assert "value_not_present_cap" not in missing_param_confidence.reasons
    assert mismatch_market_confidence.base_confidence == Decimal("0.7000")
    assert "price_check_mismatch_cap" in mismatch_market_confidence.reasons
    assert low_value_comment_confidence.base_confidence == Decimal("0.2500")
    assert "low_value_comment" in low_value_comment_confidence.reasons
    assert missing_dimension_confidence.base_confidence == Decimal("0.2500")
    assert "dimension_missing_cap" in missing_dimension_confidence.reasons


def test_confidence_service_scores_quality_issue_by_severity():
    service = EvidenceConfidenceService()
    mapper = EvidenceMapper()
    warning_issue = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "source_clean_table": "core3_data_quality_issue",
            "source_table": "selling_points_data",
            "clean_record_key": "quality:claim_coverage_missing:TV00029115",
            "clean_hash": "sha256:m01_clean_hash_v1:issue_warning",
            "domain": "claim",
            "issue_type": "claim_coverage_missing",
            "severity": "warning",
            "issue_detail": "缺少结构化卖点来源",
        }
    )
    error_issue = mapper.map_clean_record(
        {
            **BASE_RECORD,
            "source_clean_table": "core3_data_quality_issue",
            "source_table": "week_sales_data",
            "clean_record_key": "quality:invalid_number:TV00029115",
            "clean_hash": "sha256:m01_clean_hash_v1:issue_error",
            "domain": "market",
            "issue_type": "invalid_number",
            "severity": "error",
            "issue_detail": "销量字段无法解析",
        }
    )

    warning_confidence = service.calculate(warning_issue)
    error_confidence = service.calculate(error_issue)

    assert warning_confidence.base_confidence == Decimal("0.3500")
    assert warning_confidence.confidence_level == Core3ConfidenceLevel.LOW
    assert error_confidence.base_confidence == Decimal("0.2000")
    assert error_confidence.confidence_level == Core3ConfidenceLevel.LOW
