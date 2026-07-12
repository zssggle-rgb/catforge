"""Input context assembly for M12D SKU purchase reason profiles."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import Select, case, false, select

from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
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
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    M12DInputStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    M12DAnchorTaxonomyLoader,
)
from app.services.core3_real_data.purchase_reason_input_quality import (
    M12DInputQualityAdapter,
    legacy_status_from_quality,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DInputQuality,
    M12DInputSnapshot,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.repositories import Core3BaseRepository

SERVING_SCOPE_BATCH_ID_PREFIX = "serving-scope:"


class SkuPurchaseReasonContextBuilder(Core3BaseRepository):
    """Builds an auditable, degradation-aware input context for one SKU."""

    def build_context(
        self,
        *,
        batch_id: str,
        sku_code: str,
        product_category: str = "TV",
        detail_limit: int = 50,
        param_rule_version: str | None = None,
        claim_taxonomy_version: str | None = None,
        claim_rule_version: str | None = None,
        comment_taxonomy_version: str | None = None,
        comment_rule_version: str | None = None,
        market_rule_version: str = CORE3_M07_RULE_VERSION,
        task_taxonomy_version: str | None = None,
        task_rule_version: str | None = None,
        target_group_taxonomy_version: str | None = None,
        target_group_rule_version: str | None = None,
        battlefield_taxonomy_version: str | None = None,
        battlefield_rule_version: str | None = None,
        semantic_market_rule_version: str = CORE3_M11D_RULE_VERSION,
        claim_value_rule_version: str | None = None,
    ) -> M12DSkuPurchaseReasonContext:
        normalized_product_category = str(product_category or "TV").strip().upper()
        version_defaults = _category_version_defaults(normalized_product_category)
        param_rule_version = param_rule_version or version_defaults["param_rule_version"]
        claim_taxonomy_version = claim_taxonomy_version or version_defaults["claim_taxonomy_version"]
        claim_rule_version = claim_rule_version or version_defaults["claim_rule_version"]
        comment_taxonomy_version = comment_taxonomy_version or version_defaults["comment_taxonomy_version"]
        comment_rule_version = comment_rule_version or version_defaults["comment_rule_version"]
        task_taxonomy_version = task_taxonomy_version or version_defaults["task_taxonomy_version"]
        task_rule_version = task_rule_version or version_defaults["task_rule_version"]
        target_group_taxonomy_version = target_group_taxonomy_version or version_defaults["target_group_taxonomy_version"]
        target_group_rule_version = target_group_rule_version or version_defaults["target_group_rule_version"]
        battlefield_taxonomy_version = battlefield_taxonomy_version or version_defaults["battlefield_taxonomy_version"]
        battlefield_rule_version = battlefield_rule_version or version_defaults["battlefield_rule_version"]
        claim_value_rule_version = claim_value_rule_version or version_defaults["claim_value_rule_version"]
        anchor_taxonomy = M12DAnchorTaxonomyLoader().load(
            version_defaults["anchor_taxonomy_version"],
            product_category=normalized_product_category,
        )
        quality_adapter = M12DInputQualityAdapter(anchor_taxonomy)

        param_profile = self._get_param_profile(batch_id, sku_code, param_rule_version)
        claim_profile = self._get_profile(
            entities.Core3SkuClaimFactProfile,
            batch_id,
            sku_code,
            taxonomy_version=claim_taxonomy_version,
            rule_version=claim_rule_version,
        )
        claim_facts = self._list_sku_rows(
            entities.Core3SkuClaimFact,
            batch_id,
            sku_code,
            taxonomy_version=claim_taxonomy_version,
            rule_version=claim_rule_version,
            order_fields=("claim_code", "source_claim_key"),
            limit=detail_limit,
        )
        claim_positions = self._list_sku_rows(
            entities.Core3SkuClaimDimensionPosition,
            batch_id,
            sku_code,
            taxonomy_version=claim_taxonomy_version,
            rule_version=claim_rule_version,
            order_fields=("dimension_code", "position_code"),
            limit=detail_limit,
        )
        comment_profile = self._get_profile(
            entities.Core3SkuCommentFactProfile,
            batch_id,
            sku_code,
            taxonomy_version=comment_taxonomy_version,
            rule_version=comment_rule_version,
        )
        comment_facts = self._list_sku_rows(
            entities.Core3CommentFactAtom,
            batch_id,
            sku_code,
            taxonomy_version=comment_taxonomy_version,
            rule_version=comment_rule_version,
            order_fields=("dimension_code", "subdimension_code"),
            limit=detail_limit,
        )
        market_profile = self._get_market_profile(batch_id, sku_code, market_rule_version)
        task_profile = self._get_profile(
            entities.Core3M09cSkuUserTaskProfile,
            batch_id,
            sku_code,
            taxonomy_version=task_taxonomy_version,
            rule_version=task_rule_version,
        )
        target_group_profile = self._get_profile(
            entities.Core3M10cSkuTargetGroupProfile,
            batch_id,
            sku_code,
            taxonomy_version=target_group_taxonomy_version,
            rule_version=target_group_rule_version,
        )
        battlefield_profile = self._get_profile(
            entities.Core3SkuValueBattlefieldProfile,
            batch_id,
            sku_code,
            taxonomy_version=battlefield_taxonomy_version,
            rule_version=battlefield_rule_version,
        )
        semantic_allocations = self._list_sku_rows(
            entities.Core3SemanticMarketAllocation,
            batch_id,
            sku_code,
            rule_version=semantic_market_rule_version,
            order_fields=("dimension_type", "dimension_code"),
            limit=detail_limit,
        )
        semantic_contributions = self._list_sku_rows(
            entities.Core3SemanticMarketSkuContribution,
            batch_id,
            sku_code,
            rule_version=semantic_market_rule_version,
            order_fields=("dimension_type", "dimension_code"),
            limit=detail_limit,
        )
        claim_values = self._list_sku_rows(
            entities.Core3SkuClaimValueQuantification,
            batch_id,
            sku_code,
            rule_version=claim_value_rule_version,
            order_fields=("claim_code", "context_type", "context_code"),
            limit=detail_limit,
        )
        claim_value_quality_rows = self._list_sku_rows(
            entities.Core3SkuClaimValueQuantification,
            batch_id,
            sku_code,
            rule_version=claim_value_rule_version,
            order_fields=("claim_code", "context_type", "context_code"),
            limit=0,
        )
        claim_attributions = self._list_sku_rows(
            entities.Core3SkuClaimContributionAttribution,
            batch_id,
            sku_code,
            rule_version=claim_value_rule_version,
            order_fields=("context_type", "context_code"),
            limit=detail_limit,
        )

        param_quality = quality_adapter.param_profile(param_profile)
        claim_quality = quality_adapter.claim_profile(
            claim_profile,
            claim_facts,
            param_profile_present=param_profile is not None,
        )
        comment_quality = quality_adapter.comment_profile(comment_profile, comment_facts)
        market_quality = quality_adapter.market_profile(market_profile)
        semantic_quality = quality_adapter.semantic_profiles(
            task_profile,
            target_group_profile,
            battlefield_profile,
        )
        semantic_market_quality = quality_adapter.semantic_market(
            [*semantic_allocations, *semantic_contributions]
        )
        claim_value_quality = quality_adapter.claim_value(claim_value_quality_rows)
        anchor_claim_value_roles = quality_adapter.claim_value_roles_by_anchor(
            claim_value_quality_rows
        )

        param_snapshot = self._param_snapshot(param_profile, param_quality)
        claim_snapshot = self._claim_snapshot(claim_profile, claim_facts, claim_positions, claim_quality)
        comment_snapshot = self._comment_snapshot(comment_profile, comment_facts, comment_quality)
        market_snapshot = self._market_snapshot(market_profile, market_quality)
        semantic_snapshot = self._semantic_profile_snapshot(
            task_profile,
            target_group_profile,
            battlefield_profile,
            semantic_quality,
        )
        semantic_market_snapshot = self._semantic_market_snapshot(
            semantic_allocations,
            semantic_contributions,
            semantic_market_quality,
        )
        claim_value_snapshot = self._claim_value_snapshot(
            claim_values,
            claim_attributions,
            claim_value_quality,
            anchor_claim_value_roles,
            claim_value_quality_rows,
        )
        snapshots = (
            param_snapshot,
            claim_snapshot,
            comment_snapshot,
            market_snapshot,
            semantic_snapshot,
            semantic_market_snapshot,
            claim_value_snapshot,
        )

        identity = _resolve_identity(
            sku_code,
            (
                market_profile,
                param_profile,
                claim_profile,
                comment_profile,
                task_profile,
                target_group_profile,
                battlefield_profile,
                claim_values[0] if claim_values else None,
                claim_attributions[0] if claim_attributions else None,
            ),
        )
        input_status = {
            "param_profile_status": param_snapshot.status,
            "claim_fact_status": claim_snapshot.status,
            "comment_profile_status": comment_snapshot.status,
            "market_profile_status": market_snapshot.status,
            "semantic_profile_status": semantic_snapshot.status,
            "semantic_market_status": semantic_market_snapshot.status,
            "claim_value_status": claim_value_snapshot.status,
        }
        input_quality = {
            snapshot.module_code: snapshot.quality
            for snapshot in snapshots
            if snapshot.quality is not None
        }
        source_refs = [source_ref for snapshot in snapshots for source_ref in snapshot.source_refs]
        missing_reasons = [reason for snapshot in snapshots for reason in snapshot.missing_reasons]
        input_fingerprint = _fingerprint(
            {
                "project_id": self.project_id,
                "category_code": self.category_code.value,
                "batch_id": batch_id,
                "sku_code": sku_code,
                "input_status": input_status,
                "input_quality": {
                    key: value.model_dump(mode="json") for key, value in input_quality.items()
                },
                "input_quality_policy_version": CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
                "source_refs": [source_ref.model_dump(mode="python") for source_ref in source_refs],
            }
        )
        return M12DSkuPurchaseReasonContext(
            project_id=self.project_id,
            category_code=self.category_code,
            batch_id=batch_id,
            product_category=normalized_product_category,
            sku_code=sku_code,
            model_name=identity["model_name"],
            brand_name=identity["brand_name"],
            display_name_cn=identity["display_name_cn"],
            param_profile_status=param_snapshot.status,
            claim_fact_status=claim_snapshot.status,
            comment_profile_status=comment_snapshot.status,
            market_profile_status=market_snapshot.status,
            semantic_profile_status=semantic_snapshot.status,
            semantic_market_status=semantic_market_snapshot.status,
            claim_value_status=claim_value_snapshot.status,
            param_profile=param_snapshot,
            claim_fact_profile=claim_snapshot,
            comment_profile=comment_snapshot,
            market_profile=market_snapshot,
            semantic_profile=semantic_snapshot,
            semantic_market_profile=semantic_market_snapshot,
            claim_value_profile=claim_value_snapshot,
            input_status_json={key: _jsonable_value(value) for key, value in input_status.items()},
            input_quality_json=input_quality,
            input_quality_policy_version=CORE3_M12D_INPUT_QUALITY_POLICY_VERSION,
            missing_input_reasons_json=missing_reasons,
            source_refs_json=source_refs,
            input_fingerprint=input_fingerprint,
        )

    def _get_param_profile(self, batch_id: str, sku_code: str, rule_version: str) -> Any | None:
        stmt = self._sku_stmt(entities.Core3SkuParamProfile, batch_id, sku_code).where(
            entities.Core3SkuParamProfile.rule_version == rule_version
        )
        return self.db.execute(stmt).scalars().first()

    def _get_market_profile(self, batch_id: str, sku_code: str, rule_version: str) -> Any | None:
        stmt = (
            self._sku_stmt(entities.Core3SkuMarketProfile, batch_id, sku_code)
            .where(entities.Core3SkuMarketProfile.rule_version == rule_version)
            .where(entities.Core3SkuMarketProfile.analysis_window == "full_observed_window")
            .where(entities.Core3SkuMarketProfile.is_current.is_(True))
        )
        return self.db.execute(stmt).scalars().first()

    def _get_profile(
        self,
        model_cls: Any,
        batch_id: str,
        sku_code: str,
        *,
        taxonomy_version: str | None = None,
        rule_version: str | None = None,
    ) -> Any | None:
        stmt = self._sku_stmt(model_cls, batch_id, sku_code)
        stmt = _filter_if_present(stmt, model_cls, "taxonomy_version", taxonomy_version)
        stmt = _filter_if_present(stmt, model_cls, "rule_version", rule_version)
        stmt = _filter_if_present(stmt, model_cls, "is_current", True)
        return self.db.execute(stmt).scalars().first()

    def _list_sku_rows(
        self,
        model_cls: Any,
        batch_id: str,
        sku_code: str,
        *,
        taxonomy_version: str | None = None,
        rule_version: str | None = None,
        order_fields: Sequence[str] = (),
        limit: int = 50,
    ) -> list[Any]:
        stmt = self._sku_stmt(model_cls, batch_id, sku_code)
        stmt = _filter_if_present(stmt, model_cls, "taxonomy_version", taxonomy_version)
        stmt = _filter_if_present(stmt, model_cls, "rule_version", rule_version)
        stmt = _filter_if_present(stmt, model_cls, "is_current", True)
        for field_name in order_fields:
            if hasattr(model_cls, field_name):
                stmt = stmt.order_by(getattr(model_cls, field_name))
        if limit > 0:
            stmt = stmt.limit(limit)
        return list(self.db.execute(stmt).scalars())

    def _sku_stmt(self, model_cls: Any, batch_id: str, sku_code: str) -> Select[Any]:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.sku_code == sku_code)
        )
        batch_ids = _batch_ids_from_scope(batch_id)
        if not batch_ids:
            return stmt.where(false())
        if len(batch_ids) == 1:
            return stmt.where(model_cls.batch_id == batch_ids[0])
        order_map = {candidate_batch_id: index for index, candidate_batch_id in enumerate(batch_ids)}
        return stmt.where(model_cls.batch_id.in_(batch_ids)).order_by(
            case(order_map, value=model_cls.batch_id, else_=len(batch_ids))
        )

    def _param_snapshot(
        self,
        profile: Any | None,
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        if profile is None:
            return _missing_snapshot("M03B", "M03B SKU 参数事实画像缺失。", quality)
        status = legacy_status_from_quality(quality)
        return _snapshot(
            "M03B",
            [profile],
            status=status,
            quality=quality,
            summary={
                "model_name": profile.model_name,
                "param_completeness": profile.param_completeness,
                "known_param_count": profile.known_param_count,
                "unknown_param_count": profile.unknown_param_count,
                "conflict_count": profile.conflict_count,
                "review_required_count": profile.review_required_count,
                "param_values_json": profile.param_values_json,
                "core_picture_params_json": profile.core_picture_params_json,
                "core_gaming_params_json": profile.core_gaming_params_json,
                "core_system_params_json": profile.core_system_params_json,
                "core_eye_care_params_json": profile.core_eye_care_params_json,
                "quality_summary_json": profile.quality_summary_json,
            },
            record_fields=(
                "sku_code",
                "model_name",
                "param_completeness",
                "known_param_count",
                "unknown_param_count",
                "conflict_count",
                "profile_hash",
                "rule_version",
            ),
        )

    def _claim_snapshot(
        self,
        profile: Any | None,
        facts: Sequence[Any],
        positions: Sequence[Any],
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        if profile is None:
            return _missing_snapshot("M04C", "M04C SKU 卖点事实画像缺失。", quality)
        status = legacy_status_from_quality(quality)
        return _snapshot(
            "M04C",
            [profile, *facts, *positions],
            status=status,
            quality=quality,
            summary={
                "raw_claim_count": profile.raw_claim_count,
                "matched_claim_count": profile.matched_claim_count,
                "fact_claim_count": profile.fact_claim_count,
                "unsupported_claim_count": profile.unsupported_claim_count,
                "param_unknown_claim_count": profile.param_unknown_claim_count,
                "service_separate_claim_count": profile.service_separate_claim_count,
                "claim_codes": profile.claim_codes,
                "fact_claim_codes": profile.fact_claim_codes,
                "unsupported_claim_codes": profile.unsupported_claim_codes,
                "service_claim_codes": profile.service_claim_codes,
                "dimension_profile_json": profile.dimension_profile_json,
                "dimension_position_profile_json": profile.dimension_position_profile_json,
                "claim_summary_json": profile.claim_summary_json,
                "claim_fact_count": len(facts),
                "dimension_position_count": len(positions),
            },
        )

    def _comment_snapshot(
        self,
        profile: Any | None,
        facts: Sequence[Any],
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        if profile is None:
            return _missing_snapshot("M05C", "M05C SKU 评论事实画像缺失。", quality)
        status = legacy_status_from_quality(quality)
        return _snapshot(
            "M05C",
            [profile, *facts],
            status=status,
            quality=quality,
            summary={
                "comment_sentence_count": profile.comment_sentence_count,
                "matched_sentence_count": profile.matched_sentence_count,
                "fact_atom_count": profile.fact_atom_count,
                "product_fact_sentence_count": profile.product_fact_sentence_count,
                "positive_sentence_count": profile.positive_sentence_count,
                "negative_sentence_count": profile.negative_sentence_count,
                "service_excluded_sentence_count": profile.service_excluded_sentence_count,
                "dimension_summary_json": profile.dimension_summary_json,
                "signal_summary_json": profile.signal_summary_json,
                "supported_param_codes": profile.supported_param_codes,
                "contradicted_param_codes": profile.contradicted_param_codes,
                "supported_claim_codes": profile.supported_claim_codes,
                "contradicted_claim_codes": profile.contradicted_claim_codes,
                "evidence_examples_json": profile.evidence_examples_json,
                "comment_fact_count": len(facts),
            },
            record_fields=(
                "sku_code",
                "dimension_code",
                "subdimension_code",
                "polarity",
                "raw_comment_text",
                "result_hash",
                "rule_version",
                "taxonomy_version",
            ),
        )

    def _market_snapshot(
        self,
        profile: Any | None,
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        if profile is None:
            return _missing_snapshot("M07", "M07 SKU 市场画像缺失。", quality)
        status = legacy_status_from_quality(quality)
        return _snapshot(
            "M07",
            [profile],
            status=status,
            quality=quality,
            summary={
                "analysis_window": profile.analysis_window,
                "active_week_count": profile.active_week_count,
                "market_row_count": profile.market_row_count,
                "screen_size_inch": profile.screen_size_inch,
                "size_segment": profile.size_segment,
                "screen_size_class": profile.screen_size_class,
                "sales_volume_total": profile.sales_volume_total,
                "sales_amount_total": profile.sales_amount_total,
                "price_wavg": profile.price_wavg,
                "price_median": profile.price_median,
                "price_latest": profile.price_latest,
                "price_band_category": profile.price_band_category,
                "price_band_size": profile.price_band_size,
                "price_percentile_in_size": profile.price_percentile_in_size,
                "volume_percentile_in_size": profile.volume_percentile_in_size,
                "amount_percentile_in_size": profile.amount_percentile_in_size,
                "sample_status": profile.sample_status,
                "market_confidence": profile.market_confidence,
                "confidence_level": profile.confidence_level,
                "quality_flags": profile.quality_flags,
            },
        )

    def _semantic_profile_snapshot(
        self,
        task_profile: Any | None,
        target_group_profile: Any | None,
        battlefield_profile: Any | None,
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        rows = [row for row in (task_profile, target_group_profile, battlefield_profile) if row is not None]
        if not rows:
            return _missing_snapshot(
                "M09C_M10C_M11C",
                "M09C/M10C/M11C 语义画像均缺失。",
                quality,
            )
        missing_reasons = []
        if task_profile is None:
            missing_reasons.append("M09C 用户任务画像缺失。")
        if target_group_profile is None:
            missing_reasons.append("M10C 目标客群画像缺失。")
        if battlefield_profile is None:
            missing_reasons.append("M11C 价值战场画像缺失。")
        return _snapshot(
            "M09C_M10C_M11C",
            rows,
            status=legacy_status_from_quality(quality),
            quality=quality,
            summary={
                "user_task": _semantic_row_summary(
                    task_profile,
                    primary_field="primary_user_task_code",
                    secondary_field="secondary_user_task_codes_json",
                    summary_field="user_task_summary_json",
                ),
                "target_group": _semantic_row_summary(
                    target_group_profile,
                    primary_field="primary_target_group_code",
                    secondary_field="secondary_target_group_codes_json",
                    summary_field="target_group_summary_json",
                ),
                "battlefield": _semantic_row_summary(
                    battlefield_profile,
                    primary_field="primary_battlefield_code",
                    secondary_field="secondary_battlefield_codes_json",
                    summary_field="battlefield_summary_json",
                ),
            },
            missing_reasons=missing_reasons,
        )

    def _semantic_market_snapshot(
        self,
        allocations: Sequence[Any],
        contributions: Sequence[Any],
        quality: M12DInputQuality,
    ) -> M12DInputSnapshot:
        rows = [*allocations, *contributions]
        if not rows:
            return _missing_snapshot("M11D", "M11D 语义市场图谱分配缺失。", quality)
        return _snapshot(
            "M11D",
            rows,
            status=legacy_status_from_quality(quality),
            quality=quality,
            summary={
                "allocation_count": len(allocations),
                "contribution_count": len(contributions),
                "dimension_codes": sorted({row.dimension_code for row in rows if getattr(row, "dimension_code", None)}),
                "allocation_weight_total": sum((getattr(row, "allocation_weight", Decimal("0")) or Decimal("0")) for row in rows),
            },
        )

    def _claim_value_snapshot(
        self,
        claim_values: Sequence[Any],
        attributions: Sequence[Any],
        quality: M12DInputQuality,
        anchor_claim_value_roles: Mapping[str, Mapping[str, Sequence[str]]],
        claim_value_quality_rows: Sequence[Any],
    ) -> M12DInputSnapshot:
        rows = [*claim_values, *attributions]
        if not rows:
            return _missing_snapshot(
                "M12C",
                "M12C 用户卖点支付价值缺失；后续画像只能降级生成。",
                quality,
            )
        return _snapshot(
            "M12C",
            rows,
            status=legacy_status_from_quality(quality),
            quality=quality,
            summary={
                "claim_value_count": len(claim_values),
                "attribution_count": len(attributions),
                "claim_codes": [row.claim_code for row in claim_values],
                "claim_value_roles": {
                    row.claim_code: row.claim_value_role
                    for row in claim_values
                    if getattr(row, "claim_code", None)
                },
                "anchor_claim_value_roles": {
                    str(anchor_code): dict(roles)
                    for anchor_code, roles in anchor_claim_value_roles.items()
                },
                "claim_value_role_evidence": _claim_value_role_evidence(
                    claim_value_quality_rows
                ),
                "positive_claims_json": getattr(attributions[0], "positive_claims_json", []) if attributions else [],
                "drag_claims_json": getattr(attributions[0], "drag_claims_json", []) if attributions else [],
                "opportunity_claims_json": getattr(attributions[0], "opportunity_claims_json", []) if attributions else [],
            },
            record_fields=(
                "sku_code",
                "claim_code",
                "claim_name",
                "claim_value_role",
                "quality_flags_json",
                "reason_cn",
                "result_hash",
                "rule_version",
            ),
        )


def _category_version_defaults(product_category: str) -> dict[str, str]:
    if str(product_category).strip().upper() == "AC":
        return {
            "param_rule_version": CORE3_M03B_AC_RULE_VERSION,
            "claim_taxonomy_version": CORE3_M04C_AC_TAXONOMY_VERSION,
            "claim_rule_version": CORE3_M04C_AC_RULE_VERSION,
            "comment_taxonomy_version": CORE3_M05C_AC_TAXONOMY_VERSION,
            "comment_rule_version": CORE3_M05C_AC_RULE_VERSION,
            "task_taxonomy_version": CORE3_M09C_AC_TAXONOMY_VERSION,
            "task_rule_version": CORE3_M09C_AC_RULE_VERSION,
            "target_group_taxonomy_version": CORE3_M10C_AC_TAXONOMY_VERSION,
            "target_group_rule_version": CORE3_M10C_AC_RULE_VERSION,
            "battlefield_taxonomy_version": CORE3_M11C_AC_TAXONOMY_VERSION,
            "battlefield_rule_version": CORE3_M11C_AC_RULE_VERSION,
            "claim_value_rule_version": CORE3_M12C_AC_RULE_VERSION,
            "anchor_taxonomy_version": CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        }
    return {
        "param_rule_version": CORE3_M03B_RULE_VERSION,
        "claim_taxonomy_version": CORE3_M04C_TV_TAXONOMY_VERSION,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
        "comment_taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
        "comment_rule_version": CORE3_M05C_TV_RULE_VERSION,
        "task_taxonomy_version": CORE3_M09C_TV_TAXONOMY_VERSION,
        "task_rule_version": CORE3_M09C_TV_RULE_VERSION,
        "target_group_taxonomy_version": CORE3_M10C_TV_TAXONOMY_VERSION,
        "target_group_rule_version": CORE3_M10C_TV_RULE_VERSION,
        "battlefield_taxonomy_version": CORE3_M11C_TV_TAXONOMY_VERSION,
        "battlefield_rule_version": CORE3_M11C_TV_RULE_VERSION,
        "claim_value_rule_version": CORE3_M12C_TV_RULE_VERSION,
        "anchor_taxonomy_version": CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    }


def _claim_value_role_evidence(
    rows: Sequence[Any],
    *,
    per_role_limit: int = 3,
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        claim_code = str(getattr(row, "claim_code", "") or "")
        role = str(getattr(row, "claim_value_role", "") or "")
        if not claim_code or not role:
            continue
        role_rows = result.setdefault(claim_code, {}).setdefault(role, [])
        if len(role_rows) >= per_role_limit:
            continue
        ref = _source_ref("M12C", row)
        role_rows.append(
            {
                "table_name": ref.table_name,
                "record_id": ref.record_id,
                "result_hash": ref.result_hash,
                "evidence_ids": list(ref.evidence_ids),
                "reason_cn": getattr(row, "reason_cn", None),
                "quality_flags_json": _jsonable_value(
                    getattr(row, "quality_flags_json", None)
                ),
            }
        )
    return result


def _filter_if_present(stmt: Select[Any], model_cls: Any, field_name: str, value: Any | None) -> Select[Any]:
    if value is None or not hasattr(model_cls, field_name):
        return stmt
    column = getattr(model_cls, field_name)
    if isinstance(value, bool):
        return stmt.where(column.is_(value))
    return stmt.where(column == value)


def _missing_snapshot(
    module_code: str,
    reason: str,
    quality: M12DInputQuality | None = None,
) -> M12DInputSnapshot:
    return M12DInputSnapshot(
        module_code=module_code,
        status=M12DInputStatus.MISSING,
        record_count=0,
        missing_reasons=[reason],
        quality=quality,
    )


def _snapshot(
    module_code: str,
    rows: Sequence[Any],
    *,
    status: M12DInputStatus,
    quality: M12DInputQuality,
    summary: Mapping[str, Any],
    missing_reasons: Sequence[str] = (),
    record_fields: Sequence[str] = (),
) -> M12DInputSnapshot:
    source_refs = [_source_ref(module_code, row) for row in rows]
    return M12DInputSnapshot(
        module_code=module_code,
        status=status,
        record_count=len(rows),
        summary=_jsonable_mapping(summary),
        records=[_record_payload(row, record_fields) for row in rows],
        source_refs=source_refs,
        missing_reasons=list(missing_reasons),
        quality=quality,
    )


def _source_ref(module_code: str, row: Any) -> M12DSourceRef:
    return M12DSourceRef(
        module_code=module_code,
        table_name=row.__table__.name,
        record_id=_record_id(row),
        result_hash=_first_attr(row, ("result_hash", "profile_hash", "fact_hash", "position_hash", "input_fingerprint")),
        evidence_ids=_evidence_ids(row),
        extra=_jsonable_mapping(
            {
                "rule_version": getattr(row, "rule_version", None),
                "taxonomy_version": getattr(row, "taxonomy_version", None),
                "is_current": getattr(row, "is_current", None),
            }
        ),
    )


def _record_id(row: Any) -> str:
    primary_keys = list(row.__table__.primary_key.columns)
    if primary_keys:
        value = getattr(row, primary_keys[0].name)
        if value is not None:
            return str(value)
    for field_name in ("profile_id", "sku_code", "claim_code"):
        value = getattr(row, field_name, None)
        if value:
            return str(value)
    return f"{row.__table__.name}:unknown"


def _record_payload(row: Any, fields: Sequence[str]) -> dict[str, Any]:
    selected_fields = fields or (
        "sku_code",
        "brand_name",
        "model_name",
        "claim_code",
        "dimension_code",
        "context_type",
        "context_code",
        "rule_version",
        "taxonomy_version",
        "confidence",
        "market_confidence",
        "attribution_confidence",
        "review_status",
        "review_required",
        "profile_hash",
        "result_hash",
        "fact_hash",
    )
    payload: dict[str, Any] = {"table_name": row.__table__.name, "record_id": _record_id(row)}
    for field_name in selected_fields:
        if hasattr(row, field_name):
            payload[field_name] = _jsonable_value(getattr(row, field_name))
    return payload


def _profile_status(
    row: Any,
    *,
    confidence_attr: str = "confidence",
    conflict_count_attr: str | None = None,
    review_count_attr: str | None = None,
) -> M12DInputStatus:
    if row is None:
        return M12DInputStatus.MISSING
    quality_flags = _as_list(getattr(row, "quality_flags", None)) + _as_list(getattr(row, "quality_flags_json", None))
    if conflict_count_attr and (getattr(row, conflict_count_attr, 0) or 0) > 0:
        return M12DInputStatus.CONFLICT
    if any("conflict" in str(flag).lower() for flag in quality_flags):
        return M12DInputStatus.CONFLICT
    review_count = getattr(row, review_count_attr, 0) if review_count_attr else 0
    if bool(getattr(row, "review_required", False)) or (review_count or 0) > 0:
        return M12DInputStatus.PARTIAL
    confidence = getattr(row, confidence_attr, None)
    if confidence is not None and _decimal(confidence) < Decimal("0.3500"):
        return M12DInputStatus.PARTIAL
    if quality_flags:
        return M12DInputStatus.PARTIAL
    return M12DInputStatus.READY


def _row_or_missing_status(row: Any | None) -> M12DInputStatus:
    if row is None:
        return M12DInputStatus.MISSING
    return _profile_status(row)


def _combine_statuses(statuses: Iterable[M12DInputStatus | str]) -> M12DInputStatus:
    normalized = [M12DInputStatus(str(status)) for status in statuses]
    if not normalized or all(status == M12DInputStatus.MISSING for status in normalized):
        return M12DInputStatus.MISSING
    if any(status == M12DInputStatus.CONFLICT for status in normalized):
        return M12DInputStatus.CONFLICT
    if any(status in {M12DInputStatus.MISSING, M12DInputStatus.PARTIAL, M12DInputStatus.UNKNOWN} for status in normalized):
        return M12DInputStatus.PARTIAL
    return M12DInputStatus.READY


def _semantic_row_summary(row: Any | None, *, primary_field: str, secondary_field: str, summary_field: str) -> dict[str, Any]:
    if row is None:
        return {"status": M12DInputStatus.MISSING.value}
    return _jsonable_mapping(
        {
            "status": (
                M12DInputStatus.READY
                if getattr(row, primary_field, None) and not bool(getattr(row, "review_required", False))
                else M12DInputStatus.PARTIAL
            ),
            "primary_code": getattr(row, primary_field, None),
            "primary_relation_status": getattr(row, "primary_relation_status", None),
            "secondary_codes": getattr(row, secondary_field, []),
            "size_tier": getattr(row, "size_tier", None),
            "price_band_in_size_tier": getattr(row, "price_band_in_size_tier", None),
            "confidence": getattr(row, "confidence", None),
            "summary": getattr(row, summary_field, {}),
        }
    )


def _resolve_identity(sku_code: str, rows: Sequence[Any | None]) -> dict[str, str | None]:
    brand_name = None
    model_name = None
    for row in rows:
        if row is None:
            continue
        brand_name = brand_name or getattr(row, "brand_name", None) or getattr(row, "brand", None)
        model_name = model_name or getattr(row, "model_name", None) or getattr(row, "model_code", None)
    display_name = " ".join(part for part in (brand_name, model_name) if part)
    return {
        "brand_name": brand_name,
        "model_name": model_name,
        "display_name_cn": display_name or sku_code,
    }


def _first_attr(row: Any, field_names: Sequence[str]) -> str | None:
    for field_name in field_names:
        value = getattr(row, field_name, None)
        if value:
            return str(value)
    return None


def _evidence_ids(row: Any) -> list[str]:
    result: list[str] = []
    for field_name in ("evidence_ids", "evidence_ids_json", "market_evidence_ids"):
        for value in _as_list(getattr(row, field_name, None)):
            if value is not None:
                result.append(str(value))
    return sorted(set(result))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _jsonable_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable_value(value) for key, value in payload.items()}


def _batch_ids_from_scope(batch_id: str) -> tuple[str, ...]:
    text = str(batch_id or "").strip()
    if not text:
        return ()
    if not text.startswith(SERVING_SCOPE_BATCH_ID_PREFIX):
        return (text,)
    _, _, raw_batch_ids = text.removeprefix(SERVING_SCOPE_BATCH_ID_PREFIX).partition(":")
    return tuple(item for item in (part.strip() for part in raw_batch_ids.split(",")) if item)


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _jsonable_mapping(value)
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item) for item in value]
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(_jsonable_mapping(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
