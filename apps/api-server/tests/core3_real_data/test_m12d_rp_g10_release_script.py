import importlib.util
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = (
    Path(__file__).resolve().parents[4]
    / "scripts"
    / "m12d_rp_g10_publish_tv_ac.py"
)


def load_release_module():
    spec = importlib.util.spec_from_file_location("m12d_rp_g10_release", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_business_digest_ignores_technical_hashes_and_decimal_storage_shape() -> None:
    business_records_digest = load_release_module().business_records_digest
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
    business_records_digest = load_release_module().business_records_digest
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


def test_business_diff_reports_the_sku_anchor_and_changed_field() -> None:
    business_records_diff = load_release_module().business_records_diff
    expected_profile = SimpleNamespace(
        sku_code="TV001",
        status="ready",
        core_payment_anchors_json=["picture_upgrade"],
    )
    actual_profile = SimpleNamespace(
        sku_code="TV001",
        status="ready_limited",
        core_payment_anchors_json=[],
    )
    expected_anchor = SimpleNamespace(
        sku_code="TV001",
        anchor_code="picture_upgrade",
        role="core_payment",
        pressure_level="low",
    )
    actual_anchor = SimpleNamespace(
        sku_code="TV001",
        anchor_code="picture_upgrade",
        role="supporting",
        pressure_level="low",
    )

    result = business_records_diff(
        expected_profiles=[expected_profile],
        expected_anchors=[expected_anchor],
        actual_profiles=[actual_profile],
        actual_anchors=[actual_anchor],
    )

    assert result["difference_count"] == 2
    assert result["profile_difference_count"] == 1
    assert result["anchor_difference_count"] == 1
    assert result["difference_samples"][0]["key"] == ["TV001"]
    assert result["difference_samples"][0]["changed_fields"] == [
        "core_payment_anchors_json",
        "status",
    ]
