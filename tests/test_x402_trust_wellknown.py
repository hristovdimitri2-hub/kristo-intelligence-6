# -*- coding: utf-8 -*-
"""GET /.well-known/x402-trust.txt — x402 Trust provider claim domain proof.

Форматът (x402-trust.com/verify): един ред x402-trust-verification=v1:<key>,
text/plain, публичен (без auth, без 402 paywall — включително при изчерпан
free tier).
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    yield main.app.test_client()
    main._free_tier_usage.clear()


def test_wellknown_is_public_plain_text_with_the_line(client):
    r = client.get("/.well-known/x402-trust.txt")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
    body = r.get_data(as_text=True)
    assert body.startswith("x402-trust-verification=v1:"), body[:60]
    key = body.split("v1:", 1)[1].strip()
    assert len(key) >= 80, "public key too short"
    assert "\n" not in key, "key must stay on the single verification line"


def test_wellknown_stays_free_with_exhausted_tier(client):
    """The proof file must never be paywalled — Trust re-checks it regularly."""
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = client.get("/.well-known/x402-trust.txt")
        assert r.status_code == 200
        assert r.get_data(as_text=True).startswith(
            "x402-trust-verification=v1:")
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)


# ── Agent Economy Report's domain-control proof ─────────────────────────────

def test_agenteconomy_proof_is_one_plain_text_line(client):
    """Their check reads the file as plain text and compares the token.

    Domain control is the path they document for a payTo wallet that cannot
    sign — ours lives only on Render, deliberately — and it gives the same owner
    block and badges a wallet-signed claim does.
    """
    r = client.get("/.well-known/agenteconomy-verify.txt")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
    body = r.get_data(as_text=True)
    assert body.startswith("aer-"), body[:40]
    assert body.count("\n") == 1 and body.endswith("\n"), (
        "the file must be ONE line; their checker reads the token as the whole "
        "body. Got %r" % body)


def test_agenteconomy_proof_stays_free_with_exhausted_tier(client):
    """The file is re-checked daily and the claim lapses after 3 misses, so it
    must not depend on the crawler being under a free tier."""
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = client.get("/.well-known/agenteconomy-verify.txt")
        assert r.status_code == 200
        assert r.get_data(as_text=True).startswith("aer-")
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)