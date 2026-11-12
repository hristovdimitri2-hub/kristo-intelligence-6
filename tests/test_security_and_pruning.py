"""Security headers and the per-IP usage-map pruning.

Two independent audit findings, both fixed here:

  1. "No security headers" — no CSP, X-Frame-Options, HSTS or nosniff, so
     the login page and the dashboard could be framed by a foreign site.
  2. "`_free_tier_usage` and `_paid_calls_usage` grow with every new IP and
     are never cleaned" — a long-lived process leaks them.

These are unit tests: they do not call the network or the live service.
"""
import pytest

import main


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    from integrations.crm_store import CRMStore

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    main._free_tier_usage.clear()
    return main.app.test_client()


def test_security_headers_are_set_on_every_response(client):
    """Every response carries the framing, sniffing and downgrade headers."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "max-age=31536000" in r.headers.get("Strict-Transport-Security", "")
    assert "frame-ancestors 'none'" in r.headers.get("Content-Security-Policy", "")
    assert "base-uri 'self'" in r.headers.get("Content-Security-Policy", "")


def test_security_headers_do_not_override_a_route_choice(client):
    """A route that set its own header keeps it — setdefault, not set."""
    # /api/stats is a 402 in strict mode; its own CORS header is set by the
    # 402 hook. The security hook must not clobber it.
    r = client.get("/api/stats")
    assert r.status_code == 402
    assert r.headers.get("Access-Control-Allow-Origin") == "*"
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_prune_usage_maps_keeps_the_newest_entries(monkeypatch):
    """The map is capped at _USAGE_MAP_MAX and the oldest entries go first."""
    monkeypatch.setattr(main, "_USAGE_MAP_MAX", 5)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    for i in range(10):
        main._free_tier_usage["ip-%d" % i] = 1
        main._paid_calls_usage["ip-%d" % i] = 1

    main._prune_usage_maps()

    assert len(main._free_tier_usage) == 5
    assert len(main._paid_calls_usage) == 5
    # The newest five survived; the oldest five are gone.
    assert set(main._free_tier_usage) == {"ip-%d" % i for i in range(5, 10)}
    assert set(main._paid_calls_usage) == {"ip-%d" % i for i in range(5, 10)}


def test_prune_usage_maps_is_a_no_op_under_the_cap(monkeypatch):
    """Nothing is dropped while the map is within the cap."""
    monkeypatch.setattr(main, "_USAGE_MAP_MAX", 100)
    monkeypatch.setattr(main, "_free_tier_usage", {"a": 1, "b": 2})
    monkeypatch.setattr(main, "_paid_calls_usage", {"c": 3})

    main._prune_usage_maps()

    assert main._free_tier_usage == {"a": 1, "b": 2}
    assert main._paid_calls_usage == {"c": 3}
