# Errand: TO-DO

Deferred work, in rough priority order. Design rationale is in `docs/PRODUCT_DIRECTION.md`.

## Agent-facing CLI

For agents that only have a shell (MCP clients already get the `delegate` tool).

- [ ] `errand query "task synopsis"`: infer the Lane and print ranked Runners with price, expected pass rate and p95 latency. Spends nothing.
- [ ] `errand run "task" [--check "42"] [--runner Duke] [--budget 0.01]`: wraps `POST /v1/delegate` and prints the answer, verdict, cost and savings.
- [ ] `errand limits --per-errand 0.05 --daily 5`: set the spending mandate from the shell.
- [ ] Read `ERRAND_URL` and `ERRAND_API_KEY` like the SDK does; add `--json` for machine-readable output.

## Product (from PRODUCT_DIRECTION.md)

- [ ] Pin by model name across every Runner that serves it (`model=`), not only by Runner.
- [ ] Consensus panel for `math.final-answer` (adaptive 2 then 3, every member paid).
- [ ] Runner claims as a weak prior, plus a generated Markdown Runner Card.
- [ ] Server-driven tool list for the stdio MCP server, version handshake via `/v1/config`, `errand update`.
- [ ] PayPal vaulted payment method with auto-reload inside the mandate.
- [ ] Pull-based Runners (`errand run --model ollama/...` long-polls for work).
