"""A fake GitHub API (respx) so tests never touch the network."""

from __future__ import annotations

import base64
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import respx

from repo_posture.github import API_URL, GitHubClient

SHA = "a" * 40

GOOD_CI = f"""
name: ci
on: [pull_request]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{SHA} # v4
      - uses: github/codeql-action/init@{SHA}
      - uses: actions/dependency-review-action@{SHA}
      - uses: ./local-action
"""

LOOSE_CI = """
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: make test
"""


class FakeGitHub:
    """Registers a repository's files and settings on a respx router."""

    def __init__(self, router: respx.MockRouter, owner: str = "acme", repo: str = "app") -> None:
        self.router = router
        self.base = f"/repos/{owner}/{repo}"
        self.files: dict[str, str] = {}
        self.metadata: dict[str, Any] = {"default_branch": "main", "license": None}
        self.rules: list[dict[str, Any]] | None = []
        self.branch: dict[str, Any] | None = {"name": "main", "protected": False}
        self.default_setup: dict[str, Any] | None = None

    def install(self) -> None:
        self.router.get(f"{API_URL}{self.base}").mock(
            return_value=httpx.Response(200, json=self.metadata)
        )
        self.router.get(url__regex=rf"{API_URL}{self.base}/contents/(?P<path>.+)").mock(
            side_effect=self._contents
        )
        self.router.get(f"{API_URL}{self.base}/rules/branches/main").mock(
            return_value=self._maybe(self.rules)
        )
        self.router.get(f"{API_URL}{self.base}/branches/main").mock(
            return_value=self._maybe(self.branch)
        )
        self.router.get(f"{API_URL}{self.base}/code-scanning/default-setup").mock(
            return_value=self._maybe(self.default_setup, missing=403)
        )

    @staticmethod
    def _maybe(body: Any, missing: int = 404) -> httpx.Response:
        return httpx.Response(200, json=body) if body is not None else httpx.Response(missing)

    def _contents(self, request: httpx.Request, path: str) -> httpx.Response:
        if path in self.files:
            encoded = base64.b64encode(self.files[path].encode()).decode()
            return httpx.Response(200, json={"type": "file", "content": encoded})
        prefix = path.rstrip("/") + "/"
        children = sorted(
            {p[len(prefix) :].split("/")[0] for p in self.files if p.startswith(prefix)}
        )
        if children:
            return httpx.Response(200, json=[{"name": c, "type": "file"} for c in children])
        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def fake(router: respx.MockRouter) -> FakeGitHub:
    return FakeGitHub(router)


@pytest.fixture
def client() -> Iterator[GitHubClient]:
    with GitHubClient("test-token") as c:
        yield c


def well_configured(fake: FakeGitHub) -> FakeGitHub:
    fake.files.update(
        {
            "SECURITY.md": "# Security",
            ".github/dependabot.yml": "version: 2",
            ".github/CODEOWNERS": "* @acme/owners",
            ".github/workflows/ci.yml": GOOD_CI,
        }
    )
    fake.metadata.update(
        {
            "license": {"spdx_id": "MIT"},
            "security_and_analysis": {
                "secret_scanning": {"status": "enabled"},
                "secret_scanning_push_protection": {"status": "enabled"},
                "dependabot_security_updates": {"status": "enabled"},
            },
        }
    )
    fake.rules = [{"type": "pull_request"}, {"type": "required_status_checks"}]
    return fake
