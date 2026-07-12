from decimal import Decimal

from app.services.core3_real_data.constants import (
    Core3CategoryCode,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DReasonEstablishmentStatus,
    M12DUserValidationStatus,
)
from app.services.core3_real_data.purchase_reason_establishment import (
    ReasonEstablishmentScorer,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DAnchorCandidateSet,
    M12DAnchorEvidenceMatch,
    M12DInputQuality,
    M12DInputQualityIssue,
    M12DInputSnapshot,
    M12DProfileScoreResult,
    M12DScoredPurchaseReasonAnchor,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    PurchaseReasonProfileScoringService,
    ReasonRoleClassifier,
)


def test_standard_9_establishes_tv_picture_reason_with_aligned_user_validation() -> (
    None
):
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary(
            "picture_screen_experience",
            positive=10,
            negative=2,
        ),
        market_summary={"price_band_size": "mid_high"},
    )

    result = _score(candidate, context, baseline_core_count=1)

    assert (
        result.establishment_status == M12DReasonEstablishmentStatus.ESTABLISHED.value
    )
    assert result.establishment_score == Decimal("9.0000")
    assert (
        result.user_validation_status == M12DUserValidationStatus.USER_VALIDATED.value
    )
    assert result.core_eligible is True
    assert result.role_reason_json["establishment_threshold_path"] == "standard_9"


def test_no_core_8_fallback_requires_baseline_without_core() -> None:
    candidate = _candidate(
        "TV",
        "gaming_device_fit_reduces_risk",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
            M12DEvidenceDomain.CLAIM_POSITION,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary("gaming_motion_experience", positive=4),
    )

    no_core = _score(candidate, context, baseline_core_count=0)
    has_core = _score(candidate, context, baseline_core_count=1)

    assert no_core.establishment_score == Decimal("8.0000")
    assert no_core.core_eligible is True
    assert no_core.role_reason_json["establishment_threshold_path"] == "no_core_8"
    assert (
        has_core.establishment_status
        == M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value
    )
    assert has_core.core_eligible is False
    assert "fallback_requires_baseline_no_core" in has_core.core_ineligible_reasons_json


def test_reason_specific_7_never_lowers_below_seven() -> None:
    candidate = _candidate(
        "TV",
        "sports_motion_stability",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary("gaming_motion_experience", positive=3),
    )

    result = _score(candidate, context, baseline_core_count=0)

    assert result.establishment_score == Decimal("7.0000")
    assert result.core_eligible is True
    assert (
        result.role_reason_json["establishment_threshold_path"] == "reason_specific_7"
    )


def test_below_7_is_rejected_even_when_positive_comment_exists() -> None:
    candidate = _candidate(
        "TV",
        "sports_motion_stability",
        [
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary("gaming_motion_experience", positive=3),
    )

    result = _score(candidate, context, baseline_core_count=0)

    assert result.establishment_score == Decimal("6.0000")
    assert result.establishment_status == M12DReasonEstablishmentStatus.REJECTED.value
    assert result.core_eligible is False
    assert "establishment_score_below_7" in result.core_ineligible_reasons_json


def test_tv_family_operation_with_only_product_and_scene_is_proposition() -> None:
    candidate = _candidate(
        "TV",
        "family_operation_less_friction",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )

    result = _score(candidate, _context("TV"), baseline_core_count=0)

    assert (
        result.establishment_status
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    )
    assert result.user_validation_status == M12DUserValidationStatus.NOT_OBSERVED.value
    assert result.core_eligible is False
    assert result.proposition_evidence_json
    assert result.user_support_evidence_json == []


def test_ordinary_negative_is_pressure_but_does_not_reduce_establishment_score() -> (
    None
):
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary(
            "picture_screen_experience",
            positive=8,
            negative=3,
        ),
        market_summary={"price_band_size": "high"},
    )
    legacy = _scored(candidate, adjusted_score="5.0000")

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
                input_fingerprint=context.input_fingerprint,
            )

    result = PurchaseReasonProfileScoringService(
        evidence_scorer=EvidenceScorer(),
        role_classifier=RoleClassifier(),
        profile_confidence_scorer=ProfileScorer(),
    ).score(
        candidate_set=M12DAnchorCandidateSet(
            taxonomy_version=candidate.taxonomy_version,
            product_category="TV",
            sku_code=candidate.sku_code,
            purchase_reason_candidates=[candidate],
        ),
        context=context,
    )
    anchor = result.scored_anchors[0]

    assert anchor.adjusted_evidence_score == Decimal("5.0000")
    assert anchor.establishment_score == Decimal("9.0000")
    assert anchor.core_eligible is True
    assert {tag.pressure_type for tag in anchor.pressure_tags_json} == {
        "localized_negative",
        "mixed_feedback",
    }


def test_established_high_pressure_reason_remains_core_payment() -> None:
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ],
    )
    anchor = _scored(candidate).model_copy(
        update={
            "establishment_status": M12DReasonEstablishmentStatus.ESTABLISHED,
            "establishment_score": Decimal("9.0000"),
            "user_validation_status": M12DUserValidationStatus.USER_VALIDATED,
            "core_eligible": True,
            "pressure_level": "high",
        }
    )

    classified = ReasonRoleClassifier().classify(anchor)

    assert classified.role == M12DAnchorRole.CORE_PAYMENT.value
    assert classified.role_reason_json["pressure_affects_role"] is False


def test_proposition_is_compat_supporting_but_not_user_reason() -> None:
    candidate = _candidate(
        "TV",
        "family_operation_less_friction",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    anchor = _scored(candidate).model_copy(
        update={
            "establishment_status": M12DReasonEstablishmentStatus.PROPOSITION_ONLY,
            "establishment_score": Decimal("7.0000"),
            "user_validation_status": M12DUserValidationStatus.NOT_OBSERVED,
            "core_eligible": False,
        }
    )

    classified = ReasonRoleClassifier().classify(anchor)

    assert classified.role == M12DAnchorRole.SUPPORTING.value
    assert classified.role_reason_json["semantic_role"] == "proposition"
    assert classified.downgrade_reason_code == "proposition_only_not_user_reason"


def test_comment_from_other_dimension_blocks_establishment() -> None:
    candidate = _candidate(
        "TV",
        "gaming_device_fit_reduces_risk",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
        ],
    )
    context = _context(
        "TV",
        comment_summary=_dimension_summary(
            "system_interaction_experience", positive=20
        ),
    )

    result = _score(candidate, context, baseline_core_count=0)

    assert result.establishment_status == M12DReasonEstablishmentStatus.REJECTED.value
    assert result.core_eligible is False
    assert M12DEvidenceDomain.COMMENT_PERCEPTION.value not in {
        str(domain) for domain in result.establishment_domains_json
    }
    assert "evidence_misalignment" in result.core_ineligible_reasons_json


def test_tv_big_screen_boundary_is_75_inches() -> None:
    candidate = _candidate(
        "TV",
        "big_screen_cinema_substitution",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    below = _score(
        candidate,
        _context("TV", market_summary={"screen_size_inch": 74}),
        baseline_core_count=0,
    )
    at_boundary = _score(
        candidate,
        _context("TV", market_summary={"screen_size_inch": 75}),
        baseline_core_count=0,
    )

    assert below.core_eligible is False
    assert "tv_big_screen_below_75_inch" in below.core_ineligible_reasons_json
    assert at_boundary.core_eligible is True
    assert (
        at_boundary.user_validation_status
        == M12DUserValidationStatus.MARKET_SUPPORTED.value
    )


def test_tv_low_price_market_supported_reason_requires_low_or_mid_low_band() -> None:
    candidate = _candidate(
        "TV",
        "low_price_core_experience_intact",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    low = _score(
        candidate,
        _context("TV", market_summary={"price_band_category": "low"}),
        baseline_core_count=0,
    )
    high = _score(
        candidate,
        _context("TV", market_summary={"price_band_category": "high"}),
        baseline_core_count=0,
    )

    assert low.establishment_score == Decimal("7.0000")
    assert low.core_eligible is True
    assert high.core_eligible is False
    assert "tv_low_price_band_mismatch" in high.core_ineligible_reasons_json


def test_subjective_tv_price_reason_cannot_use_market_without_positive_comment() -> (
    None
):
    candidate = _candidate(
        "TV",
        "picture_upgrade_justifies_price",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    result = _score(
        candidate,
        _context("TV", market_summary={"price_band_size": "high"}),
        baseline_core_count=0,
    )

    assert (
        result.establishment_status
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    )
    assert result.core_eligible is False


def test_ac_price_reason_accepts_only_same_reason_positive_m12c() -> None:
    candidate = _candidate(
        "AC",
        "long_term_energy_saving_offsets_price",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.CLAIM_VALUE,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    supported = _context(
        "AC",
        m12c_roles={
            candidate.anchor_code: {
                "ac_claim_energy_efficiency_apf": ["sales_driver_estimated"]
            }
        },
    )
    unrelated = _context(
        "AC",
        m12c_roles={
            candidate.anchor_code: {"ac_claim_fresh_air": ["sales_driver_estimated"]}
        },
    )

    supported_result = _score(candidate, supported, baseline_core_count=0)
    unrelated_result = _score(candidate, unrelated, baseline_core_count=0)

    assert supported_result.establishment_score == Decimal("8.0000")
    assert (
        supported_result.user_validation_status
        == M12DUserValidationStatus.USER_SUPPORTED.value
    )
    assert supported_result.core_eligible is True
    assert (
        unrelated_result.establishment_status
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    )
    assert unrelated_result.core_eligible is False


def test_ac_function_reason_without_positive_comment_stays_proposition() -> None:
    candidate = _candidate(
        "AC",
        "self_cleaning_reduces_maintenance_risk",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )

    result = _score(candidate, _context("AC"), baseline_core_count=0)

    assert (
        result.establishment_status
        == M12DReasonEstablishmentStatus.PROPOSITION_ONLY.value
    )
    assert result.core_eligible is False


def test_ac_function_reason_with_aligned_comment_can_use_7_point_path() -> None:
    candidate = _candidate(
        "AC",
        "self_cleaning_reduces_maintenance_risk",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.COMMENT_PERCEPTION,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    context = _context(
        "AC",
        comment_records=[
            _comment_record(
                "ac-comment-1",
                "health_clean_air_experience",
                "self_cleaning",
                "positive",
            )
        ],
        comment_summary=_dimension_summary(
            "health_clean_air_experience",
            positive=10,
            subdimensions=["self_cleaning", "fresh_air"],
        ),
    )

    result = _score(candidate, context, baseline_core_count=0)

    assert result.establishment_score == Decimal("7.0000")
    assert result.core_eligible is True
    assert result.user_support_evidence_json[0].record_id == "ac-comment-1"


def test_objective_falsification_rejects_otherwise_valid_reason() -> None:
    candidate = _candidate(
        "AC",
        "room_size_capacity_match_reduces_risk",
        [
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.MARKET_ACCEPTANCE,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
    )
    context = _context(
        "AC",
        market_summary={"market_pool_code": "ac-wall-1p-low"},
        qualities={
            "M03B": _quality(
                "M03B",
                [
                    M12DInputQualityIssue(
                        code="m03b_true_param_conflict",
                        severity=M12DIssueSeverity.BLOCKING,
                        scope=M12DIssueScope.ANCHOR,
                        affected_anchor_codes=[candidate.anchor_code],
                    )
                ],
            )
        },
    )

    result = _score(candidate, context, baseline_core_count=0)

    assert result.establishment_status == M12DReasonEstablishmentStatus.REJECTED.value
    assert result.core_eligible is False
    assert "objective_falsification" in result.core_ineligible_reasons_json


def test_profile_summary_keeps_established_and_proposition_separate() -> None:
    candidate = _candidate("TV", "reason_a", [])
    established = _scored(candidate).model_copy(
        update={
            "establishment_status": M12DReasonEstablishmentStatus.ESTABLISHED,
            "core_eligible": True,
        }
    )
    proposition = _scored(candidate).model_copy(
        update={
            "anchor_code": "reason_b",
            "establishment_status": M12DReasonEstablishmentStatus.PROPOSITION_ONLY,
            "core_eligible": False,
        }
    )
    profile = M12DProfileScoreResult(
        taxonomy_version="tv-taxonomy-v1",
        product_category="TV",
        sku_code="TV001",
        status=M12DProfileStatus.READY,
        scored_anchors=[established, proposition],
        input_fingerprint="profile-fp",
    )

    result = ReasonEstablishmentScorer().summarize_profile(profile)

    assert result.established_anchors_json == ["reason_a"]
    assert result.proposition_anchors_json == ["reason_b"]


def _score(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
    *,
    baseline_core_count: int,
) -> M12DScoredPurchaseReasonAnchor:
    return ReasonEstablishmentScorer().score(
        candidate=candidate,
        context=context,
        scored_anchor=_scored(candidate),
        baseline_core_count=baseline_core_count,
    )


def _candidate(
    category: str,
    anchor_code: str,
    domains: list[M12DEvidenceDomain],
) -> M12DAnchorCandidate:
    matches = []
    for index, domain in enumerate(domains):
        module = {
            M12DEvidenceDomain.PARAM_FACT: "M03B",
            M12DEvidenceDomain.FACT_CLAIM: "M04C",
            M12DEvidenceDomain.COMMENT_PERCEPTION: "M05C",
            M12DEvidenceDomain.SEMANTIC_SCENE: "M09C_M10C_M11C",
            M12DEvidenceDomain.MARKET_ACCEPTANCE: "M07",
            M12DEvidenceDomain.CLAIM_VALUE: "M12C",
            M12DEvidenceDomain.CLAIM_POSITION: "M04C",
        }.get(domain, "M04C")
        matches.append(
            M12DAnchorEvidenceMatch(
                module_code=module,
                evidence_domain=domain,
                match_source="summary",
                match_key=f"{domain.value}-{index}",
                match_value=f"{domain.value}-{index}",
                support_label_cn=f"{domain.value} 证据",
                source_refs_json=[
                    M12DSourceRef(
                        module_code=module,
                        table_name=f"source_{module.lower()}",
                        record_id=f"{category}-{anchor_code}-{domain.value}-{index}",
                    )
                ],
            )
        )
    return M12DAnchorCandidate(
        taxonomy_version=f"{category.lower()}-taxonomy-v1",
        product_category=category,
        sku_code=f"{category}001",
        anchor_code=anchor_code,
        anchor_cn=anchor_code,
        anchor_family_code="family-a",
        anchor_family_cn="理由族A",
        candidate_rank=1,
        evidence_matches=matches,
        evidence_domains_json=domains,
        support_summary_cn="候选正向证据。",
        source_refs_json=[ref for match in matches for ref in match.source_refs_json],
        input_fingerprint=f"candidate-{category}-{anchor_code}",
    )


def _scored(
    candidate: M12DAnchorCandidate,
    *,
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
        role=M12DAnchorRole.SUPPORTING,
        evidence_strength=M12DEvidenceStrength.MEDIUM,
        confidence=Decimal("0.7000"),
        raw_evidence_score=Decimal("9.0000"),
        adjusted_evidence_score=Decimal(adjusted_score),
        evidence_domains_json=candidate.evidence_domains_json,
        support_summary_cn="现有评分。",
        source_refs_json=candidate.source_refs_json,
        input_fingerprint=candidate.input_fingerprint,
    )


def _context(
    category: str,
    *,
    comment_summary: dict | None = None,
    comment_records: list[dict] | None = None,
    market_summary: dict | None = None,
    m12c_roles: dict | None = None,
    qualities: dict[str, M12DInputQuality] | None = None,
) -> M12DSkuPurchaseReasonContext:
    comment_records = comment_records or []
    m12c_roles = m12c_roles or {}
    role_evidence = {}
    m12c_records = []
    for claim_roles in m12c_roles.values():
        for claim_code, roles in claim_roles.items():
            for index, role in enumerate(roles):
                record = {
                    "table_name": "core3_sku_claim_value_quantification",
                    "record_id": f"m12c-{claim_code}-{role}-{index}",
                    "claim_code": claim_code,
                    "claim_value_role": role,
                    "reason_cn": "测试 M12C 正向价值。",
                    "result_hash": f"hash-{claim_code}-{role}-{index}",
                }
                m12c_records.append(record)
                role_evidence.setdefault(claim_code, {}).setdefault(role, []).append(
                    record
                )
    snapshots = {
        module: M12DInputSnapshot(module_code=module, status=M12DInputStatus.READY)
        for module in ("M03B", "M04C", "M05C", "M07", "M09C_M10C_M11C", "M11D", "M12C")
    }
    snapshots["M05C"] = M12DInputSnapshot(
        module_code="M05C",
        status=M12DInputStatus.READY,
        record_count=len(comment_records),
        records=comment_records,
        summary={"dimension_summary_json": comment_summary or {}},
        source_refs=[
            M12DSourceRef(
                module_code="M05C",
                table_name="core3_sku_comment_fact_profile",
                record_id=f"comment-profile-{category}",
            )
        ],
    )
    snapshots["M07"] = M12DInputSnapshot(
        module_code="M07",
        status=M12DInputStatus.READY,
        summary=market_summary or {},
    )
    snapshots["M12C"] = M12DInputSnapshot(
        module_code="M12C",
        status=M12DInputStatus.READY,
        record_count=len(m12c_records),
        records=m12c_records,
        summary={
            "anchor_claim_value_roles": m12c_roles,
            "claim_value_role_evidence": role_evidence,
        },
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


def _dimension_summary(
    dimension_code: str,
    *,
    positive: int,
    negative: int = 0,
    mixed: int = 0,
    subdimensions: list[str] | None = None,
) -> dict:
    return {
        dimension_code: {
            "fact_atom_count": positive + negative + mixed,
            "polarity_counts": {
                "positive": positive,
                "negative": negative,
                "mixed": mixed,
                "neutral": 0,
            },
            "subdimension_codes": subdimensions or [f"{dimension_code}_detail"],
            "examples": [
                {
                    "comment_text": "正向评论",
                    "polarity": "positive",
                    "subdimension_code": (
                        subdimensions or [f"{dimension_code}_detail"]
                    )[0],
                    "evidence_ids": [f"evidence-{dimension_code}"],
                }
            ],
        }
    }


def _comment_record(
    record_id: str,
    dimension_code: str,
    subdimension_code: str,
    polarity: str,
) -> dict:
    return {
        "table_name": "core3_comment_fact_atom",
        "record_id": record_id,
        "dimension_code": dimension_code,
        "subdimension_code": subdimension_code,
        "polarity": polarity,
        "raw_comment_text": "真实评论样例",
        "result_hash": f"hash-{record_id}",
    }


def _quality(module_code: str, issues: list[M12DInputQualityIssue]) -> M12DInputQuality:
    return M12DInputQuality(
        module_code=module_code,
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED,
        issues=issues,
    )
