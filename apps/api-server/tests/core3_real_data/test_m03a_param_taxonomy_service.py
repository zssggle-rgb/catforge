from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.param_taxonomy_repositories import (
    ParamTaxonomyEvidenceReader,
    ParamTaxonomyRepository,
)
from app.services.core3_real_data.param_taxonomy_schemas import (
    ParamDefinitionInput,
    ParamTaxonomyDraftRequest,
    TaxonomyReviewStatus,
    TaxonomyStatus,
)
from app.services.core3_real_data.param_taxonomy_service import ParamTaxonomyLlmError, ParamTaxonomyService


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606200001"


class FakeTaxonomyClient:
    model_name = "deepseek-v4-pro"

    def __init__(self) -> None:
        self.last_package = None

    def generate_taxonomy(self, package):
        self.last_package = package
        return {
            "param_candidates": [
                {
                    "candidate_code": "SCREEN_SIZE_INCH",
                    "candidate_name": "屏幕尺寸",
                    "source_raw_fields": ["屏幕尺寸"],
                    "definition_candidate": "屏幕对角线尺寸，通常以英寸表示。",
                    "data_type_candidate": "number",
                    "unit_candidate": "英寸",
                    "parser_candidate": "number",
                    "capability_tags": ["大屏沉浸", "TASK_LIVING_ROOM"],
                    "benefit_hints": ["观看距离", "沉浸感"],
                    "scenario_hints": ["客厅观影"],
                    "comparison_axis": "larger_better",
                    "evidence_role": "strong_param_evidence",
                    "confidence": 0.93,
                    "review_required": False,
                },
                {
                    "candidate_code": "REFRESH_RATE_HZ",
                    "candidate_name": "刷新率",
                    "source_raw_fields": ["刷新率"],
                    "definition_candidate": "屏幕每秒刷新次数，通常以 Hz 表示。",
                    "data_type_candidate": "number",
                    "unit_candidate": "Hz",
                    "parser_candidate": "number",
                    "capability_tags": ["画面流畅"],
                    "benefit_hints": ["运动画面更顺滑"],
                    "scenario_hints": ["游戏", "体育赛事"],
                    "comparison_axis": "larger_better",
                    "evidence_role": "strong_param_evidence",
                    "confidence": 0.91,
                    "review_required": False,
                },
            ],
            "field_decisions": [
                {
                    "raw_param_name": "屏幕尺寸",
                    "param_code": "PARAM_SCREEN_SIZE_INCH",
                    "mapping_type": "direct",
                    "value_policy": "use_as_value",
                    "confidence": 0.95,
                },
                {
                    "raw_param_name": "刷新率",
                    "param_code": "PARAM_REFRESH_RATE_HZ",
                    "mapping_type": "direct",
                    "value_policy": "use_as_value",
                    "confidence": 0.94,
                },
                {
                    "raw_param_name": "商品编号",
                    "mapping_type": "metadata",
                    "value_policy": "do_not_extract",
                    "confidence": 0.86,
                },
            ],
            "review_items": [],
        }


class FailingTaxonomyClient:
    model_name = "deepseek-v4-pro"

    def generate_taxonomy(self, package):
        raise ParamTaxonomyLlmError("LLM unavailable")


class EmptyCandidateTaxonomyClient:
    model_name = "deepseek-v4-pro"

    def generate_taxonomy(self, package):
        return {"param_candidates": []}


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3ParamTaxonomyVersion.__table__,
        entities.Core3ParamRawFieldInventory.__table__,
        entities.Core3ParamFieldCluster.__table__,
        entities.Core3ParamConceptCandidate.__table__,
        entities.Core3ParamDefinition.__table__,
        entities.Core3ParamFieldMappingRule.__table__,
        entities.Core3ParamTaxonomyReviewItem.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["attribute_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            status="registered",
        )
    )
    session.add_all(
        [
            _param_atom("ev_size_1", sku_code="TV001", raw_field="屏幕尺寸", clean_value="85英寸", unit_value="英寸"),
            _param_atom("ev_size_2", sku_code="TV002", raw_field="屏幕尺寸", clean_value="75英寸", unit_value="英寸"),
            _param_atom("ev_refresh_1", sku_code="TV001", raw_field="刷新率", clean_value="144Hz", unit_value="Hz"),
            _param_atom("ev_refresh_2", sku_code="TV002", raw_field="刷新率", clean_value="120Hz", unit_value="Hz"),
            _param_atom("ev_sku_meta_1", sku_code="TV001", raw_field="商品编号", clean_value="1000123"),
        ]
    )
    session.flush()
    return session


def _param_atom(
    evidence_id: str,
    *,
    sku_code: str,
    raw_field: str,
    clean_value: str,
    unit_value: str | None = None,
) -> entities.Core3EvidenceAtom:
    return entities.Core3EvidenceAtom(
        evidence_id=evidence_id,
        evidence_key=f"key_{evidence_id}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=sku_code,
        model_name="85E7Q" if sku_code == "TV001" else "75E7Q",
        brand_name="海信",
        evidence_type="param_raw",
        evidence_grain="field",
        evidence_field=raw_field,
        evidence_title=f"{raw_field}参数原始证据",
        source_table="attribute_data",
        source_pk=evidence_id,
        source_row_id=f"attribute_data:{evidence_id}",
        source_row_hash=f"sha256:m00_row_hash_v1:{evidence_id}",
        clean_table="core3_clean_attribute",
        clean_record_key=f"attribute:{evidence_id}",
        clean_hash=f"sha256:m01_clean_hash_v1:{evidence_id}",
        clean_version="m01_clean_v1",
        raw_field=raw_field,
        raw_value=clean_value,
        clean_field=raw_field,
        clean_value=clean_value,
        value_presence="present",
        numeric_values_json=[],
        unit_value=unit_value,
        text_value=clean_value,
        quality_status="ok",
        quality_flags=[],
        base_confidence=Decimal("0.9000"),
        confidence_level="high",
        evidence_payload_json={},
        evidence_status="current",
        is_current=True,
        evidence_version="m02_evidence_v1",
        confidence_rule_version="m02_confidence_v1",
        asset_version="default",
        review_required=False,
        review_status="auto_pass",
    )


def test_param_taxonomy_service_builds_draft_from_m02_param_evidence():
    session = make_session()
    fake_client = FakeTaxonomyClient()
    repository = ParamTaxonomyRepository(session, PROJECT_ID)
    service = ParamTaxonomyService(
        repository,
        ParamTaxonomyEvidenceReader(session, PROJECT_ID),
        llm_client=fake_client,
        page_size=2,
    )

    result = service.build_draft(
        ParamTaxonomyDraftRequest(
            category_code="TV",
            batch_ids=[BATCH_ID],
            taxonomy_version="tv_param_taxonomy_test_v1",
            use_llm=True,
            created_by="pytest",
        )
    )
    session.flush()

    taxonomy = repository.load_taxonomy("tv_param_taxonomy_test_v1", category_code="TV")
    definitions = {item.param_code: item for item in taxonomy["definitions"]}
    mapping_rules = {item.raw_param_name: item for item in taxonomy["mapping_rules"]}

    assert fake_client.last_package["fields"][0]["raw_param_name"] in {"刷新率", "商品编号", "屏幕尺寸"}
    assert result.source_field_count == 3
    assert result.active_param_count == 2
    assert set(definitions) == {"PARAM_SCREEN_SIZE_INCH", "PARAM_REFRESH_RATE_HZ"}
    assert definitions["PARAM_SCREEN_SIZE_INCH"].source_raw_fields == ["屏幕尺寸"]
    assert definitions["PARAM_SCREEN_SIZE_INCH"].capability_tags == ["大屏沉浸"]
    assert mapping_rules["商品编号"].mapping_type == "metadata"
    assert any(item.item_type == "downstream_tag_removed" for item in taxonomy["review_items"])


def test_param_taxonomy_review_count_refreshes_and_publish_sets_current():
    session = make_session()
    repository = ParamTaxonomyRepository(session, PROJECT_ID)
    service = ParamTaxonomyService(
        repository,
        ParamTaxonomyEvidenceReader(session, PROJECT_ID),
        llm_client=FakeTaxonomyClient(),
    )
    service.build_draft(
        ParamTaxonomyDraftRequest(
            category_code="TV",
            batch_ids=[BATCH_ID],
            taxonomy_version="tv_param_taxonomy_publish_v1",
            use_llm=True,
        )
    )
    taxonomy = repository.load_taxonomy("tv_param_taxonomy_publish_v1", category_code="TV")
    review_item = taxonomy["review_items"][0]
    before = repository.get_version("tv_param_taxonomy_publish_v1", category_code="TV")
    assert before is not None
    assert before.review_required_count >= 1
    before_review_required_count = before.review_required_count

    repository.apply_review_decision(
        taxonomy_version="tv_param_taxonomy_publish_v1",
        review_item_id=review_item.review_item_id,
        review_status=TaxonomyReviewStatus.APPROVED.value,
        decision_payload={"reason": "validated in test"},
    )
    after = repository.get_version("tv_param_taxonomy_publish_v1", category_code="TV")
    assert after is not None
    assert after.review_required_count == before_review_required_count - 1

    published = repository.publish(category_code="TV", taxonomy_version="tv_param_taxonomy_publish_v1")

    assert published.status == TaxonomyStatus.PUBLISHED.value
    assert repository.get_current_published("TV").taxonomy_version == "tv_param_taxonomy_publish_v1"


def test_param_taxonomy_requires_llm_when_enabled():
    session = make_session()
    repository = ParamTaxonomyRepository(session, PROJECT_ID)
    service = ParamTaxonomyService(
        repository,
        ParamTaxonomyEvidenceReader(session, PROJECT_ID),
        llm_client=FailingTaxonomyClient(),
    )

    with pytest.raises(ParamTaxonomyLlmError, match="LLM unavailable"):
        service.build_draft(
            ParamTaxonomyDraftRequest(
                category_code="TV",
                batch_ids=[BATCH_ID],
                taxonomy_version="tv_param_taxonomy_requires_llm",
                use_llm=True,
            )
        )

    assert repository.get_version("tv_param_taxonomy_requires_llm", category_code="TV") is None


def test_param_taxonomy_rejects_empty_llm_candidates_when_enabled():
    session = make_session()
    repository = ParamTaxonomyRepository(session, PROJECT_ID)
    service = ParamTaxonomyService(
        repository,
        ParamTaxonomyEvidenceReader(session, PROJECT_ID),
        llm_client=EmptyCandidateTaxonomyClient(),
    )

    with pytest.raises(ParamTaxonomyLlmError, match="empty param_candidates"):
        service.build_draft(
            ParamTaxonomyDraftRequest(
                category_code="TV",
                batch_ids=[BATCH_ID],
                taxonomy_version="tv_param_taxonomy_empty_llm",
                use_llm=True,
            )
        )

    assert repository.get_version("tv_param_taxonomy_empty_llm", category_code="TV") is None


def test_param_definition_rejects_downstream_business_codes_in_capability_tags():
    with pytest.raises(ValueError, match="downstream business codes"):
        ParamDefinitionInput(
            param_code="PARAM_SCREEN_SIZE_INCH",
            param_name="屏幕尺寸",
            definition="屏幕对角线尺寸。",
            source_raw_fields=["屏幕尺寸"],
            capability_tags=["TASK_LIVING_ROOM"],
            definition_hash="sha256:test",
        )
