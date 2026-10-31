"""`errand connect <client>`: wire Errand into an MCP client in one command.

Edits the client's own config file (after saving a .bak copy), merging rather than overwriting.
Remote-capable clients get the gateway's /mcp URL; stdio-only clients get the local errand-mcp command.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()


def _appdata() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", HOME / "AppData" / "Roaming"))
    if sys.platform == "darwin":
        return HOME / "Library" / "Application Support"
    return Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config"))


def mcp_command() -> tuple[str, list[str]]:
    """Absolute path to errand-mcp, so GUI apps without our PATH can still launch it."""
    exe = "errand-mcp.exe" if platform.system() == "Windows" else "errand-mcp"
    for cand in (Path(sys.executable).parent / exe, Path(sys.executable).parent / "Scripts" / exe):
        if cand.exists():
            return str(cand), []
    found = shutil.which("errand-mcp")
    return (found, []) if found else (sys.executable, ["-m", "errand.mcp_server"])


def _merge_json(path: Path, section: str, entry: dict) -> str:
    data = {}
    if path.exists() and path.read_text(encoding="utf-8").strip():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(f"{path} is not valid JSON ({e}); fix it or add the snippet by hand (errand connect print).")
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    path.parent.mkdir(parents=True, exist_ok=True)
    data.setdefault(section, {})["errand"] = entry
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return f"updated {path}"


def _merge_codex_toml(path: Path, command: str, args: list[str], env: dict) -> str:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    out, skipping = [], False
    for line in lines:  # drop any previous [mcp_servers.errand] block
        stripped = line.strip()
        if stripped.startswith("["):
            skipping = stripped in ("[mcp_servers.errand]", "[mcp_servers.errand.env]")
        if not skipping:
            out.append(line)
    q = lambda s: json.dumps(s)  # TOML basic strings share JSON escaping for our values
    block = ["", "[mcp_servers.errand]", f"command = {q(command)}", f"args = [{', '.join(q(a) for a in args)}]",
             "", "[mcp_servers.errand.env]"] + [f"{k} = {q(v)}" for k, v in env.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out).rstrip() + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    return f"updated {path}"


def snippets(url: str, key: str) -> dict[str, str]:
    cmd, args = mcp_command()
    remote = f"{url}/mcp"
    hdr = {"Authorization": f"Bearer {key}"}
    env = {"ERRAND_URL": url, "ERRAND_API_KEY": key}
    return {
        "Any remote MCP client": f"URL: {remote}\nHeader: Authorization: Bearer {key}\n(URL-only clients: {remote}?key={key})",
        "Claude Code": f'claude mcp add --transport http --scope user errand {remote} --header "Authorization: Bearer {key}"',
        "Claude Desktop (claude_desktop_config.json)": json.dumps({"mcpServers": {"errand": {"command": cmd, "args": args, "env": env}}}, indent=2),
        "Cursor (~/.cursor/mcp.json)": json.dumps({"mcpServers": {"errand": {"url": remote, "headers": hdr}}}, indent=2),
        "VS Code (.vscode/mcp.json)": json.dumps({"servers": {"errand": {"type": "http", "url": remote, "headers": hdr}}}, indent=2),
        "Windsurf (~/.codeium/windsurf/mcp_config.json)": json.dumps({"mcpServers": {"errand": {"serverUrl": remote, "headers": hdr}}}, indent=2),
        "Gemini CLI (~/.gemini/settings.json)": json.dumps({"mcpServers": {"errand": {"httpUrl": remote, "headers": hdr}}}, indent=2),
        "Codex CLI (~/.codex/config.toml)": f'[mcp_servers.errand]\ncommand = {json.dumps(cmd)}\nargs = {json.dumps(args)}\n\n[mcp_servers.errand.env]\n'
                                            + "\n".join(f"{k} = {json.dumps(v)}" for k, v in env.items()),
        "Stdio (any client)": f"{cmd} {' '.join(args)}  with env ERRAND_URL={url} ERRAND_API_KEY={key}",
    }


def _claude_code(url: str, key: str) -> str:
    exe = shutil.which("claude")
    cmd = ["mcp", "add", "--transport", "http", "--scope", "user", "errand", f"{url}/mcp",
           "--header", f"Authorization: Bearer {key}"]
    if not exe:
        return "claude CLI not found; run this yourself:\n  claude " + " ".join(
            f'"{c}"' if " " in c else c for c in cmd)
    subprocess.run([exe, "mcp", "remove", "errand", "--scope", "user"], capture_output=True)
    r = subprocess.run([exe, *cmd], capture_output=True, text=True)
    return "added to Claude Code (user scope)" if r.returncode == 0 else f"claude mcp add failed: {r.stderr.strip()}"


CLIENTS = {
    "claude-desktop": "Claude Desktop (stdio)",
    "claude-code": "Claude Code (remote HTTP)",
    "cursor": "Cursor (remote HTTP)",
    "vscode": "VS Code / GitHub Copilot, this workspace (remote HTTP)",
    "windsurf": "Windsurf (remote HTTP)",
    "gemini": "Gemini CLI (remote HTTP)",
    "codex": "OpenAI Codex CLI (stdio)",
}


def detected() -> list[str]:
    found = []
    if (_appdata() / "Claude").exists():
        found.append("claude-desktop")
    if shutil.which("claude"):
        found.append("claude-code")
    if (HOME / ".cursor").exists():
        found.append("cursor")
    if (HOME / ".codeium" / "windsurf").exists():
        found.append("windsurf")
    if (HOME / ".gemini").exists():
        found.append("gemini")
    if (HOME / ".codex").exists() or shutil.which("codex"):
        found.append("codex")
    return found


def connect(client: str, url: str, key: str) -> str:
    remote = f"{url}/mcp"
    hdr = {"Authorization": f"Bearer {key}"}
    if client == "claude-desktop":
        cmd, args = mcp_command()
        return _merge_json(_appdata() / "Claude" / "claude_desktop_config.json", "mcpServers",
                           {"command": cmd, "args": args, "env": {"ERRAND_URL": url, "ERRAND_API_KEY": key}}) + \
            " (restart Claude Desktop)"
    if client == "claude-code":
        return _claude_code(url, key)
    if client == "cursor":
        return _merge_json(HOME / ".cursor" / "mcp.json", "mcpServers", {"url": remote, "headers": hdr})
    if client == "vscode":
        return _merge_json(Path.cwd() / ".vscode" / "mcp.json", "servers", {"type": "http", "url": remote, "headers": hdr}) + \
            " (contains your key: keep .vscode/mcp.json out of git)"
    if client == "windsurf":
        return _merge_json(HOME / ".codeium" / "windsurf" / "mcp_config.json", "mcpServers", {"serverUrl": remote, "headers": hdr})
    if client == "gemini":
        return _merge_json(HOME / ".gemini" / "settings.json", "mcpServers", {"httpUrl": remote, "headers": hdr})
    if client == "codex":
        cmd, args = mcp_command()
        return _merge_codex_toml(HOME / ".codex" / "config.toml", cmd, args, {"ERRAND_URL": url, "ERRAND_API_KEY": key})
    raise SystemExit(f"unknown client {client!r}; choose from: {', '.join(CLIENTS)}, all, print")
