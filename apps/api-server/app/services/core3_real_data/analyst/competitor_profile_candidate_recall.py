"""Pure in-memory, multi-entry recall for competitor-profile candidates."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    ALL_RECALL_ENTRY_CODES,
    CandidateRecallConfig,
    CandidateRecallManifest,
    RecallEntryCoverage,
    RecallFact,
    RecalledCandidate,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    COMPETITOR_PROFILE_SOURCE_MODULES,
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CandidateIdentity,
    EvidenceRef,
)
from app.services.core3_real_data.hash_utils import stable_hash


_SEMANTIC_MODULES = ("M09C", "M10C", "M11C", "M12C", "M12D")
_ENTRY_MODULES: dict[str, tuple[str, ...]] = {
    "downtrade": ("M07", *_SEMANTIC_MODULES),
    "market_reference": ("M07",),
    "same_brand_ladder": ("M03B", "M07"),
    "same_purchase_pool": ("M03B", "M07"),
    "same_value": ("M11C", "M12C", "M12D"),
    "scenario": ("M09C", "M10C", "M11C"),
    "uptrade": ("M07", *_SEMANTIC_MODULES),
}


class CandidateRecallError(RuntimeError):
    """Base class for recall failures that must not silently degrade scope."""


class CandidateRecallScopeError(CandidateRecallError):
    pass


@dataclass(frozen=True)
class _SkuRecallFeatures:
    sku_code: str
    product_category: str
    records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]]
    identity: CandidateIdentity
    brand_key: str | None
    price: Decimal | None
    weekly_volume: Decimal | None
    market_pool_key: str | None
    size_segment: str | None
    screen_size_inch: Decimal | None
    ac_form: str | None
    ac_capacity: str | None
    primary_tasks: frozenset[str]
    tasks: frozenset[str]
    primary_audiences: frozenset[str]
    audiences: frozenset[str]
    primary_battlefields: frozenset[str]
    secondary_battlefields: frozenset[str]
    opportunity_battlefields: frozenset[str]
    purchase_reasons: frozenset[str]
    claim_values: frozenset[str]


class CandidateRecallEngine:
    """Build a complete recall manifest without qualification, scoring, or limits."""

    def recall(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        config: CandidateRecallConfig | None = None,
    ) -> CandidateRecallManifest:
        recall_config = config or CandidateRecallConfig()
        self._assert_scope(category_bundle, target_bundle)
        if target_bundle.analysis_state == "blocked":
            raise CandidateRecallScopeError(
                "blocked target input cannot enter candidate recall"
            )

        features_by_sku = {
            sku_code: _features_for_sku(category_bundle, sku_code, recall_config)
            for sku_code in category_bundle.authoritative_sku_codes
        }
        target = features_by_sku[target_bundle.target_sku_code]
        enabled = set(recall_config.enabled_entries)
        candidates: list[RecalledCandidate] = []
        for candidate_sku_code in category_bundle.authoritative_sku_codes:
            if candidate_sku_code == target.sku_code:
                continue
            candidate = features_by_sku[candidate_sku_code]
            facts = _recall_facts(target, candidate, recall_config, enabled)
            if not facts:
                continue
            candidates.append(
                _recalled_candidate(
                    target=target,
                    candidate=candidate,
                    facts=facts,
                    category_input_fingerprint=category_bundle.input_fingerprint,
                    config=recall_config,
                )
            )
        candidates.sort(key=lambda row: row.candidate.sku_code)
        entry_coverage = _entry_coverage(
            target=target,
            candidates=candidates,
            config=recall_config,
        )
        limitations = sorted(
            {
                *target_bundle.limitations,
                *(
                    ["candidate_recall_manifest_empty"]
                    if not candidates
                    else []
                ),
            }
        )
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "target_sku_code": target.sku_code,
                "config": recall_config.model_dump(mode="python"),
            },
            version="competitor_profile_candidate_recall_input_v1",
        )
        result_payload = {
            "input_fingerprint": input_fingerprint,
            "candidate_hashes": {
                row.candidate.sku_code: row.result_hash for row in candidates
            },
            "entry_coverage_hashes": {
                code: entry_coverage[code].result_hash
                for code in sorted(entry_coverage)
            },
            "limitations": limitations,
        }
        return CandidateRecallManifest(
            project_id=category_bundle.serving_scope.project_id,
            category_code=category_bundle.serving_scope.category_code,
            product_category=category_bundle.serving_scope.product_category,
            release_scope_key=category_bundle.serving_scope.release_scope_key,
            target_sku_code=target.sku_code,
            category_input_fingerprint=category_bundle.input_fingerprint,
            target_input_fingerprint=target_bundle.input_fingerprint,
            config=recall_config,
            candidate_count=len(candidates),
            candidates=candidates,
            entry_coverage=entry_coverage,
            limitations=limitations,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_candidate_recall_result_v1",
            ),
        )

    @staticmethod
    def _assert_scope(
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
    ) -> None:
        if category_bundle.serving_scope != target_bundle.serving_scope:
            raise CandidateRecallScopeError(
                "target and category bundles must use the same serving scope"
            )
        if target_bundle.target_sku_code not in category_bundle.authoritative_sku_codes:
            raise CandidateRecallScopeError(
                "target SKU is outside the authoritative recall manifest"
            )
        scope = category_bundle.serving_scope
        if scope.category_code != scope.product_category:
            raise CandidateRecallScopeError(
                "recall scope category and product category must match"
            )
        if any(
            not sku_code.startswith(scope.category_code)
            for sku_code in category_bundle.authoritative_sku_codes
        ):
            raise CandidateRecallScopeError(
                "authoritative manifest contains a cross-category SKU"
            )
        for module_code, module in category_bundle.modules.items():
            if (
                module.authority.project_id != scope.project_id
                or module.authority.category_code != scope.category_code
                or module.authority.product_category != scope.product_category
            ):
                raise CandidateRecallScopeError(
                    f"{module_code} authority conflicts with recall scope"
                )


def _features_for_sku(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
    config: CandidateRecallConfig,
) -> _SkuRecallFeatures:
    records = {
        code: tuple(bundle.modules[code].records_by_sku.get(sku_code, []))
        for code in COMPETITOR_PROFILE_SOURCE_MODULES
    }
    market = _first_facts(records["M07"])
    params = _first_facts(records["M03B"])
    task = _first_facts(records["M09C"])
    audience = _first_facts(records["M10C"])
    battlefield = _first_facts(records["M11C"])
    purchase_reason = _first_facts(records["M12D"])
    brand_name = _text(market.get("brand_name") or market.get("brand"))
    model_name = _text(market.get("model_name"))
    if purchase_reason:
        brand_name = brand_name or _text(purchase_reason.get("brand_name"))
        model_name = model_name or _text(purchase_reason.get("model_name"))
    display_name = " ".join(value for value in (brand_name, model_name) if value)
    price = _decimal(market.get("price_wavg"))
    weekly_volume = _weekly_volume(market)
    param_values = params.get("param_values_json")
    ac_form = _param_value(param_values, config.ac_form_param_codes)
    ac_capacity = _param_value(param_values, config.ac_capacity_param_codes)
    return _SkuRecallFeatures(
        sku_code=sku_code,
        product_category=bundle.serving_scope.product_category,
        records=records,
        identity=CandidateIdentity(
            sku_code=sku_code,
            brand_name=brand_name,
            model_name=model_name,
            display_name_cn=display_name or sku_code,
            product_category=bundle.serving_scope.product_category,
        ),
        brand_key=_brand_key(brand_name),
        price=price,
        weekly_volume=weekly_volume,
        market_pool_key=_known_text(market.get("market_pool_key")),
        size_segment=_known_text(market.get("size_segment")),
        screen_size_inch=_decimal(market.get("screen_size_inch")),
        ac_form=_known_text(ac_form),
        ac_capacity=_known_text(ac_capacity),
        primary_tasks=frozenset(_codes(task.get("primary_user_task_code"))),
        tasks=frozenset(
            _codes(
                task.get("primary_user_task_code"),
                task.get("secondary_user_task_codes_json"),
                task.get("comment_observed_task_codes_json"),
                task.get("latent_capability_task_codes_json"),
            )
        ),
        primary_audiences=frozenset(
            _codes(audience.get("primary_target_group_code"))
        ),
        audiences=frozenset(
            _codes(
                audience.get("primary_target_group_code"),
                audience.get("secondary_target_group_codes_json"),
                audience.get("comment_observed_group_codes_json"),
                audience.get("latent_group_codes_json"),
            )
        ),
        primary_battlefields=frozenset(
            _codes(battlefield.get("primary_battlefield_code"))
        ),
        secondary_battlefields=frozenset(
            _codes(battlefield.get("secondary_battlefield_codes_json"))
        ),
        opportunity_battlefields=frozenset(
            _codes(battlefield.get("opportunity_battlefield_codes_json"))
        ),
        purchase_reasons=frozenset(
            _codes(
                purchase_reason.get("core_payment_anchors_json"),
                purchase_reason.get("established_anchors_json"),
                purchase_reason.get("core_reasons_json"),
            )
        ),
        claim_values=frozenset(
            _codes(
                *(
                    row.facts.get("claim_code")
                    for row in records["M12C"]
                    if _known_text(row.facts.get("claim_code"))
                )
            )
        ),
    )


def _recall_facts(
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    config: CandidateRecallConfig,
    enabled: set[str],
) -> list[RecallFact]:
    drafts: list[RecallFact] = []
    compatible = _product_form_compatible(target, candidate, config)
    price_gap_pct = _price_gap_pct(target.price, candidate.price)
    budget_bucket = _budget_bucket(price_gap_pct, config)
    shared = _shared_semantics(target, candidate)

    if (
        "same_purchase_pool" in enabled
        and compatible is True
        and budget_bucket in {"same_budget", "adjacent_budget"}
    ):
        drafts.append(
            _fact(
                "same_purchase_pool",
                f"{budget_bucket}_compatible_product",
                target,
                candidate,
                modules=("M03B", "M07"),
                target_values=_market_values(target, price_gap_pct),
                candidate_values=_market_values(candidate, price_gap_pct),
            )
        )

    if (
        "same_brand_ladder" in enabled
        and target.brand_key
        and target.brand_key == candidate.brand_key
        and compatible is True
        and budget_bucket in {"same_budget", "adjacent_budget"}
    ):
        drafts.append(
            _fact(
                "same_brand_ladder",
                "same_brand_adjacent_product_ladder",
                target,
                candidate,
                modules=("M03B", "M07"),
                matched_values=[target.brand_key],
                target_values=_market_values(target, price_gap_pct),
                candidate_values=_market_values(candidate, price_gap_pct),
            )
        )

    if "scenario" in enabled:
        _append_overlap_fact(
            drafts,
            entry_code="scenario",
            reason_code="shared_user_task",
            target=target,
            candidate=candidate,
            matched=shared["task"],
            modules=("M09C",),
        )
        _append_overlap_fact(
            drafts,
            entry_code="scenario",
            reason_code="shared_target_audience",
            target=target,
            candidate=candidate,
            matched=shared["audience"],
            modules=("M10C",),
        )

    if "same_value" in enabled:
        _append_overlap_fact(
            drafts,
            entry_code="same_value",
            reason_code="same_primary_battlefield",
            target=target,
            candidate=candidate,
            matched=shared["primary_battlefield"],
            modules=("M11C",),
        )
        _append_overlap_fact(
            drafts,
            entry_code="same_value",
            reason_code="adjacent_secondary_or_opportunity_battlefield",
            target=target,
            candidate=candidate,
            matched=shared["adjacent_battlefield"],
            modules=("M11C",),
        )
        _append_overlap_fact(
            drafts,
            entry_code="same_value",
            reason_code="shared_purchase_reason",
            target=target,
            candidate=candidate,
            matched=shared["purchase_reason"],
            modules=("M12D",),
        )
        _append_overlap_fact(
            drafts,
            entry_code="same_value",
            reason_code="shared_claim_value",
            target=target,
            candidate=candidate,
            matched=shared["claim_value"],
            modules=("M12C",),
        )

    direction_entry = None
    if price_gap_pct is not None:
        if price_gap_pct <= -config.price_direction_min_pct:
            direction_entry = "downtrade"
        elif price_gap_pct >= config.price_direction_min_pct:
            direction_entry = "uptrade"
    if direction_entry in enabled:
        for semantic_name, module_code in (
            ("task", "M09C"),
            ("audience", "M10C"),
            ("battlefield", "M11C"),
            ("purchase_reason", "M12D"),
            ("claim_value", "M12C"),
        ):
            _append_overlap_fact(
                drafts,
                entry_code=direction_entry,
                reason_code=f"{direction_entry}_shared_{semantic_name}",
                target=target,
                candidate=candidate,
                matched=shared[semantic_name],
                modules=("M07", module_code),
                target_values=_market_values(target, price_gap_pct),
                candidate_values=_market_values(candidate, price_gap_pct),
            )

    if "market_reference" in enabled:
        if (
            target.market_pool_key
            and target.market_pool_key == candidate.market_pool_key
        ):
            drafts.append(
                _fact(
                    "market_reference",
                    "same_market_pool_baseline",
                    target,
                    candidate,
                    modules=("M07",),
                    matched_values=[target.market_pool_key],
                    target_values=_market_values(target, price_gap_pct),
                    candidate_values=_market_values(candidate, price_gap_pct),
                )
            )
        elif compatible is True and budget_bucket in {
            "same_budget",
            "adjacent_budget",
        }:
            drafts.append(
                _fact(
                    "market_reference",
                    "adjacent_price_market_baseline",
                    target,
                    candidate,
                    modules=("M07",),
                    target_values=_market_values(target, price_gap_pct),
                    candidate_values=_market_values(candidate, price_gap_pct),
                )
            )
        performance_direction = _performance_direction(target, candidate, config)
        if compatible is True and performance_direction:
            drafts.append(
                _fact(
                    "market_reference",
                    performance_direction,
                    target,
                    candidate,
                    modules=("M07",),
                    target_values=_market_values(target, price_gap_pct),
                    candidate_values=_market_values(candidate, price_gap_pct),
                )
            )
    unique = {row.result_hash: row for row in drafts}
    return sorted(
        unique.values(),
        key=lambda row: (row.entry_code, row.reason_code, tuple(row.matched_values)),
    )


def _shared_semantics(
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
) -> dict[str, list[str]]:
    primary_battlefields = target.primary_battlefields & candidate.primary_battlefields
    target_current = target.primary_battlefields | target.secondary_battlefields
    candidate_current = candidate.primary_battlefields | candidate.secondary_battlefields
    adjacent = (
        (target.opportunity_battlefields & candidate_current)
        | (candidate.opportunity_battlefields & target_current)
        | (target.secondary_battlefields & candidate.secondary_battlefields)
    ) - primary_battlefields
    battlefield = (
        target_current | target.opportunity_battlefields
    ) & (candidate_current | candidate.opportunity_battlefields)
    return {
        "task": sorted(target.tasks & candidate.tasks),
        "audience": sorted(target.audiences & candidate.audiences),
        "primary_battlefield": sorted(primary_battlefields),
        "adjacent_battlefield": sorted(adjacent),
        "battlefield": sorted(battlefield),
        "purchase_reason": sorted(
            target.purchase_reasons & candidate.purchase_reasons
        ),
        "claim_value": sorted(target.claim_values & candidate.claim_values),
    }


def _append_overlap_fact(
    facts: list[RecallFact],
    *,
    entry_code: str,
    reason_code: str,
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    matched: Sequence[str],
    modules: Sequence[str],
    target_values: Mapping[str, Any] | None = None,
    candidate_values: Mapping[str, Any] | None = None,
) -> None:
    if not matched:
        return
    facts.append(
        _fact(
            entry_code,
            reason_code,
            target,
            candidate,
            modules=modules,
            matched_values=matched,
            target_values=target_values,
            candidate_values=candidate_values,
        )
    )


def _fact(
    entry_code: str,
    reason_code: str,
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    *,
    modules: Sequence[str],
    matched_values: Sequence[str] = (),
    target_values: Mapping[str, Any] | None = None,
    candidate_values: Mapping[str, Any] | None = None,
) -> RecallFact:
    target_refs = _evidence_refs(target, modules)
    candidate_refs = _evidence_refs(candidate, modules)
    if not target_refs or not candidate_refs:
        raise CandidateRecallScopeError(
            f"recall fact {entry_code}/{reason_code} lacks source lineage"
        )
    model_payload = {
        "entry_code": entry_code,
        "reason_code": reason_code,
        "matched_values": sorted(set(matched_values)),
        "target_values": dict(target_values or {}),
        "candidate_values": dict(candidate_values or {}),
    }
    hash_payload = {
        **model_payload,
        "target_refs": [_ref_key(row) for row in target_refs],
        "candidate_refs": [_ref_key(row) for row in candidate_refs],
    }
    return RecallFact(
        **model_payload,
        target_evidence_refs=target_refs,
        candidate_evidence_refs=candidate_refs,
        result_hash=stable_hash(
            hash_payload,
            version="competitor_profile_recall_fact_v1",
        ),
    )


def _recalled_candidate(
    *,
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    facts: list[RecallFact],
    category_input_fingerprint: str,
    config: CandidateRecallConfig,
) -> RecalledCandidate:
    sources = sorted({row.entry_code for row in facts})
    evidence_refs = _dedupe_refs(
        row
        for fact in facts
        for row in (*fact.target_evidence_refs, *fact.candidate_evidence_refs)
    )
    unknown_reasons = sorted(
        {
            *(
                f"target_{code.lower()}_unknown"
                for code in COMPETITOR_PROFILE_SOURCE_MODULES
                if not target.records[code]
            ),
            *(
                f"candidate_{code.lower()}_unknown"
                for code in COMPETITOR_PROFILE_SOURCE_MODULES
                if not candidate.records[code]
            ),
        }
    )
    input_fingerprint = stable_hash(
        {
            "category_input_fingerprint": category_input_fingerprint,
            "target_sku_code": target.sku_code,
            "candidate_sku_code": candidate.sku_code,
            "config_version": config.config_version,
            "evidence_refs": [_ref_key(row) for row in evidence_refs],
        },
        version="competitor_profile_recalled_candidate_input_v1",
    )
    result_hash = stable_hash(
        {
            "input_fingerprint": input_fingerprint,
            "fact_hashes": [row.result_hash for row in facts],
            "unknown_reason_codes": unknown_reasons,
        },
        version="competitor_profile_recalled_candidate_result_v1",
    )
    return RecalledCandidate(
        candidate=candidate.identity,
        recall_sources=sources,
        recall_facts=facts,
        unknown_reason_codes=unknown_reasons,
        evidence_refs=evidence_refs,
        manifest_order_key=candidate.sku_code,
        input_fingerprint=input_fingerprint,
        result_hash=result_hash,
    )


def _entry_coverage(
    *,
    target: _SkuRecallFeatures,
    candidates: Sequence[RecalledCandidate],
    config: CandidateRecallConfig,
) -> dict[str, RecallEntryCoverage]:
    enabled = set(config.enabled_entries)
    result: dict[str, RecallEntryCoverage] = {}
    for entry_code in ALL_RECALL_ENTRY_CODES:
        candidate_rows = [
            row for row in candidates if entry_code in row.recall_sources
        ]
        reason_codes = sorted(
            {
                fact.reason_code
                for row in candidate_rows
                for fact in row.recall_facts
                if fact.entry_code == entry_code
            }
        )
        missing_modules = sorted(
            code for code in _ENTRY_MODULES[entry_code] if not target.records[code]
        )
        if entry_code not in enabled:
            status = "disabled"
        elif _entry_unavailable(entry_code, target):
            status = "unavailable"
        elif missing_modules:
            status = "partial"
        else:
            status = "available"
        payload = {
            "entry_code": entry_code,
            "status": status,
            "candidate_count": len(candidate_rows),
            "target_missing_modules": missing_modules,
            "reason_codes": reason_codes,
        }
        result[entry_code] = RecallEntryCoverage(
            **payload,
            result_hash=stable_hash(
                payload,
                version="competitor_profile_recall_entry_coverage_v1",
            ),
        )
    return result


def _entry_unavailable(entry_code: str, target: _SkuRecallFeatures) -> bool:
    present = {code for code, rows in target.records.items() if rows}
    if entry_code in {"same_purchase_pool", "same_brand_ladder"}:
        return not {"M03B", "M07"}.issubset(present)
    if entry_code == "market_reference":
        return "M07" not in present
    if entry_code in {"downtrade", "uptrade"}:
        return "M07" not in present or not (present & set(_SEMANTIC_MODULES))
    if entry_code == "scenario":
        return not (present & {"M09C", "M10C", "M11C"})
    if entry_code == "same_value":
        return not (present & {"M11C", "M12C", "M12D"})
    raise ValueError(f"unknown recall entry: {entry_code}")


def _product_form_compatible(
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    config: CandidateRecallConfig,
) -> bool | None:
    if target.product_category != candidate.product_category:
        return False
    if target.product_category == "TV":
        if target.screen_size_inch is not None and candidate.screen_size_inch is not None:
            return (
                abs(target.screen_size_inch - candidate.screen_size_inch)
                <= config.tv_screen_size_tolerance_inch
            )
        if target.size_segment and candidate.size_segment:
            return target.size_segment == candidate.size_segment
        return None
    if not target.ac_form or not candidate.ac_form:
        return None
    if target.ac_form != candidate.ac_form:
        return False
    if target.ac_capacity and candidate.ac_capacity:
        return target.ac_capacity == candidate.ac_capacity
    if target.size_segment and candidate.size_segment:
        return target.size_segment == candidate.size_segment
    return None


def _budget_bucket(
    price_gap_pct: Decimal | None,
    config: CandidateRecallConfig,
) -> str | None:
    if price_gap_pct is None:
        return None
    absolute = abs(price_gap_pct)
    if absolute <= config.same_budget_pct:
        return "same_budget"
    if absolute <= config.adjacent_budget_pct:
        return "adjacent_budget"
    return "outside_adjacent_budget"


def _performance_direction(
    target: _SkuRecallFeatures,
    candidate: _SkuRecallFeatures,
    config: CandidateRecallConfig,
) -> str | None:
    if (
        target.weekly_volume is None
        or candidate.weekly_volume is None
        or target.weekly_volume <= 0
        or candidate.weekly_volume <= 0
    ):
        return None
    ratio = candidate.weekly_volume / target.weekly_volume
    if ratio >= config.market_performance_ratio:
        return "higher_weekly_volume_market_reference"
    if ratio <= Decimal("1") / config.market_performance_ratio:
        return "lower_weekly_volume_market_reference"
    return None


def _market_values(
    row: _SkuRecallFeatures,
    price_gap_pct: Decimal | None,
) -> dict[str, Any]:
    return {
        "price_wavg": row.price,
        "weekly_volume": row.weekly_volume,
        "market_pool_key": row.market_pool_key,
        "size_segment": row.size_segment,
        "screen_size_inch": row.screen_size_inch,
        "ac_form": row.ac_form,
        "ac_capacity": row.ac_capacity,
        "candidate_price_gap_pct_to_target": price_gap_pct,
    }


def _price_gap_pct(
    target_price: Decimal | None,
    candidate_price: Decimal | None,
) -> Decimal | None:
    if target_price is None or candidate_price is None or target_price <= 0:
        return None
    return (candidate_price / target_price - Decimal("1")).quantize(
        Decimal("0.0001")
    )


def _weekly_volume(market: Mapping[str, Any]) -> Decimal | None:
    total = _decimal(market.get("sales_volume_total"))
    weeks = _decimal(market.get("active_week_count"))
    if total is None or weeks is None or weeks <= 0:
        return None
    return (total / weeks).quantize(Decimal("0.000001"))


def _evidence_refs(
    row: _SkuRecallFeatures,
    modules: Sequence[str],
) -> list[EvidenceRef]:
    return _dedupe_refs(
        _evidence_ref(record)
        for module_code in modules
        for record in row.records[module_code]
    )


def _evidence_ref(row: UpstreamRecordSnapshot) -> EvidenceRef:
    return EvidenceRef(
        module_code=row.module_code,
        profile_version=row.profile_version,
        rule_version=row.rule_version,
        taxonomy_version=row.taxonomy_version,
        record_type=row.record_type,
        record_id=row.record_id,
        result_hash=row.result_hash,
        source_batch_id=row.source_batch_id,
    )


def _dedupe_refs(values: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {_ref_key(row): row for row in values}
    return [by_key[key] for key in sorted(by_key)]


def _ref_key(row: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        row.module_code,
        row.source_batch_id or "",
        row.record_type,
        row.record_id,
        row.result_hash,
    )


def _first_facts(records: Sequence[UpstreamRecordSnapshot]) -> dict[str, Any]:
    return dict(records[0].facts) if records else {}


def _param_value(payload: Any, codes: Sequence[str]) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    lowered = {str(key).lower(): value for key, value in payload.items()}
    for code in codes:
        if code.lower() not in lowered:
            continue
        value = lowered[code.lower()]
        if isinstance(value, Mapping):
            for key in (
                "normalized_value",
                "value",
                "tier_code",
                "text",
                "raw_value",
            ):
                normalized = _known_text(value.get(key))
                if normalized:
                    return normalized
        normalized = _known_text(value)
        if normalized:
            return normalized
    return None


def _codes(*values: Any) -> list[str]:
    result: set[str] = set()
    for value in values:
        _collect_codes(value, result)
    return sorted(result)


def _collect_codes(value: Any, result: set[str]) -> None:
    if value is None:
        return
    if isinstance(value, str):
        normalized = _known_text(value)
        if normalized:
            result.add(normalized)
        return
    if isinstance(value, Mapping):
        code_keys = (
            "anchor_code",
            "reason_code",
            "claim_code",
            "value_code",
            "code",
        )
        found = False
        for key in code_keys:
            if key in value:
                found = True
                _collect_codes(value[key], result)
        if not found:
            for nested in value.values():
                if isinstance(nested, (list, tuple, set)):
                    _collect_codes(nested, result)
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            _collect_codes(item, result)


def _brand_key(value: str | None) -> str | None:
    if not value:
        return None
    normalized = "".join(character.lower() for character in value if character.isalnum())
    return normalized or None


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _known_text(value: Any) -> str | None:
    text = _text(value)
    if not text or text.lower() in {"-", "n/a", "na", "none", "null", "unknown"}:
        return None
    return text


__all__ = [
    "CandidateRecallEngine",
    "CandidateRecallError",
    "CandidateRecallScopeError",
]
