from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfilePersistenceBundle,
    CompetitorProfileReadBundle,
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
    SkuCompetitorPairDraft,
    SkuCompetitorProfileDraft,
    SkuCompetitorRelationDraft,
    SkuCompetitorSelectionDraft,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    ALL_EVIDENCE_FAMILIES,
    ALL_QUESTION_CODES,
    ALL_RELATION_CODES,
    CandidateIdentity,
    CompetitorPairDraft,
    CompetitorProfileDraftBundle,
    EvidenceFamilyAssessment,
    EvidenceRef,
    GateResult,
    KeyCompetitorSelectionDraft,
    KeyCompetitorSummary,
    PairMarketComparison,
    PurchasePoolAssessment,
    QuestionEligibility,
    RelationAssessment,
    ServingScope,
    SkuCompetitorDecisionProfileDraft,
    SourceAuthorityRef,
)


def _authority(
    *,
    module_code: str = "M07",
    category_code: str = "TV",
    source_batch_ids: list[str] | None = None,
    release_status: str = "published",
) -> SourceAuthorityRef:
    batches = source_batch_ids or ["batch-1", "batch-2"]
    return SourceAuthorityRef(
        module_code=module_code,
        project_id=f"project-{category_code.lower()}",
        category_code=category_code,
        product_category=category_code,
        profile_version=f"{module_code.lower()}-{category_code.lower()}-v1",
        schema_version="schema-v1",
        rule_version=f"{module_code.lower()}-{category_code.lower()}-rule-v1",
        taxonomy_version=f"taxonomy-{category_code.lower()}-v1",
        release_status=release_status,
        is_current=release_status == "published",
        source_batch_ids=batches,
        result_hash=f"{module_code.lower()}-result",
    )


def _scope(category_code: str = "TV") -> ServingScope:
    batches = ["batch-1", "batch-2"] if category_code == "TV" else ["batch-ac"]
    authorities = {
        code: _authority(
            module_code=code,
            category_code=category_code,
            source_batch_ids=batches,
        )
        for code in ("M03B", "M07", "M12D")
    }
    return ServingScope(
        project_id=f"project-{category_code.lower()}",
        category_code=category_code,
        product_category=category_code,
        analysis_population="full_window",
        market_window="2025-W01_2025-W52",
        taxonomy_version=f"taxonomy-{category_code.lower()}-v1",
        storage_batch_id=batches[-1],
        source_batch_ids=batches,
        source_authorities=authorities,
        sku_prefixes=[category_code],
        authoritative_sku_count=377 if category_code == "TV" else 155,
        authoritative_sku_manifest_hash=f"manifest-{category_code.lower()}",
        release_scope_key=f"scope-{category_code.lower()}",
    )


def _evidence(module_code: str = "M12D") -> EvidenceRef:
    return EvidenceRef(
        module_code=module_code,
        profile_version=f"{module_code.lower()}-v1",
        rule_version=f"{module_code.lower()}-rule-v1",
        taxonomy_version="taxonomy-tv-v1",
        record_type="profile",
        record_id=f"record-{module_code.lower()}",
        result_hash=f"hash-{module_code.lower()}",
        source_batch_id="batch-1",
        evidence_ids=[f"evidence-{module_code.lower()}"],
        confidence=Decimal("0.85"),
    )


def _gate(
    code: str = "category_compatible",
    *,
    required: bool = True,
    known: bool = True,
    passed: bool | None = True,
) -> GateResult:
    return GateResult(
        gate_code=code,
        required=required,
        known=known,
        passed=passed,
        reason_code="gate_passed" if passed else "gate_not_passed",
        evidence_refs=[_evidence("M03B")],
    )


def _pool(*, unknown: bool = False) -> PurchasePoolAssessment:
    gates = [
        _gate("category_compatible"),
        _gate("budget_reachable"),
        _gate(
            "task_overlap",
            known=not unknown,
            passed=None if unknown else True,
        ),
    ]
    return PurchasePoolAssessment(
        level="unknown" if unknown else "P0",
        gate_results=gates,
        confidence_level="unknown" if unknown else "high",
        evidence_refs=[_evidence()],
        limitations=["task_unknown"] if unknown else [],
        result_hash="pool-hash",
    )


def _families() -> list[EvidenceFamilyAssessment]:
    rows = []
    for family in sorted(ALL_EVIDENCE_FAMILIES):
        status = "discriminative" if family in {
            "F1_purchase_reason",
            "F2_task_value_scene",
            "F4_user_realization",
        } else "supporting"
        rows.append(
            EvidenceFamilyAssessment(
                family=family,
                status=status,
                matched_codes=[f"value-{family}"],
                target_strength=Decimal("0.80"),
                candidate_strength=Decimal("0.75"),
                direction="target_stronger",
                independent_lineage_keys=[f"lineage-{family}"],
                evidence_refs=[_evidence()],
                confidence_level="high",
            )
        )
    return rows


def _market() -> PairMarketComparison:
    return PairMarketComparison(
        source_authority=_authority(module_code="M07"),
        analysis_population="full_window",
        market_window="2025-W01_2025-W52",
        comparability_status="comparable",
        target_weighted_price=Decimal("5000"),
        candidate_weighted_price=Decimal("4600"),
        price_gap=Decimal("-400"),
        price_gap_pct=Decimal("-0.08"),
        target_avg_weekly_volume=Decimal("100"),
        candidate_avg_weekly_volume=Decimal("125"),
        weekly_volume_gap=Decimal("25"),
        weekly_volume_ratio=Decimal("1.25"),
        common_week_count=8,
        common_platform_count=1,
        causal_claim=False,
        result_hash="market-hash",
    )


def _relations() -> list[RelationAssessment]:
    rows = []
    for code in sorted(ALL_RELATION_CODES):
        primary = code == "direct_substitute"
        rows.append(
            RelationAssessment(
                relation_code=code,
                status="passed" if primary else "failed",
                is_primary=primary,
                confidence_level="high" if primary else "medium",
                gate_results=[_gate(f"{code}_gate")],
                supporting_evidence_families=(
                    ["F1_purchase_reason", "F4_user_realization"]
                    if primary
                    else []
                ),
                eligible_question_codes=(
                    ["purchase_choice", "key_competitor_selection"]
                    if primary
                    else []
                ),
                reason_codes=[] if primary else ["relation_gate_failed"],
                evidence_refs=[_evidence()],
                result_hash=f"relation-{code}",
            )
        )
    return rows


def _questions(*, selected: bool = True) -> list[QuestionEligibility]:
    rows = []
    for code in sorted(ALL_QUESTION_CODES):
        eligible = code in {"purchase_choice", "price_volume_pressure"} or (
            selected and code == "key_competitor_selection"
        )
        rows.append(
            QuestionEligibility(
                question_code=code,
                availability="eligible" if eligible else "unavailable",
                usable_relation_codes=["direct_substitute"] if eligible else [],
                required_evidence_families=[
                    "F1_purchase_reason",
                    "F4_user_realization",
                ],
                available_evidence_families=(
                    ["F1_purchase_reason", "F4_user_realization"]
                    if eligible
                    else []
                ),
                missing_inputs=[] if eligible else [f"missing-{code}"],
                business_boundary_code="question_usable" if eligible else "input_missing",
                reason_cn="可以回答。" if eligible else "当前证据不足。",
                result_hash=f"question-{code}",
            )
        )
    return rows


def _pair(
    *,
    candidate_code: str = "TV-C1",
    selected: bool = True,
    competitor_member: bool = True,
    reference_member: bool = False,
    candidate_status: str = "eligible",
    confidence: Decimal = Decimal("0.85"),
    review_required: bool = False,
) -> CompetitorPairDraft:
    relations = _relations()
    if not competitor_member:
        relations = [
            row.model_copy(
                update={
                    "status": "failed",
                    "is_primary": False,
                    "eligible_question_codes": [],
                    "reason_codes": ["reference_only"],
                }
            )
            for row in relations
        ]
    return CompetitorPairDraft(
        project_id="project-tv",
        category_code="TV",
        target_sku_code="TV-TARGET",
        candidate=CandidateIdentity(
            sku_code=candidate_code,
            brand_name="品牌A",
            model_name="型号A",
            display_name_cn=f"品牌A {candidate_code}",
            product_category="TV",
        ),
        recall_sources=["same_budget", "same_value"],
        manifest_order_key=candidate_code,
        competitor_member=competitor_member,
        reference_member=reference_member,
        candidate_status=candidate_status,
        purchase_pool=_pool(),
        evidence_family_assessments=_families(),
        market_comparison=_market(),
        relation_assessments=relations,
        question_eligibility=_questions(selected=selected),
        reference_purposes=(
            ["same_value_realization_reference"] if reference_member else []
        ),
        selected=selected,
        non_selection_reason_code=None if selected else "topic_already_covered",
        non_selection_reason_cn=None if selected else "该压力已由证据更强的候选覆盖。",
        confidence_level="low" if confidence < Decimal("0.6") else "high",
        confidence=confidence,
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        evidence_refs=[_evidence()],
        input_fingerprint=f"pair-input-{candidate_code}",
        result_hash=f"pair-result-{candidate_code}",
    )


def _selection(candidate_code: str = "TV-C1", rank: int = 1):
    return KeyCompetitorSelectionDraft(
        target_sku_code="TV-TARGET",
        candidate_sku_code=candidate_code,
        selection_rank=rank,
        primary_decision_topic="purchase_choice",
        covered_decision_topics=["purchase_choice", "value_route"],
        primary_relation_code="direct_substitute",
        auxiliary_relation_codes=[],
        selection_reason_cn="它与本品处于同一购买池并承接相同核心价值。",
        independent_information_reason_cn="它回答用户最可能在哪两款之间选择。",
        confidence_level="high",
        evidence_refs=[_evidence()],
        result_hash=f"selection-{candidate_code}",
    )


def _profile(
    *,
    analysis_state: str = "ready",
    conclusion_state: str = "available",
    selections: list[KeyCompetitorSelectionDraft] | None = None,
    confidence: Decimal = Decimal("0.85"),
    review_required: bool = False,
) -> SkuCompetitorDecisionProfileDraft:
    selected = [_selection()] if selections is None else selections
    summaries = [
        KeyCompetitorSummary(
            candidate_sku_code=row.candidate_sku_code,
            display_name_cn=f"品牌A {row.candidate_sku_code}",
            selection_rank=row.selection_rank,
            primary_decision_topic=row.primary_decision_topic,
            primary_relation_code=row.primary_relation_code,
            conclusion_cn="这是当前最需要关注的用户选择对手。",
        )
        for row in selected
    ]
    return SkuCompetitorDecisionProfileDraft(
        project_id="project-tv",
        category_code="TV",
        target_sku_code="TV-TARGET",
        brand_name="海信",
        model_name="65E7Q",
        display_name_cn="海信 65E7Q",
        analysis_state=analysis_state,
        conclusion_state=conclusion_state,
        freshness_status="current",
        profile_confidence=confidence,
        candidate_status_counts={"eligible": len(selected)},
        relation_status_counts={"passed": len(selected)},
        key_competitor_summary=summaries,
        competitive_advantages=(
            [{"conclusion_cn": "画质价值获得相对市场支撑。"}]
            if conclusion_state == "available"
            else []
        ),
        no_conclusion_reason=(
            {"reason_cn": "关键用户价值证据不足。"}
            if conclusion_state == "insufficient_evidence"
            else {}
        ),
        review_required=review_required,
        review_status="review_required" if review_required else "auto_pass",
        input_fingerprint="profile-input",
        result_hash="profile-result",
    )


def _draft_scope() -> dict[str, Any]:
    return {
        "competitor_profile_version_id": "version-1",
        "project_id": "project-tv",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-2",
        "release_scope_key": "scope-tv",
        "profile_version": "competitor-profile-v1",
        "input_fingerprint": "profile-input",
        "result_hash": "row-result",
    }


def _persistence_bundle() -> CompetitorProfilePersistenceBundle:
    pair = _pair()
    profile_row = SkuCompetitorProfileDraft(
        **{**_draft_scope(), "result_hash": "profile-result"},
        target_sku_code="TV-TARGET",
        profile_payload=_profile(),
    )
    pair_row = SkuCompetitorPairDraft(
        **{
            **_draft_scope(),
            "input_fingerprint": "pair-input-TV-C1",
            "result_hash": "pair-result-TV-C1",
        },
        target_sku_code="TV-TARGET",
        candidate_sku_code="TV-C1",
        candidate_status="eligible",
        confidence_level="high",
        selected=True,
        competitor_member=True,
        reference_member=False,
        pair_payload=pair,
    )
    relation_rows = [
        SkuCompetitorRelationDraft(
            **{**_draft_scope(), "result_hash": row.result_hash},
            target_sku_code="TV-TARGET",
            candidate_sku_code="TV-C1",
            relation_code=row.relation_code,
            relation_payload=row,
        )
        for row in pair.relation_assessments
    ]
    selection_row = SkuCompetitorSelectionDraft(
        **{**_draft_scope(), "result_hash": "selection-TV-C1"},
        target_sku_code="TV-TARGET",
        candidate_sku_code="TV-C1",
        selection_rank=1,
        selection_payload=_selection(),
    )
    return CompetitorProfilePersistenceBundle(
        profile=profile_row,
        pairs=[pair_row],
        relations=relation_rows,
        selections=[selection_row],
    )


def test_serving_scope_supports_tv_multi_batch_and_ac_single_batch() -> None:
    tv = _scope("TV")
    ac = _scope("AC")

    assert tv.source_batch_ids == ["batch-1", "batch-2"]
    assert ac.source_batch_ids == ["batch-ac"]
    assert tv.authoritative_sku_count == 377
    assert ac.authoritative_sku_count == 155


def test_serving_scope_rejects_unsorted_batches_and_cross_category_authority() -> None:
    payload = _scope().model_dump(mode="python")
    payload["source_batch_ids"] = ["batch-2", "batch-1"]
    with pytest.raises(ValidationError, match="sorted and unique"):
        ServingScope(**payload)

    payload = _scope().model_dump(mode="python")
    payload["source_authorities"]["M07"]["category_code"] = "AC"
    payload["source_authorities"]["M07"]["product_category"] = "AC"
    with pytest.raises(ValidationError, match="category must match"):
        ServingScope(**payload)


def test_source_authority_rejects_published_non_current_and_preview_current() -> None:
    with pytest.raises(ValidationError, match="published source authority must be current"):
        SourceAuthorityRef(
            **{
                **_authority().model_dump(mode="python"),
                "is_current": False,
            }
        )
    with pytest.raises(ValidationError, match="preview source authority cannot be current"):
        SourceAuthorityRef(
            **{
                **_authority(release_status="preview").model_dump(mode="python"),
                "is_current": True,
            }
        )


def test_runtime_boundary_rejects_nested_factory_keys() -> None:
    payload = _profile().model_dump(mode="python")
    payload["competitive_advantages"] = [{"prompt_template": "hidden"}]

    with pytest.raises(ValidationError, match="factory-only keys"):
        SkuCompetitorDecisionProfileDraft(**payload)


def test_runtime_boundary_does_not_copy_the_validated_model_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _profile().model_dump(mode="python")

    def _unexpected_model_dump(*args, **kwargs):
        raise AssertionError("runtime-boundary validation must not dump the model graph")

    monkeypatch.setattr(
        SkuCompetitorDecisionProfileDraft,
        "model_dump",
        _unexpected_model_dump,
    )

    profile = SkuCompetitorDecisionProfileDraft(**payload)
    assert profile.target_sku_code == "TV-TARGET"


def test_gate_preserves_unknown_instead_of_false() -> None:
    gate = _gate("unknown_gate", known=False, passed=None)
    assert gate.passed is None

    with pytest.raises(ValidationError, match="unknown gates cannot"):
        _gate("unknown_gate", known=False, passed=False)


def test_purchase_pool_unknown_requires_unknown_required_gate() -> None:
    assert _pool(unknown=True).level == "unknown"
    payload = _pool().model_dump(mode="python")
    payload["level"] = "unknown"

    with pytest.raises(ValidationError, match="requires an unknown required gate"):
        PurchasePoolAssessment(**payload)


def test_generic_and_missing_evidence_family_boundaries() -> None:
    base = _families()[0].model_dump(mode="python")
    base["status"] = "generic"
    with pytest.raises(ValidationError, match="require a reason code"):
        EvidenceFamilyAssessment(**base)

    base = _families()[0].model_dump(mode="python")
    base["status"] = "missing"
    with pytest.raises(ValidationError, match="cannot carry matches"):
        EvidenceFamilyAssessment(**base)


def test_market_comparison_forbids_causal_claim_and_invalid_ratios() -> None:
    payload = _market().model_dump(mode="python")
    payload["causal_claim"] = True
    with pytest.raises(ValidationError):
        PairMarketComparison(**payload)

    payload = _market().model_dump(mode="python")
    payload["target_weighted_price"] = None
    with pytest.raises(ValidationError, match="price gap pct"):
        PairMarketComparison(**payload)

    payload = _market().model_dump(mode="python")
    payload["target_avg_weekly_volume"] = Decimal("0")
    with pytest.raises(ValidationError, match="weekly volume ratio"):
        PairMarketComparison(**payload)


def test_market_unknown_requires_reason_and_preserves_nulls() -> None:
    market = PairMarketComparison(
        source_authority=_authority(),
        analysis_population="full_window",
        market_window="window",
        comparability_status="unknown",
        unknown_reasons=["market_missing"],
        result_hash="unknown-market",
    )
    dumped = market.model_dump(mode="json")

    assert dumped["target_weighted_price"] is None
    assert dumped["causal_claim"] is False


def test_relation_requires_questions_or_failure_reasons() -> None:
    passed = _relations()[0].model_dump(mode="python")
    passed["status"] = "passed"
    passed["eligible_question_codes"] = []
    passed["reason_codes"] = []
    with pytest.raises(ValidationError, match="require an eligible question"):
        RelationAssessment(**passed)

    failed = _relations()[1].model_dump(mode="python")
    failed["status"] = "failed"
    failed["reason_codes"] = []
    with pytest.raises(ValidationError, match="require a reason code"):
        RelationAssessment(**failed)


def test_question_available_evidence_must_be_required() -> None:
    payload = _questions()[0].model_dump(mode="python")
    payload["available_evidence_families"] = ["F3_audience_need"]

    with pytest.raises(ValidationError, match="subset"):
        QuestionEligibility(**payload)


def test_pair_requires_all_five_families_seven_relations_and_eight_questions() -> None:
    pair = _pair()
    assert len(pair.evidence_family_assessments) == 5
    assert len(pair.relation_assessments) == 7
    assert len(pair.question_eligibility) == 8

    payload = pair.model_dump(mode="python")
    payload["relation_assessments"] = payload["relation_assessments"][:-1]
    with pytest.raises(ValidationError, match="all relations"):
        CompetitorPairDraft(**payload)


def test_pair_rejects_self_cross_category_and_no_membership() -> None:
    payload = _pair().model_dump(mode="python")
    payload["candidate"]["sku_code"] = "TV-TARGET"
    with pytest.raises(ValidationError, match="must differ"):
        CompetitorPairDraft(**payload)

    payload = _pair().model_dump(mode="python")
    payload["candidate"]["product_category"] = "AC"
    with pytest.raises(ValidationError, match="product category"):
        CompetitorPairDraft(**payload)

    payload = _pair().model_dump(mode="python")
    payload["competitor_member"] = False
    payload["reference_member"] = False
    with pytest.raises(ValidationError, match="requires competitor or reference"):
        CompetitorPairDraft(**payload)


def test_reference_only_pair_is_separate_and_cannot_be_selected() -> None:
    pair = _pair(
        selected=False,
        competitor_member=False,
        reference_member=True,
        candidate_status="reference_only",
    )
    assert pair.reference_member is True
    assert pair.competitor_member is False

    payload = pair.model_dump(mode="python")
    payload["selected"] = True
    with pytest.raises(ValidationError, match="only eligible or limited"):
        CompetitorPairDraft(**payload)


def test_low_confidence_pair_requires_review_and_cannot_auto_pass() -> None:
    with pytest.raises(ValidationError, match="require review"):
        _pair(selected=False, confidence=Decimal("0.4"))

    pair = _pair(
        selected=False,
        confidence=Decimal("0.4"),
        review_required=True,
    )
    assert pair.review_status == "review_required"


@pytest.mark.parametrize(
    ("analysis_state", "conclusion_state", "allowed"),
    [
        ("ready", "no_priority_competitor", True),
        ("partial", "no_priority_competitor", False),
        ("partial", "insufficient_evidence", True),
        ("ready", "insufficient_evidence", False),
    ],
)
def test_profile_distinguishes_no_priority_from_insufficient(
    analysis_state: str,
    conclusion_state: str,
    allowed: bool,
) -> None:
    kwargs = {
        "analysis_state": analysis_state,
        "conclusion_state": conclusion_state,
        "selections": [],
        "review_required": analysis_state == "blocked",
    }
    if allowed:
        profile = _profile(**kwargs)
        assert profile.conclusion_state == conclusion_state
    else:
        with pytest.raises(ValidationError):
            _profile(**kwargs)


def test_profile_and_bundle_allow_zero_to_three_selections_without_forcing_three() -> None:
    for count in range(4):
        selections = [_selection(f"TV-C{index}", index) for index in range(1, count + 1)]
        pairs = [
            _pair(candidate_code=f"TV-C{index}")
            for index in range(1, count + 1)
        ]
        conclusion = "available" if count else "no_priority_competitor"
        profile = _profile(conclusion_state=conclusion, selections=selections)
        bundle = CompetitorProfileDraftBundle(
            profile=profile,
            pairs=pairs,
            selections=selections,
        )
        assert len(bundle.selections) == count


def test_bundle_rejects_selection_not_backed_by_selected_pair() -> None:
    pair = _pair(selected=False)
    with pytest.raises(ValidationError, match="selected pair"):
        CompetitorProfileDraftBundle(
            profile=_profile(),
            pairs=[pair],
            selections=[_selection()],
        )


def test_version_draft_validates_scope_counts_and_publish_current_separation() -> None:
    scope = _scope()
    version = CompetitorProfileVersionDraftCreate(
        project_id="project-tv",
        category_code="TV",
        product_category="TV",
        storage_batch_id="batch-2",
        release_scope_key="scope-tv",
        profile_version="competitor-v1",
        method_versions_json={"recall": "v1", "relation": "v1"},
        serving_scope=scope,
        sku_count=377,
        input_fingerprint="version-input",
        candidate_universe_fingerprint="candidate-input",
        result_hash="version-result",
    )

    assert version.release_status == "draft"
    assert version.is_current is False

    payload = version.model_dump(mode="python")
    payload["ready_count"] = 378
    with pytest.raises(ValidationError, match="cannot exceed SKU count"):
        CompetitorProfileVersionDraftCreate(**payload)


def test_published_version_record_requires_publisher_and_current_actor() -> None:
    now = datetime.now(timezone.utc)
    base = {
        **CompetitorProfileVersionDraftCreate(
            project_id="project-tv",
            category_code="TV",
            product_category="TV",
            storage_batch_id="batch-2",
            release_scope_key="scope-tv",
            profile_version="competitor-v1",
            method_versions_json={"recall": "v1"},
            serving_scope=_scope(),
            sku_count=377,
            input_fingerprint="version-input",
            candidate_universe_fingerprint="candidate-input",
            result_hash="version-result",
        ).model_dump(mode="python"),
        "competitor_profile_version_id": "version-1",
        "release_status": "published",
        "release_quality_status": "ready",
        "is_current": True,
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
        "published_at": now,
        "published_by": "pm-owner",
        "current_at": now,
        "current_by": "release-owner",
    }
    record = CompetitorProfileVersionRecord(**base)
    assert record.published_by == "pm-owner"
    assert record.current_by == "release-owner"

    with pytest.raises(ValidationError, match="explicit actor"):
        CompetitorProfileVersionRecord(**{**base, "current_by": None})


def test_persistence_bundle_requires_all_relations_and_matching_scope() -> None:
    bundle = _persistence_bundle()
    assert len(bundle.relations) == 7

    payload = bundle.model_dump(mode="python")
    payload["relations"] = payload["relations"][:-1]
    with pytest.raises(ValidationError, match="all seven relations"):
        CompetitorProfilePersistenceBundle(**payload)

    payload = bundle.model_dump(mode="python")
    payload["pairs"][0]["project_id"] = "other-project"
    with pytest.raises(ValidationError, match="must match persisted scope"):
        CompetitorProfilePersistenceBundle(**payload)


def test_formal_read_requires_current_published_but_preview_accepts_draft() -> None:
    bundle = _persistence_bundle()
    now = datetime.now(timezone.utc)
    version_payload = {
        "competitor_profile_version_id": "version-1",
        "project_id": "project-tv",
        "category_code": "TV",
        "product_category": "TV",
        "storage_batch_id": "batch-2",
        "release_scope_key": "scope-tv",
        "profile_version": "competitor-v1",
        "schema_version": "schema-v1",
        "rule_version": "rule-v1",
        "method_version": "method-v1",
        "method_versions_json": {"recall": "v1"},
        "serving_scope": _scope(),
        "release_status": "draft",
        "release_quality_status": "unassessed",
        "is_current": False,
        "freshness_status": "current",
        "generated_at": now,
        "generated_by": "system",
        "sku_count": 1,
        "ready_count": 1,
        "partial_count": 0,
        "blocked_count": 0,
        "failed_count": 0,
        "pair_count": 1,
        "relation_count": 7,
        "selection_count": 1,
        "input_fingerprint": "version-input",
        "candidate_universe_fingerprint": "candidate-input",
        "result_hash": "version-result",
        "processing_status": "completed",
        "review_required": False,
        "review_status": "unassessed",
        "created_at": now,
        "updated_at": now,
    }
    version = CompetitorProfileVersionRecord(**version_payload)
    preview = CompetitorProfileReadBundle(
        version=version,
        profile=bundle.profile,
        pairs=bundle.pairs,
        relations=bundle.relations,
        selections=bundle.selections,
        preview=True,
    )
    assert preview.preview is True
    with pytest.raises(ValidationError, match="current published"):
        CompetitorProfileReadBundle(
            version=version,
            profile=bundle.profile,
            pairs=bundle.pairs,
            relations=bundle.relations,
            selections=bundle.selections,
            preview=False,
        )


@pytest.mark.parametrize(
    ("group", "index"),
    [
        ("profile", None),
        ("pairs", 0),
        ("relations", 0),
        ("selections", 0),
    ],
)
def test_persistence_rows_require_payload_matching_result_hash(
    group: str,
    index: int | None,
) -> None:
    payload = _persistence_bundle().model_dump(mode="python")
    row = payload[group] if index is None else payload[group][index]
    row["result_hash"] = "tampered-outer-hash"

    with pytest.raises(ValidationError, match="result hash must match"):
        CompetitorProfilePersistenceBundle(**payload)
