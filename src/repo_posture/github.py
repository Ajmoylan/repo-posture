"""A small, read-only GitHub REST API client.

Only GET requests are made. A token is optional: without one, public repositories can be scanned
within GitHub's unauthenticated rate limit, and checks that need more access report "unknown"
instead of guessing.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

API_URL = "https://api.github.com"


class GitHubError(Exception):
    """The API refused or failed a request in a way the scan cannot work around."""


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = API_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "repo-posture",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=base_url, headers=headers, timeout=20.0, transport=transport
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> GitHubClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(self, path: str) -> Any | None:
        """GET a JSON resource. Returns None when it doesn't exist or isn't visible (404, 403).

        Rate limiting is an error, never "missing": a scan must not report a control as absent
        just because GitHub stopped answering.
        """
        response = self._http.get(path)
        if response.status_code == 200:
            return response.json()
        if response.status_code in (403, 429) and (
            response.headers.get("x-ratelimit-remaining") == "0" or response.status_code == 429
        ):
            raise GitHubError(
                "GitHub API rate limit reached. Set GITHUB_TOKEN to scan with a higher limit."
            )
        if response.status_code in (401, 403, 404):
            return None
        raise GitHubError(f"GET {path} failed with HTTP {response.status_code}.")

    def file_text(self, owner: str, repo: str, path: str) -> str | None:
        """The decoded text of a file on the default branch, or None if it doesn't exist."""
        data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        if not isinstance(data, dict) or data.get("type") != "file":
            return None
        content = data.get("content")
        if not isinstance(content, str):
            return None
        return base64.b64decode(content).decode("utf-8", errors="replace")

    def list_dir(self, owner: str, repo: str, path: str) -> list[str] | None:
        """File names in a directory, or None if the directory doesn't exist."""
        data = self.get(f"/repos/{owner}/{repo}/contents/{path}")
        if not isinstance(data, list):
            return None
        return [str(item["name"]) for item in data if item.get("type") == "file"]
