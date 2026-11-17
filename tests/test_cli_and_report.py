import json

import httpx
import pytest
import respx

from repo_posture.cli import main
from repo_posture.github import API_URL

from .conftest import FakeGitHub, well_configured


def test_markdown_report(fake: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> None:
    fake.install()
    assert main(["acme/app"]) == 0
    out = capsys.readouterr().out
    assert "## Posture report: `acme/app`" in out
    assert "### Fix first" in out
    assert "Unknown checks aren't scored" in out
    assert "https://docs.github.com/en/" in out


def test_json_report(fake: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> None:
    well_configured(fake).install()
    assert main(["acme/app", "--format", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["repository"] == "acme/app"
    assert data["score"] == 100 and data["coverage"] == 100
    assert {c["status"] for c in data["checks"]} == {"pass"}


def test_markdown_escapes_table_cells(fake: FakeGitHub, capsys: pytest.CaptureFixture[str]) -> None:
    well_configured(fake)
    fake.metadata["license"] = {"spdx_id": "A|B"}
    fake.install()
    main(["acme/app"])
    assert "A\\|B" in capsys.readouterr().out


def test_min_score_gate_fails_below_threshold(
    fake: FakeGitHub, capsys: pytest.CaptureFixture[str]
) -> None:
    fake.install()
    assert main(["acme/app", "--min-score", "80"]) == 1
    assert "below the minimum score of 80: acme/app" in capsys.readouterr().err


def test_min_score_gate_passes_at_threshold(fake: FakeGitHub) -> None:
    well_configured(fake).install()
    assert main(["acme/app", "--min-score", "100"]) == 0


def test_errors_exit_2(router: respx.MockRouter, capsys: pytest.CaptureFixture[str]) -> None:
    router.get(f"{API_URL}/repos/acme/ghost").mock(return_value=httpx.Response(404))
    assert main(["acme/ghost"]) == 2
    assert "not found" in capsys.readouterr().err
    assert main(["not-a-repo"]) == 2


def test_token_is_read_from_the_environment(
    fake: FakeGitHub, monkeypatch: pytest.MonkeyPatch, router: respx.MockRouter
) -> None:
    fake.install()
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    main(["acme/app"])
    assert router.calls.last.request.headers["authorization"] == "Bearer env-token"
