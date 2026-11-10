"""errand command line: serve, demo, seed, keys, reset, mcp."""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

from . import config


def cmd_serve(a) -> None:
    import os
    import uvicorn
    if a.port != 8000 and "ERRAND_BASE_URL" not in os.environ:
        os.environ["ERRAND_BASE_URL"] = f"http://localhost:{a.port}"  # read again when uvicorn imports the app
        config.configure(base_url=os.environ["ERRAND_BASE_URL"])
    print(f"Errand on http://{'localhost' if a.host in ('0.0.0.0', '127.0.0.1') else a.host}:{a.port}  "
          f"(demo={'on' if config.get().demo else 'off'}, PayPal {'sandbox' if config.get().paypal_live else 'mock'})")
    uvicorn.run("errand.app:app", host=a.host, port=a.port, reload=a.reload)


def cmd_seed(a) -> None:
    from . import db, seed
    conn = db.connect()
    keys = seed.seed(conn, with_ollama=not a.no_ollama)
    print(json.dumps(keys, indent=2))
    print(f"\nKeys saved to {seed.keys_path()}")


def cmd_keys(a) -> None:
    from . import seed
    print(json.dumps(seed.load_keys(), indent=2))


def cmd_reset(a) -> None:
    db_path = Path(config.get().db_path)
    if not a.yes:
        sys.exit(f"This deletes {db_path} and its demo keys. Re-run with --yes to confirm.")
    for p in (db_path, db_path.with_suffix(".db-wal"), db_path.with_suffix(".db-shm"), db_path.parent / "demo_keys.json"):
        if p.exists():
            p.unlink()
            print(f"deleted {p}")


def cmd_demo(a) -> None:
    """Run a scripted session: Alan delegates a batch of errands, mystery errands audit the Runners,
    and Shady (the model-swapper) gets caught. Prints the receipt."""
    if a.fresh:
        config.configure(db_path=str(Path(tempfile.mkdtemp(prefix="errand-demo-")) / "errand.db"))
    config.configure(sim_latency_scale=a.speed)
    from . import db, integrity, seed, service, taskbank

    conn = db.connect()
    seed.seed(conn, with_ollama=False)
    alan = service.get_account(conn, "snd_alan")
    rng = random.Random(a.seed)
    math_items = taskbank.items("math.final-answer", "demo")
    code_items = taskbank.items("code.python.tests", "demo")
    print(f"Alan delegates {a.n} errands (about 75% math, 25% code). Mystery errands audit Runners as we go.\n")

    results, flags = [], []
    for i in range(a.n):
        lane = "code.python.tests" if rng.random() < 0.25 else "math.final-answer"
        item = rng.choice(code_items if lane == "code.python.tests" else math_items)
        try:
            e = service.send_errand(conn, service.get_account(conn, alan["id"]), lane,
                                    taskbank.payload_for(lane, item), mystery_async=False)
        except service.FundsError as err:
            print(f"  stopped: {err}")
            break
        results.append(e)
        mark = {"passed": "ok ", "delivered": "ok ", None: "-- "}.get(e["verdict"], "!! ")
        who = e["runner"]["name"] if e["runner"] else "nobody"
        shown = "tests passed" if lane == "code.python.tests" and e["verdict"] == "passed" else str(e["answer"])[:18]
        print(f"  {mark}{lane:18} {who:8} answer={shown:18} paid=${e['total_usd']:.5f}")
        if rng.random() < a.mystery:
            m = integrity.run_mystery(conn, lane, rng=rng)
            if m and m["flag"]:
                flags.append(m["flag"])
                print(f"\n  >> MYSTERY ERRAND CAUGHT {m['flag']['runner_id']}: {m['flag']['detail']}\n"
                      f"     Bond slashed ${m['flag']['slashed_usd']:.2f}, ${m['flag']['refunded_usd']:.4f} refunded to Senders.\n")

    done = [e for e in results if e["status"] == "completed"]
    paid = sum(e["total_usd"] for e in done)
    baseline = sum(e["baseline_usd"] for e in done)
    by_runner = Counter(e["runner"]["name"] for e in done if e["runner"])
    verified = [e for e in done if e["verdict"] == "passed"]
    print("\n" + "=" * 64)
    print(f"Errands completed      {len(done)}/{len(results)}  (verified {len(verified)})")
    print(f"Alan paid              ${paid:.4f}")
    print(f"Frontier estimate      ${baseline:.4f}  (lane baseline x errands; an assumption, see lanes.py)")
    if baseline:
        print(f"Saved                  ${baseline - paid:.4f}  ({100 * (1 - paid / baseline):.0f}%)")
    print(f"Dispatch               {dict(by_runner)}")
    print(f"Flags                  {[f['runner_id'] for f in flags] or 'none'}")
    print(f"Ledger balanced        {service.ledger.total(conn) == 0}")
    print("=" * 64)
    print(f"\nDatabase: {config.get().db_path}")
    if not a.fresh:
        print("Open the dashboard (errand serve) to see these errands, the leaderboard and the slashing.")


def cmd_mcp(a) -> None:
    from .mcp_server import main
    main()


def _resolve_key(explicit: str | None) -> tuple[str, str]:
    import os
    from . import seed
    if explicit:
        return explicit, "--key"
    if os.environ.get("ERRAND_API_KEY"):
        return os.environ["ERRAND_API_KEY"], "ERRAND_API_KEY"
    alan = seed.load_keys().get("senders", {}).get("snd_alan")
    if alan:
        return alan["api_key"], "demo Sender 'Alan'"
    sys.exit("No API key. Sign up at /signup and pass --key erk_..., or run `errand seed` for a demo key.")


def cmd_connect(a) -> None:
    from . import connect
    url = (a.url or config.get().base_url).rstrip("/")
    if a.client in (None, "list"):
        found = connect.detected()
        print("Clients:")
        for name, label in connect.CLIENTS.items():
            print(f"  {'*' if name in found else ' '} {name:15} {label}")
        print("\n* = detected on this machine.  Usage: errand connect <client> | all | print")
        return
    key, source = _resolve_key(a.key)
    if a.client == "print":
        for title, text in connect.snippets(url, key).items():
            print(f"--- {title} ---\n{text}\n")
        return
    targets = connect.detected() if a.client == "all" else [a.client]
    if not targets:
        sys.exit("No supported MCP clients detected. Use `errand connect print` for copy-paste snippets.")
    print(f"Connecting to {url}/mcp with the key from {source}\n")
    for t in targets:
        print(f"  {t:15} {connect.connect(t, url, key)}")
    print("\nAsk your agent something like: \"Use Errand to solve: what is 17 * 23?\"")


def cmd_up(a) -> None:
    """Start everything and open the dashboard: the zero-thought way to run Errand."""
    import threading
    import webbrowser
    threading.Timer(2.5, lambda: webbrowser.open(f"http://localhost:{a.port}/login")).start()
    a.host, a.reload = "127.0.0.1", False
    cmd_serve(a)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="errand", description="Send your model on fewer errands.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the gateway and dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(fn=cmd_serve)

    u = sub.add_parser("up", help="start Errand and open the dashboard in your browser")
    u.add_argument("--port", type=int, default=8000)
    u.set_defaults(fn=cmd_up)

    c = sub.add_parser("connect", help="add Errand to an MCP client (claude-desktop, claude-code, cursor, vscode, "
                                       "windsurf, gemini, codex), 'all' detected ones, or 'print' snippets")
    c.add_argument("client", nargs="?")
    c.add_argument("--key", help="Sender API key (default: ERRAND_API_KEY, then the demo key)")
    c.add_argument("--url", help="gateway URL (default: ERRAND_BASE_URL or http://localhost:8000)")
    c.set_defaults(fn=cmd_connect)

    d = sub.add_parser("demo", help="run a scripted delegation session and print the receipt")
    d.add_argument("-n", type=int, default=40, help="number of errands")
    d.add_argument("--mystery", type=float, default=0.35, help="mystery errand rate per errand")
    d.add_argument("--speed", type=float, default=0.05, help="simulated latency scale (1.0 = realistic)")
    d.add_argument("--seed", type=int, default=7)
    d.add_argument("--fresh", action="store_true", help="use a throwaway database")
    d.set_defaults(fn=cmd_demo)

    sd = sub.add_parser("seed", help="create demo accounts and Runners")
    sd.add_argument("--no-ollama", action="store_true", help="do not auto-register local Ollama models")
    sd.set_defaults(fn=cmd_seed)

    sub.add_parser("keys", help="print demo API keys").set_defaults(fn=cmd_keys)
    r = sub.add_parser("reset", help="delete the local database")
    r.add_argument("--yes", action="store_true")
    r.set_defaults(fn=cmd_reset)
    sub.add_parser("mcp", help="run the MCP server on stdio").set_defaults(fn=cmd_mcp)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
