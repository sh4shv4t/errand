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

## Conventions

- Commit messages use Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`.
- No em dashes or double-hyphen dashes in any written output.
- Planned stack: Python (FastAPI), Postgres, Redis, Python SDK first.
