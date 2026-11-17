# repo-posture

**A read-only scanner that scores a GitHub repository's security and governance posture and tells
you what to fix first.**

[![ci](https://github.com/Ajmoylan/repo-posture/actions/workflows/ci.yml/badge.svg)](https://github.com/Ajmoylan/repo-posture/actions/workflows/ci.yml)
[![codeql](https://github.com/Ajmoylan/repo-posture/actions/workflows/codeql.yml/badge.svg)](https://github.com/Ajmoylan/repo-posture/actions/workflows/codeql.yml)
[![posture](https://github.com/Ajmoylan/repo-posture/actions/workflows/posture.yml/badge.svg)](https://github.com/Ajmoylan/repo-posture/actions/workflows/posture.yml)

### ▶ [Open the live dashboard](https://ajmoylan.github.io/repo-posture/)

**[ajmoylan.github.io/repo-posture](https://ajmoylan.github.io/repo-posture/)**: score, coverage,
the 13 controls, prioritised remediation, a before/after comparison (85 → 100) and an example
report (MOYLAN//OS, 92/100), from saved CLI reports. You can also import your own JSON report.

```console
$ GITHUB_TOKEN=... repo-posture Ajmoylan/moylan-os
## Posture report: `Ajmoylan/moylan-os`
**Score 92/100** across the checks the scan could see (coverage 100%). 11 passed, 2 failed, 0 unknown.
| ✅ | Default branch protected            | 4 | A ruleset requires pull requests on main. |
| ✅ | Code scanning (CodeQL)              | 4 | CodeQL runs in a workflow (advanced setup). |
| ✅ | Secret scanning push protection     | 4 | Enabled: pushes containing detected secrets are blocked. |
| ❌ | Code owners                         | 2 | No CODEOWNERS file: reviews aren't routed to the right owners. |
...
### Fix first
1. **Code owners** (weight 2): how to fix → docs.github.com
```

## The business problem

Teams adopting GitHub Enterprise, GitHub Advanced Security or Copilot usually start from the same
question: *how well are our repositories protected today, and what should we switch on first?*
The answer is spread across settings pages, workflow files and repository files: whether CodeQL
runs, whether secret scanning and push protection are on, whether Dependabot updates
dependencies, whether `main` accepts direct pushes, and whether CI workflows pin their actions and
limit their tokens. Checking this by hand for each repository is slow and inconsistent, so it's
often skipped, and adoption conversations start without a baseline.

repo-posture turns that checklist into a repeatable, explainable scan:

- **One command per repository**, read-only, with a 0–100 score and a prioritised fix list that
  links each failure to GitHub's own documentation.
- **Honest about what it can't see.** Some settings (secret scanning, push protection, Dependabot
  security updates) are only visible to repository admins. Those checks report **unknown**, are
  left out of the score, and lower the reported **coverage**, so a low-access scan never looks
  better or worse than it is.
- **Runs in CI as a policy gate** (`--min-score`), so posture can't quietly regress.

## The dashboard

A static web dashboard ([`dashboard/`](dashboard/)) for presenting scan results to engineering
leaders and customers, deployed to GitHub Pages by the `pages` workflow.

- **Overview:** score ring, assessment coverage and pass / fail / unknown counts.
- **Controls:** all 13 controls grouped by area (access control, code security, secret
  protection, supply chain, CI/CD hardening, governance), with the GitHub capability behind each.
- **Prioritised remediation:** failures ordered by the score points each fix adds, then the
  unknown controls to verify, with links to GitHub's docs.
- **Before / after:** this repository's first automated scan (85/100, `main` unprotected) against
  the scan after adding the ruleset (100/100), with the controls that changed.
- **Example report:** MOYLAN//OS at 92/100.
- **Import:** load any `repo-posture --format json` report. It's validated (including that the
  score matches its own checks) and stays in the browser tab; nothing is uploaded.
- **Copilot:** what's implemented here, kept separate from recommended Copilot opportunities.

**Security by design:** the page holds **no GitHub token and never calls the GitHub API**. It
shows saved reports with their scan times and sources, never presented as live scans. A strict
Content-Security-Policy allows only the site's own scripts, styles and data. All report text is
rendered as text (never HTML), and links are only created for `https://docs.github.com/` URLs.
The data model is covered by `node --test` in CI and analysed by CodeQL.

Run it locally: `python3 -m http.server -d dashboard 8000`, then open http://localhost:8000.

## What it checks

| Check | Weight | How it's determined |
|---|---|---|
| Default branch protected | 4 | Rulesets API (`pull_request` rule), then classic branch protection |
| Code scanning (CodeQL) | 4 | `github/codeql-action` in a workflow, or CodeQL default setup |
| Secret scanning | 4 | `security_and_analysis` (admin token) |
| Secret scanning push protection | 4 | `security_and_analysis` (admin token) |
| Dependabot security updates | 3 | `security_and_analysis` (admin token) |
| Dependabot version updates | 3 | `.github/dependabot.yml` |
| GitHub Actions CI | 3 | Workflows in `.github/workflows` |
| Actions pinned to full commit SHAs | 3 | Every `uses:` reference in every workflow |
| Least-privilege `GITHUB_TOKEN` | 3 | `permissions:` at workflow level or on every job |
| Dependency review on pull requests | 2 | `actions/dependency-review-action` in a workflow |
| Code owners | 2 | `CODEOWNERS` in `.github/`, the root or `docs/` |
| Security policy | 2 | `SECURITY.md` in `.github/`, the root or `docs/` |
| License | 1 | GitHub's license detection |

Weights favour controls that prevent incidents (blocked pushes, protected branches, scanning) over
documentation. **Score** = passed weight ÷ weight of the checks the scan could see.
**Coverage** = weight the scan could see ÷ total weight.

## Architecture

```
cli.py ──► scanner.py ──► checks.py (13 checks, each pass / fail / unknown)
                │               │
                │               └──► workflows.py  pure YAML analysis: pinning, permissions, actions used
                └──► github.py  read-only REST client (GET only, optional token, rate-limit aware)
report.py  ──► Markdown (people, job summaries) or JSON (tools, dashboards)
dashboard/ ──► static site: reads saved JSON reports, validates and visualises them (no API calls)
```

- **Python 3.11+**, two runtime dependencies (`httpx`, `PyYAML`), locked with `uv.lock`.
- Repository data is fetched once per scan into a `RepoContext`, and each check is a small
  function, so adding a check means one function and one test.
- A rate-limited or failing API is an **error** (exit 2), never reported as a missing control.

## Security and supply chain (applied to this repository too)

| Control | Where |
|---|---|
| CodeQL (`security-extended`) for Python, the dashboard's JavaScript **and** the workflows | `.github/workflows/codeql.yml` |
| Dependency review: blocks moderate+ vulnerabilities and non-allow-listed licenses | `.github/workflows/dependency-review.yml` |
| Dependabot version updates for `uv` and GitHub Actions, grouped | `.github/dependabot.yml` |
| Secret scanning, push protection, Dependabot security updates | Repository settings |
| Ruleset on `main`: pull request + passing checks required, no force-push or deletion | Repository settings |
| Every action pinned to a full commit SHA; every workflow declares minimal `permissions` | All workflows |
| Workflow inputs passed via environment variables, never interpolated into scripts | `posture.yml` |
| CODEOWNERS, PR template with a security checklist, private vulnerability reporting | `.github/`, `SECURITY.md` |

The scanner itself only issues `GET` requests and never logs or stores the token.

## Developer productivity and automation

- **`posture` workflow:** scans this repository on every push to `main`, weekly and on demand
  (any list of repositories), writes the report to the run's **job summary**, and fails below the
  policy threshold (default 80).
- **`ci` workflow:** Ruff lint and format, `mypy --strict` and pytest with a **90% coverage floor**
  on Python 3.11, 3.12 and 3.13, from the lockfile only, plus the dashboard's tests.
- **`pages` workflow:** tests the dashboard, then publishes it to GitHub Pages on changes to `main`.
- **Dependabot** keeps dependencies and pinned action SHAs current through grouped PRs that must
  pass the same gates.

## Measured results

Measured on 17 November 2026 (no estimates):

| Measure | Result |
|---|---|
| Automated tests | 35 Python tests, **99% line coverage**, no network access (GitHub API mocked with respx); 9 dashboard tests (`node --test`) |
| Static checks | Ruff (including the `S` security rules) and `mypy --strict`: clean |
| Known-vulnerable dependencies (`pip-audit`) | none found |
| Scan time | about **3–4 seconds per repository** for 13 checks (local run, including start-up) |
| Real scan, admin token (`Ajmoylan/moylan-os`) | **92/100, 100% coverage**: 11 passed; found 2 gaps (CODEOWNERS, license) |
| Same repository, no token | 89/100, **71% coverage**: the 3 admin-only checks correctly reported unknown |
| This repository, first automated scan ([posture run](https://github.com/Ajmoylan/repo-posture/actions/runs/44112645762)) | **85/100**: flagged that `main` accepted direct pushes (the ruleset wasn't created yet) |
| This repository, after adding the `protect-main` ruleset | **100/100, 100% coverage** (admin token); 100/100 at 71% coverage without one |

## Run it

```bash
# Requires uv (https://docs.astral.sh/uv/)
git clone https://github.com/Ajmoylan/repo-posture && cd repo-posture
uv sync

uv run repo-posture owner/repo                      # Markdown report
uv run repo-posture owner/repo --format json        # JSON for tooling
uv run repo-posture org/a org/b --min-score 80      # CI gate: exit 1 below 80

uv run pytest                                       # tests + coverage
uv run ruff check . && uv run mypy                  # lint + types
```

Set `GITHUB_TOKEN` (or `GH_TOKEN`) for higher rate limits and admin-only checks. A
**fine-grained, read-only** token is enough: Metadata, Contents and Administration (read), plus
Code scanning alerts (read) for default-setup detection. Without a token, public repositories can
be scanned within GitHub's unauthenticated rate limit.

Exit codes: `0` success, `1` a repository scored below `--min-score`, `2` an error (not found,
rate limited, API failure).

## GitHub Copilot

How Copilot could fit this workflow, and what has and hasn't been demonstrated, is in
[docs/COPILOT.md](docs/COPILOT.md).

**Development note:** This project was developed using AI-assisted coding tools. Its
functionality is supported by automated tests and reproducible security scans. The GitHub Copilot
documentation distinguishes proposed applications from capabilities actually demonstrated.

## Limitations and next steps

- Scans one repository at a time; organisation-wide scans (listing an org's repositories) and
  trends over time are natural next steps, not implemented. The dashboard shows saved reports;
  it doesn't run scans.
- Doesn't yet read organisation-level rulesets or security configurations separately; they're
  reflected only where the branch rules API includes them.
- Checks for the presence of controls, not their quality (for example, it doesn't review CodeQL
  query suites or Dependabot schedules).

## License

[MIT](LICENSE)
