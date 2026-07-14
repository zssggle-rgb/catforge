from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputProvider,
    CompetitorProfileSourceAuthorityError,
    CompetitorProfileSourceConflictError,
    CompetitorProfileTargetNotFoundError,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileInputRequest,
    CompetitorProfileTargetInputBundle,
    ModuleCategorySnapshot,
    TargetModuleInput,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.constants import (
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_AC_TAXONOMY_VERSION,
    CORE3_M03B_RULE_VERSION,
    CORE3_M03B_TAXONOMY_VERSION,
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
    CORE3_M05C_AC_RULE_VERSION,
    CORE3_M05C_AC_TAXONOMY_VERSION,
    CORE3_M05C_TV_RULE_VERSION,
    CORE3_M05C_TV_TAXONOMY_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M09C_AC_RULE_VERSION,
    CORE3_M09C_AC_TAXONOMY_VERSION,
    CORE3_M09C_TV_RULE_VERSION,
    CORE3_M09C_TV_TAXONOMY_VERSION,
    CORE3_M10C_AC_RULE_VERSION,
    CORE3_M10C_AC_TAXONOMY_VERSION,
    CORE3_M10C_TV_RULE_VERSION,
    CORE3_M10C_TV_TAXONOMY_VERSION,
    CORE3_M11C_AC_RULE_VERSION,
    CORE3_M11C_AC_TAXONOMY_VERSION,
    CORE3_M11C_TV_RULE_VERSION,
    CORE3_M11C_TV_TAXONOMY_VERSION,
    CORE3_M11D_RULE_VERSION,
    CORE3_M12C_AC_RULE_VERSION,
    CORE3_M12C_TV_RULE_VERSION,
    CORE3_M12D_RULE_VERSION,
    Core3CategoryCode,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


@pytest.fixture
def session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    entities.Base.metadata.create_all(engine)
    db = Session(engine, autoflush=False, future=True)
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _project_id(category: str) -> str:
    return f"project-{category.lower()}"


def _sku_codes(category: str) -> tuple[str, str]:
    return (f"{category}000001", f"{category}000002")


def _batch_ids(category: str) -> tuple[str, ...]:
    return ("batch-tv-a", "batch-tv-b") if category == "TV" else ("batch-ac",)


def _storage_batch(category: str) -> str:
    return _batch_ids(category)[-1]


def _request(category: str = "TV") -> CompetitorProfileInputRequest:
    return CompetitorProfileInputRequest(
        project_id=_project_id(category),
        category_code=category,
        product_category=category,
        storage_batch_id=_storage_batch(category),
        source_batch_ids=list(_batch_ids(category)),
        analysis_population="competitor_profile_full_published_scope",
        semantic_market_analysis_population=(
            "fact_complete_with_comment"
            if category == "TV"
            else "all_semantic_profiles"
        ),
        claim_value_analysis_population="claim_value_ready_with_comment",
        market_window="full_observed_window",
    )


def _provider(session: Session, category: str = "TV") -> CompetitorProfileInputProvider:
    return CompetitorProfileInputProvider(
        Core3RepositoryContext(
            db=session,
            project_id=_project_id(category),
            category_code=Core3CategoryCode(category),
        )
    )


def _rules(category: str) -> dict[str, str]:
    ac = category == "AC"
    return {
        "M03B": CORE3_M03B_AC_RULE_VERSION if ac else CORE3_M03B_RULE_VERSION,
        "M04C": CORE3_M04C_AC_RULE_VERSION if ac else CORE3_M04C_TV_RULE_VERSION,
        "M05C": CORE3_M05C_AC_RULE_VERSION if ac else CORE3_M05C_TV_RULE_VERSION,
        "M09C": CORE3_M09C_AC_RULE_VERSION if ac else CORE3_M09C_TV_RULE_VERSION,
        "M10C": CORE3_M10C_AC_RULE_VERSION if ac else CORE3_M10C_TV_RULE_VERSION,
        "M11C": CORE3_M11C_AC_RULE_VERSION if ac else CORE3_M11C_TV_RULE_VERSION,
        "M12C": CORE3_M12C_AC_RULE_VERSION if ac else CORE3_M12C_TV_RULE_VERSION,
    }


def _taxonomies(category: str) -> dict[str, str]:
    ac = category == "AC"
    return {
        "M03B": (
            CORE3_M03B_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M03B_TAXONOMY_VERSION
        ),
        "M04C": (
            CORE3_M04C_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M04C_TV_TAXONOMY_VERSION
        ),
        "M05C": (
            CORE3_M05C_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M05C_TV_TAXONOMY_VERSION
        ),
        "M09C": (
            CORE3_M09C_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M09C_TV_TAXONOMY_VERSION
        ),
        "M10C": (
            CORE3_M10C_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M10C_TV_TAXONOMY_VERSION
        ),
        "M11C": (
            CORE3_M11C_AC_TAXONOMY_VERSION
            if ac
            else CORE3_M11C_TV_TAXONOMY_VERSION
        ),
    }


def _seed_category(
    session: Session,
    *,
    category: str = "TV",
    missing: set[tuple[str, str]] | None = None,
    polluted_m03_sku: str | None = None,
) -> str:
    missing = missing or set()
    project_id = _project_id(category)
    batches = _batch_ids(category)
    storage_batch = _storage_batch(category)
    sku_codes = _sku_codes(category)
    rules = _rules(category)
    taxonomies = _taxonomies(category)
    request = _request(category)

    session.add(
        entities.CategoryProject(
            project_id=project_id,
            name=category,
            category_code=category,
        )
    )
    for batch_id in batches:
        session.add(
            entities.Core3SourceBatch(
                batch_id=batch_id,
                project_id=project_id,
                category_code=category,
                source_system="fixture",
                source_database="fixture",
                source_tables=[],
                ruleset_version="rules-v1",
                module_version="module-v1",
                hash_version="hash-v1",
                scan_started_at=datetime.now(timezone.utc),
                status="completed",
            )
        )
    session.flush()

    for index, sku_code in enumerate(sku_codes):
        batch_id = batches[index % len(batches)]
        if ("M03B", sku_code) not in missing:
            session.add(
                entities.Core3SkuParamProfile(
                    project_id=project_id,
                    category_code=category,
                    batch_id=batch_id,
                    sku_code=sku_code,
                    model_name=f"型号-{sku_code}",
                    profile_hash=f"m03-{sku_code}",
                    rule_version=rules["M03B"],
                )
            )
        if ("M04C", sku_code) not in missing:
            session.add(
                entities.Core3SkuClaimFactProfile(
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    taxonomy_version=taxonomies["M04C"],
                    sku_code=sku_code,
                    claim_codes=["claim-picture"],
                    profile_hash=f"m04-{sku_code}",
                    rule_version=rules["M04C"],
                    is_current=True,
                )
            )
        if ("M05C", sku_code) not in missing:
            session.add(
                entities.Core3SkuCommentFactProfile(
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    taxonomy_version=taxonomies["M05C"],
                    sku_code=sku_code,
                    signal_summary_json={"picture": "positive"},
                    profile_hash=f"m05-{sku_code}",
                    rule_version=rules["M05C"],
                    is_current=True,
                )
            )
        session.add(
            entities.Core3SkuMarketProfile(
                project_id=project_id,
                category_code=category,
                batch_id=batch_id,
                sku_code=sku_code,
                brand_name="品牌A",
                model_name=f"型号-{sku_code}",
                analysis_window=request.market_window,
                market_pool_key=f"{category}-pool",
                screen_size_inch=(Decimal("65") if category == "TV" else None),
                price_wavg=Decimal("5000") + index * 100,
                sales_volume_total=Decimal("100") + index * 10,
                active_week_count=10,
                rule_version=CORE3_M07_RULE_VERSION,
                input_fingerprint=f"m07-input-{sku_code}",
                result_hash=f"m07-{sku_code}",
                is_current=True,
            )
        )
        if ("M09C", sku_code) not in missing:
            session.add(
                entities.Core3M09cSkuUserTaskProfile(
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    taxonomy_version=taxonomies["M09C"],
                    rule_version=rules["M09C"],
                    sku_code=sku_code,
                    primary_user_task_code="task-picture",
                    profile_hash=f"m09-{sku_code}",
                    is_current=True,
                )
            )
        if ("M10C", sku_code) not in missing:
            session.add(
                entities.Core3M10cSkuTargetGroupProfile(
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    taxonomy_version=taxonomies["M10C"],
                    rule_version=rules["M10C"],
                    sku_code=sku_code,
                    primary_target_group_code="group-family",
                    profile_hash=f"m10-{sku_code}",
                    is_current=True,
                )
            )
        if ("M11C", sku_code) not in missing:
            session.add(
                entities.Core3SkuValueBattlefieldProfile(
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    taxonomy_version=taxonomies["M11C"],
                    rule_version=rules["M11C"],
                    sku_code=sku_code,
                    primary_battlefield_code="battlefield-picture",
                    profile_hash=f"m11-{sku_code}",
                    is_current=True,
                )
            )
        if ("M11D", sku_code) not in missing:
            summary = entities.Core3SemanticMarketDimensionSummary(
                project_id=project_id,
                category_code=category,
                product_category=category,
                batch_id=batch_id,
                analysis_population=request.semantic_market_analysis_population,
                market_window=request.market_window,
                dimension_type="battlefield",
                dimension_code=f"battlefield-picture-{sku_code}",
                dimension_name="画质体验",
                taxonomy_version=taxonomies["M11C"],
                rule_version=CORE3_M11D_RULE_VERSION,
                input_fingerprint=f"m11d-summary-input-{sku_code}",
                result_hash=f"m11d-summary-{sku_code}",
                is_current=True,
            )
            allocation = entities.Core3SemanticMarketAllocation(
                project_id=project_id,
                category_code=category,
                product_category=category,
                batch_id=batch_id,
                analysis_population=request.semantic_market_analysis_population,
                market_window=request.market_window,
                dimension_type="battlefield",
                dimension_code=f"battlefield-picture-{sku_code}",
                dimension_name="画质体验",
                sku_code=sku_code,
                allocation_role="primary",
                relation_status="established",
                input_fingerprint=f"m11d-allocation-input-{sku_code}",
                result_hash=f"m11d-allocation-{sku_code}",
                rule_version=CORE3_M11D_RULE_VERSION,
                is_current=True,
            )
            session.add_all([summary, allocation])
            session.flush()
            session.add(
                entities.Core3SemanticMarketSkuContribution(
                    summary_id=summary.summary_id,
                    allocation_id=allocation.allocation_id,
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    analysis_population=request.semantic_market_analysis_population,
                    market_window=request.market_window,
                    dimension_type="battlefield",
                    dimension_code=f"battlefield-picture-{sku_code}",
                    dimension_name="画质体验",
                    sku_code=sku_code,
                    allocation_role="primary",
                    relation_status="established",
                    input_fingerprint=f"m11d-input-{sku_code}",
                    result_hash=f"m11d-{sku_code}",
                    rule_version=CORE3_M11D_RULE_VERSION,
                    is_current=True,
                )
            )
        if ("M12C", sku_code) not in missing:
            pool = entities.Core3ClaimValueContextPool(
                project_id=project_id,
                category_code=category,
                product_category=category,
                batch_id=batch_id,
                market_window=request.market_window,
                analysis_population=request.claim_value_analysis_population,
                claim_code=f"claim-{sku_code}",
                pool_hash=f"pool-{sku_code}",
                rule_version=rules["M12C"],
                input_fingerprint=f"pool-input-{sku_code}",
                is_current=True,
            )
            session.add(pool)
            session.flush()
            session.add(
                entities.Core3SkuClaimValueQuantification(
                    pool_id=pool.pool_id,
                    project_id=project_id,
                    category_code=category,
                    product_category=category,
                    batch_id=batch_id,
                    market_window=request.market_window,
                    analysis_population=request.claim_value_analysis_population,
                    sku_code=sku_code,
                    claim_code=f"claim-{sku_code}",
                    claim_name="画质清晰",
                    claim_value_role="value_bundle_claim",
                    result_hash=f"m12c-{sku_code}",
                    rule_version=rules["M12C"],
                    is_current=True,
                )
            )

    version = entities.Core3PurchaseReasonProfileVersion(
        project_id=project_id,
        category_code=category,
        product_category=category,
        batch_id=storage_batch,
        m12d_profile_version=f"m12d_{category.lower()}_current_v1",
        schema_version="sku_purchase_reason_profile_v1",
        rule_version=CORE3_M12D_RULE_VERSION,
        release_status="published",
        release_quality_status="ready",
        is_current=True,
        source_batch_ids_json=list(batches),
        input_scope_json={
            "product_category": category,
            "market_window": request.market_window,
            "source_batch_ids": list(batches),
        },
        sku_count=len(sku_codes),
        ready_count=len(sku_codes),
        input_fingerprint=f"m12d-version-input-{category}",
        result_hash=f"m12d-version-{category}",
    )
    session.add(version)
    session.flush()
    for sku_code in sku_codes:
        if ("M12D", sku_code) in missing:
            continue
        session.add(
            entities.Core3SkuPurchaseReasonProfile(
                purchase_reason_version_id=version.purchase_reason_version_id,
                project_id=project_id,
                category_code=category,
                product_category=category,
                batch_id=storage_batch,
                m12d_profile_version=version.m12d_profile_version,
                schema_version=version.schema_version,
                rule_version=version.rule_version,
                sku_code=sku_code,
                model_name=f"型号-{sku_code}",
                brand_name="品牌A",
                display_name_cn=f"品牌A 型号-{sku_code}",
                status="ready",
                profile_confidence=Decimal("0.85"),
                source_batch_ids_json=list(batches),
                release_status="published",
                is_current=True,
                input_fingerprint=f"m12d-input-{sku_code}",
                result_hash=f"m12d-{sku_code}",
            )
        )
    if polluted_m03_sku:
        session.add(
            entities.Core3SkuParamProfile(
                project_id=project_id,
                category_code=category,
                batch_id=storage_batch,
                sku_code=polluted_m03_sku,
                model_name="错误 AC 参数画像",
                profile_hash=f"polluted-{polluted_m03_sku}",
                rule_version=(
                    CORE3_M03B_AC_RULE_VERSION
                    if category == "TV"
                    else CORE3_M03B_RULE_VERSION
                ),
            )
        )
    session.flush()
    return version.purchase_reason_version_id


def test_tv_category_bundle_locks_exact_authorities_and_avoids_n_plus_one(
    session: Session,
) -> None:
    _seed_category(session)
    provider = _provider(session)
    request = _request()
    select_count = 0

    def _count_selects(_, __, statement, ___, ____, _____) -> None:
        nonlocal select_count
        if statement.lstrip().upper().startswith("SELECT"):
            select_count += 1

    event.listen(session.bind, "before_cursor_execute", _count_selects)
    bundle = provider.load_category_input_bundle(request)
    assert select_count == 11
    before_target = select_count
    target = provider.load_target_input(bundle, "TV000001")
    assert select_count == before_target
    event.remove(session.bind, "before_cursor_execute", _count_selects)

    assert bundle.authoritative_sku_codes == ["TV000001", "TV000002"]
    assert bundle.serving_scope.authoritative_sku_count == 2
    assert set(bundle.modules) == set(bundle.serving_scope.source_authorities)
    assert bundle.modules["M03B"].authority.taxonomy_version != bundle.modules[
        "M04C"
    ].authority.taxonomy_version
    assert bundle.modules["M03B"].authority.source_batch_ids == [
        "batch-tv-a",
        "batch-tv-b",
    ]
    assert target.analysis_state == "ready"
    assert target.target_identity["model_name"] == "型号-TV000001"
    assert all(row.availability == "present" for row in target.modules.values())
    assert provider.load_category_input_bundle(request).input_fingerprint == (
        bundle.input_fingerprint
    )


def test_public_manifest_and_scope_methods_use_the_same_exact_snapshot(
    session: Session,
) -> None:
    _seed_category(session)
    provider = _provider(session)
    request = _request()

    assert provider.list_authoritative_sku_codes(request) == [
        "TV000001",
        "TV000002",
    ]
    scope = provider.resolve_serving_scope(request)
    assert scope.authoritative_sku_count == 2
    assert scope.authoritative_sku_manifest_hash
    assert set(scope.source_authorities) == {
        "M03B",
        "M04C",
        "M05C",
        "M07",
        "M09C",
        "M10C",
        "M11C",
        "M11D",
        "M12C",
        "M12D",
    }


def test_production_input_request_uses_exact_current_published_m12d_scope(
    session: Session,
) -> None:
    _seed_category(session)
    request = _provider(session).build_production_input_request()

    assert request == _request("TV")
    assert request.allow_preview_inputs is False


def test_production_input_request_fails_closed_without_one_current_version(
    session: Session,
) -> None:
    with pytest.raises(
        CompetitorProfileSourceAuthorityError,
        match="exactly one current published M12D",
    ):
        _provider(session).build_production_input_request()


def test_optional_target_gap_is_unknown_not_zero_or_whole_sku_block(
    session: Session,
) -> None:
    _seed_category(session, missing={("M05C", "TV000001")})
    bundle = _provider(session).load_category_input_bundle(_request())
    target = _provider(session).load_target_input(bundle, "TV000001")

    assert target.analysis_state == "partial"
    assert target.hard_block_reasons == []
    assert target.modules["M05C"].availability == "unknown"
    assert target.modules["M05C"].records == []
    assert target.modules["M05C"].missing_reason_code == (
        "m05c_sku_not_covered_by_locked_authority"
    )
    assert bundle.modules["M05C"].records_by_sku["TV000002"]


def test_wrong_category_m03_rule_is_never_used_as_target_fallback(
    session: Session,
) -> None:
    _seed_category(
        session,
        missing={("M03B", "TV000001")},
        polluted_m03_sku="TV000001",
    )
    provider = _provider(session)
    bundle = provider.load_category_input_bundle(_request())
    target = provider.load_target_input(bundle, "TV000001")

    assert target.analysis_state == "blocked"
    assert target.hard_block_reasons == [
        "m03b_sku_not_covered_by_locked_authority"
    ]
    assert target.modules["M03B"].availability == "unknown"
    assert set(bundle.modules["M03B"].records_by_sku) == {"TV000002"}
    assert bundle.modules["M03B"].authority.rule_version == CORE3_M03B_RULE_VERSION


def test_ac_single_batch_uses_ac_rules_and_stays_category_isolated(
    session: Session,
) -> None:
    _seed_category(session, category="AC")
    provider = _provider(session, "AC")
    bundle = provider.load_category_input_bundle(_request("AC"))
    target = provider.load_target_input(bundle, "AC000001")

    assert bundle.serving_scope.source_batch_ids == ["batch-ac"]
    assert bundle.modules["M03B"].authority.rule_version == CORE3_M03B_AC_RULE_VERSION
    assert all(code.startswith("AC") for code in bundle.authoritative_sku_codes)
    assert target.analysis_state == "ready"


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"product_category": "TV"}, "must match"),
        ({"source_batch_ids": ["batch-ac", "batch-ac-2"]}, "exactly one"),
        ({"storage_batch_id": "outside"}, "inside"),
    ],
)
def test_input_request_rejects_invalid_scopes(
    updates: dict[str, object],
    message: str,
) -> None:
    payload = _request("AC").model_dump(mode="python")
    payload.update(updates)
    with pytest.raises(ValidationError, match=message):
        CompetitorProfileInputRequest(**payload)

    tv_payload = _request().model_dump(mode="python")
    tv_payload["source_batch_ids"] = ["batch-tv-b", "batch-tv-a"]
    with pytest.raises(ValidationError, match="sorted and unique"):
        CompetitorProfileInputRequest(**tv_payload)


def test_provider_rejects_request_from_another_project_category(
    session: Session,
) -> None:
    with pytest.raises(ValueError, match="provider context"):
        _provider(session).load_category_input_bundle(_request("AC"))


def test_m12d_version_lock_ignores_newer_noncurrent_version(session: Session) -> None:
    _seed_category(session)
    session.add(
        entities.Core3PurchaseReasonProfileVersion(
            project_id=_project_id("TV"),
            category_code="TV",
            product_category="TV",
            batch_id=_storage_batch("TV"),
            m12d_profile_version="zzz-newer-but-not-current",
            rule_version=CORE3_M12D_RULE_VERSION,
            release_status="published",
            release_quality_status="ready",
            is_current=False,
            source_batch_ids_json=list(_batch_ids("TV")),
            input_fingerprint="noncurrent-input",
            result_hash="noncurrent-result",
        )
    )
    session.flush()

    bundle = _provider(session).load_category_input_bundle(_request())
    assert bundle.modules["M12D"].authority.profile_version == "m12d_tv_current_v1"


def test_multiple_current_m12d_versions_are_an_authority_conflict(
    session: Session,
) -> None:
    _seed_category(session)
    session.add(
        entities.Core3PurchaseReasonProfileVersion(
            project_id=_project_id("TV"),
            category_code="TV",
            product_category="TV",
            batch_id=_storage_batch("TV"),
            m12d_profile_version="m12d_tv_conflicting_current",
            rule_version=CORE3_M12D_RULE_VERSION,
            release_status="published",
            release_quality_status="ready",
            is_current=True,
            source_batch_ids_json=list(_batch_ids("TV")),
            input_fingerprint="conflict-input",
            result_hash="conflict-result",
        )
    )
    session.flush()
    with pytest.raises(CompetitorProfileSourceAuthorityError, match="exactly one"):
        _provider(session).load_category_input_bundle(_request())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("release_quality_status", "blocked", "non-consumable"),
        ("source_batch_ids_json", ["outside-batch"], "outside"),
        (
            "input_scope_json",
            {"product_category": "AC"},
            "product_category",
        ),
    ],
)
def test_m12d_authority_quality_batch_and_scope_conflicts_fail_closed(
    session: Session,
    field_name: str,
    value: object,
    message: str,
) -> None:
    _seed_category(session)
    version = session.execute(
        select(entities.Core3PurchaseReasonProfileVersion).where(
            entities.Core3PurchaseReasonProfileVersion.is_current.is_(True)
        )
    ).scalar_one()
    setattr(version, field_name, value)
    session.flush()

    with pytest.raises(CompetitorProfileSourceAuthorityError, match=message):
        _provider(session).load_category_input_bundle(_request())


def test_m12d_can_be_unavailable_for_the_whole_authoritative_scope(
    session: Session,
) -> None:
    _seed_category(
        session,
        missing={("M12D", "TV000001"), ("M12D", "TV000002")},
    )
    bundle = _provider(session).load_category_input_bundle(_request())

    assert bundle.modules["M12D"].record_count == 0
    assert bundle.modules["M12D"].records_by_sku == {}
    assert bundle.modules["M12D"].authority.release_status == "unavailable"
    target = _provider(session).load_target_input(bundle, "TV000001")
    assert target.modules["M12D"].availability == "unknown"
    assert any("m12d" in reason for reason in target.limitations)


def test_m12d_conflicting_rows_are_not_resolved_by_batch_recency(
    session: Session,
) -> None:
    _seed_category(session)
    version = session.execute(
        select(entities.Core3PurchaseReasonProfileVersion).where(
            entities.Core3PurchaseReasonProfileVersion.is_current.is_(True)
        )
    ).scalar_one()
    session.add(
        entities.Core3SkuPurchaseReasonProfile(
            purchase_reason_version_id=version.purchase_reason_version_id,
            project_id=_project_id("TV"),
            category_code="TV",
            product_category="TV",
            batch_id="batch-tv-a",
            m12d_profile_version=version.m12d_profile_version,
            schema_version=version.schema_version,
            rule_version=version.rule_version,
            sku_code="TV000001",
            display_name_cn="冲突画像",
            status="ready",
            profile_confidence=Decimal("0.80"),
            source_batch_ids_json=list(_batch_ids("TV")),
            release_status="published",
            is_current=True,
            input_fingerprint="conflicting-m12d-input",
            result_hash="conflicting-m12d-result",
        )
    )
    session.flush()
    with pytest.raises(CompetitorProfileSourceConflictError, match="M12D"):
        _provider(session).load_category_input_bundle(_request())


def test_conflicting_single_record_rows_are_not_resolved_by_batch_recency(
    session: Session,
) -> None:
    _seed_category(session)
    session.add(
        entities.Core3SkuParamProfile(
            project_id=_project_id("TV"),
            category_code="TV",
            batch_id="batch-tv-b",
            sku_code="TV000001",
            profile_hash="conflicting-m03-hash",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.flush()
    with pytest.raises(CompetitorProfileSourceConflictError, match="TV000001"):
        _provider(session).load_category_input_bundle(_request())


def test_empty_single_record_hash_is_rejected_before_materialization(
    session: Session,
) -> None:
    _seed_category(session)
    row = session.execute(
        select(entities.Core3SkuParamProfile).where(
            entities.Core3SkuParamProfile.sku_code == "TV000001"
        )
    ).scalar_one()
    row.profile_hash = ""
    session.flush()
    with pytest.raises(CompetitorProfileSourceConflictError, match="empty"):
        _provider(session).load_category_input_bundle(_request())


def test_wrong_taxonomy_and_noncurrent_rows_do_not_fill_optional_gap(
    session: Session,
) -> None:
    _seed_category(session, missing={("M04C", "TV000001")})
    session.add_all(
        [
            entities.Core3SkuClaimFactProfile(
                project_id=_project_id("TV"),
                category_code="TV",
                product_category="TV",
                batch_id="batch-tv-a",
                taxonomy_version="old-taxonomy",
                sku_code="TV000001",
                profile_hash="wrong-taxonomy",
                rule_version=CORE3_M04C_TV_RULE_VERSION,
                is_current=True,
            ),
            entities.Core3SkuClaimFactProfile(
                project_id=_project_id("TV"),
                category_code="TV",
                product_category="TV",
                batch_id="batch-tv-a",
                taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
                sku_code="TV000001",
                profile_hash="noncurrent-correct-taxonomy",
                rule_version=CORE3_M04C_TV_RULE_VERSION,
                is_current=False,
            ),
        ]
    )
    session.flush()
    bundle = _provider(session).load_category_input_bundle(_request())
    target = _provider(session).load_target_input(bundle, "TV000001")
    assert target.modules["M04C"].availability == "unknown"


def test_missing_whole_optional_source_authority_is_unknown(
    session: Session,
) -> None:
    _seed_category(
        session,
        missing={("M04C", "TV000001"), ("M04C", "TV000002")},
    )
    provider = _provider(session)
    bundle = provider.load_category_input_bundle(_request())

    assert bundle.modules["M04C"].record_count == 0
    assert bundle.modules["M04C"].authority.release_status == "unavailable"
    assert provider.load_target_input(bundle, "TV000001").modules[
        "M04C"
    ].availability == "unknown"


def test_evidence_identity_is_preserved_in_target_refs(
    session: Session,
) -> None:
    _seed_category(session)
    row = session.execute(
        select(entities.Core3M09cSkuUserTaskProfile).where(
            entities.Core3M09cSkuUserTaskProfile.sku_code == "TV000001"
        )
    ).scalar_one()
    row.evidence_ids_json = ["evidence-shared-1"]
    session.flush()

    provider = _provider(session)
    target = provider.load_target_input(
        provider.load_category_input_bundle(_request()),
        "TV000001",
    )
    ref = target.modules["M09C"].evidence_refs[0]
    assert ref.evidence_ids == ["evidence-shared-1"]


def test_target_outside_manifest_is_not_silently_resolved(session: Session) -> None:
    _seed_category(session)
    provider = _provider(session)
    bundle = provider.load_category_input_bundle(_request())
    with pytest.raises(CompetitorProfileTargetNotFoundError, match="outside"):
        provider.load_target_input(bundle, "TV999999")


def test_upstream_record_and_module_snapshot_reject_scope_and_shape_drift(
    session: Session,
) -> None:
    _seed_category(session)
    bundle = _provider(session).load_category_input_bundle(_request())
    module_payload = bundle.modules["M03B"].model_dump(mode="python")
    record_payload = module_payload["records_by_sku"]["TV000001"][0]

    wrong_category = dict(record_payload)
    wrong_category["product_category"] = "AC"
    with pytest.raises(ValidationError, match="category and product category"):
        UpstreamRecordSnapshot.model_validate(wrong_category)

    wrong_authority = dict(module_payload)
    wrong_authority["module_code"] = "M04C"
    with pytest.raises(ValidationError, match="authority must match"):
        ModuleCategorySnapshot.model_validate(wrong_authority)

    wrong_count = dict(module_payload)
    wrong_count["record_count"] += 1
    with pytest.raises(ValidationError, match="record count"):
        ModuleCategorySnapshot.model_validate(wrong_count)

    wrong_sku_count = dict(module_payload)
    wrong_sku_count["sku_count"] += 1
    with pytest.raises(ValidationError, match="SKU count"):
        ModuleCategorySnapshot.model_validate(wrong_sku_count)

    wrong_key = dict(module_payload)
    wrong_key["records_by_sku"] = {
        **module_payload["records_by_sku"],
        "TV999999": module_payload["records_by_sku"]["TV000001"],
    }
    wrong_key["records_by_sku"].pop("TV000001")
    with pytest.raises(ValidationError, match="inside their SKU key"):
        ModuleCategorySnapshot.model_validate(wrong_key)

    wrong_order = dict(module_payload)
    wrong_order["records_by_sku"] = dict(
        reversed(list(module_payload["records_by_sku"].items()))
    )
    with pytest.raises(ValidationError, match="SKU keys must be sorted"):
        ModuleCategorySnapshot.model_validate(wrong_order)

    wrong_record_order = dict(module_payload)
    wrong_record_order["records_by_sku"] = dict(module_payload["records_by_sku"])
    later_record = dict(record_payload)
    later_record["source_batch_id"] = "zz-batch"
    later_record["record_id"] = "zz-record"
    wrong_record_order["records_by_sku"]["TV000001"] = [
        later_record,
        record_payload,
    ]
    wrong_record_order["record_count"] += 1
    with pytest.raises(ValidationError, match="deterministic order"):
        ModuleCategorySnapshot.model_validate(wrong_record_order)


def test_category_bundle_rejects_manifest_and_authority_drift(session: Session) -> None:
    _seed_category(session)
    bundle = _provider(session).load_category_input_bundle(_request())
    payload = bundle.model_dump(mode="python")

    wrong_manifest = dict(payload)
    wrong_manifest["authoritative_sku_codes"] = list(
        reversed(payload["authoritative_sku_codes"])
    )
    with pytest.raises(ValidationError, match="manifest must be sorted"):
        CompetitorProfileCategoryInputBundle.model_validate(wrong_manifest)

    missing_module = dict(payload)
    missing_module["modules"] = dict(payload["modules"])
    missing_module["modules"].pop("M05C")
    with pytest.raises(ValidationError, match="all source modules"):
        CompetitorProfileCategoryInputBundle.model_validate(missing_module)

    wrong_module_key = dict(payload)
    wrong_module_key["modules"] = dict(payload["modules"])
    wrong_module_key["modules"]["M04C"], wrong_module_key["modules"]["M05C"] = (
        wrong_module_key["modules"]["M05C"],
        wrong_module_key["modules"]["M04C"],
    )
    with pytest.raises(ValidationError, match="dict key"):
        CompetitorProfileCategoryInputBundle.model_validate(wrong_module_key)

    missing_scope_authority = dict(payload)
    missing_scope_authority["serving_scope"] = dict(payload["serving_scope"])
    missing_scope_authority["serving_scope"]["source_authorities"] = dict(
        payload["serving_scope"]["source_authorities"]
    )
    missing_scope_authority["serving_scope"]["source_authorities"].pop("M05C")
    with pytest.raises(ValidationError, match="lock every source authority"):
        CompetitorProfileCategoryInputBundle.model_validate(missing_scope_authority)

    wrong_authority = dict(payload)
    wrong_authority["modules"] = dict(payload["modules"])
    wrong_authority["modules"]["M04C"] = dict(
        wrong_authority["modules"]["M04C"]
    )
    wrong_authority["modules"]["M04C"]["authority"] = dict(
        payload["modules"]["M04C"]["authority"]
    )
    wrong_authority["modules"]["M04C"]["authority"]["result_hash"] = (
        payload["modules"]["M05C"]["authority"]["result_hash"]
    )
    with pytest.raises(ValidationError, match="locked source authority"):
        CompetitorProfileCategoryInputBundle.model_validate(wrong_authority)


def test_target_input_schemas_reject_availability_and_state_contradictions(
    session: Session,
) -> None:
    _seed_category(session, missing={("M05C", "TV000001")})
    provider = _provider(session)
    category_bundle = provider.load_category_input_bundle(_request())
    target = provider.load_target_input(category_bundle, "TV000001")

    present_payload = target.modules["M03B"].model_dump(mode="python")
    present_payload["records"] = []
    with pytest.raises(ValidationError, match="present module inputs"):
        TargetModuleInput.model_validate(present_payload)

    unknown_payload = target.modules["M05C"].model_dump(mode="python")
    unknown_payload["missing_reason_code"] = None
    with pytest.raises(ValidationError, match="unknown module inputs"):
        TargetModuleInput.model_validate(unknown_payload)

    payload = target.model_dump(mode="python")
    blocked_without_reason = dict(payload)
    blocked_without_reason["analysis_state"] = "blocked"
    with pytest.raises(ValidationError, match="require hard-block reasons"):
        CompetitorProfileTargetInputBundle.model_validate(blocked_without_reason)

    partial_with_reason = dict(payload)
    partial_with_reason["hard_block_reasons"] = ["unexpected"]
    with pytest.raises(ValidationError, match="cannot carry hard-block reasons"):
        CompetitorProfileTargetInputBundle.model_validate(partial_with_reason)

    ready_with_limitation = dict(payload)
    ready_with_limitation["analysis_state"] = "ready"
    with pytest.raises(ValidationError, match="cannot carry missing-module limitations"):
        CompetitorProfileTargetInputBundle.model_validate(ready_with_limitation)

    missing_module = dict(payload)
    missing_module["modules"] = dict(payload["modules"])
    missing_module["modules"].pop("M05C")
    with pytest.raises(ValidationError, match="all source modules"):
        CompetitorProfileTargetInputBundle.model_validate(missing_module)
