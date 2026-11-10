"""Errand business logic: accounts, the errand lifecycle, PayPal money flows, and read models.

Every function takes an open sqlite3 connection so the API, CLI, MCP server and tests share it.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3

from . import config, db, dispatch, integrity, lanes, ledger, ratings, tiers
from .config import to_micros, to_usd
from .db import PAYPAL_ID, PLATFORM_ID, new_id, now
from .paypal import PayPalError
from .paypal import client as paypal

MAX_ATTEMPTS = 3
DIVIDEND_SHARE = 0.20  # share of the platform fee returned to Senders who share Receipts (consent >= 2)
TOPUP_MIN, TOPUP_MAX = 1_000_000, 500_000_000
STARTER_CREDIT = 1_000_000  # $1 of platform-funded credit, so a new Sender's first errands need no PayPal step


class ErrandError(Exception):
    status = 400


class MandateError(ErrandError):
    status = 403


class FundsError(ErrandError):
    status = 402


class NotFound(ErrandError):
    status = 404


# ---------- accounts ----------

def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_account(conn: sqlite3.Connection, kind: str, name: str, email: str | None = None,
                   account_id: str | None = None, starter_credit: bool = True) -> tuple[dict, str]:
    if kind not in ("sender", "runner"):
        raise ErrandError("kind must be 'sender' or 'runner'")
    name = (name or "").strip()
    if not name:
        raise ErrandError("name is required")
    api_key = "erk_" + secrets.token_urlsafe(24)
    account_id = account_id or new_id("snd" if kind == "sender" else "run")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO accounts(id, kind, name, email, api_key_hash, created_at, paypal_email) VALUES (?,?,?,?,?,?,?)",
            (account_id, kind, name, email, hash_key(api_key), now(), email),
        )
        if kind == "sender" and starter_credit:
            ledger.move(conn, "starter credit (platform funded, not PayPal)", (PLATFORM_ID, "promo"),
                        (account_id, "wallet"), STARTER_CREDIT, allow_negative=True)
    return get_account(conn, account_id), api_key


def get_account(conn: sqlite3.Connection, account_id: str) -> dict:
    a = db.row(conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone())
    if a is None:
        raise NotFound(f"account {account_id} not found")
    a.pop("api_key_hash", None)
    return a


def account_by_key(conn: sqlite3.Connection, api_key: str) -> dict | None:
    a = db.row(conn.execute("SELECT * FROM accounts WHERE api_key_hash=?", (hash_key(api_key),)).fetchone())
    if a:
        a.pop("api_key_hash", None)
    return a


def set_platform_key(conn: sqlite3.Connection) -> str:
    key = "erk_" + secrets.token_urlsafe(24)
    with db.tx(conn):
        conn.execute("UPDATE accounts SET api_key_hash=? WHERE id=?", (hash_key(key), PLATFORM_ID))
    return key


def update_settings(conn: sqlite3.Connection, account_id: str, data: dict) -> dict:
    fields = {}
    if "consent_level" in data and data["consent_level"] is not None:
        level = int(data["consent_level"])
        if level not in (0, 1, 2, 3):
            raise ErrandError("consent_level must be 0, 1, 2 or 3")
        fields["consent_level"] = level
    for key, col in (("cap_per_errand_usd", "cap_per_errand"), ("cap_daily_usd", "cap_daily")):
        if data.get(key) is not None:
            v = to_micros(data[key])
            if v <= 0:
                raise ErrandError(f"{key} must be positive")
            fields[col] = v
    if data.get("preset") is not None:
        if data["preset"] not in dispatch.PRESETS:
            raise ErrandError(f"preset must be one of {', '.join(dispatch.PRESETS)}")
        fields["preset"] = data["preset"]
    if data.get("paypal_email") is not None:
        fields["paypal_email"] = str(data["paypal_email"]).strip() or None
    if data.get("name"):
        fields["name"] = str(data["name"]).strip()
    if fields:
        with db.tx(conn):
            conn.execute(f"UPDATE accounts SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                         (*fields.values(), account_id))
    return get_account(conn, account_id)


# ---------- runners ----------

def register_runner(conn: sqlite3.Connection, runner_id: str, declared_model: str, lane_prices_usd: dict,
                    kind: str, cfg: dict, start_exam: bool = True, sync_exam: bool = False) -> dict:
    acct = get_account(conn, runner_id)
    if acct["kind"] != "runner":
        raise ErrandError("only runner accounts can register a model")
    if kind not in ("openai", "webhook", "simulated"):
        raise ErrandError("kind must be openai, webhook or simulated")
    if kind == "simulated" and not config.get().demo:
        raise ErrandError("simulated runners are only allowed in demo mode")
    if kind == "openai" and not (cfg.get("base_url") and cfg.get("model")):
        raise ErrandError("openai runners need config.base_url and config.model")
    if kind == "webhook" and not cfg.get("url"):
        raise ErrandError("webhook runners need config.url")
    prices = {}
    for lane_id, usd in (lane_prices_usd or {}).items():
        lanes.get(lane_id)
        p = to_micros(usd)
        if p <= 0:
            raise ErrandError("prices must be positive")
        prices[lane_id] = p
    if not prices:
        raise ErrandError("choose at least one lane with a price")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO runners(id, declared_model, lanes, kind, config, status, created_at) VALUES (?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET declared_model=excluded.declared_model, lanes=excluded.lanes, "
            "kind=excluded.kind, config=excluded.config, status='onboarding'",
            (runner_id, declared_model.strip() or "unnamed-model", db.dumps(prices), kind, db.dumps(cfg),
             "onboarding", now()),
        )
    if start_exam:
        maybe_start_exam(conn, runner_id, sync=sync_exam)
    return runner_view(conn, runner_id)


def maybe_start_exam(conn: sqlite3.Connection, runner_id: str, sync: bool = False) -> str:
    r = conn.execute("SELECT status FROM runners WHERE id=?", (runner_id,)).fetchone()
    if r is None or r["status"] != "onboarding":
        return r["status"] if r else "unregistered"
    if sync:
        return integrity.run_exam(conn, runner_id)["status"]
    integrity.run_exam_async(runner_id)
    return "onboarding"


# ---------- errands ----------

def _runner_pay(conn, runner_id: str, amount: int) -> list[tuple[str, str, int]]:
    """Ledger entries paying a Runner. Earnings fill the Bond first, so nobody has to post one up front."""
    to_bond = min(amount, max(0, integrity.MIN_BOND - ledger.balance(conn, runner_id, "bond")))
    return [(runner_id, "bond", to_bond), (runner_id, "earnings", amount - to_bond)]


def resolve_runner(conn, ref: str) -> str:
    """A Runner id (run_duke) or display name (Duke), case-insensitive."""
    ref = (ref or "").strip()
    r = conn.execute("SELECT r.id FROM runners r JOIN accounts a ON a.id=r.id WHERE r.id=? OR lower(a.name)=lower(?)",
                     (ref, ref)).fetchone()
    if r is None:
        raise NotFound(f"no runner called {ref!r}")
    return r[0]


_DEF_RE = re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*\(")
_ASSERT_CALL_RE = re.compile(r"\bassert\s+(?:not\s+)?\(?\s*([A-Za-z_]\w*)\s*\(")
_CODE_HINT_RE = re.compile(r"\b(write|implement|create|add|build)\b.*\bfunction\b|\bdef\s+\w+\s*\(|\.py\b|_function_"
                           r"|\bpython\s+function\b|\bfunction\s+`[A-Za-z_]\w*\s*\(", re.I | re.S)


def infer_errand(task: str, check: str | None = None) -> tuple[str, dict]:
    """Turn a plain task (plus an optional expected answer or assert tests) into a Lane and payload."""
    task, check = (task or "").strip(), (check or "").strip()
    if not task:
        raise ErrandError("task is required")
    if "assert" in check:
        m = _DEF_RE.search(task) or _ASSERT_CALL_RE.search(check)
        if not m:
            raise ErrandError("name the function in the task (def name(...)) or call it in the asserts")
        return "code.python.tests", {"function_name": m.group(1), "spec": task, "tests": check}
    if _CODE_HINT_RE.search(task):
        raise ErrandError("code errands need tests: pass Python assert lines as `check`, "
                          "so payment is released only if they pass")
    return "math.final-answer", {"problem": task} | ({"expected": check} if check else {})


def delegate(conn: sqlite3.Connection, sender: dict, task: str, check: str | None = None,
             budget_usd: float | None = None, runner: str | None = None, preset: str | None = None,
             fallback: bool = True) -> dict:
    """The one-call entry point: Errand picks the Lane, the Runner, and verifies before paying."""
    lane_id, payload = infer_errand(task, check)
    return send_errand(conn, sender, lane_id, payload, budget_usd, preset, runner=runner, fallback=fallback)


def _spent_last_24h(conn, sender_id: str) -> int:
    r = conn.execute(
        "SELECT COALESCE(SUM(price+fee),0) FROM errands WHERE sender_id=? AND status='completed' AND created_at>=?",
        (sender_id, now() - 86400),
    ).fetchone()
    return int(r[0])


def send_errand(conn: sqlite3.Connection, sender: dict, lane_id: str, payload: dict,
                budget_usd: float | None = None, preset: str | None = None, mode: str = "sample",
                mystery_async: bool = True, runner: str | None = None, fallback: bool = True) -> dict:
    if sender["kind"] != "sender":
        raise ErrandError("only sender accounts can post errands")
    lane = lanes.get(lane_id)
    try:
        lane.validate(payload)
    except lanes.PayloadError as e:
        raise ErrandError(str(e)) from None
    if lane_id == "code.python.tests":  # broken tests can never pass: bounce them before anyone is paid to try
        try:
            compile(payload["tests"], "<tests>", "exec")
        except SyntaxError as e:
            raise ErrandError(f"your tests do not parse (line {e.lineno}: {e.msg}); fix them and send again. "
                              "Nothing was charged.") from None
    if mode not in ("sample", "top"):
        raise ErrandError("mode must be 'sample' or 'top'")
    preset = preset or sender.get("preset") or "balanced"
    pinned = resolve_runner(conn, runner) if runner else None
    budget = to_micros(budget_usd) if budget_usd is not None else sender["cap_per_errand"]
    if budget <= 0:
        raise ErrandError("budget must be positive")
    if budget > sender["cap_per_errand"]:
        raise MandateError(f"budget ${to_usd(budget):.4f} exceeds your per-errand cap ${to_usd(sender['cap_per_errand']):.2f}")
    if _spent_last_24h(conn, sender["id"]) + budget > sender["cap_daily"]:
        raise MandateError(f"this errand could exceed your daily cap of ${to_usd(sender['cap_daily']):.2f}")

    tier = tiers.tier_for(conn, sender["id"])
    fee_rate = config.get().take_rate * tier.fee_multiplier
    max_price = int(budget / (1 + fee_rate))
    errand_id = new_id("err")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO errands(id, sender_id, lane, payload, budget, kind, status, baseline, created_at) "
            "VALUES (?,?,?,?,?,'live','running',?,?)",
            (errand_id, sender["id"], lane_id, db.dumps(payload), budget, lane.baseline_micros, now()),
        )

    tried: set[str] = set()
    last_detail = "no active runner fits this lane and budget"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        cands = dispatch.candidates(conn, lane_id, max_price, exclude=tried)
        if pinned and (attempt == 1 or not fallback):
            mine = [c for c in cands if c.runner["id"] == pinned]
            if mine:
                cands = mine
            elif not fallback:
                last_detail = "the Runner you picked is not available for this lane and budget"
                break
        if not cands:
            break
        cand, policy = dispatch.choose(cands, preset, mode)
        if cand.runner["id"] == pinned:
            policy = "pinned"
        runner = cand.runner
        tried.add(runner["id"])
        price = cand.price
        fee = int(round(price * fee_rate))
        try:
            with db.tx(conn):
                ledger.move(conn, "escrow hold", (sender["id"], "wallet"), (sender["id"], "escrow"), price + fee, ref=errand_id)
        except ledger.InsufficientFunds as e:
            _finish(conn, errand_id, "failed", attempts=attempt - 1,
                    detail=f"insufficient funds: needs ${to_usd(e.needed):.4f}, wallet has ${to_usd(e.available):.4f}")
            raise FundsError(f"insufficient wallet balance (${to_usd(e.available):.4f}); top up to continue") from None

        res, answer, conf, verdict = integrity.execute(conn, errand_id, runner, lane_id, payload, "live")
        if res.ok_call and verdict.passed is not False:
            dividend = int(fee * DIVIDEND_SHARE) if sender.get("consent_level", 0) >= 2 else 0
            with db.tx(conn):
                ledger.post(conn, "errand settled", [
                    (sender["id"], "escrow", -(price + fee)),
                    *_runner_pay(conn, runner["id"], price),
                    (PLATFORM_ID, "revenue", fee - dividend),
                    (sender["id"], "wallet", dividend),
                ], ref=errand_id)
            _finish(conn, errand_id, "completed", runner_id=runner["id"], output=res.output, answer=answer,
                    confidence=conf, verdict="passed" if verdict.passed else "delivered", detail=verdict.detail,
                    price=price, fee=fee, dividend=dividend, latency_ms=res.latency_ms, attempts=attempt, policy=policy)
            break
        with db.tx(conn):
            ledger.move(conn, "escrow refund", (sender["id"], "escrow"), (sender["id"], "wallet"), price + fee, ref=errand_id)
        last_detail = f"{runner['name']}: {verdict.detail}"
        integrity.check_swap(conn, runner["id"], lane_id)

    e = errand_row(conn, errand_id)
    if e["status"] == "running":
        _finish(conn, errand_id, "failed", attempts=len(tried), detail=last_detail)
    elif e["runner_id"]:
        integrity.check_swap(conn, e["runner_id"], lane_id)
    if mystery_async:
        integrity.maybe_mystery_async(lane_id)
    return errand_public(errand_row(conn, errand_id), viewer="sender")


def _finish(conn, errand_id: str, status: str, **fields) -> None:
    fields["status"] = status
    fields["completed_at"] = now()
    with db.tx(conn):
        conn.execute(f"UPDATE errands SET {', '.join(f'{k}=?' for k in fields)} WHERE id=?",
                     (*fields.values(), errand_id))


def errand_row(conn, errand_id: str) -> dict:
    e = db.row(conn.execute(
        "SELECT e.*, a.name AS runner_name, r.declared_model FROM errands e "
        "LEFT JOIN accounts a ON a.id=e.runner_id LEFT JOIN runners r ON r.id=e.runner_id WHERE e.id=?",
        (errand_id,)).fetchone())
    if e is None:
        raise NotFound(f"errand {errand_id} not found")
    return e


def errand_public(e: dict, viewer: str = "sender") -> dict:
    total = e["price"] + e["fee"] - e.get("dividend", 0)
    out = {
        "id": e["id"],
        "lane": e["lane"],
        "kind": e["kind"],
        "status": e["status"],
        "verdict": e["verdict"],
        "answer": e["answer"],
        "output": e["output"],
        "confidence": e["confidence"],
        "detail": e["detail"],
        "runner": {"id": e["runner_id"], "name": e.get("runner_name"), "model": e.get("declared_model")} if e["runner_id"] else None,
        "price_usd": to_usd(e["price"]),
        "fee_usd": to_usd(e["fee"]),
        "dividend_usd": to_usd(e.get("dividend", 0)),
        "total_usd": to_usd(total),
        "baseline_usd": to_usd(e["baseline"]),
        "saved_usd": to_usd(max(0, e["baseline"] - total)) if e["status"] == "completed" else 0.0,
        "latency_ms": e["latency_ms"],
        "attempts": e["attempts"],
        "policy": e["policy"],
        "feedback": e["feedback"],
        "created_at": e["created_at"],
        "completed_at": e["completed_at"],
    }
    if viewer == "sender":
        out["payload"] = json.loads(e["payload"])
    else:  # Runners see the task but never who sent it
        p = json.loads(e["payload"])
        p.pop("expected", None)
        out["payload"] = p
        out["fee_usd"] = out["dividend_usd"] = out["baseline_usd"] = out["saved_usd"] = None
    return out


def list_errands(conn, account: dict, limit: int = 200) -> list[dict]:
    col = "sender_id" if account["kind"] == "sender" else "runner_id"
    ids = [r[0] for r in conn.execute(
        f"SELECT id FROM errands WHERE {col}=? ORDER BY created_at DESC LIMIT ?", (account["id"], limit))]
    viewer = "sender" if account["kind"] == "sender" else "runner"
    return [errand_public(errand_row(conn, i), viewer) for i in ids]


def give_feedback(conn, sender: dict, errand_id: str, accepted: bool) -> dict:
    e = errand_row(conn, errand_id)
    if e["sender_id"] != sender["id"]:
        raise NotFound(f"errand {errand_id} not found")
    if e["status"] != "completed":
        raise ErrandError("feedback is only accepted on completed errands")
    with db.tx(conn):
        conn.execute("UPDATE errands SET feedback=? WHERE id=?", (1 if accepted else -1, errand_id))
    return errand_public(errand_row(conn, errand_id))


def recommend(conn, lane_id: str, preset: str = "balanced", budget_usd: float | None = None) -> dict:
    lane = lanes.get(lane_id)
    max_price = to_micros(budget_usd) if budget_usd else None
    ranked = dispatch.rank(dispatch.candidates(conn, lane_id, max_price), preset)
    return {
        "lane": lane.public(),
        "preset": preset,
        "should_delegate": bool(ranked) and ranked[0].stats.mean >= 0.6,
        "runners": [c.public() for c in ranked],
    }


# ---------- PayPal: top-ups (Orders v2, intent CAPTURE) ----------

def _record_op(conn, account_id: str, kind: str, purpose: str, amount: int, paypal_id: str | None,
               status: str, meta: dict | None = None, op_id: str | None = None) -> str:
    op_id = op_id or new_id("pp")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO paypal_ops(id, account_id, kind, purpose, paypal_id, amount, status, meta, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (op_id, account_id, kind, purpose, paypal_id, amount, status, db.dumps(meta or {}), now(), now()),
        )
    return op_id


def _op_by_order(conn, order_id: str) -> dict:
    op = db.row(conn.execute("SELECT * FROM paypal_ops WHERE paypal_id=? AND kind='order'", (order_id,)).fetchone())
    if op is None:
        raise NotFound(f"unknown PayPal order {order_id}")
    return op


def _set_op(conn, op_id: str, status: str, meta: dict | None = None) -> None:
    with db.tx(conn):
        if meta is None:
            conn.execute("UPDATE paypal_ops SET status=?, updated_at=? WHERE id=?", (status, now(), op_id))
        else:
            conn.execute("UPDATE paypal_ops SET status=?, meta=?, updated_at=? WHERE id=?",
                         (status, db.dumps(meta), now(), op_id))


def start_topup(conn, account: dict, amount_usd: float, purpose: str = "wallet", return_path: str = "/dashboard") -> dict:
    if purpose not in ("wallet", "bond"):
        raise ErrandError("purpose must be wallet or bond")
    if purpose == "wallet" and account["kind"] != "sender":
        raise ErrandError("only senders have a wallet; runners top up their bond")
    if purpose == "bond" and account["kind"] != "runner":
        raise ErrandError("only runners post a bond")
    amount = to_micros(amount_usd)
    if not TOPUP_MIN <= amount <= TOPUP_MAX:
        raise ErrandError("top-ups must be between $1 and $500")
    base = config.get().base_url
    op_id = new_id("pp")
    order = paypal.create_order(amount, "CAPTURE", f"{base}/paypal/return?next={return_path}",
                                f"{base}/paypal/cancel?next={return_path}", op_id,
                                f"Errand {'wallet top-up' if purpose == 'wallet' else 'runner bond'}")
    _record_op(conn, account["id"], "order", purpose, amount, order["id"], "created",
               {"return_path": return_path}, op_id=op_id)
    return {"order_id": order["id"], "approve_url": order["approve_url"], "amount_usd": to_usd(amount),
            "purpose": purpose, "paypal_mode": paypal.mode}


def mock_approve(conn, order_id: str) -> dict:
    op = _op_by_order(conn, order_id)
    if paypal.live:
        raise ErrandError("mock approval is disabled when PayPal sandbox keys are configured")
    if op["status"] == "created":
        _set_op(conn, op["id"], "approved")
    return op


def complete_order(conn, order_id: str) -> dict:
    """Called when the payer returns from PayPal. Idempotent."""
    op = _op_by_order(conn, order_id)
    if op["status"] in ("completed", "settled", "voided"):
        return {"op": op, "already": True}
    if not paypal.live and op["status"] != "approved":
        raise ErrandError("order was not approved")
    if op["purpose"] == "bounty":
        return {"op": op, "bounty": _run_bounty(conn, op)}
    cap = paypal.capture_order(order_id)
    if cap["status"] != "COMPLETED":
        _set_op(conn, op["id"], f"capture_{cap['status'].lower()}")
        raise ErrandError(f"PayPal capture status {cap['status']}")
    with db.tx(conn):
        ledger.move(conn, f"PayPal {op['purpose']} top-up", (PAYPAL_ID, "world"), (op["account_id"], op["purpose"]),
                    op["amount"], ref=order_id)
        meta = json.loads(op["meta"] or "{}") | {"capture_id": cap["capture_id"]}
        conn.execute("UPDATE paypal_ops SET status='completed', meta=?, updated_at=? WHERE id=?",
                     (db.dumps(meta), now(), op["id"]))
    if op["purpose"] == "bond":
        maybe_start_exam(conn, op["account_id"])
    return {"op": db.row(conn.execute("SELECT * FROM paypal_ops WHERE id=?", (op["id"],)).fetchone()), "already": False}


def cancel_order(conn, order_id: str) -> None:
    op = _op_by_order(conn, order_id)
    if op["status"] in ("created", "approved"):
        _set_op(conn, op["id"], "cancelled")


# ---------- PayPal: bounties (Orders v2, intent AUTHORIZE: capture on verified, void on fail) ----------

def start_bounty(conn, sender: dict, lane_id: str, payload: dict, amount_usd: float) -> dict:
    if sender["kind"] != "sender":
        raise ErrandError("only senders can post bounties")
    lane = lanes.get(lane_id)
    try:
        lane.validate(payload)
    except lanes.PayloadError as e:
        raise ErrandError(str(e)) from None
    amount = to_micros(amount_usd)
    if not TOPUP_MIN <= amount <= TOPUP_MAX:
        raise ErrandError("bounties must be between $1 and $500")
    base = config.get().base_url
    op_id = new_id("pp")
    order = paypal.create_order(amount, "AUTHORIZE", f"{base}/paypal/return?next=/dashboard",
                                f"{base}/paypal/cancel?next=/dashboard", op_id, f"Errand bounty: {lane.title}")
    _record_op(conn, sender["id"], "order", "bounty", amount, order["id"], "created",
               {"lane": lane_id, "payload": payload}, op_id=op_id)
    return {"order_id": order["id"], "approve_url": order["approve_url"], "amount_usd": to_usd(amount),
            "paypal_mode": paypal.mode}


def _run_bounty(conn, op: dict) -> dict:
    meta = json.loads(op["meta"])
    auth = paypal.authorize_order(op["paypal_id"])
    meta["authorization_id"] = auth["authorization_id"]
    _set_op(conn, op["id"], "authorized", meta)

    sender = get_account(conn, op["account_id"])
    lane_id, payload, amount = meta["lane"], meta["payload"], op["amount"]
    fee = int(round(amount * config.get().take_rate))
    errand_id = new_id("err")
    with db.tx(conn):
        conn.execute(
            "INSERT INTO errands(id, sender_id, lane, payload, budget, kind, status, baseline, bounty_op, created_at) "
            "VALUES (?,?,?,?,?,'bounty','running',?,?,?)",
            (errand_id, sender["id"], lane_id, db.dumps(payload), amount, lanes.get(lane_id).baseline_micros, op["id"], now()),
        )
    tried: set[str] = set()
    detail = "no eligible runner"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        cands = dispatch.candidates(conn, lane_id, amount - fee, exclude=tried)
        if not cands:
            break
        cand, policy = dispatch.choose(cands, "best", "top")
        tried.add(cand.runner["id"])
        res, answer, conf, verdict = integrity.execute(conn, errand_id, cand.runner, lane_id, payload, "bounty")
        if res.ok_call and verdict.passed is not False:
            cap = paypal.capture_authorization(meta["authorization_id"], amount)
            meta["capture_id"] = cap.get("capture_id")
            with db.tx(conn):
                ledger.post(conn, "bounty captured and paid", [
                    (PAYPAL_ID, "world", -amount),
                    *_runner_pay(conn, cand.runner["id"], amount - fee),
                    (PLATFORM_ID, "revenue", fee),
                ], ref=errand_id)
                conn.execute("UPDATE paypal_ops SET status='settled', meta=?, updated_at=? WHERE id=?",
                             (db.dumps(meta), now(), op["id"]))
            _finish(conn, errand_id, "completed", runner_id=cand.runner["id"], output=res.output, answer=answer,
                    confidence=conf, verdict="passed" if verdict.passed else "delivered", detail=verdict.detail,
                    price=amount - fee, fee=fee, latency_ms=res.latency_ms, attempts=attempt, policy=policy)
            return errand_public(errand_row(conn, errand_id))
        detail = f"{cand.runner['name']}: {verdict.detail}"
    paypal.void_authorization(meta["authorization_id"])
    _set_op(conn, op["id"], "voided", meta)
    _finish(conn, errand_id, "failed", attempts=len(tried), detail=f"{detail}. PayPal authorization voided; you were not charged.")
    return errand_public(errand_row(conn, errand_id))


# ---------- PayPal: runner withdrawals (Payouts) ----------

def withdraw(conn, runner: dict, amount_usd: float) -> dict:
    if runner["kind"] != "runner":
        raise ErrandError("only runners can withdraw earnings")
    email = runner.get("paypal_email")
    if not email:
        raise ErrandError("set your PayPal email in settings first")
    amount = to_micros(amount_usd)
    if amount < 10_000:
        raise ErrandError("minimum withdrawal is $0.01")
    batch_id = new_id("payout")
    with db.tx(conn):
        ledger.move(conn, "PayPal payout", (runner["id"], "earnings"), (PAYPAL_ID, "world"), amount, ref=batch_id)
    try:
        res = paypal.create_payout(email, amount, "Your Errand earnings", batch_id)
    except PayPalError as e:
        with db.tx(conn):
            ledger.move(conn, "payout reversed", (PAYPAL_ID, "world"), (runner["id"], "earnings"), amount, ref=batch_id)
        _record_op(conn, runner["id"], "payout", "withdraw", amount, None, "failed", {"error": str(e)[:300]})
        raise ErrandError(f"payout failed: {e}") from None
    _record_op(conn, runner["id"], "payout", "withdraw", amount, res["payout_batch_id"], res["status"].lower(),
               {"email": email, "sender_batch_id": batch_id})
    return {"payout_batch_id": res["payout_batch_id"], "status": res["status"], "amount_usd": to_usd(amount),
            "paypal_mode": paypal.mode}


def paypal_ops(conn, account_id: str | None = None, limit: int = 200) -> list[dict]:
    if account_id:
        rs = conn.execute("SELECT * FROM paypal_ops WHERE account_id=? ORDER BY created_at DESC LIMIT ?", (account_id, limit))
    else:
        rs = conn.execute("SELECT * FROM paypal_ops ORDER BY created_at DESC LIMIT ?", (limit,))
    out = []
    for r in rs:
        d = dict(r)
        d["amount_usd"] = to_usd(d.pop("amount"))
        meta = json.loads(d.pop("meta") or "{}")
        d["detail"] = meta.get("authorization_id") or meta.get("capture_id") or meta.get("error") or ""
        out.append(d)
    return out


# ---------- read models ----------

def _bal_usd(conn, account_id: str) -> dict:
    return {k: to_usd(v) for k, v in ledger.balances(conn, account_id).items()}


def sender_view(conn, sender_id: str) -> dict:
    acct = get_account(conn, sender_id)
    act = tiers.sender_activity(conn, sender_id)
    tier = tiers.tier_for(conn, sender_id)
    nxt = tiers.next_tier(tier)
    dividends = conn.execute("SELECT COALESCE(SUM(dividend),0) FROM errands WHERE sender_id=?", (sender_id,)).fetchone()[0]
    return {
        "account": acct,
        "balances": _bal_usd(conn, sender_id),
        "tier": {"name": tier.name, "fee_rate": config.get().take_rate * tier.fee_multiplier,
                 "rate_limit_per_min": tier.rate_limit_per_min,
                 "next": {"name": nxt.name, "spend_needed_usd": to_usd(max(0, nxt.min_spend - act["spend"]))} if nxt else None},
        "activity": {"spend_30d_usd": to_usd(act["spend"]), "errands_30d": act["errands"],
                     "dispute_rate": act["dispute_rate"], "baseline_30d_usd": to_usd(act["baseline"]),
                     "saved_30d_usd": to_usd(max(0, act["baseline"] - act["spend"])),
                     "dividends_usd": to_usd(int(dividends))},
    }


def runner_view(conn, runner_id: str) -> dict:
    acct = get_account(conn, runner_id)
    r = db.row(conn.execute("SELECT * FROM runners WHERE id=?", (runner_id,)).fetchone())
    lane_rows = []
    if r:
        r["lanes"] = {k: to_usd(v) for k, v in json.loads(r["lanes"]).items()}
        cfg = json.loads(r.pop("config"))
        r["config"] = {k: v for k, v in cfg.items() if "key" not in k.lower() and "secret" not in k.lower()}
        for lane_id, price in r["lanes"].items():
            s = ratings.lane_stats(conn, runner_id, lane_id)
            lane_rows.append(s.public() | {"price_usd": price, "rating": ratings.runner_rating(s)})
    flags = db.rows(conn.execute("SELECT * FROM flags WHERE runner_id=? ORDER BY created_at DESC", (runner_id,)))
    served = conn.execute("SELECT COUNT(*), COALESCE(SUM(price),0) FROM errands WHERE runner_id=? AND status='completed'",
                          (runner_id,)).fetchone()
    status = r["status"] if r else "unregistered"
    return {
        "account": acct,
        "runner": r,
        "status": status,
        "balances": _bal_usd(conn, runner_id),
        "min_bond_usd": to_usd(integrity.MIN_BOND),
        "lanes": lane_rows,
        "flags": flags,
        "served": {"errands": served[0], "gross_usd": to_usd(served[1])},
    }


def leaderboard(conn, lane_id: str) -> list[dict]:
    lanes.get(lane_id)
    out = []
    for r in conn.execute("SELECT r.*, a.name FROM runners r JOIN accounts a ON a.id=r.id"):
        prices = json.loads(r["lanes"])
        if lane_id not in prices:
            continue
        s = ratings.lane_stats(conn, r["id"], lane_id)
        out.append({
            "runner_id": r["id"], "name": r["name"], "declared_model": r["declared_model"], "kind": r["kind"],
            "status": r["status"], "rating": ratings.runner_rating(s), "quality_lcb": round(s.lcb, 3),
            "pass_mean": round(s.mean, 3), "verified": s.n_verified, "price_usd": to_usd(prices[lane_id]),
            "p50_ms": round(s.p50_ms), "p95_ms": round(s.p95_ms), "uptime": round(s.uptime, 3),
            "brier": round(s.brier, 3) if s.brier is not None else None,
            "exam_rate": s.public()["exam_rate"], "mystery_rate": s.public()["mystery_rate"],
            "bond_usd": to_usd(ledger.balance(conn, r["id"], "bond")),
        })
    return sorted(out, key=lambda x: (x["status"] == "active", x["rating"]), reverse=True)


def receipts_for(conn, runner_id: str, lane_id: str | None = None, limit: int = 500) -> list[dict]:
    """Opt-in training data: verified receipts from Senders with consent >= 2 (pool) or 3 (direct to this Runner)."""
    q = ("SELECT e.id, e.lane, e.payload, e.answer, e.output, e.verdict, e.runner_id, a.consent_level "
         "FROM errands e JOIN accounts a ON a.id=e.sender_id WHERE e.kind='live' AND e.verdict='passed' "
         "AND (a.consent_level=2 OR (a.consent_level=3 AND e.runner_id=?))")
    args: list = [runner_id]
    if lane_id:
        q += " AND e.lane=?"
        args.append(lane_id)
    q += " ORDER BY e.completed_at DESC LIMIT ?"
    args.append(limit)
    out = []
    for r in conn.execute(q, args):
        p = json.loads(r["payload"])
        out.append({"receipt_id": "rcpt_" + r["id"][4:], "lane": r["lane"], "input": p,
                    "output": r["output"], "answer": r["answer"], "verdict": r["verdict"],
                    "share": "direct" if r["consent_level"] == 3 else "pool"})
    return out


def platform_view(conn) -> dict:
    gmv = conn.execute("SELECT COALESCE(SUM(price+fee),0), COUNT(*) FROM errands WHERE status='completed' AND kind IN ('live','bounty')").fetchone()
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM errands WHERE kind IN ('live','bounty') GROUP BY status")}
    mystery = conn.execute("SELECT COUNT(*), COALESCE(SUM(verdict='passed'),0) FROM errands WHERE kind='mystery'").fetchone()
    return {
        "revenue_usd": to_usd(ledger.balance(conn, PLATFORM_ID, "revenue")),
        "gmv_usd": to_usd(gmv[0]),
        "errands_completed": gmv[1],
        "errands_by_status": by_status,
        "mystery": {"sent": mystery[0], "passed": mystery[1]},
        "paypal_net_inflow_usd": -to_usd(ledger.balance(conn, PAYPAL_ID, "world")),
        "ledger_balanced": ledger.total(conn) == 0,
        "senders": conn.execute("SELECT COUNT(*) FROM accounts WHERE kind='sender'").fetchone()[0],
        "runners": conn.execute("SELECT COUNT(*) FROM runners WHERE status='active'").fetchone()[0],
        "flags": db.rows(conn.execute(
            "SELECT f.*, a.name FROM flags f JOIN accounts a ON a.id=f.runner_id ORDER BY f.created_at DESC")),
        "paypal_mode": paypal.mode,
    }


def ledger_entries(conn, limit: int = 300) -> list[dict]:
    rs = conn.execute(
        "SELECT l.*, a.name FROM ledger l JOIN accounts a ON a.id=l.account_id ORDER BY l.id DESC LIMIT ?", (limit,))
    return [dict(r) | {"amount_usd": to_usd(r["amount"])} for r in rs]
