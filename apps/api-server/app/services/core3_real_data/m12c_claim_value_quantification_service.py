"""M12C claim value quantification.

M12C is a deterministic result layer. It consumes the current fact and semantic
profiles and estimates observable claim value inside comparable pools. The
numbers are market-contribution estimates, not causal effects.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_RULE_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3BaseRepository, Core3RepositoryContext


ANALYSIS_POPULATION_READY = "claim_value_ready"
ANALYSIS_POPULATION_READY_WITH_COMMENT = "claim_value_ready_with_comment"
MARKET_WINDOW_FULL_OBSERVED = "full_observed_window"

M12C_ROLE_PREMIUM = "premium_driver_estimated"
M12C_ROLE_SALES = "sales_driver_estimated"
M12C_ROLE_BASIC = "basic_threshold"
M12C_ROLE_VALUE_BUNDLE = "value_bundle_claim"
M12C_ROLE_WEAK_USER = "weak_user_perception_claim"
M12C_ROLE_HIGH_PRICE_INTERCEPT = "high_price_competitor_intercept"
M12C_ROLE_PRICE_UP = "price_up_opportunity"
M12C_ROLE_BRAND = "brand_claim_only"
M12C_ROLE_USER_NEED = "user_validated_need"
M12C_ROLE_DRAG = "drag_factor"
M12C_ROLE_OPPORTUNITY = "opportunity_gap"
M12C_ROLE_SAMPLE = "sample_insufficient"
M12C_ROLE_UNIQUE = "unique_payment_potential"

POSITIVE_ROLES = {M12C_ROLE_PREMIUM, M12C_ROLE_SALES, M12C_ROLE_VALUE_BUNDLE}
OPPORTUNITY_ROLES = {M12C_ROLE_OPPORTUNITY, M12C_ROLE_HIGH_PRICE_INTERCEPT, M12C_ROLE_PRICE_UP}
MIN_POOL_SKU_COUNT = 3
MIN_WEAK_POOL_SKU_COUNT = 3
MIN_GROUP_SKU_COUNT = 1
M12C_PREMIUM_MIN_SALES_RATIO = Decimal("0.7000")
M12C_PREMIUM_MIN_REVENUE_RATIO = Decimal("1.0000")
M12C_PREMIUM_REVENUE_BACKUP_MIN_SALES_RATIO = Decimal("0.6000")
M12C_FORCE_THRESHOLD_CLAIM_CODES = {
    # Interface availability is an entry-ticket signal in the current TV taxonomy.
    # If a later taxonomy splits out a scarce high-spec implementation, that new
    # claim can be measured separately instead of inheriting this threshold rule.
    "tv_claim_hdmi21_connectivity",
    "tv_claim_miniled_display",
}
M12C_SCENE_CONTEXT_CLAIM_CODES = {
    "tv_claim_theater_scene",
}
M12C_STRICT_SUPPORT_PARAM_CODES: dict[str, tuple[str, ...]] = {
    "tv_claim_eye_care_display": ("low_blue_light_flag", "flicker_free_flag", "eye_care_certification", "anti_glare_flag"),
    "tv_claim_dolby_audio_video": ("dolby_vision_flag", "dolby_atmos_flag", "speaker_output_power_w"),
}
M12C_TIER_DIFFERENTIATED_CLAIM_CODES = {
    "tv_claim_hdr_high_brightness",
    "tv_claim_local_dimming",
    "tv_claim_picture_engine_ai",
    "tv_claim_chip_performance",
    "tv_claim_wide_color_accuracy",
    "tv_claim_refresh_rate",
    "tv_claim_high_refresh_rate",
}

M12C_CLAIM_TYPE_PREMIUM = "premium_payment_claim"
M12C_CLAIM_TYPE_SHARE = "share_conversion_claim"
M12C_CLAIM_TYPE_CUSTOMER_VALUE = "customer_value_claim"
M12C_CLAIM_TYPE_THRESHOLD = "threshold_claim"
M12C_CLAIM_TYPE_PENDING = "pending_activation_claim"
M12C_CLAIM_TYPE_BRAND = "brand_claim"
M12C_CLAIM_TYPE_INTERCEPT = "competitor_intercept_claim"
M12C_CLAIM_TYPE_PRICE_PRESSURE = "price_pressure_claim"
M12C_CLAIM_TYPE_SAMPLE = "sample_insufficient_claim"
M12C_CLAIM_TYPE_UNIQUE = "unique_payment_potential_claim"

M12C_SCORE_WEIGHTS = {
    "battlefield_relevance": Decimal("0.20"),
    "parameter_competitiveness": Decimal("0.25"),
    "comment_perception": Decimal("0.25"),
    "competitor_difference": Decimal("0.15"),
    "market_validation": Decimal("0.15"),
}
M12C_UNIQUE_SCORE_WEIGHTS = {
    "battlefield_relevance": Decimal("0.30"),
    "parameter_competitiveness": Decimal("0.30"),
    "comment_perception": Decimal("0.25"),
    "competitor_gap": Decimal("0.15"),
}

M12C_PARAM_LEVEL_LEADING = "leading_advantage"
M12C_PARAM_LEVEL_STRONG = "strong_advantage"
M12C_PARAM_LEVEL_PARITY = "parity_threshold"
M12C_PARAM_LEVEL_WEAK = "weak_or_missing"
M12C_PARAM_LEVEL_SPARSE = "sparse_unknown"

M04C_PARAM_SUPPORT_STRONG_SPECIFIC = "strong_specific_support"
M04C_PARAM_SUPPORT_STRONG_NUMERIC = "strong_numeric_or_tier_support"
M04C_PARAM_SUPPORT_BROAD_GENERIC = "broad_generic_support"
M04C_PARAM_SUPPORT_WEAK_INDIRECT = "weak_indirect_support"
M04C_PARAM_SUPPORT_NO_PARAM = "no_param_support"
M04C_WTP_GUARD_ELIGIBLE = "eligible_strong_param"
M04C_WTP_GUARD_BLOCKED_GENERIC = "blocked_generic_param"
M04C_WTP_GUARD_BLOCKED_NO_PARAM = "blocked_no_param"
M04C_WTP_GUARD_NOT_SCOPE = "not_product_wtp_scope"
M04C_WTP_GUARD_UNKNOWN = "unknown"
M12C_POSITIVE_WTP_GUARDS = {M04C_WTP_GUARD_ELIGIBLE}
M12C_BLOCKED_WTP_GUARDS = {M04C_WTP_GUARD_BLOCKED_GENERIC, M04C_WTP_GUARD_BLOCKED_NO_PARAM, M04C_WTP_GUARD_NOT_SCOPE}

M12C_TARGET_FACT_CLAIM = "target_fact_claim"
M12C_TARGET_PARAM_CAPABILITY = "target_param_capability"
M12C_COMPETITOR_GAP = "competitor_opportunity_gap"

M12C_CLAIM_PARAM_FALLBACKS: dict[str, tuple[str, ...]] = {
    "tv_claim_hdr_high_brightness": ("declared_brightness_nit_or_band", "hdr_support_flag"),
    "tv_claim_local_dimming": ("local_dimming_zone_count",),
    "tv_claim_picture_engine_ai": ("picture_engine_chip", "ai_picture_engine_flag", "processor_chip_model"),
    "tv_claim_chip_performance": ("processor_chip_model", "processor_vendor", "cpu_core_count", "cpu_frequency_ghz"),
    "tv_claim_wide_color_accuracy": ("color_gamut_ratio", "wide_color_gamut_pct", "color_gamut_percent", "high_color_gamut_flag", "quantum_dot_flag"),
    "tv_claim_high_refresh_rate": ("declared_refresh_rate_hz", "native_refresh_rate_hz", "refresh_rate_hz"),
    "tv_claim_refresh_rate": ("declared_refresh_rate_hz", "native_refresh_rate_hz", "refresh_rate_hz"),
    "tv_claim_gaming_low_latency": ("declared_refresh_rate_hz", "hdmi_2_1_port_count", "hdmi21_flag", "hdmi_version_mix"),
    "tv_claim_hdmi21_connectivity": ("hdmi_2_1_port_count", "hdmi21_flag", "hdmi_version_mix"),
    "tv_claim_miniled_display": ("mini_led_flag", "mini_led_type", "display_tech_class", "declared_brightness_nit_or_band", "local_dimming_zone_count"),
    "tv_claim_eye_care_display": ("low_blue_light_flag", "flicker_free_flag", "eye_care_certification", "anti_glare_flag"),
    "tv_claim_dolby_audio_video": ("dolby_vision_flag", "dolby_atmos_flag", "hdr_support_flag"),
    "tv_claim_theater_scene": (),
}

M12C_PARAM_ALIASES: dict[str, tuple[str, ...]] = {
    "declared_brightness_nit_or_band": ("declared_brightness_nit_or_band", "peak_brightness_nits", "brightness_nit", "brightness_nits", "亮度", "峰值亮度"),
    "hdr_support_flag": ("hdr_support_flag", "hdr_flag", "HDR"),
    "local_dimming_zone_count": ("local_dimming_zone_count", "dimming_zone_count", "local_dimming_zones", "控光分区", "背光分区"),
    "picture_engine_chip": ("picture_engine_chip", "ai_picture_engine", "画质芯片", "画质引擎"),
    "ai_picture_engine_flag": ("ai_picture_engine_flag", "ai_picture_flag", "AI画质"),
    "processor_chip_model": ("processor_chip_model", "chip_model", "soc_model", "处理器", "芯片"),
    "processor_vendor": ("processor_vendor", "chip_vendor", "芯片厂商"),
    "cpu_core_count": ("cpu_core_count", "cpu_cores", "CPU核心"),
    "cpu_frequency_ghz": ("cpu_frequency_ghz", "cpu_frequency", "CPU频率"),
    "color_gamut_ratio": ("color_gamut_ratio", "color_gamut_percent", "wide_color_gamut_pct", "色域", "广色域"),
    "wide_color_gamut_pct": ("wide_color_gamut_pct", "color_gamut_percent", "color_gamut_ratio", "色域"),
    "color_gamut_percent": ("color_gamut_percent", "wide_color_gamut_pct", "color_gamut_ratio", "色域"),
    "high_color_gamut_flag": ("high_color_gamut_flag", "wide_color_gamut_flag", "广色域"),
    "quantum_dot_flag": ("quantum_dot_flag", "qd_flag", "量子点"),
    "declared_refresh_rate_hz": ("declared_refresh_rate_hz", "native_refresh_rate_hz", "refresh_rate_hz", "刷新率"),
    "native_refresh_rate_hz": ("native_refresh_rate_hz", "declared_refresh_rate_hz", "refresh_rate_hz", "刷新率"),
    "refresh_rate_hz": ("refresh_rate_hz", "declared_refresh_rate_hz", "native_refresh_rate_hz", "刷新率"),
    "hdmi_2_1_port_count": ("hdmi_2_1_port_count", "hdmi21_port_count", "HDMI2.1接口数量"),
    "hdmi21_flag": ("hdmi21_flag", "hdmi_2_1_flag", "HDMI2.1"),
    "hdmi_version_mix": ("hdmi_version_mix", "hdmi_version", "HDMI版本"),
    "mini_led_flag": ("mini_led_flag", "miniled_flag", "MiniLED"),
    "mini_led_type": ("mini_led_type", "miniled_type", "MiniLED类型"),
    "display_tech_class": ("display_tech_class", "display_technology", "显示技术"),
    "low_blue_light_flag": ("low_blue_light_flag", "low_blue_flag", "低蓝光"),
    "flicker_free_flag": ("flicker_free_flag", "no_flicker_flag", "无频闪"),
    "eye_care_certification": ("eye_care_certification", "eye_care_cert", "护眼认证"),
    "anti_glare_flag": ("anti_glare_flag", "anti_reflection_flag", "抗反光", "防眩光"),
    "dolby_vision_flag": ("dolby_vision_flag", "dolby_vision", "杜比视界"),
    "dolby_atmos_flag": ("dolby_atmos_flag", "dolby_atmos", "杜比全景声"),
    "screen_size_inch": ("screen_size_inch", "screen_size", "尺寸"),
    "speaker_output_power_w": ("speaker_output_power_w", "speaker_power_w", "音响功率"),
}

M12C_NUMERIC_GROUP_PARAM_LABELS: dict[str, str] = {
    "declared_brightness_nit_or_band": "亮度",
    "local_dimming_zone_count": "控光分区",
    "declared_refresh_rate_hz": "刷新率",
    "native_refresh_rate_hz": "刷新率",
    "refresh_rate_hz": "刷新率",
    "processor_chip_model": "芯片型号",
    "cpu_core_count": "CPU 核心数",
    "cpu_frequency_ghz": "CPU 频率",
    "color_gamut_ratio": "色域",
    "wide_color_gamut_pct": "色域",
    "color_gamut_percent": "色域",
    "hdmi_2_1_port_count": "HDMI2.1 接口数",
    "speaker_output_power_w": "音响功率",
}


@dataclass(frozen=True)
class M12CWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


@dataclass(frozen=True)
class M12CServiceResult:
    status: Core3RunStatus
    input_count: int
    output_count: int
    warnings: list[str]
    summary: dict[str, Any]
    created_output_count: int = 0
    reused_output_count: int = 0
    updated_output_count: int = 0


@dataclass(frozen=True)
class MarketState:
    sku_code: str
    brand_name: str | None
    model_name: str | None
    size_tier: str
    exact_size_tier: str
    price_band: str
    price: Decimal
    sales_volume_total: Decimal
    sales_amount_total: Decimal
    avg_weekly_sales_volume: Decimal
    avg_weekly_sales_amount: Decimal
    active_week_count: int
    window_start_week: int | None
    window_end_week: int | None


@dataclass(frozen=True)
class ClaimState:
    sku_code: str
    claim_code: str
    claim_name: str
    claim_dimension: str
    claim_subtype: str
    claim_kind: str
    param_support_status: str
    supporting_param_codes: tuple[str, ...]
    supporting_param_snapshot: Mapping[str, Any]
    match_score: Decimal
    confidence: Decimal
    fact_claim_flag: bool
    service_separate_flag: bool
    evidence_ids: tuple[str, ...]
    param_support_level: str = M04C_PARAM_SUPPORT_NO_PARAM
    param_support_specificity: str = ""
    primary_supporting_param_codes: tuple[str, ...] = ()
    generic_support_param_codes: tuple[str, ...] = ()
    source_claim_group_id: str | None = None
    same_source_param_group_id: str | None = None
    canonical_claim_code: str | None = None
    canonical_claim_name: str | None = None
    wtp_input_guard: str = M04C_WTP_GUARD_UNKNOWN
    member_claim_codes: tuple[str, ...] = ()
    member_claim_names: tuple[str, ...] = ()

    @property
    def is_supported(self) -> bool:
        status = self.param_support_status.lower()
        return self.fact_claim_flag and not self.service_separate_flag and status not in {"unsupported", "not_supported", "missing"}

    @property
    def payment_value_eligible(self) -> bool:
        return _effective_wtp_input_guard(self) in M12C_POSITIVE_WTP_GUARDS

    @property
    def param_support_strength(self) -> Decimal:
        status = self.param_support_status.lower()
        guard = _effective_wtp_input_guard(self)
        if guard == M04C_WTP_GUARD_BLOCKED_GENERIC:
            return Decimal("0.4500")
        if guard in {M04C_WTP_GUARD_BLOCKED_NO_PARAM, M04C_WTP_GUARD_NOT_SCOPE}:
            return Decimal("0.1500")
        if status in {"supported", "strong_supported", "fact_supported"}:
            return Decimal("1.0000")
        if status in {"partially_supported", "partial_supported", "weak_supported", "unknown"}:
            return Decimal("0.6000")
        if status in {"param_unknown", "missing"}:
            return Decimal("0.3500")
        return Decimal("0.1000")


@dataclass(frozen=True)
class ParamProfileState:
    sku_code: str
    values: Mapping[str, Any]
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class CommentState:
    sku_code: str
    supported_claim_codes: tuple[str, ...]
    contradicted_claim_codes: tuple[str, ...]
    positive_sentence_count: int
    negative_sentence_count: int
    confidence: Decimal

    def support_strength(self, claim_code: str) -> Decimal:
        if claim_code in self.contradicted_claim_codes:
            return Decimal("0.1500")
        if claim_code in self.supported_claim_codes:
            return Decimal("1.0000")
        return Decimal("0.4500")

    def has_negative(self, claim_code: str) -> bool:
        return claim_code in self.contradicted_claim_codes


def _comment_support_strength(comment: CommentState, claim: ClaimState | None, pool: "ClaimPool") -> Decimal:
    claim_codes = _claim_code_family(claim, pool)
    if any(code in comment.contradicted_claim_codes for code in claim_codes):
        return Decimal("0.1500")
    if any(code in comment.supported_claim_codes for code in claim_codes):
        return Decimal("1.0000")
    return Decimal("0.4500")


def _comment_has_negative(comment: CommentState, claim: ClaimState | None, pool: "ClaimPool") -> bool:
    return any(code in comment.contradicted_claim_codes for code in _claim_code_family(claim, pool))


def _claim_code_family(claim: ClaimState | None, pool: "ClaimPool") -> tuple[str, ...]:
    codes: list[str] = [pool.claim_code, *pool.member_claim_codes]
    if claim:
        codes.extend([claim.claim_code, *(claim.member_claim_codes or ())])
    return _unique_tuple(codes)


@dataclass(frozen=True)
class SemanticState:
    sku_code: str
    contexts: tuple[tuple[str, str, str, str], ...]
    allocation_weights: Mapping[tuple[str, str], Decimal] | None = None

    def support_strength(self, context_type: str, context_code: str) -> Decimal:
        for item_type, item_code, _, relation_role in self.contexts:
            if item_type == context_type and item_code == context_code:
                if relation_role == "primary":
                    return Decimal("1.0000")
                if relation_role == "secondary":
                    return Decimal("0.7500")
                if relation_role == "opportunity":
                    return Decimal("0.5500")
                if relation_role == "drag":
                    return Decimal("0.3000")
        return Decimal("0.4500") if context_type == "market_pool" else Decimal("0.0000")

    def allocation_weight(self, context_type: str, context_code: str) -> Decimal:
        key = (context_type, context_code)
        if self.allocation_weights and key in self.allocation_weights:
            return _q6(self.allocation_weights[key])
        raw_weights = {
            (item_type, item_code): _fallback_context_weight(relation_role)
            for item_type, item_code, _, relation_role in self.contexts
            if item_type == "battlefield" and relation_role in {"primary", "secondary"}
        }
        raw = raw_weights.get(key, Decimal("0.000000"))
        total = sum(raw_weights.values(), Decimal("0.000000"))
        if total > Decimal("1.000000"):
            return _q6(raw / total)
        return _q6(raw)


@dataclass(frozen=True)
class ClaimPool:
    claim_code: str
    claim_name: str
    context_type: str
    context_code: str
    context_name: str
    size_tier: str
    price_band_group: str
    sku_codes: tuple[str, ...]
    with_claim_skus: tuple[str, ...]
    without_claim_skus: tuple[str, ...]
    unknown_skus: tuple[str, ...]
    sample_status: str
    quality_flags: tuple[str, ...]
    relaxation_path: tuple[dict[str, Any], ...]
    pool_relax_level: str = "L0"
    baseline_price_method: str = "weighted_median_excluding_target"
    member_claim_codes: tuple[str, ...] = ()
    comparison_basis: str = "claim_presence"
    comparison_param_code: str | None = None
    comparison_threshold_value: str | None = None
    comparison_group_label_cn: str = "有卖点组"
    control_group_label_cn: str = "对照组"


@dataclass(frozen=True)
class ClaimGroupSplit:
    with_skus: tuple[str, ...]
    without_skus: tuple[str, ...]
    unknown_skus: tuple[str, ...]
    comparison_basis: str
    comparison_param_code: str | None = None
    comparison_threshold_value: str | None = None
    comparison_group_label_cn: str = "有卖点组"
    control_group_label_cn: str = "对照组"


class M12CRepository(Core3BaseRepository):
    def list_market_states(self, *, batch_id: str, market_window: str, product_category: str) -> dict[str, MarketState]:
        prefix = "TV" if product_category.upper() == "TV" else "AC"
        stmt = (
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == self.project_id)
            .where(entities.Core3SkuMarketProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuMarketProfile.batch_id == batch_id)
            .where(entities.Core3SkuMarketProfile.analysis_window == market_window)
            .where(entities.Core3SkuMarketProfile.rule_version == CORE3_M07_RULE_VERSION)
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
            .where(entities.Core3SkuMarketProfile.sku_code.like(f"{prefix}%"))
            .order_by(entities.Core3SkuMarketProfile.sku_code)
        )
        rows = list(self.db.execute(stmt).scalars())
        return {row.sku_code: _market_state(row) for row in rows}

    def list_claim_states(self, *, batch_id: str, product_category: str) -> dict[str, dict[str, ClaimState]]:
        stmt = (
            select(entities.Core3SkuClaimFact)
            .where(entities.Core3SkuClaimFact.project_id == self.project_id)
            .where(entities.Core3SkuClaimFact.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimFact.batch_id == batch_id)
            .where(entities.Core3SkuClaimFact.product_category == product_category.upper())
            .where(entities.Core3SkuClaimFact.rule_version == CORE3_M04C_TV_RULE_VERSION)
            .where(entities.Core3SkuClaimFact.is_current.is_(True))
            .order_by(entities.Core3SkuClaimFact.sku_code, entities.Core3SkuClaimFact.claim_code)
        )
        result: dict[str, dict[str, ClaimState]] = defaultdict(dict)
        for row in self.db.execute(stmt).scalars():
            guard = _row_wtp_input_guard(row)
            canonical_claim_code = _row_canonical_claim_code(row)
            canonical_claim_name = _row_canonical_claim_name(row)
            state = ClaimState(
                sku_code=row.sku_code,
                claim_code=canonical_claim_code,
                claim_name=canonical_claim_name,
                claim_dimension=row.claim_dimension or "",
                claim_subtype=row.claim_subtype or "",
                claim_kind=row.claim_kind or "",
                param_support_status=row.param_support_status or "unknown",
                supporting_param_codes=tuple(str(item) for item in (row.supporting_param_codes or [])),
                supporting_param_snapshot=row.supporting_param_snapshot_json or {},
                match_score=_q4(row.match_score),
                confidence=_q4(row.confidence),
                fact_claim_flag=bool(row.fact_claim_flag),
                service_separate_flag=bool(row.service_separate_flag),
                evidence_ids=tuple(str(item) for item in (row.evidence_ids or [])),
                param_support_level=_row_param_support_level(row),
                param_support_specificity=str(getattr(row, "param_support_specificity", "") or ""),
                primary_supporting_param_codes=tuple(str(item) for item in (getattr(row, "primary_supporting_param_codes", None) or [])),
                generic_support_param_codes=tuple(str(item) for item in (getattr(row, "generic_support_param_codes", None) or [])),
                source_claim_group_id=getattr(row, "source_claim_group_id", None),
                same_source_param_group_id=getattr(row, "same_source_param_group_id", None),
                canonical_claim_code=canonical_claim_code,
                canonical_claim_name=canonical_claim_name,
                wtp_input_guard=guard,
                member_claim_codes=(str(row.claim_code),),
                member_claim_names=(str(row.claim_name),),
            )
            existing = result[row.sku_code].get(canonical_claim_code)
            if existing is None or state.confidence > existing.confidence:
                result[row.sku_code][canonical_claim_code] = _merge_claim_states(existing, state)
            elif existing is not None:
                result[row.sku_code][canonical_claim_code] = _merge_claim_states(existing, state)
        return dict(result)

    def list_param_states(self, *, batch_id: str, product_category: str) -> dict[str, ParamProfileState]:
        prefix = "TV" if product_category.upper() == "TV" else "AC"
        rule_version = CORE3_M03B_AC_RULE_VERSION if product_category.upper() == "AC" else CORE3_M03B_RULE_VERSION
        stmt = (
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == self.project_id)
            .where(entities.Core3SkuParamProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuParamProfile.batch_id == batch_id)
            .where(entities.Core3SkuParamProfile.rule_version == rule_version)
            .where(entities.Core3SkuParamProfile.sku_code.like(f"{prefix}%"))
            .order_by(entities.Core3SkuParamProfile.sku_code)
        )
        result: dict[str, ParamProfileState] = {}
        for row in self.db.execute(stmt).scalars():
            result[row.sku_code] = ParamProfileState(
                sku_code=row.sku_code,
                values=_param_profile_values(row),
                evidence_ids=tuple(str(item) for item in (row.evidence_ids or [])),
            )
        return result

    def list_comment_states(self, *, batch_id: str, product_category: str) -> dict[str, CommentState]:
        stmt = (
            select(entities.Core3SkuCommentFactProfile)
            .where(entities.Core3SkuCommentFactProfile.project_id == self.project_id)
            .where(entities.Core3SkuCommentFactProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
            .where(entities.Core3SkuCommentFactProfile.product_category == product_category.upper())
            .where(entities.Core3SkuCommentFactProfile.rule_version == CORE3_M05C_TV_RULE_VERSION)
            .where(entities.Core3SkuCommentFactProfile.is_current.is_(True))
            .order_by(entities.Core3SkuCommentFactProfile.sku_code)
        )
        return {
            row.sku_code: CommentState(
                sku_code=row.sku_code,
                supported_claim_codes=tuple(str(item) for item in (row.supported_claim_codes or [])),
                contradicted_claim_codes=tuple(str(item) for item in (row.contradicted_claim_codes or [])),
                positive_sentence_count=int(row.positive_sentence_count or 0),
                negative_sentence_count=int(row.negative_sentence_count or 0),
                confidence=_q4(row.confidence),
            )
            for row in self.db.execute(stmt).scalars()
        }

    def list_semantic_states(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
    ) -> dict[str, SemanticState]:
        contexts_by_sku: dict[str, list[tuple[str, str, str, str]]] = defaultdict(list)
        self._append_battlefield_contexts(batch_id, product_category, contexts_by_sku)
        allocation_weights = self._m11d_allocation_weights(batch_id, product_category, analysis_population, market_window)
        allocated_skus = set(allocation_weights)
        if allocated_skus:
            contexts_by_sku = {sku: value for sku, value in contexts_by_sku.items() if sku in allocated_skus}
        return {
            sku: SemanticState(
                sku_code=sku,
                contexts=tuple(items),
                allocation_weights=allocation_weights.get(sku, {}),
            )
            for sku, items in contexts_by_sku.items()
        }

    def list_dimension_names(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
    ) -> dict[tuple[str, str], str]:
        stmt = (
            select(entities.Core3SemanticMarketDimensionSummary)
            .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
            .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code.value)
            .where(entities.Core3SemanticMarketDimensionSummary.batch_id == batch_id)
            .where(entities.Core3SemanticMarketDimensionSummary.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == _m11d_population(analysis_population))
            .where(entities.Core3SemanticMarketDimensionSummary.market_window == market_window)
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
        )
        return {(row.dimension_type, row.dimension_code): row.dimension_name for row in self.db.execute(stmt).scalars()}

    def list_dimension_market_spaces(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
    ) -> dict[tuple[str, str], entities.Core3SemanticMarketDimensionSummary]:
        stmt = (
            select(entities.Core3SemanticMarketDimensionSummary)
            .where(entities.Core3SemanticMarketDimensionSummary.project_id == self.project_id)
            .where(entities.Core3SemanticMarketDimensionSummary.category_code == self.category_code.value)
            .where(entities.Core3SemanticMarketDimensionSummary.batch_id == batch_id)
            .where(entities.Core3SemanticMarketDimensionSummary.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketDimensionSummary.analysis_population == _m11d_population(analysis_population))
            .where(entities.Core3SemanticMarketDimensionSummary.market_window == market_window)
            .where(entities.Core3SemanticMarketDimensionSummary.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketDimensionSummary.is_current.is_(True))
        )
        return {(row.dimension_type, row.dimension_code): row for row in self.db.execute(stmt).scalars()}

    def save_pools(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3ClaimValueContextPool, rows, unique_fields=(
            "batch_id", "product_category", "market_window", "analysis_population", "claim_code", "context_type", "context_code", "size_tier", "price_band_group", "rule_version", "is_current",
        ), hash_field="pool_hash")

    def save_metrics(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3ClaimValuePoolMetric, rows, unique_fields=(
            "batch_id", "pool_id", "claim_code", "rule_version", "is_current",
        ))

    def save_quantifications(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3SkuClaimValueQuantification, rows, unique_fields=(
            "batch_id", "sku_code", "claim_code", "context_type", "context_code", "size_tier", "price_band_group", "rule_version", "is_current",
        ))

    def save_attributions(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3SkuClaimContributionAttribution, rows, unique_fields=(
            "batch_id", "sku_code", "context_type", "context_code", "size_tier", "price_band_group", "rule_version", "is_current",
        ))

    def retire_stale_quantifications(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
        rule_version: str,
        sku_codes: set[str],
        active_rows: Sequence[dict[str, Any]],
    ) -> int:
        active_keys = {
            (
                row["sku_code"],
                row["claim_code"],
                row["context_type"],
                row["context_code"],
                row["size_tier"],
                row["price_band_group"],
            )
            for row in active_rows
        }
        stmt = (
            select(entities.Core3SkuClaimValueQuantification)
            .where(entities.Core3SkuClaimValueQuantification.project_id == self.project_id)
            .where(entities.Core3SkuClaimValueQuantification.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimValueQuantification.batch_id == batch_id)
            .where(entities.Core3SkuClaimValueQuantification.product_category == product_category.upper())
            .where(entities.Core3SkuClaimValueQuantification.analysis_population == analysis_population)
            .where(entities.Core3SkuClaimValueQuantification.market_window == market_window)
            .where(entities.Core3SkuClaimValueQuantification.rule_version == rule_version)
            .where(entities.Core3SkuClaimValueQuantification.is_current.is_(True))
        )
        if sku_codes:
            stmt = stmt.where(entities.Core3SkuClaimValueQuantification.sku_code.in_(sorted(sku_codes)))
        retired = 0
        for record in self.db.execute(stmt).scalars():
            key = (
                record.sku_code,
                record.claim_code,
                record.context_type,
                record.context_code,
                record.size_tier,
                record.price_band_group,
            )
            if key in active_keys:
                continue
            record.is_current = False
            retired += 1
        if retired:
            self.db.flush()
        return retired

    def retire_stale_attributions(
        self,
        *,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
        rule_version: str,
        sku_codes: set[str],
        active_rows: Sequence[dict[str, Any]],
    ) -> int:
        active_keys = {
            (
                row["sku_code"],
                row["context_type"],
                row["context_code"],
                row["size_tier"],
                row["price_band_group"],
            )
            for row in active_rows
        }
        stmt = (
            select(entities.Core3SkuClaimContributionAttribution)
            .where(entities.Core3SkuClaimContributionAttribution.project_id == self.project_id)
            .where(entities.Core3SkuClaimContributionAttribution.category_code == self.category_code.value)
            .where(entities.Core3SkuClaimContributionAttribution.batch_id == batch_id)
            .where(entities.Core3SkuClaimContributionAttribution.product_category == product_category.upper())
            .where(entities.Core3SkuClaimContributionAttribution.analysis_population == analysis_population)
            .where(entities.Core3SkuClaimContributionAttribution.market_window == market_window)
            .where(entities.Core3SkuClaimContributionAttribution.rule_version == rule_version)
            .where(entities.Core3SkuClaimContributionAttribution.is_current.is_(True))
        )
        if sku_codes:
            stmt = stmt.where(entities.Core3SkuClaimContributionAttribution.sku_code.in_(sorted(sku_codes)))
        retired = 0
        for record in self.db.execute(stmt).scalars():
            key = (
                record.sku_code,
                record.context_type,
                record.context_code,
                record.size_tier,
                record.price_band_group,
            )
            if key in active_keys:
                continue
            record.is_current = False
            retired += 1
        if retired:
            self.db.flush()
        return retired

    def save_dimension_summaries(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3ClaimValueDimensionSummary, rows, unique_fields=(
            "batch_id", "claim_code", "dimension_type", "dimension_code", "size_tier", "price_band_group", "analysis_population", "market_window", "rule_version", "is_current",
        ))

    def save_review_issues(self, rows: Sequence[dict[str, Any]]) -> M12CWriteResult:
        return self._save_many(entities.Core3ClaimValueReviewIssue, rows, unique_fields=(
            "batch_id", "issue_scope", "sku_code", "claim_code", "pool_id", "issue_code", "input_fingerprint",
        ))

    def _append_task_contexts(self, batch_id: str, product_category: str, result: dict[str, list[tuple[str, str, str, str]]]) -> None:
        stmt = (
            select(entities.Core3M09cSkuUserTaskProfile)
            .where(entities.Core3M09cSkuUserTaskProfile.project_id == self.project_id)
            .where(entities.Core3M09cSkuUserTaskProfile.category_code == self.category_code.value)
            .where(entities.Core3M09cSkuUserTaskProfile.batch_id == batch_id)
            .where(entities.Core3M09cSkuUserTaskProfile.product_category == product_category.upper())
            .where(entities.Core3M09cSkuUserTaskProfile.rule_version == CORE3_M09C_TV_RULE_VERSION)
            .where(entities.Core3M09cSkuUserTaskProfile.is_current.is_(True))
        )
        for row in self.db.execute(stmt).scalars():
            if row.primary_user_task_code:
                result[row.sku_code].append(("user_task", row.primary_user_task_code, row.primary_user_task_code, "primary"))
            for code in row.secondary_user_task_codes_json or []:
                result[row.sku_code].append(("user_task", str(code), str(code), "secondary"))
            for code in row.drag_factor_task_codes_json or []:
                result[row.sku_code].append(("user_task", str(code), str(code), "drag"))

    def _append_group_contexts(self, batch_id: str, product_category: str, result: dict[str, list[tuple[str, str, str, str]]]) -> None:
        stmt = (
            select(entities.Core3M10cSkuTargetGroupProfile)
            .where(entities.Core3M10cSkuTargetGroupProfile.project_id == self.project_id)
            .where(entities.Core3M10cSkuTargetGroupProfile.category_code == self.category_code.value)
            .where(entities.Core3M10cSkuTargetGroupProfile.batch_id == batch_id)
            .where(entities.Core3M10cSkuTargetGroupProfile.product_category == product_category.upper())
            .where(entities.Core3M10cSkuTargetGroupProfile.rule_version == CORE3_M10C_TV_RULE_VERSION)
            .where(entities.Core3M10cSkuTargetGroupProfile.is_current.is_(True))
        )
        for row in self.db.execute(stmt).scalars():
            if row.primary_target_group_code:
                result[row.sku_code].append(("target_group", row.primary_target_group_code, row.primary_target_group_code, "primary"))
            for code in row.secondary_target_group_codes_json or []:
                result[row.sku_code].append(("target_group", str(code), str(code), "secondary"))
            for code in row.unmet_group_need_codes_json or []:
                result[row.sku_code].append(("target_group", str(code), str(code), "drag"))

    def _append_battlefield_contexts(self, batch_id: str, product_category: str, result: dict[str, list[tuple[str, str, str, str]]]) -> None:
        stmt = (
            select(entities.Core3SkuValueBattlefieldProfile)
            .where(entities.Core3SkuValueBattlefieldProfile.project_id == self.project_id)
            .where(entities.Core3SkuValueBattlefieldProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuValueBattlefieldProfile.batch_id == batch_id)
            .where(entities.Core3SkuValueBattlefieldProfile.product_category == product_category.upper())
            .where(entities.Core3SkuValueBattlefieldProfile.rule_version == CORE3_M11C_TV_RULE_VERSION)
            .where(entities.Core3SkuValueBattlefieldProfile.is_current.is_(True))
        )
        for row in self.db.execute(stmt).scalars():
            if row.primary_battlefield_code:
                result[row.sku_code].append(("battlefield", row.primary_battlefield_code, row.primary_battlefield_code, "primary"))
            for code in row.secondary_battlefield_codes_json or []:
                result[row.sku_code].append(("battlefield", str(code), str(code), "secondary"))

    def _m11d_allocation_weights(
        self,
        batch_id: str,
        product_category: str,
        analysis_population: str,
        market_window: str,
    ) -> dict[str, dict[tuple[str, str], Decimal]]:
        stmt = (
            select(
                entities.Core3SemanticMarketAllocation.sku_code,
                entities.Core3SemanticMarketAllocation.dimension_type,
                entities.Core3SemanticMarketAllocation.dimension_code,
                entities.Core3SemanticMarketAllocation.allocation_weight,
            )
            .where(entities.Core3SemanticMarketAllocation.project_id == self.project_id)
            .where(entities.Core3SemanticMarketAllocation.category_code == self.category_code.value)
            .where(entities.Core3SemanticMarketAllocation.batch_id == batch_id)
            .where(entities.Core3SemanticMarketAllocation.product_category == product_category.upper())
            .where(entities.Core3SemanticMarketAllocation.analysis_population == _m11d_population(analysis_population))
            .where(entities.Core3SemanticMarketAllocation.market_window == market_window)
            .where(entities.Core3SemanticMarketAllocation.dimension_type == "battlefield")
            .where(entities.Core3SemanticMarketAllocation.allocation_value_type == "positive_value")
            .where(entities.Core3SemanticMarketAllocation.allocation_weight > Decimal("0"))
            .where(entities.Core3SemanticMarketAllocation.rule_version == CORE3_M11D_RULE_VERSION)
            .where(entities.Core3SemanticMarketAllocation.is_current.is_(True))
        )
        result: dict[str, dict[tuple[str, str], Decimal]] = defaultdict(dict)
        for sku_code, dimension_type, dimension_code, allocation_weight in self.db.execute(stmt).all():
            result[str(sku_code)][(str(dimension_type), str(dimension_code))] = _q6(allocation_weight)
        return dict(result)

    def _save_many(self, model_cls: Any, payloads: Sequence[dict[str, Any]], *, unique_fields: tuple[str, ...], hash_field: str = "result_hash") -> M12CWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            existing = self._find_existing(model_cls, payload, unique_fields)
            if existing is None:
                record = model_cls(**payload)
                self.db.add(record)
                self.db.flush()
                records.append(record)
                created_count += 1
                continue
            if getattr(existing, hash_field) == payload.get(hash_field):
                _assign(existing, payload)
                self.db.flush()
                records.append(existing)
                reused_count += 1
                continue
            _assign(existing, payload)
            self.db.flush()
            records.append(existing)
            updated_count += 1
        return M12CWriteResult(tuple(records), created_count=created_count, reused_count=reused_count, updated_count=updated_count)

    def _find_existing(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = select(model_cls)
        for field in unique_fields:
            stmt = stmt.where(getattr(model_cls, field) == payload.get(field))
        return self.db.execute(stmt.limit(1)).scalar_one_or_none()


class M12CClaimValueQuantificationService:
    def __init__(self, repository: M12CRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        product_category: str,
        market_window: str = MARKET_WINDOW_FULL_OBSERVED,
        analysis_population: str = ANALYSIS_POPULATION_READY_WITH_COMMENT,
        target_sku_codes: Sequence[str] = (),
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M12C_RULE_VERSION,
    ) -> M12CServiceResult:
        normalized_category = product_category.upper()
        markets_all = self.repository.list_market_states(batch_id=batch_id, market_window=market_window, product_category=normalized_category)
        claims_all = self.repository.list_claim_states(batch_id=batch_id, product_category=normalized_category)
        param_profiles_all = self.repository.list_param_states(batch_id=batch_id, product_category=normalized_category)
        comments_all = self.repository.list_comment_states(batch_id=batch_id, product_category=normalized_category)
        semantics_all = self.repository.list_semantic_states(
            batch_id=batch_id,
            product_category=normalized_category,
            analysis_population=analysis_population,
            market_window=market_window,
        )
        dimension_names = self.repository.list_dimension_names(
            batch_id=batch_id,
            product_category=normalized_category,
            analysis_population=analysis_population,
            market_window=market_window,
        )
        dimension_spaces = self.repository.list_dimension_market_spaces(
            batch_id=batch_id,
            product_category=normalized_category,
            analysis_population=analysis_population,
            market_window=market_window,
        )

        scope = set(target_sku_codes or ())
        comparable_skus = set(markets_all) & set(claims_all) & set(semantics_all)
        if analysis_population == ANALYSIS_POPULATION_READY_WITH_COMMENT:
            comparable_skus &= set(comments_all)
        comparable_skus = {sku for sku in comparable_skus if claims_all.get(sku)}
        output_skus = comparable_skus & scope if scope else set(comparable_skus)
        if not comparable_skus or not output_skus:
            return M12CServiceResult(
                status=Core3RunStatus.WARNING,
                input_count=0,
                output_count=0,
                warnings=["M12C 没有找到同时具备市场、卖点、语义图谱和所需评论事实的 SKU。"],
                summary={
                    "batch_id": batch_id,
                    "product_category": normalized_category,
                    "market_window": market_window,
                    "analysis_population": analysis_population,
                    "eligible_sku_count": 0,
                    "comparable_sku_count": len(comparable_skus),
                    "target_sku_codes": sorted(scope),
                },
            )

        markets = {sku: markets_all[sku] for sku in sorted(comparable_skus)}
        claims = {sku: claims_all[sku] for sku in sorted(comparable_skus)}
        param_profiles = {sku: param_profiles_all[sku] for sku in sorted(comparable_skus) if sku in param_profiles_all}
        comments = {sku: comments_all.get(sku, _empty_comment(sku)) for sku in sorted(comparable_skus)}
        semantics = {sku: semantics_all[sku] for sku in sorted(comparable_skus)}
        pools = _build_pools(
            markets=markets,
            claims=claims,
            semantics=semantics,
            dimension_names=dimension_names,
            param_profiles=param_profiles,
        )
        pool_rows, metric_rows, metric_by_pool = _pool_and_metric_rows(
            pools=pools,
            markets=markets,
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        quant_rows, quant_by_sku_context = _quantification_rows(
            pools=pools,
            metric_by_pool=metric_by_pool,
            markets=markets,
            claims=claims,
            param_profiles=param_profiles,
            comments=comments,
            semantics=semantics,
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
            output_sku_codes=output_skus,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        attribution_rows = _attribution_rows(
            quant_by_sku_context=quant_by_sku_context,
            markets=markets,
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        summary_rows = _dimension_summary_rows(
            quant_rows=quant_rows,
            dimension_spaces=dimension_spaces,
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        review_rows = _review_issue_rows(
            pools=pools,
            batch_id=batch_id,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            product_category=normalized_category,
            market_window=market_window,
            analysis_population=analysis_population,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )

        pool_write = self.repository.save_pools(pool_rows)
        metric_write = self.repository.save_metrics(metric_rows)
        quant_write = self.repository.save_quantifications(quant_rows)
        attr_write = self.repository.save_attributions(attribution_rows)
        retired_quant_count = self.repository.retire_stale_quantifications(
            batch_id=batch_id,
            product_category=normalized_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            sku_codes=output_skus,
            active_rows=quant_rows,
        )
        retired_attr_count = self.repository.retire_stale_attributions(
            batch_id=batch_id,
            product_category=normalized_category,
            analysis_population=analysis_population,
            market_window=market_window,
            rule_version=rule_version,
            sku_codes=output_skus,
            active_rows=attribution_rows,
        )
        summary_write = self.repository.save_dimension_summaries(summary_rows)
        review_write = self.repository.save_review_issues(review_rows)
        created = sum(item.created_count for item in (pool_write, metric_write, quant_write, attr_write, summary_write, review_write))
        reused = sum(item.reused_count for item in (pool_write, metric_write, quant_write, attr_write, summary_write, review_write))
        updated = sum(item.updated_count for item in (pool_write, metric_write, quant_write, attr_write, summary_write, review_write))
        role_counts = Counter(row["claim_value_role"] for row in quant_rows)
        sample_counts = Counter(pool.sample_status for pool in pools)
        warnings = []
        if review_rows:
            warnings.append(f"M12C 生成 {len(review_rows)} 条样本或可比池复核问题。")
        return M12CServiceResult(
            status=Core3RunStatus.WARNING if review_rows else Core3RunStatus.SUCCESS,
            input_count=len(output_skus),
            output_count=len(pool_rows) + len(metric_rows) + len(quant_rows) + len(attribution_rows) + len(summary_rows) + len(review_rows),
            warnings=warnings,
            created_output_count=created,
            reused_output_count=reused,
            updated_output_count=updated,
            summary={
                "batch_id": batch_id,
                "product_category": normalized_category,
                "market_window": market_window,
                "analysis_population": analysis_population,
                "rule_version": rule_version,
                "eligible_sku_count": len(output_skus),
                "comparable_sku_count": len(comparable_skus),
                "claim_pool_count": len(pool_rows),
                "pool_metric_count": len(metric_rows),
                "sku_claim_value_count": len(quant_rows),
                "sku_attribution_count": len(attribution_rows),
                "dimension_summary_count": len(summary_rows),
                "review_issue_count": len(review_rows),
                "role_counts": dict(role_counts),
                "sample_status_counts": dict(sample_counts),
                "created_output_count": created,
                "reused_output_count": reused,
                "updated_output_count": updated,
                "retired_quantification_count": retired_quant_count,
                "retired_attribution_count": retired_attr_count,
                "boundary_note": "M12C 输出为可观测市场贡献估计，不代表严格因果。",
            },
        )


def _build_pools(
    *,
    markets: Mapping[str, MarketState],
    claims: Mapping[str, Mapping[str, ClaimState]],
    semantics: Mapping[str, SemanticState],
    dimension_names: Mapping[tuple[str, str], str],
    param_profiles: Mapping[str, ParamProfileState],
) -> list[ClaimPool]:
    claims_by_code: dict[str, str] = {}
    members_by_code: dict[str, tuple[str, ...]] = {}
    for claim_map in claims.values():
        for state in claim_map.values():
            claims_by_code.setdefault(state.claim_code, state.claim_name)
            members_by_code[state.claim_code] = _unique_tuple((*members_by_code.get(state.claim_code, ()), *state.member_claim_codes, state.claim_code))
    contexts: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for sku, market in markets.items():
        for context_type, context_code, context_name, _ in semantics[sku].contexts:
            if context_type != "battlefield":
                continue
            name = dimension_names.get((context_type, context_code), context_name or context_code)
            contexts[(context_type, context_code, name)].add(sku)

    pools: list[ClaimPool] = []
    seen_keys: set[tuple[str, str, str, str, str]] = set()
    for (context_type, context_code, context_name), context_skus in sorted(contexts.items()):
        starting_buckets: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for sku in sorted(context_skus):
            market = markets.get(sku)
            if not market:
                continue
            starting_buckets[(market.exact_size_tier, market.size_tier, market.price_band)].append(sku)
        for (exact_size_tier, size_tier, price_band), _ in sorted(starting_buckets.items()):
            for claim_code, claim_name in sorted(claims_by_code.items()):
                relaxed = _relaxed_pool_for_claim(
                    all_skus=set(markets),
                    context_skus=context_skus,
                    markets=markets,
                    claims=claims,
                    param_profiles=param_profiles,
                    claim_code=claim_code,
                    exact_size_tier=exact_size_tier,
                    size_tier=size_tier,
                    price_band=price_band,
                )
                if relaxed is None:
                    continue
                (
                    final_size_tier,
                    final_price_band,
                    pool_relax_level,
                    sku_codes,
                    with_skus,
                    without_skus,
                    unknown_skus,
                    sample_status,
                    quality_flags,
                    relaxation_path,
                    comparison_basis,
                    comparison_param_code,
                    comparison_threshold_value,
                    comparison_group_label_cn,
                    control_group_label_cn,
                ) = relaxed
                pool_key = (claim_code, context_type, context_code, final_size_tier, final_price_band)
                if pool_key in seen_keys:
                    continue
                seen_keys.add(pool_key)
                pools.append(
                    ClaimPool(
                        claim_code=claim_code,
                        claim_name=claim_name,
                        context_type=context_type,
                        context_code=context_code,
                        context_name=context_name,
                        size_tier=final_size_tier,
                        price_band_group=final_price_band,
                        sku_codes=tuple(sorted(sku_codes)),
                        with_claim_skus=tuple(sorted(with_skus)),
                        without_claim_skus=tuple(sorted(without_skus)),
                        unknown_skus=tuple(sorted(unknown_skus)),
                        sample_status=sample_status,
                        quality_flags=tuple(quality_flags),
                        relaxation_path=relaxation_path,
                        pool_relax_level=pool_relax_level,
                        member_claim_codes=members_by_code.get(claim_code, (claim_code,)),
                        comparison_basis=comparison_basis,
                        comparison_param_code=comparison_param_code,
                        comparison_threshold_value=comparison_threshold_value,
                        comparison_group_label_cn=comparison_group_label_cn,
                        control_group_label_cn=control_group_label_cn,
                    )
                )
    return pools


def _relaxed_pool_for_claim(
    *,
    all_skus: set[str],
    context_skus: set[str],
    markets: Mapping[str, MarketState],
    claims: Mapping[str, Mapping[str, ClaimState]],
    param_profiles: Mapping[str, ParamProfileState],
    claim_code: str,
    exact_size_tier: str,
    size_tier: str,
    price_band: str,
) -> tuple[str, str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], str, list[str], tuple[dict[str, Any], ...], str, str | None, str | None, str, str] | None:
    levels = [
        ("L0", context_skus, exact_size_tier, (price_band,), "同战场、同具体尺寸、同价格带。"),
        ("L1", context_skus, size_tier, (price_band,), "同战场、同五档尺寸段、同价格带。"),
        ("L2", context_skus, size_tier, tuple(_adjacent_price_bands(price_band)), "同战场、同五档尺寸段、相邻价格带。"),
        ("L3", context_skus, size_tier, tuple(_adjacent_price_bands(price_band)), "同战场、同五档尺寸段、相邻价格带，不强制评论。"),
        ("L4", all_skus, size_tier, tuple(_adjacent_price_bands(price_band)), "同五档尺寸段、相邻价格带，不限定价值战场；仅用于门槛和待验证。"),
    ]
    path: list[dict[str, Any]] = []
    fallback: tuple[str, str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...], str, list[str], tuple[dict[str, Any], ...], str, str | None, str | None, str, str] | None = None
    for level, candidate_skus, size_scope, price_scope, reason in levels:
        sku_codes = tuple(sorted(_filter_pool_skus(candidate_skus, markets, size_scope, price_scope, exact_scope=(level == "L0"))))
        split = _split_claim_or_numeric_groups(sku_codes, claims, param_profiles, claim_code)
        sample_status, quality_flags = _sample_status(len(sku_codes), len(split.with_skus), len(split.without_skus))
        price_scope_label = price_band if level in {"L0", "L1"} else _price_scope_label(price_band, price_scope)
        final_size = exact_size_tier if level == "L0" else size_tier
        path_item = {
            "level": level,
            "reason": reason,
            "size_scope": final_size,
            "price_scope": price_scope_label,
            "pool_sku_count": len(sku_codes),
            "with_claim_sku_count": len(split.with_skus),
            "without_claim_sku_count": len(split.without_skus),
            "sample_status": sample_status,
            "comparison_basis": split.comparison_basis,
            "comparison_param_code": split.comparison_param_code,
            "comparison_threshold_value": split.comparison_threshold_value,
            "comparison_group_label_cn": split.comparison_group_label_cn,
            "control_group_label_cn": split.control_group_label_cn,
        }
        path.append(path_item)
        result = (
            final_size,
            price_scope_label,
            level,
            sku_codes,
            split.with_skus,
            split.without_skus,
            split.unknown_skus,
            sample_status,
            quality_flags,
            tuple(path),
            split.comparison_basis,
            split.comparison_param_code,
            split.comparison_threshold_value,
            split.comparison_group_label_cn,
            split.control_group_label_cn,
        )
        if fallback is None and sku_codes:
            fallback = result
        if level in {"L0", "L1", "L2"} and sample_status == "sufficient":
            return result
        if level == "L3" and sample_status in {"sufficient", "weak"}:
            return result
        if level == "L4" and sku_codes:
            if sample_status == "sufficient":
                quality_flags = [*quality_flags, "l4_threshold_only"]
            result = (
                final_size,
                price_scope_label,
                level,
                sku_codes,
                split.with_skus,
                split.without_skus,
                split.unknown_skus,
                sample_status,
                quality_flags,
                tuple(path),
                split.comparison_basis,
                split.comparison_param_code,
                split.comparison_threshold_value,
                split.comparison_group_label_cn,
                split.control_group_label_cn,
            )
            return result
    return fallback


def _filter_pool_skus(candidate_skus: Iterable[str], markets: Mapping[str, MarketState], size_scope: str, price_scope: Sequence[str], *, exact_scope: bool) -> list[str]:
    result: list[str] = []
    price_set = {item for item in price_scope if item}
    for sku in candidate_skus:
        market = markets.get(sku)
        if not market:
            continue
        current_size = market.exact_size_tier if exact_scope else market.size_tier
        if current_size != size_scope:
            continue
        if market.price_band not in price_set:
            continue
        result.append(sku)
    return result


def _split_claim_groups(sku_codes: Sequence[str], claims: Mapping[str, Mapping[str, ClaimState]], claim_code: str) -> tuple[list[str], list[str], list[str]]:
    with_skus: list[str] = []
    without_skus: list[str] = []
    unknown_skus: list[str] = []
    for sku in sku_codes:
        claim_state = claims.get(sku, {}).get(claim_code)
        if claim_state is None:
            without_skus.append(sku)
        elif claim_state.is_supported:
            with_skus.append(sku)
        elif claim_state.service_separate_flag:
            unknown_skus.append(sku)
        else:
            without_skus.append(sku)
    return with_skus, without_skus, unknown_skus


def _split_claim_or_numeric_groups(
    sku_codes: Sequence[str],
    claims: Mapping[str, Mapping[str, ClaimState]],
    param_profiles: Mapping[str, ParamProfileState],
    claim_code: str,
) -> ClaimGroupSplit:
    numeric_split = _split_numeric_param_groups(sku_codes, claims, param_profiles, claim_code)
    if numeric_split is not None:
        return numeric_split
    with_skus, without_skus, unknown_skus = _split_claim_groups(sku_codes, claims, claim_code)
    return ClaimGroupSplit(
        with_skus=tuple(sorted(with_skus)),
        without_skus=tuple(sorted(without_skus)),
        unknown_skus=tuple(sorted(unknown_skus)),
        comparison_basis="claim_presence",
        comparison_group_label_cn="有卖点组",
        control_group_label_cn="对照组",
    )


def _split_numeric_param_groups(
    sku_codes: Sequence[str],
    claims: Mapping[str, Mapping[str, ClaimState]],
    param_profiles: Mapping[str, ParamProfileState],
    claim_code: str,
) -> ClaimGroupSplit | None:
    if not sku_codes:
        return None
    for param_code in _numeric_group_candidate_params(sku_codes, claims, claim_code):
        values: list[tuple[str, Decimal]] = []
        unknown_skus: list[str] = []
        for sku in sku_codes:
            claim_state = claims.get(sku, {}).get(claim_code)
            entry = _param_entry(param_profiles, claim_state, sku, param_code)
            numeric_value = _decimal_param_value(entry.get("normalized_value")) if entry else None
            if numeric_value is None:
                unknown_skus.append(sku)
                continue
            values.append((sku, _q4(numeric_value)))
        if len(values) < MIN_POOL_SKU_COUNT or len({value for _, value in values}) < 2:
            continue
        numeric_values = [value for _, value in values]
        threshold = _median(numeric_values)
        if threshold is None:
            continue
        high_skus = [sku for sku, value in values if value >= threshold]
        low_skus = [sku for sku, value in values if value < threshold]
        if not high_skus or not low_skus:
            max_value = max(numeric_values)
            high_skus = [sku for sku, value in values if value == max_value]
            low_skus = [sku for sku, value in values if value < max_value]
            threshold = max_value
        if len(high_skus) < MIN_GROUP_SKU_COUNT or len(low_skus) < MIN_GROUP_SKU_COUNT:
            continue
        label = M12C_NUMERIC_GROUP_PARAM_LABELS.get(param_code, param_code)
        threshold_text = str(_q4(threshold))
        return ClaimGroupSplit(
            with_skus=tuple(sorted(high_skus)),
            without_skus=tuple(sorted(low_skus)),
            unknown_skus=tuple(sorted(unknown_skus)),
            comparison_basis="numeric_param_tier",
            comparison_param_code=param_code,
            comparison_threshold_value=threshold_text,
            comparison_group_label_cn=f"{label}高档组",
            control_group_label_cn=f"{label}低档组",
        )
    return None


def _numeric_group_candidate_params(sku_codes: Sequence[str], claims: Mapping[str, Mapping[str, ClaimState]], claim_code: str) -> tuple[str, ...]:
    if claim_code in M12C_SCENE_CONTEXT_CLAIM_CODES:
        return ()
    strict_codes = set(M12C_STRICT_SUPPORT_PARAM_CODES.get(claim_code, ()))
    ordered: list[str] = []
    for sku in sku_codes:
        claim = claims.get(sku, {}).get(claim_code)
        for param_code in (claim.primary_supporting_param_codes if claim else ()):
            if strict_codes and param_code not in strict_codes:
                continue
            _append_numeric_candidate_param(ordered, param_code)
        for param_code in (claim.supporting_param_codes if claim else ()):
            if strict_codes and param_code not in strict_codes:
                continue
            _append_numeric_candidate_param(ordered, param_code)
    for param_code in M12C_CLAIM_PARAM_FALLBACKS.get(claim_code, ()):
        if strict_codes and param_code not in strict_codes:
            continue
        _append_numeric_candidate_param(ordered, param_code)
    return tuple(ordered)


def _append_numeric_candidate_param(target: list[str], param_code: str) -> None:
    text = str(param_code or "").strip()
    if not text or text.startswith("_"):
        return
    if text.endswith("_flag") or text in {"hdr_support_flag", "hdmi21_flag", "low_blue_light_flag", "flicker_free_flag", "high_color_gamut_flag", "quantum_dot_flag", "dolby_vision_flag", "dolby_atmos_flag"}:
        return
    if text not in target:
        target.append(text)


def _row_wtp_input_guard(row: entities.Core3SkuClaimFact) -> str:
    guard = str(getattr(row, "wtp_input_guard", "") or "").strip()
    if guard and guard != M04C_WTP_GUARD_UNKNOWN:
        return guard
    claim_code = str(row.claim_code or "")
    supporting_codes = {str(item) for item in (row.supporting_param_codes or [])}
    primary_codes = {str(item) for item in (getattr(row, "primary_supporting_param_codes", None) or [])}
    if claim_code == "tv_claim_dolby_audio_video" and supporting_codes and not primary_codes and supporting_codes.issubset({"hdr_support_flag"}):
        return M04C_WTP_GUARD_BLOCKED_GENERIC
    status = str(row.param_support_status or "").lower()
    if bool(row.service_separate_flag) or status == "not_param_applicable":
        return M04C_WTP_GUARD_NOT_SCOPE
    if status in {"supported", "partially_supported", "strong_supported", "fact_supported"}:
        return M04C_WTP_GUARD_ELIGIBLE
    return M04C_WTP_GUARD_BLOCKED_NO_PARAM


def _row_param_support_level(row: entities.Core3SkuClaimFact) -> str:
    level = str(getattr(row, "param_support_level", "") or "").strip()
    if level and level != "unknown":
        return level
    guard = _row_wtp_input_guard(row)
    if guard == M04C_WTP_GUARD_BLOCKED_GENERIC:
        return M04C_PARAM_SUPPORT_BROAD_GENERIC
    if guard == M04C_WTP_GUARD_ELIGIBLE:
        return M04C_PARAM_SUPPORT_STRONG_SPECIFIC
    if guard == M04C_WTP_GUARD_NOT_SCOPE:
        return M04C_PARAM_SUPPORT_NO_PARAM
    return M04C_PARAM_SUPPORT_NO_PARAM


def _row_canonical_claim_code(row: entities.Core3SkuClaimFact) -> str:
    return str(getattr(row, "canonical_claim_code", "") or row.claim_code or "")


def _row_canonical_claim_name(row: entities.Core3SkuClaimFact) -> str:
    return str(getattr(row, "canonical_claim_name", "") or row.claim_name or "")


def _merge_claim_states(existing: ClaimState | None, incoming: ClaimState) -> ClaimState:
    if existing is None:
        return incoming
    primary = incoming if incoming.confidence >= existing.confidence else existing
    other = existing if primary is incoming else incoming
    supporting_snapshot = dict(other.supporting_param_snapshot or {})
    supporting_snapshot.update(dict(primary.supporting_param_snapshot or {}))
    primary_codes = _unique_tuple((*existing.primary_supporting_param_codes, *incoming.primary_supporting_param_codes))
    generic_codes = _unique_tuple((*existing.generic_support_param_codes, *incoming.generic_support_param_codes))
    supporting_codes = _unique_tuple((*primary_codes, *existing.supporting_param_codes, *incoming.supporting_param_codes))
    return ClaimState(
        sku_code=primary.sku_code,
        claim_code=primary.canonical_claim_code or primary.claim_code,
        claim_name=primary.canonical_claim_name or primary.claim_name,
        claim_dimension=primary.claim_dimension,
        claim_subtype=primary.claim_subtype,
        claim_kind=primary.claim_kind,
        param_support_status=_strongest_support_status(existing.param_support_status, incoming.param_support_status),
        supporting_param_codes=supporting_codes,
        supporting_param_snapshot=supporting_snapshot,
        match_score=max(existing.match_score, incoming.match_score),
        confidence=max(existing.confidence, incoming.confidence),
        fact_claim_flag=existing.fact_claim_flag or incoming.fact_claim_flag,
        service_separate_flag=existing.service_separate_flag and incoming.service_separate_flag,
        evidence_ids=_unique_tuple((*existing.evidence_ids, *incoming.evidence_ids)),
        param_support_level=_strongest_param_support_level(existing.param_support_level, incoming.param_support_level),
        param_support_specificity=primary.param_support_specificity or other.param_support_specificity,
        primary_supporting_param_codes=primary_codes,
        generic_support_param_codes=generic_codes,
        source_claim_group_id=primary.source_claim_group_id or other.source_claim_group_id,
        same_source_param_group_id=primary.same_source_param_group_id or other.same_source_param_group_id,
        canonical_claim_code=primary.canonical_claim_code or primary.claim_code,
        canonical_claim_name=primary.canonical_claim_name or primary.claim_name,
        wtp_input_guard=_strongest_wtp_guard(existing.wtp_input_guard, incoming.wtp_input_guard),
        member_claim_codes=_unique_tuple((*existing.member_claim_codes, *incoming.member_claim_codes)),
        member_claim_names=_unique_tuple((*existing.member_claim_names, *incoming.member_claim_names)),
    )


def _effective_wtp_input_guard(claim: ClaimState | None) -> str:
    if claim is None:
        return M04C_WTP_GUARD_BLOCKED_NO_PARAM
    guard = str(claim.wtp_input_guard or "").strip()
    if guard and guard != M04C_WTP_GUARD_UNKNOWN:
        return guard
    if claim.claim_code == "tv_claim_dolby_audio_video" and not claim.primary_supporting_param_codes and set(claim.supporting_param_codes).issubset({"hdr_support_flag"}):
        return M04C_WTP_GUARD_BLOCKED_GENERIC
    if claim.service_separate_flag:
        return M04C_WTP_GUARD_NOT_SCOPE
    if claim.param_support_status.lower() in {"supported", "partially_supported", "strong_supported", "fact_supported"}:
        return M04C_WTP_GUARD_ELIGIBLE
    return M04C_WTP_GUARD_BLOCKED_NO_PARAM


def _strongest_wtp_guard(*guards: str) -> str:
    priority = {
        M04C_WTP_GUARD_ELIGIBLE: 4,
        M04C_WTP_GUARD_BLOCKED_GENERIC: 3,
        M04C_WTP_GUARD_BLOCKED_NO_PARAM: 2,
        M04C_WTP_GUARD_NOT_SCOPE: 1,
        M04C_WTP_GUARD_UNKNOWN: 0,
    }
    return max((guard or M04C_WTP_GUARD_UNKNOWN for guard in guards), key=lambda item: priority.get(item, 0))


def _strongest_param_support_level(*levels: str) -> str:
    priority = {
        M04C_PARAM_SUPPORT_STRONG_NUMERIC: 5,
        M04C_PARAM_SUPPORT_STRONG_SPECIFIC: 4,
        M04C_PARAM_SUPPORT_BROAD_GENERIC: 3,
        M04C_PARAM_SUPPORT_WEAK_INDIRECT: 2,
        M04C_PARAM_SUPPORT_NO_PARAM: 1,
    }
    return max((level or M04C_PARAM_SUPPORT_NO_PARAM for level in levels), key=lambda item: priority.get(item, 0))


def _strongest_support_status(*statuses: str) -> str:
    priority = {"supported": 4, "partially_supported": 3, "param_unknown": 2, "not_param_applicable": 1, "unsupported_by_param": 0}
    return max((status or "param_unknown" for status in statuses), key=lambda item: priority.get(item, 0))


def _unique_tuple(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)


def _pool_and_metric_rows(
    *,
    pools: Sequence[ClaimPool],
    markets: Mapping[str, MarketState],
    batch_id: str,
    project_id: str,
    category_code: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    pool_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    metrics_by_pool: dict[str, dict[str, Any]] = {}
    for pool in pools:
        pool_id = _record_id("m12c_pool", batch_id, product_category, market_window, analysis_population, pool.claim_code, pool.context_type, pool.context_code, pool.size_tier, pool.price_band_group, rule_version)
        pool_payload = {
            "pool_id": pool_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "market_window": market_window,
            "analysis_population": analysis_population,
            "window_start_week": _min_week(markets[sku].window_start_week for sku in pool.sku_codes if sku in markets),
            "window_end_week": _max_week(markets[sku].window_end_week for sku in pool.sku_codes if sku in markets),
            "claim_code": pool.claim_code,
            "claim_name": pool.claim_name,
            "context_type": pool.context_type,
            "context_code": pool.context_code,
            "context_name": pool.context_name,
            "size_tier": pool.size_tier,
            "price_band_group": pool.price_band_group,
            "pool_sku_count": len(pool.sku_codes),
            "with_claim_sku_count": len(pool.with_claim_skus),
            "without_claim_sku_count": len(pool.without_claim_skus),
            "unknown_claim_sku_count": len(pool.unknown_skus),
            "pool_sku_codes_json": list(pool.sku_codes),
            "with_claim_sku_codes_json": list(pool.with_claim_skus),
            "without_claim_sku_codes_json": list(pool.without_claim_skus),
            "unknown_claim_sku_codes_json": list(pool.unknown_skus),
            "relaxation_path_json": list(pool.relaxation_path),
            "sample_status": pool.sample_status,
            "quality_flags_json": [
                *pool.quality_flags,
                f"comparison_basis:{pool.comparison_basis}",
                *([f"comparison_param:{pool.comparison_param_code}"] if pool.comparison_param_code else []),
            ],
            "rule_version": rule_version,
            "input_fingerprint": stable_hash({"pool": pool.__dict__}, version="m12c-pool-input-v1"),
            "is_current": True,
        }
        pool_payload["pool_hash"] = stable_hash(pool_payload, version="m12c-pool-v1")
        metric = _pool_metric(pool, markets)
        metric_id = _record_id("m12c_metric", pool_id, rule_version)
        metric_payload = {
            "metric_id": metric_id,
            "pool_id": pool_id,
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "market_window": market_window,
            "analysis_population": analysis_population,
            "claim_code": pool.claim_code,
            "claim_name": pool.claim_name,
            "context_type": pool.context_type,
            "context_code": pool.context_code,
            "context_name": pool.context_name,
            "size_tier": pool.size_tier,
            "price_band_group": pool.price_band_group,
            **metric,
            "business_summary_cn": _metric_summary_cn(pool, metric),
            "quality_flags_json": [
                *pool.quality_flags,
                f"comparison_basis:{pool.comparison_basis}",
                *([f"comparison_param:{pool.comparison_param_code}"] if pool.comparison_param_code else []),
            ],
            "rule_version": rule_version,
            "is_current": True,
        }
        metric_payload["result_hash"] = stable_hash(metric_payload, version="m12c-pool-metric-v1")
        pool_rows.append(pool_payload)
        metric_rows.append(metric_payload)
        metrics_by_pool[pool_id] = metric_payload
    return pool_rows, metric_rows, metrics_by_pool


def _claim_business_display_name(
    pool: ClaimPool,
    claim: ClaimState | None,
    sku_code: str,
    param_profiles: Mapping[str, ParamProfileState],
) -> str:
    if pool.claim_code in M12C_SCENE_CONTEXT_CLAIM_CODES:
        return f"{pool.claim_name}（场景证据）"
    if pool.comparison_basis == "numeric_param_tier":
        value_label = _target_param_display_value(pool.comparison_param_code or "", claim, sku_code, param_profiles)
        if pool.claim_code == "tv_claim_hdr_high_brightness" and pool.comparison_param_code == "declared_brightness_nit_or_band":
            return f"{value_label} 高亮档位" if value_label else "高亮参数优势"
        if pool.claim_code in {"tv_claim_high_refresh_rate", "tv_claim_refresh_rate"} and pool.comparison_param_code in {
            "declared_refresh_rate_hz",
            "native_refresh_rate_hz",
            "refresh_rate_hz",
        }:
            return f"{value_label} 高阶刷新率" if value_label else "高阶刷新率档位"
        if pool.claim_code == "tv_claim_local_dimming" and pool.comparison_param_code == "local_dimming_zone_count":
            return f"{value_label} 分区控光" if value_label else "高分区控光"
        if pool.claim_code == "tv_claim_wide_color_accuracy" and pool.comparison_param_code in {
            "color_gamut_ratio",
            "wide_color_gamut_pct",
            "color_gamut_percent",
        }:
            return f"{value_label} 色彩表现" if value_label else "高色域/色彩还原"
    return claim.canonical_claim_name if claim and claim.canonical_claim_name else pool.claim_name


def _target_param_display_value(
    param_code: str,
    claim: ClaimState | None,
    sku_code: str,
    param_profiles: Mapping[str, ParamProfileState],
) -> str:
    if not param_code:
        return ""
    entry = _param_entry(param_profiles, claim, sku_code, param_code)
    if not entry:
        return ""
    value = _decimal_param_value(entry.get("normalized_value"))
    if value is None:
        raw_value = entry.get("normalized_value")
        return str(raw_value).strip() if raw_value is not None else ""
    if param_code == "declared_brightness_nit_or_band":
        return f"{int(value)}nits"
    if param_code in {"declared_refresh_rate_hz", "native_refresh_rate_hz", "refresh_rate_hz"}:
        return f"{int(value)}Hz"
    if param_code == "local_dimming_zone_count":
        return f"{int(value)}"
    if param_code in {"color_gamut_ratio", "wide_color_gamut_pct", "color_gamut_percent"}:
        return f"{_format_decimal_for_label(value)}%"
    return _format_decimal_for_label(value)


def _format_decimal_for_label(value: Decimal) -> str:
    rounded = _q4(value)
    if rounded == rounded.to_integral_value():
        return str(int(rounded))
    return format(rounded.normalize(), "f").rstrip("0").rstrip(".")


def _quantification_rows(
    *,
    pools: Sequence[ClaimPool],
    metric_by_pool: Mapping[str, Mapping[str, Any]],
    markets: Mapping[str, MarketState],
    claims: Mapping[str, Mapping[str, ClaimState]],
    param_profiles: Mapping[str, ParamProfileState],
    comments: Mapping[str, CommentState],
    semantics: Mapping[str, SemanticState],
    batch_id: str,
    project_id: str,
    category_code: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    output_sku_codes: set[str],
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> tuple[list[dict[str, Any]], dict[tuple[str, str, str, str, str], list[dict[str, Any]]]]:
    rows: list[dict[str, Any]] = []
    by_sku_context: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for pool in pools:
        pool_id = _record_id("m12c_pool", batch_id, product_category, market_window, analysis_population, pool.claim_code, pool.context_type, pool.context_code, pool.size_tier, pool.price_band_group, rule_version)
        metric = metric_by_pool[pool_id]
        for sku in pool.sku_codes:
            if sku not in output_sku_codes:
                continue
            market = markets[sku]
            claim = claims.get(sku, {}).get(pool.claim_code)
            fact_claim_present = bool(claim and claim.is_supported)
            has_claim = fact_claim_present
            if pool.comparison_basis == "numeric_param_tier":
                has_claim = fact_claim_present and sku in pool.with_claim_skus
            comment = comments.get(sku, _empty_comment(sku))
            comment_strength = _comment_support_strength(comment, claim, pool)
            has_negative = _comment_has_negative(comment, claim, pool)
            sku_battlefield_strength = semantics[sku].support_strength(pool.context_type, pool.context_code)
            battlefield_weight = semantics[sku].allocation_weight(pool.context_type, pool.context_code)
            battlefield_claim_relevance = _battlefield_claim_relevance_strength(pool, claim)
            semantic_strength = _q4(sku_battlefield_strength * Decimal("0.45") + battlefield_claim_relevance * Decimal("0.55"))
            parameter_competitiveness = _claim_parameter_competitiveness(
                pool=pool,
                target_sku=sku,
                claim=claim,
                claims=claims,
                comments=comments,
                param_profiles=param_profiles,
            )
            parameter_competitiveness_strength = _q4(
                Decimal(str(parameter_competitiveness.get("overall_parameter_competitiveness_score") or 0)) / Decimal("100")
            )
            param_strength = max(claim.param_support_strength if claim else Decimal("0.0000"), parameter_competitiveness_strength)
            claim_strength = _claim_evidence_strength(claim) if claim else Decimal("0.0000")
            source_type = _claim_source_type(
                has_claim=has_claim,
                parameter_competitiveness=parameter_competitiveness,
                battlefield_claim_relevance=battlefield_claim_relevance,
            )
            target_baseline = _target_baseline(pool, markets, sku)
            baseline_price = target_baseline["baseline_price"]
            baseline_sales = target_baseline["baseline_weekly_sales"]
            baseline_amount = target_baseline["baseline_weekly_amount"]
            market_position = _market_position_signal(
                market_price=market.price,
                market_sales=market.avg_weekly_sales_volume,
                market_amount=market.avg_weekly_sales_amount,
                baseline_price=baseline_price,
                baseline_sales=baseline_sales,
                baseline_amount=baseline_amount,
            )
            market_acceptance = _market_acceptance_score(
                market=market,
                baseline_price=baseline_price,
                baseline_sales=baseline_sales,
                baseline_amount=baseline_amount,
                pool=pool,
                comment=comment,
            )
            amount_basis = _amount_quantification_basis(pool, sku)
            role = _claim_role(
                target_sku=sku,
                has_claim=has_claim,
                metric=metric,
                pool=pool,
                param_strength=param_strength,
                comment_strength=comment_strength,
                semantic_strength=semantic_strength,
                battlefield_claim_relevance=battlefield_claim_relevance,
                parameter_competitiveness=parameter_competitiveness,
                source_type=source_type,
                has_negative=has_negative,
                market_price=market.price,
            )
            if source_type == M12C_COMPETITOR_GAP and role not in OPPORTUNITY_ROLES:
                continue
            display_claim_name = _claim_business_display_name(pool, claim, sku, param_profiles)
            scorecard = _claim_value_scorecard(
                pool=pool,
                role=role,
                metric=metric,
                has_claim=has_claim,
                param_strength=param_strength,
                comment_strength=comment_strength,
                semantic_strength=semantic_strength,
                has_negative=has_negative,
                market_position=market_position,
                market_acceptance=market_acceptance,
                parameter_competitiveness=parameter_competitiveness,
            )
            unique_potential_scorecard: dict[str, Any] | None = None
            if role == M12C_ROLE_UNIQUE:
                unique_potential_scorecard = _unique_payment_potential_scorecard(
                    pool=pool,
                    target_sku=sku,
                    param_strength=param_strength,
                    comment_strength=comment_strength,
                    semantic_strength=semantic_strength,
                    parameter_competitiveness=parameter_competitiveness,
                    amount_basis=amount_basis,
                )
                scorecard = {
                    **scorecard,
                    "total_score": unique_potential_scorecard["total_score"],
                    "score_method_cn": unique_potential_scorecard["score_method_cn"],
                    "dimensions": unique_potential_scorecard["dimensions"],
                    "unique_payment_potential": unique_potential_scorecard,
                }
            business_claim_type = _business_claim_type(
                role,
                metric,
                scorecard,
                market_position=market_position,
                parameter_competitiveness=parameter_competitiveness,
            )
            business_claim_type_cn = _business_claim_type_label(business_claim_type)
            weight_seed = _positive_weight(role, metric, claim_strength, semantic_strength, comment_strength, scorecard)
            effective_price_space = _effective_price_space(market, baseline_price, market_position, market_acceptance)
            weekly_sales_space = max(Decimal("0.000000"), _q6(market.avg_weekly_sales_volume - baseline_sales))
            weekly_amount_space = max(Decimal("0.000000"), _q6(market.avg_weekly_sales_amount - baseline_amount))
            payload = {
                "sku_claim_value_id": _record_id("m12c_sku_claim", batch_id, sku, pool.claim_code, pool.context_type, pool.context_code, pool.size_tier, pool.price_band_group, rule_version),
                "pool_id": pool_id,
                "metric_id": metric.get("metric_id"),
                "project_id": project_id,
                "category_code": category_code,
                "batch_id": batch_id,
                "run_id": run_id,
                "module_run_id": module_run_id,
                "product_category": product_category,
                "market_window": market_window,
                "analysis_population": analysis_population,
                "sku_code": sku,
                "brand_name": market.brand_name,
                "model_name": market.model_name,
                "claim_code": pool.claim_code,
                "claim_name": display_claim_name,
                "claim_dimension": claim.claim_dimension if claim else "",
                "claim_value_role": role,
                "context_type": pool.context_type,
                "context_code": pool.context_code,
                "context_name": pool.context_name,
                "size_tier": pool.size_tier,
                "price_band_group": pool.price_band_group,
                "claim_evidence_strength": claim_strength,
                "param_support_strength": param_strength,
                "comment_support_strength": comment_strength,
                "semantic_support_strength": semantic_strength,
                "estimated_price_premium_abs": Decimal("0.0000"),
                "estimated_weekly_sales_lift_abs": Decimal("0.000000"),
                "estimated_weekly_sales_amount_lift_abs": Decimal("0.000000"),
                "contribution_share_in_sku": Decimal("0.000000"),
                "attribution_confidence": _q4(min(Decimal("1.0000"), _q4(metric["effect_confidence"]) * Decimal("0.7") + claim_strength * Decimal("0.3"))),
                "supporting_dimensions_json": {
                    "context_type": pool.context_type,
                    "context_code": pool.context_code,
                    "context_name": pool.context_name,
                    "target_has_claim": source_type != M12C_COMPETITOR_GAP,
                    "target_fact_claim_flag": fact_claim_present,
                    "target_qualifies_comparison_group": has_claim,
                    "claim_source_type": source_type,
                    "claim_source_type_cn": _source_type_cn(source_type),
                    "semantic_support_strength": float(semantic_strength),
                    "sku_battlefield_strength": float(sku_battlefield_strength),
                    "battlefield_claim_relevance": float(battlefield_claim_relevance),
                    "parameter_competitiveness": parameter_competitiveness,
                    "business_claim_type": business_claim_type,
                    "business_claim_type_cn": business_claim_type_cn,
                    "business_claim_type_definition_cn": _business_claim_type_meaning_cn(business_claim_type),
                    "standard_claim_name": pool.claim_name,
                    "business_display_name": display_claim_name,
                    "canonical_claim_code": claim.canonical_claim_code if claim else pool.claim_code,
                    "canonical_claim_name": claim.canonical_claim_name if claim else pool.claim_name,
                    "member_claim_codes": list(_claim_code_family(claim, pool)),
                    "wtp_input_guard": parameter_competitiveness.get("wtp_input_guard") or _effective_wtp_input_guard(claim),
                    "param_support_level": parameter_competitiveness.get("param_support_level") or (claim.param_support_level if claim else ""),
                    "primary_supporting_param_codes": list(claim.primary_supporting_param_codes if claim else ()),
                    "generic_support_param_codes": list(claim.generic_support_param_codes if claim else ()),
                    "claim_value_score": scorecard["total_score"],
                    "scorecard": scorecard,
                    "market_position_type": market_position["type"],
                    "market_position_cn": market_position["summary_cn"],
                    "comparable_pool": {
                        "pool_relax_level": pool.pool_relax_level,
                        "pool_sku_count": len(pool.sku_codes),
                        "with_claim_sku_count": len(pool.with_claim_skus),
                        "without_claim_sku_count": len(pool.without_claim_skus),
                        "comparison_basis": pool.comparison_basis,
                        "comparison_param_code": pool.comparison_param_code,
                        "comparison_threshold_value": pool.comparison_threshold_value,
                        "comparison_group_label_cn": pool.comparison_group_label_cn,
                        "control_group_label_cn": pool.control_group_label_cn,
                        "fact_claim_present": fact_claim_present,
                        "target_in_comparison_group": sku in pool.with_claim_skus,
                        "sample_status": pool.sample_status,
                        "target_price": float(_q4(market.price)),
                        "target_weekly_sales": float(_q6(market.avg_weekly_sales_volume)),
                        "target_weekly_amount": float(_q6(market.avg_weekly_sales_amount)),
                        "baseline_price": float(_q4(baseline_price)),
                        "baseline_weekly_sales": float(_q6(baseline_sales)),
                        "baseline_weekly_amount": float(_q6(baseline_amount)),
                        "baseline_price_method": target_baseline["baseline_price_method"],
                        "baseline_explanation_cn": target_baseline["baseline_explanation_cn"],
                        "comparison_sku_codes": target_baseline["comparison_sku_codes"],
                        "baseline_sku_codes": target_baseline["baseline_sku_codes"],
                        "amount_quantification_ready": amount_basis["amount_quantification_ready"],
                        "sample_grade": amount_basis["sample_grade"],
                        "no_amount_reason_cn": amount_basis["no_amount_reason_cn"],
                    },
                    "market_acceptance": market_acceptance,
                    "amount_quantification_basis": amount_basis,
                    "unique_payment_potential_scorecard": unique_potential_scorecard or {},
                    "value_space": {
                        "raw_price_gap": float(_q4(market.price - baseline_price)),
                        "effective_price_space": float(effective_price_space),
                        "weekly_sales_space": float(weekly_sales_space),
                        "weekly_amount_space": float(weekly_amount_space),
                        "formula_cn": "战场支付价值空间 = 可解释价差 × 市场承接系数；卖点金额 = 战场空间 × 卖点支付价值分占比 × 卖点类型系数。",
                    },
                    "claim_type_coefficient": float(_claim_type_coefficient(business_claim_type)),
                    "battlefield_allocation_weight": float(battlefield_weight),
                    "sku_level_aggregation_basis_cn": "先在单个价值战场内判断卖点支付价值，再按主/辅战场权重汇总到 SKU 层。",
                },
                "evidence_ids_json": list(claim.evidence_ids if claim else ()),
                "reason_cn": _quant_reason_cn(pool, role, metric),
                "quality_flags_json": [
                    *_unique_nonempty(
                        [
                            *pool.quality_flags,
                            *amount_basis.get("quality_flags", ()),
                            *(["comment_negative"] if has_negative else []),
                        ]
                    )
                ],
                "_pool_claim_price_delta_abs": _q4(metric["price_premium_abs"]),
                "_pool_claim_weekly_sales_delta_abs": _q6(metric["weekly_sales_lift_abs"]),
                "_pool_claim_weekly_sales_amount_delta_abs": _q6(metric["weekly_sales_amount_lift_abs"]),
                "_business_value_label": _business_value_label(role, metric),
                "_business_value_meaning_cn": _business_value_meaning_cn(role, metric),
                "_baseline_price": baseline_price,
                "_baseline_sales": baseline_sales,
                "_baseline_amount": baseline_amount,
                "_weight_seed": weight_seed,
                "_claim_value_score": Decimal(str(scorecard["total_score"])),
                "_business_claim_type": business_claim_type,
                "_claim_type_coefficient": _claim_type_coefficient(business_claim_type),
                "_battlefield_weight": battlefield_weight,
                "_effective_price_space": effective_price_space,
                "_weekly_sales_space": weekly_sales_space,
                "_weekly_amount_space": weekly_amount_space,
                "_market_acceptance_coefficient": Decimal(str(market_acceptance["market_validation_coefficient"])),
                "_market_price": market.price,
                "_market_sales": market.avg_weekly_sales_volume,
                "_market_amount": market.avg_weekly_sales_amount,
                "rule_version": rule_version,
                "is_current": True,
            }
            by_sku_context[(sku, pool.context_type, pool.context_code, pool.size_tier, pool.price_band_group)].append(payload)
    normalized_rows: list[dict[str, Any]] = []
    for context_key, context_rows in by_sku_context.items():
        positive_total_by_type: dict[str, Decimal] = defaultdict(Decimal)
        for context_row in context_rows:
            if context_row["claim_value_role"] in POSITIVE_ROLES:
                positive_total_by_type[str(context_row["_business_claim_type"])] += max(Decimal("0"), _q6(context_row["_claim_value_score"]))
        for row in context_rows:
            share = Decimal("0.000000")
            type_total = positive_total_by_type.get(str(row["_business_claim_type"]), Decimal("0"))
            if row["claim_value_role"] in POSITIVE_ROLES and type_total > 0:
                share = _q6(max(Decimal("0"), _q6(row["_claim_value_score"])) / type_total)
            battlefield_weight = _q6(row.get("_battlefield_weight") or Decimal("0"))
            weighted_share = _q6(share * battlefield_weight)
            row["contribution_share_in_sku"] = weighted_share
            coeff = _q4(row["_claim_type_coefficient"])
            if row["_business_claim_type"] == M12C_CLAIM_TYPE_PREMIUM:
                row["estimated_price_premium_abs"] = _q4(row["_effective_price_space"] * weighted_share * coeff)
            else:
                row["estimated_price_premium_abs"] = Decimal("0.0000")
            row["estimated_weekly_sales_lift_abs"] = _q6(row["_weekly_sales_space"] * weighted_share * coeff)
            row["estimated_weekly_sales_amount_lift_abs"] = _q6(row["_weekly_amount_space"] * weighted_share * coeff)
            save_row = {key: value for key, value in row.items() if not key.startswith("_")}
            save_row["result_hash"] = stable_hash(save_row, version="m12c-sku-claim-v1")
            normalized_rows.append(save_row)
    return normalized_rows, by_sku_context


def _attribution_rows(
    *,
    quant_by_sku_context: Mapping[tuple[str, str, str, str, str], Sequence[dict[str, Any]]],
    markets: Mapping[str, MarketState],
    batch_id: str,
    project_id: str,
    category_code: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (sku, context_type, context_code, size_tier, price_band), quant_rows in sorted(quant_by_sku_context.items()):
        market = markets[sku]
        first = quant_rows[0]
        positive = sorted(
            [row for row in quant_rows if row["claim_value_role"] in POSITIVE_ROLES],
            key=lambda row: (_q6(row["contribution_share_in_sku"]), _q4(row["estimated_weekly_sales_amount_lift_abs"])),
            reverse=True,
        )
        drag = [row for row in quant_rows if row["claim_value_role"] == M12C_ROLE_DRAG]
        opportunity = [row for row in quant_rows if row["claim_value_role"] in OPPORTUNITY_ROLES]
        baseline_price = _q4(first.get("_baseline_price", Decimal("0")))
        baseline_sales = _q6(first.get("_baseline_sales", Decimal("0")))
        baseline_amount = _q6(first.get("_baseline_amount", Decimal("0")))
        payload = {
            "attribution_id": _record_id("m12c_attr", batch_id, sku, context_type, context_code, size_tier, price_band, rule_version),
            "pool_id": first.get("pool_id"),
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "market_window": market_window,
            "analysis_population": analysis_population,
            "sku_code": sku,
            "brand_name": market.brand_name,
            "model_name": market.model_name,
            "context_type": context_type,
            "context_code": context_code,
            "context_name": first.get("context_name") or context_code,
            "size_tier": size_tier,
            "price_band_group": price_band,
            "baseline_price": baseline_price,
            "baseline_weekly_sales_volume": baseline_sales,
            "baseline_weekly_sales_amount": baseline_amount,
            "sku_price": market.price,
            "sku_weekly_sales_volume": market.avg_weekly_sales_volume,
            "sku_weekly_sales_amount": market.avg_weekly_sales_amount,
            "sku_price_premium_abs": _q4(market.price - baseline_price),
            "sku_weekly_sales_lift_abs": _q6(market.avg_weekly_sales_volume - baseline_sales),
            "sku_weekly_sales_amount_lift_abs": _q6(market.avg_weekly_sales_amount - baseline_amount),
            "positive_claims_json": [_claim_brief(row) for row in positive[:8]],
            "drag_claims_json": [_claim_brief(row) for row in drag[:8]],
            "opportunity_claims_json": [_claim_brief(row) for row in opportunity[:8]],
            "attribution_summary_cn": _attribution_summary_cn(market, positive, context_type, first.get("context_name") or context_code),
            "confidence": _avg(row["attribution_confidence"] for row in quant_rows),
            "rule_version": rule_version,
            "is_current": True,
        }
        payload["result_hash"] = stable_hash(payload, version="m12c-attribution-v1")
        rows.append(payload)
    return rows


def _dimension_summary_rows(
    *,
    quant_rows: Sequence[dict[str, Any]],
    dimension_spaces: Mapping[tuple[str, str], entities.Core3SemanticMarketDimensionSummary],
    batch_id: str,
    project_id: str,
    category_code: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in quant_rows:
        groups[(row["claim_code"], row["context_type"], row["context_code"], row["size_tier"], row["price_band_group"])].append(row)
    result: list[dict[str, Any]] = []
    for (claim_code, dimension_type, dimension_code, size_tier, price_band), rows in sorted(groups.items()):
        role_counts = Counter(row["claim_value_role"] for row in rows)
        space = dimension_spaces.get((dimension_type, dimension_code))
        top_skus = sorted(rows, key=lambda row: (_q6(row["estimated_weekly_sales_amount_lift_abs"]), _q4(row["attribution_confidence"])), reverse=True)[:10]
        payload = {
            "summary_id": _record_id("m12c_dim", batch_id, claim_code, dimension_type, dimension_code, size_tier, price_band, analysis_population, market_window, rule_version),
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "market_window": market_window,
            "analysis_population": analysis_population,
            "claim_code": claim_code,
            "claim_name": rows[0].get("claim_name") or claim_code,
            "dimension_type": dimension_type,
            "dimension_code": dimension_code,
            "dimension_name": rows[0].get("context_name") or (space.dimension_name if space else dimension_code),
            "size_tier": size_tier,
            "price_band_group": price_band,
            "sku_count": len({row["sku_code"] for row in rows}),
            "premium_driver_sku_count": role_counts[M12C_ROLE_PREMIUM],
            "sales_driver_sku_count": role_counts[M12C_ROLE_SALES],
            "basic_threshold_sku_count": role_counts[M12C_ROLE_BASIC],
            "brand_claim_only_sku_count": role_counts[M12C_ROLE_BRAND],
            "drag_factor_sku_count": role_counts[M12C_ROLE_DRAG],
            "opportunity_gap_sku_count": sum(role_counts[role] for role in OPPORTUNITY_ROLES),
            "estimated_sales_volume": _q4(space.estimated_sales_volume if space else Decimal("0")),
            "estimated_avg_weekly_sales_volume": _q6(space.estimated_avg_weekly_sales_volume if space else Decimal("0")),
            "estimated_sales_amount": _q4(space.estimated_sales_amount if space else Decimal("0")),
            "estimated_avg_weekly_sales_amount": _q6(space.estimated_avg_weekly_sales_amount if space else Decimal("0")),
            "top_skus_json": [_claim_brief(row) for row in top_skus],
            "business_summary_cn": f"{rows[0].get('claim_name') or claim_code} 在 {rows[0].get('context_name') or dimension_code} 中覆盖 {len({row['sku_code'] for row in rows})} 个 SKU。",
            "rule_version": rule_version,
            "is_current": True,
        }
        payload["result_hash"] = stable_hash(payload, version="m12c-dimension-summary-v1")
        result.append(payload)
    return result


def _review_issue_rows(
    *,
    pools: Sequence[ClaimPool],
    batch_id: str,
    project_id: str,
    category_code: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pool in pools:
        if pool.sample_status == "sufficient":
            continue
        pool_id = _record_id("m12c_pool", batch_id, product_category, market_window, analysis_population, pool.claim_code, pool.context_type, pool.context_code, pool.size_tier, pool.price_band_group, rule_version)
        issue_code = "sample_insufficient" if pool.sample_status == "insufficient" else "sample_weak"
        payload = {
            "issue_id": _record_id("m12c_issue", batch_id, pool_id, issue_code),
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "product_category": product_category,
            "market_window": market_window,
            "analysis_population": analysis_population,
            "issue_scope": "pool",
            "sku_code": "",
            "claim_code": pool.claim_code,
            "claim_name": pool.claim_name,
            "pool_id": pool_id,
            "context_type": pool.context_type,
            "context_code": pool.context_code,
            "issue_code": issue_code,
            "issue_level": "warning" if pool.sample_status == "weak" else "blocker",
            "issue_cn": f"{pool.claim_name} 在 {pool.context_name} / {pool.size_tier} / {pool.price_band_group} 的可比池样本不足。",
            "recommended_action_cn": "保留观察结果，但不要把该卖点强判为溢价或销量贡献。",
            "resolved_status": "open",
            "issue_payload_json": {
                "pool_sku_count": len(pool.sku_codes),
                "with_claim_sku_count": len(pool.with_claim_skus),
                "without_claim_sku_count": len(pool.without_claim_skus),
                "quality_flags": list(pool.quality_flags),
            },
            "input_fingerprint": stable_hash({"pool_id": pool_id, "issue_code": issue_code}, version="m12c-issue-input-v1"),
            "rule_version": rule_version,
            "is_current": True,
        }
        payload["result_hash"] = stable_hash(payload, version="m12c-review-issue-v1")
        rows.append(payload)
    return rows


def _pool_metric(pool: ClaimPool, markets: Mapping[str, MarketState]) -> dict[str, Any]:
    with_prices = [markets[sku].price for sku in pool.with_claim_skus if sku in markets]
    without_prices = [markets[sku].price for sku in pool.without_claim_skus if sku in markets]
    with_sales = [markets[sku].avg_weekly_sales_volume for sku in pool.with_claim_skus if sku in markets]
    without_sales = [markets[sku].avg_weekly_sales_volume for sku in pool.without_claim_skus if sku in markets]
    with_amount = [markets[sku].avg_weekly_sales_amount for sku in pool.with_claim_skus if sku in markets]
    without_amount = [markets[sku].avg_weekly_sales_amount for sku in pool.without_claim_skus if sku in markets]
    with_price_median = _median(with_prices)
    without_price_median = _median(without_prices)
    with_sales_median = _median(with_sales)
    without_sales_median = _median(without_sales)
    with_amount_median = _median(with_amount)
    without_amount_median = _median(without_amount)
    price_premium_abs = _none_delta(with_price_median, without_price_median, scale="q4")
    weekly_sales_lift_abs = _none_delta(with_sales_median, without_sales_median, scale="q6")
    weekly_amount_lift_abs = _none_delta(with_amount_median, without_amount_median, scale="q6")
    total_sales = sum((markets[sku].sales_volume_total for sku in pool.sku_codes if sku in markets), Decimal("0"))
    with_sales_total = sum((markets[sku].sales_volume_total for sku in pool.with_claim_skus if sku in markets), Decimal("0"))
    without_sales_total = sum((markets[sku].sales_volume_total for sku in pool.without_claim_skus if sku in markets), Decimal("0"))
    with_share = with_sales_total / total_sales if total_sales else Decimal("0")
    without_share = without_sales_total / total_sales if total_sales else Decimal("0")
    market_share_lift = (with_share / max(len(pool.with_claim_skus), 1)) - (without_share / max(len(pool.without_claim_skus), 1))
    price_rate = _rate(price_premium_abs, without_price_median)
    sales_rate = _rate(weekly_sales_lift_abs, without_sales_median)
    amount_rate = _rate(weekly_amount_lift_abs, without_amount_median)
    price_effect = _clamp(price_rate / Decimal("0.20"), Decimal("-1"), Decimal("1"))
    sales_effect = _clamp(sales_rate / Decimal("0.50"), Decimal("-1"), Decimal("1"))
    amount_effect = _clamp(amount_rate / Decimal("0.50"), Decimal("-1"), Decimal("1"))
    sample_factor = Decimal("1.0000") if pool.sample_status == "sufficient" else Decimal("0.6000") if pool.sample_status == "weak" else Decimal("0.2500")
    effect_score = _q4(price_effect * Decimal("0.35") + sales_effect * Decimal("0.30") + amount_effect * Decimal("0.25") + sample_factor * Decimal("0.10"))
    confidence = _q4(sample_factor * Decimal("0.70") + Decimal(min(len(pool.sku_codes), 20)) / Decimal("20") * Decimal("0.30"))
    return {
        "with_price_median": with_price_median,
        "without_price_median": without_price_median,
        "price_premium_abs": _q4(price_premium_abs),
        "price_premium_rate": _q6(price_rate),
        "with_weekly_sales_median": with_sales_median,
        "without_weekly_sales_median": without_sales_median,
        "weekly_sales_lift_abs": _q6(weekly_sales_lift_abs),
        "weekly_sales_lift_rate": _q6(sales_rate),
        "with_weekly_sales_amount_median": with_amount_median,
        "without_weekly_sales_amount_median": without_amount_median,
        "weekly_sales_amount_lift_abs": _q6(weekly_amount_lift_abs),
        "weekly_sales_amount_lift_rate": _q6(amount_rate),
        "market_share_lift": _q6(market_share_lift),
        "claim_value_effect_score": effect_score,
        "effect_confidence": confidence,
    }


def _param_profile_values(row: entities.Core3SkuParamProfile) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for blob in (
        row.param_values_json or {},
        row.core_picture_params_json or {},
        row.core_gaming_params_json or {},
        row.core_system_params_json or {},
        row.core_eye_care_params_json or {},
    ):
        _merge_param_values(values, blob)
    return values


def _merge_param_values(target: dict[str, Any], blob: Mapping[str, Any]) -> None:
    for key, value in blob.items():
        key_text = str(key)
        target.setdefault(key_text, value)
        if isinstance(value, Mapping) and not _looks_like_param_value(value):
            for child_key, child_value in value.items():
                target.setdefault(str(child_key), child_value)


def _looks_like_param_value(value: Mapping[str, Any]) -> bool:
    return any(key in value for key in ("value", "raw_value", "normalized_value", "unit", "source_field", "confidence", "exists"))


def _claim_parameter_competitiveness(
    *,
    pool: ClaimPool,
    target_sku: str,
    claim: ClaimState | None,
    claims: Mapping[str, Mapping[str, ClaimState]],
    comments: Mapping[str, CommentState],
    param_profiles: Mapping[str, ParamProfileState],
) -> dict[str, Any]:
    if pool.claim_code in M12C_SCENE_CONTEXT_CLAIM_CODES:
        return {
            "support_param_codes": [],
            "support_param_count": 0,
            "target_has_supporting_param": False,
            "key_param_results": [],
            "claim_label_coverage_rate": 0.0,
            "differentiated_param_coverage_rate": 0.0,
            "overall_parameter_competitiveness_score": 0.0,
            "overall_parameter_competitiveness_level": M12C_PARAM_LEVEL_WEAK,
            "overall_parameter_competitiveness_level_cn": _parameter_level_cn(M12C_PARAM_LEVEL_WEAK),
            "dimension_scores": {},
            "sparse_sample_flag": False,
            "wtp_input_guard": M04C_WTP_GUARD_NOT_SCOPE,
            "param_support_level": M04C_PARAM_SUPPORT_NO_PARAM,
            "eligibility_type": "scene_context_evidence",
            "downgrade_reason_cn": "该表达是用户场景或任务证据，不是可分配金额的产品卖点。",
            "explanation_cn": "场景表达只能解释用户任务、目标客群和价值战场，不能作为高溢价或销量贡献卖点。",
        }
    wtp_input_guard = _effective_wtp_input_guard(claim)
    if claim is not None and wtp_input_guard == M04C_WTP_GUARD_BLOCKED_GENERIC:
        support_param_codes = _claim_support_param_codes(claim, pool.claim_code)
        return {
            "support_param_codes": list(support_param_codes),
            "support_param_count": len(support_param_codes),
            "target_has_supporting_param": bool(support_param_codes),
            "key_param_results": [],
            "claim_label_coverage_rate": 0.0,
            "differentiated_param_coverage_rate": 0.0,
            "overall_parameter_competitiveness_score": 45.0,
            "overall_parameter_competitiveness_level": M12C_PARAM_LEVEL_PARITY,
            "overall_parameter_competitiveness_level_cn": _parameter_level_cn(M12C_PARAM_LEVEL_PARITY),
            "dimension_scores": {
                "parameter_truth_score": 45.0,
                "pool_position_score": 0.0,
                "direct_competitor_gap_score": 0.0,
                "param_comment_perception_score": 0.0,
                "formula_cn": "该卖点只有泛参数支撑，只能作为入围门槛，不能进入支付价值金额分配。",
            },
            "sparse_sample_flag": False,
            "wtp_input_guard": wtp_input_guard,
            "param_support_level": claim.param_support_level,
            "eligibility_type": "threshold_capability",
            "downgrade_reason_cn": "该卖点只有泛参数支撑，不能作为高溢价或人无我有支付价值依据。",
            "explanation_cn": "泛支撑参数只能证明基础能力存在，不能证明该具体卖点成立。",
        }
    if claim is not None and wtp_input_guard in {M04C_WTP_GUARD_BLOCKED_NO_PARAM, M04C_WTP_GUARD_NOT_SCOPE}:
        return {
            "support_param_codes": list(_claim_support_param_codes(claim, pool.claim_code)),
            "support_param_count": len(_claim_support_param_codes(claim, pool.claim_code)),
            "target_has_supporting_param": False,
            "key_param_results": [],
            "claim_label_coverage_rate": 0.0,
            "differentiated_param_coverage_rate": 0.0,
            "overall_parameter_competitiveness_score": 0.0,
            "overall_parameter_competitiveness_level": M12C_PARAM_LEVEL_WEAK,
            "overall_parameter_competitiveness_level_cn": _parameter_level_cn(M12C_PARAM_LEVEL_WEAK),
            "dimension_scores": {},
            "sparse_sample_flag": False,
            "wtp_input_guard": wtp_input_guard,
            "param_support_level": claim.param_support_level,
            "eligibility_type": "not_product_value_scope" if wtp_input_guard == M04C_WTP_GUARD_NOT_SCOPE else "certification_or_brand_claim_needs_specific_proof",
            "downgrade_reason_cn": "该卖点缺少具体参数支撑，不进入支付价值量化。",
            "explanation_cn": "缺少可比较的具体参数，不能作为用户支付价值依据。",
        }
    support_param_codes = _claim_support_param_codes(claim, pool.claim_code)
    target_entries: list[dict[str, Any]] = []
    param_results: list[dict[str, Any]] = []
    for param_code in support_param_codes:
        target_entry = _param_entry(param_profiles, claim, target_sku, param_code)
        if target_entry is None:
            continue
        target_entries.append(target_entry)
        pool_entries = [
            entry
            for sku in pool.sku_codes
            if (entry := _param_entry(param_profiles, claims.get(sku, {}).get(pool.claim_code), sku, param_code)) is not None
        ]
        param_results.append(_single_param_competitiveness(param_code=param_code, target_entry=target_entry, pool_entries=pool_entries))

    comment_strength = _comment_support_strength(comments.get(target_sku, _empty_comment(target_sku)), claim, pool)
    claim_label_coverage_rate = Decimal(len(pool.with_claim_skus)) / Decimal(max(len(pool.sku_codes), 1))
    if not support_param_codes:
        level = M12C_PARAM_LEVEL_WEAK
        score = Decimal("0")
        downgrade_reason = "该卖点缺少可用于比较的支撑参数，不能判断用户支付价值。"
    elif not target_entries:
        level = M12C_PARAM_LEVEL_WEAK
        score = Decimal("0")
        downgrade_reason = "本品没有找到该卖点的可比较参数事实，不能作为高溢价依据。"
    else:
        score_snapshot = _aggregate_param_competitiveness(param_results, comment_strength)
        level = str(score_snapshot["level"])
        score = _q4(Decimal(str(score_snapshot["score"])))
        downgrade_reason = str(score_snapshot.get("downgrade_reason_cn") or "")

    if target_entries:
        score_snapshot = _aggregate_param_competitiveness(param_results, comment_strength)
        level = str(score_snapshot["level"])
        score = _q4(Decimal(str(score_snapshot["score"])))
        downgrade_reason = str(score_snapshot.get("downgrade_reason_cn") or downgrade_reason)
        dimension_scores = score_snapshot.get("dimension_scores") or {}
    else:
        dimension_scores = {}
    differentiated_count = sum(1 for item in param_results if item.get("level") in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG})
    sparse_flag = any(item.get("level") == M12C_PARAM_LEVEL_SPARSE for item in param_results) or level == M12C_PARAM_LEVEL_SPARSE
    return {
        "support_param_codes": list(support_param_codes),
        "support_param_count": len(support_param_codes),
        "target_has_supporting_param": bool(target_entries),
        "key_param_results": param_results[:8],
        "claim_label_coverage_rate": float(_q4(claim_label_coverage_rate)),
        "differentiated_param_coverage_rate": float(_q4(Decimal(differentiated_count) / Decimal(max(len(param_results), 1)))) if param_results else 0.0,
        "overall_parameter_competitiveness_score": float(score),
        "overall_parameter_competitiveness_level": level,
        "overall_parameter_competitiveness_level_cn": _parameter_level_cn(level),
        "dimension_scores": dimension_scores,
        "sparse_sample_flag": sparse_flag,
        "wtp_input_guard": wtp_input_guard,
        "param_support_level": claim.param_support_level if claim else "",
        "eligibility_type": "quantifiable_product_claim" if target_entries else "certification_or_brand_claim_needs_specific_proof",
        "downgrade_reason_cn": downgrade_reason,
        "explanation_cn": _parameter_competitiveness_explanation(level, param_results, downgrade_reason),
    }


def _claim_support_param_codes(claim: ClaimState | None, claim_code: str) -> tuple[str, ...]:
    if claim_code in M12C_SCENE_CONTEXT_CLAIM_CODES:
        return ()
    strict_codes = set(M12C_STRICT_SUPPORT_PARAM_CODES.get(claim_code, ()))
    ordered: list[str] = []
    for code in (claim.primary_supporting_param_codes if claim else ()):
        text = str(code).strip()
        if strict_codes and text not in strict_codes:
            continue
        if text and not text.startswith("_") and text not in ordered:
            ordered.append(text)
    for code in (claim.supporting_param_codes if claim else ()):
        text = str(code).strip()
        if strict_codes and text not in strict_codes:
            continue
        if text and not text.startswith("_") and text not in ordered:
            ordered.append(text)
    for code in M12C_CLAIM_PARAM_FALLBACKS.get(claim_code, ()):
        if strict_codes and code not in strict_codes:
            continue
        if code and not code.startswith("_") and code not in ordered:
            ordered.append(code)
    return tuple(ordered)


def _param_entry(
    param_profiles: Mapping[str, ParamProfileState],
    claim: ClaimState | None,
    sku_code: str,
    param_code: str,
) -> dict[str, Any] | None:
    aliases = (param_code, *M12C_PARAM_ALIASES.get(param_code, ()))
    profile = param_profiles.get(sku_code)
    if profile:
        for alias in aliases:
            if alias in profile.values:
                raw = profile.values[alias]
                normalized = _normalized_param_value(raw)
                if not _missing_value(normalized):
                    return {
                        "sku_code": sku_code,
                        "param_code": param_code,
                        "source_param_code": alias,
                        "raw_value": raw,
                        "normalized_value": normalized,
                        "value_type": _param_value_type(normalized),
                        "source_module": "M03B",
                    }
    snapshot = claim.supporting_param_snapshot if claim else {}
    if isinstance(snapshot, Mapping):
        for alias in aliases:
            if alias in snapshot:
                raw = snapshot[alias]
                normalized = _normalized_param_value(raw)
                if not _missing_value(normalized):
                    return {
                        "sku_code": sku_code,
                        "param_code": param_code,
                        "source_param_code": alias,
                        "raw_value": raw,
                        "normalized_value": normalized,
                        "value_type": _param_value_type(normalized),
                        "source_module": "M04C",
                    }
    return None


def _single_param_competitiveness(*, param_code: str, target_entry: Mapping[str, Any], pool_entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    target_value = target_entry.get("normalized_value")
    numeric_target = _decimal_param_value(target_value)
    numeric_values = [_decimal_param_value(entry.get("normalized_value")) for entry in pool_entries]
    numeric_values = [value for value in numeric_values if value is not None]
    known_values = [entry.get("normalized_value") for entry in pool_entries if not _missing_value(entry.get("normalized_value"))]
    sample_count = len(known_values)
    if not _boolean_like_param(param_code, target_value) and numeric_target is not None and numeric_values:
        return _numeric_param_competitiveness(param_code, target_entry, numeric_target, numeric_values)
    return _categorical_param_competitiveness(param_code, target_entry, known_values, sample_count)


def _numeric_param_competitiveness(param_code: str, target_entry: Mapping[str, Any], target_value: Decimal, pool_values: Sequence[Decimal]) -> dict[str, Any]:
    sorted_values = sorted(pool_values)
    sample_count = len(sorted_values)
    if sample_count < 3:
        level = M12C_PARAM_LEVEL_SPARSE
        score = Decimal("58")
        percentile = Decimal("0")
        reason = "可比池中该参数样本不足，保留观察但不能强判。"
    else:
        less_equal = sum(1 for value in sorted_values if value <= target_value)
        percentile = _q4(Decimal(less_equal) / Decimal(sample_count))
        if percentile >= Decimal("0.8500"):
            level = M12C_PARAM_LEVEL_LEADING
            score = Decimal("92")
            reason = "本品关键参数位于同战场可比池前列，可支撑差异化支付价值。"
        elif percentile >= Decimal("0.6500"):
            level = M12C_PARAM_LEVEL_STRONG
            score = Decimal("78")
            reason = "本品关键参数高于多数可比 SKU，具备较强支撑。"
        elif percentile >= Decimal("0.3500"):
            level = M12C_PARAM_LEVEL_PARITY
            score = Decimal("52")
            reason = "本品关键参数接近可比池中位，更接近入围门槛。"
        else:
            level = M12C_PARAM_LEVEL_WEAK
            score = Decimal("32")
            reason = "本品关键参数低于多数可比 SKU，不能支撑高溢价。"
    median_value = _median(sorted_values) or Decimal("0")
    max_value = max(sorted_values) if sorted_values else Decimal("0")
    return {
        "param_code": param_code,
        "source_param_code": target_entry.get("source_param_code"),
        "target_value": _json_value(target_entry.get("normalized_value")),
        "target_numeric_value": float(_q4(target_value)),
        "sample_count": sample_count,
        "pool_median": float(_q4(median_value)),
        "pool_max": float(_q4(max_value)),
        "pool_percentile": float(percentile),
        "score": float(_q4(score)),
        "level": level,
        "level_cn": _parameter_level_cn(level),
        "reason_cn": reason,
    }


def _categorical_param_competitiveness(param_code: str, target_entry: Mapping[str, Any], known_values: Sequence[Any], sample_count: int) -> dict[str, Any]:
    target_value = target_entry.get("normalized_value")
    if sample_count < 3:
        level = M12C_PARAM_LEVEL_SPARSE
        score = Decimal("55") if not _missing_value(target_value) else Decimal("0")
        coverage_rate = Decimal("0")
        reason = "可比池中该参数样本不足，保留观察但不能强判。"
    else:
        boolean_like = _boolean_like_param(param_code, target_value)
        target_truthy = _truthy_param_value(target_value)
        true_count = sum(1 for value in known_values if _truthy_param_value(value))
        same_count = sum(1 for value in known_values if _normalized_text(value) == _normalized_text(target_value))
        true_rate = Decimal(true_count) / Decimal(sample_count)
        same_rate = Decimal(same_count) / Decimal(sample_count)
        coverage_rate = true_rate if boolean_like else same_rate
        if target_truthy is False or _missing_value(target_value):
            level = M12C_PARAM_LEVEL_WEAK
            score = Decimal("25")
            reason = "本品没有形成该参数能力，不能作为高溢价依据。"
        elif coverage_rate >= Decimal("0.7500"):
            level = M12C_PARAM_LEVEL_PARITY
            score = Decimal("45")
            reason = "可比池中多数 SKU 都具备该能力，更接近基础门槛。"
        elif coverage_rate >= Decimal("0.4000"):
            level = M12C_PARAM_LEVEL_STRONG
            score = Decimal("68")
            reason = "该能力在可比池中不是普遍配置，具备一定差异化。"
        else:
            level = M12C_PARAM_LEVEL_LEADING
            score = Decimal("82")
            reason = "该能力在同战场可比池中相对稀缺，可作为差异化卖点。"
    return {
        "param_code": param_code,
        "source_param_code": target_entry.get("source_param_code"),
        "target_value": _json_value(target_value),
        "sample_count": sample_count,
        "pool_coverage_rate": float(_q4(coverage_rate)),
        "score": float(_q4(score)),
        "level": level,
        "level_cn": _parameter_level_cn(level),
        "reason_cn": reason,
    }


def _aggregate_param_competitiveness(param_results: Sequence[Mapping[str, Any]], comment_strength: Decimal) -> dict[str, Any]:
    if not param_results:
        return {
            "score": 0,
            "level": M12C_PARAM_LEVEL_WEAK,
            "downgrade_reason_cn": "缺少可比较参数。",
            "dimension_scores": {},
        }
    param_scores = [_q4(Decimal(str(item.get("score") or 0))) for item in param_results]
    best_score = max(param_scores)
    avg_score = _avg(param_scores)
    leading_count = sum(1 for item in param_results if item.get("level") == M12C_PARAM_LEVEL_LEADING)
    strong_count = sum(1 for item in param_results if item.get("level") == M12C_PARAM_LEVEL_STRONG)
    sparse_count = sum(1 for item in param_results if item.get("level") == M12C_PARAM_LEVEL_SPARSE)
    parameter_truth_score = Decimal("100") if best_score > 0 else Decimal("0")
    pool_position_score = best_score
    direct_competitor_gap_score = _q4(best_score * Decimal("0.70") + avg_score * Decimal("0.30"))
    param_comment_perception_score = _strength_score(comment_strength)
    total = _q4(
        parameter_truth_score * Decimal("0.35")
        + pool_position_score * Decimal("0.30")
        + direct_competitor_gap_score * Decimal("0.20")
        + param_comment_perception_score * Decimal("0.15")
    )
    if sparse_count == len(param_results):
        level = M12C_PARAM_LEVEL_SPARSE
        reason = "支撑参数样本不足，不能强判为高溢价。"
    elif leading_count > 0 and total >= Decimal("75"):
        level = M12C_PARAM_LEVEL_LEADING
        reason = ""
    elif leading_count + strong_count > 0 and total >= Decimal("65"):
        level = M12C_PARAM_LEVEL_STRONG
        reason = ""
    elif best_score >= Decimal("40"):
        level = M12C_PARAM_LEVEL_PARITY
        reason = "关键参数接近同战场门槛，不能单独支撑高溢价。"
    else:
        level = M12C_PARAM_LEVEL_WEAK
        reason = "关键参数竞争力不足，不能支撑该卖点支付价值。"
    return {
        "score": float(total),
        "level": level,
        "downgrade_reason_cn": reason,
        "dimension_scores": {
            "parameter_truth_score": float(_q4(parameter_truth_score)),
            "pool_position_score": float(_q4(pool_position_score)),
            "direct_competitor_gap_score": float(_q4(direct_competitor_gap_score)),
            "param_comment_perception_score": float(_q4(param_comment_perception_score)),
            "formula_cn": "参数竞争力 = 参数事实成立35% + 战场池位置30% + 竞品差距20% + 评论感知15%。",
        },
    }


def _normalized_param_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        for key in ("normalized_value", "business_value", "value", "raw_value", "exists"):
            if key in value and not _missing_value(value[key]):
                return _normalized_param_value(value[key])
        return value
    if isinstance(value, (list, tuple)):
        if len(value) == 1:
            return _normalized_param_value(value[0])
        return ",".join(str(_normalized_param_value(item)) for item in value if not _missing_value(item))
    return value


def _missing_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "—", "无", "未知", "不详", "None", "null"}
    return False


def _decimal_param_value(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return Decimal("1") if value else Decimal("0")
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except Exception:
            return None
    if isinstance(value, Mapping):
        normalized = _normalized_param_value(value)
        if isinstance(normalized, Mapping):
            return None
        return _decimal_param_value(normalized)
    if isinstance(value, str):
        text = value.replace(",", "").replace("，", "").strip()
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match:
            try:
                return Decimal(match.group(0))
            except Exception:
                return None
    return None


def _truthy_param_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)) > 0
    if isinstance(value, Mapping):
        normalized = _normalized_param_value(value)
        if isinstance(normalized, Mapping):
            return None
        return _truthy_param_value(normalized)
    text = str(value or "").strip().lower()
    if not text or text in {"0", "false", "no", "none", "null", "无", "否", "不支持", "未见", "-"}:
        return False
    if text in {"1", "true", "yes", "有", "支持", "是"}:
        return True
    return True


def _boolean_like_param(param_code: str, value: Any) -> bool:
    if param_code.endswith("_flag") or param_code.endswith("_support"):
        return True
    text = str(value or "").strip().lower()
    return text in {"0", "1", "true", "false", "yes", "no", "有", "无", "支持", "不支持", "是", "否", "未见"}


def _param_value_type(value: Any) -> str:
    if _decimal_param_value(value) is not None:
        return "numeric"
    if isinstance(_truthy_param_value(value), bool):
        return "boolean_or_category"
    return "text"


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(_q4(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _normalized_text(value: Any) -> str:
    return str(_normalized_param_value(value) or "").strip().lower()


def _parameter_level_cn(level: str) -> str:
    return {
        M12C_PARAM_LEVEL_LEADING: "领先优势",
        M12C_PARAM_LEVEL_STRONG: "较强优势",
        M12C_PARAM_LEVEL_PARITY: "基础门槛",
        M12C_PARAM_LEVEL_WEAK: "弱或缺失",
        M12C_PARAM_LEVEL_SPARSE: "样本不足",
    }.get(level, "未判断")


def _parameter_competitiveness_explanation(level: str, param_results: Sequence[Mapping[str, Any]], downgrade_reason: str) -> str:
    if downgrade_reason:
        return downgrade_reason
    leading = [str(item.get("param_code") or "") for item in param_results if item.get("level") in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG}]
    if leading:
        return f"关键参数 {'、'.join(leading[:3])} 在同战场可比池中具备优势。"
    if level == M12C_PARAM_LEVEL_PARITY:
        return "支撑参数更多表现为入围能力，不宜作为单独溢价来源。"
    return "参数竞争力未形成稳定优势。"


def _source_type_cn(source_type: str) -> str:
    return {
        M12C_TARGET_FACT_CLAIM: "本品已成立卖点",
        M12C_TARGET_PARAM_CAPABILITY: "本品参数能力待激活",
        M12C_COMPETITOR_GAP: "竞品拦截/机会缺口",
    }.get(source_type, "未分类来源")


def _claim_source_type(
    *,
    has_claim: bool,
    parameter_competitiveness: Mapping[str, Any],
    battlefield_claim_relevance: Decimal,
) -> str:
    if has_claim:
        return M12C_TARGET_FACT_CLAIM
    level = str(parameter_competitiveness.get("overall_parameter_competitiveness_level") or "")
    has_param = bool(parameter_competitiveness.get("target_has_supporting_param"))
    if has_param and battlefield_claim_relevance >= Decimal("0.7000") and level in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG}:
        return M12C_TARGET_PARAM_CAPABILITY
    return M12C_COMPETITOR_GAP


def _unique_nonempty(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _amount_quantification_basis(pool: ClaimPool, target_sku: str) -> dict[str, Any]:
    reasons: list[str] = []
    quality_flags: list[str] = []
    if pool.pool_relax_level in {"L3", "L4"}:
        reasons.append("可比池已放宽到趋势观察或兜底层级，不能分配金额。")
        quality_flags.append("relaxed_pool_not_amount_quantifiable")
    if pool.pool_relax_level == "L2" and pool.sample_status != "sufficient":
        reasons.append("相邻价格带放宽后样本仍不足，不能分配金额。")
        quality_flags.append("l2_sample_not_sufficient")
    if pool.sample_status != "sufficient":
        reasons.append("可比池样本状态不足，不能稳定量化。")
        quality_flags.append("sample_not_sufficient_for_amount")
    if len(pool.with_claim_skus) < MIN_GROUP_SKU_COUNT:
        reasons.append(f"{pool.comparison_group_label_cn}没有有效 SKU，不能形成比较组。")
        quality_flags.append("with_claim_group_too_small")
    if len(pool.without_claim_skus) < MIN_GROUP_SKU_COUNT:
        reasons.append(f"{pool.control_group_label_cn}没有有效 SKU，不能形成对照组。")
        quality_flags.append("without_claim_group_too_small")
    if "l4_threshold_only" in pool.quality_flags:
        reasons.append("L4 兜底池只能用于门槛或待验证判断。")
        quality_flags.append("l4_threshold_only_no_amount")
    ready = not reasons
    if ready and target_sku in pool.with_claim_skus and len(pool.with_claim_skus) <= 1:
        sample_grade = "可量化，比较组单样本"
        quality_flags.append("single_sku_comparison_group")
    else:
        sample_grade = "可量化" if ready else "对照样本不足"
    return {
        "amount_quantification_ready": ready,
        "sample_grade": sample_grade,
        "no_amount_reason_cn": "；".join(_unique_nonempty(reasons)) or "",
        "quality_flags": tuple(_unique_nonempty(quality_flags)),
    }


def _is_unique_payment_potential_candidate(
    *,
    has_claim: bool,
    pool: ClaimPool,
    target_sku: str,
    param_strength: Decimal,
    comment_strength: Decimal,
    semantic_strength: Decimal,
    battlefield_claim_relevance: Decimal,
    parameter_competitiveness: Mapping[str, Any] | None,
    source_type: str,
) -> bool:
    if not has_claim or source_type != M12C_TARGET_FACT_CLAIM:
        return False
    if pool.claim_code in M12C_FORCE_THRESHOLD_CLAIM_CODES:
        return False
    if _amount_quantification_basis(pool, target_sku)["amount_quantification_ready"]:
        return False
    if semantic_strength < Decimal("0.5000") or battlefield_claim_relevance < Decimal("0.7000"):
        return False
    param_level = str((parameter_competitiveness or {}).get("overall_parameter_competitiveness_level") or "")
    param_sparse = bool((parameter_competitiveness or {}).get("sparse_sample_flag")) or param_level == M12C_PARAM_LEVEL_SPARSE
    param_evidence = (
        (param_level in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG} and not param_sparse)
        or param_strength >= Decimal("0.7500")
    )
    user_evidence = comment_strength >= Decimal("0.5000")
    weak_control = (
        len(pool.with_claim_skus) < MIN_GROUP_SKU_COUNT
        or len(pool.without_claim_skus) < MIN_GROUP_SKU_COUNT
        or (target_sku in pool.with_claim_skus and len(pool.with_claim_skus) <= 1)
    )
    return weak_control and (param_evidence or user_evidence)


def _unique_payment_potential_scorecard(
    *,
    pool: ClaimPool,
    target_sku: str,
    param_strength: Decimal,
    comment_strength: Decimal,
    semantic_strength: Decimal,
    parameter_competitiveness: Mapping[str, Any] | None,
    amount_basis: Mapping[str, Any],
) -> dict[str, Any]:
    coverage_rate = Decimal(len(pool.with_claim_skus)) / Decimal(max(len(pool.sku_codes), 1))
    dimensions = [
        _unique_score_dimension(
            code="battlefield_relevance",
            name_cn="战场相关度",
            raw_score=_context_relevance_score(pool.context_type, semantic_strength),
            reason_cn=_context_relevance_reason(pool, semantic_strength),
        ),
        _unique_score_dimension(
            code="parameter_competitiveness",
            name_cn="参数竞争力",
            raw_score=_parameter_competitiveness_score(param_strength, parameter_competitiveness),
            reason_cn=_parameter_competitiveness_reason(True, param_strength, parameter_competitiveness),
        ),
        _unique_score_dimension(
            code="comment_perception",
            name_cn="用户评论感知",
            raw_score=_comment_score(comment_strength, False),
            reason_cn=_comment_reason(comment_strength, False),
        ),
        _unique_score_dimension(
            code="competitor_gap",
            name_cn="竞品缺口",
            raw_score=_unique_competitor_gap_score(pool, target_sku, coverage_rate),
            reason_cn=_unique_competitor_gap_reason(pool, target_sku, coverage_rate),
        ),
    ]
    total_score = _q4(sum(_q4(Decimal(str(item["raw_score"])) * Decimal(str(item["weight"]))) for item in dimensions))
    if total_score >= Decimal("75"):
        potential_level_cn = "高潜力"
    elif total_score >= Decimal("60"):
        potential_level_cn = "中等潜力"
    else:
        potential_level_cn = "低潜力"
    return {
        "total_score": float(total_score),
        "score_unit": "0-100",
        "potential_level_cn": potential_level_cn,
        "score_method_cn": "人无我有支付价值潜力分 = 战场相关度30% + 参数竞争力30% + 用户评论感知25% + 竞品缺口15%。",
        "dimensions": dimensions,
        "no_amount_reason_cn": amount_basis.get("no_amount_reason_cn") or "同战场缺少稳定对照样本，不能量化金额。",
        "verification_required_cn": "需要后续在同价值战场、同尺寸价格池中继续观察竞品跟进、用户评论、销量承接和价格变化。",
        "sample_grade": amount_basis.get("sample_grade") or "对照样本不足",
        "pool_relax_level": pool.pool_relax_level,
        "pool_key": f"{pool.context_type}:{pool.context_code}:{pool.size_tier}:{pool.price_band_group}:{pool.claim_code}",
        "report_explanation_cn": (
            f"{pool.claim_name} 在 {pool.context_name} 中具备提高用户最高支付意愿的潜力，"
            "但当前同战场可比对照不足，只能输出潜力和证据链，不能输出确定金额。"
        ),
    }


def _unique_score_dimension(*, code: str, name_cn: str, raw_score: Decimal, reason_cn: str) -> dict[str, Any]:
    weight = M12C_UNIQUE_SCORE_WEIGHTS[code]
    raw = _q4(_clamp(raw_score, Decimal("0"), Decimal("100")))
    return {
        "code": code,
        "name_cn": name_cn,
        "weight": float(weight),
        "raw_score": float(raw),
        "weighted_score": float(_q4(raw * weight)),
        "reason_cn": reason_cn,
    }


def _unique_competitor_gap_score(pool: ClaimPool, target_sku: str, coverage_rate: Decimal) -> Decimal:
    if target_sku in pool.with_claim_skus and len(pool.with_claim_skus) <= 1:
        return Decimal("90")
    if len(pool.with_claim_skus) < MIN_GROUP_SKU_COUNT:
        return Decimal("82")
    if len(pool.without_claim_skus) < MIN_GROUP_SKU_COUNT:
        return Decimal("62")
    if coverage_rate <= Decimal("0.3000"):
        return Decimal("78")
    return Decimal("45")


def _unique_competitor_gap_reason(pool: ClaimPool, target_sku: str, coverage_rate: Decimal) -> str:
    if target_sku in pool.with_claim_skus and len(pool.with_claim_skus) <= 1:
        return f"目标 SKU 是同战场{pool.comparison_group_label_cn}的唯一样本，说明竞品缺少可直接对照的同类表达。"
    if len(pool.with_claim_skus) < MIN_GROUP_SKU_COUNT:
        return f"同战场{pool.comparison_group_label_cn}样本过少，卖点具备稀缺性，但不能量化金额。"
    if len(pool.without_claim_skus) < MIN_GROUP_SKU_COUNT:
        return f"同战场缺少稳定{pool.control_group_label_cn}，不能判断组间价差。"
    return f"同战场约 {float(_q4(coverage_rate * Decimal('100'))):.0f}% SKU 具备该卖点，差异性需要继续验证。"


def _claim_role(
    *,
    target_sku: str,
    has_claim: bool,
    metric: Mapping[str, Any],
    pool: ClaimPool,
    param_strength: Decimal,
    comment_strength: Decimal,
    semantic_strength: Decimal,
    battlefield_claim_relevance: Decimal = Decimal("1.0000"),
    has_negative: bool = False,
    parameter_competitiveness: Mapping[str, Any] | None = None,
    source_type: str = M12C_TARGET_FACT_CLAIM,
    market_price: Decimal | None = None,
) -> str:
    if pool.claim_code in M12C_SCENE_CONTEXT_CLAIM_CODES:
        return M12C_ROLE_BRAND if has_claim else M12C_ROLE_SAMPLE
    if has_negative or (has_claim and param_strength <= Decimal("0.2000")):
        return M12C_ROLE_DRAG
    wtp_input_guard = str((parameter_competitiveness or {}).get("wtp_input_guard") or "")
    if has_claim and wtp_input_guard == M04C_WTP_GUARD_BLOCKED_GENERIC:
        return M12C_ROLE_BASIC
    if has_claim and wtp_input_guard in {M04C_WTP_GUARD_BLOCKED_NO_PARAM, M04C_WTP_GUARD_NOT_SCOPE}:
        return M12C_ROLE_BRAND
    if (
        has_claim
        and pool.claim_code in M12C_STRICT_SUPPORT_PARAM_CODES
        and parameter_competitiveness is not None
        and not bool(parameter_competitiveness.get("target_has_supporting_param"))
    ):
        return M12C_ROLE_BRAND
    param_level = str((parameter_competitiveness or {}).get("overall_parameter_competitiveness_level") or "")
    param_sparse = bool((parameter_competitiveness or {}).get("sparse_sample_flag")) or param_level == M12C_PARAM_LEVEL_SPARSE
    if parameter_competitiveness is None:
        param_can_premium = param_strength >= Decimal("0.6000")
    else:
        param_can_premium = param_level in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG} and not param_sparse
    if has_claim and pool.claim_code in M12C_FORCE_THRESHOLD_CLAIM_CODES:
        return M12C_ROLE_BASIC
    price_delta = _q4(metric["price_premium_abs"])
    sales_delta = _q6(metric["weekly_sales_lift_abs"])
    amount_delta = _q6(metric["weekly_sales_amount_lift_abs"])
    price_positive = price_delta > Decimal("0")
    sales_positive = sales_delta > Decimal("0")
    amount_positive = amount_delta > Decimal("0")
    amount_basis = _amount_quantification_basis(pool, target_sku)
    if not has_claim:
        if source_type == M12C_TARGET_PARAM_CAPABILITY:
            return M12C_ROLE_WEAK_USER if param_can_premium else M12C_ROLE_BRAND
        if price_positive and metric["effect_confidence"] >= Decimal("0.4000"):
            with_price_median = metric.get("with_price_median")
            if market_price is not None and with_price_median is not None and _q4(market_price) < _q4(with_price_median):
                return M12C_ROLE_HIGH_PRICE_INTERCEPT
            return M12C_ROLE_PRICE_UP
        if (sales_positive or amount_positive) and metric["effect_confidence"] >= Decimal("0.4000"):
            return M12C_ROLE_OPPORTUNITY
        return M12C_ROLE_SAMPLE
    coverage_rate = Decimal(len(pool.with_claim_skus)) / Decimal(max(len(pool.sku_codes), 1))
    if not amount_basis["amount_quantification_ready"]:
        if coverage_rate >= Decimal("0.7500"):
            return M12C_ROLE_BASIC
        if _is_unique_payment_potential_candidate(
            has_claim=has_claim,
            pool=pool,
            target_sku=target_sku,
            param_strength=param_strength,
            comment_strength=comment_strength,
            semantic_strength=semantic_strength,
            battlefield_claim_relevance=battlefield_claim_relevance,
            parameter_competitiveness=parameter_competitiveness,
            source_type=source_type,
        ):
            return M12C_ROLE_UNIQUE
        if param_strength >= Decimal("0.6000") or comment_strength >= Decimal("0.6000"):
            return M12C_ROLE_WEAK_USER
        return M12C_ROLE_SAMPLE
    positive_price_value = (
        price_positive
        and amount_positive
        and battlefield_claim_relevance >= Decimal("0.9000")
        and semantic_strength >= Decimal("0.5000")
        and max(param_strength, comment_strength) >= Decimal("0.6000")
        and param_can_premium
        and amount_basis["amount_quantification_ready"]
    )
    if battlefield_claim_relevance < Decimal("0.9000"):
        if sales_positive and max(comment_strength, param_strength) >= Decimal("0.6000") and (param_can_premium or comment_strength >= Decimal("0.8000")):
            return M12C_ROLE_SALES
        if param_strength >= Decimal("0.6000") or comment_strength >= Decimal("0.6000"):
            return M12C_ROLE_WEAK_USER
        return M12C_ROLE_BRAND
    if coverage_rate >= Decimal("0.7500"):
        if positive_price_value and pool.claim_code in M12C_TIER_DIFFERENTIATED_CLAIM_CODES:
            return M12C_ROLE_PREMIUM
        return M12C_ROLE_BASIC
    if pool.pool_relax_level == "L4":
        return M12C_ROLE_SAMPLE
    if pool.sample_status == "insufficient":
        return M12C_ROLE_SAMPLE
    if pool.sample_status == "weak":
        if positive_price_value and param_can_premium:
            return M12C_ROLE_PREMIUM
        return M12C_ROLE_SAMPLE
    if positive_price_value:
        return M12C_ROLE_PREMIUM
    if sales_positive and semantic_strength >= Decimal("0.4500") and max(comment_strength, param_strength) >= Decimal("0.5000"):
        return M12C_ROLE_SALES
    if not price_positive and (amount_positive or sales_positive) and semantic_strength >= Decimal("0.5000") and max(param_strength, comment_strength) >= Decimal("0.5500"):
        return M12C_ROLE_VALUE_BUNDLE
    if param_strength >= Decimal("0.6000") and comment_strength < Decimal("0.5000") and semantic_strength >= Decimal("0.4500"):
        return M12C_ROLE_WEAK_USER
    if comment_strength >= Decimal("0.8000") and param_strength < Decimal("0.5000"):
        return M12C_ROLE_USER_NEED
    return M12C_ROLE_BRAND


def _claim_value_scorecard(
    *,
    pool: ClaimPool,
    role: str,
    metric: Mapping[str, Any],
    has_claim: bool,
    param_strength: Decimal,
    comment_strength: Decimal,
    semantic_strength: Decimal,
    has_negative: bool,
    market_position: Mapping[str, Any],
    market_acceptance: Mapping[str, Any] | None = None,
    parameter_competitiveness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    coverage_rate = Decimal(len(pool.with_claim_skus)) / Decimal(max(len(pool.sku_codes), 1))
    price_delta = _q4(metric["price_premium_abs"])
    sales_delta = _q6(metric["weekly_sales_lift_abs"])
    amount_delta = _q6(metric["weekly_sales_amount_lift_abs"])
    dimensions = [
        _score_dimension(
            code="battlefield_relevance",
            name_cn="战场相关度",
            raw_score=_context_relevance_score(pool.context_type, semantic_strength),
            reason_cn=_context_relevance_reason(pool, semantic_strength),
            evidence_refs=[_evidence_ref(pool.context_type, pool.context_code)],
        ),
        _score_dimension(
            code="parameter_competitiveness",
            name_cn="参数竞争力",
            raw_score=_parameter_competitiveness_score(param_strength, parameter_competitiveness),
            reason_cn=_parameter_competitiveness_reason(has_claim, param_strength, parameter_competitiveness),
            evidence_refs=[
                {"source_module": "M03B", "evidence_type": "sku_param_profile"},
                {"source_module": "M04C", "evidence_type": "claim_param_support"},
            ],
        ),
        _score_dimension(
            code="comment_perception",
            name_cn="用户评论感知",
            raw_score=_comment_score(comment_strength, has_negative),
            reason_cn=_comment_reason(comment_strength, has_negative),
            evidence_refs=[{"source_module": "M05C", "evidence_type": "claim_comment_support"}],
        ),
        _score_dimension(
            code="competitor_difference",
            name_cn="竞品差异",
            raw_score=_competitor_difference_score(has_claim, coverage_rate, price_delta, sales_delta, amount_delta),
            reason_cn=_competitor_difference_reason(has_claim, coverage_rate, pool),
            evidence_refs=[{"source_module": "M12C", "evidence_type": "with_claim_vs_without_claim_pool"}],
        ),
        _score_dimension(
            code="market_validation",
            name_cn="市场验证",
            raw_score=_market_validation_score(pool, price_delta, sales_delta, amount_delta, market_position, market_acceptance),
            reason_cn=_market_validation_reason(pool, price_delta, sales_delta, amount_delta, market_position, market_acceptance),
            evidence_refs=[{"source_module": "M07", "evidence_type": "price_sales_market_profile"}],
        ),
    ]
    downgrade_reasons = _scorecard_downgrade_reasons(
        pool=pool,
        role=role,
        has_claim=has_claim,
        has_negative=has_negative,
        coverage_rate=coverage_rate,
        param_strength=param_strength,
        comment_strength=comment_strength,
        parameter_competitiveness=parameter_competitiveness,
    )
    total_score = _q4(sum(_q4(Decimal(str(item["raw_score"])) * Decimal(str(item["weight"]))) for item in dimensions))
    return {
        "total_score": float(total_score),
        "score_unit": "0-100",
        "score_method_cn": "卖点支付价值分 = 战场相关度20% + 参数竞争力25% + 用户评论感知25% + 竞品差异15% + 市场验证15%。",
        "dimensions": dimensions,
        "downgrade_reasons": downgrade_reasons,
        "sample_status": pool.sample_status,
        "pool_relax_level": pool.pool_relax_level,
        "pool_sku_count": len(pool.sku_codes),
        "with_claim_sku_count": len(pool.with_claim_skus),
        "without_claim_sku_count": len(pool.without_claim_skus),
        "claim_coverage_rate": float(_q4(coverage_rate)),
        "market_position_type": market_position["type"],
        "market_acceptance": market_acceptance or {},
    }


def _score_dimension(*, code: str, name_cn: str, raw_score: Decimal, reason_cn: str, evidence_refs: list[dict[str, Any]]) -> dict[str, Any]:
    weight = M12C_SCORE_WEIGHTS[code]
    raw = _q4(_clamp(raw_score, Decimal("0"), Decimal("100")))
    return {
        "code": code,
        "name_cn": name_cn,
        "weight": float(weight),
        "raw_score": float(raw),
        "weighted_score": float(_q4(raw * weight)),
        "reason_cn": reason_cn,
        "evidence_refs": evidence_refs,
    }


def _context_relevance_score(context_type: str, semantic_strength: Decimal) -> Decimal:
    raw = _strength_score(semantic_strength)
    if context_type == "battlefield":
        return max(raw, Decimal("55"))
    if context_type in {"user_task", "target_group"}:
        return min(raw, Decimal("85"))
    return min(raw, Decimal("60"))


def _battlefield_claim_relevance_strength(pool: ClaimPool, claim: ClaimState | None) -> Decimal:
    if pool.context_type != "battlefield" or claim is None:
        return Decimal("0.0000")
    text = " ".join(
        [
            claim.claim_code,
            claim.claim_name,
            claim.claim_dimension,
            claim.claim_subtype,
            " ".join(claim.supporting_param_codes),
        ]
    ).lower()
    if _keyword_hit(text, _battlefield_core_keywords(pool.context_code)):
        return Decimal("1.0000")
    if _keyword_hit(text, _battlefield_support_keywords(pool.context_code)):
        return Decimal("0.7000")
    return Decimal("0.2500")


def _battlefield_core_keywords(context_code: str) -> tuple[str, ...]:
    code = context_code.upper()
    if "PREMIUM_PICTURE" in code:
        return ("画质", "亮度", "高亮", "控光", "分区", "色彩", "色域", "hdr", "miniled", "mini led", "oled", "qd", "量子点", "清晰", "分辨率", "芯片", "背光")
    if "GAMING" in code or "SPORTS" in code:
        return ("游戏", "高刷", "刷新", "hdmi", "vrr", "allm", "低延迟", "延迟", "运动", "体育", "流畅", "芯片")
    if "SMART_CONNECTED" in code:
        return ("智能", "ai", "语音", "投屏", "互联", "wifi", "蓝牙", "摄像头", "iot", "家电联动", "芯片", "内存", "系统")
    if "EYE_CARE" in code:
        return ("护眼", "蓝光", "频闪", "儿童", "舒适", "健康")
    if "CINEMA" in code or "THEATER" in code:
        return ("影院", "沉浸", "音响", "杜比", "hdr", "大屏", "画质", "亮度", "控光")
    if "LIVING" in code or "FAMILY" in code:
        return ("客厅", "家庭", "画质", "音响", "智能", "护眼", "大屏", "全面屏")
    return ("画质", "智能", "价格", "销量", "性价比")


def _battlefield_support_keywords(context_code: str) -> tuple[str, ...]:
    code = context_code.upper()
    if "PREMIUM_PICTURE" in code:
        return ("杜比", "护眼", "影院", "音响", "高刷", "刷新")
    if "GAMING" in code or "SPORTS" in code:
        return ("高亮", "亮度", "运动补偿", "音效", "杜比")
    if "SMART_CONNECTED" in code:
        return ("遥控", "系统", "应用", "开机", "处理器")
    if "EYE_CARE" in code:
        return ("画质", "亮度", "儿童", "家庭")
    return ("画质", "智能", "护眼", "音响", "芯片")


def _keyword_hit(text: str, keywords: Sequence[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def _context_relevance_reason(pool: ClaimPool, semantic_strength: Decimal) -> str:
    if pool.context_type == "battlefield":
        return f"该卖点在 {pool.context_name} 内评估，战场相关度结合 SKU 主辅战场关系和卖点对该战场购买理由的相关度，折算为 {float(_strength_score(semantic_strength)):.0f} 分。"
    if pool.context_type == "user_task":
        return f"该卖点在用户任务 {pool.context_name} 内评估，作为战场解释的辅助证据。"
    if pool.context_type == "target_group":
        return f"该卖点在目标客群 {pool.context_name} 内评估，作为战场解释的辅助证据。"
    return "整体市场池只用于兜底观察，不作为强支付价值的核心场景。"


def _parameter_competitiveness_score(param_strength: Decimal, parameter_competitiveness: Mapping[str, Any] | None) -> Decimal:
    if parameter_competitiveness:
        return _q4(Decimal(str(parameter_competitiveness.get("overall_parameter_competitiveness_score") or 0)))
    return _strength_score(param_strength)


def _parameter_competitiveness_reason(has_claim: bool, param_strength: Decimal, parameter_competitiveness: Mapping[str, Any] | None) -> str:
    if parameter_competitiveness:
        explanation = str(parameter_competitiveness.get("explanation_cn") or "").strip()
        if explanation:
            return explanation
    if not has_claim:
        return "本品没有形成该标准卖点，参数证据不成立。"
    if param_strength >= Decimal("0.8000"):
        return "卖点有明确参数或事实卖点支撑。"
    if param_strength >= Decimal("0.5000"):
        return "卖点存在部分参数支撑，需结合评论和市场表现判断。"
    return "卖点文本存在，但参数支撑偏弱。"


def _comment_reason(comment_strength: Decimal, has_negative: bool) -> str:
    if has_negative:
        return "评论存在负向或矛盾反馈，用户支付价值降级。"
    if comment_strength >= Decimal("0.8000"):
        return "评论中能观察到对该卖点的正向感知。"
    if comment_strength >= Decimal("0.5000"):
        return "评论感知中等，能作为辅助证据但不能单独证明溢价。"
    return "评论验证不足，更多属于厂家表达或参数能力。"


def _competitor_difference_score(has_claim: bool, coverage_rate: Decimal, price_delta: Decimal, sales_delta: Decimal, amount_delta: Decimal) -> Decimal:
    if not has_claim:
        if price_delta > 0 or sales_delta > 0 or amount_delta > 0:
            return Decimal("78")
        return Decimal("35")
    if coverage_rate >= Decimal("0.7500"):
        return Decimal("35")
    if coverage_rate >= Decimal("0.5500"):
        return Decimal("55")
    if coverage_rate >= Decimal("0.3000"):
        return Decimal("72")
    return Decimal("85")


def _competitor_difference_reason(has_claim: bool, coverage_rate: Decimal, pool: ClaimPool) -> str:
    coverage_text = f"{float(_q4(coverage_rate * Decimal('100'))):.0f}%"
    if not has_claim:
        return f"本品缺失该卖点；可比池中有 {len(pool.with_claim_skus)} 个 SKU 具备该卖点，形成潜在拦截。"
    if coverage_rate >= Decimal("0.7500"):
        return f"可比池中约 {coverage_text} 的 SKU 都具备该卖点，更接近入围门槛。"
    return f"可比池中约 {coverage_text} 的 SKU 具备该卖点，具备一定差异化观察价值。"


def _market_validation_score(
    pool: ClaimPool,
    price_delta: Decimal,
    sales_delta: Decimal,
    amount_delta: Decimal,
    market_position: Mapping[str, Any],
    market_acceptance: Mapping[str, Any] | None = None,
) -> Decimal:
    if pool.sample_status == "insufficient":
        return Decimal("25")
    if pool.sample_status == "weak":
        return Decimal("45")
    if market_acceptance:
        return _q4(Decimal(str(market_acceptance.get("market_validation_coefficient") or 0)) * Decimal("100"))
    if price_delta > 0 and (sales_delta > 0 or amount_delta > 0):
        return Decimal("90")
    if sales_delta > 0 or amount_delta > 0:
        return Decimal("76")
    if price_delta > 0 and market_position["type"] == "price_pressure":
        return Decimal("45")
    if price_delta > 0:
        return Decimal("60")
    return Decimal("35")


def _market_validation_reason(pool: ClaimPool, price_delta: Decimal, sales_delta: Decimal, amount_delta: Decimal, market_position: Mapping[str, Any], market_acceptance: Mapping[str, Any] | None = None) -> str:
    if pool.sample_status != "sufficient":
        return "可比池样本不足，保留观察但不能强判卖点支付价值。"
    if market_acceptance:
        return (
            f"本品市场位置为{market_position['summary_cn']}；市场承接系数约 "
            f"{float(Decimal(str(market_acceptance.get('market_validation_coefficient') or 0))):.2f}，"
            "由销量承接、销额承接、评论验证和样本可靠性共同计算。"
        )
    return (
        f"可比池有卖点组相对对照组价格差异约 {_fmt_money(price_delta)} 元，"
        f"周均销量差异约 {_fmt_num(sales_delta)} 台；本品市场位置为{market_position['summary_cn']}。"
    )


def _scorecard_downgrade_reasons(
    *,
    pool: ClaimPool,
    role: str,
    has_claim: bool,
    has_negative: bool,
    coverage_rate: Decimal,
    param_strength: Decimal,
    comment_strength: Decimal,
    parameter_competitiveness: Mapping[str, Any] | None = None,
) -> list[str]:
    reasons: list[str] = []
    if pool.sample_status != "sufficient":
        reasons.append("可比池样本不足，不能稳定量化。")
    if not has_claim:
        reasons.append("本品缺失该卖点，只能作为竞品拦截或机会判断。")
    if has_negative or role == M12C_ROLE_DRAG:
        reasons.append("评论或参数存在负向/矛盾反馈，支付价值降级。")
    if coverage_rate >= Decimal("0.7500") and has_claim:
        reasons.append("可比池普遍具备，更接近基础门槛。")
    if parameter_competitiveness:
        level = str(parameter_competitiveness.get("overall_parameter_competitiveness_level") or "")
        downgrade = str(parameter_competitiveness.get("downgrade_reason_cn") or "").strip()
        if downgrade:
            reasons.append(downgrade)
        elif level == M12C_PARAM_LEVEL_PARITY and has_claim:
            reasons.append("支撑参数在同战场内接近基础门槛，不单独支撑高溢价。")
        elif level == M12C_PARAM_LEVEL_SPARSE:
            reasons.append("支撑参数样本不足，不能强判为高溢价。")
        elif level == M12C_PARAM_LEVEL_WEAK and has_claim:
            reasons.append("支撑参数竞争力不足。")
    if param_strength < Decimal("0.5000") and has_claim:
        reasons.append("参数支撑不足。")
    if comment_strength < Decimal("0.5000") and has_claim:
        reasons.append("评论感知不足。")
    return reasons


def _market_position_signal(
    *,
    market_price: Decimal,
    market_sales: Decimal,
    baseline_price: Decimal,
    baseline_sales: Decimal,
    market_amount: Decimal | None = None,
    baseline_amount: Decimal | None = None,
) -> dict[str, Any]:
    price_gap = _q4(market_price - baseline_price)
    sales_gap = _q6(market_sales - baseline_sales)
    amount_gap = _q6((market_amount or Decimal("0")) - (baseline_amount or Decimal("0")))
    sales_ratio = _ratio_or_zero(market_sales, baseline_sales)
    amount_ratio = _ratio_or_zero(market_amount or Decimal("0"), baseline_amount or Decimal("0"))
    price_neutral_threshold = max(abs(baseline_price) * Decimal("0.03"), Decimal("50"))
    sales_not_weak = sales_ratio >= M12C_PREMIUM_MIN_SALES_RATIO
    revenue_not_weak = amount_ratio >= M12C_PREMIUM_MIN_REVENUE_RATIO and sales_ratio >= M12C_PREMIUM_REVENUE_BACKUP_MIN_SALES_RATIO
    if price_gap > price_neutral_threshold and (sales_not_weak or revenue_not_weak):
        return {"type": "premium_accepted", "summary_cn": "价格较高且销量不弱，存在溢价承接", "amount_gap": float(amount_gap)}
    if abs(price_gap) <= price_neutral_threshold and (sales_gap > 0 or amount_gap > 0):
        return {"type": "share_conversion", "summary_cn": "价格持平但销量更强，偏份额转化"}
    if price_gap < -price_neutral_threshold and (sales_gap > 0 or amount_gap > 0):
        return {"type": "customer_value_gain", "summary_cn": "价格更低且销量更强，偏客户获得价值"}
    if price_gap > price_neutral_threshold and sales_gap < 0:
        return {"type": "price_pressure", "summary_cn": "价格较高但销量偏弱，存在价格压力"}
    return {"type": "payment_unverified", "summary_cn": "价格和销量暂未验证支付价值"}


def _business_claim_type(
    role: str,
    metric: Mapping[str, Any],
    scorecard: Mapping[str, Any],
    market_position: Mapping[str, Any] | None = None,
    parameter_competitiveness: Mapping[str, Any] | None = None,
) -> str:
    price_delta = _q4(metric.get("price_premium_abs") or metric.get("_pool_claim_price_delta_abs"))
    total_score = Decimal(str(scorecard.get("total_score") or 0))
    market_type = str((market_position or {}).get("type") or "")
    param_level = str((parameter_competitiveness or {}).get("overall_parameter_competitiveness_level") or "")
    param_sparse = bool((parameter_competitiveness or {}).get("sparse_sample_flag")) or param_level == M12C_PARAM_LEVEL_SPARSE
    wtp_input_guard = str((parameter_competitiveness or {}).get("wtp_input_guard") or "")
    if wtp_input_guard == M04C_WTP_GUARD_BLOCKED_GENERIC and role != M12C_ROLE_DRAG:
        return M12C_CLAIM_TYPE_THRESHOLD
    if wtp_input_guard in {M04C_WTP_GUARD_BLOCKED_NO_PARAM, M04C_WTP_GUARD_NOT_SCOPE} and role != M12C_ROLE_DRAG:
        return M12C_CLAIM_TYPE_BRAND
    if role == M12C_ROLE_UNIQUE:
        return M12C_CLAIM_TYPE_UNIQUE
    if role == M12C_ROLE_PREMIUM and parameter_competitiveness is not None:
        if param_sparse:
            return M12C_CLAIM_TYPE_SAMPLE
        if param_level not in {M12C_PARAM_LEVEL_LEADING, M12C_PARAM_LEVEL_STRONG}:
            return M12C_CLAIM_TYPE_PENDING
    if role == M12C_ROLE_SAMPLE:
        return M12C_CLAIM_TYPE_SAMPLE
    if role == M12C_ROLE_BASIC:
        return M12C_CLAIM_TYPE_THRESHOLD
    if role == M12C_ROLE_DRAG:
        return M12C_CLAIM_TYPE_PRICE_PRESSURE
    if role in OPPORTUNITY_ROLES:
        return M12C_CLAIM_TYPE_INTERCEPT
    if role in {M12C_ROLE_WEAK_USER, M12C_ROLE_USER_NEED}:
        return M12C_CLAIM_TYPE_PENDING
    if role == M12C_ROLE_BRAND:
        return M12C_CLAIM_TYPE_BRAND
    if market_type == "price_pressure" and role in {M12C_ROLE_PREMIUM, M12C_ROLE_SALES, M12C_ROLE_VALUE_BUNDLE}:
        return M12C_CLAIM_TYPE_PRICE_PRESSURE
    if role == M12C_ROLE_PREMIUM and market_type == "premium_accepted" and price_delta > 0 and total_score >= Decimal("65"):
        return M12C_CLAIM_TYPE_PREMIUM
    if role == M12C_ROLE_SALES and market_type == "share_conversion":
        return M12C_CLAIM_TYPE_SHARE
    if role == M12C_ROLE_VALUE_BUNDLE and market_type == "customer_value_gain":
        return M12C_CLAIM_TYPE_CUSTOMER_VALUE
    if role in {M12C_ROLE_PREMIUM, M12C_ROLE_SALES, M12C_ROLE_VALUE_BUNDLE}:
        return M12C_CLAIM_TYPE_PENDING
    return M12C_CLAIM_TYPE_BRAND


def _business_claim_type_label(claim_type: str) -> str:
    return {
        M12C_CLAIM_TYPE_PREMIUM: "高溢价卖点",
        M12C_CLAIM_TYPE_SHARE: "份额转化卖点",
        M12C_CLAIM_TYPE_CUSTOMER_VALUE: "客户获得价值卖点",
        M12C_CLAIM_TYPE_THRESHOLD: "门槛卖点",
        M12C_CLAIM_TYPE_PENDING: "待激活卖点",
        M12C_CLAIM_TYPE_BRAND: "厂家主张卖点",
        M12C_CLAIM_TYPE_INTERCEPT: "竞品拦截卖点",
        M12C_CLAIM_TYPE_PRICE_PRESSURE: "价格压力卖点",
        M12C_CLAIM_TYPE_SAMPLE: "样本不足待复核",
        M12C_CLAIM_TYPE_UNIQUE: "人无我有型支付价值卖点",
    }.get(claim_type, "未分类卖点")


def _business_claim_type_meaning_cn(claim_type: str) -> str:
    return {
        M12C_CLAIM_TYPE_PREMIUM: "用户愿意为该卖点支付更高价格，并且参数、评论和市场验证共同成立。",
        M12C_CLAIM_TYPE_SHARE: "该卖点不一定抬高价格，但能解释同价或相近价格下的销量/份额优势。",
        M12C_CLAIM_TYPE_CUSTOMER_VALUE: "该卖点让用户觉得产品更值，主要体现为价格压力更小或销量承接更强。",
        M12C_CLAIM_TYPE_THRESHOLD: "该卖点是进入购买清单的基础要求，有了不加价，缺了会掉队。",
        M12C_CLAIM_TYPE_PENDING: "本品有参数或厂家表达，但用户评论或市场验证还不足，需要继续激活。",
        M12C_CLAIM_TYPE_BRAND: "当前主要是厂家主张，尚未形成稳定用户支付价值。",
        M12C_CLAIM_TYPE_INTERCEPT: "竞品具备并形成市场验证，本品缺失或表达弱，会影响购买转化。",
        M12C_CLAIM_TYPE_PRICE_PRESSURE: "卖点表达、参数或用户反馈没有支撑当前价格，可能削弱成交理由。",
        M12C_CLAIM_TYPE_SAMPLE: "样本或对照组不足，只能作为观察线索。",
        M12C_CLAIM_TYPE_UNIQUE: "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿，但当前缺少稳定对照样本，不能量化金额。",
    }.get(claim_type, "当前分类尚未定义。")


def _strength_score(value: Decimal) -> Decimal:
    return _q4(_clamp(value, Decimal("0"), Decimal("1")) * Decimal("100"))


def _comment_score(comment_strength: Decimal, has_negative: bool) -> Decimal:
    raw = _strength_score(comment_strength)
    if has_negative:
        return min(raw, Decimal("35"))
    return raw


def _evidence_ref(context_type: str, context_code: str) -> dict[str, Any]:
    module = {"battlefield": "M11C", "user_task": "M09C", "target_group": "M10C"}.get(context_type, "M07")
    return {"source_module": module, "context_type": context_type, "context_code": context_code}


def _sample_status(pool_count: int, with_count: int, without_count: int) -> tuple[str, list[str]]:
    flags: list[str] = []
    if pool_count < MIN_WEAK_POOL_SKU_COUNT or with_count == 0 or without_count == 0:
        flags.append("insufficient_comparison_group")
        return "insufficient", flags
    if pool_count < MIN_POOL_SKU_COUNT or with_count < MIN_GROUP_SKU_COUNT or without_count < MIN_GROUP_SKU_COUNT:
        flags.append("small_comparable_pool")
        return "weak", flags
    return "sufficient", flags


def _market_state(row: entities.Core3SkuMarketProfile) -> MarketState:
    active_weeks = int(row.active_week_count or 0)
    sales_volume = _q4(row.sales_volume_total)
    sales_amount = _q4(row.sales_amount_total)
    screen_size = _decimal_or_none(row.screen_size_inch)
    exact_size_tier = _exact_size_tier(screen_size, row.size_segment or row.screen_size_class)
    five_tier = _five_size_tier(screen_size, row.size_segment or row.screen_size_class)
    return MarketState(
        sku_code=row.sku_code,
        brand_name=row.brand_name or row.brand,
        model_name=row.model_name,
        size_tier=five_tier,
        exact_size_tier=exact_size_tier,
        price_band=row.price_band_size or row.price_band_category or "unknown",
        price=_q4(row.price_wavg or row.price_median or Decimal("0")),
        sales_volume_total=sales_volume,
        sales_amount_total=sales_amount,
        avg_weekly_sales_volume=_safe_avg(sales_volume, active_weeks),
        avg_weekly_sales_amount=_safe_avg(sales_amount, active_weeks),
        active_week_count=active_weeks,
        window_start_week=row.period_start_week_index,
        window_end_week=row.period_end_week_index,
    )


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _exact_size_tier(screen_size: Decimal | None, fallback: str | None) -> str:
    if screen_size and screen_size > 0:
        return f"size_{int(screen_size.to_integral_value(rounding=ROUND_HALF_UP))}"
    text = str(fallback or "").strip()
    if text and text not in {"unknown", "UNKNOWN"}:
        digits = "".join(ch for ch in text if ch.isdigit())
        if digits:
            return f"size_{digits}"
    return "size_unknown"


def _five_size_tier(screen_size: Decimal | None, fallback: str | None) -> str:
    text = str(fallback or "").strip()
    if text in {"small_32_45", "medium_46_59", "large_60_69", "xlarge_70_85", "giant_98_plus"}:
        return text
    size = screen_size
    if size is None:
        digits = "".join(ch for ch in text if ch.isdigit())
        size = Decimal(digits) if digits else None
    if size is None or size <= 0:
        return "unknown"
    if size <= Decimal("45"):
        return "small_32_45"
    if size <= Decimal("59"):
        return "medium_46_59"
    if size <= Decimal("69"):
        return "large_60_69"
    if size <= Decimal("85"):
        return "xlarge_70_85"
    return "giant_98_plus"


def _adjacent_price_bands(price_band: str) -> list[str]:
    order = ["low", "mid_low", "mid", "mid_high", "high"]
    if price_band not in order:
        return [price_band]
    idx = order.index(price_band)
    result = [price_band]
    if idx > 0:
        result.append(order[idx - 1])
    if idx < len(order) - 1:
        result.append(order[idx + 1])
    return result


def _price_scope_label(price_band: str, price_scope: Sequence[str]) -> str:
    unique = [item for item in price_scope if item]
    if len(unique) <= 1:
        return unique[0] if unique else price_band
    return f"{price_band}_with_adjacent"


def _empty_comment(sku_code: str) -> CommentState:
    return CommentState(sku_code=sku_code, supported_claim_codes=(), contradicted_claim_codes=(), positive_sentence_count=0, negative_sentence_count=0, confidence=Decimal("0.0000"))


def _claim_evidence_strength(claim: ClaimState | None) -> Decimal:
    if claim is None:
        return Decimal("0.0000")
    return _q4(claim.param_support_strength * Decimal("0.60") + claim.match_score * Decimal("0.25") + claim.confidence * Decimal("0.15"))


def _positive_weight(role: str, metric: Mapping[str, Any], claim_strength: Decimal, semantic_strength: Decimal, comment_strength: Decimal, scorecard: Mapping[str, Any] | None = None) -> Decimal:
    if role not in POSITIVE_ROLES:
        return Decimal("0.000000")
    if scorecard:
        return _q6(max(Decimal("0"), Decimal(str(scorecard.get("total_score") or 0))))
    effect = max(Decimal("0"), _q4(metric["claim_value_effect_score"]))
    return _q6(effect * claim_strength * max(semantic_strength, Decimal("0.2000")) * max(comment_strength, Decimal("0.3000")))


def _metric_baseline(metric: Mapping[str, Any], without_key: str, with_key: str) -> Decimal:
    without_value = metric.get(without_key)
    if without_value is not None:
        return _q6(without_value)
    return _q6(metric.get(with_key) or Decimal("0"))


def _target_baseline(pool: ClaimPool, markets: Mapping[str, MarketState], target_sku: str) -> dict[str, Any]:
    comparison_skus = [sku for sku in pool.sku_codes if sku != target_sku and sku in markets]
    if not comparison_skus:
        comparison_skus = [sku for sku in pool.sku_codes if sku in markets]
    target_market = markets.get(target_sku)
    baseline_skus = _direct_baseline_skus(pool, markets, target_market, comparison_skus)
    price_values = [markets[sku].price for sku in baseline_skus if sku in markets and markets[sku].price > 0]
    sales_values = [markets[sku].avg_weekly_sales_volume for sku in baseline_skus if sku in markets]
    amount_values = [markets[sku].avg_weekly_sales_amount for sku in baseline_skus if sku in markets]
    baseline_price = _median(price_values) or Decimal("0")
    baseline_sales = _median(sales_values) or Decimal("0")
    baseline_amount = _median(amount_values) or Decimal("0")
    method = "nearest_price_median_excluding_target" if set(baseline_skus) != set(comparison_skus) else "median_excluding_target"
    return {
        "baseline_price": _q4(baseline_price),
        "baseline_weekly_sales": _q6(baseline_sales),
        "baseline_weekly_amount": _q6(baseline_amount),
        "baseline_price_method": method,
        "comparison_sku_codes": comparison_skus,
        "baseline_sku_codes": baseline_skus,
        "baseline_explanation_cn": (
            "基准价按同战场可比池中排除目标 SKU 后、价格最接近的一组直接可比 SKU 的成交均价中位价计算；"
            f"本次可比 SKU {len(comparison_skus)} 个，直接基准 SKU {len(baseline_skus)} 个，放宽层级 {pool.pool_relax_level}。"
        ),
    }


def _direct_baseline_skus(
    pool: ClaimPool,
    markets: Mapping[str, MarketState],
    target_market: MarketState | None,
    comparison_skus: Sequence[str],
) -> list[str]:
    candidates = [sku for sku in comparison_skus if sku in markets and markets[sku].price > 0]
    if not candidates or target_market is None or target_market.price <= 0:
        return list(candidates)
    same_price_band = [sku for sku in candidates if markets[sku].price_band == target_market.price_band]
    if len(same_price_band) >= 3:
        candidates = same_price_band
    same_exact_size = [sku for sku in candidates if markets[sku].exact_size_tier == target_market.exact_size_tier]
    if len(same_exact_size) >= 3:
        candidates = same_exact_size
    ranked = sorted(
        candidates,
        key=lambda sku: (
            abs(_q4(markets[sku].price - target_market.price)),
            markets[sku].price,
            sku,
        ),
    )
    if len(ranked) >= 3:
        return list(ranked[:3])
    return list(ranked)


def _weighted_median(value_weight_pairs: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    pairs = [(value, weight) for value, weight in value_weight_pairs if value is not None and _q6(value) > 0 and _q6(weight) > 0]
    if not pairs:
        return Decimal("0")
    pairs.sort(key=lambda item: item[0])
    total_weight = sum((weight for _, weight in pairs), Decimal("0"))
    midpoint = total_weight / Decimal("2")
    cumulative = Decimal("0")
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= midpoint:
            return value
    return pairs[-1][0]


def _market_acceptance_score(
    *,
    market: MarketState,
    baseline_price: Decimal,
    baseline_sales: Decimal,
    baseline_amount: Decimal,
    pool: ClaimPool,
    comment: CommentState,
) -> dict[str, Any]:
    sales_ratio = _ratio_or_zero(market.avg_weekly_sales_volume, baseline_sales)
    amount_ratio = _ratio_or_zero(market.avg_weekly_sales_amount, baseline_amount)
    sales_score = _acceptance_bucket(sales_ratio)
    amount_score = _acceptance_bucket(amount_ratio)
    comment_score = _battlefield_comment_validation_score(comment)
    sample_score = _sample_reliability_score(pool)
    coefficient = _q4(sales_score * Decimal("0.45") + amount_score * Decimal("0.25") + comment_score * Decimal("0.20") + sample_score * Decimal("0.10"))
    return {
        "sales_acceptance_score": float(sales_score),
        "amount_acceptance_score": float(amount_score),
        "comment_validation_score": float(comment_score),
        "sample_reliability_score": float(sample_score),
        "market_validation_coefficient": float(coefficient),
        "sales_ratio": float(_q4(sales_ratio)),
        "amount_ratio": float(_q4(amount_ratio)),
        "sales_acceptance_reason_cn": _acceptance_reason_cn("销量", sales_ratio, sales_score),
        "amount_acceptance_reason_cn": _acceptance_reason_cn("销额", amount_ratio, amount_score),
        "comment_validation_reason_cn": _comment_validation_reason_cn(comment, comment_score),
        "sample_reliability_reason_cn": f"可比池放宽层级 {pool.pool_relax_level}，样本状态 {pool.sample_status}。",
    }


def _ratio_or_zero(value: Decimal, baseline: Decimal) -> Decimal:
    if _q6(baseline) == 0:
        return Decimal("0")
    return _q6(value / baseline)


def _acceptance_bucket(ratio: Decimal) -> Decimal:
    if ratio >= Decimal("1.20"):
        return Decimal("1.0000")
    if ratio >= Decimal("0.90"):
        return Decimal("0.8000")
    if ratio >= Decimal("0.70"):
        return Decimal("0.6000")
    return Decimal("0.3000")


def _battlefield_comment_validation_score(comment: CommentState) -> Decimal:
    positive = comment.positive_sentence_count
    negative = comment.negative_sentence_count
    if positive >= 5 and positive >= negative * 2:
        return Decimal("1.0000")
    if positive >= 2 and positive >= negative:
        return Decimal("0.7500")
    if positive > 0:
        return Decimal("0.5000")
    return Decimal("0.2000")


def _sample_reliability_score(pool: ClaimPool) -> Decimal:
    if pool.sample_status == "sufficient" and pool.pool_relax_level in {"L0", "L1"}:
        return Decimal("1.0000")
    if pool.pool_relax_level == "L2" and pool.sample_status == "sufficient":
        return Decimal("0.8500")
    if pool.pool_relax_level == "L3" and pool.sample_status in {"sufficient", "weak"}:
        return Decimal("0.7000")
    if pool.sample_status == "weak":
        return Decimal("0.4000")
    return Decimal("0.2000")


def _acceptance_reason_cn(label: str, ratio: Decimal, score: Decimal) -> str:
    return f"本品{label}约为可比基准的 {float(_q4(ratio)):.2f} 倍，对应承接分 {float(score):.2f}。"


def _comment_validation_reason_cn(comment: CommentState, score: Decimal) -> str:
    return f"评论正向句 {comment.positive_sentence_count} 条、负向句 {comment.negative_sentence_count} 条，对应评论验证分 {float(score):.2f}。"


def _effective_price_space(market: MarketState, baseline_price: Decimal, market_position: Mapping[str, Any], market_acceptance: Mapping[str, Any]) -> Decimal:
    if market_position.get("type") != "premium_accepted":
        return Decimal("0.0000")
    raw_gap = max(Decimal("0.0000"), _q4(market.price - baseline_price))
    coefficient = Decimal(str(market_acceptance.get("market_validation_coefficient") or 0))
    return _q4(raw_gap * coefficient)


def _claim_type_coefficient(claim_type: str) -> Decimal:
    if claim_type == M12C_CLAIM_TYPE_PREMIUM:
        return Decimal("1.0000")
    if claim_type == M12C_CLAIM_TYPE_SHARE:
        return Decimal("0.8000")
    if claim_type == M12C_CLAIM_TYPE_CUSTOMER_VALUE:
        return Decimal("0.7000")
    if claim_type == M12C_CLAIM_TYPE_PENDING:
        return Decimal("0.5000")
    if claim_type == M12C_CLAIM_TYPE_THRESHOLD:
        return Decimal("0.3000")
    return Decimal("0.0000")


def _claim_brief(row: Mapping[str, Any]) -> dict[str, Any]:
    supporting = row.get("supporting_dimensions_json") if isinstance(row.get("supporting_dimensions_json"), dict) else {}
    business_claim_type = str(supporting.get("business_claim_type") or "")
    business_claim_type_cn = str(supporting.get("business_claim_type_cn") or "")
    scorecard = supporting.get("scorecard") if isinstance(supporting.get("scorecard"), dict) else {}
    return {
        "sku_code": row.get("sku_code"),
        "brand_name": row.get("brand_name"),
        "model_name": row.get("model_name"),
        "claim_code": row.get("claim_code"),
        "claim_name": row.get("claim_name"),
        "claim_value_role": row.get("claim_value_role"),
        "business_claim_type": business_claim_type,
        "business_claim_type_cn": business_claim_type_cn,
        "business_claim_type_definition_cn": supporting.get("business_claim_type_definition_cn"),
        "claim_value_score": supporting.get("claim_value_score") or scorecard.get("total_score"),
        "business_value_label": row.get("_business_value_label") or _business_value_label(str(row.get("claim_value_role") or ""), row),
        "business_value_meaning_cn": row.get("_business_value_meaning_cn") or _business_value_meaning_cn(str(row.get("claim_value_role") or ""), row),
        "pool_claim_price_delta_abs": float(_q4(row.get("_pool_claim_price_delta_abs"))),
        "pool_claim_weekly_sales_delta_abs": float(_q6(row.get("_pool_claim_weekly_sales_delta_abs"))),
        "pool_claim_weekly_sales_amount_delta_abs": float(_q6(row.get("_pool_claim_weekly_sales_amount_delta_abs"))),
        "sku_excess_price_explained_abs": float(_q4(row.get("estimated_price_premium_abs"))),
        "sku_excess_weekly_sales_explained_abs": float(_q6(row.get("estimated_weekly_sales_lift_abs"))),
        "estimated_price_premium_abs": float(_q4(row.get("estimated_price_premium_abs"))),
        "estimated_weekly_sales_lift_abs": float(_q6(row.get("estimated_weekly_sales_lift_abs"))),
        "estimated_weekly_sales_amount_lift_abs": float(_q6(row.get("estimated_weekly_sales_amount_lift_abs"))),
        "contribution_share_in_sku": float(_q6(row.get("contribution_share_in_sku"))),
        "attribution_confidence": float(_q4(row.get("attribution_confidence"))),
        "scorecard": scorecard,
        "market_position": {
            "type": supporting.get("market_position_type"),
            "summary_cn": supporting.get("market_position_cn"),
        },
        "reason_cn": row.get("reason_cn", ""),
    }


def _business_value_label(role: str, metric: Mapping[str, Any]) -> str:
    price_delta = _q4(metric.get("price_premium_abs") or metric.get("_pool_claim_price_delta_abs"))
    if role == M12C_ROLE_PREMIUM:
        return "强溢价卖点" if price_delta > 0 else "组合型增值卖点"
    if role == M12C_ROLE_SALES:
        return "强销量卖点"
    if role == M12C_ROLE_BASIC:
        return "基础门槛卖点"
    if role == M12C_ROLE_VALUE_BUNDLE:
        return "组合型增值卖点"
    if role == M12C_ROLE_UNIQUE:
        return "人无我有型支付价值卖点"
    if role == M12C_ROLE_WEAK_USER:
        return "用户感知不足卖点"
    if role == M12C_ROLE_HIGH_PRICE_INTERCEPT:
        return "高价竞品拦截卖点"
    if role == M12C_ROLE_PRICE_UP:
        return "价格上探机会卖点"
    if role == M12C_ROLE_DRAG:
        return "拖后腿卖点"
    if role == M12C_ROLE_OPPORTUNITY:
        return "机会缺口"
    if role == M12C_ROLE_BRAND:
        return "厂家主张卖点"
    if role == M12C_ROLE_USER_NEED:
        return "用户验证需求"
    return "样本不足待复核"


def _business_value_meaning_cn(role: str, metric: Mapping[str, Any]) -> str:
    price_delta = _q4(metric.get("price_premium_abs") or metric.get("_pool_claim_price_delta_abs"))
    if role == M12C_ROLE_PREMIUM and price_delta > 0:
        return "同尺寸、同价格带、同语义市场中，有该卖点且证据成立的一组 SKU 价格更高。"
    if role == M12C_ROLE_SALES:
        return "价格不一定更高，但更能解释同池周均销量或销额优势。"
    if role == M12C_ROLE_BASIC:
        return "同池普遍具备，有了不加价，缺了会掉队。"
    if role == M12C_ROLE_VALUE_BUNDLE or (role == M12C_ROLE_PREMIUM and price_delta <= 0):
        return "单点不一定独立溢价，但与一组高价值卖点组合后参与高端价值解释。"
    if role == M12C_ROLE_UNIQUE:
        return "本品具备同池稀缺卖点或关键参数优势，可能提高用户最高支付意愿；当前对照样本不足，只输出潜力和证据链，不输出金额。"
    if role == M12C_ROLE_WEAK_USER:
        return "参数或卖点存在，但评论验证弱、负向明显，或弱于高价竞品。"
    if role == M12C_ROLE_HIGH_PRICE_INTERCEPT:
        return "同池高价竞品具备并能成交，本品缺失、表达弱或评论弱。"
    if role == M12C_ROLE_PRICE_UP:
        return "高价 SKU 反复具备且有市场价值，本品补强后可能提升上探空间。"
    if role == M12C_ROLE_DRAG:
        return "厂家主张、参数或评论之间不一致，削弱关键战场、任务或客群。"
    if role == M12C_ROLE_OPPORTUNITY:
        return "同池强竞品或高价值 SKU 具备，本品缺失或表达弱。"
    if role == M12C_ROLE_BRAND:
        return "卖点文本存在，但参数、评论或市场验证不足。"
    if role == M12C_ROLE_USER_NEED:
        return "评论中存在需求，但本品卖点或参数支撑不足。"
    return "可比池、对照组或评论样本不足，不能稳定判断。"


def _metric_summary_cn(pool: ClaimPool, metric: Mapping[str, Any]) -> str:
    return (
        f"{pool.claim_name} 在 {pool.context_name} / {pool.size_tier} / {pool.price_band_group} 可比池中，"
        f"{pool.comparison_group_label_cn} {len(pool.with_claim_skus)} 个 SKU，"
        f"{pool.control_group_label_cn} {len(pool.without_claim_skus)} 个 SKU；"
        f"可比池组间价格差异约 {_fmt_money(metric['price_premium_abs'])} 元，"
        f"组间周均销量差异约 {_fmt_num(metric['weekly_sales_lift_abs'])} 台。"
    )


def _quant_reason_cn(pool: ClaimPool, role: str, metric: Mapping[str, Any]) -> str:
    role_cn = {
        M12C_ROLE_PREMIUM: "强溢价卖点",
        M12C_ROLE_SALES: "强销量卖点",
        M12C_ROLE_BASIC: "基础门槛卖点",
        M12C_ROLE_VALUE_BUNDLE: "组合型增值卖点",
        M12C_ROLE_UNIQUE: "人无我有型支付价值卖点",
        M12C_ROLE_WEAK_USER: "用户感知不足卖点",
        M12C_ROLE_HIGH_PRICE_INTERCEPT: "高价竞品拦截卖点",
        M12C_ROLE_PRICE_UP: "价格上探机会卖点",
        M12C_ROLE_BRAND: "厂家主张卖点",
        M12C_ROLE_USER_NEED: "用户验证需求",
        M12C_ROLE_DRAG: "拖后腿卖点",
        M12C_ROLE_OPPORTUNITY: "机会缺口",
        M12C_ROLE_SAMPLE: "样本不足",
    }.get(role, role)
    if role == M12C_ROLE_UNIQUE:
        return (
            f"{pool.claim_name} 被判为{role_cn}；同战场可比池缺少稳定对照或目标 SKU 是有卖点组孤例，"
            "当前只说明该卖点可能提高用户最高支付意愿，不使用组间价差量化金额。"
        )
    return (
        f"{pool.claim_name} 被判为{role_cn}；所在可比池{pool.comparison_group_label_cn}相对{pool.control_group_label_cn}"
        f"价格差异约 {_fmt_money(metric['price_premium_abs'])} 元，"
        f"周均销量差异约 {_fmt_num(metric['weekly_sales_lift_abs'])} 台。该数值是组间可观测差异，不是单一卖点因果贡献。"
    )


def _attribution_summary_cn(market: MarketState, positive: Sequence[Mapping[str, Any]], context_type: str, context_name: str) -> str:
    if not positive:
        return f"{market.brand_name or ''} {market.model_name or market.sku_code} 在 {context_name} 中没有形成高置信正向卖点贡献。".strip()
    names = "、".join(str(row.get("claim_name") or row.get("claim_code")) for row in positive[:3])
    return f"{market.brand_name or ''} {market.model_name or market.sku_code} 在 {context_name} 中的超额表现主要由 {names} 提供可观测解释。".strip()


def _m11d_population(analysis_population: str) -> str:
    if analysis_population == ANALYSIS_POPULATION_READY_WITH_COMMENT:
        return "fact_complete_with_comment"
    if analysis_population == ANALYSIS_POPULATION_READY:
        return "all_semantic_profiles"
    return analysis_population


def _fallback_context_weight(relation_role: str) -> Decimal:
    if relation_role == "primary":
        return Decimal("1.000000")
    if relation_role == "secondary":
        return Decimal("0.700000")
    return Decimal("0.000000")


def _assign(record: Any, payload: Mapping[str, Any]) -> None:
    for key, value in payload.items():
        setattr(record, key, value)


def _record_id(prefix: str, *parts: object) -> str:
    return stable_hash([prefix, *parts], version="m12c-id-v1")[:120]


def _median(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return _q6(Decimal(str(median([float(value) for value in values]))))


def _none_delta(left: Decimal | None, right: Decimal | None, *, scale: str) -> Decimal:
    if left is None or right is None:
        return Decimal("0")
    return _q4(left - right) if scale == "q4" else _q6(left - right)


def _rate(delta: Decimal, base: Decimal | None) -> Decimal:
    if base is None or _q6(base) == 0:
        return Decimal("0")
    return _q6(delta / _q6(base))


def _safe_avg(total: Decimal, active_weeks: int) -> Decimal:
    if active_weeks <= 0:
        return Decimal("0.000000")
    return _q6(total / Decimal(active_weeks))


def _avg(values: Iterable[Any]) -> Decimal:
    vals = [_q4(value) for value in values]
    if not vals:
        return Decimal("0.0000")
    return _q4(sum(vals, Decimal("0")) / Decimal(len(vals)))


def _q4(value: Any) -> Decimal:
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _q6(value: Any) -> Decimal:
    if value is None:
        value = Decimal("0")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return min(high, max(low, value))


def _min_week(values: Iterable[int | None]) -> int | None:
    filtered = [value for value in values if value is not None]
    return min(filtered) if filtered else None


def _max_week(values: Iterable[int | None]) -> int | None:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _fmt_money(value: Any) -> str:
    return f"{float(_q4(value)):,.0f}"


def _fmt_num(value: Any) -> str:
    return f"{float(_q6(value)):,.1f}"
