"""Audit #6 BREAK 1: /mcp/sse must be a REAL HTTP+SSE transport.

The official python client (mcp 2.x sse_client) does exactly this:

    GET  /mcp/sse                     <- reads `event: endpoint` -> POST url
    POST <endpoint> (raise_for_status) <- one JSON-RPC message per POST
    read `event: message`             <- the server's JSON-RPC responses

The Flask test client cannot drive this: it buffers the SSE response until
the generator finishes, which deadlocks against the POST. So the test runs a
REAL threaded local server and speaks the wire protocol over sockets — the
same flow the official client performs against production.
"""
from __future__ import annotations

import json
import threading

import requests


def _make_live_server(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.dashboard_store import DashboardStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))

    from werkzeug.serving import make_server
    server = make_server("127.0.0.1", 0, main.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _sse_events(stream):
    """Yield (event, data) pairs from ONE continuous iter_lines pass.

    Must be a single long-lived generator: abandoning a chunked
    iter_lines mid-stream closes the connection (GC -> urllib3), so a
    second independent read would just see EOF. Holding THIS generator
    alive between reads keeps the stream open.
    """
    current_event = None
    for raw in stream.iter_lines(decode_unicode=True):
        if raw is None:
            continue
        if raw.startswith("event:"):
            current_event = raw.split(":", 1)[1].strip()
        elif raw.startswith("data:") and current_event:
            yield current_event, raw.split(":", 1)[1].strip()
            current_event = None
        elif raw == "":
            current_event = None


def _next_event(events, want):
    """Pull from the shared stream until `event == want`."""
    for ev, data in events:
        if ev == want:
            return data
    raise AssertionError(f"SSE stream ended without event: {want}")


def test_sse_full_round_trip_like_the_official_client(monkeypatch, tmp_path):
    server, thread = _make_live_server(monkeypatch, tmp_path)
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        with requests.get(f"{base}/mcp/sse", stream=True, timeout=20) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            events = _sse_events(r)

            # 1) endpoint event must advertise a POST-able path, NOT itself
            endpoint = _next_event(events, "endpoint")
            assert "/mcp/message?sessionId=" in endpoint, endpoint
            assert not endpoint.rstrip("/").endswith("/mcp/sse")

            # 2) initialize — exactly what their client POSTs
            pr = requests.post(endpoint, timeout=10, json={
                "jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-11-25",
                           "capabilities": {},
                           "clientInfo": {"name": "audit6-official",
                                          "version": "1.0"}},
            })
            assert pr.status_code == 202 and pr.content == b"", pr.text
            init = json.loads(_next_event(events, "message"))
            assert init["id"] == 1
            assert init["result"]["protocolVersion"] == "2025-11-25"
            assert init["result"]["serverInfo"]["name"] == "kristo-intelligence"
            assert "tools" in init["result"]["capabilities"]

            # 3) notifications/initialized — 202, no message pushed
            nr = requests.post(endpoint, timeout=10, json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            })
            assert nr.status_code == 202 and nr.content == b""

            # 4) tools/list — the REAL handler's answer (not canned)
            requests.post(endpoint, timeout=10, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            tools = json.loads(_next_event(events, "message"))
            assert tools["id"] == 2
            names = [t["name"] for t in tools["result"]["tools"]]
            # Every paid route must be callable over MCP. This list used to
            # carry only three, so the flagship /api/v1/signal could not be
            # bought from Claude Desktop or Cursor at all, while agents.json
            # described all of them.
            assert names == ["get_market_stats", "get_onchain_sales",
                             "get_bot_status", "get_trading_signal",
                             "get_whale_flow", "get_arbitrage_opportunities",
                             "verify_seller_receiver", "get_demand_census"]
            for t in tools["result"]["tools"]:
                assert "price_usdc" in t["x402"]

            # 5) tools/call — x402 structuredContent travels the SSE rail too
            requests.post(endpoint, timeout=10, json={
                "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                "params": {"name": "get_bot_status", "arguments": {}}})
            call = json.loads(_next_event(events, "message"))
            assert call["id"] == 3
            x402 = call["result"]["structuredContent"]["x402"]
            assert x402["endpoint"].endswith("/api/bot-status")
            assert x402["price_usdc"] > 0
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_every_mcp_tool_advertises_the_paywall_real_price():
    """The tool list must not be able to quote a price the paywall refuses.

    Every route price is environment-overridable and X402_PRICE_MAP is the
    paywall's own source of truth. The tools used the flat X402_FEE_USDC alias,
    which happened to match the three routes they exposed — but the moment a
    route is repriced, a hardcoded manifest starts advertising a number the 402
    challenge contradicts. An agent that trusts it underfunds its authorization
    and gets rejected.

    WHAT THE LIST IS, now that it is no longer the whole price map. It is the
    public VITRINE, and a route can be paid and priced without being catalogued
    yet — the paywall-only stage the whale-flow spec calls condition 4
    ("unlisted until it passes a paid canary"). `/api/v1/demand-census` sat in
    that stage from 24.11.2026 until 26.11.2026, when its paid canary settled and
    the owner approved its promotion, and it is an eighth MCP tool from that day.
    It was recorded here as impossible because the official registry rejects a
    publisher extension over 4096 bytes and server.json looked to have room for
    no eighth row — that turned out to be true of the bytes and false of the
    block, which was carrying repetition: two discovery URLs already present in
    the document's own `remotes`, and cross-reference tails repeated across tool
    descriptions. Trimming those made room (see
    tests/test_server_json_registry_limits.py, which still enforces the limit and
    the headroom). The assertion is therefore the one that still means what it
    always meant — every tool offered is a route the paywall charges for, at that
    route's own price, and the catalogue is exactly the vitrine.
    """
    import main
    from app.blueprints import discovery

    tools = discovery._mcp_tools("https://example.invalid")
    routes = [t["x402"]["endpoint"].rsplit("https://example.invalid", 1)[-1]
              for t in tools]

    # The catalogue is exactly the vitrine, and every row in it is priced.
    assert sorted(routes) == sorted(r["endpoint"]
                                    for r in main.REAL_X402_ROUTES)
    assert len(tools) == len(main.REAL_X402_ROUTES)
    assert set(routes) <= set(main.X402_PRICE_MAP), (
        "a tool is offered for a route the paywall has no price for: %s"
        % sorted(set(routes) - set(main.X402_PRICE_MAP)))

    for tool in tools:
        route = tool["x402"]["endpoint"].rsplit("https://example.invalid", 1)[-1]
        assert float(tool["x402"]["price_usdc"]) == float(
            main.X402_PRICE_MAP[route]), (
            f"{tool['name']} advertises {tool['x402']['price_usdc']} but the "
            f"paywall charges {main.X402_PRICE_MAP[route]} for {route}")

    # The flagship must be reachable, and the two cheap routes must not be
    # flattened to the base fee.
    by_name = {t["name"]: t for t in tools}
    assert by_name["get_trading_signal"]["x402"]["price_usdc"] == \
        main.X402_PRICE_MAP["/api/v1/signal"]
    assert by_name["get_whale_flow"]["x402"]["price_usdc"] == \
        main.X402_PRICE_MAP["/api/v1/whaleflow"]


def test_initialize_without_version_falls_back_to_2025_11_25():
    """Both transports share _mcp_dispatch: the fallback (client that omits
    protocolVersion) is 2025-11-25 — the OLD SSE canned answer was a stale
    2024-11-05 that no longer matched streamable."""
    import main as _main
    from app.blueprints.discovery import _mcp_dispatch

    with _main.app.test_request_context("/mcp", method="POST"):
        kind, payload = _mcp_dispatch({
            "jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    assert kind == "response"
    assert payload["result"]["protocolVersion"] == "2025-11-25"

    # …and an echoed version still wins (streamable's historic behaviour).
    with _main.app.test_request_context("/mcp", method="POST"):
        kind, payload = _mcp_dispatch({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"}})
    assert payload["result"]["protocolVersion"] == "2025-06-18"