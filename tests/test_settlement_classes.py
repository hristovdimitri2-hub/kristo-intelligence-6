# -*- coding: utf-8 -*-
"""GET /api/v1/settlement-classes — the clean number, including the bad half.

PayAI posted the ask on 05.11.2026: *"x402 data mixes real agent spend with
cron jobs, bots and wash activity. Nobody can say how much of it is genuinely
agentic. Build the open classifier: label every settlement as agent, script or
noise, then publish the clean number."*

These tests exist mostly to hold the route to the two things that make such a
number worth publishing at all: it must be FREE (a statement nobody can read
without paying is not a statement), and it must not flatter us — a seller that
publishes only the good half is what makes the ecosystem number untrustworthy.
"""
import pytest


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
    main._free_tier_usage.clear()
    yield main.app.test_client(), main, dash
    main._free_tier_usage.clear()


def _sell(dash, tx, sender, amount, payer_class):
    dash.history._run(
        """INSERT INTO onchain_sales
               (tx_hash, block_number, ts, sender, amount_usdc,
                payer_class, payer_label, source, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tx, 1, "2026-11-11T00:00:00+00:00", sender, amount,
         payer_class, payer_class, "test", "2026-11-11T00:00:00+00:00"))


# ── the shape and the honesty ───────────────────────────────────────────────

def test_the_route_is_public_and_free_with_the_tier_exhausted(client):
    """A statement about our own ledger must not be behind a paywall."""
    c, main, _dash = client
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = c.get("/api/v1/settlement-classes")
        assert r.status_code == 200, r.status_code
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)


def test_it_publishes_the_method_and_its_own_limits(client):
    c, _main, _dash = client
    body = c.get("/api/v1/settlement-classes").get_json()
    assert body["ok"] is True
    assert body["source"] == "real_blockchain"
    # The method must name the evidence, not the intent.
    assert "on-chain" in body["method"].lower()
    assert "fingerprint" in body["method"].lower()
    assert "self-report" in body["method"].lower()
    # And it must say what it is NOT, because the temptation is to imply more.
    assert "OUR ledger, not the ecosystem" in body["caveat"]


def test_every_class_carries_a_meaning(client):
    c, _main, dash = client
    _sell(dash, "0x1", "0xaaa", 0.003, "own_key")
    _sell(dash, "0x2", "0xbbb", 0.003, "external")
    _sell(dash, "0x3", "0xccc", 0.003, "sampler")
    _sell(dash, "0x4", "0xddd", 0.003, "canary")
    body = c.get("/api/v1/settlement-classes").get_json()
    assert len(body["classes"]) == 4
    for entry in body["classes"]:
        assert entry["meaning"], entry
        assert entry["meaning"] != "Unclassified payer.", (
            "%s has no meaning written beside it in PAYER_CLASSES" % entry["class"])


# ── the number itself ───────────────────────────────────────────────────────

def test_our_own_settlements_are_excluded_from_the_clean_number(client):
    """The whole point: self-payments are not demand and must not count."""
    c, _main, dash = client
    _sell(dash, "0x1", "0xaaa", 0.500, "own_key")
    _sell(dash, "0x2", "0xbbb", 0.010, "external")
    body = c.get("/api/v1/settlement-classes").get_json()
    clean = body["clean_number"]
    assert clean["settlements"] == 2
    assert clean["usdc"] == pytest.approx(0.510, abs=1e-9)
    assert clean["third_party_settlements"] == 1
    assert clean["third_party_usdc"] == pytest.approx(0.010, abs=1e-9)
    assert clean["third_party_share_of_usdc"] == pytest.approx(0.010 / 0.510,
                                                              abs=1e-6)


def test_a_crawler_heartbeat_is_not_counted_as_a_customer(client):
    """`sampler` is third-party, but the route must not let it read as demand."""
    c, _main, dash = client
    _sell(dash, "0x1", "0xaaa", 0.003, "sampler")
    body = c.get("/api/v1/settlement-classes").get_json()
    entry = [e for e in body["classes"] if e["class"] == "sampler"][0]
    assert "heartbeat" in entry["meaning"]
    assert "not a buyer" in body["reading_it"] or "heartbeat" in body["reading_it"]
    # It IS third-party money (we did receive it), so it stays in that total.
    assert body["clean_number"]["third_party_settlements"] == 1


def test_an_empty_ledger_does_not_divide_by_zero(client):
    c, _main, _dash = client
    body = c.get("/api/v1/settlement-classes").get_json()
    assert body["ok"] is True
    assert body["clean_number"]["usdc"] == 0
    assert body["clean_number"]["third_party_share_of_usdc"] is None


def test_classes_are_ordered_by_money_not_by_name(client):
    c, _main, dash = client
    _sell(dash, "0x1", "0xaaa", 0.001, "own_key")
    _sell(dash, "0x2", "0xbbb", 0.900, "external")
    _sell(dash, "0x3", "0xccc", 0.050, "sampler")
    body = c.get("/api/v1/settlement-classes").get_json()
    assert [e["class"] for e in body["classes"]] == [
        "external", "sampler", "own_key"]


def test_the_store_summary_survives_an_unknown_class(client):
    """A new class must not break the route before its meaning is written."""
    c, _main, dash = client
    _sell(dash, "0x1", "0xaaa", 0.003, "brand_new_class")
    r = c.get("/api/v1/settlement-classes")
    assert r.status_code == 200
    entry = [e for e in r.get_json()["classes"]
             if e["class"] == "brand_new_class"][0]
    assert entry["meaning"] == "Unclassified payer."


# ── the backend-shape trap ──────────────────────────────────────────────────

def test_the_summary_reads_rows_by_column_name(client, monkeypatch):
    """Postgres hands back `dict_row`; SQLite hands back `sqlite3.Row`.

    ONLY the second supports integer indexing, so a reader written as `row[0]`
    passes the whole suite on SQLite and raises `KeyError: 0` on production —
    which is exactly what shipped, and what the log reported as the unhelpful
    "settlement classes unavailable: 0". This pins the contract: the reader must
    work on dicts, because that is what the live backend returns.
    """
    c, _main, dash = client
    rows = [
        {"cls": "own_key", "n": 74, "usdc": 0.868, "payers": 1},
        {"cls": "external", "n": 16, "usdc": 0.052, "payers": 9},
    ]
    monkeypatch.setattr(dash.history, "_run", lambda *a, **kw: (rows, 0))

    r = c.get("/api/v1/settlement-classes")
    assert r.status_code == 200, (
        "the reader must accept the row shape the live backend returns; got %s "
        "%s" % (r.status_code, r.get_json()))
    clean = r.get_json()["clean_number"]
    assert clean["settlements"] == 90
    assert clean["third_party_settlements"] == 16
    assert clean["third_party_usdc"] == pytest.approx(0.052, abs=1e-9)

