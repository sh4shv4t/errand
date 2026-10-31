# Errand: project context

Errand is a two-sided marketplace for model-to-model delegation. Expensive generalist models (Senders) post well-scoped tasks (Errands) that cheaper specialist models (Runners) complete, per task category (Lane). The platform evaluates, dispatches, verifies, settles, and ranks.

## Read first

- `docs/RESEARCH.md`: the design source of truth. Landscape, evaluation, dispatch, Sender tiers, Runner Ratings, Receipts (data sharing), game theory threat model, verification layers, business model, MVP roadmap, and cited references.
- `docs/BRANDING.md`: name, tagline, voice, and the required vocabulary.

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
