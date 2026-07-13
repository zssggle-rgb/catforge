"""PM report adapter and renderers that only consume a stored profile bundle."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Sequence

from pydantic import Field

from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    _write_markdown_report,
)
from app.services.core3_real_data.analyst.competitor_answer import _publish_report
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueProfileReadBundle,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)


INTERNAL_LANGUAGE_REPLACEMENTS = {
    "反事实": "对照比较",
    "合成对照": "市场基线比较",
    "合成控制": "市场基线比较",
    "门禁": "可用条件",
    "门槛功能": "基础竞争能力",
    "门槛": "普及判断",
    "counterfactual": "comparison",
    "synthetic control": "market baseline",
}

INVESTMENT_ACTION_CN = {
    "retain": "继续保留",
    "unconverted": "先改善体验兑现",
    "do_not_follow": "当前不用跟",
    "table_stake": "保持基础竞争能力",
    "missing_competitive_gap": "优先评估补齐",
    "unknown": "暂不作产品取舍",
}


class StoredPmFirstScreen(SellpointValueProfileBaseModel):
    retain_cn: str = Field(min_length=1)
    unconverted_cn: str = Field(min_length=1)
    competitor_action_cn: str = Field(min_length=1)
    price_support_cn: str = Field(min_length=1)
    growth_action_cn: str = Field(min_length=1)


class StoredPmInvestmentRow(SellpointValueProfileBaseModel):
    capability_code: str = Field(min_length=1)
    capability_name_cn: str = Field(min_length=1)
    action_code: str = Field(min_length=1)
    action_cn: str = Field(min_length=1)
    business_reason_cn: str = Field(min_length=1)
    evidence_boundary_cn: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    review_required: bool


class StoredPmCandidateRow(SellpointValueProfileBaseModel):
    candidate_sku_code: str = Field(min_length=1)
    candidate_name_cn: str = Field(min_length=1)
    pool_type: str = Field(min_length=1)
    relation_cn: str = Field(min_length=1)
    usability_cn: str = Field(min_length=1)
    price: float | None = None
    weekly_sales: float | None = None
    selected_for: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class StoredPmValueAccountRow(SellpointValueProfileBaseModel):
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    value_bundle_code: str = Field(min_length=1)
    value_bundle_name_cn: str = Field(min_length=1)
    perceived_outcome_cn: str = Field(min_length=1)
    value_status_cn: str = Field(min_length=1)
    investment_actions_cn: list[str] = Field(default_factory=list)
    representative_comparisons_cn: list[str] = Field(default_factory=list)
    price_performance_cn: str = Field(min_length=1)
    volume_performance_cn: str = Field(min_length=1)
    evidence_boundary_cn: str = Field(min_length=1)


class StoredSellpointValuePmReport(SellpointValueProfileBaseModel):
    schema_version: str = "sku_sellpoint_value_pm_report_v1"
    target: dict[str, Any]
    analysis_state: str = Field(min_length=1)
    freshness_status: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    release_status: str = Field(min_length=1)
    generated_at: datetime
    published_at: datetime | None = None
    candidate_manifest_hash: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    first_screen: StoredPmFirstScreen
    value_accounts: list[StoredPmValueAccountRow]
    investment_decisions: list[StoredPmInvestmentRow]
    full_candidates: list[StoredPmCandidateRow]
    candidate_count: int = Field(ge=0)
    reference_count: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)


def build_stored_profile_pm_report(
    bundle: SellpointValueProfileReadBundle,
) -> StoredSellpointValuePmReport:
    profile = bundle.profile
    pm = profile.pm_decisions_json or {}
    investments = [_investment_row(row) for row in profile.investment_decisions_json]
    candidates = [_candidate_row(row) for row in bundle.candidates]
    candidate_names = {
        row.candidate_sku_code: row.candidate_name_cn for row in candidates
    }
    values = [
        _value_row(row, candidate_names, investments) for row in bundle.value_items
    ]
    retain = _names(pm.get("investments_to_retain"))
    table_stakes = _names(pm.get("table_stakes_to_maintain"))
    unconverted = _names(pm.get("investments_not_converted"))
    no_follow = _names(pm.get("configurations_not_to_follow"))
    gaps = _names(pm.get("missing_competitive_gaps"))
    retain_parts = []
    if retain:
        retain_parts.append(f"继续保留并优先兑现：{'、'.join(retain)}。")
    if table_stakes:
        retain_parts.append(
            f"作为基础竞争能力保持，但不承担溢价任务：{'、'.join(table_stakes)}。"
        )
    first_screen = StoredPmFirstScreen(
        retain_cn=_sanitize(
            "".join(retain_parts)
            or "现有画像尚未确认需要继续加码的差异化投入。"
        ),
        unconverted_cn=_sanitize(
            f"先改善体验兑现，不继续堆参数：{'、'.join(unconverted)}。"
            if unconverted
            else "现有画像没有确认投入已做但用户价值尚未形成的项目。"
        ),
        competitor_action_cn=_sanitize(
            " ".join(
                item
                for item in (
                    f"当前不用为了参数对齐而跟进：{'、'.join(no_follow)}。"
                    if no_follow
                    else "",
                    f"需要优先评估补齐：{'、'.join(gaps)}。" if gaps else "",
                )
                if item
            )
            or "现有画像没有确认可直接放弃跟进或必须补齐的竞品配置。"
        ),
        price_support_cn=_sanitize(
            str(pm.get("current_price_support_cn") or "当前价格支撑尚不明确。")
        ),
        growth_action_cn=_sanitize(
            str(pm.get("growth_action_cn") or "当前销量动作尚不明确。")
        ),
    )
    return StoredSellpointValuePmReport(
        target={
            "sku_code": profile.sku_code,
            "brand_name": profile.brand_name,
            "model_name": profile.model_name,
            "product_category": profile.product_category,
        },
        analysis_state=profile.analysis_state,
        freshness_status=profile.freshness_status,
        profile_version=profile.profile_version,
        release_status=profile.release_status,
        generated_at=bundle.version.generated_at,
        published_at=bundle.version.published_at,
        candidate_manifest_hash=str(
            profile.candidate_universe_summary_json.get("candidate_manifest_hash")
            or bundle.version.candidate_universe_fingerprint
        ),
        profile_result_hash=profile.result_hash,
        first_screen=first_screen,
        value_accounts=values,
        investment_decisions=investments,
        full_candidates=candidates,
        candidate_count=sum(row.pool_type == "competitor" for row in candidates),
        reference_count=sum(row.pool_type == "reference" for row in candidates),
        limitations=_profile_limitations(profile),
    )


def build_stored_profile_answer_artifacts(
    report: StoredSellpointValuePmReport,
    *,
    with_report: str = "none",
    max_chat_chars: int = 900,
    report_title: str | None = None,
    selection_compare_url: str | None = None,
    evidence_report_url: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(report.target)} 用户卖点价值分析"
    links = _links(selection_compare_url, evidence_report_url)
    markdown = render_stored_profile_markdown(report, title=title, links=links)
    markdown_path = (
        _write_markdown_report(title, markdown)
        if with_report in {"markdown", "feishu-doc"}
        else None
    )
    delivery = _publish_report(title=title, markdown=markdown, with_report=with_report)
    final_links = _links(selection_compare_url, evidence_report_url or delivery.url)
    return {
        "report_ref": {
            "schema_version": report.schema_version,
            "profile_version": report.profile_version,
            "release_status": report.release_status,
            "generated_at": report.generated_at.isoformat(),
            "published_at": (
                report.published_at.isoformat() if report.published_at else None
            ),
            "candidate_manifest_hash": report.candidate_manifest_hash,
            "result_hash": report.profile_result_hash,
        },
        "short_answer": render_stored_profile_short_answer(
            report,
            links=final_links,
            max_chat_chars=max_chat_chars,
        ),
        "markdown": markdown if with_report == "markdown" else None,
        "markdown_path": markdown_path,
        "feishu_card_payload": render_stored_profile_feishu_card(
            report,
            title=title,
            links=final_links,
        ),
        "report_links": final_links,
        "report_delivery": delivery.to_dict(),
        "report_title": title,
        "profile_version": report.profile_version,
        "release_status": report.release_status,
        "result_hash": report.profile_result_hash,
    }


def render_stored_profile_short_answer(
    report: StoredSellpointValuePmReport,
    *,
    links: Sequence[dict[str, str]] = (),
    max_chat_chars: int = 900,
) -> str:
    screen = report.first_screen
    business_lines = [
        f"{_display_name(report.target)} 用户卖点价值结论",
        f"保留什么｜{screen.retain_cn}",
        f"哪里没转化｜{screen.unconverted_cn}",
        f"竞品配置怎么处理｜{screen.competitor_action_cn}",
        f"当前价格是否撑得住｜{screen.price_support_cn}",
        f"如果要销量｜{screen.growth_action_cn}",
    ]
    trace_lines = [
        (
            f"画像版本｜{report.profile_version}（{report.release_status}，"
            f"{report.freshness_status}）｜{_release_time_cn(report)}"
        ),
        (
            f"候选范围编号｜{report.candidate_manifest_hash}｜"
            f"结果编号 {report.profile_result_hash}"
        ),
    ]
    suffix = "\n".join(
        f"{item['label']}：{item['url']}"
        for item in links
        if item.get("url", "").startswith("http")
    )
    mandatory = "\n".join(trace_lines + ([suffix] if suffix else []))
    body_limit = max(1, max_chat_chars - len(mandatory) - 1)
    body = _compress("\n".join(business_lines), body_limit)
    return _sanitize(f"{body}\n{mandatory}")


def render_stored_profile_markdown(
    report: StoredSellpointValuePmReport,
    *,
    title: str,
    links: Sequence[dict[str, str]] = (),
) -> str:
    screen = report.first_screen
    lines = [
        f"# {title}",
        "",
        (
            f"> 画像版本：{report.profile_version}｜状态：{report.release_status}｜"
            f"新鲜度：{report.freshness_status}｜{_release_time_cn(report)}"
        ),
        (
            f"> 候选范围编号：{report.candidate_manifest_hash}｜"
            f"结果编号：{report.profile_result_hash}"
        ),
        "",
        "## 一、产品经理先看这五个答案",
        "",
        f"1. **哪些投入值得保留**：{screen.retain_cn}",
        f"2. **哪些投入没有转化成用户价值**：{screen.unconverted_cn}",
        f"3. **哪些竞品配置不用跟、哪些缺口要补**：{screen.competitor_action_cn}",
        f"4. **当前价格是否得到用户价值支撑**：{screen.price_support_cn}",
        f"5. **如果追求销量，产品动作是什么**：{screen.growth_action_cn}",
        "",
        "## 二、用户价值账",
        "",
    ]
    if report.value_accounts:
        for index, row in enumerate(report.value_accounts, start=1):
            lines.extend(
                [
                    f"### {index}. {row.battlefield_name_cn}｜{row.value_bundle_name_cn}",
                    "",
                    f"- 用户实际获得：{row.perceived_outcome_cn}",
                    f"- 当前价值状态：{row.value_status_cn}",
                    (
                        "- 产品投入处理："
                        + ("；".join(row.investment_actions_cn) or "暂未形成明确取舍。")
                    ),
                    (
                        "- 代表产品比较："
                        + ("；".join(row.representative_comparisons_cn) or "当前没有可展示的代表产品。")
                    ),
                    f"- 价格表现：{row.price_performance_cn}",
                    f"- 销量表现：{row.volume_performance_cn}",
                    f"- 证据边界：{row.evidence_boundary_cn}",
                    "",
                ]
            )
    else:
        lines.extend(["当前画像没有形成可展示的用户价值账。", ""])
    lines.extend(["## 三、产品投入清单", ""])
    if report.investment_decisions:
        lines.extend(
            [
                "| 产品投入 | 建议动作 | 工作含义 | 可信度 |",
                "| --- | --- | --- | ---: |",
                *(
                    f"| {row.capability_name_cn} | {row.action_cn} | "
                    f"{row.business_reason_cn} | {row.confidence:.0%} |"
                    for row in report.investment_decisions
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## 四、分析使用的产品范围",
            "",
            f"正式竞品 {report.candidate_count} 款，其他分析参照 {report.reference_count} 款。",
            "",
        ]
    )
    if report.full_candidates:
        lines.extend(
            [
                "| 产品 | 用途 | 可用于什么 | 均价 | 周均销量 |",
                "| --- | --- | --- | ---: | ---: |",
                *(
                    f"| {row.candidate_name_cn} | {row.relation_cn} | {row.usability_cn} | "
                    f"{_number_or_dash(row.price)} | {_number_or_dash(row.weekly_sales)} |"
                    for row in report.full_candidates
                ),
                "",
            ]
        )
    if report.limitations:
        lines.extend(
            [
                "## 五、当前不能下的结论",
                "",
                *(f"- {item}" for item in report.limitations),
                "",
            ]
        )
    if links:
        lines.extend(
            [
                "## 相关链接",
                "",
                *(
                    f"- [{item['label']}]({item['url']})"
                    for item in links
                    if item.get("url", "").startswith("http")
                ),
            ]
        )
    return _sanitize("\n".join(lines).strip())


def render_stored_profile_feishu_card(
    report: StoredSellpointValuePmReport,
    *,
    title: str,
    links: Sequence[dict[str, str]] = (),
) -> dict[str, Any]:
    screen = report.first_screen
    content = "\n".join(
        (
            f"**保留什么**：{screen.retain_cn}",
            f"**哪里没转化**：{screen.unconverted_cn}",
            f"**竞品配置怎么处理**：{screen.competitor_action_cn}",
            f"**价格是否撑得住**：{screen.price_support_cn}",
            f"**如果要销量**：{screen.growth_action_cn}",
            (
                f"画像版本：{report.profile_version}｜{report.release_status}｜"
                f"{report.freshness_status}｜{_release_time_cn(report)}"
            ),
            (
                f"候选范围编号：{report.candidate_manifest_hash}｜"
                f"结果编号：{report.profile_result_hash}"
            ),
        )
    )
    elements: list[dict[str, Any]] = [
        {"tag": "markdown", "content": _sanitize(content)}
    ]
    actions = [
        {
            "tag": "button",
            "text": {"tag": "plain_text", "content": item["label"]},
            "type": "default",
            "url": item["url"],
        }
        for item in links
        if item.get("url", "").startswith("http")
    ]
    if actions:
        elements.append({"tag": "action", "actions": actions})
    return {
        "schema": "2.0",
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": "blue",
        },
        "body": {"elements": elements},
        "profile_version": report.profile_version,
        "release_status": report.release_status,
        "generated_at": report.generated_at.isoformat(),
        "published_at": (
            report.published_at.isoformat() if report.published_at else None
        ),
        "candidate_manifest_hash": report.candidate_manifest_hash,
        "result_hash": report.profile_result_hash,
    }


def _investment_row(row: dict[str, Any]) -> StoredPmInvestmentRow:
    action_code = str(row.get("classification") or "unknown")
    return StoredPmInvestmentRow(
        capability_code=str(row.get("capability_code") or "unknown"),
        capability_name_cn=str(
            row.get("capability_name_cn") or row.get("capability_code") or "未命名投入"
        ),
        action_code=action_code,
        action_cn=INVESTMENT_ACTION_CN.get(action_code, "暂不作产品取舍"),
        business_reason_cn=_sanitize(
            str(row.get("business_reason_cn") or "现有证据不足以形成产品动作。")
        ),
        evidence_boundary_cn=_sanitize(
            str(row.get("boundary_cn") or "请结合画像证据范围使用。")
        ),
        confidence=float(row.get("confidence") or 0.0),
        review_required=str(row.get("review_status")) == "review_required",
    )


def _candidate_row(row: Any) -> StoredPmCandidateRow:
    market = row.market_summary_json or {}
    pool_type = str(row.pool_type)
    return StoredPmCandidateRow(
        candidate_sku_code=row.candidate_sku_code,
        candidate_name_cn=(
            f"{row.candidate_brand_name or ''} "
            f"{row.candidate_model_name or row.candidate_sku_code}"
        ).strip(),
        pool_type=pool_type,
        relation_cn=(
            "竞争产品"
            if pool_type == "competitor"
            else "市场与产品设计参照"
        ),
        usability_cn=_candidate_usability(row),
        price=_number(
            market.get("price_wavg")
            or market.get("avg_price")
            or market.get("current_price")
        ),
        weekly_sales=_number(
            market.get("avg_weekly_sales_volume")
            or market.get("weekly_sales")
        ),
        selected_for=[_sanitize(str(item)) for item in row.selected_questions_json],
        limitations=[_sanitize(str(item)) for item in row.limitations_json],
    )


def _candidate_usability(row: Any) -> str:
    if row.pool_type == "reference":
        return "用于判断市场价格、销量或产品组合，不用于回答用户为什么在两款产品中作选择。"
    return {
        "eligible": "可用于当前价格、用户价值和具体竞品比较。",
        "limited": "只用于已有数据能够支持的比较。",
        "review_required": "证据需要复核，本报告不据此下正式结论。",
        "blocked": "当前不参与正式结论。",
        "recalled_only": "仅保留在候选清单，当前不参与正式结论。",
    }.get(str(row.eligibility_status), "当前用途尚不明确。")


def _value_row(
    row: Any,
    candidate_names: dict[str, str],
    investments: Sequence[StoredPmInvestmentRow],
) -> StoredPmValueAccountRow:
    action_by_code = {item.capability_code: item for item in investments}
    investment_actions = [
        f"{action_by_code[code].capability_name_cn}：{action_by_code[code].action_cn}"
        for code in row.capability_codes_json
        if code in action_by_code
    ]
    comparisons = []
    for question in row.question_result_refs_json:
        codes = question.get("eligible_candidate_sku_codes") or []
        names = [candidate_names.get(str(code), str(code)) for code in codes]
        if names:
            comparisons.append(
                f"用{'、'.join(names[:5])}判断{_question_cn(question.get('question'))}"
            )
    return StoredPmValueAccountRow(
        battlefield_code=row.battlefield_code,
        battlefield_name_cn=row.battlefield_name_cn or row.battlefield_code,
        value_bundle_code=row.value_bundle_code,
        value_bundle_name_cn=row.value_bundle_name_cn,
        perceived_outcome_cn=_sanitize(row.perceived_outcome_cn),
        value_status_cn=_value_status_cn(row.perceived_value_status),
        investment_actions_cn=investment_actions,
        representative_comparisons_cn=comparisons,
        price_performance_cn=_price_performance_cn(row.price_realization_json),
        volume_performance_cn=_volume_performance_cn(row.volume_realization_json),
        evidence_boundary_cn=_sanitize(row.evidence_boundary_cn),
    )


def _price_performance_cn(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    current_price = _number(payload.get("current_price"))
    if status == "available":
        if current_price is not None:
            return f"当前均价约 {current_price:,.0f} 元；具体承接程度见本价值项的市场比较。"
        return "已有可用的价格表现比较。"
    if status == "degraded":
        return "现有市场数据只能提供方向性价格判断。"
    if status in {"blocked", "unidentifiable"}:
        return "现有数据不能确认这项用户价值支撑了多少价格。"
    return "当前没有可用的价格表现结论。"


def _volume_performance_cn(payload: dict[str, Any]) -> str:
    status = str(payload.get("status") or "unknown")
    position = payload.get("raw_market_position") or {}
    weekly = _number(
        position.get("avg_weekly_sales_volume") or position.get("weekly_sales")
    )
    if status == "available":
        return (
            f"当前周均销量约 {weekly:,.1f} 台。"
            if weekly is not None
            else "已有可用的销量表现比较。"
        )
    if status == "degraded":
        return "现有市场数据只能提供方向性销量判断。"
    if status in {"blocked", "unidentifiable"}:
        return "现有数据不能把销量表现单独归到这一项用户价值。"
    return "当前没有可用的销量表现结论。"


def _value_status_cn(status: str) -> str:
    return {
        "observed_positive": "用户已稳定感知到具体好处",
        "observed_mixed": "不同用户或场景的感知有正有负",
        "observed_negative": "用户实际体验以负向结果为主",
        "partial": "用户只感知到部分好处",
        "not_observed": "现有反馈尚未观察到这项好处",
        "conflicted": "不同来源结论冲突，需要复核",
        "unknown": "现有证据不足",
    }.get(status, "现有证据不足")


def _question_cn(value: Any) -> str:
    return {
        "user_realization": "用户实际感知",
        "relative_highlight": "相对用户价值优势",
        "without_value_baseline": "没有这组价值时的市场表现",
        "price_realization": "当前价格支撑",
        "volume_realization": "当前销量表现",
        "strict_bundle_price_interval": "价格承接范围",
        "battlefield_portfolio": "产品价值方向",
    }.get(str(value), "当前产品问题")


def _links(
    selection_compare_url: str | None,
    evidence_report_url: str | None,
) -> list[dict[str, str]]:
    result = []
    if selection_compare_url:
        result.append({"label": "查看用户选择对比", "url": selection_compare_url})
    if evidence_report_url:
        result.append({"label": "查看完整画像", "url": evidence_report_url})
    return result


def _names(value: Any) -> list[str]:
    return sorted({str(item) for item in (value or []) if str(item).strip()})


def _profile_limitations(profile: Any) -> list[str]:
    limitations = [_sanitize(str(item)) for item in profile.limitations_json]
    if profile.freshness_status == "stale":
        limitations.append("上游画像已发生变化，本结果可用于回看，不能作为当前产品决策依据。")
    if profile.analysis_state == "blocked":
        limitations.append("关键证据不足或冲突，本画像只能预览，不能形成正式产品取舍。")
    return list(dict.fromkeys(limitations))


def _sanitize(value: str) -> str:
    result = value
    for internal, business in INTERNAL_LANGUAGE_REPLACEMENTS.items():
        result = result.replace(internal, business)
    return result


def _display_name(target: dict[str, Any]) -> str:
    return (
        f"{target.get('brand_name') or ''} "
        f"{target.get('model_name') or target.get('sku_code') or '本品'}"
    ).strip()


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _number_or_dash(value: float | None) -> str:
    return f"{value:,.1f}" if value is not None else "—"


def _datetime_cn(value: datetime) -> str:
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def _release_time_cn(report: StoredSellpointValuePmReport) -> str:
    generated = f"生成时间：{_datetime_cn(report.generated_at)}"
    if report.published_at is None:
        return generated
    return f"{generated}｜发布时间：{_datetime_cn(report.published_at)}"


def _compress(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(limit - 1, 0)].rstrip() + "…"


__all__ = [
    "INTERNAL_LANGUAGE_REPLACEMENTS",
    "StoredPmCandidateRow",
    "StoredPmFirstScreen",
    "StoredPmInvestmentRow",
    "StoredPmValueAccountRow",
    "StoredSellpointValuePmReport",
    "build_stored_profile_answer_artifacts",
    "build_stored_profile_pm_report",
    "render_stored_profile_feishu_card",
    "render_stored_profile_markdown",
    "render_stored_profile_short_answer",
]
