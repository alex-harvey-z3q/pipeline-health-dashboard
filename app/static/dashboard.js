const $ = (selector) => document.querySelector(selector);
const statusClass = (value) => (value || "unknown").toLowerCase().replaceAll(" ", "");
const result = (item) => item.result || item.status || "unknown";
const tests = (item) => item.tests.available ? `${item.tests.passed}/${item.tests.total} passed${item.tests.failed ? `, ${item.tests.failed} failed` : ""}` : "Unavailable";
const escapeHtml = (value) => String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const link = (url, label) => url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>` : "-";

function repositoryTable(items) {
  if (!items.length) return "<p class=\"empty\">No configured repositories.</p>";
  const rows = items.map((item) => {
    const run = item.latest_run;
    return `<tr><td>${escapeHtml(item.project)}</td><td>${escapeHtml(item.repository)}</td><td>${escapeHtml(item.branch)}</td><td><span class="status ${statusClass(item.health)}">${escapeHtml(item.health)}</span></td><td>${run ? escapeHtml(run.pipeline.name) : "No associated pipeline"}</td><td>${run ? escapeHtml(run.run_number || "No run") : "-"}</td><td>${run ? escapeHtml(run.started_at || "-") : "-"}</td><td>${run ? escapeHtml(run.completed_at || "-") : "-"}</td><td>${run ? escapeHtml(tests(run)) : "-"}</td><td>${run ? link(run.run_url, "Open run") : "-"}</td></tr>`;
  }).join("");
  return `<table class="table"><thead><tr><th>Project</th><th>Repository</th><th>Branch</th><th>Health</th><th>Pipeline</th><th>Latest run</th><th>Started</th><th>Completed</th><th>Tests</th><th>Azure DevOps</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRows(container, items, render) { container.innerHTML = items.length ? items.map(render).join("") : "<p class=\"empty\">No items to show.</p>"; }

function render(data) {
  const metrics = [[data.summary.repositories_monitored, "Repositories"], [data.summary.healthy, "Healthy"], [data.summary.failing, "Failing"], [data.summary.running, "Running"], [data.summary.unknown, "Unknown"]];
  $("#summary").innerHTML = metrics.map(([number, label]) => `<div class="metric"><strong>${number}</strong><span>${label}</span></div>`).join("");
  $("#repositories").innerHTML = repositoryTable(data.repositories);
  renderRows($("#smoke-list"), data.smoke_tests, (item) => `<article class="row"><h3>${escapeHtml(item.pipeline.project)} / ${escapeHtml(item.pipeline.name)} <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></h3><p>Run: ${link(item.run_url, item.run_number || "No run")} | Tests: ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.agent_pool || "Unknown")}</p></article>`);
  renderRows($("#supporting-pipeline-list"), data.supporting_pipelines, (item) => `<article class="row"><h3>${escapeHtml(item.pipeline.project)} / ${escapeHtml(item.pipeline.name)} <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></h3><p>Role: ${escapeHtml(item.pipeline.role)} | Run: ${link(item.run_url, item.run_number || "No run")} | Tests: ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.agent_pool || "Unknown")}</p></article>`);
  renderRows($("#pr-list"), data.pull_requests, (pr) => `<article class="row"><h3>${escapeHtml(pr.pr_id ? `PR ${pr.pr_id}: ${pr.title}` : pr.title)}</h3><p>${escapeHtml(pr.project)} / ${escapeHtml(pr.repository)} | ${escapeHtml(pr.source_branch)} to ${escapeHtml(pr.target_branch)} | ${link(pr.url, "Open PR")}</p>${pr.error ? `<p class="error">${escapeHtml(pr.error)}</p>` : pr.validations.map((item) => `<p>${escapeHtml(item.pipeline.name)}: <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span> ${link(item.run_url, item.run_number || "No run")} | ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.agent_pool || "Unknown")}</p>`).join("") || "<p>No configured validation pipelines.</p>"}</article>`);
}

async function refresh() {
  $("#refresh").disabled = true; $("#error").hidden = true;
  try { const response = await fetch("/api/dashboard", {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Dashboard request failed."); render(data); $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`; }
  catch (error) { $("#error").textContent = error.message; $("#error").hidden = false; }
  finally { $("#refresh").disabled = false; }
}
$("#refresh").addEventListener("click", refresh); refresh(); setInterval(refresh, 60000);
