"""Opt-in bounded memory telemetry for V1.1 generation diagnostics."""

from __future__ import annotations

import os
import sys


def trace_competitor_profile_memory(stage: str) -> None:
    if os.getenv("CATFORGE_COMPETITOR_PROFILE_MEMORY_TRACE") != "1":
        return
    values: dict[str, str] = {}
    try:
        with open("/proc/self/status", encoding="utf-8") as handle:
            for line in handle:
                key, separator, value = line.partition(":")
                if separator and key in {"VmRSS", "VmHWM"}:
                    values[key] = value.strip()
    except OSError:
        values = {}
    print(
        "competitor_profile_v1_1_memory "
        f"stage={stage} rss={values.get('VmRSS', 'unknown')} "
        f"high_water={values.get('VmHWM', 'unknown')}",
        file=sys.stderr,
        flush=True,
    )


__all__ = ["trace_competitor_profile_memory"]
