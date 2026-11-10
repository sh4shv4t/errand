"""A tiny coding agent that delegates through Errand, used in the demo video.

The agent model (any OpenAI-compatible endpoint; Ollama by default) gets two tools: Errand's `delegate`,
and `write_file` into a scratch project. Everything printed is what actually happened.

    ERRAND_URL=http://localhost:8002 ERRAND_API_KEY=erk_... python demo/coding_agent.py "Add slugify(s) to text_utils.py"
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from errand.client import Errand  # noqa: E402

LLM = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b")
PROJECT = Path(os.environ.get("AGENT_PROJECT", Path(__file__).resolve().parent / "out" / "my-app"))

errand = Errand(api_key=os.environ.get("ERRAND_API_KEY"), base_url=os.environ.get("ERRAND_URL"))

_delegate = next(t for t in errand.tools("openai") if t["function"]["name"] == "delegate")
# small agent models invent values for optional fields, so this agent only sees task and check
_delegate["function"]["parameters"]["properties"] = {k: v for k, v in _delegate["function"]["parameters"]["properties"].items()
                                                     if k in ("task", "check")}
TOOLS = [
    _delegate,
    {"type": "function", "function": {
        "name": "write_file", "description": "Write a file in the user's project.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
]

SYSTEM = ("You are a coding agent working in the user's project. To write a function, do not write it yourself: first call "
          "`delegate` with a clear task that names the function, and put 3 to 5 Python assert lines that call it in "
          "`check`. Errand returns code that already passed those tests. Then call `write_file` with exactly that code. "
          "Finish with one short sentence for the user.\n\n"
          "Example of a correct delegate call for 'add is_even(n) to num.py':\n"
          '{"task": "Write a Python function is_even(n) that returns True when n is even.", '
          '"check": "assert is_even(2)\\nassert not is_even(3)\\nassert is_even(0)"}')


def say(kind: str, text: str) -> None:
    print(f"{kind}|{text}", flush=True)


def chat(messages: list[dict]) -> dict:
    r = httpx.post(f"{LLM}/chat/completions", timeout=300,
                   json={"model": MODEL, "messages": messages, "tools": TOOLS, "temperature": 0})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def run_tool(name: str, args: dict) -> dict:
    if name == "delegate":
        if os.environ.get("AGENT_BUDGET_USD"):  # the owner's per-errand spending cap, set outside the model's reach
            args["budget_usd"] = float(os.environ["AGENT_BUDGET_USD"])
        say("tool", f"errand.delegate(task={args.get('task', '')[:70]!r}, check=<{len(str(args.get('check', '')).splitlines())} asserts>)" + (f" · budget ${args['budget_usd']}" if args.get('budget_usd') else ""))
        r = errand.run_tool("delegate", args)
        if r.get("status") == "completed":
            who = (r.get("runner") or {}).get("name", "a specialist")
            checked = "tests passed" if r.get("verdict") == "passed" else "delivered unchecked"
            say("ok" if r.get("verdict") == "passed" else "err",
                f"{'verified' if r.get('verdict') == 'passed' else 'answered'} by {who} · {checked} · "
                f"paid ${r['total_usd']:.4f} (frontier est. ${r['baseline_usd']:.3f})")
            return {"code": r.get("answer") or "", "verdict": r.get("verdict"), "cost_usd": r.get("total_usd")}
        say("err", r.get("detail") or r.get("error") or "not completed")
        return r
    if name == "write_file":
        path = PROJECT / args["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(args["content"], encoding="utf-8")
        say("file", f"wrote {args['path']} ({len(args['content'].splitlines())} lines)")
        return {"ok": True}
    return {"error": f"unknown tool {name}"}


def main(task: str) -> None:
    say("user", task)
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    for _ in range(6):
        msg = chat(messages)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            say("agent", (msg.get("content") or "Done.").strip().splitlines()[0][:160])
            return
        for call in calls:
            args = json.loads(call["function"]["arguments"] or "{}")
            result = run_tool(call["function"]["name"], args)
            messages.append({"role": "tool", "tool_call_id": call.get("id", "0"), "content": json.dumps(result)[:6000]})
    say("agent", "Stopped after 6 steps.")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "Add a function slugify(s) to text_utils.py that lowercases, trims, and joins words with '-'.")
