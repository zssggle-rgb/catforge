"""Deterministic Q&A over one locked, saved V5.1 profile."""

from __future__ import annotations

from typing import Any, Sequence

from app.services.core3_real_data.analyst.sellpoint_value_profile_qa import (
    PROFILE_QA_HASH_VERSION,
    ProfileQaFact,
    ProfileQaTargetAmbiguousError,
    ProfileQaTopicCode,
    SellpointValueProfileAnswer,
    route_profile_question,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_report import (
    build_v5_1_stored_profile_pm_report,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_consumer import (
    SellpointValueV51ConsumerReadRequest,
    SellpointValueV51ConsumerReader,
)
from app.services.core3_real_data.hash_utils import stable_hash


class SellpointValueV51QaService:
    """Answer product questions from saved fields without analytical fallback."""

    def __init__(self, reader: SellpointValueV51ConsumerReader) -> None:
        self.reader = reader

    def answer(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        question: str,
        sku_code: str | None = None,
        model_name: str | None = None,
        query: str | None = None,
        access_mode: str = "formal",
        profile_version: str | None = None,
        sellpoint_value_profile_version_id: str | None = None,
        expected_result_hash: str | None = None,
        topic_code: ProfileQaTopicCode | None = None,
        candidate_sku_code: str | None = None,
    ) -> SellpointValueProfileAnswer | None:
        read = self.reader.read(
            SellpointValueV51ConsumerReadRequest(
                project_id=project_id,
                category_code=category_code,
                batch_id=batch_id,
                access_mode=access_mode,
                sku_code=sku_code,
                model_name=model_name,
                query=query,
                profile_version=profile_version,
                sellpoint_value_profile_version_id=(sellpoint_value_profile_version_id),
            )
        )
        if read.status == "profile_unavailable":
            return None
        if read.status == "ambiguous":
            raise ProfileQaTargetAmbiguousError(read.candidates)
        assert read.readback is not None
        readback = read.readback
        topic = topic_code or route_profile_question(question)
        if expected_result_hash and (
            readback.profile.result_hash != expected_result_hash
        ):
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status="unknown",
                direct_answer_cn="指定报告与当前读取画像不是同一份结果，不能继续回答。",
                work_implication_cn="请使用同一份报告中的结果编号重新发起追问。",
                boundary_cn="本次没有读取或重算其他版本的数据。",
                limitations=["expected_result_hash_mismatch"],
            )
        consumer_status = readback.profile.sku_conclusion.consumer_status
        if consumer_status == "data_insufficient":
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status="unknown",
                direct_answer_cn=(
                    "现有数据不足，暂不能形成该 SKU 的用户卖点价值结论。"
                ),
                work_implication_cn="当前不据此调整产品投入、价格或 SKU 角色。",
                boundary_cn="只返回画像已保存的无结论状态，没有现场补算。",
                limitations=["data_insufficient"],
            )
        if consumer_status == "invalid":
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status="unknown",
                direct_answer_cn=(
                    "画像数据完整性异常，暂不能形成该 SKU 的用户卖点价值结论。"
                ),
                work_implication_cn="请先修复画像数据，再使用产品结论。",
                boundary_cn="本次没有绕过异常或回退到旧画像。",
                limitations=["profile_invalid"],
            )
        return self._answer_topic(
            readback,
            question=question,
            topic=topic,
            candidate_sku_code=candidate_sku_code,
        )

    def _answer_topic(
        self,
        readback: Any,
        *,
        question: str,
        topic: ProfileQaTopicCode,
        candidate_sku_code: str | None,
    ) -> SellpointValueProfileAnswer:
        report = build_v5_1_stored_profile_pm_report(readback)
        screen = report.first_screen
        status = "limited" if report.consumer_status == "usable_partial" else "answered"
        if topic in {"retain_investment", "capability_investment"}:
            rows = _matching_investments(report.investment_decisions, question)
            text = (
                "；".join(
                    f"{row.capability_name_cn}：{row.action_cn}，{row.business_reason_cn}"
                    for row in rows
                )
                or screen.retain_cn
            )
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status=status,
                direct_answer_cn=text,
                work_implication_cn="将已确认的差异化投入纳入产品定义和资源优先级。",
                boundary_cn="动作来自画像保存的局部投入结论，不从置信度或复核原因重新推导。",
                facts=_investment_facts(rows),
            )
        if topic == "unconverted_investment":
            return _screen_answer(
                readback,
                question,
                topic,
                status,
                screen.unconverted_cn,
                "优先改善用户能感知的体验兑现，再决定是否继续加投入。",
                "first_screen.unconverted_cn",
            )
        if topic in {"do_not_follow", "missing_gap"}:
            return _screen_answer(
                readback,
                question,
                topic,
                status,
                screen.competitor_action_cn,
                "用于区分需要补齐的竞争缺口与无需跟进的参数配置。",
                "first_screen.competitor_action_cn",
            )
        if topic == "price_support":
            facts = _market_facts(readback, metric="price")
            return _screen_answer(
                readback,
                question,
                topic,
                status if facts else "limited",
                screen.price_support_cn,
                "用于判断当前价格位置是否需要调整，或先强化已有用户价值。",
                "first_screen.price_support_cn",
                facts=facts,
            )
        if topic in {"volume_action", "price_volume_increment"}:
            facts = _market_facts(readback, metric="sales")
            boundary = "回答来自已保存的周均量价、市场原型或市场基线结果；市场关联不解释为随机实验因果。"
            return _screen_answer(
                readback,
                question,
                topic,
                status if facts else "limited",
                screen.growth_action_cn,
                "用于选择先改价格位置、强化卖点表达，还是调整 SKU 角色。",
                "first_screen.growth_action_cn",
                facts=facts,
                boundary_cn=boundary,
            )
        if topic == "competitor_selection":
            candidates = [
                row
                for row in report.full_candidates
                if row.pool_type == "competitor"
                and (
                    candidate_sku_code is None
                    or row.candidate_sku_code == candidate_sku_code
                )
            ]
            direct = "；".join(
                f"{row.candidate_name_cn}：{row.relation_cn}，{row.usability_cn}"
                for row in candidates
            )
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status=status if direct else "limited",
                direct_answer_cn=direct or "该产品未进入本画像的正式竞品范围。",
                work_implication_cn="用候选角色和问题用途选择具体对照，不做逐款无目的量价比较。",
                boundary_cn="竞品范围和用途直接来自已保存的两池与问题级候选。",
                facts=_candidate_facts(candidates),
                limitations=[] if direct else ["candidate_not_in_formal_pool"],
            )
        if topic == "source_pool":
            direct = (
                f"本画像保存正式竞品 {report.candidate_count} 款，"
                f"市场与产品设计参照 {report.reference_count} 款；两类产品按问题用途分开使用。"
            )
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status=status,
                direct_answer_cn=direct,
                work_implication_cn="正式竞品用于竞争选择判断，分析参照用于市场、参数或组合比较。",
                boundary_cn="分析参照不会被表述为用户直接二选一的竞品。",
                facts=_candidate_facts(report.full_candidates),
            )
        if topic == "battlefield_action":
            facts = _archetype_facts(readback)
            direct = "；".join(row.summary_cn for row in facts)
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status=status if direct else "limited",
                direct_answer_cn=direct or "现有画像尚未形成明确的价值战场动作结论。",
                work_implication_cn="优先使用已保存的增强已有战场或相邻战场参照安排产品动作。",
                boundary_cn="可选市场原型无结论时不会抹掉已有直接量价结论。",
                facts=facts,
            )
        if topic == "table_stake":
            rows = [
                row
                for value in readback.profile.values
                for row in value.investment_decisions
                if row.classification == "table_stake"
                and _enum_text(row.status)
                in {"conclusion_available", "partial_conclusion"}
            ]
            direct = "；".join(row.business_reason_cn for row in rows)
            return _make_answer(
                readback,
                question=question,
                topic=topic,
                answer_status=status if direct else "limited",
                direct_answer_cn=direct or "现有画像没有确认该能力属于基础竞争能力。",
                work_implication_cn="基础竞争能力维持可用性，但不占据核心卖点和溢价任务。",
                boundary_cn="只有画像保存为 table_stake 的能力才进入本答案。",
                facts=[
                    ProfileQaFact(
                        fact_path=f"values.{row.value_bundle_code}.investments.{row.capability_code}",
                        summary_cn=row.business_reason_cn,
                        record_type="investment_decision",
                        record_id=row.result_hash,
                    )
                    for row in rows
                ],
            )
        return _make_answer(
            readback,
            question=question,
            topic=topic,
            answer_status="unknown",
            direct_answer_cn="这份用户卖点价值画像没有保存回答该问题所需的业务事实。",
            work_implication_cn="请改问产品投入、价格、销量、竞品或价值战场问题。",
            boundary_cn="本次没有调用其他模块补算答案。",
            limitations=["unsupported_profile_question"],
        )


def _screen_answer(
    readback: Any,
    question: str,
    topic: ProfileQaTopicCode,
    status: str,
    direct: str,
    implication: str,
    fact_path: str,
    *,
    facts: Sequence[ProfileQaFact] = (),
    boundary_cn: str = "答案只映射当前画像保存的业务结论。",
) -> SellpointValueProfileAnswer:
    return _make_answer(
        readback,
        question=question,
        topic=topic,
        answer_status=status,
        direct_answer_cn=direct,
        work_implication_cn=implication,
        boundary_cn=boundary_cn,
        facts=[
            ProfileQaFact(
                fact_path=fact_path,
                summary_cn=direct,
                record_type="profile_projection",
                record_id=readback.profile.result_hash,
            ),
            *facts,
        ],
    )


def _make_answer(
    readback: Any,
    *,
    question: str,
    topic: ProfileQaTopicCode,
    answer_status: str,
    direct_answer_cn: str,
    work_implication_cn: str,
    boundary_cn: str,
    facts: Sequence[ProfileQaFact] = (),
    limitations: Sequence[str] = (),
) -> SellpointValueProfileAnswer:
    profile = readback.profile
    persisted = readback.persisted
    evidence_refs = _evidence_refs(profile, facts)
    payload = {
        "schema_version": "sellpoint_value_profile_answer_v1_1",
        "question": question,
        "topic_code": topic,
        "answer_status": answer_status,
        "direct_answer_cn": direct_answer_cn,
        "profile_facts": list(facts),
        "work_implication_cn": work_implication_cn,
        "evidence_boundary_cn": boundary_cn,
        "project_id": profile.project_id,
        "category_code": profile.category_code,
        "batch_id": profile.batch_id,
        "sku_code": profile.target.sku_code,
        "profile_version": profile.profile_version,
        "release_status": persisted.version.release_status,
        "result_hash": profile.result_hash,
        "fact_paths": [row.fact_path for row in facts],
        "candidate_record_ids": [
            row.sku_sellpoint_value_candidate_id for row in persisted.candidates
        ],
        "value_item_record_ids": [
            row.sku_sellpoint_value_item_id for row in persisted.value_items
        ],
        "evidence_refs": evidence_refs,
        "limitations": list(dict.fromkeys([*limitations, *profile.limitations])),
    }
    answer_hash = stable_hash(
        {
            **payload,
            "profile_facts": [row.model_dump(mode="json") for row in facts],
        },
        version=PROFILE_QA_HASH_VERSION,
    )
    return SellpointValueProfileAnswer(**payload, answer_hash=answer_hash)


def _matching_investments(rows: Sequence[Any], question: str) -> list[Any]:
    matched = [
        row
        for row in rows
        if row.capability_name_cn in question or row.capability_code in question
    ]
    return matched or [row for row in rows if row.action_code == "retain"]


def _investment_facts(rows: Sequence[Any]) -> list[ProfileQaFact]:
    return [
        ProfileQaFact(
            fact_path=f"investment_decisions.{row.capability_code}",
            summary_cn=f"{row.capability_name_cn}：{row.action_cn}",
            record_type="investment_decision",
            record_id=row.capability_code,
        )
        for row in rows
    ]


def _market_facts(readback: Any, *, metric: str) -> list[ProfileQaFact]:
    result = []
    for value in readback.profile.values:
        for row in value.direct_market_results:
            comparison = (
                row.price_comparison if metric == "price" else row.sales_comparison
            )
            if comparison is None or _enum_text(row.status) not in {
                "conclusion_available",
                "partial_conclusion",
            }:
                continue
            result.append(
                ProfileQaFact(
                    fact_path=f"values.{value.value_bundle_code}.direct_market.{metric}",
                    summary_cn=row.business_conclusion_cn,
                    record_type="direct_market_result",
                    record_id=row.result_hash,
                )
            )
        if metric == "sales" and value.synthetic_market_baseline is not None:
            synthetic = value.synthetic_market_baseline
            if synthetic.visible_by_default and _enum_text(synthetic.status) in {
                "conclusion_available",
                "partial_conclusion",
            }:
                result.append(
                    ProfileQaFact(
                        fact_path=f"values.{value.value_bundle_code}.synthetic_market_baseline",
                        summary_cn=synthetic.business_conclusion_cn,
                        record_type="synthetic_market_baseline",
                        record_id=synthetic.result_hash,
                    )
                )
    return result


def _candidate_facts(rows: Sequence[Any]) -> list[ProfileQaFact]:
    return [
        ProfileQaFact(
            fact_path=f"candidate_pools.{row.pool_type}.{row.candidate_sku_code}",
            summary_cn=f"{row.candidate_name_cn}：{row.usability_cn}",
            record_type=f"{row.pool_type}_candidate",
            record_id=row.candidate_sku_code,
        )
        for row in rows
    ]


def _archetype_facts(readback: Any) -> list[ProfileQaFact]:
    return [
        ProfileQaFact(
            fact_path=f"values.{value.value_bundle_code}.market_archetypes.{row.method}",
            summary_cn=row.business_conclusion_cn,
            record_type="market_archetype",
            record_id=row.result_hash,
        )
        for value in readback.profile.values
        for row in value.market_archetype_results
        if row.visible_by_default
        and _enum_text(row.status) in {"conclusion_available", "partial_conclusion"}
    ]


def _evidence_refs(
    profile: Any, facts: Sequence[ProfileQaFact]
) -> list[dict[str, Any]]:
    result = [ref.model_dump(mode="json") for ref in profile.evidence_refs]
    result.extend(
        {
            "module_code": "SPV51",
            "record_type": fact.record_type,
            "record_id": fact.record_id,
            "result_hash": profile.result_hash,
        }
        for fact in facts
    )
    seen: set[tuple[Any, ...]] = set()
    deduped = []
    for row in result:
        key = (
            row.get("module_code"),
            row.get("record_type"),
            row.get("record_id"),
            row.get("result_hash"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


__all__ = ["SellpointValueV51QaService"]
