from app.services.core3_real_data.comment_evidence_repositories import CommentEvidenceReadRepository
from app.services.core3_real_data.comment_evidence_service import CommentEvidenceService
from app.services.core3_real_data.comment_topic_seed_loader import CommentTopicSeedLoader

from .test_m05_comment_repositories import make_context, make_session
from .test_m05_comment_topic_hint_matcher import (
    BATCH_ID,
    PROJECT_ID,
    SKU_CODE,
    assert_no_forbidden_business_fields,
    bundle,
    evidence_input,
)


RUN_ID = "run-m05-n"
MODULE_RUN_ID = "module-run-m05-n"


def test_comment_evidence_service_orchestrates_and_persists_m05_outputs():
    session = make_session()
    repository = CommentEvidenceReadRepository(make_context(session))
    service = CommentEvidenceService(
        repository,
        topic_seed=CommentTopicSeedLoader().load_seed(),
        target_sku_expected_comment_units={SKU_CODE: 1},
    )
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_raw",
                text_value="游戏模式延迟低，玩主机很流畅。",
                payload={"sentiment_clean": "正面"},
            ),
            evidence_input(
                "ev_sentence",
                evidence_type="comment_sentence",
                evidence_field="comment_sentence:0",
                segment_text_hash="sha256:sentence:gaming",
                sentence_seq=0,
                text_value="游戏模式延迟低，玩主机很流畅",
            ),
            evidence_input(
                "ev_dimension",
                evidence_type="comment_dimension",
                evidence_field="comment_dimension",
                dimension_path_raw="产品体验/游戏流畅",
                text_value="产品体验/游戏流畅",
            ),
        ]
    )

    result = service.process_bundle(sku_bundle, run_id=RUN_ID, module_run_id=MODULE_RUN_ID)

    assert result.input_count == 3
    assert len(result.comment_units) == 1
    assert len(result.unit_links) == 3
    assert len(result.sentence_atoms) == 1
    assert result.quality_profile.downstream_ready is True
    assert result.blocked is False
    assert result.topic_hints
    assert "TOPIC_GAMING_SMOOTHNESS" in {hint.topic_code for hint in result.topic_hints}
    assert result.write_summary["comment_units"]["created_count"] == 1
    assert result.write_summary["sentence_atoms"]["created_count"] == 1
    assert result.write_summary["quality_profiles"]["created_count"] == 1
    assert result.summary["comment_unit_count"] == 1
    assert result.summary["unit_link_count"] == 3
    assert result.summary["seed_loaded"] is True
    assert result.summary["m02_comment_trace_ready"] is True
    assert_no_forbidden_business_fields(result.summary)

    persisted_units = repository.list_current_units(BATCH_ID, SKU_CODE)
    persisted_atoms = repository.list_current_atoms(BATCH_ID, SKU_CODE, usable_for_downstream=True)
    persisted_topic_hints = repository.list_current_topic_hints(
        BATCH_ID,
        SKU_CODE,
        topic_code="TOPIC_GAMING_SMOOTHNESS",
    )
    persisted_profile = repository.get_current_profile(BATCH_ID, SKU_CODE)
    persisted_links = repository.list_links_by_unit(persisted_units[0].comment_unit_id)

    assert [unit.comment_unit_id for unit in persisted_units] == [result.comment_units[0].comment_unit_id]
    assert [atom.comment_evidence_id for atom in persisted_atoms] == [
        result.sentence_atoms[0].comment_evidence_id
    ]
    assert persisted_topic_hints
    assert persisted_profile is not None
    assert persisted_profile.comment_quality_profile_id == result.quality_profile.comment_quality_profile_id
    assert len(persisted_links) == 3


def test_comment_evidence_service_reuses_current_outputs_on_repeat_run():
    session = make_session()
    repository = CommentEvidenceReadRepository(make_context(session))
    service = CommentEvidenceService(
        repository,
        topic_seed=CommentTopicSeedLoader().load_seed(),
        target_sku_expected_comment_units={SKU_CODE: 1},
    )
    sku_bundle = bundle(
        [
            evidence_input(
                "ev_raw",
                text_value="画质清晰，游戏模式延迟低。",
                payload={"sentiment_clean": "正面"},
            )
        ]
    )

    first = service.process_bundle(sku_bundle, run_id=RUN_ID, module_run_id=MODULE_RUN_ID)
    second = service.process_bundle(sku_bundle, run_id=RUN_ID, module_run_id=MODULE_RUN_ID)

    assert first.write_summary["comment_units"]["created_count"] == 1
    assert second.write_summary["comment_units"]["reused_count"] == 1
    assert second.write_summary["sentence_atoms"]["reused_count"] == 1
    assert second.write_summary["quality_profiles"]["reused_count"] == 1
    assert second.write_summary["previous_outputs_inactivated"]["updated_count"] >= 3
    assert second.write_summary["unit_links_deleted"]["deleted_count"] >= 1
    assert len(repository.list_current_units(BATCH_ID, SKU_CODE)) == 1
    assert len(repository.list_current_atoms(BATCH_ID, SKU_CODE)) == 1
    assert repository.get_current_profile(BATCH_ID, SKU_CODE) is not None


def test_comment_evidence_service_blocks_empty_comment_bundle_with_quality_profile():
    session = make_session()
    repository = CommentEvidenceReadRepository(make_context(session))
    service = CommentEvidenceService(
        repository,
        topic_seed=CommentTopicSeedLoader().load_seed(),
        target_sku_expected_comment_units={SKU_CODE: 1},
    )
    empty_bundle = bundle([])

    result = service.process_bundle(empty_bundle, run_id=RUN_ID, module_run_id=MODULE_RUN_ID)

    assert result.input_count == 0
    assert result.comment_units == []
    assert result.sentence_atoms == []
    assert result.topic_hints == []
    assert result.blocked is True
    assert result.review_required is True
    assert result.quality_profile.downstream_ready is False
    assert set(result.quality_profile.blocked_reasons) == {"no_comment_unit", "no_sentence_atom"}
    assert "m05_no_comment_unit" in result.warnings
    assert "m05_m02_comment_trace_missing" in result.warnings
    assert result.write_summary["quality_profiles"]["created_count"] == 1
    assert repository.get_current_profile(BATCH_ID, SKU_CODE) is not None
    assert_no_forbidden_business_fields(result.summary)

