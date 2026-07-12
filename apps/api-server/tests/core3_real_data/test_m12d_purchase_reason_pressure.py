from decimal import Decimal

from app.services.core3_real_data.constants import (
    Core3CategoryCode,
    Core3ConfidenceLevel,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DPurchasePressureLevel,
)
from app.services.core3_real_data.purchase_reason_pressure import (
    PurchasePressureClassifier,
    _dedupe_source_refs,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DAnchorCandidateSet,
    M12DInputQuality,
    M12DInputQualityIssue,
    M12DInputSnapshot,
    M12DProfileScoreResult,
    M12DPurchasePressureTag,
    M12DScoredPurchaseReasonAnchor,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    PurchaseReasonProfileScoringService,
)


def test_pressure_source_refs_are_canonical_across_input_orders() -> None:
    first = M12DSourceRef(
        module_code="M12C",
        table_name="core3_sku_claim_value_quantification",
        record_id="record-a",
    )
    second = M12DSourceRef(
        module_code="M12C",
        table_name="core3_sku_claim_value_quantification",
        record_id="record-b",
    )

    forward = _dedupe_source_refs([second, first, second])
    reverse = _dedupe_source_refs([first, second, first])

    assert [ref.record_id for ref in forward] == ["record-a", "record-b"]
    assert [ref.record_id for ref in reverse] == ["record-a", "record-b"]


def test_comment_localized_negative_and_mixed_feedback_are_parallel_pressure() -> None:
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    records = [
        _comment_record(index, "picture_screen_experience", "picture_clarity_resolution", "positive")
        for index in range(8)
    ] + [
        _comment_record(9, "picture_screen_experience", "picture_clarity_resolution", "negative")
    ]
    context = _context("TV", comment_records=records, expected_comment_count=len(records))
    scored = _scored(candidate, role=M12DAnchorRole.CORE_PAYMENT, adjusted_score="7.0000")

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=scored,
    )

    assert {tag.pressure_type for tag in result.pressure_tags_json} == {
        "localized_negative",
        "mixed_feedback",
    }
    assert result.pressure_level == M12DPurchasePressureLevel.MEDIUM.value
    assert all(tag.limits_establishment is False for tag in result.pressure_tags_json)
    assert result.role == M12DAnchorRole.CORE_PAYMENT.value
    assert result.adjusted_evidence_score == Decimal("7.0000")
    assert result.establishment_score is None


def test_negative_dominant_is_high_pressure_but_does_not_delete_ac_reason() -> None:
    candidate = _candidate(
        "AC",
        "sleep_room_quiet_comfort_assurance",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    records = [
        _comment_record(1, "noise_sleep_experience", "noise_risk", "positive"),
        _comment_record(2, "noise_sleep_experience", "noise_risk", "negative"),
        _comment_record(3, "noise_sleep_experience", "noise_risk", "negative"),
        _comment_record(4, "noise_sleep_experience", "noise_risk", "negative"),
    ]
    context = _context("AC", comment_records=records, expected_comment_count=4)
    scored = _scored(candidate, role=M12DAnchorRole.SUPPORTING, adjusted_score="6.0000")

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=scored,
    )

    dominant = next(tag for tag in result.pressure_tags_json if tag.pressure_type == "negative_dominant")
    assert result.pressure_level == M12DPurchasePressureLevel.HIGH.value
    assert dominant.negative_count == 3
    assert dominant.limits_establishment is False
    assert result.role == M12DAnchorRole.SUPPORTING.value
    assert result.adjusted_evidence_score == Decimal("6.0000")


def test_unreferenced_comment_dimension_does_not_spread_to_anchor() -> None:
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        domains=[M12DEvidenceDomain.PARAM_FACT],
    )
    context = _context(
        "TV",
        comment_records=[
            _comment_record(1, "system_interaction_experience", "system_smooth_ads", "negative")
        ],
        expected_comment_count=1,
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert result.pressure_level == M12DPurchasePressureLevel.NONE.value
    assert result.pressure_tags_json == []


def test_complete_cross_dimension_comment_evidence_is_misalignment_not_negative_pressure() -> None:
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    context = _context(
        "TV",
        comment_records=[
            _comment_record(1, "system_interaction_experience", "system_smooth_ads", "negative")
        ],
        expected_comment_count=1,
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert [tag.pressure_type for tag in result.pressure_tags_json] == ["evidence_misalignment"]
    assert result.pressure_tags_json[0].limits_establishment is True
    assert result.pressure_level == M12DPurchasePressureLevel.CRITICAL.value


def test_partial_comment_expansion_limits_comparison_without_false_misalignment() -> None:
    candidate = _candidate(
        "AC",
        "smart_remote_control_less_friction",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    context = _context(
        "AC",
        comment_records=[
            _comment_record(1, "temperature_effect_experience", "cooling_effect", "positive")
        ],
        expected_comment_count=20,
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert result.pressure_tags_json == []
    assert result.pressure_level == M12DPurchasePressureLevel.NONE.value
    assert [item.limitation_code for item in result.comparison_limitations_json] == [
        "comment_alignment_not_fully_expanded"
    ]


def test_full_dimension_distribution_drives_pressure_instead_of_expanded_sample() -> None:
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    context = _context(
        "TV",
        comment_records=[
            _comment_record(index, "picture_screen_experience", "picture_clarity", "positive")
            for index in range(5)
        ],
        expected_comment_count=100,
        comment_dimension_summary={
            "picture_screen_experience": {
                "fact_atom_count": 100,
                "polarity_counts": {
                    "positive": 80,
                    "negative": 20,
                    "mixed": 0,
                    "neutral": 0,
                },
                "subdimension_codes": ["picture_clarity"],
                "examples": [
                    {
                        "comment_text": "清晰度不错",
                        "polarity": "positive",
                        "subdimension_code": "picture_clarity",
                        "evidence_ids": ["evidence-1"],
                    }
                ],
            }
        },
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    localized = next(tag for tag in result.pressure_tags_json if tag.pressure_type == "localized_negative")
    assert localized.positive_count == 80
    assert localized.negative_count == 20
    assert any(ref.table_name == "core3_sku_comment_fact_profile" for ref in localized.source_refs)
    profile_ref = next(ref for ref in localized.source_refs if ref.table_name == "core3_sku_comment_fact_profile")
    assert profile_ref.extra["polarity_counts"]["negative"] == 20
    assert profile_ref.extra["comment_examples"][0]["evidence_ids"] == ["evidence-1"]


def test_complete_dimension_inventory_can_prove_comment_misalignment() -> None:
    candidate = _candidate(
        "AC",
        "smart_remote_control_less_friction",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    context = _context(
        "AC",
        comment_records=[],
        expected_comment_count=40,
        comment_dimension_summary={
            "temperature_effect_experience": {
                "fact_atom_count": 40,
                "polarity_counts": {"positive": 35, "negative": 5},
                "subdimension_codes": ["cooling_effect"],
            }
        },
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert [tag.pressure_type for tag in result.pressure_tags_json] == ["evidence_misalignment"]
    assert result.pressure_tags_json[0].limits_establishment is True


def test_partial_subdimension_distribution_is_not_inferred_from_dimension_total() -> None:
    candidate = _candidate(
        "TV",
        "family_long_watch_comfort_assurance",
        domains=[M12DEvidenceDomain.COMMENT_PERCEPTION],
    )
    context = _context(
        "TV",
        comment_records=[
            _comment_record(
                1,
                "picture_screen_experience",
                "picture_eye_care_reflection",
                "positive",
            )
        ],
        expected_comment_count=100,
        comment_dimension_summary={
            "picture_screen_experience": {
                "fact_atom_count": 100,
                "polarity_counts": {"positive": 60, "negative": 40},
                "subdimension_codes": [
                    "picture_eye_care_reflection",
                    "picture_clarity",
                ],
            }
        },
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert result.pressure_tags_json == []
    assert [item.limitation_code for item in result.comparison_limitations_json] == [
        "comment_subdimension_distribution_unavailable"
    ]


def test_m12c_headwind_is_scoped_to_matching_anchor_and_claim() -> None:
    reason_a = _candidate("TV", "picture_upgrade_justifies_price")
    reason_b = _candidate("TV", "family_operation_less_friction")
    quality = _quality(
        "M12C",
        [
            _issue(
                "m12c_related_claim_negative",
                [reason_a.anchor_code],
                source_table="core3_sku_claim_value_quantification",
                source_id="m12c-a",
                details={"claim_codes": ["tv_claim_miniled_display"]},
            )
        ],
    )
    context = _context(
        "TV",
        qualities={"M12C": quality},
        claim_value_summary={
            "anchor_claim_value_roles": {
                reason_a.anchor_code: {
                    "tv_claim_miniled_display": ["sales_driver_estimated", "drag_factor"]
                },
                reason_b.anchor_code: {
                    "tv_claim_voice_control": ["sales_driver_estimated"]
                },
            }
        },
        claim_value_records=[
            _claim_value_record("tv_claim_miniled_display", "drag_factor"),
            _claim_value_record("tv_claim_voice_control", "sales_driver_estimated"),
        ],
    )

    result_a = PurchasePressureClassifier().classify(
        candidate=reason_a,
        context=context,
        scored_anchor=_scored(reason_a),
    )
    result_b = PurchasePressureClassifier().classify(
        candidate=reason_b,
        context=context,
        scored_anchor=_scored(reason_b),
    )

    assert [tag.pressure_type for tag in result_a.pressure_tags_json] == ["m12c_value_headwind"]
    assert result_a.pressure_level == M12DPurchasePressureLevel.HIGH.value
    assert result_b.pressure_tags_json == []
    assert {ref.record_id for ref in result_a.pressure_tags_json[0].source_refs} == {
        "m12c-a",
        "claim-tv_claim_miniled_display-drag_factor",
    }


def test_m12c_generic_anchor_role_does_not_spread_unrelated_claim_pressure() -> None:
    candidate = _candidate("AC", "room_size_capacity_match_reduces_risk")
    context = _context(
        "AC",
        claim_value_summary={
            "anchor_claim_value_roles": {
                candidate.anchor_code: {
                    "ac_claim_energy_efficiency_apf": ["high_price_competitor_intercept"],
                    "ac_claim_fast_cooling_heating": ["sales_driver_estimated"],
                }
            }
        },
        claim_value_records=[
            _claim_value_record(
                "ac_claim_energy_efficiency_apf",
                "high_price_competitor_intercept",
            ),
            _claim_value_record("ac_claim_fast_cooling_heating", "sales_driver_estimated"),
        ],
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert result.pressure_tags_json == []


def test_m12c_opportunity_gap_is_not_treated_as_current_purchase_pressure() -> None:
    candidate = _candidate("TV", "picture_upgrade_justifies_price")
    context = _context(
        "TV",
        claim_value_summary={
            "anchor_claim_value_roles": {
                candidate.anchor_code: {
                    "tv_claim_miniled_display": ["opportunity_gap"]
                }
            }
        },
        claim_value_records=[
            _claim_value_record("tv_claim_miniled_display", "opportunity_gap")
        ],
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    assert result.pressure_tags_json == []


def test_m12c_full_role_summary_keeps_trace_when_detail_row_is_not_expanded() -> None:
    candidate = _candidate("TV", "picture_upgrade_justifies_price")
    context = _context(
        "TV",
        claim_value_summary={
            "anchor_claim_value_roles": {
                candidate.anchor_code: {
                    "tv_claim_miniled_display": ["weak_user_perception_claim"]
                }
            },
            "claim_value_role_evidence": {
                "tv_claim_miniled_display": {
                    "weak_user_perception_claim": [
                        {
                            "table_name": "core3_sku_claim_value_quantification",
                            "record_id": "full-m12c-row-1",
                            "result_hash": "full-m12c-hash-1",
                            "evidence_ids": ["m12c-evidence-1"],
                            "reason_cn": "用户感知承接较弱。",
                        }
                    ]
                }
            },
        },
        claim_value_records=[],
    )

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    tag = result.pressure_tags_json[0]
    assert tag.pressure_type == "m12c_value_headwind"
    assert [ref.record_id for ref in tag.source_refs] == ["full-m12c-row-1"]
    assert tag.source_refs[0].extra["claim_code"] == "tv_claim_miniled_display"


def test_market_uncertainty_only_applies_to_market_using_anchor() -> None:
    market_reason = _candidate(
        "TV",
        "same_price_core_config_gain",
        domains=[M12DEvidenceDomain.MARKET_ACCEPTANCE],
    )
    non_market_reason = _candidate(
        "TV",
        "family_operation_less_friction",
        domains=[M12DEvidenceDomain.PARAM_FACT],
    )
    market_quality = _quality(
        "M07",
        [
            _issue(
                "size_pool_limited",
                [market_reason.anchor_code, non_market_reason.anchor_code],
                source_table="core3_sku_market_profile",
                source_id="market-1",
            )
        ],
    )
    context = _context("TV", qualities={"M07": market_quality})

    market_result = PurchasePressureClassifier().classify(
        candidate=market_reason,
        context=context,
        scored_anchor=_scored(market_reason),
    )
    non_market_result = PurchasePressureClassifier().classify(
        candidate=non_market_reason,
        context=context,
        scored_anchor=_scored(non_market_reason),
    )

    assert [tag.pressure_type for tag in market_result.pressure_tags_json] == ["market_uncertainty"]
    assert market_result.pressure_tags_json[0].limits_comparison is True
    assert market_result.comparison_limitations_json[0].scope == "market"
    assert non_market_result.pressure_tags_json == []


def test_objective_falsification_is_the_only_pressure_that_blocks_establishment_here() -> None:
    candidate = _candidate("AC", "room_size_capacity_match_reduces_risk")
    quality = _quality(
        "M03B",
        [
            _issue(
                "m03b_true_param_conflict",
                [candidate.anchor_code],
                severity=M12DIssueSeverity.BLOCKING,
                source_table="core3_sku_param_profile",
                source_id="param-1",
            )
        ],
    )
    context = _context("AC", qualities={"M03B": quality})

    result = PurchasePressureClassifier().classify(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
    )

    tag = result.pressure_tags_json[0]
    assert tag.pressure_type == "objective_falsification"
    assert tag.pressure_level == M12DPurchasePressureLevel.CRITICAL.value
    assert tag.limits_establishment is True


def test_profile_pressure_summary_aggregates_without_changing_profile_decision() -> None:
    candidate = _candidate("TV", "picture_upgrade_justifies_price")
    clean = _scored(candidate).model_copy(update={"pressure_level": "none"})
    pressured = _scored(candidate).model_copy(
        update={
            "anchor_code": "reason_b",
            "pressure_level": "high",
            "pressure_tags_json": [
                M12DPurchasePressureTag(
                    pressure_type="negative_dominant",
                    pressure_level="high",
                    affected_anchor_code="reason_b",
                )
            ],
        }
    )
    base = M12DProfileScoreResult(
        taxonomy_version="taxonomy-v1",
        product_category="TV",
        sku_code="TV001",
        status=M12DProfileStatus.READY,
        profile_confidence=Decimal("0.8000"),
        confidence_level=Core3ConfidenceLevel.HIGH,
        scored_anchors=[clean, pressured],
        core_payment_anchors_json=[candidate.anchor_code],
        input_fingerprint="profile-fp",
    )

    result = PurchasePressureClassifier().summarize_profile(base)

    assert result.status == M12DProfileStatus.READY.value
    assert result.profile_confidence == Decimal("0.8000")
    assert result.core_payment_anchors_json == [candidate.anchor_code]
    assert result.pressure_summary_json["highest_pressure_level"] == "high"
    assert result.pressure_summary_json["pressured_anchor_codes"] == ["reason_b"]


def test_scoring_service_attaches_pressure_without_pressure_classifier_changing_legacy_score() -> None:
    candidate = _candidate("TV", "picture_upgrade_justifies_price")
    context = _context("TV")
    legacy = _scored(candidate, adjusted_score="8.0000")

    class EvidenceScorer:
        def score(self, _candidate, _context):
            return legacy

    class RoleClassifier:
        def classify(self, anchor):
            return anchor

    class ProfileScorer:
        def score(self, *, candidate_set, context, scored_anchors):
            return M12DProfileScoreResult(
                taxonomy_version=candidate_set.taxonomy_version,
                product_category=context.product_category,
                sku_code=context.sku_code,
                status=M12DProfileStatus.READY,
                scored_anchors=list(scored_anchors),
                core_payment_anchors_json=[candidate.anchor_code],
                input_fingerprint=context.input_fingerprint,
            )

    result = PurchaseReasonProfileScoringService(
        evidence_scorer=EvidenceScorer(),
        role_classifier=RoleClassifier(),
        profile_confidence_scorer=ProfileScorer(),
    ).score(
        candidate_set=M12DAnchorCandidateSet(
            taxonomy_version="taxonomy-v1",
            product_category="TV",
            sku_code="TV001",
            purchase_reason_candidates=[candidate],
        ),
        context=context,
    )

    assert result.scored_anchors[0].adjusted_evidence_score == Decimal("8.0000")
    assert result.scored_anchors[0].role == M12DAnchorRole.CORE_PAYMENT.value
    assert result.scored_anchors[0].pressure_level == M12DPurchasePressureLevel.NONE.value


def _candidate(
    category: str,
    anchor_code: str,
    *,
    domains: list[M12DEvidenceDomain] | None = None,
) -> M12DAnchorCandidate:
    return M12DAnchorCandidate(
        taxonomy_version=f"{category.lower()}-taxonomy-v1",
        product_category=category,
        sku_code=f"{category}001",
        anchor_code=anchor_code,
        anchor_cn=anchor_code,
        anchor_family_code="family-a",
        anchor_family_cn="理由族A",
        candidate_rank=1,
        evidence_domains_json=domains or [],
        support_summary_cn="候选证据。",
        input_fingerprint=f"candidate-{category}-{anchor_code}",
    )


def _scored(
    candidate: M12DAnchorCandidate,
    *,
    role: M12DAnchorRole = M12DAnchorRole.CORE_PAYMENT,
    adjusted_score: str = "9.0000",
) -> M12DScoredPurchaseReasonAnchor:
    return M12DScoredPurchaseReasonAnchor(
        taxonomy_version=candidate.taxonomy_version,
        product_category=candidate.product_category,
        sku_code=candidate.sku_code,
        anchor_code=candidate.anchor_code,
        anchor_cn=candidate.anchor_cn,
        anchor_family_code=candidate.anchor_family_code,
        anchor_family_cn=candidate.anchor_family_cn,
        anchor_rank=candidate.candidate_rank,
        role=role,
        evidence_strength=M12DEvidenceStrength.STRONG,
        confidence=Decimal("0.8000"),
        raw_evidence_score=Decimal("9.0000"),
        conflict_penalty=Decimal("2.0000"),
        adjusted_evidence_score=Decimal(adjusted_score),
        evidence_domains_json=candidate.evidence_domains_json,
        support_summary_cn="现有评分结果。",
        input_fingerprint=candidate.input_fingerprint,
    )


def _context(
    category: str,
    *,
    comment_records: list[dict] | None = None,
    expected_comment_count: int = 0,
    comment_dimension_summary: dict | None = None,
    qualities: dict[str, M12DInputQuality] | None = None,
    claim_value_summary: dict | None = None,
    claim_value_records: list[dict] | None = None,
) -> M12DSkuPurchaseReasonContext:
    comment_records = comment_records or []
    snapshots = {
        module: M12DInputSnapshot(module_code=module, status=M12DInputStatus.READY)
        for module in ("M03B", "M04C", "M05C", "M07", "M09C_M10C_M11C", "M11D", "M12C")
    }
    snapshots["M05C"] = M12DInputSnapshot(
        module_code="M05C",
        status=M12DInputStatus.READY,
        record_count=len(comment_records),
        records=comment_records,
        summary={
            "fact_atom_count": expected_comment_count,
            "comment_fact_count": len(comment_records),
            "dimension_summary_json": comment_dimension_summary or {},
        },
        source_refs=[
            M12DSourceRef(
                module_code="M05C",
                table_name="core3_sku_comment_fact_profile",
                record_id=f"comment-profile-{category}",
                result_hash=f"comment-profile-hash-{category}",
            )
        ],
    )
    snapshots["M12C"] = M12DInputSnapshot(
        module_code="M12C",
        status=M12DInputStatus.READY,
        record_count=len(claim_value_records or []),
        records=claim_value_records or [],
        summary=claim_value_summary or {},
    )
    return M12DSkuPurchaseReasonContext(
        project_id="project-1",
        category_code=Core3CategoryCode(category),
        batch_id="batch-1",
        product_category=category,
        sku_code=f"{category}001",
        display_name_cn=f"{category} test",
        param_profile=snapshots["M03B"],
        claim_fact_profile=snapshots["M04C"],
        comment_profile=snapshots["M05C"],
        market_profile=snapshots["M07"],
        semantic_profile=snapshots["M09C_M10C_M11C"],
        semantic_market_profile=snapshots["M11D"],
        claim_value_profile=snapshots["M12C"],
        input_quality_json=qualities or {},
        input_fingerprint=f"context-{category}",
    )


def _comment_record(
    index: int,
    dimension_code: str,
    subdimension_code: str,
    polarity: str,
) -> dict:
    return {
        "table_name": "core3_comment_fact_atom",
        "record_id": f"comment-{index}",
        "dimension_code": dimension_code,
        "subdimension_code": subdimension_code,
        "polarity": polarity,
        "raw_comment_text": f"评论 {index}",
        "result_hash": f"comment-hash-{index}",
    }


def _claim_value_record(claim_code: str, role: str) -> dict:
    return {
        "table_name": "core3_sku_claim_value_quantification",
        "record_id": f"claim-{claim_code}-{role}",
        "claim_code": claim_code,
        "claim_value_role": role,
        "reason_cn": "测试卖点价值角色。",
        "result_hash": f"hash-{claim_code}-{role}",
    }


def _quality(module_code: str, issues: list[M12DInputQualityIssue]) -> M12DInputQuality:
    return M12DInputQuality(
        module_code=module_code,
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED if issues else M12DInputUsability.USABLE,
        issues=issues,
    )


def _issue(
    code: str,
    anchors: list[str],
    *,
    severity: M12DIssueSeverity = M12DIssueSeverity.WARNING,
    source_table: str,
    source_id: str,
    details: dict | None = None,
) -> M12DInputQualityIssue:
    return M12DInputQualityIssue(
        code=code,
        severity=severity,
        scope=M12DIssueScope.ANCHOR,
        affected_anchor_codes=anchors,
        source_refs=[{"table_name": source_table, "record_id": source_id}],
        details_json=details or {},
    )
