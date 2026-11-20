"""The x402lint conformance checks we can hold in place, as tests.

Measured 19.11.2026: x402lint graded the origin B, 84/100, with three FAILs and
three WARNs. Three of those were ours and mechanical, and each one is a rule
that a future edit can break silently — so each is asserted here rather than
fixed once:

  P8  desc-length-cap        one advertised description was 603 characters;
                             CDP truncates or rejects anything over 500
  S2  openapi-x402-scheme    components.securitySchemes.x402 was absent
  S4  paid-ops-security-402  seven paid operations carried no security
  S6  well-known-x402        /.well-known/x402 had no endpoints[]/accepts[]

The remaining WARNs are not encoded here because they are not single facts:
P5 (HEAD with an invalid X-Payment header) is about the paywall's response
codes, and D5 (not in the x402 ecosystem list) is a PR to someone else's repo.

Two things this file deliberately does NOT assert, because they are the trap
that made the scheme harmful in October: that the scheme states an amount, and
that it documents a manual "send N USDC then retry" flow. A scheme that repeats
a price goes stale the moment a route is repriced, and the 402 challenge is the
only authority on what to pay.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


def _paid_operations(spec):
    """Every operation that advertises itself as paid via x-payment-info."""
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and "x-payment-info" in op:
                yield path, method, op


def _free_operations(spec):
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if isinstance(op, dict) and "x-payment-info" not in op:
                yield path, method, op


# ── P8: the description length cap ───────────────────────────────────────────

def test_no_advertised_description_enters_the_400_character_danger_zone(client):
    """CDP truncates over 500; x402lint warns from 400.

    The hard cap is 500, but the lint's own wording is "keep advertised
    descriptions comfortably under 500 characters to avoid CDP truncation", and
    it reported 496 as "in the 400-500 char danger zone" — a WARN, not a pass.
    So the number asserted here is 400: where the warning starts, not where
    truncation does.

    The `/api/v1/verify-seller` description was 603 before the first trim.
    Truncation is worse than shortening here: the sentence that got cut was the
    honesty rule about reporting `partial` coverage, so the advertised text lost
    exactly the part that distinguishes the product from a reputation score.
    """
    spec = client.get("/openapi.json").get_json()

    over = []
    for path, method, op in _paid_operations(spec):
        for field in ("description", "summary"):
            text = op.get(field) or ""
            if len(text) > 400:
                over.append((path, method, field, len(text)))
    assert not over, "descriptions in the 400-500 danger zone: %r" % (over,)

    # The document's own description is advertised too, by the same crawler.
    info_description = spec["info"].get("description") or ""
    assert len(info_description) <= 400, len(info_description)


def test_the_trimmed_description_kept_the_honesty_rule(client):
    """A trim must not quietly delete the claim the product is sold on.

    The route's differentiator is that it reports its own coverage instead of
    presenting an unmeasured zero as a measured one. A shortening that kept the
    character count and dropped that sentence would pass the cap and lose the
    product.
    """
    spec = client.get("/openapi.json").get_json()
    text = spec["paths"]["/api/v1/verify-seller"]["get"]["description"]
    assert "partial" in text or "coverage" in text, text
    assert "chain data" in text and "reputation score" in text, text


# ── S2: the x402 security scheme ─────────────────────────────────────────────

def test_the_openapi_declares_the_x402_security_scheme(client):
    """S2: components.securitySchemes.x402 must exist.

    Removed in October on a third-party tool's advice (x402scan #1270) because
    an apiKey scheme made clients read the routes as "apiKey+paid". That advice
    was about the scheme's CONTENT — a flat "send 0.005 USDC" and a manual
    X-Payment-Address retry flow — not about the declaration existing. Both
    x402lint S2/S4 and x402scan's own DISCOVERY.md ("Auth requirements: use
    OpenAPI security + components.securitySchemes") ask for it.
    """
    spec = client.get("/openapi.json").get_json()
    schemes = (spec.get("components") or {}).get("securitySchemes") or {}
    assert "x402" in schemes, "components.securitySchemes.x402 is absent"

    scheme = schemes["x402"]
    # `http` with a custom scheme name, NOT `apiKey`. Measured against
    # agentcash's discovery tool: an apiKey declaration labels every paid route
    # "apiKey+paid" (the October regression), while http labels them "paid".
    # The header name still has to be stated, so it lives in the description.
    assert scheme.get("type") == "http", scheme
    assert scheme.get("scheme") == "x402", scheme
    assert "X-PAYMENT" in (scheme.get("description") or ""), scheme


def test_the_scheme_does_not_restate_a_price_or_a_manual_flow(client):
    """The two properties that made the October scheme harmful.

    A scheme that names an amount overpays cheap routes and under-describes dear
    ones; a scheme that documents a hand-rolled retry teaches callers a flow no
    x402 client implements. Both are the 402 challenge's job.
    """
    spec = client.get("/openapi.json").get_json()
    scheme = spec["components"]["securitySchemes"]["x402"]
    text = ((scheme.get("description") or "") + " ").lower()

    assert "402" in text, "the scheme must point at the 402 challenge"
    for banned in ("send 0.005", "0.003 usdc", "x-payment-address"):
        assert banned not in text, "the scheme restates %r" % banned
    # A literal USDC amount in the scheme would go stale on the next repricing.
    assert "usdc" not in text.replace("usdc authorization", ""), (
        "the scheme should not name a currency amount: %r" % text)


# ── S4: every paid operation requires the scheme and documents its 402 ───────

def test_every_paid_operation_requires_the_scheme(client):
    """S4: a paid operation without a security requirement reads as unpaid."""
    spec = client.get("/openapi.json").get_json()
    paid = list(_paid_operations(spec))
    assert len(paid) >= 7, "expected at least seven paid operations, got %d" % len(paid)

    for path, method, op in paid:
        security = op.get("security")
        assert isinstance(security, list) and security, (
            "%s %s has no security requirement" % (method.upper(), path))
        named = [set(entry) for entry in security if isinstance(entry, dict)]
        assert any("x402" in entry for entry in named), (
            "%s %s does not require the x402 scheme: %r"
            % (method.upper(), path, security))


def test_every_paid_operation_documents_its_402_and_its_price(client):
    """S4's second half, plus the x402scan requirement next to it."""
    spec = client.get("/openapi.json").get_json()
    for path, method, op in _paid_operations(spec):
        assert "402" in (op.get("responses") or {}), (
            "%s %s does not document a 402" % (method.upper(), path))
        price = ((op.get("x-payment-info") or {}).get("price") or {})
        assert price.get("mode") == "fixed", (path, price)
        assert price.get("amount"), (path, price)


def test_every_free_operation_declares_an_empty_security_list(client):
    """S3: the mirror image. A free route must not inherit the document default.

    Declaring the scheme once at components level is not enough to make this
    true — a document-level `security` would apply to every operation, so the
    free ones state their own empty list.
    """
    spec = client.get("/openapi.json").get_json()
    assert "security" not in spec, (
        "a document-level security requirement would make every free route "
        "demand a payment proof")
    for path, method, op in _free_operations(spec):
        assert op.get("security") == [], (
            "%s %s is free but does not declare an empty security list"
            % (method.upper(), path))


# ── S6: the well-known file must be parseable ────────────────────────────────

def test_the_well_known_file_carries_parseable_endpoints(client):
    """S6: x402lint read `200 JSON but no endpoints[]/accepts[] to parse`.

    `resources[]` is the x402scan fan-out shape and stays; `endpoints[]` is the
    same routes in the per-resource shape the lint reads. Both are served from
    the same list, so they cannot describe different sets of routes.
    """
    data = client.get("/.well-known/x402").get_json()
    endpoints = data.get("endpoints")
    assert isinstance(endpoints, list) and endpoints, "no endpoints[] to parse"

    resources = data["resources"]
    assert [e["url"] for e in endpoints] == [r["url"] for r in resources], (
        "endpoints[] and resources[] describe different routes")

    for endpoint in endpoints:
        assert endpoint.get("method") == "GET", endpoint
        accepts = endpoint.get("accepts")
        assert isinstance(accepts, list) and accepts, endpoint
        rail = accepts[0]
        assert rail.get("scheme") == "exact", rail
        assert rail.get("network") == "eip155:8453", rail
        # v2 states the amount in TOKEN ATOMIC units, as a string. "0.005"
        # here would be read as 0.005 atomic units — five thousandths of a
        # cent — and the challenge would be unpayable.
        amount = rail.get("amount")
        assert isinstance(amount, str) and amount.isdigit(), rail
        assert int(amount) >= 1_000, "amount looks like dollars, not atomic units"


def test_the_well_known_endpoints_agree_with_the_paywall(client):
    """The static file must not advertise a price the 402 does not charge."""
    import main

    data = client.get("/.well-known/x402").get_json()
    for endpoint in data["endpoints"]:
        path = endpoint["url"].split("://", 1)[1]
        path = "/" + path.split("/", 1)[1]
        expected = int(round(float(main.X402_PRICE_MAP[path]) * 1_000_000))
        assert int(endpoint["accepts"][0]["amount"]) == expected, (
            "%s advertises %s atomic units, the paywall charges %s"
            % (path, endpoint["accepts"][0]["amount"], expected))


# ── P5: HEAD must not settle ─────────────────────────────────────────────────

def test_head_on_a_paid_route_answers_the_challenge_and_never_settles(client):
    """P5 "head-no-settle": a HEAD with a junk X-PAYMENT answered 401/400/503.

    A HEAD receives no body, so there is nothing to deliver and nothing to
    charge for. Before this, a HEAD walked the full paid path: it consumed a
    free-tier slot, and with a credential present it entered settlement
    verification. The truthful answer is the 402 challenge, on every paid route,
    whatever credential arrives.
    """
    import main

    for path in sorted(main.X402_PAID_ENDPOINTS):
        r = client.head(path, headers={"X-PAYMENT": "not-a-real-payment"})
        assert r.status_code == 402, (
            "HEAD %s answered %s, not 402" % (path, r.status_code))
        # The challenge travels in the header, so a HEAD still carries the price
        # even though the body is dropped.
        assert r.headers.get("PAYMENT-REQUIRED"), path


def test_head_does_not_consume_the_free_tier(client):
    """A probe must not spend a free call an IP is entitled to.

    Uptime monitors and registries HEAD a route to see whether it is alive. If
    that spends the free tier, the first real caller is charged for a request
    nobody made — and the monitor's own probe looks like a purchase. Production
    runs with FREE_TIER_LIMIT=0, so the counter is asserted directly rather than
    through the GET that would follow it.
    """
    import main

    path = "/api/stats"
    main._free_tier_usage.clear()

    client.head(path)
    assert main._free_tier_usage.get("127.0.0.1", 0) == 0, (
        "a HEAD consumed a free-tier slot")

    # And the GET is not affected by the HEAD that preceded it: it is answered
    # by the same rule as a GET on a fresh client.
    assert client.get(path).status_code == 402

