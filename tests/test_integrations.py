"""Remote MCP endpoint, the Python SDK tool runner, and `errand connect` config writers."""

import json

import pytest
from fastapi.testclient import TestClient

from errand import connect, seed
from errand.app import app
from errand.client import Errand

H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


@pytest.fixture
def client(seeded):
    with TestClient(app) as c:
        yield c


def rpc(client, method, params=None, key=None, query=""):
    headers = dict(H)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    r = client.post(f"/mcp{query}", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_remote_mcp_lists_and_calls_tools(client):
    key = seed.load_keys()["senders"]["snd_alan"]["api_key"]
    names = [t["name"] for t in rpc(client, "tools/list")["tools"]]
    assert {"send_errand", "recommend_runner", "request_top_up"} <= set(names)

    res = rpc(client, "tools/call", {"name": "send_errand", "arguments": {"lane": "math.final-answer", "problem": "What is 6 * 7?"}}, key=key)
    assert json.loads(res["content"][0]["text"])["answer"] == "42"

    res = rpc(client, "tools/call", {"name": "wallet", "arguments": {}}, query=f"?key={key}")
    assert json.loads(res["content"][0]["text"])["account"]["id"] == "snd_alan"

    res = rpc(client, "tools/call", {"name": "wallet", "arguments": {}})
    assert json.loads(res["content"][0]["text"])["status"] == 401


def test_sdk_run_tool_matches_schemas(client):
    key = seed.load_keys()["senders"]["snd_alan"]["api_key"]
    e = Errand(api_key=key, base_url="http://testserver")
    e._http = client  # route the SDK through the in-process app
    client.headers["Authorization"] = f"Bearer {key}"
    names = {t["function"]["name"] for t in e.tools("openai")}
    assert names == {t["name"] for t in e.tools("anthropic")}
    assert e.run_tool("send_errand", {"lane": "math.final-answer", "problem": "What is 2 + 3?"})["answer"] == "5"
    assert "error" in e.run_tool("send_errand", {"lane": "nope"})
    assert "approve_url" in e.run_tool("request_top_up", {"amount_usd": 5})


def test_connect_merges_and_backs_up(tmp_path, monkeypatch):
    monkeypatch.setattr(connect, "HOME", tmp_path)
    monkeypatch.setattr(connect, "_appdata", lambda: tmp_path / "appdata")
    cursor = tmp_path / ".cursor" / "mcp.json"
    cursor.parent.mkdir()
    cursor.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))

    connect.connect("cursor", "http://localhost:8000", "erk_test")
    data = json.loads(cursor.read_text())
    assert data["mcpServers"]["other"] == {"command": "x"}
    assert data["mcpServers"]["errand"]["url"] == "http://localhost:8000/mcp"
    assert (tmp_path / ".cursor" / "mcp.json.bak").exists()

    connect.connect("claude-desktop", "http://localhost:8000", "erk_test")
    desk = json.loads((tmp_path / "appdata" / "Claude" / "claude_desktop_config.json").read_text())
    assert desk["mcpServers"]["errand"]["env"]["ERRAND_API_KEY"] == "erk_test"

    toml = tmp_path / ".codex" / "config.toml"
    toml.parent.mkdir()
    toml.write_text('model = "x"\n\n[mcp_servers.errand]\ncommand = "old"\n')
    connect.connect("codex", "http://localhost:8000", "erk_test")
    text = toml.read_text()
    assert text.count("[mcp_servers.errand]") == 1 and '"old"' not in text and 'model = "x"' in text

    for title in connect.snippets("http://h", "erk_k"):
        assert title
