"""Business-facing low-sales diagnosis answer generation."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.services.core3_real_data.analyst.competitor_answer import _publish_report


ReportMode = Literal["none", "markdown", "feishu-doc"]


@dataclass(frozen=True)
class LowSalesReportFile:
    status: str
    path: str | None = None
    message_cn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "path": self.path, "message_cn": self.message_cn}


def build_low_sales_answer(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    with_report: ReportMode = "none",
    max_chat_chars: int = 800,
    report_title: str | None = None,
) -> dict[str, Any]:
    title = report_title or f"{_display_name(target)} 单品低销量诊断报告"
    markdown = render_low_sales_report(title=title, target=target, payload=payload)
    report_file = _write_markdown_report(title=title, markdown=markdown) if with_report in {"markdown", "feishu-doc"} else LowSalesReportFile(status="disabled", message_cn="未请求生成 Markdown 文件。")
    publish_result = _publish_report(title=title, markdown=markdown, with_report=with_report)
    report_location = _business_report_location(with_report=with_report, publish_result=publish_result, report_file=report_file)
    short_answer = render_low_sales_short_answer(
        target=target,
        payload=payload,
        report_location=report_location,
        max_chat_chars=max_chat_chars,
    )
    report = publish_result.to_dict()
    report["markdown_path"] = report_file.path
    if report_file.message_cn:
        report["markdown_message_cn"] = report_file.message_cn
    return {
        "short_answer": short_answer,
        "report": report,
        "markdown": markdown if with_report == "markdown" else None,
        "report_title": title,
    }


def render_low_sales_short_answer(
    *,
    target: dict[str, Any],
    payload: dict[str, Any],
    report_location: str | None = None,
    max_chat_chars: int = 800,
) -> str:
    name = _display_name(target)
    sales_status = payload.get("sales_status") or {}
    reasons = [row for row in payload.get("reason_ranking") or [] if isinstance(row, dict)]
    actions = payload.get("action_plan") or {}
    status_text = _sales_status_sentence(name, sales_status)
    reason_text = _reason_sentence(reasons)
    action_text = _action_sentence(actions)
    boundary = "当前不能判断广告、库存、促销和毛利原因，因为缺少对应数据。"
    core_lines = [status_text]
    if reason_text:
        core_lines.append(reason_text)
    if action_text:
        core_lines.append(action_text)
    suffix_lines = [boundary]
    if report_location:
        suffix_lines.append(f"详细报告：{report_location}")
    return _compress_with_suffix("\n".join(core_lines), "\n".join(suffix_lines), max_chat_chars=max_chat_chars)


def render_low_sales_report(*, title: str, target: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = [
        f"# {title}",
        "",
        "## 一、结论",
        "",
        render_low_sales_short_answer(target=target, payload=payload, max_chat_chars=2000),
        "",
        "## 二、是否真的卖得弱",
        "",
        *_sales_status_lines(payload.get("sales_status") or {}),
        "",
        "## 三、价值棒拆解",
        "",
        *_value_stick_lines(payload.get("value_stick_summary") or {}),
        "",
        "## 四、主要原因排序",
        "",
        *_reason_table_lines(payload.get("reason_ranking") or []),
        "",
        "## 五、重点竞品购买锚点差距",
        "",
        *_competitor_lines(payload.get("competitor_evidence") or []),
        "",
        "## 六、卖点支付价值、参数口径和价格压力",
        "",
        *_claim_value_lines(payload.get("claim_value_summary") or {}),
        "",
        "## 七、战场、任务、客群和评论缺口",
        "",
        *_gap_lines(payload),
        "",
        "## 八、同品牌产品线分流",
        "",
        *_product_line_lines(payload.get("product_line_cannibalization_summary") or {}),
        "",
        "## 九、动作建议",
        "",
        *_action_lines(payload.get("action_plan") or {}),
        "",
        "## 十、数据口径和限制",
        "",
        *_limit_lines(payload.get("not_supported_reasons") or []),
    ]
    return "\n".join(lines).strip() + "\n"


def _sales_status_sentence(name: str, sales_status: dict[str, Any]) -> str:
    status = str(sales_status.get("status") or "uncertain")
    basis = str(sales_status.get("basis_cn") or "").strip()
    if status == "weak":
        return f"{name} 在当前可比线上样本中属于相对偏弱。{basis}"
    if status == "not_weak":
        return f"{name} 在当前可比线上样本中不属于明显低销量 SKU。{basis}"
    if status == "mixed":
        return f"{name} 的销量表现是混合状态，对部分竞品偏弱、对部分竞品不弱。{basis}"
    return f"当前样本不足以判断 {name} 是否真的卖得弱。{basis}"


def _reason_sentence(reasons: list[dict[str, Any]]) -> str:
    if not reasons:
        return ""
    chunks = []
    for row in reasons[:3]:
        name = str(row.get("reason_name_cn") or "").strip()
        root_cause = str(row.get("root_cause_cn") or row.get("summary_cn") or "").strip("。")
        observation = _first_observation_point(row).strip("。")
        decision = str(row.get("decision_implication_cn") or "").strip("。")
        parts = []
        if root_cause:
            parts.append(root_cause)
        if observation:
            parts.append(f"证据：{observation}")
        if decision:
            parts.append(f"决策含义：{decision}")
        if name and parts:
            chunks.append(f"{name}：{'；'.join(parts)}")
        elif parts:
            chunks.append("；".join(parts))
    chunks = [chunk for chunk in chunks if chunk]
    return f"主要诊断优先看：{'；'.join(chunks)}。" if chunks else ""


def _action_sentence(actions: dict[str, Any]) -> str:
    short = [row for row in actions.get("short_term_actions") or [] if isinstance(row, dict)]
    mid = [row for row in actions.get("mid_term_actions") or [] if isinstance(row, dict)]
    parts: list[str] = []
    if short:
        parts.append("建议先做：" + "；".join(str(row.get("summary_cn") or "").strip("。") for row in short[:2] if row.get("summary_cn")))
    if mid:
        parts.append("中期关注：" + "；".join(str(row.get("summary_cn") or "").strip("。") for row in mid[:1] if row.get("summary_cn")))
    return "。".join(part for part in parts if part) + ("。" if parts else "")


def _sales_status_lines(sales_status: dict[str, Any]) -> list[str]:
    rows = sales_status.get("comparison_rows") or []
    lines = [
        f"- 状态：{sales_status.get('status') or 'uncertain'}",
        f"- 置信度：{sales_status.get('confidence') or 'unknown'}",
        f"- 判断依据：{sales_status.get('basis_cn') or '样本不足或缺少可比结果。'}",
        f"- 可用对比数：{sales_status.get('comparison_count', 0)}",
    ]
    if rows:
        lines.extend(["", "| 竞品 | 判断 | 销量比 | 销额比 | 说明 |", "| --- | --- | ---: | ---: | --- |"])
        for row in rows[:10]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("candidate_name") or row.get("candidate_sku_code") or ""),
                        _md(row.get("status") or ""),
                        _md(_fmt_ratio(row.get("sales_ratio"))),
                        _md(_fmt_ratio(row.get("amount_ratio"))),
                        _md(row.get("summary_cn") or ""),
                    ]
                )
                + " |"
            )
    return lines


def _value_stick_lines(summary: dict[str, Any]) -> list[str]:
    if not summary:
        return ["当前没有价值棒拆解结果。"]
    labels = {
        "customer_wtp": "用户愿付价值",
        "price_capture": "价格攫取",
        "competitor_alternative": "竞品替代",
        "product_line_cannibalization": "同品牌产品线分流",
        "evidence_risk": "证据风险",
        "enterprise_side": "企业侧",
    }
    return [f"- {labels.get(key, key)}：{(value or {}).get('summary_cn') or (value or {}).get('status') or '未知'}" for key, value in summary.items()]


def _reason_table_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["当前没有足够证据形成原因排序。"]
    lines = ["| 排名 | 诊断原因 | 事实证据 | 真正原因 | 价值棒机制 | 决策含义 | 验证动作 |", "| ---: | --- | --- | --- | --- | --- | --- |"]
    for row in rows[:8]:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("rank") or ""),
                    _md(row.get("reason_name_cn") or row.get("reason_type") or ""),
                    _md(_first_observation_point(row)),
                    _md(row.get("root_cause_cn") or row.get("summary_cn") or ""),
                    _md(row.get("value_stick_mechanism_cn") or row.get("value_stick_effect_cn") or ""),
                    _md(row.get("decision_implication_cn") or ""),
                    _md(row.get("validation_cn") or ""),
                ]
            )
            + " |"
        )
        observation_points = [str(item) for item in row.get("observation_points") or row.get("detail_points") or [] if item]
        for detail in observation_points[1:4]:
            lines.append(f"|  |  | {_md(detail)} |  |  |  |  |")
    return lines


def _competitor_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["当前没有稳定重点竞品拦截证据。"]
    lines: list[str] = []
    for row in rows[:5]:
        parts = [
            str(row.get("sales_summary_cn") or "").strip(),
            str(row.get("specific_gap_summary_cn") or "").strip(),
            str(row.get("claim_gap_summary_cn") or "").strip(),
        ]
        lines.append(f"- {row.get('candidate_name') or row.get('candidate_sku_code') or '竞品'}：{''.join(part for part in parts if part)}")
    return lines


def _claim_value_lines(summary: dict[str, Any]) -> list[str]:
    if not summary:
        return ["当前没有卖点支付价值汇总。"]
    labels = {
        "premium_claims": "溢价相关市场观测",
        "share_conversion_claims": "销量/份额转化相关市场观测",
        "customer_value_claims": "客户价值相关市场观测",
        "threshold_claims": "基础门槛卖点",
        "pending_claims": "待激活卖点",
        "brand_claims": "厂家主张卖点",
        "intercept_claims": "竞品拦截卖点",
        "price_pressure_claims": "价格压力卖点",
        "sample_insufficient_claims": "样本不足待复核",
    }
    lines: list[str] = []
    for key, label in labels.items():
        names = _claim_names(summary.get(key) or [])
        if names:
            lines.append(f"- {label}：{names}")
    return lines or ["当前没有显著卖点支付价值分类。"]


def _gap_lines(payload: dict[str, Any]) -> list[str]:
    battlefield = payload.get("battlefield_gap_summary") or {}
    signals = payload.get("gap_signal_summary") or {}
    lines: list[str] = []
    for key, label in (
        ("opportunity_battlefields", "机会战场"),
        ("drag_factor_battlefields", "拖后腿战场"),
        ("user_observed_battlefields", "用户观察战场"),
    ):
        names = _dimension_names(battlefield.get(key) or [])
        if names:
            lines.append(f"- {label}：{names}")
    for key, label in (
        ("price_gap_signals", "价格信号"),
        ("param_gap_signals", "参数信号"),
        ("claim_gap_signals", "卖点信号"),
        ("comment_gap_signals", "评论信号"),
        ("semantic_gap_signals", "语义信号"),
    ):
        messages = [str(row.get("message_cn") or "") for row in signals.get(key) or [] if isinstance(row, dict)]
        messages = [msg for msg in messages if msg]
        if messages:
            lines.append(f"- {label}：{'；'.join(messages[:3])}")
    return lines or ["当前没有显著战场、任务、客群或评论缺口。"]


def _product_line_lines(summary: dict[str, Any]) -> list[str]:
    if not summary:
        return ["当前没有同品牌产品线分流汇总。"]
    lines = [f"- 状态：{summary.get('status') or 'unknown'}", f"- 摘要：{summary.get('summary_cn') or '没有发现稳定同品牌分流信号。'}"]
    candidates = [row for row in summary.get("candidates") or [] if isinstance(row, dict)]
    if candidates:
        lines.extend(["", "| 同品牌候选 | 价差 | 周均销量 | 目标周均销量 | 说明 |", "| --- | ---: | ---: | ---: | --- |"])
        for row in candidates[:5]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(" ".join(str(part) for part in (row.get("brand_name"), row.get("model_name") or row.get("sku_code")) if part)),
                        _md(_fmt_yuan(row.get("price_gap_to_target"))),
                        _md(_fmt_number(row.get("avg_weekly_sales_volume"))),
                        _md(_fmt_number(row.get("target_avg_weekly_sales_volume"))),
                        _md(row.get("summary_cn") or ""),
                    ]
                )
                + " |"
            )
    return lines


def _action_lines(actions: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, title in (
        ("short_term_actions", "短期动作"),
        ("mid_term_actions", "中期动作"),
        ("high_cost_actions", "高成本动作"),
    ):
        items = [row for row in actions.get(key) or [] if isinstance(row, dict)]
        if not items:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for row in items[:5]:
            lines.append(f"- {row.get('summary_cn') or ''} 依据：{row.get('why_cn') or ''}")
        lines.append("")
    return lines or ["当前没有足够证据生成动作建议。"]


def _limit_lines(reasons: list[Any]) -> list[str]:
    lines = [f"- {item}" for item in reasons if item]
    return lines or ["- 缺少广告、库存、促销、毛利和线下渠道数据，不能判断这些因素。"]


def _first_observation_point(row: dict[str, Any]) -> str:
    points = [str(item).strip() for item in row.get("observation_points") or row.get("detail_points") or [] if str(item).strip()]
    return points[0] if points else ""


def _write_markdown_report(*, title: str, markdown: str) -> LowSalesReportFile:
    safe_title = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", title).strip("_") or "low_sales_diagnosis"
    path = Path(tempfile.gettempdir()) / f"{safe_title}.md"
    path.write_text(markdown, encoding="utf-8")
    return LowSalesReportFile(status="created", path=str(path), message_cn="已生成 Markdown 报告。")


def _business_report_location(*, with_report: str, publish_result: Any, report_file: LowSalesReportFile) -> str | None:
    if with_report == "feishu-doc" and getattr(publish_result, "url", None):
        return str(publish_result.url)
    if with_report in {"markdown", "feishu-doc"} and report_file.path:
        return report_file.path
    return None


def _display_name(target: dict[str, Any]) -> str:
    brand = str(target.get("brand_name") or "").strip()
    model = str(target.get("model_name") or target.get("sku_code") or "").strip()
    return " ".join(part for part in (brand, model) if part) or "目标 SKU"


def _claim_names(rows: list[Any]) -> str:
    names: list[str] = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row.get("claim_name") or row.get("claim_code") or "未命名卖点"))
        else:
            names.append(str(row))
    return "、".join(name for name in names if name)


def _dimension_names(rows: list[Any]) -> str:
    names = []
    for row in rows:
        if isinstance(row, dict):
            names.append(str(row.get("dimension_name") or row.get("dimension_code") or "未命名维度"))
    return "、".join(name for name in names if name)


def _fmt_ratio(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.2f}"


def _fmt_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.1f}".rstrip("0").rstrip(".")


def _fmt_yuan(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:.0f}元"


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _compress_text(text: str, *, max_chat_chars: int) -> str:
    if max_chat_chars <= 0 or len(text) <= max_chat_chars:
        return text
    return text[: max_chat_chars - 1].rstrip() + "…"


def _compress_with_suffix(core_text: str, suffix_text: str, *, max_chat_chars: int) -> str:
    if max_chat_chars <= 0:
        return "\n".join(part for part in (core_text, suffix_text) if part)
    if not suffix_text:
        return _compress_text(core_text, max_chat_chars=max_chat_chars)
    full_text = "\n".join(part for part in (core_text, suffix_text) if part)
    if len(full_text) <= max_chat_chars:
        return full_text
    available = max_chat_chars - len(suffix_text) - 1
    if available <= 1:
        return _compress_text(suffix_text, max_chat_chars=max_chat_chars)
    compressed_core = _compress_text(core_text, max_chat_chars=available)
    return "\n".join(part for part in (compressed_core, suffix_text) if part)
