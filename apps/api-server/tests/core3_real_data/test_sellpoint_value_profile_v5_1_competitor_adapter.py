from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    sellpoint_value_profile_v5_1_competitor_adapter as adapter_module,
)
from app.services.core3_real_data.analyst.competitor_profile_agent_snapshot_schemas import (
    AGENT_SNAPSHOT_METHOD_VERSION,
    AGENT_SNAPSHOT_RULE_VERSION,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorProfileAdapter,
    SellpointValueCompetitorReadRequest,
    SellpointValueCompetitorSourceIntegrityError,
)
from app.services.core3_real_data.constants import Core3CategoryCode


FACT_GROUPS = (
    "basis",
    "semantic_overlap",
    "parameter_claim_overlap",
    "sales_overlap",
    "target_purchase_reason_profile",
    "candidate_purchase_reason_profile",
    "anchor_substitutability",
    "value_anchor",
    "replacement_pressure",
    "purchase_pressure_comparison",
    "m12d_consumption",
    "purchase_pool",
    "weighted_overlap",
    "matched_dimensions",
    "market_validation",
    "selection_gate",
    "ranking_trace",
    "ranking_gate_reasons",
    "shared_business_context",
)


def _market(sku_code: str, rank: int) -> SimpleNamespace:
    return SimpleNamespace(
        sku_code=sku_code,
        brand_name=f"品牌{rank}",
        model_name=f"型号{rank}",
        size_tier="65",
        price_band_in_size_tier="mid",
        screen_size_inch=Decimal("65"),
        price_wavg=Decimal(5000 + rank),
        avg_weekly_sales_volume=Decimal(50 + rank),
        sales_volume_total=Decimal(1000 + rank),
        price_gap_to_target=Decimal(rank),
        price_gap_pct_to_target=Decimal(rank) / Decimal(100),
    )


def _analysis(sku_code: str, rank: int) -> SimpleNamespace:
    values: dict[str, Any] = {
        group: {"rank": rank, "group": group} for group in FACT_GROUPS
    }
    values["ranking_gate_reasons"] = ["saved_gate"]
    values["shared_business_context"] = ["客厅换新"]
    parameter_claim_overlap = {
        **values.pop("parameter_claim_overlap"),
        "parameter_overlap": {
            "target_items": [
                {
                    "code": "capacity_w",
                    "roles": ["core_picture", "param_value"],
                }
            ],
            "matched_items": [
                {
                    "code": "capacity_w",
                    "target_roles": ["core_picture", "param_value"],
                    "candidate_roles": ["core_gaming", "param_value"],
                }
            ],
        },
    }
    if rank != 2:
        values["param_claim_overlap"] = parameter_claim_overlap
    return SimpleNamespace(
        candidate=_market(sku_code, rank),
        role="primary_direct" if rank == 1 else "downtrade_diversion",
        role_cn="核心正面竞争" if rank == 1 else "价格下探分流",
        business_score=Decimal("0.90") - Decimal(rank) / Decimal(100),
        **values,
    )


def _candidate(
    rank: int,
    *,
    selected_rank: int | None = None,
) -> SimpleNamespace:
    sku_code = f"TV-C{rank}"
    return SimpleNamespace(
        candidate_sku_code=sku_code,
        candidate_snapshot_ref=f"snapshot-{sku_code}",
        candidate_snapshot_result_hash=f"snapshot-hash-{sku_code}",
        source_rank=rank,
        selected_rank=selected_rank,
        analysis=_analysis(sku_code, rank),
        result_hash=f"hash:pair:{rank}",
    )


def _full() -> SimpleNamespace:
    return SimpleNamespace(
        competitor_profile_version_id="cp-version-1",
        profile_version="cp-profile-r1",
        project_id="project-1",
        category_code="TV",
        release_scope_key="project-1:TV:agent",
        method_version=AGENT_SNAPSHOT_METHOD_VERSION,
        target=SimpleNamespace(
            sku_code="TV-TARGET",
            brand_name="海信",
            model_name="65E7Q",
            product_category="TV",
            size_tier="65",
            price_band_in_size_tier="mid",
            screen_size_inch=Decimal("65"),
            weighted_price=Decimal("6000"),
            avg_weekly_sales_volume=Decimal("45"),
            sales_volume_total=Decimal("900"),
        ),
        target_snapshot_ref="snapshot-TV-TARGET",
        target_snapshot_result_hash="snapshot-hash-TV-TARGET",
        candidates=[
            _candidate(2),
            _candidate(4, selected_rank=3),
            _candidate(1, selected_rank=2),
            _candidate(3, selected_rank=1),
        ],
        priority_order=["TV-C3", "TV-C1", "TV-C4"],
        result_hash="hash:profile:target",
    )


def _version(
    *,
    release_status: str = "published",
    is_current: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        competitor_profile_version_id="cp-version-1",
        project_id="project-1",
        category_code="TV",
        release_scope_key="project-1:TV:agent",
        profile_version="cp-profile-r1",
        schema_version=COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
        rule_version=AGENT_SNAPSHOT_RULE_VERSION,
        method_version=AGENT_SNAPSHOT_METHOD_VERSION,
        release_status=release_status,
        is_current=is_current,
        result_hash="hash:version:1",
    )


def _read(
    *,
    preview: bool = False,
    full: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        status="available",
        read_mode="full",
        preview=preview,
        competitor_profile_version_id="cp-version-1",
        full=full or _full(),
    )


class StrictSavedRepository:
    project_id = "project-1"
    category_code = Core3CategoryCode.TV

    def __init__(
        self,
        *,
        read: SimpleNamespace | None = None,
        version: SimpleNamespace | None = None,
    ) -> None:
        self.read_result = read or _read()
        self.version = version or _version()
        self.calls: list[tuple[str, Any]] = []
        self.fact_briefs: dict[str, dict[str, Any]] = {}

    def read_agent_profile_payload(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(("read_agent_profile_payload", kwargs))
        return self.read_result

    def get_version_by_id(self, version_id: str) -> SimpleNamespace:
        self.calls.append(("get_version_by_id", version_id))
        return self.version

    def read_agent_sku_fact_briefs(
        self,
        *,
        snapshot_result_hashes: dict[str, str],
    ) -> dict[str, dict[str, Any]]:
        self.calls.append(
            ("read_agent_sku_fact_briefs", snapshot_result_hashes)
        )
        return {
            snapshot_ref: self.fact_briefs.get(snapshot_ref, {})
            for snapshot_ref in snapshot_result_hashes
        }

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"adapter attempted a non-saved source: {name}")


def _request(**overrides: Any) -> SellpointValueCompetitorReadRequest:
    payload = {
        "project_id": "project-1",
        "category_code": "TV",
        "target_sku_code": "tv-target",
        "access_mode": "formal",
    }
    payload.update(overrides)
    return SellpointValueCompetitorReadRequest.model_validate(payload)


def test_formal_adapter_maps_all_saved_candidates_pair_facts_and_hashes() -> None:
    repository = StrictSavedRepository()
    result = SellpointValueCompetitorProfileAdapter(repository).read(_request())

    assert result.status == "available"
    assert result.source is not None
    source = result.source
    assert source.target_sku_code == "TV-TARGET"
    assert source.target_market.weighted_price == Decimal("6000")
    assert [row.candidate_sku_code for row in source.candidates] == [
        "TV-C1",
        "TV-C2",
        "TV-C3",
        "TV-C4",
    ]
    assert source.priority_order == ["TV-C3", "TV-C1", "TV-C4"]
    assert [row.selected_rank for row in source.candidates] == [2, None, 1, 3]
    assert source.source_version_result_hash == "hash:version:1"
    assert source.source_result_hash == "hash:profile:target"
    assert source.candidates[0].pair_result_hash == "hash:pair:1"
    assert source.candidates[0].pair_facts.value_anchor["rank"] == 1
    parameter_overlap = source.candidates[0].pair_facts.parameter_claim_overlap[
        "parameter_overlap"
    ]
    assert parameter_overlap["target_items"][0]["roles"] == [
        "core_picture",
        "param_value",
    ]
    assert "parameter_claim_overlap" in (
        source.candidates[1].pair_facts.unavailable_fact_groups
    )
    assert source.candidates[1].market.avg_weekly_sales_volume == Decimal("52")
    assert repository.calls == [
        (
            "read_agent_profile_payload",
            {
                "target_sku_code": "TV-TARGET",
                "access_mode": "formal",
                "competitor_profile_version_id": None,
                "release_scope_key": None,
            },
        ),
        ("get_version_by_id", "cp-version-1"),
        (
            "read_agent_sku_fact_briefs",
            {
                "snapshot-TV-C1": "snapshot-hash-TV-C1",
                "snapshot-TV-C2": "snapshot-hash-TV-C2",
                "snapshot-TV-C3": "snapshot-hash-TV-C3",
                "snapshot-TV-C4": "snapshot-hash-TV-C4",
                "snapshot-TV-TARGET": "snapshot-hash-TV-TARGET",
            },
        ),
    ]


def test_adapter_reads_typed_parameter_facts_once_and_reuses_snapshot_cache() -> None:
    repository = StrictSavedRepository()
    repository.fact_briefs = {
        snapshot_ref: {
            "sections": {
                "parameter_fact": {
                    "core_params": {
                        "picture": {
                            "mini_led_flag": {
                                "normalized_value": True,
                                "value_presence": "present",
                                "evidence_ids": [f"evidence-{snapshot_ref}"],
                            },
                            "quantum_dot_flag": {
                                "normalized_value": False,
                                "value_presence": "derived_false",
                            },
                        }
                    }
                }
            }
        }
        for snapshot_ref in (
            "snapshot-TV-TARGET",
            "snapshot-TV-C1",
            "snapshot-TV-C2",
            "snapshot-TV-C3",
            "snapshot-TV-C4",
        )
    }
    adapter = SellpointValueCompetitorProfileAdapter(repository)

    first = adapter.read(_request())
    second = adapter.read(_request())

    assert first.source is not None
    assert second.source is not None
    assert [
        (row.parameter_code, row.fact_status)
        for row in first.source.target_parameter_facts
    ] == [
        ("mini_led_flag", "known_present"),
        ("quantum_dot_flag", "known_absent"),
    ]
    assert first.source.candidates[0].parameter_facts[0].evidence_ids == [
        "evidence-snapshot-TV-C1"
    ]
    assert (
        [call[0] for call in repository.calls].count(
            "read_agent_sku_fact_briefs"
        )
        == 1
    )


def test_preview_is_explicitly_locked_to_one_non_current_draft() -> None:
    repository = StrictSavedRepository(
        read=_read(preview=True),
        version=_version(release_status="draft", is_current=False),
    )
    request = _request(
        access_mode="preview",
        release_scope_key="project-1:TV:agent",
        competitor_profile_version_id="cp-version-1",
    )

    result = SellpointValueCompetitorProfileAdapter(repository).read(request)

    assert result.source is not None
    assert result.source.access_mode == "preview"
    assert result.source.release_status == "draft"
    assert not result.source.is_current
    assert repository.calls[0][1]["competitor_profile_version_id"] == "cp-version-1"
    assert repository.calls[0][1]["release_scope_key"] == "project-1:TV:agent"


def test_adapter_category_contract_is_not_hardcoded_to_tv() -> None:
    full = _full()
    full.category_code = "AC"
    full.target.sku_code = "AC-TARGET"
    full.target.product_category = "AC"
    full.release_scope_key = "project-1:AC:agent"
    renamed: dict[str, str] = {}
    for row in full.candidates:
        candidate_sku_code = row.candidate_sku_code.replace("TV-", "AC-")
        renamed[row.candidate_sku_code] = candidate_sku_code
        row.candidate_sku_code = candidate_sku_code
        row.analysis.candidate.sku_code = candidate_sku_code
    full.priority_order = [renamed[code] for code in full.priority_order]
    version = _version()
    version.category_code = "AC"
    version.release_scope_key = "project-1:AC:agent"
    repository = StrictSavedRepository(read=_read(full=full), version=version)
    repository.category_code = Core3CategoryCode.AC

    result = SellpointValueCompetitorProfileAdapter(repository).read(
        _request(category_code="AC", target_sku_code="ac-target")
    )

    assert result.source is not None
    assert result.source.category_code == "AC"
    assert result.source.target_market.product_category == "AC"
    assert all(row.market.product_category == "AC" for row in result.source.candidates)
    parameter_overlap = result.source.candidates[
        0
    ].pair_facts.parameter_claim_overlap["parameter_overlap"]
    assert parameter_overlap["target_items"][0]["roles"] == ["param_value"]
    assert parameter_overlap["matched_items"][0]["target_roles"] == ["param_value"]
    assert parameter_overlap["matched_items"][0]["candidate_roles"] == [
        "param_value"
    ]


def test_unavailable_profile_is_explicit_and_does_not_read_version() -> None:
    repository = StrictSavedRepository(
        read=SimpleNamespace(
            status="profile_unavailable",
            read_mode="full",
            preview=False,
            competitor_profile_version_id=None,
            full=None,
        )
    )

    result = SellpointValueCompetitorProfileAdapter(repository).read(_request())

    assert result.status == "profile_unavailable"
    assert result.source is None
    assert [call[0] for call in repository.calls] == [
        "read_agent_profile_payload"
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {"competitor_profile_version_id": "cp-version-1"},
        {
            "access_mode": "preview",
            "competitor_profile_version_id": "cp-version-1",
        },
        {"access_mode": "preview", "release_scope_key": "project-1:TV:agent"},
    ],
)
def test_request_rejects_formal_version_selection_and_implicit_preview(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        _request(**payload)


@pytest.mark.parametrize(
    ("object_name", "field", "value", "message"),
    [
        ("version", "project_id", "project-2", "project or category"),
        ("full", "category_code", "AC", "project or category"),
        ("version", "method_version", "legacy", "agent snapshot v2"),
        ("full", "profile_version", "other-profile", "profile identity"),
        ("version", "release_status", "draft", "current published"),
        ("version", "result_hash", "", "result hashes"),
    ],
)
def test_integrity_mismatch_fails_instead_of_falling_back(
    object_name: str,
    field: str,
    value: Any,
    message: str,
) -> None:
    full = _full()
    version = _version()
    setattr(full if object_name == "full" else version, field, value)
    repository = StrictSavedRepository(read=_read(full=full), version=version)

    with pytest.raises(SellpointValueCompetitorSourceIntegrityError, match=message):
        SellpointValueCompetitorProfileAdapter(repository).read(_request())

    assert [call[0] for call in repository.calls] == [
        "read_agent_profile_payload",
        "get_version_by_id",
    ]


def test_adapter_import_graph_and_runtime_are_saved_profile_only() -> None:
    tree = ast.parse(Path(adapter_module.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        str(node.module) for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    forbidden = {
        "sellpoint_value_profile_candidate_service",
        "sellpoint_value_profile_candidate_repositories",
        "competitor_profile_candidate_recall",
        "competitor_profile_pair_feature",
        "competitor_answer",
    }
    assert not any(
        any(name.endswith(forbidden_name) for forbidden_name in forbidden)
        for name in imported
    )

    repository = StrictSavedRepository()
    SellpointValueCompetitorProfileAdapter(repository).read(_request())
    assert {call[0] for call in repository.calls} == {
        "read_agent_profile_payload",
        "get_version_by_id",
        "read_agent_sku_fact_briefs",
    }
