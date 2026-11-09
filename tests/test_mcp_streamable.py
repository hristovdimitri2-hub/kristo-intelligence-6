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


# ── the priced tool result must carry payable terms, not prose (07.11) ───────
#
# An independent prober read our priced MCP tool result as
# `payment_terms_unreadable` — "says payment is required, but without x402 terms
# we can read: a listing cannot verify yet" — and said plainly that an agent
# "cannot pay it in-session". The tool named a URL to go and pay somewhere else,
# which an agent inside an MCP session will not do. These tests hold the fix.


def _priced_call(client, name):
    r = _post(client, {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                       "params": {"name": name, "arguments": {}}})
    assert r.status_code == 200
    return r.get_json()["result"]


def test_a_priced_tool_answers_with_the_canonical_payment_required_object(client):
    """x402Version + accepts[] must be present, or the listing cannot verify."""
    sc = _priced_call(client, "get_trading_signal")["structuredContent"]

    assert sc["x402Version"] == 2
    assert isinstance(sc.get("accepts"), list) and sc["accepts"], (
        "no machine-readable accepts[] — this is exactly what made the listing "
        "unverifiable and the tool unpayable in-session")
    assert "resource" in sc and "extensions" in sc


def test_the_mcp_terms_cannot_drift_from_the_http_402(client):
    """The assertion that matters: MCP must quote the price the 402 charges.

    Both are built by the same `_x402_challenge_core` call, so an agent that
    trusts the MCP terms and an agent that reads the 402 envelope are told the
    same amount, receiver, network and asset.

    The free tier is exhausted first, or this route answers 200 in tests and
    there is no challenge to compare against.
    """
    import main

    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999   # exhaust it → a real 402
    try:
        mcp_accept = _priced_call(client, "get_trading_signal")[
            "structuredContent"]["accepts"][0]

        live = client.get("/api/v1/signal")
        assert live.status_code == 402, live.status_code
        http_accept = live.get_json()["accepts"][0]

        for field in ("scheme", "network", "amount", "payTo", "asset"):
            assert mcp_accept[field] == http_accept[field], (
                f"{field}: MCP publishes {mcp_accept[field]!r} but the 402 at "
                f"that route charges {http_accept[field]!r}")
    finally:
        main._free_tier_usage.clear()


def test_the_mcp_payment_terms_are_also_readable_as_text(client):
    """A client that only reads content[] must still be able to pay."""
    result = _priced_call(client, "get_whale_flow")
    texts = [c["text"] for c in result["content"] if c.get("type") == "text"]
    parsed = [json.loads(t) for t in texts if t.strip().startswith("{")]

    assert parsed, "the x402 terms are unreachable from content[]"
    assert parsed[0]["x402Version"] == 2
    assert parsed[0]["accepts"][0]["amount"] == "3000", (
        "0.003 USDC is 3000 atomic units on Base")


def test_the_resource_url_is_the_route_not_a_url_glued_to_a_url(client):
    """`x["endpoint"]` is absolute; the builder wants the path.

    Passing it through unchanged produced "http://host/https://host/api/..."
    """
    sc = _priced_call(client, "get_trading_signal")["structuredContent"]
    url = sc["resource"]["url"]

    # THE INVARIANT, and it is the point of this test: a url with a url glued
    # into it is never correct. The first version of the MCP retargeting produced
    # exactly that — "http://localhost/api/v1/whaleflow/mcp#get_whale_flow" — and
    # this assertion is what caught it.
    assert url.count("://") == 1, url
    # WHAT CHANGED (09.11), and why this second assertion had to. The resource
    # now names the TOOL, not the HTTP route. Measured: a real MCP payment
    # settled through CDP and the catalog still showed ZERO MCP entries for us,
    # because CDP indexes by `resource.url` and we were handing it the route we
    # already had — so the settlement was filed under the endpoint and never
    # under the tool. The catalog's own MCP entries are shaped
    # `<mcp endpoint>#<toolName>`, which is what makes 515 of them addressable as
    # tools rather than as endpoints.
    assert url.endswith("/mcp#get_trading_signal"), url


def test_the_mcp_tool_keeps_the_legacy_x402_key(client):
    """Clients already reading structuredContent["x402"] must not break."""
    sc = _priced_call(client, "get_onchain_sales")["structuredContent"]

    assert sc["x402"]["price_usdc"] > 0
    assert sc["x402"]["endpoint"].startswith("http")
    assert sc["accepts"][0]["amount"] == "5000"

