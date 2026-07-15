#!/usr/bin/env python3
"""Reproduce all four G28 legacy fixtures and emit exact argv receipts.

The same process constructs the remote application argv, asserts that no
``--limit`` token is present, captures stdout, validates its canonical hash,
writes the deterministic fixture, and records the receipt.  This closes the
audit gap left by hand-written capture metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from G28_capture_legacy_fixture import (
    PRESENTATION_ONLY_KEYS,
    _canonical_bytes,
    _write_deterministic_gzip,
    capture,
)


HERE = Path(__file__).resolve().parent
PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
DEFAULT_LIMIT = 20
TV_BATCH = (
    "serving-scope:TV:m00_20260623014631_c8630747,"
    "m00_20260619084551_857df63b,m00_20260613004311_d548f6dc"
)
AC_BATCH = "m00_20260624000202_1150a669"

SPECS = (
    {
        "fixture": "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz",
        "category_code": "TV",
        "product_category": "tv",
        "batch_id": TV_BATCH,
        "sku_code": "TV00029112",
        "candidate_count": 20,
        "canonical_json_sha256": (
            "048d0314b3c18d72279fe03a37f1149342911f7c5e4e844a5ad0bd7754edd86a"
        ),
    },
    {
        "fixture": "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz",
        "category_code": "TV",
        "product_category": "tv",
        "batch_id": TV_BATCH,
        "sku_code": "TV00009549",
        "candidate_count": 13,
        "canonical_json_sha256": (
            "ad4fe69647682e24da43b834bfd8a6e7c372a37f5b5a2b34ed2c8a49a2b045f5"
        ),
    },
    {
        "fixture": "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz",
        "category_code": "AC",
        "product_category": "ac",
        "batch_id": AC_BATCH,
        "sku_code": "AC00026378",
        "candidate_count": 16,
        "canonical_json_sha256": (
            "92f183cbe8043faab347c053a98cbea661653e496db2a4a4ee019589513ddb1a"
        ),
    },
    {
        "fixture": "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz",
        "category_code": "AC",
        "product_category": "ac",
        "batch_id": AC_BATCH,
        "sku_code": "AC00034959",
        "candidate_count": 20,
        "canonical_json_sha256": (
            "1d0f5c129edaa85cde5c220642f11d961075974ee2308f860de8e2888129b553"
        ),
    },
)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _ssh_prefix(args: argparse.Namespace) -> list[str]:
    return [
        "ssh",
        "-i",
        str(args.ssh_key),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        args.host,
    ]


def _run_remote(
    args: argparse.Namespace,
    remote_argv: list[str],
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.run(
        [*_ssh_prefix(args), *remote_argv],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode != 0:
        safe_error = process.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(
            f"read-only remote command failed ({process.returncode}): {safe_error}"
        )
    return process


def _app_argv(spec: dict[str, Any]) -> list[str]:
    argv = [
        "python",
        "-m",
        "app.cli.catforge_analyst",
        "competitor-set",
        "--project-id",
        PROJECT_ID,
        "--category-code",
        spec["category_code"],
        "--batch-id",
        spec["batch_id"],
        "--product-category",
        spec["product_category"],
        "--sku-code",
        spec["sku_code"],
        "--top-n",
        "3",
        "--answer-style",
        "xiaoao",
        "--with-report",
        "none",
        "--format",
        "json",
    ]
    assert "--limit" not in argv
    assert not any(token.startswith("--limit=") for token in argv)
    return argv


def _capture_one(
    args: argparse.Namespace,
    spec: dict[str, Any],
) -> dict[str, Any]:
    app_argv = _app_argv(spec)
    remote_argv = [
        "docker",
        "compose",
        "--project-directory",
        args.remote_project_dir,
        "exec",
        "-T",
        "api",
        *app_argv,
    ]
    print(f"capturing {spec['sku_code']} without --limit", file=sys.stderr)
    process = _run_remote(args, remote_argv)
    response = json.loads(process.stdout)
    fixture = capture(
        response,
        expected_sku_code=spec["sku_code"],
        expected_category_code=spec["category_code"],
        maximum_candidate_count=DEFAULT_LIMIT,
        minimum_candidate_count=1,
    )
    candidate_count = fixture["legacy_input"]["candidate_count"]
    if candidate_count != spec["candidate_count"]:
        raise RuntimeError(
            f"candidate count drift for {spec['sku_code']}: "
            f"{candidate_count} != {spec['candidate_count']}"
        )
    canonical_raw = _canonical_bytes(fixture)
    canonical_hash = _sha256(canonical_raw)
    if canonical_hash != spec["canonical_json_sha256"]:
        raise RuntimeError(
            f"canonical fixture drift for {spec['sku_code']}: "
            f"{canonical_hash} != {spec['canonical_json_sha256']}"
        )
    output = HERE / spec["fixture"]
    _write_deterministic_gzip(output, canonical_raw)
    top3 = [
        item["candidate"]["sku_code"]
        for item in fixture["legacy_analysis"]["top_competitors"]
    ]
    return {
        "fixture": output.name,
        "target_sku_code": spec["sku_code"],
        "category_code": spec["category_code"],
        "batch_id": spec["batch_id"],
        "application_argv": app_argv,
        "limit_argument_present": False,
        "default_candidate_limit": DEFAULT_LIMIT,
        "actual_candidate_count": candidate_count,
        "top3_sku_codes": top3,
        "source_stdout_sha256": _sha256(process.stdout),
        "canonical_json_sha256": canonical_hash,
        "canonical_json_bytes": len(canonical_raw),
        "gzip_sha256": _sha256(output.read_bytes()),
        "gzip_bytes": output.stat().st_size,
        "presentation_fields_removed": sorted(PRESENTATION_ONLY_KEYS),
    }


def _provenance(args: argparse.Namespace) -> dict[str, Any]:
    commit = _run_remote(
        args,
        ["git", "-C", args.remote_project_dir, "rev-parse", "HEAD"],
    ).stdout.decode("utf-8").strip()
    image_raw = _run_remote(
        args,
        [
            "docker",
            "compose",
            "--project-directory",
            args.remote_project_dir,
            "images",
            "--format",
            "json",
            "api",
        ],
    ).stdout
    images = json.loads(image_raw)
    if len(images) != 1:
        raise RuntimeError("expected exactly one API image in capture provenance")
    return {
        "remote_commit": commit,
        "remote_api_image": images[0]["ID"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ssh-key", type=Path, required=True)
    parser.add_argument("--host", default="deploy@123.56.42.205")
    parser.add_argument("--remote-project-dir", default="/opt/catforge")
    parser.add_argument(
        "--receipt-output",
        type=Path,
        default=HERE / "G28_legacy_capture_receipts.json",
    )
    args = parser.parse_args()
    if not args.ssh_key.is_file():
        raise ValueError("SSH key file does not exist")

    provenance = _provenance(args)
    entries = [_capture_one(args, spec) for spec in SPECS]
    receipt = {
        "receipt_version": "competitor_profile_v1_1_g28_capture_receipt_v1",
        "capture_date": "2026-07-15",
        "source_environment": "205-read-only",
        "transport": "ssh_batch_mode_to_existing_api_container",
        "remote_project_dir": args.remote_project_dir,
        **provenance,
        "database_write": False,
        "remote_file_write": False,
        "feishu_publish": False,
        "profile_write_flag_present": False,
        "all_application_argv_omit_limit": all(
            not item["limit_argument_present"] for item in entries
        ),
        "entries": entries,
    }
    unhashed = _canonical_bytes(receipt)
    receipt["receipt_hash"] = _sha256(unhashed)
    args.receipt_output.write_text(
        json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "captured",
                "receipt": args.receipt_output.name,
                "receipt_hash": receipt["receipt_hash"],
                "entry_count": len(entries),
                "all_application_argv_omit_limit": receipt[
                    "all_application_argv_omit_limit"
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
