"""Lanes: task categories with a prompt format, an answer parser, and a verifier.

MVP lanes are verifiable on purpose (docs/RESEARCH.md section 4): verifiers are cheap,
unbiased, and cannot be gamed with style the way an LLM judge can.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

_CONF_RE = re.compile(r"CONFIDENCE\s*[:=]\s*([01](?:\.\d+)?)", re.I)


class PayloadError(ValueError):
    pass


def parse_confidence(text: str) -> float | None:
    m = _CONF_RE.search(text or "")
    if not m:
        return None
    return max(0.0, min(1.0, float(m.group(1))))


@dataclass(frozen=True)
class Verdict:
    passed: bool | None  # None means delivered but not verifiable (no ground truth supplied)
    detail: str


@dataclass(frozen=True)
class Lane:
    id: str
    title: str
    description: str
    baseline_micros: int  # estimated cost if the Sender's frontier model did this itself
    payload_fields: tuple[str, ...]
    build_prompt: Callable[[dict], str]
    extract: Callable[[str], str | None]
    verify: Callable[[dict, str | None], Verdict]

    def validate(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            raise PayloadError("payload must be an object")
        missing = [f for f in self.payload_fields if not str(payload.get(f, "")).strip()]
        if missing:
            raise PayloadError(f"{self.id} payload is missing: {', '.join(missing)}")

    def public(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "payload_fields": list(self.payload_fields),
            "baseline_usd": self.baseline_micros / 1_000_000,
        }


# ---------- math.final-answer ----------

_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?(?:/\d+)?")


def _to_number(text: str) -> Fraction | None:
    t = text.strip().replace(",", "").replace("$", "").rstrip("%").strip()
    try:
        return Fraction(t)
    except (ValueError, ZeroDivisionError):
        return None


def math_prompt(p: dict) -> str:
    return (
        "Solve the problem. Think briefly, then end with exactly two lines:\n"
        "ANSWER: <final numeric answer only>\nCONFIDENCE: <probability 0 to 1 that your answer is correct>\n\n"
        f"Problem: {p['problem']}"
    )


def math_extract(output: str) -> str | None:
    m = re.search(r"ANSWER\s*[:=]\s*(.+)", output or "", re.I)
    candidates = _NUM_RE.findall(m.group(1)) if m else _NUM_RE.findall(output or "")
    if not candidates:
        return None
    value = candidates[0] if m else candidates[-1]
    num = _to_number(value)
    if num is None:
        return None
    return str(num.numerator) if num.denominator == 1 else format(float(num), "g")


def math_verify(p: dict, answer: str | None) -> Verdict:
    if answer is None:
        return Verdict(False, "no numeric answer found")
    expected = p.get("expected")
    if expected is None or str(expected).strip() == "":
        return Verdict(None, "delivered; no expected answer supplied so it was not checked")
    a, e = _to_number(answer), _to_number(str(expected))
    if a is None or e is None:
        return Verdict(False, f"could not compare {answer!r} with {expected!r}")
    ok = abs(float(a) - float(e)) <= 1e-6 * max(1.0, abs(float(e)))
    return Verdict(ok, "matches expected answer" if ok else f"expected {expected}, got {answer}")


# ---------- code.python.tests ----------

_FENCE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def code_prompt(p: dict) -> str:
    return (
        f"Write a Python function named `{p['function_name']}`.\n\nSpecification: {p['spec']}\n\n"
        "It must pass these tests:\n```python\n" + p["tests"] + "\n```\n\n"
        "Reply with one ```python code block containing only the function (and any imports), "
        "then a final line: CONFIDENCE: <probability 0 to 1 that it passes>."
    )


def code_extract(output: str) -> str | None:
    blocks = _FENCE_RE.findall(output or "")
    code = blocks[0] if blocks else (output or "")
    code = _CONF_RE.sub("", code).strip()
    return code or None


def code_verify(p: dict, code: str | None, timeout: float = 10.0) -> Verdict:
    if not code:
        return Verdict(False, "no code returned")
    if f"def {p['function_name']}" not in code:
        return Verdict(False, f"function {p['function_name']} not defined")
    # Runs untrusted code in a separate isolated interpreter with a timeout and a scratch cwd.
    # This is a hackathon-grade sandbox, not a security boundary; see README "Limitations".
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "check.py"
        f.write_text(code + "\n\n" + p["tests"] + "\nprint('ERRAND_OK')\n", encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-I", str(f)], cwd=d, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return Verdict(False, f"tests timed out after {timeout:.0f}s")
    if proc.returncode == 0 and "ERRAND_OK" in proc.stdout:
        return Verdict(True, "all tests passed")
    err = (proc.stderr or proc.stdout).strip().splitlines()
    return Verdict(False, "tests failed: " + (err[-1] if err else f"exit {proc.returncode}"))


LANES: dict[str, Lane] = {
    "math.final-answer": Lane(
        id="math.final-answer",
        title="Math, final answer",
        description="Word problems and competition-style math with a single numeric answer. "
        "Pass `expected` to have the answer checked; otherwise it is delivered unchecked.",
        baseline_micros=12_000,  # about 1.2k output tokens at $10 per million
        payload_fields=("problem",),
        build_prompt=math_prompt,
        extract=math_extract,
        verify=math_verify,
    ),
    "code.python.tests": Lane(
        id="code.python.tests",
        title="Python function with tests",
        description="Write one Python function. The Sender supplies assert-style tests; payment releases only if they pass.",
        baseline_micros=20_000,  # about 2k output tokens at $10 per million
        payload_fields=("spec", "function_name", "tests"),
        build_prompt=code_prompt,
        extract=code_extract,
        verify=code_verify,
    ),
}


def get(lane_id: str) -> Lane:
    try:
        return LANES[lane_id]
    except KeyError:
        raise PayloadError(f"unknown lane {lane_id!r}; choose one of {', '.join(LANES)}") from None
