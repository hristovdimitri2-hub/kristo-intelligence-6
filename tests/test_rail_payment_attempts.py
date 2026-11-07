"""The payment rail records the ATTEMPT, not just the response (07.11.2026).

`request_log` records WHAT WE ANSWERED, and the paywall's status codes carry less
information than they appear to:

    402  no credential was presented  -> the canonical challenge
    401  a credential WAS presented and we refused it
    425  a settlement is on-chain, our node has not caught up
    200  paid

So a buyer whose valid signature fails to settle and a buyer who sent a garbage
signature BOTH get a 401. Two opposite facts — "we lost a sale we caused" and
"the client is buggy" — collapse into one status code, and the board could not
tell them apart.

These tests pin the recording at the rail itself. Verify and settle are stubbed
by the recovery suite's own helpers; everything the rail does around them — the
402/401 distinction, the guard claim, the depth gate — runs for real, so a call
site that stops recording is caught here rather than discovered as a flat funnel.

`abandoned` is deliberately NOT recorded: it is the 402 count, read straight from
`request_log`, and it survives this table breaking entirely.
"""

import pytest

# `env` is imported as a NAME on purpose: pytest resolves fixtures by name in
# the test module's namespace, so importing the function is what makes it
# available here. The rest are plain helpers.
from test_payment_recovery import (  # noqa: F401
    _FakeEth, _install_fake_web3, _receipt, _standard_header, env,
    NONCE_A, PAYER, TX_SELF)


def _outcomes(store, path=None):
    """(`outcome`, `path`) pairs recorded on the rail."""
    target = getattr(store, "history", store)
    rows = target.payment_attempt_rows()
    return sorted((r["outcome"], r["path"]) for r in rows
                  if path is None or r["path"] == path)


def _rows(store, path=None):
    target = getattr(store, "history", store)
    out = target._run(
        "SELECT path, outcome, payer, amount_usdc, detail, tx_hash "
        "FROM payment_attempts", (), "all")[0] or []
    return [dict(r) for r in out if path is None or r["path"] == path]


# ── nothing presented: nothing recorded ─────────────────────────────────────

def test_a_buyer_who_presents_nothing_is_not_recorded(env):
    """The abandonment case must stay DERIVED. A row here would be subtracted
    from the 402 count a second time and erase real abandonment."""
    r = env.client.get("/api/stats")
    assert r.status_code == 402, r.get_json()
    assert _outcomes(env.dash) == [], (
        "a buyer who never presented a payload produced an attempt row, so "
        "`abandoned` will under-count by exactly that many")


# ── a payload that does not verify ──────────────────────────────────────────

def test_a_rejected_payload_is_recorded_as_rejected(env, monkeypatch):
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (False, PAYER, "signature_mismatch"))
    r = env.client.get("/api/stats",
                       headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    # 401, NOT 402 — the paywall's own distinction (main.py:4092): a credential
    # WAS presented and we refused it. This is the fact the whole funnel design
    # rests on, so it is asserted rather than assumed.
    assert r.status_code == 401, r.get_json()
    assert _outcomes(env.dash) == [("rejected", "/api/stats")], (
        "a payload that arrived and failed verification was not recorded, so "
        "the funnel cannot tell it from a buyer who never tried")


def test_a_rejected_payload_keeps_its_reason(env, monkeypatch):
    """The detail is what makes the row actionable rather than a tally."""
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (False, PAYER, "signature_mismatch"))
    env.client.get("/api/stats",
                   headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    row = _rows(env.dash, "/api/stats")[0]
    assert "signature_mismatch" in (row["detail"] or ""), row


# ── verified, but we could not take the money ───────────────────────────────

def test_a_failed_settlement_is_recorded_as_settle_failed(env, monkeypatch):
    """THE lost sale. The buyer authorised a real payment; our rail refused it.

    It answers 401 — the SAME status as a bad signature. That is the blind spot:
    `request_log` can only say "a credential was refused", never which of the two
    opposite reasons it was, so the board read 1,779 challenges and 0 payments on
    07.11 with no way to say how many were sales we dropped.
    """
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment",
                        lambda h, r: ("", "insufficient_funds"))
    r = env.client.get("/api/stats",
                       headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert r.status_code == 401, r.get_json()
    assert _outcomes(env.dash) == [("settle_failed", "/api/stats")], (
        "a settlement we failed to take was not recorded — this is a lost sale "
        "filed as 'nobody was interested'")
    row = _rows(env.dash, "/api/stats")[0]
    assert row["payer"] == PAYER, "the payer is who we would have to contact"
    assert "insufficient_funds" in (row["detail"] or "")


def test_a_failed_settlement_survives_a_raising_connector(env, monkeypatch):
    """Telemetry must never be what breaks a payment response."""
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))

    def boom(h, r):
        raise RuntimeError("facilitator exploded")

    monkeypatch.setattr(env.connectors, "settle_standard_payment", boom)
    r = env.client.get("/api/stats",
                       headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert r.status_code >= 400, "the rail must still answer, not crash"


# ── the sale ────────────────────────────────────────────────────────────────

def test_a_settled_payment_is_recorded_as_settled(env, monkeypatch):
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment",
                        lambda h, r: (TX_SELF, "settled_self_broadcast"))
    receipt = _receipt(TX_SELF, 100, PAYER, 5000, env.main.X402_RECEIVER_ADDRESS)
    eth = _FakeEth(block_number=101, receipts={TX_SELF: receipt}, auth_logs=[])
    _install_fake_web3(monkeypatch, eth)

    r = env.client.get("/api/stats",
                       headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert r.status_code == 200, r.get_json()
    assert _outcomes(env.dash) == [("settled", "/api/stats")], (
        "a completed sale was not recorded on the rail")
    row = _rows(env.dash, "/api/stats")[0]
    assert row["tx_hash"] == TX_SELF, "the sale must carry its settlement tx"


def test_a_settled_payment_is_recorded_before_the_depth_gate(env, monkeypatch):
    """A settlement our node has not caught up to is STILL a buyer who paid.

    The rail answers 425 in that window. Recording nothing would file a real
    payment under abandonment — the exact confusion the table exists to remove.
    """
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment",
                        lambda h, r: (TX_SELF, "settled_self_broadcast"))
    receipt = _receipt(TX_SELF, 100, PAYER, 5000, env.main.X402_RECEIVER_ADDRESS)
    # head BELOW the settlement's block: the depth gate refuses with 425.
    eth = _FakeEth(block_number=99, receipts={TX_SELF: receipt}, auth_logs=[])
    _install_fake_web3(monkeypatch, eth)

    r = env.client.get("/api/stats",
                       headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert r.status_code == 425, r.get_json()
    assert _outcomes(env.dash) == [("settled", "/api/stats")], (
        "a payment that is on-chain but not yet deep enough was filed as no "
        "payment at all")


# ── the two calls are mutually exclusive ────────────────────────────────────

def test_exactly_one_attempt_row_per_presented_payload(env, monkeypatch):
    """One payload, one row. Two rows for one attempt would inflate every rate."""
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (True, PAYER, "verified_locally"))
    monkeypatch.setattr(env.connectors, "settle_standard_payment",
                        lambda h, r: ("", "insufficient_funds"))
    env.client.get("/api/stats",
                   headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert len(_rows(env.dash, "/api/stats")) == 1


def test_a_rejected_payload_is_never_also_recorded_as_settled(env, monkeypatch):
    """Verification failing must short-circuit the settle recording."""
    monkeypatch.setattr(env.connectors, "verify_standard_payment",
                        lambda h, r: (False, PAYER, "signature_mismatch"))

    def must_not_run(h, r):
        raise AssertionError("settle ran for a payload that did not verify")

    monkeypatch.setattr(env.connectors, "settle_standard_payment", must_not_run)
    env.client.get("/api/stats",
                   headers={"PAYMENT-SIGNATURE": _standard_header(env.main)})
    assert _outcomes(env.dash) == [("rejected", "/api/stats")]
