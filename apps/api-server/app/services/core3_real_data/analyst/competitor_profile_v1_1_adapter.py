"""Pure V1.1 profile-to-agent projections.

The adapter receives only already-materialized reader DTOs.  It never recalls,
scores, classifies, sorts, selects, or reads persistence itself.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import Field, model_serializer, model_validator

from app.services.core3_real_data.analyst.competitor_profile_v1_1_persistence_schemas import (
    CompetitorProfileV11CompactDTO,
    CompetitorProfileV11QuestionDTO,
    CompetitorProfileV11ReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    CompetitorProfileAdapterContract,
    CompetitorProfileAnalysisDTO,
    CompetitorProfileV11BaseModel,
    EvidenceRef,
    FactIndexEntry,
    IdentityMarketSnapshot,
    PairBusinessQuestionResult,
    PairIndexItem,
    PairScopeStatus,
    PairSelectionAssessment,
    ProfileVersionAnalysisContext,
    QuestionCode,
    SkuCompetitionAnalysisSummary,
    VersionSkuAnalysisSnapshot,
    _assert_authoritative_adapter_input,
    _assert_authoritative_adapter_runtime_state,
    _strip_adapter_compatibility_fields,
)


class CompetitorProfileAdapterInputError(ValueError):
    """Raised when a reader projection is unavailable, stale, or incomplete."""


class AgentReadProjectionReceipt(CompetitorProfileV11BaseModel):
    read_mode: Literal["compact", "question_specific"]
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    target_snapshot_result_hash: str = Field(min_length=1)
    summary_result_hash: str = Field(min_length=1)
    candidate_snapshot_result_hashes: dict[str, str] = Field(default_factory=dict)
    candidate_pair_result_hashes: dict[str, str] = Field(default_factory=dict)
    priority_selection_result_hashes: dict[str, str] = Field(default_factory=dict)
    adapter_projection_hash: str = Field(min_length=1)
    receipt_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_receipt(self) -> "AgentReadProjectionReceipt":
        for values in (
            self.candidate_snapshot_result_hashes,
            self.candidate_pair_result_hashes,
            self.priority_selection_result_hashes,
        ):
            if list(values) != sorted(values):
                raise ValueError("agent read receipt hash maps must be sorted")
        expected = _hash_payload(self.model_dump(mode="json", exclude={"receipt_hash"}))
        if self.receipt_hash != expected:
            raise ValueError("agent read receipt hash is inconsistent")
        return self


class AgentCompactProjection(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    adapter_version: Literal["competitor_profile_agent_adapter_v1_1"] = (
        "competitor_profile_agent_adapter_v1_1"
    )
    read_mode: Literal["compact"] = "compact"
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    source_receipt: AgentReadProjectionReceipt
    profile_version: ProfileVersionAnalysisContext
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_competition_summary: SkuCompetitionAnalysisSummary
    priority_order: list[str] = Field(max_length=3)
    full_pair_index: list[PairIndexItem]

    @classmethod
    def build(cls, projection: dict[str, Any]) -> "AgentCompactProjection":
        _assert_authoritative_adapter_input(projection)
        payload = _strip_adapter_compatibility_fields(
            {
                "source": "competitor_profile_v1_1",
                "adapter_version": "competitor_profile_agent_adapter_v1_1",
                "read_mode": "compact",
                **projection,
            }
        )
        receipt = _read_receipt(
            read_mode="compact",
            projection=payload,
            candidate_pair_result_hashes={
                row["candidate_sku_code"]: row["pair_result_hash"]
                for row in payload["full_pair_index"]
            },
        )
        return cls.model_validate({**payload, "source_receipt": receipt})

    @model_validator(mode="after")
    def validate_projection(self) -> "AgentCompactProjection":
        if self.competitor_profile_version_id != (
            self.profile_version.competitor_profile_version_id
        ):
            raise ValueError("compact adapter must lock one profile version")
        _validate_projection_scope(
            profile_version=self.profile_version,
            target_snapshot=self.target_snapshot,
            sku_summary=self.sku_competition_summary,
        )
        if self.priority_order != [
            row.candidate_sku_code
            for row in self.sku_competition_summary.priority_competitors
        ]:
            raise ValueError("compact adapter must preserve saved priority order")
        pair_codes = {row.candidate_sku_code for row in self.full_pair_index}
        if not set(self.priority_order).issubset(pair_codes):
            raise ValueError("compact priority candidates must exist in the pair index")
        _validate_read_receipt(self)
        return self

    @model_serializer(mode="wrap")
    def serialize_projection(self, handler: Any) -> dict[str, Any]:
        return _serialize_read_projection(self, handler)


class AgentQuestionCandidate(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_result_hash: str = Field(min_length=1)
    identity: IdentityMarketSnapshot
    recall_rank: int = Field(ge=1)
    primary_role: str | None = None
    selection_assessment: PairSelectionAssessment
    question_result: PairBusinessQuestionResult
    overall_conclusion_strength: str = Field(min_length=1)
    review_required: bool = False
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    pair_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate(self) -> "AgentQuestionCandidate":
        if self.identity.sku_code != self.candidate_sku_code:
            raise ValueError("question adapter identity must match candidate SKU")
        return self


class AgentQuestionProjection(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    adapter_version: Literal["competitor_profile_agent_adapter_v1_1"] = (
        "competitor_profile_agent_adapter_v1_1"
    )
    read_mode: Literal["question_specific"] = "question_specific"
    question_code: QuestionCode
    competitor_profile_version_id: str = Field(min_length=1)
    profile_result_hash: str = Field(min_length=1)
    source_receipt: AgentReadProjectionReceipt
    profile_version: ProfileVersionAnalysisContext
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_competition_summary: SkuCompetitionAnalysisSummary
    priority_order: list[str] = Field(max_length=3)
    candidates: list[AgentQuestionCandidate]
    omitted_hard_exclusion_count: int = Field(ge=0)
    fact_index: dict[str, FactIndexEntry]
    evidence_index: dict[str, EvidenceRef]

    @classmethod
    def build(cls, projection: dict[str, Any]) -> "AgentQuestionProjection":
        _assert_authoritative_adapter_input(projection)
        payload = _strip_adapter_compatibility_fields(
            {
                "source": "competitor_profile_v1_1",
                "adapter_version": "competitor_profile_agent_adapter_v1_1",
                "read_mode": "question_specific",
                **projection,
            }
        )
        receipt = _read_receipt(
            read_mode="question_specific",
            projection=payload,
            candidate_snapshot_result_hashes={
                row["candidate_sku_code"]: row["candidate_snapshot_result_hash"]
                for row in payload["candidates"]
            },
            candidate_pair_result_hashes={
                row["candidate_sku_code"]: row["pair_result_hash"]
                for row in payload["candidates"]
            },
        )
        return cls.model_validate({**payload, "source_receipt": receipt})

    @model_validator(mode="after")
    def validate_projection(self) -> "AgentQuestionProjection":
        if self.competitor_profile_version_id != (
            self.profile_version.competitor_profile_version_id
        ):
            raise ValueError("question adapter must lock one profile version")
        _validate_projection_scope(
            profile_version=self.profile_version,
            target_snapshot=self.target_snapshot,
            sku_summary=self.sku_competition_summary,
        )
        codes = [row.candidate_sku_code for row in self.candidates]
        if codes != sorted(set(codes)):
            raise ValueError("question adapter candidates must be sorted and unique")
        if any(
            row.question_result.question_code != self.question_code
            for row in self.candidates
        ):
            raise ValueError("question adapter contains a different question")
        if self.priority_order != [
            row.candidate_sku_code
            for row in self.sku_competition_summary.priority_competitors
        ]:
            raise ValueError("question adapter must preserve saved priority order")
        if not set(self.priority_order).issubset(set(codes)):
            raise ValueError(
                "question priority candidates must exist in the projection"
            )
        expected_excluded = self.sku_competition_summary.excluded_candidate_count
        if expected_excluded is not None and (
            self.omitted_hard_exclusion_count != expected_excluded
        ):
            raise ValueError("question adapter hard-exclusion count is stale")
        if (
            len(self.candidates) + self.omitted_hard_exclusion_count
            != self.sku_competition_summary.analysis_candidate_count
        ):
            raise ValueError(
                "question adapter must conserve the saved candidate universe"
            )
        _validate_question_fact_closure(self)
        _validate_read_receipt(self)
        return self

    @model_serializer(mode="wrap")
    def serialize_projection(self, handler: Any) -> dict[str, Any]:
        return _serialize_read_projection(self, handler)


class CompetitorProfileAgentAdapterResult(CompetitorProfileV11BaseModel):
    status: Literal["available", "profile_unavailable"]
    read_mode: Literal["full", "compact", "question_specific"]
    preview: bool = False
    competitor_profile_version_id: str | None = None
    full: CompetitorProfileAdapterContract | None = None
    compact: AgentCompactProjection | None = None
    question: AgentQuestionProjection | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "CompetitorProfileAgentAdapterResult":
        projections = [self.full, self.compact, self.question]
        populated = sum(row is not None for row in projections)
        if self.status == "profile_unavailable":
            if self.competitor_profile_version_id is not None or populated:
                raise ValueError(
                    "unavailable adapter results cannot expose a projection"
                )
            return self
        expected = {
            "full": self.full,
            "compact": self.compact,
            "question_specific": self.question,
        }[self.read_mode]
        if (
            self.competitor_profile_version_id is None
            or populated != 1
            or expected is None
        ):
            raise ValueError(
                "available adapter results require the requested projection"
            )
        return self


class CompetitorProfileAgentAdapter:
    """Map fresh G31 reader projections to immutable, runtime-safe contracts."""

    def adapt(
        self,
        source: CompetitorProfileV11ReadResult,
    ) -> CompetitorProfileAgentAdapterResult:
        fresh = CompetitorProfileV11ReadResult.model_validate(
            source.model_dump(mode="json")
        )
        if fresh.status == "profile_unavailable":
            return CompetitorProfileAgentAdapterResult(
                status="profile_unavailable",
                read_mode=fresh.read_mode,
                preview=fresh.preview,
            )
        if fresh.full is not None:
            projection = self.adapt_full(fresh.full)
            return CompetitorProfileAgentAdapterResult(
                status="available",
                read_mode="full",
                preview=fresh.preview,
                competitor_profile_version_id=fresh.competitor_profile_version_id,
                full=projection,
            )
        if fresh.compact is not None:
            projection = self.adapt_compact(fresh.compact)
            return CompetitorProfileAgentAdapterResult(
                status="available",
                read_mode="compact",
                preview=fresh.preview,
                competitor_profile_version_id=fresh.competitor_profile_version_id,
                compact=projection,
            )
        if fresh.question is not None:
            projection = self.adapt_question(fresh.question)
            return CompetitorProfileAgentAdapterResult(
                status="available",
                read_mode="question_specific",
                preview=fresh.preview,
                competitor_profile_version_id=fresh.competitor_profile_version_id,
                question=projection,
            )
        raise CompetitorProfileAdapterInputError("available read has no projection")

    def adapt_full(
        self,
        source: CompetitorProfileAnalysisDTO,
    ) -> CompetitorProfileAdapterContract:
        dto = CompetitorProfileAnalysisDTO.model_validate(
            source.model_dump(mode="json")
        )
        snapshots = {
            row.identity_market.sku_code: _safe_model(row)
            for row in dto.candidate_snapshots
        }
        analyzed: list[dict[str, Any]] = []
        excluded: list[dict[str, Any]] = []
        for pair in dto.pair_analyses:
            snapshot = snapshots[pair.candidate_sku_code]
            if pair.selection_assessment is None:
                raise CompetitorProfileAdapterInputError(
                    f"pair {pair.candidate_sku_code} has no saved selection assessment"
                )
            if pair.scope_status == PairScopeStatus.EXCLUDED.value:
                excluded.append(
                    _strip_adapter_compatibility_fields(
                        {
                            "candidate_sku_code": pair.candidate_sku_code,
                            "candidate_snapshot_ref": pair.candidate_snapshot_ref,
                            "candidate_snapshot_result_hash": snapshot["result_hash"],
                            "candidate_snapshot": snapshot,
                            "identity": snapshot["identity_market"],
                            "recall_rank": pair.recall_rank,
                            "recall_sources": pair.recall_sources,
                            "exclusion_reason_code": pair.exclusion_reason_code,
                            "selection_assessment": pair.selection_assessment.model_dump(
                                mode="json"
                            ),
                            "overall_conclusion": pair.overall_conclusion.model_dump(
                                mode="json"
                            ),
                            "source_facts": [
                                row.model_dump(mode="json") for row in pair.source_facts
                            ],
                            "review_required": pair.review_required,
                            "review_items": [
                                row.model_dump(mode="json") for row in pair.review_items
                            ],
                            "evidence_refs": [
                                row.model_dump(mode="json")
                                for row in pair.evidence_refs
                            ],
                            "limitations": pair.limitations,
                            "pair_result_hash": pair.result_hash,
                        }
                    )
                )
                continue
            required = (
                pair.purchase_pool,
                pair.dimensions,
                pair.value_anchor_analysis,
                pair.replacement_pressure_analysis,
                pair.purchase_pressure_comparison,
                pair.market_validation,
                pair.primary_role,
                pair.score_breakdown,
            )
            if any(row is None for row in required):
                raise CompetitorProfileAdapterInputError(
                    f"analyzable pair {pair.candidate_sku_code} is incomplete"
                )
            analyzed.append(
                _strip_adapter_compatibility_fields(
                    {
                        "candidate_sku_code": pair.candidate_sku_code,
                        "candidate_snapshot_ref": pair.candidate_snapshot_ref,
                        "candidate_snapshot_result_hash": snapshot["result_hash"],
                        "candidate_snapshot": snapshot,
                        "identity": snapshot["identity_market"],
                        "recall_rank": pair.recall_rank,
                        "recall_sources": pair.recall_sources,
                        "purchase_pool": pair.purchase_pool.model_dump(mode="json"),
                        "dimension_results": pair.dimensions.model_dump(mode="json"),
                        "value_anchor_analysis": pair.value_anchor_analysis.model_dump(
                            mode="json"
                        ),
                        "replacement_pressure_analysis": (
                            pair.replacement_pressure_analysis.model_dump(mode="json")
                        ),
                        "purchase_pressure_comparison": (
                            pair.purchase_pressure_comparison.model_dump(mode="json")
                        ),
                        "market_validation": pair.market_validation.model_dump(
                            mode="json"
                        ),
                        "comparison_roles": pair.comparison_roles,
                        "primary_role": pair.primary_role,
                        "score_breakdown": pair.score_breakdown.model_dump(mode="json"),
                        "relation_assessments": [
                            row.model_dump(mode="json")
                            for row in pair.relation_assessments
                        ],
                        "business_questions": [
                            row.model_dump(mode="json")
                            for row in pair.business_questions
                        ],
                        "selection_assessment": pair.selection_assessment.model_dump(
                            mode="json"
                        ),
                        "derived_facts": [
                            _derived_dimension_fact(row, pair)
                            for row in pair.derived_facts
                        ],
                        "source_facts": [
                            row.model_dump(mode="json") for row in pair.source_facts
                        ],
                        "overall_conclusion": pair.overall_conclusion.model_dump(
                            mode="json"
                        ),
                        "review_required": pair.review_required,
                        "review_items": [
                            row.model_dump(mode="json") for row in pair.review_items
                        ],
                        "evidence_refs": [
                            row.model_dump(mode="json") for row in pair.evidence_refs
                        ],
                        "limitations": pair.limitations,
                        "pair_result_hash": pair.result_hash,
                    }
                )
            )
        projection = {
            "competitor_profile_version_id": (
                dto.profile_version.competitor_profile_version_id
            ),
            "profile_result_hash": dto.profile_result_hash,
            "profile_version": _safe_model(
                dto.profile_version, "adapter.profile_version"
            ),
            "target_snapshot": _safe_model(
                dto.target_snapshot, "adapter.target_snapshot"
            ),
            "sku_competition_summary": _safe_model(
                dto.sku_summary,
                "adapter.sku_competition_summary",
            ),
            "candidates": analyzed,
            "excluded_candidates": excluded,
            "priority_order": [
                row.candidate_sku_code for row in dto.priority_selections
            ],
            "previous_priority_diffs": [
                {
                    "candidate_sku_code": row.candidate_sku_code,
                    "previous_rank": row.legacy_rank,
                    "current_rank": row.new_rank,
                    "diff_status": row.diff_status,
                    "reason_code": row.reason_code,
                    "reason_cn": row.reason_cn,
                }
                for row in dto.sku_summary.legacy_selection_diffs
            ],
            "fact_index": {
                key: row.model_dump(mode="json")
                for key, row in sorted(dto.fact_index.items())
            },
            "evidence_index": {
                key: row.model_dump(mode="json")
                for key, row in sorted(dto.evidence_index.items())
            },
        }
        return CompetitorProfileAdapterContract.build_from_authoritative_projection(
            projection
        )

    def adapt_compact(
        self,
        source: CompetitorProfileV11CompactDTO,
    ) -> AgentCompactProjection:
        dto = CompetitorProfileV11CompactDTO.model_validate(
            source.model_dump(mode="json")
        )
        return AgentCompactProjection.build(
            {
                "competitor_profile_version_id": (
                    dto.profile_version.competitor_profile_version_id
                ),
                "profile_result_hash": dto.profile_result_hash,
                "profile_version": _safe_model(
                    dto.profile_version,
                    "adapter.profile_version",
                ),
                "target_snapshot": _safe_model(
                    dto.target_snapshot,
                    "adapter.target_snapshot",
                ),
                "sku_competition_summary": _safe_model(
                    dto.sku_summary,
                    "adapter.sku_competition_summary",
                ),
                "priority_order": [
                    row.candidate_sku_code for row in dto.priority_selections
                ],
                "full_pair_index": [
                    row.model_dump(mode="json") for row in dto.full_pair_index
                ],
            }
        )

    def adapt_question(
        self,
        source: CompetitorProfileV11QuestionDTO,
    ) -> AgentQuestionProjection:
        dto = CompetitorProfileV11QuestionDTO.model_validate(
            source.model_dump(mode="json")
        )
        candidates = []
        for row in dto.pairs:
            pair = row.pair_analysis
            snapshot = row.candidate_snapshot
            if (
                snapshot.competitor_profile_version_id
                != dto.profile_version.competitor_profile_version_id
                or snapshot.project_id != dto.profile_version.project_id
                or snapshot.category_code != dto.profile_version.category_code
                or snapshot.release_scope_key != dto.profile_version.release_scope_key
            ):
                raise CompetitorProfileAdapterInputError(
                    f"question candidate {pair.candidate_sku_code} has mixed profile scope"
                )
            if (
                pair.competitor_profile_version_id
                != dto.profile_version.competitor_profile_version_id
                or pair.project_id != dto.profile_version.project_id
                or pair.category_code != dto.profile_version.category_code
                or pair.release_scope_key != dto.profile_version.release_scope_key
                or pair.target_sku_code != dto.sku_summary.target_sku_code
                or pair.target_snapshot_ref != dto.target_snapshot.snapshot_ref
            ):
                raise CompetitorProfileAdapterInputError(
                    f"question pair {pair.candidate_sku_code} has mixed profile scope"
                )
            if pair.selection_assessment is None:
                raise CompetitorProfileAdapterInputError(
                    f"question pair {pair.candidate_sku_code} has no selection assessment"
                )
            candidates.append(
                _strip_adapter_compatibility_fields(
                    {
                        "candidate_sku_code": pair.candidate_sku_code,
                        "candidate_snapshot_ref": pair.candidate_snapshot_ref,
                        "candidate_snapshot_result_hash": (
                            row.candidate_snapshot.result_hash
                        ),
                        "identity": row.candidate_snapshot.identity_market.model_dump(
                            mode="json"
                        ),
                        "recall_rank": pair.recall_rank,
                        "primary_role": pair.primary_role,
                        "selection_assessment": pair.selection_assessment.model_dump(
                            mode="json"
                        ),
                        "question_result": row.question_result.model_dump(mode="json"),
                        "overall_conclusion_strength": (
                            pair.overall_conclusion_strength
                        ),
                        "review_required": pair.review_required,
                        "evidence_refs": [
                            item.model_dump(mode="json") for item in pair.evidence_refs
                        ],
                        "limitations": pair.limitations,
                        "pair_result_hash": pair.result_hash,
                    }
                )
            )
        return AgentQuestionProjection.build(
            {
                "question_code": dto.question_code,
                "competitor_profile_version_id": (
                    dto.profile_version.competitor_profile_version_id
                ),
                "profile_result_hash": dto.profile_result_hash,
                "profile_version": _safe_model(
                    dto.profile_version,
                    "adapter.profile_version",
                ),
                "target_snapshot": _safe_model(
                    dto.target_snapshot,
                    "adapter.target_snapshot",
                ),
                "sku_competition_summary": _safe_model(
                    dto.sku_summary,
                    "adapter.sku_competition_summary",
                ),
                "priority_order": [
                    row.candidate_sku_code for row in dto.priority_selections
                ],
                "candidates": candidates,
                "omitted_hard_exclusion_count": (
                    dto.sku_summary.excluded_candidate_count or 0
                ),
                "fact_index": {
                    key: row.model_dump(mode="json")
                    for key, row in sorted(dto.fact_index.items())
                },
                "evidence_index": {
                    key: row.model_dump(mode="json")
                    for key, row in sorted(dto.evidence_index.items())
                },
            }
        )


def _safe_model(
    model: CompetitorProfileV11BaseModel,
    path: str = "adapter",
) -> dict[str, Any]:
    return _strip_adapter_compatibility_fields(
        model.model_dump(mode="json"),
        path,
    )


def _validate_projection_scope(
    *,
    profile_version: ProfileVersionAnalysisContext,
    target_snapshot: VersionSkuAnalysisSnapshot,
    sku_summary: SkuCompetitionAnalysisSummary,
) -> None:
    if target_snapshot.competitor_profile_version_id != (
        profile_version.competitor_profile_version_id
    ):
        raise ValueError("agent read target snapshot must lock the profile version")
    if (
        target_snapshot.project_id != profile_version.project_id
        or target_snapshot.category_code != profile_version.category_code
        or target_snapshot.release_scope_key != profile_version.release_scope_key
    ):
        raise ValueError("agent read target snapshot scope must match the profile")
    if target_snapshot.identity_market.sku_code != sku_summary.target_sku_code:
        raise ValueError("agent read target snapshot and summary must use one SKU")


def _validate_question_fact_closure(projection: AgentQuestionProjection) -> None:
    supporting_fact_refs = {
        fact_ref
        for candidate in projection.candidates
        for fact_ref in candidate.question_result.conclusion.supporting_fact_refs
    }
    if not supporting_fact_refs.issubset(projection.fact_index):
        raise ValueError("question adapter facts must resolve in the saved fact index")
    missing_evidence = {
        evidence_key
        for fact_ref in supporting_fact_refs
        for evidence_key in projection.fact_index[fact_ref].evidence_keys
        if evidence_key not in projection.evidence_index
    }
    if missing_evidence:
        raise ValueError("question adapter evidence keys must resolve uniquely")
    indexed_evidence = {
        _hash_payload(row.model_dump(mode="json"))
        for row in projection.evidence_index.values()
    }
    if any(
        _hash_payload(evidence.model_dump(mode="json")) not in indexed_evidence
        for candidate in projection.candidates
        for evidence in candidate.evidence_refs
    ):
        raise ValueError("question adapter evidence refs must resolve uniquely")


def _derived_dimension_fact(fact: Any, pair: Any) -> dict[str, Any]:
    if len(fact.values) != 1:
        raise CompetitorProfileAdapterInputError(
            f"derived fact {fact.fact_id} is not a typed dimension-gate fact"
        )
    typed_value = fact.values[0]
    value = typed_value.value
    required = {"availability", "conclusion_strength", "conclusion_direction"}
    dimension_code = fact.code.removeprefix("dimension_result:")
    if dimension_code == fact.code:
        raise CompetitorProfileAdapterInputError(
            f"derived fact {fact.fact_id} has an unsupported fact code"
        )
    if isinstance(value, dict):
        if set(value) != required:
            raise CompetitorProfileAdapterInputError(
                f"derived fact {fact.fact_id} has an unsupported runtime shape"
            )
    else:
        gate = next(
            (
                row
                for row in pair.dimension_gates
                if str(row.dimension_code) == dimension_code
            ),
            None,
        )
        if typed_value.presence != "missing" or gate is None:
            raise CompetitorProfileAdapterInputError(
                f"derived fact {fact.fact_id} cannot resolve its saved gate"
            )
        value = {
            "availability": gate.availability,
            "conclusion_strength": gate.conclusion_strength,
            "conclusion_direction": gate.conclusion_direction,
        }
    return {
        "fact_type": "dimension_gate",
        "fact_id": fact.fact_id,
        "code": fact.code,
        "source_path": f"pair.dimension_results.{dimension_code}",
        "roles": fact.roles,
        "availability": value["availability"],
        "conclusion_strength": value["conclusion_strength"],
        "conclusion_direction": value["conclusion_direction"],
        "support_status": fact.support_status,
        "confidence": fact.confidence,
        "evidence_refs": [row.model_dump(mode="json") for row in fact.evidence_refs],
    }


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _priority_hashes(projection: dict[str, Any]) -> dict[str, str]:
    rows = projection["sku_competition_summary"]["priority_competitors"]
    return {
        row["candidate_sku_code"]: row["result_hash"]
        for row in sorted(rows, key=lambda item: item["candidate_sku_code"])
    }


def _read_receipt(
    *,
    read_mode: Literal["compact", "question_specific"],
    projection: dict[str, Any],
    candidate_snapshot_result_hashes: dict[str, str] | None = None,
    candidate_pair_result_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "read_mode": read_mode,
        "competitor_profile_version_id": projection["competitor_profile_version_id"],
        "profile_result_hash": projection["profile_result_hash"],
        "target_snapshot_result_hash": projection["target_snapshot"]["result_hash"],
        "summary_result_hash": projection["sku_competition_summary"]["result_hash"],
        "candidate_snapshot_result_hashes": dict(
            sorted((candidate_snapshot_result_hashes or {}).items())
        ),
        "candidate_pair_result_hashes": dict(
            sorted((candidate_pair_result_hashes or {}).items())
        ),
        "priority_selection_result_hashes": _priority_hashes(projection),
        "adapter_projection_hash": _hash_payload(projection),
    }
    payload["receipt_hash"] = _hash_payload(payload)
    return payload


def _projection_without_receipt(value: Any) -> dict[str, Any]:
    common = {
        "source": value.source,
        "adapter_version": value.adapter_version,
        "read_mode": value.read_mode,
        "competitor_profile_version_id": value.competitor_profile_version_id,
        "profile_result_hash": value.profile_result_hash,
        "profile_version": value.profile_version.model_dump(mode="json"),
        "target_snapshot": value.target_snapshot.model_dump(mode="json"),
        "sku_competition_summary": value.sku_competition_summary.model_dump(
            mode="json"
        ),
        "priority_order": value.priority_order,
    }
    if isinstance(value, AgentCompactProjection):
        common["full_pair_index"] = [
            row.model_dump(mode="json") for row in value.full_pair_index
        ]
    else:
        common.update(
            {
                "question_code": str(value.question_code),
                "candidates": [row.model_dump(mode="json") for row in value.candidates],
                "omitted_hard_exclusion_count": value.omitted_hard_exclusion_count,
                "fact_index": {
                    key: row.model_dump(mode="json")
                    for key, row in value.fact_index.items()
                },
                "evidence_index": {
                    key: row.model_dump(mode="json")
                    for key, row in value.evidence_index.items()
                },
            }
        )
    return _strip_adapter_compatibility_fields(common)


def _validate_read_receipt(value: Any) -> None:
    receipt = value.source_receipt
    if (
        receipt.read_mode != value.read_mode
        or receipt.competitor_profile_version_id != value.competitor_profile_version_id
        or receipt.profile_result_hash != value.profile_result_hash
        or receipt.target_snapshot_result_hash != value.target_snapshot.result_hash
        or receipt.summary_result_hash != value.sku_competition_summary.result_hash
        or receipt.priority_selection_result_hashes
        != {
            row.candidate_sku_code: row.result_hash
            for row in sorted(
                value.sku_competition_summary.priority_competitors,
                key=lambda item: item.candidate_sku_code,
            )
        }
        or receipt.adapter_projection_hash
        != _hash_payload(_projection_without_receipt(value))
    ):
        raise ValueError("agent read receipt does not match its projection")


def _serialize_read_projection(value: Any, handler: Any) -> dict[str, Any]:
    current = handler(value)
    _assert_authoritative_adapter_runtime_state(current)
    projection = _projection_without_receipt(value)
    receipt = current["source_receipt"]
    receipt_without_hash = {
        key: child for key, child in receipt.items() if key != "receipt_hash"
    }
    if _hash_payload(receipt_without_hash) != receipt["receipt_hash"]:
        raise ValueError("agent read receipt changed after construction")
    if _hash_payload(projection) != receipt["adapter_projection_hash"]:
        raise ValueError("agent read receipt must bind the runtime projection")
    return current


__all__ = [
    "AgentCompactProjection",
    "AgentQuestionCandidate",
    "AgentQuestionProjection",
    "AgentReadProjectionReceipt",
    "CompetitorProfileAdapterInputError",
    "CompetitorProfileAgentAdapter",
    "CompetitorProfileAgentAdapterResult",
]
