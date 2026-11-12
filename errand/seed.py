"""Demo data: one Sender ("Alan"), three Runners (plus Shady with ERRAND_VILLAIN=1), and their onboarding exams.

Seed credits are written as "demo seed credit" in the ledger so they are never confused
with real PayPal money. If Ollama is running locally, its models are added as real Runners.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from . import config, db, integrity, ledger, service, taskbank  # noqa: F401  (taskbank re-exported for examples)
from .config import to_micros
from .db import PAYPAL_ID

MATH, CODE = "math.final-answer", "code.python.tests"

DEMO_RUNNERS = [
    dict(id="run_duke", name="Duke", email="duke-runner@example.com", model="duke-math-7b (simulated)",
         lanes={MATH: 0.0009},
         cfg={"accuracy": {MATH: 0.93}, "latency_ms": [180, 420]}),
    dict(id="run_ada", name="Ada", email="ada-runner@example.com", model="ada-coder-3b (simulated)",
         lanes={CODE: 0.0016},
         cfg={"accuracy": {CODE: 0.9}, "latency_ms": [300, 700]}),
    dict(id="run_atlas", name="Atlas", email="atlas-runner@example.com", model="atlas-generalist-70b (simulated)",
         lanes={MATH: 0.0045, CODE: 0.006},
         cfg={"accuracy": {MATH: 0.97, CODE: 0.95}, "latency_ms": [900, 1800]}),
    dict(id="run_kepler", name="Kepler", email="kepler-runner@example.com", model="kepler-math-3b (simulated)",
         lanes={MATH: 0.0012},
         cfg={"accuracy": {MATH: 0.88}, "latency_ms": [220, 520]}),
    dict(id="run_grace", name="Grace", email="grace-runner@example.com", model="grace-coder-7b (simulated)",
         lanes={CODE: 0.0024},
         cfg={"accuracy": {CODE: 0.94}, "latency_ms": [400, 900]}),
    dict(id="run_mercer", name="Mercer", email="mercer-runner@example.com", model="mercer-14b (simulated)",
         lanes={MATH: 0.0026, CODE: 0.0034},
         cfg={"accuracy": {MATH: 0.91, CODE: 0.87}, "latency_ms": [500, 1100]}),
    dict(id="run_lin", name="Lin", email="lin-runner@example.com", model="lin-coder-1.5b (simulated)",
         lanes={CODE: 0.0008},
         cfg={"accuracy": {CODE: 0.8}, "latency_ms": [150, 380]}),
    # The villain: passes the exam with a good model, then quietly swaps to a weak one.
    dict(id="run_shady", name="Shady", email="shady-runner@example.com", model="duke-math-7b (simulated)",
         lanes={MATH: 0.0005},
         cfg={"accuracy": {MATH: 0.95}, "latency_ms": [90, 200], "swap_after": 8, "swap_accuracy": 0.15,
              "fixed_confidence": 0.97}),
]


def keys_path() -> Path:
    p = config.get().db_path
    base = Path(p).parent if p != ":memory:" else Path.cwd() / ".errand"
    return base / "demo_keys.json"


def load_keys() -> dict:
    p = keys_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def is_seeded(conn) -> bool:
    return conn.execute("SELECT COUNT(*) FROM accounts WHERE kind='sender'").fetchone()[0] > 0


def _seed_credit(conn, account_id: str, bucket: str, usd: float) -> None:
    with db.tx(conn):
        ledger.move(conn, "demo seed credit (not PayPal)", (PAYPAL_ID, "world"), (account_id, bucket), to_micros(usd))


def ollama_models(base: str = "http://localhost:11434") -> list[str]:
    try:
        r = httpx.get(f"{base}/api/tags", timeout=1.5)
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def hosted_llm_specs() -> list[dict]:
    """Real Runners for a hosted demo, from any OpenAI-compatible API (Groq, OpenRouter, Together...).
    ERRAND_LLM_BASE_URL, ERRAND_LLM_API_KEY and ERRAND_LLM_MODELS (comma separated). Off unless all three are set."""
    base, models = os.environ.get("ERRAND_LLM_BASE_URL", "").strip(), os.environ.get("ERRAND_LLM_MODELS", "")
    if not base or not os.environ.get("ERRAND_LLM_API_KEY"):
        return []
    out = []
    for m in [m.strip() for m in models.split(",") if m.strip()]:
        slug = "".join(ch if ch.isalnum() else "-" for ch in m.split("/")[-1]).strip("-")
        out.append(dict(id=f"run_llm_{slug}"[:40], name=m.split("/")[-1], email=None, model=m,
                        lanes={MATH: 0.0004, CODE: 0.0006}, kind="openai",
                        cfg={"base_url": base, "model": m, "api_key_env": "ERRAND_LLM_API_KEY", "timeout": 60}))
    return out


def seed(conn, with_ollama: bool = True) -> dict:
    db.init(conn)
    if is_seeded(conn):
        return load_keys()
    keys: dict = {"platform": service.set_platform_key(conn)}

    alan, alan_key = service.create_account(conn, "sender", "Alan (demo agent)", "alan@example.com", account_id="snd_alan",
                                            starter_credit=False)
    service.update_settings(conn, alan["id"], {"cap_per_errand_usd": 0.05, "cap_daily_usd": 5, "consent_level": 2})
    _seed_credit(conn, alan["id"], "wallet", 2.0)
    keys["senders"] = {alan["id"]: {"name": alan["name"], "api_key": alan_key}}

    keys["runners"] = {}
    specs = [s for s in DEMO_RUNNERS if s["id"] != "run_shady" or config.get().villain]
    scale = config.get().sim_latency_scale
    config.configure(sim_latency_scale=0.0)  # demo exams run instantly; real Runners keep real latency
    if with_ollama:
        wanted = [m.strip() for m in os.environ.get("ERRAND_OLLAMA_MODELS", "").split(",") if m.strip()]
        found = ollama_models()
        for m in ([m for m in wanted if m in found] if wanted else found[:2]):
            slug = "".join(ch if ch.isalnum() else "-" for ch in m).strip("-")
            specs.append(dict(id=f"run_ollama_{slug}"[:40], name=f"Ollama {m}", email=None, model=m,
                              lanes={MATH: 0.0002, CODE: 0.0003}, kind="openai",
                              cfg={"base_url": "http://localhost:11434/v1", "model": m, "timeout": 180}))
    specs += hosted_llm_specs()
    for spec in specs:
        acct, key = service.create_account(conn, "runner", spec["name"], spec["email"], account_id=spec["id"])
        _seed_credit(conn, acct["id"], "bond", 2.0)
        service.register_runner(conn, acct["id"], spec["model"], spec["lanes"], spec.get("kind", "simulated"),
                                spec["cfg"], start_exam=True, sync_exam=True)
        keys["runners"][acct["id"]] = {"name": acct["name"], "api_key": key}
    config.configure(sim_latency_scale=scale)

    p = keys_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    return keys


def warm_up(conn, n: int, rng_seed: int = 7) -> int:
    """Run n demo errands as Alan so a fresh hosted instance has receipts, savings and ratings to show.
    Uses the built-in task bank, so the simulated Runners can answer. Returns how many completed."""
    import random

    rng = random.Random(rng_seed)
    scale = config.get().sim_latency_scale
    config.configure(sim_latency_scale=0.0)
    done = 0
    try:
        for _ in range(n):
            lane = CODE if rng.random() < 0.25 else MATH
            item = rng.choice(taskbank.items(lane, "demo"))
            try:
                e = service.send_errand(conn, service.get_account(conn, "snd_alan"), lane,
                                        taskbank.payload_for(lane, item), mystery_async=False)
            except service.ErrandError:
                break
            done += e["status"] == "completed"
        _warm_extras(conn, rng)
    finally:
        config.configure(sim_latency_scale=scale)
    return done


# custom questions the simulated Runners cannot answer: they are refunded, which is what judges should see
OFF_BANK = ["How tall is Mount Everest in metres?", "What is the population of Lisbon?"]


def _warm_extras(conn, rng) -> None:
    """Fill the rest of a fresh demo: pinned errands, refunds, audits and real PayPal activity. Each step is
    best effort, so a PayPal hiccup never stops the server from starting."""
    alan = lambda: service.get_account(conn, "snd_alan")  # noqa: E731  (balance changes between steps)
    steps = []
    for runner, lane in (("run_ada", CODE), ("run_mercer", MATH), ("run_grace", CODE), ("run_kepler", MATH)):
        item = rng.choice(taskbank.items(lane, "demo"))
        steps.append(lambda r=runner, l=lane, i=item: service.send_errand(
            conn, alan(), l, taskbank.payload_for(l, i), runner=r, mystery_async=False))
    for q in OFF_BANK:
        steps.append(lambda q=q: service.send_errand(conn, alan(), MATH, {"problem": q}, mystery_async=False))
    for lane in (MATH, CODE, MATH):
        steps.append(lambda l=lane: integrity.run_mystery(conn, l, rng=rng))
    def payouts():  # real PayPal Payouts in sandbox mode, mock otherwise; the two top earners cash out a cent
        rows = conn.execute("SELECT id FROM accounts WHERE kind='runner'").fetchall()
        top = sorted((ledger.balance(conn, r["id"], "earnings"), r["id"]) for r in rows)[-2:]
        for micros, rid in top:
            if micros >= 10_000:
                service.withdraw(conn, service.get_account(conn, rid), 0.01)
    steps.append(payouts)
    steps.append(lambda: service.start_topup(conn, alan(), 5.0))  # an order awaiting a human's approval
    for step in steps:
        try:
            step()
        except Exception:  # noqa: BLE001
            pass
