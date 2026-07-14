"""Render PM artifacts from one saved competitor profile without recomputation."""

from __future__ import annotations

from collections import Counter
import re
from decimal import Decimal
from typing import Any, Iterable

from app.services.core3_real_data.analyst.competitor_answer import _publish_report
from app.services.core3_real_data.analyst.competitor_profile_consumption_schemas import (
    CompetitorProfileConsumptionContext,
)
from app.services.core3_real_data.analyst.competitor_profile_presentation_schemas import (
    CompetitorProfilePresentationBundle,
    CompetitorProfileQuestionAnswer,
)
from app.services.core3_real_data.hash_utils import stable_hash


_INTERNAL_VISIBLE_PATTERN = re.compile(
    r"(?:\bM\d{2}[A-Z]?\b|\bcore3_[a-z0-9_]+\b|sha256:|"
    r"\b[a-z]+_[a-z0-9_]+\b|反事实|门禁|内部模块|结果哈希)"
)
_SOURCE_NAMES = {
    "M03B": "产品参数事实",
    "M04C": "产品卖点事实",
    "M05C": "用户反馈事实",
    "M07": "市场价格与销量",
    "M09C": "用户使用需求",
    "M10C": "目标用户需求",
    "M11C": "用户价值方向",
    "M11D": "同类市场空间",
    "M12C": "卖点市场表现",
    "M12D": "用户成交理由",
}
_GENERIC_VALUE_LABELS = {"相关产品价值", "HDMI 2.1连接"}
_FOUNDATION_CONFIGURATION_LABELS = {
    "相关产品价值",
    "HDMI 2.1连接",
    "屏幕尺寸英寸",
    "语音控制",
}


def build_competitor_profile_presentation(
    context: CompetitorProfileConsumptionContext,
    *,
    with_report: str = "none",
) -> CompetitorProfilePresentationBundle:
    """Build card, two reports, QA and sellpoint handoff from one context."""

    business, evidence = _require_available(context)
    evidence_title = f"{business.目标产品} 竞品识别与分析依据"
    evidence_markdown = render_evidence_report(context, title=evidence_title)
    _assert_business_output(evidence_markdown)
    evidence_delivery = _publish_report(
        title=evidence_title,
        markdown=evidence_markdown,
        with_report=with_report,
    )
    pm_title = f"{business.目标产品} 竞品决策与用户选择分析"
    pm_markdown = render_pm_report(
        context,
        title=pm_title,
        evidence_report_url=evidence_delivery.url,
    )
    _assert_business_output(pm_markdown)
    pm_delivery = _publish_report(
        title=pm_title,
        markdown=pm_markdown,
        with_report=with_report,
    )
    qa_answers = [
        answer_competitor_profile_question(context, question)
        for question in _default_questions()
    ]
    sellpoint = build_sellpoint_consumption_proof(context)
    card = render_feishu_card(
        context,
        pm_report_url=pm_delivery.url,
        evidence_report_url=evidence_delivery.url,
    )
    _assert_business_output(_visible_card_text(card))
    short_answer = render_short_answer(context)
    payload = {
        "competitor_profile_version_id": context.competitor_profile_version_id,
        "profile_version": evidence.profile_version,
        "profile_result_hash": evidence.profile_result_hash,
        "preview": context.preview,
        "short_answer": short_answer,
        "feishu_card_payload": card,
        "pm_report_title": pm_title,
        "pm_report_markdown": pm_markdown,
        "pm_report_delivery": pm_delivery.to_dict(),
        "evidence_report_title": evidence_title,
        "evidence_report_markdown": evidence_markdown,
        "evidence_report_delivery": evidence_delivery.to_dict(),
        "qa_answers": qa_answers,
        "sellpoint_value_consumption": sellpoint,
    }
    return CompetitorProfilePresentationBundle(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_presentation_bundle_v1",
        ),
    )


def render_short_answer(context: CompetitorProfileConsumptionContext) -> str:
    business, _ = _require_available(context)
    choice = _selection_summary(business)
    return "\n".join(
        [
            f"{business.目标产品} 竞品决策",
            f"用户选择｜{choice}",
            f"本品优势｜{_advantage_summary(business)}",
            f"替代风险｜{_substitution_summary(business)}",
            f"价格销量｜{_pressure_summary(business)}",
            f"产品动作｜{_action_summary(business)}",
        ]
    )


def render_pm_report(
    context: CompetitorProfileConsumptionContext,
    *,
    title: str,
    evidence_report_url: str | None = None,
) -> str:
    business, _ = _require_available(context)
    selected = business.重点竞品
    lines = [
        f"# {title}",
        "",
        "## 总结论",
        "",
        f"1. **用户会比较谁**：{_selection_summary(business)}",
        f"2. **本品靠什么赢**：{_advantage_summary(business)}",
        f"3. **哪里容易被替代**：{_substitution_summary(business)}",
        f"4. **价格和销量受谁影响**：{_pressure_summary(business)}",
        f"5. **产品经理怎么做**：{_action_summary(business)}",
        "",
        "## 一、谁会直接竞争，谁只需做战略参照",
        "",
    ]
    if selected:
        for row in selected:
            lines.extend(
                [
                    f"### {row.get('排序')}. {row.get('产品')}",
                    "",
                    str(row.get("为什么要关注") or ""),
                    "",
                ]
            )
    else:
        lines.extend([business.结论状态, ""])
    comparisons = [row for row in business.竞品对比 if row.get("关注层级") == "重点关注"]
    if comparisons:
        lines.extend(
            [
                "| 产品 | 主要竞争关系 | 本品均价 | 对方均价 | 本品周均销量 | 对方周均销量 | 产品判断 |",
                "| --- | --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for row in comparisons:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("产品")),
                        _md(row.get("主要关系")),
                        _money(row.get("本品均价")),
                        _money(row.get("对方均价")),
                        _volume(row.get("本品周均销量")),
                        _volume(row.get("对方周均销量")),
                        _md(row.get("为什么关注")),
                    ]
                )
                + " |"
            )
        lines.append("")
    lines.extend(
        [
            "## 二、本品的优势和替代风险",
            "",
            f"**本品优势**：{_advantage_summary(business)}",
            "",
            f"**替代风险**：{_substitution_summary(business)}",
            "",
            "## 三、价格与销量怎么判断",
            "",
            _pressure_summary(business),
            "",
            "## 四、产品线和配置怎么取舍",
            "",
            f"**产品线角色**：{_portfolio_summary(business)}",
            "",
            f"**配置取舍**：{_configuration_summary(business)}",
            "",
            "## 五、产品经理最终怎么做",
            "",
            f"**{_action_summary(business)}**",
            "",
        ]
    )
    if evidence_report_url and evidence_report_url.startswith("http"):
        lines.extend([f"[查看竞品识别与分析依据]({evidence_report_url})", ""])
    return "\n".join(lines).strip() + "\n"


def render_evidence_report(
    context: CompetitorProfileConsumptionContext,
    *,
    title: str,
) -> str:
    business, evidence = _require_available(context)
    lines = [
        f"# {title}",
        "",
        "## 一、本次比较覆盖了什么",
        "",
        f"本次从同品类市场范围中识别出 {_candidate_total(business)} 款可比较或可参照产品。",
        "重点名单只保留能独立回答产品决策问题的产品，没有为了凑满数量而补入弱候选。",
        "",
        "## 二、这些产品分别能回答什么",
        "",
    ]
    comparisons = business.竞品对比
    if comparisons:
        lines.extend(
            [
                "| 产品 | 关注层级 | 成立的竞争关系 | 可以回答什么 | 市场表现 |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for row in comparisons:
            market = _pair_market_sentence(row)
            relations = "、".join(
                item
                for item in [
                    str(row.get("主要关系") or ""),
                    *(str(value) for value in row.get("辅助关系") or []),
                ]
                if item
            )
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("产品")),
                        _md(row.get("关注层级")),
                        _md(relations or "仅用于专项比较"),
                        _md("、".join(row.get("可以回答") or [])),
                        _md(market),
                    ]
                )
                + " |"
            )
        lines.append("")
    lines.extend(["## 三、结论使用了哪些信息", ""])
    for row in evidence.source_lineage:
        source_name = _SOURCE_NAMES.get(str(row.get("module_code") or ""))
        if source_name:
            lines.append(f"- {source_name}")
    lines.extend(
        [
            "",
            "## 四、哪些结论可以用，哪些不能扩大解释",
            "",
            "- 可以用于比较双方价值路线、均价、周均销量和产品线压力。",
            "- 只有“用户购买选择”有可用结论时，才把候选写成用户会直接二选一的产品。",
            "- 可以用于判断竞品配置是否值得进入产品定义讨论，但不会因为对方具备某项功能就自动要求跟进。",
            "- 价格和销量差用于判断市场压力，不把它写成单项卖点必然带来的销量或涨价结果。",
            "- 仅用于市场参照的产品不会被写成用户会直接二选一的竞品。",
            "",
        ]
    )
    if business.数据不足说明:
        lines.extend(
            [
                "## 五、当前仍需谨慎的部分",
                "",
                str(business.数据不足说明.get("说明") or business.结论状态),
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def render_feishu_card(
    context: CompetitorProfileConsumptionContext,
    *,
    pm_report_url: str | None = None,
    evidence_report_url: str | None = None,
) -> dict[str, Any]:
    business, _ = _require_available(context)
    elements: list[dict[str, Any]] = [
        _card_markdown(f"**总结果**\n{_selection_summary(business)}"),
        {"tag": "hr"},
        _card_markdown(f"**本品靠什么赢**\n{_advantage_summary(business)}"),
        {"tag": "hr"},
        _card_markdown(f"**哪里容易被替代**\n{_substitution_summary(business)}"),
        {"tag": "hr"},
        _card_markdown(f"**价格和销量受谁影响**\n{_pressure_summary(business)}"),
        {"tag": "hr"},
        _card_markdown(f"**产品经理怎么做**\n{_action_summary(business)}"),
    ]
    for label, url, primary in (
        ("查看用户选择对比", pm_report_url, True),
        ("查看分析依据", evidence_report_url, False),
    ):
        if url and url.startswith("http"):
            elements.append(
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": label},
                    "type": "primary" if primary else "default",
                    "url": url,
                }
            )
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"{business.目标产品} 竞品决策",
            },
            "template": "turquoise",
        },
        "body": {"elements": elements},
    }


def answer_competitor_profile_question(
    context: CompetitorProfileConsumptionContext,
    question: str,
) -> CompetitorProfileQuestionAnswer:
    business, evidence = _require_available(context)
    normalized = question.strip()
    if any(token in normalized for token in ("价格", "销量", "降价", "规模")):
        answer = _pressure_summary(business)
        products = _supporting_products(business.价格销量压力, business)
    elif any(token in normalized for token in ("配置", "跟进", "功能")):
        answer = _configuration_summary(business)
        products = _supporting_products(business.配置决策, business)
    elif any(token in normalized for token in ("产品线", "同品牌", "角色")):
        answer = _portfolio_summary(business)
        products = _supporting_products(business.同品牌产品线, business)
    elif any(token in normalized for token in ("优势", "赢", "强")):
        answer = _advantage_summary(business)
        products = _supporting_products(business.本品优势, business)
    elif any(token in normalized for token in ("替代", "风险", "丢")):
        answer = _substitution_summary(business)
        products = _supporting_products(business.可替代价值, business)
    elif any(token in normalized for token in ("谁", "比较", "竞品", "选择")):
        answer = _selection_summary(business)
        products = [str(row.get("产品") or "") for row in business.重点竞品]
    else:
        answer = _action_summary(business)
        products = [str(row.get("产品") or "") for row in business.重点竞品]
    payload = {
        "question_cn": normalized or "本品当前最重要的竞品结论是什么？",
        "answer_cn": answer,
        "supporting_products": sorted(set(filter(None, products))),
        "boundary_cn": "答案只使用本次已确认的竞品分析结果，不临时改变比较对象或重点名单。",
        "competitor_profile_version_id": str(context.competitor_profile_version_id),
        "profile_result_hash": evidence.profile_result_hash,
    }
    return CompetitorProfileQuestionAnswer(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_question_answer_v1",
        ),
    )


def build_sellpoint_consumption_proof(
    context: CompetitorProfileConsumptionContext,
) -> dict[str, Any]:
    business, evidence = _require_available(context)
    candidates = []
    references = []
    for row in evidence.candidate_evidence:
        item = {
            "candidate_sku_code": row.get("candidate_sku_code"),
            "candidate_status": row.get("candidate_status"),
            "selected": bool(row.get("selected")),
            "relation_codes": list(row.get("relation_codes") or []),
            "question_eligibility": list(row.get("question_eligibility") or []),
        }
        if row.get("competitor_member"):
            candidates.append(item)
        if row.get("reference_member"):
            references.append(item)
    return {
        "competitor_profile_version_id": context.competitor_profile_version_id,
        "profile_version": evidence.profile_version,
        "profile_result_hash": evidence.profile_result_hash,
        "target_sku_code": evidence.target_sku_code,
        "formal_candidates": candidates,
        "reference_candidates": references,
        "key_competitor_names": [
            row.get("产品") for row in business.重点竞品 if row.get("产品")
        ],
        "read_only": True,
        "sellpoint_profile_write": False,
        "fallback_used": False,
    }


def _require_available(context: CompetitorProfileConsumptionContext):
    if context.status != "available" or not context.business or not context.evidence:
        raise ValueError("competitor profile presentation requires one available context")
    return context.business, context.evidence


def _default_questions() -> tuple[str, ...]:
    return (
        "用户会拿本品和谁比较？",
        "本品为什么会赢？",
        "哪些用户价值容易被替代？",
        "当前价格和销量受到谁的压力？",
        "哪些配置值得跟进？",
        "同品牌产品线是否需要调整？",
    )


def _selection_summary(business: Any) -> str:
    direct = [
        row
        for row in business.竞品对比
        if "用户购买选择" in (row.get("可以回答") or [])
    ]
    if direct:
        names = [str(row.get("产品") or "") for row in direct[:3]]
        return f"用户可能在本品与{'、'.join(filter(None, names))}之间直接取舍。"
    if not business.重点竞品:
        return "目前还不能把任何一款产品列为本品的直接二选一对象。"
    row = business.重点竞品[0]
    name = str(row.get("产品") or "重点产品")
    purpose = str(row.get("主要回答") or "产品角色与市场压力")
    return (
        "目前还不能把任何一款产品列为本品的直接二选一对象；"
        f"{name}应作为{purpose}参照，重点判断本品的产品角色和市场防守。"
    )


def _advantage_summary(business: Any) -> str:
    if not business.本品优势:
        return (
            "当前没有找到本品相对可比较产品的稳定用户价值优势；"
            "现有卖点不能直接作为加价或继续追加投入的依据。"
        )
    products = _supporting_products(business.本品优势, business)
    suffix = f"，主要相对{'、'.join(products)}成立" if products else ""
    return f"本品已有用户价值证据形成相对优势{suffix}，应优先强化已经被用户感知的部分。"


def _substitution_summary(business: Any) -> str:
    if not business.可替代价值:
        return "当前没有确认哪项核心用户价值正被竞品稳定替代。"
    values = _ranked_labels(
        business.可替代价值,
        key="用户价值",
        excluded=_GENERIC_VALUE_LABELS,
    )
    if not values:
        return "已有竞品能承接与本品相同的用户价值，但现有证据还不能定位到具体价值主题。"
    themes = "、".join(f"{label}（{count}款）" for label, count in values[:5])
    return (
        f"竞争最集中的价值是{themes}。"
        "下一版产品定义应从中选择一至两项建立明确领先，不再把同质功能当作差异化。"
    )


def _pressure_summary(business: Any) -> str:
    rows = business.价格销量压力
    if not rows:
        return "当前没有观察到足以改变本品定价或规模判断的明确竞品压力。"
    sentences = [
        _pressure_sentence(row, business)
        for row in rows[:2]
    ]
    return (
        "；".join(filter(None, sentences))
        + "。这些压力首先指向价值表达和产品角色，降价不应作为第一动作。"
    )


def _portfolio_summary(business: Any) -> str:
    if not business.同品牌产品线:
        target_brand = str(business.目标产品).split(maxsplit=1)[0]
        same_brand = [
            str(row.get("产品") or "")
            for row in business.重点竞品
            if str(row.get("产品") or "").startswith(target_brand)
        ]
        if same_brand:
            return (
                f"当前没有确认{same_brand[0]}正在直接分流本品，但它是最重要的产品线与场景参照；"
                "需要写清两款产品各自的预算、空间和升级理由，避免同系列只靠规格区分。"
            )
        return "当前没有确认同品牌产品正在明显分流本品，产品线不因弱证据调整。"
    products = _supporting_products(business.同品牌产品线, business)
    return f"重点检查{'、'.join(products) or '同品牌相邻产品'}与本品的升级理由是否重复，避免产品线内部互相分流。"


def _configuration_summary(business: Any) -> str:
    if not business.配置决策:
        return "当前没有确认必须跟进的竞品配置；不因为竞品具备某项功能就自动追配。"
    follow = [
        row for row in business.配置决策 if row.get("建议动作") == "评估是否值得跟进"
    ]
    if not follow:
        return "现有配置差异尚未证明会改变用户选择，暂不作为新增投入依据。"
    differences = _ranked_labels(
        follow,
        key="差异配置",
        excluded=_FOUNDATION_CONFIGURATION_LABELS,
    )
    if not differences:
        return (
            "现有差异集中在基础功能或规格层面，不能作为新增投入依据；"
            "只有具体领先档位连接到用户价值和市场压力时才进入产品定义。"
        )
    themes = "、".join(f"{label}（{count}款）" for label, count in differences[:3])
    return (
        f"需要进入产品定义评审的非基础差异集中在{themes}；"
        "先核对双方具体档位和用户兑现，再决定强化或放弃。基础功能不进入重点追配清单。"
    )


def _action_summary(business: Any) -> str:
    if not business.重点竞品:
        return "不为弱候选追配；继续观察是否出现真正能改变用户选择的产品。"
    selected = str(business.重点竞品[0].get("产品") or "重点产品")
    substitution = _ranked_labels(
        business.可替代价值,
        key="用户价值",
        excluded=_GENERIC_VALUE_LABELS,
    )
    value_focus = "、".join(label for label, _ in substitution[:2])
    pressure_products = _supporting_products(business.价格销量压力, business)
    pressure_focus = "、".join(pressure_products[:2]) or selected
    value_action = (
        f"再从{value_focus}中选择一至两项建立领先"
        if value_focus
        else "再选择一至两项用户价值建立领先"
    )
    target_brand = _product_brand(str(business.目标产品))
    selected_brand = _product_brand(selected)
    positioning_action = (
        f"先明确本品与{selected}的产品角色分工"
        if target_brand and selected_brand and target_brand == selected_brand
        else f"先明确本品相对{selected}的目标用户和价值取舍"
    )
    return (
        f"{positioning_action}；{value_action}；"
        f"价格先对照{pressure_focus}的量价表现，不把降价作为第一动作。"
    )


def _product_brand(display_name: str) -> str:
    return display_name.strip().split(maxsplit=1)[0].casefold()


def _ranked_labels(
    rows: Iterable[dict[str, Any]],
    *,
    key: str,
    excluded: set[str],
) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    for row in rows:
        labels = {
            str(value).strip()
            for value in row.get(key) or []
            if str(value).strip() and str(value).strip() not in excluded
        }
        counts.update(labels)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _pressure_sentence(row: dict[str, Any], business: Any) -> str:
    names = _supporting_products([row], business)
    name = names[0] if names else "相关竞品"
    price_gap = _decimal(row.get("价格差幅"))
    volume_ratio = _decimal(row.get("周均销量倍数"))
    direction = str(row.get("市场压力方向") or "")
    price_text = (
        f"均价比本品{'高' if price_gap >= 0 else '低'}{abs(price_gap) * 100:.1f}%"
        if price_gap is not None
        else "均价可比"
    )
    volume_text = (
        f"周均销量是本品{volume_ratio:.2f}倍"
        if volume_ratio is not None
        else "周均销量只能有限比较"
    )
    meaning = {
        "更高价格获得市场接受": "显示更高价方案获得了更强市场承接",
        "同预算竞争压力": "构成同预算下的规模压力",
        "低价分流压力": "构成低价分流压力",
    }.get(direction, "形成可观察的市场压力")
    return f"{name}{price_text}、{volume_text}，{meaning}"


def _supporting_products(rows: Iterable[dict[str, Any]], business: Any) -> list[str]:
    name_by_code = {
        str(row.get("产品编号") or ""): str(row.get("产品") or "")
        for row in business.竞品对比
    }
    return sorted(
        {
            name_by_code.get(str(row.get("参照产品") or ""), "")
            for row in rows
            if name_by_code.get(str(row.get("参照产品") or ""), "")
        }
    )


def _candidate_total(business: Any) -> int:
    return sum(int(value or 0) for value in business.候选概况.values())


def _pair_market_sentence(row: dict[str, Any]) -> str:
    target_price = _money(row.get("本品均价"))
    candidate_price = _money(row.get("对方均价"))
    target_volume = _volume(row.get("本品周均销量"))
    candidate_volume = _volume(row.get("对方周均销量"))
    if "—" in {target_price, candidate_price, target_volume, candidate_volume}:
        return "双方量价信息只能形成有限比较"
    return f"本品{target_price}/{target_volume}，对方{candidate_price}/{candidate_volume}"


def _card_markdown(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _visible_card_text(card: dict[str, Any]) -> str:
    values: list[str] = []

    def walk(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                if child_key in {"content", "text"}:
                    walk(child, child_key)
                elif child_key not in {"url", "schema", "config"}:
                    walk(child, child_key)
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and key in {"content", "text"}:
            values.append(value)

    walk(card)
    return "\n".join(values)


def _assert_business_output(text: str) -> None:
    matched = _INTERNAL_VISIBLE_PATTERN.search(text)
    if matched:
        raise ValueError(f"竞品画像业务输出包含内部术语：{matched.group(0)}")


def _md(value: Any) -> str:
    return str(value or "—").replace("|", "\\|").replace("\n", " ")


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (ValueError, ArithmeticError):
        return None


def _money(value: Any) -> str:
    number = _decimal(value)
    return f"¥{number:,.0f}" if number is not None else "—"


def _volume(value: Any) -> str:
    number = _decimal(value)
    return f"{number:,.0f} 台/周" if number is not None else "—"


__all__ = [
    "answer_competitor_profile_question",
    "build_competitor_profile_presentation",
    "build_sellpoint_consumption_proof",
    "render_evidence_report",
    "render_feishu_card",
    "render_pm_report",
    "render_short_answer",
]
