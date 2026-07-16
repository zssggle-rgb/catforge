"""V1.1 scope, relation, question, and review gate semantics.

The legacy pipeline used one candidate status as a global stop switch.  This
module keeps the four V1.1 axes independent:

* scope decides only whether a pair is inside the legal analysis universe;
* dimension availability is copied from the calculated G33 result;
* relation/question strength is evaluated at the smallest relevant scope; and
* review is an overlay and never changes scope membership by itself.

No persistence, ranking, selection, materialization, LLM, or network behavior
belongs here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from pydantic import Field, StrictBool, model_validator

from app.services.core3_real_data.analyst.competitor_profile_pair_feature_schemas import (
    PairFeatureRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_price_volume_pressure_schemas import (
    PriceVolumePressureAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_purchase_pool_schemas import (
    PurchasePoolSemanticPairAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation import (
    CompetitorRelationEvaluator,
)
from app.services.core3_real_data.analyst.competitor_profile_relation_evaluation_schemas import (
    CompetitorRelationConfig,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceRef,
    RelationAssessment as LegacyRelationAssessment,
)
from app.services.core3_real_data.analyst.competitor_profile_value_substitution_schemas import (
    ValueSubstitutionEvidencePair,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisAssembly,
    pair_analysis_assembly_expected_hash,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    ALL_QUESTION_CODES,
    ALL_RELATION_CODES,
    HARD_EXCLUSION_CODES,
    QUESTION_ALTERNATIVE_EVIDENCE_GROUPS,
    QUESTION_REQUIRED_DIMENSIONS,
    RELATION_REQUIRED_DIMENSIONS,
    CompetitorProfileV11BaseModel,
    ConclusionDirection,
    ConclusionMetric,
    ConclusionStrength,
    DimensionAvailability,
    DimensionCode,
    MachineReadableConclusion,
    PairBusinessQuestionResult,
    PairScopeStatus,
    QuestionAlternativeEvidenceGroup,
    RelationAssessment,
    RelationStatusV11,
    ReviewItem,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMPETITOR_PROFILE_V1_1_SCOPE_METHOD_VERSION = "candidate_scope_classifier_v1_1"
COMPETITOR_PROFILE_V1_1_SCOPE_CONFIG_VERSION = "five_hard_scope_exclusions_v1"
COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION = "pair_gate_evaluator_v1_1"
COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION = (
    "scope_dimension_strength_review_four_axis_v1"
)
COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION = (
    "v1_1_relation_evidence_calculator_v1"
)

ALL_GATE_DIMENSION_CODES = tuple(
    sorted(
        {
            *(
                code
                for required in RELATION_REQUIRED_DIMENSIONS.values()
                for code in required
            ),
            *(
                code
                for required in QUESTION_REQUIRED_DIMENSIONS.values()
                for code in required
            ),
            *(
                code
                for groups in QUESTION_ALTERNATIVE_EVIDENCE_GROUPS.values()
                for required in groups.values()
                for code in required
            ),
            "claim_comparison",
            "parameter_comparison",
            "target_group_overlap",
            "user_realization_comparison",
        }
    )
)

_STRENGTH_RANK = {
    ConclusionStrength.UNKNOWN.value: 0,
    ConclusionStrength.REFERENCE.value: 1,
    ConclusionStrength.DIRECTIONAL.value: 2,
    ConclusionStrength.SUPPORTED.value: 3,
    ConclusionStrength.STRONG.value: 4,
}
_SCOPE_REVIEW_KEYWORDS = ("authority", "lineage", "taxonomy")
_LEGACY_CANDIDATE_CONTROL_GATE = "candidate_relation_evaluation_eligibility"


class PairGateInputError(RuntimeError):
    """Raised when the G34 input does not form one closed pair chain."""


class CandidateScopeAssessment(CompetitorProfileV11BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str | None = None
    target_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_ref: str | None = None
    scope_status: PairScopeStatus
    exclusion_reason_code: str | None = None
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    method_version: Literal["candidate_scope_classifier_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCOPE_METHOD_VERSION
    )
    config_version: Literal["five_hard_scope_exclusions_v1"] = (
        COMPETITOR_PROFILE_V1_1_SCOPE_CONFIG_VERSION
    )
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope(self) -> "CandidateScopeAssessment":
        if self.scope_status == PairScopeStatus.EXCLUDED.value:
            if self.exclusion_reason_code not in HARD_EXCLUSION_CODES:
                raise ValueError(
                    "excluded scope requires one frozen hard-exclusion code"
                )
            if self.review_required or self.review_items:
                raise ValueError("hard scope exclusions do not carry a review overlay")
        elif self.exclusion_reason_code is not None:
            raise ValueError("analyzable scope cannot carry an exclusion reason")
        if self.scope_status == PairScopeStatus.ANALYZABLE.value and (
            not self.candidate_sku_code or not self.candidate_snapshot_ref
        ):
            raise ValueError("analyzable scope requires a decoded candidate snapshot")
        if self.review_required != bool(self.review_items):
            raise ValueError("scope review flag must match concrete review items")
        return self


class DimensionGateState(CompetitorProfileV11BaseModel):
    dimension_code: DimensionCode
    availability: DimensionAvailability
    conclusion_strength: ConclusionStrength
    conclusion_direction: ConclusionDirection
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_state(self) -> "DimensionGateState":
        unavailable = self.availability in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
        if unavailable != (
            self.conclusion_strength == ConclusionStrength.UNKNOWN.value
        ):
            raise ValueError(
                "unknown/conflict availability must align with unknown strength"
            )
        if unavailable != (
            self.conclusion_direction == ConclusionDirection.UNKNOWN.value
        ):
            raise ValueError(
                "unknown/conflict availability must align with unknown direction"
            )
        if self.review_required != bool(self.review_items):
            raise ValueError("dimension review flag must match concrete review items")
        if self.availability == DimensionAvailability.CONFLICT.value and not (
            self.review_required
        ):
            raise ValueError("conflicting dimensions require a local review overlay")
        if self.limitations != sorted(set(self.limitations)):
            raise ValueError("dimension limitations must be sorted and unique")
        _assert_evidence_order(self.evidence_refs)
        return self


class PairGateEvaluation(CompetitorProfileV11BaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    competitor_profile_version_id: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str | None = None
    scope: CandidateScopeAssessment
    dimension_states: list[DimensionGateState] = Field(default_factory=list)
    relation_assessments: list[RelationAssessment] = Field(default_factory=list)
    business_questions: list[PairBusinessQuestionResult] = Field(default_factory=list)
    answerable_question_codes: list[str] = Field(default_factory=list)
    review_required: StrictBool = False
    review_items: list[ReviewItem] = Field(default_factory=list)
    relation_source_hashes: dict[str, str] = Field(default_factory=dict)
    method_version: Literal["pair_gate_evaluator_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION
    )
    config_version: Literal["scope_dimension_strength_review_four_axis_v1"] = (
        COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION
    )
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evaluation(self) -> "PairGateEvaluation":
        if (
            self.target_sku_code != self.scope.target_sku_code
            or self.candidate_sku_code != self.scope.candidate_sku_code
        ):
            raise ValueError("gate identity must match its scope assessment")
        if (
            self.project_id != self.scope.project_id
            or self.category_code != self.scope.category_code
            or self.competitor_profile_version_id
            != self.scope.competitor_profile_version_id
            or self.release_scope_key != self.scope.release_scope_key
        ):
            raise ValueError("gate authority scope must match its scope assessment")
        if self.scope.scope_status == PairScopeStatus.EXCLUDED.value:
            if (
                any(
                    (
                        self.dimension_states,
                        self.relation_assessments,
                        self.business_questions,
                        self.answerable_question_codes,
                        self.relation_source_hashes,
                        self.review_items,
                    )
                )
                or self.review_required
            ):
                raise ValueError("hard-excluded pairs cannot carry analytical gates")
            return self
        dimension_codes = [str(row.dimension_code) for row in self.dimension_states]
        if tuple(dimension_codes) != ALL_GATE_DIMENSION_CODES:
            raise ValueError("analyzable pairs require every frozen dimension state")
        relation_codes = [str(row.relation_code) for row in self.relation_assessments]
        if tuple(relation_codes) != ALL_RELATION_CODES:
            raise ValueError("analyzable pairs require all seven relation gates")
        question_codes = [str(row.question_code) for row in self.business_questions]
        if tuple(question_codes) != ALL_QUESTION_CODES:
            raise ValueError("analyzable pairs require all eight question gates")
        expected_answerable = [
            str(row.question_code) for row in self.business_questions if row.answerable
        ]
        if self.answerable_question_codes != expected_answerable:
            raise ValueError("answerable question index must match question results")
        if set(self.relation_source_hashes) != set(ALL_RELATION_CODES):
            raise ValueError("relation source hashes must cover all seven relations")
        if self.review_required != bool(self.review_items):
            raise ValueError("pair review flag must match concrete review items")
        return self


class CandidateScopeClassifier:
    """Classify legal pair scope without using evidence completeness as a gate."""

    def classify(
        self,
        *,
        target_snapshot: VersionSkuAnalysisSnapshot,
        candidate_snapshot: VersionSkuAnalysisSnapshot | None,
        authoritative_manifest_sku_codes: Sequence[str],
        candidate_identity_token: str | None = None,
    ) -> CandidateScopeAssessment:
        manifest = sorted(set(authoritative_manifest_sku_codes))
        decoded_candidate_code = (
            candidate_snapshot.identity_market.sku_code
            if candidate_snapshot is not None
            else None
        )
        candidate_code = (
            decoded_candidate_code
            if candidate_identity_token is None
            else candidate_identity_token.strip()
        )
        exclusion_reason = _hard_exclusion_reason(
            target_snapshot=target_snapshot,
            candidate_snapshot=candidate_snapshot,
            candidate_code=candidate_code,
            decoded_candidate_code=decoded_candidate_code,
            manifest=manifest,
        )
        scope_status = (
            PairScopeStatus.EXCLUDED.value
            if exclusion_reason is not None
            else PairScopeStatus.ANALYZABLE.value
        )
        review_items = (
            []
            if exclusion_reason is not None or candidate_snapshot is None
            else _scope_review_items(target_snapshot, candidate_snapshot)
        )
        input_payload = {
            "target_snapshot_hash": target_snapshot.result_hash,
            "candidate_snapshot_hash": (
                candidate_snapshot.result_hash if candidate_snapshot else None
            ),
            "candidate_identity_token": candidate_identity_token,
            "authoritative_manifest_sku_codes": manifest,
            "method_version": COMPETITOR_PROFILE_V1_1_SCOPE_METHOD_VERSION,
            "config_version": COMPETITOR_PROFILE_V1_1_SCOPE_CONFIG_VERSION,
        }
        input_fingerprint = stable_hash(
            input_payload,
            version="competitor_profile_v1_1_scope_input_v1",
        )
        result_payload = _scope_result_payload(
            project_id=target_snapshot.project_id,
            category_code=target_snapshot.category_code,
            competitor_profile_version_id=(
                target_snapshot.competitor_profile_version_id
            ),
            release_scope_key=target_snapshot.release_scope_key,
            target_sku_code=target_snapshot.identity_market.sku_code,
            candidate_sku_code=candidate_code,
            target_snapshot_ref=target_snapshot.snapshot_ref,
            candidate_snapshot_ref=(
                candidate_snapshot.snapshot_ref if candidate_snapshot else None
            ),
            scope_status=scope_status,
            exclusion_reason_code=exclusion_reason,
            review_items=review_items,
            input_fingerprint=input_fingerprint,
        )
        return CandidateScopeAssessment(
            project_id=target_snapshot.project_id,
            category_code=target_snapshot.category_code,
            competitor_profile_version_id=(
                target_snapshot.competitor_profile_version_id
            ),
            release_scope_key=target_snapshot.release_scope_key,
            target_sku_code=target_snapshot.identity_market.sku_code,
            candidate_sku_code=candidate_code,
            target_snapshot_ref=target_snapshot.snapshot_ref,
            candidate_snapshot_ref=(
                candidate_snapshot.snapshot_ref if candidate_snapshot else None
            ),
            scope_status=scope_status,
            exclusion_reason_code=exclusion_reason,
            review_required=bool(review_items),
            review_items=review_items,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_v1_1_scope_result_v1",
            ),
        )


# Compatibility name for callers migrating from the legacy classifier.  The
# V1 module remains untouched; this alias exists only in the V1.1 module.
CandidateEligibilityClassifier = CandidateScopeClassifier


class V11RelationEvidenceCalculator:
    """Calculate mature relation facts without replaying legacy admission controls.

    V1 stopped relation calculation when a candidate failed its global admission
    switch.  V1.1 owns candidate scope separately, so an analyzable pair must run
    the mature seven-relation calculation regardless of those two legacy control
    fields.  All product, semantic, value, and market facts remain unchanged.
    """

    method_version = COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION

    def calculate(
        self,
        *,
        pair_feature: PairFeatureRecord,
        purchase_pool: PurchasePoolSemanticPairAssessment,
        value_substitution: ValueSubstitutionEvidencePair,
        price_volume_pressure: PriceVolumePressureAssessment,
        config: CompetitorRelationConfig,
    ) -> list[LegacyRelationAssessment]:
        _assert_relation_calculation_inputs(
            pair_feature=pair_feature,
            purchase_pool=purchase_pool,
            value_substitution=value_substitution,
            price_volume_pressure=price_volume_pressure,
            config=config,
        )
        analyzable_pair = pair_feature.model_copy(
            update={
                "candidate_status": "recalled_only",
                "relation_evaluation_member": True,
            }
        )
        legacy_pair_result = CompetitorRelationEvaluator()._evaluate_pair(  # noqa: SLF001
            analyzable_pair,
            purchase_pool,
            value_substitution,
            price_volume_pressure,
            config,
        )
        return legacy_pair_result.relation_assessments


class PairGateEvaluator:
    """Apply four-axis V1.1 gates to G33 facts and legacy relation gate facts."""

    def evaluate(
        self,
        *,
        scope: CandidateScopeAssessment,
        assembly: PairAnalysisAssembly | None = None,
        legacy_relation_assessments: Sequence[LegacyRelationAssessment] = (),
        project_id: str | None = None,
        category_code: Literal["TV", "AC"] | None = None,
        competitor_profile_version_id: str | None = None,
        release_scope_key: str | None = None,
    ) -> PairGateEvaluation:
        _assert_scope_result_hash(scope)
        if scope.scope_status == PairScopeStatus.EXCLUDED.value:
            if assembly is not None or legacy_relation_assessments:
                raise PairGateInputError(
                    "hard-excluded scope cannot carry calculated pair results"
                )
            return _excluded_gate_result(
                scope=scope,
                project_id=project_id,
                category_code=category_code,
                competitor_profile_version_id=competitor_profile_version_id,
                release_scope_key=release_scope_key,
            )
        if assembly is None:
            raise PairGateInputError("analyzable scope requires one G33 assembly")
        _assert_scope_assembly(scope, assembly)
        legacy_by_code = _legacy_relation_index(legacy_relation_assessments)
        states = _dimension_states(assembly)
        states_by_code = {str(row.dimension_code): row for row in states}
        relations = [
            _relation_result(legacy_by_code[code], states_by_code)
            for code in ALL_RELATION_CODES
        ]
        questions = _question_results(states_by_code)
        review_items = _merge_review_items(
            scope.review_items,
            *(row.review_items for row in states),
            *(row.review_items for row in relations),
        )
        input_payload = {
            "scope_result_hash": scope.result_hash,
            "assembly_result_hash": assembly.result_hash,
            "relation_source_hashes": {
                code: legacy_by_code[code].result_hash for code in ALL_RELATION_CODES
            },
            "relation_calculator_method_version": (
                COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION
            ),
            "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
            "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
        }
        input_fingerprint = stable_hash(
            input_payload,
            version="competitor_profile_v1_1_gate_input_v1",
        )
        answerable = [str(row.question_code) for row in questions if row.answerable]
        result_payload = {
            "input_fingerprint": input_fingerprint,
            "dimension_hashes": {
                str(row.dimension_code): row.source_result_hash for row in states
            },
            "relation_hashes": {
                str(row.relation_code): row.result_hash for row in relations
            },
            "question_hashes": {
                str(row.question_code): row.result_hash for row in questions
            },
            "review_items": [row.model_dump(mode="json") for row in review_items],
        }
        return PairGateEvaluation(
            project_id=assembly.project_id,
            category_code=assembly.category_code,
            competitor_profile_version_id=assembly.competitor_profile_version_id,
            release_scope_key=assembly.release_scope_key,
            target_sku_code=assembly.target_sku_code,
            candidate_sku_code=assembly.candidate_sku_code,
            scope=scope,
            dimension_states=states,
            relation_assessments=relations,
            business_questions=questions,
            answerable_question_codes=answerable,
            review_required=bool(review_items),
            review_items=review_items,
            relation_source_hashes={
                code: legacy_by_code[code].result_hash for code in ALL_RELATION_CODES
            },
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_v1_1_gate_result_v1",
            ),
        )


def _hard_exclusion_reason(
    *,
    target_snapshot: VersionSkuAnalysisSnapshot,
    candidate_snapshot: VersionSkuAnalysisSnapshot | None,
    candidate_code: str | None,
    decoded_candidate_code: str | None,
    manifest: Sequence[str],
) -> str | None:
    if (
        candidate_snapshot is None
        or not candidate_code
        or not decoded_candidate_code
        or candidate_code != decoded_candidate_code
    ):
        return "identity_decode_failed"
    if candidate_code == target_snapshot.identity_market.sku_code:
        return "self_pair"
    if candidate_snapshot.project_id != target_snapshot.project_id:
        return "project_mismatch"
    if (
        candidate_snapshot.category_code != target_snapshot.category_code
        or candidate_snapshot.identity_market.product_category
        != target_snapshot.identity_market.product_category
    ):
        return "category_mismatch"
    if candidate_code not in manifest:
        return "candidate_outside_manifest"
    return None


def _assert_relation_calculation_inputs(
    *,
    pair_feature: PairFeatureRecord,
    purchase_pool: PurchasePoolSemanticPairAssessment,
    value_substitution: ValueSubstitutionEvidencePair,
    price_volume_pressure: PriceVolumePressureAssessment,
    config: CompetitorRelationConfig,
) -> None:
    expected_target = pair_feature.target
    expected_candidate = pair_feature.candidate
    if any(
        row.target != expected_target or row.candidate != expected_candidate
        for row in (
            purchase_pool,
            value_substitution,
            price_volume_pressure,
        )
    ):
        raise PairGateInputError(
            "pair, pool, value, and pressure identities must match"
        )
    if config.product_category != pair_feature.target.product_category:
        raise PairGateInputError("relation config category must match pair facts")
    if purchase_pool.pair_feature_result_hash != pair_feature.result_hash:
        raise PairGateInputError("purchase-pool pair hash chain mismatch")
    if (
        value_substitution.pair_feature_result_hash != pair_feature.result_hash
        or value_substitution.purchase_pool_result_hash != purchase_pool.result_hash
    ):
        raise PairGateInputError("value substitution pair hash chain mismatch")
    if (
        price_volume_pressure.pair_feature_result_hash != pair_feature.result_hash
        or price_volume_pressure.purchase_pool_result_hash != purchase_pool.result_hash
        or price_volume_pressure.value_substitution_result_hash
        != value_substitution.result_hash
    ):
        raise PairGateInputError("price-volume pair hash chain mismatch")


def _scope_review_items(
    target: VersionSkuAnalysisSnapshot,
    candidate: VersionSkuAnalysisSnapshot,
) -> list[ReviewItem]:
    rows: list[ReviewItem] = []
    if target.competitor_profile_version_id != candidate.competitor_profile_version_id:
        rows.append(
            ReviewItem(
                review_code="profile_version_lineage_mismatch",
                reason_cn="候选与本品快照版本不一致，但产品身份有效，保留分析并复核来源。",
                evidence_refs=_merge_evidence_refs(
                    target.evidence_refs, candidate.evidence_refs
                ),
            )
        )
    if target.release_scope_key != candidate.release_scope_key:
        rows.append(
            ReviewItem(
                review_code="release_scope_lineage_mismatch",
                reason_cn="候选与本品快照发布范围不一致，但产品身份有效，保留分析并复核来源。",
                evidence_refs=_merge_evidence_refs(
                    target.evidence_refs, candidate.evidence_refs
                ),
            )
        )
    for side, snapshot in (("candidate", candidate), ("target", target)):
        for limitation in sorted(set(snapshot.limitations)):
            if not any(
                keyword in limitation.lower() for keyword in _SCOPE_REVIEW_KEYWORDS
            ):
                continue
            rows.append(
                ReviewItem(
                    review_code=f"{side}_scope_{_slug(limitation)}",
                    reason_cn=(
                        f"{side} 快照存在 {limitation}，保留候选并在相关维度复核。"
                    ),
                    evidence_refs=snapshot.evidence_refs,
                )
            )
    return _merge_review_items(rows)


def _excluded_gate_result(
    *,
    scope: CandidateScopeAssessment,
    project_id: str | None,
    category_code: Literal["TV", "AC"] | None,
    competitor_profile_version_id: str | None,
    release_scope_key: str | None,
) -> PairGateEvaluation:
    required = {
        "project_id": project_id,
        "category_code": category_code,
        "competitor_profile_version_id": competitor_profile_version_id,
        "release_scope_key": release_scope_key,
    }
    missing = sorted(key for key, value in required.items() if not value)
    if missing:
        raise PairGateInputError(
            f"excluded scope requires explicit audit identity: {', '.join(missing)}"
        )
    input_fingerprint = stable_hash(
        {
            "scope_result_hash": scope.result_hash,
            "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
            "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
        },
        version="competitor_profile_v1_1_excluded_gate_input_v1",
    )
    return PairGateEvaluation(
        project_id=str(project_id),
        category_code=category_code,
        competitor_profile_version_id=str(competitor_profile_version_id),
        release_scope_key=str(release_scope_key),
        target_sku_code=scope.target_sku_code,
        candidate_sku_code=scope.candidate_sku_code,
        scope=scope,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            {
                "input_fingerprint": input_fingerprint,
                "scope_result_hash": scope.result_hash,
            },
            version="competitor_profile_v1_1_excluded_gate_result_v1",
        ),
    )


def _assert_scope_assembly(
    scope: CandidateScopeAssessment,
    assembly: PairAnalysisAssembly,
) -> None:
    if (
        scope.target_sku_code != assembly.target_sku_code
        or scope.candidate_sku_code != assembly.candidate_sku_code
    ):
        raise PairGateInputError("scope and G33 assembly identities must match")
    if (
        scope.project_id != assembly.project_id
        or scope.category_code != assembly.category_code
        or scope.competitor_profile_version_id != assembly.competitor_profile_version_id
        or scope.release_scope_key != assembly.release_scope_key
        or scope.target_snapshot_ref != assembly.target_snapshot_ref
        or scope.candidate_snapshot_ref != assembly.candidate_snapshot_ref
    ):
        raise PairGateInputError("scope and G33 assembly authority chain must match")
    expected_hash = pair_analysis_assembly_expected_hash(assembly)
    if assembly.result_hash != expected_hash:
        raise PairGateInputError("G33 assembly result hash does not close")


def _scope_result_payload(
    *,
    project_id: str,
    category_code: str,
    competitor_profile_version_id: str,
    release_scope_key: str,
    target_sku_code: str,
    candidate_sku_code: str | None,
    target_snapshot_ref: str,
    candidate_snapshot_ref: str | None,
    scope_status: str,
    exclusion_reason_code: str | None,
    review_items: Sequence[ReviewItem],
    input_fingerprint: str,
) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "category_code": category_code,
        "competitor_profile_version_id": competitor_profile_version_id,
        "release_scope_key": release_scope_key,
        "target_sku_code": target_sku_code,
        "candidate_sku_code": candidate_sku_code,
        "target_snapshot_ref": target_snapshot_ref,
        "candidate_snapshot_ref": candidate_snapshot_ref,
        "scope_status": scope_status,
        "exclusion_reason_code": exclusion_reason_code,
        "review_items": [row.model_dump(mode="json") for row in review_items],
        "input_fingerprint": input_fingerprint,
    }


def _assert_scope_result_hash(scope: CandidateScopeAssessment) -> None:
    expected = stable_hash(
        _scope_result_payload(
            project_id=scope.project_id,
            category_code=_enum_value(scope.category_code),
            competitor_profile_version_id=scope.competitor_profile_version_id,
            release_scope_key=scope.release_scope_key,
            target_sku_code=scope.target_sku_code,
            candidate_sku_code=scope.candidate_sku_code,
            target_snapshot_ref=scope.target_snapshot_ref,
            candidate_snapshot_ref=scope.candidate_snapshot_ref,
            scope_status=_enum_value(scope.scope_status),
            exclusion_reason_code=scope.exclusion_reason_code,
            review_items=scope.review_items,
            input_fingerprint=scope.input_fingerprint,
        ),
        version="competitor_profile_v1_1_scope_result_v1",
    )
    if scope.result_hash != expected:
        raise PairGateInputError("candidate scope result hash does not close")


def _legacy_relation_index(
    rows: Sequence[LegacyRelationAssessment],
) -> dict[str, LegacyRelationAssessment]:
    result: dict[str, LegacyRelationAssessment] = {}
    for row in rows:
        code = _enum_value(row.relation_code)
        if code in result:
            raise PairGateInputError("legacy relation inputs must be unique")
        result[code] = row
    if (
        tuple(code for code in ALL_RELATION_CODES if code in result)
        != ALL_RELATION_CODES
    ):
        raise PairGateInputError(
            "legacy relation inputs must cover all seven relations"
        )
    if set(result) != set(ALL_RELATION_CODES):
        raise PairGateInputError("legacy relation inputs contain an unknown relation")
    return result


def _dimension_states(assembly: PairAnalysisAssembly) -> list[DimensionGateState]:
    raw: dict[str, DimensionGateState] = {}

    def add(
        code: str,
        availability: str,
        strength: str,
        direction: str,
        *,
        review_required: bool,
        review_items: Sequence[ReviewItem],
        evidence_refs: Sequence[EvidenceRef],
        limitations: Sequence[str],
        result_hash: str,
    ) -> None:
        raw[code] = DimensionGateState(
            dimension_code=code,
            availability=availability,
            conclusion_strength=strength,
            conclusion_direction=direction,
            review_required=review_required,
            review_items=_merge_review_items(review_items),
            evidence_refs=_merge_evidence_refs(evidence_refs),
            limitations=sorted(set(limitations)),
            source_result_hash=result_hash,
        )

    pool_refs = _merge_evidence_refs(
        *(row.evidence_refs for row in assembly.purchase_pool.gate_facts)
    )
    add(
        "purchase_pool",
        (
            DimensionAvailability.UNKNOWN.value
            if assembly.purchase_pool.level == "unknown"
            else DimensionAvailability.AVAILABLE.value
        ),
        _enum_value(assembly.purchase_pool.conclusion.strength),
        _enum_value(assembly.purchase_pool.conclusion.direction),
        review_required=False,
        review_items=(),
        evidence_refs=pool_refs,
        limitations=assembly.purchase_pool.conclusion.limitations,
        result_hash=assembly.purchase_pool.result_hash,
    )
    for field_name in (
        "battlefield_overlap",
        "claim_comparison",
        "parameter_comparison",
        "purchase_reason_comparison",
        "target_group_overlap",
        "user_realization_comparison",
        "user_task_overlap",
    ):
        value = getattr(assembly.dimensions, field_name)
        add(
            field_name,
            _enum_value(value.availability),
            _enum_value(value.conclusion_strength),
            _enum_value(value.conclusion.direction),
            review_required=value.review_required,
            review_items=value.review_items,
            evidence_refs=value.evidence_refs,
            limitations=value.limitations,
            result_hash=value.result_hash,
        )
    anchor = assembly.value_anchor_analysis
    add(
        "value_anchor",
        (
            DimensionAvailability.UNKNOWN.value
            if anchor.anchor_substitutability_score is None
            else DimensionAvailability.AVAILABLE.value
        ),
        _enum_value(anchor.conclusion_strength),
        _enum_value(anchor.conclusion.direction),
        review_required=anchor.review_required,
        review_items=anchor.review_items,
        evidence_refs=anchor.evidence_refs,
        limitations=anchor.limitations,
        result_hash=anchor.result_hash,
    )
    replacement = assembly.replacement_pressure_analysis
    add(
        "replacement_pressure",
        (
            DimensionAvailability.UNKNOWN.value
            if replacement.replacement_pressure_score is None
            else DimensionAvailability.AVAILABLE.value
        ),
        _enum_value(replacement.conclusion_strength),
        _enum_value(replacement.conclusion.direction),
        review_required=replacement.review_required,
        review_items=replacement.review_items,
        evidence_refs=replacement.evidence_refs,
        limitations=replacement.limitations,
        result_hash=replacement.result_hash,
    )
    market = assembly.market_validation
    add(
        "market_validation",
        (
            DimensionAvailability.UNKNOWN.value
            if market.market_validation_strength == ConclusionStrength.UNKNOWN.value
            else DimensionAvailability.AVAILABLE.value
        ),
        _enum_value(market.market_validation_strength),
        _enum_value(market.conclusion.direction),
        review_required=False,
        review_items=(),
        evidence_refs=market.evidence_refs,
        limitations=market.limitations,
        result_hash=market.result_hash,
    )
    if tuple(sorted(raw)) != ALL_GATE_DIMENSION_CODES:
        raise PairGateInputError("G33 assembly did not project every G34 dimension")
    return [raw[code] for code in ALL_GATE_DIMENSION_CODES]


def _relation_result(
    source: LegacyRelationAssessment,
    states: Mapping[str, DimensionGateState],
) -> RelationAssessment:
    code = _enum_value(source.relation_code)
    required = list(RELATION_REQUIRED_DIMENSIONS[code])
    required_states = [states[item] for item in required]
    missing = sorted(
        row.dimension_code
        for row in required_states
        if row.availability == DimensionAvailability.UNKNOWN.value
    )
    conflicts = sorted(
        row.dimension_code
        for row in required_states
        if row.availability == DimensionAvailability.CONFLICT.value
    )
    partial = any(
        row.availability == DimensionAvailability.PARTIAL.value
        for row in required_states
    )
    unavailable_count = len(missing) + len(conflicts)
    support = _legacy_relation_support(source)
    source_status = _enum_value(source.status)
    source_local_review = (
        "insufficient_independent_evidence_for_auto_use" in source.reason_codes
        or "relation_requires_manual_evidence_review" in source.limitations
    )
    limitations = sorted(
        {
            *source.limitations,
            *(item for row in required_states for item in row.limitations),
            *(
                ["legacy_candidate_control_gate_ignored"]
                if any(
                    row.gate_code == _LEGACY_CANDIDATE_CONTROL_GATE
                    for row in source.gate_results
                )
                else []
            ),
        }
    )
    if unavailable_count == len(required):
        status = RelationStatusV11.UNASSESSABLE.value
        strength = ConclusionStrength.UNKNOWN.value
        limitations.append("all_required_dimensions_unavailable")
    elif unavailable_count or partial:
        status = RelationStatusV11.LIMITED.value
        strength = (
            ConclusionStrength.DIRECTIONAL.value
            if support is not False
            else ConclusionStrength.REFERENCE.value
        )
        limitations.append("required_dimension_evidence_limited")
    elif source_status == "limited":
        status = RelationStatusV11.LIMITED.value
        strength = ConclusionStrength.DIRECTIONAL.value
        limitations.append("legacy_relation_directional_only")
    elif source_local_review:
        status = RelationStatusV11.LIMITED.value
        strength = ConclusionStrength.REFERENCE.value
        limitations.append("independent_relation_evidence_requires_review")
    elif support is True:
        status = RelationStatusV11.PASSED.value
        strength = _supported_strength(required_states)
    elif support is False:
        status = RelationStatusV11.FAILED.value
        strength = ConclusionStrength.SUPPORTED.value
    else:
        status = RelationStatusV11.LIMITED.value
        strength = ConclusionStrength.REFERENCE.value
        limitations.append("relation_gate_signal_incomplete")
    limitations = sorted(set(limitations))
    review_items = _merge_review_items(
        *(row.review_items for row in required_states),
        (
            [
                ReviewItem(
                    review_code=f"{code}_independent_evidence_review",
                    reason_cn="该关系的独立证据不足，保留参照结论并单独复核。",
                    evidence_refs=source.evidence_refs,
                )
            ]
            if source_local_review
            else []
        ),
    )
    evidence_refs = _merge_evidence_refs(
        source.evidence_refs,
        *(row.evidence_refs for row in required_states),
    )
    input_payload = {
        "relation_code": code,
        "source_result_hash": source.result_hash,
        "dimension_hashes": {
            row.dimension_code: row.source_result_hash for row in required_states
        },
        "method_version": COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION,
        "config_version": COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION,
    }
    input_fingerprint = stable_hash(
        input_payload,
        version="competitor_profile_v1_1_relation_gate_input_v1",
    )
    conclusion = _relation_conclusion(
        code=code,
        status=status,
        strength=strength,
        support=support,
        required_states=required_states,
        limitations=limitations,
    )
    payload = {
        "relation_code": code,
        "status": status,
        "required_dimensions": required,
        "missing_dimensions": missing,
        "conflict_dimensions": conflicts,
        "conclusion": conclusion.model_dump(mode="json"),
        "review_items": [row.model_dump(mode="json") for row in review_items],
        "evidence_refs": [row.model_dump(mode="json") for row in evidence_refs],
        "limitations": limitations,
        "input_fingerprint": input_fingerprint,
    }
    return RelationAssessment(
        relation_code=code,
        status=status,
        required_dimensions=required,
        missing_dimensions=missing,
        conclusion_strength=strength,
        conclusion=conclusion,
        review_required=bool(review_items),
        review_items=review_items,
        conflict_dimensions=conflicts,
        evidence_refs=evidence_refs,
        limitations=limitations,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_relation_gate_result_v1",
        ),
    )


def _legacy_relation_support(source: LegacyRelationAssessment) -> bool | None:
    status = _enum_value(source.status)
    gates = [
        row
        for row in source.gate_results
        if row.gate_code != _LEGACY_CANDIDATE_CONTROL_GATE
    ]
    if status == "failed":
        return (
            False if any(row.known and row.passed is False for row in gates) else None
        )
    if status in {"passed", "limited"}:
        return True
    if status == "unassessable":
        return None
    if any(row.known and row.passed is False for row in gates):
        return False
    if gates and all(row.known and row.passed is True for row in gates):
        return True
    return None


def _supported_strength(states: Sequence[DimensionGateState]) -> str:
    if states and all(
        row.conclusion_strength == ConclusionStrength.STRONG.value for row in states
    ):
        return ConclusionStrength.STRONG.value
    return ConclusionStrength.SUPPORTED.value


def _relation_conclusion(
    *,
    code: str,
    status: str,
    strength: str,
    support: bool | None,
    required_states: Sequence[DimensionGateState],
    limitations: Sequence[str],
) -> MachineReadableConclusion:
    if strength == ConclusionStrength.UNKNOWN.value:
        return MachineReadableConclusion(
            conclusion_code=f"{code}_unassessable",
            subject=code,
            direction=ConclusionDirection.UNKNOWN.value,
            strength=strength,
            limitations=sorted(set(limitations))
            or ["required_relation_dimensions_unavailable"],
            audit_summary_cn="该关系所需维度均不可用，仅保留缺失边界。",
        )
    direction = (
        ConclusionDirection.POSITIVE_PRESSURE.value
        if status in {RelationStatusV11.PASSED.value, RelationStatusV11.LIMITED.value}
        and support is not False
        else ConclusionDirection.NO_MATERIAL_EFFECT.value
    )
    return MachineReadableConclusion(
        conclusion_code=f"{code}_{status}",
        subject=code,
        direction=direction,
        metrics=[
            ConclusionMetric(
                metric_code="known_required_dimension_count",
                value=sum(
                    row.availability
                    in {
                        DimensionAvailability.AVAILABLE.value,
                        DimensionAvailability.PARTIAL.value,
                    }
                    for row in required_states
                ),
                unit="dimension",
            ),
            ConclusionMetric(
                metric_code="required_dimension_count",
                value=len(required_states),
                unit="dimension",
            ),
            ConclusionMetric(
                metric_code="source_gate_support",
                value=support,
            ),
        ],
        supporting_fact_refs=sorted(
            {row.source_result_hash for row in required_states}
        ),
        strength=strength,
        limitations=sorted(set(limitations)),
        audit_summary_cn=f"{code} 关系状态为 {status}，复核标记独立保存。",
    )


def _question_results(
    states: Mapping[str, DimensionGateState],
) -> list[PairBusinessQuestionResult]:
    result: dict[str, PairBusinessQuestionResult] = {}
    for code in ALL_QUESTION_CODES:
        if code == "key_competitor_selection":
            continue
        result[code] = _question_result(code, states)
    answerable_decisions = [row for row in result.values() if row.answerable]
    key_strength = (
        max(
            (str(row.conclusion_strength) for row in answerable_decisions),
            key=_STRENGTH_RANK.__getitem__,
        )
        if answerable_decisions
        else ConclusionStrength.UNKNOWN.value
    )
    key_facts = sorted(
        {
            fact
            for row in answerable_decisions
            for fact in row.conclusion.supporting_fact_refs
        }
    )
    key_metrics = (
        [
            ConclusionMetric(
                metric_code="answerable_product_question_count",
                value=len(answerable_decisions),
                unit="question",
            )
        ]
        if answerable_decisions
        else []
    )
    key_conclusion = MachineReadableConclusion(
        conclusion_code=(
            "key_competitor_selection_answerable"
            if answerable_decisions
            else "key_competitor_selection_unknown"
        ),
        subject="key_competitor_selection",
        direction=(
            ConclusionDirection.POSITIVE_PRESSURE.value
            if answerable_decisions
            else ConclusionDirection.UNKNOWN.value
        ),
        metrics=key_metrics,
        supporting_fact_refs=key_facts,
        strength=key_strength,
        limitations=(
            [] if answerable_decisions else ["no_answerable_product_decision_question"]
        ),
        audit_summary_cn=(
            "至少一个产品决策问题可回答，候选继续进入 G35 重点选择。"
            if answerable_decisions
            else "当前没有可独立回答的产品决策问题，不生成重点选择资格。"
        ),
    )
    key_payload = {
        "question_code": "key_competitor_selection",
        "answerable": bool(answerable_decisions),
        "conclusion": key_conclusion.model_dump(mode="json"),
    }
    result["key_competitor_selection"] = PairBusinessQuestionResult(
        question_code="key_competitor_selection",
        answerable=bool(answerable_decisions),
        conclusion_strength=key_strength,
        conclusion=key_conclusion,
        required_dimensions=[],
        missing_dimensions=[],
        alternative_evidence_groups=[],
        result_hash=stable_hash(
            key_payload,
            version="competitor_profile_v1_1_question_gate_result_v1",
        ),
    )
    return [result[code] for code in ALL_QUESTION_CODES]


def _question_result(
    code: str,
    states: Mapping[str, DimensionGateState],
) -> PairBusinessQuestionResult:
    required = list(QUESTION_REQUIRED_DIMENSIONS[code])
    required_states = [states[item] for item in required]
    missing = sorted(
        row.dimension_code
        for row in required_states
        if row.availability
        in {
            DimensionAvailability.UNKNOWN.value,
            DimensionAvailability.CONFLICT.value,
        }
    )
    groups = []
    group_strengths: list[str] = []
    alternative_states: list[DimensionGateState] = []
    groups_ready = True
    for group_code, any_of in sorted(
        QUESTION_ALTERNATIVE_EVIDENCE_GROUPS.get(code, {}).items()
    ):
        satisfied = sorted(
            dimension_code
            for dimension_code in any_of
            if states[dimension_code].availability
            in {
                DimensionAvailability.AVAILABLE.value,
                DimensionAvailability.PARTIAL.value,
            }
        )
        groups.append(
            QuestionAlternativeEvidenceGroup(
                group_code=group_code,
                any_of_dimensions=list(any_of),
                satisfied_dimensions=satisfied,
            )
        )
        groups_ready = groups_ready and bool(satisfied)
        if satisfied:
            alternative_states.extend(states[item] for item in satisfied)
            group_strengths.append(
                max(
                    (str(states[item].conclusion_strength) for item in satisfied),
                    key=_STRENGTH_RANK.__getitem__,
                )
            )
    answerable = not missing and groups_ready
    considered = [str(row.conclusion_strength) for row in required_states]
    considered.extend(group_strengths)
    if answerable:
        strength = (
            min(considered, key=_STRENGTH_RANK.__getitem__)
            if considered
            else ConclusionStrength.REFERENCE.value
        )
        considered_states = [*required_states, *alternative_states]
        if any(row.review_required for row in considered_states):
            strength = min(
                strength,
                ConclusionStrength.DIRECTIONAL.value,
                key=_STRENGTH_RANK.__getitem__,
            )
        if strength == ConclusionStrength.UNKNOWN.value:
            strength = ConclusionStrength.REFERENCE.value
    else:
        strength = ConclusionStrength.UNKNOWN.value
    fact_refs = sorted(
        {
            row.source_result_hash
            for row in required_states
            if row.availability
            in {
                DimensionAvailability.AVAILABLE.value,
                DimensionAvailability.PARTIAL.value,
            }
        }
        | {
            states[dimension].source_result_hash
            for group in groups
            for dimension in group.satisfied_dimensions
        }
    )
    if answerable:
        conclusion = MachineReadableConclusion(
            conclusion_code=f"{code}_answerable",
            subject=code,
            direction=_question_direction([*required_states, *alternative_states]),
            metrics=[
                ConclusionMetric(
                    metric_code="available_required_dimension_count",
                    value=len(required) - len(missing),
                    unit="dimension",
                ),
                ConclusionMetric(
                    metric_code="required_dimension_count",
                    value=len(required),
                    unit="dimension",
                ),
            ],
            supporting_fact_refs=fact_refs,
            strength=strength,
            limitations=sorted(
                {
                    item
                    for row in [*required_states, *alternative_states]
                    for item in row.limitations
                }
            ),
            audit_summary_cn=f"{code} 已满足最低证据，按 {strength} 强度回答。",
        )
    else:
        missing_boundaries = sorted(
            {
                *(str(item) for item in missing),
                *(
                    f"alternative_group:{group.group_code}"
                    for group in groups
                    if not group.satisfied_dimensions
                ),
            }
        )
        conclusion = MachineReadableConclusion(
            conclusion_code=f"{code}_unknown",
            subject=code,
            direction=ConclusionDirection.UNKNOWN.value,
            strength=ConclusionStrength.UNKNOWN.value,
            limitations=[
                f"missing_minimum_evidence:{item}" for item in missing_boundaries
            ]
            or ["minimum_question_evidence_unavailable"],
            audit_summary_cn=f"{code} 的最低证据不足，仅返回缺失边界。",
        )
    payload = {
        "question_code": code,
        "answerable": answerable,
        "required_dimensions": required,
        "missing_dimensions": missing,
        "alternative_evidence_groups": [row.model_dump(mode="json") for row in groups],
        "conclusion": conclusion.model_dump(mode="json"),
    }
    return PairBusinessQuestionResult(
        question_code=code,
        answerable=answerable,
        conclusion_strength=strength,
        conclusion=conclusion,
        required_dimensions=required,
        missing_dimensions=missing,
        alternative_evidence_groups=groups,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_question_gate_result_v1",
        ),
    )


def _question_direction(states: Sequence[DimensionGateState]) -> str:
    known = {
        str(row.conclusion_direction)
        for row in states
        if row.availability
        in {
            DimensionAvailability.AVAILABLE.value,
            DimensionAvailability.PARTIAL.value,
        }
        and row.conclusion_direction != ConclusionDirection.UNKNOWN.value
    }
    if not known:
        return ConclusionDirection.NO_MATERIAL_EFFECT.value
    if len(known) == 1:
        return next(iter(known))
    return ConclusionDirection.DIFFERENT_ROUTE.value


def _merge_review_items(*groups: Sequence[ReviewItem]) -> list[ReviewItem]:
    result: dict[tuple[Any, ...], ReviewItem] = {}
    for row in (item for group in groups for item in group):
        key = (
            row.review_code,
            _enum_value(row.dimension_code) if row.dimension_code else "",
            row.reason_cn,
        )
        if key in result:
            current = result[key]
            result[key] = current.model_copy(
                update={
                    "evidence_refs": _merge_evidence_refs(
                        current.evidence_refs, row.evidence_refs
                    )
                }
            )
        else:
            result[key] = row.model_copy(
                update={"evidence_refs": _merge_evidence_refs(row.evidence_refs)}
            )
    return [result[key] for key in sorted(result)]


def _merge_evidence_refs(*groups: Sequence[EvidenceRef]) -> list[EvidenceRef]:
    result: dict[tuple[str, ...], EvidenceRef] = {}
    for row in (item for group in groups for item in group):
        key = (
            row.module_code,
            row.source_batch_id or "",
            row.record_type,
            row.record_id,
            row.result_hash,
        )
        current = result.get(key)
        if current is None:
            result[key] = row.model_copy(
                update={
                    "evidence_ids": sorted(set(row.evidence_ids)),
                    "source_file_ids": sorted(set(row.source_file_ids)),
                    "raw_row_ids": sorted(set(row.raw_row_ids)),
                }
            )
            continue
        if (
            current.profile_version != row.profile_version
            or current.rule_version != row.rule_version
            or current.taxonomy_version != row.taxonomy_version
        ):
            raise PairGateInputError("duplicate evidence reference metadata conflicts")
        confidence = (
            None
            if current.confidence is None or row.confidence is None
            else min(current.confidence, row.confidence)
        )
        result[key] = current.model_copy(
            update={
                "evidence_ids": sorted({*current.evidence_ids, *row.evidence_ids}),
                "source_file_ids": sorted(
                    {*current.source_file_ids, *row.source_file_ids}
                ),
                "raw_row_ids": sorted({*current.raw_row_ids, *row.raw_row_ids}),
                "confidence": confidence,
            }
        )
    return [result[key] for key in sorted(result)]


def _assert_evidence_order(rows: Sequence[EvidenceRef]) -> None:
    keys = [
        (
            row.module_code,
            row.source_batch_id or "",
            row.record_type,
            row.record_id,
            row.result_hash,
        )
        for row in rows
    ]
    if keys != sorted(set(keys)):
        raise ValueError("evidence refs must be sorted and unique")


def _slug(value: str) -> str:
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in value
    )
    return "_".join(part for part in normalized.split("_") if part) or "review"


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


__all__ = [
    "ALL_GATE_DIMENSION_CODES",
    "COMPETITOR_PROFILE_V1_1_GATE_CONFIG_VERSION",
    "COMPETITOR_PROFILE_V1_1_GATE_METHOD_VERSION",
    "COMPETITOR_PROFILE_V1_1_RELATION_CALCULATOR_METHOD_VERSION",
    "COMPETITOR_PROFILE_V1_1_SCOPE_CONFIG_VERSION",
    "COMPETITOR_PROFILE_V1_1_SCOPE_METHOD_VERSION",
    "CandidateEligibilityClassifier",
    "CandidateScopeAssessment",
    "CandidateScopeClassifier",
    "DimensionGateState",
    "PairGateEvaluation",
    "PairGateEvaluator",
    "PairGateInputError",
    "V11RelationEvidenceCalculator",
]
