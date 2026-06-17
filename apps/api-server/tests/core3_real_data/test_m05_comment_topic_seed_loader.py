import json

import pytest

from app.services.core3_real_data.comment_topic_seed_loader import (
    REQUIRED_COMMENT_TOPIC_CODES,
    CommentTopicSeedLoader,
    CommentTopicSeedValidationError,
)
from app.services.core3_real_data.constants import CORE3_M05_SEED_VERSION


def test_m05_comment_topic_seed_loader_loads_real_seed_and_required_topics():
    result = CommentTopicSeedLoader().load()
    seed = result.seed
    topic_codes = [topic.topic_code for topic in seed.topics]

    assert seed.seed_version == CORE3_M05_SEED_VERSION
    assert result.seed_version == CORE3_M05_SEED_VERSION
    assert result.raw_version == "core3-mvp-0.2.0"
    assert result.asset_version == "core3-mvp-0.2.0"
    assert result.comment_topic_count == len(seed.topics) == 16
    assert len(topic_codes) == len(set(topic_codes))
    assert set(topic_codes) == REQUIRED_COMMENT_TOPIC_CODES
    assert result.required_topic_codes == sorted(REQUIRED_COMMENT_TOPIC_CODES)
    assert result.seed_content_hash.startswith("sha256:m05_comment_topic_seed_v1:")
    assert seed.metadata_json["raw_comment_topic_count"] == 16
    assert seed.metadata_json["required_comment_topic_count"] == 16
    assert seed.metadata_json["extra_topic_codes"] == []
    assert seed.metadata_json["seed_content_hash"] == result.seed_content_hash


def test_m05_comment_topic_seed_loader_builds_business_indexes_from_real_seed():
    result = CommentTopicSeedLoader().load()
    seed = result.seed

    assert result.alias_index["画质"] == ["TOPIC_PICTURE_QUALITY"]
    assert "TOPIC_GAMING_SMOOTHNESS" in result.keyword_index["游戏"]
    assert set(result.positive_keyword_index["不卡"]) == {
        "TOPIC_GAMING_SMOOTHNESS",
        "TOPIC_SPORTS_WATCHING",
    }
    assert result.negative_keyword_index["广告多"] == ["TOPIC_SYSTEM_ADS_PERFORMANCE"]
    assert result.ignored_source_type_counts == {"market_fact": 1}
    assert result.topic_group_counts == {
        "market_perception": 1,
        "product_experience": 12,
        "product_risk": 2,
        "service_experience": 1,
    }
    assert seed.metadata_json["keyword_index"] == result.keyword_index
    assert seed.metadata_json["alias_index"] == result.alias_index
    assert seed.metadata_json["dimension_path_index"] == {}


def test_m05_comment_topic_seed_loader_preserves_mappings_without_final_conclusions():
    seed = CommentTopicSeedLoader().load_seed()
    gaming = seed.topic_by_code["TOPIC_GAMING_SMOOTHNESS"]
    service = seed.topic_by_code["TOPIC_INSTALLATION_SERVICE"]
    price = seed.topic_by_code["TOPIC_PRICE_VALUE"]

    assert gaming.source_types == ["comment_text"]
    assert gaming.aliases == ["游戏体验", "游戏流畅", "主机游戏"]
    assert gaming.activates_product_claim is True
    assert gaming.service_guardrail is False
    assert gaming.mapped_claim_codes == [
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_GAMING_LOW_LATENCY",
        "CLAIM_HDMI_2_1_GAMING",
    ]
    assert gaming.mapped_task_codes == ["TASK_GAMING_ENTERTAINMENT"]
    assert gaming.mapped_battlefield_codes == ["BF_GAMING_SPORTS"]

    assert service.topic_group == "service_experience"
    assert service.activates_product_claim is False
    assert service.service_guardrail is True
    assert price.topic_group == "market_perception"
    assert price.source_types == ["comment_text"]

    model_fields = type(gaming).model_fields
    assert set(model_fields) >= {
        "topic_code",
        "topic_name",
        "topic_group",
        "aliases",
        "keywords",
        "positive_keywords",
        "negative_keywords",
        "source_types",
        "evidence_requirement",
        "mapped_claim_codes",
        "mapped_task_codes",
        "mapped_battlefield_codes",
        "activates_product_claim",
        "service_guardrail",
    }
    assert "task_code" not in model_fields
    assert "battlefield_code" not in model_fields
    assert "competitor_sku_code" not in model_fields


def test_m05_comment_topic_seed_loader_validates_required_root_and_fields(tmp_path):
    missing_root_path = tmp_path / "missing_root.json"
    missing_root_path.write_text(json.dumps({"version": "test"}), encoding="utf-8")

    with pytest.raises(CommentTopicSeedValidationError, match="comment_topics"):
        CommentTopicSeedLoader(missing_root_path).load()

    missing_field_path = tmp_path / "missing_field.json"
    missing_field_path.write_text(
        json.dumps(
            {
                "version": "test",
                "comment_topics": [
                    {
                        "topic_code": "TOPIC_PICTURE_QUALITY",
                        "topic_name": "画质体验",
                        "topic_group": "product_experience",
                        "source_types": ["comment_text"],
                        "mapped_claim_codes": ["CLAIM_HIGH_BRIGHTNESS_HDR"],
                        "mapped_task_codes": ["TASK_PREMIUM_PICTURE_AV"],
                        "mapped_battlefield_codes": ["BF_PREMIUM_PICTURE"],
                        "activates_product_claim": True,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(CommentTopicSeedValidationError) as exc_info:
        CommentTopicSeedLoader(missing_field_path).load()

    message = str(exc_info.value)
    assert "definition is required" in message
    assert "aliases is required" in message
    assert "keywords is required" in message
    assert "positive_keywords is required" in message
    assert "negative_keywords is required" in message
    assert "evidence_requirement is required" in message
    assert "missing required topic codes" in message


def test_m05_comment_topic_seed_loader_rejects_duplicate_unknown_and_non_comment_sources(tmp_path):
    bad_seed = {
        "version": "test",
        "comment_topics": [
            _topic("TOPIC_PICTURE_QUALITY", source_types=["comment_text"], topic_group="product_experience"),
            _topic("TOPIC_PICTURE_QUALITY", source_types=["review_note"], topic_group="product_experience"),
            _topic("TOPIC_BRIGHTNESS_HDR", source_types=["market_fact"], topic_group="market_perception"),
            _topic("TOPIC_DARK_SCENE_CONTRAST", source_types=["comment_text"], topic_group="unknown_group"),
            _topic("TOPIC_SPORTS_WATCHING", source_types=["comment_text"], activates_product_claim="yes"),
        ],
    }
    bad_seed_path = tmp_path / "bad_seed.json"
    bad_seed_path.write_text(json.dumps(bad_seed, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(CommentTopicSeedValidationError) as exc_info:
        CommentTopicSeedLoader(bad_seed_path).load()

    message = str(exc_info.value)
    assert "topic_code must be unique" in message
    assert "unsupported source type: review_note" in message
    assert "has no M05-usable source type" in message
    assert "topic_group is unsupported: unknown_group" in message
    assert "activates_product_claim must be a boolean" in message


def _topic(
    topic_code: str,
    *,
    source_types: list[str],
    topic_group: str = "product_experience",
    activates_product_claim: bool | str = True,
) -> dict[str, object]:
    return {
        "topic_code": topic_code,
        "topic_name": "测试主题",
        "definition": "测试定义",
        "topic_group": topic_group,
        "aliases": ["测试主题"],
        "keywords": ["测试"],
        "positive_keywords": ["好"],
        "negative_keywords": ["差"],
        "source_types": source_types,
        "evidence_requirement": ["comment_sentence_match"],
        "mapped_claim_codes": ["CLAIM_HIGH_BRIGHTNESS_HDR"],
        "mapped_task_codes": ["TASK_PREMIUM_PICTURE_AV"],
        "mapped_battlefield_codes": ["BF_PREMIUM_PICTURE"],
        "activates_product_claim": activates_product_claim,
    }
