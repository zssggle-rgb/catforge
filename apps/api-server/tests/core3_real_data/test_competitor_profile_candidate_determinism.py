from __future__ import annotations

import copy
import inspect
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst import (
    competitor_profile_candidate_determinism as determinism_module,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism import (
    CandidatePipelineDeterminismGuard,
    CandidatePipelineDuplicateConflictError,
    CandidatePipelineHashIntegrityError,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_determinism_schemas import (
    CandidatePipelineDeterminismReceipt,
    ModuleCanonicalizationStats,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_eligibility_schemas import (
    CandidateEligibilityConfig,
    CandidateEligibilityManifest,
)
from app.services.core3_real_data.analyst.competitor_profile_candidate_recall_schemas import (
    CandidateRecallConfig,
    CandidateRecallManifest,
    RecallFact,
    RecalledCandidate,
)
from app.services.core3_real_data.analyst.competitor_profile_input_schemas import (
    CompetitorProfileCategoryInputBundle,
    CompetitorProfileTargetInputBundle,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
    _target_bundle,
)


def _run(
    bundle: CompetitorProfileCategoryInputBundle,
    target_sku_code: str,
    **kwargs: Any,
) -> Any:
    return CandidatePipelineDeterminismGuard().run(
        bundle,
        _target_bundle(bundle, target_sku_code),
        **kwargs,
    )


def _duplicate_category_record(
    bundle: CompetitorProfileCategoryInputBundle,
    module_code: str,
    sku_code: str,
    *,
    conflict: bool = False,
) -> CompetitorProfileCategoryInputBundle:
    payload = bundle.model_dump(mode="python")
    rows = payload["modules"][module_code]["records_by_sku"][sku_code]
    duplicate = copy.deepcopy(rows[0])
    if conflict:
        duplicate["facts"]["conflicting_duplicate_marker"] = True
    rows.append(duplicate)
    rows.sort(key=lambda row: (row["source_batch_id"], row["record_id"]))
    payload["modules"][module_code]["record_count"] += 1
    return CompetitorProfileCategoryInputBundle.model_validate(payload)


def _duplicate_target_record(
    target: CompetitorProfileTargetInputBundle,
    module_code: str,
) -> CompetitorProfileTargetInputBundle:
    payload = target.model_dump(mode="python")
    row = copy.deepcopy(payload["modules"][module_code]["records"][0])
    ref = copy.deepcopy(payload["modules"][module_code]["evidence_refs"][0])
    payload["modules"][module_code]["records"].append(row)
    payload["modules"][module_code]["evidence_refs"].append(ref)
    payload["evidence_refs"].append(ref)
    return CompetitorProfileTargetInputBundle.model_validate(payload)


def _source_pages(
    bundle: CompetitorProfileCategoryInputBundle,
) -> dict[str, list[list[Any]]]:
    pages: dict[str, list[list[Any]]] = {}
    for module_code, module in bundle.modules.items():
        records = [
            record
            for sku_code in module.records_by_sku
            for record in module.records_by_sku[sku_code]
        ]
        pages[module_code] = [
            list(reversed(records[1::2])),
            list(reversed(records[::2])),
        ]
    return pages


def test_two_pass_generation_is_idempotent_and_emits_typed_hash_receipt() -> None:
    bundle = _category_bundle()
    first = _run(bundle, "TV000001")
    second = _run(bundle, "TV000001")

    assert first.recall_manifest.model_dump(
        mode="json"
    ) == second.recall_manifest.model_dump(mode="json")
    assert first.eligibility_manifest.model_dump(
        mode="json"
    ) == second.eligibility_manifest.model_dump(mode="json")
    assert first.receipt.result_hash == second.receipt.result_hash
    assert first.receipt.mode == "generated"
    assert first.receipt.replay_count == 2
    assert first.receipt.candidate_count == 4
    assert first.receipt.question_assessment_count == 32
    assert {row.check_code for row in first.receipt.checks} >= {
        "candidate_conservation",
        "canonical_source_deduplication",
        "eligibility_replay_idempotency",
        "recall_replay_idempotency",
        "stable_hash_chain",
    }


def test_canonicalization_reuses_typed_source_records_without_deep_copy() -> None:
    bundle = _category_bundle()
    original = bundle.modules["M12C"].records_by_sku["TV000002"][0]

    generated = _run(bundle, "TV000001")

    canonical = generated.category_bundle.modules["M12C"].records_by_sku[
        "TV000002"
    ][0]
    assert canonical is original
    assert canonical.facts is original.facts


def test_verify_recomputes_every_nested_hash_chain_and_rejects_tampering() -> None:
    bundle = _category_bundle()
    target = _target_bundle(bundle, "TV000001")
    generated = CandidatePipelineDeterminismGuard().run(bundle, target)
    receipt = CandidatePipelineDeterminismGuard().verify(
        bundle,
        target,
        generated.recall_manifest,
        generated.eligibility_manifest,
    )
    assert receipt.mode == "verified"
    assert {row.check_code for row in receipt.checks} >= {
        "provided_eligibility_hash_chain_verified",
        "provided_recall_hash_chain_verified",
    }

    recall_payload = generated.recall_manifest.model_dump(mode="python")
    recall_payload["candidates"][0]["recall_facts"][0]["result_hash"] = (
        "tampered-recall-fact-hash"
    )
    with pytest.raises(CandidatePipelineHashIntegrityError, match="recall manifest"):
        CandidatePipelineDeterminismGuard().verify(
            bundle,
            target,
            CandidateRecallManifest.model_validate(recall_payload),
            generated.eligibility_manifest,
        )

    eligibility_payload = generated.eligibility_manifest.model_dump(mode="python")
    eligibility_payload["candidates"][0]["question_readiness"][0]["result_hash"] = (
        "tampered-question-hash"
    )
    with pytest.raises(
        CandidatePipelineHashIntegrityError, match="eligibility manifest"
    ):
        CandidatePipelineDeterminismGuard().verify(
            bundle,
            target,
            generated.recall_manifest,
            CandidateEligibilityManifest.model_validate(eligibility_payload),
        )


def test_exact_duplicate_source_and_target_records_are_deduped_without_changing_results() -> (
    None
):
    bundle = _category_bundle()
    target = _target_bundle(bundle, "TV000001")
    baseline = CandidatePipelineDeterminismGuard().run(bundle, target)
    duplicated_bundle = _duplicate_category_record(
        bundle,
        "M12C",
        "TV000002",
    )
    duplicated_target = _duplicate_target_record(target, "M07")
    duplicated = CandidatePipelineDeterminismGuard().run(
        duplicated_bundle,
        duplicated_target,
    )

    assert (
        duplicated.recall_manifest.result_hash == baseline.recall_manifest.result_hash
    )
    assert (
        duplicated.eligibility_manifest.result_hash
        == baseline.eligibility_manifest.result_hash
    )
    assert duplicated.category_bundle.modules["M12C"].record_count == (
        bundle.modules["M12C"].record_count
    )
    assert len(duplicated.target_bundle.modules["M07"].records) == 1
    stats = {row.module_code: row for row in duplicated.receipt.canonicalization_stats}
    assert stats["M12C"].category_exact_duplicate_count == 1
    assert stats["M07"].target_exact_duplicate_count == 1


def test_same_business_key_with_conflicting_content_fails_closed() -> None:
    bundle = _duplicate_category_record(
        _category_bundle(),
        "M12C",
        "TV000002",
        conflict=True,
    )
    with pytest.raises(
        CandidatePipelineDuplicateConflictError,
        match="conflicting duplicate source record",
    ):
        _run(bundle, "TV000001")


def test_page_grouping_and_record_order_do_not_change_pipeline_results() -> None:
    bundle = _category_bundle()
    target = _target_bundle(bundle, "TV000001")
    baseline = CandidatePipelineDeterminismGuard().run(bundle, target)
    regrouped = CandidatePipelineDeterminismGuard().run(
        bundle,
        target,
        source_pages=_source_pages(bundle),
    )

    assert regrouped.recall_manifest.result_hash == baseline.recall_manifest.result_hash
    assert (
        regrouped.eligibility_manifest.result_hash
        == baseline.eligibility_manifest.result_hash
    )
    assert regrouped.receipt.result_hash == baseline.receipt.result_hash

    pages = _source_pages(bundle)
    pages["M12C"][0] = pages["M12C"][0][1:]
    with pytest.raises(CandidatePipelineHashIntegrityError):
        CandidatePipelineDeterminismGuard().run(
            bundle,
            target,
            source_pages=pages,
        )


def test_config_authority_and_protected_fact_changes_propagate_to_downstream_hashes() -> (
    None
):
    bundle = _category_bundle()
    baseline = _run(bundle, "TV000001")

    custom_recall = _run(
        bundle,
        "TV000001",
        recall_config=CandidateRecallConfig(
            config_version="test-recall-config-revision-v2"
        ),
    )
    assert (
        custom_recall.recall_manifest.result_hash
        != baseline.recall_manifest.result_hash
    )
    assert (
        custom_recall.eligibility_manifest.result_hash
        != baseline.eligibility_manifest.result_hash
    )

    custom_eligibility = _run(
        bundle,
        "TV000001",
        eligibility_config=CandidateEligibilityConfig(
            config_version="test-eligibility-config-revision-v2"
        ),
    )
    assert (
        custom_eligibility.recall_manifest.result_hash
        == baseline.recall_manifest.result_hash
    )
    assert (
        custom_eligibility.eligibility_manifest.result_hash
        != baseline.eligibility_manifest.result_hash
    )

    authority_payload = bundle.model_dump(mode="python")
    authority_payload["input_fingerprint"] = "changed-exact-authority-fingerprint"
    changed_authority = _run(
        CompetitorProfileCategoryInputBundle.model_validate(authority_payload),
        "TV000001",
    )
    assert (
        changed_authority.recall_manifest.result_hash
        != baseline.recall_manifest.result_hash
    )

    changed_fact_bundle = bundle.model_copy(deep=True)
    changed_fact_bundle.modules["M12C"].records_by_sku["TV000002"][0].facts[
        "claim_value_role"
    ] = "known_absent"
    changed_fact = _run(changed_fact_bundle, "TV000001")
    assert (
        changed_fact.recall_manifest.result_hash == baseline.recall_manifest.result_hash
    )
    assert (
        changed_fact.eligibility_manifest.result_hash
        != baseline.eligibility_manifest.result_hash
    )


def test_tv_ac_and_empty_candidate_manifests_keep_the_same_contract() -> None:
    tv = _run(_category_bundle(), "TV000001")
    assert tv.receipt.category_code == "TV"

    ac_target = _default_spec("AC", 1)
    ac_target.update(
        {
            "task_primary": "sleep",
            "purchase_reasons": ["quiet"],
            "claim_values": ["quiet-cooling"],
        }
    )
    ac_candidate = _default_spec("AC", 2)
    ac_candidate.update(
        {
            "task_primary": "sleep",
            "purchase_reasons": ["quiet"],
            "claim_values": ["quiet-cooling"],
        }
    )
    ac = _run(_category_bundle("AC", [ac_target, ac_candidate]), "AC000001")
    assert ac.receipt.category_code == "AC"
    assert ac.receipt.candidate_count == 1

    target = _default_spec("TV", 1)
    unrelated = _default_spec("TV", 2)
    unrelated.update(
        {
            "price": Decimal("9000"),
            "screen_size": Decimal("55"),
            "size_segment": "55",
            "market_pool": "unrelated",
        }
    )
    empty = _run(_category_bundle(specs=[target, unrelated]), "TV000001")
    assert empty.receipt.candidate_count == 0
    assert empty.receipt.question_assessment_count == 0
    assert empty.recall_manifest.candidates == []
    assert empty.eligibility_manifest.candidates == []


def test_nested_dtos_reject_duplicate_evidence_facts_and_questions() -> None:
    generated = _run(_category_bundle(), "TV000001")
    candidate = generated.recall_manifest.candidates[0]
    fact = candidate.recall_facts[0]

    fact_payload = fact.model_dump(mode="python")
    fact_payload["target_evidence_refs"].append(
        copy.deepcopy(fact_payload["target_evidence_refs"][0])
    )
    fact_payload["target_evidence_refs"].sort(
        key=lambda row: (
            row["module_code"],
            row.get("source_batch_id") or "",
            row["record_type"],
            row["record_id"],
            row["result_hash"],
        )
    )
    with pytest.raises(ValidationError, match="evidence refs"):
        RecallFact.model_validate(fact_payload)

    candidate_payload = candidate.model_dump(mode="python")
    candidate_payload["recall_facts"].append(
        copy.deepcopy(candidate_payload["recall_facts"][0])
    )
    candidate_payload["recall_facts"].sort(
        key=lambda row: (
            row["entry_code"],
            row["reason_code"],
            tuple(row["matched_values"]),
        )
    )
    with pytest.raises(ValidationError, match="facts"):
        RecalledCandidate.model_validate(candidate_payload)

    eligibility_payload = generated.eligibility_manifest.candidates[0].model_dump(
        mode="python"
    )
    eligibility_payload["question_readiness"].append(
        copy.deepcopy(eligibility_payload["question_readiness"][0])
    )
    with pytest.raises(ValidationError, match="all provisional questions"):
        generated.eligibility_manifest.candidates[0].__class__.model_validate(
            eligibility_payload
        )


def test_receipt_schemas_reject_count_and_order_contradictions() -> None:
    receipt = _run(_category_bundle(), "TV000001").receipt
    stat_payload = receipt.canonicalization_stats[0].model_dump(mode="python")
    stat_payload["category_exact_duplicate_count"] += 1
    with pytest.raises(ValidationError, match="counts are inconsistent"):
        ModuleCanonicalizationStats.model_validate(stat_payload)

    receipt_payload = receipt.model_dump(mode="python")
    receipt_payload["question_assessment_count"] += 1
    with pytest.raises(ValidationError, match="eight questions"):
        CandidatePipelineDeterminismReceipt.model_validate(receipt_payload)

    receipt_payload = receipt.model_dump(mode="python")
    receipt_payload["checks"] = list(reversed(receipt_payload["checks"]))
    with pytest.raises(ValidationError, match="checks must be sorted"):
        CandidatePipelineDeterminismReceipt.model_validate(receipt_payload)


def test_candidate_conservation_multi_entry_dedup_and_runtime_boundaries() -> None:
    generated = _run(_category_bundle(), "TV000001")
    recall_codes = [
        row.candidate.sku_code for row in generated.recall_manifest.candidates
    ]
    eligibility_codes = [
        row.candidate.sku_code for row in generated.eligibility_manifest.candidates
    ]
    assert recall_codes == eligibility_codes
    assert len(recall_codes) == len(set(recall_codes))
    direct = next(
        row
        for row in generated.recall_manifest.candidates
        if row.candidate.sku_code == "TV000002"
    )
    assert len(direct.recall_sources) > 1
    assert generated.receipt.candidate_count == len(recall_codes)

    source = inspect.getsource(determinism_module).lower()
    assert "sqlalchemy" not in source
    assert "repository" not in source
    assert "openai" not in source
    assert ".query(" not in source
