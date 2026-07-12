from decimal import Decimal
from pathlib import Path

from app.core.database import SessionLocal
from app.services.core3_real_data.analyst.purchase_reason_profile_reader import (
    FixturePurchaseReasonProfileReader,
    PurchaseReasonProfileLookupKey,
    RepositoryPurchaseReasonProfileReader,
    decide_candidate_m12d_usage,
    decide_target_m12d_usage,
    default_m12d_contract_fixture_path,
)
from app.services.core3_real_data.constants import (
    CORE3_M12D_RULE_VERSION,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputStatus,
    M12DProfileStatus,
    M12DReleaseQualityStatus,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import (
    PurchaseReasonProfileRepository,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DDownstreamReadContract,
    M12DPurchaseReasonAnchorRecord,
    M12DPurchaseReasonProfileVersionRecord,
    M12DSkuPurchaseReasonProfileRecord,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


PROJECT_ID = "d8d2245b-358b-4a64-95cc-9d7f2341bd26"
BATCH_ID = "m00_20260623014631_c8630747"
M12D_VERSION = "m12d_tv_purchase_reason_profile_v0_1_draft"


def test_fixture_reader_reads_published_contract_and_marks_degraded_target(
    repo_root: Path,
) -> None:
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )

    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code=Core3CategoryCode.TV,
            batch_id=BATCH_ID,
            m12d_profile_version=M12D_VERSION,
            sku_code="TV00029112",
        )
    )

    assert contract.found is True
    assert contract.consumption_state == "published_degraded"
    assert contract.downstream_action == "degraded_pair_scoring"
    assert contract.profile is not None
    assert contract.profile.core_payment_anchors
    assert contract.profile.weak_expression_anchors

    decision = decide_target_m12d_usage(contract)
    assert decision.pair_scoring_allowed is True
    assert decision.strong_ranking_allowed is False
    assert decision.requires_review is True
    assert decision.confidence_state == "degraded"


def test_fixture_reader_blocks_target_when_profile_is_missing(repo_root: Path) -> None:
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )

    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            m12d_profile_version=M12D_VERSION,
            sku_code="TV_M12D_NOT_FOUND",
        )
    )

    decision = decide_target_m12d_usage(contract)
    assert contract.found is False
    assert decision.pair_scoring_allowed is False
    assert decision.strong_ranking_allowed is False
    assert decision.action == "block_strong_ranking"
    assert "待生成" in decision.message_cn


def test_fixture_reader_drops_candidate_when_profile_is_missing(
    repo_root: Path,
) -> None:
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )

    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code=Core3CategoryCode.TV,
            batch_id=BATCH_ID,
            m12d_profile_version=M12D_VERSION,
            sku_code="TV_UNKNOWN_CANDIDATE",
        )
    )

    decision = decide_candidate_m12d_usage(contract)
    assert contract.found is False
    assert decision.pair_scoring_allowed is False
    assert decision.top3_eligible is False
    assert decision.action == "drop_candidate_or_review"
    assert "不能依赖关键价值锚点进入 Top 3" in decision.message_cn


def test_reader_keeps_proposition_only_sku_in_other_dimensions() -> None:
    contract = M12DDownstreamReadContract(
        found=True,
        lookup_key={"category_code": "AC", "sku_code": "AC001"},
        consumption_state="published_degraded",
        downstream_action="degraded_pair_scoring",
        capabilities={
            "comparison_mode": "facts_only",
            "fact_dimensions_allowed": True,
            "proposition_comparison_allowed": True,
        },
    )

    target = decide_target_m12d_usage(contract)
    candidate = decide_candidate_m12d_usage(contract)

    assert target.action == "fact_dimensions_only"
    assert target.pair_scoring_allowed is False
    assert target.requires_review is False
    assert candidate.action == "fact_dimensions_only"
    assert candidate.pair_scoring_allowed is False
    assert candidate.top3_eligible is True


def test_fixture_reader_treats_unpublished_version_as_not_found(
    repo_root: Path,
) -> None:
    reader = FixturePurchaseReasonProfileReader.from_path(
        repo_root / default_m12d_contract_fixture_path()
    )

    contract = reader.read(
        PurchaseReasonProfileLookupKey(
            project_id=PROJECT_ID,
            category_code=Core3CategoryCode.TV,
            batch_id=BATCH_ID,
            m12d_profile_version=f"{M12D_VERSION}_unpublished_fixture",
            sku_code="TV00029112",
        )
    )

    decision = decide_target_m12d_usage(contract)
    assert contract.found is False
    assert contract.consumption_state == "not_found"
    assert decision.strong_ranking_allowed is False


def test_repository_reader_only_reads_published_m12d(client) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_competitor_m12d_reader",
                category_code=Core3CategoryCode.TV,
            )
        )
        repository.save_versions([_version_payload()])
        repository.save_profiles([_profile_payload()])
        repository.save_anchors([_anchor_payload()])

        reader = RepositoryPurchaseReasonProfileReader(session)
        lookup = PurchaseReasonProfileLookupKey(
            project_id="project_competitor_m12d_reader",
            category_code=Core3CategoryCode.TV,
            batch_id="batch_competitor_m12d_reader",
            m12d_profile_version="m12d_competitor_reader_v1",
            sku_code="TV_READER_001",
        )

        unpublished = reader.read(lookup)
        assert unpublished.found is False
        assert decide_target_m12d_usage(unpublished).strong_ranking_allowed is False

        repository.publish_version(
            batch_id="batch_competitor_m12d_reader",
            m12d_profile_version="m12d_competitor_reader_v1",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="competitor_reader_test",
        )

        published = reader.read(lookup)
        assert published.found is True
        assert published.consumption_state == "published_ready"
        assert published.profile is not None
        assert published.profile.core_payment_anchors == [
            "worth_paying_more_for_experience_upgrade"
        ]
        assert decide_candidate_m12d_usage(published).top3_eligible is True

        serving_scope = reader.read(
            PurchaseReasonProfileLookupKey(
                project_id="project_competitor_m12d_reader",
                category_code=Core3CategoryCode.TV,
                batch_id=(
                    "serving-scope:TV:batch_without_m12d,batch_competitor_m12d_reader"
                ),
                m12d_profile_version="m12d_competitor_reader_v1",
                sku_code="TV_READER_001",
            )
        )
        assert serving_scope.found is True
        assert serving_scope.profile is not None
        assert serving_scope.profile.batch_id == "batch_competitor_m12d_reader"
        assert serving_scope.lookup_key["batch_id"] == "batch_competitor_m12d_reader"
    finally:
        session.close()


def test_competitor_m12d_reader_does_not_import_m12d_runner(repo_root: Path) -> None:
    source = (
        repo_root
        / "apps/api-server/app/services/core3_real_data/analyst/purchase_reason_profile_reader.py"
    ).read_text(encoding="utf-8")

    assert "purchase_reason_profile_runner" not in source
    assert "PurchaseReasonProfileBatchGenerator" not in source


def _version_payload() -> M12DPurchaseReasonProfileVersionRecord:
    return M12DPurchaseReasonProfileVersionRecord(
        purchase_reason_version_id="version_competitor_reader_1",
        project_id="project_competitor_m12d_reader",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_competitor_m12d_reader",
        m12d_profile_version="m12d_competitor_reader_v1",
        release_quality_status=M12DReleaseQualityStatus.READY,
        source_batch_ids_json=["m00_fixture"],
        input_scope_json={"sku_count": 1},
        sku_count=1,
        ready_count=1,
        input_fingerprint="input_version_competitor_reader_1",
        result_hash="hash_version_competitor_reader_1",
    )


def _profile_payload() -> M12DSkuPurchaseReasonProfileRecord:
    return M12DSkuPurchaseReasonProfileRecord(
        purchase_reason_profile_id="profile_competitor_reader_1",
        purchase_reason_version_id="version_competitor_reader_1",
        project_id="project_competitor_m12d_reader",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_competitor_m12d_reader",
        m12d_profile_version="m12d_competitor_reader_v1",
        sku_code="TV_READER_001",
        brand_name="海信",
        model_name="Reader 65",
        display_name_cn="海信 Reader 65",
        status=M12DProfileStatus.READY,
        profile_confidence=Decimal("0.8200"),
        confidence_level=Core3ConfidenceLevel.HIGH,
        core_reasons_json=["贵得值的体验升级"],
        core_payment_anchors_json=["worth_paying_more_for_experience_upgrade"],
        param_profile_status=M12DInputStatus.READY,
        claim_fact_status=M12DInputStatus.READY,
        comment_profile_status=M12DInputStatus.READY,
        market_profile_status=M12DInputStatus.READY,
        semantic_profile_status=M12DInputStatus.READY,
        semantic_market_status=M12DInputStatus.READY,
        claim_value_status=M12DInputStatus.READY,
        source_batch_ids_json=["m00_fixture"],
        source_merge_strategy="unit_test",
        input_fingerprint="input_profile_competitor_reader_1",
        result_hash="hash_profile_competitor_reader_1",
    )


def _anchor_payload() -> M12DPurchaseReasonAnchorRecord:
    return M12DPurchaseReasonAnchorRecord(
        purchase_reason_anchor_id="anchor_competitor_reader_1",
        purchase_reason_profile_id="profile_competitor_reader_1",
        purchase_reason_version_id="version_competitor_reader_1",
        project_id="project_competitor_m12d_reader",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_competitor_m12d_reader",
        m12d_profile_version="m12d_competitor_reader_v1",
        sku_code="TV_READER_001",
        brand_name="海信",
        model_name="Reader 65",
        anchor_code="worth_paying_more_for_experience_upgrade",
        anchor_cn="贵得值的体验升级",
        anchor_family_code="experience_upgrade",
        anchor_rank=1,
        role=M12DAnchorRole.CORE_PAYMENT,
        evidence_strength=M12DEvidenceStrength.STRONG,
        confidence=Decimal("0.8500"),
        evidence_domains_json=[
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.CLAIM_VALUE,
        ],
        support_summary_cn="参数、卖点和 M12C 支付价值共同支撑贵得值的体验升级。",
        input_fingerprint="input_anchor_competitor_reader_1",
        result_hash="hash_anchor_competitor_reader_1",
    )
