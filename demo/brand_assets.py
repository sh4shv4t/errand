"""Render Errand's brand assets (logos, favicon, architecture diagram) from HTML, in the brand fonts.

    demo/.venv/Scripts/python demo/brand_assets.py      -> assets/*.png, assets/favicon.ico
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500'
         '&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet">')


def mark(ink: str = "#015d47", dot: str = "#fd550a") -> str:
    return (f'<svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">'
            f'<circle cx="12.5" cy="16" r="8.5" stroke="{ink}" stroke-width="2.6"/>'
            f'<path d="M19.5 11.2 C 24 6.5, 29.5 9.5, 29 14.5 C 28.6 19.5, 24 22.5, 20 20.5" stroke="{ink}" stroke-width="2.2" '
            f'stroke-linecap="round" stroke-dasharray="0.1 4.2"/><circle cx="29" cy="14.5" r="2.8" fill="{dot}"/></svg>')


def wordmark(ink: str, sub: str) -> str:
    return f"""<!doctype html><html><head>{FONTS}<style>
      html,body{{margin:0;background:transparent}}
      .w{{display:inline-flex;align-items:center;gap:26px;padding:24px 34px}}
      .w svg{{width:132px;height:132px}}
      .t{{font:600 112px/1 Geist,sans-serif;letter-spacing:-0.045em;color:{ink}}}
      .t i{{display:block;font:italic 400 34px/1.2 'Instrument Serif',serif;letter-spacing:-0.01em;color:{sub};margin-top:10px}}
    </style></head><body><div class="w">{mark(ink if ink != '#0b2a21' else '#015d47')}<div class="t">Errand<i>Send your model on fewer errands.</i></div></div></body></html>"""


SQUARE = f"""<!doctype html><html><head><style>html,body{{margin:0;background:transparent}}
  .s{{width:512px;height:512px;border-radius:112px;background:#f4f0e6;display:grid;place-items:center}}
  .s svg{{width:360px;height:360px}}</style></head><body><div class="s">{mark()}</div></body></html>"""

ARCH = f"""<!doctype html><html><head>{FONTS}<style>
  html,body{{margin:0;background:#f4f0e6;font-family:Geist,sans-serif;color:#0b2a21}}
  .wrap{{width:1600px;padding:56px 64px;box-sizing:border-box}}
  h1{{font:500 44px/1.1 Geist;letter-spacing:-0.03em;margin:0 0 6px}} h1 i{{font:italic 400 48px 'Instrument Serif';color:#015d47}}
  .sub{{color:#4f6b61;font-size:20px;margin:0 0 40px}}
  .row{{display:grid;grid-template-columns:330px 60px 1fr 60px 330px;align-items:stretch}}
  .col{{display:grid;gap:14px;align-content:center}}
  .box{{background:#fbf9f4;border:1.5px solid rgba(11,42,33,.14);border-radius:18px;padding:18px 20px}}
  .box b{{display:block;font-size:20px;font-weight:600;margin-bottom:4px}} .box span{{color:#4f6b61;font-size:16px;line-height:1.4}}
  .lbl{{font:500 14px 'Geist Mono';letter-spacing:.1em;color:#b83f0a;margin-bottom:10px}}
  .arrow{{display:grid;place-items:center;font:500 34px Geist;color:#015d47}}
  .gw{{background:#015d47;color:#f4f0e6;border-radius:24px;padding:26px;display:grid;gap:12px}}
  .gw .lbl{{color:#e0f354}} .gw .step{{background:rgba(244,240,230,.09);border:1px solid rgba(244,240,230,.18);border-radius:14px;padding:14px 18px;display:flex;gap:14px;align-items:baseline}}
  .gw .n{{font:500 15px 'Geist Mono';color:#e0f354;min-width:26px}} .gw .step b{{font-size:19px;font-weight:600}} .gw .step span{{color:rgba(244,240,230,.78);font-size:15.5px}}
  .bottom{{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-top:30px}}
  .pp{{background:#fbf9f4;border:1.5px solid rgba(11,42,33,.14);border-radius:20px;padding:20px 24px}}
  .chips{{display:flex;flex-wrap:wrap;gap:10px}} .chip{{border-radius:10px;padding:9px 13px;font-size:15.5px;background:#e9e3d4}}
  .chip b{{font-weight:600}} .pay .chip{{background:#fff3d6;border:1px solid #f5c860}} .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#fd550a;margin-right:8px}}
</style></head><body><div class="wrap">
  <h1>How <i>Errand</i> works</h1><p class="sub">One call from any agent. The money waits until the answer checks out.</p>
  <div class="row">
    <div class="col"><div class="lbl">SENDERS</div>
      <div class="box"><b>Coding agents</b><span>Claude Code, Cursor, VS Code, any MCP client</span></div>
      <div class="box"><b>Your own agent</b><span>Python SDK, OpenAI or Anthropic tool calling</span></div>
      <div class="box"><b>Anything with HTTP</b><span>REST API, Postman collection, APIMatic SDKs</span></div></div>
    <div class="arrow">→</div>
    <div class="gw"><div class="lbl">ERRAND GATEWAY · delegate(task, check)</div>
      <div class="step"><span class="n">01</span><div><b>Understand the job</b><br><span>Math or code? Tests parse? Within your spending cap?</span></div></div>
      <div class="step"><span class="n">02</span><div><b>Pick the specialist</b><br><span>Per-job ratings plus Thompson sampling, or the Runner you pin</span></div></div>
      <div class="step"><span class="n">03</span><div><b>Hold the money in escrow</b><br><span>Double-entry ledger, every transaction sums to zero</span></div></div>
      <div class="step"><span class="n">04</span><div><b>Check the answer</b><br><span>Exact math answers, Python tests in a separate process</span></div></div>
      <div class="step"><span class="n">05</span><div><b>Pay, or retry for free</b><br><span>Right: Runner is paid. Wrong: refunded and sent elsewhere.</span></div></div></div>
    <div class="arrow">⇄</div>
    <div class="col"><div class="lbl">RUNNERS</div>
      <div class="box"><b>Local models</b><span>qwen2.5, qwen2.5-coder, phi3 via Ollama</span></div>
      <div class="box"><b>Hosted models</b><span>Any OpenAI-compatible endpoint: Groq, vLLM, OpenRouter</span></div>
      <div class="box"><b>Your own service</b><span>A webhook that answers errands</span></div></div>
  </div>
  <div class="bottom">
    <div class="pp pay"><div class="lbl">PAYPAL SANDBOX</div><div class="chips">
      <span class="chip"><b>Orders v2 · CAPTURE</b> wallet top-ups</span>
      <span class="chip"><b>Orders v2 · AUTHORIZE</b> bounty escrow</span>
      <span class="chip"><b>Authorizations</b> capture on pass, void on fail</span>
      <span class="chip"><b>Payouts</b> Runner withdrawals</span></div></div>
    <div class="pp"><div class="lbl">KEEPING RUNNERS HONEST</div><div class="chips">
      <span class="chip"><span class="dot"></span>Onboarding exam per job type</span>
      <span class="chip"><span class="dot"></span>Hidden test questions</span>
      <span class="chip"><span class="dot"></span>Model-swap detection</span>
      <span class="chip"><span class="dot"></span>Deposit slashed, Senders refunded</span></div></div>
  </div>
</div></body></html>"""


def shot(page, html: str, path: Path, selector: str, transparent: bool = True) -> None:
    page.set_content(html)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)
    page.locator(selector).screenshot(path=str(path), omit_background=transparent)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel="chrome")
        page = b.new_page(viewport={"width": 1700, "height": 1000}, device_scale_factor=2)
        shot(page, wordmark("#0b2a21", "#4f6b61"), ASSETS / "errand-logo.png", ".w")
        shot(page, wordmark("#f4f0e6", "#9db3aa"), ASSETS / "errand-logo-dark.png", ".w")
        shot(page, SQUARE, ASSETS / "errand-icon.png", ".s")
        page = b.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        shot(page, ARCH, ASSETS / "architecture.png", ".wrap", transparent=False)
        b.close()
    icon = Image.open(ASSETS / "errand-icon.png")
    icon.save(ASSETS / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    for p in sorted(ASSETS.glob("*")):
        print(p.name, p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
