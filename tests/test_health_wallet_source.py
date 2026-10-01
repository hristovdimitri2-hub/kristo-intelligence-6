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
