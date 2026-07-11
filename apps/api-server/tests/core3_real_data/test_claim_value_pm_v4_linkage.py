from __future__ import annotations

import json
from pathlib import Path

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    EvidenceRef,
    LineageGate,
    LineageIssue,
    PurchaseReasonSnapshot,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
    SkuIdentity,
    SourceStatus,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_reason_value_bundle_links,
)
from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    FixturePurchaseReasonProfileReader,
    PurchaseReasonProfileLookupKey,
    default_m12d_contract_fixture_path,
)


def _ref(module_code: str, record_id: str) -> EvidenceRef:
    return EvidenceRef(
        module_code=module_code,
        record_type=f"table_{module_code.lower()}",
        record_id=record_id,
        result_hash=f"hash-{record_id}",
        batch_id="batch-1",
        rule_version=f"{module_code.lower()}-v1",
    )


def _atom(
    text: str,
    *,
    key: str = "comment-1",
    subdimension: str = "picture_brightness_hdr",
    polarity: str = "positive",
    supported_params: list[str] | None = None,
    contradicted_params: list[str] | None = None,
) -> dict:
    return {
        "source_comment_key": key,
        "source_comment_id": key,
        "sentence_seq": 1,
        "clean_comment_text": text,
        "dimension_code": "picture_screen_experience",
        "subdimension_code": subdimension,
        "dimension_type": "product_experience",
        "polarity": polarity,
        "support_relation": (
            "contradicts_sku_param_claim"
            if polarity in {"negative", "mixed"}
            else "supports_sku_param_claim"
        ),
        "supported_param_codes": supported_params or [],
        "contradicted_param_codes": contradicted_params or [],
        "supported_claim_codes": [],
        "contradicted_claim_codes": [],
        "evidence_ids": [f"evidence-{key}"],
        "quality_flags": [],
        "confidence": 0.9,
    }


def _anchor(
    code: str,
    name_cn: str,
    family: str,
    *,
    role: str = "core_payment",
) -> dict:
    return {
        "anchor_code": code,
        "anchor_cn": name_cn,
        "anchor_family_code": family,
        "anchor_rank": 1,
        "role": role,
        "evidence_strength": "strong" if role == "core_payment" else "medium",
        "confidence": "0.9",
        "evidence_domains": ["param_fact", "comment_perception"],
        "support_summary_cn": "fixture",
        "weakness_summary_cn": "",
        "risk_flags": [],
        "source_refs": [],
    }


def _context(
    *,
    atoms: list[dict] | None = None,
    anchors: list[dict] | None = None,
    purchase_found: bool = True,
    lineage_conflict: bool = False,
) -> SellpointValueV4Context:
    refs = [_ref("M03B", "param"), _ref("M04C", "claim"), _ref("M05C", "comment")]
    source_status = {
        module: SourceStatus(availability="present", usability="usable")
        for module in ("M03B", "M04C", "M05C", "M11C", "M11D")
    }
    facts = {
        "parameter_fact": {
            "summary": {"conflict_count": 0},
            "dimension_tier_profile": {
                "picture": "premium",
                "gaming": "enhanced",
                "system": "base",
            },
            "core_params": {
                "picture": {
                    "screen_size_inch": {"normalized_value": 65},
                    "mini_led_flag": {"normalized_value": True},
                    "declared_brightness_nit_or_band": {
                        "normalized_value": {"value": 5200, "unit": "nits"}
                    },
                    "local_dimming_zone_count": {"normalized_value": 1920},
                    "wide_color_gamut_pct": {"normalized_value": 98},
                },
                "gaming": {"refresh_rate_hz": {"normalized_value": 300}},
                "system": {
                    "ai_chip_flag": {"normalized_value": True},
                    "memory_capacity_gb": {"normalized_value": 4},
                },
                "eye_care": {"low_blue_light_flag": {"normalized_value": True}},
            },
        },
        "claim_fact": {
            "fact_claim_codes": [
                "tv_claim_miniled_display",
                "tv_claim_hdr_high_brightness",
                "tv_claim_local_dimming",
                "tv_claim_high_refresh_rate",
                "tv_claim_chip_performance",
            ]
        },
        "comment_fact": {},
    }
    snapshot_payload = {
        "identity": SkuIdentity(
            sku_code="TV00029112",
            brand_name="海信",
            model_name="65E7Q",
            product_category="TV",
            screen_size_inch=65,
        ),
        "source_status": source_status,
        "facts": facts,
        "comment_outcomes": atoms or [],
        "market": {},
        "tasks": [],
        "target_groups": [],
        "battlefields": [
            {
                "primary_battlefield_code": "BF_PREMIUM_PICTURE_UPGRADE",
                "secondary_battlefield_codes": [
                    "BF_GAMING_SPORTS_FLUENCY",
                    "BF_SMART_CONNECTED_EXPERIENCE",
                ],
                "opportunity_battlefield_codes": ["BF_EYE_CARE_FAMILY_COMFORT"],
            }
        ],
        "semantic_market": [
            {
                "dimension_code": "BF_PREMIUM_PICTURE_UPGRADE",
                "dimension_name": "高端画质升级战场",
                "market_space": {"estimated_sales_volume": 1000},
            }
        ],
        "source_refs": refs,
    }
    snapshot = SkuEvidenceSnapshot(
        **snapshot_payload,
        snapshot_hash=canonical_v4_hash(snapshot_payload),
    )
    if lineage_conflict:
        issues = [
            LineageIssue(
                code="version_lineage_conflict",
                severity="blocking",
                scope="relation",
                message_cn="M03B version conflict",
                affected_module_codes=["M03B"],
            )
        ]
        lineage_status = "stale_conflict"
    else:
        issues = []
        lineage_status = "aligned"
    lineage = LineageGate(
        status=lineage_status,
        published_lineage=[],
        current_validation_lineage=[],
        issues=issues,
        blocked_reason_codes=["version_lineage_conflict"] if issues else [],
    )
    reason_anchors = anchors or [
        _anchor(
            "picture_upgrade_justifies_price",
            "画质配置解释加价",
            "picture_upgrade",
        ),
        _anchor(
            "family_operation_less_friction",
            "家庭多设备使用更省操作",
            "operation_convenience",
            role="weak_expression",
        ),
    ]
    purchase = PurchaseReasonSnapshot(
        found=purchase_found,
        lineage_status=lineage_status if purchase_found else "unresolved",
        profile_version="m12d-v1" if purchase_found else None,
        release_id="m12d-v1" if purchase_found else None,
        anchors=reason_anchors if purchase_found else [],
        review_required=False,
        source_refs=[_ref("M12D", "profile")] if purchase_found else [],
    )
    context_payload = {
        "schema_version": "sellpoint_value_v4_context_v1",
        "project_id": "project-1",
        "category_code": "TV",
        "requested_batch_id": "batch-1",
        "serving_batch_ids": ["batch-1"],
        "market_window": "full_observed_window",
        "target": snapshot.identity,
        "authority_manifest": [],
        "lineage_gate": lineage,
        "target_snapshot": snapshot,
        "purchase_reason_profile": purchase,
        "candidate_snapshots": [],
        "market_cells": [],
        "m12c_pool_tiers": [],
        "evidence_refs": refs,
    }
    return SellpointValueV4Context(
        **context_payload,
        input_hash=canonical_v4_hash(context_payload),
    )


def test_concrete_post_purchase_outcome_establishes_picture_value() -> None:
    context = _context(atoms=[_atom("白天阳光照进客厅也看得清，暗场层次也清楚")])

    links = build_reason_value_bundle_links(context)

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert picture.value_status == "partial"
    assert picture.link_status == "partial"
    assert picture.battlefield_code == "BF_PREMIUM_PICTURE_UPGRADE"
    assert picture.battlefield_market_space == {"estimated_sales_volume": 1000}
    assert "只部分支持" in picture.outcome_cn
    assert picture.bundle.collinearity_group == "collinear:picture_upgrade_perception"
    assert picture.bundle.independently_identifiable is False
    assert {member.capability_code for member in picture.bundle.members} == {
        "tv_bright_room_dark_detail",
        "tv_color_picture_truth",
    }


def test_generic_picture_praise_does_not_establish_technical_value() -> None:
    links = build_reason_value_bundle_links(
        _context(
            atoms=[
                _atom("画质很好，非常清晰", subdimension="picture_clarity_resolution")
            ]
        )
    )

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert picture.value_status == "not_observed"
    assert picture.link_status == "partial"
    assert any("泛化好评" in item for item in picture.limitations)
    assert "尚未观察到" in picture.outcome_cn


def test_all_picture_bundle_results_can_establish_the_theme() -> None:
    links = build_reason_value_bundle_links(
        _context(
            atoms=[
                _atom("白天阳光照进客厅也看得清，暗场层次也清楚", key="brightness"),
                _atom(
                    "肤色自然，颜色还原很真实",
                    key="color",
                    subdimension="picture_color_accuracy",
                ),
            ]
        )
    )

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert picture.value_status == "established"
    assert picture.link_status == "supported"


def test_no_comment_keeps_capability_confirmed_but_value_not_observed() -> None:
    links = build_reason_value_bundle_links(_context(atoms=[]))

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert any(member.fact_status == "confirmed" for member in picture.bundle.members)
    assert picture.value_status == "not_observed"
    assert picture.link_status == "partial"


def test_negative_and_positive_picture_evidence_stays_conflicted() -> None:
    links = build_reason_value_bundle_links(
        _context(
            atoms=[
                _atom("5200nit亮度，暗场层次很清楚", key="positive"),
                _atom(
                    "暗场漏光和光晕很明显",
                    key="negative",
                    polarity="negative",
                    contradicted_params=["local_dimming_zone_count"],
                ),
            ]
        )
    )

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert picture.value_status == "conflicted"
    assert picture.link_status == "conflicted"
    assert "正反并存" in picture.outcome_cn


def test_weak_expression_purchase_reason_is_not_promoted() -> None:
    links = build_reason_value_bundle_links(_context(atoms=[]))

    assert "family_operation_less_friction" not in {
        item.purchase_reason_code for item in links
    }


def test_system_boot_outcome_only_supports_operation_not_ai_picture() -> None:
    context = _context(
        atoms=[
            _atom(
                "开机很快，切换也不卡",
                subdimension="system_smooth_ads",
            )
        ],
        anchors=[
            _anchor(
                "family_operation_less_friction",
                "家庭多设备使用更省操作",
                "operation_convenience",
                role="supporting",
            )
        ],
    )

    links = build_reason_value_bundle_links(context)

    assert len(links) == 1
    assert links[0].realized_value_code == "operation_convenience_perception"
    assert links[0].value_status == "established"
    assert (
        links[0].bundle.members[0].capability_code == "tv_system_interaction_efficiency"
    )
    assert "AI画质" not in links[0].outcome_cn


def test_duplicate_sentence_atoms_do_not_change_relation_hash() -> None:
    one = _atom(
        "5200nit亮度，白天也看得清",
        supported_params=["declared_brightness_nit_or_band"],
    )
    duplicate = {
        **one,
        "subdimension_code": "picture_local_dimming_black",
        "supported_param_codes": ["local_dimming_zone_count"],
    }

    single_links = build_reason_value_bundle_links(_context(atoms=[one]))
    duplicate_links = build_reason_value_bundle_links(_context(atoms=[one, duplicate]))

    single = next(
        item
        for item in single_links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    duplicated = next(
        item
        for item in duplicate_links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert single.relation_hash == duplicated.relation_hash


def test_lineage_conflict_blocks_relation_but_not_observed_value() -> None:
    links = build_reason_value_bundle_links(
        _context(
            atoms=[_atom("白天阳光照进客厅也看得清")],
            lineage_conflict=True,
        )
    )

    picture = next(
        item
        for item in links
        if item.realized_value_code == "picture_upgrade_perception"
    )
    assert picture.value_status == "partial"
    assert picture.link_status == "conflicted"
    assert any("版本冲突" in item for item in picture.limitations)


def test_missing_published_purchase_reason_does_not_rebuild_one() -> None:
    assert build_reason_value_bundle_links(_context(purchase_found=False)) == []


def test_65e7q_published_anchors_do_not_invent_post_purchase_value(
    repo_root: Path,
) -> None:
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )
    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id="d8d2245b-358b-4a64-95cc-9d7f2341bd26",
            category_code="TV",
            batch_id="m00_20260623014631_c8630747",
            m12d_profile_version="m12d_tv_purchase_reason_profile_v0_1_draft",
            sku_code="TV00029112",
        )
    )
    assert contract.profile is not None
    anchors = [item.model_dump(mode="json") for item in contract.profile.anchors]

    links = build_reason_value_bundle_links(
        _context(atoms=[], anchors=anchors, lineage_conflict=True)
    )

    assert links
    relation_keys = [
        (item.battlefield_code, item.purchase_reason_code) for item in links
    ]
    assert len(relation_keys) == len(set(relation_keys))
    assert "picture_upgrade_justifies_price" in {
        item.purchase_reason_code for item in links
    }
    multi_theme = next(
        item
        for item in links
        if item.purchase_reason_code == "worth_paying_more_for_experience_upgrade"
    )
    assert multi_theme.realized_value_code.startswith("value_combo:")
    assert "＋" in multi_theme.realized_value_name_cn
    assert "same_price_core_config_gain" not in {
        item.purchase_reason_code for item in links
    }
    assert "family_operation_less_friction" not in {
        item.purchase_reason_code for item in links
    }
    assert all(item.value_status == "not_observed" for item in links)
    assert all(item.link_status == "conflicted" for item in links)
    serialized = json.dumps(
        [item.model_dump(mode="json") for item in links], ensure_ascii=False
    )
    assert "WTP" not in serialized
    assert "建议涨价" not in serialized


def test_g04_models_match_frozen_contract(repo_root: Path) -> None:
    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G02_schema_contract.json"
        ).read_text(encoding="utf-8")
    )["models"]
    from app.services.core3_real_data.analyst import (
        claim_value_pm_v4_schemas as schemas,
    )

    for name in ("BundleMember", "SellpointBundle", "ReasonValueBundleLink"):
        model = getattr(schemas, name)
        assert set(model.model_fields) == set(contract[name]["fields"])
        assert {
            key for key, field in model.model_fields.items() if field.is_required()
        } == set(contract[name]["required"])
