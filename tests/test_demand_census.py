# -*- coding: utf-8 -*-
"""The demand census: the paid route, the document, and the way it fails.

WHY THIS FILE EXISTS. `GET /api/v1/demand-census` is the first route this
service sells whose product is a DOCUMENT ABOUT ITS OWN MARKET rather than a
read of the market, and it is the dearest call we sell ($0.25). Three things
about it can go wrong in ways no other route's tests would catch:

  * it can be built at request time — three aggregates over a 1.2M-row ledger
    on a 0.1-CPU instance — instead of served from a snapshot, so the guard
    below reads the handler's own source and refuses a database call in it;
  * it can be paid for and then answer nothing, which is the one failure the
    x402 community treats as unforgivable. A missing or unreadable snapshot
    must therefore be refused BEFORE settlement and, if it is ever reached, must
    answer a named 503 rather than a 500 or an empty 200;
  * the free sample and the paid document can be allowed to describe two
    different schemas. Both read the same output example, and the test below
    holds the served document to the keys the 402 promises.

The generator's own arithmetic is tested too, against fixture rows rather than
production: the window comes from MIN/MAX of the rows actually found (never an
assumed 30 days), and the headline totals are derived from the per-agent list so
a buyer can re-add the rows and get the same numbers back.
"""
from __future__ import annotations

import inspect
import json
import os

import pytest

import main
from scripts import build_demand_census as census

ROUTE = "/api/v1/demand-census"
SAMPLE = "/api/v1/demand-census/sample"

#: The document's contract, in the order the generator writes it. Every key here
#: is unconditional in `build_document`, which is why the 402 may declare them
#: all as `required`.
DOCUMENT_KEYS = ("generated_at", "window", "totals", "payments", "attempts",
                 "agents", "method")


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0, raising=False)
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999      # exhaust the free tier
    yield main.app.test_client()
    main._free_tier_usage.clear()


@pytest.fixture()
def free_call(monkeypatch):
    """One free call, so a request can reach the handler past the paywall."""
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1, raising=False)
    main._free_tier_usage.clear()


@pytest.fixture()
def snapshot(tmp_path, monkeypatch):
    """Point the route at a throwaway snapshot and start with a cold cache."""
    path = tmp_path / "demand_census.json"
    monkeypatch.setattr(main, "_DEMAND_CENSUS_SNAPSHOT_PATH", str(path))
    monkeypatch.setattr(main, "_DEMAND_CENSUS_CACHE", {})
    return path


def _write(path, document):
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


def _document(**overrides):
    document = {
        "generated_at": "2026-11-24T21:00:00+00:00",
        "window": {"requests": {"requests": 10}},
        "totals": {"requests": 10},
        "payments": {"count": 2},
        "attempts": {"count": 3},
        "agents": [{"user_agent": "ExampleBot/1.0"}],
        "method": "fixture",
    }
    document.update(overrides)
    return document


# ── the price and the price source ─────────────────────────────────────────

def test_the_price_is_the_new_constant_and_is_not_hardcoded():
    from config import KRISTO_DEMAND_CENSUS_PRICE

    assert main.X402_PRICE_MAP[ROUTE] == KRISTO_DEMAND_CENSUS_PRICE
    # The owner-approved default, pinned because it is a business decision and
    # not an implementation detail: $0.25, above every existing route.
    assert float(KRISTO_DEMAND_CENSUS_PRICE) == 0.25
    assert float(KRISTO_DEMAND_CENSUS_PRICE) > max(
        price for route, price in main.X402_PRICE_MAP.items() if route != ROUTE)


def test_nothing_else_in_the_price_map_moved():
    """A new price is added; no existing price is touched."""
    from config import (KRISTO_ARB_PRICE, KRISTO_SALES_PRICE,
                        KRISTO_SIGNAL_PRICE, KRISTO_STATS_PRICE,
                        KRISTO_VERIFY_SELLER_PRICE, KRISTO_WHALEFLOW_PRICE)

    assert main.X402_PRICE_MAP["/api/stats"] == KRISTO_STATS_PRICE
    assert main.X402_PRICE_MAP["/api/sales"] == KRISTO_SALES_PRICE
    assert main.X402_PRICE_MAP["/api/bot-status"] == KRISTO_STATS_PRICE
    assert main.X402_PRICE_MAP["/api/arb/opportunities"] == KRISTO_ARB_PRICE
    assert main.X402_PRICE_MAP["/api/v1/signal"] == KRISTO_SIGNAL_PRICE
    assert main.X402_PRICE_MAP["/api/v1/whaleflow"] == KRISTO_WHALEFLOW_PRICE
    assert main.X402_PRICE_MAP["/api/v1/verify-seller"] == \
        KRISTO_VERIFY_SELLER_PRICE


def test_the_volume_discount_cannot_cut_this_route_to_a_cent():
    """$0.01 after ten calls is a 96% cut on the dearest product we sell.

    Until this route existed `min(0.01, base)` could not fire, because every
    base price was already at or below a cent — and the published npm client
    README states plainly that there is no volume discount. At $0.25 the
    expression becomes live, so the route is exempted by name; this asserts the
    exemption rather than the arithmetic, because the arithmetic is what would
    silently come back.
    """
    high_volume_ip = "203.0.113.7"
    main._paid_calls_usage[high_volume_ip] = 99
    try:
        assert main._get_dynamic_price(high_volume_ip, ROUTE) == \
            main.X402_PRICE_MAP[ROUTE]
        # …while a cheap route is unaffected either way (the discount is a
        # no-op there), so the exemption is scoped and not a new pricing model.
        assert main._get_dynamic_price(high_volume_ip, "/api/sales") == \
            main.X402_PRICE_MAP["/api/sales"]
    finally:
        main._paid_calls_usage.pop(high_volume_ip, None)


# ── the paywall ────────────────────────────────────────────────────────────

def test_an_unpaid_call_is_challenged_at_the_configured_price(client):
    assert ROUTE in main.X402_PAID_ENDPOINTS
    assert ROUTE not in main.X402_FREE_ENDPOINTS
    response = client.get(ROUTE)
    assert response.status_code == 402
    accepts = response.get_json()["accepts"]
    assert len(accepts) == 1
    assert int(accepts[0]["amount"]) == round(
        float(main.X402_PRICE_MAP[ROUTE]) * 1_000_000)
    assert accepts[0]["payTo"].lower() == main.X402_RECEIVER_ADDRESS.lower()
    assert accepts[0]["network"] == "eip155:8453"


def test_the_challenge_is_published_even_with_no_snapshot_at_all(client,
                                                                 snapshot):
    """The catalogues read this challenge to index the route.

    Refusing the bare path because the product is not built yet would take the
    route out of discovery in order to protect a billing edge — the same trade
    the seller-audit guard refuses.
    """
    assert not snapshot.exists()
    response = client.get(ROUTE)
    assert response.status_code == 402
    assert response.get_json()["accepts"][0]["amount"]


def test_a_missing_snapshot_is_refused_before_settlement(client, snapshot,
                                                         monkeypatch):
    """No money may move for a document this deployment does not have."""
    assert not snapshot.exists()
    settled = []
    monkeypatch.setattr(main, "_try_consume_standard_payment",
                        lambda *args: settled.append(args) or True)

    response = client.get(
        ROUTE, headers={"PAYMENT-SIGNATURE": "present-but-never-verified"})

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "no_census_to_deliver"
    assert body["payment_taken"] is False
    assert response.headers.get("Retry-After")
    assert settled == [], "the settle path ran for a route with nothing to sell"


def test_a_ready_snapshot_lets_the_credential_path_through_at_the_map_price(
        client, snapshot, monkeypatch):
    """The guard must not become a wall: the correct call still pays and passes."""
    _write(snapshot, _document())
    seen = []
    monkeypatch.setattr(
        main, "_try_consume_standard_payment",
        lambda path, price, ip: seen.append((path, price)) or True)

    response = client.get(ROUTE,
                          headers={"PAYMENT-SIGNATURE": "present-but-unused"})

    assert response.status_code == 200, response.get_json()
    assert seen == [(ROUTE, main.X402_PRICE_MAP[ROUTE])]


# ── the document ───────────────────────────────────────────────────────────

def test_the_paid_response_is_the_snapshot_and_carries_every_key(client,
                                                                 free_call,
                                                                 snapshot):
    document = _write(snapshot, _document())
    response = client.get(ROUTE)
    assert response.status_code == 200
    assert response.get_json() == document
    for key in DOCUMENT_KEYS:
        assert key in response.get_json(), key


def test_the_served_document_has_the_keys_the_402_promised(client, snapshot):
    """The challenge is the contract; the paid call must not reshape it.

    Checked in both directions, because either half can drift alone: the 402
    could promise a key the generator never writes (a BLOCK for a buyer that
    validates), or the generator could add one the challenge never declared.
    """
    bazaar = client.get(ROUTE).get_json()["extensions"]["bazaar"]
    example = bazaar["info"]["output"]["example"]
    declared = bazaar["schema"]["properties"]["output"]["properties"]["example"]
    required = declared.get("required") or []
    assert required, "the census challenge declares no required keys at all"
    assert set(required) <= set(example)
    assert set(example) == set(DOCUMENT_KEYS), (
        "the published example and the generator disagree about the document: "
        "%s" % sorted(set(example) ^ set(DOCUMENT_KEYS)))


def _undeclared(document, example, path="$"):
    """Every key the document carries that the example does not, at any depth.

    Top-level keys are not enough, and this is not hypothetical: the first
    version of this example published a FLAT window (`requests_first_ts`,
    `sales_first_ts`, `days`, …) while the generator writes one object per
    source table. Both had the key `window`, so a shape the buyer would never
    receive passed every check — for a document sold at $0.25, and until this
    walk existed.
    """
    problems = []
    if isinstance(document, dict):
        if not isinstance(example, dict):
            return ["%s: the document is an object here, the example is not"
                    % path]
        for key, value in document.items():
            if key not in example:
                problems.append("%s.%s" % (path, key))
                continue
            problems += _undeclared(value, example[key], "%s.%s" % (path, key))
    elif isinstance(document, list):
        if not isinstance(example, list) or not example:
            return ["%s: the example declares no row to compare with" % path]
        for item in document:
            if isinstance(item, dict):
                problems += _undeclared(item, example[0], path + "[]")
    return problems


def test_the_example_has_the_same_nested_shape_as_the_document():
    """The depth of the schema is part of the promise, not decoration."""
    document = _build()
    example = main._BAZAAR_OUTPUT_EXAMPLES[ROUTE]
    assert sorted(example) == sorted(document)
    assert _undeclared(document, example) == [], (
        "the 402 example does not describe the document the buyer receives")
    # …and the example must not promise a branch the document never produces
    # either, which is the same lie in the other direction.
    assert _undeclared(example, document) == []


def test_the_free_sample_is_free_and_carries_no_real_agent(client):
    """The schema is free; the agents that are the product are not."""
    assert SAMPLE in main.X402_FREE_ENDPOINTS
    response = client.get(SAMPLE)
    assert response.status_code == 200
    body = response.get_json()
    assert body["paid_route"] == ROUTE
    # The sample is the 402's own example, by reference at the source — a second
    # hand-written copy is how the free page and the paid challenge drift apart.
    assert body["output_example"] == main._BAZAAR_OUTPUT_EXAMPLES[ROUTE]
    assert "no payment" in body["disclaimer"].lower() or \
        "paid call" in body["disclaimer"].lower()
    example_agents = body["output_example"]["agents"]
    assert example_agents, "the sample must show the shape of an agent row"
    for row in example_agents:
        assert set(row) >= {"user_agent", "first_seen", "last_seen", "requests",
                            "challenged", "delivered", "ever_paid"}


# ── the failure modes, which must never be a 500 ───────────────────────────

def test_a_missing_snapshot_is_a_named_503_when_the_handler_is_reached(
        client, free_call, snapshot):
    assert not snapshot.exists()
    response = client.get(ROUTE)
    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "demand_census_unavailable"
    assert body["ok"] is False
    assert body["retryable"] is True
    assert response.headers.get("Retry-After")
    assert "no census snapshot" in body["message"]


@pytest.mark.parametrize("payload", ["{not json at all", "[1, 2, 3]", '"a string"'])
def test_an_unreadable_or_wrongly_shaped_snapshot_is_a_clean_503(
        client, free_call, snapshot, payload):
    """Truncated JSON from an interrupted write is the realistic corruption.

    A 500 here would be indistinguishable from a bug in the route, and a 200
    carrying half a document would be worse: the buyer paid for the numbers and
    would have no way to tell that some of them are missing.
    """
    snapshot.write_text(payload, encoding="utf-8")
    response = client.get(ROUTE)
    assert response.status_code == 503, response.get_json()
    assert response.get_json()["error"] == "demand_census_unavailable"


def test_an_oversized_snapshot_is_refused_rather_than_allocated(
        client, free_call, snapshot, monkeypatch):
    monkeypatch.setattr(main, "_DEMAND_CENSUS_MAX_BYTES", 16)
    snapshot.write_text(json.dumps(_document()), encoding="utf-8")
    response = client.get(ROUTE)
    assert response.status_code == 503
    assert "over the" in response.get_json()["message"]


def test_the_route_never_opens_a_database_at_request_time():
    """The architectural requirement, guarded at the source that would break it.

    A regression here is not a wrong number — it is three full aggregates over
    the 1.2M-row request ledger, run once per paying caller on an instance with
    a tenth of a CPU. There is no database client in this handler to disable, so
    the guard reads the handler instead and fails if one is ever added.
    """
    source = inspect.getsource(main.api_demand_census)
    assert "_demand_census_snapshot" in source
    for forbidden in ("execute(", "SELECT ", "psycopg", "sqlite3",
                      "dashboard_db", "_db_fetch"):
        assert forbidden not in source, (
            "%s appeared in the request path; the census is served from a "
            "snapshot built offline" % forbidden)


# ── the snapshot cache ─────────────────────────────────────────────────────

def test_the_snapshot_is_parsed_once_and_re_read_after_a_rebuild(snapshot):
    """Cached on the file's identity, not on a timer.

    Both halves matter at this price: a batch of paid calls must not re-parse
    the same bytes, and a snapshot rebuilt by the operator must be served by the
    very next request rather than at the next restart.
    """
    _write(snapshot, _document(generated_at="first"))
    first = main._demand_census_snapshot()
    assert main._demand_census_snapshot() is first, "the document was re-parsed"

    _write(snapshot, _document(generated_at="second"))
    stamp = os.stat(snapshot)
    os.utime(snapshot, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10_000_000))
    assert main._demand_census_snapshot()["generated_at"] == "second"


# ── the generator, against fixture rows rather than production ─────────────

def _rows(**overrides):
    """Query rows in the shape the generator's own statements return.

    Every window is carried ON the rows it describes (a count plus MIN/MAX per
    group) rather than by a second statement, which is what makes the totals
    re-addable — see the note on `census.queries`.
    """
    rows = {
        "agents": [
            {"user_agent": "monitor/1.0", "requests": 6,
             "first_seen": "2026-11-10 00:00:00", "last_seen": "2026-11-18 00:00:00",
             "challenged": 4, "delivered": 0, "total_requests": 9},
            {"user_agent": "buyer/1.0", "requests": 2,
             "first_seen": "2026-11-15 00:00:00", "last_seen": "2026-11-17 00:00:00",
             "challenged": 1, "delivered": 1, "total_requests": 9},
            {"user_agent": "(none)", "requests": 1,
             "first_seen": "2026-11-12 00:00:00", "last_seen": "2026-11-12 00:00:00",
             "challenged": 0, "delivered": 0, "total_requests": 9},
        ],
        "payments_by_class": [
            {"payer_class": "own_key", "payer_label": "demo", "n": 2, "usdc": 1.5,
             "first_ts": "2026-11-11 00:00:00", "last_ts": "2026-11-17 00:00:00"},
        ],
        "attempts_by_outcome": [
            {"outcome": "settled", "n": 2, "payers": 1,
             "first_ts": "2026-11-15 00:00:00", "last_ts": "2026-11-17 00:00:00"},
            {"outcome": "rejected", "n": 1, "payers": 1,
             "first_ts": "2026-11-16 00:00:00", "last_ts": "2026-11-16 00:00:00"},
        ],
        "attempts_payers": [{"payers": 2}],
        "agents_paid_attempts": [{"user_agent": "buyer/1.0", "matches": 1}],
        "agents_paid_guards": [{"user_agent": "monitor/1.0", "matches": 1}],
    }
    rows.update(overrides)
    return rows


def _build(rows=None, paths=("/api/stats",)):
    return census.build_document(rows if rows is not None else _rows(),
                                 list(paths), "2026-11-24T21:00:00+00:00")


def test_the_window_is_measured_from_the_rows_and_never_assumed():
    document = _build()
    assert document["window"]["requests"]["days"] == 8.0
    assert document["window"]["requests"]["first_ts"] == "2026-11-10 00:00:00"
    assert document["window"]["requests"]["last_ts"] == "2026-11-18 00:00:00"
    # A 30-day assumption would have printed 30 here; the generator has no such
    # constant anywhere, which is what the module docstring promises.
    assert document["window"]["sales"]["days"] == 6.0
    assert document["window"]["attempts"]["days"] == 2.0


def test_an_empty_ledger_still_produces_a_well_formed_document():
    """A new deployment must answer with zeros, not with a traceback."""
    document = _build(rows={})
    assert document["totals"] == {
        "requests": 0, "distinct_user_agents": 0,
        "agents_challenged_on_paid_routes": 0,
        "agents_delivered_on_paid_routes": 0, "agents_ever_paid": 0}
    assert document["window"]["requests"]["days"] is None
    assert document["agents"] == []
    assert document["method"]


def test_a_window_is_carried_by_the_same_rows_as_its_count():
    """Three statements on one live table do not agree to the row.

    The first production run of this generator counted `request_log` twice and
    came out three requests short of the sum of its own per-agent rows — the
    service takes ~30,000 requests a day, so "the same instant" is not a thing
    on that table. Every window is therefore carried by the rows it describes:
    one statement for the agents, one for the money, one for the credentials.
    """
    document = _build()
    assert document["window"]["requests"]["requests"] == 9
    assert document["window"]["requests"]["first_ts"] == "2026-11-10 00:00:00"
    assert document["window"]["requests"]["last_ts"] == "2026-11-18 00:00:00"
    assert document["window"]["sales"]["payments"] == 2
    assert document["window"]["attempts"]["attempts"] == 3
    assert document["totals"]["requests"] == document["window"]["requests"]["requests"]
    assert document["payments"]["count"] == document["window"]["sales"]["payments"]
    assert document["attempts"]["count"] == document["window"]["attempts"]["attempts"]


def test_the_totals_can_be_re_added_from_the_agent_rows():
    document = _build()
    assert document["totals"] == {
        "requests": 9,
        "distinct_user_agents": 3,
        "agents_challenged_on_paid_routes": 2,
        "agents_delivered_on_paid_routes": 1,
        "agents_ever_paid": 2,
    }
    assert document["totals"]["requests"] == sum(
        row["requests"] for row in document["agents"])
    assert [row["user_agent"] for row in document["agents"]] == [
        "monitor/1.0", "buyer/1.0", "(none)"]
    assert [row["ever_paid"] for row in document["agents"]] == [True, True, False]


def test_the_money_and_the_attempts_are_split_as_the_task_asked():
    document = _build()
    assert document["payments"]["count"] == 2
    assert document["payments"]["total_usdc"] == 1.5
    assert document["payments"]["by_payer_class"][0]["payer_class"] == "own_key"
    assert document["attempts"]["count"] == 3
    assert document["attempts"]["distinct_payers"] == 2
    assert [row["outcome"] for row in document["attempts"]["by_outcome"]] == [
        "settled", "rejected"]


def test_a_failed_association_query_costs_the_paid_flag_and_nothing_else():
    """A missing `payment_guards` table must not take the document down.

    It must also not pass silently: `method` says which sources were used, so a
    reader can tell "nobody paid" from "we could not see the payment ledger".
    """
    document = census.build_document(
        _rows(agents_paid_guards=[{"error": "relation does not exist"}]),
        ["/api/stats"], "2026-11-24T21:00:00+00:00",
        guard_error="relation does not exist")
    assert document["totals"]["requests"] == 9
    assert "UNAVAILABLE" in document["method"]
    assert document["totals"]["agents_ever_paid"] == 1


def test_the_generator_counts_the_paywalls_own_paid_paths():
    """The generator must not keep a second list of what a paid route is."""
    assert census.paid_paths() == sorted(main.X402_PAID_ENDPOINTS)
    assert ROUTE in census.paid_paths()


def test_every_statement_the_generator_runs_is_a_select():
    """All SQL is SELECT-only, checked before it is ever sent."""
    statements = dict(census.queries(["/api/stats"]))
    statements["agents_paid_guards"] = census.guards_query(["/api/stats"])
    census.assert_select_only(statements)          # raises SystemExit otherwise
    assert statements, "the generator runs no statements at all"


def test_a_write_statement_is_refused_before_it_reaches_production():
    with pytest.raises(SystemExit):
        census.assert_select_only(
            {"oops": "UPDATE request_log SET ts = '2020-01-01'"})
    with pytest.raises(SystemExit):
        census.assert_select_only({"oops": "DELETE FROM onchain_sales"})


# ── the transfer, which is where a $0.25 document was nearly lost ──────────

def _chunked(payload, size=40_000):
    """The job's own framing: compressed, base64, numbered lines."""
    import base64
    import json as _json
    import zlib as _zlib

    blob = base64.b64encode(_zlib.compress(
        _json.dumps(payload).encode(), 6)).decode()
    parts = [blob[i:i + size] for i in range(0, len(blob), size)] or [""]
    return ["DC %d/%d %s" % (i, len(parts), part)
            for i, part in enumerate(parts, 1)]


def test_the_payload_survives_the_log_line_transport():
    """The first real run lost the document to a 100,000-character log line.

    `json.decoder.JSONDecodeError: Unterminated string starting at ... char
    99991` — the log viewer truncates a line, and the per-agent table is the one
    payload here that is bigger than the other audit scripts' summaries. The
    framing is therefore part of the product, not plumbing: it must round-trip a
    document far larger than the limit, and it must refuse a truncated transfer
    loudly instead of decoding half a census.
    """
    # High-entropy on purpose: a document of repeating names compresses to one
    # chunk and would let a broken transport pass this test.
    import hashlib

    document = {"agents": [{"user_agent": hashlib.sha1(
        str(i).encode()).hexdigest(), "requests": i} for i in range(4000)],
        "method": "x" * 5000}
    lines = _chunked(document)
    assert len(lines) > 1, "this fixture must exercise the multi-chunk path"
    assert max(len(line) for line in lines) < 100_000

    chunks, expected = {}, None
    for line in lines:
        index, expected, part = census._chunk(line)
        chunks[index] = part
    assert census._decode_chunks(chunks, expected, "job") == document

    del chunks[2]
    with pytest.raises(SystemExit) as failure:
        census._decode_chunks(chunks, expected, "job")
    assert "never printed chunks" in str(failure.value)


def test_a_log_line_that_is_not_ours_is_ignored():
    """The job's own startup output shares the log with the payload."""
    for line in ("", "DC", "DC nope", "TA 1/1 abc",
                 "2026-11-24 demand census job starting"):
        assert census._chunk(line) is None
