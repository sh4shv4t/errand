---
name: delegate
description: Use when a task contains a self-contained math problem with a numeric answer or a single Python function that can be specified with tests. Delegates it to a cheaper specialist model through the Errand MCP tools and pays only if the result is verified.
---

# Delegate with Errand

Use the `errand` MCP tools to hand off well-scoped sub-problems instead of solving them yourself.

## When to delegate

- A math sub-problem with a single numeric answer (lane `math.final-answer`).
- One Python function you can describe with a short spec and `assert` tests (lane `code.python.tests`).

Do not delegate open-ended reasoning, anything that needs the wider conversation, or anything with secrets or personal data.

## How

1. Optional: `recommend_runner(lane)` to see the expected cost, pass rate and latency.
2. `send_errand(...)`:
   - math: `problem`, plus `expected` if you already know the answer (enables verification).
   - code: `function_name`, `spec`, `tests` (always include tests; payment only releases if they pass).
3. Use the returned `answer`. Report the cost and savings (`total_usd`, `saved_usd`) to the user once per task.
4. If the result looks wrong, call `give_feedback(errand_id, accepted=false)`.

## Money

- If a call returns status 402 (empty wallet), call `request_top_up(amount_usd)` and show the returned PayPal link to the user. Never claim a top-up happened until they confirm.
- Respect the budget the user gave you; pass it as `budget_usd`.
