from __future__ import annotations

from app.cli import catforge_analyst
from app.services.core3_real_data.analyst.ability_registry import get_ability
from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext
from app.services.core3_real_data.analyst.analyst_service import (
    SOP_COMMANDS,
    route_question,
)
from app.services.core3_real_data.analyst.sop_orchestrators import SopOrchestrators
from tests.core3_real_data.test_claim_value_pm_v4_quantification import (
    _synthetic_context,
)


def _analyst_context() -> AnalystContext:
    return AnalystContext(
        project_id="project-1",
        category_code="TV",
        batch_id="batch-1",
        product_category="TV",
        market_window="full_observed_window",
        analysis_population="fact_complete_with_comment",
    )


class _FakeAtomicHandlers:
    def __init__(self) -> None:
        self.v4_context = _synthetic_context()
        self.call_count = 0

    def sellpoint_value_v4_context(self, context, **kwargs):
        del context, kwargs
        self.call_count += 1
        return {
            "status": "ok",
            "target": self.v4_context.target.model_dump(mode="json"),
            "result": {
                "sellpoint_value_v4_context": self.v4_context.model_dump(mode="json")
            },
            "atoms_used": [
                {"ability_code": "sellpoint-value-v4-context", "status": "ok"}
            ],
            "evidence": [],
            "limitations": [],
        }


def test_cli_command_exists_but_is_default_off() -> None:
    parser = catforge_analyst.build_parser()

    disabled = parser.parse_args(["sellpoint-value-pm-v5", "--sku-code", "TV00029112"])
    enabled = parser.parse_args(
        [
            "sellpoint-value-pm-v5",
            "--sku-code",
            "TV00029112",
            "--enable-v5",
            "--preview-profile-version",
            "spv-draft-1",
            "--preview-sellpoint-value-profile-version-id",
            "spv-version-1",
        ]
    )

    assert disabled.enable_v5 is False
    assert enabled.enable_v5 is True
    assert enabled.preview_profile_version == "spv-draft-1"
    assert enabled.preview_sellpoint_value_profile_version_id == "spv-version-1"
    assert "sellpoint-value-pm-v5" in SOP_COMMANDS
    assert get_ability("sellpoint-value-pm-v5").status == "implemented_default_off"


def test_cli_default_off_returns_before_session_creation(monkeypatch, capsys) -> None:
    def _session_must_not_open():
        raise AssertionError("database session opened before V5 flag gate")

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _session_must_not_open)

    exit_code = catforge_analyst.main(
        ["sellpoint-value-pm-v5", "--sku-code", "TV00029112", "--format", "text"]
    )

    assert exit_code == 1
    assert "默认关闭" in capsys.readouterr().out


def test_cli_forwards_explicit_profile_preview(monkeypatch, capsys) -> None:
    captured = {}

    class _SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    def _run(_db, **kwargs):
        captured.update(kwargs)
        return {"status": "not_found", "result": {}}

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _SessionContext)
    monkeypatch.setattr(catforge_analyst, "run_analyst_command", _run)

    exit_code = catforge_analyst.main(
        [
            "sellpoint-value-pm-v5",
            "--sku-code",
            "TV00029112",
            "--enable-v5",
            "--preview-profile-version",
            "spv-draft-1",
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    assert captured["preview_profile_version"] == "spv-draft-1"
    assert "not_found" in capsys.readouterr().out


def test_orchestrator_default_off_returns_before_context_load() -> None:
    handlers = _FakeAtomicHandlers()
    orchestrator = SopOrchestrators(handlers)  # type: ignore[arg-type]

    result = orchestrator.sellpoint_value_pm_v5(
        _analyst_context(), sku_code="TV00029112"
    )

    assert result["status"] == "error"
    assert "默认关闭" in result["message_cn"]
    assert handlers.call_count == 0


def test_explicit_command_without_profile_store_does_not_recompute() -> None:
    handlers = _FakeAtomicHandlers()
    orchestrator = SopOrchestrators(handlers)  # type: ignore[arg-type]

    result = orchestrator.dispatch(
        "sellpoint-value-pm-v5",
        _analyst_context(),
        sku_code="TV00029112",
        enable_v5=True,
        selection_compare_url="https://example.com/compare",
        evidence_report_url="https://example.com/evidence",
    )

    assert result["status"] == "not_found"
    assert "画像" in result["message_cn"]
    assert handlers.call_count == 0


def test_natural_language_route_remains_on_v2() -> None:
    route = route_question(
        "请分析 65E7Q 的用户卖点价值、选择和支付意愿",
        explicit_params={"sku_code": "TV00029112"},
    )

    assert route.command != "sellpoint-value-pm-v5"
    assert route.command in {"sellpoint-value-pm", "sku-claim-value"}


def test_cli_business_text_prefers_v5_short_answer() -> None:
    result = {
        "status": "ok",
        "result": {
            "sellpoint_value_pm_v5": {"analysis_state": "ready"},
            "sellpoint_value_pm_v5_answer": {"short_answer": "V5 short answer"},
        },
    }

    assert catforge_analyst.format_business_text(result) == "V5 short answer"
