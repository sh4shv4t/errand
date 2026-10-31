"""Double-entry ledger. Every transaction's entries sum to zero, so money is never created or lost.

Buckets:
  wallet   sender spendable balance
  escrow   sender funds held for an in-flight errand
  earnings runner balance available to withdraw
  bond     runner stake, slashable
  revenue  platform take
  world    money outside Errand (the PayPal side); goes negative as money comes in
"""

from __future__ import annotations

import sqlite3

from .db import new_id, now


class InsufficientFunds(Exception):
    def __init__(self, account_id: str, bucket: str, needed: int, available: int):
        super().__init__(f"{account_id}/{bucket} needs {needed} micros, has {available}")
        self.account_id, self.bucket, self.needed, self.available = account_id, bucket, needed, available


def balance(conn: sqlite3.Connection, account_id: str, bucket: str) -> int:
    r = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM ledger WHERE account_id=? AND bucket=?", (account_id, bucket)
    ).fetchone()
    return int(r[0])


def balances(conn: sqlite3.Connection, account_id: str) -> dict[str, int]:
    out = {}
    for r in conn.execute(
        "SELECT bucket, SUM(amount) FROM ledger WHERE account_id=? GROUP BY bucket", (account_id,)
    ):
        out[r[0]] = int(r[1])
    return out


def post(conn: sqlite3.Connection, memo: str, entries: list[tuple[str, str, int]], ref: str | None = None) -> str:
    """Write a balanced transaction. Call inside db.tx()."""
    if sum(amount for _, _, amount in entries) != 0:
        raise ValueError(f"unbalanced transaction: {entries}")
    txn = new_id("txn")
    ts = now()
    conn.executemany(
        "INSERT INTO ledger(txn, account_id, bucket, amount, memo, ref, created_at) VALUES (?,?,?,?,?,?,?)",
        [(txn, a, b, amt, memo, ref, ts) for a, b, amt in entries if amt != 0],
    )
    return txn


def move(conn, memo: str, src: tuple[str, str], dst: tuple[str, str], amount: int, ref: str | None = None,
         allow_negative: bool = False) -> str:
    """Move amount from src (account, bucket) to dst. Refuses to overdraw unless allow_negative."""
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if not allow_negative and src[1] != "world":
        available = balance(conn, *src)
        if available < amount:
            raise InsufficientFunds(src[0], src[1], amount, available)
    return post(conn, memo, [(src[0], src[1], -amount), (dst[0], dst[1], amount)], ref)


def total(conn: sqlite3.Connection) -> int:
    """Sum of every entry. Must always be zero."""
    return int(conn.execute("SELECT COALESCE(SUM(amount),0) FROM ledger").fetchone()[0])
