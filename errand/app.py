"""FastAPI app: the JSON API (/v1/...), PayPal return handlers, and the web dashboard."""

from __future__ import annotations

import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.routing import Route

from . import __version__, config, db, lanes, mcp_server, seed, service, tiers, tools
from .paypal import PayPalError
from .paypal import client as paypal

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))
COOKIE = "errand_key"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    try:
        db.init(conn)
        if config.get().demo and not seed.is_seeded(conn):
            seed.seed(conn)
    finally:
        conn.close()
    # A session manager runs once per instance, so every startup gets a fresh MCP app.
    mcp_app = mcp_server.http_app(app)
    _mcp.inner = mcp_app
    async with mcp_app.router.lifespan_context(mcp_app):
        yield


app = FastAPI(title="Errand", version=__version__, lifespan=lifespan,
              description="Send your model on fewer errands. Delegate tasks to specialist models, settled through PayPal.")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

class _McpDispatch:
    """ASGI endpoint for /mcp that forwards to the MCP app created in lifespan()."""

    inner = None

    async def __call__(self, scope, receive, send):
        if self.inner is None:
            resp = JSONResponse({"error": "MCP endpoint is starting"}, status_code=503)
            return await resp(scope, receive, send)
        await self.inner(scope, receive, send)


# Remote MCP at /mcp: any MCP client connects with a URL and a key, nothing to install.
_mcp = _McpDispatch()
app.router.routes.append(Route("/mcp", endpoint=_mcp, methods=["GET", "POST", "DELETE"]))


class McpKeyMiddleware:
    """Hands the caller's API key to the MCP tools for this request (Bearer header, or ?key= fallback)."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/mcp"):
            return await self.inner(scope, receive, send)
        auth = dict(scope["headers"]).get(b"authorization", b"").decode()
        key = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        if not key:
            key = (parse_qs(scope.get("query_string", b"").decode()).get("key") or [None])[0]
        token = mcp_server.request_key.set(key)
        try:
            await self.inner(scope, receive, send)
        finally:
            mcp_server.request_key.reset(token)


app.add_middleware(McpKeyMiddleware)


# ---------- plumbing ----------

def get_conn():
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _key_from(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE)


def current_account(request: Request, conn=Depends(get_conn)) -> dict:
    key = _key_from(request)
    acct = service.account_by_key(conn, key) if key else None
    if acct is None:
        raise HTTPException(401, "missing or invalid API key (send 'Authorization: Bearer erk_...')")
    return acct


def optional_account(request: Request, conn=Depends(get_conn)) -> dict | None:
    key = _key_from(request)
    return service.account_by_key(conn, key) if key else None


_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(conn, acct: dict) -> None:
    limit = tiers.tier_for(conn, acct["id"]).rate_limit_per_min if acct["kind"] == "sender" else 120
    q, t = _hits[acct["id"]], time.time()
    while q and q[0] < t - 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, f"rate limit of {limit} requests per minute for your tier")
    q.append(t)


@app.exception_handler(service.ErrandError)
async def errand_error(_: Request, exc: service.ErrandError):
    return JSONResponse({"error": str(exc)}, status_code=exc.status)


@app.exception_handler(PayPalError)
async def paypal_error(_: Request, exc: PayPalError):
    return JSONResponse({"error": str(exc)}, status_code=502)


@app.exception_handler(LookupError)
async def lookup_error(_: Request, exc: LookupError):
    return JSONResponse({"error": str(exc)}, status_code=404)


def _require(acct: dict, kind: str) -> None:
    if acct["kind"] != kind:
        raise HTTPException(403, f"this endpoint is for {kind} accounts")


# ---------- request models ----------

class SignupIn(BaseModel):
    kind: str = Field(pattern="^(sender|runner)$")
    name: str
    email: str | None = None


class SettingsIn(BaseModel):
    name: str | None = None
    consent_level: int | None = None
    cap_per_errand_usd: float | None = None
    cap_daily_usd: float | None = None
    preset: str | None = None
    paypal_email: str | None = None


class ErrandIn(BaseModel):
    lane: str
    payload: dict[str, Any]
    budget_usd: float | None = None
    preset: str | None = None
    mode: str = "sample"
    runner: str | None = None
    fallback: bool = True


class DelegateIn(BaseModel):
    task: str
    check: str | None = None
    budget_usd: float | None = None
    runner: str | None = None
    preset: str | None = None
    fallback: bool = True


class FeedbackIn(BaseModel):
    accepted: bool


class TopupIn(BaseModel):
    amount_usd: float
    purpose: str = "wallet"
    return_path: str = "/dashboard"


class BountyIn(BaseModel):
    amount_usd: float
    lane: str | None = None
    payload: dict[str, Any] | None = None
    task: str | None = None  # or describe it in plain words, like /v1/delegate
    check: str | None = None


class RunnerProfileIn(BaseModel):
    declared_model: str
    lanes: dict[str, float]
    kind: str = "openai"
    config: dict[str, Any] = {}


class WithdrawIn(BaseModel):
    amount_usd: float


# ---------- JSON API ----------

@app.get("/v1/config")
def api_config():
    s = config.get()
    return {"version": __version__, "demo": s.demo, "paypal_mode": paypal.mode, "take_rate": s.take_rate,
            "lanes": [l.public() for l in lanes.LANES.values()]}


@app.post("/v1/accounts")
def api_signup(body: SignupIn, conn=Depends(get_conn)):
    acct, key = service.create_account(conn, body.kind, body.name, body.email)
    return {"account": acct, "api_key": key, "note": "Store this key now; it is not shown again."}


@app.get("/v1/me")
def api_me(acct=Depends(current_account), conn=Depends(get_conn)):
    if acct["kind"] == "sender":
        return service.sender_view(conn, acct["id"])
    if acct["kind"] == "runner":
        return service.runner_view(conn, acct["id"])
    return service.platform_view(conn)


@app.patch("/v1/me")
def api_settings(body: SettingsIn, acct=Depends(current_account), conn=Depends(get_conn)):
    return service.update_settings(conn, acct["id"], body.model_dump(exclude_none=True))


@app.get("/v1/tools")
def api_tools(format: str = "openai"):
    """Tool definitions for agents that do not speak MCP (OpenAI / Anthropic function calling)."""
    if format not in ("openai", "anthropic"):
        raise service.ErrandError("format must be openai or anthropic")
    return tools.definitions(format)


@app.get("/v1/lanes")
def api_lanes():
    return [l.public() for l in lanes.LANES.values()]


@app.get("/v1/recommend")
def api_recommend(lane: str, preset: str = "balanced", budget_usd: float | None = None, conn=Depends(get_conn)):
    try:
        return service.recommend(conn, lane, preset, budget_usd)
    except lanes.PayloadError as e:
        raise service.ErrandError(str(e)) from None


@app.post("/v1/errands")
def api_send(body: ErrandIn, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "sender")
    rate_limit(conn, acct)
    try:
        return service.send_errand(conn, acct, body.lane, body.payload, body.budget_usd, body.preset, body.mode,
                                   runner=body.runner, fallback=body.fallback)
    except lanes.PayloadError as e:
        raise service.ErrandError(str(e)) from None


@app.post("/v1/delegate")
def api_delegate(body: DelegateIn, acct=Depends(current_account), conn=Depends(get_conn)):
    """One call: describe the task, optionally give an expected answer or assert tests. Errand does the rest."""
    _require(acct, "sender")
    rate_limit(conn, acct)
    try:
        return service.delegate(conn, acct, body.task, body.check, body.budget_usd, body.runner, body.preset, body.fallback)
    except lanes.PayloadError as e:
        raise service.ErrandError(str(e)) from None


@app.get("/v1/stats")
def api_stats(conn=Depends(get_conn)):
    """Public headline numbers for the landing page."""
    done = conn.execute("SELECT COUNT(*), COALESCE(SUM(verdict='passed'),0), COALESCE(SUM(MAX(0, baseline-(price+fee-dividend))),0) "
                        "FROM errands WHERE status='completed' AND kind IN ('live','bounty')").fetchone()
    recent = conn.execute(
        "SELECT e.lane, e.answer, e.verdict, e.price+e.fee-e.dividend AS total, e.baseline, e.latency_ms, a.name "
        "FROM errands e JOIN accounts a ON a.id=e.runner_id WHERE e.status='completed' AND e.kind IN ('live','bounty') "
        "ORDER BY e.completed_at DESC LIMIT 12").fetchall()
    return {"recent": [{"lane": r["lane"], "runner": r["name"], "verdict": r["verdict"], "latency_ms": r["latency_ms"],
                        "answer": r["answer"] if r["lane"] == "math.final-answer" else "tests passed",
                        "total_usd": r["total"] / 1e6, "baseline_usd": r["baseline"] / 1e6} for r in recent],
            "errands": done[0], "verified": done[1], "saved_usd": done[2] / 1e6,
            "runners": conn.execute("SELECT COUNT(*) FROM runners WHERE status='active'").fetchone()[0],
            "slashed": conn.execute("SELECT COUNT(*) FROM flags").fetchone()[0]}


@app.get("/v1/runners")
def api_runners(conn=Depends(get_conn)):
    """Active Runners a Sender can pin, with their Lanes and prices."""
    rows = conn.execute("SELECT r.id, a.name, r.declared_model, r.lanes FROM runners r JOIN accounts a ON a.id=r.id "
                        "WHERE r.status='active' ORDER BY a.name")
    return [{"id": r["id"], "name": r["name"], "model": r["declared_model"],
             "lanes": {k: v / 1e6 for k, v in json.loads(r["lanes"]).items()}} for r in rows]


@app.get("/v1/errands")
def api_errands(limit: int = 200, acct=Depends(current_account), conn=Depends(get_conn)):
    return service.list_errands(conn, acct, min(limit, 1000))


@app.get("/v1/errands/{errand_id}")
def api_errand(errand_id: str, acct=Depends(current_account), conn=Depends(get_conn)):
    e = service.errand_row(conn, errand_id)
    if acct["id"] not in (e["sender_id"], e["runner_id"]) and acct["kind"] != "platform":
        raise HTTPException(404, "errand not found")
    return service.errand_public(e, "sender" if acct["id"] == e["sender_id"] else "runner")


@app.post("/v1/errands/{errand_id}/feedback")
def api_feedback(errand_id: str, body: FeedbackIn, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "sender")
    return service.give_feedback(conn, acct, errand_id, body.accepted)


@app.post("/v1/wallet/topup")
def api_topup(body: TopupIn, acct=Depends(current_account), conn=Depends(get_conn)):
    return service.start_topup(conn, acct, body.amount_usd, body.purpose, body.return_path)


@app.post("/v1/bounties")
def api_bounty(body: BountyIn, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "sender")
    try:
        lane_id, payload = (body.lane, body.payload) if body.lane else service.infer_errand(body.task, body.check)
        return service.start_bounty(conn, acct, lane_id, payload or {}, body.amount_usd)
    except lanes.PayloadError as e:
        raise service.ErrandError(str(e)) from None


@app.get("/v1/paypal/ops")
def api_paypal_ops(acct=Depends(current_account), conn=Depends(get_conn)):
    return service.paypal_ops(conn, None if acct["kind"] == "platform" else acct["id"])


@app.put("/v1/runner/profile")
def api_runner_profile(body: RunnerProfileIn, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "runner")
    return service.register_runner(conn, acct["id"], body.declared_model, body.lanes, body.kind, body.config)


@app.post("/v1/runner/withdraw")
def api_withdraw(body: WithdrawIn, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "runner")
    return service.withdraw(conn, acct, body.amount_usd)


@app.get("/v1/runner/receipts")
def api_receipts(lane: str | None = None, acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "runner")
    return service.receipts_for(conn, acct["id"], lane)


@app.get("/v1/leaderboard")
def api_leaderboard(lane: str = "math.final-answer", conn=Depends(get_conn)):
    try:
        return service.leaderboard(conn, lane)
    except lanes.PayloadError as e:
        raise service.ErrandError(str(e)) from None


@app.get("/v1/platform/overview")
def api_platform(acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "platform")
    return service.platform_view(conn)


@app.get("/v1/platform/ledger")
def api_ledger(acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "platform")
    return service.ledger_entries(conn)


@app.post("/v1/platform/mystery")
def api_mystery(lane: str = "math.final-answer", acct=Depends(current_account), conn=Depends(get_conn)):
    _require(acct, "platform")
    from . import integrity
    return integrity.run_mystery(conn, lane) or {"error": "no active runner in this lane"}


@app.get("/v1/demo/tasks")
def api_demo_tasks():
    from . import taskbank
    return {
        "math.final-answer": [{"problem": i["problem"], "expected": i["answer"]} for i in taskbank.items("math.final-answer", "demo")],
        "code.python.tests": [taskbank.code_payload(i) for i in taskbank.items("code.python.tests", "demo")],
    }


# ---------- PayPal return handlers (shared by browser and agent-initiated flows) ----------

def _safe_next(path: str | None) -> str:
    return path if path and path.startswith("/") and not path.startswith("//") else "/dashboard"


@app.get("/paypal/return")
def paypal_return(token: str, next: str = "/dashboard", conn=Depends(get_conn)):
    try:
        res = service.complete_order(conn, token)
    except (service.ErrandError, PayPalError) as e:
        return RedirectResponse(f"{_safe_next(next)}?flash={quote('PayPal: ' + str(e))}", status_code=303)
    if res.get("bounty"):
        b = res["bounty"]
        msg = (f"Bounty paid: {b['runner']['name']} solved it; PayPal authorization captured."
               if b["status"] == "completed" else "Bounty failed verification; PayPal authorization voided, you were not charged.")
    else:
        op = res["op"]
        msg = f"PayPal top-up of ${op['amount'] / 1e6:.2f} {'already applied' if res['already'] else 'received'}."
    return RedirectResponse(f"{_safe_next(next)}?flash={quote(msg)}", status_code=303)


@app.get("/paypal/cancel")
def paypal_cancel(token: str | None = None, next: str = "/dashboard", conn=Depends(get_conn)):
    if token:
        try:
            service.cancel_order(conn, token)
        except service.ErrandError:
            pass
    return RedirectResponse(f"{_safe_next(next)}?flash={quote('PayPal checkout cancelled.')}", status_code=303)


@app.get("/paypal/mock/approve", response_class=HTMLResponse)
def mock_approve_page(request: Request, token: str, conn=Depends(get_conn)):
    op = service._op_by_order(conn, token)
    nxt = json.loads(op["meta"] or "{}").get("return_path") or "/dashboard"
    return page(request, "mock_approve.html", optional_account(request, conn), op=op, token=token, next=nxt)


@app.post("/paypal/mock/approve")
def mock_approve(token: str = Form(...), decision: str = Form(...), next: str = Form("/dashboard"), conn=Depends(get_conn)):
    if decision != "approve":
        return RedirectResponse(f"/paypal/cancel?token={token}&next={quote(_safe_next(next))}", status_code=303)
    service.mock_approve(conn, token)
    return RedirectResponse(f"/paypal/return?token={token}&next={quote(_safe_next(next))}", status_code=303)


# ---------- web pages ----------

def page(request: Request, name: str, acct: dict | None, **ctx):
    s = config.get()
    return templates.TemplateResponse(request, name, {"acct": acct, "demo": s.demo, "paypal_mode": paypal.mode,
                                                       "version": __version__, "flash": request.query_params.get("flash"), **ctx})


@app.get("/", response_class=HTMLResponse)
def index(request: Request, acct=Depends(optional_account)):
    bench_file = HERE / "static" / "bench.json"  # written by `errand bench`
    bench = json.loads(bench_file.read_text(encoding="utf-8")) if bench_file.exists() else None
    return page(request, "index.html", acct, lanes=list(lanes.LANES.values()), base_url=config.get().base_url, bench=bench)


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(request: Request, acct=Depends(optional_account)):
    return page(request, "leaderboard.html", acct, lanes=list(lanes.LANES.values()))


@app.get("/connect", response_class=HTMLResponse)
def connect_page(request: Request, acct=Depends(optional_account)):
    # Your own key is the session cookie, so the page can fill it in for real accounts too.
    demo_key = request.cookies.get(COOKIE) if acct else None
    from . import connect as connect_mod
    base = config.get().base_url
    return page(request, "connect.html", acct, base_url=base, demo_key=demo_key,
                snippets=connect_mod.snippets(base, demo_key or "erk_YOUR_KEY"))


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, acct=Depends(optional_account)):
    demo_accounts = []
    if config.get().demo:
        k = seed.load_keys()
        demo_accounts = [{"id": i, "name": v["name"], "kind": "sender"} for i, v in k.get("senders", {}).items()]
        demo_accounts += [{"id": i, "name": v["name"], "kind": "runner"} for i, v in k.get("runners", {}).items()]
        if k.get("platform"):
            demo_accounts.append({"id": "platform", "name": "Errand platform (admin)", "kind": "platform"})
    return page(request, "login.html", acct, demo_accounts=demo_accounts)


def _login(key: str, dest: str = "/dashboard") -> RedirectResponse:
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(COOKIE, key, httponly=True, samesite="lax", max_age=30 * 86400)
    return resp


@app.post("/login")
def login(api_key: str = Form(...), conn=Depends(get_conn)):
    if service.account_by_key(conn, api_key.strip()) is None:
        return RedirectResponse(f"/login?flash={quote('That API key was not recognised.')}", status_code=303)
    return _login(api_key.strip())


@app.post("/login/demo/{account_id}")
def login_demo(account_id: str):
    if not config.get().demo:
        raise HTTPException(404)
    k = seed.load_keys()
    if account_id == "platform":
        key = k.get("platform")
    else:
        key = (k.get("senders", {}).get(account_id) or k.get("runners", {}).get(account_id) or {}).get("api_key")
    if not key:
        raise HTTPException(404, "demo account not found")
    return _login(key)


@app.post("/logout")
def logout():
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, kind: str = "sender", acct=Depends(optional_account)):
    return page(request, "signup.html", acct, kind=kind, new_key=None)


@app.post("/signup", response_class=HTMLResponse)
def signup(request: Request, kind: str = Form(...), name: str = Form(...), email: str = Form(""), conn=Depends(get_conn)):
    try:
        acct, key = service.create_account(conn, kind, name, email or None)
    except service.ErrandError as e:
        return page(request, "signup.html", None, kind=kind, new_key=None, error=str(e))
    welcome = ("Welcome. You have $1.00 of starter credit, so your first errands are on us."
               if acct["kind"] == "sender" else "Welcome. Register your model below; the onboarding exam starts right away.")
    return _login(key, f"/dashboard?flash={quote(welcome)}")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, acct=Depends(optional_account)):
    if acct is None:
        return RedirectResponse("/login", status_code=303)
    template = {"sender": "sender.html", "runner": "runner.html", "platform": "platform.html"}[acct["kind"]]
    return page(request, template, acct, lanes=list(lanes.LANES.values()), base_url=config.get().base_url,
                api_key=request.cookies.get(COOKIE) or "erk_YOUR_KEY")
