from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.comment_native_dimension_runner import M084CommentNativeDimensionRunner
from app.services.core3_real_data.comment_native_dimension_schemas import M084NativeDimensionCandidateRecord
from app.services.core3_real_data.comment_native_dimension_service import _seed_matches_for_candidate
from app.services.core3_real_data.constants import Core3RunStatus, Core3SourceBatchStatus


PROJECT_ID = "core3_m084_validation"
BATCH_ID = "m00_m084_validation"


def make_session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    entities.Base.metadata.create_all(bind=engine)
    return Session(engine)


def seed_foundation(session: Session) -> None:
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="M08.4 验证项目", category_code="TV"))
    session.add(
        entities.Core3SourceBatch(
            batch_id=BATCH_ID,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_type="incremental",
            source_system="unit_test",
            source_database="unit_test",
            source_tables=["week_sales_data", "attribute_data", "selling_points_data", "comment_data"],
            ruleset_version="tv-core3-real-data-v2-0.1.0",
            module_version="m00-source-registry-0.1.0",
            hash_version="m00_row_hash_v1",
            scan_started_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
            status=Core3SourceBatchStatus.REGISTERED.value,
            review_status="auto_pass",
        )
    )
    session.flush()


def seed_m08_inputs(session: Session) -> None:
    rows = {
        "TV_GAME": (
            ("param", "core_params", "param.core_params"),
            ("claim", "final_claim_activation", "claim.final_claim_activation"),
            ("market", "sales", "sales"),
        ),
        "TV_BIG": (
            ("param", "screen_size_inch", "screen_size_inch"),
            ("claim", "CLAIM_LARGE_SCREEN_IMMERSION", "CLAIM_LARGE_SCREEN_IMMERSION"),
            ("market", "sales", "sales"),
        ),
    }
    for sku_code, feature_rows in rows.items():
        profile_id = f"profile-{sku_code}"
        session.add(
            entities.Core3SkuSignalProfile(
                sku_signal_profile_id=profile_id,
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code=sku_code,
                model_name=sku_code,
                brand_name="海信",
                market_summary_json={"sales_volume_12m": 100, "price_latest": 3999},
                data_completeness_score=Decimal("0.8000"),
                confidence=Decimal("0.7500"),
                confidence_level="medium",
                profile_status="ready",
                downstream_ready_json={"M08_4": {"ready": True}},
                input_fingerprint=f"m08-input-{sku_code}",
                profile_hash=f"m08-profile-{sku_code}",
                result_hash=f"m08-result-{sku_code}",
            )
        )
        for domain, sub_domain, feature_code in feature_rows:
            session.add(
                entities.Core3SkuSignalEvidenceMatrix(
                    sku_signal_evidence_matrix_id=f"matrix-{sku_code}-{feature_code}",
                    sku_signal_profile_id=profile_id,
                    project_id=PROJECT_ID,
                    category_code="TV",
                    batch_id=BATCH_ID,
                    sku_code=sku_code,
                    domain=domain,
                    sub_domain=sub_domain,
                    feature_code=feature_code,
                    evidence_count=1,
                    high_confidence_count=1,
                    representative_evidence_ids=[f"ev-{sku_code}-{feature_code}"],
                    domain_confidence=Decimal("0.8000"),
                    input_fingerprint=f"matrix-input-{sku_code}-{feature_code}",
                    result_hash=f"matrix-result-{sku_code}-{feature_code}",
                )
            )
    session.flush()


def seed_product_anchor_inputs(session: Session) -> None:
    session.add(
        entities.Core3SkuParamProfile(
            sku_param_profile_id="param-profile-TV_GAME",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code="TV_GAME",
            model_name="TV_GAME",
            param_values_json={"native_refresh_rate_hz": "144HZ", "hdmi_2_1_ports": "HDMI2.1"},
            core_gaming_params_json={"native_refresh_rate_hz": "144HZ", "hdmi_2_1_ports": "HDMI2.1"},
            param_completeness=Decimal("0.800000"),
            known_param_count=2,
            unknown_param_count=0,
            conflict_count=0,
            review_required_count=0,
            evidence_ids=["param-ev-refresh", "param-ev-hdmi"],
            quality_summary_json={},
            profile_hash="param-profile-hash-TV_GAME",
        )
    )
    session.add_all(
        [
            entities.Core3ExtractParamValue(
                param_value_id="param-refresh-TV_GAME",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code="TV_GAME",
                model_name="TV_GAME",
                param_code="native_refresh_rate_hz",
                param_name="原生刷新率",
                param_group="gaming",
                data_type="number",
                normalized_value={"value": 144, "unit": "Hz"},
                numeric_value=Decimal("144.000000"),
                value_text="144HZ",
                unit="Hz",
                value_presence="present",
                source_type="raw_param",
                source_priority_rank=1,
                raw_param_name="屏幕刷新率",
                raw_param_value="144HZ",
                match_type="seed_alias",
                parser_status="parsed",
                confidence=Decimal("0.9500"),
                confidence_level="high",
                evidence_ids=["param-ev-refresh"],
                primary_evidence_id="param-ev-refresh",
                quality_flags=[],
                param_value_hash="param-refresh-hash-TV_GAME",
            ),
            entities.Core3ExtractParamValue(
                param_value_id="param-hdmi-TV_GAME",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code="TV_GAME",
                model_name="TV_GAME",
                param_code="hdmi_2_1_ports",
                param_name="HDMI 2.1 接口数",
                param_group="gaming",
                data_type="string",
                normalized_value={"value": "HDMI2.1"},
                numeric_value=None,
                value_text="HDMI2.1",
                unit=None,
                value_presence="present",
                source_type="raw_param",
                source_priority_rank=1,
                raw_param_name="HDMI参数",
                raw_param_value="HDMI2.1",
                match_type="seed_alias",
                parser_status="parsed",
                confidence=Decimal("0.9000"),
                confidence_level="high",
                evidence_ids=["param-ev-hdmi"],
                primary_evidence_id="param-ev-hdmi",
                quality_flags=[],
                param_value_hash="param-hdmi-hash-TV_GAME",
            ),
        ]
    )
    session.add_all(
        [
            entities.Core3SkuClaimActivationBase(
                claim_activation_base_id="claim-base-refresh-TV_GAME",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code="TV_GAME",
                model_name="TV_GAME",
                claim_code="CLAIM_HIGH_REFRESH_RATE",
                claim_name="高刷新率",
                claim_group="gaming",
                claim_type="technical",
                param_score=Decimal("0.9000"),
                promo_score=Decimal("0.0000"),
                base_activation_score=Decimal("0.6300"),
                activation_level="medium",
                activation_basis="param_only",
                param_support_json={"matched_params": [{"param_code": "native_refresh_rate_hz"}]},
                promo_support_json={},
                missing_signals=[],
                conflict_flags=[],
                confidence=Decimal("0.8500"),
                confidence_level="high",
                evidence_ids=["param-ev-refresh"],
                param_evidence_ids=["param-ev-refresh"],
                promo_evidence_ids=[],
                quality_evidence_ids=[],
                claim_hit_ids=[],
                activation_hash="claim-base-refresh-hash-TV_GAME",
            ),
            entities.Core3SkuClaimActivationBase(
                claim_activation_base_id="claim-base-hdmi-TV_GAME",
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code="TV_GAME",
                model_name="TV_GAME",
                claim_code="CLAIM_HDMI_2_1_GAMING",
                claim_name="HDMI 2.1 游戏接口",
                claim_group="gaming",
                claim_type="technical",
                param_score=Decimal("0.8000"),
                promo_score=Decimal("0.0000"),
                base_activation_score=Decimal("0.5600"),
                activation_level="medium",
                activation_basis="param_only",
                param_support_json={"matched_params": [{"param_code": "hdmi_2_1_ports"}]},
                promo_support_json={},
                missing_signals=[],
                conflict_flags=[],
                confidence=Decimal("0.8000"),
                confidence_level="high",
                evidence_ids=["param-ev-hdmi"],
                param_evidence_ids=["param-ev-hdmi"],
                promo_evidence_ids=[],
                quality_evidence_ids=[],
                claim_hit_ids=[],
                activation_hash="claim-base-hdmi-hash-TV_GAME",
            ),
        ]
    )
    session.flush()


def seed_dirty_motion_anchor_inputs(session: Session) -> None:
    sku_code = "TV_DIRTY_SPORT"
    session.add(
        entities.Core3SkuSignalProfile(
            sku_signal_profile_id=f"profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=sku_code,
            brand_name="海信",
            market_summary_json={"sales_volume_12m": 80, "price_latest": 3299},
            data_completeness_score=Decimal("0.7000"),
            confidence=Decimal("0.7000"),
            confidence_level="medium",
            profile_status="ready",
            downstream_ready_json={"M08_4": {"ready": True}},
            input_fingerprint=f"m08-input-{sku_code}",
            profile_hash=f"m08-profile-{sku_code}",
            result_hash=f"m08-result-{sku_code}",
        )
    )
    session.add(
        entities.Core3SkuSignalEvidenceMatrix(
            sku_signal_evidence_matrix_id=f"matrix-{sku_code}-generic",
            sku_signal_profile_id=f"profile-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            domain="param",
            sub_domain="core_params",
            feature_code="param.core_params",
            evidence_count=1,
            high_confidence_count=1,
            representative_evidence_ids=["ev-dirty-sport-generic"],
            domain_confidence=Decimal("0.7000"),
            input_fingerprint=f"matrix-input-{sku_code}-generic",
            result_hash=f"matrix-result-{sku_code}-generic",
        )
    )
    session.add(
        entities.Core3ExtractParamValue(
            param_value_id=f"param-motion-dirty-{sku_code}",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            model_name=sku_code,
            param_code="motion_compensation_flag",
            param_name="运动补偿",
            param_group="motion",
            data_type="boolean",
            normalized_value={"value": True},
            numeric_value=None,
            value_text="是",
            unit=None,
            value_presence="present",
            source_type="raw_param",
            source_priority_rank=1,
            raw_param_name="人工智能",
            raw_param_value="是",
            match_type="seed_alias",
            parser_status="parsed",
            confidence=Decimal("0.7000"),
            confidence_level="medium",
            evidence_ids=["param-ev-motion-dirty"],
            primary_evidence_id="param-ev-motion-dirty",
            quality_flags=[],
            param_value_hash=f"param-motion-dirty-hash-{sku_code}",
        )
    )
    text = "看球赛时运动画面很流畅，追体育赛事不拖影"
    unit_id = "unit-dirty-motion"
    session.add(
        entities.Core3CommentUnit(
            comment_unit_id=unit_id,
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            comment_unit_key=unit_id,
            dedup_strategy="source_row_fallback",
            canonical_comment_text=text,
            canonical_text_length=len(text),
            source_row_count=1,
            source_sentence_count=1,
            sentiment_hint="positive",
            comment_unit_status="usable",
            low_value_flag=False,
            low_value_reasons=[],
            confidence=Decimal("0.7600"),
            confidence_level="medium",
            input_fingerprint="unit-input-dirty-motion",
            result_hash="unit-result-dirty-motion",
        )
    )
    session.add(
        entities.Core3CommentEvidenceAtom(
            comment_evidence_id="atom-dirty-motion",
            project_id=PROJECT_ID,
            category_code="TV",
            batch_id=BATCH_ID,
            sku_code=sku_code,
            comment_evidence_key="atom-dirty-motion",
            comment_unit_id=unit_id,
            sentence_source_priority="raw_fallback",
            sentence_text=text,
            normalized_sentence_text=text,
            sentence_length=len(text),
            primary_domain_hint="product_experience",
            sentiment_hint="positive",
            sentiment_source="text_rule",
            low_value_flag=False,
            low_value_reasons=[],
            specificity_score=Decimal("0.8000"),
            representative_phrase=text,
            usable_for_downstream=True,
            downstream_block_reasons=[],
            confidence=Decimal("0.7600"),
            confidence_level="medium",
            input_fingerprint="atom-input-dirty-motion",
            result_hash="atom-result-dirty-motion",
        )
    )
    session.flush()


def seed_m05_m06_inputs(session: Session) -> None:
    rows = [
        ("TV_GAME", "游戏主机高刷画面很流畅，低延迟体验明显", "product_experience", "atom-game", True, False),
        ("TV_BIG", "安装师傅上门很快，配送和挂架服务放心", "logistics_installation", "atom-service", True, False),
        ("TV_BIG", "安装很好", "logistics_installation", "atom-service-low-value", False, True),
    ]
    for sku_code, text, domain, atom_id, usable, low_value in rows:
        unit_id = f"unit-{atom_id}"
        session.add(
            entities.Core3CommentUnit(
                comment_unit_id=unit_id,
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code=sku_code,
                comment_unit_key=unit_id,
                dedup_strategy="source_row_fallback",
                canonical_comment_text=text,
                canonical_text_length=len(text),
                source_row_count=1,
                source_sentence_count=1,
                sentiment_hint="positive",
                comment_unit_status="usable" if usable else "low_value",
                low_value_flag=low_value,
                low_value_reasons=["generic_short_praise"] if low_value else [],
                confidence=Decimal("0.7500"),
                confidence_level="medium",
                input_fingerprint=f"unit-input-{atom_id}",
                result_hash=f"unit-result-{atom_id}",
            )
        )
        session.add(
            entities.Core3CommentEvidenceAtom(
                comment_evidence_id=atom_id,
                project_id=PROJECT_ID,
                category_code="TV",
                batch_id=BATCH_ID,
                sku_code=sku_code,
                comment_evidence_key=atom_id,
                comment_unit_id=unit_id,
                sentence_source_priority="raw_fallback",
                sentence_text=text,
                normalized_sentence_text=text,
                sentence_length=len(text),
                primary_domain_hint=domain,
                sentiment_hint="positive",
                sentiment_source="text_rule",
                low_value_flag=low_value,
                low_value_reasons=["generic_short_praise"] if low_value else [],
                specificity_score=Decimal("0.8200") if not low_value else Decimal("0.1000"),
                representative_phrase=text,
                usable_for_downstream=usable,
                downstream_block_reasons=["low_value"] if not usable else [],
                confidence=Decimal("0.7800") if not low_value else Decimal("0.2000"),
                confidence_level="medium" if not low_value else "low",
                input_fingerprint=f"atom-input-{atom_id}",
                result_hash=f"atom-result-{atom_id}",
            )
        )
    session.add_all(
        [
            _downstream_signal(
                signal_id="signal-game",
                sku_code="TV_GAME",
                signal_type="battlefield_support",
                target_code="BF_GAMING_SPORTS",
                target_name="游戏体育战场",
                evidence_ids=["atom-game"],
                phrases=["游戏主机高刷画面很流畅"],
            ),
            _downstream_signal(
                signal_id="signal-service",
                sku_code="TV_BIG",
                signal_type="service_signal",
                target_code="SERVICE_INSTALLATION",
                target_name="配送安装服务",
                evidence_ids=["atom-service"],
                phrases=["安装师傅上门很快"],
                service=True,
            ),
        ]
    )
    session.flush()


def _downstream_signal(
    *,
    signal_id: str,
    sku_code: str,
    signal_type: str,
    target_code: str,
    target_name: str,
    evidence_ids: list[str],
    phrases: list[str],
    service: bool = False,
) -> entities.Core3CommentDownstreamSignal:
    return entities.Core3CommentDownstreamSignal(
        signal_id=signal_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=sku_code,
        signal_key=signal_id,
        signal_type=signal_type,
        target_code_hint=target_code,
        target_name_hint=target_name,
        polarity="support",
        mention_count=2,
        sentence_count=2,
        valid_comment_unit_count=1,
        usable_sentence_count=2,
        mention_rate=Decimal("0.500000"),
        sentence_mention_rate=Decimal("0.500000"),
        positive_count=2,
        positive_rate=Decimal("1.000000"),
        signal_score=Decimal("0.8500"),
        signal_level="strong",
        specificity_avg=Decimal("0.8200"),
        evidence_quality_score=Decimal("0.8000"),
        sample_status="usable",
        representative_phrases=phrases,
        evidence_ids=evidence_ids,
        service_guardrail_flag=service,
        confidence=Decimal("0.8200"),
        confidence_level="high",
        input_fingerprint=f"signal-input-{signal_id}",
        result_hash=f"signal-result-{signal_id}",
    )


def test_m08_4_discovers_native_dimensions_before_seed_calibration() -> None:
    session = make_session()
    seed_foundation(session)
    seed_m08_inputs(session)
    seed_product_anchor_inputs(session)
    seed_m05_m06_inputs(session)

    result = M084CommentNativeDimensionRunner(session).run_batch(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_id="run-m084",
        module_run_id="module-run-m084",
    )

    assert result.module_code == "M08.4"
    assert result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING}
    assert result.summary_json["input_sku_count"] == 2
    assert result.summary_json["usable_comment_atom_count"] == 2
    assert result.summary_json["native_signal_count"] >= 2
    assert result.summary_json["native_dimension_count"] > 0
    assert result.summary_json["service_context_candidate_count"] == 1

    signals = session.execute(select(entities.Core3CommentNativeSignal)).scalars().all()
    signal_codes = {row.native_signal_code for row in signals}
    assert "scene_game_console" in signal_codes
    assert "capability_high_refresh_low_latency" in signal_codes
    assert "service_fulfillment" in signal_codes
    service_signal = next(row for row in signals if row.native_signal_code == "service_fulfillment")
    assert service_signal.sentence_count == 1
    assert service_signal.low_value_excluded_count == 0
    assert service_signal.service_context_flag is True

    candidates = session.execute(select(entities.Core3NativeDimensionCandidate)).scalars().all()
    product_values = {row.native_dimension_code for row in candidates if row.dimension_type == "native_product_value_battlefield"}
    task_names = {row.native_dimension_name_cn for row in candidates if row.dimension_type == "native_task"}
    group_names = {row.native_dimension_name_cn for row in candidates if row.dimension_type == "native_target_group"}
    battlefield_names = {row.native_dimension_name_cn for row in candidates if row.dimension_type == "native_product_value_battlefield"}
    service_candidates = [row for row in candidates if row.dimension_type == "service_context"]
    assert "native_product_value_battlefield_high_refresh_low_latency_gaming" in product_values
    assert "主机游戏低延迟娱乐" in task_names
    assert "主机游戏和年轻娱乐用户" in group_names
    assert "高刷低延迟游戏战场" in battlefield_names
    assert not any(row.native_dimension_name_cn.startswith(("任务：", "客群：", "产品价值：")) for row in candidates)
    assert all("service_fulfillment" not in code for code in product_values)
    assert len(service_candidates) == 1
    assert service_candidates[0].service_context_flag is True
    gaming_battlefield = next(row for row in candidates if row.native_dimension_code == "native_product_value_battlefield_high_refresh_low_latency_gaming")
    assert gaming_battlefield.product_anchor_score > Decimal("0.3000")
    assert "capability_high_refresh_low_latency" in gaming_battlefield.source_signal_codes
    anchor = gaming_battlefield.support_summary_json["product_anchor_by_sku"]["TV_GAME"]
    assert anchor["param_anchor_score"] > 0
    assert anchor["proxy_param_anchor_score"] == 0.0
    assert anchor["claim_anchor_score"] > 0
    assert anchor["comment_validation_score"] > 0
    assert anchor["market_anchor_score"] > 0
    assert anchor["overall_anchor_score"] == anchor["score"]
    assert anchor["anchor_source_status"] == "claim_plus_param"
    assert "comment_validated" in anchor["quality_flags"]
    assert {hit["anchor_code"] for hit in anchor["param_hits"]} >= {"native_refresh_rate_hz", "hdmi_2_1_ports"}
    assert {hit["anchor_code"] for hit in anchor["claim_hits"]} >= {"CLAIM_HIGH_REFRESH_RATE", "CLAIM_HDMI_2_1_GAMING"}
    assert anchor["comment_hits"]
    assert anchor["market_hits"]

    supports = session.execute(select(entities.Core3NativeDimensionSkuSupport)).scalars().all()
    assert any(
        row.sku_code == "TV_GAME"
        and row.native_dimension_code == "native_product_value_battlefield_high_refresh_low_latency_gaming"
        and row.support_score > 0
        for row in supports
    )

    alignments = session.execute(select(entities.Core3NativeDimensionAlignmentProposal)).scalars().all()
    assert any(row.proposed_action == "downgrade_to_service_context" for row in alignments)
    assert any(row.native_dimension_code == "native_product_value_battlefield_high_refresh_low_latency_gaming" for row in alignments)

    issues = session.execute(select(entities.Core3NativeDimensionReviewIssue)).scalars().all()
    assert any(row.issue_code == "service_signal_not_product_value" for row in issues)


def test_m08_4_blocks_dirty_param_mapping_from_effective_anchor_score() -> None:
    session = make_session()
    seed_foundation(session)
    seed_dirty_motion_anchor_inputs(session)

    result = M084CommentNativeDimensionRunner(session).run_batch(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_id="run-m084-dirty",
        module_run_id="module-run-m084-dirty",
    )

    assert result.status == Core3RunStatus.WARNING
    sports = session.execute(
        select(entities.Core3NativeDimensionCandidate).where(
            entities.Core3NativeDimensionCandidate.native_dimension_code
            == "native_product_value_battlefield_motion_smooth_sports"
        )
    ).scalar_one()
    anchor = sports.support_summary_json["product_anchor_by_sku"]["TV_DIRTY_SPORT"]
    assert anchor["param_anchor_score"] == 0.0
    assert anchor["comment_validation_score"] > 0.0
    assert anchor["market_anchor_score"] > 0.0
    assert anchor["score"] == 0.0
    assert anchor["overall_anchor_score"] == 0.0
    assert anchor["anchor_source_status"] == "comment_only"
    assert sports.product_anchor_score == Decimal("0.0000")
    assert sports.review_reason_json["reason"] == "missing_product_anchor"
    assert "param_mapping_suspect" in anchor["quality_flags"]
    assert any(hit["anchor_code"] == "motion_compensation_flag" for hit in anchor["param_hits"])
    assert all(hit["usable_for_battlefield"] is False for hit in anchor["param_hits"])

    issues = session.execute(select(entities.Core3NativeDimensionReviewIssue)).scalars().all()
    issue_codes = {row.issue_code for row in issues}
    assert "product_anchor_missing" in issue_codes
    assert "param_mapping_suspect" in issue_codes


def test_product_battlefield_candidate_can_align_to_multiple_seed_battlefields() -> None:
    seed_rows = [
        {
            "type": "battlefield",
            "code": "BF_PREMIUM_PICTURE",
            "name": "高端画质战场",
            "definition": "围绕 Mini LED/OLED、高亮、控光、色彩和高端价格支撑展开竞争。",
            "keywords": ["高端画质", "旗舰画质", "画质战场"],
        },
        {
            "type": "battlefield",
            "code": "BF_FAMILY_VIEWING_UPGRADE",
            "name": "家庭观影升级战场",
            "definition": "围绕客厅大屏、HDR、音效和全家观影体验展开竞争。",
            "keywords": ["家庭观影", "客厅升级", "客厅影院"],
        },
        {
            "type": "battlefield",
            "code": "BF_CINEMA_AUDIO_IMMERSION",
            "name": "影院音效战场",
            "definition": "围绕音响功率、杜比、环绕、低音和沉浸影院感展开竞争。",
            "keywords": ["影院音效", "沉浸音频", "音响战场"],
        },
        {
            "type": "battlefield",
            "code": "BF_SMART_SYSTEM_EXPERIENCE",
            "name": "智能系统体验战场",
            "definition": "围绕系统流畅、语音、内存、广告风险和智能体验展开竞争。",
            "keywords": ["智能系统", "系统体验", "语音系统"],
        },
        {
            "type": "battlefield",
            "code": "BF_SENIOR_EASE_OF_USE",
            "name": "长辈易用战场",
            "definition": "围绕语音、适老、简洁系统、少广告和长辈评论展开竞争。",
            "keywords": ["长辈易用", "老人友好", "爸妈电视"],
        },
    ]
    audio_candidate = _candidate_record(
        code="native_product_value_battlefield_audio_visual_immersion",
        name="声画沉浸战场",
        definition="SKU 依靠音响、杜比、声场、画质、亮度、色彩和 HDR 组合提供沉浸式影音体验。",
        source_signals=["capability_audio_immersion", "capability_picture_quality", "scene_living_room_family"],
        rule_keywords=["audio", "speaker", "dolby", "sound", "hdr", "mini", "oled", "音效", "影院", "画质", "亮度", "色彩", "客厅", "家庭"],
    )
    smart_candidate = _candidate_record(
        code="native_product_value_battlefield_smart_interaction_easy_use",
        name="智能交互易用战场",
        definition="SKU 依靠语音、遥控、系统流畅度和投屏等能力降低使用门槛。",
        source_signals=["capability_smart_easy_use", "person_senior"],
        rule_keywords=["system", "voice", "ram", "storage", "chip", "语音", "系统", "智能", "长辈"],
    )

    audio_codes = {str(row["code"]) for row, _ in _seed_matches_for_candidate(audio_candidate, seed_rows)}
    smart_codes = {str(row["code"]) for row, _ in _seed_matches_for_candidate(smart_candidate, seed_rows)}

    assert {"BF_PREMIUM_PICTURE", "BF_FAMILY_VIEWING_UPGRADE", "BF_CINEMA_AUDIO_IMMERSION"} <= audio_codes
    assert {"BF_SENIOR_EASE_OF_USE", "BF_SMART_SYSTEM_EXPERIENCE"} <= smart_codes


def _candidate_record(
    *,
    code: str,
    name: str,
    definition: str,
    source_signals: list[str],
    rule_keywords: list[str],
) -> M084NativeDimensionCandidateRecord:
    return M084NativeDimensionCandidateRecord(
        native_dimension_id=f"id-{code}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        dimension_type="native_product_value_battlefield",
        native_dimension_code=code,
        native_dimension_name_cn=name,
        definition_draft_cn=definition,
        source_signal_codes=source_signals,
        include_keyword_json={"matched": [], "rule_keywords": rule_keywords},
        exclude_keyword_json={},
        sentence_count=10,
        sku_count=5,
        strong_sku_count=3,
        native_support_score=Decimal("0.6000"),
        product_anchor_score=Decimal("0.3500"),
        distinctiveness_score=Decimal("0.7000"),
        representative_phrase_json=[],
        representative_evidence_ids=[],
        support_summary_json={},
        service_context_flag=False,
        candidate_status="candidate",
        review_required=False,
        review_reason_json={},
        input_fingerprint=f"input-{code}",
        result_hash=f"result-{code}",
    )
