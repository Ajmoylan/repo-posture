from repo_posture import workflows as wf

from .conftest import GOOD_CI, LOOSE_CI, SHA


def test_parse_collects_step_and_reusable_workflow_uses() -> None:
    text = f"""
jobs:
  a:
    steps:
      - uses: actions/checkout@{SHA}
      - run: echo hi
  b:
    uses: acme/shared/.github/workflows/build.yml@main
"""
    parsed = wf.parse("x.yml", text)
    assert parsed is not None
    assert parsed.uses == (
        f"actions/checkout@{SHA}",
        "acme/shared/.github/workflows/build.yml@main",
    )


def test_parse_rejects_invalid_or_non_mapping_yaml() -> None:
    assert wf.parse("bad.yml", "jobs: [unclosed") is None
    assert wf.parse("list.yml", "- just\n- a list") is None


def test_parse_tolerates_odd_job_shapes() -> None:
    parsed = wf.parse("odd.yml", "jobs:\n  a: nope\n  b:\n    steps:\n      - just-a-string\n")
    assert parsed is not None and parsed.uses == ()


def test_is_pinned() -> None:
    assert wf.is_pinned(f"actions/checkout@{SHA}")
    assert wf.is_pinned("./.github/actions/setup")
    assert wf.is_pinned("docker://alpine@sha256:" + "b" * 64)
    assert not wf.is_pinned("docker://alpine:3.20")
    assert not wf.is_pinned("actions/checkout@v4")
    assert not wf.is_pinned("actions/checkout@main")
    assert not wf.is_pinned(f"actions/checkout@{SHA[:7]}")
    assert not wf.is_pinned("actions/checkout")


def test_unpinned_lists_file_and_reference() -> None:
    loose = wf.parse("ci.yml", LOOSE_CI)
    good = wf.parse("good.yml", GOOD_CI)
    assert loose and good
    assert wf.unpinned([good, loose]) == ["ci.yml: actions/checkout@v4"]


def test_declares_permissions_top_level_or_every_job() -> None:
    top = wf.parse("a.yml", "permissions: {}\njobs:\n  x:\n    steps: []\n")
    every = wf.parse("b.yml", "jobs:\n  x:\n    permissions: {}\n  y:\n    permissions: read-all\n")
    some = wf.parse("c.yml", "jobs:\n  x:\n    permissions: {}\n  y:\n    steps: []\n")
    empty = wf.parse("d.yml", "on: push\n")
    assert top and every and some and empty
    assert wf.declares_permissions(top)
    assert wf.declares_permissions(every)
    assert not wf.declares_permissions(some)
    assert not wf.declares_permissions(empty)


def test_uses_action_matches_name_and_sub_paths_only() -> None:
    good = wf.parse("good.yml", GOOD_CI)
    assert good
    assert wf.uses_action([good], "github/codeql-action")
    assert wf.uses_action([good], "actions/dependency-review-action")
    assert not wf.uses_action([good], "actions/check")
