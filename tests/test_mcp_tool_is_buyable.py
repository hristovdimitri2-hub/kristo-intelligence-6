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

        def get(self, path, headers=None, query_string=None):
            seen["path"] = path
            seen["headers"] = headers or {}
            seen["query_string"] = query_string
            return FakeResponse()

    monkeypatch.setattr(main.app, "test_client", lambda: FakeClient())
    discovery._serve_paid_mcp_tool("/api/v1/whaleflow", 0.003, "BUYER-HEADER")
    assert seen["headers"].get("PAYMENT-SIGNATURE") == "BUYER-HEADER"
    assert seen["path"] == "/api/v1/whaleflow"


# ── the tool's arguments must reach the route they paid for ─────────────────
#
# Measured live, 09.11 19:26:49: `verify_seller_receiver` was paid for ($0.10,
# tx 0x697923104b312862fc333fd6464e542a77a7253a635a2070125ccbff9d7413f0, status
# 0x1) with a valid `receiver`, and the forward dropped it. The route answered
# 400 `receiver_required`, the tool fell back to the challenge, and the money was
# gone with the nonce already spent. Six tools without input in the same run
# worked, which is exactly why it went unnoticed.

def test_the_forward_carries_the_tools_arguments_as_query_parameters(monkeypatch):
    """THE BUG. Without this, a paid call to the one input-taking tool is
    unservable and the buyer's USDC is already settled."""
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

        def get(self, path, headers=None, query_string=None):
            seen["path"] = path
            seen["query_string"] = query_string
            return FakeResponse()

    monkeypatch.setattr(main.app, "test_client", lambda: FakeClient())
    body = discovery._serve_paid_mcp_tool(
        "/api/v1/verify-seller", 0.10, "H",
        {"receiver": "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f", "days": 7})
    assert body == {"ok": True}
    assert seen["path"] == "/api/v1/verify-seller"
    assert seen["query_string"] == {
        "receiver": "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f", "days": 7}


def _paid_forward_recorder(monkeypatch):
    """Replace the rail with a recorder: what reached it, and with what."""
    calls = []

    def fake(path, price, header, arguments=None):
        calls.append({"path": path, "price": price, "arguments": arguments})
        return {"ok": True, "served": True}

    monkeypatch.setattr(discovery, "_serve_paid_mcp_tool", fake)
    return calls


def _call_verify(client, arguments, header="PAYMENT-SIGNATURE-GOES-HERE"):
    resp = client.post("/mcp", headers={"PAYMENT-SIGNATURE": header}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "verify_seller_receiver", "arguments": arguments}})
    return resp.get_json() or {}


def test_a_paid_call_with_a_valid_receiver_reaches_the_route_with_it(monkeypatch):
    calls = _paid_forward_recorder(monkeypatch)
    with main.app.test_client() as client:
        body = _call_verify(client, {"receiver":
                                     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"})
    assert calls, "the paid call never reached the rail"
    assert calls[0]["path"] == "/api/v1/verify-seller"
    assert calls[0]["arguments"] == {
        "receiver": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"}
    assert ((body.get("result") or {}).get("structuredContent") or {}).get("ok")


def test_a_paid_call_that_names_no_receiver_is_refused_before_the_rail(monkeypatch):
    """THE MONEY GUARD. The rail settles before the route handler runs, so a
    call the route will reject must be rejected before it is ever forwarded —
    otherwise the buyer pays for a 400."""
    calls = _paid_forward_recorder(monkeypatch)
    with main.app.test_client() as client:
        body = _call_verify(client, {})
    assert not calls, "an argument-less paid call was forwarded to the rail"
    err = (body.get("error") or {}).get("message") or ""
    assert "receiver" in err, body
    assert "charged" in err, "the caller must be told nothing was charged"


def test_a_paid_call_with_a_malformed_receiver_is_refused_before_the_rail(monkeypatch):
    calls = _paid_forward_recorder(monkeypatch)
    with main.app.test_client() as client:
        body = _call_verify(client, {"receiver": "0xnot-an-address"})
    assert not calls, "a typo'd receiver was forwarded to the rail"
    assert "receiver" in ((body.get("error") or {}).get("message") or "")


def test_a_paid_call_with_an_unknown_argument_is_refused_before_the_rail(monkeypatch):
    """Every schema here declares additionalProperties false, so the contract
    says what happens to an argument the tool does not declare."""
    calls = _paid_forward_recorder(monkeypatch)
    with main.app.test_client() as client:
        body = _call_verify(client, {"receiver": "0x" + "11" * 20,
                                     "network": "base"})
    assert not calls
    assert "network" in ((body.get("error") or {}).get("message") or "")


def test_an_unpaid_call_still_sees_the_terms_even_with_bad_arguments(monkeypatch):
    """Validation lives on the PAID path only. An agent that has not been
    charged must still be able to read the price and the schema."""
    calls = _paid_forward_recorder(monkeypatch)
    with main.app.test_client() as client:
        resp = client.post("/mcp", json={
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "verify_seller_receiver", "arguments": {}}})
    sc = ((resp.get_json() or {}).get("result") or {}).get("structuredContent") or {}
    assert sc.get("error") == "payment_required"
    assert sc.get("accepts")
    assert not calls


def test_arguments_are_read_from_the_tools_own_schema():
    """No second copy of the rules: the tool's inputSchema decides."""
    from app.blueprints.discovery import _mcp_forward_arguments
    tool = next(t for t in discovery._mcp_tools("https://example.test")
                if t["name"] == "verify_seller_receiver")

    query, problem = _mcp_forward_arguments(tool, {"receiver": "0x" + "AB" * 20})
    assert problem is None
    assert query == {"receiver": "0x" + "ab" * 20}

    query, problem = _mcp_forward_arguments(tool, {"receiver": "0x" + "AB" * 20,
                                                   "days": "14"})
    assert problem is None and query["days"] == 14

    query, problem = _mcp_forward_arguments(tool, {"receiver": "0x" + "AB" * 20,
                                                   "days": "soon"})
    assert query == {} and "integer" in problem

    plain = next(t for t in discovery._mcp_tools("https://example.test")
                 if t["name"] == "get_whale_flow")
    assert _mcp_forward_arguments(plain, {}) == ({}, None)
    assert _mcp_forward_arguments(plain, None) == ({}, None)


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
