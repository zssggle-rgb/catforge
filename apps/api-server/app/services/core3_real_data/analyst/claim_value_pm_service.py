"""Evidence-gated sellpoint weighting and price-acceptance analysis.

The service is deterministic and deliberately keeps whole-product market
signals separate from sellpoint attribution. It never allocates an observed
SKU price gap across claims.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.claim_value_pm_schemas import (
    ClaimValuePmAction,
    ClaimValuePmAnalysis,
    ClaimValuePmCommentAtom,
    ClaimValuePmCompetitorComparison,
    ClaimValuePmCompetitorSnapshot,
    ClaimValuePmContext,
    ClaimValuePmCurvePoint,
    ClaimValuePmDataGate,
    ClaimValuePmDataIssue,
    ClaimValuePmMarketPricing,
    ClaimValuePmMarketWeeklyRow,
    ClaimValuePmPairCurve,
    ClaimValuePmPriceScenario,
    ClaimValuePmPurchaseRole,
    ClaimValuePmUserUnderstanding,
    ClaimValuePmValueUnit,
    ClaimValuePmWeights,
)


@dataclass(frozen=True)
class TvValueUnitDefinition:
    code: str
    name_cn: str
    param_codes: tuple[str, ...]
    claim_codes: tuple[str, ...]
    subdimensions: tuple[str, ...]
    direct_patterns: tuple[str, ...]
    outcome_patterns: tuple[str, ...]
    generic_patterns: tuple[str, ...]
    independently_identifiable: bool = False


TV_VALUE_UNITS: tuple[TvValueUnitDefinition, ...] = (
    TvValueUnitDefinition(
        code="tv_bright_room_dark_detail",
        name_cn="明亮环境与明暗层次",
        param_codes=(
            "mini_led_flag",
            "mini_led_type",
            "display_tech_class",
            "declared_brightness_nit_or_band",
            "local_dimming_zone_count",
            "backlight_subtype",
        ),
        claim_codes=("tv_claim_miniled_display", "tv_claim_hdr_high_brightness", "tv_claim_local_dimming"),
        subdimensions=("picture_clarity_resolution", "picture_brightness_hdr", "picture_local_dimming_black"),
        direct_patterns=(
            r"mini\s*led",
            r"\d{3,4}\s*(?:nit|尼特)",
            r"亮度|峰值亮",
            r"\d{2,4}\s*(?:分区|区)",
            r"分区控光|控光|黑位|光晕|漏光|hdr|黑曜屏",
        ),
        outcome_patterns=(r"白天|强光|阳光", r"暗场|黑场|明暗层次", r"不发灰|反光少|看得清|层次(?:好|清楚|分明)|通透"),
        generic_patterns=(r"画质.{0,3}(?:好|不错)", r"(?:很|真)?清晰", r"高清|细腻|鲜艳"),
    ),
    TvValueUnitDefinition(
        code="tv_gaming_motion_fluency",
        name_cn="游戏与运动流畅",
        param_codes=("declared_refresh_rate_hz", "refresh_rate_hz", "hdmi21_port_count", "hdmi_2_1_port_count", "hdmi_version_mix"),
        claim_codes=("tv_claim_high_refresh_rate", "tv_claim_high_refresh", "tv_claim_gaming_low_latency", "tv_claim_hdmi21_connectivity"),
        subdimensions=("gaming_high_refresh_motion",),
        direct_patterns=(r"\d{3}\s*hz", r"高刷|刷新率", r"hdmi\s*2[.]1", r"低延迟|输入延迟|input\s*lag"),
        outcome_patterns=(r"(?:不|少|没有)拖影|拖影少", r"操作.{0,3}跟手|响应.{0,3}快", r"(?:球赛|体育|高速画面).{0,5}流畅", r"游戏.{0,5}(?:跟手|不卡|流畅)"),
        generic_patterns=(r"游戏性能.{0,3}(?:好|强|不错)?", r"很流畅|运行流畅"),
    ),
    TvValueUnitDefinition(
        code="tv_color_picture_truth",
        name_cn="色彩与画面真实",
        param_codes=("wide_color_gamut_pct", "color_gamut_ratio", "high_color_gamut_flag", "quantum_dot_flag"),
        claim_codes=("tv_claim_wide_color_accuracy", "tv_claim_qd_miniled_display", "tv_claim_rgb_miniled_display"),
        subdimensions=("picture_color_accuracy", "picture_clarity_resolution"),
        direct_patterns=(r"\d{2,3}\s*%\s*(?:色域)?", r"色域|色准|量子点|rgb\s*mini"),
        outcome_patterns=(r"肤色.{0,3}(?:自然|真实)", r"颜色.{0,3}(?:真实|自然|准确|不偏)", r"还原.{0,3}(?:准|真实)"),
        generic_patterns=(r"色彩.{0,3}(?:好|鲜艳|不错)", r"颜色.{0,3}(?:好看|鲜艳)"),
    ),
    TvValueUnitDefinition(
        code="tv_cinema_soundstage",
        name_cn="影院声场",
        param_codes=("speaker_power_w", "speaker_system", "speaker_channel", "dolby_audio_flag"),
        claim_codes=("tv_claim_speaker_sound", "tv_claim_dolby_audio_video", "tv_claim_theater_scene"),
        subdimensions=("audio_quality",),
        direct_patterns=(r"\d[.]\d[.]\d\s*(?:声道)?", r"声道|杜比|dolby|低音|扬声器|音响功率"),
        outcome_patterns=(r"对白.{0,3}(?:清楚|清晰)", r"包围感|声场|低频.{0,3}(?:足|有力|下潜)", r"影院感|沉浸"),
        generic_patterns=(r"音质.{0,3}(?:好|不错)", r"声音.{0,3}(?:好|大|不错)"),
    ),
    TvValueUnitDefinition(
        code="tv_system_interaction_efficiency",
        name_cn="系统与交互效率",
        param_codes=(
            "processor_chip_model",
            "ai_chip_flag",
            "ai_capability_flag",
            "ai_model_capability_flag",
            "ai_model_name",
            "memory_storage",
            "memory_capacity_gb",
            "ram_gb",
            "storage_capacity_gb",
            "storage_gb",
        ),
        claim_codes=("tv_claim_chip_performance", "tv_claim_memory_storage", "tv_claim_voice_control", "tv_claim_smart_home_iot"),
        subdimensions=("system_smooth_ads", "interaction_voice_casting"),
        direct_patterns=(r"mt\d{3,5}|芯片|处理器", r"\d+\s*[+＋]\s*\d+\s*gb", r"内存|存储", r"语音|投屏|互联"),
        outcome_patterns=(r"开机.{0,3}(?:快|不卡)", r"切换.{0,3}(?:快|顺|不卡)", r"系统.{0,5}(?:不卡|顺畅)", r"投屏.{0,3}(?:稳|快|方便)"),
        generic_patterns=(r"(?:系统|操作|运行).{0,3}流畅", r"反应.{0,3}快"),
    ),
    TvValueUnitDefinition(
        code="tv_long_viewing_comfort",
        name_cn="长时间观看舒适",
        param_codes=("low_blue_light_flag", "flicker_free_flag", "eye_care_flag", "anti_reflection_flag", "ambient_light_sensor_flag"),
        claim_codes=("tv_claim_eye_care_display",),
        subdimensions=("picture_eye_care_reflection", "picture_brightness_hdr"),
        direct_patterns=(r"护眼|低蓝光|无频闪|防反|抗反|环境光",),
        outcome_patterns=(r"久看.{0,4}(?:不累|舒服)", r"眼睛.{0,4}(?:不累|舒服|不酸)", r"反光.{0,3}(?:少|不明显)"),
        generic_patterns=(r"看着.{0,3}舒服", r"不刺眼"),
    ),
)

ALL_UNIT_CODES = tuple(item.code for item in TV_VALUE_UNITS)
PRODUCT_EXPERIENCE_TYPES = {"product_experience", "product_risk", "price_value"}
VALID_PRICE_STATUSES = {"ok", "uncheckable", "unchecked", ""}
PRICE_CURVE_ROLE_CODES = {
    "direct_fight",
    "price_volume_pressure",
    "primary_direct",
    "strong_direct",
    "price_adjacent",
}
DIRECT_CHOICE_PATTERNS = (
    r"冲着.{0,12}(?:买|选)",
    r"看中.{0,12}(?:买|选)",
    r"就是因为.{0,16}(?:买|选)",
    r"因为.{0,16}(?:买了|购买|选择)",
    r"对比.{0,20}(?:选了|选择|买了)",
    r"贵.{0,8}(?:也值|值得买)",
    r"决定.{0,8}(?:买|购买|选择)",
)

PARAM_LABELS = {
    "mini_led_flag": "MiniLED",
    "mini_led_type": "MiniLED 类型",
    "display_tech_class": "显示技术",
    "declared_brightness_nit_or_band": "标称亮度",
    "local_dimming_zone_count": "控光分区",
    "backlight_subtype": "背光类型",
    "declared_refresh_rate_hz": "刷新率",
    "refresh_rate_hz": "刷新率",
    "hdmi21_port_count": "HDMI 2.1 接口",
    "hdmi_2_1_port_count": "HDMI 2.1 接口",
    "hdmi_version_mix": "HDMI 接口",
    "wide_color_gamut_pct": "色域",
    "color_gamut_ratio": "色域",
    "high_color_gamut_flag": "广色域",
    "quantum_dot_flag": "量子点",
    "speaker_power_w": "音响功率",
    "speaker_system": "声道",
    "speaker_channel": "声道",
    "dolby_audio_flag": "杜比音频",
    "processor_chip_model": "芯片",
    "ai_chip_flag": "AI 芯片",
    "ai_capability_flag": "AI 能力",
    "ai_model_capability_flag": "AI 大模型能力",
    "ai_model_name": "AI 模型",
    "memory_storage": "内存/存储",
    "memory_capacity_gb": "运行内存",
    "ram_gb": "运行内存",
    "storage_capacity_gb": "存储",
    "storage_gb": "存储",
    "low_blue_light_flag": "低蓝光",
    "flicker_free_flag": "无频闪",
    "eye_care_flag": "护眼",
    "anti_reflection_flag": "防反光",
    "ambient_light_sensor_flag": "环境光调节",
}

PARAM_VALUE_TIERS: dict[str, tuple[float, ...]] = {
    "declared_brightness_nit_or_band": (500, 1000, 2000, 4000),
    "local_dimming_zone_count": (100, 500, 1000, 1500, 2000),
    "declared_refresh_rate_hz": (120, 144, 240),
    "refresh_rate_hz": (120, 144, 240),
    "hdmi21_port_count": (1, 2, 4),
    "hdmi_2_1_port_count": (1, 2, 4),
    "wide_color_gamut_pct": (90, 95, 98),
    "color_gamut_ratio": (90, 95, 98),
    "speaker_power_w": (20, 40, 60, 100),
    "memory_capacity_gb": (2, 4, 8, 16),
    "storage_capacity_gb": (16, 32, 64, 128),
    "ram_gb": (2, 4, 8, 16),
    "storage_gb": (16, 32, 64, 128),
}

PARAM_COMPARISON_ALIASES = {
    "declared_refresh_rate_hz": "refresh_rate_hz",
    "refresh_rate_hz": "refresh_rate_hz",
    "hdmi_2_1_port_count": "hdmi21_port_count",
    "hdmi21_port_count": "hdmi21_port_count",
    "color_gamut_ratio": "wide_color_gamut_pct",
    "wide_color_gamut_pct": "wide_color_gamut_pct",
    "speaker_channel": "speaker_system",
    "speaker_system": "speaker_system",
    "ram_gb": "memory_capacity_gb",
    "storage_gb": "storage_capacity_gb",
    "ai_capability_flag": "ai_chip_flag",
}
MIN_COMPARABLE_PARAM_COUNT = 2


def analyze_sellpoint_value_pm(context: ClaimValuePmContext | dict[str, Any]) -> dict[str, Any]:
    """Build the V2 product-manager analysis from published profile snapshots."""

    source = context if isinstance(context, ClaimValuePmContext) else ClaimValuePmContext.model_validate(context)
    if source.product_category.upper() != "TV":
        gate = ClaimValuePmDataGate(
            status="blocked",
            status_cn="当前品类尚未配置卖点称重规则",
            issues=[
                ClaimValuePmDataIssue(
                    code="unsupported_product_category",
                    severity="blocking",
                    scope="general",
                    message_cn="首版只实现彩电价值单元，不能把彩电规则套到其他品类。",
                )
            ],
            missing_sources=[],
            available_sources=[],
            review_required=True,
        )
        result = ClaimValuePmAnalysis(
            analysis_status="blocked",
            target=source.target,
            data_gate=gate,
            headline_cn="当前品类暂不能生成可靠的卖点称重结果。",
            market_pricing=_empty_market_pricing("当前品类没有可用量化规则。"),
            limitations=["首版仅支持 TV。"],
            audit=_audit_payload(source, method_level="L0"),
        )
        return result.model_dump(mode="json")

    gate = build_data_gate(source)
    market_pricing = build_market_pricing(source)
    eligible_sentence_count = _eligible_sentence_count(source.comment_atoms)
    units: list[ClaimValuePmValueUnit] = []
    for definition in TV_VALUE_UNITS:
        units.append(
            _build_value_unit(
                definition,
                source=source,
                gate=gate,
                market_pricing=market_pricing,
                eligible_sentence_count=eligible_sentence_count,
            )
        )
    actions = _decision_actions(gate, units, market_pricing)
    backlog = _test_backlog(gate, units, market_pricing)
    headline = _headline(gate, units, market_pricing)
    limitations = _dedupe_strings(
        [
            "评论来自购买后用户，只能说明体验是否被说出来，不能代表未购买用户。",
            "同价销量承接和价格情景来自历史直接竞品对照，不能证明某个技术点单独导致销量变化。",
            "选择保持价差是价格测试边界，不是某个卖点的确定金额，也不是建议售价。",
            "当前没有成本数据，因此不判断利润贡献或利润最优价。",
            *market_pricing.limitations,
        ]
    )
    result = ClaimValuePmAnalysis(
        analysis_status=gate.status,
        target=source.target,
        data_gate=gate,
        headline_cn=headline,
        decision_summary=actions,
        value_units=units,
        market_pricing=market_pricing,
        competitor_boundary={
            "source": source.competitor_source,
            "competitor_count": len(source.competitors),
            "sku_codes": [item.sku_code for item in source.competitors],
            "detail_entry": "原竞品智能体（competitor-set）",
            "policy_cn": "只复用既有竞品集合和事实，不在本报告重选竞品，也不把竞品报告结论重复算作证据。",
        },
        test_backlog=backlog,
        limitations=limitations,
        audit=_audit_payload(source, method_level=market_pricing.method_level),
    )
    return result.model_dump(mode="json")


def build_data_gate(context: ClaimValuePmContext) -> ClaimValuePmDataGate:
    sections = _sections(context.fact_brief)
    available: list[str] = []
    missing: list[str] = []
    issues: list[ClaimValuePmDataIssue] = []
    module_by_section = {
        "parameter_fact": "M03B",
        "claim_fact": "M04C",
        "comment_fact": "M05C",
        "market": "M07",
        "user_task": "M09C",
        "target_group": "M10C",
        "value_battlefield": "M11C",
        "semantic_dimension_positions": "M11D",
    }
    for section, module in module_by_section.items():
        if sections.get(section):
            available.append(module)
        else:
            missing.append(module)
    if "M03B" in missing:
        issues.append(
            ClaimValuePmDataIssue(
                code="m03b_missing",
                severity="blocking",
                scope="product_fact",
                message_cn="缺少产品参数事实，无法确认卖点能力是否成立。",
                source_modules=["M03B"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    if "M07" in missing:
        issues.append(
            ClaimValuePmDataIssue(
                code="m07_missing",
                severity="blocking",
                scope="market",
                message_cn="缺少价格销量画像，无法判断同价销量承接和当前价格承接。",
                source_modules=["M07"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    if "M05C" in missing or not context.comment_atoms:
        issues.append(
            ClaimValuePmDataIssue(
                code="m05c_comment_atoms_missing",
                severity="warning",
                scope="user_evidence",
                message_cn="没有可用评论事实原子，本轮只能看产品和市场，不能判断用户如何理解卖点。",
                source_modules=["M05C"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    claim = sections.get("claim_fact") or {}
    param = sections.get("parameter_fact") or {}
    claim_summary = claim.get("summary") or {}
    quality_flags = {str(item) for item in claim.get("quality_flags") or []}
    if not claim:
        issues.append(
            ClaimValuePmDataIssue(
                code="m04c_missing",
                severity="warning",
                scope="product_fact",
                message_cn="缺少卖点事实画像，只能展示参数事实，不能确认产品侧卖点表达是否成立。",
                source_modules=["M04C"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    if claim and param and "m03b_param_profile_missing" in quality_flags:
        issues.append(
            ClaimValuePmDataIssue(
                code="m03b_m04c_presence_conflict",
                severity="blocking",
                scope="product_fact",
                message_cn="参数画像已经存在，但卖点事实仍声明参数画像缺失；受影响卖点暂停做价格归因。",
                source_modules=["M03B", "M04C"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    matched_count = int(claim_summary.get("matched_claim_count") or 0)
    fact_count = int(claim_summary.get("fact_claim_count") or 0)
    if matched_count > 0 and fact_count == 0:
        issues.append(
            ClaimValuePmDataIssue(
                code="m04c_all_claims_unresolved",
                severity="blocking",
                scope="product_fact",
                message_cn="产品卖点已经被识别，但没有一条完成事实确认；不能把产品表达当成已成立能力。",
                source_modules=["M04C"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    param_summary = param.get("summary") or {}
    if int(param_summary.get("conflict_count") or 0) > 0:
        issues.append(
            ClaimValuePmDataIssue(
                code="m03b_parameter_conflict",
                severity="blocking",
                scope="product_fact",
                message_cn="关键参数存在冲突，相关价值组合暂停判断。",
                source_modules=["M03B"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    if not context.competitors:
        issues.append(
            ClaimValuePmDataIssue(
                code="competitor_set_missing",
                severity="warning",
                scope="competitor",
                message_cn="没有可复用的直接竞品集合，本轮不判断竞品位置和选择保持价差。",
                source_modules=["M14"],
                affected_unit_codes=list(ALL_UNIT_CODES),
            )
        )
    blocking = any(item.severity == "blocking" for item in issues)
    required_block = any(item.code in {"m03b_missing", "m07_missing"} for item in issues)
    status = "blocked" if required_block else "partial" if issues else "ready"
    if status == "blocked":
        status_cn = "本轮暂停核心判断"
    elif blocking:
        status_cn = "数据需修复，卖点结论暂停"
    elif status == "partial":
        status_cn = "仅供方向参考"
    else:
        status_cn = "可用于产品决策"
    return ClaimValuePmDataGate(
        status=status,
        status_cn=status_cn,
        issues=issues,
        available_sources=_dedupe_strings(available),
        missing_sources=_dedupe_strings(missing),
        review_required=blocking or bool(issues),
    )


def attribute_comment_atoms(
    definition: TvValueUnitDefinition,
    atoms: Sequence[ClaimValuePmCommentAtom],
    *,
    eligible_sentence_count: int | None = None,
) -> ClaimValuePmUserUnderstanding:
    """Classify comment sentences without treating generic praise as a technical claim."""

    relevant: dict[tuple[str, int | None], ClaimValuePmCommentAtom] = {}
    for atom in atoms:
        if atom.dimension_type not in PRODUCT_EXPERIENCE_TYPES:
            continue
        linked = bool(
            set(atom.supported_param_codes + atom.contradicted_param_codes).intersection(definition.param_codes)
            or set(atom.supported_claim_codes + atom.contradicted_claim_codes).intersection(definition.claim_codes)
        )
        if atom.subdimension_code not in definition.subdimensions and not linked:
            continue
        relevant.setdefault((atom.source_comment_key, atom.sentence_seq), atom)
    direct: list[ClaimValuePmCommentAtom] = []
    indirect: list[ClaimValuePmCommentAtom] = []
    unattributable: list[ClaimValuePmCommentAtom] = []
    negative: list[ClaimValuePmCommentAtom] = []
    for atom in relevant.values():
        text = _normalize_text(atom.clean_comment_text)
        contradicted = bool(
            set(atom.contradicted_param_codes).intersection(definition.param_codes)
            or set(atom.contradicted_claim_codes).intersection(definition.claim_codes)
        )
        if atom.polarity in {"negative", "mixed"} or atom.support_relation.startswith("contradict") or contradicted:
            negative.append(atom)
            continue
        if _matches_any(text, definition.direct_patterns):
            direct.append(atom)
        elif _matches_outcome(text, definition.outcome_patterns):
            indirect.append(atom)
        else:
            unattributable.append(atom)
    direct_choice_count = sum(
        1
        for atom in (*direct, *indirect)
        if _matches_any(_normalize_text(atom.clean_comment_text), DIRECT_CHOICE_PATTERNS)
    )
    denominator = eligible_sentence_count if eligible_sentence_count is not None else _eligible_sentence_count(atoms)
    perception_weight = None
    if denominator > 0:
        perception_weight = min(1.0, (len(direct) + 0.5 * len(indirect)) / denominator)
    if negative and (direct or indirect):
        status, status_cn = "mixed", "用户评价分化，正向和反向体验同时存在"
    elif negative and not direct and not indirect:
        status, status_cn = "negative", "用户说出了反向体验"
    elif direct:
        status, status_cn = "direct", "用户直接说到了这项能力或参数"
    elif indirect:
        status, status_cn = "outcome_only", "用户说到了体验结果，但不能拆到单一技术点"
    elif relevant:
        status, status_cn = "unrecognized", "本批评论只有泛化评价，尚未认到具体价值"
    else:
        status, status_cn = "insufficient", "本批评论未观察到相关体验"
    evidence_ids = _dedupe_strings(
        evidence_id
        for atom in (*direct, *indirect, *unattributable, *negative)
        for evidence_id in atom.evidence_ids
    )
    return ClaimValuePmUserUnderstanding(
        status=status,
        status_cn=status_cn,
        eligible_sentence_count=denominator,
        direct_sentence_count=len(direct),
        indirect_sentence_count=len(indirect),
        unattributable_sentence_count=len(unattributable),
        negative_sentence_count=len(negative),
        direct_choice_sentence_count=direct_choice_count,
        perception_weight=_round(perception_weight, 4),
        positive_examples=[_atom_example(item, "direct") for item in direct[:2]] + [_atom_example(item, "indirect") for item in indirect[:2]][: max(0, 3 - min(2, len(direct)))],
        negative_examples=[_atom_example(item, "negative") for item in negative[:2]],
        evidence_ids=evidence_ids,
    )


def build_market_pricing(context: ClaimValuePmContext) -> ClaimValuePmMarketPricing:
    if not context.market_weekly_rows:
        return _empty_market_pricing("缺少目标 SKU 周度价格销量明细。")
    target_size = _screen_size(context.fact_brief)
    pair_curves: list[ClaimValuePmPairCurve] = []
    for competitor in context.competitors:
        competitor_name = _display_name(competitor.model_name, competitor.brand_name, competitor.sku_code)
        competitor_size = _screen_size(competitor.fact_brief)
        exact_size = target_size is not None and competitor_size is not None and math.isclose(target_size, competitor_size, abs_tol=0.5)
        isolation_grade = _overall_configuration_isolation_grade(context.fact_brief, competitor.fact_brief)
        if (competitor.slot_code or "").strip().lower() not in PRICE_CURVE_ROLE_CODES:
            pair_curves.append(
                ClaimValuePmPairCurve(
                    competitor_sku_code=competitor.sku_code,
                    competitor_name=competitor_name,
                    exact_size_match=exact_size,
                    configuration_isolation_grade=isolation_grade,
                    sample_level="insufficient",
                    selection_weight=0.0,
                    limitations=["该既有竞品承担标杆、上下探或情景参照角色，只用于事实观察，不进入当前同价价格曲线。"],
                )
            )
            continue
        if not exact_size:
            pair_curves.append(
                ClaimValuePmPairCurve(
                    competitor_sku_code=competitor.sku_code,
                    competitor_name=competitor_name,
                    exact_size_match=False,
                    configuration_isolation_grade=isolation_grade,
                    sample_level="insufficient",
                    selection_weight=0.0,
                    limitations=["该既有竞品与本品不是精确同尺寸，只用于配置事实观察，不进入价格曲线。"],
                )
            )
            continue
        pair_curves.append(
            build_pair_curve(
                context.market_weekly_rows,
                competitor.market_weekly_rows,
                competitor_sku_code=competitor.sku_code,
                competitor_name=competitor_name,
                selection_confidence=competitor.selection_confidence,
                evidence_completeness_score=competitor.evidence_completeness_score,
                exact_size_match=True,
                configuration_isolation_grade=isolation_grade,
            )
        )
    normalized = [
        item
        for item in pair_curves
        if item.same_price_share is not None
        and item.same_price_method == "same_price_interpolated"
        and item.sample_level in {"strong", "medium"}
        and item.exact_size_match
    ]
    near_observations = [
        item
        for item in pair_curves
        if item.same_price_share is not None
        and item.same_price_method == "near_same_price_observation"
        and item.sample_level in {"strong", "medium", "weak"}
        and item.exact_size_match
    ]
    # Whole-product price acceptance reuses M14's direct market roles. It does
    # not require every sellpoint bundle to be independently attributable;
    # that stricter A/B gate remains on each value unit below.
    l3_eligible = list(normalized)
    strong = [item for item in l3_eligible if item.sample_level == "strong"]
    signs = [1 if (item.same_price_share or 0) > 0.5 else -1 if (item.same_price_share or 0) < 0.5 else 0 for item in l3_eligible]
    nonzero_signs = [item for item in signs if item]
    consistency = None
    if nonzero_signs:
        consistency = max(nonzero_signs.count(1), nonzero_signs.count(-1)) / len(nonzero_signs)
    two_native_pairs_ready = len(l3_eligible) == 2 and len(strong) == 2 and (consistency or 0) == 1
    extended_pool_ready = len(l3_eligible) >= 3 and len(strong) >= 2 and (consistency or 0) >= (2 / 3)
    if two_native_pairs_ready or extended_pool_ready:
        level = "L3"
        name_cn = "稳定直接竞品条件销量承接曲线"
    elif len(normalized) >= 2:
        level = "L2"
        name_cn = "直接竞品条件销量承接曲线"
    elif normalized:
        level = "L1"
        name_cn = "单一竞品同价销量承接观察"
    elif near_observations:
        level = "L1"
        name_cn = "直接竞品近同价销量承接观察"
    else:
        level = "L0"
        name_cn = "整机市场位置描述"
    aggregate_pairs = l3_eligible if level == "L3" else normalized if normalized else near_observations
    weights = [max(item.selection_weight, 0.001) for item in aggregate_pairs]
    shares = [float(item.same_price_share) for item in aggregate_pairs if item.same_price_share is not None]
    same_share = _weighted_median(shares, weights) if shares else None
    advantages = [(value - 0.5) * 100 for value in shares]
    advantage = (same_share - 0.5) * 100 if same_share is not None else None
    interval = _weighted_interval(advantages, weights) if advantages else []
    crossings = [
        (item.hold_gap_amount, item.hold_gap_ratio, item.selection_weight)
        for item in l3_eligible
        if item.hold_gap_amount is not None and item.hold_gap_ratio is not None
    ]
    amount_range: list[float] = []
    ratio_range: list[float] = []
    if level == "L3" and same_share is not None and same_share > 0.5 and len(crossings) >= 2:
        amount_range = _weighted_interval([float(item[0]) for item in crossings], [float(item[2]) for item in crossings])
        ratio_range = _weighted_interval([float(item[1]) for item in crossings], [float(item[2]) for item in crossings])
        hold_cn = f"历史样本中，整机相对直接竞品的销量承接保持价差约为{_money_range_cn(amount_range)}。"
    elif level == "L3" and same_share is not None and same_share > 0.5:
        lower_bounds = [item.hold_gap_lower_bound_ratio for item in l3_eligible if item.hold_gap_lower_bound_ratio is not None]
        if len(lower_bounds) >= 2:
            hold_cn = f"多个直接竞品样本内至少保持到约 +{min(lower_bounds) * 100:.1f}%，但尚未观察到销量承接回到五五开的稳定交点。"
        else:
            hold_cn = "样本不足，暂不计算选择保持价差。"
    elif same_share is not None and same_share <= 0.5:
        hold_cn = "当前未观察到正向选择保持价差。"
    else:
        hold_cn = "样本不足，暂不计算选择保持价差。"
    current_price_raw = _recent_reference_price(context.market_weekly_rows)
    current_price = _business_price(current_price_raw) if current_price_raw else None
    scenarios = _build_price_scenarios(pair_curves, current_price=current_price, enabled=level == "L3")
    price_acceptance_status, price_acceptance_status_cn, price_acceptance_basis_cn = _current_price_acceptance(
        method_level=level,
        same_price_share=same_share,
        scenarios=scenarios,
    )
    limitations = _dedupe_strings(
        [
            limitation
            for item in pair_curves
            for limitation in item.limitations
        ]
    )
    if level != "L3":
        limitations.append("未达到 2 个可用于当前价格比较的强直接竞品且方向一致，价格情景只保留当前价基准。")
    return ClaimValuePmMarketPricing(
        method_level=level,
        method_name_cn=name_cn,
        attribution_status="whole_product_only",
        attribution_status_cn="当前数值只说明整机方案相对直接竞品的历史销量承接，不拆给单个卖点。",
        current_price=_round(current_price, 0),
        valid_pair_count=len(aggregate_pairs),
        strong_pair_count=len(strong),
        direction_consistency=_round(consistency, 4),
        same_price_choice_share=_round(same_share, 4),
        same_price_choice_advantage_pp=_round(advantage, 2),
        same_price_competitor_interval_pp=[_round(value, 2) or 0.0 for value in interval],
        selection_holding_gap_amount_range=[_round(value, 0) or 0.0 for value in amount_range],
        selection_holding_gap_ratio_range=[_round(value, 4) or 0.0 for value in ratio_range],
        holding_gap_status_cn=hold_cn,
        current_price_acceptance_status=price_acceptance_status,
        current_price_acceptance_status_cn=price_acceptance_status_cn,
        current_price_acceptance_basis_cn=price_acceptance_basis_cn,
        pair_curves=pair_curves,
        price_scenarios=scenarios,
        limitations=limitations,
    )


def _current_price_acceptance(
    *,
    method_level: str,
    same_price_share: float | None,
    scenarios: Sequence[ClaimValuePmPriceScenario],
) -> tuple[str, str, str]:
    if method_level != "L3" or same_price_share is None:
        return (
            "insufficient",
            "无法判断",
            "当前直接竞品样本不足，不能判断现价是否已经消耗整机优势。",
        )
    if same_price_share <= 0.5:
        return (
            "no_observed_advantage",
            "未观察到可承接优势",
            "整机在同价条件下的销量承接未高于五五开，当前没有可用于加价判断的正向优势。",
        )
    current = next((item for item in scenarios if item.label_cn == "当前价格"), None)
    current_share = current.comparison_choice_share if current is not None else None
    if current_share is None:
        return (
            "insufficient",
            "无法判断",
            "当前价附近缺少足够的直接竞品样本，不能判断现价是否已经消耗整机优势。",
        )
    if current_share >= 0.55:
        return (
            "room_remaining",
            "仍有承接空间",
            f"当前价格下两款条件销量份额约 {current_share * 100:.1f}%，仍明显高于五五开；历史样本显示整机优势尚未完全被价格消耗。",
        )
    if current_share >= 0.48:
        return (
            "mostly_captured",
            "价格已基本承接",
            f"当前价格下两款条件销量份额约 {current_share * 100:.1f}%，已接近五五开；继续上调前应先做小流量验证。",
        )
    return (
        "over_captured",
        "价格可能承接过度",
        f"当前价格下两款条件销量份额约 {current_share * 100:.1f}%，已低于五五开；历史样本提示现价可能超过整机优势的承接边界。",
    )


def build_pair_curve(
    target_rows: Sequence[ClaimValuePmMarketWeeklyRow],
    competitor_rows: Sequence[ClaimValuePmMarketWeeklyRow],
    *,
    competitor_sku_code: str,
    competitor_name: str,
    selection_confidence: float | None = None,
    evidence_completeness_score: float | None = None,
    exact_size_match: bool = True,
    configuration_isolation_grade: str = "unknown",
) -> ClaimValuePmPairCurve:
    target_panel = _aggregate_week_platform(target_rows)
    competitor_panel = _aggregate_week_platform(competitor_rows)
    common_keys = sorted(set(target_panel).intersection(competitor_panel))
    raw: list[tuple[float, float, float, int]] = []
    excluded = 0
    for key in common_keys:
        target = target_panel[key]
        competitor = competitor_panel[key]
        if target["sales"] <= 0 or competitor["sales"] <= 0 or target["price"] <= 0 or competitor["price"] <= 0:
            excluded += 1
            continue
        gap = (target["price"] - competitor["price"]) / competitor["price"]
        if gap < -0.60 or gap > 1.50:
            excluded += 1
            continue
        total_sales = target["sales"] + competitor["sales"]
        share = target["sales"] / total_sales
        raw.append((gap, share, total_sales, key[0]))
    if not raw:
        return ClaimValuePmPairCurve(
            competitor_sku_code=competitor_sku_code,
            competitor_name=competitor_name,
            exact_size_match=exact_size_match,
            configuration_isolation_grade=configuration_isolation_grade,
            sample_level="insufficient",
            limitations=["没有两款同时具备有效价格和正销量的周平台单元。"],
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
    bin_count = len(binned)
    contains_zero = gap_min <= 0 <= gap_max
    local_zero_supported = _interpolation_supported(observed_bins, 0.0)
    if len(raw) >= 8 and week_count >= 6 and bin_count >= 4 and gap_span >= 0.08 and local_zero_supported:
        sample_level = "strong"
        quality_factor = 1.0
    elif len(raw) >= 6 and bin_count >= 3 and gap_span >= 0.05:
        sample_level = "medium"
        quality_factor = 0.70
    elif len(raw) >= 4 and bin_count >= 2:
        sample_level = "weak"
        quality_factor = 0.35
    else:
        sample_level = "insufficient"
        quality_factor = 0.10
    same_price_share = None
    same_price_method = None
    if contains_zero and local_zero_supported and sample_level != "insufficient":
        same_price_share = evaluate_choice_curve(curve, 0.0, observed_min=gap_min, observed_max=gap_max)
        same_price_method = "same_price_interpolated"
    elif min(abs(gap_min), abs(gap_max)) <= 0.03 and sample_level != "insufficient":
        nearest = gap_min if abs(gap_min) <= abs(gap_max) else gap_max
        same_price_share = evaluate_choice_curve(curve, nearest, observed_min=gap_min, observed_max=gap_max)
        same_price_method = "near_same_price_observation"
    competitor_price = _recent_reference_price(competitor_rows)
    target_price = _recent_reference_price(target_rows)
    hold_ratio = None
    hold_amount = None
    lower_bound = None
    if same_price_share is not None and same_price_share > 0.5:
        crossing = choice_share_crossing(curve, threshold=0.5, start_gap=0.0, observed_min=gap_min, observed_max=gap_max)
        if crossing is not None and _gap_locally_supported(observed_bins, crossing):
            hold_ratio = crossing
            hold_amount = crossing * competitor_price if competitor_price else None
        elif gap_max > 0 and evaluate_choice_curve(curve, gap_max, observed_min=gap_min, observed_max=gap_max) > 0.5:
            lower_bound = gap_max
    confidence = 0.5 if selection_confidence is None else selection_confidence
    completeness = 0.5 if evidence_completeness_score is None else evidence_completeness_score
    selection_weight = max(0.01, confidence * completeness * quality_factor)
    limitations: list[str] = []
    if excluded:
        limitations.append(f"{excluded} 个周平台单元因零销量、无有效价格或异常价差未进入主模型。")
    if not contains_zero:
        limitations.append("历史相对价差范围没有覆盖同价位置，不能做严格同价归一。")
    elif not local_zero_supported:
        limitations.append("虽然历史价差跨过同价位置，但同价附近存在样本空洞，不能插值得到同价结果。")
    if sample_level in {"weak", "insufficient"}:
        limitations.append("该竞品对价格变化或重叠周不足，只能作观察。")
    return ClaimValuePmPairCurve(
        competitor_sku_code=competitor_sku_code,
        competitor_name=competitor_name,
        exact_size_match=exact_size_match,
        configuration_isolation_grade=configuration_isolation_grade,
        sample_level=sample_level,
        valid_cell_count=len(raw),
        distinct_week_count=week_count,
        price_gap_bin_count=bin_count,
        observed_gap_min=_round(gap_min, 4),
        observed_gap_max=_round(gap_max, 4),
        observed_price_gap_bins=[_round(value, 4) or 0.0 for value in observed_bins],
        same_price_share=_round(same_price_share, 4),
        same_price_method=same_price_method,
        same_price_advantage_pp=_round((same_price_share - 0.5) * 100, 2) if same_price_share is not None else None,
        hold_gap_ratio=_round(hold_ratio, 4),
        hold_gap_amount=_round(hold_amount, 0),
        hold_gap_lower_bound_ratio=_round(lower_bound, 4),
        target_reference_price=_round(target_price, 0),
        competitor_reference_price=_round(competitor_price, 0),
        curve_points=[
            ClaimValuePmCurvePoint(
                relative_price_gap=_round(x, 4) or 0.0,
                relative_price_gap_min=_round(x_min, 4),
                relative_price_gap_max=_round(x_max, 4),
                target_choice_share=_round(y, 4) or 0.0,
                weight=_round(weight, 2) or 0.0,
            )
            for x, y, weight, x_min, x_max in curve
        ],
        selection_weight=_round(selection_weight, 4) or 0.01,
        limitations=limitations,
    )


def pava_nonincreasing(points: Sequence[tuple[float, float, float]]) -> list[tuple[float, float, float, float, float]]:
    """Weighted PAVA for a non-increasing y(x) curve."""

    blocks: list[dict[str, float]] = []
    for x, y, weight in sorted(points, key=lambda item: item[0]):
        safe_weight = max(float(weight), 1e-9)
        blocks.append(
            {
                "x_sum": x * safe_weight,
                "y_sum": y * safe_weight,
                "weight": safe_weight,
                "x_min": x,
                "x_max": x,
            }
        )
        while len(blocks) >= 2:
            previous = blocks[-2]
            current = blocks[-1]
            previous_y = previous["y_sum"] / previous["weight"]
            current_y = current["y_sum"] / current["weight"]
            if previous_y >= current_y:
                break
            merged = {
                "x_sum": previous["x_sum"] + current["x_sum"],
                "y_sum": previous["y_sum"] + current["y_sum"],
                "weight": previous["weight"] + current["weight"],
                "x_min": min(previous["x_min"], current["x_min"]),
                "x_max": max(previous["x_max"], current["x_max"]),
            }
            blocks[-2:] = [merged]
    return [
        (
            block["x_sum"] / block["weight"],
            block["y_sum"] / block["weight"],
            block["weight"],
            block["x_min"],
            block["x_max"],
        )
        for block in blocks
    ]


def evaluate_choice_curve(
    curve: Sequence[tuple[float, ...]] | Sequence[ClaimValuePmCurvePoint],
    relative_price_gap: float,
    *,
    observed_min: float,
    observed_max: float,
) -> float | None:
    if relative_price_gap < observed_min - 1e-9 or relative_price_gap > observed_max + 1e-9 or not curve:
        return None
    points: list[tuple[float, float, float, float]] = []
    for item in curve:
        if isinstance(item, ClaimValuePmCurvePoint):
            center = float(item.relative_price_gap)
            y = float(item.target_choice_share)
            x_min = float(item.relative_price_gap_min if item.relative_price_gap_min is not None else center)
            x_max = float(item.relative_price_gap_max if item.relative_price_gap_max is not None else center)
        else:
            center = float(item[0])
            y = float(item[1])
            x_min = float(item[3]) if len(item) >= 5 else center
            x_max = float(item[4]) if len(item) >= 5 else center
        points.append((center, y, x_min, x_max))
    points.sort(key=lambda item: item[0])
    for _, y, x_min, x_max in points:
        if x_min - 1e-12 <= relative_price_gap <= x_max + 1e-12:
            return y
    if relative_price_gap <= points[0][2]:
        return points[0][1]
    if relative_price_gap >= points[-1][3]:
        return points[-1][1]
    for left, right in zip(points, points[1:]):
        left_x, left_y = left[3], left[1]
        right_x, right_y = right[2], right[1]
        if left_x <= relative_price_gap <= right_x:
            if math.isclose(left_x, right_x):
                return (left_y + right_y) / 2
            ratio = (relative_price_gap - left_x) / (right_x - left_x)
            return left_y + ratio * (right_y - left_y)
    return None


def choice_share_crossing(
    curve: Sequence[tuple[float, ...]] | Sequence[ClaimValuePmCurvePoint],
    *,
    threshold: float,
    start_gap: float,
    observed_min: float,
    observed_max: float,
) -> float | None:
    if start_gap < observed_min or start_gap > observed_max:
        return None
    start_value = evaluate_choice_curve(curve, start_gap, observed_min=observed_min, observed_max=observed_max)
    if start_value is None or start_value <= threshold:
        return None
    candidate_gaps = {start_gap, observed_max}
    for item in curve:
        if isinstance(item, ClaimValuePmCurvePoint):
            center = float(item.relative_price_gap)
            x_min = float(item.relative_price_gap_min if item.relative_price_gap_min is not None else center)
            x_max = float(item.relative_price_gap_max if item.relative_price_gap_max is not None else center)
        else:
            center = float(item[0])
            x_min = float(item[3]) if len(item) >= 5 else center
            x_max = float(item[4]) if len(item) >= 5 else center
        if start_gap < x_min <= observed_max:
            candidate_gaps.add(x_min)
        if start_gap < x_max <= observed_max:
            candidate_gaps.add(x_max)
    points = [
        (gap, evaluate_choice_curve(curve, gap, observed_min=observed_min, observed_max=observed_max))
        for gap in sorted(candidate_gaps)
    ]
    points = [(gap, value) for gap, value in points if value is not None]
    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_y > threshold >= right_y:
            if math.isclose(left_y, right_y):
                return right_x
            ratio = (left_y - threshold) / (left_y - right_y)
            return left_x + ratio * (right_x - left_x)
    return None


def _build_value_unit(
    definition: TvValueUnitDefinition,
    *,
    source: ClaimValuePmContext,
    gate: ClaimValuePmDataGate,
    market_pricing: ClaimValuePmMarketPricing,
    eligible_sentence_count: int,
) -> ClaimValuePmValueUnit:
    facts = _unit_product_facts(definition, source.fact_brief)
    conflict_issue_codes = {"m03b_m04c_presence_conflict", "m04c_all_claims_unresolved", "m03b_parameter_conflict"}
    affected = any(
        definition.code in issue.affected_unit_codes
        and issue.severity == "blocking"
        and issue.scope == "product_fact"
        and issue.code in conflict_issue_codes
        for issue in gate.issues
    )
    if affected:
        fact_status = "conflict"
    elif facts:
        fact_status = "confirmed"
    elif _sections(source.fact_brief).get("parameter_fact"):
        fact_status = "unknown"
    else:
        fact_status = "partial"
    fact_status_cn = {
        "confirmed": "产品事实已确认",
        "partial": "产品事实不完整",
        "conflict": "产品事实链存在冲突",
        "unknown": "当前画像未确认该能力",
    }[fact_status]
    understanding = attribute_comment_atoms(definition, source.comment_atoms, eligible_sentence_count=eligible_sentence_count)
    comparisons = [
        _competitor_comparison(definition, source.fact_brief, competitor)
        for competitor in source.competitors
    ]
    pair_curve_by_sku = {item.competitor_sku_code: item for item in market_pricing.pair_curves}
    positive_aligned_pairs = [
        comparison
        for comparison in comparisons
        if comparison.isolation_grade in {"A", "B"}
        and comparison.fact_relation == "target_stronger"
        and (pair_curve := pair_curve_by_sku.get(comparison.sku_code)) is not None
        and pair_curve.sample_level in {"strong", "medium"}
        and pair_curve.same_price_method == "same_price_interpolated"
        and (pair_curve.same_price_advantage_pp or 0) > 0
    ]
    competitor_stronger_count = sum(
        item.fact_relation == "competitor_stronger" and item.isolation_grade in {"A", "B"}
        for item in comparisons
    )
    purchase_role = _purchase_role(
        understanding,
        fact_status=fact_status,
        comparisons=comparisons,
    )
    if fact_status == "conflict":
        readiness, readiness_cn = "not_ready", "先修产品事实链，不进入价格测试"
    elif fact_status not in {"confirmed"}:
        readiness, readiness_cn = "insufficient", "产品事实不足，暂不测试"
    elif understanding.status in {"negative", "mixed"}:
        readiness, readiness_cn = "not_ready", "先修反向体验，不进入价格测试"
    elif purchase_role.status == "direct_reason" and market_pricing.method_level == "L3" and len(positive_aligned_pairs) >= 2:
        if definition.independently_identifiable and understanding.status == "direct":
            readiness, readiness_cn = "single_test", "可进入单项价格测试"
        else:
            readiness, readiness_cn = "bundle_test", "只适合按体验组合做价格测试"
    else:
        readiness, readiness_cn = "insufficient", "证据未达到价格测试门槛"
    if fact_status == "conflict":
        stage = "E0"
    elif fact_status != "confirmed":
        stage = "E1"
    elif understanding.status in {"direct", "outcome_only", "negative", "mixed"}:
        stage = "E2"
    else:
        stage = "E1"
    if stage == "E2" and purchase_role.status == "direct_reason" and len(positive_aligned_pairs) >= 2 and market_pricing.method_level in {"L2", "L3"}:
        stage = "E3"
    if readiness in {"single_test", "bundle_test"}:
        stage = "E4"
    decision_code, decision_cn, validation_cn = _unit_decision(
        definition,
        fact_status=fact_status,
        understanding=understanding,
        readiness=readiness,
        isolated_pair_count=len(positive_aligned_pairs),
        competitor_stronger_count=competitor_stronger_count,
    )
    limitations: list[str] = []
    if understanding.unattributable_sentence_count:
        limitations.append("泛化好评只保留在体验组合，不拆给具体技术参数。")
    if not positive_aligned_pairs:
        limitations.append("现有竞品差异无法隔离到该价值组合，市场结果只作为整机观察。")
    if affected:
        limitations.append("上游事实冲突未修复前，不输出该组合的价格结论。")
    return ClaimValuePmValueUnit(
        unit_code=definition.code,
        unit_name_cn=definition.name_cn,
        product_claim_cn="、".join(facts) if facts else "当前已发布画像没有确认可展示的配置事实",
        linked_param_codes=list(definition.param_codes),
        linked_claim_codes=list(definition.claim_codes),
        product_fact_status=fact_status,
        product_fact_status_cn=fact_status_cn,
        product_fact_items=facts,
        user_understanding=understanding,
        purchase_role=purchase_role,
        weights=ClaimValuePmWeights(
            product_fact_weight=1.0 if fact_status == "confirmed" else 0.5 if fact_status == "partial" else None,
            user_perception_weight=understanding.perception_weight,
            pricing_readiness=readiness,
            pricing_readiness_cn=readiness_cn,
        ),
        evidence_stage=stage,
        competitor_comparison=comparisons,
        decision_code=decision_code,
        decision_cn=decision_cn,
        next_validation_cn=validation_cn,
        limitations=limitations,
        evidence_ids=_dedupe_strings(understanding.evidence_ids),
    )


def _competitor_comparison(
    definition: TvValueUnitDefinition,
    target_fact_brief: dict[str, Any],
    competitor: ClaimValuePmCompetitorSnapshot,
) -> ClaimValuePmCompetitorComparison:
    target_facts = _unit_product_facts(definition, target_fact_brief)
    candidate_facts = _unit_product_facts(definition, competitor.fact_brief)
    relation = _fact_relation(definition, target_fact_brief, competitor.fact_brief)
    other_difference_count = 0
    unknown_count = 0
    for other in TV_VALUE_UNITS:
        if other.code == definition.code:
            continue
        other_relation = _fact_relation(other, target_fact_brief, competitor.fact_brief)
        if other_relation in {"target_stronger", "competitor_stronger", "different"}:
            other_difference_count += 1
        elif other_relation == "unknown":
            unknown_count += 1
    if relation in {"similar", "unknown"}:
        isolation = "unknown"
    elif unknown_count >= 3 or other_difference_count >= 2:
        isolation = "C"
    elif other_difference_count == 1:
        isolation = "B"
    else:
        isolation = "A"
    candidate_understanding = attribute_comment_atoms(
        definition,
        competitor.comment_atoms,
        eligible_sentence_count=_eligible_sentence_count(competitor.comment_atoms),
    )
    market = _sections(competitor.fact_brief).get("market") or {}
    position = market.get("market_position") or {}
    metrics = market.get("market_metrics") or {}
    market_cn = _market_position_cn(position, metrics)
    return ClaimValuePmCompetitorComparison(
        sku_code=competitor.sku_code,
        display_name=_display_name(competitor.model_name, competitor.brand_name, competitor.sku_code),
        selection_role_cn=competitor.slot_name_cn,
        fact_relation=relation,
        target_fact_cn="、".join(target_facts) if target_facts else "本品事实未知",
        competitor_fact_cn="、".join(candidate_facts) if candidate_facts else "竞品事实未知",
        competitor_user_status_cn=candidate_understanding.status_cn,
        market_position_cn=market_cn,
        isolation_grade=isolation,
    )


def _build_price_scenarios(
    pair_curves: Sequence[ClaimValuePmPairCurve],
    *,
    current_price: float | None,
    enabled: bool,
) -> list[ClaimValuePmPriceScenario]:
    if not current_price:
        return []
    changes = (-0.05, -0.03, 0.0, 0.03, 0.05)
    eligible_pairs = [
        item
        for item in pair_curves
        if item.exact_size_match
        and item.sample_level in {"strong", "medium"}
        and item.curve_points
    ]
    scenarios: list[ClaimValuePmPriceScenario] = []
    total_weight = sum(item.selection_weight for item in eligible_pairs) or 1.0
    for change in changes:
        price = _business_price(current_price * (1 + change))
        actual_change = price / current_price - 1
        if change != 0 and not enabled:
            scenarios.append(
                ClaimValuePmPriceScenario(
                    label_cn=_scenario_label(change),
                    price=price,
                    price_change_pct=actual_change,
                    status_cn="样本门槛不足，暂不计算该价格情景。",
                )
            )
            continue
        scenario_values: list[tuple[float, float, float]] = []
        for pair in eligible_pairs:
            competitor_price = pair.competitor_reference_price
            if not competitor_price or pair.observed_gap_min is None or pair.observed_gap_max is None:
                continue
            scenario_gap = (price - competitor_price) / competitor_price
            baseline_gap = (current_price - competitor_price) / competitor_price
            if not _gap_locally_supported(pair.observed_price_gap_bins, scenario_gap):
                continue
            if not _gap_locally_supported(pair.observed_price_gap_bins, baseline_gap):
                continue
            scenario_share = evaluate_choice_curve(
                pair.curve_points,
                scenario_gap,
                observed_min=pair.observed_gap_min,
                observed_max=pair.observed_gap_max,
            )
            baseline_share = evaluate_choice_curve(
                pair.curve_points,
                baseline_gap,
                observed_min=pair.observed_gap_min,
                observed_max=pair.observed_gap_max,
            )
            if scenario_share is not None and baseline_share is not None:
                scenario_values.append((scenario_share, baseline_share, max(pair.selection_weight, 0.001)))
        used_weight = sum(item[2] for item in scenario_values)
        pair_count = len(scenario_values)
        coverage = min(1.0, used_weight / total_weight)
        if not scenario_values or pair_count < (1 if change == 0 else 2) or (change != 0 and coverage < 0.60):
            scenarios.append(
                ClaimValuePmPriceScenario(
                    label_cn=_scenario_label(change),
                    price=price,
                    price_change_pct=actual_change,
                    pair_count=pair_count,
                    weight_coverage=_round(coverage, 4) or 0.0,
                    status_cn="历史观察范围覆盖不足，暂不展示结果。",
                )
            )
            continue
        share = sum(item[0] * item[2] for item in scenario_values) / used_weight
        base = sum(item[1] * item[2] for item in scenario_values) / used_weight
        choice_index = share / base * 100 if base > 0 else 100.0
        revenue_index = choice_index * price / current_price
        scenarios.append(
            ClaimValuePmPriceScenario(
                label_cn=_scenario_label(change),
                price=price,
                price_change_pct=actual_change,
                pair_count=pair_count,
                weight_coverage=_round(coverage, 4) or 0.0,
                comparison_choice_share=_round(share, 4),
                choice_index=_round(choice_index, 1),
                comparison_revenue_index=_round(revenue_index, 1),
                status_cn="历史直接竞品条件销量承接观察，未外推到样本范围外。",
            )
        )
    return scenarios


def _scenario_share(
    pair_curves: Sequence[ClaimValuePmPairCurve],
    *,
    target_price: float,
    with_meta: bool = False,
) -> float | tuple[float | None, float, int] | None:
    values: list[tuple[float, float]] = []
    for pair in pair_curves:
        if (
            not pair.exact_size_match
            or pair.sample_level not in {"strong", "medium"}
        ):
            continue
        competitor_price = pair.competitor_reference_price
        if not competitor_price or pair.observed_gap_min is None or pair.observed_gap_max is None:
            continue
        gap = (target_price - competitor_price) / competitor_price
        if not _gap_locally_supported(pair.observed_price_gap_bins, gap):
            continue
        share = evaluate_choice_curve(
            pair.curve_points,
            gap,
            observed_min=pair.observed_gap_min,
            observed_max=pair.observed_gap_max,
        )
        if share is not None:
            values.append((share, max(pair.selection_weight, 0.001)))
    if not values:
        return (None, 0.0, 0) if with_meta else None
    total_weight = sum(weight for _, weight in values)
    result = sum(value * weight for value, weight in values) / total_weight
    return (result, total_weight, len(values)) if with_meta else result


def _business_price(value: float) -> float:
    increment = 100.0 if value >= 3000 else 50.0 if value >= 1000 else 10.0
    return round(value / increment) * increment


def _aggregate_week_platform(rows: Sequence[ClaimValuePmMarketWeeklyRow]) -> dict[tuple[int, str], dict[str, float]]:
    buckets: dict[tuple[int, str], dict[str, float]] = {}
    for row in rows:
        if (row.price_check_status or "").lower() not in VALID_PRICE_STATUSES:
            continue
        sales = float(row.sales_volume or 0)
        amount = float(row.sales_amount or 0)
        price = float(row.avg_price or 0)
        if sales < 0 or amount < 0 or price < 0:
            continue
        key = (row.period_week_index, row.platform_type or "unknown")
        bucket = buckets.setdefault(key, {"sales": 0.0, "amount": 0.0, "price_weighted": 0.0, "price_weight": 0.0})
        bucket["sales"] += sales
        bucket["amount"] += amount
        if price > 0:
            weight = sales if sales > 0 else 1.0
            bucket["price_weighted"] += price * weight
            bucket["price_weight"] += weight
    result: dict[tuple[int, str], dict[str, float]] = {}
    for key, bucket in buckets.items():
        if bucket["sales"] > 0 and bucket["amount"] > 0:
            price = bucket["amount"] / bucket["sales"]
        elif bucket["price_weight"] > 0:
            price = bucket["price_weighted"] / bucket["price_weight"]
        else:
            price = 0.0
        result[key] = {"sales": bucket["sales"], "amount": bucket["amount"], "price": price}
    return result


def _bin_choice_points(raw: Sequence[tuple[float, float, float, int]]) -> list[tuple[float, float, float]]:
    bins: dict[int, dict[str, float]] = {}
    for x, y, weight, _ in raw:
        key = int(round(x / 0.02))
        bucket = bins.setdefault(key, {"x_sum": 0.0, "y_sum": 0.0, "weight": 0.0})
        bucket["x_sum"] += x * weight
        bucket["y_sum"] += y * weight
        bucket["weight"] += weight
    return [
        (bucket["x_sum"] / bucket["weight"], bucket["y_sum"] / bucket["weight"], bucket["weight"])
        for _, bucket in sorted(bins.items())
    ]


def _gap_locally_supported(
    observed_bins: Sequence[float],
    gap: float,
    *,
    direct_distance: float = 0.025,
    side_distance: float = 0.05,
    max_neighbor_gap: float = 0.08,
) -> bool:
    points = sorted(float(item) for item in observed_bins)
    if not points:
        return False
    if min(abs(item - gap) for item in points) <= direct_distance:
        return True
    left = [item for item in points if item < gap]
    right = [item for item in points if item > gap]
    if not left or not right:
        return False
    nearest_left = max(left)
    nearest_right = min(right)
    return (
        gap - nearest_left <= side_distance
        and nearest_right - gap <= side_distance
        and nearest_right - nearest_left <= max_neighbor_gap
    )


def _interpolation_supported(
    observed_bins: Sequence[float],
    gap: float,
    *,
    exact_distance: float = 0.005,
    side_distance: float = 0.05,
    max_neighbor_gap: float = 0.08,
) -> bool:
    points = sorted(float(item) for item in observed_bins)
    if not points:
        return False
    if min(abs(item - gap) for item in points) <= exact_distance:
        return True
    left = [item for item in points if item < gap]
    right = [item for item in points if item > gap]
    if not left or not right:
        return False
    nearest_left = max(left)
    nearest_right = min(right)
    return (
        gap - nearest_left <= side_distance
        and nearest_right - gap <= side_distance
        and nearest_right - nearest_left <= max_neighbor_gap
    )


def _recent_reference_price(rows: Sequence[ClaimValuePmMarketWeeklyRow]) -> float | None:
    valid = [row for row in rows if (row.price_check_status or "").lower() in VALID_PRICE_STATUSES and (row.sales_volume or 0) > 0]
    if not valid:
        return None
    recent_weeks = sorted({row.period_week_index for row in valid}, reverse=True)[:4]
    selected = [row for row in valid if row.period_week_index in recent_weeks]
    total_sales = sum(float(row.sales_volume or 0) for row in selected)
    total_amount = sum(float(row.sales_amount or 0) for row in selected)
    if total_sales > 0 and total_amount > 0:
        return total_amount / total_sales
    weighted = [(float(row.avg_price or 0), float(row.sales_volume or 0)) for row in selected if (row.avg_price or 0) > 0]
    if not weighted:
        return None
    weight_sum = sum(weight for _, weight in weighted) or len(weighted)
    return sum(price * (weight or 1.0) for price, weight in weighted) / weight_sum


def _unit_product_facts(definition: TvValueUnitDefinition, fact_brief: dict[str, Any]) -> list[str]:
    param = _sections(fact_brief).get("parameter_fact") or {}
    core = param.get("core_params") or {}
    flattened = _flatten_param_values(core)
    result: list[str] = []
    for code in definition.param_codes:
        if code not in flattened or not _known_value(flattened[code]):
            continue
        result.append(f"{PARAM_LABELS.get(code, code)}={_format_value(flattened[code])}")
    claim = _sections(fact_brief).get("claim_fact") or {}
    claim_codes = set(claim.get("fact_claim_codes") or claim.get("claim_codes") or [])
    if claim_codes.intersection(definition.claim_codes) and not result:
        result.append("产品侧已发布相关卖点表达")
    return _dedupe_strings(result)


def _flatten_param_values(payload: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return result
    for key, value in payload.items():
        if isinstance(value, dict) and "normalized_value" in value:
            result[str(key)] = value.get("normalized_value")
        elif isinstance(value, dict):
            nested = _flatten_param_values(value)
            if nested:
                result.update(nested)
            elif _known_value(value):
                result[str(key)] = value
        elif _known_value(value):
            result[str(key)] = value
    return result


def _fact_relation(definition: TvValueUnitDefinition, target_fact: dict[str, Any], competitor_fact: dict[str, Any]) -> str:
    target = _unit_comparison_params(definition, target_fact)
    competitor = _unit_comparison_params(definition, competitor_fact)
    target_codes = set(target)
    competitor_codes = set(competitor)
    if target_codes != competitor_codes or len(target_codes) < MIN_COMPARABLE_PARAM_COUNT:
        return "unknown"
    shared = sorted(target_codes)
    numeric_signs: list[int] = []
    different = False
    for code in shared:
        left_raw = target[code]
        right_raw = competitor[code]
        if isinstance(left_raw, bool) and isinstance(right_raw, bool):
            if left_raw != right_raw:
                numeric_signs.append(1 if left_raw else -1)
            continue
        left = _numeric_value(left_raw)
        right = _numeric_value(right_raw)
        if code in PARAM_VALUE_TIERS and left is not None and right is not None:
            left_tier = _value_tier(left, PARAM_VALUE_TIERS[code])
            right_tier = _value_tier(right, PARAM_VALUE_TIERS[code])
            if left_tier != right_tier:
                numeric_signs.append(1 if left_tier > right_tier else -1)
        elif _stable_value(left_raw) != _stable_value(right_raw):
            different = True
    if numeric_signs and all(item > 0 for item in numeric_signs):
        return "target_stronger"
    if numeric_signs and all(item < 0 for item in numeric_signs):
        return "competitor_stronger"
    if numeric_signs or different:
        return "different"
    return "similar"


def _unit_comparison_params(definition: TvValueUnitDefinition, fact_brief: dict[str, Any]) -> dict[str, Any]:
    flattened = _flatten_param_values(((_sections(fact_brief).get("parameter_fact") or {}).get("core_params") or {}))
    result: dict[str, Any] = {}
    for code in definition.param_codes:
        value = flattened.get(code)
        if not _known_value(value):
            continue
        canonical = PARAM_COMPARISON_ALIASES.get(code, code)
        result.setdefault(canonical, value)
    return result


def _value_tier(value: float, thresholds: Sequence[float]) -> int:
    return sum(value >= threshold for threshold in thresholds)


def _screen_size(fact_brief: dict[str, Any]) -> float | None:
    market = _sections(fact_brief).get("market") or {}
    market_size = (market.get("market_position") or {}).get("screen_size_inch")
    value = _numeric_value(market_size)
    if value is not None:
        return value
    params = _flatten_param_values(((_sections(fact_brief).get("parameter_fact") or {}).get("core_params") or {}))
    return _numeric_value(params.get("screen_size_inch"))


def _overall_configuration_isolation_grade(target_fact: dict[str, Any], competitor_fact: dict[str, Any]) -> str:
    relations = [_fact_relation(definition, target_fact, competitor_fact) for definition in TV_VALUE_UNITS]
    known = [item for item in relations if item != "unknown"]
    if not known:
        return "unknown"
    unknown_count = relations.count("unknown")
    difference_count = sum(item in {"target_stronger", "competitor_stronger", "different"} for item in known)
    if unknown_count >= 3 or difference_count >= 3:
        return "C"
    if difference_count == 2:
        return "B"
    return "A"


def _purchase_role(
    understanding: ClaimValuePmUserUnderstanding,
    *,
    fact_status: str,
    comparisons: Sequence[ClaimValuePmCompetitorComparison],
) -> ClaimValuePmPurchaseRole:
    if understanding.status == "mixed":
        return ClaimValuePmPurchaseRole(
            status="mixed_experience",
            status_cn="评价分化，尚不能作为稳定选购理由",
            basis_cn="同一价值组合同时出现正向和反向购后体验。",
        )
    if understanding.status == "negative":
        return ClaimValuePmPurchaseRole(
            status="drag",
            status_cn="可能成为排除因素",
            basis_cn="现有评论只观察到反向体验，需先修产品。",
        )
    if understanding.direct_choice_sentence_count > 0 and understanding.status in {"direct", "outcome_only"}:
        return ClaimValuePmPurchaseRole(
            status="direct_reason",
            status_cn="已有直接选购表达",
            basis_cn=f"有 {understanding.direct_choice_sentence_count} 条相关评论明确表达看中、对比后选择或因为该体验购买。",
        )
    if understanding.status in {"direct", "outcome_only"}:
        return ClaimValuePmPurchaseRole(
            status="post_purchase_satisfaction",
            status_cn="已形成购后体验，尚未证明影响选购",
            basis_cn="用户说出了能力或体验结果，但没有明确表达因此购买或对比后选择。",
        )
    similar_count = sum(item.fact_relation == "similar" for item in comparisons)
    if fact_status == "confirmed" and similar_count >= 2:
        return ClaimValuePmPurchaseRole(
            status="entry_requirement_hypothesis",
            status_cn="同价位普遍具备，可能是入围门槛",
            basis_cn="既有直接竞品普遍具备相近事实，但当前没有购买前淘汰数据，仍需验证。",
        )
    return ClaimValuePmPurchaseRole(
        status="not_proven",
        status_cn="尚未证明影响选购",
        basis_cn="当前只有产品事实或泛化评价，没有直接选购证据。",
    )


def _unit_decision(
    definition: TvValueUnitDefinition,
    *,
    fact_status: str,
    understanding: ClaimValuePmUserUnderstanding,
    readiness: str,
    isolated_pair_count: int,
    competitor_stronger_count: int,
) -> tuple[str, str, str]:
    if fact_status == "conflict":
        return "BLOCKED_DATA", "先修配置事实链，本轮不做卖点取舍或加价判断。", "核对 SKU 版本、参数来源与卖点事实映射后重跑。"
    if understanding.status in {"negative", "mixed"}:
        return "FIX_EXPERIENCE", "用户已经说出反向体验，先修产品，不放大宣传。", "复测负向体验发生场景，确认修复后负向比例下降。"
    if fact_status == "confirmed" and competitor_stronger_count >= 2:
        return "CLOSE_COMPETITOR_GAP", "重点竞品在该组合上更强，先判断是否补短板，不把整机表现当成本品卖点优势。", "核对参数档位、真实体验和丢单场景，确认补强后再做价格测试。"
    if readiness in {"single_test", "bundle_test"}:
        return "PRICE_TEST", "产品事实、用户结果和竞品对照方向一致，可进入小范围价格梯度测试。", "固定其他配置，用同一人群和渠道比较选择率是否守住。"
    if fact_status == "confirmed" and understanding.status in {"direct", "outcome_only"}:
        return "KEEP_STRENGTHEN", "用户已经接住体验，建议保留并用用户结果表达，不把整机优势拆成单技术金额。", "补足可隔离竞品或配置对照，再判断是否进入价格测试。"
    if fact_status == "confirmed" and understanding.unattributable_sentence_count:
        return "COMBINE_AND_TELL", "用户只说总体体验，相关技术点合并成一个体验组合，不单独讲或加价。", "用具体场景问题验证用户能否说出该组合带来的结果。"
    if fact_status == "confirmed":
        return "OBSERVE_ONLY", "产品有这项能力，但本批用户反馈尚未说明它带来了什么。", "补购买前选择、详情页行为或定向体验测试。"
    if isolated_pair_count:
        return "VERIFY_FACT", "竞品存在差异，但本品事实尚未确认，先补事实再判断动作。", "完成参数和卖点事实复核。"
    return "OBSERVE_ONLY", "当前证据不足，不做配置或价格动作。", "先补产品事实和用户体验证据。"


def _decision_actions(
    gate: ClaimValuePmDataGate,
    units: Sequence[ClaimValuePmValueUnit],
    market: ClaimValuePmMarketPricing,
) -> list[ClaimValuePmAction]:
    actions: list[ClaimValuePmAction] = []
    blocking_messages = [item.message_cn for item in gate.issues if item.severity == "blocking"]
    product_fact_blocked = any(
        item.severity == "blocking" and item.scope == "product_fact"
        for item in gate.issues
    )
    if blocking_messages:
        actions.append(
            ClaimValuePmAction(
                priority=1,
                action_type="数据核验",
                action_cn="先修参数事实与卖点事实链，再讨论单项卖点的价格作用。",
                why_cn="；".join(blocking_messages[:2]),
                success_signal_cn="同一产品版本的参数事实、卖点表达、能力数量和确认状态完全一致。",
            )
        )
    received = [item for item in units if item.user_understanding.status in {"direct", "outcome_only"} and item.product_fact_status == "confirmed"]
    if received:
        names = "、".join(item.unit_name_cn for item in received[:2])
        actions.append(
            ClaimValuePmAction(
                priority=len(actions) + 1,
                action_type="产品与表达",
                action_cn=f"优先保留并做强{names}，传播时直接讲用户结果。",
                why_cn="这些组合已有产品事实和可归因用户结果，证据层级高于只存在技术名的卖点。",
                success_signal_cn="后续评论和购买前研究能稳定说出同一体验结果。",
            )
        )
    unreceived = [item for item in units if item.product_fact_status == "confirmed" and item.user_understanding.status in {"unrecognized", "insufficient"}]
    if unreceived:
        names = "、".join(item.unit_name_cn for item in unreceived[:2])
        actions.append(
            ClaimValuePmAction(
                priority=len(actions) + 1,
                action_type="卖点表达",
                action_cn=f"{names}暂不独立占加价理由，先改成场景化体验语言。",
                why_cn="产品有配置，但本批用户没有明确说出它带来的结果。",
                success_signal_cn="定向测试中用户无需提示即可复述具体使用结果。",
            )
        )
    if market.method_level == "L3" and not product_fact_blocked:
        actions.append(
            ClaimValuePmAction(
                priority=len(actions) + 1,
                action_type="价格验证",
                action_cn="按报告价格情景做小流量梯度测试，不把整机结果拆给单个技术点。",
                why_cn=market.holding_gap_status_cn,
                success_signal_cn="价格上调后销量承接指数未跌破预设停止线。",
            )
        )
    return actions[:5]


def _test_backlog(
    gate: ClaimValuePmDataGate,
    units: Sequence[ClaimValuePmValueUnit],
    market: ClaimValuePmMarketPricing,
) -> list[ClaimValuePmAction]:
    result: list[ClaimValuePmAction] = []
    product_blockers = [item for item in gate.issues if item.severity == "blocking" and item.scope == "product_fact"]
    if product_blockers:
        return [
            ClaimValuePmAction(
                priority=1,
                action_type="先修数据",
                action_cn="先解决产品事实冲突，本轮不安排卖点选择或价格测试。",
                why_cn="；".join(item.message_cn for item in product_blockers[:2]),
                success_signal_cn="参数事实与卖点事实对同一 SKU、同一规格口径一致。",
            )
        ]
    candidates = sorted(
        units,
        key=lambda item: (
            item.product_fact_status == "confirmed",
            item.user_understanding.unattributable_sentence_count,
            item.user_understanding.indirect_sentence_count,
        ),
        reverse=True,
    )
    for unit in candidates[:3]:
        result.append(
            ClaimValuePmAction(
                priority=len(result) + 1,
                action_type="组合测试" if unit.weights.pricing_readiness != "single_test" else "单项测试",
                action_cn=f"验证“{unit.unit_name_cn}”在固定其他配置时是否提高选择。",
                why_cn=unit.weights.pricing_readiness_cn,
                success_signal_cn="同价选择率提升且价格上调后仍保持预设选择阈值。",
            )
        )
    if market.method_level != "L3":
        result.append(
            ClaimValuePmAction(
                priority=len(result) + 1,
                action_type="补市场样本",
                action_cn="补足直接竞品共同在售周和有效价格变化。",
                why_cn="当前历史样本不足以稳定计算选择保持价差。",
                success_signal_cn="两类直接价格竞品都具备充分价格变化，且销量承接方向一致。",
            )
        )
    return result[:4]


def _headline(gate: ClaimValuePmDataGate, units: Sequence[ClaimValuePmValueUnit], market: ClaimValuePmMarketPricing) -> str:
    if gate.status == "blocked":
        return "关键产品或市场事实缺失，本轮先补数据，不做卖点取舍和价格判断。"
    conflicts = [item for item in units if item.product_fact_status == "conflict"]
    received = [item.unit_name_cn for item in units if item.user_understanding.status in {"direct", "outcome_only"} and item.product_fact_status == "confirmed"]
    generic = [item.unit_name_cn for item in units if item.user_understanding.unattributable_sentence_count > 0]
    if conflicts:
        market_note = "整机销量承接仍可观察" if market.method_level != "L0" else "整机市场样本也不足"
        return f"当前配置事实链存在冲突，{market_note}，但不能把结果归到具体卖点；先修事实链，再决定保留、升级或价格测试。"
    if received:
        first = "、".join(received[:2])
        return f"用户目前最明确接住的是{first}；其他技术名是否能支撑价格仍要看独立配置对照。"
    if generic:
        return f"用户说到了{'、'.join(generic[:2])}的总体好感，但没有认到具体技术；先合并表达，不做单技术加价。"
    return "本批数据尚未形成可执行的卖点价格结论，先补用户结果和直接竞品对照。"


def _empty_market_pricing(reason: str) -> ClaimValuePmMarketPricing:
    return ClaimValuePmMarketPricing(
        method_level="L0",
        method_name_cn="整机市场位置描述",
        attribution_status="not_available",
        attribution_status_cn="当前没有可用的销量承接量化结果。",
        holding_gap_status_cn="样本不足，暂不计算选择保持价差。",
        limitations=[reason],
    )


def _audit_payload(context: ClaimValuePmContext, *, method_level: str) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": context.project_id,
        "category_code": context.category_code,
        "batch_id": context.batch_id,
        "competitor_selection_batch_id": context.competitor_selection_batch_id,
        "target_sku_code": context.target.get("sku_code"),
        "schema_version": "sellpoint_value_pm_v1",
        "method_level": method_level,
        "source_versions": context.source_versions,
        "sample_summary": {
            "comment_atom_count": len(context.comment_atoms),
            "market_weekly_row_count": len(context.market_weekly_rows),
            "competitor_count": len(context.competitors),
        },
        "purchase_reason_hypothesis": {
            "source": context.purchase_reason_hypothesis.get("source"),
            "found": context.purchase_reason_hypothesis.get("found"),
            "consumption_state": context.purchase_reason_hypothesis.get("consumption_state"),
            "review_required": context.purchase_reason_hypothesis.get("review_required"),
            "usage": "只作为待验证假设，不参与独立证据计数",
        },
        "evidence_ids": context.evidence_ids,
    }


def _sections(fact_brief: dict[str, Any]) -> dict[str, Any]:
    return fact_brief.get("sections") or {}


def _eligible_sentence_count(atoms: Sequence[ClaimValuePmCommentAtom]) -> int:
    return len(
        {
            (item.source_comment_key, item.sentence_seq)
            for item in atoms
            if item.dimension_type in PRODUCT_EXPERIENCE_TYPES
        }
    )


def _atom_example(atom: ClaimValuePmCommentAtom, attribution: str) -> dict[str, Any]:
    return {
        "text": atom.clean_comment_text,
        "attribution": attribution,
        "polarity": atom.polarity,
        "evidence_ids": atom.evidence_ids,
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _matches_any(text: str, patterns: Sequence[str]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _matches_outcome(text: str, patterns: Sequence[str]) -> bool:
    hits = sum(1 for pattern in patterns if re.search(pattern, text, re.IGNORECASE))
    return hits >= 2 or (hits == 1 and len(text) >= 7)


def _market_position_cn(position: dict[str, Any], metrics: dict[str, Any]) -> str:
    price_pct = position.get("price_percentile_in_size")
    volume_pct = position.get("volume_percentile_in_size")
    parts: list[str] = []
    if price_pct is not None:
        parts.append(f"同尺寸价格分位约{float(price_pct) * 100:.0f}%")
    if volume_pct is not None:
        parts.append(f"销量分位约{float(volume_pct) * 100:.0f}%")
    if metrics.get("price_wavg") is not None:
        parts.append(f"观察期成交均价约{float(metrics['price_wavg']):.0f}元")
    return "，".join(parts) or "市场位置数据不足"


def _fact_items_by_code(fact_brief: dict[str, Any]) -> dict[str, Any]:
    return _flatten_param_values(((_sections(fact_brief).get("parameter_fact") or {}).get("core_params") or {}))


def _known_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown", "未知", "-", "null", "none"}
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("value", "amount", "count", "hz"):
            if key in value:
                return _numeric_value(value[key])
    if isinstance(value, str):
        match = re.search(r"-?\d+(?:[.]\d+)?", value.replace(",", ""))
        if match:
            return float(match.group())
    return None


def _stable_value(value: Any) -> str:
    if isinstance(value, dict):
        return "|".join(f"{key}:{_stable_value(item)}" for key, item in sorted(value.items()))
    if isinstance(value, (list, tuple)):
        return "|".join(_stable_value(item) for item in value)
    return str(value).strip().lower()


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "有" if value else "无"
    if isinstance(value, dict):
        if "value" in value:
            unit = value.get("unit") or ""
            return f"{value['value']}{unit}"
        return "/".join(str(item) for item in value.values() if _known_value(item))
    return str(value)


def _display_name(model_name: str | None, brand_name: str | None, sku_code: str) -> str:
    return " ".join(item for item in (brand_name, model_name) if item) or sku_code


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    rows = sorted(zip(values, weights), key=lambda item: item[0])
    threshold = sum(weight for _, weight in rows) / 2
    cumulative = 0.0
    for value, weight in rows:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return rows[-1][0]


def _weighted_interval(values: Sequence[float], weights: Sequence[float]) -> list[float]:
    if not values:
        return []
    return [_weighted_quantile(values, weights, 0.25), _weighted_quantile(values, weights, 0.75)]


def _weighted_quantile(values: Sequence[float], weights: Sequence[float], quantile: float) -> float:
    rows = sorted(zip(values, weights), key=lambda item: item[0])
    threshold = sum(weight for _, weight in rows) * quantile
    cumulative = 0.0
    for value, weight in rows:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return rows[-1][0]


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _money_range_cn(values: Sequence[float]) -> str:
    if len(values) < 2:
        return "暂不可计算"
    low, high = sorted(values[:2])
    return f"{low:.0f}–{high:.0f}元"


def _scenario_label(change: float) -> str:
    if math.isclose(change, 0.0):
        return "当前价格"
    return f"价格{'上调' if change > 0 else '下调'}{abs(change) * 100:.0f}%"


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(float(value), digits)


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
