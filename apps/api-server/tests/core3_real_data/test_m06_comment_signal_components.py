from decimal import Decimal

from app.services.core3_real_data.comment_downstream_signal_schemas import (
    CommentEntityExtraction,
    M06CommentAtomInput,
    M06QualityProfileInput,
    M06SkuInputBundle,
    M06TopicHintInput,
    SignalExtractionContext,
)
from app.services.core3_real_data.comment_downstream_signal_repositories import (
    CommentSignalRepositoryWriteResult,
)
from app.services.core3_real_data.comment_downstream_signal_service import (
    CommentDownstreamSignalService,
)
from app.services.core3_real_data.comment_entity_extractor import CommentEntityExtractor
from app.services.core3_real_data.comment_signal_extractors import ClaimValidationSignalExtractor
from app.services.core3_real_data.comment_signal_seed_loader import CommentSignalSeedLoader
from app.services.core3_real_data.constants import (
    COMMENT_SIGNAL_TARGET_PREFIX,
    CORE3_M06_FORBIDDEN_OUTPUT_FIELDS,
    CommentDomainHint,
    CommentSentimentHint,
    CommentSignalType,
)
from app.models import entities


class _M06FakeRepository:
    def __init__(self):
        self.candidates = []
        self.signals = []
        self.profile = None

    def _mark_previous_inactive(self, *args, **kwargs):
        return 0

    def bulk_upsert_candidates(self, records):
        self.candidates = list(records)
        return CommentSignalRepositoryWriteResult(records=tuple(records), created_count=len(records))

    def bulk_upsert_signals(self, records):
        self.signals = list(records)
        return CommentSignalRepositoryWriteResult(records=tuple(records), created_count=len(records))

    def upsert_profile(self, record):
        self.profile = record
        return CommentSignalRepositoryWriteResult(records=(record,), created_count=1)


def test_m06_seed_loader_covers_all_downstream_signal_targets():
    result = CommentSignalSeedLoader().load()

    assert result.target_counts == {
        "claim_validation": 20,
        "task_cue": 10,
        "target_group_cue": 9,
        "battlefield_support": 10,
        "pain_point": 8,
        "price_perception": 5,
        "service_signal": 6,
    }
    for signal_type, targets in result.seed.targets.items():
        expected_prefix = COMMENT_SIGNAL_TARGET_PREFIX[signal_type]
        assert targets
        assert all(target.code.startswith(expected_prefix) for target in targets)


def test_m06_entity_extractor_splits_business_entities_for_downstream_use():
    extracted = CommentEntityExtractor().extract("给父母买放客厅，看球不卡，语音很方便，价格也划算。")

    assert "父母" in extracted.people
    assert "客厅" in extracted.scenarios
    assert "看球" in extracted.actions
    assert "不卡" in extracted.experience_results
    assert "语音" in extracted.actions
    assert "划算" in extracted.price_terms


def test_service_comment_does_not_become_product_claim_validation():
    seed = CommentSignalSeedLoader().load().seed
    atom = M06CommentAtomInput(
        comment_evidence_id="m05-atom-service",
        comment_unit_id="m05-unit-service",
        sku_code="TV900001",
        sentence_text="安装师傅很专业，挂装很快。",
        normalized_sentence_text="安装师傅很专业，挂装很快。",
        specificity_score=Decimal("0.7000"),
        sentiment_hint=CommentSentimentHint.POSITIVE,
        primary_domain_hint=CommentDomainHint.LOGISTICS_INSTALLATION,
        source_m05_evidence_ids=["m05-atom-service"],
        source_m02_evidence_ids=["m02-comment-service"],
        result_hash="sha256:test:m05-service",
    )
    topic = M06TopicHintInput(
        topic_hint_id="topic-service",
        comment_evidence_id=atom.comment_evidence_id,
        comment_unit_id=atom.comment_unit_id,
        topic_code="TOPIC_INSTALLATION_SERVICE",
        topic_name="安装服务",
        topic_group="logistics_installation",
        matched_terms=["安装", "师傅"],
        polarity_hint=CommentSentimentHint.POSITIVE,
        topic_confidence=Decimal("0.8000"),
        service_guardrail_flag=True,
        mapped_claim_codes_snapshot=["CLAIM_INSTALLATION_SERVICE_ASSURANCE", "CLAIM_LARGE_SCREEN_IMMERSION"],
        result_hash="sha256:test:topic-service",
    )
    bundle = M06SkuInputBundle(
        project_id="core3_mvp",
        batch_id="m00_test",
        sku_code="TV900001",
        quality_profile=M06QualityProfileInput(
            sku_code="TV900001",
            comment_unit_count=1,
            usable_sentence_count=1,
            comment_usability_score=Decimal("0.800000"),
            downstream_ready=True,
            result_hash="sha256:test:profile",
        ),
        atoms=[atom],
        topic_hints_by_atom={atom.comment_evidence_id: [topic]},
        input_fingerprint="sha256:test:m06-input",
    )
    context = SignalExtractionContext(
        bundle=bundle,
        atom=atom,
        topic_hints=[topic],
        entities=CommentEntityExtractor().extract(atom.sentence_text),
        seed=seed,
    )

    candidates = ClaimValidationSignalExtractor().extract(context, run_id=None, module_run_id=None)
    service_candidate = next(item for item in candidates if item.target_code_hint == "CLAIM_INSTALLATION_SERVICE_ASSURANCE")
    product_candidate = next(item for item in candidates if item.target_code_hint == "CLAIM_LARGE_SCREEN_IMMERSION")

    assert service_candidate.service_guardrail_flag is True
    assert service_candidate.eligible_for_service_claim is True
    assert service_candidate.eligible_for_product_claim is False
    assert product_candidate.eligible_for_product_claim is False
    assert "service_to_product_claim_blocked" in product_candidate.blocked_reasons


def test_m06_tables_do_not_expose_final_business_conclusion_fields():
    m06_columns = {
        *entities.Core3CommentSignalCandidate.__table__.columns.keys(),
        *entities.Core3CommentDownstreamSignal.__table__.columns.keys(),
        *entities.Core3SkuCommentSignalProfile.__table__.columns.keys(),
    }

    assert not (m06_columns & set(CORE3_M06_FORBIDDEN_OUTPUT_FIELDS))
    assert "signal_type" in entities.Core3CommentSignalCandidate.__table__.columns
    assert "target_code_hint" in entities.Core3CommentDownstreamSignal.__table__.columns


def test_m06_service_respects_signal_type_scope():
    seed = CommentSignalSeedLoader().load().seed
    atom = M06CommentAtomInput(
        comment_evidence_id="m05-atom-task",
        comment_unit_id="m05-unit-task",
        sku_code="TV900001",
        sentence_text="给父母买放客厅，看球不卡，语音很方便，价格也划算。",
        normalized_sentence_text="给父母买放客厅，看球不卡，语音很方便，价格也划算。",
        specificity_score=Decimal("0.8200"),
        sentiment_hint=CommentSentimentHint.POSITIVE,
        primary_domain_hint=CommentDomainHint.PRODUCT_EXPERIENCE,
        source_m05_evidence_ids=["m05-atom-task"],
        source_m02_evidence_ids=["m02-comment-task"],
        result_hash="sha256:test:m05-task",
    )
    topic = M06TopicHintInput(
        topic_hint_id="topic-task",
        comment_evidence_id=atom.comment_evidence_id,
        comment_unit_id=atom.comment_unit_id,
        topic_code="TOPIC_SPORTS_MOTION",
        topic_name="体育流畅",
        topic_group="product_experience",
        matched_terms=["看球", "不卡", "语音", "划算"],
        polarity_hint=CommentSentimentHint.POSITIVE,
        topic_confidence=Decimal("0.8600"),
        mapped_claim_codes_snapshot=["CLAIM_SPORTS_MOTION_SMOOTH"],
        mapped_task_codes_snapshot=["TASK_SPORTS_WATCHING", "TASK_SENIOR_EASY_USE", "TASK_VALUE_PURCHASE"],
        mapped_battlefield_codes_snapshot=["BF_GAMING_SPORTS"],
        result_hash="sha256:test:topic-task",
    )
    bundle = M06SkuInputBundle(
        project_id="core3_mvp",
        batch_id="m00_test",
        sku_code="TV900001",
        quality_profile=M06QualityProfileInput(
            sku_code="TV900001",
            comment_unit_count=1,
            usable_sentence_count=1,
            comment_usability_score=Decimal("0.880000"),
            downstream_ready=True,
            result_hash="sha256:test:profile-task",
        ),
        atoms=[atom],
        topic_hints_by_atom={atom.comment_evidence_id: [topic]},
        input_fingerprint="sha256:test:m06-task-input",
    )
    repository = _M06FakeRepository()

    result = CommentDownstreamSignalService(repository, seed=seed).process_bundle(
        bundle,
        signal_types=[CommentSignalType.TASK_CUE],
    )

    assert result.candidates
    assert result.downstream_signals
    assert {CommentSignalType(item.signal_type) for item in result.candidates} == {CommentSignalType.TASK_CUE}
    assert {CommentSignalType(item.signal_type) for item in result.downstream_signals} == {CommentSignalType.TASK_CUE}
    assert result.summary["filtered_signal_types"] == ["task_cue"]
    assert repository.candidates == result.candidates
    assert repository.signals == result.downstream_signals
