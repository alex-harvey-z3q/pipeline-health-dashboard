const $ = (selector) => document.querySelector(selector);
const statusClass = (value) => (value || "unknown").toLowerCase().replaceAll(" ", "");
const result = (item) => item.result || item.status || "unknown";
const tests = (item) => `${item.tests.passed}/${item.tests.total} passed${item.tests.failed ? `, ${item.tests.failed} failed` : ""}`;
const escapeHtml = (value) => String(value || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
const link = (url, label) => url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>` : "-";

function provenance(item) {
  if (!item.provenance) return "<p class=\"provenance\"><strong>Provenance</strong><br>Not supplied for this run.</p>";
  const image = item.provenance.image_build;
  return `<p class="provenance"><strong>Explicit provenance</strong><br>Agent pool: ${escapeHtml(item.provenance.agent_pool || item.reported_agent_pool || "not supplied")}<br>Image: ${escapeHtml(item.provenance.image_version || "not supplied")}<br>Image build: ${image ? escapeHtml(`${image.pipeline_key} #${image.run_id}${image.version ? ` (${image.version})` : ""}`) : "not supplied"}</p>`;
}

function pipelineTable(items) {
  if (!items.length) return "<p class=\"empty\">No configured pipelines.</p>";
  const rows = items.map((item) => `<tr><td>${escapeHtml(item.pipeline.project)}</td><td>${escapeHtml(item.pipeline.name)}<br><small>${escapeHtml(item.pipeline.role)}</small></td><td><span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></td><td>${escapeHtml(item.run_number || "No runs")}</td><td>${escapeHtml(item.branch || "-")}</td><td>${escapeHtml(item.reported_agent_pool || item.pipeline.agent_pool || "-")}</td><td>${escapeHtml(tests(item))}</td><td>${link(item.run_url, "Open run")}</td></tr>`).join("");
  return `<table class="table"><thead><tr><th>Project</th><th>Pipeline</th><th>Result</th><th>Latest run</th><th>Branch</th><th>Agent pool</th><th>Tests</th><th>Azure DevOps</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function renderRows(container, items, render) { container.innerHTML = items.length ? items.map(render).join("") : "<p class=\"empty\">No items to show.</p>"; }

function render(data) {
  const metrics = [[data.summary.pipelines_monitored, "Pipelines"], [data.summary.succeeded, "Succeeded"], [data.summary.failed, "Failed"], [data.summary.running, "Running"], [data.summary.smoke_test_failures, "Smoke failures"], [data.summary.pr_validation_failures, "PR validation failures"]];
  $("#summary").innerHTML = metrics.map(([number, label]) => `<div class="metric"><strong>${number}</strong><span>${label}</span></div>`).join("");
  $("#pipelines").innerHTML = pipelineTable(data.pipelines);
  const smokes = data.pipelines.filter((item) => item.pipeline.role === "smoke-test");
  renderRows($("#smoke-list"), smokes, (item) => `<article class="row"><h3>${escapeHtml(item.pipeline.project)} / ${escapeHtml(item.pipeline.name)} <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span></h3><p>Run: ${link(item.run_url, item.run_number || "No run")} | Tests: ${escapeHtml(tests(item))} | Agent pool: ${escapeHtml(item.reported_agent_pool || item.pipeline.agent_pool || "not reported")}</p>${provenance(item)}</article>`);
  renderRows($("#deployment-list"), data.deployments, (deployment) => `<article class="row"><h3>${escapeHtml(deployment.environment)} <small>${escapeHtml(deployment.deployment_id)}</small></h3><p>Agent pool: ${escapeHtml(deployment.agent_pool || "not supplied")} | Image: ${escapeHtml(deployment.image_version || "not supplied")} | Deployed: ${escapeHtml(deployment.deployed_at || "not supplied")}</p><p>Image build: ${deployment.image_build ? escapeHtml(`${deployment.image_build.pipeline_key} #${deployment.image_build.run_id}`) : "not supplied"}</p>${deployment.smoke_tests.map((item) => `<p>Smoke: ${escapeHtml(item.pipeline.name)} - ${escapeHtml(result(item))} (${escapeHtml(tests(item))})</p>`).join("") || "<p>No explicitly associated smoke tests.</p>"}</article>`);
  renderRows($("#pr-list"), data.pull_requests, (pr) => `<article class="row"><h3>${escapeHtml(pr.pr_id ? `PR ${pr.pr_id}: ${pr.title}` : pr.title)}</h3><p>${escapeHtml(pr.project)} / ${escapeHtml(pr.repository)} | ${escapeHtml(pr.source_branch)} to ${escapeHtml(pr.target_branch)} | ${link(pr.url, "Open PR")}</p>${pr.error ? `<p class="error">${escapeHtml(pr.error)}</p>` : pr.validations.map((item) => `<p>${escapeHtml(item.pipeline.name)}: <span class="status ${statusClass(result(item))}">${escapeHtml(result(item))}</span> ${link(item.run_url, item.run_number || "No run")} | ${escapeHtml(tests(item))}</p>${provenance(item)}`).join("") || "<p>No configured validation pipelines.</p>"}</article>`);
}

async function refresh() {
  $("#refresh").disabled = true; $("#error").hidden = true;
  try { const response = await fetch("/api/dashboard", {cache: "no-store"}); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Dashboard request failed."); render(data); $("#updated").textContent = `Updated ${new Date().toLocaleTimeString()}`; }
  catch (error) { $("#error").textContent = error.message; $("#error").hidden = false; }
  finally { $("#refresh").disabled = false; }
}
$("#refresh").addEventListener("click", refresh); refresh(); setInterval(refresh, 60000);
