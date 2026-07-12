import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models import entities
from app.services.core3_real_data.constants import (
    M12DAnchorRole,
    M12DEvidenceStrength,
    M12DPurchasePressureLevel,
    M12DReasonEstablishmentStatus,
    M12DUserValidationStatus,
)
from app.services.core3_real_data.purchase_reason_profile_contract import (
    build_downstream_read_contract,
)
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DComparisonLimitation,
    M12DDownstreamAnchorContract,
    M12DPublishedProfile,
    M12DPurchasePressureTag,
    M12DPurchaseReasonAnchorRecord,
    M12DSourceRef,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "0044_core3_m12d_reason_pressure_contract.py"
)


def test_m12d_reason_pressure_anchor_contract_accepts_typed_business_fields() -> None:
    source_ref = M12DSourceRef(
        module_code="M05C",
        table_name="core3_comment_fact_atom",
        record_id="comment-1",
    )
    pressure = M12DPurchasePressureTag(
        pressure_type="mixed_feedback",
        pressure_level="medium",
        affected_aspect_code="reflection_control",
        affected_anchor_code="same_size_picture_step_up",
        positive_count=18,
        negative_count=3,
        dominance="positive",
        summary_cn="画质升级理由成立，但反光体验存在少量争议。",
        source_refs=[source_ref],
    )
    limitation = M12DComparisonLimitation(
        limitation_code="amount_not_quantifiable",
        scope="amount_wtp",
        summary_cn="当前只能比较相对价值，不能量化支付金额。",
        source_refs=[source_ref],
    )

    record = _anchor_record(
        establishment_status="established",
        establishment_score=Decimal("9.0000"),
        establishment_domains_json=[
            "param_fact",
            "comment_perception",
            "semantic_scene",
        ],
        user_validation_status="user_validated",
        core_eligible=True,
        user_support_evidence_json=[source_ref],
        pressure_level="medium",
        pressure_tags_json=[pressure],
        pressure_summary_cn="理由成立，同时存在中等购买阻力。",
        comparison_limitations_json=[limitation],
    )

    assert (
        record.establishment_status == M12DReasonEstablishmentStatus.ESTABLISHED.value
    )
    assert (
        record.user_validation_status == M12DUserValidationStatus.USER_VALIDATED.value
    )
    assert record.pressure_level == M12DPurchasePressureLevel.MEDIUM.value
    assert record.core_eligible is True
    assert record.pressure_tags_json[0].limits_establishment is False
    assert record.comparison_limitations_json[0].limits_comparison is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("establishment_status", "assumed_established"),
        ("user_validation_status", "probably_supported"),
        ("pressure_level", "very_high"),
    ],
)
def test_m12d_reason_pressure_contract_rejects_invalid_enums(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        _anchor_record(**{field: value})


def test_m12d_pressure_tag_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        M12DPurchasePressureTag(
            pressure_type="generic_negative",
            pressure_level="low",
            affected_anchor_code="reason_a",
        )


@pytest.mark.parametrize(("category", "sku_code"), [("TV", "TV001"), ("AC", "AC001")])
def test_m12d_legacy_rows_map_to_unassessed_without_guessing(
    category: str,
    sku_code: str,
) -> None:
    published = M12DPublishedProfile(
        version=SimpleNamespace(release_quality_status="ready"),
        profile=_legacy_profile(category=category, sku_code=sku_code),
        anchors=(_legacy_anchor(),),
    )

    contract = build_downstream_read_contract(
        published,
        lookup_key={"category_code": category, "sku_code": sku_code},
    )

    assert contract.profile is not None
    assert contract.profile.category_code == category
    assert contract.profile.established_anchors == []
    assert contract.profile.proposition_anchors == []
    anchor = contract.profile.anchors[0]
    assert anchor.establishment_status == M12DReasonEstablishmentStatus.UNASSESSED.value
    assert anchor.user_validation_status == M12DUserValidationStatus.UNASSESSED.value
    assert anchor.pressure_level == M12DPurchasePressureLevel.UNASSESSED.value
    assert anchor.core_eligible is None
    assert anchor.pressure_tags == []


def test_limited_version_does_not_degrade_ready_sku() -> None:
    profile = _legacy_profile(category="TV", sku_code="TV001")
    profile.established_anchors_json = ["reason_a"]
    profile.proposition_anchors_json = []
    anchor = _legacy_anchor()
    anchor.establishment_status = "established"
    anchor.establishment_score = Decimal("9.0000")
    anchor.user_validation_status = "user_validated"
    anchor.core_eligible = True

    contract = build_downstream_read_contract(
        M12DPublishedProfile(
            version=SimpleNamespace(release_quality_status="limited"),
            profile=profile,
            anchors=(anchor,),
        ),
        lookup_key={"category_code": "TV", "sku_code": "TV001"},
    )

    assert contract.consumption_state == "published_ready"
    assert contract.capabilities.comparison_mode == "strong"
    assert contract.capabilities.strong_reason_comparison_allowed is True
    assert contract.version_quality_notes
    assert "release_quality_status_limited" not in contract.profile.degradation_reasons


def test_proposition_only_sku_keeps_fact_dimensions_without_reason_comparison() -> None:
    profile = _legacy_profile(category="AC", sku_code="AC001")
    profile.status = "ready_limited"
    profile.core_reasons_json = []
    profile.core_payment_anchors_json = []
    profile.established_anchors_json = []
    profile.proposition_anchors_json = ["reason_a"]
    anchor = _legacy_anchor()
    anchor.role = "supporting"
    anchor.establishment_status = "proposition_only"
    anchor.establishment_score = Decimal("7.0000")
    anchor.user_validation_status = "not_observed"
    anchor.core_eligible = False

    contract = build_downstream_read_contract(
        M12DPublishedProfile(
            version=SimpleNamespace(release_quality_status="ready"),
            profile=profile,
            anchors=(anchor,),
        ),
        lookup_key={"category_code": "AC", "sku_code": "AC001"},
    )

    assert contract.consumption_state == "published_degraded"
    assert contract.capabilities.comparison_mode == "facts_only"
    assert contract.capabilities.fact_dimensions_allowed is True
    assert contract.capabilities.proposition_comparison_allowed is True
    assert contract.capabilities.established_reason_comparison_allowed is False
    assert contract.capabilities.strong_reason_comparison_allowed is False


def test_m12d_downstream_contract_exposes_business_fields_only() -> None:
    contract = M12DDownstreamAnchorContract(
        anchor_code="reason_a",
        anchor_cn="理由A",
        role=M12DAnchorRole.SUPPORTING,
        evidence_strength=M12DEvidenceStrength.MEDIUM,
        establishment_status="proposition_only",
        user_validation_status="not_observed",
        core_eligible=False,
        pressure_level="none",
    )

    payload = contract.model_dump(mode="json")

    assert {
        "establishment_status",
        "user_validation_status",
        "core_eligible",
        "pressure_level",
        "pressure_tags",
        "comparison_limitations",
    } <= set(payload)
    assert {
        "raw_evidence_score",
        "adjusted_evidence_score",
        "domain_scores_json",
        "role_reason_json",
        "downgrade_reason_code",
        "input_fingerprint",
        "taxonomy_generation_prompt",
    }.isdisjoint(payload)


def test_m12d_reason_pressure_columns_exist_on_profile_and_anchor_models() -> None:
    profile_columns = set(
        entities.Core3SkuPurchaseReasonProfile.__table__.columns.keys()
    )
    anchor_columns = set(entities.Core3SkuPurchaseReasonAnchor.__table__.columns.keys())

    assert {
        "established_anchors_json",
        "proposition_anchors_json",
        "pressure_summary_json",
        "comparison_limitations_json",
    } <= profile_columns
    assert {
        "establishment_status",
        "establishment_score",
        "establishment_domains_json",
        "user_validation_status",
        "core_eligible",
        "core_ineligible_reasons_json",
        "proposition_evidence_json",
        "user_support_evidence_json",
        "pressure_level",
        "pressure_tags_json",
        "pressure_summary_cn",
        "comparison_limitations_json",
    } <= anchor_columns


def test_m12d_reason_pressure_migration_adds_compatibility_columns(monkeypatch) -> None:
    module = _load_migration()
    added: dict[str, list[str]] = {
        "core3_sku_purchase_reason_profile": [],
        "core3_sku_purchase_reason_anchor": [],
    }

    class Inspector:
        def has_table(self, table_name: str) -> bool:
            return table_name in added

        def get_columns(self, table_name: str) -> list[dict[str, str]]:
            return []

    class Bind:
        def execute(self, _statement):
            return None

    monkeypatch.setattr(module.op, "get_bind", lambda: Bind())
    monkeypatch.setattr(module.sa, "inspect", lambda _bind: Inspector())
    monkeypatch.setattr(
        module.op,
        "add_column",
        lambda table_name, column: added[table_name].append(str(column.name)),
    )

    module.upgrade()

    assert set(added["core3_sku_purchase_reason_profile"]) == {
        "established_anchors_json",
        "proposition_anchors_json",
        "pressure_summary_json",
        "comparison_limitations_json",
    }
    assert set(added["core3_sku_purchase_reason_anchor"]) == {
        "establishment_status",
        "establishment_score",
        "establishment_domains_json",
        "user_validation_status",
        "core_eligible",
        "core_ineligible_reasons_json",
        "proposition_evidence_json",
        "user_support_evidence_json",
        "pressure_level",
        "pressure_tags_json",
        "pressure_summary_cn",
        "comparison_limitations_json",
    }


def _anchor_record(**updates) -> M12DPurchaseReasonAnchorRecord:
    payload = {
        "purchase_reason_anchor_id": "anchor-1",
        "project_id": "project-1",
        "batch_id": "batch-1",
        "m12d_profile_version": "m12d-v1",
        "sku_code": "TV001",
        "anchor_code": "same_size_picture_step_up",
        "anchor_cn": "同尺寸画质升级更值",
        "role": "supporting",
        "support_summary_cn": "测试证据。",
        "input_fingerprint": "fingerprint-1",
        "result_hash": "hash-1",
    }
    payload.update(updates)
    return M12DPurchaseReasonAnchorRecord.model_validate(payload)


def _legacy_profile(*, category: str, sku_code: str) -> SimpleNamespace:
    return SimpleNamespace(
        project_id="project-1",
        category_code=category,
        batch_id="batch-1",
        product_category=category,
        m12d_profile_version="m12d-v1",
        schema_version="schema-v1",
        rule_version="rule-v1",
        sku_code=sku_code,
        model_code=None,
        model_name=None,
        brand_name=None,
        display_name_cn=sku_code,
        status="ready",
        profile_confidence=Decimal("0.8000"),
        confidence_level="high",
        core_reasons_json=["理由A"],
        core_payment_anchors_json=["reason_a"],
        supporting_anchors_json=[],
        weak_expression_anchors_json=[],
        risk_drag_anchors_json=[],
        review_required=False,
        review_status="auto_pass",
        review_reason_json={},
        evidence_summary_json={},
        source_batch_ids_json=["source-1"],
        source_refs_json=[],
    )


def _legacy_anchor() -> SimpleNamespace:
    return SimpleNamespace(
        anchor_code="reason_a",
        anchor_cn="理由A",
        anchor_family_code="family_a",
        anchor_rank=1,
        role="core_payment",
        evidence_strength="strong",
        confidence=Decimal("0.8000"),
        evidence_domains_json=["param_fact", "semantic_scene"],
        support_summary_cn="历史证据。",
        weakness_summary_cn="",
        risk_flags_json=[],
        source_refs_json=[],
    )


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "m12d_reason_pressure_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
