"""M04b review issue policy."""

from __future__ import annotations

from app.services.core3_real_data.claim_comment_enhancement_schemas import (
    ClaimCommentReviewIssueRecord,
    ClaimCommentValidationRecord,
    SkuClaimActivationRecord,
)
from app.services.core3_real_data.constants import (
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    ClaimCommentDownstreamPolicy,
    ClaimCommentEnhancedType,
    ClaimCommentIssueSeverity,
    ClaimCommentIssueType,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


class ClaimCommentReviewPolicy:
    def evaluate(
        self,
        validation: ClaimCommentValidationRecord,
        activation: SkuClaimActivationRecord,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str = CORE3_M04B_RULE_VERSION,
        seed_version: str = CORE3_M04B_SEED_VERSION,
    ) -> list[ClaimCommentReviewIssueRecord]:
        issues: list[ClaimCommentReviewIssueRecord] = []
        if validation.comment_only_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.COMMENT_ONLY,
                    ClaimCommentIssueSeverity.REVIEW_REQUIRED,
                    "评论提到了该卖点，但上游没有参数或宣传基础，不能自动作为高置信卖点。",
                    "人工复核是否需要补充参数或宣传证据，未补齐前下游只能低置信使用。",
                    ClaimCommentDownstreamPolicy.REQUIRE_APPROVAL,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if validation.comment_only_flag and validation.hard_spec_protection_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.SPEC_CLAIMED_BY_COMMENT,
                    ClaimCommentIssueSeverity.BLOCKED,
                    "评论只能说明体验感知，不能证明亮度、分区、接口、面板等硬规格。",
                    "补充结构化参数证据前，不允许用该评论激活硬规格卖点。",
                    ClaimCommentDownstreamPolicy.BLOCK_DOWNSTREAM,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if validation.service_guardrail_flag and validation.m04b_claim_type != ClaimCommentEnhancedType.SERVICE:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.SERVICE_MISMATCH,
                    ClaimCommentIssueSeverity.BLOCKED,
                    "安装、物流或售后评论不能增强画质、游戏、护眼、音效等产品卖点。",
                    "该评论信号只能保留为服务体验证据，不能进入产品卖点激活。",
                    ClaimCommentDownstreamPolicy.BLOCK_DOWNSTREAM,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if validation.contradiction_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.COMMENT_CONTRADICTION,
                    ClaimCommentIssueSeverity.REVIEW_REQUIRED,
                    "基础卖点与评论体验出现冲突，需确认该卖点是否应降权。",
                    "检查负向评论是否集中且与同一体验相关。",
                    ClaimCommentDownstreamPolicy.REQUIRE_APPROVAL,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if validation.weak_perception_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.WEAK_PERCEPTION,
                    ClaimCommentIssueSeverity.WARNING,
                    "基础卖点存在，但评论侧用户感知偏弱。",
                    "下游任务、客群和战场推导应降低评论体验权重。",
                    ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if activation.missing_structured_claim_flag and validation.comment_effect == "enhance":
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.MISSING_STRUCTURED_CLAIM_ENHANCED,
                    ClaimCommentIssueSeverity.WARNING,
                    "该 SKU 缺结构化宣传卖点，但评论增强了体验感知，报告必须提示数据缺口。",
                    "补充结构化卖点数据前，不得把评论写成宣传证据。",
                    ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if activation.param_only_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.PARAM_ONLY_CORE_CLAIM,
                    ClaimCommentIssueSeverity.WARNING,
                    "该卖点主要来自参数支撑，缺宣传卖点闭环，默认最高中置信。",
                    "下游可以使用，但必须保留 param-only 风险。",
                    ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if activation.promo_only_flag:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.PROMO_ONLY_PARAM_MISSING,
                    ClaimCommentIssueSeverity.WARNING,
                    "该卖点主要来自宣传文本，缺少参数支撑。",
                    "涉及硬规格或竞品评分时需补参数证据。",
                    ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        if activation.value_requires_market_validation:
            issues.append(
                self._issue(
                    validation,
                    activation,
                    ClaimCommentIssueType.VALUE_REQUIRES_MARKET_VALIDATION,
                    ClaimCommentIssueSeverity.WARNING,
                    "评论体现了价值感，但价格竞争力仍需市场价格和销量验证。",
                    "M11.5/M13 必须结合市场证据后再使用。",
                    ClaimCommentDownstreamPolicy.CONTINUE_WITH_WARNING,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    seed_version=seed_version,
                )
            )
        return issues

    def _issue(
        self,
        validation: ClaimCommentValidationRecord,
        activation: SkuClaimActivationRecord,
        issue_type: ClaimCommentIssueType,
        severity: ClaimCommentIssueSeverity,
        business_note: str,
        suggested_action: str,
        downstream_policy: ClaimCommentDownstreamPolicy,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        seed_version: str,
    ) -> ClaimCommentReviewIssueRecord:
        key_payload = {
            "batch_id": validation.batch_id,
            "sku_code": validation.sku_code,
            "claim_code": validation.claim_code,
            "issue_type": issue_type.value,
            "rule_version": rule_version,
            "seed_version": seed_version,
        }
        issue_key = stable_hash(key_payload, version="m04b_issue_key_v1")
        result_hash = stable_hash(
            {
                **key_payload,
                "severity": severity.value,
                "business_note": business_note,
                "evidence_ids": sorted(activation.evidence_ids),
                "comment_signal_ids": sorted(validation.comment_signal_ids),
            },
            version="m04b_issue_result_v1",
        )
        return ClaimCommentReviewIssueRecord(
            issue_id=f"m04bissue_{issue_key.split(':')[-1][:32]}",
            project_id=validation.project_id,
            category_code=validation.category_code,
            batch_id=validation.batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=validation.sku_code,
            model_name=validation.model_name,
            brand_name=validation.brand_name,
            issue_key=issue_key,
            claim_activation_id=activation.claim_activation_id,
            claim_comment_validation_id=validation.claim_comment_validation_id,
            claim_activation_base_id=validation.claim_activation_base_id,
            claim_code=validation.claim_code,
            claim_name=validation.claim_name,
            issue_type=issue_type,
            severity=severity,
            business_note=business_note,
            technical_note="M04b 自动规则生成，评论只作为体验验证证据。",
            suggested_action=suggested_action,
            downstream_policy=downstream_policy,
            evidence_ids=activation.evidence_ids,
            comment_signal_ids=validation.comment_signal_ids,
            quality_flags=activation.quality_flags,
            rule_version=rule_version,
            seed_version=seed_version,
            input_fingerprint=validation.input_fingerprint,
            result_hash=result_hash,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED,
            review_reason_json={"issue_type": issue_type.value, "severity": severity.value},
        )
