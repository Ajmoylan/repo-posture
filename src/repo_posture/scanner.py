"""Run every check against one repository and score the result."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from repo_posture import workflows as wf
from repo_posture.checks import ALL_CHECKS, CheckResult, RepoContext, Status
from repo_posture.github import GitHubClient, GitHubError


@dataclass(frozen=True)
class RepoReport:
    repository: str
    scanned_at: str
    results: tuple[CheckResult, ...]

    @property
    def known(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is not Status.UNKNOWN)

    @property
    def score(self) -> int:
        """Weighted share of the checks the scan could see that pass, 0-100."""
        total = sum(r.weight for r in self.known)
        if total == 0:
            return 0
        passed = sum(r.weight for r in self.known if r.status is Status.PASS)
        return round(100 * passed / total)

    @property
    def coverage(self) -> int:
        """Weighted share of all checks the scan could see, 0-100."""
        total = sum(r.weight for r in self.results)
        return round(100 * sum(r.weight for r in self.known) / total) if total else 0

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        """Failed checks, highest weight first: the order to fix them in."""
        failed = [r for r in self.results if r.status is Status.FAIL]
        return tuple(sorted(failed, key=lambda r: -r.weight))


def parse_repository(value: str) -> tuple[str, str]:
    """Accept "owner/repo" or a github.com URL."""
    cleaned = value.strip().rstrip("/").removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        cleaned = cleaned.removeprefix(prefix)
    parts = cleaned.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"Expected owner/repo, got {value!r}.")
    return parts[0], parts[1]


def load_workflows(client: GitHubClient, owner: str, repo: str) -> list[wf.Workflow] | None:
    names = client.list_dir(owner, repo, ".github/workflows")
    if names is None:
        return None
    workflows = []
    for name in sorted(names):
        if not name.endswith((".yml", ".yaml")):
            continue
        text = client.file_text(owner, repo, f".github/workflows/{name}")
        parsed = wf.parse(name, text) if text is not None else None
        if parsed is not None:
            workflows.append(parsed)
    return workflows


def scan(client: GitHubClient, repository: str, *, now: datetime | None = None) -> RepoReport:
    owner, repo = parse_repository(repository)
    metadata = client.get(f"/repos/{owner}/{repo}")
    if not isinstance(metadata, dict):
        raise GitHubError(f"Repository {owner}/{repo} not found or not visible to this token.")
    ctx = RepoContext(
        owner=owner,
        repo=repo,
        metadata=metadata,
        workflows=load_workflows(client, owner, repo),
        client=client,
    )
    results = tuple(check(ctx) for check in ALL_CHECKS)
    stamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return RepoReport(repository=f"{owner}/{repo}", scanned_at=stamp, results=results)
