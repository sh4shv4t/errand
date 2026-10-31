"""Dispatch: pick a Runner for an Errand (docs/RESEARCH.md section 5).

score = quality - lam * price_in_cents - mu * p95_seconds   (a quality-adjusted scoring auction)

Modes:
  sample  Thompson sampling: quality is drawn from each Runner's Beta posterior, so new
          Runners get traffic in proportion to their chance of being best. A small slice
          of traffic is dispatched uniformly at random and logged for offline replay.
  top     deterministic: quality is the lower confidence bound. Reproducible.
"""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass

from . import ratings

PRESETS: dict[str, tuple[float, float]] = {
    # (lam per cent, mu per second of p95 latency)
    "balanced": (0.05, 0.02),
    "cheapest": (0.5, 0.005),
    "fastest": (0.01, 0.2),
    "best": (0.0, 0.0),
}
UNIFORM_SLICE = 0.02


@dataclass
class Candidate:
    runner: dict
    price: int
    stats: ratings.LaneStats
    score: float = 0.0

    def public(self) -> dict:
        return {
            "runner_id": self.runner["id"],
            "name": self.runner["name"],
            "declared_model": self.runner["declared_model"],
            "price_usd": self.price / 1_000_000,
            "expected_pass_rate": round(self.stats.mean, 3),
            "quality_lcb": round(self.stats.lcb, 3),
            "p95_latency_ms": round(self.stats.p95_ms),
            "uptime": round(self.stats.uptime, 3),
            "verified_samples": self.stats.n_verified,
            "score": round(self.score, 4),
        }


def candidates(conn: sqlite3.Connection, lane: str, max_price: int | None = None,
               exclude: set[str] | None = None) -> list[Candidate]:
    out = []
    for r in conn.execute(
        "SELECT r.*, a.name FROM runners r JOIN accounts a ON a.id=r.id WHERE r.status='active'"
    ):
        prices = json.loads(r["lanes"])
        if lane not in prices or (exclude and r["id"] in exclude):
            continue
        price = int(prices[lane])
        if max_price is not None and price > max_price:
            continue
        out.append(Candidate(dict(r), price, ratings.lane_stats(conn, r["id"], lane)))
    return out


def score(c: Candidate, quality: float, preset: str) -> float:
    lam, mu = PRESETS.get(preset, PRESETS["balanced"])
    return quality - lam * (c.price / 10_000) - mu * (c.stats.p95_ms / 1000)


def rank(cands: list[Candidate], preset: str) -> list[Candidate]:
    for c in cands:
        c.score = score(c, c.stats.lcb, preset)
    return sorted(cands, key=lambda c: c.score, reverse=True)


def choose(cands: list[Candidate], preset: str, mode: str, rng: random.Random | None = None) -> tuple[Candidate, str]:
    if not cands:
        raise LookupError("no active runner fits this lane and budget")
    rng = rng or random
    if mode == "top":
        return rank(cands, preset)[0], "top"
    if rng.random() < UNIFORM_SLICE:
        return rng.choice(cands), "uniform"
    for c in cands:
        c.score = score(c, rng.betavariate(c.stats.alpha, c.stats.beta), preset)
    return max(cands, key=lambda c: c.score), "thompson"
