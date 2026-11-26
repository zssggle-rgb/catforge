import io
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


probe = runpy.run_path(str(Path(__file__).resolve().parents[3] / "scripts/qa/probe"))
SHA = "a" * 40


@pytest.mark.parametrize("labels, expected", [
    ([], None), ([SHA], None), ([SHA, "b" * 40], None), (["latest"] * 2, None), ([SHA] * 2, SHA),
])
def test_probe_requires_matching_running_images(monkeypatch, labels, expected):
    monkeypatch.setenv("FM_QA_HOST", "assigned-test")
    monkeypatch.setenv("FM_QA_SSH_CONFIG", "/test/ssh_config")
    with patch("subprocess.run") as ssh:
        ssh.return_value.stdout = "\n".join(labels)
        assert probe["running_revision"]() == expected


@pytest.mark.parametrize("database, expected", [("ok", True), ("unavailable", False)])
def test_readiness_uses_web_proxy_and_database(database, expected):
    client = MagicMock()
    client.open.side_effect = [io.BytesIO(b'<div id="root"></div>'),
                               io.BytesIO(('{"status":"ready","database":"%s"}' % database).encode())]
    with patch("urllib.request.build_opener", return_value=client):
        assert probe["ready"]("http://qa:8100/") is expected
    assert client.open.call_args.args[0] == "http://qa:8100/api/readyz"
