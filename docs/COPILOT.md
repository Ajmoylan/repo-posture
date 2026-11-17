# GitHub Copilot and this project

**What's demonstrated here:** a working scanner, its tests and the CI, security and automation
around it. **What isn't:** this repository makes no claim that GitHub Copilot was used to build
it, and contains no measurements of Copilot's impact. This page describes where Copilot would fit
in this workflow, based on Copilot's documented features, so the claims can be checked.

## Where Copilot could help in this workflow

| Task in this project | Copilot feature | How it would help | What stays with the developer |
|---|---|---|---|
| Adding a new check (one function in `checks.py`) | Code completion, Copilot Chat in the IDE | Draft the function from the existing pattern and a docstring | Deciding what the check should prove, and the pass/fail/unknown rules |
| Writing the tests for that check | Copilot Chat (`/tests`) | Propose respx-mocked cases following `tests/conftest.py` | Making sure failure and "unknown" paths are tested, not just the happy path |
| Explaining a CodeQL alert | Copilot Autofix for code scanning | Suggest a fix on the alert, reviewed in a PR | Reviewing the fix; CI and CodeQL must pass again |
| Reviewing pull requests | Copilot code review | A first-pass review comment on each PR | CODEOWNERS approval is still required by the ruleset |
| Writing workflow YAML | Copilot Chat | Draft jobs and steps | Pinning actions to SHAs and keeping `permissions` minimal: the scanner checks both |
| Small, well-defined issues (for example, "add a check for `.github/FUNDING.yml`") | Copilot coding agent | Open a draft PR from an issue | The same CI, CodeQL, dependency review and code-owner review gates apply |

## Guardrails that apply whatever writes the code

The controls in this repository don't trust any author, human or AI:

- the ruleset requires a pull request and passing checks on `main`;
- CodeQL, dependency review, Ruff's security rules and `mypy --strict` run on every PR;
- tests must keep coverage at or above 90%;
- secret scanning with push protection blocks committed credentials.

## How Copilot's impact could be measured (not yet done)

If Copilot were adopted here, these would be the honest measures, compared over the same kind of
work before and after:

- time from issue opened to PR merged for similar-sized changes;
- PRs that pass CI on the first run;
- test coverage and CodeQL alerts per change (quality must not drop);
- for organisations, GitHub's Copilot usage metrics (acceptance rates and active users) rather
  than anecdotes.
