"""Render a RepoReport as Markdown (for people and job summaries) or JSON (for tools)."""

from __future__ import annotations

import json

from repo_posture.checks import Status
from repo_posture.scanner import RepoReport

ICONS = {Status.PASS: "✅", Status.FAIL: "❌", Status.UNKNOWN: "❔"}


def to_json(report: RepoReport) -> str:
    return json.dumps(
        {
            "repository": report.repository,
            "scanned_at": report.scanned_at,
            "score": report.score,
            "coverage": report.coverage,
            "checks": [
                {
                    "id": r.id,
                    "title": r.title,
                    "status": r.status.value,
                    "weight": r.weight,
                    "detail": r.detail,
                    "remediation": r.remediation,
                }
                for r in report.results
            ],
        },
        indent=2,
        ensure_ascii=False,
    )


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def to_markdown(report: RepoReport) -> str:
    counts = {s: sum(1 for r in report.results if r.status is s) for s in Status}
    lines = [
        f"## Posture report: `{report.repository}`",
        "",
        f"**Score {report.score}/100** across the checks the scan could see "
        f"(coverage {report.coverage}%). "
        f"{counts[Status.PASS]} passed, {counts[Status.FAIL]} failed, "
        f"{counts[Status.UNKNOWN]} unknown. Scanned {report.scanned_at}.",
        "",
        "| | Check | Weight | Detail |",
        "|---|---|---|---|",
    ]
    for r in report.results:
        lines.append(f"| {ICONS[r.status]} | {r.title} | {r.weight} | {_cell(r.detail)} |")
    if report.failures:
        lines += ["", "### Fix first", ""]
        for i, r in enumerate(report.failures, 1):
            lines.append(f"{i}. **{r.title}** (weight {r.weight}): [how to fix]({r.remediation})")
    if counts[Status.UNKNOWN]:
        lines += [
            "",
            "_Unknown checks aren't scored. Scan with a token that has admin access to the "
            "repository to see them._",
        ]
    return "\n".join(lines) + "\n"
