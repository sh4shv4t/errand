# Errand: Product Direction (November 2026)

*Written 2026-11-03, after the end-to-end MVP on `feat/end-to-end-mvp`. This doc covers two things: making Errand plug and play, and four feature questions (consensus, Runner claims, pinning a Runner, auto-update). `docs/RESEARCH.md` stays the design source of truth for evaluation, dispatch and integrity. Reference numbers continue from RESEARCH.md ([56] onward).*

---

## 0. TL;DR

| Question | Answer | Build for the hackathon? |
|---|---|---|
| Plug and play | Keep every trust mechanism, make it invisible: one `delegate` tool, starter credit, hosted by default, one-click connect, earned Bonds. | Yes, first. |
| Consensus mode | **Yes, as an opt-in "panel"**, capped at 5 Runners, adaptive (2 first, a third only on disagreement). Not "as many as you want": more votes can make answers *worse*, and models share mistakes. | Yes, math lane only. |
| Runner claims | **Yes, as a weak prior that the exam and live traffic overwrite.** Measured results become a public Runner Card (Markdown). Embeddings come later, learned from our own pass/fail data. | Claims + Runner Card: yes. Embeddings: no. |
| Pick a specific Runner | **Yes, always allowed**, OpenRouter style: pin, allow fallback by default, exclude list. Escrow and verification still apply. | Yes, small. |
| Auto-update | **Yes, mostly by moving logic to the server.** Hosted gateway and remote MCP update on deploy; local clients get a version check and `errand update`. | Yes, small. |

---

## 1. Plug and play

### 1.1 Friction today

- **Sender:** run the gateway locally, sign up, copy a key shown once, run `errand connect` (needs the CLI), approve a PayPal top-up before the first errand (and one more approval per bounty), then face caps, presets, tiers and consent levels 0 to 3. The agent gets six tools and must pick a lane from an enum, shape the payload, know the expected answer, and recover from a 402.
- **Runner:** sign up, register an endpoint as JSON, post a $1 Bond through PayPal before the exam starts (`MIN_BOND` in `errand/integrity.py`), set a PayPal email, withdraw by hand. A laptop model behind NAT cannot receive webhooks.

### 1.2 Principle

**Keep every trust mechanism, but make it invisible.** Escrow, mystery errands, the ledger, tiers and slashing stay. They become defaults nobody has to touch. Pitch line: *"Every errand is escrowed. You never see it."*

### 1.3 Plan

**Tier 1 (small, highest impact)**

1. **One tool:** `delegate(task, check=None, budget_usd=None, runner=None, panel=None)`. The server infers the Lane. `check` is an expected answer or test lines; without it the errand is *delivered*, not verified. The response carries cost and savings; `dry_run=true` replaces `recommend_runner`. Keep `account()` (balance plus top-up link) and optional `feedback()`. Advanced tools move behind a flag.
2. **Starter credit** (for example $1, platform funded, posted to the ledger) so the first errand needs no PayPal step. Ask for money at the moment of value: "you saved $0.40, add funds to keep going".
3. **Hosted by default:** the Render URL is the default `ERRAND_URL`. Senders need no Python.
4. **One-click connect** on `/connect`: Cursor and VS Code MCP install deeplinks, a copyable `claude mcp add --transport http ...` line, and the existing `?key=` URL.
5. **Hide the knobs:** signup asks for a name only; safe defaults for caps, preset and consent; the dashboard opens on a self-ticking checklist (Connected, First errand, Funded).

**Tier 2 (the PayPal story, smoother)**

6. **Approve once, auto-reload:** vault the PayPal payment method (Orders v2 `payment_source.paypal.attributes.vault`) and reload within a mandate, so the agent never sees a 402. *Verify sandbox vault behavior before building; fall back to the current link flow plus starter credit.*
7. **Bounties become an option**, kept for the demo and for big errands. Normal errands use ledger escrow with no extra approval.
8. **Earned Bond:** new Runners start on probation with a small traffic share; early earnings are held until they reach `MIN_BOND`, and slashing takes from that. Then auto-payout above a threshold.

**Tier 3 (stretch)**

9. **Pull-based Runners:** `errand run --model ollama/...` long-polls `/v1/runner/next`, so a laptop model with no public URL can join with one command.
10. **MCP OAuth with Log in with PayPal**, so there is no key to copy. Most elegant, riskiest in the time left.

---

## 2. Consensus mode ("panel")

### 2.1 What the research says

- **More votes is not always better.** Chen et al. [56] study majority voting over repeated LLM calls and find accuracy *first rises, then falls* as the number of calls grows: voting helps on easy items and hurts on hard ones, where the wrong answer is the popular one. They fit a scaling law to pick the best number of calls from a small sample.
- **Mixing models can hurt.** Li et al. [57] ("Rethinking Mixture-of-Agents") find that aggregating samples from the single best model beats mixing different models in most settings they tested (+6.6% on AlpacaEval 2.0, +3.8% on average across MMLU, CRUX and MATH), because weaker members drag the average down. They also name settings where mixing helps. The original Mixture-of-Agents result [8] is the optimistic counterpoint.
- **Models make the same mistakes.** Kim et al. [58] find that when two models are both wrong, they pick the *same* wrong answer about 60% of the time on HELM MMLU data, and the correlation is *higher* for more accurate models, even after controlling for shared developer or architecture. Five correlated votes are worth far fewer than five independent ones. (Their data is multiple choice; open-ended answers may behave differently.)
- **Code has a better tool than voting.** For code, candidates can be clustered by behavior (run them on shared inputs and group those that agree), as in CodeT [59], instead of comparing text.

### 2.2 Recommendation

**Build it, but as a bounded, adaptive panel, not "pick as many as you want".**

- **Size:** 3 by default, maximum 5, always odd. The cap is honest product design, not a limitation: [56] and [58] say more votes past a point add cost and correlated error, not accuracy.
- **Adaptive, to save money:** ask 2 Runners first. If they agree, stop. If not, add a third (up to the cap). Most easy items finish at 2 calls.
- **Diversity over count:** prefer Runners with different declared base models (we store `declared_model`), since shared lineage drives correlated errors [58]. Optionally offer "best Runner, sampled 3 times" as a panel type, following [57].
- **Where it matters most:** lanes or errands **without a verifier** (a math errand sent with no `expected`). There, agreement is the only quality signal we have. When a verifier exists, the verifier decides; use a *race* (first verified pass wins, cancel the rest) instead of a vote.
- **Aggregation per lane:**
  - `math.final-answer`: majority over normalized answers (the lane already extracts and normalizes).
  - `code.python.tests`: with tests, any passing candidate. Without tests, behavioral clustering [59], pick the largest cluster.
  - Free-text lanes (future): an LLM aggregator in the MoA style [8][57]. Out of scope for verifiable lanes.
- **Output:** the answer plus `agreement: "2/3"` and the dissenting answer, so the Sender's model can decide whether to trust it. Never call consensus "verified": it is *agreed*, a separate verdict.

### 2.3 Money and incentives

- **Pay every panel member its price.** Each one did the work. Paying only the majority creates herding: Runners would learn to guess the popular answer instead of the right one (a beauty-contest incentive), and colluding Runners could coordinate.
- **Do not update Runner Ratings strongly from consensus.** Consensus is not ground truth (correlated errors [58]). Treat agreement as a weak signal; mystery errands stay the strong one (RESEARCH.md section 4).
- **Price:** quote the expected cost up front (2 to 3 times a single errand), within the Sender's per-errand cap.
- **API:** `delegate(..., panel=3)` or `panel={"size": 3, "diverse": true}`.

---

## 3. Runner claims and capability profiles

### 3.1 What the research says

- **Self-reported numbers are unreliable.** Contamination inflates benchmark scores by roughly 6% to 40% depending on the setting, and no detection method is reliable across settings [60]. Vendor-reported scores often fail to replicate under a fixed harness, and under-specified evaluation setups alone produce large spreads [61]. A claim is cheap talk until it is measured.
- **Learned model embeddings work for routing.** EmbedLLM [62] learns one compact vector per model from a (model x question) correctness matrix. It beats earlier methods at routing in accuracy and latency, predicts benchmark scores without extra inference, and its vectors reveal traits like "good at code" without being told. RouteLLM's matrix-factorization router [4] uses the same recommender-system idea and reports 95% of GPT-4 quality with 26% of GPT-4 calls.
- **We already collect exactly that matrix.** The `attempts` table records (Runner, Lane, task, passed) for exam, mystery and live errands.

### 3.2 Recommendation

**Accept claims, use them as a weak prior, and replace them with measurements as fast as possible.** Phase it:

**Phase 1 (hackathon): claims as a prior, plus a Runner Card.**
- At registration a Runner states claims in structured form: Lanes, optional sub-skills (tags such as `math.algebra`, `math.geometry`), and optionally a benchmark number with its source.
- Each claim becomes a Beta prior worth a small, fixed number of pseudo-observations (for example 5), and never more than the onboarding exam's weight. Live data overwhelms it within a few dozen errands. Thompson sampling (RESEARCH.md 5.2) then routes exploration traffic toward claimed strengths first, which is the cold-start help you want.
- The exam tests the claim directly, and the **gap between claimed and measured** is shown publicly. Big overclaims cost reputation, scored like calibration (a proper scoring rule, RESEARCH.md 7.2). That makes honest claims the best strategy.
- **Runner Card:** an auto-generated Markdown page per Runner: claims, measured pass rate per Lane and tag with sample sizes, price, p95 latency, claim-versus-measured gap, Bond, swap-check status. It is readable by humans and by the Sender's model (return it from `recommend`). Claims are written by the Runner; the Card is written by Errand.
- Optional **bonded claims**: a claim backed by extra Bond that is slashed if the measured rate falls far below it. This reuses the existing slashing code.

**Phase 2 (after launch): tags inside Lanes.** Tag task-bank items and live errands by sub-skill (a cheap classifier), and keep a Beta posterior per (Runner, tag). This is most of the routing value at low complexity.

**Phase 3 (with data): embeddings.** Learn Runner vectors and query vectors from the `attempts` matrix (EmbedLLM [62] or matrix factorization [4]), and route by predicted pass probability for *this* query. Cold-start a new Runner's vector from its claim text embedding until it has enough attempts. Keep the LCB rule on top so uncertainty still matters. Do not build this before there are thousands of graded attempts per Lane; it will overfit.

**Markdown or vector?** Both, for different readers: the **Card (Markdown) is the explanation**, the **vector is the router's internal state**. Never route on the Runner's own text alone.

---

## 4. Letting the Sender pick the Runner

### 4.1 What the industry does

OpenRouter, the closest incumbent, lets a caller pin providers with `order`, restrict with `only`, skip with `ignore`, and set `allow_fallbacks` (default `true`); with no preferences it routes on price, throughput, latency and reliability [63]. Pinning is a normal, expected control.

### 4.2 Recommendation

**Yes, always allow it.** Developers will not adopt a router they cannot override, and debugging needs it.

- **API:** `delegate(..., runner="duke-math")` pins; `fallback=true` by default lets Dispatch retry another Runner if the pinned one is down, over budget or fails verification; `exclude=[...]` skips Runners. Also allow pinning by **model** (`model="qwen2.5-math-1.5b"`) across every Runner serving it; swap detection is what makes that safe.
- **Escrow, verification and the mandate still apply.** Pinning changes who runs the errand, not how it is paid.
- **Fail clearly:** a pinned Runner that is suspended, slashed or over budget returns a clear error (or falls back, if allowed). Never route a pinned errand to a suspended Runner.
- **Data hygiene:** log `policy="pinned"`. Pinned errands are not random exploration, so exclude them from off-policy replay (or log propensity 1). They still feed ratings through the verifier.
- **Disintermediation:** pinning makes going direct easy. What still keeps a Sender on Errand after pinning is escrow, verification, swap detection, fallback and PayPal settlement. That is the real product, and it belongs in the pitch.

---

## 5. Auto-update

### 5.1 Errand's update surfaces

| Surface | How it updates today | Plan |
|---|---|---|
| Hosted gateway + dashboard (Render) | On every deploy | Already automatic. |
| Remote MCP (`/mcp`) | Served by the gateway, so updates on deploy | Declare `tools.listChanged` and send `notifications/tools/list_changed` when tools change [64]. Client support varies; one report says Claude Code handles it from v2.1.0 [64]. Others may need a reconnect. |
| Local CLI and stdio `errand-mcp` | Manual `pip install` | Version check and `errand update` (below). |
| Claude Code plugin | Third-party marketplaces do not auto-update by default; a `version` in `plugin.json` that is not bumped keeps users on the old copy [65] | Bump `version` on every release (or omit it so the git SHA is used), and tell users to enable auto-update for the marketplace. |
| Runner protocol (webhook, OpenAI-compatible, future pull) | Fixed | Version the protocol (`errand_protocol: 1`), support the previous version for one release. |

### 5.2 Recommendation

1. **Move logic to the server, keep clients thin.** Today `errand/mcp_server.py` defines tools with decorators and `errand/tools.py` hardcodes the Lane enum, so adding a Lane needs a client update. Instead, have stdio `errand-mcp` fetch tool definitions from `/v1/tools` at startup, and drop client-side enums (the server validates). Then most updates ship with a deploy and only the thin transport ever changes.
2. **Version handshake.** `/v1/config` already returns `version`. Add `latest_client` and `min_client`. Clients print a one-line hint when behind, and refuse with a clear message when below `min_client`.
3. **`errand update`** runs `pip install -U` from the official source. It is user-initiated, prints the version change, and never runs silently in the background. Code updating itself on a user's machine is a trust problem; keep the human in the loop, and later ship signed releases.
4. **API stability.** Keep `/v1` backward compatible. Breaking changes go to `/v2`, and `/v1` responses get a `Deprecation` header first.
5. **Feature flags for behavior we may change often** (mystery rate, take rate, panel cap) live server side, which `config.py` mostly does already.

---

## 6. Build order (deadline 2026-11-12)

1. Tier 1 plug and play (section 1.3, items 1 to 5), including `runner=` pinning (section 4) and server-driven tools plus the version check (section 5, items 1 and 2), since all three touch the same tool and client code.
2. Runner claims as prior plus Runner Card (section 3, phase 1).
3. Panel mode for `math.final-answer` (section 2).
4. Tier 2 money items (section 1.3, items 6 to 8) as time allows.
5. Freeze, record the video.

---

## References (continuing RESEARCH.md)

- [56] Chen, Davis, Hanin, Bailis, Stoica, Zaharia, Zou. *Are More LLM Calls All You Need? Towards the Scaling Properties of Compound AI Systems.* NeurIPS 2024. https://arxiv.org/abs/2403.02419
- [57] Li, Lin, Xia, Jin. *Rethinking Mixture-of-Agents: Is Mixing Different Large Language Models Beneficial?* 2025 (TMLR). https://arxiv.org/abs/2502.00674
- [58] Kim, Garg, Peng, Garg. *Correlated Errors in Large Language Models.* ICML 2025. https://arxiv.org/abs/2506.07962
- [59] Chen et al. *CodeT: Code Generation with Generated Tests.* ICLR 2023. https://arxiv.org/abs/2207.10397
- [60] Systematic review of LLM benchmark contamination (inflation estimates of about 6% to 40%), and the Llama-2 contamination analysis. https://arxiv.org/abs/2310.17589 *(secondary summary; read the original before quoting numbers)*
- [61] *What Twelve LLM Agent Benchmark Papers Disclose About Themselves: A Pilot Audit and an Open Scoring Schema.* 2026. https://arxiv.org/abs/2605.21404
- [62] Zhuang et al. *EmbedLLM: Learning Compact Representations of Large Language Models.* ICLR 2025. https://arxiv.org/abs/2410.02223
- [63] OpenRouter, Provider Routing docs. https://openrouter.ai/docs/features/provider-routing
- [64] MCP tools `listChanged` and `notifications/tools/list_changed`, and client support notes. https://www.seuros.com/blog/tools-list-changed-bug-not-feature/ *(secondary; check the spec version you target)*
- [65] Claude Code docs, plugin marketplaces and auto-update. https://code.claude.com/docs/en/discover-plugins
