"""Product screenshots for the README and the Devpost gallery (3:2, 1500x1000).

Starts a fresh demo instance (same as record.py, so PayPal runs in sandbox mode when .env has keys),
and captures the key screens. The coding-agent screenshot comes from demo/agent_shot.py.

    demo/.venv/Scripts/python demo/screenshots.py      -> assets/screens/*.png
"""

from __future__ import annotations

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


def main() -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    server = record.start_server()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(channel="chrome", args=["--hide-scrollbars"])
            ctx = b.new_context(viewport={"width": W, "height": H}, color_scheme="light")
            page = ctx.new_page()
            page.goto(record.BASE + "/")
            page.wait_for_selector(".dc-receipt.show", timeout=30000)  # hero card has played one full errand
            page.wait_for_timeout(700)
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
