"""M04b claim type and downstream usage policy helpers."""

from __future__ import annotations

from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimDefinitionInput,
    ClaimTypePolicy,
)
from app.services.core3_real_data.constants import ClaimCommentEnhancedType


class ClaimTypePolicyService:
    def __init__(self, claims: dict[str, ClaimDefinitionInput], policies: dict[str, ClaimTypePolicy]) -> None:
        self.claims = claims
        self.policies = policies

    def claim(self, claim_code: str) -> ClaimDefinitionInput | None:
        return self.claims.get(claim_code)

    def policy(self, claim_code: str) -> ClaimTypePolicy:
        if claim_code in self.policies:
            return self.policies[claim_code]
        return ClaimTypePolicy(
            claim_code=claim_code,
            m04b_claim_type=ClaimCommentEnhancedType.UNKNOWN,
            base_weight=0.8,
            comment_weight=0.2,
            risk_penalty_weight=0.2,
        )

    def downstream_policy_json(
        self,
        *,
        claim_code: str,
        param_only_flag: bool,
        comment_only_flag: bool,
        missing_structured_claim_flag: bool,
        value_requires_market_validation: bool,
        hard_spec_protection_flag: bool,
    ) -> dict[str, object]:
        return {
            "M08": {"allowed": True, "usage": "sku_claim_signal", "keep_risk_flags": True},
            "M09": {
                "allowed": True,
                "max_confidence_if_param_only": "medium" if param_only_flag else None,
                "blocked_if_comment_only": comment_only_flag,
            },
            "M10": {
                "allowed": True,
                "max_confidence_if_comment_only": "low" if comment_only_flag else None,
            },
            "M11": {
                "allowed": True,
                "requires_task_or_market_support": True,
                "weak_if_missing_structured_claim": missing_structured_claim_flag,
            },
            "M11_5": {
                "allowed": True,
                "value_layer_required": True,
                "market_validation_required": value_requires_market_validation,
            },
            "M13": {
                "allowed": True,
                "must_keep_evidence_risk": True,
                "market_validation_required": value_requires_market_validation,
            },
            "M15": {
                "display_data_gap": missing_structured_claim_flag,
                "display_comment_as_experience_not_spec": hard_spec_protection_flag,
            },
            "claim_code": claim_code,
        }
