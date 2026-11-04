"""The dashboard's plain-language summary: the owner's four questions.

The owner's report was not "the numbers are wrong" but "I cannot tell what they
mean" — when a sale happened, on which day, who paid, and whether the caller was
a person or a bot. The numbers were all present and none of them answered those
questions in words.

These tests guard the answers, and one property above all: the summary is derived
from the same `sales`/`requests`/`clients` objects as the sections below it, so it
can never disagree with the tables it summarises. A summary that drifts from its
own tables is worse than no summary, because it is the part that gets read.
"""
import datetime as dt
import re

import main

UTC = dt.timezone.utc


def _iso(days_ago: int, hour: int = 12) -> str:
    """A timestamp `days_ago` days before today, at a fixed hour."""
    day = dt.datetime.now(UTC).date() - dt.timedelta(days=days_ago)
    return dt.datetime(day.year, day.month, day.day, hour, tzinfo=UTC).isoformat()


# ── who is calling: a person, an AI agent, or a robot ────────────────────────

def test_headless_chrome_is_a_robot_not_a_person():
    """The bug this test was written from.

    `HeadlessChrome/153.0` fell through to the browser rule, so automation was
    counted as a human reader - the one number the owner would act on. A headless
    browser is a program driving a browser.
    """
    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) HeadlessChrome/153.0.8010.12 Safari/537.36")
    assert main._caller_kind(ua) == "Търсачка или робот"


def test_every_caller_kind_is_recognised_from_a_real_user_agent():
    cases = {
        "claude-code/2.1.310 (cli)": "AI агент",
        "Render/1.0": "Наш собствен монитор",
        "Werkzeug/3.1.8": "Наш собствен монитор",
        # Third-party liveness checkers, exactly as they appeared on the live
        # page: 59k requests that were filed under "Друго" and CarbonMonitor
        # that was wrongly filed as ours.
        "SentinelOracle/0.1 (+https://glimind.com/opt-out; liveness-only, "
        "never invokes tools)": "Външен монитор",
        "mako-pulse-prober/0.1": "Външен монитор",
        "mcp-health-probe/0.1 (read-only; initialize+tools/list only)":
            "Външен монитор",
        "CarbonMonitor/0.1 healthcheck (+https://carbon-cashmere.de)":
            "Външен монитор",
        "Googlebot/2.1 (+http://www.google.com/bot.html)": "Търсачка или робот",
        "curl/8.4.0": "Програмен клиент",
        "python-requests/2.31.0": "Програмен клиент",
        "Go-http-client/1.1": "Програмен клиент",
        # Node's fetch sends the bare word "node" - measured live at 112k
        # requests sitting in "Друго" before this rule existed.
        "node": "Програмен клиент",
        "Mozilla/5.0 (Windows NT 10.0) Chrome/120.0 Safari/537.36":
            "Браузър (човек)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15":
            "Браузър (човек)",
        "SomethingNobodyHasSeen/1.0": "Друго",
        "": "Неизвестен",
    }
    wrong = {ua: (main._caller_kind(ua), want) for ua, want in cases.items()
             if main._caller_kind(ua) != want}
    assert not wrong, wrong


def test_a_browser_wins_over_a_bot_word_only_when_it_really_is_a_browser():
    """Order matters: the specific rules precede the browser rule.

    Almost every bot claims to be Mozilla, so a "bot" that also says Mozilla must
    still be a robot, while a plain browser must not be dragged into the bot
    bucket by an unrelated substring.
    """
    assert main._caller_kind("Mozilla/5.0 compatible Googlebot/2.1") == \
        "Търсачка или робот"
    assert main._caller_kind("Mozilla/5.0 (X11) Firefox/121.0") == \
        "Браузър (човек)"


def test_the_caller_split_adds_up_to_the_requests_it_was_given():
    """The split must account for every request it was handed, not just some."""
    rows = [{"user_agent": "claude-code/2.1.310", "n": 100},
            {"user_agent": "curl/8.4.0", "n": 30},
            {"user_agent": "Mozilla/5.0 Chrome/120", "n": 5}]
    split = main._human_or_bot(rows)
    assert sum(item["requests"] for item in split) == 135
    assert split[0]["kind"] == "AI агент"          # biggest first
    assert [item["requests"] for item in split] == sorted(
        [item["requests"] for item in split], reverse=True)


def test_the_caller_split_survives_junk_rows():
    for rows in ([], None, [{"n": 5}], [{"user_agent": None, "n": None}]):
        split = main._human_or_bot(rows)
        assert isinstance(split, list)
        assert all(isinstance(item["requests"], int) for item in split)


# ── when: a timestamp in the words a person says ─────────────────────────────

def test_ago_words_says_when_in_plain_bulgarian():
    assert main._ago_words(_iso(0, hour=0)) in ("преди", "току-що") or \
        main._ago_words(dt.datetime.now(UTC).isoformat()) == "току-що"
    assert main._ago_words(dt.datetime.now(UTC).isoformat()) == "току-що"
    assert main._ago_words(
        (dt.datetime.now(UTC) - dt.timedelta(minutes=5)).isoformat()
    ) == "преди 5 мин"
    assert main._ago_words(
        (dt.datetime.now(UTC) - dt.timedelta(hours=3)).isoformat()
    ) == "преди 3 ч"
    assert main._ago_words(
        (dt.datetime.now(UTC) - dt.timedelta(days=1)).isoformat()
    ) == "вчера"
    assert main._ago_words(
        (dt.datetime.now(UTC) - dt.timedelta(days=4)).isoformat()
    ) == "преди 4 дни"


def test_ago_words_never_raises_on_a_broken_timestamp():
    for broken in (None, "", "not a date", 12345, [], {}):
        assert isinstance(main._ago_words(broken), str)


# ── how many: days, weeks, and the comparison between two weeks ──────────────

def test_the_daily_series_still_defaults_to_seven_days():
    """The existing caller and its chart must not change under it."""
    assert len(main._daily_sales_series([])) == 7
    assert len(main._daily_sales_series([], days=7)) == 7
    assert len(main._daily_sales_series([], days=28)) == 28


def test_the_series_ends_on_today_and_has_no_gaps():
    series = main._daily_sales_series([], days=28)
    today = dt.datetime.now(UTC).date()
    assert series[-1]["date"] == today.isoformat()
    assert series[0]["date"] == (today - dt.timedelta(days=27)).isoformat()
    days = [row["date"] for row in series]
    assert days == sorted(days)
    assert len(set(days)) == 28


def _summary(sales_history, total_count=None, total_usdc=None,
             top_user_agents=None, clients=None, hourly=None):
    sales = {"history": sales_history,
             "total_count": (total_count if total_count is not None
                             else len(sales_history)),
             "total_usdc": (total_usdc if total_usdc is not None
                            else sum(r["amount_usdc"] for r in sales_history))}
    requests = {"top_user_agents": top_user_agents or [],
                "hourly": hourly or []}
    return main._plain_summary(sales, requests, clients or {})


def test_this_week_is_compared_with_the_week_before_it():
    """The whole point of the 28-day window.

    "тази седмица" is the calendar week starting Monday, which is what a person
    means by it; the week before it is the seven days immediately preceding.
    """
    # One sale today, and two inside the previous calendar week. Both are placed
    # relative to today so the assertion never depends on the calendar date the
    # suite happens to run on.
    today = dt.datetime.now(UTC).date()
    this_week_start = today - dt.timedelta(days=today.weekday())
    prev_week_day = this_week_start - dt.timedelta(days=3)

    history = [
        {"ts": dt.datetime(today.year, today.month, today.day, 9,
                           tzinfo=UTC).isoformat(), "amount_usdc": 0.005},
        {"ts": dt.datetime(prev_week_day.year, prev_week_day.month,
                           prev_week_day.day, 9,
                           tzinfo=UTC).isoformat(), "amount_usdc": 0.003},
        {"ts": dt.datetime(prev_week_day.year, prev_week_day.month,
                           prev_week_day.day, 10,
                           tzinfo=UTC).isoformat(), "amount_usdc": 0.003},
    ]
    summary = _summary(history)

    assert summary["this_week"]["count"] == 1
    assert summary["last_week"]["count"] == 2
    assert summary["week_change"]["delta"] == -1
    assert "по-малко" in summary["week_change"]["words"]
    assert summary["last_week"]["usdc"] == 0.006
    # The two windows must not overlap or leave a hole between them.
    assert summary["last_week"]["to"] < summary["this_week"]["from"]


def test_a_week_with_no_sales_before_it_reports_no_percentage():
    """0 → 1 is not "+100%". Dividing by zero would print "None%" or crash."""
    history = [{"ts": dt.datetime.now(UTC).isoformat(), "amount_usdc": 0.003}]
    summary = _summary(history)
    if summary["this_week"]["count"] > 0 and summary["last_week"]["count"] == 0:
        assert summary["week_change"]["percent"] is None
        assert summary["week_change"]["words"] == "първите продажби"


def test_an_empty_history_produces_a_complete_summary_not_a_crash():
    summary = _summary([])
    assert summary["last_sale"] is None
    assert summary["today"]["count"] == 0
    assert summary["week_change"]["words"] == "няма продажби"
    assert summary["all_time"]["count"] == 0
    assert summary["best_day"] is None
    assert summary["busiest_hour"] is None
    assert len(summary["sales_by_day"]) == 28


def test_best_day_ignores_the_zero_days():
    """A day with no sales must never be reported as the best day."""
    history = [{"ts": _iso(2), "amount_usdc": 0.005},
               {"ts": _iso(2), "amount_usdc": 0.005},
               {"ts": _iso(5), "amount_usdc": 0.003}]
    summary = _summary(history)
    assert summary["best_day"]["date"] == _iso(2)[:10]
    assert summary["best_day"]["usdc"] == 0.01
    assert summary["best_day"]["count"] == 2


def test_the_summary_agrees_with_the_tables_it_summarises():
    """The invariant stated in `_plain_summary`'s docstring, measured.

    Every figure in the summary is drawn from the same rows as the sections, so
    the totals must match exactly. If this ever fails the two halves of the page
    have started telling different stories.
    """
    history = [{"ts": _iso(1), "amount_usdc": 0.003},
               {"ts": _iso(3), "amount_usdc": 0.005},
               {"ts": _iso(9), "amount_usdc": 0.003}]
    summary = _summary(history, total_count=3, total_usdc=0.011)

    assert summary["all_time"]["count"] == 3
    assert round(summary["all_time"]["usdc"], 6) == 0.011
    # Sales-by-day is derived from the same rows, so its sum must equal the total
    # for every day the window covers.
    inside = [r for r in summary["sales_by_day"] if r["count"]]
    assert sum(r["count"] for r in inside) == len(history)
    assert round(sum(r["usdc"] for r in inside), 6) == 0.011
    # Today's figure is a slice of the same series, not a second measurement.
    today_row = [r for r in summary["sales_by_day"]
                 if r["date"] == summary["today"]["from"]][0]
    assert summary["today"]["count"] == today_row["count"]
    assert summary["today"]["usdc"] == today_row["usdc"]


def test_the_payer_labels_no_longer_speak_in_internal_names():
    """The owner read "canary (Chet — верификация)" and could not decode it."""
    labels = main.PAYER_CLASS_LABELS_BG
    assert set(labels) == {"canary", "sampler", "external"}
    for text in labels.values():
        lowered = text.lower()
        for jargon in ("canary", "sampler", "chet", "crawler", "external"):
            assert jargon not in lowered, (text, jargon)
    assert "клиент" in labels["external"]
    assert "не е клиент" in labels["canary"]
    assert "не е клиент" in labels["sampler"]


# ── the wiring: it reaches the page, and it stays inside F-01 ────────────────

def test_the_summary_ships_in_the_free_dashboard_payload():
    client = main.app.test_client()
    response = client.get("/api/dashboard/data")
    assert response.status_code == 200
    doc = response.get_json()
    summary = doc["sections"]["summary"]
    for key in ("last_sale", "today", "yesterday", "this_week", "last_week",
                "week_change", "all_time", "best_day", "busiest_hour",
                "sales_by_day", "human_or_bot"):
        assert key in summary, key
    assert len(doc["daily_sales"]) == 7
    assert len(doc["daily_sales_28"]) == 28


def test_the_summary_cannot_leak_a_payer_or_a_transaction_hash():
    """F-01: the free payload is redacted to the aggregates. The new section is
    part of that payload, so it must not become the hole the redaction missed."""
    client = main.app.test_client()
    summary = client.get("/api/dashboard/data").get_json()["sections"]["summary"]
    text = repr(summary).lower()
    for forbidden in ("tx_hash", "transaction_hash", "sender", "payer_"):
        assert forbidden not in text, forbidden
    import re
    assert not re.search(r"0x[0-9a-fA-F]{64}", repr(summary))


def test_the_track_record_no_longer_gives_away_a_transaction_hash():
    """The F-01 residue this work found.

    `track_record` shipped `started_tx` and a `first_tx` per payer - the exact
    66-character hashes the paid /api/sales sells. Nothing read them, so on the
    free payload they were pure giveaway. The payer ADDRESSES are deliberately
    kept: they are public on Base by construction and the owner needs them to
    answer "who paid".
    """
    client = main.app.test_client()
    network = client.get("/api/dashboard/data").get_json()["sections"]["track_record"]
    assert "started_tx" not in network
    for payer in network.get("payers") or []:
        assert "first_tx" not in payer
    # The half the owner actually reads must survive the redaction.
    assert "started_date" in network or "started_at" in network
    assert all("short" in payer for payer in (network.get("payers") or []))


# ── the page itself: the answers must be on screen, not merely available ─────

def _page() -> str:
    return main.app.test_client().get("/dashboard").get_data(as_text=True)


def test_every_new_section_has_an_element_to_write_into():
    """A renderer with no target silently writes into null and the section
    stays empty - the failure mode is a blank panel, not an error."""
    html = _page()
    for element_id in ("answer-cards", "answer-note", "week-cards", "daybars",
                       "days-body", "days-note", "caller-cards", "callers-body",
                       "callers-note", "howto-receiver", "howto-basescan"):
        assert 'id="%s"' % element_id in html, element_id


def test_every_new_renderer_is_actually_called_by_load():
    """Defined-but-never-called is the quiet version of "not built"."""
    html = _page()
    for call in ("renderAnswers(s.summary", "renderDays(s.summary",
                 "renderCallers(s.summary"):
        assert call in html, call


def test_the_sales_chart_uses_the_28_day_series():
    """7 days cannot show whether this week beat last week."""
    html = _page()
    assert "d.daily_sales_28" in html


def test_the_dashboard_does_not_advertise_a_price_it_does_not_charge():
    """It said $0.10 for a micro-call while the 402 demanded $0.003.

    The comment above the section still mentions the old figure on purpose (it
    records the fix), so this checks the RENDERED price, not the file.
    """
    import re
    html = _page()
    prices = re.findall(r'<div class="tier-price">.*?</div>', html, re.S)
    assert prices, "the pricing section vanished"
    rendered = " ".join(prices)
    assert "$0.10" not in rendered
    assert "0.003" in rendered          # the real cheapest route
    assert "29.00" in rendered          # VIP, unchanged


def test_the_page_explains_itself():
    """The owner asked for the system to be described on the page: what is what,
    and how the thing works. These are the load-bearing claims."""
    html = _page()
    assert "Как работи системата" in html
    for claim in ("Истината е веригата", "EIP-3009", "402",
                  "data/dashboard_state.db", "платения"):
        assert claim in html, claim


# ── the operator's columns: back for him, still gone for everyone else ───────

def _store_row():
    return {
        "ts": "2026-11-04T02:46:17+00:00", "amount_usdc": 0.003,
        "tx_hash": "0x" + "ab" * 32, "sender": "0x" + "cd" * 20,
        "payer_class": "external", "payer_label": "external",
        "route": "/api/v1/signal", "block_number": 53505059, "source": "live",
    }


def test_the_public_row_keeps_only_time_and_amount():
    row, = main._onchain_history([_store_row()])
    assert set(row) <= {"ts", "amount"}
    assert row["amount"] == 0.003 and row["ts"].startswith("2026-11-04")


def test_the_operator_row_carries_the_columns_he_asked_for():
    """The sales table had Време · Сума · УСЛУГА · КЛИЕНТ until 10.10.

    They were dropped for F-01 (the full row is the paid /api/sales product) and
    the owner asked for them back, because "is this our own test, a crawler or a
    real customer, and which account paid" is how he reads the business.
    """
    row, = main._onchain_history([_store_row()], include_private=True)
    assert row["sender"] == "0x" + "cd" * 20       # the account that paid
    assert row["tx_hash"] == "0x" + "ab" * 32      # openable on BaseScan
    assert row["payer_class"] == "external"        # the colour / the words
    assert row["route"] == "/api/v1/signal"        # УСЛУГА
    assert row["amount"] == 0.003                  # and the public half survives


def test_both_views_keep_the_same_rows_in_the_same_order():
    """The operator must not be looking at a different ledger from the public."""
    rows = [_store_row(), dict(_store_row(), ts="2026-11-03T07:45:09+00:00")]
    public = main._onchain_history(rows)
    private = main._onchain_history(rows, include_private=True)
    assert [r["ts"] for r in public] == [r["ts"] for r in private]
    assert [r["amount"] for r in public] == [r["amount"] for r in private]


def test_the_history_helper_survives_an_empty_or_broken_source():
    assert main._onchain_history([]) == []
    assert main._onchain_history(None) == []
    assert main._onchain_history(None, include_private=True) == []
    # A row missing everything must still produce a row, not an exception.
    assert main._onchain_history([{}]) == [{"ts": None, "amount": None}]


def test_every_sales_cell_carries_the_value_its_column_sorts_on():
    """The table sorts by reading each cell's `data-v` (no libraries).

    A cell rendered without `data-v` does not fail loudly - it sorts as the empty
    string and that column quietly stops working. I did exactly that to the four
    new operator columns, and caught it only because the commit message I had
    already written claimed they carried it. So the claim is now a test.
    """
    source = re.search(r"function renderOnchain\(.*?\n\}", _page(), re.S)
    assert source, "renderOnchain moved or was renamed"
    cells = [c for c in re.findall(r"<td\b[^>]*>", source.group(0))
             if "colspan" not in c]          # the empty-state row holds no value
    assert len(cells) >= 6, cells            # 2 public + 4 operator columns
    for cell in cells:
        assert "data-v=" in cell, "a cell would sort as empty: %s" % cell


def test_the_operator_columns_require_a_real_token(monkeypatch):
    """The columns come back for the operator - and for nobody who guesses.

    F-01 is not weakened by putting them behind auth; it is the audit's own
    recommendation ("the dashboard payload behind an admin/session scope").
    """
    monkeypatch.setenv("ADMIN_API_TOKEN", "unit-test-admin-token")
    client = main.app.test_client()

    with_token = client.get(
        "/api/dashboard/data",
        headers={"X-Admin-Token": "unit-test-admin-token"}).get_json()
    without = client.get("/api/dashboard/data").get_json()
    with_wrong = client.get(
        "/api/dashboard/data",
        headers={"X-Admin-Token": "not-the-token"}).get_json()

    def fields(payload):
        rows = payload["sections"]["onchain"]["history"]
        return set().union(*[set(r) for r in rows]) if rows else set()

    assert "sender" in fields(with_token)
    assert "tx_hash" in fields(with_token)
    assert not (fields(without) & {"sender", "tx_hash", "route", "payer_class"})
    assert not (fields(with_wrong) & {"sender", "tx_hash", "route", "payer_class"})
    # The account the owner reads must not be spoilable by a near-miss token.
    assert fields(without) <= {"ts", "amount"}
