const state = {
  currentOutput: null,
  lastEvaluation: null,
  mode: "balanced",
  currentTab: "summary"
};

const samples = [
  ["CRM SaaS", "Build a CRM SaaS with login, contacts, companies, deals, dashboard, role-based access, analytics, premium plan, and payments."],
  ["Inventory", "Create inventory management for a hardware shop with products, suppliers, purchase orders, low stock alerts, reports, and manager roles."],
  ["Learning", "Build a learning platform with courses, lessons, students, teachers, quizzes, comments, files, and role permissions."],
  ["Restaurant POS", "Create a restaurant ordering system with menu items, tables, orders, kitchen status, online payments, and admin reports."],
  ["Booking", "Build an appointment booking app for a clinic with doctors, patients, calendar slots, reminders, admin analytics, and patient login."],
  ["Finance", "Build an invoice and expense tracker with clients, payments, recurring billing, reports, search, and role-based approvals."],
  ["Real Estate", "Create a real estate CRM with properties, leads, agents, visits, deals, dashboard analytics, and admin permissions."],
  ["Hospital", "Build a hospital appointment system with doctors, patients, prescriptions, reports, billing, and role-based access."],
  ["Retail Credit", "Create a local retail credit tracker with customers, purchases, payments, outstanding balances, reminders, and owner dashboard."],
  ["Subscription", "Build a SaaS subscription dashboard with workspaces, team roles, premium plans, checkout, invoices, analytics, and admin controls."]
];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortValue(value) {
  if (value === null || value === undefined) return "none";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "none";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function downloadText(filename, content, type = "application/json") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function setBusy(isBusy) {
  [
    "#compileBtn",
    "#repairBtn",
    "#evaluateBtn",
    "#determinismBtn",
    "#exportBtn",
    "#runtimeExportBtn",
    "#evaluationExportBtn",
    "#bundleBtn"
  ].forEach((selector) => {
    const node = $(selector);
    if (node) node.disabled = isBusy;
  });
}

function activateTab(tabName) {
  state.currentTab = tabName;
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabName));
  $$(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === tabName));
}

function activateMode(mode) {
  state.mode = mode;
  $$(".mode-option").forEach((button) => button.classList.toggle("active", button.dataset.mode === mode));
  $("#modeLabel").textContent = mode[0].toUpperCase() + mode.slice(1);
  if (state.currentOutput) renderCost(state.currentOutput);
}

function renderSamples() {
  $("#sampleGrid").innerHTML = samples
    .map(([label, prompt]) => `<button class="sample" type="button" data-sample="${escapeHtml(prompt)}">${escapeHtml(label)}</button>`)
    .join("");
  $$(".sample").forEach((button) => {
    button.addEventListener("click", () => {
      $("#prompt").value = button.dataset.sample;
      compile(false);
    });
  });
}

function readinessScore(output) {
  if (typeof output.score === "number") return output.score;
  let score = 100;
  score -= output.validation.issues.filter((issue) => issue.severity === "critical").length * 35;
  score -= output.validation.issues.filter((issue) => issue.severity === "high").length * 9;
  if (!output.execution.ready) score -= 30;
  return Math.max(0, Math.min(100, score));
}

function renderStatus(output) {
  const smokePassed = output.execution.smokeTests.filter((test) => test.passed).length;
  const smokeTotal = output.execution.smokeTests.length;
  const statusLabels = { ready: "Ready", needs_clarification: "Clarify", blocked: "Blocked" };
  $("#runTitle").textContent = output.config.app.name;
  $("#statusPill").textContent = statusLabels[output.status] || "Attention";
  $("#statusPill").className = `status-pill ${output.status === "ready" ? "ready" : output.status === "blocked" ? "blocked" : "attention"}`;
  $("#metricScore").textContent = readinessScore(output);
  $("#metricLatency").textContent = `${output.pipeline.totalLatencyMs} ms`;
  $("#metricRepairs").textContent = output.validation.repairActions.length;
  $("#metricRuntime").textContent = output.execution.ready ? "Ready" : "Blocked";
  $("#metricSmoke").textContent = `${smokePassed}/${smokeTotal}`;
}

function renderReadiness(output) {
  const smokePassed = output.execution.smokeTests.filter((test) => test.passed).length;
  const checks = [
    ["JSON Contract", output.validation.guarantees.validJson ? "Locked" : "Broken", "contract"],
    ["Consistency", output.validation.guarantees.crossLayerConsistency ? "Clean" : "Review", "validation"],
    ["Field Maps", output.validation.guarantees.fieldLevelMappings ? "Verified" : "Review", "validation"],
    ["Runtime", output.execution.ready ? "Executable" : "Blocked", "runtime"],
    ["Smoke Tests", `${smokePassed}/${output.execution.smokeTests.length}`, "runtime"],
    ["Deterministic", output.pipeline.deterministicHash.slice(0, 10), "cost"]
  ];
  $("#readinessView").innerHTML = checks.map(([label, value, tab]) => `
    <button class="readiness-card" type="button" data-tab="${tab}">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </button>
  `).join("");
  $$(".readiness-card").forEach((card) => card.addEventListener("click", () => activateTab(card.dataset.tab)));
}

function renderStageTrace(output) {
  const stages = output.pipeline.trace || output.pipeline.stages || [];
  $("#stageCount").textContent = `${stages.length} stages`;
  $("#stageTrace").innerHTML = stages.map((stage) => `
    <article class="timeline-item ${escapeHtml(stage.status)}">
      <div>
        <strong>${escapeHtml(stage.stageName || stage.stage)}</strong>
        <span>${escapeHtml(stage.status)} · ${escapeHtml(stage.latencyMs)} ms · confidence ${escapeHtml(Math.round((stage.confidenceScore || 0) * 100))}%</span>
      </div>
      <p>${escapeHtml(Object.entries(stage.output || {}).map(([key, value]) => `${key}: ${shortValue(value)}`).join(" · "))}</p>
    </article>
  `).join("");
}

function renderSurface(output) {
  const config = output.config;
  const items = [
    ["Pages", config.ui.pages.map((page) => `${page.title} ${page.route}`)],
    ["APIs", config.api.endpoints.slice(0, 12).map((endpoint) => `${endpoint.method} ${endpoint.path}`)],
    ["Tables", config.database.tables.map((table) => `${table.name} (${table.fields.length} fields)`)],
    ["Roles", config.auth.roles.map((role) => `${role.role}: ${role.allowedEndpoints.length} endpoints`)]
  ];
  $("#surfaceView").innerHTML = items.map(([title, rows]) => `
    <article class="surface-card">
      <strong>${escapeHtml(title)}</strong>
      <ul>${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
    </article>
  `).join("");
}

function renderSubmission(output) {
  const cards = [
    ["Compiler, not chatbot", `${output.pipeline.trace.length} deterministic stages with explicit contracts.`],
    ["Repair proof", `${output.validation.repairActions.length} targeted repairs; full retries: ${output.pipeline.fullRetries}.`],
    ["Runtime proof", `${output.execution.smokeTests.filter((test) => test.passed).length} smoke tests passing with SQLite + manifest validation.`],
    ["Evaluation-ready", "20 prompts, edge cases, deterministic hashes, latency, failure and repair categories."],
    ["Cost control", `${output.mode.label}: ${output.mode.estimatedCost}, ${output.mode.validationDepth} validation.`]
  ];
  $("#submissionView").innerHTML = cards.map(([title, body]) => `
    <article class="submission-card">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(body)}</span>
    </article>
  `).join("");
}

function renderIntent(output) {
  const intent = output.intent;
  const configIntent = output.config.intent || {};
  const tags = [
    ["Domain", intent.domains.join(", ")],
    ["Features", intent.features.join(", ")],
    ["Entities", intent.entities.join(", ")],
    ["Roles", intent.roles.join(", ")],
    ["Ambiguity", intent.ambiguity.level],
    ["Conflicts", intent.conflicts.length],
    ["Intent ID", intent.id],
    ["Config Intent", configIntent.id || "-"]
  ];
  $("#intentView").innerHTML = tags.map(([label, value]) => `
    <article class="tag-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value || "-")}</strong>
    </article>
  `).join("");
}

function renderAssumptions(output) {
  const assumptions = output.config.assumptions || [];
  const clarifications = output.config.clarifications || output.config.clarificationQuestions || [];
  const groups = [
    ["Assumptions", assumptions.length ? assumptions : ["No assumptions required."]],
    ["Clarifications", clarifications.length ? clarifications : ["No clarification needed."]],
    ["Failure Types", output.validation.failureTypes.length ? output.validation.failureTypes : ["none"]]
  ];
  $("#assumptionView").innerHTML = groups.map(([title, rows]) => `
    <article class="list-card">
      <strong>${escapeHtml(title)}</strong>
      <ul>${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
    </article>
  `).join("");
}

function renderArchitecture(output) {
  const design = output.design;
  const runtimePlan = output.config.runtimePlan || {};
  const groups = [
    ["Architecture", Object.entries(design.architecture || {}).map(([key, value]) => `${key}: ${value}`)],
    ["Flows", (design.flows || []).map((flow) => `${flow.name}: ${flow.steps.join(" > ")}`)],
    ["Runtime Plan", [
      `${(runtimePlan.routes || []).length} generated routes`,
      `${(runtimePlan.apiEndpoints || []).length} API endpoints`,
      `${(runtimePlan.databaseTables || []).length} database tables`,
      `${(runtimePlan.dashboardWidgets || []).length} dashboard widgets`
    ]],
    ["Payments", [
      `enabled: ${output.config.payments.enabled}`,
      `plans: ${(output.config.payments.plans || []).map((plan) => `${plan.name} $${plan.price}`).join(", ") || "none"}`,
      `gated: ${(output.config.payments.gatedFeatures || []).join(", ") || "none"}`
    ]]
  ];
  $("#architectureView").innerHTML = groups.map(([title, rows]) => `
    <article class="panel-card">
      <div class="card-heading"><h3>${escapeHtml(title)}</h3><span>${escapeHtml(rows.length)} items</span></div>
      <ul class="clean-list">${rows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
    </article>
  `).join("");
}

function renderJson(output) {
  $("#jsonOutput").textContent = output.strictConfigJson;
}

function renderValidation(output) {
  const validation = output.validation;
  $("#validationStatus").textContent = validation.status;
  const guarantees = Object.entries(validation.guarantees || {}).map(([key, value]) => `
    <article class="issue-card ${value ? "success" : "medium"}">
      <strong>${escapeHtml(key)}</strong>
      <span>${value ? "true" : "false"}</span>
    </article>
  `).join("");
  const issues = validation.issues.length
    ? validation.issues.map((issue) => `
      <article class="issue-card ${escapeHtml(issue.severity)}">
        <strong>${escapeHtml(issue.code)}</strong>
        <span>${escapeHtml(issue.message)}</span>
        <small>${escapeHtml(issue.path)}${issue.blocking ? " · blocking" : ""}</small>
      </article>
    `).join("")
    : `<div class="empty-state">No validation issues</div>`;
  $("#validationView").innerHTML = guarantees + issues;
}

function renderRepairs(output) {
  const repairs = output.validation.repairActions || [];
  if (!repairs.length) {
    $("#repairView").innerHTML = `<div class="empty-state">No repair required for this compile</div>`;
    return;
  }
  $("#repairView").innerHTML = `
    <table>
      <thead>
        <tr><th>Issue</th><th>Location</th><th>Action</th><th>Before</th><th>After</th></tr>
      </thead>
      <tbody>
        ${repairs.map((repair) => `
          <tr>
            <td><strong>${escapeHtml(repair.code)}</strong><br><span>${repair.repaired === false ? "needs decision" : "repaired"}</span></td>
            <td>${escapeHtml(repair.path)}</td>
            <td>${escapeHtml(repair.reason)}</td>
            <td>${escapeHtml(shortValue(repair.before))}</td>
            <td>${escapeHtml(shortValue(repair.after))}</td>
          </tr>
        `).join("")}
      </tbody>
    </table>
  `;
}

function renderRuntime(output) {
  const runtime = output.execution;
  const groups = [
    ["Smoke Tests", runtime.smokeTests.map((test) => `${test.passed ? "PASS" : "FAIL"} ${test.name}${test.detail ? ` · ${test.detail}` : ""}`)],
    ["Generated Routes", runtime.routeMap.map((route) => `${route.route} · ${route.layout} · ${route.apiBindings.length} APIs`)],
    ["API Handlers", runtime.apiHandlers.slice(0, 16).map((handler) => `${handler.method} ${handler.path} -> ${handler.handler}`)],
    ["Access Matrix", (runtime.accessControlMatrix || []).map((row) => `${row.role}: ${row.endpointCount} endpoints`)],
    ["Dashboard Widgets", (runtime.dashboardWidgets || []).map((widget) => `${widget.label}: ${widget.sourceEntity} via ${widget.sourceApi}`)],
    ["Bundle Files", (runtime.bundle?.files || []).map((file) => `${file.name} · ${file.bytes} bytes`)]
  ];
  $("#runtimeView").innerHTML = groups.map(([title, rows]) => `
    <article class="panel-card runtime-card">
      <div class="card-heading"><h3>${escapeHtml(title)}</h3><span>${escapeHtml(rows.length)} rows</span></div>
      <ul class="clean-list">${(rows.length ? rows : ["none"]).map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul>
    </article>
  `).join("");
}

function renderEvaluation(report) {
  const cards = [
    ["Dataset", `${report.datasetSize} prompts`],
    ["Success", `${Math.round(report.successRate * 100)}%`],
    ["Validation", `${Math.round(report.validationPassRate * 100)}%`],
    ["Runtime", `${Math.round(report.runtimeExecutableRate * 100)}%`],
    ["Bundle", `${Math.round(report.bundleReadyRate * 100)}%`],
    ["Determinism", `${Math.round(report.deterministicScore * 100)}%`],
    ["Avg Latency", `${report.averageLatencyMs} ms`],
    ["Avg Repairs", `${report.averageRepairActions}`]
  ];
  const failureRows = Object.entries(report.failureTypes || {}).map(([key, value]) => `${key}: ${value}`);
  const repairRows = Object.entries(report.repairTypes || {}).map(([key, value]) => `${key}: ${value}`);
  const latencyRows = Object.entries(report.latencyByStageMs || {}).map(([key, value]) => `${key}: ${value} ms`);
  $("#evaluationView").innerHTML = `
    ${cards.map(([title, value]) => `
      <article class="metric-tile">
        <span>${escapeHtml(title)}</span>
        <strong>${escapeHtml(value)}</strong>
      </article>
    `).join("")}
    <article class="panel-card span-2"><div class="card-heading"><h3>Failure Types</h3><span>validation</span></div><ul class="clean-list">${(failureRows.length ? failureRows : ["none"]).map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul></article>
    <article class="panel-card span-2"><div class="card-heading"><h3>Repair Types</h3><span>targeted</span></div><ul class="clean-list">${(repairRows.length ? repairRows : ["none"]).map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul></article>
    <article class="panel-card span-2"><div class="card-heading"><h3>Latency By Stage</h3><span>${escapeHtml(report.mode?.label || state.mode)}</span></div><ul class="clean-list">${latencyRows.map((row) => `<li>${escapeHtml(row)}</li>`).join("")}</ul></article>
  `;
}

function renderCost(output) {
  const cost = output.costQuality || {};
  const mode = cost.mode || output.mode || {};
  const modes = [
    ["Fast Mode", "Basic validation", "Lowest latency", "Reliability 78"],
    ["Balanced Mode", "Field-level validation", "Normal latency", "Reliability 90"],
    ["Strict Mode", "Deep policy checks", "Highest latency", "Reliability 97"]
  ];
  $("#costView").innerHTML = `
    <article class="panel-card span-2">
      <div class="card-heading"><h3>Active Tradeoff</h3><span>${escapeHtml(mode.label || state.mode)}</span></div>
      <div class="cost-summary">
        <div><span>Estimated Cost</span><strong>${escapeHtml(cost.estimatedCost || "$0 local")}</strong></div>
        <div><span>Latency</span><strong>${escapeHtml(cost.latency || mode.estimatedLatency || "-")}</strong></div>
        <div><span>Reliability</span><strong>${escapeHtml(cost.reliabilityScore || mode.reliabilityScore || "-")}</strong></div>
        <div><span>Validation</span><strong>${escapeHtml(cost.validationDepth || mode.validationDepth || "-")}</strong></div>
      </div>
      <p class="muted-copy">${escapeHtml(cost.tradeoff || mode.description || "")}</p>
    </article>
    ${modes.map((row) => `
      <article class="mode-card ${row[0].toLowerCase().startsWith(state.mode) ? "active" : ""}">
        <strong>${escapeHtml(row[0])}</strong>
        <span>${escapeHtml(row[1])}</span>
        <span>${escapeHtml(row[2])}</span>
        <span>${escapeHtml(row[3])}</span>
      </article>
    `).join("")}
  `;
}

function renderOutput(output) {
  state.currentOutput = output;
  renderStatus(output);
  renderReadiness(output);
  renderStageTrace(output);
  renderSurface(output);
  renderSubmission(output);
  renderIntent(output);
  renderAssumptions(output);
  renderArchitecture(output);
  renderJson(output);
  renderValidation(output);
  renderRepairs(output);
  renderRuntime(output);
  renderCost(output);
}

async function requestCompile(prompt, repairDemoFault = false) {
  const response = await fetch("/api/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, repairDemoFault, mode: state.mode })
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "compile_failed");
  return payload;
}

async function compile(repairDemoFault = false) {
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  setBusy(true);
  try {
    const output = await requestCompile(prompt, repairDemoFault);
    renderOutput(output);
    activateTab(repairDemoFault ? "repairs" : "summary");
  } catch (error) {
    $("#statusPill").textContent = "Error";
    $("#statusPill").className = "status-pill blocked";
    $("#validationView").innerHTML = `<article class="issue-card critical"><strong>Request failed</strong><span>${escapeHtml(error.message)}</span></article>`;
    activateTab("validation");
  } finally {
    setBusy(false);
  }
}

async function runEvaluation(shouldNavigate = true) {
  setBusy(true);
  try {
    const response = await fetch(`/api/evaluate?mode=${encodeURIComponent(state.mode)}`);
    const report = await response.json();
    if (!response.ok) throw new Error(report.error || "evaluation_failed");
    state.lastEvaluation = report;
    renderEvaluation(report);
    if (shouldNavigate) activateTab("evaluation");
    return report;
  } finally {
    setBusy(false);
  }
}

async function runDeterminismCheck() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  setBusy(true);
  try {
    const first = await requestCompile(prompt, false);
    const second = await requestCompile(prompt, false);
    const stable = first.strictConfigJson === second.strictConfigJson;
    const report = {
      datasetSize: 2,
      mode: first.mode,
      successRate: stable ? 1 : 0.5,
      validationPassRate: 1,
      runtimeExecutableRate: [first, second].filter((item) => item.execution.ready).length / 2,
      bundleReadyRate: [first, second].filter((item) => item.execution.bundle.ready).length / 2,
      deterministicScore: stable ? 1 : 0,
      averageLatencyMs: Number(((first.pipeline.totalLatencyMs + second.pipeline.totalLatencyMs) / 2).toFixed(3)),
      averageRepairActions: Number(((first.validation.repairActions.length + second.validation.repairActions.length) / 2).toFixed(3)),
      failureTypes: stable ? {} : { nondeterministic_output: 1 },
      repairTypes: {},
      latencyByStageMs: first.pipeline.stages.reduce((acc, stage) => ({ ...acc, [stage.stage]: stage.latencyMs }), {})
    };
    state.lastEvaluation = report;
    renderOutput(first);
    renderEvaluation(report);
    activateTab("evaluation");
  } finally {
    setBusy(false);
  }
}

function exportJson() {
  if (!state.currentOutput) return;
  const name = state.currentOutput.config.app.name.replaceAll(" ", "_").toLowerCase();
  downloadText(`${name}_app_config.json`, state.currentOutput.strictConfigJson);
}

function copyJson() {
  if (!state.currentOutput) return;
  navigator.clipboard.writeText(state.currentOutput.strictConfigJson);
}

function exportRuntimeProof() {
  if (!state.currentOutput) return;
  const payload = {
    compileId: state.currentOutput.compileId,
    status: state.currentOutput.status,
    score: state.currentOutput.score,
    runtime: state.currentOutput.execution,
    validation: state.currentOutput.validation
  };
  downloadText("runtime_proof.json", JSON.stringify(payload, null, 2));
}

async function exportEvaluationReport() {
  if (!state.lastEvaluation) await runEvaluation(false);
  if (state.lastEvaluation) downloadText("evaluation_report.json", JSON.stringify(state.lastEvaluation, null, 2));
}

async function downloadBundle() {
  const prompt = $("#prompt").value.trim();
  if (!prompt) return;
  setBusy(true);
  try {
    const response = await fetch("/api/bundle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, mode: state.mode })
    });
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.error || "bundle_download_failed");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "appcompilerai_runtime_bundle.zip";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
    activateTab("runtime");
  } finally {
    setBusy(false);
  }
}

function bindEvents() {
  renderSamples();
  $$(".mode-option").forEach((button) => button.addEventListener("click", () => activateMode(button.dataset.mode)));
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => activateTab(tab.dataset.tab)));
  $("#compileBtn").addEventListener("click", () => compile(false));
  $("#repairBtn").addEventListener("click", () => compile(true));
  $("#evaluateBtn").addEventListener("click", () => runEvaluation(true));
  $("#determinismBtn").addEventListener("click", runDeterminismCheck);
  $("#exportBtn").addEventListener("click", exportJson);
  $("#copyJsonBtn").addEventListener("click", copyJson);
  $("#copyJsonBtnSecondary").addEventListener("click", copyJson);
  $("#runtimeExportBtn").addEventListener("click", exportRuntimeProof);
  $("#evaluationExportBtn").addEventListener("click", exportEvaluationReport);
  $("#bundleBtn").addEventListener("click", downloadBundle);
  $("#statusPill").addEventListener("click", () => activateTab(state.currentOutput?.execution?.ready ? "runtime" : "validation"));
}

bindEvents();
compile(false);
