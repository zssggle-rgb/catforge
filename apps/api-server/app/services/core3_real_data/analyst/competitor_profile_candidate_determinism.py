"""Canonicalize and replay the candidate pipeline without database access."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism_schemas import (
    CandidatePipelineDeterminismReceipt,
    DeterminismCheck,
    ModuleCanonicalizationStats,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility import (
    CandidateEligibilityClassifier,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityConfig,
    CandidateEligibilityManifest,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall import (
    CandidateRecallEngine,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallConfig,
    CandidateRecallManifest,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
    ModuleCategorySnapshot,
    TargetModuleInput,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import EvidenceRef
from app.services.core3_real_data.hash_utils import canonicalize_json, stable_hash


SourcePages = Mapping[str, Sequence[Sequence[UpstreamRecordSnapshot]]]


class CandidatePipelineDeterminismError(RuntimeError):
    """Base error for candidate-pipeline canonicalization or replay failures."""


class CandidatePipelineDuplicateConflictError(CandidatePipelineDeterminismError):
    pass


class CandidatePipelineHashIntegrityError(CandidatePipelineDeterminismError):
    pass


@dataclass(frozen=True)
class CandidatePipelineRun:
    category_bundle: CompetitorProfileCategoryInputBundle
    target_bundle: CompetitorProfileTargetInputBundle
    recall_manifest: CandidateRecallManifest
    eligibility_manifest: CandidateEligibilityManifest
    receipt: CandidatePipelineDeterminismReceipt


@dataclass(frozen=True)
class _CanonicalizedInputs:
    category_bundle: CompetitorProfileCategoryInputBundle
    target_bundle: CompetitorProfileTargetInputBundle
    stats: tuple[ModuleCanonicalizationStats, ...]


class CandidatePipelineDeterminismGuard:
    """Generate or verify G10/G11 outputs through a canonical two-pass replay."""

    def run(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        *,
        recall_config: CandidateRecallConfig | None = None,
        eligibility_config: CandidateEligibilityConfig | None = None,
        source_pages: SourcePages | None = None,
    ) -> CandidatePipelineRun:
        canonical, recall, eligibility = self._generate(
            category_bundle,
            target_bundle,
            recall_config=recall_config or CandidateRecallConfig(),
            eligibility_config=eligibility_config or CandidateEligibilityConfig(),
            source_pages=source_pages,
        )
        receipt = _build_receipt(
            mode="generated",
            canonical=canonical,
            recall=recall,
            eligibility=eligibility,
            provided_verified=False,
        )
        return CandidatePipelineRun(
            category_bundle=canonical.category_bundle,
            target_bundle=canonical.target_bundle,
            recall_manifest=recall,
            eligibility_manifest=eligibility,
            receipt=receipt,
        )

    def run_precanonicalized(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        *,
        recall_config: CandidateRecallConfig | None = None,
        eligibility_config: CandidateEligibilityConfig | None = None,
    ) -> CandidatePipelineRun:
        """Replay a provider-canonical bundle without constructing a full copy.

        ``CompetitorProfileInputProvider`` already emits SKU-ordered, unique
        authority records.  Production generation can therefore validate that
        contract in place and retain the same two-pass replay receipt, avoiding
        a second category-sized Pydantic graph in memory.  General callers that
        may contain duplicates must continue to use :meth:`run`.
        """

        canonical = _validate_precanonicalized_inputs(category_bundle, target_bundle)
        recall, eligibility = self._replay(
            canonical,
            recall_config=recall_config or CandidateRecallConfig(),
            eligibility_config=eligibility_config or CandidateEligibilityConfig(),
        )
        receipt = _build_receipt(
            mode="generated",
            canonical=canonical,
            recall=recall,
            eligibility=eligibility,
            provided_verified=False,
        )
        return CandidatePipelineRun(
            category_bundle=category_bundle,
            target_bundle=target_bundle,
            recall_manifest=recall,
            eligibility_manifest=eligibility,
            receipt=receipt,
        )

    def verify(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        recall_manifest: CandidateRecallManifest,
        eligibility_manifest: CandidateEligibilityManifest,
        *,
        source_pages: SourcePages | None = None,
    ) -> CandidatePipelineDeterminismReceipt:
        canonical, expected_recall, expected_eligibility = self._generate(
            category_bundle,
            target_bundle,
            recall_config=recall_manifest.config,
            eligibility_config=eligibility_manifest.config,
            source_pages=source_pages,
        )
        if _payload(recall_manifest) != _payload(expected_recall):
            raise CandidatePipelineHashIntegrityError(
                "provided recall manifest does not match deterministic replay"
            )
        if _payload(eligibility_manifest) != _payload(expected_eligibility):
            raise CandidatePipelineHashIntegrityError(
                "provided eligibility manifest does not match deterministic replay"
            )
        return _build_receipt(
            mode="verified",
            canonical=canonical,
            recall=expected_recall,
            eligibility=expected_eligibility,
            provided_verified=True,
        )

    @staticmethod
    def _generate(
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_bundle: CompetitorProfileTargetInputBundle,
        *,
        recall_config: CandidateRecallConfig,
        eligibility_config: CandidateEligibilityConfig,
        source_pages: SourcePages | None,
    ) -> tuple[
        _CanonicalizedInputs,
        CandidateRecallManifest,
        CandidateEligibilityManifest,
    ]:
        canonical = _canonicalize_inputs(
            category_bundle,
            target_bundle,
            source_pages=source_pages,
        )
        recall, eligibility = CandidatePipelineDeterminismGuard._replay(
            canonical,
            recall_config=recall_config,
            eligibility_config=eligibility_config,
        )
        return canonical, recall, eligibility

    @staticmethod
    def _replay(
        canonical: _CanonicalizedInputs,
        *,
        recall_config: CandidateRecallConfig,
        eligibility_config: CandidateEligibilityConfig,
    ) -> tuple[CandidateRecallManifest, CandidateEligibilityManifest]:
        first_recall = CandidateRecallEngine().recall(
            canonical.category_bundle,
            canonical.target_bundle,
            recall_config,
        )
        first_eligibility = CandidateEligibilityClassifier().classify(
            canonical.category_bundle,
            canonical.target_bundle,
            first_recall,
            eligibility_config,
        )
        second_recall = CandidateRecallEngine().recall(
            canonical.category_bundle,
            canonical.target_bundle,
            recall_config,
        )
        second_eligibility = CandidateEligibilityClassifier().classify(
            canonical.category_bundle,
            canonical.target_bundle,
            second_recall,
            eligibility_config,
        )
        if _manifest_signature(first_recall) != _manifest_signature(second_recall):
            raise CandidatePipelineHashIntegrityError("recall replay is not idempotent")
        if _manifest_signature(first_eligibility) != _manifest_signature(
            second_eligibility
        ):
            raise CandidatePipelineHashIntegrityError(
                "eligibility replay is not idempotent"
            )
        _assert_candidate_conservation(first_recall, first_eligibility)
        return first_recall, first_eligibility


def _validate_precanonicalized_inputs(
    category_bundle: CompetitorProfileCategoryInputBundle,
    target_bundle: CompetitorProfileTargetInputBundle,
) -> _CanonicalizedInputs:
    """Validate the provider's canonical contract without copying record facts."""

    if category_bundle.serving_scope != target_bundle.serving_scope:
        raise CandidatePipelineDeterminismError(
            "target and category bundles must use the same serving scope"
        )
    if set(category_bundle.modules) != set(target_bundle.modules):
        raise CandidatePipelineDeterminismError(
            "precanonicalized target modules must exactly cover category modules"
        )

    stats: list[ModuleCanonicalizationStats] = []
    for module_code in sorted(category_bundle.modules):
        module = category_bundle.modules[module_code]
        sku_codes = list(module.records_by_sku)
        if sku_codes != sorted(set(sku_codes)):
            raise CandidatePipelineDeterminismError(
                f"precanonicalized {module_code} SKU keys are not sorted and unique"
            )

        category_count = 0
        business_keys: set[tuple[str, str, str, str]] = set()
        for sku_code in sku_codes:
            records = module.records_by_sku[sku_code]
            if records != sorted(records, key=_record_sort_key):
                raise CandidatePipelineDeterminismError(
                    f"precanonicalized {module_code} records are not canonical"
                )
            for record in records:
                if record.sku_code != sku_code:
                    raise CandidatePipelineDeterminismError(
                        f"precanonicalized {module_code} record crosses its SKU key"
                    )
                key = _record_business_key(record)
                if key in business_keys:
                    raise CandidatePipelineDuplicateConflictError(
                        f"precanonicalized {module_code} contains duplicate authority keys"
                    )
                business_keys.add(key)
                category_count += 1

        target_module = target_bundle.modules[module_code]
        target_records = target_module.records
        if target_records != sorted(target_records, key=_record_sort_key):
            raise CandidatePipelineDeterminismError(
                f"precanonicalized target {module_code} records are not canonical"
            )
        expected = module.records_by_sku.get(target_bundle.target_sku_code, [])
        if target_records != expected:
            raise CandidatePipelineDeterminismError(
                f"precanonicalized target {module_code} records conflict with category"
            )

        stat_payload = {
            "module_code": module_code,
            "category_input_record_count": category_count,
            "category_unique_record_count": category_count,
            "category_exact_duplicate_count": 0,
            "target_input_record_count": len(target_records),
            "target_unique_record_count": len(target_records),
            "target_exact_duplicate_count": 0,
        }
        stats.append(
            ModuleCanonicalizationStats(
                **stat_payload,
                result_hash=stable_hash(
                    stat_payload,
                    version="competitor_profile_module_canonicalization_v1",
                ),
            )
        )
    return _CanonicalizedInputs(
        category_bundle=category_bundle,
        target_bundle=target_bundle,
        stats=tuple(stats),
    )


def _canonicalize_inputs(
    category_bundle: CompetitorProfileCategoryInputBundle,
    target_bundle: CompetitorProfileTargetInputBundle,
    *,
    source_pages: SourcePages | None,
) -> _CanonicalizedInputs:
    if category_bundle.serving_scope != target_bundle.serving_scope:
        raise CandidatePipelineDeterminismError(
            "target and category bundles must use the same serving scope"
        )
    page_modules = set(source_pages or {})
    unknown_page_modules = page_modules - set(category_bundle.modules)
    if unknown_page_modules:
        raise CandidatePipelineDeterminismError(
            "source pages contain modules outside the exact authority bundle"
        )

    category_modules: dict[str, ModuleCategorySnapshot] = {}
    category_counts: dict[str, tuple[int, int, int]] = {}
    for module_code in sorted(category_bundle.modules):
        module = category_bundle.modules[module_code]
        original_records = [
            record
            for sku_code in module.records_by_sku
            for record in module.records_by_sku[sku_code]
        ]
        canonical_original, _ = _canonical_records(
            original_records,
            scope=f"category:{module_code}",
        )
        selected_records = original_records
        if source_pages is not None and module_code in source_pages:
            selected_records = [
                record for page in source_pages[module_code] for record in page
            ]
            canonical_selected, selected_duplicates = _canonical_records(
                selected_records,
                scope=f"source_pages:{module_code}",
            )
            if _record_map(canonical_selected) != _record_map(canonical_original):
                raise CandidatePipelineHashIntegrityError(
                    f"source pages for {module_code} do not preserve the exact authority records"
                )
        else:
            canonical_selected, selected_duplicates = _canonical_records(
                selected_records,
                scope=f"category:{module_code}",
            )
        grouped: dict[str, list[UpstreamRecordSnapshot]] = defaultdict(list)
        for record in canonical_selected:
            grouped[record.sku_code].append(record)
        records_by_sku = {
            sku_code: sorted(grouped[sku_code], key=_record_sort_key)
            for sku_code in sorted(grouped)
        }
        category_modules[module_code] = module.model_copy(
            update={
                "record_count": len(canonical_selected),
                "sku_count": len(records_by_sku),
                "records_by_sku": records_by_sku,
            }
        )
        category_counts[module_code] = (
            len(selected_records),
            len(canonical_selected),
            selected_duplicates,
        )

    canonical_category = category_bundle.model_copy(
        update={"modules": category_modules}
    )
    target_modules: dict[str, TargetModuleInput] = {}
    target_evidence_refs: list[EvidenceRef] = []
    stats: list[ModuleCanonicalizationStats] = []
    for module_code in sorted(canonical_category.modules):
        target_module = target_bundle.modules[module_code]
        target_records, target_duplicates = _canonical_records(
            target_module.records,
            scope=f"target:{module_code}",
        )
        expected_target_records = canonical_category.modules[
            module_code
        ].records_by_sku.get(target_bundle.target_sku_code, [])
        if _record_map(target_records) != _record_map(expected_target_records):
            raise CandidatePipelineDeterminismError(
                f"target {module_code} records conflict with the category bundle"
            )
        refs = [_evidence_ref(record) for record in target_records]
        target_evidence_refs.extend(refs)
        target_modules[module_code] = target_module.model_copy(
            update={
                "records": target_records,
                "evidence_refs": refs,
            }
        )
        category_input_count, category_unique_count, category_duplicates = (
            category_counts[module_code]
        )
        stat_payload = {
            "module_code": module_code,
            "category_input_record_count": category_input_count,
            "category_unique_record_count": category_unique_count,
            "category_exact_duplicate_count": category_duplicates,
            "target_input_record_count": len(target_module.records),
            "target_unique_record_count": len(target_records),
            "target_exact_duplicate_count": target_duplicates,
        }
        stats.append(
            ModuleCanonicalizationStats(
                **stat_payload,
                result_hash=stable_hash(
                    stat_payload,
                    version="competitor_profile_module_canonicalization_v1",
                ),
            )
        )
    canonical_target = target_bundle.model_copy(
        update={
            "modules": target_modules,
            "evidence_refs": _dedupe_refs(target_evidence_refs),
        }
    )
    return _CanonicalizedInputs(
        category_bundle=canonical_category,
        target_bundle=canonical_target,
        stats=tuple(stats),
    )


def _canonical_records(
    records: Sequence[UpstreamRecordSnapshot],
    *,
    scope: str,
) -> tuple[list[UpstreamRecordSnapshot], int]:
    by_key: dict[tuple[str, str, str, str], UpstreamRecordSnapshot] = {}
    duplicate_count = 0
    for record in records:
        key = _record_business_key(record)
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            continue
        if canonicalize_json(_payload(existing)) != canonicalize_json(_payload(record)):
            raise CandidatePipelineDuplicateConflictError(
                f"conflicting duplicate source record in {scope}: {'/'.join(key)}"
            )
        duplicate_count += 1
    return sorted(by_key.values(), key=_record_sort_key), duplicate_count


def _assert_candidate_conservation(
    recall: CandidateRecallManifest,
    eligibility: CandidateEligibilityManifest,
) -> None:
    recall_codes = [row.candidate.sku_code for row in recall.candidates]
    eligibility_codes = [row.candidate.sku_code for row in eligibility.candidates]
    if recall_codes != eligibility_codes:
        raise CandidatePipelineHashIntegrityError(
            "eligibility manifest does not conserve recalled candidates"
        )
    if recall.candidate_count != eligibility.candidate_count:
        raise CandidatePipelineHashIntegrityError(
            "candidate counts differ between recall and eligibility"
        )
    if eligibility.recall_result_hash != recall.result_hash:
        raise CandidatePipelineHashIntegrityError(
            "eligibility manifest is not chained to the recall result hash"
        )


def _build_receipt(
    *,
    mode: str,
    canonical: _CanonicalizedInputs,
    recall: CandidateRecallManifest,
    eligibility: CandidateEligibilityManifest,
    provided_verified: bool,
) -> CandidatePipelineDeterminismReceipt:
    fact_count = sum(len(row.recall_facts) for row in recall.candidates)
    question_count = sum(len(row.question_readiness) for row in eligibility.candidates)
    evidence_keys = {
        _ref_key(ref)
        for candidate in recall.candidates
        for ref in candidate.evidence_refs
    } | {
        _ref_key(ref)
        for candidate in eligibility.candidates
        for ref in candidate.evidence_refs
    }
    check_counts = {
        "candidate_conservation": recall.candidate_count,
        "canonical_source_deduplication": sum(
            row.category_input_record_count for row in canonical.stats
        ),
        "eligibility_replay_idempotency": eligibility.candidate_count,
        "question_coverage": question_count,
        "recall_replay_idempotency": recall.candidate_count,
        "stable_hash_chain": 2 + recall.candidate_count + eligibility.candidate_count,
    }
    if provided_verified:
        check_counts.update(
            {
                "provided_eligibility_hash_chain_verified": eligibility.candidate_count,
                "provided_recall_hash_chain_verified": recall.candidate_count,
            }
        )
    checks = [
        DeterminismCheck(
            check_code=check_code,
            passed=True,
            checked_node_count=check_counts[check_code],
            detail_hash=stable_hash(
                {
                    "check_code": check_code,
                    "checked_node_count": check_counts[check_code],
                    "recall_result_hash": recall.result_hash,
                    "eligibility_result_hash": eligibility.result_hash,
                },
                version="competitor_profile_determinism_check_v1",
            ),
        )
        for check_code in sorted(check_counts)
    ]
    category = canonical.category_bundle
    target = canonical.target_bundle
    input_payload = {
        "mode": mode,
        "category_input_fingerprint": category.input_fingerprint,
        "target_input_fingerprint": target.input_fingerprint,
        "recall_config_version": recall.config.config_version,
        "eligibility_config_version": eligibility.config.config_version,
        "canonicalization_hashes": [row.result_hash for row in canonical.stats],
    }
    input_fingerprint = stable_hash(
        input_payload,
        version="competitor_profile_candidate_determinism_input_v1",
    )
    receipt_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "recall_result_hash": recall.result_hash,
        "eligibility_result_hash": eligibility.result_hash,
        "candidate_count": recall.candidate_count,
        "recall_fact_count": fact_count,
        "question_assessment_count": question_count,
        "unique_evidence_ref_count": len(evidence_keys),
        "check_hashes": [row.detail_hash for row in checks],
    }
    return CandidatePipelineDeterminismReceipt(
        mode=mode,
        project_id=category.serving_scope.project_id,
        category_code=category.serving_scope.category_code,
        product_category=category.serving_scope.product_category,
        release_scope_key=category.serving_scope.release_scope_key,
        target_sku_code=target.target_sku_code,
        category_input_fingerprint=category.input_fingerprint,
        target_input_fingerprint=target.input_fingerprint,
        recall_config_version=recall.config.config_version,
        eligibility_config_version=eligibility.config.config_version,
        recall_result_hash=recall.result_hash,
        eligibility_result_hash=eligibility.result_hash,
        candidate_count=recall.candidate_count,
        recall_fact_count=fact_count,
        question_assessment_count=question_count,
        unique_evidence_ref_count=len(evidence_keys),
        replay_count=2,
        canonicalization_stats=list(canonical.stats),
        checks=checks,
        input_fingerprint=input_fingerprint,
        result_hash=stable_hash(
            receipt_payload,
            version="competitor_profile_candidate_determinism_result_v1",
        ),
    )


def _record_map(
    records: Sequence[UpstreamRecordSnapshot],
) -> dict[tuple[str, str, str, str], str]:
    return {
        _record_business_key(record): canonicalize_json(_payload(record))
        for record in records
    }


def _record_business_key(
    record: UpstreamRecordSnapshot,
) -> tuple[str, str, str, str]:
    return (
        record.module_code,
        record.source_batch_id,
        record.record_type,
        record.record_id,
    )


def _record_sort_key(
    record: UpstreamRecordSnapshot,
) -> tuple[str, str, str, str, str]:
    return (
        record.sku_code,
        record.source_batch_id,
        record.record_type,
        record.record_id,
        record.result_hash,
    )


def _evidence_ref(record: UpstreamRecordSnapshot) -> EvidenceRef:
    return EvidenceRef(
        module_code=record.module_code,
        profile_version=record.profile_version,
        rule_version=record.rule_version,
        taxonomy_version=record.taxonomy_version,
        record_type=record.record_type,
        record_id=record.record_id,
        result_hash=record.result_hash,
        source_batch_id=record.source_batch_id,
    )


def _dedupe_refs(refs: Iterable[EvidenceRef]) -> list[EvidenceRef]:
    by_key = {_ref_key(ref): ref for ref in refs}
    return [by_key[key] for key in sorted(by_key)]


def _ref_key(ref: EvidenceRef) -> tuple[str, str, str, str, str]:
    return (
        ref.module_code,
        ref.source_batch_id or "",
        ref.record_type,
        ref.record_id,
        ref.result_hash,
    )


def _payload(value: object) -> dict[str, object]:
    model_dump = getattr(value, "model_dump", None)
    if model_dump is None:
        raise TypeError("determinism payload must be a typed model")
    return model_dump(mode="python")


def _manifest_signature(value: object) -> tuple[str, str, tuple[str, ...]]:
    """Compare replay outputs without materializing another full nested payload."""

    result_hash = str(getattr(value, "result_hash", ""))
    input_fingerprint = str(getattr(value, "input_fingerprint", ""))
    candidates = getattr(value, "candidates", ())
    candidate_hashes = tuple(str(row.result_hash) for row in candidates)
    return result_hash, input_fingerprint, candidate_hashes


__all__ = [
    "CandidatePipelineDeterminismError",
    "CandidatePipelineDeterminismGuard",
    "CandidatePipelineDuplicateConflictError",
    "CandidatePipelineHashIntegrityError",
    "CandidatePipelineRun",
    "SourcePages",
]
