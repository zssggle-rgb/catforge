from decimal import Decimal
from types import SimpleNamespace

from app.services.core3_real_data.sku_business_profile_service import (
    CLAIM_INFERENCE_SOURCE_MODULE,
    DimensionDraft,
    _battlefield_drafts_from_portfolio,
    _dimension_drafts,
    _rank_dimensions,
    _remap_persisted_dimension_ids,
    _remap_persisted_profile_ids,
    _select_allocatable_battlefield_rows,
    _select_allocatable_task_rows,
)
from app.services.core3_real_data.sku_business_profile_schemas import (
    M116BuildArtifacts,
    M116SkuBusinessProfileDimensionRecord,
    M116SkuBusinessProfileRecord,
    M116SkuBusinessProfileReviewIssueRecord,
    M116SkuBusinessProfileSalesAllocationRecord,
)


def test_m116_infers_low_confidence_claims_when_m115_layer_is_missing():
    bundle = SimpleNamespace(
        profile=SimpleNamespace(
            sku_signal_profile_id="m08p_test",
            claim_activation_summary_json={
                "top_claims": [
                    {
                        "claim_code_hint": "CLAIM_HIGH_REFRESH_RATE",
                        "claim_name": "高刷新率",
                        "activation_basis": "param_only",
                        "final_activation_score": Decimal("0.3734"),
                        "perception_status": "insufficient_comment",
                        "confidence": Decimal("0.4332"),
                    },
                    {
                        "claim_code_hint": "CLAIM_VALUE_FOR_MONEY",
                        "claim_name": "高性价比",
                        "activation_basis": "comment_enhanced",
                        "final_activation_score": Decimal("0.1758"),
                        "perception_status": "validated",
                        "confidence": Decimal("0.5802"),
                    },
                    {
                        "claim_code_hint": "CLAIM_OLED_SELF_LIT",
                        "claim_name": "OLED 自发光",
                        "activation_basis": "param_only",
                        "final_activation_score": Decimal("0.2712"),
                        "perception_status": "insufficient_comment",
                        "confidence": Decimal("0.3974"),
                    },
                ]
            },
            representative_evidence_ids=["evidence_from_profile"],
        ),
        task_scores=(),
        target_group_scores=(),
        battlefield_scores=(),
        claim_value_layers=(),
    )

    ranked = _rank_dimensions(_dimension_drafts(bundle))
    claim_drafts = [draft for draft in ranked if draft.dimension_type == "claim"]

    assert {draft.code for draft in claim_drafts} == {"CLAIM_HIGH_REFRESH_RATE", "CLAIM_VALUE_FOR_MONEY"}
    assert all(draft.source_module == CLAIM_INFERENCE_SOURCE_MODULE for draft in claim_drafts)
    assert {draft.value_layer for draft in claim_drafts} == {"param_inferred", "comment_inferred"}
    assert sum(draft.normalized_weight for draft in claim_drafts) == Decimal("1.000000")
    assert all("低置信卖点维度" in draft.business_reason_cn for draft in claim_drafts)


def test_m116_dedupes_dimension_codes_before_weight_normalization():
    ranked = _rank_dimensions(
        [
            DimensionDraft(
                dimension_type="task",
                code="TASK_GAMING",
                name="游戏娱乐",
                score=Decimal("0.8000"),
                confidence=Decimal("0.7000"),
                relation_level="primary",
                value_layer=None,
                source_module="M09",
                source_record_refs=({"table": "core3_sku_task_score", "id": "old"},),
                support_breakdown={"source": "old"},
                evidence_ids=("ev1",),
                business_reason_cn="旧版本任务候选。",
            ),
            DimensionDraft(
                dimension_type="task",
                code="TASK_GAMING",
                name="游戏娱乐",
                score=Decimal("0.9000"),
                confidence=Decimal("0.8000"),
                relation_level="primary",
                value_layer=None,
                source_module="M09",
                source_record_refs=({"table": "core3_sku_task_score", "id": "new"},),
                support_breakdown={"source": "new"},
                evidence_ids=("ev2",),
                business_reason_cn="新版本任务候选。",
            ),
            DimensionDraft(
                dimension_type="task",
                code="TASK_MOVIE",
                name="家庭观影",
                score=Decimal("0.6000"),
                confidence=Decimal("0.7000"),
                relation_level="secondary",
                value_layer=None,
                source_module="M09",
                source_record_refs=({"table": "core3_sku_task_score", "id": "movie"},),
                support_breakdown={},
                evidence_ids=("ev3",),
                business_reason_cn="家庭观影候选。",
            ),
        ]
    )
    task_drafts = [draft for draft in ranked if draft.dimension_type == "task"]

    assert [draft.code for draft in task_drafts] == ["TASK_GAMING", "TASK_MOVIE"]
    assert sum(draft.normalized_weight for draft in task_drafts) == Decimal("1.000000")
    assert task_drafts[0].score == Decimal("0.9000")
    assert task_drafts[0].support_breakdown["duplicate_count"] == 2
    assert {ref["id"] for ref in task_drafts[0].source_record_refs} == {"old", "new"}
    assert set(task_drafts[0].evidence_ids) == {"ev1", "ev2"}


def test_m116_allocates_only_qualified_dimensions_and_limits_width():
    rows = [
        SimpleNamespace(task_score=Decimal("0.91"), relation_level="main", task_code="TASK_1"),
        SimpleNamespace(task_score=Decimal("0.86"), relation_level="secondary", task_code="TASK_2"),
        SimpleNamespace(task_score=Decimal("0.82"), relation_level="secondary", task_code="TASK_3"),
        SimpleNamespace(task_score=Decimal("0.78"), relation_level="secondary", task_code="TASK_4"),
        SimpleNamespace(task_score=Decimal("0.70"), relation_level="weak", task_code="TASK_5"),
    ]

    selected = _select_allocatable_task_rows(rows)

    assert [row.task_code for row in selected] == ["TASK_1", "TASK_2", "TASK_3"]


def test_m116_allocates_single_fallback_when_no_strong_dimension_exists():
    rows = [
        SimpleNamespace(task_score=Decimal("0.58"), relation_level="weak", task_code="TASK_WEAK_TOP"),
        SimpleNamespace(task_score=Decimal("0.51"), relation_level="weak", task_code="TASK_WEAK_SECOND"),
        SimpleNamespace(task_score=Decimal("0.62"), relation_level="insufficient", task_code="TASK_INSUFFICIENT"),
    ]

    selected = _select_allocatable_task_rows(rows)

    assert [row.task_code for row in selected] == ["TASK_WEAK_TOP"]


def test_m116_does_not_allocate_service_assurance_as_product_battlefield():
    rows = [
        SimpleNamespace(battlefield_score=Decimal("0.95"), relation_level="main", battlefield_code="BF_SERVICE_ASSURANCE"),
        SimpleNamespace(battlefield_score=Decimal("0.61"), relation_level="secondary", battlefield_code="BF_GAMING_SPORTS"),
    ]

    selected = _select_allocatable_battlefield_rows(rows)

    assert [row.battlefield_code for row in selected] == ["BF_GAMING_SPORTS"]


def test_m116_uses_m11_portfolio_weights_for_battlefield_allocation():
    score_rows = (
        SimpleNamespace(
            battlefield_code="BF_GAMING_SPORTS",
            battlefield_name_cn="游戏体育流畅战场",
            battlefield_score=Decimal("0.8100"),
            confidence=Decimal("0.7600"),
            relation_level="main",
            sku_battlefield_score_id="score-game",
            score_breakdown_json={"formula_version": "m11_battlefield_v2_size_price_pool"},
            evidence_ids=("ev-game",),
            business_reason_cn="游戏体育锚点最强。",
        ),
        SimpleNamespace(
            battlefield_code="BF_FAMILY_VIEWING_UPGRADE",
            battlefield_name_cn="家庭观影舒适战场",
            battlefield_score=Decimal("0.6200"),
            confidence=Decimal("0.7000"),
            relation_level="secondary",
            sku_battlefield_score_id="score-family",
            score_breakdown_json={},
            evidence_ids=("ev-family",),
            business_reason_cn="家庭观影为辅助战场。",
        ),
    )
    bundle = SimpleNamespace(
        battlefield_scores=score_rows,
        battlefield_portfolio=SimpleNamespace(
            sku_battlefield_portfolio_id="portfolio-1",
            main_battlefields_json=[
                {
                    "battlefield_code": "BF_GAMING_SPORTS",
                    "battlefield_name_cn": "游戏体育流畅战场",
                    "battlefield_score": 0.81,
                    "confidence": 0.76,
                    "allocation_weight": 0.62,
                    "allocation_eligible": True,
                    "allocation_role": "main_battlefield",
                    "market_pool_key": "tv:large_upgrade:online:full",
                    "product_anchor_score": 0.52,
                }
            ],
            secondary_battlefields_json=[
                {
                    "battlefield_code": "BF_FAMILY_VIEWING_UPGRADE",
                    "battlefield_name_cn": "家庭观影舒适战场",
                    "battlefield_score": 0.62,
                    "confidence": 0.70,
                    "allocation_weight": 0.38,
                    "allocation_eligible": True,
                    "allocation_role": "secondary_battlefield",
                }
            ],
        ),
    )

    ranked = _rank_dimensions(_battlefield_drafts_from_portfolio(bundle))

    assert [draft.code for draft in ranked] == ["BF_GAMING_SPORTS", "BF_FAMILY_VIEWING_UPGRADE"]
    assert [draft.relation_level for draft in ranked] == ["main", "secondary"]
    assert [draft.normalized_weight for draft in ranked] == [Decimal("0.620000"), Decimal("0.380000")]
    assert ranked[0].support_breakdown["allocation_policy"] == "m11_v2_portfolio"
    assert ranked[0].support_breakdown["market_pool_key"] == "tv:large_upgrade:online:full"


def test_m116_remaps_child_foreign_keys_to_persisted_profile_and_dimension_ids():
    artifacts = M116BuildArtifacts(
        profiles=(
            M116SkuBusinessProfileRecord.model_construct(
                sku_business_profile_id="generated-profile-id",
                batch_id="batch-1",
                sku_code="TV900001",
                rule_version="rule-v1",
            ),
        ),
        dimensions=(
            M116SkuBusinessProfileDimensionRecord.model_construct(
                profile_dimension_id="generated-dimension-id",
                sku_business_profile_id="generated-profile-id",
                batch_id="batch-1",
                sku_code="TV900001",
                dimension_type="battlefield",
                dimension_code="BF_GAMING_SPORTS",
                rule_version="rule-v1",
            ),
        ),
        allocations=(
            M116SkuBusinessProfileSalesAllocationRecord.model_construct(
                sales_allocation_id="allocation-id",
                sku_business_profile_id="generated-profile-id",
                profile_dimension_id="generated-dimension-id",
                batch_id="batch-1",
                sku_code="TV900001",
                dimension_type="battlefield",
                dimension_code="BF_GAMING_SPORTS",
                rule_version="rule-v1",
            ),
        ),
        review_issues=(
            M116SkuBusinessProfileReviewIssueRecord.model_construct(
                sku_business_profile_review_issue_id="issue-id",
                sku_business_profile_id="generated-profile-id",
                profile_dimension_id="generated-dimension-id",
                batch_id="batch-1",
                sku_code="TV900001",
                dimension_type="battlefield",
                dimension_code="BF_GAMING_SPORTS",
                issue_type="weak_dimension_evidence",
                rule_version="rule-v1",
            ),
        ),
    )
    persisted_profile = SimpleNamespace(
        sku_business_profile_id="persisted-profile-id",
        batch_id="batch-1",
        sku_code="TV900001",
        rule_version="rule-v1",
    )
    persisted_dimension = SimpleNamespace(
        profile_dimension_id="persisted-dimension-id",
        batch_id="batch-1",
        sku_code="TV900001",
        dimension_type="battlefield",
        dimension_code="BF_GAMING_SPORTS",
        rule_version="rule-v1",
    )

    remapped = _remap_persisted_profile_ids(artifacts, (persisted_profile,))
    remapped = _remap_persisted_dimension_ids(remapped, (persisted_dimension,))

    assert remapped.profiles[0].sku_business_profile_id == "persisted-profile-id"
    assert remapped.dimensions[0].sku_business_profile_id == "persisted-profile-id"
    assert remapped.dimensions[0].profile_dimension_id == "persisted-dimension-id"
    assert remapped.allocations[0].sku_business_profile_id == "persisted-profile-id"
    assert remapped.allocations[0].profile_dimension_id == "persisted-dimension-id"
    assert remapped.review_issues[0].sku_business_profile_id == "persisted-profile-id"
    assert remapped.review_issues[0].profile_dimension_id == "persisted-dimension-id"
