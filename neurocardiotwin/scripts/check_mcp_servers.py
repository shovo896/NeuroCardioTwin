"""Verify the three deployed NeuroCardioTwin MCP servers with a real Auth0 token.

The token is read from an environment variable and is never printed or written
to disk. Run after authenticating in the workspace:

  NCT_MCP_ACCESS_TOKEN='<access token>' \
    .venv/bin/python scripts/check_mcp_servers.py --call-safe-tool
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request


DEFAULT_BASE = "https://neurocardiotwin.vercel.app"
SAFE_TOOLS = {
    "workspace": "get_workspace_security",
    "knowledge": "get_knowledge_catalog",
    "models": "get_model_status",
}


def call(endpoint: str, token: str, request_id: int, method: str, params: dict | None = None) -> dict:
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{endpoint} returned HTTP {exc.code}: {detail}") from exc
    if "error" in body:
        raise RuntimeError(f"{endpoint} returned MCP error: {body['error'].get('message', 'unknown error')}")
    return body["result"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify NeuroCardioTwin MCP discovery and safe tools.")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="Deployed application origin.")
    parser.add_argument("--token-env", default="NCT_MCP_ACCESS_TOKEN", help="Environment variable containing an Auth0 access token.")
    parser.add_argument("--call-safe-tool", action="store_true", help="Also call one safe, read-only tool on each server.")
    args = parser.parse_args()
    token = os.getenv(args.token_env, "").strip()
    if not token:
        raise SystemExit(f"Set {args.token_env} to a fresh Auth0 access token with mcp:read; the token will not be printed.")
    base = args.base_url.rstrip("/")
    for request_id, server in enumerate(("workspace", "knowledge", "models"), start=1):
        endpoint = f"{base}/mcp/{server}"
        initialized = call(endpoint, token, request_id * 10, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "neurocardiotwin-mcp-check", "version": "1.0.0"}})
        tools = call(endpoint, token, request_id * 10 + 1, "tools/list")
        names = [tool.get("name") for tool in tools.get("tools", [])]
        print(f"{server}: {initialized['serverInfo']['name']} — {len(names)} tools: {', '.join(names)}")
        if args.call_safe_tool:
            result = call(endpoint, token, request_id * 10 + 2, "tools/call", {"name": SAFE_TOOLS[server], "arguments": {}})
            is_error = bool(result.get("isError"))
            print(f"  {SAFE_TOOLS[server]}: {'error' if is_error else 'ok'}")
            if is_error:
                raise SystemExit("A safe MCP tool returned an error.")


if __name__ == "__main__":
    main()
