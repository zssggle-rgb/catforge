#!/usr/bin/env python3
"""Build the deterministic G29 contract over the frozen G28 legacy inventory.

This is a schema-only compatibility utility.  It reads local G28 artifacts and
writes one local, deterministic gzip contract; it never imports repositories,
opens a database connection, calls an LLM, or publishes an external artifact.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sys
from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import Any


ARTIFACT_DIR = Path(__file__).resolve().parent
REPO_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "apps").is_dir() and (parent / "docs").is_dir()
)
API_ROOT = REPO_ROOT / "apps/api-server"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.core3_real_data.analyst import (  # noqa: E402
    competitor_profile_v1_1_schemas as schemas,
)


INVENTORY_PATH = ARTIFACT_DIR / "G28_legacy_leaf_mapping_inventory.json.gz"
OUTPUT_PATH = ARTIFACT_DIR / "G29_legacy_typed_mapping_contract.json.gz"
REAL_FIXTURE_NAMES = (
    "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz",
    "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz",
)
ALL_JSON_TYPES = [
    "array",
    "boolean",
    "integer",
    "null",
    "number",
    "object",
    "string",
]


def _read_json_gzip(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path.name}")
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _extract_normalized_values(value: Any, normalized_path: str) -> list[Any]:
    tokens = [token for token in normalized_path.split(".") if token]

    def visit(current: Any, index: int) -> list[Any]:
        if index == len(tokens):
            return [current]
        token = tokens[index]
        is_array = token.endswith("[]")
        key = token[:-2] if is_array else token
        if not isinstance(current, dict) or key not in current:
            return []
        child = current[key]
        if not is_array:
            return visit(child, index + 1)
        if not isinstance(child, list):
            return []
        if not child:
            return [[]] if index == len(tokens) - 1 else []
        values: list[Any] = []
        for item in child:
            values.extend(visit(item, index + 1))
        return values

    return visit(value, 0)


def _extract_normalized_occurrences(
    value: Any,
    normalized_path: str,
    *,
    path_prefix: str = "",
) -> list[tuple[str, Any]]:
    """Return every raw occurrence with an index-addressable stable path."""

    tokens = [token for token in normalized_path.split(".") if token]

    def visit(current: Any, index: int, current_path: str) -> list[tuple[str, Any]]:
        if index == len(tokens):
            return [(current_path, current)]
        token = tokens[index]
        is_array = token.endswith("[]")
        key = token[:-2] if is_array else token
        if not isinstance(current, dict) or key not in current:
            return []
        child = current[key]
        child_path = f"{current_path}.{key}" if current_path else key
        if not is_array:
            return visit(child, index + 1, child_path)
        if not isinstance(child, list):
            return []
        if not child:
            return [(f"{child_path}[]", [])] if index == len(tokens) - 1 else []
        occurrences: list[tuple[str, Any]] = []
        for item_index, item in enumerate(child):
            occurrences.extend(
                visit(item, index + 1, f"{child_path}[{item_index}]")
            )
        return occurrences

    return visit(value, 0, path_prefix)


def _entity_values(
    fixture: dict[str, Any],
    source_path: str,
) -> list[tuple[str, list[tuple[str, Any]]]]:
    target_sku = str(fixture["snapshot"]["target"]["sku_code"])
    candidate_roots = (
        ("legacy_input.candidates[]", fixture["legacy_input"]["candidates"]),
        (
            "legacy_analysis.all_candidates[]",
            fixture["legacy_analysis"]["all_candidates"],
        ),
    )
    for root, rows in candidate_roots:
        if source_path == root or source_path.startswith(root + "."):
            suffix = source_path[len(root) :].removeprefix(".")
            grouped: dict[str, list[tuple[str, Any]]] = defaultdict(list)
            root_path = root.removesuffix("[]")
            for row_index, row in enumerate(rows):
                candidate_sku = str(row["candidate"]["sku_code"])
                entity_key = (
                    target_sku
                    if suffix.startswith("target_")
                    else candidate_sku
                )
                row_path = f"{root_path}[{row_index}]"
                grouped[entity_key].extend(
                    [(row_path, row)]
                    if not suffix
                    else _extract_normalized_occurrences(
                        row,
                        suffix,
                        path_prefix=row_path,
                    )
                )
            return sorted(grouped.items())
    occurrences = _extract_normalized_occurrences(fixture, source_path)
    if not occurrences:
        return []
    entity_key = (
        target_sku
        if source_path.startswith("legacy_input.target_")
        or source_path.startswith("snapshot.target.")
        else f"profile:{target_sku}"
    )
    return [(entity_key, occurrences)]


def _typed_fact_value(value: Any, source_path: str) -> dict[str, Any]:
    if value is None:
        return {"presence": "explicit_null", "source_path": source_path}
    if isinstance(value, str) and value.strip() in {"", "-"}:
        return {
            "presence": "missing",
            "unknown_reason_code": "legacy_missing_marker",
            "source_path": source_path,
        }
    return {"presence": "known", "value": value, "source_path": source_path}


def _write_deterministic_gzip(path: Path, payload: dict[str, Any]) -> None:
    canonical = _canonical_json_bytes(payload)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as handle:
            handle.write(canonical)


def _bucket_equivalent_source(source_path: str) -> str | None:
    match = re.fullmatch(
        r"legacy_analysis\.candidate_buckets\.([^.\[]+)(?:\[\](?:\.(.*))?)?",
        source_path,
    )
    if match is None:
        return None
    suffix = match.group(2)
    if suffix is None:
        return None
    if suffix in {"brand_name", "model_name", "sku_code"}:
        suffix = f"candidate.{suffix}"
    return f"legacy_analysis.all_candidates[].{suffix}"


def _top_equivalent_source(source_path: str) -> str | None:
    prefix = "legacy_analysis.top_competitors[]"
    if not source_path.startswith(prefix):
        return None
    return "legacy_analysis.all_candidates[]" + source_path[len(prefix) :]


def _canonical_g28_source(
    source_path: str,
    alias_parent: dict[str, str],
) -> str:
    source_path = (
        _top_equivalent_source(source_path)
        or _bucket_equivalent_source(source_path)
        or source_path
    )
    visited: set[str] = set()
    while source_path in alias_parent:
        if source_path in visited:
            raise ValueError(f"legacy alias cycle at {source_path}")
        visited.add(source_path)
        source_path = alias_parent[source_path]
    return source_path


def _canonical_typed_path(g28_target: str) -> str:
    replacements = (
        ("profile_version.audit_summary", "profile_version.legacy_audit_summary"),
        (
            "pairs[].source_lineage.m12d_consumption",
            "pairs[].source_lineage.legacy_m12d_consumption",
        ),
        (
            "pairs[].dimensions.semantic_overlap",
            "pairs[].dimensions.legacy_semantic_overlap_payload",
        ),
        (
            "pairs[].dimensions.parameter_claim_overlap",
            "pairs[].dimensions.legacy_parameter_claim_overlap_payload",
        ),
        (
            "pairs[].market_validation.sales_overlap_snapshot",
            "pairs[].market_validation.legacy_summary.sales_overlap_snapshot",
        ),
        (
            "pairs[].value_anchor_analysis.matcher_result",
            "pairs[].value_anchor_analysis.legacy_matcher_payload",
        ),
        (
            "pairs[].value_anchor_analysis",
            "pairs[].value_anchor_analysis.legacy_payload",
        ),
        (
            "pairs[].replacement_pressure_analysis",
            "pairs[].replacement_pressure_analysis.legacy_payload",
        ),
        (
            "pairs[].purchase_pressure_comparison",
            "pairs[].purchase_pressure_comparison.legacy_payload",
        ),
        ("pairs[].purchase_pool", "pairs[].purchase_pool.legacy_payload"),
        (
            "pairs[].score_breakdown.weighted_overlap",
            "pairs[].score_breakdown.legacy_payload.weighted_overlap",
        ),
        (
            "pairs[].score_breakdown.ranking_trace",
            "pairs[].score_breakdown.legacy_payload.ranking_trace",
        ),
        (
            "pairs[].dimension_conclusions",
            "pairs[].legacy_dimension_conclusions",
        ),
        (
            "pairs[].business_questions",
            "pairs[].legacy_review_payload.business_questions",
        ),
        (
            "pairs[].review_items_and_limitations",
            "pairs[].legacy_review_payload.review_items_and_limitations",
        ),
        ("pairs[].primary_role", "pairs[].legacy_primary_role"),
    )
    for source_prefix, target_prefix in replacements:
        if g28_target == source_prefix or g28_target.startswith(source_prefix + "."):
            return target_prefix + g28_target[len(source_prefix) :]

    snapshot_match = re.match(
        r"(sku_snapshots\[(?:target|candidate)\]\.(identity_market|fact_sections|"
        r"claim_value_snapshot|claim_contribution_snapshot|purchase_reason_snapshot))"
        r"(?:\.(.*))?$",
        g28_target,
    )
    if snapshot_match is not None:
        root, _, suffix = snapshot_match.groups()
        return f"{root}.legacy_payload" + (f".{suffix}" if suffix else "")
    return g28_target


def _binding_for_path(typed_path: str) -> tuple[str, str]:
    def first_field(value: str) -> str:
        return value.split(".", 1)[0].removesuffix("[]")

    root_bindings = {
        "generation_receipt": schemas.ProfileGenerationReceipt,
        "profile_version": schemas.ProfileVersionAnalysisContext,
        "sku_summary": schemas.SkuCompetitionAnalysisSummary,
    }
    for root, model in root_bindings.items():
        if typed_path.startswith(root + "."):
            field = first_field(typed_path[len(root) + 1 :])
            return model.__name__, field

    snapshot_match = re.match(
        r"sku_snapshots\[(?:target|candidate)\]\.(identity_market|fact_sections|"
        r"claim_value_snapshot|claim_contribution_snapshot|purchase_reason_snapshot)"
        r"\.(legacy_payload)",
        typed_path,
    )
    if snapshot_match is not None:
        model_by_field = {
            "identity_market": schemas.IdentityMarketSnapshot,
            "fact_sections": schemas.FactSectionsSnapshot,
            "claim_value_snapshot": schemas.ClaimValueSnapshot,
            "claim_contribution_snapshot": schemas.ClaimContributionSnapshot,
            "purchase_reason_snapshot": schemas.PurchaseReasonSnapshot,
        }
        model = model_by_field[snapshot_match.group(1)]
        return model.__name__, snapshot_match.group(2)

    pair_nested_bindings = (
        ("pairs[].source_lineage.", schemas.PairAnalysisSourceLineage),
        ("pairs[].dimensions.", schemas.PairDimensionSet),
        ("pairs[].market_validation.", schemas.MarketValidationAnalysisResult),
        ("pairs[].value_anchor_analysis.", schemas.ValueAnchorAnalysisResult),
        (
            "pairs[].replacement_pressure_analysis.",
            schemas.ReplacementPressureAnalysisResult,
        ),
        (
            "pairs[].purchase_pressure_comparison.",
            schemas.PurchasePressureComparisonResult,
        ),
        ("pairs[].purchase_pool.", schemas.PurchasePoolAnalysis),
        ("pairs[].score_breakdown.", schemas.PairScoreBreakdown),
        ("pairs[].audit_summary.", schemas.PairAuditSummary),
    )
    for prefix, model in pair_nested_bindings:
        if typed_path.startswith(prefix):
            return model.__name__, first_field(typed_path[len(prefix) :])
    if typed_path.startswith("pairs[]."):
        return (
            schemas.PairAnalysisSnapshot.__name__,
            first_field(typed_path[len("pairs[].") :]),
        )
    raise ValueError(f"no typed schema binding for {typed_path}")


def _field_exists(model_name: str, field_name: str) -> bool:
    model = getattr(schemas, model_name)
    return field_name in model.model_fields


def _direct_target_types(typed_path: str) -> list[str]:
    exact = {
        "pairs[].recall_rank": ["integer"],
        "pairs[].audit_summary.role_cn": ["null", "string"],
        "profile_version.analysis_population": ALL_JSON_TYPES,
        "profile_version.category_code": ["string"],
        "profile_version.market_window": ALL_JSON_TYPES,
        "profile_version.product_category": ["string"],
        "profile_version.project_id": ["string"],
        "generation_receipt.source_status": ["string"],
    }
    if typed_path in exact:
        return exact[typed_path]
    suffix_types = {
        "generation_receipt.source_atoms[].ability_code": ["string"],
        "generation_receipt.source_atoms[].status": ["string"],
        "generation_receipt.calculation_steps[].run_count": ["integer"],
        "generation_receipt.calculation_steps[].status": ["string"],
        "generation_receipt.calculation_steps[].step_code": ["string"],
    }
    if typed_path in suffix_types:
        return suffix_types[typed_path]
    raise ValueError(f"direct typed leaf lacks an explicit target-type contract: {typed_path}")


def _normalized_binding(
    *,
    g28_target_path: str,
    typed_path: str,
    assignment_mode: str,
) -> tuple[str, str, str]:
    if assignment_mode == "direct":
        model_name, field_name = _binding_for_path(typed_path)
        return typed_path, model_name, field_name
    if assignment_mode == "scalar_to_singleton_list":
        return (
            "profile_version.source_batch_ids",
            schemas.ProfileVersionAnalysisContext.__name__,
            "source_batch_ids",
        )
    if assignment_mode == "bucket_rows_to_sku_refs":
        return (
            g28_target_path,
            schemas.SkuCompetitionAnalysisSummary.__name__,
            "role_buckets",
        )
    owner_bindings = (
        ("profile_version.", schemas.ProfileVersionAnalysisContext),
        ("generation_receipt.", schemas.ProfileGenerationReceipt),
        ("sku_snapshots[", schemas.VersionSkuAnalysisSnapshot),
        ("pairs[].", schemas.PairAnalysisSnapshot),
        ("sku_summary.", schemas.SkuCompetitionAnalysisSummary),
        ("selections[].", schemas.PriorityCompetitorSelection),
    )
    for prefix, model in owner_bindings:
        if g28_target_path.startswith(prefix):
            return g28_target_path, model.__name__, "source_facts"
    raise ValueError(f"no normalized source-fact owner for {g28_target_path}")


def _validate_fixture_duplicate_views(fixtures: list[dict[str, Any]]) -> None:
    for fixture in fixtures:
        analysis = fixture["legacy_analysis"]
        pairs = {
            row["candidate"]["sku_code"]: row for row in analysis["all_candidates"]
        }
        for selected in analysis["top_competitors"]:
            sku_code = selected["candidate"]["sku_code"]
            if selected != pairs[sku_code]:
                raise ValueError(f"top competitor payload diverges for {sku_code}")
        for rows in analysis["candidate_buckets"].values():
            for bucket_row in rows:
                sku_code = bucket_row["sku_code"]
                pair = pairs[sku_code]
                expected = {
                    "sku_code": pair["candidate"]["sku_code"],
                    "brand_name": pair["candidate"]["brand_name"],
                    "model_name": pair["candidate"]["model_name"],
                    "business_score": pair["business_score"],
                    "purchase_pool": pair["purchase_pool"],
                    "replacement_pressure": pair["replacement_pressure"],
                    "role_cn": pair["role_cn"],
                }
                if bucket_row != expected:
                    raise ValueError(f"candidate bucket payload diverges for {sku_code}")


def build_fixture_normalization_projection(
    fixture: dict[str, Any],
) -> dict[str, Any]:
    """Project the three non-direct legacy shapes into their typed references.

    This is a local compatibility proof for G29, not the V1.1 materializer.  It
    demonstrates that the scalar batch ID, duplicated Top list, and duplicated
    role buckets have deterministic typed destinations without storing a second
    complete pair payload.
    """

    _validate_fixture_duplicate_views([fixture])
    analysis = fixture["legacy_analysis"]
    canonical_pairs = {
        row["candidate"]["sku_code"]: row for row in analysis["all_candidates"]
    }
    priority_pair_refs = [
        {
            "candidate_sku_code": row["candidate"]["sku_code"],
            "selection_rank": rank,
            "pair_ref": f"pair:{row['candidate']['sku_code']}",
        }
        for rank, row in enumerate(analysis["top_competitors"], start=1)
    ]
    role_buckets = {
        role: sorted({row["sku_code"] for row in rows})
        for role, rows in sorted(analysis["candidate_buckets"].items())
    }
    return {
        "source_batch_ids": [fixture["snapshot"]["batch_id"]],
        "canonical_pair_payloads": canonical_pairs,
        "priority_pair_refs": priority_pair_refs,
        "role_buckets": role_buckets,
    }


def _pick(payload: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: payload[field] for field in fields if field in payload}


def _normalize_claim_contribution(
    payload: dict[str, Any],
) -> schemas.ClaimContributionRecord:
    fields = (
        "claim_code",
        "claim_name",
        "sku_code",
        "brand_name",
        "model_name",
        "claim_value_role",
        "claim_value_score",
        "business_claim_type",
        "business_claim_type_cn",
        "business_claim_type_definition_cn",
        "business_value_label",
        "business_value_meaning_cn",
        "attribution_confidence",
        "contribution_share_in_sku",
        "estimated_price_premium_abs",
        "estimated_weekly_sales_lift_abs",
        "estimated_weekly_sales_amount_lift_abs",
        "pool_claim_price_delta_abs",
        "pool_claim_weekly_sales_delta_abs",
        "pool_claim_weekly_sales_amount_delta_abs",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
        "reason_cn",
        "scorecard",
    )
    return schemas.ClaimContributionRecord.model_validate(
        {**_pick(payload, fields), "raw_details": payload}
    )


def _normalize_claim_attribution(
    payload: dict[str, Any],
) -> schemas.ClaimAttributionRecord:
    fields = (
        "sku_code",
        "brand_name",
        "model_name",
        "price_band_group",
        "size_tier",
        "context_code",
        "context_name",
        "context_type",
        "confidence",
        "baseline",
        "sku_observed",
        "sku_gap_vs_baseline",
        "attribution_summary_cn",
    )
    return schemas.ClaimAttributionRecord.model_validate(
        {
            **_pick(payload, fields),
            "positive_claims": [
                _normalize_claim_contribution(row).model_dump(mode="json")
                for row in payload.get("positive_claims", [])
            ],
            "drag_claims": [
                _normalize_claim_contribution(row).model_dump(mode="json")
                for row in payload.get("drag_claims", [])
            ],
            "opportunity_claims": [
                _normalize_claim_contribution(row).model_dump(mode="json")
                for row in payload.get("opportunity_claims", [])
            ],
            "raw_details": payload,
        }
    )


def normalize_claim_value_snapshot(payload: dict[str, Any]) -> schemas.ClaimValueSnapshot:
    claim_value_fields = (
        "claim_code",
        "claim_name",
        "sku_code",
        "brand_name",
        "model_name",
        "claim_dimension",
        "claim_source_type",
        "claim_source_type_cn",
        "claim_value_role",
        "claim_value_score",
        "business_claim_type",
        "business_claim_type_cn",
        "business_claim_type_definition_cn",
        "business_value_label",
        "business_value_meaning_cn",
        "context_code",
        "context_name",
        "context_type",
        "target_has_claim",
        "attribution_confidence",
        "evidence_id_count",
        "evidence_strength",
        "supporting_dimensions",
        "estimated_contribution",
        "pool_effect",
        "parameter_competitiveness",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
        "price_band_group",
        "size_tier",
        "scorecard",
        "quality_flags",
        "reason_cn",
    )
    sku_level_fields = (
        "claim_code",
        "claim_name",
        "claim_value_score",
        "claim_source_type",
        "claim_source_type_cn",
        "business_claim_type",
        "business_claim_type_cn",
        "business_claim_type_definition_cn",
        "business_value_label",
        "business_value_meaning_cn",
        "target_has_claim",
        "main_contexts",
        "context_values",
        "parameter_competitiveness",
        "sku_level_user_payment_value_abs",
        "sku_level_weekly_sales_lift_abs",
        "sku_level_weekly_sales_amount_lift_abs",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
        "evidence_summary_cn",
    )
    return schemas.ClaimValueSnapshot.model_validate(
        {
            **_pick(
                payload,
                (
                    "sku_code",
                    "analysis_population",
                    "market_window",
                    "filters",
                    "role_counts",
                    "method_note_cn",
                ),
            ),
            "attributions": [
                _normalize_claim_attribution(row).model_dump(mode="json")
                for row in payload["attributions"]
            ],
            "claim_values": [
                {
                    **_pick(row, claim_value_fields),
                    "raw_details": row,
                }
                for row in payload["claim_values"]
            ],
            "sku_level_claim_values": [
                {
                    **_pick(row, sku_level_fields),
                    "raw_details": row,
                }
                for row in payload["sku_level_claim_values"]
            ],
            "legacy_payload": payload,
        }
    )


def normalize_claim_contribution_snapshot(
    payload: dict[str, Any],
) -> schemas.ClaimContributionSnapshot:
    return schemas.ClaimContributionSnapshot.model_validate(
        {
            **_pick(
                payload,
                (
                    "sku_code",
                    "analysis_population",
                    "market_window",
                    "attribution_count",
                    "filters",
                    "method_note_cn",
                ),
            ),
            "attributions": [
                _normalize_claim_attribution(row).model_dump(mode="json")
                for row in payload["attributions"]
            ],
            "legacy_payload": payload,
        }
    )


def normalize_purchase_reason_snapshot(
    payload: dict[str, Any],
) -> schemas.PurchaseReasonSnapshot:
    anchor_fields = (
        "anchor_cn",
        "role",
        "core_eligible",
        "establishment_score",
        "establishment_status",
        "evidence_domains",
        "evidence_strength",
        "user_validation_status",
        "support_summary_cn",
        "weakness_summary_cn",
        "pressure_level",
        "pressure_summary_cn",
    )
    pressure_fields = (
        "anchor_cn",
        "pressure_level",
        "pressure_summary_cn",
    )
    return schemas.PurchaseReasonSnapshot.model_validate(
        {
            **_pick(
                payload,
                (
                    "found",
                    "comparison_mode",
                    "consumption_state",
                    "profile_confidence",
                    "core_reasons_cn",
                    "established_reasons_cn",
                    "proposition_reasons_cn",
                    "supporting_reasons_cn",
                    "weak_expression_reasons_cn",
                    "risk_drag_reasons_cn",
                ),
            ),
            "anchors": [
                {**_pick(row, anchor_fields), "raw_details": row}
                for row in payload["anchors"]
            ],
            "purchase_pressure_reasons": [
                {**_pick(row, pressure_fields), "raw_details": row}
                for row in payload["purchase_pressure_reasons"]
            ],
            "legacy_payload": payload,
        }
    )


def build_contract() -> schemas.LegacyTypedMappingContract:
    inventory = _read_json_gzip(INVENTORY_PATH)
    rows = inventory["observed_paths"]
    row_by_source = {row["source_path"]: row for row in rows}
    alias_parent = {
        alias: group["canonical_source_path"]
        for group in inventory["target_alias_groups"]
        for alias in group["alias_source_paths"]
    }
    fixtures = [_read_json_gzip(ARTIFACT_DIR / name) for name in REAL_FIXTURE_NAMES]
    _validate_fixture_duplicate_views(fixtures)

    field_contracts: list[dict[str, Any]] = []
    canonical_source_by_source: dict[str, str] = {}
    for row in rows:
        source_path = row["source_path"]
        canonical_source = _canonical_g28_source(source_path, alias_parent)
        canonical_source_by_source[source_path] = canonical_source
        canonical_row = row_by_source.get(canonical_source)
        if canonical_row is None:
            raise ValueError(f"canonical source is absent from G28 inventory: {source_path}")
        typed_path = _canonical_typed_path(canonical_row["target_leaf_path"])
        model_name, field_name = _binding_for_path(typed_path)
        if not _field_exists(model_name, field_name):
            raise ValueError(f"unknown typed target {model_name}.{field_name}")
        is_duplicate_view = canonical_source != source_path
        is_legacy_subtree = ".legacy" in typed_path
        is_batch_id = source_path == "snapshot.batch_id"
        is_role_bucket = source_path.startswith(
            "legacy_analysis.candidate_buckets."
        ) and "[]" not in source_path
        if is_duplicate_view:
            preservation_policy = "canonical_pair_reference_no_duplicate"
            assignment_mode = "canonical_reference"
        elif is_legacy_subtree:
            preservation_policy = "typed_legacy_subtree"
            assignment_mode = "normalize_legacy_subtree"
        elif is_batch_id:
            preservation_policy = "typed_normalization"
            assignment_mode = "scalar_to_singleton_list"
        elif is_role_bucket:
            preservation_policy = "typed_normalization"
            assignment_mode = "bucket_rows_to_sku_refs"
        else:
            preservation_policy = "typed_field"
            assignment_mode = "direct"
        (
            normalized_target_path,
            normalized_target_model,
            normalized_target_field,
        ) = _normalized_binding(
            g28_target_path=canonical_row["target_leaf_path"],
            typed_path=typed_path,
            assignment_mode=assignment_mode,
        )
        transform_code = {
            "direct": "direct_assignment",
            "normalize_legacy_subtree": "observed_leaf_to_typed_source_fact",
            "scalar_to_singleton_list": "scalar_to_singleton_list",
            "bucket_rows_to_sku_refs": "bucket_rows_to_sku_refs",
            "canonical_reference": "canonical_reference",
        }[assignment_mode]
        if assignment_mode == "direct":
            accepted_target_types = _direct_target_types(typed_path)
        elif assignment_mode in {
            "scalar_to_singleton_list",
            "bucket_rows_to_sku_refs",
        }:
            accepted_target_types = ["array"]
        else:
            accepted_target_types = ALL_JSON_TYPES
        field_contracts.append(
            {
                "source_path": source_path,
                "source_atom": row["source_atom"],
                "g28_target_leaf_path": row["target_leaf_path"],
                "canonical_typed_path": typed_path,
                "target_model": model_name,
                "target_field": field_name,
                "normalized_target_path": normalized_target_path,
                "normalized_target_model": normalized_target_model,
                "normalized_target_field": normalized_target_field,
                "transform_code": transform_code,
                "observed_source_types": sorted(row["observed_source_types"]),
                "accepted_target_types": accepted_target_types,
                "occurrence_count": row["occurrence_count"],
                "empty_container_observed": row["empty_container_observed"],
                "nullable_observed": row["nullable_observed"],
                "preservation_policy": preservation_policy,
                "assignment_mode": assignment_mode,
                "authoritative_for_v11_analysis": (
                    assignment_mode == "direct"
                ),
                "normalized_authoritative_for_v11_analysis": (
                    assignment_mode != "canonical_reference"
                ),
                "normalization_required": (
                    assignment_mode
                    in {
                        "normalize_legacy_subtree",
                        "scalar_to_singleton_list",
                        "bucket_rows_to_sku_refs",
                    }
                ),
                "missing_policy": "explicit_unknown_never_zero_false_or_empty",
                "roundtrip_required": True,
            }
        )

    alias_members: dict[str, set[str]] = defaultdict(set)
    for source_path, canonical_source in canonical_source_by_source.items():
        if source_path != canonical_source:
            alias_members[canonical_source].add(source_path)
    field_by_source = {row["source_path"]: row for row in field_contracts}
    alias_contracts = [
        {
            "canonical_source_path": canonical_source,
            "alias_source_paths": sorted(alias_sources),
            "canonical_typed_path": field_by_source[canonical_source][
                "canonical_typed_path"
            ],
            "conflict_policy": "fail_roundtrip",
            "duplicate_storage_allowed": False,
        }
        for canonical_source, alias_sources in sorted(alias_members.items())
    ]
    payload = {
        "contract_version": "competitor_profile_v1_1_g29_typed_mapping_v1",
        "source_inventory_hash": inventory["inventory_hash"],
        "source_fixture_count": inventory["source_fixture_count"],
        "observed_path_count": inventory["source_observed_path_count"],
        "value_leaf_path_count": inventory["source_value_leaf_path_count"],
        "empty_container_path_count": inventory["source_empty_container_path_count"],
        "field_contracts": field_contracts,
        "alias_contracts": alias_contracts,
        "unmapped_path_count": 0,
        "typed_schema_complete": True,
        "known_to_unknown_allowed": False,
        "selection_membership_policy": (
            "top_list_index_to_rank_and_candidate_to_pair_ref"
        ),
    }
    payload["contract_hash"] = hashlib.sha256(
        _canonical_json_bytes(payload)
    ).hexdigest()
    return schemas.LegacyTypedMappingContract.model_validate(payload)


def iter_normalized_source_facts(
    fixture: dict[str, Any],
    contract: schemas.LegacyTypedMappingContract | None = None,
) -> Iterator[schemas.NormalizedSourceFact]:
    """Execute every canonical legacy-leaf normalization without materializing a DB row."""

    active_contract = contract or build_contract()
    for field_contract in active_contract.field_contracts:
        if field_contract.transform_code != "observed_leaf_to_typed_source_fact":
            continue
        for entity_key, occurrences in _entity_values(
            fixture,
            field_contract.source_path,
        ):
            if not occurrences:
                continue
            occurrence_payload = [
                {
                    "occurrence_key": occurrence_key,
                    "raw_value": raw_value,
                }
                for occurrence_key, raw_value in occurrences
            ]
            value_hash = hashlib.sha256(
                _canonical_json_bytes(occurrence_payload)
            ).hexdigest()
            fact_id = "source-fact:" + hashlib.sha256(
                _canonical_json_bytes(
                    {
                        "entity_key": entity_key,
                        "source_path": field_contract.source_path,
                        "value_hash": value_hash,
                    }
                )
            ).hexdigest()
            yield schemas.NormalizedSourceFact.model_validate(
                {
                    "fact_id": fact_id,
                    "code": field_contract.source_path,
                    "roles": ["normalized_legacy_source"],
                    "values": [
                        _typed_fact_value(raw_value, field_contract.source_path)
                        for _, raw_value in occurrences
                    ],
                    "entity_key": entity_key,
                    "source_atom": field_contract.source_atom,
                    "source_path": field_contract.source_path,
                    "normalized_target_path": (
                        field_contract.normalized_target_path
                    ),
                    "source_occurrences": [
                        {
                            "occurrence_key": occurrence_key,
                            "ordinal": ordinal,
                            "raw_value": raw_value,
                            "typed_value": _typed_fact_value(
                                raw_value,
                                field_contract.source_path,
                            ),
                        }
                        for ordinal, (occurrence_key, raw_value) in enumerate(
                            occurrences
                        )
                    ],
                    "occurrence_count": len(occurrences),
                    "source_value_hash": value_hash,
                }
            )


def main() -> int:
    contract = build_contract()
    payload = contract.model_dump(mode="json")
    _write_deterministic_gzip(OUTPUT_PATH, payload)
    print(
        json.dumps(
            {
                "artifact": OUTPUT_PATH.name,
                "observed_path_count": contract.observed_path_count,
                "alias_contract_count": len(contract.alias_contracts),
                "contract_hash": contract.contract_hash,
                "database_write": False,
                "external_publish": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
