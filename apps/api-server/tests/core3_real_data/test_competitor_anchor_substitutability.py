from app.services.core3_real_data.analyst.anchor_substitutability import (
    ValueAnchorMatcher,
)
from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    FixturePurchaseReasonProfileReader,
    PurchaseReasonProfileLookupKey,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamReadContract,
)


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
BATCH_ID = "m00_20260623014631_c8630747"
M12D_VERSION = "m12d_tv_purchase_reason_profile_v0_1_draft"


def test_anchor_substitutability_reads_m12d_fixture_and_degrades_review_profiles() -> (
    None
):
    reader = FixturePurchaseReasonProfileReader.from_default_fixture()
    target = _read_fixture_contract(reader, "TV00029112")
    candidate = _read_fixture_contract(reader, "TV00029936")

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.pair_scoring_allowed is True
    assert result.requires_review is True
    assert result.primary_direct_eligible is False
    assert result.anchor_substitutability_score == 11
    assert result.anchor_substitutability_level == "medium"
    assert result.score_breakdown.target_core_anchor_coverage == 5
    assert "画质配置解释加价" in result.shared_core_anchors
    assert "贵得值的体验升级" in result.shared_core_anchors
    assert result.match_details[0].match_type in {
        "exact_substitute",
        "candidate_stronger",
    }
    assert "排序结论必须同步降置信度" in result.anchor_substitution_summary_cn


def test_anchor_substitutability_candidate_missing_blocks_pair_scoring() -> None:
    reader = FixturePurchaseReasonProfileReader.from_default_fixture()
    target = _read_fixture_contract(reader, "TV00029112")
    candidate = _read_fixture_contract(reader, "TV_UNKNOWN_CANDIDATE")

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.anchor_substitutability_score == 0
    assert result.anchor_substitutability_level == "blocked"
    assert result.pair_scoring_allowed is False
    assert result.primary_direct_eligible is False
    assert "画质配置解释加价" in result.target_only_anchors
    assert "不能依赖关键价值锚点进入 Top 3" in result.anchor_substitution_summary_cn


def test_anchor_substitutability_supporting_only_cannot_be_primary_direct() -> None:
    target = _contract(
        sku_code="TARGET",
        core_codes=["picture_upgrade_justifies_price"],
        anchors=[
            _anchor(
                "picture_upgrade_justifies_price",
                "画质配置解释加价",
                "core_payment",
                "strong",
                "0.85",
            ),
        ],
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        core_codes=[],
        supporting_codes=["picture_upgrade_justifies_price"],
        anchors=[
            _anchor(
                "picture_upgrade_justifies_price",
                "画质配置解释加价",
                "supporting",
                "strong",
                "0.82",
            ),
        ],
    )

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.anchor_substitutability_score == 6
    assert result.anchor_substitutability_level == "insufficient"
    assert result.primary_direct_eligible is False
    assert result.match_details[0].match_type == "adjacent_substitute"
    assert "target_core_anchor_not_exactly_covered" in result.gate_reasons


def test_anchor_substitutability_weak_expression_does_not_push_score() -> None:
    target = _contract(
        sku_code="TARGET",
        core_codes=["same_price_core_config_gain"],
        anchors=[
            _anchor(
                "same_price_core_config_gain",
                "同价位核心配置获得感",
                "core_payment",
                "medium",
                "0.70",
            ),
        ],
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        core_codes=[],
        weak_codes=["same_price_core_config_gain"],
        anchors=[
            _anchor(
                "same_price_core_config_gain",
                "同价位核心配置获得感",
                "weak_expression",
                "weak",
                "0.40",
            ),
        ],
    )

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.anchor_substitutability_score == 0
    assert result.anchor_substitutability_level == "blocked"
    assert result.shared_core_anchors == []
    assert result.pair_scoring_allowed is False
    assert result.primary_direct_eligible is False


def test_anchor_substitutability_candidate_stronger_on_target_core_anchor() -> None:
    target = _contract(
        sku_code="TARGET",
        core_codes=["picture_upgrade_justifies_price"],
        anchors=[
            _anchor(
                "picture_upgrade_justifies_price",
                "画质配置解释加价",
                "core_payment",
                "medium",
                "0.65",
            ),
        ],
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        core_codes=["picture_upgrade_justifies_price"],
        anchors=[
            _anchor(
                "picture_upgrade_justifies_price",
                "画质配置解释加价",
                "core_payment",
                "strong",
                "0.90",
            ),
        ],
    )

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.anchor_substitutability_score == 15
    assert result.anchor_substitutability_level == "strong"
    assert result.candidate_stronger_anchors == ["画质配置解释加价"]
    assert result.primary_direct_eligible is True
    assert result.to_legacy_value_anchor()["score"] == result.normalized_score


def test_anchor_substitutability_does_not_count_proposition_as_purchase_reason() -> (
    None
):
    target = _contract(
        sku_code="TARGET",
        core_codes=["family_operation_less_friction"],
        anchors=[
            _anchor(
                "family_operation_less_friction",
                "家庭操作更省心",
                "core_payment",
                "strong",
                "0.85",
                establishment_status="established",
            ),
        ],
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        core_codes=[],
        supporting_codes=["family_operation_less_friction"],
        anchors=[
            _anchor(
                "family_operation_less_friction",
                "家庭操作更省心",
                "supporting",
                "strong",
                "0.90",
                establishment_status="proposition_only",
            ),
        ],
    )

    result = ValueAnchorMatcher().match(
        target_contract=target, candidate_contract=candidate
    )

    assert result.anchor_substitutability_score == 0
    assert result.shared_core_anchors == []
    assert result.proposition_only_anchors == ["家庭操作更省心"]
    assert result.match_details[0].match_type == "proposition_only"
    assert "希望传达但尚未观察到用户承接" in result.anchor_substitution_summary_cn


def _read_fixture_contract(
    reader: FixturePurchaseReasonProfileReader,
    sku_code: str,
) -> M12DDownstreamReadContract:
    return reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            m12d_profile_version=M12D_VERSION,
            sku_code=sku_code,
        )
    )


def _contract(
    *,
    sku_code: str,
    anchors: list[dict[str, object]],
    core_codes: list[str],
    supporting_codes: list[str] | None = None,
    weak_codes: list[str] | None = None,
    risk_codes: list[str] | None = None,
    confidence: str = "0.8200",
) -> M12DDownstreamReadContract:
    comparison_mode = (
        "strong" if core_codes else "limited" if supporting_codes else "facts_only"
    )
    return M12DDownstreamReadContract.model_validate(
        {
            "found": True,
            "lookup_key": {
                "project_id": "project_anchor_match",
                "category_code": "TV",
                "batch_id": "batch_anchor_match",
                "m12d_profile_version": "m12d_anchor_match_v1",
                "sku_code": sku_code,
            },
            "consumption_state": "published_ready",
            "downstream_action": "normal_pair_scoring",
            "message_cn": "已发布 M12D 画像可正常消费。",
            "release_quality_status": "ready",
            "capabilities": {
                "comparison_mode": comparison_mode,
                "fact_dimensions_allowed": True,
                "proposition_comparison_allowed": True,
                "established_reason_comparison_allowed": comparison_mode
                in {"strong", "limited"},
                "strong_reason_comparison_allowed": comparison_mode == "strong",
                "pressure_comparison_allowed": comparison_mode in {"strong", "limited"},
            },
            "profile": {
                "project_id": "project_anchor_match",
                "category_code": "TV",
                "batch_id": "batch_anchor_match",
                "product_category": "TV",
                "m12d_profile_version": "m12d_anchor_match_v1",
                "sku_code": sku_code,
                "display_name_cn": sku_code,
                "status": "ready",
                "profile_confidence": confidence,
                "confidence_level": "high",
                "core_reasons_cn": [
                    anchor["anchor_cn"]
                    for anchor in anchors
                    if anchor["anchor_code"] in core_codes
                ],
                "core_payment_anchors": core_codes,
                "supporting_anchors": supporting_codes or [],
                "weak_expression_anchors": weak_codes or [],
                "risk_drag_anchors": risk_codes or [],
                "anchors": anchors,
            },
        }
    )


def _anchor(
    code: str,
    name: str,
    role: str,
    strength: str,
    confidence: str,
    *,
    family: str = "picture_upgrade",
    domains: list[str] | None = None,
    establishment_status: str = "unassessed",
) -> dict[str, object]:
    return {
        "anchor_code": code,
        "anchor_cn": name,
        "anchor_family_code": family,
        "anchor_rank": 1,
        "role": role,
        "evidence_strength": strength,
        "confidence": confidence,
        "establishment_status": establishment_status,
        "evidence_domains": domains
        or [
            "param_fact",
            "fact_claim",
            "comment_perception",
            "claim_value",
            "semantic_scene",
            "market_acceptance",
        ],
        "support_summary_cn": f"{name}测试证据。",
    }
