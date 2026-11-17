// Dashboard rendering. All report text is written with textContent (never innerHTML), and links
// are only created for validated https://docs.github.com/ remediation URLs.
import {
  CONTROL_INFO,
  MAX_IMPORT_BYTES,
  compareReports,
  counts,
  grade,
  groupByArea,
  remediationPlan,
  validateReport,
} from "./model.js";

const SVG = "http://www.w3.org/2000/svg";
const STATUS_LABEL = { pass: "Pass", fail: "Fail", unknown: "Unknown" };
const STATUS_ICON = { pass: "✓", fail: "✕", unknown: "?" };
const TALLY_LABEL = { pass: "Passed", fail: "Failed", unknown: "Unknown" };

const state = { reports: [], selected: null };

function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  for (const [name, value] of Object.entries(options.attrs ?? {})) node.setAttribute(name, value);
  for (const child of children) if (child) node.append(child);
  return node;
}

function chip(status) {
  return el("span", { className: `chip chip-${status}` }, [
    el("span", { text: STATUS_ICON[status], attrs: { "aria-hidden": "true" } }),
    el("span", { text: STATUS_LABEL[status] }),
  ]);
}

function formatTime(iso) {
  const date = new Date(iso);
  return `${date.toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  })} UTC`;
}

function ring(score, size = 168, label = "") {
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone = grade(score).tone;
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("width", String(size));
  svg.setAttribute("height", String(size));
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `${label}Score ${score} out of 100`);
  const track = document.createElementNS(SVG, "circle");
  const arc = document.createElementNS(SVG, "circle");
  for (const circle of [track, arc]) {
    circle.setAttribute("cx", String(size / 2));
    circle.setAttribute("cy", String(size / 2));
    circle.setAttribute("r", String(radius));
    circle.setAttribute("fill", "none");
    circle.setAttribute("stroke-width", String(stroke));
  }
  track.setAttribute("class", "ring-track");
  arc.setAttribute("class", `ring-arc tone-${tone}`);
  arc.setAttribute("stroke-linecap", "round");
  arc.setAttribute("stroke-dasharray", `${(circumference * score) / 100} ${circumference}`);
  arc.setAttribute("transform", `rotate(-90 ${size / 2} ${size / 2})`);
  const value = document.createElementNS(SVG, "text");
  value.setAttribute("x", "50%");
  value.setAttribute("y", "48%");
  value.setAttribute("class", "ring-value");
  value.textContent = String(score);
  const caption = document.createElementNS(SVG, "text");
  caption.setAttribute("x", "50%");
  caption.setAttribute("y", "66%");
  caption.setAttribute("class", "ring-caption");
  caption.textContent = "/ 100";
  svg.append(track, arc, value, caption);
  return svg;
}

function renderTabs() {
  const tabs = document.getElementById("report-tabs");
  tabs.replaceChildren(
    ...state.reports.map((entry) => {
      const selected = entry === state.selected;
      const button = el(
        "button",
        {
          className: "tab",
          attrs: { type: "button", role: "tab", "aria-selected": String(selected) },
        },
        [
          el("span", { text: entry.label }),
          el("span", { className: `tab-score tone-${grade(entry.report.score).tone}`, text: String(entry.report.score) }),
        ],
      );
      button.addEventListener("click", () => select(entry));
      return button;
    }),
  );
  const provenance = document.getElementById("provenance");
  provenance.replaceChildren(el("span", { text: state.selected.provenance }));
  if (state.selected.sourceUrl) {
    provenance.append(
      " ",
      el("a", { text: "View the original run ↗", attrs: { href: state.selected.sourceUrl, rel: "noopener" } }),
    );
  }
}

function renderOverview(report) {
  document.getElementById("score-ring").replaceChildren(ring(report.score));
  document.getElementById("score-repo").textContent = report.repository;
  const g = grade(report.score);
  const gradeNode = document.getElementById("score-grade");
  gradeNode.className = `grade tone-${g.tone}`;
  gradeNode.textContent = `${g.label} posture`;
  document.getElementById("score-time").textContent = `Scanned ${formatTime(report.scannedAt)}`;

  document.getElementById("coverage-value").textContent = `${report.coverage}%`;
  const meter = document.getElementById("coverage-meter");
  meter.setAttribute("aria-label", `Coverage ${report.coverage} percent`);
  const fill = el("span", { className: "meter-fill" });
  fill.style.width = `${report.coverage}%`;
  meter.replaceChildren(fill);
  document.getElementById("coverage-note").textContent =
    report.coverage === 100
      ? "Every control was visible to the scan."
      : "Some controls are only visible with an admin token. They're excluded from the score.";

  const c = counts(report);
  document.getElementById("tally").replaceChildren(
    ...["pass", "fail", "unknown"].map((status) =>
      el("li", { className: `tally-item tone-${status}` }, [
        el("span", { className: "tally-number", text: String(c[status]) }),
        el("span", { text: TALLY_LABEL[status] }),
      ]),
    ),
  );
  const stack = document.getElementById("stack-bar");
  stack.setAttribute("aria-label", `${c.pass} passed, ${c.fail} failed, ${c.unknown} unknown`);
  stack.replaceChildren(
    ...["pass", "fail", "unknown"]
      .filter((status) => c[status] > 0)
      .map((status) => {
        const part = el("span", { className: `stack-part bg-${status}` });
        part.style.flexGrow = String(c[status]);
        return part;
      }),
  );
}

function renderControls(report) {
  document.getElementById("areas").replaceChildren(
    ...groupByArea(report).map(([area, checks]) => {
      const passed = checks.filter((check) => check.status === "pass").length;
      return el("article", { className: "card area" }, [
        el("div", { className: "area-head" }, [
          el("h3", { text: area }),
          el("span", { className: "muted small", text: `${passed}/${checks.length} passing` }),
        ]),
        el(
          "ul",
          { className: "controls" },
          checks.map((check) =>
            el("li", { className: `control status-${check.status}` }, [
              el("div", { className: "control-top" }, [
                el("span", { className: "control-title", text: check.title }),
                chip(check.status),
              ]),
              el("p", { className: "control-detail", text: check.detail }),
              el("p", { className: "control-meta" }, [
                el("span", { text: CONTROL_INFO[check.id]?.product ?? "Other" }),
                el("span", { className: "weight", attrs: { title: "Weight" } }, [
                  ...Array.from({ length: Math.min(check.weight, 5) }, () =>
                    el("i", { attrs: { "aria-hidden": "true" } }),
                  ),
                  el("span", { className: "sr-only", text: `Weight ${check.weight}` }),
                ]),
              ]),
            ]),
          ),
        ),
      ]);
    }),
  );
}

function renderPlan(report) {
  const plan = remediationPlan(report);
  const list = document.getElementById("plan");
  if (plan.length === 0) {
    list.replaceChildren(
      el("li", { className: "card plan-empty" }, [
        el("strong", { text: "Nothing to fix. " }),
        el("span", { text: "Every control passed and every control was visible to the scan." }),
      ]),
    );
    return;
  }
  list.replaceChildren(
    ...plan.map((item) => {
      const { check } = item;
      const impact =
        item.kind === "fix"
          ? el("span", { className: "impact tone-pass", text: `+${item.gain} pts` })
          : el("span", { className: "impact tone-unknown", text: "Coverage" });
      const action =
        item.kind === "fix"
          ? "Enable or add this control."
          : "Re-scan with an admin token to verify this control.";
      const body = el("div", { className: "plan-body" }, [
        el("p", { className: "plan-title", text: check.title }),
        el("p", { className: "muted small", text: `${action} ${check.detail}` }),
      ]);
      if (check.remediation) {
        body.append(
          el("a", {
            className: "small",
            text: "GitHub docs: how to fix ↗",
            attrs: { href: check.remediation, rel: "noopener noreferrer" },
          }),
        );
      }
      return el("li", { className: "card plan-item" }, [chip(check.status), body, impact]);
    }),
  );
}

function renderComparison() {
  const before = state.reports.find((entry) => entry.role === "before");
  const after = state.reports.find((entry) => entry.role === "after");
  const container = document.getElementById("compare");
  if (!before || !after) {
    container.replaceChildren(el("p", { className: "muted", text: "Comparison data unavailable." }));
    return;
  }
  const changes = compareReports(before.report, after.report);
  const side = (entry, title) =>
    el("article", { className: "card compare-side" }, [
      el("p", { className: "eyebrow", text: title }),
      ring(entry.report.score, 140, `${title}: `),
      el("p", { className: "muted small", text: `Coverage ${entry.report.coverage}% · ${formatTime(entry.report.scannedAt)}` }),
    ]);
  container.replaceChildren(
    side(before, "Before"),
    el("article", { className: "card compare-changes" }, [
      el("p", { className: "eyebrow", text: `${changes.length} controls changed` }),
      el(
        "ul",
        { className: "changes" },
        changes.map((change) =>
          el("li", {}, [
            el("span", { className: "change-title", text: change.check.title }),
            el("span", { className: "change-flow" }, [chip(change.from), el("span", { text: "→", attrs: { "aria-label": "became" } }), chip(change.to)]),
          ]),
        ),
      ),
      el("p", {
        className: "muted small",
        text: "The admin-only checks were unknown in the first automated scan, which ran without an admin token; the second scan used one.",
      }),
    ]),
    side(after, "After"),
  );
}

function select(entry) {
  state.selected = entry;
  renderTabs();
  renderOverview(entry.report);
  renderControls(entry.report);
  renderPlan(entry.report);
}

function setStatus(message, tone) {
  const status = document.getElementById("import-status");
  status.textContent = message;
  status.className = `status-line tone-${tone}`;
}

async function importFile(file) {
  if (!file) return;
  if (file.size > MAX_IMPORT_BYTES) {
    setStatus("That file is larger than 1 MB, so it isn't a repo-posture report.", "fail");
    return;
  }
  try {
    const report = validateReport(JSON.parse(await file.text()));
    const entry = {
      id: `import-${Date.now()}`,
      label: `${report.repository} (imported)`,
      role: "imported",
      provenance: `Imported from ${file.name} in this browser session. Validated, not uploaded anywhere, and not a live scan.`,
      report,
    };
    state.reports.push(entry);
    select(entry);
    setStatus(`Loaded ${report.repository}: score ${report.score}, coverage ${report.coverage}%.`, "pass");
    document.getElementById("overview").scrollIntoView({ behavior: "smooth" });
  } catch (error) {
    const message = error instanceof SyntaxError ? "The file isn't valid JSON." : error.message;
    setStatus(`Couldn't import: ${message}`, "fail");
  }
}

function setupImport() {
  const input = document.getElementById("file-input");
  input.addEventListener("change", () => {
    importFile(input.files?.[0]);
    input.value = "";
  });
  const zone = document.getElementById("dropzone");
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    importFile(event.dataTransfer?.files?.[0]);
  });
}

async function loadBundledReports() {
  const manifest = await (await fetch("data/reports.json")).json();
  const loaded = await Promise.all(
    manifest.map(async (item) => ({
      id: item.id,
      label: item.label,
      role: item.role,
      provenance: item.provenance,
      sourceUrl: item.source_url?.startsWith("https://github.com/") ? item.source_url : null,
      report: validateReport(await (await fetch(`data/${item.file}`)).json()),
    })),
  );
  state.reports = loaded;
}

async function start() {
  setupImport();
  try {
    await loadBundledReports();
  } catch (error) {
    setStatus(`Couldn't load the bundled reports: ${error.message}`, "fail");
    return;
  }
  renderComparison();
  select(state.reports.find((entry) => entry.role === "example") ?? state.reports[0]);
}

start();
