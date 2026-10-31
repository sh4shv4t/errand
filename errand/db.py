"""SQLite storage. One file, no server, safe for a single gateway process."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,                      -- sender | runner | platform | external
  name TEXT NOT NULL,
  email TEXT,
  api_key_hash TEXT UNIQUE,
  created_at REAL NOT NULL,
  consent_level INTEGER NOT NULL DEFAULT 0, -- Receipts consent, 0..3
  cap_per_errand INTEGER NOT NULL DEFAULT 1000000,  -- spending mandate, micros
  cap_daily INTEGER NOT NULL DEFAULT 20000000,
  preset TEXT NOT NULL DEFAULT 'balanced',
  paypal_email TEXT
);

CREATE TABLE IF NOT EXISTS runners (
  id TEXT PRIMARY KEY REFERENCES accounts(id),
  declared_model TEXT NOT NULL,
  lanes TEXT NOT NULL,                     -- json {lane_id: price_micros}
  kind TEXT NOT NULL,                      -- simulated | openai | webhook
  config TEXT NOT NULL,                    -- json adapter config
  status TEXT NOT NULL,                    -- onboarding | active | rejected | suspended
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS errands (
  id TEXT PRIMARY KEY,
  sender_id TEXT NOT NULL,
  lane TEXT NOT NULL,
  payload TEXT NOT NULL,
  budget INTEGER NOT NULL,
  kind TEXT NOT NULL DEFAULT 'live',       -- live | bounty | mystery | exam
  status TEXT NOT NULL,                    -- running | completed | failed
  runner_id TEXT,
  output TEXT,
  answer TEXT,
  confidence REAL,
  verdict TEXT,                            -- passed | delivered | failed
  detail TEXT,
  price INTEGER NOT NULL DEFAULT 0,
  fee INTEGER NOT NULL DEFAULT 0,
  dividend INTEGER NOT NULL DEFAULT 0,
  baseline INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  policy TEXT,
  feedback INTEGER,
  bounty_op TEXT,
  created_at REAL NOT NULL,
  completed_at REAL
);
CREATE INDEX IF NOT EXISTS errands_sender ON errands(sender_id, created_at);
CREATE INDEX IF NOT EXISTS errands_runner ON errands(runner_id, created_at);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  errand_id TEXT NOT NULL,
  runner_id TEXT NOT NULL,
  lane TEXT NOT NULL,
  kind TEXT NOT NULL,                      -- live | bounty | mystery | exam
  ok_call INTEGER NOT NULL,                -- 0 when the runner errored or timed out
  passed INTEGER,                          -- 1 / 0 / NULL (unverifiable)
  confidence REAL,
  latency_ms INTEGER,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS attempts_runner ON attempts(runner_id, lane, created_at);

CREATE TABLE IF NOT EXISTS ledger (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  txn TEXT NOT NULL,
  account_id TEXT NOT NULL,
  bucket TEXT NOT NULL,                    -- wallet | escrow | earnings | bond | revenue | world
  amount INTEGER NOT NULL,
  memo TEXT NOT NULL,
  ref TEXT,
  created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ledger_account ON ledger(account_id, bucket);

CREATE TABLE IF NOT EXISTS paypal_ops (
  id TEXT PRIMARY KEY,
  account_id TEXT NOT NULL,
  kind TEXT NOT NULL,                      -- order | authorization | payout
  purpose TEXT NOT NULL,                   -- wallet | bond | bounty | withdraw
  paypal_id TEXT,
  amount INTEGER NOT NULL,
  status TEXT NOT NULL,
  meta TEXT,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS flags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  runner_id TEXT NOT NULL,
  lane TEXT NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL,
  slashed INTEGER NOT NULL DEFAULT 0,
  refunded INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);
"""

PLATFORM_ID = "acct_platform"
PAYPAL_ID = "acct_paypal"  # stands in for "the outside world" in double-entry bookkeeping


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def now() -> float:
    return time.time()


def connect() -> sqlite3.Connection:
    path = config.get().db_path
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def tx(conn: sqlite3.Connection):
    """Write transaction. BEGIN IMMEDIATE serializes writers so balances stay consistent."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for acct_id, kind, name in ((PLATFORM_ID, "platform", "Errand Platform"), (PAYPAL_ID, "external", "PayPal")):
        conn.execute(
            "INSERT OR IGNORE INTO accounts(id, kind, name, created_at) VALUES (?,?,?,?)",
            (acct_id, kind, name, now()),
        )


def row(r: sqlite3.Row | None) -> dict | None:
    return dict(r) if r is not None else None


def rows(rs) -> list[dict]:
    return [dict(r) for r in rs]


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"))
