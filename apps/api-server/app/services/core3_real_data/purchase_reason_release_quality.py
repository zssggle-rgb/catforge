"""Category-isolated release quality evaluation for M12D profile versions."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.constants import (
    Core3CategoryCode,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DReleaseQualityStatus,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DFocusSkuValidationResult,
    M12DReleaseQualityEvaluation,
    M12DReleaseSystemIssue,
    M12DReleaseThresholdResult,
)


GENERATION_SUCCESS_THRESHOLD = Decimal("0.9800")
READY_THRESHOLD = Decimal("0.8500")
USABLE_THRESHOLD = Decimal("0.9500")
REVIEW_REQUIRED_THRESHOLD = Decimal("0.1500")
MISSING_FAILED_THRESHOLD = Decimal("0.0500")
CORE_MISSING_THRESHOLD = Decimal("0.1500")
FOCUS_PASS_THRESHOLD = Decimal("1.0000")
SYSTEMIC_BLOCKING_COVERAGE_THRESHOLD = Decimal("0.2000")


class M12DReleaseQualityEvaluationError(ValueError):
    pass


class M12DReleaseQualityEvaluator:
    def evaluate(
        self,
        *,
        category_code: Core3CategoryCode | str,
        product_category: str,
        profiles: Sequence[Any],
        expected_sku_count: int | None = None,
        focus_validation_results: Sequence[
            M12DFocusSkuValidationResult | Mapping[str, Any]
        ]
        | None = None,
    ) -> M12DReleaseQualityEvaluation:
        category = _category(category_code)
        normalized_product_category = str(product_category or "").strip().upper()
        if normalized_product_category != category.value:
            raise M12DReleaseQualityEvaluationError(
                f"M12D release category mismatch: {category.value}/{normalized_product_category}"
            )
        profile_rows = list(profiles)
        expected_count = (
            len(profile_rows) if expected_sku_count is None else int(expected_sku_count)
        )
        if expected_count <= 0:
            raise M12DReleaseQualityEvaluationError(
                "expected_sku_count must be positive"
            )
        self._validate_profile_categories(
            category, normalized_product_category, profile_rows
        )

        sku_codes = [_sku_code(profile) for profile in profile_rows]
        unique_sku_codes = set(sku_codes)
        profile_gap = max(0, expected_count - len(unique_sku_codes))
        status_counts = _status_counts(profile_rows)
        ready_count = status_counts[M12DProfileStatus.READY.value]
        limited_count = status_counts[M12DProfileStatus.READY_LIMITED.value]
        weak_expression_count = status_counts[
            M12DProfileStatus.WEAK_EXPRESSION_ONLY.value
        ]
        failed_count = status_counts[M12DProfileStatus.FAILED.value]
        missing_count = status_counts[M12DProfileStatus.MISSING_INPUT.value]
        success_count = min(expected_count, len(profile_rows) - failed_count)
        review_count = sum(
            1
            for profile in profile_rows
            if bool(_field(profile, "review_required", False))
        )
        core_missing_count = (
            sum(
                1
                for profile in profile_rows
                if not list(_field(profile, "core_payment_anchors_json", []) or [])
            )
            + profile_gap
        )
        missing_failed_count = missing_count + failed_count + profile_gap

        threshold_results = [
            _threshold(
                "generation_success_rate",
                success_count,
                expected_count,
                ">=",
                GENERATION_SUCCESS_THRESHOLD,
                "成功生成画像的 SKU 比例",
            ),
            _threshold(
                "ready_rate",
                ready_count,
                expected_count,
                ">=",
                READY_THRESHOLD,
                "可供强消费的 ready 画像比例",
            ),
            _threshold(
                "sku_consumable_rate",
                ready_count + limited_count + weak_expression_count,
                expected_count,
                ">=",
                USABLE_THRESHOLD,
                "至少一个业务维度可消费的 SKU 比例",
            ),
            _threshold(
                "review_required_rate",
                review_count,
                expected_count,
                "<=",
                REVIEW_REQUIRED_THRESHOLD,
                "需要人工复核的画像比例",
            ),
            _threshold(
                "missing_or_failed_rate",
                missing_failed_count,
                expected_count,
                "<=",
                MISSING_FAILED_THRESHOLD,
                "缺少最低输入或生成失败的画像比例",
            ),
            _threshold(
                "core_payment_missing_rate",
                core_missing_count,
                expected_count,
                "<=",
                CORE_MISSING_THRESHOLD,
                "缺少核心成交理由的画像比例",
            ),
        ]
        focus_threshold = _focus_threshold(focus_validation_results)
        threshold_results.append(focus_threshold)

        blocking_coverage = _blocking_issue_coverage(profile_rows, expected_count)
        system_issues = _release_system_issues(
            expected_count=expected_count,
            profile_count=len(profile_rows),
            unique_sku_count=len(unique_sku_codes),
            blocking_coverage=blocking_coverage,
        )
        failed_thresholds = [
            result.metric_code for result in threshold_results if not result.passed
        ]
        failure_reason_codes = [
            *failed_thresholds,
            *(issue.code for issue in system_issues),
        ]
        if system_issues:
            quality_status = M12DReleaseQualityStatus.BLOCKED
        elif failure_reason_codes:
            quality_status = M12DReleaseQualityStatus.LIMITED
        else:
            quality_status = M12DReleaseQualityStatus.READY

        metrics = {
            "expected_sku_count": expected_count,
            "profile_count": len(profile_rows),
            "unique_sku_count": len(unique_sku_codes),
            "status_counts": dict(sorted(status_counts.items())),
            "ready_count": ready_count,
            "ready_limited_count": limited_count,
            "weak_expression_only_count": weak_expression_count,
            "review_required_count": review_count,
            "missing_input_count": missing_count,
            "failed_count": failed_count,
            "profile_gap_count": profile_gap,
            "core_payment_missing_count": core_missing_count,
            "focus_validation_evaluated": focus_threshold.applicable,
            "focus_validation_count": focus_threshold.denominator,
        }
        for result in threshold_results:
            metrics[result.metric_code] = (
                str(result.observed_rate) if result.observed_rate is not None else None
            )
        metrics["ready_or_limited_rate"] = str(
            _rate(ready_count + limited_count, expected_count)
        )

        return M12DReleaseQualityEvaluation(
            category_code=category,
            product_category=normalized_product_category,
            expected_sku_count=expected_count,
            profile_count=len(profile_rows),
            release_quality_status=quality_status,
            metrics_json=metrics,
            threshold_results=threshold_results,
            blocking_issue_coverage_json=blocking_coverage,
            system_issues=system_issues,
            failure_reason_codes=_dedupe(failure_reason_codes),
        )

    @staticmethod
    def _validate_profile_categories(
        category: Core3CategoryCode,
        product_category: str,
        profiles: Sequence[Any],
    ) -> None:
        for profile in profiles:
            profile_category = _value(_field(profile, "category_code", "")).upper()
            profile_product_category = str(
                _field(profile, "product_category", "")
            ).upper()
            if (
                profile_category != category.value
                or profile_product_category != product_category
            ):
                raise M12DReleaseQualityEvaluationError(
                    "M12D release evaluation cannot mix categories: "
                    f"expected {category.value}, got {profile_category}/{profile_product_category}"
                )


def _threshold(
    metric_code: str,
    numerator: int,
    denominator: int,
    operator: str,
    threshold: Decimal,
    label_cn: str,
) -> M12DReleaseThresholdResult:
    observed = _rate(numerator, denominator)
    if operator == ">=":
        passed = observed >= threshold
    elif operator == "<=":
        passed = observed <= threshold
    else:
        passed = observed == threshold
    return M12DReleaseThresholdResult(
        metric_code=metric_code,
        numerator=numerator,
        denominator=denominator,
        observed_rate=observed,
        operator=operator,
        threshold=threshold,
        applicable=True,
        passed=passed,
        reason_cn=(
            f"{label_cn}为 {observed}，门槛为 {operator} {threshold}，"
            f"结果{'通过' if passed else '未通过'}。"
        ),
    )


def _focus_threshold(
    focus_validation_results: Sequence[M12DFocusSkuValidationResult | Mapping[str, Any]]
    | None,
) -> M12DReleaseThresholdResult:
    if not focus_validation_results:
        return M12DReleaseThresholdResult(
            metric_code="focus_sku_pass_rate",
            numerator=0,
            denominator=0,
            observed_rate=None,
            operator="=",
            threshold=FOCUS_PASS_THRESHOLD,
            applicable=False,
            passed=False,
            reason_cn="重点 SKU 尚未完成验证，版本不能判为 release-ready。",
        )
    results = [
        item
        if isinstance(item, M12DFocusSkuValidationResult)
        else M12DFocusSkuValidationResult.model_validate(item)
        for item in focus_validation_results
    ]
    passed_count = sum(1 for item in results if item.passed)
    return _threshold(
        "focus_sku_pass_rate",
        passed_count,
        len(results),
        "=",
        FOCUS_PASS_THRESHOLD,
        "重点 SKU 验证通过率",
    )


def _blocking_issue_coverage(
    profiles: Sequence[Any],
    expected_sku_count: int,
) -> list[dict[str, Any]]:
    affected_skus: dict[str, set[str]] = defaultdict(set)
    for profile in profiles:
        sku_code = _sku_code(profile)
        quality_json = _field(profile, "input_quality_json", {}) or {}
        quality_rows = (
            quality_json.values() if isinstance(quality_json, Mapping) else ()
        )
        for quality in quality_rows:
            for issue in _field(quality, "issues", []) or []:
                if (
                    _value(_field(issue, "severity", ""))
                    != M12DIssueSeverity.BLOCKING.value
                ):
                    continue
                issue_code = str(_field(issue, "code", "")).strip()
                if issue_code:
                    affected_skus[issue_code].add(sku_code)
    return [
        {
            "issue_code": issue_code,
            "affected_sku_count": len(sku_codes),
            "total_sku_count": expected_sku_count,
            "coverage_rate": str(_rate(len(sku_codes), expected_sku_count)),
        }
        for issue_code, sku_codes in sorted(affected_skus.items())
    ]


def _release_system_issues(
    *,
    expected_count: int,
    profile_count: int,
    unique_sku_count: int,
    blocking_coverage: Sequence[Mapping[str, Any]],
) -> list[M12DReleaseSystemIssue]:
    issues: list[M12DReleaseSystemIssue] = []
    if profile_count != expected_count or unique_sku_count != expected_count:
        issues.append(
            M12DReleaseSystemIssue(
                code="release_profile_scope_mismatch",
                affected_sku_count=abs(expected_count - unique_sku_count),
                total_sku_count=expected_count,
                coverage_rate=_rate(
                    abs(expected_count - unique_sku_count), expected_count
                ),
                message_cn="版本画像数量或 SKU 唯一数与发布范围不一致，必须先修复批处理或 lineage。",
            )
        )
    for coverage in blocking_coverage:
        rate = Decimal(str(coverage["coverage_rate"]))
        if rate <= SYSTEMIC_BLOCKING_COVERAGE_THRESHOLD:
            continue
        issue_code = str(coverage["issue_code"])
        issues.append(
            M12DReleaseSystemIssue(
                code="systemic_blocking_issue_coverage",
                source_issue_code=issue_code,
                affected_sku_count=int(coverage["affected_sku_count"]),
                total_sku_count=expected_count,
                coverage_rate=rate,
                message_cn=(
                    f"同一阻断问题 {issue_code} 覆盖 {rate} 的 SKU，超过 0.2000，"
                    "属于系统问题，禁止发布。"
                ),
            )
        )
    return issues


def _status_counts(profiles: Sequence[Any]) -> dict[str, int]:
    counts = {
        M12DProfileStatus.READY.value: 0,
        M12DProfileStatus.READY_LIMITED.value: 0,
        M12DProfileStatus.WEAK_EXPRESSION_ONLY.value: 0,
        M12DProfileStatus.MISSING_INPUT.value: 0,
        M12DProfileStatus.FAILED.value: 0,
    }
    for profile in profiles:
        status = _value(_field(profile, "status", ""))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _sku_code(profile: Any) -> str:
    sku_code = str(_field(profile, "sku_code", "")).strip()
    if not sku_code:
        raise M12DReleaseQualityEvaluationError("profile sku_code is required")
    return sku_code


def _category(value: Core3CategoryCode | str) -> Core3CategoryCode:
    try:
        return Core3CategoryCode(_value(value).upper())
    except ValueError as exc:
        raise M12DReleaseQualityEvaluationError(
            f"unsupported M12D release category: {value}"
        ) from exc


def _field(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _value(value: Any) -> str:
    return str(value.value) if isinstance(value, Enum) else str(value)


def _rate(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.0000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))


__all__ = [
    "M12DReleaseQualityEvaluationError",
    "M12DReleaseQualityEvaluator",
]
