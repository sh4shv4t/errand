"""Runner Ratings (docs/RESEARCH.md sections 4.2 and 7).

Quality is a Beta posterior over pass rate per (Runner, Lane). Evidence is weighted by how
much we trust its source: mystery errands > onboarding exam > verified live errands > Sender
feedback. We rank by the lower confidence bound so 3/3 never outranks 970/1000, and old
evidence decays during inactivity (Glicko-style) so a stale Runner must re-earn its spot.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import asdict, dataclass

from .db import now

WEIGHTS = {"mystery": 3.0, "exam": 2.0, "live": 1.0, "bounty": 1.0}
FEEDBACK_WEIGHT = 0.5
HALF_LIFE_DAYS = 14.0
Z = 1.645  # one-sided 95%


@dataclass
class LaneStats:
    runner_id: str
    lane: str
    alpha: float
    beta: float
    mean: float
    lcb: float
    n_verified: int
    exam_pass: int
    exam_n: int
    mystery_pass: int
    mystery_n: int
    live_n: int
    calls: int
    uptime: float
    p50_ms: float
    p95_ms: float
    brier: float | None
    last_active: float | None

    def public(self) -> dict:
        d = asdict(self)
        d["exam_rate"] = self.exam_pass / self.exam_n if self.exam_n else None
        d["mystery_rate"] = self.mystery_pass / self.mystery_n if self.mystery_n else None
        return d


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def beta_lcb(alpha: float, beta: float, z: float = Z) -> float:
    n = alpha + beta
    mean = alpha / n
    sd = math.sqrt(alpha * beta / (n * n * (n + 1)))
    return max(0.0, mean - z * sd)


def lane_stats(conn: sqlite3.Connection, runner_id: str, lane: str, window: int = 400) -> LaneStats:
    rs = conn.execute(
        "SELECT kind, ok_call, passed, confidence, latency_ms, created_at FROM attempts "
        "WHERE runner_id=? AND lane=? ORDER BY id DESC LIMIT ?",
        (runner_id, lane, window),
    ).fetchall()
    fb = conn.execute(
        "SELECT COALESCE(SUM(feedback=1),0), COALESCE(SUM(feedback=-1),0) FROM errands WHERE runner_id=? AND lane=?",
        (runner_id, lane),
    ).fetchone()

    last_active = rs[0]["created_at"] if rs else None
    idle_days = (now() - last_active) / 86400 if last_active else 0.0
    decay = 0.5 ** (idle_days / HALF_LIFE_DAYS)

    a = b = 0.0
    exam_pass = exam_n = mys_pass = mys_n = live_n = n_verified = 0
    latencies, brier_terms = [], []
    calls = len(rs)
    ok_calls = 0
    for r in rs:
        if r["ok_call"]:
            ok_calls += 1
            if r["latency_ms"] is not None:
                latencies.append(r["latency_ms"])
        passed = r["passed"]
        if r["kind"] in ("live", "bounty"):
            live_n += 1
        if passed is None:
            continue
        n_verified += 1
        w = WEIGHTS.get(r["kind"], 1.0)
        a += w * passed
        b += w * (1 - passed)
        if r["kind"] == "exam":
            exam_n += 1
            exam_pass += passed
        elif r["kind"] == "mystery":
            mys_n += 1
            mys_pass += passed
        if r["confidence"] is not None:
            brier_terms.append((r["confidence"] - passed) ** 2)

    a += FEEDBACK_WEIGHT * fb[0]
    b += FEEDBACK_WEIGHT * fb[1]
    alpha, beta = 1.0 + decay * a, 1.0 + decay * b
    return LaneStats(
        runner_id=runner_id,
        lane=lane,
        alpha=alpha,
        beta=beta,
        mean=alpha / (alpha + beta),
        lcb=beta_lcb(alpha, beta),
        n_verified=n_verified,
        exam_pass=exam_pass,
        exam_n=exam_n,
        mystery_pass=mys_pass,
        mystery_n=mys_n,
        live_n=live_n,
        calls=calls,
        uptime=ok_calls / calls if calls else 1.0,
        p50_ms=_percentile(latencies, 0.5),
        p95_ms=_percentile(latencies, 0.95),
        brier=sum(brier_terms) / len(brier_terms) if brier_terms else None,
        last_active=last_active,
    )


def runner_rating(stats: LaneStats) -> float:
    """Single 0..100 number for browsing. Dispatch never uses it; it uses Sender weights."""
    calib = 1.0 - (stats.brier if stats.brier is not None else 0.25)
    return round(100 * (0.75 * stats.lcb + 0.15 * stats.uptime + 0.10 * calib), 1)
