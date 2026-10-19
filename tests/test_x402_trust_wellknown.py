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