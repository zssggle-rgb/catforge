from decimal import Decimal

from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader
from app.services.core3_real_data.promo_claim_matcher import (
    ClaimEntityExtractor,
    PromoClaimMatcher,
)


PROJECT_ID = "core3_mvp"
BATCH_ID = "batch_m04a"


def test_m04a_entity_extractor_covers_core_promo_entity_types():
    entities = ClaimEntityExtractor().extract(
        "Mini LED 3500分区控光，144Hz 刷新率，HDMI2.1、VRR、ALLM，"
        "低蓝光无频闪护眼，Dolby Atmos 40W 2.1声道，AI语音，送装售后无忧。"
    )
    payload = entities.to_json()

    assert "Mini LED" in payload["technology_entities"]
    assert "分区" in payload["backlight_entities"]
    assert "HDMI2.1" in payload["gaming_entities"]
    assert "刷新率" in payload["motion_entities"]
    assert "低蓝光" in payload["eye_care_entities"]
    assert "Dolby" in payload["audio_entities"]
    assert "AI" in payload["smart_entities"]
    assert "送装" in payload["service_entities"]
    assert {"display_technology", "backlight_control", "gaming_connection", "eye_care", "audio", "smart", "service"}.issubset(
        entities.categories()
    )
    assert {"raw": "3500分区", "value": 3500, "unit": "zones", "entity_type": "dimming_zones", "unit_uncertain": False} in payload[
        "numeric_entities"
    ]
    assert {"raw": "144Hz", "value": 144, "unit": "Hz", "entity_type": "refresh_rate", "unit_uncertain": False} in payload[
        "numeric_entities"
    ]
    assert payload["entity_quality"]["abstract_promo_only"] is False


def test_m04a_promo_matcher_matches_alias_keyword_and_entities_to_claim_hits():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)

    hits = matcher.match(
        [
            _promo(
                "ev_promo_1",
                text="Mini LED 背光配合 3500分区控光，144Hz 高刷和 HDMI2.1 游戏接口，观影游戏都流畅。",
                claim_seq=1,
                sentence_seq=0,
                title_hint="功能价值",
            )
        ]
    )
    by_code = {hit.claim_code: hit for hit in hits}

    assert {"CLAIM_MINI_LED_BACKLIGHT", "CLAIM_FINE_LOCAL_DIMMING", "CLAIM_HIGH_REFRESH_RATE", "CLAIM_HDMI_2_1_GAMING"}.issubset(
        by_code
    )
    mini_led = by_code["CLAIM_MINI_LED_BACKLIGHT"]
    assert mini_led.hit_source_type == "promo_sentence"
    assert mini_led.claim_group == "picture"
    assert mini_led.match_method in {"exact_alias", "keyword"}
    assert "Mini LED" in mini_led.matched_keywords
    assert mini_led.promo_evidence_ids == ["ev_promo_1"]
    assert mini_led.param_evidence_ids == []
    assert mini_led.quality_evidence_ids == []
    assert mini_led.extracted_entity_json["numeric_entities"]
    assert mini_led.claim_seq == 1
    assert mini_led.sentence_seq == 0
    assert mini_led.hit_hash.startswith("sha256:m04a-claim-hit-v1:")
    assert mini_led.to_record_payload()["source_sentence_key"] == "ev_key_1_0"


def test_m04a_promo_matcher_marks_close_multi_claim_hits_for_review():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)

    hits = matcher.match(
        [
            _promo(
                "ev_promo_multi",
                text="OLED 自发光纯黑表现出色，HDR 高亮画面也很震撼。",
                claim_seq=2,
                sentence_seq=0,
            )
        ]
    )
    hit_codes = {hit.claim_code for hit in hits}

    assert {"CLAIM_OLED_SELF_LIT", "CLAIM_HIGH_BRIGHTNESS_HDR"}.issubset(hit_codes)
    review_hits = [hit for hit in hits if hit.review_required]
    assert any("multi_claim_close_match" in hit.quality_flags for hit in review_hits)
    assert all(hit.review_status == "review_required" for hit in review_hits)


def test_m04a_promo_matcher_uses_title_hint_only_as_weak_signal_not_standalone_match():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)

    no_hit = matcher.match([_promo("ev_title_only", text="核心定位", title_hint="核心定位")])
    hit = matcher.match([_promo("ev_title_keyword", text="智能语音操控简单", title_hint="便捷体验")])

    assert no_hit == []
    assert [item.claim_code for item in hit] == ["CLAIM_SMART_VOICE_EASE"]
    assert "title_hint_weak" in hit[0].quality_flags
    assert hit[0].match_confidence <= Decimal("0.8500")


def test_m04a_promo_matcher_downweights_abstract_promo_only_text():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)

    hits = matcher.match(
        [
            _promo(
                "ev_abstract",
                text="高刷旗舰体验行业领先，震撼升级。",
                title_hint="行业地位",
            )
        ]
    )

    assert hits
    assert {hit.claim_code for hit in hits} == {"CLAIM_HIGH_REFRESH_RATE", "CLAIM_SPORTS_MOTION_SMOOTH"}
    assert all(hit.match_confidence <= Decimal("0.4200") for hit in hits)
    assert all("abstract_promo_only" in hit.quality_flags for hit in hits)
    assert all(hit.review_required for hit in hits)


def test_m04a_promo_matcher_ignores_non_current_comment_and_market_evidence():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)

    hits = matcher.match(
        [
            _promo("ev_old", text="Mini LED", evidence_status="superseded"),
            {"evidence_id": "ev_comment", "evidence_type": "comment_sentence", "text_value": "游戏流畅", "is_current": True},
            {"evidence_id": "ev_market", "evidence_type": "market_fact", "text_value": "销量领先", "is_current": True},
        ]
    )

    assert hits == []


def test_m04a_promo_matcher_is_deterministic_for_same_sentence_and_seed():
    seed = StdClaimSeedLoader().load_seed()
    matcher = PromoClaimMatcher(project_id=PROJECT_ID, batch_id=BATCH_ID, seed=seed)
    evidence = [_promo("ev_repeat", text="杜比 Atmos 40W 音响带来沉浸音效", claim_seq=3, sentence_seq=1)]

    first = matcher.match(evidence)
    second = matcher.match(evidence)

    assert [hit.claim_code for hit in first] == [hit.claim_code for hit in second]
    assert [hit.claim_hit_id for hit in first] == [hit.claim_hit_id for hit in second]
    assert [hit.hit_hash for hit in first] == [hit.hit_hash for hit in second]
    assert {"CLAIM_IMMERSIVE_AUDIO", "CLAIM_DOLBY_CINEMA_AUDIO"}.issubset({hit.claim_code for hit in first})


def _promo(
    evidence_id: str,
    *,
    text: str,
    claim_seq: int = 1,
    sentence_seq: int = 0,
    evidence_status: str = "current",
    title_hint: str | None = None,
) -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"ev_key_{claim_seq}_{sentence_seq}",
        "evidence_type": "promo_sentence",
        "evidence_status": evidence_status,
        "is_current": evidence_status == "current",
        "sku_code": "TV00029115",
        "model_name": "85E7Q",
        "text_value": text,
        "base_confidence": Decimal("0.9000"),
        "confidence_level": "high",
        "quality_flags": [],
        "evidence_payload_json": {
            "claim_seq": claim_seq,
            "sentence_seq": sentence_seq,
            "sentence_text": text,
            "sentence_role_hint": title_hint,
            "title_hint": title_hint,
        },
    }
