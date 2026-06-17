from app.services.core3_real_data.comment_quality_profile_service import CommentQualityProfileService
from app.services.core3_real_data.comment_review_policy import CommentEvidenceReviewPolicy

from .test_m05_comment_quality_profile_service import (
    BATCH_ID,
    PROJECT_ID,
    SKU_CODE,
    make_atom,
    make_topic,
    make_unit,
)


def build_profile(units, atoms, topics):
    return CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=units,
        sentence_atoms=atoms,
        topic_hints=topics,
    ).record


def test_review_policy_converts_quality_warnings_to_review_issues_and_impacts():
    units = [
        make_unit(0, comment_text_hash="sha256:same", source_row_count=2),
        make_unit(1, comment_text_hash="sha256:same", source_row_count=2),
    ]
    atoms = [
        make_atom(0, units[0], domain="service_experience", sentiment="unknown", has_dimension=False),
        make_atom(1, units[0], domain="logistics_installation", sentiment="unknown", has_dimension=False),
        make_atom(2, units[1], domain="service_experience", sentiment="unknown", has_dimension=False, low_value=True),
        make_atom(3, units[1], domain="product_risk", sentiment="negative", has_dimension=True, low_value=True),
        make_atom(4, units[1], domain="service_experience", sentiment="negative", has_dimension=False, low_value=True),
    ]
    topics = [make_topic(0, atoms[0])]
    profile = build_profile(units, atoms, topics)

    result = CommentEvidenceReviewPolicy().evaluate(
        profile=profile,
        sentence_atoms=atoms,
        topic_hints=topics,
        target_sku_expected_comment_units={},
    )

    issue_codes = {issue.issue_code for issue in result.review_issues}
    assert "m05_low_value_sentence_rate_high" in issue_codes
    assert "m05_service_installation_share_high" in issue_codes
    assert "m05_topic_unknown_rate_high" in issue_codes
    assert result.blocked is False
    assert result.review_required is True
    assert {impact.target_module for impact in result.downstream_impacts} == {"M06", "M16"}
    assert all(impact.impact_level == "medium" for impact in result.downstream_impacts)
    assert all(issue.review_required for issue in result.review_issues)
    assert "business_conclusion" not in [key for issue in result.review_issues for key in issue.model_dump()]


def test_review_policy_blocks_when_preconditions_or_profile_are_blocked():
    profile = CommentQualityProfileService().build_profile(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
        comment_units=[],
        sentence_atoms=[],
        topic_hints=[],
        input_fingerprint="sha256:m05:empty",
    ).record

    result = CommentEvidenceReviewPolicy().evaluate(
        profile=profile,
        sentence_atoms=[],
        topic_hints=[],
        seed_loaded=False,
        m02_completed=False,
        target_sku_expected_comment_units={},
    )

    issue_codes = {issue.issue_code for issue in result.review_issues}
    assert {"m05_seed_missing", "m05_m02_not_completed", "m05_no_comment_unit", "m05_no_sentence_atom"} <= issue_codes
    assert result.blocked is True
    assert result.blocker_count >= 4
    assert {impact.target_module for impact in result.downstream_impacts} == {"M06", "M16"}
    assert all(impact.impact_level == "high" for impact in result.downstream_impacts)


def test_review_policy_reviews_service_comment_matched_as_product_topic():
    units = [make_unit(0)]
    atoms = [make_atom(0, units[0], domain="service_experience", sentiment="positive")]
    product_topic = make_topic(0, atoms[0], status="matched")
    profile = build_profile(units, atoms, [product_topic])

    result = CommentEvidenceReviewPolicy().evaluate(
        profile=profile,
        sentence_atoms=atoms,
        topic_hints=[product_topic],
        target_sku_expected_comment_units={},
    )

    service_issue = next(
        issue for issue in result.review_issues if issue.issue_code == "m05_service_comment_product_topic_conflict"
    )
    assert service_issue.object_type == "topic_hint"
    assert service_issue.object_id == product_topic.topic_hint_id
    assert service_issue.reason_code == "service_guardrail"
    assert service_issue.severity == "high"
    assert atoms[0].comment_evidence_id in service_issue.evidence_refs


def test_review_policy_reviews_target_sku_count_against_85e7q_reference_scale():
    units = [make_unit(idx) for idx in range(80)]
    atoms = [make_atom(idx, units[idx % len(units)]) for idx in range(120)]
    topics = [make_topic(idx, atom) for idx, atom in enumerate(atoms[:90])]
    profile = build_profile(units, atoms, topics)

    result = CommentEvidenceReviewPolicy().evaluate(
        profile=profile,
        sentence_atoms=atoms,
        topic_hints=topics,
    )

    issue_codes = {issue.issue_code for issue in result.review_issues}
    assert "m05_target_sku_comment_units_low" in issue_codes
    assert result.review_required is True
    assert result.blocked is False

