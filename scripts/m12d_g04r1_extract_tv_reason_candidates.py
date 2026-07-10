#!/usr/bin/env python3
"""Read-only candidate extraction for M12D-G04R1.

The script does not create the final TV standard. It reads current Core3 TV
outputs, applies transparent candidate lenses, and writes an auditable report
for Codex/business review.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CODE = "TV"
MAX_SAMPLE_SKUS = 8
MAX_SAMPLE_TERMS = 12

POSITIVE_M12C_ROLES = {
    "premium_driver_estimated",
    "sales_driver_estimated",
    "value_bundle_claim",
    "customer_gain",
}
WEAK_M12C_ROLES = {
    "brand_claim_only",
    "weak_user_perception_claim",
    "basic_threshold",
    "sample_insufficient",
}
RISK_M12C_ROLES = {
    "drag_factor",
    "opportunity_gap",
    "price_up_opportunity",
    "high_price_competitor_intercept",
}


@dataclass(frozen=True)
class CandidateLens:
    code: str
    name_cn: str
    candidate_type: str
    definition_cn: str
    terms_by_domain: dict[str, list[str]]
    decision_question_cn: str
    related_value_theme_codes: tuple[str, ...] = ()
    related_task_hint_cn: str = ""
    required_logic_cn: str = ""
    weak_boundary_cn: str = ""


VALUE_THEME_LENSES: tuple[CandidateLens, ...] = (
    CandidateLens(
        code="picture_upgrade_perception",
        name_cn="画质升级感",
        candidate_type="value_theme",
        definition_cn="用户能感知到画面清晰度、亮度、控光、色彩或显示技术升级。",
        terms_by_domain={
            "param": ["mini_led", "miniled", "oled", "qled", "hdr", "brightness", "dimming", "resolution", "picture", "display", "color", "亮度", "画质", "分区", "色域"],
            "claim": ["tv_claim_miniled", "tv_claim_oled", "tv_claim_qled", "tv_claim_hdr", "tv_claim_picture_chip", "画质", "miniled", "控光", "分区"],
            "comment": ["picture", "screen", "clarity", "brightness", "清晰", "画质", "亮度", "电影", "观影"],
            "semantic_reference": ["premium_picture", "picture", "影音", "画质"],
            "claim_value": ["tv_claim_miniled", "tv_claim_oled", "tv_claim_qled", "tv_claim_picture_chip", "premium_driver", "sales_driver"],
        },
        decision_question_cn="这个主题是否代表用户可感知的画质升级价值，而不是单个画质参数？",
    ),
    CandidateLens(
        code="dynamic_stability_perception",
        name_cn="动态画面稳定感",
        candidate_type="value_theme",
        definition_cn="游戏、体育、运动画面中流畅、低延迟、少拖影的体验获得感。",
        terms_by_domain={
            "param": ["refresh", "hz", "hdmi", "vrr", "latency", "memc", "刷新率", "低延迟", "运动"],
            "claim": ["tv_claim_high_refresh", "tv_claim_hdmi_2_1", "tv_claim_vrr", "tv_claim_low_latency", "高刷", "游戏", "刷新率"],
            "comment": ["gaming", "sports", "motion", "smooth", "游戏", "体育", "流畅", "高刷"],
            "semantic_reference": ["gaming", "sports", "smoothness", "fluency", "游戏", "体育", "流畅"],
            "claim_value": ["tv_claim_high_refresh", "tv_claim_hdmi_2_1", "tv_claim_vrr", "tv_claim_low_latency"],
        },
        decision_question_cn="这个主题是否代表动态画面体验，而不是简单复制游戏战场？",
    ),
    CandidateLens(
        code="living_room_immersion_perception",
        name_cn="客厅沉浸感",
        candidate_type="value_theme",
        definition_cn="大屏、音效、杜比、观影距离与客厅空间共同形成的沉浸感。",
        terms_by_domain={
            "param": ["screen_size", "large", "audio", "dolby", "inch", "尺寸", "大屏", "音响"],
            "claim": ["大屏", "杜比", "音响", "影院", "沉浸"],
            "comment": ["cinema", "movie", "living_room", "watching", "电影", "追剧", "观影", "沉浸", "客厅"],
            "semantic_reference": ["cinema", "living_room", "large_screen", "观影", "客厅", "大屏"],
            "market": ["size_segment", "screen_size", "large", "xlarge", "ultra_large"],
        },
        decision_question_cn="这个主题是否代表客厅场景下的沉浸体验，而不是只有尺寸参数？",
    ),
    CandidateLens(
        code="operation_convenience_perception",
        name_cn="操作便利感",
        candidate_type="value_theme",
        definition_cn="AI、语音、投屏、IoT、系统易用带来的家庭使用便利。",
        terms_by_domain={
            "param": ["ai", "voice", "cast", "iot", "wifi", "smart_system", "智能", "语音", "投屏"],
            "claim": ["tv_claim_smart_iot", "tv_claim_voice_control", "tv_claim_screen_casting", "智能", "语音", "投屏", "互联"],
            "comment": ["smart", "voice", "cast", "easy", "智能", "语音", "投屏", "方便", "易用"],
            "semantic_reference": ["smart", "connected", "iot", "智能", "互联", "投屏"],
        },
        decision_question_cn="这个主题是否代表家庭使用便利，而不是泛化智能口号？",
    ),
    CandidateLens(
        code="long_watch_comfort_perception",
        name_cn="长看舒适感",
        candidate_type="value_theme",
        definition_cn="护眼、低蓝光、无频闪、抗反光和家庭长时间观看形成的舒适安心。",
        terms_by_domain={
            "param": ["eye", "blue", "flicker", "anti_glare", "护眼", "低蓝光", "无频闪", "抗反光"],
            "claim": ["护眼", "低蓝光", "无频闪", "抗反光"],
            "comment": ["eye", "child", "elder", "long_watch", "护眼", "孩子", "老人", "久看"],
            "semantic_reference": ["family", "long_watch", "child", "elder", "家庭"],
        },
        decision_question_cn="这个主题是否代表长时间观看舒适，而不是健康宣传语？",
    ),
    CandidateLens(
        code="space_aesthetic_fit",
        name_cn="空间审美适配",
        candidate_type="value_theme",
        definition_cn="外观、超薄、贴墙、全面屏、壁画和新家装修的空间适配价值。",
        terms_by_domain={
            "param": ["slim", "wall", "bezel", "art", "frame", "超薄", "贴墙", "全面屏", "壁画"],
            "claim": ["tv_claim_slim_body", "tv_claim_art_frame", "tv_claim_wall_mount", "超薄", "贴墙", "外观", "壁画"],
            "comment": ["decor", "new_home", "appearance", "新家", "家装", "外观", "好看"],
            "semantic_reference": ["decor", "new_home", "home_decor", "家装", "新家", "外观"],
        },
        decision_question_cn="这个主题是否代表空间/审美适配，而不是单个外观卖点？",
    ),
    CandidateLens(
        code="budget_configuration_efficiency",
        name_cn="预算配置效率",
        candidate_type="value_theme",
        definition_cn="在给定预算和尺寸池里，用户获得核心配置、价格和销量承接的效率。",
        terms_by_domain={
            "claim": ["value_price", "price_value", "tv_claim_value_price", "tv_claim_price_value", "性价比", "价格", "划算", "预算"],
            "comment": ["value_for_money", "budget", "cheap", "性价比", "划算", "这个价格", "预算"],
            "market": ["low", "mid_low", "volume_percentile", "price_band", "低价", "销量"],
            "claim_value": ["value_for_money", "customer_gain", "value_bundle", "price", "budget", "价格", "预算"],
        },
        decision_question_cn="这个主题是否代表预算内配置获得感，而不是厂家一句性价比？",
        weak_boundary_cn="只有 value_price/price_value 或性价比口号时，只能作为弱表达候选。",
    ),
)


PURCHASE_REASON_LENSES: tuple[CandidateLens, ...] = (
    CandidateLens(
        code="picture_upgrade_justifies_price",
        name_cn="画质配置解释加价",
        candidate_type="purchase_reason",
        definition_cn="在中高价或同尺寸对比中，SKU 用可验证画质配置和用户感知解释更高价格。",
        related_value_theme_codes=("picture_upgrade_perception",),
        related_task_hint_cn="客厅观影、影音体验、画质升级。",
        required_logic_cn="需要画质事实证据 + 用户感知或 M12C 支付价值 + 价格/市场位置。",
        weak_boundary_cn="只有“高端画质”口号或单一 claim 时不能成立。",
        decision_question_cn="这个 SKU 的画质配置是否足以解释它的价格？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[0].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[0].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[0].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[0].terms_by_domain["semantic_reference"],
            "market": ["high", "mid_high", "price_percentile", "price_band", "sales", "volume"],
            "claim_value": VALUE_THEME_LENSES[0].terms_by_domain["claim_value"],
        },
    ),
    CandidateLens(
        code="same_price_core_config_gain",
        name_cn="同价位核心配置获得感",
        candidate_type="purchase_reason",
        definition_cn="在同尺寸/同价位池中，SKU 用更多核心配置或销量承接解释“选它更划算”。",
        related_value_theme_codes=("budget_configuration_efficiency", "picture_upgrade_perception", "dynamic_stability_perception"),
        related_task_hint_cn="预算受限下的客厅换新或主流家庭购买。",
        required_logic_cn="需要价格/市场证据 + 配置事实或评论价值感；厂家性价比表达只能弱支撑。",
        weak_boundary_cn="只有 value_price/price_value 时封顶弱表达。",
        decision_question_cn="这个 SKU 是否在同价位中提供了更可解释的核心配置获得感？",
        terms_by_domain={
            "param": ["mini_led", "refresh", "hdmi", "screen_size", "ai", "配置", "尺寸"],
            "claim": VALUE_THEME_LENSES[6].terms_by_domain["claim"] + ["tv_claim_miniled", "tv_claim_high_refresh"],
            "comment": VALUE_THEME_LENSES[6].terms_by_domain["comment"],
            "market": VALUE_THEME_LENSES[6].terms_by_domain["market"],
            "claim_value": VALUE_THEME_LENSES[6].terms_by_domain["claim_value"],
        },
    ),
    CandidateLens(
        code="same_size_picture_step_up",
        name_cn="同尺寸画质越级获得感",
        candidate_type="purchase_reason",
        definition_cn="在同尺寸池中，SKU 用显示技术、亮度、控光或画质芯片解释比普通同尺寸电视更值得选。",
        related_value_theme_codes=("picture_upgrade_perception", "budget_configuration_efficiency"),
        related_task_hint_cn="同尺寸升级、客厅观影、主流家庭换新。",
        required_logic_cn="需要同尺寸/价格池参照 + 画质事实证据；评论或 M12C 可作为强化。",
        weak_boundary_cn="只有 MiniLED/画质口号但没有同尺寸参照或体验证据时，只能弱支撑。",
        decision_question_cn="这个 SKU 是否在同尺寸内提供了可感知的画质越级感？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[0].terms_by_domain["param"] + ["screen_size", "inch", "尺寸"],
            "claim": VALUE_THEME_LENSES[0].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[0].terms_by_domain["comment"],
            "market": ["screen_size", "size_segment", "price_band_size", "price_percentile", "volume_percentile"],
            "claim_value": VALUE_THEME_LENSES[0].terms_by_domain["claim_value"],
        },
    ),
    CandidateLens(
        code="av_user_willing_to_pay_for_picture",
        name_cn="影音用户愿为画质升级付费",
        candidate_type="purchase_reason",
        definition_cn="面向影音/电影/追剧用户，SKU 用画质和沉浸体验证明其具备付费升级理由。",
        related_value_theme_codes=("picture_upgrade_perception", "living_room_immersion_perception"),
        related_task_hint_cn="影音爱好者、电影追剧、客厅观影。",
        required_logic_cn="需要画质事实 + 观影/影音任务或评论 + M12C 正向支付价值。",
        weak_boundary_cn="只有影音/影院宣传语，缺少画质事实或 M12C 时不能强判。",
        decision_question_cn="影音用户是否有理由为这个 SKU 的画质/观影体验付费？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[0].terms_by_domain["param"] + VALUE_THEME_LENSES[2].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[0].terms_by_domain["claim"] + VALUE_THEME_LENSES[2].terms_by_domain["claim"],
            "comment": ["电影", "追剧", "观影", "影院", "沉浸", "清晰", "画质", "亮度"],
            "semantic_reference": ["premium_picture", "cinema", "影音", "观影", "影院"],
            "claim_value": VALUE_THEME_LENSES[0].terms_by_domain["claim_value"],
        },
    ),
    CandidateLens(
        code="living_room_upgrade_one_step",
        name_cn="客厅换新一步到位",
        candidate_type="purchase_reason",
        definition_cn="面向客厅换新，SKU 用尺寸、观影沉浸和主流价格/销量承接解释一步升级。",
        related_value_theme_codes=("living_room_immersion_perception", "picture_upgrade_perception"),
        related_task_hint_cn="客厅大屏、家庭观影、旧机换新。",
        required_logic_cn="需要尺寸/观影事实 + 用户任务或评论感知 + 市场承接。",
        weak_boundary_cn="只有屏幕尺寸数字，不足以成为购买理由。",
        decision_question_cn="这个 SKU 是否能解释客厅换新时为什么一步升级到它？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[2].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[2].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[2].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[2].terms_by_domain["semantic_reference"],
            "market": VALUE_THEME_LENSES[2].terms_by_domain["market"],
        },
    ),
    CandidateLens(
        code="big_screen_cinema_substitution",
        name_cn="大屏影音替代影院感",
        candidate_type="purchase_reason",
        definition_cn="SKU 用大屏、画质、音效或杜比能力解释家庭观影的影院替代体验。",
        related_value_theme_codes=("living_room_immersion_perception", "picture_upgrade_perception"),
        related_task_hint_cn="家庭影院、电影追剧、客厅大屏娱乐。",
        required_logic_cn="需要大屏/音画事实 + 观影评论或影院沉浸任务；市场同尺寸承接可强化。",
        weak_boundary_cn="只有“影院级/沉浸感”宣传语，没有音画事实或评论时不能成立。",
        decision_question_cn="这个 SKU 是否能解释用户用它获得大屏影音替代影院感？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[2].terms_by_domain["param"] + VALUE_THEME_LENSES[0].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[2].terms_by_domain["claim"] + VALUE_THEME_LENSES[0].terms_by_domain["claim"],
            "comment": ["电影", "追剧", "观影", "影院", "沉浸", "客厅", "大屏"],
            "semantic_reference": ["cinema", "living_room", "large_screen", "影院", "观影", "大屏"],
            "market": VALUE_THEME_LENSES[2].terms_by_domain["market"],
        },
    ),
    CandidateLens(
        code="gaming_device_fit_reduces_risk",
        name_cn="游戏设备适配降低踩坑风险",
        candidate_type="purchase_reason",
        definition_cn="面向游戏/体育用户，SKU 用高刷、接口、VRR、低延迟等完整性降低体验不确定性。",
        related_value_theme_codes=("dynamic_stability_perception",),
        related_task_hint_cn="主机游戏、体育赛事、动态画面。",
        required_logic_cn="需要高刷/接口/低延迟事实证据 + 游戏任务或评论感知。",
        weak_boundary_cn="只有“游戏电视”表达时不能成立。",
        decision_question_cn="这个 SKU 是否能减少游戏/体育体验踩坑风险？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[1].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[1].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[1].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[1].terms_by_domain["semantic_reference"],
            "claim_value": VALUE_THEME_LENSES[1].terms_by_domain["claim_value"],
        },
    ),
    CandidateLens(
        code="sports_motion_stability",
        name_cn="体育/运动画面流畅更稳",
        candidate_type="purchase_reason",
        definition_cn="面向赛事和运动画面，SKU 用刷新率、运动补偿或高刷评论解释动态画面更稳。",
        related_value_theme_codes=("dynamic_stability_perception",),
        related_task_hint_cn="体育赛事、运动画面、家庭观赛。",
        required_logic_cn="需要刷新率/MEMC/高刷事实 + 体育或运动评论/任务支撑。",
        weak_boundary_cn="只有高刷口号，没有体育/运动场景证据时不能强判。",
        decision_question_cn="这个 SKU 是否能解释体育/运动画面看起来更稳？",
        terms_by_domain={
            "param": ["refresh", "hz", "memc", "motion", "刷新率", "运动"],
            "claim": ["tv_claim_high_refresh", "高刷", "刷新率", "运动", "体育"],
            "comment": ["sports", "motion", "smooth", "体育", "运动", "流畅", "高刷"],
            "semantic_reference": ["sports", "motion", "fluency", "体育", "运动", "流畅"],
            "claim_value": ["tv_claim_high_refresh"],
        },
    ),
    CandidateLens(
        code="low_price_core_experience_intact",
        name_cn="低价不明显牺牲核心体验",
        candidate_type="purchase_reason",
        definition_cn="在低/中低价格位置，SKU 用核心画质、尺寸、系统或评论满意度证明低价不是明显牺牲体验。",
        related_value_theme_codes=("budget_configuration_efficiency", "picture_upgrade_perception", "operation_convenience_perception"),
        related_task_hint_cn="预算优先、入门换新、主流家庭基础使用。",
        required_logic_cn="需要低/中低价格位置 + 至少一个核心体验证据；销量或评论正向可强化。",
        weak_boundary_cn="只有低价、补贴或促销表达时，不进入产品购买理由。",
        decision_question_cn="这个 SKU 是否能解释低价下核心体验仍然够用？",
        terms_by_domain={
            "param": ["screen_size", "resolution", "refresh", "ai", "wifi", "尺寸", "配置"],
            "claim": ["价格", "value_price", "price_value", "性价比", "配置", "tv_claim_miniled", "tv_claim_high_refresh"],
            "comment": ["性价比", "划算", "够用", "清晰", "流畅", "这个价格"],
            "market": ["low", "mid_low", "price_band", "volume_percentile", "sales"],
            "claim_value": ["value_for_money", "customer_gain", "sales_driver", "value_bundle"],
        },
    ),
    CandidateLens(
        code="worth_paying_more_for_experience_upgrade",
        name_cn="贵得值的体验升级",
        candidate_type="purchase_reason",
        definition_cn="在中高/高价格位置，SKU 让用户看到多花钱换来的画质、动态或沉浸升级，并由评论、M12C 或市场承接证明这笔加价值得。",
        related_value_theme_codes=("picture_upgrade_perception", "dynamic_stability_perception", "living_room_immersion_perception"),
        related_task_hint_cn="中高端升级、愿意加价选择、竞品拦截。",
        required_logic_cn="需要中高/高价格位置 + 至少一个可感知强体验证据 + 评论、M12C 或市场承接；若反馈反向则转为价格压力。",
        weak_boundary_cn="只有高端口号、品牌溢价或参数堆叠，用户感知不到升级时，不能作为正向购买理由。",
        decision_question_cn="用户是否会觉得这个 SKU 虽然更贵，但多花的钱换来了明确体验升级？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[0].terms_by_domain["param"] + VALUE_THEME_LENSES[1].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[0].terms_by_domain["claim"] + VALUE_THEME_LENSES[1].terms_by_domain["claim"],
            "comment": ["画质", "清晰", "流畅", "高刷", "观影", "性价比", "价格"],
            "market": ["high", "mid_high", "price_percentile", "price_band", "volume_percentile"],
            "claim_value": ["drag_factor", "opportunity_gap", "price_up_opportunity", "high_price_competitor_intercept", "premium_driver", "sales_driver"],
        },
    ),
    CandidateLens(
        code="family_operation_less_friction",
        name_cn="家庭多设备使用更省操作",
        candidate_type="purchase_reason",
        definition_cn="家庭多人使用时，SKU 用投屏、语音、IoT 和系统易用降低操作成本。",
        related_value_theme_codes=("operation_convenience_perception",),
        related_task_hint_cn="家庭共享、投屏、智能家居。",
        required_logic_cn="需要智能/互联事实证据 + 任务或评论易用感知。",
        weak_boundary_cn="只有 AI 或智能口号时只能弱支撑。",
        decision_question_cn="这个 SKU 是否能解释家庭日常使用更省操作？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[3].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[3].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[3].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[3].terms_by_domain["semantic_reference"],
        },
    ),
    CandidateLens(
        code="family_long_watch_comfort_assurance",
        name_cn="家庭长时间观看更安心",
        candidate_type="purchase_reason",
        definition_cn="老人、孩子或家庭长看场景下，SKU 用护眼事实和用户感知降低长期观看顾虑。",
        related_value_theme_codes=("long_watch_comfort_perception",),
        related_task_hint_cn="儿童/老人/家庭长时间观看。",
        required_logic_cn="需要护眼参数或认证 + 评论/任务支撑；泛健康口号不足。",
        weak_boundary_cn="只有健康宣传或认证口号时不能强判。",
        decision_question_cn="这个 SKU 是否能解释家庭长时间观看更安心？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[4].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[4].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[4].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[4].terms_by_domain["semantic_reference"],
        },
    ),
    CandidateLens(
        code="new_home_aesthetic_fit",
        name_cn="新家客厅审美适配",
        candidate_type="purchase_reason",
        definition_cn="新家装修或客厅审美场景下，SKU 用外观/安装适配解释为什么更适合。",
        related_value_theme_codes=("space_aesthetic_fit",),
        related_task_hint_cn="新家装修、家装融合、客厅审美。",
        required_logic_cn="需要外观/安装事实 + 新家/家装任务或评论支撑。",
        weak_boundary_cn="只有外观好看表达时不能直接成为核心购买理由。",
        decision_question_cn="这个 SKU 是否能解释新家客厅为什么更适配？",
        terms_by_domain={
            "param": VALUE_THEME_LENSES[5].terms_by_domain["param"],
            "claim": VALUE_THEME_LENSES[5].terms_by_domain["claim"],
            "comment": VALUE_THEME_LENSES[5].terms_by_domain["comment"],
            "semantic_reference": VALUE_THEME_LENSES[5].terms_by_domain["semantic_reference"],
        },
    ),
)


QUERY_SPECS: tuple[dict[str, str], ...] = (
    {
        "domain": "param",
        "module": "M03B",
        "table": "core3_sku_param_profile",
        "sql": """
            select sku_code, model_name, null as brand_name,
                   jsonb_build_object(
                       'param_values_json', param_values_json,
                       'core_picture_params_json', core_picture_params_json,
                       'core_gaming_params_json', core_gaming_params_json,
                       'core_system_params_json', core_system_params_json,
                       'core_eye_care_params_json', core_eye_care_params_json,
                       'known_param_count', known_param_count,
                       'quality_summary_json', quality_summary_json
                   ) as payload
            from core3_sku_param_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "claim",
        "module": "M04C",
        "table": "core3_sku_claim_fact_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'claim_codes', claim_codes,
                       'fact_claim_codes', fact_claim_codes,
                       'unsupported_claim_codes', unsupported_claim_codes,
                       'service_claim_codes', service_claim_codes,
                       'dimension_profile_json', dimension_profile_json,
                       'dimension_position_profile_json', dimension_position_profile_json,
                       'claim_summary_json', claim_summary_json,
                       'claim_texts_json', claim_texts_json
                   ) as payload
            from core3_sku_claim_fact_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "claim",
        "module": "M04C",
        "table": "core3_sku_claim_fact",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'claim_code', claim_code,
                       'claim_name', claim_name,
                       'claim_dimension', claim_dimension,
                       'claim_subtype', claim_subtype,
                       'claim_kind', claim_kind,
                       'param_support_status', param_support_status,
                       'param_support_level', param_support_level,
                       'wtp_input_guard', wtp_input_guard,
                       'fact_claim_flag', fact_claim_flag,
                       'service_separate_flag', service_separate_flag,
                       'supporting_param_codes', supporting_param_codes,
                       'clean_claim_text', clean_claim_text
                   ) as payload
            from core3_sku_claim_fact
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "comment",
        "module": "M05C",
        "table": "core3_sku_comment_fact_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'dimension_summary_json', dimension_summary_json,
                       'signal_summary_json', signal_summary_json,
                       'claim_comment_support_json', claim_comment_support_json,
                       'param_comment_support_json', param_comment_support_json,
                       'polarity_summary_json', polarity_summary_json,
                       'evidence_examples_json', evidence_examples_json,
                       'supported_param_codes', supported_param_codes,
                       'supported_claim_codes', supported_claim_codes,
                       'positive_sentence_count', positive_sentence_count,
                       'negative_sentence_count', negative_sentence_count
                   ) as payload
            from core3_sku_comment_fact_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "comment",
        "module": "M05C",
        "table": "core3_comment_fact_atom",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'dimension_code', dimension_code,
                       'dimension_name', dimension_name,
                       'subdimension_code', subdimension_code,
                       'subdimension_name', subdimension_name,
                       'dimension_type', dimension_type,
                       'polarity', polarity,
                       'evidence_strength', evidence_strength,
                       'supported_param_codes', supported_param_codes,
                       'supported_claim_codes', supported_claim_codes,
                       'clean_comment_text', left(clean_comment_text, 80)
                   ) as payload
            from core3_comment_fact_atom
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "market",
        "module": "M07",
        "table": "core3_sku_market_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'screen_size_inch', screen_size_inch,
                       'size_segment', size_segment,
                       'screen_size_class', screen_size_class,
                       'market_pool_key', market_pool_key,
                       'price_band_category', price_band_category,
                       'price_band_size', price_band_size,
                       'price_percentile_in_size', price_percentile_in_size,
                       'volume_percentile_in_size', volume_percentile_in_size,
                       'amount_percentile_in_size', amount_percentile_in_size,
                       'sales_volume_total', sales_volume_total,
                       'price_wavg', price_wavg,
                       'sample_status', sample_status
                   ) as payload
            from core3_sku_market_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and analysis_window = 'full_observed_window'
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "semantic_reference",
        "module": "M09C",
        "table": "core3_m09c_sku_user_task_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'primary_user_task_code', primary_user_task_code,
                       'secondary_user_task_codes_json', secondary_user_task_codes_json,
                       'comment_observed_task_codes_json', comment_observed_task_codes_json,
                       'brand_claimed_task_codes_json', brand_claimed_task_codes_json,
                       'latent_capability_task_codes_json', latent_capability_task_codes_json,
                       'drag_factor_task_codes_json', drag_factor_task_codes_json,
                       'user_task_summary_json', user_task_summary_json
                   ) as payload
            from core3_m09c_sku_user_task_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "semantic_reference",
        "module": "M10C",
        "table": "core3_m10c_sku_target_group_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'primary_target_group_code', primary_target_group_code,
                       'secondary_target_group_codes_json', secondary_target_group_codes_json,
                       'comment_observed_group_codes_json', comment_observed_group_codes_json,
                       'brand_claimed_group_codes_json', brand_claimed_group_codes_json,
                       'latent_group_codes_json', latent_group_codes_json,
                       'unmet_group_need_codes_json', unmet_group_need_codes_json,
                       'target_group_summary_json', target_group_summary_json
                   ) as payload
            from core3_m10c_sku_target_group_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "semantic_reference",
        "module": "M11C",
        "table": "core3_sku_value_battlefield_profile",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'primary_battlefield_code', primary_battlefield_code,
                       'secondary_battlefield_codes_json', secondary_battlefield_codes_json,
                       'opportunity_battlefield_codes_json', opportunity_battlefield_codes_json,
                       'drag_factor_battlefield_codes_json', drag_factor_battlefield_codes_json,
                       'battlefield_summary_json', battlefield_summary_json
                   ) as payload
            from core3_sku_value_battlefield_profile
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "semantic_market",
        "module": "M11D",
        "table": "core3_semantic_market_dimension_summary",
        "sql": """
            select '' as sku_code, null as model_name, null as brand_name,
                   jsonb_build_object(
                       'dimension_type', dimension_type,
                       'dimension_code', dimension_code,
                       'dimension_name', dimension_name,
                       'sku_relation_count', sku_relation_count,
                       'allocated_sku_count', allocated_sku_count,
                       'primary_sku_count', primary_sku_count,
                       'observed_need_sku_count', observed_need_sku_count,
                       'brand_claim_sku_count', brand_claim_sku_count,
                       'drag_risk_sku_count', drag_risk_sku_count,
                       'sales_volume_share', sales_volume_share,
                       'business_summary_cn', business_summary_cn
                   ) as payload
            from core3_semantic_market_dimension_summary
            where category_code = :category_code
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
    {
        "domain": "claim_value",
        "module": "M12C",
        "table": "core3_sku_claim_value_quantification",
        "sql": """
            select sku_code, model_name, brand_name,
                   jsonb_build_object(
                       'claim_code', claim_code,
                       'claim_name', claim_name,
                       'claim_dimension', claim_dimension,
                       'claim_value_role', claim_value_role,
                       'context_type', context_type,
                       'context_code', context_code,
                       'context_name', context_name,
                       'size_tier', size_tier,
                       'price_band_group', price_band_group,
                       'claim_evidence_strength', claim_evidence_strength,
                       'param_support_strength', param_support_strength,
                       'comment_support_strength', comment_support_strength,
                       'semantic_support_strength', semantic_support_strength,
                       'estimated_price_premium_abs', estimated_price_premium_abs,
                       'estimated_weekly_sales_lift_abs', estimated_weekly_sales_lift_abs,
                       'contribution_share_in_sku', contribution_share_in_sku,
                       'reason_cn', reason_cn
                   ) as payload
            from core3_sku_claim_value_quantification
            where category_code = :category_code
              and sku_code like :sku_prefix
              and is_current is true
              and (:project_id = '' or project_id = :project_id)
        """,
    },
)


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    with engine.connect() as conn:
        rows_by_domain, source_stats, identity_by_sku = load_source_rows(
            conn,
            category_code=args.category_code,
            project_id=args.project_id or "",
        )

    value_theme_results = evaluate_lenses(VALUE_THEME_LENSES, rows_by_domain, identity_by_sku)
    purchase_reason_results = evaluate_lenses(PURCHASE_REASON_LENSES, rows_by_domain, identity_by_sku)
    source_overview = build_source_overview(source_stats)
    recommendations = build_recommendations(value_theme_results, purchase_reason_results)
    payload = {
        "generated_at_utc": generated_at,
        "project_id": args.project_id or "",
        "category_code": args.category_code,
        "purpose": "M12D-G04R1 candidate extraction; not final standard.",
        "source_overview": source_overview,
        "value_theme_candidates": value_theme_results,
        "purchase_reason_candidates": purchase_reason_results,
        "recommendations": recommendations,
    }

    json_path = out_dir / "M12D_G04R1_tv_value_theme_purchase_reason_candidates.json"
    md_path = out_dir / "M12D_G04R1_tv_value_theme_purchase_reason_candidate_report.md"
    value_theme_draft_path = out_dir / "M12D_tv_standard_value_theme_taxonomy_v0_1_draft.md"
    purchase_reason_draft_path = out_dir / "M12D_tv_standard_purchase_reason_taxonomy_v0_1_draft.md"

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_report(payload), encoding="utf-8")
    value_theme_draft_path.write_text(render_value_theme_draft(payload), encoding="utf-8")
    purchase_reason_draft_path.write_text(render_purchase_reason_draft(payload), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"wrote {value_theme_draft_path}")
    print(f"wrote {purchase_reason_draft_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract TV value-theme and purchase-reason candidates from Core3 outputs.")
    parser.add_argument("--database-url", default="", help="SQLAlchemy database URL. Defaults to CATFORGE_DATABASE_URL.")
    parser.add_argument("--project-id", default=PROJECT_ID, help="Project id filter. Empty string disables project filter.")
    parser.add_argument("--category-code", default=CATEGORY_CODE, help="Category code, default TV.")
    parser.add_argument(
        "--output-dir",
        default="docs/core3_mvp/real_data_v2/current_implementation",
        help="Directory for generated JSON/Markdown outputs.",
    )
    return parser.parse_args()


def load_source_rows(conn: Any, *, category_code: str, project_id: str) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, dict[str, str]]]:
    rows_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_stats: list[dict[str, Any]] = []
    identity_by_sku: dict[str, dict[str, str]] = {}
    params = {"category_code": category_code, "project_id": project_id, "sku_prefix": f"{category_code}%"}
    for spec in QUERY_SPECS:
        rows = [dict(row) for row in conn.execute(text(spec["sql"]), params).mappings().all()]
        sku_codes = {str(row.get("sku_code") or "") for row in rows if row.get("sku_code")}
        source_stats.append(
            {
                "module": spec["module"],
                "domain": spec["domain"],
                "table": spec["table"],
                "row_count": len(rows),
                "sku_count": len(sku_codes),
            }
        )
        for row in rows:
            sku_code = str(row.get("sku_code") or "")
            if sku_code:
                identity = identity_by_sku.setdefault(sku_code, {"sku_code": sku_code, "brand_name": "", "model_name": ""})
                identity["brand_name"] = identity["brand_name"] or str(row.get("brand_name") or "")
                identity["model_name"] = identity["model_name"] or str(row.get("model_name") or "")
            payload = jsonable(row.get("payload") or {})
            rows_by_domain[spec["domain"]].append(
                {
                    "module": spec["module"],
                    "table": spec["table"],
                    "sku_code": sku_code,
                    "brand_name": str(row.get("brand_name") or ""),
                    "model_name": str(row.get("model_name") or ""),
                    "payload": payload,
                    "text": normalize_text(payload),
                }
            )
    return dict(rows_by_domain), source_stats, identity_by_sku


def evaluate_lenses(
    lenses: Iterable[CandidateLens],
    rows_by_domain: Mapping[str, list[dict[str, Any]]],
    identity_by_sku: Mapping[str, dict[str, str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    all_skus = set(identity_by_sku)
    denominator = max(1, len(all_skus))
    for lens in lenses:
        domain_skus: dict[str, set[str]] = defaultdict(set)
        domain_terms: dict[str, Counter[str]] = defaultdict(Counter)
        domain_modules: dict[str, Counter[str]] = defaultdict(Counter)
        sample_skus: dict[str, dict[str, str]] = {}
        m12c_role_counts: Counter[str] = Counter()
        for domain, rows in rows_by_domain.items():
            terms = lens.terms_by_domain.get(domain)
            if not terms:
                continue
            for row in rows:
                matched = match_terms(row["text"], terms)
                if not matched:
                    continue
                sku_code = row.get("sku_code") or ""
                if sku_code:
                    domain_skus[domain].add(sku_code)
                    if len(sample_skus) < MAX_SAMPLE_SKUS:
                        identity = identity_by_sku.get(sku_code, {})
                        sample_skus.setdefault(
                            sku_code,
                            {
                                "sku_code": sku_code,
                                "brand_name": identity.get("brand_name") or row.get("brand_name") or "",
                                "model_name": identity.get("model_name") or row.get("model_name") or "",
                            },
                        )
                domain_modules[domain][row["module"]] += 1
                domain_terms[domain].update(matched)
                if domain == "claim_value":
                    role = str((row.get("payload") or {}).get("claim_value_role") or "")
                    if role:
                        m12c_role_counts[role] += 1
        matched_skus = set().union(*domain_skus.values()) if domain_skus else set()
        evidence_domains = sorted(domain_skus)
        result = {
            "candidate_code": lens.code,
            "candidate_name_cn": lens.name_cn,
            "candidate_type": lens.candidate_type,
            "definition_cn": lens.definition_cn,
            "decision_question_cn": lens.decision_question_cn,
            "related_value_theme_codes": list(lens.related_value_theme_codes),
            "related_task_hint_cn": lens.related_task_hint_cn,
            "required_logic_cn": lens.required_logic_cn,
            "weak_boundary_cn": lens.weak_boundary_cn,
            "matched_sku_count": len(matched_skus),
            "matched_sku_ratio": round(len(matched_skus) / denominator, 4),
            "evidence_domain_count": len(evidence_domains),
            "evidence_domains": evidence_domains,
            "domain_sku_counts": {domain: len(skus) for domain, skus in sorted(domain_skus.items())},
            "domain_modules": {domain: dict(counter.most_common()) for domain, counter in sorted(domain_modules.items())},
            "matched_terms": {
                domain: [term for term, _ in counter.most_common(MAX_SAMPLE_TERMS)]
                for domain, counter in sorted(domain_terms.items())
            },
            "sample_skus": list(sample_skus.values()),
            "m12c_role_counts": dict(m12c_role_counts.most_common()),
            "candidate_score": candidate_score(
                candidate_type=lens.candidate_type,
                matched_sku_ratio=len(matched_skus) / denominator,
                evidence_domains=evidence_domains,
                m12c_role_counts=m12c_role_counts,
            ),
            "review_flags": review_flags(lens, evidence_domains, m12c_role_counts),
        }
        results.append(result)
    return sorted(results, key=lambda item: (-item["candidate_score"], -item["matched_sku_count"], item["candidate_code"]))


def candidate_score(
    *,
    candidate_type: str,
    matched_sku_ratio: float,
    evidence_domains: list[str],
    m12c_role_counts: Counter[str],
) -> float:
    domain_score = min(0.42, len(evidence_domains) * 0.07)
    coverage_score = min(0.20, matched_sku_ratio * 0.35)
    user_score = 0.12 if "comment" in evidence_domains else 0.0
    fact_score = 0.10 if {"param", "claim"} & set(evidence_domains) else 0.0
    market_score = 0.08 if {"market", "semantic_market"} & set(evidence_domains) else 0.0
    semantic_score = 0.06 if "semantic_reference" in evidence_domains else 0.0
    positive_roles = sum(count for role, count in m12c_role_counts.items() if role in POSITIVE_M12C_ROLES or "driver" in role)
    risk_roles = sum(count for role, count in m12c_role_counts.items() if role in RISK_M12C_ROLES)
    claim_value_score = 0.10 if positive_roles else 0.0
    risk_penalty = 0.04 if risk_roles and not positive_roles else 0.0
    type_penalty = 0.03 if candidate_type == "purchase_reason" and "market" not in evidence_domains and "claim_value" not in evidence_domains else 0.0
    return round(max(0.0, min(1.0, domain_score + coverage_score + user_score + fact_score + market_score + semantic_score + claim_value_score - risk_penalty - type_penalty)), 4)


def review_flags(lens: CandidateLens, evidence_domains: list[str], m12c_role_counts: Counter[str]) -> list[str]:
    flags: list[str] = []
    domains = set(evidence_domains)
    if domains == {"semantic_reference"}:
        flags.append("duplicates_task_group_battlefield_risk")
    if lens.candidate_type == "purchase_reason" and "market" not in domains and "claim_value" not in domains:
        flags.append("needs_price_or_payment_validation")
    if lens.code in {"budget_configuration_efficiency", "same_price_core_config_gain"} and domains <= {"claim"}:
        flags.append("weak_expression_only_risk")
    weak_roles = sum(count for role, count in m12c_role_counts.items() if role in WEAK_M12C_ROLES)
    positive_roles = sum(count for role, count in m12c_role_counts.items() if role in POSITIVE_M12C_ROLES or "driver" in role)
    if weak_roles and not positive_roles:
        flags.append("m12c_weak_roles_only")
    if not flags:
        flags.append("review_candidate")
    return flags


def build_source_overview(source_stats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(source_stats, key=lambda item: (item["module"], item["table"]))


def build_recommendations(
    value_theme_results: list[dict[str, Any]],
    purchase_reason_results: list[dict[str, Any]],
) -> dict[str, Any]:
    accepted_value_themes = [item["candidate_code"] for item in value_theme_results if item["candidate_score"] >= 0.55]
    review_value_themes = [item["candidate_code"] for item in value_theme_results if 0.35 <= item["candidate_score"] < 0.55]
    accepted_purchase_reasons = [
        item["candidate_code"]
        for item in purchase_reason_results
        if item["candidate_score"] >= 0.50 and "needs_price_or_payment_validation" not in item["review_flags"]
    ]
    review_purchase_reasons = [
        item["candidate_code"]
        for item in purchase_reason_results
        if item["candidate_code"] not in accepted_purchase_reasons and item["candidate_score"] >= 0.35
    ]
    return {
        "standard_model_cn": "先固化 TV 标准价值主题，再在主题之上固化选择逻辑型标准购买理由；M12D 生产程序只消费标准，不自动生成标准。",
        "accepted_value_theme_candidates": accepted_value_themes,
        "review_value_theme_candidates": review_value_themes,
        "accepted_purchase_reason_candidates": accepted_purchase_reasons,
        "review_purchase_reason_candidates": review_purchase_reasons,
        "g04_taxonomy_fix_cn": "现有 G04 的高端画质/游戏流畅等应降级为价值主题候选或 theme_family；新增 purchase_reason_code 才能进入成交理由画像。",
    }


def render_report(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# M12D-G04R1 TV 价值主题与购买理由候选提炼报告")
    lines.append("")
    lines.append(f"生成时间 UTC：{payload['generated_at_utc']}")
    lines.append("")
    lines.append("本报告由只读脚本从 205 当前 Core3 TV 结果提炼候选。它不是最终标准，最终标准需要业务/Codex 审阅后固化版本。")
    lines.append("")
    lines.append("## 1. 数据覆盖")
    lines.append("")
    lines.append("| 模块 | 证据域 | 表 | 行数 | SKU 数 |")
    lines.append("| --- | --- | --- | ---: | ---: |")
    for item in payload["source_overview"]:
        lines.append(f"| {item['module']} | {item['domain']} | `{item['table']}` | {item['row_count']} | {item['sku_count']} |")
    lines.append("")
    lines.append("## 2. 价值主题候选")
    lines.append("")
    lines.extend(render_candidate_table(payload["value_theme_candidates"]))
    lines.append("")
    lines.append("## 3. 标准购买理由候选")
    lines.append("")
    lines.extend(render_candidate_table(payload["purchase_reason_candidates"]))
    lines.append("")
    lines.append("## 4. 候选详情")
    lines.append("")
    for title, candidates in (
        ("价值主题候选", payload["value_theme_candidates"]),
        ("购买理由候选", payload["purchase_reason_candidates"]),
    ):
        lines.append(f"### {title}")
        lines.append("")
        for item in candidates:
            lines.extend(render_candidate_detail(item))
    lines.append("## 5. 修正建议")
    lines.append("")
    rec = payload["recommendations"]
    lines.append(f"- 标准模型：{rec['standard_model_cn']}")
    lines.append(f"- G04 taxonomy 修正：{rec['g04_taxonomy_fix_cn']}")
    lines.append(f"- 建议进入价值主题草案：{', '.join(rec['accepted_value_theme_candidates']) or '无'}")
    lines.append(f"- 需要复核的价值主题：{', '.join(rec['review_value_theme_candidates']) or '无'}")
    lines.append(f"- 建议进入购买理由草案：{', '.join(rec['accepted_purchase_reason_candidates']) or '无'}")
    lines.append(f"- 需要复核的购买理由：{', '.join(rec['review_purchase_reason_candidates']) or '无'}")
    lines.append("")
    lines.append("## 6. G05 前置结论")
    lines.append("")
    lines.append("G05 不能继续消费 G04 中的名词型锚点作为购买理由。必须先把标准拆成 `value_theme_code` 与 `purchase_reason_code`，并让购买理由包含选择逻辑、证据门槛和弱表达边界。")
    lines.append("")
    return "\n".join(lines)


def render_candidate_table(candidates: list[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| 候选代码 | 中文名 | 得分 | SKU 数 | 证据域 | 审阅标记 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for item in candidates:
        lines.append(
            f"| `{item['candidate_code']}` | {item['candidate_name_cn']} | {item['candidate_score']:.4f} | "
            f"{item['matched_sku_count']} | {', '.join(item['evidence_domains'])} | {', '.join(item['review_flags'])} |"
        )
    return lines


def render_candidate_detail(item: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"#### {item['candidate_name_cn']} `{item['candidate_code']}`")
    lines.append("")
    lines.append(f"- 定义：{item['definition_cn']}")
    lines.append(f"- 业务问题：{item['decision_question_cn']}")
    if item.get("required_logic_cn"):
        lines.append(f"- 成立逻辑：{item['required_logic_cn']}")
    if item.get("weak_boundary_cn"):
        lines.append(f"- 弱表达边界：{item['weak_boundary_cn']}")
    lines.append(f"- 命中 SKU：{item['matched_sku_count']}，证据域：{', '.join(item['evidence_domains']) or '无'}")
    lines.append(f"- 证据域 SKU 数：{json.dumps(item['domain_sku_counts'], ensure_ascii=False)}")
    if item.get("m12c_role_counts"):
        lines.append(f"- M12C role 分布：{json.dumps(item['m12c_role_counts'], ensure_ascii=False)}")
    lines.append(f"- 主要命中词：{json.dumps(item['matched_terms'], ensure_ascii=False)}")
    sample_text = ", ".join(format_sku(item) for item in item.get("sample_skus", []))
    lines.append(f"- 样本 SKU：{sample_text or '无'}")
    lines.append(f"- 审阅标记：{', '.join(item['review_flags'])}")
    lines.append("")
    return lines


def render_value_theme_draft(payload: Mapping[str, Any]) -> str:
    candidates = payload["value_theme_candidates"]
    lines = [
        "# TV 标准价值主题 v0.1 草案",
        "",
        f"生成时间 UTC：{payload['generated_at_utc']}",
        "",
        "本草案来自 M12D-G04R1 候选提炼报告，尚需业务审核。价值主题表达用户获得的可感知价值类型，不等同于价值战场，也不等同于购买理由。",
        "",
        "| value_theme_code | 中文名 | 定义 | 证据域 | 审阅状态 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        status = "draft_accept" if item["candidate_score"] >= 0.55 else "review"
        lines.append(
            f"| `{item['candidate_code']}` | {item['candidate_name_cn']} | {item['definition_cn']} | "
            f"{', '.join(item['evidence_domains'])} | {status} |"
        )
    lines.append("")
    lines.append("审核规则：保留能由事实/感知/市场或支付价值支撑的主题；删除只复制价值战场、只有厂家口号或无法区分 SKU 强弱的主题。")
    lines.append("")
    return "\n".join(lines)


def render_purchase_reason_draft(payload: Mapping[str, Any]) -> str:
    candidates = payload["purchase_reason_candidates"]
    lines = [
        "# TV 标准购买理由 v0.1 草案",
        "",
        f"生成时间 UTC：{payload['generated_at_utc']}",
        "",
        "本草案来自 M12D-G04R1 候选提炼报告，尚需业务审核。购买理由必须是选择逻辑型解释，回答为什么选择这个 SKU，而不是只描述价值方向。",
        "",
        "| purchase_reason_code | 中文名 | 对应价值主题 | 成立逻辑 | 弱表达边界 | 审阅状态 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in candidates:
        status = "draft_accept" if item["candidate_score"] >= 0.50 and "needs_price_or_payment_validation" not in item["review_flags"] else "review"
        lines.append(
            f"| `{item['candidate_code']}` | {item['candidate_name_cn']} | {', '.join(item['related_value_theme_codes'])} | "
            f"{item['required_logic_cn']} | {item['weak_boundary_cn']} | {status} |"
        )
    lines.append("")
    lines.append("审核规则：购买理由必须具备用户任务/场景、价格或竞品取舍、SKU 证据组合和弱表达边界。")
    lines.append("")
    return "\n".join(lines)


def format_sku(item: Mapping[str, str]) -> str:
    display = " ".join(part for part in (item.get("brand_name", ""), item.get("model_name", "")) if part)
    return f"{item.get('sku_code', '')} {display}".strip()


def match_terms(text_value: str, terms: Iterable[str]) -> list[str]:
    matched: list[str] = []
    for term in terms:
        normalized = normalize_token(term)
        if normalized and normalized in text_value:
            matched.append(term)
    return matched


def normalize_text(value: Any) -> str:
    tokens = [normalize_token(token) for token in flatten(value)]
    return " ".join(token for token in tokens if token)


def normalize_token(value: Any) -> str:
    text_value = str(value).strip().lower()
    text_value = re.sub(r"[\s\-./]+", "_", text_value)
    return text_value


def flatten(value: Any) -> Iterable[str]:
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from flatten(item)
        return
    if isinstance(value, (list, tuple, set)):
        for item in value:
            yield from flatten(item)
        return
    yield str(value)


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


if __name__ == "__main__":
    main()
