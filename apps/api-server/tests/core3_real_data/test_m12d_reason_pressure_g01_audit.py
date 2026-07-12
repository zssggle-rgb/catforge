import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[4] / "scripts" / "m12d_rp_g01_audit_tv_ac_baseline.py"


def load_audit_module():
    spec = importlib.util.spec_from_file_location("m12d_rp_g01_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_comment_alignment_is_anchor_and_category_scoped():
    audit = load_audit_module()
    picture_fact = {
        "dimension_code": "picture_screen_experience",
        "subdimension_code": "picture_clarity_resolution",
    }
    price_fact = {
        "dimension_code": "price_value_perception",
        "subdimension_code": "value_price",
    }

    assert audit.comment_aligns("TV", "picture_upgrade_justifies_price", picture_fact)
    assert not audit.comment_aligns("TV", "picture_upgrade_justifies_price", price_fact)
    assert not audit.comment_aligns("AC", "picture_upgrade_justifies_price", picture_fact)


def test_positive_m12c_roles_do_not_disappear_when_negative_pressure_coexists():
    audit = load_audit_module()
    summary = {
        "anchor_claim_value_roles": {
            "reason_a": {
                "claim_positive": ["sales_driver_estimated"],
                "claim_negative": ["drag_factor"],
            }
        }
    }

    roles = audit.anchor_claim_value_roles(summary, "reason_a")

    assert "sales_driver_estimated" in roles
    assert "drag_factor" in roles
    assert set(roles) & audit.POSITIVE_M12C_ROLES


def test_unaffected_regression_preserves_core_availability():
    audit = load_audit_module()
    no_core = {
        "current": {"core_anchors": []},
        "audit_summary": {"established_anchors": []},
        "anchors": [],
    }
    retained_core = {
        "current": {"core_anchors": ["reason_a"]},
        "audit_summary": {"established_anchors": ["reason_a"]},
        "anchors": [{"anchor_code": "reason_a", "audit": {"established": True}}],
    }
    lost_core = {
        "current": {"core_anchors": ["reason_a"]},
        "audit_summary": {"established_anchors": []},
        "anchors": [{"anchor_code": "reason_a", "audit": {"established": False}}],
    }

    assert audit.current_core_unaffected(no_core)
    assert audit.current_core_unaffected(retained_core)
    assert not audit.current_core_unaffected(lost_core)
