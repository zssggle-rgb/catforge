"""G36 single-SKU and resumable batch generation for V1.1 draft DTOs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import Field, model_validator

from app.services.core3_real_data.analyst.competitor_profile_v1_1_gate_evaluation import (
    PairGateEvaluation,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_materializer import (
    CompetitorProfileV11Materializer,
    HardExcludedPairMaterializationInput,
    MaterializedCompetitorProfileV11,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisAssembly,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_repositories import (
    CompetitorProfileV11Repository,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_schemas import (
    CompetitorProfileAnalysisDTO,
    CompetitorProfileV11BaseModel,
    ProfileVersionAnalysisContext,
    VersionSkuAnalysisSnapshot,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorSelectionResult,
)
from app.services.core3_real_data.hash_utils import stable_hash


class CompetitorProfileV11ImmutableDraftError(RuntimeError):
    """Raised when a different result tries to replace an existing V1.1 draft."""


class CompetitorProfileV11DraftStore(Protocol):
    def get_draft(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
    ) -> CompetitorProfileAnalysisDTO | None: ...

    def write_draft(
        self,
        dto: CompetitorProfileAnalysisDTO,
    ) -> CompetitorProfileAnalysisDTO: ...


class InMemoryCompetitorProfileV11DraftStore:
    """Test/local store with the same immutable idempotency boundary as G31."""

    def __init__(self) -> None:
        self._drafts: dict[tuple[str, str], CompetitorProfileAnalysisDTO] = {}

    def get_draft(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
    ) -> CompetitorProfileAnalysisDTO | None:
        row = self._drafts.get(
            (competitor_profile_version_id, target_sku_code.strip().upper())
        )
        return (
            CompetitorProfileAnalysisDTO.model_validate(row.model_dump(mode="json"))
            if row is not None
            else None
        )

    def write_draft(
        self,
        dto: CompetitorProfileAnalysisDTO,
    ) -> CompetitorProfileAnalysisDTO:
        dto = CompetitorProfileAnalysisDTO.model_validate(dto.model_dump(mode="json"))
        key = (
            dto.profile_version.competitor_profile_version_id,
            dto.sku_summary.target_sku_code,
        )
        existing = self._drafts.get(key)
        if existing is not None and existing != dto:
            raise CompetitorProfileV11ImmutableDraftError(
                "V1.1 draft already exists with a different immutable result"
            )
        if existing is None:
            self._drafts[key] = dto
        return CompetitorProfileAnalysisDTO.model_validate(
            self._drafts[key].model_dump(mode="json")
        )


class RepositoryCompetitorProfileV11DraftStore:
    """Transactional G31 adapter; it performs no analysis or state switching."""

    def __init__(self, repository: CompetitorProfileV11Repository) -> None:
        self.repository = repository

    def get_draft(
        self,
        *,
        competitor_profile_version_id: str,
        target_sku_code: str,
    ) -> CompetitorProfileAnalysisDTO | None:
        try:
            result = self.repository.get_profile(
                competitor_profile_version_id=competitor_profile_version_id,
                target_sku_code=target_sku_code,
                read_mode="full",
                preview=True,
            )
            self.repository.db.commit()
        except Exception:
            self.repository.db.rollback()
            raise
        return result.full if result is not None else None

    def write_draft(
        self,
        dto: CompetitorProfileAnalysisDTO,
    ) -> CompetitorProfileAnalysisDTO:
        try:
            result = self.repository.write_draft(dto)
            self.repository.db.commit()
        except Exception:
            self.repository.db.rollback()
            raise
        return result


@dataclass(frozen=True)
class CompetitorProfileV11GenerationWorkItem:
    profile_version: ProfileVersionAnalysisContext
    target_snapshot: VersionSkuAnalysisSnapshot
    candidate_snapshots: Sequence[VersionSkuAnalysisSnapshot]
    pair_assemblies: Sequence[PairAnalysisAssembly]
    gate_evaluations: Sequence[PairGateEvaluation]
    selection_result: CompetitorSelectionResult
    hard_excluded_inputs: Sequence[HardExcludedPairMaterializationInput] = ()

    @property
    def target_sku_code(self) -> str:
        return self.selection_result.target_sku_code


class CompetitorProfileV11SkuGenerationStatus(CompetitorProfileV11BaseModel):
    target_sku_code: str = Field(min_length=1)
    status: Literal["generated", "reused", "skipped", "failed"]
    profile_result_hash: str | None = None
    error_code: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "CompetitorProfileV11SkuGenerationStatus":
        succeeded = self.status in {"generated", "reused", "skipped"}
        if succeeded != (self.profile_result_hash is not None):
            raise ValueError("successful generation status requires a result hash")
        if (self.status == "failed") != bool(self.error_code and self.error_message):
            raise ValueError("failed generation status requires a safe error")
        return self


class CompetitorProfileV11GenerationCheckpoint(CompetitorProfileV11BaseModel):
    completed_hashes: dict[str, str] = Field(default_factory=dict)
    completed_input_fingerprints: dict[str, str] = Field(default_factory=dict)
    failure_codes: dict[str, str] = Field(default_factory=dict)
    last_target_sku_code: str | None = None
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "CompetitorProfileV11GenerationCheckpoint":
        if set(self.completed_hashes) & set(self.failure_codes):
            raise ValueError("checkpoint successes and failures must be disjoint")
        if set(self.completed_input_fingerprints) != set(self.completed_hashes):
            raise ValueError(
                "checkpoint input fingerprints must exactly cover completed SKUs"
            )
        expected = stable_hash(
            {
                "completed_hashes": dict(sorted(self.completed_hashes.items())),
                "completed_input_fingerprints": dict(
                    sorted(self.completed_input_fingerprints.items())
                ),
                "failure_codes": dict(sorted(self.failure_codes.items())),
                "last_target_sku_code": self.last_target_sku_code,
            },
            version="competitor_profile_v1_1_generation_checkpoint_v1",
        )
        if self.result_hash != expected:
            raise ValueError("generation checkpoint hash does not close")
        return self


class CompetitorProfileV11BatchGenerationResult(CompetitorProfileV11BaseModel):
    requested_count: int = Field(ge=0)
    succeeded_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    statuses: list[CompetitorProfileV11SkuGenerationStatus]
    checkpoint: CompetitorProfileV11GenerationCheckpoint
    result_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "CompetitorProfileV11BatchGenerationResult":
        if self.requested_count != len(self.statuses):
            raise ValueError("batch requested count must match statuses")
        if self.statuses != sorted(
            self.statuses,
            key=lambda row: row.target_sku_code,
        ):
            raise ValueError("batch statuses must be SKU ordered")
        actual_failed = sum(row.status == "failed" for row in self.statuses)
        actual_skipped = sum(row.status == "skipped" for row in self.statuses)
        if self.failed_count != actual_failed or self.skipped_count != actual_skipped:
            raise ValueError("batch failed/skipped counts must match statuses")
        if self.succeeded_count != self.requested_count - self.failed_count:
            raise ValueError("batch success count must include generated/reused/skipped")
        expected_hash = stable_hash(
            {
                "statuses": [row.model_dump(mode="json") for row in self.statuses],
                "checkpoint_result_hash": self.checkpoint.result_hash,
            },
            version="competitor_profile_v1_1_batch_generation_result_v1",
        )
        if self.result_hash != expected_hash:
            raise ValueError("batch generation result hash does not close")
        return self


class CompetitorProfileV11GenerationService:
    """Persist already-computed V1.1 DTOs with resumable per-SKU isolation."""

    def __init__(
        self,
        *,
        draft_store: CompetitorProfileV11DraftStore,
        materializer: CompetitorProfileV11Materializer | None = None,
    ) -> None:
        self.draft_store = draft_store
        self.materializer = materializer or CompetitorProfileV11Materializer()

    def generate_draft(
        self,
        item: CompetitorProfileV11GenerationWorkItem,
    ) -> tuple[Literal["generated", "reused"], MaterializedCompetitorProfileV11]:
        materialized = self._materialize(item)
        version_id = materialized.dto.profile_version.competitor_profile_version_id
        existing = self.draft_store.get_draft(
            competitor_profile_version_id=version_id,
            target_sku_code=item.target_sku_code,
        )
        if existing is not None:
            if existing != materialized.dto:
                raise CompetitorProfileV11ImmutableDraftError(
                    "V1.1 draft result differs; create a new profile version"
                )
            return "reused", materialized
        persisted = self.draft_store.write_draft(materialized.dto)
        if persisted != materialized.dto:
            raise CompetitorProfileV11ImmutableDraftError(
                "V1.1 draft readback differs from the generated DTO"
            )
        return "generated", materialized

    def batch_generate(
        self,
        items: Sequence[CompetitorProfileV11GenerationWorkItem],
        *,
        checkpoint: CompetitorProfileV11GenerationCheckpoint | None = None,
        resume: bool = True,
    ) -> CompetitorProfileV11BatchGenerationResult:
        ordered = sorted(items, key=lambda row: row.target_sku_code)
        codes = [row.target_sku_code for row in ordered]
        if len(codes) != len(set(codes)):
            raise ValueError("batch target SKU codes must be unique")
        completed = dict(checkpoint.completed_hashes) if checkpoint else {}
        completed_inputs = (
            dict(checkpoint.completed_input_fingerprints) if checkpoint else {}
        )
        failures = dict(checkpoint.failure_codes) if checkpoint else {}
        statuses: list[CompetitorProfileV11SkuGenerationStatus] = []
        last_target = checkpoint.last_target_sku_code if checkpoint else None
        for item in ordered:
            code = item.target_sku_code
            last_target = code
            current_input = _work_item_fingerprint(item)
            if (
                resume
                and code in completed
                and completed_inputs.get(code) == current_input
            ):
                existing = self.draft_store.get_draft(
                    competitor_profile_version_id=(
                        item.profile_version.competitor_profile_version_id
                    ),
                    target_sku_code=code,
                )
                if existing is not None and existing.profile_result_hash == completed[code]:
                    statuses.append(
                        CompetitorProfileV11SkuGenerationStatus(
                            target_sku_code=code,
                            status="skipped",
                            profile_result_hash=completed[code],
                        )
                    )
                    continue
            try:
                status, materialized = self.generate_draft(item)
            except Exception as exc:  # noqa: BLE001 - per-SKU isolation boundary
                completed.pop(code, None)
                completed_inputs.pop(code, None)
                failures[code] = type(exc).__name__
                statuses.append(
                    CompetitorProfileV11SkuGenerationStatus(
                        target_sku_code=code,
                        status="failed",
                        error_code=type(exc).__name__,
                        error_message=(
                            "SKU V1.1 competitor profile generation failed; "
                            "inspect the isolated generation log."
                        ),
                    )
                )
                continue
            failures.pop(code, None)
            completed[code] = materialized.result_hash
            completed_inputs[code] = current_input
            statuses.append(
                CompetitorProfileV11SkuGenerationStatus(
                    target_sku_code=code,
                    status=status,
                    profile_result_hash=materialized.result_hash,
                )
            )
        new_checkpoint = _checkpoint(
            completed,
            completed_inputs,
            failures,
            last_target,
        )
        result_payload = {
            "statuses": [row.model_dump(mode="json") for row in statuses],
            "checkpoint_result_hash": new_checkpoint.result_hash,
        }
        return CompetitorProfileV11BatchGenerationResult(
            requested_count=len(statuses),
            succeeded_count=sum(row.status != "failed" for row in statuses),
            failed_count=sum(row.status == "failed" for row in statuses),
            skipped_count=sum(row.status == "skipped" for row in statuses),
            statuses=statuses,
            checkpoint=new_checkpoint,
            result_hash=stable_hash(
                result_payload,
                version="competitor_profile_v1_1_batch_generation_result_v1",
            ),
        )

    def _materialize(
        self,
        item: CompetitorProfileV11GenerationWorkItem,
    ) -> MaterializedCompetitorProfileV11:
        return self.materializer.materialize(
            profile_version=item.profile_version,
            target_snapshot=item.target_snapshot,
            candidate_snapshots=item.candidate_snapshots,
            pair_assemblies=item.pair_assemblies,
            gate_evaluations=item.gate_evaluations,
            selection_result=item.selection_result,
            hard_excluded_inputs=item.hard_excluded_inputs,
        )


def _checkpoint(
    completed: dict[str, str],
    completed_inputs: dict[str, str],
    failures: dict[str, str],
    last_target: str | None,
) -> CompetitorProfileV11GenerationCheckpoint:
    payload = {
        "completed_hashes": dict(sorted(completed.items())),
        "completed_input_fingerprints": dict(sorted(completed_inputs.items())),
        "failure_codes": dict(sorted(failures.items())),
        "last_target_sku_code": last_target,
    }
    return CompetitorProfileV11GenerationCheckpoint(
        **payload,
        result_hash=stable_hash(
            payload,
            version="competitor_profile_v1_1_generation_checkpoint_v1",
        ),
    )


def _work_item_fingerprint(
    item: CompetitorProfileV11GenerationWorkItem,
) -> str:
    return stable_hash(
        {
            "profile_version": item.profile_version.model_dump(mode="json"),
            "target_snapshot_hash": item.target_snapshot.result_hash,
            "candidate_snapshot_hashes": {
                row.identity_market.sku_code: row.result_hash
                for row in sorted(
                    item.candidate_snapshots,
                    key=lambda row: row.identity_market.sku_code,
                )
            },
            "assembly_hashes": {
                row.candidate_sku_code: row.result_hash
                for row in sorted(
                    item.pair_assemblies,
                    key=lambda row: row.candidate_sku_code,
                )
            },
            "gate_hashes": {
                row.candidate_sku_code or "": row.result_hash
                for row in sorted(
                    item.gate_evaluations,
                    key=lambda row: row.candidate_sku_code or "",
                )
            },
            "selection_result_hash": item.selection_result.result_hash,
            "hard_excluded_inputs": [
                row.model_dump(mode="json")
                for row in sorted(
                    item.hard_excluded_inputs,
                    key=lambda row: row.candidate_sku_code,
                )
            ],
        },
        version="competitor_profile_v1_1_generation_work_item_v1",
    )


__all__ = [
    "CompetitorProfileV11BatchGenerationResult",
    "CompetitorProfileV11DraftStore",
    "CompetitorProfileV11GenerationCheckpoint",
    "CompetitorProfileV11GenerationService",
    "CompetitorProfileV11GenerationWorkItem",
    "CompetitorProfileV11ImmutableDraftError",
    "CompetitorProfileV11SkuGenerationStatus",
    "InMemoryCompetitorProfileV11DraftStore",
    "RepositoryCompetitorProfileV11DraftStore",
]
