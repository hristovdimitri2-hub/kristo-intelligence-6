"""Payment attempts — the funnel's missing middle (07.11.2026).

THE DEFECT THIS FILE PINS. The funnel derived everything from `request_log`:
402 = a challenge, 200 = a paid retry. But the paywall uses the status code to
say something the funnel then threw away:

    402  NO credential was presented  -> the canonical challenge (main.py:4127)
    401  a credential WAS presented and we refused it (main.py:4092)
    425  a settlement is on-chain, our node has not caught up (main.py:4076)
    200  paid

So the 402 count already IS abandonment, and the number that was missing is the
SPLIT of the 401s. `401` covers two opposite facts:

    "your signature was wrong"            -> routine; the buyer will fix it
    "we could not take your valid payment"-> a sale WE lost

The second is the one worth waking someone for, and on 07.11 — 1,779 challenges,
0 payments — the board could not say whether any of them existed.

`payment_attempts` records what happened to a credential that WAS presented.
Abandonment is NOT stored: it is the 402 count, read directly, so it cannot
drift and cannot be under-counted by subtracting the buyers who tried.

AN EARLIER DRAFT OF THIS CODE SUBTRACTED `rejected + settle_failed` FROM THE 402
COUNT. That was wrong — those outcomes answer 401, so they were never inside the
402 count, and the subtraction under-counted abandonment by exactly the number
of people who tried. `tests/test_rail_payment_attempts.py` caught it. The tests
below encode the corrected model, including the reconciliation that would catch
a rail call site which stops recording.
"""

import re
import sqlite3

import pytest


def _render_funnel_source():
    """The body of `renderFunnel`, cut at the function's own closing brace.

    Sliced by STRUCTURE rather than by a character count. The first version used
    `[:3600]`, and adding one block to the function pushed the text these tests
    look for past the limit — so a guard failed for the wrong reason, reporting a
    missing sentence that was still there. A fixed offset measures the size of
    the function, not the presence of the thing being asserted.
    """
    from pathlib import Path
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    start = html.find("function renderFunnel(")
    assert start >= 0, "renderFunnel has been renamed or removed"
    # Walk to the matching closing brace at the same nesting depth.
    depth = 0
    for i in range(html.index("{", start), len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth == 0:
                return html[start:i + 1]
    raise AssertionError("renderFunnel has unbalanced braces")


@pytest.fixture()
def store(tmp_path):
    from integrations.dashboard_store import (DashboardStore,
                                              PAYMENT_ATTEMPTS_SINCE_KEY)
    s = DashboardStore(tmp_path / "dashboard_state.db")
    # Backdate the recording epoch. Production writes it at deploy time, which
    # leaves TODAY's attempt split only partially observed. These tests are about
    # the arithmetic, so they run from the day after a normal deploy; the
    # fresh-epoch behaviour has its own test.
    s.history.set_durable_meta(PAYMENT_ATTEMPTS_SINCE_KEY,
                               "2020-01-01T00:00:00+00:00")
    return s


def _served(store):
    """`requests_summary()` once the all-time snapshot has been built.

    The unbounded panels are read by a background pass and parked, so a store
    that has only just recorded its rows honestly reports them unread. Building
    the snapshot first is what makes these assertions about the numbers rather
    than about the parking.
    """
    target = getattr(store, "history", store)
    target.refresh_requests_snapshot(runner=target._run)
    return store.requests_summary()


def _rows(store, sql, params=()):
    """Read rows out of `_run`, which returns `(rows, rowcount)`."""
    target = getattr(store, "history", store)
    return target._run(sql, params, "all")[0] or []


# ── the table exists and is usable ───────────────────────────────────────────

def test_the_attempt_table_is_created_on_a_fresh_store(store):
    """A missing table turns a correctly provisioned database into HTTP 500 for
    the whole dashboard — the CRM lesson. It must exist from boot."""
    rows = _rows(store, "SELECT name FROM sqlite_master WHERE type='table' "
                        "AND name=?", ("payment_attempts",))
    assert rows, "payment_attempts was never created"


def test_a_recorded_attempt_is_stored_with_its_outcome(store):
    store.record_payment_attempt("/api/v1/signal", "settle_failed",
                                 payer="0xABC", amount_usdc=0.003,
                                 detail="facilitator refused")
    rows = _rows(store, "SELECT path, outcome, payer, amount_usdc, detail "
                        "FROM payment_attempts")
    assert len(rows) == 1
    r = dict(rows[0])
    assert r["path"] == "/api/v1/signal"
    assert r["outcome"] == "settle_failed"
    assert r["payer"] == "0xABC"
    assert r["detail"] == "facilitator refused"


# ── abandonment is the 402 count, full stop ─────────────────────────────────

def test_abandonment_is_the_402_count(store):
    """Three 402s, three walked away. No attempt data needed."""
    for _ in range(3):
        store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["challenges_today"] == 3
    assert f["abandoned_today"] == 3


def test_a_buyer_who_tried_does_not_reduce_abandonment(store):
    """THE corrected behaviour, and the bug the rail tests caught.

    A payload that arrives and fails settlement answers 401 — NOT 402. So it was
    never in the 402 count, and subtracting it would claim two people walked away
    when three did.
    """
    for _ in range(3):
        store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    # The buyer who tried got a 401, not a 402.
    store.record_request("GET", "/api/v1/signal", "api", 401, user_agent="node")
    store.record_payment_attempt("/api/v1/signal", "settle_failed",
                                 payer="0xPAYER", amount_usdc=0.003,
                                 detail="nonce already used")

    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["challenges_today"] == 3, "only the 402s are challenges"
    assert f["settle_failed_today"] == 1, "the presented payload was recorded"
    assert f["abandoned_today"] == 3, (
        "the buyer who tried answered 401 and was never among the 402s; "
        "subtracting them under-counts abandonment")


def test_a_rejected_payload_does_not_reduce_abandonment(store):
    """A malformed signature also answers 401, so the 402 count is untouched."""
    for _ in range(3):
        store.record_request("GET", "/api/stats", "api", 402, user_agent="node")
    store.record_request("GET", "/api/stats", "api", 401, user_agent="node")
    store.record_payment_attempt("/api/stats", "rejected",
                                 detail="verification failed")
    f = _served(store)["funnel"]["/api/stats"]
    assert f["challenges_today"] == 3
    assert f["rejected_today"] == 1
    assert f["abandoned_today"] == 3


def test_a_sale_does_not_reduce_abandonment(store):
    """A settled payment answers 200 — never inside the 402 count either."""
    store.record_request("GET", "/api/sales", "api", 402, user_agent="node")
    store.record_request("GET", "/api/sales", "api", 200, user_agent="node")
    store.record_payment_attempt("/api/sales", "settled",
                                 payer="0xP", amount_usdc=0.005,
                                 tx_hash="0xdead")
    f = _served(store)["funnel"]["/api/sales"]
    assert f["challenges_today"] == 1
    assert f["settled_today"] == 1
    assert f["abandoned_today"] == 1, (
        "the settled call was a 200; subtracting it would claim zero "
        "abandonment on a route that had one")


def test_an_authorised_attempt_does_not_reduce_abandonment(store):
    """`authorised` is a credential that verified with no determined outcome.

    Its response is 401/425, not 402 — so it is likewise outside the count.
    """
    store.record_request("GET", "/api/sales", "api", 402, user_agent="node")
    store.record_request("GET", "/api/sales", "api", 425, user_agent="node")
    store.record_payment_attempt("/api/sales", "authorised", payer="0xP")
    f = _served(store)["funnel"]["/api/sales"]
    assert f["challenges_today"] == 1
    assert f["authorised_today"] == 1
    assert f["abandoned_today"] == 1


def test_abandonment_is_never_negative_or_invented(store):
    """A route with attempts but no 402s reports zero abandonment, not -N."""
    store.record_payment_attempt("/api/v1/whaleflow", "settle_failed")
    store.record_payment_attempt("/api/v1/whaleflow", "rejected")
    f = _served(store)["funnel"]["/api/v1/whaleflow"]
    assert f["abandoned_today"] == 0
    assert f["abandoned_today"] >= 0


def test_a_settlement_is_recorded_once_per_transaction(store):
    """THE regression guard for the double-counted sale.

    `record_payment_attempt(..., "settled", ...)` is called BEFORE the C1 replay
    claim in `_try_consume_standard_payment`, deliberately: a settlement our depth
    gate answers 425 is still a buyer who paid, and the depth gate runs later.

    But a REPLAYED request re-enters the whole rail and reaches that line again,
    and C1 refuses it only afterwards. So the recording cannot rely on C1 having
    run first — measured, one payment replayed twice produced THREE `settled`
    rows, inflating exactly the figure this panel exists to make trustworthy.

    The store therefore records a settlement once per tx hash. The other outcomes
    are events, not facts about a transaction, so they are always recorded.
    """
    for _ in range(3):
        store.record_payment_attempt("/api/stats", "settled", payer="0xP",
                                     amount_usdc=0.005, tx_hash="0xabc123")
    rows = _rows(store, "SELECT COUNT(*) AS n FROM payment_attempts "
                        "WHERE outcome = 'settled'")
    assert int(dict(rows[0])["n"]) == 1, (
        "the same settlement was counted as multiple sales — a replay inflates "
        "the funnel's paid figure")

    f = _served(store)["funnel"]["/api/stats"]
    assert f["settled_today"] == 1
    assert f["presented_today"] == 1


def test_different_settlements_are_still_counted_separately(store):
    """The counterpart: idempotency must key on the TRANSACTION, not on the
    route. Two buyers paying on one route is two sales."""
    store.record_payment_attempt("/api/stats", "settled", tx_hash="0xaaa")
    store.record_payment_attempt("/api/stats", "settled", tx_hash="0xbbb")
    f = _served(store)["funnel"]["/api/stats"]
    assert f["settled_today"] == 2


def test_a_settlement_with_no_hash_is_still_recorded(store):
    """A settlement the facilitator reported without a usable hash must not be
    silently dropped — that would lose a real sale. Only DE-DUPLICATION needs a
    hash; recording does not."""
    store.record_payment_attempt("/api/sales", "settled", tx_hash="")
    store.record_payment_attempt("/api/sales", "settled", tx_hash="")
    rows = _rows(store, "SELECT COUNT(*) AS n FROM payment_attempts "
                        "WHERE outcome = 'settled'")
    assert int(dict(rows[0])["n"]) == 2, (
        "a hashless settlement was dropped or wrongly de-duplicated")


def test_repeated_rejections_are_all_recorded(store):
    """Only `settled` is de-duplicated. A buyer retrying a bad signature is
    still a buyer trying, and the panel should show the attempts."""
    for _ in range(3):
        store.record_payment_attempt("/api/v1/signal", "rejected",
                                     detail="signature_mismatch")
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["rejected_today"] == 3


# ── the reconciliation: every credential must have a row ────────────────────

def test_every_presented_credential_is_accounted_for(store):
    """One 401 in the log, one attempt row. The gap is published, and is zero."""
    store.record_request("GET", "/api/v1/signal", "api", 401, user_agent="node")
    store.record_payment_attempt("/api/v1/signal", "rejected")
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["credentials_today"] == 1, "request_log saw a credential"
    assert f["presented_today"] == 1, "the rail recorded it"
    assert f["unrecorded_today"] == 0


def test_a_credential_with_no_attempt_row_is_published_as_a_gap(store):
    """THE self-check. A rail call site that stops recording would flatten this
    panel silently; instead the gap becomes visible."""
    for _ in range(3):
        store.record_request("GET", "/api/stats", "api", 401, user_agent="node")
    store.record_payment_attempt("/api/stats", "rejected")     # only one recorded
    f = _served(store)["funnel"]["/api/stats"]
    assert f["credentials_today"] == 3
    assert f["presented_today"] == 1
    assert f["unrecorded_today"] == 2, (
        "two credentials reached the rail and left no trace, which means a call "
        "site stopped recording")


def test_a_425_in_flight_counts_as_a_presented_credential(store):
    """A settlement that is on-chain but not yet deep enough answers 425. The
    buyer paid; `request_log` must count them as having presented."""
    store.record_request("GET", "/api/v1/whaleflow", "api", 425, user_agent="node")
    store.record_payment_attempt("/api/v1/whaleflow", "settled",
                                 tx_hash="0xabc")
    f = _served(store)["funnel"]["/api/v1/whaleflow"]
    assert f["credentials_today"] == 1
    assert f["unrecorded_today"] == 0


def test_the_gap_is_not_reported_before_the_recording_window(store):
    """On deploy day the morning's 401s have no rows for a good reason. Calling
    that a defect would be crying wolf on every release."""
    from integrations.dashboard_store import PAYMENT_ATTEMPTS_SINCE_KEY
    store.history.set_durable_meta(PAYMENT_ATTEMPTS_SINCE_KEY,
                                   "2099-01-01T00:00:00+00:00")
    store.record_request("GET", "/api/stats", "api", 401, user_agent="node")
    f = _served(store)["funnel"]["/api/stats"]
    assert f["unrecorded_today"] is None, (
        "an unmeasurable window must not be reported as a recording defect")


# ── the honesty rules ────────────────────────────────────────────────────────

def test_an_unreadable_attempt_table_still_reports_abandonment(store, monkeypatch):
    """Abandonment comes from `request_log`, so it survives a broken attempt
    table — only the split goes unknown.

    The failure is injected at `_run`, on the real code path, rather than by
    stubbing a method: the funnel issues this SQL through the budgeted `q()`
    wrapper, and a test that bypasses that wrapper would not notice the day the
    wrapper stops catching the error.
    """
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    target = getattr(store, "history", store)
    real_run = target._run

    def picky(sql, params=(), fetch=""):
        if "payment_attempts" in sql:
            raise sqlite3.OperationalError("no such table: payment_attempts")
        return real_run(sql, params, fetch)

    monkeypatch.setattr(target, "_run", picky)
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["abandoned_today"] == 2, (
        "abandonment does not depend on the attempt table and must not be lost "
        "when it breaks")
    for field in ("presented_today", "authorised_today", "settled_today",
                  "rejected_today", "settle_failed_today", "unrecorded_today"):
        assert f[field] is None, (
            f"{field} reported {f[field]!r} while the table could not be read")


def test_an_unreadable_request_log_reports_abandonment_as_none(store, monkeypatch):
    """The other direction: if the 402 count itself could not be read, then
    abandonment is unknown — not zero."""
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    target = getattr(store, "history", store)
    real_run = target._run

    def picky(sql, params=(), fetch=""):
        if "status_code = 402" in sql:
            raise sqlite3.OperationalError("statement timeout")
        return real_run(sql, params, fetch)

    monkeypatch.setattr(target, "_run", picky)
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["abandoned_today"] is None, (
        "an unread 402 count must not be published as zero abandonment")
    assert f["challenges_today"] is None


def test_readable_and_empty_are_different_answers(store):
    """The distinction the whole codebase keeps insisting on."""
    target = getattr(store, "history", store)
    assert target.payment_attempts_readable() is True, (
        "an empty but readable table must report readable")
    assert target.payment_attempt_rows() == []


def test_a_broken_attempt_read_reports_unreadable(store, monkeypatch):
    target = getattr(store, "history", store)

    def boom(*a, **k):
        raise sqlite3.OperationalError("no such table: payment_attempts")

    monkeypatch.setattr(target, "_run", boom)
    assert target.payment_attempts_readable() is False
    assert target.payment_attempt_rows() is None, (
        "a failed read returned a list, which the caller cannot tell apart "
        "from a table that was read and is genuinely empty")


def test_an_unrecognised_outcome_is_recorded_as_rejected(store):
    """A typo must not silently create a fifth state that corrupts aggregates."""
    store.record_payment_attempt("/api/v1/signal", "soomething_else")
    rows = _rows(store, "SELECT outcome FROM payment_attempts")
    assert [dict(r)["outcome"] for r in rows] == ["rejected"]


def test_a_blank_outcome_is_recorded_as_rejected(store):
    store.record_payment_attempt("/api/v1/signal", "")
    rows = _rows(store, "SELECT outcome FROM payment_attempts")
    assert [dict(r)["outcome"] for r in rows] == ["rejected"]


def test_recording_never_raises(store, monkeypatch):
    """Telemetry must not be able to fail a payment."""
    target = getattr(store, "history", store)

    def boom(*a, **k):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(target, "_run", boom)
    store.record_payment_attempt("/api/v1/signal", "settled")  # must not raise


def test_the_outcome_vocabulary_matches_what_the_rail_records():
    """The rail names its outcomes as strings; a rename here would silently make
    every attempt fall into `rejected` and every lost-sale figure wrong."""
    from integrations.dashboard_store import PAYMENT_ATTEMPT_OUTCOMES
    assert set(PAYMENT_ATTEMPT_OUTCOMES) == {
        "authorised", "rejected", "settle_failed", "settled"}
    assert "settled" in PAYMENT_ATTEMPT_OUTCOMES


# ── the window ───────────────────────────────────────────────────────────────

def test_the_day_window_separates_today_from_all_time(store):
    """An attempt recorded with an old timestamp must not appear in today."""
    target = getattr(store, "history", store)
    target._run(
        """INSERT INTO payment_attempts (ts, path, outcome, payer,
                                          amount_usdc, detail, tx_hash)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("2020-01-01T00:00:00+00:00", "/api/v1/signal", "settle_failed",
         "", 0.0, "old", ""),
    )
    store.record_payment_attempt("/api/v1/signal", "rejected")
    rows_all = target.payment_attempt_rows()
    assert sum(int(r["n"]) for r in rows_all) == 2, "all-time missed a row"
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["presented_total"] == 2, "all-time total should hold both"
    assert f["presented_today"] == 1, (
        "the 2020 row was counted as today, so the window filter is not applied")
    assert f["settle_failed_today"] == 0


def test_the_epoch_is_recorded_once_and_never_moved(tmp_path):
    """The window may only ever grow. A redeploy that reset it would silently
    shrink what the platform claims to have measured."""
    from integrations.dashboard_store import (DashboardStore,
                                              PAYMENT_ATTEMPTS_SINCE_KEY)
    db = tmp_path / "reopen.db"
    first = DashboardStore(db)
    epoch = first.history.payment_attempts_since()
    assert epoch, "a fresh store recorded no epoch"

    second = DashboardStore(db)          # simulates a restart / redeploy
    assert second.history.payment_attempts_since() == epoch, (
        "reopening the store moved the measurement window")

    second.history.set_durable_meta(PAYMENT_ATTEMPTS_SINCE_KEY,
                                    "2020-01-01T00:00:00+00:00")
    third = DashboardStore(db)
    assert third.history.payment_attempts_since() == "2020-01-01T00:00:00+00:00", (
        "the schema pass overwrote an existing epoch — INSERT ... ON CONFLICT "
        "DO NOTHING is what prevents this, and without it every redeploy would "
        "quietly shrink the window the platform claims to have measured")


def test_recording_an_attempt_does_not_move_the_epoch(store):
    before = store.history.payment_attempts_since()
    store.record_payment_attempt("/api/v1/signal", "settled")
    store.record_payment_attempt("/api/v1/signal", "rejected")
    assert store.history.payment_attempts_since() == before


def test_a_store_that_began_recording_today_still_reconciles_today(tmp_path):
    """THE regression guard for the deploy-day bug.

    `attempts_since` is written as a full ISO TIMESTAMP and `today` is a DATE. The
    check compared them as STRINGS, so

        "2026-11-07T17:01:17+00:00" <= "2026-11-07"   ->   False

    because 'T' sorts after the empty string. The self-check was therefore
    silently DISABLED on the very day it was deployed — the only day it exists
    for, since on every later day the epoch is comfortably in the past — and then
    armed itself the next morning, reconciling hours it had never covered.

    A fresh store IS the deploy-day case: its epoch is now. Credentials that
    arrived after the epoch must be reconciled; abandonment stays exact either
    way because it never reads this table.
    """
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "fresh.db")
    for _ in range(2):
        store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    # One credential arrived AFTER the epoch and the rail recorded it; two did
    # not. On a fresh store both are post-epoch, so the gap is 1 and it is real.
    store.record_request("GET", "/api/v1/signal", "api", 401, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 401, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 401, user_agent="node")
    store.record_payment_attempt("/api/v1/signal", "rejected")

    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["abandoned_today"] == 2, "abandonment is read off the 402s"
    assert f["measured_since"], "the window must be published so the page can date it"
    assert f["unrecorded_today"] == 2, (
        "the reconciliation is disabled on the day of the deploy — the epoch is a "
        "timestamp and 'today' is a date, and comparing them as strings is always "
        "False. Got %r, expected 2 (3 credentials, 1 recorded)."
        % (f["unrecorded_today"],))


# ── the funnel still answers its original question ───────────────────────────

def test_the_original_402_to_paid_numbers_are_unchanged(store):
    """The new fields are additive: nothing this table added may change what the
    funnel already reported."""
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 200, user_agent="node")
    f = _served(store)["funnel"]["/api/v1/signal"]
    assert f["challenges_today"] == 3
    assert f["paid_today"] == 1
    assert f["challenges_total"] == 3
    rate = round(100.0 * f["paid_today"] / f["challenges_today"], 1)
    assert rate == 33.3


def test_the_attempt_read_happens_before_the_budget_is_spent(store, monkeypatch):
    """THE regression guard for the first live deploy of this panel.

    Every `q()` in `requests_summary` spends from ONE 6-second budget, and the
    heavy all-time scans over `request_log` spend all of it. This panel was
    originally read next to the funnel it feeds — logically the right place, and
    last in execution — so on the first deploy it was reported
    `payment_attempts:out_of_budget` while being the cheapest read in the method.

    `out_of_budget` is the OPPOSITE of a slow query: it means the panel never
    ran. So the marker said "skipped", the board rendered the split as unread,
    and the cause was ordering, not cost.

    This pins the ORDER, not the SQL: `payment_attempts` must be issued before
    the first unbounded aggregate over `request_log`.
    """
    issued = []
    target = getattr(store, "history", store)
    real_run = target._run

    def record(sql, params=(), fetch=""):
        issued.append(" ".join(sql.split()))
        return real_run(sql, params, fetch)

    monkeypatch.setattr(target, "_run", record)
    store.requests_summary()

    attempt_at = next((i for i, s in enumerate(issued)
                       if "FROM payment_attempts" in s), None)
    assert attempt_at is not None, (
        "the attempt split was never read on the request path — the panel is "
        "silently absent rather than unread")

    # EVERY request_log read, not just the last one.
    #
    # The first version of this guard compared against `max(log_at)` — the last
    # request_log read on the path, which is the funnel query. That made it
    # vacuous: a "half-fixed" placement just BEFORE the funnel still passed,
    # while sitting after four of the five log reads and therefore still at the
    # mercy of the budget those four spend. Measured issuance order then was
    # attempt at 3 and log reads at [0, 1, 2, 4, 6]; the assertion `3 < 6` held
    # for the very ordering it was written to forbid.
    #
    # The panel is the CHEAPEST read in the method (an indexed `path IN` against
    # a table of attempts, not of traffic), so the honest requirement is that no
    # request_log read precedes it at all.
    log_at = [i for i, s in enumerate(issued) if "FROM request_log" in s]
    assert log_at, "no request_log read ran; the guard is moot"
    earlier = [i for i in log_at if i < attempt_at]
    assert not earlier, (
        "the attempt split is read at position %d, AFTER %d request_log read(s) "
        "at %r. Every `q()` spends from ONE 6-second budget, and the reads over "
        "request_log are the expensive ones — so this panel, the cheapest here, "
        "gets reported out_of_budget ('never ran') on a live deploy. Read it "
        "before every request_log panel."
        % (attempt_at, len(earlier), earlier))


def test_every_funnel_route_exposes_the_missing_middle(store):
    """A route that lost the new fields would render a blank where the answer to
    'why is nobody paying' is supposed to be."""
    from integrations.dashboard_store import FUNNEL_ROUTES
    f = _served(store)["funnel"]
    required = ("presented_today", "presented_total", "authorised_today",
                "settled_today", "settled_total", "rejected_today",
                "settle_failed_today", "abandoned_today", "abandoned_total",
                "credentials_today", "unrecorded_today",
                "measured_since", "challenges_since")
    for path in FUNNEL_ROUTES:
        assert path in f, f"{path} vanished from the funnel"
        for field in required:
            assert field in f[path], f"{path} is missing {field}"


# ── the page has to show it ──────────────────────────────────────────────────
#
# Data nobody renders is data nobody has. These guard the panel itself, in the
# same style as the existing degraded-panel and missing-number guards: a reader
# must not be able to mistake an unmeasured figure for a measured one.

def test_the_page_shows_the_middle_of_the_funnel():
    """The 402 → paid cells alone are the defect; the page must carry the split."""
    render = _render_funnel_source()
    for field in ("presented_today", "settle_failed_today", "rejected_today",
                  "abandoned_today", "measured_since", "unrecorded_today"):
        assert field in render, (
            f"renderFunnel ignores {field}, so the reason nobody pays is still "
            f"invisible on the board")


def test_the_page_does_not_print_a_number_for_an_unmeasured_split():
    """On deploy day the split is partial. Rendering `|| 0` there would state
    that nobody walked away, or that the rail is broken."""
    render = _render_funnel_source()
    assert "presented === null" in render or "presented == null" in render, (
        "renderFunnel has no null branch, so an unmeasured split renders as a "
        "number")
    assert "изоставянето се мери от" in render or "се мери от" in render, (
        "an unmeasured window must say when measurement began, not just show a dash")


def test_the_page_says_when_the_attempt_read_failed():
    """`опитите не се прочетоха` and `никой не опита` are different news."""
    render = _render_funnel_source()
    assert "опитите не се прочетоха" in render, (
        "a failed attempt read must be labelled as a failed read")


def test_the_styles_used_in_the_funnel_exist():
    """`.bad`/`.warn` are only meaningful with a rule behind them, and `.warn` is
    scoped to `.offchain-box` elsewhere — an unstyled span reads as ordinary
    text, which is how a lost sale ends up looking like a footnote."""
    from pathlib import Path
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    assert "#funnel-box .bad" in html, (
        "the funnel uses class `bad` with no CSS rule, so a settlement we failed "
        "to take is not distinguishable from ordinary text")
    assert "#funnel-box .warn" in html, "the funnel uses class `warn` with no rule"
