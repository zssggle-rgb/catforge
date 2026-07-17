from __future__ import annotations

import ast
from decimal import Decimal
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    sellpoint_value_profile_v5_1_candidate_pools as candidate_pools_module,
)

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueReferenceManifestItem,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_candidate_pools import (
    QUESTION_ORDER,
    build_sellpoint_value_candidate_pools,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_COMPETITOR_FACT_GROUPS,
    CompetitorProfileCandidateRef,
    CompetitorProfilePairFacts,
    CompetitorProfileSkuMarketFacts,
    QuestionCandidateSet,
    SellpointValueCandidatePools,
    SellpointValueCompetitorSource,
)


def _pair_facts(*, unavailable: tuple[str, ...] = ()) -> CompetitorProfilePairFacts:
    values: dict[str, Any] = {
        group: {"source": group} for group in SPV_V5_1_COMPETITOR_FACT_GROUPS
    }
    values["ranking_gate_reasons"] = []
    values["shared_business_context"] = []
    unavailable_set = set(unavailable)
    return CompetitorProfilePairFacts(
        **values,
        available_fact_groups=[
            group
            for group in SPV_V5_1_COMPETITOR_FACT_GROUPS
            if group not in unavailable_set
        ],
        unavailable_fact_groups=[
            group
            for group in SPV_V5_1_COMPETITOR_FACT_GROUPS
            if group in unavailable_set
        ],
    )


def _candidate(
    rank: int,
    *,
    selected_rank: int | None = None,
    brand_name: str = "竞品品牌",
    price: Decimal | None = Decimal("5000"),
    weekly_sales: Decimal | None = Decimal("50"),
    unavailable: tuple[str, ...] = (),
) -> CompetitorProfileCandidateRef:
    sku_code = f"TV-C{rank:02d}"
    return CompetitorProfileCandidateRef(
        candidate_sku_code=sku_code,
        source_rank=rank,
        selected_rank=selected_rank,
        role="primary_direct" if selected_rank == 1 else "market_reference",
        role_cn="核心正面竞争" if selected_rank == 1 else "市场竞争参照",
        business_score=Decimal("0.8"),
        pair_result_hash=f"pair-hash-{rank}",
        market=CompetitorProfileSkuMarketFacts(
            sku_code=sku_code,
            brand_name=brand_name,
            model_name=f"型号{rank}",
            product_category="TV",
            size_tier="65",
            weighted_price=price,
            avg_weekly_sales_volume=weekly_sales,
        ),
        pair_facts=_pair_facts(unavailable=unavailable),
    )


def _source() -> SellpointValueCompetitorSource:
    candidates = [
        _candidate(1, selected_rank=2),
        _candidate(2, unavailable=("parameter_claim_overlap",)),
        _candidate(3, selected_rank=1, weekly_sales=None),
        _candidate(4, selected_rank=3, brand_name="海信"),
        _candidate(5, price=None),
    ]
    return SellpointValueCompetitorSource(
        source="competitor_profile_agent_snapshot_v2",
        access_mode="formal",
        competitor_profile_version_id="cp-version-1",
        profile_version="cp-profile-v1",
        method_version="competitor_profile_agent_snapshot_v2",
        release_status="published",
        is_current=True,
        project_id="project-1",
        category_code="TV",
        release_scope_key="project-1:TV:agent",
        target_sku_code="TV-TARGET",
        target_market=CompetitorProfileSkuMarketFacts(
            sku_code="TV-TARGET",
            brand_name="海信",
            model_name="65E7Q",
            product_category="TV",
            size_tier="65",
            weighted_price=Decimal("6000"),
            avg_weekly_sales_volume=Decimal("40"),
        ),
        candidates=candidates,
        priority_order=["TV-C03", "TV-C01", "TV-C04"],
        source_version_result_hash="version-hash-1",
        source_result_hash="profile-hash-1",
    )


def _references() -> list[dict[str, Any] | SellpointValueReferenceManifestItem]:
    return [
        SellpointValueReferenceManifestItem(
            reference_sku_code="TV-C02",
            brand_name="竞品品牌",
            model_name="型号2",
            reference_purposes=["same_size_market"],
            also_competitor=True,
            market_summary={
                "price_wavg": 5100,
                "avg_weekly_sales_volume": 52,
                "screen_size_inch": 65,
            },
            source_hashes={"M07": "market-hash-c02"},
        ),
        {
            "reference_sku_code": "TV-R-PARAM",
            "brand_name": "参数参照品牌",
            "model_name": "参数参照",
            "reference_purposes": ["parameter_group"],
            "market_summary": {
                "price_wavg": 5500,
                "avg_weekly_sales_volume": 60,
            },
            "parameter_facts": {},
            "source_hashes": {"M04C": "param-hash"},
        },
        {
            "reference_sku_code": "TV-R-BATTLEFIELD",
            "brand_name": "战场参照品牌",
            "model_name": "战场参照",
            "reference_purposes": ["battlefield_benchmark"],
            "market_summary": {
                "price_wavg": 6200,
                "avg_weekly_sales_volume": 80,
            },
            "battlefield_facts": {},
            "value_facts": {},
            "source_hashes": {"M11C": "battlefield-hash"},
        },
        {
            "reference_sku_code": "TV-R-LADDER",
            "brand_name": "海信",
            "model_name": "同品牌梯度参照",
            "reference_purposes": ["same_brand_size_ladder"],
            "market_summary": {
                "price_wavg": 7000,
                "avg_weekly_sales_volume": 30,
            },
        },
    ]


def _build(
    references: list[dict[str, Any] | SellpointValueReferenceManifestItem]
    | None = None,
) -> SellpointValueCandidatePools:
    return build_sellpoint_value_candidate_pools(
        competitor_source=_source(),
        analysis_reference_records=references
        if references is not None
        else _references(),
    )


def _question(
    pools: SellpointValueCandidatePools,
    question_code: str,
) -> QuestionCandidateSet:
    return next(
        row
        for row in pools.question_candidate_sets
        if row.question_code == question_code
    )


def _use(
    question: QuestionCandidateSet,
    sku_code: str,
    source_type: str = "competitor",
):
    return next(
        row
        for row in question.candidate_uses
        if row.candidate_sku_code == sku_code and row.source_type == source_type
    )


def test_formal_pool_preserves_every_saved_candidate_and_top3_is_only_a_label() -> None:
    pools = _build()

    assert [row.candidate_sku_code for row in pools.formal_competitors] == [
        "TV-C01",
        "TV-C02",
        "TV-C03",
        "TV-C04",
        "TV-C05",
    ]
    assert pools.priority_order == ["TV-C03", "TV-C01", "TV-C04"]
    price_question = _question(pools, "current_price_support")
    assert _use(price_question, "TV-C02").selected is True
    assert _use(price_question, "TV-C02").priority_rank is None
    assert _use(price_question, "TV-C01").priority_rank == 2


def test_same_sku_can_keep_separate_competitor_and_market_reference_identities() -> (
    None
):
    pools = _build()
    reference = next(
        row for row in pools.analysis_references if row.reference_sku_code == "TV-C02"
    )
    price_question = _question(pools, "current_price_support")
    duplicated_code_uses = [
        row
        for row in price_question.candidate_uses
        if row.candidate_sku_code == "TV-C02"
    ]

    assert reference.also_competitor is True
    assert {row.source_type.value for row in duplicated_code_uses} == {
        "competitor",
        "market_reference",
    }
    assert all(row.selected for row in duplicated_code_uses)


def test_missing_parameter_fact_only_rejects_parameter_questions() -> None:
    pools = _build()

    configuration = _use(_question(pools, "configuration_follow"), "TV-C02")
    parameter_conversion = _use(_question(pools, "parameter_conversion"), "TV-C02")
    price = _use(_question(pools, "current_price_support"), "TV-C02")
    scale = _use(_question(pools, "scale_conversion"), "TV-C02")
    specific = _use(_question(pools, "specific_competitor"), "TV-C02")

    assert configuration.selected is False
    assert configuration.unavailable_dimensions == ["parameter_claim_overlap"]
    assert parameter_conversion.selected is False
    assert price.selected is True
    assert scale.selected is True
    assert specific.selected is True
    assert "review_required" not in json.dumps(pools.model_dump(mode="json"))


def test_missing_sales_only_rejects_scale_but_keeps_other_questions_available() -> None:
    pools = _build()

    scale = _use(_question(pools, "scale_conversion"), "TV-C03")
    price = _use(_question(pools, "current_price_support"), "TV-C03")
    value = _use(_question(pools, "value_relative_advantage"), "TV-C03")

    assert scale.selected is False
    assert scale.rejection_reasons == ["missing_required_dimension:weekly_sales"]
    assert price.selected is True
    assert value.selected is True


def test_explicit_empty_saved_fact_group_remains_usable_for_its_question() -> None:
    source = _source()
    candidate = source.candidates[0]
    facts_payload = candidate.pair_facts.model_dump(mode="python")
    facts_payload["parameter_claim_overlap"] = {}
    candidate = candidate.model_copy(
        update={"pair_facts": CompetitorProfilePairFacts.model_validate(facts_payload)}
    )
    source = source.model_copy(
        update={"candidates": [candidate, *source.candidates[1:]]}
    )

    pools = build_sellpoint_value_candidate_pools(competitor_source=source)
    use = _use(_question(pools, "configuration_follow"), "TV-C01")

    assert use.selected is True
    assert use.usable_dimensions == ["parameter_claim_overlap"]


def test_reference_purpose_and_direct_facts_jointly_control_each_question() -> None:
    pools = _build()
    parameter = next(
        row
        for row in pools.analysis_references
        if row.reference_sku_code == "TV-R-PARAM"
    )
    battlefield = next(
        row
        for row in pools.analysis_references
        if row.reference_sku_code == "TV-R-BATTLEFIELD"
    )

    assert parameter.parameter_facts == {}
    assert (
        _use(
            _question(pools, "configuration_follow"),
            "TV-R-PARAM",
            "market_reference",
        ).selected
        is True
    )
    assert (
        _use(
            _question(pools, "parameter_conversion"),
            "TV-R-PARAM",
            "market_reference",
        ).selected
        is True
    )
    assert (
        _use(
            _question(pools, "specific_competitor"),
            "TV-R-PARAM",
            "market_reference",
        ).selected
        is False
    )
    assert battlefield.battlefield_facts == {}
    assert (
        _use(
            _question(pools, "value_relative_advantage"),
            "TV-R-BATTLEFIELD",
            "market_reference",
        ).selected
        is True
    )
    assert (
        _use(
            _question(pools, "battlefield_expansion"),
            "TV-R-BATTLEFIELD",
            "market_reference",
        ).selected
        is True
    )


def test_same_brand_ladder_is_reference_only_and_requires_same_brand_facts() -> None:
    pools = _build()

    ladder = _use(
        _question(pools, "same_brand_role"),
        "TV-R-LADDER",
        "market_reference",
    )
    other_brand = _use(_question(pools, "same_brand_role"), "TV-C01")
    same_brand_competitor = _use(_question(pools, "same_brand_role"), "TV-C04")

    assert ladder.selected is True
    assert other_brand.selected is False
    assert "not_same_brand_as_target" in other_brand.rejection_reasons
    assert same_brand_competitor.selected is True


def test_every_question_audits_every_row_without_global_candidate_filtering() -> None:
    pools = _build()
    expected_rows = len(pools.formal_competitors) + len(pools.analysis_references)

    assert [row.question_code for row in pools.question_candidate_sets] == list(
        QUESTION_ORDER
    )
    assert all(
        len(row.candidate_uses) == expected_rows
        for row in pools.question_candidate_sets
    )


def test_pool_contract_rejects_a_question_that_drops_one_candidate() -> None:
    pools = _build()
    payload = pools.model_dump(mode="python")
    payload["question_candidate_sets"][0]["candidate_uses"].pop()

    with pytest.raises(
        ValidationError,
        match="each question must assess every pool member",
    ):
        SellpointValueCandidatePools.model_validate(payload)
    assert all(
        use.selection_reasons if use.selected else use.rejection_reasons
        for question in pools.question_candidate_sets
        for use in question.candidate_uses
    )


def test_reference_order_and_duplicate_purpose_rows_do_not_change_result_hash() -> None:
    references = _references()
    duplicate = {
        "reference_sku_code": "TV-R-PARAM",
        "brand_name": "参数参照品牌",
        "model_name": "参数参照",
        "reference_purposes": ["same_size_market"],
        "market_summary": {
            "price_wavg": 5500,
            "avg_weekly_sales_volume": 60,
        },
        "source_hashes": {"M07": "parameter-market-hash"},
    }

    first = _build([*references, duplicate])
    second = _build([duplicate, *reversed(references)])

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.result_hash == second.result_hash
    parameter = next(
        row
        for row in first.analysis_references
        if row.reference_sku_code == "TV-R-PARAM"
    )
    assert [purpose.value for purpose in parameter.purposes] == [
        "parameter_group",
        "same_size_market",
    ]


def test_duplicate_reference_purposes_merge_complementary_market_facts() -> None:
    pools = _build(
        [
            {
                "reference_sku_code": "TV-R-MERGED",
                "reference_purposes": ["same_size_market"],
                "market_summary": {"price_wavg": 5300},
            },
            {
                "reference_sku_code": "TV-R-MERGED",
                "reference_purposes": ["performance_archetype"],
                "market_summary": {"avg_weekly_sales_volume": 70},
            },
        ]
    )
    reference = pools.analysis_references[0]

    assert reference.market.weighted_price == Decimal("5300")
    assert reference.market.avg_weekly_sales_volume == Decimal("70")
    assert (
        _use(
            _question(pools, "current_price_support"),
            "TV-R-MERGED",
            "market_reference",
        ).selected
        is True
    )
    assert (
        _use(
            _question(pools, "scale_conversion"),
            "TV-R-MERGED",
            "market_reference",
        ).selected
        is True
    )


def test_cross_category_market_reference_is_rejected_at_the_pool_boundary() -> None:
    with pytest.raises(ValueError, match="crossed.*category"):
        _build(
            [
                {
                    "reference_sku_code": "AC-R01",
                    "category_code": "AC",
                    "reference_purposes": ["same_size_market"],
                }
            ]
        )


def test_ac_source_and_references_keep_the_same_category_isolation_contract() -> None:
    payload = _source().model_dump(mode="python")
    payload["category_code"] = "AC"
    payload["release_scope_key"] = "project-1:AC:agent"
    payload["target_sku_code"] = "AC-TARGET"
    payload["target_market"]["sku_code"] = "AC-TARGET"
    payload["target_market"]["product_category"] = "AC"
    for candidate in payload["candidates"]:
        rank = candidate["source_rank"]
        candidate["candidate_sku_code"] = f"AC-C{rank:02d}"
        candidate["market"]["sku_code"] = f"AC-C{rank:02d}"
        candidate["market"]["product_category"] = "AC"
    payload["priority_order"] = [
        row["candidate_sku_code"]
        for row in sorted(
            (row for row in payload["candidates"] if row["selected_rank"] is not None),
            key=lambda row: row["selected_rank"],
        )
    ]
    source = SellpointValueCompetitorSource.model_validate(payload)

    pools = build_sellpoint_value_candidate_pools(
        competitor_source=source,
        analysis_reference_records=[
            {
                "reference_sku_code": "AC-R01",
                "category_code": "AC",
                "reference_purposes": ["same_size_market"],
                "market_summary": {
                    "price_wavg": 4000,
                    "avg_weekly_sales_volume": 35,
                },
            }
        ],
    )

    assert pools.category_code == "AC"
    assert all(row.market.product_category == "AC" for row in pools.formal_competitors)
    assert pools.analysis_references[0].market.product_category == "AC"


def test_candidate_pool_module_does_not_reintroduce_legacy_competitor_readers() -> None:
    tree = ast.parse(Path(candidate_pools_module.__file__).read_text(encoding="utf-8"))
    imports = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imports.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    source = Path(candidate_pools_module.__file__).read_text(encoding="utf-8")

    assert all(
        "sellpoint_value_profile_candidate_service" not in row for row in imports
    )
    assert all(
        "sellpoint_value_profile_candidate_repositories" not in row for row in imports
    )
    assert "CORE3_M12_RULE_VERSION" not in source
    assert "CORE3_M13_RULE_VERSION" not in source
    assert "CORE3_M14_RULE_VERSION" not in source
