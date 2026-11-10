"""Demo data: one Sender ("Alan"), three Runners (plus Shady with ERRAND_VILLAIN=1), and their onboarding exams.

Seed credits are written as "demo seed credit" in the ledger so they are never confused
with real PayPal money. If Ollama is running locally, its models are added as real Runners.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

from . import config, db, ledger, service, taskbank  # noqa: F401  (taskbank re-exported for examples)
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
