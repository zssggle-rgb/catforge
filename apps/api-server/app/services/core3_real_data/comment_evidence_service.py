"""M05 comment evidence orchestration service.

This service composes the M05 builders and persistence boundary for one SKU
input bundle. It intentionally stops before user-task, target-group,
battlefield, competitor, score, selection, and report conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.services.core3_real_data.comment_domain_hint_service import CommentDomainHintService
from app.services.core3_real_data.comment_evidence_repositories import (
    CommentEvidenceAtomRepository,
    CommentEvidenceReadRepository,
    CommentEvidenceRepositoryWriteResult,
    CommentQualityProfileRepository,
    CommentTopicHintRepository,
    CommentUnitRepository,
)
from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentQualityProfileRecord,
    CommentTopicSeedIndex,
    CommentUnitEvidenceLinkRecord,
    CommentUnitRecord,
    M05DownstreamImpact,
    M05ReviewIssue,
    M05SkuInputBundle,
    TopicHintRecord,
)
from app.services.core3_real_data.comment_quality_profile_service import CommentQualityProfileService
from app.services.core3_real_data.comment_review_policy import CommentEvidenceReviewPolicy
from app.services.core3_real_data.comment_sentence_atom_builder import CommentSentenceAtomBuilder
from app.services.core3_real_data.comment_sentiment_hint_service import CommentSentimentHintService
from app.services.core3_real_data.comment_topic_hint_matcher import CommentTopicHintMatcher
from app.services.core3_real_data.comment_topic_seed_loader import (
    CommentTopicSeedLoader,
    CommentTopicSeedValidationError,
)
from app.services.core3_real_data.comment_unit_builder import CommentUnitBuilder
from app.services.core3_real_data.comment_unit_link_builder import CommentUnitLinkBuilder
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    Core3EvidenceType,
)


@dataclass(frozen=True)
class CommentEvidenceServiceResult:
    bundle: M05SkuInputBundle
    comment_units: list[CommentUnitRecord]
    unit_links: list[CommentUnitEvidenceLinkRecord]
    sentence_atoms: list[CommentEvidenceAtomRecord]
    topic_hints: list[TopicHintRecord]
    quality_profile: CommentQualityProfileRecord
    review_issues: list[M05ReviewIssue] = field(default_factory=list)
    downstream_impacts: list[M05DownstreamImpact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    write_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    blocked: bool = False
    review_required: bool = False
    seed_loaded: bool = True
    m02_comment_trace_ready: bool = True

    @property
    def input_count(self) -> int:
        return len(self.bundle.evidence_inputs)

    @property
    def output_count(self) -> int:
        return (
            len(self.comment_units)
            + len(self.unit_links)
            + len(self.sentence_atoms)
            + len(self.topic_hints)
            + 1
        )

    @property
    def created_output_count(self) -> int:
        return sum(item.get("created_count", 0) for item in self.write_summary.values())

    @property
    def reused_output_count(self) -> int:
        return sum(item.get("reused_count", 0) for item in self.write_summary.values())

    @property
    def updated_output_count(self) -> int:
        return sum(item.get("updated_count", 0) for item in self.write_summary.values())


class CommentEvidenceService:
    """Build and persist the M05 outputs for one SKU bundle."""

    def __init__(
        self,
        repository: CommentEvidenceReadRepository,
        *,
        topic_seed: CommentTopicSeedIndex | None = None,
        topic_seed_loader: CommentTopicSeedLoader | None = None,
        unit_builder: CommentUnitBuilder | None = None,
        link_builder: CommentUnitLinkBuilder | None = None,
        atom_builder: CommentSentenceAtomBuilder | None = None,
        domain_hint_service: CommentDomainHintService | None = None,
        sentiment_hint_service: CommentSentimentHintService | None = None,
        topic_hint_matcher: CommentTopicHintMatcher | None = None,
        quality_profile_service: CommentQualityProfileService | None = None,
        review_policy: CommentEvidenceReviewPolicy | None = None,
        target_sku_expected_comment_units: Mapping[str, int] | None = None,
    ) -> None:
        self.repository = repository
        self.topic_seed = topic_seed
        self.topic_seed_loader = topic_seed_loader or CommentTopicSeedLoader()
        self.unit_builder = unit_builder or CommentUnitBuilder()
        self.link_builder = link_builder or CommentUnitLinkBuilder()
        self.atom_builder = atom_builder or CommentSentenceAtomBuilder()
        self.domain_hint_service = domain_hint_service or CommentDomainHintService()
        self.sentiment_hint_service = sentiment_hint_service or CommentSentimentHintService()
        self.topic_hint_matcher = topic_hint_matcher or CommentTopicHintMatcher()
        self.quality_profile_service = quality_profile_service or CommentQualityProfileService()
        self.review_policy = review_policy or CommentEvidenceReviewPolicy()
        self.target_sku_expected_comment_units = dict(target_sku_expected_comment_units or {})

    def process_bundle(
        self,
        bundle: M05SkuInputBundle,
        *,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentEvidenceServiceResult:
        seed, seed_loaded, seed_warning, resolved_asset_version = self._load_seed(asset_version)
        unit_result = self.unit_builder.build_units(
            bundle,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            asset_version=resolved_asset_version,
        )
        link_result = self.link_builder.build_links(
            bundle,
            unit_result.records,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            asset_version=resolved_asset_version,
        )
        atom_result = self.atom_builder.build_atoms(
            bundle,
            unit_result.records,
            run_id=run_id,
            module_run_id=module_run_id,
            rule_version=rule_version,
            asset_version=resolved_asset_version,
        )
        domain_result = self.domain_hint_service.apply_domain_hints(atom_result.records)
        sentiment_result = self.sentiment_hint_service.apply_sentiment_hints(domain_result.records)
        topic_result = (
            self.topic_hint_matcher.match_topic_hints(
                seed,
                sentiment_result.records,
                rule_version=rule_version,
                asset_version=resolved_asset_version,
            )
            if seed is not None
            else None
        )
        topic_hints = list(topic_result.records) if topic_result is not None else []
        profile_result = self.quality_profile_service.build_profile(
            project_id=bundle.project_id,
            category_code=_enum_value(bundle.category_code),
            batch_id=bundle.batch_id,
            sku_code=bundle.sku_code,
            comment_units=unit_result.records,
            sentence_atoms=sentiment_result.records,
            topic_hints=topic_hints,
            run_id=run_id,
            module_run_id=module_run_id,
            model_name=bundle.model_name,
            brand_name=bundle.brand_name,
            input_fingerprint=bundle.input_fingerprint,
            rule_version=rule_version,
            asset_version=resolved_asset_version,
        )
        m02_comment_trace_ready = _m02_comment_trace_ready(bundle)
        review_result = self.review_policy.evaluate(
            profile=profile_result.record,
            sentence_atoms=sentiment_result.records,
            topic_hints=topic_hints,
            seed_loaded=seed_loaded,
            m02_completed=True,
            m02_comment_trace_ready=m02_comment_trace_ready,
            target_sku_expected_comment_units=self.target_sku_expected_comment_units,
        )
        write_summary = self._persist_outputs(
            bundle=bundle,
            comment_units=unit_result.records,
            unit_links=link_result.records,
            sentence_atoms=sentiment_result.records,
            topic_hints=topic_hints,
            quality_profile=profile_result.record,
            rule_version=rule_version,
        )
        warnings = _unique_values(
            [
                seed_warning,
                *_issue_codes(unit_result.issues),
                *_issue_codes(link_result.issues),
                *_issue_codes(atom_result.issues),
                *_issue_codes(domain_result.issues),
                *_issue_codes(sentiment_result.issues),
                *(profile_result.record.warning_flags or []),
                *profile_result.record.blocked_reasons,
                *_issue_codes(profile_result.issues),
                *_issue_codes(review_result.review_issues),
            ]
        )
        blocked = bool(review_result.blocked or not profile_result.record.downstream_ready)
        review_required = bool(
            review_result.review_required
            or profile_result.record.review_required
            or any(record.review_required for record in [*unit_result.records, *sentiment_result.records, *topic_hints])
        )
        summary = self._build_summary(
            bundle=bundle,
            comment_units=unit_result.records,
            unit_links=link_result.records,
            sentence_atoms=sentiment_result.records,
            topic_hints=topic_hints,
            quality_profile=profile_result.record,
            review_issues=review_result.review_issues,
            downstream_impacts=review_result.downstream_impacts,
            write_summary=write_summary,
            seed_loaded=seed_loaded,
            m02_comment_trace_ready=m02_comment_trace_ready,
            topic_match_summary=_topic_match_summary(topic_result),
            warnings=warnings,
            blocked=blocked,
            review_required=review_required,
        )
        return CommentEvidenceServiceResult(
            bundle=bundle,
            comment_units=unit_result.records,
            unit_links=link_result.records,
            sentence_atoms=sentiment_result.records,
            topic_hints=topic_hints,
            quality_profile=profile_result.record,
            review_issues=review_result.review_issues,
            downstream_impacts=review_result.downstream_impacts,
            warnings=warnings,
            write_summary=write_summary,
            summary=summary,
            blocked=blocked,
            review_required=review_required,
            seed_loaded=seed_loaded,
            m02_comment_trace_ready=m02_comment_trace_ready,
        )

    def _load_seed(
        self,
        asset_version: str,
    ) -> tuple[CommentTopicSeedIndex | None, bool, str | None, str]:
        if self.topic_seed is not None:
            resolved_asset_version = _optional_string(
                self.topic_seed.metadata_json.get("asset_version")
            ) or asset_version
            return self.topic_seed, True, None, resolved_asset_version
        try:
            seed_result = self.topic_seed_loader.load()
        except CommentTopicSeedValidationError as exc:
            return None, False, "m05_topic_seed_load_failed", asset_version
        resolved_asset_version = seed_result.asset_version or asset_version
        return seed_result.seed, True, None, resolved_asset_version

    def _persist_outputs(
        self,
        *,
        bundle: M05SkuInputBundle,
        comment_units: Sequence[CommentUnitRecord],
        unit_links: Sequence[CommentUnitEvidenceLinkRecord],
        sentence_atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
        quality_profile: CommentQualityProfileRecord,
        rule_version: str,
    ) -> dict[str, dict[str, int]]:
        previous_inactive_count = (
            CommentUnitRepository.mark_previous_inactive(
                self.repository,
                bundle.batch_id,
                bundle.sku_code,
                rule_version=rule_version,
            )
            + CommentEvidenceAtomRepository.mark_previous_inactive(
                self.repository,
                bundle.batch_id,
                bundle.sku_code,
                rule_version=rule_version,
            )
            + CommentTopicHintRepository.mark_previous_inactive(
                self.repository,
                bundle.batch_id,
                bundle.sku_code,
                rule_version=rule_version,
            )
            + CommentQualityProfileRepository.mark_previous_inactive(
                self.repository,
                bundle.batch_id,
                bundle.sku_code,
                rule_version=rule_version,
            )
        )
        deleted_link_count = self.repository.delete_current_links_for_sku(
            bundle.batch_id,
            bundle.sku_code,
            rule_version=rule_version,
        )
        write_results = {
            "comment_units": self.repository.bulk_upsert_comment_units(comment_units),
            "unit_links": self.repository.bulk_insert_links(unit_links),
            "sentence_atoms": self.repository.bulk_upsert_atoms(sentence_atoms),
            "topic_hints": self.repository.bulk_upsert_topic_hints(topic_hints),
            "quality_profiles": self.repository.upsert_profile(quality_profile),
        }
        write_summary = {name: _write_summary(result) for name, result in write_results.items()}
        write_summary["previous_outputs_inactivated"] = {
            "created_count": 0,
            "reused_count": 0,
            "updated_count": previous_inactive_count,
        }
        write_summary["unit_links_deleted"] = {
            "created_count": 0,
            "reused_count": 0,
            "updated_count": deleted_link_count,
            "deleted_count": deleted_link_count,
        }
        return write_summary

    def _build_summary(
        self,
        *,
        bundle: M05SkuInputBundle,
        comment_units: Sequence[CommentUnitRecord],
        unit_links: Sequence[CommentUnitEvidenceLinkRecord],
        sentence_atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
        quality_profile: CommentQualityProfileRecord,
        review_issues: Sequence[M05ReviewIssue],
        downstream_impacts: Sequence[M05DownstreamImpact],
        write_summary: Mapping[str, Mapping[str, int]],
        seed_loaded: bool,
        m02_comment_trace_ready: bool,
        topic_match_summary: Mapping[str, int],
        warnings: Sequence[str],
        blocked: bool,
        review_required: bool,
    ) -> dict[str, Any]:
        return {
            "batch_id": bundle.batch_id,
            "sku_code": bundle.sku_code,
            "model_name": bundle.model_name,
            "brand_name": bundle.brand_name,
            "input_evidence_count": len(bundle.evidence_inputs),
            "input_fingerprint": bundle.input_fingerprint,
            "comment_unit_count": len(comment_units),
            "unit_link_count": len(unit_links),
            "evidence_atom_count": len(sentence_atoms),
            "topic_hint_count": len(topic_hints),
            "quality_profile_count": 1,
            "usable_sentence_count": quality_profile.usable_sentence_count,
            "downstream_ready_sku_count": 1 if quality_profile.downstream_ready else 0,
            "review_required_count": 1 if review_required else 0,
            "seed_loaded": seed_loaded,
            "m02_comment_trace_ready": m02_comment_trace_ready,
            "blocked": blocked,
            "review_required": review_required,
            "warnings": list(warnings),
            "topic_match_summary": dict(topic_match_summary),
            "quality_profile_summary": {
                "sample_status": _enum_value(quality_profile.sample_status),
                "comment_usability_score": str(quality_profile.comment_usability_score),
                "warning_flags": list(quality_profile.warning_flags),
                "blocked_reasons": list(quality_profile.blocked_reasons),
                "downstream_ready": quality_profile.downstream_ready,
            },
            "review_issue_codes": [issue.issue_code for issue in review_issues],
            "downstream_impacts": [
                {
                    "target_module": _enum_value(impact.target_module),
                    "impact_level": _enum_value(impact.impact_level),
                    "changed_object_count": impact.changed_object_count,
                    "reason_cn": impact.reason_cn,
                    "evidence_ref_count": len(impact.evidence_refs),
                }
                for impact in downstream_impacts
            ],
            "write_summary": {key: dict(value) for key, value in write_summary.items()},
        }


def _write_summary(result: CommentEvidenceRepositoryWriteResult) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "updated_count": result.updated_count,
    }


def _m02_comment_trace_ready(bundle: M05SkuInputBundle) -> bool:
    for item in bundle.evidence_inputs:
        if _enum_value(item.evidence_type) != Core3EvidenceType.COMMENT_RAW.value:
            continue
        if item.comment_id or item.comment_text_hash or item.source_row_id or item.clean_record_key:
            return True
    return False


def _topic_match_summary(topic_result: Any | None) -> dict[str, int]:
    if topic_result is None:
        return {
            "matched_count": 0,
            "low_confidence_count": 0,
            "blocked_low_value_count": 0,
            "blocked_service_guardrail_count": 0,
            "unknown_atom_count": 0,
        }
    return {
        "matched_count": int(topic_result.matched_count),
        "low_confidence_count": int(topic_result.low_confidence_count),
        "blocked_low_value_count": int(topic_result.blocked_low_value_count),
        "blocked_service_guardrail_count": int(topic_result.blocked_service_guardrail_count),
        "unknown_atom_count": int(topic_result.unknown_atom_count),
    }


def _issue_codes(issues: Sequence[Any]) -> list[str]:
    return [
        str(issue.issue_code)
        for issue in issues
        if getattr(issue, "issue_code", None) is not None and str(issue.issue_code).strip()
    ]


def _unique_values(values: Sequence[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        result.append(normalized)
        seen.add(normalized)
    return result


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))
