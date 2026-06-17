"""M05 comment evidence review policy.

This policy consumes M05 quality profiles, sentence atoms, and weak topic hints
to produce review issues and downstream impact hints. It does not mutate M05
records and does not create downstream business conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentQualityProfileRecord,
    M05DownstreamImpact,
    M05ReviewIssue,
    TopicHintRecord,
)
from app.services.core3_real_data.constants import (
    CommentDomainHint,
    CommentReviewReasonCode,
    CommentSampleStatus,
    CommentSentimentHint,
    CommentTopicHintStatus,
    Core3ModuleCode,
    Core3ReviewSeverity,
    Core3SourceImpactLevel,
)


TARGET_SKU_EXPECTED_COMMENT_UNITS = {"TV00029115": 1648}
TARGET_SKU_LOW_RATIO = Decimal("0.50")
TARGET_SKU_MIN_LIMITED_UNITS = 80
NEGATIVE_REVIEW_THRESHOLD = Decimal("0.150000")
SENTIMENT_CONFLICT_REVIEW_THRESHOLD = Decimal("0.100000")
HIGH_CONFIDENCE_TOPIC_THRESHOLD = Decimal("0.7500")

PRODUCT_DOMAINS = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value,
    CommentDomainHint.PRODUCT_RISK.value,
    CommentDomainHint.MARKET_PERCEPTION.value,
}
SERVICE_DOMAINS = {
    CommentDomainHint.SERVICE_EXPERIENCE.value,
    CommentDomainHint.LOGISTICS_INSTALLATION.value,
}


@dataclass(frozen=True)
class CommentEvidenceReviewPolicyResult:
    review_issues: list[M05ReviewIssue] = field(default_factory=list)
    downstream_impacts: list[M05DownstreamImpact] = field(default_factory=list)
    blocked: bool = False
    review_required: bool = False
    warning_count: int = 0
    blocker_count: int = 0


@dataclass(frozen=True)
class _IssueSpec:
    issue_code: str
    reason_code: CommentReviewReasonCode
    severity: Core3ReviewSeverity
    object_type: str
    object_id: str | None
    sku_code: str | None
    evidence_refs: list[str]
    message_cn: str
    suggestion_cn: str | None
    confidence: Decimal | None = None


class CommentEvidenceReviewPolicy:
    def evaluate(
        self,
        *,
        profile: CommentQualityProfileRecord,
        sentence_atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
        seed_loaded: bool = True,
        m02_completed: bool = True,
        m02_comment_trace_ready: bool = True,
        target_sku_expected_comment_units: Mapping[str, int] | None = None,
    ) -> CommentEvidenceReviewPolicyResult:
        atoms = [atom for atom in sentence_atoms if atom.sku_code == profile.sku_code]
        hints = [hint for hint in topic_hints if hint.sku_code == profile.sku_code]
        expected_comment_units = dict(target_sku_expected_comment_units or TARGET_SKU_EXPECTED_COMMENT_UNITS)

        issue_specs: list[_IssueSpec] = []
        issue_specs.extend(self._precondition_issues(profile, seed_loaded, m02_completed, m02_comment_trace_ready))
        issue_specs.extend(self._profile_blocked_issues(profile))
        issue_specs.extend(self._profile_warning_issues(profile))
        issue_specs.extend(self._target_sku_sample_issues(profile, expected_comment_units))
        issue_specs.extend(self._topic_guardrail_issues(profile, atoms, hints))
        issue_specs.extend(self._sentiment_review_issues(profile, atoms))
        issue_specs.extend(self._missing_source_issues(profile, atoms))

        deduped_specs = _dedupe_specs(issue_specs)
        issues = [self._build_issue(spec) for spec in deduped_specs]
        blocked = any(spec.severity == Core3ReviewSeverity.BLOCKER for spec in deduped_specs)
        impacts = self._build_downstream_impacts(profile, issues, atoms, hints, blocked)
        return CommentEvidenceReviewPolicyResult(
            review_issues=issues,
            downstream_impacts=impacts,
            blocked=blocked,
            review_required=bool(issues),
            warning_count=sum(1 for issue in issues if issue.severity in {Core3ReviewSeverity.LOW.value, Core3ReviewSeverity.MEDIUM.value}),
            blocker_count=sum(1 for issue in issues if issue.severity == Core3ReviewSeverity.BLOCKER.value),
        )

    def _precondition_issues(
        self,
        profile: CommentQualityProfileRecord,
        seed_loaded: bool,
        m02_completed: bool,
        m02_comment_trace_ready: bool,
    ) -> list[_IssueSpec]:
        specs: list[_IssueSpec] = []
        if not seed_loaded:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_seed_missing",
                    reason_code=CommentReviewReasonCode.TOPIC_SEED_MISSING,
                    severity=Core3ReviewSeverity.BLOCKER,
                    message_cn="评论主题 seed 未加载，M05 无法生成可信弱主题提示。",
                    suggestion_cn="恢复或重新发布 TV comment_topics seed 后重跑 M05。",
                )
            )
        if not m02_completed:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_m02_not_completed",
                    reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                    severity=Core3ReviewSeverity.BLOCKER,
                    message_cn="上游 M02 evidence 未完成，M05 不能继续作为下游评论输入。",
                    suggestion_cn="等待 M02 完成后重跑 M05。",
                )
            )
        if not m02_comment_trace_ready:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_m02_comment_trace_missing",
                    reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                    severity=Core3ReviewSeverity.BLOCKER,
                    message_cn="SKU 的 M02 comment_raw evidence 无法追溯清洗记录。",
                    suggestion_cn="补齐 M02 evidence 追溯链或检查 M01 清洗记录状态。",
                )
            )
        return specs

    def _profile_blocked_issues(self, profile: CommentQualityProfileRecord) -> list[_IssueSpec]:
        specs: list[_IssueSpec] = []
        for reason in profile.blocked_reasons:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code=f"m05_{reason}",
                    reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                    severity=Core3ReviewSeverity.BLOCKER,
                    message_cn=_blocked_message(reason),
                    suggestion_cn="补齐可追溯评论证据后重跑 M05。",
                )
            )
        return specs

    def _profile_warning_issues(self, profile: CommentQualityProfileRecord) -> list[_IssueSpec]:
        specs: list[_IssueSpec] = []
        for flag in profile.warning_flags:
            reason_code, severity, message_cn, suggestion_cn = _warning_policy(flag)
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code=f"m05_{flag}",
                    reason_code=reason_code,
                    severity=severity,
                    message_cn=message_cn,
                    suggestion_cn=suggestion_cn,
                    confidence=profile.comment_usability_score,
                )
            )
        return specs

    def _target_sku_sample_issues(
        self,
        profile: CommentQualityProfileRecord,
        expected_comment_units: Mapping[str, int],
    ) -> list[_IssueSpec]:
        specs: list[_IssueSpec] = []
        if profile.sku_code not in expected_comment_units:
            return specs
        if _enum_value(profile.sample_status) == CommentSampleStatus.INSUFFICIENT.value:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_target_sku_insufficient_sample",
                    reason_code=CommentReviewReasonCode.INSUFFICIENT_SAMPLE,
                    severity=Core3ReviewSeverity.HIGH,
                    message_cn="重点 SKU 评论样本不足，不能直接作为后续评论分析依据。",
                    suggestion_cn="检查去重、低价值规则和原始评论接入完整性。",
                    confidence=profile.comment_usability_score,
                )
            )
        expected_count = expected_comment_units[profile.sku_code]
        minimum_count = max(TARGET_SKU_MIN_LIMITED_UNITS, int(Decimal(expected_count) * TARGET_SKU_LOW_RATIO))
        if profile.comment_unit_count and profile.comment_unit_count < minimum_count:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_target_sku_comment_units_low",
                    reason_code=CommentReviewReasonCode.INSUFFICIENT_SAMPLE,
                    severity=Core3ReviewSeverity.HIGH,
                    message_cn=f"重点 SKU 去重评论数 {profile.comment_unit_count} 明显低于参考规模 {expected_count}。",
                    suggestion_cn="重点检查 85E7Q 原始评论接入、comment_id/text_hash 解析和低价值过滤是否过严。",
                    confidence=profile.comment_usability_score,
                )
            )
        return specs

    def _topic_guardrail_issues(
        self,
        profile: CommentQualityProfileRecord,
        atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
    ) -> list[_IssueSpec]:
        atom_by_id = {atom.comment_evidence_id: atom for atom in atoms}
        specs: list[_IssueSpec] = []
        for hint in topic_hints:
            atom = atom_by_id.get(hint.comment_evidence_id)
            if atom is None:
                continue
            if not _is_service_atom_product_topic(atom, hint):
                continue
            specs.append(
                _IssueSpec(
                    issue_code="m05_service_comment_product_topic_conflict",
                    reason_code=CommentReviewReasonCode.SERVICE_GUARDRAIL,
                    severity=Core3ReviewSeverity.HIGH,
                    object_type="topic_hint",
                    object_id=hint.topic_hint_id,
                    sku_code=profile.sku_code,
                    evidence_refs=_evidence_refs([hint.topic_hint_id, atom.comment_evidence_id, *atom.source_evidence_ids]),
                    message_cn="服务/安装类评论被匹配为产品体验高置信主题，需要复核服务隔离边界。",
                    suggestion_cn="确认该句是否只能进入 M06 service_signal，不能作为产品卖点或产品体验强证据。",
                    confidence=hint.topic_confidence,
                )
            )
        return specs

    def _sentiment_review_issues(
        self,
        profile: CommentQualityProfileRecord,
        atoms: Sequence[CommentEvidenceAtomRecord],
    ) -> list[_IssueSpec]:
        specs: list[_IssueSpec] = []
        sentence_count = max(profile.sentence_count, 1)
        conflict_count = sum(
            1
            for atom in atoms
            if atom.sentiment_conflict_flag or _enum_value(atom.sentiment_hint) == CommentSentimentHint.CONFLICT.value
        )
        conflict_rate = _rate(conflict_count, sentence_count)
        if conflict_rate > SENTIMENT_CONFLICT_REVIEW_THRESHOLD:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_sentiment_conflict_rate_high",
                    reason_code=CommentReviewReasonCode.SENTIMENT_CONFLICT,
                    severity=Core3ReviewSeverity.HIGH,
                    message_cn=f"原始情感与文本情感冲突率 {conflict_rate} 偏高，需要复核评论情感规则。",
                    suggestion_cn="抽样核对正负面规则和原始平台情感字段，必要时调低冲突句下游权重。",
                    confidence=profile.comment_usability_score,
                )
            )
        if profile.negative_sentence_rate > NEGATIVE_REVIEW_THRESHOLD:
            specs.append(
                self._profile_issue(
                    profile,
                    issue_code="m05_negative_sentence_rate_high",
                    reason_code=CommentReviewReasonCode.LOW_CONFIDENCE,
                    severity=Core3ReviewSeverity.HIGH,
                    message_cn=f"负向评论占比 {profile.negative_sentence_rate} 偏高，后续痛点和风险信号需复核。",
                    suggestion_cn="M06 可继续抽取风险信号，但 M16 需要复核负向集中原因。",
                    confidence=profile.comment_usability_score,
                )
            )
        return specs

    def _missing_source_issues(
        self,
        profile: CommentQualityProfileRecord,
        atoms: Sequence[CommentEvidenceAtomRecord],
    ) -> list[_IssueSpec]:
        missing_atoms = [atom for atom in atoms if not atom.source_comment_evidence_ids]
        if not missing_atoms:
            return []
        sample_ids = [atom.comment_evidence_id for atom in missing_atoms[:5]]
        return [
            _IssueSpec(
                issue_code="m05_comment_atom_missing_source_evidence",
                reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                severity=Core3ReviewSeverity.MEDIUM,
                object_type="comment_atom",
                object_id=sample_ids[0],
                sku_code=profile.sku_code,
                evidence_refs=sample_ids,
                message_cn=f"{len(missing_atoms)} 条句级评论证据缺少 comment_raw 追溯，当前只能降级使用。",
                suggestion_cn="检查 M02 evidence link 和 M05 atom 构建输入，补齐 comment_raw evidence 引用。",
                confidence=profile.comment_usability_score,
            )
        ]

    def _build_downstream_impacts(
        self,
        profile: CommentQualityProfileRecord,
        issues: Sequence[M05ReviewIssue],
        atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
        blocked: bool,
    ) -> list[M05DownstreamImpact]:
        evidence_refs = _evidence_refs(
            [
                profile.comment_quality_profile_id,
                *[issue.object_id for issue in issues if issue.object_id],
                *[atom.comment_evidence_id for atom in atoms[:10]],
                *[hint.topic_hint_id for hint in topic_hints[:10]],
            ]
        )
        changed_object_count = 1 + len(atoms) + len(topic_hints)
        if blocked:
            return [
                M05DownstreamImpact(
                    target_module=Core3ModuleCode.M06,
                    sku_code=profile.sku_code,
                    impact_level=Core3SourceImpactLevel.HIGH,
                    changed_object_count=changed_object_count,
                    reason_cn="M05 评论证据被阻断，M06 不能消费该 SKU 评论输入。",
                    evidence_refs=evidence_refs,
                ),
                M05DownstreamImpact(
                    target_module=Core3ModuleCode.M16,
                    sku_code=profile.sku_code,
                    impact_level=Core3SourceImpactLevel.HIGH,
                    changed_object_count=len(issues),
                    reason_cn="M05 产生阻断级复核问题，需要 M16 收敛处理。",
                    evidence_refs=evidence_refs,
                ),
            ]
        if issues:
            return [
                M05DownstreamImpact(
                    target_module=Core3ModuleCode.M06,
                    sku_code=profile.sku_code,
                    impact_level=Core3SourceImpactLevel.MEDIUM,
                    changed_object_count=changed_object_count,
                    reason_cn="M05 评论证据存在 warning/review，M06 可带质量提示继续消费。",
                    evidence_refs=evidence_refs,
                ),
                M05DownstreamImpact(
                    target_module=Core3ModuleCode.M16,
                    sku_code=profile.sku_code,
                    impact_level=Core3SourceImpactLevel.MEDIUM,
                    changed_object_count=len(issues),
                    reason_cn="M05 产生评论证据复核问题，需要 M16 进入复核队列。",
                    evidence_refs=evidence_refs,
                ),
            ]
        return [
            M05DownstreamImpact(
                target_module=Core3ModuleCode.M06,
                sku_code=profile.sku_code,
                impact_level=Core3SourceImpactLevel.LOW,
                changed_object_count=changed_object_count,
                reason_cn="M05 评论证据已刷新，可供 M06 作为评论句输入。",
                evidence_refs=evidence_refs,
            )
        ]

    def _profile_issue(
        self,
        profile: CommentQualityProfileRecord,
        *,
        issue_code: str,
        reason_code: CommentReviewReasonCode,
        severity: Core3ReviewSeverity,
        message_cn: str,
        suggestion_cn: str | None,
        confidence: Decimal | None = None,
    ) -> _IssueSpec:
        return _IssueSpec(
            issue_code=issue_code,
            reason_code=reason_code,
            severity=severity,
            object_type="sku_comment_profile",
            object_id=profile.comment_quality_profile_id,
            sku_code=profile.sku_code,
            evidence_refs=[profile.comment_quality_profile_id],
            message_cn=message_cn,
            suggestion_cn=suggestion_cn,
            confidence=confidence,
        )

    def _build_issue(self, spec: _IssueSpec) -> M05ReviewIssue:
        return M05ReviewIssue(
            issue_code=spec.issue_code,
            reason_code=spec.reason_code,
            severity=spec.severity,
            object_type=spec.object_type,
            object_id=spec.object_id,
            sku_code=spec.sku_code,
            evidence_refs=spec.evidence_refs,
            message_cn=spec.message_cn,
            suggestion_cn=spec.suggestion_cn,
            review_required=True,
            confidence=spec.confidence,
        )


def _warning_policy(
    flag: str,
) -> tuple[CommentReviewReasonCode, Core3ReviewSeverity, str, str]:
    policies = {
        "sample_insufficient": (
            CommentReviewReasonCode.INSUFFICIENT_SAMPLE,
            Core3ReviewSeverity.MEDIUM,
            "评论样本不足，仅能作为弱线索进入后续模块。",
            "检查原始评论接入完整性和低价值规则。",
        ),
        "duplicate_text_rate_high": (
            CommentReviewReasonCode.LOW_VALUE,
            Core3ReviewSeverity.MEDIUM,
            "评论正文重复率过高，可能影响主题和情感分布。",
            "检查默认好评、模板评论和重复文本去重策略。",
        ),
        "low_value_sentence_rate_high": (
            CommentReviewReasonCode.LOW_VALUE,
            Core3ReviewSeverity.MEDIUM,
            "低价值评论句占比高，后续评论信号需要降权。",
            "抽样核对低价值规则，避免把真实产品体验误过滤。",
        ),
        "empty_dimension_rate_high": (
            CommentReviewReasonCode.LOW_CONFIDENCE,
            Core3ReviewSeverity.MEDIUM,
            "原始评论维度缺失率高，弱域判断主要依赖文本规则。",
            "检查评论维度字段接入和平台侧维度解析质量。",
        ),
        "sentiment_unknown_rate_high": (
            CommentReviewReasonCode.LOW_CONFIDENCE,
            Core3ReviewSeverity.MEDIUM,
            "情感 unknown 占比高，后续正负向信号置信度需要降权。",
            "补充情感词规则或抽样校验原始情感字段。",
        ),
        "service_installation_share_high": (
            CommentReviewReasonCode.SERVICE_GUARDRAIL,
            Core3ReviewSeverity.MEDIUM,
            "服务安装评论占比偏高，需要防止淹没产品体验信号。",
            "M06 应区分 service_signal 和产品体验信号。",
        ),
        "topic_unknown_rate_high": (
            CommentReviewReasonCode.TOPIC_SEED_MISSING,
            Core3ReviewSeverity.HIGH,
            "弱主题覆盖不足，存在高频新主题未进入 seed 的可能。",
            "进入 seed 复核，补充 TV 评论主题 seed 后重跑 M05。",
        ),
        "domain_conflict_rate_high": (
            CommentReviewReasonCode.DOMAIN_CONFLICT,
            Core3ReviewSeverity.MEDIUM,
            "文本域与原始维度域冲突偏高，需要复核弱域规则。",
            "抽样核对冲突句，必要时调整文本域优先级。",
        ),
        "negative_sentence_rate_high": (
            CommentReviewReasonCode.LOW_CONFIDENCE,
            Core3ReviewSeverity.HIGH,
            "负向评论占比偏高，后续痛点和风险信号需复核。",
            "M06 可继续抽取风险信号，但 M16 需要复核负向集中原因。",
        ),
    }
    return policies.get(
        flag,
        (
            CommentReviewReasonCode.LOW_CONFIDENCE,
            Core3ReviewSeverity.MEDIUM,
            f"M05 评论质量出现未分类 warning：{flag}。",
            "补充 review policy 映射后重跑 M05。",
        ),
    )


def _blocked_message(reason: str) -> str:
    messages = {
        "no_comment_unit": "未生成可聚合的评论单元，当前 SKU 评论链路阻断。",
        "no_sentence_atom": "未生成句级评论证据，M06 无法消费评论输入。",
        "no_usable_sentence": "无可用于后续分析的句级评论证据，M06 不能消费该 SKU 评论输入。",
    }
    return messages.get(reason, f"M05 评论质量画像阻断：{reason}。")


def _is_service_atom_product_topic(atom: CommentEvidenceAtomRecord, hint: TopicHintRecord) -> bool:
    return (
        _enum_value(atom.primary_domain_hint) in SERVICE_DOMAINS
        and hint.topic_group in PRODUCT_DOMAINS
        and hint.topic_confidence >= HIGH_CONFIDENCE_TOPIC_THRESHOLD
        and _enum_value(hint.topic_hint_status) == CommentTopicHintStatus.MATCHED.value
    )


def _dedupe_specs(specs: Sequence[_IssueSpec]) -> list[_IssueSpec]:
    result: list[_IssueSpec] = []
    seen: set[tuple[str, str | None]] = set()
    for spec in specs:
        key = (spec.issue_code, spec.object_id)
        if key in seen:
            continue
        result.append(spec)
        seen.add(key)
    return result


def _evidence_refs(values: Sequence[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
    return result


def _rate(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return max(Decimal("0.000000"), min(Decimal("1.000000"), Decimal(numerator) / Decimal(denominator)))


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)

