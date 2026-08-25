import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    return main.app.test_client()


def test_health_endpoint(client, monkeypatch):
    # Simulate a healthy monitor-only wallet so the test is deterministic
    # and does not depend on live Base RPC connectivity.
    import main

    healthy_wallet_state = {
        "wallet_address": main.X402_RECEIVER_ADDRESS,
        "fee_receiver": main.X402_RECEIVER_ADDRESS,
        "usdc_balance": 0.0,
        "rpc_connected": True,
        "chain_id": 8453,
        "network": "Base Mainnet",
        "receiver_valid": True,
        "rpc_error": None,
        "last_block_checked": 0,
        "last_check_time": None,
    }
    monkeypatch.setattr(main, "_wallet_state", healthy_wallet_state)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"] == {"backend": "sqlite", "ready": True}
    assert payload["blockchain"]["network"] == "Base Mainnet"
    assert payload["blockchain"]["chain_id"] == 8453
    assert payload["blockchain"]["ready"] is True


def test_health_endpoint_returns_200_when_blockchain_rpc_is_flaky(client, monkeypatch):
    """Regression test (2026-08-24 deploy failure): platform health checks
    must not fail when the public Base RPC is rate-limited (429). The service
    itself is up — only the blockchain monitor is degraded."""
    import main

    degraded_wallet_state = {
        "wallet_address": None,
        "fee_receiver": None,
        "usdc_balance": 0.0,
        "rpc_connected": False,
        "chain_id": None,
        "network": "Base Mainnet",
        "receiver_valid": False,
        "rpc_error": "429 Too Many Requests",
        "last_block_checked": 0,
        "last_check_time": None,
    }
    monkeypatch.setattr(main, "_wallet_state", degraded_wallet_state)

    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["service"] == "up"
    assert payload["status"] == "degraded"
    assert payload["database"]["ready"] is True
    assert payload["blockchain"]["ready"] is False


def test_sentinel_module_configuration_gates():
    """The embedded Sentinel agent must stay silent unless fully configured
    (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID), and must honor SENTINEL_ENABLED=false."""
    from services import sentinel

    # Without chat id → disabled
    monkeypatch_del = pytest.MonkeyPatch()
    monkeypatch_del.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert sentinel.sentinel_enabled() is False
    monkeypatch_del.undo()

    # With both → enabled
    mp = pytest.MonkeyPatch()
    mp.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    mp.setenv("TELEGRAM_CHAT_ID", "456")
    assert sentinel.sentinel_enabled() is True

    # Explicit kill-switch wins
    mp.setenv("SENTINEL_ENABLED", "false")
    assert sentinel.sentinel_enabled() is False
    mp.undo()


def test_sentinel_health_alert_only_on_change(monkeypatch):
    """Alerts fire on transitions only; steady states must stay silent."""
    from services import sentinel

    sent: list[str] = []
    monkeypatch.setattr(sentinel, "_tg_send", lambda text: sent.append(text) or True)

    def fake_get(url, timeout=30):
        class R:
            status_code = 200
            def json(self):
                return {"status": "ok", "blockchain": {"ready": True}}
        return R()

    monkeypatch.setattr(sentinel.requests, "get", fake_get)

    state = {"health": None}
    sentinel._check_health(state)          # baseline — no alert
    assert sent == []
    sentinel._check_health(state)          # still ok — no alert
    assert sent == []

    state["health"] = "down"               # simulate previous down state
    sentinel._check_health(state)          # down -> ok transition → alert
    assert len(sent) == 1
    assert "🟢" in sent[0]


def test_sentinel_revenue_alert_on_payment(monkeypatch):
    """A balance increase must produce exactly one payment alert."""
    from services import sentinel

    sent: list[str] = []
    monkeypatch.setattr(sentinel, "_tg_send", lambda text: sent.append(text) or True)

    balances = iter(["0", "50000"])  # 0.00 → 0.05 USDC (6 decimals)
    monkeypatch.setattr(
        sentinel.requests, "post",
        lambda url, json=None, timeout=30: type("R", (), {
            "json": lambda self: {"result": hex(int(next(balances)))}
        })(),
    )

    state = {"usdc_balance": 0.0}
    sentinel._check_revenue(state)
    assert sent == []                      # baseline
    sentinel._check_revenue(state)
    assert len(sent) == 1
    assert "💰" in sent[0]
    assert state["usdc_balance"] == 0.05


def test_public_dashboard_stats_are_free_and_use_official_catalog(client):
    response = client.get("/api/dashboard-stats")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["products_summary"]["total_products"] == 8
    assert len(payload["products"]) == 8
    assert "recent_requests" not in payload
    assert all(0.01 <= product["price_usdc"] <= 0.25 for product in payload["products"])
    assert payload["total_volume_usd"] == 0.0
    assert payload["total_sales"] == 0
    assert "telegram_bot_running" in payload


def test_lead_capture_and_checkout(client):
    lead = client.post(
        "/api/leads",
        json={
            "email": "integration@example.com",
            "source": "test",
            "campaign": "integration",
        },
    )
    assert lead.status_code == 200
    assert lead.get_json()["ok"] is True

    checkout = client.post(
        "/api/checkout",
        json={"email": "integration@example.com", "plan": "pro"},
    )
    assert checkout.status_code == 200
    payload = checkout.get_json()
    assert payload["ok"] is True
    assert payload["plan"] == "Pro"
    assert payload["payment_session"]["provider"] in {"mock", "mock_fallback", "stripe"}