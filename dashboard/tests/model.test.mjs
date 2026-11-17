// Run with: node --test dashboard/tests
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  compareReports,
  computeScores,
  counts,
  grade,
  groupByArea,
  remediationPlan,
  validateReport,
} from "../js/model.js";

const load = (name) =>
  JSON.parse(readFileSync(new URL(`../data/${name}.json`, import.meta.url), "utf8"));

test("bundled reports are genuine CLI output: valid and internally consistent", () => {
  const scores = Object.fromEntries(
    ["moylan-os", "repo-posture-before", "repo-posture-after"].map((name) => {
      const report = validateReport(load(name));
      assert.equal(report.checks.length, 13);
      return [name, [report.score, report.coverage]];
    }),
  );
  assert.deepEqual(scores, {
    "moylan-os": [92, 100],
    "repo-posture-before": [85, 71],
    "repo-posture-after": [100, 100],
  });
});

test("the manifest lists every bundled report exactly once", () => {
  const manifest = load("reports");
  assert.deepEqual(manifest.map((m) => m.role).sort(), ["after", "before", "example"]);
  for (const entry of manifest) assert.ok(load(entry.file.replace(".json", "")));
});

test("scores match the CLI's formula", () => {
  const checks = [
    { status: "pass", weight: 3 },
    { status: "fail", weight: 1 },
    { status: "unknown", weight: 4 },
  ];
  assert.deepEqual(computeScores(checks), {
    score: 75,
    coverage: 50,
    passedWeight: 3,
    knownWeight: 4,
    totalWeight: 8,
  });
  assert.equal(computeScores([{ status: "unknown", weight: 2 }]).score, 0);
});

test("edited scores are rejected", () => {
  const report = load("moylan-os");
  report.score = 100;
  assert.throws(() => validateReport(report), /doesn't match its own checks/);
});

test("malformed input is rejected with a readable message", () => {
  const base = load("moylan-os");
  const cases = [
    [null, /isn't a repo-posture JSON report/],
    [[], /isn't a repo-posture JSON report/],
    [{ ...base, repository: "<script>" }, /owner\/repo/],
    [{ ...base, scanned_at: "yesterday" }, /UTC timestamp/],
    [{ ...base, checks: [] }, /1 to 50 checks/],
    [{ ...base, checks: [null] }, /isn't an object/],
    [{ ...base, checks: [{ ...base.checks[0], id: "Bad Id" }] }, /unexpected characters/],
    [{ ...base, checks: [base.checks[0], base.checks[0]] }, /appears twice/],
    [{ ...base, checks: [{ ...base.checks[0], status: "maybe" }] }, /unknown status/],
    [{ ...base, checks: [{ ...base.checks[0], weight: 0 }] }, /weight from 1 to 10/],
    [{ ...base, checks: [{ ...base.checks[0], title: "" }] }, /title/],
  ];
  for (const [input, message] of cases) assert.throws(() => validateReport(input), message);
});

test("remediation links are kept only for docs.github.com", () => {
  const report = load("moylan-os");
  report.checks[0].remediation = "javascript:alert(1)";
  report.checks[1].remediation = "https://evil.example/docs.github.com/";
  const clean = validateReport(report);
  assert.equal(clean.checks[0].remediation, null);
  assert.equal(clean.checks[1].remediation, null);
  assert.match(clean.checks[2].remediation, /^https:\/\/docs\.github\.com\//);
});

test("remediation plan: failures by points gained, then unknowns", () => {
  const moylan = validateReport(load("moylan-os"));
  const plan = remediationPlan(moylan);
  assert.deepEqual(
    plan.map((p) => [p.check.id, p.kind, p.gain]),
    [
      ["codeowners", "fix", 5],
      ["license", "fix", 3],
    ],
  );
  const before = validateReport(load("repo-posture-before"));
  assert.deepEqual(
    remediationPlan(before).map((p) => [p.check.id, p.kind]),
    [
      ["branch-protection", "fix"],
      ["secret-scanning", "verify"],
      ["push-protection", "verify"],
      ["dependabot-security-updates", "verify"],
    ],
  );
  assert.deepEqual(remediationPlan(validateReport(load("repo-posture-after"))), []);
});

test("before/after comparison lists the controls that changed", () => {
  const before = validateReport(load("repo-posture-before"));
  const after = validateReport(load("repo-posture-after"));
  assert.deepEqual(
    compareReports(before, after).map((c) => [c.check.id, c.from, c.to]),
    [
      ["branch-protection", "fail", "pass"],
      ["secret-scanning", "unknown", "pass"],
      ["push-protection", "unknown", "pass"],
      ["dependabot-security-updates", "unknown", "pass"],
    ],
  );
});

test("counts, grades and areas", () => {
  const moylan = validateReport(load("moylan-os"));
  assert.deepEqual(counts(moylan), { pass: 11, fail: 2, unknown: 0 });
  assert.equal(grade(92).label, "Strong");
  assert.equal(grade(80).label, "Good");
  assert.equal(grade(60).label, "Needs work");
  assert.equal(grade(10).label, "At risk");
  const areas = groupByArea(moylan);
  assert.equal(areas.reduce((n, [, checks]) => n + checks.length, 0), 13);
  const other = groupByArea({ checks: [{ id: "custom-check", status: "pass", weight: 1 }] });
  assert.deepEqual(other.map(([area]) => area), ["Other"]);
});
