"""Errand MCP server: gives any MCP-capable agent the ability to delegate errands.

Two ways to connect, same tools:
  remote   the gateway serves MCP at {ERRAND_URL}/mcp (streamable HTTP). Send the Sender key as
           'Authorization: Bearer erk_...' (or append ?key=erk_... for clients that only take a URL).
  stdio    run `errand-mcp` locally with ERRAND_URL and ERRAND_API_KEY in the environment.
"""

from __future__ import annotations

import contextvars
import logging
import os
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

# Set per request when served over HTTP by the gateway (see app.McpKeyMiddleware).
request_key: contextvars.ContextVar[str | None] = contextvars.ContextVar("errand_request_key", default=None)
# When mounted inside the gateway, tools call the API in-process instead of over the network.
_gateway_asgi = None

INSTRUCTIONS = """Errand lets you delegate well-scoped sub-tasks to cheaper specialist models and pay only for verified results.
Delegate when a sub-problem fits a lane (call list_lanes) and is self-contained, for example a math problem with a
numeric answer or a Python function you can describe with tests. Call recommend_runner first if you want the expected
cost and pass rate. Always pass tests for code errands and, when you know it, an expected answer for math so payment is
verified. Never invent a PayPal link: if the wallet is empty, call request_top_up and show the returned link to the human."""

server = MCPServer(name="errand", instructions=INSTRUCTIONS, website_url="https://github.com/sh4shv4t/errand")


def _base() -> str:
    return os.environ.get("ERRAND_URL", "http://localhost:8000").rstrip("/")


def _headers() -> dict:
    key = request_key.get() or os.environ.get("ERRAND_API_KEY", "")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _client() -> httpx.AsyncClient:
    if _gateway_asgi is not None:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=_gateway_asgi), base_url="http://errand.internal",
                                 headers=_headers(), timeout=300)
    return httpx.AsyncClient(base_url=_base(), headers=_headers(), timeout=300)


async def _call(method: str, path: str, **kw) -> Any:
    async with _client() as c:
        try:
            r = await c.request(method, path, **kw)
        except httpx.HTTPError as e:
            return {"error": f"cannot reach Errand at {_base()}: {e}. Is `errand serve` running?"}
    try:
        body = r.json()
    except ValueError:
        body = {"error": r.text[:500]}
    if r.status_code >= 400:
        msg = body.get("error") or body.get("detail") if isinstance(body, dict) else body
        out = {"error": msg, "status": r.status_code}
        if r.status_code == 402:
            out["hint"] = "Wallet is empty. Call request_top_up and ask the human to approve the PayPal link."
        if r.status_code == 401:
            out["hint"] = ("Add your Sender key: header 'Authorization: Bearer erk_...' for the remote /mcp endpoint, "
                           "or ERRAND_API_KEY for errand-mcp. Run `errand connect` to set this up automatically.")
        return out
    return body


@server.tool(description="List the task lanes Errand can delegate, with required payload fields and the estimated frontier-model cost.")
async def list_lanes() -> Any:
    return await _call("GET", "/v1/lanes")


@server.tool(description="Should I delegate, and to whom? Returns Runners ranked for a lane with price, expected pass rate and p95 latency. "
                         "preset is one of balanced, cheapest, fastest, best.")
async def recommend_runner(lane: str, preset: str = "balanced", budget_usd: float | None = None) -> Any:
    params = {"lane": lane, "preset": preset}
    if budget_usd is not None:
        params["budget_usd"] = budget_usd
    return await _call("GET", "/v1/recommend", params=params)


@server.tool(description="Delegate an errand and wait for the verified result. "
                         "For lane 'math.final-answer' pass problem (and expected if you know the answer). "
                         "For lane 'code.python.tests' pass function_name, spec and tests (Python assert lines). "
                         "Payment is held in escrow and released only if verification passes; failed attempts are retried "
                         "on another Runner at no cost. Returns the answer, the Runner, and a cost receipt.")
async def send_errand(lane: str, problem: str | None = None, expected: str | None = None,
                      function_name: str | None = None, spec: str | None = None, tests: str | None = None,
                      budget_usd: float | None = None, preset: str | None = None, mode: str = "sample") -> Any:
    if lane == "code.python.tests":
        payload = {"function_name": function_name, "spec": spec, "tests": tests}
    else:
        payload = {"problem": problem}
        if expected:
            payload["expected"] = expected
    body: dict[str, Any] = {"lane": lane, "payload": payload, "mode": mode}
    if budget_usd is not None:
        body["budget_usd"] = budget_usd
    if preset:
        body["preset"] = preset
    e = await _call("POST", "/v1/errands", json=body)
    if isinstance(e, dict) and "id" in e:  # trim to what an agent needs
        return {k: e[k] for k in ("id", "status", "verdict", "answer", "output", "confidence", "detail", "runner",
                                  "total_usd", "baseline_usd", "saved_usd", "latency_ms", "attempts")}
    return e


@server.tool(description="Accept or dispute a completed errand. Disputes lower the Runner's rating.")
async def give_feedback(errand_id: str, accepted: bool) -> Any:
    return await _call("POST", f"/v1/errands/{errand_id}/feedback", json={"accepted": accepted})


@server.tool(description="Wallet balance, Sender tier, 30-day spend and savings versus doing the work with a frontier model.")
async def wallet() -> Any:
    return await _call("GET", "/v1/me")


@server.tool(description="Ask the human to add funds. Returns a PayPal approval link. You cannot approve it yourself: "
                         "show the link to the human and wait. Amount between 1 and 500 USD.")
async def request_top_up(amount_usd: float) -> Any:
    r = await _call("POST", "/v1/wallet/topup", json={"amount_usd": amount_usd, "purpose": "wallet"})
    if isinstance(r, dict) and r.get("approve_url"):
        r["instructions"] = f"Ask the human to open this link and approve ${amount_usd:.2f} with PayPal: {r['approve_url']}"
    return r


def http_app(gateway_asgi):
    """Streamable-HTTP MCP app to mount inside the gateway at /mcp (stateless, JSON responses)."""
    global _gateway_asgi
    _gateway_asgi = gateway_asgi
    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    server.run("stdio")


if __name__ == "__main__":
    main()
