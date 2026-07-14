from __future__ import annotations

import inspect
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_candidate_eligibility as eligibility_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility import (
    CandidateEligibilityClassifier,
    CandidateEligibilityScopeError,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityAssessment,
    CandidateEligibilityConfig,
    CandidateEligibilityManifest,
    ProvisionalQuestionAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallManifest,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    QuestionCode,
    ReferencePurpose,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _recall,
    _target_bundle,
    _tv_specs,
)


def _classify(bundle: Any, target_sku_code: str) -> CandidateEligibilityManifest:
    target = _target_bundle(bundle, target_sku_code)
    return CandidateEligibilityClassifier().classify(
        bundle,
        target,
        _recall(bundle, target_sku_code),
    )


def _by_sku(manifest: CandidateEligibilityManifest) -> dict[str, Any]:
    return {row.candidate.sku_code: row for row in manifest.candidates}


def test_relation_evaluation_reference_and_formal_competitor_memberships_are_separate() -> (
    None
):
    manifest = _classify(_category_bundle(), "TV000001")
    by_sku = _by_sku(manifest)
    direct = by_sku["TV000002"]
    sparse = by_sku["TV000006"]

    assert direct.relation_evaluation_member is True
    assert direct.competitor_member is False
    assert direct.reference_member is True
    assert direct.candidate_status == "recalled_only"
    assert "same_value_realization_reference" in direct.reference_purposes
    assert "price_volume_archetype_reference" in direct.reference_purposes

    assert sparse.relation_evaluation_member is False
    assert sparse.competitor_member is False
    assert sparse.reference_member is True
    assert sparse.candidate_status == "reference_only"
    assert sparse.reference_purposes == ["price_volume_archetype_reference"]
    assert "candidate_m12d_unknown" in sparse.unknown_reason_codes
    assert (
        manifest.candidate_count
        == manifest.relation_evaluation_candidate_count
        + sum(not row.relation_evaluation_member for row in manifest.candidates)
    )


def test_all_eight_questions_are_provisional_and_cannot_drive_business_conclusions() -> (
    None
):
    direct = _by_sku(_classify(_category_bundle(), "TV000001"))["TV000002"]
    by_question = {row.question_code: row for row in direct.question_readiness}

    assert set(by_question) == {item.value for item in QuestionCode}
    assert all(
        row.can_drive_business_conclusion is False for row in by_question.values()
    )
    assert by_question["purchase_choice"].readiness == "provisional_eligible"
    assert by_question["key_competitor_selection"].readiness == "provisional_limited"
    assert by_question["key_competitor_selection"].missing_inputs == [
        "completed_relation_assessments"
    ]
    assert set(by_question["purchase_choice"].pending_relation_codes) >= {
        "direct_substitute",
        "same_budget_alternative",
        "same_value_substitute",
    }


def test_single_broad_recall_routes_do_not_become_relation_evaluation_members() -> None:
    target = _default_spec("TV", 1)
    target.update({"brand": "同品牌", "price": Decimal("5000")})
    same_brand_budget_only = _default_spec("TV", 2)
    same_brand_budget_only.update({"brand": "同品牌", "price": Decimal("5100")})
    shared_task_only = _default_spec("TV", 3)
    shared_task_only.update(
        {
            "brand": "另一品牌",
            "price": Decimal("5100"),
            "screen_size": Decimal("55"),
            "size_segment": "55",
            "task_primary": target["task_primary"],
        }
    )
    manifest = _classify(
        _category_bundle(specs=[target, same_brand_budget_only, shared_task_only]),
        "TV000001",
    )
    by_sku = _by_sku(manifest)

    assert by_sku["TV000002"].relation_evaluation_member is False
    assert by_sku["TV000002"].candidate_status == "reference_only"
    assert by_sku["TV000003"].relation_evaluation_member is False
    assert by_sku["TV000003"].candidate_status == "recalled_only"
    assert by_sku["TV000003"].reference_member is False


def test_reference_mapping_covers_all_seven_purposes_without_treating_missing_as_absence() -> (
    None
):
    bundle = _category_bundle()
    direct_m03 = bundle.modules["M03B"].records_by_sku["TV000002"][0]
    direct_m03.facts["param_values_json"]["cooling_capacity_segment"][
        "normalized_value"
    ] = "different-tier"
    direct_claim = bundle.modules["M12C"].records_by_sku["TV000002"][0]
    direct_claim.facts["claim_value_role"] = "known_absent"

    manifest = _classify(bundle, "TV000001")
    all_purposes = {
        purpose
        for candidate in manifest.candidates
        for purpose in candidate.reference_purposes
    }
    assert all_purposes == {item.value for item in ReferencePurpose}
    by_sku = _by_sku(manifest)
    assert "market_baseline_without_value" in by_sku["TV000002"].reference_purposes
    assert "high_performance_value_bundle" in by_sku["TV000004"].reference_purposes
    assert "low_performance_value_bundle" in by_sku["TV000003"].reference_purposes

    ordinary = _by_sku(_classify(_category_bundle(), "TV000001"))["TV000002"]
    assert "market_baseline_without_value" not in ordinary.reference_purposes


def test_review_flags_and_lineage_conflicts_do_not_drive_relation_or_reference_membership() -> (
    None
):
    review_bundle = _category_bundle()
    review_bundle.modules["M12D"].records_by_sku["TV000002"][0].facts[
        "review_required"
    ] = True
    reviewed = _by_sku(_classify(review_bundle, "TV000001"))["TV000002"]
    assert reviewed.candidate_status == "review_required"
    assert reviewed.relation_evaluation_member is False
    assert reviewed.reference_member is False
    assert reviewed.review_reason_codes == ["source_m12d_review_required"]
    assert all(
        row.readiness == "unavailable"
        and row.missing_inputs == ["candidate_source_review_required"]
        for row in reviewed.question_readiness
    )

    bundle = _category_bundle()
    recall_payload = _recall(bundle, "TV000001").model_dump(mode="python")
    recall_payload["candidates"][0]["recall_facts"][0]["candidate_evidence_refs"][0][
        "result_hash"
    ] = "tampered-lineage-hash"
    tampered_recall = CandidateRecallManifest.model_validate(recall_payload)
    blocked = _by_sku(
        CandidateEligibilityClassifier().classify(
            bundle,
            _target_bundle(bundle, "TV000001"),
            tampered_recall,
        )
    )[recall_payload["candidates"][0]["candidate"]["sku_code"]]
    assert blocked.candidate_status == "blocked"
    assert blocked.relation_evaluation_member is False
    assert blocked.reference_member is False
    assert set(blocked.review_reason_codes) >= {
        "candidate_evidence_ref_not_in_locked_authority",
        "candidate_recall_evidence_set_conflict",
    }

    flagged_bundle = _category_bundle()
    flagged_bundle.modules["M12D"].records_by_sku["TV000002"][0].facts[
        "quality_flags"
    ] = ["lineage_conflict"]
    flagged = _by_sku(_classify(flagged_bundle, "TV000001"))["TV000002"]
    assert flagged.candidate_status == "blocked"
    assert flagged.review_reason_codes == ["candidate_m12d_lineage_conflict"]


def test_tv_and_ac_candidates_use_category_specific_form_assessability() -> None:
    tv = _classify(_category_bundle(), "TV000001")
    assert _by_sku(tv)["TV000002"].relation_evaluation_member is True

    target = _default_spec("AC", 1)
    target.update(
        {
            "brand": "格力",
            "price": Decimal("3200"),
            "market_pool": "ac-wall-1.5p",
            "task_primary": "sleep-comfort",
            "purchase_reasons": ["quiet-sleep"],
            "claim_values": ["quiet-cooling"],
        }
    )
    candidate = _default_spec("AC", 2)
    candidate.update(
        {
            "brand": "美的",
            "price": Decimal("3300"),
            "market_pool": "ac-wall-1.5p",
            "task_primary": "sleep-comfort",
            "purchase_reasons": ["quiet-sleep"],
            "claim_values": ["quiet-cooling"],
        }
    )
    ac = _classify(_category_bundle("AC", [target, candidate]), "AC000001")
    ac_candidate = ac.candidates[0]
    assert ac_candidate.candidate.product_category == "AC"
    assert ac_candidate.relation_evaluation_member is True
    assert ac_candidate.competitor_member is False


def test_empty_manifest_order_stability_and_candidate_conservation() -> None:
    first = _classify(_category_bundle(), "TV000001")
    reordered = _classify(
        _category_bundle(reorder_semantic_values=True),
        "TV000001",
    )
    assert reordered.result_hash == first.result_hash
    assert [row.result_hash for row in reordered.candidates] == [
        row.result_hash for row in first.candidates
    ]
    assert [row.candidate.sku_code for row in first.candidates] == sorted(
        row.candidate.sku_code for row in first.candidates
    )
    assert first.candidate_count == len(first.candidates)
    assert sum(first.candidate_count_by_status.values()) == first.candidate_count

    target = _default_spec("TV", 1)
    unrelated = _default_spec("TV", 2)
    unrelated.update(
        {
            "price": Decimal("9000"),
            "screen_size": Decimal("55"),
            "size_segment": "55",
            "market_pool": "unrelated-pool",
        }
    )
    empty = _classify(_category_bundle(specs=[target, unrelated]), "TV000001")
    assert empty.candidate_count == 0
    assert empty.candidates == []
    assert empty.candidate_count_by_status == {}
    assert "candidate_eligibility_manifest_empty" in empty.limitations


def test_scope_conflicts_fail_closed_and_classifier_has_no_database_dependency() -> (
    None
):
    bundle = _category_bundle()
    target = _target_bundle(bundle, "TV000001")
    recall = _recall(bundle, "TV000001")
    payload = recall.model_dump(mode="python")
    payload["category_input_fingerprint"] = "wrong-authority-fingerprint"
    conflicting = CandidateRecallManifest.model_validate(payload)
    with pytest.raises(CandidateEligibilityScopeError, match="exact input authority"):
        CandidateEligibilityClassifier().classify(bundle, target, conflicting)

    source = inspect.getsource(eligibility_module)
    assert "sqlalchemy" not in source.lower()
    assert "repository" not in source.lower()
    assert ".query(" not in source


def test_eligibility_schemas_reject_config_drift_and_membership_contradictions() -> (
    None
):
    with pytest.raises(ValidationError, match="new config version"):
        CandidateEligibilityConfig(explicit_absence_claim_roles=["known_absent"])
    assert (
        CandidateEligibilityConfig(
            config_version="test-custom-eligibility-v1",
            explicit_absence_claim_roles=["known_absent"],
        ).config_version
        == "test-custom-eligibility-v1"
    )

    manifest = _classify(_category_bundle(), "TV000001")
    candidate = next(row for row in manifest.candidates if row.reference_purposes)
    candidate_payload = candidate.model_dump(mode="python")
    candidate_payload["reference_member"] = False
    with pytest.raises(ValidationError, match="reference membership"):
        CandidateEligibilityAssessment.model_validate(candidate_payload)

    question_payload = candidate.question_readiness[0].model_dump(mode="python")
    question_payload["readiness"] = "unavailable"
    question_payload["missing_inputs"] = []
    with pytest.raises(ValidationError, match="require missing inputs"):
        ProvisionalQuestionAssessment.model_validate(question_payload)

    manifest_payload = manifest.model_dump(mode="python")
    manifest_payload["candidate_count"] += 1
    with pytest.raises(ValidationError, match="candidate count"):
        CandidateEligibilityManifest.model_validate(manifest_payload)


def test_unknown_source_data_remains_unknown_instead_of_false_or_zero() -> None:
    specs = _tv_specs()
    sparse = next(row for row in specs if row["sku_code"] == "TV000006")
    sparse["missing_modules"] = {
        "M04C",
        "M05C",
        "M09C",
        "M10C",
        "M11C",
        "M11D",
        "M12C",
        "M12D",
    }
    candidate = _by_sku(_classify(_category_bundle(specs=specs), "TV000001"))[
        "TV000006"
    ]

    assert candidate.candidate_status == "reference_only"
    assert "candidate_m05c_unknown" in candidate.unknown_reason_codes
    assert "market_baseline_without_value" not in candidate.reference_purposes
    assert candidate.available_evidence_families == ["F5_capability_expression"]
    purchase = next(
        row
        for row in candidate.question_readiness
        if row.question_code == "purchase_choice"
    )
    assert purchase.readiness == "unavailable"
    assert "purchase_reason_or_user_realization_evidence" in purchase.missing_inputs
