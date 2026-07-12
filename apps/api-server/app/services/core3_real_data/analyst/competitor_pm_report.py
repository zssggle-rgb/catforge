"""Product-manager-facing comparison report rendering.

The caller supplies business-safe, Chinese product views assembled from
published profiles. This module only compares and renders those views; it does
not score competitors or infer product actions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable


UNKNOWN_VALUES = {
    "",
    "未知",
    "暂不能判断",
    "暂无稳定证据",
    "未形成稳定证据",
    "未形成稳定购买理由",
}

INTERNAL_OUTPUT_PATTERN = re.compile(
    r"\b(?:BF_[A-Z0-9_]+|TASK_[A-Z0-9_]+|TG_[A-Z0-9_]+|M\d{2}[A-Z]?|core3_[a-z0-9_]+|risk_flags|gate_reasons|missing_reason_code)\b"
)


@dataclass(frozen=True)
class PmComparisonRow:
    label_cn: str
    values_cn: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"label_cn": self.label_cn, "values_cn": list(self.values_cn)}


@dataclass(frozen=True)
class PmComparisonSection:
    title_cn: str
    rows: tuple[PmComparisonRow, ...]
    common_ground_cn: str | None = None
    key_difference_cn: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title_cn": self.title_cn,
            "rows": [row.to_dict() for row in self.rows],
            "common_ground_cn": self.common_ground_cn,
            "key_difference_cn": self.key_difference_cn,
        }


def build_pm_comparison_payload(
    *,
    title: str,
    product_views: list[dict[str, Any]],
    substitution_rows: list[dict[str, str]],
    evidence_report_url: str | None,
) -> dict[str, Any]:
    """Build the external PM-report contract from normalized product views."""

    names = tuple(str(product.get("name") or "产品") for product in product_views[:4])
    products = product_views[:4]
    sections = [
        _overview_section(products),
        _market_section(products),
        _matrix_section(
            title_cn="二、四款产品真正强在哪里",
            products=products,
            source_key="capabilities",
            summary=_capability_summary(products),
        ),
        _semantic_section(
            title_cn="三、用户购买这类产品时主要比较什么",
            products=products,
            source_key="choice_criteria",
            primary_label="主要比较内容",
            supporting_label="其他比较内容",
            common_prefix="四款产品共同进入用户对",
        ),
        _semantic_section(
            title_cn="四、用户买回去主要解决什么问题",
            products=products,
            source_key="usage_needs",
            primary_label="主要使用需求",
            supporting_label="其他使用需求",
            common_prefix="四款产品共同承接",
        ),
        _semantic_section(
            title_cn="五、哪些用户需求更容易被各款产品吸引",
            products=products,
            source_key="demand_audiences",
            primary_label="主要吸引的需求型用户",
            supporting_label="其他可覆盖用户",
            common_prefix="四款产品共同覆盖",
        ),
        _message_section(products),
        _purchase_reason_section(products),
        _substitution_section(names, substitution_rows),
        _matrix_section(
            title_cn="九、四款产品的用户价值是否传达完整",
            products=products,
            source_key="value_delivery",
            summary=_value_delivery_summary(products),
        ),
    ]
    subject_cn = "四款产品" if len(products) == 4 else "本品与重点竞品"
    visible_sections = [
        _replace_subject(section, subject_cn)
        for section in sections
        if section is not None
    ]
    return {
        "schema_version": "competitor_pm_comparison_v1",
        "title": title,
        "product_names": list(names),
        "sections": [section.to_dict() for section in visible_sections],
        "evidence_report_link": (
            {
                "label": "查看分析依据",
                "url": evidence_report_url,
                "type": "evidence_report",
            }
            if evidence_report_url
            else None
        ),
        "display_policy": {
            "compare_four_products_together": True,
            "omit_unsupported_sections": True,
            "include_actions": False,
            "include_sales_causality": False,
        },
    }


def render_pm_comparison_report(*, title: str, payload: dict[str, Any]) -> str:
    """Render a deterministic Markdown report from the PM contract."""

    product_names = [str(value) for value in payload.get("product_names") or []]
    lines = [f"# {title}", ""]
    for section in payload.get("sections") or []:
        if not isinstance(section, dict):
            continue
        rows = [row for row in section.get("rows") or [] if isinstance(row, dict)]
        if not rows:
            continue
        lines.extend([f"## {section.get('title_cn')}", ""])
        lines.extend(_render_matrix(product_names, rows))
        common = str(section.get("common_ground_cn") or "").strip()
        difference = str(section.get("key_difference_cn") or "").strip()
        if common:
            lines.extend(["", f"共同点：{common}"])
        if difference:
            lines.extend(["", f"差异：{difference}"])
        lines.append("")
    link = payload.get("evidence_report_link") or {}
    url = str(link.get("url") or "") if isinstance(link, dict) else ""
    if url.startswith("http"):
        lines.extend(["---", "", f"[查看竞品识别、评分和证据依据]({url})", ""])
    return "\n".join(lines).strip() + "\n"


def pm_business_output_issue(text: str) -> str | None:
    """Return a safe validation error when internal identifiers would leak."""

    return (
        "用户选择对比报告包含未解析的内部字段。"
        if INTERNAL_OUTPUT_PATTERN.search(text)
        else None
    )


def _overview_section(products: list[dict[str, Any]]) -> PmComparisonSection | None:
    rows = _rows_from_source(
        products,
        source_key="overview",
        row_order=(
            "价格和周均销量",
            "产品事实最突出的部分",
            "主要承接的用户选择",
            "用户主要使用需求",
            "用户已经形成的购买理由",
            "卖点接收情况",
        ),
        minimum_assessable=2,
    )
    if not rows:
        return None
    return PmComparisonSection(title_cn="四款产品总览", rows=tuple(rows))


def _market_section(products: list[dict[str, Any]]) -> PmComparisonSection | None:
    rows = _rows_from_source(
        products,
        source_key="market",
        row_order=("市场池口径", "均价", "周均销量", "池内销量表现"),
        minimum_assessable=2,
    )
    if not rows:
        return None
    prices = _numeric_product_values(products, "price")
    sales = _numeric_product_values(products, "weekly_sales")
    difference_parts: list[str] = []
    if len(prices) >= 2:
        highest = max(prices, key=lambda item: item[1])
        lowest = min(prices, key=lambda item: item[1])
        difference_parts.append(f"{highest[0]}价格最高，{lowest[0]}价格最低")
    if len(sales) >= 2:
        highest = max(sales, key=lambda item: item[1])
        lowest = min(sales, key=lambda item: item[1])
        difference_parts.append(f"{highest[0]}周均销量最高，{lowest[0]}周均销量最低")
    scopes = [
        str((product.get("market") or {}).get("_pool_scope_key") or "")
        for product in products
    ]
    common = (
        "四款产品处在同一市场池，可以直接比较价格、周均销量和池内位置。"
        if _same_nonempty(scopes)
        else None
    )
    return PmComparisonSection(
        title_cn="一、四款产品分别卖多少钱、卖得怎么样",
        rows=tuple(rows),
        common_ground_cn=common,
        key_difference_cn="；".join(difference_parts) + "。"
        if difference_parts
        else None,
    )


def _matrix_section(
    *,
    title_cn: str,
    products: list[dict[str, Any]],
    source_key: str,
    summary: tuple[str | None, str | None] = (None, None),
) -> PmComparisonSection | None:
    row_order = _ordered_labels(products, source_key)
    rows = _rows_from_source(
        products, source_key=source_key, row_order=row_order, minimum_assessable=2
    )
    if not rows:
        return None
    return PmComparisonSection(
        title_cn=title_cn,
        rows=tuple(rows),
        common_ground_cn=summary[0],
        key_difference_cn=summary[1],
    )


def _semantic_section(
    *,
    title_cn: str,
    products: list[dict[str, Any]],
    source_key: str,
    primary_label: str,
    supporting_label: str,
    common_prefix: str,
) -> PmComparisonSection | None:
    rows = _rows_from_source(
        products,
        source_key=source_key,
        row_order=(primary_label, supporting_label, "补充表现"),
        minimum_assessable=2,
    )
    if not rows:
        return None
    common_tags = _common_tags(products, source_key)
    unique_parts = _unique_tag_parts(products, source_key)
    common = f"{common_prefix}{'、'.join(common_tags[:4])}。" if common_tags else None
    difference = "；".join(unique_parts[:4]) + "。" if unique_parts else None
    return PmComparisonSection(
        title_cn=title_cn,
        rows=tuple(rows),
        common_ground_cn=common,
        key_difference_cn=difference,
    )


def _message_section(products: list[dict[str, Any]]) -> PmComparisonSection | None:
    rows = _rows_from_source(
        products,
        source_key="message_reception",
        row_order=("产品重点表达", "用户正向感知", "用户反向反馈", "尚需确认的表达"),
        minimum_assessable=2,
    )
    if not rows:
        return None
    common_tags = _common_tags(products, "message_reception", tag_key="fact_tags")
    divided = [
        str(product.get("name") or "产品")
        for product in products
        if (product.get("message_reception") or {}).get("contradicted_tags")
    ]
    common = (
        f"四款产品都重点表达了{'、'.join(common_tags[:4])}。" if common_tags else None
    )
    difference = (
        f"{'、'.join(divided)}存在稳定的用户反向反馈，其余产品当前未识别到同类稳定分歧。"
        if divided
        else None
    )
    return PmComparisonSection(
        title_cn="六、产品重点讲什么，用户实际理解了什么",
        rows=tuple(rows),
        common_ground_cn=common,
        key_difference_cn=difference,
    )


def _purchase_reason_section(
    products: list[dict[str, Any]],
) -> PmComparisonSection | None:
    rows = _rows_from_source(
        products,
        source_key="purchase_reasons",
        row_order=(
            "核心购买理由",
            "辅助购买理由",
            "产品希望传达但尚未观察到用户承接",
            "购买阻力",
        ),
        minimum_assessable=2,
    )
    if not rows:
        return None
    common_tags = _common_tags(products, "purchase_reasons", tag_key="core_tags")
    unique_parts = _unique_tag_parts(products, "purchase_reasons", tag_key="core_tags")
    common = (
        f"四款产品共同形成了{'、'.join(common_tags[:4])}等购买理由。"
        if common_tags
        else None
    )
    difference = "；".join(unique_parts[:4]) + "。" if unique_parts else None
    return PmComparisonSection(
        title_cn="七、用户为什么会选择四款产品",
        rows=tuple(rows),
        common_ground_cn=common,
        key_difference_cn=difference,
    )


def _substitution_section(
    product_names: tuple[str, ...],
    substitution_rows: list[dict[str, str]],
) -> PmComparisonSection | None:
    if not substitution_rows or len(product_names) < 2:
        return None
    labels = (
        "与本品重合的选择理由",
        "竞品更突出的理由",
        "本品保留的理由",
        "替代程度",
        "双方各自的购买阻力",
    )
    by_name = {str(row.get("name") or ""): row for row in substitution_rows}
    rows: list[PmComparisonRow] = []
    for label in labels:
        values = ["本品基准"]
        assessable = 0
        for name in product_names[1:]:
            value = str((by_name.get(name) or {}).get(label) or "暂不能判断")
            values.append(value)
            if _is_assessable(value):
                assessable += 1
        if assessable:
            rows.append(PmComparisonRow(label_cn=label, values_cn=tuple(values)))
    if not rows:
        return None
    return PmComparisonSection(
        title_cn="八、用户在四款产品之间会怎样取舍", rows=tuple(rows)
    )


def _rows_from_source(
    products: list[dict[str, Any]],
    *,
    source_key: str,
    row_order: Iterable[str],
    minimum_assessable: int,
) -> list[PmComparisonRow]:
    rows: list[PmComparisonRow] = []
    for label in row_order:
        values = tuple(
            str((product.get(source_key) or {}).get(label) or "暂不能判断")
            for product in products
        )
        if sum(_is_assessable(value) for value in values) < minimum_assessable:
            continue
        rows.append(PmComparisonRow(label_cn=label, values_cn=values))
    return rows


def _ordered_labels(products: list[dict[str, Any]], source_key: str) -> tuple[str, ...]:
    labels: list[str] = []
    for product in products:
        source = product.get(source_key) or {}
        for label in source:
            if not str(label).startswith("_") and label not in labels:
                labels.append(str(label))
    return tuple(labels)


def _capability_summary(
    products: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    labels = _ordered_labels(products, "capabilities")
    differing: list[str] = []
    common: list[str] = []
    for label in labels:
        values = [
            str((product.get("capabilities") or {}).get(label) or "")
            for product in products
        ]
        assessable = [value for value in values if _is_assessable(value)]
        if len(assessable) < 2:
            continue
        if len(set(assessable)) == 1 and len(assessable) == len(products):
            common.append(label)
        else:
            differing.append(label)
    common_cn = f"四款产品在{'、'.join(common[:4])}上表现接近。" if common else None
    difference_cn = (
        f"实际能力差异主要集中在{'、'.join(differing[:5])}。" if differing else None
    )
    return common_cn, difference_cn


def _value_delivery_summary(
    products: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    complete = [
        str(product.get("name") or "产品")
        for product in products
        if _is_assessable(
            str((product.get("value_delivery") or {}).get("已形成稳定购买理由") or "")
        )
    ]
    divided = [
        str(product.get("name") or "产品")
        for product in products
        if _is_assessable(
            str(
                (product.get("value_delivery") or {}).get("已成立理由上的购买阻力")
                or ""
            )
        )
    ]
    common = (
        f"{'、'.join(complete)}已有产品事实、用户感知和购买理由共同支撑的价值主题。"
        if complete
        else None
    )
    difference = (
        f"{'、'.join(divided)}在已成立购买理由上仍存在用户顾虑。" if divided else None
    )
    return common, difference


def _numeric_product_values(
    products: list[dict[str, Any]], key: str
) -> list[tuple[str, Decimal]]:
    values: list[tuple[str, Decimal]] = []
    for product in products:
        value = _decimal((product.get("market") or {}).get(f"_{key}"))
        if value is not None:
            values.append((str(product.get("name") or "产品"), value))
    return values


def _common_tags(
    products: list[dict[str, Any]], source_key: str, *, tag_key: str = "_all_tags"
) -> list[str]:
    tag_sets = [
        set(
            str(value)
            for value in (product.get(source_key) or {}).get(tag_key) or []
            if value
        )
        for product in products
    ]
    if not tag_sets or any(not values for values in tag_sets):
        return []
    return sorted(set.intersection(*tag_sets))


def _unique_tag_parts(
    products: list[dict[str, Any]], source_key: str, *, tag_key: str = "_all_tags"
) -> list[str]:
    tag_sets = [
        set(
            str(value)
            for value in (product.get(source_key) or {}).get(tag_key) or []
            if value
        )
        for product in products
    ]
    parts: list[str] = []
    for index, product in enumerate(products):
        own = tag_sets[index]
        others = (
            set().union(*(tag_sets[:index] + tag_sets[index + 1 :]))
            if len(tag_sets) > 1
            else set()
        )
        unique = sorted(own - others)
        if unique:
            parts.append(
                f"{product.get('name') or '产品'}更突出{'、'.join(unique[:3])}"
            )
    return parts


def _render_matrix(product_names: list[str], rows: list[dict[str, Any]]) -> list[str]:
    names = [_markdown_cell(name) for name in product_names]
    lines = [
        "| 比较内容 | " + " | ".join(names) + " |",
        "| --- | " + " | ".join("---" for _name in names) + " |",
    ]
    for row in rows:
        label = _markdown_cell(row.get("label_cn"))
        values = [_markdown_cell(value) for value in row.get("values_cn") or []]
        lines.append("| " + " | ".join([label, *values]) + " |")
    return lines


def _replace_subject(
    section: PmComparisonSection, subject_cn: str
) -> PmComparisonSection:
    def replace(value: str | None) -> str | None:
        if not value or subject_cn == "四款产品":
            return value
        return value.replace("四款产品", subject_cn).replace("四款", subject_cn)

    return PmComparisonSection(
        title_cn=replace(section.title_cn) or section.title_cn,
        rows=section.rows,
        common_ground_cn=replace(section.common_ground_cn),
        key_difference_cn=replace(section.key_difference_cn),
    )


def _is_assessable(value: str) -> bool:
    normalized = str(value or "").strip()
    return (
        bool(normalized)
        and normalized not in UNKNOWN_VALUES
        and not normalized.startswith("暂不能判断")
    )


def _same_nonempty(values: list[str]) -> bool:
    normalized = [value.strip() for value in values if _is_assessable(value)]
    return (
        bool(normalized)
        and len(normalized) == len(values)
        and len(set(normalized)) == 1
    )


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _markdown_cell(value: Any) -> str:
    return str(value or "暂不能判断").replace("\n", "<br>").replace("|", "｜").strip()
