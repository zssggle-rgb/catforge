#!/usr/bin/env python3
"""Export the 65E7Q V1 universe from a transaction forced to READ ONLY.

This script is sent to the existing 205 API container over stdin.  It prints a
single canonical JSON object and never creates, updates, or publishes data.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities


VERSION_ID = "c45c0002-9b8a-4b0d-8b12-344dee020e15"
TARGET_SKU_CODE = "TV00029112"
LEGACY_TOP3 = ("TV00027801", "TV00028909", "TV00029936")

PAIR_SUMMARY_FIELDS = (
    "candidate_sku_code",
    "candidate_identity_json",
    "recall_sources_json",
    "recall_facts_json",
    "competitor_member",
    "reference_member",
    "candidate_status",
    "purchase_pool_level",
    "question_eligibility_json",
    "reference_purposes_json",
    "primary_relation_code",
    "relation_codes_json",
    "selected",
    "non_selection_reason_code",
    "confidence_level",
    "confidence",
    "release_status",
    "is_current",
    "input_fingerprint",
    "result_hash",
    "processing_status",
    "review_required",
    "review_status",
)

RELATION_INDEX_FIELDS = (
    "candidate_sku_code",
    "relation_code",
    "relation_status",
    "is_primary",
    "confidence_level",
    "eligible_question_codes_json",
    "result_hash",
    "input_fingerprint",
    "processing_status",
    "release_status",
    "is_current",
    "review_required",
    "review_status",
)

PROFILE_FIELDS = (
    "sku_competitor_profile_id",
    "competitor_profile_version_id",
    "target_sku_code",
    "display_name_cn",
    "analysis_state",
    "conclusion_state",
    "freshness_status",
    "profile_confidence",
    "candidate_status_counts_json",
    "relation_status_counts_json",
    "release_status",
    "is_current",
    "input_fingerprint",
    "result_hash",
    "processing_status",
    "review_required",
    "review_status",
)

VERSION_FIELDS = (
    "competitor_profile_version_id",
    "project_id",
    "category_code",
    "product_category",
    "storage_batch_id",
    "release_scope_key",
    "profile_version",
    "schema_version",
    "rule_version",
    "method_version",
    "method_versions_json",
    "serving_scope_json",
    "source_authorities_json",
    "source_batch_ids_json",
    "authoritative_sku_manifest_hash",
    "release_status",
    "release_quality_status",
    "is_current",
    "freshness_status",
    "generated_at",
    "sku_count",
    "ready_count",
    "partial_count",
    "blocked_count",
    "failed_count",
    "pair_count",
    "relation_count",
    "selection_count",
    "input_fingerprint",
    "candidate_universe_fingerprint",
    "result_hash",
    "processing_status",
    "review_required",
    "review_status",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _select_fields(row: Any, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _json_value(getattr(row, field)) for field in fields}


def _full_record(row: Any) -> dict[str, Any]:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def main() -> int:
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        version = db.get(entities.Core3CompetitorProfileVersion, VERSION_ID)
        if version is None:
            raise RuntimeError(f"missing competitor profile version {VERSION_ID}")
        profile = db.scalar(
            select(entities.Core3SkuCompetitorProfile).where(
                entities.Core3SkuCompetitorProfile.competitor_profile_version_id
                == VERSION_ID,
                entities.Core3SkuCompetitorProfile.target_sku_code
                == TARGET_SKU_CODE,
            )
        )
        if profile is None:
            raise RuntimeError(f"missing profile for {TARGET_SKU_CODE}")

        pairs = list(
            db.scalars(
                select(entities.Core3SkuCompetitorProfilePair)
                .where(
                    entities.Core3SkuCompetitorProfilePair.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .order_by(
                    entities.Core3SkuCompetitorProfilePair.candidate_sku_code
                )
            )
        )
        relations = list(
            db.scalars(
                select(entities.Core3SkuCompetitorProfileRelation)
                .where(
                    entities.Core3SkuCompetitorProfileRelation.competitor_profile_version_id
                    == VERSION_ID,
                    entities.Core3SkuCompetitorProfileRelation.target_sku_code
                    == TARGET_SKU_CODE,
                )
                .order_by(
                    entities.Core3SkuCompetitorProfileRelation.candidate_sku_code,
                    entities.Core3SkuCompetitorProfileRelation.relation_code,
                )
            )
        )
        selections = list(
            db.scalars(
                select(entities.Core3SkuCompetitorProfileSelection)
                .where(
                    entities.Core3SkuCompetitorProfileSelection.sku_competitor_profile_id
                    == profile.sku_competitor_profile_id
                )
                .order_by(
                    entities.Core3SkuCompetitorProfileSelection.selection_rank
                )
            )
        )

        pair_by_code = {row.candidate_sku_code: row for row in pairs}
        relations_by_code: dict[str, list[Any]] = {}
        for relation in relations:
            relations_by_code.setdefault(relation.candidate_sku_code, []).append(
                relation
            )

        candidate_summaries = [
            {
                "candidate_order": index,
                **_select_fields(pair, PAIR_SUMMARY_FIELDS),
            }
            for index, pair in enumerate(pairs, start=1)
        ]
        relation_index = [
            _select_fields(relation, RELATION_INDEX_FIELDS)
            for relation in relations
        ]
        top3_full = []
        for rank, sku_code in enumerate(LEGACY_TOP3, start=1):
            pair = pair_by_code.get(sku_code)
            if pair is None:
                raise RuntimeError(f"legacy Top3 missing from V1 universe: {sku_code}")
            pair_relations = relations_by_code.get(sku_code, [])
            if len(pair_relations) != 7:
                raise RuntimeError(
                    f"legacy Top3 relation count is not seven: {sku_code}="
                    f"{len(pair_relations)}"
                )
            top3_full.append(
                {
                    "legacy_rank": rank,
                    "candidate_sku_code": sku_code,
                    "pair": _full_record(pair),
                    "relations": [_full_record(row) for row in pair_relations],
                }
            )

        pair_status_counts = dict(sorted(Counter(
            row.candidate_status for row in pairs
        ).items()))
        relation_status_counts = dict(sorted(Counter(
            row.relation_status for row in relations
        ).items()))
        payload = {
            "fixture_version": "competitor_profile_v1_1_g28_full_universe_v2",
            "source_environment": "205-read-only",
            "transaction_mode": "READ ONLY",
            "canonical_order": (
                "candidate_sku_code_ascending;relation_candidate_and_code_ascending"
            ),
            "version": _select_fields(version, VERSION_FIELDS),
            "profile": _select_fields(profile, PROFILE_FIELDS),
            "candidate_count": len(candidate_summaries),
            "candidates": candidate_summaries,
            "pair_status_counts": pair_status_counts,
            "target_relation_count": len(relation_index),
            "relations": relation_index,
            "relation_status_counts": relation_status_counts,
            "relation_index_hash": _sha256(relation_index),
            "legacy_top3_full": top3_full,
            "selections": [_full_record(row) for row in selections],
        }
        payload["fixture_hash"] = _sha256(payload)
        print(_canonical_bytes(payload).decode("utf-8"))
        return 0
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
