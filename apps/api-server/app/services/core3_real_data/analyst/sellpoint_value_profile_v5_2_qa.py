"""Deterministic product-manager Q&A over one saved V5.2 readback."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field

from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    StoredPmParameterRow,
    StoredPmSellpointRow,
    build_v5_2_stored_profile_pm_report,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52Readback,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_2_QA_HASH_VERSION = "sellpoint_value_profile_qa_v5_2"
SellpointValueV52QaTopic = Literal[
    "user_sellpoint_value",
    "sellpoint_classification",
    "parameter_classification",
    "price_and_volume",
    "sellpoint_action",
    "specific_sellpoint",
    "unsupported",
]


class SellpointValueV52QaFact(SellpointValueProfileBaseModel):
    fact_path: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)
    evidence_record_ids: list[str] = Field(default_factory=list)


class SellpointValueV52Answer(SellpointValueProfileBaseModel):
    schema_version: str = "sellpoint_value_profile_answer_v1_2"
    question: str = Field(min_length=1)
    topic_code: SellpointValueV52QaTopic
    answer_status: Literal["answered", "unknown"]
    direct_answer_cn: str = Field(min_length=1)
    product_manager_action_cn: str = Field(min_length=1)
    evidence_boundary_cn: str = Field(min_length=1)
    facts: list[SellpointValueV52QaFact] = Field(default_factory=list)
    profile_result_hash: str = Field(min_length=1)
    answer_hash: str = Field(min_length=1)


class SellpointValueV52QaService:
    def answer(
        self,
        readback: SellpointValueV52Readback,
        *,
        question: str,
    ) -> SellpointValueV52Answer:
        normalized = question.strip()
        if not normalized:
            raise ValueError("question is required")
        report = build_v5_2_stored_profile_pm_report(readback)
        topic = _route_question(normalized, report.sellpoint_rows)
        direct, action, rows, parameters, unknown = _answer_topic(
            report.sellpoint_rows,
            report.parameter_rows,
            price_support_cn=report.first_screen.price_support_cn,
            growth_action_cn=report.first_screen.growth_action_cn,
            question=normalized,
            topic=topic,
        )
        facts = [
            *(
                SellpointValueV52QaFact(
                    fact_path=(
                        "layered_sellpoint_analysis.sellpoint_assessments."
                        f"{row.source_claim_key}.{row.normalized_claim_code}"
                    ),
                    summary_cn=(
                        f"{row.classification_cn}“{_sellpoint_name(row)}”："
                        f"{'、'.join(row.user_values_cn) or row.current_user_recognition_cn}"
                    ),
                    evidence_record_ids=_sellpoint_evidence_ids(readback, row),
                )
                for row in rows
            ),
            *(
                SellpointValueV52QaFact(
                    fact_path=(
                        "layered_sellpoint_analysis.parameter_assessments."
                        f"{row.parameter_code}"
                    ),
                    summary_cn=(
                        f"{row.classification_cn}“{_parameter_name(row)}”："
                        f"{row.business_reason_cn}"
                    ),
                    evidence_record_ids=_parameter_evidence_ids(readback, row),
                )
                for row in parameters
            ),
        ]
        payload = {
            "question": normalized,
            "topic_code": topic,
            "answer_status": "unknown" if unknown else "answered",
            "direct_answer_cn": direct,
            "product_manager_action_cn": action,
            "evidence_boundary_cn": (
                "回答以本品已保存的原始宣传卖点、参数、用户价值和市场结果为依据；"
                "没有把参数或分析主题改写为产品卖点。"
            ),
            "facts": facts,
            "profile_result_hash": readback.profile.result_hash,
        }
        return SellpointValueV52Answer(
            **payload,
            answer_hash=stable_hash(
                {
                    **payload,
                    "facts": [row.model_dump(mode="json") for row in facts],
                },
                version=SPV_V5_2_QA_HASH_VERSION,
            ),
        )


def _route_question(
    question: str,
    sellpoints: list[StoredPmSellpointRow],
) -> SellpointValueV52QaTopic:
    if _matching_sellpoints(question, sellpoints):
        return "specific_sellpoint"
    if re.search(r"是.*卖点|算.*卖点|卖点吗", question, re.IGNORECASE):
        return "specific_sellpoint"
    for topic, pattern in (
        ("sellpoint_action", r"怎么改|修改建议|怎么写|如何表达|宣传材料"),
        ("price_and_volume", r"价格|销量|走量|降价|溢价"),
        ("parameter_classification", r"参数|配置|基础能力|短板"),
        (
            "sellpoint_classification",
            r"核心卖点|基础卖点|未认知卖点|待确认卖点|怎么分类",
        ),
        ("user_sellpoint_value", r"用户卖点价值|卖点价值|用户感知|用户价值"),
    ):
        if re.search(pattern, question, re.IGNORECASE):
            return topic  # type: ignore[return-value]
    return "unsupported"


def _answer_topic(
    sellpoints: list[StoredPmSellpointRow],
    parameters: list[StoredPmParameterRow],
    *,
    price_support_cn: str,
    growth_action_cn: str,
    question: str,
    topic: SellpointValueV52QaTopic,
) -> tuple[
    str,
    str,
    list[StoredPmSellpointRow],
    list[StoredPmParameterRow],
    bool,
]:
    if topic == "specific_sellpoint":
        rows = _matching_sellpoints(question, sellpoints)
        if not rows:
            return (
                "本品宣传材料的原始卖点中没有找到问题所指的卖点。",
                "不要把参数、用户价值主题或分析标签写成本品产品卖点；"
                "需要以本品宣传材料中的原始卖点为准。",
                [],
                [],
                True,
            )
        if len(rows) != 1:
            return (
                "问题同时命中多个产品原始卖点，请指定其中一项。",
                "使用报告中的原始卖点名称重新提问。",
                rows,
                [],
                True,
            )
        row = rows[0]
        value = "、".join(row.user_values_cn) or row.current_user_recognition_cn
        return (
            f"“{_sellpoint_name(row)}”是本品宣传材料中的产品原始卖点，"
            f"当前分类为{row.classification_cn}；对应用户价值为：{value}",
            row.product_action_cn,
            rows,
            [],
            False,
        )
    if topic == "user_sellpoint_value":
        rows = [row for row in sellpoints if row.user_values_cn]
        if not rows:
            return (
                "当前没有产品原始卖点形成可确认的用户感知价值。",
                "按现有卖点分类维护宣传材料，不新增缺少依据的价值承诺。",
                sellpoints,
                [],
                True,
            )
        direct = "；".join(
            f"“{_sellpoint_name(row)}”让用户获得“{'、'.join(row.user_values_cn)}”"
            for row in rows
        )
        return (
            direct + "。",
            "优先按核心卖点、基础卖点和用户未认知卖点的动作分别修改材料。",
            rows,
            [],
            False,
        )
    if topic == "sellpoint_classification":
        if not sellpoints:
            return (
                "本品宣传材料中没有读取到可追溯的产品原始卖点。",
                "不从参数或用户价值主题补造卖点名称。",
                [],
                [],
                True,
            )
        direct = "；".join(
            f"{row.classification_cn}：{_sellpoint_name(row)}"
            for row in sellpoints
        )
        return (
            direct + "。",
            "按各卖点保存的产品动作维护主推顺序和表达方式。",
            sellpoints,
            [],
            False,
        )
    if topic == "parameter_classification":
        if not parameters:
            return (
                "现有数据没有形成可用的参数分类。",
                "不把缺失参数判断改写成产品卖点结论。",
                [],
                [],
                True,
            )
        direct = _parameter_classification_answer_cn(parameters)
        return (
            direct,
            "差异化参数用于证明卖点，基础参数维持竞争，参数短板进入产品评估。",
            [],
            parameters,
            False,
        )
    if topic == "price_and_volume":
        return (
            f"{price_support_cn} {growth_action_cn}",
            "把该结论作为当前价格和卖点修改的联合决策依据。",
            [],
            [],
            False,
        )
    if topic == "sellpoint_action":
        if not sellpoints:
            return (
                "当前没有可执行的产品卖点修改建议。",
                "保持现有材料，不新增卖点名称。",
                [],
                [],
                True,
            )
        return (
            " ".join(row.product_action_cn for row in sellpoints),
            "按核心、基础、用户未认知和待确认的顺序修改当前宣传材料。",
            sellpoints,
            [],
            False,
        )
    return (
        "现有分析结果没有为这个问题配置可用答案。",
        "请改问用户卖点价值、卖点分类、参数判断、价格销量或卖点修改建议。",
        [],
        [],
        True,
    )


def _matching_sellpoints(
    question: str,
    rows: list[StoredPmSellpointRow],
) -> list[StoredPmSellpointRow]:
    normalized = _normalize(question)
    result = []
    for row in rows:
        exact_aliases = {
            _normalize(row.exact_quote_cn or ""),
        }
        standardized_aliases = {
            _normalize(row.normalized_claim_name_cn),
            *(
                _normalize(part)
                for part in re.split(
                    r"[/／、|]",
                    row.normalized_claim_name_cn,
                )
            ),
        }
        aliases = {
            *(
                alias
                for alias in exact_aliases
                if len(alias) >= 2
            ),
            *(
                alias
                for alias in standardized_aliases
                if len(alias) >= 4
            ),
        }
        if any(alias in normalized for alias in aliases):
            result.append(row)
    return result


def _sellpoint_name(row: StoredPmSellpointRow) -> str:
    return row.exact_quote_cn or row.normalized_claim_name_cn


def _parameter_name(row: StoredPmParameterRow) -> str:
    return (
        f"{row.parameter_name_cn}（{row.normalized_value}）"
        if row.normalized_value
        else row.parameter_name_cn
    )


def _sellpoint_evidence_ids(
    readback: SellpointValueV52Readback,
    row: StoredPmSellpointRow,
) -> list[str]:
    return sorted(
        {
            fact_id
            for fact in readback.profile.layered_sellpoint_analysis.source_sellpoints
            if fact.source_claim_key == row.source_claim_key
            for fact_id in fact.merged_claim_fact_ids
        }
    )


def _parameter_classification_answer_cn(
    rows: list[StoredPmParameterRow],
) -> str:
    parts = []
    for classification in (
        "差异化参数",
        "基础参数",
        "参数短板",
        "非关键参数差异",
        "待确认参数",
    ):
        names = [
            _parameter_name(row)
            for row in rows
            if row.classification_cn == classification
        ]
        if not names:
            continue
        shown = "、".join(names[:5])
        suffix = f"等{len(names)}项" if len(names) > 5 else ""
        parts.append(f"{classification}：{shown}{suffix}")
    return "；".join(parts) + "。"


def _parameter_evidence_ids(
    readback: SellpointValueV52Readback,
    row: StoredPmParameterRow,
) -> list[str]:
    assessment = next(
        (
            item
            for item in readback.profile.layered_sellpoint_analysis.parameter_assessments
            if item.parameter_code == row.parameter_code
        ),
        None,
    )
    if assessment is None:
        return []
    return sorted(
        {
            ref.record_id
            for ref in assessment.evidence_refs
            if ref.record_id
        }
    )


def _normalize(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", value).lower()


__all__ = [
    "SPV_V5_2_QA_HASH_VERSION",
    "SellpointValueV52Answer",
    "SellpointValueV52QaFact",
    "SellpointValueV52QaService",
    "SellpointValueV52QaTopic",
]
