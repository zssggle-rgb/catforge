"""M05 comment unit evidence link builder.

This builder expands comment unit source evidence arrays into pageable source
links. It intentionally stops before sentence atoms, topic hints, quality
profiles, tasks, battlefields, competitors, and reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentUnitEvidenceLinkRecord,
    CommentUnitRecord,
    M05EvidenceInput,
    M05SkuInputBundle,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    Core3EvidenceType,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_UNIT_LINK_ID_HASH_VERSION = "m05_comment_unit_link_id_v1"
COMMENT_UNIT_LINK_RESULT_HASH_VERSION = "m05_comment_unit_link_result_v1"

LINK_ROLE_BY_EVIDENCE_TYPE = {
    Core3EvidenceType.COMMENT_RAW.value: "raw_source",
    Core3EvidenceType.COMMENT_SENTENCE.value: "sentence_source",
    Core3EvidenceType.COMMENT_DIMENSION.value: "dimension_weak_label",
    Core3EvidenceType.QUALITY_ISSUE.value: "quality_flag",
}
SOURCE_ID_FIELDS_BY_LINK_ROLE = {
    "raw_source": "source_comment_evidence_ids",
    "sentence_source": "source_sentence_evidence_ids",
    "dimension_weak_label": "source_dimension_evidence_ids",
    "quality_flag": "source_quality_evidence_ids",
}
LINK_ROLE_SORT_ORDER = {
    "raw_source": 0,
    "sentence_source": 1,
    "dimension_weak_label": 2,
    "quality_flag": 3,
}


@dataclass(frozen=True)
class CommentUnitLinkBuildIssue:
    issue_code: str
    message_cn: str
    comment_unit_id: str | None = None
    evidence_ids: list[str] = field(default_factory=list)
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentUnitLinkBuildResult:
    records: list[CommentUnitEvidenceLinkRecord]
    skipped_evidence_ids: list[str]
    issues: list[CommentUnitLinkBuildIssue]
    review_required_count: int


class CommentUnitLinkBuilder:
    def build_links(
        self,
        bundle: M05SkuInputBundle,
        comment_units: Sequence[CommentUnitRecord],
        *,
        run_id: str | None = None,
        module_run_id: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentUnitLinkBuildResult:
        evidence_by_id = {item.evidence_id: item for item in bundle.evidence_inputs}
        link_records: dict[tuple[str, str, str, str], CommentUnitEvidenceLinkRecord] = {}
        skipped_evidence_ids: set[str] = set()
        issues: list[CommentUnitLinkBuildIssue] = []

        for unit in sorted(comment_units, key=lambda item: item.comment_unit_id):
            for source_evidence_id, link_role in self._iter_unit_sources(unit):
                evidence_input = evidence_by_id.get(source_evidence_id)
                if evidence_input is None:
                    skipped_evidence_ids.add(source_evidence_id)
                    issues.append(
                        CommentUnitLinkBuildIssue(
                            issue_code="m05_link_missing_source_evidence",
                            message_cn="评论单元引用的 M02 evidence 不在当前 M05 输入 bundle 中，无法生成来源 link。",
                            comment_unit_id=unit.comment_unit_id,
                            evidence_ids=[source_evidence_id],
                            review_required=True,
                            blocked=False,
                        )
                    )
                    continue

                expected_role = LINK_ROLE_BY_EVIDENCE_TYPE.get(str(evidence_input.evidence_type))
                if expected_role != link_role:
                    skipped_evidence_ids.add(source_evidence_id)
                    issues.append(
                        CommentUnitLinkBuildIssue(
                            issue_code="m05_link_evidence_role_mismatch",
                            message_cn="评论单元 evidence 类型与来源 link role 不一致，已跳过该来源 link。",
                            comment_unit_id=unit.comment_unit_id,
                            evidence_ids=[source_evidence_id],
                            review_required=True,
                            blocked=False,
                        )
                    )
                    continue

                record = self._build_record(
                    bundle,
                    unit,
                    evidence_input,
                    link_role,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    rule_version=rule_version,
                    asset_version=asset_version,
                )
                dedupe_key = (unit.comment_unit_id, source_evidence_id, link_role, rule_version)
                link_records.setdefault(dedupe_key, record)

        records = sorted(
            link_records.values(),
            key=lambda item: (item.comment_unit_id, LINK_ROLE_SORT_ORDER[item.link_role], item.source_evidence_id),
        )
        return CommentUnitLinkBuildResult(
            records=records,
            skipped_evidence_ids=sorted(skipped_evidence_ids),
            issues=issues,
            review_required_count=sum(1 for record in records if record.review_required),
        )

    def _iter_unit_sources(self, unit: CommentUnitRecord) -> list[tuple[str, str]]:
        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for link_role, field_name in SOURCE_ID_FIELDS_BY_LINK_ROLE.items():
            for evidence_id in getattr(unit, field_name):
                key = (str(evidence_id), link_role)
                if key in seen:
                    continue
                pairs.append(key)
                seen.add(key)
        return pairs

    def _build_record(
        self,
        bundle: M05SkuInputBundle,
        unit: CommentUnitRecord,
        evidence_input: M05EvidenceInput,
        link_role: str,
        *,
        run_id: str | None,
        module_run_id: str | None,
        rule_version: str,
        asset_version: str,
    ) -> CommentUnitEvidenceLinkRecord:
        source_evidence_id = evidence_input.evidence_id
        id_payload = {
            "comment_unit_id": unit.comment_unit_id,
            "source_evidence_id": source_evidence_id,
            "link_role": link_role,
            "rule_version": rule_version,
        }
        result_payload = {
            **id_payload,
            "source_evidence_type": evidence_input.evidence_type,
            "source_row_id": evidence_input.source_row_id,
            "comment_id": evidence_input.comment_id or unit.comment_id,
            "comment_text_hash": evidence_input.comment_text_hash or unit.comment_text_hash,
            "sentence_hash": evidence_input.segment_text_hash,
            "dimension_path_raw": evidence_input.dimension_path_raw,
            "quality_issue_type": self._quality_issue_type(evidence_input),
            "asset_version": asset_version,
        }
        review_required = bool(unit.review_required)
        return CommentUnitEvidenceLinkRecord(
            unit_link_id=stable_hash(id_payload, version=COMMENT_UNIT_LINK_ID_HASH_VERSION),
            project_id=unit.project_id,
            category_code=unit.category_code,
            batch_id=unit.batch_id,
            run_id=unit.run_id or run_id,
            module_run_id=unit.module_run_id or module_run_id,
            sku_code=unit.sku_code or bundle.sku_code,
            model_name=unit.model_name or bundle.model_name,
            brand_name=unit.brand_name or bundle.brand_name,
            comment_unit_id=unit.comment_unit_id,
            source_evidence_id=source_evidence_id,
            source_evidence_type=evidence_input.evidence_type,
            link_role=link_role,
            source_row_id=_none_if_blank(evidence_input.source_row_id),
            comment_id=_none_if_blank(evidence_input.comment_id or unit.comment_id),
            comment_text_hash=_none_if_blank(evidence_input.comment_text_hash or unit.comment_text_hash),
            sentence_hash=_none_if_blank(evidence_input.segment_text_hash),
            dimension_path_raw=_none_if_blank(evidence_input.dimension_path_raw),
            quality_issue_type=_none_if_blank(self._quality_issue_type(evidence_input)),
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=unit.input_fingerprint or bundle.input_fingerprint,
            result_hash=stable_hash(result_payload, version=COMMENT_UNIT_LINK_RESULT_HASH_VERSION),
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json=self._review_reason(unit) if review_required else {},
        )

    def _quality_issue_type(self, evidence_input: M05EvidenceInput) -> str | None:
        if str(evidence_input.evidence_type) != Core3EvidenceType.QUALITY_ISSUE.value:
            return None
        payload_issue_type = evidence_input.evidence_payload_json.get("issue_type")
        if isinstance(payload_issue_type, str) and payload_issue_type.strip():
            return payload_issue_type.strip()
        return evidence_input.evidence_field

    def _review_reason(self, unit: CommentUnitRecord) -> dict[str, object]:
        return {
            "reason_codes": ["source_unit_review_required"],
            "message_cn": "来源评论单元需要复核，link 继承该复核状态。",
            "unit_review_reason": unit.review_reason_json,
        }


def _none_if_blank(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
