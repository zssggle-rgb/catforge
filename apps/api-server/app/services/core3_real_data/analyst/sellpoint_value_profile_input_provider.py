"""Production read path for materializing stored sellpoint-value profiles."""

from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.analyst_repository import (
    AnalystRepository,
    batch_ids_from_scope,
)
from app.services.core3_real_data.analyst.analyst_schemas import (
    AnalystContext,
    AnalystStatus,
)
from app.services.core3_real_data.analyst.atomic_handlers import AtomicAnalystHandlers
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    EvidenceRef,
    SellpointValueV4Context,
    SkuEvidenceSnapshot,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    _value_unit_by_code,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    adapt_v4_context_to_v5,
    build_perceived_value_market_report,
    sellpoint_value_v5_method_configs,
)
from app.services.core3_real_data.analyst.claim_value_pm_v5_schemas import (
    ValueAccountRow,
)
from app.services.core3_real_data.analyst.competitor_answer import CLAIM_LABELS_CN
from app.services.core3_real_data.analyst.sellpoint_value_profile_candidate_service import (
    candidate_manifest_as_v4_context_pool,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer_schemas import (
    ProfileSourceLineage,
    REQUIRED_PROFILE_SOURCE_MODULES,
    SellpointValueMaterializationInput,
    SellpointValueVersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    CandidateUniverseManifest,
    CapabilityCandidateFact,
    CapabilityComparisonScope,
    CapabilityFactStatus,
    CapabilityInvestmentInput,
    MarketEvidenceStatus,
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_thresholds import (
    DECISION_HASH_VERSION,
    classify_capability_investments,
)
from app.services.core3_real_data.hash_utils import stable_hash


PROFILE_INPUT_PROVIDER_VERSION = "sellpoint_value_profile_input_provider_v1"
CANDIDATE_UNIVERSE_METHOD_VERSION = "sellpoint_value_candidate_universe_v1"
CAPABILITY_LABELS_CN = {
    **CLAIM_LABELS_CN,
    "tv_claim_art_frame": "艺术画框外观",
    "tv_claim_large_screen": "大屏观看",
    "tv_claim_wall_mount": "贴墙安装",
}


class SellpointValueProfileInputError(RuntimeError):
    """Raised when authoritative inputs cannot produce a materialization input."""


class AnalystSellpointValueMaterializationInputProvider:
    """Compose existing audited read models into one deterministic profile input."""

    def __init__(
        self,
        *,
        repository: AnalystRepository,
        atomic_handlers: AtomicAnalystHandlers | None = None,
    ) -> None:
        self.repository = repository
        self.atomic_handlers = atomic_handlers or AtomicAnalystHandlers(repository)

    def list_authoritative_sku_codes(
        self,
        request: SellpointValueVersionRequest,
    ) -> Sequence[str]:
        return self.repository.list_authoritative_sku_codes(
            batch_id=_source_batch_scope_id(request),
            product_category=_source_scope_text(
                request, "product_category", request.category_code
            ),
            market_window=_source_scope_text(
                request, "market_window", "full_observed_window"
            ),
        )

    def load_materialization_input(
        self,
        request: SellpointValueVersionRequest,
        sku_code: str,
    ) -> SellpointValueMaterializationInput:
        context = _analyst_context(request)
        candidate_payload = self.atomic_handlers.sellpoint_value_candidate_universe(
            context,
            sku_code=sku_code,
        )
        candidate_universe = CandidateUniverseManifest.model_validate(
            _atom_result(
                candidate_payload,
                command="sellpoint-value-candidate-universe",
                result_key="candidate_universe",
                sku_code=sku_code,
            )
        )
        _assert_candidate_scope(request, candidate_universe, sku_code)
        v4_payload = self.atomic_handlers.sellpoint_value_v4_context(
            context,
            sku_code=sku_code,
            fallback_candidates=candidate_manifest_as_v4_context_pool(
                candidate_universe
            ),
            m12d_profile_version=_optional_scope_text(
                request, "m12d_profile_version"
            ),
        )
        v4_context = SellpointValueV4Context.model_validate(
            _atom_result(
                v4_payload,
                command="sellpoint-value-pm-v4",
                result_key="sellpoint_value_v4_context",
                sku_code=sku_code,
            )
        )
        _assert_v4_scope(request, v4_context, sku_code)
        v5_context = adapt_v4_context_to_v5(
            v4_context,
            candidate_universe=candidate_universe,
        )
        report = build_perceived_value_market_report(v5_context)
        threshold_config = capability_threshold_config(request.category_code)
        investment_inputs = build_capability_investment_inputs(
            v4_context=v4_context,
            report_rows=report.value_account_rows,
            candidate_universe=candidate_universe,
        )
        source_lineage = build_profile_source_lineage(
            v4_context=v4_context,
            candidate_universe=candidate_universe,
        )
        limitations = sorted(
            set(
                [
                    *candidate_universe.limitations,
                    *(
                        issue.code
                        for issue in v4_context.lineage_gate.issues
                        if issue.severity == "blocking"
                    ),
                    *(
                        [f"v5_analysis_{report.analysis_state}"]
                        if report.analysis_state != "ready"
                        else []
                    ),
                ]
            )
        )
        return SellpointValueMaterializationInput(
            project_id=request.project_id,
            category_code=request.category_code,
            batch_id=request.batch_id,
            source_batch_scope_id=_source_batch_scope_id(request),
            profile_version=request.profile_version,
            target=v4_context.target,
            source_lineage=source_lineage,
            current_source_hashes={
                row.module_code: list(row.result_hashes)
                for row in source_lineage
                if row.status == "present"
            },
            candidate_universe=candidate_universe,
            threshold_config=threshold_config,
            investment_decisions=classify_capability_investments(
                investment_inputs,
                configs={request.category_code: threshold_config},
            ),
            v5_report=report,
            method_versions=request.method_versions,
            generated_by=request.generated_by,
            limitations=limitations,
        )


def build_production_version_request(
    *,
    provider: AnalystSellpointValueMaterializationInputProvider,
    project_id: str,
    category_code: str,
    batch_id: str,
    profile_version: str,
    product_category: str,
    market_window: str,
    analysis_population: str,
    generated_by: str,
    m12d_profile_version: str | None = None,
    source_batch_scope_id: str | None = None,
) -> SellpointValueVersionRequest:
    method_versions = production_method_versions(category_code)
    provisional = SellpointValueVersionRequest(
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        profile_version=profile_version,
        method_versions=method_versions,
        source_scope={
            "modules": list(REQUIRED_PROFILE_SOURCE_MODULES),
            "product_category": product_category.upper(),
            "market_window": market_window,
            "analysis_population": analysis_population,
            "m12d_profile_version": m12d_profile_version,
            "source_batch_scope_id": source_batch_scope_id or batch_id,
            "source_batch_ids": list(
                batch_ids_from_scope(source_batch_scope_id or batch_id)
            ),
        },
        version_input_fingerprint="pending",
        candidate_universe_fingerprint="pending",
        version_result_hash="pending",
        generated_by=generated_by,
    )
    sku_codes = sorted(set(provider.list_authoritative_sku_codes(provisional)))
    source_scope = {
        **provisional.source_scope,
        "authoritative_sku_count": len(sku_codes),
        "authoritative_sku_codes_hash": stable_hash(
            sku_codes,
            version="sellpoint_value_authoritative_sku_scope_v1",
        ),
    }
    version_input_fingerprint = stable_hash(
        {
            "project_id": project_id,
            "category_code": category_code,
            "batch_id": batch_id,
            "profile_version": profile_version,
            "source_scope": source_scope,
            "method_versions": method_versions,
        },
        version=PROFILE_INPUT_PROVIDER_VERSION,
    )
    candidate_universe_fingerprint = stable_hash(
        {
            "sku_codes": sku_codes,
            "candidate_method": CANDIDATE_UNIVERSE_METHOD_VERSION,
            "batch_id": batch_id,
        },
        version="sellpoint_value_candidate_universe_scope_v1",
    )
    version_result_hash = stable_hash(
        {
            "version_input_fingerprint": version_input_fingerprint,
            "candidate_universe_fingerprint": candidate_universe_fingerprint,
            "profile_method": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        },
        version="sellpoint_value_profile_version_result_v1",
    )
    return provisional.model_copy(
        update={
            "source_scope": source_scope,
            "version_input_fingerprint": version_input_fingerprint,
            "candidate_universe_fingerprint": candidate_universe_fingerprint,
            "version_result_hash": version_result_hash,
        }
    )


def production_method_versions(category_code: str) -> dict[str, str]:
    threshold = capability_threshold_config(category_code)
    v5 = sellpoint_value_v5_method_configs()
    return {
        "profile": SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        "input_provider": PROFILE_INPUT_PROVIDER_VERSION,
        "candidate_universe": CANDIDATE_UNIVERSE_METHOD_VERSION,
        "capability_investment": DECISION_HASH_VERSION,
        "capability_threshold": threshold.config_version,
        "counterfactual_recall": v5.recall_version,
        "synthetic_control": v5.synthetic_version,
        "performance_archetype": v5.archetype_version,
        "battlefield_expansion": v5.expansion_version,
        "amount": v5.amount_version,
    }


def build_profile_source_lineage(
    *,
    v4_context: SellpointValueV4Context,
    candidate_universe: CandidateUniverseManifest,
) -> list[ProfileSourceLineage]:
    authority_by_module = {
        row.module_code: row for row in v4_context.authority_manifest
    }
    refs_by_module: dict[str, list[EvidenceRef]] = defaultdict(list)
    for ref in v4_context.evidence_refs:
        refs_by_module[ref.module_code].append(ref)
    result = []
    for module_code in REQUIRED_PROFILE_SOURCE_MODULES:
        if module_code in {"M12", "M13"}:
            result.append(
                _candidate_source_lineage(module_code, candidate_universe)
            )
            continue
        authority = authority_by_module.get(module_code)
        refs = refs_by_module.get(module_code, [])
        hashes = sorted(
            set(
                [
                    *(ref.result_hash for ref in refs if ref.result_hash),
                    *(
                        [authority.source_hash]
                        if authority is not None and authority.source_hash
                        else []
                    ),
                ]
            )
        )
        record_ids = sorted(set(ref.record_id for ref in refs if ref.record_id))
        if authority is None or authority.availability == "missing":
            status = "missing"
            limitations = [f"{module_code.lower()}_source_missing"]
        elif authority.usability == "unusable":
            status = "conflict"
            limitations = sorted(
                set([*authority.warnings, f"{module_code.lower()}_source_conflict"])
            )
        elif not hashes:
            status = "missing"
            limitations = [f"{module_code.lower()}_result_hash_missing"]
        else:
            status = "present"
            limitations = sorted(set(authority.warnings))
        result.append(
            ProfileSourceLineage(
                module_code=module_code,
                status=status,
                rule_versions=(
                    [authority.rule_version]
                    if authority is not None and authority.rule_version
                    else []
                ),
                result_hashes=hashes if status == "present" else [],
                record_ids=record_ids if status == "present" else [],
                limitations=limitations,
            )
        )
    return sorted(result, key=lambda row: row.module_code)


def build_capability_investment_inputs(
    *,
    v4_context: SellpointValueV4Context,
    report_rows: Sequence[ValueAccountRow],
    candidate_universe: CandidateUniverseManifest,
) -> list[CapabilityInvestmentInput]:
    snapshots = [
        row
        for row in v4_context.candidate_snapshots
        if _is_competitor_snapshot(row)
    ]
    snapshot_by_code = {row.identity.sku_code: row for row in snapshots}
    candidate_codes = sorted(snapshot_by_code)
    target = v4_context.target_snapshot
    rows_by_capability: dict[str, list[ValueAccountRow]] = defaultdict(list)
    names: dict[str, str] = {}
    member_statuses: dict[str, list[str]] = defaultdict(list)
    member_tiers: dict[str, list[str]] = defaultdict(list)
    threshold_config = capability_threshold_config(v4_context.category_code)
    for row in report_rows:
        for member in row.sellpoint_bundle.members:
            rows_by_capability[member.capability_code].append(row)
            names.setdefault(member.capability_code, member.capability_name_cn)
            member_statuses[member.capability_code].append(member.fact_status)
            member_tiers[member.capability_code].append(member.business_tier)
            definition = _value_unit_by_code(v4_context.category_code).get(
                member.capability_code
            )
            if definition is None:
                continue
            for claim_code in definition.claim_codes:
                if _snapshot_capability_status(target, claim_code) != "known_present":
                    continue
                rows_by_capability[claim_code].append(row)
                names.setdefault(
                    claim_code,
                    CAPABILITY_LABELS_CN.get(claim_code, claim_code),
                )
                member_statuses[claim_code].append("confirmed")
                member_tiers[claim_code].append("unknown")

    all_codes = set(rows_by_capability)
    all_codes.update(
        _eligible_missing_gap_codes(
            target=target,
            candidates=snapshots,
            minimum_known_count=threshold_config.minimum_known_count,
            prevalence_threshold=threshold_config.prevalence_threshold,
        )
    )
    inputs = []
    for capability_code in sorted(all_codes):
        rows = rows_by_capability.get(capability_code, [])
        candidate_facts = [
            CapabilityCandidateFact(
                candidate_sku_code=snapshot.identity.sku_code,
                fact_status=_snapshot_capability_status(snapshot, capability_code),
                evidence_refs=_snapshot_evidence_refs(snapshot, capability_code),
            )
            for snapshot in snapshots
        ]
        target_status = (
            _member_target_status(member_statuses[capability_code])
            if capability_code in member_statuses
            else _snapshot_capability_status(target, capability_code)
        )
        market_signals = _market_signals(
            target=target,
            candidates=snapshot_by_code,
            candidate_facts=candidate_facts,
            rows=rows,
        )
        relative_experience_status = _relative_experience_status(rows)
        scope = _comparison_scope(
            v4_context=v4_context,
            candidate_universe=candidate_universe,
            candidate_codes=candidate_codes,
            battlefield_codes=[
                str(row.battlefield.get("code") or "")
                for row in rows
                if row.battlefield.get("code")
            ],
        )
        inputs.append(
            CapabilityInvestmentInput(
                capability_code=capability_code,
                capability_name_cn=(
                    names.get(capability_code)
                    or CAPABILITY_LABELS_CN.get(capability_code)
                    or capability_code
                ),
                target_fact_status=target_status,
                target_value=_target_value(rows, capability_code),
                investment_level=_investment_level(
                    member_tiers.get(capability_code, [])
                ),
                candidate_facts=candidate_facts,
                comparison_scope=scope,
                user_feedback_status=_user_feedback_status(rows),
                relative_experience_status=relative_experience_status,
                competitor_experience_stronger=(
                    True
                    if relative_experience_status == "weaker"
                    else False
                    if relative_experience_status in {"advantage", "parity"}
                    else None
                ),
                price_support=market_signals["price"],
                volume_support=market_signals["volume"],
                choice_support=market_signals["choice"],
                current_competitive_performance=market_signals["performance"],
                experience_outcomes=sorted(
                    set(
                        str(row.perceived_user_value.get("outcome_cn") or "")
                        for row in rows
                        if row.perceived_user_value.get("outcome_cn")
                    )
                ),
                evidence_refs=_dedupe_evidence_refs(
                    [
                        *_snapshot_evidence_refs(target, capability_code),
                        *(
                            ref
                            for fact in candidate_facts
                            for ref in fact.evidence_refs
                        ),
                    ]
                ),
                limitations=(
                    ["capability_not_linked_to_observed_value_row"]
                    if not rows
                    else []
                ),
            )
        )
    return inputs


def _atom_result(
    payload: dict[str, Any],
    *,
    command: str,
    result_key: str,
    sku_code: str,
) -> Any:
    if payload.get("status") != AnalystStatus.OK.value:
        message = payload.get("message_cn") or payload.get("limitations") or "unknown"
        raise SellpointValueProfileInputError(
            f"{command} failed for {sku_code}: {message}"
        )
    result = payload.get("result") or {}
    if result_key not in result:
        raise SellpointValueProfileInputError(
            f"{command} did not return {result_key} for {sku_code}"
        )
    return result[result_key]


def _assert_candidate_scope(
    request: SellpointValueVersionRequest,
    manifest: CandidateUniverseManifest,
    sku_code: str,
) -> None:
    if (
        manifest.project_id != request.project_id
        or manifest.category_code != request.category_code
        or manifest.batch_id != _source_batch_scope_id(request)
        or manifest.target_sku_code != sku_code
    ):
        raise SellpointValueProfileInputError(
            f"candidate universe scope mismatch for {sku_code}"
        )


def _assert_v4_scope(
    request: SellpointValueVersionRequest,
    context: SellpointValueV4Context,
    sku_code: str,
) -> None:
    if (
        context.project_id != request.project_id
        or context.category_code != request.category_code
        or context.requested_batch_id != _source_batch_scope_id(request)
        or context.target.sku_code != sku_code
    ):
        raise SellpointValueProfileInputError(f"V4 context scope mismatch for {sku_code}")


def _analyst_context(request: SellpointValueVersionRequest) -> AnalystContext:
    return AnalystContext(
        project_id=request.project_id,
        category_code=request.category_code,
        batch_id=_source_batch_scope_id(request),
        product_category=_source_scope_text(
            request, "product_category", request.category_code
        ),
        market_window=_source_scope_text(
            request, "market_window", "full_observed_window"
        ),
        analysis_population=_source_scope_text(
            request, "analysis_population", "fact_complete_with_comment"
        ),
    )


def _source_scope_text(
    request: SellpointValueVersionRequest,
    key: str,
    default: str,
) -> str:
    return str(request.source_scope.get(key) or default)


def _source_batch_scope_id(request: SellpointValueVersionRequest) -> str:
    return _source_scope_text(request, "source_batch_scope_id", request.batch_id)


def _optional_scope_text(
    request: SellpointValueVersionRequest,
    key: str,
) -> str | None:
    value = str(request.source_scope.get(key) or "").strip()
    return value or None


def _candidate_source_lineage(
    module_code: str,
    manifest: CandidateUniverseManifest,
) -> ProfileSourceLineage:
    hashes = sorted(
        set(
            row.source_hashes[module_code]
            for row in manifest.competitor_candidates
            if row.source_hashes.get(module_code)
        )
    )
    record_ids = sorted(
        row.source_record_ids[module_code]
        for row in manifest.competitor_candidates
        if row.source_record_ids.get(module_code)
    )
    if hashes:
        return ProfileSourceLineage(
            module_code=module_code,
            status="present",
            rule_versions=[
                manifest.m12_rule_version
                if module_code == "M12"
                else manifest.m13_rule_version
            ],
            result_hashes=hashes,
            record_ids=record_ids,
        )
    return ProfileSourceLineage(
        module_code=module_code,
        status="missing",
        rule_versions=[
            manifest.m12_rule_version
            if module_code == "M12"
            else manifest.m13_rule_version
        ],
        limitations=[f"{module_code.lower()}_source_missing"],
    )


def _member_target_status(statuses: Sequence[str]) -> CapabilityFactStatus:
    status_set = set(statuses)
    if "conflict" in status_set:
        return "contradicted"
    if status_set & {"confirmed", "partial"}:
        return "known_present"
    return "missing"


def _snapshot_capability_status(
    snapshot: SkuEvidenceSnapshot,
    capability_code: str,
) -> CapabilityFactStatus:
    definition = _value_unit_by_code(snapshot.identity.product_category).get(
        capability_code
    )
    if definition is not None:
        claim_statuses = [
            _direct_claim_status(snapshot, code) for code in definition.claim_codes
        ]
        if "known_present" in claim_statuses or any(
            _contains_code(snapshot.facts.get("parameter_fact") or {}, code)
            for code in definition.param_codes
        ):
            return "known_present"
        if "contradicted" in claim_statuses:
            return "contradicted"
        if claim_statuses and all(
            status == "known_absent" for status in claim_statuses
        ):
            return "known_absent"
        return "missing"
    return _direct_claim_status(snapshot, capability_code)


def _direct_claim_status(
    snapshot: SkuEvidenceSnapshot,
    capability_code: str,
) -> CapabilityFactStatus:
    claim_fact = snapshot.facts.get("claim_fact") or {}
    comment_fact = snapshot.facts.get("comment_fact") or {}
    fact_codes = _string_set(claim_fact.get("fact_claim_codes"))
    advertised_codes = _string_set(claim_fact.get("claim_codes"))
    unsupported_codes = _string_set(claim_fact.get("unsupported_claim_codes"))
    supported_codes = _string_set(comment_fact.get("supported_claim_codes"))
    contradicted_codes = _string_set(comment_fact.get("contradicted_claim_codes"))
    if capability_code in contradicted_codes or capability_code in unsupported_codes:
        return "contradicted"
    if capability_code in fact_codes or capability_code in advertised_codes:
        return "known_present"
    if capability_code in supported_codes:
        return "known_present"
    claim_status = snapshot.source_status.get("M04C")
    if (
        claim_status is not None
        and claim_status.availability == "present"
        and claim_status.usability == "usable"
        and capability_code.startswith(("tv_claim_", "ac_claim_"))
    ):
        return "known_absent"
    parameter_fact = snapshot.facts.get("parameter_fact") or {}
    if capability_code.startswith(("tv_param_", "ac_param_")) and _contains_code(
        parameter_fact, capability_code
    ):
        return "known_present"
    return "missing"


def _eligible_missing_gap_codes(
    *,
    target: SkuEvidenceSnapshot,
    candidates: Sequence[SkuEvidenceSnapshot],
    minimum_known_count: int,
    prevalence_threshold: float,
) -> list[str]:
    target_status = target.source_status.get("M04C")
    if (
        target_status is None
        or target_status.availability != "present"
        or target_status.usability != "usable"
    ):
        return []
    target_codes = _snapshot_claim_codes(target)
    candidate_codes = sorted(
        set(
            code
            for snapshot in candidates
            for code in _snapshot_claim_codes(snapshot)
            if code in CAPABILITY_LABELS_CN
        )
        - target_codes
    )
    result = []
    for code in candidate_codes:
        statuses = [_snapshot_capability_status(row, code) for row in candidates]
        known = sum(status in {"known_present", "known_absent"} for status in statuses)
        present = sum(status == "known_present" for status in statuses)
        if known >= minimum_known_count and present / known >= prevalence_threshold:
            result.append(code)
    return result


def _snapshot_claim_codes(snapshot: SkuEvidenceSnapshot) -> set[str]:
    claim_fact = snapshot.facts.get("claim_fact") or {}
    comment_fact = snapshot.facts.get("comment_fact") or {}
    return set().union(
        _string_set(claim_fact.get("claim_codes")),
        _string_set(claim_fact.get("fact_claim_codes")),
        _string_set(comment_fact.get("supported_claim_codes")),
    )


def _is_competitor_snapshot(snapshot: SkuEvidenceSnapshot) -> bool:
    source = snapshot.facts.get("candidate_source") or {}
    return source.get("authority_eligible") is not False


def _comparison_scope(
    *,
    v4_context: SellpointValueV4Context,
    candidate_universe: CandidateUniverseManifest,
    candidate_codes: Sequence[str],
    battlefield_codes: Sequence[str],
) -> CapabilityComparisonScope:
    target = v4_context.target_snapshot.identity
    snapshots = {
        row.identity.sku_code: row for row in v4_context.candidate_snapshots
    }
    same_form = [
        _same_product_form(v4_context.target_snapshot, snapshots[code])
        for code in candidate_codes
        if code in snapshots
    ]
    size_relation = (
        "same_product_form"
        if same_form and all(same_form)
        else "mixed_product_form"
        if same_form
        else None
    )
    product_form = (
        f"TV_{target.screen_size_inch:g}_inch"
        if target.product_category.upper() == "TV" and target.screen_size_inch
        else f"AC_{target.size_tier}"
        if target.product_category.upper() == "AC" and target.size_tier
        else None
    )
    competitor_roles = sorted(
        set(
            role
            for row in candidate_universe.competitor_candidates
            if row.candidate_sku_code in set(candidate_codes)
            for role in row.relation_types
        )
    )
    payload = {
        "category_code": v4_context.category_code,
        "price_band": target.price_band,
        "product_form": product_form,
        "size_relation": size_relation,
        "battlefield_codes": sorted(set(battlefield_codes)),
        "competitor_roles": competitor_roles,
        "candidate_scope_ids": sorted(set(candidate_codes)),
    }
    return CapabilityComparisonScope(
        **payload,
        scope_hash=stable_hash(
            payload,
            version="sellpoint_value_capability_scope_v1",
        ),
    )


def _same_product_form(
    target: SkuEvidenceSnapshot,
    candidate: SkuEvidenceSnapshot,
) -> bool:
    if target.identity.product_category.upper() == "AC":
        return bool(target.identity.size_tier) and (
            target.identity.size_tier == candidate.identity.size_tier
        )
    return bool(
        target.identity.screen_size_inch is not None
        and candidate.identity.screen_size_inch is not None
        and abs(
            target.identity.screen_size_inch
            - candidate.identity.screen_size_inch
        )
        <= 0.5
    )


def _target_value(
    rows: Sequence[ValueAccountRow],
    capability_code: str,
) -> str | None:
    summaries = [
        member.fact_summary_cn
        for row in rows
        for member in row.sellpoint_bundle.members
        if member.capability_code == capability_code and member.fact_summary_cn
    ]
    return "；".join(dict.fromkeys(summaries)) or None


def _investment_level(tiers: Sequence[str]) -> str:
    tier_set = set(tiers)
    if tier_set & {"premium", "flagship"}:
        return "high"
    if "enhanced" in tier_set:
        return "standard"
    if "base" in tier_set:
        return "low"
    return "unknown"


def _user_feedback_status(rows: Sequence[ValueAccountRow]) -> str:
    statuses = {row.value_status for row in rows}
    if statuses & {"conflicted", "observed_mixed"}:
        return "conflicted"
    if "observed_negative" in statuses:
        return "negative"
    if "observed_positive" in statuses:
        return (
            "realized_advantage"
            if any("relative_value" in row.highlight_types for row in rows)
            else "realized"
        )
    if "partial" in statuses:
        return "partial"
    if "not_observed" in statuses:
        return "not_observed"
    return "unknown"


def _relative_experience_status(rows: Sequence[ValueAccountRow]) -> str:
    statuses = {row.value_status for row in rows}
    if statuses & {"conflicted", "observed_mixed"}:
        return "conflicted"
    if "observed_negative" in statuses:
        return "weaker"
    if any("relative_value" in row.highlight_types for row in rows):
        return "advantage"
    if any(
        comparison.method == "same_claim_different_realization"
        for row in rows
        for comparison in row.price_realization.realization_comparisons
    ):
        return "advantage" if "observed_positive" in statuses else "parity"
    return "unknown"


def _market_signals(
    *,
    target: SkuEvidenceSnapshot,
    candidates: dict[str, SkuEvidenceSnapshot],
    candidate_facts: Sequence[CapabilityCandidateFact],
    rows: Sequence[ValueAccountRow],
) -> dict[str, str]:
    price_values = []
    volume_values = []
    for row in rows:
        for comparison in row.price_realization.realization_comparisons:
            if comparison.price_gap_abs is not None:
                price_values.append(comparison.price_gap_abs)
            if comparison.sales_volume_gap_abs is not None:
                volume_values.append(comparison.sales_volume_gap_abs)
        if (
            row.price_realization.strict_bundle_interval is not None
            and row.price_realization.strict_bundle_interval.status == "available"
        ):
            price_values.append(1.0)
        for comparison in row.volume_realization.realization_comparisons:
            if comparison.sales_volume_gap_abs is not None:
                volume_values.append(comparison.sales_volume_gap_abs)
    present_codes = [
        row.candidate_sku_code
        for row in candidate_facts
        if row.fact_status == "known_present" and row.candidate_sku_code in candidates
    ]
    absent_codes = [
        row.candidate_sku_code
        for row in candidate_facts
        if row.fact_status == "known_absent" and row.candidate_sku_code in candidates
    ]
    target_price = _market_metric(target, "price_wavg")
    target_volume = _market_metric(target, "avg_weekly_sales_volume")
    comparison_codes = absent_codes if rows else present_codes
    peer_prices = [
        value
        for code in comparison_codes
        if (value := _market_metric(candidates[code], "price_wavg")) is not None
    ]
    peer_volumes = [
        value
        for code in comparison_codes
        if (
            value := _market_metric(candidates[code], "avg_weekly_sales_volume")
        )
        is not None
    ]
    if not price_values and target_price is not None and len(peer_prices) >= 2:
        price_values.append(target_price - median(peer_prices))
    if not volume_values and target_volume is not None and len(peer_volumes) >= 2:
        volume_values.append(target_volume - median(peer_volumes))
    price = _evidence_status(price_values)
    volume = _evidence_status(volume_values)
    choice = _choice_evidence_status(rows)
    performance = _competitive_performance(volume, price, choice)
    return {
        "price": price,
        "volume": volume,
        "choice": choice,
        "performance": performance,
    }


def _choice_evidence_status(
    rows: Sequence[ValueAccountRow],
) -> MarketEvidenceStatus:
    values = []
    for row in rows:
        association = row.volume_realization.choice_association or {}
        if association.get("status") != "available":
            continue
        difference = association.get("choice_difference_pp")
        try:
            if difference is not None:
                values.append(float(difference))
        except (TypeError, ValueError):
            continue
    return _evidence_status(values)


def _evidence_status(values: Sequence[float]) -> MarketEvidenceStatus:
    if not values:
        return "unknown"
    signs = {1 if value > 0 else -1 if value < 0 else 0 for value in values}
    if 1 in signs and -1 in signs:
        return "unknown"
    if 1 in signs:
        return "positive"
    if -1 in signs:
        return "negative"
    return "not_weaker"


def _competitive_performance(
    volume: str,
    price: str,
    choice: str,
) -> str:
    del price
    signals = {volume, choice} - {"unknown", "not_applicable"}
    if "positive" in signals and "negative" in signals:
        return "conflicted"
    if "negative" in signals:
        return "weaker"
    if "positive" in signals:
        return "stronger"
    if "not_weaker" in signals:
        return "not_weaker"
    return "unknown"


def _market_metric(
    snapshot: SkuEvidenceSnapshot,
    key: str,
) -> float | None:
    value = (snapshot.market.get("market_metrics") or {}).get(key)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _snapshot_evidence_refs(
    snapshot: SkuEvidenceSnapshot,
    capability_code: str,
) -> list[SellpointValueEvidenceRef]:
    relevant_modules = (
        {"M03B", "M05C"}
        if capability_code.startswith(("tv_param_", "ac_param_"))
        else {"M04C", "M05C"}
    )
    return [
        _evidence_ref(ref)
        for ref in snapshot.source_refs
        if ref.module_code in relevant_modules
    ]


def _evidence_ref(ref: EvidenceRef) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code=ref.module_code,
        record_type=ref.record_type,
        record_id=ref.record_id,
        result_hash=ref.result_hash,
        batch_id=ref.batch_id,
        evidence_ids=ref.evidence_ids,
    )


def _dedupe_evidence_refs(
    refs: Iterable[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    by_key = {
        (ref.module_code, ref.record_type, ref.record_id, ref.result_hash): ref
        for ref in refs
    }
    return [by_key[key] for key in sorted(by_key)]


def _string_set(values: Any) -> set[str]:
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value) for value in values if str(value)}


def _contains_code(value: Any, code: str) -> bool:
    if isinstance(value, dict):
        return code in value or any(_contains_code(item, code) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_code(item, code) for item in value)
    return value == code


__all__ = [
    "AnalystSellpointValueMaterializationInputProvider",
    "SellpointValueProfileInputError",
    "build_capability_investment_inputs",
    "build_production_version_request",
    "build_profile_source_lineage",
    "production_method_versions",
]
