from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.core3_real_data.analyst.competitor_profile_materializer_schemas import (
    MaterializedCompetitorProfile,
    TargetMaterializationStatus,
)
from app.services.core3_real_data.analyst.competitor_profile_persistence_schemas import (
    CompetitorProfileVersionDraftCreate,
    CompetitorProfileVersionRecord,
)
from app.services.core3_real_data.analyst.competitor_profile_quality import (
    MANIFEST_HASH_VERSION,
    CompetitorProfileQualityError,
    CompetitorProfileQualityService,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    CompetitorProfileDraftBundle,
    ServingScope,
)
from app.services.core3_real_data.hash_utils import stable_hash
from tests.core3_real_data.test_competitor_profile_schemas import (
    _persistence_bundle,
    _scope,
)


def _draft_bundle(
    target_sku_code: str,
    candidate_sku_code: str,
    *,
    analysis_state: str = "ready",
) -> CompetitorProfileDraftBundle:
    persisted = _persistence_bundle().model_dump(mode="python")
    profile = persisted["profile"]["profile_payload"]
    pair = persisted["pairs"][0]["pair_payload"]
    selection = persisted["selections"][0]["selection_payload"]

    profile["target_sku_code"] = target_sku_code
    profile["result_hash"] = f"profile-result-{target_sku_code}"
    profile["key_competitor_summary"][0]["candidate_sku_code"] = candidate_sku_code
    pair["target_sku_code"] = target_sku_code
    pair["candidate"]["sku_code"] = candidate_sku_code
    pair["result_hash"] = f"pair-result-{target_sku_code}-{candidate_sku_code}"
    selection["target_sku_code"] = target_sku_code
    selection["candidate_sku_code"] = candidate_sku_code
    selection["result_hash"] = (
        f"selection-result-{target_sku_code}-{candidate_sku_code}"
    )

    if analysis_state == "partial":
        profile["analysis_state"] = "partial"
        profile["review_required"] = True
        profile["review_status"] = "review_required"
    elif analysis_state == "blocked":
        profile["analysis_state"] = "blocked"
        profile["conclusion_state"] = "insufficient_evidence"
        profile["competitive_advantages"] = []
        profile["review_required"] = True
        profile["review_status"] = "review_required"
        profile["no_conclusion_reason"] = {"reason_cn": "品类或上游版本冲突。"}
    return CompetitorProfileDraftBundle(
        profile=profile,
        pairs=[pair],
        selections=[selection],
    )


def _materialized(draft: CompetitorProfileDraftBundle) -> MaterializedCompetitorProfile:
    stage_hashes = {
        "candidate_pipeline": "candidate-stage",
        "pair_feature": "pair-stage",
        "purchase_pool": "pool-stage",
        "value_substitution": "value-stage",
        "price_volume_pressure": "market-stage",
        "relation_evaluation": "relation-stage",
        "key_selection": "selection-stage",
        "profile": draft.profile.result_hash,
    }
    payload = {
        "target_sku_code": draft.profile.target_sku_code,
        "product_category": draft.profile.category_code,
        "stage_result_hashes": stage_hashes,
        "config_version": "quality-test-v1",
        "input_fingerprint": f"input-{draft.profile.target_sku_code}",
    }
    return MaterializedCompetitorProfile(
        **payload,
        draft=draft,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_materializer_result_v1",
        ),
    )


def _serving_scope(codes: list[str]) -> ServingScope:
    payload = _scope("TV").model_dump(mode="python")
    payload["authoritative_sku_count"] = len(codes)
    payload["authoritative_sku_manifest_hash"] = stable_hash(
        sorted(codes),
        version=MANIFEST_HASH_VERSION,
    )
    return ServingScope(**payload)


def _version(
    codes: list[str],
    *,
    profile_version: str = "competitor-profile-quality-v1",
    processing_status: str = "completed",
    ready_count: int | None = None,
    partial_count: int = 0,
    blocked_count: int = 0,
    failed_count: int = 0,
    pair_count: int | None = None,
    relation_count: int | None = None,
    selection_count: int | None = None,
    scope: ServingScope | None = None,
) -> CompetitorProfileVersionRecord:
    normalized = sorted(codes)
    ready = len(codes) - partial_count - blocked_count - failed_count
    draft = CompetitorProfileVersionDraftCreate(
        project_id="project-tv",
        category_code="TV",
        product_category="TV",
        storage_batch_id="batch-2",
        release_scope_key="scope-tv",
        profile_version=profile_version,
        method_versions_json={"quality": "v1"},
        serving_scope=scope or _serving_scope(normalized),
        sku_count=len(codes),
        ready_count=ready if ready_count is None else ready_count,
        partial_count=partial_count,
        blocked_count=blocked_count,
        failed_count=failed_count,
        pair_count=(len(codes) - failed_count if pair_count is None else pair_count),
        relation_count=(
            (len(codes) - failed_count) * 7
            if relation_count is None
            else relation_count
        ),
        selection_count=(
            len(codes) - failed_count if selection_count is None else selection_count
        ),
        input_fingerprint=f"input-{profile_version}",
        candidate_universe_fingerprint=f"candidates-{profile_version}",
        result_hash=f"result-{profile_version}",
        processing_status=processing_status,
    )
    now = datetime.now(timezone.utc)
    return CompetitorProfileVersionRecord(
        **draft.model_dump(mode="python"),
        competitor_profile_version_id=f"id-{profile_version}",
        generated_at=now,
        created_at=now,
        updated_at=now,
    )


def test_ready_quality_consumes_g20_materialized_profiles_deterministically() -> None:
    codes = ["TV-T1", "TV-T2"]
    first = _materialized(_draft_bundle("TV-T1", "TV-C1"))
    second = _materialized(_draft_bundle("TV-T2", "TV-C2"))
    version = _version(codes)
    service = CompetitorProfileQualityService()
    before = version.model_dump(mode="python")

    assessment = service.assess_version(
        version=version,
        authoritative_sku_codes=list(reversed(codes)),
        profiles=[second, first],
    )
    repeated = service.assess_version(
        version=version,
        authoritative_sku_codes=codes,
        profiles=[first, second],
    )

    assert assessment.release_quality_status == "ready"
    assert assessment.review_required is False
    assert assessment.issues == []
    assert assessment.result_hash == repeated.result_hash
    assert version.model_dump(mode="python") == before


def test_partial_profile_produces_limited_quality_without_hiding_conclusions() -> None:
    codes = ["TV-T1", "TV-T2"]
    assessment = CompetitorProfileQualityService().assess_version(
        version=_version(codes, ready_count=1, partial_count=1),
        authoritative_sku_codes=codes,
        profiles=[
            _draft_bundle("TV-T1", "TV-C1"),
            _draft_bundle("TV-T2", "TV-C2", analysis_state="partial"),
        ],
    )

    assert assessment.release_quality_status == "limited"
    assert assessment.partial_count == 1
    assert {row.issue_code for row in assessment.issues} == {
        "partial_profile_present",
        "profile_review_required",
    }


def test_in_progress_missing_profile_stays_unassessed_not_blocked() -> None:
    codes = ["TV-T1", "TV-T2"]
    assessment = CompetitorProfileQualityService().assess_version(
        version=_version(
            codes,
            processing_status="running",
            ready_count=1,
            pair_count=1,
            relation_count=7,
            selection_count=1,
        ),
        authoritative_sku_codes=codes,
        profiles=[_draft_bundle("TV-T1", "TV-C1")],
    )

    assert assessment.release_quality_status == "unassessed"
    assert assessment.missing_sku_codes == ["TV-T2"]
    assert {row.issue_code for row in assessment.issues} == {"generation_incomplete"}


def test_completed_gap_and_generation_failure_block_release_quality() -> None:
    codes = ["TV-T1", "TV-T2"]
    failure = TargetMaterializationStatus(
        target_sku_code="TV-T2",
        status="failed",
        error_code="materialization_failed",
        error_message="该 SKU 画像生成失败。",
    )
    assessment = CompetitorProfileQualityService().assess_version(
        version=_version(
            codes,
            ready_count=1,
            failed_count=1,
            pair_count=1,
            relation_count=7,
            selection_count=1,
        ),
        authoritative_sku_codes=codes,
        profiles=[_draft_bundle("TV-T1", "TV-C1")],
        generation_failures=[failure],
    )

    assert assessment.release_quality_status == "blocked"
    assert assessment.failed_count == 1
    assert {
        "authoritative_profile_missing",
        "sku_generation_failed",
    }.issubset({row.issue_code for row in assessment.issues})


def test_manifest_conflict_and_cross_category_profile_are_p0_blockers() -> None:
    codes = ["AC-T1"]
    bad_scope_payload = _serving_scope(codes).model_dump(mode="python")
    bad_scope_payload["authoritative_sku_manifest_hash"] = "wrong-manifest"
    version = _version(codes, scope=ServingScope(**bad_scope_payload))
    raw = _draft_bundle("AC-T1", "AC-C1").model_dump(mode="python")
    raw["profile"]["category_code"] = "AC"
    raw["pairs"][0]["category_code"] = "AC"
    raw["pairs"][0]["candidate"]["product_category"] = "AC"
    profile = CompetitorProfileDraftBundle(**raw)

    assessment = CompetitorProfileQualityService().assess_version(
        version=version,
        authoritative_sku_codes=codes,
        profiles=[profile],
    )

    p0_codes = {row.issue_code for row in assessment.issues if row.severity == "P0"}
    assert assessment.release_quality_status == "blocked"
    assert {
        "authoritative_manifest_hash_mismatch",
        "cross_category_profile",
        "target_prefix_out_of_scope",
    }.issubset(p0_codes)


def test_materialized_hash_and_version_state_count_mismatch_are_blockers() -> None:
    codes = ["TV-T1"]
    materialized = _materialized(_draft_bundle("TV-T1", "TV-C1")).model_copy(
        update={"result_hash": "tampered-result-hash"}
    )
    assessment = CompetitorProfileQualityService().assess_version(
        version=_version(codes, ready_count=0),
        authoritative_sku_codes=codes,
        profiles=[materialized],
    )

    assert assessment.release_quality_status == "blocked"
    assert {
        "materialized_result_hash_mismatch",
        "ready_count_mismatch",
    }.issubset({row.issue_code for row in assessment.issues})


def test_quality_request_rejects_duplicate_manifest_and_non_failure_status() -> None:
    service = CompetitorProfileQualityService()
    version = _version(["TV-T1"])
    with pytest.raises(CompetitorProfileQualityError, match="duplicates"):
        service.assess_version(
            version=version,
            authoritative_sku_codes=["TV-T1", "TV-T1"],
            profiles=[],
        )
    with pytest.raises(CompetitorProfileQualityError, match="failed statuses"):
        service.assess_version(
            version=version,
            authoritative_sku_codes=["TV-T1"],
            profiles=[_draft_bundle("TV-T1", "TV-C1")],
            generation_failures=[
                TargetMaterializationStatus(
                    target_sku_code="TV-T1",
                    status="generated",
                    profile_result_hash="profile-result-TV-T1",
                )
            ],
        )


def test_freshness_current_stale_and_unknown_do_not_mutate_version() -> None:
    version = _version(["TV-T1"])
    service = CompetitorProfileQualityService()
    before = version.model_dump(mode="python")
    current = service.assess_freshness(
        version=version,
        current_serving_scope=version.serving_scope,
    )
    changed_authorities = dict(version.serving_scope.source_authorities)
    changed_authorities["M07"] = changed_authorities["M07"].model_copy(
        update={"result_hash": "m07-result-changed"}
    )
    changed_scope = version.serving_scope.model_copy(
        update={"source_authorities": changed_authorities}
    )
    stale = service.assess_freshness(
        version=version,
        current_serving_scope=changed_scope,
    )
    scope_stale = service.assess_freshness(
        version=version,
        current_serving_scope=version.serving_scope.model_copy(
            update={"market_window": "new-observed-window"}
        ),
    )
    unknown = service.assess_freshness(
        version=version,
        current_serving_scope=None,
    )

    assert current.freshness_status == "current"
    assert stale.freshness_status == "stale"
    assert stale.changed_authority_codes == ["M07"]
    assert scope_stale.freshness_status == "stale"
    assert scope_stale.changed_scope_fields == ["market_window"]
    assert unknown.freshness_status == "unknown"
    assert version.model_dump(mode="python") == before


def test_freshness_rejects_cross_category_scope() -> None:
    version = _version(["TV-T1"])
    with pytest.raises(
        CompetitorProfileQualityError, match="cross project or category"
    ):
        CompetitorProfileQualityService().assess_freshness(
            version=version,
            current_serving_scope=_scope("AC"),
        )
