"""Python SDK. Works from any agent framework, no MCP required.

    from errand.client import Errand
    e = Errand()                                  # reads ERRAND_URL and ERRAND_API_KEY
    r = e.send_math("What is 17 * 23?")
    print(r["answer"], r["total_usd"])

    # function calling with any OpenAI-compatible model:
    tools = e.tools("openai")
    result = e.run_tool(call.function.name, json.loads(call.function.arguments))
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from . import tools as _tools


class ErrandAPIError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(f"{status}: {message}")
        self.status = status


class Errand:
    def __init__(self, api_key: str | None = None, base_url: str | None = None, timeout: float = 300):
        self.base_url = (base_url or os.environ.get("ERRAND_URL", "http://localhost:8000")).rstrip("/")
        key = api_key or os.environ.get("ERRAND_API_KEY", "")
        self._http = httpx.Client(base_url=self.base_url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {key}"} if key else {})

    def _req(self, method: str, path: str, **kw) -> Any:
        r = self._http.request(method, path, **kw)
        try:
            body = r.json()
        except ValueError:
            body = {"error": r.text}
        if r.status_code >= 400:
            raise ErrandAPIError(r.status_code, body.get("error") or str(body.get("detail")) if isinstance(body, dict) else str(body))
        return body

    # ---------- core ----------
    def lanes(self) -> list[dict]:
        return self._req("GET", "/v1/lanes")

    def recommend(self, lane: str, preset: str = "balanced", budget_usd: float | None = None) -> dict:
        params = {"lane": lane, "preset": preset}
        if budget_usd is not None:
            params["budget_usd"] = budget_usd
        return self._req("GET", "/v1/recommend", params=params)

    def send(self, lane: str, payload: dict, budget_usd: float | None = None, preset: str | None = None,
             mode: str = "sample") -> dict:
        body: dict[str, Any] = {"lane": lane, "payload": payload, "mode": mode}
        if budget_usd is not None:
            body["budget_usd"] = budget_usd
        if preset:
            body["preset"] = preset
        return self._req("POST", "/v1/errands", json=body)

    def send_math(self, problem: str, expected: str | None = None, **kw) -> dict:
        payload = {"problem": problem} | ({"expected": expected} if expected else {})
        return self.send("math.final-answer", payload, **kw)

    def send_code(self, function_name: str, spec: str, tests: str, **kw) -> dict:
        return self.send("code.python.tests", {"function_name": function_name, "spec": spec, "tests": tests}, **kw)

    def feedback(self, errand_id: str, accepted: bool) -> dict:
        return self._req("POST", f"/v1/errands/{errand_id}/feedback", json={"accepted": accepted})

    def wallet(self) -> dict:
        return self._req("GET", "/v1/me")

    def top_up(self, amount_usd: float) -> dict:
        """Returns {'approve_url': ...}; a human must open it and approve with PayPal."""
        return self._req("POST", "/v1/wallet/topup", json={"amount_usd": amount_usd, "purpose": "wallet"})

    # ---------- function calling ----------
    @staticmethod
    def tools(fmt: str = "openai") -> list[dict]:
        return _tools.definitions(fmt)

    def run_tool(self, name: str, args: dict) -> Any:
        """Execute a tool call from any LLM. Errors come back as data so the model can react."""
        try:
            if name == "list_lanes":
                return self.lanes()
            if name == "recommend_runner":
                return self.recommend(args["lane"], args.get("preset", "balanced"), args.get("budget_usd"))
            if name == "send_errand":
                lane = args["lane"]
                if lane == "code.python.tests":
                    payload = {k: args.get(k) for k in ("function_name", "spec", "tests")}
                else:
                    payload = {"problem": args.get("problem")} | ({"expected": args["expected"]} if args.get("expected") else {})
                return self.send(lane, payload, args.get("budget_usd"), args.get("preset"))
            if name == "give_feedback":
                return self.feedback(args["errand_id"], bool(args["accepted"]))
            if name == "wallet":
                return self.wallet()
            if name == "request_top_up":
                return self.top_up(float(args["amount_usd"]))
            return {"error": f"unknown tool {name}"}
        except ErrandAPIError as e:
            return {"error": str(e)}
        except KeyError as e:
            return {"error": f"missing argument {e}"}
