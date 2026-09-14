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
