from __future__ import annotations

import pytest

from app.services.core3_real_data.analyst.competitor_profile_diff import (
    CompetitorProfileDiffError,
    CompetitorProfileDiffService,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileDraftBundle,
)
from tests.core3_real_data.test_competitor_profile_quality import (
    _draft_bundle,
    _version,
)


def _changed_draft(*, reverse_relations: bool = False) -> CompetitorProfileDraftBundle:
    raw = _draft_bundle("TV-T1", "TV-C1").model_dump(mode="python")
    profile = raw["profile"]
    pair = raw["pairs"][0]
    selection = raw["selections"][0]

    pair["candidate_status"] = "limited"
    pair["confidence_level"] = "medium"
    pair["result_hash"] = "pair-result-changed"
    relation = next(
        row
        for row in pair["relation_assessments"]
        if row["relation_code"] == "direct_substitute"
    )
    relation["status"] = "limited"
    relation["confidence_level"] = "medium"
    market = pair["market_comparison"]
    market["candidate_weighted_price"] = "4500"
    market["price_gap"] = "-500"
    market["price_gap_pct"] = "-0.1000"
    market["result_hash"] = "market-hash-changed"
    if reverse_relations:
        pair["relation_assessments"] = list(reversed(pair["relation_assessments"]))

    selection["primary_decision_topic"] = "price_scale_pressure"
    selection["covered_decision_topics"] = [
        "price_scale_pressure",
        "purchase_choice",
        "value_route",
    ]
    selection["confidence_level"] = "medium"
    selection["result_hash"] = "selection-result-changed"
    profile["key_competitor_summary"][0]["primary_decision_topic"] = (
        "price_scale_pressure"
    )
    profile["candidate_status_counts"] = {"limited": 1}
    profile["analysis_state"] = "partial"
    profile["review_required"] = True
    profile["review_status"] = "review_required"
    profile["configuration_decisions"] = [
        {"decision_cn": "优先补强用户能直接感知的画质表现。"}
    ]
    profile["result_hash"] = "profile-result-changed"
    return CompetitorProfileDraftBundle(**raw)


def test_diff_explains_relation_market_selection_and_profile_changes() -> None:
    before = _draft_bundle("TV-T1", "TV-C1")
    after = _changed_draft()
    service = CompetitorProfileDiffService()
    result = service.diff_profiles(
        from_version=_version(["TV-T1"], profile_version="cp-before"),
        from_profile=before,
        to_version=_version(["TV-T1"], profile_version="cp-after"),
        to_profile=after,
    )
    repeated = service.diff_profiles(
        from_version=_version(["TV-T1"], profile_version="cp-before"),
        from_profile=before,
        to_version=_version(["TV-T1"], profile_version="cp-after"),
        to_profile=_changed_draft(reverse_relations=True),
    )

    assert result.has_changes is True
    assert [row.candidate_sku_code for row in result.candidate_changes] == ["TV-C1"]
    assert [row.relation_code for row in result.relation_changes] == [
        "direct_substitute"
    ]
    assert [row.candidate_sku_code for row in result.market_changes] == ["TV-C1"]
    assert [row.candidate_sku_code for row in result.selection_changes] == ["TV-C1"]
    assert {
        "candidate_status_counts",
        "configuration_decisions",
        "key_competitor_summary",
        "profile_state",
    }.issubset(result.changed_profile_sections)
    assert any("竞品关系变化" in row for row in result.change_summary_cn)
    assert "candidate_status_counts" not in "".join(result.change_summary_cn)
    assert "候选构成" in "".join(result.change_summary_cn)
    assert result.diff_hash == repeated.diff_hash


def test_diff_reports_candidate_and_selection_add_remove() -> None:
    result = CompetitorProfileDiffService().diff_profiles(
        from_version=_version(["TV-T1"], profile_version="cp-before"),
        from_profile=_draft_bundle("TV-T1", "TV-C1"),
        to_version=_version(["TV-T1"], profile_version="cp-after"),
        to_profile=_draft_bundle("TV-T1", "TV-C2"),
    )

    assert result.candidate_added == ["TV-C2"]
    assert result.candidate_removed == ["TV-C1"]
    assert result.selection_added == ["TV-C2"]
    assert result.selection_removed == ["TV-C1"]
    assert any("候选范围变化" in row for row in result.change_summary_cn)


def test_relation_input_order_does_not_create_false_diff() -> None:
    before = _draft_bundle("TV-T1", "TV-C1")
    raw = before.model_dump(mode="python")
    raw["pairs"][0]["relation_assessments"] = list(
        reversed(raw["pairs"][0]["relation_assessments"])
    )
    reordered = CompetitorProfileDraftBundle(**raw)
    result = CompetitorProfileDiffService().diff_profiles(
        from_version=_version(["TV-T1"], profile_version="cp-before"),
        from_profile=before,
        to_version=_version(["TV-T1"], profile_version="cp-after"),
        to_profile=reordered,
    )

    assert result.has_changes is False
    assert result.relation_changes == []
    assert result.change_summary_cn == ["两个版本的竞品画像业务结论一致。"]


def test_hash_only_change_is_reported_without_inventing_business_change() -> None:
    before = _draft_bundle("TV-T1", "TV-C1")
    raw = before.model_dump(mode="python")
    raw["profile"]["result_hash"] = "profile-hash-only-change"
    after = CompetitorProfileDraftBundle(**raw)
    result = CompetitorProfileDiffService().diff_profiles(
        from_version=_version(["TV-T1"], profile_version="cp-before"),
        from_profile=before,
        to_version=_version(["TV-T1"], profile_version="cp-after"),
        to_profile=after,
    )

    assert result.has_changes is True
    assert result.changed_profile_sections == []
    assert result.change_summary_cn == [
        "结果哈希发生变化，但候选、关系、量价、重点选择和主画像业务字段未变化。"
    ]


def test_diff_rejects_cross_target_or_category_scope() -> None:
    with pytest.raises(CompetitorProfileDiffError, match="cannot cross"):
        CompetitorProfileDiffService().diff_profiles(
            from_version=_version(["TV-T1"], profile_version="cp-before"),
            from_profile=_draft_bundle("TV-T1", "TV-C1"),
            to_version=_version(["TV-T2"], profile_version="cp-after"),
            to_profile=_draft_bundle("TV-T2", "TV-C2"),
        )
