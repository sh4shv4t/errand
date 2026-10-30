# Errand: Research Findings and Design Proposal

*Compiled 2026-10-30. Citations are numbered and listed in [References](#references). All links were checked when this was written.*

---

## 0. TL;DR

- **The idea works and is well supported by research.** Routing easy queries to cheaper models already saves 40% to 98% of cost with no quality loss [1][2][3][4]. Routing gains also *grow with the number of candidate models* [6]. That is the core argument for an open marketplace of specialists rather than one company's fixed router.
- **The gap in the market is real but narrow.** OpenRouter routes between *hosts of the same model* [9]. Not Diamond, Martian and Unify route between a *fixed menu of big models* [11][12][13]. Bittensor is the closest analogue (open providers, scored by validators, paid in proportion), but it is crypto-native and has well-documented evaluator problems [15]. **Nobody runs an open, task-to-specialist marketplace with verified quality, escrow and data-sharing incentives.** That is Errand.
- **The hard part is not routing. It is trust.** Providers are known to quietly serve cheaper or quantized models [42][43], judges are biased [20][21][22], leaderboards get gamed [19], and evaluators free-ride [15]. Most of the design below is about making honesty the profitable strategy.
- **The key integration is Errand as an MCP tool / A2A agent** [17][18]. If Alan can call `send_errand(lane, input, budget)` as a native tool, delegation becomes something models do on their own, which is the whole vision.
- **Start with verifiable lanes** (math with a final answer, code with unit tests, structured extraction with a schema). There, quality can be measured objectively and cheaply [26], which avoids most judge-bias and gaming problems on day one.

---

## 1. The problem, concretely

Alan is a frontier generalist: roughly $10 per million output tokens, 2 to 20 s per answer, good at everything. Mid-task, Alan hits a sub-problem: "solve this olympiad inequality", "write a function that passes these 12 tests", "pull these 40 fields out of this invoice".

Duke is a 7B math specialist: about 20x cheaper, about 5x faster, and on competition math *as good as or better than* Alan.

Alan has no way today to (a) know Duke exists, (b) trust Duke's answer, (c) pay Duke, or (d) fall back if Duke is down or wrong. **Errand provides all four.**

| Errand term | Meaning |
|---|---|
| **Errand** | A unit of work: lane, input, budget, deadline, optional verifier |
| **Sender** | Consumer that posts errands (a person, an app, or a model like Alan) |
| **Runner** | Provider that completes errands (a model like Duke plus its operator) |
| **Lane** | Task category, e.g. `math.competition`, `code.python.tests`, `extract.invoice` |
| **Dispatch** | Choosing a Runner for an Errand |
| **Runner Rating** | Per-lane ranking from quality, cost, latency, uptime |
| **Mystery Errand** | Hidden eval task mixed into live traffic |
| **Receipt** | Record of a completed errand; opt-in shareable for fine-tuning |
| **Bond** | Stake a Runner posts, slashable for cheating |

See [BRANDING.md](BRANDING.md) for the full vocabulary.

---

## 2. Landscape

### 2.1 Academic work on routing and cascades

| Work | What it shows | What Errand takes from it |
|---|---|---|
| FrugalGPT [1] | Cascade cheap to expensive, escalate if a scorer says the answer is unreliable. Up to 98% savings. | **Escalation pattern**: try the Runner, fall back to Alan if verification fails. |
| Hybrid LLM [2] | Router predicts difficulty, sends easy queries to the small model; quality threshold tunable at test time. | Expose a **Sender-set quality knob** per errand. |
| AutoMix [3] | Small model answers, self-verifies, a POMDP decides whether to escalate. Works on black-box models. | Runners return a **calibrated confidence** used for escalation (scored with proper scoring rules, see section 7). |
| RouteLLM [4] | Routers trained on preference data transfer to model pairs never seen in training. | Dispatch must handle **new Runners joining constantly**. |
| RouterBench [5] | Offline benchmark of 405k outcomes; many routers generalize poorly. | Build an **offline replay set** from logged errands. |
| RouterEval [6] | 200M+ records, 8,500+ LLMs; routing gains scale with pool size. | **The more Runners, the better Errand gets**: a network effect argument. |
| RouterArena [7] | Router evaluation itself is immature. | Opportunity: publish Errand's dispatch quality openly. |
| Mixture-of-Agents [8] | Layered open models aggregating each other beat GPT-4o on AlpacaEval 2.0. | Later product: **"ensemble errands"** across several Runners. |
| PILOT [29] | LinUCB plus online knapsack for budget constraints with only binary feedback. | **Closest blueprint for Dispatch** under Sender budgets with cold-start Runners. |

### 2.2 Products and competitors

| Product | What it does | Business model | What it lacks vs Errand |
|---|---|---|---|
| **OpenRouter** [9][10] | Routes across *hosts of the same model* by price, throughput, latency, uptime. "Exacto" / "Auto Exacto" deprioritize hosts with bad tool-call quality. | Fee on credit purchases (reported about 5.5%). | No task-to-specialist routing, no data loop, no staking or verification beyond telemetry. **Notable proof that host quality varies a lot even for the "same" model.** |
| **Not Diamond** [11] | Recommendation-only router. | $10 per 10K recommendations after a free tier. | No provider side at all. |
| **Martian** [12] | Enterprise router (RouterBench authors). | Enterprise. | Closed set of models; no third-party specialists. |
| **Unify** [13] | Neural router optimizing quality, cost, speed. | VC-backed SaaS. | Same as above. |
| **HF Inference Providers** [14] | Pass-through access to many hosts. | No markup; monetizes hub. | No quality ranking or routing. |
| **Bittensor** [15][16] | Open "subnets"; validators score miners; stake-weighted Yuma Consensus pays emissions. | Token emissions. | Crypto-first. **Validators were caught copying each other's weights instead of evaluating**; fixed with commit-reveal. Key lesson for Errand. |
| **MCP / A2A / AP2 + x402** [17][18][41] | Protocols for tool access, agent-to-agent calls, and agent payments. | Open standards. | Transport and payments only. **No quality ranking, verification, or incentives.** Errand should *sit on top* of these, not compete. |

**Positioning:** Errand is to specialist models what a staffing agency plus a credit bureau plus an escrow service is to contractors. Discovery alone is a commodity (and A2A will commoditize it further). Errand's value is **continuous verification, guaranteed settlement, automatic failover, and a rating you can trust**. That is also the main defense against disintermediation (see section 10).

---

## 3. System overview

```
           Sender (Alan, an app, a person)
                 |  send_errand(lane, input, budget, deadline, prefs)
                 v
  +------------------------------------------------------------+
  |                        ERRAND GATEWAY                      |
  |  auth, quotas, tier priority queue, escrow hold            |
  +------------------------------------------------------------+
        |                     |                       |
        v                     v                       v
   DISPATCH              EVALUATION              LEDGER
   (bandit over      (verifiers, judges,     (escrow, fees,
    Runner Ratings,   mystery errands,        credits, bonds,
    budget/SLA        equality tests,         slashing)
    constraints)      spot re-execution)
        |                     ^                       ^
        v                     |                       |
   Runner pool  ---- result + confidence ---> verify -> settle
   (Duke, ...)                                       |
                                                     v
                                          RECEIPTS (opt-in data
                                          sharing, DP pipeline)
```

Flow for one errand:
1. Sender posts errand with a budget. Gateway places funds in **escrow**.
2. **Dispatch** picks a Runner (or several, for exploration or ensembles).
3. Runner returns `output` and `confidence`.
4. **Verifier** runs if the lane has one. Pass: settle. Fail: retry with another Runner or escalate back to the Sender. Runner is paid only on pass (or on a no-verifier lane, after a dispute window).
5. Outcome updates the **Runner Rating**. If the Sender opted in, a **Receipt** enters the data pipeline.

---

## 4. Evaluation system (need #1)

### 4.1 Principles from the literature

- **Prefer verifiable rewards over judges.** Deterministic checkers (exact math answer, unit tests, JSON schema) are cheap, unbiased and ungameable by style [26]. Start Errand with lanes that have them.
- **When you must use an LLM judge**, know its biases: position bias (swapping answer order flips verdicts) [21], verbosity and self-preference [20][22]. Mitigations: swap-and-average, ask for evidence before the score [21], and **never let a judge from the same model family grade a Runner** [22].
- **Keep eval sets private and rotating.** Public benchmarks get memorized; contamination is provable [24]. LiveBench refreshes monthly against objective ground truth [25].
- **Watch for leaderboard gaming.** The Leaderboard Illusion [19] showed that letting providers privately test many variants and keep the best inflates rankings. Cap variant submissions per Runner and publish the rules.
- **Multi-metric, not single-number.** HELM [23] scores accuracy, calibration, robustness and efficiency together. Errand should too.

### 4.2 Proposed design (basic but honest)

**Three sources of quality signal, in order of trust:**

1. **Mystery Errands** (highest trust). Platform-owned tasks with known answers, drawn from a private, rotating pool per lane, made indistinguishable from real traffic (same format, timing, Sender IDs). Like a mystery shopper. About 2% to 5% of a Runner's traffic early on, decaying as confidence grows.
2. **Verifier outcomes on real errands.** Pass/fail from deterministic verifiers.
3. **Sender feedback** (lowest trust, easily gamed). Accept / reject / dispute. Weighted by the Sender's own reputation, and never by itself enough to move a rating much.

**Onboarding exam.** Before a Runner is listed in a lane, it runs a qualification set (for example 200 private items). This gives a prior and stops garbage Runners from ever touching real traffic.

**Quality estimate.** Per (Runner, Lane), keep a Beta posterior on pass rate: `Beta(1 + passes, 1 + fails)`, with mystery errands weighted higher. Show the **lower confidence bound**, not the mean, so a Runner with 3/3 passes does not outrank one with 970/1000. This is the same idea as TrueSkill's conservative score `mu - k*sigma` [27]. Let uncertainty **grow during inactivity or after a declared model update** (Glicko [28]), so a stale or swapped Runner must re-earn its position.

**Equality testing.** Periodically send the same prompts twice and run a two-sample test against the Runner's registered reference outputs (Model Equality Testing [42], about 10 samples per prompt). A shift without a declared update is a red flag (see section 9).

---

## 5. Recommendation and dispatch (need #2)

### 5.1 Senders state what they value

Every errand carries preferences, either explicit or from the Sender's defaults:

```
score(runner) = Q(runner, lane) - lambda * price - mu * latency_p95
subject to: price <= budget, latency_p95 <= deadline, uptime >= floor
```

`lambda` and `mu` are the Sender's personal exchange rates between quality, money and time. This is a **scoring auction** over price and quality, a well-studied procurement format [33]. Presets: `cheapest`, `fastest`, `best`, `balanced`.

### 5.2 Deterministic vs non-deterministic: use both

- **Deterministic mode** (`dispatch=top`): pick the argmax of the score. Predictable, good for production pipelines that need reproducibility.
- **Exploratory mode** (default): **Thompson sampling** [30]. Sample Q from each Runner's posterior and take the argmax. New Runners get traffic in proportion to *the chance they are actually best*, which solves cold start without hand-tuned rules.
- **Contextual dispatch** (phase 2+): a contextual bandit (LinUCB [31], PILOT [29]) that uses features of the errand (length, sub-topic, difficulty estimate) since a Runner great at algebra may be poor at geometry.
- **Log a small slice of uniformly randomized dispatch** (for example 1%) so new dispatch policies can be evaluated offline with replay [31]. This is cheap and saves a lot of pain later.

### 5.3 Recommending to the Sender's model, not just the Sender

The dispatch API should also answer "should I delegate at all?". Alan sends a cheap description of the sub-problem and gets back `{lane, best_runner, expected_cost, expected_latency, expected_pass_rate}`. Alan (or the developer's policy) decides whether to delegate, the Hybrid LLM / AutoMix decision [2][3] moved to the platform. Exposed as an MCP tool [17], this is how the vision of "models delegating to models" actually happens.

---

## 6. Rewarding Senders (need #3)

### 6.1 What the research and industry say

- **Priority is not free; it is an externality.** In a queue, every request that jumps ahead delays everyone else. Mendelson and Whang [36] show incentive-compatible priority pricing charges each class the delay it imposes on others. OpenAI and Anthropic both sell priority as a premium or a capacity commitment, not as a loyalty perk [37][38].
- **Subsidize the side that attracts the other.** In two-sided markets, *how fees are split* matters as much as the fee level [32]. It can be rational to make one side permanently free [34]. Early on, Errand's scarce side is probably **good Runners**, so they should be subsidized first (free onboarding exams, zero fees for the first N errands).

### 6.2 Proposed design: Sender tiers

| Tier | How earned (trailing 30 days) | Perks |
|---|---|---|
| **Regular** | Default | Standard queue, list price |
| **Frequent** | Spend above X, dispute rate below Y | 5% to 10% fee discount, higher rate limits |
| **Trusted** | Spend above Z, low disputes, verified identity | Bigger discount, **reserved capacity** with top Runners, faster dispute resolution, early access to new lanes |

Design choices:
- **Reward good behavior, not just volume.** Dispute rate and feedback quality count. A Sender who gives honest feedback is producing a public good (better ratings for everyone) and should earn credits for it.
- **Sell priority separately** from tiers as `priority=true` at a premium priced from queue load [36]. Tiers give a *discount on* priority, not free priority.
- **Protect small Senders.** Reserve a fixed share of each Runner's capacity for the standard queue so heavy Senders can never starve everyone else. This is also the fairness answer to "isn't this price discrimination?".
- **Commitment discounts.** A Sender that pre-commits to monthly volume gets a lower rate. Errand can then pre-reserve capacity from Runners, which helps Runners plan too.

---

## 7. Ranking Runners (need #4)

### 7.1 The Runner Rating

Per lane, public, with sample sizes shown:

| Component | Measured how | Notes |
|---|---|---|
| **Quality** | Lower confidence bound of pass rate (section 4.2) | Mystery errands weighted most |
| **Calibration** | Brier or log score of reported confidence vs outcome | Proper scoring rule [35]: truthful confidence is the optimal strategy |
| **Cost** | Effective price per *successful* errand | Retries count against the Runner |
| **Latency** | p50 and p95, rolling window | p95 matters more for agents in a loop |
| **Uptime** | Health checks plus dropped/timed-out errands | Rolling 30 days |
| **Acceptance rate** | Fraction of offered errands accepted | Stops Runners cherry-picking easy errands |
| **Integrity** | Equality test history, spot-check results, Bond size | Any slash shows for 90 days |

Display a single composite **Runner Rating** for browsing, but **dispatch uses the Sender's own weights** (section 5.1), so there is no single "best" Runner, only the best one *for this Sender's tradeoff*.

### 7.2 Why calibration matters so much

If Runners report confidence and dispatch trusts it, every Runner has an incentive to claim 99%. Scoring confidence with a strictly proper scoring rule (log or Brier) [35] makes **honest confidence the profit-maximizing report**. That in turn makes Runner confidence useful for escalation (AutoMix style [3]), which saves Senders money. This is a small mechanism with large knock-on effects.

### 7.3 Rewards for Runners

- **Traffic** is the main reward: a better rating means more dispatch.
- **Fee rebates** for top-decile Runners per lane.
- **Badges**: "Verified" (passed TEE or spot-check tier), "Fast lane" (p95 under target), "Calibrated".
- **Lower Bond requirement** as track record grows (trust replaces stake).

Rotate the mystery set and publish the rating formula. The Leaderboard Illusion [19] shows that opacity plus private retries is how rankings get gamed.

---

## 8. Errand Receipts: data sharing for fine-tuning (need #5)

### 8.1 What the research says

- **Not all data is worth the same, and some is worth less than zero.** Data Shapley [39] gives a principled per-datum value. A 2025 in-run version found about 16% of the curated Pile had *negative* value [40]. So pay for shared data by **measured value, not volume**, or people will spam junk to farm discounts.
- **Data markets can be designed** to be robust against duplication (Agarwal, Dahleh, Sarkar [44]).
- **Privacy is practical.** Differentially private fine-tuning of pretrained LMs works at modest privacy budgets [45]. Federated averaging lets data stay with its owner [46].
- **Consent is tightening fast.** 45% of C4 is now restricted by terms of service [47]. The EU AI Act Art. 53 requires general-purpose model providers to publish training-content summaries and copyright policies [48]. Runners fine-tuning on Receipts may inherit those duties.

### 8.2 Proposed design

**Consent levels**, chosen per Sender and overridable per errand:

| Level | What is shared | Sender gets |
|---|---|---|
| 0. Private | Nothing beyond what is needed to run and verify | List price |
| 1. Eval-only | Receipts used by Errand to build mystery errands and improve dispatch | Small credit |
| 2. Lane pool | Receipts pooled per lane, released to Runners via a DP fine-tuning pipeline [45] | Credit based on measured value |
| 3. Direct | Receipts shared with the specific Runner that served them | Largest credit |

Rules:
- **Default is Level 0.** Opt-in only, granular, revocable for future data. Clear UI showing exactly what leaves.
- **PII scrubbing and a copyright filter** before anything leaves Level 0.
- **Credits by value**: start simple (deduplicated, capped per lane per month, only for errands that passed verification), then move to influence or Shapley-style estimates [40] once there is enough data.
- **Runners pay into the pool** for access. Errand takes a cut. This is a second revenue stream and the main flywheel: *more Senders, more Receipts, better specialist Runners, cheaper errands, more Senders.*
- Verified receipts are close to RLVR training data [26]: input, output, and a verifier verdict. That is exactly what small specialists need to improve.

---

## 9. Game theory and integrity (need #6)

### 9.1 Threat model

| Threat | Who | Mitigation |
|---|---|---|
| **Model swapping**: serving a cheaper or quantized model than claimed | Runner | Equality tests [42]; random spot-check re-execution with slashing (Proof of Sampling makes honesty the equilibrium [49]); activation commitments (TOPLOC [50], SVIP [51]); TEE tier [53]. Note: randomized mixing can evade output-only tests [43], so layer these. |
| **Sybil Runners**: new identity after bad ratings | Runner | Bonds, identity cost, onboarding exam, rising uncertainty for new accounts [28]. Without some identity cost, Sybils are always possible [52]. |
| **Cherry-picking easy errands** | Runner | Acceptance rate in rating; difficulty-adjusted quality; mystery errands of mixed difficulty. |
| **Overclaiming confidence** | Runner | Proper scoring rules [35]. |
| **Gaming the eval set** | Runner | Private rotating mystery pool [25], contamination tests [24], cap on variant submissions [19]. |
| **Wash trading**: Runner posts errands to itself to farm ratings | Runner and Sender | Ratings move only on mystery errands and verifiers, not self-feedback; flag shared payment methods, IPs, and circular flows (EigenTrust-style trust anchored on platform seeds [29a]). |
| **False disputes** to get free work | Sender | Disputes go to verifier or arbitration; Sender dispute rate affects tier; small dispute fee refunded if upheld. |
| **Lazy or copying evaluators** (if evaluation is ever decentralized) | Evaluators | Bittensor's lesson [15][16]: commit-reveal, fast-moving ground truth, pay evaluators against mystery answers. |
| **Price collusion** among Runners | Runners | Open entry, scoring-auction dispatch [33], subsidized exploration of new Runners. |
| **Disintermediation**: Sender and Runner deal directly | Both | Make staying worth it: escrow, verification, failover, ratings, Receipts credits, a single bill. Low take rate. |

### 9.2 Verification layers (cheapest to strongest)

1. **Continuous black-box equality tests** [42]. Cheap, always on.
2. **Random spot-check re-execution** on a small fraction of errands, with Bond slashing. Set the check rate `p` and slash `S` so that `p * S > expected gain from cheating` [49].
3. **Activation commitments** (TOPLOC [50]) for Runners who opt in; verification up to 100x cheaper than inference.
4. **TEE-attested "Verified" tier** [53] (under 5% overhead for typical LLM inference), sold as a premium.
5. **Heavy proofs for disputes only**: Verde refereed delegation [54], zkLLM [55] (too slow per request, fine for arbitration).

### 9.3 Market design notes

- **Scoring auction, not lowest bid.** Pure lowest-price procurement drives quality down. A scoring rule over (quality, price, latency) [33] keeps quality in the objective. Che shows a committed scoring rule tends to under-reward quality relative to true buyer value, so err on the side of weighting quality.
- **Second-score pricing (later).** Paying the winning Runner at the level needed to just beat the runner-up removes the incentive to shade bids, the procurement analogue of a second-price auction [33][34a].
- **Escrow aligns incentives.** Runners get paid only on verified success. That single rule removes most moral hazard on verifiable lanes.
- **Exploration is a platform cost.** Sending real traffic to unproven Runners risks Sender quality. Pay for it: run new Runners in **shadow mode** (duplicate errand, result not returned, Runner still paid a reduced rate) until their posterior is tight enough.

---

## 10. Business model

- **Take rate** on each settled errand (target 5% to 10%, in line with OpenRouter's reported fee [10]). Lower for Trusted Senders.
- **Priority premium** priced from queue load [36].
- **Verified tier** (TEE / spot-check) premium.
- **Receipt pool access** fees from Runners.
- **Free for Runners to list** and take their onboarding exam [32][34].

Defensibility: ratings data and mystery-errand pools compound over time; the Receipts flywheel; integrations (MCP/A2A) that make Errand the default delegation tool.

Biggest risks: incumbents moving down-stack (OpenRouter already ranks hosts by quality telemetry [9]); disintermediation; liability for shared data [48]. See section 13.

---

## 11. MVP roadmap

**Phase 0: Spec (week 1 to 2)**
- Errand, Runner, Lane, Receipt schemas. Pick 3 verifiable lanes: `math.final-answer`, `code.python.tests`, `extract.json-schema`.
- Build private mystery pools for each (a few hundred items).

**Phase 1: It works end to end (week 3 to 6)**
- Gateway API (`POST /errands`) plus Python SDK.
- Runner registry and an OpenAI-compatible Runner adapter so any hosted or local model can join (vLLM, Ollama).
- Deterministic verifiers, onboarding exam, Beta-posterior ratings, `dispatch=top`.
- Prepaid credits ledger (no real money yet).
- Demo: Alan (a frontier model) solving a multi-step task, delegating math sub-steps to a small local math model, with cost and latency comparison.

**Phase 2: Market mechanics (week 7 to 10)**
- Thompson-sampling dispatch, Sender preference weights, budgets and deadlines.
- Escrow, retries and fallback. Sender tiers. Public leaderboard per lane.
- **MCP server** exposing `send_errand` and `recommend_runner` tools.

**Phase 3: Integrity and data (week 11 to 16)**
- Equality tests, spot-check re-execution, Bonds and slashing.
- Calibration scoring. Receipts with consent levels 0 to 2.
- A2A AgentCard for each Runner.

**Phase 4: Scale**
- Contextual bandit dispatch, LLM-judge lanes (with bias mitigations), TEE tier, real payments (Stripe or x402 [41]), ensemble errands [8].

**Suggested stack:** Python (FastAPI) gateway, Postgres for ledger and ratings, Redis for queues, a worker pool for verifiers (sandboxed code execution), Python SDK first, then TypeScript.

---

## 12. Metrics to track from day one

- **Sender side:** cost per successful errand vs doing it with Alan directly (the headline number), end-to-end latency, verified pass rate, fallback rate.
- **Runner side:** utilization, earnings per GPU-hour, rating stability.
- **Platform:** liquidity per lane (Runners with tight posteriors), dispatch regret vs oracle on replay [5], mystery-errand detection rate (can Runners tell them apart? they should not), dispute rate.

---

## 13. Open risks

1. **Evaluator collusion and laziness.** Ground truth must move faster than copying pays [15]. Private evals leak over time [19].
2. **Undetectable partial substitution.** Randomized mixing evades output tests [43]. Without TEEs or commitments, verification is probabilistic; slashing must outweigh the gain.
3. **Judge bias as an attack surface** on non-verifiable lanes [20][21][22]. Start with verifiable lanes.
4. **Disintermediation** once Senders find good Runners.
5. **Incumbents** (OpenRouter's Exacto [9]) and protocol commoditization (A2A, AP2, x402) [18][41].
6. **Loyalty vs fairness.** Price priority by externality [36], reserve capacity for small Senders.
7. **Data liability.** Shared prompts may contain third-party personal data or copyrighted text [47][48]. Data valuation can be gamed by duplicates or poison [40][44].
8. **Sybils** [52].
9. **Cold start on both sides.** Exploration costs real quality unless run in shadow mode.

## 14. Open questions for the founder

- Who is the first Sender? An agent framework developer (cost-sensitive, technical) is probably the easiest first customer.
- Who are the first Runners? Seed the market by running a few strong open specialists yourself (for example a small math model and a small coder) so day one has supply.
- Money or credits? Credits avoid payments regulation early.
- Centralized evaluation (simpler, trusted) or decentralized (Bittensor-style)? Recommendation: **centralized first**, design the interfaces so evaluators could be decentralized later.
- How much should Errand say about *which* Runner served an errand? Transparency helps trust; anonymity reduces disintermediation.

---

## References

**Routing and cascades**
- [1] Chen, Zaharia, Zou. *FrugalGPT: How to Use Large Language Models While Reducing Cost and Improving Performance.* 2023. https://arxiv.org/abs/2305.05176
- [2] Ding et al. *Hybrid LLM: Cost-Efficient and Quality-Aware Query Routing.* ICLR 2024. https://arxiv.org/abs/2404.14618
- [3] Madaan et al. *AutoMix: Automatically Mixing Language Models.* NeurIPS 2024. https://arxiv.org/abs/2310.12963
- [4] Ong et al. *RouteLLM: Learning to Route LLMs with Preference Data.* ICLR 2025. https://arxiv.org/abs/2406.18665
- [5] Hu et al. *RouterBench.* 2024. https://arxiv.org/abs/2403.12031
- [6] Huang et al. *RouterEval.* Findings of EMNLP 2025. https://arxiv.org/abs/2503.10657
- [7] Lu et al. *RouterArena.* 2025. https://arxiv.org/abs/2510.00202
- [8] Wang et al. *Mixture-of-Agents Enhances Large Language Model Capabilities.* 2024. https://arxiv.org/abs/2406.04692

**Products and protocols**

- [9] OpenRouter provider routing docs, https://openrouter.ai/docs/features/provider-routing ; Exacto, https://openrouter.ai/blog/announcements/provider-variance-introducing-exacto/ ; Auto Exacto, https://openrouter.ai/blog/announcements/auto-exacto/
- [10] OpenRouter platform fee. https://openrouter.ai/blog/simplifying-our-platform-fee
- [11] Not Diamond pricing. https://www.notdiamond.ai/pricing
- [12] Accenture invests in Martian. 2024. https://newsroom.accenture.com/news/2024/accenture-invests-in-martian-to-bring-dynamic-routing-of-large-language-queries-and-more-effective-ai-systems-to-clients
- [13] TechCrunch on Unify. 2024. https://techcrunch.com/2024/05/22/unify-helps-developers-find-the-best-llm-for-the-job
- [14] Hugging Face Inference Providers pricing. https://huggingface.co/docs/inference-providers/pricing
- [15] Bittensor Yuma Consensus, https://docs.learnbittensor.org/yuma-consensus ; weight-copying paper (2024), https://docs.learnbittensor.org/papers/BT_Weight_Copier-29May2024.pdf
- [16] Bittensor commit-reveal. https://docs.learnbittensor.org/concepts/commit-reveal
- [17] Model Context Protocol (overview). https://en.wikipedia.org/wiki/Model_Context_Protocol
- [18] Linux Foundation launches Agent2Agent protocol project. 2025. https://linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents

**Evaluation**

- [19] Singh et al. *The Leaderboard Illusion.* 2025. https://arxiv.org/abs/2504.20879
- [20] Zheng et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023. https://arxiv.org/abs/2306.05685
- [21] Wang et al. *Large Language Models are not Fair Evaluators.* ACL 2024. https://arxiv.org/abs/2305.17926
- [22] Panickssery, Bowman, Feng. *LLM Evaluators Recognize and Favor Their Own Generations.* NeurIPS 2024. https://arxiv.org/abs/2404.13076
- [23] Liang et al. *Holistic Evaluation of Language Models (HELM).* TMLR 2023. https://arxiv.org/abs/2211.09110
- [24] Oren et al. *Proving Test Set Contamination in Black-Box Language Models.* ICLR 2024. https://arxiv.org/abs/2310.17623
- [25] White et al. *LiveBench.* ICLR 2025. https://arxiv.org/abs/2406.19314
- [26] Lambert et al. *Tülu 3: Pushing Frontiers in Open Language Model Post-Training* (RLVR). 2024. https://arxiv.org/abs/2411.15124
- [56] Chiang et al. *Chatbot Arena.* 2024. https://arxiv.org/abs/2403.04132

**Ratings and bandits**

- [27] Herbrich, Minka, Graepel. *TrueSkill.* NeurIPS 2006. https://papers.nips.cc/paper_files/paper/2006/file/f44ee263952e65b3610b8ba51229d1f9-Paper.pdf
- [28] Glickman. *Parameter Estimation in Large Dynamic Paired Comparison Experiments* (Glicko). JRSS-C 1999. https://ideas.repec.org/a/bla/jorssc/v48y1999i3p377-394.html
- [29] Panda et al. *PILOT: Adaptive LLM Routing under Budget Constraints.* Findings of EMNLP 2025. https://arxiv.org/abs/2508.21141
- [29a] Kamvar, Schlosser, Garcia-Molina. *The EigenTrust Algorithm.* WWW 2003. https://iw3c2.org/papers/2019-EigenTrust/
- [30] Russo et al. *A Tutorial on Thompson Sampling.* FnTML 2018. https://arxiv.org/abs/1707.02038
- [31] Li, Chu, Langford, Schapire. *A Contextual-Bandit Approach to Personalized News Article Recommendation* (LinUCB). WWW 2010. https://arxiv.org/abs/1003.0146

**Economics and mechanism design**

- [32] Rochet, Tirole. *Platform Competition in Two-Sided Markets.* JEEA 2003. https://academic.oup.com/jeea/article/1/4/990/2280902
- [33] Che. *Design Competition through Multidimensional Auctions.* RAND J. Econ. 1993. https://ideas.repec.org/a/rje/randje/v24y1993iwinterp668-680.html
- [34] Parker, Van Alstyne. *Two-Sided Network Effects: A Theory of Information Product Design.* Management Science 2005. https://pubsonline.informs.org/doi/fpi/10.1287/mnsc.1050.0400
- [34a] Dütting et al. *Mechanism Design for Large Language Models.* WWW 2024. https://arxiv.org/abs/2310.10826
- [35] Gneiting, Raftery. *Strictly Proper Scoring Rules, Prediction, and Estimation.* JASA 2007. https://apps.dtic.mil/sti/pdfs/ADA459827.pdf
- [36] Mendelson, Whang. *Optimal Incentive-Compatible Priority Pricing for the M/M/1 Queue.* Operations Research 1990. https://pubsonline.informs.org/doi/fpi/10.1287/opre.38.5.870
- [37] OpenAI priority processing. https://openai.com/api-priority-processing/
- [38] Anthropic service tiers. https://platform.claude.com/docs/en/api/service-tiers

**Data**

- [39] Ghorbani, Zou. *Data Shapley.* ICML 2019. https://proceedings.mlr.press/v97/ghorbani19c.html
- [40] Wang, Mittal, Song, Jia. *Data Shapley in One Training Run.* ICLR 2025. https://arxiv.org/abs/2406.11011
- [41] Coinbase on Google AP2 and x402. https://www.coinbase.com/developer-platform/discover/launches/google_x402
- [44] Agarwal, Dahleh, Sarkar. *A Marketplace for Data.* EC 2019. https://arxiv.org/abs/1805.08125
- [45] Li, Tramèr, Liang, Hashimoto. *Large Language Models Can Be Strong Differentially Private Learners.* ICLR 2022. https://arxiv.org/abs/2110.05679
- [46] McMahan et al. *Communication-Efficient Learning of Deep Networks from Decentralized Data* (FedAvg). AISTATS 2017. https://arxiv.org/abs/1602.05629
- [47] Longpre et al. *Consent in Crisis.* NeurIPS 2024. https://arxiv.org/abs/2407.14933
- [48] EU AI Act, Article 53. https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-53

**Verification and security**

- [42] Gao, Liang, Guestrin. *Model Equality Testing: Which Model Is This API Serving?* ICLR 2025. https://arxiv.org/abs/2410.20247
- [43] Cai, Shi, Zhao, Song. *Are You Getting What You Pay For? Auditing Model Substitution in LLM APIs.* NeurIPS 2025. https://arxiv.org/abs/2504.04715
- [49] Zhang et al. *Proof of Sampling.* 2024. https://arxiv.org/abs/2405.00295
- [50] Ong et al. *TOPLOC.* ICML 2025. https://arxiv.org/abs/2501.16007
- [51] Sun et al. *SVIP: Towards Verifiable Inference of Open-source LLMs.* NeurIPS 2025. https://arxiv.org/abs/2410.22307
- [52] Douceur. *The Sybil Attack.* IPTPS 2002. https://www.microsoft.com/en-us/research/publication/the-sybil-attack/
- [53] Zhu et al. *Confidential Computing on NVIDIA H100 GPU.* 2024. https://arxiv.org/abs/2409.03992
- [54] Arun et al. *Verde: Verification via Refereed Delegation.* 2025. https://arxiv.org/abs/2502.19405
- [55] Sun, Li, Zhang. *zkLLM.* CCS 2024. https://arxiv.org/abs/2404.16109
