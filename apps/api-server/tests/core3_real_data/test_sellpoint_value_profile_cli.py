from __future__ import annotations

from app.cli import catforge_analyst


def test_profile_generation_commands_require_explicit_write_gate() -> None:
    parser = catforge_analyst.build_parser()

    single = parser.parse_args(
        [
            "sellpoint-value-profile-generate",
            "--sku-code",
            "TV00029112",
            "--profile-version",
            "spv-v1",
            "--generated-by",
            "tester",
        ]
    )
    batch = parser.parse_args(
        [
            "sellpoint-value-profile-batch-generate",
            "--profile-version",
            "spv-v1",
            "--generated-by",
            "tester",
            "--enable-profile-write",
            "--page-size",
            "25",
        ]
    )

    assert single.enable_profile_write is False
    assert batch.enable_profile_write is True
    assert batch.page_size == 25
    assert batch.regenerate_existing is False


def test_profile_write_gate_returns_before_database_session(monkeypatch, capsys) -> None:
    def _session_must_not_open():
        raise AssertionError("database session opened before profile write gate")

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _session_must_not_open)

    exit_code = catforge_analyst.main(
        [
            "sellpoint-value-profile-generate",
            "--sku-code",
            "TV00029112",
            "--profile-version",
            "spv-v1",
            "--generated-by",
            "tester",
            "--format",
            "text",
        ]
    )

    assert exit_code == 1
    assert "草稿写入默认关闭" in capsys.readouterr().out


def test_enabled_profile_command_uses_dedicated_generation_path(
    monkeypatch,
    capsys,
) -> None:
    captured = {}

    class _SessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, traceback):
            del exc_type, exc, traceback

    def _run(db, args):
        captured["db"] = db
        captured["args"] = args
        return {"status": "ok", "command": args.command}

    monkeypatch.setattr(catforge_analyst, "SessionLocal", _SessionContext)
    monkeypatch.setattr(
        catforge_analyst,
        "run_sellpoint_value_profile_generation",
        _run,
    )

    exit_code = catforge_analyst.main(
        [
            "sellpoint-value-profile-generate",
            "--sku-code",
            "TV00029112",
            "--profile-version",
            "spv-v1",
            "--generated-by",
            "tester",
            "--enable-profile-write",
            "--format",
            "json",
        ]
    )

    assert exit_code == 0
    assert captured["args"].sku_code == "TV00029112"
    assert "sellpoint-value-profile-generate" in capsys.readouterr().out
