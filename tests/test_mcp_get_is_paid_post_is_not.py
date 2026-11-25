# -*- coding: utf-8 -*-
"""GET /mcp is a paid resource; POST /mcp is not.

Measured on 25.11.2026 with Coinbase's own endpoint validator
(POST api.cdp.coinbase.com/platform/v2/x402/validate): every HTTP route passed
all 25 checks and `/mcp` failed at `returns_402` — "Endpoint returns 200 OK — it
needs to return 402 for unauthenticated requests to be discoverable" — because the
validator probes an indexed URL with a bare GET, and GET /mcp served the summary
document for free. The eight `/mcp#tool#tool` rows in the Bazaar are indexed
against this path, so failing that check is what lets them decay.

The other half is a spec requirement, and it is the reason the fix is NOT "make
/mcp answer 402". specs/transports-v2/mcp.md: "When a tool requires payment,
servers MUST return a tool result with `isError: true` containing the
PaymentRequired data" — the tool result is MCP's equivalent of the 402, and the
payment returns at `_meta["x402/payment"]`. So a POSTed tool call must keep
answering 200 with that tool result, and these tests pin both halves so that a
later change cannot trade one for the other.
"""
import base64
import json

import pytest

import main


@pytest.fixture()
def client(monkeypatch):
    """The same shape as tests/test_bazaar_output_example.py: no database, no
    background threads, and the free tier spent so a paid route answers its
    challenge rather than a free call."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main as module
    module._free_tier_usage.clear()
    module._free_tier_usage["127.0.0.1"] = 999
    yield module.app.test_client()
    module._free_tier_usage.clear()


def test_get_mcp_answers_the_challenge_the_validator_requires(client):
    """A bare GET is what the index probes, so a bare GET must be quoted."""
    main._free_tier_usage.clear()
    response = client.get("/mcp")

    assert response.status_code == 402, (
        "GET /mcp answered %s; the Bazaar preflight requires 402 for an "
        "unauthenticated request" % response.status_code)

    header = response.headers.get("PAYMENT-REQUIRED")
    assert header, "no PAYMENT-REQUIRED header on the GET /mcp challenge"
    decoded = json.loads(base64.b64decode(header))
    assert decoded["x402Version"] == 2
    assert decoded["accepts"][0]["payTo"] == main.X402_RECEIVER_ADDRESS
    assert decoded["resource"]["url"].endswith("/mcp")


def test_the_challenge_declares_the_bazaar_block_the_validator_reads(client):
    """`has_bazaar_extension` … `bazaar.schema` are checks 16–25 of the preflight."""
    main._free_tier_usage.clear()
    body = client.get("/mcp").get_json()
    bazaar = (body.get("extensions") or {}).get("bazaar") or {}

    assert bazaar.get("info"), "no bazaar info block on the GET /mcp challenge"
    assert bazaar["info"]["input"]["method"] == "GET"
    assert bazaar["info"].get("output", {}).get("example"), (
        "no output example — the preflight's `bazaar.info.output.example` check")
    assert bazaar.get("schema"), "no bazaar schema — the preflight's last check"


def test_a_posted_tool_call_is_never_challenged_at_the_http_level(client):
    """The spec's MUST: the tool result carries the challenge, not the status."""
    response = client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "get_trading_signal", "arguments": {}},
    })

    assert response.status_code == 200, (
        "POST /mcp answered %s — an HTTP 402 here breaks every documented x402 "
        "MCP client" % response.status_code)

    result = response.get_json()["result"]
    assert result["isError"] is True
    assert result["structuredContent"]["accepts"][0]["payTo"] == \
        main.X402_RECEIVER_ADDRESS
    assert json.loads(result["content"][0]["text"])["x402Version"] == 2


def test_the_free_manifest_is_still_free(client):
    """The document GET /mcp used to serve is not taken away, only moved."""
    assert client.get("/mcp.json").status_code == 200


def test_the_mcp_transport_methods_stay_classified_as_free():
    """F-21: a route in neither set is unclassified, and that is not "free"."""
    assert "/mcp" in main.X402_FREE_ENDPOINTS
    assert "/mcp" in main.X402_PAID_ENDPOINTS
    assert "/mcp/sse" in main.X402_FREE_ENDPOINTS
    assert "/mcp/message" in main.X402_FREE_ENDPOINTS
