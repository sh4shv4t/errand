"""Record the Errand demo video (final cut).

Starts a fresh, pre-populated Errand instance, drives it in Chrome with a visible cursor and eased
scrolling, and records the screen. Alongside the video it writes timeline.json: when to zoom (and on
what), which sound effect to play, and which caption to show. demo/edit.py turns both into the cut.

    demo/.venv/Scripts/python demo/record.py
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "out"
ERRAND = ROOT / ".venv" / "Scripts" / ("errand.exe" if os.name == "nt" else "errand")
PORT = 8002
BASE = f"http://localhost:{PORT}"
W, H = 1920, 1080

CURSOR_JS = """
window.addEventListener('DOMContentLoaded', () => {
  const c = document.createElement('div');
  c.id = '__cursor';
  c.style.cssText = 'position:fixed;left:0;top:0;width:26px;height:26px;z-index:2147483647;pointer-events:none;' +
    'transform:translate(-100px,-100px);transition:transform 40ms linear;' +
    'background:url("data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 24 24%27%3E%3Cpath d=%27M4 2l16 9.5-7 1.6-3.6 6.9z%27 fill=%27%230b2a21%27 stroke=%27white%27 stroke-width=%271.6%27 stroke-linejoin=%27round%27/%3E%3C/svg%3E") no-repeat;';
  document.body.appendChild(c);
  const last = JSON.parse(sessionStorage.getItem('__cursor') || '[-100,-100]');
  c.style.transform = `translate(${last[0]}px,${last[1]}px)`;
  document.addEventListener('mousemove', (e) => {
    c.style.transform = `translate(${e.clientX}px,${e.clientY}px)`;
    sessionStorage.setItem('__cursor', JSON.stringify([e.clientX, e.clientY]));
  });
  document.addEventListener('mousedown', (e) => {
    const r = document.createElement('div');
    r.style.cssText = `position:fixed;left:${e.clientX - 22}px;top:${e.clientY - 22}px;width:44px;height:44px;border-radius:50%;` +
      'border:3px solid #fd550a;z-index:2147483646;pointer-events:none;transition:transform 450ms ease-out,opacity 450ms ease-out;';
    document.body.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.8)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 500);
  });
});
"""

TITLE_HTML = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500&family=Geist+Mono&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#f4f0e6;color:#0b2a21;font-family:Geist,sans-serif;overflow:hidden}
  .wrap{height:100%;display:grid;place-items:center;text-align:center}
  h1{font-size:150px;font-weight:500;letter-spacing:-0.04em;margin:0;line-height:1}
  h1 em{font-family:'Instrument Serif',serif;font-weight:400;color:#015d47}
  p{font-size:40px;color:#4f6b61;margin:28px 0 0}
  .tag{font-family:'Geist Mono',monospace;font-size:22px;letter-spacing:.12em;color:#b83f0a;margin-bottom:34px}
  .dot{display:inline-block;width:20px;height:20px;border-radius:50%;background:#fd550a;margin-left:6px;vertical-align:8px}
  .rise{animation:rise .9s cubic-bezier(.32,.72,0,1) both}
  .d1{animation-delay:.15s}.d2{animation-delay:.45s}
  @keyframes rise{from{opacity:0;transform:translateY(40px)}}
</style></head><body><div class="wrap"><div>
  <div class="tag rise">%TAG%</div>
  <h1 class="rise d1">%TITLE%</h1>
  <p class="rise d2">%SUB%</p>
</div></div></body></html>"""


class Timeline:
    def __init__(self):
        self.t0 = time.monotonic()
        self.events: list[dict] = []

    def now(self) -> float:
        return round(time.monotonic() - self.t0, 3)

    def add(self, kind: str, **kw) -> None:
        self.events.append({"t": self.now(), "kind": kind, **kw})

    def zoom(self, page, selector: str, scale: float = 1.6, pad: int = 40, nth: int = 0) -> None:
        box = page.locator(selector).nth(nth).bounding_box()
        if box:
            self.add("zoom", box=[box["x"] - pad, box["y"] - pad, box["width"] + 2 * pad, box["height"] + 2 * pad], scale=scale)

    def unzoom(self) -> None:
        self.add("zoom", box=None, scale=1.0)


def start_server() -> subprocess.Popen:
    OUT.mkdir(parents=True, exist_ok=True)
    db = OUT / "errand.db"
    for p in OUT.glob("errand.db*"):
        p.unlink()
    (OUT / "demo_keys.json").unlink(missing_ok=True)
    env = os.environ | {"ERRAND_DB": str(db), "ERRAND_BASE_URL": BASE, "ERRAND_DEMO": "1", "PYTHONIOENCODING": "utf-8",
                         "ERRAND_OLLAMA_MODELS": "qwen2.5-coder:1.5b,qwen2.5:1.5b,phi3:mini"}
    # seed (local Ollama models become real Runners), populate history so receipts and rankings are real,
    # then serve with visible but short latency
    subprocess.run([str(ERRAND), "seed"], env=env, cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(ERRAND), "demo", "-n", "30", "--speed", "0", "--seed", "11"], env=env, cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)
    env["ERRAND_SIM_LATENCY_SCALE"] = "0.8"
    proc = subprocess.Popen([str(ERRAND), "serve", "--port", str(PORT)], env=env, cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    import urllib.request
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/v1/config", timeout=1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    sys.exit("Errand did not start")


def ease_scroll(page, y: int, ms: int = 1400) -> None:
    page.evaluate("""([y, ms]) => new Promise((done) => {
      document.documentElement.style.scrollBehavior = 'auto';
      const y0 = scrollY, t0 = performance.now();
      const ease = (k) => k < .5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
      const step = (t) => { const k = Math.min(1, (t - t0) / ms); scrollTo(0, y0 + (y - y0) * ease(k)); k < 1 ? requestAnimationFrame(step) : done(); };
      requestAnimationFrame(step);
    })""", [y, ms])


def scroll_to(page, selector: str, offset: int = 120, ms: int = 1400) -> None:
    y = page.evaluate("([s, o]) => document.querySelector(s).getBoundingClientRect().top + scrollY - o", [selector, offset])
    ease_scroll(page, max(0, int(y)), ms)


def glide(page, selector: str, nth: int = 0, steps: int = 28) -> None:
    box = page.locator(selector).nth(nth).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=steps)


def click(page, tl: Timeline, selector: str, nth: int = 0) -> None:
    glide(page, selector, nth)
    page.wait_for_timeout(180)
    tl.add("sfx", name="click")
    page.locator(selector).nth(nth).click()


def title_card(page, tl: Timeline, tag: str, title: str, sub: str, hold: int = 2600) -> None:
    page.set_content(TITLE_HTML.replace("%TAG%", tag).replace("%TITLE%", title).replace("%SUB%", sub))
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(hold)


PROBLEM_HTML = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#f4f0e6;color:#0b2a21;font-family:Geist,sans-serif;overflow:hidden}
  .stage{height:100%;display:grid;grid-template-columns:640px 1fr;gap:70px;padding:80px 120px 210px;box-sizing:border-box}
  .eyebrow{font:500 20px 'Geist Mono',monospace;letter-spacing:.14em;color:#b83f0a}
  .ask{margin-top:26px;background:#0b1f19;color:#f4f0e6;border-radius:18px;padding:28px 32px;font:500 34px/1.35 Geist,sans-serif;
       box-shadow:0 30px 60px -30px rgba(11,42,33,.45);min-height:92px}
  .ask .who{display:block;font:500 18px 'Geist Mono',monospace;color:#7fd1b0;margin-bottom:10px;letter-spacing:.06em}
  .bill{margin-top:56px}
  .bill .lbl{font:500 20px 'Geist Mono',monospace;letter-spacing:.12em;color:#4f6b61}
  .bill .num{font:500 120px/1 'Geist Mono',monospace;letter-spacing:-.04em;margin-top:12px;transition:color .6s}
  .bill .num.old{color:#9aa79f;text-decoration:line-through;text-decoration-thickness:6px;font-size:64px}
  .bill .new{font:500 120px/1 'Geist Mono',monospace;letter-spacing:-.04em;color:#015d47;margin-top:8px;opacity:0;transform:translateY(20px);
       transition:all .8s cubic-bezier(.32,.72,0,1)}
  .bill .new.on{opacity:1;transform:none}
  .bill .new small{display:block;font:500 20px 'Geist Mono',monospace;letter-spacing:.12em;color:#015d47;margin-bottom:10px}
  .calls{display:flex;flex-direction:column;gap:12px;align-self:center}
  .call{display:grid;grid-template-columns:44px 1fr auto auto;align-items:center;gap:18px;background:#fbf9f4;border:1.5px solid rgba(11,42,33,.1);
        border-radius:14px;padding:11px 22px;font-size:23px;opacity:0;transform:translateX(40px);transition:all .55s cubic-bezier(.32,.72,0,1)}
  .call.on{opacity:1;transform:none}
  .call .i{font:500 18px 'Geist Mono',monospace;color:#9aa79f}
  .call .tag{font:500 15px 'Geist Mono',monospace;letter-spacing:.05em;padding:6px 12px;border-radius:99px;opacity:0;transition:opacity .4s}
  .call .tag.on{opacity:1}
  .call.easy .tag{background:#e0f354;color:#0b2a21}
  .call.hard .tag{background:#0b2a21;color:#f4f0e6}
  .call .p{font:500 22px 'Geist Mono',monospace;min-width:130px;text-align:right}
  .call .p s{color:#9aa79f;margin-right:10px;font-size:18px}
  .call .p b{color:#015d47;font-weight:500}
  .call.easy.cheap{border-color:rgba(1,93,71,.35)}
</style></head><body><div class="stage">
  <div>
    <div class="eyebrow">ONE ORDINARY AGENT TASK</div>
    <div class="ask"><span class="who">you › coding agent</span><span id="ask"></span></div>
    <div class="bill"><div class="lbl" id="billlbl">MODEL BILL, ALL ON A FRONTIER MODEL</div><div class="num" id="bill">$0.000</div>
      <div class="new" id="new"><small>WITH ERRAND</small><span id="newv">$0.000</span></div></div>
  </div>
  <div class="calls" id="calls"></div>
</div>
<script>
const ASK = "Add CSV export to the billing page.";
const CALLS = [
  ["Plan the change across 4 files", 0.034, 0],
  ["Parse ISO dates in invoice rows", 0.011, 1],
  ["Format money to 2 decimal places", 0.009, 1],
  ["Regex for invoice IDs like INV-2041", 0.010, 1],
  ["Sum line items with 18% tax", 0.012, 1],
  ["Slugify the export file name", 0.009, 1],
  ["Convert cents to dollars", 0.008, 1],
  ["Write tests for the CSV writer", 0.013, 1],
  ["Escape commas and quotes in fields", 0.010, 1],
  ["Review the final diff", 0.031, 0],
];
const SMALL = 0.0009;
const $ = (s) => document.querySelector(s);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const fmt = (v) => "$" + v.toFixed(3);
function countTo(el, from, to, ms) {
  const t0 = performance.now();
  const step = (t) => { const k = Math.min(1, (t - t0) / ms); el.textContent = fmt(from + (to - from) * (1 - Math.pow(1 - k, 3))); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
window.play = async () => {
  for (let i = 0; i <= ASK.length; i++) { $("#ask").textContent = ASK.slice(0, i); await sleep(45); }
  await sleep(500);
  let bill = 0;
  for (const [i, [label, price, easy]] of CALLS.entries()) {
    const d = document.createElement("div");
    d.className = "call " + (easy ? "easy" : "hard");
    d.innerHTML = `<span class="i">${String(i + 1).padStart(2, "0")}</span><span>${label}</span><span class="tag">${easy ? "a small model can do this" : "needs the big model"}</span><span class="p">${fmt(price)}</span>`;
    $("#calls").appendChild(d);
    requestAnimationFrame(() => d.classList.add("on"));
    countTo($("#bill"), bill, bill + price, 450);
    bill += price;
    await sleep(620);
  }
  await sleep(1700);
  for (const d of document.querySelectorAll(".call")) { d.querySelector(".tag").classList.add("on"); await sleep(230); }
  await sleep(3200);
  let after = 0;
  for (const [i, [label, price, easy]] of CALLS.entries()) after += easy ? SMALL : price;
  for (const [i, d] of [...document.querySelectorAll(".call")].entries()) {
    if (!d.classList.contains("easy")) continue;
    d.classList.add("cheap");
    d.querySelector(".p").innerHTML = `<s>${fmt(CALLS[i][1])}</s><b>$${SMALL.toFixed(4)}</b>`;
    await sleep(170);
  }
  await sleep(400);
  $("#bill").classList.add("old");
  $("#new").classList.add("on");
  countTo($("#newv"), 0, after, 900);
};
</script></body></html>"""


AGENT_HTML = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#f4f0e6;font-family:Geist,sans-serif;overflow:hidden}
  .stage{height:100%;display:grid;grid-template-columns:1.25fr 1fr;gap:28px;padding:60px 80px 190px;box-sizing:border-box}
  .win{background:#0b1f19;border-radius:18px;box-shadow:0 40px 80px -30px rgba(11,42,33,.45);display:flex;flex-direction:column;overflow:hidden}
  .bar{height:50px;display:flex;align-items:center;gap:10px;padding:0 22px;background:#12291f;color:#9db3aa;font:500 16px 'Geist Mono',monospace}
  .bar i{width:13px;height:13px;border-radius:50%;background:#2c4a3f;display:inline-block}
  .bar span{margin-left:12px}
  .bar b{margin-left:auto;font-weight:500;color:#0b2a21;background:#e0f354;border-radius:99px;padding:3px 12px;font-size:13px}
  #log{flex:1;padding:26px 30px;font:21px/1.7 'Geist Mono',monospace;color:#f4f0e6;overflow:hidden}
  .ln{white-space:pre-wrap;word-break:break-word;animation:in .35s ease-out both;margin-bottom:6px}
  @keyframes in{from{opacity:0;transform:translateY(6px)}}
  .p{color:#7fd1b0}.dim{color:#9db3aa}.tool{color:#e0f354}.ok{color:#7fd1b0}.err{color:#f19a8c}.file{color:#f4f0e6}.agent{color:#f4f0e6}
  .cur{display:inline-block;width:11px;height:24px;background:#f4f0e6;vertical-align:-5px;animation:b 1s steps(1) infinite}
  @keyframes b{50%{opacity:0}}
  .spin{display:inline-block;width:16px;height:16px;border:2.5px solid #2c4a3f;border-top-color:#e0f354;border-radius:50%;vertical-align:-2px;margin-right:10px;animation:r .8s linear infinite}
  @keyframes r{to{transform:rotate(360deg)}}
  .code{background:#fbf9f4;border:1.5px solid rgba(11,42,33,.14);border-radius:18px;overflow:hidden;display:flex;flex-direction:column}
  .code .bar{background:#e9e3d4;color:#4f6b61}.code .bar i{background:#cfc6b2}
  pre{margin:0;padding:22px 28px;font:19px/1.6 'Geist Mono',monospace;color:#0b2a21;white-space:pre-wrap}
  pre .ln2{display:block;animation:in .3s ease-out both}
  .empty{color:#9aa79f}
</style></head><body><div class="stage">
  <div class="win"><div class="bar"><i></i><i></i><i></i><span>~/my-app · coding agent (qwen2.5 7B, local) + Errand</span><b>real run</b></div>
    <div id="log"></div></div>
  <div class="code"><div class="bar"><i></i><i></i><i></i><span>text_utils.py</span></div><pre id="code"><span class="empty"># empty</span></pre></div>
</div>
<script>
  const log = document.getElementById('log');
  window.addLine = (cls, text) => { const d = document.createElement('div'); d.className = 'ln ' + cls; d.textContent = text; log.appendChild(d); return d; };
  window.spin = (text) => { const d = document.createElement('div'); d.className = 'ln dim'; d.id = 'spin'; d.innerHTML = '<span class="spin"></span>' + text; log.appendChild(d); };
  window.unspin = () => { const s = document.getElementById('spin'); if (s) s.remove(); };
  window.typeLine = (prefix, text, ms) => new Promise((done) => {
    const d = document.createElement('div'); d.className = 'ln'; d.innerHTML = '<span class="p">' + prefix + '</span><span class="t"></span><span class="cur"></span>';
    log.appendChild(d); const t = d.querySelector('.t'); let i = 0;
    const tick = () => { t.textContent = text.slice(0, ++i); i < text.length ? setTimeout(tick, ms) : (d.querySelector('.cur').remove(), done()); };
    tick();
  });
  window.showCode = (code) => new Promise((done) => {
    const pre = document.getElementById('code'); pre.innerHTML = '';
    const lines = code.split('\\n'); let i = 0;
    const step = () => { if (i >= lines.length) return done(); const s = document.createElement('span'); s.className = 'ln2'; s.textContent = lines[i++] || ' '; pre.appendChild(s); setTimeout(step, 120); };
    step();
  });
</script></body></html>"""


END_HTML = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#0b2a21;color:#f4f0e6;font-family:Geist,sans-serif;overflow:hidden}
  .wrap{height:100%;display:grid;place-items:center;text-align:center}
  .glow{position:absolute;inset:0;background:radial-gradient(600px 400px at 30% 30%,rgba(224,243,84,.10),transparent),radial-gradient(700px 500px at 75% 75%,rgba(253,85,10,.12),transparent)}
  img{width:96px;height:96px;border-radius:22px}
  h1{font-size:120px;font-weight:500;letter-spacing:-.04em;margin:18px 0 0;line-height:1}
  h1 em{font-family:'Instrument Serif',serif;font-weight:400;color:#e0f354}
  .links{margin-top:46px;display:grid;gap:14px;font:500 32px 'Geist Mono',monospace}
  .links span{color:#9db3aa;font-size:22px;letter-spacing:.12em;margin-right:18px}
  .fund{display:inline-block;margin-top:44px;background:#fd550a;color:#0b2a21;font:600 30px Geist,sans-serif;padding:16px 32px;border-radius:99px}
  .contact{margin-top:26px;font:500 24px 'Geist Mono',monospace;color:#c9d6d0}
  .foot{margin-top:40px;font:500 18px 'Geist Mono',monospace;letter-spacing:.14em;color:#7d948b}
  .rise{animation:rise .9s cubic-bezier(.32,.72,0,1) both}
  @keyframes rise{from{opacity:0;transform:translateY(34px)}}
</style></head><body><div class="glow"></div><div class="wrap"><div style="position:relative">
  <img class="rise" src="%ICON%" alt="">
  <h1 class="rise" style="animation-delay:.15s">Send your model on <em>fewer</em> errands.</h1>
  <div class="links">
    <div class="rise" style="animation-delay:.6s"><span>TRY IT</span>errand-pt6h.onrender.com</div>
    <div class="rise" style="animation-delay:.8s"><span>CODE</span>github.com/sh4shv4t/errand</div>
  </div>
  <div class="fund rise" style="animation-delay:1.4s">Open to funding and collaborators</div>
  <div class="contact rise" style="animation-delay:1.7s">x.com/shashvatsingh05 · shashvat.k.singh.16@gmail.com</div>
  <div class="foot rise" style="animation-delay:2.1s">BUILT FOR THE PAYPAL AI HACKATHON 2026</div>
</div></div></body></html>"""


LIVE = "https://errand-pt6h.onrender.com"
AGENT_TASK = ("In text_utils.py, add is_palindrome(s) that ignores case and spaces, "
              "and word_count(s) that returns how many words s has.")


def cut(tl: Timeline) -> None:
    """Mark a scene change: the edit drops what follows until cutin() and cross-fades into the next scene."""
    tl.add("zoom", box=None, scale=1.0, snap=True)
    tl.add("cut")


def cutin(page, tl: Timeline, settle: int = 500) -> None:
    page.wait_for_timeout(settle)
    tl.add("cutin")


def demo_login(page, base: str, account: str) -> None:
    page.goto(base + "/login")
    page.evaluate("(a) => { const f = document.createElement('form'); f.method = 'post'; f.action = '/login/demo/' + a; document.body.appendChild(f); f.submit(); }", account)
    page.wait_for_url("**/dashboard*")
    page.wait_for_load_state("networkidle")


def prerun_agent(base: str) -> tuple[list[tuple[str, str]], str]:
    """Run the real coding agent once, off camera, and keep exactly what it printed and wrote."""
    key = json.loads((OUT / "demo_keys.json").read_text(encoding="utf-8"))["senders"]["snd_alan"]["api_key"]
    project = OUT / "video-app"  # the recorder's own scratch project
    env = os.environ | {"ERRAND_URL": base, "ERRAND_API_KEY": key, "LLM_MODEL": "qwen2.5:7b", "PYTHONIOENCODING": "utf-8",
                        "AGENT_BUDGET_USD": "0.001", "AGENT_PROJECT": str(project)}
    for attempt in range(4):
        shutil.rmtree(project, ignore_errors=True)
        project.mkdir(parents=True)
        out = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "demo" / "coding_agent.py"), AGENT_TASK],
                             env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8").stdout
        lines = [tuple(l.split("|", 1)) for l in out.splitlines() if "|" in l]
        code_file = project / "text_utils.py"
        if sum(k == "ok" for k, _ in lines) >= 2 and code_file.exists():
            (OUT / "agent-run.log").write_text(out, encoding="utf-8")
            return lines, code_file.read_text(encoding="utf-8").strip()
        print(f"agent attempt {attempt + 1} did not finish two verified errands; retrying")
    sys.exit("the coding agent did not complete two verified errands")


def agent_scene(page, tl: Timeline, lines: list[tuple[str, str]], code: str) -> None:
    """Replay the real run at a readable pace: every line shown is one the agent actually printed."""
    page.set_content(AGENT_HTML)
    page.wait_for_load_state("networkidle")
    page.mouse.move(W - 40, H - 40)
    cutin(page, tl, 300)
    tl.add("caption", text="A real coding agent, with one new tool: Errand.", dur=3.4)
    page.wait_for_timeout(900)
    page.evaluate("([p, t]) => typeLine(p, t, 24)", ["you › ", AGENT_TASK])
    page.wait_for_timeout(24 * len(AGENT_TASK) + 700)
    oks = 0
    for kind, text in lines:
        if kind == "user":
            continue
        if kind == "tool":
            page.evaluate("() => spin('agent › planning')")
            page.wait_for_timeout(1500)
            page.evaluate("() => unspin()")
            page.evaluate("([t]) => addLine('tool', '⚙ ' + t)", [text])
            tl.add("sfx", name="click")
            if oks == 0:
                tl.add("caption", text="It hands each function, with its tests, to a cheaper specialist.", dur=3.6)
            page.wait_for_timeout(1300)
            page.evaluate("() => spin('errand › matching a specialist, then running the tests')")
            page.wait_for_timeout(2300)
            page.evaluate("() => unspin()")
        elif kind == "ok":
            page.evaluate("([t]) => addLine('ok', '✓ ' + t)", [text])
            tl.add("sfx", name="ding")
            oks += 1
            tl.add("caption", text=("Errand runs the tests. Only passing code gets paid." if oks == 1 else
                                    "A different specialist this time. Each job cost a fraction of a cent."), dur=3.8)
            tl.zoom(page, "#log .ln.ok", scale=1.35, pad=40, nth=oks - 1)
            page.wait_for_timeout(3800)
            tl.unzoom()
            page.wait_for_timeout(500)
        elif kind == "err":
            page.evaluate("([t]) => addLine('err', '✗ ' + t)", [text])
            page.wait_for_timeout(1500)
        elif kind == "file":
            page.evaluate("([t]) => addLine('file', '✎ ' + t)", [text])
            page.wait_for_timeout(500)
        elif kind == "agent":
            page.evaluate("([c]) => showCode(c)", [code])
            page.wait_for_timeout(120 * (code.count("\n") + 1) + 600)
            page.evaluate("([t]) => addLine('agent', 'agent › ' + t)", [text])
            tl.add("caption", text="Verified code lands in your project.", dur=3.2)
            tl.zoom(page, ".code", scale=1.3, pad=20)
            page.wait_for_timeout(3600)
            tl.unzoom()
    page.wait_for_timeout(900)


def live_runner_with_earnings() -> str | None:
    """Pick a demo Runner on the live site that has at least a cent to withdraw."""
    import http.cookiejar
    import urllib.request
    best = (0.0, None)
    for rid in ("run_atlas", "run_mercer", "run_duke", "run_grace", "run_kepler", "run_ada", "run_lin"):
        try:
            op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            op.open(urllib.request.Request(f"{LIVE}/login/demo/{rid}", data=b"", method="POST"), timeout=90).read()
            earn = json.loads(op.open(f"{LIVE}/v1/me", timeout=60).read())["balances"].get("earnings", 0)
        except Exception:
            continue
        if earn > best[0]:
            best = (earn, rid)
    return best[1] if best[0] >= 0.0101 else None


def main() -> None:
    server = start_server()
    try:
        # off camera: a refunded custom question, then the real agent run, so both show up on the dashboard
        key = json.loads((OUT / "demo_keys.json").read_text(encoding="utf-8"))["senders"]["snd_alan"]["api_key"]
        import urllib.request
        urllib.request.urlopen(urllib.request.Request(
            BASE + "/v1/delegate", method="POST", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            data=json.dumps({"task": "How tall is Mount Everest in metres?", "check": "8849"}).encode()), timeout=120).read()
        lines, code = prerun_agent(BASE)
        live_runner = live_runner_with_earnings()
        print("live runner for the payout:", live_runner)
        icon = "data:image/png;base64," + base64.b64encode((ROOT / "assets" / "errand-icon.png").read_bytes()).decode()

        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=False, args=["--hide-scrollbars"])
            ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light",
                                      record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H})
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            tl = Timeline()

            # 1. title
            title_card(page, tl, "PAYPAL AI HACKATHON 2026", "Errand<span class='dot'></span>",
                       "Send your model on <em style=\"font-family:'Instrument Serif',serif\">fewer</em> errands.", hold=4200)

            # 2. the problem
            cut(tl)
            page.set_content(PROBLEM_HTML)
            page.wait_for_load_state("networkidle")
            page.mouse.move(W - 40, H - 40)
            cutin(page, tl, 300)
            page.evaluate("() => { play(); }")
            tl.add("caption", text="Agents run on frontier models. Every call, frontier prices.", dur=4.2)
            page.wait_for_timeout(9600)
            tl.add("caption", text="Most of those calls are small, well-defined jobs.", dur=3.6)
            page.wait_for_timeout(4200)
            tl.add("caption", text="You're paying a genius to do arithmetic.", dur=3.2)
            page.wait_for_timeout(3600)
            tl.add("caption", text="Errand sends those jobs to cheap specialist models.", dur=4.4)
            page.wait_for_timeout(5200)

            # 3. landing hero with the live errand card
            cut(tl)
            page.goto(BASE + "/")
            page.wait_for_load_state("networkidle")
            page.mouse.move(W * 0.3, H * 0.8)
            cutin(page, tl, 600)
            tl.add("caption", text="One call. Checked before anyone is paid.", dur=3.6)
            tl.zoom(page, "#live-demo", scale=1.3, pad=60)
            page.wait_for_timeout(7600)
            tl.unzoom()
            page.wait_for_timeout(600)

            # 4. a real coding agent
            cut(tl)
            agent_scene(page, tl, lines, code)

            # 5. the dashboard: the agent's errands, a fresh receipt, a refund
            cut(tl)
            demo_login(page, BASE, "snd_alan")
            page.mouse.move(W * 0.6, H * 0.5)
            cutin(page, tl, 900)
            tl.add("caption", text="Every errand your agent sends shows up here.", dur=3.4)
            scroll_to(page, "#errands-grid", offset=180, ms=1300)
            tl.zoom(page, "#errands-grid .ag-center-cols-container .ag-row", scale=1.45, pad=20)
            glide(page, "#errands-grid .ag-center-cols-container .ag-row", 1)
            page.wait_for_timeout(3600)
            tl.unzoom()
            refunded = page.locator("#errands-grid .ag-center-cols-container .ag-row", has_text="refunded")
            if refunded.count():
                tl.add("caption", text="No right answer? You pay nothing.", dur=3.2)
                box = refunded.first.bounding_box()
                tl.add("zoom", box=[box["x"] - 20, box["y"] - 30, box["width"] + 40, box["height"] + 60], scale=1.6)
                page.mouse.move(box["x"] + 700, box["y"] + box["height"] / 2, steps=24)
                page.wait_for_timeout(3600)
                tl.unzoom()
            ease_scroll(page, 0, 1100)
            page.wait_for_timeout(400)
            tl.add("caption", text="Or send one yourself. Add the answer you expect.", dur=3.4)
            click(page, tl, "#example-btn")
            page.wait_for_timeout(500)
            tl.zoom(page, ".composer form", scale=1.3, pad=20)
            page.wait_for_timeout(2600)
            tl.unzoom()
            click(page, tl, "#send-btn")
            page.wait_for_selector(".receipt-wrap", timeout=60000)
            scroll_to(page, "#result", offset=260, ms=900)
            tl.zoom(page, "#result", scale=1.4, pad=30)
            tl.add("caption", text="The payment is held, the answer is checked, then the specialist is paid.", dur=4.4)
            page.wait_for_timeout(900)
            tl.add("sfx", name="ding")
            page.wait_for_timeout(3800)
            tl.unzoom()

            # 6. PayPal: top-up checkout, the activity log, a Runner payout on the live site
            scroll_to(page, "#topup-btn", offset=420, ms=1000)
            tl.add("caption", text="Top up your wallet with PayPal.", dur=3.0)
            tl.zoom(page, "#topup-btn", scale=1.8, pad=160)
            page.wait_for_timeout(1600)
            click(page, tl, "#topup-btn")
            cut(tl)
            try:
                page.wait_for_url("**paypal.com/**", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            cutin(page, tl, 800)
            tl.add("caption", text="Real PayPal sandbox checkout. A human approves; your agent never can.", dur=4.2)
            page.wait_for_timeout(4600)
            cut(tl)
            page.goto(BASE + "/dashboard")
            page.wait_for_load_state("networkidle")
            scroll_to(page, "details:has(#ops-grid) > summary", offset=300, ms=10)
            cutin(page, tl, 900)
            tl.add("caption", text="Every PayPal step is logged, with its sandbox ID.", dur=4.0)
            click(page, tl, "details:has(#ops-grid) > summary")
            page.wait_for_timeout(1200)
            scroll_to(page, "#ops-grid", offset=300, ms=700)
            tl.zoom(page, "#ops-grid", scale=1.3, pad=20)
            page.wait_for_timeout(4000)
            tl.unzoom()
            if live_runner:
                cut(tl)
                demo_login(page, LIVE, live_runner)
                page.wait_for_timeout(1500)
                scroll_to(page, "#wd-btn", offset=520, ms=10)
                page.mouse.move(W * 0.5, H * 0.6)
                cutin(page, tl, 900)
                tl.add("caption", text="Specialists cash out with PayPal Payouts. Live on the hosted demo.", dur=4.2)
                click(page, tl, "#wd-amt")
                page.keyboard.type("0.01", delay=120)
                page.wait_for_timeout(500)
                click(page, tl, "#wd-btn")
                try:
                    page.wait_for_selector("#toast .ok, #toast > *", timeout=60000)
                except Exception:
                    pass
                tl.add("sfx", name="ding")
                tl.zoom(page, "#toast", scale=1.6, pad=40)
                page.wait_for_timeout(3200)
                tl.unzoom()
                page.wait_for_timeout(600)

            # 7. does it work
            cut(tl)
            page.goto(BASE + "/")
            page.wait_for_load_state("networkidle")
            page.evaluate("() => { document.documentElement.style.scrollBehavior = 'auto'; }")
            y = page.evaluate("() => document.querySelector('#results').getBoundingClientRect().top + scrollY - 400")
            page.evaluate("(y) => scrollTo(0, y)", y)
            cutin(page, tl, 500)
            scroll_to(page, "#results", offset=40, ms=1400)
            tl.add("caption", text="We put real open models through Errand, on checked tasks.", dur=3.6)
            page.wait_for_timeout(900)
            tl.zoom(page, "#results .stats", scale=1.35, pad=30)
            page.wait_for_timeout(3300)
            tl.unzoom()
            scroll_to(page, "#results .bandsub", offset=160, ms=1100)
            tl.add("caption", text="The right model for each job beats any single model.", dur=3.6)
            page.wait_for_timeout(500)
            tl.zoom(page, "#results .costbars.models", scale=1.45, pad=40)
            page.wait_for_timeout(3600)
            tl.unzoom()
            scroll_to(page, "#ranks", offset=300, ms=1400)
            tl.add("caption", text="Specialists are ranked by how often they're right.", dur=3.4)
            glide(page, ".rank", 0)
            tl.zoom(page, ".rank", scale=1.5, pad=24)
            page.wait_for_timeout(3200)
            tl.unzoom()

            # 8. connect in one line
            cut(tl)
            page.goto(BASE + "/connect")
            page.wait_for_load_state("networkidle")
            page.mouse.move(W * 0.5, H * 0.7)
            cutin(page, tl, 700)
            tl.add("caption", text="One line connects Claude Code, Cursor, VS Code and more.", dur=4.0)
            tl.zoom(page, ".codebox", scale=1.6, pad=40)
            page.wait_for_timeout(1300)
            click(page, tl, ".codebox .cp")
            page.wait_for_timeout(2600)
            tl.unzoom()
            page.wait_for_timeout(500)

            # 9. end card
            cut(tl)
            page.set_content(END_HTML.replace("%ICON%", icon))
            page.wait_for_load_state("networkidle")
            page.mouse.move(W + 50, H + 50)
            cutin(page, tl, 200)
            page.wait_for_timeout(9500)
            tl.add("end")

            video = page.video
            ctx.close()
            browser.close()
            raw = Path(video.path())
            shutil.move(raw, OUT / "raw.webm")
        (OUT / "timeline.json").write_text(json.dumps({"width": W, "height": H, "events": tl.events}, indent=1), encoding="utf-8")
        print(f"recorded {OUT / 'raw.webm'} with {len(tl.events)} timeline events")
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
