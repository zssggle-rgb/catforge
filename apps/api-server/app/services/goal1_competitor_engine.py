from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import CategoryProject, SkuCompetitorResult
from app.services.goal1_analysis_service import ASSET_VERSION, SkuFeatureBundle


def generate_goal1_competitors(
    db: Session,
    *,
    project: CategoryProject,
    bundles: dict[str, SkuFeatureBundle],
    competitor_rule: dict[str, Any],
    target_sku_code: str | None = None,
) -> int:
    target_codes = [target_sku_code] if target_sku_code else list(bundles)
    created = 0
    for code in target_codes:
        if not code or code not in bundles:
            continue
        target = bundles[code]
        candidates = _candidate_pool(target, bundles, competitor_rule.get("candidate_filters") or {})
        scored = [_score_candidate(target, candidate, competitor_rule) for candidate in candidates]
        scored = [item for item in scored if item["competitor_type"]]
        scored.sort(key=lambda item: item["score"], reverse=True)
        for rank, item in enumerate(scored, start=1):
            db.add(
                SkuCompetitorResult(
                    project_id=project.project_id,
                    category_code=project.category_code,
                    target_sku_code=target.sku_code,
                    competitor_sku_code=item["candidate"].sku_code,
                    battlefield_code=item["battlefield_code"],
                    competitor_type=item["competitor_type"],
                    rank=rank,
                    score=round(item["score"] * 100, 2),
                    component_scores={key: round(value, 4) for key, value in item["component_scores"].items()},
                    evidence_ids=item["evidence_ids"],
                    evidence_card=item["evidence_card"],
                    confidence=item["confidence"],
                    rule_version=str(competitor_rule["version"]),
                    asset_version=ASSET_VERSION,
                    review_status=item["review_status"],
                    insufficient_reasons=item["insufficient_reasons"],
                    status="accepted",
                )
            )
            created += 1
    db.flush()
    return created


def _candidate_pool(
    target: SkuFeatureBundle,
    bundles: dict[str, SkuFeatureBundle],
    filters: dict[str, Any],
) -> list[SkuFeatureBundle]:
    max_candidates = int(filters.get("max_candidates", 200))
    min_sales = float(filters.get("min_sales_volume", 0))
    screen_window = float(filters.get("screen_size_window_inch", 999))
    output: list[SkuFeatureBundle] = []
    for candidate in bundles.values():
        if filters.get("exclude_same_sku", True) and candidate.sku_code == target.sku_code:
            continue
        if filters.get("same_category", True) and candidate.category != target.category:
            continue
        if filters.get("channel_overlap_required") and candidate.channel != target.channel:
            continue
        if (candidate.market.get("sales_volume") or 0) < min_sales:
            continue
        if abs((candidate.params.get("screen_size_inch") or 0) - (target.params.get("screen_size_inch") or 0)) > screen_window:
            continue
        output.append(candidate)
    return output[:max_candidates]


def _score_candidate(
    target: SkuFeatureBundle, candidate: SkuFeatureBundle, competitor_rule: dict[str, Any]
) -> dict[str, Any]:
    weights = competitor_rule.get("component_weights") or {}
    component_scores = {
        "price_similarity": _price_similarity(target, candidate, competitor_rule),
        "channel_overlap": 1.0 if target.channel == candidate.channel else 0.55,
        "core_param_similarity": _core_param_similarity(target, candidate),
        "standard_claim_similarity": _claim_similarity(target, candidate),
        "task_similarity": _weighted_code_similarity(target.task_results, candidate.task_results),
        "battlefield_similarity": _weighted_code_similarity(target.battlefield_results, candidate.battlefield_results),
        "sales_strength": _sales_strength(target, candidate),
        "price_trend_risk": 0.0,
    }
    score = sum(component_scores.get(name, 0.0) * float(weight) for name, weight in weights.items())
    score = min(1.0, max(0.0, score))
    competitor_type = _classify_competitor(target, candidate, score, component_scores, competitor_rule)
    if competitor_type == "benchmark":
        benchmark_min = _min_score(competitor_rule, "benchmark")
        if benchmark_min:
            score = max(score, benchmark_min + 0.01)
    evidence_ids = _competitor_evidence(target, candidate)
    insufficient_reasons = []
    if len(evidence_ids) < 3:
        insufficient_reasons.append("insufficient_evidence")
    confidence = 0.82 if not insufficient_reasons else 0.35
    return {
        "candidate": candidate,
        "competitor_type": competitor_type,
        "score": score,
        "component_scores": component_scores,
        "battlefield_code": _best_battlefield(target, candidate),
        "evidence_ids": evidence_ids,
        "evidence_card": _evidence_card(target, candidate, component_scores),
        "confidence": confidence,
        "review_status": "auto_pass" if confidence >= 0.7 else "needs_review",
        "insufficient_reasons": insufficient_reasons,
    }


def _classify_competitor(
    target: SkuFeatureBundle,
    candidate: SkuFeatureBundle,
    score: float,
    components: dict[str, float],
    competitor_rule: dict[str, Any],
) -> str | None:
    type_rules = competitor_rule.get("type_rules") or []
    by_type = {item["competitor_type"]: item for item in type_rules}
    direct = by_type.get("direct")
    if direct and _passes_requirements(score, components, direct.get("requirements") or {}, direct["min_score"]):
        return "direct"
    benchmark = by_type.get("benchmark")
    if benchmark and _is_benchmark_candidate(target, candidate, score, components, benchmark):
        return "benchmark"
    substitute = by_type.get("substitute")
    if substitute and _passes_requirements(score, components, substitute.get("requirements") or {}, substitute["min_score"]):
        return "substitute"
    potential = by_type.get("potential")
    if potential and _passes_requirements(score, components, potential.get("requirements") or {}, potential["min_score"]):
        return "potential"
    return None


def _passes_requirements(
    score: float, components: dict[str, float], requirements: dict[str, Any], min_score: float
) -> bool:
    if score < float(min_score):
        return False
    for key, threshold in requirements.items():
        if key == "stronger_than_target_any":
            continue
        if key.endswith("_max"):
            component_name = key.removesuffix("_max")
            if components.get(component_name, 0.0) > float(threshold):
                return False
            continue
        if components.get(key, 0.0) < float(threshold):
            return False
    return True


def _is_benchmark_candidate(
    target: SkuFeatureBundle,
    candidate: SkuFeatureBundle,
    score: float,
    components: dict[str, float],
    rule: dict[str, Any],
) -> bool:
    requirements = rule.get("requirements") or {}
    stronger_fields = requirements.get("stronger_than_target_any") or []
    stronger = any(_value(candidate, field) > _value(target, field) for field in stronger_fields)
    premium_display = bool(candidate.params.get("oled_flag")) or bool(candidate.params.get("mini_led_flag"))
    battlefield_fit = components.get("battlefield_similarity", 0.0) >= 0.55
    regular_pass = _passes_requirements(score, components, requirements, rule["min_score"])
    premium_benchmark_pass = stronger and premium_display and battlefield_fit and score >= 0.5
    return regular_pass or premium_benchmark_pass


def _price_similarity(
    target: SkuFeatureBundle, candidate: SkuFeatureBundle, competitor_rule: dict[str, Any]
) -> float:
    target_price = target.market.get("avg_price") or 0
    candidate_price = candidate.market.get("avg_price") or 0
    if target_price <= 0 or candidate_price <= 0:
        return 0.0
    window = float((competitor_rule.get("candidate_filters") or {}).get("price_window_pct", 0.25))
    distance = abs(candidate_price - target_price) / max(1.0, target_price * window)
    return round(1 / (1 + distance), 4)


def _core_param_similarity(target: SkuFeatureBundle, candidate: SkuFeatureBundle) -> float:
    target_params = target.params
    candidate_params = candidate.params
    screen = 1 - min(1, abs(_value(candidate, "screen_size_inch") - _value(target, "screen_size_inch")) / 15)
    refresh = min(1.0, (_value(candidate, "refresh_rate_hz") or 0) / max(1.0, _value(target, "refresh_rate_hz")))
    hdmi = min(1.0, (_value(candidate, "hdmi_2_1_ports") or 0) / max(1.0, _value(target, "hdmi_2_1_ports")))
    display = 1.0 if candidate_params.get("mini_led_flag") == target_params.get("mini_led_flag") else 0.55
    if candidate_params.get("oled_flag"):
        display = max(display, 0.9)
    brightness = min(1.0, (_value(candidate, "peak_brightness_nits") or 0) / max(1.0, _value(target, "peak_brightness_nits")))
    zones = min(1.0, (_value(candidate, "dimming_zones") or 0) / max(1.0, _value(target, "dimming_zones")))
    if candidate_params.get("oled_flag"):
        brightness = max(brightness, 0.7)
        zones = max(zones, 0.7)
    return round((screen + refresh + hdmi + display + brightness + zones) / 6, 4)


def _claim_similarity(target: SkuFeatureBundle, candidate: SkuFeatureBundle) -> float:
    target_claims = set(target.claim_results)
    candidate_claims = set(candidate.claim_results)
    if not target_claims:
        return 0.0
    overlap = len(target_claims & candidate_claims) / len(target_claims)
    if candidate.params.get("oled_flag"):
        overlap = max(overlap, 0.75)
    return round(min(1.0, overlap), 4)


def _weighted_code_similarity(target_rows: dict[str, dict[str, Any]], candidate_rows: dict[str, dict[str, Any]]) -> float:
    if not target_rows or not candidate_rows:
        return 0.0
    scores: list[float] = []
    for code, target_result in target_rows.items():
        candidate_result = candidate_rows.get(code)
        if not candidate_result:
            scores.append(0.0)
            continue
        target_score = float(target_result.get("score") or 0)
        candidate_score = float(candidate_result.get("score") or 0)
        scores.append(min(1.0, candidate_score / max(1.0, target_score)))
    denominator = max(1, min(len(target_rows), len(candidate_rows)))
    return round(min(1.0, sum(scores) / denominator), 4)


def _sales_strength(target: SkuFeatureBundle, candidate: SkuFeatureBundle) -> float:
    target_sales = target.market.get("sales_volume") or 0
    candidate_sales = candidate.market.get("sales_volume") or 0
    return round(min(1.0, candidate_sales / max(1.0, target_sales)), 4)


def _value(bundle: SkuFeatureBundle, field: str) -> float:
    if field in bundle.params:
        value = bundle.params.get(field)
    else:
        value = bundle.market.get(field)
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _best_battlefield(target: SkuFeatureBundle, candidate: SkuFeatureBundle) -> str | None:
    shared = [code for code in target.battlefield_results if code in candidate.battlefield_results]
    if shared:
        shared.sort(key=lambda code: candidate.battlefield_results[code].get("score", 0), reverse=True)
        return shared[0]
    if target.battlefield_results:
        return max(target.battlefield_results, key=lambda code: target.battlefield_results[code].get("score", 0))
    return None


def _competitor_evidence(target: SkuFeatureBundle, candidate: SkuFeatureBundle) -> list[str]:
    features = [
        "market.avg_price",
        "market.sales_volume",
        "param.screen_size_inch",
        "param.mini_led_flag",
        "param.oled_flag",
        "param.refresh_rate_hz",
        "param.peak_brightness_nits",
        "param.dimming_zones",
        "param.hdmi_2_1_ports",
        "claim_text",
    ]
    evidence: list[str] = []
    for bundle in [target, candidate]:
        for feature in features:
            evidence.extend(bundle.evidence_by_feature.get(feature, []))
        for claim_code in bundle.claim_results:
            evidence.extend(bundle.evidence_by_feature.get(f"claim.{claim_code}", []))
        for task_code in bundle.task_results:
            evidence.extend(bundle.evidence_by_feature.get(f"task.{task_code}", []))
        for battlefield_code in bundle.battlefield_results:
            evidence.extend(bundle.evidence_by_feature.get(f"battlefield.{battlefield_code}", []))
    return _unique(evidence)


def _evidence_card(
    target: SkuFeatureBundle, candidate: SkuFeatureBundle, components: dict[str, float]
) -> dict[str, Any]:
    return {
        "target": {
            "sku_code": target.sku_code,
            "brand": target.brand,
            "model": target.model,
            "avg_price": target.market.get("avg_price"),
            "sales_volume": target.market.get("sales_volume"),
            "screen_size_inch": target.params.get("screen_size_inch"),
            "claims": sorted(target.claim_results),
            "tasks": sorted(target.task_results),
            "battlefields": sorted(target.battlefield_results),
        },
        "candidate": {
            "sku_code": candidate.sku_code,
            "brand": candidate.brand,
            "model": candidate.model,
            "avg_price": candidate.market.get("avg_price"),
            "sales_volume": candidate.market.get("sales_volume"),
            "screen_size_inch": candidate.params.get("screen_size_inch"),
            "claims": sorted(candidate.claim_results),
            "tasks": sorted(candidate.task_results),
            "battlefields": sorted(candidate.battlefield_results),
        },
        "component_scores": components,
    }


def _min_score(competitor_rule: dict[str, Any], competitor_type: str) -> float | None:
    for item in competitor_rule.get("type_rules") or []:
        if item.get("competitor_type") == competitor_type:
            return float(item["min_score"])
    return None


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output
