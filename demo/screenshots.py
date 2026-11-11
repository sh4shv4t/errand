"""Product screenshots for the README and the Devpost gallery (3:2, 1500x1000).

Starts a fresh demo instance (same as record.py, so PayPal runs in sandbox mode when .env has keys),
captures the key screens, and pulls the coding-agent frame from the last recording.

    demo/.venv/Scripts/python demo/screenshots.py      -> assets/screens/*.png
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record  # noqa: E402  (reuses the server setup and scroll helpers)

ROOT = record.ROOT
SHOTS = ROOT / "assets" / "screens"
W, H = 1500, 1000


MASK_KEYS = """() => {
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walk.nextNode()) walk.currentNode.nodeValue = walk.currentNode.nodeValue.replace(/erk_[\\w-]{6,}/g, 'erk_YOUR_KEY');
}"""


def snap(page, name: str) -> None:
    page.wait_for_timeout(900)
    if "localhost" in page.url:
        page.evaluate(MASK_KEYS)  # never publish an API key, even a throwaway demo one
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print("saved", name)


def agent_frame() -> None:
    """The real coding-agent run, from the last recording: the frame where the verified code is written."""
    raw = record.OUT / "cfr.mp4"
    timeline = record.OUT / "timeline.json"
    if not raw.exists() or not timeline.exists():
        print("skip agent frame (record and edit first)")
        return
    events = json.loads(timeline.read_text(encoding="utf-8"))["events"]
    t = next(e["t"] for e in events if e["kind"] == "caption" and e["text"].startswith("Errand runs the tests")) + 6.0
    # the terminal window sits centred in the 1920x1080 frame; crop a 3:2 box around it
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(raw), "-frames:v", "1",
                    "-vf", "crop=1530:1020:195:30,scale=1500:1000", str(SHOTS / "coding-agent.png")], check=True)
    print("saved coding-agent")


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    agent_frame()
    server = record.start_server()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="chrome", args=["--hide-scrollbars"])
            ctx = b.new_context(viewport={"width": W, "height": H}, color_scheme="light")
            page = ctx.new_page()
            page.goto(record.BASE + "/")
            snap(page, "landing")
            for sel, name, off in (("#results", "results", 20), ("#ranks", "rankings", 230), (".roadmap", "roadmap", 200)):
                page.evaluate("document.querySelectorAll('.reveal,.mark').forEach(e => e.classList.add('in'))")
                record.scroll_to(page, sel, offset=off, ms=300)
                page.wait_for_timeout(1500)  # let counters and bars finish
                snap(page, name)

            page.goto(record.BASE + "/")
            page.locator(".hero button.accent").click()
            page.wait_for_url("**/dashboard")
            page.locator("#example-btn").click()
            page.wait_for_timeout(300)
            page.locator("#send-btn").click()
            page.wait_for_selector(".receipt-wrap", timeout=30000)
            page.wait_for_timeout(1500)
            record.scroll_to(page, ".composer", offset=90, ms=300)
            snap(page, "dashboard-receipt")
            record.scroll_to(page, "#errands-grid", offset=330, ms=300)
            snap(page, "dashboard-errands")

            page.goto(record.BASE + "/connect")
            snap(page, "connect")

            # the real PayPal sandbox checkout Errand sends a top-up to (needs sandbox keys in .env)
            page.goto(record.BASE + "/dashboard")
            badge = page.locator(".nav .badge").first.inner_text()
            if "sandbox" in badge.lower():
                page.locator("#topup-btn").click()
                page.wait_for_url("**sandbox.paypal.com/**", timeout=30000)
                page.wait_for_load_state("load")  # PayPal keeps connections open, so never "networkidle"
                page.wait_for_timeout(3000)
                snap(page, "paypal-sandbox-checkout")
            else:
                print("skip PayPal checkout (mock mode)")
            b.close()
    finally:
        server.terminate()


if __name__ == "__main__":
    main()
