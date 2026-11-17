"""The posture checks. Each returns a CheckResult: pass, fail or unknown, never a guess.

"unknown" means the scan couldn't see the setting (for example, secret scanning status is only
visible to repository administrators). Unknown checks are excluded from the score and counted in
the report's coverage, so a low-access scan can't look better or worse than it is.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from repo_posture import workflows as wf
from repo_posture.github import GitHubClient

DOCS = "https://docs.github.com/en"


class Status(StrEnum):
    PASS = "pass"  # noqa: S105 (a status, not a password)
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckResult:
    id: str
    title: str
    status: Status
    detail: str
    weight: int
    remediation: str
    """Link to GitHub's documentation for fixing a failure."""


@dataclass
class RepoContext:
    """Everything the checks need, fetched once per scan."""

    owner: str
    repo: str
    metadata: dict[str, Any]
    workflows: list[wf.Workflow] | None
    """None if .github/workflows doesn't exist."""
    client: GitHubClient

    @property
    def default_branch(self) -> str:
        return str(self.metadata.get("default_branch", "main"))

    def has_file(self, *paths: str) -> str | None:
        for path in paths:
            if self.client.file_text(self.owner, self.repo, path) is not None:
                return path
        return None


def _result(
    check_id: str, title: str, weight: int, remediation: str
) -> Callable[[Status, str], CheckResult]:
    def make(status: Status, detail: str) -> CheckResult:
        return CheckResult(check_id, title, status, detail, weight, f"{DOCS}/{remediation}")

    return make


def check_security_policy(ctx: RepoContext) -> CheckResult:
    r = _result(
        "security-policy",
        "Security policy (SECURITY.md)",
        2,
        "code-security/getting-started/adding-a-security-policy-to-your-repository",
    )
    found = ctx.has_file("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")
    if found:
        return r(Status.PASS, f"Found {found}.")
    return r(Status.FAIL, "No SECURITY.md: reporters don't know how to disclose a vulnerability.")


def check_dependabot_config(ctx: RepoContext) -> CheckResult:
    r = _result(
        "dependabot-version-updates",
        "Dependabot version updates",
        3,
        "code-security/dependabot/dependabot-version-updates/configuring-dependabot-version-updates",
    )
    found = ctx.has_file(".github/dependabot.yml", ".github/dependabot.yaml")
    if found:
        return r(Status.PASS, f"Configured in {found}.")
    return r(Status.FAIL, "No .github/dependabot.yml: dependencies are only updated by hand.")


def check_codeowners(ctx: RepoContext) -> CheckResult:
    r = _result(
        "codeowners",
        "Code owners",
        2,
        "repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners",
    )
    found = ctx.has_file(".github/CODEOWNERS", "CODEOWNERS", "docs/CODEOWNERS")
    if found:
        return r(Status.PASS, f"Found {found}.")
    return r(Status.FAIL, "No CODEOWNERS file: reviews aren't routed to the right owners.")


def check_ci(ctx: RepoContext) -> CheckResult:
    r = _result("ci-workflows", "GitHub Actions CI", 3, "actions/about-github-actions")
    if ctx.workflows:
        names = ", ".join(w.name for w in ctx.workflows)
        return r(Status.PASS, f"{len(ctx.workflows)} workflow(s): {names}.")
    return r(Status.FAIL, "No workflows in .github/workflows.")


def check_code_scanning(ctx: RepoContext) -> CheckResult:
    r = _result(
        "code-scanning",
        "Code scanning (CodeQL)",
        4,
        "code-security/code-scanning/enabling-code-scanning/configuring-default-setup-for-code-scanning",
    )
    if ctx.workflows and wf.uses_action(ctx.workflows, "github/codeql-action"):
        return r(Status.PASS, "CodeQL runs in a workflow (advanced setup).")
    setup = ctx.client.get(f"/repos/{ctx.owner}/{ctx.repo}/code-scanning/default-setup")
    if isinstance(setup, dict):
        if setup.get("state") == "configured":
            return r(Status.PASS, "CodeQL default setup is configured.")
        return r(Status.FAIL, "Code scanning isn't configured.")
    return r(
        Status.UNKNOWN,
        "No CodeQL workflow; default setup isn't visible without a token with access to it.",
    )


def check_dependency_review(ctx: RepoContext) -> CheckResult:
    r = _result(
        "dependency-review",
        "Dependency review on pull requests",
        2,
        "code-security/supply-chain-security/understanding-your-software-supply-chain/configuring-the-dependency-review-action",
    )
    if ctx.workflows and wf.uses_action(ctx.workflows, "actions/dependency-review-action"):
        return r(Status.PASS, "dependency-review-action runs in a workflow.")
    return r(Status.FAIL, "Pull requests aren't checked for vulnerable or disallowed dependencies.")


def check_pinned_actions(ctx: RepoContext) -> CheckResult:
    r = _result(
        "pinned-actions",
        "Actions pinned to full commit SHAs",
        3,
        "actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#using-third-party-actions",
    )
    if not ctx.workflows:
        return r(Status.UNKNOWN, "No workflows to check.")
    loose = wf.unpinned(ctx.workflows)
    if not loose:
        return r(Status.PASS, "Every action is pinned to a full commit SHA.")
    shown = "; ".join(loose[:5]) + (f"; and {len(loose) - 5} more" if len(loose) > 5 else "")
    return r(Status.FAIL, f"{len(loose)} unpinned: {shown}.")


def check_workflow_permissions(ctx: RepoContext) -> CheckResult:
    r = _result(
        "workflow-permissions",
        "Least-privilege GITHUB_TOKEN",
        3,
        "actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token",
    )
    if not ctx.workflows:
        return r(Status.UNKNOWN, "No workflows to check.")
    missing = [w.name for w in ctx.workflows if not wf.declares_permissions(w)]
    if not missing:
        return r(Status.PASS, "Every workflow declares its token permissions.")
    return r(Status.FAIL, f"No `permissions:` in {', '.join(missing)}.")


def check_branch_protection(ctx: RepoContext) -> CheckResult:
    r = _result(
        "branch-protection",
        "Default branch protected",
        4,
        "repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets",
    )
    branch = ctx.default_branch
    rules = ctx.client.get(f"/repos/{ctx.owner}/{ctx.repo}/rules/branches/{branch}")
    types = {str(rule.get("type")) for rule in rules or [] if isinstance(rule, dict)}
    if "pull_request" in types:
        return r(Status.PASS, f"A ruleset requires pull requests on {branch}.")
    info = ctx.client.get(f"/repos/{ctx.owner}/{ctx.repo}/branches/{branch}")
    if isinstance(info, dict) and info.get("protected"):
        return r(Status.PASS, f"Branch protection is enabled on {branch}.")
    if rules is None and info is None:
        return r(Status.UNKNOWN, f"Couldn't read the rules for {branch}.")
    return r(Status.FAIL, f"{branch} accepts direct pushes: no pull-request rule or protection.")


def _security_feature(ctx: RepoContext, key: str) -> str | None:
    analysis = ctx.metadata.get("security_and_analysis")
    if not isinstance(analysis, dict):
        return None
    feature = analysis.get(key)
    return str(feature.get("status")) if isinstance(feature, dict) else None


def check_secret_scanning(ctx: RepoContext) -> CheckResult:
    r = _result(
        "secret-scanning",
        "Secret scanning",
        4,
        "code-security/secret-scanning/enabling-secret-scanning-features/enabling-secret-scanning-for-your-repository",
    )
    status = _security_feature(ctx, "secret_scanning")
    if status is None:
        return r(Status.UNKNOWN, "Only visible with an admin token.")
    if status == "enabled":
        return r(Status.PASS, "Enabled.")
    return r(Status.FAIL, "Disabled: committed credentials won't be detected.")


def check_push_protection(ctx: RepoContext) -> CheckResult:
    r = _result(
        "push-protection",
        "Secret scanning push protection",
        4,
        "code-security/secret-scanning/enabling-secret-scanning-features/enabling-push-protection-for-your-repository",
    )
    status = _security_feature(ctx, "secret_scanning_push_protection")
    if status is None:
        return r(Status.UNKNOWN, "Only visible with an admin token.")
    if status == "enabled":
        return r(Status.PASS, "Enabled: pushes containing detected secrets are blocked.")
    return r(Status.FAIL, "Disabled: secrets can be pushed before anyone notices.")


def check_dependabot_alerts(ctx: RepoContext) -> CheckResult:
    r = _result(
        "dependabot-security-updates",
        "Dependabot security updates",
        3,
        "code-security/dependabot/dependabot-security-updates/configuring-dependabot-security-updates",
    )
    status = _security_feature(ctx, "dependabot_security_updates")
    if status is None:
        return r(Status.UNKNOWN, "Only visible with an admin token.")
    if status == "enabled":
        return r(Status.PASS, "Enabled: fixes for vulnerable dependencies are proposed as PRs.")
    return r(Status.FAIL, "Disabled.")


def check_license(ctx: RepoContext) -> CheckResult:
    r = _result(
        "license",
        "License",
        1,
        "repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository",
    )
    license_info = ctx.metadata.get("license")
    if isinstance(license_info, dict) and license_info.get("spdx_id"):
        return r(Status.PASS, f"{license_info['spdx_id']}.")
    return r(Status.FAIL, "No license detected: others can't safely reuse the code.")


ALL_CHECKS: tuple[Callable[[RepoContext], CheckResult], ...] = (
    check_branch_protection,
    check_code_scanning,
    check_secret_scanning,
    check_push_protection,
    check_dependabot_alerts,
    check_dependabot_config,
    check_dependency_review,
    check_ci,
    check_pinned_actions,
    check_workflow_permissions,
    check_codeowners,
    check_security_policy,
    check_license,
)
