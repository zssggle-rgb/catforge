from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueEvidenceRef,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_claim_reader import (
    M04CSourceSellpointIntegrityError,
    M04CSourceSellpointReadRequest,
    M04CSourceSellpointReader,
    SqlAlchemyM04CSourceSellpointRepository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_2_schemas import (
    LayerIntegritySummary,
    SourceSellpointFact,
    SourceSellpointState,
)


PROJECT_ID = "project-1"
BATCH_ID = "batch-1"
SKU_CODE = "TV00029112"
RAW_GAME_CLAIM = (
    "【其他卖点】4K 170Hz原生高刷+300Hz动态刷新，"
    "四路满血HDMI 2.1支持48Gbps传输，游戏影音双丝滑"
)


def _profile(**overrides: Any) -> SimpleNamespace:
    values = {
        "claim_profile_id": "claim-profile-1",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "sku_code": SKU_CODE,
        "taxonomy_version": "tv_claim_taxonomy_manual_v0.1",
        "rule_version": "m04c_tv_claim_fact_profile_v0.2",
        "profile_hash": "sha256:profile",
        "evidence_ids": ["ev-profile"],
        "confidence": Decimal("0.91"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _fact(
    fact_id: str,
    *,
    support_status: str = "supported",
    raw_claim_text: str | None = RAW_GAME_CLAIM,
    claim_code: str = "tv_claim_gaming_low_latency",
    claim_name: str = "游戏/低延迟",
    confidence: str = "0.90",
    sku_code: str = SKU_CODE,
) -> SimpleNamespace:
    return SimpleNamespace(
        claim_fact_id=fact_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=sku_code,
        source_claim_key="raw:88",
        raw_claim_text=raw_claim_text,
        clean_claim_text=raw_claim_text,
        claim_code=claim_code,
        claim_name=claim_name,
        canonical_claim_code=None,
        canonical_claim_name=None,
        claim_dimension="motion_gaming",
        claim_kind="product_experience",
        claim_subtype="gaming",
        param_support_status=support_status,
        param_support_level="specific",
        param_support_specificity="specific",
        primary_supporting_param_codes=["refresh_rate"],
        supporting_param_codes=["hdmi_21", "refresh_rate"],
        generic_support_param_codes=[],
        service_separate_flag=False,
        fact_claim_flag=True,
        evidence_ids=[f"ev-{fact_id}"],
        confidence=Decimal(confidence),
        fact_hash=f"sha256:{fact_id}",
    )


class FakeM04CRepository:
    project_id = PROJECT_ID
    category_code = "TV"

    def __init__(
        self,
        *,
        profile: SimpleNamespace | None = None,
        facts: list[SimpleNamespace] | None = None,
    ) -> None:
        self.profile = profile
        self.facts = facts or []
        self.calls: list[tuple[str, str, str]] = []

    def read_current_profile(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> SimpleNamespace | None:
        self.calls.append(("profile", batch_id, sku_code))
        return self.profile

    def list_current_facts(
        self,
        *,
        batch_id: str,
        sku_code: str,
    ) -> list[SimpleNamespace]:
        self.calls.append(("facts", batch_id, sku_code))
        return self.facts


class FakeBatchM04CRepository(FakeM04CRepository):
    def __init__(
        self,
        *,
        profiles: dict[str, SimpleNamespace],
        facts_by_sku: dict[str, list[SimpleNamespace]],
    ) -> None:
        super().__init__()
        self.profiles = profiles
        self.facts_by_sku = facts_by_sku

    def read_many_current_profiles(
        self,
        *,
        batch_id: str,
        sku_codes: list[str],
    ) -> dict[str, SimpleNamespace]:
        self.calls.append(("profiles_many", batch_id, ",".join(sku_codes)))
        return {
            code: self.profiles[code]
            for code in sku_codes
            if code in self.profiles
        }

    def list_many_current_facts(
        self,
        *,
        batch_id: str,
        sku_codes: list[str],
    ) -> dict[str, list[SimpleNamespace]]:
        self.calls.append(("facts_many", batch_id, ",".join(sku_codes)))
        return {
            code: self.facts_by_sku.get(code, [])
            for code in sku_codes
        }


def _request() -> M04CSourceSellpointReadRequest:
    return M04CSourceSellpointReadRequest(
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=SKU_CODE.lower(),
    )


def test_source_sellpoint_exact_quote_must_come_from_original_claim() -> None:
    evidence = SellpointValueEvidenceRef(
        module_code="M04C",
        record_type="sku_claim_fact",
        record_id="fact-1",
        result_hash="sha256:fact-1",
    )
    payload = {
        "source_claim_key": "raw:88",
        "claim_fact_id": "fact-1",
        "merged_claim_fact_ids": ["fact-1"],
        "raw_claim_text": RAW_GAME_CLAIM,
        "exact_quote_cn": "游戏与运动流畅",
        "normalized_claim_code": "tv_claim_gaming_low_latency",
        "normalized_claim_name_cn": "游戏/低延迟",
        "claim_dimension": "motion_gaming",
        "claim_kind": "product_experience",
        "claim_subtype": "gaming",
        "param_support_status": "supported",
        "param_support_level": "specific",
        "param_support_specificity": "specific",
        "confidence": Decimal("0.9"),
        "evidence_refs": [evidence],
    }

    with pytest.raises(ValidationError, match="continuous source substring"):
        SourceSellpointFact.model_validate(payload)

    payload["exact_quote_cn"] = "游戏影音双丝滑"
    fact = SourceSellpointFact.model_validate(payload)
    assert fact.exact_quote_cn == "游戏影音双丝滑"


def test_reader_returns_honest_no_source_state_without_profile() -> None:
    repository = FakeM04CRepository()
    result = M04CSourceSellpointReader(repository).read(_request())

    assert result.status == SourceSellpointState.NO_SOURCE_SELLPOINT
    assert result.source_sellpoints == []
    assert result.limitations == ["m04c_claim_profile_unavailable"]
    assert repository.calls == [("profile", BATCH_ID, SKU_CODE)]


def test_reader_projects_and_deduplicates_saved_source_claims() -> None:
    facts = [
        _fact("fact-unknown", support_status="param_unknown", confidence="0.70"),
        _fact("fact-supported", support_status="supported", confidence="0.95"),
    ]
    repository = FakeM04CRepository(profile=_profile(), facts=facts)
    result = M04CSourceSellpointReader(repository).read(_request())

    assert result.status == SourceSellpointState.AVAILABLE
    assert result.lineage is not None
    assert result.lineage.profile_result_hash == "sha256:profile"
    assert len(result.source_sellpoints) == 1
    sellpoint = result.source_sellpoints[0]
    assert sellpoint.raw_claim_text == RAW_GAME_CLAIM
    assert sellpoint.normalized_claim_name_cn == "游戏/低延迟"
    assert sellpoint.claim_fact_id == "fact-supported"
    assert sellpoint.merged_claim_fact_ids == [
        "fact-supported",
        "fact-unknown",
    ]
    assert sellpoint.supporting_param_codes == ["hdmi_21", "refresh_rate"]
    assert [ref.record_id for ref in sellpoint.evidence_refs] == [
        "fact-supported",
        "fact-unknown",
    ]
    assert sellpoint.exact_quote_cn is None
    assert repository.calls == [
        ("profile", BATCH_ID, SKU_CODE),
        ("facts", BATCH_ID, SKU_CODE),
    ]


def test_reader_discards_fact_without_original_claim_but_keeps_lineage() -> None:
    repository = FakeM04CRepository(
        profile=_profile(),
        facts=[_fact("fact-missing-source", raw_claim_text=None)],
    )
    result = M04CSourceSellpointReader(repository).read(_request())

    assert result.status == SourceSellpointState.NO_SOURCE_SELLPOINT
    assert result.lineage is not None
    assert result.discarded_claim_fact_ids == ["fact-missing-source"]
    assert result.limitations == [
        "m04c_fact_missing_source_identity",
        "m04c_source_sellpoint_unavailable",
    ]


def test_reader_rejects_conflicting_source_text_for_one_claim_identity() -> None:
    repository = FakeM04CRepository(
        profile=_profile(),
        facts=[
            _fact("fact-1"),
            _fact("fact-2", raw_claim_text="另一条不一致的原始卖点"),
        ],
    )

    with pytest.raises(M04CSourceSellpointIntegrityError, match="text conflicts"):
        M04CSourceSellpointReader(repository).read(_request())


def test_reader_rejects_cross_project_or_category_requests() -> None:
    repository = FakeM04CRepository(profile=_profile())
    reader = M04CSourceSellpointReader(repository)

    with pytest.raises(ValueError, match="project"):
        reader.read(
            M04CSourceSellpointReadRequest(
                project_id="other-project",
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code=SKU_CODE,
            )
        )
    with pytest.raises(ValueError, match="category"):
        reader.read(
            M04CSourceSellpointReadRequest(
                project_id=PROJECT_ID,
                category_code="AC",
                batch_id=BATCH_ID,
                sku_code=SKU_CODE,
            )
        )


def test_reader_batches_bounded_skus_in_two_repository_queries() -> None:
    second_sku = "TV-C02"
    repository = FakeBatchM04CRepository(
        profiles={
            SKU_CODE: _profile(),
            second_sku: _profile(sku_code=second_sku),
        },
        facts_by_sku={
            SKU_CODE: [_fact("fact-target")],
            second_sku: [
                _fact(
                    "fact-c02",
                    sku_code=second_sku,
                    claim_code="tv_claim_qd_miniled_display",
                    claim_name="量子点 MiniLED 显示",
                    raw_claim_text="量子点MiniLED带来更丰富的色彩层次。",
                )
            ],
        },
    )
    requests = [
        _request(),
        M04CSourceSellpointReadRequest(
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=second_sku,
        ),
    ]

    results = M04CSourceSellpointReader(repository).read_many(requests)

    assert sorted(results) == [second_sku, SKU_CODE]
    assert results[second_sku].source_sellpoints[0].claim_fact_id == "fact-c02"
    assert repository.calls == [
        ("profiles_many", BATCH_ID, f"{second_sku},{SKU_CODE}"),
        ("facts_many", BATCH_ID, f"{second_sku},{SKU_CODE}"),
    ]


def test_layer_integrity_counts_must_reconcile() -> None:
    with pytest.raises(ValidationError, match="reconcile"):
        LayerIntegritySummary(
            displayed_sellpoint_count=2,
            sourced_sellpoint_count=1,
            unsourced_sellpoint_count=0,
            parameter_as_sellpoint_count=0,
            value_theme_as_sellpoint_count=0,
            exact_quote_mismatch_count=0,
            dangling_sellpoint_link_count=0,
            source_profile_hash_mismatch_count=0,
        )


class FakeScalarResult:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def scalars(self) -> list[Any]:
        return list(self.value)


class FakeSession:
    def __init__(self, values: list[Any]) -> None:
        self.values = list(values)
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> FakeScalarResult:
        self.statements.append(statement)
        return FakeScalarResult(self.values.pop(0))


def test_sqlalchemy_repository_returns_profile_and_ordered_facts() -> None:
    profile = _profile()
    facts = [_fact("fact-1")]
    session = FakeSession([profile, facts])
    repository = SqlAlchemyM04CSourceSellpointRepository(
        session,  # type: ignore[arg-type]
        project_id=PROJECT_ID,
        category_code="TV",
    )

    assert repository.read_current_profile(
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
    ) is profile
    assert repository.list_current_facts(
        batch_id=BATCH_ID,
        sku_code=SKU_CODE,
    ) == facts
    assert len(session.statements) == 2
