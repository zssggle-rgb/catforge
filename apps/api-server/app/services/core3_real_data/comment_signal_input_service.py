"""Input assembly for M06 comment downstream signal extraction."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from app.models import entities
from app.services.core3_real_data.comment_downstream_signal_repositories import M06CommentInputRepository
from app.services.core3_real_data.comment_downstream_signal_schemas import (
    M06CommentAtomInput,
    M06QualityProfileInput,
    M06SkuInputBundle,
    M06TopicHintInput,
)
from app.services.core3_real_data.hash_utils import stable_hash


class CommentSignalInputService:
    def __init__(self, repository: M06CommentInputRepository) -> None:
        self.repository = repository

    def list_sku_bundles(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        seed_content_hash: str,
        rule_version: str,
    ) -> list[M06SkuInputBundle]:
        self.repository.assert_m05_completed(batch_id)
        sku_codes = self.repository.list_ready_sku_codes(batch_id, sku_scope)
        return [
            self.get_sku_bundle(
                batch_id,
                sku_code,
                seed_content_hash=seed_content_hash,
                rule_version=rule_version,
            )
            for sku_code in sku_codes
        ]

    def get_sku_bundle(
        self,
        batch_id: str,
        sku_code: str,
        *,
        seed_content_hash: str,
        rule_version: str,
    ) -> M06SkuInputBundle:
        profile = self.repository.get_comment_quality_profile(batch_id, sku_code)
        if profile is None:
            raise ValueError(f"M05 comment quality profile not found for sku: {sku_code}")
        atoms = self.repository.list_usable_comment_atoms(batch_id, sku_code)
        topic_hints = self.repository.list_topic_hints_for_atoms(
            batch_id,
            sku_code,
            [atom.comment_evidence_id for atom in atoms],
        )
        hints_by_atom: dict[str, list[M06TopicHintInput]] = defaultdict(list)
        for row in topic_hints:
            hints_by_atom[row.comment_evidence_id].append(_topic_hint_input(row))
        atom_inputs = [_atom_input(row) for row in atoms]
        quality_input = _quality_profile_input(profile)
        input_fingerprint = stable_hash(
            {
                "batch_id": batch_id,
                "sku_code": sku_code,
                "profile_hash": profile.result_hash,
                "atom_hashes": sorted(atom.result_hash for atom in atoms),
                "topic_hashes": sorted(topic.result_hash for topic in topic_hints),
                "seed_content_hash": seed_content_hash,
                "rule_version": rule_version,
            },
            version="m06_input_fingerprint_v1",
        )
        return M06SkuInputBundle(
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            sku_code=sku_code,
            model_name=profile.model_name,
            brand_name=profile.brand_name,
            quality_profile=quality_input,
            atoms=atom_inputs,
            topic_hints_by_atom=dict(hints_by_atom),
            input_fingerprint=input_fingerprint,
        )


def _atom_input(row: entities.Core3CommentEvidenceAtom) -> M06CommentAtomInput:
    source_m02_ids = _dedupe(
        [
            *list(row.source_sentence_evidence_ids or []),
            *list(row.source_comment_evidence_ids or []),
            *list(row.source_dimension_evidence_ids or []),
            *list(row.source_quality_evidence_ids or []),
        ]
    )
    return M06CommentAtomInput(
        comment_evidence_id=row.comment_evidence_id,
        comment_unit_id=row.comment_unit_id,
        sku_code=row.sku_code,
        model_name=row.model_name,
        brand_name=row.brand_name,
        comment_text_hash=row.comment_text_hash,
        sentence_hash=row.sentence_hash,
        sentence_text=row.sentence_text,
        normalized_sentence_text=row.normalized_sentence_text,
        specificity_score=row.specificity_score,
        sentiment_hint=row.sentiment_hint,
        domain_hints=list(row.domain_hints or []),
        primary_domain_hint=row.primary_domain_hint,
        low_value_flag=row.low_value_flag,
        duplicate_group_id=row.duplicate_group_id,
        quality_flags=list(row.downstream_block_reasons or []) + list(row.low_value_reasons or []),
        source_m05_evidence_ids=[row.comment_evidence_id],
        source_m02_evidence_ids=source_m02_ids,
        result_hash=row.result_hash,
    )


def _topic_hint_input(row: entities.Core3CommentTopicHint) -> M06TopicHintInput:
    return M06TopicHintInput(
        topic_hint_id=row.topic_hint_id,
        comment_evidence_id=row.comment_evidence_id,
        comment_unit_id=row.comment_unit_id,
        topic_code=row.topic_code,
        topic_name=row.topic_name,
        topic_group=row.topic_group,
        matched_terms=list(row.matched_terms or []),
        polarity_hint=row.polarity_hint,
        topic_confidence=row.topic_confidence,
        service_guardrail_flag=row.service_guardrail_flag,
        mapped_claim_codes_snapshot=list(row.mapped_claim_codes_snapshot or []),
        mapped_task_codes_snapshot=list(row.mapped_task_codes_snapshot or []),
        mapped_battlefield_codes_snapshot=list(row.mapped_battlefield_codes_snapshot or []),
        result_hash=row.result_hash,
    )


def _quality_profile_input(row: entities.Core3CommentQualityProfile) -> M06QualityProfileInput:
    return M06QualityProfileInput(
        sku_code=row.sku_code,
        model_name=row.model_name,
        brand_name=row.brand_name,
        comment_unit_count=row.comment_unit_count,
        usable_sentence_count=row.usable_sentence_count,
        sample_status=row.sample_status,
        comment_usability_score=row.comment_usability_score,
        warning_flags=list(row.warning_flags or []),
        blocked_reasons=list(row.blocked_reasons or []),
        downstream_ready=row.downstream_ready,
        result_hash=row.result_hash,
    )


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
