from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.entities import (
    Core3CompetitorCandidate,
    Core3CompetitorResult,
    Core3EvidenceCard,
    Core3PipelineRun,
    Core3SkuFeatureProfile,
    Core3SkuMarketProfile,
)

CORE3_COMPETITOR_RULE_VERSION = "core3-mvp-0.2.0"
ROLE_ORDER = ["direct", "pressure", "benchmark_potential"]
ROLE_SCORE_KEYS = {
    "direct": "direct_slot_score",
    "pressure": "pressure_slot_score",
    "benchmark_potential": "benchmark_slot_score",
}
SUPERIOR_PARAM_CODES = [
    "oled_flag",
    "mini_led_flag",
    "native_refresh_rate_hz",
    "system_refresh_rate_hz",
    "refresh_rate_hz",
    "peak_brightness_nits",
    "instant_peak_brightness_nits",
    "sustained_brightness_nits",
    "sustained_peak_brightness_nits",
    "dimming_zones",
    "hdmi_2_1_ports",
    "eye_care_flag",
    "low_blue_light_flag",
    "flicker_free_flag",
]


@dataclass(frozen=True)
class Core3SkuSnapshot:
    sku_code: str
    category_code: str
    brand: str | None
    model_name: str | None
    series: str | None
    market: Core3SkuMarketProfile | None
    feature: Core3SkuFeatureProfile
    params: dict[str, dict[str, Any]]
    claims: dict[str, dict[str, Any]]
    topics: dict[str, dict[str, Any]]
    tasks: dict[str, dict[str, Any]]
    battlefields: dict[str, dict[str, Any]]
    evidence_ids: list[str]
    confidence: float


@dataclass(frozen=True)
class Core3CandidateCard:
    target: Core3SkuSnapshot
    candidate: Core3SkuSnapshot
    battlefield_code: str | None
    gate_status: str
    gate_reasons: list[str]
    component_scores: dict[str, float | None]
    slot_scores: dict[str, float]
    evidence_ids: list[str]
    evidence_categories: list[str]
    confidence: float


def generate_core3_competitors(
    db: Session,
    run: Core3PipelineRun,
    target_sku_codes: list[str],
) -> dict[str, int]:
    db.execute(delete(Core3EvidenceCard).where(Core3EvidenceCard.run_id == run.run_id))
    db.execute(delete(Core3CompetitorResult).where(Core3CompetitorResult.run_id == run.run_id))
    db.execute(delete(Core3CompetitorCandidate).where(Core3CompetitorCandidate.run_id == run.run_id))

    snapshots = _load_snapshots(db, run)
    target_codes = [code for code in target_sku_codes if code in snapshots]
    candidate_rows = 0
    result_rows = 0
    evidence_card_rows = 0
    for target_code in target_codes:
        target = snapshots[target_code]
        candidates = _score_candidates(target, snapshots)
        for candidate in candidates:
            db.add(
                Core3CompetitorCandidate(
                    run_id=run.run_id,
                    project_id=run.project_id,
                    category_code=run.category_code,
                    target_sku_code=target.sku_code,
                    candidate_sku_code=candidate.candidate.sku_code,
                    battlefield_code=candidate.battlefield_code,
                    gate_status=candidate.gate_status,
                    gate_reasons=candidate.gate_reasons,
                    component_scores=candidate.component_scores,
                    slot_scores=candidate.slot_scores,
                    evidence_ids=candidate.evidence_ids,
                    confidence=candidate.confidence,
                )
            )
            candidate_rows += 1

        for result in _select_role_results(target, candidates):
            row = Core3CompetitorResult(
                run_id=run.run_id,
                project_id=run.project_id,
                category_code=run.category_code,
                target_sku_code=target.sku_code,
                role=result["role"],
                competitor_sku_code=result["competitor_sku_code"],
                battlefield_code=result["battlefield_code"],
                score=result["score"],
                component_scores=result["component_scores"],
                reason=result["reason"],
                confidence=result["confidence"],
                confidence_level=result["confidence_level"],
                review_flag=result["review_flag"],
                insufficient_reasons=result["insufficient_reasons"],
                evidence_ids=result["evidence_ids"],
                evidence_card=result["evidence_card"],
                rule_version=CORE3_COMPETITOR_RULE_VERSION,
                asset_version=CORE3_COMPETITOR_RULE_VERSION,
            )
            db.add(row)
            db.flush()
            db.add(
                Core3EvidenceCard(
                    result_id=row.result_id,
                    run_id=run.run_id,
                    project_id=run.project_id,
                    target_sku_code=target.sku_code,
                    competitor_sku_code=result["competitor_sku_code"],
                    role=result["role"],
                    evidence_categories=result["evidence_card"].get("evidence_categories", []),
                    card_json=result["evidence_card"],
                    evidence_ids=result["evidence_ids"],
                )
            )
            result_rows += 1
            evidence_card_rows += 1
    db.flush()
    return {
        "competitor_candidate_count": candidate_rows,
        "competitor_result_count": result_rows,
        "evidence_card_count": evidence_card_rows,
    }


def _load_snapshots(db: Session, run: Core3PipelineRun) -> dict[str, Core3SkuSnapshot]:
    feature_rows = list(
        db.execute(
            select(Core3SkuFeatureProfile).where(Core3SkuFeatureProfile.run_id == run.run_id)
        ).scalars()
    )
    market_rows = {
        row.sku_code: row
        for row in db.execute(
            select(Core3SkuMarketProfile).where(Core3SkuMarketProfile.run_id == run.run_id)
        ).scalars()
    }
    snapshots: dict[str, Core3SkuSnapshot] = {}
    for feature in feature_rows:
        market = market_rows.get(feature.sku_code)
        evidence_ids = _unique([*(feature.feature_evidence_ids or []), *((market.evidence_ids or []) if market else [])])
        snapshots[feature.sku_code] = Core3SkuSnapshot(
            sku_code=feature.sku_code,
            category_code=feature.category_code,
            brand=market.brand if market else None,
            model_name=market.model_name if market else None,
            series=market.series if market else None,
            market=market,
            feature=feature,
            params=feature.standard_params or {},
            claims={item["claim_code"]: item for item in feature.claim_activations or []},
            topics={item["topic_code"]: item for item in feature.comment_topics or []},
            tasks={item["task_code"]: item for item in feature.task_scores or []},
            battlefields={item["battlefield_code"]: item for item in feature.battlefield_scores or []},
            evidence_ids=evidence_ids,
            confidence=min(feature.confidence or 0.0, market.confidence if market else 0.0),
        )
    return snapshots


def _score_candidates(
    target: Core3SkuSnapshot,
    snapshots: dict[str, Core3SkuSnapshot],
) -> list[Core3CandidateCard]:
    output: list[Core3CandidateCard] = []
    for candidate in snapshots.values():
        if candidate.sku_code == target.sku_code:
            continue
        if candidate.category_code != target.category_code:
            continue
        if not candidate.model_name and not candidate.brand:
            continue
        if _outside_hard_price_window(target, candidate):
            continue

        component_scores = _component_scores(target, candidate)
        battlefield_code = _best_shared_battlefield(target, candidate)
        gate_reasons = _gate_reasons(target, candidate, component_scores)
        gate_status = "eligible" if not _has_blocking_gate_reason(gate_reasons) else "insufficient"
        slot_scores = _slot_scores(component_scores)
        evidence_categories = _evidence_categories(target, candidate, component_scores)
        evidence_ids = _competitor_evidence_ids(target, candidate, evidence_categories)
        output.append(
            Core3CandidateCard(
                target=target,
                candidate=candidate,
                battlefield_code=battlefield_code,
                gate_status=gate_status,
                gate_reasons=gate_reasons,
                component_scores=component_scores,
                slot_scores=slot_scores,
                evidence_ids=evidence_ids,
                evidence_categories=evidence_categories,
                confidence=_candidate_confidence(slot_scores, evidence_categories, target, candidate),
            )
        )
    output.sort(key=lambda item: max(item.slot_scores.values() or [0.0]), reverse=True)
    return output[:200]


def _component_scores(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> dict[str, float | None]:
    price_similarity = _price_similarity(_price(target), _price(candidate))
    channel_overlap = _channel_overlap(target.market, candidate.market)
    size_similarity = _size_similarity(_param_number(target, "screen_size_inch"), _param_number(candidate, "screen_size_inch"))
    claim_similarity = _weighted_similarity(target.claims, candidate.claims, "activation_score")
    task_similarity = _weighted_similarity(target.tasks, candidate.tasks, "score")
    battlefield_similarity = _weighted_similarity(target.battlefields, candidate.battlefields, "final_score")
    price_advantage = _price_advantage(_price(target), _price(candidate))
    sales_strength = _sales_strength(target.market, candidate.market)
    price_drop_signal = _positive_or_zero(_market_value(candidate.market, "price_drop_rate_3m"))
    param_superiority = _param_superiority(target, candidate)
    claim_superiority = _claim_superiority(target, candidate)
    sales_or_amount_strength = _sales_or_amount_strength(candidate.market)
    premium_or_downshift = _price_premium_or_downshift(
        target,
        candidate,
        param_superiority=param_superiority,
        claim_superiority=claim_superiority,
    )
    return {
        "price_similarity": price_similarity,
        "channel_overlap": channel_overlap,
        "size_similarity": size_similarity,
        "claim_similarity": claim_similarity,
        "task_similarity": task_similarity,
        "battlefield_similarity": battlefield_similarity,
        "price_advantage": price_advantage,
        "sales_strength": sales_strength,
        "price_drop_signal": price_drop_signal,
        "param_superiority": param_superiority,
        "claim_superiority": claim_superiority,
        "sales_or_amount_strength": sales_or_amount_strength,
        "price_premium_or_downshift": premium_or_downshift,
    }


def _slot_scores(components: dict[str, float | None]) -> dict[str, float]:
    return {
        "direct_slot_score": _weighted_component_score(
            components,
            {
                "battlefield_similarity": 0.25,
                "claim_similarity": 0.20,
                "price_similarity": 0.15,
                "channel_overlap": 0.10,
                "size_similarity": 0.10,
                "task_similarity": 0.10,
                "sales_strength": 0.10,
            },
        ),
        "pressure_slot_score": _weighted_component_score(
            components,
            {
                "task_similarity": 0.25,
                "price_advantage": 0.25,
                "sales_strength": 0.20,
                "channel_overlap": 0.10,
                "battlefield_similarity": 0.10,
                "price_drop_signal": 0.10,
            },
        ),
        "benchmark_slot_score": _weighted_component_score(
            components,
            {
                "param_superiority": 0.25,
                "claim_superiority": 0.20,
                "battlefield_similarity": 0.20,
                "sales_or_amount_strength": 0.15,
                "price_premium_or_downshift": 0.15,
                "channel_overlap": 0.05,
            },
        ),
    }


def _select_role_results(target: Core3SkuSnapshot, candidates: list[Core3CandidateCard]) -> list[dict[str, Any]]:
    selected_skus: set[str] = set()
    selected_brands: list[str] = []
    results: list[dict[str, Any]] = []
    for role in ROLE_ORDER:
        role_candidates = [
            candidate
            for candidate in candidates
            if candidate.candidate.sku_code not in selected_skus and _passes_role_gate(candidate, role)
        ]
        role_candidates.sort(key=lambda item: item.slot_scores[ROLE_SCORE_KEYS[role]], reverse=True)
        selected = _brand_diversified_choice(role_candidates, selected_brands, role)
        if not selected:
            results.append(_empty_result(target, role, candidates))
            continue
        selected_skus.add(selected.candidate.sku_code)
        if selected.candidate.brand:
            selected_brands.append(selected.candidate.brand)
        results.append(_filled_result(selected, role))
    return results


def _passes_role_gate(card: Core3CandidateCard, role: str) -> bool:
    if card.gate_status != "eligible":
        return False
    c = card.component_scores
    if role == "direct":
        return (
            _score(c, "battlefield_similarity") >= 0.55
            and _score(c, "claim_similarity") >= 0.45
            and _score(c, "price_similarity") >= 0.45
            and len(card.evidence_categories) >= 3
        )
    if role == "pressure":
        return (
            _score(c, "task_similarity") >= 0.45
            and (_score(c, "price_advantage") >= 0.25 or _score(c, "sales_strength") >= 0.70)
            and ("price" in card.evidence_categories or "sales" in card.evidence_categories)
        )
    return (
        (_score(c, "param_superiority") >= 0.35 or _score(c, "claim_superiority") >= 0.35)
        and _score(c, "battlefield_similarity") >= 0.35
        and (_score(c, "price_premium_or_downshift") >= 0.50 or _score(c, "sales_or_amount_strength") >= 0.70)
    )


def _filled_result(card: Core3CandidateCard, role: str) -> dict[str, Any]:
    role_score = round(card.slot_scores[ROLE_SCORE_KEYS[role]], 4)
    confidence = _result_confidence(role_score, card.evidence_categories, card.target, card.candidate)
    confidence_level = _confidence_level(confidence, card.evidence_categories)
    insufficient_reasons = _result_insufficient_reasons(card, role, confidence_level)
    reason = _role_reason(card, role)
    evidence_card = _evidence_card(card, role, reason)
    return {
        "role": role,
        "competitor_sku_code": card.candidate.sku_code,
        "battlefield_code": card.battlefield_code,
        "score": role_score,
        "component_scores": card.component_scores,
        "reason": reason,
        "confidence": confidence,
        "confidence_level": confidence_level,
        "review_flag": confidence_level != "high" or bool(insufficient_reasons),
        "insufficient_reasons": insufficient_reasons,
        "evidence_ids": card.evidence_ids,
        "evidence_card": evidence_card,
    }


def _empty_result(
    target: Core3SkuSnapshot,
    role: str,
    candidates: list[Core3CandidateCard],
) -> dict[str, Any]:
    reasons = [f"weak_{role}"]
    if not candidates:
        reasons.append("insufficient_comparable_pool")
    if _price(target) is None:
        reasons.append("missing_target_price")
    if _market_value(target.market, "sales_volume_12m") is None:
        reasons.append("missing_target_sales")
    if candidates and max(len(candidate.evidence_categories) for candidate in candidates) < 3:
        reasons.append("less_than_three_evidence_categories")
    reason = f"{role} 未找到满足硬门槛的候选，需补充可比较 SKU 或关键量价/特征证据。"
    evidence_card = {
        "target": _snapshot_identity(target),
        "competitor": None,
        "role": role,
        "reason_summary": reason,
        "component_scores": {},
        "price_comparison": {},
        "sales_comparison": {},
        "channel_overlap": {},
        "param_comparison": {},
        "claim_comparison": {},
        "task_battlefield_similarity": {},
        "comment_evidence": {},
        "evidence_categories": [],
        "evidence_ids": [],
        "insufficient_reasons": _unique(reasons),
    }
    return {
        "role": role,
        "competitor_sku_code": None,
        "battlefield_code": None,
        "score": 0.0,
        "component_scores": {},
        "reason": reason,
        "confidence": 0.0,
        "confidence_level": "low",
        "review_flag": True,
        "insufficient_reasons": _unique(reasons),
        "evidence_ids": [],
        "evidence_card": evidence_card,
    }


def _result_confidence(
    slot_score: float,
    evidence_categories: list[str],
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
) -> float:
    evidence_coverage = min(1.0, len(evidence_categories) / 5)
    return round(
        slot_score * 0.45
        + evidence_coverage * 0.25
        + target.confidence * 0.15
        + candidate.confidence * 0.15,
        4,
    )


def _confidence_level(confidence: float, evidence_categories: list[str]) -> str:
    if confidence >= 0.78 and len(evidence_categories) >= 4:
        return "high"
    if confidence >= 0.55 and len(evidence_categories) >= 3:
        return "medium"
    return "low"


def _result_insufficient_reasons(card: Core3CandidateCard, role: str, confidence_level: str) -> list[str]:
    reasons = list(card.gate_reasons)
    if len(card.evidence_categories) < 3:
        reasons.append("less_than_three_evidence_categories")
    if confidence_level == "low":
        reasons.append(f"low_confidence_{role}")
    return _unique(reasons)


def _role_reason(card: Core3CandidateCard, role: str) -> str:
    c = card.component_scores
    battlefield = card.battlefield_code or "相近"
    if role == "direct":
        return (
            f"与目标 SKU 在 {battlefield} 战场重合，价格带接近，核心卖点重合度 "
            f"{_score(c, 'claim_similarity'):.2f}，渠道重合度 {_score(c, 'channel_overlap'):.2f}，适合作为正面对打竞品。"
        )
    if role == "pressure":
        pressure_signal = "价格优势" if _score(c, "price_advantage") >= 0.25 else "销量强势"
        return (
            f"与目标 SKU 面向相似用户任务，且候选具备{pressure_signal}，价格优势 "
            f"{_score(c, 'price_advantage'):.2f}、销量强度 {_score(c, 'sales_strength'):.2f}，会形成价格/销量挤压。"
        )
    superior = []
    if _score(c, "param_superiority") >= 0.35:
        superior.append("参数")
    if _score(c, "claim_superiority") >= 0.35:
        superior.append("卖点")
    superior_text = "、".join(superior) if superior else "部分高价值信号"
    return (
        f"候选在{superior_text}上强于目标，且价格/下探或销额信号 "
        f"{max(_score(c, 'price_premium_or_downshift'), _score(c, 'sales_or_amount_strength')):.2f}，可作为高端标杆或潜在下探竞品。"
    )


def _evidence_card(card: Core3CandidateCard, role: str, reason: str) -> dict[str, Any]:
    return {
        "target": _snapshot_identity(card.target),
        "competitor": _snapshot_identity(card.candidate),
        "role": role,
        "reason_summary": reason,
        "component_scores": card.component_scores,
        "price_comparison": {
            "target_price": _price(card.target),
            "competitor_price": _price(card.candidate),
            "price_similarity": card.component_scores.get("price_similarity"),
            "price_advantage": card.component_scores.get("price_advantage"),
        },
        "sales_comparison": {
            "target_sales_volume_12m": _market_value(card.target.market, "sales_volume_12m"),
            "competitor_sales_volume_12m": _market_value(card.candidate.market, "sales_volume_12m"),
            "target_sales_percentile": _market_value(card.target.market, "sales_percentile"),
            "competitor_sales_percentile": _market_value(card.candidate.market, "sales_percentile"),
            "sales_strength": card.component_scores.get("sales_strength"),
        },
        "channel_overlap": {
            "target_channel_share": _market_value(card.target.market, "channel_share") or {},
            "competitor_channel_share": _market_value(card.candidate.market, "channel_share") or {},
            "score": card.component_scores.get("channel_overlap"),
        },
        "param_comparison": _param_comparison(card.target, card.candidate),
        "claim_comparison": _claim_comparison(card.target, card.candidate),
        "task_battlefield_similarity": {
            "task_similarity": card.component_scores.get("task_similarity"),
            "battlefield_similarity": card.component_scores.get("battlefield_similarity"),
            "shared_battlefield_code": card.battlefield_code,
            "target_tasks": sorted(card.target.tasks),
            "competitor_tasks": sorted(card.candidate.tasks),
            "target_battlefields": sorted(card.target.battlefields),
            "competitor_battlefields": sorted(card.candidate.battlefields),
        },
        "battlefield_evidence": _battlefield_evidence(card),
        "comment_evidence": {
            "target_topics": sorted(card.target.topics),
            "competitor_topics": sorted(card.candidate.topics),
        },
        "evidence_categories": card.evidence_categories,
        "evidence_ids": card.evidence_ids,
        "gate_reasons": card.gate_reasons,
    }


def _battlefield_evidence(card: Core3CandidateCard) -> dict[str, Any]:
    shared_code = card.battlefield_code
    return {
        "shared_battlefield_code": shared_code,
        "selection_method": (
            "先分别计算目标型号和候选型号的价值战场强度，再在双方共同战场中选择综合强度最高的战场。"
        ),
        "target_selected_battlefield": _battlefield_row_with_rank(card.target, shared_code),
        "competitor_selected_battlefield": _battlefield_row_with_rank(card.candidate, shared_code),
        "target_top_battlefields": _ranked_battlefields(card.target, limit=5),
        "competitor_top_battlefields": _ranked_battlefields(card.candidate, limit=5),
    }


def _battlefield_row_with_rank(snapshot: Core3SkuSnapshot, battlefield_code: str | None) -> dict[str, Any] | None:
    if not battlefield_code or battlefield_code not in snapshot.battlefields:
        return None
    rows = _ranked_battlefields(snapshot, limit=len(snapshot.battlefields))
    for index, row in enumerate(rows, start=1):
        if row["battlefield_code"] == battlefield_code:
            return {
                **row,
                "rank": index,
                "total": len(rows),
                "is_main": row.get("relation_level") == "main",
            }
    return None


def _ranked_battlefields(snapshot: Core3SkuSnapshot, limit: int) -> list[dict[str, Any]]:
    rows = sorted(
        snapshot.battlefields.values(),
        key=lambda item: (-(item.get("final_score") or item.get("score") or 0.0), item.get("battlefield_code") or ""),
    )
    return [_battlefield_public_row(item) for item in rows[:limit]]


def _battlefield_public_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "battlefield_code": row.get("battlefield_code"),
        "battlefield_name": row.get("battlefield_name"),
        "final_score": row.get("final_score") or row.get("score"),
        "relation_level": row.get("relation_level"),
        "component_scores": row.get("component_scores") or {},
        "confidence": row.get("confidence"),
    }


def _snapshot_identity(snapshot: Core3SkuSnapshot) -> dict[str, Any]:
    return {
        "sku_code": snapshot.sku_code,
        "brand": snapshot.brand,
        "model_name": snapshot.model_name,
        "series": snapshot.series,
        "price_wavg_12m": _price(snapshot),
        "sales_volume_12m": _market_value(snapshot.market, "sales_volume_12m"),
    }


def _param_comparison(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> dict[str, Any]:
    codes = _unique(
        [
            "screen_size_inch",
            "mini_led_flag",
            "oled_flag",
            "native_refresh_rate_hz",
            "system_refresh_rate_hz",
            "refresh_rate_hz",
            "peak_brightness_nits",
            "dimming_zones",
            "hdmi_2_1_ports",
        ]
    )
    return {
        code: {
            "target": _param_value(target, code),
            "competitor": _param_value(candidate, code),
        }
        for code in codes
        if _param_value(target, code) is not None or _param_value(candidate, code) is not None
    }


def _claim_comparison(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> dict[str, Any]:
    codes = sorted(set(target.claims) | set(candidate.claims))
    return {
        code: {
            "target_score": _claim_score(target, code),
            "competitor_score": _claim_score(candidate, code),
        }
        for code in codes
    }


def _gate_reasons(
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
    components: dict[str, float | None],
) -> list[str]:
    reasons: list[str] = []
    if _price(target) is None:
        reasons.append("missing_target_price")
    if _price(candidate) is None:
        reasons.append("missing_candidate_price")
    if _market_value(target.market, "sales_volume_12m") in {None, 0}:
        reasons.append("missing_target_sales")
    if _market_value(candidate.market, "sales_volume_12m") in {None, 0}:
        reasons.append("missing_candidate_sales")
    target_size = _param_number(target, "screen_size_inch")
    candidate_size = _param_number(candidate, "screen_size_inch")
    if target_size is not None and candidate_size is not None and abs(target_size - candidate_size) > 15:
        reasons.append("outside_size_window")
    if components.get("battlefield_similarity") in {None, 0} and _score(components, "task_similarity") < 0.45:
        reasons.append("no_shared_battlefield")
    if components.get("claim_similarity") is None:
        reasons.append("insufficient_claim_signal")
    if components.get("size_similarity") is None:
        reasons.append("missing_size_signal")
    return _unique(reasons)


def _has_blocking_gate_reason(reasons: list[str]) -> bool:
    blocking = {
        "missing_target_price",
        "missing_candidate_price",
        "missing_target_sales",
        "missing_candidate_sales",
        "outside_size_window",
        "no_shared_battlefield",
        "insufficient_claim_signal",
    }
    return any(reason in blocking for reason in reasons)


def _outside_hard_price_window(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> bool:
    target_price = _price(target)
    candidate_price = _price(candidate)
    if target_price is None or candidate_price is None:
        return False
    return candidate_price < target_price * 0.45 or candidate_price > target_price * 1.80


def _brand_diversified_choice(
    candidates: list[Core3CandidateCard],
    selected_brands: list[str],
    role: str,
) -> Core3CandidateCard | None:
    if not candidates:
        return None
    best = candidates[0]
    if not selected_brands or selected_brands.count(best.candidate.brand or "") < 2:
        return best
    score_key = ROLE_SCORE_KEYS[role]
    for alternative in candidates[1:]:
        if alternative.candidate.brand in selected_brands:
            continue
        if best.slot_scores[score_key] - alternative.slot_scores[score_key] <= 0.08:
            return alternative
    return best


def _best_shared_battlefield(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> str | None:
    shared = set(target.battlefields) & set(candidate.battlefields)
    if not shared:
        return next(iter(target.battlefields), None)
    return max(
        shared,
        key=lambda code: (target.battlefields[code].get("final_score") or 0)
        + (candidate.battlefields[code].get("final_score") or 0),
    )


def _price_similarity(target_price: float | None, candidate_price: float | None) -> float | None:
    if target_price is None or candidate_price is None or target_price <= 0:
        return None
    return round(max(0.0, 1.0 - abs(candidate_price - target_price) / (target_price * 0.35)), 4)


def _channel_overlap(target_market: Core3SkuMarketProfile | None, candidate_market: Core3SkuMarketProfile | None) -> float | None:
    target_share = _market_value(target_market, "channel_share") or {}
    candidate_share = _market_value(candidate_market, "channel_share") or {}
    if not target_share or not candidate_share:
        return None
    return round(sum(min(float(target_share.get(key, 0.0)), float(candidate_share.get(key, 0.0))) for key in set(target_share) | set(candidate_share)), 4)


def _size_similarity(target_size: float | None, candidate_size: float | None) -> float | None:
    if target_size is None or candidate_size is None:
        return None
    return round(max(0.0, 1.0 - abs(candidate_size - target_size) / 15.0), 4)


def _weighted_similarity(
    target_rows: dict[str, dict[str, Any]],
    candidate_rows: dict[str, dict[str, Any]],
    score_key: str,
) -> float | None:
    if not target_rows or not candidate_rows:
        return None
    denominator = sum(float(item.get(score_key) or item.get("score") or 0.0) for item in target_rows.values())
    if denominator <= 0:
        return None
    overlap = 0.0
    for code, target_row in target_rows.items():
        candidate_row = candidate_rows.get(code)
        if not candidate_row:
            continue
        target_score = float(target_row.get(score_key) or target_row.get("score") or 0.0)
        candidate_score = float(candidate_row.get(score_key) or candidate_row.get("score") or 0.0)
        overlap += min(target_score, candidate_score)
    return round(min(1.0, overlap / denominator), 4)


def _price_advantage(target_price: float | None, candidate_price: float | None) -> float | None:
    if target_price is None or candidate_price is None or target_price <= 0:
        return None
    if candidate_price >= target_price:
        return 0.0
    return round(min(1.0, (target_price - candidate_price) / (target_price * 0.25)), 4)


def _sales_strength(target_market: Core3SkuMarketProfile | None, candidate_market: Core3SkuMarketProfile | None) -> float | None:
    candidate_percentile = _market_value(candidate_market, "sales_percentile")
    candidate_volume = _market_value(candidate_market, "sales_volume_12m")
    target_volume = _market_value(target_market, "sales_volume_12m")
    scores = []
    if isinstance(candidate_percentile, int | float):
        scores.append(float(candidate_percentile))
    if isinstance(candidate_volume, int | float) and isinstance(target_volume, int | float) and target_volume > 0:
        scores.append(min(1.0, float(candidate_volume) / float(target_volume)))
    if not scores:
        return None
    return round(max(scores), 4)


def _param_superiority(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> float | None:
    scores: list[float] = []
    for code in SUPERIOR_PARAM_CODES:
        target_value = _param_value(target, code)
        candidate_value = _param_value(candidate, code)
        if target_value is None or candidate_value is None:
            continue
        scores.append(_superiority_score(target_value, candidate_value, inverse=code == "input_lag_ms"))
    if not scores:
        return None
    return round(sum(scores) / len(scores), 4)


def _superiority_score(target_value: Any, candidate_value: Any, *, inverse: bool = False) -> float:
    if isinstance(target_value, bool) and isinstance(candidate_value, bool):
        if candidate_value == target_value:
            return 0.0
        return 1.0 if candidate_value and not target_value else 0.0
    if isinstance(target_value, int | float) and isinstance(candidate_value, int | float):
        if target_value <= 0:
            return 1.0 if candidate_value > 0 else 0.0
        if inverse:
            return round(max(0.0, min(1.0, (float(target_value) - float(candidate_value)) / float(target_value))), 4)
        return round(max(0.0, min(1.0, (float(candidate_value) - float(target_value)) / float(target_value))), 4)
    return 0.0


def _claim_superiority(target: Core3SkuSnapshot, candidate: Core3SkuSnapshot) -> float | None:
    candidate_scores = {code: _claim_score(candidate, code) for code in candidate.claims}
    if not candidate_scores:
        return None
    superior_sum = 0.0
    total_candidate = 0.0
    for code, candidate_score in candidate_scores.items():
        total_candidate += candidate_score
        superior_sum += max(0.0, candidate_score - _claim_score(target, code))
    if total_candidate <= 0:
        return None
    return round(min(1.0, superior_sum / total_candidate), 4)


def _sales_or_amount_strength(candidate_market: Core3SkuMarketProfile | None) -> float | None:
    values = [
        _market_value(candidate_market, "sales_percentile"),
        _market_value(candidate_market, "sales_amount_percentile"),
    ]
    known = [float(value) for value in values if isinstance(value, int | float)]
    if not known:
        return None
    return round(max(known), 4)


def _price_premium_or_downshift(
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
    *,
    param_superiority: float | None,
    claim_superiority: float | None,
) -> float | None:
    target_price = _price(target)
    candidate_price = _price(candidate)
    if target_price is None or candidate_price is None or target_price <= 0:
        return None
    superiority = max(param_superiority or 0.0, claim_superiority or 0.0)
    if candidate_price >= target_price * 1.15 and superiority > 0:
        return round(min(1.0, 0.5 + superiority * 0.5), 4)
    price_drop = _market_value(candidate.market, "price_drop_rate_3m")
    if isinstance(price_drop, int | float) and price_drop > 0:
        previous_price = candidate_price / max(0.01, 1.0 - float(price_drop))
        if previous_price > target_price * 1.20 and target_price * 0.80 <= candidate_price <= target_price * 1.20:
            return round(min(1.0, 0.5 + float(price_drop)), 4)
    return 0.0


def _weighted_component_score(components: dict[str, float | None], weights: dict[str, float]) -> float:
    known_weight = 0.0
    weighted = 0.0
    for key, weight in weights.items():
        value = components.get(key)
        if value is None:
            continue
        known_weight += weight
        weighted += weight * max(0.0, min(1.0, float(value)))
    if known_weight <= 0:
        return 0.0
    return round(weighted / known_weight, 4)


def _candidate_confidence(
    slot_scores: dict[str, float],
    evidence_categories: list[str],
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
) -> float:
    evidence_score = min(1.0, len(evidence_categories) / 5)
    return round(max(slot_scores.values() or [0.0]) * 0.60 + evidence_score * 0.20 + target.confidence * 0.10 + candidate.confidence * 0.10, 4)


def _evidence_categories(
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
    components: dict[str, float | None],
) -> list[str]:
    categories: list[str] = []
    if components.get("price_similarity") is not None or components.get("price_advantage") is not None:
        categories.append("price")
    if components.get("sales_strength") is not None or components.get("sales_or_amount_strength") is not None:
        categories.append("sales")
    if components.get("channel_overlap") is not None:
        categories.append("channel")
    if components.get("size_similarity") is not None or components.get("param_superiority") is not None:
        categories.append("param")
    if components.get("claim_similarity") is not None or components.get("claim_superiority") is not None:
        categories.append("claim")
    if components.get("task_similarity") is not None or components.get("battlefield_similarity") is not None:
        categories.append("task_battlefield")
    if target.topics or candidate.topics:
        categories.append("comment")
    return _unique(categories)


def _competitor_evidence_ids(
    target: Core3SkuSnapshot,
    candidate: Core3SkuSnapshot,
    evidence_categories: list[str],
) -> list[str]:
    evidence_ids: list[str] = []
    if any(category in evidence_categories for category in ["price", "sales", "channel"]):
        if target.market:
            evidence_ids.extend(target.market.evidence_ids or [])
        if candidate.market:
            evidence_ids.extend(candidate.market.evidence_ids or [])
    if "param" in evidence_categories:
        evidence_ids.extend(_param_evidence_ids(target))
        evidence_ids.extend(_param_evidence_ids(candidate))
    if "claim" in evidence_categories:
        evidence_ids.extend(_claim_evidence_ids(target))
        evidence_ids.extend(_claim_evidence_ids(candidate))
    if "comment" in evidence_categories:
        evidence_ids.extend(_topic_evidence_ids(target))
        evidence_ids.extend(_topic_evidence_ids(candidate))
    if "task_battlefield" in evidence_categories:
        evidence_ids.extend(_derived_evidence_ids(target))
        evidence_ids.extend(_derived_evidence_ids(candidate))
    return _unique(evidence_ids)


def _param_evidence_ids(snapshot: Core3SkuSnapshot) -> list[str]:
    return _unique([evidence_id for item in snapshot.params.values() for evidence_id in item.get("evidence_ids", [])])


def _claim_evidence_ids(snapshot: Core3SkuSnapshot) -> list[str]:
    return _unique([evidence_id for item in snapshot.claims.values() for evidence_id in item.get("evidence_ids", [])])


def _topic_evidence_ids(snapshot: Core3SkuSnapshot) -> list[str]:
    return _unique([evidence_id for item in snapshot.topics.values() for evidence_id in item.get("evidence_ids", [])])


def _derived_evidence_ids(snapshot: Core3SkuSnapshot) -> list[str]:
    return _unique(
        [
            evidence_id
            for rows in [snapshot.tasks.values(), snapshot.battlefields.values()]
            for item in rows
            for evidence_id in item.get("evidence_ids", [])
        ]
    )


def _price(snapshot: Core3SkuSnapshot) -> float | None:
    return _market_value(snapshot.market, "price_wavg_12m")


def _market_value(market: Core3SkuMarketProfile | None, name: str) -> Any:
    if market is None:
        return None
    return getattr(market, name, None)


def _param_value(snapshot: Core3SkuSnapshot, param_code: str) -> Any:
    if param_code not in snapshot.params:
        return None
    return snapshot.params[param_code].get("normalized_value")


def _param_number(snapshot: Core3SkuSnapshot, param_code: str) -> float | None:
    value = _param_value(snapshot, param_code)
    if isinstance(value, int | float):
        return float(value)
    return None


def _claim_score(snapshot: Core3SkuSnapshot, claim_code: str) -> float:
    if claim_code not in snapshot.claims:
        return 0.0
    return float(snapshot.claims[claim_code].get("activation_score") or 0.0)


def _positive_or_zero(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return round(max(0.0, float(value)), 4)


def _score(components: dict[str, float | None], key: str) -> float:
    value = components.get(key)
    if value is None:
        return 0.0
    return float(value)


def _unique(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value))
