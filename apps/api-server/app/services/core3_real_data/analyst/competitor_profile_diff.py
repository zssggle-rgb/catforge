"""Explainable, deterministic SKU competitor-profile version diff."""

from __future__ import annotations

from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    MaterializedCompetitorProfile,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileReadBundle,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_quality import (
    ProfileQualityInput,
)
from app.services.core3_real_data.analyst.competitor_profile_quality_schemas import (
    CandidateDiffSnapshot,
    CandidateStateChange,
    CompetitorProfileVersionDiff,
    MarketComparisonChange,
    MarketDiffSnapshot,
    ProfileStateSnapshot,
    RelationDiffSnapshot,
    RelationStateChange,
    SelectionDiffSnapshot,
    SelectionStateChange,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileDraftBundle,
)
from app.services.core3_real_data.hash_utils import stable_hash


DIFF_HASH_VERSION = "competitor_profile_version_diff_v1"
SECTION_HASH_VERSION = "competitor_profile_diff_section_v1"
PROFILE_SECTION_LABELS = {
    "target_market_summary": "本品市场表现",
    "candidate_status_counts": "候选构成",
    "relation_status_counts": "竞品关系构成",
    "key_competitor_summary": "重点竞品",
    "competitive_advantages": "本品竞争优势",
    "substitutable_values": "容易被替代的用户价值",
    "price_scale_pressures": "价格与销量压力",
    "same_brand_findings": "同品牌产品线关系",
    "configuration_decisions": "配置跟进判断",
    "no_conclusion_reason": "无结论原因",
    "source_lineage": "数据来源",
    "qa_index": "可回答问题范围",
    "evidence_refs": "证据",
    "limitations": "结论边界",
    "review_status": "复核状态",
    "profile_state": "画像结论状态",
}


class CompetitorProfileDiffError(ValueError):
    """Raised when two profiles do not share a comparable SKU scope."""


class CompetitorProfileDiffService:
    """Compare two saved/materialized SKU profiles without recomputing them."""

    def diff_profiles(
        self,
        *,
        from_version: CompetitorProfileVersionRecord,
        from_profile: ProfileQualityInput,
        to_version: CompetitorProfileVersionRecord,
        to_profile: ProfileQualityInput,
    ) -> CompetitorProfileVersionDiff:
        before, before_version_id = _draft_and_version_id(from_profile)
        after, after_version_id = _draft_and_version_id(to_profile)
        _assert_diff_scope(
            from_version,
            before,
            before_version_id,
            to_version,
            after,
            after_version_id,
        )

        before_pairs = {row.candidate.sku_code: row for row in before.pairs}
        after_pairs = {row.candidate.sku_code: row for row in after.pairs}
        before_codes = set(before_pairs)
        after_codes = set(after_pairs)
        candidate_added = sorted(after_codes - before_codes)
        candidate_removed = sorted(before_codes - after_codes)
        shared_codes = sorted(before_codes & after_codes)

        candidate_changes: list[CandidateStateChange] = []
        relation_changes: list[RelationStateChange] = []
        market_changes: list[MarketComparisonChange] = []
        for code in shared_codes:
            old_pair = before_pairs[code]
            new_pair = after_pairs[code]
            old_candidate = _candidate_snapshot(old_pair)
            new_candidate = _candidate_snapshot(new_pair)
            if old_candidate != new_candidate:
                candidate_changes.append(
                    CandidateStateChange(
                        candidate_sku_code=code,
                        before=old_candidate,
                        after=new_candidate,
                    )
                )

            old_relations = {
                row.relation_code: row for row in old_pair.relation_assessments
            }
            new_relations = {
                row.relation_code: row for row in new_pair.relation_assessments
            }
            if set(old_relations) != set(new_relations):
                raise CompetitorProfileDiffError(
                    f"pair {code} does not contain the same seven relation codes"
                )
            for relation_code in sorted(old_relations):
                old_relation = _relation_snapshot(old_relations[relation_code])
                new_relation = _relation_snapshot(new_relations[relation_code])
                if old_relation != new_relation:
                    relation_changes.append(
                        RelationStateChange(
                            candidate_sku_code=code,
                            relation_code=relation_code,
                            before=old_relation,
                            after=new_relation,
                        )
                    )

            old_market = _market_snapshot(old_pair.market_comparison)
            new_market = _market_snapshot(new_pair.market_comparison)
            if old_market != new_market:
                market_changes.append(
                    MarketComparisonChange(
                        candidate_sku_code=code,
                        before=old_market,
                        after=new_market,
                    )
                )

        before_selections = {row.candidate_sku_code: row for row in before.selections}
        after_selections = {row.candidate_sku_code: row for row in after.selections}
        before_selected = set(before_selections)
        after_selected = set(after_selections)
        selection_added = sorted(after_selected - before_selected)
        selection_removed = sorted(before_selected - after_selected)
        selection_changes = []
        for code in sorted(before_selected & after_selected):
            old_selection = _selection_snapshot(before_selections[code])
            new_selection = _selection_snapshot(after_selections[code])
            if old_selection != new_selection:
                selection_changes.append(
                    SelectionStateChange(
                        candidate_sku_code=code,
                        before=old_selection,
                        after=new_selection,
                    )
                )

        profile_state_before = _profile_state(before)
        profile_state_after = _profile_state(after)
        changed_sections = _changed_profile_sections(before, after)
        if profile_state_before != profile_state_after:
            changed_sections.append("profile_state")
        changed_sections = sorted(set(changed_sections))

        from_result_hash = before.profile.result_hash
        to_result_hash = after.profile.result_hash
        semantic_change_count = sum(
            (
                len(candidate_added),
                len(candidate_removed),
                len(candidate_changes),
                len(relation_changes),
                len(market_changes),
                len(selection_added),
                len(selection_removed),
                len(selection_changes),
                len(changed_sections),
            )
        )
        has_changes = bool(semantic_change_count or from_result_hash != to_result_hash)
        summaries = _change_summary(
            candidate_added=len(candidate_added),
            candidate_removed=len(candidate_removed),
            candidate_changed=len(candidate_changes),
            relation_changed=len(relation_changes),
            market_changed=len(market_changes),
            selection_added=len(selection_added),
            selection_removed=len(selection_removed),
            selection_changed=len(selection_changes),
            changed_sections=changed_sections,
            hashes_changed=from_result_hash != to_result_hash,
        )
        payload = {
            "project_id": from_version.project_id,
            "category_code": from_version.category_code,
            "target_sku_code": before.profile.target_sku_code,
            "from_competitor_profile_version_id": (
                from_version.competitor_profile_version_id
            ),
            "to_competitor_profile_version_id": (
                to_version.competitor_profile_version_id
            ),
            "from_profile_version": from_version.profile_version,
            "to_profile_version": to_version.profile_version,
            "candidate_added": candidate_added,
            "candidate_removed": candidate_removed,
            "candidate_changes": [
                row.model_dump(mode="python") for row in candidate_changes
            ],
            "relation_changes": [
                row.model_dump(mode="python") for row in relation_changes
            ],
            "market_changes": [row.model_dump(mode="python") for row in market_changes],
            "selection_added": selection_added,
            "selection_removed": selection_removed,
            "selection_changes": [
                row.model_dump(mode="python") for row in selection_changes
            ],
            "profile_state_before": profile_state_before.model_dump(mode="python"),
            "profile_state_after": profile_state_after.model_dump(mode="python"),
            "changed_profile_sections": changed_sections,
            "has_changes": has_changes,
            "change_summary_cn": summaries,
            "from_result_hash": from_result_hash,
            "to_result_hash": to_result_hash,
        }
        return CompetitorProfileVersionDiff(
            **payload,
            diff_hash=stable_hash(payload, version=DIFF_HASH_VERSION),
        )


def _draft_and_version_id(
    value: ProfileQualityInput,
) -> tuple[CompetitorProfileDraftBundle, str | None]:
    if isinstance(value, MaterializedCompetitorProfile):
        return value.draft, None
    if isinstance(value, CompetitorProfileReadBundle):
        return (
            CompetitorProfileDraftBundle(
                profile=value.profile.profile_payload,
                pairs=[row.pair_payload for row in value.pairs],
                selections=[row.selection_payload for row in value.selections],
            ),
            value.version.competitor_profile_version_id,
        )
    if isinstance(value, CompetitorProfileDraftBundle):
        return value, None
    raise CompetitorProfileDiffError(
        f"unsupported competitor profile diff input: {type(value).__name__}"
    )


def _assert_diff_scope(
    from_version: CompetitorProfileVersionRecord,
    before: CompetitorProfileDraftBundle,
    before_version_id: str | None,
    to_version: CompetitorProfileVersionRecord,
    after: CompetitorProfileDraftBundle,
    after_version_id: str | None,
) -> None:
    if before_version_id not in {
        None,
        from_version.competitor_profile_version_id,
    }:
        raise CompetitorProfileDiffError(
            "from profile readback does not match from version"
        )
    if after_version_id not in {None, to_version.competitor_profile_version_id}:
        raise CompetitorProfileDiffError(
            "to profile readback does not match to version"
        )
    expected = (
        from_version.project_id,
        from_version.category_code,
        before.profile.target_sku_code,
    )
    actual = (
        to_version.project_id,
        to_version.category_code,
        after.profile.target_sku_code,
    )
    if expected != actual:
        raise CompetitorProfileDiffError(
            "profile diff cannot cross project, category, or target SKU scope"
        )
    for version, draft in ((from_version, before), (to_version, after)):
        if (
            draft.profile.project_id != version.project_id
            or draft.profile.category_code != version.category_code
        ):
            raise CompetitorProfileDiffError(
                "profile payload does not match its version scope"
            )


def _candidate_snapshot(pair) -> CandidateDiffSnapshot:
    return CandidateDiffSnapshot(
        candidate_status=pair.candidate_status,
        competitor_member=pair.competitor_member,
        reference_member=pair.reference_member,
        selected=pair.selected,
        confidence_level=pair.confidence_level,
    )


def _relation_snapshot(relation) -> RelationDiffSnapshot:
    return RelationDiffSnapshot(
        status=relation.status,
        is_primary=relation.is_primary,
        confidence_level=relation.confidence_level,
        eligible_question_codes=sorted(set(relation.eligible_question_codes)),
    )


def _market_snapshot(market) -> MarketDiffSnapshot:
    return MarketDiffSnapshot(
        comparability_status=market.comparability_status,
        target_weighted_price=market.target_weighted_price,
        candidate_weighted_price=market.candidate_weighted_price,
        price_gap_pct=market.price_gap_pct,
        target_avg_weekly_volume=market.target_avg_weekly_volume,
        candidate_avg_weekly_volume=market.candidate_avg_weekly_volume,
        weekly_volume_ratio=market.weekly_volume_ratio,
    )


def _selection_snapshot(selection) -> SelectionDiffSnapshot:
    return SelectionDiffSnapshot(
        selection_rank=selection.selection_rank,
        primary_decision_topic=selection.primary_decision_topic,
        primary_relation_code=selection.primary_relation_code,
        confidence_level=selection.confidence_level,
    )


def _profile_state(draft: CompetitorProfileDraftBundle) -> ProfileStateSnapshot:
    profile = draft.profile
    return ProfileStateSnapshot(
        analysis_state=profile.analysis_state,
        conclusion_state=profile.conclusion_state,
        freshness_status=profile.freshness_status,
        profile_confidence=profile.profile_confidence,
        review_required=profile.review_required,
    )


def _changed_profile_sections(
    before: CompetitorProfileDraftBundle,
    after: CompetitorProfileDraftBundle,
) -> list[str]:
    old = before.profile
    new = after.profile
    sections = {
        "target_market_summary": (
            old.target_market_summary,
            new.target_market_summary,
        ),
        "candidate_status_counts": (
            old.candidate_status_counts,
            new.candidate_status_counts,
        ),
        "relation_status_counts": (
            old.relation_status_counts,
            new.relation_status_counts,
        ),
        "key_competitor_summary": (
            old.key_competitor_summary,
            new.key_competitor_summary,
        ),
        "competitive_advantages": (
            old.competitive_advantages,
            new.competitive_advantages,
        ),
        "substitutable_values": (
            old.substitutable_values,
            new.substitutable_values,
        ),
        "price_scale_pressures": (
            old.price_scale_pressures,
            new.price_scale_pressures,
        ),
        "same_brand_findings": (
            old.same_brand_findings,
            new.same_brand_findings,
        ),
        "configuration_decisions": (
            old.configuration_decisions,
            new.configuration_decisions,
        ),
        "no_conclusion_reason": (
            old.no_conclusion_reason,
            new.no_conclusion_reason,
        ),
        "source_lineage": (old.source_lineage, new.source_lineage),
        "qa_index": (old.qa_index, new.qa_index),
        "evidence_refs": (old.evidence_refs, new.evidence_refs),
        "limitations": (old.limitations, new.limitations),
        "review_status": (old.review_status, new.review_status),
    }
    return sorted(
        name
        for name, (old_value, new_value) in sections.items()
        if stable_hash(old_value, version=SECTION_HASH_VERSION)
        != stable_hash(new_value, version=SECTION_HASH_VERSION)
    )


def _change_summary(
    *,
    candidate_added: int,
    candidate_removed: int,
    candidate_changed: int,
    relation_changed: int,
    market_changed: int,
    selection_added: int,
    selection_removed: int,
    selection_changed: int,
    changed_sections: list[str],
    hashes_changed: bool,
) -> list[str]:
    summaries: list[str] = []
    if candidate_added or candidate_removed or candidate_changed:
        summaries.append(
            "候选范围变化："
            f"新增 {candidate_added} 款、移除 {candidate_removed} 款、"
            f"状态变化 {candidate_changed} 款。"
        )
    if relation_changed:
        summaries.append(f"竞品关系变化 {relation_changed} 项。")
    if market_changed:
        summaries.append(f"量价表现变化 {market_changed} 款。")
    if selection_added or selection_removed or selection_changed:
        summaries.append(
            "重点竞品变化："
            f"新增 {selection_added} 款、移除 {selection_removed} 款、"
            f"排序或角色变化 {selection_changed} 款。"
        )
    if changed_sections:
        summaries.append(
            "主画像变化："
            + "、".join(
                PROFILE_SECTION_LABELS.get(code, code) for code in changed_sections
            )
            + "。"
        )
    if not summaries and hashes_changed:
        summaries.append(
            "结果哈希发生变化，但候选、关系、量价、重点选择和主画像业务字段未变化。"
        )
    if not summaries:
        summaries.append("两个版本的竞品画像业务结论一致。")
    return summaries


__all__ = [
    "DIFF_HASH_VERSION",
    "PROFILE_SECTION_LABELS",
    "SECTION_HASH_VERSION",
    "CompetitorProfileDiffError",
    "CompetitorProfileDiffService",
]
