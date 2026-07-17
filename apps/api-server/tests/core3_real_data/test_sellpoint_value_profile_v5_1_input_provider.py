from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

from app.cli import catforge_analyst
from app.cli.sellpoint_value_v5_1_batch import _chunks, _merge_scope_fragments
from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
    SELLPOINT_VALUE_PROFILE_RULE_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_competitor_adapter import (
    SellpointValueCompetitorReadResult,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_input_provider import (
    SavedV5SellpointValueV51InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    materialize_sellpoint_value_profile_v5_1,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    QuantificationLayer,
)
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_candidate_pools import (
    _source,
)


PROJECT_ID = "project-1"
BATCH_ID = "batch-1"
SOURCE_PROFILE_VERSION = "saved-v5"
TARGET_PROFILE_VERSION = "spv-v5-1-single"
TARGET_SKU_CODE = "TV-TARGET"


class SavedProfileRepository:
    def __init__(self, bundle: Any) -> None:
        self.bundle = bundle
        self.calls: list[dict[str, Any]] = []

    def get_saved_v5_generation_source(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.bundle


class FormalCompetitorAdapter:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def read(self, request: Any) -> SellpointValueCompetitorReadResult:
        self.requests.append(request)
        return SellpointValueCompetitorReadResult(
            status="available",
            source=_source(),
        )


class MultiSavedProfileRepository:
    def __init__(self, bundles: dict[str, Any]) -> None:
        self.bundles = bundles
        self.calls: list[dict[str, Any]] = []

    def get_saved_v5_generation_source(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.bundles.get(kwargs["sku_code"])


class PerSkuFormalCompetitorAdapter:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def read(self, request: Any) -> SellpointValueCompetitorReadResult:
        self.requests.append(request)
        source = _source().model_copy(
            update={
                "target_sku_code": request.target_sku_code,
                "target_market": _source().target_market.model_copy(
                    update={
                        "sku_code": request.target_sku_code,
                        "model_name": request.target_sku_code,
                    }
                ),
                "source_result_hash": f"profile-hash-{request.target_sku_code}",
            }
        )
        return SellpointValueCompetitorReadResult(
            status="available",
            source=source,
        )


def _candidate(sku_code: str, rank: int) -> SimpleNamespace:
    return SimpleNamespace(
        sku_sellpoint_value_candidate_id=f"saved-candidate-{rank}",
        batch_id=BATCH_ID,
        pool_type="reference",
        candidate_sku_code=sku_code,
        candidate_brand_name="参照品牌",
        candidate_model_name=f"参照型号{rank}",
        market_summary_json={
            "price_wavg": 5000 + rank * 100,
            "avg_weekly_sales_volume": 50 + rank,
            "screen_size_inch": 65,
        },
        result_hash=f"saved-reference-hash-{rank}",
    )


def _investment(
    capability_code: str,
    capability_name_cn: str,
    target_value: str,
) -> dict[str, Any]:
    return {
        "capability_code": capability_code,
        "capability_name_cn": capability_name_cn,
        "classification": "retain",
        "target_fact_status": "known_present",
        "target_value": target_value,
        "relative_experience_status": "better",
    }


def _value_item(
    *,
    index: int,
    value_bundle_code: str,
    value_bundle_name_cn: str,
    perceived_value_status: str,
    perceived_outcome_cn: str,
    capability_code: str,
    capability_name_cn: str,
    target_value: str,
    direct_comparators: list[str],
) -> SimpleNamespace:
    return SimpleNamespace(
        sku_sellpoint_value_item_id=f"saved-value-{index}",
        batch_id=BATCH_ID,
        battlefield_code=f"battlefield-{index}",
        battlefield_name_cn=f"价值战场{index}",
        purchase_reason_code=f"reason-{index}",
        purchase_reason_name_cn=f"采购理由{index}",
        value_bundle_code=value_bundle_code,
        value_bundle_name_cn=value_bundle_name_cn,
        normalized_bundle_code=f"normalized-{index}",
        perceived_outcome_cn=perceived_outcome_cn,
        perceived_value_status=perceived_value_status,
        capability_codes_json=[capability_code],
        question_result_refs_json=[
            {
                "source_question_code": "price_realization",
                "method": "same_budget_pool",
                "selected_candidate_ids": ["TV-C01", "TV-C02"],
            }
        ],
        price_realization_json={
            "realization_comparisons": (
                [
                    {
                        "method": "same_claim_different_realization",
                        "comparator_sku_codes": direct_comparators,
                    }
                ]
                if direct_comparators
                else []
            )
        },
        investment_decisions_json=[
            _investment(capability_code, capability_name_cn, target_value)
        ],
        evidence_boundary_cn="用户体验来自已保存评论事实，量价来自周均市场事实。",
        limitations_json=[],
        confidence=Decimal("0.8200"),
        result_hash=f"saved-value-hash-{index}",
    )


def _bundle() -> SimpleNamespace:
    version = SimpleNamespace(
        sellpoint_value_profile_version_id="saved-version-id",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        profile_version=SOURCE_PROFILE_VERSION,
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        method_version=SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        result_hash="saved-version-hash",
    )
    profile = SimpleNamespace(
        sku_sellpoint_value_profile_id="saved-profile-id",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        profile_version=SOURCE_PROFILE_VERSION,
        rule_version=SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        method_version=SELLPOINT_VALUE_PROFILE_METHOD_VERSION,
        sku_code=TARGET_SKU_CODE,
        model_code="65E7Q",
        model_name="65E7Q",
        brand_name="海信",
        display_name_cn="海信 65E7Q",
        result_hash="saved-profile-hash",
    )
    picture = _value_item(
        index=1,
        value_bundle_code="picture-upgrade",
        value_bundle_name_cn="高端画质升级",
        perceived_value_status="partial",
        perceived_outcome_cn="明亮客厅看得清，暗场层次更完整。",
        capability_code="tv_bright_room_dark_detail",
        capability_name_cn="明亮环境与明暗层次",
        target_value="5200nits / 1920分区",
        direct_comparators=["TV-C01"],
    )
    gaming = _value_item(
        index=2,
        value_bundle_code="gaming-fluency",
        value_bundle_name_cn="游戏流畅体验",
        perceived_value_status="not_observed",
        perceived_outcome_cn="游戏操作跟手，高速画面少拖影。",
        capability_code="tv_gaming_motion_fluency",
        capability_name_cn="游戏与运动流畅",
        target_value="高刷低延迟",
        direct_comparators=[],
    )
    return SimpleNamespace(
        version=version,
        profile=profile,
        candidates=[_candidate("TV-C01", 1), _candidate("TV-C02", 2)],
        value_items=[picture, gaming],
    )


def _bundle_for_sku(sku_code: str) -> SimpleNamespace:
    bundle = _bundle()
    profile_payload = vars(bundle.profile).copy()
    profile_payload.update(
        {
            "sku_sellpoint_value_profile_id": f"saved-profile-{sku_code}",
            "sku_code": sku_code,
            "model_code": sku_code,
            "model_name": sku_code,
            "display_name_cn": sku_code,
            "result_hash": f"saved-profile-hash-{sku_code}",
        }
    )
    return SimpleNamespace(
        version=bundle.version,
        profile=SimpleNamespace(**profile_payload),
        candidates=bundle.candidates,
        value_items=bundle.value_items,
    )


def test_saved_v5_provider_builds_one_formal_v5_1_graph() -> None:
    repository = SavedProfileRepository(_bundle())
    competitor_adapter = FormalCompetitorAdapter()
    provider = SavedV5SellpointValueV51InputProvider(
        repository=repository,
        competitor_adapter=competitor_adapter,
        source_profile_version=SOURCE_PROFILE_VERSION,
    )

    request = provider.build_version_request(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        profile_version=TARGET_PROFILE_VERSION,
        expected_sku_codes=[TARGET_SKU_CODE],
        generated_by="spv51-g15-test",
    )
    source = provider.load_materialization_input(request, TARGET_SKU_CODE)
    materialized = materialize_sellpoint_value_profile_v5_1(
        source,
        sellpoint_value_profile_version_id="v5-1-version-id",
    )

    assert repository.calls == [
        {
            "batch_id": BATCH_ID,
            "profile_version": SOURCE_PROFILE_VERSION,
            "sku_code": TARGET_SKU_CODE,
            "rule_version": SELLPOINT_VALUE_PROFILE_RULE_VERSION,
        }
    ]
    assert len(competitor_adapter.requests) == 1
    assert competitor_adapter.requests[0].access_mode == "formal"
    assert request.expected_sku_codes == [TARGET_SKU_CODE]
    assert request.competitor_source.release_status == "published"
    assert request.competitor_source.is_current is True
    assert len(source.candidate_pools.formal_competitors) == 5
    assert source.candidate_pools.priority_order == ["TV-C03", "TV-C01", "TV-C04"]
    assert len(source.candidate_pools.analysis_references) == 2
    assert len(source.candidate_pools.question_candidate_sets) > 1

    picture = next(
        row for row in source.values if row.value_bundle_code == "picture-upgrade"
    )
    gaming = next(
        row for row in source.values if row.value_bundle_code == "gaming-fluency"
    )
    assert {row.layer for row in picture.quantification_stack.results} == set(
        QuantificationLayer
    )
    assert len(picture.direct_market_results) == 1
    assert picture.direct_market_results[0].used_comparator_sku_codes == ["TV-C01"]
    assert picture.direct_market_results[0].price_comparison is not None
    assert picture.direct_market_results[0].sales_comparison is not None
    assert len(picture.parameter_group_results) == 1
    assert picture.parameter_group_results[0].status == "no_conclusion"
    assert len(picture.market_archetype_results) == 1
    assert picture.strict_market_implied_wtp is not None
    assert picture.strict_market_implied_wtp.status == "no_conclusion"
    assert picture.investment_decisions[0].classification == "retain"
    assert picture.investment_reviews[0].review_required is False

    assert gaming.direct_market_results == []
    assert gaming.market_archetype_results == []
    assert gaming.investment_decisions[0].classification == "unconverted"
    assert gaming.investment_decisions[0].review_required is False
    assert gaming.value_conclusion.status == "partial_conclusion"
    assert source.sku_conclusion.consumer_status == "usable_conclusion"
    assert materialized.profile.result_hash
    assert materialized.profile.input_fingerprint
    assert materialized.persistence_bundle.profile.release_status == "draft"
    assert materialized.persistence_bundle.profile.is_current is False


def test_multi_sku_request_freezes_light_scope_and_retains_one_graph() -> None:
    sku_codes = ["TV-A", "TV-B"]
    repository = MultiSavedProfileRepository(
        {sku_code: _bundle_for_sku(sku_code) for sku_code in sku_codes}
    )
    competitor_adapter = PerSkuFormalCompetitorAdapter()
    provider = SavedV5SellpointValueV51InputProvider(
        repository=repository,
        competitor_adapter=competitor_adapter,
        source_profile_version=SOURCE_PROFILE_VERSION,
    )

    request = provider.build_version_request(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        profile_version="spv-v5-1-full",
        expected_sku_codes=sku_codes,
        generated_by="spv51-g17-test",
    )

    assert request.expected_sku_codes == sku_codes
    assert set(request.candidate_pool_hashes) == set(sku_codes)
    assert provider._cache == {}
    assert len(repository.calls) == 2
    assert len(competitor_adapter.requests) == 2

    first = provider.load_materialization_input(request, "TV-A")
    assert first.target.sku_code == "TV-A"
    assert list(provider._cache) == [("spv-v5-1-full", BATCH_ID, "TV-A")]

    second = provider.load_materialization_input(request, "TV-B")
    assert second.target.sku_code == "TV-B"
    assert list(provider._cache) == [("spv-v5-1-full", BATCH_ID, "TV-B")]
    assert len(repository.calls) == 4
    assert len(competitor_adapter.requests) == 4


def test_batch_scope_fragments_merge_into_one_authoritative_version() -> None:
    fragments = []
    for sku_code in ("TV-A", "TV-B"):
        provider = SavedV5SellpointValueV51InputProvider(
            repository=MultiSavedProfileRepository(
                {sku_code: _bundle_for_sku(sku_code)}
            ),
            competitor_adapter=PerSkuFormalCompetitorAdapter(),
            source_profile_version=SOURCE_PROFILE_VERSION,
        )
        fragments.append(
            provider.build_version_request(
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                profile_version="spv-v5-1-full",
                expected_sku_codes=[sku_code],
                generated_by="spv51-g17-test",
            ).model_dump(mode="json")
        )

    request = _merge_scope_fragments(fragments)

    assert request.expected_sku_codes == ["TV-A", "TV-B"]
    assert set(request.candidate_pool_hashes) == {"TV-A", "TV-B"}
    assert _chunks(request.expected_sku_codes, 1) == [["TV-A"], ["TV-B"]]
    with pytest.raises(ValueError, match="duplicate SKU"):
        _merge_scope_fragments([fragments[0], fragments[0]])


def test_v5_1_cli_requires_explicit_single_draft_write(capsys: Any) -> None:
    result = catforge_analyst.main(
        [
            "sellpoint-value-profile-v5-1-generate",
            "--project-id",
            PROJECT_ID,
            "--category-code",
            "TV",
            "--batch-id",
            BATCH_ID,
            "--sku-code",
            TARGET_SKU_CODE,
            "--profile-version",
            TARGET_PROFILE_VERSION,
            "--source-profile-version",
            SOURCE_PROFILE_VERSION,
            "--generated-by",
            "spv51-g15-test",
        ]
    )

    payload = capsys.readouterr().out
    assert result == 1
    assert "画像草稿写入默认关闭" in payload
