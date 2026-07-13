from __future__ import annotations

from app.services.core3_real_data.analyst.analyst_repository import (
    _m12c_rule_version,
    _m12c_population,
    _sellpoint_m12c_population,
)
from app.services.core3_real_data.analyst.claim_value_pm_category_config import (
    AC_BATTLEFIELD_CN,
    product_form_feature,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_reason_value_bundle_links,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    adapt_v4_context_to_v5,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_counterfactuals import (
    _same_size,
)
from app.services.core3_real_data.constants import (
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
)
from tests.core3_real_data.test_claim_value_pm_v4_linkage import (
    _anchor,
    _atom,
    _context,
)


def _ac_context():
    context = _context(
        atoms=[
            _atom(
                "1.5匹制冷很快，卧室很快就凉了",
                subdimension="cooling_effect",
                supported_params=["horsepower_hp", "cooling_capacity_w"],
            )
        ],
        anchors=[
            _anchor(
                "room_size_capacity_match_reduces_risk",
                "匹数空间匹配降低买小风险",
                "capacity_match",
            )
        ],
    )
    identity = context.target_snapshot.identity.model_copy(
        update={
            "sku_code": "AC00032338",
            "product_category": "AC",
            "screen_size_inch": None,
            "size_tier": "wall_hp_1_5",
            "price_band": "mid",
        }
    )
    facts = {
        "parameter_fact": {
            "summary": {"conflict_count": 0},
            "dimension_tier_profile": {
                "installation": "wall_mounted",
                "horsepower": "hp_1_5",
                "cooling_capacity": "cooling_1_5_3000_3999",
                "energy": "energy_grade_1",
            },
            "core_params": {
                "capacity": {
                    "installation_type": {"normalized_value": "wall_mounted"},
                    "horsepower_hp": {"normalized_value": 1.5},
                    "cooling_capacity_w": {"normalized_value": 3500},
                }
            },
        },
        "claim_fact": {
            "fact_claim_codes": [
                "ac_claim_fast_cooling_heating",
                "ac_claim_installation_space_design",
            ]
        },
        "comment_fact": {},
    }
    target = context.target_snapshot.model_copy(
        update={
            "identity": identity,
            "facts": facts,
            "battlefields": [
                {
                    "primary_battlefield_code": "BF_WALL_1_5_MAINSTREAM_VALUE",
                    "secondary_battlefield_codes": [
                        "BF_WALL_1_5_SLEEP_COMFORT_UPGRADE"
                    ],
                    "opportunity_battlefield_codes": [],
                }
            ],
            "semantic_market": [
                {
                    "dimension_type": "battlefield",
                    "dimension_code": "BF_WALL_1_5_MAINSTREAM_VALUE",
                    "dimension_name": "1.5匹挂机主流性价比战场",
                    "market_space": {"estimated_sales_volume": 1234},
                }
            ],
        }
    )
    return context.model_copy(
        update={
            "category_code": "AC",
            "target": identity,
            "target_snapshot": target,
            "candidate_snapshots": [],
        }
    )


def test_ac_linkage_uses_ac_purchase_reasons_value_units_and_battlefields() -> None:
    links = build_reason_value_bundle_links(_ac_context())

    assert len(links) == 1
    link = links[0]
    assert link.purchase_reason_code == "room_size_capacity_match_reduces_risk"
    assert link.battlefield_code == "BF_WALL_1_5_MAINSTREAM_VALUE"
    assert "冷暖能力确定感" in link.realized_value_name_cn
    assert "安装与空间适配" in link.realized_value_name_cn
    assert {member.capability_code for member in link.bundle.members} == {
        "ac_capacity_space_fit",
        "ac_installation_fit",
    }
    assert all(
        not member.capability_code.startswith("tv_") for member in link.bundle.members
    )


def test_ac_v5_adapter_contains_full_ac_battlefield_taxonomy() -> None:
    adapted = adapt_v4_context_to_v5(_ac_context())
    names = {
        row.battlefield_code: row.battlefield_name_cn
        for row in adapted.battlefield_taxonomy
    }

    assert set(AC_BATTLEFIELD_CN) <= set(names)
    assert names["BF_HUMID_CLIMATE_DEHUMIDIFY"] == "潮湿除湿场景"
    assert not any(code.startswith("BF_PREMIUM_PICTURE") for code in names)


def test_ac_comparability_and_synthetic_feature_use_installation_horsepower_tier() -> (
    None
):
    target = _ac_context().target_snapshot
    same_form = target.model_copy(
        update={"identity": target.identity.model_copy(update={"sku_code": "AC2"})}
    )
    other_form = target.model_copy(
        update={
            "identity": target.identity.model_copy(
                update={"sku_code": "AC3", "size_tier": "floor_hp_3"}
            )
        }
    )

    assert _same_size(target, same_form) is True
    assert _same_size(target, other_form) is False
    assert product_form_feature(target) > 0
    assert product_form_feature(target) != product_form_feature(other_form)


def test_m12c_rule_selection_is_category_specific() -> None:
    assert _m12c_rule_version("AC") == CORE3_M12C_AC_RULE_VERSION
    assert _m12c_rule_version("TV") == CORE3_M12C_TV_RULE_VERSION
    assert _m12c_population("fact_complete_with_comment") == "claim_value_ready_with_comment"
    assert _m12c_population("all_semantic_profiles") == "claim_value_ready"
    assert _sellpoint_m12c_population("AC", "fact_complete_with_comment") == "claim_value_ready_with_comment"
    assert _sellpoint_m12c_population("TV", "fact_complete_with_comment") == (
        "claim_value_ready_with_comment"
    )
