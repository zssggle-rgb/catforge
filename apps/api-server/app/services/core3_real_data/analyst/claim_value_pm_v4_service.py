"""Deterministic V4 linkage and sellpoint-level counterfactual qualification.

G04 links published reasons, realized value, and sellpoint bundles. G05 adds
candidate roles and comparability gates, but never calculates choice, price
acceptance, or WTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Any, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_schemas import (
    ClaimValuePmCommentAtom,
)
from app.services.core3_real_data.analyst.claim_value_pm_service import (
    TV_VALUE_UNITS,
    TvValueUnitDefinition,
    _bin_choice_points,
    _fact_relation,
    _gap_locally_supported,
    _interpolation_supported,
    _percentile,
    _unit_product_facts,
    attribute_comment_atoms,
    choice_share_crossing,
    evaluate_choice_curve,
    pava_nonincreasing,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    BundleMember,
    ChoiceAssociation,
    ComparabilityAssessment,
    EvidenceRef,
    MarketImpliedWtp,
    QuantificationResult,
    ReasonValueBundleLink,
    SellpointBundle,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    tv_purchase_reason_anchor_taxonomy_v0_1,
)


ACTIVE_REASON_ROLES = {"core_payment", "supporting"}
VALUE_THEME_UNIT_CODES: dict[str, tuple[str, ...]] = {
    "picture_upgrade_perception": (
        "tv_bright_room_dark_detail",
        "tv_color_picture_truth",
    ),
    "dynamic_stability_perception": ("tv_gaming_motion_fluency",),
    "living_room_immersion_perception": (
        "tv_large_screen_immersion",
        "tv_cinema_soundstage",
    ),
    "budget_configuration_efficiency": (
        "tv_bright_room_dark_detail",
        "tv_gaming_motion_fluency",
        "tv_system_interaction_efficiency",
    ),
    "long_watch_comfort_perception": ("tv_long_viewing_comfort",),
    "operation_convenience_perception": ("tv_system_interaction_efficiency",),
    "space_aesthetic_fit": ("tv_space_aesthetic_fit",),
}
VALUE_SCENARIOS: dict[str, tuple[str, str]] = {
    "picture_upgrade_perception": (
        "白天、暗场和日常观影",
        "画面清楚、明暗层次和色彩表现形成可感知升级",
    ),
    "dynamic_stability_perception": (
        "主机游戏、体育和高速运动画面",
        "操作更跟手、画面更流畅且拖影更少",
    ),
    "living_room_immersion_perception": (
        "客厅观影和家庭影音",
        "大屏与声场共同形成更强沉浸感",
    ),
    "budget_configuration_efficiency": (
        "同尺寸和给定预算下的日常使用",
        "核心画质、动态和系统体验没有明显短板",
    ),
    "long_watch_comfort_perception": (
        "家庭长时间观看",
        "眼睛负担、反光或频闪带来的不适更少",
    ),
    "operation_convenience_perception": (
        "开机、切换、语音、投屏和多设备使用",
        "家庭日常操作步骤更少、等待更短",
    ),
    "space_aesthetic_fit": (
        "新家、客厅装修和贴墙安装",
        "电视外观与空间风格更协调",
    ),
}
FAMILY_BATTLEFIELD_TOKENS: dict[str, tuple[str, ...]] = {
    "picture_upgrade": ("PICTURE",),
    "premium_upgrade": ("PICTURE", "PREMIUM"),
    "dynamic_stability": ("GAMING", "SPORTS", "FLUENCY"),
    "living_room_immersion": ("LIVING", "PICTURE", "IMMERSION"),
    "budget_configuration": ("MAINSTREAM", "BALANCE", "VALUE"),
    "long_watch_comfort": ("EYE", "COMFORT"),
    "operation_convenience": ("SMART", "CONNECTED", "OPERATION"),
    "space_aesthetic": ("HOME", "DECOR", "AESTHETIC"),
}
THEME_TIER_KEYS: dict[str, tuple[str, ...]] = {
    "picture_upgrade_perception": ("picture", "display", "画质"),
    "dynamic_stability_perception": ("gaming", "motion", "游戏"),
    "living_room_immersion_perception": ("picture", "audio", "影音"),
    "budget_configuration_efficiency": ("overall", "configuration", "综合"),
    "long_watch_comfort_perception": ("eye_care", "comfort", "护眼"),
    "operation_convenience_perception": ("system", "smart", "系统"),
    "space_aesthetic_fit": ("aesthetic", "appearance", "外观"),
}
TIER_ORDER = {"unknown": 0, "base": 1, "enhanced": 2, "premium": 3, "flagship": 4}
FAMILY_TIER_KEYS: dict[str, tuple[str, ...]] = {
    "picture_upgrade": ("picture", "display", "画质"),
    "premium_upgrade": ("picture", "display", "画质"),
    "dynamic_stability": ("gaming", "motion", "游戏"),
    "living_room_immersion": ("picture", "audio", "影音"),
    "budget_configuration": ("overall", "configuration", "综合"),
    "long_watch_comfort": ("eye_care", "comfort", "护眼"),
    "operation_convenience": ("system", "smart", "系统"),
    "space_aesthetic": ("aesthetic", "appearance", "外观"),
}
VALID_MARKET_PRICE_STATUSES = {"ok", "uncheckable", "unchecked", ""}
WTP_METHOD_CONFIG_VERSION = "sellpoint_value_pm_v4_matched_wtp_config_v1"


@dataclass(frozen=True)
class _V4PairCurve:
    candidate_sku_code: str
    model_family: str | None
    role: str
    isolation_grade: str
    raw_points: tuple[tuple[float, float, float, int], ...]
    curve_points: tuple[tuple[float, float, float, float, float], ...]
    sample_level: str
    same_price_method: str | None
    same_price_share: float | None
    crossing_ratio: float | None
    candidate_reference_price: float | None
    direction_consistency: float | None
    observed_gap_min: float | None
    observed_gap_max: float | None
    observed_price_min: float | None
    observed_price_max: float | None
    candidate_tier: str
    cell_count: int
    week_count: int
    limitations: tuple[str, ...]


V4_EXTRA_VALUE_UNITS: tuple[TvValueUnitDefinition, ...] = (
    TvValueUnitDefinition(
        code="tv_large_screen_immersion",
        name_cn="大屏客厅沉浸",
        param_codes=("screen_size_inch",),
        claim_codes=("tv_claim_large_screen", "tv_claim_theater_scene"),
        subdimensions=("picture_clarity_resolution", "audio_quality"),
        direct_patterns=(r"\d{2,3}\s*(?:英寸|吋)", r"大屏|巨幕"),
        outcome_patterns=(r"影院感|沉浸", r"客厅.{0,6}(?:震撼|大气)"),
        generic_patterns=(r"屏幕.{0,3}(?:大|不错)",),
    ),
    TvValueUnitDefinition(
        code="tv_space_aesthetic_fit",
        name_cn="空间审美适配",
        param_codes=(
            "slim_body_flag",
            "wall_mount_fit",
            "bezel_less_flag",
            "art_frame_flag",
        ),
        claim_codes=(
            "tv_claim_slim_body",
            "tv_claim_art_frame",
            "tv_claim_wall_mount",
        ),
        subdimensions=("appearance_design", "installation_space_fit"),
        direct_patterns=(r"超薄|贴墙|全面屏|壁画",),
        outcome_patterns=(
            r"新家|家装|装修",
            r"和.{0,5}(?:客厅|墙面|风格).{0,5}(?:搭|协调)",
        ),
        generic_patterns=(r"外观.{0,3}(?:好看|漂亮|不错)",),
    ),
)
VALUE_UNIT_BY_CODE = {
    definition.code: definition
    for definition in (*TV_VALUE_UNITS, *V4_EXTRA_VALUE_UNITS)
}


def build_reason_value_bundle_links(
    context: SellpointValueV4Context,
) -> list[ReasonValueBundleLink]:
    """Build traceable G04 links from an already-published M12D profile."""

    if not context.purchase_reason_profile.found:
        return []
    taxonomy = tv_purchase_reason_anchor_taxonomy_v0_1()
    reasons_by_code = taxonomy.purchase_reasons_by_code()
    themes_by_code = taxonomy.value_themes_by_code()
    anchors = _active_reason_anchors(
        context.purchase_reason_profile.anchors,
        known_reason_codes=set(reasons_by_code),
    )

    comment_atoms = [
        ClaimValuePmCommentAtom.model_validate(item)
        for item in context.target_snapshot.comment_outcomes
    ]
    links: list[ReasonValueBundleLink] = []
    for anchor in anchors:
        reason = reasons_by_code[str(anchor["anchor_code"])]
        themes = [
            themes_by_code[theme_code]
            for theme_code in reason.related_value_theme_codes
            if theme_code in themes_by_code
        ]
        definitions = _dedupe_definitions(
            [
                VALUE_UNIT_BY_CODE[code]
                for theme in themes
                for code in VALUE_THEME_UNIT_CODES.get(theme.value_theme_code, ())
                if code in VALUE_UNIT_BY_CODE
            ]
        )
        if not themes or not definitions:
            continue
        bundle, understandings = _build_bundle(
            bundle_code=f"bundle:{reason.purchase_reason_code}",
            bundle_name_cn=f"{reason.purchase_reason_cn}支撑卖点组合",
            bundle_family=reason.purchase_reason_family_code,
            theme_codes=[theme.value_theme_code for theme in themes],
            definitions=definitions,
            snapshot=context.target_snapshot,
            comment_atoms=comment_atoms,
        )
        value_status = _value_status(understandings)
        battlefield_code, battlefield_name, market_space = _battlefield_for_reason(
            reason.purchase_reason_family_code,
            context.target_snapshot,
        )
        relevant_lineage_conflict = _has_relevant_lineage_conflict(context)
        link_status = _link_status(
            value_status=value_status,
            bundle=bundle,
            lineage_conflict=relevant_lineage_conflict,
        )
        limitations = _link_limitations(
            value_status=value_status,
            bundle=bundle,
            lineage_conflict=relevant_lineage_conflict,
            understandings=understandings,
        )
        scenarios = _dedupe_texts(
            [VALUE_SCENARIOS[theme.value_theme_code][0] for theme in themes]
        )
        expected_outcomes = _dedupe_texts(
            [VALUE_SCENARIOS[theme.value_theme_code][1] for theme in themes]
        )
        outcome_cn = _observed_outcome_cn(
            value_status,
            expected_outcome_cn="；".join(expected_outcomes),
        )
        source_refs = _link_source_refs(context, anchor)
        evidence_domains = _evidence_domains(
            anchor,
            bundle=bundle,
            understandings=understandings,
        )
        value_code = (
            themes[0].value_theme_code
            if len(themes) == 1
            else f"value_combo:{reason.purchase_reason_code}"
        )
        payload: dict[str, Any] = {
            "battlefield_code": battlefield_code,
            "battlefield_name_cn": battlefield_name,
            "battlefield_market_space": market_space,
            "purchase_reason_code": reason.purchase_reason_code,
            "purchase_reason_name_cn": reason.purchase_reason_cn,
            "purchase_reason_family": reason.purchase_reason_family_code,
            "purchase_reason_source_status": context.purchase_reason_profile.lineage_status,
            "realized_value_code": value_code,
            "realized_value_name_cn": "＋".join(
                theme.value_theme_cn for theme in themes
            ),
            "scenario_cn": "；".join(scenarios),
            "outcome_cn": outcome_cn,
            "bundle": bundle,
            "link_status": link_status,
            "value_status": value_status,
            "evidence_domains": evidence_domains,
            "limitations": limitations,
            "source_refs": source_refs,
        }
        links.append(
            ReasonValueBundleLink(
                **payload,
                relation_hash=canonical_v4_hash(payload),
            )
        )
    return sorted(
        links,
        key=lambda item: (
            _reason_rank(item.purchase_reason_code, reasons_by_code),
            item.relation_hash,
        ),
    )


def build_counterfactual_assessments(
    context: SellpointValueV4Context,
    link: ReasonValueBundleLink,
) -> list[ComparabilityAssessment]:
    """Assess candidate comparability without calculating choice or WTP."""

    target = context.target_snapshot
    focus_codes = {member.capability_code for member in link.bundle.members}
    focus_definitions = [
        VALUE_UNIT_BY_CODE[code] for code in focus_codes if code in VALUE_UNIT_BY_CODE
    ]
    assessments: list[ComparabilityAssessment] = []
    for candidate in context.candidate_snapshots:
        provenance, slot_code = _candidate_source(candidate)
        exact_size = _exact_size(target, candidate)
        battlefield_overlap = _battlefield_overlap(
            target, candidate, link.battlefield_code
        )
        reason_overlap = _focus_fact_overlap(candidate, focus_definitions)
        tier_relation = _value_tier_relation(
            target,
            candidate,
            link=link,
            focus_definitions=focus_definitions,
        )
        declared_role = _declared_counterfactual_role(slot_code)
        role = _counterfactual_role(slot_code, tier_relation)
        role_tier_conflict = bool(
            declared_role and tier_relation != "unknown" and declared_role != role
        )
        common_cells, common_weeks, promotion_clean = _common_market_cells(
            context,
            target_sku_code=target.identity.sku_code,
            candidate_sku_code=candidate.identity.sku_code,
            battlefield_code=link.battlefield_code,
        )
        price_overlap = _price_overlap(
            context,
            target_sku_code=target.identity.sku_code,
            candidate_sku_code=candidate.identity.sku_code,
            battlefield_code=link.battlefield_code,
        )
        other_difference_count, other_unknown_count = _other_bundle_differences(
            target,
            candidate,
            focus_codes=focus_codes,
        )
        comment_comparable = _comment_comparable(
            link,
            candidate,
            focus_definitions=focus_definitions,
        )
        grade = _isolation_grade(
            exact_size=exact_size,
            battlefield_overlap=battlefield_overlap,
            reason_overlap=reason_overlap,
            common_cell_count=common_cells,
            price_overlap=price_overlap,
            other_bundle_difference_count=other_difference_count,
            other_bundle_unknown_count=other_unknown_count,
            promotion_clean_cell_count=promotion_clean,
            role_tier_conflict=role_tier_conflict,
        )
        reject_reasons = _comparability_reasons(
            exact_size=exact_size,
            battlefield_overlap=battlefield_overlap,
            reason_overlap=reason_overlap,
            tier_relation=tier_relation,
            common_cell_count=common_cells,
            common_week_count=common_weeks,
            price_overlap=price_overlap,
            other_bundle_difference_count=other_difference_count,
            other_bundle_unknown_count=other_unknown_count,
            promotion_clean_cell_count=promotion_clean,
            comment_comparable=comment_comparable,
            role=role,
            role_tier_conflict=role_tier_conflict,
        )
        levels = _eligible_levels(
            role=role,
            grade=grade,
            tier_relation=tier_relation,
            common_cell_count=common_cells,
            common_week_count=common_weeks,
            promotion_clean_cell_count=promotion_clean,
            price_overlap=price_overlap,
            other_bundle_difference_count=other_difference_count,
            comment_comparable=comment_comparable,
            lineage_conflict=_has_relevant_lineage_conflict(context),
        )
        payload: dict[str, Any] = {
            "candidate_sku_code": candidate.identity.sku_code,
            "role": role,
            "provenance": provenance,
            "isolation_grade": grade,
            "exact_size_match": exact_size,
            "battlefield_overlap": battlefield_overlap,
            "reason_overlap": reason_overlap,
            "value_tier_relation": tier_relation,
            "common_cell_count": common_cells,
            "common_week_count": common_weeks,
            "price_overlap": price_overlap,
            "other_bundle_difference_count": other_difference_count,
            "promotion_clean_cell_count": promotion_clean,
            "inventory_status": "unavailable",
            "comment_comparable": comment_comparable,
            "eligible": grade in {"A", "B"},
            "eligible_quantification_levels": levels,
            "reject_reasons": reject_reasons,
        }
        assessments.append(
            ComparabilityAssessment(
                **payload,
                assessment_hash=canonical_v4_hash(payload),
            )
        )
    ordered = sorted(
        assessments,
        key=lambda item: (
            {"base_value": 0, "same_value": 1, "stretch_benchmark": 2}[item.role],
            {"A": 0, "B": 1, "C": 2, "unusable": 3}[item.isolation_grade],
            item.candidate_sku_code,
        ),
    )
    selected: list[ComparabilityAssessment] = []
    role_counts = {"base_value": 0, "same_value": 0, "stretch_benchmark": 0}
    for assessment in ordered:
        if role_counts[assessment.role] >= 3:
            continue
        selected.append(assessment)
        role_counts[assessment.role] += 1
    return selected


def quantify_sellpoint_value(
    context: SellpointValueV4Context,
    link: ReasonValueBundleLink,
    assessments: Sequence[ComparabilityAssessment],
) -> QuantificationResult:
    """Quantify only the highest level supported by observed market cells."""

    curves = [
        _build_v4_pair_curve(context, link, assessment)
        for assessment in assessments
        if assessment.eligible and assessment.role in {"base_value", "same_value"}
    ]
    relative_experience = _relative_experience(assessments)
    choice = _apply_choice_value_gate(
        _choice_association(curves),
        value_status=link.value_status,
        relative_experience_available=relative_experience is not None,
    )
    whole_product = _whole_product_price_acceptance(curves, choice)
    wtp = _market_implied_wtp(
        context,
        link,
        assessments,
        curves,
        relative_experience_available=relative_experience is not None,
    )
    level = _quantification_level(
        value_status=link.value_status,
        relative_experience=relative_experience,
        choice=choice,
        whole_product=whole_product,
        wtp=wtp,
    )
    product_role = _product_role(
        value_status=link.value_status,
        assessments=assessments,
        choice=choice,
        wtp=wtp,
    )
    monetization_status = _monetization_status(
        level=level,
        whole_product=whole_product,
    )
    limitations = _dedupe_texts(
        [
            *link.limitations,
            *(choice.limitations if choice is not None else []),
            *wtp.exclusion_reasons,
            "库存状态不可得，结果未声称控制库存。",
            "市场隐含结果是观察性关联，不是因果效应或用户心理最高价。",
        ]
    )
    gate_results = _quantification_gate_results(
        link=link,
        relative_experience=relative_experience,
        choice=choice,
        whole_product=whole_product,
        wtp=wtp,
    )
    return QuantificationResult(
        level=level,
        value_status=link.value_status,
        product_role=product_role,
        monetization_status=monetization_status,
        relative_experience=relative_experience,
        choice_association=choice,
        whole_product_price_acceptance=whole_product,
        wtp=wtp,
        gate_results=gate_results,
        limitations=limitations,
    )


def _active_reason_anchors(
    anchors: Sequence[dict[str, Any]],
    *,
    known_reason_codes: set[str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for anchor in anchors:
        code = str(anchor.get("anchor_code") or "")
        role = str(anchor.get("role") or "")
        if (
            code not in known_reason_codes
            or role not in ACTIVE_REASON_ROLES
            or code in seen
        ):
            continue
        seen.add(code)
        result.append(anchor)
    return result


def _build_bundle(
    *,
    bundle_code: str,
    bundle_name_cn: str,
    bundle_family: str,
    theme_codes: Sequence[str],
    definitions: Sequence[TvValueUnitDefinition],
    snapshot: SkuEvidenceSnapshot,
    comment_atoms: Sequence[ClaimValuePmCommentAtom],
) -> tuple[SellpointBundle, list[Any]]:
    fact_brief = {
        "sections": {
            **snapshot.facts,
            "market": snapshot.market,
        }
    }
    business_tier = max(
        (_theme_business_tier(snapshot, theme_code) for theme_code in theme_codes),
        key=lambda item: TIER_ORDER[item],
    )
    members: list[BundleMember] = []
    understandings: list[Any] = []
    for definition in definitions:
        facts = _unit_product_facts(definition, fact_brief)
        fact_status = _fact_status(snapshot, facts)
        understanding = attribute_comment_atoms(definition, comment_atoms)
        understandings.append(understanding)
        members.append(
            BundleMember(
                capability_code=definition.code,
                capability_name_cn=definition.name_cn,
                fact_status=fact_status,
                business_tier=business_tier,
                fact_summary_cn="；".join(facts),
                user_result_support=understanding.status,
                source_refs=_member_source_refs(snapshot, definition),
            )
        )
    multi_member = len(members) > 1
    limitations = []
    if multi_member:
        limitations.append(
            "组合成员在当前 SKU 中共同变化，G04 不声明任何成员可独立量化。"
        )
    return (
        SellpointBundle(
            bundle_code=bundle_code,
            bundle_name_cn=bundle_name_cn,
            bundle_family=bundle_family,
            business_tier=business_tier,
            members=members,
            collinearity_group=(
                f"collinear:{'+'.join(theme_codes)}" if multi_member else None
            ),
            independently_identifiable=(
                len(members) == 1
                and definitions[0].independently_identifiable
                and members[0].fact_status == "confirmed"
            ),
            limitations=limitations,
        ),
        understandings,
    )


def _fact_status(snapshot: SkuEvidenceSnapshot, facts: Sequence[str]) -> str:
    relevant = [snapshot.source_status.get(code) for code in ("M03B", "M04C")]
    issue_codes = {
        issue
        for status in relevant
        if status is not None
        for issue in status.issue_codes
    }
    if "multiple_current_same_rule" in issue_codes:
        return "conflict"
    if facts:
        return "confirmed"
    present_count = sum(
        status is not None and status.availability == "present" for status in relevant
    )
    if present_count == 0:
        return "partial"
    return "unknown"


def _value_status(understandings: Sequence[Any]) -> str:
    statuses = [item.status for item in understandings]
    positive_count = sum(
        item in {"direct", "outcome_only", "mixed"} for item in statuses
    )
    negative = any(item in {"negative", "mixed"} for item in statuses)
    positive = positive_count > 0
    if positive and negative:
        return "conflicted"
    if positive_count == len(understandings):
        return "established"
    if positive:
        return "partial"
    if negative:
        return "conflicted"
    return "not_observed"


def _link_status(
    *,
    value_status: str,
    bundle: SellpointBundle,
    lineage_conflict: bool,
) -> str:
    if lineage_conflict or value_status == "conflicted":
        return "conflicted"
    confirmed = any(member.fact_status == "confirmed" for member in bundle.members)
    if value_status == "established" and confirmed:
        return "supported"
    if value_status == "established" or confirmed:
        return "partial"
    return "insufficient"


def _has_relevant_lineage_conflict(context: SellpointValueV4Context) -> bool:
    for issue in context.lineage_gate.issues:
        if issue.code != "version_lineage_conflict":
            continue
        if set(issue.affected_module_codes) & {"M03B", "M04C", "M05C"}:
            return True
    return False


def _link_limitations(
    *,
    value_status: str,
    bundle: SellpointBundle,
    lineage_conflict: bool,
    understandings: Sequence[Any],
) -> list[str]:
    result = ["用户价值仅来自购后体验证据，不代表购买前传播心智或心理最高价。"]
    if value_status == "not_observed":
        result.append("当前用户评论未观察到该项实际价值。")
    if value_status == "conflicted":
        result.append("用户反馈存在反向或正反并存体验，不能写成已稳定兑现。")
    if any(item.status == "unrecognized" for item in understandings):
        result.append("泛化好评只保留在组合层，未拆分为单一技术能力证据。")
    if lineage_conflict:
        result.append("已发布采购理由与当前产品事实版本冲突，关系结论局部阻断。")
    result.extend(bundle.limitations)
    return _dedupe_texts(result)


def _observed_outcome_cn(
    value_status: str,
    *,
    expected_outcome_cn: str,
) -> str:
    if value_status == "established":
        return f"用户购后反馈已观察到：{expected_outcome_cn}。"
    if value_status == "conflicted":
        return f"用户购后反馈对“{expected_outcome_cn}”正反并存或出现反向体验。"
    if value_status == "partial":
        return f"用户购后反馈只部分支持：{expected_outcome_cn}。"
    return f"当前用户购后反馈尚未观察到：{expected_outcome_cn}。"


def _battlefield_for_reason(
    reason_family: str,
    snapshot: SkuEvidenceSnapshot,
) -> tuple[str, str, dict[str, Any] | None]:
    profile = snapshot.battlefields[0] if snapshot.battlefields else {}
    candidates = _dedupe_texts(
        [
            profile.get("primary_battlefield_code"),
            *(profile.get("secondary_battlefield_codes") or []),
            *(profile.get("opportunity_battlefield_codes") or []),
        ]
    )
    tokens = FAMILY_BATTLEFIELD_TOKENS.get(reason_family, ())
    selected = next(
        (code for code in candidates if any(token in code.upper() for token in tokens)),
        candidates[0] if candidates else "unknown",
    )
    semantic = next(
        (
            item
            for item in snapshot.semantic_market
            if str(item.get("dimension_code") or "") == selected
        ),
        None,
    )
    return (
        selected,
        str((semantic or {}).get("dimension_name") or ""),
        (semantic or {}).get("market_space"),
    )


def _theme_business_tier(snapshot: SkuEvidenceSnapshot, theme_code: str) -> str:
    tiers = (snapshot.facts.get("parameter_fact") or {}).get(
        "dimension_tier_profile"
    ) or {}
    tokens = THEME_TIER_KEYS.get(theme_code, ())
    values: list[Any] = []
    for key, value in tiers.items() if isinstance(tiers, dict) else ():
        if any(token.lower() in str(key).lower() for token in tokens):
            values.append(value)
    normalized = [_normalize_tier(value) for value in values]
    return max(normalized or ["unknown"], key=lambda item: TIER_ORDER[item])


def _candidate_source(snapshot: SkuEvidenceSnapshot) -> tuple[str, str]:
    source = snapshot.facts.get("candidate_source") or {}
    provenance = str(source.get("provenance") or "competitor_set_fallback")
    if provenance not in {
        "M14",
        "competitor_set_fallback",
        "M12C_pool",
        "same_family_search",
    }:
        provenance = "competitor_set_fallback"
    return provenance, str(source.get("slot_code") or "")


def _exact_size(target: SkuEvidenceSnapshot, candidate: SkuEvidenceSnapshot) -> bool:
    left = target.identity.screen_size_inch
    right = candidate.identity.screen_size_inch
    return left is not None and right is not None and abs(left - right) <= 0.5


def _battlefield_codes(snapshot: SkuEvidenceSnapshot) -> set[str]:
    if not snapshot.battlefields:
        return set()
    profile = snapshot.battlefields[0]
    return set(
        _dedupe_texts(
            [
                profile.get("primary_battlefield_code"),
                *(profile.get("secondary_battlefield_codes") or []),
                *(profile.get("opportunity_battlefield_codes") or []),
            ]
        )
    )


def _battlefield_overlap(
    target: SkuEvidenceSnapshot,
    candidate: SkuEvidenceSnapshot,
    focus_code: str,
) -> float:
    target_codes = _battlefield_codes(target) | (
        {focus_code} if focus_code != "unknown" else set()
    )
    candidate_codes = _battlefield_codes(candidate)
    if focus_code in candidate_codes:
        return 1.0
    if not target_codes or not candidate_codes:
        return 0.0
    return round(
        len(target_codes & candidate_codes) / len(target_codes | candidate_codes), 4
    )


def _fact_brief(snapshot: SkuEvidenceSnapshot) -> dict[str, Any]:
    return {"sections": {**snapshot.facts, "market": snapshot.market}}


def _focus_fact_overlap(
    candidate: SkuEvidenceSnapshot,
    definitions: Sequence[TvValueUnitDefinition],
) -> float:
    if not definitions:
        return 0.0
    present = sum(
        bool(_unit_product_facts(item, _fact_brief(candidate))) for item in definitions
    )
    return round(present / len(definitions), 4)


def _snapshot_family_tier(snapshot: SkuEvidenceSnapshot, family: str) -> str:
    tiers = (snapshot.facts.get("parameter_fact") or {}).get(
        "dimension_tier_profile"
    ) or {}
    tokens = FAMILY_TIER_KEYS.get(family, ())
    values = (
        [
            _normalize_tier(value)
            for key, value in tiers.items()
            if any(token.lower() in str(key).lower() for token in tokens)
        ]
        if isinstance(tiers, dict)
        else []
    )
    return max(values or ["unknown"], key=lambda item: TIER_ORDER[item])


def _value_tier_relation(
    target: SkuEvidenceSnapshot,
    candidate: SkuEvidenceSnapshot,
    *,
    link: ReasonValueBundleLink,
    focus_definitions: Sequence[TvValueUnitDefinition],
) -> str:
    target_tier = link.bundle.business_tier
    candidate_tier = _snapshot_family_tier(candidate, link.bundle.bundle_family)
    if target_tier != "unknown" and candidate_tier != "unknown":
        if TIER_ORDER[candidate_tier] < TIER_ORDER[target_tier]:
            return "lower"
        if TIER_ORDER[candidate_tier] > TIER_ORDER[target_tier]:
            return "higher"
        return "same"
    relations = [
        _fact_relation(item, _fact_brief(target), _fact_brief(candidate))
        for item in focus_definitions
    ]
    known = {item for item in relations if item != "unknown"}
    if known == {"target_stronger"}:
        return "lower"
    if known == {"competitor_stronger"}:
        return "higher"
    if known and known <= {"similar"}:
        return "same"
    return "unknown"


def _counterfactual_role(slot_code: str, tier_relation: str) -> str:
    inferred = {
        "lower": "base_value",
        "same": "same_value",
        "higher": "stretch_benchmark",
    }.get(tier_relation)
    declared = _declared_counterfactual_role(slot_code)
    return inferred or declared or "same_value"


def _declared_counterfactual_role(slot_code: str) -> str | None:
    slot = slot_code.lower()
    if slot in {"base_value", "same_value", "stretch_benchmark"}:
        return slot
    if "base" in slot or "lower" in slot:
        return "base_value"
    if "stretch" in slot or "benchmark" in slot or "upper" in slot:
        return "stretch_benchmark"
    if "same" in slot or "direct" in slot or "fight" in slot:
        return "same_value"
    return None


def _sku_cells(
    context: SellpointValueV4Context,
    sku_code: str,
    battlefield_code: str,
) -> dict[tuple[str, int, str], Any]:
    return {
        (row.battlefield_code, row.period_week_index, row.platform_type): row
        for row in context.market_cells
        if row.sku_code == sku_code
        and row.battlefield_code == battlefield_code
        and row.avg_price is not None
        and row.avg_price > 0
        and row.sales_volume is not None
        and row.sales_volume >= 0
        and row.price_check_status.lower() in VALID_MARKET_PRICE_STATUSES
    }


def _common_market_cells(
    context: SellpointValueV4Context,
    *,
    target_sku_code: str,
    candidate_sku_code: str,
    battlefield_code: str,
) -> tuple[int, int, int]:
    target = _sku_cells(context, target_sku_code, battlefield_code)
    candidate = _sku_cells(context, candidate_sku_code, battlefield_code)
    keys = sorted(set(target) & set(candidate))
    clean = sum(
        not target[key].promotion_suspect and not candidate[key].promotion_suspect
        for key in keys
    )
    return len(keys), len({key[1] for key in keys}), clean


def _price_overlap(
    context: SellpointValueV4Context,
    *,
    target_sku_code: str,
    candidate_sku_code: str,
    battlefield_code: str,
) -> bool:
    target_rows = _sku_cells(context, target_sku_code, battlefield_code)
    candidate_rows = _sku_cells(context, candidate_sku_code, battlefield_code)
    common_keys = set(target_rows) & set(candidate_rows)
    target = [target_rows[key].avg_price for key in common_keys]
    candidate = [candidate_rows[key].avg_price for key in common_keys]
    return bool(
        target
        and candidate
        and max(min(target), min(candidate)) <= min(max(target), max(candidate))
    )


def _other_bundle_differences(
    target: SkuEvidenceSnapshot,
    candidate: SkuEvidenceSnapshot,
    *,
    focus_codes: set[str],
) -> tuple[int, int]:
    target_brief = _fact_brief(target)
    candidate_brief = _fact_brief(candidate)
    relations = []
    for code, definition in VALUE_UNIT_BY_CODE.items():
        target_facts = _unit_product_facts(definition, target_brief)
        if code in focus_codes or not target_facts:
            continue
        relation = _fact_relation(definition, target_brief, candidate_brief)
        candidate_facts = _unit_product_facts(definition, candidate_brief)
        if relation == "unknown" and candidate_facts == target_facts:
            relation = "similar"
        relations.append(relation)
    return (
        sum(
            item in {"target_stronger", "competitor_stronger", "different"}
            for item in relations
        ),
        sum(item == "unknown" for item in relations),
    )


def _comment_comparable(
    link: ReasonValueBundleLink,
    candidate: SkuEvidenceSnapshot,
    *,
    focus_definitions: Sequence[TvValueUnitDefinition],
) -> bool:
    if link.value_status == "not_observed" or not candidate.comment_outcomes:
        return False
    atoms = [
        ClaimValuePmCommentAtom.model_validate(item)
        for item in candidate.comment_outcomes
    ]
    return any(
        attribute_comment_atoms(item, atoms).status
        in {"direct", "outcome_only", "mixed", "negative"}
        for item in focus_definitions
    )


def _isolation_grade(**values: Any) -> str:
    if (
        not values["exact_size"]
        or values["battlefield_overlap"] == 0
        or values["common_cell_count"] == 0
        or not values["price_overlap"]
    ):
        return "unusable"
    if values["role_tier_conflict"]:
        return "C"
    if (
        values["battlefield_overlap"] == 1
        and values["reason_overlap"] >= 0.8
        and values["other_bundle_difference_count"] == 0
        and values["other_bundle_unknown_count"] <= 1
        and values["common_cell_count"] >= 8
        and values["promotion_clean_cell_count"] >= 4
    ):
        return "A"
    if (
        values["battlefield_overlap"] >= 0.5
        and values["reason_overlap"] >= 0.5
        and values["other_bundle_difference_count"] <= 1
        and values["other_bundle_unknown_count"] <= 3
        and values["common_cell_count"] >= 4
        and values["promotion_clean_cell_count"] >= 2
    ):
        return "B"
    return "C"


def _comparability_reasons(**values: Any) -> list[str]:
    reasons: list[str] = []
    if not values["exact_size"]:
        reasons.append("size_mismatch")
    if values["battlefield_overlap"] == 0:
        reasons.append("battlefield_mismatch")
    elif values["battlefield_overlap"] < 0.5:
        reasons.append("battlefield_overlap_low")
    if values["reason_overlap"] < 0.5:
        reasons.append("reason_support_low")
    if values["tier_relation"] == "unknown":
        reasons.append("value_tier_unknown")
    if values["common_cell_count"] == 0:
        reasons.append("no_common_week_platform_cells")
    elif values["common_cell_count"] < 4:
        reasons.append("common_cells_insufficient")
    if values["common_week_count"] < 2:
        reasons.append("temporal_variation_insufficient")
    if not values["price_overlap"]:
        reasons.append("no_price_overlap")
    if values["other_bundle_difference_count"]:
        reasons.append("other_bundle_differences")
    if values["other_bundle_unknown_count"] > 1:
        reasons.append("other_bundle_unknown")
    if values["promotion_clean_cell_count"] < 4:
        reasons.append("promotion_clean_cells_insufficient")
    if not values["comment_comparable"]:
        reasons.append("experience_not_comparable")
    if values["role_tier_conflict"]:
        reasons.append("candidate_role_tier_conflict")
    if values["role"] == "same_value":
        reasons.append("same_value_only")
    elif values["role"] == "stretch_benchmark":
        reasons.append("stretch_benchmark_only")
    return reasons


def _eligible_levels(**values: Any) -> list[str]:
    if values["grade"] not in {"A", "B"}:
        return []
    levels: list[str] = []
    if values["comment_comparable"]:
        levels.append("Q2_RELATIVE_EXPERIENCE")
    if (
        values["role"] != "stretch_benchmark"
        and values["common_cell_count"] >= 4
        and values["price_overlap"]
    ):
        levels.extend(
            [
                "Q3_MARKET_CHOICE_ASSOCIATION",
                "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE",
            ]
        )
    if (
        values["role"] == "base_value"
        and values["grade"] == "A"
        and values["tier_relation"] == "lower"
        and values["common_cell_count"] >= 12
        and values["common_week_count"] >= 8
        and values["promotion_clean_cell_count"] >= 8
        and values["price_overlap"]
        and values["other_bundle_difference_count"] == 0
        and not values["lineage_conflict"]
    ):
        levels.append("Q5_MARKET_IMPLIED_WTP")
    return levels


def _build_v4_pair_curve(
    context: SellpointValueV4Context,
    link: ReasonValueBundleLink,
    assessment: ComparabilityAssessment,
) -> _V4PairCurve:
    candidate = next(
        (
            item
            for item in context.candidate_snapshots
            if item.identity.sku_code == assessment.candidate_sku_code
        ),
        None,
    )
    if candidate is None:
        return _empty_v4_pair_curve(assessment, "候选 SKU snapshot 不存在。")
    target_rows = _sku_cells(
        context, context.target_snapshot.identity.sku_code, link.battlefield_code
    )
    candidate_rows = _sku_cells(
        context, assessment.candidate_sku_code, link.battlefield_code
    )
    common_keys = sorted(set(target_rows) & set(candidate_rows))
    raw: list[tuple[float, float, float, int]] = []
    observed_prices: list[float] = []
    candidate_prices: list[float] = []
    excluded = 0
    allocation_missing = 0
    for key in common_keys:
        target_row = target_rows[key]
        candidate_row = candidate_rows[key]
        if target_row.promotion_suspect or candidate_row.promotion_suspect:
            excluded += 1
            continue
        target_sales = float(target_row.sales_volume or 0)
        candidate_sales = float(candidate_row.sales_volume or 0)
        target_price = float(target_row.avg_price or 0)
        candidate_price = float(candidate_row.avg_price or 0)
        if (
            target_sales <= 0
            or candidate_sales <= 0
            or target_price <= 0
            or candidate_price <= 0
        ):
            excluded += 1
            continue
        gap = (target_price - candidate_price) / candidate_price
        if gap < -0.60 or gap > 1.50:
            excluded += 1
            continue
        total_sales = target_sales + candidate_sales
        sample_weight, allocation_complete = _battlefield_sample_weight(
            target_row,
            candidate_row,
        )
        if not allocation_complete:
            allocation_missing += 1
        raw.append(
            (
                gap,
                target_sales / total_sales,
                total_sales * sample_weight,
                key[1],
            )
        )
        observed_prices.extend([target_price, candidate_price])
        candidate_prices.append(candidate_price)
    if not raw:
        return _empty_v4_pair_curve(
            assessment,
            "没有同战场、同周、同平台且非促销疑似的正销量价格单元。",
            model_family=_candidate_model_family(context, candidate),
            candidate_tier=_snapshot_family_tier(candidate, link.bundle.bundle_family),
        )
    weight_cap = _percentile([item[2] for item in raw], 0.90)
    capped = [(x, y, min(weight, weight_cap), week) for x, y, weight, week in raw]
    binned = _bin_choice_points(capped)
    observed_bins = sorted(item[0] for item in binned)
    curve = pava_nonincreasing(binned)
    gap_min = min(item[0] for item in raw)
    gap_max = max(item[0] for item in raw)
    gap_span = gap_max - gap_min
    week_count = len({item[3] for item in raw})
    local_zero = _interpolation_supported(observed_bins, 0.0)
    if (
        len(raw) >= 12
        and week_count >= 8
        and len(binned) >= 6
        and gap_span >= 0.08
        and gap_min <= 0 <= gap_max
        and local_zero
    ):
        sample_level = "strong"
    elif len(raw) >= 6 and week_count >= 4 and len(binned) >= 3 and gap_span >= 0.04:
        sample_level = "medium"
    elif len(raw) >= 4 and len(binned) >= 2:
        sample_level = "weak"
    else:
        sample_level = "insufficient"
    same_price_method: str | None = None
    same_price_share: float | None = None
    if gap_min <= 0 <= gap_max and local_zero and sample_level in {"strong", "medium"}:
        same_price_method = "pair_curve_same_price"
        same_price_share = evaluate_choice_curve(
            curve,
            0.0,
            observed_min=gap_min,
            observed_max=gap_max,
        )
    elif (
        observed_bins
        and min(abs(item) for item in observed_bins) <= 0.03
        and sample_level in {"strong", "medium"}
    ):
        same_price_method = "near_same_price"
        nearest = min(observed_bins, key=abs)
        same_price_share = evaluate_choice_curve(
            curve,
            nearest,
            observed_min=gap_min,
            observed_max=gap_max,
        )
    crossing: float | None = None
    if same_price_method == "pair_curve_same_price" and (same_price_share or 0) > 0.5:
        candidate_crossing = choice_share_crossing(
            curve,
            threshold=0.5,
            start_gap=0.0,
            observed_min=gap_min,
            observed_max=gap_max,
        )
        if candidate_crossing is not None and _gap_locally_supported(
            observed_bins, candidate_crossing
        ):
            crossing = candidate_crossing
    direction_consistency = _raw_direction_consistency(binned)
    limitations: list[str] = []
    if excluded:
        limitations.append(f"{excluded} 个共同单元因促销疑似或无效量价被排除。")
    if allocation_missing:
        limitations.append(
            f"{allocation_missing} 个共同单元缺少完整战场解释权重；真实销量未改写，样本权重按可用边界处理。"
        )
    if not (gap_min <= 0 <= gap_max):
        limitations.append("观测价差没有覆盖同价位置。")
    elif not local_zero:
        limitations.append("同价附近存在样本空洞，未做插值。")
    if sample_level in {"weak", "insufficient"}:
        limitations.append("共同单元、周数、价差跨度或分箱数量不足。")
    if direction_consistency is not None and direction_consistency < 0.75:
        limitations.append("原始分箱的价格方向不稳定。")
    if crossing is None:
        limitations.append("观测范围内没有局部支持的五五开 crossing。")
    return _V4PairCurve(
        candidate_sku_code=assessment.candidate_sku_code,
        model_family=_candidate_model_family(context, candidate),
        role=assessment.role,
        isolation_grade=assessment.isolation_grade,
        raw_points=tuple(capped),
        curve_points=tuple(curve),
        sample_level=sample_level,
        same_price_method=same_price_method,
        same_price_share=_v4_round(same_price_share, 6),
        crossing_ratio=_v4_round(crossing, 6),
        candidate_reference_price=_v4_round(median(candidate_prices), 2),
        direction_consistency=_v4_round(direction_consistency, 6),
        observed_gap_min=_v4_round(gap_min, 6),
        observed_gap_max=_v4_round(gap_max, 6),
        observed_price_min=_v4_round(min(observed_prices), 2),
        observed_price_max=_v4_round(max(observed_prices), 2),
        candidate_tier=_snapshot_family_tier(candidate, link.bundle.bundle_family),
        cell_count=len(raw),
        week_count=week_count,
        limitations=tuple(limitations),
    )


def _empty_v4_pair_curve(
    assessment: ComparabilityAssessment,
    limitation: str,
    *,
    model_family: str | None = None,
    candidate_tier: str = "unknown",
) -> _V4PairCurve:
    return _V4PairCurve(
        candidate_sku_code=assessment.candidate_sku_code,
        model_family=model_family,
        role=assessment.role,
        isolation_grade=assessment.isolation_grade,
        raw_points=(),
        curve_points=(),
        sample_level="insufficient",
        same_price_method=None,
        same_price_share=None,
        crossing_ratio=None,
        candidate_reference_price=None,
        direction_consistency=None,
        observed_gap_min=None,
        observed_gap_max=None,
        observed_price_min=None,
        observed_price_max=None,
        candidate_tier=candidate_tier,
        cell_count=0,
        week_count=0,
        limitations=(limitation,),
    )


def _candidate_model_family(
    context: SellpointValueV4Context,
    candidate: SkuEvidenceSnapshot,
) -> str | None:
    source = candidate.facts.get("candidate_source") or {}
    declared = str(source.get("model_family") or "").strip()
    if declared:
        return declared
    values = {
        str(row.series_name).strip()
        for row in context.market_cells
        if row.sku_code == candidate.identity.sku_code and row.series_name
    }
    if len(values) == 1:
        return next(iter(values))
    return None


def _battlefield_sample_weight(
    target_row: Any,
    candidate_row: Any,
) -> tuple[float, bool]:
    """Return a conservative explanatory sample weight without changing sales."""

    values = [
        float(value)
        for value in (
            target_row.battlefield_allocation_weight,
            candidate_row.battlefield_allocation_weight,
        )
        if value is not None
    ]
    if not values:
        return 1.0, False
    return max(min(values), 0.0), len(values) == 2


def _raw_direction_consistency(
    binned: Sequence[tuple[float, float, float]],
) -> float | None:
    ordered = sorted(binned, key=lambda item: item[0])
    if len(ordered) < 2:
        return None
    comparisons = [left[1] >= right[1] for left, right in zip(ordered, ordered[1:])]
    return sum(comparisons) / len(comparisons)


def _relative_experience(
    assessments: Sequence[ComparabilityAssessment],
) -> dict[str, Any] | None:
    comparable = [
        item
        for item in assessments
        if item.comment_comparable
        and item.exact_size_match
        and item.battlefield_overlap >= 0.5
        and item.reason_overlap >= 0.5
        and item.role in {"base_value", "same_value", "stretch_benchmark"}
    ]
    if not comparable:
        return None
    return {
        "status": "available",
        "basis": "comparable_post_purchase_value_theme",
        "base_value_candidate_count": sum(
            item.role == "base_value" for item in comparable
        ),
        "same_value_candidate_count": sum(
            item.role == "same_value" for item in comparable
        ),
        "stretch_candidate_count": sum(
            item.role == "stretch_benchmark" for item in comparable
        ),
        "strength_comparison": "not_ranked_from_comment_counts",
        "limitation": "评论只确认同一价值主题是否被实际感知，不按评论数量排序体验强弱。",
    }


def _choice_association(curves: Sequence[_V4PairCurve]) -> ChoiceAssociation:
    exact = [
        item
        for item in curves
        if item.same_price_method == "pair_curve_same_price"
        and item.same_price_share is not None
        and item.sample_level in {"strong", "medium"}
    ]
    near = [
        item
        for item in curves
        if item.same_price_method == "near_same_price"
        and item.same_price_share is not None
        and item.sample_level in {"strong", "medium"}
    ]
    selected = exact or near
    if not selected:
        return ChoiceAssociation(
            status="insufficient",
            method="none",
            pair_count=0,
            cell_count=sum(item.cell_count for item in curves),
            week_count=max((item.week_count for item in curves), default=0),
            limitations=_dedupe_texts(
                [
                    "没有同价或近同价且局部样本充分的可比 pair。",
                    *(text for item in curves for text in item.limitations),
                ]
            ),
        )
    total_weight = sum(max(item.cell_count, 1) for item in selected)
    share = (
        sum(
            float(item.same_price_share) * max(item.cell_count, 1)
            for item in selected
            if item.same_price_share is not None
        )
        / total_weight
    )
    direction_values = [
        item.direction_consistency
        for item in selected
        if item.direction_consistency is not None
    ]
    direction = (
        sum(direction_values) / len(direction_values) if direction_values else None
    )
    status = "unstable" if direction is not None and direction < 0.60 else "available"
    ranges = [
        value
        for item in selected
        for value in (item.observed_gap_min, item.observed_gap_max)
        if value is not None
    ]
    limitations = _dedupe_texts(
        [
            *(text for item in selected for text in item.limitations),
            *(
                ["不同价差分箱的选择方向不稳定，选择差异仅作观察。"]
                if status == "unstable"
                else []
            ),
        ]
    )
    return ChoiceAssociation(
        status=status,
        method="pair_curve_same_price" if exact else "near_same_price",
        same_price_choice_share=_v4_round(share, 6),
        choice_difference_pp=_v4_round((share - 0.5) * 100, 2),
        pair_count=len(selected),
        cell_count=sum(item.cell_count for item in selected),
        week_count=max(item.week_count for item in selected),
        observed_price_gap_range=(
            [_v4_round(min(ranges), 6), _v4_round(max(ranges), 6)] if ranges else []
        ),
        direction_consistency=_v4_round(direction, 6),
        limitations=limitations,
    )


def _apply_choice_value_gate(
    choice: ChoiceAssociation,
    *,
    value_status: str,
    relative_experience_available: bool,
) -> ChoiceAssociation:
    if value_status not in {"established", "partial"}:
        reason = "用户实际价值尚未成立，市场量价不能归因到该卖点组合。"
    elif not relative_experience_available:
        reason = "缺少可比购后体验证据，市场量价不能越级标记为卖点选择贡献。"
    else:
        return choice
    return ChoiceAssociation(
        status="insufficient",
        method="none",
        pair_count=0,
        cell_count=choice.cell_count,
        week_count=choice.week_count,
        observed_price_gap_range=choice.observed_price_gap_range,
        direction_consistency=choice.direction_consistency,
        limitations=_dedupe_texts([reason, *choice.limitations]),
    )


def _whole_product_price_acceptance(
    curves: Sequence[_V4PairCurve],
    choice: ChoiceAssociation,
) -> dict[str, Any] | None:
    if choice.status != "available":
        return None
    selected = [
        item
        for item in curves
        if item.same_price_method == choice.method and item.curve_points
    ]
    current: list[tuple[float, float, float]] = []
    for item in selected:
        latest_week = max((point[3] for point in item.raw_points), default=None)
        if latest_week is None:
            continue
        latest = [point for point in item.raw_points if point[3] == latest_week]
        total_weight = sum(point[2] for point in latest)
        if total_weight <= 0:
            continue
        gap = sum(point[0] * point[2] for point in latest) / total_weight
        if item.observed_gap_min is None or item.observed_gap_max is None:
            continue
        share = evaluate_choice_curve(
            item.curve_points,
            gap,
            observed_min=item.observed_gap_min,
            observed_max=item.observed_gap_max,
        )
        if share is not None:
            current.append((gap, share, max(item.cell_count, 1)))
    if not current:
        return {
            "status": "insufficient",
            "method": "observed_current_gap",
            "attribution_scope": "whole_product_only",
        }
    total_weight = sum(item[2] for item in current)
    current_gap = sum(item[0] * item[2] for item in current) / total_weight
    current_share = sum(item[1] * item[2] for item in current) / total_weight
    if current_share >= 0.55:
        state = "advantage_remains"
    elif current_share >= 0.48:
        state = "market_balance"
    else:
        state = "price_pressure"
    return {
        "status": "available",
        "method": "observed_current_gap",
        "attribution_scope": "whole_product_only",
        "current_relative_price_gap": _v4_round(current_gap, 6),
        "current_choice_share": _v4_round(current_share, 6),
        "same_price_choice_share": choice.same_price_choice_share,
        "acceptance_state": state,
        "causal_claim": False,
    }


def _market_implied_wtp(
    context: SellpointValueV4Context,
    link: ReasonValueBundleLink,
    assessments: Sequence[ComparabilityAssessment],
    curves: Sequence[_V4PairCurve],
    *,
    relative_experience_available: bool,
) -> MarketImpliedWtp:
    assessments_by_sku = {item.candidate_sku_code: item for item in assessments}
    base_curves = [
        item
        for item in curves
        if item.role == "base_value"
        and item.isolation_grade == "A"
        and assessments_by_sku[item.candidate_sku_code].value_tier_relation == "lower"
    ]
    family_count_before = len(
        {item.model_family for item in base_curves if item.model_family}
    )
    strong = [item for item in base_curves if item.sample_level == "strong"]
    direction_ready = [
        item for item in strong if (item.direction_consistency or 0) >= 0.75
    ]
    with_crossing = [
        item
        for item in direction_ready
        if item.same_price_method == "pair_curve_same_price"
        and item.crossing_ratio is not None
        and item.crossing_ratio > 0
    ]
    leave_one_out = {
        item.candidate_sku_code: _leave_one_week_out(item) for item in with_crossing
    }
    qualified = [
        item
        for item in with_crossing
        if leave_one_out[item.candidate_sku_code]["stable"]
        and item.model_family
        and item.candidate_reference_price
    ]
    family_count = len({item.model_family for item in qualified if item.model_family})
    lineage_conflict = _has_relevant_lineage_conflict(context)
    market_cells_truncated = any(
        "market_cells_truncated" in authority.warnings
        for authority in context.authority_manifest
        if authority.module_code == "M07"
    )
    exclusions: list[str] = []
    if lineage_conflict:
        exclusions.append("version_lineage_conflict")
    elif market_cells_truncated:
        exclusions.append("market_cells_truncated")
    elif link.value_status != "established":
        exclusions.append("user_value_not_fully_established")
    elif not relative_experience_available:
        exclusions.append("relative_experience_not_comparable")
    elif not base_curves:
        if any(item.role == "base_value" for item in assessments):
            exclusions.append("base_counterfactual_not_eligible")
        elif any(item.role == "same_value" for item in assessments):
            exclusions.append("same_value_only")
        else:
            exclusions.append("base_counterfactual_missing")
    elif len(base_curves) < 2:
        exclusions.append("independent_a_pair_count_below_2")
    elif family_count_before < 2:
        exclusions.append("model_family_count_below_2")
    elif len(strong) < 2:
        exclusions.append("strong_pair_curve_count_below_2")
    elif len(direction_ready) < 2:
        exclusions.append("price_direction_consistency_failed")
    elif len(with_crossing) < 2:
        exclusions.append("equal_choice_crossing_count_below_2")
    elif len(qualified) < 2:
        exclusions.append("leave_one_week_out_stability_failed")
    elif family_count < 2:
        exclusions.append("qualified_model_family_count_below_2")
    available = (
        link.value_status == "established"
        and relative_experience_available
        and not lineage_conflict
        and not market_cells_truncated
        and len(qualified) >= 2
        and family_count >= 2
    )
    if available:
        status = "available"
    elif lineage_conflict or market_cells_truncated:
        status = "blocked"
    elif (
        len(base_curves) >= 2
        and family_count_before >= 2
        and (len(direction_ready) < 2 or len(with_crossing) < 2 or len(qualified) < 2)
    ):
        status = "unstable"
    else:
        status = "insufficient"
    amounts = [
        float(item.crossing_ratio) * float(item.candidate_reference_price)
        for item in qualified
        if item.crossing_ratio is not None and item.candidate_reference_price
    ]
    reference_prices = [
        float(item.candidate_reference_price)
        for item in qualified
        if item.candidate_reference_price
    ]
    price_ranges = [
        value
        for item in base_curves
        for value in (item.observed_price_min, item.observed_price_max)
        if value is not None
    ]
    tiers = _dedupe_texts(
        [link.bundle.business_tier, *(item.candidate_tier for item in base_curves)]
    )
    sensitivity_summary = {
        "pair_crossing_ratio": {
            item.candidate_sku_code: item.crossing_ratio for item in with_crossing
        },
        "pair_direction_consistency": {
            item.candidate_sku_code: item.direction_consistency
            for item in with_crossing
        },
        "leave_one_week_out": leave_one_out,
        "eligible_a_base_pair_count": len(base_curves),
        "explicit_model_family_count": family_count_before,
    }
    return MarketImpliedWtp(
        status=status,
        method=("matched_equal_choice_price_gap" if base_curves else "none"),
        method_config_version=WTP_METHOD_CONFIG_VERSION,
        estimate_low=_v4_round(min(amounts), 2) if available else None,
        estimate_high=_v4_round(max(amounts), 2) if available else None,
        reference_price=(_v4_round(median(reference_prices), 2) if available else None),
        currency="CNY",
        pair_count=len(qualified),
        model_family_count=family_count,
        cell_count=sum(item.cell_count for item in qualified),
        week_count=max((item.week_count for item in qualified), default=0),
        observed_price_range=(
            [_v4_round(min(price_ranges), 2), _v4_round(max(price_ranges), 2)]
            if price_ranges
            else []
        ),
        observed_value_tiers=tiers,
        sensitivity_summary=sensitivity_summary,
        assumptions=[
            "同周同平台匹配用于控制共同时间与渠道环境。",
            "促销疑似单元已排除，但库存状态不可得。",
            "品牌和其他未观察差异仍可能混杂，结果不作因果解释。",
        ],
        exclusion_reasons=[] if available else _dedupe_texts(exclusions),
        causal_claim=False,
        psychological_max_price=False,
    )


def _leave_one_week_out(curve: _V4PairCurve) -> dict[str, Any]:
    weeks = sorted({item[3] for item in curve.raw_points})
    crossings: list[float] = []
    for excluded_week in weeks:
        remaining = [item for item in curve.raw_points if item[3] != excluded_week]
        if len(remaining) < 8:
            continue
        binned = _bin_choice_points(remaining)
        bins = sorted(item[0] for item in binned)
        if not bins:
            continue
        gap_min = min(item[0] for item in remaining)
        gap_max = max(item[0] for item in remaining)
        if not (gap_min <= 0 <= gap_max) or not _interpolation_supported(bins, 0.0):
            continue
        fitted = pava_nonincreasing(binned)
        same_share = evaluate_choice_curve(
            fitted,
            0.0,
            observed_min=gap_min,
            observed_max=gap_max,
        )
        if same_share is None or same_share <= 0.5:
            continue
        crossing = choice_share_crossing(
            fitted,
            threshold=0.5,
            start_gap=0.0,
            observed_min=gap_min,
            observed_max=gap_max,
        )
        if (
            crossing is not None
            and crossing > 0
            and _gap_locally_supported(bins, crossing)
        ):
            crossings.append(crossing)
    coverage = len(crossings) / len(weeks) if weeks else 0.0
    crossing_span = max(crossings) - min(crossings) if crossings else None
    stable = (
        len(weeks) >= 8
        and coverage == 1.0
        and crossing_span is not None
        and crossing_span <= 0.04
    )
    return {
        "stable": stable,
        "week_count": len(weeks),
        "successful_leave_out_count": len(crossings),
        "coverage": _v4_round(coverage, 6),
        "crossing_ratio_min": _v4_round(min(crossings), 6) if crossings else None,
        "crossing_ratio_max": _v4_round(max(crossings), 6) if crossings else None,
    }


def _quantification_level(
    *,
    value_status: str,
    relative_experience: dict[str, Any] | None,
    choice: ChoiceAssociation,
    whole_product: dict[str, Any] | None,
    wtp: MarketImpliedWtp,
) -> str:
    if value_status not in {"established", "partial"}:
        return "Q0_NOT_OBSERVED"
    if relative_experience is None:
        return "Q1_USER_VALUE_ESTABLISHED"
    if choice.status != "available":
        return "Q2_RELATIVE_EXPERIENCE"
    if whole_product is None or whole_product.get("status") != "available":
        return "Q3_MARKET_CHOICE_ASSOCIATION"
    if wtp.status == "available":
        return "Q5_MARKET_IMPLIED_WTP"
    return "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE"


def _product_role(
    *,
    value_status: str,
    assessments: Sequence[ComparabilityAssessment],
    choice: ChoiceAssociation,
    wtp: MarketImpliedWtp,
) -> str:
    if value_status not in {"established", "partial"}:
        return "undetermined"
    if wtp.status == "available":
        return "core_differentiated_value"
    if choice.status == "available":
        if (choice.same_price_choice_share or 0) < 0.5:
            return "price_pressure"
        eligible_roles = {item.role for item in assessments if item.eligible}
        if eligible_roles and eligible_roles <= {"same_value"}:
            return "basic_threshold"
        return "supporting_choice_value"
    return "configuration_support"


def _monetization_status(
    *,
    level: str,
    whole_product: dict[str, Any] | None,
) -> str:
    if level == "Q5_MARKET_IMPLIED_WTP" and whole_product is not None:
        return {
            "advantage_remains": "partially_captured",
            "market_balance": "fully_captured",
            "price_pressure": "over_captured",
        }.get(str(whole_product.get("acceptance_state")), "whole_product_only")
    if level == "Q4_WHOLE_PRODUCT_PRICE_ACCEPTANCE":
        return "whole_product_only"
    if level == "Q3_MARKET_CHOICE_ASSOCIATION":
        return "choice_supported"
    return "not_measured"


def _quantification_gate_results(
    *,
    link: ReasonValueBundleLink,
    relative_experience: dict[str, Any] | None,
    choice: ChoiceAssociation,
    whole_product: dict[str, Any] | None,
    wtp: MarketImpliedWtp,
) -> list[dict[str, Any]]:
    return [
        {
            "gate_code": "user_value_established",
            "passed": link.value_status in {"established", "partial"},
        },
        {
            "gate_code": "relative_experience_comparable",
            "passed": relative_experience is not None,
        },
        {
            "gate_code": "market_choice_association_available",
            "passed": choice.status == "available",
        },
        {
            "gate_code": "whole_product_price_acceptance_available",
            "passed": bool(
                whole_product and whole_product.get("status") == "available"
            ),
        },
        {
            "gate_code": "market_implied_wtp_available",
            "passed": wtp.status == "available",
            "exclusion_reasons": wtp.exclusion_reasons,
        },
    ]


def _v4_round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _normalize_tier(value: Any) -> str:
    text = str(value or "").lower()
    for tier in ("flagship", "premium", "enhanced", "base"):
        if tier in text:
            return tier
    return "unknown"


def _member_source_refs(
    snapshot: SkuEvidenceSnapshot,
    definition: TvValueUnitDefinition,
) -> list[EvidenceRef]:
    del definition
    return _dedupe_refs(
        [
            ref
            for ref in snapshot.source_refs
            if ref.module_code in {"M03B", "M04C", "M05C"}
        ]
    )


def _dedupe_definitions(
    definitions: Sequence[TvValueUnitDefinition],
) -> list[TvValueUnitDefinition]:
    seen: set[str] = set()
    result: list[TvValueUnitDefinition] = []
    for definition in definitions:
        if definition.code in seen:
            continue
        seen.add(definition.code)
        result.append(definition)
    return result


def _link_source_refs(
    context: SellpointValueV4Context,
    anchor: dict[str, Any],
) -> list[EvidenceRef]:
    anchor_record_ids = {
        str(item.get("record_id"))
        for item in (anchor.get("source_refs") or [])
        if isinstance(item, dict) and item.get("record_id")
    }
    purchase_refs = [
        ref
        for ref in context.purchase_reason_profile.source_refs
        if not anchor_record_ids
        or ref.record_id in anchor_record_ids
        or ref.module_code == "M12D"
    ]
    fact_refs = [
        ref
        for ref in context.target_snapshot.source_refs
        if ref.module_code in {"M03B", "M04C", "M05C", "M11C", "M11D"}
    ]
    return _dedupe_refs([*purchase_refs, *fact_refs])


def _evidence_domains(
    anchor: dict[str, Any],
    *,
    bundle: SellpointBundle,
    understandings: Sequence[Any],
) -> list[str]:
    result = [str(item) for item in (anchor.get("evidence_domains") or [])]
    if any(member.fact_status == "confirmed" for member in bundle.members):
        result.extend(["param_fact", "fact_claim"])
    if any(
        item.status in {"direct", "outcome_only", "mixed", "negative"}
        for item in understandings
    ):
        result.append("comment_perception")
    return _dedupe_texts(result)


def _dedupe_refs(refs: Sequence[EvidenceRef]) -> list[EvidenceRef]:
    seen: set[tuple[str, str, str, str]] = set()
    result: list[EvidenceRef] = []
    for ref in refs:
        key = (ref.module_code, ref.record_type, ref.record_id, ref.result_hash)
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return sorted(
        result, key=lambda item: (item.module_code, item.record_type, item.record_id)
    )


def _dedupe_texts(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _reason_rank(code: str, reasons_by_code: dict[str, Any]) -> int:
    reason = reasons_by_code.get(code)
    return int(reason.candidate_rank) if reason is not None else 999


__all__ = [
    "build_counterfactual_assessments",
    "build_reason_value_bundle_links",
    "quantify_sellpoint_value",
]
