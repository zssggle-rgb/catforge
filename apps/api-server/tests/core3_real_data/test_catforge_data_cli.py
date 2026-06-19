from app.cli import catforge_data
from app.cli.catforge_data import _build_parser


def test_prepare_new_data_defaults_to_incremental_source_registration():
    parser = _build_parser()

    args = parser.parse_args(["prepare-new-data"])

    assert args.command == "prepare-new-data"
    assert args.register_source_batch == "incremental"
    assert args.batch_id == "latest"
    assert args.sku_batch_size == 50


def test_prepare_new_data_can_rerun_existing_batch_without_source_registration():
    parser = _build_parser()

    args = parser.parse_args(
        [
            "prepare-new-data",
            "--register-source-batch",
            "none",
            "--batch-id",
            "latest",
            "--limit-skus",
            "5",
        ]
    )

    assert args.register_source_batch == "none"
    assert args.batch_id == "latest"
    assert args.limit_skus == 5


def test_prepare_new_data_dry_run_does_not_register_source_batch(monkeypatch):
    parser = _build_parser()
    args = parser.parse_args(["prepare-new-data", "--dry-run"])

    class DummySession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fail_register(*_args, **_kwargs):
        raise AssertionError("dry-run must not register source batches")

    monkeypatch.setattr(catforge_data, "SessionLocal", DummySession)
    monkeypatch.setattr(catforge_data, "_register_source_batch", fail_register)

    result = catforge_data._prepare_new_data(args)

    assert result["status"] == "dry_run"
    assert result["source_registration"]["will_register_source_batch"] is True
    assert result["plan"]["will_run_modules"] == ["M00", "M01"]
