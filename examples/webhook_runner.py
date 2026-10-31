"""Become a Runner with any model behind a webhook. Errand POSTs each errand here:

    {"lane": "math.final-answer", "prompt": "...ready-to-use prompt...", "payload": {...}}

and expects {"output": "..."} back (end math answers with 'ANSWER: <n>' and add 'CONFIDENCE: <0..1>').

    uvicorn examples.webhook_runner:app --port 9000
    then in the Runner dashboard: Endpoint type = Webhook, URL = http://localhost:9000/errand

Replace solve() with a call to your own model.
"""

import ast
import operator

from fastapi import FastAPI, Header, HTTPException

app = FastAPI(title="Example Errand Runner")
SECRET = None  # set to a string and configure secret_env on the gateway to require X-Errand-Secret

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def _calc(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        raise ValueError("unsupported")
    return ev(ast.parse(expr, mode="eval"))


def solve(lane: str, prompt: str, payload: dict) -> str:
    if lane == "math.final-answer":
        text = payload["problem"]
        expr = "".join(ch for ch in text if ch in "0123456789+-*/. ()").strip()
        try:
            value = _calc(expr)
            return f"ANSWER: {int(value) if float(value).is_integer() else value}\nCONFIDENCE: 0.9"
        except Exception:
            return "ANSWER: unknown\nCONFIDENCE: 0.05"
    return f"```python\ndef {payload['function_name']}(*a, **k):\n    raise NotImplementedError\n```\nCONFIDENCE: 0.01"


@app.post("/errand")
def errand(body: dict, x_errand_secret: str | None = Header(default=None)):
    if SECRET and x_errand_secret != SECRET:
        raise HTTPException(401, "bad secret")
    return {"output": solve(body["lane"], body["prompt"], body["payload"])}
