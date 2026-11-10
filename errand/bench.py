"""`errand bench`: run a real model over the whole task bank and record verified results.

Every item is sent the way a live errand would be (the expected answer is never shown to the model),
then checked by the Lane's verifier. The output JSON feeds the landing page (static/bench.json).

What is measured: pass rate, latency, and what a Sender pays through Errand (Runner price plus fee,
charged only for verified answers). What is estimated: the frontier-model cost, from each Lane's
baseline in lanes.py. The JSON says which is which.
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

from . import config, lanes, runners, taskbank

LANES = ("math.final-answer", "code.python.tests")
SPLITS = ("demo", "exam", "mystery")
DEFAULT_PRICE = {"math.final-answer": 0.0002, "code.python.tests": 0.0003}


def _p95(xs: list[int]) -> int:
    return int(sorted(xs)[max(0, int(round(0.95 * len(xs))) - 1)]) if xs else 0


def run(model: str, base_url: str = "http://localhost:11434/v1", hardware: str = "", limit: int | None = None,
        on_item=None) -> dict:
    runner = {"kind": "openai"}
    cfg = {"base_url": base_url, "model": model, "timeout": 240}
    fee_rate = config.get().take_rate
    out_lanes = {}
    for lane_id in LANES:
        lane = lanes.get(lane_id)
        items = [i for s in SPLITS for i in taskbank.items(lane_id, s)][:limit]
        passed, lat, errors = 0, [], 0
        for n, item in enumerate(items, 1):
            payload = taskbank.payload_for(lane_id, item)
            visible = {k: v for k, v in payload.items() if k != "expected"}
            res = runners.run(runner, cfg, lane_id, visible)
            ok = False
            if res.ok_call:
                ok = bool(lane.verify(payload, lane.extract(res.output)).passed)
                lat.append(res.latency_ms)
            else:
                errors += 1
            passed += ok
            if on_item:
                on_item(lane_id, n, len(items), ok, res.latency_ms)
        price = DEFAULT_PRICE[lane_id] * (1 + fee_rate)
        baseline = lane.baseline_micros / 1e6
        out_lanes[lane_id] = {
            "title": lane.title,
            "tasks": len(items),
            "verified": passed,
            "pass_rate": round(passed / len(items), 3) if items else 0,
            "errors": errors,
            "median_ms": int(statistics.median(lat)) if lat else 0,
            "p95_ms": _p95(lat),
            "errand_cost_usd": round(price * passed, 6),  # only verified answers are paid for
            "frontier_cost_usd": round(baseline * passed, 6),  # same answers from a frontier model, estimated
            "unpaid_wrong_answers": len(items) - passed,
        }
    tasks = sum(l["tasks"] for l in out_lanes.values())
    verified = sum(l["verified"] for l in out_lanes.values())
    errand_cost = sum(l["errand_cost_usd"] for l in out_lanes.values())
    frontier_cost = sum(l["frontier_cost_usd"] for l in out_lanes.values())
    all_ms = [l["median_ms"] for l in out_lanes.values() if l["median_ms"]]
    return {
        "model": model,
        "hardware": hardware,
        "date": time.strftime("%Y-%m-%d"),
        "tasks": tasks,
        "verified": verified,
        "pass_rate": round(verified / tasks, 3) if tasks else 0,
        "errand_cost_usd": round(errand_cost, 6),
        "frontier_cost_usd": round(frontier_cost, 6),
        "savings_pct": round(100 * (1 - errand_cost / frontier_cost), 1) if frontier_cost else 0,
        "unpaid_wrong_answers": tasks - verified,
        "median_ms": int(statistics.median(all_ms)) if all_ms else 0,
        "lanes": out_lanes,
        "notes": {
            "measured": "pass rate (deterministic verifiers), latency, Errand cost (Runner price plus fee, verified answers only)",
            "estimated": "frontier cost per answer, from each Lane's baseline in errand/lanes.py",
        },
    }


def save(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def _summary(lane_rows: dict) -> dict:
    tasks = sum(l["tasks"] for l in lane_rows.values())
    verified = sum(l["verified"] for l in lane_rows.values())
    errand_cost = sum(l["errand_cost_usd"] for l in lane_rows.values())
    frontier_cost = sum(l["frontier_cost_usd"] for l in lane_rows.values())
    meds = [l["median_ms"] for l in lane_rows.values() if l["median_ms"]]
    return {
        "tasks": tasks, "verified": verified, "pass_rate": round(verified / tasks, 3) if tasks else 0,
        "errand_cost_usd": round(errand_cost, 6), "frontier_cost_usd": round(frontier_cost, 6),
        "savings_pct": round(100 * (1 - errand_cost / frontier_cost), 1) if frontier_cost else 0,
        "unpaid_wrong_answers": tasks - verified, "median_ms": int(statistics.median(meds)) if meds else 0,
    }


def combine(results: list[dict], hardware: str = "") -> dict:
    """Several models, plus what Errand's routing does with them: each Lane goes to the model that did best on it."""
    routed = {}
    for lane_id in LANES:
        best = max(results, key=lambda r: (r["lanes"][lane_id]["pass_rate"], -r["lanes"][lane_id]["median_ms"]))
        routed[lane_id] = best["lanes"][lane_id] | {"model": best["model"]}
    return {
        "date": time.strftime("%Y-%m-%d"),
        "hardware": hardware,
        "model": " + ".join(sorted({l["model"] for l in routed.values()})),
        **_summary(routed),
        "lanes": routed,
        "models": [{"model": r["model"], **_summary(r["lanes"]), "lanes": r["lanes"]} for r in results],
        "notes": results[0]["notes"] | {"routing": "each Lane is sent to the model with the highest verified pass rate on it"},
    }
