from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ALLOWED_RULE_TYPES = {
    "claim_activation",
    "task_score",
    "battlefield_score",
    "competitor_score",
    "review_trigger",
}
ALLOWED_OPERATORS = {
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "exists",
    "missing",
    "regex",
    "contains",
    "range",
}
LOGICAL_OPERATORS = {"any", "all", "not"}


class RuleValidationError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


@dataclass
class RuleEvaluationContext:
    features: dict[str, Any]
    evidence_by_feature: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RuleEvaluationResult:
    output_code: str
    score: float
    matched: bool
    confidence: str
    review_status: str
    relation_level: str
    evidence_ids: list[str]
    rule_version: str
    rule_id: str


def load_rule_documents(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        loaded = list(yaml.safe_load_all(handle))
    return [item for item in loaded if item]


def parse_rule_documents(content: str, source_format: str = "yaml") -> list[dict[str, Any]]:
    if source_format == "json":
        payload = json.loads(content)
        return payload if isinstance(payload, list) else [payload]
    loaded = list(yaml.safe_load_all(content))
    return [item for item in loaded if item]


def validate_rule_documents(rule_sets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    errors: list[str] = []
    for index, rule_set in enumerate(rule_sets):
        errors.extend(validate_rule_set(rule_set, f"documents[{index}]"))
    if errors:
        raise RuleValidationError(errors)
    return rule_sets


def validate_rule_set(rule_set: dict[str, Any], path: str = "rule_set") -> list[str]:
    errors: list[str] = []
    for key in ["rule_set_id", "category", "version"]:
        if not rule_set.get(key):
            errors.append(f"{path}.{key} is required")

    if _is_competitor_rule(rule_set):
        _validate_competitor_rule(rule_set, path, errors)
        return errors

    rule_type = rule_set.get("rule_type")
    if rule_type not in ALLOWED_RULE_TYPES:
        errors.append(f"{path}.rule_type must be one of {sorted(ALLOWED_RULE_TYPES)}")

    rules = rule_set.get("rules")
    if not isinstance(rules, list) or not rules:
        errors.append(f"{path}.rules must be a non-empty list")
        return errors

    for rule_index, rule in enumerate(rules):
        rule_path = f"{path}.rules[{rule_index}]"
        if not rule.get("rule_id"):
            errors.append(f"{rule_path}.rule_id is required")
        if not rule.get("output_code"):
            errors.append(f"{rule_path}.output_code is required")
        if "conditions" in rule:
            _validate_condition(rule["conditions"], f"{rule_path}.conditions", errors)
        weights = (rule.get("score") or {}).get("weights", [])
        if not isinstance(weights, list):
            errors.append(f"{rule_path}.score.weights must be a list")
        for weight_index, weight in enumerate(weights):
            weight_path = f"{rule_path}.score.weights[{weight_index}]"
            if not weight.get("feature"):
                errors.append(f"{weight_path}.feature is required")
            if "op" in weight and weight["op"] not in ALLOWED_OPERATORS:
                errors.append(f"{weight_path}.op has unsupported operator: {weight['op']}")
            if not isinstance(weight.get("points", 0), (int, float)):
                errors.append(f"{weight_path}.points must be numeric")
    return errors


def evaluate_rule_set(
    rule_set: dict[str, Any], context: RuleEvaluationContext
) -> list[RuleEvaluationResult]:
    validate_rule_documents([rule_set])
    return [_evaluate_rule(rule_set, rule, context) for rule in rule_set.get("rules", [])]


def evaluate_condition(condition: Any, context: RuleEvaluationContext) -> bool:
    if not isinstance(condition, dict):
        return False
    if "any" in condition:
        return any(evaluate_condition(item, context) for item in condition["any"])
    if "all" in condition:
        return all(evaluate_condition(item, context) for item in condition["all"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], context)
    feature = condition.get("feature")
    op = condition.get("op")
    if not feature or op not in ALLOWED_OPERATORS:
        return False
    return _compare(resolve_feature(context, feature), op, condition.get("value"))


def resolve_feature(context: RuleEvaluationContext, feature: str) -> Any:
    if feature == "claim_text":
        return context.features.get("claim_text")
    namespace, _, key = feature.partition(".")
    if not key:
        return context.features.get(feature)
    bucket = context.features.get(namespace, {})
    if isinstance(bucket, dict):
        value = bucket.get(key)
        if isinstance(value, dict) and "score" in value:
            return value.get("score")
        return value
    return None


def evidence_for_feature(context: RuleEvaluationContext, feature: str) -> list[str]:
    evidence = context.evidence_by_feature.get(feature, [])
    if evidence:
        return evidence
    namespace, _, _ = feature.partition(".")
    return context.evidence_by_feature.get(namespace, [])


def confidence_to_float(confidence: str) -> float:
    return {
        "high": 0.9,
        "medium": 0.72,
        "low": 0.55,
        "insufficient_sample": 0.25,
    }.get(confidence, 0.5)


def _evaluate_rule(
    rule_set: dict[str, Any], rule: dict[str, Any], context: RuleEvaluationContext
) -> RuleEvaluationResult:
    conditions = rule.get("conditions")
    condition_matched = True if conditions is None else evaluate_condition(conditions, context)
    score = 0.0
    evidence_ids: list[str] = []
    for weight in (rule.get("score") or {}).get("weights", []):
        feature = weight.get("feature")
        if not feature:
            continue
        if "op" in weight:
            matched = _compare(resolve_feature(context, feature), weight["op"], weight.get("value"))
        else:
            matched = _truthy_score(resolve_feature(context, feature))
        if matched:
            score += float(weight.get("points", 0))
            evidence_ids.extend(evidence_for_feature(context, feature))
    if not (rule.get("score") or {}).get("weights") and condition_matched:
        score = 100.0
    if not condition_matched:
        score = 0.0
    score = max(0.0, min(100.0, score))
    confidence, review_status, relation_level, matched = _classify(rule_set["rule_type"], score, rule)
    return RuleEvaluationResult(
        output_code=rule["output_code"],
        score=round(score, 2),
        matched=matched,
        confidence=confidence,
        review_status=review_status,
        relation_level=relation_level,
        evidence_ids=_unique(evidence_ids),
        rule_version=str(rule_set["version"]),
        rule_id=rule["rule_id"],
    )


def _classify(rule_type: str, score: float, rule: dict[str, Any]) -> tuple[str, str, str, bool]:
    thresholds = rule.get("thresholds") or {}
    if rule_type == "claim_activation":
        activated = float(thresholds.get("activated", 60))
        high = float(thresholds.get("high_confidence", 85))
        review = float(thresholds.get("review", 45))
        if score >= high:
            return "high", "auto_pass", "activated", True
        if score >= activated:
            return "medium", "auto_pass", "activated", True
        if score >= review:
            return "low", "needs_review", "candidate", False
        return "insufficient_sample", "not_applicable", "rejected", False
    if rule_type == "task_score":
        high = float(thresholds.get("high", 75))
        medium = float(thresholds.get("medium", 55))
        review = float(thresholds.get("review", 40))
        if score >= high:
            return "high", "auto_pass", "high", True
        if score >= medium:
            return "medium", "auto_pass", "medium", True
        if score >= review:
            return "low", "needs_review", "weak", True
        return "insufficient_sample", "not_applicable", "none", False
    if rule_type == "battlefield_score":
        main = float(thresholds.get("main", 75))
        secondary = float(thresholds.get("secondary", 60))
        weak = float(thresholds.get("weak", 45))
        if score >= main:
            return "high", "auto_pass", "main", True
        if score >= secondary:
            return "medium", "auto_pass", "secondary", True
        if score >= weak:
            return "low", "needs_review", "weak", True
        return "insufficient_sample", "not_applicable", "none", False
    return "medium", "auto_pass", "candidate", score > 0


def _validate_condition(condition: Any, path: str, errors: list[str]) -> None:
    if not isinstance(condition, dict):
        errors.append(f"{path} must be an object")
        return
    logical_keys = [key for key in LOGICAL_OPERATORS if key in condition]
    if logical_keys:
        for key in logical_keys:
            value = condition[key]
            if key == "not":
                _validate_condition(value, f"{path}.not", errors)
            elif not isinstance(value, list):
                errors.append(f"{path}.{key} must be a list")
            else:
                for index, item in enumerate(value):
                    _validate_condition(item, f"{path}.{key}[{index}]", errors)
        return
    if not condition.get("feature"):
        errors.append(f"{path}.feature is required")
    op = condition.get("op")
    if op not in ALLOWED_OPERATORS:
        errors.append(f"{path}.op has unsupported operator: {op}")


def _validate_competitor_rule(rule_set: dict[str, Any], path: str, errors: list[str]) -> None:
    if not isinstance(rule_set.get("candidate_filters"), dict):
        errors.append(f"{path}.candidate_filters must be an object")
    weights = rule_set.get("component_weights")
    if not isinstance(weights, dict) or not weights:
        errors.append(f"{path}.component_weights must be a non-empty object")
    type_rules = rule_set.get("type_rules")
    if not isinstance(type_rules, list) or not type_rules:
        errors.append(f"{path}.type_rules must be a non-empty list")
    for index, item in enumerate(type_rules or []):
        if not item.get("competitor_type"):
            errors.append(f"{path}.type_rules[{index}].competitor_type is required")
        if not isinstance(item.get("min_score"), (int, float)):
            errors.append(f"{path}.type_rules[{index}].min_score must be numeric")


def _is_competitor_rule(rule_set: dict[str, Any]) -> bool:
    return bool(rule_set.get("candidate_filters") or rule_set.get("rule_type") == "competitor_score")


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if op == "exists":
        return actual is not None
    if op == "missing":
        return actual is None
    if actual is None:
        return False
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op in {"gt", "gte", "lt", "lte"}:
        left = _number(actual)
        right = _number(expected)
        if left is None or right is None:
            return False
        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        return left <= right
    if op == "in":
        return actual in (expected or [])
    if op == "not_in":
        return actual not in (expected or [])
    if op == "regex":
        return bool(re.search(str(expected), str(actual)))
    if op == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return str(expected) in str(actual)
    if op == "range":
        left = _number(actual)
        if left is None:
            return False
        if isinstance(expected, dict):
            min_value = _number(expected.get("min"))
            max_value = _number(expected.get("max"))
        else:
            values = list(expected or [])
            min_value = _number(values[0]) if len(values) > 0 else None
            max_value = _number(values[1]) if len(values) > 1 else None
        return (min_value is None or left >= min_value) and (max_value is None or left <= max_value)
    return False


def _truthy_score(actual: Any) -> bool:
    if actual is None:
        return False
    if isinstance(actual, bool):
        return actual
    if isinstance(actual, (int, float)):
        return actual > 0
    if isinstance(actual, str):
        return actual not in {"", "0", "false", "False", "unknown", "none", "None"}
    if isinstance(actual, (list, tuple, set, dict)):
        return bool(actual)
    return bool(actual)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
