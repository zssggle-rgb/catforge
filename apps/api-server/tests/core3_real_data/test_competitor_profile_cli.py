from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.cli import catforge_analyst
from app.services.core3_real_data.analyst.competitor_profile_consumption_schemas import (
    CompetitorProfileConsumptionContext,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
)
from tests.core3_real_data.test_competitor_profile_generation import _request


def _request_file(tmp_path):
    path = tmp_path / "competitor-profile-request.json"
    path.write_text(_request(_category_bundle()).model_dump_json(), encoding="utf-8")
    return path


def test_competitor_generation_commands_require_explicit_write_gate(
    tmp_path,
) -> None:
    request_path = _request_file(tmp_path)
    parser = catforge_analyst.build_parser()

    single = parser.parse_args(
        [
            "competitor-profile-generate",
            "--request-json",
            str(request_path),
            "--sku-code",
            "TV000001",
        ]
    )
    batch = parser.parse_args(
        [
            "competitor-profile-batch-generate",
            "--request-json",
            str(request_path),
            "--enable-profile-write",
            "--page-size",
            "25",
            "--max-new-skus",
            "10",
        ]
    )

    assert single.enable_profile_write is False
    assert batch.enable_profile_write is True
    assert batch.page_size == 25
    assert batch.max_new_skus == 10


def test_competitor_write_gate_returns_before_database_session(
    monkeypatch,
    capsys,
    tmp_path,
) -> None:
    request_path = _request_file(tmp_path)

    def _session_must_not_open():
        raise AssertionError("database session opened before profile write gate")

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _session_must_not_open)
    exit_code = catforge_analyst.main(
        [
            "competitor-profile-generate",
            "--request-json",
            str(request_path),
            "--sku-code",
            "TV000001",
            "--format",
            "text",
        ]
    )

    assert exit_code == 1
    assert "草稿写入默认关闭" in capsys.readouterr().out


def test_generation_handler_validates_request_and_normalizes_target(
    monkeypatch,
    tmp_path,
) -> None:
    request_path = _request_file(tmp_path)
    captured = {}

    class _Result:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"status": "generated"}

    class _Service:
        def __init__(self, *, repository, input_provider):
            captured["repository"] = repository
            captured["input_provider"] = input_provider

        def generate_draft(self, request, *, target_sku_code):
            captured["request"] = request
            captured["target_sku_code"] = target_sku_code
            return _Result()

    monkeypatch.setattr(
        catforge_analyst,
        "CompetitorProfileGenerationService",
        _Service,
    )
    result = catforge_analyst.run_competitor_profile_generation(
        object(),
        argparse.Namespace(
            command="competitor-profile-generate",
            request_json=str(request_path),
            sku_code=" tv000001 ",
        ),
    )

    assert captured["target_sku_code"] == "TV000001"
    assert captured["request"].input_request.category_code == "TV"
    assert result["generation"]["status"] == "generated"


def test_build_request_handler_uses_current_production_scope(monkeypatch) -> None:
    captured = {}

    class _Request:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"profile_version": "competitor-profile-g24"}

    def fake_build(*, provider, profile_version, generated_by):
        captured["provider"] = provider
        captured["profile_version"] = profile_version
        captured["generated_by"] = generated_by
        return _Request()

    monkeypatch.setattr(
        catforge_analyst,
        "build_production_generation_request",
        fake_build,
    )
    result = catforge_analyst.run_competitor_profile_build_request(
        object(),
        argparse.Namespace(
            command="competitor-profile-build-request",
            project_id="project-tv",
            category_code="TV",
            profile_version="competitor-profile-g24",
            generated_by="g24",
        ),
    )

    assert captured["profile_version"] == "competitor-profile-g24"
    assert captured["generated_by"] == "g24"
    assert result["request"]["profile_version"] == "competitor-profile-g24"


def test_batch_generation_handler_preserves_resume_controls(
    monkeypatch,
    tmp_path,
) -> None:
    request_path = _request_file(tmp_path)
    captured = {}

    class _Result:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"status": "completed"}

    class _Service:
        def __init__(self, *, repository, input_provider):
            del repository, input_provider

        def batch_generate(self, request, **kwargs):
            captured["request"] = request
            captured.update(kwargs)
            return _Result()

    monkeypatch.setattr(
        catforge_analyst,
        "CompetitorProfileGenerationService",
        _Service,
    )
    result = catforge_analyst.run_competitor_profile_generation(
        object(),
        argparse.Namespace(
            command="competitor-profile-batch-generate",
            request_json=str(request_path),
            regenerate_existing=False,
            page_size=25,
            max_new_skus=10,
        ),
    )

    assert captured["resume_unfinished_only"] is True
    assert captured["page_size"] == 25
    assert captured["max_new_skus"] == 10
    assert result["generation"]["status"] == "completed"


def test_read_handler_builds_one_consumption_context(monkeypatch) -> None:
    captured = {}

    class _Service:
        def __init__(self, reader):
            captured["reader"] = reader

        def load(self, request):
            captured["request"] = request
            return CompetitorProfileConsumptionContext(
                status="profile_unavailable",
                message_cn="当前没有可用的正式竞品画像。",
            )

    monkeypatch.setattr(
        catforge_analyst,
        "CompetitorProfileConsumptionService",
        _Service,
    )
    result = catforge_analyst.run_competitor_profile_read(
        object(),
        argparse.Namespace(
            project_id="project-tv",
            category_code="TV",
            release_scope_key="scope-tv",
            sku_code=" tv000001 ",
            mode="formal",
            competitor_profile_version_id=None,
            allow_draft_preview=False,
            command="competitor-profile-read",
        ),
    )

    assert captured["request"].target_sku_code == "TV000001"
    assert captured["request"].mode == "formal"
    assert result["status"] == "not_found"


def test_preview_handler_loads_once_and_renders_one_locked_context(
    monkeypatch,
) -> None:
    captured = {"loads": 0, "renders": 0}
    context = SimpleNamespace(status="available")

    def fake_load(db, args):
        del db
        captured["loads"] += 1
        captured["args"] = args
        return context

    class _Presentation:
        def model_dump(self, *, mode):
            assert mode == "json"
            return {"competitor_profile_version_id": "version-g24"}

    def fake_render(value, *, with_report):
        captured["renders"] += 1
        assert value is context
        assert with_report == "feishu-doc"
        return _Presentation()

    monkeypatch.setattr(
        catforge_analyst,
        "_load_competitor_profile_consumption",
        fake_load,
    )
    monkeypatch.setattr(
        catforge_analyst,
        "build_competitor_profile_presentation",
        fake_render,
    )
    result = catforge_analyst.run_competitor_profile_preview(
        object(),
        argparse.Namespace(
            command="competitor-profile-preview",
            with_report="feishu-doc",
        ),
    )

    assert captured["loads"] == 1
    assert captured["renders"] == 1
    assert result["presentation"]["competitor_profile_version_id"] == "version-g24"


def test_parser_requires_explicit_preview_version_and_report_mode() -> None:
    parser = catforge_analyst.build_parser()
    args = parser.parse_args(
        [
            "competitor-profile-preview",
            "--project-id",
            "project-tv",
            "--category-code",
            "TV",
            "--release-scope-key",
            "scope-tv",
            "--sku-code",
            "TV000001",
            "--mode",
            "preview",
            "--competitor-profile-version-id",
            "version-g24",
            "--allow-draft-preview",
            "--with-report",
            "feishu-doc",
        ]
    )

    assert args.mode == "preview"
    assert args.competitor_profile_version_id == "version-g24"
    assert args.allow_draft_preview is True
    assert args.with_report == "feishu-doc"


def test_request_loader_rejects_invalid_or_cross_category_config(tmp_path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}", encoding="utf-8")

    with pytest.raises(ValidationError):
        catforge_analyst._load_competitor_profile_generation_request(str(invalid))
    with pytest.raises(ValueError, match="请求文件无法读取"):
        catforge_analyst._load_competitor_profile_generation_request(
            str(tmp_path / "missing.json")
        )
