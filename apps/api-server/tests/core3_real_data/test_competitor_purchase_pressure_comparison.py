from app.services.core3_real_data.analyst.purchase_pressure_comparison import (
    PurchasePressureComparator,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamReadContract,
)


def test_purchase_pressure_is_compared_without_deleting_established_reason() -> None:
    target = _contract(
        sku_code="TARGET",
        anchor=_anchor(
            establishment_status="established",
            pressure_level="medium",
            pressure_summary_cn="画质理由成立，但反光体验存在中等争议。",
        ),
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        anchor=_anchor(
            establishment_status="established",
            pressure_level="high",
            pressure_summary_cn="画质理由成立，但暗场细节负面较集中。",
        ),
    )

    result = PurchasePressureComparator().compare(
        target_contract=target, candidate_contract=candidate
    )

    assert result.comparison_allowed is True
    assert len(result.shared_anchor_comparisons) == 1
    assert result.target_highest_pressure_level == "medium"
    assert result.candidate_highest_pressure_level == "high"
    assert "不改变理由是否成立" in result.summary_cn


def test_purchase_pressure_excludes_proposition_only_from_shared_reasons() -> None:
    target = _contract(
        sku_code="TARGET",
        anchor=_anchor(
            establishment_status="established",
            pressure_level="low",
            pressure_summary_cn="已成立理由存在少量顾虑。",
        ),
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        anchor=_anchor(
            establishment_status="proposition_only",
            pressure_level="high",
            pressure_summary_cn="产品希望传达，但没有用户承接。",
        ),
    )

    result = PurchasePressureComparator().compare(
        target_contract=target, candidate_contract=candidate
    )

    assert result.shared_anchor_comparisons == []
    assert result.candidate_highest_pressure_level == "unassessed"
    assert "暂无共同成立的购买理由" in result.summary_cn


def test_purchase_pressure_respects_sku_dimension_capabilities() -> None:
    target = _contract(
        sku_code="TARGET",
        anchor=_anchor(
            establishment_status="established",
            pressure_level="medium",
            pressure_summary_cn="目标存在中等顾虑。",
        ),
    )
    candidate = _contract(
        sku_code="CANDIDATE",
        anchor=_anchor(
            establishment_status="proposition_only",
            pressure_level="none",
            pressure_summary_cn="",
        ),
        comparison_mode="facts_only",
        pressure_comparison_allowed=False,
    )

    result = PurchasePressureComparator().compare(
        target_contract=target, candidate_contract=candidate
    )

    assert result.comparison_allowed is False
    assert "其他参数、卖点和市场维度仍按各自消费能力判断" in result.summary_cn


def _contract(
    *,
    sku_code: str,
    anchor: dict[str, object],
    comparison_mode: str = "strong",
    pressure_comparison_allowed: bool = True,
) -> M12DDownstreamReadContract:
    return M12DDownstreamReadContract.model_validate(
        {
            "found": True,
            "lookup_key": {
                "project_id": "project-pressure-comparison",
                "category_code": "TV",
                "batch_id": "batch-pressure-comparison",
                "m12d_profile_version": "m12d-pressure-comparison-v1",
                "sku_code": sku_code,
            },
            "consumption_state": "published_ready",
            "downstream_action": "normal_pair_scoring",
            "release_quality_status": "ready",
            "capabilities": {
                "comparison_mode": comparison_mode,
                "fact_dimensions_allowed": True,
                "proposition_comparison_allowed": True,
                "established_reason_comparison_allowed": comparison_mode
                != "facts_only",
                "strong_reason_comparison_allowed": comparison_mode == "strong",
                "pressure_comparison_allowed": pressure_comparison_allowed,
            },
            "profile": {
                "project_id": "project-pressure-comparison",
                "category_code": "TV",
                "batch_id": "batch-pressure-comparison",
                "product_category": "TV",
                "m12d_profile_version": "m12d-pressure-comparison-v1",
                "sku_code": sku_code,
                "display_name_cn": sku_code,
                "status": "ready" if comparison_mode == "strong" else "ready_limited",
                "profile_confidence": "0.8500",
                "core_reasons_cn": [anchor["anchor_cn"]]
                if comparison_mode == "strong"
                else [],
                "core_payment_anchors": [anchor["anchor_code"]]
                if comparison_mode == "strong"
                else [],
                "supporting_anchors": [anchor["anchor_code"]]
                if comparison_mode != "strong"
                else [],
                "established_anchors": [anchor["anchor_code"]]
                if anchor["establishment_status"] == "established"
                else [],
                "proposition_anchors": [anchor["anchor_code"]]
                if anchor["establishment_status"] == "proposition_only"
                else [],
                "anchors": [anchor],
            },
        }
    )


def _anchor(
    *, establishment_status: str, pressure_level: str, pressure_summary_cn: str
) -> dict[str, object]:
    return {
        "anchor_code": "picture_upgrade_justifies_price",
        "anchor_cn": "画质升级值得加价",
        "anchor_rank": 1,
        "role": "core_payment"
        if establishment_status == "established"
        else "supporting",
        "evidence_strength": "strong",
        "confidence": "0.8500",
        "establishment_status": establishment_status,
        "establishment_score": "10.0000"
        if establishment_status == "established"
        else "5.0000",
        "user_validation_status": "user_validated"
        if establishment_status == "established"
        else "not_observed",
        "core_eligible": establishment_status == "established",
        "pressure_level": pressure_level,
        "pressure_summary_cn": pressure_summary_cn,
        "evidence_domains": [
            "param_fact",
            "fact_claim",
            "comment_perception",
            "semantic_scene",
        ],
    }
