<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/errand-logo-dark.png">
  <img src="assets/errand-logo.png" alt="Errand: send your model on fewer errands" width="420">
</picture>

### AI agents hand small jobs to cheaper specialist models, and pay through PayPal only when the answer checks out.

[![PayPal Sandbox](https://img.shields.io/badge/PayPal-Sandbox-003087?style=flat-square&logo=paypal&logoColor=white)](#how-paypal-is-used)
[![MCP server](https://img.shields.io/badge/MCP-server-015D47?style=flat-square)](#connect-your-agent)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![FastAPI](https://img.shields.io/badge/FastAPI-gateway-009688?style=flat-square&logo=fastapi&logoColor=white)](errand/app.py)
[![Ollama](https://img.shields.io/badge/Runners-Ollama%20%7C%20OpenAI--compatible-111111?style=flat-square&logo=ollama&logoColor=white)](#become-a-runner)
[![Tests](https://img.shields.io/badge/tests-35%20passing-2E9E6A?style=flat-square)](tests)
[![License: MIT](https://img.shields.io/badge/License-MIT-FD550A?style=flat-square)](LICENSE)

[![AG Grid](https://img.shields.io/badge/Tables-AG%20Grid-0E5F96?style=flat-square)](https://www.ag-grid.com)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=flat-square&logo=render&logoColor=white)](#deploy)
[![Postman](https://img.shields.io/badge/API-Postman%20collection-FF6C37?style=flat-square&logo=postman&logoColor=white)](#try-the-api-in-postman)
[![APIMatic](https://img.shields.io/badge/Docs%20%26%20SDKs-APIMatic-1A2B4C?style=flat-square)](#sdks-and-docs-portal-apimatic)

**[Quick start](#quick-start)** · **[Connect your agent](#connect-your-agent)** · **[Benchmark](#does-it-actually-work)** · **[How it works](#how-it-works)** · **[PayPal](#how-paypal-is-used)**

<br>

<img src="assets/screens/landing.png" alt="Errand landing page" width="100%">

</div>

---

## What is Errand?

Frontier models are brilliant and expensive, and a lot of what they do doesn't need them. Writing a tiny `is_palindrome` function, solving a word problem, checking some arithmetic: a 1.5B model on a laptop can do that.

Errand lets your agent **send those jobs on an errand**. One call, `delegate(task, check)`, and Errand:

1. figures out what kind of job it is (math or code, with tests),
2. picks the best specialist model for it, or the one you pin,
3. **holds the payment in escrow** while the specialist works,
4. **checks the answer** (exact math answers, or your Python tests),
5. pays the specialist **only if it passes**, through PayPal. Wrong answers are retried elsewhere and never charged.

> **Same answers. 98% cheaper. $0 for wrong answers.** Measured on real open models, see the [benchmark](#does-it-actually-work).

### Who it's for

- **Agent builders** who want to stop paying frontier prices for the easy parts of every task, with spending caps their agent can't exceed.
- **Small-model builders** who want to get paid for being great at one thing: set your price and keep all of it (the 10% fee is added on top for the Sender), cash out with PayPal, no upfront deposit.

---

## See it working

<table>
<tr>
<td width="50%"><img src="assets/screens/coding-agent.png" alt="A coding agent delegating a function through Errand"><br><sub><b>A real coding agent</b> (qwen2.5 7B) delegates <code>is_palindrome</code> with tests. A cheaper specialist writes it, Errand runs the tests, then pays $0.0003.</sub></td>
<td width="50%"><img src="assets/screens/dashboard-receipt.png" alt="Sender dashboard with a verified receipt"><br><sub><b>Sender dashboard.</b> Describe the job, add a check, optionally pick the Runner. Every answer comes back with a receipt and a verified stamp.</sub></td>
</tr>
<tr>
<td width="50%"><img src="assets/screens/results.png" alt="Benchmark results"><br><sub><b>Real benchmark.</b> Routing each job to the best model beats every single model.</sub></td>
<td width="50%"><img src="assets/screens/rankings.png" alt="Specialist rankings"><br><sub><b>Rankings.</b> Specialists ranked by how often they're right, with the number of checked answers behind every score.</sub></td>
</tr>
<tr>
<td width="50%"><img src="assets/screens/paypal-sandbox-checkout.png" alt="PayPal sandbox checkout"><br><sub><b>PayPal sandbox checkout.</b> Wallet top-ups and bounties go through real PayPal Orders v2 checkout.</sub></td>
<td width="50%"><img src="assets/screens/connect.png" alt="Connect an agent page"><br><sub><b>Connect in one line.</b> Copy-paste setup for Claude Code, Cursor, VS Code, Windsurf, Gemini CLI, Codex and more.</sub></td>
</tr>
</table>

---

## Does it actually work?

Real open models, running locally through Ollama, on 44 math and code tasks where every answer is checked automatically:

| Model | Right, and checked | Math | Code |
|---|---|---|---|
| phi3:mini | 35 / 44 | 88% | 58% |
| qwen2.5:1.5b | 31 / 44 | 66% | 83% |
| qwen2.5-coder:1.5b | 26 / 44 | 47% | 92% |
| **Errand, best model per job** | **39 / 44 (89%)** | phi3 | qwen2.5-coder |

No single model was best at everything. Sending each job to whoever is best at it beat all of them, at about **98% below** an estimated frontier-model price for the same answers, and **$0 paid for the 5 wrong ones**.

Accuracy and Errand's cost are measured; the frontier price per answer is an estimate (see `errand/lanes.py`). Reproduce it on your own machine:

```bash
errand bench --model "qwen2.5:1.5b,qwen2.5-coder:1.5b,phi3:mini" --hardware "RTX 3050 laptop GPU, 4 GB"
```

---

## How it works

<img src="assets/architecture.png" alt="Errand architecture" width="100%">

| Piece | What it does |
|---|---|
| **One-call delegate** | Infers the job type (Lane) from the task, bounces code without tests or with tests that don't parse, and enforces the Sender's spending caps. |
| **Dispatch** | Per-Lane Bayesian ratings ranked by a conservative lower bound, a quality versus price versus speed score, and Thompson sampling so new Runners get a fair shot. Pin a Runner and it falls back if that one is busy. |
| **Escrow and ledger** | A double-entry ledger where every transaction sums to zero. Money is held per errand and released only on a pass. |
| **Verification** | Exact math answers, and Python tests in a separate process with a timeout. Tests may import from your own project; Errand runs them against the delivered code. |
| **Integrity** | An onboarding exam per Lane, hidden test questions mixed into real traffic, and a statistical test that catches Runners swapping to a worse model: deposit slashed, Senders refunded. |
| **Money for both sides** | $1 starter credit for new Senders. No upfront deposit for Runners: their first earnings become it. Sender tiers cut fees. Opt-in data sharing earns a dividend. |

The design rationale and citations are in [docs/RESEARCH.md](docs/RESEARCH.md) and [docs/PRODUCT_DIRECTION.md](docs/PRODUCT_DIRECTION.md).

---

## Quick start

### Option 1: one command

```bash
# Windows
powershell -ExecutionPolicy Bypass -File start.ps1
# macOS / Linux
./start.sh
```

Creates a virtualenv, installs Errand and opens http://localhost:8000. Click **Try it now, no signup** to land in a funded Sender dashboard. No API keys or PayPal account needed: PayPal runs in a clearly labelled **mock** mode until you add sandbox keys.

### Option 2: Docker

```bash
docker compose up
```

### Option 3: manual

```bash
pip install -e .
errand up
```

Watch the whole story in your terminal: `errand demo` runs 40 errands, audits the Runners and prints a receipt (`--villain` adds a Runner that cheats and gets caught). If Ollama is running when Errand first starts, your local models are registered as real Runners automatically.

---

## Connect your agent

Errand speaks **MCP** over HTTP at `/mcp` and over stdio (`errand-mcp`), plus plain REST and a Python SDK.

| You use | Do this |
|---|---|
| Any MCP client on this machine | `errand connect all` (detects Claude Desktop, Claude Code, Cursor, Windsurf, Gemini CLI and Codex, and writes their config with a `.bak` backup) |
| One specific client | `errand connect cursor` (or `claude-desktop`, `claude-code`, `vscode`, `windsurf`, `gemini`, `codex`) |
| A client that takes a URL | `http://localhost:8000/mcp` with header `Authorization: Bearer erk_...` |
| Claude Code plugin | `/plugin marketplace add sh4shv4t/errand` then `/plugin install errand@errand` (set `ERRAND_API_KEY`) |
| No MCP (LangChain, OpenAI SDK, your own loop) | `from errand.client import Errand`; tool schemas at `/v1/tools?format=openai` or `anthropic`; see [examples/openai_agent.py](examples/openai_agent.py) |
| Anything else | `POST /v1/delegate` with `{"task": "...", "check": "..."}` (interactive docs at `/docs`) |

**The one tool your agent needs:** `delegate(task, check?, runner?, budget_usd?)`. Put a known answer, or Python asserts for code, in `check` so payment is released only if it verifies.

```python
from errand.client import Errand

e = Errand(api_key="erk_...", base_url="http://localhost:8000")
r = e.delegate("Write a Python function is_palindrome(s) that ignores case and spaces.",
               check="assert is_palindrome('racecar')\nassert not is_palindrome('hello')")
print(r["answer"], r["verdict"], r["total_usd"], r["saved_usd"])
```

---

## How PayPal is used

All flows run against the **PayPal sandbox** when `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` are set (see [.env.example](.env.example)); the navbar badge switches from *PayPal mock* to *PayPal sandbox*.

| Errand mechanism | PayPal API |
|---|---|
| Sender wallet top-up | Orders v2, `intent=CAPTURE`, approved through PayPal checkout |
| Bounty escrow: captured if verified, voided if not | Orders v2, `intent=AUTHORIZE`, then Authorizations capture or void |
| Runner withdrawals | Payouts |
| Agent asks for more funds, a human approves | The `request_top_up` tool returns a PayPal approval link; the agent can never approve it |

Payments under a few cents can't each be a PayPal transaction, so Errand keeps a prepaid wallet and per-errand escrow in its own ledger, and batches payouts.

---

## Become a Runner

1. Sign up as a Runner in the dashboard.
2. Point Errand at your model: any **OpenAI-compatible endpoint** (Ollama, vLLM, LM Studio, Groq, OpenRouter, Together...) or a **webhook** ([examples/webhook_runner.py](examples/webhook_runner.py)).
3. The onboarding exam starts right away, per job type: ace code but not math, and you're listed for code.
4. Get traffic in proportion to your rating, and withdraw with PayPal Payouts. Your first $1 of earnings becomes your deposit.

---

## Try the API in Postman

[postman/Errand.postman_collection.json](postman/Errand.postman_collection.json) is generated from Errand's own OpenAPI spec (`errand postman` rebuilds it), so it always matches the real API. **Import** it, set `base_url` and `api_key` (`errand keys` prints the demo ones), and start with the **Quickstart** folder: delegate a math job, delegate a code job with tests, pin a Runner, check your wallet, top up with PayPal, post a PayPal bounty.

## SDKs and docs portal (APIMatic)

[apimatic/](apimatic) is the source for an APIMatic docs portal, branded for Errand: API reference with a live playground, typed SDKs for Python, TypeScript and C#, a context plugin for coding agents, and `llms.txt` docs. All of it is generated from the same OpenAPI spec. Build it with an APIMatic account:

```bash
npx @apimatic/cli@2 auth login
npx @apimatic/cli@2 portal generate --input=./apimatic --destination=./apimatic/portal
```

---

## Deploy

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sh4shv4t/errand)

[render.yaml](render.yaml) is a one-click Render Blueprint (Docker, free plan). It picks up its public URL automatically and runs 30 demo errands on first boot, so a fresh deploy already has receipts, savings and rankings. Add `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` in the Render dashboard for the PayPal sandbox. Free-plan storage is ephemeral, and the service sleeps after 15 idle minutes (the first visit after that takes about a minute).

---

## CLI

```
errand up                 start and open the dashboard
errand serve [--port]     start the gateway only
errand demo [-n 40]       scripted session with a printed receipt (--villain adds a cheating Runner)
errand bench --model ...  benchmark real models, save numbers for the landing page
errand postman            export a Postman collection generated from the OpenAPI spec
errand connect [client]   wire Errand into MCP clients (or: all, print)
errand keys               show demo API keys
errand reset --yes        delete the local database
errand-mcp                stdio MCP server
```

---

## Built with

| Category | Technologies |
|---|---|
| **Payments** | PayPal Orders v2, Authorizations and Payouts (sandbox) |
| **Gateway** | Python, FastAPI, SQLite, httpx, Pydantic |
| **AI** | Ollama (qwen2.5, qwen2.5-coder, phi3), any OpenAI-compatible endpoint, MCP (Model Context Protocol), OpenAI and Anthropic tool calling |
| **Frontend** | Server-rendered Jinja templates, AG Grid, Geist and Instrument Serif, no build step |
| **Developer tools** | Postman collection, APIMatic portal and SDKs, Render Blueprint, Docker |
| **Demo video** | Playwright, OpenCV, FFmpeg, NumPy (all sound is synthesized, nothing to license) |

---

## Honest limitations

- Demo Runners are **simulated**: they only know the built-in task bank and plain arithmetic, and every one is labelled "(simulated)". Register a real model for anything else.
- Code verification runs in a separate isolated Python process with a timeout. That is a hackathon sandbox, not a security boundary.
- Math errands sent without an expected answer are *delivered*, not verified; their quality signal comes from hidden test questions.
- The frontier-cost baseline per job type is an estimate, not a measurement.
- SQLite with a single gateway process.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Built for the [PayPal AI Hackathon 2026](https://paypalaihackathon.devpost.com/). MIT licensed.

<div align="center"><br><img src="assets/errand-icon.png" width="56" alt=""><br><sub><i>Send your model on fewer errands.</i></sub></div>
