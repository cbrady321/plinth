const state = {
  view: "runs",
  runs: [],
  selectedRunId: null,
  compareRunIds: [],
  selectedStagePath: null,
  compareTab: "config",
  manifestPage: 1,
  manifestEntityFilter: null,
  entityDiffPage: 1,
  exportSections: ["config", "manifest_summary", "ledger"],
  exportFormat: "markdown",
  filters: { status: "", sort: "recency", fromDate: "", toDate: "" },
  lastError: null,
};

const VIEW_META = {
  runs: { kicker: "Analysis entry", title: "Choose runs to analyze", hint: "Select a run to inspect manifests, ledgers, and failures — or multi-select runs for comparison workflows." },
  manifest: { kicker: "Inspect", title: "Manifest & schema", hint: "View manifest.csv and schema at completed stage boundaries in ledger order." },
  ledger: { kicker: "Lineage", title: "Ledger lineage", hint: "Walk the append-only metadata ledger and hash chain per stage." },
  failures: { kicker: "Debug", title: "Failure debug", hint: "Pinpoint failing stage, entity row, and error attribution on partial or failed runs." },
  artifacts: { kicker: "Browse", title: "Artifact browser", hint: "Browse stage directories and on-disk layout in filesystem-tree order." },
  compare: { kicker: "Compare", title: "Run comparison", hint: "Diff configs, manifest summaries, entity values, and ledger fingerprints across selected runs." },
};

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || res.statusText);
  }
  const type = res.headers.get("content-type") || "";
  if (type.includes("application/json")) return res.json();
  return res.text();
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  Object.entries(attrs).forEach(([key, value]) => {
    if (key === "className") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2).toLowerCase(), value);
    else node.setAttribute(key, value);
  });
  (Array.isArray(children) ? children : [children]).forEach((child) => {
    if (child == null) return;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  });
  return node;
}

function pill(label, tone = "muted") {
  return el("span", { className: `pill ${tone}`, text: label });
}

function formatDuration(seconds) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function statusTone(status) {
  if (status === "success") return "success";
  if (status === "failed") return "danger";
  if (status === "in_progress") return "info";
  if (status === "cancelled") return "warn";
  return "muted";
}

function syncHashFromState() {
  const parts = [state.view];
  if (state.selectedRunId) parts.push(encodeURIComponent(state.selectedRunId));
  if (state.selectedStagePath && ["manifest", "artifacts"].includes(state.view)) {
    parts.push(encodeURIComponent(state.selectedStagePath));
  }
  if (state.manifestEntityFilter && state.view === "manifest") {
    parts.push(encodeURIComponent(state.manifestEntityFilter));
  }
  const hash = `#/${parts.join("/")}`;
  if (window.location.hash !== hash) history.replaceState(null, "", hash);
}

function applyHash() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  if (!raw) return false;
  const [view, runId, stagePath, entityId] = raw.split("/").map((part) => decodeURIComponent(part));
  if (view && VIEW_META[view]) state.view = view;
  if (runId) state.selectedRunId = runId;
  if (stagePath) state.selectedStagePath = stagePath;
  if (entityId) state.manifestEntityFilter = entityId;
  return true;
}

function openManifest({ runId, stagePath, entityId } = {}) {
  if (runId) state.selectedRunId = runId;
  if (stagePath) state.selectedStagePath = stagePath;
  state.manifestEntityFilter = entityId || null;
  state.manifestPage = 1;
  setView("manifest");
}

function stagePathFromArtifactPath(filePath) {
  if (!filePath) return null;
  const parts = filePath.split("/");
  return parts.length >= 2 ? parts.slice(0, -1).join("/") : parts[0];
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  const meta = VIEW_META[view];
  document.getElementById("top-kicker").textContent = meta.kicker;
  document.getElementById("top-title").textContent = meta.title;
  document.getElementById("active-run-label").textContent = state.selectedRunId
    ? `active run: ${state.selectedRunId}`
    : "no run selected";
  document.getElementById("compare-session-label").textContent = state.compareRunIds.length
    ? `comparison: ${state.compareRunIds.join(", ")}`
    : "comparison: none";
  syncHashFromState();
  render();
}

function toggleCompareRun(runId) {
  const idx = state.compareRunIds.indexOf(runId);
  if (idx >= 0) state.compareRunIds.splice(idx, 1);
  else state.compareRunIds.push(runId);
  render();
}

async function loadRuns() {
  const params = new URLSearchParams();
  if (state.filters.status) params.set("status", state.filters.status);
  params.set("sort", state.filters.sort);
  if (state.filters.fromDate) params.set("from_date", new Date(state.filters.fromDate).toISOString());
  if (state.filters.toDate) params.set("to_date", new Date(state.filters.toDate).toISOString());
  const data = await api(`/api/runs?${params}`);
  state.runs = data.runs || [];
  if (data.error) throw new Error(data.error);
  state.lastError = null;
}

function renderErrorBanner(container, err, onRetry) {
  const banner = el("div", { className: "banner danger" }, [
    el("span", { text: String(err.message || err) }),
    " ",
    el("button", { className: "btn", text: "Retry", onClick: onRetry }),
  ]);
  container.appendChild(banner);
}

async function renderRuns(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.runs.hint }));

  const toolbar = el("div", { className: "toolbar" }, [
    el("label", { text: "Status " }),
    (() => {
      const select = el("select");
      [["", "All"], ["success", "Success"], ["failed", "Failed"], ["in_progress", "In progress"]].forEach(([value, label]) => {
        const opt = el("option", { value, text: label });
        if (state.filters.status === value) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", async () => {
        state.filters.status = select.value;
        await loadRuns();
        render();
      });
      return select;
    })(),
    el("label", { text: "Sort " }),
    (() => {
      const select = el("select");
      [["recency", "Recency"], ["status", "Status"], ["duration", "Duration"]].forEach(([value, label]) => {
        const opt = el("option", { value, text: label });
        if (state.filters.sort === value) opt.selected = true;
        select.appendChild(opt);
      });
      select.addEventListener("change", async () => {
        state.filters.sort = select.value;
        await loadRuns();
        render();
      });
      return select;
    })(),
    el("label", { text: "From " }),
    (() => {
      const input = el("input", { type: "date" });
      input.value = state.filters.fromDate;
      input.addEventListener("change", async () => {
        state.filters.fromDate = input.value;
        await loadRuns();
        render();
      });
      return input;
    })(),
    el("label", { text: "To " }),
    (() => {
      const input = el("input", { type: "date" });
      input.value = state.filters.toDate;
      input.addEventListener("change", async () => {
        state.filters.toDate = input.value;
        await loadRuns();
        render();
      });
      return input;
    })(),
  ]);
  container.appendChild(toolbar);

  if (!state.runs.length) {
    container.appendChild(el("div", { className: "empty", text: "No runs found under data/pipeline/runs/. Launch a pipeline or start the server with --seed-demo." }));
    return;
  }

  const table = el("table", { className: "data" });
  table.appendChild(el("tr", {}, [
    el("th", { text: "" }),
    el("th", { text: "Run" }),
    el("th", { text: "Status" }),
    el("th", { text: "Started" }),
    el("th", { text: "Duration" }),
    el("th", { text: "Stages" }),
    el("th", { text: "Pipeline" }),
  ]));

  state.runs.forEach((run) => {
    const compareChecked = state.compareRunIds.includes(run.run_id);
    const selected = state.selectedRunId === run.run_id;
    const row = el("tr", { className: selected ? "selected" : "" }, [
      el("td", {}, [
        el("input", {
          type: "checkbox",
          ...(compareChecked ? { checked: "checked" } : {}),
          onChange: () => toggleCompareRun(run.run_id),
        }),
      ]),
      el("td", {}, [
        el("a", {
          href: "#",
          text: run.run_id,
          onClick: (e) => {
            e.preventDefault();
            state.selectedRunId = run.run_id;
            setView("manifest");
          },
        }),
      ]),
      el("td", {}, [pill(run.status, statusTone(run.status))]),
      el("td", { className: "mono", text: run.started_at ? new Date(run.started_at).toLocaleString() : "—" }),
      el("td", { text: formatDuration(run.duration_seconds) }),
      el("td", { text: String(run.stage_count) }),
      el("td", { text: run.pipeline_name || "—" }),
    ]);
    row.addEventListener("click", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "A") return;
      state.selectedRunId = run.run_id;
      render();
    });
    table.appendChild(row);
  });
  container.appendChild(el("div", { className: "card" }, [el("div", { className: "table-wrap" }, [table])]));

  if (state.selectedRunId) {
    const detail = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}`);
    container.appendChild(el("div", { className: "card" }, [
      el("div", { className: "card-title", text: "Run detail shell" }),
      el("p", { text: `Status ${detail.status} · ${detail.stages.length} stages · ${detail.run_root}` }),
      el("div", { className: "toolbar" }, [
        el("button", { className: "btn", text: "Manifest", onClick: () => setView("manifest") }),
        el("button", { className: "btn", text: "Ledger", onClick: () => setView("ledger") }),
        el("button", { className: "btn", text: "Failures", onClick: () => setView("failures") }),
        el("button", { className: "btn", text: "Artifacts", onClick: () => setView("artifacts") }),
      ]),
    ]));
  }
}

async function renderManifest(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.manifest.hint }));
  if (!state.selectedRunId) {
    container.appendChild(el("div", { className: "empty", text: "Select a run from the Runs view first." }));
    return;
  }
  const detail = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}`);
  const completed = detail.stages.filter((s) => s.status === "completed");
  const inProgress = detail.stages.filter((s) => s.status === "in_progress");
  if (!completed.length && !inProgress.length) {
    container.appendChild(el("div", { className: "banner warn", text: "No completed stages with manifest data yet." }));
    return;
  }
  if (!state.selectedStagePath) state.selectedStagePath = (completed[0] || inProgress[0]).stage_path;

  const toolbar = el("div", { className: "toolbar" });
  const select = el("select");
  completed.forEach((stage) => {
    const opt = el("option", {
      value: stage.stage_path,
      text: `${stage.stage_path} (${stage.row_count ?? "?"} rows)`,
    });
    if (stage.stage_path === state.selectedStagePath) opt.selected = true;
    select.appendChild(opt);
  });
  inProgress.forEach((stage) => {
    const opt = el("option", {
      value: stage.stage_path,
      text: `${stage.stage_path} (in progress)`,
      disabled: "disabled",
    });
    select.appendChild(opt);
  });
  select.addEventListener("change", () => {
    state.selectedStagePath = select.value;
    state.manifestPage = 1;
    render();
  });
  toolbar.appendChild(el("label", { text: "Stage " }));
  toolbar.appendChild(select);
  container.appendChild(toolbar);

  const manifestParams = new URLSearchParams({
    stage_path: state.selectedStagePath,
    page: String(state.manifestPage),
    page_size: "50",
  });
  if (state.manifestEntityFilter) manifestParams.set("entity_id", state.manifestEntityFilter);

  const [manifest, schema] = await Promise.all([
    api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/manifest?${manifestParams}`),
    api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/schema?stage_path=${encodeURIComponent(state.selectedStagePath)}`),
  ]);

  if (manifest.error) container.appendChild(el("div", { className: "banner danger", text: manifest.error }));
  if (manifest.identity_warning) container.appendChild(el("div", { className: "banner warn", text: manifest.identity_warning }));
  if (state.manifestEntityFilter) {
    container.appendChild(el("div", { className: "toolbar" }, [
      el("span", { text: `Filtered to entity: ${state.manifestEntityFilter}` }),
      el("button", {
        className: "btn",
        text: "Clear filter",
        onClick: () => {
          state.manifestEntityFilter = null;
          state.manifestPage = 1;
          render();
        },
      }),
    ]));
  }

  const split = el("div", { className: "split" });
  const schemaPanel = el("div", { className: "panel narrow card" }, [
    el("div", { className: "card-title", text: "Schema" }),
  ]);
  if (schema.error) schemaPanel.appendChild(el("div", { className: "banner danger", text: schema.error }));
  else {
    schemaPanel.appendChild(el("p", { text: `unique_key: ${(schema.unique_key || []).join(", ") || "—"}` }));
    schemaPanel.appendChild(el("p", { text: `entity_key: ${schema.identity?.entity_key || "—"}` }));
    const hierarchy = (schema.identity?.hierarchy_keys || []).join(", ");
    if (hierarchy) schemaPanel.appendChild(el("p", { text: `hierarchy_keys: ${hierarchy}` }));
    if (schema.media?.path_column) {
      schemaPanel.appendChild(el("p", { text: `file column: ${schema.media.path_column} → ${schema.media.subdir}/` }));
    }
    const colList = el("ul");
    Object.entries(schema.columns || {}).forEach(([name, type]) => {
      colList.appendChild(el("li", { text: `${name}: ${type}` }));
    });
    schemaPanel.appendChild(colList);
    if (schema.schema_path) schemaPanel.appendChild(el("p", { className: "mono", text: schema.schema_path }));
  }

  const table = el("table", { className: "data" });
  table.appendChild(el("tr", {}, manifest.columns.map((c) => el("th", { text: c }))));
  manifest.rows.forEach((row) => {
    table.appendChild(el("tr", {}, manifest.columns.map((c) => el("td", { text: row[c] == null ? "" : String(row[c]) }))));
  });
  const manifestPanel = el("div", { className: "panel card" }, [
    el("div", { className: "card-title", text: `Manifest preview (${manifest.total_rows} rows)` }),
    el("p", { className: "mono", text: `${manifest.manifest_path || ""} · ${manifest.manifest_size_bytes || "?"} bytes` }),
    el("div", { className: "table-wrap" }, [table]),
    el("p", { className: "mono", text: `page ${manifest.page} of ${manifest.total_pages} · showing ${manifest.rows.length} rows` }),
    el("div", { className: "toolbar" }, [
      el("button", {
        className: "btn",
        text: "Previous",
        disabled: manifest.page <= 1 ? "disabled" : null,
        onClick: () => { state.manifestPage = Math.max(1, state.manifestPage - 1); render(); },
      }),
      el("button", {
        className: "btn",
        text: "Next",
        disabled: manifest.page >= manifest.total_pages ? "disabled" : null,
        onClick: () => { state.manifestPage += 1; render(); },
      }),
    ]),
  ]);
  split.appendChild(schemaPanel);
  split.appendChild(manifestPanel);
  container.appendChild(split);
}

async function renderLedger(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.ledger.hint }));
  if (!state.selectedRunId) {
    container.appendChild(el("div", { className: "empty", text: "Select a run from the Runs view first." }));
    return;
  }
  const timeline = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/ledger`);
  if (timeline.error) container.appendChild(el("div", { className: "banner danger", text: timeline.error }));
  if (!timeline.integrity_ok) container.appendChild(el("div", { className: "banner danger", text: timeline.integrity_error || "Ledger integrity check failed." }));

  const exportBar = el("div", { className: "toolbar" });
  const executed = timeline.entries.filter((e) => e.status === "executed");
  if (executed.length) {
    const last = executed[executed.length - 1];
    exportBar.appendChild(el("a", {
      className: "btn",
      href: `/api/runs/${encodeURIComponent(state.selectedRunId)}/ledger/export?stage_path=${encodeURIComponent(last.stage_path)}`,
      text: "Export raw ledger",
    }));
  }
  container.appendChild(exportBar);

  const list = el("div", { className: "timeline" });
  timeline.entries.forEach((entry) => {
    const item = el("div", {
      className: `timeline-item ${entry.status === "not_executed" ? "not-executed" : ""}`,
    }, [
      el("div", { style: "display:flex;gap:10px;align-items:center" }, [
        el("strong", { text: entry.stage_name }),
        pill(entry.status === "not_executed" ? "not executed" : "executed", entry.status === "not_executed" ? "muted" : "success"),
      ]),
      el("div", { className: "mono", text: entry.stage_path }),
      el("div", { text: entry.timestamp || "—" }),
      el("div", { className: "mono", text: `in ${entry.predecessor_hash?.slice(0, 12) || "—"}… → out ${entry.output_hash?.slice(0, 16) || "—"}…` }),
      el("div", { className: "mono", text: `params ${entry.params_hash?.slice(0, 12) || "—"}…` }),
      entry.params && Object.keys(entry.params).length
        ? el("pre", { className: "code", text: JSON.stringify(entry.params, null, 2) })
        : null,
      entry.arming_hash
        ? el("div", { className: "mono", text: `arming_hash: ${entry.arming_hash}` })
        : el("div", { className: "mono", text: "arming_hash: (inactive)" }),
    ]);
    list.appendChild(item);
  });
  container.appendChild(el("div", { className: "card" }, [list]));
}

async function renderFailures(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.failures.hint }));
  if (!state.selectedRunId) {
    container.appendChild(el("div", { className: "empty", text: "Select a run from the Runs view first." }));
    return;
  }
  const report = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/failures`);
  if (report.error) container.appendChild(el("div", { className: "banner danger", text: report.error }));

  const card = el("div", { className: "card" });
  const kindLabel = report.error_kind === "infrastructure" ? "Infrastructure error" : report.error_kind === "stage_logic" ? "Stage logic failure" : "Unknown error kind";
  card.appendChild(el("p", {}, [pill(kindLabel, report.error_kind === "infrastructure" ? "warn" : "danger")]));
  card.appendChild(el("p", {}, [el("strong", { text: "Status: " }), document.createTextNode(report.status)]));
  if (report.first_failing_stage) card.appendChild(el("p", { text: `First failing stage: ${report.first_failing_stage}` }));
  if (report.stage_error) card.appendChild(el("div", { className: "banner danger", text: report.stage_error }));
  if (report.stack_summary) card.appendChild(el("pre", { className: "code", text: report.stack_summary }));
  if (!report.row_failures?.length && report.status !== "failed") {
    card.appendChild(el("div", { className: "banner success", text: "No row-level failures recorded. Stage-level error only if present above." }));
  }
  if (report.row_failures?.length) {
    const table = el("table", { className: "data" });
    table.appendChild(el("tr", {}, ["Entity", "Row", "Stage", "Error"].map((h) => el("th", { text: h }))));
    report.row_failures.forEach((row) => {
      table.appendChild(el("tr", {}, [
        el("td", {}, [
          row.entity_id
            ? el("a", {
                href: "#",
                text: row.entity_id,
                onClick: (e) => {
                  e.preventDefault();
                  openManifest({
                    runId: state.selectedRunId,
                    stagePath: row.stage_path,
                    entityId: row.entity_id,
                  });
                },
              })
            : document.createTextNode("—"),
        ]),
        el("td", { text: row.row_index == null ? "—" : String(row.row_index) }),
        el("td", { text: row.stage_path }),
        el("td", { text: row.error_message }),
      ]));
    });
    card.appendChild(el("div", { className: "table-wrap" }, [table]));
  } else if (report.status === "failed" && !report.stage_error) {
    card.appendChild(el("p", { text: "Row-level attribution unavailable — showing stage-level context only." }));
  }
  if (report.cancelled_branches?.length) {
    card.appendChild(el("div", { className: "banner warn", text: `Cancelled/skipped branches: ${report.cancelled_branches.join(", ")}` }));
  }
  if (report.log_tail) {
    card.appendChild(el("div", { className: "card-title", text: "Log tail" }));
    card.appendChild(el("pre", { className: "code", text: report.log_tail }));
  }
  container.appendChild(card);
}

function renderTreeNode(node, runId, onSelect) {
  if (node.kind === "directory") {
    const details = el("details", { open: node.path === "." ? "open" : null });
    const summaryChildren = [el("span", { text: `📁 ${node.name}` })];
    if (node.export_label) summaryChildren.push(pill(node.export_label, "success"));
    if (node.export_warning) summaryChildren.push(pill(node.export_warning, "warn"));
    const summary = el("summary", {}, summaryChildren);
    summary.addEventListener("click", (e) => {
      if (node.path !== ".") {
        e.preventDefault();
        onSelect(node);
      }
    });
    details.appendChild(summary);
    (node.children || []).forEach((child) => details.appendChild(renderTreeNode(child, runId, onSelect)));
    return details;
  }
  const size = node.size_bytes != null ? `${node.size_bytes} B` : "";
  const modified = node.modified_at ? new Date(node.modified_at).toLocaleString() : "";
  const actions = [
    el("a", {
      href: `/api/runs/${encodeURIComponent(runId)}/artifacts/download?path=${encodeURIComponent(node.path)}`,
      text: "download",
    }),
  ];
  if (node.manifest_link) {
    actions.unshift(el("a", {
      href: "#",
      text: "preview",
      onClick: (e) => {
        e.preventDefault();
        openManifest({
          runId,
          stagePath: stagePathFromArtifactPath(node.path),
        });
      },
    }));
  }
  return el("div", { className: "file-row" }, [
    el("span", { text: `📄 ${node.name}` }),
    el("span", { className: "file-meta mono", text: `${size} · ${modified}` }),
    ...actions,
  ]);
}

async function renderArtifacts(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.artifacts.hint }));
  if (!state.selectedRunId) {
    container.appendChild(el("div", { className: "empty", text: "Select a run from the Runs view first." }));
    return;
  }
  const tree = await api(`/api/runs/${encodeURIComponent(state.selectedRunId)}/artifacts`);
  if (tree.error) container.appendChild(el("div", { className: "banner danger", text: tree.error }));

  const split = el("div", { className: "split" });
  const filePanel = el("div", { className: "panel narrow card" }, [
    el("div", { className: "card-title", text: "Selected stage files" }),
    el("p", { id: "artifact-stage-label", className: "mono", text: "Select a stage directory" }),
    el("div", { id: "artifact-file-list" }),
  ]);
  const treePanel = el("div", { className: "panel card tree" });

  function showStageFiles(node) {
    document.getElementById("artifact-stage-label").textContent = node.path;
    const list = document.getElementById("artifact-file-list");
    list.innerHTML = "";
    if (node.export_label) list.appendChild(el("div", { className: "banner success", text: node.export_label }));
    if (node.export_warning) list.appendChild(el("div", { className: "banner warn", text: node.export_warning }));
    (node.children || []).forEach((child) => {
      if (child.kind === "file") {
        list.appendChild(renderTreeNode(child, state.selectedRunId, () => {}));
      }
    });
  }

  treePanel.appendChild(renderTreeNode(tree.root, state.selectedRunId, showStageFiles));
  split.appendChild(filePanel);
  split.appendChild(treePanel);
  container.appendChild(split);
}

async function renderCompare(container) {
  container.appendChild(el("p", { className: "hint", text: VIEW_META.compare.hint }));
  if (state.compareRunIds.length < 2) {
    container.appendChild(el("div", { className: "empty", text: "Multi-select at least two runs on the Runs view to start a comparison session." }));
    return;
  }

  const chips = el("div", { className: "compare-session" });
  state.compareRunIds.forEach((id) => chips.appendChild(el("span", { className: "compare-chip mono", text: id })));
  container.appendChild(chips);

  const tabs = el("div", { className: "toolbar" });
  ["config", "manifest_summary", "entity_diff", "ledger", "export"].forEach((tab) => {
    tabs.appendChild(el("button", {
      className: `btn ${state.compareTab === tab ? "primary" : ""}`,
      text: tab.replace("_", " "),
      onClick: () => { state.compareTab = tab; render(); },
    }));
  });
  container.appendChild(tabs);

  const runsParam = encodeURIComponent(state.compareRunIds.join(","));
  if (state.compareTab === "config") {
    const data = await api(`/api/compare/config?runs=${runsParam}`);
    if (data.unavailable?.length) container.appendChild(el("div", { className: "banner warn", text: `Missing config snapshots: ${data.unavailable.join(", ")}` }));
    if (data.structural_diffs?.length) {
      const diffTable = el("table", { className: "data" });
      diffTable.appendChild(el("tr", {}, ["JSONPath", "Change", ...state.compareRunIds.map((id) => el("th", { text: id }))]));
      data.structural_diffs.forEach((diff) => {
        diffTable.appendChild(el("tr", {}, [
          el("td", { className: "mono", text: diff.path }),
          el("td", { text: diff.change }),
          ...state.compareRunIds.map((id) => {
            const val = diff.per_run?.[id];
            if (!val) return el("td", { text: "—" });
            if (val.status === "removed") return el("td", { className: "mismatch", text: "removed" });
            return el("td", { className: "mono", text: JSON.stringify(val) });
          }),
        ]));
      });
      container.appendChild(el("div", { className: "card table-wrap" }, [el("div", { className: "card-title", text: "Structural diff" }), diffTable]));
    }
    data.sections.forEach((section) => {
      container.appendChild(el("div", { className: "card" }, [
        el("div", { className: "card-title", text: section.run_id }),
        el("pre", { className: "code", text: JSON.stringify(section.config, null, 2) }),
      ]));
    });
  } else if (state.compareTab === "manifest_summary") {
    const data = await api(`/api/compare/manifest-summary?runs=${runsParam}`);
    const table = el("table", { className: "data" });
    const header = el("tr", {}, [el("th", { text: "Stage" }), ...state.compareRunIds.map((id) => el("th", { text: id }))]);
    table.appendChild(header);
    data.rows.forEach((row) => {
      const cells = state.compareRunIds.map((id) => {
        const summary = row.per_run[id];
        if (!summary || summary.unavailable) return el("td", { className: "mismatch", text: "unavailable" });
        return el("td", { className: row.mismatch ? "mismatch" : "", text: `${summary.row_count} rows · ${summary.columns.length} cols` });
      });
      table.appendChild(el("tr", {}, [el("td", { className: "mono", text: row.stage_path }), ...cells]));
    });
    container.appendChild(el("div", { className: "card table-wrap" }, [table]));
  } else if (state.compareTab === "entity_diff") {
    const detail = await api(`/api/runs/${encodeURIComponent(state.compareRunIds[0])}`);
    const stagePaths = detail.stages.filter((s) => s.has_manifest).map((s) => s.stage_path);
    const stage = state.selectedStagePath && stagePaths.includes(state.selectedStagePath)
      ? state.selectedStagePath
      : stagePaths[0];
    if (!stage) {
      container.appendChild(el("div", { className: "empty", text: "No shared stage with manifests." }));
      return;
    }
    const stageSelect = el("select");
    stagePaths.forEach((sp) => {
      const opt = el("option", { value: sp, text: sp });
      if (sp === stage) opt.selected = true;
      stageSelect.appendChild(opt);
    });
    stageSelect.addEventListener("change", () => {
      state.selectedStagePath = stageSelect.value;
      state.entityDiffPage = 1;
      render();
    });
    container.appendChild(el("div", { className: "toolbar" }, [el("label", { text: "Stage " }), stageSelect]));

    const data = await api(`/api/compare/entity-diff?runs=${runsParam}&stage_path=${encodeURIComponent(stage)}&page=${state.entityDiffPage}&page_size=25`);
    if (data.error) container.appendChild(el("div", { className: "banner danger", text: data.error }));
    if (data.identity_warning) container.appendChild(el("div", { className: "banner warn", text: data.identity_warning }));
    container.appendChild(el("p", { className: "mono", text: `${data.total_items} diff items · page ${data.page} of ${data.total_pages}` }));
    if (data.items?.length) {
      const table = el("table", { className: "data" });
      table.appendChild(el("tr", {}, ["Entity", "Change", ""].map((h) => el("th", { text: h }))));
      data.items.forEach((item) => {
        const entityId = item.entity_id
          || (item.entity_key ? String(item.entity_key).split("|")[0] : null)
          || (item.changes && Object.keys(item.changes).length ? item.kind : null);
        const summary = item.changes ? JSON.stringify(item.changes) : JSON.stringify(item);
        table.appendChild(el("tr", {}, [
          el("td", { className: "mono", text: entityId || "—" }),
          el("td", { className: "mono", text: summary }),
          el("td", {}, [
            entityId
              ? el("button", {
                  className: "btn",
                  text: "Manifest",
                  onClick: () => openManifest({
                    runId: state.compareRunIds[0],
                    stagePath: stage,
                    entityId: String(entityId).split("|")[0],
                  }),
                })
              : null,
          ]),
        ]));
      });
      container.appendChild(el("div", { className: "card table-wrap" }, [table]));
    }
    container.appendChild(el("div", { className: "toolbar" }, [
      el("button", { className: "btn", text: "Previous", disabled: data.page <= 1 ? "disabled" : null, onClick: () => { state.entityDiffPage -= 1; render(); } }),
      el("button", { className: "btn", text: "Next", disabled: data.page >= data.total_pages ? "disabled" : null, onClick: () => { state.entityDiffPage += 1; render(); } }),
    ]));
  } else if (state.compareTab === "ledger") {
    const data = await api(`/api/compare/ledger?runs=${runsParam}`);
    const table = el("table", { className: "data" });
    table.appendChild(el("tr", {}, [el("th", { text: "Stage" }), ...state.compareRunIds.map((id) => el("th", { text: id }))]));
    data.rows.forEach((row) => {
      table.appendChild(el("tr", { className: row.hash_mismatch ? "mismatch" : "" }, [
        el("td", { className: "mono", text: row.stage_path }),
        ...state.compareRunIds.map((id) => {
          const entry = row.per_run[id];
          if (!entry) return el("td", { className: "mismatch", text: "unavailable" });
          const label = entry.status === "not_executed" ? "not executed" : entry.status;
          return el("td", { className: "mono", text: `${label} · ${(entry.output_hash || "").slice(0, 10)}…` });
        }),
      ]));
    });
    container.appendChild(el("div", { className: "card table-wrap" }, [table]));
  } else if (state.compareTab === "export") {
    const sectionBox = el("div", { className: "toolbar" });
    ["config", "manifest_summary", "entity_diff", "ledger"].forEach((section) => {
      const id = `export-${section}`;
      const checked = state.exportSections.includes(section);
      sectionBox.appendChild(el("label", {}, [
        el("input", {
          type: "checkbox",
          id,
          ...(checked ? { checked: "checked" } : {}),
          onChange: (e) => {
            if (e.target.checked) state.exportSections.push(section);
            else state.exportSections = state.exportSections.filter((s) => s !== section);
          },
        }),
        ` ${section}`,
      ]));
    });
    const formatSelect = el("select");
    [["markdown", "Markdown"], ["json", "JSON"]].forEach(([value, label]) => {
      const opt = el("option", { value, text: label });
      if (state.exportFormat === value) opt.selected = true;
      formatSelect.appendChild(opt);
    });
    formatSelect.addEventListener("change", () => { state.exportFormat = formatSelect.value; });

    container.appendChild(el("div", { className: "card" }, [
      el("p", { text: "Export re-computes selected comparison sections for the current session." }),
      sectionBox,
      el("div", { className: "toolbar" }, [el("label", { text: "Format " }), formatSelect]),
      el("button", {
        className: "btn primary",
        text: "Download report",
        onClick: async () => {
          const detail = await api(`/api/runs/${encodeURIComponent(state.compareRunIds[0])}`);
          const stage_path = detail.stages.find((s) => s.has_manifest)?.stage_path;
          const res = await fetch("/api/compare/export", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              run_ids: state.compareRunIds,
              sections: state.exportSections,
              format: state.exportFormat,
              stage_path,
            }),
          });
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const ext = state.exportFormat === "markdown" ? "md" : "json";
          const a = el("a", { href: url, download: `comparison.${ext}` });
          a.click();
          URL.revokeObjectURL(url);
        },
      }),
    ]));
  }
}

async function render() {
  const container = document.getElementById("content");
  container.innerHTML = "";
  try {
    if (state.view === "runs") await loadRuns();
    if (state.view === "runs") await renderRuns(container);
    else if (state.view === "manifest") await renderManifest(container);
    else if (state.view === "ledger") await renderLedger(container);
    else if (state.view === "failures") await renderFailures(container);
    else if (state.view === "artifacts") await renderArtifacts(container);
    else if (state.view === "compare") await renderCompare(container);
  } catch (err) {
    state.lastError = err;
    renderErrorBanner(container, err, () => render());
  }
}

document.querySelectorAll(".nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

window.addEventListener("hashchange", () => {
  applyHash();
  setView(state.view);
});

if (applyHash()) setView(state.view);
else setView("runs");
