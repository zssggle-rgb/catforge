"""Typed persistence contracts for versioned competitor profiles."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    COMPETITOR_PROFILE_METHOD_VERSION,
    COMPETITOR_PROFILE_RULE_VERSION,
    COMPETITOR_PROFILE_SCHEMA_VERSION,
    CandidateStatus,
    CompetitorPairDraft,
    CompetitorProfileBaseModel,
    ConfidenceLevel,
    FreshnessStatus,
    KeyCompetitorSelectionDraft,
    RelationAssessment,
    ReleaseQualityStatus,
    ReleaseStatus,
    ServingScope,
    SkuCompetitorDecisionProfileDraft,
)


class CompetitorProfileVersionDraftCreate(CompetitorProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    storage_batch_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    schema_version: str = COMPETITOR_PROFILE_SCHEMA_VERSION
    rule_version: str = COMPETITOR_PROFILE_RULE_VERSION
    method_version: str = COMPETITOR_PROFILE_METHOD_VERSION
    method_versions_json: dict[str, str] = Field(min_length=1)
    serving_scope: ServingScope
    release_status: Literal["draft"] = "draft"
    release_quality_status: ReleaseQualityStatus = ReleaseQualityStatus.UNASSESSED
    is_current: Literal[False] = False
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    generated_by: str = Field(default="system", min_length=1)
    sku_count: int = Field(ge=0)
    ready_count: int = Field(default=0, ge=0)
    partial_count: int = Field(default=0, ge=0)
    blocked_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)
    pair_count: int = Field(default=0, ge=0)
    relation_count: int = Field(default=0, ge=0)
    selection_count: int = Field(default=0, ge=0)
    input_fingerprint: str = Field(min_length=1)
    candidate_universe_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(default="pending", min_length=1)
    review_required: bool = False
    review_status: str = Field(default="unassessed", min_length=1)
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_version(self) -> "CompetitorProfileVersionDraftCreate":
        if self.category_code != self.product_category:
            raise ValueError("version category and product category must match")
        if self.project_id != self.serving_scope.project_id:
            raise ValueError("version project must match serving scope")
        if self.category_code != self.serving_scope.category_code:
            raise ValueError("version category must match serving scope")
        if self.storage_batch_id != self.serving_scope.storage_batch_id:
            raise ValueError("version storage batch must match serving scope")
        if self.release_scope_key != self.serving_scope.release_scope_key:
            raise ValueError("version release scope key must match serving scope")
        counted = self.ready_count + self.partial_count + self.blocked_count + self.failed_count
        if counted > self.sku_count:
            raise ValueError("version status counts cannot exceed SKU count")
        if self.selection_count > self.sku_count * 3:
            raise ValueError("version selection count cannot exceed three per SKU")
        if self.relation_count > self.pair_count * 7:
            raise ValueError("version relation count cannot exceed seven per pair")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required versions cannot auto-pass")
        return self


class CompetitorProfileVersionRecord(CompetitorProfileBaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    storage_batch_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    rule_version: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    method_versions_json: dict[str, str]
    serving_scope: ServingScope
    release_status: ReleaseStatus
    release_quality_status: ReleaseQualityStatus
    is_current: bool
    freshness_status: FreshnessStatus
    generated_at: datetime
    generated_by: str = Field(min_length=1)
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None
    published_at: datetime | None = None
    published_by: str | None = None
    current_at: datetime | None = None
    current_by: str | None = None
    deprecated_at: datetime | None = None
    deprecated_by: str | None = None
    release_note_cn: str | None = None
    sku_count: int = Field(ge=0)
    ready_count: int = Field(ge=0)
    partial_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    pair_count: int = Field(ge=0)
    relation_count: int = Field(ge=0)
    selection_count: int = Field(ge=0)
    input_fingerprint: str = Field(min_length=1)
    candidate_universe_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(min_length=1)
    safe_error_summary: dict[str, Any] = Field(default_factory=dict)
    review_required: bool
    review_status: str = Field(min_length=1)
    review_reasons: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_record(self) -> "CompetitorProfileVersionRecord":
        if self.category_code != self.product_category:
            raise ValueError("version category and product category must match")
        if self.is_current and self.release_status != ReleaseStatus.PUBLISHED.value:
            raise ValueError("only published versions can be current")
        if self.release_status == ReleaseStatus.PUBLISHED.value and not self.published_by:
            raise ValueError("published versions require an explicit publisher")
        if self.is_current and not self.current_by:
            raise ValueError("current versions require an explicit actor")
        return self


class CompetitorProfileDraftScope(CompetitorProfileBaseModel):
    competitor_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    product_category: Literal["TV", "AC"]
    storage_batch_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    schema_version: str = COMPETITOR_PROFILE_SCHEMA_VERSION
    rule_version: str = COMPETITOR_PROFILE_RULE_VERSION
    method_version: str = COMPETITOR_PROFILE_METHOD_VERSION
    release_status: ReleaseStatus = ReleaseStatus.DRAFT
    is_current: bool = False
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    processing_status: str = Field(default="success", min_length=1)
    review_required: bool = False
    review_status: str = Field(default="auto_pass", min_length=1)
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_draft_scope(self) -> "CompetitorProfileDraftScope":
        if self.category_code != self.product_category:
            raise ValueError("draft category and product category must match")
        if self.is_current and self.release_status != ReleaseStatus.PUBLISHED.value:
            raise ValueError("only published analytical rows can be current")
        if self.review_required and self.review_status == "auto_pass":
            raise ValueError("review-required draft rows cannot auto-pass")
        return self


class SkuCompetitorProfileDraft(CompetitorProfileDraftScope):
    sku_competitor_profile_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    profile_payload: SkuCompetitorDecisionProfileDraft

    @model_validator(mode="after")
    def validate_profile_payload(self) -> "SkuCompetitorProfileDraft":
        if self.project_id != self.profile_payload.project_id:
            raise ValueError("profile payload project must match persisted scope")
        if self.category_code != self.profile_payload.category_code:
            raise ValueError("profile payload category must match persisted scope")
        if self.target_sku_code != self.profile_payload.target_sku_code:
            raise ValueError("profile payload target must match persisted scope")
        if self.input_fingerprint != self.profile_payload.input_fingerprint:
            raise ValueError("profile input fingerprint must match persisted scope")
        if self.result_hash != self.profile_payload.result_hash:
            raise ValueError("profile result hash must match persisted scope")
        return self


class SkuCompetitorPairDraft(CompetitorProfileDraftScope):
    sku_competitor_profile_pair_id: str | None = None
    sku_competitor_profile_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    candidate_status: CandidateStatus
    confidence_level: ConfidenceLevel
    selected: bool = False
    competitor_member: bool
    reference_member: bool
    pair_payload: CompetitorPairDraft

    @model_validator(mode="after")
    def validate_pair_payload(self) -> "SkuCompetitorPairDraft":
        pair = self.pair_payload
        if self.project_id != pair.project_id or self.category_code != pair.category_code:
            raise ValueError("pair payload scope must match persisted scope")
        if self.target_sku_code != pair.target_sku_code:
            raise ValueError("pair payload target must match persisted scope")
        if self.candidate_sku_code != pair.candidate.sku_code:
            raise ValueError("pair payload candidate must match persisted scope")
        for field_name in (
            "candidate_status",
            "confidence_level",
            "selected",
            "competitor_member",
            "reference_member",
        ):
            if getattr(self, field_name) != getattr(pair, field_name):
                raise ValueError(f"persisted pair {field_name} must match payload")
        if self.input_fingerprint != pair.input_fingerprint:
            raise ValueError("pair input fingerprint must match persisted scope")
        if self.result_hash != pair.result_hash:
            raise ValueError("pair result hash must match persisted scope")
        return self


class SkuCompetitorRelationDraft(CompetitorProfileDraftScope):
    sku_competitor_profile_relation_id: str | None = None
    sku_competitor_profile_pair_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    relation_code: str = Field(min_length=1)
    relation_payload: RelationAssessment

    @model_validator(mode="after")
    def validate_relation_payload(self) -> "SkuCompetitorRelationDraft":
        if self.relation_code != self.relation_payload.relation_code:
            raise ValueError("persisted relation code must match payload")
        if self.result_hash != self.relation_payload.result_hash:
            raise ValueError("relation result hash must match persisted scope")
        return self


class SkuCompetitorSelectionDraft(CompetitorProfileDraftScope):
    sku_competitor_profile_selection_id: str | None = None
    sku_competitor_profile_id: str | None = None
    sku_competitor_profile_pair_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    selection_rank: int = Field(ge=1, le=3)
    selection_payload: KeyCompetitorSelectionDraft

    @model_validator(mode="after")
    def validate_selection_payload(self) -> "SkuCompetitorSelectionDraft":
        payload = self.selection_payload
        if self.target_sku_code != payload.target_sku_code:
            raise ValueError("selection payload target must match persisted scope")
        if self.candidate_sku_code != payload.candidate_sku_code:
            raise ValueError("selection payload candidate must match persisted scope")
        if self.selection_rank != payload.selection_rank:
            raise ValueError("selection payload rank must match persisted scope")
        if self.result_hash != payload.result_hash:
            raise ValueError("selection result hash must match persisted scope")
        return self


class CompetitorProfilePersistenceBundle(CompetitorProfileBaseModel):
    profile: SkuCompetitorProfileDraft
    pairs: list[SkuCompetitorPairDraft]
    relations: list[SkuCompetitorRelationDraft]
    selections: list[SkuCompetitorSelectionDraft] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_bundle(self) -> "CompetitorProfilePersistenceBundle":
        validate_persistence_bundle_parts(
            profile=self.profile,
            pairs=self.pairs,
            relations=self.relations,
            selections=self.selections,
        )
        return self


class CompetitorProfileReadBundle(CompetitorProfileBaseModel):
    version: CompetitorProfileVersionRecord
    profile: SkuCompetitorProfileDraft
    pairs: list[SkuCompetitorPairDraft]
    relations: list[SkuCompetitorRelationDraft]
    selections: list[SkuCompetitorSelectionDraft]
    preview: bool = False

    @model_validator(mode="after")
    def validate_read_mode(self) -> "CompetitorProfileReadBundle":
        if not self.preview and (
            self.version.release_status != ReleaseStatus.PUBLISHED.value
            or not self.version.is_current
        ):
            raise ValueError("formal read bundles require current published versions")
        return self


class CompetitorProfileResultHashReceipt(CompetitorProfileBaseModel):
    profile_result_hash: str = Field(min_length=1)
    pair_hashes: tuple[tuple[str, str], ...]
    relation_hashes: tuple[tuple[str, str, str], ...]
    selection_hashes: tuple[tuple[str, str], ...]


def validate_persistence_bundle_parts(
    *,
    profile: SkuCompetitorProfileDraft,
    pairs: list[SkuCompetitorPairDraft],
    relations: list[SkuCompetitorRelationDraft],
    selections: list[SkuCompetitorSelectionDraft],
) -> None:
    """Validate cross-table invariants without rebuilding the typed object graph."""

    pair_by_code: dict[str, SkuCompetitorPairDraft] = {}
    nested_relations_by_candidate: dict[str, dict[str, RelationAssessment]] = {}
    for pair in pairs:
        _validate_child_scope(profile, pair)
        if pair.candidate_sku_code in pair_by_code:
            raise ValueError("persisted pair candidates must be unique")
        pair_by_code[pair.candidate_sku_code] = pair
        nested_relations_by_candidate[pair.candidate_sku_code] = {
            row.relation_code: row for row in pair.pair_payload.relation_assessments
        }
    relation_keys: set[tuple[str, str]] = set()
    relation_codes_by_candidate: dict[str, set[str]] = {}
    for relation in relations:
        _validate_child_scope(profile, relation)
        if relation.candidate_sku_code not in pair_by_code:
            raise ValueError("persisted relation requires a matching pair")
        key = (relation.candidate_sku_code, relation.relation_code)
        if key in relation_keys:
            raise ValueError("persisted relations must be unique per pair and code")
        relation_keys.add(key)
        relation_codes_by_candidate.setdefault(
            relation.candidate_sku_code,
            set(),
        ).add(relation.relation_code)
        nested = nested_relations_by_candidate[relation.candidate_sku_code]
        if relation.relation_payload != nested.get(relation.relation_code):
            raise ValueError("persisted relation must match the pair payload")
    for candidate_code, nested in nested_relations_by_candidate.items():
        if relation_codes_by_candidate.get(candidate_code, set()) != set(nested):
            raise ValueError("each persisted pair requires all seven relations")
    if len(selections) > 3:
        raise ValueError("persisted bundle can contain at most three selections")
    ranks: list[int] = []
    selected_codes: list[str] = []
    for selection in selections:
        _validate_child_scope(profile, selection)
        pair = pair_by_code.get(selection.candidate_sku_code)
        if pair is None or not pair.selected:
            raise ValueError("persisted selection requires a selected pair")
        ranks.append(selection.selection_rank)
        selected_codes.append(selection.candidate_sku_code)
    if ranks != list(range(1, len(ranks) + 1)):
        raise ValueError("persisted selection ranks must be contiguous and ordered")
    if len(selected_codes) != len(set(selected_codes)):
        raise ValueError("persisted selected candidates must be unique")
    pair_selected = {code for code, row in pair_by_code.items() if row.selected}
    if pair_selected != set(selected_codes):
        raise ValueError("persisted selected pair flags must match selection rows")


def _validate_child_scope(
    parent: CompetitorProfileDraftScope,
    child: CompetitorProfileDraftScope,
) -> None:
    for field_name in (
        "competitor_profile_version_id",
        "project_id",
        "category_code",
        "product_category",
        "storage_batch_id",
        "release_scope_key",
        "profile_version",
        "schema_version",
        "rule_version",
        "method_version",
        "release_status",
        "is_current",
    ):
        if getattr(parent, field_name) != getattr(child, field_name):
            raise ValueError(f"child {field_name} must match profile")
    if parent.target_sku_code != child.target_sku_code:
        raise ValueError("child target SKU must match profile")


__all__ = [
    "CompetitorProfileDraftScope",
    "CompetitorProfilePersistenceBundle",
    "CompetitorProfileReadBundle",
    "CompetitorProfileResultHashReceipt",
    "CompetitorProfileVersionDraftCreate",
    "CompetitorProfileVersionRecord",
    "SkuCompetitorPairDraft",
    "SkuCompetitorProfileDraft",
    "SkuCompetitorRelationDraft",
    "SkuCompetitorSelectionDraft",
    "validate_persistence_bundle_parts",
]
