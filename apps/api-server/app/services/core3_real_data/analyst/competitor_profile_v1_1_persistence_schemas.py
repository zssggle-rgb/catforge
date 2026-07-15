"""Typed persistence and read projections for competitor profile V1.1.

The analysis DTO remains the canonical lossless contract.  These models only
describe which already-saved parts are returned by each repository read mode;
they never recompute candidates, scores, relations, or conclusions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    CompetitorProfileAnalysisDTO,
    CompetitorProfileV11BaseModel,
    EvidenceRef,
    FactIndexEntry,
    PairAnalysisSnapshot,
    PairBusinessQuestionResult,
    PairIndexItem,
    PriorityCompetitorSelection,
    ProfileGenerationReceipt,
    ProfileVersionAnalysisContext,
    QuestionCode,
    SkuCompetitionAnalysisSummary,
    VersionSkuAnalysisSnapshot,
)


class CompetitorProfileV11CompactDTO(CompetitorProfileV11BaseModel):
    """Bounded projection used before a caller requests pair detail."""

    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    profile_version: ProfileVersionAnalysisContext
    generation_receipt: ProfileGenerationReceipt
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_summary: SkuCompetitionAnalysisSummary
    priority_selections: list[PriorityCompetitorSelection]
    full_pair_index: list[PairIndexItem]
    profile_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_compact(self) -> "CompetitorProfileV11CompactDTO":
        if self.sku_summary.analysis_candidate_count != len(self.full_pair_index):
            raise ValueError("compact candidate count must match the pair index")
        if self.priority_selections != self.sku_summary.priority_competitors:
            raise ValueError("compact selections must match the saved summary")
        index_codes = [row.candidate_sku_code for row in self.full_pair_index]
        if index_codes != sorted(set(index_codes)):
            raise ValueError("compact pair index must be sorted and unique")
        selected = {
            row.candidate_sku_code: row.selection_rank
            for row in self.priority_selections
        }
        if any(
            row.selected_rank != selected.get(row.candidate_sku_code)
            for row in self.full_pair_index
        ):
            raise ValueError("compact pair index selection ranks are stale")
        return self


class CompetitorProfileV11QuestionPair(CompetitorProfileV11BaseModel):
    candidate_snapshot: VersionSkuAnalysisSnapshot
    pair_analysis: PairAnalysisSnapshot
    question_result: PairBusinessQuestionResult

    @model_validator(mode="after")
    def validate_pair(self) -> "CompetitorProfileV11QuestionPair":
        if (
            self.candidate_snapshot.identity_market.sku_code
            != self.pair_analysis.candidate_sku_code
            or self.candidate_snapshot.snapshot_ref
            != self.pair_analysis.candidate_snapshot_ref
        ):
            raise ValueError("question pair must resolve its saved candidate snapshot")
        return self


class CompetitorProfileV11QuestionDTO(CompetitorProfileV11BaseModel):
    """All saved pair results, including unknowns, for one frozen question."""

    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    question_code: QuestionCode
    profile_version: ProfileVersionAnalysisContext
    generation_receipt: ProfileGenerationReceipt
    target_snapshot: VersionSkuAnalysisSnapshot
    sku_summary: SkuCompetitionAnalysisSummary
    priority_selections: list[PriorityCompetitorSelection]
    pairs: list[CompetitorProfileV11QuestionPair]
    fact_index: dict[str, FactIndexEntry]
    evidence_index: dict[str, EvidenceRef]
    profile_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_question(self) -> "CompetitorProfileV11QuestionDTO":
        codes = [row.pair_analysis.candidate_sku_code for row in self.pairs]
        if codes != sorted(set(codes)):
            raise ValueError("question pairs must be sorted and unique")
        if any(row.question_result.question_code != self.question_code for row in self.pairs):
            raise ValueError("question projection contains a different question")
        return self


class CompetitorProfileV11ReadResult(CompetitorProfileV11BaseModel):
    """One explicit formal/preview read with exactly one projection populated."""

    status: Literal["available", "profile_unavailable"]
    read_mode: Literal["full", "compact", "question_specific"]
    preview: bool = False
    competitor_profile_version_id: str | None = None
    full: CompetitorProfileAnalysisDTO | None = None
    compact: CompetitorProfileV11CompactDTO | None = None
    question: CompetitorProfileV11QuestionDTO | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "CompetitorProfileV11ReadResult":
        payloads = [self.full, self.compact, self.question]
        populated = sum(payload is not None for payload in payloads)
        if self.status == "profile_unavailable":
            if self.competitor_profile_version_id is not None or populated:
                raise ValueError("unavailable reads cannot expose partial profile data")
            return self
        if self.competitor_profile_version_id is None or populated != 1:
            raise ValueError("available reads require one version and one projection")
        expected = {
            "full": self.full,
            "compact": self.compact,
            "question_specific": self.question,
        }[self.read_mode]
        if expected is None:
            raise ValueError("read mode and populated projection must match")
        version_id = expected.profile_version.competitor_profile_version_id
        if version_id != self.competitor_profile_version_id:
            raise ValueError("read projection must lock the returned profile version")
        return self


__all__ = [
    "CompetitorProfileV11CompactDTO",
    "CompetitorProfileV11QuestionDTO",
    "CompetitorProfileV11QuestionPair",
    "CompetitorProfileV11ReadResult",
]
