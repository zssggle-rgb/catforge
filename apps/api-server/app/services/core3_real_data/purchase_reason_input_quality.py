"""Module-aware M12D input quality adapters."""

from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import (
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
)
from app.services.core3_real_data.m12c_claim_value_quantification_service import (
    M12C_AMOUNT_LIMITATION_FLAGS,
    M12C_RELATIVE_COMPARISON_LIMITATION_FLAGS,
    assess_m12c_claim_value_quality,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorTaxonomy,
    M12DInputQuality,
    M12DInputQualityIssue,
)


MARKET_INFO_FLAGS = frozenset(
    {
        "observed_window_less_than_52w",
        "online_only_channel",
        "new_sku_short_history",
        "continuous_zero_sales_observed",
        "zero_sales_observed",
        "zero_sales_is_observed_fact",
        "short_history_is_lifecycle",
    }
)


class M12DInputQualityAdapter:
    """Translate module-specific facts into scoped M12D quality issues."""

    def __init__(self, taxonomy: M12DAnchorTaxonomy) -> None:
        self.taxonomy = taxonomy

    def param_profile(self, profile: Any | None) -> M12DInputQuality:
        if profile is None:
            return self._missing("M03B", "m03b_profile_missing", "M03B 参数事实画像缺失。")
        issues: list[M12DInputQualityIssue] = []
        conflict_count = int(getattr(profile, "conflict_count", 0) or 0)
        if conflict_count:
            tokens = _param_conflict_tokens(getattr(profile, "quality_summary_json", {}) or {})
            issues.append(
                self._issue(
                    module_code="M03B",
                    code="m03b_true_param_conflict",
                    severity=M12DIssueSeverity.BLOCKING,
                    scope=M12DIssueScope.ANCHOR,
                    message_cn="参数事实存在真实冲突，仅阻断引用冲突参数的购买理由。",
                    tokens=tokens,
                    rows=(profile,),
                    details={"conflict_count": conflict_count},
                )
            )
        review_count = int(getattr(profile, "review_required_count", 0) or 0)
        additional_review_count = max(0, review_count - conflict_count)
        if additional_review_count:
            issues.append(
                self._issue(
                    module_code="M03B",
                    code="m03b_param_review_required",
                    severity=M12DIssueSeverity.WARNING,
                    scope=M12DIssueScope.ANCHOR,
                    message_cn="部分参数需要复核，只影响引用这些参数的购买理由。",
                    tokens=_quality_tokens(getattr(profile, "quality_summary_json", {}) or {}),
                    rows=(profile,),
                    details={"review_required_count": additional_review_count},
                )
            )
        return self._present("M03B", issues, limited=bool(issues))

    def claim_profile(
        self,
        profile: Any | None,
        facts: Sequence[Any],
        *,
        param_profile_present: bool,
    ) -> M12DInputQuality:
        if profile is None:
            return self._missing("M04C", "m04c_profile_missing", "M04C 卖点事实画像缺失。")
        issues: list[M12DInputQualityIssue] = []
        flags = _row_flags(profile)
        for flag in sorted(flags):
            historical_dependency = flag == "m03b_param_profile_missing" and param_profile_present
            issues.append(
                self._issue(
                    module_code="M04C",
                    code=flag,
                    severity=M12DIssueSeverity.INFO,
                    scope=M12DIssueScope.ROW,
                    message_cn=(
                        "历史参数缺失标记仅保留为 lineage；当前 serving scope 已存在 M03B。"
                        if historical_dependency
                        else "卖点事实行的覆盖或输入说明，不降低其他卖点可用性。"
                    ),
                    tokens=_quality_tokens(getattr(profile, "claim_summary_json", {}) or {}),
                    rows=(profile,),
                )
            )
        if not facts and int(getattr(profile, "fact_claim_count", 0) or 0) > 0:
            issues.append(
                self._issue(
                    module_code="M04C",
                    code="m04c_fact_rows_unavailable_in_serving_scope",
                    severity=M12DIssueSeverity.INFO,
                    scope=M12DIssueScope.ROW,
                    message_cn="画像摘要声明存在事实卖点，本次明细展开未读取卖点行；摘要仍可使用。",
                    rows=(profile,),
                )
            )
        return self._present(
            "M04C",
            issues,
            limited=any(
                issue.severity in {M12DIssueSeverity.WARNING, M12DIssueSeverity.BLOCKING}
                for issue in issues
            ),
        )

    def comment_profile(self, profile: Any | None, facts: Sequence[Any]) -> M12DInputQuality:
        if profile is None:
            return self._missing("M05C", "m05c_profile_missing", "M05C 评论事实画像缺失。")
        issues: list[M12DInputQualityIssue] = []
        excluded_count = int(getattr(profile, "service_excluded_sentence_count", 0) or 0)
        if excluded_count:
            issues.append(
                self._issue(
                    module_code="M05C",
                    code="service_fulfillment_comment_excluded",
                    severity=M12DIssueSeverity.INFO,
                    scope=M12DIssueScope.ROW,
                    message_cn="服务履约评论已按规则排除，这是范围说明，不是数据异常。",
                    rows=(profile,),
                    details={"excluded_sentence_count": excluded_count},
                )
            )
        contradicted_claims = [
            str(code) for code in (getattr(profile, "contradicted_claim_codes", None) or ()) if str(code)
        ]
        if contradicted_claims:
            issues.append(
                self._issue(
                    module_code="M05C",
                    code="comment_claim_contradiction",
                    severity=M12DIssueSeverity.WARNING,
                    scope=M12DIssueScope.ANCHOR,
                    message_cn="评论与相关卖点事实存在矛盾，只影响引用这些卖点的购买理由。",
                    tokens=contradicted_claims,
                    rows=(profile, *facts),
                    details={"contradicted_claim_codes": contradicted_claims},
                )
            )
        return self._present(
            "M05C",
            issues,
            limited=bool(contradicted_claims),
        )

    def market_profile(self, profile: Any | None) -> M12DInputQuality:
        if profile is None:
            return self._missing("M07", "m07_profile_missing", "M07 市场画像缺失。")
        issues: list[M12DInputQualityIssue] = []
        sample_status = str(getattr(profile, "sample_status", "") or "").lower()
        if sample_status in {"unknown", "insufficient", "sample_insufficient"}:
            issues.append(
                self._issue(
                    module_code="M07",
                    code="market_sample_insufficient",
                    severity=M12DIssueSeverity.WARNING,
                    scope=M12DIssueScope.ANCHOR,
                    message_cn="市场样本不足，只限制引用市场承接的购买理由。",
                    rows=(profile,),
                    details={"sample_status": sample_status},
                )
            )
        for flag in sorted(_row_flags(profile)):
            severity = M12DIssueSeverity.INFO if flag in MARKET_INFO_FLAGS else M12DIssueSeverity.WARNING
            issues.append(
                self._issue(
                    module_code="M07",
                    code=flag,
                    severity=severity,
                    scope=M12DIssueScope.ROW if severity == M12DIssueSeverity.INFO else M12DIssueScope.ANCHOR,
                    message_cn=(
                        "市场范围或生命周期说明，不代表量价数据不完整。"
                        if severity == M12DIssueSeverity.INFO
                        else "市场画像存在局部限制，只影响引用市场证据的购买理由。"
                    ),
                    rows=(profile,),
                )
            )
        limited = any(issue.severity != M12DIssueSeverity.INFO for issue in issues)
        return self._present("M07", issues, limited=limited)

    def semantic_profiles(
        self,
        task_profile: Any | None,
        target_group_profile: Any | None,
        battlefield_profile: Any | None,
    ) -> M12DInputQuality:
        rows = [row for row in (task_profile, target_group_profile, battlefield_profile) if row is not None]
        if not rows:
            return self._missing(
                "M09C_M10C_M11C",
                "semantic_profiles_missing",
                "用户任务、目标客群和价值战场画像均缺失。",
            )
        issues: list[M12DInputQualityIssue] = []
        definitions = (
            ("M09C", task_profile, "primary_user_task_code"),
            ("M10C", target_group_profile, "primary_target_group_code"),
            ("M11C", battlefield_profile, "primary_battlefield_code"),
        )
        for code, row, primary_field in definitions:
            if row is None:
                issues.append(
                    self._issue(
                        module_code="M09C_M10C_M11C",
                        code=f"{code.lower()}_profile_missing",
                        severity=M12DIssueSeverity.WARNING,
                        scope=M12DIssueScope.ANCHOR,
                        message_cn=f"{code} 画像缺失，只限制依赖该语义关系的购买理由。",
                        rows=(),
                    )
                )
                continue
            if not getattr(row, primary_field, None) or bool(getattr(row, "review_required", False)):
                issues.append(
                    self._issue(
                        module_code="M09C_M10C_M11C",
                        code=f"{code.lower()}_primary_relation_unavailable",
                        severity=M12DIssueSeverity.WARNING,
                        scope=M12DIssueScope.ANCHOR,
                        message_cn=f"{code} 主关系不可用，次要关系仍保留为局部证据。",
                        tokens=_quality_tokens(_first_summary(row)),
                        rows=(row,),
                    )
                )
        return self._present("M09C_M10C_M11C", issues, limited=bool(issues))

    def semantic_market(self, rows: Sequence[Any]) -> M12DInputQuality:
        if not rows:
            return self._missing("M11D", "m11d_allocation_missing", "M11D 语义市场分配缺失。")
        low_confidence = [row for row in rows if _row_confidence(row) < Decimal("0.3500")]
        issues: list[M12DInputQualityIssue] = []
        if low_confidence:
            issues.append(
                self._issue(
                    module_code="M11D",
                    code="m11d_relation_confidence_low",
                    severity=M12DIssueSeverity.WARNING,
                    scope=M12DIssueScope.RELATION,
                    message_cn="部分语义市场关系置信度较低，只影响引用这些关系的购买理由。",
                    tokens=[str(getattr(row, "dimension_code", "")) for row in low_confidence],
                    rows=low_confidence,
                    details={"low_confidence_relation_count": len(low_confidence)},
                )
            )
        return self._present("M11D", issues, limited=bool(low_confidence))

    def claim_value(self, rows: Sequence[Any]) -> M12DInputQuality:
        if not rows:
            return self._missing("M12C", "m12c_rows_missing", "M12C 卖点价值判断缺失。")
        issues: list[M12DInputQualityIssue] = []
        for anchor_code, anchor_rows in self._m12c_rows_by_anchor(rows).items():
            claim_codes = sorted({str(getattr(row, "claim_code", "")) for row in anchor_rows if getattr(row, "claim_code", None)})
            assessment = assess_m12c_claim_value_quality(
                rows,
                referenced_claim_codes=claim_codes,
            )
            limitations = set(assessment.get("limitation_flags") or ())
            amount_flags = sorted(limitations & M12C_AMOUNT_LIMITATION_FLAGS)
            relative_flags = sorted(limitations & M12C_RELATIVE_COMPARISON_LIMITATION_FLAGS)
            if amount_flags:
                issues.append(
                    self._issue_for_anchors(
                        module_code="M12C",
                        code="m12c_amount_not_quantifiable",
                        severity=M12DIssueSeverity.INFO,
                        scope=M12DIssueScope.ANCHOR,
                        message_cn="相关卖点价值可判断，但当前比较池不支持金额或 WTP 量化。",
                        anchor_codes=(anchor_code,),
                        rows=anchor_rows,
                        details={"claim_codes": claim_codes, "flags": amount_flags},
                    )
                )
            if relative_flags:
                issues.append(
                    self._issue_for_anchors(
                        module_code="M12C",
                        code="m12c_relative_comparison_limited",
                        severity=M12DIssueSeverity.INFO,
                        scope=M12DIssueScope.ANCHOR,
                        message_cn="相关卖点的相对比较证据受限，不影响其他购买理由。",
                        anchor_codes=(anchor_code,),
                        rows=anchor_rows,
                        details={"claim_codes": claim_codes, "flags": relative_flags},
                    )
                )
            negative_rows = [row for row in anchor_rows if "comment_negative" in _row_flags(row)]
            if negative_rows:
                issues.append(
                    self._issue_for_anchors(
                        module_code="M12C",
                        code="m12c_related_claim_negative",
                        severity=M12DIssueSeverity.WARNING,
                        scope=M12DIssueScope.ANCHOR,
                        message_cn="相关卖点存在负向用户感知，只影响当前购买理由。",
                        anchor_codes=(anchor_code,),
                        rows=negative_rows,
                        details={"claim_codes": claim_codes},
                    )
                )
        return self._present(
            "M12C",
            issues,
            limited=any(issue.severity != M12DIssueSeverity.INFO for issue in issues),
        )

    def claim_value_roles_by_anchor(
        self,
        rows: Sequence[Any],
    ) -> dict[str, dict[str, list[str]]]:
        result: dict[str, dict[str, list[str]]] = {}
        for anchor_code, anchor_rows in self._m12c_rows_by_anchor(rows).items():
            role_sets: dict[str, set[str]] = {}
            for row in anchor_rows:
                claim_code = str(getattr(row, "claim_code", "") or "")
                claim_value_role = str(getattr(row, "claim_value_role", "") or "")
                if claim_code and claim_value_role:
                    role_sets.setdefault(claim_code, set()).add(claim_value_role)
            result[anchor_code] = {
                claim_code: sorted(roles)
                for claim_code, roles in sorted(role_sets.items())
            }
        return result

    def _m12c_rows_by_anchor(self, rows: Sequence[Any]) -> dict[str, list[Any]]:
        result: dict[str, list[Any]] = {}
        for reason in self.taxonomy.purchase_reasons:
            patterns = [pattern for pattern in reason.evidence_patterns if pattern.module_code == "M12C"]
            matched = [row for row in rows if any(_row_matches_pattern(row, pattern) for pattern in patterns)]
            if matched:
                result[reason.purchase_reason_code] = matched
        return result

    def _missing(self, module_code: str, code: str, message_cn: str) -> M12DInputQuality:
        return M12DInputQuality(
            module_code=module_code,
            availability=M12DInputAvailability.MISSING,
            usability=M12DInputUsability.UNUSABLE,
            issues=[
                self._issue(
                    module_code=module_code,
                    code=code,
                    severity=M12DIssueSeverity.WARNING,
                    scope=M12DIssueScope.ANCHOR,
                    message_cn=message_cn,
                    rows=(),
                )
            ],
        )

    @staticmethod
    def _present(
        module_code: str,
        issues: Sequence[M12DInputQualityIssue],
        *,
        limited: bool,
    ) -> M12DInputQuality:
        return M12DInputQuality(
            module_code=module_code,
            availability=M12DInputAvailability.PRESENT,
            usability=M12DInputUsability.LIMITED if limited else M12DInputUsability.USABLE,
            issues=list(issues),
        )

    def _issue(
        self,
        *,
        module_code: str,
        code: str,
        severity: M12DIssueSeverity,
        scope: M12DIssueScope,
        message_cn: str,
        rows: Sequence[Any],
        tokens: Iterable[str] = (),
        details: Mapping[str, Any] | None = None,
    ) -> M12DInputQualityIssue:
        affected = self._affected_anchors(module_code, tokens)
        return self._issue_for_anchors(
            module_code=module_code,
            code=code,
            severity=severity,
            scope=scope,
            message_cn=message_cn,
            anchor_codes=affected,
            rows=rows,
            details=details,
        )

    @staticmethod
    def _issue_for_anchors(
        *,
        module_code: str,
        code: str,
        severity: M12DIssueSeverity,
        scope: M12DIssueScope,
        message_cn: str,
        anchor_codes: Iterable[str],
        rows: Sequence[Any],
        details: Mapping[str, Any] | None = None,
    ) -> M12DInputQualityIssue:
        return M12DInputQualityIssue(
            code=code,
            severity=severity,
            scope=scope,
            message_cn=message_cn,
            affected_anchor_codes=sorted({str(code) for code in anchor_codes if str(code)}),
            source_refs=[_source_ref(row) for row in rows],
            details_json=dict(details or {}),
        )

    def _affected_anchors(self, module_code: str, tokens: Iterable[str]) -> list[str]:
        normalized_tokens = {_normalize(token) for token in tokens if _normalize(token)}
        all_module_anchors: list[str] = []
        matched: list[str] = []
        for reason in self.taxonomy.purchase_reasons:
            patterns = [pattern for pattern in reason.evidence_patterns if pattern.module_code == module_code]
            if not patterns:
                continue
            all_module_anchors.append(reason.purchase_reason_code)
            pattern_tokens = {
                _normalize(item)
                for pattern in patterns
                for item in (*pattern.exact_codes, *pattern.terms)
                if _normalize(item)
            }
            if normalized_tokens and any(
                left in right or right in left
                for left in normalized_tokens
                for right in pattern_tokens
            ):
                matched.append(reason.purchase_reason_code)
        return sorted(set(matched or all_module_anchors))


def legacy_status_from_quality(
    quality: M12DInputQuality,
    *,
    conflict: bool = False,
) -> M12DInputStatus:
    if quality.availability == M12DInputAvailability.MISSING:
        return M12DInputStatus.MISSING
    if conflict:
        return M12DInputStatus.CONFLICT
    profile_issues = [
        issue
        for issue in quality.issues
        if issue.scope in {M12DIssueScope.PROFILE, M12DIssueScope.RELEASE}
    ]
    if any(issue.severity == M12DIssueSeverity.BLOCKING for issue in profile_issues):
        return M12DInputStatus.CONFLICT
    if quality.usability == M12DInputUsability.UNUSABLE or profile_issues:
        return M12DInputStatus.PARTIAL
    return M12DInputStatus.READY


def _row_matches_pattern(row: Any, pattern: Any) -> bool:
    payload = {
        "claim_code": getattr(row, "claim_code", None),
        "claim_name": getattr(row, "claim_name", None),
        "claim_value_role": getattr(row, "claim_value_role", None),
        "supporting_dimensions_json": getattr(row, "supporting_dimensions_json", None),
        "reason_cn": getattr(row, "reason_cn", None),
    }
    blob = _normalize(json.dumps(payload, ensure_ascii=False, default=str))
    return any(
        normalized and normalized in blob
        for normalized in (_normalize(item) for item in (*pattern.exact_codes, *pattern.terms))
    )


def _row_flags(row: Any) -> set[str]:
    values = []
    for field_name in ("quality_flags", "quality_flags_json"):
        value = getattr(row, field_name, None)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
    return {str(value) for value in values if str(value)}


def _row_confidence(row: Any) -> Decimal:
    for field_name in ("allocation_confidence", "confidence", "attribution_confidence"):
        value = getattr(row, field_name, None)
        if value is not None:
            return Decimal(str(value))
    return Decimal("1")


def _first_summary(row: Any) -> Mapping[str, Any]:
    for field_name in (
        "user_task_summary_json",
        "target_group_summary_json",
        "battlefield_summary_json",
        "review_reason_json",
    ):
        value = getattr(row, field_name, None)
        if isinstance(value, Mapping) and value:
            return value
    return {}


def _quality_tokens(value: Any) -> list[str]:
    result: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            result.append(str(key))
            result.extend(_quality_tokens(item))
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            result.extend(_quality_tokens(item))
    elif value not in (None, ""):
        result.append(str(value))
    return result


def _param_conflict_tokens(summary: Mapping[str, Any]) -> list[str]:
    tokens = [str(code) for code in (summary.get("conflict_param_codes") or ()) if str(code)]
    for conflict in summary.get("conflicts") or ():
        if not isinstance(conflict, Mapping):
            continue
        if conflict.get("param_code"):
            tokens.append(str(conflict["param_code"]))
        tokens.extend(
            str(code) for code in (conflict.get("affected_dimension_codes") or ()) if str(code)
        )
    return tokens


def _source_ref(row: Any) -> dict[str, Any]:
    table = getattr(getattr(row, "__table__", None), "name", row.__class__.__name__)
    record_id = None
    if hasattr(row, "__table__"):
        primary_keys = list(row.__table__.primary_key.columns)
        if primary_keys:
            record_id = getattr(row, primary_keys[0].name, None)
    return {
        "table_name": str(table),
        "record_id": str(record_id or getattr(row, "sku_code", "unknown")),
    }


def _normalize(value: Any) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").lower())
