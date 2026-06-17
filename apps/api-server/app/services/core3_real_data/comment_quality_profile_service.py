"""M05 SKU-level comment quality profile service.

The service aggregates M05 comment units, sentence atoms, and weak topic hints
into one SKU quality profile. It intentionally stops before user-task,
battlefield, competitor, score, selection, and report conclusions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentQualityProfileRecord,
    CommentUnitRecord,
    TopicHintRecord,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_RULE_VERSION,
    CommentDomainHint,
    CommentSampleStatus,
    CommentSentimentHint,
    CommentTopicHintStatus,
    Core3ReviewStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_QUALITY_PROFILE_ID_HASH_VERSION = "m05_comment_quality_profile_id_v1"
COMMENT_QUALITY_PROFILE_RESULT_HASH_VERSION = "m05_comment_quality_profile_result_v1"

SERVICE_INSTALLATION_DOMAINS = {
    CommentDomainHint.SERVICE_EXPERIENCE.value,
    CommentDomainHint.LOGISTICS_INSTALLATION.value,
}
TOPIC_COVERAGE_STATUSES = {
    CommentTopicHintStatus.MATCHED.value,
    CommentTopicHintStatus.LOW_CONFIDENCE.value,
}

SAMPLE_SCORE_BY_STATUS = {
    CommentSampleStatus.SUFFICIENT.value: Decimal("1.000000"),
    CommentSampleStatus.LIMITED.value: Decimal("0.700000"),
    CommentSampleStatus.INSUFFICIENT.value: Decimal("0.350000"),
    CommentSampleStatus.UNKNOWN.value: Decimal("0.000000"),
}

SAMPLE_STATUS_CN = {
    CommentSampleStatus.SUFFICIENT.value: "样本充足",
    CommentSampleStatus.LIMITED.value: "样本有限但可用",
    CommentSampleStatus.INSUFFICIENT.value: "样本不足",
    CommentSampleStatus.UNKNOWN.value: "暂无评论样本",
}

WARNING_CN = {
    "sample_insufficient": "评论样本不足",
    "duplicate_text_rate_high": "正文重复过高",
    "low_value_sentence_rate_high": "低价值评论占比高",
    "empty_dimension_rate_high": "原始维度缺失高",
    "sentiment_unknown_rate_high": "情感未知占比高",
    "service_installation_share_high": "服务安装评论占比偏高",
    "topic_unknown_rate_high": "弱主题覆盖不足",
    "domain_conflict_rate_high": "文本域与维度域冲突偏高",
    "negative_sentence_rate_high": "负向评论占比偏高",
}

BLOCKED_CN = {
    "no_comment_unit": "未生成可聚合的评论单元",
    "no_sentence_atom": "未生成句级评论证据",
    "no_usable_sentence": "无可用于后续分析的句级评论证据",
}


@dataclass(frozen=True)
class CommentQualityProfileIssue:
    issue_code: str
    message_cn: str
    sku_code: str | None = None
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentQualityProfileBuildResult:
    record: CommentQualityProfileRecord
    issues: list[CommentQualityProfileIssue] = field(default_factory=list)


class CommentQualityProfileService:
    def build_profile(
        self,
        *,
        project_id: str,
        category_code: str,
        batch_id: str,
        sku_code: str,
        comment_units: Sequence[CommentUnitRecord],
        sentence_atoms: Sequence[CommentEvidenceAtomRecord],
        topic_hints: Sequence[TopicHintRecord],
        run_id: str | None = None,
        module_run_id: str | None = None,
        model_name: str | None = None,
        brand_name: str | None = None,
        input_fingerprint: str | None = None,
        rule_version: str = CORE3_M05_RULE_VERSION,
        asset_version: str = "default",
    ) -> CommentQualityProfileBuildResult:
        units = [unit for unit in comment_units if unit.sku_code == sku_code]
        atoms = [atom for atom in sentence_atoms if atom.sku_code == sku_code]
        hints = [hint for hint in topic_hints if hint.sku_code == sku_code]

        metadata = _first_metadata(units, atoms, hints)
        run_id = run_id if run_id is not None else metadata.get("run_id")
        module_run_id = module_run_id if module_run_id is not None else metadata.get("module_run_id")
        model_name = model_name if model_name is not None else metadata.get("model_name")
        brand_name = brand_name if brand_name is not None else metadata.get("brand_name")
        input_fingerprint = input_fingerprint or metadata.get("input_fingerprint") or stable_hash(
            {
                "project_id": project_id,
                "category_code": category_code,
                "batch_id": batch_id,
                "sku_code": sku_code,
                "unit_hashes": [unit.result_hash for unit in units],
                "atom_hashes": [atom.result_hash for atom in atoms],
                "topic_hashes": [hint.result_hash for hint in hints],
            },
            version="m05_comment_quality_profile_input_v1",
        )

        raw_comment_row_count = _raw_comment_row_count(units)
        comment_unit_count = len(units)
        distinct_comment_id_count = len({unit.comment_id for unit in units if unit.comment_id})
        distinct_comment_text_count = len({unit.comment_text_hash for unit in units if unit.comment_text_hash})
        sentence_count = len(atoms)
        usable_sentence_count = sum(1 for atom in atoms if atom.usable_for_downstream)
        low_value_unit_count = sum(1 for unit in units if unit.low_value_flag)
        low_value_sentence_count = sum(1 for atom in atoms if atom.low_value_flag)
        empty_dimension_count = sum(1 for atom in atoms if not atom.raw_dimension_paths)

        sentiment_distribution = _distribution(atoms, "sentiment_hint", CommentSentimentHint)
        domain_distribution = _distribution(atoms, "primary_domain_hint", CommentDomainHint)
        topic_distribution = _topic_distribution(hints)

        sentiment_unknown_rate = _rate(sentiment_distribution[CommentSentimentHint.UNKNOWN.value], sentence_count)
        sentiment_conflict_rate = _rate(
            sum(
                1
                for atom in atoms
                if atom.sentiment_conflict_flag
                or _enum_value(atom.sentiment_hint) == CommentSentimentHint.CONFLICT.value
            ),
            sentence_count,
        )
        empty_dimension_rate = _rate(empty_dimension_count, sentence_count)
        low_value_sentence_rate = _rate(low_value_sentence_count, sentence_count)
        duplicate_text_rate = _rate(raw_comment_row_count - distinct_comment_text_count, raw_comment_row_count)
        duplicate_row_rate = _rate(raw_comment_row_count - comment_unit_count, raw_comment_row_count)
        service_installation_share = _rate(
            sum(
                1
                for atom in atoms
                if atom.usable_for_downstream and _enum_value(atom.primary_domain_hint) in SERVICE_INSTALLATION_DOMAINS
            ),
            usable_sentence_count,
        )
        product_experience_share = _rate(
            sum(
                1
                for atom in atoms
                if atom.usable_for_downstream
                and _enum_value(atom.primary_domain_hint) == CommentDomainHint.PRODUCT_EXPERIENCE.value
            ),
            usable_sentence_count,
        )
        negative_sentence_rate = _rate(sentiment_distribution[CommentSentimentHint.NEGATIVE.value], sentence_count)
        domain_conflict_rate = _rate(sum(1 for atom in atoms if atom.domain_conflict_flag), sentence_count)
        topic_covered_atom_count = _topic_covered_atom_count(hints)
        topic_unknown_rate = _rate(sentence_count - topic_covered_atom_count, sentence_count)

        sample_status = _sample_status(comment_unit_count, usable_sentence_count)
        comment_usability_score = _comment_usability_score(
            sample_status=sample_status,
            usable_sentence_count=usable_sentence_count,
            sentence_count=sentence_count,
            low_value_sentence_rate=low_value_sentence_rate,
            duplicate_text_rate=duplicate_text_rate,
            duplicate_row_rate=duplicate_row_rate,
            sentiment_unknown_rate=sentiment_unknown_rate,
            topic_covered_atom_count=topic_covered_atom_count,
            empty_dimension_rate=empty_dimension_rate,
        )
        blocked_reasons = _blocked_reasons(comment_unit_count, sentence_count, usable_sentence_count)
        downstream_ready = not blocked_reasons
        warning_flags = _warning_flags(
            sample_status=sample_status,
            duplicate_text_rate=duplicate_text_rate,
            low_value_sentence_rate=low_value_sentence_rate,
            empty_dimension_rate=empty_dimension_rate,
            sentiment_unknown_rate=sentiment_unknown_rate,
            service_installation_share=service_installation_share,
            topic_unknown_rate=topic_unknown_rate,
            domain_conflict_rate=domain_conflict_rate,
            negative_sentence_rate=negative_sentence_rate,
        )
        review_required = bool(warning_flags or blocked_reasons)
        profile_key = f"{project_id}:{category_code}:{batch_id}:{sku_code}:comment_quality"
        comment_quality_profile_id = stable_hash(
            {
                "profile_key": profile_key,
                "rule_version": rule_version,
                "asset_version": asset_version,
            },
            version=COMMENT_QUALITY_PROFILE_ID_HASH_VERSION,
        )
        quality_summary = _quality_summary(
            sample_status=sample_status,
            comment_unit_count=comment_unit_count,
            raw_comment_row_count=raw_comment_row_count,
            sentence_count=sentence_count,
            usable_sentence_count=usable_sentence_count,
            comment_usability_score=comment_usability_score,
            duplicate_text_rate=duplicate_text_rate,
            duplicate_row_rate=duplicate_row_rate,
            low_value_sentence_rate=low_value_sentence_rate,
            sentiment_unknown_rate=sentiment_unknown_rate,
            topic_unknown_rate=topic_unknown_rate,
            service_installation_share=service_installation_share,
            product_experience_share=product_experience_share,
            negative_sentence_rate=negative_sentence_rate,
            warning_flags=warning_flags,
            blocked_reasons=blocked_reasons,
            downstream_ready=downstream_ready,
        )
        result_hash = stable_hash(
            {
                "profile_key": profile_key,
                "counts": {
                    "raw_comment_row_count": raw_comment_row_count,
                    "comment_unit_count": comment_unit_count,
                    "distinct_comment_id_count": distinct_comment_id_count,
                    "distinct_comment_text_count": distinct_comment_text_count,
                    "sentence_count": sentence_count,
                    "usable_sentence_count": usable_sentence_count,
                    "low_value_unit_count": low_value_unit_count,
                    "low_value_sentence_count": low_value_sentence_count,
                    "empty_dimension_count": empty_dimension_count,
                },
                "rates": {
                    "duplicate_text_rate": duplicate_text_rate,
                    "duplicate_row_rate": duplicate_row_rate,
                    "empty_dimension_rate": empty_dimension_rate,
                    "sentiment_unknown_rate": sentiment_unknown_rate,
                    "sentiment_conflict_rate": sentiment_conflict_rate,
                    "service_installation_share": service_installation_share,
                    "product_experience_share": product_experience_share,
                    "negative_sentence_rate": negative_sentence_rate,
                },
                "distributions": {
                    "sentiment": sentiment_distribution,
                    "domain": domain_distribution,
                    "topic": topic_distribution,
                },
                "sample_status": sample_status.value,
                "comment_usability_score": comment_usability_score,
                "warning_flags": warning_flags,
                "blocked_reasons": blocked_reasons,
                "downstream_ready": downstream_ready,
                "rule_version": rule_version,
                "asset_version": asset_version,
            },
            version=COMMENT_QUALITY_PROFILE_RESULT_HASH_VERSION,
        )
        record = CommentQualityProfileRecord(
            comment_quality_profile_id=comment_quality_profile_id,
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            run_id=run_id,
            module_run_id=module_run_id,
            sku_code=sku_code,
            model_name=model_name,
            brand_name=brand_name,
            profile_key=profile_key,
            raw_comment_row_count=raw_comment_row_count,
            comment_unit_count=comment_unit_count,
            distinct_comment_id_count=distinct_comment_id_count,
            distinct_comment_text_count=distinct_comment_text_count,
            sentence_count=sentence_count,
            usable_sentence_count=usable_sentence_count,
            low_value_unit_count=low_value_unit_count,
            low_value_sentence_count=low_value_sentence_count,
            duplicate_text_rate=duplicate_text_rate,
            duplicate_row_rate=duplicate_row_rate,
            empty_dimension_count=empty_dimension_count,
            empty_dimension_rate=empty_dimension_rate,
            sentiment_distribution_json=sentiment_distribution,
            sentiment_unknown_rate=sentiment_unknown_rate,
            sentiment_conflict_rate=sentiment_conflict_rate,
            domain_distribution_json=domain_distribution,
            topic_distribution_json=topic_distribution,
            service_installation_share=service_installation_share,
            product_experience_share=product_experience_share,
            negative_sentence_rate=negative_sentence_rate,
            sample_status=sample_status,
            comment_usability_score=comment_usability_score,
            quality_summary=quality_summary,
            warning_flags=warning_flags,
            blocked_reasons=blocked_reasons,
            downstream_ready=downstream_ready,
            rule_version=rule_version,
            asset_version=asset_version,
            input_fingerprint=input_fingerprint,
            result_hash=result_hash,
            review_required=review_required,
            review_status=Core3ReviewStatus.REVIEW_REQUIRED if review_required else Core3ReviewStatus.AUTO_PASS,
            review_reason_json=quality_summary if review_required else {},
        )
        return CommentQualityProfileBuildResult(record=record, issues=_issues(sku_code, warning_flags, blocked_reasons))


def _first_metadata(
    units: Sequence[CommentUnitRecord],
    atoms: Sequence[CommentEvidenceAtomRecord],
    hints: Sequence[TopicHintRecord],
) -> dict[str, str | None]:
    for item in [*units, *atoms, *hints]:
        return {
            "run_id": item.run_id,
            "module_run_id": item.module_run_id,
            "model_name": item.model_name,
            "brand_name": item.brand_name,
            "input_fingerprint": item.input_fingerprint,
        }
    return {}


def _raw_comment_row_count(units: Sequence[CommentUnitRecord]) -> int:
    source_row_total = sum(unit.source_row_count for unit in units)
    if source_row_total:
        return source_row_total
    evidence_ids = {evidence_id for unit in units for evidence_id in unit.source_comment_evidence_ids}
    if evidence_ids:
        return len(evidence_ids)
    return len(units)


def _distribution(records: Sequence[object], field_name: str, enum_class) -> dict[str, int]:
    counter = Counter(_enum_value(getattr(record, field_name)) for record in records)
    return {item.value: counter.get(item.value, 0) for item in enum_class}


def _topic_distribution(topic_hints: Sequence[TopicHintRecord]) -> dict[str, int]:
    counter = Counter(hint.topic_code for hint in topic_hints if hint.topic_code)
    return dict(sorted(counter.items()))


def _topic_covered_atom_count(topic_hints: Sequence[TopicHintRecord]) -> int:
    covered: set[str] = set()
    for hint in topic_hints:
        if _enum_value(hint.topic_hint_status) in TOPIC_COVERAGE_STATUSES:
            covered.add(hint.comment_evidence_id)
    return len(covered)


def _sample_status(comment_unit_count: int, usable_sentence_count: int) -> CommentSampleStatus:
    if comment_unit_count >= 300 and usable_sentence_count >= 500:
        return CommentSampleStatus.SUFFICIENT
    if comment_unit_count >= 80 and usable_sentence_count >= 120:
        return CommentSampleStatus.LIMITED
    if comment_unit_count > 0:
        return CommentSampleStatus.INSUFFICIENT
    return CommentSampleStatus.UNKNOWN


def _comment_usability_score(
    *,
    sample_status: CommentSampleStatus,
    usable_sentence_count: int,
    sentence_count: int,
    low_value_sentence_rate: Decimal,
    duplicate_text_rate: Decimal,
    duplicate_row_rate: Decimal,
    sentiment_unknown_rate: Decimal,
    topic_covered_atom_count: int,
    empty_dimension_rate: Decimal,
) -> Decimal:
    if sample_status == CommentSampleStatus.UNKNOWN:
        return Decimal("0.000000")

    sample_score = SAMPLE_SCORE_BY_STATUS[sample_status.value]
    usable_sentence_score = _rate(usable_sentence_count, sentence_count)
    non_low_value_score = _clamp_rate(Decimal("1.000000") - low_value_sentence_rate)
    non_duplicate_score = _clamp_rate(Decimal("1.000000") - max(duplicate_text_rate, duplicate_row_rate))
    sentiment_available_score = _clamp_rate(Decimal("1.000000") - sentiment_unknown_rate)
    topic_coverage_score = _rate(topic_covered_atom_count, sentence_count)
    dimension_quality_score = _clamp_rate(Decimal("1.000000") - empty_dimension_rate)

    return _quantize_rate(
        Decimal("0.25") * sample_score
        + Decimal("0.20") * usable_sentence_score
        + Decimal("0.15") * non_low_value_score
        + Decimal("0.15") * non_duplicate_score
        + Decimal("0.10") * sentiment_available_score
        + Decimal("0.10") * topic_coverage_score
        + Decimal("0.05") * dimension_quality_score
    )


def _blocked_reasons(comment_unit_count: int, sentence_count: int, usable_sentence_count: int) -> list[str]:
    reasons: list[str] = []
    if comment_unit_count == 0:
        reasons.append("no_comment_unit")
    if sentence_count == 0:
        reasons.append("no_sentence_atom")
    if sentence_count > 0 and usable_sentence_count == 0:
        reasons.append("no_usable_sentence")
    return reasons


def _warning_flags(
    *,
    sample_status: CommentSampleStatus,
    duplicate_text_rate: Decimal,
    low_value_sentence_rate: Decimal,
    empty_dimension_rate: Decimal,
    sentiment_unknown_rate: Decimal,
    service_installation_share: Decimal,
    topic_unknown_rate: Decimal,
    domain_conflict_rate: Decimal,
    negative_sentence_rate: Decimal,
) -> list[str]:
    flags: list[str] = []
    if sample_status == CommentSampleStatus.INSUFFICIENT:
        flags.append("sample_insufficient")
    if duplicate_text_rate > Decimal("0.650000"):
        flags.append("duplicate_text_rate_high")
    if low_value_sentence_rate > Decimal("0.400000"):
        flags.append("low_value_sentence_rate_high")
    if empty_dimension_rate > Decimal("0.500000"):
        flags.append("empty_dimension_rate_high")
    if sentiment_unknown_rate > Decimal("0.400000"):
        flags.append("sentiment_unknown_rate_high")
    if service_installation_share > Decimal("0.500000"):
        flags.append("service_installation_share_high")
    if topic_unknown_rate > Decimal("0.450000"):
        flags.append("topic_unknown_rate_high")
    if domain_conflict_rate > Decimal("0.200000"):
        flags.append("domain_conflict_rate_high")
    if negative_sentence_rate > Decimal("0.150000"):
        flags.append("negative_sentence_rate_high")
    return flags


def _quality_summary(
    *,
    sample_status: CommentSampleStatus,
    comment_unit_count: int,
    raw_comment_row_count: int,
    sentence_count: int,
    usable_sentence_count: int,
    comment_usability_score: Decimal,
    duplicate_text_rate: Decimal,
    duplicate_row_rate: Decimal,
    low_value_sentence_rate: Decimal,
    sentiment_unknown_rate: Decimal,
    topic_unknown_rate: Decimal,
    service_installation_share: Decimal,
    product_experience_share: Decimal,
    negative_sentence_rate: Decimal,
    warning_flags: Sequence[str],
    blocked_reasons: Sequence[str],
    downstream_ready: bool,
) -> dict[str, object]:
    sample_status_cn = SAMPLE_STATUS_CN[sample_status.value]
    summary_parts = [
        f"{sample_status_cn}，去重评论 {comment_unit_count} 条",
        f"原始评论行 {raw_comment_row_count} 条",
        f"句级证据 {sentence_count} 条",
        f"可用句级证据 {usable_sentence_count} 条",
        f"评论可用分 {comment_usability_score}",
    ]
    if warning_flags:
        summary_parts.append("需关注：" + "、".join(WARNING_CN.get(flag, flag) for flag in warning_flags))
    if blocked_reasons:
        summary_parts.append("暂不可进入后续评论分析：" + "、".join(BLOCKED_CN.get(reason, reason) for reason in blocked_reasons))
    return {
        "summary_cn": "；".join(summary_parts) + "。",
        "sample_status_cn": sample_status_cn,
        "downstream_ready": downstream_ready,
        "comment_usability_score": str(comment_usability_score),
        "counts": {
            "raw_comment_row_count": raw_comment_row_count,
            "comment_unit_count": comment_unit_count,
            "sentence_count": sentence_count,
            "usable_sentence_count": usable_sentence_count,
        },
        "rates": {
            "duplicate_text_rate": str(duplicate_text_rate),
            "duplicate_row_rate": str(duplicate_row_rate),
            "low_value_sentence_rate": str(low_value_sentence_rate),
            "sentiment_unknown_rate": str(sentiment_unknown_rate),
            "topic_unknown_rate": str(topic_unknown_rate),
            "service_installation_share": str(service_installation_share),
            "product_experience_share": str(product_experience_share),
            "negative_sentence_rate": str(negative_sentence_rate),
        },
        "warning_flags": list(warning_flags),
        "warning_labels_cn": [WARNING_CN.get(flag, flag) for flag in warning_flags],
        "blocked_reasons": list(blocked_reasons),
        "blocked_labels_cn": [BLOCKED_CN.get(reason, reason) for reason in blocked_reasons],
    }


def _issues(
    sku_code: str,
    warning_flags: Sequence[str],
    blocked_reasons: Sequence[str],
) -> list[CommentQualityProfileIssue]:
    issues = [
        CommentQualityProfileIssue(
            issue_code=reason,
            message_cn=BLOCKED_CN.get(reason, reason),
            sku_code=sku_code,
            review_required=True,
            blocked=True,
        )
        for reason in blocked_reasons
    ]
    issues.extend(
        CommentQualityProfileIssue(
            issue_code=flag,
            message_cn=WARNING_CN.get(flag, flag),
            sku_code=sku_code,
            review_required=True,
            blocked=False,
        )
        for flag in warning_flags
    )
    return issues


def _rate(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return _clamp_rate(Decimal(numerator) / Decimal(denominator))


def _clamp_rate(value: Decimal) -> Decimal:
    return _quantize_rate(max(Decimal("0.000000"), min(Decimal("1.000000"), value)))


def _quantize_rate(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)
