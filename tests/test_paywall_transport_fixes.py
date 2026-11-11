# ── Four defects measured from OUTSIDE, fixed in the transport layer ────────

"""The paywall fixes of 11.11.2026, one test per measured symptom.

Each of these was found by an external rater rather than by us, which is the
point: every one of them was invisible to server-side clients and fatal to a
whole class of buyer.

1. CORS PREFLIGHT. Lumière PayCheck graded `/api/v1/verify-seller` and reported
   "Browser agents — can't pay it yet: CORS headers missing". Reproduced: OPTIONS
   returned the canonical `402` with no `Access-Control-Allow-Methods`. A browser
   agent aborts at the preflight and never reaches the paid retry. Both reference
   implementations in this niche (`tradingagentstack.com`, `x402pulse.dev`)
   answer OPTIONS with `204`. Fixed by answering the preflight before the paywall
   can challenge it.

2. METHOD WE DO NOT SERVE. `before_request` runs even after URL matching has
   failed, so a POST to a GET-only route was challenged, SETTLED, and only then
   killed by the dispatcher with a 405. On 21.10.2026
   `JarvisClaw-Federation/1.0` POSTed `/api/v1/signal`, paid $0.003 and got the
   405 — the row is still in `payment_guards` with `delivered_at IS NULL`, i.e.
   exactly the `n_paid_undelivered` a payer agent counts against a seller. Fixed
   by refusing before any credential is read.

3. MPP CHALLENGE. x402scan raises `MPP_NO_PAYMENT_CHALLENGES` (severity: error)
   on every paid row whose 402 carries only the legacy `WWW-Authenticate: x402 …`
   token. Fixed by adding a second `Payment` challenge that advertises
   `header="PAYMENT-SIGNATURE"` — the field our existing rail actually verifies.

4. A NATIVE MPP CREDENTIAL. Advertising a challenge makes a client entitled to a
   truthful answer when it follows the wrong one. A native MPP
   `Authorization: Payment` body is refusable and MUST NOT be charged. Fixed with
   a 401 that settles nothing.

Plus the local-store fault behind 1,335 `/api/dashboard/data` 500s on 10–11.11:
`file is not a database`. The file is on an ephemeral disk and holds only
survivable state, so the store now quarantines it and starts fresh.
"""

import base64
import json
import sqlite3

import pytest

PAID_ROUTE = "/api/stats"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "catalog_store",
                        create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)
    return main.app.test_client(), main, dash


def _exhaust_free_tier(main):
    """Make the next request to a paid route need a payment."""
    main._free_tier_usage["127.0.0.1"] = main.FREE_TIER_LIMIT


def _www_authenticate_values(response) -> list:
    """Every WWW-Authenticate value on the response, in wire order."""
    values = response.headers.get_all("WWW-Authenticate")
    if values is None:
        return []
    return [str(v) for v in values]


# ── 1. CORS preflight ───────────────────────────────────────────────────────

def test_the_options_preflight_is_204_not_a_402_challenge(client):
    """The exact failure Lumière PayCheck measured from the outside."""
    c, _main, _dash = client
    r = c.options(PAID_ROUTE, headers={
        "Origin": "https://agent.example.com",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "payment-signature,x-payment",
    })
    assert r.status_code == 204, (
        "a preflight answered with a 402 cannot be followed by a paid retry; "
        "got %s" % r.status_code)


def test_the_preflight_allows_the_headers_a_payer_must_send(client):
    """Without these names the browser strips the proof and the call is unpaid."""
    c, _main, _dash = client
    r = c.options(PAID_ROUTE, headers={"Origin": "https://agent.example.com"})
    allowed = r.headers.get("Access-Control-Allow-Headers", "").lower()
    for name in ("payment-signature", "x-payment", "x-payment-proof",
                 "content-type"):
        assert name in allowed, (
            "%s must be allowed or a cross-origin agent cannot send its proof; "
            "got %r" % (name, allowed))
    assert r.headers.get("Access-Control-Allow-Origin") == "*"
    assert "GET" in r.headers.get("Access-Control-Allow-Methods", "")


def test_the_preflight_neither_costs_a_free_call_nor_takes_money(client):
    """A preflight is a capability question, not a paid request."""
    c, main, _dash = client
    before = dict(main._free_tier_usage)
    for _ in range(3):
        r = c.options(PAID_ROUTE, headers={"Origin": "https://a.example"})
        assert r.status_code == 204
    assert dict(main._free_tier_usage) == before, (
        "OPTIONS must not consume the free tier — it would spend a buyer's one "
        "free call on a preflight")


def test_the_402_itself_still_carries_the_cors_layer(client):
    """The preflight is worthless if the challenged response lacks the headers."""
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE)
    assert r.status_code == 402
    assert r.headers.get("Access-Control-Allow-Origin") == "*"
    assert "payment-signature" in (
        r.headers.get("Access-Control-Allow-Headers", "").lower())
    exposed = r.headers.get("Access-Control-Expose-Headers", "")
    assert "PAYMENT-REQUIRED" in exposed


# ── 2. A method the route does not answer ───────────────────────────────────

def test_a_method_the_route_does_not_answer_is_refused_with_405(client):
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.post(PAID_ROUTE)
    assert r.status_code == 405, (
        "POST to a GET-only paid route must be refused outright; got %s"
        % r.status_code)
    body = r.get_json()
    assert body["payment_taken"] is False
    assert "GET" in body["allowed"]
    assert "GET" in r.headers.get("Allow", "")


def test_a_wrong_method_never_reaches_the_settlement_rail(client, monkeypatch):
    """The JarvisClaw case: money moved and a 405 came back."""
    c, main, _dash = client
    calls = []
    monkeypatch.setattr(
        main, "_try_consume_standard_payment",
        lambda *a, **kw: calls.append(a) or True)
    _exhaust_free_tier(main)
    r = c.post(PAID_ROUTE)
    assert r.status_code == 405
    assert calls == [], (
        "the settlement rail was reached for a method we cannot serve — this is "
        "the exact defect that charged JarvisClaw $0.003 for a 405")


def test_the_refusal_explains_it_settled_nothing(client):
    c, main, _dash = client
    _exhaust_free_tier(main)
    body = c.post(PAID_ROUTE).get_json()
    assert body["error"] == "method_not_allowed"
    assert "nothing was settled" in body["message"].lower()


def test_a_parked_surface_still_answers_404_for_every_method(client, monkeypatch):
    """ORDERING: the park must win over the method guard.

    With the guard first, `POST /agents` answered 405 instead of the park's
    `404 surface_retired`, and `test_demo_surfaces_can_be_parked_without_deleting_code`
    failed — the fix for one defect must not quietly undo another.
    """
    c, _main, _dash = client
    monkeypatch.setenv("KRISTO_DEMO_SURFACES", "off")
    for method in (c.get, c.post):
        r = method("/agents")
        assert r.status_code == 404, (
            "%s /agents -> %s; a retired surface answers 404 for every method"
            % (method.__name__.upper(), r.status_code))
        assert (r.get_json() or {}).get("error") == "surface_retired"


# ── 3. The MPP challenge ────────────────────────────────────────────────────

def test_the_402_advertises_an_mpp_payment_challenge(client):
    """x402scan: `MPP_NO_PAYMENT_CHALLENGES`, severity error, on every paid row."""
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE)
    assert r.status_code == 402
    challenges = _www_authenticate_values(r)
    payments = [v for v in challenges if v.strip().lower().startswith("payment ")]
    assert payments, (
        "no `Payment` challenge advertised; the catalogue raises "
        "MPP_NO_PAYMENT_CHALLENGES for exactly this. Got: %r" % challenges)


def test_the_legacy_x402_challenge_is_byte_identical(client):
    """Adding a scheme must not disturb the token every existing client parses."""
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE)
    legacy = [v for v in _www_authenticate_values(r)
              if v.strip().lower().startswith("x402 ")]
    assert len(legacy) == 1
    assert 'realm="kristo-intelligence"' in legacy[0]
    assert 'chain="base"' in legacy[0]


def test_the_mpp_challenge_declares_the_real_terms_and_the_right_header(client):
    """A challenge is a promise; these are the fields it must not get wrong."""
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE)
    raw = [v for v in _www_authenticate_values(r)
           if v.strip().lower().startswith("payment ")][0]

    params = {}
    for chunk in _split_params(raw[len("Payment "):]):
        if "=" in chunk:
            k, _, v = chunk.partition("=")
            params[k.strip()] = v.strip().strip('"')

    assert params.get("method") == "evm"
    assert params.get("intent") == "charge"
    assert params.get("realm") == "kristo-intelligence"
    assert params.get("header") == "PAYMENT-SIGNATURE", (
        "the challenge must point at the header our rail actually verifies, "
        "not at a Credential shape we cannot check")
    assert params.get("id"), "MPP requires a bound challenge id"
    assert params.get("expires", "").endswith("Z")

    padded = params["request"] + "=" * (-len(params["request"]) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    assert decoded["recipient"] == main.X402_RECEIVER_ADDRESS
    assert decoded["currency"] == main.X402_USDC_CONTRACT
    header_amount = int(round(float(r.headers["X-Payment-Amount-USDC"]) * 1e6))
    assert decoded["amount"] == str(header_amount), (
        "the challenge must quote the SAME price as the x402 challenge")


def _split_params(text: str) -> list:
    """Split `a="1", b="2"` on the commas that are not inside quotes."""
    parts, buf, quoted = [], [], False
    for ch in text:
        if ch == '"':
            quoted = not quoted
        if ch == "," and not quoted:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return parts


def test_every_paid_challenge_header_is_ascii(client):
    """A non-ASCII header value makes gunicorn reject the WHOLE response.

    Measured on the 21:29 deploy: the MPP `description` carried an em-dash from
    our own selling copy, gunicorn answered

        [WARNING] Invalid request: Invalid HTTP Header: '\\'Payment id=…\\''

    and the edge turned that into a 502 — the paid route became UNPAYABLE, which
    is strictly worse than the warning the challenge was added to silence.
    """
    c, main, _dash = client
    _exhaust_free_tier(main)
    for endpoint in sorted(main.X402_PAID_ENDPOINTS):
        _exhaust_free_tier(main)
        r = c.get(endpoint)
        if r.status_code != 402:
            continue
        for name, value in r.headers.items():
            try:
                str(value).encode("ascii")
            except UnicodeEncodeError:
                raise AssertionError(
                    "%s: header %s is not ASCII (%r) — gunicorn will reject the "
                    "response and the route becomes unpayable"
                    % (endpoint, name, value))


def test_the_description_is_folded_not_dropped(client):
    """The prose is decoration, but it should survive the fold when it can."""
    c, main, _dash = client
    folded = main._header_safe("Verify a seller — before you pay it \u2014 twice")
    assert folded == "Verify a seller - before you pay it - twice"
    assert '"' not in main._header_safe('say "hi"')
    assert "\\" not in main._header_safe("back\\slash")
    assert len(main._header_safe("x" * 500)) == 180


def test_the_challenge_still_goes_out_without_a_description(client, monkeypatch):
    """An endpoint with no selling copy must still get a valid challenge."""
    c, main, _dash = client
    monkeypatch.setitem(main.CHALLENGE_DESCRIPTIONS, PAID_ROUTE, "")
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE)
    assert r.status_code == 402
    raw = [v for v in _www_authenticate_values(r)
           if v.strip().lower().startswith("payment ")]
    assert raw, "the Payment challenge must not depend on a description existing"
    assert "description=" not in raw[0]


# ── 4. A native MPP credential ──────────────────────────────────────────────

def test_a_native_mpp_credential_is_refused_without_charging(client, monkeypatch):
    c, main, _dash = client
    calls = []
    monkeypatch.setattr(
        main, "_try_consume_standard_payment",
        lambda *a, **kw: calls.append(a) or True)
    _exhaust_free_tier(main)

    credential = base64.urlsafe_b64encode(json.dumps({
        "challenge": {"id": "abc", "method": "evm", "intent": "charge",
                      "realm": "kristo-intelligence", "request": "e30"},
        "payload": {"signature": "0xdead", "authorization": {}},
        "source": "did:pkh:eip155:8453:0x" + "11" * 20,
    }).encode()).decode().rstrip("=")

    r = c.get(PAID_ROUTE, headers={"Authorization": "Payment " + credential})
    assert r.status_code == 401, (
        "an unverifiable MPP Credential must be refused, not settled; got %s"
        % r.status_code)
    body = r.get_json()
    assert body["payment_taken"] is False
    assert body["expected_header"] == "PAYMENT-SIGNATURE"
    assert calls == [], "nothing may be settled for a credential we cannot verify"


def test_a_garbage_mpp_credential_is_also_refused_without_charging(client,
                                                                  monkeypatch):
    c, main, _dash = client
    calls = []
    monkeypatch.setattr(
        main, "_try_consume_standard_payment",
        lambda *a, **kw: calls.append(a) or True)
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE, headers={"Authorization": "Payment not-base64!!"})
    assert r.status_code == 401
    assert r.get_json()["payment_taken"] is False
    assert calls == []


def test_a_non_payment_authorization_header_is_not_read_as_mpp(client):
    """An unrelated Authorization header must not be mistaken for a payment."""
    c, main, _dash = client
    _exhaust_free_tier(main)
    r = c.get(PAID_ROUTE, headers={"Authorization": "Bearer something-else"})
    assert r.status_code != 401, (
        "a non-Payment Authorization header is not an MPP credential; got %s"
        % r.status_code)
    body = r.get_json() or {}
    assert body.get("error") != "mpp_credential_unsupported"


# ── 5. The local store that said `file is not a database` ───────────────────

def test_the_local_store_quarantines_a_file_that_is_not_a_database(tmp_path):
    """The fault behind 1,335 `/api/dashboard/data` 500s on 10–11.11."""
    import os

    from integrations.dashboard_store import DashboardStore

    path = tmp_path / "dashboard_state_v2.db"
    path.write_bytes(b"# this is not sqlite, it is what a crash left behind\n")

    store = DashboardStore(path)          # must NOT raise
    assert store.backend in ("sqlite", "postgresql")

    quarantined = list(tmp_path.glob("dashboard_state_v2.db.corrupt-*"))
    assert quarantined, (
        "the unreadable file must be kept as evidence, never deleted")
    assert quarantined[0].read_bytes().startswith(b"# this is not sqlite")

    # And the fresh file is a real database again.
    with sqlite3.connect(str(path)) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "payapi_state"} <= names
    assert os.path.getsize(path) > 0


def test_a_healthy_local_file_is_left_alone(tmp_path):
    """The healing must not fire on a good file."""
    from integrations.dashboard_store import DashboardStore

    path = tmp_path / "dashboard_state.db"
    first = DashboardStore(path)
    first.set_meta("healing_probe", "kept")

    second = DashboardStore(path)
    assert second.get_meta("healing_probe") == "kept"
    assert not list(tmp_path.glob("*.corrupt-*")), (
        "a readable database must never be quarantined")
