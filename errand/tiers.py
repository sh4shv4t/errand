"""Sender tiers (docs/RESEARCH.md section 6). Earned by spend AND good behavior, not spend alone.

Thresholds are demo-scale so the tiers are visible in a short session.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .db import now


@dataclass(frozen=True)
class Tier:
    name: str
    min_spend: int  # micros over the trailing 30 days
    max_dispute_rate: float
    fee_multiplier: float
    rate_limit_per_min: int


TIERS = [
    Tier("Trusted", 5_000_000, 0.10, 0.50, 600),
    Tier("Frequent", 1_000_000, 0.25, 0.75, 120),
    Tier("Regular", 0, 1.0, 1.00, 30),
]


def sender_activity(conn: sqlite3.Connection, sender_id: str) -> dict:
    since = now() - 30 * 86400
    r = conn.execute(
        "SELECT COALESCE(SUM(price+fee),0) AS spend, COUNT(*) AS n, COALESCE(SUM(feedback=-1),0) AS disputes, "
        "COALESCE(SUM(baseline),0) AS baseline FROM errands "
        "WHERE sender_id=? AND status='completed' AND kind IN ('live','bounty') AND created_at>=?",
        (sender_id, since),
    ).fetchone()
    n = r["n"] or 0
    return {
        "spend": int(r["spend"]),
        "errands": n,
        "disputes": int(r["disputes"]),
        "dispute_rate": (r["disputes"] / n) if n else 0.0,
        "baseline": int(r["baseline"]),
    }


def tier_for(conn: sqlite3.Connection, sender_id: str) -> Tier:
    act = sender_activity(conn, sender_id)
    for t in TIERS:
        if act["spend"] >= t.min_spend and act["dispute_rate"] <= t.max_dispute_rate:
            return t
    return TIERS[-1]


def next_tier(current: Tier) -> Tier | None:
    i = TIERS.index(current)
    return TIERS[i - 1] if i > 0 else None
