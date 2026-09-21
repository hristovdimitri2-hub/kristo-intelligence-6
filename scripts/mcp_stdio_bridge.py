#!/usr/bin/env python3
"""MCP stdio bridge — the SAME server, transported over stdin/stdout.

SLEEPING ASSET — deliberately NOT wired into any CMD
---------------------------------------------------
Nothing in this repository runs this file: neither `Dockerfile`, nor `Procfile`,
nor Render's start command (`python main.py`) reference it, and it is therefore
never part of a normal deploy. It is kept ready for exactly two situations:

1. Glama's Docker hosting refuses a REMOTE URL and only introspects a container
   with `docker run -it` (stdio, no published port). Their generator contains
   zero `EXPOSE`/`-p`/`localhost`, so an HTTP-only server cannot answer it.
2. We ever want a listing that is INDEPENDENT of Render (a self-contained image
   that answers MCP without touching kristo-intelligence-api.onrender.com).

Until one of those happens this file stays dormant on purpose.

What it does
------------
Kristo Intelligence's MCP server is HTTP: Streamable HTTP at `POST /mcp` and SSE
at `GET /mcp/sse` — that is what Render serves and what `/mcp.json` advertises.

This bridge is a pure TRANSPORT adapter: it reads one JSON-RPC 2.0 message per
line from stdin, hands it to the REAL Flask handler (the very same `app` object
Render serves, in-process through Flask's test client — no port, no network, no
proxying to any external endpoint), and writes the answer back on stdout.

No tool, price, paywall or auth behaviour changes: every payload is produced by
`app/blueprints/discovery.py`, i.e. byte-for-byte what `/mcp` answers on Render.

stdout is reserved for protocol frames: `_reserve_stdout()` duplicates fd 1
first and then points `sys.stdout` at stderr, so anything the app prints or logs
can never corrupt the JSON-RPC stream.

Usage (only if the decision above is taken)
-------------------------------------------
    CMD ["python", "scripts/mcp_stdio_bridge.py"]

Set `KRISTO_DISABLE_BACKGROUND_THREADS=true` in the container environment if the
host wants a purely request-serving process (the agent loop, Telegram poller and
monitor threads are then skipped — see main.py).
"""
from __future__ import annotations

import json
import logging
import os
import sys

_HEADERS = {"Accept": "application/json, text/event-stream",
            "Content-Type": "application/json"}

_PROTOCOL_OUT = None


def _reserve_stdout():
    """Duplicate the real stdout for protocol frames; send everything else away.

    Called lazily (never at import) so tests can import this module freely.
    """
    global _PROTOCOL_OUT
    if _PROTOCOL_OUT is None:
        _PROTOCOL_OUT = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
        sys.stdout = sys.stderr
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    return _PROTOCOL_OUT


def _client():
    """The real Flask app object, imported AFTER stdout has been reserved."""
    from main import app
    return app.test_client()


def forward(message: dict, client) -> dict:
    """Hand one JSON-RPC message to the real /mcp handler and return its answer."""
    resp = client.post("/mcp", json=message, headers=_HEADERS)
    try:
        return resp.get_json()
    except Exception:                                    # pragma: no cover
        return {"jsonrpc": "2.0", "id": message.get("id"),
                "error": {"code": -32603, "message": "internal error"}}


def handle_line(line: str, client):
    """The reply for one stdin line, or None when nothing must be written.

    None means "no frame on stdout": blank lines and JSON-RPC notifications
    (no `id`, or a `notifications/...` method) are never answered.
    """
    text = line.strip()
    if not text:
        return None
    try:
        message = json.loads(text)
    except Exception:
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"}}
    if not isinstance(message, dict):
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32600, "message": "Invalid Request"}}
    if "id" not in message or str(message.get("method", "")).startswith(
            "notifications/"):
        return None
    return forward(message, client)


def run(in_stream=None, out_stream=None, client=None) -> int:
    """Serve JSON-RPC over the given streams until stdin ends."""
    out = out_stream if out_stream is not None else _reserve_stdout()
    active_client = client if client is not None else _client()
    for line in (in_stream if in_stream is not None else sys.stdin):
        reply = handle_line(line, active_client)
        if reply is None:
            continue
        out.write(json.dumps(reply) + "\n")
        out.flush()
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
