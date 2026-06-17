from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import entities
from app.services.core3_real_data.battlefield_repositories import M11BattlefieldRepository
from app.services.core3_real_data.constants import (
    CORE3_M11_SEED_VERSION,
    Core3CategoryCode,
    M11BattlefieldEvidenceDomain,
)
from app.services.core3_real_data.repositories import Core3RepositoryContext


def test_m11_breakdown_save_uses_stable_id_when_unique_key_misses(client):
    session = SessionLocal()
    try:
        repository = M11BattlefieldRepository(
            Core3RepositoryContext(
                db=session,
                project_id="project_m11_stable_id",
                category_code=Core3CategoryCode.TV,
            )
        )
        base_payload = {
            "sku_battlefield_evidence_breakdown_id": "m11b_stable_breakdown",
            "project_id": "project_m11_stable_id",
            "category_code": "TV",
            "batch_id": "batch_m11",
            "sku_code": "TV_TEST",
            "battlefield_code": "BF_PREMIUM_PICTURE",
            "battlefield_name_cn": "高端画质战场",
            "evidence_domain": M11BattlefieldEvidenceDomain.MARKET,
            "support_level": "medium",
            "domain_score": Decimal("0.5000"),
            "domain_weight": Decimal("0.3000"),
            "weighted_score": Decimal("0.1500"),
            "evidence_count": 1,
            "evidence_ids": ["ev_1"],
            "source_feature_refs_json": [{"source": "test"}],
            "domain_reason_cn": "旧规则生成的市场证据。",
            "domain_risk_json": {},
            "profile_hash": "profile_hash",
            "feature_view_hash": "feature_hash",
            "task_score_fingerprint": "task_fp",
            "target_group_score_fingerprint": "group_fp",
            "battlefield_seed_version": CORE3_M11_SEED_VERSION,
            "battlefield_seed_file_version": "seed_file_v1",
            "battlefield_seed_hash": "seed_hash",
            "rule_version": "old_rule",
            "input_fingerprint": "input_fp",
            "result_hash": "old_hash",
        }

        first = repository.save_breakdowns([base_payload])
        rebuilt_payload = {
            **base_payload,
            "rule_version": "new_rule",
            "domain_reason_cn": "重跑后生成的市场证据。",
            "result_hash": "new_hash",
        }
        second = repository.save_breakdowns([rebuilt_payload])
        third = repository.save_breakdowns([rebuilt_payload])

        rows = list(session.execute(select(entities.Core3SkuBattlefieldEvidenceBreakdown)).scalars())
        assert first.created_count == 1
        assert second.updated_count == 1
        assert third.reused_count == 1
        assert len(rows) == 1
        assert rows[0].sku_battlefield_evidence_breakdown_id == "m11b_stable_breakdown"
        assert rows[0].rule_version == "new_rule"
        assert rows[0].domain_reason_cn == "重跑后生成的市场证据。"
    finally:
        session.close()
