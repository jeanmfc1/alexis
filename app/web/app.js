/* =====================================================================
   ALEXIS Control Panel - vanilla JS
   No frameworks, no build step.
   ===================================================================== */
(function () {
  "use strict";

  // -------------------------------------------------------------------
  // Shared palette mirrors (kept in sync with viz/* + app.css)
  // -------------------------------------------------------------------
  const MODALITY_COLORS = {
    small_molecule:          "#3B82F6",
    biologic:                "#8B5CF6",
    monoclonal_antibody:     "#6366F1",
    mab:                     "#6366F1",
    adc:                     "#EC4899",
    antibody_drug_conjugate: "#EC4899",
    gene_therapy:            "#22C55E",
    cell_therapy:            "#14B8A6",
    radiopharmaceutical:     "#F59E0B",
    oligonucleotide:         "#EF4444",
    peptide:                 "#A78BFA",
    vaccine:                 "#34D399",
  };
  const MODALITY_FALLBACK = "#475569";

  // Persona palette, mirrored verbatim from viz/alexis_weekly_dashboard.html.
  // Not surfaced yet in the MVP UI but kept here so Phase-2 panels (which
  // group analytics by persona) drop in cleanly.
  const TEAM_CFG = {
    BD:         { accent: "#3B82F6", mid: "#93C5FD" },
    Marketing:  { accent: "#8B5CF6", mid: "#C4B5FD" },
    Scientific: { accent: "#10B981", mid: "#6EE7B7" },
    Operations: { accent: "#F59E0B", mid: "#FCD34D" },
  };

  const EXAMPLES = {
    trastuzumab: {
      title: "A Phase 2 Study of Trastuzumab Deruxtecan in HER2-Positive Metastatic Breast Cancer",
      brief_summary: "An open-label, multicenter study evaluating trastuzumab deruxtecan (T-DXd) in patients with HER2-positive metastatic breast cancer who have progressed after at least one prior anti-HER2 therapy.",
      conditions: "HER2-positive breast cancer\nMetastatic breast cancer",
      interventions: "Trastuzumab deruxtecan\nCapecitabine",
      phase: "PHASE2",
      intervention_type: "DRUG",
      study_type: "INTERVENTIONAL",
    },
    pembrolizumab: {
      title: "A Phase 3 Study of Pembrolizumab Plus Chemotherapy in First-Line Non-Small Cell Lung Cancer",
      brief_summary: "A randomized, double-blind trial of pembrolizumab plus platinum-based chemotherapy versus placebo plus platinum-based chemotherapy in patients with previously untreated metastatic NSCLC.",
      conditions: "Non-small cell lung cancer\nNSCLC\nMetastatic lung cancer",
      interventions: "Pembrolizumab\nCarboplatin\nPemetrexed",
      phase: "PHASE3",
      intervention_type: "DRUG",
      study_type: "INTERVENTIONAL",
    },
    mrna1273: {
      title: "A Phase 3 Randomized Study of the mRNA-1273 Vaccine in Adults to Prevent COVID-19",
      brief_summary: "A randomized, placebo-controlled study evaluating the safety, efficacy, and immunogenicity of the mRNA-1273 SARS-CoV-2 vaccine in adults aged 18 years and older.",
      conditions: "COVID-19\nSARS-CoV-2 infection",
      interventions: "mRNA-1273 vaccine\nPlacebo",
      phase: "PHASE3",
      intervention_type: "BIOLOGICAL",
      study_type: "INTERVENTIONAL",
    },
  };

  // -------------------------------------------------------------------
  // DOM utility helpers
  // -------------------------------------------------------------------
  const $  = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class")       node.className = v;
        else if (k === "html")   node.innerHTML = v;
        else if (k === "text")   node.textContent = v;
        else if (k.startsWith("on") && typeof v === "function") {
          node.addEventListener(k.slice(2).toLowerCase(), v);
        } else if (v === false || v == null) {
          // skip
        } else if (v === true) {
          node.setAttribute(k, "");
        } else {
          node.setAttribute(k, v);
        }
      }
    }
    for (const child of children) {
      if (child == null || child === false) continue;
      if (typeof child === "string" || typeof child === "number") {
        node.appendChild(document.createTextNode(String(child)));
      } else {
        node.appendChild(child);
      }
    }
    return node;
  }

  function fmtBytes(n) {
    if (n == null || isNaN(n)) return "--";
    const u = ["B", "KB", "MB", "GB"];
    let i = 0;
    let v = Number(n);
    while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return v.toFixed(v >= 10 || i === 0 ? 0 : 1) + " " + u[i];
  }

  function humanModality(s) {
    if (!s) return "Unknown";
    if (s === "adc") return "ADC";
    if (s === "mab") return "mAb";
    return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function modalityColor(key) {
    if (!key) return MODALITY_FALLBACK;
    const k = String(key).toLowerCase();
    return MODALITY_COLORS[k] || MODALITY_FALLBACK;
  }

  // -------------------------------------------------------------------
  // API client
  // -------------------------------------------------------------------
  async function api(path, opts) {
    opts = opts || {};
    const init = {
      method: opts.method || "GET",
      headers: { "Accept": "application/json" },
    };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    const resp = await fetch(path, init);
    let data = null;
    try { data = await resp.json(); } catch (_e) { /* non-json */ }
    if (!resp.ok) {
      const msg = (data && (data.error || data.detail)) || ("HTTP " + resp.status);
      const err = new Error(msg);
      err.status = resp.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  // -------------------------------------------------------------------
  // Toasts
  // -------------------------------------------------------------------
  function showToast(msg, kind) {
    kind = kind || "info";
    const host = $("#toasts");
    if (!host) return;
    const cls = kind === "ok" ? "toast toast-ok"
              : kind === "err" ? "toast toast-err"
              : "toast toast-info";
    const t = el("div", { class: cls, role: "status" }, msg);
    host.appendChild(t);
    setTimeout(() => {
      t.classList.add("toast-leaving");
      setTimeout(() => { if (t.parentNode) t.parentNode.removeChild(t); }, 200);
    }, 3200);
  }

  // -------------------------------------------------------------------
  // Tabs
  // -------------------------------------------------------------------
  function setActiveTab(name) {
    $$(".nav-item").forEach((btn) => {
      const on = btn.dataset.tab === name;
      btn.classList.toggle("nav-item-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    $$(".panel").forEach((p) => {
      const on = p.id === ("panel-" + name);
      p.classList.toggle("panel-active", on);
      if (on) p.removeAttribute("hidden"); else p.setAttribute("hidden", "");
    });
    if (name === "dashboards") loadDashboards();
    if (name === "settings")   loadSettings();
    if (name === "jobs")     { loadJobCatalog(); loadJobRuns(); }
    try { history.replaceState(null, "", "#" + name); } catch (_e) { /* ignore */ }
  }

  const VALID_TABS = ["dashboards", "classifier", "jobs", "settings"];
  function initialTab() {
    const h = (location.hash || "").replace(/^#/, "");
    return VALID_TABS.indexOf(h) !== -1 ? h : "dashboards";
  }

  function bindTabs() {
    $$(".nav-item").forEach((btn) => {
      btn.addEventListener("click", () => setActiveTab(btn.dataset.tab));
    });
  }

  // -------------------------------------------------------------------
  // Health probe
  // -------------------------------------------------------------------
  let HEALTH_OK = true;
  async function loadHealth() {
    const pill = $("#health-pill");
    const text = $("#health-text");
    const banner = $("#banner");
    try {
      const data = await api("/api/health");
      if (data && data.ok) {
        HEALTH_OK = true;
        pill.classList.remove("health-pill-err");
        pill.classList.add("health-pill-ok");
        text.textContent = "online";
        banner.classList.add("banner-hidden");
        return true;
      }
      throw new Error("health-not-ok");
    } catch (e) {
      HEALTH_OK = false;
      pill.classList.remove("health-pill-ok");
      pill.classList.add("health-pill-err");
      text.textContent = "offline";
      banner.classList.remove("banner-hidden");
      $("#banner-text").textContent = "Connection lost - retrying in 5s...";
      return false;
    }
  }

  // -------------------------------------------------------------------
  // Dashboards
  // -------------------------------------------------------------------
  async function loadDashboards() {
    const list = $("#dash-list");
    list.innerHTML = "";
    list.appendChild(el("div", { class: "dash-loading" }, "Loading dashboards..."));
    try {
      const data = await api("/api/dashboards");
      list.innerHTML = "";
      const items = (data && data.available) || [];
      if (items.length === 0) {
        list.appendChild(el("div", { class: "dash-empty" },
          el("strong", null, "No dashboards yet"),
          el("div", null, "Generate one with "),
          el("code", null, "python -m pipelines.generate_weekly_viz"),
          el("div", { style: "margin-top:8px; font-family:var(--fm); font-size:10px; letter-spacing:0.10em;" },
            "Looking in: ", el("span", { class: "mono", style: "color:var(--cyan);" }, data.viz_dir || "--")
          )
        ));
        return;
      }
      for (const d of items) {
        list.appendChild(buildDashboardCard(d));
      }
    } catch (e) {
      list.innerHTML = "";
      list.appendChild(el("div", { class: "dash-empty" },
        el("strong", null, "Failed to load dashboards"),
        el("div", null, String(e.message || e))
      ));
    }
  }

  function buildDashboardCard(d) {
    return el("div", { class: "dash-card" },
      el("div", { class: "dash-card-head" },
        el("div", null,
          el("div", { class: "mono-tag", style: "margin-bottom:6px; display:inline-block;" }, String(d.id || "").toUpperCase()),
          el("div", { class: "dash-card-title" }, d.title || d.id || "Dashboard")
        ),
        el("div", { class: "dash-card-meta" }, fmtBytes(d.size_bytes))
      ),
      el("div", { class: "dash-card-filename" }, d.filename || ""),
      el("div", { class: "dash-card-actions" },
        el("button", {
          class: "btn btn-primary btn-sm",
          onclick: () => openDashboard(d),
        }, "Open"),
      )
    );
  }

  function openDashboard(d) {
    if (!d || !d.url) return;
    const viewer = $("#dash-viewer");
    const frame  = $("#dash-iframe");
    $("#dash-viewer-id").textContent = String(d.id || "").toUpperCase();
    $("#dash-viewer-name").textContent = d.title || d.id || "Dashboard";
    frame.src = d.url;
    viewer.classList.remove("dash-viewer-hidden");
    viewer.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function closeDashboardViewer() {
    const viewer = $("#dash-viewer");
    const frame  = $("#dash-iframe");
    viewer.classList.add("dash-viewer-hidden");
    frame.src = "about:blank";
  }

  function bindDashboards() {
    $("#dash-refresh").addEventListener("click", loadDashboards);
    $("#dash-viewer-close").addEventListener("click", closeDashboardViewer);
    $("#dash-viewer-open-tab").addEventListener("click", () => {
      const frame = $("#dash-iframe");
      if (frame.src && frame.src !== "about:blank") {
        window.open(frame.src, "_blank", "noopener");
      }
    });
  }

  // -------------------------------------------------------------------
  // Classifier
  // -------------------------------------------------------------------
  function splitLines(text) {
    if (!text) return [];
    return String(text)
      .split(/\r?\n|,/)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  }

  function loadExample(key) {
    const ex = EXAMPLES[key];
    if (!ex) return;
    $("#f-title").value         = ex.title;
    $("#f-summary").value       = ex.brief_summary;
    $("#f-conditions").value    = ex.conditions;
    $("#f-interventions").value = ex.interventions;
    $("#f-phase").value         = ex.phase || "";
    $("#f-itype").value         = ex.intervention_type || "DRUG";
    $("#f-stype").value         = ex.study_type || "INTERVENTIONAL";
  }

  function resetForm() {
    $("#classify-form").reset();
    $("#f-itype").value = "DRUG";
    $("#f-stype").value = "INTERVENTIONAL";
    $("#example-select").value = "";
    renderResultEmpty();
  }

  function renderResultEmpty() {
    const body = $("#result-body");
    body.className = "result-empty";
    body.innerHTML = "";
    body.appendChild(el("div", { class: "result-placeholder" },
      "Fill in the form and click ", el("strong", null, "Classify trial"), "."
    ));
  }

  function renderResultLoading() {
    const body = $("#result-body");
    body.className = "";
    body.innerHTML = "";
    body.appendChild(el("div", { class: "result-loading" }, "Loading..."));
  }

  function renderResultError(msg) {
    const body = $("#result-body");
    body.className = "";
    body.innerHTML = "";
    body.appendChild(el("div", { class: "result-error" }, msg));
  }

  function renderResult(res) {
    const body = $("#result-body");
    body.className = "";
    body.innerHTML = "";

    const modKey  = res.modality || "unknown";
    const modName = humanModality(modKey);
    const modHex  = res.modality_color || modalityColor(modKey);

    // Modality strip
    body.appendChild(el("div", { class: "result-modality" },
      el("div", {
        class: "result-swatch",
        style: "background:" + modHex + "; box-shadow: 0 0 16px " + modHex + "55, 0 0 14px rgba(0,0,0,0.4) inset;",
      }),
      el("div", null,
        el("div", { class: "result-modality-name", style: "color:" + modHex + ";" }, modName),
        el("div", { class: "result-modality-hex" }, modHex.toUpperCase() + " - " + (modKey || "unknown"))
      )
    ));

    // Therapeutic area
    body.appendChild(el("div", { class: "result-row" },
      el("div", { class: "result-row-key" }, "Therapeutic area"),
      el("div", { class: "result-row-val" }, res.therapeutic_area || el("span", { class: "mono", style: "color:var(--muted);" }, "--unassigned--"))
    ));

    // Drug-trial badge
    const isDrug = !!res.is_drug_trial;
    body.appendChild(el("div", { class: "result-row" },
      el("div", { class: "result-row-key" }, "Drug trial"),
      el("div", { class: "result-row-val" },
        el("span", { class: "badge " + (isDrug ? "badge-ok" : "badge-err") }, isDrug ? "YES" : "NO")
      )
    ));

    // Info flags
    const flags = Array.isArray(res.info_flags) ? res.info_flags : [];
    const flagsBox = el("div", { class: "result-flags" },
      el("div", { class: "result-flags-title" }, "Info flags (" + flags.length + ")")
    );
    if (flags.length === 0) {
      flagsBox.appendChild(el("div", { class: "flag-list-empty" }, "-- none --"));
    } else {
      const ul = el("ul", { class: "flag-list" });
      for (const f of flags) ul.appendChild(el("li", null, String(f)));
      flagsBox.appendChild(ul);
    }
    body.appendChild(flagsBox);

    // Echo
    const echo = res.echo || {};
    body.appendChild(el("div", { class: "result-echo" },
      "echo: ",
      el("span", { class: "mono" },
        (echo.title || "").slice(0, 60) + ((echo.title || "").length > 60 ? "..." : "")
      ),
      el("br"),
      el("span", { class: "mono" },
        "n_conditions=" + (echo.n_conditions == null ? "?" : echo.n_conditions) +
        " . n_interventions=" + (echo.n_interventions == null ? "?" : echo.n_interventions) +
        " . " + (echo.study_type || "") + " / " + (echo.intervention_type || "")
      )
    ));
  }

  async function submitClassify(e) {
    if (e) e.preventDefault();
    const title = $("#f-title").value.trim();
    const interventions = splitLines($("#f-interventions").value);

    if (!title) {
      renderResultError("Title is required.");
      $("#f-title").focus();
      return;
    }
    if (interventions.length === 0) {
      renderResultError("At least one intervention is required (one per line).");
      $("#f-interventions").focus();
      return;
    }

    const payload = {
      title: title,
      brief_summary: $("#f-summary").value.trim(),
      conditions: splitLines($("#f-conditions").value),
      interventions: interventions,
      intervention_type: $("#f-itype").value || "DRUG",
      study_type: $("#f-stype").value || "INTERVENTIONAL",
      phase: $("#f-phase").value || "",
    };

    const btn = $("#classify-submit");
    btn.disabled = true;
    renderResultLoading();
    try {
      const res = await api("/api/classify_trial", { method: "POST", body: payload });
      renderResult(res);
    } catch (err) {
      renderResultError("Classification failed: " + (err.message || err));
    } finally {
      btn.disabled = false;
    }
  }

  function bindClassifier() {
    $("#classify-form").addEventListener("submit", submitClassify);
    $("#classify-reset").addEventListener("click", resetForm);
    $("#example-select").addEventListener("change", (e) => {
      const key = e.target.value;
      if (key) loadExample(key);
    });
    renderResultEmpty();
  }

  // -------------------------------------------------------------------
  // Settings
  // -------------------------------------------------------------------
  async function loadSettings() {
    try {
      const s = await api("/api/settings");
      $("#kv-data-dir").textContent = s.data_dir || "--";
      $("#kv-app-root").textContent = s.app_root || "--";
      $("#kv-default").textContent  = s.default_data_dir || "--";
      $("#kv-config").textContent   = s.config_path || "--";
      $("#kv-frozen").textContent   = s.is_frozen ? "true (PyInstaller)" : "false (dev)";
      const badge = $("#data-valid-badge");
      badge.classList.remove("badge-ok", "badge-err", "badge-warn", "badge-muted");
      if (s.is_valid) {
        badge.classList.add("badge-ok");
        badge.textContent = "valid";
      } else {
        badge.classList.add("badge-err");
        badge.textContent = "invalid";
      }
    } catch (e) {
      const badge = $("#data-valid-badge");
      badge.classList.remove("badge-ok", "badge-err", "badge-warn");
      badge.classList.add("badge-muted");
      badge.textContent = "error";
      showToast("Failed to load settings: " + (e.message || e), "err");
    }
  }

  function showChangeForm(show) {
    const f = $("#data-change-form");
    f.classList.toggle("change-form-hidden", !show);
    if (show) {
      $("#data-change-input").value = $("#kv-data-dir").textContent || "";
      $("#data-change-msg").textContent = "";
      $("#data-change-msg").className = "change-msg";
      setTimeout(() => $("#data-change-input").focus(), 50);
    }
  }

  function clientCheckPath(p) {
    if (!p)               return { ok: false, msg: "Path is empty." };
    if (p !== p.trim())   return { ok: false, msg: "Path has leading or trailing whitespace." };
    if (p.length < 2)     return { ok: false, msg: "Path is too short." };
    return { ok: true, msg: "Path looks well-formed. Click Save to apply (the server validates the storage/ subfolder)." };
  }

  async function saveDataDir() {
    const input = $("#data-change-input");
    const msg   = $("#data-change-msg");
    const val   = input.value;

    const check = clientCheckPath(val);
    if (!check.ok) {
      msg.className = "change-msg change-msg-err";
      msg.textContent = check.msg;
      return;
    }

    const saveBtn = $("#data-change-save");
    saveBtn.disabled = true;
    msg.className = "change-msg";
    msg.textContent = "Saving...";
    try {
      const s = await api("/api/settings", { method: "POST", body: { data_dir: val } });
      msg.className = "change-msg change-msg-ok";
      msg.textContent = "Saved.";
      showChangeForm(false);
      showToast("Data folder updated", "ok");
      // Refresh panel from canonical response
      $("#kv-data-dir").textContent = s.data_dir || "--";
      $("#kv-app-root").textContent = s.app_root || "--";
      $("#kv-default").textContent  = s.default_data_dir || "--";
      $("#kv-config").textContent   = s.config_path || "--";
      $("#kv-frozen").textContent   = s.is_frozen ? "true (PyInstaller)" : "false (dev)";
      const badge = $("#data-valid-badge");
      badge.classList.remove("badge-ok", "badge-err", "badge-warn", "badge-muted");
      if (s.is_valid) {
        badge.classList.add("badge-ok");  badge.textContent = "valid";
      } else {
        badge.classList.add("badge-err"); badge.textContent = "invalid";
      }
    } catch (err) {
      msg.className = "change-msg change-msg-err";
      msg.textContent = "Server rejected the path: " + (err.message || err);
    } finally {
      saveBtn.disabled = false;
    }
  }

  function bindSettings() {
    $("#settings-refresh").addEventListener("click", loadSettings);
    $("#data-change-btn").addEventListener("click", () => showChangeForm(true));
    $("#data-change-cancel").addEventListener("click", () => showChangeForm(false));
    $("#data-change-save").addEventListener("click", saveDataDir);
    $("#data-change-validate").addEventListener("click", () => {
      const val = $("#data-change-input").value;
      const msg = $("#data-change-msg");
      const check = clientCheckPath(val);
      msg.className = "change-msg " + (check.ok ? "change-msg-ok" : "change-msg-err");
      msg.textContent = check.msg;
    });
    $("#data-change-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); saveDataDir(); }
      if (e.key === "Escape") { showChangeForm(false); }
    });
  }

  // -------------------------------------------------------------------
  // Jobs
  // -------------------------------------------------------------------
  let jobStream   = null;   // active EventSource (only one at a time)
  let activeRun   = null;   // the run object currently shown in the console

  function jobStatusBadgeClass(status) {
    switch (status) {
      case "running":   return "badge badge-running";
      case "succeeded": return "badge badge-ok";
      case "failed":    return "badge badge-err";
      case "cancelled": return "badge badge-cancelled";
      default:          return "badge badge-muted";
    }
  }

  function fmtTime(iso) {
    if (!iso) return "--";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return "--";
    return d.toLocaleTimeString();
  }

  // Category display order + friendly section titles.
  const JOB_SECTIONS = [
    ["chain",       "One-click refresh"],
    ["us",          "US trials (ClinicalTrials.gov)"],
    ["chictr",      "China (ChiCTR)"],
    ["anzctr",      "Australia (ANZCTR)"],
    ["dashboard",   "Dashboards"],
    ["maintenance", "Maintenance"],
    ["diagnostic",  "Diagnostics"],
  ];

  async function loadJobCatalog() {
    const host = $("#jobs-catalog");
    host.innerHTML = "";
    host.appendChild(el("div", { class: "dash-loading" }, "Loading pipelines..."));
    try {
      const data = await api("/api/jobs/catalog");
      host.innerHTML = "";
      const jobs = (data && data.jobs) || [];
      if (jobs.length === 0) {
        host.appendChild(el("div", { class: "jobs-runs-empty" }, "No pipelines registered."));
        return;
      }
      const byCat = {};
      for (const j of jobs) (byCat[j.category] = byCat[j.category] || []).push(j);
      for (const [cat, title] of JOB_SECTIONS) {
        const items = byCat[cat];
        if (!items || !items.length) continue;
        host.appendChild(el("div", { class: "jobs-section-title" }, title));
        const grid = el("div", { class: cat === "chain" ? "jobs-chain-grid" : "jobs-catalog-grid" });
        for (const j of items) grid.appendChild(buildJobCard(j));
        host.appendChild(grid);
      }
    } catch (e) {
      host.innerHTML = "";
      host.appendChild(el("div", { class: "jobs-runs-empty" }, "Failed to load pipelines: " + (e.message || e)));
    }
  }

  function buildJobCard(j) {
    const isChain = !!j.is_chain;
    const hasParams = Array.isArray(j.params) && j.params.length > 0;
    const card = el("div", { class: "job-card" + (isChain ? " job-card-chain" : "") });

    card.appendChild(el("div", { class: "job-card-head" },
      el("div", { class: "job-card-title" }, j.label || j.id),
      j.long_running ? el("span", { class: "job-longhint" }, "long-running") : null
    ));
    card.appendChild(el("div", { class: "job-card-desc" }, j.description || ""));

    const runBtn = el("button", {
      class: isChain ? "btn btn-primary" : "btn btn-primary btn-sm",
      disabled: !j.ready,
      onclick: () => hasParams ? toggleParamForm(card, j) : startJob(j.id),
    }, j.ready ? (isChain ? "Run" : (hasParams ? "Configure & run" : "Run")) : "Not ready");

    card.appendChild(el("div", { class: "job-card-foot" },
      isChain
        ? el("span", { class: "job-cat job-cat-chain" }, "CHAIN")
        : el("span", { class: "job-cat job-cat-" + (j.category || "diagnostic") },
             String(j.category || "").toUpperCase()),
      runBtn
    ));
    return card;
  }

  // -- Parameter form (inline, expands under a job card) --------------------
  async function toggleParamForm(card, job) {
    const existing = card.querySelector(".param-form");
    if (existing) { existing.remove(); return; }

    const form = el("div", { class: "param-form" });
    form.appendChild(el("div", { class: "param-form-loading" }, "Loading options..."));
    card.appendChild(form);

    // Build inputs (fetch options for any 'select' provider).
    const inputs = {};
    const rows = [];
    for (const p of job.params) {
      let control;
      if (p.type === "select") {
        let opts = [];
        try { opts = (await api("/api/jobs/options/" + encodeURIComponent(p.provider))).options || []; }
        catch (_e) { opts = []; }
        const sel = el("select", { class: "select" });
        if (!p.required) sel.appendChild(el("option", { value: "" }, "-- none --"));
        opts.forEach((o, i) => {
          const opt = el("option", { value: o.value }, o.label);
          sel.appendChild(opt);
        });
        const di = typeof p.default_index === "number" ? p.default_index : 0;
        if (opts.length) sel.selectedIndex = (p.required ? di : di + 1);
        if (!opts.length) { sel.appendChild(el("option", { value: "" }, "(none found)")); sel.disabled = true; }
        control = sel;
      } else if (p.type === "bool") {
        control = el("input", { type: "checkbox" });
        if (p.default) control.checked = true;
      } else if (p.type === "int") {
        control = el("input", { type: "number", class: "input", placeholder: p.label, value: p.default != null ? String(p.default) : "" });
      } else {
        control = el("input", { type: "text", class: "input", placeholder: p.label, value: p.default != null ? String(p.default) : "" });
      }
      inputs[p.name] = { control, spec: p };
      rows.push(el("label", { class: "param-field" },
        el("span", { class: "param-label" }, p.label + (p.required ? " *" : "")),
        control
      ));
    }

    const msg = el("div", { class: "param-msg" });
    const submit = el("button", { class: "btn btn-primary btn-sm", onclick: async () => {
      const params = {};
      for (const [name, { control, spec }] of Object.entries(inputs)) {
        let v = spec.type === "bool" ? control.checked : control.value;
        if (spec.required && (v === "" || v == null)) {
          msg.className = "param-msg param-msg-err";
          msg.textContent = spec.label + " is required.";
          return;
        }
        params[name] = v;
      }
      form.remove();
      startJob(job.id, params);
    } }, "Run");
    const cancel = el("button", { class: "btn btn-secondary btn-sm", onclick: () => form.remove() }, "Cancel");

    form.innerHTML = "";
    rows.forEach((r) => form.appendChild(r));
    form.appendChild(msg);
    form.appendChild(el("div", { class: "param-actions" }, cancel, submit));
  }

  async function loadJobRuns() {
    const host = $("#jobs-runs");
    try {
      const data = await api("/api/jobs");
      const runs = (data && data.runs) || [];
      host.innerHTML = "";
      if (runs.length === 0) {
        host.appendChild(el("div", { class: "jobs-runs-empty" }, "No runs yet."));
        return;
      }
      for (const r of runs) host.appendChild(buildRunRow(r));
    } catch (e) {
      host.innerHTML = "";
      host.appendChild(el("div", { class: "jobs-runs-empty" }, "Failed to load runs: " + (e.message || e)));
    }
  }

  function buildRunRow(r) {
    const active = activeRun && activeRun.run_id === r.run_id;
    return el("div", {
        class: "run-row" + (active ? " run-row-active" : ""),
        onclick: () => openRunConsole(r),
      },
      el("span", { class: jobStatusBadgeClass(r.status) }, r.status),
      el("span", { class: "run-row-label" }, r.label || r.job_id),
      el("span", { class: "run-row-time" }, fmtTime(r.started_at))
    );
  }

  function closeStream() {
    if (jobStream) {
      try { jobStream.close(); } catch (_e) { /* ignore */ }
      jobStream = null;
    }
  }

  function setConsoleStatus(status) {
    const badge = $("#console-status");
    badge.className = jobStatusBadgeClass(status);
    badge.textContent = status;
    $("#console-cancel").hidden = (status !== "running" && status !== "pending");
  }

  function consoleNearBottom() {
    const out = $("#console-out");
    return (out.scrollHeight - out.scrollTop - out.clientHeight) < 40;
  }

  function appendConsole(text) {
    const out = $("#console-out");
    const stick = consoleNearBottom();
    // Color whole lines by their ASCII tag prefix; use textContent (no XSS).
    const lines = String(text).split(/(?<=\n)/);  // keep newlines
    for (const line of lines) {
      if (line === "") continue;
      let cls = null;
      if (line.includes("[err]"))       cls = "ln-err";
      else if (line.includes("[warn]")) cls = "ln-warn";
      else if (line.includes("[ok]"))   cls = "ln-ok";
      else if (line.includes("[info]")) cls = "ln-info";
      out.appendChild(el("span", cls ? { class: cls } : null, line));
    }
    if (stick) out.scrollTop = out.scrollHeight;
  }

  function resetConsole(run) {
    closeStream();
    activeRun = run || null;
    $("#console-id").textContent = run ? String(run.job_id || "").toUpperCase() : "--";
    $("#console-label").textContent = run ? (run.label || run.job_id) : "No job selected";
    const out = $("#console-out");
    out.innerHTML = "";
    setConsoleStatus(run ? run.status : "idle");
  }

  function openRunConsole(run) {
    if (!run || !run.run_id) return;
    resetConsole(run);
    // highlight the active row
    loadJobRuns();

    const runId = run.run_id;
    const stream = new EventSource("/api/jobs/" + encodeURIComponent(runId) + "/logs");
    jobStream = stream;

    stream.addEventListener("log", (ev) => {
      appendConsole(ev.data);
    });
    stream.addEventListener("end", (ev) => {
      let info = {};
      try { info = JSON.parse(ev.data); } catch (_e) { /* ignore */ }
      const status = info.status || "succeeded";
      setConsoleStatus(status);
      closeStream();
      loadJobRuns();
      if (activeRun) activeRun.status = status;
      // If a generate job succeeded and produced a dashboard, refresh the list.
      if (status === "succeeded" && run.produces && /\.html$/i.test(run.produces)) {
        loadDashboards();
        showToast("Dashboard updated - open it in the Dashboards tab", "ok");
      } else if (status === "succeeded") {
        showToast((run.label || "Job") + " finished", "ok");
      } else if (status === "failed") {
        showToast((run.label || "Job") + " failed (see console)", "err");
      }
    });
    stream.onerror = () => {
      // Browser will retry by default; for a terminal run we already closed it.
      const cur = activeRun;
      if (cur && (cur.status === "succeeded" || cur.status === "failed" || cur.status === "cancelled")) {
        closeStream();
        return;
      }
      appendConsole("[warn] log stream interrupted - retrying...\n");
    };
  }

  async function startJob(jobId, params) {
    try {
      const body = { job_id: jobId };
      if (params) body.params = params;
      const run = await api("/api/jobs", { method: "POST", body: body });
      setActiveTab("jobs");
      showToast("Started: " + (run.label || jobId), "info");
      openRunConsole(run);
      loadJobRuns();
    } catch (e) {
      showToast("Could not start job: " + (e.message || e), "err");
    }
  }

  async function cancelRun() {
    if (!activeRun || !activeRun.run_id) return;
    const btn = $("#console-cancel");
    btn.disabled = true;
    try {
      const run = await api("/api/jobs/" + encodeURIComponent(activeRun.run_id) + "/cancel", { method: "POST" });
      activeRun.status = run.status;
      setConsoleStatus(run.status);
      showToast("Cancellation requested", "info");
      loadJobRuns();
    } catch (e) {
      showToast("Cancel failed: " + (e.message || e), "err");
    } finally {
      btn.disabled = false;
    }
  }

  function bindJobs() {
    $("#jobs-refresh").addEventListener("click", () => { loadJobCatalog(); loadJobRuns(); });
    $("#console-cancel").addEventListener("click", cancelRun);
    $("#console-clear").addEventListener("click", () => {
      closeStream();
      resetConsole(null);
      $("#console-out").innerHTML = "";
      $("#console-out").appendChild(el("span", { class: "console-hint" },
        "Select a job and click Run, or pick a recent run to view its log."));
      loadJobRuns();
    });
  }

  // -------------------------------------------------------------------
  // Boot
  // -------------------------------------------------------------------
  function boot() {
    bindTabs();
    bindDashboards();
    bindClassifier();
    bindJobs();
    bindSettings();

    // First paint: honor the tab in the URL hash (so a reload keeps your place).
    const startTab = initialTab();
    loadHealth().then(() => {
      setActiveTab(startTab);
      // Warm settings so a quick tab-switch shows real values rather than "--".
      if (startTab !== "settings") loadSettings();
    });

    // Periodic health probe
    setInterval(loadHealth, 5000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
