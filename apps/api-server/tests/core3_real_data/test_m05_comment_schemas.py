from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.core3_real_data import (
    CommentDedupStrategy,
    CommentDomainHint,
    CommentEvidenceAtomRecord,
    CommentEvidenceAtomResponse,
    CommentLowValueReason,
    CommentQualityProfileRecord,
    CommentQualityProfileResponse,
    CommentReviewReasonCode,
    CommentSampleStatus,
    CommentSentenceCandidate,
    CommentSentimentHint,
    CommentSentimentSource,
    CommentTopicHintResponse,
    CommentTopicHintStatus,
    CommentTopicMatchMethod,
    CommentTopicSeed,
    CommentTopicSeedIndex,
    CommentUnitCandidate,
    CommentUnitEvidenceLinkRecord,
    CommentUnitRecord,
    CommentUnitSourceResponse,
    CommentUnitStatus,
    Core3CommentEvidenceRunApiRequest,
    Core3CommentSignalRunApiRequest,
    DomainHint,
    M05DownstreamImpact,
    M05EvidenceInput,
    M05ReviewIssue,
    M05RunRequest,
    M05RunResponse,
    M05RunResult,
    M05SkuInputBundle,
    SentimentHint,
    TopicHintRecord,
)
from app.services.core3_real_data.constants import (
    CORE3_M05_ALLOWED_EVIDENCE_TYPES,
    CORE3_M05_MODULE_VERSION,
    CORE3_M05_RULE_VERSION,
    CORE3_M05_SEED_VERSION,
    CORE3_M06_MODULE_VERSION,
    CORE3_M06_RULE_VERSION,
    CORE3_M06_SEED_VERSION,
    Core3ModuleCode,
    Core3ReviewSeverity,
    Core3RunStatus,
    Core3SourceImpactLevel,
)


CREATED_AT = "2026-06-13T00:00:00Z"
UPDATED_AT = "2026-06-13T00:00:01Z"
BASE_RECORD = {
    "project_id": "core3_mvp",
    "category_code": "TV",
    "batch_id": "m00_202606130001",
    "run_id": "run-m05",
    "module_run_id": "module-run-m05",
    "sku_code": "TV00029115",
    "model_name": "85E7Q",
    "brand_name": "海信",
    "created_at": CREATED_AT,
    "updated_at": UPDATED_AT,
}
FORBIDDEN_M05_BUSINESS_FIELDS = {
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "business_conclusion",
    "report_payload",
    "report_content",
    "rank",
    "score",
}


def test_m05_enums_and_constants_match_sop_contract():
    assert CORE3_M05_MODULE_VERSION == "m05-comment-evidence-0.1.0"
    assert CORE3_M05_SEED_VERSION == "tv_core3_mvp_seed_v0_2"
    assert CORE3_M05_RULE_VERSION == "m05_comment_evidence_v1"
    assert {item.value for item in CORE3_M05_ALLOWED_EVIDENCE_TYPES} == {
        "comment_raw",
        "comment_sentence",
        "comment_dimension",
        "quality_issue",
    }
    assert [item.value for item in CommentUnitStatus] == [
        "usable",
        "low_value",
        "duplicate_only",
        "blocked",
    ]
    assert [item.value for item in CommentDedupStrategy] == [
        "comment_id",
        "text_hash",
        "source_row_fallback",
    ]
    assert [item.value for item in CommentDomainHint] == [
        "product_experience",
        "product_risk",
        "market_perception",
        "service_experience",
        "logistics_installation",
        "unknown",
    ]
    assert [item.value for item in CommentSentimentHint] == [
        "positive",
        "negative",
        "neutral",
        "unknown",
        "conflict",
    ]
    assert [item.value for item in CommentSentimentSource] == [
        "raw_only",
        "text_rule",
        "raw_text_combined",
        "unknown",
    ]
    assert [item.value for item in CommentTopicMatchMethod] == [
        "keyword",
        "positive_keyword",
        "negative_keyword",
        "dimension_path",
        "phrase",
        "seed_rule",
    ]
    assert [item.value for item in CommentTopicHintStatus] == [
        "matched",
        "low_confidence",
        "blocked_low_value",
        "blocked_service_guardrail",
    ]
    assert [item.value for item in CommentSampleStatus] == [
        "sufficient",
        "limited",
        "insufficient",
        "unknown",
    ]
    assert {item.value for item in CommentLowValueReason} >= {
        "default_positive",
        "duplicate_only",
        "no_product_signal",
    }
    assert {item.value for item in CommentReviewReasonCode} >= {
        "low_confidence",
        "service_guardrail",
        "topic_seed_missing",
    }


def test_m05_run_request_result_and_api_defaults():
    request = M05RunRequest(project_id="core3_mvp", batch_id="m00_202606130001")
    api_request = Core3CommentEvidenceRunApiRequest(sku_scope=["TV00029115"])
    result = M05RunResult(
        batch_id="m00_202606130001",
        status=Core3RunStatus.WARNING,
        comment_unit_count=120,
        unit_link_count=240,
        evidence_atom_count=180,
        topic_hint_count=65,
        quality_profile_count=35,
        usable_sentence_count=96,
        downstream_ready_sku_count=20,
        review_required_count=4,
        review_required=True,
        warnings=["评论样本不足 SKU 需复核"],
    )
    response = M05RunResponse(
        result=result,
        summary_cn="M05 已生成评论基础证据层，弱主题仅作为后续抽取线索。",
        can_enter_next_stage=True,
        next_stage_note_cn="可进入 M06 评论下游信号抽取。",
    )

    assert request.model_dump() == {
        "project_id": "core3_mvp",
        "batch_id": "m00_202606130001",
        "category_code": "TV",
        "run_id": None,
        "module_run_id": None,
        "mode": "incremental",
        "module_version": CORE3_M05_MODULE_VERSION,
        "seed_version": CORE3_M05_SEED_VERSION,
        "rule_version": CORE3_M05_RULE_VERSION,
        "sku_scope": [],
        "force_rebuild": False,
        "triggered_by": "system",
    }
    assert api_request.model_dump()["sku_scope"] == ["TV00029115"]
    assert "project_id" not in api_request.model_dump()
    assert "batch_id" not in api_request.model_dump()
    assert result.model_dump()["module_code"] == "M05"
    assert response.can_enter_next_stage is True

    with pytest.raises(ValidationError):
        M05RunRequest(project_id="", batch_id="m00_202606130001")
    with pytest.raises(ValidationError, match="sku_scope"):
        M05RunRequest(project_id="core3_mvp", batch_id="m00_202606130001", sku_scope=[""])
    with pytest.raises(ValidationError):
        M05RunResult(batch_id="m00_202606130001", status="success", comment_unit_count=-1)


def test_m06_comment_signal_api_request_batches_by_sku():
    request = Core3CommentSignalRunApiRequest(sku_scope=["TV00029115"], sku_batch_size=2)

    assert request.model_dump() == {
        "run_id": None,
        "module_run_id": None,
        "category_code": "TV",
        "mode": "incremental",
        "module_version": CORE3_M06_MODULE_VERSION,
        "seed_version": CORE3_M06_SEED_VERSION,
        "rule_version": CORE3_M06_RULE_VERSION,
        "sku_scope": ["TV00029115"],
        "signal_types": [],
        "sku_batch_size": 2,
        "force_rebuild": False,
        "triggered_by": "system",
    }
    assert Core3CommentSignalRunApiRequest().sku_batch_size == 1

    with pytest.raises(ValidationError):
        Core3CommentSignalRunApiRequest(sku_batch_size=0)
    with pytest.raises(ValidationError):
        Core3CommentSignalRunApiRequest(sku_batch_size=21)


def test_m05_evidence_input_seed_and_bundle_contracts():
    evidence = M05EvidenceInput(
        evidence_id="m02ev_comment_sentence",
        evidence_key="comment_sentence:TV00029115:1",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        model_name="85E7Q",
        evidence_type="comment_sentence",
        evidence_field="sentence_text",
        source_row_id="comment-row-1",
        comment_id="comment-1",
        comment_text_hash="sha256:comment",
        segment_text_hash="sha256:sentence",
        sentence_seq=0,
        text_value="看球赛很流畅，运动画面不拖影。",
        base_confidence=Decimal("0.9000"),
    )
    seed = CommentTopicSeed(
        topic_code="comment_motion_smooth",
        topic_name="运动流畅",
        topic_group="product_experience",
        keywords=["流畅", "不拖影"],
        positive_keywords=["很流畅"],
        dimension_paths=["产品体验/画面流畅"],
        mapped_claim_codes=["claim_motion_smooth"],
        activates_product_claim=True,
        priority=10,
    )
    index = CommentTopicSeedIndex(topics=[seed])
    bundle = M05SkuInputBundle(
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        evidence_inputs=[evidence],
        input_fingerprint="sha256:m05:input",
    )

    assert evidence.model_dump()["evidence_type"] == "comment_sentence"
    assert index.topic_by_code["comment_motion_smooth"].topic_name == "运动流畅"
    assert bundle.evidence_inputs[0].evidence_id == "m02ev_comment_sentence"

    with pytest.raises(ValidationError, match="not allowed for M05"):
        M05EvidenceInput(
            evidence_id="m02ev_param",
            evidence_key="param:TV00029115",
            project_id="core3_mvp",
            batch_id="m00_202606130001",
            evidence_type="param_raw",
        )
    with pytest.raises(ValidationError, match="topic_code must be unique"):
        CommentTopicSeedIndex(topics=[seed, seed])
    with pytest.raises(ValidationError, match="mismatched sku_code"):
        M05SkuInputBundle(
            project_id="core3_mvp",
            batch_id="m00_202606130001",
            sku_code="TV00029115",
            evidence_inputs=[M05EvidenceInput(**{**evidence.model_dump(), "sku_code": "TV00010001"})],
            input_fingerprint="sha256:m05:input",
        )


def test_comment_unit_and_link_records_require_traceability_and_stop_at_m05_boundary():
    candidate = CommentUnitCandidate(
        sku_code="TV00029115",
        dedup_strategy=CommentDedupStrategy.TEXT_HASH,
        comment_text_hash="sha256:comment",
        source_evidence_ids=["m02ev_comment_raw"],
        canonical_comment_text="看球赛很流畅。",
        sentiment_hint=CommentSentimentHint.POSITIVE,
        confidence=Decimal("0.8000"),
    )
    unit = CommentUnitRecord(
        **BASE_RECORD,
        comment_unit_id="m05unit_85e7q_001",
        comment_unit_key="TV00029115:sha256:comment",
        dedup_strategy=CommentDedupStrategy.TEXT_HASH,
        comment_text_hash="sha256:comment",
        canonical_comment_text="看球赛很流畅。",
        canonical_text_length=8,
        source_row_count=1,
        source_sentence_count=1,
        source_comment_evidence_ids=["m02ev_comment_raw"],
        source_sentence_evidence_ids=["m02ev_comment_sentence"],
        sentiment_hint=CommentSentimentHint.POSITIVE,
        comment_unit_status=CommentUnitStatus.USABLE,
        confidence=Decimal("0.8000"),
        input_fingerprint="sha256:m05:unit:input",
        result_hash="sha256:m05:unit",
    )
    link = CommentUnitEvidenceLinkRecord(
        **BASE_RECORD,
        unit_link_id="m05link_001",
        comment_unit_id=unit.comment_unit_id,
        source_evidence_id="m02ev_comment_raw",
        source_evidence_type="comment_raw",
        link_role="raw_source",
        comment_text_hash="sha256:comment",
        input_fingerprint="sha256:m05:link:input",
        result_hash="sha256:m05:link",
    )

    assert candidate.model_dump()["dedup_strategy"] == "text_hash"
    assert unit.model_dump()["comment_unit_status"] == "usable"
    assert link.model_dump()["source_evidence_type"] == "comment_raw"
    assert_no_forbidden_business_fields(unit.model_dump())
    assert_no_forbidden_business_fields(link.model_dump())

    with pytest.raises(ValidationError, match="requires comment_id"):
        CommentUnitCandidate(sku_code="TV00029115", dedup_strategy="source_row_fallback")
    with pytest.raises(ValidationError, match="requires comment_id"):
        CommentUnitRecord(
            **{**BASE_RECORD, "comment_unit_id": "bad", "comment_unit_key": "bad"},
            dedup_strategy="source_row_fallback",
            input_fingerprint="sha256:bad:input",
            result_hash="sha256:bad",
        )
    with pytest.raises(ValidationError, match="not allowed for M05"):
        CommentUnitEvidenceLinkRecord(
            **{**link.model_dump(), "unit_link_id": "bad-link", "source_evidence_type": "param_raw"}
        )
    with pytest.raises(ValidationError):
        CommentUnitRecord(**{**unit.model_dump(), "battlefield_code": "battlefield_game_sport"})


def test_comment_atom_topic_quality_contracts_and_business_labels():
    domain_hint = DomainHint(
        domain_hint=CommentDomainHint.PRODUCT_EXPERIENCE,
        source_terms=["流畅"],
        confidence=Decimal("0.8500"),
        evidence_ids=["m02ev_comment_sentence"],
    )
    sentiment_hint = SentimentHint(
        sentiment_hint=CommentSentimentHint.POSITIVE,
        sentiment_source=CommentSentimentSource.TEXT_RULE,
        source_values=["很流畅"],
        confidence=Decimal("0.9000"),
    )
    sentence = CommentSentenceCandidate(
        comment_unit_id="m05unit_85e7q_001",
        comment_unit_key="TV00029115:sha256:comment",
        sku_code="TV00029115",
        sentence_seq=0,
        sentence_hash="sha256:sentence",
        sentence_text="看球赛很流畅，运动画面不拖影。",
        normalized_sentence_text="看球赛很流畅 运动画面不拖影",
        source_evidence_ids=["m02ev_comment_sentence"],
    )
    atom = CommentEvidenceAtomRecord(
        **BASE_RECORD,
        comment_evidence_id="m05atom_001",
        comment_evidence_key="TV00029115:sha256:sentence",
        comment_unit_id=sentence.comment_unit_id,
        comment_text_hash="sha256:comment",
        sentence_hash="sha256:sentence",
        sentence_seq=0,
        sentence_text=sentence.sentence_text,
        normalized_sentence_text=sentence.normalized_sentence_text,
        sentence_length=17,
        source_evidence_ids=["m02ev_comment_sentence"],
        source_sentence_evidence_ids=["m02ev_comment_sentence"],
        domain_hints=[domain_hint],
        primary_domain_hint=CommentDomainHint.PRODUCT_EXPERIENCE,
        sentiment_hint=sentiment_hint.sentiment_hint,
        sentiment_source=sentiment_hint.sentiment_source,
        specificity_score=Decimal("0.7000"),
        representative_phrase="运动画面不拖影",
        usable_for_downstream=True,
        confidence=Decimal("0.8500"),
        confidence_level="high",
        input_fingerprint="sha256:m05:atom:input",
        result_hash="sha256:m05:atom",
    )
    topic = TopicHintRecord(
        **BASE_RECORD,
        topic_hint_id="m05topic_001",
        comment_evidence_id=atom.comment_evidence_id,
        comment_unit_id=atom.comment_unit_id,
        topic_code="comment_motion_smooth",
        topic_name="运动流畅",
        topic_group="product_experience",
        match_method=CommentTopicMatchMethod.KEYWORD,
        matched_terms=["流畅", "不拖影"],
        polarity_hint=CommentSentimentHint.POSITIVE,
        topic_confidence=Decimal("0.7200"),
        is_weak_hint=True,
        activates_product_claim=True,
        mapped_claim_codes_snapshot=["claim_motion_smooth"],
        topic_hint_status=CommentTopicHintStatus.LOW_CONFIDENCE,
        input_fingerprint="sha256:m05:topic:input",
        result_hash="sha256:m05:topic",
    )
    profile = CommentQualityProfileRecord(
        **BASE_RECORD,
        comment_quality_profile_id="m05quality_001",
        profile_key="TV00029115:m05",
        raw_comment_row_count=20,
        comment_unit_count=18,
        distinct_comment_id_count=18,
        distinct_comment_text_count=17,
        sentence_count=22,
        usable_sentence_count=15,
        duplicate_text_rate=Decimal("0.050000"),
        sentiment_distribution_json={"positive": 10, "negative": 3, "unknown": 2},
        domain_distribution_json={"product_experience": 12, "service_experience": 3},
        topic_distribution_json={"comment_motion_smooth": 5},
        sample_status=CommentSampleStatus.SUFFICIENT,
        comment_usability_score=Decimal("0.720000"),
        downstream_ready=True,
        input_fingerprint="sha256:m05:quality:input",
        result_hash="sha256:m05:quality",
    )
    atom_response = CommentEvidenceAtomResponse(
        comment_evidence_id=atom.comment_evidence_id,
        comment_unit_id=atom.comment_unit_id,
        project_id=atom.project_id,
        batch_id=atom.batch_id,
        sku_code=atom.sku_code,
        sentence_text=atom.sentence_text,
        primary_domain_hint=atom.primary_domain_hint,
        sentiment_hint=atom.sentiment_hint,
        specificity_score=0.7,
        usable_for_downstream=True,
        confidence=0.85,
        confidence_level="high",
        source_evidence_count=1,
    )
    topic_response = CommentTopicHintResponse(
        topic_hint_id=topic.topic_hint_id,
        comment_evidence_id=topic.comment_evidence_id,
        comment_unit_id=topic.comment_unit_id,
        project_id=topic.project_id,
        batch_id=topic.batch_id,
        sku_code=topic.sku_code,
        topic_code=topic.topic_code,
        topic_name=topic.topic_name,
        topic_group=topic.topic_group,
        match_method=topic.match_method,
        matched_terms=topic.matched_terms,
        polarity_hint=topic.polarity_hint,
        topic_confidence=0.72,
        topic_hint_status=topic.topic_hint_status,
    )
    quality_response = CommentQualityProfileResponse(
        comment_quality_profile_id=profile.comment_quality_profile_id,
        project_id=profile.project_id,
        batch_id=profile.batch_id,
        sku_code=profile.sku_code,
        model_name=profile.model_name,
        raw_comment_row_count=profile.raw_comment_row_count,
        comment_unit_count=profile.comment_unit_count,
        sentence_count=profile.sentence_count,
        usable_sentence_count=profile.usable_sentence_count,
        duplicate_text_rate=0.05,
        sample_status=profile.sample_status,
        comment_usability_score=0.72,
        downstream_ready=profile.downstream_ready,
    )

    assert atom_response.primary_domain_hint_label_cn == "产品体验"
    assert atom_response.sentiment_hint_label_cn == "正向"
    assert topic_response.hint_type_label_cn == "基础线索"
    assert topic_response.topic_hint_status_label_cn == "弱提示，需谨慎使用"
    assert quality_response.sample_status_label_cn == "样本充足"
    assert quality_response.downstream_ready_label_cn == "可进入评论信号抽取"

    for payload in [atom.model_dump(), topic.model_dump(), profile.model_dump()]:
        assert_no_forbidden_business_fields(payload)

    with pytest.raises(ValidationError):
        CommentEvidenceAtomRecord(**{**atom.model_dump(), "source_evidence_ids": []})
    with pytest.raises(ValidationError, match="downstream_block_reasons"):
        CommentEvidenceAtomRecord(**{**atom.model_dump(), "usable_for_downstream": False})
    with pytest.raises(ValidationError, match="weak hints"):
        TopicHintRecord(**{**topic.model_dump(), "is_weak_hint": False})
    with pytest.raises(ValidationError, match="blocked_reasons"):
        CommentQualityProfileRecord(**{**profile.model_dump(), "downstream_ready": False, "blocked_reasons": []})
    with pytest.raises(ValidationError, match="usable_sentence_count"):
        CommentQualityProfileRecord(**{**profile.model_dump(), "usable_sentence_count": 30})


def test_m05_review_impact_and_api_responses_do_not_cross_future_module_boundary():
    review_issue = M05ReviewIssue(
        issue_code="m05_low_sample",
        reason_code=CommentReviewReasonCode.INSUFFICIENT_SAMPLE,
        severity=Core3ReviewSeverity.MEDIUM,
        object_type="sku_comment_quality",
        object_id="m05quality_001",
        sku_code="TV00029115",
        evidence_refs=["m05quality_001"],
        message_cn="评论样本有限，仅作为弱线索。",
    )
    impact = M05DownstreamImpact(
        target_module=Core3ModuleCode.M06,
        sku_code="TV00029115",
        impact_level=Core3SourceImpactLevel.MEDIUM,
        changed_object_count=3,
        reason_cn="评论基础证据变化，需要刷新评论下游信号。",
        evidence_refs=["m05atom_001"],
    )
    unit_response = CommentUnitSourceResponse(
        comment_unit_id="m05unit_85e7q_001",
        project_id="core3_mvp",
        batch_id="m00_202606130001",
        sku_code="TV00029115",
        canonical_comment_text="看球赛很流畅。",
        source_row_count=1,
        source_sentence_count=1,
        sentiment_hint=CommentSentimentHint.POSITIVE,
        low_value_flag=False,
        comment_unit_status=CommentUnitStatus.USABLE,
        confidence=0.8,
        confidence_level="high",
        source_evidence_count=2,
    )

    assert review_issue.model_dump()["reason_code"] == "insufficient_sample"
    assert impact.model_dump()["target_module"] == "M06"
    assert unit_response.sentiment_hint_label_cn == "正向"
    assert unit_response.comment_unit_status_label_cn == "可用于评论分析"

    for payload in [review_issue.model_dump(), impact.model_dump(), unit_response.model_dump()]:
        assert_no_forbidden_business_fields(payload)


def assert_no_forbidden_business_fields(payload):
    if isinstance(payload, dict):
        assert FORBIDDEN_M05_BUSINESS_FIELDS.isdisjoint(payload.keys())
        for value in payload.values():
            assert_no_forbidden_business_fields(value)
    elif isinstance(payload, list):
        for item in payload:
            assert_no_forbidden_business_fields(item)
