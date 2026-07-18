"""Read saved M04C source sellpoints without generating or rewriting claims."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any, Literal, Protocol, Sequence

from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    M04CSourceLineage,
    SourceSellpointFact,
    SourceSellpointReadResult,
    SourceSellpointState,
)
from app.services.core3_real_data.constants import (
    CORE3_M04C_AC_RULE_VERSION,
    CORE3_M04C_AC_TAXONOMY_VERSION,
    CORE3_M04C_TV_RULE_VERSION,
    CORE3_M04C_TV_TAXONOMY_VERSION,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)


_SUPPORT_STATUS_PRIORITY = {
    "supported": 0,
    "partially_supported": 1,
    "not_param_applicable": 2,
    "param_unknown": 3,
    "unsupported": 4,
}


class M04CSourceSellpointIntegrityError(RuntimeError):
    """Raised when saved current M04C facts conflict within one identity."""


class M04CSourceSellpointReadRequest(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)


class M04CSourceSellpointRepository(Protocol):
    project_id: str
    category_code: str

    def read_current_profile(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> entities.Core3SkuClaimFactProfile | None:
        """Return the exact current M04C profile for one SKU."""

    def list_current_facts(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> Sequence[entities.Core3SkuClaimFact]:
        """Return exact current M04C facts in deterministic order."""

    def read_many_current_profiles(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
    ) -> dict[str, entities.Core3SkuClaimFactProfile]:
        """Return current M04C profiles for a bounded SKU set."""

    def list_many_current_facts(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
    ) -> dict[str, list[entities.Core3SkuClaimFact]]:
        """Return current M04C facts for a bounded SKU set."""


class SqlAlchemyM04CSourceSellpointRepository:
    """SQLAlchemy implementation scoped to one project and category."""

    def __init__(
        self,
        db: Session,
        *,
        project_id: str,
        category_code: Literal["TV", "AC"],
    ) -> None:
        self.db = db
        self.project_id = project_id.strip()
        self.category_code = category_code
        if not self.project_id:
            raise ValueError("project_id is required")

    def read_current_profile(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> entities.Core3SkuClaimFactProfile | None:
        taxonomy_version, rule_version = _m04c_versions(self.category_code)
        stmt = (
            select(entities.Core3SkuClaimFactProfile)
            .where(
                entities.Core3SkuClaimFactProfile.project_id == self.project_id,
                entities.Core3SkuClaimFactProfile.category_code
                == self.category_code,
                entities.Core3SkuClaimFactProfile.product_category
                == self.category_code,
                entities.Core3SkuClaimFactProfile.batch_id == batch_id,
                entities.Core3SkuClaimFactProfile.sku_code == sku_code,
                entities.Core3SkuClaimFactProfile.taxonomy_version
                == taxonomy_version,
                entities.Core3SkuClaimFactProfile.rule_version == rule_version,
                entities.Core3SkuClaimFactProfile.is_current.is_(True),
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list_current_facts(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> Sequence[entities.Core3SkuClaimFact]:
        taxonomy_version, rule_version = _m04c_versions(self.category_code)
        stmt = (
            select(entities.Core3SkuClaimFact)
            .where(
                entities.Core3SkuClaimFact.project_id == self.project_id,
                entities.Core3SkuClaimFact.category_code == self.category_code,
                entities.Core3SkuClaimFact.product_category == self.category_code,
                entities.Core3SkuClaimFact.batch_id == batch_id,
                entities.Core3SkuClaimFact.sku_code == sku_code,
                entities.Core3SkuClaimFact.taxonomy_version == taxonomy_version,
                entities.Core3SkuClaimFact.rule_version == rule_version,
                entities.Core3SkuClaimFact.is_current.is_(True),
            )
            .order_by(
                entities.Core3SkuClaimFact.claim_seq.asc().nulls_last(),
                entities.Core3SkuClaimFact.source_claim_key,
                entities.Core3SkuClaimFact.claim_code,
                entities.Core3SkuClaimFact.claim_fact_id,
            )
        )
        return list(self.db.execute(stmt).scalars())

    def read_many_current_profiles(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
    ) -> dict[str, entities.Core3SkuClaimFactProfile]:
        codes = sorted(set(sku_codes))
        if not codes:
            return {}
        taxonomy_version, rule_version = _m04c_versions(self.category_code)
        stmt = (
            select(entities.Core3SkuClaimFactProfile)
            .where(
                entities.Core3SkuClaimFactProfile.project_id == self.project_id,
                entities.Core3SkuClaimFactProfile.category_code
                == self.category_code,
                entities.Core3SkuClaimFactProfile.product_category
                == self.category_code,
                entities.Core3SkuClaimFactProfile.batch_id == batch_id,
                entities.Core3SkuClaimFactProfile.sku_code.in_(codes),
                entities.Core3SkuClaimFactProfile.taxonomy_version
                == taxonomy_version,
                entities.Core3SkuClaimFactProfile.rule_version == rule_version,
                entities.Core3SkuClaimFactProfile.is_current.is_(True),
            )
            .order_by(entities.Core3SkuClaimFactProfile.sku_code)
        )
        rows = list(self.db.execute(stmt).scalars())
        if len({row.sku_code for row in rows}) != len(rows):
            raise M04CSourceSellpointIntegrityError(
                "multiple current M04C profiles found for one SKU"
            )
        return {str(row.sku_code): row for row in rows}

    def list_many_current_facts(
        self,
        *,
        batch_id: str,
        sku_codes: Sequence[str],
    ) -> dict[str, list[entities.Core3SkuClaimFact]]:
        codes = sorted(set(sku_codes))
        if not codes:
            return {}
        taxonomy_version, rule_version = _m04c_versions(self.category_code)
        stmt = (
            select(entities.Core3SkuClaimFact)
            .where(
                entities.Core3SkuClaimFact.project_id == self.project_id,
                entities.Core3SkuClaimFact.category_code == self.category_code,
                entities.Core3SkuClaimFact.product_category
                == self.category_code,
                entities.Core3SkuClaimFact.batch_id == batch_id,
                entities.Core3SkuClaimFact.sku_code.in_(codes),
                entities.Core3SkuClaimFact.taxonomy_version
                == taxonomy_version,
                entities.Core3SkuClaimFact.rule_version == rule_version,
                entities.Core3SkuClaimFact.is_current.is_(True),
            )
            .order_by(
                entities.Core3SkuClaimFact.sku_code,
                entities.Core3SkuClaimFact.claim_seq.asc().nulls_last(),
                entities.Core3SkuClaimFact.source_claim_key,
                entities.Core3SkuClaimFact.claim_code,
                entities.Core3SkuClaimFact.claim_fact_id,
            )
        )
        grouped: dict[str, list[entities.Core3SkuClaimFact]] = defaultdict(list)
        for row in self.db.execute(stmt).scalars():
            grouped[str(row.sku_code)].append(row)
        return dict(grouped)


class M04CSourceSellpointReader:
    """Project source-grounded M04C facts into the SPV V5.2 contract."""

    def __init__(self, repository: M04CSourceSellpointRepository) -> None:
        self.repository = repository

    def read(
        self,
        request: M04CSourceSellpointReadRequest,
    ) -> SourceSellpointReadResult:
        request = M04CSourceSellpointReadRequest.model_validate(
            request.model_dump(mode="python")
        )
        repository_category = _enum_text(self.repository.category_code)
        if request.project_id != self.repository.project_id:
            raise ValueError("M04C reader project does not match repository")
        if request.category_code != repository_category:
            raise ValueError("M04C reader category does not match repository")

        sku_code = request.sku_code.strip().upper()
        profile = self.repository.read_current_profile(
            batch_id=request.batch_id,
            sku_code=sku_code,
        )
        facts = (
            self.repository.list_current_facts(
                batch_id=request.batch_id,
                sku_code=sku_code,
            )
            if profile is not None
            else []
        )
        return _build_read_result(profile, facts)

    def read_many(
        self,
        requests: Sequence[M04CSourceSellpointReadRequest],
    ) -> dict[str, SourceSellpointReadResult]:
        normalized = [
            M04CSourceSellpointReadRequest.model_validate(
                request.model_dump(mode="python")
            )
            for request in requests
        ]
        if not normalized:
            return {}
        batch_ids = {request.batch_id for request in normalized}
        if len(batch_ids) != 1:
            raise ValueError("M04C batch read requires one batch")
        for request in normalized:
            if (
                request.project_id != self.repository.project_id
                or request.category_code
                != _enum_text(self.repository.category_code)
            ):
                raise ValueError("M04C batch read scope does not match repository")
        sku_codes = sorted(
            {request.sku_code.strip().upper() for request in normalized}
        )
        profile_reader = getattr(
            self.repository,
            "read_many_current_profiles",
            None,
        )
        fact_reader = getattr(
            self.repository,
            "list_many_current_facts",
            None,
        )
        if profile_reader is None or fact_reader is None:
            return {
                request.sku_code.strip().upper(): self.read(request)
                for request in normalized
            }
        batch_id = normalized[0].batch_id
        profiles = profile_reader(batch_id=batch_id, sku_codes=sku_codes)
        facts = fact_reader(batch_id=batch_id, sku_codes=sku_codes)
        return {
            sku_code: _build_read_result(
                profiles.get(sku_code),
                facts.get(sku_code, []),
            )
            for sku_code in sku_codes
        }


def _build_read_result(
    profile: entities.Core3SkuClaimFactProfile | None,
    facts: Sequence[entities.Core3SkuClaimFact],
) -> SourceSellpointReadResult:
    if profile is None:
        return SourceSellpointReadResult(
            status=SourceSellpointState.NO_SOURCE_SELLPOINT,
            limitations=["m04c_claim_profile_unavailable"],
        )

    lineage = _lineage(profile)
    source_sellpoints, discarded, limitations = _project_facts(facts)
    if not source_sellpoints:
        return SourceSellpointReadResult(
            status=SourceSellpointState.NO_SOURCE_SELLPOINT,
            lineage=lineage,
            discarded_claim_fact_ids=discarded,
            limitations=sorted(
                {*limitations, "m04c_source_sellpoint_unavailable"}
            ),
        )
    return SourceSellpointReadResult(
        status=SourceSellpointState.AVAILABLE,
        lineage=lineage,
        source_sellpoints=source_sellpoints,
        discarded_claim_fact_ids=discarded,
        limitations=limitations,
    )


def _project_facts(
    rows: Sequence[entities.Core3SkuClaimFact],
) -> tuple[list[SourceSellpointFact], list[str], list[str]]:
    groups: dict[
        tuple[str, str],
        list[entities.Core3SkuClaimFact],
    ] = defaultdict(list)
    discarded: set[str] = set()
    limitations: set[str] = set()
    for row in rows:
        raw = str(row.raw_claim_text or "").strip()
        source_key = str(row.source_claim_key or "").strip()
        claim_code = str(row.canonical_claim_code or row.claim_code or "").strip()
        if not raw or not source_key or not claim_code:
            discarded.add(str(row.claim_fact_id))
            limitations.add("m04c_fact_missing_source_identity")
            continue
        groups[(source_key, claim_code)].append(row)

    projected = [
        _merge_fact_group(identity, grouped)
        for identity, grouped in sorted(groups.items())
    ]
    return projected, sorted(discarded), sorted(limitations)


def _merge_fact_group(
    identity: tuple[str, str],
    rows: Sequence[entities.Core3SkuClaimFact],
) -> SourceSellpointFact:
    raw_texts = {str(row.raw_claim_text or "").strip() for row in rows}
    if len(raw_texts) != 1:
        raise M04CSourceSellpointIntegrityError(
            "M04C source claim text conflicts within one source/claim identity"
        )
    normalized_names = {
        str(row.canonical_claim_name or row.claim_name or "").strip()
        for row in rows
    }
    normalized_names.discard("")
    if len(normalized_names) != 1:
        raise M04CSourceSellpointIntegrityError(
            "M04C normalized claim name conflicts within one source/claim identity"
        )
    ranked = sorted(
        rows,
        key=lambda row: (
            _SUPPORT_STATUS_PRIORITY.get(str(row.param_support_status), 99),
            -float(row.confidence or 0),
            str(row.claim_fact_id),
        ),
    )
    canonical = ranked[0]
    evidence_refs = sorted(
        (_fact_evidence(row) for row in rows),
        key=lambda ref: (ref.record_id, ref.result_hash),
    )
    return SourceSellpointFact(
        source_claim_key=identity[0],
        claim_fact_id=str(canonical.claim_fact_id),
        merged_claim_fact_ids=sorted(
            {str(row.claim_fact_id) for row in rows}
        ),
        raw_claim_text=next(iter(raw_texts)),
        clean_claim_text=_first_text(row.clean_claim_text for row in ranked),
        exact_quote_cn=None,
        normalized_claim_code=identity[1],
        normalized_claim_name_cn=next(iter(normalized_names)),
        claim_dimension=str(canonical.claim_dimension),
        claim_kind=str(canonical.claim_kind),
        claim_subtype=str(canonical.claim_subtype),
        param_support_status=str(canonical.param_support_status),
        param_support_level=str(canonical.param_support_level),
        param_support_specificity=str(canonical.param_support_specificity),
        primary_supporting_param_codes=_merged_codes(
            rows,
            "primary_supporting_param_codes",
        ),
        supporting_param_codes=_merged_codes(rows, "supporting_param_codes"),
        generic_support_param_codes=_merged_codes(
            rows,
            "generic_support_param_codes",
        ),
        service_separate=any(bool(row.service_separate_flag) for row in rows),
        fact_claim=any(bool(row.fact_claim_flag) for row in rows),
        confidence=Decimal(str(max(float(row.confidence or 0) for row in rows))),
        evidence_refs=evidence_refs,
    )


def _lineage(
    profile: entities.Core3SkuClaimFactProfile,
) -> M04CSourceLineage:
    evidence_ref = SellpointValueEvidenceRef(
        module_code="M04C",
        record_type="sku_claim_fact_profile",
        record_id=str(profile.claim_profile_id),
        result_hash=str(profile.profile_hash),
        batch_id=str(profile.batch_id),
        evidence_ids=sorted(
            {
                str(value).strip()
                for value in (profile.evidence_ids or [])
                if str(value).strip()
            }
        ),
        confidence=float(profile.confidence),
    )
    return M04CSourceLineage(
        project_id=str(profile.project_id),
        category_code=_enum_text(profile.category_code),
        batch_id=str(profile.batch_id),
        sku_code=str(profile.sku_code),
        claim_profile_id=str(profile.claim_profile_id),
        taxonomy_version=str(profile.taxonomy_version),
        rule_version=str(profile.rule_version),
        profile_result_hash=str(profile.profile_hash),
        evidence_ref=evidence_ref,
    )


def _fact_evidence(
    row: entities.Core3SkuClaimFact,
) -> SellpointValueEvidenceRef:
    source_key = str(row.source_claim_key or "")
    raw_row_ids = (
        [source_key.removeprefix("raw:")]
        if source_key.startswith("raw:") and source_key.removeprefix("raw:")
        else []
    )
    return SellpointValueEvidenceRef(
        module_code="M04C",
        record_type="sku_claim_fact",
        record_id=str(row.claim_fact_id),
        result_hash=str(row.fact_hash),
        batch_id=str(row.batch_id),
        evidence_ids=sorted(
            {
                str(value).strip()
                for value in (row.evidence_ids or [])
                if str(value).strip()
            }
        ),
        raw_row_ids=raw_row_ids,
        confidence=float(row.confidence),
    )


def _merged_codes(
    rows: Sequence[entities.Core3SkuClaimFact],
    attribute: str,
) -> list[str]:
    return sorted(
        {
            str(value).strip()
            for row in rows
            for value in (getattr(row, attribute, None) or [])
            if str(value).strip()
        }
    )


def _first_text(values: Sequence[str | None] | Any) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None


def _m04c_versions(category_code: str) -> tuple[str, str]:
    if _enum_text(category_code) == "AC":
        return CORE3_M04C_AC_TAXONOMY_VERSION, CORE3_M04C_AC_RULE_VERSION
    return CORE3_M04C_TV_TAXONOMY_VERSION, CORE3_M04C_TV_RULE_VERSION


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value)).strip().upper()


__all__ = [
    "M04CSourceSellpointIntegrityError",
    "M04CSourceSellpointReadRequest",
    "M04CSourceSellpointReader",
    "SqlAlchemyM04CSourceSellpointRepository",
]
