from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticSerializationError

from app.services.core3_real_data.analyst import competitor_profile_v1_1_schemas as s


REAL_FIXTURE_NAMES = (
    "G28_65e7q_legacy_analysis_default20_205_20260715.json.gz",
    "G28_tv_partial_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_complete_legacy_analysis_default20_205_20260715.json.gz",
    "G28_ac_partial_legacy_analysis_default20_205_20260715.json.gz",
)


def _repo_root() -> Path:
    return next(
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / "apps").is_dir() and (parent / "docs").is_dir()
    )


def _artifact_dir() -> Path:
    return (
        _repo_root()
        / "docs/core3_mvp/real_data_v2/current_implementation/competitor_profile_v1"
    )


def _load_builder() -> ModuleType:
    path = _artifact_dir() / "G29_build_typed_mapping_contract.py"
    spec = importlib.util.spec_from_file_location("g29_typed_mapping", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _collect_mapping_keys(value: object) -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            keys.append(str(key))
            keys.extend(_collect_mapping_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.extend(_collect_mapping_keys(child))
    return keys


def _assert_projected_field_equal(model: object, raw: dict, field_name: str) -> None:
    if field_name not in raw:
        return
    actual = getattr(model, field_name)
    expected = raw[field_name]
    if hasattr(actual, "model_dump"):
        assert actual.model_dump(mode="json", exclude_none=True) == json.loads(
            json.dumps(expected),
            parse_float=str,
        )
    elif isinstance(actual, Decimal):
        assert actual == Decimal(str(expected))
    else:
        assert actual == expected


def _conclusion(
    *,
    code: str = "supported_result",
    strength: str = "supported",
    direction: str = "target_stronger",
) -> dict:
    if strength == "unknown":
        return {
            "conclusion_code": code,
            "subject": "T1:C1",
            "direction": "unknown",
            "strength": "unknown",
            "limitations": ["missing_required_facts"],
            "audit_summary_cn": "证据不足，保留未知。",
        }
    return {
        "conclusion_code": code,
        "subject": "T1:C1",
        "direction": direction,
        "metrics": [{"metric_code": "support_level", "value": 1}],
        "supporting_fact_refs": ["fact:1"],
        "strength": strength,
        "audit_summary_cn": "由已保存事实支持。",
    }


def _dimension_score(
    weight: str = "0.10",
    raw: str = "0.50",
) -> dict:
    return {
        "configured_weight": weight,
        "raw_score": raw,
        "available_weight": weight,
        "normalized_score": raw,
        "weighted_contribution": str(Decimal(weight) * Decimal(raw)),
    }


def _dimension(code: str) -> dict:
    weight = {
        "battlefield_overlap": "0.25",
        "user_task_overlap": "0.15",
        "target_group_overlap": "0.15",
    }.get(code, "0.10")
    return {
        "dimension_code": code,
        "availability": "available",
        "score": _dimension_score(weight=weight),
        "conclusion_strength": "supported",
        "conclusion": _conclusion(code=f"{code}_supported"),
        "result_hash": f"hash:{code}",
    }


def _dimension_set() -> dict:
    return {
        "battlefield_overlap": _dimension("battlefield_overlap"),
        "user_task_overlap": _dimension("user_task_overlap"),
        "target_group_overlap": _dimension("target_group_overlap"),
        "parameter_comparison": _dimension("parameter_comparison"),
        "claim_comparison": _dimension("claim_comparison"),
        "user_realization_comparison": _dimension("user_realization_comparison"),
        "purchase_reason_comparison": _dimension("purchase_reason_comparison"),
    }


def _purchase_pressure() -> dict:
    return {
        "comparison_allowed": True,
        "target_highest_pressure_level": "medium",
        "candidate_highest_pressure_level": "low",
        "conclusion": _conclusion(code="purchase_pressure"),
        "calculator_method_version": "purchase-pressure-v1",
        "calculator_config_version": "purchase-pressure-config-v1",
        "result_hash": "hash:purchase-pressure",
    }


def _value_anchor() -> dict:
    return {
        "shared_anchors": ["画质"],
        "target_stronger_anchors": ["强光清晰"],
        "purchase_pressure_comparison": _purchase_pressure(),
        "anchor_substitutability_score": "7.5",
        "anchor_substitutability_level": "medium",
        "score": _dimension_score(weight="0.15", raw="0.50"),
        "conclusion_strength": "supported",
        "conclusion": _conclusion(code="value_anchor"),
        "calculator_method_version": "value-anchor-v1",
        "calculator_config_version": "value-anchor-config-v1",
        "result_hash": "hash:value-anchor",
    }


def _replacement_pressure() -> dict:
    return {
        "primary_pressure_type": "same_value_lower_price",
        "auxiliary_pressure_types": ["scale_pressure"],
        "replacement_pressure_score": "5",
        "replacement_pressure_level": "medium",
        "score": _dimension_score(weight="0.10", raw="0.50"),
        "conclusion_strength": "supported",
        "conclusion": _conclusion(
            code="replacement_pressure",
            direction="positive_pressure",
        ),
        "calculator_method_version": "replacement-pressure-v1",
        "calculator_config_version": "replacement-pressure-config-v1",
        "result_hash": "hash:replacement-pressure",
    }


def _market_validation() -> dict:
    return {
        "sales_overlap_snapshot": {
            "method": "weekly_average",
            "window": "2026-01/2026-06",
            "overlap_weeks": ["2026-W01"],
            "target_overall_weekly_volume": "10",
            "candidate_overall_weekly_volume": "12",
            "target_overlap_weekly_volume": "10",
            "candidate_overlap_weekly_volume": "12",
            "volume_gap": "2",
            "volume_ratio": "1.2",
        },
        "target_weighted_price": "100",
        "candidate_weighted_price": "110",
        "price_gap": "10",
        "price_ratio": "1.1",
        "market_validation_strength": "supported",
        "conclusion": _conclusion(code="market_validation"),
        "result_hash": "hash:market-validation",
    }


def _purchase_pool() -> dict:
    return {
        "level": "P1",
        "gate_facts": [
            {
                "gate_code": "category_form",
                "known": True,
                "passed": True,
                "reason_code": "same_category_form",
            }
        ],
        "score": _dimension_score(weight="0.20", raw="0.50"),
        "conclusion": _conclusion(code="purchase_pool"),
        "result_hash": "hash:purchase-pool",
    }


def _score_breakdown(*, sparse: bool = False) -> dict:
    components = []
    for code in s.PRIMARY_SCORE_DIMENSIONS:
        weight = s.PRIMARY_DIMENSION_WEIGHTS[code]
        available = not sparse or code == "purchase_pool"
        components.append(
            {
                "dimension_code": code,
                "availability": "available" if available else "unknown",
                "weight": str(weight),
                "raw_score": "0.5" if available else None,
                "weighted_contribution": str(weight * Decimal("0.5"))
                if available
                else "0",
            }
        )
    available_weight = Decimal("0.20") if sparse else Decimal("1")
    raw_total = Decimal("0.10") if sparse else Decimal("0.50")
    return {
        "components": components,
        "raw_total": str(raw_total),
        "available_weight": str(available_weight),
        "normalized_total": "0.5",
        "coverage": str(available_weight),
        "ranking_score": "0.5",
        "ranking_tiebreakers": [
            "market_validation_strength",
            "available_weight",
            "recall_rank",
            "candidate_sku_code",
        ],
    }


def _pair() -> dict:
    return {
        "project_id": "project-1",
        "category_code": "TV",
        "competitor_profile_version_id": "version-1",
        "release_scope_key": "project-1:TV",
        "target_sku_code": "T1",
        "candidate_sku_code": "C1",
        "target_snapshot_ref": "snapshot:T1",
        "candidate_snapshot_ref": "snapshot:C1",
        "scope_status": "analyzable",
        "recall_sources": ["market_universe"],
        "recall_rank": 1,
        "purchase_pool": _purchase_pool(),
        "dimensions": _dimension_set(),
        "value_anchor_analysis": _value_anchor(),
        "replacement_pressure_analysis": _replacement_pressure(),
        "purchase_pressure_comparison": _purchase_pressure(),
        "market_validation": _market_validation(),
        "comparison_roles": ["direct_competitor"],
        "primary_role": "direct_competitor",
        "score_breakdown": _score_breakdown(),
        "relation_assessments": _relation_assessments(),
        "business_questions": _business_questions(),
        "overall_conclusion_strength": "supported",
        "overall_conclusion": _conclusion(code="overall"),
        "source_lineage": {
            "source_module_versions": {"M12D": "published-v1"},
            "source_result_hashes": {"M12D": "hash:m12d"},
        },
        "audit_summary": {"summary_cn": "竞品对分析完成。"},
        "input_fingerprint": "fingerprint:pair",
        "result_hash": "hash:pair",
    }


def _evidence_ref() -> dict:
    return {
        "module_code": "M12D",
        "profile_version": "published-v1",
        "rule_version": "m12d-rule-v1",
        "taxonomy_version": "taxonomy-v1",
        "record_type": "purchase_reason_anchor",
        "record_id": "record-1",
        "result_hash": "hash:evidence-1",
    }


def _saved_source_fact(*, entity_key: str = "T1") -> dict:
    raw_occurrences = [
        {
            "occurrence_key": "saved.support.fact",
            "raw_value": True,
        }
    ]
    typed_value = {
        "presence": "known",
        "value": True,
        "source_path": "saved.support.fact",
        "evidence_refs": [_evidence_ref()],
    }
    return {
        "fact_id": "fact:1",
        "code": "saved_support_fact",
        "values": [typed_value],
        "evidence_refs": [_evidence_ref()],
        "entity_key": entity_key,
        "source_atom": "M12D",
        "source_path": "saved.support.fact",
        "normalized_target_path": "source_facts[saved.support.fact]",
        "source_occurrences": [
            {
                "occurrence_key": "saved.support.fact",
                "ordinal": 0,
                "raw_value": True,
                "typed_value": typed_value,
            }
        ],
        "occurrence_count": 1,
        "source_value_hash": hashlib.sha256(
            _canonical_bytes(raw_occurrences)
        ).hexdigest(),
    }


def _snapshot(*, sku_code: str = "T1", model_name: str = "65E7Q") -> dict:
    return {
        "competitor_profile_version_id": "version-1",
        "project_id": "project-1",
        "category_code": "TV",
        "release_scope_key": "project-1:TV",
        "snapshot_ref": f"snapshot:{sku_code}",
        "identity_market": {
            "sku_code": sku_code,
            "brand_name": "海信",
            "model_name": model_name,
            "product_category": "TV",
            "screen_size_inch": "65",
        },
        "product_form_facts": {
            "product_category": "TV",
            "screen_size_inch": "65",
        },
        "market_snapshot": {
            "market_window": "2026-01/2026-06",
            "weighted_price": "100",
            "avg_weekly_sales_volume": "10",
        },
        "fact_sections": {},
        "source_facts": [_saved_source_fact(entity_key=sku_code)]
        if sku_code == "T1"
        else [],
        "module_availability": [],
        "input_fingerprint": "fingerprint:snapshot",
        "result_hash": "hash:snapshot",
    }


def _score_policy() -> dict:
    return {
        "components": [
            {"dimension_code": code, "weight": str(weight)}
            for code, weight in s.PRIMARY_DIMENSION_WEIGHTS.items()
        ]
    }


def _relation_assessments() -> list[dict]:
    return [
        {
            "relation_code": relation_code,
            "status": "passed",
            "required_dimensions": list(s.RELATION_REQUIRED_DIMENSIONS[relation_code]),
            "conclusion_strength": "supported",
            "conclusion": _conclusion(code=f"relation_{relation_code}"),
            "input_fingerprint": f"fingerprint:relation:{relation_code}",
            "result_hash": f"hash:relation:{relation_code}",
        }
        for relation_code in s.ALL_RELATION_CODES
    ]


def _business_questions() -> list[dict]:
    return [
        {
            "question_code": question_code,
            "answerable": True,
            "conclusion_strength": "supported",
            "conclusion": _conclusion(code=f"question_{question_code}"),
            "required_dimensions": list(s.QUESTION_REQUIRED_DIMENSIONS[question_code]),
            "alternative_evidence_groups": [
                {
                    "group_code": group_code,
                    "any_of_dimensions": list(dimensions),
                    "satisfied_dimensions": list(dimensions),
                }
                for group_code, dimensions in sorted(
                    s.QUESTION_ALTERNATIVE_EVIDENCE_GROUPS.get(
                        question_code,
                        {},
                    ).items()
                )
            ],
            "result_hash": f"hash:question:{question_code}",
        }
        for question_code in s.ALL_QUESTION_CODES
    ]


def _budget() -> dict:
    return {
        "categories": [
            {
                "category_code": "TV",
                "maximum_candidate_count": 377,
                "maximum_generation_p95_ms": 60_000,
                "maximum_peak_memory_mib": 1_200,
                "maximum_serialized_draft_bytes": 536_870_912,
            },
            {
                "category_code": "AC",
                "maximum_candidate_count": 155,
                "maximum_generation_p95_ms": 30_000,
                "maximum_peak_memory_mib": 600,
                "maximum_serialized_draft_bytes": 268_435_456,
            },
        ]
    }


def _selection() -> dict:
    return {
        "target_sku_code": "T1",
        "candidate_sku_code": "C1",
        "selection_rank": 1,
        "pair_result_hash": "hash:pair",
        "primary_role": "direct_competitor",
        "role_codes": ["direct_competitor"],
        "selection_score": "0.5",
        "selection_available_weight": "1",
        "selection_conclusion_strength": "supported",
        "selection_reason_code": "strongest_saved_pair",
        "selection_reason_cn": "在已保存竞品对中综合关系最强。",
        "result_hash": "hash:selection",
    }


def _summary() -> dict:
    return {
        "target_sku_code": "T1",
        "analysis_candidate_count": 1,
        "legacy_candidate_count": 1,
        "dimension_availability_counts": {"available": 7},
        "conclusion_strength_counts": {"supported": 1},
        "priority_competitors": [_selection()],
        "role_buckets": {"direct_competitor": ["C1"]},
        "input_fingerprint": "fingerprint:summary",
        "result_hash": "hash:summary",
    }


def _dto_payload() -> dict:
    pair = _pair()
    return {
        "profile_version": {
            "competitor_profile_version_id": "version-1",
            "project_id": "project-1",
            "category_code": "TV",
            "product_category": "TV",
            "release_scope_key": "project-1:TV",
            "source_batch_ids": ["batch-1"],
            "market_window": "2026-01/2026-06",
            "analysis_population": "online_market",
            "score_policy": _score_policy(),
            "performance_storage_budget": _budget(),
        },
        "generation_receipt": {
            "source_status": "ready",
            "input_fingerprint": "fingerprint:generation",
            "result_hash": "hash:generation",
        },
        "target_snapshot": _snapshot(),
        "candidate_snapshots": [_snapshot(sku_code="C1", model_name="竞品C1")],
        "sku_summary": _summary(),
        "priority_selections": [_selection()],
        "full_pair_index": [
            {
                "candidate_sku_code": "C1",
                "scope_status": "analyzable",
                "recall_rank": 1,
                "primary_role": "direct_competitor",
                "conclusion_strength": "supported",
                "selected_rank": 1,
                "pair_result_hash": "hash:pair",
            }
        ],
        "pair_analyses": [pair],
        "fact_index": {
            "fact:1": {
                "fact_id": "fact:1",
                "fact_code": "saved_support_fact",
                "evidence_keys": ["evidence:1"],
                "source_path": "saved.support.fact",
            }
        },
        "evidence_index": {"evidence:1": _evidence_ref()},
        "profile_result_hash": "hash:profile",
    }


def test_typed_fact_preserves_null_missing_false_zero_and_empty_values() -> None:
    assert s.TypedFactValue(presence="known", value=False).value is False
    assert s.TypedFactValue(presence="known", value=0).value == 0
    assert s.TypedFactValue(presence="known", value=[]).value == []
    assert s.TypedFactValue(presence="known", value={}).value == {}
    assert s.TypedFactValue(presence="explicit_null").presence == "explicit_null"
    assert (
        s.TypedFactValue(
            presence="missing", unknown_reason_code="not_observed"
        ).presence
        == "missing"
    )
    with pytest.raises(ValidationError, match="explicit null"):
        s.TypedFactValue(presence="explicit_null", unknown_reason_code="missing")
    with pytest.raises(ValidationError, match="missing values require"):
        s.TypedFactValue(presence="missing", value=0, unknown_reason_code="missing")
    for missing_marker in ("", "   ", "-"):
        with pytest.raises(ValidationError, match="missing markers"):
            s.TypedFactValue(presence="known", value=missing_marker)


def test_machine_readable_conclusion_and_runtime_export_boundary_are_strict() -> None:
    s.MachineReadableConclusion.model_validate(_conclusion())
    s.MachineReadableConclusion.model_validate(_conclusion(strength="unknown"))
    invalid = _conclusion(strength="unknown")
    invalid["direction"] = "target_stronger"
    with pytest.raises(ValidationError, match="unknown conclusions"):
        s.MachineReadableConclusion.model_validate(invalid)
    unsupported = _conclusion()
    unsupported["metrics"] = []
    with pytest.raises(ValidationError, match="supporting facts and metrics"):
        s.MachineReadableConclusion.model_validate(unsupported)
    with pytest.raises(ValidationError, match="factory-only keys"):
        s.AnalysisItem(
            fact_id="fact:runtime-boundary",
            code="x",
            values=[{"presence": "known", "value": 1}],
            legacy_payload={"prompt_template": "do not export"},
        )
    with pytest.raises(ValidationError, match="extra_forbidden"):
        s.TypedFactValue(presence="known", value=1, unexpected=True)


def test_sku_snapshot_separates_identity_market_and_typed_business_facts() -> None:
    payload = _snapshot()
    payload["fact_sections"] = {
        "parameter_items": [
            {
                "fact_id": "fact:peak-brightness",
                "code": "peak_brightness",
                "values": [
                    {
                        "presence": "known",
                        "value": 1500,
                        "unit": "nit",
                        "tier": "1500_nit",
                    }
                ],
            }
        ],
        "claim_items": [
            {
                "fact_id": "fact:bright-room-clarity",
                "code": "bright_room_clarity",
                "roles": ["selection_driver"],
                "values": [{"presence": "known", "value": True}],
                "supporting_parameter_codes": ["peak_brightness"],
            }
        ],
    }
    snapshot = s.VersionSkuAnalysisSnapshot.model_validate(payload)
    assert snapshot.market_snapshot.weighted_price == Decimal("100")
    assert snapshot.fact_sections.parameter_items[0].values[0].unit == "nit"
    assert snapshot.fact_sections.claim_items[0].supporting_parameter_codes == [
        "peak_brightness"
    ]


def test_foundational_feature_uses_five_known_and_eighty_percent_boundary() -> None:
    base = {
        "scope_dimensions": [
            "category_code",
            "price_band",
            "product_form",
            "size_relation",
        ],
        "source": "full_candidate_universe",
        "scope_hash": "hash:scope",
    }
    unknown = s.FeaturePrevalenceContract(
        **base,
        numerator=4,
        denominator=4,
        ratio="1",
        feature_market_status="unknown",
    )
    assert unknown.feature_market_status == "unknown"
    foundational = s.FeaturePrevalenceContract(
        **base,
        numerator=4,
        denominator=5,
        ratio="0.8",
        feature_market_status="foundational",
    )
    assert foundational.feature_market_status == "foundational"
    differentiating = s.FeaturePrevalenceContract(
        **base,
        numerator=3,
        denominator=5,
        ratio="0.6",
        feature_market_status="differentiating",
    )
    assert differentiating.feature_market_status == "differentiating"
    with pytest.raises(ValidationError, match="cannot drive differentiation"):
        s.FeatureAnalysisItem(
            fact_id="fact:hdmi-2-1",
            code="hdmi_2_1",
            values=[{"presence": "known", "value": True}],
            prevalence=foundational,
            raw_difference={
                "target": {"presence": "known", "value": True},
                "candidate": {"presence": "known", "value": True},
                "comparison_code": "equal",
            },
            contributes_to_differentiation=True,
            ranking_reason_eligible=False,
        )
    with pytest.raises(ValidationError, match="raw_difference"):
        s.FeatureAnalysisItem(
            fact_id="fact:missing-difference",
            code="missing_difference",
            values=[{"presence": "known", "value": True}],
            prevalence=differentiating,
            contributes_to_differentiation=True,
            ranking_reason_eligible=True,
        )


def test_six_dimension_score_normalizes_unknowns_without_inflating_ranking() -> None:
    policy = s.ScorePolicyContract.model_validate(_score_policy())
    assert [row.dimension_code for row in policy.components] == list(
        s.PRIMARY_SCORE_DIMENSIONS
    )
    assert policy.coverage_minimum_gate is None
    sparse = s.PairScoreBreakdown.model_validate(_score_breakdown(sparse=True))
    assert sparse.normalized_total == Decimal("0.5")
    assert sparse.coverage == Decimal("0.20")
    assert sparse.ranking_score == Decimal("0.5")
    assert policy.ranking_formula == "conclusion_strength_then_normalized_total"
    invalid = _score_breakdown(sparse=True)
    invalid["ranking_score"] = "0.1"
    with pytest.raises(ValidationError, match="normalized analytical strength"):
        s.PairScoreBreakdown.model_validate(invalid)
    wrong_policy = _score_policy()
    wrong_policy["components"][0]["weight"] = "0.25"
    with pytest.raises(ValidationError, match="frozen V1.1 weights"):
        s.ScorePolicyContract.model_validate(wrong_policy)


def test_pair_score_must_match_each_saved_source_analysis() -> None:
    s.PairAnalysisSnapshot.model_validate(_pair())
    mismatched = json.loads(json.dumps(_pair()))
    purchase_component = mismatched["score_breakdown"]["components"][0]
    purchase_component["raw_score"] = "0.4"
    purchase_component["weighted_contribution"] = "0.08"
    mismatched["score_breakdown"].update(
        {
            "raw_total": "0.48",
            "normalized_total": "0.48",
            "ranking_score": "0.48",
        }
    )
    with pytest.raises(ValidationError, match="match source analysis scores"):
        s.PairAnalysisSnapshot.model_validate(mismatched)

    unknown_pool = {
        "level": "unknown",
        "gate_facts": [
            {
                "gate_code": "category_form",
                "known": False,
                "passed": None,
                "reason_code": "product_form_missing",
            }
        ],
        "score": {
            "configured_weight": "0.20",
            "raw_score": None,
            "available_weight": "0",
            "normalized_score": None,
            "weighted_contribution": "0",
        },
        "conclusion": _conclusion(code="purchase_pool_unknown", strength="unknown"),
        "result_hash": "hash:purchase-pool-unknown",
    }
    assert s.PurchasePoolAnalysis.model_validate(unknown_pool).level == "unknown"
    unknown_pool["score"] = _dimension_score(weight="0.20", raw="0.5")
    with pytest.raises(ValidationError, match="unknown purchase pool"):
        s.PurchasePoolAnalysis.model_validate(unknown_pool)


def test_relation_and_question_statuses_follow_pair_dimension_availability() -> None:
    payload = json.loads(json.dumps(_pair()))
    battlefield = payload["dimensions"]["battlefield_overlap"]
    battlefield.update(
        {
            "availability": "unknown",
            "score": {
                "configured_weight": "0.25",
                "raw_score": None,
                "available_weight": "0",
                "normalized_score": None,
                "weighted_contribution": "0",
            },
            "conclusion_strength": "unknown",
            "conclusion": _conclusion(
                code="battlefield_unknown",
                strength="unknown",
            ),
        }
    )
    battlefield_component = next(
        row
        for row in payload["score_breakdown"]["components"]
        if row["dimension_code"] == "battlefield_overlap"
    )
    battlefield_component.update(
        {
            "availability": "unknown",
            "raw_score": None,
            "weighted_contribution": "0",
        }
    )
    payload["score_breakdown"].update(
        {
            "raw_total": "0.375",
            "available_weight": "0.75",
            "normalized_total": "0.5",
            "coverage": "0.75",
            "ranking_score": "0.5",
        }
    )
    with pytest.raises(ValidationError, match="must match pair analyses"):
        s.PairAnalysisSnapshot.model_validate(payload)

    direct_relation = next(
        row
        for row in payload["relation_assessments"]
        if row["relation_code"] == "direct_substitute"
    )
    direct_relation.update(
        {
            "status": "limited",
            "missing_dimensions": ["battlefield_overlap"],
            "conclusion_strength": "directional",
            "conclusion": _conclusion(
                code="direct_substitute_limited",
                strength="directional",
            ),
        }
    )
    purchase_choice = next(
        row
        for row in payload["business_questions"]
        if row["question_code"] == "purchase_choice"
    )
    purchase_choice.update(
        {
            "answerable": False,
            "missing_dimensions": ["battlefield_overlap"],
            "conclusion_strength": "unknown",
            "conclusion": _conclusion(
                code="purchase_choice_unknown",
                strength="unknown",
            ),
        }
    )
    assert s.PairAnalysisSnapshot.model_validate(payload).scope_status == "analyzable"


def test_unknown_dimension_cannot_emit_a_supported_directional_conclusion() -> None:
    payload = _dimension("battlefield_overlap")
    payload["availability"] = "unknown"
    payload["score"] = {
        "configured_weight": "0.25",
        "raw_score": None,
        "available_weight": "0",
        "normalized_score": None,
        "weighted_contribution": "0",
    }
    with pytest.raises(ValidationError, match="require an unknown conclusion"):
        s.DimensionAnalysisResult.model_validate(payload)
    payload["conclusion_strength"] = "unknown"
    payload["conclusion"] = _conclusion(
        code="battlefield_unknown",
        strength="unknown",
    )
    assert s.DimensionAnalysisResult.model_validate(payload).availability == "unknown"
    payload["availability"] = "conflict"
    with pytest.raises(ValidationError, match="require a review overlay"):
        s.DimensionAnalysisResult.model_validate(payload)
    payload["review_required"] = True
    payload["review_items"] = [
        {
            "review_code": "battlefield_conflict",
            "dimension_code": "battlefield_overlap",
            "reason_cn": "同一范围内战场证据冲突。",
        }
    ]
    assert s.DimensionAnalysisResult.model_validate(payload).availability == "conflict"


def test_value_anchor_and_replacement_pressure_freeze_fifteen_and_ten_point_scales() -> (
    None
):
    assert s.ValueAnchorAnalysisResult.model_validate(
        _value_anchor()
    ).score.normalized_score == Decimal("0.5")
    assert s.ReplacementPressureAnalysisResult.model_validate(
        _replacement_pressure()
    ).score.normalized_score == Decimal("0.5")
    invalid_anchor = _value_anchor()
    invalid_anchor["score"] = _dimension_score(weight="0.15", raw="0.6")
    with pytest.raises(ValidationError, match="15-point"):
        s.ValueAnchorAnalysisResult.model_validate(invalid_anchor)
    invalid_pressure = _replacement_pressure()
    invalid_pressure["score"] = _dimension_score(weight="0.10", raw="0.4")
    with pytest.raises(ValidationError, match="10-point"):
        s.ReplacementPressureAnalysisResult.model_validate(invalid_pressure)

    unknown_score_15 = {
        "configured_weight": "0.15",
        "raw_score": None,
        "available_weight": "0",
        "normalized_score": None,
        "weighted_contribution": "0",
    }
    unknown_pressure_comparison = {
        "comparison_allowed": False,
        "conclusion": _conclusion(
            code="purchase_pressure_unknown",
            strength="unknown",
        ),
        "calculator_method_version": "purchase-pressure-v1",
        "calculator_config_version": "purchase-pressure-config-v1",
        "result_hash": "hash:purchase-pressure-unknown",
    }
    unknown_anchor = {
        "purchase_pressure_comparison": unknown_pressure_comparison,
        "anchor_substitutability_score": None,
        "anchor_substitutability_level": "unknown",
        "score": unknown_score_15,
        "conclusion_strength": "unknown",
        "conclusion": _conclusion(code="value_anchor_unknown", strength="unknown"),
        "calculator_method_version": "value-anchor-v1",
        "calculator_config_version": "value-anchor-config-v1",
        "result_hash": "hash:value-anchor-unknown",
    }
    assert (
        s.ValueAnchorAnalysisResult.model_validate(
            unknown_anchor
        ).anchor_substitutability_score
        is None
    )
    unknown_replacement = {
        "primary_pressure_type": "unknown",
        "replacement_pressure_score": None,
        "replacement_pressure_level": "unknown",
        "score": {
            **unknown_score_15,
            "configured_weight": "0.10",
        },
        "conclusion_strength": "unknown",
        "conclusion": _conclusion(
            code="replacement_pressure_unknown",
            strength="unknown",
        ),
        "calculator_method_version": "replacement-pressure-v1",
        "calculator_config_version": "replacement-pressure-config-v1",
        "result_hash": "hash:replacement-pressure-unknown",
    }
    assert (
        s.ReplacementPressureAnalysisResult.model_validate(
            unknown_replacement
        ).replacement_pressure_score
        is None
    )
    fake_zero = dict(unknown_anchor)
    fake_zero["anchor_substitutability_score"] = "0"
    with pytest.raises(ValidationError, match="15-point"):
        s.ValueAnchorAnalysisResult.model_validate(fake_zero)


def test_purchase_pressure_requires_explicit_calculator_versions() -> None:
    payload = _purchase_pressure()
    payload.pop("calculator_method_version")
    with pytest.raises(ValidationError, match="calculator_method_version"):
        s.PurchasePressureComparisonResult.model_validate(payload)

    payload = _purchase_pressure()
    payload.pop("calculator_config_version")
    with pytest.raises(ValidationError, match="calculator_config_version"):
        s.PurchasePressureComparisonResult.model_validate(payload)

    payload = _purchase_pressure()
    payload["conclusion"] = _conclusion(
        code="purchase_pressure_unknown",
        strength="unknown",
    )
    with pytest.raises(ValidationError, match="needs a conclusion"):
        s.PurchasePressureComparisonResult.model_validate(payload)


def test_pair_contract_keeps_only_five_hard_exclusions_and_preserves_self_pair() -> (
    None
):
    assert s.HARD_EXCLUSION_CODES == {
        "self_pair",
        "project_mismatch",
        "category_mismatch",
        "candidate_outside_manifest",
        "identity_decode_failed",
    }
    pair = s.PairAnalysisSnapshot.model_validate(_pair())
    assert pair.primary_role == "direct_competitor"
    excluded = _pair()
    for field in (
        "purchase_pool",
        "dimensions",
        "value_anchor_analysis",
        "replacement_pressure_analysis",
        "purchase_pressure_comparison",
        "market_validation",
        "score_breakdown",
    ):
        excluded[field] = None
    excluded.update(
        {
            "candidate_sku_code": "T1",
            "candidate_snapshot_ref": "snapshot:T1",
            "scope_status": "excluded",
            "exclusion_reason_code": "self_pair",
            "comparison_roles": [],
            "primary_role": None,
            "relation_assessments": [],
            "business_questions": [],
            "overall_conclusion_strength": "unknown",
            "overall_conclusion": _conclusion(
                code="self_pair_excluded",
                strength="unknown",
            ),
        }
    )
    assert (
        s.PairAnalysisSnapshot.model_validate(excluded).exclusion_reason_code
        == "self_pair"
    )
    invalid = dict(excluded)
    invalid["exclusion_reason_code"] = "insufficient_overlap"
    with pytest.raises(ValidationError, match="hard exclusion"):
        s.PairAnalysisSnapshot.model_validate(invalid)
    invalid = dict(excluded)
    invalid["candidate_sku_code"] = "C1"
    with pytest.raises(ValidationError, match="identical target and candidate"):
        s.PairAnalysisSnapshot.model_validate(invalid)
    invalid = json.loads(json.dumps(excluded))
    invalid["overall_conclusion_strength"] = "supported"
    invalid["overall_conclusion"] = _conclusion(code="excluded_but_supported")
    with pytest.raises(ValidationError, match="unknown overall conclusion"):
        s.PairAnalysisSnapshot.model_validate(invalid)

    review_overlay = _pair()
    review_overlay["review_required"] = True
    review_overlay["review_items"] = [
        {
            "review_code": "battlefield_conflict",
            "dimension_code": "battlefield_overlap",
            "reason_cn": "战场证据冲突，其他维度继续分析。",
        }
    ]
    assert (
        s.PairAnalysisSnapshot.model_validate(review_overlay).scope_status
        == "analyzable"
    )
    lineage_mismatch = _pair()
    lineage_mismatch["source_lineage"]["source_result_hashes"] = {"OTHER": "hash:other"}
    with pytest.raises(ValidationError, match="versions and result hashes must align"):
        s.PairAnalysisSnapshot.model_validate(lineage_mismatch)


def test_analyzable_pair_requires_all_relations_and_business_questions() -> None:
    missing_relation = _pair()
    missing_relation["relation_assessments"] = missing_relation["relation_assessments"][
        :-1
    ]
    with pytest.raises(ValidationError, match="all seven relation assessments"):
        s.PairAnalysisSnapshot.model_validate(missing_relation)

    missing_question = _pair()
    missing_question["business_questions"] = missing_question["business_questions"][:-1]
    with pytest.raises(ValidationError, match="every frozen business question"):
        s.PairAnalysisSnapshot.model_validate(missing_question)

    limited_without_reason = _relation_assessments()[0]
    limited_without_reason.update(
        {
            "status": "limited",
            "conclusion_strength": "directional",
            "conclusion": _conclusion(
                code="limited_relation",
                strength="directional",
            ),
        }
    )
    with pytest.raises(ValidationError, match="concrete evidence limitation"):
        s.RelationAssessment.model_validate(limited_without_reason)


def test_product_questions_require_real_decision_evidence_before_selection() -> None:
    missing_configuration_link = _pair()
    configuration_question = next(
        row
        for row in missing_configuration_link["business_questions"]
        if row["question_code"] == "configuration_follow"
    )
    configuration_question["alternative_evidence_groups"][0][
        "satisfied_dimensions"
    ] = []
    with pytest.raises(ValidationError, match="alternative evidence"):
        s.PairAnalysisSnapshot.model_validate(missing_configuration_link)

    key_only = _pair()
    for question in key_only["business_questions"]:
        if question["question_code"] == "key_competitor_selection":
            continue
        question.update(
            {
                "answerable": False,
                "conclusion_strength": "unknown",
                "conclusion": _conclusion(
                    code=f"{question['question_code']}_unknown",
                    strength="unknown",
                ),
            }
        )
    with pytest.raises(ValidationError, match="frozen minimum evidence"):
        s.PairAnalysisSnapshot.model_validate(key_only)


def test_frozen_boolean_contracts_reject_string_and_integer_coercion() -> None:
    gate = _purchase_pool()["gate_facts"][0]
    gate["known"] = "false"
    with pytest.raises(ValidationError, match="bool_type"):
        s.PurchasePoolGateFact.model_validate(gate)
    with pytest.raises(ValidationError, match="bool_type"):
        s.ProfileGenerationReceipt(
            source_status="ready",
            external_publish=0,
            input_fingerprint="fingerprint:generation",
            result_hash="hash:generation",
        )


def test_dto_and_agent_adapter_roundtrip_lock_saved_profile_version_and_order() -> None:
    dto_payload = _dto_payload()
    pair = dto_payload["pair_analyses"][0]
    dto = s.CompetitorProfileAnalysisDTO.model_validate(dto_payload)
    assert (
        s.CompetitorProfileAnalysisDTO.model_validate(dto.model_dump(mode="json"))
        == dto
    )
    adapter_projection = {
        "competitor_profile_version_id": "version-1",
        "profile_result_hash": "hash:profile",
        "profile_version": dto_payload["profile_version"],
        "target_snapshot": _snapshot(),
        "sku_competition_summary": _summary(),
        "candidates": [
            {
                "candidate_sku_code": "C1",
                "candidate_snapshot_ref": "snapshot:C1",
                "candidate_snapshot_result_hash": "hash:snapshot",
                "candidate_snapshot": _snapshot(
                    sku_code="C1",
                    model_name="竞品C1",
                ),
                "identity": _snapshot(
                    sku_code="C1",
                    model_name="竞品C1",
                )["identity_market"],
                "recall_rank": 1,
                "recall_sources": ["market_universe"],
                "purchase_pool": pair["purchase_pool"],
                "dimension_results": pair["dimensions"],
                "value_anchor_analysis": pair["value_anchor_analysis"],
                "replacement_pressure_analysis": pair["replacement_pressure_analysis"],
                "purchase_pressure_comparison": pair["purchase_pressure_comparison"],
                "market_validation": pair["market_validation"],
                "comparison_roles": pair["comparison_roles"],
                "primary_role": pair["primary_role"],
                "score_breakdown": pair["score_breakdown"],
                "relation_assessments": pair["relation_assessments"],
                "business_questions": pair["business_questions"],
                "selection_assessment": {
                    "answerable_question_codes": list(s.ALL_QUESTION_CODES),
                    "selection_eligible": True,
                    "selected": True,
                    "selection_rank": 1,
                    "selection_reason_code": "strongest_saved_pair",
                    "selection_reason_cn": "在已保存竞品对中综合关系最强。",
                    "selection_conclusion_strength": "supported",
                    "market_validation_strength": "supported",
                    "pair_selection_result_hash": "hash:pair-selection",
                },
                "overall_conclusion": pair["overall_conclusion"],
                "pair_result_hash": "hash:pair",
            }
        ],
        "priority_order": ["C1"],
        "fact_index": dto_payload["fact_index"],
        "evidence_index": dto_payload["evidence_index"],
    }
    adapter = s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
        adapter_projection
    )
    adapter_payload = adapter.model_dump(mode="json")
    assert adapter.source == "competitor_profile_v1_1"
    assert (
        s.CompetitorProfileAdapterContract.model_validate(adapter_payload).model_dump(
            mode="json"
        )
        == adapter_payload
    )
    invalid = dict(adapter_payload)
    invalid["priority_order"] = []
    with pytest.raises(ValidationError, match="preserve the saved selection"):
        s.CompetitorProfileAdapterContract.model_validate(invalid)
    invalid_identity = json.loads(json.dumps(adapter_payload))
    invalid_identity["candidates"][0]["identity"]["sku_code"] = "OTHER"
    with pytest.raises(ValidationError, match="identity must match"):
        s.CompetitorProfileAdapterContract.model_validate(invalid_identity)
    invalid_evidence = json.loads(json.dumps(adapter_payload))
    invalid_evidence["evidence_index"] = {}
    with pytest.raises(ValidationError, match="bind the runtime projection"):
        s.CompetitorProfileAdapterContract.model_validate(invalid_evidence)
    invalid_evidence_projection = json.loads(json.dumps(adapter_projection))
    invalid_evidence_projection["evidence_index"] = {}
    with pytest.raises(ValidationError, match="resolve uniquely"):
        s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
            invalid_evidence_projection
        )
    invalid_scope = json.loads(json.dumps(adapter_payload))
    invalid_scope["target_snapshot"]["release_scope_key"] = "other:TV"
    with pytest.raises(ValidationError, match="scope must match"):
        s.CompetitorProfileAdapterContract.model_validate(invalid_scope)
    invalid_profile_hash = json.loads(json.dumps(adapter_payload))
    invalid_profile_hash["profile_result_hash"] = "hash:untraced"
    with pytest.raises(ValidationError, match="source receipt"):
        s.CompetitorProfileAdapterContract.model_validate(invalid_profile_hash)
    tampered_projection = json.loads(json.dumps(adapter_payload))
    tampered_projection["candidates"][0]["identity"]["model_name"] = "篡改名称"
    with pytest.raises(
        ValidationError,
        match="bind the runtime projection|identity must match",
    ):
        s.CompetitorProfileAdapterContract.model_validate(tampered_projection)
    raw_bag = json.loads(json.dumps(adapter_projection))
    raw_bag["target_snapshot"]["fact_sections"]["legacy_payload"] = {
        "system_prompt": "do not export"
    }
    with pytest.raises(ValueError, match="authoritative whitelist"):
        s.CompetitorProfileAdapterContract.build_from_authoritative_projection(raw_bag)
    factory_payload = json.loads(json.dumps(adapter_projection))
    factory_payload["candidates"][0]["purchase_pool"]["legacy_payload"] = {
        "gold_dataset": ["do not export"]
    }
    with pytest.raises(ValueError, match="authoritative whitelist"):
        s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
            factory_payload
        )
    for factory_key in (
        "system_prompt",
        "system_instruction",
        "gold_dataset",
        "golden_dataset",
        "internal_generation_method",
        "cross_category_migration_tool",
    ):
        nested_factory_payload = json.loads(json.dumps(adapter_projection))
        nested_factory_payload["target_snapshot"]["semantic_profiles"] = {
            "business_facts": {factory_key: "do not export"}
        }
        with pytest.raises(ValueError, match="authoritative whitelist"):
            s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
                nested_factory_payload
            )
    for disguised_legacy_key in ("Legacy_Payload", "legacyPayload"):
        disguised_legacy = json.loads(json.dumps(adapter_projection))
        disguised_legacy["target_snapshot"][disguised_legacy_key] = {
            "compatibility_raw": {"hidden": True}
        }
        with pytest.raises(ValueError, match="authoritative whitelist"):
            s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
                disguised_legacy
            )
    invalid_legacy_count = json.loads(json.dumps(adapter_projection))
    invalid_legacy_count["sku_competition_summary"]["legacy_candidate_count"] = {
        "compatibility_raw": {"hidden": True}
    }
    with pytest.raises(ValueError, match="authoritative whitelist"):
        s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
            invalid_legacy_count
        )
    misplaced_legacy_count = json.loads(json.dumps(adapter_projection))
    misplaced_legacy_count["target_snapshot"]["semantic_profiles"] = {
        "legacy_candidate_count": 1
    }
    with pytest.raises(ValueError, match="authoritative whitelist"):
        s.CompetitorProfileAdapterContract.build_from_authoritative_projection(
            misplaced_legacy_count
        )
    serialized = adapter.model_dump(mode="json")
    serialized_keys = set(_collect_mapping_keys(serialized))
    assert "raw_details" not in serialized_keys
    assert not any(
        key.startswith("legacy_") and key != "legacy_candidate_count"
        for key in serialized_keys
    )
    assert serialized["sku_competition_summary"]["legacy_candidate_count"] == 1
    mutated_name = adapter.model_copy(deep=True)
    mutated_name.candidates[0].identity.model_name = "MUTATED"
    with pytest.raises(PydanticSerializationError, match="runtime projection"):
        mutated_name.model_dump(mode="json")
    mutated_raw = adapter.model_copy(deep=True)
    mutated_raw.target_snapshot.source_facts[0].source_occurrences[0].raw_value = {
        "system_instruction": "secret"
    }
    with pytest.raises(PydanticSerializationError, match="scalar JSON"):
        mutated_raw.model_dump(mode="json")
    mutated_typed = adapter.model_copy(deep=True)
    mutated_typed.target_snapshot.source_facts[0].values[0].value = {
        "system_instruction": "secret"
    }
    mutated_typed.target_snapshot.source_facts[0].source_occurrences[
        0
    ].typed_value.value = {"system_instruction": "secret"}
    with pytest.raises(PydanticSerializationError, match="scalar JSON"):
        mutated_typed.model_dump(mode="json")
    mismatched_candidate_score = json.loads(json.dumps(adapter_payload))
    battlefield_score = mismatched_candidate_score["candidates"][0][
        "dimension_results"
    ]["battlefield_overlap"]["score"]
    battlefield_score.update(
        {
            "raw_score": "0.4",
            "normalized_score": "0.4",
            "weighted_contribution": "0.10",
        }
    )
    with pytest.raises(ValidationError, match="match source analysis scores"):
        s.CompetitorProfileAdapterContract.model_validate(mismatched_candidate_score)


def test_dto_rejects_stale_indices_scores_scopes_and_unresolved_evidence() -> None:
    stale_index = _dto_payload()
    stale_index["full_pair_index"][0]["pair_result_hash"] = "hash:stale"
    with pytest.raises(ValidationError, match="compact pair index"):
        s.CompetitorProfileAnalysisDTO.model_validate(stale_index)

    wrong_scope = _dto_payload()
    wrong_scope["candidate_snapshots"][0]["release_scope_key"] = "other:TV"
    with pytest.raises(ValidationError, match="candidate snapshot scope"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_scope)

    wrong_score = _dto_payload()
    wrong_score["priority_selections"][0]["selection_score"] = "0.4"
    wrong_score["sku_summary"]["priority_competitors"][0]["selection_score"] = "0.4"
    with pytest.raises(ValidationError, match="selection score, coverage"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_score)

    missing_fact = _dto_payload()
    missing_fact["fact_index"] = {}
    with pytest.raises(ValidationError, match="embedded facts"):
        s.CompetitorProfileAnalysisDTO.model_validate(missing_fact)

    index_only_fact = _dto_payload()
    index_only_fact["target_snapshot"]["source_facts"] = []
    with pytest.raises(ValidationError, match="facts embedded in the profile"):
        s.CompetitorProfileAnalysisDTO.model_validate(index_only_fact)

    missing_evidence = _dto_payload()
    missing_evidence["evidence_index"] = {}
    with pytest.raises(ValidationError, match="resolve uniquely"):
        s.CompetitorProfileAnalysisDTO.model_validate(missing_evidence)

    wrong_fact_code = _dto_payload()
    wrong_fact_code["fact_index"]["fact:1"]["fact_code"] = "other_fact"
    with pytest.raises(ValidationError, match="codes must match"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_fact_code)

    wrong_fact_path = _dto_payload()
    wrong_fact_path["fact_index"]["fact:1"]["source_path"] = "other.path"
    with pytest.raises(ValidationError, match="paths must match"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_fact_path)

    mismatched_fact_evidence = _dto_payload()
    saved_fact = mismatched_fact_evidence["target_snapshot"]["source_facts"][0]
    saved_fact["evidence_refs"] = []
    saved_fact["values"][0]["evidence_refs"] = []
    saved_fact["source_occurrences"][0]["typed_value"]["evidence_refs"] = []
    with pytest.raises(ValidationError, match="evidence must exactly match"):
        s.CompetitorProfileAnalysisDTO.model_validate(mismatched_fact_evidence)

    duplicate_fact_id = _dto_payload()
    duplicate = _saved_source_fact()
    duplicate["code"] = "different_content_same_id"
    duplicate_fact_id["generation_receipt"]["source_facts"] = [duplicate]
    with pytest.raises(ValidationError, match="globally unique"):
        s.CompetitorProfileAnalysisDTO.model_validate(duplicate_fact_id)

    wrong_counts = _dto_payload()
    wrong_counts["sku_summary"]["dimension_availability_counts"] = {"unknown": 999}
    with pytest.raises(ValidationError, match="availability counts"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_counts)

    wrong_roles = _dto_payload()
    wrong_roles["sku_summary"]["role_buckets"] = {"market_reference": ["C1"]}
    with pytest.raises(ValidationError, match="role buckets"):
        s.CompetitorProfileAnalysisDTO.model_validate(wrong_roles)

    unknown_candidate_finding = _dto_payload()
    unknown_candidate_finding["sku_summary"]["competitive_advantages"] = [
        {
            "finding_code": "not_in_profile",
            "candidate_sku_codes": ["NOT_IN_PROFILE"],
            "conclusion": _conclusion(code="not_in_profile"),
        }
    ]
    with pytest.raises(ValidationError, match="findings must reference"):
        s.CompetitorProfileAnalysisDTO.model_validate(unknown_candidate_finding)


def test_g29_budget_is_frozen_and_covers_g28_observed_scale() -> None:
    budget = s.G29PerformanceStorageBudget.model_validate(_budget())
    by_category = {row.category_code: row for row in budget.categories}
    scale = json.loads(
        (_artifact_dir() / "G28_max_candidate_scale_205_20260715.json").read_text(
            encoding="utf-8"
        )
    )
    assert (
        scale["categories"]["TV"]["max_candidate_count"]
        <= by_category["TV"].maximum_candidate_count
    )
    assert (
        scale["categories"]["AC"]["max_candidate_count"]
        <= by_category["AC"].maximum_candidate_count
    )
    invalid = _budget()
    invalid["categories"][0]["maximum_candidate_count"] = 376
    with pytest.raises(ValidationError, match="budgets are frozen"):
        s.G29PerformanceStorageBudget.model_validate(invalid)


def test_four_real_g28_fixtures_roundtrip_without_collapsing_legacy_values() -> None:
    for name in REAL_FIXTURE_NAMES:
        with gzip.open(_artifact_dir() / name, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
        model = s.LegacyCompetitorAnalysisCompatibilityEnvelope.model_validate(payload)
        assert model.model_dump(mode="json") == payload
        encoded = _canonical_bytes(model.model_dump(mode="json"))
        assert encoded == _canonical_bytes(payload)


def test_g29_mapping_covers_every_g28_path_and_canonicalizes_duplicate_views() -> None:
    builder = _load_builder()
    built = builder.build_contract()
    with gzip.open(
        _artifact_dir() / "G29_legacy_typed_mapping_contract.json.gz",
        "rt",
        encoding="utf-8",
    ) as handle:
        stored_payload = json.load(handle)
    stored = s.LegacyTypedMappingContract.model_validate(stored_payload)
    assert built.model_dump(mode="json") == stored.model_dump(mode="json")
    assert stored.observed_path_count == len(stored.field_contracts) == 13_756
    assert stored.value_leaf_path_count == 12_841
    assert stored.empty_container_path_count == 915
    assert stored.unmapped_path_count == 0
    assert stored.typed_schema_complete
    assert not stored.known_to_unknown_allowed
    assert all(
        row.target_field in getattr(s, row.target_model).model_fields
        for row in stored.field_contracts
    )
    assert any(
        row.source_path.startswith("legacy_analysis.top_competitors[]")
        and row.preservation_policy == "canonical_pair_reference_no_duplicate"
        for row in stored.field_contracts
    )
    assert any(
        "candidate_buckets" in row.source_path
        and "[]" in row.source_path
        and row.preservation_policy == "canonical_pair_reference_no_duplicate"
        for row in stored.field_contracts
    )
    assert all(
        row.authoritative_for_v11_analysis
        == (
            row.preservation_policy == "typed_field"
            and row.assignment_mode == "direct"
            and ".legacy" not in row.canonical_typed_path
        )
        for row in stored.field_contracts
    )
    assert all(
        row.normalized_authoritative_for_v11_analysis
        == (row.transform_code != "canonical_reference")
        for row in stored.field_contracts
    )
    assert all(
        row.normalized_target_field
        in getattr(s, row.normalized_target_model).model_fields
        for row in stored.field_contracts
    )
    assert (
        sum(
            row.transform_code == "observed_leaf_to_typed_source_fact"
            for row in stored.field_contracts
        )
        == 6_493
    )
    assert all(
        row.normalization_required
        == (
            row.assignment_mode
            in {
                "normalize_legacy_subtree",
                "scalar_to_singleton_list",
                "bucket_rows_to_sku_refs",
            }
        )
        for row in stored.field_contracts
    )
    assert all(
        ".legacy" not in row.canonical_typed_path
        for row in stored.field_contracts
        if row.authoritative_for_v11_analysis
    )
    by_source = {row.source_path: row for row in stored.field_contracts}
    assert by_source["snapshot.batch_id"].assignment_mode == (
        "scalar_to_singleton_list"
    )
    assert by_source["snapshot.batch_id"].accepted_target_types == ["array"]
    for role in (
        "excluded",
        "price_adjacent",
        "primary_direct",
        "scenario_alternative",
        "strong_direct",
    ):
        contract = by_source[f"legacy_analysis.candidate_buckets.{role}"]
        assert contract.assignment_mode == "bucket_rows_to_sku_refs"
        assert contract.accepted_target_types == ["array"]
    assert all(
        set(row.observed_source_types).issubset(set(row.accepted_target_types))
        for row in stored.field_contracts
        if row.assignment_mode == "direct"
    )
    hash_payload = dict(stored_payload)
    contract_hash = hash_payload.pop("contract_hash")
    assert hashlib.sha256(_canonical_bytes(hash_payload)).hexdigest() == contract_hash
    assert all(not row.duplicate_storage_allowed for row in stored.alias_contracts)
    assert all(
        row.conflict_policy == "fail_roundtrip" for row in stored.alias_contracts
    )
    tampered = dict(stored_payload)
    tampered["contract_hash"] = "0" * 64
    with pytest.raises(ValidationError, match="contract hash is inconsistent"):
        s.LegacyTypedMappingContract.model_validate(tampered)


def test_g29_fixture_normalization_stores_one_pair_and_reference_only_views() -> None:
    builder = _load_builder()
    contract = builder.build_contract()
    normalized_source_paths: set[str] = set()
    promoted_fields = (
        "business_claim_type",
        "business_value_label",
        "business_value_meaning_cn",
        "market_position",
        "sku_excess_explanation",
        "sku_excess_price_explained_abs",
        "sku_excess_weekly_sales_explained_abs",
    )
    promoted_non_null_counts = {field_name: 0 for field_name in promoted_fields}
    for name in REAL_FIXTURE_NAMES:
        with gzip.open(_artifact_dir() / name, "rt", encoding="utf-8") as handle:
            fixture = json.load(handle)
        projection = builder.build_fixture_normalization_projection(fixture)
        assert projection["source_batch_ids"] == [fixture["snapshot"]["batch_id"]]
        all_candidates = fixture["legacy_analysis"]["all_candidates"]
        assert len(projection["canonical_pair_payloads"]) == len(all_candidates)
        assert set(projection["canonical_pair_payloads"]) == {
            row["candidate"]["sku_code"] for row in all_candidates
        }
        assert [
            (row["candidate_sku_code"], row["selection_rank"], row["pair_ref"])
            for row in projection["priority_pair_refs"]
        ] == [
            (
                row["candidate"]["sku_code"],
                rank,
                f"pair:{row['candidate']['sku_code']}",
            )
            for rank, row in enumerate(
                fixture["legacy_analysis"]["top_competitors"],
                start=1,
            )
        ]
        for role, rows in fixture["legacy_analysis"]["candidate_buckets"].items():
            assert projection["role_buckets"][role] == sorted(
                {row["sku_code"] for row in rows}
            )
        normalized_source_paths.update(
            fact.source_path
            for fact in builder.iter_normalized_source_facts(fixture, contract)
        )
        claim_value_payloads = [fixture["legacy_input"]["target_claim_value"]] + [
            row["candidate_claim_value"]
            for row in fixture["legacy_input"]["candidates"]
        ]
        claim_contribution_payloads = [
            fixture["legacy_input"]["target_claim_contribution"]
        ] + [
            row["candidate_claim_contribution"]
            for row in fixture["legacy_input"]["candidates"]
        ]
        purchase_reason_payloads = [
            row[key]
            for row in fixture["legacy_input"]["candidates"]
            for key in (
                "target_purchase_reason_profile",
                "candidate_purchase_reason_profile",
            )
        ]
        for payload in claim_value_payloads:
            normalized = builder.normalize_claim_value_snapshot(payload)
            assert len(normalized.claim_values) == len(payload["claim_values"])
            assert len(normalized.attributions) == len(payload["attributions"])
            assert all(
                isinstance(row, s.ClaimValueRecord) for row in normalized.claim_values
            )
            for raw, row in zip(
                payload["claim_values"],
                normalized.claim_values,
                strict=True,
            ):
                for field_name in promoted_fields:
                    _assert_projected_field_equal(row, raw, field_name)
                    if field_name in raw and raw[field_name] is not None:
                        promoted_non_null_counts[field_name] += 1
            for raw, row in zip(
                payload["sku_level_claim_values"],
                normalized.sku_level_claim_values,
                strict=True,
            ):
                _assert_projected_field_equal(row, raw, "claim_source_type_cn")
                for field_name in promoted_fields:
                    _assert_projected_field_equal(row, raw, field_name)
                    if field_name in raw and raw[field_name] is not None:
                        promoted_non_null_counts[field_name] += 1
        for payload in claim_contribution_payloads:
            normalized = builder.normalize_claim_contribution_snapshot(payload)
            assert len(normalized.attributions) == payload["attribution_count"]
            assert all(
                isinstance(row, s.ClaimAttributionRecord)
                for row in normalized.attributions
            )
            for raw_attribution, attribution in zip(
                payload["attributions"],
                normalized.attributions,
                strict=True,
            ):
                for field_name in (
                    "brand_name",
                    "model_name",
                    "price_band_group",
                    "size_tier",
                ):
                    _assert_projected_field_equal(
                        attribution,
                        raw_attribution,
                        field_name,
                    )
                for bucket_name in (
                    "positive_claims",
                    "drag_claims",
                    "opportunity_claims",
                ):
                    for raw, row in zip(
                        raw_attribution.get(bucket_name, []),
                        getattr(attribution, bucket_name),
                        strict=True,
                    ):
                        for field_name in promoted_fields:
                            _assert_projected_field_equal(row, raw, field_name)
                            if field_name in raw and raw[field_name] is not None:
                                promoted_non_null_counts[field_name] += 1
        for payload in purchase_reason_payloads:
            normalized = builder.normalize_purchase_reason_snapshot(payload)
            assert len(normalized.anchors) == len(payload["anchors"])
            assert all(
                isinstance(row, s.PurchaseReasonAnchorRecord)
                for row in normalized.anchors
            )
    assert normalized_source_paths == {
        row.source_path
        for row in contract.field_contracts
        if row.transform_code == "observed_leaf_to_typed_source_fact"
    }
    assert all(count > 0 for count in promoted_non_null_counts.values())


def test_normalized_source_facts_preserve_duplicate_occurrences_and_row_paths() -> None:
    builder = _load_builder()
    with gzip.open(
        _artifact_dir() / REAL_FIXTURE_NAMES[0],
        "rt",
        encoding="utf-8",
    ) as handle:
        fixture = json.load(handle)
    source_path = (
        "legacy_input.candidates[].anchor_substitutability.match_details[]."
        "evidence_comparison_cn"
    )
    candidate_rows = fixture["legacy_input"]["candidates"]
    row_index, source_row = next(
        (index, row)
        for index, row in enumerate(candidate_rows)
        if row["candidate"]["sku_code"] == "TV00028909"
    )
    expected_values = [
        row["evidence_comparison_cn"]
        for row in source_row["anchor_substitutability"]["match_details"]
    ]
    fact = next(
        row
        for row in builder.iter_normalized_source_facts(fixture)
        if row.entity_key == "TV00028909" and row.source_path == source_path
    )
    assert len(expected_values) == 3
    assert fact.occurrence_count == 3
    assert [row.raw_value for row in fact.source_occurrences] == expected_values
    assert [row.ordinal for row in fact.source_occurrences] == [0, 1, 2]
    assert [row.occurrence_key for row in fact.source_occurrences] == [
        (
            f"legacy_input.candidates[{row_index}].anchor_substitutability."
            f"match_details[{index}].evidence_comparison_cn"
        )
        for index in range(3)
    ]


@pytest.mark.parametrize(
    ("raw_value", "tampered_typed"),
    [
        (
            True,
            {
                "presence": "known",
                "value": 999,
                "source_path": "saved.support.fact",
                "evidence_refs": [_evidence_ref()],
            },
        ),
        (
            True,
            {
                "presence": "known",
                "value": 1,
                "source_path": "saved.support.fact",
                "evidence_refs": [_evidence_ref()],
            },
        ),
        (
            None,
            {
                "presence": "missing",
                "unknown_reason_code": "not_observed",
                "source_path": "saved.support.fact",
                "evidence_refs": [_evidence_ref()],
            },
        ),
        (
            "-",
            {
                "presence": "explicit_null",
                "source_path": "saved.support.fact",
                "evidence_refs": [_evidence_ref()],
            },
        ),
        (
            1,
            {
                "presence": "conflict",
                "conflicting_values": [1, 2],
                "source_path": "saved.support.fact",
                "evidence_refs": [_evidence_ref()],
            },
        ),
    ],
)
def test_normalized_source_fact_recomputes_typed_value_from_raw_occurrence(
    raw_value: object,
    tampered_typed: dict,
) -> None:
    payload = _saved_source_fact()
    payload["values"] = [tampered_typed]
    payload["source_occurrences"][0]["raw_value"] = raw_value
    payload["source_occurrences"][0]["typed_value"] = tampered_typed
    payload["source_value_hash"] = hashlib.sha256(
        _canonical_bytes(
            [
                {
                    "occurrence_key": "saved.support.fact",
                    "raw_value": raw_value,
                }
            ]
        )
    ).hexdigest()
    with pytest.raises(ValidationError, match="derived from raw occurrences"):
        s.NormalizedSourceFact.model_validate(payload)


def test_normalized_source_fact_requires_conflict_safe_resolved_value() -> None:
    payload = _saved_source_fact()
    typed_a = {
        "presence": "known",
        "value": "a",
        "source_path": "saved.support.fact",
        "evidence_refs": [_evidence_ref()],
    }
    typed_b = {**typed_a, "value": "b"}
    payload["values"] = [typed_a, typed_b]
    payload["source_occurrences"] = [
        {
            "occurrence_key": "saved.support.fact#0",
            "ordinal": 0,
            "raw_value": "a",
            "typed_value": typed_a,
        },
        {
            "occurrence_key": "saved.support.fact#1",
            "ordinal": 1,
            "raw_value": "b",
            "typed_value": typed_b,
        },
    ]
    payload["occurrence_count"] = 2
    payload["source_value_hash"] = hashlib.sha256(
        _canonical_bytes(
            [
                {"occurrence_key": "saved.support.fact#0", "raw_value": "a"},
                {"occurrence_key": "saved.support.fact#1", "raw_value": "b"},
            ]
        )
    ).hexdigest()
    payload["resolved_value"] = {
        "presence": "conflict",
        "conflicting_values": ["a", "b"],
        "unknown_reason_code": "source_value_conflict",
        "source_path": "saved.support.fact",
        "evidence_refs": [_evidence_ref()],
    }

    fact = s.NormalizedSourceFact.model_validate(payload)
    assert fact.resolved_value is not None
    assert fact.resolved_value.presence == "conflict"

    payload["resolved_value"] = typed_a
    with pytest.raises(ValidationError, match="preserve every distinct known value"):
        s.NormalizedSourceFact.model_validate(payload)
