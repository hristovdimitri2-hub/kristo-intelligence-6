import json
from datetime import datetime, timedelta, timezone

import pytest

import main
from integrations.crm_store import CRMStore, LeadRecord
from integrations.stripe_vip_store import StripeVIPStore


class VerifiedStripeEvent:
    def __init__(self, payload):
        self.payload = payload

    def verify_webhook(self, _body, _signature):
        return self.payload


class RecordingTelegramFlow:
    def __init__(self):
        self.calls = []

    def create_vip_invite(self, checkout_id):
        self.calls.append(("create", checkout_id))
        return {
            "status": "invite_created",
            "invite_link": "https://t.me/+vip-once",
            "invite_expires_at": (
                datetime.now(timezone.utc) + timedelta(hours=24)
            ).isoformat(),
        }

    def send_vip_invite(self, chat_id, plan_name, invite_link):
        self.calls.append(("send", chat_id, plan_name, invite_link))
        return {"status": "invite_sent"}

    def send_message(self, _chat_id, _text):
        return {"status": "message_sent"}


class FailingOnceTelegramFlow(RecordingTelegramFlow):
    def __init__(self):
        super().__init__()
        self.fail_next_delivery = True

    def send_vip_invite(self, chat_id, plan_name, invite_link):
        self.calls.append(("send", chat_id, plan_name, invite_link))
        if self.fail_next_delivery:
            self.fail_next_delivery = False
            return {"status": "invite_delivery_failed"}
        return {"status": "invite_sent"}


class CreatedCheckout:
    def create_checkout_session(self, *_args, **_kwargs):
        return {
            "status": "checkout_created",
            "provider": "stripe",
            "checkout_id": "cs_created_123",
            "url": "https://checkout.stripe.test/cs_created_123",
        }


def _checkout_completed(email, checkout_id="cs_verified_123"):
    return {
        "id": "evt_verified_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": checkout_id,
                "customer_email": email,
                "metadata": {"plan": "pro"},
                "amount_total": 7900,
                "currency": "usd",
                "payment_status": "paid",
            }
        },
    }


@pytest.mark.parametrize(
    "event_type",
    ["checkout.session.completed", "checkout.session.async_payment_succeeded"],
)
def test_valid_checkout_event_marks_paid_and_grants_vip_once(
    monkeypatch, tmp_path, event_type
):
    email = "vip-buyer@example.com"
    store = CRMStore(tmp_path / "crm.db")
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    store.add_lead(
        LeadRecord(
            email=email,
            source="test",
            campaign="stripe",
            plan="Pro",
        )
    )
    vip_store.register_checkout(
        checkout_id="cs_verified_123",
        customer_email=email,
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="verified-link-token",
    )
    vip_store.link_telegram_account("verified-link-token", "778899")
    telegram_flow = RecordingTelegramFlow()
    event = _checkout_completed(email)
    event["type"] = event_type

    monkeypatch.setattr(main, "crm_store", store)
    monkeypatch.setattr(main, "stripe_vip_store", vip_store)
    monkeypatch.setattr(main, "stripe_checkout", VerifiedStripeEvent(event))
    monkeypatch.setattr(main, "telegram_flow", telegram_flow)
    client = main.app.test_client()

    first = client.post(
        "/api/webhooks/stripe",
        data=json.dumps(event),
        content_type="application/json",
        headers={"Stripe-Signature": "verified"},
    )
    second = client.post(
        "/api/webhooks/stripe",
        data=json.dumps(event),
        content_type="application/json",
        headers={"Stripe-Signature": "verified"},
    )

    assert first.status_code == 200
    assert first.get_json()["status"] == "paid"
    assert first.get_json()["vip_access"] == "invite_sent"
    assert second.status_code == 200
    assert second.get_json()["status"] == "duplicate_webhook_event"
    assert store.find_by_email(email)["payment_status"] == "paid"
    assert telegram_flow.calls == [
        ("create", "cs_verified_123"),
        ("send", "778899", "Pro", "https://t.me/+vip-once"),
    ]


def test_unknown_signed_checkout_event_does_not_create_access(monkeypatch, tmp_path):
    store = CRMStore(tmp_path / "crm.db")
    telegram_flow = RecordingTelegramFlow()
    event = _checkout_completed("unknown@example.com")

    monkeypatch.setattr(main, "crm_store", store)
    monkeypatch.setattr(main, "stripe_checkout", VerifiedStripeEvent(event))
    monkeypatch.setattr(main, "telegram_flow", telegram_flow)

    response = main.app.test_client().post(
        "/api/webhooks/stripe",
        data=json.dumps(event),
        content_type="application/json",
        headers={"Stripe-Signature": "verified"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ignored_unknown_lead"
    assert telegram_flow.calls == []


def test_known_lead_cannot_activate_vip_without_server_bound_checkout(monkeypatch, tmp_path):
    email = "known-but-unbound@example.com"
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(LeadRecord(email=email, source="test", campaign="stripe", plan="Pro"))
    event = _checkout_completed(email)

    monkeypatch.setattr(main, "crm_store", store)
    monkeypatch.setattr(main, "stripe_vip_store", StripeVIPStore(tmp_path / "vip.db"))
    monkeypatch.setattr(main, "stripe_checkout", VerifiedStripeEvent(event))
    telegram_flow = RecordingTelegramFlow()
    monkeypatch.setattr(main, "telegram_flow", telegram_flow)

    response = main.app.test_client().post(
        "/api/webhooks/stripe",
        data=json.dumps(event),
        content_type="application/json",
        headers={"Stripe-Signature": "verified"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ignored_unmatched_standard_checkout"
    assert store.find_by_email(email)["payment_status"] == "pending"
    assert telegram_flow.calls == []


def test_paid_checkout_waits_for_bot_verified_telegram_link(monkeypatch, tmp_path):
    email = "link-required@example.com"
    store = CRMStore(tmp_path / "crm.db")
    store.add_lead(LeadRecord(email=email, source="test", campaign="stripe", plan="Pro"))
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_verified_123",
        customer_email=email,
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="link-before-delivery",
    )
    event = _checkout_completed(email)
    event["id"] = "evt_waiting_for_link"
    telegram_flow = RecordingTelegramFlow()

    monkeypatch.setattr(main, "crm_store", store)
    monkeypatch.setattr(main, "stripe_vip_store", vip_store)
    monkeypatch.setattr(main, "stripe_checkout", VerifiedStripeEvent(event))
    monkeypatch.setattr(main, "telegram_flow", telegram_flow)

    response = main.app.test_client().post(
        "/api/webhooks/stripe",
        data=json.dumps(event),
        content_type="application/json",
        headers={"Stripe-Signature": "verified"},
    )

    assert response.status_code == 200
    assert response.get_json()["vip_access"] == "pending_telegram_link"
    assert vip_store.get_delivery("cs_verified_123")["status"] == "pending_link"
    assert telegram_flow.calls == []


def test_public_checkout_ignores_unverified_telegram_chat_id(monkeypatch, tmp_path):
    crm = CRMStore(tmp_path / "crm.db")
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    monkeypatch.setattr(main, "crm_store", crm)
    monkeypatch.setattr(main, "stripe_vip_store", vip_store)
    monkeypatch.setattr(main, "stripe_checkout", CreatedCheckout())

    response = main.app.test_client().post(
        "/api/checkout",
        json={
            "email": "safe-checkout@example.com",
            "plan": "pro",
            "telegram_chat_id": "attacker-controlled-chat",
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["vip_link"]["status"] == "telegram_link_required"
    assert "telegram_chat_id" not in payload
    assert crm.find_by_email("safe-checkout@example.com")["telegram_chat_id"] == ""
    registered = vip_store.get_checkout("cs_created_123")
    assert registered["expected_amount_cents"] == 7900


def test_retry_reuses_created_invite_after_telegram_delivery_failure(monkeypatch, tmp_path):
    email = "retry@example.com"
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_retry_123",
        customer_email=email,
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="retry-link-token",
    )
    vip_store.mark_paid("cs_retry_123")
    vip_store.link_telegram_account("retry-link-token", "778899")
    flow = FailingOnceTelegramFlow()

    monkeypatch.setattr(main, "stripe_vip_store", vip_store)
    monkeypatch.setattr(main, "telegram_flow", flow)

    first = main._attempt_stripe_vip_delivery("cs_retry_123")
    second = main._attempt_stripe_vip_delivery("cs_retry_123")

    assert first["status"] == "invite_delivery_failed"
    assert second["status"] == "invite_sent"
    assert flow.calls == [
        ("create", "cs_retry_123"),
        ("send", "778899", "Pro", "https://t.me/+vip-once"),
        ("send", "778899", "Pro", "https://t.me/+vip-once"),
    ]
    assert vip_store.get_delivery("cs_retry_123")["status"] == "invite_sent"


def test_telegram_link_token_cannot_be_rebound_to_another_chat(tmp_path):
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_link_123",
        customer_email="bound@example.com",
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="immutable-link-token",
    )
    vip_store.mark_paid("cs_link_123")

    first = vip_store.link_telegram_account("immutable-link-token", "first-chat")
    second = vip_store.link_telegram_account("immutable-link-token", "other-chat")

    assert first["link_result"] == "linked"
    assert second["link_result"] == "conflict"
    assert vip_store.get_delivery("cs_link_123")["telegram_chat_id"] == "first-chat"


def test_stale_stripe_webhook_processing_lease_can_be_reclaimed(tmp_path):
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_lease_123",
        customer_email="lease@example.com",
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="lease-link-token",
    )

    first_claim = vip_store.claim_webhook_event(
        "evt_lease_123", "cs_lease_123", "checkout.session.completed"
    )
    assert first_claim["status"] == "claimed"
    assert vip_store.claim_webhook_event(
        "evt_lease_123", "cs_lease_123", "checkout.session.completed"
    )["status"] == "processing"
    with vip_store._sqlite_connection() as conn:
        conn.execute(
            "UPDATE stripe_webhook_events SET received_at=? WHERE event_id=?",
            ("2000-01-01T00:00:00+00:00", "evt_lease_123"),
        )
    reclaimed_claim = vip_store.claim_webhook_event(
        "evt_lease_123", "cs_lease_123", "checkout.session.completed"
    )
    assert reclaimed_claim["status"] == "claimed"
    assert reclaimed_claim["processing_token"] != first_claim["processing_token"]
    assert not vip_store.complete_webhook_event(
        "evt_lease_123", first_claim["processing_token"]
    )
    assert not vip_store.fail_webhook_event(
        "evt_lease_123", first_claim["processing_token"]
    )
    assert vip_store.get_webhook_event("evt_lease_123")["status"] == "processing"
    assert vip_store.complete_webhook_event(
        "evt_lease_123", reclaimed_claim["processing_token"]
    )


def test_expired_invite_is_replaced_before_retry(monkeypatch, tmp_path):
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_expired_123",
        customer_email="expired@example.com",
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="expired-link-token",
    )
    vip_store.mark_paid("cs_expired_123")
    vip_store.link_telegram_account("expired-link-token", "778899")
    vip_store.save_invite(
        "cs_expired_123",
        "https://t.me/+expired",
        (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
    )
    flow = RecordingTelegramFlow()

    monkeypatch.setattr(main, "stripe_vip_store", vip_store)
    monkeypatch.setattr(main, "telegram_flow", flow)

    result = main._attempt_stripe_vip_delivery("cs_expired_123")

    assert result["status"] == "invite_sent"
    assert flow.calls == [
        ("create", "cs_expired_123"),
        ("send", "778899", "Pro", "https://t.me/+vip-once"),
    ]


def test_expired_delivery_lease_cannot_be_released_by_previous_owner(tmp_path):
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_lock_123",
        customer_email="lock@example.com",
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="lock-link-token",
    )
    vip_store.ensure_delivery("cs_lock_123")
    first_lock = vip_store.acquire_delivery_lock("cs_lock_123")
    assert first_lock
    with vip_store._sqlite_connection() as conn:
        conn.execute(
            "UPDATE stripe_vip_deliveries SET delivery_lock_until=? WHERE checkout_id=?",
            ("2000-01-01T00:00:00+00:00", "cs_lock_123"),
        )
    second_lock = vip_store.acquire_delivery_lock("cs_lock_123")
    assert second_lock and second_lock != first_lock

    vip_store.release_delivery_lock("cs_lock_123", first_lock)

    assert vip_store.acquire_delivery_lock("cs_lock_123") is None
    vip_store.release_delivery_lock("cs_lock_123", second_lock)
    assert vip_store.acquire_delivery_lock("cs_lock_123")


def test_expired_delivery_lease_cannot_mutate_state_after_takeover(tmp_path):
    vip_store = StripeVIPStore(tmp_path / "vip.db")
    vip_store.register_checkout(
        checkout_id="cs_fence_123",
        customer_email="fence@example.com",
        plan_key="pro",
        expected_amount_cents=7900,
        currency="usd",
        source="test",
        campaign="stripe",
        link_token="fence-link-token",
    )
    vip_store.ensure_delivery("cs_fence_123")
    first_lock = vip_store.acquire_delivery_lock("cs_fence_123")
    assert first_lock
    with vip_store._sqlite_connection() as conn:
        conn.execute(
            "UPDATE stripe_vip_deliveries SET delivery_lock_until=? WHERE checkout_id=?",
            ("2000-01-01T00:00:00+00:00", "cs_fence_123"),
        )
    second_lock = vip_store.acquire_delivery_lock("cs_fence_123")
    assert second_lock and second_lock != first_lock

    assert vip_store.mark_delivery(
        "cs_fence_123", "invite_sent", lock_token=first_lock
    ) is None
    assert vip_store.get_delivery("cs_fence_123")["status"] == "pending_link"
    assert vip_store.mark_delivery(
        "cs_fence_123", "invite_sent", lock_token=second_lock
    )["status"] == "invite_sent"