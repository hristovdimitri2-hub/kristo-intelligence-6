"""Checkout plan selection — the bug found by the owner's own test payment.

/sales/checkout rendered ONE plan ($79 Pro) as static text inside a hidden
field, so the $29 plan existed in pricing but was unreachable from the form.
A buyer could not choose; the API silently defaulted to Pro. These tests pin the
behaviour: every plan is offered with its price, nothing is pre-selected, and
the amount used for the payment session equals the single price source.
"""

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    # Mock payments let the flow complete locally and — importantly — the mock
    # session carries the amount resolved from the single price source, which is
    # exactly what the drift test asserts against.
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "catalog_store",
                        create_catalog_store(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main.app.test_client(), main


def test_checkout_page_offers_every_plan_including_the_29_one(client):
    """The page must show all three plans with their prices — the $29 plan used
    to be unreachable because the template printed one plan as static text."""
    test_client, _main = client
    html = test_client.get("/sales/checkout").get_data(as_text=True)

    assert '<select name="plan" required>' in html
    assert "type=\"hidden\" name=\"plan\"" not in html, \
        "the plan must no longer be a hidden field"
    for key, label in (("starter", "$29"), ("pro", "$79"), ("api", "$149")):
        assert f'value="{key}"' in html, f"plan {key} missing from the selector"
        assert label in html, f"price {label} not shown on the page"


def test_checkout_page_preselects_nothing_by_default(client):
    """No silent default: without ?plan= the buyer must choose."""
    test_client, _main = client
    html = test_client.get("/sales/checkout").get_data(as_text=True)
    selector = html.split('<select name="plan"', 1)[1].split("</select>", 1)[0]
    # The placeholder ("— изберете пакет —") is the selected option, not a plan:
    assert '<option value="" disabled selected>' in selector
    assert selector.count("selected") == 1, "exactly one option is selected"


def test_checkout_page_preselects_a_real_plan_from_the_query(client):
    """?plan=starter still works (and a bogus key selects nothing)."""
    test_client, _main = client
    html = test_client.get("/sales/checkout?plan=starter").get_data(as_text=True)
    selector = html.split('<select name="plan"', 1)[1].split("</select>", 1)[0]
    assert '<option value="starter" selected>' in selector
    assert selector.count("selected") == 1

    bogus = test_client.get("/sales/checkout?plan=nope").get_data(as_text=True)
    assert '<option value="nope"' not in bogus
    assert "selected" in bogus.split('name="plan"', 1)[1]    # placeholder only


def test_checkout_without_a_plan_does_not_silently_default_to_pro(client):
    """Posting the form with no plan must REFUSE, not quietly charge $79."""
    test_client, _main = client
    resp = test_client.post("/sales/checkout",
                            data={"email": "buyer@example.invalid"})
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] == "Изберете пакет."
    assert body["available_plans"] == ["api", "pro", "starter"]
    assert "payment_session" not in body, "no session may be created"


def test_checkout_with_an_unknown_plan_is_refused(client):
    test_client, _main = client
    resp = test_client.post("/sales/checkout",
                            data={"email": "buyer@example.invalid",
                                  "plan": "enterprise"})
    assert resp.status_code == 400
    assert resp.get_json()["error"] == "Невалиден план."


def test_api_checkout_requires_an_explicit_plan(client):
    """The JSON API used to default to Pro ($79) when the field was missing."""
    test_client, _main = client
    missing = test_client.post("/api/checkout",
                               json={"email": "api@example.invalid"})
    assert missing.status_code == 400
    assert missing.get_json()["error"] == "plan is required"
    assert missing.get_json()["available_plans"] == ["api", "pro", "starter"]

    unknown = test_client.post("/api/checkout",
                               json={"email": "api@example.invalid",
                                     "plan": "enterprise"})
    assert unknown.status_code == 400
    assert unknown.get_json()["error"] == "unknown plan"


def test_the_29_plan_creates_a_session_priced_from_the_single_source(client):
    """The acceptance criterion: choosing the $29 plan produces a $29 session —
    and every plan's session price equals PLAN_PRICES (zero drift, the lesson
    from the phantom "$0.05 on the storefront vs $0.005 charged")."""
    from integrations.payment_integration import PLAN_PRICES

    test_client, _main = client
    for key in ("starter", "pro", "api"):
        resp = test_client.post("/sales/checkout",
                                data={"email": f"{key}@example.invalid",
                                      "plan": key})
        assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
        body = resp.get_json()
        session = body["payment_session"]
        assert session["status"] == "mock_checkout_ready"
        assert session["amount_usd"] == PLAN_PRICES[key], \
            f"{key}: session ${session['amount_usd']} != PLAN_PRICES ${PLAN_PRICES[key]}"
        # …and the lead the CRM records carries the same plan the buyer chose.
        assert body["lead"]["plan"] == {"starter": "Starter", "pro": "Pro",
                                        "api": "API Access"}[key]

    # The single source is untouched by all of this.
    assert PLAN_PRICES == {"starter": 29.0, "pro": 79.0, "api": 149.0}


def test_api_checkout_session_price_matches_plan_prices(client):
    from integrations.payment_integration import PLAN_PRICES

    test_client, _main = client
    for key in ("starter", "api"):
        body = test_client.post("/api/checkout",
                                json={"email": f"{key}@example.invalid",
                                      "plan": key}).get_json()
        assert body["payment_session"]["amount_usd"] == PLAN_PRICES[key]
        assert body["payment_session"]["plan"] == key
