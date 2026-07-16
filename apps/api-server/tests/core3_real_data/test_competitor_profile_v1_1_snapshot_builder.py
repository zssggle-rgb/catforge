from __future__ import annotations

import copy
from decimal import Decimal

import pytest

from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_snapshot_builder import (
    SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION,
    VersionSkuAnalysisSnapshotBuildError,
    VersionSkuAnalysisSnapshotBuilder,
    build_authoritative_snapshot_projection,
    snapshot_expected_result_hash,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
)


def _rebuilt(
    bundle: CompetitorProfileCategoryInputBundle,
    mutate,
) -> CompetitorProfileCategoryInputBundle:
    payload = copy.deepcopy(bundle.model_dump(mode="python"))
    mutate(payload)
    return CompetitorProfileCategoryInputBundle.model_validate(payload)


def _build(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
):
    return VersionSkuAnalysisSnapshotBuilder().build(
        bundle,
        competitor_profile_version_id="competitor-profile-v11-test",
        sku_code=sku_code,
    )


def test_tv_snapshot_is_deterministic_shared_and_domain_typed() -> None:
    def add_claims(payload: dict) -> None:
        payload["modules"]["M04C"]["records_by_sku"]["TV000001"][0]["facts"].update(
            {"claim_codes": ["clear-picture"], "fact_claim_codes": ["clear-picture"]}
        )
        payload["modules"]["M05C"]["records_by_sku"]["TV000001"][0]["facts"].update(
            {"supported_claim_codes": ["clear-picture"]}
        )

    bundle = _rebuilt(_category_bundle(), add_claims)
    first = _build(bundle, "TV000001")
    second = _build(bundle, "TV000001")

    assert first == second
    assert first.snapshot_ref == second.snapshot_ref
    assert first.identity_market.sku_code == "TV000001"
    assert first.identity_market.weighted_price == Decimal("5000")
    assert first.identity_market.avg_weekly_sales_volume == Decimal("100")
    assert first.product_form_facts.screen_size_inch == Decimal("65")
    assert len(first.module_availability) == 10
    availability = {row.module_code: row for row in first.module_availability}
    assert all(
        row.availability == "available"
        for code, row in availability.items()
        if code != "M12D"
    )
    assert availability["M12D"].availability == "partial"
    assert first.fact_sections.parameter_items
    assert first.fact_sections.claim_items
    assert first.fact_sections.battlefield_items
    assert first.fact_sections.task_items
    assert first.fact_sections.audience_items
    assert first.fact_sections.claim_value_items
    assert first.fact_sections.purchase_reason_anchors
    assert first.semantic_profiles["M09C"]
    assert first.source_lineage["source_module_versions"]["M12D"]

    all_snapshots = VersionSkuAnalysisSnapshotBuilder().build_many(
        bundle,
        competitor_profile_version_id="competitor-profile-v11-test",
    )
    assert [row.identity_market.sku_code for row in all_snapshots] == (
        bundle.authoritative_sku_codes
    )
    assert len({row.snapshot_ref for row in all_snapshots}) == len(all_snapshots)


def test_authoritative_projection_keeps_typed_facts_without_raw_duplicates() -> None:
    full = _build(_category_bundle(), "TV000001")

    projected = build_authoritative_snapshot_projection(full)

    assert SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION.endswith("projection_v1")
    assert projected.storage_projection_mode == "authoritative_typed"
    assert projected.source_full_result_hash == full.result_hash
    assert projected.snapshot_ref == full.snapshot_ref
    assert projected.input_fingerprint == full.input_fingerprint
    assert projected.result_hash == snapshot_expected_result_hash(projected)
    assert projected.identity_market.sku_code == full.identity_market.sku_code
    assert projected.product_form_facts == full.product_form_facts
    for field_name in (
        "parameter_items",
        "claim_items",
        "battlefield_items",
        "task_items",
        "audience_items",
        "claim_value_items",
        "purchase_reason_anchors",
    ):
        assert len(getattr(projected.fact_sections, field_name)) == len(
            getattr(full.fact_sections, field_name)
        )
    assert projected.source_facts
    assert projected.module_availability == full.module_availability
    assert projected.evidence_refs == full.evidence_refs
    assert projected.semantic_profiles == {}
    assert projected.fact_sections.evidence_sources == []
    assert projected.fact_sections.sections == {}
    assert projected.fact_sections.sku == {}

    def assert_no_nonempty_raw_bags(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "raw_details" or key == "legacy_payload" or (
                    key.startswith("legacy_") and key.endswith("_payload")
                ):
                    assert child == {}
                assert_no_nonempty_raw_bags(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_nonempty_raw_bags(child)

    assert_no_nonempty_raw_bags(projected.model_dump(mode="json"))
    assert len(projected.model_dump_json()) < len(full.model_dump_json())


def test_unknown_null_empty_false_and_zero_are_losslessly_distinct() -> None:
    def mutate(payload: dict) -> None:
        facts = payload["modules"]["M03B"]["records_by_sku"]["TV000001"][0][
            "facts"
        ]
        facts.update(
            {
                "known_false": False,
                "known_zero": 0,
                "known_empty_list": [],
                "known_empty_object": {},
                "explicit_null": None,
                "missing_marker": "",
                "evidence_ids": ["evidence-1"],
                "source_file_ids": ["file-1"],
                "raw_row_ids": ["row-1"],
            }
        )

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    by_path = {
        (row.source_atom, row.source_path): row.values[0]
        for row in snapshot.source_facts
    }
    assert by_path[("M03B", "facts.known_false")].presence == "known"
    assert by_path[("M03B", "facts.known_false")].value is False
    assert by_path[("M03B", "facts.known_zero")].value == 0
    assert by_path[("M03B", "facts.known_empty_list")].value == []
    assert by_path[("M03B", "facts.known_empty_object")].value == {}
    assert by_path[("M03B", "facts.explicit_null")].presence == "explicit_null"
    assert by_path[("M03B", "facts.missing_marker")].presence == "missing"
    m03_ref = next(row for row in snapshot.evidence_refs if row.module_code == "M03B")
    assert m03_ref.evidence_ids == ["evidence-1"]
    assert m03_ref.source_file_ids == ["file-1"]
    assert m03_ref.raw_row_ids == ["row-1"]


def test_duplicate_source_occurrences_keep_order_and_are_not_deduplicated() -> None:
    def mutate(payload: dict) -> None:
        module = payload["modules"]["M12C"]
        rows = module["records_by_sku"]["TV000001"]
        duplicate = copy.deepcopy(rows[0])
        duplicate["record_id"] = f"{duplicate['record_id']}-duplicate"
        duplicate["result_hash"] = "hash:m12c-duplicate"
        rows.append(duplicate)
        rows.sort(key=lambda row: (row["source_batch_id"], row["record_id"]))
        module["record_count"] += 1

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    claim_code = next(
        row
        for row in snapshot.source_facts
        if row.source_atom == "M12C" and row.source_path == "facts.claim_code"
    )
    assert claim_code.occurrence_count == 2
    assert [row.ordinal for row in claim_code.source_occurrences] == [0, 1]
    assert [row.raw_value for row in claim_code.source_occurrences] == [
        "bright-room-clear",
        "bright-room-clear",
    ]
    assert len({row.occurrence_key for row in claim_code.source_occurrences}) == 2


def test_legal_m12c_claims_and_m11d_dimensions_use_entity_set_semantics() -> None:
    def mutate(payload: dict) -> None:
        m12c = payload["modules"]["M12C"]
        second_claim = copy.deepcopy(m12c["records_by_sku"]["TV000001"][0])
        second_claim["record_id"] = f"{second_claim['record_id']}-second-claim"
        second_claim["result_hash"] = "hash:m12c-second-claim"
        second_claim["facts"]["claim_code"] = "dark-detail"
        second_claim["facts"]["claim_name"] = "暗场层次"
        m12c["records_by_sku"]["TV000001"].append(second_claim)
        m12c["records_by_sku"]["TV000001"].sort(
            key=lambda row: (row["source_batch_id"], row["record_id"])
        )
        m12c["record_count"] += 1

        m11d = payload["modules"]["M11D"]
        second_dimension = copy.deepcopy(m11d["records_by_sku"]["TV000001"][0])
        second_dimension["record_id"] = (
            f"{second_dimension['record_id']}-second-dimension"
        )
        second_dimension["result_hash"] = "hash:m11d-second-dimension"
        second_dimension["facts"]["dimension_code"] = "gaming"
        second_dimension["facts"]["allocation_role"] = "secondary"
        m11d["records_by_sku"]["TV000001"].append(second_dimension)
        m11d["records_by_sku"]["TV000001"].sort(
            key=lambda row: (row["source_batch_id"], row["record_id"])
        )
        m11d["record_count"] += 1

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    claim_code_facts = [
        row
        for row in snapshot.source_facts
        if row.source_atom == "M12C" and row.source_path == "facts.claim_code"
    ]
    dimension_code_facts = [
        row
        for row in snapshot.source_facts
        if row.source_atom == "M11D" and row.source_path == "facts.dimension_code"
    ]

    assert len(claim_code_facts) == 2
    assert len(dimension_code_facts) == 2
    assert {
        row.resolved_value.value for row in claim_code_facts if row.resolved_value
    } == {"bright-room-clear", "dark-detail"}
    assert {
        row.resolved_value.value for row in dimension_code_facts if row.resolved_value
    } == {"picture", "gaming"}
    assert all(row.resolved_value.presence == "known" for row in claim_code_facts)
    assert all(row.resolved_value.presence == "known" for row in dimension_code_facts)
    assert all(row.support_status != "contradicted" for row in claim_code_facts)
    assert all(row.support_status != "contradicted" for row in dimension_code_facts)


def test_sparse_modules_degrade_locally_without_blocking_market_facts() -> None:
    snapshot = _build(_category_bundle(), "TV000006")
    availability = {row.module_code: row for row in snapshot.module_availability}

    for module_code in ("M09C", "M10C", "M11C", "M11D", "M12C", "M12D"):
        assert availability[module_code].availability == "unknown"
    assert availability["M03B"].availability == "available"
    assert availability["M07"].availability == "available"
    assert snapshot.identity_market.weighted_price == Decimal("5050")
    assert snapshot.claim_value_snapshot is None
    assert snapshot.claim_contribution_snapshot is None
    assert snapshot.purchase_reason_snapshot is None
    assert "m12d_sku_not_covered_by_locked_authority" in snapshot.limitations


def test_review_and_conflict_are_overlays_and_do_not_cross_modules() -> None:
    def mutate(payload: dict) -> None:
        payload["modules"]["M05C"]["records_by_sku"]["TV000001"][0]["facts"][
            "source_lineage_status"
        ] = "conflict"
        payload["modules"]["M12D"]["records_by_sku"]["TV000001"][0]["facts"][
            "review_required"
        ] = True

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    availability = {row.module_code: row for row in snapshot.module_availability}
    assert availability["M05C"].availability == "conflict"
    assert availability["M05C"].review_required is True
    assert availability["M12D"].availability == "partial"
    assert availability["M12D"].review_required is True
    assert availability["M07"].availability == "available"
    assert availability["M07"].review_required is False


def test_m12c_claim_value_and_contribution_are_normalized_from_locked_rows() -> None:
    def mutate(payload: dict) -> None:
        facts = payload["modules"]["M12C"]["records_by_sku"]["TV000001"][0][
            "facts"
        ]
        facts.update(
            {
                "analysis_population": "claim_value_ready_with_comment",
                "market_window": "full_observed_window",
                    "claim_name": "强光清晰",
                    "claim_dimension": "picture",
                    "claim_value_role": "premium_driver_estimated",
                "context_type": "market_pool",
                "context_code": "pool-65-main",
                "context_name": "65 英寸主流池",
                "size_tier": "65",
                "price_band_group": "middle",
                "claim_evidence_strength": "0.8",
                "param_support_strength": "0.7",
                "comment_support_strength": "0.6",
                "semantic_support_strength": "0.5",
                "estimated_price_premium_abs": "300",
                "estimated_weekly_sales_lift_abs": "12",
                "estimated_weekly_sales_amount_lift_abs": "60000",
                "contribution_share_in_sku": "0.2",
                "attribution_confidence": "0.75",
                "evidence_ids_json": ["claim-evidence-1"],
                "supporting_dimensions_json": {
                    "picture": "supported",
                    "business_claim_type": "premium_payment_claim",
                    "business_claim_type_cn": "高溢价卖点",
                    "business_claim_type_definition_cn": "用户为该卖点支付更高价格。",
                    "claim_value_score": "82",
                    "target_has_claim": True,
                    "market_position_type": "price_and_sales_supported",
                    "market_position_cn": "价格和销量共同验证",
                    "parameter_competitiveness": {
                        "overall_parameter_competitiveness_score": "88",
                        "overall_parameter_competitiveness_level_cn": "领先",
                    },
                    "pool_effect": {
                        "pool_claim_price_delta_abs": "260",
                        "pool_claim_weekly_sales_delta_abs": "9",
                        "pool_claim_weekly_sales_amount_delta_abs": "45000",
                        "with_claim_sku_count": 8,
                        "without_claim_sku_count": 6,
                        "effect_confidence": "0.72",
                    },
                },
                "quality_flags_json": [],
                "reason_cn": "量价与用户证据共同支持",
            }
        )

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    claim_value = snapshot.claim_value_snapshot
    contribution = snapshot.claim_contribution_snapshot

    assert claim_value is not None and contribution is not None
    assert len(claim_value.claim_values) == 1
    assert claim_value.claim_values[0].claim_name == "强光清晰"
    claim = claim_value.claim_values[0]
    assert claim.estimated_contribution["price_premium_abs"] == "300"
    assert claim.claim_value_score == Decimal("82")
    assert claim.business_claim_type == "premium_payment_claim"
    assert claim.business_value_label == "强溢价卖点"
    assert claim.claim_source_type == "target_fact_claim"
    assert claim.market_position is not None
    assert claim.market_position.type == "price_and_sales_supported"
    assert claim.pool_effect["pool_claim_price_delta_abs"] == "260"
    assert claim.sku_excess_explanation is not None
    assert claim.sku_excess_explanation.sku_excess_price_explained_abs == Decimal(
        "300"
    )
    assert len(claim_value.attributions) == 1
    assert claim_value.attributions[0].confidence == Decimal("0.75")
    assert contribution.attribution_count == 1
    assert contribution.attributions == claim_value.attributions
    sku_level = claim_value.sku_level_claim_values[0]
    assert sku_level.claim_value_score == Decimal("82")
    assert sku_level.business_claim_type_cn == "高溢价卖点"
    assert sku_level.parameter_competitiveness[
        "overall_parameter_competitiveness_level_cn"
    ] == "领先"


def test_m12d_purchase_reason_only_materializes_when_required_fields_are_known() -> None:
    incomplete = _build(_category_bundle(), "TV000001")
    assert incomplete.purchase_reason_snapshot is None
    assert "m12d_typed_purchase_reason_incomplete" in incomplete.limitations
    incomplete_availability = next(
        row for row in incomplete.module_availability if row.module_code == "M12D"
    )
    assert incomplete_availability.availability == "partial"
    assert incomplete_availability.review_required is True

    def mutate(payload: dict) -> None:
        facts = payload["modules"]["M12D"]["records_by_sku"]["TV000001"][0][
            "facts"
        ]
        facts.update(
            {
                "status": "ready",
                "profile_confidence": "0.82",
                "core_reasons_json": ["强光清晰"],
                "core_payment_anchors_json": [
                    {
                        "anchor_code": "clear-picture",
                        "anchor_cn": "强光清晰",
                        "role": "core_payment",
                        "core_eligible": True,
                        "establishment_score": "0.9",
                        "establishment_status": "established",
                        "evidence_domains": ["comment", "market"],
                        "evidence_strength": "strong",
                        "user_validation_status": "user_supported",
                        "support_summary_cn": "用户反馈与市场表现共同支持",
                        "weakness_summary_cn": None,
                        "pressure_level": "low",
                        "pressure_summary_cn": "替代压力较低",
                    },
                    {
                        "anchor_cn": "缺少压力字段的次要锚点",
                        "role": "supporting",
                        "core_eligible": False,
                        "establishment_score": "0.4",
                        "establishment_status": "directional",
                        "evidence_strength": "medium",
                        "user_validation_status": "partial",
                    },
                ],
            }
        )

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    reason = snapshot.purchase_reason_snapshot
    assert reason is not None
    assert reason.found is True
    assert reason.profile_confidence == Decimal("0.82")
    assert reason.anchors[0].anchor_cn == "强光清晰"
    assert len(reason.anchors) == 1
    assert reason.core_reasons_cn == ["强光清晰"]
    assert "m12d_typed_purchase_reason_incomplete" in snapshot.limitations
    m12d_availability = next(
        row for row in snapshot.module_availability if row.module_code == "M12D"
    )
    assert m12d_availability.availability == "partial"


def test_m12d_typed_validation_failure_uses_the_same_partial_overlay() -> None:
    def mutate(payload: dict) -> None:
        facts = payload["modules"]["M12D"]["records_by_sku"]["TV000001"][0][
            "facts"
        ]
        facts.update(
            {
                "status": "ready",
                "profile_confidence": "0.8",
                "core_payment_anchors_json": [
                    {
                        "anchor_cn": "无效成立分",
                        "core_eligible": True,
                        "establishment_score": "-1",
                        "establishment_status": "established",
                        "evidence_strength": "strong",
                        "user_validation_status": "user_supported",
                        "pressure_level": "low",
                    }
                ],
            }
        )

    snapshot = _build(_rebuilt(_category_bundle(), mutate), "TV000001")
    assert snapshot.purchase_reason_snapshot is not None
    assert snapshot.purchase_reason_snapshot.anchors == []
    assert "m12d_typed_purchase_reason_incomplete" in snapshot.limitations
    availability = next(
        row for row in snapshot.module_availability if row.module_code == "M12D"
    )
    assert availability.availability == "partial"
    assert availability.review_required is True


def test_ac_snapshot_uses_ac_form_and_never_carries_tv_screen_size() -> None:
    bundle = _category_bundle(
        "AC",
        specs=[_default_spec("AC", 1), _default_spec("AC", 2)],
    )
    snapshot = _build(bundle, "AC000001")

    assert snapshot.category_code == "AC"
    assert snapshot.identity_market.product_category == "AC"
    assert snapshot.identity_market.screen_size_inch is None
    assert snapshot.product_form_facts.screen_size_inch is None
    assert snapshot.product_form_facts.ac_product_form == "wall_mounted"
    assert snapshot.product_form_facts.cooling_capacity_segment == "1.5p"
    assert snapshot.product_form_facts.unknown_reason_codes == []


def test_conflicting_ac_product_form_is_unknown_instead_of_first_value_wins() -> None:
    bundle = _category_bundle(
        "AC",
        specs=[_default_spec("AC", 1), _default_spec("AC", 2)],
    )

    def mutate(payload: dict) -> None:
        module = payload["modules"]["M03B"]
        rows = module["records_by_sku"]["AC000001"]
        conflict = copy.deepcopy(rows[0])
        conflict["record_id"] = f"{conflict['record_id']}-conflict"
        conflict["result_hash"] = "hash:m03b-conflict"
        conflict["facts"]["param_values_json"]["ac_product_form"][
            "normalized_value"
        ] = "floor_standing"
        rows.append(conflict)
        rows.sort(key=lambda row: (row["source_batch_id"], row["record_id"]))
        module["record_count"] += 1

    snapshot = _build(_rebuilt(bundle, mutate), "AC000001")
    assert snapshot.product_form_facts.ac_product_form is None
    assert "ac_product_form_conflict" in (
        snapshot.product_form_facts.unknown_reason_codes
    )
    m03_availability = next(
        row for row in snapshot.module_availability if row.module_code == "M03B"
    )
    assert m03_availability.availability == "conflict"
    assert m03_availability.review_required is True
    source_fact = next(
        row
        for row in snapshot.source_facts
        if row.source_atom == "M03B"
        and row.source_path
        == "facts.param_values_json.ac_product_form.normalized_value"
    )
    assert source_fact.support_status == "contradicted"
    assert source_fact.resolved_value is not None
    assert source_fact.resolved_value.presence == "conflict"
    assert source_fact.resolved_value.conflicting_values == [
        "floor_standing",
        "wall_mounted",
    ]


def test_outside_manifest_fails_without_creating_a_partial_snapshot() -> None:
    with pytest.raises(VersionSkuAnalysisSnapshotBuildError, match="outside"):
        _build(_category_bundle(), "TV999999")
