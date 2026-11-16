"""`resource` must reach each facilitator in the shape that facilitator reads.

MEASURED, NOT ASSUMED (16.11.2026). Two settlements of the same route, an hour
apart, on the live PayAI catalogue:

  * requirements whose `resource` was the 402's OBJECT produced a catalogue row
    within 45 seconds (`/api/v1/signal`, lastUpdated=19:30:57Z, $0.01);
  * five client-driven settlements whose `resource` was the flat STRING
    produced NO rows at all, four minutes later — and the same was true of
    `/api/v1/whaleflow` until it was re-settled with the object, which listed it
    immediately (19:39:04Z).

The payload echo carried the object in BOTH cases, so the only variable was
`paymentRequirements.resource`. The spec declares that field a string URI and
CDP has settled against it for months, so the fix cannot simply swap the shape
for everyone: the server now sends both and `_requirements_for` picks one.
"""

import json
import sys
from pathlib import Path

import pytest

from services import connectors

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def client(monkeypatch):
    """The app's own test client, with the free tier cleared so a paid route
    answers a real 402."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999
    return main.app.test_client(), main


def _requirements():
    """What `main._x402_paywall` now builds for a challenge."""
    return {
        "scheme": "exact",
        "network": "eip155:8453",
        "payTo": "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844",
        "amount": "10000",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "resource": "https://kristo-intelligence-api.onrender.com/api/v1/signal",
        "resource_url": "https://kristo-intelligence-api.onrender.com/api/v1/signal",
        # Spec-legal PaymentRequirements fields, set by the server alongside.
        "description": "Trading signals",
        "mimeType": "application/json",
        "resource_object": {
            "url": "https://kristo-intelligence-api.onrender.com/api/v1/signal",
            "description": "Trading signals",
            "mimeType": "application/json",
        },
        # Server-internal: read by precheck_payment_payload to pin the EIP-712
        # domain, in no facilitator schema, and measured to stop the indexing.
        "extra_name": "USD Coin",
        "extra_version": "2",
    }


def test_cdp_gets_the_string_the_spec_declares():
    """CDP has settled against a string URI for months; it keeps getting one."""
    reqs = connectors._requirements_for("cdp", _requirements())
    assert reqs["resource"] == \
        "https://kristo-intelligence-api.onrender.com/api/v1/signal"
    assert not isinstance(reqs["resource"], dict)


def test_a_cataloguing_facilitator_gets_the_object():
    """PayAI indexes `resource.url`; handed the string it lists nothing."""
    reqs = connectors._requirements_for("payai", _requirements())
    assert isinstance(reqs["resource"], dict), reqs["resource"]
    assert reqs["resource"]["url"] == \
        "https://kristo-intelligence-api.onrender.com/api/v1/signal"


def test_the_helper_keys_never_reach_a_facilitator():
    """`resource_object`/`resource_url` are ours; neither is a spec field."""
    for name in ("cdp", "payai"):
        reqs = connectors._requirements_for(name, _requirements())
        assert "resource_object" not in reqs, name
        assert "resource_url" not in reqs, name


def test_the_internal_domain_keys_never_reach_a_facilitator():
    """`extra_name`/`extra_version` stopped the indexing DEAD.

    Measured, not reasoned: with them /api/stats was settled eight times over two
    rounds and never listed; without them, and with the spec-legal `description`
    and `mimeType` still in the body, it listed within 45 seconds. The cost was
    silent — the settlement still succeeded and the client still got a tx.

    The server still needs them for `precheck_payment_payload`, so they are
    stripped on the way OUT, not removed at the source.
    """
    for name in ("cdp", "payai"):
        reqs = connectors._requirements_for(name, _requirements())
        assert "extra_name" not in reqs, name
        assert "extra_version" not in reqs, name


def test_the_spec_legal_extras_are_kept():
    """`description` and `mimeType` ARE in the facilitator's schema — and the
    clean-form test that listed the route still carried them."""
    for name in ("cdp", "payai"):
        reqs = connectors._requirements_for(name, _requirements())
        assert reqs.get("description") == "Trading signals", name
        assert reqs.get("mimeType") == "application/json", name


def test_the_outbound_shape_logger_is_off_by_default_and_never_raises():
    """A diagnostic must not become telemetry, and must not break a settle.

    It exists because the remaining difference between the path that gets a
    route listed and the path that does not could not be found by reading the
    code — only by comparing what actually leaves. Off unless
    `X402_LOG_OUTBOUND=1`.
    """
    assert connectors._OUTBOUND_SHAPE is False, (
        "the outbound shape log must be opt-in")
    # Malformed bodies must be swallowed, not raised into the settlement path.
    for bad in ({}, {"paymentRequirements": None},
                {"paymentRequirements": {"resource": 5},
                 "paymentPayload": {"accepted": "not-a-dict"}}):
        connectors._log_outbound_shape("payai", bad)  # must not raise


def test_the_signed_terms_are_untouched_by_the_swap():
    """Only `resource` may move — amount/payTo/asset are what the buyer signed."""
    base = _requirements()
    for name in ("cdp", "payai"):
        reqs = connectors._requirements_for(name, base)
        for field in ("scheme", "network", "payTo", "amount", "asset"):
            assert reqs[field] == base[field], (name, field)


def test_a_caller_that_sends_only_the_string_is_not_broken():
    """Older callers (and the probe path) pass no `resource_object`."""
    bare = {"scheme": "exact", "payTo": "0x" + "11" * 20,
            "resource": "https://example.test/x"}
    for name in ("cdp", "payai"):
        reqs = connectors._requirements_for(name, bare)
        assert reqs["resource"] == "https://example.test/x", name


def test_the_live_402_publishes_the_object_the_indexer_needs(client):
    """The server's own challenge must carry `resource.url`, or the fix has no
    source to build the object from.

    Driven through the client because `_x402_challenge_core` reads `request`.
    """
    test_client, main = client
    resp = test_client.get("/api/v1/signal")
    assert resp.status_code == 402, resp.status_code
    resource = resp.get_json().get("resource")
    assert isinstance(resource, dict), resource
    assert isinstance(resource.get("url"), str)
    # The host comes from the request, so this is localhost under test and the
    # real origin in production — what matters is that it is an absolute URL.
    assert resource["url"].startswith("http"), resource["url"]
    assert resource["url"].endswith("/api/v1/signal"), resource["url"]
    # And it survives a JSON round trip, which is how it reaches a client.
    assert json.loads(json.dumps(resource))["url"] == resource["url"]
