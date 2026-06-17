from decimal import Decimal
from types import SimpleNamespace

from app.services.core3_real_data.battlefield_schemas import M11SkuBattlefieldScoreRecord
from app.services.core3_real_data.battlefield_service import (
    _battlefield_v2_payload,
    _effective_battlefields,
    _score_allocation_eligible,
)


def _definition(
    *,
    code: str,
    name: str,
    allocation_policy: str,
    boundary_policy: str = "product_value",
    downstream_policy: dict | None = None,
    required_evidence: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        dimension_definition_id=f"def-{code}",
        ontology_version_id="ontology-v1",
        dimension_code=code,
        dimension_name_cn=name,
        definition_cn=f"{name}的新版定义",
        definition_status="active",
        boundary_policy=boundary_policy,
        allocation_policy=allocation_policy,
        include_rule_json={},
        required_evidence_json=required_evidence or {},
        downstream_policy_json=downstream_policy or {},
        profile_eligibility_policy_json={},
        support_score=Decimal("0.8000"),
        distinctiveness_score=Decimal("0.7000"),
        sku_coverage_count=12,
        strong_sku_coverage_count=6,
        seed_hash="seed-hash",
        result_hash=f"result-{code}",
    )


def _score(code: str, *, product_anchor: float, market_pool_fit: float = 0.8) -> M11SkuBattlefieldScoreRecord:
    return M11SkuBattlefieldScoreRecord.model_construct(
        battlefield_code=code,
        score_breakdown_json={
            "product_anchor": product_anchor,
            "market_pool_fit": market_pool_fit,
        },
    )


def test_m11_overrides_seed_battlefield_with_m085_active_definition() -> None:
    seed = SimpleNamespace(
        battlefields=(
            {
                "battlefield_code": "BF_FAMILY_VIEWING_UPGRADE",
                "battlefield_name": "家庭观影升级战场",
                "definition": "旧定义",
            },
            {
                "battlefield_code": "BF_SERVICE_ASSURANCE",
                "battlefield_name": "服务保障战场",
                "definition": "服务旧定义",
            },
        )
    )
    definition = _definition(
        code="BF_FAMILY_VIEWING_UPGRADE",
        name="家庭观影舒适战场",
        allocation_policy="eligible_when_product_anchor_present",
        downstream_policy={"allocation_eligible": True, "allocation_block_reasons": []},
        required_evidence={
            "v2_definition": {
                "v2_code": "BF_FAMILY_VIEWING_COMFORT",
                "name_cn": "不应优先使用这个旧 payload 名称",
                "migration_action": "refine",
                "anchor_groups": ["display_picture", "audio_immersion"],
                "market_pool_fit": {
                    "screen_size_classes": ["mainstream_living", "large_upgrade"],
                    "price_positions": ["value", "mainstream", "upper_mainstream"],
                },
            }
        },
    )

    battlefields = _effective_battlefields(seed, [definition])

    assert battlefields[0]["battlefield_name"] == "家庭观影舒适战场"
    assert battlefields[0]["definition"] == "家庭观影舒适战场的新版定义"
    assert battlefields[1]["battlefield_name"] == "服务保障战场"
    assert "_m08_5_definition" not in battlefields[1]
    payload = _battlefield_v2_payload("BF_FAMILY_VIEWING_UPGRADE", battlefields[0])
    assert payload["definition_source"] == "m08_5_active_ontology"
    assert payload["name_cn"] == "家庭观影舒适战场"
    assert payload["allocation_policy"] == "eligible_when_product_anchor_present"
    assert payload["allocation_eligible"] is True


def test_m11_respects_m085_candidate_only_and_diagnostic_policies() -> None:
    large_screen_definition = _definition(
        code="BF_LARGE_SCREEN_VALUE",
        name="大屏换新性价比战场",
        allocation_policy="candidate_only",
        downstream_policy={"allocation_eligible": False, "allocation_block_reasons": ["coverage_too_broad"]},
    )
    design_definition = _definition(
        code="BF_DESIGN_HOME_FIT",
        name="空间适配装修语境",
        allocation_policy="candidate_only",
        boundary_policy="diagnostic_only",
        downstream_policy={"allocation_eligible": False, "allocation_block_reasons": ["context_only"]},
    )
    seed = SimpleNamespace(
        battlefields=(
            {"battlefield_code": "BF_LARGE_SCREEN_VALUE", "battlefield_name": "大屏性价比战场", "definition": "旧定义"},
            {"battlefield_code": "BF_DESIGN_HOME_FIT", "battlefield_name": "家居融合战场", "definition": "旧定义"},
        )
    )
    battlefields = _effective_battlefields(seed, [large_screen_definition, design_definition])

    assert _score_allocation_eligible(_score("BF_LARGE_SCREEN_VALUE", product_anchor=0.9), battlefields[0]) is False
    assert _score_allocation_eligible(_score("BF_DESIGN_HOME_FIT", product_anchor=0.9), battlefields[1]) is False
    assert _battlefield_v2_payload("BF_DESIGN_HOME_FIT", battlefields[1])["boundary_policy"] == "diagnostic_only"


def test_m11_requires_product_anchor_and_market_pool_for_anchor_required_policy() -> None:
    definition = _definition(
        code="BF_GAMING_SPORTS",
        name="游戏体育流畅战场",
        allocation_policy="eligible_when_product_anchor_present",
        downstream_policy={"allocation_eligible": True, "allocation_block_reasons": []},
    )
    seed = SimpleNamespace(
        battlefields=(
            {"battlefield_code": "BF_GAMING_SPORTS", "battlefield_name": "游戏体育战场", "definition": "旧定义"},
        )
    )
    battlefield = _effective_battlefields(seed, [definition])[0]

    assert _score_allocation_eligible(_score("BF_GAMING_SPORTS", product_anchor=0.29), battlefield) is False
    assert _score_allocation_eligible(_score("BF_GAMING_SPORTS", product_anchor=0.6, market_pool_fit=0.29), battlefield) is False
    assert _score_allocation_eligible(_score("BF_GAMING_SPORTS", product_anchor=0.6, market_pool_fit=0.6), battlefield) is True
