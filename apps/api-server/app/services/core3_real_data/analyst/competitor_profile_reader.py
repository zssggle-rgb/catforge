"""Read saved competitor profiles without recomputing candidates or relations."""

from __future__ import annotations

from typing import Any

from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileReadBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileBusinessDTO,
    CompetitorProfileEvidenceDTO,
    CompetitorProfileReadRequest,
    CompetitorProfileReaderResult,
)
from app.services.core3_real_data.analyst.competitor_profile_repositories import (
    CompetitorProfileRepository,
)


_STATE_CN = {
    "ready": "数据完整，可形成竞品结论",
    "partial": "部分问题已有结论，其余问题数据不足",
    "blocked": "当前数据不足，无法形成竞品结论",
}
_CONCLUSION_CN = {
    "available": "已形成可用于产品决策的竞品结论",
    "no_priority_competitor": "市场中有可比较产品，但没有需要优先跟踪的重点竞品",
    "insufficient_evidence": "当前数据不足，暂不能形成竞品结论",
}
_BUSINESS_KEY_CN = {
    "candidate_sku_code": "参照产品",
    "evidence_family": "价值证据维度",
    "value_codes": "用户价值",
    "conclusion_cn": "结论",
    "relation_codes": "可比较关系",
    "pressure_direction": "市场压力方向",
    "target_weighted_price": "本品市场均价",
    "candidate_weighted_price": "参照产品市场均价",
    "price_gap_pct": "价格差幅",
    "target_avg_weekly_volume": "本品周均销量",
    "candidate_avg_weekly_volume": "参照产品周均销量",
    "weekly_volume_ratio": "周均销量倍数",
    "relation_status": "关系状态",
    "business_effect": "对产品工作的影响",
    "decision": "建议动作",
    "feature_codes": "差异配置",
    "question_availability": "结论可用性",
    "reason_code": "数据不足原因",
    "reason_cn": "说明",
    "target_analysis_state": "数据完整度",
    "effect_code": "影响方式",
    "strong_pressure": "压力强度",
    "purchase_choice_allowed": "可用于购买选择判断",
}
_OMITTED_BUSINESS_KEYS = {
    "causal_claim",
    "causal_wtp_claim",
    "price_change_sales_increment_claim",
}


class CompetitorProfileReader:
    """Enforce formal/current and explicit-preview read boundaries."""

    def __init__(self, repository: CompetitorProfileRepository) -> None:
        self.repository = repository

    def read(self, request: CompetitorProfileReadRequest) -> CompetitorProfileReaderResult:
        if request.project_id != self.repository.project_id:
            raise ValueError("reader project scope does not match repository")
        if request.category_code != self.repository.category_code.value:
            raise ValueError("reader category scope does not match repository")
        if request.mode == "formal":
            bundle = self.repository.get_current_published_profile(
                release_scope_key=request.release_scope_key,
                target_sku_code=request.target_sku_code,
                compact=True,
            )
        else:
            version = self.repository.get_version_by_id(
                str(request.competitor_profile_version_id)
            )
            if version.release_scope_key != request.release_scope_key:
                raise ValueError("preview version does not belong to the requested release scope")
            bundle = self.repository.get_profile(
                competitor_profile_version_id=version.competitor_profile_version_id,
                target_sku_code=request.target_sku_code,
                preview=True,
                compact=True,
            )
        if bundle is None:
            return CompetitorProfileReaderResult(
                status="profile_unavailable",
                preview=request.mode == "preview",
                message_cn=(
                    "当前没有可用的正式竞品画像。"
                    if request.mode == "formal"
                    else "指定草稿版本中没有该产品的竞品画像。"
                ),
            )
        return CompetitorProfileReaderResult(
            status="available",
            competitor_profile_version_id=(
                bundle.version.competitor_profile_version_id
            ),
            preview=bundle.preview,
            business=_business_dto(bundle),
            evidence=_evidence_dto(bundle),
            message_cn=(
                "已读取正式竞品画像。"
                if not bundle.preview
                else "已读取指定草稿画像，仅用于开发验收。"
            ),
        )


def _business_dto(bundle: CompetitorProfileReadBundle) -> CompetitorProfileBusinessDTO:
    profile = bundle.profile.profile_payload
    return CompetitorProfileBusinessDTO(
        目标产品=profile.display_name_cn,
        分析结论=_STATE_CN[str(profile.analysis_state)],
        结论状态=_CONCLUSION_CN[str(profile.conclusion_state)],
        重点竞品=[
            {
                "产品": row.display_name_cn,
                "排序": row.selection_rank,
                "主要回答": _business_label(str(row.primary_decision_topic)),
                "为什么要关注": row.conclusion_cn,
            }
            for row in profile.key_competitor_summary
        ],
        本品优势=_business_rows(profile.competitive_advantages),
        可替代价值=_business_rows(profile.substitutable_values),
        价格销量压力=_business_rows(profile.price_scale_pressures),
        同品牌产品线=_business_rows(profile.same_brand_findings),
        配置决策=_business_rows(profile.configuration_decisions),
        候选概况={
            _candidate_status_label(code): count
            for code, count in profile.candidate_status_counts.items()
        },
        竞品对比=_business_pair_comparisons(bundle),
        问答范围=[
            {
                "问题": _business_label(str(row.get("question_code") or "")),
                "可以形成结论的产品数": len(
                    row.get("eligible_candidate_sku_codes") or []
                ),
                "只能形成有限结论的产品数": len(
                    row.get("limited_candidate_sku_codes") or []
                ),
            }
            for row in profile.qa_index
        ],
        数据不足说明=_business_mapping(profile.no_conclusion_reason),
    )


def _business_pair_comparisons(
    bundle: CompetitorProfileReadBundle,
) -> list[dict[str, Any]]:
    selection_by_sku = {
        row.candidate_sku_code: row.selection_payload for row in bundle.selections
    }
    pressure_by_sku = {
        str(row.get("candidate_sku_code") or ""): row
        for row in bundle.profile.profile_payload.price_scale_pressures
    }
    rows = []
    for record in bundle.pairs:
        pair = record.pair_payload
        if not pair.competitor_member:
            continue
        formal_relations = [
            row
            for row in pair.relation_assessments
            if str(row.status) in {"passed", "limited"}
        ]
        primary = next((row for row in formal_relations if row.is_primary), None)
        selection = selection_by_sku.get(pair.candidate.sku_code)
        market = pair.market_comparison
        evidence = [
            {
                "用户价值": [_business_label(code) for code in family.matched_codes],
                "对比结果": _business_label(str(family.direction)),
            }
            for family in pair.evidence_family_assessments
            if family.matched_codes
            and str(family.direction) in {"target_stronger", "candidate_stronger", "shared"}
        ]
        pressure = pressure_by_sku.get(pair.candidate.sku_code, {})
        rows.append(
            {
                "产品": pair.candidate.display_name_cn,
                "产品编号": pair.candidate.sku_code,
                "关注层级": "重点关注" if selection else "专项对比",
                "为什么关注": (
                    selection.conclusion_cn
                    if selection
                    else _relation_effect_cn(primary)
                ),
                "主要关系": (
                    _business_label(str(primary.relation_code)) if primary else ""
                ),
                "辅助关系": [
                    _business_label(str(row.relation_code))
                    for row in formal_relations
                    if not row.is_primary
                ],
                "用户价值对比": evidence,
                "本品均价": market.target_weighted_price,
                "对方均价": market.candidate_weighted_price,
                "本品周均销量": market.target_avg_weekly_volume,
                "对方周均销量": market.candidate_avg_weekly_volume,
                "市场压力": _business_label(
                    str(pressure.get("pressure_direction") or "")
                ),
                "可以回答": [
                    _business_label(str(row.question_code))
                    for row in pair.question_eligibility
                    if str(row.availability) in {"eligible", "limited"}
                ],
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["关注层级"] != "重点关注",
            str(row["产品"]),
        ),
    )


def _relation_effect_cn(row: Any | None) -> str:
    if row is None:
        return "这款产品可用于专项比较，但不需要进入首要关注名单。"
    effect = str(row.business_effect.get("effect_code") or "")
    return {
        "purchase_choice_overlap": "它会与本品进入同一批用户的最终选择。",
        "same_budget_route_competition": "它用相近预算提供了另一条用户价值路线。",
        "observed_downtrade_market_pressure": "它以更低价格形成了已观察到的销量分流压力。",
        "observed_uptrade_market_acceptance": "它证明用户愿意为更强价值继续加价。",
        "same_brand_portfolio_overlap": "它与本品存在同品牌产品线重叠。",
        "same_scenario_solution_switch": "它提供了满足同一场景的另一种产品方案。",
        "same_value_competition": "它能替代本品承接同一项用户价值。",
        "same_value_research": "它适合比较同一用户价值，但不能用于判断用户二选一。",
    }.get(effect, "它能回答一项明确的产品竞争问题。")


def _candidate_status_label(value: str) -> str:
    return {
        "eligible": "可直接形成竞品结论",
        "limited": "只能回答部分问题",
        "review_required": "需要人工复核",
        "blocked": "不可用于业务结论",
        "recalled_only": "仅进入候选范围",
        "reference_only": "仅用于市场参照",
    }.get(value, "其他候选")


def _evidence_dto(bundle: CompetitorProfileReadBundle) -> CompetitorProfileEvidenceDTO:
    profile = bundle.profile.profile_payload
    return CompetitorProfileEvidenceDTO(
        competitor_profile_version_id=bundle.version.competitor_profile_version_id,
        profile_version=bundle.version.profile_version,
        release_status=str(bundle.version.release_status),
        preview=bundle.preview,
        target_sku_code=profile.target_sku_code,
        profile_result_hash=profile.result_hash,
        candidate_evidence=[
            {
                "candidate_sku_code": pair.candidate_sku_code,
                "candidate_status": str(pair.candidate_status),
                "competitor_member": pair.competitor_member,
                "reference_member": pair.reference_member,
                "selected": pair.selected,
                "relation_codes": [
                    str(row.relation_code)
                    for row in pair.pair_payload.relation_assessments
                    if str(row.status) in {"passed", "limited"}
                ],
                "question_eligibility": [
                    row.model_dump(mode="json")
                    for row in pair.pair_payload.question_eligibility
                ],
                "evidence_refs": [
                    row.model_dump(mode="json")
                    for row in pair.pair_payload.evidence_refs
                ],
                "limitations": pair.pair_payload.limitations,
            }
            for pair in bundle.pairs
        ],
        source_lineage=profile.source_lineage,
        limitations=profile.limitations,
    )


def _business_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_business_mapping(row) for row in rows]


def _business_mapping(value: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in value.items():
        if key in _OMITTED_BUSINESS_KEYS:
            continue
        label = _BUSINESS_KEY_CN.get(key, _business_label(key))
        if isinstance(child, dict):
            result[label] = _business_mapping(child)
        elif isinstance(child, list):
            result[label] = [
                _business_mapping(item) if isinstance(item, dict) else _business_label(str(item))
                for item in child
            ]
        else:
            result[label] = _business_label(child) if isinstance(child, str) else child
    return result


def _business_label(value: str) -> str:
    labels = {
        "purchase_choice": "用户购买选择",
        "price_scale_pressure": "价格与销量压力",
        "portfolio_or_scenario": "产品线与使用场景",
        "value_route": "用户价值替代",
        "evaluate_follow": "评估是否值得跟进",
        "do_not_follow_without_value_evidence": "先确认用户价值，再决定是否跟进",
        "eligible": "可形成结论",
        "limited": "结论有限",
        "unavailable": "数据不足",
        "direct_substitute": "直接替代",
        "same_budget_alternative": "同预算替代",
        "downtrade_diversion": "低价分流",
        "uptrade_alternative": "升档替代",
        "same_brand_ladder": "同品牌梯度",
        "scenario_substitute": "场景替代",
        "same_value_substitute": "同价值替代",
        "price_volume_pressure": "价格与销量压力",
        "configuration_follow": "配置是否值得跟进",
        "same_brand_portfolio_role": "同品牌产品线角色",
        "scenario_solution": "另一种场景方案",
        "price_ladder_defense": "上探或下探防守",
        "key_competitor_selection": "重点竞品选择",
        "value_substitution": "用户价值替代",
        "target_stronger": "本品更强",
        "candidate_stronger": "对方更强",
        "shared": "双方共同具备",
        "direct_budget_pressure": "同预算竞争压力",
        "downtrade_volume_pressure": "低价销量分流压力",
        "uptrade_market_acceptance": "更高价格获得市场接受",
        "value_route_pressure": "另一条价值路线形成压力",
        "no_observed_pressure": "未观察到明确市场压力",
        "insufficient_evidence": "现有信息不足",
        "no_priority_competitor": "没有需要优先关注的竞品",
        "selected": "已形成重点竞品",
        "review_required": "需要人工复核",
        "partial": "部分问题可回答",
        "ready": "信息完整",
        "blocked": "信息不足",
        "purchase_choice_overlap": "进入同一批用户的最终选择",
        "same_budget_route_competition": "相近预算下提供另一条价值路线",
        "observed_downtrade_market_pressure": "较低价格形成销量分流压力",
        "observed_uptrade_market_acceptance": "更强价值获得加价接受",
        "same_brand_portfolio_overlap": "同品牌产品线存在重叠",
        "same_scenario_solution_switch": "同一场景存在另一种解决方案",
        "same_value_competition": "承接相同用户价值",
        "same_value_research": "适合研究同一用户价值",
        "clear_picture": "画质清晰",
    }
    if value in labels:
        return labels[value]
    normalized = value.strip()
    if not normalized:
        return ""
    tokens = normalized.lower().split("_")
    token_labels = {
        "tv": "",
        "ac": "",
        "claim": "",
        "bf": "",
        "task": "",
        "tg": "",
        "picture": "画质",
        "image": "画质",
        "brightness": "亮度",
        "hdr": "HDR",
        "miniled": "MiniLED",
        "mini": "MiniLED",
        "led": "",
        "local": "局部",
        "dimming": "控光",
        "color": "色彩",
        "gamut": "色域",
        "gaming": "游戏",
        "game": "游戏",
        "refresh": "高刷",
        "rate": "",
        "low": "低",
        "latency": "延迟",
        "hdmi21": "HDMI 2.1",
        "connectivity": "连接",
        "audio": "音效",
        "dolby": "杜比影音",
        "smart": "智能",
        "voice": "语音",
        "ai": "AI",
        "family": "家庭",
        "viewing": "观影",
        "cinema": "影院",
        "immersion": "沉浸",
        "comfort": "舒适",
        "energy": "节能",
        "efficient": "高效",
        "healthy": "健康",
        "health": "健康",
        "quiet": "静音",
        "sleep": "睡眠",
        "control": "控制",
        "wifi": "联网",
        "screen": "屏幕",
        "size": "尺寸",
        "inch": "英寸",
        "ports": "接口",
        "format": "格式",
        "list": "",
    }
    if len(tokens) > 1 and all(token in token_labels for token in tokens):
        label = "".join(token_labels[token] for token in tokens)
        return label or "相关产品价值"
    return normalized if "_" not in normalized else "相关产品价值"


__all__ = ["CompetitorProfileReader"]
