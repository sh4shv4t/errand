"""`errand postman`: a Postman collection generated from Errand's own OpenAPI spec.

A hand-picked Quickstart folder comes first (the calls a new user actually makes), then every endpoint.
Set the collection variables `base_url` and `api_key` (a Sender key, `errand keys` prints the demo ones).
"""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

QUICKSTART = [
    ("Delegate a math job", "POST", "/v1/delegate",
     {"task": "A train travels 216 km in 12 hours at a constant speed. What is its speed in km per hour?", "check": "18"},
     "One call. Errand picks the Lane and the specialist, checks the answer against `check`, and only then pays."),
    ("Delegate a code job (with tests)", "POST", "/v1/delegate",
     {"task": "Write a Python function is_palindrome(s) that ignores case and spaces.",
      "check": "assert is_palindrome('racecar')\nassert is_palindrome('Never odd or even')\nassert not is_palindrome('hello')"},
     "Code needs tests in `check`. Payment is released only if they pass; failed attempts are retried elsewhere for free."),
    ("Delegate to a Runner you pick", "POST", "/v1/delegate",
     {"task": "What is 17 * 23?", "check": "391", "runner": "Atlas", "budget_usd": 0.01},
     "Pin a Runner by name or id. If it is unavailable or over budget, Errand falls back to the next best one."),
    ("List Runners you can pick", "GET", "/v1/runners", None, "Active specialists with their Lanes and prices."),
    ("Wallet, tier and savings", "GET", "/v1/me", None, "Balance, 30-day spend and how much you saved versus a frontier model."),
    ("Your errands", "GET", "/v1/errands", None, "Every errand with its verdict, Runner, cost and savings."),
    ("Top up with PayPal", "POST", "/v1/wallet/topup", {"amount_usd": 5, "purpose": "wallet"},
     "Returns a PayPal approval link (Orders v2, CAPTURE). A human opens it and approves; the wallet is credited on return."),
    ("Post a PayPal bounty", "POST", "/v1/bounties",
     {"task": "What is 12% of 2450?", "check": "294", "amount_usd": 2},
     "PayPal Orders v2 with intent AUTHORIZE: captured only if the answer verifies, voided otherwise."),
]


def _example(schema: dict, defs: dict) -> object:
    """A small example value for a JSON schema (enough to make a request body readable)."""
    if "$ref" in schema:
        return _example(defs[schema["$ref"].split("/")[-1]], defs)
    if "anyOf" in schema:
        return _example(next((s for s in schema["anyOf"] if s.get("type") != "null"), {}), defs)
    if "default" in schema:
        return schema["default"]
    t = schema.get("type")
    if t == "object":
        return {k: _example(v, defs) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return []
    return {"string": "", "number": 0, "integer": 0, "boolean": False}.get(t)


def _request(name: str, method: str, path: str, body: object | None, description: str = "", query: list | None = None) -> dict:
    url = {"raw": "{{base_url}}" + path, "host": ["{{base_url}}"], "path": [p for p in path.split("/") if p]}
    if query:
        url["query"] = query
        url["raw"] += "?" + "&".join(f"{q['key']}={q['value']}" for q in query)
    req = {"method": method, "header": [], "url": url, "description": description}
    if body is not None:
        req["header"].append({"key": "Content-Type", "value": "application/json"})
        req["body"] = {"mode": "raw", "raw": json.dumps(body, indent=2), "options": {"raw": {"language": "json"}}}
    return {"name": name, "request": req}


def collection(openapi: dict, base_url: str = "http://localhost:8000") -> dict:
    defs = openapi.get("components", {}).get("schemas", {})
    everything = []
    for path, ops in openapi["paths"].items():
        if not path.startswith("/v1/"):
            continue  # web pages and PayPal return handlers are for browsers, not API clients
        for method, op in ops.items():
            body = None
            content = op.get("requestBody", {}).get("content", {}).get("application/json")
            if content:
                body = _example(content["schema"], defs)
            query = [{"key": p["name"], "value": str(p.get("schema", {}).get("default", ""))}
                     for p in op.get("parameters", []) if p.get("in") == "query"]
            pm_path = path.replace("{", "{{").replace("}", "}}")
            everything.append(_request(f"{method.upper()} {path}", method.upper(), pm_path, body,
                                       op.get("description", ""), query or None))
    return {
        "info": {
            "name": "Errand API",
            "description": "Send your model on fewer errands. Delegate sub-tasks to cheaper specialist models and pay "
                           "through PayPal only when the answer checks out.\n\nSet `base_url` and `api_key` (a Sender "
                           "key; `errand keys` prints the demo ones), then start with the Quickstart folder.",
            "schema": SCHEMA,
        },
        "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{api_key}}", "type": "string"}]},
        "variable": [{"key": "base_url", "value": base_url}, {"key": "api_key", "value": "erk_YOUR_SENDER_KEY"}],
        "item": [
            {"name": "Quickstart", "item": [_request(*q) for q in QUICKSTART]},
            {"name": "All endpoints", "item": everything},
        ],
    }


def write(path: Path, base_url: str = "http://localhost:8000") -> dict:
    from .app import app  # imported lazily: building the spec loads the whole gateway

    col = collection(app.openapi(), base_url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(col, indent=2) + "\n", encoding="utf-8")
    return col
