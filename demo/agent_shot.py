"""Screenshot of a real coding-agent run that branches into several errands.

Runs demo/coding_agent.py live against a running demo instance (start one with record.start_server, or any
Errand at ERRAND_URL), then renders its actual output beside the file it wrote. Nothing is typed in by hand.

    demo/.venv/Scripts/python demo/agent_shot.py      -> assets/screens/coding-agent.png
"""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo" / "out"
PROJECT = OUT / "branch-app"
TASK = ("In text_utils.py, add is_palindrome(s) that ignores case and spaces, and word_count(s) that returns how many "
        "words s has. Also work out how many ways a committee of 4 can be chosen from 10 people, and note it in a comment.")

STYLE = {"tool": ("#e0f354", "⚙ "), "ok": ("#7fd1b0", "✓ "), "err": ("#f19a8c", "✗ "), "file": ("#f4f0e6", "✎ "),
         "agent": ("#f4f0e6", "agent › "), "user": ("#7fd1b0", "you › ")}


def run_agent() -> list[tuple[str, str]]:
    key = json.loads((OUT / "demo_keys.json").read_text(encoding="utf-8"))["senders"]["snd_alan"]["api_key"]
    env = os.environ | {"ERRAND_URL": os.environ.get("ERRAND_URL", "http://localhost:8002"), "ERRAND_API_KEY": key,
                        "LLM_MODEL": "qwen2.5:7b", "AGENT_BUDGET_USD": "0.001", "AGENT_PROJECT": str(PROJECT),
                        "PYTHONIOENCODING": "utf-8"}
    for f in PROJECT.glob("*"):
        f.unlink()
    out = subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "demo" / "coding_agent.py"), TASK],
                         env=env, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout
    lines = [tuple(l.split("|", 1)) for l in out.splitlines() if "|" in l]
    (OUT / "agent-shot.log").write_text(out, encoding="utf-8")
    return lines


def page_html(lines: list[tuple[str, str]], code: str) -> str:
    rows = "".join(f'<div class="ln" style="color:{STYLE[k][0]}">{html.escape(STYLE[k][1] + t)}</div>'
                   for k, t in lines if k in STYLE)
    return f"""<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  html,body{{margin:0;background:#f4f0e6;font-family:Geist,sans-serif}}
  .stage{{width:1500px;height:1000px;box-sizing:border-box;padding:40px 44px;display:grid;grid-template-rows:auto 1fr;gap:22px}}
  .win{{background:#0b1f19;border-radius:16px;overflow:hidden;box-shadow:0 30px 60px -30px rgba(11,42,33,.45)}}
  .bar{{height:44px;display:flex;align-items:center;gap:9px;padding:0 18px;background:#12291f;color:#9db3aa;font:500 15px 'Geist Mono',monospace}}
  .bar i{{width:12px;height:12px;border-radius:50%;background:#2c4a3f;display:inline-block}} .bar span{{margin-left:12px}}
  .log{{padding:20px 26px;font:17.5px/1.7 'Geist Mono',monospace;white-space:pre-wrap;word-break:break-word}}
  .code{{background:#fbf9f4;border:1.5px solid rgba(11,42,33,.14);border-radius:16px;overflow:hidden;display:flex;flex-direction:column}}
  .code .bar{{background:#e9e3d4;color:#4f6b61}} .code .bar i{{background:#cfc6b2}}
  pre{{margin:0;padding:16px 26px;font:15.5px/1.55 'Geist Mono',monospace;color:#0b2a21;overflow:hidden}}
</style></head><body><div class="stage">
  <div class="win"><div class="bar"><i></i><i></i><i></i><span>~/my-app · coding agent (qwen2.5 7B) + Errand</span></div>
    <div class="log">{rows}</div></div>
  <div class="code"><div class="bar"><i></i><i></i><i></i><span>text_utils.py · written by the agent from two verified errands</span></div>
    <pre>{html.escape(code)}</pre></div>
</div></body></html>"""


def main() -> None:
    lines = run_agent()
    if sum(k == "ok" for k, _ in lines) < 2:
        sys.exit("the agent did not complete two verified errands this time; run again")
    code = (PROJECT / "text_utils.py").read_text(encoding="utf-8").strip()
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        page = b.new_page(viewport={"width": 1500, "height": 1000})
        page.set_content(page_html(lines, code))
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(400)
        page.screenshot(path=str(ROOT / "assets" / "screens" / "coding-agent.png"))
        b.close()
    print("saved assets/screens/coding-agent.png")


if __name__ == "__main__":
    main()
