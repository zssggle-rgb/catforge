"""M08.4 comment-native business dimension discovery."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.models import entities
from app.services.core3_real_data.comment_native_dimension_repositories import (
    CommentNativeDimensionRepository,
    M084InputBundle,
)
from app.services.core3_real_data.comment_native_dimension_schemas import (
    M084AlignmentProposalRecord,
    M084NativeDimensionCandidateRecord,
    M084NativeSignalRecord,
    M084ReviewIssueRecord,
    M084ServiceResult,
    M084SkuSupportRecord,
)
from app.services.core3_real_data.constants import (
    CORE3_M08_4_RULE_VERSION,
    CORE3_M08_4_SEED_VERSION,
    Core3RunStatus,
)
from app.services.core3_real_data.dimension_ontology_seed_loader import M085DimensionSeed, M085DimensionSeedLoader
from app.services.core3_real_data.hash_utils import stable_hash


@dataclass(frozen=True)
class NativeSignalRule:
    code: str
    name_cn: str
    signal_family: str
    source_domain: str
    keywords: tuple[str, ...]
    eligible_dimension_types: tuple[str, ...] = ()
    product_anchor_keywords: tuple[str, ...] = ()
    service_context: bool = False
    negative_context: bool = False


@dataclass(frozen=True)
class DimensionAssemblyRule:
    dimension_type: str
    code: str
    name_cn: str
    definition_cn: str
    required_signal_codes: tuple[str, ...]
    optional_signal_codes: tuple[str, ...] = ()
    product_anchor_keywords: tuple[str, ...] = ()
    service_context: bool = False
    review_if_missing_anchor: bool = False

    @property
    def source_signal_codes(self) -> tuple[str, ...]:
        return (*self.required_signal_codes, *self.optional_signal_codes)


@dataclass(frozen=True)
class SignalHit:
    rule: NativeSignalRule
    atom: entities.Core3CommentEvidenceAtom
    strength: Decimal


@dataclass(frozen=True)
class ParamAnchorRule:
    param_codes: tuple[str, ...]
    strength: str = "strong"
    score: Decimal = Decimal("0.1800")
    min_numeric: Decimal | None = None
    value_keywords: tuple[str, ...] = ()
    invalid_raw_name_keywords: tuple[str, ...] = ()
    valid_raw_name_keywords: tuple[str, ...] = ()
    proxy_for_codes: tuple[str, ...] = ()
    max_score_cap: Decimal | None = None


@dataclass(frozen=True)
class ClaimAnchorRule:
    claim_codes: tuple[str, ...]
    strength: str = "strong"
    score: Decimal = Decimal("0.1500")
    min_score: Decimal = Decimal("0.1500")
    requires_param_support: bool = False
    support_param_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class BattlefieldAnchorSpec:
    code: str
    param_rules: tuple[ParamAnchorRule, ...] = ()
    claim_rules: tuple[ClaimAnchorRule, ...] = ()
    matrix_keywords: tuple[str, ...] = ()
    min_product_anchor_score: Decimal = Decimal("0.3000")


@dataclass(frozen=True)
class ProductAnchorEvidence:
    source_type: str
    anchor_code: str
    anchor_name_cn: str
    anchor_group: str
    raw_name: str | None = None
    raw_value: str | None = None
    normalized_value: Any | None = None
    score: Decimal = Decimal("0.0000")
    strength: str = "weak"
    confidence: Decimal = Decimal("0.0000")
    evidence_ids: tuple[str, ...] = ()
    quality_flags: tuple[str, ...] = ()
    usable_for_battlefield: bool = True


@dataclass(frozen=True)
class ProductAnchorMatch:
    sku_code: str
    score: Decimal
    param_anchor_score: Decimal
    claim_anchor_score: Decimal
    matrix_anchor_score: Decimal
    proxy_param_anchor_score: Decimal = Decimal("0.0000")
    comment_validation_score: Decimal = Decimal("0.0000")
    market_anchor_score: Decimal = Decimal("0.0000")
    overall_anchor_score: Decimal = Decimal("0.0000")
    anchor_source_status: str = "no_direct_anchor"
    param_hits: tuple[ProductAnchorEvidence, ...] = ()
    claim_hits: tuple[ProductAnchorEvidence, ...] = ()
    comment_hits: tuple[ProductAnchorEvidence, ...] = ()
    market_hits: tuple[ProductAnchorEvidence, ...] = ()
    matrix_hits: tuple[ProductAnchorEvidence, ...] = ()
    quality_flags: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "score": float(self.score),
            "param_anchor_score": float(self.param_anchor_score),
            "proxy_param_anchor_score": float(self.proxy_param_anchor_score),
            "claim_anchor_score": float(self.claim_anchor_score),
            "comment_validation_score": float(self.comment_validation_score),
            "market_anchor_score": float(self.market_anchor_score),
            "overall_anchor_score": float(self.overall_anchor_score),
            "anchor_source_status": self.anchor_source_status,
            "matrix_anchor_score": float(self.matrix_anchor_score),
            "param_hits": [_anchor_evidence_json(item) for item in self.param_hits],
            "claim_hits": [_anchor_evidence_json(item) for item in self.claim_hits],
            "comment_hits": [_anchor_evidence_json(item) for item in self.comment_hits],
            "market_hits": [_anchor_evidence_json(item) for item in self.market_hits],
            "matrix_hits": [_anchor_evidence_json(item) for item in self.matrix_hits],
            "quality_flags": list(self.quality_flags),
        }

NATIVE_SIGNAL_RULES: tuple[NativeSignalRule, ...] = (
    NativeSignalRule(
        "capability_picture_quality",
        "画质体验",
        "capability",
        "product_experience",
        ("画质", "清晰", "色彩", "亮度", "hdr", "控光", "黑位", "mini led", "oled", "qled", "显示"),
        ("native_task", "native_product_value_battlefield"),
        ("brightness", "hdr", "dimming", "mini", "oled", "qled", "picture", "color", "screen"),
    ),
    NativeSignalRule(
        "capability_audio_immersion",
        "音质与声场体验",
        "capability",
        "product_experience",
        ("音质", "音效", "杜比", "影院", "低音", "环绕", "声场", "喇叭"),
        ("native_task", "native_product_value_battlefield"),
        ("audio", "speaker", "dolby", "sound"),
    ),
    NativeSignalRule(
        "scene_game_console",
        "主机游戏场景",
        "scene",
        "product_experience",
        ("游戏", "主机", "电竞", "ps5", "xbox"),
        ("native_task", "native_target_group"),
    ),
    NativeSignalRule(
        "capability_high_refresh_low_latency",
        "高刷低延迟能力",
        "capability",
        "product_experience",
        ("高刷", "刷新率", "低延迟", "hdmi", "120hz", "144hz", "vrr", "allm"),
        ("native_product_value_battlefield", "native_task"),
        ("refresh", "hz", "hdmi", "memc", "vrr", "game", "high_refresh"),
    ),
    NativeSignalRule(
        "scene_sports_watching",
        "体育赛事观看场景",
        "scene",
        "product_experience",
        ("体育", "球赛", "足球", "篮球", "运动", "赛事", "看球"),
        ("native_task", "native_target_group"),
    ),
    NativeSignalRule(
        "capability_motion_smoothness",
        "运动流畅能力",
        "capability",
        "product_experience",
        ("拖影", "流畅", "运动补偿", "memc", "不卡顿"),
        ("native_product_value_battlefield", "native_task"),
        ("refresh", "memc", "motion", "hz"),
    ),
    NativeSignalRule(
        "scene_living_room_family",
        "客厅家庭使用场景",
        "scene",
        "product_experience",
        ("客厅", "全家", "家庭", "观影", "追剧", "看电影"),
        ("native_task", "native_target_group"),
    ),
    NativeSignalRule(
        "capability_large_screen",
        "大屏尺寸感知",
        "capability",
        "product_experience",
        ("大屏", "大尺寸", "换大", "85寸", "75寸", "尺寸"),
        ("native_task", "native_product_value_battlefield"),
        ("screen", "size", "inch"),
    ),
    NativeSignalRule(
        "person_senior",
        "长辈使用者",
        "person",
        "product_experience",
        ("老人", "长辈", "父母", "爸妈", "老年"),
        ("native_target_group", "native_task"),
    ),
    NativeSignalRule(
        "person_child",
        "儿童使用者",
        "person",
        "product_experience",
        ("孩子", "儿童", "小孩", "学习", "家长"),
        ("native_target_group", "native_task"),
    ),
    NativeSignalRule(
        "capability_smart_easy_use",
        "智能交互易用能力",
        "capability",
        "product_experience",
        ("系统", "智能", "语音", "投屏", "操作", "流畅", "不卡", "开机", "遥控"),
        ("native_product_value_battlefield", "native_task"),
        ("system", "voice", "ram", "storage", "chip", "wifi"),
    ),
    NativeSignalRule(
        "capability_eye_care",
        "护眼舒适能力",
        "capability",
        "product_experience",
        ("护眼", "防蓝光", "低蓝光", "不刺眼", "眼睛", "舒服", "无频闪"),
        ("native_product_value_battlefield", "native_task"),
        ("eye", "blue", "care", "flicker", "tuv"),
    ),
    NativeSignalRule(
        "scene_new_home_decoration",
        "新家装修空间场景",
        "scene",
        "market_perception",
        ("新家", "装修", "搬家", "挂墙", "安装位置", "客厅宽", "空间", "电视柜", "背景墙"),
        ("purchase_motive", "native_task", "native_target_group"),
        ("screen", "size", "inch"),
    ),
    NativeSignalRule(
        "motive_price_value",
        "价格价值动机",
        "motive",
        "market_perception",
        ("价格", "便宜", "划算", "性价比", "预算", "优惠", "活动", "降价", "值"),
        ("purchase_motive",),
    ),
    NativeSignalRule(
        "motive_replacement_upgrade",
        "旧机换新动机",
        "motive",
        "market_perception",
        ("换新", "旧电视", "升级", "换大", "以旧换新", "上一台", "替换"),
        ("purchase_motive", "native_task", "native_target_group"),
        ("screen", "size", "inch"),
    ),
    NativeSignalRule(
        "service_fulfillment",
        "配送安装与售后履约",
        "service",
        "service_experience",
        ("安装", "配送", "师傅", "送货", "售后", "客服", "上门", "挂架", "预约", "物流"),
        ("service_context",),
        service_context=True,
    ),
    NativeSignalRule(
        "system_quality_risk",
        "系统卡顿和质量风险",
        "risk",
        "product_risk",
        ("卡顿", "死机", "闪退", "漏光", "坏点", "异响", "黑屏", "故障", "退换"),
        ("risk_context",),
        negative_context=True,
    ),
)


DIMENSION_ASSEMBLY_RULES: tuple[DimensionAssemblyRule, ...] = (
    DimensionAssemblyRule(
        "native_task",
        "living_room_big_screen_viewing",
        "客厅大屏追剧观影",
        "用户在客厅或家庭场景中，用大屏电视完成追剧、观影和全家娱乐任务。",
        ("scene_living_room_family",),
        ("capability_large_screen", "capability_picture_quality", "capability_audio_immersion"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "console_gaming_low_latency",
        "主机游戏低延迟娱乐",
        "用户连接主机或玩游戏，希望获得高刷、低延迟和流畅操作体验。",
        ("scene_game_console",),
        ("capability_high_refresh_low_latency", "capability_picture_quality"),
        ("refresh", "hz", "hdmi", "vrr", "allm", "game", "high_refresh"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "sports_smooth_watching",
        "体育赛事流畅观看",
        "用户在看球或体育赛事时，希望画面运动流畅、拖影少。",
        ("scene_sports_watching",),
        ("capability_motion_smoothness", "capability_high_refresh_low_latency"),
        ("refresh", "memc", "motion", "hz"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "senior_easy_operation",
        "给长辈买一台易操作电视",
        "家庭成员为父母或长辈购买电视，核心任务是操作简单、语音遥控和上手门槛低。",
        ("person_senior",),
        ("capability_smart_easy_use", "capability_eye_care"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "children_eye_care_viewing",
        "儿童长期观看护眼陪伴",
        "有儿童家庭希望电视在动画、学习或长期观看时更护眼、更舒适。",
        ("person_child",),
        ("capability_eye_care", "capability_picture_quality"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "new_home_big_screen_fit",
        "新家装修配大屏电视",
        "用户在新家装修、搬家或空间规划场景下，为客厅和墙面选择尺寸合适的大屏电视。",
        ("scene_new_home_decoration",),
        ("capability_large_screen", "capability_picture_quality"),
        ("screen", "size", "inch"),
    ),
    DimensionAssemblyRule(
        "native_task",
        "replacement_big_screen_upgrade",
        "旧机换新升级大屏",
        "用户从旧电视换新，通常希望尺寸升级、体验升级或借助补贴完成换新。",
        ("motive_replacement_upgrade",),
        ("capability_large_screen", "motive_price_value"),
        ("screen", "size", "inch"),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "family_living_room_upgrade",
        "家庭客厅升级用户",
        "以家庭客厅为主要使用场景，关注大屏、画质和声画体验的换新或升级人群。",
        ("scene_living_room_family",),
        ("capability_large_screen", "capability_picture_quality", "capability_audio_immersion"),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "console_gaming_young_entertainment",
        "主机游戏和年轻娱乐用户",
        "以游戏、主机和高刷体验为核心需求的年轻娱乐或游戏用户。",
        ("scene_game_console",),
        ("capability_high_refresh_low_latency",),
        ("refresh", "hz", "hdmi", "vrr", "allm", "game", "high_refresh"),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "sports_heavy_viewer",
        "体育赛事重度观看用户",
        "经常观看球赛或体育赛事，关注运动画面流畅度的人群。",
        ("scene_sports_watching",),
        ("capability_motion_smoothness", "capability_high_refresh_low_latency"),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "senior_family_buyer",
        "长辈家庭代购用户",
        "为父母或长辈购买电视，并关注语音、遥控、系统易用和舒适观看的家庭决策者。",
        ("person_senior",),
        ("capability_smart_easy_use", "capability_eye_care"),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "children_family",
        "有儿童家庭用户",
        "家中有儿童，关注护眼、动画学习陪伴和长期观看舒适度的家庭用户。",
        ("person_child",),
        ("capability_eye_care",),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "new_home_decoration_user",
        "新家装修用户",
        "处于装修、搬家、客厅空间规划阶段，关注尺寸、外观和家居适配的人群。",
        ("scene_new_home_decoration",),
        ("capability_large_screen",),
    ),
    DimensionAssemblyRule(
        "native_target_group",
        "price_sensitive_replacement_user",
        "价格敏感换新用户",
        "受预算、促销、国补或旧机换新驱动，在价格价值和尺寸升级之间做选择的人群。",
        ("motive_price_value",),
        ("motive_replacement_upgrade", "capability_large_screen"),
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "big_screen_picture_immersion",
        "大屏沉浸画质战场",
        "SKU 依靠尺寸、画质、亮度、控光和色彩表现参与大屏观影竞争。",
        ("capability_picture_quality",),
        ("capability_large_screen", "scene_living_room_family"),
        ("screen", "size", "inch", "brightness", "hdr", "dimming", "mini", "oled", "qled", "picture", "color"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "high_refresh_low_latency_gaming",
        "高刷低延迟游戏战场",
        "SKU 依靠刷新率、HDMI、VRR、低延迟和游戏模式参与主机游戏竞争。",
        ("capability_high_refresh_low_latency",),
        ("scene_game_console",),
        ("refresh", "hz", "hdmi", "vrr", "allm", "game", "high_refresh"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "motion_smooth_sports",
        "运动流畅观看战场",
        "SKU 依靠刷新率、MEMC 和运动补偿能力满足体育赛事流畅观看。",
        ("scene_sports_watching",),
        ("capability_motion_smoothness", "capability_high_refresh_low_latency"),
        ("refresh", "memc", "motion", "hz"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "smart_interaction_easy_use",
        "智能交互易用战场",
        "SKU 依靠语音、遥控、系统流畅度和投屏等能力降低使用门槛。",
        ("capability_smart_easy_use",),
        ("person_senior",),
        ("system", "voice", "ram", "storage", "chip", "wifi", "remote"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "eye_care_comfort_viewing",
        "护眼舒适观看战场",
        "SKU 依靠护眼、低蓝光、无频闪和亮度调节能力支撑长期舒适观看。",
        ("capability_eye_care",),
        ("person_child", "person_senior"),
        ("eye", "blue", "care", "flicker", "tuv"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "audio_visual_immersion",
        "声画沉浸战场",
        "SKU 依靠音响、杜比、声场和画质组合提供沉浸式影音体验。",
        ("capability_audio_immersion",),
        ("capability_picture_quality", "scene_living_room_family"),
        ("audio", "speaker", "dolby", "sound"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "big_screen_value_for_money",
        "大屏价值性价比战场",
        "SKU 依靠尺寸、关键配置、价格和销量表现形成同价位价值竞争。",
        ("motive_price_value",),
        ("capability_large_screen", "motive_replacement_upgrade"),
        ("screen", "size", "inch", "price", "sales"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "native_product_value_battlefield",
        "home_space_fit_design",
        "家居空间适配战场",
        "SKU 依靠尺寸、外观、挂装和空间适配参与新家装修场景竞争。",
        ("scene_new_home_decoration",),
        ("capability_large_screen",),
        ("screen", "size", "inch", "design", "bezel", "wall"),
        review_if_missing_anchor=True,
    ),
    DimensionAssemblyRule(
        "purchase_motive",
        "price_value",
        "价格划算与预算选择",
        "用户因价格、国补、优惠或预算约束形成购买动机。",
        ("motive_price_value",),
    ),
    DimensionAssemblyRule(
        "purchase_motive",
        "replacement_upgrade",
        "旧机换新与尺寸升级",
        "用户因旧机替换、以旧换新或尺寸升级形成购买动机。",
        ("motive_replacement_upgrade",),
        ("capability_large_screen",),
    ),
    DimensionAssemblyRule(
        "service_context",
        "service_fulfillment",
        "配送安装与售后履约",
        "用户在评论中提到配送、安装、售后和客服履约体验，只作为服务语境，不进入产品价值战场。",
        ("service_fulfillment",),
        service_context=True,
    ),
    DimensionAssemblyRule(
        "risk_context",
        "system_quality_risk",
        "系统卡顿和质量风险",
        "用户在评论中提到卡顿、故障、坏点、退换等负向体验，用于复核提示。",
        ("system_quality_risk",),
    ),
)


BATTLEFIELD_ANCHOR_SPECS: dict[str, BattlefieldAnchorSpec] = {
    "big_screen_picture_immersion": BattlefieldAnchorSpec(
        code="big_screen_picture_immersion",
        param_rules=(
            ParamAnchorRule(("screen_size_inch", "size_inch"), score=Decimal("0.1600"), min_numeric=Decimal("65")),
            ParamAnchorRule(("resolution", "panel_resolution"), score=Decimal("0.1200"), value_keywords=("4k", "8k", "3840", "7680")),
            ParamAnchorRule(("brightness_nits", "peak_brightness_nits", "instant_peak_brightness_nits"), score=Decimal("0.1600"), min_numeric=Decimal("500")),
            ParamAnchorRule(("local_dimming_zones", "dimming_zone_count", "dimming_zones"), score=Decimal("0.1700"), min_numeric=Decimal("1")),
            ParamAnchorRule(("backlight_type", "panel_type"), score=Decimal("0.1600"), value_keywords=("mini", "oled", "qled", "量子点")),
            ParamAnchorRule(("hdr_support", "hdr_standard", "hdr_format_list"), strength="proxy", score=Decimal("0.1100"), value_keywords=("hdr", "dolby vision", "杜比视界")),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_LARGE_SCREEN_IMMERSION",),
                score=Decimal("0.0600"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("screen_size_inch", "size_inch"),
            ),
            ClaimAnchorRule(
                ("CLAIM_MINI_LED_BACKLIGHT", "CLAIM_OLED_SELF_LIT", "CLAIM_QLED_WIDE_COLOR"),
                score=Decimal("0.1400"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("backlight_type", "panel_type"),
            ),
            ClaimAnchorRule(
                ("CLAIM_FINE_LOCAL_DIMMING",),
                score=Decimal("0.1200"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("local_dimming_zones", "dimming_zone_count", "dimming_zones"),
            ),
        ),
        matrix_keywords=("screen", "size", "inch", "brightness", "hdr", "dimming", "mini", "oled", "qled", "picture", "color"),
    ),
    "high_refresh_low_latency_gaming": BattlefieldAnchorSpec(
        code="high_refresh_low_latency_gaming",
        param_rules=(
            ParamAnchorRule(("native_refresh_rate_hz", "refresh_rate_hz", "refresh_rate", "system_refresh_rate_hz"), score=Decimal("0.2000"), min_numeric=Decimal("120")),
            ParamAnchorRule(("hdmi_2_1_ports", "hdmi_2_1_port_count", "hdmi_version"), score=Decimal("0.1700"), value_keywords=("hdmi2.1", "hdmi 2.1", "2.1")),
            ParamAnchorRule(("hdmi_port_count", "hdmi_ports"), strength="proxy", score=Decimal("0.0800"), min_numeric=Decimal("2"), proxy_for_codes=("hdmi_2_1_ports",)),
            ParamAnchorRule(("vrr_support_flag", "vrr_flag", "allm_support_flag", "allm_flag", "game_mode_flag"), score=Decimal("0.1200"), value_keywords=("是", "yes", "true", "支持", "vrr", "allm", "游戏")),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_HIGH_REFRESH_RATE", "CLAIM_HDMI_2_1_GAMING"),
                score=Decimal("0.1600"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("native_refresh_rate_hz", "refresh_rate_hz", "refresh_rate", "system_refresh_rate_hz", "hdmi_2_1_ports", "hdmi_2_1_port_count", "hdmi_version"),
            ),
            ClaimAnchorRule(
                ("CLAIM_GAMING_LOW_LATENCY",),
                score=Decimal("0.1200"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("vrr_support_flag", "vrr_flag", "allm_support_flag", "allm_flag", "game_mode_flag", "hdmi_2_1_ports", "hdmi_2_1_port_count", "hdmi_version"),
            ),
        ),
        matrix_keywords=("refresh", "hz", "hdmi", "vrr", "allm", "game", "high_refresh"),
    ),
    "motion_smooth_sports": BattlefieldAnchorSpec(
        code="motion_smooth_sports",
        param_rules=(
            ParamAnchorRule(("native_refresh_rate_hz", "refresh_rate_hz", "refresh_rate", "system_refresh_rate_hz"), score=Decimal("0.1600"), min_numeric=Decimal("120")),
            ParamAnchorRule(
                ("motion_compensation_flag", "memc_support_flag", "memc_flag", "motion_smoothing_flag"),
                score=Decimal("0.1800"),
                value_keywords=("是", "yes", "true", "支持", "memc", "运动补偿"),
                invalid_raw_name_keywords=("人工智能", "全屋智控", "无缝贴墙"),
                valid_raw_name_keywords=("运动", "补偿", "memc", "流畅"),
            ),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_SPORTS_MOTION_SMOOTH",),
                score=Decimal("0.1700"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=(
                    "native_refresh_rate_hz",
                    "refresh_rate_hz",
                    "refresh_rate",
                    "system_refresh_rate_hz",
                    "motion_compensation_flag",
                    "memc_support_flag",
                    "memc_flag",
                    "motion_smoothing_flag",
                ),
            ),
        ),
        matrix_keywords=("refresh", "memc", "motion", "hz"),
    ),
    "smart_interaction_easy_use": BattlefieldAnchorSpec(
        code="smart_interaction_easy_use",
        param_rules=(
            ParamAnchorRule(("chipset_name", "cpu_name"), strength="proxy", score=Decimal("0.0600"), value_keywords=("a", "mt", "quad", "core", "核")),
            ParamAnchorRule(("ram_gb", "memory_gb"), strength="proxy", score=Decimal("0.0700"), min_numeric=Decimal("2")),
            ParamAnchorRule(("storage_gb",), strength="proxy", score=Decimal("0.0600"), min_numeric=Decimal("16")),
            ParamAnchorRule(("voice_control_flag", "far_field_voice_flag"), score=Decimal("0.1300"), value_keywords=("是", "yes", "true", "支持", "语音")),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_SMART_VOICE_EASE",),
                score=Decimal("0.1500"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("voice_control_flag", "far_field_voice_flag"),
            ),
            ClaimAnchorRule(("CLAIM_NO_AD_OR_CLEAN_SYSTEM",), score=Decimal("0.0800"), min_score=Decimal("0.1000")),
            ClaimAnchorRule(
                ("CLAIM_ELDER_FRIENDLY_SMART",),
                score=Decimal("0.0800"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("voice_control_flag", "far_field_voice_flag"),
            ),
        ),
        matrix_keywords=("system", "voice", "ram", "storage", "chip", "wifi", "remote"),
    ),
    "eye_care_comfort_viewing": BattlefieldAnchorSpec(
        code="eye_care_comfort_viewing",
        param_rules=(
            ParamAnchorRule(
                (
                    "eye_care_flag",
                    "eye_protection_flag",
                    "eye_protection_mode_flag",
                    "low_blue_light_flag",
                    "flicker_free_flag",
                    "tuv_certification",
                    "child_mode_flag",
                ),
                score=Decimal("0.1800"),
                value_keywords=("是", "yes", "true", "支持", "护眼", "低蓝光", "无频闪", "tuv", "儿童"),
            ),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_EYE_CARE_COMFORT",),
                score=Decimal("0.1800"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=(
                    "eye_care_flag",
                    "eye_protection_flag",
                    "eye_protection_mode_flag",
                    "low_blue_light_flag",
                    "flicker_free_flag",
                    "tuv_certification",
                    "child_mode_flag",
                ),
            ),
        ),
        matrix_keywords=("eye", "blue", "care", "flicker", "tuv"),
    ),
    "audio_visual_immersion": BattlefieldAnchorSpec(
        code="audio_visual_immersion",
        param_rules=(
            ParamAnchorRule(
                (
                    "speaker_power_w",
                    "speaker_power_total_w",
                    "speaker_channel",
                    "speaker_channel_count",
                    "audio_system",
                    "sound_system",
                    "dolby_audio_flag",
                    "dolby_atmos_flag",
                    "dts_support_flag",
                ),
                score=Decimal("0.1800"),
                min_numeric=Decimal("10"),
                value_keywords=("dolby", "杜比", "dts", "音响", "扬声器", "声道", "w"),
                invalid_raw_name_keywords=("内置wifi", "wifi"),
                valid_raw_name_keywords=("音", "声", "喇叭", "扬声器", "杜比", "dts", "speaker", "audio"),
            ),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_IMMERSIVE_AUDIO", "CLAIM_DOLBY_CINEMA_AUDIO"),
                score=Decimal("0.1700"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=(
                    "speaker_power_w",
                    "speaker_power_total_w",
                    "speaker_channel",
                    "speaker_channel_count",
                    "audio_system",
                    "sound_system",
                    "dolby_audio_flag",
                    "dolby_atmos_flag",
                    "dts_support_flag",
                ),
            ),
        ),
        matrix_keywords=("audio", "speaker", "dolby", "sound"),
    ),
    "big_screen_value_for_money": BattlefieldAnchorSpec(
        code="big_screen_value_for_money",
        param_rules=(
            ParamAnchorRule(("screen_size_inch", "size_inch"), strength="proxy", score=Decimal("0.0600"), min_numeric=Decimal("65")),
            ParamAnchorRule(("price_latest", "price_wavg_12m"), score=Decimal("0.1000"), min_numeric=Decimal("1")),
        ),
        claim_rules=(ClaimAnchorRule(("CLAIM_VALUE_FOR_MONEY",), score=Decimal("0.1000"), min_score=Decimal("0.1000")),),
        matrix_keywords=("screen", "size", "inch", "price", "sales"),
    ),
    "home_space_fit_design": BattlefieldAnchorSpec(
        code="home_space_fit_design",
        param_rules=(
            ParamAnchorRule(("screen_size_inch", "size_inch"), strength="proxy", score=Decimal("0.0400"), min_numeric=Decimal("65")),
            ParamAnchorRule(
                ("thickness_mm", "body_thickness_mm", "bezel_width_mm", "wall_mount_flag", "full_screen_flag", "slim_design_flag"),
                score=Decimal("0.1200"),
                value_keywords=("是", "yes", "true", "支持", "超薄", "挂墙", "全面屏"),
            ),
        ),
        claim_rules=(
            ClaimAnchorRule(
                ("CLAIM_THIN_DESIGN",),
                score=Decimal("0.1300"),
                min_score=Decimal("0.1000"),
                requires_param_support=True,
                support_param_codes=("thickness_mm", "body_thickness_mm", "bezel_width_mm", "wall_mount_flag", "full_screen_flag", "slim_design_flag"),
            ),
        ),
        matrix_keywords=("screen", "size", "inch", "design", "bezel", "wall"),
    ),
}


class CommentNativeDimensionDiscoveryService:
    def __init__(
        self,
        repository: CommentNativeDimensionRepository,
        *,
        seed_loader: M085DimensionSeedLoader | None = None,
    ) -> None:
        self.repository = repository
        self.seed_loader = seed_loader or M085DimensionSeedLoader()

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M08_4_RULE_VERSION,
        seed_version: str = CORE3_M08_4_SEED_VERSION,
    ) -> M084ServiceResult:
        self.repository.assert_inputs_ready(batch_id)
        bundle = self.repository.load_input_bundle(batch_id)
        seed = self.seed_loader.load()
        signals = _build_signals(
            bundle,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        candidates = _build_candidates(
            bundle,
            signals,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        self.repository.supersede_current_outputs(batch_id, rule_version=rule_version)
        signal_write = self.repository.save_signals(signals)
        candidate_write = self.repository.save_candidates(candidates)
        id_by_dimension_code = {
            record.native_dimension_code: row.native_dimension_id
            for record, row in zip(candidates, candidate_write.records, strict=False)
        }
        supports = _build_sku_supports(
            bundle,
            candidates,
            id_by_dimension_code=id_by_dimension_code,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        support_write = self.repository.save_sku_supports(supports)
        alignments = _build_alignments(
            seed,
            candidates,
            id_by_dimension_code=id_by_dimension_code,
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            seed_version=seed_version,
        )
        alignment_write = self.repository.save_alignments(alignments)
        issues = _build_issues(
            candidates,
            alignments,
            total_sku_count=len(bundle.profiles),
            project_id=self.repository.project_id,
            category_code=self.repository.category_code.value,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
        )
        issue_write = self.repository.save_issues(issues)

        summary = _summary(
            bundle=bundle,
            signals=signals,
            candidates=candidates,
            supports=supports,
            alignments=alignments,
            issues=issues,
            write_summary={
                "signals": _write_result_dict(signal_write),
                "candidates": _write_result_dict(candidate_write),
                "sku_supports": _write_result_dict(support_write),
                "alignments": _write_result_dict(alignment_write),
                "issues": _write_result_dict(issue_write),
            },
        )
        warnings = _warnings(summary)
        status = Core3RunStatus.WARNING if warnings or any(issue.severity != "info" for issue in issues) else Core3RunStatus.SUCCESS
        return M084ServiceResult(
            signals=tuple(signals),
            candidates=tuple(candidates),
            sku_supports=tuple(supports),
            alignments=tuple(alignments),
            issues=tuple(issues),
            summary=summary,
            warnings=warnings,
            status=status,
            input_count=len(bundle.comment_atoms),
            output_count=len(signals) + len(candidates) + len(supports) + len(alignments) + len(issues),
            created_output_count=sum(item["created_count"] for item in summary["write_summary"].values()),
        )


def _build_signals(
    bundle: M084InputBundle,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[M084NativeSignalRecord]:
    hits_by_code: dict[str, list[SignalHit]] = defaultdict(list)
    for atom in bundle.comment_atoms:
        text = _text(atom)
        for rule in NATIVE_SIGNAL_RULES:
            if _matches_rule(text, rule):
                hits_by_code[rule.code].append(SignalHit(rule=rule, atom=atom, strength=_hit_strength(atom, rule)))
    matrix_index = _matrix_anchor_index(bundle.matrices)
    records: list[M084NativeSignalRecord] = []
    for code, hits in sorted(hits_by_code.items()):
        rule = hits[0].rule
        sku_codes = sorted({hit.atom.sku_code for hit in hits})
        phrases = _representative_phrases(hit.atom for hit in hits)
        evidence_ids = _representative_evidence_ids(hit.atom for hit in hits)
        product_anchor = {
            sku_code: sorted(_matched_anchor_keywords(matrix_index.get(sku_code, ()), rule.product_anchor_keywords))
            for sku_code in sku_codes
            if _matched_anchor_keywords(matrix_index.get(sku_code, ()), rule.product_anchor_keywords)
        }
        payload = {
            "native_signal_code": code,
            "signal_type": rule.signal_family,
            "sentence_count": len(hits),
            "sku_count": len(sku_codes),
            "avg_strength_score": _avg(hit.strength for hit in hits),
            "specificity_score": _avg(_decimal(hit.atom.specificity_score) for hit in hits),
            "comment_confidence": _avg(_decimal(hit.atom.confidence) for hit in hits),
            "sku_distribution_json": _sku_distribution(hits),
            "representative_evidence_ids": evidence_ids,
        }
        input_fingerprint = stable_hash(payload, version="m084_native_signal_input_v1")
        result_hash = stable_hash({**payload, "phrases": phrases, "anchors": product_anchor}, version="m084_native_signal_result_v1")
        records.append(
            M084NativeSignalRecord(
                native_signal_id=_stable_id("m084-signal", code),
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                native_signal_code=code,
                native_signal_name_cn=rule.name_cn,
                signal_type=rule.signal_family,
                source_comment_domain=rule.source_domain,
                sentence_count=len(hits),
                sku_count=len(sku_codes),
                strong_sentence_count=sum(1 for hit in hits if hit.strength >= Decimal("0.7500")),
                positive_sentence_count=sum(1 for hit in hits if str(hit.atom.sentiment_hint) == "positive"),
                negative_sentence_count=sum(1 for hit in hits if str(hit.atom.sentiment_hint) == "negative"),
                service_sentence_count=len(hits) if rule.service_context else 0,
                avg_strength_score=_avg(hit.strength for hit in hits),
                specificity_score=_avg(_decimal(hit.atom.specificity_score) for hit in hits),
                comment_confidence=_avg(_decimal(hit.atom.confidence) for hit in hits),
                native_keyword_json={"matched": _matched_keywords_for_hits(hits), "rule_keywords": list(rule.keywords)},
                sku_distribution_json=_sku_distribution(hits),
                representative_phrase_json=phrases,
                representative_evidence_ids=evidence_ids,
                product_anchor_hint_json=product_anchor,
                service_context_flag=rule.service_context,
                signal_status="active",
                review_required=rule.service_context or rule.negative_context,
                review_reason_json=_signal_review_reason(rule),
                source_rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                result_hash=result_hash,
            )
        )
    return records


def _build_candidates(
    bundle: M084InputBundle,
    signals: Sequence[M084NativeSignalRecord],
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[M084NativeDimensionCandidateRecord]:
    signal_by_code = {signal.native_signal_code: signal for signal in signals}
    product_anchor_index = ProductAnchorIndex.from_bundle(bundle)
    total_sku_count = max(len(bundle.profiles), 1)
    records: list[M084NativeDimensionCandidateRecord] = []
    for rule in DIMENSION_ASSEMBLY_RULES:
        if not _assembly_rule_active(rule, signal_by_code):
            continue
        source_signals = _signals_for_assembly_rule(rule, signal_by_code)
        sku_distribution = _aggregate_signal_distribution_for_rule(rule, signal_by_code)
        if not sku_distribution:
            continue
        native_dimension_code = f"{rule.dimension_type}_{rule.code}"
        sentence_count = sum(signal.sentence_count for signal in source_signals)
        sku_count = len(sku_distribution)
        product_anchor_by_sku = _candidate_product_anchor_by_sku(sku_distribution, product_anchor_index, rule)
        product_anchor_score = _candidate_product_anchor_score_from_distribution(
            product_anchor_by_sku,
            sku_count=sku_count,
            dimension_type=rule.dimension_type,
            service_context=rule.service_context,
        )
        coverage_ratio = Decimal(sku_count) / Decimal(total_sku_count)
        distinctiveness = _clamp(Decimal("1.0000") - coverage_ratio + Decimal("0.1500"))
        evidence_diversity_score = _clamp(Decimal(len(source_signals)) / Decimal("4"))
        avg_strength_score = _avg(signal.avg_strength_score for signal in source_signals)
        native_support_score = _dimension_support_score(
            dimension_type=rule.dimension_type,
            avg_strength_score=avg_strength_score,
            product_anchor_score=product_anchor_score,
            distinctiveness_score=distinctiveness,
            evidence_diversity_score=evidence_diversity_score,
        )
        strong_sku_count = sum(1 for item in sku_distribution.values() if _decimal(item.get("avg_strength")) >= Decimal("0.7000"))
        include_keywords = _candidate_include_keywords(rule, source_signals)
        phrases = _merge_representative_phrases(source_signals)
        evidence_ids = _merge_representative_evidence_ids(source_signals)
        anchor_quality_summary = _anchor_quality_summary(product_anchor_by_sku, sku_count)
        payload = {
            "dimension_type": rule.dimension_type,
            "native_dimension_code": native_dimension_code,
            "source_signal_codes": list(rule.source_signal_codes),
            "sentence_count": sentence_count,
            "sku_count": sku_count,
            "native_support_score": native_support_score,
            "product_anchor_score": product_anchor_score,
            "assembly_rule": rule.code,
        }
        input_fingerprint = stable_hash(payload, version="m084_candidate_input_v2")
        records.append(
            M084NativeDimensionCandidateRecord(
                native_dimension_id=_stable_id("m084-dim", native_dimension_code),
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                dimension_type=rule.dimension_type,
                native_dimension_code=native_dimension_code,
                native_dimension_name_cn=rule.name_cn,
                definition_draft_cn=rule.definition_cn,
                source_signal_codes=list(rule.source_signal_codes),
                include_keyword_json=include_keywords,
                exclude_keyword_json=_candidate_exclude_keywords(rule.dimension_type),
                sentence_count=sentence_count,
                sku_count=sku_count,
                strong_sku_count=strong_sku_count,
                native_support_score=native_support_score,
                product_anchor_score=product_anchor_score,
                distinctiveness_score=distinctiveness,
                representative_phrase_json=phrases,
                representative_evidence_ids=evidence_ids,
                support_summary_json={
                    "assembly_rule": rule.code,
                    "required_signal_codes": list(rule.required_signal_codes),
                    "optional_signal_codes": list(rule.optional_signal_codes),
                    "source_signal_codes": [signal.native_signal_code for signal in source_signals],
                    "signal_family_by_code": {signal.native_signal_code: signal.signal_type for signal in source_signals},
                    "product_anchor_keywords": list(rule.product_anchor_keywords),
                    "product_anchor_by_sku": product_anchor_by_sku,
                    "anchor_quality_summary": anchor_quality_summary,
                    "sku_distribution": sku_distribution,
                },
                service_context_flag=rule.service_context,
                candidate_status=_candidate_status(
                    native_support_score,
                    product_anchor_score,
                    service_context_flag=rule.service_context,
                    dimension_type=rule.dimension_type,
                ),
                review_required=_candidate_review_required(rule, product_anchor_score),
                review_reason_json=_candidate_review_reason(rule, product_anchor_score, anchor_quality_summary=anchor_quality_summary),
                rule_version=rule_version,
                input_fingerprint=input_fingerprint,
                result_hash=stable_hash(
                    payload | {"name": rule.name_cn, "anchors": product_anchor_by_sku},
                    version="m084_candidate_result_v2",
                ),
            )
        )
    return records


def _build_sku_supports(
    bundle: M084InputBundle,
    candidates: Sequence[M084NativeDimensionCandidateRecord],
    *,
    id_by_dimension_code: Mapping[str, str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[M084SkuSupportRecord]:
    profile_by_sku = {profile.sku_code: profile for profile in bundle.profiles}
    signal_distribution_by_code = _signal_distribution_from_candidates(candidates)
    market_index = _market_anchor_index(bundle.profiles)
    records: list[M084SkuSupportRecord] = []
    for candidate in candidates:
        distribution = signal_distribution_by_code.get(candidate.native_dimension_code, {})
        product_anchor_by_sku = candidate.support_summary_json.get("product_anchor_by_sku") or {}
        product_anchor_keywords = tuple(candidate.support_summary_json.get("product_anchor_keywords") or [])
        for sku_code, dist in sorted(distribution.items()):
            profile = profile_by_sku.get(sku_code)
            anchor_payload = product_anchor_by_sku.get(sku_code, {})
            product_anchor = _anchor_payload_score(anchor_payload)
            layered_market_anchor = _decimal(anchor_payload.get("market_anchor_score")) if isinstance(anchor_payload, Mapping) else Decimal("0.0000")
            market_anchor = layered_market_anchor if layered_market_anchor > 0 else market_index.get(sku_code, Decimal("0.0000"))
            comment_support = _decimal(dist.get("avg_strength"))
            support_score = _sku_dimension_support_score(
                dimension_type=candidate.dimension_type,
                comment_support=comment_support,
                product_anchor=product_anchor,
                market_anchor=market_anchor,
            )
            payload = {
                "native_dimension_code": candidate.native_dimension_code,
                "sku_code": sku_code,
                "support_score": support_score,
                "comment_sentence_count": int(dist.get("sentence_count") or 0),
            }
            records.append(
                M084SkuSupportRecord(
                    native_dimension_sku_support_id=_stable_id("m084-support", f"{candidate.native_dimension_code}-{sku_code}"),
                    native_dimension_id=id_by_dimension_code[candidate.native_dimension_code],
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    sku_code=sku_code,
                    model_name=getattr(profile, "model_name", None),
                    brand_name=getattr(profile, "brand_name", None),
                    dimension_type=candidate.dimension_type,
                    native_dimension_code=candidate.native_dimension_code,
                    comment_sentence_count=int(dist.get("sentence_count") or 0),
                    comment_support_score=comment_support,
                    product_anchor_score=product_anchor,
                    market_anchor_score=market_anchor,
                    support_score=support_score,
                    support_level=_support_level(support_score),
                    evidence_breakdown_json={
                        "comment": dist,
                        "product_anchor_keywords": list(product_anchor_keywords),
                        "product_anchor": anchor_payload,
                        "source_signal_codes": candidate.source_signal_codes,
                    },
                    representative_evidence_ids=list(dist.get("evidence_ids") or [])[:10],
                    support_reason_cn=_support_reason(candidate, comment_support, product_anchor, market_anchor),
                    service_context_flag=candidate.service_context_flag,
                    review_required=support_score < Decimal("0.3500"),
                    review_reason_json={"reason": "support_score_low"} if support_score < Decimal("0.3500") else {},
                    rule_version=rule_version,
                    input_fingerprint=stable_hash(payload, version="m084_support_input_v1"),
                    result_hash=stable_hash(payload | {"anchor": product_anchor, "market": market_anchor}, version="m084_support_result_v1"),
                )
            )
    return records


def _build_alignments(
    seed: M085DimensionSeed,
    candidates: Sequence[M084NativeDimensionCandidateRecord],
    *,
    id_by_dimension_code: Mapping[str, str],
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    seed_version: str,
) -> list[M084AlignmentProposalRecord]:
    seed_rows = _seed_rows(seed)
    records: list[M084AlignmentProposalRecord] = []
    matched_seed_codes: set[str] = set()
    for candidate in candidates:
        if candidate.dimension_type == "service_context":
            seed_row = _find_seed(seed_rows, "battlefield", "BF_SERVICE_ASSURANCE")
            if seed_row is not None:
                matched_seed_codes.add("BF_SERVICE_ASSURANCE")
                records.append(
                    _alignment_record(
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        native_dimension_id=id_by_dimension_code.get(candidate.native_dimension_code),
                        seed_dimension_type="battlefield",
                        seed_dimension_code="BF_SERVICE_ASSURANCE",
                        seed_dimension_name_cn=seed_row["name"],
                        candidate=candidate,
                        relation="service_context_only",
                        score=Decimal("0.9000"),
                        action="downgrade_to_service_context",
                        reason_cn="评论中的配送、安装、售后属于履约体验，不应作为产品价值战场参与 SKU 分类。",
                        rule_version=rule_version,
                        seed_version=seed_version,
                    )
                )
            continue
        compatible_seeds = [row for row in seed_rows if _compatible_dimension_type(candidate.dimension_type, row["type"])]
        seed_matches = _seed_matches_for_candidate(candidate, compatible_seeds)
        if seed_matches:
            for match_index, (seed_row, score) in enumerate(seed_matches):
                matched_seed_codes.add(str(seed_row["code"]))
                relation = "merge" if score >= Decimal("0.5500") else "partial_overlap"
                action = "keep_with_native_boundary" if score >= Decimal("0.5500") else "review_split_or_refine"
                reason = (
                    "评论原生候选与预设维度存在语义重合，建议保留预设名称但补充边界定义。"
                    if score >= Decimal("0.5500")
                    else "评论原生候选只覆盖预设维度的一部分，建议复核是否拆分或重命名。"
                )
                if match_index > 0:
                    reason = f"{reason} 该候选同时支撑多个预设战场，作为二级产品锚点对齐。"
                records.append(
                    _alignment_record(
                        project_id=project_id,
                        category_code=category_code,
                        batch_id=batch_id,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        native_dimension_id=id_by_dimension_code.get(candidate.native_dimension_code),
                        seed_dimension_type=str(seed_row["type"]),
                        seed_dimension_code=str(seed_row["code"]),
                        seed_dimension_name_cn=str(seed_row["name"]),
                        candidate=candidate,
                        relation=relation,
                        score=score,
                        action=action,
                        reason_cn=reason,
                        rule_version=rule_version,
                        seed_version=seed_version,
                    )
                )
        else:
            _, best_score = _best_seed_match(candidate, compatible_seeds)
            records.append(
                _alignment_record(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    native_dimension_id=id_by_dimension_code.get(candidate.native_dimension_code),
                    seed_dimension_type=_seed_type_for_candidate(candidate.dimension_type),
                    seed_dimension_code=None,
                    seed_dimension_name_cn=None,
                    candidate=candidate,
                    relation="new_native_candidate",
                    score=best_score,
                    action="review_add_or_merge",
                    reason_cn="评论中出现了预设未稳定覆盖的原生业务维度，需要业务复核是否新增、合并或作为别名。",
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
    for seed_row in seed_rows:
        if seed_row["code"] in matched_seed_codes or seed_row["code"] == "BF_SERVICE_ASSURANCE":
            continue
        if any(_compatible_dimension_type(candidate.dimension_type, str(seed_row["type"])) for candidate in candidates):
            score = Decimal("0.0000")
            key_candidate = None
            records.append(
                _alignment_record(
                    project_id=project_id,
                    category_code=category_code,
                    batch_id=batch_id,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    native_dimension_id=None,
                    seed_dimension_type=str(seed_row["type"]),
                    seed_dimension_code=str(seed_row["code"]),
                    seed_dimension_name_cn=str(seed_row["name"]),
                    candidate=key_candidate,
                    relation="seed_no_native_support",
                    score=score,
                    action="keep_seed_but_mark_weak_support",
                    reason_cn="当前样例评论未发现该预设维度的原生表达，后续分类需更多参数、卖点或市场证据支撑。",
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
    return records


def _build_issues(
    candidates: Sequence[M084NativeDimensionCandidateRecord],
    alignments: Sequence[M084AlignmentProposalRecord],
    *,
    total_sku_count: int,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
) -> list[M084ReviewIssueRecord]:
    issues: list[M084ReviewIssueRecord] = []
    for candidate in candidates:
        if candidate.service_context_flag:
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    "service_signal_not_product_value",
                    "service_boundary",
                    "warning",
                    "native_dimension_candidate",
                    candidate.native_dimension_code,
                    f"{candidate.native_dimension_name_cn} 属于履约服务语境，不能直接进入产品价值战场。",
                    "在 M08.5 中降级为服务语境，只允许作为报告解释和服务问题提示。",
                    {"candidate": candidate.native_dimension_code, "dimension_type": candidate.dimension_type},
                )
            )
        anchor_quality = candidate.support_summary_json.get("anchor_quality_summary") or {}
        if candidate.dimension_type == "native_product_value_battlefield" and candidate.product_anchor_score < Decimal("0.3000"):
            has_any_anchor = _has_effective_anchor(anchor_quality)
            issue_code = "product_anchor_weak" if has_any_anchor else "product_anchor_missing"
            message_cn = (
                f"{candidate.native_dimension_name_cn} 已命中部分参数或卖点锚点，但平均强度不足。"
                if has_any_anchor
                else f"{candidate.native_dimension_name_cn} 评论有表达，但未命中可用参数、卖点或同池优势锚点。"
            )
            recommendation_cn = (
                "保留为候选并进入复核；正式发布前需要补足强参数、强卖点或同池优势证据。"
                if has_any_anchor
                else "后续进入正式价值战场前，需要先命中参数、卖点或同池优势锚点。"
            )
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    issue_code,
                    "evidence_gap",
                    "warning",
                    "native_dimension_candidate",
                    candidate.native_dimension_code,
                    message_cn,
                    recommendation_cn,
                    {
                        "candidate": candidate.native_dimension_code,
                        "product_anchor_score": float(candidate.product_anchor_score),
                        **anchor_quality,
                    },
                )
            )
        if int(anchor_quality.get("dirty_param_sku_count") or 0) > 0:
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    "param_mapping_suspect",
                    "anchor_quality",
                    "warning",
                    "native_dimension_candidate",
                    candidate.native_dimension_code,
                    f"{candidate.native_dimension_name_cn} 存在参数字段语义错配，不能直接作为强产品锚点。",
                    "复核 M03 参数映射；在修复前，M08.4 只把这些参数作为质量问题，不抬高战场分数。",
                    {"candidate": candidate.native_dimension_code, **anchor_quality},
                )
            )
        if int(anchor_quality.get("matrix_only_sku_count") or 0) > 0 and candidate.dimension_type == "native_product_value_battlefield":
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    "matrix_only_anchor",
                    "anchor_quality",
                    "warning",
                    "native_dimension_candidate",
                    candidate.native_dimension_code,
                    f"{candidate.native_dimension_name_cn} 存在只由 M08 泛化矩阵支撑的 SKU。",
                    "产品价值战场进入正式本体前，需要参数或卖点锚点，矩阵泛化特征不能单独成立。",
                    {"candidate": candidate.native_dimension_code, **anchor_quality},
                )
            )
        coverage_ratio = Decimal(candidate.sku_count) / Decimal(max(total_sku_count, 1))
        if coverage_ratio >= Decimal("0.7500") and candidate.dimension_type in {"native_product_value_battlefield", "native_target_group", "native_task"}:
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    "dimension_too_broad",
                    "distinctiveness",
                    "warning",
                    "native_dimension_candidate",
                    candidate.native_dimension_code,
                    f"{candidate.native_dimension_name_cn} 覆盖 SKU 比例过高，区分度可能不足。",
                    "复核关键词是否过宽，避免所有 SKU 都命中同一业务维度。",
                    {"candidate": candidate.native_dimension_code, "coverage_ratio": float(coverage_ratio)},
                )
            )
    for alignment in alignments:
        if alignment.proposed_action in {"review_add_or_merge", "review_split_or_refine", "downgrade_to_service_context"}:
            issues.append(
                _issue(
                    project_id,
                    category_code,
                    batch_id,
                    run_id,
                    module_run_id,
                    rule_version,
                    f"alignment_{alignment.proposed_action}",
                    "ontology_alignment",
                    "warning" if alignment.proposed_action != "downgrade_to_service_context" else "medium",
                    "alignment_proposal",
                    alignment.alignment_key,
                    alignment.reason_cn,
                    "由 M08.5 本体校准阶段消费该建议，生成更清晰的预设定义和边界。",
                    {"alignment_key": alignment.alignment_key, "score": float(alignment.alignment_score)},
                )
            )
    return _dedupe_issues(issues)


def _alignment_record(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    native_dimension_id: str | None,
    seed_dimension_type: str,
    seed_dimension_code: str | None,
    seed_dimension_name_cn: str | None,
    candidate: M084NativeDimensionCandidateRecord | None,
    relation: str,
    score: Decimal,
    action: str,
    reason_cn: str,
    rule_version: str,
    seed_version: str,
) -> M084AlignmentProposalRecord:
    native_code = candidate.native_dimension_code if candidate else None
    native_name = candidate.native_dimension_name_cn if candidate else None
    alignment_key = f"{seed_dimension_type}:{seed_dimension_code or 'NEW'}:{native_code or 'NO_NATIVE'}:{relation}"
    payload = {
        "alignment_key": alignment_key,
        "seed_dimension_code": seed_dimension_code,
        "native_dimension_code": native_code,
        "relation": relation,
        "action": action,
        "score": score,
    }
    return M084AlignmentProposalRecord(
        alignment_proposal_id=_stable_id("m084-align", alignment_key),
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        native_dimension_id=native_dimension_id,
        alignment_key=alignment_key,
        seed_dimension_type=seed_dimension_type,
        seed_dimension_code=seed_dimension_code,
        seed_dimension_name_cn=seed_dimension_name_cn,
        native_dimension_code=native_code,
        native_dimension_name_cn=native_name,
        alignment_relation=relation,
        alignment_score=score,
        proposed_action=action,
        reason_cn=reason_cn,
        evidence_json={"native_dimension": native_code, "native_support": float(candidate.native_support_score) if candidate else None},
        downstream_effect_json={"consumer": "M08.5", "effect": action},
        review_required=action != "keep_with_native_boundary",
        review_status="open" if action != "keep_with_native_boundary" else "auto_pass",
        rule_version=rule_version,
        seed_version=seed_version,
        input_fingerprint=stable_hash(payload, version="m084_alignment_input_v1"),
        result_hash=stable_hash(payload | {"reason": reason_cn}, version="m084_alignment_result_v1"),
    )


def _issue(
    project_id: str,
    category_code: str,
    batch_id: str,
    run_id: str | None,
    module_run_id: str | None,
    rule_version: str,
    issue_code: str,
    issue_type: str,
    severity: str,
    object_type: str,
    object_code: str,
    message: str,
    suggestion: str,
    evidence: dict[str, Any],
) -> M084ReviewIssueRecord:
    issue_key = f"{issue_code}:{object_type}:{object_code}"
    payload = {"issue_key": issue_key, "message": message, "evidence": evidence}
    return M084ReviewIssueRecord(
        native_dimension_issue_id=_stable_id("m084-issue", issue_key),
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        issue_key=issue_key,
        issue_code=issue_code,
        issue_type=issue_type,
        severity=severity,
        object_type=object_type,
        object_code=object_code,
        issue_message_cn=message,
        evidence_json=evidence,
        suggested_action_cn=suggestion,
        review_status="open",
        rule_version=rule_version,
        input_fingerprint=stable_hash(payload, version="m084_issue_input_v1"),
        result_hash=stable_hash(payload | {"suggestion": suggestion}, version="m084_issue_result_v1"),
    )


def _assembly_rule_active(rule: DimensionAssemblyRule, signal_by_code: Mapping[str, M084NativeSignalRecord]) -> bool:
    return all(signal_code in signal_by_code for signal_code in rule.required_signal_codes)


def _signals_for_assembly_rule(
    rule: DimensionAssemblyRule,
    signal_by_code: Mapping[str, M084NativeSignalRecord],
) -> list[M084NativeSignalRecord]:
    seen: set[str] = set()
    records: list[M084NativeSignalRecord] = []
    for signal_code in rule.source_signal_codes:
        signal = signal_by_code.get(signal_code)
        if signal is None or signal_code in seen:
            continue
        seen.add(signal_code)
        records.append(signal)
    return records


def _aggregate_signal_distribution_for_rule(
    rule: DimensionAssemblyRule,
    signal_by_code: Mapping[str, M084NativeSignalRecord],
) -> dict[str, dict[str, Any]]:
    required_sku_sets: list[set[str]] = []
    for signal_code in rule.required_signal_codes:
        signal = signal_by_code.get(signal_code)
        if signal is None:
            return {}
        required_sku_sets.append(set((signal.sku_distribution_json or {}).keys()))
    if not required_sku_sets:
        return {}
    eligible_skus = set.intersection(*required_sku_sets)
    if not eligible_skus:
        return {}
    signals = _signals_for_assembly_rule(rule, signal_by_code)
    return _aggregate_signal_distribution(signals, eligible_skus=eligible_skus)


def _aggregate_signal_distribution(
    signals: Sequence[M084NativeSignalRecord],
    *,
    eligible_skus: set[str],
) -> dict[str, dict[str, Any]]:
    by_sku: dict[str, dict[str, Any]] = {}
    for signal in signals:
        for sku_code, dist in (signal.sku_distribution_json or {}).items():
            if sku_code not in eligible_skus:
                continue
            bucket = by_sku.setdefault(
                sku_code,
                {
                    "sentence_count": 0,
                    "strength_sum": Decimal("0.0000"),
                    "evidence_ids": [],
                    "phrases": [],
                    "source_signal_codes": [],
                },
            )
            sentence_count = int(dist.get("sentence_count") or 0)
            avg_strength = _decimal(dist.get("avg_strength"))
            bucket["sentence_count"] += sentence_count
            bucket["strength_sum"] += avg_strength * Decimal(max(sentence_count, 1))
            _extend_unique(bucket["evidence_ids"], list(dist.get("evidence_ids") or []), limit=20)
            _extend_unique(bucket["phrases"], list(dist.get("phrases") or []), limit=8)
            _extend_unique(bucket["source_signal_codes"], [signal.native_signal_code], limit=20)
    result: dict[str, dict[str, Any]] = {}
    for sku_code, bucket in sorted(by_sku.items()):
        sentence_count = int(bucket["sentence_count"])
        result[sku_code] = {
            "sentence_count": sentence_count,
            "avg_strength": float(_clamp(bucket["strength_sum"] / Decimal(max(sentence_count, 1)))),
            "evidence_ids": bucket["evidence_ids"],
            "phrases": bucket["phrases"],
            "source_signal_codes": bucket["source_signal_codes"],
        }
    return result


class ProductAnchorIndex:
    def __init__(
        self,
        *,
        profiles_by_sku: Mapping[str, entities.Core3SkuSignalProfile],
        market_profiles_by_sku: Mapping[str, Sequence[entities.Core3SkuMarketProfile]],
        params_by_sku: Mapping[str, Sequence[entities.Core3ExtractParamValue]],
        claim_bases_by_sku: Mapping[str, Sequence[entities.Core3SkuClaimActivationBase]],
        claims_by_sku: Mapping[str, Sequence[entities.Core3SkuClaimActivation]],
        matrix_index: Mapping[str, Sequence[str]],
    ) -> None:
        self.profiles_by_sku = profiles_by_sku
        self.market_profiles_by_sku = market_profiles_by_sku
        self.params_by_sku = params_by_sku
        self.claim_bases_by_sku = claim_bases_by_sku
        self.claims_by_sku = claims_by_sku
        self.matrix_index = matrix_index

    @classmethod
    def from_bundle(cls, bundle: M084InputBundle) -> "ProductAnchorIndex":
        return cls(
            profiles_by_sku={profile.sku_code: profile for profile in bundle.profiles},
            market_profiles_by_sku=_group_by_sku(bundle.market_profiles),
            params_by_sku=_group_by_sku(bundle.param_values),
            claim_bases_by_sku=_group_by_sku(bundle.claim_activation_bases),
            claims_by_sku=_group_by_sku(bundle.claim_activations),
            matrix_index=_matrix_anchor_index(bundle.matrices),
        )

    def match(self, sku_code: str, rule: DimensionAssemblyRule, sku_distribution: Mapping[str, Any] | None = None) -> ProductAnchorMatch:
        spec = BATTLEFIELD_ANCHOR_SPECS.get(rule.code)
        if spec is None:
            return self._fallback_matrix_match(sku_code, rule.product_anchor_keywords, sku_distribution)
        param_hits = _dedupe_anchor_evidence(
            [
                evidence
                for param_rule in spec.param_rules
                for row in self.params_by_sku.get(sku_code, ())
                if row.param_code in param_rule.param_codes
                for evidence in [_param_anchor_evidence(row, param_rule)]
                if evidence is not None
            ]
        )
        direct_param_hits = tuple(
            hit for hit in param_hits if hit.usable_for_battlefield and hit.score > 0 and hit.strength not in {"proxy", "weak"}
        )
        proxy_param_hits = tuple(
            hit for hit in param_hits if hit.usable_for_battlefield and hit.score > 0 and hit.strength in {"proxy", "weak"}
        )
        claim_records: list[ProductAnchorEvidence] = []
        for claim_rule in spec.claim_rules:
            rule_claim_records = [
                evidence
                for evidence in [
                    *_claim_base_anchor_evidence(self.claim_bases_by_sku.get(sku_code, ()), claim_rule),
                    *_claim_anchor_evidence(self.claims_by_sku.get(sku_code, ()), claim_rule),
                ]
                if evidence is not None
            ]
            if claim_rule.requires_param_support and not _claim_has_param_support(claim_rule, direct_param_hits):
                rule_claim_records = [_downgrade_claim_without_param_support(evidence) for evidence in rule_claim_records]
            claim_records.extend(rule_claim_records)
        claim_hits = _dedupe_anchor_evidence(claim_records)
        comment_hits = _comment_anchor_hits(sku_code, rule, sku_distribution or {})
        market_hits = _market_anchor_hits(
            sku_code,
            self.market_profiles_by_sku.get(sku_code, ()),
            self.profiles_by_sku.get(sku_code),
        )
        matrix_hits = self._matrix_hits(sku_code, spec.matrix_keywords)
        param_anchor_score = _cap_anchor_score(direct_param_hits, Decimal("0.5500"))
        proxy_param_anchor_score = _cap_anchor_score(proxy_param_hits, Decimal("0.2500"))
        claim_anchor_score = _cap_anchor_score(claim_hits, Decimal("0.3500"))
        comment_validation_score = _cap_anchor_score(comment_hits, Decimal("0.1500"))
        market_anchor_score = _cap_anchor_score(market_hits, Decimal("0.1500"))
        matrix_anchor_score = _cap_anchor_score(matrix_hits, Decimal("0.1000"))
        raw_quality_flags = [
            flag
            for evidence in (*param_hits, *claim_hits, *comment_hits, *market_hits, *matrix_hits)
            for flag in evidence.quality_flags
        ]
        anchor_source_status = _anchor_source_status(
            param_anchor_score=param_anchor_score,
            proxy_param_anchor_score=proxy_param_anchor_score,
            claim_anchor_score=claim_anchor_score,
            comment_validation_score=comment_validation_score,
        )
        if matrix_hits and anchor_source_status in {"no_direct_anchor", "comment_only"}:
            raw_quality_flags.append("matrix_only_anchor")
        if comment_hits and anchor_source_status not in {"no_direct_anchor", "comment_only"}:
            raw_quality_flags.append("comment_validated")
        quality_flags = _unique_preserve_order(raw_quality_flags)
        overall_anchor_score = _layered_anchor_score(
            param_anchor_score=param_anchor_score,
            proxy_param_anchor_score=proxy_param_anchor_score,
            claim_anchor_score=claim_anchor_score,
            comment_validation_score=comment_validation_score,
            market_anchor_score=market_anchor_score,
            matrix_anchor_score=matrix_anchor_score,
            quality_flags=quality_flags,
        )
        return ProductAnchorMatch(
            sku_code=sku_code,
            score=overall_anchor_score,
            param_anchor_score=param_anchor_score,
            proxy_param_anchor_score=proxy_param_anchor_score,
            claim_anchor_score=claim_anchor_score,
            comment_validation_score=comment_validation_score,
            market_anchor_score=market_anchor_score,
            overall_anchor_score=overall_anchor_score,
            anchor_source_status=anchor_source_status,
            matrix_anchor_score=matrix_anchor_score,
            param_hits=tuple(param_hits),
            claim_hits=tuple(claim_hits),
            comment_hits=tuple(comment_hits),
            market_hits=tuple(market_hits),
            matrix_hits=tuple(matrix_hits),
            quality_flags=tuple(quality_flags),
        )

    def _fallback_matrix_match(
        self,
        sku_code: str,
        anchor_keywords: Sequence[str],
        sku_distribution: Mapping[str, Any] | None = None,
    ) -> ProductAnchorMatch:
        matrix_hits = self._matrix_hits(sku_code, anchor_keywords)
        matrix_anchor_score = _cap_anchor_score(matrix_hits, Decimal("0.1000"))
        comment_hits = _comment_anchor_hits(
            sku_code,
            DimensionAssemblyRule(
                dimension_type="fallback",
                code="fallback",
                name_cn="辅助锚点",
                definition_cn="无专用规则的辅助锚点。",
                required_signal_codes=(),
                product_anchor_keywords=tuple(anchor_keywords),
            ),
            sku_distribution or {},
        )
        comment_validation_score = _cap_anchor_score(comment_hits, Decimal("0.1500"))
        overall_anchor_score = _layered_anchor_score(
            param_anchor_score=Decimal("0.0000"),
            proxy_param_anchor_score=Decimal("0.0000"),
            claim_anchor_score=Decimal("0.0000"),
            comment_validation_score=comment_validation_score,
            market_anchor_score=Decimal("0.0000"),
            matrix_anchor_score=matrix_anchor_score,
            quality_flags=(),
        )
        return ProductAnchorMatch(
            sku_code=sku_code,
            score=overall_anchor_score,
            param_anchor_score=Decimal("0.0000"),
            proxy_param_anchor_score=Decimal("0.0000"),
            claim_anchor_score=Decimal("0.0000"),
            comment_validation_score=comment_validation_score,
            market_anchor_score=Decimal("0.0000"),
            overall_anchor_score=overall_anchor_score,
            anchor_source_status="comment_only" if comment_validation_score > 0 else "no_direct_anchor",
            matrix_anchor_score=matrix_anchor_score,
            comment_hits=tuple(comment_hits),
            matrix_hits=tuple(matrix_hits),
        )

    def _matrix_hits(self, sku_code: str, anchor_keywords: Sequence[str]) -> tuple[ProductAnchorEvidence, ...]:
        if not anchor_keywords:
            return ()
        matched = sorted(_matched_anchor_keywords(self.matrix_index.get(sku_code, ()), anchor_keywords))
        if not matched:
            return ()
        score = min(Decimal(len(matched)) * Decimal("0.0250"), Decimal("0.1000"))
        return (
            ProductAnchorEvidence(
                source_type="matrix",
                anchor_code="matrix_keyword",
                anchor_name_cn="M08 证据矩阵辅助锚点",
                anchor_group="matrix",
                raw_value=",".join(matched),
                score=score,
                strength="auxiliary",
                confidence=Decimal("0.5000"),
                usable_for_battlefield=True,
            ),
        )


def _candidate_product_anchor_by_sku(
    sku_distribution: Mapping[str, Any],
    product_anchor_index: ProductAnchorIndex,
    rule: DimensionAssemblyRule,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for sku_code, dist in sku_distribution.items():
        match = product_anchor_index.match(sku_code, rule, dist if isinstance(dist, Mapping) else {})
        if match.score <= 0 and not match.quality_flags:
            continue
        result[sku_code] = match.to_json()
    return result


def _comment_anchor_hits(
    sku_code: str,
    rule: DimensionAssemblyRule,
    sku_distribution: Mapping[str, Any],
) -> tuple[ProductAnchorEvidence, ...]:
    if rule.service_context or not sku_distribution:
        return ()
    sentence_count = int(sku_distribution.get("sentence_count") or 0)
    avg_strength = _decimal(sku_distribution.get("avg_strength"))
    if sentence_count <= 0 or avg_strength <= 0:
        return ()
    phrases = [str(item) for item in list(sku_distribution.get("phrases") or []) if item]
    phrase_text = " ".join(phrases).lower()
    keywords = tuple(rule.product_anchor_keywords or rule.source_signal_codes)
    matched_keywords = sorted(_matched_anchor_keywords([phrase_text], keywords))
    score = min(avg_strength * Decimal("0.1500"), Decimal("0.1500"))
    if not matched_keywords and rule.dimension_type == "native_product_value_battlefield":
        score = score * Decimal("0.6000")
    return (
        ProductAnchorEvidence(
            source_type="comment",
            anchor_code="comment_validation",
            anchor_name_cn="评论体验验证",
            anchor_group="comment",
            raw_value="；".join(phrases[:3]),
            normalized_value={
                "sentence_count": sentence_count,
                "avg_strength": float(avg_strength),
                "matched_keywords": matched_keywords,
            },
            score=_clamp(score),
            strength="validation" if matched_keywords else "weak_validation",
            confidence=_clamp(avg_strength),
            evidence_ids=tuple(str(item) for item in list(sku_distribution.get("evidence_ids") or [])[:10]),
            quality_flags=(),
            usable_for_battlefield=True,
        ),
    )


def _market_anchor_hits(
    sku_code: str,
    market_profiles: Sequence[entities.Core3SkuMarketProfile],
    profile: entities.Core3SkuSignalProfile | None,
) -> tuple[ProductAnchorEvidence, ...]:
    row = _best_market_profile(market_profiles)
    if row is not None:
        score = Decimal("0.0000")
        percentile_values = [
            _decimal_optional(row.sales_percentile),
            _decimal_optional(row.sales_amount_percentile),
            _decimal_optional(row.volume_percentile_in_category),
            _decimal_optional(row.amount_percentile_in_category),
            _decimal_optional(row.volume_percentile_in_size),
            _decimal_optional(row.amount_percentile_in_size),
            _decimal_optional(getattr(row, "same_pool_volume_percentile", None)),
            _decimal_optional(getattr(row, "same_pool_amount_percentile", None)),
        ]
        percentile = max((value for value in percentile_values if value is not None), default=None)
        if percentile is not None:
            score += min(max(percentile, Decimal("0.0000")), Decimal("1.0000")) * Decimal("0.1000")
        if any(
            value not in (None, "", "-")
            for value in (
                row.sales_volume_12m,
                row.sales_amount_12m,
                row.sales_volume_total,
                row.sales_amount_total,
                row.price_latest,
                row.price_wavg_12m,
            )
        ):
            score += Decimal("0.0500")
        score = min(score, Decimal("0.1500"))
        if score <= 0:
            return ()
        return (
            ProductAnchorEvidence(
                source_type="market",
                anchor_code="market_observable_position",
                anchor_name_cn="市场可观察位置",
                anchor_group="market",
                raw_value=str(row.analysis_window),
                normalized_value={
                    "analysis_window": row.analysis_window,
                    "price_band_category": row.price_band_category,
                    "price_band_size": row.price_band_size,
                    "screen_size_class": getattr(row, "screen_size_class", "unknown"),
                    "market_pool_key": getattr(row, "market_pool_key", None),
                    "same_pool_price_percentile": getattr(row, "same_pool_price_percentile", None),
                    "same_pool_volume_percentile": getattr(row, "same_pool_volume_percentile", None),
                    "same_pool_amount_percentile": getattr(row, "same_pool_amount_percentile", None),
                    "price_per_inch_percentile": getattr(row, "price_per_inch_percentile", None),
                    "sales_volume_12m": row.sales_volume_12m,
                    "sales_amount_12m": row.sales_amount_12m,
                    "sales_percentile": row.sales_percentile,
                    "sales_amount_percentile": row.sales_amount_percentile,
                    "market_confidence": float(_decimal(row.market_confidence)),
                },
                score=_clamp(score),
                strength="auxiliary",
                confidence=_decimal(row.market_confidence),
                evidence_ids=tuple(str(item) for item in [*list(row.evidence_ids or []), *list(row.market_evidence_ids or [])] if item),
                quality_flags=tuple(str(item) for item in list(row.quality_flags or [])),
                usable_for_battlefield=True,
            ),
        )
    market = (profile.market_summary_json if profile is not None else None) or {}
    if not market:
        return ()
    observable_keys = ("sales_volume_12m", "sales_amount_12m", "price_latest", "price_wavg_12m")
    observable_count = sum(1 for key in observable_keys if market.get(key) not in (None, "", "-"))
    if observable_count <= 0:
        return ()
    score = min(Decimal(observable_count) * Decimal("0.0300"), Decimal("0.1200"))
    return (
        ProductAnchorEvidence(
            source_type="market",
            anchor_code="market_summary_observable",
            anchor_name_cn="市场汇总可观察性",
            anchor_group="market",
            raw_value=str(sku_code),
            normalized_value={key: market.get(key) for key in observable_keys if market.get(key) not in (None, "", "-")},
            score=score,
            strength="auxiliary",
            confidence=Decimal("0.6000"),
            evidence_ids=(),
            quality_flags=(),
            usable_for_battlefield=True,
        ),
    )


def _best_market_profile(rows: Sequence[entities.Core3SkuMarketProfile]) -> entities.Core3SkuMarketProfile | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            Decimal("1.0000")
            if str(row.analysis_window or "").lower() in {"full", "full_window", "full_observed_window", "all"}
            else Decimal("0.0000"),
            _decimal(row.market_confidence),
        ),
        reverse=True,
    )[0]


def _decimal_optional(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    return _decimal(value)


def _anchor_source_status(
    *,
    param_anchor_score: Decimal,
    proxy_param_anchor_score: Decimal,
    claim_anchor_score: Decimal,
    comment_validation_score: Decimal,
) -> str:
    has_strong_param = param_anchor_score > 0
    has_proxy_param = proxy_param_anchor_score > 0
    has_claim = claim_anchor_score > 0
    has_comment = comment_validation_score > 0
    if (has_strong_param or has_proxy_param) and has_claim:
        return "claim_plus_param"
    if has_strong_param:
        return "param_only"
    if has_proxy_param:
        return "proxy_param_only"
    if has_claim:
        return "claim_only"
    if has_comment:
        return "comment_only"
    return "no_direct_anchor"


def _layered_anchor_score(
    *,
    param_anchor_score: Decimal,
    proxy_param_anchor_score: Decimal,
    claim_anchor_score: Decimal,
    comment_validation_score: Decimal,
    market_anchor_score: Decimal,
    matrix_anchor_score: Decimal,
    quality_flags: Sequence[str],
) -> Decimal:
    has_strong_param = param_anchor_score > 0
    has_proxy_param = proxy_param_anchor_score > 0
    has_claim = claim_anchor_score > 0
    has_comment = comment_validation_score > 0
    has_direct_anchor = has_strong_param or has_proxy_param or has_claim
    dirty_without_direct_anchor = (not has_direct_anchor) and any(
        flag in {"param_mapping_suspect", "invalid_param_value"} for flag in quality_flags
    )
    if has_strong_param:
        claim_multiplier = Decimal("1.0000")
        comment_multiplier = Decimal("0.8000")
        market_multiplier = Decimal("0.6000")
    elif has_proxy_param:
        claim_multiplier = Decimal("0.8500")
        comment_multiplier = Decimal("0.6000")
        market_multiplier = Decimal("0.5000")
    elif has_claim:
        claim_multiplier = Decimal("0.6500")
        comment_multiplier = Decimal("0.5000")
        market_multiplier = Decimal("0.4000")
    elif has_comment and not dirty_without_direct_anchor:
        claim_multiplier = Decimal("0.0000")
        comment_multiplier = Decimal("0.0000")
        market_multiplier = Decimal("0.0000")
    else:
        claim_multiplier = Decimal("0.0000")
        comment_multiplier = Decimal("0.0000")
        market_multiplier = Decimal("0.0000")
    matrix_bonus = min(matrix_anchor_score * Decimal("0.5000"), Decimal("0.0500")) if has_direct_anchor else Decimal("0.0000")
    return _clamp(
        param_anchor_score
        + proxy_param_anchor_score * Decimal("0.7000")
        + claim_anchor_score * claim_multiplier
        + comment_validation_score * comment_multiplier
        + market_anchor_score * market_multiplier
        + matrix_bonus
    )


def _anchor_quality_summary(product_anchor_by_sku: Mapping[str, Any], sku_count: int) -> dict[str, Any]:
    valid_param_sku_count = 0
    valid_proxy_param_sku_count = 0
    valid_claim_sku_count = 0
    comment_validated_sku_count = 0
    market_anchor_sku_count = 0
    dirty_param_sku_count = 0
    matrix_only_sku_count = 0
    quality_flags: list[str] = []
    source_status_count: dict[str, int] = defaultdict(int)
    for payload in product_anchor_by_sku.values():
        param_hits = list(payload.get("param_hits") or [])
        claim_hits = list(payload.get("claim_hits") or [])
        comment_hits = list(payload.get("comment_hits") or [])
        market_hits = list(payload.get("market_hits") or [])
        matrix_hits = list(payload.get("matrix_hits") or [])
        status = str(payload.get("anchor_source_status") or "unknown")
        source_status_count[status] = source_status_count.get(status, 0) + 1
        if _decimal(payload.get("param_anchor_score")) > 0 or any(
            _decimal(hit.get("score")) > 0 and hit.get("strength") not in {"proxy", "weak"} for hit in param_hits
        ):
            valid_param_sku_count += 1
        if _decimal(payload.get("proxy_param_anchor_score")) > 0:
            valid_proxy_param_sku_count += 1
        if any(_decimal(hit.get("score")) > 0 for hit in claim_hits):
            valid_claim_sku_count += 1
        if status not in {"comment_only", "no_direct_anchor"} and any(_decimal(hit.get("score")) > 0 for hit in comment_hits):
            comment_validated_sku_count += 1
        if any(_decimal(hit.get("score")) > 0 for hit in market_hits):
            market_anchor_sku_count += 1
        flags = list(payload.get("quality_flags") or [])
        quality_flags.extend(str(flag) for flag in flags)
        if "param_mapping_suspect" in flags:
            dirty_param_sku_count += 1
        if _anchor_payload_score(payload) <= 0 and matrix_hits:
            matrix_only_sku_count += 1
    return {
        "covered_sku_count": int(sku_count),
        "anchor_sku_count": len(product_anchor_by_sku),
        "valid_param_sku_count": valid_param_sku_count,
        "valid_proxy_param_sku_count": valid_proxy_param_sku_count,
        "valid_claim_sku_count": valid_claim_sku_count,
        "comment_validated_sku_count": comment_validated_sku_count,
        "market_anchor_sku_count": market_anchor_sku_count,
        "dirty_param_sku_count": dirty_param_sku_count,
        "matrix_only_sku_count": matrix_only_sku_count,
        "anchor_source_status_count": dict(sorted(source_status_count.items())),
        "quality_flags": _unique_preserve_order(quality_flags),
    }


def _group_by_sku(rows: Sequence[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = defaultdict(list)
    for row in rows:
        sku_code = str(getattr(row, "sku_code", "") or "")
        if sku_code:
            result[sku_code].append(row)
    return result


def _param_anchor_evidence(
    row: entities.Core3ExtractParamValue,
    rule: ParamAnchorRule,
) -> ProductAnchorEvidence | None:
    value_text = _param_value_text(row)
    raw_name = str(row.raw_param_name or row.param_name or "")
    raw_value = str(row.raw_param_value or row.value_text or "")
    quality_flags: list[str] = []
    if _is_invalid_anchor_value(value_text):
        quality_flags.append("invalid_param_value")
    if _param_raw_name_suspect(raw_name, rule):
        quality_flags.append("param_mapping_suspect")
    if bool(row.conflict_flag) or bool(row.review_required) or str(row.confidence_level or "").lower() == "low":
        quality_flags.append("param_quality_review")
    value_matched = _param_rule_value_matches(row, rule, value_text)
    hard_blocked = any(flag in quality_flags for flag in ("invalid_param_value", "param_mapping_suspect"))
    if not value_matched and not hard_blocked:
        return None
    score = Decimal("0.0000")
    usable = value_matched and not hard_blocked
    if usable:
        score = rule.score
        if "param_quality_review" in quality_flags:
            score = score * Decimal("0.5000")
    return ProductAnchorEvidence(
        source_type="param",
        anchor_code=str(row.param_code),
        anchor_name_cn=str(row.param_name or row.param_code),
        anchor_group=str(row.param_group or "param"),
        raw_name=raw_name,
        raw_value=raw_value,
        normalized_value=row.normalized_value,
        score=_clamp(score),
        strength=rule.strength if usable else "blocked",
        confidence=_decimal(row.confidence),
        evidence_ids=tuple(str(item) for item in (row.evidence_ids or [])),
        quality_flags=tuple(_unique_preserve_order(quality_flags)),
        usable_for_battlefield=usable,
    )


def _claim_base_anchor_evidence(
    rows: Sequence[entities.Core3SkuClaimActivationBase],
    rule: ClaimAnchorRule,
) -> list[ProductAnchorEvidence]:
    result: list[ProductAnchorEvidence] = []
    for row in rows:
        if row.claim_code not in rule.claim_codes:
            continue
        result.append(
            _claim_like_anchor_evidence(
                claim_code=row.claim_code,
                claim_name=row.claim_name,
                claim_group=row.claim_group,
                activation_basis=row.activation_basis,
                score_value=_decimal(row.base_activation_score),
                confidence=_decimal(row.confidence),
                review_required=bool(row.review_required),
                quality_flags=list(row.conflict_flags or []),
                evidence_ids=[*list(row.evidence_ids or []), *list(row.param_evidence_ids or []), *list(row.promo_evidence_ids or [])],
                rule=rule,
                source_type="claim_base",
            )
        )
    return [item for item in result if item is not None]


def _claim_anchor_evidence(
    rows: Sequence[entities.Core3SkuClaimActivation],
    rule: ClaimAnchorRule,
) -> list[ProductAnchorEvidence]:
    result: list[ProductAnchorEvidence] = []
    for row in rows:
        if row.claim_code not in rule.claim_codes:
            continue
        flags = list(row.quality_flags or []) + list(row.conflict_flags or [])
        if bool(row.service_guardrail_flag):
            flags.append("service_guardrail")
        if bool(row.contradiction_flag):
            flags.append("claim_contradiction")
        result.append(
            _claim_like_anchor_evidence(
                claim_code=row.claim_code,
                claim_name=row.claim_name,
                claim_group=row.claim_group,
                activation_basis=row.activation_basis,
                score_value=max(_decimal(row.final_activation_score), _decimal(row.base_activation_score)),
                confidence=_decimal(row.confidence),
                review_required=bool(row.review_required),
                quality_flags=flags,
                evidence_ids=[
                    *list(row.evidence_ids or []),
                    *list(row.param_evidence_ids or []),
                    *list(row.promo_evidence_ids or []),
                    *list(row.comment_evidence_ids or []),
                ],
                rule=rule,
                source_type="claim",
            )
        )
    return [item for item in result if item is not None]


def _claim_has_param_support(
    rule: ClaimAnchorRule,
    direct_param_hits: Sequence[ProductAnchorEvidence],
) -> bool:
    if not rule.requires_param_support:
        return True
    usable_param_codes = {
        hit.anchor_code
        for hit in direct_param_hits
        if hit.usable_for_battlefield and hit.score > 0
    }
    if not usable_param_codes:
        return False
    if not rule.support_param_codes:
        return True
    return any(param_code in usable_param_codes for param_code in rule.support_param_codes)


def _downgrade_claim_without_param_support(record: ProductAnchorEvidence) -> ProductAnchorEvidence:
    normalized_value = dict(record.normalized_value) if isinstance(record.normalized_value, Mapping) else {}
    normalized_value["param_support_required"] = True
    return ProductAnchorEvidence(
        source_type=record.source_type,
        anchor_code=record.anchor_code,
        anchor_name_cn=record.anchor_name_cn,
        anchor_group=record.anchor_group,
        raw_name=record.raw_name,
        raw_value=record.raw_value,
        normalized_value=normalized_value,
        score=Decimal("0.0000"),
        strength="blocked",
        confidence=record.confidence,
        evidence_ids=record.evidence_ids,
        quality_flags=tuple(_unique_preserve_order([*record.quality_flags, "claim_requires_param_anchor"])),
        usable_for_battlefield=False,
    )


def _claim_like_anchor_evidence(
    *,
    claim_code: str,
    claim_name: str,
    claim_group: str,
    activation_basis: str,
    score_value: Decimal,
    confidence: Decimal,
    review_required: bool,
    quality_flags: list[str],
    evidence_ids: Sequence[str],
    rule: ClaimAnchorRule,
    source_type: str,
) -> ProductAnchorEvidence | None:
    normalized_basis = str(activation_basis or "unknown")
    flags = list(quality_flags)
    if normalized_basis == "insufficient":
        flags.append("claim_insufficient")
    if review_required:
        flags.append("claim_review_required")
    if score_value < rule.min_score:
        flags.append("claim_anchor_weak")
    hard_blocked = any(flag in flags for flag in ("service_guardrail", "claim_contradiction", "claim_insufficient"))
    if score_value < rule.min_score and hard_blocked:
        return None
    basis_factor = _claim_basis_factor(normalized_basis)
    usable = score_value >= rule.min_score and not hard_blocked
    score = _clamp(rule.score * basis_factor) if usable else Decimal("0.0000")
    if usable and "claim_review_required" in flags:
        score = score * Decimal("0.5000")
    return ProductAnchorEvidence(
        source_type=source_type,
        anchor_code=str(claim_code),
        anchor_name_cn=str(claim_name or claim_code),
        anchor_group=str(claim_group or "claim"),
        raw_name=str(claim_name or claim_code),
        raw_value=normalized_basis,
        normalized_value={"activation_score": float(score_value), "activation_basis": normalized_basis},
        score=_clamp(score),
        strength=rule.strength if usable else "weak",
        confidence=confidence,
        evidence_ids=tuple(str(item) for item in evidence_ids if item),
        quality_flags=tuple(_unique_preserve_order(flags)),
        usable_for_battlefield=usable,
    )


def _claim_basis_factor(activation_basis: str) -> Decimal:
    return {
        "param_and_promo": Decimal("1.0000"),
        "param_only": Decimal("0.9500"),
        "promo_only": Decimal("0.7000"),
        "comment_enhanced": Decimal("0.4500"),
        "comment_weakened": Decimal("0.2500"),
    }.get(activation_basis, Decimal("0.5000"))


def _param_rule_value_matches(row: entities.Core3ExtractParamValue, rule: ParamAnchorRule, value_text: str) -> bool:
    checks: list[bool] = []
    if rule.min_numeric is not None:
        numeric_value = _param_numeric_value(row, value_text)
        checks.append(numeric_value is not None and numeric_value >= rule.min_numeric)
    if rule.value_keywords:
        lowered = value_text.lower()
        checks.append(any(keyword.lower() in lowered for keyword in rule.value_keywords))
    if not checks:
        checks.append(not _is_invalid_anchor_value(value_text))
    return any(checks)


def _param_numeric_value(row: entities.Core3ExtractParamValue, value_text: str) -> Decimal | None:
    if row.numeric_value is not None:
        return _decimal(row.numeric_value)
    match = re.search(r"\d+(?:\.\d+)?", value_text)
    if not match:
        return None
    return _decimal(match.group(0))


def _param_value_text(row: entities.Core3ExtractParamValue) -> str:
    values = [
        row.value_text,
        row.raw_param_value,
        str(row.numeric_value) if row.numeric_value is not None else None,
        _json_scalar_text(row.normalized_value),
    ]
    return " ".join(str(value) for value in values if value not in (None, ""))


def _json_scalar_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool, Decimal)):
        return str(value)
    if isinstance(value, Mapping):
        return " ".join(str(item) for item in value.values() if item not in (None, ""))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(str(item) for item in value if item not in (None, ""))
    return str(value)


def _is_invalid_anchor_value(value_text: str) -> bool:
    normalized = value_text.strip().lower()
    return normalized in {"", "-", "--", "未知", "无", "不详", "n/a", "na", "none", "null"}


def _param_raw_name_suspect(raw_name: str, rule: ParamAnchorRule) -> bool:
    normalized = raw_name.strip().lower().replace(" ", "")
    if not normalized:
        return False
    if any(keyword.lower().replace(" ", "") in normalized for keyword in rule.invalid_raw_name_keywords):
        return True
    if rule.valid_raw_name_keywords and not any(
        keyword.lower().replace(" ", "") in normalized for keyword in rule.valid_raw_name_keywords
    ):
        return True
    return False


def _dedupe_anchor_evidence(records: Sequence[ProductAnchorEvidence]) -> tuple[ProductAnchorEvidence, ...]:
    by_code: dict[tuple[str, str], ProductAnchorEvidence] = {}
    for record in records:
        key = ("claim" if record.source_type in {"claim", "claim_base"} else record.source_type, record.anchor_code)
        existing = by_code.get(key)
        if existing is None or record.score > existing.score:
            by_code[key] = record
        elif existing is not None and record.quality_flags:
            by_code[key] = _merge_anchor_quality(existing, record)
    return tuple(sorted(by_code.values(), key=lambda item: (item.source_type, item.anchor_code)))


def _merge_anchor_quality(left: ProductAnchorEvidence, right: ProductAnchorEvidence) -> ProductAnchorEvidence:
    return ProductAnchorEvidence(
        source_type=left.source_type,
        anchor_code=left.anchor_code,
        anchor_name_cn=left.anchor_name_cn,
        anchor_group=left.anchor_group,
        raw_name=left.raw_name,
        raw_value=left.raw_value,
        normalized_value=left.normalized_value,
        score=left.score,
        strength=left.strength,
        confidence=left.confidence,
        evidence_ids=tuple(_unique_preserve_order([*left.evidence_ids, *right.evidence_ids])),
        quality_flags=tuple(_unique_preserve_order([*left.quality_flags, *right.quality_flags])),
        usable_for_battlefield=left.usable_for_battlefield,
    )


def _cap_anchor_score(records: Sequence[ProductAnchorEvidence], cap: Decimal) -> Decimal:
    total = sum((record.score for record in records if record.usable_for_battlefield), Decimal("0.0000"))
    return _clamp(min(total, cap))


def _anchor_evidence_json(record: ProductAnchorEvidence) -> dict[str, Any]:
    return {
        "source_type": record.source_type,
        "anchor_code": record.anchor_code,
        "anchor_name_cn": record.anchor_name_cn,
        "anchor_group": record.anchor_group,
        "raw_name": record.raw_name,
        "raw_value": record.raw_value,
        "normalized_value": record.normalized_value,
        "score": float(record.score),
        "strength": record.strength,
        "confidence": float(record.confidence),
        "evidence_ids": list(record.evidence_ids),
        "quality_flags": list(record.quality_flags),
        "usable_for_battlefield": record.usable_for_battlefield,
    }


def _unique_preserve_order(values: Sequence[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _candidate_product_anchor_score_from_distribution(
    product_anchor_by_sku: Mapping[str, Any],
    *,
    sku_count: int,
    dimension_type: str,
    service_context: bool,
) -> Decimal:
    if service_context or dimension_type in {"service_context", "risk_context", "purchase_motive"}:
        return Decimal("0.0000")
    if sku_count <= 0:
        return Decimal("0.0000")
    score_sum = sum(_anchor_payload_score(value) for value in product_anchor_by_sku.values())
    return _clamp(score_sum / Decimal(sku_count))


def _anchor_payload_score(value: Any) -> Decimal:
    if not isinstance(value, Mapping):
        return Decimal("0.0000")
    return _decimal(value.get("overall_anchor_score", value.get("score")))


def _dimension_support_score(
    *,
    dimension_type: str,
    avg_strength_score: Decimal,
    product_anchor_score: Decimal,
    distinctiveness_score: Decimal,
    evidence_diversity_score: Decimal,
) -> Decimal:
    if dimension_type == "native_product_value_battlefield":
        return _weighted_score(
            (avg_strength_score, Decimal("0.35")),
            (product_anchor_score, Decimal("0.35")),
            (distinctiveness_score, Decimal("0.15")),
            (evidence_diversity_score, Decimal("0.15")),
        )
    if dimension_type in {"native_task", "native_target_group"}:
        return _weighted_score(
            (avg_strength_score, Decimal("0.55")),
            (distinctiveness_score, Decimal("0.20")),
            (evidence_diversity_score, Decimal("0.15")),
            (product_anchor_score, Decimal("0.10")),
        )
    return _weighted_score(
        (avg_strength_score, Decimal("0.70")),
        (distinctiveness_score, Decimal("0.15")),
        (evidence_diversity_score, Decimal("0.15")),
    )


def _sku_dimension_support_score(
    *,
    dimension_type: str,
    comment_support: Decimal,
    product_anchor: Decimal,
    market_anchor: Decimal,
) -> Decimal:
    if dimension_type == "native_product_value_battlefield":
        return _weighted_score(
            (comment_support, Decimal("0.45")),
            (product_anchor, Decimal("0.40")),
            (market_anchor, Decimal("0.15")),
        )
    if dimension_type in {"native_task", "native_target_group"}:
        return _weighted_score(
            (comment_support, Decimal("0.65")),
            (product_anchor, Decimal("0.15")),
            (market_anchor, Decimal("0.20")),
        )
    return _weighted_score(
        (comment_support, Decimal("0.85")),
        (market_anchor, Decimal("0.15")),
    )


def _candidate_include_keywords(
    rule: DimensionAssemblyRule,
    signals: Sequence[M084NativeSignalRecord],
) -> dict[str, Any]:
    matched: set[str] = set()
    rule_keywords: set[str] = set()
    for signal in signals:
        keywords = signal.native_keyword_json or {}
        matched.update(str(item) for item in keywords.get("matched") or [])
        rule_keywords.update(str(item) for item in keywords.get("rule_keywords") or [])
    return {
        "assembly_rule": rule.code,
        "source_signal_codes": [signal.native_signal_code for signal in signals],
        "required_signal_codes": list(rule.required_signal_codes),
        "optional_signal_codes": list(rule.optional_signal_codes),
        "atomic_signal_families": {signal.native_signal_code: signal.signal_type for signal in signals},
        "matched": sorted(matched),
        "rule_keywords": sorted(rule_keywords),
        "product_anchor_keywords": list(rule.product_anchor_keywords),
    }


def _merge_representative_phrases(signals: Sequence[M084NativeSignalRecord]) -> list[Any]:
    phrases: list[Any] = []
    for signal in signals:
        _extend_unique(phrases, signal.representative_phrase_json or [], limit=8)
    return phrases


def _merge_representative_evidence_ids(signals: Sequence[M084NativeSignalRecord]) -> list[str]:
    evidence_ids: list[str] = []
    for signal in signals:
        _extend_unique(evidence_ids, list(signal.representative_evidence_ids or []), limit=20)
    return evidence_ids


def _extend_unique(target: list[Any], values: Sequence[Any], *, limit: int) -> None:
    seen = {str(item) for item in target}
    for value in values:
        key = str(value)
        if not key or key in seen:
            continue
        seen.add(key)
        target.append(value)
        if len(target) >= limit:
            break


def _matches_rule(text: str, rule: NativeSignalRule) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in rule.keywords)


def _hit_strength(atom: entities.Core3CommentEvidenceAtom, rule: NativeSignalRule) -> Decimal:
    strength = Decimal("0.4500")
    strength += _decimal(atom.specificity_score) * Decimal("0.2500")
    strength += _decimal(atom.confidence) * Decimal("0.2000")
    if str(atom.sentiment_hint) == "positive":
        strength += Decimal("0.0700")
    if str(atom.sentiment_hint) == "negative" and rule.negative_context:
        strength += Decimal("0.0700")
    if rule.service_context and str(atom.primary_domain_hint) in {"service_experience", "logistics_installation"}:
        strength += Decimal("0.0800")
    return _clamp(strength)


def _text(atom: entities.Core3CommentEvidenceAtom) -> str:
    return " ".join(
        item
        for item in (
            atom.sentence_text or "",
            atom.normalized_sentence_text or "",
            atom.representative_phrase or "",
        )
        if item
    )


def _matched_keywords_for_hits(hits: Sequence[SignalHit]) -> list[str]:
    text = " ".join(_text(hit.atom).lower() for hit in hits)
    keywords: set[str] = set()
    for hit in hits:
        keywords.update(keyword for keyword in hit.rule.keywords if keyword.lower() in text)
    return sorted(keywords)


def _sku_distribution(hits: Sequence[SignalHit]) -> dict[str, dict[str, Any]]:
    by_sku: dict[str, list[SignalHit]] = defaultdict(list)
    for hit in hits:
        by_sku[hit.atom.sku_code].append(hit)
    return {
        sku_code: {
            "sentence_count": len(items),
            "avg_strength": float(_avg(item.strength for item in items)),
            "evidence_ids": _representative_evidence_ids(item.atom for item in items),
            "phrases": _representative_phrases(item.atom for item in items),
        }
        for sku_code, items in sorted(by_sku.items())
    }


def _matrix_anchor_index(matrices: Sequence[entities.Core3SkuSignalEvidenceMatrix]) -> dict[str, tuple[str, ...]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in matrices:
        values = [
            str(row.domain or ""),
            str(row.sub_domain or ""),
            str(row.feature_code or ""),
            " ".join(str(item) for item in (row.representative_evidence_ids or [])),
        ]
        result[row.sku_code].update(_normalize_token(value) for value in values if value)
    return {sku_code: tuple(sorted(values)) for sku_code, values in result.items()}


def _matched_anchor_keywords(features: Iterable[str], anchor_keywords: Sequence[str]) -> set[str]:
    feature_text = " ".join(features).lower()
    return {keyword for keyword in anchor_keywords if keyword.lower() in feature_text}


def _sku_product_anchor_score(features: Sequence[str], anchor_keywords: Sequence[str]) -> Decimal:
    if not anchor_keywords:
        return Decimal("0.0000")
    matched = _matched_anchor_keywords(features, anchor_keywords)
    if not matched:
        return Decimal("0.0000")
    return _clamp(Decimal(len(matched)) / Decimal(max(len(anchor_keywords), 1)) + Decimal("0.2500"))


def _market_anchor_index(profiles: Sequence[entities.Core3SkuSignalProfile]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for profile in profiles:
        market = profile.market_summary_json or {}
        if not market:
            result[profile.sku_code] = Decimal("0.0000")
            continue
        score = Decimal("0.2000")
        for key in ("sales_volume_12m", "sales_amount_12m", "price_latest", "price_wavg_12m"):
            if market.get(key) not in (None, "", "-"):
                score += Decimal("0.1000")
        result[profile.sku_code] = _clamp(score)
    return result


def _signal_distribution_from_candidates(candidates: Sequence[M084NativeDimensionCandidateRecord]) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate in candidates:
        source = candidate.support_summary_json.get("sku_distribution") or {}
        result[candidate.native_dimension_code] = dict(source)
    return result


def _source_signal_code(candidate: M084NativeDimensionCandidateRecord) -> str:
    return str((candidate.source_signal_codes or [""])[0])


def _rule(code: str) -> NativeSignalRule | None:
    return next((rule for rule in NATIVE_SIGNAL_RULES if rule.code == code), None)


def _seed_rows(seed: M085DimensionSeed) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in seed.tasks:
        rows.append(_seed_row(row, "task", "task_code", "task_name"))
    for row in seed.target_groups:
        rows.append(_seed_row(row, "target_group", "target_group_code", "target_group_name"))
    for row in seed.battlefields:
        rows.append(_seed_row(row, "battlefield", "battlefield_code", "battlefield_name"))
    return rows


def _seed_row(row: Mapping[str, Any], dimension_type: str, code_key: str, name_key: str) -> dict[str, Any]:
    return {
        "type": dimension_type,
        "code": row.get(code_key),
        "name": row.get(name_key),
        "definition": row.get("definition") or "",
        "keywords": list(row.get("keywords") or []) + list(row.get("aliases") or []),
    }


def _find_seed(seed_rows: Sequence[Mapping[str, Any]], dimension_type: str, code: str) -> Mapping[str, Any] | None:
    return next((row for row in seed_rows if row["type"] == dimension_type and row["code"] == code), None)


def _best_seed_match(
    candidate: M084NativeDimensionCandidateRecord,
    seed_rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, Decimal]:
    candidate_tokens = _candidate_tokens(candidate)
    best_row: Mapping[str, Any] | None = None
    best_score = Decimal("0.0000")
    for row in seed_rows:
        seed_tokens = _seed_tokens(row)
        score = _overlap_score(candidate_tokens, seed_tokens)
        if score > best_score:
            best_score = score
            best_row = row
    return best_row, best_score


def _seed_matches_for_candidate(
    candidate: M084NativeDimensionCandidateRecord,
    seed_rows: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], Decimal], ...]:
    candidate_tokens = _candidate_tokens(candidate)
    scored: list[tuple[Mapping[str, Any], Decimal]] = []
    for row in seed_rows:
        score = _overlap_score(candidate_tokens, _seed_tokens(row))
        if score < Decimal("0.2600"):
            continue
        scored.append((row, score))
    scored.sort(key=lambda item: (item[1], str(item[0].get("code") or "")), reverse=True)
    if not scored:
        return ()

    best_row, best_score = scored[0]
    matches: list[tuple[Mapping[str, Any], Decimal]] = [(best_row, best_score)]
    if candidate.dimension_type != "native_product_value_battlefield":
        return tuple(matches)

    matched_codes = {str(best_row.get("code") or "")}
    for row, score in scored[1:]:
        seed_code = str(row.get("code") or "")
        if seed_code in matched_codes:
            continue
        if score < Decimal("0.5500"):
            continue
        matched_codes.add(seed_code)
        matches.append((row, score))
    return tuple(matches)


def _candidate_tokens(candidate: M084NativeDimensionCandidateRecord) -> set[str]:
    values: list[str] = [
        candidate.native_dimension_code,
        candidate.native_dimension_name_cn,
        candidate.definition_draft_cn,
        " ".join(candidate.source_signal_codes or []),
    ]
    values.extend(candidate.include_keyword_json.get("matched") or [])
    values.extend(candidate.include_keyword_json.get("rule_keywords") or [])
    return _tokens(values)


def _seed_tokens(row: Mapping[str, Any]) -> set[str]:
    return _tokens([str(row.get("code") or ""), str(row.get("name") or ""), str(row.get("definition") or ""), *(row.get("keywords") or [])])


def _tokens(values: Iterable[str]) -> set[str]:
    text = " ".join(str(value).lower() for value in values if value)
    latin_tokens = set(re.findall(r"[a-z0-9_]+", text))
    cjk_tokens = {token for token in _CJK_BUSINESS_TOKENS if token in text}
    return latin_tokens | cjk_tokens


_CJK_BUSINESS_TOKENS = {
    "画质",
    "清晰",
    "亮度",
    "色彩",
    "音质",
    "音效",
    "影院",
    "游戏",
    "体育",
    "高刷",
    "客厅",
    "家庭",
    "大屏",
    "换新",
    "老人",
    "长辈",
    "父母",
    "儿童",
    "孩子",
    "护眼",
    "智能",
    "语音",
    "系统",
    "装修",
    "新家",
    "价格",
    "性价比",
    "安装",
    "配送",
    "售后",
    "卡顿",
    "故障",
}


def _overlap_score(candidate_tokens: set[str], seed_tokens: set[str]) -> Decimal:
    if not candidate_tokens or not seed_tokens:
        return Decimal("0.0000")
    overlap = candidate_tokens & seed_tokens
    score = Decimal(len(overlap)) / Decimal(max(min(len(candidate_tokens), len(seed_tokens)), 1))
    return _clamp(score)


def _compatible_dimension_type(candidate_type: str, seed_type: str) -> bool:
    return {
        "native_task": "task",
        "native_target_group": "target_group",
        "native_product_value_battlefield": "battlefield",
    }.get(candidate_type) == seed_type


def _seed_type_for_candidate(candidate_type: str) -> str:
    return {
        "native_task": "task",
        "native_target_group": "target_group",
        "native_product_value_battlefield": "battlefield",
        "purchase_motive": "purchase_motive",
        "service_context": "service_context",
        "risk_context": "risk_context",
    }.get(candidate_type, candidate_type)


def _dimension_name(dimension_type: str, signal_name: str) -> str:
    prefix = {
        "native_task": "任务",
        "native_target_group": "客群",
        "native_product_value_battlefield": "产品价值",
        "purchase_motive": "购买动机",
        "service_context": "服务语境",
        "risk_context": "风险语境",
    }.get(dimension_type, "维度")
    return f"{prefix}：{signal_name}"


def _dimension_definition(dimension_type: str, signal_name: str, signal: M084NativeSignalRecord) -> str:
    if dimension_type == "service_context":
        return f"用户在评论中提到{signal_name}，用于识别履约服务体验，不参与产品价值战场分类。"
    if dimension_type == "risk_context":
        return f"用户在评论中提到{signal_name}，用于识别体验风险和复核提示，不直接作为正向业务定位。"
    if dimension_type == "purchase_motive":
        return f"用户因{signal_name}形成购买、换新或预算选择动机。"
    return f"用户围绕{signal_name}形成稳定业务语义，可作为后续任务、客群或产品价值战场的候选边界。"


def _candidate_exclude_keywords(dimension_type: str) -> dict[str, Any]:
    if dimension_type == "native_product_value_battlefield":
        return {"service_context": ["安装", "配送", "售后", "客服", "物流"]}
    return {}


def _candidate_status(
    score: Decimal,
    anchor: Decimal,
    *,
    service_context_flag: bool,
    dimension_type: str,
) -> str:
    if service_context_flag:
        return "service_context_only"
    if dimension_type == "native_product_value_battlefield" and anchor < Decimal("0.3000"):
        return "candidate_review"
    if score >= Decimal("0.6500"):
        return "strong_candidate"
    if score >= Decimal("0.4500") or anchor >= Decimal("0.5000"):
        return "candidate"
    return "weak_candidate"


def _support_level(score: Decimal) -> str:
    if score >= Decimal("0.7000"):
        return "strong"
    if score >= Decimal("0.5000"):
        return "medium"
    if score >= Decimal("0.3000"):
        return "weak"
    return "trace"


def _support_reason(candidate: M084NativeDimensionCandidateRecord, comment: Decimal, product: Decimal, market: Decimal) -> str:
    parts = [f"评论支撑 {comment:.2f}"]
    if product > 0:
        parts.append(f"参数/卖点锚点 {product:.2f}")
    if market > 0:
        parts.append(f"市场数据锚点 {market:.2f}")
    return f"{candidate.native_dimension_name_cn}：" + "，".join(parts)


def _signal_review_reason(rule: NativeSignalRule) -> dict[str, Any]:
    if rule.service_context:
        return {"reason": "service_context_only", "message_cn": "服务履约不作为产品价值战场。"}
    if rule.negative_context:
        return {"reason": "risk_context", "message_cn": "负向风险只作复核提示。"}
    return {}


def _candidate_review_required(rule: DimensionAssemblyRule, product_anchor_score: Decimal) -> bool:
    if rule.service_context:
        return True
    return (
        rule.dimension_type == "native_product_value_battlefield"
        and rule.review_if_missing_anchor
        and product_anchor_score < Decimal("0.3000")
    )


def _candidate_review_reason(
    rule: DimensionAssemblyRule,
    product_anchor_score: Decimal,
    *,
    anchor_quality_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if rule.service_context:
        return {"reason": "service_context_only"}
    if rule.dimension_type == "native_product_value_battlefield" and product_anchor_score < Decimal("0.3000"):
        anchor_quality_summary = anchor_quality_summary or {}
        has_any_anchor = _has_effective_anchor(anchor_quality_summary)
        return {
            "reason": "weak_product_anchor" if has_any_anchor else "missing_product_anchor",
            "required_anchor_keywords": list(rule.product_anchor_keywords),
            "threshold": 0.3,
            **anchor_quality_summary,
        }
    return {}


def _has_effective_anchor(anchor_quality_summary: Mapping[str, Any]) -> bool:
    return (
        int(anchor_quality_summary.get("valid_param_sku_count") or 0)
        + int(anchor_quality_summary.get("valid_proxy_param_sku_count") or 0)
        + int(anchor_quality_summary.get("valid_claim_sku_count") or 0)
        + int(anchor_quality_summary.get("comment_validated_sku_count") or 0)
    ) > 0


def _dedupe_issues(issues: Sequence[M084ReviewIssueRecord]) -> list[M084ReviewIssueRecord]:
    result: dict[str, M084ReviewIssueRecord] = {}
    for issue in issues:
        result.setdefault(issue.issue_key, issue)
    return list(result.values())


def _summary(
    *,
    bundle: M084InputBundle,
    signals: Sequence[M084NativeSignalRecord],
    candidates: Sequence[M084NativeDimensionCandidateRecord],
    supports: Sequence[M084SkuSupportRecord],
    alignments: Sequence[M084AlignmentProposalRecord],
    issues: Sequence[M084ReviewIssueRecord],
    write_summary: dict[str, dict[str, int]],
) -> dict[str, Any]:
    by_type: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        by_type[candidate.dimension_type] += 1
    service_count = sum(1 for candidate in candidates if candidate.service_context_flag)
    return {
        "input_sku_count": len(bundle.profiles),
        "usable_comment_atom_count": len(bundle.comment_atoms),
        "m06_signal_count": len(bundle.downstream_signals),
        "native_signal_count": len(signals),
        "native_dimension_count": len(candidates),
        "native_dimension_count_by_type": dict(sorted(by_type.items())),
        "sku_support_count": len(supports),
        "alignment_proposal_count": len(alignments),
        "review_issue_count": len(issues),
        "service_context_candidate_count": service_count,
        "product_value_candidate_count": by_type.get("native_product_value_battlefield", 0),
        "write_summary": write_summary,
    }


def _warnings(summary: Mapping[str, Any]) -> list[str]:
    warnings: list[str] = []
    if int(summary.get("usable_comment_atom_count") or 0) == 0:
        warnings.append("M08.4 未发现可下游消费的代表评论，无法从评论中发现原生业务维度。")
    if int(summary.get("native_dimension_count") or 0) == 0:
        warnings.append("M08.4 未生成原生业务维度候选，后续 M08.5 只能依赖预设和非评论证据。")
    if int(summary.get("service_context_candidate_count") or 0) > 0:
        warnings.append("M08.4 发现服务履约语境，已标记为 service_context，后续不得作为产品价值战场。")
    return warnings


def _write_result_dict(write_result: Any) -> dict[str, int]:
    return {
        "created_count": int(write_result.created_count),
        "reused_count": int(write_result.reused_count),
        "updated_count": int(write_result.updated_count),
        "record_count": len(write_result.records),
    }


def _representative_phrases(atoms: Iterable[entities.Core3CommentEvidenceAtom]) -> list[str]:
    seen: set[str] = set()
    phrases: list[str] = []
    for atom in atoms:
        phrase = (atom.representative_phrase or atom.sentence_text or "").strip()
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        phrases.append(phrase[:120])
        if len(phrases) >= 8:
            break
    return phrases


def _representative_evidence_ids(atoms: Iterable[entities.Core3CommentEvidenceAtom]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for atom in atoms:
        if atom.comment_evidence_id in seen:
            continue
        seen.add(atom.comment_evidence_id)
        result.append(atom.comment_evidence_id)
        if len(result) >= 20:
            break
    return result


def _weighted_score(*items: tuple[Decimal, Decimal]) -> Decimal:
    total_weight = sum(weight for _, weight in items)
    if total_weight <= 0:
        return Decimal("0.0000")
    value = sum(_decimal(score) * weight for score, weight in items) / total_weight
    return _clamp(value)


def _avg(values: Iterable[Decimal]) -> Decimal:
    normalized = [_decimal(value) for value in values]
    if not normalized:
        return Decimal("0.0000")
    return _clamp(sum(normalized) / Decimal(len(normalized)))


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.0000")
    return Decimal(str(value))


def _clamp(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0.0000")
    if value > 1:
        return Decimal("1.0000")
    return value.quantize(Decimal("0.0001"))


def _stable_id(prefix: str, value: str) -> str:
    digest = stable_hash(value, version="m084_id_v1").split(":")[-1][:24]
    return f"{prefix}-{digest}"


def _normalize_token(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_").lower()
