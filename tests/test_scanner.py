from datetime import UTC, datetime

import httpx
import pytest
import respx

from repo_posture.checks import Status
from repo_posture.github import API_URL, GitHubClient, GitHubError
from repo_posture.scanner import parse_repository, scan

from .conftest import LOOSE_CI, FakeGitHub, well_configured

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


def statuses(report: object) -> dict[str, Status]:
    return {r.id: r.status for r in report.results}  # type: ignore[attr-defined]


def test_well_configured_repository_passes_everything(
    fake: FakeGitHub, client: GitHubClient
) -> None:
    well_configured(fake).install()
    report = scan(client, "acme/app", now=NOW)
    assert set(statuses(report).values()) == {Status.PASS}
    assert (report.score, report.coverage) == (100, 100)
    assert report.failures == ()
    assert report.scanned_at == "2026-11-17T12:00:00Z"


def test_bare_repository_fails_with_fixes_ordered_by_weight(
    fake: FakeGitHub, client: GitHubClient
) -> None:
    fake.files[".github/workflows/ci.yml"] = LOOSE_CI
    fake.install()
    report = scan(client, "https://github.com/acme/app.git")
    s = statuses(report)
    assert s["ci-workflows"] is Status.PASS
    assert s["pinned-actions"] is Status.FAIL
    assert s["workflow-permissions"] is Status.FAIL
    assert s["branch-protection"] is Status.FAIL
    # Without an admin token, GitHub hides these settings: unknown, never guessed.
    for hidden in ("secret-scanning", "push-protection", "dependabot-security-updates"):
        assert s[hidden] is Status.UNKNOWN
    assert s["code-scanning"] is Status.UNKNOWN
    assert report.score == 13  # only CI (weight 3) passes, of 23 known weight
    assert report.coverage < 100
    weights = [r.weight for r in report.failures]
    assert weights == sorted(weights, reverse=True)


def test_repository_without_workflows(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.install()
    s = statuses(scan(client, "acme/app"))
    assert s["ci-workflows"] is Status.FAIL
    assert s["pinned-actions"] is Status.UNKNOWN
    assert s["workflow-permissions"] is Status.UNKNOWN
    assert s["dependency-review"] is Status.FAIL


def test_code_scanning_default_setup(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.default_setup = {"state": "configured"}
    fake.install()
    assert statuses(scan(client, "acme/app"))["code-scanning"] is Status.PASS


def test_code_scanning_default_setup_off(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.default_setup = {"state": "not-configured"}
    fake.install()
    assert statuses(scan(client, "acme/app"))["code-scanning"] is Status.FAIL


def test_legacy_branch_protection_counts(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.rules = None
    fake.branch = {"name": "main", "protected": True}
    fake.install()
    assert statuses(scan(client, "acme/app"))["branch-protection"] is Status.PASS


def test_unreadable_branch_rules_are_unknown(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.rules = None
    fake.branch = None
    fake.install()
    assert statuses(scan(client, "acme/app"))["branch-protection"] is Status.UNKNOWN


def test_disabled_security_features_fail(fake: FakeGitHub, client: GitHubClient) -> None:
    fake.metadata["security_and_analysis"] = {
        "secret_scanning": {"status": "disabled"},
        "secret_scanning_push_protection": {"status": "disabled"},
        "dependabot_security_updates": {"status": "disabled"},
    }
    fake.install()
    s = statuses(scan(client, "acme/app"))
    assert s["secret-scanning"] is s["push-protection"] is Status.FAIL
    assert s["dependabot-security-updates"] is Status.FAIL


def test_many_unpinned_actions_are_summarised(fake: FakeGitHub, client: GitHubClient) -> None:
    steps = "\n".join(f"      - uses: acme/action-{i}@v1" for i in range(7))
    fake.files[".github/workflows/ci.yml"] = f"jobs:\n  a:\n    steps:\n{steps}\n"
    fake.files[".github/workflows/notes.txt"] = "not a workflow"
    fake.files[".github/workflows/broken.yml"] = "jobs: [unclosed"
    fake.install()
    report = scan(client, "acme/app")
    pinned = next(r for r in report.results if r.id == "pinned-actions")
    assert pinned.detail.startswith("7 unpinned:") and "and 2 more" in pinned.detail


def test_missing_repository_is_an_error(router: respx.MockRouter, client: GitHubClient) -> None:
    router.get(f"{API_URL}/repos/acme/ghost").mock(return_value=httpx.Response(404))
    with pytest.raises(GitHubError, match="not found"):
        scan(client, "acme/ghost")


def test_rate_limit_is_an_error_not_a_missing_control(
    router: respx.MockRouter, client: GitHubClient
) -> None:
    router.get(f"{API_URL}/repos/acme/app").mock(
        return_value=httpx.Response(403, headers={"x-ratelimit-remaining": "0"})
    )
    with pytest.raises(GitHubError, match="rate limit"):
        scan(client, "acme/app")


def test_server_errors_are_reported(router: respx.MockRouter, client: GitHubClient) -> None:
    router.get(f"{API_URL}/repos/acme/app").mock(return_value=httpx.Response(502))
    with pytest.raises(GitHubError, match="HTTP 502"):
        scan(client, "acme/app")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("acme/app", ("acme", "app")),
        ("https://github.com/acme/app", ("acme", "app")),
        ("github.com/acme/app.git/", ("acme", "app")),
    ],
)
def test_parse_repository(value: str, expected: tuple[str, str]) -> None:
    assert parse_repository(value) == expected


@pytest.mark.parametrize("value", ["acme", "acme/app/extra", "/app", ""])
def test_parse_repository_rejects(value: str) -> None:
    with pytest.raises(ValueError, match="owner/repo"):
        parse_repository(value)


def test_client_sends_token_and_api_version(router: respx.MockRouter) -> None:
    route = router.get(f"{API_URL}/rate_limit").mock(return_value=httpx.Response(200, json={}))
    with GitHubClient("secret-value") as c:
        c.get("/rate_limit")
    sent = route.calls.last.request.headers
    assert sent["authorization"] == "Bearer secret-value"
    assert sent["x-github-api-version"] == "2022-11-28"


def test_client_without_token_sends_no_authorization(router: respx.MockRouter) -> None:
    route = router.get(f"{API_URL}/rate_limit").mock(return_value=httpx.Response(200, json={}))
    with GitHubClient() as c:
        c.get("/rate_limit")
    assert "authorization" not in route.calls.last.request.headers
