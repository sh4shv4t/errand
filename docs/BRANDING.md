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

## Palette options

**Decision (2026-11-10): Forest and Mandarin is the brand palette.** The trios below are potential alternatives, kept for later. Each is a **canvas**, a **primary** (buttons, brand, "verified") and an **accent** (the one thing that moves: dispatch, live, the main call to action). They are defined as token sets at the end of `errand/static/app.css` and can be previewed on any page with `?palette=<key>`; nothing in the product exposes them to users. Contrast ratios are WCAG 2.x, measured.

| Key | Name | Canvas | Primary | Accent | Mood | Contrast notes |
|---|---|---|---|---|---|---|
| *(default, chosen)* | **Forest and Mandarin** | Paper `#F4F0E6` | Forest `#015D47` | Mandarin `#FD550A` | Calm, earthy, trustworthy. Closest to Perplexity's editorial feel. | Forest on paper 6.9:1. Mandarin is a fill, never body text (2.9:1); ink text on it is 4.7:1. |
| `paypal` | **PayPal Blue** | Cloud `#F5F7FA` | Navy `#003087` | PayPal yellow `#FFC439` | Instantly reads as "payments". Strongest fit for a PayPal hackathon. | Navy on canvas 11.0:1, ink on yellow 10.4:1. Inspired by PayPal's colours, not their logo or wordmark; never imply endorsement. |
| `night` | **Night Forest** | Deep forest `#0B2A21` | Mint `#7FD1B0` | Crest `#E0F354` | Dark-first and high energy. Great on stage and in the video. | Paper text on canvas 13.5:1, mint 8.5:1, crest 12.5:1. |
| `ink` | **Ink and Mandarin** | Off-white `#F6F5F1` | Ink `#121212` | Mandarin `#FD550A` | Stark editorial, like a printed receipt. Orange does all the talking. | Ink 17.2:1. Mandarin text uses `#B83F0A` (5.1:1). |
| `ultra` | **Ultramarine and Volt** | Bone `#F1EFEA` | Ultramarine `#2433FF` | Volt `#D7FF3D` | The wild one. Loud, modern, unmistakable. | Ultramarine on bone 6.1:1, white on ultramarine 7.0:1, ink on volt 15.6:1. |
| `clay` | **Teal and Terracotta** | Cream `#FBF9F5` | Teal `#1C6E7A` | Terracotta `#B5502F` | Library-calm. Risk: reads close to Perplexity itself. | Teal 5.6:1, white on terracotta 5.1:1. The highlight colour `#F2C14E` on teal is 3.5:1, so it's for big numbers only. |
| `plum` | **Plum and Peach** | Blush `#F7F1EC` | Plum `#4A1F4F` | Peach `#FF8A5B` | Warm and premium. Stands out among blue and green fintech brands. | Plum 11.7:1, ink on peach 7.3:1. |

**If we revisit:** `paypal` makes the payments story obvious at a glance, `night` records well on video, and `ultra` is the boldest. Forest stays the most distinctive and the calmest. Whatever is chosen, keep the rules from `docs/UI_BRANDING.md`: the canvas covers about 70% of a screen, the primary about 25%, and the accent under 5%.

## Naming conventions

- Repo / package: `errand`
- CLI: `errand send --lane math.competition --budget 0.002 problem.json`
- SDK: `errand.send(...)`, `errand.Runner`, `errand.Lane`
- IDs: `err_01J...` for errands, `run_...` for runners, `rcpt_...` for receipts.

## Alternatives considered

Guild, Referral, Switchboard. Guild had the strongest reputation/ranking story; Errand won for being the most direct description of what a Sender actually does.
