from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import entities
from app.services.core3_real_data.analyst.competitor_profile_generation import (
    CompetitorProfileGenerationService,
)
from app.services.core3_real_data.analyst.competitor_profile_reader import (
    CompetitorProfileReader,
    _business_mapping,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileReaderResult,
    CompetitorProfileReadRequest,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
    _default_spec,
)
from tests.core3_real_data.test_competitor_profile_generation import (
    _FixtureInputProvider,
    _repository,
    _request,
)


pytest_plugins = ("tests.core3_real_data.test_competitor_profile_generation",)


def _generated(session: Session):
    category = _category_bundle(specs=[_default_spec("TV", 1), _default_spec("TV", 2)])
    repository = _repository(session)
    readback = CompetitorProfileGenerationService(
        repository=repository,
        input_provider=_FixtureInputProvider(category),
    ).generate_draft(_request(category), target_sku_code="TV000001")
    return category, repository, readback


def test_formal_read_never_falls_back_to_a_draft(session: Session) -> None:
    category, repository, readback = _generated(session)
    result = CompetitorProfileReader(repository).read(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
        )
    )

    assert readback.persisted.preview is True
    assert result.status == "profile_unavailable"
    assert result.competitor_profile_version_id is None
    assert result.business is None


def test_preview_requires_explicit_opt_in_and_locks_one_version(session: Session) -> None:
    category, repository, readback = _generated(session)
    version_id = readback.persisted.version.competitor_profile_version_id
    with pytest.raises(ValidationError):
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
            mode="preview",
            competitor_profile_version_id=version_id,
        )

    result = CompetitorProfileReader(repository).read(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
            mode="preview",
            competitor_profile_version_id=version_id,
            allow_draft_preview=True,
        )
    )

    assert result.status == "available"
    assert result.preview is True
    assert result.competitor_profile_version_id == version_id
    assert result.evidence is not None
    assert result.evidence.competitor_profile_version_id == version_id


def test_business_dto_contains_business_labels_not_internal_snake_case(
    session: Session,
) -> None:
    category, repository, readback = _generated(session)
    result = CompetitorProfileReader(repository).read(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
            mode="preview",
            competitor_profile_version_id=(
                readback.persisted.version.competitor_profile_version_id
            ),
            allow_draft_preview=True,
        )
    )
    assert result.business is not None
    payload = result.business.model_dump(mode="json")

    def assert_business_keys(value) -> None:
        if isinstance(value, dict):
            assert all("_" not in key for key in value)
            assert all("hash" not in key.lower() for key in value)
            for child in value.values():
                assert_business_keys(child)
        elif isinstance(value, list):
            for child in value:
                assert_business_keys(child)

    assert_business_keys(payload)
    assert payload["目标产品"]
    assert "分析结论" in payload


def test_formal_read_returns_only_current_published_profile(session: Session) -> None:
    category, repository, readback = _generated(session)
    version_id = readback.persisted.version.competitor_profile_version_id
    now = datetime.now(timezone.utc)
    session.execute(
        update(entities.Core3CompetitorProfileVersion)
        .where(
            entities.Core3CompetitorProfileVersion.competitor_profile_version_id
            == version_id
        )
        .values(
            release_status="published",
            is_current=True,
            published_at=now,
            published_by="reviewer",
            current_at=now,
            current_by="reviewer",
        )
    )
    for model in (
        entities.Core3SkuCompetitorProfile,
        entities.Core3SkuCompetitorProfilePair,
        entities.Core3SkuCompetitorProfileRelation,
        entities.Core3SkuCompetitorProfileSelection,
    ):
        session.execute(
            update(model)
            .where(model.competitor_profile_version_id == version_id)
            .values(release_status="published", is_current=True)
        )
    session.commit()

    result = CompetitorProfileReader(repository).read(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
        )
    )

    assert result.status == "available"
    assert result.preview is False
    assert result.competitor_profile_version_id == version_id
    assert result.evidence is not None
    assert result.evidence.release_status == "published"


def test_reader_rejects_cross_scope_and_preview_version_mismatch(session: Session) -> None:
    category, repository, readback = _generated(session)
    reader = CompetitorProfileReader(repository)
    with pytest.raises(ValueError, match="project"):
        reader.read(
            CompetitorProfileReadRequest(
                project_id="another-project",
                category_code="TV",
                release_scope_key=category.serving_scope.release_scope_key,
                target_sku_code="TV000001",
            )
        )
    with pytest.raises(ValueError, match="category"):
        reader.read(
            CompetitorProfileReadRequest(
                project_id="project-tv",
                category_code="AC",
                release_scope_key=category.serving_scope.release_scope_key,
                target_sku_code="AC000001",
            )
        )
    with pytest.raises(ValueError, match="release scope"):
        reader.read(
            CompetitorProfileReadRequest(
                project_id="project-tv",
                category_code="TV",
                release_scope_key="another-scope",
                target_sku_code="TV000001",
                mode="preview",
                competitor_profile_version_id=(
                    readback.persisted.version.competitor_profile_version_id
                ),
                allow_draft_preview=True,
            )
        )


def test_reader_contract_rejects_partial_envelopes_and_translates_nested_rows() -> None:
    with pytest.raises(ValidationError):
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key="scope-tv",
            target_sku_code="TV000001",
            competitor_profile_version_id="draft-id",
        )
    with pytest.raises(ValidationError):
        CompetitorProfileReaderResult(
            status="profile_unavailable",
            competitor_profile_version_id="unexpected-id",
            message_cn="不可用",
        )

    translated = _business_mapping(
        {
            "causal_claim": False,
            "business_effect": {"effect_code": "purchase_choice_overlap"},
            "value_codes": ["clear_picture", {"decision": "evaluate_follow"}],
        }
    )
    assert "causal_claim" not in translated
    assert translated["对产品工作的影响"]["影响方式"] == (
        "进入同一批用户的最终选择"
    )
    assert translated["用户价值"][0] == "画质清晰"
    assert translated["用户价值"][1]["建议动作"] == "评估是否值得跟进"
