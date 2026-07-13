from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.claim_value_pm_v5_answer import (
    adapt_v4_context_to_v5,
    build_perceived_value_market_report,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    PurchaseReasonSnapshot,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_candidate_service import (
    build_candidate_universe_manifest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_input_provider import (
    AnalystSellpointValueMaterializationInputProvider,
    SellpointValueProfileInputError,
    build_capability_investment_inputs,
    build_production_version_request,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_lifecycle import (
    SellpointValueProfileLifecycleService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_materializer_schemas import (
    REQUIRED_PROFILE_SOURCE_MODULES,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_threshold_config import (
    capability_threshold_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_thresholds import (
    classify_capability_investments,
)
from tests.core3_real_data.test_claim_value_pm_v4_quantification import (
    _synthetic_context,
)
from tests.core3_real_data.test_sellpoint_value_profile_persistence import (
    _create_dependencies,
    _create_profile_tables,
    _engine,
    _repository,
    _source_batch,
)


class _Repository:
    def __init__(self, sku_codes: list[str]) -> None:
        self.sku_codes = sku_codes
        self.calls: list[dict[str, Any]] = []

    def list_authoritative_sku_codes(self, **kwargs: Any) -> list[str]:
        self.calls.append(kwargs)
        return list(self.sku_codes)


class _Handlers:
    def __init__(self, *, candidate_payload: dict[str, Any], v4_payload: dict[str, Any]) -> None:
        self.candidate_payload = candidate_payload
        self.v4_payload = v4_payload
        self.candidate_calls: list[dict[str, Any]] = []
        self.v4_calls: list[dict[str, Any]] = []

    def sellpoint_value_candidate_universe(self, context, **kwargs: Any) -> dict[str, Any]:
        self.candidate_calls.append({"context": context, **kwargs})
        return self.candidate_payload

    def sellpoint_value_v4_context(self, context, **kwargs: Any) -> dict[str, Any]:
        self.v4_calls.append({"context": context, **kwargs})
        return self.v4_payload


def _candidate_record(sku_code: str) -> dict[str, Any]:
    return {
        "candidate_sku_code": sku_code,
        "candidate_brand_name": "测试品牌",
        "candidate_model_name": sku_code,
        "primary_relation_type": "scenario_substitute",
        "relation_types": ["scenario_substitute"],
        "recall_sources": ["M12"],
        "recall_strength": "strong",
        "recall_priority_score": 0.8,
        "pool_record_id": f"m12-record-{sku_code}",
        "pool_evidence_ids": [f"m12-evidence-{sku_code}"],
        "pool_result_hash": f"m12-{sku_code}",
        "component": {
            "component_total_score": 0.8,
            "processing_status": "success",
            "review_required": False,
            "record_id": f"m13-record-{sku_code}",
            "evidence_ids": [f"m13-evidence-{sku_code}"],
            "result_hash": f"m13-{sku_code}",
        },
        "roles": [],
        "feature": {
            "market_feature": {"price_wavg": 4000},
            "param_feature": {"known": True},
            "claim_value_overlap": {"known": True},
            "battlefield_overlap": {"known": True},
            "task_overlap": {},
            "audience_overlap": {},
            "record_id": f"feature-record-{sku_code}",
            "evidence_ids": [f"feature-evidence-{sku_code}"],
            "feature_snapshot_hash": f"feature-{sku_code}",
        },
        "selection": None,
    }


def _manifest():
    return build_candidate_universe_manifest(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        target_sku_code="TV00029112",
        candidate_records=[_candidate_record("BASE-1"), _candidate_record("BASE-2")],
    )


def _payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _manifest()
    v4 = _synthetic_context()
    return (
        {
            "status": "ok",
            "result": {"candidate_universe": manifest.model_dump(mode="json")},
        },
        {
            "status": "ok",
            "result": {
                "sellpoint_value_v4_context": v4.model_dump(mode="json")
            },
        },
    )


def _ac_payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    base = _synthetic_context()
    target_identity = base.target.model_copy(
        update={
            "sku_code": "AC000001",
            "brand_name": "海信",
            "model_name": "KFR-35",
            "product_category": "AC",
            "screen_size_inch": None,
            "size_tier": "wall_hp_1_5",
            "price_band": "mid",
        }
    )
    target_snapshot = base.target_snapshot.model_copy(
        update={"identity": target_identity, "market": {}}
    )
    candidates = [
        snapshot.model_copy(
            update={
                "identity": snapshot.identity.model_copy(
                    update={
                        "sku_code": f"ACBASE{index}",
                        "product_category": "AC",
                        "screen_size_inch": None,
                        "size_tier": "wall_hp_1_5",
                        "price_band": "mid",
                    }
                ),
                "market": {},
            }
        )
        for index, snapshot in enumerate(base.candidate_snapshots, start=1)
    ]
    v4 = base.model_copy(
        update={
            "project_id": "project-ac",
            "category_code": "AC",
            "requested_batch_id": "batch-ac",
            "serving_batch_ids": ["batch-ac"],
            "target": target_identity,
            "target_snapshot": target_snapshot,
            "purchase_reason_profile": PurchaseReasonSnapshot(
                found=False,
                lineage_status="unresolved",
                profile_version=None,
                anchors=[],
            ),
            "candidate_snapshots": candidates,
            "market_cells": [],
            "m12c_pool_tiers": [],
            "input_hash": "ac-v4-input-hash",
        }
    )
    manifest = build_candidate_universe_manifest(
        project_id="project-ac",
        category_code="AC",
        batch_id="batch-ac",
        target_sku_code="AC000001",
        candidate_records=[
            _candidate_record("ACBASE1"),
            _candidate_record("ACBASE2"),
        ],
    )
    return (
        {
            "status": "ok",
            "result": {"candidate_universe": manifest.model_dump(mode="json")},
        },
        {
            "status": "ok",
            "result": {
                "sellpoint_value_v4_context": v4.model_dump(mode="json")
            },
        },
    )


def test_production_request_fingerprints_complete_authoritative_scope() -> None:
    candidate_payload, v4_payload = _payloads()
    repository = _Repository(["TV00029113", "TV00029112", "TV00029112"])
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=repository,  # type: ignore[arg-type]
        atomic_handlers=_Handlers(  # type: ignore[arg-type]
            candidate_payload=candidate_payload,
            v4_payload=v4_payload,
        ),
    )

    first = build_production_version_request(
        provider=provider,
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        profile_version="spv-v1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
    )
    second = build_production_version_request(
        provider=provider,
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        profile_version="spv-v1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
    )

    assert first == second
    assert first.source_scope["authoritative_sku_count"] == 2
    assert first.version_input_fingerprint != "pending"
    assert first.candidate_universe_fingerprint != "pending"
    assert first.version_result_hash != "pending"
    assert repository.calls[0] == {
        "batch_id": "batch-1",
        "product_category": "TV",
        "market_window": "full_observed_window",
    }


def test_production_request_separates_persistence_anchor_from_composite_source_scope() -> None:
    candidate_payload, v4_payload = _payloads()
    repository = _Repository(["TV00029112"])
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=repository,  # type: ignore[arg-type]
        atomic_handlers=_Handlers(  # type: ignore[arg-type]
            candidate_payload=candidate_payload,
            v4_payload=v4_payload,
        ),
    )

    request = build_production_version_request(
        provider=provider,
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        source_batch_scope_id="serving-scope:TV:batch-1,batch-older",
        profile_version="spv-v1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
    )

    assert request.batch_id == "batch-1"
    assert request.source_scope["source_batch_scope_id"] == (
        "serving-scope:TV:batch-1,batch-older"
    )
    assert request.source_scope["source_batch_ids"] == ["batch-1", "batch-older"]
    assert repository.calls[0]["batch_id"] == (
        "serving-scope:TV:batch-1,batch-older"
    )


def test_provider_composes_existing_atoms_without_llm_or_report_recompute_reads() -> None:
    candidate_payload, v4_payload = _payloads()
    repository = _Repository(["TV00029112"])
    handlers = _Handlers(
        candidate_payload=candidate_payload,
        v4_payload=v4_payload,
    )
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=repository,  # type: ignore[arg-type]
        atomic_handlers=handlers,  # type: ignore[arg-type]
    )
    request = build_production_version_request(
        provider=provider,
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        profile_version="spv-v1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
        m12d_profile_version="m12d-published-v2",
    )

    source = provider.load_materialization_input(request, "TV00029112")

    assert source.target.sku_code == "TV00029112"
    assert source.candidate_universe.candidate_manifest_hash == (
        _manifest().candidate_manifest_hash
    )
    assert source.v5_report.result_hash
    assert source.investment_decisions
    assert all(
        "_claim_" not in row.capability_name_cn
        and not row.capability_name_cn.startswith(("tv_", "ac_"))
        for row in source.investment_decisions
    )
    assert {row.module_code for row in source.source_lineage} == set(
        REQUIRED_PROFILE_SOURCE_MODULES
    )
    lineage = {row.module_code: row for row in source.source_lineage}
    assert lineage["M12"].status == "present"
    assert lineage["M13"].status == "present"
    assert lineage["M12"].record_ids == [
        "m12-record-BASE-1",
        "m12-record-BASE-2",
    ]
    assert lineage["M14"].status == "missing"
    assert source.current_source_hashes == {
        row.module_code: row.result_hashes
        for row in source.source_lineage
        if row.status == "present"
    }
    assert handlers.v4_calls[0]["m12d_profile_version"] == "m12d-published-v2"


def test_capability_inputs_include_value_capability_and_grounded_claims() -> None:
    v4 = _synthetic_context()
    report = build_perceived_value_market_report(adapt_v4_context_to_v5(v4))

    inputs = build_capability_investment_inputs(
        v4_context=v4,
        report_rows=report.value_account_rows,
        candidate_universe=_manifest(),
    )
    by_code = {row.capability_code: row for row in inputs}

    assert "tv_bright_room_dark_detail" in by_code
    assert "tv_claim_hdr_high_brightness" in by_code
    assert by_code["tv_claim_hdr_high_brightness"].capability_name_cn == "高亮度 HDR"
    assert by_code["tv_claim_hdr_high_brightness"].target_fact_status == "known_present"
    assert {
        row.candidate_sku_code
        for row in by_code["tv_claim_hdr_high_brightness"].candidate_facts
    } == {"BASE-1", "BASE-2"}


def test_production_capability_assembly_filters_common_claim_as_table_stake() -> None:
    base = _synthetic_context()
    target_identity = base.target.model_copy(update={"price_band": "premium"})
    target_snapshot = base.target_snapshot.model_copy(
        update={"identity": target_identity}
    )
    candidates = [
        base.candidate_snapshots[0].model_copy(
            update={
                "identity": base.candidate_snapshots[0].identity.model_copy(
                    update={"sku_code": f"BASE-{index}", "price_band": "premium"}
                )
            }
        )
        for index in range(1, 6)
    ]
    v4 = base.model_copy(
        update={
            "target": target_identity,
            "target_snapshot": target_snapshot,
            "candidate_snapshots": candidates,
        }
    )
    manifest = build_candidate_universe_manifest(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        target_sku_code="TV00029112",
        candidate_records=[
            _candidate_record(f"BASE-{index}") for index in range(1, 6)
        ],
    )
    report = build_perceived_value_market_report(
        adapt_v4_context_to_v5(v4, candidate_universe=manifest)
    )
    inputs = build_capability_investment_inputs(
        v4_context=v4,
        report_rows=report.value_account_rows,
        candidate_universe=manifest,
    )

    decisions = classify_capability_investments(
        inputs,
        configs={"TV": capability_threshold_config("TV")},
    )
    by_code = {row.capability_code: row for row in decisions}

    assert by_code["tv_claim_hdr_high_brightness"].classification == "table_stake"
    assert by_code["tv_claim_hdr_high_brightness"].business_reason_cn.startswith(
        "该能力在当前竞争范围内已是普遍配置"
    )


@pytest.mark.parametrize(
    ("target_volume", "expected_classification"),
    [(50.0, "missing_competitive_gap"), (150.0, "do_not_follow")],
)
def test_production_gap_assembly_uses_current_volume_performance_for_pm_action(
    target_volume: float,
    expected_classification: str,
) -> None:
    base = _synthetic_context()
    target_claim_fact = dict(base.target_snapshot.facts["claim_fact"])
    target_claim_fact["fact_claim_codes"] = [
        code
        for code in target_claim_fact["fact_claim_codes"]
        if code != "tv_claim_high_refresh_rate"
    ]
    target_facts = {**base.target_snapshot.facts, "claim_fact": target_claim_fact}
    target_identity = base.target.model_copy(update={"price_band": "premium"})
    target_snapshot = base.target_snapshot.model_copy(
        update={
            "identity": target_identity,
            "facts": target_facts,
            "market": {
                "market_metrics": {
                    "price_wavg": 5000.0,
                    "avg_weekly_sales_volume": target_volume,
                }
            },
        }
    )
    candidates = [
        base.candidate_snapshots[0].model_copy(
            update={
                "identity": base.candidate_snapshots[0].identity.model_copy(
                    update={"sku_code": f"BASE-{index}", "price_band": "premium"}
                ),
                "market": {
                    "market_metrics": {
                        "price_wavg": 5000.0,
                        "avg_weekly_sales_volume": 100.0,
                    }
                },
            }
        )
        for index in range(1, 6)
    ]
    v4 = base.model_copy(
        update={
            "target": target_identity,
            "target_snapshot": target_snapshot,
            "candidate_snapshots": candidates,
        }
    )
    manifest = build_candidate_universe_manifest(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        target_sku_code="TV00029112",
        candidate_records=[
            _candidate_record(f"BASE-{index}") for index in range(1, 6)
        ],
    )
    report = build_perceived_value_market_report(
        adapt_v4_context_to_v5(v4, candidate_universe=manifest)
    )
    inputs = build_capability_investment_inputs(
        v4_context=v4,
        report_rows=report.value_account_rows,
        candidate_universe=manifest,
    )
    decisions = classify_capability_investments(
        inputs,
        configs={"TV": capability_threshold_config("TV")},
    )
    by_code = {row.capability_code: row for row in decisions}

    assert by_code["tv_claim_high_refresh_rate"].classification == (
        expected_classification
    )


def test_provider_rejects_failed_atom_instead_of_persisting_partial_input() -> None:
    _, v4_payload = _payloads()
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=_Repository(["TV00029112"]),  # type: ignore[arg-type]
        atomic_handlers=_Handlers(  # type: ignore[arg-type]
            candidate_payload={"status": "not_found", "limitations": ["missing"]},
            v4_payload=v4_payload,
        ),
    )
    request = build_production_version_request(
        provider=provider,
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        profile_version="spv-v1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
    )

    with pytest.raises(SellpointValueProfileInputError, match="candidate-universe"):
        provider.load_materialization_input(request, "TV00029112")


def test_production_provider_supports_ac_without_tv_specific_fallbacks() -> None:
    candidate_payload, v4_payload = _ac_payloads()
    provider = AnalystSellpointValueMaterializationInputProvider(
        repository=_Repository(["AC000001"]),  # type: ignore[arg-type]
        atomic_handlers=_Handlers(  # type: ignore[arg-type]
            candidate_payload=candidate_payload,
            v4_payload=v4_payload,
        ),
    )
    request = build_production_version_request(
        provider=provider,
        project_id="project-ac",
        category_code="AC",
        batch_id="batch-ac",
        profile_version="spv-ac-v1",
        product_category="AC",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
        generated_by="test",
    )

    source = provider.load_materialization_input(request, "AC000001")

    assert source.category_code == "AC"
    assert source.target.product_category == "AC"
    assert source.target.sku_code == "AC000001"
    assert source.threshold_config.category_code == "AC"
    assert source.v5_report.analysis_state == "blocked"


def test_production_provider_runs_through_draft_lifecycle_and_batch_resume() -> None:
    engine = _engine()
    with engine.begin() as connection:
        _create_dependencies(connection)
        _create_profile_tables(connection)
    db = Session(engine, autoflush=False, future=True)
    try:
        db.add_all(
            [
                entities.CategoryProject(
                    project_id="project-1",
                    name="TV project",
                    category_code="TV",
                ),
                _source_batch("batch-1", "project-1", "TV"),
            ]
        )
        db.commit()
        candidate_payload, v4_payload = _payloads()
        provider = AnalystSellpointValueMaterializationInputProvider(
            repository=_Repository(["TV00029112"]),  # type: ignore[arg-type]
            atomic_handlers=_Handlers(  # type: ignore[arg-type]
                candidate_payload=candidate_payload,
                v4_payload=v4_payload,
            ),
        )
        request = build_production_version_request(
            provider=provider,
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            profile_version="spv-production-v1",
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="fact_complete_with_comment",
            generated_by="test",
        )
        lifecycle = SellpointValueProfileLifecycleService(
            repository=_repository(db, project_id="project-1", category_code="TV"),
            input_provider=provider,
        )

        readback = lifecycle.generate_draft(request, sku_code="TV00029112")
        resumed = lifecycle.batch_generate(request, resume_unfinished_only=True)

        assert readback.persisted.profile.result_hash == readback.profile.result_hash
        assert resumed.requested_sku_count == 1
        assert resumed.skipped_count == 1
        assert resumed.generated_count == 0
        assert resumed.statuses[0].sku_code == "TV00029112"
        assert resumed.statuses[0].status == "skipped"
    finally:
        db.close()
        engine.dispose()
