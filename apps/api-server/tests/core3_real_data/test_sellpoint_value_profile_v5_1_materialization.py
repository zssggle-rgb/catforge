from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
    SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_aggregation import (
    aggregate_sku_conclusion,
    aggregate_value_conclusion,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_config import (
    sellpoint_value_v5_1_config,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_enhancements import (
    adapt_same_budget_market_archetype,
    adapt_strict_market_implied_wtp,
    adapt_synthetic_market_baseline,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_generation import (
    SellpointValueV51GenerationService,
    build_v5_1_candidate_universe_fingerprint,
    build_v5_1_version_input_fingerprint,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_investments import (
    build_local_investment_review_overlays,
    classify_local_capability_investment,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_market_comparison import (
    calculate_direct_market_comparison,
    calculate_parameter_group_comparison,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    build_v5_1_profile_input_fingerprint,
    materialize_sellpoint_value_profile_v5_1,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51CompetitorVersionSource,
    SellpointValueV51MaterializationInput,
    SellpointValueV51SourceLineage,
    SellpointValueV51Target,
    SellpointValueV51ValueInput,
    SellpointValueV51VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51ReadbackIntegrityError,
    SellpointValueV51Repository,
    SellpointValueV51SourceIntegrityError,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    DirectMarketGap,
    QuantificationResult,
    QuestionConclusionSignal,
    SkuConclusionAggregationInput,
    ValueConclusionAggregationInput,
    ValueQuantificationStack,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_sellpoint_value_profile_persistence import (
    _source_batch,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_candidate_pools import (
    _build as _candidate_pools,
    _source as _competitor_source,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_enhancements import (
    _available_wtp,
    _synthetic,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_investments import (
    _investment,
    _scoped,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_market_comparison import (
    _direct_input,
    _market_observation,
    _parameter_input,
    _parameter_observation,
)


ROOT = Path(__file__).resolve().parents[2]


class FixtureProvider:
    def __init__(self, rows: dict[str, Any]) -> None:
        self.rows = rows

    def load_materialization_input(self, request, sku_code: str):
        value = self.rows[sku_code]
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    with engine.begin() as connection:
        entities.CategoryProject.__table__.create(bind=connection)
        entities.Core3V2PipelineRun.__table__.create(bind=connection)
        entities.Core3V2ModuleRun.__table__.create(bind=connection)
        entities.Core3SourceBatch.__table__.create(bind=connection)
        entities.Core3CompetitorProfileVersion.__table__.create(bind=connection)
        for table in (
            entities.Core3SellpointValueProfileVersion.__table__,
            entities.Core3SkuSellpointValueProfile.__table__,
            entities.Core3SkuSellpointValueCandidate.__table__,
            entities.Core3SkuSellpointValueItem.__table__,
        ):
            table.create(bind=connection)
    db = Session(engine, autoflush=False, future=True)
    db.add(
        entities.CategoryProject(
            project_id="project-1",
            name="TV project",
            category_code="TV",
        )
    )
    db.add(_source_batch("batch-1", "project-1", "TV"))
    db.flush()
    db.add(
        entities.Core3CompetitorProfileVersion(
            competitor_profile_version_id="cp-version-1",
            project_id="project-1",
            category_code="TV",
            product_category="TV",
            storage_batch_id="batch-1",
            release_scope_key="project-1:TV:agent",
            profile_version="cp-profile-v1",
            schema_version="competitor_profile_v1_1",
            rule_version="competitor_profile_agent_snapshot_rule_v2",
            method_version="competitor_profile_agent_snapshot_v2",
            authoritative_sku_manifest_hash="cp-manifest-hash",
            release_status="published",
            release_quality_status="limited",
            is_current=True,
            freshness_status="current",
            sku_count=2,
            input_fingerprint="cp-input-hash",
            candidate_universe_fingerprint="cp-candidate-hash",
            result_hash="version-hash-1",
            processing_status="completed",
        )
    )
    db.add(
        entities.Core3SellpointValueProfileVersion(
            sellpoint_value_profile_version_id="spv-v5-published",
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            product_category="TV",
            profile_version="spv-v5-history",
            schema_version=SELLPOINT_VALUE_PROFILE_SCHEMA_VERSION,
            rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
            method_version=SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
            release_status="published",
            release_quality_status="ready",
            is_current=True,
            input_fingerprint="v5-history-input",
            candidate_universe_fingerprint="v5-history-candidates",
            result_hash="v5-history-result",
            processing_status="completed",
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _repository(session: Session) -> SellpointValueV51Repository:
    return SellpointValueV51Repository(
        Core3RepositoryContext(
            db=session,
            project_id="project-1",
            category_code=Core3CategoryCode.TV,
        )
    )


def _value_input() -> SellpointValueV51ValueInput:
    pools = _candidate_pools()
    selected_use = next(
        use
        for question in pools.question_candidate_sets
        if question.question_code == "current_price_support"
        for use in question.candidate_uses
        if use.source_type == "competitor" and use.candidate_sku_code == "TV-C01"
    )
    direct = calculate_direct_market_comparison(
        _direct_input([_market_observation("TV-C01")])
    )
    parameter = calculate_parameter_group_comparison(
        _parameter_input([_parameter_observation("TV-C01", "60")])
    )
    same_budget_direct = calculate_direct_market_comparison(
        _direct_input([_market_observation("TV-C01")]).model_copy(
            update={"method": "same_budget_pool"}
        )
    )
    archetype = adapt_same_budget_market_archetype(same_budget_direct)
    synthetic = adapt_synthetic_market_baseline(
        project_id="project-1",
        category_code="TV",
        source=_synthetic(available=False),
    )
    strict_wtp = adapt_strict_market_implied_wtp(
        project_id="project-1",
        category_code="TV",
        target_sku_code="TV-TARGET",
        value_bundle_code="VALUE-1",
        source=_available_wtp(),
    )
    investment = classify_local_capability_investment(
        _scoped(
            item=_investment(
                capability_code="picture_quality",
                user_feedback_status="realized_advantage",
                relative_experience_status="advantage",
                price_support="positive",
            )
        )
    )
    review = build_local_investment_review_overlays([investment])[0]
    quantifications = [
        QuantificationResult(
            layer="user_value_evidence",
            method="saved_user_value_evidence",
            status="conclusion_available",
            strength="directional",
            facts={"source": "purchase_reason_profile"},
            result={"user_outcome_cn": "强光清晰、暗场有层次"},
            result_hash="quant-user-value",
        ),
        QuantificationResult(
            layer="direct_market_gap",
            method=direct.method,
            status="conclusion_available",
            strength="single",
            candidate_uses=[selected_use],
            facts={"comparator_count": 1},
            result={"business_conclusion_cn": direct.business_conclusion_cn},
            direct_market_gaps=[
                DirectMarketGap(
                    method="direct_comparable",
                    comparator_sku_codes=["TV-C01"],
                    comparator_count=1,
                    strength="single",
                    target_price=Decimal("6000"),
                    comparator_price=Decimal("5000"),
                    price_gap_abs=Decimal("1000"),
                    price_gap_pct=Decimal("0.2"),
                    target_weekly_sales=Decimal("40"),
                    comparator_weekly_sales=Decimal("50"),
                    sales_gap_abs=Decimal("-10"),
                    sales_gap_pct=Decimal("-0.2"),
                )
            ],
            result_hash="quant-direct-market",
        ),
        QuantificationResult(
            layer="market_archetype",
            method="same_budget",
            status="conclusion_available",
            strength="directional",
            candidate_uses=[selected_use],
            facts={"group_count": len(archetype.groups)},
            result={"business_conclusion_cn": archetype.business_conclusion_cn},
            result_hash="quant-market-archetype",
        ),
        QuantificationResult(
            layer="strict_market_implied_wtp",
            method=strict_wtp.method,
            status="conclusion_available",
            strength="directional",
            candidate_uses=[selected_use],
            facts={"pair_count": strict_wtp.pair_count},
            result={"estimate_center": strict_wtp.estimate_center},
            result_hash="quant-strict-wtp",
        ),
    ]
    signal_rows = [
        ("quant_user_value", quantifications[0].result_hash, "conclusion_available"),
        ("quant_direct_market", quantifications[1].result_hash, "conclusion_available"),
        (
            "quant_market_archetype",
            quantifications[2].result_hash,
            "conclusion_available",
        ),
        ("quant_strict_wtp", quantifications[3].result_hash, "conclusion_available"),
        ("direct_market", direct.result_hash, direct.status),
        ("parameter_group", parameter.result_hash, parameter.status),
        ("same_budget_archetype", archetype.result_hash, archetype.status),
        ("synthetic_baseline", synthetic.result_hash, synthetic.status),
        ("strict_wtp", strict_wtp.result_hash, strict_wtp.status),
        ("investment_conversion", investment.result_hash, investment.status),
        ("investment_review", review.result_hash, "no_conclusion"),
    ]
    signals = [
        QuestionConclusionSignal(
            question_code=code,
            status=status,
            confidence=(
                Decimal("0.4000")
                if status in {"conclusion_available", "partial_conclusion"}
                else None
            ),
            source_result_hash=result_hash,
        )
        for code, result_hash, status in signal_rows
    ]
    conclusion = aggregate_value_conclusion(
        ValueConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV-TARGET",
            value_bundle_code="VALUE-1",
            question_signals=signals,
        )
    )
    return SellpointValueV51ValueInput(
        battlefield_code="BF-PICTURE",
        battlefield_name_cn="画质体验",
        purchase_reason_code="PR-PICTURE",
        purchase_reason_name_cn="画质",
        value_bundle_code="VALUE-1",
        value_bundle_name_cn="客厅画质体验",
        normalized_bundle_code="picture_experience",
        perceived_outcome_cn="白天客厅不用拉窗帘也能看清，暗场层次更完整",
        capability_codes=["picture_quality"],
        question_signals=signals,
        quantification_stack=ValueQuantificationStack(
            value_bundle_code="VALUE-1",
            results=quantifications,
        ),
        direct_market_results=[direct],
        parameter_group_results=[parameter],
        market_archetype_results=[archetype],
        synthetic_market_baseline=synthetic,
        strict_market_implied_wtp=strict_wtp,
        investment_decisions=[investment],
        investment_reviews=[review],
        value_conclusion=conclusion,
        evidence_boundary_cn="量价为观察性市场关联，严格 WTP 仅在独立门槛通过时成立。",
    )


def _materialization_input(
    *,
    profile_version: str = "spv-v51-r1",
) -> SellpointValueV51MaterializationInput:
    source = _competitor_source()
    pools = _candidate_pools()
    value = _value_input()
    sku_conclusion = aggregate_sku_conclusion(
        SkuConclusionAggregationInput(
            project_id="project-1",
            category_code="TV",
            target_sku_code="TV-TARGET",
            value_results=[value.value_conclusion],
        )
    )
    return SellpointValueV51MaterializationInput(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        release_scope_key=source.release_scope_key,
        profile_version=profile_version,
        target=SellpointValueV51Target(
            sku_code="TV-TARGET",
            model_name="65E7Q",
            brand_name="海信",
            display_name_cn="海信 65E7Q",
        ),
        competitor_source=source,
        candidate_pools=pools,
        method_config=sellpoint_value_v5_1_config("TV"),
        source_lineage=[
            SellpointValueV51SourceLineage(
                source_code="market_facts",
                source_type="upstream",
                method_version="market-profile-v1",
                result_hash="market-facts-hash",
            ),
            SellpointValueV51SourceLineage(
                source_code="user_value_facts",
                source_type="upstream",
                method_version="purchase-reason-profile-v2",
                result_hash="user-value-facts-hash",
            ),
        ],
        values=[value],
        sku_conclusion=sku_conclusion,
    )


def _request(
    source: SellpointValueV51MaterializationInput,
    *,
    profile_version: str | None = None,
    expected_sku_codes: list[str] | None = None,
) -> SellpointValueV51VersionRequest:
    expected = expected_sku_codes or [source.target.sku_code]
    candidate_hashes = {
        code: source.candidate_pools.result_hash
        if code == source.target.sku_code
        else f"candidate-hash-{code}"
        for code in expected
    }
    competitor = source.competitor_source
    return SellpointValueV51VersionRequest(
        project_id=source.project_id,
        category_code=source.category_code,
        batch_id=source.batch_id,
        profile_version=profile_version or source.profile_version,
        competitor_source=SellpointValueV51CompetitorVersionSource(
            access_mode=competitor.access_mode,
            competitor_profile_version_id=competitor.competitor_profile_version_id,
            profile_version=competitor.profile_version,
            method_version=competitor.method_version,
            release_status=competitor.release_status,
            is_current=competitor.is_current,
            release_scope_key=competitor.release_scope_key,
            version_result_hash=competitor.source_version_result_hash,
        ),
        expected_sku_codes=expected,
        candidate_pool_hashes=candidate_hashes,
        method_config=source.method_config,
        method_versions={
            "aggregation": "sellpoint_value_sku_status_v5_1",
            "candidate_pools": "sellpoint_value_candidate_pools_v5_1",
            "competitor_source": "competitor_profile_agent_snapshot_v2",
            "direct_market": "sellpoint_value_direct_market_gap_v5_1",
            "enhancements": "sellpoint_value_market_archetype_v5_1",
            "investment": "sellpoint_value_local_investment_v5_1",
            "parameter_group": "sellpoint_value_parameter_group_v5_1",
        },
        source_lineage=source.source_lineage,
    )


def test_materializer_persists_complete_low_gate_typed_profile_and_fingerprints() -> (
    None
):
    source = _materialization_input()

    materialized = materialize_sellpoint_value_profile_v5_1(
        source,
        sellpoint_value_profile_version_id="spv-version-v51",
    )

    assert materialized.profile.sku_conclusion.status == "conclusion_available"
    assert materialized.persistence_bundle.profile.profile_confidence == Decimal(
        "0.4000"
    )
    assert materialized.persistence_bundle.profile.review_required is False
    assert {
        row.layer for row in materialized.profile.values[0].quantification_stack.results
    } == {
        "user_value_evidence",
        "direct_market_gap",
        "market_archetype",
        "strict_market_implied_wtp",
    }
    assert materialized.persistence_bundle.value_items[0].direct_market_result_available
    assert len(materialized.persistence_bundle.candidates) == (
        len(source.candidate_pools.formal_competitors)
        + len(source.candidate_pools.analysis_references)
    )
    duplicate = [
        row
        for row in materialized.persistence_bundle.candidates
        if row.candidate_sku_code == "TV-C02"
    ]
    assert {row.pool_type for row in duplicate} == {"competitor", "reference"}
    assert (
        next(row for row in duplicate if row.pool_type == "reference").review_required
        is False
    )

    reversed_source = source.model_copy(
        update={
            "source_lineage": list(reversed(source.source_lineage)),
            "values": [
                source.values[0].model_copy(
                    update={
                        "question_signals": list(
                            reversed(source.values[0].question_signals)
                        )
                    }
                )
            ],
        }
    )
    assert build_v5_1_profile_input_fingerprint(source) == (
        build_v5_1_profile_input_fingerprint(reversed_source)
    )
    changed_source = source.model_copy(
        update={
            "competitor_source": source.competitor_source.model_copy(
                update={"source_version_result_hash": "version-hash-changed"}
            )
        }
    )
    assert build_v5_1_profile_input_fingerprint(source) != (
        build_v5_1_profile_input_fingerprint(changed_source)
    )
    changed_analysis = source.model_copy(
        update={
            "values": [
                source.values[0].model_copy(
                    update={
                        "question_signals": [
                            source.values[0]
                            .question_signals[0]
                            .model_copy(update={"confidence": Decimal("0.45")}),
                            *source.values[0].question_signals[1:],
                        ]
                    }
                )
            ]
        }
    )
    assert build_v5_1_profile_input_fingerprint(source) != (
        build_v5_1_profile_input_fingerprint(changed_analysis)
    )
    changed_config = source.model_copy(
        update={
            "method_config": source.method_config.model_copy(
                update={
                    "table_stake": source.method_config.table_stake.model_copy(
                        update={"prevalence_threshold": Decimal("0.75")}
                    )
                }
            )
        }
    )
    assert build_v5_1_profile_input_fingerprint(source) != (
        build_v5_1_profile_input_fingerprint(changed_config)
    )


def test_generation_is_idempotent_and_preserves_v5_published_current(
    session: Session,
) -> None:
    source = _materialization_input()
    request = _request(source)
    repository = _repository(session)
    service = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({"TV-TARGET": source}),
    )

    first = service.generate_draft(request, sku_code="TV-TARGET")
    second = service.generate_draft(request, sku_code="TV-TARGET")

    assert first.profile == second.profile
    assert first.persisted.profile.sku_sellpoint_value_profile_id == (
        second.persisted.profile.sku_sellpoint_value_profile_id
    )
    assert first.persisted.version.release_status == "draft"
    assert first.persisted.version.is_current is False
    assert first.persisted.version.release_quality_status == "ready"
    assert first.persisted.version.source_competitor_profile_version_id == (
        "cp-version-1"
    )
    assert (
        session.scalar(
            select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
        )
        == 1
    )
    assert session.scalar(
        select(func.count()).select_from(entities.Core3SkuSellpointValueCandidate)
    ) == len(first.persisted.candidates)
    history = session.get(
        entities.Core3SellpointValueProfileVersion,
        "spv-v5-published",
    )
    assert history is not None
    assert history.release_status == "published"
    assert history.is_current is True
    assert history.result_hash == "v5-history-result"


def test_typed_readback_rejects_hash_tampering(session: Session) -> None:
    source = _materialization_input()
    repository = _repository(session)
    service = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({"TV-TARGET": source}),
    )
    service.generate_draft(_request(source), sku_code="TV-TARGET")
    row = session.scalar(select(entities.Core3SkuSellpointValueProfile))
    assert row is not None
    row.question_analyses_json = []
    session.commit()

    with pytest.raises(SellpointValueV51ReadbackIntegrityError):
        repository.get_v5_1_profile(
            batch_id="batch-1",
            profile_version=source.profile_version,
            sku_code="TV-TARGET",
        )


def test_typed_readback_rejects_missing_candidate_child(session: Session) -> None:
    source = _materialization_input(profile_version="spv-v51-dangling")
    repository = _repository(session)
    SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_draft(_request(source), sku_code="TV-TARGET")
    candidate = session.scalar(
        select(entities.Core3SkuSellpointValueCandidate).where(
            entities.Core3SkuSellpointValueCandidate.candidate_sku_code == "TV-C01"
        )
    )
    assert candidate is not None
    session.delete(candidate)
    session.commit()

    with pytest.raises(SellpointValueV51ReadbackIntegrityError):
        repository.get_v5_1_profile(
            batch_id="batch-1",
            profile_version=source.profile_version,
            sku_code="TV-TARGET",
        )


def test_failed_sku_rolls_back_only_itself_and_version_records_failure(
    session: Session,
) -> None:
    source = _materialization_input(profile_version="spv-v51-batch")
    request = _request(
        source,
        expected_sku_codes=["TV-BAD", "TV-TARGET"],
    )
    repository = _repository(session)
    result = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider(
            {
                "TV-BAD": RuntimeError("fixture failure"),
                "TV-TARGET": source,
            }
        ),
    ).generate_many(request)

    assert [(row.sku_code, row.status) for row in result.statuses] == [
        ("TV-BAD", "failed"),
        ("TV-TARGET", "generated"),
    ]
    assert result.version.failed_count == 1
    assert result.version.release_quality_status == "blocked"
    assert (
        session.scalar(
            select(func.count()).select_from(entities.Core3SkuSellpointValueProfile)
        )
        == 1
    )
    saved = repository.get_v5_1_profile(
        batch_id="batch-1",
        profile_version="spv-v51-batch",
        sku_code="TV-TARGET",
    )
    assert saved is not None
    assert (
        repository.get_v5_1_profile(
            batch_id="batch-1",
            profile_version="spv-v51-batch",
            sku_code="TV-BAD",
        )
        is None
    )


def test_version_progress_batches_integrity_reads_without_per_sku_queries(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _materialization_input(profile_version="spv-v51-progress-pages")
    repository = _repository(session)
    saved = SellpointValueV51GenerationService(
        repository=repository,
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_draft(_request(source), sku_code="TV-TARGET")
    version_id = saved.persisted.version.sellpoint_value_profile_version_id
    original = session.scalar(
        select(entities.Core3SkuSellpointValueProfile).where(
            entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
            == version_id
        )
    )
    assert original is not None
    table = entities.Core3SkuSellpointValueProfile.__table__
    base_payload = {
        column.name: getattr(original, column.name)
        for column in table.c
        if column.name not in {"created_at", "updated_at"}
    }
    expected_sku_codes = ["TV-TARGET"]
    for index in range(1, 130):
        sku_code = f"TV-PROGRESS-{index:03d}"
        expected_sku_codes.append(sku_code)
        session.add(
            entities.Core3SkuSellpointValueProfile(
                **{
                    **base_payload,
                    "sku_sellpoint_value_profile_id": f"progress-profile-{index:03d}",
                    "sku_code": sku_code,
                    "display_name_cn": sku_code,
                    "input_fingerprint": f"progress-input-{index:03d}",
                    "result_hash": f"progress-result-{index:03d}",
                }
            )
        )
    session.commit()
    monkeypatch.setattr(
        repository,
        "_validate_v5_1_readback",
        lambda persisted: persisted,
    )
    select_statements: list[str] = []

    def count_selects(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            select_statements.append(statement)

    engine = session.get_bind()
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        progress = repository.refresh_v5_1_version_progress(
            sellpoint_value_profile_version_id=version_id,
            expected_sku_codes=sorted(expected_sku_codes),
        )
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert progress.sku_count == 130
    assert progress.conclusion_available_count == 130
    assert len(select_statements) <= 15


def test_competitor_source_hash_must_exist_before_v5_1_version_creation(
    session: Session,
) -> None:
    source = _materialization_input(profile_version="spv-v51-bad-source")
    request = _request(source)
    bad_request = request.model_copy(
        update={
            "competitor_source": request.competitor_source.model_copy(
                update={"version_result_hash": "wrong-source-hash"}
            )
        }
    )
    service = SellpointValueV51GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider({"TV-TARGET": source}),
    )

    with pytest.raises(SellpointValueV51SourceIntegrityError):
        service.ensure_version(bad_request)
    assert (
        session.scalar(
            select(func.count())
            .select_from(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.method_version
                == "sellpoint_value_profile_method_v5_1"
            )
        )
        == 0
    )


def test_version_fingerprints_are_order_invariant_and_bind_candidate_hashes() -> None:
    source = _materialization_input()
    request = _request(
        source,
        expected_sku_codes=["TV-A", "TV-TARGET"],
    )
    reordered = request.model_copy(
        update={
            "expected_sku_codes": list(reversed(request.expected_sku_codes)),
            "candidate_pool_hashes": dict(
                reversed(list(request.candidate_pool_hashes.items()))
            ),
            "source_lineage": list(reversed(request.source_lineage)),
        }
    )
    changed = request.model_copy(
        update={
            "candidate_pool_hashes": {
                **request.candidate_pool_hashes,
                "TV-A": "changed-candidate-pool-hash",
            }
        }
    )

    assert build_v5_1_version_input_fingerprint(request) == (
        build_v5_1_version_input_fingerprint(reordered)
    )
    assert build_v5_1_candidate_universe_fingerprint(request) == (
        build_v5_1_candidate_universe_fingerprint(reordered)
    )
    assert build_v5_1_version_input_fingerprint(request) != (
        build_v5_1_version_input_fingerprint(changed)
    )


def test_v5_1_generation_modules_do_not_import_old_candidate_or_live_paths() -> None:
    files = [
        ROOT
        / "app/services/core3_real_data/analyst/sellpoint_value_profile_v5_1_materializer.py",
        ROOT
        / "app/services/core3_real_data/analyst/sellpoint_value_profile_v5_1_repository.py",
        ROOT
        / "app/services/core3_real_data/analyst/sellpoint_value_profile_v5_1_generation.py",
    ]
    forbidden = {
        "sellpoint_value_profile_input_provider",
        "sellpoint_value_profile_candidate_service",
        "claim_value_pm_v5_service",
        "competitor_answer",
        "sop_orchestrators",
    }
    imported: set[str] = set()
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

    assert not any(token in module for token in forbidden for module in imported)
