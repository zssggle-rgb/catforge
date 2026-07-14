"""Deterministic version-quality and freshness assessment for competitor profiles."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    MaterializedCompetitorProfile,
    TargetMaterializationStatus,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileReadBundle,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_quality_schemas import (
    CompetitorProfileFreshnessAssessment,
    CompetitorProfileQualityIssue,
    CompetitorProfileVersionQualityAssessment,
    QualityIssueSeverity,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileDraftBundle,
    FreshnessStatus,
    ReleaseQualityStatus,
    ServingScope,
)
from app.services.core3_real_data.hash_utils import stable_hash


QUALITY_HASH_VERSION = "competitor_profile_quality_assessment_v1"
FRESHNESS_HASH_VERSION = "competitor_profile_freshness_assessment_v1"
MANIFEST_HASH_VERSION = "competitor_profile_authoritative_sku_manifest_v1"

ProfileQualityInput: TypeAlias = (
    CompetitorProfileDraftBundle
    | CompetitorProfileReadBundle
    | MaterializedCompetitorProfile
)


class CompetitorProfileQualityError(ValueError):
    """Raised when the assessment request itself violates the typed contract."""


class CompetitorProfileQualityService:
    """Assess saved/materialized versions without mutating analytical rows."""

    def assess_version(
        self,
        *,
        version: CompetitorProfileVersionRecord,
        authoritative_sku_codes: Sequence[str],
        profiles: Sequence[ProfileQualityInput],
        generation_failures: Sequence[TargetMaterializationStatus] = (),
    ) -> CompetitorProfileVersionQualityAssessment:
        expected_codes = _authoritative_codes(authoritative_sku_codes)
        issues: list[CompetitorProfileQualityIssue] = []
        normalized: list[tuple[str, CompetitorProfileDraftBundle]] = []

        for value in profiles:
            draft, version_id = _draft_and_version_id(value)
            target = draft.profile.target_sku_code
            issues.extend(_input_hash_issues(value, target))
            if (
                version_id is not None
                and version_id != version.competitor_profile_version_id
            ):
                issues.append(
                    _issue(
                        "profile_version_mismatch",
                        QualityIssueSeverity.P0,
                        "profile",
                        "画像读取结果不属于待评估版本。",
                        target,
                    )
                )
            normalized.append((target, draft))
        normalized.sort(key=lambda row: (row[0], row[1].profile.result_hash))

        profile_by_sku: dict[str, CompetitorProfileDraftBundle] = {}
        for target, draft in normalized:
            if target in profile_by_sku:
                issues.append(
                    _issue(
                        "duplicate_target_profile",
                        QualityIssueSeverity.P1,
                        "profile",
                        "同一 SKU 在版本中出现重复画像。",
                        target,
                    )
                )
                continue
            profile_by_sku[target] = draft

        expected_set = set(expected_codes)
        assessed_codes = sorted(profile_by_sku)
        assessed_set = set(assessed_codes)
        missing_codes = sorted(expected_set - assessed_set)
        unexpected_codes = sorted(assessed_set - expected_set)

        issues.extend(_version_scope_issues(version, expected_codes))
        for target in unexpected_codes:
            issues.append(
                _issue(
                    "unexpected_target_profile",
                    QualityIssueSeverity.P0,
                    "profile",
                    "版本包含权威 SKU 清单之外的画像。",
                    target,
                )
            )

        processing_complete = version.processing_status == "completed"
        if missing_codes:
            severity = (
                QualityIssueSeverity.P1
                if processing_complete
                else QualityIssueSeverity.P2
            )
            code = (
                "authoritative_profile_missing"
                if processing_complete
                else "generation_incomplete"
            )
            reason = (
                "生成已结束，但仍有权威 SKU 未形成画像。"
                if processing_complete
                else "画像生成尚未覆盖全部权威 SKU。"
            )
            for target in missing_codes:
                issues.append(_issue(code, severity, "profile", reason, target))
        elif not processing_complete:
            issues.append(
                _issue(
                    "generation_incomplete",
                    QualityIssueSeverity.P2,
                    "version",
                    "版本尚未完成生成，质量状态保持未评估。",
                )
            )

        failed_codes: list[str] = []
        for failure in generation_failures:
            if failure.status != "failed":
                raise CompetitorProfileQualityError(
                    "generation_failures can contain failed statuses only"
                )
            failed_codes.append(failure.target_sku_code)
            issues.append(
                _issue(
                    "sku_generation_failed",
                    QualityIssueSeverity.P1,
                    "profile",
                    "该 SKU 生成失败，版本不能进入发布评审。",
                    failure.target_sku_code,
                )
            )
        if len(failed_codes) != len(set(failed_codes)):
            raise CompetitorProfileQualityError(
                "generation failure targets must be unique"
            )
        if version.failed_count and not failed_codes:
            issues.append(
                _issue(
                    "version_failed_count_present",
                    QualityIssueSeverity.P1,
                    "version",
                    "版本记录了生成失败，但缺少对应失败 SKU 明细。",
                )
            )
        if version.failed_count != len(failed_codes):
            issues.append(
                _issue(
                    "failed_count_mismatch",
                    QualityIssueSeverity.P1,
                    "version",
                    "版本失败计数与失败 SKU 明细不一致。",
                )
            )

        ready_count = 0
        partial_count = 0
        blocked_count = 0
        pair_count = 0
        relation_count = 0
        selection_count = 0
        for target in assessed_codes:
            draft = profile_by_sku[target]
            profile = draft.profile
            if profile.project_id != version.project_id:
                issues.append(
                    _issue(
                        "profile_project_mismatch",
                        QualityIssueSeverity.P0,
                        "profile",
                        "SKU 画像项目与版本项目不一致。",
                        target,
                    )
                )
            if profile.category_code != version.category_code:
                issues.append(
                    _issue(
                        "cross_category_profile",
                        QualityIssueSeverity.P0,
                        "profile",
                        "SKU 画像品类与版本品类不一致。",
                        target,
                    )
                )
            if not any(
                target.startswith(prefix)
                for prefix in version.serving_scope.sku_prefixes
            ):
                issues.append(
                    _issue(
                        "target_prefix_out_of_scope",
                        QualityIssueSeverity.P0,
                        "profile",
                        "SKU 编码超出版本允许的品类前缀。",
                        target,
                    )
                )

            if profile.analysis_state == "ready":
                ready_count += 1
            elif profile.analysis_state == "partial":
                partial_count += 1
                issues.append(
                    _issue(
                        "partial_profile_present",
                        QualityIssueSeverity.P2,
                        "profile",
                        "该 SKU 只有部分竞品问题形成结论。",
                        target,
                    )
                )
            else:
                blocked_count += 1
                issues.append(
                    _issue(
                        "blocked_profile_present",
                        QualityIssueSeverity.P1,
                        "profile",
                        "该 SKU 存在阻断问题，不能作为可发布画像。",
                        target,
                    )
                )
            if profile.review_required and profile.analysis_state != "blocked":
                issues.append(
                    _issue(
                        "profile_review_required",
                        QualityIssueSeverity.P2,
                        "profile",
                        "该 SKU 仍需人工复核。",
                        target,
                    )
                )
            if profile.freshness_status == FreshnessStatus.STALE.value:
                issues.append(
                    _issue(
                        "stale_profile_present",
                        QualityIssueSeverity.P2,
                        "profile",
                        "该 SKU 使用的上游版本已经变化。",
                        target,
                    )
                )

            pair_count += len(draft.pairs)
            relation_count += sum(
                len(pair.relation_assessments) for pair in draft.pairs
            )
            selection_count += len(draft.selections)
            issues.extend(_bundle_integrity_issues(draft))

        if processing_complete:
            actual_counts = {
                "ready_count": ready_count,
                "partial_count": partial_count,
                "blocked_count": blocked_count,
                "pair_count": pair_count,
                "relation_count": relation_count,
                "selection_count": selection_count,
            }
            for field_name, actual in actual_counts.items():
                if getattr(version, field_name) != actual:
                    issues.append(
                        _issue(
                            f"{field_name}_mismatch",
                            QualityIssueSeverity.P1,
                            "version",
                            f"版本 {field_name} 与实际画像统计不一致。",
                        )
                    )

        issues = _sorted_unique_issues(issues)
        quality = _quality_status(
            processing_complete=processing_complete,
            issues=issues,
        )
        payload = {
            "competitor_profile_version_id": version.competitor_profile_version_id,
            "profile_version": version.profile_version,
            "project_id": version.project_id,
            "category_code": version.category_code,
            "release_quality_status": quality.value,
            "processing_status": version.processing_status,
            "expected_sku_count": len(expected_codes),
            "profile_count": len(assessed_codes),
            "ready_count": ready_count,
            "partial_count": partial_count,
            "blocked_count": blocked_count,
            "failed_count": len(failed_codes),
            "pair_count": pair_count,
            "relation_count": relation_count,
            "selection_count": selection_count,
            "assessed_sku_codes": assessed_codes,
            "missing_sku_codes": missing_codes,
            "unexpected_sku_codes": unexpected_codes,
            "issues": [row.model_dump(mode="python") for row in issues],
            "review_required": quality != ReleaseQualityStatus.READY,
        }
        return CompetitorProfileVersionQualityAssessment(
            **payload,
            result_hash=stable_hash(payload, version=QUALITY_HASH_VERSION),
        )

    def assess_freshness(
        self,
        *,
        version: CompetitorProfileVersionRecord,
        current_serving_scope: ServingScope | None,
    ) -> CompetitorProfileFreshnessAssessment:
        saved_scope = version.serving_scope
        saved_dump = saved_scope.model_dump(mode="python")
        saved_fingerprint = stable_hash(
            saved_dump,
            version="competitor_profile_serving_scope_fingerprint_v1",
        )
        changed_authorities: list[str] = []
        unavailable_authorities: list[str] = []
        changed_scope_fields: list[str] = []
        reason_codes: list[str] = []
        current_fingerprint: str | None = None

        if current_serving_scope is None:
            status = FreshnessStatus.UNKNOWN
            unavailable_authorities = sorted(saved_scope.source_authorities)
            reason_codes = ["current_serving_scope_unavailable"]
        else:
            _assert_scope_identity(version, current_serving_scope)
            current_dump = current_serving_scope.model_dump(mode="python")
            current_fingerprint = stable_hash(
                current_dump,
                version="competitor_profile_serving_scope_fingerprint_v1",
            )
            saved_authorities = saved_scope.source_authorities
            current_authorities = current_serving_scope.source_authorities
            for code in sorted(set(saved_authorities) | set(current_authorities)):
                saved = saved_authorities.get(code)
                current = current_authorities.get(code)
                if saved is None:
                    changed_authorities.append(code)
                elif current is None:
                    unavailable_authorities.append(code)
                elif saved.model_dump(mode="python") != current.model_dump(
                    mode="python"
                ):
                    changed_authorities.append(code)

            for field_name in (
                "analysis_population",
                "market_window",
                "taxonomy_version",
                "storage_batch_id",
                "source_batch_ids",
                "sku_prefixes",
                "authoritative_sku_count",
                "authoritative_sku_manifest_hash",
                "release_scope_key",
            ):
                if getattr(saved_scope, field_name) != getattr(
                    current_serving_scope, field_name
                ):
                    changed_scope_fields.append(field_name)
            reason_codes.extend(
                f"source_authority_changed:{code}" for code in changed_authorities
            )
            reason_codes.extend(
                f"current_source_authority_unavailable:{code}"
                for code in unavailable_authorities
            )
            reason_codes.extend(
                f"serving_scope_changed:{field_name}"
                for field_name in changed_scope_fields
            )
            if changed_authorities or changed_scope_fields:
                status = FreshnessStatus.STALE
            elif unavailable_authorities:
                status = FreshnessStatus.UNKNOWN
            else:
                status = FreshnessStatus.CURRENT

        payload = {
            "competitor_profile_version_id": version.competitor_profile_version_id,
            "freshness_status": status.value,
            "changed_authority_codes": sorted(set(changed_authorities)),
            "unavailable_authority_codes": sorted(set(unavailable_authorities)),
            "changed_scope_fields": sorted(set(changed_scope_fields)),
            "reason_codes": sorted(set(reason_codes)),
            "saved_scope_fingerprint": saved_fingerprint,
            "current_scope_fingerprint": current_fingerprint,
        }
        return CompetitorProfileFreshnessAssessment(
            **payload,
            result_hash=stable_hash(payload, version=FRESHNESS_HASH_VERSION),
        )


def _authoritative_codes(values: Sequence[str]) -> list[str]:
    codes = [str(value).strip() for value in values]
    if not codes or any(not code for code in codes):
        raise CompetitorProfileQualityError(
            "authoritative SKU manifest must contain non-empty codes"
        )
    if len(codes) != len(set(codes)):
        raise CompetitorProfileQualityError(
            "authoritative SKU manifest must not contain duplicates"
        )
    return sorted(codes)


def _draft_and_version_id(
    value: ProfileQualityInput,
) -> tuple[CompetitorProfileDraftBundle, str | None]:
    if isinstance(value, MaterializedCompetitorProfile):
        return value.draft, None
    if isinstance(value, CompetitorProfileReadBundle):
        draft = CompetitorProfileDraftBundle(
            profile=value.profile.profile_payload,
            pairs=[row.pair_payload for row in value.pairs],
            selections=[row.selection_payload for row in value.selections],
        )
        return draft, value.version.competitor_profile_version_id
    if isinstance(value, CompetitorProfileDraftBundle):
        return value, None
    raise CompetitorProfileQualityError(
        f"unsupported competitor profile quality input: {type(value).__name__}"
    )


def _version_scope_issues(
    version: CompetitorProfileVersionRecord,
    authoritative_sku_codes: list[str],
) -> list[CompetitorProfileQualityIssue]:
    issues: list[CompetitorProfileQualityIssue] = []
    scope = version.serving_scope
    if (
        version.project_id != scope.project_id
        or version.category_code != scope.category_code
        or version.product_category != scope.product_category
    ):
        issues.append(
            _issue(
                "version_scope_identity_conflict",
                QualityIssueSeverity.P0,
                "source",
                "版本身份与保存的 serving scope 不一致。",
            )
        )
    if version.sku_count != len(authoritative_sku_codes):
        issues.append(
            _issue(
                "version_sku_count_mismatch",
                QualityIssueSeverity.P1,
                "version",
                "版本 SKU 数与权威清单不一致。",
            )
        )
    if scope.authoritative_sku_count != len(authoritative_sku_codes):
        issues.append(
            _issue(
                "serving_scope_sku_count_mismatch",
                QualityIssueSeverity.P0,
                "source",
                "serving scope 的 SKU 数与权威清单不一致。",
            )
        )
    actual_manifest_hash = stable_hash(
        authoritative_sku_codes,
        version=MANIFEST_HASH_VERSION,
    )
    if scope.authoritative_sku_manifest_hash != actual_manifest_hash:
        issues.append(
            _issue(
                "authoritative_manifest_hash_mismatch",
                QualityIssueSeverity.P0,
                "source",
                "权威 SKU 清单与版本锁定的清单哈希不一致。",
            )
        )
    return issues


def _bundle_integrity_issues(
    draft: CompetitorProfileDraftBundle,
) -> list[CompetitorProfileQualityIssue]:
    target = draft.profile.target_sku_code
    issues: list[CompetitorProfileQualityIssue] = []
    for pair in draft.pairs:
        candidate = pair.candidate.sku_code
        if len(pair.relation_assessments) != 7:
            issues.append(
                _issue(
                    "pair_relation_cardinality_invalid",
                    QualityIssueSeverity.P1,
                    "relation",
                    "候选关系没有完整覆盖七类竞品关系。",
                    target,
                    candidate,
                )
            )
        if pair.category_code != draft.profile.category_code:
            issues.append(
                _issue(
                    "pair_category_mismatch",
                    QualityIssueSeverity.P0,
                    "pair",
                    "候选 pair 与目标 SKU 品类不一致。",
                    target,
                    candidate,
                )
            )
    return issues


def _input_hash_issues(
    value: ProfileQualityInput,
    target_sku_code: str,
) -> list[CompetitorProfileQualityIssue]:
    if not isinstance(value, MaterializedCompetitorProfile):
        return []
    expected = stable_hash(
        {
            "target_sku_code": value.target_sku_code,
            "product_category": value.product_category,
            "stage_result_hashes": value.stage_result_hashes,
            "config_version": value.config_version,
            "input_fingerprint": value.input_fingerprint,
        },
        version="competitor_profile_materializer_result_v1",
    )
    if value.result_hash == expected:
        return []
    return [
        _issue(
            "materialized_result_hash_mismatch",
            QualityIssueSeverity.P1,
            "profile",
            "G20 materialized 结果哈希与保存内容不一致。",
            target_sku_code,
        )
    ]


def _quality_status(
    *,
    processing_complete: bool,
    issues: Sequence[CompetitorProfileQualityIssue],
) -> ReleaseQualityStatus:
    if any(row.severity in {"P0", "P1"} for row in issues):
        return ReleaseQualityStatus.BLOCKED
    if not processing_complete:
        return ReleaseQualityStatus.UNASSESSED
    if issues:
        return ReleaseQualityStatus.LIMITED
    return ReleaseQualityStatus.READY


def _issue(
    issue_code: str,
    severity: QualityIssueSeverity,
    scope: str,
    reason_cn: str,
    target_sku_code: str | None = None,
    candidate_sku_code: str | None = None,
) -> CompetitorProfileQualityIssue:
    return CompetitorProfileQualityIssue(
        issue_code=issue_code,
        severity=severity,
        scope=scope,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        reason_cn=reason_cn,
    )


def _sorted_unique_issues(
    issues: Sequence[CompetitorProfileQualityIssue],
) -> list[CompetitorProfileQualityIssue]:
    by_key = {
        (
            row.issue_code,
            row.severity,
            row.scope,
            row.target_sku_code or "",
            row.candidate_sku_code or "",
        ): row
        for row in issues
    }
    severity_order = {"P0": 0, "P1": 1, "P2": 2}
    return [
        by_key[key]
        for key in sorted(
            by_key,
            key=lambda row: (
                severity_order[str(row[1])],
                row[0],
                row[3],
                row[4],
            ),
        )
    ]


def _assert_scope_identity(
    version: CompetitorProfileVersionRecord,
    current_scope: ServingScope,
) -> None:
    actual = (
        current_scope.project_id,
        current_scope.category_code,
        current_scope.product_category,
    )
    expected = (
        version.project_id,
        version.category_code,
        version.product_category,
    )
    if actual != expected:
        raise CompetitorProfileQualityError(
            "freshness comparison cannot cross project or category scope"
        )


__all__ = [
    "FRESHNESS_HASH_VERSION",
    "MANIFEST_HASH_VERSION",
    "QUALITY_HASH_VERSION",
    "CompetitorProfileQualityError",
    "CompetitorProfileQualityService",
    "ProfileQualityInput",
]
