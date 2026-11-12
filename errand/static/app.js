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
  // display money: enough digits to be honest, few enough to read ($0.0009, $0.012, $1.89)
  const money = (v) => (v == null ? "" : "$" + Number(v).toFixed(Math.abs(v) >= 1 ? 2 : Math.abs(v) >= 0.01 ? 3 : 4));
  const pct = (v) => (v == null ? "" : (100 * v).toFixed(0) + "%");
  const ago = (t) => {
    if (!t) return "";
    const s = Math.max(0, Date.now() / 1000 - t);
    return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)}m ago` : s < 86400 ? `${Math.floor(s / 3600)}h ago` : new Date(t * 1000).toLocaleDateString();
  };
  const taskText = (e) => {
    const p = e.payload || {};
    return p.problem || (p.function_name ? `Write ${p.function_name}(): ${p.spec || ""}` : p.spec || e.lane);
  };
  const resultOf = (e) => (e.status === "running" ? "running" : e.status !== "completed" ? "refunded" : e.verdict === "passed" ? "verified" : "delivered");
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
  const statusBadge = (s) => badge(s, { active: "ok", completed: "ok", passed: "ok", delivered: "ok", suspended: "bad", failed: "bad", rejected: "bad", onboarding: "warn", needs_bond: "warn", running: "warn", pinned: "ok" }[s]);

  async function withBusy(btn, fn) {
    const label = btn.textContent;
    btn.disabled = true; btn.textContent = "Working...";
    try { await fn(); } catch (e) { toast(e.message, "bad"); } finally { btn.disabled = false; btn.textContent = label; }
  }

  // code blocks: light syntax colour and a copy icon on every <pre>
  const TOK = /("(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'|(?:^|\s)#[^\n]*|\b(?:from|import|def|return|assert|curl|claude|errand|npx|pip)\b|(?:^|\s)--?[a-zA-Z][\w-]*)/gm;
  function highlight(pre) {
    pre.innerHTML = pre.textContent.split(TOK).map((t, i) => {
      if (i % 2 === 0 || !t) return esc(t);
      const lead = t.match(/^\s*/)[0], body = t.slice(lead.length);
      const cls = body[0] === '"' || body[0] === "'" ? "s" : body[0] === "#" ? "c" : body[0] === "-" ? "f" : "k";
      return esc(lead) + `<span class="${cls}">${esc(body)}</span>`;
    }).join("");
  }
  const COPY_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg>';
  const CHECK_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>';
  function decorate(pre) {
    if (pre.closest(".codebox")) return;
    highlight(pre);
    const box = document.createElement("div");
    box.className = "codebox";
    pre.replaceWith(box);
    box.appendChild(pre);
    const b = document.createElement("button");
    b.type = "button"; b.className = "cp"; b.title = "Copy"; b.setAttribute("aria-label", "Copy"); b.innerHTML = COPY_SVG;
    b.addEventListener("click", () => navigator.clipboard.writeText(pre.textContent.trim()).then(() => {
      b.innerHTML = CHECK_SVG; setTimeout(() => (b.innerHTML = COPY_SVG), 1400);
    }));
    box.appendChild(b);
  }
  $$("main pre").forEach(decorate);
  $$("[data-copy]").forEach((b) => b.addEventListener("click", () => {
    navigator.clipboard.writeText($(b.dataset.copy).textContent.trim()).then(() => toast("Copied", "ok"));
  }));

  // ---------- motion: progress line, nav, hover pill, reveals, counters (docs/UI_BRANDING.md section 5) ----------
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const nav = $(".nav"), bar = $(".progress");
  const scrollFx = [];
  function onScroll() {
    const max = document.documentElement.scrollHeight - innerHeight;
    if (bar) bar.style.transform = `scaleX(${max > 0 ? scrollY / max : 0})`;
    if (nav) nav.classList.toggle("scrolled", scrollY > 24);
    scrollFx.forEach((fn) => fn());
  }
  let ticking = false;
  addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; onScroll(); }); } }, { passive: true });
  onScroll();

  const menu = $(".menu-btn");
  if (menu) menu.addEventListener("click", () => menu.setAttribute("aria-expanded", String(nav.classList.toggle("open"))));
  const links = $(".nav .links"), pill = $(".nav .links .pill");
  if (links) $$("a", links).forEach((a) => { if (location.pathname === a.getAttribute("href")) a.classList.add("active"); });
  if (links && pill && matchMedia("(hover: hover)").matches) {
    $$("a", links).forEach((a) => a.addEventListener("mouseenter", () => {
      pill.style.width = a.offsetWidth + "px";
      pill.style.transform = `translateX(${a.offsetLeft}px)`;
      pill.style.opacity = "1";
    }));
    links.addEventListener("mouseleave", () => { pill.style.opacity = "0"; });
  }

  function countTo(el, from, to, { prefix = "", suffix = "", decimals = 0 } = {}) {
    if (!el) return;
    const fmt = (v) => prefix + Number(v).toFixed(decimals) + suffix;
    if (reduced || from === to) { el.textContent = fmt(to); return; }
    const t0 = performance.now(), dur = 900;
    const step = (t) => {
      const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = fmt(from + (to - from) * e);
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  const io = "IntersectionObserver" in window ? new IntersectionObserver((entries) => {
    entries.forEach((en) => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
  }, { rootMargin: "0px 0px -12% 0px" }) : null;
  $$(".reveal, .mark").forEach((el) => (io ? io.observe(el) : el.classList.add("in")));

  // ---------- rankings (index + leaderboard pages): plain words, no jargon ----------
  const speed = (ms) => (ms < 1000 ? "under 1 s" : `${(ms / 1000).toFixed(1)} s`);
  async function initLeaderboard() {
    const tabs = $$("#lb-tabs button"), list = $("#ranks");
    async function load(lane) {
      tabs.forEach((t) => t.classList.toggle("active", t.dataset.lane === lane));
      const rows = (await api(`/v1/leaderboard?lane=${encodeURIComponent(lane)}`)).filter((r) => r.status === "active");
      list.innerHTML = rows.map((r, i) => {
        const acc = Math.round(100 * r.pass_mean);
        const off = r.status !== "active";
        return `<li class="rank${off ? " off" : ""}" style="--i:${i}">
          <span class="pos">${i + 1}</span>
          <div class="who"><b>${esc(r.name)}</b><span>${esc(r.declared_model.replace(" (simulated)", ""))}${off ? " · paused" : ""}</span></div>
          <div class="acc"><small><b>${acc}%</b> right · ${r.verified} checked answers</small><div class="bar"><i style="--w:${acc}%"></i></div></div>
          <div class="metric">${usd(r.price_usd)}<small>per job</small></div>
          <div class="metric">${speed(r.p95_ms)}<small>speed</small></div>
          <div class="metric">${Math.round(r.rating)}<small>score</small></div>
        </li>`;
      }).join("") || `<li class="muted">No specialists here yet.</li>`;
    }
    tabs.forEach((t) => t.addEventListener("click", () => load(t.dataset.lane)));
    if (tabs.length) await load(tabs[0].dataset.lane);
  }

  // ---------- landing: hero card plays a few real-looking errands on a loop ----------
  const DEMO = [
    { task: "What is 17 × 23?", check: "391", steps: [
      ["Finding the best specialist", "Matched <b>Duke</b>", "math · $0.0009"],
      ["Holding payment in escrow", "Payment held", "$0.0009", "hold"],
      ["Checking the answer", "<b>391</b> matches the check", "verified"],
      ["Releasing payment", "Paid Duke", "via PayPal wallet"]],
      paid: "$0.0009", frontier: "$0.012", saved: "92%" },
    { task: "Write is_palindrome(s), ignore case", check: "3 asserts", steps: [
      ["Finding the best specialist", "Matched <b>Ada</b>", "code · $0.0016"],
      ["Holding payment in escrow", "Payment held", "$0.0016", "hold"],
      ["Running your tests", "<b>3 of 3</b> tests passed", "verified"],
      ["Releasing payment", "Paid Ada", "via PayPal wallet"]],
      paid: "$0.0016", frontier: "$0.020", saved: "92%" },
    { task: "A train goes 216 km in 12 h. Speed in km/h?", check: "18", steps: [
      ["Finding the best specialist", "Matched <b>Atlas</b>", "math · $0.0046"],
      ["Checking the answer", "Atlas said <b>16</b>, wrong", "not charged", "bad"],
      ["Trying the next specialist", "Matched <b>Duke</b>", "math · $0.0009"],
      ["Checking the answer", "<b>18</b> matches the check", "verified"],
      ["Releasing payment", "Paid Duke only", "via PayPal wallet"]],
      paid: "$0.0009", frontier: "$0.012", saved: "92%" },
  ];
  function initDemo() {
    const card = $("#live-demo");
    if (!card) return;
    const taskEl = $(".dc-task", card), list = $(".dc-steps", card), rc = $(".dc-receipt", card);
    const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    const call = (d, n) => {
      const rest = n > d.task.length ? `, check=<q>${esc(d.check)}</q>` : "";
      return `<q>${esc(d.task.slice(0, n))}</q>${rest}`;
    };
    const fill = (d) => {
      $(".dc-paid", card).textContent = d.paid; $(".dc-frontier", card).textContent = d.frontier; $(".dc-saved", card).textContent = d.saved;
    };
    const finalState = (d) => {
      taskEl.innerHTML = call(d, 999);
      list.innerHTML = d.steps.map(([, done, meta, kind]) => `<li class="${kind || "ok"}"><span class="dc-ic"></span><span>${done}</span><small>${meta}</small></li>`).join("");
      fill(d); rc.classList.add("show");
    };
    if (reduced) return finalState(DEMO[0]);
    (async () => {
      for (let i = 0; ; i = (i + 1) % DEMO.length) {
        const d = DEMO[i];
        list.innerHTML = ""; rc.classList.remove("show"); fill(d);
        for (let n = 0; n <= d.task.length; n++) { taskEl.innerHTML = call(d, n); await sleep(28); }
        await sleep(350); taskEl.innerHTML = call(d, 999); await sleep(500);
        for (const [pending, done, meta, kind] of d.steps) {
          const li = document.createElement("li");
          li.className = "run";
          li.innerHTML = `<span class="dc-ic"></span><span>${pending}</span><small></small>`;
          list.appendChild(li);
          await sleep(kind === "hold" ? 650 : 1000);
          li.className = kind || "ok";
          li.innerHTML = `<span class="dc-ic"></span><span>${done}</span><small>${meta}</small>`;
          await sleep(300);
        }
        rc.classList.add("show");
        await sleep(3600);
        while (document.hidden) await sleep(500);
      }
    })();
  }

  // ---------- landing ----------
  async function initIndex() {
    initDemo();
    // the How-it-works line draws itself as you scroll, lighting each step it reaches
    const howto = $(".howto"), trail = $(".howto .trail path"), steps = $$(".howto .step");
    if (howto && trail) scrollFx.push(() => {
      const r = howto.getBoundingClientRect();
      const k = Math.max(0, Math.min(1, (innerHeight * 0.85 - r.top) / (r.height + innerHeight * 0.25)));
      trail.style.strokeDashoffset = String(1 - k);
      steps.forEach((s, i) => s.classList.toggle("lit", k >= (i + 0.5) / steps.length));
    });
    onScroll();

    // benchmark numbers count up the first time they scroll into view
    $$("[data-to]").forEach((el) => {
      const go = () => countTo(el, 0, Number(el.dataset.to),
        { prefix: el.dataset.prefix || "", suffix: el.dataset.suffix || "", decimals: Number(el.dataset.decimals || 0) });
      if (!io) return go();
      const o = new IntersectionObserver((en) => { if (en[0].isIntersecting) { go(); o.disconnect(); } });
      o.observe(el);
    });

    const st = await api("/v1/stats");
    const track = $("#receipts-track");
    if (track && st.recent.length) {
      const html = st.recent.map((r) => `<div class="mini-receipt">
        <div class="r"><span class="lane">${r.lane.startsWith("math") ? "Math" : "Code"}</span><span class="ok">${r.verdict === "passed" ? "✓ checked" : esc(r.verdict)}</span></div>
        <div class="q">${esc(r.task || "")}</div>
        <div class="a">→ ${esc(r.lane.startsWith("math") ? r.answer : "tests passed")}</div>
        <div class="r"><span>${esc(r.runner)} · <b>${money(r.total_usd)}</b></span><span><s>${money(r.baseline_usd)}</s></span></div></div>`).join("");
      track.innerHTML = html + html;
      if (!reduced) track.animate([{ transform: "translateX(0)" }, { transform: "translateX(-50%)" }],
        { duration: 4000 * st.recent.length, iterations: Infinity });
    } else if (track) track.parentElement.hidden = true;
    await initLeaderboard();
  }

  // ---------- sender ----------
  async function initSender() {
    let demoTasks = null, exampleTurn = 0, savedShown = 0;

    async function refresh() {
      const me = await api("/v1/me");
      const b = me.balances, a = me.activity;
      $("#k-wallet").textContent = usd(b.wallet || 0, 2);
      $("#k-spent").textContent = `${money(a.spend_30d_usd)} spent`;
      $("#k-errands").textContent = a.errands_30d;
      countTo($("#k-saved"), savedShown, a.saved_30d_usd, { prefix: "$", decimals: a.saved_30d_usd >= 1 ? 2 : 3 });
      savedShown = a.saved_30d_usd;
      $("#k-tier").textContent = me.tier.name;
      $("#k-tier-next").textContent = me.tier.next ? `${usd(me.tier.next.spend_needed_usd, 2)} more to ${me.tier.next.name}` : "top tier";
      const acc = me.account;
      $("#cap1").value = (acc.cap_per_errand / 1e6).toString();
      $("#capd").value = (acc.cap_daily / 1e6).toString();
      $("#defpreset").value = acc.preset;
      $("#consent").value = String(acc.consent_level);
      const errands = await api("/v1/errands");
      grid("#errands-grid", [
        { headerName: "Task", flex: 3, minWidth: 260, valueGetter: (p) => taskText(p.data), cellClass: "cell-task",
          cellRenderer: (p) => `<div class="t">${esc(p.value)}</div><div class="l">${p.data.lane.startsWith("math") ? "Math" : "Code"}${p.data.kind === "bounty" ? " · PayPal bounty" : ""}</div>` },
        { field: "answer", headerName: "Answer", flex: 1, minWidth: 90, cellClass: "mono",
          valueGetter: (p) => (p.data.lane.startsWith("code") && p.data.status === "completed" ? "tests passed" : p.data.answer) },
        { headerName: "Specialist", flex: 1, minWidth: 100, valueGetter: (p) => p.data.runner && p.data.runner.name },
        { headerName: "Result", flex: 1, minWidth: 110, valueGetter: (p) => resultOf(p.data),
          cellRenderer: (p) => badge(p.value, { verified: "ok", delivered: "plain", refunded: "bad", running: "warn" }[p.value]) },
        { field: "total_usd", headerName: "Cost", flex: 1, minWidth: 90, valueFormatter: (p) => money(p.value), cellClass: "mono" },
        { field: "saved_usd", headerName: "Saved", flex: 1, minWidth: 90, valueFormatter: (p) => (p.value ? money(p.value) : ""), cellClass: "mono saved" },
        { field: "created_at", headerName: "When", flex: 1, minWidth: 90, valueFormatter: (p) => ago(p.value), cellClass: "muted" },
        { headerName: "", flex: 1, minWidth: 120, sortable: false, filter: false, cellRenderer: (p) => {
          if (p.data.status !== "completed") return "";
          if (p.data.feedback) return `<span class="muted small">${p.data.feedback > 0 ? "accepted" : "disputed"}</span>`;
          return `<a href="#" data-fb="1" data-id="${p.data.id}">accept</a> · <a href="#" data-fb="0" data-id="${p.data.id}">dispute</a>`;
        } },
      ], errands, { rowHeight: 58, defaultColDef: { sortable: true, filter: false, resizable: true } });
      grid("#ops-grid", opsCols, await api("/v1/paypal/ops"));
    }

    async function loadRunners() {
      const sel = $("#runner");
      for (const r of await api("/v1/runners")) {
        const o = document.createElement("option");
        o.value = r.name;
        const prices = Object.entries(r.lanes).map(([l, v]) => `${l.split(".")[0]} ${usd(v)}`).join(", ");
        o.textContent = `${r.name} · ${prices}`;
        sel.appendChild(o);
      }
    }

    function body() {
      const b = { task: $("#task").value };
      if ($("#check").value.trim()) b.check = $("#check").value.trim();
      if ($("#runner").value) b.runner = $("#runner").value;
      if ($("#budget").value) b.budget_usd = Number($("#budget").value);
      return b;
    }

    function showPending() {
      $("#result").innerHTML = `<div class="head"><span class="badge live">running</span>
        <span class="escrow" title="Your payment is held until the result verifies">held in escrow</span></div>`;
    }

    function renderResult(e) {
      const ok = e.status === "completed";
      const stamp = !ok ? ["failed", "bad"] : e.verdict === "passed" ? ["verified", ""] : ["delivered", "delivered"];
      const answer = e.lane === "code.python.tests" ? "Function written, tests passed" : (e.answer ?? "");
      $("#result").innerHTML = `
        <div class="head">${statusBadge(e.status)}
          ${ok ? `<span class="escrow">held in escrow</span>` : `<span class="badge plain">refunded, not charged</span>`}
          ${e.runner ? `<span class="small">by <b>${esc(e.runner.name)}</b> <span class="muted mono">${esc(e.runner.model)}</span></span>` : ""}</div>
        <div class="receipt-wrap printing">
          <span class="stamp ${stamp[1]}">${stamp[0]}</span>
          <div class="receipt">
            ${ok ? `<div class="answer">${esc(answer)}</div>
            <div class="line"><span>Lane</span><span>${esc(e.lane)}</span></div>
            <div class="line"><span>Runner price</span><span>${usd(e.price_usd, 6)}</span></div>
            <div class="line"><span>Errand fee (your half)</span><span>${usd(e.fee_usd, 6)}</span></div>
            ${e.dividend_usd ? `<div class="line"><span>Data dividend</span><span>-${usd(e.dividend_usd, 6)}</span></div>` : ""}
            <div class="line total"><span>You paid</span><span>${usd(e.total_usd, 6)}</span></div>
            <div class="line"><span>Frontier estimate</span><span>${usd(e.baseline_usd, 6)}</span></div>
            <div class="line"><span>Latency · attempts · policy</span><span>${e.latency_ms} ms · ${e.attempts} · ${esc(e.policy)}</span></div>
            <div class="line"><span>Errand</span><span>${esc(e.id)}</span></div>`
            : `<div class="answer">No charge</div><p class="muted" style="margin:0">${esc(e.detail || "")}</p>`}
          </div>
        </div>
        ${ok ? `<p class="small muted">${esc(e.detail || "")}</p><details><summary class="small">Full output</summary><pre>${esc(e.output)}</pre></details>` : ""}`;
      const chip = $("#result .escrow");
      if (chip) setTimeout(() => { chip.classList.add("released"); chip.textContent = "released to Runner"; }, 700);
    }

    $("#example-btn").addEventListener("click", async () => {
      demoTasks = demoTasks || (await api("/v1/demo/tasks"));
      const code = exampleTurn++ % 2 === 1;
      const list = demoTasks[code ? "code.python.tests" : "math.final-answer"];
      const t = list[Math.floor(Math.random() * list.length)];
      $("#task").value = code ? `${t.spec} Name the function ${t.function_name}.` : t.problem;
      $("#check").value = code ? t.tests : t.expected;
      $("#task").focus();
    });
    $("#errand-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      withBusy($("#send-btn"), async () => {
        showPending();
        try {
          renderResult(await api("/v1/delegate", { method: "POST", body: body() }));
        } catch (e) { $("#result").innerHTML = ""; throw e; }
        await refresh();
      });
    });
    $("#bounty-btn").addEventListener("click", () => withBusy($("#bounty-btn"), async () => {
      const amt = prompt("Bounty amount in USD (charged through PayPal only if the work is verified):", "2");
      if (!amt) return;
      const b = body();
      const r = await api("/v1/bounties", { method: "POST", body: { task: b.task, check: b.check, amount_usd: Number(amt) } });
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
    await Promise.all([refresh(), loadRunners()]);
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
        toast("Saved. The onboarding exam has started.", "ok");
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

  const inits = { connect: initConnect, index: initIndex, leaderboard: initLeaderboard, sender: initSender, runner: initRunner, platform: initPlatform };
  if (inits[page]) inits[page]().catch((e) => toast(e.message, "bad"));
})();
