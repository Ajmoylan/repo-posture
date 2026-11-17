// Pure data model for the dashboard: validation, scoring, grouping, remediation and comparison.
// No DOM and no network, so it runs unchanged in the browser and in `node --test`.

export const STATUSES = ["pass", "fail", "unknown"];
export const MAX_IMPORT_BYTES = 1_000_000;

const REPO_PATTERN = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/;
const TIMESTAMP_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;
const DOCS_PREFIX = "https://docs.github.com/";

/** How each control maps to a GitHub capability, for grouping and for customer conversations. */
export const CONTROL_INFO = {
  "branch-protection": { area: "Access control", product: "Repository rulesets" },
  codeowners: { area: "Access control", product: "CODEOWNERS" },
  "code-scanning": { area: "Code security", product: "GitHub Code Security (CodeQL)" },
  "dependency-review": { area: "Supply chain", product: "Dependency review" },
  "secret-scanning": { area: "Secret protection", product: "GitHub Secret Protection" },
  "push-protection": { area: "Secret protection", product: "GitHub Secret Protection" },
  "dependabot-security-updates": { area: "Supply chain", product: "Dependabot" },
  "dependabot-version-updates": { area: "Supply chain", product: "Dependabot" },
  "pinned-actions": { area: "CI/CD hardening", product: "GitHub Actions" },
  "workflow-permissions": { area: "CI/CD hardening", product: "GitHub Actions" },
  "ci-workflows": { area: "CI/CD hardening", product: "GitHub Actions" },
  "security-policy": { area: "Governance", product: "Security policy" },
  license: { area: "Governance", product: "Licensing" },
};

export const AREAS = [
  "Access control",
  "Code security",
  "Secret protection",
  "Supply chain",
  "CI/CD hardening",
  "Governance",
];

function fail(message) {
  throw new Error(message);
}

function text(value, field, max) {
  if (typeof value !== "string" || value.length === 0 || value.length > max) {
    fail(`"${field}" must be text of up to ${max} characters.`);
  }
  return value;
}

/** Score and coverage recomputed from the checks, exactly as the CLI computes them. */
export function computeScores(checks) {
  const total = checks.reduce((sum, c) => sum + c.weight, 0);
  const known = checks.filter((c) => c.status !== "unknown");
  const knownWeight = known.reduce((sum, c) => sum + c.weight, 0);
  const passed = known.filter((c) => c.status === "pass").reduce((sum, c) => sum + c.weight, 0);
  return {
    score: knownWeight ? Math.round((100 * passed) / knownWeight) : 0,
    coverage: total ? Math.round((100 * knownWeight) / total) : 0,
    passedWeight: passed,
    knownWeight,
    totalWeight: total,
  };
}

/**
 * Validate a report produced by `repo-posture --format json` and return a clean copy containing
 * only known fields. Throws an Error with a readable message when the input isn't a valid report,
 * including when its score or coverage don't match its own checks.
 */
export function validateReport(input) {
  if (typeof input !== "object" || input === null || Array.isArray(input)) {
    fail("The file isn't a repo-posture JSON report.");
  }
  const repository = text(input.repository, "repository", 201);
  if (!REPO_PATTERN.test(repository)) fail('"repository" must look like owner/repo.');
  const scannedAt = text(input.scanned_at, "scanned_at", 20);
  if (!TIMESTAMP_PATTERN.test(scannedAt)) fail('"scanned_at" must be a UTC timestamp.');
  if (!Array.isArray(input.checks) || input.checks.length === 0 || input.checks.length > 50) {
    fail('"checks" must be a list of 1 to 50 checks.');
  }
  const seen = new Set();
  const checks = input.checks.map((check, index) => {
    if (typeof check !== "object" || check === null) fail(`Check ${index + 1} isn't an object.`);
    const id = text(check.id, `checks[${index}].id`, 60);
    if (!/^[a-z0-9-]+$/.test(id)) fail(`Check id "${id}" has unexpected characters.`);
    if (seen.has(id)) fail(`Check "${id}" appears twice.`);
    seen.add(id);
    if (!STATUSES.includes(check.status)) fail(`Check "${id}" has an unknown status.`);
    if (!Number.isInteger(check.weight) || check.weight < 1 || check.weight > 10) {
      fail(`Check "${id}" must have a whole-number weight from 1 to 10.`);
    }
    const remediation =
      typeof check.remediation === "string" && check.remediation.startsWith(DOCS_PREFIX)
        ? check.remediation
        : null;
    return {
      id,
      title: text(check.title, `checks[${index}].title`, 120),
      status: check.status,
      weight: check.weight,
      detail: text(check.detail, `checks[${index}].detail`, 500),
      remediation,
    };
  });
  const computed = computeScores(checks);
  if (input.score !== computed.score || input.coverage !== computed.coverage) {
    fail(
      `The report's score (${input.score}) or coverage (${input.coverage}) doesn't match its ` +
        `own checks (${computed.score}, ${computed.coverage}). It may have been edited.`,
    );
  }
  return { repository, scannedAt, score: computed.score, coverage: computed.coverage, checks };
}

export function counts(report) {
  const result = { pass: 0, fail: 0, unknown: 0 };
  for (const check of report.checks) result[check.status] += 1;
  return result;
}

export function grade(score) {
  if (score >= 90) return { label: "Strong", tone: "pass" };
  if (score >= 75) return { label: "Good", tone: "warn" };
  if (score >= 50) return { label: "Needs work", tone: "warn" };
  return { label: "At risk", tone: "fail" };
}

/** Checks grouped by area, in AREAS order; unrecognised checks go to "Other". */
export function groupByArea(report) {
  const groups = new Map(AREAS.map((area) => [area, []]));
  for (const check of report.checks) {
    const area = CONTROL_INFO[check.id]?.area ?? "Other";
    if (!groups.has(area)) groups.set(area, []);
    groups.get(area).push(check);
  }
  return [...groups].filter(([, checks]) => checks.length > 0);
}

/**
 * Prioritised actions: failures first, ordered by the score points each fix would add, then
 * unknowns (verify with an admin token: improves coverage, not the score).
 */
export function remediationPlan(report) {
  const { passedWeight, knownWeight, score } = computeScores(report.checks);
  const fixes = report.checks
    .filter((c) => c.status === "fail")
    .map((c) => ({
      check: c,
      kind: "fix",
      gain: knownWeight ? Math.round((100 * (passedWeight + c.weight)) / knownWeight) - score : 0,
    }))
    .sort((a, b) => b.gain - a.gain || b.check.weight - a.check.weight);
  const verify = report.checks
    .filter((c) => c.status === "unknown")
    .map((c) => ({ check: c, kind: "verify", gain: 0 }))
    .sort((a, b) => b.check.weight - a.check.weight);
  return [...fixes, ...verify];
}

/** Checks whose status differs between two reports of the same repository. */
export function compareReports(before, after) {
  const previous = new Map(before.checks.map((c) => [c.id, c]));
  return after.checks
    .filter((c) => previous.has(c.id) && previous.get(c.id).status !== c.status)
    .map((c) => ({ check: c, from: previous.get(c.id).status, to: c.status }));
}
