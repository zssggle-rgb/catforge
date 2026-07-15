#!/usr/bin/env python3
"""Validate JSON from stdin and persist it as deterministic gzip JSON."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    value = json.load(sys.stdin)
    raw = _canonical_bytes(value)
    with args.output.open("wb") as binary_handle:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=binary_handle,
            mtime=0,
        ) as gzip_handle:
            gzip_handle.write(raw)
    receipt = {
        "status": "stored",
        "output": args.output.name,
        "canonical_json_bytes": len(raw),
        "canonical_json_sha256": hashlib.sha256(raw).hexdigest(),
        "gzip_bytes": args.output.stat().st_size,
    }
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
