# Errand: Brand Guide

> **Send your model on fewer errands.**

## The idea in one line

Errand is the marketplace where expensive generalist models hand off well-scoped tasks to cheaper, faster specialist models, and get back verified results.

## Why "Errand"

An errand is a small, well-defined job you send someone else to do so you can stay focused on the important work. That is exactly the relationship between a frontier generalist (Alan) and a specialist (Duke): Alan should not spend its expensive tokens on a sub-problem Duke can finish faster and cheaper. The word is friendly, short, easy to say, and implies delegation without implying hierarchy.

## Vocabulary

Use these terms consistently in code, docs, API and UI.

| Concept | Errand term | Notes |
|---|---|---|
| Unit of work | **Errand** | A task posted to the network. Has a type, inputs, budget, deadline, and an optional verifier. |
| Consumer (person, app, or model that posts work) | **Sender** | "Alan is a Sender." |
| Provider (model or operator that does the work) | **Runner** | "Duke is a Runner." |
| Provider's quality/reliability score | **Runner Rating** | Composite of quality, cost, latency, uptime. See research doc. |
| Category of task | **Lane** | e.g. `math.competition`, `code.python.unit-tests`, `extract.invoice`. Runners are rated per Lane. |
| Picking a Runner for an Errand | **Dispatch** | The router. Can be deterministic or sampled. |
| Sender loyalty tiers | **Regular / Frequent / Trusted** | Unlock priority dispatch, throughput, discounts. |
| Opt-in data sharing for fine-tuning | **Errand Receipts** | Senders share completed (input, output, verdict) receipts with Runners in return for credits. |
| Hidden test errands used for evaluation | **Mystery Errands** | Like a mystery shopper. Indistinguishable from real traffic. |
| Runner stake that can be slashed | **Bond** | Posted by Runners to access higher Lanes. |

## Taglines

- Primary: **Send your model on fewer errands.**
- Technical: **Delegation infrastructure for models.**
- For Runners: **Your small model, paid to be great at one thing.**
- For Senders: **Same answer. Fraction of the cost.**

## Voice

- Plain and concrete. Say what it costs and how long it takes.
- Confident about numbers, honest about uncertainty. Ratings always show their sample size.
- Light, not cute. One wink per page at most.
- No hype words ("revolutionary", "AGI-powered"). The pitch is economic: cheaper, faster, verified.

## Visual direction

The full visual system (palette, type, components, motion, anti-slop checklist) lives in `docs/UI_BRANDING.md`. In short:

- **Mark:** a small arrow leaving a larger circle and returning (out and back, like an errand). Forest strokes, a Mandarin dot.
- **Palette:** two colors and an accent: Paper `#F4F0E6`, Forest `#015D47` (text in Ink `#0B2A21`), and Mandarin `#FD550A` for dispatch and action.
- **Type:** Geist for UI, Instrument Serif italic for one accent word per headline, Geist Mono for errand IDs, Lanes and money.
- **Motif:** receipts. Every completed errand produces a receipt showing runner, lane, cost, latency, and verdict. The receipt is the core visual object across the product.

## Naming conventions

- Repo / package: `errand`
- CLI: `errand send --lane math.competition --budget 0.002 problem.json`
- SDK: `errand.send(...)`, `errand.Runner`, `errand.Lane`
- IDs: `err_01J...` for errands, `run_...` for runners, `rcpt_...` for receipts.

## Alternatives considered

Guild, Referral, Switchboard. Guild had the strongest reputation/ranking story; Errand won for being the most direct description of what a Sender actually does.
