"""Framework-neutral tool definitions, so agents without MCP can delegate too.

The same six tools as the MCP server, as JSON Schema. Serve with GET /v1/tools?format=openai|anthropic
and execute with errand.client.Errand.run_tool(name, arguments).
"""

from __future__ import annotations

TOOLS = [
    {
        "name": "list_lanes",
        "description": "List the task lanes Errand can delegate, with required fields and the estimated frontier-model cost.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "recommend_runner",
        "description": "Should I delegate, and to whom? Returns specialist Runners ranked for a lane with price, expected pass rate and latency.",
        "parameters": {"type": "object", "properties": {
            "lane": {"type": "string", "enum": ["math.final-answer", "code.python.tests"]},
            "preset": {"type": "string", "enum": ["balanced", "cheapest", "fastest", "best"]},
            "budget_usd": {"type": "number"},
        }, "required": ["lane"]},
    },
    {
        "name": "send_errand",
        "description": "Delegate a self-contained sub-task to a cheaper specialist model and get a verified answer. "
                       "Math: give problem (and expected if known). Code: give function_name, spec and tests (Python asserts). "
                       "Payment is escrowed and released only if verification passes.",
        "parameters": {"type": "object", "properties": {
            "lane": {"type": "string", "enum": ["math.final-answer", "code.python.tests"]},
            "problem": {"type": "string", "description": "math: the problem text"},
            "expected": {"type": "string", "description": "math: known answer, enables verification"},
            "function_name": {"type": "string", "description": "code: function to write"},
            "spec": {"type": "string", "description": "code: what the function must do"},
            "tests": {"type": "string", "description": "code: Python assert lines"},
            "budget_usd": {"type": "number", "description": "max total spend for this errand"},
            "preset": {"type": "string", "enum": ["balanced", "cheapest", "fastest", "best"]},
        }, "required": ["lane"]},
    },
    {
        "name": "give_feedback",
        "description": "Accept or dispute a completed errand.",
        "parameters": {"type": "object", "properties": {
            "errand_id": {"type": "string"}, "accepted": {"type": "boolean"}}, "required": ["errand_id", "accepted"]},
    },
    {
        "name": "wallet",
        "description": "Wallet balance, tier, 30-day spend and savings.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "request_top_up",
        "description": "Ask the human to add funds. Returns a PayPal approval link the human must open; you cannot approve it.",
        "parameters": {"type": "object", "properties": {"amount_usd": {"type": "number"}}, "required": ["amount_usd"]},
    },
]


def definitions(fmt: str = "openai") -> list[dict]:
    if fmt == "anthropic":
        return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in TOOLS]
    return [{"type": "function", "function": t} for t in TOOLS]
