"""Deterministic V5.2 separation of sellpoints, parameters, and user value."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field

from app.services.core3_real_data.analyst.claim_value_pm_category_config import (
    AC_VALUE_UNITS,
)
from app.services.core3_real_data.analyst.claim_value_pm_service import (
    PARAM_LABELS,
    TV_VALUE_UNITS,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    V4_EXTRA_VALUE_UNITS,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    CompetitorSellpointFinding,
    CompetitorSellpointFindingType,
    LayerIntegritySummary,
    LayeredSellpointAnalysis,
    ParameterClassification,
    ProductParameterAssessment,
    ProductSellpointAssessment,
    SellpointClassification,
    SellpointParameterLink,
    SellpointParameterSupportRole,
    SellpointUserValueLink,
    SourceSellpointFact,
    SourceSellpointReadResult,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_2_LAYER_MAPPING_VERSION = "sellpoint_value_layer_mapping_v5_2"

_AVAILABLE_STATUSES = {"conclusion_available", "partial_conclusion"}
_GAMING_QUOTE_PATTERNS = (
    re.compile(r"游戏[^，。；]{0,16}双丝滑", re.IGNORECASE),
    re.compile(r"游戏[^，。；]{0,16}低延迟", re.IGNORECASE),
    re.compile(r"游戏[^，。；]{0,16}流畅", re.IGNORECASE),
)
_GENERIC_BRACKET_TITLES = {
    "核心定位",
    "功能价值",
    "情感价值",
    "便捷体验",
    "差异化定位",
    "行业地位",
    "其他卖点",
}

_USER_VALUE_CN_BY_DEFINITION = {
    "tv_bright_room_dark_detail": "白天客厅画面仍清楚，暗场层次更完整、光晕更少。",
    "tv_gaming_motion_fluency": "游戏操作更跟手，高速画面更流畅、拖影更少。",
    "tv_color_picture_truth": "色彩更自然准确，人物和画面还原更真实。",
    "tv_cinema_soundstage": "对白更清楚，声场和包围感带来更强影院沉浸。",
    "tv_system_interaction_efficiency": "开机、切换、投屏和语音操作更流畅省事。",
    "tv_large_screen_immersion": "大屏观看更有临场感，客厅观影更沉浸。",
    "tv_long_viewing_comfort": "长时间观看更舒适，反光、频闪和眼疲劳更少。",
    "ac_capacity_space_fit": "制冷制热能力与房间面积更匹配。",
    "ac_energy_cost_control": "长期使用更省电，用电成本更可控。",
    "ac_sleep_quiet_comfort": "夜间运行更安静，睡眠不易被打扰。",
    "ac_comfortable_airflow": "送风更柔和，减少冷风直吹的不适。",
    "ac_clean_air_health": "空气更洁净，日常清洁和维护更省心。",
    "ac_large_space_coverage": "大空间降温升温更快，覆盖更均匀。",
    "ac_installation_fit": "安装更适配现有空间，减少尺寸和位置限制。",
    "ac_smart_operation": "远程、语音和自动调节让操作更省事。",
    "ac_seasonal_reliability": "极端天气和潮湿环境下运行更稳定。",
}


class CompetitorSellpointObservation(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_sellpoint: SourceSellpointFact
    target_has_matching_sellpoint: bool
    competitor_value_advantage: bool
    target_value_weakness: bool
    market_support: bool
    linked_value_bundle_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[SellpointValueEvidenceRef] = Field(default_factory=list)


def build_layered_sellpoint_analysis(
    *,
    category_code: Literal["TV", "AC"],
    target_sku_code: str,
    source_sellpoints: SourceSellpointReadResult,
    values: Sequence[Any],
    target_parameter_facts: Sequence[Any],
    competitor_sellpoints: Sequence[CompetitorSellpointObservation] = (),
) -> LayeredSellpointAnalysis:
    """Build a source-grounded graph without creating a product sellpoint."""

    sourced = [
        _source_fact_with_exact_quote(row)
        for row in source_sellpoints.source_sellpoints
    ]
    parameter_links = _parameter_links(sourced)
    user_value_links = _user_value_links(
        category_code=category_code,
        source_sellpoints=sourced,
        values=values,
    )
    parameter_assessments = _parameter_assessments(
        category_code=category_code,
        source_sellpoints=sourced,
        parameter_links=parameter_links,
        values=values,
        target_parameter_facts=target_parameter_facts,
    )
    sellpoint_assessments = _sellpoint_assessments(
        category_code=category_code,
        source_sellpoints=sourced,
        parameter_links=parameter_links,
        user_value_links=user_value_links,
        parameter_assessments=parameter_assessments,
        values=values,
    )
    competitor_findings = _competitor_sellpoint_findings(competitor_sellpoints)
    integrity = evaluate_layer_integrity(
        category_code=category_code,
        source_sellpoints=sourced,
        parameter_links=parameter_links,
        user_value_links=user_value_links,
        sellpoint_assessments=sellpoint_assessments,
    )
    payload = {
        "category_code": category_code,
        "target_sku_code": target_sku_code.strip().upper(),
        "source_sellpoint_state": source_sellpoints.status,
        "source_lineage": source_sellpoints.lineage,
        "source_sellpoints": sourced,
        "sellpoint_parameter_links": parameter_links,
        "sellpoint_user_value_links": user_value_links,
        "sellpoint_assessments": sellpoint_assessments,
        "parameter_assessments": parameter_assessments,
        "competitor_sellpoint_findings": competitor_findings,
        "integrity": integrity,
        "limitations": sorted(set(source_sellpoints.limitations)),
    }
    return LayeredSellpointAnalysis(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_2_LAYER_MAPPING_VERSION,
        ),
    )


def evaluate_layer_integrity(
    *,
    category_code: Literal["TV", "AC"],
    source_sellpoints: Sequence[SourceSellpointFact],
    parameter_links: Sequence[SellpointParameterLink],
    user_value_links: Sequence[SellpointUserValueLink],
    sellpoint_assessments: Sequence[ProductSellpointAssessment],
) -> LayerIntegritySummary:
    source_ids = {row.claim_fact_id for row in source_sellpoints}
    source_ids.update(
        fact_id
        for row in source_sellpoints
        for fact_id in row.merged_claim_fact_ids
    )
    assessment_ids = {
        fact_id
        for row in sellpoint_assessments
        for fact_id in row.source_sellpoint_fact_ids
    }
    link_ids = {
        row.sellpoint_fact_id for row in (*parameter_links, *user_value_links)
    }
    dangling = len((assessment_ids | link_ids) - source_ids)
    unsourced = sum(
        not set(row.source_sellpoint_fact_ids).issubset(source_ids)
        for row in sellpoint_assessments
    )
    value_codes = {
        definition.code for definition in _value_definitions(category_code)
    }
    parameter_as_sellpoint = sum(
        row.normalized_claim_code.startswith("param:")
        for row in sellpoint_assessments
    )
    value_theme_as_sellpoint = sum(
        row.normalized_claim_code in value_codes
        for row in sellpoint_assessments
    )
    quote_mismatches = sum(
        bool(row.exact_quote_cn and row.exact_quote_cn not in row.raw_claim_text)
        for row in source_sellpoints
    )
    displayed = len(sellpoint_assessments)
    return LayerIntegritySummary(
        displayed_sellpoint_count=displayed,
        sourced_sellpoint_count=displayed - unsourced,
        unsourced_sellpoint_count=unsourced,
        parameter_as_sellpoint_count=parameter_as_sellpoint,
        value_theme_as_sellpoint_count=value_theme_as_sellpoint,
        exact_quote_mismatch_count=quote_mismatches,
        dangling_sellpoint_link_count=dangling,
        source_profile_hash_mismatch_count=0,
    )


def _source_fact_with_exact_quote(
    fact: SourceSellpointFact,
) -> SourceSellpointFact:
    if fact.exact_quote_cn:
        return fact
    quote = _exact_source_quote(fact)
    return fact.model_copy(update={"exact_quote_cn": quote}) if quote else fact


def _exact_source_quote(fact: SourceSellpointFact) -> str | None:
    raw = fact.raw_claim_text
    if fact.normalized_claim_code in {
        "tv_claim_gaming_low_latency",
        "tv_claim_high_refresh_rate",
        "tv_claim_high_refresh",
        "tv_claim_hdmi21_connectivity",
    }:
        for pattern in _GAMING_QUOTE_PATTERNS:
            match = pattern.search(raw)
            if match:
                return match.group(0)
    bracket = re.match(r"^【([^】]+)】", raw)
    if bracket and bracket.group(1).strip() not in _GENERIC_BRACKET_TITLES:
        return bracket.group(1).strip()
    return None


def _parameter_links(
    source_sellpoints: Sequence[SourceSellpointFact],
) -> list[SellpointParameterLink]:
    links: dict[tuple[str, str], SellpointParameterLink] = {}
    for sellpoint in source_sellpoints:
        roles: dict[str, SellpointParameterSupportRole] = {}
        for code in sellpoint.generic_support_param_codes:
            roles[code] = SellpointParameterSupportRole.GENERIC
        for code in sellpoint.supporting_param_codes:
            roles[code] = SellpointParameterSupportRole.SUPPORTING
        for code in sellpoint.primary_supporting_param_codes:
            roles[code] = SellpointParameterSupportRole.PRIMARY
        for code, role in sorted(roles.items()):
            links[(sellpoint.claim_fact_id, code)] = SellpointParameterLink(
                sellpoint_fact_id=sellpoint.claim_fact_id,
                parameter_code=code,
                parameter_name_cn=PARAM_LABELS.get(code, code),
                normalized_value=None,
                support_role=role,
                evidence_refs=sellpoint.evidence_refs,
            )
    return [
        links[key]
        for key in sorted(links)
    ]


def _user_value_links(
    *,
    category_code: Literal["TV", "AC"],
    source_sellpoints: Sequence[SourceSellpointFact],
    values: Sequence[Any],
) -> list[SellpointUserValueLink]:
    definitions_by_claim: dict[str, list[Any]] = defaultdict(list)
    definitions = _value_definitions(category_code)
    definitions_by_code = {definition.code: definition for definition in definitions}
    for definition in definitions:
        for claim_code in definition.claim_codes:
            definitions_by_claim[claim_code].append(definition)

    links: list[SellpointUserValueLink] = []
    for sellpoint in source_sellpoints:
        for definition in _matching_definitions(
            sellpoint,
            definitions_by_claim,
            definitions_by_code,
        ):
            for value in _matching_values(definition.code, values):
                evidence = _dedupe_evidence(
                    [
                        *sellpoint.evidence_refs,
                        *_value_evidence(value),
                    ]
                )
                links.append(
                    SellpointUserValueLink(
                        sellpoint_fact_id=sellpoint.claim_fact_id,
                        value_bundle_code=str(value.value_bundle_code),
                        user_value_cn=_definition_user_value_cn(definition),
                        perceived_status=_perceived_status(
                            definition.code,
                            value,
                        ),
                        internal_value_theme_codes=[definition.code],
                        evidence_refs=evidence,
                    )
                )
    return sorted(
        links,
        key=lambda row: (row.sellpoint_fact_id, row.value_bundle_code),
    )


def match_source_sellpoint_value_bundle_codes(
    *,
    category_code: Literal["TV", "AC"],
    source_sellpoint: SourceSellpointFact,
    values: Sequence[Any],
) -> list[str]:
    """Return only saved value bundles supported by one source sellpoint."""

    definitions = _value_definitions(category_code)
    definitions_by_code = {
        definition.code: definition for definition in definitions
    }
    definitions_by_claim: dict[str, list[Any]] = defaultdict(list)
    for definition in definitions:
        for claim_code in definition.claim_codes:
            definitions_by_claim[claim_code].append(definition)
    return sorted(
        {
            str(value.value_bundle_code)
            for definition in _matching_definitions(
                source_sellpoint,
                definitions_by_claim,
                definitions_by_code,
            )
            for value in _matching_values(definition.code, values)
        }
    )


def _parameter_assessments(
    *,
    category_code: Literal["TV", "AC"],
    source_sellpoints: Sequence[SourceSellpointFact],
    parameter_links: Sequence[SellpointParameterLink],
    values: Sequence[Any],
    target_parameter_facts: Sequence[Any],
) -> list[ProductParameterAssessment]:
    parameter_results: dict[str, list[Any]] = defaultdict(list)
    for value in values:
        for result in getattr(value, "parameter_group_results", ()):
            parameter_results[str(result.parameter_code)].append(result)
    facts = {
        str(row.parameter_code): row for row in target_parameter_facts
    }
    source_links: dict[str, list[SellpointParameterLink]] = defaultdict(list)
    for link in parameter_links:
        source_links[link.parameter_code].append(link)
    known_parameter_codes = {
        *facts,
        *parameter_results,
        *source_links,
    }
    decisions: dict[str, list[Any]] = defaultdict(list)
    for value in values:
        for decision in getattr(value, "investment_decisions", ()):
            raw_code = str(decision.capability_code)
            code = _parameter_code(raw_code)
            if raw_code.startswith("param:") or code in known_parameter_codes:
                decisions[code].append(decision)

    codes = sorted(
        {
            *facts,
            *decisions,
            *parameter_results,
            *source_links,
        }
    )
    assessments = []
    for code in codes:
        related_decisions = decisions.get(code, [])
        related_results = parameter_results.get(code, [])
        fact = facts.get(code)
        classification, reason = _parameter_classification(
            related_decisions,
            related_results,
        )
        evidence = _dedupe_evidence(
            [
                *(
                    _parameter_fact_evidence(fact)
                    if fact is not None
                    else []
                ),
                *(
                    ref
                    for decision in related_decisions
                    for ref in getattr(decision, "evidence_refs", ())
                ),
                *(
                    ref
                    for result in related_results
                    for ref in getattr(result, "evidence_refs", ())
                ),
                *(
                    ref
                    for link in source_links.get(code, [])
                    for ref in link.evidence_refs
                ),
            ]
        )
        if not evidence:
            continue
        assessments.append(
            ProductParameterAssessment(
                parameter_code=code,
                parameter_name_cn=_parameter_name(
                    code,
                    related_decisions,
                    related_results,
                ),
                normalized_value=_parameter_value(fact, related_results),
                classification=classification,
                linked_sellpoint_fact_ids=sorted(
                    {
                        link.sellpoint_fact_id
                        for link in source_links.get(code, [])
                    }
                ),
                business_reason_cn=reason,
                confidence=_parameter_confidence(
                    related_decisions,
                    related_results,
                ),
                evidence_refs=evidence,
            )
        )
    return sorted(assessments, key=lambda row: row.parameter_code)


def _sellpoint_assessments(
    *,
    category_code: Literal["TV", "AC"],
    source_sellpoints: Sequence[SourceSellpointFact],
    parameter_links: Sequence[SellpointParameterLink],
    user_value_links: Sequence[SellpointUserValueLink],
    parameter_assessments: Sequence[ProductParameterAssessment],
    values: Sequence[Any],
) -> list[ProductSellpointAssessment]:
    definitions_by_claim: dict[str, list[Any]] = defaultdict(list)
    definitions = _value_definitions(category_code)
    definitions_by_code = {definition.code: definition for definition in definitions}
    for definition in definitions:
        for claim_code in definition.claim_codes:
            definitions_by_claim[claim_code].append(definition)
    parameter_classification = {
        row.parameter_code: row.classification for row in parameter_assessments
    }
    links_by_sellpoint: dict[str, list[SellpointParameterLink]] = defaultdict(list)
    for link in parameter_links:
        links_by_sellpoint[link.sellpoint_fact_id].append(link)
    values_by_sellpoint: dict[str, list[SellpointUserValueLink]] = defaultdict(list)
    for link in user_value_links:
        values_by_sellpoint[link.sellpoint_fact_id].append(link)

    assessments = []
    for sellpoint in source_sellpoints:
        if sellpoint.service_separate:
            continue
        definitions = _matching_definitions(
            sellpoint,
            definitions_by_claim,
            definitions_by_code,
        )
        mapped_values = [
            value
            for definition in definitions
            for value in _matching_values(definition.code, values)
        ]
        decisions = [
            decision
            for definition in definitions
            for value in mapped_values
            for decision in getattr(value, "investment_decisions", ())
            if str(decision.capability_code)
            in {definition.code, sellpoint.normalized_claim_code}
        ]
        linked_parameters = links_by_sellpoint.get(sellpoint.claim_fact_id, [])
        linked_classes = {
            parameter_classification.get(link.parameter_code)
            for link in linked_parameters
        }
        linked_classes.discard(None)
        classification, reason, action = _sellpoint_classification(
            decisions=decisions,
            mapped_values=mapped_values,
            linked_parameter_classes=linked_classes,
        )
        evidence = _dedupe_evidence(
            [
                *sellpoint.evidence_refs,
                *(
                    ref
                    for decision in decisions
                    for ref in getattr(decision, "evidence_refs", ())
                ),
                *(
                    ref
                    for value in mapped_values
                    for ref in _value_evidence(value)
                ),
            ]
        )
        assessments.append(
            ProductSellpointAssessment(
                source_claim_key=sellpoint.source_claim_key,
                normalized_claim_code=sellpoint.normalized_claim_code,
                source_sellpoint_fact_ids=sellpoint.merged_claim_fact_ids,
                classification=classification,
                parameter_codes=sorted(
                    {link.parameter_code for link in linked_parameters}
                ),
                value_bundle_codes=sorted(
                    {
                        link.value_bundle_code
                        for link in values_by_sellpoint.get(
                            sellpoint.claim_fact_id,
                            [],
                        )
                    }
                ),
                user_value_summaries_cn=sorted(
                    {
                        link.user_value_cn
                        for link in values_by_sellpoint.get(
                            sellpoint.claim_fact_id,
                            [],
                        )
                    }
                ),
                market_result_refs=sorted(
                    {
                        str(result.result_hash)
                        for value in mapped_values
                        for result in getattr(value, "direct_market_results", ())
                        if _enum_text(result.status) in _AVAILABLE_STATUSES
                    }
                ),
                business_reason_cn=reason,
                product_action_cn=action,
                confidence=_sellpoint_confidence(
                    sellpoint,
                    decisions,
                ),
                evidence_refs=evidence,
            )
        )
    return sorted(
        assessments,
        key=lambda row: (row.source_claim_key, row.normalized_claim_code),
    )


def _sellpoint_classification(
    *,
    decisions: Sequence[Any],
    mapped_values: Sequence[Any],
    linked_parameter_classes: set[Any],
) -> tuple[SellpointClassification, str, str]:
    decision_classes = {
        _enum_text(decision.classification) for decision in decisions
    }
    if "unconverted" in decision_classes:
        return (
            SellpointClassification.USER_UNRECOGNIZED_SELLPOINT,
            "产品已经发布该卖点，但现有用户反馈尚未形成对应认知或体验价值。",
            "优先修改卖点表达或改善实际体验，不继续堆叠同类参数。",
        )
    if linked_parameter_classes and linked_parameter_classes == {
        ParameterClassification.BASIC_PARAMETER
    }:
        return (
            SellpointClassification.BASIC_SELLPOINT,
            "该卖点的主要支撑能力已是当前同层产品的基础要求。",
            "继续保持，但不单独承担差异化和溢价任务。",
        )
    has_market_support = any(
        _enum_text(result.status) in _AVAILABLE_STATUSES
        for value in mapped_values
        for result in getattr(value, "direct_market_results", ())
    )
    if "retain" in decision_classes and has_market_support:
        return (
            SellpointClassification.CORE_SELLPOINT,
            "该原始卖点已经连接用户价值，并获得当前相对市场表现支撑。",
            "继续作为重点卖点，并明确说明给用户带来的实际好处。",
        )
    return (
        SellpointClassification.PENDING_SELLPOINT,
        "原始卖点存在，但当前用户价值或市场证据不足以完成分类。",
        "保留来源并继续观察，暂不作产品取舍。",
    )


def _parameter_classification(
    decisions: Sequence[Any],
    results: Sequence[Any],
) -> tuple[ParameterClassification, str]:
    classes = {_enum_text(row.classification) for row in decisions}
    if {"missing_competitive_gap", "do_not_follow"}.issubset(classes):
        return (
            ParameterClassification.PENDING_PARAMETER,
            "现有判断对该参数的竞争作用存在冲突，需要先完成复核。",
        )
    if "missing_competitive_gap" in classes:
        return (
            ParameterClassification.PARAMETER_GAP,
            "本品该参数缺失或较弱，当前对照显示其可能形成竞争压力。",
        )
    if any(
        bool(getattr(row, "core_highlight_eligible", False))
        and _enum_text(row.status) in _AVAILABLE_STATUSES
        for row in results
    ):
        return (
            ParameterClassification.DIFFERENTIATING_PARAMETER,
            "该具体参数档位已连接用户价值，并形成可比较的相对表现。",
        )
    if "table_stake" in classes:
        return (
            ParameterClassification.BASIC_PARAMETER,
            "该参数已是当前同尺寸、同价格层的基础要求。",
        )
    if "do_not_follow" in classes:
        return (
            ParameterClassification.NON_KEY_PARAMETER_DIFFERENCE,
            "竞品具备该参数，但当前没有证据显示本品因此受损。",
        )
    return (
        ParameterClassification.PENDING_PARAMETER,
        "已保存该参数事实，但当前证据不足以判断其业务作用。",
    )


def _competitor_sellpoint_findings(
    observations: Sequence[CompetitorSellpointObservation],
) -> list[CompetitorSellpointFinding]:
    grouped: dict[
        tuple[str, str],
        list[CompetitorSellpointObservation],
    ] = defaultdict(list)
    for row in observations:
        grouped[
            (
                row.candidate_sku_code,
                row.source_sellpoint.normalized_claim_code,
            )
        ].append(row)
    findings = []
    for members in grouped.values():
        if any(row.target_has_matching_sellpoint for row in members):
            continue
        representative = sorted(
            members,
            key=lambda row: (
                -row.source_sellpoint.confidence,
                row.source_sellpoint.claim_fact_id,
            ),
        )[0]
        opportunity = (
            any(row.competitor_value_advantage for row in members)
            and any(row.target_value_weakness for row in members)
            and any(row.market_support for row in members)
        )
        findings.append(
            CompetitorSellpointFinding(
                candidate_sku_code=representative.candidate_sku_code,
                source_sellpoint_fact_id=(
                    representative.source_sellpoint.claim_fact_id
                ),
                normalized_claim_code=(
                    representative.source_sellpoint.normalized_claim_code
                ),
                normalized_claim_name_cn=(
                    representative.source_sellpoint.normalized_claim_name_cn
                ),
                finding_type=(
                    CompetitorSellpointFindingType.SELLPOINT_OPPORTUNITY
                    if opportunity
                    else CompetitorSellpointFindingType.NON_KEY_COMPETITOR_SELLPOINT
                ),
                linked_value_bundle_codes=sorted(
                    {
                        code
                        for row in members
                        for code in row.linked_value_bundle_codes
                    }
                ),
                business_reason_cn=(
                    "竞品原始卖点对应本品尚未满足的用户价值，并获得市场表现支撑。"
                    if opportunity
                    else "竞品存在该卖点，但当前没有证据显示其造成本品竞争损失。"
                ),
                evidence_refs=_dedupe_evidence(
                    [
                        *(
                            ref
                            for row in members
                            for ref in row.source_sellpoint.evidence_refs
                        ),
                        *(
                            ref
                            for row in members
                            for ref in row.evidence_refs
                        ),
                    ]
                ),
            )
        )
    return sorted(
        findings,
        key=lambda row: (
            row.candidate_sku_code,
            row.normalized_claim_code,
        ),
    )


def _matching_values(
    definition_code: str,
    values: Sequence[Any],
) -> list[Any]:
    exact = [
        value
        for value in values
        if definition_code
        == str(getattr(value, "normalized_bundle_code", ""))
    ]
    if exact:
        return exact
    return [
        value
        for value in values
        if definition_code in set(getattr(value, "capability_codes", ()))
    ]


def _matching_definitions(
    sellpoint: SourceSellpointFact,
    definitions_by_claim: Mapping[str, Sequence[Any]],
    definitions_by_code: Mapping[str, Any],
) -> list[Any]:
    definitions = list(
        definitions_by_claim.get(sellpoint.normalized_claim_code, ())
    )
    raw = sellpoint.raw_claim_text.lower()
    if sellpoint.normalized_claim_code == "tv_claim_chip_performance":
        if re.search(r"画质|控光|色彩|清晰|场景画质", raw) and not re.search(
            r"开机|系统|操作|投屏|语音|运行|切换",
            raw,
        ):
            definition = definitions_by_code.get("tv_bright_room_dark_detail")
            return [definition] if definition is not None else []
    if sellpoint.normalized_claim_code == "tv_claim_dolby_audio_video":
        if re.search(r"色彩|色准|潘通|pantone", raw) and not re.search(
            r"声音|音响|声道|声场|低音|对白|包围",
            raw,
        ):
            definition = definitions_by_code.get("tv_color_picture_truth")
            return [definition] if definition is not None else []
    if (
        sellpoint.normalized_claim_code == "tv_claim_theater_scene"
        and not re.search(
            r"影院|沉浸|声场|音响|声道|对白|包围|客厅观影",
            raw,
        )
    ):
        return []
    if sellpoint.normalized_claim_code not in {
        "tv_claim_high_refresh_rate",
        "tv_claim_high_refresh",
    }:
        return definitions
    if re.search(r"游戏|高刷|刷新率|运动|流畅|低延迟|hdmi", raw):
        return definitions
    return []


def _definition_user_value_cn(definition: Any) -> str:
    return _USER_VALUE_CN_BY_DEFINITION.get(
        str(definition.code),
        str(definition.name_cn),
    )


def _perceived_status(
    definition_code: str,
    value: Any,
) -> str:
    classes = {
        _enum_text(row.classification)
        for row in getattr(value, "investment_decisions", ())
        if str(row.capability_code) == definition_code
    }
    if "unconverted" in classes:
        return "not_recognized"
    if "retain" in classes:
        return "recognized"
    status = _enum_text(value.value_conclusion.status)
    if status in _AVAILABLE_STATUSES:
        return "partially_recognized"
    return "unknown"


def _value_evidence(value: Any) -> list[SellpointValueEvidenceRef]:
    return _dedupe_evidence(
        [
            *getattr(value.value_conclusion, "evidence_refs", ()),
            *(
                ref
                for result in getattr(value, "direct_market_results", ())
                for ref in getattr(result, "evidence_refs", ())
            ),
        ]
    )


def _parameter_fact_evidence(fact: Any) -> list[SellpointValueEvidenceRef]:
    return [
        SellpointValueEvidenceRef(
            module_code="COMPETITOR_PROFILE",
            record_type="sku_parameter_fact",
            record_id=f"{fact.source_snapshot_ref}:{fact.parameter_code}",
            result_hash=str(fact.source_snapshot_result_hash),
            evidence_ids=sorted(set(fact.evidence_ids)),
        )
    ]


def _parameter_name(
    code: str,
    decisions: Sequence[Any],
    results: Sequence[Any],
) -> str:
    if results:
        return str(results[0].parameter_name_cn)
    if decisions:
        return str(decisions[0].capability_name_cn)
    return PARAM_LABELS.get(code, code)


def _parameter_value(
    fact: Any | None,
    results: Sequence[Any],
) -> str | None:
    if fact is not None:
        for value in (
            getattr(fact, "value_text", None),
            getattr(fact, "normalized_value", None),
            getattr(fact, "numeric_value", None),
        ):
            if value not in (None, ""):
                return str(value)
    for result in results:
        if getattr(result, "target_value", None) not in (None, ""):
            return str(result.target_value)
    return None


def _parameter_confidence(
    decisions: Sequence[Any],
    results: Sequence[Any],
) -> Decimal | None:
    values = [
        Decimal(str(row.confidence))
        for row in decisions
        if getattr(row, "confidence", None) is not None
    ]
    if values:
        return max(values)
    if results:
        return Decimal("0.7000")
    return None


def _sellpoint_confidence(
    sellpoint: SourceSellpointFact,
    decisions: Sequence[Any],
) -> Decimal:
    values = [
        sellpoint.confidence,
        *(
            Decimal(str(row.confidence))
            for row in decisions
            if getattr(row, "confidence", None) is not None
        ),
    ]
    return min(values)


def _parameter_code(code: str) -> str:
    return code.removeprefix("param:")


def _value_definitions(category_code: Literal["TV", "AC"]) -> Sequence[Any]:
    return (
        AC_VALUE_UNITS
        if category_code == "AC"
        else (*TV_VALUE_UNITS, *V4_EXTRA_VALUE_UNITS)
    )


def _dedupe_evidence(
    values: Sequence[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    by_key = {
        (
            row.module_code,
            row.record_type,
            row.record_id,
            row.result_hash,
        ): row
        for row in values
    }
    return [by_key[key] for key in sorted(by_key)]


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value)).strip()


def _json_payload(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return {
            str(key): _json_payload(item)
            for key, item in value.model_dump(mode="json").items()
        }
    if isinstance(value, Mapping):
        return {
            str(key): _json_payload(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return [_json_payload(item) for item in value]
    return value


__all__ = [
    "CompetitorSellpointObservation",
    "SPV_V5_2_LAYER_MAPPING_VERSION",
    "build_layered_sellpoint_analysis",
    "evaluate_layer_integrity",
    "match_source_sellpoint_value_bundle_codes",
]
