from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_generation import (
    SellpointValueV52GenerationService,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_input_provider import (
    SavedV5SellpointValueV52InputProvider,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer import (
    build_v5_2_profile_input_fingerprint,
    build_v5_2_source_hashes,
    materialize_sellpoint_value_profile_v5_2,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_materializer_schemas import (
    SellpointValueV52MaterializationInput,
    SellpointValueV52VersionRequest,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_repository import (
    SellpointValueV52ReadbackIntegrityError,
    SellpointValueV52Repository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    M04CSourceLineage,
    SourceSellpointFact,
    SourceSellpointReadResult,
    SourceSellpointState,
)
from app.services.core3_real_data.constants import Core3CategoryCode
from app.services.core3_real_data.repositories import Core3RepositoryContext
from tests.core3_real_data.test_sellpoint_value_profile_v5_1_materialization import (
    _materialization_input,
    _request,
    session as _v5_1_session,
)


class FixtureProvider:
    def __init__(self, rows):
        self.rows = rows

    def load_materialization_input(self, request, sku_code):
        value = self.rows[sku_code]
        if isinstance(value, Exception):
            raise value
        return value


class FixtureBaseProvider:
    def __init__(self, source):
        self.source = source
        self.load_calls = []

    def build_version_request(self, **kwargs):
        return _request(
            self.source,
            expected_sku_codes=list(kwargs["expected_sku_codes"]),
        )

    def load_materialization_input(self, request, sku_code):
        self.load_calls.append((request.profile_version, sku_code))
        return self.source


class FixtureSourceSellpointReader:
    def __init__(self, result):
        self.result = result
        self.requests = []

    def read(self, request):
        self.requests.append(request)
        return self.result


@pytest.fixture(name="session")
def session_fixture():
    yield from _v5_1_session.__wrapped__()


def _evidence(record_id: str) -> SellpointValueEvidenceRef:
    return SellpointValueEvidenceRef(
        module_code="M04C",
        record_type="claim_fact",
        record_id=record_id,
        result_hash=f"sha256:{record_id}",
        evidence_ids=[f"ev-{record_id}"],
    )


def _source_sellpoints(
    *,
    raw_claim_text: str = "【核心定位】65英寸Mini LED电视，呈现专业画质。",
    profile_hash: str = "sha256:m04c-profile",
) -> SourceSellpointReadResult:
    return SourceSellpointReadResult(
        status=SourceSellpointState.AVAILABLE,
        lineage=M04CSourceLineage(
            project_id="project-1",
            category_code="TV",
            batch_id="batch-1",
            sku_code="TV-TARGET",
            claim_profile_id="m04c-profile-1",
            taxonomy_version="tv-taxonomy",
            rule_version="tv-rule",
            profile_result_hash=profile_hash,
            evidence_ref=_evidence("m04c-profile-1"),
        ),
        source_sellpoints=[
            SourceSellpointFact(
                source_claim_key="raw:1",
                claim_fact_id="claim-fact-1",
                merged_claim_fact_ids=["claim-fact-1"],
                raw_claim_text=raw_claim_text,
                clean_claim_text=raw_claim_text,
                normalized_claim_code="tv_claim_miniled_display",
                normalized_claim_name_cn="MiniLED 显示/背光",
                claim_dimension="product_experience",
                claim_kind="product_experience",
                claim_subtype="experience",
                param_support_status="supported",
                param_support_level="specific",
                param_support_specificity="specific",
                primary_supporting_param_codes=["mini_led_flag"],
                fact_claim=True,
                confidence=Decimal("0.90"),
                evidence_refs=[_evidence("claim-fact-1")],
            )
        ],
    )


def _v52_input(
    *,
    profile_version: str = "spv-v52-r1",
    source_sellpoints: SourceSellpointReadResult | None = None,
) -> SellpointValueV52MaterializationInput:
    return SellpointValueV52MaterializationInput(
        base=_materialization_input(profile_version=profile_version),
        source_sellpoints=source_sellpoints or _source_sellpoints(),
    )


def _v52_request(
    source: SellpointValueV52MaterializationInput,
    *,
    expected_sku_codes: list[str] | None = None,
) -> SellpointValueV52VersionRequest:
    expected = expected_sku_codes or [source.base.target.sku_code]
    base = _request(source.base, expected_sku_codes=expected)
    hashes = build_v5_2_source_hashes(source)
    return SellpointValueV52VersionRequest(
        base=base,
        source_hashes_by_sku={code: hashes for code in expected},
    )


def _repository(session: Session) -> SellpointValueV52Repository:
    return SellpointValueV52Repository(
        Core3RepositoryContext(
            db=session,
            project_id="project-1",
            category_code=Core3CategoryCode.TV,
        )
    )


def test_v5_2_materializer_persists_source_layers_and_binds_source_hashes() -> None:
    source = _v52_input()

    materialized = materialize_sellpoint_value_profile_v5_2(
        source,
        sellpoint_value_profile_version_id="spv-version-v52",
    )

    profile = materialized.profile
    persisted = materialized.persistence_bundle.profile
    assert profile.layered_sellpoint_analysis.source_sellpoints[0].raw_claim_text == (
        "【核心定位】65英寸Mini LED电视，呈现专业画质。"
    )
    assert profile.layered_sellpoint_analysis.sellpoint_assessments
    assert persisted.method_version == "sellpoint_value_profile_method_v5_2"
    assert persisted.pm_decisions_json["layered_sellpoint_analysis"][
        "result_hash"
    ] == profile.layered_sellpoint_analysis.result_hash
    assert persisted.evidence_summary_json["source_sellpoint_count"] == 1
    changed = source.model_copy(
        update={
            "source_sellpoints": _source_sellpoints(
                profile_hash="sha256:m04c-profile-changed"
            )
        }
    )
    assert build_v5_2_profile_input_fingerprint(source) != (
        build_v5_2_profile_input_fingerprint(changed)
    )


def test_v5_2_production_provider_builds_and_reuses_source_grounded_input() -> None:
    base = _materialization_input(profile_version="spv-v52-provider")
    base_provider = FixtureBaseProvider(base)
    claim_reader = FixtureSourceSellpointReader(_source_sellpoints())
    provider = SavedV5SellpointValueV52InputProvider(
        base_provider=base_provider,
        source_sellpoint_reader=claim_reader,
    )

    request = provider.build_version_request(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        profile_version="spv-v52-provider",
        expected_sku_codes=["TV-TARGET"],
        generated_by="pytest",
    )
    source = provider.load_materialization_input(request, "tv-target")

    assert source.base is base
    assert source.source_sellpoints == _source_sellpoints()
    assert request.source_hashes_by_sku["TV-TARGET"] == (
        build_v5_2_source_hashes(source)
    )
    assert len(base_provider.load_calls) == 1
    assert claim_reader.requests[0].sku_code == "TV-TARGET"


def test_v5_2_generation_is_idempotent_and_preserves_v5_current(
    session: Session,
) -> None:
    source = _v52_input()
    request = _v52_request(source)
    service = SellpointValueV52GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider({"TV-TARGET": source}),
    )

    first = service.generate_draft(request, sku_code="TV-TARGET")
    second = service.generate_draft(request, sku_code="TV-TARGET")

    assert first.profile == second.profile
    assert first.persisted.profile.sku_sellpoint_value_profile_id == (
        second.persisted.profile.sku_sellpoint_value_profile_id
    )
    assert first.persisted.version.release_status == "draft"
    assert first.persisted.version.is_current is False
    assert first.profile.layered_sellpoint_analysis.integrity.unsourced_sellpoint_count == 0
    assert (
        session.scalar(
            select(func.count()).select_from(
                entities.Core3SkuSellpointValueProfile
            )
        )
        == 1
    )
    history = session.get(
        entities.Core3SellpointValueProfileVersion,
        "spv-v5-published",
    )
    assert history is not None
    assert history.release_status == "published"
    assert history.is_current is True
    assert history.result_hash == "v5-history-result"


def test_v5_2_readback_rejects_layered_payload_tampering(
    session: Session,
) -> None:
    source = _v52_input(profile_version="spv-v52-tamper")
    repository = _repository(session)
    SellpointValueV52GenerationService(
        repository=repository,
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_draft(_v52_request(source), sku_code="TV-TARGET")
    row = session.scalar(select(entities.Core3SkuSellpointValueProfile))
    assert row is not None
    row.pm_decisions_json = {
        **row.pm_decisions_json,
        "layered_sellpoint_analysis": {
            **row.pm_decisions_json["layered_sellpoint_analysis"],
            "result_hash": "tampered",
        },
    }
    session.commit()

    with pytest.raises(SellpointValueV52ReadbackIntegrityError):
        repository.get_v5_2_profile(
            batch_id="batch-1",
            profile_version=source.base.profile_version,
            sku_code="TV-TARGET",
        )


def test_v5_2_batch_failure_isolated_to_one_sku(session: Session) -> None:
    source = _v52_input(profile_version="spv-v52-batch")
    request = _v52_request(
        source,
        expected_sku_codes=["TV-BAD", "TV-TARGET"],
    )

    result = SellpointValueV52GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider(
            {
                "TV-BAD": RuntimeError("fixture failure"),
                "TV-TARGET": source,
            }
        ),
    ).generate_many(request)

    assert [(row.sku_code, row.status) for row in result.statuses] == [
        ("TV-BAD", "failed"),
        ("TV-TARGET", "generated"),
    ]
    assert result.version.failed_count == 1
    assert result.version.release_quality_status == "blocked"
    assert (
        session.scalar(
            select(func.count()).select_from(
                entities.Core3SkuSellpointValueProfile
            )
        )
        == 1
    )


def test_v5_2_complete_batch_finishes_readback_validation(
    session: Session,
) -> None:
    source = _v52_input(profile_version="spv-v52-complete-batch")
    result = SellpointValueV52GenerationService(
        repository=_repository(session),
        input_provider=FixtureProvider({"TV-TARGET": source}),
    ).generate_many(_v52_request(source))

    assert result.failed_count == 0
    assert result.version.processing_status == "completed"
    assert result.version.release_quality_status == "ready"
    assert result.version.review_required is False
