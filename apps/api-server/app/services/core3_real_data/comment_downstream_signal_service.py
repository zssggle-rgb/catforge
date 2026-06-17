"""M06 comment downstream signal orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.services.core3_real_data.comment_downstream_signal_repositories import (
    CommentDownstreamSignalRepository,
    CommentDownstreamSignalReadRepository,
    CommentSignalCandidateRepository,
    SkuCommentSignalProfileRepository,
)
from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentDownstreamSignalRecord,
    CommentSignalCandidateRecord,
    CommentSignalReviewIssue,
    M06SkuInputBundle,
    M06SignalSeedBundle,
    SignalExtractionContext,
    SkuCommentSignalProfileRecord,
)
from app.services.core3_real_data.comment_entity_extractor import CommentEntityExtractor
from app.services.core3_real_data.comment_signal_aggregator import CommentSignalAggregator
from app.services.core3_real_data.comment_signal_extractors import CommentSignalExtractionPipeline
from app.services.core3_real_data.comment_signal_review_policy import CommentSignalReviewPolicy
from app.services.core3_real_data.constants import CORE3_M06_RULE_VERSION, CommentSignalType
from app.services.core3_real_data.sku_comment_signal_profile_builder import SkuCommentSignalProfileBuilder


@dataclass(frozen=True)
class CommentDownstreamSignalServiceResult:
    bundle: M06SkuInputBundle
    candidates: list[CommentSignalCandidateRecord]
    downstream_signals: list[CommentDownstreamSignalRecord]
    profile: SkuCommentSignalProfileRecord
    review_issues: list[CommentSignalReviewIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    write_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def input_count(self) -> int:
        return len(self.bundle.atoms)

    @property
    def output_count(self) -> int:
        return len(self.candidates) + len(self.downstream_signals) + 1

    @property
    def created_output_count(self) -> int:
        return sum(item.get("created_count", 0) for item in self.write_summary.values())

    @property
    def reused_output_count(self) -> int:
        return sum(item.get("reused_count", 0) for item in self.write_summary.values())

    @property
    def updated_output_count(self) -> int:
        return sum(item.get("updated_count", 0) for item in self.write_summary.values())


class CommentDownstreamSignalService:
    def __init__(
        self,
        repository: CommentDownstreamSignalReadRepository,
        *,
        seed: M06SignalSeedBundle,
        entity_extractor: CommentEntityExtractor | None = None,
        signal_pipeline: CommentSignalExtractionPipeline | None = None,
        aggregator: CommentSignalAggregator | None = None,
        profile_builder: SkuCommentSignalProfileBuilder | None = None,
        review_policy: CommentSignalReviewPolicy | None = None,
    ) -> None:
        self.repository = repository
        self.seed = seed
        self.entity_extractor = entity_extractor or CommentEntityExtractor()
        self.signal_pipeline = signal_pipeline or CommentSignalExtractionPipeline()
        self.aggregator = aggregator or CommentSignalAggregator()
        self.profile_builder = profile_builder or SkuCommentSignalProfileBuilder()
        self.review_policy = review_policy or CommentSignalReviewPolicy()

    def process_bundle(
        self,
        bundle: M06SkuInputBundle,
        *,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M06_RULE_VERSION,
        asset_version: str = "default",
        signal_types: Sequence[CommentSignalType | str] = (),
    ) -> CommentDownstreamSignalServiceResult:
        allowed_signal_types = _normalize_signal_types(signal_types)
        candidates: list[CommentSignalCandidateRecord] = []
        for atom in bundle.atoms:
            topic_hints = bundle.topic_hints_by_atom.get(atom.comment_evidence_id, [])
            extra_keywords = [term for topic in topic_hints for term in topic.matched_terms]
            entities = self.entity_extractor.extract(atom.sentence_text, extra_keywords=extra_keywords)
            context = SignalExtractionContext(
                bundle=bundle,
                atom=atom,
                topic_hints=topic_hints,
                entities=entities,
                seed=self.seed,
            )
            candidates.extend(
                self.signal_pipeline.extract(
                    context,
                    run_id=run_id,
                    module_run_id=module_run_id,
                )
            )
        if allowed_signal_types:
            candidates = [
                candidate
                for candidate in candidates
                if CommentSignalType(candidate.signal_type) in allowed_signal_types
            ]

        downstream_signals = self.aggregator.aggregate(
            bundle,
            candidates,
            run_id=run_id,
            module_run_id=module_run_id,
            asset_version=asset_version,
            rule_version=rule_version,
        )
        profile = self.profile_builder.build(
            bundle,
            downstream_signals,
            run_id=run_id,
            module_run_id=module_run_id,
            asset_version=asset_version,
            rule_version=rule_version,
        )
        review_issues = self.review_policy.evaluate(bundle, downstream_signals)
        write_summary = self._persist_outputs(
            bundle=bundle,
            candidates=candidates,
            downstream_signals=downstream_signals,
            profile=profile,
            rule_version=rule_version,
        )
        warnings = _warnings(bundle, review_issues)
        summary = {
            "sku_code": bundle.sku_code,
            "input_atom_count": len(bundle.atoms),
            "candidate_count": len(candidates),
            "downstream_signal_count": len(downstream_signals),
            "profile_count": 1,
            "signal_type_counts": _signal_type_counts(downstream_signals),
            "filtered_signal_types": sorted(signal_type.value for signal_type in allowed_signal_types),
            "ready_flags": {
                "claim_validation_ready": profile.claim_validation_ready,
                "task_cue_ready": profile.task_cue_ready,
                "target_group_cue_ready": profile.target_group_cue_ready,
                "battlefield_support_ready": profile.battlefield_support_ready,
            },
            "write_summary": write_summary,
            "warnings": warnings,
            "boundary_note": "M06 只输出评论下游信号，不输出最终任务、客群、战场或竞品结论。",
        }
        return CommentDownstreamSignalServiceResult(
            bundle=bundle,
            candidates=candidates,
            downstream_signals=downstream_signals,
            profile=profile,
            review_issues=review_issues,
            warnings=warnings,
            write_summary=write_summary,
            summary=summary,
        )

    def _persist_outputs(
        self,
        *,
        bundle: M06SkuInputBundle,
        candidates: list[CommentSignalCandidateRecord],
        downstream_signals: list[CommentDownstreamSignalRecord],
        profile: SkuCommentSignalProfileRecord,
        rule_version: str,
    ) -> dict[str, dict[str, int]]:
        CommentSignalCandidateRepository.mark_previous_inactive(
            self.repository,
            bundle.batch_id,
            bundle.sku_code,
            rule_version=rule_version,
        )
        CommentDownstreamSignalRepository.mark_previous_inactive(
            self.repository,
            bundle.batch_id,
            bundle.sku_code,
            rule_version=rule_version,
        )
        SkuCommentSignalProfileRepository.mark_previous_inactive(
            self.repository,
            bundle.batch_id,
            bundle.sku_code,
            rule_version=rule_version,
        )
        candidate_result = self.repository.bulk_upsert_candidates(candidates)
        signal_result = self.repository.bulk_upsert_signals(downstream_signals)
        profile_result = self.repository.upsert_profile(profile)
        return {
            "comment_signal_candidate": _write_counts(candidate_result),
            "comment_downstream_signal": _write_counts(signal_result),
            "sku_comment_signal_profile": _write_counts(profile_result),
        }


def _write_counts(result: Any) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "updated_count": result.updated_count,
    }


def _normalize_signal_types(signal_types: Sequence[CommentSignalType | str]) -> set[CommentSignalType]:
    return {CommentSignalType(value) for value in signal_types if str(value).strip()}


def _signal_type_counts(signals: list[CommentDownstreamSignalRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for signal in signals:
        key = str(signal.signal_type)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _warnings(bundle: M06SkuInputBundle, review_issues: list[CommentSignalReviewIssue]) -> list[str]:
    values = [issue.reason_code for issue in review_issues if issue.review_required]
    if not bundle.atoms:
        values.append("no_usable_comment_atom")
    return sorted({str(value) for value in values})
