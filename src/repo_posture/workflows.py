"""Pure analysis of GitHub Actions workflow files (no network)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Workflow:
    name: str
    """The file name, for example "ci.yml"."""
    data: dict[str, Any]
    uses: tuple[str, ...] = field(default=())
    """Every `uses:` reference in the workflow's job steps and reusable-workflow jobs."""


def parse(name: str, text: str) -> Workflow | None:
    """Parse a workflow file. Returns None if it isn't a valid YAML mapping."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    uses: list[str] = []
    jobs = data.get("jobs")
    if isinstance(jobs, dict):
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            if isinstance(job.get("uses"), str):
                uses.append(job["uses"])
            for step in job.get("steps") or []:
                if isinstance(step, dict) and isinstance(step.get("uses"), str):
                    uses.append(step["uses"])
    return Workflow(name=name, data=data, uses=tuple(uses))


def is_pinned(reference: str) -> bool:
    """True if an action reference is local, a Docker digest, or pinned to a full commit SHA.

    Tags and branches (`@v4`, `@main`) can be moved to different code after review, which is why
    GitHub recommends pinning third-party actions to a full-length commit SHA.
    """
    if reference.startswith("./"):
        return True
    if reference.startswith("docker://"):
        return "@sha256:" in reference
    _, _, ref = reference.partition("@")
    return bool(_FULL_SHA.match(ref))


def unpinned(workflows: list[Workflow]) -> list[str]:
    """`file: reference` for every action not pinned to a full commit SHA."""
    return [f"{wf.name}: {ref}" for wf in workflows for ref in wf.uses if not is_pinned(ref)]


def declares_permissions(workflow: Workflow) -> bool:
    """True if the workflow limits its GITHUB_TOKEN: top-level `permissions`, or on every job."""
    if "permissions" in workflow.data:
        return True
    jobs = workflow.data.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        return False
    return all(isinstance(job, dict) and "permissions" in job for job in jobs.values())


def uses_action(workflows: list[Workflow], action: str) -> bool:
    """True if any workflow uses `action` (owner/name, optionally a sub-path), at any version."""
    for wf in workflows:
        for ref in wf.uses:
            name = ref.partition("@")[0]
            if name == action or name.startswith(action + "/"):
                return True
    return False
