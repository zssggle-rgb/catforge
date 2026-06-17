"""Build M04b base-claim inputs from M04a outputs."""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from app.services.core3_real_data.claim_comment_enhancement_repositories import (
    ClaimCommentEnhancementRepository,
)
from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    M04bClaimBaseInput,
    M04bClaimSourceStatusInput,
)
from app.services.core3_real_data.hash_utils import stable_hash


class ClaimBaseInputService:
    def __init__(self, repository: ClaimCommentEnhancementRepository) -> None:
        self.repository = repository

    def load(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
    ) -> tuple[dict[str, M04bClaimSourceStatusInput], dict[str, list[M04bClaimBaseInput]], dict[str, str]]:
        self.repository.assert_m04a_completed(batch_id)
        statuses = {
            status.sku_code: _source_status_input(status)
            for status in self.repository.list_source_statuses(batch_id, sku_scope=sku_scope)
        }
        base_claims_by_sku: dict[str, list[M04bClaimBaseInput]] = defaultdict(list)
        for row in self.repository.list_base_claims(batch_id, sku_scope=sku_scope, claim_scope=claim_scope):
            base_claims_by_sku[row.sku_code].append(_base_input(row))
        fingerprints = {
            sku_code: stable_hash(
                {
                    "source_status": statuses.get(sku_code).status_hash if statuses.get(sku_code) else None,
                    "base_activation_hashes": sorted(item.activation_hash for item in base_claims),
                },
                version="m04b_base_input_v1",
            )
            for sku_code, base_claims in base_claims_by_sku.items()
        }
        return statuses, dict(base_claims_by_sku), fingerprints


def _source_status_input(row) -> M04bClaimSourceStatusInput:
    return M04bClaimSourceStatusInput(
        claim_source_status_id=row.claim_source_status_id,
        sku_code=row.sku_code,
        claim_source_status=row.claim_source_status,
        structured_claim_count=row.structured_claim_count,
        param_only_claim_count=row.param_only_claim_count,
        missing_signals=list(row.missing_signals or []),
        conflict_summary_json=dict(row.conflict_summary_json or {}),
        status_hash=row.status_hash,
    )


def _base_input(row) -> M04bClaimBaseInput:
    return M04bClaimBaseInput(
        claim_activation_base_id=row.claim_activation_base_id,
        sku_code=row.sku_code,
        model_name=row.model_name,
        claim_code=row.claim_code,
        claim_name=row.claim_name,
        claim_group=row.claim_group,
        claim_type=row.claim_type,
        param_score=row.param_score,
        promo_score=row.promo_score,
        base_activation_score=row.base_activation_score,
        base_activation_level=row.activation_level,
        base_activation_basis=row.activation_basis,
        missing_signals=list(row.missing_signals or []),
        conflict_flags=list(row.conflict_flags or []),
        confidence=row.confidence,
        confidence_level=row.confidence_level,
        evidence_ids=list(row.evidence_ids or []),
        param_evidence_ids=list(row.param_evidence_ids or []),
        promo_evidence_ids=list(row.promo_evidence_ids or []),
        quality_evidence_ids=list(row.quality_evidence_ids or []),
        activation_hash=row.activation_hash,
    )
