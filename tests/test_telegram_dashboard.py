import pytest


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-webhook-secret")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    from integrations.crm_store import CRMStore, LeadRecord

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    main._live_request_log.clear()
    main._telegram_active_chats.clear()
    main._bot_status.update(
        {
            "active_users": 0,
            "commands_processed": 0,
            "messages_sent": 0,
            "vip_invites_sent": 0,
        }
    )

    lead = LeadRecord(
        email="vip@example.com",
        source="test",
        campaign="dashboard",
        plan="Pro",
        telegram_chat_id="123456",
    )
    main.crm_store.add_lead(lead)
    main.crm_store.mark_paid("vip@example.com", 79.0, "Pro")
    return main, main.app.test_client()


def test_start_returns_fallback_when_market_service_fails(monkeypatch):
    import services.telegram_sales as telegram_sales

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(
        telegram_sales,
        "get_market_snapshot",
        lambda: (_ for _ in ()).throw(RuntimeError("rate limited")),
    )
    sent = []

    def fake_api_call(method, token, payload, timeout=15):
        sent.append((method, payload))
        return {"message_id": 42} if method == "sendMessage" else True

    monkeypatch.setattr(telegram_sales, "_api_call", fake_api_call)

    result = telegram_sales.process_webhook_update(
        {"message": {"chat": {"id": 99}, "text": "/start"}}
    )

    assert result["handled"] is True
    assert result["degraded"] is True
    assert result["response_sent"] is True
    assert any("временно не са налични" in payload["text"] for method, payload in sent if method == "sendMessage")


def test_unknown_callback_always_receives_text_reply(monkeypatch):
    import services.telegram_sales as telegram_sales

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_api_call(method, token, payload, timeout=15):
        sent.append((method, payload))
        return {"message_id": 43} if method == "sendMessage" else True

    monkeypatch.setattr(telegram_sales, "_api_call", fake_api_call)

    result = telegram_sales.process_webhook_update(
        {
            "callback_query": {
                "id": "callback-1",
                "data": "expired_button",
                "message": {"chat": {"id": 99}, "message_id": 123},
            }
        }
    )

    assert result["response_sent"] is True
    assert any("вече не е активен" in payload["text"] for method, payload in sent if method == "sendMessage")


def test_gas_callback_returns_a_useful_text_reply(monkeypatch):
    import services.telegram_sales as telegram_sales

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    sent = []

    def fake_api_call(method, token, payload, timeout=15):
        sent.append((method, payload))
        return {"message_id": 44} if method == "sendMessage" else True

    monkeypatch.setattr(telegram_sales, "_api_call", fake_api_call)

    result = telegram_sales.process_webhook_update(
        {
            "callback_query": {
                "id": "callback-gas",
                "data": "gas",
                "message": {"chat": {"id": 99}, "message_id": 124},
            }
        }
    )

    assert result["response_sent"] is True
    assert any("Base Gas мониторинг" in payload["text"] for method, payload in sent if method == "sendMessage")


def test_admin_overview_is_protected_and_redacts_chat_ids(app_client):
    main, client = app_client

    assert client.get("/api/admin/overview").status_code == 401
    client.get("/health")
    response = client.get(
        "/api/admin/overview",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["metrics"]["paid_payments"] == 1
    assert payload["metrics"]["active_vip_plans"] == 1
    assert payload["vip_plans"][0]["telegram_linked"] is True
    assert payload["payments"][0]["email"] == "v***@example.com"
    assert payload["vip_plans"][0]["email"] == "v***@example.com"
    assert payload["launch_gates"]["catalog"]["published"] is False
    assert payload["launch_gates"]["broad_launch"]["status"] == "blocked"
    persistence = payload["launch_gates"]["persistence"]
    assert {
        "catalog_healthy",
        "audit_healthy",
        "stripe_vip_healthy",
        "settlement_schema_healthy",
        "schema_verified",
    } <= set(persistence)
    assert "telegram_chat_id" not in response.get_data(as_text=True)
    assert "vip@example.com" not in response.get_data(as_text=True)
    assert any(row["path"] == "/health" for row in payload["request_log"])
    assert payload["services"]["crm"]["ready"] is True


def test_admin_overview_includes_coingecko_cache_freshness(app_client, monkeypatch):
    main, client = app_client
    monkeypatch.setattr(
        main,
        "get_coingecko_cache_status",
        lambda: {
            "state": "stale",
            "age_seconds": 120,
            "last_success_at": "2026-08-20T10:00:00+00:00",
            "detail": "rate-limit cooldown",
        },
    )

    response = client.get(
        "/api/admin/overview",
        headers={"X-Admin-Token": "test-admin-token"},
    )

    assert response.status_code == 200
    coingecko = response.get_json()["services"]["coingecko"]
    assert coingecko["ready"] is False
    assert coingecko["state"] == "stale"
    assert coingecko["age_seconds"] == 120
    assert "rate-limit cooldown" in coingecko["detail"]


def test_admin_dashboard_login_creates_browser_session(app_client):
    _, client = app_client

    login = client.post(
        "/sales/admin/login",
        data={"admin_token": "test-admin-token"},
        follow_redirects=True,
    )

    assert login.status_code == 200
    assert "Оперативен dashboard" in login.get_data(as_text=True)
    assert "v6 launch gates" in login.get_data(as_text=True)
    overview = client.get("/api/admin/overview")
    assert overview.status_code == 200


def test_admin_session_cookie_is_secure(app_client):
    _, client = app_client

    response = client.post(
        "/sales/admin/login",
        data={"admin_token": "test-admin-token"},
    )

    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=Lax" in cookie


def test_telegram_webhook_requires_secret_and_tracks_authorized_update(app_client, monkeypatch):
    main, client = app_client
    monkeypatch.setattr(
        main,
        "process_webhook_update",
        lambda payload: {"handled": True, "type": "command", "response_sent": True},
    )
    payload = {"message": {"chat": {"id": 99}, "text": "/start"}}

    assert client.post("/api/telegram-webhook", json=payload).status_code == 401
    accepted = client.post(
        "/api/telegram-webhook",
        json=payload,
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-webhook-secret"},
    )

    assert accepted.status_code == 200
    assert main._bot_status["active_users"] == 1
    assert main._bot_status["commands_processed"] == 1


def test_stripe_payment_listing_reads_past_unpaid_page(monkeypatch):
    from integrations.stripe_checkout import StripeCheckoutService

    class Session:
        def __init__(self, session_id, payment_status):
            self.id = session_id
            self.payment_status = payment_status
            self.metadata = {"plan": "pro"}
            self.customer_details = type("Customer", (), {"email": "buyer@example.com"})()
            self.amount_total = 7900
            self.currency = "usd"
            self.created = 123

    class Page:
        def __init__(self, data, has_more):
            self.data = data
            self.has_more = has_more

    class CheckoutSessions:
        calls = []

        @classmethod
        def list(cls, **kwargs):
            cls.calls.append(kwargs)
            if "starting_after" not in kwargs:
                return Page([Session("open-session", "unpaid")], True)
            return Page([Session("paid-session", "paid")], False)

    service = StripeCheckoutService()
    service.enabled = True
    service._stripe = type(
        "Stripe",
        (),
        {"checkout": type("Checkout", (), {"Session": CheckoutSessions})()},
    )()

    listing = service.list_recent_completed_payments(limit=1)

    assert listing["available"] is True
    assert listing["payments"][0]["checkout_id"] == "paid-session"
    assert len(CheckoutSessions.calls) == 2