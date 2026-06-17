"""Build M04b claim-validation inputs from M06 downstream signals."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from app.services.core3_real_data.claim_comment_enhancement_repositories import (
    ClaimCommentEnhancementRepository,
)
from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    M04bClaimValidationSignalInput,
)
from app.services.core3_real_data.constants import (
    CommentHardSpecPolicy,
    CommentSignalPolarity,
    CommentSignalStrengthLevel,
)
from app.services.core3_real_data.hash_utils import stable_hash


class ClaimValidationSignalInputService:
    def __init__(self, repository: ClaimCommentEnhancementRepository) -> None:
        self.repository = repository

    def load(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
    ) -> tuple[dict[str, list[M04bClaimValidationSignalInput]], dict[str, str]]:
        self.repository.assert_m06_completed(batch_id)
        signals_by_sku: dict[str, list[M04bClaimValidationSignalInput]] = defaultdict(list)
        for row in self.repository.list_claim_validation_signals(batch_id, sku_scope=sku_scope, claim_scope=claim_scope):
            signals_by_sku[row.sku_code].append(_signal_input(row))
        fingerprints = {
            sku_code: stable_hash(
                {
                    "claim_validation_hashes": sorted(item.result_hash for item in signals),
                    "claim_codes": sorted({item.claim_code for item in signals}),
                },
                version="m04b_claim_validation_signal_input_v1",
            )
            for sku_code, signals in signals_by_sku.items()
        }
        return dict(signals_by_sku), fingerprints


def _signal_input(row) -> M04bClaimValidationSignalInput:
    return M04bClaimValidationSignalInput(
        signal_id=row.signal_id,
        sku_code=row.sku_code,
        model_name=row.model_name,
        brand_name=row.brand_name,
        claim_code=row.target_code_hint,
        claim_name=row.target_name_hint,
        claim_group=row.target_group_hint,
        polarity=CommentSignalPolarity(row.polarity),
        mention_count=row.mention_count,
        sentence_count=row.sentence_count,
        valid_comment_unit_count=row.valid_comment_unit_count,
        mention_rate=row.mention_rate,
        positive_count=row.positive_count,
        negative_count=row.negative_count,
        positive_rate=row.positive_rate,
        negative_rate=row.negative_rate,
        signal_score=row.signal_score,
        signal_level=CommentSignalStrengthLevel(row.signal_level),
        specificity_avg=row.specificity_avg,
        evidence_quality_score=row.evidence_quality_score,
        representative_phrases=list(row.representative_phrases or []),
        top_candidate_ids=list(row.top_candidate_ids or []),
        evidence_ids=list(row.evidence_ids or []),
        service_guardrail_flag=row.service_guardrail_flag,
        hard_spec_policy=CommentHardSpecPolicy(row.hard_spec_policy),
        confidence=row.confidence,
        confidence_level=row.confidence_level,
        result_hash=row.result_hash,
    )
