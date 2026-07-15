"""Exact-authority, batch-only input provider for competitor profiles."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from sqlalchemy import and_, select
from sqlalchemy.orm import load_only

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION,
    HARD_REQUIRED_TARGET_MODULES,
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileInputRequest,
    CompetitorProfileTargetInputBundle,
    ModuleCategorySnapshot,
    TargetModuleInput,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceRef,
    ServingScope,
    SourceAuthorityRef,
)
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
    CORE3_M12D_RULE_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.repositories import (
    Core3BaseRepository,
    Core3RepositoryContext,
)


class CompetitorProfileInputError(RuntimeError):
    """Base class for safe, non-fallback input-provider errors."""


class CompetitorProfileSourceAuthorityError(CompetitorProfileInputError):
    pass


class CompetitorProfileSourceConflictError(CompetitorProfileInputError):
    pass


class CompetitorProfileTargetNotFoundError(CompetitorProfileInputError):
    pass


_COMMON_QUALITY_FACT_FIELDS = {
    "conflict_count",
    "evidence_lineage_status",
    "lineage_status",
    "processing_status",
    "quality_flags",
    "review_required",
    "review_required_count",
    "review_status",
    "risk_flags",
    "source_lineage_status",
}
_ALGORITHM_FACT_FIELDS_BY_MODULE = {
    "M03B": {
        "model_name",
        "param_values_json",
        "core_picture_params_json",
        "core_gaming_params_json",
        "core_system_params_json",
        "core_eye_care_params_json",
        "param_code",
        "normalized_value",
        "param_value",
        "value",
    },
    "M04C": {
        "claim_codes",
        "fact_claim_codes",
        "service_claim_codes",
        "supported_claim_codes",
        "unsupported_claim_codes",
        "claim_code",
        "claim_status",
    },
    "M05C": {
        "supported_claim_codes",
        "supported_param_codes",
        "contradicted_claim_codes",
        "contradicted_param_codes",
        "unmentioned_claim_codes",
        "unmentioned_param_codes",
        "topic_codes",
        "value_codes",
        "topic_code",
        "support_status",
    },
    "M07": {
        "brand",
        "brand_name",
        "model_name",
        "series",
        "market_pool_key",
        "screen_size_inch",
        "size_segment",
        "price_wavg",
        "weighted_price",
        "avg_weekly_volume",
        "weekly_volume",
        "sales_volume_total",
        "active_week_count",
        "platform_count",
        "promotion_suspect_flag",
        "market_row_count",
        "sales_amount_total",
        "sales_amount",
        "same_pool_price_percentile",
        "price_percentile_in_size",
        "price_percentile",
        "same_pool_volume_percentile",
        "volume_percentile_in_size",
        "sales_percentile",
        "common_week_count",
        "common_platform_count",
        "price_band_size",
    },
    "M09C": {
        "primary_user_task_code",
        "secondary_user_task_codes_json",
        "comment_observed_task_codes_json",
        "latent_capability_task_codes_json",
    },
    "M10C": {
        "primary_target_group_code",
        "secondary_target_group_codes_json",
        "comment_observed_group_codes_json",
        "latent_group_codes_json",
    },
    "M11C": {
        "primary_battlefield_code",
        "secondary_battlefield_codes_json",
        "opportunity_battlefield_codes_json",
        "drag_factor_battlefield_codes_json",
    },
    "M11D": {"dimension_code", "allocation_role"},
    "M12C": {
        "analysis_population",
        "attribution_confidence",
        "brand_name",
        "claim_code",
        "claim_dimension",
        "claim_evidence_strength",
        "claim_name",
        "claim_value_role",
        "claim_role",
        "comment_support_strength",
        "context_name",
        "allocation_role",
        "context_type",
        "context_code",
        "contribution_share_in_sku",
        "estimated_price_premium_abs",
        "estimated_weekly_sales_amount_lift_abs",
        "estimated_weekly_sales_lift_abs",
        "market_window",
        "model_name",
        "param_support_strength",
        "price_band_group",
        "quality_flags_json",
        "reason_cn",
        "semantic_support_strength",
        "size_tier",
        "supporting_dimensions_json",
    },
    "M12D": {
        "brand_name",
        "claim_fact_status",
        "claim_value_status",
        "comment_profile_status",
        "comparison_limitations_json",
        "confidence_level",
        "model_name",
        "display_name_cn",
        "core_reasons_json",
        "core_payment_anchors_json",
        "evidence_summary_json",
        "input_quality_json",
        "input_status_json",
        "market_profile_status",
        "missing_input_reasons_json",
        "param_profile_status",
        "pressure_summary_json",
        "profile_confidence",
        "review_reason_json",
        "role_downgrade_reasons_json",
        "semantic_market_status",
        "semantic_profile_status",
        "source_batch_ids_json",
        "source_merge_strategy",
        "source_refs_json",
        "status",
        "supporting_anchors_json",
        "weak_expression_anchors_json",
        "risk_drag_anchors_json",
        "established_anchors_json",
        "proposition_anchors_json",
    },
}
_TRACE_CONTAINER_FIELDS = {
    "evidence_ids",
    "evidence_ids_json",
    "evidence_refs",
    "evidence_refs_json",
    "market_evidence_ids",
    "param_evidence_ids",
    "raw_row_id",
    "raw_row_ids",
    "raw_row_ids_json",
    "source_file_id",
    "source_file_ids",
    "source_file_ids_json",
    "source_lineage",
    "source_lineage_json",
}
_CONFIDENCE_FIELDS = {
    "confidence",
    "confidence_score",
    "market_confidence",
    "profile_confidence",
}


@dataclass(frozen=True)
class _ModuleSpec:
    module_code: str
    model: Any
    record_id_attr: str
    result_hash_attr: str
    rule_version: str
    taxonomy_version: str
    schema_version: str
    hard_required_for_target: bool = False
    requires_current: bool = True
    has_product_category: bool = True
    single_record_per_sku: bool = True
    extra_filters: Mapping[str, str] = field(default_factory=dict)

    @property
    def record_type(self) -> str:
        return str(self.model.__tablename__)

    @property
    def profile_version(self) -> str:
        return self.rule_version


@dataclass(frozen=True)
class _M12CJoinedSource:
    claim_value: entities.Core3SkuClaimValueQuantification
    context_pool: entities.Core3ClaimValueContextPool
    pool_metric: entities.Core3ClaimValuePoolMetric | None
    attribution: entities.Core3SkuClaimContributionAttribution | None
    result_hash: str


class CompetitorProfileInputProvider(Core3BaseRepository):
    """Read one immutable category snapshot without generating or recalling anything."""

    def __init__(self, context: Core3RepositoryContext) -> None:
        super().__init__(context)

    def resolve_serving_scope(
        self,
        request: CompetitorProfileInputRequest,
    ) -> ServingScope:
        return self.load_category_input_bundle(request).serving_scope

    def build_production_input_request(self) -> CompetitorProfileInputRequest:
        """Resolve the one current published category authority without latest fallback."""

        version_model = entities.Core3PurchaseReasonProfileVersion
        versions = list(
            self.db.execute(
                select(version_model)
                .where(version_model.project_id == self.project_id)
                .where(version_model.category_code == self.category_code.value)
                .where(version_model.product_category == self.category_code.value)
                .where(version_model.rule_version == CORE3_M12D_RULE_VERSION)
                .where(version_model.release_status == "published")
                .where(version_model.is_current.is_(True))
                .order_by(version_model.purchase_reason_version_id)
            ).scalars()
        )
        if len(versions) != 1:
            raise CompetitorProfileSourceAuthorityError(
                "production request requires exactly one current published M12D version"
            )
        version = versions[0]
        if version.release_quality_status not in {"ready", "limited"}:
            raise CompetitorProfileSourceAuthorityError(
                "production request requires a consumable current published M12D version"
            )
        source_batch_ids = _sorted_unique_text(version.source_batch_ids_json)
        if not source_batch_ids or version.batch_id not in source_batch_ids:
            raise CompetitorProfileSourceAuthorityError(
                "production M12D authority has an invalid source batch scope"
            )
        scope = dict(version.input_scope_json or {})
        market_window = str(scope.get("market_window") or "full_observed_window")
        category = self.category_code.value
        semantic_population = (
            "fact_complete_with_comment"
            if category == "TV"
            else "all_semantic_profiles"
        )
        return CompetitorProfileInputRequest(
            project_id=self.project_id,
            category_code=category,
            product_category=category,
            storage_batch_id=str(version.batch_id),
            source_batch_ids=source_batch_ids,
            analysis_population="competitor_profile_full_published_scope",
            semantic_market_analysis_population=semantic_population,
            claim_value_analysis_population="claim_value_ready_with_comment",
            market_window=market_window,
        )

    def list_authoritative_sku_codes(
        self,
        request: CompetitorProfileInputRequest,
    ) -> list[str]:
        self._assert_request_scope(request)
        spec = _module_specs(request.category_code, request)["M07"]
        rows = self._load_generic_rows(request, spec)
        self._assert_single_record_consistency(spec, rows)
        return sorted({str(row.sku_code) for row in rows})

    def load_category_input_bundle(
        self,
        request: CompetitorProfileInputRequest,
    ) -> CompetitorProfileCategoryInputBundle:
        self._assert_request_scope(request)
        specs = _module_specs(request.category_code, request)
        rows_by_module: dict[str, list[Any]] = {}
        prebuilt_modules: dict[
            str,
            tuple[SourceAuthorityRef, list[UpstreamRecordSnapshot]],
        ] = {}

        market_spec = specs["M07"]
        market_rows = self._load_generic_rows(request, market_spec)
        self._assert_single_record_consistency(market_spec, market_rows)
        sku_codes = sorted({str(row.sku_code) for row in market_rows})
        rows_by_module["M07"] = market_rows

        for module_code, spec in specs.items():
            if module_code == "M07":
                continue
            if module_code == "M12C":
                prebuilt_modules[module_code] = self._load_m12c_snapshots(
                    request,
                    spec,
                    sku_codes=sku_codes,
                )
                rows_by_module[module_code] = []
                continue
            rows = self._load_generic_rows(
                request,
                spec,
                sku_codes=sku_codes,
            )
            self._assert_single_record_consistency(spec, rows)
            rows_by_module[module_code] = rows

        m12d_version, m12d_rows = self._load_m12d(
            request,
            sku_codes=sku_codes,
        )
        rows_by_module["M12D"] = m12d_rows

        modules: dict[str, ModuleCategorySnapshot] = {}
        authorities: dict[str, SourceAuthorityRef] = {}
        for module_code in sorted(rows_by_module):
            if module_code == "M12D":
                authority = self._m12d_authority(
                    request,
                    m12d_version,
                    m12d_rows,
                )
                snapshots = [
                    _record_snapshot_from_m12d(row, authority)
                    for row in m12d_rows
                ]
                hard_required = False
            elif module_code in prebuilt_modules:
                authority, snapshots = prebuilt_modules[module_code]
                hard_required = specs[module_code].hard_required_for_target
            else:
                spec = specs[module_code]
                authority = _generic_authority(request, spec, rows_by_module[module_code])
                snapshots = [
                    _record_snapshot(row, spec, authority, request.category_code)
                    for row in rows_by_module[module_code]
                ]
                hard_required = spec.hard_required_for_target
            authorities[module_code] = authority
            modules[module_code] = _module_snapshot(
                module_code=module_code,
                authority=authority,
                snapshots=snapshots,
                hard_required=hard_required,
            )

        manifest_hash = stable_hash(
            sku_codes,
            version="competitor_profile_authoritative_sku_manifest_v1",
        )
        scope_fingerprint = stable_hash(
            {
                "project_id": request.project_id,
                "category_code": request.category_code,
                "storage_batch_id": request.storage_batch_id,
                "source_batch_ids": request.source_batch_ids,
                "analysis_population": request.analysis_population,
                "semantic_market_analysis_population": (
                    request.semantic_market_analysis_population
                ),
                "claim_value_analysis_population": (
                    request.claim_value_analysis_population
                ),
                "market_window": request.market_window,
                "manifest_hash": manifest_hash,
                "authorities": {
                    code: authorities[code].result_hash
                    for code in sorted(authorities)
                },
            },
            version="competitor_profile_release_scope_v1",
        )
        serving_scope = ServingScope(
            project_id=request.project_id,
            category_code=request.category_code,
            product_category=request.product_category,
            analysis_population=request.analysis_population,
            market_window=request.market_window,
            taxonomy_version=(
                f"competitor_profile_{request.category_code.lower()}_source_manifest_v1"
            ),
            storage_batch_id=request.storage_batch_id,
            source_batch_ids=request.source_batch_ids,
            source_authorities=authorities,
            sku_prefixes=[request.category_code],
            authoritative_sku_count=len(sku_codes),
            authoritative_sku_manifest_hash=manifest_hash,
            release_scope_key=(
                f"{request.project_id}:{request.category_code}:"
                f"{scope_fingerprint.rsplit(':', 1)[-1][:24]}"
            ),
        )
        input_fingerprint = stable_hash(
            {
                "provider_version": COMPETITOR_PROFILE_INPUT_PROVIDER_VERSION,
                "serving_scope": serving_scope.model_dump(mode="python"),
                "module_hashes": {
                    code: modules[code].result_hash for code in sorted(modules)
                },
            },
            version="competitor_profile_category_input_v1",
        )
        return CompetitorProfileCategoryInputBundle(
            serving_scope=serving_scope,
            authoritative_sku_codes=sku_codes,
            modules=modules,
            input_fingerprint=input_fingerprint,
        )

    def load_target_input(
        self,
        category_bundle: CompetitorProfileCategoryInputBundle,
        target_sku_code: str,
    ) -> CompetitorProfileTargetInputBundle:
        sku_code = target_sku_code.strip().upper()
        if sku_code not in category_bundle.authoritative_sku_codes:
            raise CompetitorProfileTargetNotFoundError(
                f"target SKU is outside the authoritative manifest: {sku_code}"
            )
        module_inputs: dict[str, TargetModuleInput] = {}
        evidence_refs: list[EvidenceRef] = []
        hard_block_reasons: list[str] = []
        limitations: list[str] = []
        for module_code in sorted(category_bundle.modules):
            module = category_bundle.modules[module_code]
            records = list(module.records_by_sku.get(sku_code, []))
            hard_required = module_code in HARD_REQUIRED_TARGET_MODULES
            if records:
                refs = [_evidence_ref(row) for row in records]
                evidence_refs.extend(refs)
                module_inputs[module_code] = TargetModuleInput(
                    module_code=module_code,
                    availability="present",
                    hard_required=hard_required,
                    records=records,
                    evidence_refs=refs,
                    input_fingerprint=_target_module_hash(module_code, records),
                )
                continue
            reason = f"{module_code.lower()}_sku_not_covered_by_locked_authority"
            if hard_required:
                hard_block_reasons.append(reason)
            else:
                limitations.append(reason)
            module_inputs[module_code] = TargetModuleInput(
                module_code=module_code,
                availability="unknown",
                hard_required=hard_required,
                missing_reason_code=reason,
                input_fingerprint=stable_hash(
                    {
                        "module_code": module_code,
                        "target_sku_code": sku_code,
                        "availability": "unknown",
                        "reason": reason,
                        "authority_hash": module.authority.result_hash,
                    },
                    version="competitor_profile_target_module_input_v1",
                ),
            )

        market_records = module_inputs["M07"].records
        target_identity = _target_identity(sku_code, market_records)
        analysis_state = (
            "blocked"
            if hard_block_reasons
            else "partial"
            if limitations
            else "ready"
        )
        input_fingerprint = stable_hash(
            {
                "category_input_fingerprint": category_bundle.input_fingerprint,
                "target_sku_code": sku_code,
                "module_inputs": {
                    code: module_inputs[code].input_fingerprint
                    for code in sorted(module_inputs)
                },
                "hard_block_reasons": sorted(hard_block_reasons),
                "limitations": sorted(limitations),
            },
            version="competitor_profile_target_input_v1",
        )
        return CompetitorProfileTargetInputBundle(
            serving_scope=category_bundle.serving_scope,
            target_sku_code=sku_code,
            target_identity=target_identity,
            modules=module_inputs,
            analysis_state=analysis_state,
            hard_block_reasons=sorted(hard_block_reasons),
            limitations=sorted(limitations),
            evidence_refs=sorted(
                evidence_refs,
                key=lambda row: (
                    row.module_code,
                    row.source_batch_id or "",
                    row.record_id,
                ),
            ),
            input_fingerprint=input_fingerprint,
        )

    def _assert_request_scope(self, request: CompetitorProfileInputRequest) -> None:
        if (
            request.project_id != self.project_id
            or request.category_code != self.category_code.value
        ):
            raise ValueError(
                "input request project/category does not match provider context"
            )

    def _load_generic_rows(
        self,
        request: CompetitorProfileInputRequest,
        spec: _ModuleSpec,
        *,
        sku_codes: Sequence[str] | None = None,
    ) -> list[Any]:
        model = spec.model
        stmt = (
            select(model)
            .options(
                load_only(
                    *_projected_columns(
                        model,
                        spec.module_code,
                        required={
                            "project_id",
                            "category_code",
                            "batch_id",
                            "sku_code",
                            "rule_version",
                            spec.record_id_attr,
                            spec.result_hash_attr,
                            *(("product_category",) if spec.has_product_category else ()),
                        },
                    )
                )
            )
            .where(model.project_id == request.project_id)
            .where(model.category_code == request.category_code)
            .where(model.batch_id.in_(request.source_batch_ids))
            .where(model.rule_version == spec.rule_version)
            .where(model.sku_code.like(f"{request.category_code}%"))
        )
        if spec.has_product_category:
            stmt = stmt.where(model.product_category == request.product_category)
        if hasattr(model, "taxonomy_version"):
            stmt = stmt.where(model.taxonomy_version == spec.taxonomy_version)
        if spec.requires_current:
            stmt = stmt.where(model.is_current.is_(True))
        if sku_codes is not None:
            stmt = stmt.where(model.sku_code.in_(sku_codes))
        for field_name, value in spec.extra_filters.items():
            stmt = stmt.where(getattr(model, field_name) == value)
        return list(
            self.db.execute(
                stmt.order_by(
                    model.sku_code,
                    model.batch_id,
                    getattr(model, spec.record_id_attr),
                )
            ).scalars()
        )

    def _load_m12c_snapshots(
        self,
        request: CompetitorProfileInputRequest,
        spec: _ModuleSpec,
        *,
        sku_codes: Sequence[str],
    ) -> tuple[SourceAuthorityRef, list[UpstreamRecordSnapshot]]:
        claim_value = entities.Core3SkuClaimValueQuantification
        context_pool = entities.Core3ClaimValueContextPool
        pool_metric = entities.Core3ClaimValuePoolMetric
        attribution = entities.Core3SkuClaimContributionAttribution
        stmt = (
            select(claim_value, context_pool, pool_metric, attribution)
            .join(
                context_pool,
                and_(
                    context_pool.pool_id == claim_value.pool_id,
                    context_pool.project_id == claim_value.project_id,
                    context_pool.category_code == claim_value.category_code,
                    context_pool.batch_id == claim_value.batch_id,
                    context_pool.product_category == claim_value.product_category,
                    context_pool.market_window == claim_value.market_window,
                    context_pool.analysis_population
                    == claim_value.analysis_population,
                    context_pool.rule_version == claim_value.rule_version,
                    context_pool.is_current.is_(True),
                ),
            )
            .outerjoin(
                pool_metric,
                and_(
                    pool_metric.metric_id == claim_value.metric_id,
                    pool_metric.project_id == claim_value.project_id,
                    pool_metric.category_code == claim_value.category_code,
                    pool_metric.batch_id == claim_value.batch_id,
                    pool_metric.product_category == claim_value.product_category,
                    pool_metric.market_window == claim_value.market_window,
                    pool_metric.analysis_population == claim_value.analysis_population,
                    pool_metric.rule_version == claim_value.rule_version,
                    pool_metric.is_current.is_(True),
                ),
            )
            .outerjoin(
                attribution,
                and_(
                    attribution.project_id == claim_value.project_id,
                    attribution.category_code == claim_value.category_code,
                    attribution.batch_id == claim_value.batch_id,
                    attribution.product_category == claim_value.product_category,
                    attribution.market_window == claim_value.market_window,
                    attribution.analysis_population == claim_value.analysis_population,
                    attribution.sku_code == claim_value.sku_code,
                    attribution.context_type == claim_value.context_type,
                    attribution.context_code == claim_value.context_code,
                    attribution.size_tier == claim_value.size_tier,
                    attribution.price_band_group == claim_value.price_band_group,
                    attribution.rule_version == claim_value.rule_version,
                    attribution.is_current.is_(True),
                ),
            )
            .where(claim_value.project_id == request.project_id)
            .where(claim_value.category_code == request.category_code)
            .where(claim_value.batch_id.in_(request.source_batch_ids))
            .where(claim_value.product_category == request.product_category)
            .where(claim_value.market_window == request.market_window)
            .where(
                claim_value.analysis_population
                == request.claim_value_analysis_population
            )
            .where(claim_value.rule_version == spec.rule_version)
            .where(claim_value.sku_code.in_(sku_codes))
            .where(claim_value.sku_code.like(f"{request.category_code}%"))
            .where(claim_value.is_current.is_(True))
            .order_by(
                claim_value.sku_code,
                claim_value.batch_id,
                claim_value.sku_claim_value_id,
            )
        )
        joined = []
        for value_row, pool_row, metric_row, attribution_row in self.db.execute(
            stmt
        ).all():
            component_hashes = {
                "claim_value": str(value_row.result_hash),
                "context_pool": str(pool_row.pool_hash),
                "pool_metric": (
                    str(metric_row.result_hash) if metric_row is not None else None
                ),
                "attribution": (
                    str(attribution_row.result_hash)
                    if attribution_row is not None
                    else None
                ),
            }
            joined.append(
                _M12CJoinedSource(
                    claim_value=value_row,
                    context_pool=pool_row,
                    pool_metric=metric_row,
                    attribution=attribution_row,
                    result_hash=stable_hash(
                        component_hashes,
                        version="competitor_profile_m12c_joined_source_v1",
                    ),
                )
            )
        authority = _m12c_authority(request, spec, joined)
        snapshots = [
            _record_snapshot_from_m12c(row, authority) for row in joined
        ]
        return authority, snapshots

    def _load_m12d(
        self,
        request: CompetitorProfileInputRequest,
        *,
        sku_codes: Sequence[str],
    ) -> tuple[entities.Core3PurchaseReasonProfileVersion | None, list[Any]]:
        version_model = entities.Core3PurchaseReasonProfileVersion
        versions = list(
            self.db.execute(
                select(version_model)
                .where(version_model.project_id == request.project_id)
                .where(version_model.category_code == request.category_code)
                .where(version_model.product_category == request.product_category)
                .where(version_model.batch_id == request.storage_batch_id)
                .where(version_model.rule_version == CORE3_M12D_RULE_VERSION)
                .where(version_model.release_status == "published")
                .where(version_model.is_current.is_(True))
                .order_by(version_model.purchase_reason_version_id)
            ).scalars()
        )
        if len(versions) > 1:
            raise CompetitorProfileSourceAuthorityError(
                "M12D allows at most exactly one current published version in the locked scope"
            )
        if not versions:
            return None, []
        version = versions[0]
        if version.release_quality_status not in {"ready", "limited"}:
            raise CompetitorProfileSourceAuthorityError(
                "M12D current published version has non-consumable release quality"
            )
        version_batches = _sorted_unique_text(version.source_batch_ids_json)
        if not version_batches or not set(version_batches).issubset(
            request.source_batch_ids
        ):
            raise CompetitorProfileSourceAuthorityError(
                "M12D source batches are outside the locked serving scope"
            )
        _assert_optional_scope_value(
            version.input_scope_json,
            "product_category",
            request.product_category,
        )
        _assert_optional_scope_value(
            version.input_scope_json,
            "market_window",
            request.market_window,
        )
        profile = entities.Core3SkuPurchaseReasonProfile
        rows = list(
            self.db.execute(
                select(profile)
                .options(
                    load_only(
                        *_projected_columns(
                            profile,
                            "M12D",
                            required={
                                "purchase_reason_profile_id",
                                "project_id",
                                "category_code",
                                "product_category",
                                "batch_id",
                                "sku_code",
                                "m12d_profile_version",
                                "schema_version",
                                "rule_version",
                                "result_hash",
                            },
                        )
                    )
                )
                .where(profile.project_id == request.project_id)
                .where(profile.category_code == request.category_code)
                .where(profile.product_category == request.product_category)
                .where(
                    profile.purchase_reason_version_id
                    == version.purchase_reason_version_id
                )
                .where(profile.m12d_profile_version == version.m12d_profile_version)
                .where(profile.rule_version == version.rule_version)
                .where(profile.batch_id.in_(request.source_batch_ids))
                .where(profile.sku_code.in_(sku_codes))
                .where(profile.sku_code.like(f"{request.category_code}%"))
                .where(profile.release_status == "published")
                .where(profile.is_current.is_(True))
                .order_by(profile.sku_code, profile.purchase_reason_profile_id)
            ).scalars()
        )
        self._assert_m12d_consistency(rows)
        return version, rows

    @staticmethod
    def _assert_single_record_consistency(
        spec: _ModuleSpec,
        rows: Sequence[Any],
    ) -> None:
        if not rows and spec.hard_required_for_target:
            raise CompetitorProfileSourceAuthorityError(
                f"{spec.module_code} exact source authority has no rows"
            )
        if not rows:
            return
        if not spec.single_record_per_sku:
            return
        hashes_by_sku: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            result_hash = str(getattr(row, spec.result_hash_attr) or "").strip()
            if not result_hash:
                raise CompetitorProfileSourceConflictError(
                    f"{spec.module_code} contains an empty result hash"
                )
            hashes_by_sku[str(row.sku_code)].add(result_hash)
        conflicted = sorted(
            sku_code
            for sku_code, result_hashes in hashes_by_sku.items()
            if len(result_hashes) > 1
        )
        if conflicted:
            raise CompetitorProfileSourceConflictError(
                f"{spec.module_code} has conflicting locked rows for SKU: {conflicted[0]}"
            )

    @staticmethod
    def _assert_m12d_consistency(rows: Sequence[Any]) -> None:
        hashes_by_sku: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            result_hash = str(row.result_hash or "").strip()
            if not result_hash:
                raise CompetitorProfileSourceConflictError(
                    "M12D contains an empty result hash"
                )
            hashes_by_sku[str(row.sku_code)].add(result_hash)
        if any(len(values) > 1 for values in hashes_by_sku.values()):
            raise CompetitorProfileSourceConflictError(
                "M12D has conflicting current profiles for one SKU"
            )

    @staticmethod
    def _m12d_authority(
        request: CompetitorProfileInputRequest,
        version: entities.Core3PurchaseReasonProfileVersion | None,
        rows: Sequence[Any],
    ) -> SourceAuthorityRef:
        if version is None:
            return SourceAuthorityRef(
                module_code="M12D",
                project_id=request.project_id,
                category_code=request.category_code,
                product_category=request.product_category,
                profile_version="unavailable",
                schema_version="sku_purchase_reason_profile_v1",
                rule_version=CORE3_M12D_RULE_VERSION,
                taxonomy_version="unavailable",
                release_status="unavailable",
                is_current=False,
                source_batch_ids=request.source_batch_ids,
                result_hash=stable_hash(
                    {
                        "module_code": "M12D",
                        "scope": request.model_dump(mode="json"),
                        "availability": "unavailable",
                    },
                    version="competitor_profile_m12d_unavailable_authority_v1",
                ),
            )
        source_batch_ids = (
            _sorted_unique_text(version.source_batch_ids_json)
            or request.source_batch_ids
        )
        refs = [
            {
                "record_id": str(row.purchase_reason_profile_id),
                "sku_code": str(row.sku_code),
                "source_batch_id": str(row.batch_id),
                "result_hash": str(row.result_hash),
            }
            for row in rows
        ]
        consumable = bool(rows) and version.release_quality_status in {"ready", "limited"}
        return SourceAuthorityRef(
            module_code="M12D",
            project_id=request.project_id,
            category_code=request.category_code,
            product_category=request.product_category,
            profile_version=str(version.m12d_profile_version),
            schema_version=str(version.schema_version),
            rule_version=str(version.rule_version),
            taxonomy_version="not_applicable",
            release_status="published" if consumable else "unavailable",
            is_current=consumable,
            source_batch_ids=source_batch_ids,
            result_hash=stable_hash(
                {
                    "version_id": version.purchase_reason_version_id,
                    "version_result_hash": version.result_hash,
                    "records": refs,
                },
                version="competitor_profile_m12d_authority_v1",
            ),
        )


def _module_specs(
    category_code: str,
    request: CompetitorProfileInputRequest,
) -> dict[str, _ModuleSpec]:
    ac = category_code == "AC"
    return {
        "M03B": _ModuleSpec(
            module_code="M03B",
            model=entities.Core3SkuParamProfile,
            record_id_attr="sku_param_profile_id",
            result_hash_attr="profile_hash",
            rule_version=(
                CORE3_M03B_AC_RULE_VERSION if ac else CORE3_M03B_RULE_VERSION
            ),
            taxonomy_version=(
                CORE3_M03B_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M03B_TAXONOMY_VERSION
            ),
            schema_version="core3_sku_param_profile_v1",
            hard_required_for_target=True,
            requires_current=False,
            has_product_category=False,
        ),
        "M04C": _ModuleSpec(
            module_code="M04C",
            model=entities.Core3SkuClaimFactProfile,
            record_id_attr="claim_profile_id",
            result_hash_attr="profile_hash",
            rule_version=(CORE3_M04C_AC_RULE_VERSION if ac else CORE3_M04C_TV_RULE_VERSION),
            taxonomy_version=(
                CORE3_M04C_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M04C_TV_TAXONOMY_VERSION
            ),
            schema_version="core3_sku_claim_fact_profile_v1",
        ),
        "M05C": _ModuleSpec(
            module_code="M05C",
            model=entities.Core3SkuCommentFactProfile,
            record_id_attr="comment_profile_id",
            result_hash_attr="profile_hash",
            rule_version=(CORE3_M05C_AC_RULE_VERSION if ac else CORE3_M05C_TV_RULE_VERSION),
            taxonomy_version=(
                CORE3_M05C_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M05C_TV_TAXONOMY_VERSION
            ),
            schema_version="core3_sku_comment_fact_profile_v1",
        ),
        "M07": _ModuleSpec(
            module_code="M07",
            model=entities.Core3SkuMarketProfile,
            record_id_attr="profile_id",
            result_hash_attr="result_hash",
            rule_version=CORE3_M07_RULE_VERSION,
            taxonomy_version="not_applicable",
            schema_version="core3_sku_market_profile_v2",
            hard_required_for_target=True,
            has_product_category=False,
            extra_filters={"analysis_window": request.market_window},
        ),
        "M09C": _ModuleSpec(
            module_code="M09C",
            model=entities.Core3M09cSkuUserTaskProfile,
            record_id_attr="profile_id",
            result_hash_attr="profile_hash",
            rule_version=(CORE3_M09C_AC_RULE_VERSION if ac else CORE3_M09C_TV_RULE_VERSION),
            taxonomy_version=(
                CORE3_M09C_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M09C_TV_TAXONOMY_VERSION
            ),
            schema_version="core3_m09c_sku_user_task_profile_v1",
        ),
        "M10C": _ModuleSpec(
            module_code="M10C",
            model=entities.Core3M10cSkuTargetGroupProfile,
            record_id_attr="profile_id",
            result_hash_attr="profile_hash",
            rule_version=(CORE3_M10C_AC_RULE_VERSION if ac else CORE3_M10C_TV_RULE_VERSION),
            taxonomy_version=(
                CORE3_M10C_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M10C_TV_TAXONOMY_VERSION
            ),
            schema_version="core3_m10c_sku_target_group_profile_v1",
        ),
        "M11C": _ModuleSpec(
            module_code="M11C",
            model=entities.Core3SkuValueBattlefieldProfile,
            record_id_attr="profile_id",
            result_hash_attr="profile_hash",
            rule_version=(CORE3_M11C_AC_RULE_VERSION if ac else CORE3_M11C_TV_RULE_VERSION),
            taxonomy_version=(
                CORE3_M11C_AC_TAXONOMY_VERSION
                if ac
                else CORE3_M11C_TV_TAXONOMY_VERSION
            ),
            schema_version="core3_sku_value_battlefield_profile_v1",
        ),
        "M11D": _ModuleSpec(
            module_code="M11D",
            model=entities.Core3SemanticMarketSkuContribution,
            record_id_attr="contribution_id",
            result_hash_attr="result_hash",
            rule_version=CORE3_M11D_RULE_VERSION,
            taxonomy_version="not_applicable",
            schema_version="core3_semantic_market_sku_contribution_v1",
            single_record_per_sku=False,
            extra_filters={
                "analysis_population": request.semantic_market_analysis_population,
                "market_window": request.market_window,
            },
        ),
        "M12C": _ModuleSpec(
            module_code="M12C",
            model=entities.Core3SkuClaimValueQuantification,
            record_id_attr="sku_claim_value_id",
            result_hash_attr="result_hash",
            rule_version=(CORE3_M12C_AC_RULE_VERSION if ac else CORE3_M12C_TV_RULE_VERSION),
            taxonomy_version="not_applicable",
            schema_version="core3_sku_claim_value_quantification_v1",
            single_record_per_sku=False,
            extra_filters={
                "analysis_population": request.claim_value_analysis_population,
                "market_window": request.market_window,
            },
        ),
    }


def _generic_authority(
    request: CompetitorProfileInputRequest,
    spec: _ModuleSpec,
    rows: Sequence[Any],
) -> SourceAuthorityRef:
    source_batch_ids = sorted({str(row.batch_id) for row in rows})
    refs = [
        {
            "record_id": str(getattr(row, spec.record_id_attr)),
            "sku_code": str(row.sku_code),
            "source_batch_id": str(row.batch_id),
            "result_hash": str(getattr(row, spec.result_hash_attr)),
        }
        for row in rows
    ]
    available = bool(rows)
    return SourceAuthorityRef(
        module_code=spec.module_code,
        project_id=request.project_id,
        category_code=request.category_code,
        product_category=request.product_category,
        profile_version=spec.profile_version,
        schema_version=spec.schema_version,
        rule_version=spec.rule_version,
        taxonomy_version=spec.taxonomy_version,
        release_status="published" if available else "unavailable",
        is_current=available,
        source_batch_ids=source_batch_ids or request.source_batch_ids,
        result_hash=stable_hash(
            refs,
            version=f"competitor_profile_{spec.module_code.lower()}_authority_v1",
        ),
    )


def _m12c_authority(
    request: CompetitorProfileInputRequest,
    spec: _ModuleSpec,
    rows: Sequence[_M12CJoinedSource],
) -> SourceAuthorityRef:
    refs = [
        {
            "record_id": str(row.claim_value.sku_claim_value_id),
            "sku_code": str(row.claim_value.sku_code),
            "source_batch_id": str(row.claim_value.batch_id),
            "result_hash": row.result_hash,
        }
        for row in rows
    ]
    source_batch_ids = sorted(
        {str(row.claim_value.batch_id) for row in rows}
    )
    available = bool(rows)
    return SourceAuthorityRef(
        module_code="M12C",
        project_id=request.project_id,
        category_code=request.category_code,
        product_category=request.product_category,
        profile_version=spec.profile_version,
        schema_version=spec.schema_version,
        rule_version=spec.rule_version,
        taxonomy_version=spec.taxonomy_version,
        release_status="published" if available else "unavailable",
        is_current=available,
        source_batch_ids=source_batch_ids or request.source_batch_ids,
        result_hash=stable_hash(
            refs,
            version="competitor_profile_m12c_authority_v2",
        ),
    )


def _record_snapshot(
    row: Any,
    spec: _ModuleSpec,
    authority: SourceAuthorityRef,
    category_code: str,
) -> UpstreamRecordSnapshot:
    return UpstreamRecordSnapshot(
        module_code=spec.module_code,
        record_type=spec.record_type,
        record_id=str(getattr(row, spec.record_id_attr)),
        sku_code=str(row.sku_code),
        project_id=str(row.project_id),
        category_code=str(row.category_code),
        product_category=str(getattr(row, "product_category", category_code)),
        source_batch_id=str(row.batch_id),
        profile_version=authority.profile_version,
        schema_version=authority.schema_version,
        rule_version=str(row.rule_version),
        taxonomy_version=authority.taxonomy_version,
        result_hash=str(getattr(row, spec.result_hash_attr)),
        facts=_row_facts(row, spec.module_code),
    )


def _record_snapshot_from_m12c(
    row: _M12CJoinedSource,
    authority: SourceAuthorityRef,
) -> UpstreamRecordSnapshot:
    source = row.claim_value
    facts = _row_facts(source, "M12C")
    facts["pool_effect"] = _m12c_pool_effect(
        row.pool_metric,
        row.context_pool,
    )
    facts["context_pool_result_hash"] = str(row.context_pool.pool_hash)
    if row.pool_metric is not None:
        facts["pool_metric_result_hash"] = str(row.pool_metric.result_hash)
    if row.attribution is not None:
        facts["claim_contribution_attribution"] = _m12c_attribution_payload(
            row.attribution
        )
        facts["claim_contribution_result_hash"] = str(row.attribution.result_hash)
    missing_components = []
    if row.pool_metric is None:
        missing_components.append("pool_metric")
    if row.attribution is None:
        missing_components.append("claim_contribution_attribution")
    if missing_components:
        facts["review_required"] = True
        facts["review_reason_json"] = {
            "reason_code": "m12c_typed_component_missing",
            "missing_components": missing_components,
        }
    facts["claim_value_result_hash"] = str(source.result_hash)
    return UpstreamRecordSnapshot(
        module_code="M12C",
        record_type=source.__tablename__,
        record_id=str(source.sku_claim_value_id),
        sku_code=str(source.sku_code),
        project_id=str(source.project_id),
        category_code=str(source.category_code),
        product_category=str(source.product_category),
        source_batch_id=str(source.batch_id),
        profile_version=authority.profile_version,
        schema_version=authority.schema_version,
        rule_version=str(source.rule_version),
        taxonomy_version=authority.taxonomy_version,
        result_hash=row.result_hash,
        facts=facts,
    )


def _m12c_pool_effect(
    row: entities.Core3ClaimValuePoolMetric | None,
    pool: entities.Core3ClaimValueContextPool,
) -> dict[str, Any]:
    return {
        "pool_claim_price_delta_abs": (
            str(row.price_premium_abs) if row is not None else None
        ),
        "pool_claim_weekly_sales_delta_abs": (
            str(row.weekly_sales_lift_abs) if row is not None else None
        ),
        "pool_claim_weekly_sales_amount_delta_abs": (
            str(row.weekly_sales_amount_lift_abs) if row is not None else None
        ),
        "with_claim_sku_count": pool.with_claim_sku_count,
        "without_claim_sku_count": pool.without_claim_sku_count,
        "effect_confidence": (
            str(row.effect_confidence) if row is not None else None
        ),
        "business_summary_cn": row.business_summary_cn if row is not None else None,
    }


def _m12c_attribution_payload(
    row: entities.Core3SkuClaimContributionAttribution,
) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "context_type": row.context_type,
        "context_code": row.context_code,
        "context_name": row.context_name,
        "size_tier": row.size_tier,
        "price_band_group": row.price_band_group,
        "baseline": {
            "price": str(row.baseline_price),
            "weekly_sales_volume": str(row.baseline_weekly_sales_volume),
            "weekly_sales_amount": str(row.baseline_weekly_sales_amount),
        },
        "sku_observed": {
            "price": str(row.sku_price),
            "weekly_sales_volume": str(row.sku_weekly_sales_volume),
            "weekly_sales_amount": str(row.sku_weekly_sales_amount),
        },
        "sku_gap_vs_baseline": {
            "price_premium_abs": str(row.sku_price_premium_abs),
            "weekly_sales_lift_abs": str(row.sku_weekly_sales_lift_abs),
            "weekly_sales_amount_lift_abs": str(
                row.sku_weekly_sales_amount_lift_abs
            ),
        },
        "positive_claims": row.positive_claims_json or [],
        "drag_claims": row.drag_claims_json or [],
        "opportunity_claims": row.opportunity_claims_json or [],
        "attribution_summary_cn": row.attribution_summary_cn,
        "confidence": str(row.confidence),
    }


def _record_snapshot_from_m12d(
    row: entities.Core3SkuPurchaseReasonProfile,
    authority: SourceAuthorityRef,
) -> UpstreamRecordSnapshot:
    return UpstreamRecordSnapshot(
        module_code="M12D",
        record_type=row.__tablename__,
        record_id=str(row.purchase_reason_profile_id),
        sku_code=str(row.sku_code),
        project_id=str(row.project_id),
        category_code=str(row.category_code),
        product_category=str(row.product_category),
        source_batch_id=str(row.batch_id),
        profile_version=str(row.m12d_profile_version),
        schema_version=str(row.schema_version),
        rule_version=str(row.rule_version),
        taxonomy_version=authority.taxonomy_version,
        result_hash=str(row.result_hash),
        facts=_row_facts(row, "M12D"),
    )


def _module_snapshot(
    *,
    module_code: str,
    authority: SourceAuthorityRef,
    snapshots: Sequence[UpstreamRecordSnapshot],
    hard_required: bool,
) -> ModuleCategorySnapshot:
    grouped: dict[str, list[UpstreamRecordSnapshot]] = defaultdict(list)
    for row in snapshots:
        grouped[row.sku_code].append(row)
    records_by_sku = {
        sku_code: sorted(
            grouped[sku_code],
            key=lambda row: (row.source_batch_id, row.record_id),
        )
        for sku_code in sorted(grouped)
    }
    return ModuleCategorySnapshot(
        module_code=module_code,
        authority=authority,
        hard_required_for_target=hard_required,
        record_count=len(snapshots),
        sku_count=len(records_by_sku),
        records_by_sku=records_by_sku,
        result_hash=authority.result_hash,
    )


def _target_module_hash(
    module_code: str,
    records: Sequence[UpstreamRecordSnapshot],
) -> str:
    return stable_hash(
        {
            "module_code": module_code,
            "records": [
                {
                    "record_id": row.record_id,
                    "source_batch_id": row.source_batch_id,
                    "result_hash": row.result_hash,
                }
                for row in records
            ],
        },
        version="competitor_profile_target_module_input_v1",
    )


def _evidence_ref(row: UpstreamRecordSnapshot) -> EvidenceRef:
    evidence_ids, source_file_ids, raw_row_ids, confidence = _trace_fields(row.facts)
    return EvidenceRef(
        module_code=row.module_code,
        profile_version=row.profile_version,
        rule_version=row.rule_version,
        taxonomy_version=row.taxonomy_version,
        record_type=row.record_type,
        record_id=row.record_id,
        result_hash=row.result_hash,
        source_batch_id=row.source_batch_id,
        evidence_ids=evidence_ids,
        source_file_ids=source_file_ids,
        raw_row_ids=raw_row_ids,
        confidence=confidence,
    )


def _trace_fields(
    facts: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], Decimal | None]:
    evidence_ids: set[str] = set()
    source_file_ids: set[str] = set()
    raw_row_ids: set[str] = set()
    confidences: list[Decimal] = []

    def add_text(target: set[str], value: Any) -> None:
        values = value if isinstance(value, (list, tuple, set)) else [value]
        for item in values:
            if isinstance(item, Mapping):
                visit(item)
                continue
            text = str(item or "").strip()
            if text:
                target.add(text)

    def add_confidence(value: Any) -> None:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return
        if Decimal("0") <= parsed <= Decimal("1"):
            confidences.append(parsed)

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                normalized = str(key).lower()
                if normalized in {"evidence_id", "evidence_ids", "evidence_ids_json"} or (
                    normalized.endswith("_evidence_ids")
                    or normalized.endswith("_evidence_ids_json")
                ):
                    add_text(evidence_ids, child)
                elif normalized in {
                    "source_file_id",
                    "source_file_ids",
                    "source_file_ids_json",
                }:
                    add_text(source_file_ids, child)
                elif normalized in {"raw_row_id", "raw_row_ids", "raw_row_ids_json"}:
                    add_text(raw_row_ids, child)
                elif normalized in _CONFIDENCE_FIELDS:
                    add_confidence(child)
                elif normalized in {
                    "evidence_refs",
                    "evidence_refs_json",
                    "source_lineage",
                    "source_lineage_json",
                }:
                    visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)

    visit(facts)
    return (
        sorted(evidence_ids),
        sorted(source_file_ids),
        sorted(raw_row_ids),
        min(confidences) if confidences else None,
    )


def _target_identity(
    sku_code: str,
    market_records: Sequence[UpstreamRecordSnapshot],
) -> dict[str, Any]:
    if not market_records:
        return {"sku_code": sku_code}
    facts = market_records[0].facts
    return {
        "sku_code": sku_code,
        "brand_name": facts.get("brand_name") or facts.get("brand"),
        "model_name": facts.get("model_name"),
        "series": facts.get("series"),
        "market_pool_key": facts.get("market_pool_key"),
        "screen_size_inch": facts.get("screen_size_inch"),
        "size_segment": facts.get("size_segment"),
        "product_category": market_records[0].product_category,
    }


def _row_facts(row: Any, module_code: str) -> dict[str, Any]:
    """Keep only consumed facts plus normalized audit lineage from an ORM row."""

    columns = {column.name for column in row.__table__.columns}
    allowed = _ALGORITHM_FACT_FIELDS_BY_MODULE[module_code] | (
        _COMMON_QUALITY_FACT_FIELDS
    )
    facts = {
        name: getattr(row, name)
        for name in sorted(allowed & columns)
    }
    trace_payload = {
        name: getattr(row, name)
        for name in sorted(
            (_TRACE_CONTAINER_FIELDS | _CONFIDENCE_FIELDS) & columns
        )
        if getattr(row, name) is not None
    }
    evidence_ids, source_file_ids, raw_row_ids, confidence = _trace_fields(
        trace_payload
    )
    if evidence_ids:
        facts["evidence_ids"] = evidence_ids
    if source_file_ids:
        facts["source_file_ids"] = source_file_ids
    if raw_row_ids:
        facts["raw_row_ids"] = raw_row_ids
    if confidence is not None:
        facts["confidence"] = confidence
    return facts


def _projected_columns(
    model: Any,
    module_code: str,
    *,
    required: set[str],
) -> list[Any]:
    """Project only fields consumed by the typed snapshot and audit lineage."""

    names = (
        required
        | _ALGORITHM_FACT_FIELDS_BY_MODULE[module_code]
        | _COMMON_QUALITY_FACT_FIELDS
        | _TRACE_CONTAINER_FIELDS
        | _CONFIDENCE_FIELDS
    )
    return [getattr(model, name) for name in sorted(names) if hasattr(model, name)]


def _sorted_unique_text(values: Any) -> list[str]:
    return sorted({str(value).strip() for value in (values or []) if str(value).strip()})


def _assert_optional_scope_value(
    scope: Mapping[str, Any] | None,
    key: str,
    expected: str,
) -> None:
    value = (scope or {}).get(key)
    if value is not None and str(value).upper() != expected.upper():
        raise CompetitorProfileSourceAuthorityError(
            f"M12D locked input scope conflicts on {key}"
        )


__all__ = [
    "CompetitorProfileInputError",
    "CompetitorProfileInputProvider",
    "CompetitorProfileSourceAuthorityError",
    "CompetitorProfileSourceConflictError",
    "CompetitorProfileTargetNotFoundError",
]
