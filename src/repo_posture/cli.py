"""Command line: `repo-posture owner/repo [--format md|json] [--min-score N]`."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from repo_posture import __version__
from repo_posture.github import GitHubClient, GitHubError
from repo_posture.report import to_json, to_markdown
from repo_posture.scanner import scan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-posture",
        description="Scan GitHub repositories' security and governance posture (read-only).",
    )
    parser.add_argument("repositories", nargs="+", help="owner/repo or a github.com URL")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        metavar="N",
        help="exit with status 1 if any repository scores below N (a CI policy gate)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    below: list[str] = []
    try:
        with GitHubClient(token) as client:
            for repository in args.repositories:
                report = scan(client, repository)
                print(to_json(report) if args.format == "json" else to_markdown(report))
                if args.min_score is not None and report.score < args.min_score:
                    below.append(f"{report.repository} ({report.score})")
    except (GitHubError, ValueError) as error:
        print(f"repo-posture: {error}", file=sys.stderr)
        return 2
    if below:
        print(
            f"repo-posture: below the minimum score of {args.min_score}: {', '.join(below)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
