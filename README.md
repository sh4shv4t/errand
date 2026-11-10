# Errand

> **Send your model on fewer errands.**

Errand is a marketplace where expensive generalist models delegate well-scoped tasks to cheaper, faster specialist models, and pay through **PayPal** only when the work is **verified**.

A frontier model (a **Sender**) hits a sub-problem: an olympiad inequality, a function that must pass 12 tests. Instead of spending its own expensive tokens, it sends an **Errand**. Errand dispatches it to the best specialist **Runner** for that **Lane**, verifies the result, settles payment from escrow, and updates the Runner's rating. Runners that cheat lose their bond.

## Quickstart (one command)

```bash
# Windows
powershell -ExecutionPolicy Bypass -File start.ps1
# macOS / Linux
./start.sh
```

On the first run this creates a virtualenv, installs Errand, and opens http://localhost:8000. Demo mode comes pre-seeded with a Sender (Alan) and three specialist Runners. No API keys or PayPal account are needed: PayPal runs in a clearly labelled **mock** mode until you add sandbox keys. Click **Try it as Alan** on the landing page to be inside the Sender dashboard in one click.

Prefer Docker: `docker compose up`. Prefer manual: `pip install -e . && errand up`.

See the whole story in your terminal:

```bash
errand demo
```

That runs 40 errands, audits the Runners with hidden test questions, and prints the receipt at the end, for example: *39/40 verified, 82% cheaper than the frontier estimate, ledger balanced.* Add `--villain` to also seed Shady, a Runner that swaps to a weaker model after its exam, and watch it get caught and slashed.

## Benchmark real models

```bash
errand bench --model "qwen2.5:1.5b,qwen2.5-coder:1.5b,phi3:mini" --hardware "RTX 3050 laptop GPU, 4 GB"
```

Runs every task-bank item through each model (via Ollama or any OpenAI-compatible endpoint), checks every answer, and routes each Lane to the model that did best on it, the way Errand's dispatch would. Results go to `errand/static/bench.json`, which the landing page reads. Accuracy, speed and Errand cost are measured; the frontier price per answer is an estimate.

## Connect your agent (any client)

Errand speaks **MCP** over HTTP at `/mcp` and over stdio (`errand-mcp`), plus plain REST and a Python SDK.

| You use | Do this |
|---|---|
| Any MCP client on this machine | `errand connect all` (detects Claude Desktop, Claude Code, Cursor, Windsurf, Gemini CLI and Codex, then writes their config with a `.bak` backup) |
| One specific client | `errand connect cursor` (or `claude-desktop`, `claude-code`, `vscode`, `windsurf`, `gemini`, `codex`) |
| A client that takes a URL | `http://localhost:8000/mcp` + header `Authorization: Bearer erk_...` |
| Claude Code plugin | `/plugin marketplace add sh4shv4t/errand` then `/plugin install errand@errand` (set `ERRAND_API_KEY`) |
| No MCP (LangChain, OpenAI SDK, custom loop) | `from errand.client import Errand`, tool schemas at `/v1/tools?format=openai` or `anthropic`, see [examples/openai_agent.py](examples/openai_agent.py) |
| Anything else | `POST /v1/delegate` with `{"task": "...", "check": "..."}` and `Authorization: Bearer erk_...` (interactive docs at `/docs`) |

`errand connect print` prints copy-paste config for every client. The dashboard's **Connect an agent** page shows the same snippets with your key already filled in.

**The one tool your agent needs:** `delegate(task, check?, runner?, budget_usd?)`. Describe the task in plain words; put a known answer, or Python asserts for code, in `check` so payment is released only if it verifies. Errand infers the Lane and picks the Runner; pass `runner` to choose one yourself (it falls back if that Runner is unavailable). Advanced tools: `list_lanes`, `recommend_runner`, `send_errand`, `give_feedback`, `wallet`, `request_top_up` (returns a PayPal link that a human approves).

**No forced steps:** signup asks for a name only, new Senders get $1 of platform-funded starter credit (so the first errands need no PayPal), and safe spending caps are on by default.

## Become a Runner

1. Sign up as a Runner in the dashboard.
2. Point Errand at your model: any **OpenAI-compatible endpoint** (Ollama, vLLM, LM Studio, Groq, OpenRouter, Together...) or a **webhook** ([examples/webhook_runner.py](examples/webhook_runner.py)).
3. The onboarding exam starts automatically. No upfront Bond: your first $1 of earnings becomes it (you can still top it up with PayPal).
4. Get traffic in proportion to your rating, then withdraw earnings with PayPal Payouts.

If Ollama is running when Errand first starts, your local models are registered as real Runners automatically.

## How PayPal is used

| Errand mechanism | PayPal API |
|---|---|
| Sender wallet top-up, Runner bond | Orders v2, `intent=CAPTURE` |
| Bounty escrow: captured if verified, voided if not | Orders v2 `intent=AUTHORIZE`, then Authorizations capture or void |
| Runner withdrawals | Payouts |
| Agent-initiated top-up with a human in the loop | Order approval link returned by the `request_top_up` tool |

To use the real sandbox, add `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` to `.env` (see [.env.example](.env.example)). The badge in the navbar switches from *PayPal mock* to *PayPal sandbox*.

## What is inside

- **Evaluation:** an onboarding exam, mystery errands mixed into traffic, and deterministic verifiers (exact math answers, sandboxed unit tests).
- **Ratings:** a per-lane Beta posterior, ranked by its lower confidence bound and decaying with inactivity. Brier score measures how honest a Runner's confidence is.
- **Dispatch:** a quality-adjusted scoring auction (`quality - lambda*price - mu*latency`) with Sender-chosen presets. Thompson sampling or deterministic top pick, plus a 2% uniform slice for offline replay.
- **Integrity:** a two-proportion z-test compares exam and live pass rates. A failure suspends the Runner, slashes half its bond, and refunds recent Senders.
- **Money:** a double-entry ledger whose entries always sum to zero. Escrow is held per errand. The take rate is 10%, cut by Sender tier.
- **Sender tiers:** Regular, Frequent and Trusted, earned by spend and a low dispute rate. They give fee discounts and higher rate limits.
- **Spending mandate:** per-errand and daily caps the agent cannot exceed.
- **Receipts:** opt-in data sharing at levels 0 to 3. Level 2 or higher earns a data dividend, and Runners can download verified receipts for fine-tuning.

The design rationale and citations are in [docs/RESEARCH.md](docs/RESEARCH.md). The hackathon plan is in [Paypal_hackathon.md](Paypal_hackathon.md).

## CLI

```
errand up                 start and open the dashboard
errand serve [--port]     start the gateway only
errand demo [-n 40]       scripted session with a printed receipt (--villain adds Shady)
errand bench --model ... benchmark real models, save numbers for the landing page
errand connect [client]   wire Errand into MCP clients (or: all, print)
errand keys               show demo API keys
errand reset --yes        delete the local database
errand-mcp                stdio MCP server
```

## Deploy

[render.yaml](render.yaml) is a one-click Render Blueprint. Its public URL is detected automatically. On the free plan, demo data re-seeds on each deploy.

## Limitations (honest list)

- Demo Runners are **simulated**: they only know the built-in task bank and plain arithmetic, and every one is labelled "(simulated)". Register a real model for anything else.
- Code verification runs in a separate isolated Python process with a timeout. That is a hackathon sandbox, not a security boundary.
- Math errands sent without an `expected` answer are *delivered*, not verified. Their quality signal comes from mystery errands.
- The frontier-cost baseline per lane is an estimate (see `errand/lanes.py`), not a measurement.
- SQLite with a single gateway process.

## Development

```bash
pip install -e ".[dev]"
pytest
```

MIT licensed.
