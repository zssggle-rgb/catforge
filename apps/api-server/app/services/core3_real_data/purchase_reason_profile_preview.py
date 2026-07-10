"""Single-SKU business preview for M12D purchase reason profiles."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import (
    AnchorCandidateGenerator,
    M12DAnchorCandidateGenerationError,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    M12DAnchorTaxonomyLoader,
    M12DAnchorTaxonomyNotFoundError,
)
from app.services.core3_real_data.purchase_reason_context_builder import SkuPurchaseReasonContextBuilder
from app.services.core3_real_data.purchase_reason_profile_scoring import PurchaseReasonProfileScoringService
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DInputSnapshot,
    M12DScoredPurchaseReasonAnchor,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


class M12DSkuPurchaseReasonPreviewError(ValueError):
    """Raised when a single-SKU purchase reason preview cannot be built."""


ROLE_LABELS: dict[str, str] = {
    "core_payment": "核心成交理由",
    "supporting": "支撑理由",
    "weak_expression": "弱表达",
    "risk_drag": "风险拖拽",
}
EVIDENCE_STRENGTH_LABELS: dict[str, str] = {
    "strong": "强",
    "medium": "中",
    "weak": "弱",
    "insufficient": "不足",
}
EVIDENCE_DOMAIN_LABELS: dict[str, str] = {
    "param_fact": "参数事实",
    "fact_claim": "卖点事实",
    "comment_perception": "评论感知",
    "claim_value": "支付价值",
    "semantic_scene": "任务/客群/战场语义",
    "market_acceptance": "市场承接",
    "claim_position": "卖点位置",
    "service_signal": "服务信号",
    "risk_signal": "风险信号",
}
INPUT_SOURCE_LABELS: dict[str, str] = {
    "param_profile": "参数事实",
    "claim_fact_profile": "卖点事实",
    "comment_profile": "评论感知",
    "market_profile": "市场承接",
    "semantic_profile": "任务/客群/战场语义",
    "semantic_market_profile": "语义市场承接",
    "claim_value_profile": "支付价值",
}
INPUT_STATUS_LABELS: dict[str, str] = {
    "ready": "已就绪",
    "partial": "部分可用",
    "missing": "缺失",
    "conflict": "冲突",
    "unknown": "未知",
}
PROFILE_STATUS_LABELS: dict[str, str] = {
    "ready": "可用",
    "ready_degraded": "可用但降级",
    "weak_expression_only": "仅弱表达",
    "missing_input": "输入缺失",
    "review_required": "需复核",
    "failed": "失败",
}
CONFIDENCE_LEVEL_LABELS: dict[str, str] = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "unknown": "未知",
}


def build_sku_purchase_reason_preview(
    db: Session,
    *,
    project_id: str,
    category_code: str | Core3CategoryCode,
    batch_id: str,
    sku_code: str,
    product_category: str = "TV",
    taxonomy_version: str | None = None,
    max_anchors: int = 8,
) -> dict[str, Any]:
    """Build an auditable, business-readable preview for one SKU."""

    normalized_category = _normalize_category_code(category_code)
    normalized_product_category = product_category.strip().upper()
    if normalized_product_category not in {"TV", "AC"}:
        raise M12DSkuPurchaseReasonPreviewError(f"当前 M12D 单 SKU 预览不支持 {product_category} 品类。")
    if normalized_category.value != normalized_product_category:
        raise M12DSkuPurchaseReasonPreviewError(
            f"category_code={normalized_category.value} 与 product_category={normalized_product_category} 不一致。"
        )
    if not sku_code.strip():
        raise M12DSkuPurchaseReasonPreviewError("sku_code is required")

    repository_context = Core3RepositoryContext(
        db=db,
        project_id=project_id,
        category_code=normalized_category,
    )
    context = SkuPurchaseReasonContextBuilder(repository_context).build_context(
        batch_id=batch_id,
        sku_code=sku_code.strip(),
        product_category=normalized_product_category,
    )
    try:
        taxonomy = M12DAnchorTaxonomyLoader().load(
            taxonomy_version or _default_taxonomy_version(normalized_product_category),
            product_category=normalized_product_category,
        )
        candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)
    except (M12DAnchorTaxonomyNotFoundError, M12DAnchorCandidateGenerationError) as exc:
        raise M12DSkuPurchaseReasonPreviewError(str(exc)) from exc

    score_result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set,
        context=context,
    )
    anchors = [_anchor_preview(anchor) for anchor in score_result.scored_anchors[: max(1, max_anchors)]]
    value_themes = [
        _value_theme_preview(candidate)
        for candidate in candidate_set.value_theme_candidates[: max(1, max_anchors)]
    ]
    preview = {
        "sku": _sku_preview(context),
        "taxonomy_version": candidate_set.taxonomy_version,
        "product_category": normalized_product_category,
        "profile": {
            "status": _enum_value(score_result.status),
            "status_cn": PROFILE_STATUS_LABELS.get(_enum_value(score_result.status), _enum_value(score_result.status)),
            "profile_confidence": score_result.profile_confidence,
            "profile_confidence_pct": _format_pct(score_result.profile_confidence),
            "confidence_level": _enum_value(score_result.confidence_level),
            "confidence_level_cn": CONFIDENCE_LEVEL_LABELS.get(
                _enum_value(score_result.confidence_level),
                _enum_value(score_result.confidence_level),
            ),
            "review_required": score_result.review_required,
            "review_reasons": list(score_result.review_reason_json.get("reasons") or []),
            "core_payment_anchors": _anchors_by_codes(
                anchors,
                score_result.core_payment_anchors_json,
            ),
            "supporting_anchors": _anchors_by_codes(
                anchors,
                score_result.supporting_anchors_json,
            ),
            "weak_expression_anchors": _anchors_by_codes(
                anchors,
                score_result.weak_expression_anchors_json,
            ),
            "risk_drag_anchors": _anchors_by_codes(
                anchors,
                score_result.risk_drag_anchors_json,
            ),
        },
        "purchase_reason_anchors": anchors,
        "value_theme_candidates": value_themes,
        "input_status": _input_status_preview(context),
        "limitations": _preview_limitations(context, anchors),
    }
    preview["markdown_preview"] = format_sku_purchase_reason_markdown(preview)
    return preview


def format_sku_purchase_reason_markdown(preview: dict[str, Any]) -> str:
    """Render the preview as a concise Markdown report for business review."""

    sku = preview.get("sku") or {}
    profile = preview.get("profile") or {}
    target_name = sku.get("display_name_cn") or sku.get("sku_code") or "未知 SKU"
    lines = [
        f"# SKU 成交理由画像预览：{target_name}",
        "",
        f"- SKU：{sku.get('sku_code', '')}",
        f"- 品类：{sku.get('category_code', '')}",
        f"- 品牌/型号：{sku.get('brand_name') or '-'} / {sku.get('model_name') or '-'}",
        f"- 批次：{sku.get('batch_id', '')}",
        (
            f"- 画像状态：{profile.get('status_cn', profile.get('status', '-'))}"
            f"；置信度：{profile.get('profile_confidence_pct', '-')}"
            f"；置信等级：{profile.get('confidence_level_cn', '-')}"
        ),
    ]
    if profile.get("review_required"):
        reasons = "、".join(str(item) for item in profile.get("review_reasons") or [])
        lines.append(f"- 复核提示：需要复核{f'（{reasons}）' if reasons else ''}")

    lines.extend(["", "## 核心成交理由"])
    core_anchors = profile.get("core_payment_anchors") or []
    if not core_anchors:
        lines.append("当前证据未形成可直接作为成交理由的核心锚点。")
    else:
        lines.extend(_anchor_table(core_anchors))

    supporting = profile.get("supporting_anchors") or []
    weak = profile.get("weak_expression_anchors") or []
    risk = profile.get("risk_drag_anchors") or []
    lines.extend(["", "## 支撑、弱表达与风险"])
    if not supporting and not weak and not risk:
        lines.append("暂无额外支撑、弱表达或风险锚点。")
    else:
        if supporting:
            lines.append("### 支撑理由")
            lines.extend(_anchor_table(supporting))
        if weak:
            lines.append("### 弱表达")
            lines.extend(_anchor_table(weak))
        if risk:
            lines.append("### 风险拖拽")
            lines.extend(_anchor_table(risk))

    themes = preview.get("value_theme_candidates") or []
    lines.extend(["", "## 匹配到的价值主题"])
    if themes:
        for theme in themes:
            domains = "、".join(theme.get("evidence_domains_cn") or [])
            suffix = f"（证据：{domains}）" if domains else ""
            lines.append(f"- {theme.get('anchor_cn', theme.get('anchor_code'))}{suffix}")
    else:
        lines.append("暂无可匹配的价值主题。")

    lines.extend(["", "## 输入覆盖"])
    lines.append("| 输入层 | 状态 | 记录数 |")
    lines.append("| --- | --- | ---: |")
    for item in preview.get("input_status") or []:
        lines.append(f"| {item.get('source_cn')} | {item.get('status_cn')} | {item.get('record_count', 0)} |")

    limitations = preview.get("limitations") or []
    if limitations:
        lines.extend(["", "## 口径与限制"])
        for item in limitations:
            lines.append(f"- {item}")
    return "\n".join(lines).strip()


def _sku_preview(context: M12DSkuPurchaseReasonContext) -> dict[str, Any]:
    return {
        "sku_code": context.sku_code,
        "display_name_cn": context.display_name_cn,
        "brand_name": context.brand_name,
        "model_name": context.model_name,
        "batch_id": context.batch_id,
        "category_code": _enum_value(context.category_code),
        "product_category": context.product_category,
    }


def _anchor_preview(anchor: M12DScoredPurchaseReasonAnchor) -> dict[str, Any]:
    role = _enum_value(anchor.role)
    strength = _enum_value(anchor.evidence_strength)
    domains = [_enum_value(item) for item in anchor.evidence_domains_json]
    return {
        "anchor_code": anchor.anchor_code,
        "anchor_cn": anchor.anchor_cn,
        "anchor_family_code": anchor.anchor_family_code,
        "anchor_family_cn": anchor.anchor_family_cn,
        "role": role,
        "role_cn": ROLE_LABELS.get(role, role),
        "evidence_strength": strength,
        "evidence_strength_cn": EVIDENCE_STRENGTH_LABELS.get(strength, strength),
        "confidence": anchor.confidence,
        "confidence_pct": _format_pct(anchor.confidence),
        "evidence_domains": domains,
        "evidence_domains_cn": [EVIDENCE_DOMAIN_LABELS.get(domain, domain) for domain in domains],
        "support_summary_cn": anchor.support_summary_cn,
        "weakness_summary_cn": anchor.weakness_summary_cn,
        "risk_flags": list(anchor.risk_flags_json),
        "downgrade_reason_code": anchor.downgrade_reason_code,
    }


def _value_theme_preview(candidate: M12DAnchorCandidate) -> dict[str, Any]:
    domains = [_enum_value(item) for item in candidate.evidence_domains_json]
    return {
        "anchor_code": candidate.anchor_code,
        "anchor_cn": candidate.anchor_cn,
        "anchor_family_code": candidate.anchor_family_code,
        "anchor_family_cn": candidate.anchor_family_cn,
        "evidence_domains": domains,
        "evidence_domains_cn": [EVIDENCE_DOMAIN_LABELS.get(domain, domain) for domain in domains],
        "support_summary_cn": candidate.support_summary_cn,
    }


def _input_status_preview(context: M12DSkuPurchaseReasonContext) -> list[dict[str, Any]]:
    snapshots: tuple[tuple[str, M12DInputSnapshot], ...] = (
        ("param_profile", context.param_profile),
        ("claim_fact_profile", context.claim_fact_profile),
        ("comment_profile", context.comment_profile),
        ("market_profile", context.market_profile),
        ("semantic_profile", context.semantic_profile),
        ("semantic_market_profile", context.semantic_market_profile),
        ("claim_value_profile", context.claim_value_profile),
    )
    result: list[dict[str, Any]] = []
    for key, snapshot in snapshots:
        status = _enum_value(snapshot.status)
        result.append(
            {
                "source": key,
                "source_cn": INPUT_SOURCE_LABELS[key],
                "status": status,
                "status_cn": INPUT_STATUS_LABELS.get(status, status),
                "record_count": snapshot.record_count,
            }
        )
    return result


def _preview_limitations(context: M12DSkuPurchaseReasonContext, anchors: list[dict[str, Any]]) -> list[str]:
    limitations: list[str] = []
    missing_sources = [
        item["source_cn"]
        for item in _input_status_preview(context)
        if item["status"] in {"missing", "unknown", "conflict"}
    ]
    if missing_sources:
        limitations.append(f"以下输入层缺失或不可完全判断：{'、'.join(missing_sources)}。")
    if not any(anchor.get("role") == "core_payment" for anchor in anchors):
        limitations.append("当前没有形成核心成交理由，不能直接用于竞品匹配评分。")
    limitations.append("本预览只展示业务解释口径，评分和证据明细以 M12D 标准契约为准。")
    return limitations


def _anchor_table(anchors: Iterable[dict[str, Any]]) -> list[str]:
    lines = [
        "| 成交理由 | 证据强度 | 置信度 | 证据来源 | 支撑摘要 | 风险/弱点 |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for anchor in anchors:
        domains = "、".join(anchor.get("evidence_domains_cn") or []) or "-"
        weakness = anchor.get("weakness_summary_cn") or "无明显风险"
        if anchor.get("risk_flags"):
            weakness = f"{weakness}；风险标记：{'、'.join(str(item) for item in anchor['risk_flags'])}"
        lines.append(
            "| "
            f"{anchor.get('anchor_cn', anchor.get('anchor_code', '-'))} | "
            f"{anchor.get('evidence_strength_cn', '-')} | "
            f"{anchor.get('confidence_pct', '-')} | "
            f"{domains} | "
            f"{_escape_table_text(anchor.get('support_summary_cn') or '-')} | "
            f"{_escape_table_text(weakness)} |"
        )
    return lines


def _anchors_by_codes(anchors: list[dict[str, Any]], codes: Iterable[str]) -> list[dict[str, Any]]:
    anchor_by_code = {anchor["anchor_code"]: anchor for anchor in anchors}
    return [anchor_by_code[code] for code in codes if code in anchor_by_code]


def _normalize_category_code(category_code: str | Core3CategoryCode) -> Core3CategoryCode:
    try:
        return Core3CategoryCode(str(category_code).strip().upper())
    except ValueError as exc:
        raise M12DSkuPurchaseReasonPreviewError(f"不支持的品类代码：{category_code}") from exc


def _default_taxonomy_version(product_category: str) -> str:
    if product_category == "AC":
        return CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION
    return CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION


def _enum_value(value: Any) -> str:
    enum_value = getattr(value, "value", value)
    return str(enum_value)


def _format_pct(value: Any) -> str:
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return "-"
    return f"{(decimal_value * Decimal('100')).quantize(Decimal('1'))}%"


def _escape_table_text(value: str) -> str:
    return value.replace("|", "｜").replace("\n", " ")
