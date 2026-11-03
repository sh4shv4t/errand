# Errand: project context

Errand is a two-sided marketplace for model-to-model delegation. Expensive generalist models (Senders) post well-scoped tasks (Errands) that cheaper specialist models (Runners) complete, per task category (Lane). The platform evaluates, dispatches, verifies, settles, and ranks.

## Read first

- `docs/RESEARCH.md`: the design source of truth. Landscape, evaluation, dispatch, Sender tiers, Runner Ratings, Receipts (data sharing), game theory threat model, verification layers, business model, MVP roadmap, and cited references.
- `docs/BRANDING.md`: name, tagline, voice, and the required vocabulary.
- `docs/UI_BRANDING.md`: visual system (Paper, Forest, Mandarin), typography, components, motion, anti-slop checklist.
- `docs/PRODUCT_DIRECTION.md` (2026-11-03): plug-and-play plan, plus decisions on consensus panels, Runner claims and Runner Cards, Sender pinning, and auto-update, with the build order to the hackathon deadline.

## Vocabulary (use consistently in code, API, docs)

Errand (unit of work), Sender (consumer), Runner (provider), Lane (task category), Dispatch (routing), Runner Rating, Mystery Errand (hidden eval task), Receipt (completed errand record, opt-in shareable), Bond (slashable Runner stake). Sender tiers: Regular, Frequent, Trusted.

## Key design decisions so far

- Start with verifiable lanes only: `math.final-answer`, `code.python.tests`, `extract.json-schema`.
- Quality = lower confidence bound of a per-(Runner, Lane) Beta posterior, mystery errands weighted highest; uncertainty grows with inactivity.
- Dispatch scores `Q - lambda*price - mu*latency_p95` with Sender-set weights; deterministic (`top`) and Thompson-sampling modes; log ~1% uniform-random dispatch for offline replay.
- Runner confidence is scored with a proper scoring rule (Brier/log).
- Escrow: Runners are paid on verified success.
- Priority is priced by queue externality, not given free; reserve capacity for small Senders.
- Receipts are opt-in (levels 0 to 3), default private, credited by measured value.
- Centralized evaluation first; keep interfaces open to decentralizing later.
- Expose Errand as an MCP server (`send_errand`, `recommend_runner`) so models can delegate natively.
- Plug and play: keep trust mechanisms (escrow, mystery errands, slashing) but make them invisible; default surface is one `delegate` tool, starter credit, hosted gateway, one-click connect.
- Consensus is an opt-in panel, capped at 5, adaptive (2 then a tie-breaker); every member is paid; agreement is a weak rating signal, never "verified".
- Runner claims are a weak Beta prior (a few pseudo-observations); measurements replace them; Errand publishes a Markdown Runner Card. Embedding routing only once data exists.
- Senders can always pin a Runner or model (fallback on by default); escrow and verification still apply; pinned errands are logged as `policy="pinned"`.
- Updates ship server side: thin clients fetch tools from `/v1/tools`, version handshake via `/v1/config`, user-initiated `errand update`.

## Code map (MVP, branch feat/end-to-end-mvp)

- `errand/service.py`: errand lifecycle, escrow, PayPal flows, read models. Start here.
- `errand/integrity.py`: onboarding exam, mystery errands, swap detection and slashing.
- `errand/dispatch.py`, `errand/ratings.py`, `errand/tiers.py`, `errand/lanes.py`, `errand/taskbank.py`.
- `errand/ledger.py`: double-entry ledger; amounts are integer micro-dollars.
- `errand/paypal.py`: Orders v2 / Authorizations / Payouts, with a mock twin when no sandbox keys are set.
- `errand/app.py`: REST API (`/v1`), PayPal return handlers, dashboard pages, remote MCP at `/mcp`.
- `errand/mcp_server.py` (stdio + HTTP), `errand/connect.py` (`errand connect`), `errand/client.py` (SDK), `errand/tools.py` (schemas).
- `errand/templates`, `errand/static`: server-rendered dashboard, AG Grid from CDN, no build step.
- `plugin/` + `.claude-plugin/marketplace.json`: Claude Code plugin.
- Tests: `pytest` (core, API, integrations). Demo: `errand demo`.

## Conventions

- Commit messages use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- No em dashes or double-hyphen dashes in any written output.
- Planned stack: Python (FastAPI), Postgres, Redis, Python SDK first.
