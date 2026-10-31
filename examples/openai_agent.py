"""A tool-calling agent that delegates through Errand. Works with ANY OpenAI-compatible chat API:
OpenAI, Ollama, Groq, OpenRouter, Together, vLLM, LM Studio...

    # local, free (needs a tool-capable model, e.g. `ollama pull qwen2.5:7b`)
    python examples/openai_agent.py "What is 12% of 2450, and write a python function slugify(s) with tests"

    # hosted
    LLM_BASE_URL=https://api.openai.com/v1 LLM_API_KEY=sk-... LLM_MODEL=gpt-4o-mini python examples/openai_agent.py "..."
"""

import json
import os
import sys

import httpx

from errand import seed
from errand.client import Errand

BASE = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "qwen2.5:7b")
HEADERS = {"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"} if os.environ.get("LLM_API_KEY") else {}

key = os.environ.get("ERRAND_API_KEY") or seed.load_keys().get("senders", {}).get("snd_alan", {}).get("api_key")
errand = Errand(api_key=key)

SYSTEM = ("You are a careful assistant. For self-contained math problems or single Python functions, delegate with the "
          "send_errand tool instead of solving them yourself; always include tests for code. Then answer the user and "
          "mention what delegation cost.")


def chat(messages):
    r = httpx.post(f"{BASE}/chat/completions", headers=HEADERS, timeout=300,
                   json={"model": MODEL, "messages": messages, "tools": errand.tools("openai")})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def main(task: str) -> None:
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": task}]
    for _ in range(8):
        msg = chat(messages)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            print(msg.get("content", ""))
            return
        for call in calls:
            args = json.loads(call["function"]["arguments"] or "{}")
            result = errand.run_tool(call["function"]["name"], args)
            print(f"[errand] {call['function']['name']}({', '.join(f'{k}=' + repr(v)[:40] for k, v in args.items())})"
                  f" -> {result.get('answer', result.get('error', 'ok')) if isinstance(result, dict) else 'ok'}")
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result)[:6000]})
    print("stopped after 8 steps")


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "What is the sum of the integers from 1 to 49? Use Errand.")
