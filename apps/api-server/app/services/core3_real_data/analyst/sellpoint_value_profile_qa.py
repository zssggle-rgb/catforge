"""Deterministic product-manager Q&A over one stored sellpoint-value profile."""

from __future__ import annotations

import re
from typing import Any, Literal, Sequence

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueProfileReadBundle,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.hash_utils import stable_hash


PROFILE_QA_HASH_VERSION = "sellpoint_value_profile_qa_v1"
ProfileQaStatus = Literal["answered", "limited", "unknown"]
ProfileQaTopicCode = Literal[
    "retain_investment",
    "unconverted_investment",
    "do_not_follow",
    "missing_gap",
    "price_support",
    "price_volume_increment",
    "volume_action",
    "competitor_selection",
    "source_pool",
    "battlefield_action",
    "table_stake",
    "version_change",
    "unsupported",
]


TOPIC_PATTERNS: tuple[tuple[ProfileQaTopicCode, tuple[str, ...]], ...] = (
    ("version_change", (r"上一版|版本.*变化|候选.*变化|相比.*版本",)),
    ("source_pool", (r"哪些.*竞品.*参考|来自竞品|来自.*参考|参考池|分析参照",)),
    ("price_volume_increment", (r"降价.*多少|增加多少销量|净增.*销量",)),
    ("do_not_follow", (r"不用跟|不需要跟|无需跟|不跟进",)),
    ("missing_gap", (r"缺口|补齐|需要补|必须补",)),
    ("unconverted_investment", (r"未转化|没有感知|没感知|具备.*没有|投入.*没",)),
    ("table_stake", (r"基础竞争|普及|常规功能|门槛",)),
    ("battlefield_action", (r"价值战场|新战场|战场.*增强|相邻战场",)),
    ("competitor_selection", (r"为什么.*对照|为什么.*选|为什么.*没选|竞品|相比.*赢|相比.*输",)),
    ("volume_action", (r"走量|追求销量|改卖点|改价格|销量动作",)),
    ("price_support", (r"价格|溢价|撑得住|价格支撑",)),
    ("retain_investment", (r"值得保留|继续保留|保留什么|哪些投入",)),
)


class ProfileQaFact(SellpointValueProfileBaseModel):
    fact_path: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    record_id: str = Field(min_length=1)


class SellpointValueProfileAnswer(SellpointValueProfileBaseModel):
    schema_version: str = "sellpoint_value_profile_answer_v1"
    question: str = Field(min_length=1)
    topic_code: ProfileQaTopicCode
    answer_status: ProfileQaStatus
    direct_answer_cn: str = Field(min_length=1)
    profile_facts: list[ProfileQaFact] = Field(default_factory=list)
    work_implication_cn: str = Field(min_length=1)
    evidence_boundary_cn: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    release_status: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    fact_paths: list[str] = Field(default_factory=list)
    candidate_record_ids: list[str] = Field(default_factory=list)
    value_item_record_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    answer_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unknown_answer(self) -> "SellpointValueProfileAnswer":
        if self.answer_status == "unknown" and not self.limitations:
            raise ValueError("unknown profile answers require limitations")
        return self


class ProfileQaTargetAmbiguousError(ValueError):
    def __init__(self, candidates: Sequence[dict[str, Any]]) -> None:
        super().__init__("multiple stored sellpoint-value profiles matched")
        self.candidates = list(candidates)


class SellpointValueProfileQaService:
    def __init__(self, repository: SellpointValueProfileRepository) -> None:
        self.repository = repository

    def answer(
        self,
        *,
        batch_id: str,
        question: str,
        sku_code: str | None = None,
        model_name: str | None = None,
        query: str | None = None,
        profile_version: str | None = None,
        expected_result_hash: str | None = None,
        topic_code: ProfileQaTopicCode | None = None,
        candidate_sku_code: str | None = None,
        compare_profile_version: str | None = None,
    ) -> SellpointValueProfileAnswer | None:
        bundle = self._resolve_bundle(
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            model_name=model_name,
            query=query,
        )
        if bundle is None:
            return None
        topic = topic_code or route_profile_question(question)
        if expected_result_hash and bundle.profile.result_hash != expected_result_hash:
            return _answer(
                bundle,
                question=question,
                topic_code=topic,
                answer_status="unknown",
                direct_answer_cn="指定报告与当前读取画像不是同一份结果，不能继续回答。",
                work_implication_cn="请使用报告中的画像版本和结果编号重新发起追问。",
                boundary_cn="为避免混用不同候选集合和量价结论，本次没有读取或重算其他数据。",
                limitations=["expected_result_hash_mismatch"],
            )
        answer = self._answer_topic(
            bundle,
            question=question,
            topic=topic,
            candidate_sku_code=candidate_sku_code,
            compare_profile_version=compare_profile_version,
        )
        return _apply_quality_boundary(answer, bundle)

    def _resolve_bundle(
        self,
        *,
        batch_id: str,
        profile_version: str | None,
        sku_code: str | None,
        model_name: str | None,
        query: str | None,
    ) -> SellpointValueProfileReadBundle | None:
        targets = self.repository.resolve_profile_targets(
            batch_id=batch_id,
            profile_version=profile_version,
            sku_code=sku_code,
            model_name=model_name,
            query=query,
        )
        if not targets:
            return None
        if len(targets) > 1:
            raise ProfileQaTargetAmbiguousError(targets)
        target = targets[0]
        if profile_version:
            return self.repository.get_profile(
                batch_id=batch_id,
                profile_version=profile_version,
                sku_code=str(target["sku_code"]),
                rule_version=str(target["rule_version"]),
            )
        return self.repository.get_current_published_profile(
            batch_id=batch_id,
            sku_code=str(target["sku_code"]),
        )

    def _answer_topic(
        self,
        bundle: SellpointValueProfileReadBundle,
        *,
        question: str,
        topic: ProfileQaTopicCode,
        candidate_sku_code: str | None,
        compare_profile_version: str | None,
    ) -> SellpointValueProfileAnswer:
        investment_topics = {
            "retain_investment": "retain",
            "unconverted_investment": "unconverted",
            "do_not_follow": "do_not_follow",
            "missing_gap": "missing_competitive_gap",
            "table_stake": "table_stake",
        }
        if topic in investment_topics:
            return _investment_answer(
                bundle,
                question=question,
                topic=topic,
                classification=investment_topics[topic],
            )
        if topic == "price_support":
            return _price_answer(bundle, question)
        if topic == "price_volume_increment":
            return _price_increment_answer(bundle, question)
        if topic == "volume_action":
            return _volume_answer(bundle, question)
        if topic == "competitor_selection":
            return _candidate_answer(
                bundle,
                question=question,
                candidate_sku_code=candidate_sku_code,
            )
        if topic == "source_pool":
            return _source_pool_answer(bundle, question)
        if topic == "battlefield_action":
            return _battlefield_answer(bundle, question)
        if topic == "version_change":
            return self._version_answer(
                bundle,
                question=question,
                compare_profile_version=compare_profile_version,
            )
        return _answer(
            bundle,
            question=question,
            topic_code="unsupported",
            answer_status="unknown",
            direct_answer_cn="当前画像没有为这个问题配置可用的问答主题。",
            work_implication_cn="请改问产品投入、价格、销量、竞品、价值战场或版本变化。",
            boundary_cn="未调用外部模型，也没有临时读取上游数据推断答案。",
            limitations=["unsupported_profile_question"],
        )

    def _version_answer(
        self,
        bundle: SellpointValueProfileReadBundle,
        *,
        question: str,
        compare_profile_version: str | None,
    ) -> SellpointValueProfileAnswer:
        if not compare_profile_version:
            return _answer(
                bundle,
                question=question,
                topic_code="version_change",
                answer_status="unknown",
                direct_answer_cn="需要明确要与哪个画像版本比较，当前不能自动选择另一版。",
                work_implication_cn="指定上一画像版本后，可核对候选、投入分类和产品结论变化。",
                boundary_cn="不自动把未审核草稿或其他批次当成上一版。",
                limitations=["compare_profile_version_required"],
            )
        previous = self._resolve_bundle(
            batch_id=bundle.profile.batch_id,
            profile_version=compare_profile_version,
            sku_code=bundle.profile.sku_code,
            model_name=None,
            query=None,
        )
        if previous is None:
            return _answer(
                bundle,
                question=question,
                topic_code="version_change",
                answer_status="unknown",
                direct_answer_cn=f"没有找到指定的对比画像版本 {compare_profile_version}。",
                work_implication_cn="请确认版本号和批次后再比较。",
                boundary_cn="没有用其他 SKU 或其他批次替代缺失版本。",
                limitations=["compare_profile_not_found"],
            )
        return _version_diff_answer(bundle, previous, question)


def route_profile_question(question: str) -> ProfileQaTopicCode:
    normalized = question.strip()
    for topic, patterns in TOPIC_PATTERNS:
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in patterns):
            return topic
    return "unsupported"


def _investment_answer(
    bundle: SellpointValueProfileReadBundle,
    *,
    question: str,
    topic: ProfileQaTopicCode,
    classification: str,
) -> SellpointValueProfileAnswer:
    rows = [
        row
        for row in bundle.profile.investment_decisions_json
        if str(row.get("classification")) == classification
    ]
    if not rows:
        return _answer(
            bundle,
            question=question,
            topic_code=topic,
            answer_status="unknown",
            direct_answer_cn="当前画像没有形成这类产品投入结论。",
            work_implication_cn="暂不据此增加、删除或继续加码产品配置。",
            boundary_cn="没有把 unknown、缺失事实或其他投入分类改写成确定答案。",
            limitations=[f"investment_classification_not_found:{classification}"],
        )
    names = [_capability_name(row) for row in rows]
    direct_templates = {
        "retain": f"值得继续保留的投入是：{'、'.join(names)}。",
        "unconverted": f"已投入但尚未转化成稳定用户价值的是：{'、'.join(names)}。",
        "do_not_follow": f"当前不需要为了跟竞品而补的配置是：{'、'.join(names)}。",
        "missing_competitive_gap": f"需要优先评估补齐的竞争缺口是：{'、'.join(names)}。",
        "table_stake": f"应保持但不作为溢价亮点的基础竞争能力是：{'、'.join(names)}。",
    }
    work_templates = {
        "retain": "产品定义应保留这些投入，并继续保证用户体验兑现。",
        "unconverted": "先改善体验兑现和卖点表达，不建议继续只堆参数。",
        "do_not_follow": "可把资源留给已形成用户价值的投入，不为参数对齐而跟进。",
        "missing_competitive_gap": "进入下一轮产品定义评估，优先核对补齐成本和受影响用户价值。",
        "table_stake": "维持可用性即可，不把它承担为核心溢价和差异化任务。",
    }
    capability_codes = {str(row.get("capability_code")) for row in rows}
    candidate_codes = {
        str(code) for row in rows for code in row.get("candidate_scope_ids", [])
    }
    candidates = [
        row for row in bundle.candidates if row.candidate_sku_code in candidate_codes
    ]
    items = [
        row
        for row in bundle.value_items
        if capability_codes.intersection(row.capability_codes_json)
    ]
    facts = [
        ProfileQaFact(
            fact_path=f"investment_decisions.{row.get('capability_code')}",
            summary_cn=(
                f"{_capability_name(row)}："
                f"{_business_text(row.get('business_reason_cn') or '画像已保存该投入分类。')}"
            ),
            record_type="sku_sellpoint_value_profile",
            record_id=bundle.profile.sku_sellpoint_value_profile_id,
        )
        for row in rows
    ]
    return _answer(
        bundle,
        question=question,
        topic_code=topic,
        answer_status="answered",
        direct_answer_cn=direct_templates[classification],
        facts=facts,
        work_implication_cn=work_templates[classification],
        boundary_cn="；".join(
            sorted(
                {
                    _business_text(
                        str(row.get("boundary_cn") or "只适用于当前画像候选范围。")
                    )
                    for row in rows
                }
            )
        ),
        candidate_rows=candidates,
        value_rows=items,
    )


def _price_answer(
    bundle: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    summary = str(
        bundle.profile.pm_decisions_json.get("current_price_support_cn") or ""
    ).strip()
    items = [row for row in bundle.value_items if row.price_realization_json]
    if not summary:
        return _unknown(bundle, question, "price_support", "画像没有保存当前价格支撑结论。")
    facts = [
        ProfileQaFact(
            fact_path="pm_decisions.current_price_support_cn",
            summary_cn=_business_text(summary),
            record_type="sku_sellpoint_value_profile",
            record_id=bundle.profile.sku_sellpoint_value_profile_id,
        ),
        *(
            ProfileQaFact(
                fact_path=f"value_items.{row.normalized_bundle_code}.price_realization",
                summary_cn=(
                    f"{row.value_bundle_name_cn}："
                    f"{_market_payload_cn(row.price_realization_json, '价格')}"
                ),
                record_type="sku_sellpoint_value_item",
                record_id=row.sku_sellpoint_value_item_id,
            )
            for row in items
        ),
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="price_support",
        answer_status="answered",
        direct_answer_cn=_business_text(summary),
        facts=facts,
        work_implication_cn="据此决定当前价位应保持、调整表达，还是进入价格调整评估。",
        boundary_cn="这是当前候选范围内的市场表现判断，不等于单一卖点的因果溢价。",
        candidate_rows=_question_candidates(bundle, {"current_price_support"}),
        value_rows=items,
    )


def _price_increment_answer(
    bundle: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    rows = [
        row
        for row in bundle.value_items
        if row.price_realization_json.get("own_price_curve")
    ]
    if not rows:
        return _answer(
            bundle,
            question=question,
            topic_code="price_volume_increment",
            answer_status="unknown",
            direct_answer_cn="当前画像不能量化降价会增加多少销量。",
            work_implication_cn="可以评估价格调整方向，但不能把方向性判断写成确定增量。",
            boundary_cn="画像未保存本品可用的历史价格变化曲线或合格准实验结果。",
            limitations=["qualified_own_price_curve_not_available"],
        )
    facts = [
        ProfileQaFact(
            fact_path=f"value_items.{row.normalized_bundle_code}.price_realization.own_price_curve",
            summary_cn=f"{row.value_bundle_name_cn}：画像已保存本品价格变化曲线。",
            record_type="sku_sellpoint_value_item",
            record_id=row.sku_sellpoint_value_item_id,
        )
        for row in rows
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="price_volume_increment",
        answer_status="limited",
        direct_answer_cn="画像存在本品价格变化曲线，但需要按画像保存的区间读取，不能给出区间外销量承诺。",
        facts=facts,
        work_implication_cn="可用画像区间做价格方案测算，并同时评估同品牌产品分流。",
        boundary_cn="历史价格关联不自动等同未来因果增量；当前回答不外推画像未保存的价格点。",
        value_rows=rows,
        limitations=["observational_price_curve_only"],
    )


def _volume_answer(
    bundle: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    summary = str(bundle.profile.pm_decisions_json.get("growth_action_cn") or "").strip()
    items = [row for row in bundle.value_items if row.volume_realization_json]
    if not summary:
        return _unknown(bundle, question, "volume_action", "画像没有保存走量动作。")
    facts = [
        ProfileQaFact(
            fact_path="pm_decisions.growth_action_cn",
            summary_cn=_business_text(summary),
            record_type="sku_sellpoint_value_profile",
            record_id=bundle.profile.sku_sellpoint_value_profile_id,
        ),
        *(
            ProfileQaFact(
                fact_path=f"value_items.{row.normalized_bundle_code}.volume_realization",
                summary_cn=(
                    f"{row.value_bundle_name_cn}："
                    f"{_market_payload_cn(row.volume_realization_json, '销量')}"
                ),
                record_type="sku_sellpoint_value_item",
                record_id=row.sku_sellpoint_value_item_id,
            )
            for row in items
        ),
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="volume_action",
        answer_status="answered",
        direct_answer_cn=_business_text(summary),
        facts=facts,
        work_implication_cn="把画像中的动作作为价格、卖点或 SKU 角色方案输入，再结合成本约束决策。",
        boundary_cn="销量表现是当前市场关联；没有净新增证据时不承诺必然增量。",
        candidate_rows=_question_candidates(bundle, {"scale_conversion"}),
        value_rows=items,
    )


def _candidate_answer(
    bundle: SellpointValueProfileReadBundle,
    *,
    question: str,
    candidate_sku_code: str | None,
) -> SellpointValueProfileAnswer:
    candidate = _find_candidate(bundle, candidate_sku_code, question)
    if candidate is None:
        return _answer(
            bundle,
            question=question,
            topic_code="competitor_selection",
            answer_status="unknown",
            direct_answer_cn="当前画像中没有找到指定产品，不能解释它为何被采用或未采用。",
            work_implication_cn="请从报告的完整竞品或分析参照清单中指定 SKU。",
            boundary_cn="没有临时从市场池新增产品，也没有把分析参照改称竞品。",
            limitations=["candidate_not_found_in_profile"],
        )
    analyses = [
        row
        for row in bundle.profile.question_analyses_json
        if candidate.candidate_sku_code
        in (
            set(row.get("eligible_candidate_ids", []))
            | set(row.get("selected_candidate_ids", []))
            | {
                str(code)
                for rejected in row.get("rejected_candidates", [])
                for code in rejected.get("candidate_sku_codes", [])
            }
        )
    ]
    selected = [
        row
        for row in analyses
        if candidate.candidate_sku_code in row.get("selected_candidate_ids", [])
    ]
    rejected_reasons = [
        str(reason)
        for row in analyses
        for rejected in row.get("rejected_candidates", [])
        if candidate.candidate_sku_code in rejected.get("candidate_sku_codes", [])
        for reason in rejected.get("reasons", [])
    ]
    name = _candidate_name(candidate)
    if selected:
        direct = (
            f"{name} 被用于回答 "
            f"{'、'.join(sorted({str(row.get('business_question_cn')) for row in selected}))}。"
        )
        status: ProfileQaStatus = "answered"
    elif analyses:
        direct = (
            f"{name} 在画像候选范围内，但没有被当前问题最终采用。"
            + (f"原因：{'；'.join(sorted(set(rejected_reasons)))}。" if rejected_reasons else "")
        )
        status = "answered"
    else:
        direct = f"{name} 被保留在画像清单中，但没有进入任何已保存的问题比较。"
        status = "limited"
    facts = [
        ProfileQaFact(
            fact_path=f"candidates.{candidate.candidate_sku_code}",
            summary_cn=(
                f"{name} 的用途是"
                f"{'竞争产品' if candidate.pool_type == 'competitor' else '市场与产品设计参照'}，"
                f"{_candidate_status_cn(candidate.eligibility_status)}。"
            ),
            record_type="sku_sellpoint_value_candidate",
            record_id=candidate.sku_sellpoint_value_candidate_id,
        ),
        *(
            ProfileQaFact(
                fact_path=f"question_analyses.{row.get('result_hash')}",
                summary_cn=_question_analysis_cn(row, candidate.candidate_sku_code),
                record_type="sku_sellpoint_value_profile",
                record_id=bundle.profile.sku_sellpoint_value_profile_id,
            )
            for row in analyses
        ),
    ]
    item_keys = {
        (str(row.get("battlefield_code")), str(row.get("value_bundle_code")))
        for row in analyses
    }
    items = [
        row
        for row in bundle.value_items
        if (row.battlefield_code, row.value_bundle_code) in item_keys
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="competitor_selection",
        answer_status=status,
        direct_answer_cn=_business_text(direct),
        facts=facts,
        work_implication_cn=(
            "若为竞争产品，可用于当前竞争取舍；若为分析参照，只用于市场或产品设计判断。"
        ),
        boundary_cn="是否采用按画像保存的问题级可用条件判断，不代表该产品对所有问题都可比。",
        candidate_rows=[candidate],
        value_rows=items,
        limitations=[] if status == "answered" else ["candidate_not_selected_for_question"],
    )


def _source_pool_answer(
    bundle: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    competitors = [row for row in bundle.candidates if row.pool_type == "competitor"]
    references = [row for row in bundle.candidates if row.pool_type == "reference"]
    direct = (
        f"当前画像保存 {len(competitors)} 款竞争产品和 {len(references)} 款市场与产品设计参照。"
        "竞争产品用于竞争取舍，分析参照只用于市场、参数或价值战场判断。"
    )
    facts = [
        ProfileQaFact(
            fact_path="candidate_universe_summary",
            summary_cn=direct,
            record_type="sku_sellpoint_value_profile",
            record_id=bundle.profile.sku_sellpoint_value_profile_id,
        )
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="source_pool",
        answer_status="answered",
        direct_answer_cn=direct,
        facts=facts,
        work_implication_cn="看竞争输赢时只使用竞争产品；看参数、市场基线或新价值方向时可使用分析参照。",
        boundary_cn="分析参照不回答用户为什么在两款产品中作选择。",
        candidate_rows=[*competitors, *references],
    )


def _battlefield_answer(
    bundle: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    options = bundle.profile.battlefield_options_json
    items = list(bundle.value_items)
    if not options and not items:
        return _unknown(bundle, question, "battlefield_action", "画像没有保存价值战场动作。")
    summary = str(bundle.profile.pm_decisions_json.get("growth_action_cn") or "").strip()
    direct = _business_text(summary) if summary else (
        f"画像保存了 {len(options)} 个价值战场选项，需按各选项的已保存状态逐项查看。"
    )
    facts = [
        ProfileQaFact(
            fact_path="battlefield_options",
            summary_cn=f"画像保存 {len(options)} 个战场动作选项。",
            record_type="sku_sellpoint_value_profile",
            record_id=bundle.profile.sku_sellpoint_value_profile_id,
        ),
        *(
            ProfileQaFact(
                fact_path=f"value_items.{row.battlefield_code}.{row.normalized_bundle_code}",
                summary_cn=f"{row.battlefield_name_cn or row.battlefield_code}：{row.perceived_outcome_cn}",
                record_type="sku_sellpoint_value_item",
                record_id=row.sku_sellpoint_value_item_id,
            )
            for row in items
        ),
    ]
    return _answer(
        bundle,
        question=question,
        topic_code="battlefield_action",
        answer_status="answered",
        direct_answer_cn=direct,
        facts=facts,
        work_implication_cn="优先按画像已成立的用户价值增强现有战场；新战场只在画像明确满足进入条件时立项。",
        boundary_cn="已有战场的销量分配不是净新增销量，新战场空间也不是本品必然可获得销量。",
        value_rows=items,
    )


def _version_diff_answer(
    current: SellpointValueProfileReadBundle,
    previous: SellpointValueProfileReadBundle,
    question: str,
) -> SellpointValueProfileAnswer:
    old_candidates = {
        (row.pool_type, row.candidate_sku_code): row for row in previous.candidates
    }
    new_candidates = {
        (row.pool_type, row.candidate_sku_code): row for row in current.candidates
    }
    added = sorted(code for _, code in set(new_candidates) - set(old_candidates))
    removed = sorted(code for _, code in set(old_candidates) - set(new_candidates))
    old_investments = {
        str(row.get("capability_code")): (
            _capability_name(row),
            str(row.get("classification")),
        )
        for row in previous.profile.investment_decisions_json
    }
    new_investments = {
        str(row.get("capability_code")): (
            _capability_name(row),
            str(row.get("classification")),
        )
        for row in current.profile.investment_decisions_json
    }
    changed = [
        (
            f"{(new_investments.get(code) or old_investments.get(code) or (code, ''))[0]}："
            f"{_investment_status_cn((old_investments.get(code) or ('', 'none'))[1])}→"
            f"{_investment_status_cn((new_investments.get(code) or ('', 'none'))[1])}"
        )
        for code in sorted(set(old_investments) | set(new_investments))
        if old_investments.get(code) != new_investments.get(code)
    ]
    parts = [
        f"候选新增 {len(added)} 款、移除 {len(removed)} 款",
        f"投入判断变化 {len(changed)} 项",
        (
            "价格与产品动作结论发生变化"
            if current.profile.pm_decisions_json != previous.profile.pm_decisions_json
            else "价格与产品动作结论未变化"
        ),
    ]
    facts = [
        ProfileQaFact(
            fact_path="profile_version_diff.candidates",
            summary_cn=f"新增：{'、'.join(added) or '无'}；移除：{'、'.join(removed) or '无'}。",
            record_type="sku_sellpoint_value_profile",
            record_id=current.profile.sku_sellpoint_value_profile_id,
        ),
        ProfileQaFact(
            fact_path="profile_version_diff.investments",
            summary_cn="；".join(changed) if changed else "投入分类未变化。",
            record_type="sku_sellpoint_value_profile",
            record_id=current.profile.sku_sellpoint_value_profile_id,
        ),
    ]
    return _answer(
        current,
        question=question,
        topic_code="version_change",
        answer_status="answered",
        direct_answer_cn="；".join(parts) + "。",
        facts=facts,
        work_implication_cn="优先复核由候选范围变化带来的结论变化，再决定是否调整产品定义。",
        boundary_cn=(
            f"仅比较同一批次 SKU 的 {previous.profile.profile_version} 与 "
            f"{current.profile.profile_version} 两个已保存画像，不重算历史结果。"
        ),
        candidate_rows=list(new_candidates.values()),
        value_rows=current.value_items,
    )


def _answer(
    bundle: SellpointValueProfileReadBundle,
    *,
    question: str,
    topic_code: ProfileQaTopicCode,
    answer_status: ProfileQaStatus,
    direct_answer_cn: str,
    work_implication_cn: str,
    boundary_cn: str,
    facts: Sequence[ProfileQaFact] = (),
    candidate_rows: Sequence[Any] = (),
    value_rows: Sequence[Any] = (),
    limitations: Sequence[str] = (),
) -> SellpointValueProfileAnswer:
    fact_paths = sorted({row.fact_path for row in facts})
    candidate_record_ids = sorted(
        {row.sku_sellpoint_value_candidate_id for row in candidate_rows}
    )
    value_item_record_ids = sorted(
        {row.sku_sellpoint_value_item_id for row in value_rows}
    )
    evidence_refs = _evidence_refs(bundle, candidate_rows, value_rows)
    payload = {
        "question": question.strip(),
        "topic_code": topic_code,
        "answer_status": answer_status,
        "direct_answer_cn": _business_text(direct_answer_cn),
        "profile_facts": [row.model_dump(mode="json") for row in facts],
        "work_implication_cn": _business_text(work_implication_cn),
        "evidence_boundary_cn": _business_text(boundary_cn),
        "project_id": bundle.profile.project_id,
        "category_code": bundle.profile.category_code,
        "batch_id": bundle.profile.batch_id,
        "sku_code": bundle.profile.sku_code,
        "profile_version": bundle.profile.profile_version,
        "release_status": bundle.profile.release_status,
        "result_hash": bundle.profile.result_hash,
        "fact_paths": fact_paths,
        "candidate_record_ids": candidate_record_ids,
        "value_item_record_ids": value_item_record_ids,
        "evidence_refs": evidence_refs,
        "limitations": sorted(set(limitations)),
    }
    return SellpointValueProfileAnswer(
        **payload,
        answer_hash=stable_hash(payload, version=PROFILE_QA_HASH_VERSION),
    )


def _unknown(
    bundle: SellpointValueProfileReadBundle,
    question: str,
    topic: ProfileQaTopicCode,
    reason_cn: str,
) -> SellpointValueProfileAnswer:
    return _answer(
        bundle,
        question=question,
        topic_code=topic,
        answer_status="unknown",
        direct_answer_cn=reason_cn,
        work_implication_cn="暂不据此调整产品定义、价格或 SKU 角色。",
        boundary_cn="画像没有保存足以回答该问题的事实，本次未临时重算。",
        limitations=[f"profile_fact_not_available:{topic}"],
    )


def _apply_quality_boundary(
    answer: SellpointValueProfileAnswer,
    bundle: SellpointValueProfileReadBundle,
) -> SellpointValueProfileAnswer:
    reasons = []
    if bundle.profile.freshness_status == "stale":
        reasons.append("画像上游已变化，本回答只能用于回看。")
    if bundle.profile.analysis_state == "blocked":
        reasons.append("画像关键证据不足或冲突，本回答不能形成正式产品取舍。")
    if not reasons:
        return answer
    payload = answer.model_dump(mode="python", exclude={"answer_hash"})
    payload["answer_status"] = (
        "unknown" if answer.answer_status == "unknown" else "limited"
    )
    payload["evidence_boundary_cn"] = (
        f"{answer.evidence_boundary_cn} {' '.join(reasons)}"
    ).strip()
    payload["limitations"] = sorted(
        set([*answer.limitations, *reasons])
    )
    return SellpointValueProfileAnswer(
        **payload,
        answer_hash=stable_hash(payload, version=PROFILE_QA_HASH_VERSION),
    )


def _question_candidates(
    bundle: SellpointValueProfileReadBundle,
    question_codes: set[str],
) -> list[Any]:
    codes = {
        str(code)
        for analysis in bundle.profile.question_analyses_json
        if str(analysis.get("question_code")) in question_codes
        for code in analysis.get("selected_candidate_ids", [])
    }
    return [row for row in bundle.candidates if row.candidate_sku_code in codes]


def _find_candidate(
    bundle: SellpointValueProfileReadBundle,
    candidate_sku_code: str | None,
    question: str,
) -> Any | None:
    if candidate_sku_code:
        normalized = candidate_sku_code.strip().lower()
        return next(
            (
                row
                for row in bundle.candidates
                if row.candidate_sku_code.lower() == normalized
            ),
            None,
        )
    matches = [
        row
        for row in bundle.candidates
        if row.candidate_sku_code.lower() in question.lower()
        or (row.candidate_model_name or "").lower() in question.lower()
        and bool(row.candidate_model_name)
    ]
    return matches[0] if len(matches) == 1 else None


def _question_analysis_cn(row: dict[str, Any], sku_code: str) -> str:
    if sku_code in row.get("selected_candidate_ids", []):
        return f"用于回答：{row.get('business_question_cn')}。"
    reasons = [
        str(reason)
        for rejected in row.get("rejected_candidates", [])
        if sku_code in rejected.get("candidate_sku_codes", [])
        for reason in rejected.get("reasons", [])
    ]
    if reasons:
        return f"未用于回答 {row.get('business_question_cn')}：{'；'.join(reasons)}。"
    return f"属于 {row.get('business_question_cn')} 的可用候选，但未被最终采用。"


def _evidence_refs(
    bundle: SellpointValueProfileReadBundle,
    candidates: Sequence[Any],
    items: Sequence[Any],
) -> list[dict[str, Any]]:
    rows = [
        *_profile_evidence_summary_refs(bundle.profile.evidence_refs_json),
        *(ref for row in candidates for ref in row.evidence_refs_json),
        *(ref for row in items for ref in row.evidence_refs_json),
    ]
    deduped = {
        (row.module_code, row.record_type, row.record_id, row.result_hash): row
        for row in rows
    }
    return [
        deduped[key].model_dump(mode="json")
        for key in sorted(deduped)
    ]


def _profile_evidence_summary_refs(rows: Sequence[Any]) -> list[Any]:
    """Keep one audit anchor per upstream module in the PM-facing answer."""

    direct_refs = [
        row for row in rows if row.record_type != "profile_source_lineage"
    ]
    lineage_by_module: dict[str, list[Any]] = {}
    for row in rows:
        if row.record_type != "profile_source_lineage":
            continue
        lineage_by_module.setdefault(row.module_code, []).append(row)
    summaries = []
    for module_code, module_rows in sorted(lineage_by_module.items()):
        summaries.append(
            min(
                module_rows,
                key=lambda row: (
                    not row.record_id.startswith(f"{module_code}:"),
                    row.record_id,
                    row.result_hash,
                ),
            )
        )
    return [*direct_refs, *summaries]


def _market_payload_cn(payload: dict[str, Any], label: str) -> str:
    status = str(payload.get("status") or "unknown")
    if status == "available":
        return f"已有可用的{label}表现比较。"
    if status == "degraded":
        return f"{label}表现只能作方向性判断。"
    status_cn = {
        "blocked": "关键事实不足",
        "unidentifiable": "无法单独识别",
        "not_applicable": "不适用于当前问题",
        "unknown": "现有证据不足",
    }.get(status, "现有证据不足")
    return f"当前{label}表现{status_cn}，不能形成更强结论。"


def _capability_name(row: dict[str, Any]) -> str:
    return str(row.get("capability_name_cn") or row.get("capability_code") or "未命名投入")


def _candidate_name(row: Any) -> str:
    return (
        f"{row.candidate_brand_name or ''} "
        f"{row.candidate_model_name or row.candidate_sku_code}"
    ).strip()


def _candidate_status_cn(status: str) -> str:
    return {
        "eligible": "可用于当前画像中的正式比较",
        "limited": "只可用于已有数据支持的部分问题",
        "review_required": "需要复核后才能形成正式结论",
        "blocked": "当前不能参与正式结论",
        "recalled_only": "只保留在候选清单，尚未完成可比性判断",
    }.get(status, "当前用途尚未明确")


def _investment_status_cn(status: str) -> str:
    return {
        "retain": "继续保留",
        "unconverted": "尚未转化",
        "do_not_follow": "当前不用跟",
        "table_stake": "保持基础竞争能力",
        "missing_competitive_gap": "优先评估补齐",
        "unknown": "暂不作产品取舍",
        "none": "无",
    }.get(status, "暂不作产品取舍")


def _business_text(value: Any) -> str:
    text = str(value)
    replacements = {
        "反事实": "对照比较",
        "合成对照": "市场基线比较",
        "合成控制": "市场基线比较",
        "门禁": "可用条件",
        "门槛功能": "基础竞争能力",
        "门槛": "普及判断",
        "counterfactual": "comparison",
        "synthetic control": "market baseline",
    }
    for internal, business in replacements.items():
        text = text.replace(internal, business)
    return text


__all__ = [
    "PROFILE_QA_HASH_VERSION",
    "ProfileQaFact",
    "ProfileQaStatus",
    "ProfileQaTargetAmbiguousError",
    "ProfileQaTopicCode",
    "SellpointValueProfileAnswer",
    "SellpointValueProfileQaService",
    "route_profile_question",
]
