"""Keeping Runners honest (docs/RESEARCH.md sections 4 and 9).

  onboarding exam   every new Runner answers private exam tasks before it gets traffic
  mystery errands   known-answer tasks mixed into traffic, paid like real work, indistinguishable to the Runner
  swap detection    if a Runner's pass rate after onboarding falls far below its exam rate
                    (two-proportion z-test), we treat it as a model swap: suspend the Runner,
                    slash half its Bond, and refund recent Senders from the slashed amount
"""

from __future__ import annotations

import json
import math
import random
import sqlite3
import threading

from . import config, db, ledger, lanes, runners, taskbank
from .db import PLATFORM_ID, new_id, now

EXAM_SIZE = {"math.final-answer": 6, "code.python.tests": 4}
EXAM_PASS_RATE = 0.5
MIN_BOND = 1_000_000  # $1.00
SLASH_FRACTION = 0.5
SWAP_MIN_SAMPLES = 5
SWAP_Z = 1.96
SWAP_GAP = 0.3
REFUND_WINDOW = 20


def call_index(conn: sqlite3.Connection, runner_id: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM attempts WHERE runner_id=?", (runner_id,)).fetchone()[0])


def execute(conn: sqlite3.Connection, errand_id: str, runner: dict, lane_id: str, payload: dict, kind: str):
    """Run one attempt on one Runner and record it. Returns (RunResult, answer, confidence, Verdict)."""
    lane = lanes.get(lane_id)
    # never show the Runner the expected answer; it is only for the verifier
    visible = {k: v for k, v in payload.items() if k != "expected"}
    res = runners.run(runner, json.loads(runner["config"]), lane_id, visible, call_index(conn, runner["id"]))
    if res.ok_call:
        answer = lane.extract(res.output)
        verdict = lane.verify(payload, answer)
        confidence = lanes.parse_confidence(res.output)
    else:
        answer, confidence, verdict = None, None, lanes.Verdict(False, f"runner error: {res.error}")
    passed = None if verdict.passed is None else int(bool(verdict.passed))
    with db.tx(conn):
        conn.execute(
            "INSERT INTO attempts(errand_id, runner_id, lane, kind, ok_call, passed, confidence, latency_ms, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (errand_id, runner["id"], lane_id, kind, int(res.ok_call), passed, confidence, res.latency_ms, now()),
        )
    return res, answer, confidence, verdict


def _runner(conn, runner_id: str) -> dict:
    r = conn.execute("SELECT r.*, a.name FROM runners r JOIN accounts a ON a.id=r.id WHERE r.id=?", (runner_id,)).fetchone()
    if r is None:
        raise LookupError(f"runner {runner_id} not found")
    return dict(r)


# ---------- onboarding exam ----------

def run_exam(conn: sqlite3.Connection, runner_id: str) -> dict:
    runner = _runner(conn, runner_id)
    results = {}
    for lane_id in json.loads(runner["lanes"]):
        passes = 0
        tasks = taskbank.sample(lane_id, "exam", EXAM_SIZE.get(lane_id, 4))
        for item in tasks:
            _, _, _, verdict = execute(conn, "exam", runner, lane_id, taskbank.payload_for(lane_id, item), "exam")
            passes += bool(verdict.passed)
        results[lane_id] = {"passed": passes, "total": len(tasks)}
    ok = all(r["total"] and r["passed"] / r["total"] >= EXAM_PASS_RATE for r in results.values())
    status = "active" if ok else "rejected"
    with db.tx(conn):
        conn.execute("UPDATE runners SET status=? WHERE id=?", (status, runner_id))
    return {"status": status, "lanes": results}


def run_exam_async(runner_id: str) -> None:
    def work():
        conn = db.connect()
        try:
            run_exam(conn, runner_id)
        finally:
            conn.close()
    threading.Thread(target=work, daemon=True).start()


# ---------- mystery errands ----------

def run_mystery(conn: sqlite3.Connection, lane_id: str, runner_id: str | None = None,
                rng: random.Random | None = None) -> dict | None:
    rng = rng or random.Random()
    pool = [dict(r) for r in conn.execute(
        "SELECT r.*, a.name FROM runners r JOIN accounts a ON a.id=r.id WHERE r.status='active'")]
    pool = [r for r in pool if lane_id in json.loads(r["lanes"]) and (runner_id is None or r["id"] == runner_id)]
    if not pool:
        return None
    # favor Runners with the least mystery evidence so every rating stays fresh
    counts = {r["id"]: conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE runner_id=? AND lane=? AND kind='mystery'", (r["id"], lane_id)
    ).fetchone()[0] for r in pool}
    weights = [1.0 / (1 + counts[r["id"]]) for r in pool]
    runner = rng.choices(pool, weights=weights, k=1)[0]
    item = rng.choice(taskbank.items(lane_id, "mystery"))
    payload = taskbank.payload_for(lane_id, item, with_answer=True)
    price = int(json.loads(runner["lanes"])[lane_id])

    errand_id = new_id("err")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO errands(id, sender_id, lane, payload, budget, kind, status, runner_id, policy, created_at) "
            "VALUES (?,?,?,?,?,'mystery','running',?,'mystery',?)",
            (errand_id, PLATFORM_ID, lane_id, db.dumps(payload), price, runner["id"], now()),
        )
    res, answer, conf, verdict = execute(conn, errand_id, runner, lane_id, payload, "mystery")
    paid = res.ok_call
    with db.tx(conn):
        if paid:  # mystery errands are paid like real work so they are indistinguishable
            ledger.move(conn, "mystery errand payment", (PLATFORM_ID, "revenue"), (runner["id"], "earnings"),
                        price, ref=errand_id, allow_negative=True)
        conn.execute(
            "UPDATE errands SET status='completed', output=?, answer=?, confidence=?, verdict=?, detail=?, price=?, "
            "latency_ms=?, attempts=1, completed_at=? WHERE id=?",
            (res.output, answer, conf, "passed" if verdict.passed else "failed", verdict.detail,
             price if paid else 0, res.latency_ms, now(), errand_id),
        )
    flag = check_swap(conn, runner["id"], lane_id)
    return {"errand_id": errand_id, "runner_id": runner["id"], "passed": bool(verdict.passed), "flag": flag}


def maybe_mystery_async(lane_id: str) -> None:
    if random.random() >= config.get().mystery_rate:
        return

    def work():
        conn = db.connect()
        try:
            run_mystery(conn, lane_id)
        finally:
            conn.close()
    threading.Thread(target=work, daemon=True).start()


# ---------- model-swap detection and slashing ----------

def swap_test(exam_pass: int, exam_n: int, post_pass: int, post_n: int) -> tuple[float, float]:
    """Two-proportion z-test. Returns (z, gap) where gap = exam_rate - post_rate."""
    if exam_n == 0 or post_n == 0:
        return 0.0, 0.0
    p1, p2 = exam_pass / exam_n, post_pass / post_n
    pooled = (exam_pass + post_pass) / (exam_n + post_n)
    se = math.sqrt(max(pooled * (1 - pooled), 1e-9) * (1 / exam_n + 1 / post_n))
    return (p1 - p2) / se, p1 - p2


def check_swap(conn: sqlite3.Connection, runner_id: str, lane_id: str) -> dict | None:
    runner = _runner(conn, runner_id)
    if runner["status"] != "active":
        return None
    r = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN kind='exam' THEN passed END),0) AS ep, "
        "COALESCE(SUM(kind='exam' AND passed IS NOT NULL),0) AS en, "
        "COALESCE(SUM(CASE WHEN kind!='exam' THEN passed END),0) AS pp, "
        "COALESCE(SUM(kind!='exam' AND passed IS NOT NULL),0) AS pn "
        "FROM attempts WHERE runner_id=? AND lane=?",
        (runner_id, lane_id),
    ).fetchone()
    if r["pn"] < SWAP_MIN_SAMPLES:
        return None
    z, gap = swap_test(r["ep"], r["en"], r["pp"], r["pn"])
    if z < SWAP_Z or gap < SWAP_GAP:
        return None
    detail = (f"Exam pass rate {r['ep']}/{r['en']} vs {r['pp']}/{r['pn']} after onboarding "
              f"(z={z:.2f}). Consistent with serving a different model than the one that passed the exam.")
    return slash(conn, runner_id, lane_id, "model_swap_suspected", detail)


def slash(conn: sqlite3.Connection, runner_id: str, lane_id: str, kind: str, detail: str) -> dict:
    with db.tx(conn):
        bond = ledger.balance(conn, runner_id, "bond")
        slashed = int(bond * SLASH_FRACTION)
        remaining = slashed
        refunded = 0
        recent = conn.execute(
            "SELECT id, sender_id, price FROM errands WHERE runner_id=? AND lane=? AND kind='live' "
            "AND status='completed' ORDER BY completed_at DESC LIMIT ?",
            (runner_id, lane_id, REFUND_WINDOW),
        ).fetchall()
        for e in recent:
            amt = min(e["price"], remaining)
            if amt <= 0:
                break
            ledger.move(conn, "refund from slashed bond", (runner_id, "bond"), (e["sender_id"], "wallet"), amt, ref=e["id"])
            remaining -= amt
            refunded += amt
        if remaining > 0:
            ledger.move(conn, "slashed bond", (runner_id, "bond"), (PLATFORM_ID, "revenue"), remaining)
        conn.execute("UPDATE runners SET status='suspended' WHERE id=?", (runner_id,))
        conn.execute(
            "INSERT INTO flags(runner_id, lane, kind, detail, slashed, refunded, created_at) VALUES (?,?,?,?,?,?,?)",
            (runner_id, lane_id, kind, detail, slashed, refunded, now()),
        )
    return {"runner_id": runner_id, "lane": lane_id, "kind": kind, "detail": detail,
            "slashed_usd": slashed / 1e6, "refunded_usd": refunded / 1e6}
