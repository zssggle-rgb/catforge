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

    disabled = parser.parse_args(["sellpoint-value-pm-v4", "--sku-code", "TV00029112"])
    enabled = parser.parse_args(
        [
            "sellpoint-value-pm-v4",
            "--sku-code",
            "TV00029112",
            "--enable-v4",
        ]
    )

    assert disabled.enable_v4 is False
    assert enabled.enable_v4 is True
    assert "sellpoint-value-pm-v4" in SOP_COMMANDS
    assert get_ability("sellpoint-value-pm-v4").status == "implemented_default_off"


def test_cli_default_off_exits_before_database_context(capsys) -> None:
    exit_code = catforge_analyst.main(
        [
            "sellpoint-value-pm-v4",
            "--sku-code",
            "TV00029112",
            "--format",
            "text",
        ]
    )

    assert exit_code == 1
    assert "默认关闭" in capsys.readouterr().out


def test_default_off_gate_returns_before_context_load() -> None:
    handlers = _FakeAtomicHandlers()
    orchestrator = SopOrchestrators(handlers)  # type: ignore[arg-type]

    result = orchestrator.sellpoint_value_pm_v4(
        _analyst_context(),
        sku_code="TV00029112",
    )

    assert result["status"] == "error"
    assert "默认关闭" in result["message_cn"]
    assert handlers.call_count == 0


def test_explicit_enabled_command_returns_report_and_same_source_answer() -> None:
    handlers = _FakeAtomicHandlers()
    orchestrator = SopOrchestrators(handlers)  # type: ignore[arg-type]

    result = orchestrator.dispatch(
        "sellpoint-value-pm-v4",
        _analyst_context(),
        sku_code="TV00029112",
        enable_v4=True,
        answer_style="xiaoao",
        selection_compare_url="https://example.com/compare",
        evidence_report_url="https://example.com/evidence",
    )

    assert result["status"] == "ok"
    assert handlers.call_count == 1
    payload = result["result"]
    report = payload["sellpoint_value_pm_v4"]
    answer = payload["sellpoint_value_pm_v4_answer"]
    assert answer["result_hash"] == report["result_hash"]
    assert "画质配置解释加价" in answer["short_answer"]
    assert [item["label"] for item in answer["report_links"]] == [
        "查看用户选择对比",
        "查看分析依据",
    ]


def test_natural_language_route_remains_on_v2() -> None:
    route = route_question(
        "请分析 65E7Q 的用户卖点价值、选择和支付意愿",
        explicit_params={"sku_code": "TV00029112"},
    )

    assert route.command != "sellpoint-value-pm-v4"
    assert route.command in {"sellpoint-value-pm", "sku-claim-value"}


def test_cli_business_text_prefers_v4_short_answer() -> None:
    result = {
        "status": "ok",
        "result": {
            "sellpoint_value_pm_v4": {"headline_cn": "V4 headline"},
            "sellpoint_value_pm_v4_answer": {"short_answer": "V4 short answer"},
        },
    }

    assert catforge_analyst.format_business_text(result) == "V4 short answer"
