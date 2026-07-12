#!/usr/bin/env python3
"""Shadow, write, and compare TV/AC M07 v2 drafts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M07_AC_POOL_RULE_VERSION,
    CORE3_M07_AC_PRICE_BAND_RULE_VERSION,
    M07_ANALYSIS_WINDOWS,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
)
from app.services.core3_real_data.market_profile_repositories import (
    M07MarketRepository,
    MarketRepositoryWriteResult,
    _jsonable_payload,
)
from app.services.core3_real_data.market_profile_service import MarketProfileService
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "product_category": "TV",
        "batches": (
            "m00_20260613004311_d548f6dc",
            "m00_20260619084551_857df63b",
        ),
        "old_rule_version": "m07_market_profile_v1",
        "rule_version": CORE3_M07_RULE_VERSION,
        "price_band_rule_version": CORE3_M07_PRICE_BAND_RULE_VERSION,
        "pool_rule_version": CORE3_M07_POOL_RULE_VERSION,
        "expected_full_sample_status": {"sufficient": 377},
        "expected_full_confidence_migrations": 13,
    },
    "AC": {
        "product_category": "AC",
        "batches": ("m00_20260624000202_1150a669",),
        "old_rule_version": "m07_market_profile_v1",
        "rule_version": CORE3_M07_RULE_VERSION,
        "price_band_rule_version": CORE3_M07_AC_PRICE_BAND_RULE_VERSION,
        "pool_rule_version": CORE3_M07_AC_POOL_RULE_VERSION,
        "expected_full_sample_status": {"sufficient": 155},
        "expected_full_confidence_migrations": 0,
    },
}

DOWNSTREAM_TABLES = (
    "core3_m09c_sku_user_task_profile",
    "core3_m10c_sku_target_group_profile",
    "core3_sku_value_battlefield_profile",
    "core3_sku_claim_value_quantification",
    "core3_sku_purchase_reason_profile",
)
TARGET_CHUNK_SIZE = 75

SELF_RAW_PROFILE_FIELDS = (
    "sales_volume_total",
    "sales_amount_total",
    "price_wavg",
    "price_median",
    "price_min",
    "price_max",
    "screen_size_inch",
    "size_segment",
    "screen_size_class",
    "market_pool_key",
)

COMPARISON_PROFILE_FIELDS = (
    "price_latest",
    "price_band_category",
    "price_band_size",
    "price_percentile_in_category",
    "volume_percentile_in_category",
    "amount_percentile_in_category",
    "price_percentile_in_size",
    "volume_percentile_in_size",
    "amount_percentile_in_size",
    "same_pool_price_percentile",
    "same_pool_volume_percentile",
    "same_pool_amount_percentile",
    "same_pool_sku_count",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        downstream_before = capture_downstream_guard(db)
        validated_shadow = load_validated_shadow(args.validated_shadow_json)
        persisted_before = (
            validated_shadow["persisted_before"]
            if validated_shadow is not None
            else {
                category: capture_db_category(db, category, use_new=False)
                for category in CATEGORY_CONFIG
            }
        )
        if validated_shadow is None:
            legacy_service = load_legacy_market_profile_service()
            before, legacy_runs = build_shadow(db, service_class=legacy_service, legacy=True)
            shadow, shadow_runs = build_shadow(db)
            db.rollback()
            shadow_comparisons = {
                category: compare_category(before[category], shadow[category])
                for category in CATEGORY_CONFIG
            }
            print(json.dumps({"shadow_comparisons": shadow_comparisons}, default=str), flush=True)
            assert_acceptance(shadow_comparisons, shadow)
        else:
            before = validated_shadow["before"]
            shadow = validated_shadow["after"]
            shadow_comparisons = validated_shadow["comparisons"]
            legacy_runs = validated_shadow.get("legacy_runs", {})
            shadow_runs = validated_shadow.get("shadow_runs", {})

        write_runs: dict[str, Any] = {}
        if args.write_draft:
            for category, config in CATEGORY_CONFIG.items():
                write_runs[category] = []
                for batch_id in config["batches"]:
                    target_chunks = batch_target_chunks(db, category, batch_id)
                    for window in M07_ANALYSIS_WINDOWS:
                        for sku_scope in target_chunks:
                            result = run_batch(
                                db,
                                category,
                                batch_id,
                                window=window.value,
                                sku_scope=sku_scope,
                                write=True,
                            )
                            write_runs[category].append(compact_run(result))
                            db.commit()
                            print(
                                json.dumps(
                                    {
                                        "phase": "write",
                                        "category": category,
                                        "batch_id": batch_id,
                                        "window": window.value,
                                        "processed_sku_count": len(sku_scope),
                                    }
                                ),
                                flush=True,
                            )

        read_persisted_draft = args.write_draft or args.validate_persisted_only
        after = {
            category: (
                capture_db_category_compact(db, category, use_new=True)
                if args.validate_persisted_only
                else capture_db_category(db, category, use_new=True)
            )
            if read_persisted_draft
            else shadow[category]
            for category in CATEGORY_CONFIG
        }
        downstream_after = capture_downstream_guard(db)

    if validated_shadow is None:
        comparisons = {
            category: compare_category(before[category], after[category])
            for category in CATEGORY_CONFIG
        }
        assert_acceptance(comparisons, after)
        before_payload = {category: compact_capture(value) for category, value in before.items()}
    else:
        comparisons = shadow_comparisons
        assert_persisted_matches_validated_shadow(after, validated_shadow["after"])
        before_payload = validated_shadow["before"]
    if downstream_before != downstream_after:
        raise RuntimeError("M09C and later tables changed during M07 draft rebuild")

    payload = {
        "task_id": "M12D-QF-05",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": "M07 only",
        "write_draft": read_persisted_draft,
        "allowed_migrations": {
            "TV": [
                "observed_window_less_than_52w and online_only_channel move from profile flags to range info",
                "weeks without rows are zero-sales market facts, so latest-week gap and per-SKU trend coverage are not quality issues",
                "two new-launch SKUs move from limited to sufficient because short observed history is lifecycle fact, not missing data",
            ],
            "AC": [
                "observed_window_less_than_52w and online_only_channel move from profile flags to range info",
                "weeks without rows are zero-sales market facts while AC price/pool v2 stays unchanged",
            ],
        },
        "persisted_before": {
            category: compact_capture(value)
            for category, value in persisted_before.items()
        },
        "before": before_payload,
        "after": {category: compact_capture(value) for category, value in after.items()},
        "comparisons": comparisons,
        "persisted_migrations": (
            validated_shadow.get("persisted_migrations", {})
            if args.validate_persisted_only and validated_shadow is not None
            else {
                category: compare_category(persisted_before[category], after[category])
                for category in CATEGORY_CONFIG
            }
        ),
        "legacy_runs": legacy_runs,
        "shadow_runs": shadow_runs,
        "write_runs": write_runs,
        "downstream_guard": {
            "before": downstream_before,
            "after": downstream_after,
            "unchanged": downstream_before == downstream_after,
        },
    }
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    output_markdown.write_text(render_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "comparisons": comparisons,
                "downstream_unchanged": downstream_before == downstream_after,
                "output_json": str(output_json),
                "output_markdown": str(output_markdown),
            },
            ensure_ascii=False,
        )
    )
    return 0


def load_legacy_market_profile_service():
    path = Path(
        "/usr/local/lib/python3.11/site-packages/app/services/core3_real_data/market_profile_service.py"
    )
    if not path.exists():
        raise RuntimeError(f"legacy M07 implementation not found: {path}")
    spec = importlib.util.spec_from_file_location(
        "app.services.core3_real_data._qf05_legacy_market_profile_service",
        path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load legacy M07 implementation: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.MarketProfileService


def load_validated_shadow(path_value: str | None) -> dict[str, Any] | None:
    if not path_value:
        return None
    payload = json.loads(Path(path_value).read_text(encoding="utf-8"))
    if payload.get("task_id") != "M12D-QF-05":
        raise RuntimeError("validated shadow belongs to a different task")
    if payload.get("write_draft"):
        raise RuntimeError("validated shadow must be a read-only run")
    if not (payload.get("downstream_guard") or {}).get("unchanged"):
        raise RuntimeError("validated shadow did not preserve downstream tables")
    return payload


def assert_persisted_matches_validated_shadow(
    actual: Mapping[str, Mapping[str, Any]],
    expected: Mapping[str, Mapping[str, Any]],
) -> None:
    fields = (
        "profile_count",
        "signal_count",
        "pool_count",
        "member_count",
        "sku_count",
        "window_counts",
        "sample_status_counts",
        "full_sample_status_counts",
        "full_flag_counts",
        "quality_issue_counts",
        "quality_severity_counts",
        "full_review_required_count",
        "price_band_rule_versions",
        "pool_rule_versions",
        "cross_category_pool_candidate_count",
    )
    for category in CATEGORY_CONFIG:
        for field in fields:
            if actual[category].get(field) != expected[category].get(field):
                raise RuntimeError(
                    f"{category} persisted draft differs from validated shadow for {field}: "
                    f"{actual[category].get(field)} != {expected[category].get(field)}"
                )


def build_shadow(
    db,
    *,
    service_class=MarketProfileService,
    legacy: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    captures: dict[str, Any] = {}
    runs: dict[str, Any] = {}
    for category, config in CATEGORY_CONFIG.items():
        profiles = []
        signal_count = 0
        pools = []
        member_count = 0
        runs[category] = []
        for batch_id in config["batches"]:
            target_chunks = batch_target_chunks(db, category, batch_id)
            if legacy:
                target_chunks = [tuple(code for chunk in target_chunks for code in chunk)]
            for window in M07_ANALYSIS_WINDOWS:
                for sku_scope in target_chunks:
                    result = run_batch(
                        db,
                        category,
                        batch_id,
                        window=window.value,
                        sku_scope=sku_scope,
                        write=False,
                        service_class=service_class,
                        rule_version=(config["old_rule_version"] if legacy else config["rule_version"]),
                    )
                    profiles.extend(result.profiles)
                    signal_count += len(result.signals)
                    pools.extend(result.pools)
                    member_count += len(result.members)
                    runs[category].append(compact_run(result))
                    print(
                        json.dumps(
                            {
                                "phase": "legacy" if legacy else "shadow",
                                "category": category,
                                "batch_id": batch_id,
                                "window": window.value,
                                "processed_sku_count": len(sku_scope),
                            }
                        ),
                        flush=True,
                    )
        captures[category] = build_capture(profiles, signal_count, pools, member_count)
    return captures, runs


def batch_target_chunks(db, category: str, batch_id: str) -> list[tuple[str, ...]]:
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    repository = M07MarketRepository(context)
    prefix = category.upper()
    clean_sku_codes = {
        row.sku_code
        for row in repository.list_clean_skus(batch_id)
        if row.sku_code and row.sku_code.upper().startswith(prefix)
    }
    market_sku_codes = {
        row.sku_code
        for row in repository.list_clean_market_rows(batch_id)
        if row.sku_code and row.sku_code.upper().startswith(prefix)
    }
    sku_codes = sorted(clean_sku_codes & market_sku_codes)
    return [
        tuple(sku_codes[index : index + TARGET_CHUNK_SIZE])
        for index in range(0, len(sku_codes), TARGET_CHUNK_SIZE)
    ]


def run_batch(
    db,
    category: str,
    batch_id: str,
    *,
    window: str,
    sku_scope: Sequence[str],
    write: bool,
    service_class=MarketProfileService,
    rule_version: str | None = None,
):
    config = CATEGORY_CONFIG[category]
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"m12d-qf05:{category}:{batch_id}"))
    run_row = db.get(entities.Core3V2PipelineRun, run_id) if write else None
    if write and run_row is None:
        run_row = entities.Core3V2PipelineRun(
            run_id=run_id,
            project_id=PROJECT_ID,
            category_code=category,
            run_mode="quality_fix_draft",
            trigger_type="automation",
            triggered_by="M12D-QF-05",
            data_batch_id=batch_id,
            target_scope_json={"module": "M07", "product_category": config["product_category"]},
            ruleset_version=config["rule_version"],
            module_version_json={"M07": config["rule_version"]},
            seed_version_json={},
            input_watermark_json={"batch_id": batch_id},
            status="running",
            release_status="not_ready",
        )
        db.add(run_row)
        db.flush()
    base_repository = M07MarketRepository(context)
    repository = DraftMarketRepository(context) if write else ShadowMarketRepository(base_repository)
    effective_rule_version = rule_version or config["rule_version"]
    result = service_class(repository).run_batch(
        batch_id=batch_id,
        run_id=run_id,
        product_category=config["product_category"],
        rule_version=effective_rule_version,
        price_band_rule_version=config["price_band_rule_version"],
        pool_rule_version=config["pool_rule_version"],
        analysis_windows=(window,),
        sku_scope=sku_scope,
    )
    if run_row is not None:
        run_row.status = "completed"
        run_row.finished_at = datetime.now(timezone.utc)
        run_row.output_summary_json = result.summary
    return result


class ShadowMarketRepository:
    def __init__(self, delegate: M07MarketRepository) -> None:
        self.delegate = delegate
        self.project_id = delegate.project_id
        self.category_code = delegate.category_code

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def save_profiles(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._capture(records)

    def save_signals(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._capture(records)

    def save_pools(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._capture(records)

    def save_members(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return self._capture(records)

    def expire_stale_signals_for_profiles(self, profiles: Sequence[Any], signals: Sequence[Any]) -> int:
        return 0

    @staticmethod
    def _capture(records: Sequence[Any]) -> MarketRepositoryWriteResult:
        return MarketRepositoryWriteResult(records=tuple(records), created_count=len(records))


class DraftMarketRepository(M07MarketRepository):
    def save_members(self, records: Sequence[Any]) -> MarketRepositoryWriteResult:
        if not records:
            return MarketRepositoryWriteResult(records=())
        model = entities.Core3MarketPoolMember
        constraint_name = "uq_core3_market_pool_member_key"
        immutable_columns = {
            "pool_member_id",
            "pool_id",
            "target_sku_code",
            "member_sku_code",
            "rule_version",
            "created_at",
        }
        for start in range(0, len(records), 1000):
            payloads = [
                _jsonable_payload(self._normalize_payload(model, record))
                for record in records[start : start + 1000]
            ]
            statement = pg_insert(model).values(payloads)
            update_values = {
                column.name: statement.excluded[column.name]
                for column in model.__table__.columns
                if column.name not in immutable_columns
            }
            self.db.execute(
                statement.on_conflict_do_update(
                    constraint=constraint_name,
                    set_=update_values,
                )
            )
        self.db.flush()
        return MarketRepositoryWriteResult(records=(), created_count=len(records))


def compact_run(result) -> dict[str, Any]:
    return {
        "status": result.status.value if hasattr(result.status, "value") else str(result.status),
        "input_count": result.input_count,
        "output_count": result.output_count,
        "warnings": list(result.warnings),
        "summary": result.summary,
    }


def capture_db_category(db, category: str, *, use_new: bool) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    rule_version = config["rule_version"] if use_new else config["old_rule_version"]
    profiles = list(
        db.execute(
            select(entities.Core3SkuMarketProfile)
            .where(entities.Core3SkuMarketProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuMarketProfile.category_code == category)
            .where(entities.Core3SkuMarketProfile.batch_id.in_(config["batches"]))
            .where(entities.Core3SkuMarketProfile.rule_version == rule_version)
        ).scalars()
    )
    signal_count = int(
        db.execute(
            select(func.count())
            .select_from(entities.Core3MarketSignal)
            .where(entities.Core3MarketSignal.project_id == PROJECT_ID)
            .where(entities.Core3MarketSignal.category_code == category)
            .where(entities.Core3MarketSignal.batch_id.in_(config["batches"]))
            .where(entities.Core3MarketSignal.rule_version == rule_version)
        ).scalar_one()
    )
    pools = list(
        db.execute(
            select(entities.Core3ComparablePoolBaseline)
            .where(entities.Core3ComparablePoolBaseline.project_id == PROJECT_ID)
            .where(entities.Core3ComparablePoolBaseline.category_code == category)
            .where(entities.Core3ComparablePoolBaseline.batch_id.in_(config["batches"]))
            .where(entities.Core3ComparablePoolBaseline.rule_version == rule_version)
        ).scalars()
    )
    member_count = int(
        db.execute(
            select(func.count())
            .select_from(entities.Core3MarketPoolMember)
            .where(entities.Core3MarketPoolMember.project_id == PROJECT_ID)
            .where(entities.Core3MarketPoolMember.category_code == category)
            .where(entities.Core3MarketPoolMember.batch_id.in_(config["batches"]))
            .where(entities.Core3MarketPoolMember.rule_version == rule_version)
        ).scalar_one()
    )
    return build_capture(profiles, signal_count, pools, member_count)


def capture_db_category_compact(db, category: str, *, use_new: bool) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    rule_version = config["rule_version"] if use_new else config["old_rule_version"]
    profile_table = entities.Core3SkuMarketProfile
    profile_rows = list(
        db.execute(
            select(
                profile_table.sku_code,
                profile_table.analysis_window,
                profile_table.sample_status,
                profile_table.quality_flags,
                profile_table.review_reason_json,
                profile_table.review_required,
                profile_table.price_band_rule_version,
            )
            .where(profile_table.project_id == PROJECT_ID)
            .where(profile_table.category_code == category)
            .where(profile_table.batch_id.in_(config["batches"]))
            .where(profile_table.rule_version == rule_version)
        ).mappings()
    )
    full = [row for row in profile_rows if enum_value(row["analysis_window"]) == "full_observed_window"]
    quality_issues = [
        issue
        for row in profile_rows
        for issue in (row.get("review_reason_json") or {}).get("quality_issues", [])
    ]
    signal_count = int(
        db.execute(
            select(func.count())
            .select_from(entities.Core3MarketSignal)
            .where(entities.Core3MarketSignal.project_id == PROJECT_ID)
            .where(entities.Core3MarketSignal.category_code == category)
            .where(entities.Core3MarketSignal.batch_id.in_(config["batches"]))
            .where(entities.Core3MarketSignal.rule_version == rule_version)
        ).scalar_one()
    )
    pool_count = int(
        db.execute(
            select(func.count())
            .select_from(entities.Core3ComparablePoolBaseline)
            .where(entities.Core3ComparablePoolBaseline.project_id == PROJECT_ID)
            .where(entities.Core3ComparablePoolBaseline.category_code == category)
            .where(entities.Core3ComparablePoolBaseline.batch_id.in_(config["batches"]))
            .where(entities.Core3ComparablePoolBaseline.rule_version == rule_version)
        ).scalar_one()
    )
    pool_rule_versions = dict(
        db.execute(
            select(
                entities.Core3ComparablePoolBaseline.pool_rule_version,
                func.count(),
            )
            .where(entities.Core3ComparablePoolBaseline.project_id == PROJECT_ID)
            .where(entities.Core3ComparablePoolBaseline.category_code == category)
            .where(entities.Core3ComparablePoolBaseline.batch_id.in_(config["batches"]))
            .where(entities.Core3ComparablePoolBaseline.rule_version == rule_version)
            .group_by(entities.Core3ComparablePoolBaseline.pool_rule_version)
        ).all()
    )
    member_count = int(
        db.execute(
            select(func.count())
            .select_from(entities.Core3MarketPoolMember)
            .where(entities.Core3MarketPoolMember.project_id == PROJECT_ID)
            .where(entities.Core3MarketPoolMember.category_code == category)
            .where(entities.Core3MarketPoolMember.batch_id.in_(config["batches"]))
            .where(entities.Core3MarketPoolMember.rule_version == rule_version)
        ).scalar_one()
    )
    cross_category_pool_candidate_count = int(
        db.execute(
            text(
                """select count(*)
                from core3_comparable_pool_baseline pool
                cross join lateral jsonb_array_elements_text(pool.candidate_sku_codes) candidate(value)
                where pool.project_id = :project_id
                  and pool.category_code = :category
                  and pool.batch_id = any(:batch_ids)
                  and pool.rule_version = :rule_version
                  and candidate.value not like :category_prefix"""
            ),
            {
                "project_id": PROJECT_ID,
                "category": category,
                "batch_ids": list(config["batches"]),
                "rule_version": rule_version,
                "category_prefix": f"{category}%",
            },
        ).scalar_one()
    )
    return {
        "profile_count": len(profile_rows),
        "signal_count": signal_count,
        "pool_count": pool_count,
        "member_count": member_count,
        "sku_count": len({row["sku_code"] for row in profile_rows}),
        "window_counts": dict(sorted(Counter(enum_value(row["analysis_window"]) for row in profile_rows).items())),
        "sample_status_counts": dict(sorted(Counter(enum_value(row["sample_status"]) for row in profile_rows).items())),
        "full_sample_status_counts": dict(sorted(Counter(enum_value(row["sample_status"]) for row in full).items())),
        "full_flag_counts": dict(sorted(Counter(flag for row in full for flag in (row.get("quality_flags") or [])).items())),
        "quality_issue_counts": dict(sorted(Counter(str(issue.get("issue_code")) for issue in quality_issues).items())),
        "quality_severity_counts": dict(sorted(Counter(str(issue.get("severity")) for issue in quality_issues).items())),
        "full_review_required_count": sum(1 for row in full if row.get("review_required")),
        "price_band_rule_versions": dict(sorted(Counter(row.get("price_band_rule_version") for row in full).items())),
        "pool_rule_versions": dict(sorted(pool_rule_versions.items())),
        "cross_category_pool_candidate_count": cross_category_pool_candidate_count,
    }


def build_capture(
    profiles: Sequence[Any],
    signals: Sequence[Any] | int,
    pools: Sequence[Any],
    members: Sequence[Any] | int,
) -> dict[str, Any]:
    profile_rows = [payload_of(row) for row in profiles]
    pool_rows = [payload_of(row) for row in pools]
    profile_map = {
        (row["batch_id"], row["sku_code"], enum_value(row["analysis_window"])): row
        for row in profile_rows
    }
    pool_map = {
        (
            row["batch_id"],
            row["target_sku_code"],
            enum_value(row["analysis_window"]),
            enum_value(row["pool_type"]),
        ): row
        for row in pool_rows
    }
    full = [row for row in profile_rows if enum_value(row["analysis_window"]) == "full_observed_window"]
    quality_issues = [
        issue
        for row in profile_rows
        for issue in (row.get("review_reason_json") or {}).get("quality_issues", [])
    ]
    cross_category_pool_candidate_count = sum(
        1
        for row in pool_rows
        for candidate in (row.get("candidate_sku_codes") or [])
        if not str(candidate).upper().startswith(str(row.get("category_code") or "").upper())
    )
    return {
        "profile_count": len(profile_rows),
        "signal_count": signals if isinstance(signals, int) else len(signals),
        "pool_count": len(pool_rows),
        "member_count": members if isinstance(members, int) else len(members),
        "sku_count": len({row["sku_code"] for row in profile_rows}),
        "window_counts": dict(sorted(Counter(enum_value(row["analysis_window"]) for row in profile_rows).items())),
        "sample_status_counts": dict(sorted(Counter(enum_value(row["sample_status"]) for row in profile_rows).items())),
        "full_sample_status_counts": dict(sorted(Counter(enum_value(row["sample_status"]) for row in full).items())),
        "full_flag_counts": dict(sorted(Counter(flag for row in full for flag in row.get("quality_flags", [])).items())),
        "quality_issue_counts": dict(sorted(Counter(str(issue.get("issue_code")) for issue in quality_issues).items())),
        "quality_severity_counts": dict(sorted(Counter(str(issue.get("severity")) for issue in quality_issues).items())),
        "full_review_required_count": sum(1 for row in full if row.get("review_required")),
        "price_band_rule_versions": dict(sorted(Counter(row.get("price_band_rule_version") for row in full).items())),
        "pool_rule_versions": dict(sorted(Counter(row.get("pool_rule_version") for row in pool_rows).items())),
        "cross_category_pool_candidate_count": cross_category_pool_candidate_count,
        "profiles": profile_map,
        "pools": pool_map,
    }


def compare_category(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    old_profile_keys = set(before["profiles"])
    new_profile_keys = set(after["profiles"])
    old_pool_keys = set(before["pools"])
    new_pool_keys = set(after["pools"])
    self_raw_changes = []
    comparison_field_changes = []
    full_confidence_changes = []
    for key in sorted(old_profile_keys & new_profile_keys):
        old = before["profiles"][key]
        new = after["profiles"][key]
        self_changed = [
            field
            for field in SELF_RAW_PROFILE_FIELDS
            if normalized(old.get(field)) != normalized(new.get(field))
        ]
        comparison_changed = [
            field
            for field in COMPARISON_PROFILE_FIELDS
            if normalized(old.get(field)) != normalized(new.get(field))
        ]
        if self_changed:
            self_raw_changes.append({"key": key, "fields": self_changed})
        if comparison_changed:
            comparison_field_changes.append({"key": key, "fields": comparison_changed})
        if key[2] == "full_observed_window" and normalized(old.get("market_confidence")) != normalized(new.get("market_confidence")):
            full_confidence_changes.append(key)
    pool_membership_changes = []
    for key in sorted(old_pool_keys & new_pool_keys):
        old = before["pools"][key]
        new = after["pools"][key]
        old_candidates = set(old.get("candidate_sku_codes") or [])
        new_candidates = set(new.get("candidate_sku_codes") or [])
        if old_candidates != new_candidates:
            pool_membership_changes.append(
                {
                    "key": key,
                    "removed_candidates": sorted(old_candidates - new_candidates),
                    "added_candidates": sorted(new_candidates - old_candidates),
                }
            )
    removed_pool_details = [
        {
            "key": key,
            "candidate_sku_codes": sorted(before["pools"][key].get("candidate_sku_codes") or []),
        }
        for key in sorted(old_pool_keys - new_pool_keys)
    ]
    return {
        "profile_added_count": len(new_profile_keys - old_profile_keys),
        "profile_removed_count": len(old_profile_keys - new_profile_keys),
        "pool_added_count": len(new_pool_keys - old_pool_keys),
        "pool_removed_count": len(old_pool_keys - new_pool_keys),
        "pool_removed_samples": removed_pool_details[:10],
        "self_raw_profile_change_count": len(self_raw_changes),
        "self_raw_profile_change_samples": self_raw_changes[:10],
        "comparison_field_change_count": len(comparison_field_changes),
        "comparison_field_change_samples": comparison_field_changes[:10],
        "full_confidence_change_count": len(full_confidence_changes),
        "full_confidence_change_samples": full_confidence_changes[:10],
        "pool_membership_change_count": len(pool_membership_changes),
        "pool_membership_change_samples": pool_membership_changes[:10],
        "sample_status_counts_before": before["sample_status_counts"],
        "sample_status_counts_after": after["sample_status_counts"],
        "full_sample_status_counts_before": before["full_sample_status_counts"],
        "full_sample_status_counts_after": after["full_sample_status_counts"],
        "full_flag_counts_before": before["full_flag_counts"],
        "full_flag_counts_after": after["full_flag_counts"],
        "quality_issue_counts_after": after["quality_issue_counts"],
        "quality_severity_counts_after": after["quality_severity_counts"],
    }


def assert_acceptance(comparisons: Mapping[str, Mapping[str, Any]], captures: Mapping[str, Mapping[str, Any]]) -> None:
    for category, comparison in comparisons.items():
        for field in (
            "profile_added_count",
            "profile_removed_count",
            "self_raw_profile_change_count",
        ):
            if comparison[field] != 0:
                raise RuntimeError(f"{category} unexpected {field}: {comparison[field]}")
        capture = captures[category]
        if capture["cross_category_pool_candidate_count"]:
            raise RuntimeError(
                f"{category} still has cross-category pool candidates: "
                f"{capture['cross_category_pool_candidate_count']}"
            )
        expected_status = CATEGORY_CONFIG[category]["expected_full_sample_status"]
        if capture["full_sample_status_counts"] != expected_status:
            raise RuntimeError(
                f"{category} full-window status changed: {capture['full_sample_status_counts']} != {expected_status}"
            )
        expected_confidence_migrations = CATEGORY_CONFIG[category]["expected_full_confidence_migrations"]
        if comparison["full_confidence_change_count"] != expected_confidence_migrations:
            raise RuntimeError(
                f"{category} unexpected full confidence migrations: "
                f"{comparison['full_confidence_change_count']} != {expected_confidence_migrations}"
            )
        flags = capture["full_flag_counts"]
        for derived_flag in (
            "observed_window_less_than_52w",
            "online_only_channel",
            "trend_sample_insufficient",
            "baseline_window_insufficient",
            "latest_week_gap",
        ):
            if flags.get(derived_flag, 0):
                raise RuntimeError(f"{category} invalid quality flag remains: {derived_flag}")
        if capture["full_review_required_count"]:
            raise RuntimeError(f"{category} metric-scoped quality issues incorrectly require full-profile review")
        if not capture["quality_issue_counts"].get("observed_window_less_than_52w"):
            raise RuntimeError(f"{category} missing structured observed-window range info")
        if not capture["quality_issue_counts"].get("online_only_channel"):
            raise RuntimeError(f"{category} missing structured online-channel range info")


def capture_downstream_guard(db) -> dict[str, Any]:
    result = {}
    for table_name in DOWNSTREAM_TABLES:
        row = db.execute(
            text(f"select count(*) as row_count, max(updated_at) as max_updated_at from {table_name}")
        ).mappings().one()
        result[table_name] = {
            "row_count": int(row["row_count"] or 0),
            "max_updated_at": row["max_updated_at"].isoformat() if row["max_updated_at"] else None,
        }
    return result


def payload_of(row: Any) -> dict[str, Any]:
    if hasattr(row, "model_dump"):
        return row.model_dump(mode="python")
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def normalized(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value.normalize())
    if isinstance(value, float):
        return str(Decimal(str(value)).normalize())
    if hasattr(value, "value"):
        return value.value
    return value


def enum_value(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value)


def compact_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in capture.items() if key not in {"profiles", "pools"}}


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-05 TV/AC M07 v2 Draft Report",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Write draft: `{payload['write_draft']}`",
        f"- Downstream unchanged: `{payload['downstream_guard']['unchanged']}`",
        "",
    ]
    for category in ("TV", "AC"):
        before = payload["before"][category]
        after = payload["after"][category]
        comparison = payload["comparisons"][category]
        lines.extend(
            [
                f"## {category}",
                "",
                f"- Profiles: `{before['profile_count']} -> {after['profile_count']}`",
                f"- Full sample status: `{before['full_sample_status_counts']} -> {after['full_sample_status_counts']}`",
                f"- Full flags: `{before['full_flag_counts']} -> {after['full_flag_counts']}`",
                f"- Quality issues: `{after['quality_issue_counts']}`",
                f"- Self raw profile changes: `{comparison['self_raw_profile_change_count']}`",
                f"- Comparison-field changes: `{comparison['comparison_field_change_count']}`",
                f"- Full confidence changes: `{comparison['full_confidence_change_count']}`",
                f"- Pool membership changes: `{comparison['pool_membership_change_count']}`",
                f"- Price-band versions: `{after['price_band_rule_versions']}`",
                f"- Pool versions: `{after['pool_rule_versions']}`",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", action="store_true")
    parser.add_argument("--validate-persisted-only", action="store_true")
    parser.add_argument("--validated-shadow-json")
    parser.add_argument("--output-json", default="/tmp/M12D_QF05_tv_ac_m07_draft.json")
    parser.add_argument("--output-markdown", default="/tmp/M12D_QF05_tv_ac_m07_draft_report.md")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
