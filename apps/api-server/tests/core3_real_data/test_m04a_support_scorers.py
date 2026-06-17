from decimal import Decimal

from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader
from app.services.core3_real_data.claim_support_scorer import (
    ClaimSupportScorer,
    ParamSupportScorer,
    PromoSupportScorer,
)
from app.services.core3_real_data.param_conflicts import ParamConflictDetector
from app.services.core3_real_data.param_extraction_service import ParamValueExtractor
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_profile_builder import SkuParamProfileBuilder
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader
from app.services.core3_real_data.promo_claim_matcher import PromoClaimMatcher


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m04a"


def test_m04a_param_support_scores_mini_led_from_m03_profile():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    profile = _profile([_evidence("ev_miniled", field_name="Mini LED", value="支持")])

    support = ParamSupportScorer().score_claim(claim, profile)

    assert support.param_score >= Decimal("0.8500")
    assert support.matched_param_codes == ["mini_led_flag"]
    assert support.param_evidence_ids == ["ev_miniled"]
    assert support.param_support_json["param_only_allowed"] is True
    assert support.param_support_json["param_only_level_cap"] == "medium"
    assert set(support.param_support_json["seed_weight_snapshot"]["normalized_m04a_weights"]) == {"param", "promo"}


def test_m04a_param_support_downweights_uncertain_brightness_and_system_refresh_scope():
    claim_seed = StdClaimSeedLoader().load_seed()
    profile = _profile(
        [
            _evidence("ev_brightness", field_name="峰值亮度", value="5200"),
            _evidence("ev_system_refresh", field_name="系统刷新率", value="300Hz"),
        ]
    )

    hdr_support = ParamSupportScorer().score_claim(_claim(claim_seed, "CLAIM_HIGH_BRIGHTNESS_HDR"), profile)
    refresh_support = ParamSupportScorer().score_claim(_claim(claim_seed, "CLAIM_HIGH_REFRESH_RATE"), profile)

    assert Decimal("0.5000") <= hdr_support.param_score <= Decimal("0.7200")
    assert "unit_uncertain" in hdr_support.quality_flags
    assert hdr_support.review_required is True
    assert Decimal("0.5000") <= refresh_support.param_score <= Decimal("0.7200")
    assert "refresh_scope_uncertain" in refresh_support.quality_flags
    assert refresh_support.review_required is True


def test_m04a_param_support_does_not_fabricate_hdmi_2_1_port_count_from_version_only():
    claim_seed = StdClaimSeedLoader().load_seed()
    profile = _profile([_evidence("ev_hdmi", field_name="HDMI2.1", value="HDMI2.1")])

    support = ParamSupportScorer().score_claim(_claim(claim_seed, "CLAIM_HDMI_2_1_GAMING"), profile)

    assert Decimal("0.3000") <= support.param_score < Decimal("0.5500")
    assert support.matched_param_codes == ["hdmi_2_1_ports"]
    assert "hdmi_version_without_count" in support.quality_flags
    assert support.param_support_json["matched_details"][0]["actual_value"] is None


def test_m04a_param_support_caps_non_param_only_value_claims():
    claim_seed = StdClaimSeedLoader().load_seed()
    profile = _profile([_evidence("ev_size", field_name="尺寸", value="85英寸")])

    support = ParamSupportScorer().score_claim(_claim(claim_seed, "CLAIM_VALUE_FOR_MONEY"), profile)

    assert support.param_score == Decimal("0.5000")
    assert support.param_support_json["param_only_allowed"] is False
    assert support.param_support_json["param_only_level_cap"] == "low"
    assert "param_only_not_strong_activation" in support.quality_flags
    assert support.review_required is True


def test_m04a_promo_support_scores_hits_and_keeps_missing_promo_at_zero():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    hits = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=claim_seed).match(
        [_promo("ev_promo", text="Mini LED 背光技术带来清晰画质。")]
    )

    support = PromoSupportScorer().score_claim(claim, hits)
    missing_support = PromoSupportScorer().score_claim(_claim(claim_seed, "CLAIM_EYE_CARE_COMFORT"), [])

    assert support.promo_score >= Decimal("0.8500")
    assert support.claim_hit_ids
    assert support.promo_evidence_ids == ["ev_promo"]
    assert support.promo_support_json["matched_hit_count"] >= 1
    assert missing_support.promo_score == Decimal("0.0000")
    assert missing_support.missing_signals == ["missing_promo_evidence"]


def test_m04a_promo_support_keeps_abstract_promo_low_and_review_required():
    claim_seed = StdClaimSeedLoader().load_seed()
    hits = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=claim_seed).match(
        [_promo("ev_abstract", text="高刷旗舰体验行业领先，震撼升级。", title_hint="行业地位")]
    )

    support = PromoSupportScorer().score_claim(_claim(claim_seed, "CLAIM_HIGH_REFRESH_RATE"), hits)

    assert support.promo_score <= Decimal("0.4200")
    assert "abstract_promo_only" in support.quality_flags
    assert support.review_required is True


def test_m04a_claim_support_combines_param_and_promo_payloads_without_final_activation():
    claim_seed = StdClaimSeedLoader().load_seed()
    profile = _profile([_evidence("ev_miniled", field_name="Mini LED", value="支持")])
    hits = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=claim_seed).match(
        [_promo("ev_promo", text="Mini LED 背光和分区控光带来高端画质。")]
    )

    support = ClaimSupportScorer().score_claim(
        _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT"),
        sku_param_profile=profile,
        claim_hits=hits,
    )

    assert support.param_score > Decimal("0.8000")
    assert support.promo_score > Decimal("0.8000")
    assert support.param_evidence_ids == ["ev_miniled"]
    assert support.promo_evidence_ids == ["ev_promo"]
    assert support.evidence_ids == ["ev_miniled", "ev_promo"]
    assert "base_activation_score" not in support.param_support_json
    assert "activation_level" not in support.promo_support_json


def _claim(seed, claim_code):
    return next(claim for claim in seed.standard_claims if claim.claim_code == claim_code)


def _profile(records):
    param_seed = StdParamSeedLoader().load_seed()
    profiles = ParamFieldProfiler(project_id=PROJECT_ID, batch_id=BATCH_ID).build_profiles(records)
    matched_profiles = ParamAliasMatcher(param_seed).apply_matches(profiles)
    values = ParamValueExtractor(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=param_seed).extract_values(
        records,
        matched_profiles,
    )
    values, conflicts = ParamConflictDetector(project_id=PROJECT_ID, batch_id=BATCH_ID).apply_conflicts(values)
    [profile] = SkuParamProfileBuilder(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=param_seed).build_profiles(
        values,
        conflicts,
    )
    return profile


def _evidence(evidence_id: str, *, field_name: str, value: object) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "evidence_type": "param_raw",
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "raw_value": value,
        "value_presence": "present",
        "base_confidence": Decimal("1.0000"),
    }


def _promo(
    evidence_id: str,
    *,
    text: str,
    title_hint: str | None = None,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_key": evidence_id,
        "evidence_type": "promo_sentence",
        "evidence_status": "current",
        "is_current": True,
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "text_value": text,
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "quality_flags": [],
        "evidence_payload_json": {
            "claim_seq": 1,
            "sentence_seq": 0,
            "sentence_text": text,
            "sentence_role_hint": title_hint,
            "title_hint": title_hint,
        },
    }
