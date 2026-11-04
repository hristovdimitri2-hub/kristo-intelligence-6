"""RED→GREEN: /health must read `_wallet_state` from the STARTUP module.

Prod runs `python main.py`, so the initialized state lives in `__main__`.
The lazy `import main` copy (whose threads the env guard skips) keeps the
defaults — reading it reports a false "degraded" with null chain_id /
fee_receiver (discovery.py:44). One test, two directions:

  A) `__main__` ready + `main` defaults  → /health = ok
  B) `__main__` defaults                 → /health = degraded
"""

import sys
import types

import pytest

# Mirrors main.py:361-373 — the untouched defaults of `_wallet_STATE`.
_DEFAULTS = {
    "wallet_address": None,
    "fee_receiver": None,
    "usdc_balance": 0.0,
    "receiver_usdc_balance": 0.0,
    "rpc_connected": False,
    "chain_id": None,
    "network": "Base Mainnet",
    "receiver_valid": False,
    "rpc_error": None,
    "last_block_checked": 0,
    "last_check_time": None,
}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(
        main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)
    return main.app.test_client(), main


def _startup_module(main_mod, wallet_state):
    """Stub of `sys.modules["__main__"]` the way `python main.py` builds it."""
    stub = types.ModuleType("__main__")
    stub.__file__ = "C:/app/main.py"  # basename == "main.py"
    stub._wallet_state = wallet_state
    stub._lock = main_mod._lock
    stub.crm_store = main_mod.crm_store
    return stub


def test_health_reads_starting_module_wallet_state(client, monkeypatch):
    flask_client, main_mod = client
    import config

    ready = dict(
        _DEFAULTS,
        rpc_connected=True,
        chain_id=config.BASE_CHAIN_ID,
        receiver_valid=True,
        fee_receiver=main_mod.X402_RECEIVER_ADDRESS,
    )

    # A) startup module READY while the guarded `main` copy is at defaults
    monkeypatch.setattr(main_mod, "_wallet_state", dict(_DEFAULTS))
    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, ready))
    body = flask_client.get("/health").get_json()
    assert body["status"] == "ok", body
    assert body["blockchain"]["ready"] is True
    assert body["blockchain"]["chain_id"] == config.BASE_CHAIN_ID
    assert body["blockchain"]["fee_receiver"] == main_mod.X402_RECEIVER_ADDRESS

    # B) startup module itself at defaults → degraded (today's live case)
    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, dict(_DEFAULTS)))
    body = flask_client.get("/health").get_json()
    assert body["status"] == "degraded", body
    assert body["blockchain"]["ready"] is False
    assert body["blockchain"]["chain_id"] is None
    assert body["blockchain"]["fee_receiver"] is None


def test_health_publishes_how_far_the_payment_monitor_has_scanned(client,
                                                                 monkeypatch):
    """The monitor's progress must be visible without paying for /api/stats.

    It lived only in the paid wallet block, so there was no way - from outside or
    from here - to tell whether the thing that detects incoming payments was
    keeping up or had silently stopped. F-39 made that worse: the monitor started
    at the chain head on every restart, and nothing showed it.
    """
    flask_client, main_mod = client
    import config

    ready = dict(
        _DEFAULTS,
        rpc_connected=True,
        chain_id=config.BASE_CHAIN_ID,
        receiver_valid=True,
        fee_receiver=main_mod.X402_RECEIVER_ADDRESS,
        last_block_checked=53_499_123,
        last_check_time="2026-11-04T10:20:30+00:00",
    )
    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, ready))

    monitor = flask_client.get("/health").get_json()["blockchain"]["monitor"]
    assert monitor["last_block_checked"] == 53_499_123, (
        "the health check reports %r, not the monitor's real position"
        % monitor.get("last_block_checked"))
    assert monitor["last_check_time"] == "2026-11-04T10:20:30+00:00"


def test_health_is_free_so_the_monitor_signal_needs_no_payment(client):
    """A liveness signal behind a paywall is not a liveness signal."""
    flask_client, main_mod = client

    assert "/health" in main_mod.X402_FREE_ENDPOINTS
    assert "/ready" in main_mod.X402_FREE_ENDPOINTS
    assert flask_client.get("/health").status_code == 200


# ── F-10: liveness and readiness are different questions ──────────────────────


class _DeadStore:
    """A store whose database cannot be reached, or even asked about."""

    backend = "postgres"

    def __init__(self, raises=False):
        self._raises = raises

    def is_healthy(self):
        if self._raises:
            raise RuntimeError("database is unreachable")
        return False


@pytest.mark.parametrize("raises", [False, True],
                         ids=["answers-not-ready", "raises-on-asking"])
def test_health_stays_200_when_the_database_is_unreachable(client, monkeypatch,
                                                           raises):
    """F-10: a restart cannot repair a database.

    /health used to answer 503 when the store was unhealthy, which is what the
    platform acts on, so a database blip restarted the only worker into a cold start
    that could not answer /health either. Measured with the store unreachable, /health
    was the only endpoint of eighteen that changed - /validation, /llms.txt,
    /mcp.json, /sitemap.xml, /robots.txt, /agents.json, /openapi.json and /mcp all
    still answered 200, because none of them needs a database. The surface that has
    to stay up for anyone to find us was being taken down for nothing.
    """
    flask_client, main_mod = client
    monkeypatch.setattr(main_mod, "crm_store", _DeadStore(raises=raises))

    response = flask_client.get("/health")

    assert response.status_code == 200, (
        "/health answered %s with the database down; nothing a restart can fix, and "
        "the free discovery surface does not need a database"
        % response.status_code)
    body = response.get_json()
    assert body["service"] == "up"


@pytest.mark.parametrize("raises", [False, True],
                         ids=["answers-not-ready", "raises-on-asking"])
def test_health_still_reports_the_truth_so_the_sentinel_can_alert(client,
                                                                  monkeypatch,
                                                                  raises):
    """Liveness must not become silence.

    sentinel.py reads `status` out of the body at 200 and sends a Telegram alert when
    it changes, so keeping the code at 200 is only safe while the body goes on saying
    "degraded". This is the half that must not regress.
    """
    flask_client, main_mod = client
    monkeypatch.setattr(main_mod, "crm_store", _DeadStore(raises=raises))

    body = flask_client.get("/health").get_json()

    assert body["status"] == "degraded", (
        "the body says %r while the database is down, so the sentinel would never "
        "alert" % body["status"])
    assert body["database"]["ready"] is False


@pytest.mark.parametrize("raises", [False, True],
                         ids=["answers-not-ready", "raises-on-asking"])
def test_ready_is_where_the_503_belongs(client, monkeypatch, raises):
    """The honest half: readiness is genuinely false when a dependency is down."""
    flask_client, main_mod = client
    monkeypatch.setattr(main_mod, "crm_store", _DeadStore(raises=raises))

    response = flask_client.get("/ready")

    assert response.status_code == 503, (
        "/ready answered %s with the database down" % response.status_code)
    body = response.get_json()
    assert body["ready"] is False
    assert body["status"] == "not_ready"


def test_ready_is_200_only_when_both_dependencies_are_usable(client, monkeypatch):
    """Readiness is the conjunction, and each half is genuinely required."""
    flask_client, main_mod = client
    import config

    ready_wallet = dict(
        _DEFAULTS,
        rpc_connected=True,
        chain_id=config.BASE_CHAIN_ID,
        receiver_valid=True,
        fee_receiver=main_mod.X402_RECEIVER_ADDRESS,
    )

    # a healthy store that reports readiness, so the store is not the blocker
    class _LiveStore:
        backend = "sqlite"

        def is_healthy(self):
            return True

    monkeypatch.setattr(main_mod, "crm_store", _LiveStore())

    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, ready_wallet))
    assert flask_client.get("/ready").status_code == 200

    monkeypatch.setitem(
        sys.modules, "__main__", _startup_module(main_mod, dict(_DEFAULTS)))
    assert flask_client.get("/ready").status_code == 503, (
        "readiness must not be granted while the chain connection is unusable")


def test_the_readiness_route_is_not_a_restart_trigger(client):
    """The docstring warns against pointing a restarter here; keep the warning true.

    /health is the route a platform health check may act on and it is liveness only.
    If someone repointed the restarter at /ready, a database blip would restart an
    otherwise healthy worker - F-10 under a new name. The two must stay distinct.
    """
    flask_client, main_mod = client
    import inspect

    from app.blueprints import discovery

    health_source = inspect.getsource(discovery.health)
    ready_source = inspect.getsource(discovery.ready)

    assert "F-10" in health_source, (
        "/health no longer records why it must stay liveness-only")
    assert "/ready" in health_source
    assert "Do NOT point the platform health check at this route" in ready_source
