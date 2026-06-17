"""Review policy for M06 comment downstream signals."""

from __future__ import annotations

from decimal import Decimal

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentSignalReviewIssue,
    CommentDownstreamSignalRecord,
    M06SkuInputBundle,
)
from app.services.core3_real_data.constants import (
    CommentSignalReviewReasonCode,
    Core3ReviewSeverity,
)


class CommentSignalReviewPolicy:
    def evaluate(
        self,
        bundle: M06SkuInputBundle,
        signals: list[CommentDownstreamSignalRecord],
    ) -> list[CommentSignalReviewIssue]:
        issues: list[CommentSignalReviewIssue] = []
        if not bundle.quality_profile.downstream_ready:
            issues.append(
                CommentSignalReviewIssue(
                    issue_code=f"M06_{bundle.sku_code}_M05_NOT_READY",
                    reason_code=CommentSignalReviewReasonCode.M05_NOT_READY,
                    severity=Core3ReviewSeverity.HIGH,
                    object_type="sku_comment_signal_profile",
                    sku_code=bundle.sku_code,
                    message_cn="M05 评论质量画像未达到下游可用状态，M06 仅保留空画像或弱提示。",
                    suggestion_cn="先复核 M05 评论去重、低价值和句级证据质量。",
                    confidence=Decimal("0.9000"),
                )
            )
        if bundle.quality_profile.usable_sentence_count == 0:
            issues.append(
                CommentSignalReviewIssue(
                    issue_code=f"M06_{bundle.sku_code}_NO_USABLE_ATOM",
                    reason_code=CommentSignalReviewReasonCode.NO_USABLE_COMMENT_ATOM,
                    severity=Core3ReviewSeverity.HIGH,
                    object_type="comment_evidence_atom",
                    sku_code=bundle.sku_code,
                    message_cn="没有可用于下游的评论句级证据，无法形成评论信号。",
                    suggestion_cn="补充评论数据或复核 M05 低价值阻断规则。",
                    confidence=Decimal("0.9500"),
                )
            )
        if bundle.quality_profile.usable_sentence_count > 0 and not signals:
            issues.append(
                CommentSignalReviewIssue(
                    issue_code=f"M06_{bundle.sku_code}_NO_MATCHED_SIGNAL",
                    reason_code=CommentSignalReviewReasonCode.LOW_CONFIDENCE_SIGNAL,
                    severity=Core3ReviewSeverity.MEDIUM,
                    object_type="comment_downstream_signal",
                    sku_code=bundle.sku_code,
                    message_cn="有可用评论句，但未命中任何下游信号目标。",
                    suggestion_cn="复核评论主题 seed 或补充本地样例中任务/客群/战场相关表达。",
                    confidence=Decimal("0.7000"),
                )
            )
        service_guardrail_count = sum(1 for signal in signals if signal.service_guardrail_flag)
        if service_guardrail_count:
            issues.append(
                CommentSignalReviewIssue(
                    issue_code=f"M06_{bundle.sku_code}_SERVICE_GUARDRAIL",
                    reason_code=CommentSignalReviewReasonCode.SERVICE_GUARDRAIL,
                    severity=Core3ReviewSeverity.LOW,
                    object_type="comment_downstream_signal",
                    sku_code=bundle.sku_code,
                    message_cn=f"该 SKU 有 {service_guardrail_count} 条服务隔离信号，只能用于服务保障或安装相关分析。",
                    suggestion_cn="后续 M04b 不得把服务评论增强为产品技术卖点。",
                    confidence=Decimal("0.8500"),
                    review_required=False,
                )
            )
        return issues
