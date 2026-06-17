from __future__ import annotations

from typing import Any

from app.schemas.core3_mvp import Core3SeedCatalog


DEFAULT_TASK_WEIGHTS = {"claim": 0.40, "param": 0.25, "comment": 0.20, "market": 0.15}


def derive_semantic_profiles(
    seed: Core3SeedCatalog,
    *,
    market_profile: Any | None,
    standard_params: dict[str, dict[str, Any]],
    claim_activations: list[dict[str, Any]],
    comment_topics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive task, target-group, and battlefield scores from extracted evidence."""
    param_seed = {item.param_code: item for item in seed.standard_params}
    claims = {item["claim_code"]: item for item in claim_activations}
    topics = {item["topic_code"]: item for item in comment_topics}

    tasks = _derive_tasks(seed, param_seed, market_profile, standard_params, claims, topics)
    task_by_code = {item["task_code"]: item for item in tasks}
    groups = _derive_target_groups(seed, market_profile, standard_params, claims, topics, task_by_code)
    group_by_code = {item["target_group_code"]: item for item in groups}
    battlefields = _derive_battlefields(
        seed,
        param_seed,
        market_profile,
        standard_params,
        claims,
        topics,
        task_by_code,
        group_by_code,
    )

    evidence_ids = _unique(
        [
            evidence_id
            for rows in [tasks, groups, battlefields]
            for row in rows
            for evidence_id in row.get("evidence_ids", [])
        ]
    )
    missing_signals = _unique(
        [
            missing
            for rows in [tasks, groups, battlefields]
            for row in rows
            for missing in row.get("missing_signals", [])
        ]
    )
    if not tasks:
        missing_signals.append("missing_task_scores")
    if not groups:
        missing_signals.append("missing_target_group_scores")
    if not battlefields:
        missing_signals.append("missing_battlefield_scores")

    return {
        "task_scores": tasks,
        "target_group_scores": groups,
        "battlefield_scores": battlefields,
        "evidence_ids": evidence_ids,
        "missing_signals": _unique(missing_signals),
        "diagnostics": {
            "task_count": len(tasks),
            "target_group_count": len(groups),
            "battlefield_count": len(battlefields),
        },
    }


def _derive_tasks(
    seed: Core3SeedCatalog,
    param_seed: dict[str, Any],
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in seed.user_tasks:
        weights = {**DEFAULT_TASK_WEIGHTS, **(task.score_rule or {})}
        claim_signal = _claim_signal(task.positive_claim_codes, claims)
        param_signal = _param_signal(task.positive_param_codes, params, param_seed)
        comment_signal = _comment_signal(task.comment_topic_codes, topics)
        market_signal = _market_signal(task.market_signals, market_profile, params, claims, topics)
        score, confidence, missing = _weighted_score(
            weights,
            {
                "claim": claim_signal,
                "param": param_signal,
                "comment": comment_signal,
                "market": market_signal,
            },
        )
        if score is None or score < 0.25:
            continue
        evidence_ids = _evidence_for(
            params=params,
            param_codes=task.positive_param_codes,
            claims=claims,
            claim_codes=task.positive_claim_codes,
            topics=topics,
            topic_codes=task.comment_topic_codes,
            market_profile=market_profile,
            include_market=market_signal is not None,
        )
        if not evidence_ids:
            continue
        rows.append(
            {
                "task_code": task.task_code,
                "task_name": task.task_name,
                "score": round(score, 4),
                "relation_level": _relation_level(score),
                "component_scores": {
                    "claim_signal": _round_or_none(claim_signal),
                    "param_signal": _round_or_none(param_signal),
                    "comment_signal": _round_or_none(comment_signal),
                    "market_signal": _round_or_none(market_signal),
                },
                "reason": _task_reason(task.task_name, claim_signal, param_signal, comment_signal, market_signal),
                "evidence_ids": evidence_ids,
                "missing_signals": [f"{task.task_code}:missing_{name}_signal" for name in missing],
                "confidence": round(confidence, 4),
            }
        )
    rows.sort(key=lambda item: (-item["score"], item["task_code"]))
    return rows


def _derive_target_groups(
    seed: Core3SeedCatalog,
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
    task_by_code: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in seed.target_groups:
        task_signal = _average_known(
            [task_by_code[code]["score"] for code in group.source_task_codes if code in task_by_code]
        )
        market_fit = _market_signal((group.market_fit_rule or {}).get("signals") or [], market_profile, params, claims, topics)
        comment_validation = _group_comment_validation(group.source_task_codes, seed, topics)
        score, confidence, missing = _weighted_score(
            {"task": 0.60, "market": 0.20, "comment": 0.20},
            {"task": task_signal, "market": market_fit, "comment": comment_validation},
        )
        if score is None or score < 0.25:
            continue
        evidence_ids = _unique(
            [
                evidence_id
                for code in group.source_task_codes
                if code in task_by_code
                for evidence_id in task_by_code[code].get("evidence_ids", [])
            ]
            + _evidence_for(
                params=params,
                param_codes=[],
                claims=claims,
                claim_codes=[],
                topics=topics,
                topic_codes=_topic_codes_for_tasks(seed, group.source_task_codes),
                market_profile=market_profile,
                include_market=market_fit is not None,
            )
        )
        rows.append(
            {
                "target_group_code": group.target_group_code,
                "target_group_name": group.target_group_name,
                "score": round(score, 4),
                "relation_level": _relation_level(score),
                "component_scores": {
                    "source_task_score": _round_or_none(task_signal),
                    "price_channel_fit": _round_or_none(market_fit),
                    "comment_validation": _round_or_none(comment_validation),
                },
                "source_task_codes": [code for code in group.source_task_codes if code in task_by_code],
                "reason": f"{group.target_group_name} 由任务得分、市场位置和评论校验共同派生。",
                "evidence_ids": evidence_ids,
                "missing_signals": [f"{group.target_group_code}:missing_{name}_signal" for name in missing],
                "confidence": round(confidence, 4),
            }
        )
    rows.sort(key=lambda item: (-item["score"], item["target_group_code"]))
    return rows


def _derive_battlefields(
    seed: Core3SeedCatalog,
    param_seed: dict[str, Any],
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
    task_by_code: dict[str, dict[str, Any]],
    group_by_code: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for battlefield in seed.battlefields:
        core_task_score = _average_known(
            [task_by_code[code]["score"] for code in battlefield.core_task_codes if code in task_by_code]
        )
        core_claim_combo = _claim_signal(battlefield.core_claim_codes, claims)
        core_param_score = _param_signal(battlefield.core_param_codes, params, param_seed)
        claim_or_param = _average_known([core_claim_combo, core_param_score])
        comment_validation = _comment_signal(battlefield.comment_topic_codes, topics)
        group_score = _average_known(
            [
                group["score"]
                for group in group_by_code.values()
                if battlefield.battlefield_code in group.get("mapped_battlefield_codes", [])
                or battlefield.battlefield_code in _group_battlefields(seed, group["target_group_code"])
            ]
        )
        semantic_score, semantic_confidence, semantic_missing = _weighted_score(
            {"task": 0.40, "claim_combo": 0.35, "comment": 0.15, "group": 0.10},
            {
                "task": core_task_score,
                "claim_combo": claim_or_param,
                "comment": comment_validation,
                "group": group_score,
            },
        )
        market_score, market_missing = _battlefield_market_score(
            battlefield.market_score_rule or {},
            market_profile,
            params,
            claims,
            topics,
        )
        if semantic_score is None:
            continue
        weights = {"semantic": 0.65, "market": 0.35}
        weights.update(battlefield.semantic_market_weights or {})
        final_score = float(weights["semantic"]) * semantic_score + float(weights["market"]) * (market_score or 0.0)
        thresholds = battlefield.entry_thresholds or {"main": 0.75, "secondary": 0.55, "weak": 0.35}
        weak_threshold = float(thresholds.get("weak", 0.35))
        if final_score < weak_threshold:
            continue
        evidence_ids = _evidence_for(
            params=params,
            param_codes=battlefield.core_param_codes,
            claims=claims,
            claim_codes=battlefield.core_claim_codes,
            topics=topics,
            topic_codes=battlefield.comment_topic_codes,
            market_profile=market_profile,
            include_market=market_score is not None,
        )
        if not evidence_ids:
            continue
        relation_level = _battlefield_level(final_score, thresholds)
        missing_signals = [f"{battlefield.battlefield_code}:missing_{name}_signal" for name in semantic_missing]
        missing_signals.extend(f"{battlefield.battlefield_code}:missing_{name}_market_signal" for name in market_missing)
        if market_score is None:
            missing_signals.append(f"{battlefield.battlefield_code}:missing_market_score")
        rows.append(
            {
                "battlefield_code": battlefield.battlefield_code,
                "battlefield_name": battlefield.battlefield_name,
                "score": round(final_score, 4),
                "final_score": round(final_score, 4),
                "semantic_score": round(semantic_score, 4),
                "market_score": _round_or_none(market_score),
                "relation_level": relation_level,
                "component_scores": {
                    "core_task_score": _round_or_none(core_task_score),
                    "core_claim_combo_score": _round_or_none(claim_or_param),
                    "comment_validation_score": _round_or_none(comment_validation),
                    "target_group_score": _round_or_none(group_score),
                    "market_score": _round_or_none(market_score),
                },
                "reason": f"{battlefield.battlefield_name} 由语义信号 {round(semantic_score, 4)} 和市场信号 {_round_or_none(market_score)} 共同计算。",
                "evidence_ids": evidence_ids,
                "missing_signals": _unique(missing_signals),
                "confidence": round(min(1.0, semantic_confidence * 0.70 + (0.30 if market_score is not None else 0.0)), 4),
            }
        )
    rows.sort(key=lambda item: (-item["score"], item["battlefield_code"]))
    return rows


def _claim_signal(claim_codes: list[str], claims: dict[str, dict[str, Any]]) -> float | None:
    return _average_known([claims[code].get("activation_score") for code in claim_codes if code in claims])


def _param_signal(
    param_codes: list[str],
    params: dict[str, dict[str, Any]],
    param_seed: dict[str, Any],
) -> float | None:
    scores = []
    for code in param_codes:
        if code not in params:
            continue
        scores.append(_param_value_score(code, params[code].get("normalized_value"), param_seed.get(code)))
    return _average_known(scores)


def _param_value_score(param_code: str, value: Any, seed_param: Any | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, dict):
        numeric_values = [float(item) for item in value.values() if isinstance(item, int | float)]
        return _average_known([min(1.0, item / 4.0) for item in numeric_values])
    if isinstance(value, list):
        return 1.0 if value else None
    if isinstance(value, str):
        return 0.65 if value.strip() else None
    if not isinstance(value, int | float):
        return None
    numeric = float(value)
    if param_code in {"input_lag_ms"}:
        return round(max(0.0, min(1.0, (80.0 - numeric) / 80.0)), 4)
    threshold_values = []
    if seed_param is not None:
        threshold_values = [float(item) for item in (seed_param.thresholds or {}).values() if isinstance(item, int | float)]
    threshold = min(threshold_values) if threshold_values else _default_numeric_threshold(param_code)
    if threshold <= 0:
        return 0.65 if numeric > 0 else 0.0
    return round(max(0.0, min(1.0, numeric / threshold)), 4)


def _default_numeric_threshold(param_code: str) -> float:
    if "refresh_rate" in param_code:
        return 120.0
    if "brightness" in param_code:
        return 1000.0
    if "dimming" in param_code or "zones" in param_code:
        return 100.0
    if "hdmi" in param_code or "ports" in param_code:
        return 1.0
    if param_code == "screen_size_inch":
        return 75.0
    return 1.0


def _comment_signal(topic_codes: list[str], topics: dict[str, dict[str, Any]]) -> float | None:
    return _average_known([topics[code].get("positive_rate") for code in topic_codes if code in topics])


def _market_signal(
    signals: list[str],
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
) -> float | None:
    return _average_known(
        [_market_signal_one(signal, market_profile, params, claims, topics) for signal in signals]
    )


def _market_signal_one(
    signal: str,
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
) -> float | None:
    price_pct = _attr(market_profile, "price_percentile")
    sales_pct = _attr(market_profile, "sales_percentile")
    amount_pct = _attr(market_profile, "sales_amount_percentile")
    price_drop = _attr(market_profile, "price_drop_rate_3m")
    sales_growth = _attr(market_profile, "sales_growth_3m")
    screen_score = _param_value_score("screen_size_inch", _param_value(params, "screen_size_inch"), None)

    if signal in {"premium_price_band", "price_percentile"}:
        return price_pct
    if signal in {"mid_high_price_band", "mainstream_price_band", "price_band_fit"}:
        return _fit_percentile(price_pct, 0.60)
    if signal in {"low_price_percentile", "low_price_band"}:
        return None if price_pct is None else round(1.0 - float(price_pct), 4)
    if signal in {"high_sales_volume", "sales_volume_rank", "sales_volume_percentile", "mid_high_sales"}:
        return sales_pct
    if signal in {"high_sales_amount", "sales_amount_percentile", "premium_price_acceptance"}:
        return amount_pct
    if signal == "price_per_inch":
        low_price = None if price_pct is None else 1.0 - float(price_pct)
        return _average_known([low_price, screen_score])
    if signal in {"family_size_demand", "large_screen", "family_purchase", "new_home_purchase"}:
        return _average_known([screen_score, sales_pct])
    if signal == "small_size_fit":
        size = _param_value(params, "screen_size_inch")
        if not isinstance(size, int | float):
            return None
        return round(max(0.0, min(1.0, (65.0 - float(size)) / 30.0)), 4)
    if signal == "gaming_price_band":
        return _fit_percentile(price_pct, 0.55)
    if signal == "promotion_flag":
        if price_drop is None:
            return None
        return round(max(0.0, min(1.0, float(price_drop) / 0.20)), 4)
    if signal in {"sports_event_season", "low_return_risk"}:
        return _average_known([sales_pct, _positive_topic_average(topics)])
    if signal in {"system_risk_comments", "service_positive_rate", "audio_comment_rate"}:
        return _positive_topic_average(topics)
    if signal == "durability_negative_rate":
        negative = _negative_topic_average(topics)
        return None if negative is None else round(1.0 - negative, 4)
    if signal == "premium_price_acceptance":
        return amount_pct
    if signal == "sales_trend":
        return None if sales_growth is None else round(max(0.0, min(1.0, 0.5 + float(sales_growth))), 4)
    return _average_known([sales_pct, amount_pct])


def _battlefield_market_score(
    rule: dict[str, Any],
    market_profile: Any | None,
    params: dict[str, dict[str, Any]],
    claims: dict[str, dict[str, Any]],
    topics: dict[str, dict[str, Any]],
) -> tuple[float | None, list[str]]:
    configured_signal = _market_signal(rule.get("signals") or [], market_profile, params, claims, topics)
    sales_validation = _average_known(
        [_attr(market_profile, "sales_percentile"), _attr(market_profile, "sales_amount_percentile")]
    )
    channel_share = _attr(market_profile, "channel_share") or {}
    channel_fit = max(channel_share.values()) if channel_share else None
    trend_signal = _average_known(
        [
            _positive_rate(_attr(market_profile, "sales_growth_3m")),
            _positive_rate(_attr(market_profile, "price_drop_rate_3m")),
        ]
    )
    comparable_strength = _attr(market_profile, "confidence")
    scores = {
        "price_position": configured_signal,
        "sales_validation": sales_validation,
        "channel_fit": channel_fit,
        "trend_signal": trend_signal,
        "comparable_pool": comparable_strength,
    }
    score, _, missing = _weighted_score(
        {
            "price_position": 0.30,
            "sales_validation": 0.25,
            "channel_fit": 0.15,
            "trend_signal": 0.15,
            "comparable_pool": 0.15,
        },
        scores,
    )
    return score, missing


def _weighted_score(weights: dict[str, float], scores: dict[str, float | None]) -> tuple[float | None, float, list[str]]:
    known_weight = 0.0
    weighted_score = 0.0
    missing: list[str] = []
    total_weight = sum(float(value) for value in weights.values()) or 1.0
    for name, weight in weights.items():
        score = scores.get(name)
        if score is None:
            missing.append(name)
            continue
        known_weight += float(weight)
        weighted_score += float(weight) * max(0.0, min(1.0, float(score)))
    if known_weight <= 0:
        return None, 0.0, missing
    return round(weighted_score / known_weight, 4), round(known_weight / total_weight, 4), missing


def _average_known(values: list[Any]) -> float | None:
    known = [float(value) for value in values if isinstance(value, int | float)]
    if not known:
        return None
    return round(sum(known) / len(known), 4)


def _fit_percentile(value: Any, target: float) -> float | None:
    if value is None:
        return None
    return round(max(0.0, 1.0 - abs(float(value) - target) / max(target, 1.0 - target)), 4)


def _positive_rate(value: Any) -> float | None:
    if value is None:
        return None
    return round(max(0.0, min(1.0, 0.5 + float(value))), 4)


def _positive_topic_average(topics: dict[str, dict[str, Any]]) -> float | None:
    return _average_known([topic.get("positive_rate") for topic in topics.values()])


def _negative_topic_average(topics: dict[str, dict[str, Any]]) -> float | None:
    return _average_known([topic.get("negative_rate") for topic in topics.values()])


def _topic_codes_for_tasks(seed: Core3SeedCatalog, task_codes: list[str]) -> list[str]:
    task_set = set(task_codes)
    return _unique([code for task in seed.user_tasks if task.task_code in task_set for code in task.comment_topic_codes])


def _group_comment_validation(
    source_task_codes: list[str],
    seed: Core3SeedCatalog,
    topics: dict[str, dict[str, Any]],
) -> float | None:
    return _comment_signal(_topic_codes_for_tasks(seed, source_task_codes), topics)


def _group_battlefields(seed: Core3SeedCatalog, target_group_code: str) -> list[str]:
    for group in seed.target_groups:
        if group.target_group_code == target_group_code:
            return list(group.mapped_battlefield_codes)
    return []


def _evidence_for(
    *,
    params: dict[str, dict[str, Any]],
    param_codes: list[str],
    claims: dict[str, dict[str, Any]],
    claim_codes: list[str],
    topics: dict[str, dict[str, Any]],
    topic_codes: list[str],
    market_profile: Any | None,
    include_market: bool,
) -> list[str]:
    evidence_ids = [
        evidence_id
        for code in param_codes
        if code in params
        for evidence_id in params[code].get("evidence_ids", [])
    ]
    evidence_ids.extend(
        evidence_id
        for code in claim_codes
        if code in claims
        for evidence_id in claims[code].get("evidence_ids", [])
    )
    evidence_ids.extend(
        evidence_id
        for code in topic_codes
        if code in topics
        for evidence_id in topics[code].get("evidence_ids", [])
    )
    if include_market and market_profile is not None:
        evidence_ids.extend(_attr(market_profile, "evidence_ids") or [])
    return _unique(evidence_ids)


def _param_value(params: dict[str, dict[str, Any]], param_code: str) -> Any:
    if param_code not in params:
        return None
    return params[param_code].get("normalized_value")


def _attr(obj: Any | None, name: str) -> Any:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _relation_level(score: float) -> str:
    if score >= 0.75:
        return "main"
    if score >= 0.55:
        return "secondary"
    return "weak"


def _battlefield_level(score: float, thresholds: dict[str, Any]) -> str:
    if score >= float(thresholds.get("main", 0.75)):
        return "main"
    if score >= float(thresholds.get("secondary", 0.55)):
        return "secondary"
    return "weak"


def _task_reason(
    task_name: str,
    claim_signal: float | None,
    param_signal: float | None,
    comment_signal: float | None,
    market_signal: float | None,
) -> str:
    parts = []
    for label, value in [
        ("卖点", claim_signal),
        ("参数", param_signal),
        ("评论", comment_signal),
        ("市场", market_signal),
    ]:
        if value is not None:
            parts.append(f"{label}{round(value, 4)}")
    return f"{task_name} 由" + "、".join(parts) + "共同支持。"


def _round_or_none(value: Any) -> float | None:
    if not isinstance(value, int | float):
        return None
    return round(float(value), 4)


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
