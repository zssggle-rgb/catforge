"""Product-manager-facing answer, report, and Feishu card for sellpoint V2."""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.core3_real_data.analyst.competitor_answer import _publish_report


def build_claim_value_pm_answer(
    *,
    target: dict[str, Any],
    analysis: dict[str, Any],
    with_report: str = "none",
    max_chat_chars: int = 600,
    report_title: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(target)} 卖点经营盘：哪些该做强，哪些别再单独讲"
    dashboard_without_link = build_claim_value_pm_dashboard_payload(
        target=target,
        analysis=analysis,
        report_url=None,
        title=title,
    )
    markdown = render_claim_value_pm_report(title=title, dashboard=dashboard_without_link)
    markdown_path = _write_markdown_report(title, markdown) if with_report in {"markdown", "feishu-doc"} else None
    publish_result = _publish_report(title=title, markdown=markdown, with_report=with_report)
    dashboard = build_claim_value_pm_dashboard_payload(
        target=target,
        analysis=analysis,
        report_url=publish_result.url,
        title=title,
    )
    card = render_claim_value_pm_feishu_card_payload(dashboard)
    short_answer = render_claim_value_pm_short_answer(
        dashboard,
        report_url=publish_result.url,
        report_message=publish_result.message_cn,
        max_chat_chars=max_chat_chars,
    )
    report = publish_result.to_dict()
    report["markdown_path"] = markdown_path
    return {
        "short_answer": short_answer,
        "dashboard_payload": dashboard,
        "feishu_card_payload": card,
        "report": report,
        "markdown": markdown if with_report == "markdown" else None,
        "report_title": title,
    }


def build_claim_value_pm_dashboard_payload(
    *,
    target: dict[str, Any],
    analysis: dict[str, Any],
    report_url: str | None,
    title: str | None = None,
) -> dict[str, Any]:
    payload = dict(analysis)
    payload.update(
        {
            "dashboard_schema_version": "sellpoint_value_pm_dashboard_v1",
            "title": title or f"{_display_name(target)} 卖点经营盘",
            "target": target,
            "report_evidence_links": ([{"label": "查看完整报告", "url": report_url, "type": "report"}] if report_url else []),
            "display_policy": {
                "main_answer": "feishu_card",
                "report_as_evidence": True,
                "fallback_to_short_answer": True,
                "hide_internal_fields": True,
            },
        }
    )
    return payload


def render_claim_value_pm_short_answer(
    dashboard: dict[str, Any],
    *,
    report_url: str | None = None,
    report_message: str | None = None,
    max_chat_chars: int = 600,
) -> str:
    gate = dashboard.get("data_gate") or {}
    market = dashboard.get("market_pricing") or {}
    actions = [item for item in dashboard.get("decision_summary") or [] if isinstance(item, dict)]
    lines = [
        f"{_display_name(dashboard.get('target') or {})} 卖点称重结论：{gate.get('status_cn') or '待核验'}。",
        str(dashboard.get("headline_cn") or "当前没有可执行结论。"),
    ]
    if market.get("same_price_choice_share") is not None:
        share = float(market["same_price_choice_share"]) * 100
        advantage = float(market.get("same_price_choice_advantage_pp") or 0)
        lines.append(f"整机同价条件销量份额约 {share:.1f}%，相对五五开为 {advantage:+.1f} 个百分点；该结果没有拆给单个卖点。")
    lines.append(
        f"当前价格承接：{market.get('current_price_acceptance_status_cn') or '无法判断'}。"
        f"{market.get('current_price_acceptance_basis_cn') or ''}"
    )
    lines.append(str(market.get("holding_gap_status_cn") or "样本不足，暂不计算选择保持价差。"))
    for item in actions[:3]:
        lines.append(f"{item.get('priority')}. {item.get('action_cn')}")
    report_line = f"完整报告：{report_url}" if report_url else ""
    if not report_line and report_message and report_message not in {"未请求生成外部报告。", "未请求生成 Markdown 文件。"}:
        lines.append(report_message)
    body_limit = max_chat_chars - len(report_line) - 1 if report_line else max_chat_chars
    body = _compress("\n".join(lines), max(1, body_limit))
    return f"{body}\n{report_line}" if report_line else body


def render_claim_value_pm_report(*, title: str, dashboard: dict[str, Any]) -> str:
    gate = dashboard.get("data_gate") or {}
    units = [item for item in dashboard.get("value_units") or [] if isinstance(item, dict)]
    actions = [item for item in dashboard.get("decision_summary") or [] if isinstance(item, dict)]
    market = dashboard.get("market_pricing") or {}
    issues = [item for item in gate.get("issues") or [] if isinstance(item, dict)]
    lines: list[str] = [
        f"# {title}",
        "",
        f"> 数据状态：**{_md(gate.get('status_cn') or '待核验')}**。{_md(dashboard.get('headline_cn') or '')}",
        "",
        "## 一、本周先做这几件事",
        "",
    ]
    if actions:
        for item in actions:
            lines.extend(
                [
                    f"### {item.get('priority')}. {_md(item.get('action_type'))}",
                    "",
                    f"- **动作**：{_md(item.get('action_cn'))}",
                    f"- **为什么**：{_md(item.get('why_cn'))}",
                    f"- **做到什么算有效**：{_md(item.get('success_signal_cn'))}",
                    "",
                ]
            )
    else:
        lines.extend(["当前先补齐关键证据，不做配置或价格动作。", ""])
    lines.extend(
        [
            "## 二、卖点称重总表",
            "",
            "| 用户价值组合 | 产品事实 | 用户怎么看 | 有效体验句 | 对选购的作用 | 价格测试准备度 | 产品动作 |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
    )
    for unit in units:
        understanding = unit.get("user_understanding") or {}
        weights = unit.get("weights") or {}
        purchase_role = unit.get("purchase_role") or {}
        attributed_count = int(understanding.get("direct_sentence_count") or 0) + int(understanding.get("indirect_sentence_count") or 0)
        eligible_count = int(understanding.get("eligible_sentence_count") or 0)
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(unit.get("unit_name_cn")),
                    _md(unit.get("product_fact_status_cn")),
                    _md(understanding.get("status_cn")),
                    f"{attributed_count}/{eligible_count}" if eligible_count else "—",
                    _md(purchase_role.get("status_cn")),
                    _md(weights.get("pricing_readiness_cn")),
                    _md(unit.get("decision_cn")),
                ]
            )
            + " |"
        )
    lines.extend(["", "产品事实、用户体验、选购作用和整机价格承接是四个分开的判断；购后好评不能替代选购证据，整机结果也不会被分摊成单项金额。", ""])
    lines.extend(_market_pricing_lines(market))
    lines.extend(["## 四、逐项看用户、竞品和动作", ""])
    for index, unit in enumerate(units, start=1):
        understanding = unit.get("user_understanding") or {}
        lines.extend(
            [
                f"### {index}. {_md(unit.get('unit_name_cn'))}",
                "",
                f"- **产品做到了什么**：{_md(unit.get('product_claim_cn'))}（{_md(unit.get('product_fact_status_cn'))}）",
                f"- **用户实际怎么看**：{_md(understanding.get('status_cn'))}；直接 {int(understanding.get('direct_sentence_count') or 0)} 条，体验结果 {int(understanding.get('indirect_sentence_count') or 0)} 条，泛化不可归因 {int(understanding.get('unattributable_sentence_count') or 0)} 条，反向 {int(understanding.get('negative_sentence_count') or 0)} 条。",
                f"- **对选购的作用**：{_md((unit.get('purchase_role') or {}).get('status_cn'))}。{_md((unit.get('purchase_role') or {}).get('basis_cn'))}",
                f"- **产品动作**：{_md(unit.get('decision_cn'))}",
                f"- **下一步验证**：{_md(unit.get('next_validation_cn'))}",
                "",
            ]
        )
        examples = [item for item in understanding.get("positive_examples") or [] if isinstance(item, dict)]
        negative = [item for item in understanding.get("negative_examples") or [] if isinstance(item, dict)]
        if examples or negative:
            lines.extend(["**用户原话**", ""])
            for item in examples:
                label = "直接" if item.get("attribution") == "direct" else "体验结果"
                lines.append(f"- [{label}] “{_md(item.get('text'))}”")
            for item in negative:
                lines.append(f"- [反向] “{_md(item.get('text'))}”")
            lines.append("")
        comparisons = [item for item in unit.get("competitor_comparison") or [] if isinstance(item, dict)]
        if comparisons:
            lines.extend(
                [
                    "**既有竞品校准**",
                    "",
                    "| 竞品 | 既有角色 | 本品/竞品事实关系 | 竞品用户反馈 | 市场位置 | 能否单独比较 |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for item in comparisons[:1]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            _md(item.get("display_name")),
                            _md(item.get("selection_role_cn") or "既有竞品"),
                            _relation_cn(item.get("fact_relation")),
                            _md(item.get("competitor_user_status_cn")),
                            _md(item.get("market_position_cn")),
                            _isolation_cn(item.get("isolation_grade")),
                        ]
                    )
                    + " |"
                )
            lines.append("")
        for limitation in unit.get("limitations") or []:
            lines.append(f"- 边界：{_md(limitation)}")
        if unit.get("limitations"):
            lines.append("")
    lines.extend(["## 五、数据问题与不能下的结论", ""])
    if issues:
        for item in issues:
            prefix = "阻断" if item.get("severity") == "blocking" else "提醒"
            lines.append(f"- **{prefix}**：{_md(item.get('message_cn'))}")
    for item in dashboard.get("limitations") or []:
        lines.append(f"- {_md(item)}")
    lines.extend(["", "## 六、下一步验证清单", ""])
    for item in dashboard.get("test_backlog") or []:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                f"{item.get('priority')}. **{_md(item.get('action_cn'))}**",
                f"   - 原因：{_md(item.get('why_cn'))}",
                f"   - 成功标准：{_md(item.get('success_signal_cn'))}",
            ]
        )
    audit = dashboard.get("audit") or {}
    purchase_reason = audit.get("purchase_reason_hypothesis") or {}
    boundary = dashboard.get("competitor_boundary") or {}
    lines.extend(
        [
            "",
            "## 七、口径与证据",
            "",
            f"- 目标 SKU：`{_md(audit.get('target_sku_code'))}`",
            f"- 批次：`{_md(audit.get('batch_id'))}`",
            f"- 市场样本口径：{_md(market.get('method_name_cn') or '当前无可用市场量化结果')}。",
            f"- 成交理由画像：{'已读取' if purchase_reason.get('found') else '本轮未找到可用发布版'}；只作为待验证假设，不参与独立证据计数。",
            f"- 竞品来源：{_competitor_source_cn(boundary.get('source'))}，共 {int(boundary.get('competitor_count') or 0)} 款。",
            f"- 详细竞品策略入口：{_md(boundary.get('detail_entry') or '原竞品智能体')}。",
            f"- 竞品边界：{_md(boundary.get('policy_cn'))}",
            f"- 生成时间：`{_md(audit.get('generated_at'))}`",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _market_pricing_lines(market: dict[str, Any]) -> list[str]:
    lines = [
        "## 三、当前价格承接与价格情景",
        "",
        f"- **样本口径**：{_md(market.get('method_name_cn'))}",
        f"- **口径**：{_md(market.get('attribution_status_cn'))}",
    ]
    if market.get("current_price") is not None:
        lines.append(f"- **当前观察价**：约 {float(market['current_price']):.0f} 元")
    lines.append(f"- **当前价格承接状态**：{_md(market.get('current_price_acceptance_status_cn') or '无法判断')}。{_md(market.get('current_price_acceptance_basis_cn'))}")
    if market.get("same_price_choice_share") is not None:
        share = float(market["same_price_choice_share"]) * 100
        advantage = float(market.get("same_price_choice_advantage_pp") or 0)
        interval = market.get("same_price_competitor_interval_pp") or []
        interval_cn = f"；竞品间区间 {float(interval[0]):+.1f} 至 {float(interval[-1]):+.1f} 个百分点" if len(interval) >= 2 else ""
        lines.append(f"- **同价销量承接**：两款条件销量份额约 {share:.1f}%，相对五五开 {advantage:+.1f} 个百分点{interval_cn}。")
    lines.append(f"- **选择保持价差**：{_md(market.get('holding_gap_status_cn'))}")
    lines.extend(["", "### 价格情景", "", "| 情景 | 价格 | 条件销量份额 | 销量承接指数 | 对比销额指数 | 样本状态 |", "| --- | ---: | ---: | ---: | ---: | --- |"])
    scenarios = [item for item in market.get("price_scenarios") or [] if isinstance(item, dict)]
    if scenarios:
        for item in scenarios:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(item.get("label_cn")),
                        f"{float(item['price']):.0f}元" if item.get("price") is not None else "—",
                        f"{float(item['comparison_choice_share']) * 100:.1f}%" if item.get("comparison_choice_share") is not None else "—",
                        f"{float(item['choice_index']):.1f}" if item.get("choice_index") is not None else "—",
                        f"{float(item['comparison_revenue_index']):.1f}" if item.get("comparison_revenue_index") is not None else "—",
                        _md(item.get("status_cn")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| 当前样本 | — | — | — | — | 暂无可用情景 |")
    lines.extend(["", "价格情景固定竞品参考价和对照规模，只用于观察方向，不是销量承诺或建议售价。", ""])
    return lines


def render_claim_value_pm_feishu_card_payload(dashboard: dict[str, Any]) -> dict[str, Any]:
    gate = dashboard.get("data_gate") or {}
    market = dashboard.get("market_pricing") or {}
    actions = [item for item in dashboard.get("decision_summary") or [] if isinstance(item, dict)]
    units = [item for item in dashboard.get("value_units") or [] if isinstance(item, dict)]
    body: list[dict[str, Any]] = [
        {"tag": "markdown", "content": f"**数据状态：{gate.get('status_cn') or '待核验'}**\n{dashboard.get('headline_cn') or ''}"},
        {"tag": "hr"},
        {"tag": "markdown", "content": _card_unit_summary(units)},
        {"tag": "hr"},
        {"tag": "markdown", "content": _card_market_summary(market, gate=gate)},
    ]
    if actions:
        body.extend(
            [
                {"tag": "hr"},
                {"tag": "markdown", "content": "**本轮动作**\n" + "\n".join(f"{item.get('priority')}. {item.get('action_cn')}" for item in actions[:3])},
            ]
        )
    links = dashboard.get("report_evidence_links") or []
    if links:
        url = str((links[0] or {}).get("url") or "")
        if url.startswith("http"):
            body.append(
                {
                    "tag": "button",
                    "element_id": "view_sellpoint_value_report",
                    "type": "primary",
                    "size": "medium",
                    "width": "fill",
                    "text": {"tag": "plain_text", "content": "查看完整报告"},
                    "behaviors": [{"type": "open_url", "default_url": url, "pc_url": url, "ios_url": url, "android_url": url}],
                }
            )
    card = {
        "schema": "2.0",
        "config": {"summary": {"content": str(dashboard.get("title") or "卖点经营盘")}, "width_mode": "fill", "update_multi": True},
        "header": {"template": "orange" if gate.get("status") != "ready" else "turquoise", "title": {"tag": "plain_text", "content": str(dashboard.get("title") or "卖点经营盘")}},
        "body": {"elements": body},
    }
    if len(json.dumps(card, ensure_ascii=False).encode("utf-8")) > 30_000:
        card["body"]["elements"] = body[:5]
    return card


def _card_unit_summary(units: list[dict[str, Any]]) -> str:
    conflicts = [item.get("unit_name_cn") for item in units if item.get("product_fact_status") == "conflict"]
    usable = [item for item in units if item.get("product_fact_status") != "conflict"]
    fix_first = [item.get("unit_name_cn") for item in usable if (item.get("user_understanding") or {}).get("status") in {"negative", "mixed"}]
    stable = [item for item in usable if (item.get("user_understanding") or {}).get("status") not in {"negative", "mixed"}]
    outcomes = [item.get("unit_name_cn") for item in stable if (item.get("user_understanding") or {}).get("status") == "outcome_only" or (item.get("purchase_role") or {}).get("status") == "direct_reason"]
    technical_only = [item.get("unit_name_cn") for item in stable if (item.get("user_understanding") or {}).get("status") == "direct" and (item.get("purchase_role") or {}).get("status") != "direct_reason"]
    unreceived = [item.get("unit_name_cn") for item in stable if (item.get("user_understanding") or {}).get("status") in {"unrecognized", "insufficient"}]
    do_not_price = [item.get("unit_name_cn") for item in stable if item.get("product_fact_status") == "confirmed" and (item.get("weights") or {}).get("pricing_readiness") in {"not_ready", "insufficient"}]
    lines = ["**卖点称重**"]
    lines.append(f"- 说出具体体验结果：{_unit_names_cn(outcomes, empty='本批未观察到')}")
    lines.append(f"- 只说到技术/参数：{_unit_names_cn(technical_only)}")
    lines.append(f"- 有配置但未形成具体结果：{_unit_names_cn(unreceived)}")
    lines.append(f"- 不单独讲或加价：{_unit_names_cn(do_not_price)}")
    if fix_first:
        lines.append(f"- 优先修产品：{_unit_names_cn(fix_first)}")
    if conflicts:
        lines.append(f"- 暂停判断：{_unit_names_cn(conflicts)}")
    return "\n".join(lines)


def _card_market_summary(market: dict[str, Any], *, gate: dict[str, Any] | None = None) -> str:
    lines = ["**整机价格承接**"]
    if market.get("same_price_choice_share") is not None:
        lines.append(f"- 整机同价条件销量份额：{float(market['same_price_choice_share']) * 100:.1f}%")
    lines.append(f"- 当前价格：{market.get('current_price_acceptance_status_cn') or '无法判断'}")
    product_fact_blocked = any(
        isinstance(item, dict)
        and item.get("severity") == "blocking"
        and item.get("scope") == "product_fact"
        for item in (gate or {}).get("issues") or []
    )
    if product_fact_blocked:
        lines.append("- 价格测试准备：先修产品事实，本轮不下发涨价动作")
    else:
        lines.append(f"- 价格测试准备：{'达到历史样本门槛，仍需小流量验证' if market.get('method_level') == 'L3' else '当前样本不足，不给涨价动作'}")
    lines.append("- 数值只代表整机方案，不拆给单个技术点。")
    return "\n".join(lines)


def _write_markdown_report(title: str, markdown: str) -> str:
    root = Path(tempfile.gettempdir()) / "catforge_analyst_reports"
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", title).strip("-")[:80] or "sellpoint-value-report"
    path = root / f"{timestamp}-{slug}.md"
    path.write_text(markdown, encoding="utf-8")
    return str(path)


def _display_name(target: dict[str, Any]) -> str:
    return " ".join(str(target.get(key) or "").strip() for key in ("brand_name", "model_name") if target.get(key)) or str(target.get("sku_code") or "目标产品")


def _compress(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)].rstrip() + "…"


def _md(value: Any) -> str:
    return str(value or "—").replace("|", "\\|").replace("\n", " ")


def _pct(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.1f}%"


def _relation_cn(value: Any) -> str:
    return {
        "target_stronger": "本品配置更强",
        "competitor_stronger": "竞品配置更强",
        "different": "配置不同，不能只归因一项",
        "similar": "配置接近",
        "unknown": "事实不足",
    }.get(str(value), "事实不足")


def _isolation_cn(value: Any) -> str:
    return {
        "A": "可单独比较",
        "B": "需连同一项配置一起看",
        "C": "差异过多，不能归到本项",
        "unknown": "事实不足",
    }.get(str(value), "事实不足")


def _competitor_source_cn(value: Any) -> str:
    return {
        "M14": "既有竞品智能体已确认的竞品",
        "competitor_set_fallback": "既有竞品智能体的降级结果",
        "none": "本轮没有可用竞品",
    }.get(str(value), "既有竞品结果")


def _unit_names_cn(values: list[Any], *, empty: str = "无", limit: int = 3) -> str:
    names = [str(item) for item in values if item]
    if not names:
        return empty
    visible = "、".join(names[:limit])
    return f"{visible}等{len(names)}项" if len(names) > limit else visible
