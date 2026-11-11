# -*- coding: utf-8 -*-
"""The 402 must declare the input the handler actually reads.

THE DEFECT THIS FILE EXISTS FOR. Every paid route published

    queryParams: {}   with additionalProperties false
    "No query parameters: none are required — call this route as plain GET
     without a query string."

That was true of six of the seven routes and false of /api/v1/verify-seller,
whose handler opens with `request.args.get("receiver")` and answers
HTTP 400 receiver_required without it. Our own OpenAPI document
(app/blueprints/discovery.py) had always declared `receiver` required for that
same path, so the service published two contradictory descriptions of one
endpoint — and the 402 is the copy CDP indexes out of
paymentPayload.extensions.bazaar, i.e. the one an agent reads before paying.

The cost was measured on 10.11.2026: the listing call for the /api/v1/seller-check
alias paid $0.10 and received HTTP 400 receiver_required. The declaration had
told the agent, in as many words, that no input was needed.

WHY THE GUARD IS SHAPED LIKE THIS. The previous guard asserted the map was
empty for three routes that genuinely take no arguments — an empty map was the
expected value, so it passed for the wrong reason on the seventh. These tests
derive the expectation from the HANDLER SOURCE rather than from a list, so a
route that starts reading a new parameter cannot ship a challenge that denies it.
"""
import inspect
import re

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def _info_for(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path} did not answer 402: {r.status_code}"
    return r.get_json()["extensions"]["bazaar"]["info"]


def _schema_for(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path} did not answer 402: {r.status_code}"
    return (r.get_json()["extensions"]["bazaar"]["schema"]["properties"]
            ["input"]["properties"]["queryParams"])


def _handler_reads(path):
    """Every query-param name the route's own view function reads."""
    import main
    for rule in main.app.url_map.iter_rules():
        if str(rule) == path:
            fn = main.app.view_functions[rule.endpoint]
            src = inspect.getsource(fn)
            return set(re.findall(
                r'request\.args\.get\(\s*["\']([^"\']+)["\']', src))
    raise AssertionError(f"no URL rule for {path}")


CANONICAL_SELLER = "/api/v1/verify-seller"
ALIAS_SELLER = "/api/v1/seller-check"


# ── 1. the rule: declared input == read input, in both directions ────────────

def test_every_paid_route_declares_exactly_the_parameters_it_reads(client):
    """The invariant. Derived from handler source, not from a hand-kept list.

    A route that reads a parameter must declare it (or the challenge misleads a
    paying agent); a route that declares one it never reads is the opposite lie,
    advertising an interface that does not exist.
    """
    import main
    assert main.X402_PAID_ENDPOINTS, "canonical paid-route set is empty"
    for path in sorted(main.X402_PAID_ENDPOINTS):
        declared = set((_info_for(client, path)["input"]["queryParams"]
                        or {}).keys())
        read = _handler_reads(path)
        assert declared == read, (
            f"{path}: 402 declares {sorted(declared)} but the handler reads "
            f"{sorted(read)}")


# ── 2. the specific contract the seller routes have ─────────────────────────

def test_the_seller_routes_declare_receiver_as_required(client):
    """receiver is not optional: without it the route reads nothing."""
    for path in (CANONICAL_SELLER, ALIAS_SELLER):
        info = _info_for(client, path)
        declared = info["input"]["queryParams"]
        assert "receiver" in declared, f"{path}: receiver not declared"
        assert "days" in declared, f"{path}: days not declared"
        schema = _schema_for(client, path)
        assert "receiver" in schema["required"], (
            f"{path}: receiver is not marked required")
        assert schema["properties"]["receiver"]["type"] == "string"
        assert schema["properties"]["days"]["type"] == "integer"


def test_the_seller_challenge_does_not_deny_its_own_required_parameter(client):
    """The exact sentence that caused the $0.10 400 must be gone.

    The empty-map wording is correct for six routes; if it appears on a route
    that requires `receiver`, the challenge is instructing an agent to call it in
    a way that cannot succeed.
    """
    for path in (CANONICAL_SELLER, ALIAS_SELLER):
        text = _schema_for(client, path)["description"]
        assert "none are required" not in text.lower(), (
            f"{path}: still claims no query parameters are required")
        assert "REQUIRED" in text or "required" in text, (
            f"{path}: does not state that receiver is required")
        assert "additionalProperties" not in text


def test_the_required_input_is_shown_as_a_caller_would_write_it(client):
    """verification can build the call: the example names a real address."""
    for path in (CANONICAL_SELLER, ALIAS_SELLER):
        example = _info_for(client, path)["input"]["queryParams"]
        addr = example["receiver"]
        assert re.fullmatch(r"0x[0-9a-fA-F]{40}", addr), (
            f"{path}: example receiver is not an EVM address: {addr!r}")
        assert isinstance(example["days"], int)


# ── 3. the routes that really take nothing keep saying so ───────────────────

def test_routes_that_take_no_arguments_still_publish_an_empty_map(client):
    """The original guard's intent, now applied only where it is true."""
    import main
    checked = 0
    for path in sorted(main.X402_PAID_ENDPOINTS):
        if _handler_reads(path):
            continue
        assert _info_for(client, path)["input"]["queryParams"] == {}, (
            f"{path}: takes no arguments but declares a non-empty map")
        assert _schema_for(client, path)["properties"] == {}
        checked += 1
    assert checked >= 6, f"expected at least six argument-free routes, saw {checked}"


# ── 4. the alias cannot drift from the route it fronts ──────────────────────

def test_the_alias_declares_the_same_input_object_as_its_canonical(client):
    """By reference, for the same reason the output example is shared."""
    import main
    assert (main.X402_INPUT_QUERY_PARAMS[ALIAS_SELLER]
            is main.X402_INPUT_QUERY_PARAMS[CANONICAL_SELLER])
    assert (_info_for(client, ALIAS_SELLER)["input"]["queryParams"]
            == _info_for(client, CANONICAL_SELLER)["input"]["queryParams"])


def test_only_routes_that_read_arguments_have_a_declarations_entry():
    """The map is not a place to park hopeful metadata."""
    import main
    for path in main.X402_INPUT_QUERY_PARAMS:
        assert path in main.X402_PAID_ENDPOINTS, (
            f"{path} declares input but is not a paid route")
        assert _handler_reads(path), (
            f"{path} declares input but reads no request.args")


# ── 5. a request we cannot serve is never settled ───────────────────────────
# Measured on 11.11.2026 with our own money: a paid call to
# /api/v1/verify-seller without `?receiver=` settled $0.01 and THEN answered 400
# receiver_required. The declaration was already correct, so the defect was one
# of ordering — the paywall settled before asking whether the request could be
# answered at all. These tests pin the order, not just the status code.

def _credential():
    """Any non-empty payment credential: the guard fires on PRESENCE."""
    return {"PAYMENT-SIGNATURE": "present-but-never-verified"}


def test_a_payment_credential_without_the_required_parameter_settles_NOTHING(
        client, monkeypatch):
    """The money must not move. Asserted on the settle call, not on the reply."""
    import main
    settled = []

    def _never(path, price, ip):
        settled.append((path, price))
        return True

    monkeypatch.setattr(main, "_try_consume_standard_payment", _never)
    r = client.get(CANONICAL_SELLER, headers=_credential())
    assert r.status_code == 400, (
        f"expected a refusal, got {r.status_code} — a 402 would invite a second "
        "payment and a 200 would charge for nothing")
    body = r.get_json()
    assert body["error"] == "missing_required_parameter"
    assert body["missing"] == ["receiver"]
    assert body["payment_taken"] is False
    assert settled == [], (
        "the settle path ran for a request that cannot be answered: %r" % settled)


def test_the_same_guard_covers_the_alias(client, monkeypatch):
    """The alias is a paid route in every sense, so it cannot be the loose one."""
    import main
    settled = []
    monkeypatch.setattr(main, "_try_consume_standard_payment",
                        lambda *a: settled.append(a) or True)
    r = client.get(ALIAS_SELLER, headers=_credential())
    assert r.status_code == 400 and r.get_json()["missing"] == ["receiver"]
    assert settled == []


def test_the_refusal_hands_the_caller_the_call_it_should_have_made(client):
    """A refusal that does not say how to succeed is only half a refusal."""
    r = client.get(CANONICAL_SELLER, headers=_credential())
    body = r.get_json()
    assert body["call_it_like"].startswith("?receiver=0x")
    assert body["required"] == ["receiver"]
    assert body["free_sample"].endswith("/api/v1/verify-seller/sample")
    assert "nothing was settled" in body["message"].lower() or \
        "Nothing was settled" in body["message"]


def _stub_view(monkeypatch, path):
    """Replace a route's view with a stub, so a test about the PAYWALL does not
    also run the product.

    /api/v1/verify-seller reads Base mainnet per call; letting it run made this
    file hang for ten minutes, which is a slow test pretending to be a guard.
    """
    import main
    rule = next(r for r in main.app.url_map.iter_rules() if str(r) == path)
    monkeypatch.setitem(main.app.view_functions, rule.endpoint,
                        lambda **kw: ({"ok": True, "stub": path}, 200))


def test_a_credential_WITH_the_parameter_still_reaches_the_rail(client, monkeypatch):
    """The guard must not become a wall: the correct call still pays and passes."""
    import main
    seen = []

    def _ok(path, price, ip):
        seen.append((path, price))
        return True

    monkeypatch.setattr(main, "_try_consume_standard_payment", _ok)
    monkeypatch.setattr(main, "_get_dynamic_price", lambda ip, path: 0.01)
    _stub_view(monkeypatch, CANONICAL_SELLER)
    r = client.get(CANONICAL_SELLER + "?receiver=0x" + "a1" * 20,
                   headers=_credential())
    assert seen == [(CANONICAL_SELLER, 0.01)], (
        "the rail was not reached for a well-formed paid call: %r" % seen)
    assert r.status_code == 200, r.get_json()


def test_an_UNPAID_bare_path_still_publishes_the_402(client):
    """The catalogues read this challenge to index the route.

    Refusing the bare path outright would take /api/v1/verify-seller out of
    discovery in order to fix a billing edge, which is a worse trade.
    """
    for path in (CANONICAL_SELLER, ALIAS_SELLER):
        r = client.get(path)
        assert r.status_code == 402, (
            f"{path} answered {r.status_code} without a credential — an unpaid "
            "call must still be offered the challenge")
        assert r.get_json()["accepts"][0]["amount"]


def test_routes_without_required_parameters_are_untouched(client, monkeypatch):
    """The guard is driven by the declaration, so argument-free routes never see
    it: their paid calls still settle exactly as before."""
    import main
    seen = []
    monkeypatch.setattr(main, "_try_consume_standard_payment",
                        lambda path, price, ip: seen.append(path) or True)
    monkeypatch.setattr(main, "_get_dynamic_price", lambda ip, path: 0.003)
    for path in ("/api/v1/signal", "/api/stats"):
        _stub_view(monkeypatch, path)
        r = client.get(path, headers=_credential())
        assert r.status_code != 400, f"{path} was refused: {r.get_json()}"
    assert set(seen) == {"/api/v1/signal", "/api/stats"}, seen
