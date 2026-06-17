"""M04a parameter and promo support scorers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping

from app.services.core3_real_data.base_claim_activation_schemas import (
    ClaimMatchMethod,
    StdClaimDefinition,
    StdClaimSeed,
)


SCORE_ZERO = Decimal("0.0000")
PARAM_ONLY_ALLOWED_LEVEL_CAP = "medium"
PARAM_ONLY_NOT_ALLOWED_LEVEL_CAP = "low"
PARAM_UNCERTAIN_CODES = {
    "system_refresh_rate_hz": "refresh_scope_uncertain",
    "refresh_rate_hz": "refresh_scope_uncertain",
    "instant_peak_brightness_nits": "brightness_scope_uncertain",
    "sustained_peak_brightness_nits": "brightness_scope_uncertain",
}
PARAM_GENERIC_SUPPORT_SCORE = Decimal("0.6000")
PARAM_VERSION_ONLY_SUPPORT_SCORE = Decimal("0.4800")
PROMO_ADDITIONAL_HIT_BONUS = Decimal("0.0300")


@dataclass(frozen=True)
class ClaimParamSupport:
    claim_code: str
    param_score: Decimal
    matched_param_codes: list[str]
    param_evidence_ids: list[str]
    missing_signals: list[str]
    conflict_flags: list[str]
    quality_flags: list[str]
    review_required: bool
    param_support_json: dict[str, Any]


@dataclass(frozen=True)
class ClaimPromoSupport:
    claim_code: str
    promo_score: Decimal
    claim_hit_ids: list[str]
    promo_evidence_ids: list[str]
    quality_evidence_ids: list[str]
    missing_signals: list[str]
    conflict_flags: list[str]
    quality_flags: list[str]
    review_required: bool
    promo_support_json: dict[str, Any]


@dataclass(frozen=True)
class ClaimSupportScore:
    claim_code: str
    param_score: Decimal
    promo_score: Decimal
    param_support_json: dict[str, Any]
    promo_support_json: dict[str, Any]
    matched_param_codes: list[str]
    claim_hit_ids: list[str]
    evidence_ids: list[str]
    param_evidence_ids: list[str]
    promo_evidence_ids: list[str]
    quality_evidence_ids: list[str]
    missing_signals: list[str]
    conflict_flags: list[str]
    quality_flags: list[str]
    review_required: bool


class ParamSupportScorer:
    """Score how strongly M03 parameters support one standard claim."""

    def score_claim(self, claim: StdClaimDefinition, sku_param_profile: Any | None) -> ClaimParamSupport:
        param_values = _param_values(sku_param_profile)
        expected_param_codes = _claim_param_codes(claim)
        matched_details: list[dict[str, Any]] = []
        missing_param_codes: list[str] = []
        unknown_param_codes: list[str] = []
        conflict_flags: list[str] = []
        quality_flags: list[str] = []
        review_required = False

        for param_code in expected_param_codes:
            entry = _entry_for_param(param_values, param_code)
            if entry is None:
                missing_param_codes.append(param_code)
                continue
            if str(entry.get("value_presence") or "") != "present":
                unknown_param_codes.append(param_code)
                quality_flags.extend(_string_list(entry.get("quality_flags")))
                review_required = review_required or bool(entry.get("review_required"))
                continue

            score, detail_quality_flags, detail_conflict_flags, detail_review_required = _score_param_entry(
                claim,
                param_code,
                entry,
            )
            quality_flags.extend(detail_quality_flags)
            conflict_flags.extend(detail_conflict_flags)
            review_required = review_required or detail_review_required
            if score > SCORE_ZERO:
                matched_details.append(
                    {
                        "param_code": param_code,
                        "score": _decimal_text(score),
                        "actual_value": _actual_value_for_json(entry, param_code),
                        "evidence_ids": _string_list(entry.get("evidence_ids")),
                        "quality_flags": _unique_preserve_order(detail_quality_flags),
                        "conflict_flags": _unique_preserve_order(detail_conflict_flags),
                        "review_required": detail_review_required,
                    }
                )

        score = _combine_param_scores([_decimal(detail["score"]) for detail in matched_details])
        cap_quality_flags: list[str] = []
        if not bool(claim.param_only_allowed) and score > Decimal("0.5000"):
            score = Decimal("0.5000")
            cap_quality_flags.append("param_only_not_strong_activation")
            review_required = True

        quality_flags.extend(cap_quality_flags)
        if missing_param_codes and not matched_details:
            review_required = True
        if unknown_param_codes:
            review_required = True

        matched_param_codes = [detail["param_code"] for detail in matched_details]
        param_evidence_ids = _unique_preserve_order(
            evidence_id
            for detail in matched_details
            for evidence_id in _string_list(detail.get("evidence_ids"))
        )
        missing_signals = []
        if missing_param_codes and not matched_details:
            missing_signals.append("missing_required_param")
        if unknown_param_codes:
            missing_signals.append("param_unknown")

        support_json = {
            "claim_code": claim.claim_code,
            "score": _decimal_text(score),
            "evaluated_param_codes": expected_param_codes,
            "matched_param_codes": matched_param_codes,
            "missing_param_codes": missing_param_codes,
            "unknown_param_codes": unknown_param_codes,
            "matched_details": matched_details,
            "param_only_allowed": bool(claim.param_only_allowed),
            "param_only_level_cap": PARAM_ONLY_ALLOWED_LEVEL_CAP
            if bool(claim.param_only_allowed)
            else PARAM_ONLY_NOT_ALLOWED_LEVEL_CAP,
            "seed_weight_snapshot": _seed_weight_snapshot(claim),
            "quality_flags": _unique_preserve_order(quality_flags),
            "conflict_flags": _unique_preserve_order(conflict_flags),
        }

        return ClaimParamSupport(
            claim_code=claim.claim_code,
            param_score=score.quantize(Decimal("0.0001")),
            matched_param_codes=matched_param_codes,
            param_evidence_ids=param_evidence_ids,
            missing_signals=_unique_preserve_order(missing_signals),
            conflict_flags=_unique_preserve_order(conflict_flags),
            quality_flags=_unique_preserve_order(quality_flags),
            review_required=review_required,
            param_support_json=support_json,
        )


class PromoSupportScorer:
    """Score how strongly M04a promo claim hits support one standard claim."""

    def score_claim(self, claim: StdClaimDefinition, claim_hits: Iterable[Any]) -> ClaimPromoSupport:
        matching_hits = [hit for hit in claim_hits if _field_value(hit, "claim_code") == claim.claim_code]
        if not matching_hits:
            return ClaimPromoSupport(
                claim_code=claim.claim_code,
                promo_score=SCORE_ZERO,
                claim_hit_ids=[],
                promo_evidence_ids=[],
                quality_evidence_ids=[],
                missing_signals=["missing_promo_evidence"],
                conflict_flags=[],
                quality_flags=[],
                review_required=False,
                promo_support_json={
                    "claim_code": claim.claim_code,
                    "score": _decimal_text(SCORE_ZERO),
                    "matched_hit_count": 0,
                    "hit_details": [],
                    "seed_weight_snapshot": _seed_weight_snapshot(claim),
                },
            )

        hit_details: list[dict[str, Any]] = []
        quality_flags: list[str] = []
        conflict_flags: list[str] = []
        review_required = False
        for hit in matching_hits:
            score, hit_quality_flags, hit_conflict_flags, hit_review_required = _score_promo_hit(hit)
            quality_flags.extend(hit_quality_flags)
            conflict_flags.extend(hit_conflict_flags)
            review_required = review_required or hit_review_required
            hit_details.append(
                {
                    "claim_hit_id": _optional_string(_field_value(hit, "claim_hit_id")),
                    "score": _decimal_text(score),
                    "match_method": _enum_value(_field_value(hit, "match_method")),
                    "matched_keywords": _string_list(_field_value(hit, "matched_keywords")),
                    "title_hint": _optional_string(_field_value(hit, "title_hint")),
                    "promo_evidence_ids": _string_list(_field_value(hit, "promo_evidence_ids")),
                    "quality_evidence_ids": _string_list(_field_value(hit, "quality_evidence_ids")),
                    "quality_flags": _unique_preserve_order(hit_quality_flags),
                    "conflict_flags": _unique_preserve_order(hit_conflict_flags),
                    "review_required": hit_review_required,
                }
            )

        score = _combine_promo_scores([_decimal(detail["score"]) for detail in hit_details])
        claim_hit_ids = _unique_preserve_order(
            hit_id for detail in hit_details for hit_id in [_optional_string(detail.get("claim_hit_id"))] if hit_id
        )
        promo_evidence_ids = _unique_preserve_order(
            evidence_id
            for detail in hit_details
            for evidence_id in _string_list(detail.get("promo_evidence_ids"))
        )
        quality_evidence_ids = _unique_preserve_order(
            evidence_id
            for detail in hit_details
            for evidence_id in _string_list(detail.get("quality_evidence_ids"))
        )
        support_json = {
            "claim_code": claim.claim_code,
            "score": _decimal_text(score),
            "matched_hit_count": len(matching_hits),
            "hit_details": hit_details,
            "seed_weight_snapshot": _seed_weight_snapshot(claim),
            "quality_flags": _unique_preserve_order(quality_flags),
            "conflict_flags": _unique_preserve_order(conflict_flags),
        }
        return ClaimPromoSupport(
            claim_code=claim.claim_code,
            promo_score=score.quantize(Decimal("0.0001")),
            claim_hit_ids=claim_hit_ids,
            promo_evidence_ids=promo_evidence_ids,
            quality_evidence_ids=quality_evidence_ids,
            missing_signals=[],
            conflict_flags=_unique_preserve_order(conflict_flags),
            quality_flags=_unique_preserve_order(quality_flags),
            review_required=review_required,
            promo_support_json=support_json,
        )


class ClaimSupportScorer:
    """Build M04a param and promo support payloads without final activation."""

    def __init__(
        self,
        *,
        param_scorer: ParamSupportScorer | None = None,
        promo_scorer: PromoSupportScorer | None = None,
    ) -> None:
        self.param_scorer = param_scorer or ParamSupportScorer()
        self.promo_scorer = promo_scorer or PromoSupportScorer()

    def score_claim(
        self,
        claim: StdClaimDefinition,
        *,
        sku_param_profile: Any | None,
        claim_hits: Iterable[Any],
    ) -> ClaimSupportScore:
        param_support = self.param_scorer.score_claim(claim, sku_param_profile)
        promo_support = self.promo_scorer.score_claim(claim, claim_hits)
        evidence_ids = _unique_preserve_order(
            [
                *param_support.param_evidence_ids,
                *promo_support.promo_evidence_ids,
                *promo_support.quality_evidence_ids,
            ]
        )
        return ClaimSupportScore(
            claim_code=claim.claim_code,
            param_score=param_support.param_score,
            promo_score=promo_support.promo_score,
            param_support_json=param_support.param_support_json,
            promo_support_json=promo_support.promo_support_json,
            matched_param_codes=param_support.matched_param_codes,
            claim_hit_ids=promo_support.claim_hit_ids,
            evidence_ids=evidence_ids,
            param_evidence_ids=param_support.param_evidence_ids,
            promo_evidence_ids=promo_support.promo_evidence_ids,
            quality_evidence_ids=promo_support.quality_evidence_ids,
            missing_signals=_unique_preserve_order(
                [*param_support.missing_signals, *promo_support.missing_signals]
            ),
            conflict_flags=_unique_preserve_order(
                [*param_support.conflict_flags, *promo_support.conflict_flags]
            ),
            quality_flags=_unique_preserve_order([*param_support.quality_flags, *promo_support.quality_flags]),
            review_required=param_support.review_required or promo_support.review_required,
        )

    def score_all(
        self,
        seed: StdClaimSeed,
        *,
        sku_param_profile: Any | None,
        claim_hits: Iterable[Any],
    ) -> list[ClaimSupportScore]:
        hit_list = list(claim_hits)
        return [
            self.score_claim(claim, sku_param_profile=sku_param_profile, claim_hits=hit_list)
            for claim in seed.standard_claims
        ]


def _score_param_entry(
    claim: StdClaimDefinition,
    param_code: str,
    entry: Mapping[str, Any],
) -> tuple[Decimal, list[str], list[str], bool]:
    quality_flags = _string_list(entry.get("quality_flags"))
    conflict_flags: list[str] = []
    review_required = bool(entry.get("review_required"))
    if bool(entry.get("conflict_flag")):
        conflict_flags.append("param_conflict")
        review_required = True

    score = _activation_rule_score(claim, param_code, entry)
    if score <= SCORE_ZERO and param_code in claim.supporting_param_codes:
        score = _generic_param_support_score(param_code, entry)
    if score <= SCORE_ZERO:
        return SCORE_ZERO, quality_flags, conflict_flags, review_required

    confidence = _decimal(entry.get("confidence"), Decimal("0.7000"))
    score = score * (Decimal("0.7000") + confidence * Decimal("0.3000"))

    param_uncertain_flag = PARAM_UNCERTAIN_CODES.get(param_code)
    if param_uncertain_flag:
        quality_flags.append(param_uncertain_flag)
        score = min(score, Decimal("0.7200"))
        review_required = True
    if "scope_uncertain" in quality_flags or str(entry.get("parser_status") or "") == "scope_uncertain":
        score = min(score, Decimal("0.7000"))
        review_required = True
    if (
        "unit_inferred" in quality_flags
        or "unit_uncertain" in quality_flags
        or str(entry.get("parser_status") or "") == "unit_uncertain"
    ):
        score = min(score, Decimal("0.7200"))
        quality_flags.append("unit_uncertain")
        review_required = True
    if conflict_flags:
        score = min(score, Decimal("0.6000"))
    return _clamp_score(score), _unique_preserve_order(quality_flags), conflict_flags, review_required


def _activation_rule_score(claim: StdClaimDefinition, param_code: str, entry: Mapping[str, Any]) -> Decimal:
    score = SCORE_ZERO
    for rule in _rule_param_conditions(claim):
        if rule.get("param") != param_code:
            continue
        if _rule_condition_matches(rule, entry, param_code):
            score = max(score, _matched_rule_base_score(param_code, rule, entry))
    return score


def _rule_param_conditions(claim: StdClaimDefinition) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for raw_condition in claim.activation_rule.get("any", []):
        if isinstance(raw_condition, Mapping) and raw_condition.get("param"):
            conditions.append(dict(raw_condition))
    return conditions


def _rule_condition_matches(rule: Mapping[str, Any], entry: Mapping[str, Any], param_code: str) -> bool:
    actual = _actual_value(entry, param_code)
    if actual is None:
        return False
    if "eq" in rule:
        return _normalized_compare_value(actual) == _normalized_compare_value(rule["eq"])
    if "gte" in rule:
        actual_decimal = _decimal_or_none(actual)
        expected_decimal = _decimal_or_none(rule["gte"])
        return actual_decimal is not None and expected_decimal is not None and actual_decimal >= expected_decimal
    if "lte" in rule:
        actual_decimal = _decimal_or_none(actual)
        expected_decimal = _decimal_or_none(rule["lte"])
        return actual_decimal is not None and expected_decimal is not None and actual_decimal <= expected_decimal
    if "gt" in rule:
        actual_decimal = _decimal_or_none(actual)
        expected_decimal = _decimal_or_none(rule["gt"])
        return actual_decimal is not None and expected_decimal is not None and actual_decimal > expected_decimal
    if "lt" in rule:
        actual_decimal = _decimal_or_none(actual)
        expected_decimal = _decimal_or_none(rule["lt"])
        return actual_decimal is not None and expected_decimal is not None and actual_decimal < expected_decimal
    return False


def _matched_rule_base_score(param_code: str, rule: Mapping[str, Any], entry: Mapping[str, Any]) -> Decimal:
    if "eq" in rule:
        return Decimal("0.9300")
    if param_code == "hdmi_2_1_ports" and _hdmi_version_without_count(entry):
        return PARAM_VERSION_ONLY_SUPPORT_SCORE
    actual_decimal = _decimal_or_none(_actual_value(entry, param_code))
    expected_decimal = _decimal_or_none(rule.get("gte") if "gte" in rule else rule.get("lte"))
    if actual_decimal is None or expected_decimal is None or expected_decimal == 0:
        return Decimal("0.8800")
    if "gte" in rule and actual_decimal >= expected_decimal * Decimal("2"):
        return Decimal("0.9500")
    if "lte" in rule and actual_decimal <= expected_decimal / Decimal("2"):
        return Decimal("0.9500")
    return Decimal("0.8800")


def _generic_param_support_score(param_code: str, entry: Mapping[str, Any]) -> Decimal:
    if param_code == "hdmi_2_1_ports" and _hdmi_version_without_count(entry):
        return PARAM_VERSION_ONLY_SUPPORT_SCORE
    if _actual_value(entry, param_code) is None:
        return SCORE_ZERO
    return PARAM_GENERIC_SUPPORT_SCORE


def _score_promo_hit(hit: Any) -> tuple[Decimal, list[str], list[str], bool]:
    method = _enum_value(_field_value(hit, "match_method"))
    quality_flags = _string_list(_field_value(hit, "quality_flags"))
    conflict_flags: list[str] = []
    review_required = bool(_field_value(hit, "review_required"))
    confidence = _decimal(_field_value(hit, "match_confidence"), SCORE_ZERO)

    method_floor = {
        ClaimMatchMethod.EXACT_ALIAS.value: Decimal("0.8800"),
        ClaimMatchMethod.KEYWORD.value: Decimal("0.7600"),
        ClaimMatchMethod.ENTITY.value: Decimal("0.4500"),
    }.get(method, confidence)
    score = max(confidence, method_floor)

    extracted_entities = _mapping(_field_value(hit, "extracted_entity_json"))
    if _has_entity_payload(extracted_entities):
        score = min(Decimal("0.9000"), score + Decimal("0.0300"))
    if _string_list(extracted_entities.get("numeric_entities")):
        score = min(Decimal("0.9200"), score + Decimal("0.0400"))
    if "title_hint_weak" in quality_flags:
        score = min(Decimal("0.8500"), score + Decimal("0.0300"))
    if "abstract_promo_only" in quality_flags:
        score = min(score, Decimal("0.4200"))
        review_required = True
    if "scope_uncertain" in quality_flags:
        score = min(score, Decimal("0.7800"))
        review_required = True
    if "unit_uncertain" in quality_flags:
        score = min(score, Decimal("0.7000"))
        review_required = True
    if "multi_claim_close_match" in quality_flags:
        score = min(score, Decimal("0.8200"))
        review_required = True
    if "param_conflict" in quality_flags:
        score = min(score, Decimal("0.6500"))
        conflict_flags.append("param_promo_conflict")
        review_required = True
    return _clamp_score(score), _unique_preserve_order(quality_flags), conflict_flags, review_required


def _combine_param_scores(scores: list[Decimal]) -> Decimal:
    if not scores:
        return SCORE_ZERO
    ordered_scores = sorted(scores, reverse=True)
    bonus = min(Decimal("0.1200"), Decimal(len(ordered_scores) - 1) * Decimal("0.0400"))
    return _clamp_score(ordered_scores[0] + bonus)


def _combine_promo_scores(scores: list[Decimal]) -> Decimal:
    if not scores:
        return SCORE_ZERO
    ordered_scores = sorted(scores, reverse=True)
    bonus = min(Decimal("0.1200"), Decimal(len(ordered_scores) - 1) * PROMO_ADDITIONAL_HIT_BONUS)
    return _clamp_score(ordered_scores[0] + bonus)


def _claim_param_codes(claim: StdClaimDefinition) -> list[str]:
    rule_param_codes = [condition["param"] for condition in _rule_param_conditions(claim)]
    return _unique_preserve_order([*claim.supporting_param_codes, *claim.mapped_param_codes, *rule_param_codes])


def _param_values(sku_param_profile: Any | None) -> dict[str, Any]:
    if sku_param_profile is None:
        return {}
    return _mapping(_field_value(sku_param_profile, "param_values_json"))


def _entry_for_param(param_values: Mapping[str, Any], param_code: str) -> Mapping[str, Any] | None:
    entry = param_values.get(param_code)
    return entry if isinstance(entry, Mapping) else None


def _actual_value(entry: Mapping[str, Any], param_code: str) -> Any:
    numeric_value = _decimal_or_none(entry.get("numeric_value"))
    if numeric_value is not None:
        return numeric_value
    normalized_value = entry.get("normalized_value")
    if isinstance(normalized_value, Mapping):
        if param_code == "hdmi_2_1_ports":
            return _decimal_or_none(normalized_value.get("port_count"))
        if "value" in normalized_value:
            return normalized_value["value"]
        if "resolution_class" in normalized_value:
            return normalized_value["resolution_class"]
        if "hdmi_version" in normalized_value:
            return normalized_value["hdmi_version"]
        return normalized_value
    return normalized_value


def _actual_value_for_json(entry: Mapping[str, Any], param_code: str) -> Any:
    value = _actual_value(entry, param_code)
    if isinstance(value, Decimal):
        return _decimal_text(value)
    return value


def _hdmi_version_without_count(entry: Mapping[str, Any]) -> bool:
    normalized_value = entry.get("normalized_value")
    if not isinstance(normalized_value, Mapping):
        return False
    return bool(normalized_value.get("hdmi_version")) and normalized_value.get("port_count") is None


def _has_entity_payload(entity_payload: Mapping[str, Any]) -> bool:
    for key, value in entity_payload.items():
        if key in {"entity_quality", "numeric_entities"}:
            continue
        if isinstance(value, list) and value:
            return True
    return False


def _seed_weight_snapshot(claim: StdClaimDefinition) -> dict[str, Any]:
    normalized_weights = {key: _decimal_text(value) for key, value in sorted(claim.activation_weights.items())}
    return {
        "normalized_m04a_weights": normalized_weights,
        "m04a_usable_weight_keys": sorted(normalized_weights),
        "ignored_weight_keys": ["comment", "market"],
    }


def _field_value(record: Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    if hasattr(record, "model_dump"):
        return record.model_dump().get(field_name)
    return getattr(record, field_name, None)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _enum_value(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    return str(value or "")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalized_compare_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        decimal_value = _decimal_or_none(value)
        if decimal_value is not None:
            return decimal_value
        return str(value).casefold()
    return value


def _decimal(value: Any, default: Decimal = SCORE_ZERO) -> Decimal:
    result = _decimal_or_none(value)
    return result if result is not None else default


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_text(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001")))


def _clamp_score(score: Decimal) -> Decimal:
    return min(Decimal("1.0000"), max(SCORE_ZERO, score)).quantize(Decimal("0.0001"))


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result
