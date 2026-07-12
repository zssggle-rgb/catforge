"""Batch generation for draft M12D purchase reason profiles."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Sequence

from app.services.core3_real_data.analyst.analyst_repository import batch_ids_from_scope
from app.services.core3_real_data.constants import (
    CORE3_M12D_MODULE_VERSION,
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_RULE_VERSION,
    CORE3_M12D_SCHEMA_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    Core3RunStatus,
    M12DProfileStatus,
    M12DReleaseStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import AnchorCandidateGenerator
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import M12DAnchorTaxonomyLoader
from app.services.core3_real_data.purchase_reason_context_builder import SkuPurchaseReasonContextBuilder
from app.services.core3_real_data.purchase_reason_profile_repositories import PurchaseReasonProfileRepository
from app.services.core3_real_data.purchase_reason_release_quality import M12DReleaseQualityEvaluator
from app.services.core3_real_data.purchase_reason_profile_scoring import PurchaseReasonProfileScoringService
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorTaxonomy,
    M12DFocusSkuValidationResult,
    M12DProfileScoreResult,
    M12DPurchaseReasonAnchorRecord,
    M12DPurchaseReasonProfileVersionRecord,
    M12DScoredPurchaseReasonAnchor,
    M12DServiceResult,
    M12DSkuPurchaseReasonContext,
    M12DSkuPurchaseReasonProfileRecord,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


class M12DPurchaseReasonBatchGenerationError(ValueError):
    """Raised when a draft M12D batch cannot be generated."""


class PurchaseReasonProfileBatchGenerator:
    """Generate draft M12D profiles for a SKU batch without publishing them."""

    def __init__(
        self,
        context: Core3RepositoryContext,
        *,
        context_builder: SkuPurchaseReasonContextBuilder | None = None,
        taxonomy_loader: M12DAnchorTaxonomyLoader | None = None,
        scoring_service: PurchaseReasonProfileScoringService | None = None,
        release_quality_evaluator: M12DReleaseQualityEvaluator | None = None,
        repository: PurchaseReasonProfileRepository | None = None,
    ) -> None:
        self.context = context
        self.context_builder = context_builder or SkuPurchaseReasonContextBuilder(context)
        self.taxonomy_loader = taxonomy_loader or M12DAnchorTaxonomyLoader()
        self.scoring_service = scoring_service or PurchaseReasonProfileScoringService()
        self.release_quality_evaluator = release_quality_evaluator or M12DReleaseQualityEvaluator()
        self.repository = repository or PurchaseReasonProfileRepository(context)

    def generate(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
        m12d_profile_version: str,
        product_category: str = "TV",
        taxonomy_version: str = CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        storage_batch_id: str | None = None,
        run_id: str | None = None,
        module_run_id: str | None = None,
        write: bool = False,
        generated_by: str = "system",
        detail_limit: int = 50,
        focus_validation_results: Sequence[M12DFocusSkuValidationResult | dict[str, Any]] | None = None,
    ) -> M12DServiceResult:
        normalized_product_category = product_category.strip().upper()
        if normalized_product_category not in {"TV", "AC"}:
            raise M12DPurchaseReasonBatchGenerationError(
                f"M12D batch generation currently supports TV and AC only: {product_category}"
            )
        if taxonomy_version == CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION and normalized_product_category != "TV":
            raise M12DPurchaseReasonBatchGenerationError("TV M12D taxonomy cannot be used for non-TV batch generation.")
        if taxonomy_version == CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION and normalized_product_category != "AC":
            raise M12DPurchaseReasonBatchGenerationError("AC M12D taxonomy cannot be used for non-AC batch generation.")
        normalized_sku_codes = _normalize_sku_codes(sku_codes)
        if not normalized_sku_codes:
            raise M12DPurchaseReasonBatchGenerationError("sku_codes is required.")
        source_batch_ids = tuple(batch_ids_from_scope(batch_id))
        normalized_storage_batch_id = (storage_batch_id or _default_storage_batch_id(batch_id)).strip()
        if not normalized_storage_batch_id:
            raise M12DPurchaseReasonBatchGenerationError("storage_batch_id is required.")

        taxonomy = self.taxonomy_loader.load(taxonomy_version, product_category=normalized_product_category)
        candidate_generator = AnchorCandidateGenerator(taxonomy)
        now = datetime.now(timezone.utc)
        version_id = _stable_id(
            "m12d_ver",
            self.context.project_id,
            self.context.category_code.value,
            normalized_storage_batch_id,
            m12d_profile_version,
            CORE3_M12D_RULE_VERSION,
        )
        profiles: list[M12DSkuPurchaseReasonProfileRecord] = []
        anchors: list[M12DPurchaseReasonAnchorRecord] = []
        warnings: list[str] = []
        failures: list[dict[str, str]] = []

        for sku_code in normalized_sku_codes:
            profile_id = _stable_id(
                "m12d_prof",
                self.context.project_id,
                self.context.category_code.value,
                normalized_storage_batch_id,
                m12d_profile_version,
                sku_code,
            )
            try:
                sku_context = self.context_builder.build_context(
                    batch_id=batch_id,
                    sku_code=sku_code,
                    product_category=normalized_product_category,
                    detail_limit=detail_limit,
                )
                candidate_set = candidate_generator.generate(sku_context)
                score_result = self.scoring_service.score(candidate_set=candidate_set, context=sku_context)
                profile = _profile_record(
                    context=sku_context,
                    score_result=score_result,
                    taxonomy=taxonomy,
                    profile_id=profile_id,
                    version_id=version_id,
                    batch_id=normalized_storage_batch_id,
                    read_batch_id=batch_id,
                    source_batch_ids=source_batch_ids,
                    m12d_profile_version=m12d_profile_version,
                    run_id=run_id,
                    module_run_id=module_run_id,
                    generated_at=now,
                )
                anchor_records = _anchor_records(
                    context=sku_context,
                    score_result=score_result,
                    profile_id=profile_id,
                    version_id=version_id,
                    batch_id=normalized_storage_batch_id,
                    source_batch_ids=source_batch_ids,
                    m12d_profile_version=m12d_profile_version,
                    run_id=run_id,
                    module_run_id=module_run_id,
                )
                profiles.append(profile)
                anchors.extend(anchor_records)
            except Exception as exc:  # noqa: BLE001 - keep one SKU failure from blocking the batch.
                message = str(exc) or exc.__class__.__name__
                warnings.append(f"{sku_code}: {message}")
                failures.append({"sku_code": sku_code, "message": message})
                profiles.append(
                    _failed_profile_record(
                        sku_code=sku_code,
                        profile_id=profile_id,
                        version_id=version_id,
                        project_id=self.context.project_id,
                        category_code=self.context.category_code,
                        batch_id=normalized_storage_batch_id,
                        read_batch_id=batch_id,
                        source_batch_ids=source_batch_ids,
                        m12d_profile_version=m12d_profile_version,
                        run_id=run_id,
                        module_run_id=module_run_id,
                        generated_at=now,
                        message=message,
                    )
                )

        quality_summary = _quality_summary(profiles, anchors, failures)
        release_quality_evaluation = self.release_quality_evaluator.evaluate(
            category_code=self.context.category_code,
            product_category=normalized_product_category,
            profiles=profiles,
            expected_sku_count=len(normalized_sku_codes),
            focus_validation_results=focus_validation_results,
        )
        quality_summary["release_quality_evaluation"] = release_quality_evaluation.model_dump(
            mode="json"
        )
        version = _version_record(
            version_id=version_id,
            project_id=self.context.project_id,
            category_code=self.context.category_code,
            batch_id=normalized_storage_batch_id,
            read_batch_id=batch_id,
            source_batch_ids=source_batch_ids,
            m12d_profile_version=m12d_profile_version,
            run_id=run_id,
            module_run_id=module_run_id,
            product_category=normalized_product_category,
            generated_by=generated_by,
            sku_codes=normalized_sku_codes,
            quality_summary=quality_summary,
            failures=failures,
        )

        created_count = updated_count = reused_count = 0
        if write:
            version_result = self.repository.save_versions([version])
            profile_result = self.repository.save_profiles(profiles)
            anchor_result = self.repository.save_anchors(anchors)
            self.context.db.flush()
            created_count = version_result.created_count + profile_result.created_count + anchor_result.created_count
            updated_count = version_result.updated_count + profile_result.updated_count + anchor_result.updated_count
            reused_count = version_result.reused_count + profile_result.reused_count + anchor_result.reused_count

        summary = {
            **quality_summary,
            "batch_id": normalized_storage_batch_id,
            "read_batch_id": batch_id,
            "source_batch_ids": list(source_batch_ids),
            "m12d_profile_version": m12d_profile_version,
            "taxonomy_version": taxonomy_version,
            "rule_version": CORE3_M12D_RULE_VERSION,
            "schema_version": CORE3_M12D_SCHEMA_VERSION,
            "module_version": CORE3_M12D_MODULE_VERSION,
            "write_enabled": write,
            "created_output_count": created_count,
            "updated_output_count": updated_count,
            "reused_output_count": reused_count,
            "failure_skus": failures,
        }
        status = (
            Core3RunStatus.WARNING
            if failures or quality_summary["failed_count"]
            else Core3RunStatus.SUCCESS
        )
        return M12DServiceResult(
            status=status,
            input_count=len(normalized_sku_codes),
            output_count=len(profiles),
            created_output_count=created_count,
            updated_output_count=updated_count,
            reused_output_count=reused_count,
            warnings=warnings,
            profiles=tuple(profiles),
            anchors=tuple(anchors),
            summary=summary,
        )


def _profile_record(
    *,
    context: M12DSkuPurchaseReasonContext,
    score_result: M12DProfileScoreResult,
    taxonomy: M12DAnchorTaxonomy,
    profile_id: str,
    version_id: str,
    batch_id: str,
    read_batch_id: str,
    source_batch_ids: Sequence[str],
    m12d_profile_version: str,
    run_id: str | None,
    module_run_id: str | None,
    generated_at: datetime,
) -> M12DSkuPurchaseReasonProfileRecord:
    core_reason_labels = _anchor_labels(taxonomy, score_result.core_payment_anchors_json)
    evidence_summary = {
        "taxonomy_version": score_result.taxonomy_version,
        "read_batch_id": read_batch_id,
        "scored_anchor_count": len(score_result.scored_anchors),
        "core_payment_count": len(score_result.core_payment_anchors_json),
        "supporting_count": len(score_result.supporting_anchors_json),
        "weak_expression_count": len(score_result.weak_expression_anchors_json),
        "risk_drag_count": len(score_result.risk_drag_anchors_json),
        "evidence_domain_counts": _domain_counts(score_result.scored_anchors),
        "confidence_basis": score_result.confidence_basis_json,
        "input_quality_policy_version": context.input_quality_policy_version,
    }
    hash_payload = {
        "context_input_fingerprint": context.input_fingerprint,
        "score_result": score_result.model_dump(mode="python"),
        "batch_id": batch_id,
        "read_batch_id": read_batch_id,
        "source_batch_ids": list(source_batch_ids),
        "m12d_profile_version": m12d_profile_version,
    }
    return M12DSkuPurchaseReasonProfileRecord(
        purchase_reason_profile_id=profile_id,
        purchase_reason_version_id=version_id,
        project_id=context.project_id,
        category_code=context.category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        product_category=context.product_category,
        m12d_profile_version=m12d_profile_version,
        sku_code=context.sku_code,
        model_name=context.model_name,
        brand_name=context.brand_name,
        display_name_cn=context.display_name_cn,
        status=score_result.status,
        profile_confidence=score_result.profile_confidence,
        confidence_level=score_result.confidence_level,
        core_reasons_json=core_reason_labels,
        core_payment_anchors_json=score_result.core_payment_anchors_json,
        supporting_anchors_json=score_result.supporting_anchors_json,
        weak_expression_anchors_json=score_result.weak_expression_anchors_json,
        risk_drag_anchors_json=score_result.risk_drag_anchors_json,
        evidence_summary_json=evidence_summary,
        input_status_json=context.input_status_json,
        input_quality_json=context.input_quality_json,
        param_profile_status=context.param_profile_status,
        claim_fact_status=context.claim_fact_status,
        comment_profile_status=context.comment_profile_status,
        market_profile_status=context.market_profile_status,
        semantic_profile_status=context.semantic_profile_status,
        semantic_market_status=context.semantic_market_status,
        claim_value_status=context.claim_value_status,
        source_batch_ids_json=list(source_batch_ids),
        source_merge_strategy="serving_scope_priority_by_domain",
        missing_input_reasons_json=context.missing_input_reasons_json,
        role_downgrade_reasons_json=score_result.role_downgrade_reasons_json,
        risk_flags_json=score_result.risk_flags_json,
        source_refs_json=_source_refs_json(context.source_refs_json),
        release_status=M12DReleaseStatus.DRAFT,
        generated_at=generated_at,
        input_fingerprint=context.input_fingerprint,
        result_hash=_fingerprint(hash_payload),
        is_current=True,
        processing_status=(
            "failed"
            if score_result.status == M12DProfileStatus.FAILED.value
            else "success"
        ),
        review_required=score_result.review_required,
        review_status="review_required" if score_result.review_required else "auto_pass",
        review_reason_json=score_result.review_reason_json,
    )


def _failed_profile_record(
    *,
    sku_code: str,
    profile_id: str,
    version_id: str,
    project_id: str,
    category_code: Any,
    batch_id: str,
    read_batch_id: str,
    source_batch_ids: Sequence[str],
    m12d_profile_version: str,
    run_id: str | None,
    module_run_id: str | None,
    generated_at: datetime,
    message: str,
) -> M12DSkuPurchaseReasonProfileRecord:
    hash_payload = {
        "sku_code": sku_code,
        "batch_id": batch_id,
        "read_batch_id": read_batch_id,
        "source_batch_ids": list(source_batch_ids),
        "m12d_profile_version": m12d_profile_version,
        "error": message,
    }
    return M12DSkuPurchaseReasonProfileRecord(
        purchase_reason_profile_id=profile_id,
        purchase_reason_version_id=version_id,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        m12d_profile_version=m12d_profile_version,
        sku_code=sku_code,
        display_name_cn=sku_code,
        status=M12DProfileStatus.FAILED,
        source_batch_ids_json=list(source_batch_ids),
        source_merge_strategy="serving_scope_priority_by_domain",
        missing_input_reasons_json=[{"reason_code": "m12d_generation_failed", "message": message}],
        release_status=M12DReleaseStatus.DRAFT,
        generated_at=generated_at,
        input_fingerprint=_fingerprint(hash_payload),
        result_hash=_fingerprint(hash_payload),
        is_current=True,
        processing_status="failed",
        review_required=True,
        review_status="failed",
        review_reason_json={"reasons": ["m12d_generation_failed"], "message": message},
    )


def _anchor_records(
    *,
    context: M12DSkuPurchaseReasonContext,
    score_result: M12DProfileScoreResult,
    profile_id: str,
    version_id: str,
    batch_id: str,
    source_batch_ids: Sequence[str],
    m12d_profile_version: str,
    run_id: str | None,
    module_run_id: str | None,
) -> list[M12DPurchaseReasonAnchorRecord]:
    records: list[M12DPurchaseReasonAnchorRecord] = []
    for anchor in score_result.scored_anchors:
        hash_payload = {
            "context_input_fingerprint": context.input_fingerprint,
            "anchor": anchor.model_dump(mode="python"),
            "batch_id": batch_id,
            "source_batch_ids": list(source_batch_ids),
            "m12d_profile_version": m12d_profile_version,
        }
        records.append(
            M12DPurchaseReasonAnchorRecord(
                purchase_reason_anchor_id=_stable_id(
                    "m12d_anchor",
                    context.project_id,
                    _value(context.category_code),
                    batch_id,
                    m12d_profile_version,
                    context.sku_code,
                    anchor.anchor_code,
                ),
                purchase_reason_profile_id=profile_id,
                purchase_reason_version_id=version_id,
                project_id=context.project_id,
                category_code=context.category_code,
                batch_id=batch_id,
                run_id=run_id,
                module_run_id=module_run_id,
                product_category=context.product_category,
                m12d_profile_version=m12d_profile_version,
                sku_code=context.sku_code,
                model_name=context.model_name,
                brand_name=context.brand_name,
                anchor_code=anchor.anchor_code,
                anchor_cn=anchor.anchor_cn,
                anchor_family_code=anchor.anchor_family_code,
                anchor_rank=anchor.anchor_rank,
                role=anchor.role,
                evidence_strength=anchor.evidence_strength,
                confidence=anchor.confidence,
                evidence_domains_json=anchor.evidence_domains_json,
                domain_scores_json=anchor.domain_scores_json,
                support_summary_cn=anchor.support_summary_cn,
                weakness_summary_cn=anchor.weakness_summary_cn,
                source_refs_json=_source_refs_json(anchor.source_refs_json),
                risk_flags_json=anchor.risk_flags_json,
                role_reason_json=anchor.role_reason_json,
                downgrade_reason_code=anchor.downgrade_reason_code,
                release_status=M12DReleaseStatus.DRAFT,
                input_fingerprint=anchor.input_fingerprint,
                result_hash=_fingerprint(hash_payload),
                is_current=True,
            )
        )
    return records


def _version_record(
    *,
    version_id: str,
    project_id: str,
    category_code: Any,
    batch_id: str,
    read_batch_id: str,
    source_batch_ids: Sequence[str],
    m12d_profile_version: str,
    run_id: str | None,
    module_run_id: str | None,
    product_category: str,
    generated_by: str,
    sku_codes: Sequence[str],
    quality_summary: dict[str, Any],
    failures: Sequence[dict[str, str]],
) -> M12DPurchaseReasonProfileVersionRecord:
    input_scope = {
        "read_batch_id": read_batch_id,
        "storage_batch_id": batch_id,
        "source_batch_ids": list(source_batch_ids),
        "sku_codes": list(sku_codes),
        "product_category": product_category,
    }
    validation_summary = {
        "failed_skus": list(failures),
        "low_confidence_skus": quality_summary["low_confidence_skus"],
        "review_required_skus": quality_summary["review_required_skus"],
        "core_payment_missing_skus": quality_summary["core_payment_missing_skus"],
        "release_quality_failure_reason_codes": quality_summary[
            "release_quality_evaluation"
        ]["failure_reason_codes"],
        "release_system_issues": quality_summary["release_quality_evaluation"][
            "system_issues"
        ],
    }
    hash_payload = {
        "m12d_profile_version": m12d_profile_version,
        "rule_version": CORE3_M12D_RULE_VERSION,
        "input_scope": input_scope,
        "quality_summary": quality_summary,
        "validation_summary": validation_summary,
    }
    return M12DPurchaseReasonProfileVersionRecord(
        purchase_reason_version_id=version_id,
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        run_id=run_id,
        module_run_id=module_run_id,
        product_category=product_category,
        m12d_profile_version=m12d_profile_version,
        release_status=M12DReleaseStatus.DRAFT,
        release_quality_status=quality_summary["release_quality_evaluation"][
            "release_quality_status"
        ],
        is_current=False,
        generated_by=generated_by,
        source_batch_ids_json=list(source_batch_ids),
        input_scope_json=input_scope,
        quality_summary_json=quality_summary,
        validation_summary_json=validation_summary,
        sku_count=quality_summary["total_sku_count"],
        ready_count=quality_summary["ready_count"],
        review_required_count=quality_summary["review_required_count"],
        missing_input_count=quality_summary["missing_input_count"],
        failed_count=quality_summary["failed_count"],
        low_confidence_count=quality_summary["low_confidence_count"],
        core_payment_missing_count=quality_summary["core_payment_missing_count"],
        input_fingerprint=_fingerprint(input_scope),
        result_hash=_fingerprint(hash_payload),
    )


def _quality_summary(
    profiles: Sequence[M12DSkuPurchaseReasonProfileRecord],
    anchors: Sequence[M12DPurchaseReasonAnchorRecord],
    failures: Sequence[dict[str, str]],
) -> dict[str, Any]:
    total = len(profiles)
    ready = [profile for profile in profiles if _value(profile.status) == M12DProfileStatus.READY.value]
    ready_limited = [
        profile
        for profile in profiles
        if _value(profile.status) == M12DProfileStatus.READY_LIMITED.value
    ]
    review_required = [profile for profile in profiles if bool(profile.review_required)]
    missing_input = [profile for profile in profiles if _value(profile.status) == M12DProfileStatus.MISSING_INPUT.value]
    low_confidence = [profile for profile in profiles if Decimal(str(profile.profile_confidence)) < Decimal("0.5000")]
    core_missing = [profile for profile in profiles if not profile.core_payment_anchors_json]
    role_counts: dict[str, int] = {}
    anchor_code_counts: dict[str, int] = {}
    for anchor in anchors:
        role_counts[_value(anchor.role)] = role_counts.get(_value(anchor.role), 0) + 1
        anchor_code_counts[anchor.anchor_code] = anchor_code_counts.get(anchor.anchor_code, 0) + 1
    failed_profiles = [profile for profile in profiles if _value(profile.status) == M12DProfileStatus.FAILED.value]
    return {
        "total_sku_count": total,
        "profile_record_count": len(profiles),
        "anchor_record_count": len(anchors),
        "ready_count": len(ready),
        "ready_limited_count": len(ready_limited),
        "usable_profile_count": len(ready) + len(ready_limited),
        "review_required_count": len(review_required),
        "missing_input_count": len(missing_input),
        "failed_count": len(failed_profiles),
        "low_confidence_count": len(low_confidence),
        "core_payment_missing_count": len(core_missing),
        "success_rate": _rate(total - len(failed_profiles), total),
        "low_confidence_rate": _rate(len(low_confidence), total),
        "core_payment_missing_rate": _rate(len(core_missing), total),
        "review_required_rate": _rate(len(review_required), total),
        "role_counts": role_counts,
        "top_anchor_codes": _top_counts(anchor_code_counts),
        "failed_skus": list(failures),
        "low_confidence_skus": _brief_profiles(low_confidence),
        "review_required_skus": _brief_profiles(review_required),
        "core_payment_missing_skus": _brief_profiles(core_missing),
    }


def _normalize_sku_codes(sku_codes: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for sku_code in sku_codes:
        normalized = str(sku_code or "").strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def _default_storage_batch_id(batch_id: str) -> str:
    batch_ids = batch_ids_from_scope(batch_id)
    return batch_ids[0] if batch_ids else str(batch_id or "").strip()


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = _fingerprint(parts)[:24]
    return f"{prefix}_{digest}"


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _value(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _source_refs_json(source_refs: Iterable[Any]) -> list[dict[str, Any]]:
    return [_jsonable(source_ref) for source_ref in source_refs]


def _domain_counts(anchors: Sequence[M12DScoredPurchaseReasonAnchor]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for anchor in anchors:
        for domain in anchor.evidence_domains_json:
            key = _value(domain)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _anchor_labels(taxonomy: M12DAnchorTaxonomy, anchor_codes: Sequence[str]) -> list[str]:
    by_code = taxonomy.purchase_reasons_by_code()
    return [by_code[code].purchase_reason_cn for code in anchor_codes if code in by_code]


def _brief_profiles(profiles: Sequence[M12DSkuPurchaseReasonProfileRecord]) -> list[dict[str, Any]]:
    return [
        {
            "sku_code": profile.sku_code,
            "display_name_cn": profile.display_name_cn,
            "status": _value(profile.status),
            "profile_confidence": str(profile.profile_confidence),
            "core_payment_anchors": list(profile.core_payment_anchors_json),
            "review_reasons": list((profile.review_reason_json or {}).get("reasons") or []),
        }
        for profile in profiles
    ]


def _rate(count: int, total: int) -> str:
    if total <= 0:
        return "0.0000"
    return f"{Decimal(count) / Decimal(total):.4f}"


def _top_counts(counts: dict[str, int], *, limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"code": code, "count": count}
        for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]
