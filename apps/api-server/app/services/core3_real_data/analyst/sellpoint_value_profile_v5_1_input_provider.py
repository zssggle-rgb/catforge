"""Production input assembly for immutable sellpoint-value V5.1 drafts.

The provider intentionally has two read-only inputs:

* the explicitly locked, already-saved V5 profile supplies user-value,
  capability-investment, market-reference, and prior comparison selections;
* the current published competitor-agent snapshot v2 supplies the formal
  competitor universe and current saved market facts.

It never recalls candidates, invokes live competitor analysis, or reads the
legacy M12/M13/M14 candidate path.  Old V5 review and release states are not
propagated: only saved facts and source hashes are adapted into the V5.1
question-local contracts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SellpointValueSavedV5GenerationSource,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_repositories import (
    SellpointValueProfileRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_aggregation import (
    SPV_V5_1_SKU_AGGREGATION_VERSION,
    SPV_V5_1_VALUE_AGGREGATION_VERSION,
    aggregate_sku_conclusion,
    aggregate_value_conclusion,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_candidate_pools import (
    SPV_V5_1_CANDIDATE_POOLS_SCHEMA_VERSION,
    build_sellpoint_value_candidate_pools,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
    SellpointValueCompetitorReadRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    sellpoint_value_v5_1_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_enhancements import (
    SPV_V5_1_ARCHETYPE_ADAPTER_VERSION,
    SPV_V5_1_STRICT_WTP_ADAPTER_VERSION,
    adapt_same_budget_market_archetype,
    adapt_strict_market_implied_wtp,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SPV_V5_1_VERSION_CANDIDATE_HASH_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_investments import (
    SPV_V5_1_INVESTMENT_METHOD_VERSION,
    SPV_V5_1_LOCAL_REVIEW_METHOD_VERSION,
    build_local_investment_review_overlays,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_market_comparison import (
    SPV_V5_1_DIRECT_MARKET_METHOD_VERSION,
    SPV_V5_1_PARAMETER_GROUP_METHOD_VERSION,
    calculate_direct_market_comparison,
    calculate_parameter_group_comparison,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51CompetitorVersionSource,
    SellpointValueV51MaterializationInput,
    SellpointValueV51SourceLineage,
    SellpointValueV51Target,
    SellpointValueV51ValueInput,
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    AnalysisReferencePurpose,
    CandidateSourceType,
    CompetitorProfileSkuMarketFacts,
    DirectMarketComparisonInput,
    DirectMarketComparisonResult,
    DirectMarketGap,
    InvestmentQuestionCode,
    LocalCapabilityInvestmentDecision,
    MarketArchetypeEnhancementResult,
    MarketComparatorObservation,
    MarketObservationSourceType,
    ParameterGroupComparisonInput,
    ParameterGroupComparisonResult,
    ParameterValueObservation,
    QuantificationLayer,
    QuantificationResult,
    QuestionCandidateUse,
    QuestionConclusionSignal,
    QuestionConclusionStatus,
    QuestionConclusionStrength,
    SkuConclusionAggregationInput,
    StrictMarketImpliedWtpResult,
    TableStakeAssessment,
    TableStakeAssessmentStatus,
    ValueConclusionAggregationInput,
    ValueQuantificationStack,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_1_SAVED_V5_INPUT_METHOD_VERSION = "sellpoint_value_saved_v5_input_v5_1"
SPV_V5_1_QUANTIFICATION_METHOD_VERSION = "sellpoint_value_quantification_v5_1"
SPV_V5_1_PARAMETER_INPUT_METHOD_VERSION = (
    "sellpoint_value_saved_parameter_input_v5_1"
)

SPV_V5_1_PRODUCTION_METHOD_VERSIONS = {
    "aggregation_sku": SPV_V5_1_SKU_AGGREGATION_VERSION,
    "aggregation_value": SPV_V5_1_VALUE_AGGREGATION_VERSION,
    "candidate_pools": SPV_V5_1_CANDIDATE_POOLS_SCHEMA_VERSION,
    "candidate_universe": SPV_V5_1_VERSION_CANDIDATE_HASH_VERSION,
    "competitor_source": "competitor_profile_agent_snapshot_v2",
    "direct_market": SPV_V5_1_DIRECT_MARKET_METHOD_VERSION,
    "investment": SPV_V5_1_INVESTMENT_METHOD_VERSION,
    "local_review": SPV_V5_1_LOCAL_REVIEW_METHOD_VERSION,
    "market_archetype": SPV_V5_1_ARCHETYPE_ADAPTER_VERSION,
    "parameter_group": SPV_V5_1_PARAMETER_GROUP_METHOD_VERSION,
    "saved_v5_input": SPV_V5_1_SAVED_V5_INPUT_METHOD_VERSION,
    "strict_wtp": SPV_V5_1_STRICT_WTP_ADAPTER_VERSION,
}

_REFERENCE_PURPOSE_BY_METHOD = {
    "same_budget_pool": AnalysisReferencePurpose.SAME_BUDGET_MARKET,
    "same_brand_size_ladder": AnalysisReferencePurpose.SAME_BRAND_SIZE_LADDER,
    "param_tier_pool": AnalysisReferencePurpose.PARAMETER_GROUP,
    "parameter_configuration": AnalysisReferencePurpose.PARAMETER_GROUP,
    "same_claim_realization": AnalysisReferencePurpose.PERFORMANCE_ARCHETYPE,
    "performance_archetype": AnalysisReferencePurpose.PERFORMANCE_ARCHETYPE,
    "battlefield_portfolio": AnalysisReferencePurpose.BATTLEFIELD_BENCHMARK,
    "market_synthetic": AnalysisReferencePurpose.SYNTHETIC_DONOR,
}

_DIRECT_METHODS = {
    "same_claim_different_realization",
    "direct_comparable",
    "same_budget_pool",
    "same_brand_size_ladder",
    "parameter_configuration",
}


class SellpointValueV51ProductionInputError(RuntimeError):
    """Raised when saved production inputs cannot form one V5.1 graph."""


class SavedV5SellpointValueV51InputProvider:
    """Assemble V5.1 inputs from one explicit saved V5 version."""

    def __init__(
        self,
        *,
        repository: SellpointValueProfileRepository,
        competitor_adapter: SellpointValueCompetitorProfileAdapter,
        source_profile_version: str,
        source_rule_version: str = SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    ) -> None:
        self.repository = repository
        self.competitor_adapter = competitor_adapter
        self.source_profile_version = source_profile_version.strip()
        self.source_rule_version = source_rule_version.strip()
        if not self.source_profile_version:
            raise ValueError("saved V5 source profile version is required")
        if not self.source_rule_version:
            raise ValueError("saved V5 source rule version is required")
        self._cache: dict[
            tuple[str, str, str],
            SellpointValueV51MaterializationInput,
        ] = {}

    def build_version_request(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        profile_version: str,
        expected_sku_codes: Sequence[str],
        generated_by: str,
    ) -> SellpointValueV51VersionRequest:
        normalized_category = category_code.strip().upper()
        if normalized_category not in {"TV", "AC"}:
            raise ValueError(f"unsupported V5.1 category: {category_code}")
        expected = sorted(
            {
                str(sku_code).strip().upper()
                for sku_code in expected_sku_codes
                if str(sku_code).strip()
            }
        )
        if not expected:
            raise ValueError("V5.1 generation requires at least one SKU")

        candidate_pool_hashes: dict[str, str] = {}
        competitor_versions: set[tuple[Any, ...]] = set()
        version_competitor = None
        version_source_lineage: list[SellpointValueV51SourceLineage] = []
        if len(expected) == 1:
            source = self._build_materialization_input(
                project_id=project_id,
                category_code=normalized_category,
                batch_id=batch_id,
                profile_version=profile_version,
                sku_code=expected[0],
                generated_by=generated_by,
            )
            self._remember_input(
                (profile_version, batch_id, source.target.sku_code),
                source,
            )
            candidate_pool_hashes[source.target.sku_code] = (
                source.candidate_pools.result_hash
            )
            version_competitor = source.competitor_source
            version_source_lineage = source.source_lineage
            competitor_versions.add(
                _competitor_version_identity(source.competitor_source)
            )
        else:
            # Freeze only the light version scope here. Holding every fully
            # assembled value graph made a 377-SKU request retain more than a
            # gigabyte before the first draft write. Each full graph is built
            # later, one SKU at a time, and rechecked against this hash.
            for sku_code in expected:
                bundle, competitor = self._load_saved_v5_bundle_and_competitor(
                    project_id=project_id,
                    category_code=normalized_category,
                    batch_id=batch_id,
                    sku_code=sku_code,
                )
                candidate_pools = build_sellpoint_value_candidate_pools(
                    competitor_source=competitor,
                    analysis_reference_records=[
                        _analysis_reference_record(
                            row,
                            purposes=_reference_purposes(bundle),
                        )
                        for row in bundle.candidates
                        if row.pool_type == "reference"
                    ],
                )
                candidate_pool_hashes[sku_code] = candidate_pools.result_hash
                competitor_versions.add(_competitor_version_identity(competitor))
                if version_competitor is None:
                    version_competitor = competitor
                    version_source_lineage = _saved_v5_source_lineage(bundle)
        if len(competitor_versions) != 1 or version_competitor is None:
            raise SellpointValueV51ProductionInputError(
                "authoritative SKUs do not share one formal competitor version"
            )
        competitor = version_competitor
        request = SellpointValueV51VersionRequest(
            project_id=project_id,
            category_code=normalized_category,
            batch_id=batch_id,
            profile_version=profile_version,
            competitor_source=SellpointValueV51CompetitorVersionSource(
                access_mode=competitor.access_mode,
                competitor_profile_version_id=(
                    competitor.competitor_profile_version_id
                ),
                profile_version=competitor.profile_version,
                method_version=competitor.method_version,
                release_status=competitor.release_status,
                is_current=competitor.is_current,
                release_scope_key=competitor.release_scope_key,
                version_result_hash=competitor.source_version_result_hash,
            ),
            expected_sku_codes=expected,
            candidate_pool_hashes=candidate_pool_hashes,
            method_config=sellpoint_value_v5_1_config(normalized_category),
            method_versions=dict(sorted(SPV_V5_1_PRODUCTION_METHOD_VERSIONS.items())),
            source_lineage=version_source_lineage,
            generated_by=generated_by,
        )
        return request

    def _remember_input(
        self,
        key: tuple[str, str, str],
        source: SellpointValueV51MaterializationInput,
    ) -> None:
        # Generation is strictly serial. Retaining more than the current graph
        # adds no reuse value and makes full-category runs scale with all SKUs.
        self._cache.clear()
        self._cache[key] = source

    def _load_saved_v5_bundle_and_competitor(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        sku_code: str,
    ) -> tuple[SellpointValueSavedV5GenerationSource, Any]:
        bundle = self.repository.get_saved_v5_generation_source(
            batch_id=batch_id,
            profile_version=self.source_profile_version,
            sku_code=sku_code,
            rule_version=self.source_rule_version,
        )
        if bundle is None:
            raise SellpointValueV51ProductionInputError(
                f"saved V5 source profile is unavailable for {sku_code}"
            )
        _assert_saved_v5_bundle(
            bundle,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            sku_code=sku_code,
            profile_version=self.source_profile_version,
            rule_version=self.source_rule_version,
        )
        competitor_read = self.competitor_adapter.read(
            SellpointValueCompetitorReadRequest(
                project_id=project_id,
                category_code=category_code,
                target_sku_code=sku_code,
                access_mode="formal",
            )
        )
        if competitor_read.status != "available" or competitor_read.source is None:
            raise SellpointValueV51ProductionInputError(
                f"current published competitor profile is unavailable for {sku_code}"
            )
        return bundle, competitor_read.source

    def load_materialization_input(
        self,
        request: SellpointValueV51VersionRequest,
        sku_code: str,
    ) -> SellpointValueV51MaterializationInput:
        normalized = sku_code.strip().upper()
        key = (request.profile_version, request.batch_id, normalized)
        source = self._cache.get(key)
        if source is None:
            source = self._build_materialization_input(
                project_id=request.project_id,
                category_code=request.category_code,
                batch_id=request.batch_id,
                profile_version=request.profile_version,
                sku_code=normalized,
                generated_by=request.generated_by,
            )
            self._remember_input(key, source)
        if source.candidate_pools.result_hash != request.candidate_pool_hashes.get(
            normalized
        ):
            raise SellpointValueV51ProductionInputError(
                "saved V5.1 candidate pool changed after request creation"
            )
        if (
            source.competitor_source.competitor_profile_version_id
            != request.competitor_source.competitor_profile_version_id
            or source.competitor_source.source_version_result_hash
            != request.competitor_source.version_result_hash
        ):
            raise SellpointValueV51ProductionInputError(
                "formal competitor source changed after request creation"
            )
        return source

    def _build_materialization_input(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        profile_version: str,
        sku_code: str,
        generated_by: str,
    ) -> SellpointValueV51MaterializationInput:
        bundle, competitor_source = self._load_saved_v5_bundle_and_competitor(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            sku_code=sku_code,
        )
        purposes = _reference_purposes(bundle)
        candidate_pools = build_sellpoint_value_candidate_pools(
            competitor_source=competitor_source,
            analysis_reference_records=[
                _analysis_reference_record(row, purposes=purposes)
                for row in bundle.candidates
                if row.pool_type == "reference"
            ],
        )
        overrides = _capability_value_status_overrides(bundle)
        values = [
            _value_input(
                bundle=bundle,
                item=item,
                competitor_source=competitor_source,
                candidate_pools=candidate_pools,
                capability_status_overrides=overrides,
            )
            for item in bundle.value_items
        ]
        sku_conclusion = aggregate_sku_conclusion(
            SkuConclusionAggregationInput(
                project_id=project_id,
                category_code=category_code,
                target_sku_code=sku_code,
                value_results=[row.value_conclusion for row in values],
            )
        )
        profile = bundle.profile
        source_lineage = _saved_v5_source_lineage(bundle)
        return SellpointValueV51MaterializationInput(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            release_scope_key=competitor_source.release_scope_key,
            profile_version=profile_version,
            target=SellpointValueV51Target(
                sku_code=sku_code,
                model_code=profile.model_code,
                model_name=profile.model_name,
                brand_name=profile.brand_name,
                display_name_cn=(
                    profile.display_name_cn
                    or " ".join(
                        value
                        for value in (profile.brand_name, profile.model_name)
                        if value
                    )
                    or sku_code
                ),
            ),
            competitor_source=competitor_source,
            candidate_pools=candidate_pools,
            method_config=sellpoint_value_v5_1_config(category_code),
            source_lineage=source_lineage,
            values=values,
            sku_conclusion=sku_conclusion,
            generated_by=generated_by,
            limitations=[
                "market_association_not_randomized_causality",
                "saved_v5_user_value_and_reference_facts_reused",
            ],
        )


def _competitor_version_identity(competitor: Any) -> tuple[Any, ...]:
    return (
        competitor.access_mode,
        competitor.competitor_profile_version_id,
        competitor.profile_version,
        competitor.method_version,
        competitor.release_status,
        competitor.is_current,
        competitor.release_scope_key,
        competitor.source_version_result_hash,
    )


def _saved_v5_source_lineage(
    bundle: SellpointValueSavedV5GenerationSource,
) -> list[SellpointValueV51SourceLineage]:
    profile = bundle.profile
    return [
        SellpointValueV51SourceLineage(
            source_code="saved_sellpoint_value_v5_profile",
            source_type="upstream",
            version_id=bundle.version.sellpoint_value_profile_version_id,
            method_version=bundle.version.method_version,
            result_hash=profile.result_hash,
            record_ids=[profile.sku_sellpoint_value_profile_id],
            limitations=[
                "saved_facts_only",
                "legacy_review_and_release_states_not_propagated",
            ],
        )
    ]


def _assert_saved_v5_bundle(
    bundle: SellpointValueSavedV5GenerationSource,
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    profile_version: str,
    rule_version: str,
) -> None:
    version = bundle.version
    profile = bundle.profile
    if (
        version.project_id != project_id
        or profile.project_id != project_id
        or version.category_code != category_code
        or profile.category_code != category_code
        or version.batch_id != batch_id
        or profile.batch_id != batch_id
        or version.profile_version != profile_version
        or profile.profile_version != profile_version
        or version.rule_version != rule_version
        or profile.rule_version != rule_version
        or version.method_version != SELLPOINT_VALUE_PROFILE_METHOD_VERSION
        or profile.method_version != SELLPOINT_VALUE_PROFILE_METHOD_VERSION
        or profile.sku_code != sku_code
    ):
        raise SellpointValueV51ProductionInputError(
            "saved V5 source crossed its locked profile scope"
        )
    if not version.result_hash or not profile.result_hash:
        raise SellpointValueV51ProductionInputError(
            "saved V5 source is missing immutable hashes"
        )


def _reference_purposes(
    bundle: SellpointValueSavedV5GenerationSource,
) -> dict[str, set[AnalysisReferencePurpose]]:
    result = {
        row.candidate_sku_code: {AnalysisReferencePurpose.SAME_SIZE_MARKET}
        for row in bundle.candidates
        if row.pool_type == "reference"
    }
    for item in bundle.value_items:
        for question in item.question_result_refs_json:
            if not isinstance(question, Mapping):
                continue
            purpose = _REFERENCE_PURPOSE_BY_METHOD.get(str(question.get("method") or ""))
            if purpose is None:
                continue
            for sku_code in question.get("selected_candidate_ids") or ():
                normalized = str(sku_code).strip().upper()
                if normalized in result:
                    result[normalized].add(purpose)
    return result


def _analysis_reference_record(
    row: Any,
    *,
    purposes: Mapping[str, set[AnalysisReferencePurpose]],
) -> dict[str, Any]:
    evidence = SellpointValueEvidenceRef(
        module_code="sellpoint_value_profile_v5",
        record_type="analysis_reference",
        record_id=row.sku_sellpoint_value_candidate_id,
        result_hash=row.result_hash,
        batch_id=row.batch_id,
    )
    return {
        "reference_sku_code": row.candidate_sku_code,
        "brand_name": row.candidate_brand_name,
        "model_name": row.candidate_model_name,
        "purposes": sorted(
            purposes.get(
                row.candidate_sku_code,
                {AnalysisReferencePurpose.SAME_SIZE_MARKET},
            ),
            key=lambda value: value.value,
        ),
        "market": dict(row.market_summary_json or {}),
        "source_hashes": {"saved_v5_reference": row.result_hash},
        "evidence_refs": [evidence.model_dump(mode="json")],
    }


def _capability_value_status_overrides(
    bundle: SellpointValueSavedV5GenerationSource,
) -> dict[str, str]:
    """Prefer a dedicated one-capability value over composite bundle inference."""

    overrides: dict[str, str] = {}
    for item in bundle.value_items:
        codes = sorted(set(item.capability_codes_json))
        if len(codes) != 1:
            continue
        status = str(item.perceived_value_status)
        if status in {"not_observed", "observed_negative", "conflicted"}:
            overrides[codes[0]] = status
    return overrides


def _value_input(
    *,
    bundle: SellpointValueSavedV5GenerationSource,
    item: Any,
    competitor_source: Any,
    candidate_pools: Any,
    capability_status_overrides: Mapping[str, str],
) -> SellpointValueV51ValueInput:
    evidence_ref = _value_evidence_ref(item)
    direct_results = _direct_market_results(
        bundle=bundle,
        item=item,
        competitor_source=competitor_source,
        candidate_pools=candidate_pools,
        evidence_ref=evidence_ref,
    )
    direct_uses = _used_candidate_uses(
        candidate_pools,
        {
            code
            for result in direct_results
            for code in result.used_comparator_sku_codes
        },
    )
    archetypes = _market_archetypes(
        item=item,
        competitor_source=competitor_source,
        candidate_pools=candidate_pools,
        evidence_ref=evidence_ref,
    )
    archetype_uses = _used_candidate_uses(
        candidate_pools,
        {
            code
            for result in archetypes
            for group in result.groups
            for code in group.sku_codes
        },
    )
    parameter_results = _parameter_results(
        project_id=bundle.profile.project_id,
        item=item,
        target_market=competitor_source.target_market,
        evidence_ref=evidence_ref,
    )
    strict_wtp = adapt_strict_market_implied_wtp(
        project_id=bundle.profile.project_id,
        category_code=bundle.profile.category_code,
        target_sku_code=bundle.profile.sku_code,
        value_bundle_code=item.value_bundle_code,
        source=None,
        evidence_refs=[evidence_ref],
    )
    investment_decisions = _investment_decisions(
        bundle=bundle,
        item=item,
        capability_status_overrides=capability_status_overrides,
        evidence_ref=evidence_ref,
    )
    investment_reviews = build_local_investment_review_overlays(
        investment_decisions
    )
    quantifications = _quantification_stack(
        item=item,
        direct_results=direct_results,
        direct_uses=direct_uses,
        archetypes=archetypes,
        archetype_uses=archetype_uses,
        strict_wtp=strict_wtp,
        evidence_ref=evidence_ref,
    )
    signals = _question_signals(
        item=item,
        quantifications=quantifications,
        direct_results=direct_results,
        parameter_results=parameter_results,
        archetypes=archetypes,
        strict_wtp=strict_wtp,
        investment_decisions=investment_decisions,
        investment_reviews=investment_reviews,
    )
    conclusion = aggregate_value_conclusion(
        ValueConclusionAggregationInput(
            project_id=bundle.profile.project_id,
            category_code=bundle.profile.category_code,
            target_sku_code=bundle.profile.sku_code,
            value_bundle_code=item.value_bundle_code,
            question_signals=signals,
        )
    )
    return SellpointValueV51ValueInput(
        battlefield_code=item.battlefield_code,
        battlefield_name_cn=item.battlefield_name_cn,
        purchase_reason_code=item.purchase_reason_code,
        purchase_reason_name_cn=item.purchase_reason_name_cn,
        value_bundle_code=item.value_bundle_code,
        value_bundle_name_cn=item.value_bundle_name_cn,
        normalized_bundle_code=item.normalized_bundle_code,
        perceived_outcome_cn=item.perceived_outcome_cn,
        capability_codes=sorted(set(item.capability_codes_json)),
        question_signals=signals,
        quantification_stack=ValueQuantificationStack(
            value_bundle_code=item.value_bundle_code,
            results=quantifications,
        ),
        direct_market_results=direct_results,
        parameter_group_results=parameter_results,
        market_archetype_results=archetypes,
        synthetic_market_baseline=None,
        strict_market_implied_wtp=strict_wtp,
        investment_decisions=investment_decisions,
        investment_reviews=investment_reviews,
        value_conclusion=conclusion,
        evidence_boundary_cn=(
            item.evidence_boundary_cn
            or "用户价值来自已保存的购后体验证据，量价为市场关联。"
        ),
        limitations=sorted(
            {
                *item.limitations_json,
                "saved_v5_fact_adapter",
                "market_association_not_single_sellpoint_causality",
            }
        ),
    )


def _direct_market_results(
    *,
    bundle: SellpointValueSavedV5GenerationSource,
    item: Any,
    competitor_source: Any,
    candidate_pools: Any,
    evidence_ref: SellpointValueEvidenceRef,
) -> list[DirectMarketComparisonResult]:
    payload = item.price_realization_json or {}
    rows = payload.get("realization_comparisons") or payload.get(
        "direct_and_pool_gaps"
    ) or []
    results = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        codes = [
            str(value).strip().upper()
            for value in row.get("comparator_sku_codes") or ()
            if str(value).strip()
        ]
        if not codes:
            continue
        method = str(row.get("method") or "direct_comparable")
        if method not in _DIRECT_METHODS:
            method = "direct_comparable"
        results.append(
            _calculate_direct(
                project_id=bundle.profile.project_id,
                category_code=bundle.profile.category_code,
                target_sku_code=bundle.profile.sku_code,
                value_bundle_code=item.value_bundle_code,
                method=method,
                comparator_sku_codes=codes,
                target_market=competitor_source.target_market,
                competitor_source=competitor_source,
                candidate_pools=candidate_pools,
                evidence_ref=evidence_ref,
            )
        )
    return sorted(results, key=lambda result: result.result_hash)


def _calculate_direct(
    *,
    project_id: str,
    category_code: str,
    target_sku_code: str,
    value_bundle_code: str,
    method: str,
    comparator_sku_codes: Sequence[str],
    target_market: CompetitorProfileSkuMarketFacts,
    competitor_source: Any,
    candidate_pools: Any,
    evidence_ref: SellpointValueEvidenceRef,
) -> DirectMarketComparisonResult:
    observations = []
    for code in sorted(set(comparator_sku_codes)):
        use, market = _candidate_use_and_market(
            candidate_pools=candidate_pools,
            competitor_source=competitor_source,
            sku_code=code,
        )
        if use is None or market is None or not use.selected:
            continue
        observations.append(
            MarketComparatorObservation(
                category_code=category_code,
                candidate_use=use,
                market=market,
                evidence_refs=list(use.evidence_refs),
            )
        )
    return calculate_direct_market_comparison(
        DirectMarketComparisonInput(
            project_id=project_id,
            category_code=category_code,
            target_sku_code=target_sku_code,
            value_bundle_code=value_bundle_code,
            method=method,
            target_market=target_market,
            comparators=observations,
            target_evidence_refs=[evidence_ref],
        )
    )


def _candidate_use_and_market(
    *,
    candidate_pools: Any,
    competitor_source: Any,
    sku_code: str,
) -> tuple[QuestionCandidateUse | None, CompetitorProfileSkuMarketFacts | None]:
    question = next(
        row
        for row in candidate_pools.question_candidate_sets
        if row.question_code == "current_price_support"
    )
    uses = [row for row in question.candidate_uses if row.candidate_sku_code == sku_code]
    use = next(
        (
            row
            for row in uses
            if row.source_type == CandidateSourceType.COMPETITOR
        ),
        uses[0] if uses else None,
    )
    if use is None:
        return None, None
    if use.source_type == CandidateSourceType.COMPETITOR:
        candidate = next(
            (
                row
                for row in competitor_source.candidates
                if row.candidate_sku_code == sku_code
            ),
            None,
        )
        return use, candidate.market if candidate is not None else None
    reference = next(
        (
            row
            for row in candidate_pools.analysis_references
            if row.reference_sku_code == sku_code
        ),
        None,
    )
    return use, reference.market if reference is not None else None


def _market_archetypes(
    *,
    item: Any,
    competitor_source: Any,
    candidate_pools: Any,
    evidence_ref: SellpointValueEvidenceRef,
) -> list[MarketArchetypeEnhancementResult]:
    if _user_value_status(item.perceived_value_status)[0] == (
        QuestionConclusionStatus.NO_CONCLUSION
    ):
        return []
    selected = []
    for question in item.question_result_refs_json:
        if not isinstance(question, Mapping):
            continue
        if (
            question.get("source_question_code") == "price_realization"
            and question.get("method") == "same_budget_pool"
        ):
            selected = [
                str(value).strip().upper()
                for value in question.get("selected_candidate_ids") or ()
                if str(value).strip()
            ]
            break
    if not selected:
        return []
    direct = _calculate_direct(
        project_id=competitor_source.project_id,
        category_code=competitor_source.category_code,
        target_sku_code=competitor_source.target_sku_code,
        value_bundle_code=item.value_bundle_code,
        method="same_budget_pool",
        comparator_sku_codes=selected,
        target_market=competitor_source.target_market,
        competitor_source=competitor_source,
        candidate_pools=candidate_pools,
        evidence_ref=evidence_ref,
    )
    return [adapt_same_budget_market_archetype(direct)]


def _parameter_results(
    *,
    project_id: str,
    item: Any,
    target_market: CompetitorProfileSkuMarketFacts,
    evidence_ref: SellpointValueEvidenceRef,
) -> list[ParameterGroupComparisonResult]:
    """Persist known target tiers and an honest no-comparator parameter state."""

    results = []
    seen: set[str] = set()
    for investment in item.investment_decisions_json:
        if not isinstance(investment, Mapping):
            continue
        code = str(investment.get("capability_code") or "").strip()
        name = str(investment.get("capability_name_cn") or code).strip()
        target_value = investment.get("target_value")
        if not code or not name or target_value in (None, "") or code in seen:
            continue
        seen.add(code)
        results.append(
            calculate_parameter_group_comparison(
                ParameterGroupComparisonInput(
                    project_id=project_id,
                    category_code=target_market.product_category,
                    target_sku_code=target_market.sku_code,
                    value_bundle_code=item.value_bundle_code,
                    parameter_code=code,
                    parameter_name_cn=name,
                    target=ParameterValueObservation(
                        category_code=target_market.product_category,
                        sku_code=target_market.sku_code,
                        source_type=MarketObservationSourceType.TARGET,
                        normalized_value=str(target_value),
                        weighted_price=target_market.weighted_price,
                        avg_weekly_sales_volume=(
                            target_market.avg_weekly_sales_volume
                        ),
                        evidence_refs=[evidence_ref],
                    ),
                    comparators=[],
                    exclude_from_core_sellpoints=False,
                )
            )
        )
    return sorted(results, key=lambda result: result.parameter_code)


def _investment_decisions(
    *,
    bundle: SellpointValueSavedV5GenerationSource,
    item: Any,
    capability_status_overrides: Mapping[str, str],
    evidence_ref: SellpointValueEvidenceRef,
) -> list[LocalCapabilityInvestmentDecision]:
    config = sellpoint_value_v5_1_config(bundle.profile.category_code)
    result = []
    seen: set[str] = set()
    for raw in item.investment_decisions_json:
        if not isinstance(raw, Mapping):
            continue
        code = str(raw.get("capability_code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        name = str(raw.get("capability_name_cn") or code).strip()
        perceived_status = capability_status_overrides.get(
            code,
            str(item.perceived_value_status),
        )
        old_classification = str(raw.get("classification") or "unknown")
        if (
            str(raw.get("target_fact_status")) == "known_present"
            and perceived_status in {"not_observed", "observed_negative"}
        ):
            classification = "unconverted"
            status = QuestionConclusionStatus.PARTIAL_CONCLUSION
            confidence = Decimal("0.8000")
            reason = (
                "产品已经投入这项能力，但用户尚未形成相应体验价值；"
                "下一步应先改善体验兑现，不继续堆叠参数。"
            )
            used_dimensions = ["target_fact", "user_feedback"]
        elif old_classification == "retain" and perceived_status in {
            "observed_positive",
            "observed_mixed",
            "partial",
        }:
            classification = "retain"
            status = QuestionConclusionStatus.CONCLUSION_AVAILABLE
            confidence = Decimal("0.8600")
            reason = (
                "这项投入已形成用户可感知价值，并与当前市场表现方向一致，"
                "下一代产品应继续保留。"
            )
            used_dimensions = [
                "price_support",
                "relative_experience",
                "target_fact",
                "user_feedback",
                "volume_support",
            ]
        else:
            classification = "unknown"
            status = QuestionConclusionStatus.NO_CONCLUSION
            confidence = None
            reason = "现有事实不足以判断这项投入应继续保留还是调整。"
            used_dimensions = (
                ["target_fact"]
                if str(raw.get("target_fact_status")) == "known_present"
                else []
            )
        table_stake = TableStakeAssessment(
            capability_code=code,
            status=TableStakeAssessmentStatus.NOT_ASSESSED,
            total_count=0,
            known_count=0,
            present_count=0,
            absent_count=0,
            missing_count=0,
            contradicted_count=0,
            minimum_known_count=config.table_stake.minimum_known_count,
            prevalence_threshold=config.table_stake.prevalence_threshold,
            prevalence=None,
            scope_complete=False,
            exclude_from_core_sellpoints=False,
            limitations=["saved_reference_capability_prevalence_unavailable"],
            review_required=False,
            review_reasons=[],
        )
        unavailable = sorted(
            {
                "choice_support",
                "table_stake_assessment",
                *(
                    ["relative_experience"]
                    if str(raw.get("relative_experience_status") or "unknown")
                    == "unknown"
                    else []
                ),
            }
            - set(used_dimensions)
        )
        payload = {
            "project_id": bundle.profile.project_id,
            "category_code": bundle.profile.category_code,
            "target_sku_code": bundle.profile.sku_code,
            "question_code": InvestmentQuestionCode.INVESTMENT_CONVERSION,
            "value_bundle_code": item.value_bundle_code,
            "capability_code": code,
            "capability_name_cn": name,
            "classification": classification,
            "status": status,
            "table_stake_assessment": table_stake,
            "used_dimensions": sorted(used_dimensions),
            "unavailable_dimensions": unavailable,
            "business_reason_cn": reason,
            "confidence": confidence,
            "limitations": [
                "saved_reference_capability_prevalence_unavailable"
            ],
            "review_required": False,
            "review_reasons": [],
            "evidence_refs": [evidence_ref],
        }
        result.append(
            LocalCapabilityInvestmentDecision(
                **payload,
                result_hash=stable_hash(
                    _json_payload(payload),
                    version=SPV_V5_1_INVESTMENT_METHOD_VERSION,
                ),
            )
        )
    return sorted(result, key=lambda row: row.capability_code)


def _quantification_stack(
    *,
    item: Any,
    direct_results: Sequence[DirectMarketComparisonResult],
    direct_uses: Sequence[QuestionCandidateUse],
    archetypes: Sequence[MarketArchetypeEnhancementResult],
    archetype_uses: Sequence[QuestionCandidateUse],
    strict_wtp: StrictMarketImpliedWtpResult,
    evidence_ref: SellpointValueEvidenceRef,
) -> list[QuantificationResult]:
    user_status, user_strength = _user_value_status(item.perceived_value_status)
    user_payload = {
        "layer": QuantificationLayer.USER_VALUE_EVIDENCE,
        "method": "saved_user_value_evidence",
        "status": user_status,
        "strength": user_strength,
        "candidate_uses": [],
        "facts": {"perceived_value_status": str(item.perceived_value_status)},
        "result": (
            {
                "perceived_outcome_cn": item.perceived_outcome_cn,
                "capability_codes": sorted(set(item.capability_codes_json)),
            }
            if user_status != QuestionConclusionStatus.NO_CONCLUSION
            else {}
        ),
        "direct_market_gaps": [],
        "limitations": list(item.limitations_json),
        "review_required": False,
        "review_reasons": [],
    }
    direct_available = [
        row
        for row in direct_results
        if row.status
        in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }
    ]
    direct_status = _aggregate_result_status(direct_available)
    direct_strength = _aggregate_strength(
        [row.strength for row in direct_available]
    )
    direct_payload = {
        "layer": QuantificationLayer.DIRECT_MARKET_GAP,
        "method": "saved_comparator_selection_current_weekly_average",
        "status": direct_status,
        "strength": direct_strength,
        "candidate_uses": list(direct_uses),
        "facts": {
            "comparison_count": len(direct_available),
            "comparator_sku_codes": sorted(
                {
                    code
                    for row in direct_available
                    for code in row.used_comparator_sku_codes
                }
            ),
        },
        "result": (
            {
                "business_conclusions_cn": [
                    row.business_conclusion_cn for row in direct_available
                ]
            }
            if direct_available
            else {}
        ),
        "direct_market_gaps": [
            gap for row in direct_available for gap in _direct_market_gaps(row)
        ],
        "limitations": sorted(
            {
                *(
                    value
                    for row in direct_results
                    for value in row.limitations
                ),
                "market_association_not_single_sellpoint_causality",
            }
        ),
        "review_required": False,
        "review_reasons": [],
    }
    visible_archetypes = [
        row
        for row in archetypes
        if row.status
        in {
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
        }
    ]
    archetype_status = _aggregate_result_status(visible_archetypes)
    archetype_payload = {
        "layer": QuantificationLayer.MARKET_ARCHETYPE,
        "method": "saved_same_budget_market_archetype",
        "status": archetype_status,
        "strength": _aggregate_strength(
            [row.strength for row in visible_archetypes]
        ),
        "candidate_uses": list(archetype_uses),
        "facts": {"archetype_count": len(visible_archetypes)},
        "result": (
            {
                "business_conclusions_cn": [
                    row.business_conclusion_cn for row in visible_archetypes
                ]
            }
            if visible_archetypes
            else {}
        ),
        "direct_market_gaps": [],
        "limitations": sorted(
            {
                value
                for row in archetypes
                for value in row.limitations
            }
        ),
        "review_required": False,
        "review_reasons": [],
    }
    strict_payload = {
        "layer": QuantificationLayer.STRICT_MARKET_IMPLIED_WTP,
        "method": strict_wtp.method,
        "status": strict_wtp.status,
        "strength": (
            QuestionConclusionStrength.DIRECTIONAL
            if strict_wtp.status == QuestionConclusionStatus.CONCLUSION_AVAILABLE
            else QuestionConclusionStrength.NONE
        ),
        "candidate_uses": [],
        "facts": {
            "pair_count": strict_wtp.pair_count,
            "model_family_count": strict_wtp.model_family_count,
            "source_status": strict_wtp.source_status,
        },
        "result": (
            {
                "estimate_low": strict_wtp.estimate_low,
                "estimate_center": strict_wtp.estimate_center,
                "estimate_high": strict_wtp.estimate_high,
            }
            if strict_wtp.status == QuestionConclusionStatus.CONCLUSION_AVAILABLE
            else {}
        ),
        "direct_market_gaps": [],
        "limitations": list(strict_wtp.limitations),
        "review_required": False,
        "review_reasons": [],
    }
    return [
        _quantification(user_payload),
        _quantification(direct_payload),
        _quantification(archetype_payload),
        _quantification(strict_payload),
    ]


def _quantification(payload: dict[str, Any]) -> QuantificationResult:
    return QuantificationResult(
        **payload,
        result_hash=stable_hash(
            _json_payload(payload),
            version=SPV_V5_1_QUANTIFICATION_METHOD_VERSION,
        ),
    )


def _question_signals(
    *,
    item: Any,
    quantifications: Sequence[QuantificationResult],
    direct_results: Sequence[DirectMarketComparisonResult],
    parameter_results: Sequence[ParameterGroupComparisonResult],
    archetypes: Sequence[MarketArchetypeEnhancementResult],
    strict_wtp: StrictMarketImpliedWtpResult,
    investment_decisions: Sequence[LocalCapabilityInvestmentDecision],
    investment_reviews: Sequence[Any],
) -> list[QuestionConclusionSignal]:
    rows: list[
        tuple[str, str, QuestionConclusionStatus, Decimal | None, list[str]]
    ] = []
    user_confidence = Decimal(str(item.confidence))
    for result in quantifications:
        confidence = _result_confidence(
            result.status,
            result.strength,
            preferred=(
                user_confidence
                if result.layer == QuantificationLayer.USER_VALUE_EVIDENCE
                else None
            ),
        )
        rows.append(
            (
                f"quant:{result.layer.value}",
                result.result_hash,
                result.status,
                confidence,
                list(result.limitations),
            )
        )
    for index, result in enumerate(direct_results):
        rows.append(
            (
                f"direct_market:{index}",
                result.result_hash,
                result.status,
                _result_confidence(result.status, result.strength),
                list(result.limitations),
            )
        )
    for index, result in enumerate(parameter_results):
        rows.append(
            (
                f"parameter_group:{index}:{result.parameter_code}",
                result.result_hash,
                result.status,
                _result_confidence(result.status, result.strength),
                list(result.limitations),
            )
        )
    for index, result in enumerate(archetypes):
        rows.append(
            (
                f"market_archetype:{index}",
                result.result_hash,
                result.status,
                _result_confidence(result.status, result.strength),
                list(result.limitations),
            )
        )
    rows.append(
        (
            "strict_market_implied_wtp",
            strict_wtp.result_hash,
            strict_wtp.status,
            (
                Decimal("0.7500")
                if strict_wtp.status
                == QuestionConclusionStatus.CONCLUSION_AVAILABLE
                else None
            ),
            list(strict_wtp.limitations),
        )
    )
    for result in investment_decisions:
        rows.append(
            (
                f"investment:{result.question_code.value}:{result.capability_code}",
                result.result_hash,
                result.status,
                result.confidence,
                list(result.limitations),
            )
        )
    for index, result in enumerate(investment_reviews):
        rows.append(
            (
                f"investment_review:{index}:{result.question_code.value}",
                result.result_hash,
                (
                    QuestionConclusionStatus.INVALID
                    if result.review_required
                    else QuestionConclusionStatus.NO_CONCLUSION
                ),
                None,
                list(result.review_reasons),
            )
        )
    return sorted(
        [
            QuestionConclusionSignal(
                question_code=code,
                status=status,
                confidence=confidence,
                limitations=sorted(set(limitations)),
                review_required=status == QuestionConclusionStatus.INVALID,
                review_reasons=(
                    sorted(set(limitations))
                    if status == QuestionConclusionStatus.INVALID
                    else []
                ),
                source_result_hash=result_hash,
            )
            for code, result_hash, status, confidence, limitations in rows
        ],
        key=lambda row: row.question_code,
    )


def _used_candidate_uses(
    candidate_pools: Any,
    sku_codes: set[str],
) -> list[QuestionCandidateUse]:
    if not sku_codes:
        return []
    question = next(
        row
        for row in candidate_pools.question_candidate_sets
        if row.question_code == "current_price_support"
    )
    selected = []
    for sku_code in sorted(sku_codes):
        matches = [
            row
            for row in question.candidate_uses
            if row.candidate_sku_code == sku_code and row.selected
        ]
        if not matches:
            continue
        selected.append(
            next(
                (
                    row
                    for row in matches
                    if row.source_type == CandidateSourceType.COMPETITOR
                ),
                matches[0],
            )
        )
    return selected


def _direct_market_gaps(
    result: DirectMarketComparisonResult,
) -> list[DirectMarketGap]:
    price = result.price_comparison
    sales = result.sales_comparison
    rows = []
    if (
        price is not None
        and sales is not None
        and price.comparator_sku_codes == sales.comparator_sku_codes
    ):
        rows.append(
            DirectMarketGap(
                method=result.method,
                comparator_sku_codes=price.comparator_sku_codes,
                comparator_count=price.comparator_count,
                strength=price.strength.value,
                target_price=price.target_value,
                comparator_price=price.comparator_average,
                price_gap_abs=price.gap_abs,
                price_gap_pct=price.gap_pct,
                target_weekly_sales=sales.target_value,
                comparator_weekly_sales=sales.comparator_average,
                sales_gap_abs=sales.gap_abs,
                sales_gap_pct=sales.gap_pct,
                limitations=list(result.limitations),
            )
        )
        return rows
    if price is not None:
        rows.append(
            DirectMarketGap(
                method=result.method,
                comparator_sku_codes=price.comparator_sku_codes,
                comparator_count=price.comparator_count,
                strength=price.strength.value,
                target_price=price.target_value,
                comparator_price=price.comparator_average,
                price_gap_abs=price.gap_abs,
                price_gap_pct=price.gap_pct,
                limitations=list(result.limitations),
            )
        )
    if sales is not None:
        rows.append(
            DirectMarketGap(
                method=result.method,
                comparator_sku_codes=sales.comparator_sku_codes,
                comparator_count=sales.comparator_count,
                strength=sales.strength.value,
                target_weekly_sales=sales.target_value,
                comparator_weekly_sales=sales.comparator_average,
                sales_gap_abs=sales.gap_abs,
                sales_gap_pct=sales.gap_pct,
                limitations=list(result.limitations),
            )
        )
    return rows


def _user_value_status(
    status: Any,
) -> tuple[QuestionConclusionStatus, QuestionConclusionStrength]:
    normalized = str(status)
    if normalized in {"observed_positive", "observed_negative"}:
        return (
            QuestionConclusionStatus.CONCLUSION_AVAILABLE,
            QuestionConclusionStrength.DIRECTIONAL,
        )
    if normalized in {"partial", "observed_mixed"}:
        return (
            QuestionConclusionStatus.PARTIAL_CONCLUSION,
            QuestionConclusionStrength.DIRECTIONAL,
        )
    return QuestionConclusionStatus.NO_CONCLUSION, QuestionConclusionStrength.NONE


def _aggregate_result_status(
    rows: Sequence[Any],
) -> QuestionConclusionStatus:
    statuses = {row.status for row in rows}
    if QuestionConclusionStatus.CONCLUSION_AVAILABLE in statuses:
        return QuestionConclusionStatus.CONCLUSION_AVAILABLE
    if QuestionConclusionStatus.PARTIAL_CONCLUSION in statuses:
        return QuestionConclusionStatus.PARTIAL_CONCLUSION
    return QuestionConclusionStatus.NO_CONCLUSION


def _aggregate_strength(
    strengths: Sequence[QuestionConclusionStrength],
) -> QuestionConclusionStrength:
    if not strengths:
        return QuestionConclusionStrength.NONE
    rank = {
        QuestionConclusionStrength.NONE: 0,
        QuestionConclusionStrength.DIRECTIONAL: 1,
        QuestionConclusionStrength.SINGLE: 2,
        QuestionConclusionStrength.SMALL_GROUP: 3,
        QuestionConclusionStrength.GROUP: 4,
    }
    return min(strengths, key=lambda value: rank[value])


def _result_confidence(
    status: QuestionConclusionStatus,
    strength: QuestionConclusionStrength,
    *,
    preferred: Decimal | None = None,
) -> Decimal | None:
    if status not in {
        QuestionConclusionStatus.CONCLUSION_AVAILABLE,
        QuestionConclusionStatus.PARTIAL_CONCLUSION,
    }:
        return None
    if preferred is not None:
        return min(Decimal("1"), max(Decimal("0"), preferred))
    return {
        QuestionConclusionStrength.GROUP: Decimal("0.8000"),
        QuestionConclusionStrength.SMALL_GROUP: Decimal("0.7200"),
        QuestionConclusionStrength.SINGLE: Decimal("0.6200"),
        QuestionConclusionStrength.DIRECTIONAL: Decimal("0.6000"),
        QuestionConclusionStrength.NONE: Decimal("0.5000"),
    }[strength]


def _value_evidence_ref(item: Any) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code="sellpoint_value_profile_v5",
        record_type="value_item",
        record_id=item.sku_sellpoint_value_item_id,
        result_hash=item.result_hash,
        batch_id=item.batch_id,
        confidence=float(item.confidence),
    )


def _json_payload(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Mapping):
        return {
            str(key): _json_payload(child)
            for key, child in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_json_payload(child) for child in value]
    return value


__all__ = [
    "SPV_V5_1_PRODUCTION_METHOD_VERSIONS",
    "SPV_V5_1_QUANTIFICATION_METHOD_VERSION",
    "SPV_V5_1_SAVED_V5_INPUT_METHOD_VERSION",
    "SavedV5SellpointValueV51InputProvider",
    "SellpointValueV51ProductionInputError",
]
