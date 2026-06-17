from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.constants import (
    CORE3_M09_SEED_VERSION,
    CORE3_M10_SEED_VERSION,
    Core3CategoryCode,
    M09TaskReviewIssueType,
    M10TargetGroupReviewIssueType,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.target_group_repositories import M10TargetGroupRepository
from app.services.core3_real_data.user_task_repositories import M09UserTaskRepository


def test_m09_review_issue_save_uses_stable_id_when_unique_key_misses(client):
    session = SessionLocal()
    try:
        repository = M09UserTaskRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m09_stable_id",
                category_code=Core3CategoryCode.TV,
            )
        )
        base_payload = {
            "sku_task_review_issue_id": "m09r_stable_issue",
            "project_id": "project_m09_stable_id",
            "category_code": "TV",
            "batch_id": "batch_m09",
            "sku_code": "TV_TEST",
            "task_code": "TASK_GAMING_SPORTS",
            "task_name_cn": "游戏与体育观看",
            "issue_type": M09TaskReviewIssueType.CLAIM_MISSING,
            "issue_severity": "warning",
            "issue_status": "open",
            "issue_reason_cn": "old input issue.",
            "issue_detail_json": {"input": "old"},
            "affected_output_json": {"task_code": "TASK_GAMING_SPORTS"},
            "evidence_refs_json": ["ev_1"],
            "suggested_action_cn": "review source evidence.",
            "rule_version": "old_rule",
            "task_seed_version": CORE3_M09_SEED_VERSION,
            "task_seed_file_version": "seed_file_v1",
            "task_seed_hash": "seed_hash",
            "profile_hash": "profile_hash",
            "feature_view_hash": "feature_hash",
            "input_fingerprint": "input_fp_old",
            "result_hash": "old_hash",
        }

        first = repository.save_review_issues([base_payload])
        rebuilt_payload = {
            **base_payload,
            "rule_version": "new_rule",
            "input_fingerprint": "input_fp_new",
            "issue_reason_cn": "rebuilt input issue.",
            "result_hash": "new_hash",
        }
        second = repository.save_review_issues([rebuilt_payload])
        third = repository.save_review_issues([rebuilt_payload])

        rows = list(session.execute(select(entities.Core3SkuTaskReviewIssue)).scalars())
        assert first.created_count == 1
        assert second.updated_count == 1
        assert third.reused_count == 1
        assert len(rows) == 1
        assert rows[0].sku_task_review_issue_id == "m09r_stable_issue"
        assert rows[0].rule_version == "new_rule"
        assert rows[0].input_fingerprint == "input_fp_new"
    finally:
        session.close()


def test_m10_review_issue_save_uses_stable_id_when_unique_key_misses(client):
    session = SessionLocal()
    try:
        repository = M10TargetGroupRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m10_stable_id",
                category_code=Core3CategoryCode.TV,
            )
        )
        base_payload = {
            "sku_target_group_review_issue_id": "m10r_stable_issue",
            "project_id": "project_m10_stable_id",
            "category_code": "TV",
            "batch_id": "batch_m10",
            "sku_code": "TV_TEST",
            "target_group_code": "TG_GAMER",
            "target_group_name_cn": "游戏玩家",
            "issue_type": M10TargetGroupReviewIssueType.MISSING_TASK_SCORE,
            "issue_severity": "warning",
            "issue_status": "open",
            "issue_reason_cn": "old input issue.",
            "issue_detail_json": {"input": "old"},
            "affected_output_json": {"target_group_code": "TG_GAMER"},
            "evidence_ids": ["ev_1"],
            "suggested_action_cn": "review source evidence.",
            "profile_hash": "profile_hash",
            "feature_view_hash": "feature_hash",
            "task_score_fingerprint": "task_fp",
            "target_group_seed_version": CORE3_M10_SEED_VERSION,
            "target_group_seed_file_version": "seed_file_v1",
            "target_group_seed_hash": "seed_hash",
            "rule_version": "old_rule",
            "input_fingerprint": "input_fp_old",
            "result_hash": "old_hash",
        }

        first = repository.save_review_issues([base_payload])
        rebuilt_payload = {
            **base_payload,
            "rule_version": "new_rule",
            "input_fingerprint": "input_fp_new",
            "issue_reason_cn": "rebuilt input issue.",
            "result_hash": "new_hash",
        }
        second = repository.save_review_issues([rebuilt_payload])
        third = repository.save_review_issues([rebuilt_payload])

        rows = list(session.execute(select(entities.Core3SkuTargetGroupReviewIssue)).scalars())
        assert first.created_count == 1
        assert second.updated_count == 1
        assert third.reused_count == 1
        assert len(rows) == 1
        assert rows[0].sku_target_group_review_issue_id == "m10r_stable_issue"
        assert rows[0].rule_version == "new_rule"
        assert rows[0].input_fingerprint == "input_fp_new"
    finally:
        session.close()
