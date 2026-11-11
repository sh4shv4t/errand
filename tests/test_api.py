import pytest
from fastapi.testclient import TestClient

from errand import seed
from errand.app import app


@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c


def auth(key):
    return {"Authorization": f"Bearer {key}"}


def test_public_pages_render(client):
    for path in ("/", "/leaderboard", "/login", "/signup", "/connect", "/docs"):
        assert client.get(path).status_code == 200, path


def test_signup_send_and_dashboard(client):
    r = client.post("/v1/accounts", json={"kind": "sender", "name": "Agent Smith"})
    key = r.json()["api_key"]
    assert client.get("/v1/me", headers=auth(key)).json()["tier"]["name"] == "Regular"

    # starter credit: the first errand needs no PayPal step, and one call is enough
    assert client.get("/v1/me", headers=auth(key)).json()["balances"]["wallet"] == 1.0
    r = client.post("/v1/delegate", headers=auth(key), json={"task": "What is 6 * 7?", "check": "42"})
    assert r.status_code == 200 and r.json()["verdict"] == "passed"
    assert any(x["name"] == "Duke" for x in client.get("/v1/runners").json())

    # top up through the (mock) PayPal redirect flow
    order = client.post("/v1/wallet/topup", headers=auth(key), json={"amount_usd": 5}).json()
    r = client.post("/paypal/mock/approve", data={"token": order["order_id"], "decision": "approve", "next": "/dashboard"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert client.get("/v1/me", headers=auth(key)).json()["balances"]["wallet"] > 5.9

    r = client.post("/v1/errands", headers=auth(key), json={"lane": "math.final-answer", "payload": {"problem": "What is 6 * 7?"}})
    assert r.status_code == 200 and r.json()["answer"] == "42"
    eid = r.json()["id"]
    assert client.post(f"/v1/errands/{eid}/feedback", headers=auth(key), json={"accepted": True}).status_code == 200
    assert [e["status"] for e in client.get("/v1/errands", headers=auth(key)).json()] == ["completed", "completed"]


def test_bad_requests(client):
    keys = seed.load_keys()
    alan = keys["senders"]["snd_alan"]["api_key"]
    assert client.get("/v1/me").status_code == 401
    assert client.post("/v1/errands", headers=auth(alan), json={"lane": "nope", "payload": {}}).status_code == 400
    assert client.post("/v1/errands", headers=auth(alan), json={"lane": "code.python.tests", "payload": {"spec": "x"}}).status_code == 400
    runner = next(iter(keys["runners"].values()))["api_key"]
    assert client.post("/v1/errands", headers=auth(runner), json={"lane": "math.final-answer", "payload": {"problem": "1+1"}}).status_code == 403


def test_demo_login_and_dashboards(client):
    for account_id in ("snd_alan", "run_duke", "platform"):
        client.cookies.clear()
        r = client.post(f"/login/demo/{account_id}", follow_redirects=True)
        assert r.status_code == 200 and "dashboard" in r.text.lower()
    assert client.get("/v1/platform/overview").json()["ledger_balanced"] is True


def test_recommend_and_leaderboard(client):
    rec = client.get("/v1/recommend", params={"lane": "math.final-answer", "preset": "cheapest"}).json()
    assert rec["runners"] and rec["should_delegate"]
    lb = client.get("/v1/leaderboard", params={"lane": "code.python.tests"}).json()
    assert {r["name"] for r in lb} >= {"Ada", "Atlas"}


def test_postman_collection_matches_the_api(client):
    from errand import postman

    col = postman.collection(client.get("/openapi.json").json())
    quick, everything = col["item"]
    assert quick["name"] == "Quickstart" and any("/v1/delegate" in i["request"]["url"]["raw"] for i in quick["item"])
    paths = {i["request"]["url"]["raw"].split("?")[0].replace("{{base_url}}", "") for i in everything["item"]}
    assert "/v1/delegate" in paths and all(p.startswith("/v1/") for p in paths)
    assert col["auth"]["type"] == "bearer"
