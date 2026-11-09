"""An MCP tool must be BUYABLE, and must never be served without a sale.

THE GAP THIS CLOSES. `tools/call` built the x402 challenge and returned it — every
time, with no code that could accept a payment. An agent inside an MCP session
could read our terms and never complete a purchase, and the tool text told it to
"call <endpoint> with the payment header", i.e. go and pay somewhere else, which
an MCP client will not do.

That is the shape of `api.aiskills402.com`, measured in the same session: 175
listings, discovery-only MCP, and the FEWEST payers in the market census.

THE HOLE I INTRODUCED FIXING IT, and the reason half these tests exist. The first
version forwarded the caller's header to the HTTP route and treated a 200 as a
purchase. The forward arrives from 127.0.0.1 — loopback — and the free tier grants
on IP, so `PAYMENT-SIGNATURE: FAKE` returned the data for nothing:

    Free tier access: ip=127.0.0.1, used=1/1, endpoint=/api/v1/whaleflow

The test is therefore not "did it answer" but "DID A SETTLEMENT HAPPEN": the rail
emits a PAYMENT-RESPONSE header only when a real transaction settled.
"""

import json

import main
from app.blueprints import discovery


def _call(client, header=None, tool="get_whale_flow"):
    headers = {"PAYMENT-SIGNATURE": header} if header is not None else {}
    resp = client.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": {}}})
    return ((resp.get_json() or {}).get("result") or {}).get("structuredContent") or {}


# ── the security property: no settlement, no data ───────────────────────────

def test_an_unpaid_call_gets_the_challenge():
    with main.app.test_client() as client:
        body = _call(client)
    assert body.get("error") == "payment_required"
    assert body.get("accepts"), "the challenge must carry payable terms"


def test_a_fake_payment_header_does_not_buy_anything():
    """THE HOLE. This returned real data before the settlement check existed."""
    with main.app.test_client() as client:
        body = _call(client, "FAKE")
    assert body.get("error") == "payment_required", (
        "a forged payment header was served data — the forward accepted a 200 "
        "from loopback, where the free tier grants on IP")


def test_an_empty_payment_header_does_not_buy_anything():
    with main.app.test_client() as client:
        body = _call(client, "")
    assert body.get("error") == "payment_required"


def test_a_well_formed_but_unsigned_payload_does_not_buy_anything():
    """Base64 that decodes to JSON, so the shape checks pass and only the
    signature is wrong — the case a decoder-only check would let through."""
    import base64

    forged = base64.urlsafe_b64encode(
        json.dumps({"x402Version": 2, "scheme": "exact",
                    "network": "eip155:8453",
                    "payload": {"signature": "0x" + "00" * 65,
                                "authorization": {}}}).encode()).decode().rstrip("=")
    with main.app.test_client() as client:
        body = _call(client, forged)
    assert body.get("error") == "payment_required"


def test_a_200_without_a_settlement_is_refused(monkeypatch):
    """THE BELT AS WELL AS THE BRACES, asserted directly.

    Even if the route answers 200 — free tier, cache, a future change to the IP
    rules — the tool is not served unless the rail says a transaction settled.
    """
    class FakeResponse:
        status_code = 200
        headers = {"Content-Type": "application/json"}   # no PAYMENT-RESPONSE

        def get_json(self, silent=False):
            return {"ok": True, "whales": ["free data an attacker should not see"]}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(main.app, "test_client", lambda: FakeClient())
    assert discovery._serve_paid_mcp_tool("/api/v1/whaleflow", 0.003, "x") is None


def test_a_settlement_makes_it_servable(monkeypatch):
    """The positive half, so the guard cannot be satisfied by refusing always."""
    class FakeResponse:
        status_code = 200
        headers = {"PAYMENT-RESPONSE": "eyJzdWNjZXNzIjp0cnVlfQ=="}

        def get_json(self, silent=False):
            return {"ok": True, "whales": [{"amount": 5_000_000}]}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **k):
            return FakeResponse()

    monkeypatch.setattr(main.app, "test_client", lambda: FakeClient())
    body = discovery._serve_paid_mcp_tool("/api/v1/whaleflow", 0.003, "x")
    assert body == {"ok": True, "whales": [{"amount": 5_000_000}]}


def test_the_forward_carries_the_callers_own_header(monkeypatch):
    """It must be the BUYER's payment that is presented, not a fresh one — the
    sale has to belong to the caller who paid for it."""
    seen = {}

    class FakeResponse:
        status_code = 200
        headers = {"PAYMENT-RESPONSE": "ok"}

        def get_json(self, silent=False):
            return {"ok": True}

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path, headers=None):
            seen["path"] = path
            seen["headers"] = headers or {}
            return FakeResponse()

    monkeypatch.setattr(main.app, "test_client", lambda: FakeClient())
    discovery._serve_paid_mcp_tool("/api/v1/whaleflow", 0.003, "BUYER-HEADER")
    assert seen["headers"].get("PAYMENT-SIGNATURE") == "BUYER-HEADER"
    assert seen["path"] == "/api/v1/whaleflow"


# ── the buyable path exists at all ──────────────────────────────────────────

def test_the_handler_consults_the_rail_when_a_header_is_present():
    """Structural, because the real settlement needs a funded key: the handler
    must reach for the forward rather than returning the challenge first."""
    src = (discovery.__file__)
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "_serve_paid_mcp_tool(" in text
    assert "PAYMENT-SIGNATURE" in text
    # and the paid answer is returned BEFORE the challenge is
    paid_at = text.index("if paid_response is not None:")
    challenge_at = text.index("if payment_required is not None:")
    assert paid_at < challenge_at, (
        "the challenge is returned before the paid path is considered, so a "
        "paying agent is told to pay again")


def test_the_bazaar_declaration_is_retargeted_for_mcp():
    """The other half: an MCP tool declaring `type: http` is not an MCP resource,
    which is why the catalog showed 515 MCP entries and none of them ours."""
    with main.app.test_client() as client:
        body = _call(client)
    inp = (((body.get("extensions") or {}).get("bazaar") or {}).get("info") or {}).get("input") or {}
    assert inp.get("type") == "mcp"
    assert inp.get("toolName") == "get_whale_flow"
    assert "example" in inp and "inputSchema" in inp
