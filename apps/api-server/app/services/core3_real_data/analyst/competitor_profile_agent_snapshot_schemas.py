"""Typed contracts for persisting the existing competitor-agent analysis once.

The snapshot is intentionally aligned with ``competitor-set`` live analysis:
candidate discovery, pair analysis, scoring, role assignment, and Top-3 selection
are completed before persistence.  Runtime readers may render the saved result,
but must never repeat those analytical steps.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import json
import zlib
from decimal import Decimal
from io import BytesIO
from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION,
    CompetitorProfileV11BaseModel,
)
from app.services.core3_real_data.hash_utils import stable_hash


AGENT_SNAPSHOT_METHOD_VERSION = "competitor_profile_agent_snapshot_v2"
AGENT_SNAPSHOT_RULE_VERSION = "competitor_profile_agent_snapshot_rule_v2"
AGENT_SNAPSHOT_SOURCE_VERSION = "competitor_set_legacy_analysis_v1"
AGENT_SNAPSHOT_CANDIDATE_LIMIT = 20
AGENT_SNAPSHOT_PRIORITY_LIMIT = 3
AGENT_SNAPSHOT_SKU_PAYLOAD_CODEC = "gzip+base64+json"
AGENT_SNAPSHOT_MAX_COMPRESSED_PAYLOAD_CHARS = 48_000_000
AGENT_SNAPSHOT_MAX_DECOMPRESSED_PAYLOAD_BYTES = 64_000_000


class AgentSkuIdentity(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    product_category: Literal["TV", "AC"]
    size_tier: str | None = None
    price_band_in_size_tier: str | None = None
    screen_size_inch: Decimal | None = Field(default=None, ge=0)
    weighted_price: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    sales_volume_total: Decimal | None = Field(default=None, ge=0)


class AgentSkuSourcePayload(CompetitorProfileV11BaseModel):
    fact_brief: dict[str, Any]
    claim_value: dict[str, Any]
    claim_contribution: dict[str, Any]
    purchase_reason_profile: dict[str, Any]


class AgentCandidateMarket(CompetitorProfileV11BaseModel):
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    size_tier: str | None = None
    price_band_in_size_tier: str | None = None
    screen_size_inch: Decimal | None = Field(default=None, ge=0)
    price_wavg: Decimal | None = Field(default=None, ge=0)
    avg_weekly_sales_volume: Decimal | None = Field(default=None, ge=0)
    sales_volume_total: Decimal | None = Field(default=None, ge=0)
    price_gap_to_target: Decimal | None = None
    price_gap_pct_to_target: Decimal | None = None
    same_pool_sku_count: int | None = Field(default=None, ge=0)
    evidence_id_count: int | None = Field(default=None, ge=0)


class AgentCandidateAnalysisPayload(CompetitorProfileV11BaseModel):
    """The existing agent's already-calculated candidate result."""

    rank: int = Field(ge=1)
    candidate: AgentCandidateMarket
    competitor_score: Decimal = Field(ge=0, le=1)
    basis: dict[str, Any]
    semantic_overlap: dict[str, Any]
    param_claim_overlap: dict[str, Any]
    sales_overlap: dict[str, Any]
    candidate_fact_brief: dict[str, Any]
    candidate_claim_value: dict[str, Any]
    candidate_claim_contribution: dict[str, Any]
    target_purchase_reason_profile: dict[str, Any]
    candidate_purchase_reason_profile: dict[str, Any]
    anchor_substitutability: dict[str, Any]
    value_anchor: dict[str, Any]
    replacement_pressure: dict[str, Any]
    purchase_pressure_comparison: dict[str, Any]
    m12d_consumption: dict[str, Any]
    business_score: Decimal = Field(ge=0, le=1)
    role: str = Field(min_length=1)
    role_cn: str = Field(min_length=1)
    purchase_pool: dict[str, Any]
    weighted_overlap: dict[str, Any]
    matched_dimensions: dict[str, Any]
    market_validation: dict[str, Any]
    selection_gate: dict[str, Any]
    ranking_trace: dict[str, Any]
    ranking_gate_reasons: list[str] = Field(default_factory=list)
    shared_business_context: list[str] = Field(default_factory=list)
    top3_eligible: bool
    exclusion_reason_cn: str | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "AgentCandidateAnalysisPayload":
        if len(self.ranking_gate_reasons) != len(set(self.ranking_gate_reasons)):
            raise ValueError("ranking gate reasons must be unique")
        if len(self.shared_business_context) != len(set(self.shared_business_context)):
            raise ValueError("shared business context must be unique")
        return self


class AgentEvidenceReceipt(CompetitorProfileV11BaseModel):
    source_module: str = Field(min_length=1)
    sku_code: str | None = None
    candidate_sku_code: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    evidence_id_count: int | None = Field(default=None, ge=0)
    profile_version: str | None = None
    result_hash: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class AgentCandidateAnalysisRecord(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    candidate_snapshot_ref: str = Field(min_length=1)
    candidate_snapshot_result_hash: str = Field(min_length=1)
    source_rank: int = Field(ge=1)
    selected_rank: int | None = Field(
        default=None,
        ge=1,
        le=AGENT_SNAPSHOT_PRIORITY_LIMIT,
    )
    analysis: AgentCandidateAnalysisPayload
    evidence: list[AgentEvidenceReceipt] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_record(self) -> "AgentCandidateAnalysisRecord":
        if self.candidate_sku_code != self.analysis.candidate.sku_code:
            raise ValueError("candidate record and analysis SKU must match")
        if self.source_rank != self.analysis.rank:
            raise ValueError("candidate record and analysis rank must match")
        expected = stable_hash(
            self.model_dump(mode="json", exclude={"result_hash"}),
            version="competitor_profile_agent_candidate_result_v2",
        )
        if self.result_hash != expected:
            raise ValueError("candidate result hash is inconsistent")
        return self


class AgentSkuSnapshot(CompetitorProfileV11BaseModel):
    schema_version: Literal["sku_competitor_decision_profile_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
    )
    method_version: Literal["competitor_profile_agent_snapshot_v2"] = (
        AGENT_SNAPSHOT_METHOD_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    identity: AgentSkuIdentity
    payload_codec: Literal["gzip+base64+json"] = AGENT_SNAPSHOT_SKU_PAYLOAD_CODEC
    payload_b64: str = Field(
        min_length=1,
        max_length=AGENT_SNAPSHOT_MAX_COMPRESSED_PAYLOAD_CHARS,
    )
    available_modules: list[str] = Field(default_factory=list)
    evidence: list[AgentEvidenceReceipt] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    snapshot_ref: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_snapshot(self) -> "AgentSkuSnapshot":
        if self.identity.product_category != self.category_code:
            raise ValueError("snapshot category and identity category must match")
        if len(self.available_modules) != len(set(self.available_modules)):
            raise ValueError("snapshot available modules must be unique")
        expected = stable_hash(
            self.model_dump(mode="json", exclude={"result_hash"}),
            version="competitor_profile_agent_sku_snapshot_result_v2",
        )
        if self.result_hash != expected:
            raise ValueError("SKU snapshot result hash is inconsistent")
        return self


class AgentCompetitorProfileSnapshot(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    schema_version: Literal["sku_competitor_decision_profile_v1_1"] = (
        COMPETITOR_PROFILE_V1_1_SCHEMA_VERSION
    )
    method_version: Literal["competitor_profile_agent_snapshot_v2"] = (
        AGENT_SNAPSHOT_METHOD_VERSION
    )
    source_analysis_version: Literal["competitor_set_legacy_analysis_v1"] = (
        AGENT_SNAPSHOT_SOURCE_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    release_scope_key: str = Field(min_length=1)
    storage_batch_id: str = Field(min_length=1)
    source_batch_ids: list[str] = Field(min_length=1)
    target: AgentSkuIdentity
    target_snapshot_ref: str = Field(min_length=1)
    target_snapshot_result_hash: str = Field(min_length=1)
    target_fact_brief: dict[str, Any]
    target_claim_value: dict[str, Any]
    target_claim_contribution: dict[str, Any]
    m12d_consumption: dict[str, Any]
    candidate_pool_policy: list[str] = Field(min_length=1)
    candidate_pool_order: list[str] = Field(default_factory=list)
    analysis_order: list[str] = Field(default_factory=list)
    candidates: list[AgentCandidateAnalysisRecord] = Field(default_factory=list)
    priority_order: list[str] = Field(
        default_factory=list,
        max_length=AGENT_SNAPSHOT_PRIORITY_LIMIT,
    )
    evidence: list[AgentEvidenceReceipt] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    source_analysis_result_hash: str = Field(min_length=1)
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_profile(self) -> "AgentCompetitorProfileSnapshot":
        if self.target.product_category != self.category_code:
            raise ValueError("profile category and target category must match")
        candidate_codes = [row.candidate_sku_code for row in self.candidates]
        candidate_set = set(candidate_codes)
        if len(candidate_codes) != len(candidate_set):
            raise ValueError("profile candidates must be unique")
        if self.target.sku_code in candidate_set:
            raise ValueError("profile cannot contain a self candidate")
        if self.target_fact_brief != {"storage_ref": self.target_snapshot_ref}:
            raise ValueError("target fact brief must reference its shared snapshot")
        if self.target_claim_value != {"storage_ref": self.target_snapshot_ref}:
            raise ValueError("target claim value must reference its shared snapshot")
        if self.target_claim_contribution != {"storage_ref": self.target_snapshot_ref}:
            raise ValueError(
                "target claim contribution must reference its shared snapshot"
            )
        for row in self.candidates:
            expected_ref = {"storage_ref": row.candidate_snapshot_ref}
            if (
                row.analysis.candidate_fact_brief != expected_ref
                or row.analysis.candidate_claim_value != expected_ref
                or row.analysis.candidate_claim_contribution != expected_ref
            ):
                raise ValueError(
                    "candidate heavy payloads must reference one shared snapshot"
                )
        if (
            len(self.candidate_pool_order) != len(candidate_codes)
            or len(set(self.candidate_pool_order)) != len(candidate_codes)
            or set(self.candidate_pool_order) != candidate_set
        ):
            raise ValueError("candidate pool order must cover saved candidates")
        if (
            len(self.analysis_order) != len(candidate_codes)
            or len(set(self.analysis_order)) != len(candidate_codes)
            or set(self.analysis_order) != candidate_set
        ):
            raise ValueError("analysis order must cover saved candidates")
        if len(self.priority_order) != len(set(self.priority_order)):
            raise ValueError("priority order must be unique")
        if not set(self.priority_order).issubset(candidate_set):
            raise ValueError("priority order must reference saved candidates")
        if {row.source_rank for row in self.candidates} != set(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidate source ranks must be unique and contiguous")
        selected = {
            row.candidate_sku_code: row.selected_rank
            for row in self.candidates
            if row.selected_rank is not None
        }
        if selected != {
            sku_code: rank for rank, sku_code in enumerate(self.priority_order, start=1)
        }:
            raise ValueError("saved candidate ranks must match priority order")
        expected = stable_hash(
            self.model_dump(mode="json", exclude={"result_hash"}),
            version="competitor_profile_agent_profile_result_v2",
        )
        if self.result_hash != expected:
            raise ValueError("profile result hash is inconsistent")
        return self


class AgentPairIndexItem(CompetitorProfileV11BaseModel):
    candidate_sku_code: str = Field(min_length=1)
    source_rank: int = Field(ge=1)
    selected_rank: int | None = Field(
        default=None,
        ge=1,
        le=AGENT_SNAPSHOT_PRIORITY_LIMIT,
    )
    role: str = Field(min_length=1)
    business_score: Decimal = Field(ge=0, le=1)
    result_hash: str = Field(min_length=1)


class AgentCompetitorProfileCompact(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    method_version: Literal["competitor_profile_agent_snapshot_v2"] = (
        AGENT_SNAPSHOT_METHOD_VERSION
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    priority_order: list[str] = Field(max_length=AGENT_SNAPSHOT_PRIORITY_LIMIT)
    pair_index: list[AgentPairIndexItem]
    profile_result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_compact(self) -> "AgentCompetitorProfileCompact":
        codes = [row.candidate_sku_code for row in self.pair_index]
        if len(codes) != self.candidate_count or len(codes) != len(set(codes)):
            raise ValueError("compact pair index must match candidate count")
        if {row.source_rank for row in self.pair_index} != set(
            range(1, self.candidate_count + 1)
        ):
            raise ValueError("compact source ranks must be unique and contiguous")
        if len(self.priority_order) != len(set(self.priority_order)):
            raise ValueError("compact priority order must be unique")
        if not set(self.priority_order).issubset(codes):
            raise ValueError("compact priority order must reference pair index")
        return self


class AgentCompetitorProfileReadResult(CompetitorProfileV11BaseModel):
    status: Literal["available", "profile_unavailable"]
    read_mode: Literal["full", "compact"]
    preview: bool = False
    competitor_profile_version_id: str | None = None
    full: AgentCompetitorProfileSnapshot | None = None
    compact: AgentCompetitorProfileCompact | None = None
    sku_snapshots: list[AgentSkuSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_read(self) -> "AgentCompetitorProfileReadResult":
        populated = int(self.full is not None) + int(self.compact is not None)
        if self.status == "profile_unavailable":
            if (
                self.competitor_profile_version_id is not None
                or populated
                or self.sku_snapshots
            ):
                raise ValueError("unavailable reads cannot expose profile data")
            return self
        expected = self.full if self.read_mode == "full" else self.compact
        if (
            self.competitor_profile_version_id is None
            or populated != 1
            or expected is None
        ):
            raise ValueError("available reads require the requested projection")
        if expected.competitor_profile_version_id != self.competitor_profile_version_id:
            raise ValueError("read projection must lock one version")
        if self.read_mode == "compact" and self.sku_snapshots:
            raise ValueError("compact reads cannot load shared SKU payloads")
        if self.read_mode == "full":
            if self.full is None:
                raise ValueError("full reads require a full profile payload")
            expected_codes = {
                self.full.target.sku_code,
                *(row.candidate_sku_code for row in self.full.candidates),
            }
            actual_codes = {row.identity.sku_code for row in self.sku_snapshots}
            if (
                len(self.sku_snapshots) != len(actual_codes)
                or actual_codes != expected_codes
            ):
                raise ValueError("full reads require one shared snapshot per saved SKU")
            snapshots = {row.identity.sku_code: row for row in self.sku_snapshots}
            if (
                snapshots[self.full.target.sku_code].snapshot_ref
                != self.full.target_snapshot_ref
                or snapshots[self.full.target.sku_code].result_hash
                != self.full.target_snapshot_result_hash
            ):
                raise ValueError("target snapshot identity differs from the profile")
            for row in self.full.candidates:
                snapshot = snapshots[row.candidate_sku_code]
                if (
                    snapshot.snapshot_ref != row.candidate_snapshot_ref
                    or snapshot.result_hash != row.candidate_snapshot_result_hash
                ):
                    raise ValueError(
                        "candidate snapshot identity differs from the profile"
                    )
        return self


class AgentCompetitorRuntimeProjection(CompetitorProfileV11BaseModel):
    source: Literal["competitor_profile_v1_1"] = "competitor_profile_v1_1"
    adapter_version: Literal["competitor_profile_agent_snapshot_adapter_v2"] = (
        "competitor_profile_agent_snapshot_adapter_v2"
    )
    competitor_profile_version_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)
    release_scope_key: str = Field(min_length=1)
    target: AgentSkuIdentity
    target_fact_brief: dict[str, Any]
    target_claim_value: dict[str, Any]
    target_claim_contribution: dict[str, Any]
    candidates: list[AgentCandidateAnalysisPayload]
    candidate_pool_order: list[str]
    analysis_order: list[str]
    priority_order: list[str] = Field(max_length=AGENT_SNAPSHOT_PRIORITY_LIMIT)
    evidence: list[AgentEvidenceReceipt]
    limitations: list[str]
    profile_result_hash: str = Field(min_length=1)


class CompetitorProfileAgentSnapshotAdapter:
    """Validate and expose only saved analysis; never score or rank."""

    def adapt(
        self,
        source: AgentCompetitorProfileSnapshot,
        sku_snapshots: list[AgentSkuSnapshot],
    ) -> AgentCompetitorRuntimeProjection:
        frozen = AgentCompetitorProfileSnapshot.model_validate(
            source.model_dump(mode="json")
        )
        by_code = {row.candidate_sku_code: row for row in frozen.candidates}
        snapshots = {
            row.identity.sku_code: AgentSkuSnapshot.model_validate(
                row.model_dump(mode="json")
            )
            for row in sku_snapshots
        }
        expected_codes = {frozen.target.sku_code, *by_code}
        if set(snapshots) != expected_codes:
            raise ValueError("saved profile and shared SKU snapshots do not match")
        source_payloads = {
            sku_code: decode_agent_sku_payload(snapshot)
            for sku_code, snapshot in snapshots.items()
        }
        target_payload = source_payloads[frozen.target.sku_code]
        candidates = []
        for code in frozen.analysis_order:
            record = by_code[code]
            payload = source_payloads[code]
            candidate_data = record.analysis.model_dump(mode="json")
            candidate_data.update(
                {
                    "candidate_fact_brief": payload.fact_brief,
                    "candidate_claim_value": payload.claim_value,
                    "candidate_claim_contribution": payload.claim_contribution,
                    "target_purchase_reason_profile": (
                        target_payload.purchase_reason_profile
                    ),
                    "candidate_purchase_reason_profile": (
                        payload.purchase_reason_profile
                    ),
                }
            )
            candidates.append(
                AgentCandidateAnalysisPayload.model_validate(candidate_data)
            )
        return AgentCompetitorRuntimeProjection(
            competitor_profile_version_id=frozen.competitor_profile_version_id,
            profile_version=frozen.profile_version,
            release_scope_key=frozen.release_scope_key,
            target=frozen.target,
            target_fact_brief=target_payload.fact_brief,
            target_claim_value=target_payload.claim_value,
            target_claim_contribution=target_payload.claim_contribution,
            candidates=candidates,
            candidate_pool_order=frozen.candidate_pool_order,
            analysis_order=frozen.analysis_order,
            priority_order=frozen.priority_order,
            evidence=frozen.evidence,
            limitations=frozen.limitations,
            profile_result_hash=frozen.result_hash,
        )


def encode_agent_sku_payload(payload: AgentSkuSourcePayload) -> str:
    frozen = AgentSkuSourcePayload.model_validate(payload.model_dump(mode="json"))
    raw = json.dumps(
        frozen.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > AGENT_SNAPSHOT_MAX_DECOMPRESSED_PAYLOAD_BYTES:
        raise ValueError("agent SKU source payload exceeds the storage boundary")
    buffer = BytesIO()
    with gzip.GzipFile(
        fileobj=buffer,
        mode="wb",
        compresslevel=1,
        mtime=0,
    ) as stream:
        stream.write(raw)
    compressed = buffer.getvalue()
    encoded = base64.b64encode(compressed).decode("ascii")
    if len(encoded) > AGENT_SNAPSHOT_MAX_COMPRESSED_PAYLOAD_CHARS:
        raise ValueError("compressed agent SKU payload exceeds the storage boundary")
    return encoded


def decode_agent_sku_payload(snapshot: AgentSkuSnapshot) -> AgentSkuSourcePayload:
    frozen = AgentSkuSnapshot.model_validate(snapshot.model_dump(mode="json"))
    try:
        compressed = base64.b64decode(frozen.payload_b64, validate=True)
        decoder = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        raw = decoder.decompress(
            compressed,
            AGENT_SNAPSHOT_MAX_DECOMPRESSED_PAYLOAD_BYTES + 1,
        )
    except (ValueError, binascii.Error, zlib.error) as exc:
        raise ValueError(
            "saved agent SKU payload is not valid compressed JSON"
        ) from exc
    if (
        len(raw) > AGENT_SNAPSHOT_MAX_DECOMPRESSED_PAYLOAD_BYTES
        or not decoder.eof
        or decoder.unconsumed_tail
        or decoder.unused_data
    ):
        raise ValueError("decompressed agent SKU payload exceeds the read boundary")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("saved agent SKU payload is not valid JSON") from exc
    return AgentSkuSourcePayload.model_validate(payload)


__all__ = [
    "AGENT_SNAPSHOT_METHOD_VERSION",
    "AGENT_SNAPSHOT_CANDIDATE_LIMIT",
    "AGENT_SNAPSHOT_PRIORITY_LIMIT",
    "AGENT_SNAPSHOT_RULE_VERSION",
    "AGENT_SNAPSHOT_SKU_PAYLOAD_CODEC",
    "AGENT_SNAPSHOT_SOURCE_VERSION",
    "AgentCandidateAnalysisPayload",
    "AgentCandidateAnalysisRecord",
    "AgentCompetitorProfileCompact",
    "AgentCompetitorProfileReadResult",
    "AgentCompetitorProfileSnapshot",
    "AgentCompetitorRuntimeProjection",
    "AgentEvidenceReceipt",
    "AgentPairIndexItem",
    "AgentSkuIdentity",
    "AgentSkuSourcePayload",
    "AgentSkuSnapshot",
    "CompetitorProfileAgentSnapshotAdapter",
    "decode_agent_sku_payload",
    "encode_agent_sku_payload",
]
