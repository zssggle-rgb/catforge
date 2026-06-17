"""M04b claim comment enhancement orchestration service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.services.core3_real_data.claim_activation_final_scorer import ClaimActivationFinalScorer
from app.services.core3_real_data.claim_base_input_service import ClaimBaseInputService
from app.services.core3_real_data.claim_comment_enhancement_repositories import (
    ClaimCommentEnhancementRepository,
    ClaimCommentReviewIssueRepository,
    SkuClaimActivationRepository,
    SkuClaimCommentValidationRepository,
)
from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimCommentReviewIssueRecord,
    ClaimCommentValidationRecord,
    M04bSkuInputBundle,
    SkuClaimActivationRecord,
)
from app.services.core3_real_data.claim_comment_review_policy import ClaimCommentReviewPolicy
from app.services.core3_real_data.claim_comment_seed_loader import ClaimCommentSeedLoader
from app.services.core3_real_data.claim_comment_validation_builder import ClaimCommentValidationBuilder
from app.services.core3_real_data.claim_type_policy_service import ClaimTypePolicyService
from app.services.core3_real_data.claim_validation_signal_input_service import (
    ClaimValidationSignalInputService,
)
from app.services.core3_real_data.constants import CORE3_M04B_RULE_VERSION, CORE3_M04B_SEED_VERSION
from app.services.core3_real_data.hash_utils import stable_hash


@dataclass(frozen=True)
class ClaimCommentEnhancementServiceResult:
    bundles: list[M04bSkuInputBundle]
    validations: list[ClaimCommentValidationRecord]
    activations: list[SkuClaimActivationRecord]
    issues: list[ClaimCommentReviewIssueRecord]
    warnings: list[str] = field(default_factory=list)
    write_summary: dict[str, dict[str, int]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def input_count(self) -> int:
        return sum(len(bundle.base_claims) + len(bundle.claim_validation_signals) for bundle in self.bundles)

    @property
    def output_count(self) -> int:
        return len(self.validations) + len(self.activations) + len(self.issues)

    @property
    def created_output_count(self) -> int:
        return sum(item.get("created_count", 0) for item in self.write_summary.values())


class ClaimCommentEnhancementService:
    def __init__(self, repository: ClaimCommentEnhancementRepository) -> None:
        self.repository = repository

    def run_batch(
        self,
        *,
        batch_id: str,
        run_id: str | None = None,
        module_run_id: str | None = None,
        sku_scope: Sequence[str] = (),
        claim_scope: Sequence[str] = (),
        rule_version: str = CORE3_M04B_RULE_VERSION,
        seed_version: str = CORE3_M04B_SEED_VERSION,
    ) -> ClaimCommentEnhancementServiceResult:
        seed_result = ClaimCommentSeedLoader().load()
        policy_service = ClaimTypePolicyService(seed_result.claims, seed_result.policies)
        statuses_by_sku, base_by_sku, base_fingerprints = ClaimBaseInputService(self.repository).load(
            batch_id,
            sku_scope=sku_scope,
            claim_scope=claim_scope,
        )
        signals_by_sku, signal_fingerprints = ClaimValidationSignalInputService(self.repository).load(
            batch_id,
            sku_scope=sku_scope,
            claim_scope=claim_scope,
        )
        sku_codes = sorted(set(base_by_sku) | set(signals_by_sku))
        bundles = [
            _bundle(
                project_id=self.repository.project_id,
                category_code=self.repository.category_code.value,
                batch_id=batch_id,
                sku_code=sku_code,
                source_status=statuses_by_sku.get(sku_code),
                base_claims=base_by_sku.get(sku_code, []),
                signals=signals_by_sku.get(sku_code, []),
                base_fingerprint=base_fingerprints.get(sku_code),
                signal_fingerprint=signal_fingerprints.get(sku_code),
                seed_hash=seed_result.seed_content_hash,
                rule_version=rule_version,
                seed_version=seed_version,
            )
            for sku_code in sku_codes
        ]

        validation_builder = ClaimCommentValidationBuilder(policy_service)
        scorer = ClaimActivationFinalScorer(policy_service)
        review_policy = ClaimCommentReviewPolicy()
        validations: list[ClaimCommentValidationRecord] = []
        activations: list[SkuClaimActivationRecord] = []
        issues: list[ClaimCommentReviewIssueRecord] = []
        for bundle in bundles:
            bundle_validations = validation_builder.build(
                bundle,
                run_id=run_id,
                module_run_id=module_run_id,
                rule_version=rule_version,
                seed_version=seed_version,
            )
            for validation in bundle_validations:
                activation = scorer.score(
                    validation,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
                validations.append(validation)
                activations.append(activation)
                issues.extend(
                    review_policy.evaluate(
                        validation,
                        activation,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        rule_version=rule_version,
                        seed_version=seed_version,
                    )
                )

        write_summary = self._persist(
            batch_id=batch_id,
            sku_codes=sku_codes,
            validations=validations,
            activations=activations,
            issues=issues,
            rule_version=rule_version,
        )
        warnings = _warnings(bundles, validations, activations, issues)
        summary = {
            "batch_id": batch_id,
            "sku_count": len(bundles),
            "validation_count": len(validations),
            "activation_count": len(activations),
            "issue_count": len(issues),
            "review_required_count": sum(1 for activation in activations if activation.review_required),
            "blocked_claim_count": sum(1 for validation in validations if validation.comment_effect == "blocked"),
            "comment_enhanced_count": sum(1 for activation in activations if activation.activation_basis == "comment_enhanced"),
            "param_only_count": sum(1 for activation in activations if activation.param_only_flag),
            "missing_structured_claim_count": sum(1 for activation in activations if activation.missing_structured_claim_flag),
            "comment_only_hint_count": sum(1 for activation in activations if activation.comment_only_flag),
            "value_requires_market_validation_count": sum(1 for activation in activations if activation.value_requires_market_validation),
            "claim_type_counts": _counts([str(activation.m04b_claim_type) for activation in activations]),
            "activation_level_counts": _counts([str(activation.activation_level) for activation in activations]),
            "seed_content_hash": seed_result.seed_content_hash,
            "seed_claim_type_counts": seed_result.claim_type_counts,
            "write_summary": write_summary,
            "boundary_note": "M04b 只生成最终卖点激活和评论验证风险，不生成任务、客群、战场或竞品结论。",
        }
        return ClaimCommentEnhancementServiceResult(
            bundles=bundles,
            validations=validations,
            activations=activations,
            issues=issues,
            warnings=warnings,
            write_summary=write_summary,
            summary=summary,
        )

    def _persist(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        validations: list[ClaimCommentValidationRecord],
        activations: list[SkuClaimActivationRecord],
        issues: list[ClaimCommentReviewIssueRecord],
        rule_version: str,
    ) -> dict[str, dict[str, int]]:
        for sku_code in sku_codes:
            SkuClaimCommentValidationRepository.mark_previous_inactive(
                self.repository,
                batch_id,
                sku_code,
                rule_version=rule_version,
            )
            SkuClaimActivationRepository.mark_previous_inactive(
                self.repository,
                batch_id,
                sku_code,
                rule_version=rule_version,
            )
            ClaimCommentReviewIssueRepository.mark_previous_inactive(
                self.repository,
                batch_id,
                sku_code,
                rule_version=rule_version,
            )
        validation_result = self.repository.bulk_upsert_validations(validations)
        activation_result = self.repository.bulk_upsert_activations(activations)
        issue_result = self.repository.bulk_upsert_issues(issues)
        return {
            "claim_comment_validation": _write_counts(validation_result),
            "sku_claim_activation": _write_counts(activation_result),
            "claim_comment_review_issue": _write_counts(issue_result),
        }


def _bundle(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    source_status,
    base_claims,
    signals,
    base_fingerprint: str | None,
    signal_fingerprint: str | None,
    seed_hash: str,
    rule_version: str,
    seed_version: str,
) -> M04bSkuInputBundle:
    model_name = next((item.model_name for item in base_claims if item.model_name), None)
    if model_name is None:
        model_name = next((item.model_name for item in signals if item.model_name), None)
    brand_name = next((item.brand_name for item in signals if item.brand_name), None)
    fingerprint = stable_hash(
        {
            "batch_id": batch_id,
            "sku_code": sku_code,
            "base_fingerprint": base_fingerprint,
            "signal_fingerprint": signal_fingerprint,
            "seed_hash": seed_hash,
            "rule_version": rule_version,
            "seed_version": seed_version,
        },
        version="m04b_sku_input_bundle_v1",
    )
    return M04bSkuInputBundle(
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        sku_code=sku_code,
        model_name=model_name,
        brand_name=brand_name,
        source_status=source_status,
        base_claims=base_claims,
        claim_validation_signals=signals,
        input_fingerprint=fingerprint,
    )


def _warnings(
    bundles: list[M04bSkuInputBundle],
    validations: list[ClaimCommentValidationRecord],
    activations: list[SkuClaimActivationRecord],
    issues: list[ClaimCommentReviewIssueRecord],
) -> list[str]:
    warnings: list[str] = []
    if not bundles:
        warnings.append("m04b_no_sku_input")
    if any(validation.comment_only_flag for validation in validations):
        warnings.append("m04b_comment_only_hint")
    if any(activation.param_only_flag for activation in activations):
        warnings.append("m04b_param_only_claim")
    if any(activation.missing_structured_claim_flag for activation in activations):
        warnings.append("m04b_missing_structured_claim")
    if issues:
        warnings.append("m04b_review_issue_generated")
    return sorted(set(warnings))


def _write_counts(result) -> dict[str, int]:
    return {
        "created_count": result.created_count,
        "reused_count": result.reused_count,
        "updated_count": result.updated_count,
    }


def _counts(values: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for value in values:
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))
