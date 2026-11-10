"""Record the Errand demo walkthrough.

Starts a fresh, pre-populated Errand instance, drives it in Chrome with a visible cursor and eased
scrolling, and records the screen. Alongside the video it writes timeline.json: when to zoom (and on
what), which sound effect to play, and which caption to show. demo/edit.py turns both into the cut.

    demo/.venv/Scripts/python demo/record.py
"""

from __future__ import annotations

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


TERMINAL_HTML = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;background:#f4f0e6;font-family:Geist,sans-serif;overflow:hidden}
  .stage{height:100%;display:grid;place-items:center}
  .win{width:1440px;height:760px;background:#0b1f19;border-radius:18px;box-shadow:0 40px 80px -30px rgba(11,42,33,.45);
       display:flex;flex-direction:column;overflow:hidden}
  .bar{height:52px;display:flex;align-items:center;gap:10px;padding:0 22px;background:#12291f;color:#9db3aa;font:500 17px Geist Mono,monospace}
  .bar i{width:13px;height:13px;border-radius:50%;background:#2c4a3f;display:inline-block}
  .bar span{margin-left:14px}
  #log{flex:1;padding:30px 36px;font:24px/1.75 'Geist Mono',monospace;color:#f4f0e6;overflow:hidden}
  .ln{white-space:pre-wrap;animation:in .35s ease-out both}
  @keyframes in{from{opacity:0;transform:translateY(6px)}}
  .p{color:#7fd1b0}.dim{color:#9db3aa}.tool{color:#e0f354}.ok{color:#7fd1b0}.err{color:#f19a8c}.file{color:#f4f0e6}.agent{color:#f4f0e6}
  .cur{display:inline-block;width:12px;height:26px;background:#f4f0e6;vertical-align:-5px;animation:b 1s steps(1) infinite}
  @keyframes b{50%{opacity:0}}
</style></head><body><div class="stage"><div class="win">
  <div class="bar"><i></i><i></i><i></i><span>~/my-app · coding agent (qwen2.5 7B) + Errand</span></div>
  <div id="log"></div></div></div>
<script>
  const log = document.getElementById('log');
  window.addLine = (cls, text) => { const d = document.createElement('div'); d.className = 'ln ' + cls; d.textContent = text; log.appendChild(d); return d; };
  window.typeLine = (prefix, text, ms) => new Promise((done) => {
    const d = document.createElement('div'); d.className = 'ln'; d.innerHTML = '<span class="p">' + prefix + '</span><span class="t"></span><span class="cur"></span>';
    log.appendChild(d); const t = d.querySelector('.t'); let i = 0;
    const tick = () => { t.textContent = text.slice(0, ++i); i < text.length ? setTimeout(tick, ms) : (d.querySelector('.cur').remove(), done()); };
    tick();
  });
</script></body></html>"""


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


AGENT_TASK = "Add a function is_palindrome(s) to text_utils.py that ignores case and spaces."


def agent_scene(page, tl: Timeline) -> None:
    """Run the real coding agent and stream its output into a terminal window."""
    page.set_content(TERMINAL_HTML)
    page.wait_for_load_state("networkidle")
    page.mouse.move(W - 40, H - 40)
    tl.add("caption", text="Your coding agent gets one new tool: Errand.", dur=3.2)
    page.wait_for_timeout(700)
    page.evaluate("([p, t]) => typeLine(p, t, 28)", ["you › ", AGENT_TASK])
    page.wait_for_timeout(600)
    key = json.loads((OUT / "demo_keys.json").read_text(encoding="utf-8"))["senders"]["snd_alan"]["api_key"]
    env = os.environ | {"ERRAND_URL": BASE, "ERRAND_API_KEY": key, "LLM_MODEL": "qwen2.5:7b", "PYTHONIOENCODING": "utf-8", "AGENT_BUDGET_USD": "0.001",
                        "AGENT_PROJECT": str(OUT / "my-app")}
    proc = subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "demo" / "coding_agent.py"), AGENT_TASK],
                            env=env, cwd=ROOT, stdout=subprocess.PIPE, text=True, encoding="utf-8")
    page.evaluate("() => addLine('dim', 'agent › thinking…')")
    page.wait_for_timeout(1000)
    tl.add("fast", on=True)  # model think time plays as a time-lapse in the edit
    for raw in proc.stdout:
        kind, _, text = raw.rstrip("\n").partition("|")
        if kind == "user":
            continue
        tl.add("fast", on=False)
        if kind == "tool":
            page.evaluate("([t]) => addLine('tool', '⚙ ' + t)", [text])
            tl.add("sfx", name="click")
            tl.add("caption", text="It hands the function, with tests, to a cheaper specialist.", dur=3.4)
            sel = "#log .ln.tool"
            tl.zoom(page, sel, scale=1.5, pad=40)
        elif kind == "ok":
            page.evaluate("([t]) => addLine('ok', '✓ ' + t)", [text])
            tl.add("sfx", name="ding")
            tl.add("caption", text="Errand runs the tests. Only passing code gets paid.", dur=3.4)
            tl.zoom(page, "#log .ln.ok", scale=1.5, pad=40)
        elif kind == "err":
            page.evaluate("([t]) => addLine('err', '✗ ' + t)", [text])
        elif kind == "file":
            page.evaluate("([t]) => addLine('file', '✎ ' + t)", [text])
        elif kind == "agent":
            page.evaluate("([t]) => addLine('agent', 'agent › ' + t)", [text])
        page.wait_for_timeout(3600 if kind in ("tool", "ok") else 1400)
        tl.unzoom()
        tl.add("fast", on=True)
    tl.add("fast", on=False)
    proc.wait()
    page.wait_for_timeout(1600)
    tl.unzoom()
    page.wait_for_timeout(900)


def main() -> None:
    server = start_server()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(channel="chrome", headless=False, args=["--hide-scrollbars"])
            ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light",
                                      record_video_dir=str(OUT / "raw"), record_video_size={"width": W, "height": H})
            ctx.add_init_script(CURSOR_JS)
            page = ctx.new_page()
            tl = Timeline()

            # 1. title
            title_card(page, tl, "PAYPAL AI HACKATHON 2026", "Errand<span class='dot'></span>",
                       "Send your model on <em style=\"font-family:'Instrument Serif',serif\">fewer</em> errands.")

            # 2. landing hero
            page.goto(BASE + "/")
            page.mouse.move(W * 0.7, H * 0.75)
            tl.add("caption", text="Big AI models are brilliant. And expensive.", dur=3.0)
            page.wait_for_timeout(900)
            tl.zoom(page, ".hero h1", scale=1.45, pad=60)
            page.wait_for_timeout(2400)
            tl.add("caption", text="Errand lets your AI hand small jobs to cheaper specialists.", dur=3.2)
            tl.zoom(page, ".hero p.lead", scale=1.7, pad=50)
            page.wait_for_timeout(2600)
            tl.unzoom()
            page.wait_for_timeout(700)

            # 3. a real coding agent using Errand
            agent_scene(page, tl)
            page.goto(BASE + "/")
            page.wait_for_timeout(600)

            # 4. real benchmark
            scroll_to(page, "#results", offset=40, ms=1500)
            tl.add("caption", text="We put real open models through Errand.", dur=3.0)
            page.wait_for_timeout(1200)
            tl.zoom(page, "#results .stats", scale=1.35, pad=30)
            page.wait_for_timeout(2600)
            tl.unzoom()
            scroll_to(page, "#results .bandsub", offset=160, ms=1000)
            tl.add("caption", text="The right model for each job beats any single model.", dur=3.2)
            page.wait_for_timeout(500)
            tl.zoom(page, "#results .costbars.models", scale=1.5, pad=40)
            page.wait_for_timeout(3000)
            tl.unzoom()

            # 5. rankings
            scroll_to(page, "#ranks", offset=260, ms=1500)
            tl.add("caption", text="Specialists are ranked by how often they're right.", dur=3.0)
            page.wait_for_timeout(500)
            glide(page, ".rank", 0)
            tl.zoom(page, ".rank", scale=1.5, pad=24)
            page.wait_for_timeout(2600)
            tl.unzoom()

            # 6. into the dashboard, where the agent's errand already shows up
            ease_scroll(page, 0, 1300)
            page.wait_for_timeout(300)
            click(page, tl, ".hero button.accent")
            page.wait_for_url("**/dashboard")
            page.wait_for_timeout(1200)
            tl.add("caption", text="Every errand your agent sends shows up here.", dur=3.0)
            scroll_to(page, "#errands-grid", offset=200, ms=1100)
            tl.zoom(page, "#errands-grid .ag-row", scale=1.6, pad=30)
            page.wait_for_timeout(2600)
            tl.unzoom()
            ease_scroll(page, 0, 900)

            # 7. a math errand, verified then paid
            tl.add("caption", text="Describe the job. Add the answer you expect, if you know it.", dur=3.4)
            click(page, tl, "#example-btn")
            page.wait_for_timeout(500)
            tl.zoom(page, ".composer form", scale=1.35, pad=20)
            page.wait_for_timeout(2600)
            tl.unzoom()
            click(page, tl, "#send-btn")
            page.wait_for_selector(".receipt-wrap", timeout=20000)
            scroll_to(page, "#result", offset=260, ms=900)
            tl.zoom(page, "#result", scale=1.45, pad=30)
            tl.add("caption", text="Checked first. Paid only because it's right.", dur=3.4)
            page.wait_for_timeout(750)
            page.wait_for_timeout(500)
            tl.add("sfx", name="ding")
            page.wait_for_timeout(2600)
            tl.unzoom()

            # 8. pick your own model, a code errand
            ease_scroll(page, 0, 900)
            tl.add("caption", text="Want a specific model? Pick it. Code jobs ship with tests.", dur=3.4)
            click(page, tl, "#example-btn")
            page.wait_for_timeout(300)
            glide(page, "#runner")
            tl.add("sfx", name="click")
            page.select_option("#runner", "Atlas")
            tl.zoom(page, "#runner", scale=1.9, pad=60)
            page.wait_for_timeout(1700)
            tl.unzoom()
            click(page, tl, "#send-btn")
            page.wait_for_function("document.querySelector('#result .line') && document.querySelector('#result').innerText.includes('pinned')",
                                   timeout=30000)
            scroll_to(page, "#result", offset=260, ms=900)
            tl.zoom(page, "#result", scale=1.45, pad=30)
            page.wait_for_timeout(750)
            page.wait_for_timeout(500)
            tl.add("sfx", name="ding")
            page.wait_for_timeout(2200)
            tl.unzoom()

            # 9. savings and connect
            ease_scroll(page, 0, 900)
            page.wait_for_timeout(300)
            tl.add("caption", text="Every errand adds to what you've saved.", dur=2.6)
            tl.zoom(page, ".kpi.accent", scale=2.0, pad=30)
            page.wait_for_timeout(2400)
            tl.unzoom()
            tl.add("caption", text="One line connects any AI agent: Claude, Cursor, VS Code.", dur=3.4)
            tl.zoom(page, "#connect-cmd", scale=1.8, pad=40)
            page.wait_for_timeout(1200)
            click(page, tl, "[data-copy='#connect-cmd']")
            page.wait_for_timeout(1800)
            tl.unzoom()
            page.wait_for_timeout(500)

            # 10. end card
            title_card(page, tl, "PAY ON PROOF · SETTLED WITH PAYPAL", "Errand<span class='dot'></span>",
                       "Same answers. 98% cheaper. Pay only when it's right.", hold=3600)
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
