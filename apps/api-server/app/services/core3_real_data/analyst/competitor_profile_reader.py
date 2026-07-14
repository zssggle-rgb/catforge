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
        数据不足说明=_business_mapping(profile.no_conclusion_reason),
    )


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
    }
    if value in labels:
        return labels[value]
    return value.replace("_", "·")


__all__ = ["CompetitorProfileReader"]
