"""Tests for the MCP Streamable HTTP transport (POST /mcp) — additive to SSE."""

import json

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    return main.app.test_client()


def _post(client, payload):
    return client.post("/mcp", data=json.dumps(payload),
                       content_type="application/json")


def test_mcp_streamable_initialize(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": "2025-03-26"}})
    assert r.status_code == 200
    body = r.get_json()
    assert body["jsonrpc"] == "2.0" and body["id"] == 1
    assert body["result"]["serverInfo"]["name"] == "kristo-intelligence"
    assert "tools" in body["result"]["capabilities"]


def test_mcp_streamable_tools_list_advertises_x402(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert r.status_code == 200
    tools = r.get_json()["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"get_market_stats", "get_onchain_sales", "get_bot_status"} <= names
    for t in tools:
        x = t["x402"]
        assert x["price_usdc"] > 0 and x["chain_id"] and x["receiver"]
        assert x["endpoint"].startswith("http")


def test_mcp_streamable_notification_202(client):
    r = _post(client, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202 and not r.data


def test_mcp_streamable_ping(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert r.status_code == 200 and r.get_json()["result"] == {}


def test_mcp_streamable_tools_call_returns_payment_instructions_not_execution(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "get_market_stats", "arguments": {}}})
    assert r.status_code == 200
    body = r.get_json()["result"]
    text = body["content"][0]["text"]
    assert "x402" in text and "USDC" in text
    # The paid endpoint is NOT executed here — the tool points at the 402 flow.
    assert body["structuredContent"]["x402"]["endpoint"].endswith("/api/stats")


def test_mcp_streamable_unknown_tool_error_envelope(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                       "params": {"name": "no_such_tool"}})
    assert r.status_code == 200  # JSON-RPC errors ride inside HTTP 200
    assert r.get_json()["error"]["code"] == -32602


def test_mcp_streamable_unknown_method(client):
    r = _post(client, {"jsonrpc": "2.0", "id": 6, "method": "bogus/method"})
    assert r.status_code == 200
    assert r.get_json()["error"]["code"] == -32601


def test_mcp_streamable_invalid_body(client):
    r = client.post("/mcp", data="not json",
                    content_type="application/json")
    assert r.status_code == 400


def test_mcp_delete_session_is_stateless_204(client):
    r = client.delete("/mcp")
    assert r.status_code == 204


def test_get_mcp_info_unchanged_after_streamable_addition(client):
    """GET /mcp (the human/machine info view) must be untouched."""
    r = client.get("/mcp")
    assert r.status_code == 200
    assert r.get_json()["mcp"]["sse_endpoint"].endswith("/mcp/sse")


def test_mcp_json_lists_exactly_the_tools_the_protocol_serves(client):
    """/mcp.json names a tool an agent will call, so it must name real ones.

    It listed nine. One of them, "get_sales_history", was the old name of
    "get_onchain_sales" - the protocol, agents.json and server.json had all moved
    on and this document had not, so an agent that trusted it called a tool that
    does not exist and never discovered the one that does. The other three,
    get_mcp_manifest / get_x402_discovery / get_openapi_spec, are plain HTTP GETs;
    tools/call on them fails. They are advertised under "free_endpoints" now.

    Nothing caught it because no test compared this file to the protocol. The
    names it got wrong appear in no assertion anywhere in the suite, while three
    separate tests pinned the protocol's own names - so the suite was green on
    both sides of a disagreement it never put side by side.
    """
    listing = _post(client, {"jsonrpc": "2.0", "id": 7, "method": "tools/list"})
    served = {t["name"] for t in listing.get_json()["result"]["tools"]}

    doc = client.get("/mcp.json").get_json()
    listed = {t["name"] for t in doc["tools"]}

    assert listed == served, (
        "/mcp.json advertises %s but the protocol serves %s (it names %s that do "
        "not exist, and omits %s)"
        % (sorted(listed), sorted(served),
           sorted(listed - served), sorted(served - listed)))

    # The names are the right strings; now prove each one is actually callable, so
    # a rename that keeps the two lists in step but breaks dispatch still fails.
    for index, name in enumerate(sorted(listed)):
        call = _post(client, {"jsonrpc": "2.0", "id": 200 + index,
                              "method": "tools/call",
                              "params": {"name": name, "arguments": {}}})
        body = call.get_json()
        assert "error" not in body, (
            "%s is advertised in /mcp.json and served by tools/list but "
            "tools/call rejects it: %s" % (name, body.get("error")))
        endpoint = body["result"]["structuredContent"]["x402"]["endpoint"]
        assert endpoint.startswith("http") and "/api/" in endpoint, (name, endpoint)


def test_mcp_json_free_endpoints_are_not_advertised_as_tools(client):
    """The three free HTTP endpoints must stay out of the callable tool list."""
    doc = client.get("/mcp.json").get_json()
    names = {t["name"] for t in doc["tools"]}

    for removed in ("get_mcp_manifest", "get_x402_discovery", "get_openapi_spec"):
        assert removed not in names, (
            "%s is a plain GET endpoint; naming it as an MCP tool makes "
            "tools/call fail" % removed)

    # ...but they are still published, so nothing was lost in the move.
    free = {entry["endpoint"] for entry in doc["free_endpoints"]}
    for path in ("/api/mcp/manifest", "/.well-known/x402.json", "/openapi.json"):
        assert any(entry.endswith(path) for entry in free), (path, sorted(free))
