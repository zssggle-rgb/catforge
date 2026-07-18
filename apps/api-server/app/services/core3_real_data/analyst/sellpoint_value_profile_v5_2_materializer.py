"""Deterministic V5.2 materialization over the proven V5.1 value profile."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app.services.core3_real_data.analyst.sellpoint_value_profile_persistence_schemas import (
    SellpointValueDraftBundle,
    SkuSellpointValueCandidateDraft,
    SkuSellpointValueItemDraft,
    SkuSellpointValueProfileDraft,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer import (
    build_v5_1_profile_input_fingerprint,
    materialize_sellpoint_value_profile_v5_1,
    project_v5_1_profile_to_persistence,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_mapping import (
    SPV_V5_2_LAYER_MAPPING_VERSION,
    build_layered_sellpoint_analysis,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52MaterializationInput,
    SellpointValueV52MaterializedDraft,
    SellpointValueV52Profile,
    SellpointValueV52SourceHashes,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    SPV_V5_2_METHOD_VERSION,
    SPV_V5_2_RULE_VERSION,
    SPV_V5_2_SCHEMA_VERSION,
)
from app.services.core3_real_data.hash_utils import stable_hash


SPV_V5_2_PROFILE_INPUT_HASH_VERSION = "sellpoint_value_profile_input_v5_2"
SPV_V5_2_PROFILE_RESULT_HASH_VERSION = "sellpoint_value_profile_result_v5_2"
SPV_V5_2_MISSING_M04C_HASH_VERSION = "sellpoint_value_missing_m04c_v5_2"
SPV_V5_2_COMPETITOR_SELLPOINT_HASH_VERSION = (
    "sellpoint_value_competitor_sellpoints_v5_2"
)


def build_v5_2_source_hashes(
    source: SellpointValueV52MaterializationInput,
) -> SellpointValueV52SourceHashes:
    base = source.base
    m04c = source.source_sellpoints
    return SellpointValueV52SourceHashes(
        m04c_profile_result_hash=(
            m04c.lineage.profile_result_hash
            if m04c.lineage is not None
            else stable_hash(
                m04c.model_dump(mode="json"),
                version=SPV_V5_2_MISSING_M04C_HASH_VERSION,
            )
        ),
        m03b_parameter_result_hashes=sorted(
            {
                row.source_snapshot_result_hash
                for row in base.competitor_source.target_parameter_facts
            }
        ),
        upstream_result_hashes=dict(
            sorted(
                (row.source_code, row.result_hash)
                for row in base.source_lineage
            )
        ),
        user_value_result_hashes=sorted(
            {row.value_conclusion.result_hash for row in base.values}
        ),
        competitor_profile_result_hash=(
            base.competitor_source.source_version_result_hash
        ),
        competitor_sku_result_hash=base.competitor_source.source_result_hash,
        competitor_sellpoint_result_hash=stable_hash(
            [
                row.model_dump(mode="json")
                for row in sorted(
                    source.competitor_sellpoints,
                    key=lambda item: (
                        item.candidate_sku_code,
                        item.source_sellpoint.claim_fact_id,
                    ),
                )
            ],
            version=SPV_V5_2_COMPETITOR_SELLPOINT_HASH_VERSION,
        ),
    )


def build_v5_2_profile_input_fingerprint(
    source: SellpointValueV52MaterializationInput,
) -> str:
    """Bind M04C, M03B, user value, competitor, and mapping rule inputs."""

    layered = build_layered_sellpoint_analysis(
        category_code=source.base.category_code,
        target_sku_code=source.base.target.sku_code,
        source_sellpoints=source.source_sellpoints,
        values=source.base.values,
        target_parameter_facts=source.base.competitor_source.target_parameter_facts,
        competitor_sellpoints=source.competitor_sellpoints,
    )
    return _profile_input_hash(
        base_profile_input_fingerprint=build_v5_1_profile_input_fingerprint(
            source.base
        ),
        source_hashes=build_v5_2_source_hashes(source),
        source_sellpoints=source.source_sellpoints,
        competitor_sellpoint_findings=[
            row.model_dump(mode="json")
            for row in layered.competitor_sellpoint_findings
        ],
    )


def build_v5_2_profile_input_fingerprint_from_profile(
    profile: SellpointValueV52Profile,
) -> str:
    return _profile_input_hash(
        base_profile_input_fingerprint=profile.base_profile.input_fingerprint,
        source_hashes=profile.source_hashes,
        source_sellpoints=profile.source_sellpoints,
        competitor_sellpoint_findings=[
            row.model_dump(mode="json")
            for row in profile.layered_sellpoint_analysis.competitor_sellpoint_findings
        ],
    )


def build_v5_2_profile_result_hash(profile: SellpointValueV52Profile) -> str:
    return stable_hash(
        profile.model_dump(mode="json", exclude={"result_hash"}),
        version=SPV_V5_2_PROFILE_RESULT_HASH_VERSION,
    )


def materialize_sellpoint_value_profile_v5_2(
    source: SellpointValueV52MaterializationInput,
    *,
    sellpoint_value_profile_version_id: str,
) -> SellpointValueV52MaterializedDraft:
    """Build one source-grounded V5.2 immutable draft."""

    base = materialize_sellpoint_value_profile_v5_1(
        source.base,
        sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
    ).profile
    layered = build_layered_sellpoint_analysis(
        category_code=base.category_code,
        target_sku_code=base.target.sku_code,
        source_sellpoints=source.source_sellpoints,
        values=base.values,
        target_parameter_facts=base.competitor_source.target_parameter_facts,
        competitor_sellpoints=source.competitor_sellpoints,
    )
    unhashed = SellpointValueV52Profile(
        base_profile=base,
        source_hashes=build_v5_2_source_hashes(source),
        source_sellpoints=source.source_sellpoints,
        layered_sellpoint_analysis=layered,
        input_fingerprint=_profile_input_hash(
            base_profile_input_fingerprint=base.input_fingerprint,
            source_hashes=build_v5_2_source_hashes(source),
            source_sellpoints=source.source_sellpoints,
            competitor_sellpoint_findings=[
                row.model_dump(mode="json")
                for row in layered.competitor_sellpoint_findings
            ],
        ),
        result_hash="pending",
    )
    profile = unhashed.model_copy(
        update={"result_hash": build_v5_2_profile_result_hash(unhashed)}
    )
    return SellpointValueV52MaterializedDraft(
        profile=profile,
        persistence_bundle=project_v5_2_profile_to_persistence(
            profile,
            sellpoint_value_profile_version_id=(
                sellpoint_value_profile_version_id
            ),
        ),
    )


def project_v5_2_profile_to_persistence(
    profile: SellpointValueV52Profile,
    *,
    sellpoint_value_profile_version_id: str,
) -> SellpointValueDraftBundle:
    """Project V5.2 into the existing four-table persistence contract."""

    base_bundle = project_v5_1_profile_to_persistence(
        profile.base_profile,
        sellpoint_value_profile_version_id=sellpoint_value_profile_version_id,
    )
    scope = {
        "schema_version": SPV_V5_2_SCHEMA_VERSION,
        "rule_version": SPV_V5_2_RULE_VERSION,
        "method_version": SPV_V5_2_METHOD_VERSION,
        "input_fingerprint": profile.input_fingerprint,
    }
    candidates = [
        SkuSellpointValueCandidateDraft.model_validate(
            {**row.model_dump(mode="python"), **scope}
        )
        for row in base_bundle.candidates
    ]
    value_items = [
        SkuSellpointValueItemDraft.model_validate(
            {**row.model_dump(mode="python"), **scope}
        )
        for row in base_bundle.value_items
    ]
    base_row = base_bundle.profile
    layered = profile.layered_sellpoint_analysis
    evidence_refs = _dedupe_evidence_refs(
        [
            *profile.base_profile.evidence_refs,
            *_layered_evidence_refs(profile),
        ]
    )
    limitations = sorted(
        {
            *profile.base_profile.limitations,
            *profile.source_sellpoints.limitations,
            *layered.limitations,
        }
    )
    profile_payload = {
        **base_row.model_dump(mode="python"),
        **scope,
        "result_hash": profile.result_hash,
        "source_lineage_json": [
            *base_row.source_lineage_json,
            {
                "record_type": "m04c_source_sellpoints",
                "payload": profile.source_sellpoints.model_dump(mode="json"),
            },
        ],
        "pm_decisions_json": {
            "record_type": "sku_conclusion",
            "payload": profile.base_profile.sku_conclusion.model_dump(mode="json"),
            "v5_1_base_profile_meta": {
                "input_fingerprint": profile.base_profile.input_fingerprint,
                "result_hash": profile.base_profile.result_hash,
                "evidence_refs": [
                    row.model_dump(mode="json")
                    for row in profile.base_profile.evidence_refs
                ],
                "limitations": profile.base_profile.limitations,
            },
            "source_hashes": profile.source_hashes.model_dump(mode="json"),
            "layered_sellpoint_analysis": layered.model_dump(mode="json"),
        },
        "qa_index_json": [
            *base_row.qa_index_json,
            {
                "record_type": "layered_sellpoint_analysis",
                "result_hash": layered.result_hash,
            },
        ],
        "evidence_summary_json": {
            **base_row.evidence_summary_json,
            "source_sellpoint_count": len(layered.source_sellpoints),
            "sellpoint_assessment_count": len(layered.sellpoint_assessments),
            "parameter_assessment_count": len(layered.parameter_assessments),
            "competitor_sellpoint_finding_count": len(
                layered.competitor_sellpoint_findings
            ),
            "layer_integrity_summary": layered.integrity.model_dump(mode="json"),
            "evidence_ref_count": len(evidence_refs),
        },
        "evidence_refs_json": evidence_refs,
        "limitations_json": limitations,
    }
    persisted_profile = SkuSellpointValueProfileDraft.model_validate(
        profile_payload
    )
    return SellpointValueDraftBundle(
        profile=persisted_profile,
        candidates=candidates,
        value_items=value_items,
    )


def _layered_evidence_refs(
    profile: SellpointValueV52Profile,
) -> list[SellpointValueEvidenceRef]:
    source = profile.source_sellpoints
    layered = profile.layered_sellpoint_analysis
    return [
        *([source.lineage.evidence_ref] if source.lineage is not None else []),
        *(ref for row in source.source_sellpoints for ref in row.evidence_refs),
        *(ref for row in layered.sellpoint_parameter_links for ref in row.evidence_refs),
        *(ref for row in layered.sellpoint_user_value_links for ref in row.evidence_refs),
        *(ref for row in layered.sellpoint_assessments for ref in row.evidence_refs),
        *(ref for row in layered.parameter_assessments for ref in row.evidence_refs),
        *(
            ref
            for row in layered.competitor_sellpoint_findings
            for ref in row.evidence_refs
        ),
    ]


def _profile_input_hash(
    *,
    base_profile_input_fingerprint: str,
    source_hashes: SellpointValueV52SourceHashes,
    source_sellpoints: Any,
    competitor_sellpoint_findings: list[dict[str, Any]],
) -> str:
    return stable_hash(
        {
            "schema_version": SPV_V5_2_SCHEMA_VERSION,
            "rule_version": SPV_V5_2_RULE_VERSION,
            "method_version": SPV_V5_2_METHOD_VERSION,
            "mapping_version": SPV_V5_2_LAYER_MAPPING_VERSION,
            "base_profile_input_fingerprint": base_profile_input_fingerprint,
            "source_hashes": source_hashes.model_dump(mode="json"),
            "source_sellpoints": source_sellpoints.model_dump(mode="json"),
            "competitor_sellpoint_findings": competitor_sellpoint_findings,
        },
        version=SPV_V5_2_PROFILE_INPUT_HASH_VERSION,
    )


def _dedupe_evidence_refs(
    values: Iterable[SellpointValueEvidenceRef],
) -> list[SellpointValueEvidenceRef]:
    rows: dict[tuple[Any, ...], SellpointValueEvidenceRef] = {}
    for row in values:
        payload = row.model_dump(mode="json")
        key = (
            payload.get("module_code"),
            payload.get("record_type"),
            payload.get("record_id"),
            payload.get("result_hash"),
        )
        rows[key] = row
    return [rows[key] for key in sorted(rows)]


__all__ = [
    "SPV_V5_2_MISSING_M04C_HASH_VERSION",
    "SPV_V5_2_PROFILE_INPUT_HASH_VERSION",
    "SPV_V5_2_PROFILE_RESULT_HASH_VERSION",
    "build_v5_2_profile_input_fingerprint",
    "build_v5_2_profile_input_fingerprint_from_profile",
    "build_v5_2_profile_result_hash",
    "build_v5_2_source_hashes",
    "materialize_sellpoint_value_profile_v5_2",
    "project_v5_2_profile_to_persistence",
]
