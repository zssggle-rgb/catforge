#!/usr/bin/env python3
"""Capture a read-only legacy competitor-set JSON response as a G28 fixture.

The remote command is intentionally executed by the caller.  This helper only
accepts its JSON stdout, removes presentation-only fields, validates that the
legacy default candidate limit was used, and writes deterministic gzip JSON.
It has no database, network, Feishu, or profile-generation dependency.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


SNAPSHOT_KEYS = (
    "status",
    "project_id",
    "category_code",
    "batch_id",
    "product_category",
    "market_window",
    "analysis_population",
    "target",
    "sop_steps",
    "atoms_used",
)

LEGACY_INPUT_KEYS = (
    "ranking_policy",
    "target_fact_brief",
    "target_claim_value",
    "target_claim_contribution",
    "candidate_count",
    "candidates",
)

LEGACY_ANALYSIS_KEYS = (
    "selection_policy_cn",
    "candidate_buckets",
    "all_candidates",
    "top_competitors",
)

PRESENTATION_ONLY_KEYS = {
    "dashboard_payload",
    "display_policy",
    "evidence_report_url",
    "feishu_card_payload",
    "pm_comparison_report_message_cn",
    "pm_comparison_report_payload",
    "pm_comparison_report_status",
    "pm_comparison_report_url",
    "report_message_cn",
    "report_payload",
    "report_status",
    "report_url",
    "short_answer",
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _select(source: dict[str, Any], keys: tuple[str, ...], *, label: str) -> dict[str, Any]:
    missing = [key for key in keys if key not in source]
    if missing:
        raise ValueError(f"{label} is missing required keys: {missing}")
    return {key: source[key] for key in keys}


def _write_deterministic_gzip(path: Path, raw: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as binary_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=binary_handle,
            mtime=0,
        ) as gzip_handle:
            gzip_handle.write(raw)


def capture(
    response: dict[str, Any],
    *,
    expected_sku_code: str,
    expected_category_code: str,
    maximum_candidate_count: int,
    minimum_candidate_count: int,
) -> dict[str, Any]:
    if response.get("status") != "ok":
        raise ValueError(f"legacy competitor-set did not return ok: {response.get('status')}")
    if response.get("command") != "competitor-set":
        raise ValueError(f"unexpected command: {response.get('command')}")
    target = response.get("target") or {}
    if target.get("sku_code") != expected_sku_code:
        raise ValueError(
            f"unexpected target SKU: {target.get('sku_code')} != {expected_sku_code}"
        )
    if response.get("category_code") != expected_category_code:
        raise ValueError(
            "unexpected category: "
            f"{response.get('category_code')} != {expected_category_code}"
        )

    result = response.get("result") or {}
    competitor_set = result.get("competitor_set") or {}
    competitor_answer = result.get("competitor_answer") or {}
    candidate_count = competitor_set.get("candidate_count")
    if not isinstance(candidate_count, int):
        raise ValueError(f"legacy candidate_count is not an integer: {candidate_count}")
    if not minimum_candidate_count <= candidate_count <= maximum_candidate_count:
        raise ValueError(
            "legacy default-limit fixture candidate count is outside the allowed range: "
            f"{candidate_count} not in [{minimum_candidate_count}, "
            f"{maximum_candidate_count}]"
        )
    if len(competitor_set.get("candidates") or []) != candidate_count:
        raise ValueError("legacy candidate_count does not match candidates length")
    if len(competitor_answer.get("all_candidates") or []) != candidate_count:
        raise ValueError("legacy answer does not contain every candidate")
    leaked = PRESENTATION_ONLY_KEYS.intersection(competitor_answer)
    if not leaked:
        raise ValueError(
            "expected xiaoao response with presentation fields before fixture stripping"
        )

    return {
        "snapshot": _select(response, SNAPSHOT_KEYS, label="legacy snapshot"),
        "legacy_input": _select(
            competitor_set,
            LEGACY_INPUT_KEYS,
            label="legacy competitor input",
        ),
        "legacy_analysis": _select(
            competitor_answer,
            LEGACY_ANALYSIS_KEYS,
            label="legacy competitor analysis",
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sku-code", required=True)
    parser.add_argument("--category-code", choices=("TV", "AC"), required=True)
    parser.add_argument("--maximum-candidate-count", type=int, default=20)
    parser.add_argument("--minimum-candidate-count", type=int, default=1)
    args = parser.parse_args()

    source_raw = sys.stdin.buffer.read()
    response = json.loads(source_raw)
    fixture = capture(
        response,
        expected_sku_code=args.sku_code,
        expected_category_code=args.category_code,
        maximum_candidate_count=args.maximum_candidate_count,
        minimum_candidate_count=args.minimum_candidate_count,
    )
    canonical_raw = _canonical_bytes(fixture)
    _write_deterministic_gzip(args.output, canonical_raw)
    receipt = {
        "status": "captured",
        "output": args.output.name,
        "source_stdout_sha256": _sha256(source_raw),
        "canonical_json_sha256": _sha256(canonical_raw),
        "canonical_json_bytes": len(canonical_raw),
        "gzip_bytes": args.output.stat().st_size,
        "target_sku_code": args.sku_code,
        "category_code": args.category_code,
        "candidate_count": fixture["legacy_input"]["candidate_count"],
        "default_candidate_limit": args.maximum_candidate_count,
        "presentation_fields_removed": sorted(PRESENTATION_ONLY_KEYS),
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
