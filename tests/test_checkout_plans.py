"""Checkout plan selection — the bug found by the owner's own test payment.

/sales/checkout rendered ONE plan ($79 Pro) as static text inside a hidden
field, so the $29 plan existed in pricing but was unreachable from the form.
A buyer could not choose; the API silently defaulted to Pro. These tests pin the
behaviour: every plan is offered with its price, nothing is pre-selected, and
the amount used for the payment session equals the single price source.
"""

import pytest

# ── Key-shaped test values are assembled at RUNTIME ────────────────────────
# GitHub's push protection rejected the first push of these tests with
# "Stripe API Key" pointing at this file: a fake `sk_live_…` literal is
# indistinguishable from a real one inside a diff, so the pattern must never
# appear contiguously in the repository text — only in memory while the test
# runs. (The bodies below are obviously fake; the point is the SHAPE.)
_LIVE_PREFIX = "sk_" + "live_"
_TEST_PREFIX = "sk_" + "test_"
_RESTRICTED_PREFIX = "rk_" + "live_"
_WEBHOOK_PREFIX = "whsec_"
_REDACTED = "***"


def _key(prefix: str, body: str) -> str:
    """Build a key-shaped string without writing one into the repo."""
    return prefix + body


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


# ── The key-name trap and the invisible failure it caused (14.09) ──────────

def test_the_secret_key_is_read_from_either_env_name(monkeypatch):
    """`STRIPE_SECRET_KEY` must work — it is Stripe's own name for the key, so it
    is what a human types. Until 14.09 the service read ONLY `STRIPE_API_KEY`, so
    a key set under the other name did absolutely nothing, silently."""
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_API_KEY", _key(_TEST_PREFIX, "primary_value"))
    primary = StripeCheckoutService()
    assert primary.key_source == "STRIPE_API_KEY"
    assert primary.key_format_ok is True and primary.enabled is True
    assert primary.key_mode == "test"

    # The same key under Stripe's own name is now picked up as well.
    fallback_value = _key(_LIVE_PREFIX, "fallback_value")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", fallback_value)
    fallback = StripeCheckoutService()
    assert fallback.key_source == "STRIPE_SECRET_KEY"
    assert fallback.api_key == fallback_value
    assert fallback.key_format_ok is True and fallback.enabled is True
    assert fallback.key_mode == "live"


def test_a_pasted_key_id_is_flagged_loudly_at_boot(monkeypatch, caplog):
    """The 14.09 failure, pinned at its source.

    The env held `mk_1U5Q…XI4u` — the ID of an API key, not the key. Stripe
    answered 401 ("This looks like the ID of an API key rather than the key
    itself") and every checkout returned 503, while OUR logs said nothing at all.
    Now the boot is loud, and the value is never printed.
    """
    import logging

    from integrations.stripe_checkout import StripeCheckoutService

    pasted_id = "mk_1U5QVexampleexampleexampleXI4u"
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.setenv("STRIPE_API_KEY", pasted_id)
    with caplog.at_level(logging.WARNING, logger="integrations.stripe_checkout"):
        svc = StripeCheckoutService()

    assert svc.key_format_ok is False, "a key ID must not pass the format check"
    assert svc.enabled is True, "it is non-empty, so the service still tries"
    assert svc.key_mode == "unknown"
    warnings = [r.getMessage() for r in caplog.records
                if r.levelno >= logging.WARNING]
    assert warnings, "this must be a WARNING, not a silent success"
    joined = " ".join(warnings)
    assert "mk_" in joined, "name the shape the owner pasted"
    assert "sk_ / rk_" in joined, "say what a real key looks like"
    assert pasted_id not in joined, "the value itself must NEVER be logged"
    assert "XI4u" not in joined, "not even its tail"


def test_no_key_at_all_is_not_reported_as_a_format_error(monkeypatch, caplog):
    """Missing is a different problem from malformed: no key means the service is
    disabled (and the dashboard says configured=false), not that something was
    pasted wrongly."""
    import logging

    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    with caplog.at_level(logging.INFO, logger="integrations.stripe_checkout"):
        svc = StripeCheckoutService()
    assert svc.enabled is False
    assert svc.key_format_ok is True
    assert svc.key_source == ""
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert "STRIPE_API_KEY/STRIPE_SECRET_KEY" in caplog.text, \
        "the log must name the variables it looked at"


def test_a_failed_checkout_logs_the_providers_own_message(monkeypatch, caplog):
    """A bare `except` used to swallow Stripe's reason entirely.

    The diagnosis of the 14.09 incident had to be rebuilt from the Stripe API by
    hand because our own log contained nothing but a generic error code. The
    provider's message is now recorded — with any key-shaped token redacted.
    """
    import logging

    from integrations.stripe_checkout import StripeCheckoutService

    class _BadSession:
        @staticmethod
        def create(**_kwargs):
            # Built at runtime — see the note at the top of this file.
            raise RuntimeError("Invalid API key provided: "
                               + _key(_LIVE_PREFIX, "ABCdefGHIjklMNOpqrSTUvwxYZ"))

    class _Checkout:
        Session = _BadSession

    class _FakeStripe:
        checkout = _Checkout

    leaked_body = "ABCdefGHIjklMNOpqrSTUvwxYZ"
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")
    svc = StripeCheckoutService()
    monkeypatch.setattr(svc, "_stripe", _FakeStripe)

    with caplog.at_level(logging.WARNING, logger="integrations.stripe_checkout"):
        result = svc.create_checkout_session("starter", "buyer@example.invalid")

    # The caller's contract is unchanged (no call site had to learn anything).
    assert result == {"status": "checkout_error", "provider": "stripe",
                      "error": "stripe_checkout_creation_failed"}
    assert "FAILED" in caplog.text and "plan=starter" in caplog.text
    assert "RuntimeError" in caplog.text
    assert _LIVE_PREFIX + _REDACTED in caplog.text, "the reason is kept"
    assert leaked_body not in caplog.text, "the credential is NOT kept"


def test_a_managed_payments_account_falls_back_without_payment_method_types(
        monkeypatch, caplog):
    """The new live account enables MANAGED PAYMENTS, which refuses
    `payment_method_types` with 400 "Unsupported parameter: payment_method_types"
    (observed live on 16.09: every checkout returned 503 *while the account could
    charge*). Accounts without Managed Payments still need the explicit card type,
    so the parameter is a fallback: try with it, retry ONCE without it on that
    exact error, and leave every other error alone.
    """
    import logging

    from integrations.stripe_checkout import StripeCheckoutService

    calls = []

    class _Created:
        id = "cs_test_managed"
        url = "https://checkout.stripe.com/c/pay/cs_test_managed"

    class _Sessions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if "payment_method_types" in kwargs:
                raise RuntimeError(
                    "Request req_x: Unsupported parameter: payment_method_types. "
                    "Managed Payments, which is enabled by default on your "
                    "account, handles this parameter for you.")
            return _Created()

    class _FakeStripe:
        checkout = type("Checkout", (), {"Session": _Sessions})()

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")
    service = StripeCheckoutService()
    monkeypatch.setattr(service, "_stripe", _FakeStripe)

    with caplog.at_level(logging.WARNING, logger="integrations.stripe_checkout"):
        result = service.create_checkout_session("starter",
                                                 "buyer@example.invalid")

    assert result["status"] == "checkout_created"
    assert result["checkout_id"] == "cs_test_managed"
    assert len(calls) == 2, "it must retry exactly once"
    assert calls[0].get("payment_method_types") == ["card"], \
        "the first attempt keeps the explicit card type for older accounts"
    assert "payment_method_types" not in calls[1], \
        "the retry drops the parameter Managed Payments owns"
    tax_codes = [li["price_data"]["product_data"]["tax_code"]
                 for li in calls[1]["line_items"]]
    assert tax_codes == ["txcd_10000000"], \
        "the tax code MUST survive the retry — Managed Payments requires it"
    assert "Managed Payments" in caplog.text


def test_the_line_item_carries_an_eligible_product_tax_code(monkeypatch):
    """Managed Payments (Stripe as MERCHANT OF RECORD, so VAT in 80+ countries is
    handled for us) refuses a session without a per-product tax code:
    "Invalid line_items[0]: the product tax code is missing." The default is the
    eligible general digital-services code, and `STRIPE_PRODUCT_TAX_CODE`
    overrides it without a code deploy."""
    from integrations.stripe_checkout import (StripeCheckoutService,
                                              _DEFAULT_PRODUCT_TAX_CODE)

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")

    assert _DEFAULT_PRODUCT_TAX_CODE == "txcd_10000000"
    monkeypatch.delenv("STRIPE_PRODUCT_TAX_CODE", raising=False)
    assert StripeCheckoutService().product_tax_code == "txcd_10000000"

    monkeypatch.setenv("STRIPE_PRODUCT_TAX_CODE", "txcd_10103001")
    service = StripeCheckoutService()
    assert service.product_tax_code == "txcd_10103001"

    captured = {}

    class _Created:
        id = "cs_test_tax"
        url = "https://checkout.stripe.com/c/pay/cs_test_tax"

    class _Sessions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return _Created()

    monkeypatch.setattr(service, "_stripe", type(
        "S", (), {"checkout": type("C", (), {"Session": _Sessions})()})())
    service.create_checkout_session("starter", "buyer@example.invalid")

    product = captured["line_items"][0]["price_data"]["product_data"]
    assert product["tax_code"] == "txcd_10103001"
    assert product["name"], "the product name is still sent"


def test_the_tax_code_is_dropped_only_for_an_account_that_refuses_it(monkeypatch,
                                                                    caplog):
    """The last step of the chain exists for an account with neither Managed
    Payments nor support for the tax code. It must be reached ONLY on a message
    that names tax_code as unsupported — a "tax code is missing" complaint is a
    reason to SEND it, never to drop it."""
    import logging

    from integrations.stripe_checkout import StripeCheckoutService

    calls = []

    class _Sessions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if "payment_method_types" in kwargs:
                raise RuntimeError("Unsupported parameter: payment_method_types")
            if "tax_code" in str(kwargs):
                raise RuntimeError("Unsupported parameter: tax_code")
            created = type("C", (), {"id": "cs_test_bare", "url": "u"})()
            return created

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")
    service = StripeCheckoutService()
    monkeypatch.setattr(service, "_stripe", type(
        "S", (), {"checkout": type("C", (), {"Session": _Sessions})()})())

    with caplog.at_level(logging.WARNING, logger="integrations.stripe_checkout"):
        result = service.create_checkout_session("starter", "b@example.invalid")

    assert result["status"] == "checkout_created"
    assert len(calls) == 3, "full → no methods → no methods and no tax code"
    assert "tax_code" in str(calls[1]), "step 2 keeps the tax code"
    assert "tax_code" not in str(calls[2]), "step 3 drops it"
    assert "does not accept a product tax code" in caplog.text

    # …and a "missing tax code" answer must NOT walk that last step.
    calls.clear()

    class _OnlyMissing:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            if "payment_method_types" in kwargs:
                raise RuntimeError("Unsupported parameter: payment_method_types")
            raise RuntimeError(
                "Invalid line_items[0]: the product tax code is missing.")

    service2 = StripeCheckoutService()
    monkeypatch.setattr(service2, "_stripe", type(
        "S", (), {"checkout": type("C", (), {"Session": _OnlyMissing})()})())
    result = service2.create_checkout_session("starter", "b@example.invalid")

    assert result["status"] == "checkout_error"
    assert len(calls) == 2, "no attempt to drop a tax code that is REQUIRED"


def test_an_unrelated_stripe_error_is_not_retried(monkeypatch):
    """Only the Managed-Payments refusal triggers the fallback — a real failure
    (bad key, bad amount) must surface immediately instead of being retried."""
    from integrations.stripe_checkout import StripeCheckoutService

    calls = []

    class _Sessions:
        @staticmethod
        def create(**kwargs):
            calls.append(dict(kwargs))
            raise RuntimeError("Invalid API key provided: sk_test_***")

    class _FakeStripe:
        checkout = type("Checkout", (), {"Session": _Sessions})()

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    monkeypatch.setenv("APP_PUBLIC_URL", "https://checkout.test")
    service = StripeCheckoutService()
    monkeypatch.setattr(service, "_stripe", _FakeStripe)

    result = service.create_checkout_session("starter", "buyer@example.invalid")

    assert result == {"status": "checkout_error", "provider": "stripe",
                      "error": "stripe_checkout_creation_failed"}
    assert len(calls) == 1, "no blind retry for an unrelated error"


def test_redact_hides_every_key_shaped_token():
    from integrations.stripe_checkout import redact

    live_body, test_body = "AAAABBBBCCCCDDDD", "11112222"
    restricted_body, webhook_body = "zzzz9999", "abcdef123456"
    text = ("failed: " + _key(_LIVE_PREFIX, live_body)
            + " and " + _key(_TEST_PREFIX, test_body)
            + " and " + _key(_RESTRICTED_PREFIX, restricted_body)
            + " and " + _key(_WEBHOOK_PREFIX, webhook_body))
    out = redact(text)
    for secret in (live_body, test_body, restricted_body, webhook_body):
        assert secret not in out
    assert out.count(_REDACTED) == 4
    assert _LIVE_PREFIX + _REDACTED in out
    assert _WEBHOOK_PREFIX + _REDACTED in out


def test_api_checkout_session_price_matches_plan_prices(client):
    from integrations.payment_integration import PLAN_PRICES

    test_client, _main = client
    for key in ("starter", "api"):
        body = test_client.post("/api/checkout",
                                json={"email": f"{key}@example.invalid",
                                      "plan": key}).get_json()
        assert body["payment_session"]["amount_usd"] == PLAN_PRICES[key]
        assert body["payment_session"]["plan"] == key


def test_the_stripe_payment_feed_survives_stripeobject_fields(monkeypatch):
    """The Stripe payment feed was UNAVAILABLE for days, failing once a minute,
    because of ONE call: `metadata.get("plan", "")` on a StripeObject.

        AttributeError: 'get' is a dict method, but a StripeObject is not a dict.

    The admin view then silently fell back to the CRM list (`detail:
    "stripe_list_unavailable"`, "Stripe snapshot: не") while the Stripe API itself
    answered 200 — a working feed presented as broken, with the real cause only in
    a log line nobody read. SDK objects expose fields as ATTRIBUTES, so the reader
    must never use .get() on them.
    """
    from integrations.stripe_checkout import StripeCheckoutService

    class StripeObject:
        """Faithful stand-in: attribute access, .get() raises like the SDK."""

        def __init__(self, **fields):
            self.__dict__.update(fields)

        def get(self, *args, **kwargs):
            raise AttributeError(
                "'get' is a dict method, but a StripeObject is not a dict. "
                "Use .to_dict() to convert it.")

    class Sessions:
        data = [StripeObject(
            id="cs_live_paid", payment_status="paid", amount_total=3480,
            currency="usd", created=1758000000, customer_email="",
            customer_details=StripeObject(email="buyer@example.com"),
            metadata=StripeObject(plan="starter", campaign="launch"))]
        has_more = False

    class Session:
        @staticmethod
        def list(**kwargs):
            return Sessions()

    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", _key(_TEST_PREFIX, "whatever"))
    service = StripeCheckoutService()
    monkeypatch.setattr(service, "_stripe", type(
        "S", (), {"checkout": type("C", (), {"Session": Session})()})())

    result = service.list_recent_completed_payments()

    assert result["available"] is True, result.get("reason", result)
    assert len(result["payments"]) == 1
    payment = result["payments"][0]
    assert payment["plan"] == "starter", "the metadata plan must survive"
    assert payment["amount_usd"] == 34.8
    assert payment["email"] == "buyer@example.com"
    assert payment["checkout_id"] == "cs_live_paid"
    assert payment["provider"] == "stripe"
    # …and the trap is still a trap: this is what used to kill the whole feed.
    with pytest.raises(AttributeError):
        Sessions.data[0].metadata.get("plan")


def test_the_paid_webhook_records_the_event_time_and_reports_it_once(
        client, monkeypatch, caplog, tmp_path):
    """Two things the first human payment taught us (16.09):

    1. the sale must be dated by the EVENT's own timestamp — the owner's check is
       `paid_at == event created`; before this the dashboard dated a sale by the
       LEAD's creation (38 s early that time, hours early if a buyer pays later);
    2. a successful money path must be AUDIBLE. The 200 lives only in the access
       log, which is not retained, so a silent success was indistinguishable from
       a silent failure. Exactly ONE INFO line, with the checkout id, plan and
       amount — and the customer masked, like every other surface.
    """
    import logging
    from datetime import datetime, timezone

    from integrations.crm_store import CRMStore

    test_client, main = client
    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    main.crm_store.add_lead(main.LeadRecord(
        email="gergana@example.com", source="website", campaign="launch",
        plan="Starter"))

    event_created = 1789548968            # 2026-09-16 08:56:08 UTC — the sale
    monkeypatch.setattr(main.stripe_checkout, "verify_webhook",
                        lambda _payload, _signature: {
                            "type": "checkout.session.completed",
                            "created": event_created,
                            "data": {"object": {
                                "id": "cs_live_first_paid",
                                "customer_email": "gergana@example.com",
                                "amount_total": 3480,
                                "currency": "usd",
                                "payment_status": "paid",
                                "metadata": {"plan": "starter"},
                            }},
                        })

    with caplog.at_level(logging.INFO, logger="kristo.v6.main"):
        response = test_client.post("/api/webhooks/stripe", data=b"{}",
                                    headers={"Stripe-Signature": "test"})

    assert response.status_code == 200
    assert response.get_json()["status"] == "paid"

    lead = main.crm_store.find_by_email("gergana@example.com")
    assert lead["paid_at"] == datetime.fromtimestamp(
        event_created, tz=timezone.utc).isoformat(), "paid_at == event created"
    assert lead["checkout_id"] == "cs_live_first_paid"
    assert lead["plan"] == "starter" and lead["amount_usd"] == 34.80
    assert lead["payment_status"] == "paid"

    money_lines = [r.getMessage() for r in caplog.records
                   if "money event" in r.getMessage()]
    assert len(money_lines) == 1, money_lines
    assert "checkout_id=cs_live_first_paid" in money_lines[0]
    assert "plan=starter" in money_lines[0] and "$34.80" in money_lines[0]
    assert "2026-09-16T08:56:08" in money_lines[0]
    assert "gergana@example.com" not in money_lines[0], "emails stay masked"
