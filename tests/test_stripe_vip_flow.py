import json

import pytest

import main
from integrations.crm_store import CRMStore, LeadRecord


class VerifiedStripeEvent:
    def __init__(self, payload):
        self.payload = payload

    def verify_webhook(self, _body, _signature):
        return self.payload


class RecordingTelegramFlow:
    def __init__(self):
        self.calls = []

    def deliver_vip_invite(self, chat_id, checkout_id, plan_name):
        self.calls.append((chat_id, checkout_id, plan_name))
        return {"status": "invite_sent"}


def _checkout_completed(email, chat_id="778899"):
    return {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_verified_123",
                "customer_email": email,
                "metadata": {"plan": "pro", "telegram_chat_id": chat_id},
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
    store.add_lead(
        LeadRecord(
            email=email,
            source="test",
            campaign="stripe",
            plan="Pro",
            telegram_chat_id="778899",
        )
    )
    telegram_flow = RecordingTelegramFlow()
    event = _checkout_completed(email)
    event["type"] = event_type

    monkeypatch.setattr(main, "crm_store", store)
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
    assert second.get_json()["vip_access"] == "already_active"
    assert store.find_by_email(email)["payment_status"] == "paid"
    assert telegram_flow.calls == [("778899", "cs_verified_123", "Pro")]


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