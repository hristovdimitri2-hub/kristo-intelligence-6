"""The honesty rules of the seller audit.

This module exists to be handed to somebody deciding whether to send money, so
the rules that matter are the ones about NOT overstating: a window that was not
read end to end must never look like a window with no payments, and a failed
read must never look like a zero.

Every test here works on `build_audit`, which is pure — no RPC, no Flask — so
the split is proven rather than asserted.
"""
import json
from datetime import datetime, timezone

import pytest

from services.seller_audit import (
    AUDIT_CACHE_SECONDS,
    MAX_AUDIT_DAYS,
    MIN_AUDIT_DAYS,
    build_audit,
    cached_audit,
    store_audit,
)

RECEIVER = "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f"
OTHER = "0x1111111111111111111111111111111111111111"
CANARY = "0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0"


def _t(payer, amount, tx="0xabc"):
    return {"tx_hash": tx, "payer": payer, "amount_usdc": amount,
            "block_number": 1}


def _audit(transfers, complete=True, failed_reason=""):
    cov = {"complete": complete, "from_block": 1, "to_block": 100,
           "requested_blocks": 100, "scanned_blocks": 100 if complete else 60,
           "failed_ranges": 0 if complete else 2, "split_retries": 0}
    return build_audit(transfers, cov, receiver=RECEIVER, days=7,
                       failed_reason=failed_reason)


# ── "could not look" must never be published as "found nothing" ──────────────

def test_an_incomplete_window_is_partial_and_says_so():
    """The defect class this whole service fights, applied to money."""
    report = _audit([_t(OTHER, 0.003)], complete=False)

    assert report["read"] == "partial"
    assert report["coverage"]["complete"] is False
    assert "not read end to end" in report["verdict"]
    assert "not evidence that nobody paid" in report["verdict"], (
        "a partial read must never be readable as a clean zero")


def test_a_failed_read_is_not_a_zero():
    report = _audit([], failed_reason="rpc_read_failed: ConnectionError")

    assert report["read"] == "failed"
    assert report["ok"] is False
    assert report["read_reason"] == "rpc_read_failed: ConnectionError"
    assert "unknown, not as empty" in report["verdict"]


def test_a_clean_window_with_no_payers_is_a_real_zero():
    """The other direction: a real zero must be reported as a zero.

    An absence must not be softened into "unknown" either — that would hide a
    seller's real problem from them.
    """
    report = _audit([])

    assert report["read"] == "clean"
    assert report["payer_analysis"]["external_unique_payers"] == 0
    assert "real zero for this window" in report["verdict"]


# ── the headline cannot be inflated ──────────────────────────────────────────

def test_a_reviewer_canary_is_not_counted_as_a_customer():
    """Known verification addresses pay real USDC but are not customers."""
    report = _audit([_t(CANARY, 0.003), _t(OTHER, 0.003)])

    analysis = report["payer_analysis"]
    assert analysis["external_unique_payers"] == 1, (
        "the canary inflated the customer count")
    assert analysis["known_verification_txs"] == 1
    assert analysis["known_verifications"][0]["payer"].lower() == CANARY.lower()


def test_a_treasury_sized_transfer_is_not_a_per_call_payment():
    report = _audit([_t(OTHER, 0.003), _t("0x" + "9" * 40, 5000.0)])

    analysis = report["payer_analysis"]
    assert analysis["noise"]["large_tx_count"] == 1
    assert analysis["total_usdc"] == pytest.approx(0.003), (
        "a treasury flow was counted as per-call revenue")


def test_the_verdict_counts_repeat_payers_from_the_real_bucket():
    report = _audit([_t(OTHER, 0.003, "0xa"), _t(OTHER, 0.003, "0xb"),
                     _t("0x" + "2" * 40, 0.003, "0xc")])

    assert report["payer_analysis"]["external_unique_payers"] == 2
    assert "1 of them paid more than once" in report["verdict"]


# ── the report states its own limits ─────────────────────────────────────────

def test_the_notes_refuse_to_equate_an_address_with_a_customer():
    report = _audit([_t(OTHER, 0.003)])
    notes = " ".join(report["notes"])

    assert "not a distinct customer" in notes, (
        "a distinct address is not a distinct customer and the buyer must be told")


def test_the_report_is_json_serialisable():
    """It is served over HTTP; a datetime leaking in would break the response."""
    report = _audit([_t(OTHER, 0.003)])

    assert json.loads(json.dumps(report))["receiver"] == RECEIVER
    assert report["checked_at"] == json.loads(json.dumps(report))["checked_at"]
    datetime.fromisoformat(report["checked_at"])


# ── the cache is a convenience, and bounded ──────────────────────────────────

def test_an_audit_is_reused_while_fresh_and_a_copy_is_handed_out():
    store_audit(RECEIVER, 7, {"marker": 1})

    first = cached_audit(RECEIVER, 7)
    assert first == {"marker": 1}

    first["marker"] = 999          # a caller must not poison the next caller
    assert cached_audit(RECEIVER, 7) == {"marker": 1}
    assert cached_audit(RECEIVER, 30) is None, "the window is part of the key"


def test_the_window_is_bounded_both_ways():
    assert MIN_AUDIT_DAYS >= 1
    assert MAX_AUDIT_DAYS <= 30, (
        "a longer window than this is thousands of chunked calls on a public RPC")
    assert AUDIT_CACHE_SECONDS >= 60, (
        "a shorter cache would make the same receiver pay for RPC twice")


# ── the free surface ─────────────────────────────────────────────────────────
#
# It must answer for a stranger, so it must not 500 when the thing it reads is
# broken, and it must never promote "no heartbeat" into "nobody paid".


class _Store:
    def __init__(self, rows=None, heartbeat=None, boom=False):
        self._rows = rows or []
        self._heartbeat = heartbeat
        self._boom = boom

    def sales_summary(self, history_limit=1000):
        if self._boom:
            raise RuntimeError("store is down")
        return {"history": self._rows}

    def get_meta(self, key):
        if self._boom:
            raise RuntimeError("store is down")
        return self._heartbeat


def _iso(dt):
    return dt.isoformat()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    return main.app.test_client()


def _serve(monkeypatch, store):
    import main

    monkeypatch.setattr(main, "dashboard_db", store)
    # The route reads this process's copy only when main.py IS __main__; under
    # pytest it takes the `from main import ...` branch, so patching the module
    # attribute is what the route actually sees.
    return main.app.test_client()


def test_the_fresh_surface_is_free_even_with_the_free_tier_exhausted(
        monkeypatch, client):
    """It is advertised as free, so it must not answer 402 to anybody."""
    import main

    monkeypatch.setattr(main, "dashboard_db", _Store(rows=[]))
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = client.get("/api/v1/seller-audit")
    finally:
        main._free_tier_usage.clear()

    assert r.status_code == 200, r.status_code


def test_no_monitor_heartbeat_is_partial_and_never_a_zero(monkeypatch):
    """The whole point: an unread window must not be published as no payments."""
    client = _serve(monkeypatch, _Store(rows=[], heartbeat=None))
    body = client.get("/api/v1/seller-audit").get_json()

    assert body["read"] == "partial", body["read"]
    assert body["coverage"]["complete"] is False
    assert "not evidence that nobody paid" in body["verdict"]


def test_a_fresh_heartbeat_makes_a_read_window_clean(monkeypatch):
    now = datetime.now(timezone.utc)
    client = _serve(monkeypatch, _Store(rows=[], heartbeat=_iso(now)))
    body = client.get("/api/v1/seller-audit").get_json()

    assert body["read"] == "clean"
    assert body["coverage"]["complete"] is True
    assert "real zero for this window" in body["verdict"]


def test_the_surface_reports_stored_payers_and_stays_fresh(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = [
        {"tx_hash": "0x1", "sender": OTHER, "amount_usdc": 0.003,
         "block_number": 10, "ts": _iso(now), "payer_class": "external"},
        {"tx_hash": "0x2", "sender": CANARY, "amount_usdc": 0.003,
         "block_number": 11, "ts": _iso(now), "payer_class": "canary"},
    ]
    client = _serve(monkeypatch, _Store(rows=rows, heartbeat=_iso(now)))
    body = client.get("/api/v1/seller-audit").get_json()

    assert body["payer_analysis"]["external_unique_payers"] == 1
    assert body["payer_analysis"]["known_verification_txs"] == 1


def test_a_broken_store_is_failed_not_a_crash(monkeypatch):
    """A stranger reading this page must get an honest report, not a 500."""
    client = _serve(monkeypatch, _Store(boom=True))
    r = client.get("/api/v1/seller-audit")

    assert r.status_code == 200, r.status_code
    body = r.get_json()
    assert body["read"] == "failed"
    assert body["ok"] is False
    assert "store_unreadable" in (body["read_reason"] or "")


def test_the_window_parameter_is_clamped(monkeypatch):
    now = datetime.now(timezone.utc)
    for asked, expected in (("9999", MAX_AUDIT_DAYS), ("0", MIN_AUDIT_DAYS),
                            ("nonsense", 7)):
        client = _serve(monkeypatch, _Store(rows=[], heartbeat=_iso(now)))
        body = client.get(f"/api/v1/seller-audit?days={asked}").get_json()
        assert body["window_days"] == expected, (asked, body["window_days"])


def test_the_surface_says_what_it_is_and_what_it_is_not(monkeypatch):
    """It is fixed to our own receiver, and must say so rather than imply more."""
    now = datetime.now(timezone.utc)
    client = _serve(monkeypatch, _Store(rows=[], heartbeat=_iso(now)))
    body = client.get("/api/v1/seller-audit").get_json()

    assert "own receiver" in body["scope_note"]
    assert "monitor records" in body["source"]

