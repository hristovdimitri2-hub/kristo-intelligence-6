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
