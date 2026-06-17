import json
from decimal import Decimal

import pytest
from app.services.core3_real_data.base_claim_seed_loader import (
    PARAM_ONLY_ALLOWED_CLAIM_CODES,
    REQUIRED_STANDARD_CLAIM_CODES,
    StdClaimSeedLoader,
    StdClaimSeedValidationError,
)
from app.services.core3_real_data.constants import CORE3_M04A_SEED_VERSION


def test_m04a_seed_loader_loads_real_seed_and_required_claims():
    result = StdClaimSeedLoader().load()
    seed = result.seed
    claim_codes = [item.claim_code for item in seed.standard_claims]

    assert seed.seed_version == CORE3_M04A_SEED_VERSION
    assert result.seed_version == CORE3_M04A_SEED_VERSION
    assert result.raw_version == "core3-mvp-0.2.0"
    assert result.asset_version == "core3-mvp-0.2.0"
    assert result.standard_claim_count == len(seed.standard_claims) == 20
    assert len(claim_codes) == len(set(claim_codes))
    assert set(claim_codes) == REQUIRED_STANDARD_CLAIM_CODES
    assert result.required_claim_codes == sorted(REQUIRED_STANDARD_CLAIM_CODES)
    assert seed.metadata_json["raw_standard_claim_count"] == 20
    assert seed.metadata_json["required_standard_claim_count"] == 20
    assert seed.metadata_json["extra_claim_codes"] == []


def test_m04a_seed_loader_normalizes_sources_and_defers_comment_market_sources():
    result = StdClaimSeedLoader().load()
    seed = result.seed
    source_values = {
        source_type
        for standard_claim in seed.standard_claims
        for source_type in standard_claim.model_dump()["source_types"]
    }

    assert source_values <= {"standard_param", "claim_text", "raw_param"}
    assert "comment_text" not in source_values
    assert "market_fact" not in source_values
    assert result.ignored_source_type_counts["comment_text"] == 16
    assert result.ignored_source_type_counts["market_fact"] == 1
    assert len(result.comment_deferred_claim_codes) == 16
    assert result.market_deferred_claim_codes == ["CLAIM_VALUE_FOR_MONEY"]
    assert seed.metadata_json["comment_deferred_to_m04b_claim_codes"] == result.comment_deferred_claim_codes

    value_claim = next(item for item in seed.standard_claims if item.claim_code == "CLAIM_VALUE_FOR_MONEY")
    assert value_claim.source_types == ["claim_text"]


def test_m04a_seed_loader_preserves_claim_metadata_without_crossing_module_boundary():
    seed = StdClaimSeedLoader().load_seed()
    refresh_rate = next(item for item in seed.standard_claims if item.claim_code == "CLAIM_HIGH_REFRESH_RATE")
    service = next(item for item in seed.standard_claims if item.claim_code == "CLAIM_INSTALLATION_SERVICE_ASSURANCE")

    assert refresh_rate.claim_type == "technical"
    assert refresh_rate.param_only_allowed is True
    assert {"native_refresh_rate_hz", "system_refresh_rate_hz"}.issubset(refresh_rate.supporting_param_codes)
    assert refresh_rate.mapped_task_codes
    assert refresh_rate.mapped_battlefield_codes
    assert set(refresh_rate.activation_weights) == {"param", "promo"}
    assert sum(refresh_rate.activation_weights.values(), Decimal("0")) == Decimal("1.000000")
    assert "comment" not in refresh_rate.activation_weights

    assert service.claim_type == "service"
    assert service.param_only_allowed is False
    assert service.activation_weights == {"promo": Decimal("1.000000")}
    assert service.comment_topic_codes

    model_fields = type(refresh_rate).model_fields
    assert set(model_fields) >= {
        "claim_code",
        "claim_name",
        "claim_group",
        "claim_type",
        "source_types",
        "evidence_requirement",
        "supporting_param_codes",
        "activation_rule",
        "activation_weights",
    }
    assert "comment_validation_score" not in model_fields
    assert "battlefield_code" not in model_fields
    assert "competitor_sku_code" not in model_fields


def test_m04a_seed_loader_param_only_policy_matches_design():
    seed = StdClaimSeedLoader().load_seed()
    allowed_from_seed = {item.claim_code for item in seed.standard_claims if item.param_only_allowed}

    assert allowed_from_seed == PARAM_ONLY_ALLOWED_CLAIM_CODES
    assert "CLAIM_GAMING_LOW_LATENCY" not in allowed_from_seed
    assert "CLAIM_VALUE_FOR_MONEY" not in allowed_from_seed


def test_m04a_seed_loader_validates_required_root_and_fields(tmp_path):
    missing_root_path = tmp_path / "missing_root.json"
    missing_root_path.write_text(json.dumps({"version": "test"}), encoding="utf-8")

    with pytest.raises(StdClaimSeedValidationError, match="standard_claims"):
        StdClaimSeedLoader(missing_root_path).load()

    missing_field_path = tmp_path / "missing_field.json"
    missing_field_path.write_text(
        json.dumps(
            {
                "version": "test",
                "standard_claims": [
                    {
                        "claim_code": "CLAIM_LARGE_SCREEN_IMMERSION",
                        "claim_name": "大屏沉浸观影",
                        "claim_group": "picture",
                        "source_types": ["standard_param"],
                        "supporting_param_codes": ["screen_size_inch"],
                        "mapped_param_codes": ["screen_size_inch"],
                        "mapped_task_codes": ["TASK_LIVING_ROOM_CINEMA"],
                        "mapped_battlefield_codes": ["BF_FAMILY_VIEWING_UPGRADE"],
                        "activation_rule": {"any": [{"param": "screen_size_inch", "gte": 75}]},
                        "activation_weights": {"param": 1.0},
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(StdClaimSeedValidationError) as exc_info:
        StdClaimSeedLoader(missing_field_path).load()

    message = str(exc_info.value)
    assert "definition is required" in message
    assert "aliases is required" in message
    assert "keywords is required" in message
    assert "promo_keywords is required" in message
    assert "evidence_requirement is required" in message
    assert "missing required claim codes" in message


def test_m04a_seed_loader_rejects_duplicate_codes_unknown_sources_and_bad_weights(tmp_path):
    bad_seed = {
        "version": "test",
        "standard_claims": [
            _claim("CLAIM_LARGE_SCREEN_IMMERSION", source_types=["claim_text"], activation_weights={"promo": 1}),
            _claim(
                "CLAIM_LARGE_SCREEN_IMMERSION",
                source_types=["comment_text", "review_note"],
                activation_weights={"comment": 1},
            ),
            _claim(
                "CLAIM_MINI_LED_BACKLIGHT",
                source_types=["claim_text"],
                activation_weights={"promo": -1},
            ),
            _claim(
                "CLAIM_OLED_SELF_LIT",
                source_types=["claim_text"],
                activation_weights={"comment": 1},
            ),
        ],
    }
    bad_seed_path = tmp_path / "bad_seed.json"
    bad_seed_path.write_text(json.dumps(bad_seed, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(StdClaimSeedValidationError) as exc_info:
        StdClaimSeedLoader(bad_seed_path).load()

    message = str(exc_info.value)
    assert "claim_code must be unique" in message
    assert "unsupported source type: review_note" in message
    assert "must contain positive param or promo weight" in message
    assert "must not be negative" in message


def _claim(
    claim_code: str,
    *,
    source_types: list[str],
    activation_weights: dict[str, float | int],
) -> dict[str, object]:
    return {
        "claim_code": claim_code,
        "claim_name": "测试卖点",
        "definition": "测试定义",
        "claim_group": "picture",
        "aliases": ["测试卖点"],
        "keywords": ["测试"],
        "promo_keywords": ["测试"],
        "source_types": source_types,
        "evidence_requirement": ["param_or_promo"],
        "supporting_param_codes": ["screen_size_inch"],
        "mapped_param_codes": ["screen_size_inch"],
        "mapped_task_codes": ["TASK_LIVING_ROOM_CINEMA"],
        "mapped_battlefield_codes": ["BF_FAMILY_VIEWING_UPGRADE"],
        "activation_rule": {"any": [{"keywords": ["测试"]}]},
        "activation_weights": activation_weights,
    }
