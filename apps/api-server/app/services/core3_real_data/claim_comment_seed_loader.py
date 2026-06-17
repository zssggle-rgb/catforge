"""M04b seed loader for standard-claim comment enhancement policy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.services.core3_real_data.base_claim_seed_loader import StdClaimSeedLoader, StdClaimSeedValidationError
from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimDefinitionInput,
    ClaimTypePolicy,
)
from app.services.core3_real_data.constants import (
    CORE3_M04B_SEED_VERSION,
    ClaimCommentEnhancedType,
)
from app.services.core3_real_data.hash_utils import stable_hash


TECHNICAL_HARD_CLAIMS = frozenset(
    {
        "CLAIM_MINI_LED_BACKLIGHT",
        "CLAIM_OLED_SELF_LIT",
        "CLAIM_QLED_WIDE_COLOR",
        "CLAIM_HIGH_BRIGHTNESS_HDR",
        "CLAIM_FINE_LOCAL_DIMMING",
        "CLAIM_HDMI_2_1_GAMING",
    }
)
TECHNICAL_EXPERIENCE_MIXED_CLAIMS = frozenset(
    {
        "CLAIM_HIGH_REFRESH_RATE",
        "CLAIM_GAMING_LOW_LATENCY",
        "CLAIM_EYE_CARE_COMFORT",
        "CLAIM_IMMERSIVE_AUDIO",
        "CLAIM_DOLBY_CINEMA_AUDIO",
        "CLAIM_SMART_VOICE_EASE",
        "CLAIM_NO_AD_OR_CLEAN_SYSTEM",
    }
)
EXPERIENCE_SCENARIO_CLAIMS = frozenset(
    {
        "CLAIM_LARGE_SCREEN_IMMERSION",
        "CLAIM_SPORTS_MOTION_SMOOTH",
        "CLAIM_ELDER_FRIENDLY_SMART",
        "CLAIM_THIN_DESIGN",
    }
)
SERVICE_CLAIMS = frozenset({"CLAIM_INSTALLATION_SERVICE_ASSURANCE"})
VALUE_CLAIMS = frozenset({"CLAIM_VALUE_FOR_MONEY", "CLAIM_ENERGY_SAVING"})


@dataclass(frozen=True)
class ClaimCommentSeedLoadResult:
    claims: dict[str, ClaimDefinitionInput]
    policies: dict[str, ClaimTypePolicy]
    seed_version: str
    asset_version: str
    seed_content_hash: str
    claim_type_counts: dict[str, int]


class ClaimCommentSeedLoader:
    def __init__(self, seed_path: Path | str | None = None) -> None:
        self.seed_path = seed_path

    def load(self) -> ClaimCommentSeedLoadResult:
        try:
            loaded = StdClaimSeedLoader(self.seed_path).load()
        except StdClaimSeedValidationError:
            raise

        claims: dict[str, ClaimDefinitionInput] = {}
        policies: dict[str, ClaimTypePolicy] = {}
        for claim in loaded.seed.standard_claims:
            claim_type = infer_m04b_claim_type(claim.claim_code, str(claim.claim_group), str(claim.claim_type))
            definition = ClaimDefinitionInput(
                claim_code=claim.claim_code,
                claim_name=claim.claim_name,
                claim_group=str(claim.claim_group),
                claim_type=str(claim.claim_type),
                m04b_claim_type=claim_type,
                hard_spec_protection_flag=claim_type == ClaimCommentEnhancedType.TECHNICAL_HARD,
                value_requires_market_validation=claim_type == ClaimCommentEnhancedType.VALUE,
                service_claim_flag=claim_type == ClaimCommentEnhancedType.SERVICE,
                keywords=claim.keywords,
                mapped_task_codes=claim.mapped_task_codes,
                mapped_battlefield_codes=claim.mapped_battlefield_codes,
            )
            policy = policy_for_claim(definition)
            claims[claim.claim_code] = definition
            policies[claim.claim_code] = policy

        seed_hash = stable_hash(
            {
                "seed_version": CORE3_M04B_SEED_VERSION,
                "claims": {
                    code: claims[code].model_dump(mode="json")
                    for code in sorted(claims)
                },
                "policy_version": "m04b_claim_type_policy_v1",
            },
            version="m04b_claim_comment_seed_v1",
        )
        claim_type_counts: dict[str, int] = {}
        for definition in claims.values():
            claim_type_counts[str(definition.m04b_claim_type)] = claim_type_counts.get(str(definition.m04b_claim_type), 0) + 1
        return ClaimCommentSeedLoadResult(
            claims=claims,
            policies=policies,
            seed_version=CORE3_M04B_SEED_VERSION,
            asset_version=loaded.asset_version or CORE3_M04B_SEED_VERSION,
            seed_content_hash=seed_hash,
            claim_type_counts=dict(sorted(claim_type_counts.items())),
        )


def infer_m04b_claim_type(claim_code: str, claim_group: str, claim_type: str) -> ClaimCommentEnhancedType:
    if claim_code in TECHNICAL_HARD_CLAIMS:
        return ClaimCommentEnhancedType.TECHNICAL_HARD
    if claim_code in TECHNICAL_EXPERIENCE_MIXED_CLAIMS:
        return ClaimCommentEnhancedType.TECHNICAL_EXPERIENCE_MIXED
    if claim_code in EXPERIENCE_SCENARIO_CLAIMS:
        return ClaimCommentEnhancedType.EXPERIENCE_SCENARIO
    if claim_code in SERVICE_CLAIMS or claim_group == "service":
        return ClaimCommentEnhancedType.SERVICE
    if claim_code in VALUE_CLAIMS or claim_group == "value":
        return ClaimCommentEnhancedType.VALUE
    if claim_type in {"technical", "mixed"}:
        return ClaimCommentEnhancedType.TECHNICAL_EXPERIENCE_MIXED
    if claim_type in {"experience", "design"}:
        return ClaimCommentEnhancedType.EXPERIENCE_SCENARIO
    return ClaimCommentEnhancedType.UNKNOWN


def policy_for_claim(definition: ClaimDefinitionInput) -> ClaimTypePolicy:
    weights = {
        ClaimCommentEnhancedType.TECHNICAL_HARD: (Decimal("0.85"), Decimal("0.15"), Decimal("0.20")),
        ClaimCommentEnhancedType.TECHNICAL_EXPERIENCE_MIXED: (Decimal("0.70"), Decimal("0.30"), Decimal("0.25")),
        ClaimCommentEnhancedType.EXPERIENCE_SCENARIO: (Decimal("0.55"), Decimal("0.45"), Decimal("0.30")),
        ClaimCommentEnhancedType.SERVICE: (Decimal("0.40"), Decimal("0.60"), Decimal("0.35")),
        ClaimCommentEnhancedType.VALUE: (Decimal("0.70"), Decimal("0.30"), Decimal("0.20")),
        ClaimCommentEnhancedType.UNKNOWN: (Decimal("0.80"), Decimal("0.20"), Decimal("0.20")),
    }
    base_weight, comment_weight, risk_weight = weights[ClaimCommentEnhancedType(definition.m04b_claim_type)]
    return ClaimTypePolicy(
        claim_code=definition.claim_code,
        m04b_claim_type=definition.m04b_claim_type,
        base_weight=base_weight,
        comment_weight=comment_weight,
        risk_penalty_weight=risk_weight,
        hard_spec_protection_flag=definition.hard_spec_protection_flag,
        value_requires_market_validation=definition.value_requires_market_validation,
        service_claim_flag=definition.service_claim_flag,
    )
