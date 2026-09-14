(() => {
  "use strict";

  const state = {
    activeTab: "dashboard",
    selectedPort: null,
    grade: "VLSFO",
    range: "7D",
    dashboard: null,
    comparison: [],
    chart: null,
    loading: false,
    pollTimer: null,
    sort: { key: "port", direction: 1 },
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));
  const csrf = $("meta[name='csrf-token']").content;
  const providerMeta = {
    excel: { name: "Excel", color: "--warning", dash: [2, 4] },
  };

  function announce(message) {
    $("#live-message").textContent = message;
  }

  function formatDate(value, withTime = true) {
    if (!value) return "Never";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Unknown";
    return new Intl.DateTimeFormat(undefined, {
      day: "2-digit", month: "short", year: "numeric",
      ...(withTime ? { hour: "2-digit", minute: "2-digit", timeZoneName: "short" } : {}),
    }).format(date);
  }

  function ageLabel(value) {
    if (!value) return "No timestamp";
    const minutes = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
    if (minutes < 2) return "Just now";
    if (minutes < 60) return `${minutes} min ago`;
    const hours = Math.round(minutes / 60);
    if (hours < 48) return `${hours} hr ago`;
    return `${Math.round(hours / 24)} d ago`;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, { credentials: "same-origin", ...options });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("bunker-monitor-theme", theme);
    $("#theme-toggle").setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} mode`);
    if (state.chart) updateChartColors();
  }

  function statusClass(status) {
    return `status-${String(status || "unknown").replace(/[^a-z_]/g, "")}`;
  }

  function statusText(status) {
    return ({
      current: "Current", demo: "Demo data", mixed: "Excel + demo", empty: "No workbook", stale: "Stale", partial: "Partial",
      rate_limited: "Rate limited", unavailable: "Unavailable", not_configured: "Not configured",
      complete: "Completed", failed: "Failed", running: "Running", cooldown: "Cooldown",
    })[status] || "Waiting";
  }

  function setTab(name) {
    state.activeTab = name;
    $$(".nav-link").forEach((button) => button.classList.toggle("is-active", button.dataset.tab === name));
    $$(".tab-panel").forEach((panel) => {
      const active = panel.dataset.panel === name;
      panel.hidden = !active;
      panel.classList.toggle("is-active", active);
    });
    location.hash = name;
    if (name === "compare") loadCompare();
    if (name === "sources") loadSources();
    if (name === "dashboard" && state.chart) setTimeout(() => state.chart.resize(), 0);
  }

  function providerCell(observation, provider) {
    if (!observation) return `<span class="missing">Not available</span>`;
    const delta = observation.delta;
    const deltaClass = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
    const arrow = delta > 0 ? "▲" : delta < 0 ? "▼" : "—";
    return `<span class="provider-label">${provider}</span><span class="price">$${observation.price.toFixed(2)}</span> <span class="delta ${deltaClass}">${arrow}${delta == null ? "" : ` ${Math.abs(delta).toFixed(2)}`}</span>`;
  }

  function renderCards(payload) {
    const grid = $("#port-grid");
    if (!payload.ports.length) {
      grid.innerHTML = `<div class="empty-state"><strong>No workbook connected yet.</strong><br>Open Sources and connect a OneDrive or SharePoint Excel workbook.</div>`;
      return;
    }
    const providers = payload.providers || [];
    grid.innerHTML = payload.ports.map((port) => `
      <button type="button" class="port-card ${port.code === payload.selectedPort.code ? "is-selected" : ""}" data-port="${esc(port.code)}" aria-pressed="${port.code === payload.selectedPort.code}">
        <span class="port-card-head"><span><h3>${esc(port.name)}</h3><span class="port-country">${esc(port.country)}</span></span><span class="muted" aria-hidden="true">›</span></span>
        ${port.grades.map((row) => `
          <span class="fuel-row">
            <span class="fuel-meta"><span>${esc(row.grade)}</span><span>${Object.values(row.providers).filter(Boolean).length} of ${providers.length} sources</span></span>
            <span class="provider-values" style="--provider-count:${Math.max(providers.length, 1)}">
              ${providers.map((provider) => `<span class="provider-value">${providerCell(row.providers[provider.id], provider.name)}</span>`).join("")}
            </span>
          </span>`).join("")}
      </button>`).join("");
    $$(".port-card", grid).forEach((card) => card.addEventListener("click", () => {
      state.selectedPort = card.dataset.port;
      loadDashboard();
    }));
  }

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }

  function updateChartColors() {
    if (!state.chart) return;
    state.chart.options.scales.x.ticks.color = css("--muted");
    state.chart.options.scales.y.ticks.color = css("--muted");
    state.chart.options.scales.x.grid.color = css("--chart-grid");
    state.chart.options.scales.y.grid.color = css("--chart-grid");
    state.chart.options.scales.y.title.color = css("--muted");
    state.chart.update("none");
  }

  function renderChart(payload) {
    const activeProviderIds = new Set((payload.providers || []).map((provider) => provider.id));
    $$('[data-provider-control]').forEach((control) => { control.hidden = !activeProviderIds.has(control.dataset.providerControl); });
    const allTimes = [...new Set(payload.history.flatMap((series) => series.points.map((point) => point.time)))].sort();
    const datasets = payload.history.map((series) => {
      const byTime = new Map(series.points.map((point) => [point.time, point.price]));
      const meta = providerMeta[series.provider] || { name: series.provider, color: "--neutral", dash: [] };
      const checkbox = $(`input[data-provider='${series.provider}']`);
      return {
        label: meta.name,
        provider: series.provider,
        data: allTimes.map((time) => byTime.has(time) ? byTime.get(time) : null),
        borderColor: css(meta.color),
        backgroundColor: css(meta.color),
        borderDash: meta.dash,
        borderWidth: 2,
        pointRadius: 2.5,
        pointHoverRadius: 6,
        pointHitRadius: 12,
        tension: .24,
        spanGaps: false,
        hidden: checkbox ? !checkbox.checked : false,
      };
    });
    const labels = allTimes.map((time) => formatDate(time, false));
    $("#chart-title").textContent = `${payload.selectedPort.name} price history`;

    if (state.chart) state.chart.destroy();
    state.chart = new Chart($("#price-chart"), {
      type: "line",
      data: { labels, datasets },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        animation: { duration: matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 180 },
        plugins: {
          legend: { display: false },
          tooltip: {
            enabled: true,
            backgroundColor: css("--ink"), titleColor: css("--card"), bodyColor: css("--card"),
            padding: 12, displayColors: true,
            callbacks: {
              title(items) { return allTimes[items[0].dataIndex] ? formatDate(allTimes[items[0].dataIndex]) : "Unknown time"; },
              label(item) { return `${item.dataset.label} · ${payload.selectedGrade}: $${Number(item.raw).toFixed(2)}/MT`; },
            },
          },
        },
        scales: {
          x: { grid: { color: css("--chart-grid") }, ticks: { color: css("--muted"), maxTicksLimit: 8 } },
          y: {
            grid: { color: css("--chart-grid") }, ticks: { color: css("--muted"), callback: (value) => `$${value}` },
            title: { display: true, text: "Price (USD/MT)", color: css("--muted"), font: { size: 12, weight: "600" } },
          },
        },
      },
    });
  }

  async function loadDashboard({ quiet = false } = {}) {
    if (state.loading) return;
    state.loading = true;
    try {
      const query = new URLSearchParams({ grade: state.grade, range: state.range });
      if (state.selectedPort) query.set("port", state.selectedPort);
      const payload = await api(`/api/dashboard?${query}`);
      state.dashboard = payload;
      state.selectedPort = payload.selectedPort?.code || null;
      renderCards(payload);
      if (payload.selectedPort) renderChart(payload);
      $("#dashboard-subtitle").textContent = `${payload.ports.length} monitored hubs · Updated ${formatDate(payload.generatedAt)}`;
      const badge = $("#demo-badge");
      badge.hidden = payload.mode === "live" || payload.mode === "empty";
      badge.textContent = payload.mode === "mixed" ? "Includes demo data" : "Excel workbook";
      const status = $("#connection-status");
      status.className = `status-chip ${payload.mode === "live" || payload.mode === "empty" ? "status-current" : "status-demo"}`;
      status.innerHTML = `<span class="status-dot"></span>${payload.mode === "empty" ? "Excel not connected" : payload.mode === "mixed" ? "Excel + demo" : payload.mode === "demo" ? "Demo data" : "Excel workbook"}`;
      if (!quiet) announce("Dashboard updated");
    } catch (error) {
      announce(`Dashboard refresh failed. Previous values remain visible. ${error.message}`);
      $("#connection-status").className = "status-chip status-stale";
      $("#connection-status").innerHTML = `<span class="status-dot"></span>Stale`;
    } finally { state.loading = false; }
  }

  async function loadCompare() {
    try {
      const payload = await api("/api/compare");
      state.comparison = payload.rows;
      renderComparison();
    } catch (error) { announce(`Comparison failed: ${error.message}`); }
  }

  function renderComparison() {
    const grade = $("#compare-grade").value;
    const search = $("#compare-search").value.trim().toLowerCase();
    const rows = state.comparison.filter((row) => (!grade || row.grade === grade) && (!search || `${row.port} ${row.country}`.toLowerCase().includes(search)));
    const { key, direction } = state.sort;
    rows.sort((a, b) => {
      const get = (row) => key === "excel" ? row.providers.excel?.price ?? -Infinity : key === "freshness" ? Object.values(row.providers).map((value) => value?.sourceTime || "").sort().pop() : row[key] ?? "";
      return String(get(a)).localeCompare(String(get(b)), undefined, { numeric: true }) * direction;
    });
    $("#compare-count").textContent = `${rows.length} comparisons`;
    $("#compare-table tbody").innerHTML = rows.map((row) => {
      const x = row.providers.excel;
      const values = [b, o, x].filter(Boolean);
      const newest = values.map((value) => value.sourceTime).filter(Boolean).sort().pop();
      const fresh = values.some((value) => value.freshness === "stale") ? "stale" : values.length ? "current" : "no_data";
      const valueCell = (value) => value ? `$${value.price.toFixed(2)}<span class="cell-sub">${ageLabel(value.sourceTime)}</span>` : "—";
      return `<tr><td><strong>${esc(row.port)}</strong><span class="cell-sub">${esc(row.country)}</span></td><td>${esc(row.grade)}</td><td class="numeric">${valueCell(x)}</td><td><span class="status-chip ${statusClass(fresh)}">${statusText(fresh)}</span><span class="cell-sub">${ageLabel(newest)}</span></td></tr>`;
    }).join("");
  }

  async function loadSources() {
    try {
      const payload = await api("/api/sources");
      $("#source-cards").innerHTML = payload.providers.map((provider) => `
        <article class="card source-card">
          <div class="source-card-head"><div><h2>${esc(provider.name)}</h2><p class="muted">${provider.id === "excel" ? "Uploaded workbook snapshot" : provider.configured ? "API key configured" : provider.status === "demo" ? "Using labelled fixture data" : "API key required"}</p></div><span class="status-chip ${statusClass(provider.status)}">${statusText(provider.status)}</span></div>
          <div class="source-metrics">
            <div><span class="metric-label">Last success</span><span class="metric-value">${formatDate(provider.lastSuccess)}</span></div>
            <div><span class="metric-label">${provider.id === "excel" ? "Source" : "Requests today"}</span><span class="metric-value">${provider.id === "excel" ? "Manual upload" : `${provider.requestsToday} / ${provider.dailyQuota}`}</span></div>
            <div><span class="metric-label">Records</span><span class="metric-value">${provider.recordsLastRun}</span></div>
            <div><span class="metric-label">Ports</span><span class="metric-value">${provider.portsLastRun}</span></div>
          </div>${provider.lastError ? `<p class="source-error">${esc(provider.lastError)}</p>` : ""}
        </article>`).join("");
      renderUploadDiagnostics(payload.upload);
      renderCloudStatus(payload.cloud);
      const run = payload.lastRun;
      $("#last-run-copy").textContent = run ? `${formatDate(run.startedAt)} · ${run.inserted} new observations${run.error ? ` · ${run.error}` : ""}` : "No provider refresh has run yet.";
      $("#last-run-status").className = `status-chip ${statusClass(run?.status)}`;
      $("#last-run-status").textContent = statusText(run?.status);
      $("#source-table tbody").innerHTML = payload.preview.map((row) => `<tr><td>${esc(row.provider)}</td><td><strong>${esc(row.port)}</strong><span class="cell-sub">${esc(row.portCode)}</span></td><td>${esc(row.grade)}</td><td class="numeric">$${row.price.toFixed(2)} ${esc(row.currency)}/${esc(row.unit)}</td><td>${formatDate(row.sourceTime)}</td><td>${formatDate(row.retrievedAt)}</td><td><span class="status-chip ${statusClass(row.freshness)}">${statusText(row.freshness)}</span></td><td>${esc(row.sourceLabel)}</td></tr>`).join("");
    } catch (error) { announce(`Source diagnostics failed: ${error.message}`); }
  }

  function renderCloudStatus(cloud) {
    const target = $("#cloud-status");
    if (!cloud || !cloud.connected) { target.innerHTML = "<p>Not connected. Connect Microsoft account to select a workbook.</p>"; return; }
    const worksheet = cloud.worksheets?.length ? `<select id="cloud-worksheet" aria-label="Cloud workbook worksheet">${cloud.worksheets.map((name) => `<option ${name === cloud.worksheet ? "selected" : ""}>${esc(name)}</option>`).join("")}</select>` : esc(cloud.worksheet || "—");
    target.innerHTML = `<dl><div><dt>File</dt><dd>${esc(cloud.fileName || "—")}</dd></div><div><dt>Path</dt><dd>${esc(cloud.filePath || "—")}</dd></div><div><dt>Worksheet</dt><dd>${worksheet}</dd></div><div><dt>Cloud modified</dt><dd>${formatDate(cloud.lastModified)}</dd></div><div><dt>Last check</dt><dd>${formatDate(cloud.lastChecked)}</dd></div><div><dt>Status</dt><dd><span class="status-chip ${statusClass(cloud.status)}">${statusText(cloud.status)}</span></dd></div></dl>${cloud.changed ? "<p>Changed workbook detected and imported.</p>" : ""}${cloud.error ? `<p class="source-error">${esc(cloud.error)}</p>` : ""}`;
    $("#cloud-worksheet")?.addEventListener("change", (event) => cloudAction("/api/graph/worksheet", { worksheet: event.target.value }));
  }

  async function cloudAction(path, body) {
    try { const result = await api(path, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: body ? JSON.stringify(body) : undefined }); renderCloudStatus(result); await Promise.all([loadDashboard(), loadCompare(), loadSources()]); }
    catch (error) { announce(`Cloud workbook action failed: ${error.message}`); }
  }

  async function browseCloud() {
    try {
      const result = await api("/api/graph/files");
      const target = $("#cloud-files"); target.hidden = false;
      target.innerHTML = result.files.length ? result.files.map((file) => `<button type="button" class="button button-secondary cloud-file" data-id="${esc(file.id)}" data-drive="${esc(file.parentReference?.driveId || "")}" data-name="${esc(file.name)}" data-folder="${file.folder ? "true" : "false"}">${esc(file.folder ? "📁 " : "📄 ")}${esc(file.name)}</button>`).join(" ") : "<p>No folders or .xlsx files found.</p>";
      $$(".cloud-file", target).forEach((button) => button.addEventListener("click", () => button.dataset.folder === "true" ? browseCloud(button.dataset.id) : cloudAction("/api/graph/select", { itemId: button.dataset.id, driveId: button.dataset.drive, name: button.dataset.name })));
    } catch (error) { announce(`OneDrive browse failed: ${error.message}`); }
  }

  function renderUploadDiagnostics(upload) {
    const target = $("#upload-diagnostics");
    if (!upload) {
      target.innerHTML = "<p><strong>No workbook uploaded yet.</strong> The raw file is deleted after processing; normalized prices remain in this app’s database.</p>";
      return;
    }
    target.innerHTML = `<dl>
      <div><dt>File</dt><dd>${esc(upload.fileName || "Previous data retained")}</dd></div>
      <div><dt>Worksheet</dt><dd>${esc(upload.worksheet || "—")}</dd></div>
      <div><dt>Uploaded</dt><dd>${formatDate(upload.uploadedAt)}</dd></div>
      <div><dt>Layout</dt><dd>${esc(upload.layout || "—")}</dd></div>
      <div><dt>Observations</dt><dd>${upload.observations}</dd></div>
      <div><dt>Ports</dt><dd>${upload.ports}</dd></div>
    </dl>${upload.formulaCacheMissing || upload.excelErrors || upload.skippedCells ? `<p class="source-error">Warnings: ${upload.skippedCells} skipped values, ${upload.formulaCacheMissing} formulas without saved results, ${upload.excelErrors} Excel errors.</p>` : ""}${upload.lastError ? `<p class="source-error">Last import failed: ${esc(upload.lastError)} Previous Excel data remains visible.</p>` : ""}`;
  }

  async function uploadExcel(event) {
    event.preventDefault();
    const input = $("#excel-file");
    if (!input.files.length) return;
    const button = $("#excel-upload-button");
    const form = new FormData();
    form.append("file", input.files[0]);
    button.disabled = true;
    button.textContent = "Processing…";
    announce("Uploading and processing the Excel workbook");
    try {
      const result = await api("/api/uploads/excel", { method: "POST", headers: { "X-CSRF-Token": csrf }, body: form });
      input.value = "";
      await Promise.all([loadDashboard(), loadCompare(), loadSources()]);
      announce(`${result.fileName} imported: ${result.observations} observations from ${result.worksheet}`);
    } catch (error) {
      announce(`Excel upload failed. Previous data remains visible. ${error.message}`);
      await loadSources();
    } finally {
      button.disabled = false;
      button.textContent = "Upload and import";
    }
  }

  async function refreshNow() {
    if (state.loading) return;
    const button = $("#refresh-now");
    button.disabled = true;
    announce("Checking configured providers");
    try {
      const result = await api("/api/refresh", { method: "POST", headers: { "X-CSRF-Token": csrf } });
      await loadDashboard();
      if (state.activeTab === "sources") await loadSources();
      announce(result.status === "already_running" ? "A provider refresh is already running" : `Refresh ${result.status}; ${result.inserted} new observations stored`);
    } catch (error) {
      announce(`Refresh failed. Previous data remains visible. ${error.message}`);
      $("#connection-status").className = "status-chip status-stale";
      $("#connection-status").innerHTML = `<span class="status-dot"></span>Stale`;
    } finally { button.disabled = false; }
  }

  function configurePolling() {
    clearInterval(state.pollTimer);
    const interval = Number($("#browser-refresh").value);
    if (interval) state.pollTimer = setInterval(() => {
      if (!document.hidden && !state.loading) loadDashboard({ quiet: true });
    }, interval);
  }

  function bindEvents() {
    $$(".nav-link").forEach((button) => button.addEventListener("click", () => setTab(button.dataset.tab)));
    $("#theme-toggle").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    $("#refresh-now").addEventListener("click", refreshNow);
    $("#browser-refresh").addEventListener("change", configurePolling);
    $$("[data-grade]").forEach((button) => button.addEventListener("click", () => {
      state.grade = button.dataset.grade;
      $$("[data-grade]").forEach((item) => item.classList.toggle("is-active", item === button));
      loadDashboard();
    }));
    $$("[data-range]").forEach((button) => button.addEventListener("click", () => {
      state.range = button.dataset.range;
      $$("[data-range]").forEach((item) => item.classList.toggle("is-active", item === button));
      loadDashboard();
    }));
    $$("input[data-provider]").forEach((checkbox) => checkbox.addEventListener("change", () => {
      const dataset = state.chart?.data.datasets.find((item) => item.provider === checkbox.dataset.provider);
      if (dataset) { dataset.hidden = !checkbox.checked; state.chart.update(); }
    }));
    $("#compare-grade").addEventListener("change", renderComparison);
    $("#compare-search").addEventListener("input", renderComparison);
    $("#excel-upload-form").addEventListener("submit", uploadExcel);
    $("#cloud-refresh").addEventListener("click", () => cloudAction("/api/graph/refresh"));
    $("#cloud-browse").addEventListener("click", browseCloud);
    $("#cloud-disconnect").addEventListener("click", () => cloudAction("/api/graph/disconnect"));
    $("#cloud-link-form").addEventListener("submit", (event) => { event.preventDefault(); cloudAction("/api/graph/link", { link: $("#cloud-link").value }); });
    $$("#compare-table th[data-sort]").forEach((header) => header.addEventListener("click", () => {
      const key = header.dataset.sort;
      state.sort.direction = state.sort.key === key ? -state.sort.direction : 1;
      state.sort.key = key;
      renderComparison();
    }));
  }

  document.addEventListener("DOMContentLoaded", () => {
    setTheme(localStorage.getItem("bunker-monitor-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
    bindEvents();
    configurePolling();
    const requestedTab = location.hash.slice(1);
    setTab(["dashboard", "compare", "sources"].includes(requestedTab) ? requestedTab : "dashboard");
    loadDashboard();
  });
})();
