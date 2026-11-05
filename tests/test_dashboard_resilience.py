"""The dashboard must stay operational — and must stay HONEST while it does.

The owner's requirement is that the board is always up ("искам таблото
постоянно да е оперативно"). Bounding the Postgres waits (see
tests/test_shared_pg_link_bounds.py) stops a slow read from taking the whole
service down, but a fast failure still leaves the board blank.

`_dashboard_payload_resilient` closes that gap: when the live build fails it
replays the last payload that DID build, with its age attached.

The risk this file exists to police is that the fallback becomes a way to show
something that is not true. A stale number presented as live is worse than no
number at all, and a cache keyed more loosely than the grant would hand a
public caller an ADMIN payload — the one thing `include_crm` and
`include_sales_detail` exist to prevent. Both are asserted here.
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture()
def main_module():
    """main.py with the networked background threads off."""
    import os

    os.environ.setdefault("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    return main


@pytest.fixture(autouse=True)
def _clean_cache(main_module):
    """Every test starts with an empty cache and leaves one behind."""
    with main_module._DASHBOARD_LAST_GOOD_LOCK:
        main_module._DASHBOARD_LAST_GOOD.clear()
    yield
    with main_module._DASHBOARD_LAST_GOOD_LOCK:
        main_module._DASHBOARD_LAST_GOOD.clear()


def _fake_payload(monkeypatch, main, value=1.23):
    """Replace the real builder with a controllable stand-in."""
    calls = {"n": 0}

    def builder(include_crm=False, include_sales_detail=False):
        calls["n"] += 1
        return {
            "ok": True,
            "generated_at": "2026-11-05T00:00:00+00:00",
            "receiver_address": "0xd4cdA900839c0FED4374EE37EA0DBE8e4c6fd08f",
            "sections": {"onchain": {"total_usdc": value}},
            "build_no": calls["n"],
            "crm": {"leads": 7} if include_crm else None,
        }

    monkeypatch.setattr(main, "_canonical_dashboard_payload", builder)
    return calls


# ── 1. the happy path is unchanged, and it is marked live ──────────────────
def test_a_successful_build_is_marked_not_stale(main_module, monkeypatch):
    main = main_module
    _fake_payload(monkeypatch, main)

    payload = main._dashboard_payload_resilient(False, False)

    assert payload["ok"] is True
    assert payload["stale"] is False, (
        "a live payload must say so; the page keys its 'stale' banner off this")


# ── 2. the fallback preserves the last real numbers, clearly labelled ──────
def test_a_failed_build_serves_the_last_good_read_marked_stale(
        main_module, monkeypatch):
    main = main_module
    _fake_payload(monkeypatch, main)

    live = main._dashboard_payload_resilient(False, False)
    real_total = live["sections"]["onchain"]["total_usdc"]

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("shared Postgres link busy")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)

    fallback = main._dashboard_payload_resilient(False, False)

    assert fallback["stale"] is True
    assert "stale_since" in fallback and "stale_age_seconds" in fallback
    assert fallback["stale_age_seconds"] >= 0
    assert "last figures" in fallback["stale_reason"]
    # THE POINT: the real numbers survive the outage rather than blanking.
    assert fallback["sections"]["onchain"]["total_usdc"] == real_total, (
        "the fallback must replay the last real read, not invent a zero")


def test_the_stale_marker_reports_how_old_the_data_is(main_module, monkeypatch):
    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("down")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)
    time.sleep(0.05)
    fallback = main._dashboard_payload_resilient(False, False)

    assert fallback["stale_age_seconds"] > 0, (
        "an age of zero would claim the stale data is current")


# ── 3. with nothing cached, the error must surface ─────────────────────────
def test_the_first_failure_with_no_cache_still_raises(main_module, monkeypatch):
    """A blank success would hide that the database is unreachable."""
    main = main_module

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("shared Postgres link busy")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)

    with pytest.raises(TimeoutError):
        main._dashboard_payload_resilient(False, False)


# ── 4. THE SECURITY TEST: the cache must never cross a grant boundary ──────
def test_a_public_caller_can_never_be_served_the_admin_payload(
        main_module, monkeypatch):
    """A cache keyed by anything but the grant pair would leak the CRM.

    Prime BOTH variants, then fail the builder and ask as the PUBLIC. If the
    two variants ever shared a slot, the public caller would be handed the
    admin payload — off-chain Stripe and CRM data that is deliberately not
    curl-able, and the exact reason the two grants are passed separately.
    """
    main = main_module
    _fake_payload(monkeypatch, main)

    admin_live = main._dashboard_payload_resilient(True, True)
    public_live = main._dashboard_payload_resilient(False, False)
    assert admin_live["crm"] == {"leads": 7}, "precondition: admin saw the CRM"
    assert public_live.get("crm") is None, "precondition: public did not"

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("down")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)

    public = main._dashboard_payload_resilient(False, False)

    assert public["stale"] is True
    assert public.get("crm") is None, (
        "a public fallback returned the admin CRM section — the cache is "
        "keyed too loosely and is leaking off-chain data")

    # And the admin's own fallback still carries what the admin is allowed.
    admin = main._dashboard_payload_resilient(True, True)
    assert admin["stale"] is True
    assert admin["crm"] == {"leads": 7}


def test_the_two_grants_use_separate_cache_slots(main_module, monkeypatch):
    main = main_module
    _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(False, False)
    main._dashboard_payload_resilient(True, True)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        keys = set(main._DASHBOARD_LAST_GOOD)

    assert (False, False) in keys
    assert (True, True) in keys
    assert len(keys) >= 2, "the grant variants share a cache slot"


# ── 5. a fallback must not corrupt what is cached for later callers ────────
def test_serving_a_fallback_does_not_overwrite_the_cached_payload(
        main_module, monkeypatch):
    """The fallback ADDS markers; it must not store its own output back.

    If it did, every later request would inherit `stale: true` and an ever
    growing age, and the board could never report live again.
    """
    main = main_module
    _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(False, False)

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("down")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)
    main._dashboard_payload_resilient(False, False)
    main._dashboard_payload_resilient(False, False)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        cached, _at = main._DASHBOARD_LAST_GOOD[(False, False)]

    assert "stale" not in cached, (
        "the fallback wrote its markers into the cache; the board can now "
        "never report live data again")
    assert "stale_age_seconds" not in cached


def test_a_recovered_build_reports_live_again(main_module, monkeypatch):
    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    def explode(include_crm=False, include_sales_detail=False):
        raise TimeoutError("down")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", explode)
    assert main._dashboard_payload_resilient(False, False)["stale"] is True

    _fake_payload(monkeypatch, main)          # the database answers again
    assert main._dashboard_payload_resilient(False, False)["stale"] is False, (
        "the board stayed stuck on stale after the database recovered")


# ── 6. the page must not paint LIVE over a fallback payload ────────────────
def test_the_page_checks_stale_before_it_declares_live():
    """A 200 carrying a fallback must not be rendered as LIVE.

    The server marks staleness with `stale: true`, but the page only ever
    checked `r.ok` — and a fallback response IS 200. Without an explicit
    check, the board would print LIVE over figures that are hours old, which
    is the one lie the whole mechanism exists to prevent.

    Asserted structurally, and on the ORDER: the stale branch has to come
    before the line that sets the live badge, and it has to stop there.
    """
    from pathlib import Path

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    stale_at = html.find("d.stale === true")
    live_at = html.find("b.className = 'badge live'")

    assert stale_at != -1, (
        "the page never checks d.stale — a fallback payload renders as LIVE")
    assert live_at != -1, "precondition: the live badge assignment moved"
    assert stale_at < live_at, (
        "the stale check runs AFTER the page declares LIVE, so stale data "
        "is shown as current")

    # The branch must actually stop, not fall through into the live path.
    branch = html[stale_at:live_at]
    assert "return;" in branch, (
        "the stale branch does not return, so execution continues into the "
        "success path and overwrites the marker with LIVE")
    assert "ЗАСТАРЕЛИ" in branch, (
        "the stale branch does not label the data for the reader")
