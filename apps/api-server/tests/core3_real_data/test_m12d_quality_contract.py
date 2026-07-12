from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    Core3CategoryCode,
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DReleaseQualityStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    M12DAnchorTaxonomyLoader,
)
from app.services.core3_real_data.purchase_reason_input_quality import (
    M12DInputQualityAdapter,
    legacy_status_from_quality,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamReadContract,
    M12DInputQuality,
    M12DInputQualityIssue,
)
from app.services.core3_real_data.purchase_reason_release_quality import (
    M12DReleaseQualityEvaluationError,
    M12DReleaseQualityEvaluator,
)
from app.services.core3_real_data.purchase_reason_quality_baseline import (
    baseline_fingerprint,
    summarize_m12d_records,
    summarize_upstream_rows,
)


def test_m12d_quality_contract_serializes_scope_and_affected_anchors() -> None:
    quality = M12DInputQuality(
        module_code="M07",
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED,
        issues=[
            M12DInputQualityIssue(
                code="trend_sample_insufficient",
                severity=M12DIssueSeverity.WARNING,
                scope=M12DIssueScope.ANCHOR,
                affected_anchor_codes=["market_accepted_upgrade"],
                source_refs=[
                    {"table_name": "core3_sku_market_profile", "record_id": "market-1"}
                ],
            )
        ],
    )

    assert quality.model_dump(mode="json") == {
        "module_code": "M07",
        "availability": "present",
        "usability": "limited",
        "issues": [
            {
                "code": "trend_sample_insufficient",
                "severity": "warning",
                "scope": "anchor",
                "message_cn": "",
                "affected_anchor_codes": ["market_accepted_upgrade"],
                "source_refs": [
                    {"table_name": "core3_sku_market_profile", "record_id": "market-1"}
                ],
                "details_json": {},
            }
        ],
    }


def test_m12d_compatibility_statuses_are_available_without_changing_reader_behavior() -> (
    None
):
    contract = M12DDownstreamReadContract(found=False)

    assert M12DProfileStatus.READY_LIMITED.value == "ready_limited"
    assert contract.release_quality_status == M12DReleaseQualityStatus.UNASSESSED.value
    assert (
        "release_quality_status"
        in entities.Core3PurchaseReasonProfileVersion.__table__.columns
    )
    assert (
        "input_quality_json" in entities.Core3SkuPurchaseReasonProfile.__table__.columns
    )


def test_m12d_release_quality_all_info_profiles_are_ready() -> None:
    profiles = _release_profiles(
        category="TV",
        ready_count=100,
        issue_count=100,
        issue_severity=M12DIssueSeverity.INFO,
    )

    result = M12DReleaseQualityEvaluator().evaluate(
        category_code=Core3CategoryCode.TV,
        product_category="TV",
        profiles=profiles,
        expected_sku_count=100,
        focus_validation_results=[{"sku_code": "TV_FOCUS", "passed": True}],
    )

    assert result.release_quality_status == M12DReleaseQualityStatus.READY.value
    assert result.blocking_issue_coverage_json == []
    assert result.system_issues == []
    assert all(item.passed for item in result.threshold_results)


def test_m12d_release_quality_counts_weak_expression_as_fact_consumable() -> None:
    result = M12DReleaseQualityEvaluator().evaluate(
        category_code="TV",
        product_category="TV",
        profiles=_release_profiles(category="TV", ready_count=85, weak_count=15),
        expected_sku_count=100,
        focus_validation_results=[{"sku_code": "TV_FOCUS", "passed": True}],
    )

    assert result.release_quality_status == M12DReleaseQualityStatus.READY.value
    assert result.metrics_json["ready_rate"] == "0.8500"
    assert result.metrics_json["ready_or_limited_rate"] == "0.8500"
    assert result.metrics_json["sku_consumable_rate"] == "1.0000"
    assert "sku_consumable_rate" not in result.failure_reason_codes


@pytest.mark.parametrize(
    ("blocking_count", "expected_status", "expected_system_issue_count"),
    [
        (20, M12DReleaseQualityStatus.READY.value, 0),
        (21, M12DReleaseQualityStatus.BLOCKED.value, 1),
    ],
)
def test_m12d_release_quality_blocks_only_above_twenty_percent(
    blocking_count: int,
    expected_status: str,
    expected_system_issue_count: int,
) -> None:
    profiles = _release_profiles(
        category="TV",
        ready_count=100,
        issue_count=blocking_count,
        issue_severity=M12DIssueSeverity.BLOCKING,
    )

    result = M12DReleaseQualityEvaluator().evaluate(
        category_code="TV",
        product_category="TV",
        profiles=profiles,
        expected_sku_count=100,
        focus_validation_results=[{"sku_code": "TV_FOCUS", "passed": True}],
    )

    assert result.release_quality_status == expected_status
    assert len(result.system_issues) == expected_system_issue_count
    assert (
        result.blocking_issue_coverage_json[0]["coverage_rate"]
        == f"0.{blocking_count:02d}00"
    )
    if expected_system_issue_count:
        assert result.system_issues[0].code == "systemic_blocking_issue_coverage"
        assert result.system_issues[0].source_issue_code == "shared_blocking_issue"


def test_m12d_release_quality_keeps_tv_and_ac_denominators_isolated() -> None:
    evaluator = M12DReleaseQualityEvaluator()
    tv = evaluator.evaluate(
        category_code="TV",
        product_category="TV",
        profiles=_release_profiles(category="TV", ready_count=100),
        expected_sku_count=100,
        focus_validation_results=[{"sku_code": "TV_FOCUS", "passed": True}],
    )
    ac = evaluator.evaluate(
        category_code="AC",
        product_category="AC",
        profiles=_release_profiles(category="AC", ready_count=84, limited_count=16),
        expected_sku_count=100,
        focus_validation_results=[{"sku_code": "AC_FOCUS", "passed": True}],
    )

    assert tv.release_quality_status == M12DReleaseQualityStatus.READY.value
    assert ac.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
    assert tv.metrics_json["ready_rate"] == "1.0000"
    assert ac.metrics_json["ready_rate"] == "0.8400"
    assert "ready_rate" in ac.failure_reason_codes


def test_m12d_release_quality_requires_focus_validation_for_ready() -> None:
    result = M12DReleaseQualityEvaluator().evaluate(
        category_code="TV",
        product_category="TV",
        profiles=_release_profiles(category="TV", ready_count=100),
        expected_sku_count=100,
    )

    assert result.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
    assert "focus_sku_pass_rate" in result.failure_reason_codes
    focus = next(
        item
        for item in result.threshold_results
        if item.metric_code == "focus_sku_pass_rate"
    )
    assert focus.applicable is False


def test_m12d_release_quality_requires_every_focus_sku_to_pass() -> None:
    result = M12DReleaseQualityEvaluator().evaluate(
        category_code="TV",
        product_category="TV",
        profiles=_release_profiles(category="TV", ready_count=100),
        expected_sku_count=100,
        focus_validation_results=[
            {"sku_code": "TV_FOCUS_1", "passed": True},
            {"sku_code": "TV_FOCUS_2", "passed": False},
        ],
    )

    assert result.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
    focus = next(
        item
        for item in result.threshold_results
        if item.metric_code == "focus_sku_pass_rate"
    )
    assert focus.observed_rate == Decimal("0.5000")
    assert focus.passed is False


def test_m12d_release_quality_rejects_cross_category_profiles() -> None:
    with pytest.raises(
        M12DReleaseQualityEvaluationError, match="cannot mix categories"
    ):
        M12DReleaseQualityEvaluator().evaluate(
            category_code="TV",
            product_category="TV",
            profiles=_release_profiles(category="AC", ready_count=1),
            expected_sku_count=1,
            focus_validation_results=[{"sku_code": "TV_FOCUS", "passed": True}],
        )


def test_m12d_baseline_summary_preserves_legacy_status_and_issue_counts() -> None:
    version = SimpleNamespace(
        purchase_reason_version_id="version-1",
        batch_id="batch-1",
        m12d_profile_version="profile-v1",
        rule_version="rule-v1",
        release_status="published",
        is_current=True,
        source_batch_ids_json=["source-1"],
    )
    profiles = [
        _profile(
            "TV001", "ready_degraded", "0.5000", True, ["missing_or_partial_inputs"]
        ),
        _profile("TV002", "weak_expression_only", "0.3000", False, []),
    ]
    anchors = [
        SimpleNamespace(
            sku_code="TV001",
            role="supporting",
            evidence_strength="medium",
            risk_flags_json=["missing_or_partial_inputs"],
        )
    ]

    summary = summarize_m12d_records(
        version=version, profiles=profiles, anchors=anchors
    )

    assert summary["status_counts"] == {"ready_degraded": 1, "weak_expression_only": 1}
    assert summary["review_required_count"] == 1
    assert summary["core_payment_missing_count"] == 2
    assert summary["profile_risk_flags"]["sku_counts"] == {
        "missing_or_partial_inputs": 1
    }
    assert summary["anchor_risk_flags"]["row_counts"] == {
        "missing_or_partial_inputs": 1
    }


def test_m12d_upstream_baseline_uses_latest_row_and_counts_flag_sku_coverage() -> None:
    older = SimpleNamespace(
        sku_code="AC001",
        batch_id="older-batch",
        updated_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        rule_version="rule-v1",
        quality_flags=["old_flag"],
        quality_flags_json=[],
        review_required=True,
        conflict_count=1,
    )
    latest = SimpleNamespace(
        sku_code="AC001",
        batch_id="preferred-batch",
        updated_at=datetime(2026, 7, 11, tzinfo=timezone.utc),
        rule_version="rule-v2",
        quality_flags=["current_flag"],
        quality_flags_json=[],
        review_required=False,
        conflict_count=0,
    )

    summary = summarize_upstream_rows(
        [older, latest], batch_order=("preferred-batch", "older-batch")
    )

    assert summary["row_count"] == 1
    assert summary["rule_versions"] == {"rule-v2": 1}
    assert summary["quality_flags"]["sku_counts"] == {"current_flag": 1}
    assert summary["conflict_sku_count"] == 0


def test_m12d_baseline_fingerprint_is_order_stable() -> None:
    left = {"categories": {"TV": {"status": {"ready": 1}}}, "project_id": "project"}
    right = {"project_id": "project", "categories": {"TV": {"status": {"ready": 1}}}}

    assert baseline_fingerprint(left) == baseline_fingerprint(right)


def test_m12d_market_scope_flags_are_info_and_keep_legacy_status_ready() -> None:
    adapter = _tv_quality_adapter()
    quality = adapter.market_profile(
        SimpleNamespace(
            sku_code="TV001",
            sample_status="complete",
            quality_flags=[
                "observed_window_less_than_52w",
                "online_only_channel",
                "zero_sales_is_observed_fact",
            ],
        )
    )

    assert quality.availability == "present"
    assert quality.usability == "usable"
    assert {issue.severity for issue in quality.issues} == {"info"}
    assert legacy_status_from_quality(quality) == M12DInputStatus.READY


def test_m12d_comment_conflict_only_affects_related_purchase_reasons() -> None:
    adapter = _tv_quality_adapter()
    quality = adapter.comment_profile(
        SimpleNamespace(
            sku_code="TV001",
            service_excluded_sentence_count=2,
            contradicted_claim_codes=["tv_claim_high_refresh"],
        ),
        facts=[],
    )

    contradiction = next(
        issue for issue in quality.issues if issue.code == "comment_claim_contradiction"
    )
    assert contradiction.scope == "anchor"
    assert "gaming_device_fit_reduces_risk" in contradiction.affected_anchor_codes
    assert "family_operation_less_friction" not in contradiction.affected_anchor_codes
    assert legacy_status_from_quality(quality) == M12DInputStatus.READY


def test_m12d_m12c_amount_limit_stays_on_matching_anchor() -> None:
    adapter = _tv_quality_adapter()
    quality = adapter.claim_value(
        [
            SimpleNamespace(
                sku_code="TV001",
                claim_code="tv_claim_miniled",
                claim_name="MiniLED 画质",
                claim_value_role="unique_payment_potential",
                supporting_dimensions_json={
                    "quality_assessment": {
                        "amount_quantification_status": "not_quantifiable",
                        "relative_comparison_status": "ready",
                    }
                },
                quality_flags_json=[
                    "l4_threshold_only",
                    "relaxed_pool_not_amount_quantifiable",
                    "l4_threshold_only_no_amount",
                ],
                reason_cn="画质卖点有定性价值，但当前不能量化金额。",
            )
        ]
    )

    issue = next(
        issue
        for issue in quality.issues
        if issue.code == "m12c_amount_not_quantifiable"
    )
    assert "picture_upgrade_justifies_price" in issue.affected_anchor_codes
    assert "family_operation_less_friction" not in issue.affected_anchor_codes
    assert issue.severity == "info"
    assert legacy_status_from_quality(quality) == M12DInputStatus.READY


def test_m12d_m12c_roles_are_grouped_by_matching_anchor() -> None:
    row = SimpleNamespace(
        sku_code="TV001",
        claim_code="tv_claim_miniled",
        claim_name="MiniLED 画质",
        claim_value_role="premium_driver_estimated",
        supporting_dimensions_json={},
        quality_flags_json=[],
        reason_cn="画质升级形成溢价理由。",
    )

    second_context_row = SimpleNamespace(
        **{
            **vars(row),
            "claim_value_role": "high_price_competitor_intercept",
        }
    )

    result = _tv_quality_adapter().claim_value_roles_by_anchor(
        [row, second_context_row]
    )

    assert result["picture_upgrade_justifies_price"] == {
        "tv_claim_miniled": [
            "high_price_competitor_intercept",
            "premium_driver_estimated",
        ]
    }
    assert "family_operation_less_friction" not in result


def test_m12d_m03b_conflict_only_maps_conflicting_param_to_anchors() -> None:
    quality = _tv_quality_adapter().param_profile(
        SimpleNamespace(
            sku_code="TV001",
            conflict_count=1,
            review_required_count=1,
            quality_summary_json={
                "conflict_param_codes": ["refresh_rate_hz"],
                "conflicts": [
                    {
                        "param_code": "refresh_rate_hz",
                        "affected_dimension_codes": ["gaming"],
                    }
                ],
            },
        )
    )

    issue = next(
        issue for issue in quality.issues if issue.code == "m03b_true_param_conflict"
    )
    assert issue.severity == "blocking"
    assert issue.scope == "anchor"
    assert "gaming_device_fit_reduces_risk" in issue.affected_anchor_codes
    assert "family_operation_less_friction" not in issue.affected_anchor_codes
    assert legacy_status_from_quality(quality) == M12DInputStatus.READY


def test_m12d_profile_blocking_issue_still_blocks_legacy_module_status() -> None:
    quality = M12DInputQuality(
        module_code="M04C",
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED,
        issues=[
            M12DInputQualityIssue(
                code="profile_contract_incompatible",
                severity=M12DIssueSeverity.BLOCKING,
                scope=M12DIssueScope.PROFILE,
            )
        ],
    )

    assert legacy_status_from_quality(quality) == M12DInputStatus.CONFLICT


def test_m12d_missing_module_remains_missing_without_fabricating_false() -> None:
    quality = _tv_quality_adapter().param_profile(None)

    assert quality.availability == "missing"
    assert quality.usability == "unusable"
    assert quality.issues[0].affected_anchor_codes
    assert legacy_status_from_quality(quality) == M12DInputStatus.MISSING


def _tv_quality_adapter() -> M12DInputQualityAdapter:
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category="TV",
    )
    return M12DInputQualityAdapter(taxonomy)


def _release_profiles(
    *,
    category: str,
    ready_count: int,
    limited_count: int = 0,
    weak_count: int = 0,
    issue_count: int = 0,
    issue_severity: M12DIssueSeverity = M12DIssueSeverity.INFO,
) -> list[SimpleNamespace]:
    total = ready_count + limited_count + weak_count
    profiles = []
    for index in range(total):
        if index < ready_count:
            status = M12DProfileStatus.READY.value
        elif index < ready_count + limited_count:
            status = M12DProfileStatus.READY_LIMITED.value
        else:
            status = M12DProfileStatus.WEAK_EXPRESSION_ONLY.value
        issues = []
        if index < issue_count:
            issues.append(
                M12DInputQualityIssue(
                    code="shared_blocking_issue",
                    severity=issue_severity,
                    scope=M12DIssueScope.ANCHOR,
                )
            )
        profiles.append(
            SimpleNamespace(
                sku_code=f"{category}{index:04d}",
                category_code=category,
                product_category=category,
                status=status,
                review_required=False,
                profile_confidence=Decimal("0.8500"),
                core_payment_anchors_json=(
                    ["core_reason"] if status == M12DProfileStatus.READY.value else []
                ),
                input_quality_json={
                    "M03B": M12DInputQuality(
                        module_code="M03B",
                        availability=M12DInputAvailability.PRESENT,
                        usability=M12DInputUsability.USABLE,
                        issues=issues,
                    )
                },
            )
        )
    return profiles


def _profile(
    sku_code: str,
    status: str,
    confidence: str,
    review_required: bool,
    risk_flags: list[str],
):
    return SimpleNamespace(
        sku_code=sku_code,
        status=status,
        review_status="review_required" if review_required else "auto_pass",
        review_required=review_required,
        review_reason_json={"reasons": ["missing_or_partial_inputs"]}
        if review_required
        else {},
        profile_confidence=confidence,
        core_payment_anchors_json=[],
        risk_flags_json=risk_flags,
        param_profile_status="partial",
        claim_fact_status="partial",
        comment_profile_status="partial",
        market_profile_status="partial",
        semantic_profile_status="partial",
        semantic_market_status="ready",
        claim_value_status="partial",
    )
