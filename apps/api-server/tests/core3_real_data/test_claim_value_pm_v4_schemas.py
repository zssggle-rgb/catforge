from __future__ import annotations

import json
from copy import deepcopy
from typing import get_args

import pytest
from pydantic import TypeAdapter, ValidationError

from app.services.core3_real_data.analyst.analyst_repository import (
    build_sellpoint_value_v4_lineage_gate,
    canonical_v4_hash,
)
from app.services.core3_real_data.analyst.claim_value_pm_v4_schemas import (
    ComparablePoolTierFact,
    EvidenceRef,
    LineageGate,
    MarketCellRow,
    MarketImpliedWtp,
    SourceAuthority,
    ValueStatus,
)


MODULES = ("M03B", "M04C", "M05C", "M07", "M09C", "M10C", "M11C", "M11D", "M12C")


def _ref(
    module_code: str, *, rule_version: str = "v1", result_hash: str = "hash-v1"
) -> EvidenceRef:
    return EvidenceRef(
        module_code=module_code,
        record_type=f"table_{module_code.lower()}",
        record_id=f"record-{module_code}",
        result_hash=result_hash,
        batch_id="batch-1",
        rule_version=rule_version,
    )


def _authority(
    module_code: str, *, rule_version: str = "v1", result_hash: str = "hash-v1"
) -> SourceAuthority:
    ref = _ref(module_code, rule_version=rule_version, result_hash=result_hash)
    return SourceAuthority(
        module_code=module_code,
        table_name=ref.record_type,
        authority_mode="configured_rule",
        rule_version=rule_version,
        selected_batch_ids=["batch-1"],
        row_count=1,
        availability="present",
        usability="usable",
        source_hash=result_hash,
        selected_reason="test",
    )


def test_models_forbid_unknown_fields() -> None:
    payload = _ref("M03B").model_dump()
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="extra_forbidden"):
        EvidenceRef.model_validate(payload)


def test_missing_authority_cannot_contain_rows_or_be_usable() -> None:
    with pytest.raises(
        ValidationError, match="missing authority cannot contain selected rows"
    ):
        SourceAuthority(
            module_code="M03B",
            table_name="core3_sku_param_profile",
            authority_mode="configured_rule",
            rule_version="v1",
            selected_batch_ids=["batch-1"],
            row_count=1,
            availability="missing",
            usability="usable",
            selected_reason="invalid",
        )


def test_market_cell_inventory_is_explicitly_unavailable() -> None:
    payload = {
        "sku_code": "TV1",
        "battlefield_code": "unknown",
        "period_week_index": 1,
        "platform_type": "jd",
        "price_check_status": "ok",
        "promotion_suspect": False,
        "inventory_status": "unavailable",
        "source_ref": _ref("M07"),
    }

    cell = MarketCellRow.model_validate(payload)

    assert cell.inventory_status == "unavailable"
    with pytest.raises(ValidationError):
        MarketCellRow.model_validate({**payload, "inventory_status": "in_stock"})


def test_pool_counts_cannot_exceed_pool_size() -> None:
    payload = {
        "claim_code": "claim",
        "bundle_code": "bundle",
        "context_code": "all",
        "comparison_basis": "market_pool",
        "pool_sku_count": 2,
        "with_count": 1,
        "without_count": 1,
        "unknown_count": 1,
        "sample_status": "usable",
        "pool_hash": "hash",
    }

    with pytest.raises(ValidationError, match="pool counts cannot exceed"):
        ComparablePoolTierFact.model_validate(payload)


def test_canonical_hash_ignores_mapping_order_but_not_value_changes() -> None:
    left = {"b": [2, 1], "a": {"x": "值"}}
    right = {"a": {"x": "值"}, "b": [2, 1]}

    assert canonical_v4_hash(left) == canonical_v4_hash(right)
    assert canonical_v4_hash(left) != canonical_v4_hash({"b": [1, 2], "a": {"x": "值"}})


def test_g08r1_contract_addendum_matches_runtime(repo_root) -> None:
    contract = json.loads(
        (
            repo_root
            / "docs/core3_mvp/real_data_v2/current_implementation/sellpoint_value_pm_v4/G08R1_schema_contract_addendum.json"
        ).read_text(encoding="utf-8")
    )

    expected_statuses = contract["overrides"]["enums.ValueStatus"]
    assert list(get_args(ValueStatus)) == expected_statuses
    for status in expected_statuses:
        assert TypeAdapter(ValueStatus).validate_python(status) == status
    with pytest.raises(ValidationError):
        TypeAdapter(ValueStatus).validate_python("conflicted")

    expected_method = contract["overrides"][
        "models.MarketImpliedWtp.fields.method_config_version"
    ]
    field = MarketImpliedWtp.model_fields["method_config_version"]
    assert get_args(field.annotation) == (expected_method,)


def test_lineage_is_aligned_only_when_rule_and_record_hash_match() -> None:
    published = [_authority(module) for module in MODULES]
    current = deepcopy(published)

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=published,
        current_validation_lineage=current,
    )

    assert result.status == "aligned"
    assert result.issues == []


def test_changed_version_and_hash_is_a_localized_blocking_conflict() -> None:
    published = [_authority(module) for module in MODULES]
    current = [_authority(module) for module in MODULES]
    current[0] = _authority("M03B", rule_version="v2", result_hash="hash-v2")

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=published,
        current_validation_lineage=current,
    )

    assert result.status == "stale_conflict"
    assert result.blocked_reason_codes == ["version_lineage_conflict"]
    assert [issue.affected_module_codes for issue in result.issues] == [["M03B"]]


def test_changed_version_with_identical_record_hash_is_revalidated() -> None:
    published = [_authority(module) for module in MODULES]
    current = [_authority(module) for module in MODULES]
    current[0] = _authority("M03B", rule_version="v2", result_hash="hash-v1")

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=published,
        current_validation_lineage=current,
    )

    assert result.status == "stale_revalidated"
    assert result.blocked_reason_codes == []


def test_missing_published_lineage_is_unknown_not_false() -> None:
    current = [_authority(module) for module in MODULES]

    result = build_sellpoint_value_v4_lineage_gate(
        published_lineage=current[:-1],
        current_validation_lineage=current,
    )

    assert result.status == "unresolved"
    assert any(issue.code == "published_lineage_missing" for issue in result.issues)


def test_stale_conflict_contract_requires_explicit_issue() -> None:
    with pytest.raises(ValidationError, match="stale_conflict requires"):
        LineageGate(
            status="stale_conflict",
            published_lineage=[],
            current_validation_lineage=[],
            issues=[],
        )
