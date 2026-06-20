from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.schemas.core3_real_data import Core3TargetScopeSchema
from app.services.core3_real_data.constants import (
    Core3ModuleTargetScope,
    Core3RunMode,
    Core3RunStatus,
    Core3SourceBatchStatus,
    Core3TargetScopeType,
)
from app.services.core3_real_data.m03b_param_profile_service import M03BParamEvidenceReader, M03BRunner, _display_tech_class
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.runner import Core3ModuleTarget


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606180001"
RUN_ID = "run-m03b"
MODULE_RUN_ID = "module-run-m03b"
SKU_CODE = "TV00027549"


def raw_param(raw_field: str, clean_value: str) -> dict[str, str]:
    return {"clean_field": raw_field, "clean_value": clean_value, "evidence_id": f"ev_{raw_field}"}


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    for table in [
        entities.CategoryProject.__table__,
        entities.Core3V2PipelineRun.__table__,
        entities.Core3V2ModuleRun.__table__,
        entities.Core3SourceBatch.__table__,
        entities.Core3EvidenceAtom.__table__,
        entities.Core3ExtractParamValue.__table__,
        entities.Core3SkuParamProfile.__table__,
        entities.Core3SkuParamDimensionTier.__table__,
        entities.Core3ParamTierCoverage.__table__,
    ]:
        table.create(bind=engine, checkfirst=True)

    session = Session(engine)
    seed_foundation(session)
    return session


def seed_foundation(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="Core3 MVP", category_code="TV"))
    session.add(
        entities.Core3V2PipelineRun(
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_mode="daily_incremental",
            ruleset_version="tv-core3-real-data-v2-0.1.0",
        )
    )
    session.add(
        entities.Core3V2ModuleRun(
            module_run_id=MODULE_RUN_ID,
            run_id=RUN_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            module_code="M03B",
            batch_id=BATCH_ID,
        )
    )
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            run_id=RUN_ID,
            module_run_id=MODULE_RUN_ID,
            batch_type="incremental",
            source_system="postgresql_205",
            source_database="catforge_dev",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
            review_status="auto_pass",
        )
    )
    session.flush()


def test_display_tech_class_uses_rgb_only_when_miniled_type_is_explicit_rgb_miniled():
    display_class, _ = _display_tech_class(
        {
            "产品技术": raw_param("产品技术", "LCD"),
            "背光源": raw_param("背光源", "LED"),
            "MINILED": raw_param("MINILED", "是"),
            "MINILED2": raw_param("MINILED2", "MINILED"),
            "RGB": raw_param("RGB", "RGB"),
        }
    )
    assert display_class == "miniled"

    display_class, _ = _display_tech_class(
        {
            "产品技术": raw_param("产品技术", "LCD"),
            "MINILED": raw_param("MINILED", "是"),
            "MINILED2": raw_param("MINILED2", "QD-MINILED"),
            "RGB": raw_param("RGB", "RGB"),
        }
    )
    assert display_class == "qd_miniled"

    display_class, _ = _display_tech_class(
        {
            "产品技术": raw_param("产品技术", "LCD"),
            "MINILED": raw_param("MINILED", "是"),
            "MINILED2": raw_param("MINILED2", "RGB-MINILED"),
            "RGB": raw_param("RGB", "RGB"),
        }
    )
    assert display_class == "rgb_miniled"

    display_class, _ = _display_tech_class(
        {
            "产品技术": raw_param("产品技术", "LCD"),
            "背光源": raw_param("背光源", "LED"),
            "MINILED": raw_param("MINILED", "否"),
            "MINILED2": raw_param("MINILED2", "非MINILED"),
            "RGB": raw_param("RGB", "RGB"),
        }
    )
    assert display_class == "lcd_led"


def seed_tv_param_evidence(session: Session) -> None:
    raw_fields = {
        "尺寸": "65英寸",
        "分辨率": "3840×2160",
        "清晰度2": "4K",
        "屏幕刷新率": "144HZ",
        "亮度": "200-300",
        "HDR": "HDR",
        "全色域": "100%",
        "MINILED": "否",
        "MINILED2": "非MINILED",
        "分区背光": "0",
        "产品技术": "LCD",
        "背光源": "LED",
        "RAM内存": "2GB",
        "ROM容量": "32GB",
        "AI大模型": "海信星海",
        "人工智能": "是",
        "语音识别": "支持",
        "远场语音": "支持",
        "HDMI参数": "HDMI2.1",
        "HDMI数量": "2",
        "USB参数": "USB2.0",
        "USB数量": "2",
        "机身厚度": "72MM",
        "能效等级": "一级",
    }
    session.add_all(
        entities.Core3EvidenceAtom(**evidence(f"ev_{index:03d}_{raw_field}", evidence_field=raw_field, clean_value=value))
        for index, (raw_field, value) in enumerate(raw_fields.items(), start=1)
    )
    session.add(
        entities.Core3EvidenceAtom(
            **evidence(
                "ev_comment",
                evidence_type="comment_sentence",
                evidence_grain="sentence",
                evidence_field="评论",
                clean_value="安装很快，服务很好",
                source_table="comment_data",
                clean_table="core3_clean_comment_sentence",
            )
        )
    )
    session.add(
        entities.Core3EvidenceAtom(
            **evidence(
                "ev_claim",
                evidence_type="promo_sentence",
                evidence_grain="sentence",
                evidence_field="卖点",
                clean_value="AI 画质引擎",
                source_table="selling_points_data",
                clean_table="core3_clean_claim_sentence",
            )
        )
    )
    session.add(
        entities.Core3EvidenceAtom(
            **evidence(
                "ev_market",
                evidence_type="market_fact",
                evidence_grain="row",
                evidence_field="销量",
                clean_value="100",
                source_table="week_sales_data",
                clean_table="core3_clean_market_weekly",
            )
        )
    )
    session.add(
        entities.Core3EvidenceAtom(
            **evidence("ev_ac_size", sku_code="AC00000001", model_name="KFR-35", evidence_field="尺寸", clean_value="1.5匹")
        )
    )
    session.flush()


def evidence(
    evidence_id: str,
    *,
    sku_code: str = SKU_CODE,
    model_name: str = "65E3Q",
    brand_name: str = "海信",
    evidence_type: str = "param_raw",
    evidence_grain: str = "field",
    evidence_field: str,
    clean_value: str,
    source_table: str = "attribute_data",
    clean_table: str = "core3_clean_attribute",
    base_confidence: Decimal = Decimal("0.9000"),
) -> dict:
    return {
        "evidence_id": evidence_id,
        "evidence_key": f"{BATCH_ID}:{sku_code}:{evidence_type}:{evidence_field}:{evidence_id}",
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "run_id": RUN_ID,
        "module_run_id": MODULE_RUN_ID,
        "sku_code": sku_code,
        "model_name": model_name,
        "brand_name": brand_name,
        "evidence_type": evidence_type,
        "evidence_grain": evidence_grain,
        "evidence_field": evidence_field,
        "evidence_title": evidence_field,
        "source_table": source_table,
        "source_pk": evidence_id,
        "source_row_id": f"{source_table}:{evidence_id}",
        "source_row_hash": f"sha256:m00_row_hash_v1:{evidence_id}",
        "clean_table": clean_table,
        "clean_record_key": f"{clean_table}:{evidence_id}",
        "clean_hash": f"sha256:m01_clean_hash_v1:{evidence_id}",
        "clean_version": "m01_clean_v1",
        "raw_field": evidence_field,
        "raw_value": clean_value,
        "clean_field": evidence_field,
        "clean_value": clean_value,
        "value_presence": "present",
        "numeric_values_json": [],
        "quality_status": "ok",
        "quality_flags": [],
        "base_confidence": base_confidence,
        "confidence_level": "high",
        "evidence_payload_json": {"clean_value": clean_value},
        "evidence_status": "current",
        "is_current": True,
        "evidence_version": "m02_evidence_v1",
        "confidence_rule_version": "m02_confidence_v1",
        "asset_version": "default",
        "review_required": False,
        "review_status": "auto_pass",
    }


def make_context(session: Session) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=session, project_id=PROJECT_ID)


def make_run_context():
    return build_run_context(
        run_id=RUN_ID,
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(scope_type=Core3TargetScopeType.CHANGED_SKU),
    )


def make_target(target_sku_codes=(), *, force_rebuild: bool = False):
    return Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(target_sku_codes),
        metadata={
            "batch_id": BATCH_ID,
            "module_run_id": MODULE_RUN_ID,
            "force_rebuild": force_rebuild,
            "sku_code_prefix": "TV",
        },
    )


def test_m03b_reader_consumes_only_current_tv_param_raw_evidence():
    session = make_session()
    seed_tv_param_evidence(session)

    records = M03BParamEvidenceReader(make_context(session)).list_param_raw_evidence(BATCH_ID, sku_code_prefix="TV")

    evidence_ids = {record.evidence_id for record in records}
    assert "ev_comment" not in evidence_ids
    assert "ev_claim" not in evidence_ids
    assert "ev_market" not in evidence_ids
    assert "ev_ac_size" not in evidence_ids
    assert {record.evidence_type for record in records} == {"param_raw"}
    assert len(records) == 24


def test_m03b_runner_builds_sku_param_profile_dimension_tiers_and_tier_coverage():
    session = make_session()
    seed_tv_param_evidence(session)

    result = M03BRunner(session).run(make_run_context(), make_target())

    assert result.module_code == "M03B"
    assert result.status == Core3RunStatus.SUCCESS
    assert result.input_count == 24
    assert result.output_count > 0

    profile = session.execute(select(entities.Core3SkuParamProfile).where(entities.Core3SkuParamProfile.sku_code == SKU_CODE)).scalar_one()
    profile_json = profile.param_values_json
    assert profile_json["screen_size_inch"]["normalized_value"] == 65
    assert profile_json["screen_size_segment"]["normalized_value"] == "large_60_69"
    assert profile_json["display_tech_class"]["normalized_value"] == "lcd_led"
    assert profile_json["camera_flag"]["normalized_value"] is False
    assert profile_json["dimension_tier_profile"] == {
        "appearance": "appearance_standard",
        "display_tech": "lcd_led",
        "energy": "energy_grade_1",
        "local_dimming": "z_none_0",
        "performance": "perf_basic",
        "picture_overall": "picture_enhanced",
        "ports": "ports_main_hdmi21",
        "size": "large_60_69",
        "smart": "smart_ai_voice",
    }

    dimension_tiers = session.execute(
        select(entities.Core3SkuParamDimensionTier).where(entities.Core3SkuParamDimensionTier.sku_code == SKU_CODE)
    ).scalars().all()
    assert len(dimension_tiers) == 9
    assert {
        (item.dimension_code, item.tier_code)
        for item in dimension_tiers
    } >= {("picture_overall", "picture_enhanced"), ("display_tech", "lcd_led"), ("performance", "perf_basic")}

    picture_coverage = session.execute(
        select(entities.Core3ParamTierCoverage).where(
            entities.Core3ParamTierCoverage.dimension_code == "picture_overall",
            entities.Core3ParamTierCoverage.tier_code == "picture_enhanced",
        )
    ).scalar_one()
    assert picture_coverage.sku_count == 1
    assert picture_coverage.sku_codes == [SKU_CODE]

    oled_coverage = session.execute(
        select(entities.Core3ParamTierCoverage).where(
            entities.Core3ParamTierCoverage.dimension_code == "display_tech",
            entities.Core3ParamTierCoverage.tier_code == "oled",
        )
    ).scalar_one()
    assert oled_coverage.sku_count == 0
    assert oled_coverage.coverage_status == "empty_current_batch"

    saved_param_codes = {
        param_code
        for (param_code,) in session.execute(select(entities.Core3ExtractParamValue.param_code)).all()
    }
    assert "camera_flag" not in saved_param_codes
    assert "screen_size_inch" in saved_param_codes

    second_result = M03BRunner(session).run(make_run_context(), make_target())
    assert second_result.status == Core3RunStatus.SUCCESS
    assert session.scalar(select(func.count()).select_from(entities.Core3SkuParamProfile)) == 1
    assert session.scalar(select(func.count()).select_from(entities.Core3SkuParamDimensionTier)) == 9
    assert session.scalar(select(func.count()).select_from(entities.Core3ParamTierCoverage)) > 20


def test_m03b_force_rebuild_refreshes_same_business_keys():
    session = make_session()
    seed_tv_param_evidence(session)

    M03BRunner(session).run(make_run_context(), make_target())
    result = M03BRunner(session).run(make_run_context(), make_target(force_rebuild=True))

    assert result.status == Core3RunStatus.SUCCESS
    assert session.scalar(select(func.count()).select_from(entities.Core3SkuParamProfile)) == 1
    assert session.scalar(select(func.count()).select_from(entities.Core3SkuParamDimensionTier)) == 9
