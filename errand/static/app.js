// Errand dashboard. Plain JS + AG Grid; every page calls the same /v1 JSON API the agents use.
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const page = document.body.dataset.page;

  async function api(path, opts = {}) {
    const init = { credentials: "same-origin", headers: { "Content-Type": "application/json" }, ...opts };
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    const r = await fetch(path, init);
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || (typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail)) || r.statusText);
    return j;
  }
  const usd = (v, d = 4) => (v == null ? "" : "$" + Number(v).toFixed(d));
  const pct = (v) => (v == null ? "" : (100 * v).toFixed(0) + "%");
  const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function toast(msg, kind = "") {
    const el = document.createElement("div");
    el.className = "flash " + kind;
    el.textContent = msg;
    $("#toast").appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  const grids = {};
  function grid(sel, columnDefs, rowData, extra = {}) {
    const el = $(sel);
    if (!el) return;
    if (grids[sel]) { grids[sel].setGridOption("rowData", rowData); return grids[sel]; }
    grids[sel] = agGrid.createGrid(el, {
      columnDefs, rowData, domLayout: "autoHeight", pagination: rowData.length > 15, paginationPageSize: 15,
      paginationPageSizeSelector: false,
      defaultColDef: { sortable: true, filter: true, resizable: true, flex: 1, minWidth: 105 },
      overlayNoRowsTemplate: '<span class="muted">Nothing here yet</span>', ...extra,
    });
    return grids[sel];
  }
  const badge = (text, kind) => `<span class="badge ${kind || ""}">${esc(text)}</span>`;
  const statusBadge = (s) => badge(s, { active: "ok", completed: "ok", passed: "ok", delivered: "ok", suspended: "bad", failed: "bad", rejected: "bad", onboarding: "warn", needs_bond: "warn", running: "warn" }[s]);

  async function withBusy(btn, fn) {
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Working...";
    try { await fn(); } catch (e) { toast(e.message, "bad"); } finally { btn.disabled = false; btn.textContent = label; }
  }

  // copy buttons
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    navigator.clipboard.writeText($(b.dataset.copy).textContent.trim()).then(() => toast("Copied", "ok"));
  }));

  // ---------- leaderboard (index + leaderboard pages) ----------
  const lbCols = [
    { field: "name", headerName: "Runner", minWidth: 110 },
    { field: "declared_model", headerName: "Model", minWidth: 170 },
    { field: "status", cellRenderer: (p) => statusBadge(p.value), minWidth: 110 },
    { field: "rating", headerName: "Rating", sort: "desc" },
    { field: "quality_lcb", headerName: "Quality (LCB)", valueFormatter: (p) => pct(p.value) },
    { field: "verified", headerName: "Samples" },
    { field: "price_usd", headerName: "Price", valueFormatter: (p) => usd(p.value) },
    { field: "p95_ms", headerName: "p95 ms" },
    { field: "uptime", valueFormatter: (p) => pct(p.value) },
    { field: "brier", headerName: "Brier" },
    { field: "exam_rate", headerName: "Exam", valueFormatter: (p) => pct(p.value) },
    { field: "mystery_rate", headerName: "Mystery", valueFormatter: (p) => pct(p.value) },
  ];
  async function initLeaderboard() {
    const tabs = $$("#lb-tabs button");
    async function load(lane) {
      tabs.forEach((t) => t.classList.toggle("active", t.dataset.lane === lane));
      grid("#lb-grid", lbCols, await api(`/v1/leaderboard?lane=${encodeURIComponent(lane)}`));
    }
    tabs.forEach((t) => t.addEventListener("click", () => load(t.dataset.lane)));
    if (tabs.length) await load(tabs[0].dataset.lane);
  }

  // ---------- sender ----------
  async function initSender() {
    let demoTasks = null;
    const laneSel = $("#lane");

    async function refresh() {
      const me = await api("/v1/me");
      const b = me.balances, a = me.activity;
      $("#k-wallet").textContent = usd(b.wallet || 0, 2);
      $("#k-spent").textContent = usd(a.spend_30d_usd, 4);
      $("#k-errands").textContent = `${a.errands_30d} errands`;
      $("#k-saved").textContent = usd(a.saved_30d_usd, 4);
      $("#k-tier").textContent = me.tier.name;
      $("#k-tier-next").textContent = me.tier.next ? `${usd(me.tier.next.spend_needed_usd, 2)} more to ${me.tier.next.name}` : "top tier";
      $("#k-div").textContent = usd(a.dividends_usd, 4);
      const acc = me.account;
      $("#cap1").value = (acc.cap_per_errand / 1e6).toString();
      $("#capd").value = (acc.cap_daily / 1e6).toString();
      $("#defpreset").value = acc.preset;
      $("#consent").value = String(acc.consent_level);
      const errands = await api("/v1/errands");
      grid("#errands-grid", [
        { field: "created_at", headerName: "When", valueFormatter: (p) => when(p.value), minWidth: 160 },
        { field: "lane", minWidth: 140 },
        { field: "kind", maxWidth: 100 },
        { field: "status", cellRenderer: (p) => statusBadge(p.value), maxWidth: 120 },
        { field: "verdict", cellRenderer: (p) => (p.value ? statusBadge(p.value) : ""), maxWidth: 120 },
        { field: "answer", minWidth: 90 },
        { headerName: "Runner", valueGetter: (p) => p.data.runner && p.data.runner.name },
        { field: "total_usd", headerName: "Cost", valueFormatter: (p) => usd(p.value) },
        { field: "saved_usd", headerName: "Saved", valueFormatter: (p) => usd(p.value) },
        { field: "latency_ms", headerName: "ms", maxWidth: 90 },
        { field: "policy", maxWidth: 110 },
        { headerName: "Feedback", minWidth: 130, cellRenderer: (p) => {
          if (p.data.status !== "completed") return "";
          if (p.data.feedback) return p.data.feedback > 0 ? "accepted" : "disputed";
          return `<a href="#" data-fb="1" data-id="${p.data.id}">accept</a> · <a href="#" data-fb="0" data-id="${p.data.id}">dispute</a>`;
        } },
      ], errands);
      grid("#ops-grid", opsCols, await api("/v1/paypal/ops"));
    }

    function showLaneFields() {
      const code = laneSel.value === "code.python.tests";
      $("#fields-math").hidden = code;
      $("#fields-code").hidden = !code;
      refreshRec();
    }
    function payload() {
      if (laneSel.value === "code.python.tests") {
        return { function_name: $("#function_name").value, spec: $("#spec").value, tests: $("#tests").value };
      }
      const p = { problem: $("#problem").value };
      if ($("#expected").value.trim()) p.expected = $("#expected").value.trim();
      return p;
    }
    async function refreshRec() {
      const preset = $("#preset").value || "balanced";
      const r = await api(`/v1/recommend?lane=${encodeURIComponent(laneSel.value)}&preset=${preset}`);
      grid("#rec-grid", [
        { field: "name", headerName: "Runner" },
        { field: "price_usd", headerName: "Price", valueFormatter: (p) => usd(p.value) },
        { field: "expected_pass_rate", headerName: "Pass", valueFormatter: (p) => pct(p.value) },
        { field: "p95_latency_ms", headerName: "p95 ms" },
        { field: "score", headerName: "Score" },
      ], r.runners);
    }
    function renderResult(e) {
      const ok = e.status === "completed";
      $("#result").innerHTML = `
        <div class="head">${statusBadge(e.status)} ${e.verdict ? statusBadge(e.verdict) : ""}
          ${e.runner ? `<span>by <b>${esc(e.runner.name)}</b> <span class="muted">${esc(e.runner.model)}</span></span>` : ""}</div>
        ${ok ? `<div class="receipt">
          <div><span>Answer</span><span>${esc(e.answer ?? "")}</span></div>
          <div><span>Runner price</span><span>${usd(e.price_usd, 6)}</span></div>
          <div><span>Errand fee</span><span>${usd(e.fee_usd, 6)}</span></div>
          ${e.dividend_usd ? `<div><span>Data dividend</span><span>-${usd(e.dividend_usd, 6)}</span></div>` : ""}
          <div class="total"><span>You paid</span><span>${usd(e.total_usd, 6)}</span></div>
          <div><span>Frontier estimate</span><span>${usd(e.baseline_usd, 6)}</span></div>
          <div><span>Latency, attempts, policy</span><span>${e.latency_ms} ms, ${e.attempts}, ${esc(e.policy)}</span></div>
        </div>` : `<p class="muted">${esc(e.detail || "")}</p>`}
        ${ok ? `<p class="small muted">${esc(e.detail || "")}</p><details><summary class="small">Full output</summary><pre>${esc(e.output)}</pre></details>` : ""}`;
    }

    laneSel.addEventListener("change", showLaneFields);
    $("#preset").addEventListener("change", refreshRec);
    $("#example-btn").addEventListener("click", async () => {
      demoTasks = demoTasks || (await api("/v1/demo/tasks"));
      const list = demoTasks[laneSel.value];
      const t = list[Math.floor(Math.random() * list.length)];
      if (laneSel.value === "code.python.tests") {
        $("#function_name").value = t.function_name; $("#spec").value = t.spec; $("#tests").value = t.tests;
      } else {
        $("#problem").value = t.problem; $("#expected").value = t.expected;
      }
    });
    $("#errand-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      withBusy($("#send-btn"), async () => {
        const body = { lane: laneSel.value, payload: payload() };
        if ($("#preset").value) body.preset = $("#preset").value;
        if ($("#budget").value) body.budget_usd = Number($("#budget").value);
        const e = await api("/v1/errands", { method: "POST", body });
        renderResult(e);
        await refresh(); await refreshRec();
      });
    });
    $("#bounty-btn").addEventListener("click", () => withBusy($("#bounty-btn"), async () => {
      const amt = prompt("Bounty amount in USD (charged through PayPal only if the work is verified):", "2");
      if (!amt) return;
      const r = await api("/v1/bounties", { method: "POST", body: { lane: laneSel.value, payload: payload(), amount_usd: Number(amt) } });
      location.href = r.approve_url;
    }));
    $("#topup-btn").addEventListener("click", () => withBusy($("#topup-btn"), async () => {
      const r = await api("/v1/wallet/topup", { method: "POST", body: { amount_usd: Number($("#topup-amt").value), purpose: "wallet" } });
      location.href = r.approve_url;
    }));
    $("#settings-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      try {
        await api("/v1/me", { method: "PATCH", body: {
          cap_per_errand_usd: Number($("#cap1").value), cap_daily_usd: Number($("#capd").value),
          preset: $("#defpreset").value, consent_level: Number($("#consent").value) } });
        toast("Saved", "ok"); refresh();
      } catch (e) { toast(e.message, "bad"); }
    });
    $("#errands-grid").addEventListener("click", async (ev) => {
      const a = ev.target.closest("a[data-fb]");
      if (!a) return;
      ev.preventDefault();
      try { await api(`/v1/errands/${a.dataset.id}/feedback`, { method: "POST", body: { accepted: a.dataset.fb === "1" } }); refresh(); }
      catch (e) { toast(e.message, "bad"); }
    });
    showLaneFields();
    await refresh();
  }

  const opsCols = [
    { field: "created_at", headerName: "When", valueFormatter: (p) => when(p.value), minWidth: 160 },
    { field: "kind", maxWidth: 120 },
    { field: "purpose", maxWidth: 110 },
    { field: "amount_usd", headerName: "Amount", valueFormatter: (p) => usd(p.value, 2), maxWidth: 110 },
    { field: "status", maxWidth: 120 },
    { field: "paypal_id", headerName: "PayPal ID", minWidth: 190 },
    { field: "detail", headerName: "Auth / capture", minWidth: 160 },
  ];

  // ---------- runner ----------
  async function initRunner() {
    const kindSel = $("#kind");
    function showCfg() {
      $("#cfg-openai").hidden = kindSel.value !== "openai";
      $("#cfg-webhook").hidden = kindSel.value !== "webhook";
      $("#cfg-sim").hidden = kindSel.value !== "simulated";
    }
    kindSel.addEventListener("change", showCfg);
    let poll = null;

    async function refresh(fillForm = false) {
      const me = await api("/v1/me");
      const b = me.balances, r = me.runner;
      $("#k-status").innerHTML = statusBadge(me.status);
      $("#k-model").textContent = r ? r.declared_model : "no model registered";
      $("#k-earn").textContent = usd(b.earnings || 0, 4);
      $("#k-bond").textContent = usd(b.bond || 0, 2);
      $("#k-served").textContent = me.served.errands;
      $("#k-gross").textContent = `${usd(me.served.gross_usd, 4)} gross`;
      $("#k-rating").textContent = me.lanes.length ? Math.max(...me.lanes.map((l) => l.rating)) : "n/a";
      $("#min-bond").textContent = me.min_bond_usd.toFixed(2);
      const msgs = {
        unregistered: "Register your model below to get started.",
        needs_bond: "Post your bond with PayPal to start the onboarding exam.",
        onboarding: "Onboarding exam in progress. This page refreshes automatically.",
        rejected: "Your model did not pass the onboarding exam. Update it and save to retry.",
        suspended: "Suspended: see the integrity flags below.",
      };
      $("#status-banner").innerHTML = msgs[me.status] ? `<div class="flash ${me.status === "suspended" || me.status === "rejected" ? "bad" : ""}">${msgs[me.status]}</div>` : "";
      clearTimeout(poll);
      if (me.status === "onboarding") poll = setTimeout(() => refresh(), 2500);

      grid("#lanes-grid", [
        { field: "lane", minWidth: 150 },
        { field: "rating" },
        { field: "lcb", headerName: "Quality (LCB)", valueFormatter: (p) => pct(p.value) },
        { field: "n_verified", headerName: "Samples" },
        { field: "price_usd", headerName: "Price", valueFormatter: (p) => usd(p.value) },
        { field: "p95_ms", headerName: "p95 ms", valueFormatter: (p) => Math.round(p.value) },
        { field: "uptime", valueFormatter: (p) => pct(p.value) },
        { field: "brier", valueFormatter: (p) => (p.value == null ? "" : p.value.toFixed(3)) },
        { field: "exam_rate", headerName: "Exam", valueFormatter: (p) => pct(p.value) },
        { field: "mystery_rate", headerName: "Mystery", valueFormatter: (p) => pct(p.value) },
      ], me.lanes);

      $("#flags").innerHTML = me.flags.length
        ? me.flags.map((f) => `<div class="flash bad"><b>${esc(f.kind)}</b> in ${esc(f.lane)}: ${esc(f.detail)}<br><span class="small">Slashed ${usd(f.slashed / 1e6, 2)}, refunded ${usd(f.refunded / 1e6, 4)} to Senders.</span></div>`).join("")
        : '<p class="muted">No flags. Keep serving the model you declared.</p>';

      if (fillForm) {
        $("#pp-email").value = me.account.paypal_email || "";
        if (r) {
          $("#model").value = r.declared_model;
          kindSel.value = r.kind;
          const c = r.config || {};
          $("#base_url").value = c.base_url || ""; $("#cfg_model").value = c.model || ""; $("#api_key_env").value = c.api_key_env || "";
          $("#url").value = c.url || "";
          if (r.kind === "simulated") $("#sim_json").value = JSON.stringify(c);
          $$(".lane-on").forEach((cb) => { cb.checked = r.lanes[cb.value] != null; });
          $$(".lane-price").forEach((inp) => { if (r.lanes[inp.dataset.lane] != null) inp.value = r.lanes[inp.dataset.lane]; });
        }
        showCfg();
      }
      grid("#jobs-grid", [
        { field: "created_at", headerName: "When", valueFormatter: (p) => when(p.value), minWidth: 160 },
        { field: "lane", minWidth: 140 },
        { field: "status", cellRenderer: (p) => statusBadge(p.value), maxWidth: 120 },
        { field: "verdict", cellRenderer: (p) => (p.value ? statusBadge(p.value) : ""), maxWidth: 120 },
        { field: "answer" },
        { field: "price_usd", headerName: "Paid", valueFormatter: (p) => usd(p.value) },
        { field: "latency_ms", headerName: "ms" },
      ], await api("/v1/errands"));
      grid("#ops-grid", opsCols, await api("/v1/paypal/ops"));
    }

    $("#profile-form").addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const lanesMap = {};
      $$(".lane-on").forEach((cb) => {
        if (cb.checked) lanesMap[cb.value] = Number($(`.lane-price[data-lane="${cb.value}"]`).value || 0.001);
      });
      let config = {};
      if (kindSel.value === "openai") {
        config = { base_url: $("#base_url").value, model: $("#cfg_model").value };
        if ($("#api_key_env").value) config.api_key_env = $("#api_key_env").value;
      } else if (kindSel.value === "webhook") config = { url: $("#url").value };
      else {
        try { config = JSON.parse($("#sim_json").value); } catch { return toast("Simulation config is not valid JSON", "bad"); }
      }
      try {
        await api("/v1/runner/profile", { method: "PUT", body: { declared_model: $("#model").value, kind: kindSel.value, config, lanes: lanesMap } });
        toast("Saved. Exam starts as soon as your bond is posted.", "ok");
        refresh();
      } catch (e) { toast(e.message, "bad"); }
    });
    $("#bond-btn").addEventListener("click", () => withBusy($("#bond-btn"), async () => {
      const r = await api("/v1/wallet/topup", { method: "POST", body: { amount_usd: Number($("#bond-amt").value), purpose: "bond" } });
      location.href = r.approve_url;
    }));
    $("#email-btn").addEventListener("click", async () => {
      try { await api("/v1/me", { method: "PATCH", body: { paypal_email: $("#pp-email").value } }); toast("PayPal email saved", "ok"); }
      catch (e) { toast(e.message, "bad"); }
    });
    $("#wd-btn").addEventListener("click", () => withBusy($("#wd-btn"), async () => {
      const r = await api("/v1/runner/withdraw", { method: "POST", body: { amount_usd: Number($("#wd-amt").value) } });
      toast(`Payout ${r.status}: ${usd(r.amount_usd, 2)} (batch ${r.payout_batch_id})`, "ok");
      refresh();
    }));
    $("#receipts-btn").addEventListener("click", async () => {
      try {
        const data = await api("/v1/runner/receipts");
        const a = document.createElement("a");
        a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
        a.download = "errand-receipts.json"; a.click();
        toast(`${data.length} receipts downloaded`, "ok");
      } catch (e) { toast(e.message, "bad"); }
    });
    await refresh(true);
  }

  // ---------- platform ----------
  async function initPlatform() {
    async function refresh() {
      const o = await api("/v1/platform/overview");
      $("#k-rev").textContent = usd(o.revenue_usd, 4);
      $("#k-gmv").textContent = usd(o.gmv_usd, 4);
      $("#k-done").textContent = `${o.errands_completed} errands completed`;
      $("#k-pp").textContent = usd(o.paypal_net_inflow_usd, 2);
      $("#k-ppmode").textContent = `PayPal ${o.paypal_mode}`;
      $("#k-mys").textContent = o.mystery.sent;
      $("#k-mys-pass").textContent = `${o.mystery.passed} passed`;
      $("#k-ledger").innerHTML = o.ledger_balanced ? badge("balanced", "ok") : badge("UNBALANCED", "bad");
      grid("#flags-grid", [
        { field: "created_at", headerName: "When", valueFormatter: (p) => when(p.value), minWidth: 160 },
        { field: "name", headerName: "Runner" }, { field: "lane" }, { field: "kind" },
        { field: "slashed", valueFormatter: (p) => usd(p.value / 1e6, 2) },
        { field: "refunded", valueFormatter: (p) => usd(p.value / 1e6, 4) },
        { field: "detail", minWidth: 380, wrapText: true, autoHeight: true },
      ], o.flags);
      grid("#ledger-grid", [
        { field: "id", maxWidth: 80 },
        { field: "created_at", headerName: "When", valueFormatter: (p) => when(p.value), minWidth: 160 },
        { field: "name", headerName: "Account" }, { field: "bucket", maxWidth: 110 },
        { field: "amount_usd", headerName: "Amount", valueFormatter: (p) => usd(p.value, 6) },
        { field: "memo", minWidth: 180 }, { field: "ref", minWidth: 160 }, { field: "txn", minWidth: 160 },
      ], await api("/v1/platform/ledger"));
      grid("#ops-grid", opsCols, await api("/v1/paypal/ops"));
    }
    $$(".mystery-btn").forEach((b) => b.addEventListener("click", () => withBusy(b, async () => {
      const r = await api(`/v1/platform/mystery?lane=${encodeURIComponent(b.dataset.lane)}`, { method: "POST" });
      if (r.error) return toast(r.error, "bad");
      toast(`Mystery errand to ${r.runner_id}: ${r.passed ? "passed" : "failed"}${r.flag ? ". FLAGGED and slashed." : ""}`, r.flag ? "bad" : "ok");
      refresh();
    })));
    await refresh();
  }

  function initConnect() {
    const tabs = $$("#client-tabs button");
    tabs.forEach((t) => t.addEventListener("click", () => {
      tabs.forEach((x) => x.classList.toggle("active", x === t));
      $$(".client-snippet").forEach((s) => { s.hidden = s.dataset.i !== t.dataset.i; });
    }));
    return Promise.resolve();
  }

  const inits = { connect: initConnect, index: initLeaderboard, leaderboard: initLeaderboard, sender: initSender, runner: initRunner, platform: initPlatform };
  if (inits[page]) inits[page]().catch((e) => toast(e.message, "bad"));
})();
