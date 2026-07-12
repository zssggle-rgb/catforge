"""Independent, anchor-scoped purchase pressure classification for M12D."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    M12DEvidenceDomain,
    M12DIssueSeverity,
    M12DPurchasePressureLevel,
    M12DPurchasePressureType,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DComparisonLimitation,
    M12DProfileScoreResult,
    M12DPurchasePressureTag,
    M12DScoredPurchaseReasonAnchor,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)


PRESSURE_LEVEL_ORDER = {
    M12DPurchasePressureLevel.UNASSESSED.value: -1,
    M12DPurchasePressureLevel.NONE.value: 0,
    M12DPurchasePressureLevel.LOW.value: 1,
    M12DPurchasePressureLevel.MEDIUM.value: 2,
    M12DPurchasePressureLevel.HIGH.value: 3,
    M12DPurchasePressureLevel.CRITICAL.value: 4,
}
M12C_HEADWIND_ROLES = {
    "drag_factor",
    "high_price_competitor_intercept",
    "weak_user_perception_claim",
}
M12C_HIGH_HEADWIND_ROLES = {
    "drag_factor",
    "high_price_competitor_intercept",
}
MARKET_UNCERTAINTY_CODES = {
    "market_sample_insufficient",
    "m11d_relation_confidence_low",
}
MARKET_UNCERTAINTY_PREFIXES = (
    "market_pool_",
    "price_band_sample_",
    "size_pool_",
)


# These mappings bind M12D reasons to the published M05C business dimensions.
# TV and AC deliberately have separate maps even when pressure types are shared.
COMMENT_SCOPE_BY_REASON: dict[str, dict[str, frozenset[tuple[str, str | None]]]] = {
    "TV": {
        "picture_upgrade_justifies_price": frozenset({("picture_screen_experience", None)}),
        "low_price_core_experience_intact": frozenset({("price_value_perception", None)}),
        "same_price_core_config_gain": frozenset({("price_value_perception", None)}),
        "same_size_picture_step_up": frozenset({("picture_screen_experience", None)}),
        "worth_paying_more_for_experience_upgrade": frozenset({("picture_screen_experience", None)}),
        "av_user_willing_to_pay_for_picture": frozenset({("picture_screen_experience", None)}),
        "gaming_device_fit_reduces_risk": frozenset(
            {
                ("gaming_motion_experience", None),
                ("use_case_signal", "use_gaming_sports"),
            }
        ),
        "sports_motion_stability": frozenset(
            {
                ("gaming_motion_experience", None),
                ("use_case_signal", "use_gaming_sports"),
            }
        ),
        "big_screen_cinema_substitution": frozenset(
            {
                ("use_case_signal", "use_living_room_cinema"),
                ("appearance_installation_space", "appearance_size_fit"),
                ("audio_cinema_experience", None),
            }
        ),
        "living_room_upgrade_one_step": frozenset(
            {
                ("use_case_signal", "use_living_room_cinema"),
                ("appearance_installation_space", "appearance_size_fit"),
                ("audio_cinema_experience", None),
            }
        ),
        "family_long_watch_comfort_assurance": frozenset(
            {
                ("picture_screen_experience", "picture_eye_care_reflection"),
                ("use_case_signal", "use_bedroom"),
                ("audience_signal", "audience_child_family"),
                ("audience_signal", "audience_senior"),
            }
        ),
        "family_operation_less_friction": frozenset({("system_interaction_experience", None)}),
        "new_home_aesthetic_fit": frozenset({("appearance_installation_space", None)}),
    },
    "AC": {
        "room_size_capacity_match_reduces_risk": frozenset(
            {
                ("temperature_effect_experience", None),
                ("appearance_installation_space", "space_fit_area"),
            }
        ),
        "large_space_one_step_cooling_heating": frozenset(
            {
                ("temperature_effect_experience", None),
                ("airflow_comfort_experience", "airflow_volume_coverage"),
                ("use_case_signal", "use_living_room_large"),
            }
        ),
        "cooling_heating_performance_justifies_price": frozenset(
            {
                ("temperature_effect_experience", None),
                ("price_value_perception", None),
            }
        ),
        "long_term_energy_saving_offsets_price": frozenset(
            {
                ("energy_cost_experience", None),
                ("price_value_perception", None),
            }
        ),
        "same_price_efficiency_capacity_gain": frozenset(
            {
                ("price_value_perception", None),
                ("energy_cost_experience", None),
                ("temperature_effect_experience", None),
            }
        ),
        "low_price_core_ac_experience_intact": frozenset(
            {
                ("price_value_perception", None),
                ("temperature_effect_experience", None),
            }
        ),
        "sleep_room_quiet_comfort_assurance": frozenset(
            {
                ("noise_sleep_experience", None),
                ("use_case_signal", "use_bedroom_sleep"),
            }
        ),
        "elderly_child_soft_wind_comfort": frozenset(
            {
                ("airflow_comfort_experience", "soft_wind_no_direct"),
                ("audience_signal", "audience_senior_parent"),
                ("audience_signal", "audience_child_baby"),
                ("audience_signal", "audience_family"),
            }
        ),
        "fresh_air_health_reduces_stuffy_risk": frozenset({("health_clean_air_experience", None)}),
        "humidity_dehumidification_reassurance": frozenset({("health_clean_air_experience", None)}),
        "self_cleaning_reduces_maintenance_risk": frozenset(
            {("health_clean_air_experience", "self_cleaning")}
        ),
        "small_room_installation_fit": frozenset(
            {
                ("appearance_installation_space", None),
                ("use_case_signal", "use_bedroom_sleep"),
            }
        ),
        "smart_remote_control_less_friction": frozenset({("smart_control_experience", None)}),
    },
}


# M12C evidence patterns can match generic role words. Pressure therefore uses
# an explicit category/reason claim scope and never inherits every row matched
# by a generic role such as sales_driver_estimated.
M12C_CLAIM_SCOPE_BY_REASON: dict[str, dict[str, frozenset[str]]] = {
    "TV": {
        "picture_upgrade_justifies_price": frozenset(
            {
                "tv_claim_hdr_high_brightness",
                "tv_claim_local_dimming",
                "tv_claim_miniled_display",
                "tv_claim_picture_engine_ai",
                "tv_claim_qd_miniled_display",
                "tv_claim_rgb_miniled_display",
                "tv_claim_wide_color_accuracy",
            }
        ),
        "low_price_core_experience_intact": frozenset(
            {
                "tv_claim_casting_connectivity",
                "tv_claim_chip_performance",
                "tv_claim_hdr_high_brightness",
                "tv_claim_high_refresh_rate",
                "tv_claim_memory_storage",
                "tv_claim_picture_engine_ai",
            }
        ),
        "same_price_core_config_gain": frozenset(
            {
                "tv_claim_casting_connectivity",
                "tv_claim_chip_performance",
                "tv_claim_gaming_low_latency",
                "tv_claim_hdmi21_connectivity",
                "tv_claim_high_refresh_rate",
                "tv_claim_memory_storage",
                "tv_claim_picture_engine_ai",
            }
        ),
        "same_size_picture_step_up": frozenset(
            {
                "tv_claim_hdr_high_brightness",
                "tv_claim_local_dimming",
                "tv_claim_miniled_display",
                "tv_claim_picture_engine_ai",
                "tv_claim_qd_miniled_display",
                "tv_claim_rgb_miniled_display",
                "tv_claim_wide_color_accuracy",
            }
        ),
        "worth_paying_more_for_experience_upgrade": frozenset(
            {
                "tv_claim_dolby_audio_video",
                "tv_claim_gaming_low_latency",
                "tv_claim_hdr_high_brightness",
                "tv_claim_hdmi21_connectivity",
                "tv_claim_high_refresh_rate",
                "tv_claim_local_dimming",
                "tv_claim_miniled_display",
                "tv_claim_picture_engine_ai",
                "tv_claim_qd_miniled_display",
                "tv_claim_rgb_miniled_display",
                "tv_claim_theater_scene",
                "tv_claim_wide_color_accuracy",
            }
        ),
        "av_user_willing_to_pay_for_picture": frozenset(
            {
                "tv_claim_dolby_audio_video",
                "tv_claim_hdr_high_brightness",
                "tv_claim_local_dimming",
                "tv_claim_miniled_display",
                "tv_claim_picture_engine_ai",
                "tv_claim_qd_miniled_display",
                "tv_claim_rgb_miniled_display",
                "tv_claim_theater_scene",
                "tv_claim_wide_color_accuracy",
            }
        ),
        "gaming_device_fit_reduces_risk": frozenset(
            {
                "tv_claim_gaming_low_latency",
                "tv_claim_hdmi21_connectivity",
                "tv_claim_high_refresh_rate",
            }
        ),
        "sports_motion_stability": frozenset(
            {
                "tv_claim_gaming_low_latency",
                "tv_claim_high_refresh_rate",
            }
        ),
        "big_screen_cinema_substitution": frozenset(
            {
                "tv_claim_dolby_audio_video",
                "tv_claim_theater_scene",
            }
        ),
        "living_room_upgrade_one_step": frozenset(
            {
                "tv_claim_dolby_audio_video",
                "tv_claim_theater_scene",
            }
        ),
        "family_operation_less_friction": frozenset(
            {
                "tv_claim_ai_large_model",
                "tv_claim_camera_interaction",
                "tv_claim_casting_connectivity",
                "tv_claim_smart_home_iot",
                "tv_claim_voice_control",
            }
        ),
        "new_home_aesthetic_fit": frozenset(
            {
                "tv_claim_flush_wall_mount",
                "tv_claim_full_screen_design",
                "tv_claim_premium_material_design",
                "tv_claim_slim_body",
            }
        ),
    },
    "AC": {
        "room_size_capacity_match_reduces_risk": frozenset(
            {
                "ac_claim_fast_cooling_heating",
                "ac_claim_installation_space_design",
                "ac_claim_large_airflow_coverage",
            }
        ),
        "large_space_one_step_cooling_heating": frozenset(
            {
                "ac_claim_fast_cooling_heating",
                "ac_claim_large_airflow_coverage",
            }
        ),
        "cooling_heating_performance_justifies_price": frozenset(
            {
                "ac_claim_fast_cooling_heating",
                "ac_claim_large_airflow_coverage",
            }
        ),
        "long_term_energy_saving_offsets_price": frozenset(
            {"ac_claim_energy_efficiency_apf"}
        ),
        "same_price_efficiency_capacity_gain": frozenset(
            {
                "ac_claim_energy_efficiency_apf",
                "ac_claim_fast_cooling_heating",
                "ac_claim_large_airflow_coverage",
            }
        ),
        "low_price_core_ac_experience_intact": frozenset(
            {
                "ac_claim_energy_efficiency_apf",
                "ac_claim_fast_cooling_heating",
                "ac_claim_large_airflow_coverage",
            }
        ),
        "sleep_room_quiet_comfort_assurance": frozenset(
            {"ac_claim_soft_wind_no_direct"}
        ),
        "elderly_child_soft_wind_comfort": frozenset(
            {"ac_claim_soft_wind_no_direct"}
        ),
        "fresh_air_health_reduces_stuffy_risk": frozenset(
            {"ac_claim_fresh_air", "ac_claim_purification_antibacterial"}
        ),
        "self_cleaning_reduces_maintenance_risk": frozenset(
            {"ac_claim_self_cleaning"}
        ),
        "small_room_installation_fit": frozenset(
            {"ac_claim_installation_space_design"}
        ),
        "smart_remote_control_less_friction": frozenset(
            {"ac_claim_smart_app_voice_iot"}
        ),
    },
}


class PurchasePressureClassifier:
    """Classify pressure without changing legacy evidence score or anchor role."""

    def classify(
        self,
        *,
        candidate: M12DAnchorCandidate,
        context: M12DSkuPurchaseReasonContext,
        scored_anchor: M12DScoredPurchaseReasonAnchor,
    ) -> M12DScoredPurchaseReasonAnchor:
        pressure_tags: list[M12DPurchasePressureTag] = []
        limitations: list[M12DComparisonLimitation] = []

        comment_tags, comment_limitations = _comment_pressure(candidate, context)
        pressure_tags.extend(comment_tags)
        limitations.extend(comment_limitations)

        m12c_tags, m12c_limitations = _m12c_pressure(candidate, context)
        pressure_tags.extend(m12c_tags)
        limitations.extend(m12c_limitations)

        market_tags, market_limitations = _market_pressure(candidate, context)
        pressure_tags.extend(market_tags)
        limitations.extend(market_limitations)

        pressure_tags.extend(_objective_falsification(candidate, context))
        pressure_tags = _dedupe_pressure_tags(pressure_tags)
        limitations = _dedupe_limitations(limitations)
        pressure_level = _highest_pressure_level(pressure_tags)
        pressure_summary = _pressure_summary(pressure_tags)

        return scored_anchor.model_copy(
            update={
                "pressure_level": pressure_level,
                "pressure_tags_json": pressure_tags,
                "pressure_summary_cn": pressure_summary,
                "comparison_limitations_json": limitations,
            }
        )

    def summarize_profile(self, result: M12DProfileScoreResult) -> M12DProfileScoreResult:
        level_counts = Counter(str(anchor.pressure_level) for anchor in result.scored_anchors)
        type_counts = Counter(
            str(tag.pressure_type)
            for anchor in result.scored_anchors
            for tag in anchor.pressure_tags_json
        )
        pressured = [
            anchor.anchor_code
            for anchor in result.scored_anchors
            if str(anchor.pressure_level)
            not in {
                M12DPurchasePressureLevel.UNASSESSED.value,
                M12DPurchasePressureLevel.NONE.value,
            }
        ]
        highest = _highest_level_value(level_counts)
        limitations = _dedupe_limitations(
            limitation
            for anchor in result.scored_anchors
            for limitation in anchor.comparison_limitations_json
        )
        return result.model_copy(
            update={
                "pressure_summary_json": {
                    "highest_pressure_level": highest,
                    "pressured_anchor_codes": pressured,
                    "anchor_level_counts": dict(sorted(level_counts.items())),
                    "pressure_type_counts": dict(sorted(type_counts.items())),
                    "summary_cn": (
                        f"{len(pressured)} 个购买理由存在明确阻力，最高为{_level_cn(highest)}。"
                        if pressured
                        else "当前未观察到明确购买阻力。"
                    ),
                },
                "comparison_limitations_json": limitations,
            }
        )


def _comment_pressure(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> tuple[list[M12DPurchasePressureTag], list[M12DComparisonLimitation]]:
    category = str(context.product_category).strip().upper()
    scope = COMMENT_SCOPE_BY_REASON.get(category, {}).get(candidate.anchor_code, frozenset())
    scope_by_dimension: dict[str, set[str | None]] = defaultdict(set)
    for dimension_code, subdimension_code in scope:
        scope_by_dimension[dimension_code].add(subdimension_code)
    records = [
        record
        for record in context.comment_profile.records
        if str(record.get("table_name") or "") == "core3_comment_fact_atom"
    ]
    dimension_summary = _comment_dimension_summary(context)
    tags: list[M12DPurchasePressureTag] = []
    limitations: list[M12DComparisonLimitation] = []
    aligned = [record for record in records if _comment_record_aligns(scope, record)]
    for dimension_code, target_subdimensions in sorted(scope_by_dimension.items()):
        summary = dimension_summary.get(dimension_code)
        if not isinstance(summary, Mapping):
            continue
        observed_subdimensions = {
            str(code)
            for code in summary.get("subdimension_codes") or []
            if str(code)
        }
        accepts_whole_dimension = None in target_subdimensions
        exact_subdimensions = {
            str(code) for code in target_subdimensions if code is not None
        }
        aggregate_is_scoped = accepts_whole_dimension or (
            bool(observed_subdimensions)
            and observed_subdimensions.issubset(exact_subdimensions)
        )
        if aggregate_is_scoped:
            counts = _polarity_counts(summary.get("polarity_counts"))
            refs = _dedupe_source_refs(
                [
                    *_comment_dimension_source_refs(context, dimension_code, summary),
                    *_record_source_refs(
                        "M05C",
                        (
                            record
                            for record in aligned
                            if str(record.get("dimension_code") or "") == dimension_code
                        ),
                    ),
                ]
            )
            aspect = (
                next(iter(exact_subdimensions))
                if not accepts_whole_dimension and len(exact_subdimensions) == 1
                else dimension_code
            )
            tags.extend(
                _comment_count_pressure_tags(
                    candidate=candidate,
                    aspect=aspect,
                    counts=counts,
                    source_refs=refs,
                )
            )
            continue

        # The stored M05C aggregate is dimension-level. Do not infer a
        # subdimension ratio from the first expanded examples.
        scoped_records = [
            record
            for record in aligned
            if str(record.get("dimension_code") or "") == dimension_code
        ]
        if scoped_records and _comment_records_complete(context, records):
            grouped = _group_comment_records(scoped_records)
            for aspect, rows in sorted(grouped.items()):
                tags.extend(
                    _comment_count_pressure_tags(
                        candidate=candidate,
                        aspect=aspect,
                        counts=_record_polarity_counts(rows),
                        source_refs=_record_source_refs("M05C", rows),
                    )
                )
            continue
        if scoped_records:
            negative_rows = [
                row
                for row in scoped_records
                if str(row.get("polarity") or "").lower() in {"negative", "mixed"}
            ]
            if negative_rows:
                tags.append(
                    _pressure_tag(
                        pressure_type=M12DPurchasePressureType.LOCALIZED_NEGATIVE,
                        pressure_level=M12DPurchasePressureLevel.LOW,
                        candidate=candidate,
                        aspect=dimension_code,
                        positive=0,
                        negative=sum(
                            str(row.get("polarity") or "").lower() == "negative"
                            for row in negative_rows
                        ),
                        mixed=sum(
                            str(row.get("polarity") or "").lower() == "mixed"
                            for row in negative_rows
                        ),
                        dominance="unknown",
                        summary_cn=(
                            f"{candidate.anchor_cn}的相关评论样例中存在负面体验，"
                            "但当前不能据此判断完整占比。"
                        ),
                        source_refs=_record_source_refs("M05C", negative_rows),
                    )
                )
        limitations.append(
            M12DComparisonLimitation(
                limitation_code="comment_subdimension_distribution_unavailable",
                scope="anchor",
                limits_comparison=True,
                summary_cn="评论画像只有维度级完整分布，当前不能量化该购买理由指定子维度的正负占比。",
                source_refs=_comment_dimension_source_refs(
                    context,
                    dimension_code,
                    summary,
                ),
            )
        )

    if not dimension_summary:
        grouped = _group_comment_records(aligned)
        for aspect, rows in sorted(grouped.items()):
            tags.extend(
                _comment_count_pressure_tags(
                    candidate=candidate,
                    aspect=aspect,
                    counts=_record_polarity_counts(rows),
                    source_refs=_record_source_refs("M05C", rows),
                )
            )

    uses_comment = M12DEvidenceDomain.COMMENT_PERCEPTION.value in {
        str(domain) for domain in candidate.evidence_domains_json
    }
    has_comment_evidence = bool(dimension_summary or records)
    has_scoped_comment = _summary_has_scoped_comment(scope_by_dimension, dimension_summary)
    if not dimension_summary:
        has_scoped_comment = bool(aligned)
    if uses_comment and has_comment_evidence and not has_scoped_comment:
        summary_inventory_complete = bool(dimension_summary)
        if summary_inventory_complete or _comment_records_complete(context, records):
            tags.append(
                _pressure_tag(
                    pressure_type=M12DPurchasePressureType.EVIDENCE_MISALIGNMENT,
                    pressure_level=M12DPurchasePressureLevel.CRITICAL,
                    candidate=candidate,
                    aspect="comment_dimension",
                    positive=0,
                    negative=0,
                    mixed=0,
                    dominance="unknown",
                    limits_establishment=True,
                    summary_cn=f"{candidate.anchor_cn}引用的评论不属于该理由对应的用户体验方面。",
                    source_refs=(
                        _comment_profile_source_refs(context)
                        if summary_inventory_complete
                        else _record_source_refs("M05C", records)
                    ),
                )
            )
        else:
            limitations.append(
                M12DComparisonLimitation(
                    limitation_code="comment_alignment_not_fully_expanded",
                    scope="anchor",
                    limits_comparison=True,
                    summary_cn="评论明细只展开了部分样本，当前不能确认评论是否与该购买理由同维度。",
                    source_refs=_record_source_refs("M05C", records),
                )
            )
    return tags, limitations


def _comment_count_pressure_tags(
    *,
    candidate: M12DAnchorCandidate,
    aspect: str,
    counts: Mapping[str, int],
    source_refs: Sequence[M12DSourceRef],
) -> list[M12DPurchasePressureTag]:
    positive = int(counts.get("positive") or 0)
    negative = int(counts.get("negative") or 0)
    mixed = int(counts.get("mixed") or 0)
    weighted_negative = Decimal(negative) + Decimal("0.5") * Decimal(mixed)
    tags: list[M12DPurchasePressureTag] = []
    if negative > 0 and Decimal(positive) > weighted_negative:
        ratio = Decimal(negative) / Decimal(max(1, positive + negative + mixed))
        level = (
            M12DPurchasePressureLevel.LOW
            if ratio <= Decimal("0.2000")
            else M12DPurchasePressureLevel.MEDIUM
        )
        tags.append(
            _pressure_tag(
                pressure_type=M12DPurchasePressureType.LOCALIZED_NEGATIVE,
                pressure_level=level,
                candidate=candidate,
                aspect=aspect,
                positive=positive,
                negative=negative,
                mixed=mixed,
                dominance="positive",
                summary_cn=f"{candidate.anchor_cn}成立证据中，{aspect}存在少量负面体验。",
                source_refs=source_refs,
            )
        )
    if mixed > 0 or (positive > 0 and negative > 0):
        tags.append(
            _pressure_tag(
                pressure_type=M12DPurchasePressureType.MIXED_FEEDBACK,
                pressure_level=M12DPurchasePressureLevel.MEDIUM,
                candidate=candidate,
                aspect=aspect,
                positive=positive,
                negative=negative,
                mixed=mixed,
                dominance="mixed",
                summary_cn=f"{candidate.anchor_cn}在{aspect}上同时存在正向和负向反馈。",
                source_refs=source_refs,
            )
        )
    if negative > 0 and weighted_negative > Decimal(positive):
        tags.append(
            _pressure_tag(
                pressure_type=M12DPurchasePressureType.NEGATIVE_DOMINANT,
                pressure_level=M12DPurchasePressureLevel.HIGH,
                candidate=candidate,
                aspect=aspect,
                positive=positive,
                negative=negative,
                mixed=mixed,
                dominance="negative",
                summary_cn=f"{candidate.anchor_cn}在{aspect}上的负向反馈占主导。",
                source_refs=source_refs,
            )
        )
    return tags


def _m12c_pressure(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> tuple[list[M12DPurchasePressureTag], list[M12DComparisonLimitation]]:
    claim_scope = _m12c_claim_scope(context, candidate.anchor_code)
    roles_by_claim = {
        claim_code: roles
        for claim_code, roles in _anchor_claim_roles(context, candidate.anchor_code).items()
        if claim_code in claim_scope
    }
    risk_roles = {
        role
        for roles in roles_by_claim.values()
        for role in roles
        if role in M12C_HEADWIND_ROLES
    }
    issues = [
        issue
        for issue in _anchor_issues(context, "M12C", candidate.anchor_code)
        if _m12c_issue_matches_claim_scope(issue, claim_scope)
    ]
    negative_issues = [
        issue for issue in issues if str(issue.code) == "m12c_related_claim_negative"
    ]
    negative_records = _m12c_negative_records(context, claim_scope)
    negative_summary_refs = _m12c_summary_negative_refs(context, claim_scope)
    tags: list[M12DPurchasePressureTag] = []
    if negative_records or negative_summary_refs or negative_issues or risk_roles:
        level = (
            M12DPurchasePressureLevel.HIGH
            if risk_roles & M12C_HIGH_HEADWIND_ROLES
            else M12DPurchasePressureLevel.MEDIUM
        )
        record_refs = _m12c_record_refs(context, roles_by_claim)
        tags.append(
            _pressure_tag(
                pressure_type=M12DPurchasePressureType.M12C_VALUE_HEADWIND,
                pressure_level=level,
                candidate=candidate,
                aspect="claim_value_acceptance",
                positive=0,
                negative=max(
                    1,
                    len(negative_records) + len(negative_issues) + len(risk_roles),
                ),
                mixed=0,
                dominance="negative",
                summary_cn=f"{candidate.anchor_cn}存在卖点价值承接或价格解释压力。",
                source_refs=_dedupe_source_refs(
                    [
                        *record_refs,
                        *_record_source_refs("M12C", negative_records),
                        *negative_summary_refs,
                        *_issue_source_refs("M12C", negative_issues),
                    ]
                ),
            )
        )

    limitations: list[M12DComparisonLimitation] = []
    for issue in issues:
        code = str(issue.code)
        if code == "m12c_amount_not_quantifiable":
            limitations.append(
                M12DComparisonLimitation(
                    limitation_code=code,
                    scope="amount_wtp",
                    limits_comparison=True,
                    summary_cn="相关卖点可以做定性比较，但当前不能量化支付金额。",
                    source_refs=_issue_source_refs("M12C", [issue]),
                )
            )
        elif code == "m12c_relative_comparison_limited":
            limitations.append(
                M12DComparisonLimitation(
                    limitation_code=code,
                    scope="replacement",
                    limits_comparison=True,
                    summary_cn="相关卖点的相对价值比较受限，不能据此输出强替代结论。",
                    source_refs=_issue_source_refs("M12C", [issue]),
                )
            )
    return tags, limitations


def _market_pressure(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> tuple[list[M12DPurchasePressureTag], list[M12DComparisonLimitation]]:
    uses_market = M12DEvidenceDomain.MARKET_ACCEPTANCE.value in {
        str(domain) for domain in candidate.evidence_domains_json
    }
    if not uses_market:
        return [], []
    scoped_issues = [
        (module_code, issue)
        for module_code in ("M07", "M11D")
        for issue in _anchor_issues(context, module_code, candidate.anchor_code)
        if _is_market_uncertainty_issue(issue)
    ]
    if not scoped_issues:
        return [], []
    refs = _dedupe_source_refs(
        ref
        for module_code, issue in scoped_issues
        for ref in _issue_source_refs(module_code, [issue])
    )
    tag = _pressure_tag(
        pressure_type=M12DPurchasePressureType.MARKET_UNCERTAINTY,
        pressure_level=M12DPurchasePressureLevel.LOW,
        candidate=candidate,
        aspect="market_comparison",
        positive=0,
        negative=0,
        mixed=0,
        dominance="unknown",
        limits_comparison=True,
        summary_cn=f"{candidate.anchor_cn}的市场承接比较存在样本或关系限制。",
        source_refs=refs,
    )
    limitations = [
        M12DComparisonLimitation(
            limitation_code=str(issue.code),
            scope="market",
            limits_comparison=True,
            summary_cn="市场池、价格带或语义市场关系受限，不能输出无条件的同池排名或规模结论。",
            source_refs=_issue_source_refs(module_code, [issue]),
        )
        for module_code, issue in scoped_issues
    ]
    return [tag], limitations


def _objective_falsification(
    candidate: M12DAnchorCandidate,
    context: M12DSkuPurchaseReasonContext,
) -> list[M12DPurchasePressureTag]:
    issues = [
        issue
        for issue in _anchor_issues(context, "M03B", candidate.anchor_code)
        if str(issue.code) == "m03b_true_param_conflict"
    ]
    if not issues:
        return []
    return [
        _pressure_tag(
            pressure_type=M12DPurchasePressureType.OBJECTIVE_FALSIFICATION,
            pressure_level=M12DPurchasePressureLevel.CRITICAL,
            candidate=candidate,
            aspect="parameter_fact",
            positive=0,
            negative=len(issues),
            mixed=0,
            dominance="negative",
            limits_establishment=True,
            summary_cn=f"{candidate.anchor_cn}引用的可验证产品事实存在冲突，不能据此成立。",
            source_refs=_issue_source_refs("M03B", issues),
        )
    ]


def _pressure_tag(
    *,
    pressure_type: M12DPurchasePressureType,
    pressure_level: M12DPurchasePressureLevel,
    candidate: M12DAnchorCandidate,
    aspect: str,
    positive: int,
    negative: int,
    mixed: int,
    dominance: str,
    summary_cn: str,
    source_refs: Sequence[M12DSourceRef],
    limits_establishment: bool = False,
    limits_comparison: bool = False,
) -> M12DPurchasePressureTag:
    return M12DPurchasePressureTag(
        pressure_type=pressure_type,
        pressure_level=pressure_level,
        affected_aspect_code=aspect,
        affected_anchor_code=candidate.anchor_code,
        positive_count=positive,
        negative_count=negative,
        mixed_count=mixed,
        dominance=dominance,
        limits_establishment=limits_establishment,
        limits_comparison=limits_comparison,
        summary_cn=summary_cn,
        source_refs=list(source_refs),
    )


def _anchor_issues(
    context: M12DSkuPurchaseReasonContext,
    module_code: str,
    anchor_code: str,
) -> list[Any]:
    quality = context.input_quality_json.get(module_code)
    if quality is None:
        return []
    return [
        issue
        for issue in quality.issues
        if anchor_code in {str(code) for code in issue.affected_anchor_codes}
    ]


def _anchor_claim_roles(
    context: M12DSkuPurchaseReasonContext,
    anchor_code: str,
) -> dict[str, set[str]]:
    payload = context.claim_value_profile.summary.get("anchor_claim_value_roles") or {}
    if not isinstance(payload, Mapping):
        return {}
    claims = payload.get(anchor_code) or {}
    if not isinstance(claims, Mapping):
        return {}
    result: dict[str, set[str]] = {}
    for claim_code, values in claims.items():
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            roles = {str(value) for value in values if str(value)}
        elif values:
            roles = {str(values)}
        else:
            roles = set()
        if roles:
            result[str(claim_code)] = roles
    return result


def _m12c_record_refs(
    context: M12DSkuPurchaseReasonContext,
    roles_by_claim: Mapping[str, set[str]],
) -> list[M12DSourceRef]:
    claim_codes = set(roles_by_claim)
    records = [
        record
        for record in context.claim_value_profile.records
        if str(record.get("claim_code") or "") in claim_codes
        and str(record.get("claim_value_role") or "") in M12C_HEADWIND_ROLES
    ]
    return _dedupe_source_refs(
        [
            *_record_source_refs("M12C", records),
            *_m12c_summary_role_refs(context, roles_by_claim),
        ]
    )


def _m12c_negative_records(
    context: M12DSkuPurchaseReasonContext,
    claim_scope: set[str],
) -> list[Mapping[str, Any]]:
    return [
        record
        for record in context.claim_value_profile.records
        if str(record.get("claim_code") or "") in claim_scope
        and "comment_negative" in {
            str(flag) for flag in record.get("quality_flags_json") or []
        }
    ]


def _m12c_summary_role_refs(
    context: M12DSkuPurchaseReasonContext,
    roles_by_claim: Mapping[str, set[str]],
) -> list[M12DSourceRef]:
    payload = context.claim_value_profile.summary.get("claim_value_role_evidence") or {}
    if not isinstance(payload, Mapping):
        return []
    refs: list[M12DSourceRef] = []
    for claim_code, roles in roles_by_claim.items():
        claim_payload = payload.get(claim_code) or {}
        if not isinstance(claim_payload, Mapping):
            continue
        for role in roles & M12C_HEADWIND_ROLES:
            for raw in claim_payload.get(role) or []:
                ref = _m12c_summary_ref(raw, claim_code=claim_code, role=role)
                if ref is not None:
                    refs.append(ref)
    return _dedupe_source_refs(refs)


def _m12c_summary_negative_refs(
    context: M12DSkuPurchaseReasonContext,
    claim_scope: set[str],
) -> list[M12DSourceRef]:
    payload = context.claim_value_profile.summary.get("claim_value_role_evidence") or {}
    if not isinstance(payload, Mapping):
        return []
    refs: list[M12DSourceRef] = []
    for claim_code in claim_scope:
        claim_payload = payload.get(claim_code) or {}
        if not isinstance(claim_payload, Mapping):
            continue
        for role, records in claim_payload.items():
            for raw in records or []:
                if not isinstance(raw, Mapping) or "comment_negative" not in {
                    str(flag) for flag in raw.get("quality_flags_json") or []
                }:
                    continue
                ref = _m12c_summary_ref(raw, claim_code=claim_code, role=str(role))
                if ref is not None:
                    refs.append(ref)
    return _dedupe_source_refs(refs)


def _m12c_summary_ref(
    raw: Any,
    *,
    claim_code: str,
    role: str,
) -> M12DSourceRef | None:
    if not isinstance(raw, Mapping):
        return None
    table_name = str(raw.get("table_name") or "")
    record_id = str(raw.get("record_id") or "")
    if not table_name or not record_id:
        return None
    return M12DSourceRef(
        module_code="M12C",
        table_name=table_name,
        record_id=record_id,
        result_hash=str(raw.get("result_hash")) if raw.get("result_hash") else None,
        evidence_ids=[str(value) for value in raw.get("evidence_ids") or [] if str(value)],
        extra={
            "claim_code": claim_code,
            "claim_value_role": role,
            "reason_cn": raw.get("reason_cn"),
            "quality_flags_json": raw.get("quality_flags_json") or [],
        },
    )


def _m12c_claim_scope(
    context: M12DSkuPurchaseReasonContext,
    anchor_code: str,
) -> set[str]:
    category = str(context.product_category).strip().upper()
    return set(M12C_CLAIM_SCOPE_BY_REASON.get(category, {}).get(anchor_code, frozenset()))


def _m12c_issue_matches_claim_scope(issue: Any, claim_scope: set[str]) -> bool:
    if not claim_scope:
        return False
    claim_codes = {
        str(code)
        for code in issue.details_json.get("claim_codes") or []
        if str(code)
    }
    return bool(claim_codes & claim_scope)


def _comment_record_aligns(
    scope: Iterable[tuple[str, str | None]],
    record: Mapping[str, Any],
) -> bool:
    dimension = str(record.get("dimension_code") or "")
    subdimension = str(record.get("subdimension_code") or "")
    return any(
        dimension == target_dimension
        and (target_subdimension is None or subdimension == target_subdimension)
        for target_dimension, target_subdimension in scope
    )


def _comment_dimension_summary(
    context: M12DSkuPurchaseReasonContext,
) -> dict[str, Mapping[str, Any]]:
    payload = context.comment_profile.summary.get("dimension_summary_json") or {}
    if not isinstance(payload, Mapping):
        return {}
    return {
        str(dimension_code): summary
        for dimension_code, summary in payload.items()
        if str(dimension_code) and isinstance(summary, Mapping)
    }


def _summary_has_scoped_comment(
    scope_by_dimension: Mapping[str, set[str | None]],
    dimension_summary: Mapping[str, Mapping[str, Any]],
) -> bool:
    for dimension_code, target_subdimensions in scope_by_dimension.items():
        summary = dimension_summary.get(dimension_code)
        if not isinstance(summary, Mapping):
            continue
        if None in target_subdimensions:
            return True
        observed = {
            str(code)
            for code in summary.get("subdimension_codes") or []
            if str(code)
        }
        expected = {
            str(code) for code in target_subdimensions if code is not None
        }
        if observed & expected:
            return True
    return False


def _polarity_counts(payload: Any) -> dict[str, int]:
    if not isinstance(payload, Mapping):
        return {}
    result: dict[str, int] = {}
    for polarity in ("positive", "negative", "mixed", "neutral"):
        try:
            result[polarity] = max(0, int(payload.get(polarity) or 0))
        except (TypeError, ValueError):
            result[polarity] = 0
    return result


def _record_polarity_counts(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, int]:
    counts = Counter(str(record.get("polarity") or "unknown").lower() for record in records)
    return {
        polarity: int(counts[polarity])
        for polarity in ("positive", "negative", "mixed", "neutral")
    }


def _group_comment_records(
    records: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        aspect = str(record.get("subdimension_code") or record.get("dimension_code") or "unknown")
        grouped[aspect].append(record)
    return grouped


def _comment_profile_source_refs(
    context: M12DSkuPurchaseReasonContext,
) -> list[M12DSourceRef]:
    return _dedupe_source_refs(
        ref
        for ref in context.comment_profile.source_refs
        if ref.table_name == "core3_sku_comment_fact_profile"
    )


def _comment_dimension_source_refs(
    context: M12DSkuPurchaseReasonContext,
    dimension_code: str,
    summary: Mapping[str, Any],
) -> list[M12DSourceRef]:
    examples = []
    for raw in summary.get("examples") or []:
        if not isinstance(raw, Mapping):
            continue
        examples.append(
            {
                key: raw.get(key)
                for key in (
                    "comment_text",
                    "polarity",
                    "subdimension_code",
                    "evidence_ids",
                    "source_comment_key",
                )
                if raw.get(key) not in (None, "", [])
            }
        )
    refs: list[M12DSourceRef] = []
    for ref in _comment_profile_source_refs(context):
        extra = dict(ref.extra)
        extra.update(
            {
                "dimension_code": dimension_code,
                "polarity_counts": _polarity_counts(summary.get("polarity_counts")),
                "subdimension_codes": [
                    str(code) for code in summary.get("subdimension_codes") or [] if str(code)
                ],
                "comment_examples": examples,
            }
        )
        refs.append(ref.model_copy(update={"extra": extra}))
    return refs


def _comment_records_complete(
    context: M12DSkuPurchaseReasonContext,
    records: Sequence[Mapping[str, Any]],
) -> bool:
    expected = int(context.comment_profile.summary.get("fact_atom_count") or 0)
    expanded = int(context.comment_profile.summary.get("comment_fact_count") or len(records))
    return expected > 0 and expanded >= expected and len(records) >= expected


def _is_market_uncertainty_issue(issue: Any) -> bool:
    code = str(issue.code)
    severity = str(issue.severity)
    return (
        severity != M12DIssueSeverity.INFO.value
        and (
            code in MARKET_UNCERTAINTY_CODES
            or code.startswith(MARKET_UNCERTAINTY_PREFIXES)
        )
    )


def _record_source_refs(
    module_code: str,
    records: Iterable[Mapping[str, Any]],
) -> list[M12DSourceRef]:
    refs = []
    for record in records:
        record_id = str(record.get("record_id") or "")
        table_name = str(record.get("table_name") or "")
        if not record_id or not table_name:
            continue
        extra = {
            key: record.get(key)
            for key in (
                "dimension_code",
                "subdimension_code",
                "polarity",
                "raw_comment_text",
                "claim_code",
                "claim_value_role",
                "reason_cn",
            )
            if record.get(key) not in (None, "")
        }
        refs.append(
            M12DSourceRef(
                module_code=module_code,
                table_name=table_name,
                record_id=record_id,
                result_hash=str(record.get("result_hash")) if record.get("result_hash") else None,
                extra=extra,
            )
        )
    return _dedupe_source_refs(refs)


def _issue_source_refs(module_code: str, issues: Iterable[Any]) -> list[M12DSourceRef]:
    refs: list[M12DSourceRef] = []
    for issue in issues:
        for raw in issue.source_refs:
            if not isinstance(raw, Mapping):
                continue
            table_name = str(raw.get("table_name") or "")
            record_id = str(raw.get("record_id") or "")
            if table_name and record_id:
                refs.append(
                    M12DSourceRef(
                        module_code=module_code,
                        table_name=table_name,
                        record_id=record_id,
                        result_hash=str(raw.get("result_hash")) if raw.get("result_hash") else None,
                    )
                )
    return _dedupe_source_refs(refs)


def _highest_pressure_level(tags: Sequence[M12DPurchasePressureTag]) -> str:
    if not tags:
        return M12DPurchasePressureLevel.NONE.value
    return max(
        (str(tag.pressure_level) for tag in tags),
        key=lambda level: PRESSURE_LEVEL_ORDER.get(level, -1),
    )


def _highest_level_value(level_counts: Mapping[str, int]) -> str:
    observed = [level for level, count in level_counts.items() if count]
    if not observed:
        return M12DPurchasePressureLevel.NONE.value
    return max(observed, key=lambda level: PRESSURE_LEVEL_ORDER.get(level, -1))


def _pressure_summary(tags: Sequence[M12DPurchasePressureTag]) -> str:
    if not tags:
        return "当前未观察到该购买理由的明确购买阻力。"
    return "".join(dict.fromkeys(str(tag.summary_cn) for tag in tags if str(tag.summary_cn)))


def _dedupe_pressure_tags(
    tags: Iterable[M12DPurchasePressureTag],
) -> list[M12DPurchasePressureTag]:
    result: list[M12DPurchasePressureTag] = []
    seen: set[tuple[str, str | None, str]] = set()
    for tag in tags:
        key = (str(tag.pressure_type), tag.affected_aspect_code, str(tag.pressure_level))
        if key not in seen:
            seen.add(key)
            result.append(tag)
    return result


def _dedupe_limitations(
    limitations: Iterable[M12DComparisonLimitation],
) -> list[M12DComparisonLimitation]:
    result: list[M12DComparisonLimitation] = []
    seen: set[tuple[str, str]] = set()
    for limitation in limitations:
        key = (str(limitation.limitation_code), str(limitation.scope))
        if key not in seen:
            seen.add(key)
            result.append(limitation)
    return result


def _dedupe_source_refs(refs: Iterable[M12DSourceRef]) -> list[M12DSourceRef]:
    result: list[M12DSourceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        key = (str(ref.module_code), ref.table_name, ref.record_id)
        if key not in seen:
            seen.add(key)
            result.append(ref)
    return result


def _level_cn(level: str) -> str:
    return {
        "none": "无明确阻力",
        "low": "低压力",
        "medium": "中压力",
        "high": "高压力",
        "critical": "阻断级压力",
        "unassessed": "未评估",
    }.get(level, "未知压力")


__all__ = [
    "COMMENT_SCOPE_BY_REASON",
    "PurchasePressureClassifier",
]
