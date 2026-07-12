"""Deterministic multi-layer counterfactual recall for sellpoint-value V5.

This module deliberately stops before effect estimation.  It separates broad
market recall from candidates that are eligible for descriptive comparisons;
G04 and G06 own synthetic effects and strict amount gates respectively.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
import hashlib
import json
from typing import Any

from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_category_config import same_product_form
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    CounterfactualCandidate,
    CounterfactualMethod,
    CounterfactualQuestion,
    CounterfactualSet,
    SellpointValueV5Context,
)


SAME_BUDGET_RATIO = 0.15
SYNTHETIC_RECALL_RATIO = 0.30
MIN_SYNTHETIC_DONORS = 5
OWN_CURVE_MIN_WEEKS = 8
OWN_CURVE_MIN_PLATFORMS = 2

_METHOD_ORDER: dict[str, int] = {
    "direct_sku": 0,
    "same_budget_pool": 1,
    "same_brand_size_ladder": 2,
    "param_tier_pool": 3,
    "same_claim_realization": 4,
    "own_price_curve": 5,
    "market_synthetic": 6,
    "performance_archetype": 7,
}

_QUESTION_METHOD_PRIORITY: dict[str, tuple[str, ...]] = {
    "user_realization": ("same_claim_realization",),
    "relative_highlight": (
        "direct_sku",
        "same_budget_pool",
        "same_brand_size_ladder",
        "param_tier_pool",
    ),
    "without_value_baseline": ("direct_sku", "param_tier_pool", "market_synthetic"),
    "price_realization": (
        "direct_sku",
        "own_price_curve",
        "same_budget_pool",
        "same_brand_size_ladder",
    ),
    "volume_realization": ("direct_sku", "same_budget_pool", "market_synthetic"),
}


def build_v5_counterfactual_sets(
    context: SellpointValueV5Context,
    *,
    bundle_code: str,
    focus_dimension_codes: Sequence[str] = (),
    focus_claim_codes: Sequence[str] = (),
) -> list[CounterfactualSet]:
    """Recall all V5 counterfactual layers without estimating effects."""

    target_code = context.v4_context.target.sku_code
    snapshots = {row.identity.sku_code: row for row in context.market_universe}
    target = snapshots[target_code]
    peers = [snapshots[code] for code in sorted(snapshots) if code != target_code]
    direct_codes = {
        row.identity.sku_code for row in context.v4_context.candidate_snapshots
    }
    dimensions = tuple(sorted(set(focus_dimension_codes)))
    claims = tuple(sorted(set(focus_claim_codes)))

    candidates_by_question: dict[str, list[CounterfactualCandidate]] = {
        question: [] for question in _QUESTION_METHOD_PRIORITY
    }

    for peer in peers:
        peer_code = peer.identity.sku_code
        exact_size = _same_size(target, peer)
        battlefield_overlap = _battlefield_overlap(target, peer)
        price_ratio = _relative_price_ratio(target, peer)
        same_budget = exact_size and price_ratio is not None and price_ratio <= SAME_BUDGET_RATIO
        same_brand_size = (
            exact_size
            and bool(target.identity.brand_name)
            and target.identity.brand_name == peer.identity.brand_name
        )
        tier_relation, tier_dimensions = _tier_relation(target, peer, dimensions)

        if peer_code in direct_codes:
            relative = _direct_candidate(
                context,
                target,
                peer,
                bundle_code=bundle_code,
                question="relative_highlight",
                tier_relation=tier_relation,
                exact_size=exact_size,
                battlefield_overlap=battlefield_overlap,
                price_ratio=price_ratio,
            )
            candidates_by_question["relative_highlight"].append(relative)
            if tier_relation == "lower":
                candidates_by_question["without_value_baseline"].append(
                    _retarget_direct_candidate(
                        relative, question="without_value_baseline"
                    )
                )
            for question in ("price_realization", "volume_realization"):
                candidates_by_question[question].append(
                    _retarget_direct_candidate(relative, question=question)
                )

        if same_budget:
            base = _descriptive_candidate(
                target,
                peer,
                method="same_budget_pool",
                question="relative_highlight",
                bundle_code=bundle_code,
                tier_relation=tier_relation,
                price_ratio=price_ratio,
                battlefield_overlap=battlefield_overlap,
                eligible_measure="same_budget_market_position",
                controls={"exact_size": True, "price_ratio": price_ratio},
            )
            candidates_by_question["relative_highlight"].append(base)
            for question in ("price_realization", "volume_realization"):
                candidates_by_question[question].append(
                    base.model_copy(
                        update={
                            "question": question,
                            "candidate_key": f"same_budget_pool:{question}:{peer_code}",
                        }
                    )
                )

        if same_brand_size:
            ladder = _descriptive_candidate(
                target,
                peer,
                method="same_brand_size_ladder",
                question="relative_highlight",
                bundle_code=bundle_code,
                tier_relation=tier_relation,
                price_ratio=price_ratio,
                battlefield_overlap=battlefield_overlap,
                eligible_measure="brand_size_ladder_position",
                controls={"exact_size": True, "same_brand": True},
            )
            candidates_by_question["relative_highlight"].append(ladder)
            candidates_by_question["price_realization"].append(
                ladder.model_copy(
                    update={
                        "question": "price_realization",
                        "candidate_key": f"same_brand_size_ladder:price_realization:{peer_code}",
                    }
                )
            )

        if same_budget and tier_dimensions:
            tier_candidate = _descriptive_candidate(
                target,
                peer,
                method="param_tier_pool",
                question="relative_highlight",
                bundle_code=bundle_code,
                tier_relation=tier_relation,
                price_ratio=price_ratio,
                battlefield_overlap=battlefield_overlap,
                eligible_measure="parameter_tier_contrast",
                controls={"tier_dimensions": tier_dimensions},
            )
            candidates_by_question["relative_highlight"].append(tier_candidate)
            if tier_relation == "lower":
                candidates_by_question["without_value_baseline"].append(
                    tier_candidate.model_copy(
                        update={
                            "question": "without_value_baseline",
                            "candidate_key": f"param_tier_pool:without_value_baseline:{peer_code}",
                        }
                    )
                )

        claim_contrast = _same_claim_contrast(target, peer, claims)
        if same_budget and claim_contrast:
            candidates_by_question["user_realization"].append(
                _descriptive_candidate(
                    target,
                    peer,
                    method="same_claim_realization",
                    question="user_realization",
                    bundle_code=bundle_code,
                    tier_relation=tier_relation,
                    price_ratio=price_ratio,
                    battlefield_overlap=battlefield_overlap,
                    eligible_measure="same_claim_user_realization",
                    controls=claim_contrast,
                )
            )

    own_curve = _own_price_curve_candidate(target, bundle_code=bundle_code)
    candidates_by_question["price_realization"].append(own_curve)

    synthetic_donors = []
    for peer in peers:
        price_ratio = _relative_price_ratio(target, peer)
        if (
            _same_size(target, peer)
            and price_ratio is not None
            and price_ratio <= SYNTHETIC_RECALL_RATIO
            and _battlefield_overlap(target, peer) > 0
        ):
            synthetic_donors.append(peer)
    for question in ("without_value_baseline", "volume_realization"):
        candidates_by_question[question].append(
            _synthetic_pool_candidate(
                target,
                synthetic_donors,
                bundle_code=bundle_code,
                question=question,
            )
        )

    return [
        _counterfactual_set(bundle_code, question, candidates_by_question[question])
        for question in _QUESTION_METHOD_PRIORITY
    ]


def _direct_candidate(
    context: SellpointValueV5Context,
    target: SkuEvidenceSnapshot,
    peer: SkuEvidenceSnapshot,
    *,
    bundle_code: str,
    question: CounterfactualQuestion,
    tier_relation: str,
    exact_size: bool,
    battlefield_overlap: float,
    price_ratio: float | None,
) -> CounterfactualCandidate:
    reasons: list[str] = []
    if not exact_size:
        reasons.append("size_mismatch")
    if battlefield_overlap <= 0:
        reasons.append("battlefield_mismatch")
    authority_eligible = _direct_authority_eligible(peer)
    if not authority_eligible:
        reasons.append("direct_authority_not_eligible")
    common_weeks, common_platforms = _common_market_scope(
        context, target.identity.sku_code, peer.identity.sku_code
    )
    hard_reject = any(reason in {"size_mismatch", "battlefield_mismatch"} for reason in reasons)
    stage = "rejected" if hard_reject else "eligible" if authority_eligible else "screened"
    grade = "unusable" if hard_reject else "A" if authority_eligible else "C"
    eligible_measures = ["direct_relative_comparison"] if stage == "eligible" else []
    source = _candidate_source(peer)
    return _candidate(
        target,
        [peer],
        method="direct_sku",
        question=question,
        stage=stage,
        candidate_key=f"direct_sku:{question}:{peer.identity.sku_code}",
        provenance=source,
        tier_relation=tier_relation,
        controls={
            "exact_size": exact_size,
            "battlefield_overlap": battlefield_overlap,
            "price_ratio": price_ratio,
            "authority_eligible": authority_eligible,
            "bundle_code": bundle_code,
        },
        common_week_count=common_weeks,
        common_platform_count=common_platforms,
        observed_price_overlap=_overlap_score(price_ratio),
        grade=grade,
        eligible_measures=eligible_measures,
        reject_reasons=reasons,
    )


def _descriptive_candidate(
    target: SkuEvidenceSnapshot,
    peer: SkuEvidenceSnapshot,
    *,
    method: CounterfactualMethod,
    question: CounterfactualQuestion,
    bundle_code: str,
    tier_relation: str,
    price_ratio: float | None,
    battlefield_overlap: float,
    eligible_measure: str,
    controls: dict[str, Any],
) -> CounterfactualCandidate:
    return _candidate(
        target,
        [peer],
        method=method,
        question=question,
        stage="eligible",
        candidate_key=f"{method}:{question}:{peer.identity.sku_code}",
        provenance="market_universe",
        tier_relation=tier_relation,
        controls={
            **controls,
            "battlefield_overlap": battlefield_overlap,
            "bundle_code": bundle_code,
        },
        observed_price_overlap=_overlap_score(price_ratio),
        grade="B" if method == "same_claim_realization" else "C",
        eligible_measures=[eligible_measure],
        reject_reasons=[],
    )


def _retarget_direct_candidate(
    candidate: CounterfactualCandidate,
    *,
    question: CounterfactualQuestion,
) -> CounterfactualCandidate:
    stage = candidate.stage
    measures = list(candidate.eligible_measures)
    reasons = list(candidate.reject_reasons)
    if candidate.stage == "eligible" and question in {"price_realization", "volume_realization"}:
        market_ready = (
            candidate.common_week_count >= OWN_CURVE_MIN_WEEKS
            and candidate.common_platform_count >= OWN_CURVE_MIN_PLATFORMS
            and candidate.observed_price_overlap is not None
        )
        if market_ready:
            measures = ["direct_market_comparison"]
        else:
            stage = "screened"
            measures = []
            reasons.append("direct_market_scope_insufficient")
    elif candidate.stage == "eligible" and question == "without_value_baseline":
        measures = ["direct_value_tier_contrast"]
    return candidate.model_copy(
        update={
            "question": question,
            "stage": stage,
            "candidate_key": (
                f"direct_sku:{question}:{candidate.candidate_sku_codes[0]}"
            ),
            "eligible_measures": measures,
            "reject_reasons": sorted(set(reasons)),
        }
    )


def _own_price_curve_candidate(
    target: SkuEvidenceSnapshot, *, bundle_code: str
) -> CounterfactualCandidate:
    weeks = int(_market_value(target, "active_week_count") or 0)
    platforms = int(_market_value(target, "platform_count") or 0)
    volatility = float(_market_value(target, "price_volatility") or 0)
    reasons: list[str] = []
    if weeks < OWN_CURVE_MIN_WEEKS:
        reasons.append("active_weeks_insufficient")
    if platforms < OWN_CURVE_MIN_PLATFORMS:
        reasons.append("platform_count_insufficient")
    if volatility <= 0:
        reasons.append("price_variation_insufficient")
    eligible = not reasons
    return _candidate(
        target,
        [target],
        method="own_price_curve",
        question="price_realization",
        stage="eligible" if eligible else "rejected",
        candidate_key=f"own_price_curve:price_realization:{target.identity.sku_code}",
        provenance="target_market_history",
        tier_relation="same",
        controls={
            "bundle_code": bundle_code,
            "active_week_count": weeks,
            "platform_count": platforms,
            "price_volatility": volatility,
        },
        common_week_count=weeks,
        common_platform_count=platforms,
        grade="A" if eligible else "unusable",
        eligible_measures=["whole_product_own_price_response"] if eligible else [],
        reject_reasons=reasons,
    )


def _synthetic_pool_candidate(
    target: SkuEvidenceSnapshot,
    donors: Sequence[SkuEvidenceSnapshot],
    *,
    bundle_code: str,
    question: CounterfactualQuestion,
) -> CounterfactualCandidate:
    reasons = [] if len(donors) >= MIN_SYNTHETIC_DONORS else ["broad_donor_pool_insufficient"]
    stage = "recalled" if not reasons else "rejected"
    selected = list(sorted(donors, key=lambda row: row.identity.sku_code))
    return _candidate(
        target,
        selected,
        method="market_synthetic",
        question=question,
        stage=stage,
        candidate_key=f"market_synthetic:{question}:{bundle_code}",
        provenance="market_universe_broad_recall",
        tier_relation="unknown",
        controls={
            "bundle_code": bundle_code,
            "donor_count": len(donors),
            "same_size": True,
            "price_ratio_max": SYNTHETIC_RECALL_RATIO,
            "shared_entered_battlefield": True,
            "balanced": False,
        },
        grade="C" if not reasons else "unusable",
        eligible_measures=[],
        reject_reasons=reasons,
    )


def _candidate(
    target: SkuEvidenceSnapshot,
    rows: Sequence[SkuEvidenceSnapshot],
    *,
    method: CounterfactualMethod,
    question: CounterfactualQuestion,
    stage: str,
    candidate_key: str,
    provenance: str,
    tier_relation: str,
    controls: dict[str, Any],
    common_week_count: int = 0,
    common_platform_count: int = 0,
    observed_price_overlap: float | None = None,
    grade: str | None = None,
    eligible_measures: Sequence[str] = (),
    reject_reasons: Sequence[str] = (),
) -> CounterfactualCandidate:
    codes = sorted({row.identity.sku_code for row in rows})
    manifest = {
        "target": target.snapshot_hash,
        "method": method,
        "question": question,
        "candidate_snapshots": {
            row.identity.sku_code: row.snapshot_hash
            for row in sorted(rows, key=lambda item: item.identity.sku_code)
        },
    }
    return CounterfactualCandidate(
        method=method,
        question=question,
        stage=stage,  # type: ignore[arg-type]
        candidate_key=candidate_key,
        candidate_sku_codes=codes,
        provenance=provenance,
        value_tier_relation=tier_relation,  # type: ignore[arg-type]
        control_dimensions=controls,
        common_week_count=common_week_count,
        common_platform_count=common_platform_count,
        observed_price_overlap=observed_price_overlap,
        inventory_status="unavailable",
        comparability_grade=grade,  # type: ignore[arg-type]
        eligible_measures=list(eligible_measures),
        reject_reasons=sorted(set(reject_reasons)),
        sample_manifest_hash=_canonical_hash(manifest),
        source_refs=_dedupe_refs(row.source_refs for row in rows),
    )


def _counterfactual_set(
    bundle_code: str,
    question: CounterfactualQuestion,
    candidates: Sequence[CounterfactualCandidate],
) -> CounterfactualSet:
    unique: dict[tuple[str, str], CounterfactualCandidate] = {}
    for row in candidates:
        unique[(row.method, row.candidate_key)] = row
    ordered = sorted(
        unique.values(),
        key=lambda row: (_METHOD_ORDER[row.method], row.candidate_key),
    )
    highest = _highest_available_method(question, ordered)
    payload = {
        "bundle_code": bundle_code,
        "question": question,
        "candidates": [row.model_dump(mode="json") for row in ordered],
        "highest_available_method": highest,
    }
    degradation = sorted(
        {
            reason
            for row in ordered
            if row.stage != "eligible"
            for reason in row.reject_reasons
        }
    )
    if not ordered:
        degradation.append("no_counterfactual_recalled")
    return CounterfactualSet(
        bundle_code=bundle_code,
        question=question,
        candidates=ordered,
        highest_available_method=highest,  # type: ignore[arg-type]
        selection_reasons=(
            [f"highest_available_method:{highest}"] if highest else []
        ),
        degradation_reasons=degradation,
        set_hash=_canonical_hash(payload),
    )


def _highest_available_method(
    question: str, candidates: Sequence[CounterfactualCandidate]
) -> str | None:
    eligible = {row.method for row in candidates if row.stage == "eligible"}
    for method in _QUESTION_METHOD_PRIORITY[question]:
        if method in eligible:
            return method
    return None


def _direct_authority_eligible(snapshot: SkuEvidenceSnapshot) -> bool:
    source = snapshot.facts.get("candidate_source") or {}
    return source.get("authority_eligible") is True


def _candidate_source(snapshot: SkuEvidenceSnapshot) -> str:
    source = snapshot.facts.get("candidate_source") or {}
    return str(source.get("provenance") or "v4_candidate")


def _same_size(target: SkuEvidenceSnapshot, peer: SkuEvidenceSnapshot) -> bool:
    if target.identity.product_category.upper() == "AC":
        return same_product_form(target, peer)
    left = target.identity.screen_size_inch
    right = peer.identity.screen_size_inch
    return left is not None and right is not None and abs(left - right) <= 0.01


def _relative_price_ratio(
    target: SkuEvidenceSnapshot, peer: SkuEvidenceSnapshot
) -> float | None:
    left = _market_price(target)
    right = _market_price(peer)
    if left is None or right is None or left <= 0 or right <= 0:
        return None
    return abs(right / left - 1.0)


def _overlap_score(price_ratio: float | None) -> float | None:
    if price_ratio is None:
        return None
    return round(max(0.0, 1.0 - price_ratio), 6)


def _market_price(snapshot: SkuEvidenceSnapshot) -> float | None:
    value = _market_value(snapshot, "price_wavg", "weighted_price", "avg_price", "price_wavg_12m")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _market_value(snapshot: SkuEvidenceSnapshot, *keys: str) -> Any:
    return _recursive_find(snapshot.market, keys)


def _battlefields(snapshot: SkuEvidenceSnapshot) -> set[str]:
    result: set[str] = set()
    for row in snapshot.battlefields:
        for key in ("primary_battlefield_code", "battlefield_code"):
            value = row.get(key)
            if isinstance(value, str) and value:
                result.add(value)
        for key in (
            "secondary_battlefield_codes",
            "secondary_battlefield_codes_json",
            "opportunity_battlefield_codes",
            "opportunity_battlefield_codes_json",
            "user_observed_battlefield_codes",
        ):
            result.update(_string_set(row.get(key)))
    return result


def _battlefield_overlap(
    target: SkuEvidenceSnapshot, peer: SkuEvidenceSnapshot
) -> float:
    left = _battlefields(target)
    right = _battlefields(peer)
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 6)


def _tier_relation(
    target: SkuEvidenceSnapshot,
    peer: SkuEvidenceSnapshot,
    focus_dimensions: Sequence[str],
) -> tuple[str, list[str]]:
    left = _dimension_tiers(target)
    right = _dimension_tiers(peer)
    dimensions = set(focus_dimensions) if focus_dimensions else left.keys() & right.keys()
    comparable = sorted(code for code in dimensions if code in left and code in right)
    if not comparable:
        return "unknown", []
    diffs = [right[code] - left[code] for code in comparable]
    if all(diff == 0 for diff in diffs):
        return "same", comparable
    if all(diff <= 0 for diff in diffs) and any(diff < 0 for diff in diffs):
        return "lower", comparable
    if all(diff >= 0 for diff in diffs) and any(diff > 0 for diff in diffs):
        return "higher", comparable
    return "unknown", comparable


def _dimension_tiers(snapshot: SkuEvidenceSnapshot) -> dict[str, int]:
    payload = _recursive_find(
        snapshot.facts,
        ("dimension_tier_ranks", "dimension_tier_profile", "param_tiers"),
    )
    if not isinstance(payload, dict):
        return {}
    result: dict[str, int] = {}
    rank_map = {"unknown": 0, "base": 1, "enhanced": 2, "premium": 3, "flagship": 4}
    for code, value in payload.items():
        raw = value.get("tier_rank") if isinstance(value, dict) else value
        if isinstance(raw, bool):
            continue
        if isinstance(raw, (int, float)):
            result[str(code)] = int(raw)
        elif isinstance(raw, str) and raw.lower() in rank_map and raw.lower() != "unknown":
            result[str(code)] = rank_map[raw.lower()]
    return result


def _same_claim_contrast(
    target: SkuEvidenceSnapshot,
    peer: SkuEvidenceSnapshot,
    focus_claims: Sequence[str],
) -> dict[str, Any]:
    target_advertised = _fact_code_set(target, "advertised_claim_codes", "claim_codes")
    target_supported = _fact_code_set(target, "supported_claim_codes")
    peer_advertised = _fact_code_set(peer, "advertised_claim_codes", "claim_codes")
    peer_supported = _fact_code_set(peer, "supported_claim_codes")
    peer_contradicted = _fact_code_set(peer, "contradicted_claim_codes")
    relevant = target_advertised & target_supported & peer_advertised
    if focus_claims:
        relevant &= set(focus_claims)
    not_realized = sorted(relevant - peer_supported)
    contradicted = sorted(relevant & peer_contradicted)
    if not not_realized and not contradicted:
        return {}
    return {
        "same_advertised_claim_codes": sorted(relevant),
        "peer_not_realized_claim_codes": not_realized,
        "peer_contradicted_claim_codes": contradicted,
    }


def _fact_code_set(snapshot: SkuEvidenceSnapshot, *keys: str) -> set[str]:
    result: set[str] = set()
    for key in keys:
        result.update(_string_set(_recursive_find(snapshot.facts, (key,))))
        result.update(_string_set(_recursive_find(snapshot.comment_outcomes, (key,))))
    return result


def _common_market_scope(
    context: SellpointValueV5Context, target_code: str, peer_code: str
) -> tuple[int, int]:
    by_sku: dict[str, set[tuple[int, str]]] = {target_code: set(), peer_code: set()}
    for row in context.v4_context.market_cells:
        if row.sku_code not in by_sku or row.price_check_status != "ok" or row.promotion_suspect:
            continue
        by_sku[row.sku_code].add((row.period_week_index, row.platform_type))
    common = by_sku[target_code] & by_sku[peer_code]
    return len({week for week, _ in common}), len({platform for _, platform in common})


def _recursive_find(payload: Any, keys: Iterable[str]) -> Any:
    wanted = set(keys)
    queue = [payload]
    while queue:
        value = queue.pop(0)
        if isinstance(value, dict):
            for key in sorted(value):
                if key in wanted:
                    return value[key]
                nested = value[key]
                if isinstance(nested, (dict, list)):
                    queue.append(nested)
        elif isinstance(value, list):
            queue.extend(item for item in value if isinstance(item, (dict, list)))
    return None


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value} if value else set()
    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value if isinstance(item, str) and item}
    return set()


def _dedupe_refs(groups: Iterable[Sequence[Any]]) -> list[Any]:
    by_key = {}
    for group in groups:
        for ref in group:
            key = (ref.module_code, ref.record_type, ref.record_id, ref.result_hash)
            by_key[key] = ref
    return [by_key[key] for key in sorted(by_key)]


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "MIN_SYNTHETIC_DONORS",
    "OWN_CURVE_MIN_PLATFORMS",
    "OWN_CURVE_MIN_WEEKS",
    "SAME_BUDGET_RATIO",
    "SYNTHETIC_RECALL_RATIO",
    "build_v5_counterfactual_sets",
]
