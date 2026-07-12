#!/usr/bin/env python3
"""Rebuild TV/AC M05C v0.2 drafts from existing classified comment facts."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from sqlalchemy import select, text

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
)
from app.services.core3_real_data.m05c_comment_fact_profile_service import (
    DIMENSION_TYPE_SERVICE,
    LLM_MODE_OFF,
    M05CCommentEvidenceReader,
    M05CCommentFactRepository,
    M05CCommentTaxonomyLoader,
    M05CLlmAnnotation,
    M05CProfileBuilder,
    M05CService,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
CATEGORY_CONFIG = {
    "TV": {
        "product_category": "TV",
        "batches": (
            "m00_20260613004311_d548f6dc",
            "m00_20260619084551_857df63b",
            "m00_20260623014631_c8630747",
        ),
        "taxonomy_version": CORE3_M05C_TV_TAXONOMY_VERSION,
        "old_rule_version": "m05c_tv_comment_fact_profile_v0.1",
        "rule_version": CORE3_M05C_TV_RULE_VERSION,
        "param_rule_version": CORE3_M03B_RULE_VERSION,
        "claim_rule_version": CORE3_M04C_TV_RULE_VERSION,
    },
    "AC": {
        "product_category": "AC",
        "batches": ("m00_20260624000202_1150a669",),
        "taxonomy_version": CORE3_M05C_AC_TAXONOMY_VERSION,
        "old_rule_version": "m05c_ac_comment_fact_profile_v0.1",
        "rule_version": CORE3_M05C_AC_RULE_VERSION,
        "param_rule_version": CORE3_M03B_AC_RULE_VERSION,
        "claim_rule_version": CORE3_M04C_AC_RULE_VERSION,
    },
}

DOWNSTREAM_TABLES = (
    "core3_sku_market_profile",
    "core3_m09c_sku_user_task_profile",
    "core3_m10c_sku_target_group_profile",
    "core3_sku_value_battlefield_profile",
    "core3_sku_claim_value_quantification",
    "core3_sku_purchase_reason_profile",
)


def main() -> int:
    args = parse_args()
    output_json = Path(args.output_json)
    output_markdown = Path(args.output_markdown)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    with SessionLocal() as db:
        downstream_before = capture_downstream_guard(db)
        before = {category: capture_db_category(db, category, use_new=False) for category in CATEGORY_CONFIG}
        shadows = {category: build_shadow_category(db, category) for category in CATEGORY_CONFIG}
        shadow_captures = {category: value["capture"] for category, value in shadows.items()}
        shadow_comparisons = {
            category: compare_category(before[category], shadow_captures[category])
            for category in CATEGORY_CONFIG
        }
        assert_acceptance(shadow_comparisons, shadow_captures)

        write_results: dict[str, Any] = {}
        if args.write_draft:
            for category, shadow in shadows.items():
                write_results[category] = write_shadow(db, category, shadow)
                db.commit()

        after = {
            category: capture_db_category(db, category, use_new=True)
            if args.write_draft
            else shadow_captures[category]
            for category in CATEGORY_CONFIG
        }
        if args.write_draft:
            for category in CATEGORY_CONFIG:
                after[category]["context_summary"] = shadow_captures[category]["context_summary"]
        downstream_after = capture_downstream_guard(db)

    comparisons = {
        category: compare_category(before[category], after[category])
        for category in CATEGORY_CONFIG
    }
    assert_acceptance(comparisons, after)
    if downstream_before != downstream_after:
        raise RuntimeError("M07 and later downstream tables changed during M05C draft rebuild")

    payload = {
        "task_id": "M12D-QF-04",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": PROJECT_ID,
        "scope": "M05C only",
        "write_draft": args.write_draft,
        "classification_source": "existing M05C v0.1 fact topic and polarity; no LLM call",
        "allowed_migrations": {
            "TV": [
                "param_profile_missing is recomputed from current TV M03B v0.2 serving scope",
                "claim_fact_profile_missing is recomputed from current TV M04C v0.2 profile presence",
                "service exclusion and comment contradiction move from SKU profile flags to localized notices/issues",
                "support relation may change only because current M03B/M04C context replaces batch-exact historical context",
            ],
            "AC": [
                "service exclusion and comment contradiction move from SKU profile flags to localized notices/issues",
                "M03B/M04C context is revalidated against AC-only v0.2 versions",
            ],
        },
        "before": {category: compact_capture(value) for category, value in before.items()},
        "after": {category: compact_capture(value) for category, value in after.items()},
        "comparisons": comparisons,
        "write_results": write_results,
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


def build_shadow_category(db, category: str) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    service = M05CService(context)
    reader = M05CCommentEvidenceReader(context)
    taxonomy = M05CCommentTaxonomyLoader().load(
        config["taxonomy_version"],
        product_category=config["product_category"],
    )
    all_profiles = []
    all_facts = []
    all_coverages = []
    all_reviews = []
    context_summary = {
        "param_source_batches": Counter(),
        "claim_source_batches": Counter(),
        "param_missing_skus": set(),
        "claim_profile_missing_skus": set(),
    }

    for batch_id in config["batches"]:
        old_profiles = list(
            db.execute(
                select(entities.Core3SkuCommentFactProfile)
                .where(entities.Core3SkuCommentFactProfile.project_id == PROJECT_ID)
                .where(entities.Core3SkuCommentFactProfile.category_code == category)
                .where(entities.Core3SkuCommentFactProfile.product_category == config["product_category"])
                .where(entities.Core3SkuCommentFactProfile.batch_id == batch_id)
                .where(entities.Core3SkuCommentFactProfile.taxonomy_version == config["taxonomy_version"])
                .where(entities.Core3SkuCommentFactProfile.rule_version == config["old_rule_version"])
            ).scalars()
        )
        target_skus = sorted({row.sku_code for row in old_profiles})
        if not target_skus:
            continue
        records = reader.list_comment_records(
            batch_id,
            sku_code_prefix=taxonomy.sku_code_prefix,
            target_sku_codes=target_skus,
        )
        old_facts = list(
            db.execute(
                select(entities.Core3CommentFactAtom)
                .where(entities.Core3CommentFactAtom.project_id == PROJECT_ID)
                .where(entities.Core3CommentFactAtom.category_code == category)
                .where(entities.Core3CommentFactAtom.product_category == config["product_category"])
                .where(entities.Core3CommentFactAtom.batch_id == batch_id)
                .where(entities.Core3CommentFactAtom.taxonomy_version == config["taxonomy_version"])
                .where(entities.Core3CommentFactAtom.rule_version == config["old_rule_version"])
            ).scalars()
        )
        annotations = annotations_from_existing_facts(old_facts)
        param_profiles = service._read_param_profiles(
            batch_id,
            sku_codes=target_skus,
            rule_version=config["param_rule_version"],
        )
        claim_profiles, claim_facts = service._read_claim_context(
            batch_id,
            sku_codes=target_skus,
            product_category=config["product_category"],
            rule_version=config["claim_rule_version"],
        )
        context_summary["param_source_batches"].update(row.batch_id for row in param_profiles.values())
        context_summary["claim_source_batches"].update(row.batch_id for row in claim_profiles.values())
        context_summary["param_missing_skus"].update(set(target_skus) - set(param_profiles))
        context_summary["claim_profile_missing_skus"].update(set(target_skus) - set(claim_profiles))

        records_by_sku: dict[str, list[Any]] = defaultdict(list)
        for record in records:
            records_by_sku[record.sku_code].append(record)
        builder = M05CProfileBuilder(
            project_id=PROJECT_ID,
            category_code=category,
            batch_id=batch_id,
            taxonomy=taxonomy,
            rule_version=config["rule_version"],
            llm_mode=LLM_MODE_OFF,
        )
        batch_facts = []
        for sku_code in target_skus:
            sku_result = builder._build_sku(
                sku_code,
                records_by_sku[sku_code],
                param_profiles.get(sku_code),
                claim_facts.get(sku_code, {}),
                sku_code in claim_profiles,
                annotations.get(sku_code, {}),
            )
            all_profiles.append(sku_result["profile"])
            all_facts.extend(sku_result["facts"])
            all_reviews.extend(sku_result["review_issues"])
            batch_facts.extend(sku_result["facts"])
        all_coverages.extend(builder._build_coverages(batch_facts, total_sku_count=len(target_skus)))

    capture = build_capture(
        all_profiles,
        all_facts,
        all_reviews,
        context_summary={
            "param_source_batch_counts": dict(sorted(context_summary["param_source_batches"].items())),
            "claim_source_batch_counts": dict(sorted(context_summary["claim_source_batches"].items())),
            "param_missing_sku_count": len(context_summary["param_missing_skus"]),
            "claim_profile_missing_sku_count": len(context_summary["claim_profile_missing_skus"]),
        },
    )
    return {
        "profiles": all_profiles,
        "facts": all_facts,
        "coverages": all_coverages,
        "reviews": all_reviews,
        "capture": capture,
    }


def annotations_from_existing_facts(rows: Sequence[entities.Core3CommentFactAtom]) -> dict[str, dict[str, M05CLlmAnnotation]]:
    grouped: dict[tuple[str, str], list[entities.Core3CommentFactAtom]] = defaultdict(list)
    for row in rows:
        grouped[(row.sku_code, row.source_comment_key)].append(row)
    result: dict[str, dict[str, M05CLlmAnnotation]] = defaultdict(dict)
    for (sku_code, source_key), facts in grouped.items():
        first = facts[0]
        extraction = first.extraction_payload_json or {}
        was_llm = extraction.get("method") == "llm"
        result[sku_code][source_key] = M05CLlmAnnotation(
            source_comment_key=source_key,
            subdimension_codes=tuple(sorted({row.subdimension_code for row in facts})),
            polarity=first.polarity,
            confidence=float(extraction.get("llm_confidence") or first.confidence or 1) if was_llm else None,
            rationale=extraction.get("llm_rationale"),
        )
    return {sku_code: dict(values) for sku_code, values in result.items()}


def write_shadow(db, category: str, shadow: Mapping[str, Any]) -> dict[str, Any]:
    context = Core3RepositoryContext(db=db, project_id=PROJECT_ID, category_code=category)
    repository = M05CCommentFactRepository(context)
    writes = {
        "profiles": repository.save_profiles(shadow["profiles"], replace_on_hash_conflict=True),
        "facts": repository.save_facts(shadow["facts"], replace_on_hash_conflict=True),
        "coverages": repository.save_coverages(shadow["coverages"], replace_on_hash_conflict=True),
        "reviews": repository.save_review_issues(shadow["reviews"], replace_on_hash_conflict=True),
    }
    return {
        name: {
            "created_count": value.created_count,
            "reused_count": value.reused_count,
            "record_count": len(value.records),
        }
        for name, value in writes.items()
    }


def capture_db_category(db, category: str, *, use_new: bool) -> dict[str, Any]:
    config = CATEGORY_CONFIG[category]
    rule_version = config["rule_version"] if use_new else config["old_rule_version"]
    profiles = list(
        db.execute(
            select(entities.Core3SkuCommentFactProfile)
            .where(entities.Core3SkuCommentFactProfile.project_id == PROJECT_ID)
            .where(entities.Core3SkuCommentFactProfile.category_code == category)
            .where(entities.Core3SkuCommentFactProfile.product_category == config["product_category"])
            .where(entities.Core3SkuCommentFactProfile.batch_id.in_(config["batches"]))
            .where(entities.Core3SkuCommentFactProfile.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3SkuCommentFactProfile.rule_version == rule_version)
        ).scalars()
    )
    facts = list(
        db.execute(
            select(entities.Core3CommentFactAtom)
            .where(entities.Core3CommentFactAtom.project_id == PROJECT_ID)
            .where(entities.Core3CommentFactAtom.category_code == category)
            .where(entities.Core3CommentFactAtom.product_category == config["product_category"])
            .where(entities.Core3CommentFactAtom.batch_id.in_(config["batches"]))
            .where(entities.Core3CommentFactAtom.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3CommentFactAtom.rule_version == rule_version)
        ).scalars()
    )
    reviews = list(
        db.execute(
            select(entities.Core3CommentFactReviewIssue)
            .where(entities.Core3CommentFactReviewIssue.project_id == PROJECT_ID)
            .where(entities.Core3CommentFactReviewIssue.category_code == category)
            .where(entities.Core3CommentFactReviewIssue.product_category == config["product_category"])
            .where(entities.Core3CommentFactReviewIssue.batch_id.in_(config["batches"]))
            .where(entities.Core3CommentFactReviewIssue.taxonomy_version == config["taxonomy_version"])
            .where(entities.Core3CommentFactReviewIssue.rule_version == rule_version)
        ).scalars()
    )
    return build_capture(profiles, facts, reviews)


def build_capture(
    profiles: Sequence[Any],
    facts: Sequence[Any],
    reviews: Sequence[Any],
    *,
    context_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    profile_rows = [payload_of(row) for row in profiles]
    fact_rows = [payload_of(row) for row in facts]
    review_rows = [payload_of(row) for row in reviews]
    profile_map = {(row["batch_id"], row["sku_code"]): row for row in profile_rows}
    fact_map = {
        (row["batch_id"], row["sku_code"], row["source_comment_key"], row["subdimension_code"]): row
        for row in fact_rows
    }
    return {
        "profile_count": len(profile_rows),
        "fact_count": len(fact_rows),
        "review_issue_count": len(review_rows),
        "profile_flag_counts": dict(sorted(Counter(flag for row in profile_rows for flag in row.get("quality_flags", [])).items())),
        "service_fact_count": sum(1 for row in fact_rows if row.get("dimension_type") == DIMENSION_TYPE_SERVICE),
        "contradiction_fact_count": sum(1 for row in fact_rows if row.get("support_relation") == "contradicts_sku_param_claim"),
        "contradiction_sku_count": len(
            {row["sku_code"] for row in fact_rows if row.get("support_relation") == "contradicts_sku_param_claim"}
        ),
        "support_relation_counts": dict(sorted(Counter(str(row.get("support_relation")) for row in fact_rows).items())),
        "context_summary": dict(context_summary or {}),
        "profiles": profile_map,
        "facts": fact_map,
    }


def compare_category(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    before_profile_keys = set(before["profiles"])
    after_profile_keys = set(after["profiles"])
    before_fact_keys = set(before["facts"])
    after_fact_keys = set(after["facts"])
    immutable_fields = (
        "batch_id",
        "sku_code",
        "source_comment_key",
        "clean_comment_text",
        "dimension_code",
        "subdimension_code",
        "dimension_type",
        "polarity",
        "evidence_ids",
    )
    immutable_changes = []
    support_changes = 0
    for key in sorted(before_fact_keys & after_fact_keys):
        old = before["facts"][key]
        new = after["facts"][key]
        changed = [field for field in immutable_fields if old.get(field) != new.get(field)]
        if changed:
            immutable_changes.append({"key": key, "fields": changed})
        support_fields = (
            "support_relation",
            "support_target_type",
            "supported_param_codes",
            "contradicted_param_codes",
            "supported_claim_codes",
            "contradicted_claim_codes",
        )
        if any(old.get(field) != new.get(field) for field in support_fields):
            support_changes += 1
    return {
        "profile_added_count": len(after_profile_keys - before_profile_keys),
        "profile_removed_count": len(before_profile_keys - after_profile_keys),
        "fact_added_count": len(after_fact_keys - before_fact_keys),
        "fact_removed_count": len(before_fact_keys - after_fact_keys),
        "immutable_fact_change_count": len(immutable_changes),
        "immutable_fact_change_samples": immutable_changes[:10],
        "support_context_change_count": support_changes,
        "profile_flag_counts_before": before["profile_flag_counts"],
        "profile_flag_counts_after": after["profile_flag_counts"],
        "service_fact_count_before": before["service_fact_count"],
        "service_fact_count_after": after["service_fact_count"],
        "contradiction_fact_count_before": before["contradiction_fact_count"],
        "contradiction_fact_count_after": after["contradiction_fact_count"],
        "contradiction_sku_count_before": before["contradiction_sku_count"],
        "contradiction_sku_count_after": after["contradiction_sku_count"],
        "review_issue_count_before": before["review_issue_count"],
        "review_issue_count_after": after["review_issue_count"],
        "context_summary_after": after.get("context_summary", {}),
    }


def assert_acceptance(comparisons: Mapping[str, Mapping[str, Any]], captures: Mapping[str, Mapping[str, Any]]) -> None:
    for category, comparison in comparisons.items():
        for field in (
            "profile_added_count",
            "profile_removed_count",
            "fact_added_count",
            "fact_removed_count",
            "immutable_fact_change_count",
        ):
            if comparison[field] != 0:
                raise RuntimeError(f"{category} unexpected {field}: {comparison[field]}")
        flags = captures[category]["profile_flag_counts"]
        if flags.get("service_fulfillment_comment_excluded", 0):
            raise RuntimeError(f"{category} service exclusion still degrades SKU profiles")
        if flags.get("comment_contradicts_existing_param_or_claim", 0):
            raise RuntimeError(f"{category} localized contradiction still degrades SKU profiles")
        context = captures[category].get("context_summary") or {}
        if context:
            if flags.get("param_profile_missing", 0) != context["param_missing_sku_count"]:
                raise RuntimeError(f"{category} param missing flags do not match serving scope")
            if flags.get("claim_fact_profile_missing", 0) != context["claim_profile_missing_sku_count"]:
                raise RuntimeError(f"{category} claim profile missing flags do not match serving scope")
        if captures[category]["review_issue_count"] != captures[category]["contradiction_fact_count"]:
            raise RuntimeError(f"{category} localized review issues do not match contradiction facts")


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
    if hasattr(row, "payload"):
        return dict(row.payload)
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


def compact_capture(capture: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in capture.items() if key not in {"profiles", "facts"}}


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# M12D-QF-04 TV/AC M05C v0.2 Draft Report",
        "",
        f"- Generated: `{payload['generated_at']}`",
        f"- Write draft: `{payload['write_draft']}`",
        "- Classification: reuse existing M05C v0.1 topic and polarity; no LLM call.",
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
                f"- Facts: `{before['fact_count']} -> {after['fact_count']}`",
                f"- Profile flags: `{before['profile_flag_counts']} -> {after['profile_flag_counts']}`",
                f"- Service facts retained: `{before['service_fact_count']} -> {after['service_fact_count']}`",
                f"- Contradiction facts: `{before['contradiction_fact_count']} -> {after['contradiction_fact_count']}`",
                f"- Contradiction SKUs: `{before['contradiction_sku_count']} -> {after['contradiction_sku_count']}`",
                f"- Local review issues: `{before['review_issue_count']} -> {after['review_issue_count']}`",
                f"- Support-context changes: `{comparison['support_context_change_count']}`",
                f"- Immutable fact changes: `{comparison['immutable_fact_change_count']}`",
                f"- Serving-scope context: `{json.dumps(after.get('context_summary', {}), ensure_ascii=False)}`",
                "",
            ]
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-draft", action="store_true")
    parser.add_argument(
        "--output-json",
        default="/tmp/M12D_QF04_tv_ac_m05c_draft.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="/tmp/M12D_QF04_tv_ac_m05c_draft_report.md",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
