from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.entities import Core3PipelineRun, Core3SkuFeatureProfile
from app.schemas.core3_mvp import Core3SeedCatalog
from app.services.core3_mvp.competitor_engine import generate_core3_competitors
from app.services.core3_mvp.data_access import load_project_input
from app.services.core3_mvp.evidence_graph import get_or_create_evidence
from app.services.core3_mvp.extraction import (
    ClaimHit,
    CommentTopicHit,
    ParamExtraction,
    discover_candidate_claims,
    discover_candidate_comment_topics,
    discover_candidate_param_aliases,
    extract_claim_hits,
    extract_comment_topic_hits,
    extract_param_values,
    profile_param_fields,
)
from app.services.core3_mvp.market_profile import build_market_profiles
from app.services.core3_mvp.report_service import finish_run
from app.services.core3_mvp.seed_loader import load_core3_seed
from app.services.core3_mvp.semantic_profile import derive_semantic_profiles


def run_feature_extraction(
    db: Session,
    run_id: str,
    *,
    seed: Core3SeedCatalog | None = None,
) -> list[Core3SkuFeatureProfile]:
    run = db.get(Core3PipelineRun, run_id)
    if not run:
        raise ValueError("Core3 run 不存在")
    bundle = load_project_input(db, run.project_id)
    seed = seed or load_core3_seed()
    target_sku_codes = _target_sku_codes(run, bundle)
    if not target_sku_codes:
        finish_run(
            db,
            run_id,
            status="completed_empty",
            counts={**(run.counts or {}), "feature_profile_count": 0},
            diagnostics={"feature_pipeline": {"target_sku_codes": [], "reason": "no_target_sku"}},
        )
        return []

    profile_sku_codes = _profile_sku_codes(run, bundle, target_sku_codes)
    market_profiles = build_market_profiles(db, run, bundle, profile_sku_codes)
    market_by_sku = {row.sku_code: row for row in market_profiles}
    field_profiles = profile_param_fields(bundle, seed)
    param_extractions, param_conflicts = extract_param_values(bundle, seed)
    claim_hits = extract_claim_hits(bundle, seed)
    topic_hits = extract_comment_topic_hits(bundle, seed)
    diagnostics = {
        "field_mappings": [item.model_dump() for item in field_profiles],
        "param_conflicts": param_conflicts,
        "candidate_param_aliases": [
            item.model_dump() for item in discover_candidate_param_aliases(field_profiles)
        ],
        "candidate_claims": [
            item.model_dump() for item in discover_candidate_claims(bundle, seed, claim_hits)
        ],
        "candidate_comment_topics": [
            item.model_dump() for item in discover_candidate_comment_topics(bundle, seed, topic_hits)
        ],
        "missing_signals": [],
    }

    param_rows = _persist_param_evidence(db, run, param_extractions)
    claim_rows = _persist_claim_evidence(db, run, claim_hits)
    topic_rows = _persist_topic_evidence(db, run, topic_hits)

    params_by_sku = _aggregate_params(param_rows)
    topics_by_sku = _aggregate_topics(topic_rows)
    claims_by_sku = _aggregate_claims(seed, params_by_sku, claim_rows, topics_by_sku)

    db.execute(delete(Core3SkuFeatureProfile).where(Core3SkuFeatureProfile.run_id == run_id))
    profiles: list[Core3SkuFeatureProfile] = []
    for sku_code in profile_sku_codes:
        sku_params = params_by_sku.get(sku_code, {})
        sku_claims = claims_by_sku.get(sku_code, [])
        sku_topics = topics_by_sku.get(sku_code, [])
        market_profile = market_by_sku.get(sku_code)
        semantic_profiles = derive_semantic_profiles(
            seed,
            market_profile=market_profile,
            standard_params=sku_params,
            claim_activations=sku_claims,
            comment_topics=sku_topics,
        )
        evidence_ids = _unique(
            [
                evidence_id
                for item in list(sku_params.values()) + sku_claims + sku_topics
                for evidence_id in item.get("evidence_ids", [])
            ]
            + (market_profile.evidence_ids if market_profile else [])
            + semantic_profiles["evidence_ids"]
        )
        missing_signals = _missing_signals(sku_code, sku_params, sku_claims, sku_topics)
        if market_profile:
            missing_signals = _unique([*missing_signals, *market_profile.missing_signals])
        missing_signals = _unique([*missing_signals, *semantic_profiles["missing_signals"]])
        profile = Core3SkuFeatureProfile(
            run_id=run.run_id,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=sku_code,
            standard_params=sku_params,
            claim_activations=sku_claims,
            comment_topics=sku_topics,
            task_scores=semantic_profiles["task_scores"],
            target_group_scores=semantic_profiles["target_group_scores"],
            battlefield_scores=semantic_profiles["battlefield_scores"],
            feature_evidence_ids=evidence_ids,
            extraction_diagnostics={
                **diagnostics,
                "market_profile": _market_diagnostics(market_profile),
                "semantic_profile": semantic_profiles["diagnostics"],
                "missing_signals": missing_signals,
            },
            missing_signals=missing_signals,
            confidence=_feature_confidence(
                sku_params,
                sku_claims,
                sku_topics,
                param_conflicts,
                market_profile.confidence if market_profile else None,
            ),
        )
        db.add(profile)
        profiles.append(profile)
    db.flush()
    competitor_counts = generate_core3_competitors(db, run, target_sku_codes)
    finish_run(
        db,
        run_id,
        status="completed",
        counts={
            **(run.counts or {}),
            "feature_profile_count": len(profiles),
            "market_profile_count": len(market_profiles),
            **competitor_counts,
        },
        warnings=[warning for warning in (run.warnings or []) if "仅创建运行上下文" not in warning],
        diagnostics={
            "feature_pipeline": {
                "target_sku_codes": target_sku_codes,
                "profile_sku_codes": profile_sku_codes,
                "completed": True,
            }
        },
    )
    return profiles


def _target_sku_codes(run: Core3PipelineRun, bundle: Any) -> list[str]:
    diagnostics = run.diagnostics or {}
    target_sku_codes = diagnostics.get("target_sku_codes")
    if target_sku_codes:
        return [str(code) for code in target_sku_codes]
    return sorted({str(row.sku_code).strip() for row in bundle.sku_master if row.sku_code})


def _profile_sku_codes(run: Core3PipelineRun, bundle: Any, target_sku_codes: list[str]) -> list[str]:
    all_sku_codes = sorted({str(row.sku_code).strip() for row in bundle.sku_master if row.sku_code})
    if run.scope == "single_sku":
        return all_sku_codes
    return all_sku_codes if target_sku_codes else []


def _persist_param_evidence(
    db: Session,
    run: Core3PipelineRun,
    rows: list[ParamExtraction],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        evidence = get_or_create_evidence(
            db,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=row.sku_code,
            source_type=row.source_type,
            source_file_id=row.source_file_id,
            raw_row_id=row.raw_row_id,
            field_name=row.field_name,
            raw_value=row.raw_value,
            normalized_value={"param_code": row.param_code, "value": row.normalized_value, "unit": row.unit},
            source_ref=row.source_ref,
            confidence=row.confidence,
        )
        output.append(
            {
                "sku_code": row.sku_code,
                "param_code": row.param_code,
                "normalized_value": row.normalized_value,
                "unit": row.unit,
                "source": row.source_type,
                "confidence": row.confidence,
                "match_type": row.match_type,
                "raw_value": row.raw_value,
                "evidence_ids": [evidence.evidence_id],
            }
        )
    return output


def _persist_claim_evidence(
    db: Session,
    run: Core3PipelineRun,
    hits: list[ClaimHit],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for hit in hits:
        evidence = get_or_create_evidence(
            db,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=hit.sku_code,
            source_type="claim_text",
            source_file_id=hit.source_file_id,
            raw_row_id=hit.raw_row_id,
            field_name="claim_text",
            raw_value=hit.sentence,
            normalized_value={"claim_code": hit.claim_code, "matched_keywords": hit.matched_keywords},
            source_ref=hit.source_ref,
            confidence=hit.confidence,
        )
        output.append(
            {
                "sku_code": hit.sku_code,
                "claim_code": hit.claim_code,
                "sentence": hit.sentence,
                "promo_score": 1.0,
                "confidence": hit.confidence,
                "matched_keywords": hit.matched_keywords,
                "evidence_ids": [evidence.evidence_id],
            }
        )
    return output


def _persist_topic_evidence(
    db: Session,
    run: Core3PipelineRun,
    hits: list[CommentTopicHit],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for hit in hits:
        evidence = get_or_create_evidence(
            db,
            project_id=run.project_id,
            category_code=run.category_code,
            sku_code=hit.sku_code,
            source_type="comment_text",
            source_file_id=hit.source_file_id,
            raw_row_id=hit.raw_row_id,
            field_name="comment_text",
            raw_value=hit.sentence,
            normalized_value={
                "topic_code": hit.topic_code,
                "sentiment": hit.sentiment,
                "comment_type": hit.comment_type,
            },
            source_ref=hit.source_ref,
            confidence=hit.confidence,
        )
        output.append(
            {
                "sku_code": hit.sku_code,
                "topic_code": hit.topic_code,
                "sentence": hit.sentence,
                "sentiment": hit.sentiment,
                "comment_type": hit.comment_type,
                "confidence": hit.confidence,
                "matched_keywords": hit.matched_keywords,
                "evidence_ids": [evidence.evidence_id],
            }
        )
    return output


def _aggregate_params(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_sku: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    priority = {"raw_param": 3, "claim_text": 2, "model_name": 1, "comment_text": 0}
    for row in rows:
        existing = by_sku[row["sku_code"]].get(row["param_code"])
        if existing and (priority.get(existing["source"], 0), existing["confidence"]) >= (
            priority.get(row["source"], 0),
            row["confidence"],
        ):
            existing["evidence_ids"] = _unique([*existing["evidence_ids"], *row["evidence_ids"]])
            continue
        by_sku[row["sku_code"]][row["param_code"]] = {
            "param_code": row["param_code"],
            "normalized_value": row["normalized_value"],
            "unit": row["unit"],
            "source": row["source"],
            "confidence": row["confidence"],
            "match_type": row["match_type"],
            "evidence_ids": row["evidence_ids"],
        }
    return by_sku


def _aggregate_topics(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["sku_code"], row["topic_code"])
        item = grouped.setdefault(
            key,
            {
                "topic_code": row["topic_code"],
                "mention_count": 0,
                "positive_count": 0,
                "negative_count": 0,
                "neutral_count": 0,
                "sample_sentences": [],
                "evidence_ids": [],
                "comment_type": row["comment_type"],
            },
        )
        item["mention_count"] += 1
        item[f"{row['sentiment']}_count"] += 1
        if len(item["sample_sentences"]) < 3:
            item["sample_sentences"].append({"sentence": row["sentence"], "sentiment": row["sentiment"]})
        item["evidence_ids"] = _unique([*item["evidence_ids"], *row["evidence_ids"]])
    by_sku: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (sku_code, _), item in grouped.items():
        total = item["mention_count"] or 1
        item["positive_rate"] = round(item["positive_count"] / total, 4)
        item["negative_rate"] = round(item["negative_count"] / total, 4)
        by_sku[sku_code].append(item)
    for items in by_sku.values():
        items.sort(key=lambda item: (-item["mention_count"], item["topic_code"]))
    return by_sku


def _aggregate_claims(
    seed: Core3SeedCatalog,
    params_by_sku: dict[str, dict[str, dict[str, Any]]],
    claim_rows: list[dict[str, Any]],
    topics_by_sku: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    claim_hits: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in claim_rows:
        claim_hits[(row["sku_code"], row["claim_code"])].append(row)

    sku_codes = set(params_by_sku) | {sku for sku, _ in claim_hits} | set(topics_by_sku)
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sku_code in sku_codes:
        sku_params = params_by_sku.get(sku_code, {})
        sku_topics = {item["topic_code"]: item for item in topics_by_sku.get(sku_code, [])}
        for claim in seed.standard_claims:
            param_score = _claim_param_score(claim.activation_rule, sku_params, claim.supporting_param_codes)
            promo_hits = claim_hits.get((sku_code, claim.claim_code), [])
            promo_score = 1.0 if promo_hits else None
            topic_evidence = [sku_topics[code] for code in claim.comment_topic_codes if code in sku_topics]
            comment_score = min(1.0, sum(item["positive_rate"] for item in topic_evidence)) if topic_evidence else None
            activation_score, confidence, missing = _weighted_activation(
                claim.activation_weights,
                {"param": param_score, "promo": promo_score, "comment": comment_score},
            )
            if activation_score <= 0:
                continue
            evidence_ids = _unique(
                [
                    evidence_id
                    for param_code in claim.supporting_param_codes
                    if param_code in sku_params
                    for evidence_id in sku_params[param_code].get("evidence_ids", [])
                ]
                + [evidence_id for hit in promo_hits for evidence_id in hit.get("evidence_ids", [])]
                + [evidence_id for item in topic_evidence for evidence_id in item.get("evidence_ids", [])]
            )
            if not evidence_ids:
                continue
            output[sku_code].append(
                {
                    "claim_code": claim.claim_code,
                    "activation_score": round(activation_score, 4),
                    "param_score": param_score,
                    "promo_score": promo_score,
                    "comment_score": comment_score,
                    "confidence": round(confidence, 4),
                    "evidence_ids": evidence_ids,
                    "missing_signals": missing,
                }
            )
        output[sku_code].sort(key=lambda item: (-item["activation_score"], item["claim_code"]))
    return output


def _claim_param_score(
    activation_rule: dict[str, Any],
    sku_params: dict[str, dict[str, Any]],
    supporting_param_codes: list[str],
) -> float | None:
    scores: list[float] = []
    for param_code in supporting_param_codes:
        if param_code not in sku_params:
            continue
        value = sku_params[param_code]["normalized_value"]
        scores.append(_score_param_value(param_code, value, activation_rule))
    return max(scores) if scores else None


def _score_param_value(param_code: str, value: Any, activation_rule: dict[str, Any]) -> float:
    for rule in _iter_rule_dicts(activation_rule):
        if rule.get("param") != param_code:
            continue
        if "eq" in rule:
            return 1.0 if value == rule["eq"] else 0.0
        if "gte" in rule and isinstance(value, int | float):
            return min(1.0, float(value) / float(rule["gte"]))
        if "lte" in rule and isinstance(value, int | float):
            return 1.0 if float(value) <= float(rule["lte"]) else 0.0
    if value is True:
        return 1.0
    if value is False:
        return 0.0
    if isinstance(value, int | float):
        return 0.75 if value > 0 else 0.0
    return 0.65


def _iter_rule_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        output = [value]
        for child in value.values():
            output.extend(_iter_rule_dicts(child))
        return output
    if isinstance(value, list):
        output: list[dict[str, Any]] = []
        for child in value:
            output.extend(_iter_rule_dicts(child))
        return output
    return []


def _weighted_activation(weights: dict[str, float], scores: dict[str, float | None]) -> tuple[float, float, list[str]]:
    total_weight = sum(weights.values()) or 1.0
    known_weight = 0.0
    weighted_score = 0.0
    missing: list[str] = []
    for signal, weight in weights.items():
        score = scores.get(signal)
        if score is None:
            missing.append(signal)
            continue
        known_weight += weight
        weighted_score += weight * score
    if known_weight == 0:
        return 0.0, 0.0, missing
    return weighted_score / known_weight, known_weight / total_weight, missing


def _missing_signals(
    sku_code: str,
    params: dict[str, Any],
    claims: list[dict[str, Any]],
    topics: list[dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    if not params:
        missing.append(f"{sku_code}:missing_params")
    if not claims:
        missing.append(f"{sku_code}:missing_claim_activations")
    if not topics:
        missing.append(f"{sku_code}:missing_comment_topics")
    return missing


def _market_diagnostics(market_profile: Any | None) -> dict[str, Any]:
    if market_profile is None:
        return {"status": "missing", "missing_signals": ["missing_market_profile"]}
    return {
        "status": "ready" if not market_profile.missing_signals else "degraded",
        "price_percentile": market_profile.price_percentile,
        "sales_percentile": market_profile.sales_percentile,
        "sales_amount_percentile": market_profile.sales_amount_percentile,
        "confidence": market_profile.confidence,
        "missing_signals": market_profile.missing_signals,
        "evidence_ids": market_profile.evidence_ids,
    }


def _feature_confidence(
    params: dict[str, Any],
    claims: list[dict[str, Any]],
    topics: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    market_confidence: float | None = None,
) -> float:
    param_coverage = min(1.0, len(params) / 12)
    claim_coverage = 1.0 if claims and all(item.get("evidence_ids") for item in claims) else 0.0
    comment_coverage = 1.0 if topics else 0.0
    conflict_penalty = 0.0 if conflicts else 1.0
    market_score = market_confidence if market_confidence is not None else 0.0
    return round(
        param_coverage * 0.30
        + claim_coverage * 0.25
        + comment_coverage * 0.15
        + conflict_penalty * 0.10
        + market_score * 0.20,
        4,
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
