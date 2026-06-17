from decimal import Decimal

from app.services.core3_real_data.claim_source_status_builder import (
    ClaimSourceStatusBuilder,
    ClaimSourceStatusInput,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m04a"


def test_m04a_source_status_builder_outputs_has_structured_claim():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)

    draft = builder.build(
        ClaimSourceStatusInput(
            sku_code="SKU1",
            model_name="85E7Q",
            evidence_records=(
                _promo("ev_promo_raw", evidence_type="promo_raw", text="144Hz 高刷游戏电视"),
                _promo("ev_promo_sentence", evidence_type="promo_sentence", text="支持 HDMI2.1 和低延迟游戏"),
                _comment("ev_comment_ignored"),
            ),
            param_profile={"known_param_count": 8},
        )
    )

    assert draft.claim_source_status == "has_structured_claim"
    assert draft.structured_claim_count == 1
    assert draft.claim_sentence_count == 1
    assert draft.promo_evidence_count == 2
    assert draft.review_required is False
    assert draft.review_status == "auto_pass"
    assert draft.missing_signals == []
    assert draft.conflict_summary_json == {}
    assert draft.status_hash.startswith("sha256:m04a-claim-source-status-v1:")
    assert draft.to_record_payload()["sku_code"] == "SKU1"


def test_m04a_source_status_builder_outputs_missing_structured_claim_when_params_exist():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)

    draft = builder.build(
        ClaimSourceStatusInput(
            sku_code="TV00029115",
            model_name="85E7Q",
            evidence_records=(
                _quality_issue("ev_claim_missing", issue_type="claim_coverage_missing"),
                _comment("ev_comment_ignored"),
            ),
            param_profile={"param_values_json": {"native_refresh_rate_hz": {"value": 144}}},
        )
    )

    assert draft.claim_source_status == "missing_structured_claim"
    assert draft.structured_claim_count == 0
    assert draft.promo_evidence_count == 0
    assert draft.quality_evidence_ids == ["ev_claim_missing"]
    assert draft.missing_signals == ["structured_claim_missing", "claim_coverage_missing"]
    assert draft.review_required is True
    assert draft.review_status == "review_required"
    assert "不代表没有卖点" in draft.status_note


def test_m04a_source_status_builder_outputs_claim_data_insufficient_for_unusable_promos():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)

    draft = builder.build(
        ClaimSourceStatusInput(
            sku_code="SKU2",
            model_name="坏宣传样例",
            evidence_records=(
                _promo("ev_empty", evidence_type="promo_raw", text=""),
                _promo("ev_skipped", evidence_type="promo_sentence", text="高刷", evidence_status="skipped"),
                _promo(
                    "ev_low_quality",
                    evidence_type="promo_sentence",
                    text="旗舰升级",
                    quality_flags=["low_value_claim"],
                ),
            ),
            param_profile={"known_param_count": 3},
        )
    )

    assert draft.claim_source_status == "claim_data_insufficient"
    assert draft.structured_claim_count == 0
    assert draft.claim_sentence_count == 0
    assert draft.promo_evidence_count == 0
    assert draft.missing_signals == [
        "promo_evidence_not_current",
        "promo_text_empty",
        "promo_evidence_low_quality",
    ]
    assert draft.review_required is True
    assert "低质量" in draft.status_note


def test_m04a_source_status_builder_outputs_claim_conflict_with_quality_issue_priority():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)

    draft = builder.build(
        ClaimSourceStatusInput(
            sku_code="SKU3",
            model_name="冲突样例",
            evidence_records=(
                _promo("ev_promo", evidence_type="promo_sentence", text="宣传为 300Hz 高刷"),
                _quality_issue("ev_conflict", issue_type="cross_table_conflict"),
            ),
            param_profile={"known_param_count": 6},
        )
    )

    assert draft.claim_source_status == "claim_conflict"
    assert draft.structured_claim_count == 0
    assert draft.claim_sentence_count == 1
    assert draft.promo_evidence_count == 1
    assert draft.quality_evidence_ids == ["ev_conflict"]
    assert draft.conflict_summary_json == {
        "issue_type_counts": {"cross_table_conflict": 1},
        "quality_evidence_ids": ["ev_conflict"],
        "conflict_level": "review_required",
    }
    assert draft.review_required is True
    assert "冲突" in draft.status_note


def test_m04a_source_status_builder_ignores_comment_and_market_evidence_for_boundary():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)

    draft = builder.build(
        ClaimSourceStatusInput(
            sku_code="SKU4",
            model_name="越界样例",
            evidence_records=(
                _comment("ev_comment_positive"),
                _market("ev_market_sales"),
            ),
            param_profile={"known_param_count": 1},
        )
    )

    assert draft.claim_source_status == "missing_structured_claim"
    assert draft.structured_claim_count == 0
    assert draft.quality_evidence_ids == []
    assert draft.missing_signals == ["structured_claim_missing"]
    payload = draft.to_record_payload()
    assert "comment_signal" not in payload
    assert "market_signal" not in payload
    assert "battlefield_code" not in payload
    assert "competitor_sku_code" not in payload


def test_m04a_source_status_builder_is_deterministic_and_sorts_many_by_sku():
    builder = ClaimSourceStatusBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID)
    inputs = [
        ClaimSourceStatusInput(sku_code="SKU2", evidence_records=(), param_profile={"known_param_count": 1}),
        ClaimSourceStatusInput(
            sku_code="SKU1",
            evidence_records=(_promo("ev_promo", evidence_type="promo_raw", text="Mini LED"),),
            param_profile=None,
        ),
    ]

    first = builder.build_many(inputs)
    second = builder.build_many(inputs)

    assert [item.sku_code for item in first] == ["SKU1", "SKU2"]
    assert [item.status_hash for item in first] == [item.status_hash for item in second]
    assert first[0].claim_source_status_id == second[0].claim_source_status_id


def _promo(
    evidence_id: str,
    *,
    evidence_type: str,
    text: str,
    evidence_status: str = "current",
    quality_flags: list[str] | None = None,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": evidence_type,
        "evidence_status": evidence_status,
        "is_current": evidence_status == "current",
        "text_value": text,
        "clean_value": text,
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "quality_flags": quality_flags or [],
        "evidence_payload_json": {
            "clean_claim_text": text if evidence_type == "promo_raw" else None,
            "sentence_text": text if evidence_type == "promo_sentence" else None,
        },
    }


def _quality_issue(evidence_id: str, *, issue_type: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": "quality_issue",
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": f"quality_issue:claim:{issue_type}",
        "quality_flags": [issue_type],
        "evidence_payload_json": {
            "domain": "claim",
            "issue_type": issue_type,
            "severity": "warning",
        },
    }


def _comment(evidence_id: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": "comment_sentence",
        "evidence_status": "current",
        "is_current": True,
        "text_value": "游戏很流畅",
    }


def _market(evidence_id: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_type": "market_fact",
        "evidence_status": "current",
        "is_current": True,
        "sales_volume": 100,
    }
