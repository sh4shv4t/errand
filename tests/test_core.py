import random

import pytest

from errand import db, dispatch, integrity, lanes, ledger, ratings, service, taskbank
from errand.db import PAYPAL_ID, PLATFORM_ID

MATH, CODE = "math.final-answer", "code.python.tests"


def fund(conn, account_id, bucket, usd):
    with db.tx(conn):
        ledger.move(conn, "test credit", (PAYPAL_ID, "world"), (account_id, bucket), int(usd * 1e6))


def make_sender(conn, usd=1.0, **settings):
    acct, _ = service.create_account(conn, "sender", "Tester", starter_credit=False)
    if settings:
        service.update_settings(conn, acct["id"], settings)
    if usd:
        fund(conn, acct["id"], "wallet", usd)
    return service.get_account(conn, acct["id"])


def make_runner(conn, name, lanes_prices, cfg, bond=2.0):
    acct, _ = service.create_account(conn, "runner", name)
    fund(conn, acct["id"], "bond", bond)
    service.register_runner(conn, acct["id"], f"{name}-model (simulated)", lanes_prices, "simulated", cfg,
                            start_exam=True, sync_exam=True)
    return acct["id"]


# ---------- verifiers ----------

def test_math_extract_and_verify():
    assert lanes.math_extract("blah\nANSWER: 1,225\nCONFIDENCE: 0.9") == "1225"
    assert lanes.math_extract("so the answer is 3/4") == "0.75"
    assert lanes.math_verify({"problem": "x", "expected": "0.25"}, "1/4").passed is True
    assert lanes.math_verify({"problem": "x", "expected": "7"}, "8").passed is False
    assert lanes.math_verify({"problem": "x"}, "8").passed is None  # delivered, not checked
    assert lanes.parse_confidence("CONFIDENCE: 0.83") == 0.83


def test_code_verifier_pass_and_fail():
    item = taskbank.CODE[0]
    p = taskbank.code_payload(item)
    assert lanes.code_verify(p, item["reference"]).passed is True
    assert lanes.code_verify(p, f"def {item['function_name']}(s):\n    return False\n").passed is False
    assert lanes.code_verify(p, "def other():\n    pass\n").passed is False
    assert lanes.code_verify(p, f"def {item['function_name']}(s):\n    while True: pass\n", timeout=1).passed is False


def test_task_bank_answers_are_self_consistent():
    for item in taskbank.CODE:
        assert lanes.code_verify(taskbank.code_payload(item), item["reference"]).passed, item["id"]
    assert {i["split"] for i in taskbank.MATH} == {"demo", "exam", "mystery"}


# ---------- ledger ----------

def test_ledger_refuses_overdraft_and_stays_balanced(conn):
    s = make_sender(conn, usd=1.0)
    with pytest.raises(ledger.InsufficientFunds):
        with db.tx(conn):
            ledger.move(conn, "too much", (s["id"], "wallet"), (s["id"], "escrow"), 2_000_000)
    with pytest.raises(ValueError):
        with db.tx(conn):
            ledger.post(conn, "bad", [(s["id"], "wallet", 1)])
    assert ledger.balance(conn, s["id"], "wallet") == 1_000_000
    assert ledger.total(conn) == 0


# ---------- ratings and dispatch ----------

def test_lcb_prefers_proven_runner():
    assert ratings.beta_lcb(1 + 970, 1 + 30) > ratings.beta_lcb(1 + 3, 1)


def test_dispatch_presets_change_choice(conn):
    cheap = make_runner(conn, "Cheap", {MATH: 0.0005}, {"accuracy": {MATH: 0.85}, "latency_ms": [0, 0]})
    pricey = make_runner(conn, "Pricey", {MATH: 0.05}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    cands = dispatch.candidates(conn, MATH)
    assert dispatch.rank(cands, "cheapest")[0].runner["id"] == cheap
    assert dispatch.choose(cands, "best", "top")[0].runner["id"] in (cheap, pricey)
    assert {c.runner["id"] for c in dispatch.candidates(conn, MATH, max_price=1000)} == {cheap}


# ---------- errand lifecycle ----------

def test_errand_settles_escrow_and_pays_runner(conn):
    runner = make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn, usd=1.0, consent_level=2)
    item = taskbank.items(MATH, "demo")[0]
    e = service.send_errand(conn, s, MATH, taskbank.payload_for(MATH, item), mystery_async=False)
    assert e["status"] == "completed" and e["verdict"] == "passed" and e["answer"] == item["answer"]
    assert ledger.balance(conn, runner, "earnings") == 1000
    assert ledger.balance(conn, s["id"], "escrow") == 0
    assert e["fee_usd"] == pytest.approx(0.0001)
    assert e["dividend_usd"] == pytest.approx(0.00002)  # consent 2 earns 20% of the fee back
    assert ledger.balance(conn, s["id"], "wallet") == 1_000_000 - 1100 + 20
    assert ledger.total(conn) == 0


def test_failed_attempt_is_refunded_and_retried(conn):
    bad = make_runner(conn, "Bad", {MATH: 0.0001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0], "swap_after": 6,
                                                     "swap_accuracy": 0.0})
    good = make_runner(conn, "Good", {MATH: 0.002}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn, usd=1.0, preset="cheapest")
    item = taskbank.items(MATH, "demo")[1]
    e = service.send_errand(conn, s, MATH, taskbank.payload_for(MATH, item), mode="top", mystery_async=False)
    assert e["status"] == "completed" and e["runner"]["id"] == good and e["attempts"] == 2
    assert ledger.balance(conn, bad, "earnings") == 0  # never paid for wrong work
    assert ledger.balance(conn, s["id"], "escrow") == 0


def test_insufficient_funds_and_mandate(conn):
    make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    broke = make_sender(conn, usd=0)
    payload = {"problem": "What is 2 + 2?"}
    with pytest.raises(service.FundsError):
        service.send_errand(conn, broke, MATH, payload, mystery_async=False)
    capped = make_sender(conn, usd=1.0, cap_per_errand_usd=0.01)
    with pytest.raises(service.MandateError):
        service.send_errand(conn, capped, MATH, payload, budget_usd=0.5, mystery_async=False)


def test_unverifiable_math_is_delivered(conn):
    make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn)
    e = service.send_errand(conn, s, MATH, {"problem": "What is 17 * 23?"}, mystery_async=False)
    assert e["verdict"] == "delivered" and e["answer"] == "391"


# ---------- integrity ----------

def test_model_swap_is_caught_slashed_and_refunded(conn):
    shady = make_runner(conn, "Shady", {MATH: 0.0005}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0],
                                                         "swap_after": 6, "swap_accuracy": 0.0})
    s = make_sender(conn, usd=1.0)
    item = taskbank.items(MATH, "demo")[0]
    payload = {"problem": item["problem"]}  # no expected answer: delivered, so the Sender pays for bad work
    e = service.send_errand(conn, s, MATH, payload, mode="top", mystery_async=False)
    assert e["runner"]["id"] == shady and e["verdict"] == "delivered"
    flag = None
    rng = random.Random(1)
    for _ in range(10):
        r = integrity.run_mystery(conn, MATH, shady, rng=rng)
        if r is None:  # already suspended
            break
        flag = flag or r["flag"]
    assert flag and flag["kind"] == "model_swap_suspected"
    assert conn.execute("SELECT status FROM runners WHERE id=?", (shady,)).fetchone()[0] == "suspended"
    assert ledger.balance(conn, shady, "bond") == 1_000_000  # half of $2 slashed
    assert flag["refunded_usd"] == pytest.approx(0.0005)  # the Sender's payment came back
    assert ledger.total(conn) == 0


def test_exam_rejects_bad_runner(conn):
    rid = make_runner(conn, "Weak", {CODE: 0.001}, {"accuracy": {CODE: 0.0}, "latency_ms": [0, 0]})
    assert conn.execute("SELECT status FROM runners WHERE id=?", (rid,)).fetchone()[0] == "rejected"


def test_runner_without_bond_starts_and_earns_its_bond(conn):
    acct, _ = service.create_account(conn, "runner", "NoBond")
    service.register_runner(conn, acct["id"], "m", {MATH: 0.001}, "simulated",
                            {"accuracy": {MATH: 1}, "latency_ms": [0, 0]}, sync_exam=True)
    assert service.runner_view(conn, acct["id"])["status"] == "active"  # no upfront bond
    s = make_sender(conn, usd=1.0)
    item = taskbank.items(MATH, "demo")[0]
    service.send_errand(conn, s, MATH, taskbank.payload_for(MATH, item), mystery_async=False)
    assert ledger.balance(conn, acct["id"], "bond") == 1000  # first earnings fill the bond
    assert ledger.balance(conn, acct["id"], "earnings") == 0
    assert ledger.total(conn) == 0


def test_starter_credit_and_delegate_infers_lane(conn):
    make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    make_runner(conn, "Ada", {CODE: 0.001}, {"accuracy": {CODE: 1.0}, "latency_ms": [0, 0]})
    acct, _ = service.create_account(conn, "sender", "Newbie")
    assert ledger.balance(conn, acct["id"], "wallet") == service.STARTER_CREDIT
    item = taskbank.items(MATH, "demo")[0]
    e = service.delegate(conn, acct, item["problem"], item["answer"])
    assert e["lane"] == MATH and e["verdict"] == "passed"
    code = taskbank.code_payload(taskbank.items(CODE, "demo")[0])
    e = service.delegate(conn, acct, code["spec"], code["tests"])
    assert e["lane"] == CODE and e["verdict"] == "passed"
    with pytest.raises(service.ErrandError):
        service.delegate(conn, acct, "Write a function that reverses a list")  # code without tests
    assert ledger.total(conn) == 0


def test_pinned_runner_is_used_and_falls_back(conn):
    make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    make_runner(conn, "Atlas", {MATH: 0.004}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn, usd=1.0)
    item = taskbank.items(MATH, "demo")[0]
    e = service.delegate(conn, s, item["problem"], item["answer"], runner="atlas")
    assert e["runner"]["name"] == "Atlas" and e["policy"] == "pinned"
    with pytest.raises(service.NotFound):
        service.delegate(conn, s, item["problem"], item["answer"], runner="nobody")
    e = service.delegate(conn, s, item["problem"], item["answer"], runner="atlas", budget_usd=0.002)
    assert e["runner"]["name"] == "Duke"  # Atlas is over budget, so dispatch falls back


# ---------- PayPal flows (mock mode) ----------

def test_topup_requires_approval_then_credits_wallet(conn):
    s = make_sender(conn, usd=0)
    order = service.start_topup(conn, s, 5)
    with pytest.raises(service.ErrandError):
        service.complete_order(conn, order["order_id"])  # not approved yet
    service.mock_approve(conn, order["order_id"])
    service.complete_order(conn, order["order_id"])
    service.complete_order(conn, order["order_id"])  # idempotent
    assert ledger.balance(conn, s["id"], "wallet") == 5_000_000


def test_bond_topup_starts_exam(conn):
    acct, _ = service.create_account(conn, "runner", "Late")
    service.register_runner(conn, acct["id"], "m", {MATH: 0.001}, "simulated",
                            {"accuracy": {MATH: 1}, "latency_ms": [0, 0]}, start_exam=False)
    order = service.start_topup(conn, acct, 2, purpose="bond")
    service.mock_approve(conn, order["order_id"])
    service.complete_order(conn, order["order_id"])
    assert ledger.balance(conn, acct["id"], "bond") == 2_000_000


def test_bounty_captures_on_pass_and_voids_on_fail(conn):
    good = make_runner(conn, "Ada", {CODE: 0.001}, {"accuracy": {CODE: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn, usd=0)
    item = taskbank.items(CODE, "demo")[0]
    b = service.start_bounty(conn, s, CODE, taskbank.code_payload(item), 3)
    service.mock_approve(conn, b["order_id"])
    res = service.complete_order(conn, b["order_id"])
    assert res["bounty"]["status"] == "completed"
    assert ledger.balance(conn, good, "earnings") == 2_700_000  # $3 minus 10% fee
    assert ledger.balance(conn, PLATFORM_ID, "revenue") >= 300_000

    impossible = {"function_name": "nope", "spec": "unsolvable", "tests": "assert False"}
    b2 = service.start_bounty(conn, s, CODE, impossible, 3)
    service.mock_approve(conn, b2["order_id"])
    res2 = service.complete_order(conn, b2["order_id"])
    assert res2["bounty"]["status"] == "failed"
    op = conn.execute("SELECT status FROM paypal_ops WHERE paypal_id=?", (b2["order_id"],)).fetchone()
    assert op[0] == "voided"
    assert ledger.total(conn) == 0


def test_withdraw_needs_email_and_balance(conn):
    rid = make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    fund(conn, rid, "earnings", 1.0)
    runner = service.get_account(conn, rid)
    with pytest.raises(service.ErrandError):
        service.withdraw(conn, runner, 0.5)
    runner = service.update_settings(conn, rid, {"paypal_email": "duke@example.com"})
    out = service.withdraw(conn, runner, 0.5)
    assert out["status"] == "SUCCESS"
    assert ledger.balance(conn, rid, "earnings") == 500_000
    with pytest.raises(ledger.InsufficientFunds):
        service.withdraw(conn, runner, 5)


def test_receipts_respect_consent(conn):
    rid = make_runner(conn, "Duke", {MATH: 0.001}, {"accuracy": {MATH: 1.0}, "latency_ms": [0, 0]})
    private = make_sender(conn, consent_level=0)
    sharing = make_sender(conn, consent_level=2)
    item = taskbank.items(MATH, "demo")[0]
    for s in (private, sharing):
        service.send_errand(conn, s, MATH, taskbank.payload_for(MATH, item), mystery_async=False)
    rec = service.receipts_for(conn, rid)
    assert len(rec) == 1 and rec[0]["share"] == "pool"


def test_seed_and_tiers(seeded):
    view = service.sender_view(seeded, "snd_alan")
    assert view["tier"]["name"] == "Regular"
    assert {r["status"] for r in service.leaderboard(seeded, MATH)} == {"active"}


# ---------- benchmark and demo seed ----------

def test_bench_combine_routes_each_lane_to_its_best_model():
    from errand import bench

    def fake(model, math_rate, code_rate):
        rows = {}
        for lane_id, rate in ((MATH, math_rate), (CODE, code_rate)):
            v = int(rate * 10)
            rows[lane_id] = {"tasks": 10, "verified": v, "pass_rate": rate, "median_ms": 1000, "p95_ms": 2000,
                             "errand_cost_usd": 0.0002 * v, "frontier_cost_usd": 0.012 * v, "unpaid_wrong_answers": 10 - v,
                             "errors": 0, "title": lane_id}
        return {"model": model, "lanes": rows, "notes": {}}

    out = bench.combine([fake("mathy", 0.9, 0.2), fake("cody", 0.3, 0.8)])
    assert out["lanes"][MATH]["model"] == "mathy" and out["lanes"][CODE]["model"] == "cody"
    assert out["verified"] == 17 and out["tasks"] == 20 and out["unpaid_wrong_answers"] == 3
    assert len(out["models"]) == 2 and 0 < out["savings_pct"] < 100


def test_demo_seed_leaves_out_the_villain_unless_asked(seeded):
    names = {r[0] for r in seeded.execute("SELECT a.name FROM runners r JOIN accounts a ON a.id=r.id")}
    assert "Shady" not in names and {"Duke", "Ada", "Atlas"} <= names


def test_exam_lists_a_specialist_only_in_the_lanes_it_passes(conn):
    rid = make_runner(conn, "Coder", {MATH: 0.001, CODE: 0.001},
                      {"accuracy": {MATH: 0.0, CODE: 1.0}, "latency_ms": [0, 0]})
    status, lanes_json = conn.execute("SELECT status, lanes FROM runners WHERE id=?", (rid,)).fetchone()
    assert status == "active" and list(__import__("json").loads(lanes_json)) == [CODE]
    assert all(c.runner["id"] != rid for c in dispatch.candidates(conn, MATH))


def test_code_errand_with_broken_tests_is_bounced_for_free(conn):
    make_runner(conn, "Ada", {CODE: 0.001}, {"accuracy": {CODE: 1.0}, "latency_ms": [0, 0]})
    s = make_sender(conn, usd=1.0)
    with pytest.raises(service.ErrandError, match="do not parse"):
        service.delegate(conn, s, "Write is_palindrome(s).", "assert is_palindrome('I'm')")
    assert ledger.balance(conn, s["id"], "wallet") == 1_000_000
    assert conn.execute("SELECT COUNT(*) FROM attempts").fetchone()[0] == 4  # only Ada's onboarding exam


def test_warm_up_gives_a_fresh_demo_some_history(seeded):
    from errand import seed
    assert seed.warm_up(seeded, 12) >= 10
    assert seeded.execute("SELECT COUNT(*) FROM errands WHERE kind='live' AND status='completed'").fetchone()[0] >= 10
    assert ledger.total(seeded) == 0
