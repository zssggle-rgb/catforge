"""Deterministic V4 linkage and sellpoint-level counterfactual qualification.

G04 links published reasons, realized value, and sellpoint bundles. G05 adds
candidate roles and comparability gates, but never calculates choice, price
acceptance, or WTP.
"""

from __future__ import annotations

from typing import Any, Sequence

from app.services.core3_real_data.analyst.analyst_repository import canonical_v4_hash
from app.services.core3_real_data.analyst.claim_value_pm_schemas import (
    ClaimValuePmCommentAtom,
)
from app.services.core3_real_data.analyst.claim_value_pm_service import (
    TV_VALUE_UNITS,
    TvValueUnitDefinition,
    _fact_relation,
    _unit_product_facts,
    attribute_comment_atoms,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    BundleMember,
    ComparabilityAssessment,
    EvidenceRef,
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
    return sorted(
        assessments,
        key=lambda item: (
            {"base_value": 0, "same_value": 1, "stretch_benchmark": 2}[item.role],
            {"A": 0, "B": 1, "C": 2, "unusable": 3}[item.isolation_grade],
            item.candidate_sku_code,
        ),
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
]
