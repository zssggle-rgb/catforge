from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.services.core3_real_data.analyst.competitor_profile_consumption import (
    CompetitorProfileConsumptionService,
)
from app.services.core3_real_data.analyst.competitor_profile_consumption_schemas import (
    COMPETITOR_PROFILE_CONSUMERS,
    CompetitorProfileConsumptionContext,
)
from app.services.core3_real_data.analyst.competitor_profile_reader import (
    CompetitorProfileReader,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileReadRequest,
)
from tests.core3_real_data.test_competitor_profile_reader import _generated


pytest_plugins = ("tests.core3_real_data.test_competitor_profile_generation",)


class _CountingReader(CompetitorProfileReader):
    calls = 0

    def read(self, request):
        self.calls += 1
        return super().read(request)


def test_consumers_share_one_explicit_preview_read_and_version(session) -> None:
    category, repository, readback = _generated(session)
    version_id = readback.persisted.version.competitor_profile_version_id
    reader = _CountingReader(repository)
    context = CompetitorProfileConsumptionService(reader).load(
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

    assert reader.calls == 1
    assert context.status == "available"
    assert context.competitor_profile_version_id == version_id
    assert context.consumers == list(COMPETITOR_PROFILE_CONSUMERS)
    assert context.evidence is not None
    assert context.evidence.competitor_profile_version_id == version_id


def test_formal_unavailable_does_not_fall_back_or_enable_consumers(session) -> None:
    category, repository, _ = _generated(session)
    context = CompetitorProfileConsumptionService(
        CompetitorProfileReader(repository)
    ).load(
        CompetitorProfileReadRequest(
            project_id="project-tv",
            category_code="TV",
            release_scope_key=category.serving_scope.release_scope_key,
            target_sku_code="TV000001",
        )
    )

    assert context.status == "profile_unavailable"
    assert context.consumers == []
    assert context.business is None
    assert context.evidence is None


def test_consumption_contract_rejects_split_or_partial_versions() -> None:
    with pytest.raises(ValidationError):
        CompetitorProfileConsumptionContext(
            status="available",
            competitor_profile_version_id="version-a",
            consumers=list(COMPETITOR_PROFILE_CONSUMERS),
            message_cn="已读取",
        )
    with pytest.raises(ValidationError):
        CompetitorProfileConsumptionContext(
            status="profile_unavailable",
            competitor_profile_version_id="unexpected",
            message_cn="不可用",
        )
