"""Production orchestration from one frozen category input to one V1.1 draft."""

from __future__ import annotations

import ctypes
import gc
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallManifest,
)
from app.services.core3_real_data.analyst.competitor_profile_config import (
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputProvider,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_key_competitor_selection import (
    KeyCompetitorSelector,
)
from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    CompetitorProfileMaterializationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature import (
    PairFeatureBuilder,
)
from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure import (
    PriceVolumePressureEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import ServingScope
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool import (
    PurchasePoolSemanticEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticBundle,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation import (
    CompetitorRelationEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
    COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
    COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION,
    CandidateScopeClassifier,
    PairGateEvaluation,
    PairGateEvaluator,
    V11RelationEvidenceCalculator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_generation import (
    CompetitorProfileV11GenerationWorkItem,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_materializer import (
    COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION,
    CompetitorProfileV11Materializer,
    MaterializedCompetitorProfileV11,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_memory import (
    trace_competitor_profile_memory,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PAIR_ANALYSIS_AUTHORITATIVE_PROJECTION_VERSION,
    PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
    PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
    PairAnalysisAssembler,
    PairAnalysisAssembly,
    PairAnalysisCalculator,
    PairAnalysisCalculatorInput,
    build_authoritative_pair_projection,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11Repository,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
    COMPETITOR_PROFILE_V1_1_RULE_VERSION,
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
    G29PerformanceStorageBudget,
    ProfileVersionAnalysisContext,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION,
    COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION,
    CompetitorProfileV11Selector,
    LegacyTopCompetitorReference,
    PairSelectionInput,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_snapshot_builder import (
    SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION,
    SNAPSHOT_BUILDER_VERSION,
    VersionSkuAnalysisSnapshotBuilder,
    build_authoritative_snapshot_projection,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution import (
    ValueSubstitutionEvidenceEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidenceBundle,
)
from app.services.core3_real_data.hash_utils import stable_hash


PRODUCTION_ORCHESTRATOR_VERSION = "competitor_profile_v1_1_production_v1"


@dataclass(frozen=True)
class CompetitorProfileV11PreparedStages:
    category_bundle: CompetitorProfileCategoryInputBundle
    target_sku_code: str
    config: CompetitorProfileMaterializationConfig
    recall_manifest: CandidateRecallManifest
    pair_features: PairFeatureBundle
    purchase_pool: PurchasePoolSemanticBundle
    value_substitution: ValueSubstitutionEvidenceBundle
    price_volume_pressure: PriceVolumePressureBundle
    legacy_top3: tuple[LegacyTopCompetitorReference, ...]
    legacy_selection_result_hash: str


@dataclass(frozen=True)
class CompetitorProfileV11SnapshotStage:
    target_sku_code: str
    authoritative_sku_codes: tuple[str, ...]
    serving_scope: ServingScope
    config: CompetitorProfileMaterializationConfig
    recall_manifest: CandidateRecallManifest
    pair_features: PairFeatureBundle
    purchase_pool: PurchasePoolSemanticBundle
    value_substitution: ValueSubstitutionEvidenceBundle
    price_volume_pressure: PriceVolumePressureBundle
    legacy_top3: tuple[LegacyTopCompetitorReference, ...]
    legacy_selection_result_hash: str
    snapshot_sources: list[CompetitorProfileCategoryInputBundle]


@dataclass(frozen=True)
class CompetitorProfileV11ProductionGenerationResult:
    status: Literal["generated", "reused"]
    version: CompetitorProfileVersionRecord
    materialized: MaterializedCompetitorProfileV11
    candidate_count: int
    selected_sku_codes: tuple[str, ...]


class CompetitorProfileV11ProductionWorkItemBuilder:
    """Run the frozen V1 facts and V1.1 calculation chain without persistence."""

    def prepare(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        config: CompetitorProfileMaterializationConfig,
    ) -> CompetitorProfileV11PreparedStages:
        pipeline = CandidatePipelineDeterminismGuard().run_precanonicalized(
            category_bundle,
            target_bundle,
            recall_config=config.recall,
            eligibility_config=config.eligibility,
        )
        pair_features = PairFeatureBuilder().build(pipeline)
        purchase_pool = PurchasePoolSemanticEvaluator().evaluate(
            pair_features,
            config.purchase_pool,
        )
        value_substitution = ValueSubstitutionEvidenceEvaluator().evaluate(
            pair_features,
            purchase_pool,
            config.value_substitution,
        )
        price_volume_pressure = PriceVolumePressureEvaluator().evaluate(
            pair_features,
            purchase_pool,
            value_substitution,
            config.price_volume,
        )
        legacy_relations = CompetitorRelationEvaluator().evaluate(
            pair_features,
            purchase_pool,
            value_substitution,
            price_volume_pressure,
            config.relation,
        )
        legacy_selection = KeyCompetitorSelector().select(
            legacy_relations,
            config.key_selection,
        )
        legacy_top3 = tuple(
            LegacyTopCompetitorReference(
                candidate_sku_code=row.candidate_sku_code,
                legacy_rank=row.selection_rank,
                legacy_role=str(row.primary_relation_code),
            )
            for row in legacy_selection.selections
        )
        return CompetitorProfileV11PreparedStages(
            category_bundle=pipeline.category_bundle,
            target_sku_code=pipeline.target_bundle.target_sku_code,
            config=config,
            recall_manifest=pipeline.recall_manifest,
            pair_features=pair_features,
            purchase_pool=purchase_pool,
            value_substitution=value_substitution,
            price_volume_pressure=price_volume_pressure,
            legacy_top3=legacy_top3,
            legacy_selection_result_hash=legacy_selection.result_hash,
        )

    def build_snapshot_stage(
        self,
        prepared: CompetitorProfileV11PreparedStages,
        *,
        competitor_profile_version_id: str,
    ) -> CompetitorProfileV11SnapshotStage:
        if not competitor_profile_version_id.strip():
            raise ValueError("competitor profile version ID cannot be empty")
        return CompetitorProfileV11SnapshotStage(
            target_sku_code=prepared.target_sku_code,
            authoritative_sku_codes=tuple(
                prepared.category_bundle.authoritative_sku_codes
            ),
            serving_scope=prepared.category_bundle.serving_scope,
            config=prepared.config,
            recall_manifest=prepared.recall_manifest,
            pair_features=prepared.pair_features,
            purchase_pool=prepared.purchase_pool,
            value_substitution=prepared.value_substitution,
            price_volume_pressure=prepared.price_volume_pressure,
            legacy_top3=prepared.legacy_top3,
            legacy_selection_result_hash=prepared.legacy_selection_result_hash,
            snapshot_sources=[prepared.category_bundle],
        )

    def build_work_item(
        self,
        prepared: CompetitorProfileV11PreparedStages,
        *,
        competitor_profile_version_id: str,
    ) -> CompetitorProfileV11GenerationWorkItem:
        stage = self.build_snapshot_stage(
            prepared,
            competitor_profile_version_id=competitor_profile_version_id,
        )
        return self.build_work_item_from_snapshot_stage(
            stage,
            competitor_profile_version_id=competitor_profile_version_id,
        )

    def build_work_item_from_snapshot_stage(
        self,
        stage: CompetitorProfileV11SnapshotStage,
        *,
        competitor_profile_version_id: str,
    ) -> CompetitorProfileV11GenerationWorkItem:
        target_code = stage.target_sku_code
        candidate_codes = [row.candidate.sku_code for row in stage.pair_features.pairs]
        if len(stage.snapshot_sources) != 1:
            raise ValueError("snapshot stage source must be consumed exactly once")
        category_bundle = stage.snapshot_sources.pop()
        trace_competitor_profile_memory("work_item_after_source_pop")
        snapshot_builder = VersionSkuAnalysisSnapshotBuilder()
        target_snapshot = snapshot_builder.build(
            category_bundle,
            competitor_profile_version_id=competitor_profile_version_id,
            sku_code=target_code,
        )
        trace_competitor_profile_memory("work_item_after_target_snapshot")
        snapshot_by_sku = {target_code: target_snapshot}
        stage_rows = (
            stage.recall_manifest.candidates,
            stage.pair_features.pairs,
            stage.purchase_pool.pairs,
            stage.value_substitution.pairs,
            stage.price_volume_pressure.pairs,
        )
        stage_candidate_orders = [
            [row.candidate.sku_code for row in rows] for rows in stage_rows
        ]
        if any(order != candidate_codes for order in stage_candidate_orders):
            raise ValueError("pair stages do not preserve the recalled candidate order")

        assemblies: list[PairAnalysisAssembly] = []
        gates: list[PairGateEvaluation] = []
        selection_inputs: list[PairSelectionInput] = []
        relation_calculator = V11RelationEvidenceCalculator()
        pair_calculator = PairAnalysisCalculator()
        pair_assembler = PairAnalysisAssembler()
        scope_classifier = CandidateScopeClassifier()
        gate_evaluator = PairGateEvaluator()
        target_fact_refs: set[str] = set()
        for recall_rank, candidate_code in enumerate(candidate_codes, start=1):
            if recall_rank == 1:
                trace_competitor_profile_memory("work_item_pair_1_before_snapshot")
            recalled_candidate = stage.recall_manifest.candidates.pop(0)
            pair_feature = stage.pair_features.pairs.pop(0)
            purchase_pool = stage.purchase_pool.pairs.pop(0)
            value_substitution = stage.value_substitution.pairs.pop(0)
            price_volume_pressure = stage.price_volume_pressure.pairs.pop(0)
            candidate_snapshot = snapshot_builder.build(
                category_bundle,
                competitor_profile_version_id=competitor_profile_version_id,
                sku_code=candidate_code,
            )
            if recall_rank == 1:
                trace_competitor_profile_memory("work_item_pair_1_after_snapshot")
            scope = scope_classifier.classify(
                target_snapshot=target_snapshot,
                candidate_snapshot=candidate_snapshot,
                authoritative_manifest_sku_codes=(stage.authoritative_sku_codes),
            )
            source = PairAnalysisCalculatorInput(
                competitor_profile_version_id=competitor_profile_version_id,
                pair_feature=pair_feature,
                purchase_pool=purchase_pool,
                value_substitution=value_substitution,
                price_volume_pressure=price_volume_pressure,
                target_snapshot=target_snapshot,
                candidate_snapshot=candidate_snapshot,
                recalled_candidate=recalled_candidate,
                recall_rank=recall_rank,
            )
            full_assembly = pair_assembler.assemble(
                pair_calculator.calculate(source)
            )
            if recall_rank == 1:
                trace_competitor_profile_memory("work_item_pair_1_after_assembly")
            assembly = build_authoritative_pair_projection(full_assembly)
            del full_assembly
            if recall_rank == 1:
                trace_competitor_profile_memory("work_item_pair_1_after_projection")
            gate = gate_evaluator.evaluate(
                scope=scope,
                assembly=assembly,
                legacy_relation_assessments=relation_calculator.calculate(
                    pair_feature=pair_feature,
                    purchase_pool=purchase_pool,
                    value_substitution=value_substitution,
                    price_volume_pressure=price_volume_pressure,
                    config=stage.config.relation,
                ),
            )
            assemblies.append(assembly)
            gates.append(gate)
            selection_inputs.append(
                PairSelectionInput(assembly=assembly, gate_evaluation=gate)
            )
            pair_fact_refs = _collect_fact_references((assembly, gate))
            target_fact_refs.update(pair_fact_refs)
            snapshot_by_sku[candidate_code] = (
                build_authoritative_snapshot_projection(
                    candidate_snapshot,
                    retained_fact_ids=pair_fact_refs,
                )
            )
            if recall_rank == 1:
                trace_competitor_profile_memory("work_item_pair_1_after_gate_projection")
            del (
                source,
                recalled_candidate,
                pair_feature,
                purchase_pool,
                value_substitution,
                price_volume_pressure,
                candidate_snapshot,
            )
            if recall_rank % 8 == 0:
                _release_memory()

        del category_bundle, snapshot_builder
        _release_memory()

        selection_result = CompetitorProfileV11Selector().select(
            selection_inputs,
            legacy_top3=stage.legacy_top3,
            # G33 assemblies were created immediately above and never crossed
            # a persistence or trust boundary. Re-expanding every large pair
            # solely to recompute the same hash can exceed the worker budget.
            verify_assembly_hashes=False,
        )
        scope = stage.serving_scope
        profile_context = ProfileVersionAnalysisContext(
            competitor_profile_version_id=competitor_profile_version_id,
            project_id=scope.project_id,
            category_code=scope.category_code,
            product_category=scope.product_category,
            release_scope_key=scope.release_scope_key,
            source_batch_ids=scope.source_batch_ids,
            market_window=scope.market_window,
            analysis_population=scope.analysis_population,
            score_policy=selection_result.score_policy,
            performance_storage_budget=production_performance_storage_budget(),
            legacy_recall_policy=stage.config.recall.model_dump(mode="json"),
            legacy_audit_summary={
                "legacy_candidate_count": len(candidate_codes),
                "legacy_top3": [
                    row.model_dump(mode="json") for row in stage.legacy_top3
                ],
                "legacy_selection_result_hash": stage.legacy_selection_result_hash,
            },
        )
        projected_target_snapshot = build_authoritative_snapshot_projection(
            target_snapshot,
            retained_fact_ids=target_fact_refs,
        )
        snapshot_by_sku[target_code] = projected_target_snapshot
        return CompetitorProfileV11GenerationWorkItem(
            profile_version=profile_context,
            target_snapshot=projected_target_snapshot,
            candidate_snapshots=[snapshot_by_sku[code] for code in candidate_codes],
            pair_assemblies=assemblies,
            gate_evaluations=gates,
            selection_result=selection_result,
        )


class CompetitorProfileV11ProductionService:
    """Create/reuse one V1.1 version and persist one immutable target draft."""

    def __init__(
        self,
        *,
        repository: CompetitorProfileV11Repository,
        input_provider: CompetitorProfileInputProvider,
        work_item_builder: CompetitorProfileV11ProductionWorkItemBuilder | None = None,
    ) -> None:
        self.repository = repository
        self.input_provider = input_provider
        self.work_item_builder = (
            work_item_builder or CompetitorProfileV11ProductionWorkItemBuilder()
        )

    def generate_single_draft(
        self,
        *,
        target_sku_code: str,
        profile_version: str,
        generated_by: str,
    ) -> CompetitorProfileV11ProductionGenerationResult:
        input_request = self.input_provider.build_production_input_request()
        category = self.input_provider.load_category_input_bundle(input_request)
        target_code = target_sku_code.strip().upper()
        target = self.input_provider.load_target_input(category, target_code)
        config = build_production_materialization_config(category)
        prepared = self.work_item_builder.prepare(category, target, config)
        trace_competitor_profile_memory("production_after_prepare")
        del category, target
        _release_memory()
        version = self._ensure_version(
            prepared,
            profile_version=profile_version,
            generated_by=generated_by,
        )
        try:
            snapshot_stage = self.work_item_builder.build_snapshot_stage(
                prepared,
                competitor_profile_version_id=version.competitor_profile_version_id,
            )
            trace_competitor_profile_memory("production_after_snapshot_stage")
            del prepared
            _release_memory()
            item = self.work_item_builder.build_work_item_from_snapshot_stage(
                snapshot_stage,
                competitor_profile_version_id=version.competitor_profile_version_id,
            )
            trace_competitor_profile_memory("production_after_work_item")
            del snapshot_stage
            _release_memory()
            materialized = CompetitorProfileV11Materializer().materialize(
                profile_version=item.profile_version,
                target_snapshot=item.target_snapshot,
                candidate_snapshots=item.candidate_snapshots,
                pair_assemblies=item.pair_assemblies,
                gate_evaluations=item.gate_evaluations,
                selection_result=item.selection_result,
                hard_excluded_inputs=item.hard_excluded_inputs,
                release_inputs=True,
                verify_source_hashes=False,
            )
            trace_competitor_profile_memory("production_after_materialize")
            del item
            _release_memory()
            created = self.repository.write_materialized_draft_without_readback(
                materialized.dto
            )
            trace_competitor_profile_memory("production_after_repository_write")
            self.repository.db.commit()
            status: Literal["generated", "reused"] = (
                "generated" if created else "reused"
            )
        except Exception as exc:
            self.repository.db.rollback()
            self._refresh_version_state(
                version.competitor_profile_version_id,
                failure_code=type(exc).__name__,
                failed_target_sku_code=target_code,
            )
            raise
        version = self._refresh_version_state(version.competitor_profile_version_id)
        return CompetitorProfileV11ProductionGenerationResult(
            status=status,
            version=version,
            materialized=materialized,
            candidate_count=len(materialized.dto.pair_analyses),
            selected_sku_codes=tuple(
                row.candidate_sku_code for row in materialized.dto.priority_selections
            ),
        )

    def _ensure_version(
        self,
        prepared: CompetitorProfileV11PreparedStages,
        *,
        profile_version: str,
        generated_by: str,
    ) -> CompetitorProfileVersionRecord:
        category = prepared.category_bundle
        scope = category.serving_scope
        method_versions = {
            **_legacy_method_versions(prepared.config),
            "v1_1_gate": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
            "v1_1_gate_config": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
            "v1_1_materializer": COMPETITOR_PROFILE_V1_1_MATERIALIZER_VERSION,
            "v1_1_pair_assembler": PAIR_ANALYSIS_ASSEMBLER_METHOD_VERSION,
            "v1_1_pair_calculator": PAIR_ANALYSIS_CALCULATOR_METHOD_VERSION,
            "v1_1_pair_projection": (
                PAIR_ANALYSIS_AUTHORITATIVE_PROJECTION_VERSION
            ),
            "v1_1_relation_calculator": (
                COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION
            ),
            "v1_1_selector": COMPETITOR_PROFILE_V1_1_SELECTION_METHOD_VERSION,
            "v1_1_selector_config": (COMPETITOR_PROFILE_V1_1_SELECTION_CONFIG_VERSION),
            "v1_1_snapshot_builder": SNAPSHOT_BUILDER_VERSION,
            "v1_1_snapshot_projection": (
                SNAPSHOT_AUTHORITATIVE_PROJECTION_VERSION
            ),
            "v1_1_orchestrator": PRODUCTION_ORCHESTRATOR_VERSION,
        }
        version_input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category.input_fingerprint,
                "serving_scope": scope.model_dump(mode="json"),
                "config": prepared.config.model_dump(mode="json"),
                "method_versions": method_versions,
            },
            version="competitor_profile_v1_1_version_input_v1",
        )
        version = self.repository.create_version(
            CompetitorProfileVersionDraftCreate(
                project_id=scope.project_id,
                category_code=scope.category_code,
                product_category=scope.product_category,
                storage_batch_id=scope.storage_batch_id,
                release_scope_key=scope.release_scope_key,
                profile_version=profile_version,
                schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
                rule_version=COMPETITOR_PROFILE_V1_1_RULE_VERSION,
                method_version=COMPETITOR_PROFILE_V1_1_METHOD_VERSION,
                method_versions_json=dict(sorted(method_versions.items())),
                serving_scope=scope,
                generated_by=generated_by,
                sku_count=len(category.authoritative_sku_codes),
                input_fingerprint=version_input_fingerprint,
                candidate_universe_fingerprint=stable_hash(
                    {
                        "authoritative_sku_codes": category.authoritative_sku_codes,
                        "category_input_fingerprint": category.input_fingerprint,
                    },
                    version="competitor_profile_v1_1_candidate_universe_v1",
                ),
                result_hash=stable_hash(
                    {
                        "profile_version": profile_version,
                        "release_scope_key": scope.release_scope_key,
                        "version_input_fingerprint": version_input_fingerprint,
                    },
                    version="competitor_profile_v1_1_version_result_v1",
                ),
                processing_status="running",
            )
        )
        self.repository.db.commit()
        return version

    def _refresh_version_state(
        self,
        competitor_profile_version_id: str,
        *,
        failure_code: str | None = None,
        failed_target_sku_code: str | None = None,
    ) -> CompetitorProfileVersionRecord:
        db = self.repository.db
        profile_rows = list(
            db.execute(
                select(entities.Core3SkuCompetitorProfile.analysis_state)
                .where(
                    entities.Core3SkuCompetitorProfile.competitor_profile_version_id
                    == competitor_profile_version_id
                )
                .where(
                    entities.Core3SkuCompetitorProfile.schema_version
                    == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
                )
            ).scalars()
        )
        states = Counter(profile_rows)
        pair_count = _version_row_count(
            db,
            entities.Core3SkuCompetitorProfilePair,
            competitor_profile_version_id,
        )
        relation_count = _version_row_count(
            db,
            entities.Core3SkuCompetitorProfileRelation,
            competitor_profile_version_id,
        )
        selection_count = _version_row_count(
            db,
            entities.Core3SkuCompetitorProfileSelection,
            competitor_profile_version_id,
        )
        version = self.repository.update_draft_generation_state(
            competitor_profile_version_id,
            ready_count=states.get("ready", 0),
            partial_count=states.get("partial", 0),
            blocked_count=states.get("blocked", 0),
            failed_count=1 if failure_code else 0,
            pair_count=pair_count,
            relation_count=relation_count,
            selection_count=selection_count,
            processing_status=(
                "failed" if failure_code else "success" if profile_rows else "running"
            ),
            safe_error_summary=(
                {
                    "failures": {
                        failed_target_sku_code or "unknown": failure_code,
                    }
                }
                if failure_code
                else {}
            ),
        )
        self.repository.db.commit()
        return version


def production_performance_storage_budget() -> G29PerformanceStorageBudget:
    return G29PerformanceStorageBudget.model_validate(
        {
            "categories": [
                {
                    "category_code": "TV",
                    "maximum_candidate_count": 377,
                    "maximum_generation_p95_ms": 60_000,
                    "maximum_peak_memory_mib": 1_200,
                    "maximum_serialized_draft_bytes": 536_870_912,
                },
                {
                    "category_code": "AC",
                    "maximum_candidate_count": 155,
                    "maximum_generation_p95_ms": 30_000,
                    "maximum_peak_memory_mib": 600,
                    "maximum_serialized_draft_bytes": 268_435_456,
                },
            ]
        }
    )


def _pairs_by_sku(rows):
    result = {row.candidate.sku_code: row for row in rows}
    if len(result) != len(rows):
        raise ValueError("pair stage contains duplicate candidate SKU codes")
    return result


def _collect_fact_references(value) -> set[str]:
    references: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"supporting_fact_refs", "input_fact_refs"} and isinstance(
                child, list
            ):
                references.update(str(item) for item in child)
            else:
                references.update(_collect_fact_references(child))
        return references
    if isinstance(value, (list, tuple)):
        for child in value:
            references.update(_collect_fact_references(child))
        return references
    model_fields = getattr(type(value), "model_fields", None)
    if isinstance(model_fields, dict):
        for field_name in model_fields:
            child = getattr(value, field_name)
            if field_name in {"supporting_fact_refs", "input_fact_refs"} and isinstance(
                child, list
            ):
                references.update(str(item) for item in child)
            else:
                references.update(_collect_fact_references(child))
    return references


def _legacy_method_versions(
    config: CompetitorProfileMaterializationConfig,
) -> dict[str, str]:
    return {
        "candidate_eligibility": config.eligibility.config_version,
        "candidate_recall": config.recall.config_version,
        "key_selection": config.key_selection.config_version,
        "materializer": config.config_version,
        "price_volume": config.price_volume.config_version,
        "purchase_pool": config.purchase_pool.config_version,
        "relation": config.relation.config_version,
        "value_substitution": config.value_substitution.config_version,
    }


def _version_row_count(db, model, version_id: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(model)
            .where(model.competitor_profile_version_id == version_id)
            .where(model.schema_version == COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION)
        )
        or 0
    )


def _release_memory() -> None:
    """Release completed production phases back to the Linux host when possible."""

    gc.collect()
    try:
        malloc_trim = ctypes.CDLL(None).malloc_trim
    except (AttributeError, OSError):
        return
    malloc_trim(0)


__all__ = [
    "CompetitorProfileV11PreparedStages",
    "CompetitorProfileV11ProductionGenerationResult",
    "CompetitorProfileV11ProductionService",
    "CompetitorProfileV11SnapshotStage",
    "CompetitorProfileV11ProductionWorkItemBuilder",
    "PRODUCTION_ORCHESTRATOR_VERSION",
    "production_performance_storage_budget",
]
