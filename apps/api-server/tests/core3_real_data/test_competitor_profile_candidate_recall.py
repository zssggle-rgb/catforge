from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.competitor_profile_candidate_recall import (
    CandidateRecallEngine,
    CandidateRecallScopeError,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    ALL_RECALL_ENTRY_CODES,
    CandidateRecallConfig,
    CandidateRecallManifest,
    RecallEntryCoverage,
    RecallFact,
    RecalledCandidate,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    COMPETITOR_PROFILE_SOURCE_MODULES,
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
    ModuleCategorySnapshot,
    TargetModuleInput,
    UpstreamRecordSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_schemas import (
    EvidenceRef,
    ServingScope,
    SourceAuthorityRef,
)
from app.services.core3_real_data.hash_utils import stable_hash


def _sku(category: str, number: int) -> str:
    return f"{category}{number:06d}"


def _default_spec(category: str, number: int) -> dict[str, Any]:
    sku_code = _sku(category, number)
    return {
        "sku_code": sku_code,
        "brand": f"品牌{number}",
        "model": f"型号{number}",
        "price": Decimal("5000") + number,
        "weekly_volume": Decimal("100"),
        "screen_size": Decimal("65") if category == "TV" else None,
        "size_segment": "65" if category == "TV" else "1.5p",
        "market_pool": f"pool-{number}",
        "ac_form": "wall_mounted",
        "ac_capacity": "1.5p",
        "task_primary": f"task-{number}",
        "task_secondary": [],
        "audience_primary": f"audience-{number}",
        "battlefield_primary": f"battlefield-{number}",
        "battlefield_secondary": [],
        "battlefield_opportunity": [],
        "purchase_reasons": [f"reason-{number}"],
        "claim_values": [f"claim-{number}"],
        "missing_modules": set(),
    }


def _tv_specs() -> list[dict[str, Any]]:
    target = _default_spec("TV", 1)
    target.update(
        {
            "brand": "海信",
            "price": Decimal("5000"),
            "weekly_volume": Decimal("100"),
            "market_pool": "pool-65-main",
            "task_primary": "cinema",
            "task_secondary": ["gaming"],
            "audience_primary": "family-av",
            "battlefield_primary": "picture",
            "battlefield_secondary": ["smooth"],
            "battlefield_opportunity": ["gaming"],
            "purchase_reasons": ["clear-picture", "dark-detail"],
            "claim_values": ["bright-room-clear"],
        }
    )
    direct = _default_spec("TV", 2)
    direct.update(
        {
            "brand": "TCL",
            "price": Decimal("5100"),
            "weekly_volume": Decimal("120"),
            "market_pool": "pool-65-main",
            "task_primary": "cinema",
            "audience_primary": "family-av",
            "battlefield_primary": "picture",
            "purchase_reasons": ["clear-picture"],
            "claim_values": ["bright-room-clear"],
        }
    )
    uptrade = _default_spec("TV", 3)
    uptrade.update(
        {
            "brand": "海信",
            "price": Decimal("6000"),
            "weekly_volume": Decimal("70"),
            "market_pool": "pool-65-up",
            "task_primary": "gaming",
            "audience_primary": "console-player",
            "battlefield_primary": "gaming",
            "battlefield_secondary": ["picture"],
            "purchase_reasons": ["dark-detail"],
            "claim_values": ["high-refresh"],
        }
    )
    downtrade = _default_spec("TV", 4)
    downtrade.update(
        {
            "brand": "小米",
            "price": Decimal("4000"),
            "weekly_volume": Decimal("180"),
            "market_pool": "pool-65-down",
            "task_primary": "cinema",
            "audience_primary": "value-family",
            "battlefield_primary": "basic-picture",
            "purchase_reasons": ["simple-use"],
            "claim_values": ["bright-room-clear"],
        }
    )
    unrelated = _default_spec("TV", 5)
    unrelated.update(
        {
            "brand": "创维",
            "price": Decimal("9000"),
            "weekly_volume": Decimal("95"),
            "screen_size": Decimal("55"),
            "size_segment": "55",
            "market_pool": "pool-55-premium",
        }
    )
    sparse = _default_spec("TV", 6)
    sparse.update(
        {
            "brand": "康佳",
            "price": Decimal("5050"),
            "weekly_volume": Decimal("90"),
            "market_pool": "pool-65-main",
            "missing_modules": {"M09C", "M10C", "M11C", "M11D", "M12C", "M12D"},
        }
    )
    return [target, direct, uptrade, downtrade, unrelated, sparse]


def _facts(module_code: str, spec: dict[str, Any]) -> list[dict[str, Any]]:
    if module_code in spec["missing_modules"]:
        return []
    common = {
        "sku_code": spec["sku_code"],
        "brand_name": spec["brand"],
        "model_name": spec["model"],
    }
    if module_code == "M03B":
        return [
            {
                **common,
                "param_values_json": {
                    "ac_product_form": {"normalized_value": spec["ac_form"]},
                    "cooling_capacity_segment": {
                        "normalized_value": spec["ac_capacity"]
                    },
                },
            }
        ]
    if module_code == "M07":
        return [
            {
                **common,
                "brand": spec["brand"],
                "price_wavg": spec["price"],
                "sales_volume_total": spec["weekly_volume"] * Decimal("10"),
                "active_week_count": 10,
                "screen_size_inch": spec["screen_size"],
                "size_segment": spec["size_segment"],
                "market_pool_key": spec["market_pool"],
                "price_band_size": "middle",
            }
        ]
    if module_code == "M09C":
        return [
            {
                **common,
                "primary_user_task_code": spec["task_primary"],
                "secondary_user_task_codes_json": spec["task_secondary"],
                "comment_observed_task_codes_json": [],
                "latent_capability_task_codes_json": [],
            }
        ]
    if module_code == "M10C":
        return [
            {
                **common,
                "primary_target_group_code": spec["audience_primary"],
                "secondary_target_group_codes_json": [],
                "comment_observed_group_codes_json": [],
                "latent_group_codes_json": [],
            }
        ]
    if module_code == "M11C":
        return [
            {
                **common,
                "primary_battlefield_code": spec["battlefield_primary"],
                "secondary_battlefield_codes_json": spec["battlefield_secondary"],
                "opportunity_battlefield_codes_json": spec[
                    "battlefield_opportunity"
                ],
            }
        ]
    if module_code == "M11D":
        return [
            {
                **common,
                "dimension_type": "battlefield",
                "dimension_code": spec["battlefield_primary"],
                "allocation_role": "primary",
            }
        ]
    if module_code == "M12C":
        return [
            {
                **common,
                "claim_code": claim_code,
                "claim_value_role": "value_bundle_claim",
            }
            for claim_code in spec["claim_values"]
        ]
    if module_code == "M12D":
        return [
            {
                **common,
                "display_name_cn": f"{spec['brand']} {spec['model']}",
                "core_payment_anchors_json": [
                    {"anchor_code": value} for value in spec["purchase_reasons"]
                ],
                "established_anchors_json": [],
                "core_reasons_json": [],
            }
        ]
    return [{**common, "profile_status": "ready"}]


def _snapshot(
    category: str,
    module_code: str,
    spec: dict[str, Any],
    facts: dict[str, Any],
    index: int,
) -> UpstreamRecordSnapshot:
    sku_code = spec["sku_code"]
    return UpstreamRecordSnapshot(
        module_code=module_code,
        record_type=f"test_{module_code.lower()}_record",
        record_id=f"{module_code.lower()}-{sku_code}-{index}",
        sku_code=sku_code,
        project_id=f"project-{category.lower()}",
        category_code=category,
        product_category=category,
        source_batch_id="batch-1",
        profile_version=f"{module_code.lower()}-profile-v1",
        schema_version=f"{module_code.lower()}-schema-v1",
        rule_version=f"{module_code.lower()}-rule-v1",
        taxonomy_version=f"{module_code.lower()}-taxonomy-v1",
        result_hash=stable_hash(
            {"module": module_code, "sku": sku_code, "index": index},
            version="test_upstream_record_v1",
        ),
        facts=facts,
    )


def _authority(category: str, module_code: str) -> SourceAuthorityRef:
    return SourceAuthorityRef(
        module_code=module_code,
        project_id=f"project-{category.lower()}",
        category_code=category,
        product_category=category,
        profile_version=f"{module_code.lower()}-profile-v1",
        schema_version=f"{module_code.lower()}-schema-v1",
        rule_version=f"{module_code.lower()}-rule-v1",
        taxonomy_version=f"{module_code.lower()}-taxonomy-v1",
        release_status="published",
        is_current=True,
        source_batch_ids=["batch-1"],
        result_hash=stable_hash(module_code, version="test_authority_v1"),
    )


def _category_bundle(
    category: str = "TV",
    specs: list[dict[str, Any]] | None = None,
    *,
    reorder_semantic_values: bool = False,
) -> CompetitorProfileCategoryInputBundle:
    source_specs = specs or _tv_specs()
    if reorder_semantic_values:
        source_specs = [dict(spec) for spec in source_specs]
        for spec in source_specs:
            spec["task_secondary"] = list(reversed(spec["task_secondary"]))
            spec["battlefield_secondary"] = list(
                reversed(spec["battlefield_secondary"])
            )
            spec["battlefield_opportunity"] = list(
                reversed(spec["battlefield_opportunity"])
            )
            spec["purchase_reasons"] = list(reversed(spec["purchase_reasons"]))
            spec["claim_values"] = list(reversed(spec["claim_values"]))
    sku_codes = sorted(spec["sku_code"] for spec in source_specs)
    authorities = {
        code: _authority(category, code) for code in COMPETITOR_PROFILE_SOURCE_MODULES
    }
    modules: dict[str, ModuleCategorySnapshot] = {}
    for module_code in COMPETITOR_PROFILE_SOURCE_MODULES:
        records_by_sku: dict[str, list[UpstreamRecordSnapshot]] = {}
        for spec in sorted(source_specs, key=lambda row: row["sku_code"]):
            rows = [
                _snapshot(category, module_code, spec, facts, index)
                for index, facts in enumerate(_facts(module_code, spec), start=1)
            ]
            if rows:
                records_by_sku[spec["sku_code"]] = rows
        record_count = sum(len(rows) for rows in records_by_sku.values())
        modules[module_code] = ModuleCategorySnapshot(
            module_code=module_code,
            authority=authorities[module_code],
            hard_required_for_target=module_code in {"M03B", "M07"},
            record_count=record_count,
            sku_count=len(records_by_sku),
            records_by_sku=records_by_sku,
            result_hash=authorities[module_code].result_hash,
        )
    scope = ServingScope(
        project_id=f"project-{category.lower()}",
        category_code=category,
        product_category=category,
        analysis_population="competitor_profile_full_published_scope",
        market_window="full_observed_window",
        taxonomy_version=f"competitor-profile-{category.lower()}-manifest-v1",
        storage_batch_id="batch-1",
        source_batch_ids=["batch-1"],
        source_authorities=authorities,
        sku_prefixes=[category],
        authoritative_sku_count=len(sku_codes),
        authoritative_sku_manifest_hash=stable_hash(
            sku_codes,
            version="test_authoritative_manifest_v1",
        ),
        release_scope_key=f"project-{category.lower()}:{category}:scope-v1",
    )
    return CompetitorProfileCategoryInputBundle(
        serving_scope=scope,
        authoritative_sku_codes=sku_codes,
        modules=modules,
        input_fingerprint="category-input-stable-v1",
    )


def _evidence_ref(row: UpstreamRecordSnapshot) -> EvidenceRef:
    return EvidenceRef(
        module_code=row.module_code,
        profile_version=row.profile_version,
        rule_version=row.rule_version,
        taxonomy_version=row.taxonomy_version,
        record_type=row.record_type,
        record_id=row.record_id,
        result_hash=row.result_hash,
        source_batch_id=row.source_batch_id,
    )


def _target_bundle(
    category_bundle: CompetitorProfileCategoryInputBundle,
    target_sku_code: str,
) -> CompetitorProfileTargetInputBundle:
    module_inputs: dict[str, TargetModuleInput] = {}
    limitations: list[str] = []
    hard_blocks: list[str] = []
    evidence: list[EvidenceRef] = []
    for module_code in sorted(category_bundle.modules):
        rows = category_bundle.modules[module_code].records_by_sku.get(
            target_sku_code,
            [],
        )
        if rows:
            refs = [_evidence_ref(row) for row in rows]
            evidence.extend(refs)
            module_inputs[module_code] = TargetModuleInput(
                module_code=module_code,
                availability="present",
                hard_required=module_code in {"M03B", "M07"},
                records=rows,
                evidence_refs=refs,
                input_fingerprint=f"target-{module_code}-present",
            )
        else:
            reason = f"{module_code.lower()}_sku_not_covered_by_locked_authority"
            if module_code in {"M03B", "M07"}:
                hard_blocks.append(reason)
            else:
                limitations.append(reason)
            module_inputs[module_code] = TargetModuleInput(
                module_code=module_code,
                availability="unknown",
                hard_required=module_code in {"M03B", "M07"},
                missing_reason_code=reason,
                input_fingerprint=f"target-{module_code}-unknown",
            )
    market = module_inputs["M07"].records[0].facts if module_inputs["M07"].records else {}
    analysis_state = "blocked" if hard_blocks else "partial" if limitations else "ready"
    return CompetitorProfileTargetInputBundle(
        serving_scope=category_bundle.serving_scope,
        target_sku_code=target_sku_code,
        target_identity={
            "sku_code": target_sku_code,
            "brand_name": market.get("brand_name"),
            "model_name": market.get("model_name"),
            "product_category": category_bundle.serving_scope.product_category,
        },
        modules=module_inputs,
        analysis_state=analysis_state,
        hard_block_reasons=sorted(hard_blocks),
        limitations=sorted(limitations),
        evidence_refs=sorted(
            evidence,
            key=lambda row: (
                row.module_code,
                row.source_batch_id or "",
                row.record_id,
            ),
        ),
        input_fingerprint=f"target-input-{target_sku_code}",
    )


def _recall(
    bundle: CompetitorProfileCategoryInputBundle,
    target_sku_code: str,
) -> CandidateRecallManifest:
    return CandidateRecallEngine().recall(
        bundle,
        _target_bundle(bundle, target_sku_code),
    )


def test_tv_recall_keeps_all_entries_and_merges_one_candidate_pair() -> None:
    bundle = _category_bundle()
    manifest = _recall(bundle, "TV000001")
    by_sku = {row.candidate.sku_code: row for row in manifest.candidates}

    assert "TV000005" not in by_sku
    assert manifest.candidate_count == 4
    direct = by_sku["TV000002"]
    assert direct.recall_sources == [
        "market_reference",
        "same_purchase_pool",
        "same_value",
        "scenario",
    ]
    assert {
        row.reason_code for row in direct.recall_facts
    } >= {
        "same_budget_compatible_product",
        "same_primary_battlefield",
        "shared_purchase_reason",
        "shared_claim_value",
        "shared_user_task",
        "same_market_pool_baseline",
    }
    assert len({row.candidate.sku_code for row in manifest.candidates}) == 4
    assert all(row.evidence_refs for row in manifest.candidates)


def test_uptrade_downtrade_same_brand_and_adjacent_battlefield_are_recalled() -> None:
    manifest = _recall(_category_bundle(), "TV000001")
    by_sku = {row.candidate.sku_code: row for row in manifest.candidates}

    assert set(by_sku["TV000003"].recall_sources) >= {
        "same_brand_ladder",
        "uptrade",
        "same_value",
    }
    assert any(
        fact.reason_code == "adjacent_secondary_or_opportunity_battlefield"
        and fact.matched_values == ["gaming"]
        for fact in by_sku["TV000003"].recall_facts
    )
    assert set(by_sku["TV000004"].recall_sources) >= {
        "downtrade",
        "same_value",
    }
    assert any(
        fact.reason_code == "downtrade_shared_claim_value"
        for fact in by_sku["TV000004"].recall_facts
    )


def test_sparse_candidate_stays_recalled_with_typed_unknown_reasons() -> None:
    manifest = _recall(_category_bundle(), "TV000001")
    sparse = next(
        row for row in manifest.candidates if row.candidate.sku_code == "TV000006"
    )

    assert sparse.recall_sources == ["market_reference", "same_purchase_pool"]
    assert "candidate_m11c_unknown" in sparse.unknown_reason_codes
    assert "candidate_m12d_unknown" in sparse.unknown_reason_codes
    assert manifest.entry_coverage["same_value"].status == "available"


def test_recall_has_no_fixed_candidate_limit() -> None:
    specs = [_default_spec("TV", 1)]
    specs[0].update(
        {
            "brand": "目标品牌",
            "price": Decimal("5000"),
            "market_pool": "large-pool",
            "task_primary": "target-task",
            "battlefield_primary": "target-value",
            "purchase_reasons": ["target-reason"],
            "claim_values": ["target-claim"],
        }
    )
    for number in range(2, 43):
        spec = _default_spec("TV", number)
        spec.update(
            {
                "price": Decimal("5000") + Decimal(number),
                "market_pool": "large-pool",
            }
        )
        specs.append(spec)

    manifest = _recall(_category_bundle(specs=specs), "TV000001")
    assert manifest.candidate_count == 41
    assert [row.candidate.sku_code for row in manifest.candidates] == [
        _sku("TV", number) for number in range(2, 43)
    ]


def test_semantic_input_list_order_does_not_change_recall_hash() -> None:
    first = _recall(_category_bundle(), "TV000001")
    reordered = _recall(
        _category_bundle(reorder_semantic_values=True),
        "TV000001",
    )
    assert reordered.result_hash == first.result_hash
    assert [row.result_hash for row in reordered.candidates] == [
        row.result_hash for row in first.candidates
    ]


def test_ac_recall_requires_form_and_capacity_compatibility_for_purchase_pool() -> None:
    target = _default_spec("AC", 1)
    target.update(
        {
            "brand": "格力",
            "price": Decimal("3200"),
            "market_pool": "ac-wall-1.5p",
        }
    )
    compatible = _default_spec("AC", 2)
    compatible.update(
        {
            "brand": "美的",
            "price": Decimal("3300"),
            "market_pool": "ac-wall-1.5p",
        }
    )
    wrong_form = _default_spec("AC", 3)
    wrong_form.update(
        {
            "brand": "海尔",
            "price": Decimal("3250"),
            "market_pool": "ac-floor-1.5p",
            "ac_form": "floor_standing",
        }
    )
    manifest = _recall(
        _category_bundle("AC", [target, compatible, wrong_form]),
        "AC000001",
    )
    by_sku = {row.candidate.sku_code: row for row in manifest.candidates}

    assert "same_purchase_pool" in by_sku["AC000002"].recall_sources
    assert "AC000003" not in by_sku


def test_cross_scope_and_blocked_target_fail_closed() -> None:
    tv_bundle = _category_bundle()
    ac_spec = [_default_spec("AC", 1), _default_spec("AC", 2)]
    ac_bundle = _category_bundle("AC", ac_spec)

    with pytest.raises(CandidateRecallScopeError, match="same serving scope"):
        CandidateRecallEngine().recall(
            tv_bundle,
            _target_bundle(ac_bundle, "AC000001"),
        )

    specs = _tv_specs()
    specs[0] = dict(specs[0])
    specs[0]["missing_modules"] = {"M03B"}
    blocked_bundle = _category_bundle(specs=specs)
    with pytest.raises(CandidateRecallScopeError, match="blocked target"):
        CandidateRecallEngine().recall(
            blocked_bundle,
            _target_bundle(blocked_bundle, "TV000001"),
        )


def test_empty_manifest_and_partial_entry_coverage_are_explicit() -> None:
    target = _default_spec("TV", 1)
    target["missing_modules"] = {"M11C", "M12C"}
    unrelated = _default_spec("TV", 2)
    unrelated.update(
        {
            "price": Decimal("9000"),
            "screen_size": Decimal("55"),
            "size_segment": "55",
            "market_pool": "unrelated-pool",
            "weekly_volume": Decimal("100"),
        }
    )
    bundle = _category_bundle(specs=[target, unrelated])
    manifest = _recall(bundle, "TV000001")

    assert manifest.candidate_count == 0
    assert manifest.candidates == []
    assert manifest.limitations == [
        "candidate_recall_manifest_empty",
        "m11c_sku_not_covered_by_locked_authority",
        "m12c_sku_not_covered_by_locked_authority",
    ]
    assert manifest.entry_coverage["same_value"].status == "partial"
    assert manifest.entry_coverage["same_value"].target_missing_modules == [
        "M11C",
        "M12C",
    ]


def test_disabled_entries_stay_disabled_without_changing_candidate_limit() -> None:
    bundle = _category_bundle()
    config = CandidateRecallConfig(
        config_version="test_market_reference_only_v1",
        enabled_entries=["market_reference"],
    )
    manifest = CandidateRecallEngine().recall(
        bundle,
        _target_bundle(bundle, "TV000001"),
        config,
    )

    assert manifest.entry_coverage["market_reference"].status == "available"
    assert all(
        coverage.status == "disabled"
        for code, coverage in manifest.entry_coverage.items()
        if code != "market_reference"
    )
    assert all(row.recall_sources == ["market_reference"] for row in manifest.candidates)


def test_recall_config_and_manifest_schema_reject_hidden_limits_and_drift() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        CandidateRecallConfig(max_candidates=12)
    with pytest.raises(ValidationError, match="sorted and unique"):
        CandidateRecallConfig(enabled_entries=["scenario", "downtrade"])
    with pytest.raises(ValidationError, match="below adjacent"):
        CandidateRecallConfig(
            same_budget_pct=Decimal("0.30"),
            adjacent_budget_pct=Decimal("0.15"),
        )

    manifest = _recall(_category_bundle(), "TV000001")
    assert set(manifest.entry_coverage) == set(ALL_RECALL_ENTRY_CODES)
    payload = manifest.model_dump(mode="python")
    payload["candidate_count"] += 1
    with pytest.raises(ValidationError, match="candidate count"):
        CandidateRecallManifest.model_validate(payload)


def test_recall_config_rejects_threshold_and_category_mapping_drift() -> None:
    with pytest.raises(ValidationError, match="direction threshold"):
        CandidateRecallConfig(
            price_direction_min_pct=Decimal("0.20"),
            strong_price_difference_pct=Decimal("0.15"),
        )
    with pytest.raises(ValidationError, match="ac_form_param_codes"):
        CandidateRecallConfig(
            ac_form_param_codes=["product_form", "ac_product_form"],
        )
    with pytest.raises(ValidationError, match="new config version"):
        CandidateRecallConfig(enabled_entries=["market_reference"])
    assert CandidateRecallConfig(
        config_version="test_market_reference_only_v1",
        enabled_entries=["market_reference"],
    ).config_version == "test_market_reference_only_v1"


def test_recall_dtos_reject_order_membership_and_coverage_contradictions() -> None:
    manifest = _recall(_category_bundle(), "TV000001")
    candidate = manifest.candidates[0]
    fact = next(
        row
        for row in candidate.recall_facts
        if len(row.target_evidence_refs) > 1
    )

    fact_payload = fact.model_dump(mode="python")
    fact_payload["matched_values"] = ["z-value", "a-value"]
    with pytest.raises(ValidationError, match="matched values"):
        RecallFact.model_validate(fact_payload)

    fact_payload = fact.model_dump(mode="python")
    fact_payload["target_evidence_refs"] = list(
        reversed(fact_payload["target_evidence_refs"])
    )
    with pytest.raises(ValidationError, match="evidence refs"):
        RecallFact.model_validate(fact_payload)

    candidate_payload = candidate.model_dump(mode="python")
    candidate_payload["recall_sources"] = list(
        reversed(candidate_payload["recall_sources"])
    )
    with pytest.raises(ValidationError, match="sources"):
        RecalledCandidate.model_validate(candidate_payload)

    candidate_payload = candidate.model_dump(mode="python")
    candidate_payload["recall_facts"] = list(
        reversed(candidate_payload["recall_facts"])
    )
    with pytest.raises(ValidationError, match="facts"):
        RecalledCandidate.model_validate(candidate_payload)

    coverage = manifest.entry_coverage["market_reference"].model_dump(mode="python")
    coverage["status"] = "disabled"
    with pytest.raises(ValidationError, match="cannot have candidates"):
        RecallEntryCoverage.model_validate(coverage)

    payload = manifest.model_dump(mode="python")
    payload["candidates"] = list(reversed(payload["candidates"]))
    with pytest.raises(ValidationError, match="sorted and unique"):
        CandidateRecallManifest.model_validate(payload)

    payload = manifest.model_dump(mode="python")
    payload["entry_coverage"] = dict(payload["entry_coverage"])
    payload["entry_coverage"].pop("same_value")
    with pytest.raises(ValidationError, match="coverage for every entry"):
        CandidateRecallManifest.model_validate(payload)
