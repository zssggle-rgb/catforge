from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models import entities
from app.services.core3_real_data.constants import Core3RunStatus, Core3SourceBatchStatus
from app.services.core3_real_data.dimension_ontology_runner import M085DimensionOntologyRunner
from app.services.core3_real_data.dimension_ontology_seed_loader import M085DimensionSeedLoader


PROJECT_ID = "core3_m085_validation"
BATCH_ID = "m00_m085_validation"


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
    session.add(entities.CategoryProject(project_id=PROJECT_ID, name="M08.5 验证项目", category_code="TV"))
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
    for sku_code, feature_rows in {
        "TV_GAME": (
            ("param", "native_refresh_rate_hz", "native_refresh_rate_hz"),
            ("claim", "CLAIM_HIGH_REFRESH_RATE", "CLAIM_HIGH_REFRESH_RATE"),
            ("market", "sales", "sales"),
        ),
        "TV_BIG": (
            ("param", "screen_size_inch", "screen_size_inch"),
            ("claim", "CLAIM_LARGE_SCREEN_IMMERSION", "CLAIM_LARGE_SCREEN_IMMERSION"),
            ("market", "sales", "sales"),
        ),
    }.items():
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
                data_completeness_score=Decimal("0.8000"),
                confidence=Decimal("0.7500"),
                confidence_level="medium",
                profile_status="ready",
                market_summary_json=market_summary_fixture(sku_code),
                business_signal_index_json=business_signal_index_fixture(sku_code),
                downstream_ready_json={"M08_5": {"ready": True}},
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


def market_summary_fixture(sku_code: str) -> dict:
    if sku_code == "TV_GAME":
        return {
            "market_pool_key": "TV|large_upgrade|online|latest_12m",
            "screen_size_class": "large_upgrade",
            "same_pool_price_percentile": "0.6200",
            "same_pool_volume_percentile": "0.7200",
            "same_pool_amount_percentile": "0.7600",
            "price_per_inch_percentile": "0.4800",
            "same_pool_sku_count": 18,
        }
    return {
        "market_pool_key": "TV|large_upgrade|online|latest_12m",
        "screen_size_class": "large_upgrade",
        "same_pool_price_percentile": "0.3600",
        "same_pool_volume_percentile": "0.6600",
        "same_pool_amount_percentile": "0.6400",
        "price_per_inch_percentile": "0.3300",
        "same_pool_sku_count": 18,
    }


def business_signal_index_fixture(sku_code: str) -> dict:
    summary = market_summary_fixture(sku_code)
    if sku_code == "TV_GAME":
        anchor_groups = {
            "motion_gaming": {
                "overall_score": "0.5200",
                "param_anchor_score": "0.4000",
                "claim_anchor_score": "0.1200",
                "market_anchor_score": "0.0000",
                "source_status": "claim_plus_param",
            },
            "screen_value_market": {
                "overall_score": "0.2000",
                "param_anchor_score": "0.1000",
                "claim_anchor_score": "0.0000",
                "market_anchor_score": "0.1000",
                "source_status": "param_plus_market",
            },
        }
    else:
        anchor_groups = {
            "screen_value_market": {
                "overall_score": "0.4200",
                "param_anchor_score": "0.2000",
                "claim_anchor_score": "0.1200",
                "market_anchor_score": "0.1000",
                "source_status": "claim_plus_param",
            },
            "audio_immersion": {
                "overall_score": "0.1800",
                "param_anchor_score": "0.0000",
                "claim_anchor_score": "0.1800",
                "market_anchor_score": "0.0000",
                "source_status": "claim_only",
            },
        }
    return {
        "market_pool_key": summary["market_pool_key"],
        "screen_size_class": summary["screen_size_class"],
        "same_pool_position": {
            "price_percentile": summary["same_pool_price_percentile"],
            "volume_percentile": summary["same_pool_volume_percentile"],
            "amount_percentile": summary["same_pool_amount_percentile"],
            "price_per_inch_percentile": summary["price_per_inch_percentile"],
            "sample_count": summary["same_pool_sku_count"],
        },
        "product_anchor_index": {
            "anchor_schema_version": "m08_product_anchor_index_v1",
            "anchor_groups": anchor_groups,
            "anchor_group_count": len(anchor_groups),
            "strong_anchor_groups": [
                code
                for code, payload in anchor_groups.items()
                if Decimal(str(payload["overall_score"])) >= Decimal("0.3000") and payload["source_status"] not in {"claim_only", "market_only"}
            ],
            "market_pool_key": summary["market_pool_key"],
            "screen_size_class": summary["screen_size_class"],
        },
    }


def seed_m05_m06_inputs(session: Session) -> None:
    rows = [
        (
            "TV_GAME",
            "游戏主机高刷画面很流畅，低延迟体验明显",
            "product_experience",
            "atom-game",
            True,
            False,
        ),
        (
            "TV_BIG",
            "安装师傅上门很快，配送和挂架服务放心",
            "logistics_installation",
            "atom-service",
            True,
            False,
        ),
        (
            "TV_BIG",
            "安装很好",
            "logistics_installation",
            "atom-service-low-value",
            False,
            True,
        ),
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
            downstream_signal(
                signal_id="signal-game",
                sku_code="TV_GAME",
                signal_type="battlefield_support",
                target_code="BF_GAMING_SPORTS",
                target_name="游戏体育战场",
                evidence_ids=["atom-game"],
                phrases=["游戏主机高刷画面很流畅"],
            ),
            downstream_signal(
                signal_id="signal-service",
                sku_code="TV_BIG",
                signal_type="battlefield_support",
                target_code="BF_SERVICE_ASSURANCE",
                target_name="服务保障战场",
                evidence_ids=["atom-service"],
                phrases=["安装师傅上门很快"],
                service=True,
            ),
            downstream_signal(
                signal_id="signal-task-game",
                sku_code="TV_GAME",
                signal_type="task_cue",
                target_code="TASK_GAMING_ENTERTAINMENT",
                target_name="游戏娱乐",
                evidence_ids=["atom-game"],
                phrases=["游戏主机高刷"],
            ),
        ]
    )
    session.flush()


def seed_m08_4_inputs(session: Session) -> None:
    candidates = [
        native_candidate(
            native_dimension_id="native-dim-game",
            native_dimension_code="native_product_value_battlefield_high_refresh_low_latency_gaming",
            native_dimension_name_cn="高刷低延迟游戏战场",
            source_signal_codes=["capability_high_refresh_low_latency", "scene_game_console"],
            sku_count=1,
            strong_sku_count=1,
            product_anchor_score=Decimal("0.4500"),
            support_summary_json={
                "product_anchor_by_sku": {
                    "TV_GAME": {
                        "score": 0.72,
                        "param_anchor_score": 0.80,
                        "claim_anchor_score": 0.65,
                        "quality_flags": [],
                        "param_hits": [
                            {
                                "anchor_code": "native_refresh_rate_hz",
                                "quality_flags": [],
                                "usable_for_battlefield": True,
                            }
                        ],
                        "claim_hits": [
                            {
                                "anchor_code": "CLAIM_HIGH_REFRESH_RATE",
                                "quality_flags": [],
                                "usable_for_battlefield": True,
                            }
                        ],
                    }
                },
                "anchor_quality_summary": {
                    "covered_sku_count": 1,
                    "anchor_sku_count": 1,
                    "valid_param_sku_count": 1,
                    "valid_claim_sku_count": 1,
                    "dirty_param_sku_count": 0,
                    "matrix_only_sku_count": 0,
                    "quality_flags": [],
                },
            },
        ),
        native_candidate(
            native_dimension_id="native-dim-eye",
            native_dimension_code="native_product_value_battlefield_eye_care_comfort",
            native_dimension_name_cn="护眼舒适战场",
            source_signal_codes=["capability_eye_care"],
            sku_count=1,
            strong_sku_count=0,
            product_anchor_score=Decimal("0.0800"),
            candidate_status="candidate_review",
            review_required=True,
            review_reason_json={"reason": "product_anchor_weak"},
            support_summary_json={
                "product_anchor_by_sku": {
                    "TV_BIG": {
                        "score": 0.12,
                        "param_anchor_score": 0.00,
                        "claim_anchor_score": 0.12,
                        "quality_flags": ["product_anchor_weak"],
                    }
                },
                "anchor_quality_summary": {
                    "covered_sku_count": 1,
                    "anchor_sku_count": 1,
                    "valid_param_sku_count": 0,
                    "valid_claim_sku_count": 1,
                    "dirty_param_sku_count": 0,
                    "matrix_only_sku_count": 0,
                    "quality_flags": ["product_anchor_weak"],
                },
            },
        ),
        native_candidate(
            native_dimension_id="native-dim-audio",
            native_dimension_code="native_product_value_battlefield_audio_immersion",
            native_dimension_name_cn="沉浸声画战场",
            source_signal_codes=["capability_audio_immersion"],
            sku_count=1,
            strong_sku_count=1,
            product_anchor_score=Decimal("0.3500"),
            candidate_status="candidate_review",
            review_required=True,
            review_reason_json={"reason": "param_mapping_suspect"},
            support_summary_json={
                "product_anchor_by_sku": {
                    "TV_BIG": {
                        "score": 0.35,
                        "param_anchor_score": 0.30,
                        "claim_anchor_score": 0.45,
                        "quality_flags": ["param_mapping_suspect"],
                    }
                },
                "anchor_quality_summary": {
                    "covered_sku_count": 1,
                    "anchor_sku_count": 1,
                    "valid_param_sku_count": 0,
                    "valid_claim_sku_count": 1,
                    "dirty_param_sku_count": 1,
                    "matrix_only_sku_count": 0,
                    "quality_flags": ["param_mapping_suspect"],
                },
            },
        ),
        native_candidate(
            native_dimension_id="native-dim-sports-dirty",
            native_dimension_code="native_product_value_battlefield_motion_smooth_sports",
            native_dimension_name_cn="运动流畅观看战场",
            source_signal_codes=["capability_motion_smooth"],
            sku_count=1,
            strong_sku_count=0,
            product_anchor_score=Decimal("0.1200"),
            candidate_status="candidate_review",
            review_required=True,
            review_reason_json={"reason": "param_mapping_suspect"},
            support_summary_json={
                "product_anchor_by_sku": {
                    "TV_GAME": {
                        "score": 0.12,
                        "param_anchor_score": 0.00,
                        "claim_anchor_score": 0.12,
                        "quality_flags": ["param_mapping_suspect", "product_anchor_weak"],
                        "param_hits": [
                            {
                                "anchor_code": "motion_compensation_flag",
                                "quality_flags": ["param_mapping_suspect"],
                                "usable_for_battlefield": False,
                            }
                        ],
                    }
                },
                "anchor_quality_summary": {
                    "covered_sku_count": 1,
                    "anchor_sku_count": 1,
                    "valid_param_sku_count": 0,
                    "valid_claim_sku_count": 1,
                    "dirty_param_sku_count": 1,
                    "matrix_only_sku_count": 0,
                    "quality_flags": ["param_mapping_suspect", "product_anchor_weak"],
                },
            },
        ),
    ]
    session.add_all(candidates)
    session.add_all(
        [
            native_support(
                native_dimension_id="native-dim-game",
                native_dimension_code="native_product_value_battlefield_high_refresh_low_latency_gaming",
                sku_code="TV_GAME",
                product_anchor_score=Decimal("0.7200"),
                support_score=Decimal("0.8200"),
                support_level="strong",
            ),
            native_support(
                native_dimension_id="native-dim-eye",
                native_dimension_code="native_product_value_battlefield_eye_care_comfort",
                sku_code="TV_BIG",
                product_anchor_score=Decimal("0.1200"),
                support_score=Decimal("0.2600"),
                support_level="weak",
            ),
            native_support(
                native_dimension_id="native-dim-audio",
                native_dimension_code="native_product_value_battlefield_audio_immersion",
                sku_code="TV_BIG",
                product_anchor_score=Decimal("0.3500"),
                support_score=Decimal("0.5600"),
                support_level="medium",
            ),
            native_support(
                native_dimension_id="native-dim-sports-dirty",
                native_dimension_code="native_product_value_battlefield_motion_smooth_sports",
                sku_code="TV_GAME",
                product_anchor_score=Decimal("0.1200"),
                support_score=Decimal("0.2400"),
                support_level="weak",
            ),
        ]
    )
    session.add_all(
        [
            native_alignment(
                native_dimension_id="native-dim-game",
                native_dimension_code="native_product_value_battlefield_high_refresh_low_latency_gaming",
                native_dimension_name_cn="高刷低延迟游戏战场",
                seed_dimension_code="BF_GAMING_SPORTS",
                seed_dimension_name_cn="游戏体育战场",
                alignment_score=Decimal("0.8800"),
            ),
            native_alignment(
                native_dimension_id="native-dim-eye",
                native_dimension_code="native_product_value_battlefield_eye_care_comfort",
                native_dimension_name_cn="护眼舒适战场",
                seed_dimension_code="BF_FAMILY_EYE_CARE",
                seed_dimension_name_cn="家庭护眼战场",
                alignment_score=Decimal("0.7600"),
            ),
            native_alignment(
                native_dimension_id="native-dim-audio",
                native_dimension_code="native_product_value_battlefield_audio_immersion",
                native_dimension_name_cn="沉浸声画战场",
                seed_dimension_code="BF_CINEMA_AUDIO_IMMERSION",
                seed_dimension_name_cn="影院声画沉浸战场",
                alignment_score=Decimal("0.8200"),
            ),
            native_alignment(
                native_dimension_id="native-dim-sports-dirty",
                native_dimension_code="native_product_value_battlefield_motion_smooth_sports",
                native_dimension_name_cn="运动流畅观看战场",
                seed_dimension_code="BF_GAMING_SPORTS",
                seed_dimension_name_cn="游戏体育战场",
                alignment_score=Decimal("0.7000"),
            ),
        ]
    )
    session.add_all(
        [
            native_review_issue(
                issue_key="m084-eye-weak",
                issue_code="product_anchor_weak",
                object_code="native_product_value_battlefield_eye_care_comfort",
                issue_message_cn="护眼舒适只有弱卖点锚点，不能进入分配。",
            ),
            native_review_issue(
                issue_key="m084-audio-param-suspect",
                issue_code="param_mapping_suspect",
                object_code="native_product_value_battlefield_audio_immersion",
                issue_message_cn="声画沉浸存在参数映射可疑，不能进入分配。",
            ),
            native_review_issue(
                issue_key="m084-sports-weak",
                issue_code="product_anchor_weak",
                object_code="native_product_value_battlefield_motion_smooth_sports",
                issue_message_cn="运动流畅候选锚点偏弱。",
            ),
            native_review_issue(
                issue_key="m084-sports-param-suspect",
                issue_code="param_mapping_suspect",
                object_code="native_product_value_battlefield_motion_smooth_sports",
                issue_message_cn="运动流畅候选存在参数映射可疑。",
            ),
        ]
    )
    session.flush()


def native_candidate(
    *,
    native_dimension_id: str,
    native_dimension_code: str,
    native_dimension_name_cn: str,
    source_signal_codes: list[str],
    sku_count: int,
    strong_sku_count: int,
    product_anchor_score: Decimal,
    support_summary_json: dict,
    candidate_status: str = "candidate",
    review_required: bool = False,
    review_reason_json: dict | None = None,
) -> entities.Core3NativeDimensionCandidate:
    return entities.Core3NativeDimensionCandidate(
        native_dimension_id=native_dimension_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        dimension_type="native_product_value_battlefield",
        native_dimension_code=native_dimension_code,
        native_dimension_name_cn=native_dimension_name_cn,
        definition_draft_cn=f"{native_dimension_name_cn}，由评论原生信号和产品锚点共同归纳。",
        source_signal_codes=source_signal_codes,
        include_keyword_json={"keywords": []},
        exclude_keyword_json={"keywords": []},
        sentence_count=3,
        sku_count=sku_count,
        strong_sku_count=strong_sku_count,
        native_support_score=Decimal("0.6000"),
        product_anchor_score=product_anchor_score,
        distinctiveness_score=Decimal("0.7000"),
        representative_phrase_json=[native_dimension_name_cn],
        representative_evidence_ids=[f"ev-{native_dimension_id}"],
        support_summary_json=support_summary_json,
        service_context_flag=False,
        candidate_status=candidate_status,
        review_required=review_required,
        review_reason_json=review_reason_json or {},
        input_fingerprint=f"m084-input-{native_dimension_id}",
        result_hash=f"m084-result-{native_dimension_id}",
    )


def native_support(
    *,
    native_dimension_id: str,
    native_dimension_code: str,
    sku_code: str,
    product_anchor_score: Decimal,
    support_score: Decimal,
    support_level: str,
) -> entities.Core3NativeDimensionSkuSupport:
    return entities.Core3NativeDimensionSkuSupport(
        native_dimension_sku_support_id=f"support-{native_dimension_id}-{sku_code}",
        native_dimension_id=native_dimension_id,
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        sku_code=sku_code,
        model_name=sku_code,
        brand_name="海信",
        dimension_type="native_product_value_battlefield",
        native_dimension_code=native_dimension_code,
        comment_sentence_count=2,
        comment_support_score=Decimal("0.5000"),
        product_anchor_score=product_anchor_score,
        market_anchor_score=Decimal("0.3000"),
        support_score=support_score,
        support_level=support_level,
        evidence_breakdown_json={"fixture": True},
        representative_evidence_ids=[f"ev-{native_dimension_id}-{sku_code}"],
        support_reason_cn="本地夹具用于验证 M08.5 消费 M08.4 产品锚点质量。",
        input_fingerprint=f"support-input-{native_dimension_id}-{sku_code}",
        result_hash=f"support-result-{native_dimension_id}-{sku_code}",
    )


def native_alignment(
    *,
    native_dimension_id: str,
    native_dimension_code: str,
    native_dimension_name_cn: str,
    seed_dimension_code: str,
    seed_dimension_name_cn: str,
    alignment_score: Decimal,
) -> entities.Core3NativeDimensionAlignmentProposal:
    return entities.Core3NativeDimensionAlignmentProposal(
        alignment_proposal_id=f"alignment-{native_dimension_id}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        native_dimension_id=native_dimension_id,
        alignment_key=f"{native_dimension_code}->{seed_dimension_code}",
        seed_dimension_type="battlefield",
        seed_dimension_code=seed_dimension_code,
        seed_dimension_name_cn=seed_dimension_name_cn,
        native_dimension_code=native_dimension_code,
        native_dimension_name_cn=native_dimension_name_cn,
        alignment_relation="aligned_to_seed",
        alignment_score=alignment_score,
        proposed_action="merge_to_seed",
        reason_cn="本地夹具验证原生维度向预设战场对齐。",
        evidence_json={"fixture": True},
        downstream_effect_json={"fixture": True},
        review_required=False,
        review_status="auto_pass",
        seed_version="tv_core3_mvp_seed_v0_2",
        input_fingerprint=f"alignment-input-{native_dimension_id}",
        result_hash=f"alignment-result-{native_dimension_id}",
    )


def native_review_issue(
    *,
    issue_key: str,
    issue_code: str,
    object_code: str,
    issue_message_cn: str,
) -> entities.Core3NativeDimensionReviewIssue:
    return entities.Core3NativeDimensionReviewIssue(
        native_dimension_issue_id=f"issue-{issue_key}",
        project_id=PROJECT_ID,
        category_code="TV",
        batch_id=BATCH_ID,
        issue_key=issue_key,
        issue_code=issue_code,
        issue_type="anchor_quality",
        severity="warning",
        object_type="native_dimension",
        object_code=object_code,
        issue_message_cn=issue_message_cn,
        evidence_json={"fixture": True},
        suggested_action_cn="降级为候选或复核产品锚点。",
        review_status="open",
        input_fingerprint=f"issue-input-{issue_key}",
        result_hash=f"issue-result-{issue_key}",
    )


def downstream_signal(
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


def test_seed_loader_keeps_fixed_dimension_contract() -> None:
    seed = M085DimensionSeedLoader().load()

    assert len(seed.tasks) == 10
    assert len(seed.target_groups) == 9
    assert len(seed.battlefields) == 10
    assert seed.definition_seed_count == 29
    assert seed.battlefields[-1]["battlefield_code"] == "BF_SERVICE_ASSURANCE"
    assert seed.standard_claims
    assert seed.standard_params
    assert seed.comment_topics


def test_m08_5_generates_ontology_and_separates_service_context() -> None:
    session = make_session()
    seed_foundation(session)
    seed_m08_inputs(session)
    seed_m05_m06_inputs(session)
    seed_m08_4_inputs(session)

    result = M085DimensionOntologyRunner(session).run_batch(
        project_id=PROJECT_ID,
        batch_id=BATCH_ID,
        run_id="run-m085",
        module_run_id="module-run-m085",
    )

    assert result.module_code == "M08.5"
    assert result.status in {Core3RunStatus.SUCCESS, Core3RunStatus.WARNING}
    assert result.summary_json["input_sku_count"] == 2
    assert result.summary_json["usable_comment_atom_count"] == 2
    assert result.summary_json["definition_count"]["task"] == 10
    assert result.summary_json["definition_count"]["battlefield"] == 9
    assert result.summary_json["definition_count"]["service_context"] == 1
    assert result.summary_json["quality_summary"]["m08_4_native_candidate_count"] == 4
    assert result.summary_json["quality_summary"]["m08_4_alignment_count"] == 4

    definitions = session.execute(select(entities.Core3DimensionDefinition)).scalars().all()
    service_definition = next(item for item in definitions if item.dimension_code == "SERVICE_FULFILLMENT_ASSURANCE")
    assert service_definition.dimension_type == "service_context"
    assert service_definition.base_dimension_code == "BF_SERVICE_ASSURANCE"
    assert service_definition.boundary_policy == "service_context"
    assert service_definition.allocation_policy == "never_allocate"
    assert "BF_SERVICE_ASSURANCE" not in {
        item.dimension_code for item in definitions if item.dimension_type == "battlefield"
    }

    game_definition = next(item for item in definitions if item.dimension_code == "BF_GAMING_SPORTS")
    assert game_definition.dimension_type == "battlefield"
    assert game_definition.dimension_name_cn == "游戏体育流畅战场"
    assert game_definition.support_score > Decimal("0.0000")
    assert game_definition.support_score < Decimal("1.0000")
    assert game_definition.allocation_policy == "eligible_when_product_anchor_present"
    assert game_definition.required_evidence_json["market_pool_required_for_allocation"] is True
    assert game_definition.required_evidence_json["v2_definition"]["v2_code"] == "BF_GAMING_SPORTS_FLUENCY"
    assert game_definition.profile_eligibility_policy_json["requires_market_pool"] is True
    assert game_definition.profile_eligibility_policy_json["market_pool_policy"]["allowed_market_pool_fit"]["screen_size_classes"] == [
        "mainstream_living",
        "large_upgrade",
    ]
    assert game_definition.include_rule_json["market_pool_profile"]["market_pool_key_counts"] == {
        "TV|large_upgrade|online|latest_12m": 1
    }
    assert game_definition.include_rule_json["product_anchor_profile"]["strong_anchor_group_sku_counts"]["motion_gaming"] == 1
    assert game_definition.downstream_policy_json["allocation_eligible"] is True
    assert game_definition.downstream_policy_json["allocation_block_reasons"] == []
    assert game_definition.downstream_policy_json["dimension_role_policy"]["requires_product_anchor"] is True
    assert game_definition.downstream_policy_json["sku_relation_limits"]["secondary_per_sku_max"] == 2

    eye_definition = next(item for item in definitions if item.dimension_code == "BF_FAMILY_EYE_CARE")
    assert eye_definition.dimension_name_cn == "护眼舒适观看战场"
    assert eye_definition.allocation_policy == "candidate_only"
    assert eye_definition.downstream_policy_json["profile_eligible"] is False
    assert eye_definition.downstream_policy_json["allocation_eligible"] is False
    assert "product_anchor_weak" in eye_definition.downstream_policy_json["allocation_block_reasons"]

    audio_definition = next(item for item in definitions if item.dimension_code == "BF_CINEMA_AUDIO_IMMERSION")
    assert audio_definition.allocation_policy == "review_required"
    assert audio_definition.downstream_policy_json["profile_eligible"] is True
    assert audio_definition.downstream_policy_json["allocation_eligible"] is False
    assert "param_mapping_suspect" in audio_definition.downstream_policy_json["allocation_block_reasons"]
    assert "v2_anchor_to_parent_battlefield" in audio_definition.downstream_policy_json["allocation_block_reasons"]
    assert audio_definition.downstream_policy_json["v2_definition"]["migration_action"] == "anchor_to"

    senior_definition = next(item for item in definitions if item.dimension_code == "BF_SENIOR_EASE_OF_USE")
    assert senior_definition.downstream_policy_json["v2_definition"]["migration_action"] == "merge_to"
    assert senior_definition.downstream_policy_json["allocation_eligible"] is False
    assert "v2_merged_to_parent_battlefield" in senior_definition.downstream_policy_json["allocation_block_reasons"]

    design_definition = next(item for item in definitions if item.dimension_code == "BF_DESIGN_HOME_FIT")
    assert design_definition.boundary_policy == "diagnostic_only"
    assert design_definition.downstream_policy_json["v2_definition"]["migration_action"] == "context_only"
    assert design_definition.downstream_policy_json["allocation_eligible"] is False

    family_group_definition = next(item for item in definitions if item.dimension_code == "TG_FAMILY_UPGRADE")
    assert family_group_definition.downstream_policy_json["dimension_role_policy"]["requires_product_anchor"] is False
    assert "谁是主要购买人或使用人" in family_group_definition.downstream_policy_json["dimension_role_policy"]["answers"]

    living_task_definition = next(item for item in definitions if item.dimension_code == "TASK_LIVING_ROOM_CINEMA")
    assert living_task_definition.downstream_policy_json["dimension_role_policy"]["requires_market_pool"] is False
    assert "用户用这台电视完成什么" in living_task_definition.downstream_policy_json["dimension_role_policy"]["answers"]

    snapshots = session.execute(select(entities.Core3DimensionCandidateSnapshot)).scalars().all()
    service_snapshot = next(item for item in snapshots if item.signal_code == "installation_service")
    assert service_snapshot.sentence_count == 1
    assert service_snapshot.low_value_sentence_count == 0

    exclude_rules = (
        session.execute(
            select(entities.Core3DimensionMappingRule)
            .where(entities.Core3DimensionMappingRule.source_code == "installation_service")
            .where(entities.Core3DimensionMappingRule.mapping_level == "exclude")
            .where(entities.Core3DimensionMappingRule.target_dimension_type == "battlefield")
        )
        .scalars()
        .all()
    )
    assert exclude_rules
    assert all(rule.service_guardrail_flag for rule in exclude_rules)

    mapping_rules = session.execute(select(entities.Core3DimensionMappingRule)).scalars().all()
    game_mapping_levels = {
        rule.mapping_level for rule in mapping_rules if rule.target_dimension_code == "BF_GAMING_SPORTS"
    }
    assert "allocation_eligible" in game_mapping_levels
    motion_mapping_levels = {
        rule.mapping_level
        for rule in mapping_rules
        if rule.target_dimension_code == "BF_GAMING_SPORTS" and rule.source_code == "motion_compensation_flag"
    }
    assert motion_mapping_levels == {"candidate_trigger"}
    refresh_mapping_levels = {
        rule.mapping_level
        for rule in mapping_rules
        if rule.target_dimension_code == "BF_GAMING_SPORTS" and rule.source_code == "native_refresh_rate_hz"
    }
    assert "allocation_eligible" in refresh_mapping_levels
    eye_mapping_levels = {
        rule.mapping_level for rule in mapping_rules if rule.target_dimension_code == "BF_FAMILY_EYE_CARE"
    }
    assert "candidate_trigger" in eye_mapping_levels
    assert "profile_eligible" not in eye_mapping_levels
    assert "allocation_eligible" not in eye_mapping_levels
    audio_mapping_levels = {
        rule.mapping_level for rule in mapping_rules if rule.target_dimension_code == "BF_CINEMA_AUDIO_IMMERSION"
    }
    assert "profile_eligible" in audio_mapping_levels
    assert "allocation_eligible" not in audio_mapping_levels

    issues = session.execute(select(entities.Core3DimensionCalibrationIssue)).scalars().all()
    issue_codes = {issue.issue_code for issue in issues}
    assert "service_dimension_should_be_context" in issue_codes
    assert "product_anchor_weak" in issue_codes
    assert "param_mapping_suspect" in issue_codes
