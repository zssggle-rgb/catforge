"""M05 comment evidence input reader and bundle builder.

This module reads only M02 evidence atoms and converts them into typed M05
input bundles. It does not read raw comment tables and does not build comment
units, topic hints, quality profiles, tasks, battlefields, competitors, or
business conclusions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import and_, func, not_, select

from app.models.entities import Core3EvidenceAtom, Core3V2ModuleRun
from app.services.core3_real_data.comment_evidence_schemas import M05EvidenceInput, M05SkuInputBundle
from app.services.core3_real_data.constants import (
    CORE3_M05_ALLOWED_EVIDENCE_TYPES,
    CORE3_M05_RULE_VERSION,
    CommentReviewReasonCode,
    CommentSampleStatus,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3QualityIssueType,
    Core3ReviewSeverity,
    Core3RunStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import Core3BaseRepository


M05_COMMENT_EVIDENCE_TYPE_VALUES: tuple[str, ...] = tuple(
    evidence_type.value for evidence_type in CORE3_M05_ALLOWED_EVIDENCE_TYPES
)
M02_ACCEPTABLE_STATUSES = frozenset(
    {
        Core3RunStatus.SUCCESS.value,
        Core3RunStatus.WARNING.value,
        Core3RunStatus.REVIEW_REQUIRED.value,
    }
)
M05_INPUT_FINGERPRINT_VERSION = "m05_comment_input_v1"


class M05InputBlockedError(RuntimeError):
    """Raised when M05 cannot safely consume upstream M02 evidence."""


@dataclass(frozen=True)
class M05InputIssue:
    issue_code: str
    reason_code: CommentReviewReasonCode
    severity: Core3ReviewSeverity
    message_cn: str
    evidence_ids: list[str] = field(default_factory=list)
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class M05SkuInputBundleResult:
    bundle: M05SkuInputBundle
    evidence_type_counts: dict[str, int]
    raw_count: int
    sentence_count: int
    dimension_count: int
    quality_issue_count: int
    sample_status: CommentSampleStatus
    review_required: bool
    blocked: bool
    can_degrade_sentence: bool
    issues: list[M05InputIssue]


class CommentEvidenceInputRepository(Core3BaseRepository):
    """Read M02 evidence required by M05."""

    def assert_m02_completed(self, batch_id: str) -> Core3V2ModuleRun:
        stmt = (
            select(Core3V2ModuleRun)
            .where(Core3V2ModuleRun.project_id == self.project_id)
            .where(Core3V2ModuleRun.category_code == self.category_code.value)
            .where(Core3V2ModuleRun.batch_id == batch_id)
            .where(Core3V2ModuleRun.module_code == Core3ModuleCode.M02.value)
            .order_by(Core3V2ModuleRun.updated_at.desc(), Core3V2ModuleRun.module_run_id.desc())
            .limit(1)
        )
        module_run = self.db.execute(stmt).scalars().first()
        if module_run is None:
            raise M05InputBlockedError(f"M02 module run not found for batch_id={batch_id}")
        if module_run.status not in M02_ACCEPTABLE_STATUSES:
            raise M05InputBlockedError(f"M02 module run is not consumable: {module_run.status}")
        return module_run

    def list_sku_codes_with_comment_evidence(self, batch_id: str) -> list[str]:
        stmt = (
            select(Core3EvidenceAtom.sku_code)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(Core3EvidenceAtom.evidence_type.in_(M05_COMMENT_EVIDENCE_TYPE_VALUES))
            .where(_m05_consumable_evidence_filter())
            .where(Core3EvidenceAtom.sku_code.is_not(None))
            .group_by(Core3EvidenceAtom.sku_code)
            .order_by(Core3EvidenceAtom.sku_code)
        )
        return [str(sku_code) for sku_code in self.db.execute(stmt).scalars().all() if sku_code]

    def list_comment_evidence(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] | None = None,
        evidence_types: Sequence[str] | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[Core3EvidenceAtom]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=5000)
        types = tuple(evidence_types) if evidence_types else M05_COMMENT_EVIDENCE_TYPE_VALUES
        unsupported_types = sorted(set(types) - set(M05_COMMENT_EVIDENCE_TYPE_VALUES))
        if unsupported_types:
            raise ValueError(f"unsupported M05 evidence_types: {', '.join(unsupported_types)}")

        stmt = (
            select(Core3EvidenceAtom)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(Core3EvidenceAtom.evidence_type.in_(types))
            .where(_m05_consumable_evidence_filter())
            .order_by(
                Core3EvidenceAtom.sku_code,
                Core3EvidenceAtom.evidence_type,
                Core3EvidenceAtom.comment_id,
                Core3EvidenceAtom.sentence_seq,
                Core3EvidenceAtom.evidence_id,
            )
            .limit(normalized_limit)
            .offset(normalized_offset)
        )
        if sku_scope:
            stmt = stmt.where(Core3EvidenceAtom.sku_code.in_(tuple(sku_scope)))
        return list(self.db.execute(stmt).scalars())

    def count_comment_evidence_by_type(self, batch_id: str, *, sku_code: str | None = None) -> dict[str, int]:
        stmt = (
            select(Core3EvidenceAtom.evidence_type, func.count())
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.batch_id == batch_id)
            .where(Core3EvidenceAtom.is_current.is_(True))
            .where(Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
            .where(Core3EvidenceAtom.evidence_type.in_(M05_COMMENT_EVIDENCE_TYPE_VALUES))
            .where(_m05_consumable_evidence_filter())
            .group_by(Core3EvidenceAtom.evidence_type)
        )
        if sku_code is not None:
            stmt = stmt.where(Core3EvidenceAtom.sku_code == sku_code)
        return {str(evidence_type): int(count) for evidence_type, count in self.db.execute(stmt).all()}

    def get_evidence_result_hashes(self, evidence_ids: Sequence[str]) -> dict[str, str]:
        if not evidence_ids:
            return {}
        stmt = (
            select(Core3EvidenceAtom.evidence_id, Core3EvidenceAtom.clean_hash)
            .where(Core3EvidenceAtom.project_id == self.project_id)
            .where(Core3EvidenceAtom.category_code == self.category_code.value)
            .where(Core3EvidenceAtom.evidence_id.in_(tuple(evidence_ids)))
        )
        return {str(evidence_id): str(clean_hash) for evidence_id, clean_hash in self.db.execute(stmt).all()}


class CommentEvidenceInputService:
    def __init__(self, repository: CommentEvidenceInputRepository) -> None:
        self.repository = repository

    def build_sku_bundle(
        self,
        batch_id: str,
        sku_code: str,
        *,
        seed_content_hash: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
    ) -> M05SkuInputBundleResult:
        self.repository.assert_m02_completed(batch_id)
        records = self.repository.list_comment_evidence(batch_id, sku_scope=[sku_code], limit=5000)
        inputs = [self._to_input(record) for record in records]
        evidence_type_counts = dict(sorted(Counter(item.evidence_type for item in inputs).items()))
        raw_count = evidence_type_counts.get(Core3EvidenceType.COMMENT_RAW.value, 0)
        sentence_count = evidence_type_counts.get(Core3EvidenceType.COMMENT_SENTENCE.value, 0)
        dimension_count = evidence_type_counts.get(Core3EvidenceType.COMMENT_DIMENSION.value, 0)
        quality_issue_count = evidence_type_counts.get(Core3EvidenceType.QUALITY_ISSUE.value, 0)

        issues = self._build_input_issues(inputs, raw_count=raw_count, sentence_count=sentence_count, dimension_count=dimension_count)
        blocked = any(issue.blocked for issue in issues)
        review_required = any(issue.review_required for issue in issues)
        can_degrade_sentence = raw_count > 0 and sentence_count == 0 and not blocked
        sample_status = self._sample_status(raw_count)
        model_name = self._first_non_empty(record.model_name for record in records)
        brand_name = self._first_non_empty(record.brand_name for record in records)
        input_fingerprint = self.build_input_fingerprint(
            inputs,
            seed_content_hash=seed_content_hash,
            rule_version=rule_version,
        )
        bundle = M05SkuInputBundle(
            project_id=self.repository.project_id,
            category_code=self.repository.category_code,
            batch_id=batch_id,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            evidence_inputs=inputs,
            input_fingerprint=input_fingerprint,
        )
        return M05SkuInputBundleResult(
            bundle=bundle,
            evidence_type_counts=evidence_type_counts,
            raw_count=raw_count,
            sentence_count=sentence_count,
            dimension_count=dimension_count,
            quality_issue_count=quality_issue_count,
            sample_status=sample_status,
            review_required=review_required,
            blocked=blocked,
            can_degrade_sentence=can_degrade_sentence,
            issues=issues,
        )

    def list_sku_bundles(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] | None = None,
        seed_content_hash: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
    ) -> list[M05SkuInputBundleResult]:
        self.repository.assert_m02_completed(batch_id)
        sku_codes = list(sku_scope) if sku_scope else self.repository.list_sku_codes_with_comment_evidence(batch_id)
        return [
            self.build_sku_bundle(
                batch_id,
                sku_code,
                seed_content_hash=seed_content_hash,
                rule_version=rule_version,
            )
            for sku_code in sku_codes
        ]

    def build_input_fingerprint(
        self,
        inputs: Sequence[M05EvidenceInput],
        *,
        seed_content_hash: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
    ) -> str:
        evidence_payload = [
            {
                "evidence_id": item.evidence_id,
                "evidence_type": item.evidence_type,
                "clean_record_key": item.clean_record_key,
                "base_confidence": item.base_confidence,
                "comment_id": item.comment_id,
                "comment_text_hash": item.comment_text_hash,
                "segment_text_hash": item.segment_text_hash,
                "source_row_id": item.source_row_id,
                "text_value": item.text_value,
            }
            for item in sorted(inputs, key=lambda input_item: input_item.evidence_id)
        ]
        return stable_hash(
            {
                "rule_version": rule_version,
                "seed_content_hash": seed_content_hash,
                "evidence": evidence_payload,
            },
            version=M05_INPUT_FINGERPRINT_VERSION,
        )

    def _to_input(self, record: Core3EvidenceAtom) -> M05EvidenceInput:
        return M05EvidenceInput(
            evidence_id=record.evidence_id,
            evidence_key=record.evidence_key,
            project_id=record.project_id,
            category_code=record.category_code,
            batch_id=record.batch_id,
            sku_code=record.sku_code,
            model_name=record.model_name,
            brand_name=record.brand_name,
            evidence_type=record.evidence_type,
            evidence_field=record.evidence_field,
            source_row_id=record.source_row_id,
            clean_record_key=record.clean_record_key,
            comment_id=record.comment_id,
            comment_text_hash=record.comment_text_hash,
            segment_text_hash=record.segment_text_hash,
            sentence_seq=record.sentence_seq,
            dimension_path_raw=record.dimension_path_raw,
            text_value=record.text_value,
            raw_value=record.raw_value,
            clean_value=record.clean_value,
            evidence_payload_json=record.evidence_payload_json or {},
            confidence_level=record.confidence_level,
            base_confidence=record.base_confidence or Decimal("0.0000"),
            quality_flags=record.quality_flags or [],
            is_current=bool(record.is_current),
        )

    def _build_input_issues(
        self,
        inputs: Sequence[M05EvidenceInput],
        *,
        raw_count: int,
        sentence_count: int,
        dimension_count: int,
    ) -> list[M05InputIssue]:
        issues: list[M05InputIssue] = []
        if raw_count == 0:
            issues.append(
                M05InputIssue(
                    issue_code="m05_missing_comment_raw",
                    reason_code=CommentReviewReasonCode.INSUFFICIENT_SAMPLE,
                    severity=Core3ReviewSeverity.HIGH,
                    message_cn="该 SKU 没有 M02 comment_raw evidence，M05 只能写未知样本画像。",
                    review_required=True,
                    blocked=False,
                )
            )
        if raw_count > 0 and sentence_count == 0:
            issues.append(
                M05InputIssue(
                    issue_code="m05_missing_comment_sentence",
                    reason_code=CommentReviewReasonCode.LOW_CONFIDENCE,
                    severity=Core3ReviewSeverity.MEDIUM,
                    message_cn="该 SKU 有原始评论但没有 M02 comment_sentence evidence，后续需降级切句并复核。",
                    evidence_ids=[item.evidence_id for item in inputs if item.evidence_type == Core3EvidenceType.COMMENT_RAW.value],
                    review_required=True,
                    blocked=False,
                )
            )
        if raw_count > 0 and dimension_count == 0:
            issues.append(
                M05InputIssue(
                    issue_code="m05_missing_comment_dimension",
                    reason_code=CommentReviewReasonCode.LOW_CONFIDENCE,
                    severity=Core3ReviewSeverity.LOW,
                    message_cn="该 SKU 没有 M02 comment_dimension evidence，弱域只能依赖文本规则。",
                    review_required=False,
                    blocked=False,
                )
            )

        missing_clean_key_ids = [item.evidence_id for item in inputs if not item.clean_record_key]
        if missing_clean_key_ids:
            issues.append(
                M05InputIssue(
                    issue_code="m05_missing_clean_record_trace",
                    reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                    severity=Core3ReviewSeverity.BLOCKER,
                    message_cn="部分 M02 评论 evidence 缺少 clean_record_key，无法追溯 M01 清洗记录。",
                    evidence_ids=missing_clean_key_ids,
                    review_required=True,
                    blocked=True,
                )
            )

        weak_trace_ids = [
            item.evidence_id
            for item in inputs
            if item.evidence_type in {Core3EvidenceType.COMMENT_RAW.value, Core3EvidenceType.COMMENT_SENTENCE.value}
            and not (item.comment_id or item.comment_text_hash or item.source_row_id)
        ]
        if weak_trace_ids:
            issues.append(
                M05InputIssue(
                    issue_code="m05_weak_comment_trace",
                    reason_code=CommentReviewReasonCode.MISSING_SOURCE_EVIDENCE,
                    severity=Core3ReviewSeverity.MEDIUM,
                    message_cn="部分评论 evidence 缺少 comment_id、comment_text_hash 和 source_row_id，只能低置信处理。",
                    evidence_ids=weak_trace_ids,
                    review_required=True,
                    blocked=False,
                )
            )
        return issues

    def _sample_status(self, raw_count: int) -> CommentSampleStatus:
        if raw_count <= 0:
            return CommentSampleStatus.UNKNOWN
        return CommentSampleStatus.INSUFFICIENT

    def _first_non_empty(self, values: Sequence[str | None]) -> str | None:
        for value in values:
            if value:
                return value
        return None


def _m05_consumable_evidence_filter():
    excluded_comment_quality_fields = (
        f"quality_issue:comment:{Core3QualityIssueType.LOW_VALUE_COMMENT.value}",
        f"quality_issue:comment:{Core3QualityIssueType.DUPLICATE_COMMENT_TEXT.value}",
    )
    return not_(
        and_(
            Core3EvidenceAtom.evidence_type == Core3EvidenceType.QUALITY_ISSUE.value,
            Core3EvidenceAtom.evidence_field.in_(excluded_comment_quality_fields),
        )
    )
