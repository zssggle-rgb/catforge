from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from app.services.core3_real_data.analyst.analyst_repository import (
    build_sellpoint_value_v4_lineage_gate,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_service import (
    build_counterfactual_assessments,
    quantify_sellpoint_value,
)
from tests.core3_real_data.test_claim_value_pm_v4_context import _current_authority
from tests.core3_real_data.test_claim_value_pm_v4_counterfactual import (
    _base_context,
    _candidate,
    _picture_link,
    _set_target_size_and_tier,
    _with_candidates,
)
from tests.core3_real_data.test_claim_value_pm_v4_quantification import (
    _quantify,
    _synthetic_context,
)


def _manifest(repo_root: Path) -> dict:
    path = (
        repo_root
        / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G01_cohort_manifest.json"
    )
    artifact_manifest = json.loads(
        (
            path.parent / "G01_artifact_manifest.json"
        ).read_text(encoding="utf-8")
    )
    expected = next(
        item["sha256"]
        for item in artifact_manifest["artifacts"]
        if item["path"].endswith("G01_cohort_manifest.json")
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert all(
        re.fullmatch(r"[0-9a-f]{64}", item["input_manifest_sha256"])
        for item in payload["cohorts"]
    )
    return payload


def _cohort(repo_root: Path, cohort_id: str) -> dict:
    return next(
        item for item in _manifest(repo_root)["cohorts"]
        if item["cohort_id"] == cohort_id
    )


def test_c01_replays_frozen_picture_tier_candidate(repo_root: Path) -> None:
    frozen = _cohort(repo_root, "C01_IDENTIFIABLE_CANDIDATE_PICTURE_TIER")
    controlled = frozen["controlled_observed_features"]
    difference = frozen["value_tier_difference"]
    context = _set_target_size_and_tier(
        _base_context(),
        size=float(controlled["screen_size_inch"]),
        tier="base",
    )
    candidate = _candidate(
        context,
        sku_code=frozen["counterfactual_sku_codes"][0],
        role="stretch_benchmark",
        provenance="same_family_search",
        tier="premium",
        size=float(controlled["screen_size_inch"]),
        battlefield=controlled["primary_battlefield"],
        brightness=float(difference["counterfactual_brightness_nit"]),
        zones=int(difference["counterfactual_local_dimming_zones"]),
    )
    context = _with_candidates(context, [candidate])

    assessment = build_counterfactual_assessments(
        context,
        _picture_link(context),
    )[0]

    assert frozen["identification_status"] == "candidate_only"
    assert assessment.role == "stretch_benchmark"
    assert "Q5_MARKET_IMPLIED_WTP" not in assessment.eligible_quantification_levels
    assert frozen["wtp_allowed_now"] is False


def test_c02_replays_frozen_same_value_boundary(repo_root: Path) -> None:
    frozen = _cohort(repo_root, "C02_ONLY_SAME_VALUE")
    shared = frozen["shared_value"]
    context = _set_target_size_and_tier(
        _base_context(),
        size=float(shared["screen_size_inch"]),
        tier="premium",
    )
    candidate = _candidate(
        context,
        sku_code=frozen["counterfactual_sku_codes"][0],
        role="same_value",
        provenance="competitor_set_fallback",
        tier="premium",
        size=float(shared["screen_size_inch"]),
        battlefield=shared["primary_battlefield"],
    )
    context = _with_candidates(context, [candidate])
    link = _picture_link(context)
    assessments = build_counterfactual_assessments(context, link)
    result = quantify_sellpoint_value(context, link, assessments)

    assert frozen["identification_status"] == "same_value_only"
    assert assessments[0].role == "same_value"
    assert "same_value_only" in result.wtp.exclusion_reasons
    assert result.wtp.estimate_low is None


def test_c03_replays_frozen_bundle_only_boundary(repo_root: Path) -> None:
    frozen = _cohort(repo_root, "C03_FULL_COLLINEAR_SELLPOINTS")
    context = _base_context()
    candidates = [
        _candidate(
            context,
            sku_code=sku_code,
            role=role,
            provenance="competitor_set_fallback",
            tier=tier,
        )
        for sku_code, role, tier in zip(
            frozen["counterfactual_sku_codes"],
            ("base_value", "same_value", "stretch_benchmark"),
            ("base", "premium", "flagship"),
        )
    ]
    context = _with_candidates(context, candidates)
    link = _picture_link(context)
    result = quantify_sellpoint_value(
        context,
        link,
        build_counterfactual_assessments(context, link),
    )
    serialized = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)

    assert frozen["identification_status"] == "bundle_only"
    assert len(frozen["collinear_sellpoints"]) >= 2
    assert link.bundle.collinearity_group is not None
    assert link.bundle.independently_identifiable is False
    assert all(
        f"{member.capability_code}_wtp" not in serialized
        for member in link.bundle.members
    )


def test_c04_replays_frozen_single_week_boundary(repo_root: Path) -> None:
    frozen = _cohort(repo_root, "C04_NO_TEMPORAL_PRICE_VARIATION")
    result = _quantify(
        _synthetic_context(single_week=frozen["temporal_week_count"] == 1)
    )

    assert frozen["identification_status"] == "no_temporal_price_variation"
    assert result.choice_association is not None
    assert result.choice_association.status == "insufficient"
    assert result.wtp.estimate_low is None


def test_c05_replays_frozen_version_conflict(repo_root: Path) -> None:
    frozen = _cohort(repo_root, "C05_VERSION_FACT_CONFLICT")
    conflict = frozen["conflict"]
    modules = ("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D", "M12C")
    published = [_current_authority(module, "v1", f"hash-{module}") for module in modules]
    current = [item.model_copy(deep=True) for item in published]
    version_pairs = {
        "M03B": (
            conflict["published_m12d_m03b_source_version"],
            conflict["latest_m03b_source_version"],
        ),
        "M04C": (
            conflict["published_m12d_m04c_source_version"],
            conflict["latest_m04c_source_version"],
        ),
        "M12C": (
            conflict["published_m12d_m12c_source_version"],
            conflict["latest_m12c_source_version"],
        ),
    }
    for module, (published_version, current_version) in version_pairs.items():
        index = modules.index(module)
        published[index] = published[index].model_copy(
            update={"rule_version": published_version, "source_hash": f"published-{module}"}
        )
        current[index] = current[index].model_copy(
            update={"rule_version": current_version, "source_hash": f"current-{module}"}
        )

    gate = build_sellpoint_value_v4_lineage_gate(
        published_lineage=published,
        current_validation_lineage=current,
    )

    affected = {
        module
        for issue in gate.issues
        for module in issue.affected_module_codes
    }
    assert frozen["identification_status"] == "version_lineage_conflict"
    assert gate.status == "stale_conflict"
    assert {"M03B", "M04C", "M12C"} <= affected
