from decimal import Decimal
from types import SimpleNamespace

from scripts.m12d_rp_g10_publish_tv_ac import business_records_digest


def test_business_digest_ignores_technical_hashes_and_decimal_storage_shape() -> None:
    profile_fields = {
        "sku_code": "TV001",
        "status": "ready",
        "profile_confidence": Decimal("0.9000"),
        "core_payment_anchors_json": ["picture_upgrade"],
        "established_anchors_json": ["picture_upgrade"],
        "pressure_summary_json": {"highest_pressure_level": "low"},
        "result_hash": "run-one",
        "input_fingerprint": "input-one",
    }
    anchor_fields = {
        "sku_code": "TV001",
        "anchor_code": "picture_upgrade",
        "anchor_rank": 1,
        "role": "core_payment",
        "establishment_status": "established",
        "establishment_score": Decimal("9.0000"),
        "core_eligible": True,
        "pressure_level": "low",
        "domain_scores_json": {"param_fact": Decimal("3.0000")},
        "result_hash": "anchor-run-one",
    }

    first = business_records_digest(
        [SimpleNamespace(**profile_fields)], [SimpleNamespace(**anchor_fields)]
    )
    profile_fields.update(
        profile_confidence=0.9,
        result_hash="run-two",
        input_fingerprint="input-two",
    )
    anchor_fields.update(
        establishment_score=9.0,
        domain_scores_json={"param_fact": 3.0},
        result_hash="anchor-run-two",
    )
    second = business_records_digest(
        [SimpleNamespace(**profile_fields)], [SimpleNamespace(**anchor_fields)]
    )

    assert first == second


def test_business_digest_changes_when_purchase_reason_outcome_changes() -> None:
    profile = SimpleNamespace(
        sku_code="AC001",
        status="ready",
        core_payment_anchors_json=["energy_saving"],
    )
    anchor = SimpleNamespace(
        sku_code="AC001",
        anchor_code="energy_saving",
        role="core_payment",
        establishment_status="established",
        establishment_score=Decimal("9.0000"),
        core_eligible=True,
        pressure_level="none",
    )
    baseline = business_records_digest([profile], [anchor])

    anchor.pressure_level = "high"

    assert business_records_digest([profile], [anchor]) != baseline
