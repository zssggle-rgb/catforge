from dataclasses import replace
from decimal import Decimal

from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader
from app.services.core3_real_data.claim_activation_scorer import ClaimActivationBaseScorer
from app.services.core3_real_data.claim_support_scorer import ClaimSupportScorer
from app.services.core3_real_data.param_conflicts import ParamConflictDetector
from app.services.core3_real_data.param_extraction_service import ParamValueExtractor
from app.services.core3_real_data.param_field_matcher import ParamAliasMatcher
from app.services.core3_real_data.param_field_profiler import ParamFieldProfiler
from app.services.core3_real_data.param_profile_builder import SkuParamProfileBuilder
from app.services.core3_real_data.param_seed_loader import StdParamSeedLoader
from app.services.core3_real_data.promo_claim_matcher import PromoClaimMatcher


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m04a"
SKU_CODE = "TV00029115"
MODEL_NAME = "85E7Q"


def test_m04a_activation_scorer_builds_high_param_and_promo_technical_claim():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    support = _support(
        claim_seed,
        claim,
        profile_records=[_evidence("ev_miniled", field_name="Mini LED", value="支持")],
        promo_records=[_promo("ev_promo", text="Mini LED 背光技术带来清晰画质。")],
    )

    activation = _scorer().score_claim(claim, support, sku_code=SKU_CODE, model_name=MODEL_NAME)

    assert activation.claim_activation_base_id.startswith("m04abase_")
    assert activation.activation_hash.startswith("sha256:m04a-claim-activation-v1:")
    assert activation.activation_basis == "param_and_promo"
    assert activation.activation_level == "high"
    assert activation.confidence_level == "high"
    assert activation.base_activation_score >= Decimal("0.7500")
    assert activation.review_required is False
    assert activation.review_status == "auto_pass"
    assert activation.evidence_ids == ["ev_miniled", "ev_promo"]
    assert activation.param_support_json["activation_weight"] == "0.6500"
    assert activation.promo_support_json["activation_weight"] == "0.3500"


def test_m04a_activation_scorer_caps_param_only_technical_claim_and_marks_source_missing():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    support = _support(
        claim_seed,
        claim,
        profile_records=[_evidence("ev_miniled", field_name="Mini LED", value="支持")],
        promo_records=[],
    )

    activation = _scorer().score_claim(
        claim,
        support,
        sku_code=SKU_CODE,
        model_name=MODEL_NAME,
        source_status=_source_status(["structured_claim_missing"], review_required=True),
    )

    assert activation.activation_basis == "param_only"
    assert activation.activation_level == "medium"
    assert "missing_structured_claim" in activation.missing_signals
    assert "missing_promo_evidence" not in activation.missing_signals
    assert activation.review_required is True
    assert "param-only" in activation.review_reason


def test_m04a_activation_scorer_requires_review_for_technical_promo_only_claim():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    support = _support(
        claim_seed,
        claim,
        profile_records=[],
        promo_records=[_promo("ev_promo", text="Mini LED 背光技术带来清晰画质。")],
    )

    activation = _scorer().score_claim(claim, support, sku_code=SKU_CODE, model_name=MODEL_NAME)

    assert activation.activation_basis == "promo_only"
    assert activation.activation_level in {"unknown", "low", "medium"}
    assert activation.activation_level != "high"
    assert "missing_required_param" in activation.missing_signals
    assert activation.review_required is True
    assert "技术型卖点只有宣传没有参数支撑" in activation.review_reason


def test_m04a_activation_scorer_keeps_value_param_only_unknown_and_market_pending():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_VALUE_FOR_MONEY")
    support = _support(
        claim_seed,
        claim,
        profile_records=[_evidence("ev_size", field_name="尺寸", value="85英寸")],
        promo_records=[],
    )

    activation = _scorer().score_claim(claim, support, sku_code=SKU_CODE, model_name=MODEL_NAME)

    assert activation.activation_basis == "param_only"
    assert activation.activation_level in {"unknown", "low"}
    assert activation.base_activation_score < Decimal("0.3500")
    assert "comment_validation_pending" in activation.missing_signals
    assert "market_value_pending" in activation.missing_signals
    assert activation.review_required is True
    assert "价值判断仍待市场验证" in activation.review_reason


def test_m04a_activation_scorer_applies_conflict_penalty_and_keeps_hash_deterministic():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_MINI_LED_BACKLIGHT")
    support = _support(
        claim_seed,
        claim,
        profile_records=[_evidence("ev_miniled", field_name="Mini LED", value="支持")],
        promo_records=[_promo("ev_promo", text="Mini LED 背光技术带来清晰画质。")],
    )
    conflict_support = replace(
        support,
        conflict_flags=["param_promo_conflict"],
        quality_evidence_ids=["ev_quality_conflict"],
        evidence_ids=[*support.evidence_ids, "ev_quality_conflict"],
    )

    clean_activation = _scorer().score_claim(claim, support, sku_code=SKU_CODE, model_name=MODEL_NAME)
    conflict_activation = _scorer().score_claim(claim, conflict_support, sku_code=SKU_CODE, model_name=MODEL_NAME)
    repeated_conflict_activation = _scorer().score_claim(
        claim,
        conflict_support,
        sku_code=SKU_CODE,
        model_name=MODEL_NAME,
    )

    assert conflict_activation.base_activation_score == clean_activation.base_activation_score - Decimal("0.1500")
    assert conflict_activation.review_required is True
    assert "参数、宣传或质量证据存在冲突" in conflict_activation.review_reason
    assert conflict_activation.quality_evidence_ids == ["ev_quality_conflict"]
    assert conflict_activation.activation_hash == repeated_conflict_activation.activation_hash


def test_m04a_activation_scorer_record_payload_is_ready_for_activation_base_table():
    claim_seed = StdClaimSeedLoader().load_seed()
    claim = _claim(claim_seed, "CLAIM_HIGH_REFRESH_RATE")
    support = _support(
        claim_seed,
        claim,
        profile_records=[_evidence("ev_refresh", field_name="系统刷新率", value="300Hz")],
        promo_records=[_promo("ev_promo", text="144Hz 高刷带来游戏流畅体验。")],
    )

    payload = _scorer().score_claim(claim, support, sku_code=SKU_CODE, model_name=MODEL_NAME).to_record_payload()

    assert payload["sku_code"] == SKU_CODE
    assert payload["claim_code"] == "CLAIM_HIGH_REFRESH_RATE"
    assert payload["activation_basis"] == "param_and_promo"
    assert payload["param_score"] <= Decimal("0.7200")
    assert "scope_uncertain" in payload["missing_signals"]
    assert payload["review_status"] == "review_required"
    assert payload["param_support_json"]["activation_weight"] == "0.6500"
    assert payload["promo_support_json"]["activation_weight"] == "0.3500"


def _scorer():
    return ClaimActivationBaseScorer(project_id=PROJECT_ID, batch_id=BATCH_ID)


def _claim(seed, claim_code):
    return next(claim for claim in seed.standard_claims if claim.claim_code == claim_code)


def _support(claim_seed, claim, *, profile_records, promo_records):
    profile = _profile(profile_records) if profile_records else None
    hits = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=claim_seed).match(promo_records)
    return ClaimSupportScorer().score_claim(claim, sku_param_profile=profile, claim_hits=hits)


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


def _source_status(missing_signals, *, review_required=False):
    return {
        "sku_code": SKU_CODE,
        "model_name": MODEL_NAME,
        "missing_signals": missing_signals,
        "quality_evidence_ids": [],
        "review_required": review_required,
    }


def _evidence(evidence_id: str, *, field_name: str, value: object) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "sku_code": SKU_CODE,
        "model_name": MODEL_NAME,
        "evidence_type": "param_raw",
        "evidence_status": "current",
        "is_current": True,
        "evidence_field": field_name,
        "clean_value": value,
        "raw_value": value,
        "value_presence": "present",
        "base_confidence": Decimal("1.0000"),
    }


def _promo(evidence_id: str, *, text: str) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_key": evidence_id,
        "evidence_type": "promo_sentence",
        "evidence_status": "current",
        "is_current": True,
        "sku_code": SKU_CODE,
        "model_name": MODEL_NAME,
        "text_value": text,
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "quality_flags": [],
        "evidence_payload_json": {
            "claim_seq": 1,
            "sentence_seq": 0,
            "sentence_text": text,
        },
    }
