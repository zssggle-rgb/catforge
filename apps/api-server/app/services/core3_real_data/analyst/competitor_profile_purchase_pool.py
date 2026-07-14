"""Evaluate purchase-pool gates and battlefield overlap from G14 pair facts."""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairAlignedFeature,
    PairFeatureBundle,
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    BattlefieldCodeAssessment,
    BattlefieldOverlapSummary,
    PurchasePoolSemanticBundle,
    PurchasePoolSemanticConfig,
    PurchasePoolSemanticPairAssessment,
    assert_pair_feature_category,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceRef,
    GateResult,
    PurchasePoolAssessment,
)
from app.services.core3_real_data.hash_utils import stable_hash


_CURRENT_ROLES = frozenset({"primary", "secondary", "user_observed"})
_POSITIVE_ROLES = _CURRENT_ROLES | {"opportunity"}
_ROLE_ALIASES = {
    "drag": "drag",
    "drag_factor": "drag",
    "drag_factor_battlefield": "drag",
    "opportunity": "opportunity",
    "opportunity_battlefield": "opportunity",
    "primary": "primary",
    "primary_battlefield": "primary",
    "secondary": "secondary",
    "secondary_battlefield": "secondary",
    "user_observed": "user_observed",
    "user_observed_battlefield": "user_observed",
}
_G15_RELEVANT_MODULES = frozenset({"m03b", "m07", "m09c", "m11c", "m11d", "m12c"})


class PurchasePoolEvaluationError(RuntimeError):
    """Raised when G14 facts and the G15 evaluation scope conflict."""


class PurchasePoolSemanticEvaluator:
    """Classify purchase pools without evaluating formal competitor relations."""

    def evaluate(
        self,
        pair_bundle: PairFeatureBundle,
        config: PurchasePoolSemanticConfig,
    ) -> PurchasePoolSemanticBundle:
        try:
            assert_pair_feature_category(pair_bundle, config)
        except ValueError as exc:
            raise PurchasePoolEvaluationError(str(exc)) from exc
        self._assert_bundle(pair_bundle)
        pairs = [
            self._evaluate_pair(pair, config)
            for pair in sorted(
                pair_bundle.pairs,
                key=lambda row: row.candidate.sku_code,
            )
        ]
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair_bundle.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_purchase_pool_input_v1",
        )
        return PurchasePoolSemanticBundle(
            project_id=pair_bundle.project_id,
            category_code=pair_bundle.category_code,
            product_category=pair_bundle.product_category,
            release_scope_key=pair_bundle.release_scope_key,
            target=pair_bundle.target,
            candidate_count=len(pairs),
            pairs=pairs,
            config=config,
            pair_feature_result_hash=pair_bundle.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                {
                    "input_fingerprint": input_fingerprint,
                    "pair_hashes": {
                        row.candidate.sku_code: row.result_hash for row in pairs
                    },
                },
                version="competitor_profile_purchase_pool_result_v1",
            ),
        )

    @staticmethod
    def _assert_bundle(bundle: PairFeatureBundle) -> None:
        candidate_codes = [row.candidate.sku_code for row in bundle.pairs]
        if bundle.candidate_count != len(candidate_codes):
            raise PurchasePoolEvaluationError(
                "pair feature candidate count does not match pair rows"
            )
        if candidate_codes != sorted(set(candidate_codes)):
            raise PurchasePoolEvaluationError(
                "pair feature candidates must be sorted and unique"
            )
        if any(row.target != bundle.target for row in bundle.pairs):
            raise PurchasePoolEvaluationError(
                "pair feature target must be consistent across candidates"
            )

    def _evaluate_pair(
        self,
        pair: PairFeatureRecord,
        config: PurchasePoolSemanticConfig,
    ) -> PurchasePoolSemanticPairAssessment:
        battlefield = _battlefield_overlap(pair, config)
        target_tasks, candidate_tasks, task_refs = _task_roles(pair)
        shared_tasks = sorted(set(target_tasks) & set(candidate_tasks))
        shared_primary_tasks = sorted(
            code
            for code in shared_tasks
            if "primary" in target_tasks[code] and "primary" in candidate_tasks[code]
        )

        same_form, form_gate = _form_gate(pair, shared_primary_tasks)
        same_segment, segment_gate = _segment_gate(pair, shared_primary_tasks)
        budget_band, budget_gate = _budget_gate(pair, config)
        overlap_gate = _task_value_gate(
            pair,
            shared_tasks,
            battlefield,
            task_refs,
        )
        gates = sorted(
            [budget_gate, form_gate, segment_gate, overlap_gate],
            key=lambda row: row.gate_code,
        )
        level, limitations = _pool_level(
            gates=gates,
            same_form=same_form,
            same_segment=same_segment,
            budget_band=budget_band,
            shared_primary_tasks=shared_primary_tasks,
            battlefield=battlefield,
        )
        review_reasons = {
            reason
            for reason in [
                *pair.review_reason_codes,
                *pair.lineage_conflict_reason_codes,
            ]
            if _is_g15_review_reason(reason)
        }
        if battlefield.review_required:
            review_reasons.add("battlefield_role_conflict_requires_review")
        review_required = bool(review_reasons)
        confidence = _confidence(level, review_required)
        evidence_refs = _merge_refs(
            battlefield.evidence_refs,
            *(gate.evidence_refs for gate in gates),
        )
        purchase_pool_payload = {
            "level": level,
            "gate_results": [row.model_dump(mode="json") for row in gates],
            "confidence_level": confidence,
            "evidence_refs": [_ref_payload(ref) for ref in evidence_refs],
            "limitations": limitations,
        }
        purchase_pool = PurchasePoolAssessment(
            level=level,
            gate_results=gates,
            confidence_level=confidence,
            evidence_refs=evidence_refs,
            limitations=limitations,
            result_hash=stable_hash(
                purchase_pool_payload,
                version="competitor_profile_purchase_pool_assessment_v1",
            ),
        )
        input_fingerprint = stable_hash(
            {
                "pair_feature_result_hash": pair.result_hash,
                "config": config.model_dump(mode="json"),
            },
            version="competitor_profile_purchase_pool_pair_input_v1",
        )
        result_payload = {
            "target_sku_code": pair.target.sku_code,
            "candidate_sku_code": pair.candidate.sku_code,
            "candidate_status": pair.candidate_status,
            "purchase_pool_hash": purchase_pool.result_hash,
            "battlefield_overlap_hash": battlefield.result_hash,
            "shared_primary_task_codes": shared_primary_tasks,
            "shared_task_codes": shared_tasks,
            "budget_band": budget_band,
            "same_product_form": same_form,
            "same_size_or_capacity_segment": same_segment,
            "review_required": review_required,
            "review_reason_codes": sorted(review_reasons),
            "limitations": limitations,
            "pair_feature_result_hash": pair.result_hash,
            "config_version": config.config_version,
            "input_fingerprint": input_fingerprint,
        }
        return PurchasePoolSemanticPairAssessment(
            target=pair.target,
            candidate=pair.candidate,
            candidate_status=pair.candidate_status,
            purchase_pool=purchase_pool,
            battlefield_overlap=battlefield,
            shared_primary_task_codes=shared_primary_tasks,
            shared_task_codes=shared_tasks,
            budget_band=budget_band,
            same_product_form=same_form,
            same_size_or_capacity_segment=same_segment,
            review_required=review_required,
            review_reason_codes=sorted(review_reasons),
            limitations=limitations,
            evidence_refs=evidence_refs,
            pair_feature_result_hash=pair.result_hash,
            config_version=config.config_version,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_purchase_pool_pair_result_v1",
            ),
        )


def _battlefield_overlap(
    pair: PairFeatureRecord,
    config: PurchasePoolSemanticConfig,
) -> BattlefieldOverlapSummary:
    target_roles: dict[str, set[str]] = {}
    candidate_roles: dict[str, set[str]] = {}
    refs_by_code: dict[str, list[EvidenceRef]] = {}
    for feature in pair.aligned_features:
        if feature.feature_group in {"battlefield", "market_position"}:
            _merge_feature_roles(feature, target_roles, candidate_roles, refs_by_code)
        elif feature.feature_group == "claim_value":
            _merge_claim_context_roles(
                feature,
                target_roles,
                candidate_roles,
                refs_by_code,
            )

    assessments = [
        _battlefield_assessment(
            code,
            target_roles.get(code, set()),
            candidate_roles.get(code, set()),
            refs_by_code.get(code, []),
            config,
        )
        for code in sorted(set(target_roles) | set(candidate_roles))
    ]
    target_primary = sorted(
        code for code, roles in target_roles.items() if "primary" in roles
    )
    candidate_primary = sorted(
        code for code, roles in candidate_roles.items() if "primary" in roles
    )
    shared_positive = sorted(
        row.battlefield_code for row in assessments if row.positive_overlap
    )
    shared_discriminative = sorted(
        row.battlefield_code
        for row in assessments
        if row.supports_purchase_pool_overlap
    )
    supporting = sorted(
        row.battlefield_code
        for row in assessments
        if row.positive_overlap and row.classification != "discriminative"
    )
    target_drag = sorted(
        code for code, roles in target_roles.items() if "drag" in roles
    )
    candidate_drag = sorted(
        code for code, roles in candidate_roles.items() if "drag" in roles
    )
    target_current = {
        code for code, roles in target_roles.items() if roles & _CURRENT_ROLES
    }
    candidate_current = {
        code for code, roles in candidate_roles.items() if roles & _CURRENT_ROLES
    }
    if not target_current or not candidate_current:
        value_route_status = "unknown"
    elif target_current & candidate_current:
        value_route_status = "same"
    else:
        value_route_status = "different"
    evidence_refs = _merge_refs(*(row.evidence_refs for row in assessments))
    review_required = any(row.review_required for row in assessments)
    input_fingerprint = stable_hash(
        {
            "pair_feature_result_hash": pair.result_hash,
            "config_version": config.config_version,
            "taxonomy": {
                "generic": config.generic_value_codes,
                "table_stake": config.table_stake_value_codes,
                "discriminative": config.discriminative_value_codes,
                "coverage": {
                    code: str(value)
                    for code, value in config.value_coverage_ratios.items()
                },
                "generic_coverage_threshold": str(config.generic_coverage_threshold),
            },
        },
        version="competitor_profile_battlefield_overlap_input_v1",
    )
    result_payload = {
        "assessment_hashes": [row.result_hash for row in assessments],
        "target_primary_codes": target_primary,
        "candidate_primary_codes": candidate_primary,
        "shared_positive_codes": shared_positive,
        "shared_discriminative_codes": shared_discriminative,
        "supporting_or_generic_codes": supporting,
        "target_drag_codes": target_drag,
        "candidate_drag_codes": candidate_drag,
        "value_route_status": value_route_status,
        "review_required": review_required,
        "input_fingerprint": input_fingerprint,
    }
    return BattlefieldOverlapSummary(
        assessments=assessments,
        target_primary_codes=target_primary,
        candidate_primary_codes=candidate_primary,
        shared_positive_codes=shared_positive,
        shared_discriminative_codes=shared_discriminative,
        supporting_or_generic_codes=supporting,
        target_drag_codes=target_drag,
        candidate_drag_codes=candidate_drag,
        value_route_status=value_route_status,
        review_required=review_required,
        evidence_refs=evidence_refs,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            result_payload,
            version="competitor_profile_battlefield_overlap_result_v1",
        ),
    )


def _merge_feature_roles(
    feature: PairAlignedFeature,
    target_roles: dict[str, set[str]],
    candidate_roles: dict[str, set[str]],
    refs_by_code: dict[str, list[EvidenceRef]],
) -> None:
    target = {_normalize_role(value) for value in feature.target_values}
    candidate = {_normalize_role(value) for value in feature.candidate_values}
    target.discard(None)
    candidate.discard(None)
    if target:
        target_roles.setdefault(feature.feature_code, set()).update(target)
    if candidate:
        candidate_roles.setdefault(feature.feature_code, set()).update(candidate)
    if target or candidate:
        refs_by_code.setdefault(feature.feature_code, []).extend(
            [*feature.target_evidence_refs, *feature.candidate_evidence_refs]
        )


def _merge_claim_context_roles(
    feature: PairAlignedFeature,
    target_roles: dict[str, set[str]],
    candidate_roles: dict[str, set[str]],
    refs_by_code: dict[str, list[EvidenceRef]],
) -> None:
    for values, role_map, refs in (
        (feature.target_values, target_roles, feature.target_evidence_refs),
        (feature.candidate_values, candidate_roles, feature.candidate_evidence_refs),
    ):
        role = next(
            (
                normalized
                for value in values
                if value.startswith("role:")
                for normalized in [_normalize_role(value.removeprefix("role:"))]
                if normalized == "drag"
            ),
            None,
        )
        if role is None:
            continue
        for value in values:
            code = _battlefield_context_code(value)
            if not code:
                continue
            role_map.setdefault(code, set()).add(role)
            refs_by_code.setdefault(code, []).extend(refs)


def _battlefield_context_code(value: str) -> str | None:
    for prefix in ("context:battlefield:", "context:value_battlefield:"):
        if value.startswith(prefix):
            return value.removeprefix(prefix).strip() or None
    return None


def _normalize_role(value: str) -> str | None:
    return _ROLE_ALIASES.get(value.strip().lower())


def _battlefield_assessment(
    code: str,
    target_roles: set[str],
    candidate_roles: set[str],
    evidence_refs: Sequence[EvidenceRef],
    config: PurchasePoolSemanticConfig,
) -> BattlefieldCodeAssessment:
    classification, reason, coverage = _classify_value_code(code, config)
    overlap_type, positive_overlap, review_required = _overlap_type(
        target_roles,
        candidate_roles,
    )
    explicit_drag = "drag" in target_roles or "drag" in candidate_roles
    supports_purchase_pool = (
        classification == "discriminative"
        and positive_overlap
        and not explicit_drag
        and overlap_type != "shared_opportunity"
    )
    refs = _merge_refs(evidence_refs)
    payload = {
        "battlefield_code": code,
        "target_roles": sorted(target_roles),
        "candidate_roles": sorted(candidate_roles),
        "classification": classification,
        "classification_reason_code": reason,
        "coverage_ratio": str(coverage) if coverage is not None else None,
        "overlap_type": overlap_type,
        "positive_overlap": positive_overlap,
        "supports_purchase_pool_overlap": supports_purchase_pool,
        "explicit_drag": explicit_drag,
        "review_required": review_required,
        "evidence_refs": [_ref_payload(ref) for ref in refs],
    }
    return BattlefieldCodeAssessment(
        battlefield_code=code,
        target_roles=sorted(target_roles),
        candidate_roles=sorted(candidate_roles),
        classification=classification,
        classification_reason_code=reason,
        coverage_ratio=coverage,
        overlap_type=overlap_type,
        positive_overlap=positive_overlap,
        supports_purchase_pool_overlap=supports_purchase_pool,
        explicit_drag=explicit_drag,
        review_required=review_required,
        evidence_refs=refs,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_battlefield_code_assessment_v1",
        ),
    )


def _classify_value_code(
    code: str,
    config: PurchasePoolSemanticConfig,
) -> tuple[str, str, Decimal | None]:
    coverage = config.value_coverage_ratios.get(code)
    if code in config.table_stake_value_codes:
        return "table_stake", "taxonomy_table_stake", coverage
    if code in config.generic_value_codes:
        return "generic", "taxonomy_generic", coverage
    if coverage is not None and coverage >= config.generic_coverage_threshold:
        return "generic", "serving_scope_coverage_generic", coverage
    if code in config.discriminative_value_codes and coverage is not None:
        return (
            "discriminative",
            "taxonomy_specific_and_coverage_below_threshold",
            coverage,
        )
    if code in config.discriminative_value_codes:
        return "supporting", "coverage_unknown_not_discriminative", None
    if coverage is not None:
        return "supporting", "taxonomy_unclassified_supporting_only", coverage
    return "supporting", "taxonomy_and_coverage_unknown_supporting_only", None


def _overlap_type(
    target_roles: set[str],
    candidate_roles: set[str],
) -> tuple[str, bool, bool]:
    target_positive = target_roles & _POSITIVE_ROLES
    candidate_positive = candidate_roles & _POSITIVE_ROLES
    target_drag = "drag" in target_roles
    candidate_drag = "drag" in candidate_roles
    if (target_drag and candidate_positive) or (candidate_drag and target_positive):
        return "role_conflict", False, True
    if target_drag and candidate_drag:
        return "shared_drag", False, False
    if target_drag:
        return "target_drag", False, False
    if candidate_drag:
        return "candidate_drag", False, False
    if "primary" in target_roles and "primary" in candidate_roles:
        return "shared_primary", True, False
    if target_roles & _CURRENT_ROLES and candidate_roles & _CURRENT_ROLES:
        return "shared_current", True, False
    if "opportunity" in target_roles and candidate_roles & _CURRENT_ROLES:
        return "target_opportunity_candidate_current", True, False
    if "opportunity" in candidate_roles and target_roles & _CURRENT_ROLES:
        return "candidate_opportunity_target_current", True, False
    if "opportunity" in target_roles and "opportunity" in candidate_roles:
        return "shared_opportunity", True, False
    if target_roles and candidate_roles:
        return "role_conflict", False, True
    return (
        ("target_only", False, False)
        if target_roles
        else (
            "candidate_only",
            False,
            False,
        )
    )


def _task_roles(
    pair: PairFeatureRecord,
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[EvidenceRef]]:
    target: dict[str, set[str]] = {}
    candidate: dict[str, set[str]] = {}
    refs: list[EvidenceRef] = []
    for feature in pair.aligned_features:
        if feature.feature_group != "task":
            continue
        if feature.target_values:
            target[feature.feature_code] = set(feature.target_values)
        if feature.candidate_values:
            candidate[feature.feature_code] = set(feature.candidate_values)
        refs.extend(feature.target_evidence_refs)
        refs.extend(feature.candidate_evidence_refs)
    return target, candidate, _merge_refs(refs)


def _form_gate(
    pair: PairFeatureRecord,
    shared_primary_tasks: Sequence[str],
) -> tuple[bool | None, GateResult]:
    refs = _refs_for_modules(pair, "M03B", "M07")
    facts = pair.product_form_facts
    if facts.product_category == "TV":
        return True, _gate(
            "category_product_form_compatibility",
            True,
            True,
            "same_tv_product_form",
            refs,
        )
    if not facts.target_ac_form or not facts.candidate_ac_form:
        return None, _gate(
            "category_product_form_compatibility",
            False,
            None,
            "ac_product_form_unknown",
            refs,
        )
    same_form = facts.target_ac_form == facts.candidate_ac_form
    if same_form:
        reason = "same_ac_product_form"
        passed = True
    elif shared_primary_tasks:
        reason = "cross_form_shared_primary_task_scenario"
        passed = True
    else:
        reason = "cross_form_without_shared_primary_task"
        passed = False
    return same_form, _gate(
        "category_product_form_compatibility",
        True,
        passed,
        reason,
        refs,
    )


def _segment_gate(
    pair: PairFeatureRecord,
    shared_primary_tasks: Sequence[str],
) -> tuple[bool | None, GateResult]:
    refs = _refs_for_modules(pair, "M03B", "M07", "M09C")
    facts = pair.product_form_facts
    if facts.product_category == "TV":
        target = facts.target_screen_size_inch or facts.target_size_segment
        candidate = facts.candidate_screen_size_inch or facts.candidate_size_segment
        unknown_reason = "tv_size_segment_unknown"
    else:
        target = facts.target_ac_capacity or facts.target_size_segment
        candidate = facts.candidate_ac_capacity or facts.candidate_size_segment
        unknown_reason = "ac_capacity_segment_unknown"
    if target is None or candidate is None:
        return None, _gate(
            "size_capacity_task_substitutability",
            False,
            None,
            unknown_reason,
            refs,
        )
    same_segment = str(target).strip().lower() == str(candidate).strip().lower()
    if same_segment:
        reason = "same_size_or_capacity_segment"
        passed = True
    elif shared_primary_tasks:
        reason = "different_segment_shared_primary_task_scenario"
        passed = True
    else:
        reason = "different_segment_without_shared_primary_task"
        passed = False
    return same_segment, _gate(
        "size_capacity_task_substitutability",
        True,
        passed,
        reason,
        refs,
    )


def _budget_gate(
    pair: PairFeatureRecord,
    config: PurchasePoolSemanticConfig,
) -> tuple[str, GateResult]:
    refs = _refs_for_modules(pair, "M07")
    target = pair.market_comparison.target_weighted_price
    candidate = pair.market_comparison.candidate_weighted_price
    if target is None or candidate is None or target <= 0 or candidate <= 0:
        return "unknown", _gate(
            "budget_reachability",
            False,
            None,
            "positive_pair_price_unknown",
            refs,
        )
    gap_ratio = abs(candidate - target) / target
    if gap_ratio <= config.same_budget_max_gap_ratio:
        band = "same"
    elif gap_ratio <= config.adjacent_budget_max_gap_ratio:
        band = "adjacent"
    else:
        band = "outside"
    return band, _gate(
        "budget_reachability",
        True,
        band != "outside",
        f"budget_band_{band}",
        refs,
    )


def _task_value_gate(
    pair: PairFeatureRecord,
    shared_tasks: Sequence[str],
    battlefield: BattlefieldOverlapSummary,
    task_refs: Sequence[EvidenceRef],
) -> GateResult:
    task_known = _module_pair_available(pair, "M09C")
    battlefield_known = _module_pair_available(pair, "M11C") or (
        _module_pair_available(pair, "M11D")
    )
    refs = _merge_refs(task_refs, battlefield.evidence_refs)
    if not task_known and not battlefield_known:
        return _gate(
            "task_value_scene_overlap",
            False,
            None,
            "task_and_value_scene_sources_unknown",
            refs,
        )
    if shared_tasks:
        return _gate(
            "task_value_scene_overlap",
            True,
            True,
            "shared_user_task",
            refs,
        )
    if battlefield.shared_discriminative_codes:
        return _gate(
            "task_value_scene_overlap",
            True,
            True,
            "shared_discriminative_value_scene",
            refs,
        )
    return _gate(
        "task_value_scene_overlap",
        True,
        False,
        "no_shared_task_or_discriminative_value_scene",
        refs,
    )


def _pool_level(
    *,
    gates: Sequence[GateResult],
    same_form: bool | None,
    same_segment: bool | None,
    budget_band: str,
    shared_primary_tasks: Sequence[str],
    battlefield: BattlefieldOverlapSummary,
) -> tuple[str, list[str]]:
    limitations: set[str] = set()
    if any(not gate.known for gate in gates):
        limitations.update(
            f"required_gate_unknown:{gate.gate_code}"
            for gate in gates
            if not gate.known
        )
        return "unknown", sorted(limitations)
    shared_current_discriminative = any(
        row.supports_purchase_pool_overlap
        and row.overlap_type in {"shared_primary", "shared_current"}
        for row in battlefield.assessments
    )
    if (
        same_form is True
        and same_segment is True
        and budget_band == "same"
        and shared_primary_tasks
        and shared_current_discriminative
    ):
        return "P0", []
    if (
        same_form is True
        and same_segment is True
        and budget_band in {"same", "adjacent"}
        and shared_primary_tasks
        and battlefield.value_route_status == "different"
    ):
        return "P1", []
    all_gates_pass = all(gate.passed is True for gate in gates)
    if (
        all_gates_pass
        and budget_band in {"same", "adjacent"}
        and shared_primary_tasks
        and (same_form is False or same_segment is False)
    ):
        return "P2", []
    limitations.add("market_reference_only_not_purchase_choice")
    if battlefield.value_route_status == "unknown":
        limitations.add("value_route_unknown")
    if not shared_primary_tasks:
        limitations.add("no_shared_primary_task")
    if budget_band == "outside":
        limitations.add("budget_outside_reachable_range")
    return "P3", sorted(limitations)


def _confidence(level: str, review_required: bool) -> str:
    if level == "unknown":
        return "unknown"
    if review_required or level == "P3":
        return "low"
    return "high" if level == "P0" else "medium"


def _is_g15_review_reason(reason: str) -> bool:
    normalized = reason.lower()
    return any(
        f"_{module}_" in normalized or normalized.startswith(f"{module}_")
        for module in _G15_RELEVANT_MODULES
    )


def _gate(
    gate_code: str,
    known: bool,
    passed: bool | None,
    reason_code: str,
    evidence_refs: Sequence[EvidenceRef],
) -> GateResult:
    return GateResult(
        gate_code=gate_code,
        required=True,
        known=known,
        passed=passed,
        reason_code=reason_code,
        evidence_refs=_merge_refs(evidence_refs),
    )


def _module_pair_available(pair: PairFeatureRecord, module_code: str) -> bool:
    row = next(
        item for item in pair.module_availability if item.module_code == module_code
    )
    return (
        row.target_availability == "present" and row.candidate_availability == "present"
    )


def _refs_for_modules(
    pair: PairFeatureRecord,
    *module_codes: str,
) -> list[EvidenceRef]:
    allowed = set(module_codes)
    return _merge_refs(ref for ref in pair.evidence_refs if ref.module_code in allowed)


def _merge_refs(*groups: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    unique: dict[tuple[str, str, str, str, str], EvidenceRef] = {}
    for group in groups:
        for ref in group:
            unique[_ref_key(ref)] = ref
    return [unique[key] for key in sorted(unique)]


def _ref_key(ref: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        ref.module_code,
        ref.source_batch_id or "",
        ref.record_type,
        ref.record_id,
        ref.result_hash,
    )


def _ref_payload(ref: EvidenceRef) -> Mapping[str, object]:
    return ref.model_dump(mode="json")


__all__ = [
    "PurchasePoolEvaluationError",
    "PurchasePoolSemanticEvaluator",
]
