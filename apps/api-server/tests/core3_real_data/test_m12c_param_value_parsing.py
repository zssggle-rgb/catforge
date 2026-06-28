from decimal import Decimal

from app.services.core3_real_data import m12c_claim_value_quantification_service as m12c_service


def test_m12c_param_value_parsing_ignores_metadata_dicts() -> None:
    metadata = {
        "rule_version": "m03b_tv_param_profile_v0.1",
        "parser_version": "m03b_tv_parser_v0.1",
        "taxonomy_version": "tv_param_taxonomy_manual_v0.1",
    }

    assert m12c_service._decimal_param_value(metadata) is None
    assert m12c_service._truthy_param_value(metadata) is None
    assert m12c_service._param_value_type(metadata) == "text"


def test_m12c_support_param_codes_filters_internal_fields() -> None:
    claim = m12c_service.ClaimState(
        sku_code="sku-a",
        claim_code="tv_claim_hdr_high_brightness",
        claim_name="HDR/高亮画质",
        claim_dimension="画质",
        claim_subtype="高亮",
        claim_kind="fact",
        param_support_status="supported",
        supporting_param_codes=("_metadata", "declared_brightness_nit_or_band"),
        supporting_param_snapshot={},
        match_score=Decimal("0.9000"),
        confidence=Decimal("0.9000"),
        fact_claim_flag=True,
        service_separate_flag=False,
        evidence_ids=("e1",),
    )

    support_codes = m12c_service._claim_support_param_codes(claim, "tv_claim_hdr_high_brightness")

    assert "_metadata" not in support_codes
    assert support_codes[0] == "declared_brightness_nit_or_band"
