const $ = (selector) => document.querySelector(selector);
const statusClass = (value) => (value || "unknown").toLowerCase().replaceAll(" ", "");
const result = (item) => item.result || item.status || "unknown";
const tests = (item) => item.tests.available ? `${item.tests.passed}/${item.tests.total} passed${item.tests.failed ? `, ${item.tests.failed} failed` : ""}` : "Unavailable";
const escapeHtml = (value) => String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const link = (url, label) => url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>` : "-";

function repositoryTable(items) {
  if (!items.length) return "<p class=\"empty\">No configured repositories.</p>";
  const rows = items.map((item) => {
    const pipelines = item.ci_runs.length
      ? item.ci_runs.map((run) => `<p>${escapeHtml(run.pipeline.name)}: <span class="status ${statusClass(result(run))}">${escapeHtml(result(run))}</span> ${link(run.run_url, run.run_number || "No run")} | ${escapeHtml(tests(run))}</p>`).join("")
      : "-";
    return `<tr><td>${escapeHtml(item.project)}</td><td>${escapeHtml(item.repository)}</td><td>${escapeHtml(item.branch || "Unknown")}</td><td><span class="status ${statusClass(item.health)}">${escapeHtml(item.health)}</span></td><td>${pipelines}</td><td>${escapeHtml(item.status_reason || "-")}</td></tr>`;
  }).join("");
  return `<table class="table"><thead><tr><th>Project</th><th>Repository</th><th>Default branch</th><th>Health</th><th>Default-branch CI pipelines</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRows(container, items, render) { container.innerHTML = items.length ? items.map(render).join("") : "<p class=\"empty\">No items to show.</p>"; }

function reusableTemplatePrs(items) {
  if (!items.length) return "<p class=\"empty\">No open PRs currently modify configured reusable templates.</p>";
  return items.map((pr) => {
    const areas = pr.affected_areas.join(", ");
    const age = pr.age_days === null ? "Unknown age" : `${pr.age_days} day${pr.age_days === 1 ? "" : "s"}`;
    const freshness = pr.stale === null ? "Unknown" : pr.stale ? "Stale" : "Fresh";
    return `<article class="row"><h3>PR ${escapeHtml(pr.pr_id)}: ${escapeHtml(pr.title)} <span class="status ${pr.stale ? "stale" : pr.stale === false ? "fresh" : "unknown"}">${freshness}</span></h3><p>${escapeHtml(pr.project)} / ${escapeHtml(pr.repository)} | ${escapeHtml(pr.source_branch)} to ${escapeHtml(pr.target_branch)} | ${link(pr.web_url, "Open PR")}</p><p>Created: ${escapeHtml(pr.created_at || "Unknown")} | Age: ${escapeHtml(age)}${pr.author ? ` | Author: ${escapeHtml(pr.author)}` : ""}</p><p>Template areas: ${escapeHtml(areas)}</p></article>`;
  }).join("");
}

function render(data) {
  const metrics = [[data.summary.repositories_monitored, "Repositories"], [data.summary.healthy, "Healthy"], [data.summary.failing, "Failing"], [data.summary.running, "Running"], [data.summary.unknown, "Unknown"]];
  $("#summary").innerHTML = metrics.map(([number, label]) => `<div class="metric"><strong>${number}</strong><span>${label}</span></div>`).join("");
  $("#repositories").innerHTML = repositoryTable(data.repositories);
  $("#template-pr-list").innerHTML = reusableTemplatePrs(data.reusable_template_prs || []);
  renderRows($("#smoke-list"), data.smoke_tests, (item) => `<article class="row"><h3>${escapeHtml(item.pipeline.project)} / ${escapeHtml(item.pipeline.name)} <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></h3><p>Run: ${link(item.run_url, item.run_number || "No run")} | Tests: ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.agent_pool || "Unknown")}</p></article>`);
  renderRows($("#supporting-pipeline-list"), data.supporting_pipelines, (item) => `<article class="row"><h3>${escapeHtml(item.pipeline.project)} / ${escapeHtml(item.pipeline.name)} <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></h3><p>Role: ${escapeHtml(item.pipeline.role)} | Run: ${link(item.run_url, item.run_number || "No run")} | Tests: ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.agent_pool || "Unknown")}</p></article>`);
}

async function refresh() {
  $("#refresh").disabled = true; $("#error").hidden = true;
  try { const response = await fetch("/api/dashboard", {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Dashboard request failed."); render(data); $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`; }
  catch (error) { $("#error").textContent = error.message; $("#error").hidden = false; }
  finally { $("#refresh").disabled = false; }
}
$("#refresh").addEventListener("click", refresh); refresh(); setInterval(refresh, 60000);
