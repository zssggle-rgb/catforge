#!/usr/bin/env python3
"""Read-only AC candidate extraction for M12D AC G02.

The script does not publish the AC standard taxonomy. It reads current AC
Core3 outputs, applies transparent candidate lenses, and writes an auditable
candidate report for Codex/business review.
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
CATEGORY_CODE = "AC"
BATCH_ID = "m00_20260624000202_1150a669"
MARKET_WINDOW = "full_observed_window"
ANALYSIS_POPULATION = "fact_complete_with_comment"
DEFAULT_OUTPUT_DIR = "docs/core3_mvp/real_data_v2/current_implementation"
MAX_SAMPLE_SKUS = 8
MAX_TERMS_PER_DOMAIN = 12

POSITIVE_M12C_ROLES = {
    "sales_driver_estimated",
    "premium_driver_estimated",
    "customer_gain",
    "value_bundle_claim",
}
WEAK_M12C_ROLES = {
    "weak_user_perception_claim",
    "basic_threshold",
    "sample_insufficient",
    "brand_claim_only",
}
RISK_M12C_ROLES = {
    "drag_factor",
    "opportunity_gap",
    "price_up_opportunity",
    "high_price_competitor_intercept",
}
DOMAIN_WEIGHTS = {
    "param": 2.0,
    "claim": 1.5,
    "comment": 2.0,
    "semantic_reference": 1.5,
    "semantic_market": 1.0,
    "market": 1.5,
    "claim_value": 2.0,
}
MISSING_MODULES_TO_REPORT = {"M03B", "M04C", "M05C", "M09C", "M10C", "M11C", "M11D", "M12C"}


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
        code="cooling_heating_capacity_assurance",
        name_cn="冷暖能力确定感",
        candidate_type="value_theme",
        definition_cn="用户相信空调能覆盖目标空间，冷得快、热得稳，不容易买小或不够用。",
        terms_by_domain={
            "param": ["capacity", "cooling", "heating", "制冷", "制热", "匹", "风量", "循环风量", "电辅热"],
            "claim": ["temperature_performance", "速冷", "速热", "制冷", "制热", "大风量", "冷暖"],
            "comment": ["制冷", "制热", "冷得快", "降温", "暖和", "够用", "风量"],
            "semantic_reference": ["large_space", "coverage", "reliable", "冷暖", "大空间", "可靠"],
            "market": ["sales_volume_total", "same_pool_volume_percentile", "high", "mid_high"],
            "claim_value": ["temperature_performance", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表用户对冷暖能力和空间覆盖的确定感，而不是只看到一个匹数？",
    ),
    CandidateLens(
        code="energy_cost_efficiency",
        name_cn="长期用电成本效率",
        candidate_type="value_theme",
        definition_cn="用户相信长期使用电费更可控，能效/APF/变频可以解释后续成本。",
        terms_by_domain={
            "param": ["apf", "energy", "能效", "一级", "变频", "耗电", "省电"],
            "claim": ["energy_efficiency", "一级能效", "apf", "变频", "省电", "节能"],
            "comment": ["省电", "耗电", "电费", "节能", "一级能效"],
            "semantic_reference": ["energy", "long_use", "saver", "节能", "长期"],
            "claim_value": ["energy_efficiency", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表长期用电成本，而不是一级能效口号？",
    ),
    CandidateLens(
        code="sleep_quiet_comfort",
        name_cn="睡眠静音舒适感",
        candidate_type="value_theme",
        definition_cn="用户在卧室或夜间使用时更安静、不扰眠、温控更舒适。",
        terms_by_domain={
            "param": ["noise", "db", "sleep", "静音", "噪音", "睡眠"],
            "claim": ["静音", "睡眠", "airflow_comfort", "低噪"],
            "comment": ["静音", "安静", "噪音", "睡觉", "睡眠", "卧室", "不吵"],
            "semantic_reference": ["sleep", "quiet", "bedroom", "卧室", "睡眠", "静音"],
            "claim_value": ["airflow_comfort", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表卧室睡眠舒适，而不是泛化静音表达？",
    ),
    CandidateLens(
        code="comfortable_airflow_health",
        name_cn="舒适风与健康空气",
        candidate_type="value_theme",
        definition_cn="用户减少直吹、闷、异味或空气健康担忧。",
        terms_by_domain={
            "param": ["fresh", "air", "sterili", "filter", "wind", "swing", "新风", "除菌", "净化", "柔风", "防直吹", "扫风"],
            "claim": ["airflow_comfort", "health_clean_air", "新风", "净化", "除菌", "柔风", "防直吹", "舒适风"],
            "comment": ["不直吹", "柔风", "风感", "新风", "异味", "空气", "闷", "除菌", "净化"],
            "semantic_reference": ["soft_wind", "health", "comfort", "空气", "柔风", "健康"],
            "claim_value": ["airflow_comfort", "health_clean_air", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表舒适风和健康空气，而不是单个新风/柔风卖点？",
    ),
    CandidateLens(
        code="large_space_coverage",
        name_cn="大空间覆盖感",
        candidate_type="value_theme",
        definition_cn="用户相信客厅、大卧室或大面积空间能被快速覆盖。",
        terms_by_domain={
            "param": ["72", "88", "3匹", "柜机", "floor", "large", "capacity", "风量", "制冷量"],
            "claim": ["大风量", "大空间", "客厅", "柜机", "temperature_performance"],
            "comment": ["客厅", "大空间", "大房间", "风量", "制冷快", "够用"],
            "semantic_reference": ["large_space", "living", "floor", "coverage", "客厅", "大空间"],
            "market": ["high", "same_pool_volume_percentile", "sales_volume_total"],
        },
        decision_question_cn="这个主题是否代表大空间覆盖，而不是只有柜机或大匹数标签？",
    ),
    CandidateLens(
        code="installation_space_fit",
        name_cn="安装与空间适配",
        candidate_type="value_theme",
        definition_cn="用户相信房型、安装位置和预算条件下能装得下、用得上。",
        terms_by_domain={
            "param": ["wall", "floor", "size", "安装", "挂机", "柜机", "内机", "外机"],
            "claim": ["installation_design", "安装", "小巧", "空间", "柜机", "挂机"],
            "comment": ["安装", "空间", "小房间", "租房", "位置", "外机", "内机"],
            "semantic_reference": ["install", "space_fit", "renter", "small_room", "安装", "空间"],
        },
        decision_question_cn="这个主题是否代表空间/安装适配，而不是安装服务本身？",
        weak_boundary_cn="安装、送装、售后只能做辅助或风险，不能单独成为产品核心理由。",
    ),
    CandidateLens(
        code="operation_maintenance_convenience",
        name_cn="操作维护省心",
        candidate_type="value_theme",
        definition_cn="用户减少清洁、控制、调温和日常维护成本。",
        terms_by_domain={
            "param": ["self", "clean", "wifi", "app", "voice", "smart", "自清洁", "智控", "语音", "远程"],
            "claim": ["smart_control", "durability_quality", "自清洁", "防霉", "智能", "远程", "app"],
            "comment": ["自清洁", "清洁", "防霉", "智能", "远程", "app", "控制", "方便"],
            "semantic_reference": ["smart", "remote", "maintenance", "reliable", "智能", "省心"],
            "claim_value": ["smart_control", "durability_quality", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表操作和维护省心，而不是智能口号？",
    ),
    CandidateLens(
        code="budget_configuration_efficiency",
        name_cn="预算配置效率",
        candidate_type="value_theme",
        definition_cn="用户在预算内获得足够的核心冷暖、能效或舒适配置。",
        terms_by_domain={
            "claim": ["price_value", "性价比", "价格", "划算", "补贴", "低价"],
            "comment": ["性价比", "划算", "便宜", "价格", "预算", "值"],
            "market": ["low", "mid_low", "same_pool_price_percentile", "same_pool_volume_percentile", "sales"],
            "claim_value": ["price", "value", "sales_driver_estimated"],
        },
        decision_question_cn="这个主题是否代表预算内配置获得感，而不是厂家一句性价比？",
        weak_boundary_cn="只有价格、补贴或 price_value 表达时，只能作为弱表达候选。",
    ),
    CandidateLens(
        code="seasonal_reliability",
        name_cn="季节和极端天气可靠性",
        candidate_type="value_theme",
        definition_cn="用户相信夏季高温、冬季低温、梅雨潮湿等季节压力下更稳定。",
        terms_by_domain={
            "param": ["dehumid", "heating", "cooling", "humidity", "除湿", "制热", "制冷", "防冻"],
            "claim": ["除湿", "速冷", "速热", "低温", "高温", "temperature_performance", "durability_quality"],
            "comment": ["夏天", "冬天", "梅雨", "潮湿", "除湿", "制热", "制冷", "稳定"],
            "semantic_reference": ["reliable", "season", "dehumid", "长期", "可靠"],
        },
        decision_question_cn="这个主题是否代表季节可靠性，而不是泛化品质宣传？",
    ),
)


PURCHASE_REASON_LENSES: tuple[CandidateLens, ...] = (
    CandidateLens(
        code="room_size_capacity_match_reduces_risk",
        name_cn="匹数空间匹配降低买小风险",
        candidate_type="purchase_reason",
        definition_cn="用户通过匹数、能力和空间任务判断这台空调不容易买小或不够用。",
        related_value_theme_codes=("cooling_heating_capacity_assurance", "installation_space_fit"),
        related_task_hint_cn="房间面积匹配、卧室/客厅选型。",
        required_logic_cn="需要能力参数或安装形态 + 空间/任务/市场参照。",
        weak_boundary_cn="只有型号或匹数字样，不足以成为核心购买理由。",
        decision_question_cn="这个 SKU 是否能降低用户买小、买错空间的风险？",
        terms_by_domain={
            "param": ["capacity", "匹", "制冷量", "制热量", "风量", "72", "35", "26"],
            "claim": ["temperature_performance", "大风量", "匹", "制冷", "制热"],
            "comment": ["够用", "房间", "客厅", "卧室", "制冷快", "制热"],
            "semantic_reference": ["large_space", "small_room", "install_space", "coverage", "空间"],
            "market": ["same_pool_volume_percentile", "sales_volume_total"],
        },
    ),
    CandidateLens(
        code="large_space_one_step_cooling_heating",
        name_cn="大空间冷暖一步到位",
        candidate_type="purchase_reason",
        definition_cn="面向客厅或大空间，SKU 用大匹数、柜机/大风量和市场承接解释一步到位。",
        related_value_theme_codes=("large_space_coverage", "cooling_heating_capacity_assurance"),
        related_task_hint_cn="客厅、大卧室、大空间覆盖。",
        required_logic_cn="需要大空间任务 + 能力/柜机事实 + 评论或市场承接。",
        weak_boundary_cn="只有柜机或大匹数标签时不能强判。",
        decision_question_cn="这个 SKU 是否能解释大空间冷暖为什么一步到位？",
        terms_by_domain={
            "param": ["72", "88", "3匹", "柜机", "floor", "large", "风量", "制冷量"],
            "claim": ["大空间", "大风量", "客厅", "柜机", "temperature_performance"],
            "comment": ["客厅", "大空间", "风量", "制冷快", "够用"],
            "semantic_reference": ["large_space", "living", "floor", "coverage"],
            "market": ["high", "sales_volume_total", "same_pool_volume_percentile"],
        },
    ),
    CandidateLens(
        code="cooling_heating_performance_justifies_price",
        name_cn="冷暖效果解释更高价格",
        candidate_type="purchase_reason",
        definition_cn="在中高/高价格位置，SKU 用冷暖能力、稳定性和用户感知解释更高价格。",
        related_value_theme_codes=("cooling_heating_capacity_assurance", "seasonal_reliability"),
        related_task_hint_cn="高价升级、极端天气、冷暖能力优先。",
        required_logic_cn="需要高价格位置 + 冷暖能力事实 + 评论、M12C 或市场承接。",
        weak_boundary_cn="只有高价或能力口号，没有体验/市场补证时不能成立。",
        decision_question_cn="这个 SKU 的冷暖效果是否足以解释更高价格？",
        terms_by_domain={
            "param": ["capacity", "cooling", "heating", "制冷量", "制热量", "apf", "风量"],
            "claim": ["temperature_performance", "速冷", "速热", "大风量", "制冷", "制热"],
            "comment": ["制冷快", "制热", "够用", "暖和", "降温"],
            "semantic_reference": ["reliable", "large_space", "coverage", "冷暖"],
            "market": ["high", "mid_high", "price_band", "sales_volume_total"],
            "claim_value": ["temperature_performance", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="long_term_energy_saving_offsets_price",
        name_cn="长期省电抵消更高价格",
        candidate_type="purchase_reason",
        definition_cn="用户愿意为高能效多花钱，因为长期省电可以解释使用成本。",
        related_value_theme_codes=("energy_cost_efficiency", "budget_configuration_efficiency"),
        related_task_hint_cn="长期使用、家庭省电、一级能效升级。",
        required_logic_cn="需要能效/APF 事实 + 长期使用任务或省电评论 + 价格位置/M12C 补证。",
        weak_boundary_cn="只有一级能效口号时封顶弱表达。",
        decision_question_cn="这个 SKU 是否能解释长期省电抵消更高价格？",
        terms_by_domain={
            "param": ["apf", "能效", "一级", "变频", "energy"],
            "claim": ["energy_efficiency", "一级能效", "省电", "节能", "变频"],
            "comment": ["省电", "电费", "节能", "耗电"],
            "semantic_reference": ["energy", "long_use", "saver", "长期"],
            "market": ["high", "mid_high", "price_band"],
            "claim_value": ["energy_efficiency", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="same_price_efficiency_capacity_gain",
        name_cn="同价位能效/能力获得感",
        candidate_type="purchase_reason",
        definition_cn="在同价位池里，SKU 用能效、冷暖能力或销量承接解释选它更划算。",
        related_value_theme_codes=("budget_configuration_efficiency", "energy_cost_efficiency", "cooling_heating_capacity_assurance"),
        related_task_hint_cn="预算有限、同价位比较、主流换新。",
        required_logic_cn="需要价格/市场证据 + 能效或能力事实；只有性价比表达不够。",
        weak_boundary_cn="只有 price_value、补贴或低价表达时封顶弱表达。",
        decision_question_cn="这个 SKU 是否在同价位中提供更可解释的能效/能力获得感？",
        terms_by_domain={
            "param": ["apf", "能效", "capacity", "制冷量", "风量", "变频"],
            "claim": ["price_value", "energy_efficiency", "temperature_performance", "性价比", "价格"],
            "comment": ["性价比", "划算", "省电", "够用", "制冷"],
            "market": ["low", "mid_low", "same_pool_price_percentile", "same_pool_volume_percentile"],
            "claim_value": ["sales_driver_estimated", "price", "value"],
        },
    ),
    CandidateLens(
        code="sleep_room_quiet_comfort_assurance",
        name_cn="卧室睡眠更安静舒适",
        candidate_type="purchase_reason",
        definition_cn="卧室睡眠场景下，SKU 用低噪、睡眠模式、风感和评论证明更安静舒适。",
        related_value_theme_codes=("sleep_quiet_comfort", "comfortable_airflow_health"),
        related_task_hint_cn="卧室、夜间睡眠、静音舒适。",
        required_logic_cn="需要静音/风感事实 + 卧室/睡眠任务或评论。",
        weak_boundary_cn="只有静音卖点，没有噪音参数、任务或评论时封顶辅助/弱表达。",
        decision_question_cn="这个 SKU 是否能解释卧室睡眠更安静舒适？",
        terms_by_domain={
            "param": ["noise", "db", "sleep", "静音", "噪音"],
            "claim": ["静音", "睡眠", "airflow_comfort"],
            "comment": ["安静", "噪音", "睡觉", "睡眠", "卧室", "不吵"],
            "semantic_reference": ["sleep", "quiet", "bedroom", "卧室"],
            "claim_value": ["airflow_comfort", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="elderly_child_soft_wind_comfort",
        name_cn="老人儿童房柔风不直吹",
        candidate_type="purchase_reason",
        definition_cn="老人儿童或家庭舒适场景下，柔风、防直吹和风感评论降低不适风险。",
        related_value_theme_codes=("comfortable_airflow_health", "sleep_quiet_comfort"),
        related_task_hint_cn="老人儿童、卧室、柔风不直吹。",
        required_logic_cn="需要柔风/防直吹事实 + 老人儿童/卧室任务或风感评论。",
        weak_boundary_cn="只有柔风或防直吹表达，缺场景/评论时封顶辅助。",
        decision_question_cn="这个 SKU 是否能解释老人儿童房柔风不直吹？",
        terms_by_domain={
            "param": ["soft", "wind", "swing", "柔风", "防直吹", "扫风"],
            "claim": ["airflow_comfort", "柔风", "防直吹", "舒适风"],
            "comment": ["不直吹", "柔风", "风感", "老人", "孩子", "舒服"],
            "semantic_reference": ["soft_wind", "child", "elder", "comfort"],
            "claim_value": ["airflow_comfort", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="fresh_air_health_reduces_stuffy_risk",
        name_cn="新风/净化减少闷和空气担忧",
        candidate_type="purchase_reason",
        definition_cn="用户用新风、净化或除菌能力降低室内闷、异味和空气健康担忧。",
        related_value_theme_codes=("comfortable_airflow_health", "operation_maintenance_convenience"),
        related_task_hint_cn="健康空气、闷和异味、新风净化。",
        required_logic_cn="需要新风/净化参数或事实 + 空气评论/任务或 M12C。",
        weak_boundary_cn="只有新风/净化口号，没有风量/滤网/评论时封顶弱表达。",
        decision_question_cn="这个 SKU 是否能解释减少闷和空气健康担忧？",
        terms_by_domain={
            "param": ["fresh", "filter", "sterili", "新风", "净化", "除菌"],
            "claim": ["health_clean_air", "新风", "净化", "除菌"],
            "comment": ["新风", "空气", "闷", "异味", "净化", "除菌"],
            "semantic_reference": ["health", "fresh", "air", "空气"],
            "claim_value": ["health_clean_air", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="humidity_dehumidification_reassurance",
        name_cn="潮湿环境除湿更安心",
        candidate_type="purchase_reason",
        definition_cn="梅雨或潮湿环境下，除湿和季节可靠性降低使用担忧。",
        related_value_theme_codes=("seasonal_reliability", "comfortable_airflow_health"),
        related_task_hint_cn="潮湿、梅雨、除湿。",
        required_logic_cn="需要除湿能力或评论 + 季节/潮湿场景。",
        weak_boundary_cn="只有除湿字样而无评论/场景补证时不能强判。",
        decision_question_cn="这个 SKU 是否能解释潮湿环境除湿更安心？",
        terms_by_domain={
            "param": ["dehumid", "humidity", "除湿", "湿度"],
            "claim": ["除湿", "干爽", "humidity"],
            "comment": ["除湿", "潮湿", "梅雨", "干爽", "湿"],
            "semantic_reference": ["dehumid", "season", "reliable"],
        },
    ),
    CandidateLens(
        code="self_cleaning_reduces_maintenance_risk",
        name_cn="自清洁/防霉降低维护风险",
        candidate_type="purchase_reason",
        definition_cn="用户通过自清洁、防霉和维护便利降低清洁、异味和长期维护风险。",
        related_value_theme_codes=("operation_maintenance_convenience", "comfortable_airflow_health"),
        related_task_hint_cn="清洁维护、防霉、长期使用。",
        required_logic_cn="需要自清洁/防霉事实 + 维护评论或健康空气场景。",
        weak_boundary_cn="只有自清洁口号时封顶辅助/弱表达。",
        decision_question_cn="这个 SKU 是否能解释自清洁/防霉降低维护风险？",
        terms_by_domain={
            "param": ["clean", "self", "mildew", "自清洁", "防霉"],
            "claim": ["自清洁", "防霉", "durability_quality", "health_clean_air"],
            "comment": ["自清洁", "清洁", "防霉", "异味", "维护"],
            "semantic_reference": ["maintenance", "reliable", "health"],
        },
    ),
    CandidateLens(
        code="small_room_installation_fit",
        name_cn="小房间/租房安装适配",
        candidate_type="purchase_reason",
        definition_cn="小房间、租房或安装受限场景下，SKU 用挂机/小匹数/价格和安装适配降低选择摩擦。",
        related_value_theme_codes=("installation_space_fit", "budget_configuration_efficiency"),
        related_task_hint_cn="租房、小房间、安装受限。",
        required_logic_cn="需要安装/小空间事实 + 租房/小房间任务或低价市场承接。",
        weak_boundary_cn="只有安装服务或低价时不能强判。",
        decision_question_cn="这个 SKU 是否能解释小房间/租房安装更适配？",
        terms_by_domain={
            "param": ["26", "35", "wall", "挂机", "小", "安装"],
            "claim": ["installation_design", "安装", "小巧", "挂机", "price_value"],
            "comment": ["小房间", "租房", "安装", "卧室", "便宜"],
            "semantic_reference": ["renter", "small_room", "install", "space_fit"],
            "market": ["low", "mid_low", "same_pool_price_percentile"],
        },
    ),
    CandidateLens(
        code="smart_remote_control_less_friction",
        name_cn="远程/智能控制减少操作摩擦",
        candidate_type="purchase_reason",
        definition_cn="用户通过 App、远程、语音或智能控制减少日常操作成本。",
        related_value_theme_codes=("operation_maintenance_convenience",),
        related_task_hint_cn="远程开关、智能家居、日常调温。",
        required_logic_cn="需要智能/远程事实 + 评论或智能任务补证。",
        weak_boundary_cn="只有智能口号时封顶弱表达。",
        decision_question_cn="这个 SKU 是否能解释远程/智能控制减少操作摩擦？",
        terms_by_domain={
            "param": ["wifi", "app", "voice", "smart", "智能", "远程", "语音"],
            "claim": ["smart_control", "智能", "远程", "app", "语音"],
            "comment": ["智能", "远程", "app", "语音", "控制", "方便"],
            "semantic_reference": ["smart", "remote", "operation"],
            "claim_value": ["smart_control", "sales_driver_estimated"],
        },
    ),
    CandidateLens(
        code="low_price_core_ac_experience_intact",
        name_cn="低价不明显牺牲核心冷暖体验",
        candidate_type="purchase_reason",
        definition_cn="在低/中低价位置，SKU 用冷暖能力、能效、评论或销量证明低价不是明显牺牲核心体验。",
        related_value_theme_codes=("budget_configuration_efficiency", "cooling_heating_capacity_assurance"),
        related_task_hint_cn="预算优先、补贴购买、入门换新。",
        required_logic_cn="需要低价位置 + 冷暖/能效事实或评论/销量承接。",
        weak_boundary_cn="只有低价、补贴或 price_value 表达时，不能进入核心产品理由。",
        decision_question_cn="这个 SKU 是否能解释低价下核心冷暖体验仍然够用？",
        terms_by_domain={
            "param": ["capacity", "apf", "能效", "制冷", "制热", "变频"],
            "claim": ["price_value", "temperature_performance", "energy_efficiency", "性价比", "低价"],
            "comment": ["性价比", "便宜", "划算", "制冷", "省电", "够用"],
            "market": ["low", "mid_low", "same_pool_price_percentile", "same_pool_volume_percentile", "sales"],
            "claim_value": ["sales_driver_estimated", "price", "value"],
        },
    ),
)


def main() -> None:
    args = parse_args()
    database_url = args.database_url or os.getenv("CATFORGE_DATABASE_URL")
    if not database_url:
        raise SystemExit("CATFORGE_DATABASE_URL is required.")

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parents[1] / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    with engine.connect() as conn:
        payload = extract_candidates(conn, args)

    json_path = output_dir / "M12D_AC_G02_value_theme_purchase_reason_candidates.json"
    md_path = output_dir / "M12D_AC_G02_value_theme_purchase_reason_candidate_report.md"
    payload["artifacts"] = {"json_path": str(json_path), "markdown_path": str(md_path)}
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default="")
    parser.add_argument("--project-id", default=PROJECT_ID)
    parser.add_argument("--category-code", default=CATEGORY_CODE)
    parser.add_argument("--batch-id", default=BATCH_ID)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-limit", type=int, default=MAX_SAMPLE_SKUS)
    return parser.parse_args()


def extract_candidates(conn: Any, args: argparse.Namespace) -> dict[str, Any]:
    source = {
        "project_id": args.project_id,
        "category_code": args.category_code,
        "batch_id": args.batch_id,
        "market_window": MARKET_WINDOW,
        "analysis_population": ANALYSIS_POPULATION,
    }
    sku_evidence = load_sku_evidence(conn, source)
    coverage = load_coverage(conn, source)
    readiness = load_readiness(conn, source)
    role_distribution = load_m12c_role_distribution(conn, source)
    claim_dimension_distribution = load_claim_dimension_distribution(conn, source)
    value_theme_candidates = evaluate_lenses(VALUE_THEME_LENSES, sku_evidence, args.sample_limit)
    purchase_reason_candidates = evaluate_lenses(PURCHASE_REASON_LENSES, sku_evidence, args.sample_limit)
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "AC-M12D-G02 value theme / purchase reason candidate extraction",
        "source": source,
        "script_contract": {
            "read_only": True,
            "writes_database": False,
            "publishes_taxonomy": False,
            "category_isolation": "category_code=AC and product_category=AC where present",
            "tv_taxonomy_reuse": False,
        },
        "coverage": coverage,
        "readiness_segments": readiness,
        "m12c_role_distribution": role_distribution,
        "m04c_claim_dimension_distribution": claim_dimension_distribution,
        "value_theme_candidates": value_theme_candidates,
        "purchase_reason_candidates": purchase_reason_candidates,
        "sample_sku_matrix": sample_sku_matrix(sku_evidence),
        "boundary_notes": boundary_notes(),
    }


def load_sku_evidence(conn: Any, source: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    skus: dict[str, dict[str, Any]] = {}
    base_rows = conn.execute(
        text(
            """
            select sku_code, brand_name, model_name, price_band_category, price_band_size,
                   price_wavg, sales_volume_total, sales_amount_total, same_pool_price_percentile,
                   same_pool_volume_percentile, active_week_count
            from core3_sku_market_profile
            where project_id = :project_id
              and category_code = :category_code
              and batch_id = :batch_id
              and is_current is true
              and rule_version = 'm07_market_profile_v1'
              and analysis_window = :market_window
            order by sku_code
            """
        ),
        source,
    ).mappings()
    for row in base_rows:
        sku_code = str(row["sku_code"])
        skus[sku_code] = {
            "sku_code": sku_code,
            "brand_name": row.get("brand_name"),
            "model_name": row.get("model_name"),
            "market": json_ready(dict(row)),
            "domains": defaultdict(list),
            "domain_counts": Counter(),
            "m12c_roles": Counter(),
            "missing_modules": set(),
        }
        append_domain_text(skus[sku_code], "market", dict(row))

    for spec in query_specs():
        rows = conn.execute(text(spec["sql"]), source).mappings()
        seen_skus: set[str] = set()
        for row in rows:
            sku_code = str(row["sku_code"])
            if sku_code not in skus:
                continue
            seen_skus.add(sku_code)
            payload = dict(row)
            append_domain_text(skus[sku_code], spec["domain"], payload)
            skus[sku_code]["domain_counts"][spec["module"]] += 1
            if spec["module"] == "M12C":
                role = str(row.get("claim_value_role") or "")
                if role:
                    skus[sku_code]["m12c_roles"][role] += 1
        for sku_code, sku in skus.items():
            if spec["module"] in MISSING_MODULES_TO_REPORT and sku_code not in seen_skus:
                sku["missing_modules"].add(spec["module"])

    for sku in skus.values():
        sku["domains"] = dict(sku["domains"])
        sku["domain_counts"] = dict(sku["domain_counts"])
        sku["m12c_roles"] = dict(sku["m12c_roles"])
        sku["missing_modules"] = sorted(set(sku["missing_modules"]))
    return skus


def query_specs() -> tuple[dict[str, str], ...]:
    return (
        {
            "domain": "param",
            "module": "M03B",
            "sql": """
                select sku_code, model_name, null as brand_name,
                       param_values_json, known_param_count, unknown_param_count, quality_summary_json
                from core3_sku_param_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and batch_id = :batch_id
                  and rule_version = 'm03b_ac_param_profile_v0.1'
            """,
        },
        {
            "domain": "claim",
            "module": "M04C",
            "sql": """
                select sku_code, model_name, brand_name, claim_codes, fact_claim_codes,
                       service_claim_codes, dimension_profile_json, dimension_position_profile_json,
                       claim_summary_json, raw_claim_count, fact_claim_count, service_separate_claim_count
                from core3_sku_claim_fact_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm04c_ac_claim_fact_profile_v0.1'
            """,
        },
        {
            "domain": "claim",
            "module": "M04C_fact",
            "sql": """
                select sku_code, model_name, brand_name, claim_code, claim_name, claim_dimension,
                       claim_subtype, claim_kind, param_support_status, param_support_level,
                       supporting_param_codes, clean_claim_text, fact_claim_flag, service_separate_flag,
                       wtp_input_guard
                from core3_sku_claim_fact
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm04c_ac_claim_fact_profile_v0.1'
            """,
        },
        {
            "domain": "comment",
            "module": "M05C",
            "sql": """
                select sku_code, model_name, brand_name, dimension_summary_json, signal_summary_json,
                       claim_comment_support_json, param_comment_support_json, polarity_summary_json,
                       evidence_examples_json, supported_param_codes, supported_claim_codes,
                       positive_sentence_count, negative_sentence_count, comment_sentence_count
                from core3_sku_comment_fact_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm05c_ac_comment_fact_profile_v0.1'
            """,
        },
        {
            "domain": "comment",
            "module": "M05C_atom",
            "sql": """
                select sku_code, model_name, brand_name, dimension_code, dimension_name,
                       subdimension_code, subdimension_name, polarity, evidence_strength,
                       supported_param_codes, supported_claim_codes, left(clean_comment_text, 80) as comment_excerpt
                from core3_comment_fact_atom
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm05c_ac_comment_fact_profile_v0.1'
            """,
        },
        {
            "domain": "semantic_reference",
            "module": "M09C",
            "sql": """
                select sku_code, model_name, brand_name, primary_user_task_code,
                       secondary_user_task_codes_json, comment_observed_task_codes_json,
                       brand_claimed_task_codes_json, latent_capability_task_codes_json,
                       drag_factor_task_codes_json, user_task_summary_json
                from core3_m09c_sku_user_task_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm09c_ac_user_task_profile_v0.1'
            """,
        },
        {
            "domain": "semantic_reference",
            "module": "M10C",
            "sql": """
                select sku_code, model_name, brand_name, primary_target_group_code,
                       secondary_target_group_codes_json, comment_observed_group_codes_json,
                       brand_claimed_group_codes_json, latent_group_codes_json,
                       unmet_group_need_codes_json, target_group_summary_json
                from core3_m10c_sku_target_group_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm10c_ac_target_group_profile_v0.1'
            """,
        },
        {
            "domain": "semantic_reference",
            "module": "M11C",
            "sql": """
                select sku_code, model_name, brand_name, primary_battlefield_code,
                       secondary_battlefield_codes_json, opportunity_battlefield_codes_json,
                       drag_factor_battlefield_codes_json, battlefield_summary_json
                from core3_sku_value_battlefield_profile
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and is_current is true
                  and rule_version = 'm11c_ac_value_battlefield_profile_v0.1'
            """,
        },
        {
            "domain": "semantic_market",
            "module": "M11D",
            "sql": """
                select sku_code, brand_name, model_name, dimension_type, dimension_code, dimension_name,
                       relation_status, allocation_role, allocated_sales_volume, allocated_sales_amount,
                       allocation_confidence
                from core3_semantic_market_sku_contribution
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and analysis_population = :analysis_population
                  and market_window = :market_window
                  and is_current is true
                  and rule_version = 'm11d_semantic_market_allocation_v0.1'
            """,
        },
        {
            "domain": "claim_value",
            "module": "M12C",
            "sql": """
                select sku_code, brand_name, model_name, claim_code, claim_name, claim_dimension,
                       claim_value_role, context_type, context_code, context_name,
                       claim_evidence_strength, param_support_strength, comment_support_strength,
                       semantic_support_strength, contribution_share_in_sku, attribution_confidence,
                       reason_cn, quality_flags_json
                from core3_sku_claim_value_quantification
                where project_id = :project_id
                  and category_code = :category_code
                  and product_category = :category_code
                  and batch_id = :batch_id
                  and analysis_population = 'claim_value_ready_with_comment'
                  and market_window = :market_window
                  and is_current is true
                  and rule_version = 'm12c_claim_value_quantification_v0.1'
            """,
        },
    )


def load_coverage(conn: Any, source: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            with counts as (
              select 'M03B' module, count(distinct sku_code) sku_count, count(*) row_count
              from core3_sku_param_profile
              where project_id=:project_id and category_code=:category_code and batch_id=:batch_id and rule_version='m03b_ac_param_profile_v0.1'
              union all select 'M04C', count(distinct sku_code), count(*)
              from core3_sku_claim_fact_profile
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and rule_version='m04c_ac_claim_fact_profile_v0.1'
              union all select 'M05C', count(distinct sku_code), count(*)
              from core3_sku_comment_fact_profile
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and rule_version='m05c_ac_comment_fact_profile_v0.1'
              union all select 'M07', count(distinct sku_code), count(*)
              from core3_sku_market_profile
              where project_id=:project_id and category_code=:category_code and batch_id=:batch_id and is_current=true and analysis_window=:market_window and rule_version='m07_market_profile_v1'
              union all select 'M09C', count(distinct sku_code), count(*)
              from core3_m09c_sku_user_task_profile
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and rule_version='m09c_ac_user_task_profile_v0.1'
              union all select 'M10C', count(distinct sku_code), count(*)
              from core3_m10c_sku_target_group_profile
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and rule_version='m10c_ac_target_group_profile_v0.1'
              union all select 'M11C', count(distinct sku_code), count(*)
              from core3_sku_value_battlefield_profile
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and rule_version='m11c_ac_value_battlefield_profile_v0.1'
              union all select 'M11D', count(distinct sku_code), count(*)
              from core3_semantic_market_sku_contribution
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and analysis_population=:analysis_population and market_window=:market_window and rule_version='m11d_semantic_market_allocation_v0.1'
              union all select 'M12C', count(distinct sku_code), count(*)
              from core3_sku_claim_value_quantification
              where project_id=:project_id and category_code=:category_code and product_category=:category_code and batch_id=:batch_id and is_current=true and analysis_population='claim_value_ready_with_comment' and market_window=:market_window and rule_version='m12c_claim_value_quantification_v0.1'
            )
            select * from counts order by module
            """
        ),
        source,
    ).mappings()
    return [json_ready(dict(row)) for row in rows]


def load_readiness(conn: Any, source: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            with base as (
              select distinct sku_code
              from core3_sku_market_profile
              where project_id=:project_id and category_code=:category_code and batch_id=:batch_id
                and is_current=true and rule_version='m07_market_profile_v1' and analysis_window=:market_window
            ), flags as (
              select b.sku_code,
                     exists(select 1 from core3_sku_comment_fact_profile x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.rule_version='m05c_ac_comment_fact_profile_v0.1') has_m05c,
                     exists(select 1 from core3_m09c_sku_user_task_profile x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.rule_version='m09c_ac_user_task_profile_v0.1') has_m09c,
                     exists(select 1 from core3_m10c_sku_target_group_profile x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.rule_version='m10c_ac_target_group_profile_v0.1') has_m10c,
                     exists(select 1 from core3_sku_value_battlefield_profile x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.rule_version='m11c_ac_value_battlefield_profile_v0.1') has_m11c,
                     exists(select 1 from core3_semantic_market_sku_contribution x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.analysis_population=:analysis_population and x.market_window=:market_window and x.rule_version='m11d_semantic_market_allocation_v0.1') has_m11d,
                     exists(select 1 from core3_sku_claim_value_quantification x where x.project_id=:project_id and x.category_code=:category_code and x.product_category=:category_code and x.batch_id=:batch_id and x.sku_code=b.sku_code and x.is_current=true and x.analysis_population='claim_value_ready_with_comment' and x.market_window=:market_window and x.rule_version='m12c_claim_value_quantification_v0.1') has_m12c
              from base b
            )
            select case
                     when has_m05c and has_m09c and has_m10c and has_m11c and has_m11d and has_m12c then 'ready_strong_candidate'
                     when not has_m05c then 'facts_market_only_comment_missing'
                     when not has_m11d or not has_m12c then 'other_degraded'
                     else 'other'
                   end segment,
                   count(*) sku_count
            from flags
            group by 1
            order by sku_count desc, segment
            """
        ),
        source,
    ).mappings()
    return [json_ready(dict(row)) for row in rows]


def load_m12c_role_distribution(conn: Any, source: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select claim_value_role, count(*) row_count, count(distinct sku_code) sku_count, count(distinct claim_code) claim_count
            from core3_sku_claim_value_quantification
            where project_id=:project_id and category_code=:category_code and product_category=:category_code
              and batch_id=:batch_id and is_current=true and analysis_population='claim_value_ready_with_comment'
              and market_window=:market_window and rule_version='m12c_claim_value_quantification_v0.1'
            group by 1
            order by row_count desc, claim_value_role
            """
        ),
        source,
    ).mappings()
    return [json_ready(dict(row)) for row in rows]


def load_claim_dimension_distribution(conn: Any, source: Mapping[str, str]) -> list[dict[str, Any]]:
    rows = conn.execute(
        text(
            """
            select claim_dimension, count(*) claim_fact_rows, count(distinct sku_code) sku_count
            from core3_sku_claim_fact
            where project_id=:project_id and category_code=:category_code and product_category=:category_code
              and batch_id=:batch_id and is_current=true and rule_version='m04c_ac_claim_fact_profile_v0.1'
            group by 1
            order by sku_count desc, claim_dimension
            """
        ),
        source,
    ).mappings()
    return [json_ready(dict(row)) for row in rows]


def evaluate_lenses(
    lenses: Iterable[CandidateLens],
    sku_evidence: Mapping[str, Mapping[str, Any]],
    sample_limit: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for lens in lenses:
        sku_matches: list[dict[str, Any]] = []
        status_counts: Counter[str] = Counter()
        domain_counts: Counter[str] = Counter()
        for sku in sku_evidence.values():
            match = evaluate_lens_for_sku(lens, sku)
            if not match:
                continue
            sku_matches.append(match)
            status_counts[match["candidate_status"]] += 1
            domain_counts.update(match["matched_domains"])
        sku_matches.sort(key=lambda item: (item["raw_score"], item["positive_m12c_count"], item["market_sales_volume"] or 0), reverse=True)
        candidates.append(
            {
                "code": lens.code,
                "name_cn": lens.name_cn,
                "candidate_type": lens.candidate_type,
                "definition_cn": lens.definition_cn,
                "decision_question_cn": lens.decision_question_cn,
                "related_value_theme_codes": list(lens.related_value_theme_codes),
                "related_task_hint_cn": lens.related_task_hint_cn,
                "required_logic_cn": lens.required_logic_cn,
                "weak_boundary_cn": lens.weak_boundary_cn,
                "matched_sku_count": len(sku_matches),
                "status_counts": dict(status_counts),
                "domain_counts": dict(domain_counts),
                "sample_skus": sku_matches[:sample_limit],
                "draft_recommendation": recommend_candidate(lens, len(sku_matches), status_counts),
            }
        )
    candidates.sort(key=lambda item: (item["status_counts"].get("draft_accept", 0), item["matched_sku_count"]), reverse=True)
    return candidates


def evaluate_lens_for_sku(lens: CandidateLens, sku: Mapping[str, Any]) -> dict[str, Any] | None:
    domain_matches: dict[str, list[str]] = {}
    for domain, terms in lens.terms_by_domain.items():
        text_blob = "\n".join(str(item) for item in sku.get("domains", {}).get(domain, []))
        matched = match_terms(text_blob, terms)
        if matched:
            domain_matches[domain] = matched[:MAX_TERMS_PER_DOMAIN]
    if not domain_matches:
        return None
    matched_domains = sorted(domain_matches)
    raw_score = round(sum(DOMAIN_WEIGHTS.get(domain, 1.0) for domain in matched_domains), 2)
    role_counts = Counter(sku.get("m12c_roles") or {})
    positive_count = sum(role_counts.get(role, 0) for role in POSITIVE_M12C_ROLES)
    weak_count = sum(role_counts.get(role, 0) for role in WEAK_M12C_ROLES)
    risk_count = sum(role_counts.get(role, 0) for role in RISK_M12C_ROLES)
    missing_modules = set(sku.get("missing_modules") or [])
    candidate_status = classify_candidate_status(
        lens,
        matched_domains,
        raw_score,
        positive_count,
        weak_count,
        risk_count,
        missing_modules,
    )
    market = sku.get("market") or {}
    return {
        "sku_code": sku.get("sku_code"),
        "brand_name": sku.get("brand_name"),
        "model_name": sku.get("model_name"),
        "matched_domains": matched_domains,
        "matched_terms": domain_matches,
        "raw_score": raw_score,
        "candidate_status": candidate_status,
        "positive_m12c_count": positive_count,
        "weak_m12c_count": weak_count,
        "risk_m12c_count": risk_count,
        "missing_modules": sorted(missing_modules),
        "market_price_band": market.get("price_band_category"),
        "market_sales_volume": market.get("sales_volume_total"),
    }


def classify_candidate_status(
    lens: CandidateLens,
    matched_domains: list[str],
    raw_score: float,
    positive_count: int,
    weak_count: int,
    risk_count: int,
    missing_modules: set[str],
) -> str:
    if lens.candidate_type == "value_theme":
        if raw_score >= 6 and len(matched_domains) >= 3:
            return "theme_strong_candidate"
        if matched_domains == ["claim"] or matched_domains == ["market"]:
            return "theme_weak_boundary"
        return "theme_review"
    if "M12C" in missing_modules or "M11D" in missing_modules:
        return "degraded_missing_m12c_or_m11d"
    if matched_domains == ["claim"] or set(matched_domains).issubset({"claim", "market"}):
        return "weak_boundary"
    if risk_count > positive_count and risk_count >= weak_count:
        return "risk_review"
    if raw_score >= 7 and len(matched_domains) >= 4 and positive_count > 0:
        return "draft_accept"
    if raw_score >= 5 and len(matched_domains) >= 3:
        return "review"
    return "weak_boundary"


def recommend_candidate(lens: CandidateLens, matched_count: int, status_counts: Mapping[str, int]) -> str:
    if lens.candidate_type == "value_theme":
        strong = status_counts.get("theme_strong_candidate", 0)
        if strong >= 20:
            return "draft_accept"
        if matched_count >= 20:
            return "review"
        return "low_coverage_review"
    if status_counts.get("draft_accept", 0) >= 10:
        return "draft_accept"
    if status_counts.get("review", 0) + status_counts.get("risk_review", 0) >= 10:
        return "review"
    return "weak_or_low_coverage"


def sample_sku_matrix(sku_evidence: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    sample_order = [
        "AC00038063",
        "AC00028640",
        "AC00029751",
        "AC00036139",
        "AC00038662",
        "AC00028642",
        "AC00036739",
        "AC00036333",
        "AC00035996",
        "AC00036020",
        "AC00038680",
        "AC00034731",
        "AC00039165",
        "AC00038066",
        "AC00034959",
    ]
    rows: list[dict[str, Any]] = []
    for sku_code in sample_order:
        sku = sku_evidence.get(sku_code)
        if not sku:
            continue
        rows.append(
            {
                "sku_code": sku_code,
                "brand_name": sku.get("brand_name"),
                "model_name": sku.get("model_name"),
                "market": sku.get("market"),
                "domain_counts": sku.get("domain_counts"),
                "m12c_roles": sku.get("m12c_roles"),
                "missing_modules": sku.get("missing_modules"),
            }
        )
    return rows


def boundary_notes() -> list[str]:
    return [
        "G02 只提炼候选，不发布标准 taxonomy。",
        "M03B 查询必须限定 category_code=AC，避免 AC 前缀旧 TV 批次污染。",
        "只有 price_value、补贴、服务履约、安装售后或认证背书时，候选必须停留在 weak_boundary。",
        "M12C 缺失或只有 weak/risk role 时，不得作为后续 core_payment 的正向证明。",
        "当前 AC M12C 正向角色主要是 sales_driver_estimated，应作为销量转化证据而非高价支付理由。",
    ]


def append_domain_text(sku: dict[str, Any], domain: str, payload: Mapping[str, Any]) -> None:
    sku["domains"][domain].append(json.dumps(json_ready(payload), ensure_ascii=False, sort_keys=True))


def match_terms(text_blob: str, terms: Iterable[str]) -> list[str]:
    normalized = normalize_text(text_blob)
    matched: list[str] = []
    for term in terms:
        if normalize_text(term) in normalized:
            matched.append(term)
    return list(dict.fromkeys(matched))


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).lower())


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    return value


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D AC-G02 价值主题与购买理由候选提炼报告",
        "",
        f"- 生成时间 UTC：{payload['generated_at_utc']}",
        f"- 数据源：205 `catforge_dev` / `{payload['source']['project_id']}` / `{payload['source']['category_code']}`",
        f"- 批次：`{payload['source']['batch_id']}`",
        "- 脚本性质：只读 SELECT；不发布 taxonomy；不生成 M12D 画像；不修改竞品智能体。",
        "",
        "## 1. 覆盖摘要",
        "",
        "| 模块 | SKU 数 | 行数 |",
        "| --- | ---: | ---: |",
    ]
    for item in payload["coverage"]:
        lines.append(f"| {item['module']} | {item['sku_count']} | {item['row_count']} |")
    lines.extend(["", "## 2. 就绪分层", "", "| 分层 | SKU 数 |", "| --- | ---: |"])
    for item in payload["readiness_segments"]:
        lines.append(f"| `{item['segment']}` | {item['sku_count']} |")

    lines.extend(["", "## 3. M12C 角色分布", "", "| role | 行数 | SKU 数 | claim 数 |", "| --- | ---: | ---: | ---: |"])
    for item in payload["m12c_role_distribution"]:
        lines.append(
            f"| `{item['claim_value_role']}` | {item['row_count']} | {item['sku_count']} | {item['claim_count']} |"
        )

    lines.extend(["", "## 4. AC 标准价值主题候选", ""])
    lines.extend(render_candidate_table(payload["value_theme_candidates"]))
    lines.extend(["", "## 5. AC 标准购买理由候选", ""])
    lines.extend(render_candidate_table(payload["purchase_reason_candidates"]))

    lines.extend(["", "## 6. 样本 SKU 矩阵", ""])
    lines.extend(render_sample_matrix(payload["sample_sku_matrix"]))

    lines.extend(["", "## 7. G03 使用建议", ""])
    lines.extend(
        [
            "- `draft_accept` 只表示证据覆盖足够进入人审草案，不等于标准 taxonomy 已发布。",
            "- `review` 和 `risk_review` 需要在 G03 中人工判断是否拆分、合并或降级。",
            "- `weak_boundary` 主要用于定义弱表达上限，不应直接进入核心购买理由。",
            "- G03 应优先处理覆盖广、区分度够、业务解释清楚的购买理由。",
        ]
    )
    lines.extend(["", "## 8. 边界说明", ""])
    for note in payload["boundary_notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines) + "\n"


def render_candidate_table(candidates: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| code | 中文名 | 命中 SKU | 审阅建议 | 状态分布 | 主要证据域 | 样本 SKU |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    for item in candidates:
        status = ", ".join(f"{key}:{value}" for key, value in sorted(item["status_counts"].items()))
        domains = ", ".join(f"{key}:{value}" for key, value in sorted(item["domain_counts"].items()))
        samples = ", ".join(sample["sku_code"] for sample in item["sample_skus"][:5])
        lines.append(
            f"| `{item['code']}` | {item['name_cn']} | {item['matched_sku_count']} | "
            f"`{item['draft_recommendation']}` | {status or '-'} | {domains or '-'} | {samples or '-'} |"
        )
    return lines


def render_sample_matrix(samples: Iterable[Mapping[str, Any]]) -> list[str]:
    lines = [
        "| SKU | 品牌 | 型号 | 价格带 | 销量 | 缺失模块 | M12C role 摘要 |",
        "| --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for item in samples:
        market = item.get("market") or {}
        roles = item.get("m12c_roles") or {}
        role_summary = ", ".join(f"{key}:{value}" for key, value in sorted(roles.items())) or "-"
        missing = ", ".join(item.get("missing_modules") or []) or "-"
        lines.append(
            f"| `{item['sku_code']}` | {item.get('brand_name') or ''} | {item.get('model_name') or ''} | "
            f"{market.get('price_band_category') or ''}/{market.get('price_band_size') or ''} | "
            f"{market.get('sales_volume_total') or 0} | {missing} | {role_summary} |"
        )
    return lines


if __name__ == "__main__":
    main()
