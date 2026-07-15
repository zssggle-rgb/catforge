from __future__ import annotations

from typing import Any

import pytest

from app.cli import catforge_analyst
from app.services.core3_real_data.analyst import competitor_answer
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.analyst_service import (
    CatForgeAnalystService,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_pair_analysis import (
    PairAnalysisCalculator,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_persistence_schemas import (
    CompetitorProfileV11ReadResult,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_reader import (
    CompetitorProfileV11ReadRequest,
    CompetitorProfileV11Reader,
)
from app.services.core3_real_data.analyst.competitor_profile_v1_1_selection import (
    CompetitorProfileV11Selector,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from tests.core3_real_data.test_catforge_analyst_cli import make_session
from tests.core3_real_data.test_competitor_profile_v1_1_adapter import (
    _hard_excluded_dto,
    _market_only_dto,
    _materialize,
)
from tests.core3_real_data.test_competitor_profile_v1_1_gate_evaluation import (
    PairGateEvaluator,
)
from tests.core3_real_data.test_competitor_profile_v1_1_materializer_generation import (
    _twenty_candidate_65e7q_item,
    _work_item,
)
from tests.core3_real_data.test_competitor_profile_v1_1_repository import (
    _zero_candidate_dto,
)


class ForbiddenAtomicHandlers:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"profile route attempted AtomicHandlers.{name}")


class ResolverOnlyAtomicHandlers(ForbiddenAtomicHandlers):
    def __init__(self, target_sku_code: str) -> None:
        self.target_sku_code = target_sku_code
        self.calls: list[str] = []

    def resolve_sku(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append("resolve-sku")
        return {
            "status": "ok",
            "command": "resolve-sku",
            "target": {"sku_code": self.target_sku_code},
        }


class FakeReader:
    def __init__(self, result: CompetitorProfileV11ReadResult) -> None:
        self.result = result
        self.requests: list[CompetitorProfileV11ReadRequest] = []

    def read(
        self, request: CompetitorProfileV11ReadRequest
    ) -> CompetitorProfileV11ReadResult:
        self.requests.append(request)
        return self.result


def _available_read(dto: Any, *, preview: bool = False) -> CompetitorProfileV11ReadResult:
    return CompetitorProfileV11ReadResult(
        status="available",
        read_mode="full",
        preview=preview,
        competitor_profile_version_id=(
            dto.profile_version.competitor_profile_version_id
        ),
        full=dto,
    )


def _context(dto: Any) -> AnalystContext:
    return AnalystContext(
        project_id=dto.profile_version.project_id,
        category_code=dto.profile_version.category_code,
        batch_id="latest",
        product_category=dto.profile_version.product_category,
    )


def _run_profile(
    dto: Any,
    *,
    preview: bool = False,
    atomic_handlers: Any | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], FakeReader]:
    reader = FakeReader(_available_read(dto, preview=preview))
    orchestrator = SopOrchestrators(
        atomic_handlers or ForbiddenAtomicHandlers(),  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )
    release_scope_key = kwargs.pop(
        "competitor_profile_release_scope_key",
        dto.profile_version.release_scope_key,
    )
    result = orchestrator.competitor_set(
        _context(dto),
        sku_code=dto.target_snapshot.identity_market.sku_code,
        answer_style="xiaoao",
        competitor_profile_release_scope_key=release_scope_key,
        **kwargs,
    )
    return result, reader


@pytest.mark.parametrize("category", ["TV", "AC"])
def test_formal_agent_reads_one_saved_profile_and_preserves_saved_order(
    category: str,
) -> None:
    dto = _materialize(_work_item(category))

    result, reader = _run_profile(dto)

    assert result["status"] == "ok"
    assert len(reader.requests) == 1
    request = reader.requests[0]
    assert request.access_mode == "formal"
    assert request.read_mode == "full"
    assert request.competitor_profile_version_id is None
    assert request.allow_draft_preview is False
    payload = result["result"]["competitor_set"]
    assert payload["source"] == "competitor_profile_v1_1"
    assert payload["competitor_profile_version_id"] == (
        dto.profile_version.competitor_profile_version_id
    )
    assert payload["saved_priority_order"] == [
        row.candidate_sku_code for row in dto.priority_selections
    ]
    assert [row["candidate"]["sku_code"] for row in payload["candidates"]] == [
        row.candidate_sku_code
        for row in sorted(dto.pair_analyses, key=lambda item: item.recall_rank)
        if row.scope_status != "excluded"
    ]
    assert result["atoms_used"] == []


def test_preview_requires_explicit_version_and_opt_in_and_locks_one_version() -> None:
    dto = _materialize(_work_item())
    reader = FakeReader(_available_read(dto, preview=True))
    orchestrator = SopOrchestrators(
        ForbiddenAtomicHandlers(),  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )
    common = {
        "sku_code": dto.target_snapshot.identity_market.sku_code,
        "competitor_profile_release_scope_key": (
            dto.profile_version.release_scope_key
        ),
    }

    with pytest.raises(ValueError, match="preview reads require"):
        orchestrator.competitor_set(
            _context(dto),
            profile_access_mode="preview",
            **common,
        )
    with pytest.raises(ValueError, match="formal reads cannot"):
        orchestrator.competitor_set(
            _context(dto),
            competitor_profile_version_id=(
                dto.profile_version.competitor_profile_version_id
            ),
            **common,
        )

    result = orchestrator.competitor_set(
        _context(dto),
        profile_access_mode="preview",
        competitor_profile_version_id=(
            dto.profile_version.competitor_profile_version_id
        ),
        allow_draft_preview=True,
        **common,
    )

    assert result["status"] == "ok"
    assert len(reader.requests) == 1
    assert reader.requests[0].competitor_profile_version_id == (
        result["result"]["competitor_set"]["competitor_profile_version_id"]
    )


def test_formal_agent_can_resolve_the_activated_current_without_internal_scope_key() -> (
    None
):
    dto = _materialize(_work_item())
    reader = FakeReader(_available_read(dto))
    orchestrator = SopOrchestrators(
        ForbiddenAtomicHandlers(),  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )

    result = orchestrator.competitor_set(
        _context(dto),
        sku_code=dto.target_snapshot.identity_market.sku_code,
    )

    assert result["status"] == "ok"
    assert reader.requests[0].release_scope_key is None
    assert result["result"]["competitor_set"][
        "competitor_profile_release_scope_key"
    ] == dto.profile_version.release_scope_key


def test_profile_unavailable_is_explicit_and_never_falls_back_to_legacy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unavailable = CompetitorProfileV11ReadResult(
        status="profile_unavailable",
        read_mode="full",
    )
    reader = FakeReader(unavailable)

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("profile unavailable attempted legacy analysis")

    monkeypatch.setattr(SopOrchestrators, "_competitor_set_legacy", forbidden)
    orchestrator = SopOrchestrators(
        ForbiddenAtomicHandlers(),  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )
    context = AnalystContext(
        project_id="project-tv",
        category_code="TV",
        batch_id="latest",
        product_category="TV",
    )

    result = orchestrator.competitor_set(
        context,
        sku_code="TV000001",
        competitor_profile_release_scope_key="project-tv:TV:scope-v1",
    )

    assert result["status"] == "not_found"
    assert result["result"]["competitor_set"] == {
        "source": "competitor_profile_v1_1",
        "status": "profile_unavailable",
        "preview": False,
        "candidate_count": 0,
        "candidates": [],
    }
    assert result["atoms_used"] == []
    assert [row["run_count"] for row in result["sop_steps"]] == [0, 1, 0, 0]


def test_agent_returns_all_twenty_65e7q_candidates_and_ignores_top_n_for_order() -> (
    None
):
    dto = _materialize(_twenty_candidate_65e7q_item())

    result, _ = _run_profile(dto, top_n=1)

    payload = result["result"]["competitor_set"]
    assert result["target"]["sku_code"] == "TV00029112"
    assert payload["candidate_count"] == 20
    assert len(payload["candidates"]) == 20
    assert payload["saved_priority_order"] == [
        row.candidate_sku_code for row in dto.priority_selections
    ]
    assert result["result"]["competitor_answer"]["top_competitors"]
    assert "请求的 top_n 不改变画像保存的重点竞品顺序。" in result["limitations"]


def test_zero_candidate_hard_exclusion_and_market_only_profiles_remain_usable() -> (
    None
):
    zero = _zero_candidate_dto("competitor-profile-v11-zero-agent")
    zero_result, _ = _run_profile(zero)
    assert zero_result["status"] == "ok"
    assert zero_result["result"]["competitor_set"]["candidate_count"] == 0
    assert zero_result["result"]["competitor_answer"]["all_candidates"] == []

    excluded = _hard_excluded_dto()
    excluded_result, _ = _run_profile(excluded)
    excluded_payload = excluded_result["result"]["competitor_set"]
    assert excluded_result["status"] == "ok"
    assert excluded_payload["candidate_count"] == 0
    assert excluded_payload["excluded_candidate_count"] == 1
    assert len(excluded_payload["excluded_candidate_audit"]) == 1

    market_only = _market_only_dto()
    market_result, _ = _run_profile(market_only)
    candidate = market_result["result"]["competitor_set"]["candidates"][0]
    assert market_result["status"] == "ok"
    assert candidate["market_validation"]["strength"] == "strong"
    assert candidate["semantic_overlap"]["value_battlefield"]["availability"] == (
        "unknown"
    )
    assert candidate["business_questions"][0]["conclusion_strength"] == "unknown"
    assert candidate["limitations"]


def test_query_target_uses_only_resolver_then_reads_profile() -> None:
    dto = _materialize(_work_item())
    resolver = ResolverOnlyAtomicHandlers(
        dto.target_snapshot.identity_market.sku_code
    )
    reader = FakeReader(_available_read(dto))
    orchestrator = SopOrchestrators(
        resolver,  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )

    result = orchestrator.competitor_set(
        _context(dto),
        query="fixture model",
        competitor_profile_release_scope_key=(
            dto.profile_version.release_scope_key
        ),
    )

    assert result["status"] == "ok"
    assert resolver.calls == ["resolve-sku"]
    assert result["atoms_used"] == [
        {"ability_code": "resolve-sku", "status": "ok"}
    ]


def test_profile_route_makes_no_live_analysis_sort_or_selection_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dto = _materialize(_work_item())

    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("profile route attempted live analysis")

    import app.services.core3_real_data.analyst.sop_orchestrators as sop_module

    monkeypatch.setattr(sop_module, "build_competitor_answer", forbidden)
    monkeypatch.setattr(SopOrchestrators, "_competitor_set_legacy", forbidden)
    for name in (
        "_enrich_competitor",
        "_sort_key",
        "_assign_top_roles",
        "_select_top_competitors",
        "_market_validation_score",
    ):
        monkeypatch.setattr(competitor_answer, name, forbidden)
    monkeypatch.setattr(PairAnalysisCalculator, "calculate", forbidden)
    monkeypatch.setattr(PairGateEvaluator, "evaluate", forbidden)
    monkeypatch.setattr(CompetitorProfileV11Selector, "select", forbidden)

    result, _ = _run_profile(dto)

    assert result["status"] == "ok"


def test_feishu_report_publishes_only_pre_rendered_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dto = _materialize(_work_item())
    calls: list[dict[str, Any]] = []

    def fake_publish_report(**kwargs: Any) -> competitor_answer.ReportPublishResult:
        calls.append(kwargs)
        return competitor_answer.ReportPublishResult(
            status="published",
            url="https://example.test/docx/profile",
        )

    monkeypatch.setattr(competitor_answer, "_publish_report", fake_publish_report)

    result, _ = _run_profile(dto, with_report="feishu-doc")

    answer = result["result"]["competitor_answer"]
    assert len(calls) == 1
    assert calls[0]["with_report"] == "feishu-doc"
    assert calls[0]["markdown"].startswith("# ")
    assert answer["report_status"] == "published"
    assert answer["report_url"] == "https://example.test/docx/profile"
    assert answer["report_payload"]["markdown"] is None


def test_reader_scope_version_or_post_construction_mutation_fails_closed() -> None:
    dto = _materialize(_work_item())

    with pytest.raises(ValueError, match="different version"):
        _run_profile(
            dto,
            preview=True,
            profile_access_mode="preview",
            competitor_profile_version_id="not-the-returned-version",
            allow_draft_preview=True,
        )

    with pytest.raises(ValueError, match="wrong scope"):
        _run_profile(
            dto,
            preview=True,
            profile_access_mode="preview",
            competitor_profile_version_id=(
                dto.profile_version.competitor_profile_version_id
            ),
            competitor_profile_release_scope_key="wrong-release-scope",
            allow_draft_preview=True,
        )

    read = _available_read(dto)
    dto.sku_summary.analysis_candidate_count += 1
    reader = FakeReader(read)
    orchestrator = SopOrchestrators(
        ForbiddenAtomicHandlers(),  # type: ignore[arg-type]
        competitor_profile_v1_1_reader=reader,  # type: ignore[arg-type]
    )
    with pytest.raises(ValueError):
        orchestrator.competitor_set(
            _context(dto),
            sku_code=dto.target_snapshot.identity_market.sku_code,
            competitor_profile_release_scope_key=(
                dto.profile_version.release_scope_key
            ),
        )


def test_legacy_path_requires_explicit_operations_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dto = _materialize(_work_item())
    sentinel = {"status": "legacy-explicit"}

    def legacy(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return sentinel

    monkeypatch.setattr(SopOrchestrators, "_competitor_set_legacy", legacy)
    orchestrator = SopOrchestrators(ForbiddenAtomicHandlers())  # type: ignore[arg-type]

    result = orchestrator.competitor_set(
        _context(dto),
        sku_code=dto.target_snapshot.identity_market.sku_code,
        legacy_live_analysis=True,
    )

    assert result is sentinel


def test_service_wires_v11_reader_and_cli_exposes_explicit_profile_modes() -> None:
    service = CatForgeAnalystService(
        make_session(),
        project_id="project-tv",
        category_code="TV",
    )
    assert isinstance(
        service.sop_orchestrators.competitor_profile_v1_1_reader,
        CompetitorProfileV11Reader,
    )

    args = catforge_analyst.build_parser().parse_args(
        [
            "competitor-set",
            "--sku-code",
            "TV00029112",
            "--competitor-profile-mode",
            "preview",
            "--competitor-profile-version-id",
            "version-1",
            "--competitor-profile-release-scope-key",
            "scope-1",
            "--allow-competitor-profile-draft-preview",
        ]
    )
    assert args.profile_access_mode == "preview"
    assert args.competitor_profile_version_id == "version-1"
    assert args.competitor_profile_release_scope_key == "scope-1"
    assert args.allow_competitor_profile_draft_preview is True
    assert args.legacy_competitor_live_analysis is False


@pytest.mark.parametrize(
    ("command", "command_kwargs"),
    [
        ("competitor-set", {"sku_code": "TV00029112"}),
        ("ask", {"question": "TV00029112 的竞品有哪些"}),
    ],
)
def test_exact_sku_profile_command_does_not_resolve_latest_legacy_batch(
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    command_kwargs: dict[str, Any],
) -> None:
    calls: list[bool] = []

    class FakeService:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        def build_context(self, **kwargs: Any) -> AnalystContext:
            calls.append(kwargs["resolve_latest"])
            return AnalystContext(
                project_id="project-tv",
                category_code="TV",
                batch_id="latest",
                product_category="tv",
            )

        def dispatch(
            self, _command: str, _context: AnalystContext, **_kwargs: Any
        ) -> dict[str, Any]:
            return {"status": "ok"}

    monkeypatch.setattr(catforge_analyst, "CatForgeAnalystService", FakeService)

    result = catforge_analyst.run_analyst_command(
        make_session(),
        command=command,
        project_id="project-tv",
        category_code="TV",
        **command_kwargs,
    )

    assert result == {"status": "ok"}
    assert calls == [False]
