from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import event

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.analyst.analyst_repository import (
    AnalystRepository,
    _v4_candidate_references,
    _v4_multirow_authority,
    _v4_current_m12d_input_lineage,
    _v4_pick_rows_by_key,
    _v4_published_lineage,
    _v4_select_snapshot_candidates,
    _v4_trim_market_weekly_rows,
    build_sellpoint_value_v4_lineage_gate,
)
from app.services.core3_real_data.analyst.analyst_schemas import ResolvedSku
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    EvidenceRef,
    SourceAuthority,
)
from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    FixturePurchaseReasonProfileReader,
    PurchaseReasonProfileLookupKey,
    default_m12d_contract_fixture_path,
)
from app.services.core3_real_data.constants import (
    CORE3_M03B_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M12C_RULE_VERSION,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import M12DSourceRef


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
BATCH_ID = "m00_20260623014631_c8630747"
M12D_VERSION = "m12d_tv_purchase_reason_profile_v0_1_draft"


def _target() -> ResolvedSku:
    return ResolvedSku(
        sku_code="TV00029112",
        brand_name="海信",
        model_name="65E7Q",
        product_category="TV",
        size_tier="size_65_75",
        price_band_in_size_tier="premium",
        screen_size_inch=Decimal("65"),
        source="fixture",
    )


def test_context_loader_is_read_only_bounded_and_keeps_fallback_provenance(
    client,
) -> None:
    session = SessionLocal()
    statements: list[str] = []
    pending_profile = entities.Core3SkuMarketProfile(
        project_id="g08-pending-probe",
        category_code="TV",
        batch_id="g08-pending-batch",
        sku_code="TVG08PENDING",
        brand_name="probe",
        model_name="probe",
        analysis_window="full_observed_window",
        screen_size_inch=Decimal("65"),
        size_segment="size_65_75",
        price_band_size="premium",
        active_week_count=1,
        market_row_count=1,
        platform_count=1,
        promotion_suspect_flag=False,
        input_fingerprint="g08-pending",
        result_hash="g08-pending",
        rule_version=CORE3_M07_RULE_VERSION,
        is_current=True,
    )
    session.add(pending_profile)

    def capture_statement(
        _conn, _cursor, statement, _parameters, _context, _executemany
    ) -> None:
        statements.append(statement.strip())

    event.listen(session.bind, "before_cursor_execute", capture_statement)
    try:
        repository = AnalystRepository(
            session, project_id=PROJECT_ID, category_code="TV"
        )
        context = repository.sellpoint_value_v4_context(
            batch_id=BATCH_ID,
            sku=_target(),
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="claim_value_ready_with_comment",
            fallback_candidates=[
                {
                    "candidate": {
                        "sku_code": "TV00029020",
                        "brand_name": "小米",
                        "model_name": "L65MC-SP",
                    },
                    "competitor_role": "same_value",
                }
            ],
        )
        single_candidate_query_count = len(statements)
        statements.clear()
        multi_candidate_context = repository.sellpoint_value_v4_context(
            batch_id=BATCH_ID,
            sku=_target(),
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="claim_value_ready_with_comment",
            fallback_candidates=[
                {
                    "candidate": {
                        "sku_code": f"TV-CANDIDATE-{index:03d}",
                        "model_name": f"候选型号{index}",
                    }
                }
                for index in range(35)
            ],
        )
        multi_candidate_query_count = len(statements)
        pending_remained_unflushed = pending_profile in session.new
    finally:
        event.remove(session.bind, "before_cursor_execute", capture_statement)
        session.close()

    sql_verbs = [
        statement.split(None, 1)[0].upper() for statement in statements if statement
    ]
    assert single_candidate_query_count <= 30
    assert multi_candidate_query_count <= 30
    assert multi_candidate_query_count == single_candidate_query_count
    assert set(sql_verbs) <= {"SELECT", "PRAGMA"}
    assert not {"INSERT", "UPDATE", "DELETE"} & set(sql_verbs)
    assert pending_remained_unflushed is True
    assert context.target.sku_code == "TV00029112"
    assert context.target_snapshot.identity.model_name == "65E7Q"
    assert context.lineage_gate.status == "unresolved"
    assert context.purchase_reason_profile.found is False
    assert context.candidate_snapshots[0].identity.sku_code == "TV00029020"
    assert (
        context.candidate_snapshots[0].facts["candidate_source"]["provenance"]
        == "competitor_set_fallback"
    )
    m14 = next(item for item in context.authority_manifest if item.module_code == "M14")
    assert m14.authority_mode == "fallback"
    assert "fallback_provenance_not_m14" in m14.warnings
    assert context.market_cells == []
    assert context.m12c_pool_tiers == []
    assert context.input_hash
    assert len(multi_candidate_context.candidate_snapshots) == 35


def test_target_only_m12d_lineage_keeps_composite_semantic_scope() -> None:
    context = SimpleNamespace(
        source_refs_json=[
            M12DSourceRef(
                module_code="M09C_M10C_M11C",
                table_name="core3_m09c_sku_user_task_profile",
                record_id="task-1",
                result_hash="task-hash",
                extra={"rule_version": "m09-v1", "taxonomy_version": "task-v1"},
            ),
            M12DSourceRef(
                module_code="M09C_M10C_M11C",
                table_name="core3_m11c_sku_value_battlefield_profile",
                record_id="battlefield-1",
                result_hash="battlefield-hash",
                extra={"rule_version": "m11-v1", "taxonomy_version": "battlefield-v1"},
            ),
        ]
    )

    lineage = _v4_current_m12d_input_lineage(
        context,
        requested_batch_id="serving-scope:TV:batch-current,batch-fallback",
    )
    by_module = {item.module_code: item for item in lineage}

    semantic = by_module["M09C_M10C_M11C"]
    assert semantic.row_count == 2
    assert semantic.source_hash
    assert semantic.selected_batch_ids == ["batch-current", "batch-fallback"]
    assert "multiple_current_rule_versions" in semantic.warnings
    assert by_module["M12C"].availability == "missing"


def test_65e7q_fixture_detects_published_vs_current_lineage_conflict(
    repo_root: Path,
) -> None:
    fixture = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G01_65E7Q_fixture.json"
        ).read_text(encoding="utf-8")
    )
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )
    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            m12d_profile_version=M12D_VERSION,
            sku_code="TV00029112",
        )
    )
    current_versions = fixture["source_versions"]
    current_hashes = fixture["aggregate_source_hashes"]["TV00029112"]
    current = [
        _current_authority(
            module,
            current_versions[module],
            current_hashes.get(module, f"fixture-current-{module.lower()}"),
        )
        for module in (
            "M03B",
            "M04C",
            "M05C",
            "M07",
            "M09C",
            "M10C",
            "M11C",
            "M11D",
            "M12C",
        )
    ]

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=_v4_published_lineage(contract),
        current_validation_lineage=current,
    )

    assert contract.found is True
    assert contract.consumption_state == "published_degraded"
    assert result.status == "stale_conflict"
    conflict_modules = {
        module
        for issue in result.issues
        if issue.code == "version_lineage_conflict"
        for module in issue.affected_module_codes
    }
    assert {"M03B", "M04C", "M05C", "M12C"} <= conflict_modules


def test_same_version_and_batch_with_changed_hash_is_blocked() -> None:
    published = [
        _current_authority(module, "v1", f"published-{module}")
        for module in (
            "M03B",
            "M04C",
            "M05C",
            "M07",
            "M09C",
            "M10C",
            "M11C",
            "M11D",
            "M12C",
        )
    ]
    current = [item.model_copy(deep=True) for item in published]
    current[0] = current[0].model_copy(update={"source_hash": "current-M03B"})

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=published,
        current_validation_lineage=current,
    )

    assert result.status == "stale_conflict"
    assert result.issues[0].affected_module_codes == ["M03B"]


def test_authority_hash_is_independent_of_database_row_order() -> None:
    refs = [
        EvidenceRef(
            module_code="M11D",
            record_type="allocation",
            record_id=record_id,
            result_hash=f"hash-{record_id}",
            batch_id=BATCH_ID,
        )
        for record_id in ("b", "a", "c")
    ]

    first = _v4_multirow_authority(
        module_code="M11D",
        table_name="allocation",
        rule_version="v1",
        rows=[],
        refs=refs,
        ambiguous_keys=set(),
    )
    second = _v4_multirow_authority(
        module_code="M11D",
        table_name="allocation",
        rule_version="v1",
        rows=[],
        refs=list(reversed(refs)),
        ambiguous_keys=set(),
    )

    assert first.source_hash == second.source_hash


def test_snapshot_selection_preserves_declared_roles_beyond_top_three() -> None:
    candidates = [
        {
            "sku_code": f"TV{i}",
            "slot_code": "same_value" if i <= 3 else "base_value",
        }
        for i in range(1, 8)
    ]

    selected = _v4_select_snapshot_candidates(candidates, limit=4)

    assert len(selected) == 4
    assert any(item["sku_code"] == "TV4" for item in selected)
    assert {item["slot_code"] for item in selected} == {"same_value", "base_value"}


def test_m14_labels_authoritative_candidates_but_cannot_expand_them() -> None:
    def selection(sku_code: str, rank: int) -> SimpleNamespace:
        return SimpleNamespace(
            candidate_sku_code=sku_code,
            candidate_brand_name="品牌",
            candidate_model_name=sku_code,
            selection_rank=rank,
            slot_code="same_value",
            confidence=Decimal("0.9"),
            competitor_selection_id=f"selection-{rank}",
            result_hash=f"selection-hash-{rank}",
            batch_id=BATCH_ID,
            rule_version="m14-v1",
            evidence_ids=[],
        )

    candidates = _v4_candidate_references(
        target_sku_code="TV-TARGET",
        selection_rows=[selection("TV-M12-1", 1), selection("TV-M14-ONLY", 2)],
        fallback_candidates=[
            {
                "candidate": {"sku_code": "TV-M12-1"},
                "candidate_source": "M12_M13_candidate_universe",
                "competitor_role": "direct_fight",
            }
        ],
    )

    assert [item["sku_code"] for item in candidates] == ["TV-M12-1"]
    assert candidates[0]["slot_code"] == "same_value"
    assert candidates[0]["provenance"] == "M12_M13_candidate_universe"
    assert candidates[0]["source_refs"][0].module_code == "M14"


def test_market_row_budget_keeps_complete_groups_and_reports_truncation() -> None:
    rows = [
        SimpleNamespace(
            period_week_index=week,
            platform_type="jd",
            channel_type="online",
            sku_code=f"TV{sku}",
            source_row_id=f"{week}-{sku}",
        )
        for week in range(1, 1001)
        for sku in range(2)
    ]
    rows.append(
        SimpleNamespace(
            period_week_index=0,
            platform_type="jd",
            channel_type="online",
            sku_code="TV0",
            source_row_id="boundary-partial",
        )
    )

    selected, truncated = _v4_trim_market_weekly_rows(rows, limit=2000)

    assert truncated is True
    assert len(selected) == 2000
    assert {row.period_week_index for row in selected} == set(range(1, 1001))
    assert all(row.source_row_id != "boundary-partial" for row in selected)


def test_context_replays_selected_profiles_and_market_cells_deterministically(
    client, repo_root: Path
) -> None:
    session = SessionLocal()
    try:
        session.add_all(
            [
                entities.Core3SkuParamProfile(
                    project_id=PROJECT_ID,
                    category_code="TV",
                    batch_id=BATCH_ID,
                    sku_code="TV00029112",
                    model_name="65E7Q",
                    param_values_json={
                        "dimension_tier_profile": {"size": "size_65_75"}
                    },
                    core_picture_params_json={
                        "mini_led_flag": {"normalized_value": True},
                        "declared_brightness_nit_or_band": {
                            "normalized_value": {"value": 5200}
                        },
                    },
                    conflict_count=0,
                    profile_hash="current-m03b-hash",
                    seed_version="tv-seed-v1",
                    rule_version=CORE3_M03B_RULE_VERSION,
                ),
                entities.Core3SkuMarketProfile(
                    project_id=PROJECT_ID,
                    category_code="TV",
                    batch_id=BATCH_ID,
                    sku_code="TV00029112",
                    brand_name="海信",
                    model_name="65E7Q",
                    analysis_window="full_observed_window",
                    screen_size_inch=Decimal("65"),
                    size_segment="size_65_75",
                    price_band_size="premium",
                    active_week_count=1,
                    market_row_count=1,
                    platform_count=1,
                    promotion_suspect_flag=True,
                    input_fingerprint="m07-input",
                    result_hash="current-m07-hash",
                    rule_version=CORE3_M07_RULE_VERSION,
                    is_current=True,
                ),
                entities.Core3CleanMarketWeekly(
                    clean_market_id="weekly-65e7q-1",
                    project_id=PROJECT_ID,
                    category_code="TV",
                    batch_id=BATCH_ID,
                    source_table="week_sales_data",
                    source_pk="weekly-source-1",
                    source_row_id="weekly-source-1",
                    source_operation_type="UPSERT",
                    sku_code="TV00029112",
                    model_name="65E7Q",
                    brand_name="海信",
                    period_raw="2026-W01",
                    period_week_index=202601,
                    period_parse_status="parsed",
                    platform_type="jd",
                    sales_volume=Decimal("100"),
                    sales_amount=Decimal("500000"),
                    avg_price=Decimal("5000"),
                    price_check_status="ok",
                    clean_record_key="weekly-key-1",
                    clean_hash="weekly-hash-1",
                    clean_version="m01-clean-v1",
                    hash_version="sha256-v1",
                    record_status="active",
                    quality_status="ok",
                ),
            ]
        )
        session.commit()
        reader = FixturePurchaseReasonProfileReader.from_path(
            repo_root / default_m12d_contract_fixture_path()
        )
        repository = AnalystRepository(
            session, project_id=PROJECT_ID, category_code="TV"
        )

        by_sku = repository.resolve_sku(
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            sku_code="TV00029112",
        )
        by_model = repository.resolve_sku(
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
            model_name="65E7Q",
        )
        authoritative_sku_codes = repository.list_authoritative_sku_codes(
            batch_id=BATCH_ID,
            product_category="TV",
            market_window="full_observed_window",
        )

        first = repository.sellpoint_value_v4_context(
            batch_id=BATCH_ID,
            sku=_target(),
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="claim_value_ready_with_comment",
            m12d_profile_version=M12D_VERSION,
            purchase_reason_reader=reader,
        )
        second = repository.sellpoint_value_v4_context(
            batch_id=BATCH_ID,
            sku=_target(),
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="claim_value_ready_with_comment",
            m12d_profile_version=M12D_VERSION,
            purchase_reason_reader=reader,
        )
    finally:
        session.close()

    authority = {item.module_code: item for item in first.authority_manifest}
    assert authority["M03B"].availability == "present"
    assert authority["M03B"].rule_version == CORE3_M03B_RULE_VERSION
    assert authority["M07"].availability == "present"
    assert first.target_snapshot.source_status["M03B"].usability == "usable"
    assert first.target_snapshot.source_status["M04C"].availability == "missing"
    assert (
        first.target_snapshot.facts["parameter_fact"]["summary"]["conflict_count"] == 0
    )
    assert len(first.market_cells) == 1
    assert first.market_cells[0].promotion_suspect is True
    assert first.market_cells[0].inventory_status == "unavailable"
    assert first.purchase_reason_profile.found is True
    assert first.lineage_gate.status == "stale_conflict"
    assert first.input_hash == second.input_hash
    assert first.target_snapshot.snapshot_hash == second.target_snapshot.snapshot_hash
    assert [item.sku_code for item in by_sku] == ["TV00029112"]
    assert [item.sku_code for item in by_model] == ["TV00029112"]
    assert authoritative_sku_codes == ["TV00029112"]


def test_m12c_adapter_reads_pool_and_numeric_tier_but_not_legacy_amounts(
    client,
) -> None:
    session = SessionLocal()
    try:
        session.add(
            entities.Core3ClaimValueContextPool(
                pool_id="pool-brightness",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                product_category="TV",
                market_window="full_observed_window",
                analysis_population="claim_value_ready_with_comment",
                claim_code="tv_claim_hdr_high_brightness",
                claim_name="高亮度",
                context_type="value_battlefield",
                context_code="BF_PREMIUM_PICTURE_UPGRADE",
                context_name="高端画质升级战场",
                size_tier="size_65_75",
                price_band_group="premium",
                pool_sku_count=10,
                with_claim_sku_count=4,
                without_claim_sku_count=5,
                unknown_claim_sku_count=1,
                sample_status="sufficient",
                quality_flags_json=[
                    "comparison_basis:numeric_param_tier",
                    "comparison_param:declared_brightness_nit_or_band",
                ],
                pool_hash="pool-hash-brightness",
                input_fingerprint="pool-input",
                rule_version=CORE3_M12C_RULE_VERSION,
                is_current=True,
            )
        )
        session.add(
            entities.Core3SkuClaimValueQuantification(
                sku_claim_value_id="sku-claim-brightness",
                pool_id="pool-brightness",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                product_category="TV",
                market_window="full_observed_window",
                analysis_population="claim_value_ready_with_comment",
                sku_code="TV00029112",
                claim_code="tv_claim_hdr_high_brightness",
                claim_name="高亮度",
                context_type="value_battlefield",
                context_code="BF_PREMIUM_PICTURE_UPGRADE",
                size_tier="size_65_75",
                price_band_group="premium",
                estimated_price_premium_abs=Decimal("9999"),
                estimated_weekly_sales_lift_abs=Decimal("8888"),
                estimated_weekly_sales_amount_lift_abs=Decimal("7777"),
                result_hash="sku-claim-hash",
                rule_version=CORE3_M12C_RULE_VERSION,
                is_current=True,
            )
        )
        session.commit()
        repository = AnalystRepository(
            session, project_id=PROJECT_ID, category_code="TV"
        )

        facts, rows_by_sku, refs, ambiguous = repository._v4_m12c_pool_tiers(
            batch_id=BATCH_ID,
            sku_codes=["TV00029112"],
            product_category="TV",
            market_window="full_observed_window",
            analysis_population="fact_complete_with_comment",
        )
    finally:
        session.close()

    assert len(facts) == 1
    assert facts[0].comparison_basis == "numeric_param_tier"
    assert facts[0].comparison_param_code == "declared_brightness_nit_or_band"
    assert facts[0].pool_sku_count == 10
    assert rows_by_sku["TV00029112"]
    assert refs
    assert ambiguous == set()
    serialized = json.dumps(
        [fact.model_dump(mode="json") for fact in facts], ensure_ascii=False
    )
    assert "9999" not in serialized
    assert "8888" not in serialized
    assert "7777" not in serialized
    assert "estimated_price_premium_abs" not in serialized


def test_g03_repository_source_has_no_runner_or_write_path(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/analyst_repository.py"
    ).read_text(encoding="utf-8")
    start = source.index("    def sellpoint_value_v4_context(")
    end = source.index("    def _sellpoint_competitor_selections(", start)
    g03_source = source[start:end]

    assert "purchase_reason_profile_runner" not in g03_source
    assert "self.db.add(" not in g03_source
    assert "self.db.flush(" not in g03_source
    assert "self.db.commit(" not in g03_source
    assert "estimated_price_premium_abs" not in g03_source
    assert "estimated_weekly_sales_lift_abs" not in g03_source
    assert "estimated_weekly_sales_amount_lift_abs" not in g03_source


def test_serving_scope_precedence_is_deterministic() -> None:
    selected, ambiguous = _v4_pick_rows_by_key(
        [
            SimpleNamespace(sku_code="TV1", batch_id="old", value="old"),
            SimpleNamespace(sku_code="TV1", batch_id="new", value="new"),
        ],
        requested_batch_id="serving-scope:TV:new,old",
        key_fn=lambda row: row.sku_code,
    )

    assert selected["TV1"].value == "new"
    assert ambiguous == set()


def test_multiple_current_rows_at_same_precedence_are_not_auto_selected() -> None:
    selected, ambiguous = _v4_pick_rows_by_key(
        [
            SimpleNamespace(sku_code="TV1", batch_id="new", taxonomy="a"),
            SimpleNamespace(sku_code="TV1", batch_id="new", taxonomy="b"),
        ],
        requested_batch_id="serving-scope:TV:new,old",
        key_fn=lambda row: row.sku_code,
    )

    assert "TV1" not in selected
    assert json.dumps("TV1") in ambiguous


def test_explicit_historical_batch_does_not_select_newer_row() -> None:
    selected, ambiguous = _v4_pick_rows_by_key(
        [
            SimpleNamespace(sku_code="TV1", batch_id="new", value="new"),
            SimpleNamespace(sku_code="TV1", batch_id="old", value="old"),
        ],
        requested_batch_id="old",
        key_fn=lambda row: row.sku_code,
    )

    assert selected["TV1"].value == "old"
    assert ambiguous == set()


def _current_authority(
    module_code: str, rule_version: str, result_hash: str
) -> SourceAuthority:
    ref = EvidenceRef(
        module_code=module_code,
        record_type=f"fixture_{module_code.lower()}",
        record_id=f"fixture-{module_code}",
        result_hash=result_hash,
        batch_id=BATCH_ID,
        rule_version=rule_version,
    )
    return SourceAuthority(
        module_code=module_code,
        table_name=ref.record_type,
        authority_mode="configured_rule",
        rule_version=rule_version,
        selected_batch_ids=[BATCH_ID],
        row_count=1,
        availability="present",
        usability="usable",
        source_hash=result_hash,
        selected_reason="G01 frozen fixture",
    )
