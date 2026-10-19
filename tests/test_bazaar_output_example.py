# -*- coding: utf-8 -*-
"""Bazaar info.output.example — 402-ът на трите рута носи реалистичен пример.

CDP validator finding (18.10): bazaar.info.output was missing — "recommended
for discovery quality, not required for indexing" (get-discovered docs:
complete output schemas with realistic examples raise metadata quality).
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    # Exhaust free tier → every paid route answers 402 (the challenge body).
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def test_whaleflow_402_carries_bazaar_output_example(client):
    r = client.get("/api/v1/whaleflow")
    assert r.status_code == 402
    info = r.get_json()["extensions"]["bazaar"]["info"]
    assert info["input"] == {"type": "http", "method": "GET"}
    example = info.get("output", {}).get("example")
    assert isinstance(example, dict) and example, "info.output.example missing"
    for key in ("state", "whales", "threshold_usdc", "source"):
        assert key in example, key


def test_signal_402_carries_bazaar_output_example(client):
    r = client.get("/api/v1/signal")
    assert r.status_code == 402
    info = r.get_json()["extensions"]["bazaar"]["info"]
    example = info.get("output", {}).get("example")
    assert isinstance(example, dict) and example
    for key in ("generated_at", "signals"):
        assert key in example, key


def test_stats_402_carries_bazaar_output_example(client):
    r = client.get("/api/stats")
    assert r.status_code == 402
    info = r.get_json()["extensions"]["bazaar"]["info"]
    example = info.get("output", {}).get("example")
    assert isinstance(example, dict) and example
    for key in ("today", "requests_today", "top_paths"):
        assert key in example, key


def test_unknown_route_keeps_info_without_output(client):
    """Routes outside the map keep the previous shape (no output key)."""
    r = client.get("/api/arb/opportunities")
    assert r.status_code == 402
    info = r.get_json()["extensions"]["bazaar"]["info"]
    assert info["input"] == {"type": "http", "method": "GET"}
    assert "output" not in info