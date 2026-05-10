"""MCP bridge for PMOVES mesh: Agent Zero, Archon, Supabase, Neo4j topology.

Provides Agent Zero-callable tools to list registered MCP endpoints,
route JSON-RPC calls to named servers, and health-check individual servers.
Endpoint registry loaded from config/mcp-topology.yaml (bundled) or
$MCP_TOPOLOGY_PATH env override.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_TOPOLOGY_PATH = os.environ.get(
    "MCP_TOPOLOGY_PATH",
    str(pathlib.Path(__file__).parent.parent / "config" / "mcp-topology.yaml"),
)
_topology_cache: Optional[Dict[str, Any]] = None


def _load_topology() -> Dict[str, Any]:
    global _topology_cache
    if _topology_cache is not None:
        return _topology_cache

    p = pathlib.Path(_TOPOLOGY_PATH)
    if not p.exists():
        _topology_cache = {"servers": []}
        return _topology_cache

    text = p.read_text(encoding="utf-8")
    if _HAS_YAML:
        _topology_cache = yaml.safe_load(text) or {"servers": []}
    else:
        # Fallback: treat as JSON (topology.yaml is also valid JSON if needed)
        try:
            _topology_cache = json.loads(text)
        except Exception:
            _topology_cache = {"servers": []}
    return _topology_cache


def list_endpoints() -> List[Dict[str, Any]]:
    """List all registered MCP endpoints from the topology config.

    Returns:
        List of server dicts: name, url, transport, description, tags.
    """
    topo = _load_topology()
    return topo.get("servers", [])


def health_check(server: str) -> bool:
    """Ping a named MCP server's health endpoint.

    Args:
        server: Server name as registered in mcp-topology.yaml.

    Returns:
        True if server responds with HTTP 2xx, False otherwise.
    """
    topo = _load_topology()
    servers = {s["name"]: s for s in topo.get("servers", [])}
    entry = servers.get(server)
    if not entry:
        return False

    url = entry.get("url", "")
    health_path = entry.get("health_path", "/")
    full_url = url.rstrip("/") + health_path

    try:
        with urllib.request.urlopen(full_url, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def call_mcp(
    server: str,
    method: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Route a JSON-RPC 2.0 call to a named MCP server.

    Args:
        server: Server name as registered in mcp-topology.yaml.
        method: MCP method name (e.g. "tools/list", "tools/call").
        params: Method parameters dict.

    Returns:
        JSON-RPC response dict (result or error key).
    """
    topo = _load_topology()
    servers = {s["name"]: s for s in topo.get("servers", [])}
    entry = servers.get(server)
    if not entry:
        return {"error": f"Unknown MCP server: {server}. Known: {list(servers)}"}

    url = entry.get("url", "").rstrip("/") + "/mcp"
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {exc.code}: {body[:500]}"}
    except Exception as exc:
        return {"error": str(exc)}
