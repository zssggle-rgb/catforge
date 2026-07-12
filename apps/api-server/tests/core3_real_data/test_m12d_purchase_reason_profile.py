from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.cli import catforge_analyst
from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
    CORE3_M12D_RULE_VERSION,
    CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
    CORE3_M03B_AC_RULE_VERSION,
    CORE3_M03B_RULE_VERSION,
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
    Core3CategoryCode,
    Core3RunStatus,
    M12DAnchorRole,
    M12DEvidenceDomain,
    M12DEvidenceStrength,
    M12DInputAvailability,
    M12DInputStatus,
    M12DInputUsability,
    M12DIssueScope,
    M12DIssueSeverity,
    M12DProfileStatus,
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
    M12DReleaseQualityStatus,
    M12DReleaseStatus,
)
from app.services.core3_real_data.purchase_reason_anchor_candidate_generator import (
    AnchorCandidateGenerator,
    M12DAnchorCandidateGenerationError,
)
from app.services.core3_real_data.purchase_reason_anchor_taxonomy import (
    M12DAnchorTaxonomyLoader,
    M12DAnchorTaxonomyNotFoundError,
)
from app.services.core3_real_data.purchase_reason_context_builder import (
    SkuPurchaseReasonContextBuilder,
)
from app.services.core3_real_data.purchase_reason_profile_contract import (
    get_downstream_read_contract,
)
from app.services.core3_real_data.purchase_reason_profile_repositories import (
    M12DReleaseQualityNotPublishableError,
    PurchaseReasonProfileRepository,
)
from app.services.core3_real_data.purchase_reason_profile_runner import (
    PurchaseReasonProfileBatchGenerator,
)
from app.services.core3_real_data.purchase_reason_profile_scoring import (
    ProfileConfidenceScorer,
    PurchaseReasonProfileScoringService,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidateSet,
    M12DInputQuality,
    M12DInputQualityIssue,
    M12DInputSnapshot,
    M12DPurchaseReasonAnchorRecord,
    M12DPurchaseReasonProfileVersionRecord,
    M12DScoredPurchaseReasonAnchor,
    M12DSkuPurchaseReasonProfileRecord,
    M12DSkuPurchaseReasonContext,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


def test_m12d_profile_schema_validates_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        M12DPurchaseReasonAnchorRecord(
            purchase_reason_anchor_id="anchor_bad",
            project_id="project_m12d_schema",
            category_code=Core3CategoryCode.TV,
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v1",
            sku_code="TV00029112",
            anchor_code="worth_paying_more_for_experience_upgrade",
            anchor_cn="贵得值的体验升级",
            role=M12DAnchorRole.CORE_PAYMENT,
            evidence_strength=M12DEvidenceStrength.STRONG,
            confidence=Decimal("1.2000"),
            evidence_domains_json=[M12DEvidenceDomain.PARAM_FACT],
            support_summary_cn="MiniLED 和高亮参数支撑高端画质。",
            input_fingerprint="input_fp",
            result_hash="result_hash",
        )


def test_m12d_repository_only_reads_published_current_version(client) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_publish",
                category_code=Core3CategoryCode.TV,
            )
        )
        repository.save_versions([_version_payload("version_1", "m12d_v1", "hash_v1")])
        profile_result = repository.save_profiles(
            [_profile_payload("profile_1", "version_1", "m12d_v1", "hash_profile_v1")]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_1", "profile_1", "version_1", "m12d_v1", "hash_anchor_v1"
                )
            ]
        )

        assert profile_result.created_count == 1
        assert (
            repository.get_published_profile(
                batch_id="batch_m12d", sku_code="TV00029112"
            )
            is None
        )

        repository.publish_version(
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v1",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="tester",
        )
        published = repository.get_published_profile(
            batch_id="batch_m12d", sku_code="TV00029112"
        )
        assert published is not None
        assert published.version.m12d_profile_version == "m12d_v1"
        assert published.profile.release_status == M12DReleaseStatus.PUBLISHED.value
        assert [anchor.anchor_code for anchor in published.anchors] == [
            "worth_paying_more_for_experience_upgrade"
        ]

        repository.save_versions(
            [
                _version_payload(
                    "version_2",
                    "m12d_v2",
                    "hash_v2",
                    release_quality_status=M12DReleaseQualityStatus.BLOCKED,
                )
            ]
        )
        repository.save_profiles(
            [_profile_payload("profile_2", "version_2", "m12d_v2", "hash_profile_v2")]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_2", "profile_2", "version_2", "m12d_v2", "hash_anchor_v2"
                )
            ]
        )

        assert (
            repository.get_published_profile(
                batch_id="batch_m12d",
                sku_code="TV00029112",
                m12d_profile_version="m12d_v2",
            )
            is None
        )
        with pytest.raises(M12DReleaseQualityNotPublishableError):
            repository.publish_version(
                batch_id="batch_m12d",
                m12d_profile_version="m12d_v2",
                rule_version=CORE3_M12D_RULE_VERSION,
                published_by="tester",
            )
        current = repository.get_published_profile(
            batch_id="batch_m12d", sku_code="TV00029112"
        )
        assert current is not None
        assert current.version.m12d_profile_version == "m12d_v1"

        repository.save_versions([_version_payload("version_3", "m12d_v3", "hash_v3")])
        repository.save_profiles(
            [_profile_payload("profile_3", "version_3", "m12d_v3", "hash_profile_v3")]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_3", "profile_3", "version_3", "m12d_v3", "hash_anchor_v3"
                )
            ]
        )
        repository.publish_version(
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v3",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="tester",
        )

        old_profile = session.get(entities.Core3SkuPurchaseReasonProfile, "profile_1")
        old_anchor = session.get(entities.Core3SkuPurchaseReasonAnchor, "anchor_1")
        new_profile = session.get(entities.Core3SkuPurchaseReasonProfile, "profile_3")
        new_anchor = session.get(entities.Core3SkuPurchaseReasonAnchor, "anchor_3")
        assert old_profile is not None and old_profile.is_current is False
        assert old_anchor is not None and old_anchor.is_current is False
        assert new_profile is not None and new_profile.is_current is True
        assert new_anchor is not None and new_anchor.is_current is True

        version_rows = list(
            session.execute(
                select(entities.Core3PurchaseReasonProfileVersion)
            ).scalars()
        )
        assert len(version_rows) == 3
    finally:
        session.close()


@pytest.mark.parametrize(
    "quality_status",
    [M12DReleaseQualityStatus.UNASSESSED, M12DReleaseQualityStatus.BLOCKED],
)
def test_m12d_repository_rejects_unassessed_and_blocked_versions(
    client,
    quality_status: M12DReleaseQualityStatus,
) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_publish",
                category_code=Core3CategoryCode.TV,
            )
        )
        repository.save_versions(
            [
                _version_payload(
                    f"version_{quality_status.value}",
                    f"m12d_v_{quality_status.value}",
                    f"hash_{quality_status.value}",
                    release_quality_status=quality_status,
                )
            ]
        )

        with pytest.raises(
            M12DReleaseQualityNotPublishableError, match=quality_status.value
        ):
            repository.publish_version(
                batch_id="batch_m12d",
                m12d_profile_version=f"m12d_v_{quality_status.value}",
                rule_version=CORE3_M12D_RULE_VERSION,
                published_by="tester",
            )
    finally:
        session.close()


def test_m12d_repository_hides_legacy_blocked_current_version(client) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_publish",
                category_code=Core3CategoryCode.TV,
            )
        )
        version_payload = _version_payload(
            "version_blocked_current",
            "m12d_v_blocked_current",
            "hash_blocked_current",
            release_quality_status=M12DReleaseQualityStatus.BLOCKED,
        )
        repository.save_versions([version_payload])
        repository.save_profiles(
            [
                _profile_payload(
                    "profile_blocked_current",
                    "version_blocked_current",
                    "m12d_v_blocked_current",
                    "hash_profile_blocked_current",
                )
            ]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_blocked_current",
                    "profile_blocked_current",
                    "version_blocked_current",
                    "m12d_v_blocked_current",
                    "hash_anchor_blocked_current",
                )
            ]
        )
        version = session.get(
            entities.Core3PurchaseReasonProfileVersion,
            "version_blocked_current",
        )
        profile = session.get(
            entities.Core3SkuPurchaseReasonProfile,
            "profile_blocked_current",
        )
        anchor = session.get(
            entities.Core3SkuPurchaseReasonAnchor,
            "anchor_blocked_current",
        )
        version.release_status = M12DReleaseStatus.PUBLISHED.value
        version.is_current = True
        profile.release_status = M12DReleaseStatus.PUBLISHED.value
        profile.is_current = True
        anchor.release_status = M12DReleaseStatus.PUBLISHED.value
        anchor.is_current = True
        session.flush()

        assert (
            repository.get_published_profile(
                batch_id="batch_m12d",
                sku_code="TV00029112",
            )
            is None
        )
    finally:
        session.close()


def test_m12d_legacy_published_unassessed_version_keeps_existing_consumption(
    client,
) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_publish",
                category_code=Core3CategoryCode.TV,
            )
        )
        repository.save_versions(
            [
                _version_payload(
                    "version_legacy_unassessed",
                    "m12d_v_legacy_unassessed",
                    "hash_legacy_unassessed",
                    release_quality_status=M12DReleaseQualityStatus.UNASSESSED,
                )
            ]
        )
        repository.save_profiles(
            [
                _profile_payload(
                    "profile_legacy_unassessed",
                    "version_legacy_unassessed",
                    "m12d_v_legacy_unassessed",
                    "hash_profile_legacy_unassessed",
                )
            ]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_legacy_unassessed",
                    "profile_legacy_unassessed",
                    "version_legacy_unassessed",
                    "m12d_v_legacy_unassessed",
                    "hash_anchor_legacy_unassessed",
                )
            ]
        )
        version = session.get(
            entities.Core3PurchaseReasonProfileVersion,
            "version_legacy_unassessed",
        )
        profile = session.get(
            entities.Core3SkuPurchaseReasonProfile,
            "profile_legacy_unassessed",
        )
        anchor = session.get(
            entities.Core3SkuPurchaseReasonAnchor,
            "anchor_legacy_unassessed",
        )
        version.release_status = M12DReleaseStatus.PUBLISHED.value
        version.is_current = True
        profile.release_status = M12DReleaseStatus.PUBLISHED.value
        profile.is_current = True
        anchor.release_status = M12DReleaseStatus.PUBLISHED.value
        anchor.is_current = True
        session.flush()

        contract = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d",
            sku_code="TV00029112",
        )

        assert (
            contract.release_quality_status == M12DReleaseQualityStatus.UNASSESSED.value
        )
        assert contract.consumption_state == "published_ready"
        assert contract.downstream_action == "normal_pair_scoring"
    finally:
        session.close()


def test_m12d_limited_version_requires_human_approval_but_keeps_ready_sku(
    client,
) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_publish",
                category_code=Core3CategoryCode.TV,
            )
        )
        repository.save_versions(
            [
                _version_payload(
                    "version_limited",
                    "m12d_v_limited",
                    "hash_limited",
                    release_quality_status=M12DReleaseQualityStatus.LIMITED,
                )
            ]
        )
        repository.save_profiles(
            [
                _profile_payload(
                    "profile_limited",
                    "version_limited",
                    "m12d_v_limited",
                    "hash_profile_limited",
                )
            ]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_limited",
                    "profile_limited",
                    "version_limited",
                    "m12d_v_limited",
                    "hash_anchor_limited",
                )
            ]
        )

        with pytest.raises(
            M12DReleaseQualityNotPublishableError, match="allow_limited"
        ):
            repository.publish_version(
                batch_id="batch_m12d",
                m12d_profile_version="m12d_v_limited",
                rule_version=CORE3_M12D_RULE_VERSION,
                published_by="tester",
            )
        with pytest.raises(M12DReleaseQualityNotPublishableError, match="non-system"):
            repository.publish_version(
                batch_id="batch_m12d",
                m12d_profile_version="m12d_v_limited",
                rule_version=CORE3_M12D_RULE_VERSION,
                allow_limited=True,
            )

        repository.publish_version(
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v_limited",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="product_owner",
            allow_limited=True,
        )
        contract = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d",
            sku_code="TV00029112",
        )

        assert contract.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
        assert contract.consumption_state == "published_ready"
        assert contract.downstream_action == "normal_pair_scoring"
        assert contract.profile is not None
        assert contract.capabilities.strong_reason_comparison_allowed is True
        assert contract.version_quality_notes
        assert (
            "release_quality_status_limited" not in contract.profile.degradation_reasons
        )
    finally:
        session.close()


def test_m12d_repository_reuses_existing_profile_when_hash_unchanged(client) -> None:
    session = SessionLocal()
    try:
        repository = PurchaseReasonProfileRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_reuse",
                category_code=Core3CategoryCode.TV,
            )
        )
        base_payload = _profile_payload(
            "profile_reuse", "version_reuse", "m12d_reuse", "same_hash"
        )
        first = repository.save_profiles([base_payload])
        base_payload_dict = base_payload.model_dump(mode="python")
        second = repository.save_profiles(
            [{**base_payload_dict, "display_name_cn": "海信 65E7Q 更新显示名"}]
        )
        third = repository.save_profiles(
            [
                {
                    **base_payload_dict,
                    "result_hash": "new_hash",
                    "display_name_cn": "海信 65E7Q 新画像",
                }
            ]
        )

        rows = list(
            session.execute(select(entities.Core3SkuPurchaseReasonProfile)).scalars()
        )
        assert first.created_count == 1
        assert second.reused_count == 1
        assert third.updated_count == 1
        assert len(rows) == 1
        assert rows[0].purchase_reason_profile_id == "profile_reuse"
        assert rows[0].display_name_cn == "海信 65E7Q 新画像"
    finally:
        session.close()


def test_m12d_downstream_contract_requires_publish_and_freezes_degradation(
    client,
) -> None:
    session = SessionLocal()
    try:
        repository_context = Core3RepositoryContext(
            db=session,
            project_id="project_m12d_publish",
            category_code=Core3CategoryCode.TV,
        )
        repository = PurchaseReasonProfileRepository(repository_context)
        repository.save_versions(
            [
                _version_payload(
                    "version_contract_1", "m12d_v_contract_1", "hash_contract_1"
                )
            ]
        )
        repository.save_profiles(
            [
                _profile_payload(
                    "profile_contract_1",
                    "version_contract_1",
                    "m12d_v_contract_1",
                    "hash_profile_contract_1",
                )
            ]
        )
        repository.save_anchors(
            [
                _anchor_payload(
                    "anchor_contract_1",
                    "profile_contract_1",
                    "version_contract_1",
                    "m12d_v_contract_1",
                    "hash_anchor_contract_1",
                )
            ]
        )

        unpublished = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d",
            sku_code="TV00029112",
            m12d_profile_version="m12d_v_contract_1",
        )
        assert unpublished.found is False
        assert unpublished.consumption_state == "not_found"
        assert unpublished.downstream_action == "block_target_or_drop_candidate"

        repository.publish_version(
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v_contract_1",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="tester",
        )
        published = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d",
            sku_code="TV00029112",
            m12d_profile_version="m12d_v_contract_1",
        )
        assert published.found is True
        assert published.release_quality_status == M12DReleaseQualityStatus.READY.value
        assert published.consumption_state == "published_ready"
        assert published.downstream_action == "normal_pair_scoring"
        assert published.profile is not None
        assert published.profile.core_payment_anchors == [
            "worth_paying_more_for_experience_upgrade"
        ]
        assert (
            published.profile.anchors[0].anchor_code
            == "worth_paying_more_for_experience_upgrade"
        )

        degraded_payload = _profile_payload(
            "profile_contract_2",
            "version_contract_2",
            "m12d_v_contract_2",
            "hash_profile_contract_2",
        ).model_copy(
            update={
                "status": M12DProfileStatus.READY_DEGRADED,
                "profile_confidence": Decimal("0.3000"),
                "confidence_level": "low",
                "core_reasons_json": [],
                "core_payment_anchors_json": [],
                "supporting_anchors_json": [],
                "review_required": True,
                "review_status": "review_required",
                "review_reason_json": {
                    "reasons": ["low_profile_confidence", "core_payment_missing"]
                },
            }
        )
        repository.save_versions(
            [
                _version_payload(
                    "version_contract_2", "m12d_v_contract_2", "hash_contract_2"
                )
            ]
        )
        repository.save_profiles([degraded_payload])
        repository.publish_version(
            batch_id="batch_m12d",
            m12d_profile_version="m12d_v_contract_2",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="tester",
        )
        degraded = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d",
            sku_code="TV00029112",
            m12d_profile_version="m12d_v_contract_2",
        )
        assert degraded.found is True
        assert degraded.consumption_state == "published_degraded"
        assert degraded.downstream_action == "degraded_pair_scoring"
        assert degraded.profile is not None
        assert {"low_profile_confidence", "core_payment_missing"} <= set(
            degraded.profile.degradation_reasons
        )
    finally:
        session.close()


def test_m12d_context_builder_assembles_65e7q_input_snapshots(client) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(batch_id="batch_m12d_context", sku_code="TV00029112")

        assert context.display_name_cn == "海信 65E7Q"
        assert context.param_profile_status == M12DInputStatus.READY.value
        assert context.claim_fact_status == M12DInputStatus.READY.value
        assert context.comment_profile_status == M12DInputStatus.READY.value
        assert context.market_profile_status == M12DInputStatus.READY.value
        assert context.semantic_profile_status == M12DInputStatus.READY.value
        assert context.semantic_market_status == M12DInputStatus.READY.value
        assert context.claim_value_status == M12DInputStatus.READY.value
        assert set(context.input_quality_json) == {
            "M03B",
            "M04C",
            "M05C",
            "M07",
            "M09C_M10C_M11C",
            "M11D",
            "M12C",
        }
        comment_issues = context.input_quality_json["M05C"].issues
        contradiction = next(
            issue
            for issue in comment_issues
            if issue.code == "comment_claim_contradiction"
        )
        assert contradiction.scope == "anchor"
        assert "gaming_device_fit_reduces_risk" in contradiction.affected_anchor_codes
        assert context.param_profile.summary["unknown_param_count"] == 5
        assert context.claim_fact_profile.summary["fact_claim_count"] == 2
        assert (
            context.claim_value_profile.summary["claim_value_roles"][
                "tv_claim_miniled_display"
            ]
            == "premium_driver_estimated"
        )
        assert context.claim_value_profile.summary["anchor_claim_value_roles"][
            "picture_upgrade_justifies_price"
        ]["tv_claim_miniled_display"] == ["premium_driver_estimated"]
        assert context.missing_input_reasons_json == []
        assert context.input_fingerprint
        assert {ref.module_code for ref in context.source_refs_json} >= {
            "M03B",
            "M04C",
            "M05C",
            "M07",
            "M09C_M10C_M11C",
            "M11D",
            "M12C",
        }
    finally:
        session.close()


def test_m12d_context_builder_reads_serving_scope_batch_ids(client) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(
            batch_id="serving-scope:TV:missing_batch,batch_m12d_context",
            sku_code="TV00029112",
        )

        assert context.display_name_cn == "海信 65E7Q"
        assert context.param_profile_status == M12DInputStatus.READY.value
        assert context.claim_fact_status == M12DInputStatus.READY.value
        assert context.claim_value_status == M12DInputStatus.READY.value
        assert context.source_refs_json[0].module_code == "M03B"
    finally:
        session.close()


def test_m12d_context_builder_preserves_missing_m12c_as_missing_not_false(
    client,
) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=False)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(batch_id="batch_m12d_context", sku_code="TV00029112")

        assert context.claim_value_status == M12DInputStatus.MISSING.value
        assert context.claim_value_profile.record_count == 0
        assert context.claim_value_profile.summary == {}
        assert context.input_status_json["claim_value_status"] == "missing"
        assert any("M12C" in reason for reason in context.missing_input_reasons_json)
        assert context.param_profile_status == M12DInputStatus.READY.value
    finally:
        session.close()


def test_m12d_tv_anchor_taxonomy_is_standard_and_category_scoped() -> None:
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category="TV",
    )

    assert len(taxonomy.value_themes) == 7
    assert len(taxonomy.purchase_reasons) == 13
    assert "两层结构" in taxonomy.source_note_cn
    assert "picture_upgrade_perception" in taxonomy.value_themes_by_code()
    assert (
        "worth_paying_more_for_experience_upgrade"
        in taxonomy.purchase_reasons_by_code()
    )
    with pytest.raises(M12DAnchorTaxonomyNotFoundError):
        M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            product_category="AC",
        )


def test_m12d_ac_anchor_taxonomy_is_standard_and_category_scoped() -> None:
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )

    assert taxonomy.product_category == "AC"
    assert len(taxonomy.value_themes) == 9
    assert len(taxonomy.purchase_reasons) == 13
    assert "G01 上游证据审计" in taxonomy.source_note_cn
    assert "cooling_heating_capacity_assurance" in taxonomy.value_themes_by_code()
    assert (
        "long_term_energy_saving_offsets_price" in taxonomy.purchase_reasons_by_code()
    )
    assert "picture_upgrade_perception" not in taxonomy.value_themes_by_code()
    assert "gaming_device_fit_reduces_risk" not in taxonomy.purchase_reasons_by_code()
    with pytest.raises(M12DAnchorTaxonomyNotFoundError):
        M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
            product_category="TV",
        )
    with pytest.raises(M12DAnchorTaxonomyNotFoundError):
        M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            product_category="AC",
        )


def test_m12d_anchor_candidate_generator_matches_standard_tv_anchors(client) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(batch_id="batch_m12d_context", sku_code="TV00029112")
        taxonomy = M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            product_category="TV",
        )

        candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)
        themes_by_code = {
            candidate.anchor_code: candidate
            for candidate in candidate_set.value_theme_candidates
        }
        reasons_by_code = {
            candidate.anchor_code: candidate
            for candidate in candidate_set.purchase_reason_candidates
        }

        assert {
            "picture_upgrade_perception",
            "dynamic_stability_perception",
            "operation_convenience_perception",
            "budget_configuration_efficiency",
        } <= set(themes_by_code)
        assert {
            "picture_upgrade_justifies_price",
            "worth_paying_more_for_experience_upgrade",
        } <= set(reasons_by_code)
        assert (
            themes_by_code["picture_upgrade_perception"].candidate_type == "value_theme"
        )
        assert (
            reasons_by_code["worth_paying_more_for_experience_upgrade"].candidate_type
            == "purchase_reason"
        )
        assert (
            M12DEvidenceDomain.CLAIM_VALUE.value
            in themes_by_code["picture_upgrade_perception"].evidence_domains_json
        )
        assert (
            "贵得值"
            in reasons_by_code["worth_paying_more_for_experience_upgrade"].anchor_cn
        )
        assert (
            "多花的钱"
            in reasons_by_code[
                "worth_paying_more_for_experience_upgrade"
            ].decision_question_cn
        )
        assert reasons_by_code[
            "worth_paying_more_for_experience_upgrade"
        ].related_value_theme_codes == [
            "picture_upgrade_perception",
            "dynamic_stability_perception",
            "living_room_immersion_perception",
        ]
        assert (
            themes_by_code["budget_configuration_efficiency"].role_cap
            == M12DAnchorRole.WEAK_EXPRESSION.value
        )
        assert themes_by_code["budget_configuration_efficiency"].role_cap_reasons == [
            "only_weak_expression_sources"
        ]
        assert all(
            match.weak_expression_only
            for match in themes_by_code[
                "budget_configuration_efficiency"
            ].evidence_matches
        )

        high_refresh_matches = [
            match
            for match in themes_by_code["dynamic_stability_perception"].evidence_matches
            if match.module_code == "M04C"
            and match.match_key == "tv_claim_high_refresh"
        ]
        assert len(high_refresh_matches) == 1
    finally:
        session.close()


def test_m12d_anchor_candidate_generator_matches_standard_ac_anchors() -> None:
    context = _manual_ac_m12d_context(
        param_summary={
            "param_values_json": {
                "installation_type": "柜机",
                "capacity_hp": "3匹",
                "cooling_capacity": 7200,
                "heating_capacity": 9600,
                "air_volume": 1300,
                "apf": 5.2,
                "energy_efficiency_level": "一级能效",
                "noise_db": 18,
                "fresh_air_volume": 60,
                "anti_direct_blow": True,
                "self_clean": True,
                "wifi": True,
            }
        },
        claim_summary={
            "fact_claim_codes": [
                "temperature_performance",
                "energy_efficiency",
                "airflow_comfort",
                "health_clean_air",
                "smart_control",
                "durability_quality",
            ],
            "dimension_profile_json": {
                "temperature_performance": {"fact_claim_count": 2},
                "energy_efficiency": {"fact_claim_count": 1},
                "airflow_comfort": {"fact_claim_count": 2},
                "health_clean_air": {"fact_claim_count": 1},
                "smart_control": {"fact_claim_count": 1},
                "durability_quality": {"fact_claim_count": 1},
            },
            "claim_summary_json": {
                "keywords": ["速冷", "一级能效", "新风", "防直吹", "自清洁", "远程"]
            },
        },
        comment_summary={
            "dimension_summary_json": {
                "temperature_performance": {"positive": 8},
                "energy_efficiency": {"positive": 3},
                "airflow_comfort": {"positive": 5},
                "health_clean_air": {"positive": 2},
            },
            "signal_summary_json": {
                "use_case_signal": ["客厅大空间", "卧室睡眠", "老人儿童"]
            },
            "evidence_examples_json": [
                {"text": "客厅制冷快，风感柔和不直吹，晚上睡觉也安静。"},
                {"text": "一级能效省电，新风打开后不闷，远程控制方便。"},
            ],
        },
        market_summary={
            "price_band_category": "mid_high",
            "price_band_size": "high",
            "same_pool_volume_percentile": "high",
            "sales_volume_total": 120000,
        },
        semantic_summary={
            "user_task": [
                "large_space",
                "bedroom_sleep",
                "elderly_child",
                "seasonal_reliability",
            ],
            "target_group": ["family", "elderly_child"],
            "battlefield": [
                "BF_COOLING_HEATING_CAPACITY",
                "BF_HEALTH_CLEAN_AIR",
                "BF_OPERATION_CONVENIENCE",
            ],
        },
        claim_value_summary={
            "claim_value_roles": ["sales_driver_estimated"],
            "positive_claims_json": [
                "temperature_performance",
                "energy_efficiency",
                "health_clean_air",
                "smart_control",
            ],
        },
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )

    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)
    themes_by_code = {
        candidate.anchor_code: candidate
        for candidate in candidate_set.value_theme_candidates
    }
    reasons_by_code = {
        candidate.anchor_code: candidate
        for candidate in candidate_set.purchase_reason_candidates
    }

    assert candidate_set.product_category == "AC"
    assert {
        "cooling_heating_capacity_assurance",
        "energy_cost_efficiency",
        "sleep_quiet_comfort",
        "comfortable_airflow_health",
        "large_space_coverage",
        "operation_maintenance_convenience",
    } <= set(themes_by_code)
    assert {
        "cooling_heating_performance_justifies_price",
        "long_term_energy_saving_offsets_price",
        "sleep_room_quiet_comfort_assurance",
        "fresh_air_health_reduces_stuffy_risk",
        "smart_remote_control_less_friction",
    } <= set(reasons_by_code)
    assert "picture_upgrade_perception" not in themes_by_code
    assert "gaming_device_fit_reduces_risk" not in reasons_by_code
    assert reasons_by_code[
        "long_term_energy_saving_offsets_price"
    ].related_value_theme_codes == [
        "energy_cost_efficiency",
        "budget_configuration_efficiency",
    ]
    assert (
        M12DEvidenceDomain.PARAM_FACT.value
        in reasons_by_code[
            "long_term_energy_saving_offsets_price"
        ].evidence_domains_json
    )
    assert (
        M12DEvidenceDomain.CLAIM_VALUE.value
        in reasons_by_code["fresh_air_health_reduces_stuffy_risk"].evidence_domains_json
    )

    tv_context = _manual_m12d_context(
        claim_summary={}, claim_status=M12DInputStatus.MISSING
    )
    with pytest.raises(
        M12DAnchorCandidateGenerationError, match="taxonomy .* is for AC"
    ):
        AnchorCandidateGenerator(taxonomy).generate(tv_context)


def test_m12d_ac_candidate_generator_caps_single_energy_claim_as_weak_expression() -> (
    None
):
    context = _manual_ac_m12d_context(
        claim_summary={
            "fact_claim_codes": ["energy_efficiency"],
            "claim_codes": ["energy_efficiency"],
            "dimension_profile_json": {"energy_efficiency": {"fact_claim_count": 1}},
            "claim_summary_json": {"keywords": ["一级能效"]},
        },
        claim_status=M12DInputStatus.READY,
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )

    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)
    reasons_by_code = {
        candidate.anchor_code: candidate
        for candidate in candidate_set.purchase_reason_candidates
    }
    candidate = reasons_by_code["long_term_energy_saving_offsets_price"]

    assert candidate.role_cap == M12DAnchorRole.WEAK_EXPRESSION.value
    assert candidate.role_cap_reasons == ["only_weak_expression_sources"]
    assert all(match.weak_expression_only for match in candidate.evidence_matches)
    assert candidate.weak_boundary_cn == "只有一级能效口号时封顶弱表达。"


def test_m12d_ac_reason_scoring_promotes_multi_domain_reason_to_core_payment() -> None:
    context = _rich_ac_m12d_context()
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}
    anchor = by_code["cooling_heating_performance_justifies_price"]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert anchor.evidence_strength == M12DEvidenceStrength.STRONG.value
    assert anchor.role_reason_json["strong_domain_count"] >= 2
    assert anchor.role_reason_json["ac_core_block_flags"] == []
    assert (
        "cooling_heating_performance_justifies_price"
        in result.core_payment_anchors_json
    )


def test_m12d_ac_reason_scoring_ignores_legacy_partial_without_scoped_issue() -> None:
    context = _rich_ac_m12d_context()
    context.claim_value_status = M12DInputStatus.PARTIAL.value
    context.semantic_profile_status = M12DInputStatus.PARTIAL.value
    context.semantic_market_status = M12DInputStatus.PARTIAL.value
    context.market_profile_status = M12DInputStatus.PARTIAL.value
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}
    anchor = by_code["cooling_heating_performance_justifies_price"]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert "missing_or_partial_inputs" not in anchor.risk_flags_json
    assert anchor.conflict_penalty == Decimal("0.0000")
    assert anchor.role_reason_json["ac_core_block_flags"] == []
    assert (
        "cooling_heating_performance_justifies_price"
        in result.core_payment_anchors_json
    )


def test_m12d_anchor_scoring_info_issue_has_zero_business_impact() -> None:
    context = _rich_ac_m12d_context()
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)
    baseline = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set,
        context=context,
    )
    _attach_input_quality_issue(
        context,
        module_code="M12C",
        code="m12c_amount_not_quantifiable",
        severity=M12DIssueSeverity.INFO,
        affected_anchor_codes=["cooling_heating_performance_justifies_price"],
    )

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    before = {anchor.anchor_code: anchor for anchor in baseline.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]
    after = {anchor.anchor_code: anchor for anchor in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert (after.adjusted_evidence_score, after.confidence, after.role) == (
        before.adjusted_evidence_score,
        before.confidence,
        before.role,
    )
    assert after.risk_flags_json == before.risk_flags_json


def test_m12d_anchor_scoring_unmatched_warning_has_zero_business_impact() -> None:
    context = _rich_ac_m12d_context()
    _attach_input_quality_issue(
        context,
        module_code="M05C",
        code="comment_claim_contradiction",
        severity=M12DIssueSeverity.WARNING,
        affected_anchor_codes=["smart_remote_control_less_friction"],
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "long_term_energy_saving_offsets_price"
    ]

    assert anchor.conflict_penalty == Decimal("0.0000")
    assert "comment_claim_contradiction" not in anchor.risk_flags_json
    assert anchor.role_reason_json["applied_quality_issues"] == []


def test_m12d_anchor_scoring_deduplicates_same_domain_issue_penalty() -> None:
    context = _rich_ac_m12d_context()
    context.input_quality_json["M07"] = M12DInputQuality(
        module_code="M07",
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED,
        issues=[
            M12DInputQualityIssue(
                code=code,
                severity=M12DIssueSeverity.WARNING,
                scope=M12DIssueScope.ANCHOR,
                affected_anchor_codes=["cooling_heating_performance_justifies_price"],
            )
            for code in ("market_pool_insufficient", "price_band_sample_insufficient")
        ],
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role_reason_json["quality_score_penalty"] == Decimal("1.0000")
    assert anchor.conflict_penalty == Decimal("1.0000")
    assert anchor.role_reason_json["quality_confidence_penalty"] == Decimal("0.1000")


def test_m12d_anchor_scoring_blocking_issue_cannot_be_core() -> None:
    context = _rich_ac_m12d_context()
    _attach_input_quality_issue(
        context,
        module_code="M03B",
        code="m03b_true_param_conflict",
        severity=M12DIssueSeverity.BLOCKING,
        affected_anchor_codes=["cooling_heating_performance_justifies_price"],
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role == M12DAnchorRole.RISK_DRAG.value
    assert anchor.confidence <= Decimal("0.3000")
    assert "anchor_quality_blocking" in anchor.risk_flags_json
    assert anchor.downgrade_reason_code == "objective_rejection"


def test_m12d_ac_price_reason_accepts_comment_and_market_alternative_when_m12c_missing() -> (
    None
):
    context = _rich_ac_m12d_context(include_claim_value=False)
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert anchor.evidence_strength == M12DEvidenceStrength.STRONG.value
    assert anchor.downgrade_reason_code is None
    assert "price_value_core_evidence_missing" not in anchor.risk_flags_json
    assert (
        "cooling_heating_performance_justifies_price"
        in result.core_payment_anchors_json
    )


def test_m12d_ac_price_reason_without_m12c_or_comment_market_alternative_is_not_core() -> (
    None
):
    context = _rich_ac_m12d_context(include_claim_value=False)
    context.comment_profile = _input_snapshot("M05C")
    context.comment_profile_status = M12DInputStatus.MISSING.value
    context.semantic_profile.summary["battlefield"] = [
        *context.semantic_profile.summary.get("battlefield", []),
        "BF_ENERGY_SAVING",
    ]
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "long_term_energy_saving_offsets_price"
    ]

    assert anchor.evidence_strength == M12DEvidenceStrength.STRONG.value
    assert anchor.role == M12DAnchorRole.WEAK_EXPRESSION.value
    assert "price_value_core_evidence_missing" in anchor.risk_flags_json


def test_m12d_tv_function_reason_can_be_core_when_m12c_is_missing() -> None:
    context = _manual_m12d_context(
        claim_summary={
            "fact_claim_codes": ["tv_claim_high_refresh", "tv_claim_high_refresh_rate"],
            "dimension_profile_json": {"motion_gaming": {"fact_claim_count": 1}},
        },
        claim_status=M12DInputStatus.READY,
    )
    context.param_profile = _input_snapshot(
        "M03B",
        status=M12DInputStatus.READY,
        summary={"core_gaming_params_json": {"refresh_rate_hz": 144, "vrr_flag": True}},
        record_count=1,
    )
    context.param_profile_status = M12DInputStatus.READY.value
    context.comment_profile = _input_snapshot(
        "M05C",
        status=M12DInputStatus.READY,
        summary={
            "dimension_summary_json": {
                "motion_gaming": {"polarity_counts": {"positive": 5}},
                "gaming_motion_experience": {"polarity_counts": {"positive": 5}},
            }
        },
        record_count=1,
    )
    context.comment_profile_status = M12DInputStatus.READY.value
    context.semantic_profile = _input_snapshot(
        "M09C_M10C_M11C",
        status=M12DInputStatus.READY,
        summary={"user_task": ["TASK_GAMING_SPORTS_SMOOTHNESS"]},
        record_count=1,
    )
    context.semantic_profile_status = M12DInputStatus.READY.value
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category="TV",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "gaming_device_fit_reduces_risk"
    ]

    assert context.claim_value_status == M12DInputStatus.MISSING.value
    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert "price_value_core_evidence_missing" not in anchor.risk_flags_json


def test_m12d_ac_negative_dominance_adds_pressure_without_deleting_reason() -> None:
    context = _rich_ac_m12d_context(
        comment_summary={
            "positive_sentence_count": 1,
            "negative_sentence_count": 8,
            "dimension_summary_json": {
                "temperature_performance": {
                    "polarity_counts": {"positive": 1, "negative": 6}
                },
                "temperature_effect_experience": {
                    "polarity_counts": {"positive": 1, "negative": 6}
                },
                "airflow_comfort": {"polarity_counts": {"positive": 0, "negative": 4}},
            },
            "signal_summary_json": {"use_case_signal": ["客厅大空间"]},
            "evidence_examples_json": [
                {"text": "客厅降温慢，噪音明显，晚上睡觉会吵。"},
                {"text": "风直吹，老人小孩用起来不舒服。"},
            ],
        }
    )
    _attach_input_quality_issue(
        context,
        module_code="M05C",
        code="comment_negative_dominates",
        severity=M12DIssueSeverity.WARNING,
        affected_anchor_codes=["cooling_heating_performance_justifies_price"],
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert anchor.evidence_strength == M12DEvidenceStrength.INSUFFICIENT.value
    assert anchor.pressure_level == "high"
    assert anchor.downgrade_reason_code is None
    assert "comment_negative_dominates" in anchor.risk_flags_json
    assert (
        "cooling_heating_performance_justifies_price"
        in result.core_payment_anchors_json
    )


def test_m12d_ac_claim_value_headwind_does_not_delete_established_reason() -> None:
    context = _rich_ac_m12d_context(
        claim_value_summary={
            "claim_value_roles": {
                "ac_claim_fast_cooling_heating": "high_price_competitor_intercept",
                "ac_claim_energy_efficiency_apf": "opportunity_gap",
            },
            "anchor_claim_value_roles": {
                "cooling_heating_performance_justifies_price": {
                    "ac_claim_fast_cooling_heating": ["high_price_competitor_intercept"]
                }
            },
            "positive_claims_json": [],
        }
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert anchor.establishment_status in {"established", "established_limited"}
    assert any(
        tag.pressure_type == "m12c_value_headwind" for tag in anchor.pressure_tags_json
    )
    assert (
        "cooling_heating_performance_justifies_price"
        in result.core_payment_anchors_json
    )


def test_m12d_ac_reason_scoring_ignores_unrelated_claim_value_drag_role() -> None:
    context = _rich_ac_m12d_context(
        claim_value_summary={
            "claim_value_roles": {
                "temperature_performance": "sales_driver_estimated",
                "unrelated_service_claim": "drag_factor",
            },
            "positive_claims_json": ["temperature_performance"],
            "drag_claims_json": ["unrelated_service_claim"],
        }
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "cooling_heating_performance_justifies_price"
    ]

    assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
    assert "claim_value_drag_factor" not in anchor.risk_flags_json
    assert "ac_claim_value_risk_role_dominant" not in anchor.risk_flags_json
    assert anchor.role_reason_json["claim_value_roles"] == ["sales_driver_estimated"]


def test_m12d_ac_reason_scoring_caps_single_fresh_air_claim_as_weak_expression() -> (
    None
):
    context = _manual_ac_m12d_context(
        claim_summary={
            "fact_claim_codes": ["health_clean_air"],
            "claim_codes": ["health_clean_air"],
            "dimension_profile_json": {"health_clean_air": {"fact_claim_count": 1}},
            "claim_summary_json": {"keywords": ["新风"]},
        },
        claim_status=M12DInputStatus.READY,
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    anchor = {item.anchor_code: item for item in result.scored_anchors}[
        "fresh_air_health_reduces_stuffy_risk"
    ]

    assert anchor.role == M12DAnchorRole.WEAK_EXPRESSION.value
    assert anchor.evidence_strength == M12DEvidenceStrength.WEAK.value
    assert anchor.downgrade_reason_code == "positive_establishment_insufficient"
    assert anchor.role_reason_json["role_cap"] == M12DAnchorRole.WEAK_EXPRESSION.value


def test_m12d_reason_scoring_promotes_strong_purchase_reason_to_core_payment(
    client,
) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(batch_id="batch_m12d_context", sku_code="TV00029112")
        taxonomy = M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            product_category="TV",
        )
        candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

        result = PurchaseReasonProfileScoringService().score(
            candidate_set=candidate_set, context=context
        )
        by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}

        assert "picture_upgrade_perception" not in by_code
        assert (
            by_code["worth_paying_more_for_experience_upgrade"].role
            == M12DAnchorRole.CORE_PAYMENT.value
        )
        assert (
            by_code["worth_paying_more_for_experience_upgrade"].evidence_strength
            == M12DEvidenceStrength.STRONG.value
        )
        assert by_code[
            "worth_paying_more_for_experience_upgrade"
        ].confidence >= Decimal("0.7000")
        assert by_code["worth_paying_more_for_experience_upgrade"].domain_scores_json[
            "param_fact"
        ] == Decimal("3.0000")
        assert by_code["worth_paying_more_for_experience_upgrade"].domain_scores_json[
            "claim_value"
        ] == Decimal("3.0000")
        assert (
            "worth_paying_more_for_experience_upgrade"
            in result.core_payment_anchors_json
        )
        assert result.status == M12DProfileStatus.READY.value
    finally:
        session.close()


def test_m12d_reason_scoring_caps_price_value_only_as_weak_expression() -> None:
    context = _manual_m12d_context(
        claim_summary={
            "claim_codes": ["tv_claim_value_price"],
            "unsupported_claim_codes": ["tv_claim_value_price"],
            "dimension_position_profile_json": {"price": ["value_price"]},
        },
        claim_status=M12DInputStatus.READY,
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
        product_category="TV",
    )
    candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=candidate_set, context=context
    )
    by_code = {anchor.anchor_code: anchor for anchor in result.scored_anchors}

    assert (
        by_code["same_price_core_config_gain"].role
        == M12DAnchorRole.WEAK_EXPRESSION.value
    )
    assert (
        by_code["same_price_core_config_gain"].downgrade_reason_code
        == "positive_establishment_insufficient"
    )
    assert result.core_payment_anchors_json == []
    assert result.status == M12DProfileStatus.WEAK_EXPRESSION_ONLY.value


def test_m12d_reason_scoring_keeps_reason_and_emits_negative_pressure(client) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        context = SkuPurchaseReasonContextBuilder(
            Core3RepositoryContext(
                db=session,
                project_id="project_m12d_context",
                category_code=Core3CategoryCode.TV,
            )
        ).build_context(batch_id="batch_m12d_context", sku_code="TV00029112")
        context.comment_profile.summary["positive_sentence_count"] = 1
        context.comment_profile.summary["negative_sentence_count"] = 8
        context.comment_profile.summary["dimension_summary_json"][
            "picture_screen_experience"
        ]["polarity_counts"] = {"positive": 1, "negative": 8}
        context.claim_value_profile.summary["drag_claims_json"] = [
            "tv_claim_miniled_display"
        ]
        _attach_input_quality_issue(
            context,
            module_code="M05C",
            code="comment_negative_dominates",
            severity=M12DIssueSeverity.WARNING,
            affected_anchor_codes=["worth_paying_more_for_experience_upgrade"],
        )
        taxonomy = M12DAnchorTaxonomyLoader().load(
            CORE3_M12D_TV_ANCHOR_TAXONOMY_VERSION,
            product_category="TV",
        )
        candidate_set = AnchorCandidateGenerator(taxonomy).generate(context)

        result = PurchaseReasonProfileScoringService().score(
            candidate_set=candidate_set, context=context
        )
        anchor = {item.anchor_code: item for item in result.scored_anchors}[
            "worth_paying_more_for_experience_upgrade"
        ]

        assert anchor.role == M12DAnchorRole.CORE_PAYMENT.value
        assert anchor.evidence_strength == M12DEvidenceStrength.INSUFFICIENT.value
        assert {"comment_negative_dominates", "claim_value_drag_factor"} <= set(
            anchor.risk_flags_json
        )
        assert (
            "worth_paying_more_for_experience_upgrade"
            in result.core_payment_anchors_json
        )
        assert anchor.pressure_level in {"high", "critical"}
        assert result.status == M12DProfileStatus.READY.value
        assert result.review_required is False
    finally:
        session.close()


def test_m12d_profile_converges_core_by_score_family_and_limit_deterministically() -> (
    None
):
    context = _manual_m12d_context(claim_summary={})
    anchors = [
        _scored_anchor(
            "reason_a", family="family_1", score="10.0", confidence="0.80", rank=5
        ),
        _scored_anchor(
            "reason_b", family="family_1", score="9.5", confidence="0.90", rank=1
        ),
        _scored_anchor(
            "reason_c", family="family_2", score="9.0", confidence="0.82", rank=2
        ),
        _scored_anchor(
            "reason_d", family="family_3", score="8.0", confidence="0.81", rank=3
        ),
        _scored_anchor(
            "reason_e", family="family_4", score="7.0", confidence="0.95", rank=4
        ),
    ]

    forward = _profile_score(context, anchors)
    reverse = _profile_score(context, list(reversed(anchors)))

    assert forward.core_payment_anchors_json == ["reason_a", "reason_c", "reason_d"]
    assert reverse.core_payment_anchors_json == forward.core_payment_anchors_json
    assert len(forward.core_payment_anchors_json) == 3
    by_code = {anchor.anchor_code: anchor for anchor in forward.scored_anchors}
    assert by_code["reason_b"].role == M12DAnchorRole.SUPPORTING.value
    assert by_code["reason_b"].downgrade_reason_code == "core_limit_or_family_dedup"
    assert (
        by_code["reason_b"].role_reason_json["core_selection_demotion_reason"]
        == "family_dedup"
    )
    assert (
        by_code["reason_e"].role_reason_json["core_selection_demotion_reason"]
        == "core_limit"
    )


def test_m12d_profile_confidence_uses_only_selected_core_rank_weights() -> None:
    context = _manual_m12d_context(
        claim_summary={}, claim_status=M12DInputStatus.PARTIAL
    )
    anchors = [
        _scored_anchor(
            "reason_a", family="family_1", score="10", confidence="0.90", rank=1
        ),
        _scored_anchor(
            "reason_b", family="family_2", score="9", confidence="0.80", rank=2
        ),
        _scored_anchor(
            "reason_c", family="family_3", score="8", confidence="0.70", rank=3
        ),
        _scored_anchor(
            "reason_support",
            family="family_4",
            score="7",
            confidence="0.99",
            rank=4,
            role=M12DAnchorRole.SUPPORTING,
        ),
    ]

    result = _profile_score(context, anchors)

    assert result.profile_confidence == Decimal("0.8450")
    assert result.status == M12DProfileStatus.READY.value
    assert result.review_required is False
    assert result.confidence_basis_json["normalized_available_weights"] == [
        "0.6000",
        "0.2500",
        "0.1500",
    ]


@pytest.mark.parametrize(
    ("confidences", "expected_confidence", "expected_weights"),
    [
        (["0.72"], Decimal("0.7200"), ["1.0000"]),
        (["0.90", "0.50"], Decimal("0.7824"), ["0.7059", "0.2941"]),
    ],
)
def test_m12d_profile_confidence_normalizes_available_core_weights(
    confidences: list[str],
    expected_confidence: Decimal,
    expected_weights: list[str],
) -> None:
    context = _manual_m12d_context(claim_summary={})
    anchors = [
        _scored_anchor(
            f"reason_{index}",
            family=f"family_{index}",
            score=str(10 - index),
            confidence=confidence,
            rank=index,
        )
        for index, confidence in enumerate(confidences, start=1)
    ]

    result = _profile_score(context, anchors)

    assert result.profile_confidence == expected_confidence
    assert (
        result.confidence_basis_json["normalized_available_weights"] == expected_weights
    )


def test_m12d_profile_without_core_keeps_limited_confidence_separate() -> None:
    context = _manual_m12d_context(claim_summary={})
    result = _profile_score(
        context,
        [
            _scored_anchor(
                "reason_support",
                family="family_1",
                score="7",
                confidence="0.65",
                rank=1,
                role=M12DAnchorRole.SUPPORTING,
            )
        ],
    )

    assert result.status == M12DProfileStatus.READY_LIMITED.value
    assert result.profile_confidence == Decimal("0.0000")
    assert result.confidence_basis_json["limited_confidence"] == "0.6500"
    assert result.review_required is False


def test_m12d_profile_statuses_cover_weak_missing_and_profile_failure() -> None:
    context = _manual_m12d_context(claim_summary={})
    weak = _profile_score(
        context,
        [
            _scored_anchor(
                "reason_weak",
                family="family_1",
                score="3",
                confidence="0.42",
                rank=1,
                role=M12DAnchorRole.WEAK_EXPRESSION,
                strength=M12DEvidenceStrength.WEAK,
            )
        ],
    )
    missing = _profile_score(context, [])
    _attach_input_quality_issue(
        context,
        module_code="M04C",
        code="profile_contract_incompatible",
        severity=M12DIssueSeverity.BLOCKING,
        affected_anchor_codes=[],
        scope=M12DIssueScope.PROFILE,
    )
    failed = _profile_score(
        context,
        [
            _scored_anchor(
                "reason_core", family="family_1", score="10", confidence="0.85", rank=1
            )
        ],
    )

    assert weak.status == M12DProfileStatus.WEAK_EXPRESSION_ONLY.value
    assert missing.status == M12DProfileStatus.MISSING_INPUT.value
    assert failed.status == M12DProfileStatus.FAILED.value
    assert failed.review_required is True
    assert failed.review_reason_json["reasons"] == ["profile_blocking_issue"]


def test_m12d_profile_reviews_only_blocking_issue_that_can_change_conclusion() -> None:
    context = _rich_ac_m12d_context()
    _attach_input_quality_issue(
        context,
        module_code="M03B",
        code="m03b_true_param_conflict",
        severity=M12DIssueSeverity.BLOCKING,
        affected_anchor_codes=["cooling_heating_performance_justifies_price"],
    )
    taxonomy = M12DAnchorTaxonomyLoader().load(
        CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
        product_category="AC",
    )

    result = PurchaseReasonProfileScoringService().score(
        candidate_set=AnchorCandidateGenerator(taxonomy).generate(context),
        context=context,
    )

    assert result.review_required is True
    assert (
        "core_candidate_blocked_by_input_issue" in result.review_reason_json["reasons"]
    )
    assert result.status != M12DProfileStatus.REVIEW_REQUIRED.value


def test_m12d_profile_does_not_review_warning_or_non_core_blocking_issue() -> None:
    context = _manual_m12d_context(claim_summary={})
    weak_anchor = _scored_anchor(
        "reason_weak",
        family="family_1",
        score="3",
        confidence="0.42",
        rank=1,
        role=M12DAnchorRole.WEAK_EXPRESSION,
        strength=M12DEvidenceStrength.WEAK,
        applied_issues=[
            {
                "module_code": "M05C",
                "issue_code": "weak_fact_conflict",
                "severity": M12DIssueSeverity.BLOCKING.value,
                "scope": M12DIssueScope.ANCHOR.value,
                "applied": True,
            }
        ],
    )
    _attach_input_quality_issue(
        context,
        module_code="M07",
        code="market_sample_insufficient",
        severity=M12DIssueSeverity.WARNING,
        affected_anchor_codes=["reason_weak"],
    )

    result = _profile_score(context, [weak_anchor])

    assert result.review_required is False
    assert result.review_reason_json["reasons"] == []


def test_m12d_sku_purchase_reason_cli_outputs_business_markdown(client, capsys) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)

        result = catforge_analyst.sku_purchase_reason(
            session,
            project_id="project_m12d_context",
            category_code="TV",
            batch_id="batch_m12d_context",
            product_category="tv",
            query="海信 65E7Q",
            max_anchors=5,
        )

        preview = result["result"]["sku_purchase_reason"]
        markdown = preview["markdown_preview"]
        core_anchor_codes = {
            anchor["anchor_code"]
            for anchor in preview["profile"]["core_payment_anchors"]
        }

        assert result["status"] == "ok"
        assert result["target"]["sku_code"] == "TV00029112"
        assert "worth_paying_more_for_experience_upgrade" in core_anchor_codes
        assert "# SKU 成交理由画像预览" in markdown
        assert "贵得值的体验升级" in markdown
        assert "## 输入覆盖" in markdown
        assert "SQL" not in markdown
        assert "raw_json" not in markdown
        assert "debug" not in markdown.lower()

        catforge_analyst.emit_result(result, "markdown")
        output = capsys.readouterr().out
        assert output.startswith("# SKU 成交理由画像预览")
    finally:
        session.close()


def test_m12d_ac_sku_purchase_reason_cli_outputs_business_markdown(
    client, capsys
) -> None:
    session = SessionLocal()
    try:
        _seed_ac_m12d_context_inputs(session, include_claim_value=True)

        result = catforge_analyst.sku_purchase_reason(
            session,
            project_id="project_m12d_context_ac",
            category_code="AC",
            batch_id="batch_m12d_context_ac",
            product_category="ac",
            sku_code="AC00038063",
            max_anchors=6,
        )

        preview = result["result"]["sku_purchase_reason"]
        markdown = preview["markdown_preview"]
        core_anchor_codes = {
            anchor["anchor_code"]
            for anchor in preview["profile"]["core_payment_anchors"]
        }

        assert result["status"] == "ok"
        assert result["category_code"] == "AC"
        assert result["target"]["sku_code"] == "AC00038063"
        assert preview["taxonomy_version"] == CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION
        assert {item["source"]: item["status"] for item in preview["input_status"]} == {
            "param_profile": M12DInputStatus.READY.value,
            "claim_fact_profile": M12DInputStatus.READY.value,
            "comment_profile": M12DInputStatus.READY.value,
            "market_profile": M12DInputStatus.READY.value,
            "semantic_profile": M12DInputStatus.READY.value,
            "semantic_market_profile": M12DInputStatus.READY.value,
            "claim_value_profile": M12DInputStatus.READY.value,
        }
        assert "cooling_heating_performance_justifies_price" in core_anchor_codes
        assert "# SKU 成交理由画像预览" in markdown
        assert "品类：AC" in markdown
        assert "冷暖效果解释更高价格" in markdown
        assert "## 输入覆盖" in markdown
        assert "SQL" not in markdown
        assert "debug" not in markdown.lower()

        catforge_analyst.emit_result(result, "markdown")
        output = capsys.readouterr().out
        assert output.startswith("# SKU 成交理由画像预览")
    finally:
        session.close()


def test_m12d_batch_generator_writes_draft_records_without_publishing(client) -> None:
    session = SessionLocal()
    try:
        _seed_m12d_context_inputs(session, include_claim_value=True)
        repository_context = Core3RepositoryContext(
            db=session,
            project_id="project_m12d_context",
            category_code=Core3CategoryCode.TV,
        )
        result = PurchaseReasonProfileBatchGenerator(repository_context).generate(
            batch_id="serving-scope:TV:missing_batch,batch_m12d_context",
            storage_batch_id="batch_m12d_context",
            sku_codes=["TV00029112"],
            m12d_profile_version="m12d_g08_test_draft",
            write=True,
            generated_by="pytest",
            focus_sku_codes=["TV00029112"],
        )

        assert result.status == Core3RunStatus.SUCCESS
        assert (
            result.summary["read_batch_id"]
            == "serving-scope:TV:missing_batch,batch_m12d_context"
        )
        assert result.summary["batch_id"] == "batch_m12d_context"
        assert result.summary["profile_record_count"] == 1
        assert result.summary["anchor_record_count"] >= 1
        assert result.created_output_count >= 3

        version = session.execute(
            select(entities.Core3PurchaseReasonProfileVersion).where(
                entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
                == "m12d_g08_test_draft"
            )
        ).scalar_one()
        profile = session.execute(
            select(entities.Core3SkuPurchaseReasonProfile).where(
                entities.Core3SkuPurchaseReasonProfile.m12d_profile_version
                == "m12d_g08_test_draft"
            )
        ).scalar_one()
        anchors = list(
            session.execute(
                select(entities.Core3SkuPurchaseReasonAnchor)
                .where(
                    entities.Core3SkuPurchaseReasonAnchor.m12d_profile_version
                    == "m12d_g08_test_draft"
                )
                .order_by(entities.Core3SkuPurchaseReasonAnchor.anchor_rank)
            ).scalars()
        )

        assert version.release_status == M12DReleaseStatus.DRAFT.value
        assert (
            version.release_quality_status == M12DReleaseQualityStatus.READY.value
        ), version.quality_summary_json["release_quality_evaluation"]
        assert (
            version.quality_summary_json["release_quality_evaluation"][
                "failure_reason_codes"
            ]
            == []
        )
        assert version.is_current is False
        assert version.input_scope_json["read_batch_id"].startswith("serving-scope:TV:")
        assert profile.release_status == M12DReleaseStatus.DRAFT.value
        assert profile.purchase_reason_version_id == version.purchase_reason_version_id
        assert set(profile.input_quality_json) == {
            "M03B",
            "M04C",
            "M05C",
            "M07",
            "M09C_M10C_M11C",
            "M11D",
            "M12C",
        }
        assert (
            "worth_paying_more_for_experience_upgrade"
            in profile.core_payment_anchors_json
        )
        assert (
            "worth_paying_more_for_experience_upgrade"
            in profile.established_anchors_json
        )
        assert profile.pressure_summary_json
        assert anchors
        core_anchor = next(
            anchor
            for anchor in anchors
            if anchor.anchor_code == "worth_paying_more_for_experience_upgrade"
        )
        assert core_anchor.establishment_status in {
            M12DReasonEstablishmentStatus.ESTABLISHED.value,
            M12DReasonEstablishmentStatus.ESTABLISHED_LIMITED.value,
        }
        assert core_anchor.establishment_score is not None
        assert core_anchor.establishment_score >= Decimal("7")
        assert core_anchor.core_eligible is True
        assert core_anchor.pressure_level != M12DPurchasePressureLevel.UNASSESSED.value
        assert (
            anchors[0].purchase_reason_profile_id == profile.purchase_reason_profile_id
        )
        assert (
            PurchaseReasonProfileRepository(repository_context).get_published_profile(
                batch_id="batch_m12d_context",
                sku_code="TV00029112",
                m12d_profile_version="m12d_g08_test_draft",
            )
            is None
        )
    finally:
        session.close()


def test_m12d_ac_batch_generator_writes_draft_records_without_publishing(
    client,
) -> None:
    session = SessionLocal()
    try:
        _seed_ac_m12d_context_inputs(session, include_claim_value=True)
        repository_context = Core3RepositoryContext(
            db=session,
            project_id="project_m12d_context_ac",
            category_code=Core3CategoryCode.AC,
        )
        result = PurchaseReasonProfileBatchGenerator(repository_context).generate(
            batch_id="batch_m12d_context_ac",
            storage_batch_id="batch_m12d_context_ac",
            sku_codes=["AC00038063"],
            product_category="AC",
            taxonomy_version=CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
            m12d_profile_version="m12d_ac_g08_test_draft",
            write=True,
            generated_by="pytest",
        )

        assert result.status == Core3RunStatus.SUCCESS
        assert result.summary["batch_id"] == "batch_m12d_context_ac"
        assert (
            result.summary["taxonomy_version"] == CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION
        )
        assert result.summary["profile_record_count"] == 1
        assert result.summary["anchor_record_count"] >= 1
        assert result.created_output_count >= 3

        version = session.execute(
            select(entities.Core3PurchaseReasonProfileVersion).where(
                entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
                == "m12d_ac_g08_test_draft"
            )
        ).scalar_one()
        profile = session.execute(
            select(entities.Core3SkuPurchaseReasonProfile).where(
                entities.Core3SkuPurchaseReasonProfile.m12d_profile_version
                == "m12d_ac_g08_test_draft"
            )
        ).scalar_one()
        anchors = list(
            session.execute(
                select(entities.Core3SkuPurchaseReasonAnchor)
                .where(
                    entities.Core3SkuPurchaseReasonAnchor.m12d_profile_version
                    == "m12d_ac_g08_test_draft"
                )
                .order_by(entities.Core3SkuPurchaseReasonAnchor.anchor_rank)
            ).scalars()
        )

        assert version.category_code == Core3CategoryCode.AC.value
        assert version.product_category == "AC"
        assert version.release_status == M12DReleaseStatus.DRAFT.value
        assert version.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
        assert (
            "focus_sku_pass_rate"
            in version.quality_summary_json["release_quality_evaluation"][
                "failure_reason_codes"
            ]
        )
        assert version.is_current is False
        assert profile.category_code == Core3CategoryCode.AC.value
        assert profile.product_category == "AC"
        assert profile.release_status == M12DReleaseStatus.DRAFT.value
        assert profile.purchase_reason_version_id == version.purchase_reason_version_id
        assert (
            "cooling_heating_performance_justifies_price"
            in profile.core_payment_anchors_json
        )
        assert anchors
        assert all(anchor.product_category == "AC" for anchor in anchors)
        assert (
            PurchaseReasonProfileRepository(repository_context).get_published_profile(
                batch_id="batch_m12d_context_ac",
                sku_code="AC00038063",
                m12d_profile_version="m12d_ac_g08_test_draft",
            )
            is None
        )
    finally:
        session.close()


def test_m12d_ac_downstream_contract_requires_published_current(client) -> None:
    session = SessionLocal()
    try:
        _seed_ac_m12d_context_inputs(session, include_claim_value=True)
        repository_context = Core3RepositoryContext(
            db=session,
            project_id="project_m12d_context_ac",
            category_code=Core3CategoryCode.AC,
        )
        PurchaseReasonProfileBatchGenerator(repository_context).generate(
            batch_id="batch_m12d_context_ac",
            storage_batch_id="batch_m12d_context_ac",
            sku_codes=["AC00038063"],
            product_category="AC",
            taxonomy_version=CORE3_M12D_AC_ANCHOR_TAXONOMY_VERSION,
            m12d_profile_version="m12d_ac_g09_test_draft",
            write=True,
            generated_by="pytest",
        )
        repository = PurchaseReasonProfileRepository(repository_context)

        draft = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d_context_ac",
            sku_code="AC00038063",
            m12d_profile_version="m12d_ac_g09_test_draft",
        )
        assert draft.found is False
        assert draft.consumption_state == "not_found"
        assert draft.downstream_action == "block_target_or_drop_candidate"

        repository.publish_version(
            batch_id="batch_m12d_context_ac",
            m12d_profile_version="m12d_ac_g09_test_draft",
            rule_version=CORE3_M12D_RULE_VERSION,
            published_by="pytest",
            release_note_cn="AC G09 fixture publish",
            allow_limited=True,
        )
        published = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d_context_ac",
            sku_code="AC00038063",
            m12d_profile_version="m12d_ac_g09_test_draft",
        )

        assert published.found is True
        assert (
            published.release_quality_status == M12DReleaseQualityStatus.LIMITED.value
        )
        assert published.consumption_state == "published_ready"
        assert published.downstream_action == "normal_pair_scoring"
        assert published.capabilities.strong_reason_comparison_allowed is True
        assert published.profile is not None
        assert published.profile.category_code == Core3CategoryCode.AC.value
        assert published.profile.product_category == "AC"
        assert (
            "cooling_heating_performance_justifies_price"
            in published.profile.core_payment_anchors
        )
        assert {anchor.role for anchor in published.profile.anchors} >= {
            M12DAnchorRole.CORE_PAYMENT.value
        }

        version = session.execute(
            select(entities.Core3PurchaseReasonProfileVersion).where(
                entities.Core3PurchaseReasonProfileVersion.m12d_profile_version
                == "m12d_ac_g09_test_draft"
            )
        ).scalar_one()
        assert version.release_status == M12DReleaseStatus.PUBLISHED.value
        assert version.is_current is True
        assert version.published_by == "pytest"

        missing = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d_context_ac",
            sku_code="AC_M12D_NOT_FOUND",
            m12d_profile_version="m12d_ac_g09_test_draft",
        )
        unpublished_version = get_downstream_read_contract(
            repository,
            batch_id="batch_m12d_context_ac",
            sku_code="AC00038063",
            m12d_profile_version="m12d_ac_g09_test_draft_unpublished",
        )
        assert missing.consumption_state == "not_found"
        assert unpublished_version.consumption_state == "not_found"
    finally:
        session.close()


def _profile_score(
    context: M12DSkuPurchaseReasonContext,
    anchors: list[M12DScoredPurchaseReasonAnchor],
):
    return ProfileConfidenceScorer().score(
        candidate_set=M12DAnchorCandidateSet(
            taxonomy_version="test_taxonomy_v1",
            product_category=context.product_category,
            sku_code=context.sku_code,
        ),
        context=context,
        scored_anchors=anchors,
    )


def _scored_anchor(
    anchor_code: str,
    *,
    family: str,
    score: str,
    confidence: str,
    rank: int,
    role: M12DAnchorRole = M12DAnchorRole.CORE_PAYMENT,
    strength: M12DEvidenceStrength = M12DEvidenceStrength.STRONG,
    applied_issues: list[dict] | None = None,
) -> M12DScoredPurchaseReasonAnchor:
    return M12DScoredPurchaseReasonAnchor(
        taxonomy_version="test_taxonomy_v1",
        product_category="TV",
        sku_code="TV00000001",
        anchor_code=anchor_code,
        anchor_cn=anchor_code,
        anchor_family_code=family,
        anchor_family_cn=family,
        anchor_rank=rank,
        role=role,
        evidence_strength=strength,
        confidence=Decimal(confidence),
        raw_evidence_score=Decimal(score),
        adjusted_evidence_score=Decimal(score),
        evidence_domains_json=[
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.SEMANTIC_SCENE,
        ],
        domain_scores_json={"param_fact": Decimal("3.0000")},
        support_summary_cn=f"{anchor_code} test support",
        role_reason_json={
            "strong_domain_count": 2,
            "applied_quality_issues": applied_issues or [],
        },
        input_fingerprint=f"fp_{anchor_code}",
    )


def _manual_m12d_context(
    *,
    claim_summary: dict,
    claim_status: M12DInputStatus = M12DInputStatus.MISSING,
) -> M12DSkuPurchaseReasonContext:
    empty_param = _input_snapshot("M03B")
    claim_snapshot = _input_snapshot(
        "M04C", status=claim_status, summary=claim_summary, record_count=1
    )
    empty_comment = _input_snapshot("M05C")
    empty_market = _input_snapshot("M07")
    empty_semantic = _input_snapshot("M09C_M10C_M11C")
    empty_semantic_market = _input_snapshot("M11D")
    empty_claim_value = _input_snapshot("M12C")
    return M12DSkuPurchaseReasonContext(
        project_id="project_m12d_manual",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_m12d_manual",
        product_category="TV",
        sku_code="TV00000001",
        model_name="Manual TV",
        brand_name="Manual",
        display_name_cn="Manual TV",
        param_profile_status=empty_param.status,
        claim_fact_status=claim_snapshot.status,
        comment_profile_status=empty_comment.status,
        market_profile_status=empty_market.status,
        semantic_profile_status=empty_semantic.status,
        semantic_market_status=empty_semantic_market.status,
        claim_value_status=empty_claim_value.status,
        param_profile=empty_param,
        claim_fact_profile=claim_snapshot,
        comment_profile=empty_comment,
        market_profile=empty_market,
        semantic_profile=empty_semantic,
        semantic_market_profile=empty_semantic_market,
        claim_value_profile=empty_claim_value,
        input_status_json={
            "claim_fact_status": claim_status.value,
        },
        missing_input_reasons_json=["manual minimal context"],
        source_refs_json=[],
        input_fingerprint="manual_input_fp",
    )


def _manual_ac_m12d_context(
    *,
    param_summary: dict | None = None,
    claim_summary: dict | None = None,
    comment_summary: dict | None = None,
    market_summary: dict | None = None,
    semantic_summary: dict | None = None,
    semantic_market_summary: dict | None = None,
    claim_value_summary: dict | None = None,
    claim_status: M12DInputStatus | None = None,
) -> M12DSkuPurchaseReasonContext:
    param_snapshot = _input_snapshot(
        "M03B",
        status=M12DInputStatus.READY if param_summary else M12DInputStatus.MISSING,
        summary=param_summary,
        record_count=1 if param_summary else 0,
    )
    claim_snapshot = _input_snapshot(
        "M04C",
        status=claim_status
        or (M12DInputStatus.READY if claim_summary else M12DInputStatus.MISSING),
        summary=claim_summary,
        record_count=1 if claim_summary else 0,
    )
    comment_snapshot = _input_snapshot(
        "M05C",
        status=M12DInputStatus.READY if comment_summary else M12DInputStatus.MISSING,
        summary=comment_summary,
        record_count=1 if comment_summary else 0,
    )
    market_snapshot = _input_snapshot(
        "M07",
        status=M12DInputStatus.READY if market_summary else M12DInputStatus.MISSING,
        summary=market_summary,
        record_count=1 if market_summary else 0,
    )
    semantic_snapshot = _input_snapshot(
        "M09C_M10C_M11C",
        status=M12DInputStatus.READY if semantic_summary else M12DInputStatus.MISSING,
        summary=semantic_summary,
        record_count=1 if semantic_summary else 0,
    )
    semantic_market_snapshot = _input_snapshot(
        "M11D",
        status=M12DInputStatus.READY
        if semantic_market_summary
        else M12DInputStatus.MISSING,
        summary=semantic_market_summary,
        record_count=1 if semantic_market_summary else 0,
    )
    claim_value_snapshot = _input_snapshot(
        "M12C",
        status=M12DInputStatus.READY
        if claim_value_summary
        else M12DInputStatus.MISSING,
        summary=claim_value_summary,
        record_count=1 if claim_value_summary else 0,
    )
    return M12DSkuPurchaseReasonContext(
        project_id="project_m12d_manual_ac",
        category_code=Core3CategoryCode.AC,
        batch_id="batch_m12d_manual_ac",
        product_category="AC",
        sku_code="AC00000001",
        model_name="Manual AC",
        brand_name="Manual",
        display_name_cn="Manual AC",
        param_profile_status=param_snapshot.status,
        claim_fact_status=claim_snapshot.status,
        comment_profile_status=comment_snapshot.status,
        market_profile_status=market_snapshot.status,
        semantic_profile_status=semantic_snapshot.status,
        semantic_market_status=semantic_market_snapshot.status,
        claim_value_status=claim_value_snapshot.status,
        param_profile=param_snapshot,
        claim_fact_profile=claim_snapshot,
        comment_profile=comment_snapshot,
        market_profile=market_snapshot,
        semantic_profile=semantic_snapshot,
        semantic_market_profile=semantic_market_snapshot,
        claim_value_profile=claim_value_snapshot,
        input_status_json={
            "param_profile_status": param_snapshot.status,
            "claim_fact_status": claim_snapshot.status,
            "comment_profile_status": comment_snapshot.status,
            "market_profile_status": market_snapshot.status,
            "semantic_profile_status": semantic_snapshot.status,
            "semantic_market_status": semantic_market_snapshot.status,
            "claim_value_status": claim_value_snapshot.status,
        },
        missing_input_reasons_json=["manual AC context"],
        source_refs_json=[],
        input_fingerprint="manual_ac_input_fp",
    )


def _rich_ac_m12d_context(
    *,
    include_claim_value: bool = True,
    comment_summary: dict | None = None,
    claim_value_summary: dict | None = None,
) -> M12DSkuPurchaseReasonContext:
    resolved_claim_value_summary = claim_value_summary
    if include_claim_value and resolved_claim_value_summary is None:
        resolved_claim_value_summary = {
            "claim_value_roles": {
                "ac_claim_fast_cooling_heating": "sales_driver_estimated",
                "ac_claim_energy_efficiency_apf": "sales_driver_estimated",
            },
            "anchor_claim_value_roles": {
                "cooling_heating_performance_justifies_price": {
                    "ac_claim_fast_cooling_heating": ["sales_driver_estimated"]
                },
                "long_term_energy_saving_offsets_price": {
                    "ac_claim_energy_efficiency_apf": ["sales_driver_estimated"]
                },
            },
            "positive_claims_json": [
                "ac_claim_fast_cooling_heating",
                "ac_claim_energy_efficiency_apf",
            ],
        }
    return _manual_ac_m12d_context(
        param_summary={
            "param_values_json": {
                "installation_type": "柜机",
                "capacity_hp": "3匹",
                "cooling_capacity": 7200,
                "heating_capacity": 9600,
                "air_volume": 1300,
                "apf": 5.2,
                "energy_efficiency_level": "一级能效",
                "noise_db": 18,
                "fresh_air_volume": 60,
                "anti_direct_blow": True,
                "self_clean": True,
                "wifi": True,
            }
        },
        claim_summary={
            "fact_claim_codes": [
                "temperature_performance",
                "energy_efficiency",
                "airflow_comfort",
                "health_clean_air",
                "smart_control",
                "durability_quality",
            ],
            "dimension_profile_json": {
                "temperature_performance": {"fact_claim_count": 2},
                "energy_efficiency": {"fact_claim_count": 1},
                "airflow_comfort": {"fact_claim_count": 2},
                "health_clean_air": {"fact_claim_count": 1},
                "smart_control": {"fact_claim_count": 1},
                "durability_quality": {"fact_claim_count": 1},
            },
            "claim_summary_json": {
                "keywords": ["速冷", "一级能效", "新风", "防直吹", "自清洁", "远程"]
            },
        },
        comment_summary=comment_summary
        or {
            "positive_sentence_count": 12,
            "negative_sentence_count": 1,
            "dimension_summary_json": {
                "temperature_effect_experience": {"polarity_counts": {"positive": 8}},
                "energy_cost_experience": {"polarity_counts": {"positive": 3}},
                "airflow_comfort_experience": {"polarity_counts": {"positive": 5}},
                "health_air_experience": {"polarity_counts": {"positive": 2}},
            },
            "signal_summary_json": {
                "use_case_signal": ["客厅大空间", "卧室睡眠", "老人儿童"]
            },
            "evidence_examples_json": [
                {"text": "客厅制冷快，风感柔和不直吹，晚上睡觉也安静。"},
                {"text": "一级能效省电，新风打开后不闷，远程控制方便。"},
            ],
        },
        market_summary={
            "price_band_category": "mid_high",
            "price_band_size": "high",
            "same_pool_volume_percentile": "high",
            "sales_volume_total": 120000,
        },
        semantic_summary={
            "user_task": [
                "large_space",
                "bedroom_sleep",
                "elderly_child",
                "seasonal_reliability",
            ],
            "target_group": ["family", "elderly_child"],
            "battlefield": [
                "BF_COOLING_HEATING_CAPACITY",
                "BF_HEALTH_CLEAN_AIR",
                "BF_OPERATION_CONVENIENCE",
            ],
        },
        semantic_market_summary={
            "semantic_market_role": "matched",
            "battlefield_market_acceptance": [
                "BF_COOLING_HEATING_CAPACITY",
                "BF_HEALTH_CLEAN_AIR",
            ],
        },
        claim_value_summary=resolved_claim_value_summary
        if include_claim_value
        else None,
    )


def _input_snapshot(
    module_code: str,
    *,
    status: M12DInputStatus = M12DInputStatus.MISSING,
    summary: dict | None = None,
    record_count: int = 0,
) -> M12DInputSnapshot:
    return M12DInputSnapshot(
        module_code=module_code,
        status=status,
        record_count=record_count,
        summary=summary or {},
        records=[],
        source_refs=[],
        missing_reasons=[]
        if record_count
        else [f"{module_code} missing in manual context"],
    )


def _attach_input_quality_issue(
    context: M12DSkuPurchaseReasonContext,
    *,
    module_code: str,
    code: str,
    severity: M12DIssueSeverity,
    affected_anchor_codes: list[str],
    scope: M12DIssueScope = M12DIssueScope.ANCHOR,
) -> None:
    context.input_quality_json[module_code] = M12DInputQuality(
        module_code=module_code,
        availability=M12DInputAvailability.PRESENT,
        usability=M12DInputUsability.LIMITED,
        issues=[
            M12DInputQualityIssue(
                code=code,
                severity=severity,
                scope=scope,
                message_cn=f"test issue: {code}",
                affected_anchor_codes=affected_anchor_codes,
            )
        ],
    )


def _version_payload(
    version_id: str,
    m12d_profile_version: str,
    result_hash: str,
    *,
    release_quality_status: M12DReleaseQualityStatus = M12DReleaseQualityStatus.READY,
) -> M12DPurchaseReasonProfileVersionRecord:
    return M12DPurchaseReasonProfileVersionRecord(
        purchase_reason_version_id=version_id,
        project_id="project_m12d_publish",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_m12d",
        m12d_profile_version=m12d_profile_version,
        release_quality_status=release_quality_status,
        source_batch_ids_json=["m00_20260619084551_857df63b"],
        input_scope_json={"sku_count": 1},
        sku_count=1,
        ready_count=1,
        input_fingerprint=f"input_{m12d_profile_version}",
        result_hash=result_hash,
    )


def _profile_payload(
    profile_id: str,
    version_id: str,
    m12d_profile_version: str,
    result_hash: str,
) -> M12DSkuPurchaseReasonProfileRecord:
    project_id = (
        "project_m12d_publish"
        if m12d_profile_version.startswith("m12d_v")
        else "project_m12d_reuse"
    )
    return M12DSkuPurchaseReasonProfileRecord(
        purchase_reason_profile_id=profile_id,
        purchase_reason_version_id=version_id,
        project_id=project_id,
        category_code=Core3CategoryCode.TV,
        batch_id="batch_m12d",
        m12d_profile_version=m12d_profile_version,
        sku_code="TV00029112",
        brand_name="海信",
        model_name="65E7Q",
        display_name_cn="海信 65E7Q",
        status=M12DProfileStatus.READY,
        profile_confidence=Decimal("0.8200"),
        core_reasons_json=["高端画质支撑高价段升级购买"],
        core_payment_anchors_json=["worth_paying_more_for_experience_upgrade"],
        param_profile_status=M12DInputStatus.READY,
        claim_fact_status=M12DInputStatus.READY,
        comment_profile_status=M12DInputStatus.READY,
        market_profile_status=M12DInputStatus.READY,
        semantic_profile_status=M12DInputStatus.READY,
        semantic_market_status=M12DInputStatus.READY,
        claim_value_status=M12DInputStatus.READY,
        source_batch_ids_json=["m00_20260619084551_857df63b"],
        source_merge_strategy="serving_scope_merge_by_domain",
        input_fingerprint=f"input_{profile_id}",
        result_hash=result_hash,
    )


def _anchor_payload(
    anchor_id: str,
    profile_id: str,
    version_id: str,
    m12d_profile_version: str,
    result_hash: str,
) -> M12DPurchaseReasonAnchorRecord:
    return M12DPurchaseReasonAnchorRecord(
        purchase_reason_anchor_id=anchor_id,
        purchase_reason_profile_id=profile_id,
        purchase_reason_version_id=version_id,
        project_id="project_m12d_publish",
        category_code=Core3CategoryCode.TV,
        batch_id="batch_m12d",
        m12d_profile_version=m12d_profile_version,
        sku_code="TV00029112",
        brand_name="海信",
        model_name="65E7Q",
        anchor_code="worth_paying_more_for_experience_upgrade",
        anchor_cn="贵得值的体验升级",
        anchor_rank=1,
        role=M12DAnchorRole.CORE_PAYMENT,
        evidence_strength=M12DEvidenceStrength.STRONG,
        confidence=Decimal("0.8500"),
        evidence_domains_json=[
            M12DEvidenceDomain.PARAM_FACT,
            M12DEvidenceDomain.FACT_CLAIM,
            M12DEvidenceDomain.CLAIM_VALUE,
        ],
        domain_scores_json={
            "param_fact": Decimal("3.0000"),
            "claim_value": Decimal("3.0000"),
        },
        support_summary_cn="MiniLED、亮度和 M12C 支付价值共同支撑贵得值的体验升级。",
        source_refs_json=[{"module": "M12C", "record_id": "claim_value_1"}],
        input_fingerprint=f"input_{anchor_id}",
        result_hash=result_hash,
    )


def _seed_m12d_context_inputs(session, *, include_claim_value: bool) -> None:
    project_id = "project_m12d_context"
    batch_id = "batch_m12d_context"
    sku_code = "TV00029112"
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="m12d-param-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            sku_code=sku_code,
            model_name="65E7Q",
            param_values_json={"screen_size_inch": {"normalized_value": 65}},
            core_picture_params_json={
                "mini_led_flag": {"normalized_value": True},
                "local_dimming_zone_count": {"normalized_value": 1920},
            },
            core_gaming_params_json={"refresh_rate_hz": {"normalized_value": 144}},
            core_system_params_json={"ai_chip_flag": {"normalized_value": True}},
            core_eye_care_params_json={
                "low_blue_light_flag": {"normalized_value": True}
            },
            param_completeness=Decimal("0.820000"),
            known_param_count=42,
            unknown_param_count=5,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["ev-param-tv00029112"],
            quality_summary_json={"status": "ok"},
            profile_hash="hash-param-tv00029112",
            seed_version="tv_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="m12d-claim-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M04C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            raw_claim_count=3,
            matched_claim_count=3,
            fact_claim_count=2,
            unsupported_claim_count=1,
            claim_texts_json=["MiniLED 画质", "144Hz 高刷", "价格实惠"],
            claim_codes=[
                "tv_claim_miniled",
                "tv_claim_high_refresh",
                "tv_claim_value_price",
                "tv_claim_high_refresh",
            ],
            fact_claim_codes=[
                "tv_claim_miniled",
                "tv_claim_high_refresh",
                "tv_claim_high_refresh",
            ],
            unsupported_claim_codes=["tv_claim_value_price"],
            dimension_profile_json={"picture_quality": {"fact_claim_count": 1}},
            dimension_position_profile_json={
                "picture_quality": ["picture_flagship_miniled"]
            },
            claim_summary_json={"premium_claim_candidates": ["tv_claim_miniled"]},
            evidence_ids=["ev-claim-tv00029112"],
            confidence=Decimal("0.9000"),
            profile_hash="hash-claim-tv00029112",
            rule_version=CORE3_M04C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="m12d-comment-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M05C_TV_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            comment_sentence_count=20,
            matched_sentence_count=18,
            fact_atom_count=22,
            product_fact_sentence_count=18,
            positive_sentence_count=14,
            negative_sentence_count=2,
            service_excluded_sentence_count=1,
            dimension_summary_json={
                "picture_screen_experience": {"polarity_counts": {"positive": 8}}
            },
            signal_summary_json={"use_case_signal": ["客厅观影"]},
            param_comment_support_json={"screen_size_inch": {"positive": 3}},
            claim_comment_support_json={"tv_claim_miniled": {"positive": 5}},
            supported_param_codes=["screen_size_inch"],
            supported_claim_codes=["tv_claim_miniled"],
            contradicted_claim_codes=["tv_claim_high_refresh"],
            evidence_examples_json=[{"text": "画质清晰，客厅看电影不错"}],
            evidence_ids=["ev-comment-tv00029112"],
            confidence=Decimal("0.8800"),
            profile_hash="hash-comment-tv00029112",
            rule_version=CORE3_M05C_TV_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id="m12d-market-tv00029112",
            sku_market_profile_id="m12d-market-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            analysis_window="full_observed_window",
            active_week_count=12,
            market_row_count=24,
            platform_count=2,
            screen_size_inch=Decimal("65"),
            size_segment="large_60_69",
            screen_size_class="large_60_69",
            sales_volume_total=Decimal("1200"),
            sales_amount_total=Decimal("5998800"),
            price_wavg=Decimal("4999"),
            price_median=Decimal("4999"),
            price_latest=4999.0,
            price_band_category="mid_high",
            price_band_size="mid_high",
            price_percentile_in_size=Decimal("0.700000"),
            volume_percentile_in_size=Decimal("0.800000"),
            amount_percentile_in_size=Decimal("0.750000"),
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            evidence_ids=["ev-market-tv00029112"],
            market_evidence_ids=["ev-market-tv00029112"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint="fp-m07-tv00029112",
            result_hash="hash-m07-tv00029112",
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id="m12d-m09c-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M09C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_user_task_code="TASK_CINEMA_IMMERSION",
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=["TASK_PREMIUM_PICTURE_EXPERIENCE"],
            comment_observed_task_codes_json=["TASK_CINEMA_IMMERSION"],
            brand_claimed_task_codes_json=["TASK_PREMIUM_PICTURE_EXPERIENCE"],
            user_task_summary_json={"primary_reason_cn": "评论和卖点都支撑大屏观影。"},
            confidence=Decimal("0.8700"),
            evidence_ids_json=["ev-task-tv00029112"],
            profile_hash="hash-task-tv00029112",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id="m12d-m10c-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M10C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_target_group_code="TG_PREMIUM_AV_ENTHUSIAST",
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=["TG_MAINSTREAM_FAMILY_VIEWER"],
            comment_observed_group_codes_json=["TG_PREMIUM_AV_ENTHUSIAST"],
            target_group_summary_json={"primary_reason_cn": "影音体验用户匹配。"},
            confidence=Decimal("0.8500"),
            evidence_ids_json=["ev-group-tv00029112"],
            profile_hash="hash-group-tv00029112",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="m12d-m11c-profile-tv00029112",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            taxonomy_version=CORE3_M11C_TV_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_TV_RULE_VERSION,
            sku_code=sku_code,
            model_name="65E7Q",
            brand_name="海信",
            size_tier="large_60_69",
            price_band_in_size_tier="mid_high",
            primary_battlefield_code="BF_PREMIUM_PICTURE_UPGRADE",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=["BF_MAINSTREAM_LIVING_BALANCE"],
            opportunity_battlefield_codes_json=["BF_GAMING_SPORTS_FLUENCY"],
            drag_factor_battlefield_codes_json=["BF_SMART_CONNECTED_EXPERIENCE"],
            battlefield_summary_json={"primary_reason_cn": "MiniLED 与评论画质支撑。"},
            confidence=Decimal("0.8400"),
            evidence_ids_json=["ev-bf-tv00029112"],
            profile_hash="hash-bf-tv00029112",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="m12d-m11d-allocation-tv00029112-picture",
            project_id=project_id,
            category_code="TV",
            batch_id=batch_id,
            product_category="TV",
            dimension_type="battlefield",
            dimension_code="BF_PREMIUM_PICTURE_UPGRADE",
            dimension_name="高端画质升级战场",
            sku_code=sku_code,
            brand_name="海信",
            model_name="65E7Q",
            relation_status="primary_battlefield",
            allocation_role="primary",
            final_score=Decimal("0.8400"),
            allocation_basis=Decimal("0.840000"),
            relation_factor=Decimal("1.0000"),
            allocation_weight=Decimal("0.620000"),
            sales_volume_total=Decimal("1200"),
            sales_amount_total=Decimal("5998800"),
            allocation_confidence=Decimal("0.8600"),
            allocation_basis_json={"basis": "m11c_primary"},
            evidence_ids_json=["ev-m11d-tv00029112"],
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-m11d-tv00029112",
            result_hash="hash-m11d-tv00029112",
        )
    )
    if include_claim_value:
        session.add(
            entities.Core3SkuClaimValueQuantification(
                sku_claim_value_id="m12d-m12c-claim-value-tv00029112-miniled",
                pool_id="m12d-m12c-pool-miniled",
                project_id=project_id,
                category_code="TV",
                batch_id=batch_id,
                product_category="TV",
                sku_code=sku_code,
                brand_name="海信",
                model_name="65E7Q",
                claim_code="tv_claim_miniled_display",
                claim_name="MiniLED 画质",
                claim_dimension="picture_quality",
                claim_value_role="premium_driver_estimated",
                claim_evidence_strength=Decimal("0.9000"),
                param_support_strength=Decimal("0.9200"),
                comment_support_strength=Decimal("0.7600"),
                semantic_support_strength=Decimal("0.8300"),
                contribution_share_in_sku=Decimal("0.420000"),
                attribution_confidence=Decimal("0.8800"),
                supporting_dimensions_json={
                    "battlefield": ["BF_PREMIUM_PICTURE_UPGRADE"]
                },
                evidence_ids_json=["ev-m12c-tv00029112"],
                reason_cn="MiniLED 画质对价格承接有正向贡献。",
                result_hash="hash-m12c-tv00029112",
                rule_version=CORE3_M12C_TV_RULE_VERSION,
            )
        )
    session.commit()


def _seed_ac_m12d_context_inputs(session, *, include_claim_value: bool) -> None:
    project_id = "project_m12d_context_ac"
    batch_id = "batch_m12d_context_ac"
    sku_code = "AC00038063"
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="m12d-param-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            param_values_json={
                "installation_type": "柜机",
                "capacity_hp": "3匹",
                "cooling_capacity": 7200,
                "heating_capacity": 9600,
                "air_volume": 1300,
                "apf": 5.2,
                "energy_efficiency_level": "一级能效",
                "noise_db": 18,
                "fresh_air_volume": 60,
                "anti_direct_blow": True,
                "self_clean": True,
                "wifi": True,
            },
            param_completeness=Decimal("0.860000"),
            known_param_count=38,
            unknown_param_count=4,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["ev-param-ac00038063"],
            quality_summary_json={"status": "ok"},
            profile_hash="hash-param-ac00038063",
            seed_version="ac_param_taxonomy_manual_v0.1",
            rule_version=CORE3_M03B_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuClaimFactProfile(
            claim_profile_id="m12d-claim-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            taxonomy_version=CORE3_M04C_AC_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            raw_claim_count=6,
            matched_claim_count=6,
            fact_claim_count=5,
            unsupported_claim_count=1,
            claim_texts_json=[
                "速冷速热",
                "一级能效",
                "新风",
                "防直吹",
                "自清洁",
                "远程控制",
            ],
            claim_codes=[
                "temperature_performance",
                "energy_efficiency",
                "health_clean_air",
                "airflow_comfort",
                "smart_control",
            ],
            fact_claim_codes=[
                "temperature_performance",
                "energy_efficiency",
                "health_clean_air",
                "airflow_comfort",
                "smart_control",
            ],
            unsupported_claim_codes=[],
            dimension_profile_json={
                "temperature_performance": {"fact_claim_count": 2},
                "energy_efficiency": {"fact_claim_count": 1},
                "health_clean_air": {"fact_claim_count": 1},
                "airflow_comfort": {"fact_claim_count": 1},
                "smart_control": {"fact_claim_count": 1},
            },
            claim_summary_json={
                "keywords": ["速冷", "一级能效", "新风", "防直吹", "自清洁", "远程"]
            },
            evidence_ids=["ev-claim-ac00038063"],
            confidence=Decimal("0.9000"),
            profile_hash="hash-claim-ac00038063",
            rule_version=CORE3_M04C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuCommentFactProfile(
            comment_profile_id="m12d-comment-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            taxonomy_version=CORE3_M05C_AC_TAXONOMY_VERSION,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            comment_sentence_count=24,
            matched_sentence_count=21,
            fact_atom_count=25,
            product_fact_sentence_count=20,
            positive_sentence_count=16,
            negative_sentence_count=1,
            service_excluded_sentence_count=1,
            dimension_summary_json={
                "temperature_effect_experience": {"polarity_counts": {"positive": 8}},
                "energy_cost_experience": {"polarity_counts": {"positive": 3}},
                "airflow_comfort_experience": {"polarity_counts": {"positive": 5}},
                "health_air_experience": {"polarity_counts": {"positive": 2}},
            },
            signal_summary_json={
                "use_case_signal": ["客厅大空间", "卧室睡眠", "老人儿童"]
            },
            supported_param_codes=["capacity_hp", "air_volume", "apf"],
            supported_claim_codes=[
                "temperature_performance",
                "energy_efficiency",
                "health_clean_air",
            ],
            contradicted_claim_codes=[],
            evidence_examples_json=[
                {"text": "客厅制冷快，风感柔和不直吹，晚上睡觉也安静。"},
                {"text": "一级能效省电，新风打开后不闷，远程控制方便。"},
            ],
            evidence_ids=["ev-comment-ac00038063"],
            confidence=Decimal("0.8800"),
            profile_hash="hash-comment-ac00038063",
            rule_version=CORE3_M05C_AC_RULE_VERSION,
        )
    )
    session.add(
        entities.Core3SkuMarketProfile(
            profile_id="m12d-market-ac00038063",
            sku_market_profile_id="m12d-market-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            analysis_window="full_observed_window",
            active_week_count=12,
            market_row_count=24,
            platform_count=2,
            size_segment="floor_hp_3",
            screen_size_class="floor_hp_3",
            sales_volume_total=Decimal("13916"),
            sales_amount_total=Decimal("100309000"),
            price_wavg=Decimal("7208"),
            price_median=Decimal("7208"),
            price_latest=7208.0,
            price_band_category="mid_high",
            price_band_size="high",
            price_percentile_in_size=Decimal("0.780000"),
            volume_percentile_in_size=Decimal("0.820000"),
            amount_percentile_in_size=Decimal("0.840000"),
            market_confidence=Decimal("0.9000"),
            confidence_level="high",
            sample_status="sufficient",
            evidence_ids=["ev-market-ac00038063"],
            market_evidence_ids=["ev-market-ac00038063"],
            rule_version=CORE3_M07_RULE_VERSION,
            input_fingerprint="fp-m07-ac00038063",
            result_hash="hash-m07-ac00038063",
        )
    )
    session.add(
        entities.Core3M09cSkuUserTaskProfile(
            profile_id="m12d-m09c-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            taxonomy_version=CORE3_M09C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M09C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            size_tier="floor_hp_3",
            price_band_in_size_tier="mid_high",
            primary_user_task_code="large_space",
            primary_relation_status="primary_user_task",
            secondary_user_task_codes_json=["bedroom_sleep", "seasonal_reliability"],
            comment_observed_task_codes_json=["large_space"],
            brand_claimed_task_codes_json=["cooling_heating"],
            user_task_summary_json={
                "primary_reason_cn": "客厅大空间和季节冷暖任务明确。"
            },
            confidence=Decimal("0.8700"),
            evidence_ids_json=["ev-task-ac00038063"],
            profile_hash="hash-task-ac00038063",
        )
    )
    session.add(
        entities.Core3M10cSkuTargetGroupProfile(
            profile_id="m12d-m10c-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            taxonomy_version=CORE3_M10C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M10C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            size_tier="floor_hp_3",
            price_band_in_size_tier="mid_high",
            primary_target_group_code="family",
            primary_relation_status="primary_target_group",
            secondary_target_group_codes_json=["elderly_child"],
            comment_observed_group_codes_json=["family"],
            target_group_summary_json={"primary_reason_cn": "家庭和老人儿童场景匹配。"},
            confidence=Decimal("0.8500"),
            evidence_ids_json=["ev-group-ac00038063"],
            profile_hash="hash-group-ac00038063",
        )
    )
    session.add(
        entities.Core3SkuValueBattlefieldProfile(
            profile_id="m12d-m11c-profile-ac00038063",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            taxonomy_version=CORE3_M11C_AC_TAXONOMY_VERSION,
            rule_version=CORE3_M11C_AC_RULE_VERSION,
            sku_code=sku_code,
            model_name="KFR-88LW/N8KS1-1U",
            brand_name="美的",
            size_tier="floor_hp_3",
            price_band_in_size_tier="mid_high",
            primary_battlefield_code="BF_COOLING_HEATING_CAPACITY",
            primary_relation_status="primary_battlefield",
            secondary_battlefield_codes_json=[
                "BF_HEALTH_CLEAN_AIR",
                "BF_OPERATION_CONVENIENCE",
            ],
            opportunity_battlefield_codes_json=[],
            drag_factor_battlefield_codes_json=[],
            battlefield_summary_json={
                "primary_reason_cn": "冷暖能力和健康空气战场有支撑。"
            },
            confidence=Decimal("0.8400"),
            evidence_ids_json=["ev-bf-ac00038063"],
            profile_hash="hash-bf-ac00038063",
        )
    )
    session.add(
        entities.Core3SemanticMarketAllocation(
            allocation_id="m12d-m11d-allocation-ac00038063-capacity",
            project_id=project_id,
            category_code="AC",
            batch_id=batch_id,
            product_category="AC",
            dimension_type="battlefield",
            dimension_code="BF_COOLING_HEATING_CAPACITY",
            dimension_name="冷暖能力战场",
            sku_code=sku_code,
            brand_name="美的",
            model_name="KFR-88LW/N8KS1-1U",
            relation_status="primary_battlefield",
            allocation_role="primary",
            final_score=Decimal("0.8400"),
            allocation_basis=Decimal("0.840000"),
            relation_factor=Decimal("1.0000"),
            allocation_weight=Decimal("0.620000"),
            sales_volume_total=Decimal("13916"),
            sales_amount_total=Decimal("100309000"),
            allocation_confidence=Decimal("0.8600"),
            allocation_basis_json={"basis": "m11c_primary"},
            evidence_ids_json=["ev-m11d-ac00038063"],
            rule_version=CORE3_M11D_RULE_VERSION,
            input_fingerprint="fp-m11d-ac00038063",
            result_hash="hash-m11d-ac00038063",
        )
    )
    if include_claim_value:
        session.add(
            entities.Core3SkuClaimValueQuantification(
                sku_claim_value_id="m12d-m12c-claim-value-ac00038063-temperature",
                pool_id="m12d-m12c-pool-ac-temperature",
                project_id=project_id,
                category_code="AC",
                batch_id=batch_id,
                product_category="AC",
                sku_code=sku_code,
                brand_name="美的",
                model_name="KFR-88LW/N8KS1-1U",
                claim_code="ac_claim_fast_cooling_heating",
                claim_name="冷暖能力",
                claim_dimension="temperature_performance",
                claim_value_role="sales_driver_estimated",
                claim_evidence_strength=Decimal("0.9000"),
                param_support_strength=Decimal("0.9200"),
                comment_support_strength=Decimal("0.7600"),
                semantic_support_strength=Decimal("0.8300"),
                contribution_share_in_sku=Decimal("0.420000"),
                attribution_confidence=Decimal("0.8800"),
                supporting_dimensions_json={
                    "battlefield": ["BF_COOLING_HEATING_CAPACITY"]
                },
                evidence_ids_json=["ev-m12c-ac00038063"],
                reason_cn="冷暖能力对销量转化有正向贡献。",
                result_hash="hash-m12c-ac00038063",
                rule_version=CORE3_M12C_AC_RULE_VERSION,
            )
        )
    session.commit()
