"""Runner adapters: how the gateway talks to a provider's model.

  openai     any OpenAI-compatible chat endpoint (Ollama, vLLM, Groq, OpenRouter, Together...)
  webhook    the provider hosts an HTTP endpoint; Errand POSTs the errand and reads {"output": ...}
  simulated  a stand-in model for demos and tests; clearly labelled as simulated everywhere
"""

from __future__ import annotations

import ast
import operator
import os
import random
import re
import time
from dataclasses import dataclass

import httpx

from . import config, lanes, taskbank


@dataclass
class RunResult:
    output: str
    latency_ms: int
    ok_call: bool
    error: str | None = None


def run(runner: dict, cfg: dict, lane_id: str, payload: dict, call_index: int = 0) -> RunResult:
    lane = lanes.get(lane_id)
    prompt = lane.build_prompt(payload)
    t0 = time.perf_counter()
    try:
        if runner["kind"] == "simulated":
            output = _simulated(cfg, lane_id, payload, call_index)
        elif runner["kind"] == "openai":
            output = _openai(cfg, prompt)
        elif runner["kind"] == "webhook":
            output = _webhook(cfg, lane_id, prompt, payload)
        else:
            raise ValueError(f"unknown runner kind {runner['kind']!r}")
    except Exception as e:  # a failing Runner must never take down the gateway
        return RunResult("", int((time.perf_counter() - t0) * 1000), False, f"{type(e).__name__}: {e}")
    return RunResult(output, int((time.perf_counter() - t0) * 1000), True)


# ---------- openai-compatible ----------

def _openai(cfg: dict, prompt: str) -> str:
    headers = {}
    key = os.environ.get(cfg.get("api_key_env", "")) if cfg.get("api_key_env") else None
    if key:
        headers["Authorization"] = f"Bearer {key}"
    r = httpx.post(
        cfg["base_url"].rstrip("/") + "/chat/completions",
        json={
            "model": cfg["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": cfg.get("temperature", 0.0),
            "max_tokens": cfg.get("max_tokens", 1024),
        },
        headers=headers,
        timeout=cfg.get("timeout", 120),
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"] or ""


# ---------- webhook ----------

def _webhook(cfg: dict, lane_id: str, prompt: str, payload: dict) -> str:
    headers = {}
    secret = os.environ.get(cfg.get("secret_env", "")) if cfg.get("secret_env") else None
    if secret:
        headers["X-Errand-Secret"] = secret
    r = httpx.post(cfg["url"], json={"lane": lane_id, "prompt": prompt, "payload": payload},
                   headers=headers, timeout=cfg.get("timeout", 120))
    r.raise_for_status()
    return str(r.json().get("output", ""))


# ---------- simulated ----------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.Mod: operator.mod}
_EXPR_RE = re.compile(r"[-+*/%^().\d\s]{3,}")


def _safe_eval(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            if isinstance(n.op, ast.Pow) and abs(ev(n.right)) > 64:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        raise ValueError("unsupported expression")
    return ev(ast.parse(expr.replace("^", "**"), mode="eval"))


_LEAD_RE = re.compile(r"^\s*(what\s+is|what's|compute|calculate|evaluate|solve)\s*:?\s*", re.I)


def pure_expression(problem: str) -> str:
    """The arithmetic expression a problem consists of, or "" if it is anything more than that.
    Simulated runners only evaluate whole expressions; picking numbers out of a word problem gives wrong answers."""
    text = _LEAD_RE.sub("", problem or "").strip().rstrip("?=. ").strip()
    text = text.replace("×", "*").replace("÷", "/")
    return text if text and _EXPR_RE.fullmatch(text) and re.search(r"\d", text) else ""


def simulated_can_answer(lane_id: str, payload: dict) -> bool:
    """Whether a simulated runner has a real shot at this errand (built-in task bank, or plain arithmetic)."""
    if taskbank.lookup(lane_id, payload):
        return True
    return lane_id == "math.final-answer" and bool(pure_expression(payload.get("problem", "")))


def _simulated(cfg: dict, lane_id: str, payload: dict, call_index: int) -> str:
    rng = random.Random()
    lo, hi = cfg.get("latency_ms", [150, 450])
    time.sleep(rng.uniform(lo, hi) / 1000 * config.get().sim_latency_scale)

    accuracy = cfg.get("accuracy", {}).get(lane_id, 0.0)
    swapped = cfg.get("swap_after") is not None and call_index >= cfg["swap_after"]
    if swapped:  # the "cheater": quietly serves a much weaker model after onboarding
        accuracy = cfg.get("swap_accuracy", 0.2)
    correct = rng.random() < accuracy
    conf = cfg.get("fixed_confidence")
    if conf is None:  # honest Runners report roughly calibrated confidence
        conf = min(0.99, max(0.01, (0.9 if correct else 0.35) + rng.uniform(-0.08, 0.08)))

    item = taskbank.lookup(lane_id, payload)
    if lane_id == "math.final-answer":
        if item:
            ans = item["answer"] if correct else _wrong_number(item["answer"], rng)
            return f"Working through it step by step.\nANSWER: {ans}\nCONFIDENCE: {conf:.2f}"
        expr = pure_expression(payload.get("problem", ""))
        try:
            value = _safe_eval(expr)
            value = int(value) if float(value).is_integer() else round(value, 6)
            return f"Evaluated the expression.\nANSWER: {value}\nCONFIDENCE: {conf:.2f}"
        except Exception:
            return "This simulated runner only knows the built-in task bank and plain arithmetic.\nANSWER: unknown\nCONFIDENCE: 0.05"

    fn = payload.get("function_name", "solution")
    if item and correct:
        return f"```python\n{item['reference']}```\nCONFIDENCE: {conf:.2f}"
    return f"```python\ndef {fn}(*args, **kwargs):\n    return None\n```\nCONFIDENCE: {conf:.2f}"


def _wrong_number(answer: str, rng: random.Random) -> str:
    try:
        v = float(answer)
    except ValueError:
        return "0"
    w = v + rng.choice([-2, -1, 1, 3, 10])
    return str(int(w)) if float(w).is_integer() else str(round(w, 4))
