"""Pure pre-relation classification for recalled competitor-profile candidates."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityAssessment,
    CandidateEligibilityConfig,
    CandidateEligibilityManifest,
    ProvisionalQuestionAssessment,
    ProvisionalQuestionReadiness,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallManifest,
    RecalledCandidate,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceFamily,
    EvidenceRef,
    QuestionCode,
    ReferencePurpose,
    RelationCode,
)
from app.services.core3_real_data.hash_utils import stable_hash


_MODULE_EVIDENCE_FAMILY = {
    "M03B": EvidenceFamily.CAPABILITY_EXPRESSION.value,
    "M04C": EvidenceFamily.CAPABILITY_EXPRESSION.value,
    "M05C": EvidenceFamily.USER_REALIZATION.value,
    "M09C": EvidenceFamily.TASK_VALUE_SCENE.value,
    "M10C": EvidenceFamily.AUDIENCE_NEED.value,
    "M11C": EvidenceFamily.TASK_VALUE_SCENE.value,
    "M11D": EvidenceFamily.TASK_VALUE_SCENE.value,
    "M12C": EvidenceFamily.USER_REALIZATION.value,
    "M12D": EvidenceFamily.PURCHASE_REASON.value,
}
_SEMANTIC_FAMILIES = frozenset(
    {
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.AUDIENCE_NEED.value,
        EvidenceFamily.USER_REALIZATION.value,
    }
)
_NON_AUDIENCE_SEMANTIC_FAMILIES = _SEMANTIC_FAMILIES - {
    EvidenceFamily.AUDIENCE_NEED.value
}
_SOURCE_RELATIONS = {
    "downtrade": (RelationCode.DOWNTRADE_DIVERSION.value,),
    "same_brand_ladder": (RelationCode.SAME_BRAND_LADDER.value,),
    "same_purchase_pool": (
        RelationCode.DIRECT_SUBSTITUTE.value,
        RelationCode.SAME_BUDGET_ALTERNATIVE.value,
    ),
    "same_value": (RelationCode.SAME_VALUE_SUBSTITUTE.value,),
    "scenario": (RelationCode.SCENARIO_SUBSTITUTE.value,),
    "uptrade": (RelationCode.UPTRADE_ALTERNATIVE.value,),
}
_QUESTION_REQUIRED_FAMILIES = {
    QuestionCode.CONFIGURATION_FOLLOW.value: (
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.USER_REALIZATION.value,
        EvidenceFamily.CAPABILITY_EXPRESSION.value,
    ),
    QuestionCode.KEY_COMPETITOR_SELECTION.value: tuple(
        sorted(item.value for item in EvidenceFamily)
    ),
    QuestionCode.PRICE_LADDER_DEFENSE.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
    QuestionCode.PRICE_VOLUME_PRESSURE.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
    QuestionCode.PURCHASE_CHOICE.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
    QuestionCode.SAME_BRAND_PORTFOLIO_ROLE.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
    QuestionCode.SCENARIO_SOLUTION.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.TASK_VALUE_SCENE.value,
        EvidenceFamily.AUDIENCE_NEED.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
    QuestionCode.VALUE_SUBSTITUTION.value: (
        EvidenceFamily.PURCHASE_REASON.value,
        EvidenceFamily.USER_REALIZATION.value,
    ),
}
_LINEAGE_STATUS_KEYS = {
    "evidence_lineage_status",
    "lineage_status",
    "source_lineage_status",
}
_CONFLICT_STATUSES = {"ambiguous", "conflict", "invalid", "mismatch"}
_REVIEW_STATUS_VALUES = {
    "blocked",
    "failed",
    "needs_review",
    "pending_review",
    "review_required",
}


class CandidateEligibilityError(RuntimeError):
    """Base error for an invalid eligibility input contract."""


class CandidateEligibilityScopeError(CandidateEligibilityError):
    pass


@dataclass(frozen=True)
class _MarketFacts:
    price: Decimal | None
    weekly_volume: Decimal | None
    screen_size: Decimal | None
    size_segment: str | None


@dataclass(frozen=True)
class _CandidateContext:
    records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]]
    target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]]
    evidence_families: frozenset[str]
    independent_lineage_keys: tuple[str, ...]
    market_known: bool
    product_form_compatible: bool | None
    relation_evaluation_member: bool


class CandidateEligibilityClassifier:
    """Separate relation-evaluation candidates from analytical references."""

    def classify(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        recall_manifest: CandidateRecallManifest,
        config: CandidateEligibilityConfig | None = None,
    ) -> CandidateEligibilityManifest:
        eligibility_config = config or CandidateEligibilityConfig()
        self._assert_scope(category_bundle, target_bundle, recall_manifest)
        record_index = _record_index(category_bundle)
        target_records = _records_for_sku(
            category_bundle, target_bundle.target_sku_code
        )

        assessments = [
            self._classify_candidate(
                recalled=recalled,
                category_bundle=category_bundle,
                target_bundle=target_bundle,
                recall_manifest=recall_manifest,
                target_records=target_records,
                record_index=record_index,
                config=eligibility_config,
            )
            for recalled in recall_manifest.candidates
        ]
        assessments.sort(key=lambda row: row.candidate.sku_code)
        limitations = sorted(
            {
                *recall_manifest.limitations,
                *target_bundle.limitations,
                *(["candidate_eligibility_manifest_empty"] if not assessments else []),
            }
        )
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "recall_result_hash": recall_manifest.result_hash,
                "config": eligibility_config.model_dump(mode="python"),
            },
            version="competitor_profile_candidate_eligibility_input_v1",
        )
        status_counts: dict[str, int] = defaultdict(int)
        for assessment in assessments:
            status_counts[assessment.candidate_status] += 1
        result_payload = {
            "input_fingerprint": input_fingerprint,
            "candidate_hashes": {
                row.candidate.sku_code: row.result_hash for row in assessments
            },
            "limitations": limitations,
        }
        return CandidateEligibilityManifest(
            project_id=recall_manifest.project_id,
            category_code=recall_manifest.category_code,
            product_category=recall_manifest.product_category,
            release_scope_key=recall_manifest.release_scope_key,
            target_sku_code=recall_manifest.target_sku_code,
            recall_result_hash=recall_manifest.result_hash,
            config=eligibility_config,
            candidate_count=len(assessments),
            relation_evaluation_candidate_count=sum(
                row.relation_evaluation_member for row in assessments
            ),
            reference_candidate_count=sum(row.reference_member for row in assessments),
            candidate_count_by_status=dict(sorted(status_counts.items())),
            candidates=assessments,
            limitations=limitations,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_candidate_eligibility_result_v1",
            ),
        )

    @staticmethod
    def _assert_scope(
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        recall_manifest: CandidateRecallManifest,
    ) -> None:
        if category_bundle.serving_scope != target_bundle.serving_scope:
            raise CandidateEligibilityScopeError(
                "target and category bundles must use the same serving scope"
            )
        scope = category_bundle.serving_scope
        expected = (
            scope.project_id,
            scope.category_code,
            scope.product_category,
            scope.release_scope_key,
            target_bundle.target_sku_code,
            category_bundle.input_fingerprint,
            target_bundle.input_fingerprint,
        )
        actual = (
            recall_manifest.project_id,
            recall_manifest.category_code,
            recall_manifest.product_category,
            recall_manifest.release_scope_key,
            recall_manifest.target_sku_code,
            recall_manifest.category_input_fingerprint,
            recall_manifest.target_input_fingerprint,
        )
        if actual != expected:
            raise CandidateEligibilityScopeError(
                "recall manifest conflicts with the exact input authority scope"
            )
        if target_bundle.analysis_state == "blocked":
            raise CandidateEligibilityScopeError(
                "blocked target input cannot enter candidate eligibility"
            )
        authoritative = set(category_bundle.authoritative_sku_codes)
        recalled_codes = {row.candidate.sku_code for row in recall_manifest.candidates}
        if not recalled_codes.issubset(authoritative - {target_bundle.target_sku_code}):
            raise CandidateEligibilityScopeError(
                "recall manifest contains a candidate outside the authoritative SKU manifest"
            )
        if recall_manifest.candidate_count != len(recalled_codes):
            raise CandidateEligibilityScopeError(
                "recall manifest does not conserve recalled candidates"
            )

    def _classify_candidate(
        self,
        *,
        recalled: RecalledCandidate,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        recall_manifest: CandidateRecallManifest,
        target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
        record_index: Mapping[tuple[str, str, str, str, str], UpstreamRecordSnapshot],
        config: CandidateEligibilityConfig,
    ) -> CandidateEligibilityAssessment:
        candidate_code = recalled.candidate.sku_code
        candidate_records = _records_for_sku(category_bundle, candidate_code)
        lineage_reasons, used_records = _validate_lineage(
            recalled,
            target_bundle.target_sku_code,
            record_index,
        )
        review_reasons = _review_reasons(used_records, config)
        families, lineage_keys = _evidence_families(recalled)
        target_market = _market_facts(target_records["M07"])
        candidate_market = _market_facts(candidate_records["M07"])
        market_known = _market_pair_known(target_market, candidate_market)
        form_compatible = _product_form_compatible(
            category_bundle.serving_scope.product_category,
            target_records,
            candidate_records,
            target_market,
            candidate_market,
            recall_manifest,
        )
        relation_member = _relation_evaluation_member(
            recalled,
            families,
            market_known=market_known,
            product_form_compatible=form_compatible,
        )
        context = _CandidateContext(
            records=candidate_records,
            target_records=target_records,
            evidence_families=frozenset(families),
            independent_lineage_keys=tuple(lineage_keys),
            market_known=market_known,
            product_form_compatible=form_compatible,
            relation_evaluation_member=relation_member,
        )

        reference_purposes = _reference_purposes(
            recalled,
            context,
            target_market,
            candidate_market,
            recall_manifest,
            config,
        )
        if lineage_reasons:
            candidate_status = "blocked"
            relation_member = False
            reference_purposes = []
            review_codes = lineage_reasons
            reason_codes = ["candidate_blocked_by_lineage_conflict"]
        elif review_reasons:
            candidate_status = "review_required"
            relation_member = False
            reference_purposes = []
            review_codes = review_reasons
            reason_codes = ["candidate_requires_source_review"]
        elif relation_member:
            candidate_status = "recalled_only"
            review_codes = []
            reason_codes = ["candidate_ready_for_formal_relation_evaluation"]
        elif reference_purposes:
            candidate_status = "reference_only"
            review_codes = []
            reason_codes = ["candidate_available_for_analysis_reference_only"]
        else:
            candidate_status = "recalled_only"
            review_codes = []
            reason_codes = [
                "candidate_recalled_but_not_qualified_for_relation_evaluation"
            ]

        blocking_code = None
        if candidate_status == "blocked":
            blocking_code = "candidate_lineage_blocked"
        elif candidate_status == "review_required":
            blocking_code = "candidate_source_review_required"
        question_readiness = _question_readiness(
            recalled,
            context,
            relation_member=relation_member,
            blocking_code=blocking_code,
        )
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_input_fingerprint": target_bundle.input_fingerprint,
                "recall_result_hash": recalled.result_hash,
                "config_version": config.config_version,
                "lineage_keys": lineage_keys,
            },
            version="competitor_profile_candidate_eligibility_pair_input_v1",
        )
        payload = {
            "candidate": recalled.candidate.model_dump(mode="python"),
            "candidate_status": candidate_status,
            "relation_evaluation_member": relation_member,
            "competitor_member": False,
            "reference_member": bool(reference_purposes),
            "reference_purposes": reference_purposes,
            "available_evidence_families": families,
            "independent_lineage_keys": lineage_keys,
            "question_hashes": [row.result_hash for row in question_readiness],
            "reason_codes": reason_codes,
            "unknown_reason_codes": recalled.unknown_reason_codes,
            "review_reason_codes": review_codes,
            "evidence_refs": [
                _ref_payload(row) for row in _dedupe_refs(recalled.evidence_refs)
            ],
            "recall_result_hash": recalled.result_hash,
            "input_fingerprint": input_fingerprint,
        }
        return CandidateEligibilityAssessment(
            candidate=recalled.candidate,
            candidate_status=candidate_status,
            relation_evaluation_member=relation_member,
            competitor_member=False,
            reference_member=bool(reference_purposes),
            reference_purposes=reference_purposes,
            available_evidence_families=families,
            independent_lineage_keys=lineage_keys,
            question_readiness=question_readiness,
            reason_codes=reason_codes,
            unknown_reason_codes=recalled.unknown_reason_codes,
            review_reason_codes=review_codes,
            evidence_refs=_dedupe_refs(recalled.evidence_refs),
            recall_result_hash=recalled.result_hash,
            input_fingerprint=input_fingerprint,
            result_hash=stable_hash(
                payload,
                version="competitor_profile_candidate_eligibility_pair_result_v1",
            ),
        )


def _record_index(
    bundle: CompetitorProfileCategoryInputBundle,
) -> dict[tuple[str, str, str, str, str], UpstreamRecordSnapshot]:
    result: dict[tuple[str, str, str, str, str], UpstreamRecordSnapshot] = {}
    for module in bundle.modules.values():
        for records in module.records_by_sku.values():
            for record in records:
                key = _record_key(record)
                if key in result and result[key] != record:
                    raise CandidateEligibilityScopeError(
                        "authoritative input contains conflicting source lineage"
                    )
                result[key] = record
    return result


def _records_for_sku(
    bundle: CompetitorProfileCategoryInputBundle,
    sku_code: str,
) -> dict[str, tuple[UpstreamRecordSnapshot, ...]]:
    return {
        module_code: tuple(module.records_by_sku.get(sku_code, []))
        for module_code, module in bundle.modules.items()
    }


def _validate_lineage(
    recalled: RecalledCandidate,
    target_sku_code: str,
    record_index: Mapping[tuple[str, str, str, str, str], UpstreamRecordSnapshot],
) -> tuple[list[str], list[UpstreamRecordSnapshot]]:
    reasons: set[str] = set()
    used: dict[tuple[str, str, str, str, str], UpstreamRecordSnapshot] = {}
    candidate_code = recalled.candidate.sku_code
    for fact in recalled.recall_facts:
        for side, expected_sku, refs in (
            ("target", target_sku_code, fact.target_evidence_refs),
            ("candidate", candidate_code, fact.candidate_evidence_refs),
        ):
            for ref in refs:
                key = _ref_key(ref)
                record = record_index.get(key)
                if record is None:
                    reasons.add(f"{side}_evidence_ref_not_in_locked_authority")
                    continue
                used[key] = record
                if record.sku_code != expected_sku:
                    reasons.add(f"{side}_evidence_ref_sku_mismatch")
                if _record_has_lineage_conflict(record):
                    reasons.add(f"{side}_{record.module_code.lower()}_lineage_conflict")
    expected_keys = {_ref_key(row) for row in recalled.evidence_refs}
    fact_keys = {
        _ref_key(ref)
        for fact in recalled.recall_facts
        for ref in (*fact.target_evidence_refs, *fact.candidate_evidence_refs)
    }
    if expected_keys != fact_keys:
        reasons.add("candidate_recall_evidence_set_conflict")
    return sorted(reasons), [used[key] for key in sorted(used)]


def _record_has_lineage_conflict(record: UpstreamRecordSnapshot) -> bool:
    for key, value in _walk_items(record.facts):
        normalized = _text(value)
        if key in _LINEAGE_STATUS_KEYS and normalized in _CONFLICT_STATUSES:
            return True
        if (
            key in {"quality_flags", "risk_flags"}
            and normalized
            and ("lineage_conflict" in normalized or "source_mismatch" in normalized)
        ):
            return True
    return False


def _review_reasons(
    records: Sequence[UpstreamRecordSnapshot],
    config: CandidateEligibilityConfig,
) -> list[str]:
    reasons: set[str] = set()
    bad_processing = set(config.review_processing_statuses)
    for record in records:
        for key, value in _walk_items(record.facts):
            normalized = _text(value)
            if key == "review_required" and value is True:
                reasons.add(f"source_{record.module_code.lower()}_review_required")
            elif key == "review_status" and normalized in _REVIEW_STATUS_VALUES:
                reasons.add(
                    f"source_{record.module_code.lower()}_review_status_{normalized}"
                )
            elif key == "processing_status" and normalized in bad_processing:
                reasons.add(
                    f"source_{record.module_code.lower()}_processing_status_{normalized}"
                )
    return sorted(reasons)


def _evidence_families(
    recalled: RecalledCandidate,
) -> tuple[list[str], list[str]]:
    families: set[str] = set()
    lineage_keys: set[str] = set()
    for fact in recalled.recall_facts:
        for ref in (*fact.target_evidence_refs, *fact.candidate_evidence_refs):
            family = _MODULE_EVIDENCE_FAMILY.get(ref.module_code)
            if not family:
                continue
            families.add(family)
            if ref.evidence_ids:
                lineage_keys.update(
                    f"evidence:{value}" for value in ref.evidence_ids
                )
            elif ref.raw_row_ids:
                lineage_keys.update(
                    f"raw-row:{value}" for value in ref.raw_row_ids
                )
            elif ref.source_file_ids:
                lineage_keys.update(
                    f"source-file:{value}" for value in ref.source_file_ids
                )
            else:
                lineage_keys.add(
                    f"derived:{ref.source_batch_id or ref.profile_version}:"
                    f"{ref.result_hash}"
                )
    return sorted(families), sorted(lineage_keys)


def _relation_evaluation_member(
    recalled: RecalledCandidate,
    families: Sequence[str],
    *,
    market_known: bool,
    product_form_compatible: bool | None,
) -> bool:
    sources = set(recalled.recall_sources)
    evidence = set(families)
    semantic = evidence & _SEMANTIC_FAMILIES
    grounded_value = bool(
        evidence
        & {
            EvidenceFamily.PURCHASE_REASON.value,
            EvidenceFamily.USER_REALIZATION.value,
        }
    )
    if "same_purchase_pool" in sources and semantic:
        return True
    if "same_brand_ladder" in sources and semantic:
        return True
    if (
        sources & {"downtrade", "uptrade"}
        and market_known
        and product_form_compatible is True
        and evidence & _NON_AUDIENCE_SEMANTIC_FAMILIES
    ):
        return True
    if (
        "scenario" in sources
        and market_known
        and product_form_compatible is not None
        and EvidenceFamily.TASK_VALUE_SCENE.value in evidence
        and len(semantic) >= 2
    ):
        return True
    return bool(
        "same_value" in sources
        and market_known
        and product_form_compatible is True
        and len(semantic) >= 2
        and grounded_value
    )


def _reference_purposes(
    recalled: RecalledCandidate,
    context: _CandidateContext,
    target_market: _MarketFacts,
    candidate_market: _MarketFacts,
    recall_manifest: CandidateRecallManifest,
    config: CandidateEligibilityConfig,
) -> list[str]:
    sources = set(recalled.recall_sources)
    purposes: set[str] = set()
    if "market_reference" in sources and _explicit_value_absence(
        context.target_records["M12C"],
        context.records["M12C"],
        set(config.explicit_absence_claim_roles),
    ):
        purposes.add(ReferencePurpose.MARKET_BASELINE_WITHOUT_VALUE.value)
    ratio = _weekly_volume_ratio(target_market, candidate_market)
    if "same_value" in sources and ratio is not None:
        threshold = recall_manifest.config.market_performance_ratio
        if ratio >= threshold:
            purposes.add(ReferencePurpose.HIGH_PERFORMANCE_VALUE_BUNDLE.value)
        elif ratio <= Decimal("1") / threshold:
            purposes.add(ReferencePurpose.LOW_PERFORMANCE_VALUE_BUNDLE.value)
    if _has_parameter_tier_difference(
        context.target_records["M03B"],
        context.records["M03B"],
    ):
        purposes.add(ReferencePurpose.PARAMETER_TIER_REFERENCE.value)
    if any(
        fact.reason_code == "adjacent_secondary_or_opportunity_battlefield"
        for fact in recalled.recall_facts
    ):
        purposes.add(ReferencePurpose.ADJACENT_BATTLEFIELD_REFERENCE.value)
    if (
        "same_value" in sources
        and context.target_records["M05C"]
        and context.records["M05C"]
    ):
        purposes.add(ReferencePurpose.SAME_VALUE_REALIZATION_REFERENCE.value)
    if "market_reference" in sources and context.market_known:
        purposes.add(ReferencePurpose.PRICE_VOLUME_ARCHETYPE_REFERENCE.value)
    return sorted(purposes)


def _question_readiness(
    recalled: RecalledCandidate,
    context: _CandidateContext,
    *,
    relation_member: bool,
    blocking_code: str | None,
) -> list[ProvisionalQuestionAssessment]:
    sources = set(recalled.recall_sources)
    families = set(context.evidence_families)
    semantic = families & _SEMANTIC_FAMILIES
    market = context.market_known
    form_known = context.product_form_compatible is not None
    pending_relations = sorted(
        {
            relation
            for source in sources
            for relation in _SOURCE_RELATIONS.get(source, ())
        }
    )
    rows: list[ProvisionalQuestionAssessment] = []
    for question_code in sorted(item.value for item in QuestionCode):
        required = sorted(_QUESTION_REQUIRED_FAMILIES[question_code])
        available = sorted(families & set(required))
        if blocking_code:
            readiness = ProvisionalQuestionReadiness.UNAVAILABLE.value
            missing = [blocking_code]
            reasons = ["candidate_cannot_drive_question_before_source_resolution"]
        else:
            readiness, missing, reasons = _question_state(
                question_code,
                sources=sources,
                semantic=semantic,
                families=families,
                relation_member=relation_member,
                market_known=market,
                product_form_known=form_known,
            )
        payload = {
            "question_code": question_code,
            "readiness": readiness,
            "pending_relation_codes": pending_relations,
            "required_evidence_families": required,
            "available_evidence_families": available,
            "missing_inputs": sorted(set(missing)),
            "reason_codes": sorted(set(reasons)),
            "can_drive_business_conclusion": False,
        }
        rows.append(
            ProvisionalQuestionAssessment(
                **payload,
                result_hash=stable_hash(
                    payload,
                    version="competitor_profile_provisional_question_v1",
                ),
            )
        )
    return rows


def _question_state(
    question_code: str,
    *,
    sources: set[str],
    semantic: set[str],
    families: set[str],
    relation_member: bool,
    market_known: bool,
    product_form_known: bool,
) -> tuple[str, list[str], list[str]]:
    grounded_value = bool(
        families
        & {
            EvidenceFamily.PURCHASE_REASON.value,
            EvidenceFamily.USER_REALIZATION.value,
        }
    )
    non_audience = bool(families & _NON_AUDIENCE_SEMANTIC_FAMILIES)
    missing: list[str] = []
    sufficient = False
    relevant = False

    if question_code == QuestionCode.PURCHASE_CHOICE.value:
        relevant = relation_member or bool(semantic)
        sufficient = (
            relation_member and market_known and len(semantic) >= 2 and grounded_value
        )
        missing = _missing(
            (relation_member, "relation_evaluation_candidate"),
            (market_known, "paired_market_price_volume"),
            (len(semantic) >= 2, "two_independent_semantic_evidence_families"),
            (grounded_value, "purchase_reason_or_user_realization_evidence"),
        )
    elif question_code == QuestionCode.PRICE_VOLUME_PRESSURE.value:
        relevant = market_known or relation_member
        sufficient = relation_member and market_known and non_audience
        missing = _missing(
            (relation_member, "relation_evaluation_candidate"),
            (market_known, "paired_market_price_volume"),
            (non_audience, "non_audience_semantic_evidence"),
        )
    elif question_code == QuestionCode.VALUE_SUBSTITUTION.value:
        route = bool(
            sources & {"downtrade", "same_purchase_pool", "same_value", "uptrade"}
        )
        relevant = route or grounded_value
        sufficient = relation_member and route and grounded_value and len(semantic) >= 2
        missing = _missing(
            (relation_member, "relation_evaluation_candidate"),
            (route, "value_substitution_recall_route"),
            (grounded_value, "purchase_reason_or_user_realization_evidence"),
            (len(semantic) >= 2, "two_independent_semantic_evidence_families"),
        )
    elif question_code == QuestionCode.CONFIGURATION_FOLLOW.value:
        relevant = (
            EvidenceFamily.CAPABILITY_EXPRESSION.value in families or relation_member
        )
        sufficient = (
            relation_member
            and product_form_known
            and EvidenceFamily.CAPABILITY_EXPRESSION.value in families
            and non_audience
        )
        missing = _missing(
            (relation_member, "relation_evaluation_candidate"),
            (product_form_known, "product_form_or_size_assessability"),
            (
                EvidenceFamily.CAPABILITY_EXPRESSION.value in families,
                "capability_expression_evidence",
            ),
            (non_audience, "value_or_task_evidence"),
        )
    elif question_code == QuestionCode.SAME_BRAND_PORTFOLIO_ROLE.value:
        route = "same_brand_ladder" in sources
        relevant = route
        sufficient = route and relation_member and market_known and non_audience
        missing = _missing(
            (route, "same_brand_ladder_recall_route"),
            (relation_member, "relation_evaluation_candidate"),
            (market_known, "paired_market_price_volume"),
            (non_audience, "value_or_task_evidence"),
        )
    elif question_code == QuestionCode.SCENARIO_SOLUTION.value:
        route = "scenario" in sources
        has_task = EvidenceFamily.TASK_VALUE_SCENE.value in families
        relevant = route
        sufficient = route and relation_member and has_task and len(semantic) >= 2
        missing = _missing(
            (route, "scenario_recall_route"),
            (relation_member, "relation_evaluation_candidate"),
            (has_task, "task_value_scene_evidence"),
            (len(semantic) >= 2, "second_independent_semantic_evidence_family"),
        )
    elif question_code == QuestionCode.PRICE_LADDER_DEFENSE.value:
        route = bool(sources & {"downtrade", "uptrade"})
        relevant = route
        sufficient = route and relation_member and market_known and non_audience
        missing = _missing(
            (route, "uptrade_or_downtrade_recall_route"),
            (relation_member, "relation_evaluation_candidate"),
            (market_known, "paired_market_price_volume"),
            (non_audience, "value_or_task_evidence"),
        )
    elif question_code == QuestionCode.KEY_COMPETITOR_SELECTION.value:
        relevant = relation_member
        missing = _missing(
            (relation_member, "relation_evaluation_candidate"),
            (market_known, "paired_market_price_volume"),
            (len(semantic) >= 2, "two_independent_semantic_evidence_families"),
            (False, "completed_relation_assessments"),
        )
        if relevant:
            return (
                ProvisionalQuestionReadiness.LIMITED.value,
                missing,
                ["formal_relation_assessment_required_before_key_selection"],
            )
        return (
            ProvisionalQuestionReadiness.UNAVAILABLE.value,
            missing,
            ["candidate_not_qualified_for_key_selection"],
        )
    else:  # pragma: no cover - enum coverage makes this defensive only
        raise ValueError(f"unknown provisional question: {question_code}")

    if sufficient:
        return (
            ProvisionalQuestionReadiness.ELIGIBLE.value,
            [],
            ["inputs_sufficient_for_formal_relation_evaluation"],
        )
    if relevant:
        return (
            ProvisionalQuestionReadiness.LIMITED.value,
            missing,
            ["question_has_partial_pre_relation_support"],
        )
    return (
        ProvisionalQuestionReadiness.UNAVAILABLE.value,
        missing or ["relevant_recall_route_or_evidence"],
        ["question_has_no_supported_pre_relation_route"],
    )


def _missing(*requirements: tuple[bool, str]) -> list[str]:
    return sorted(reason for passed, reason in requirements if not passed)


def _market_facts(records: Sequence[UpstreamRecordSnapshot]) -> _MarketFacts:
    facts = records[0].facts if records else {}
    price = _decimal(facts.get("price_wavg") or facts.get("weighted_price"))
    weekly_volume = _decimal(
        facts.get("avg_weekly_volume") or facts.get("weekly_volume")
    )
    if weekly_volume is None:
        total = _decimal(facts.get("sales_volume_total"))
        weeks = _decimal(facts.get("active_week_count"))
        if total is not None and weeks is not None and weeks > 0:
            weekly_volume = total / weeks
    return _MarketFacts(
        price=price,
        weekly_volume=weekly_volume,
        screen_size=_decimal(facts.get("screen_size_inch")),
        size_segment=_text(facts.get("size_segment")),
    )


def _market_pair_known(target: _MarketFacts, candidate: _MarketFacts) -> bool:
    return bool(
        target.price is not None
        and target.price > 0
        and candidate.price is not None
        and candidate.price > 0
        and target.weekly_volume is not None
        and target.weekly_volume >= 0
        and candidate.weekly_volume is not None
        and candidate.weekly_volume >= 0
    )


def _weekly_volume_ratio(
    target: _MarketFacts,
    candidate: _MarketFacts,
) -> Decimal | None:
    if (
        target.weekly_volume is None
        or candidate.weekly_volume is None
        or target.weekly_volume <= 0
        or candidate.weekly_volume < 0
    ):
        return None
    return candidate.weekly_volume / target.weekly_volume


def _product_form_compatible(
    product_category: str,
    target_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
    candidate_records: Mapping[str, tuple[UpstreamRecordSnapshot, ...]],
    target_market: _MarketFacts,
    candidate_market: _MarketFacts,
    recall_manifest: CandidateRecallManifest,
) -> bool | None:
    if product_category == "TV":
        if (
            target_market.screen_size is not None
            and candidate_market.screen_size is not None
        ):
            return (
                abs(target_market.screen_size - candidate_market.screen_size)
                <= recall_manifest.config.tv_screen_size_tolerance_inch
            )
        if target_market.size_segment and candidate_market.size_segment:
            return target_market.size_segment == candidate_market.size_segment
        return None
    target_params = _parameter_values(target_records["M03B"])
    candidate_params = _parameter_values(candidate_records["M03B"])
    form = _first_param(
        target_params,
        candidate_params,
        recall_manifest.config.ac_form_param_codes,
    )
    capacity = _first_param(
        target_params,
        candidate_params,
        recall_manifest.config.ac_capacity_param_codes,
    )
    if form is None or capacity is None:
        return None
    return form[0] == form[1] and capacity[0] == capacity[1]


def _has_parameter_tier_difference(
    target_records: Sequence[UpstreamRecordSnapshot],
    candidate_records: Sequence[UpstreamRecordSnapshot],
) -> bool:
    target = _parameter_values(target_records)
    candidate = _parameter_values(candidate_records)
    return any(target[code] != candidate[code] for code in set(target) & set(candidate))


def _parameter_values(
    records: Sequence[UpstreamRecordSnapshot],
) -> dict[str, str]:
    result: dict[str, str] = {}
    for record in records:
        payload = record.facts.get("param_values_json")
        if isinstance(payload, Mapping):
            for code, value in payload.items():
                normalized = _parameter_value(value)
                if normalized is not None:
                    result[str(code).lower()] = normalized
        code = _text(record.facts.get("param_code"))
        value = _parameter_value(
            record.facts.get("normalized_value")
            or record.facts.get("param_value")
            or record.facts.get("value")
        )
        if code and value:
            result[code.lower()] = value
    return dict(sorted(result.items()))


def _parameter_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("normalized_value", "tier_code", "value", "text", "raw_value"):
            normalized = _text(value.get(key))
            if normalized:
                return normalized
        return None
    return _text(value)


def _first_param(
    target: Mapping[str, str],
    candidate: Mapping[str, str],
    codes: Sequence[str],
) -> tuple[str, str] | None:
    for code in codes:
        normalized = code.lower()
        if normalized in target and normalized in candidate:
            return target[normalized], candidate[normalized]
    return None


def _explicit_value_absence(
    target_records: Sequence[UpstreamRecordSnapshot],
    candidate_records: Sequence[UpstreamRecordSnapshot],
    absence_roles: set[str],
) -> bool:
    target_claims = {
        claim
        for record in target_records
        if (claim := _text(record.facts.get("claim_code")))
    }
    if not target_claims:
        return False
    for record in candidate_records:
        claim = _text(record.facts.get("claim_code"))
        role = _text(
            record.facts.get("claim_value_role")
            or record.facts.get("claim_role")
            or record.facts.get("allocation_role")
        )
        if claim in target_claims and role in absence_roles:
            return True
    return False


def _walk_items(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized_key = str(key).lower()
            if not isinstance(nested, (Mapping, list, tuple, set)):
                yield normalized_key, nested
            elif isinstance(nested, (list, tuple, set)):
                for item in nested:
                    if not isinstance(item, (Mapping, list, tuple, set)):
                        yield normalized_key, item
            yield from _walk_items(nested)
    elif isinstance(value, (list, tuple, set)):
        for nested in value:
            yield from _walk_items(nested)


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    normalized = str(value).strip().lower()
    return normalized or None


def _record_key(
    row: UpstreamRecordSnapshot,
) -> tuple[str, str, str, str, str]:
    return (
        row.module_code,
        row.source_batch_id,
        row.record_type,
        row.record_id,
        row.result_hash,
    )


def _ref_key(row: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        row.module_code,
        row.source_batch_id or "",
        row.record_type,
        row.record_id,
        row.result_hash,
    )


def _ref_payload(row: EvidenceRef) -> dict[str, Any]:
    return row.model_dump(mode="python")


def _dedupe_refs(values: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {_ref_key(row): row for row in values}
    return [by_key[key] for key in sorted(by_key)]


__all__ = [
    "CandidateEligibilityClassifier",
    "CandidateEligibilityError",
    "CandidateEligibilityScopeError",
]
