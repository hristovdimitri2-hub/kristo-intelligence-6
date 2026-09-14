"""Табло 2.0 — the sections that put the truth on one screen.

Covers the four new blocks (ON-CHAIN table, КЛИЕНТИ, КИТОВЕ, СТАЖИ) plus the
always-visible ФЪНЪЛ, and locks in two regressions that produced PHANTOM
NUMBERS on a dashboard whose whole job is honesty:

  * FUNNEL bug — "Днес: 402 → платени" was filled from the ALL-TIME query
    (`challenges_today`/`paid_today` read `cur` instead of `cur_today`), so the
    "today" column silently repeated the total.
  * ROUTE-TABLE drift — the static HTML advertised /api/sales at $0.05 while
    the live 402 demanded $0.005 (10x). The table is now rendered from the same
    list that mints the challenge, and this file asserts they agree.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

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
    return main.app.test_client(), main, dash


def _sections(test_client):
    body = test_client.get("/api/dashboard/data").get_json()
    return body["sections"]


# ── 1. ON-CHAIN SALES: the chain numbers, permanently on screen ─────────────

def test_onchain_section_carries_the_verified_chain_truth(client):
    test_client, _main, dash = client
    dash.seed_verified_sales()
    o = _sections(test_client)["onchain"]
    assert o["total_usdc"] == 0.031
    assert o["total_count"] == 9
    assert o["external_payers"] == 3
    assert o["by_class"]["canary"] == {"count": 5, "total_usdc": 0.017}
    assert o["by_class"]["external"] == {"count": 3, "total_usdc": 0.011}
    assert o["by_class"]["sampler"] == {"count": 1, "total_usdc": 0.003}
    # FULL 66-char hashes + the real block numbers (no truncation, no zeros).
    assert len(o["history"]) == 9
    for row in o["history"]:
        assert len(row["tx_hash"]) == 66 and row["tx_hash"].startswith("0x")
        assert row["block_number"] > 50_000_000
        assert row["payer_class"] in {"canary", "sampler", "external"}


# ── 2. КЛИЕНТИ: external payers, with route honesty ─────────────────────────

def test_clients_section_lists_every_external_payer(client):
    test_client, _main, dash = client
    dash.seed_verified_sales()
    c = _sections(test_client)["clients"]
    assert c["count"] == 3
    by_wallet = {x["wallet"]: x for x in c["clients"]}
    assert set(by_wallet) == {
        "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7",
        "0x902dcf34e53695bdea2ffb354b1a2e58bd598256",
        # 0xA19F was dropped by an earlier audit because the payer's history was
        # read through a paginated query; the chain scan found it later.
        "0xa19f621581dbc851a21d6179868111709a52accc",
    }
    for row in by_wallet.values():
        assert row["payments"] == 1
        assert row["last_ts"]
        assert len(row["tx_hashes"]) == 1


def test_clients_routes_are_never_invented(client):
    """$0.003 buys EITHER signal OR whaleflow, and $0.005 covers four routes.

    With no payment_guards row for those historical txs, the honest answer is
    the candidate list — naming a single route would be a fabricated fact on
    the screen that is supposed to hold only facts.
    """
    test_client, _main, dash = client
    dash.seed_verified_sales()
    c = _sections(test_client)["clients"]
    for row in c["clients"]:
        for route in row["routes"]:
            assert route["evidence"] == "price_ambiguous"
            assert route["route"] is None
            assert len(route["candidates"]) >= 2
    prices = c["route_price_map"]
    assert prices["/api/v1/signal"] == prices["/api/v1/whaleflow"] == 0.003


def test_clients_route_becomes_a_fact_once_the_guard_records_it(client):
    """After C1/H2 consume a proof, the endpoint IS recorded — so the same
    payer's route is then reported with `payment_guard` evidence (a fact)."""
    test_client, _main, dash = client
    dash.seed_verified_sales()
    tx = "0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3"
    assert dash.claim_payment_tx(tx, endpoint="/api/v1/signal",
                                 payer="0x4db7aafb", amount_usdc=0.003)
    c = _sections(test_client)["clients"]
    row = [x for x in c["clients"] if x["wallet"].startswith("0x4db7aafb")][0]
    assert any(r["evidence"] == "payment_guard"
               and r["route"] == "/api/v1/signal" for r in row["routes"])


# ── 3. КИТОВЕ: a truthful empty, never a fake zero ──────────────────────────

def test_paid_sales_route_serves_the_store_after_a_restart(client, monkeypatch):
    """AUDIT A3: /api/sales is a PAID route ($0.005, "On-Chain Sales History").
    It read the RAM `_sales_history`, so a paying customer received
    `total_sales: 0` with an empty history after any restart/deploy while the
    chain said $0.031 over 9 transfers. RAM is emptied here exactly like after
    a restart — the store must carry the answer."""
    test_client, main, dash = client
    # Make the test independent of test order: /api/sales is behind the
    # paywall and the free-tier counter is process-wide RAM.
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    dash.seed_verified_sales()
    monkeypatch.setattr(main, "_sales_history", [])   # "the process restarted"
    resp = test_client.get("/api/sales")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:200]
    payload = resp.get_json()
    assert payload["total_volume_usd"] == 0.031
    assert payload["total_sales"] == 9
    assert payload["by_token"] == {"USDC": 0.031}
    assert len(payload["history"]) == 9
    for row in payload["history"]:
        assert len(row["tx_hash"]) == 66
        assert row["amount_usd"] == row["amount_usdc"]
        assert row["timestamp"] == row["ts"]
    # Legacy order (oldest -> newest) is preserved for existing consumers.
    blocks = [row["block_number"] for row in payload["history"]]
    assert blocks == sorted(blocks)


def test_paid_sales_route_falls_back_to_ram_when_the_store_is_empty(
        client, monkeypatch):
    """The store is the truth, but an empty store must not blank a longer RAM
    history (e.g. a scan that has just discovered sales)."""
    test_client, main, _dash = client
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": "0x" + "9a" * 32, "token": "USDC", "amount_usd": 0.003,
        "sender": "0x" + "11" * 20, "block_number": 1,
    }])
    payload = test_client.get("/api/sales").get_json()
    assert payload["total_sales"] == 1
    assert payload["total_volume_usd"] == 0.003


def test_stats_route_reports_durable_request_counters(client, monkeypatch):
    """AUDIT C: the PAID /api/stats summed the RAM `_daily_stats`, so after a
    deploy the public widget showed "0 API calls" while the persistent log held
    tens of thousands. The store is the truth; the RAM view stays, labelled."""
    test_client, main, dash = client
    now = datetime.now(timezone.utc).isoformat()
    with dash._write_lock, dash._connect() as conn:
        for _ in range(3):
            conn.execute(
                """INSERT INTO request_log
                       (ts, method, path, source, status_code, user_agent,
                        referer, funnel)
                   VALUES (?, 'GET', '/health', 'api', 200, 'ua', '', NULL)""",
                (now,),
            )
        conn.commit()
    monkeypatch.setattr(main, "_daily_stats", {})   # "the process restarted"
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    payload = test_client.get("/api/stats").get_json()
    assert payload["total_requests"] == 3
    assert payload["today"]["requests"] == 3
    # Nothing hidden: the old RAM-derived view is still exposed, explicitly.
    # It counts ONLY instrumented routes and only since this process started —
    # hence 1 (this very /api/stats call) against 3 durable ones.
    assert payload["instrumented_requests"]["total"] == 1
    assert payload["instrumented_requests"]["note"]


# ── 10. AUDIT B: the demo surface can be parked with one flag ───────────────

def test_demo_surfaces_can_be_parked_without_deleting_code(client, monkeypatch):
    """The 8 demo SKUs + the Stripe lead funnel are UNPROVEN (zero paid sales
    ever came through them) yet carry the largest public surface.
    KRISTO_DEMO_SURFACES=off parks them behind a 404 and deletes no code."""
    test_client, main, _dash = client
    monkeypatch.delenv("KRISTO_DEMO_SURFACES", raising=False)
    # Default: unchanged behaviour, the switch must not surprise anyone.
    assert main.demo_surfaces_enabled() is True
    assert test_client.post("/api/v1/agents/whaleflow-radar/playground",
                            json={"input": "ETH"}).status_code == 200

    monkeypatch.setenv("KRISTO_DEMO_SURFACES", "off")
    assert main.demo_surfaces_enabled() is False
    for path in ("/api/v1/agents/whaleflow-radar/playground",
                 "/api/v1/agents/whaleflow-radar/checkout",
                 "/api/v1/agents/whaleflow-radar/access",
                 "/api/v1/agents/whaleflow-radar/click",
                 "/sales/checkout", "/api/checkout", "/agents"):
        r = test_client.post(path, json={"input": "ETH", "email": "a@b.c"})
        assert r.status_code == 404, f"{path} -> {r.status_code}"
        assert r.get_json()["error"] == "surface_retired"
    assert test_client.post("/api/leads", json={"email": "a@b.c"}).status_code == 404

    # …while the real vitrine and operations are untouched.
    assert test_client.get("/api/v1/agents").status_code == 200
    assert test_client.get("/api/v1/agents/whaleflow-radar").status_code == 200
    assert test_client.get("/dashboard").status_code == 200
    # The repair lever must never be parked.
    assert test_client.post("/api/admin/seed-sales").status_code == 401


def test_parked_demo_surfaces_do_not_touch_the_real_routes(client, monkeypatch):
    """The 6 real x402 routes are the product — parking must not reach them."""
    test_client, main, _dash = client
    monkeypatch.setenv("KRISTO_DEMO_SURFACES", "off")
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    for route in main.REAL_X402_ROUTES:
        r = test_client.get(route["endpoint"],
                            environ_base={"REMOTE_ADDR": "203.0.113.55"})
        assert r.status_code == 402, f"{route['endpoint']} -> {r.status_code}"


def test_offchain_storage_durability_is_visible_not_assumed(client):
    """AUDIT A2: with DATABASE_URL unset the CRM is SQLite on Render's EPHEMERAL
    disk — every deploy wipes leads and paid records. The dashboard must say
    that out loud, because a confident "$0" there means "unknown", not "zero".
    (Making it durable is an owner action: set DATABASE_URL.)"""
    test_client, _main, _dash = client
    c = _sections(test_client)["crm_stripe"]
    assert c["storage_backend"] in ("sqlite", "postgresql")
    assert c["durable"] is (c["storage_backend"] == "postgresql")
    assert c["storage_note"]
    if not c["durable"]:
        assert "DATABASE_URL" in c["storage_note"]
    html = test_client.get("/dashboard").get_data(as_text=True)
    assert 'id="crm-storage"' in html and "crm-storage" in html


def test_rpc_api_keys_are_redacted_before_logging():
    """A keyed RPC URL wrote the credential straight into the log stream
    (`.../v2/alch_XXXX`). Keep the host, drop the secret."""
    from integrations.dashboard_store import redact_rpc

    msg = ("500 Server Error for url: https://base-mainnet.g.alchemy.com/v2/"
           "alch_lMA7z24yRSecretKey123")
    out = redact_rpc(msg)
    assert "alch_lMA7z24yRSecretKey123" not in out
    assert "/v2/***" in out
    assert "base-mainnet.g.alchemy.com" in out     # host stays diagnosable
    assert "secretkeyvalue" not in redact_rpc("https://x.io/?apikey=secretkeyvalue")
    assert "abc123def456" not in redact_rpc("https://x.io/rpc?token=abc123def456")
    assert redact_rpc("plain text, no key") == "plain text, no key"


# ── 11. HISTORY SURVIVES A RESTART (the acceptance criterion) ───────────────

class _FakePostgres:
    """A tiny in-memory stand-in for the history tables in PostgreSQL.

    It stores the rows and answers the same queries the real backend runs, so
    the test exercises the DATA path (does the history outlive the process?)
    instead of merely asserting that some SQL was sent.
    """

    def __init__(self):
        self.whales = []
        self.requests = []
        self.sql = []


class _FakeCursor:
    def __init__(self, db):
        self.db = db
        self.rowcount = 0
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        params = tuple(params or ())
        s = " ".join(sql.split())
        self.db.sql.append(s)
        self.rowcount = 0

        if s.startswith("CREATE TABLE") or s.startswith("CREATE INDEX"):
            return
        if s.startswith("INSERT INTO whaleflow_events"):
            key = (params[0], params[1])
            if not any((r["tx_hash"], r["log_index"]) == key
                       for r in self.db.whales):
                self.db.whales.append({
                    "tx_hash": params[0], "log_index": params[1],
                    "ts": params[2], "token": params[3],
                    "amount_usdc": params[4], "from_addr": params[5],
                    "to_addr": params[6], "block_number": params[7],
                })
                self.rowcount = 1
            return
        if s.startswith("INSERT INTO request_log"):
            self.db.requests.append({"ts": params[0], "path": params[2]})
            self.rowcount = 1
            return
        if "COUNT(*) AS n, MAX(ts) AS last_ts" in s:
            big = [r for r in self.db.whales if r["amount_usdc"] >= params[0]]
            self._rows = [{
                "n": len(big),
                "last_ts": max((r["ts"] for r in big), default=None),
                "last_block": max((r["block_number"] for r in big), default=None),
            }]
            return
        if "FROM whaleflow_events" in s:
            big = [r for r in self.db.whales
                   if r["ts"] >= params[0] and r["amount_usdc"] >= params[1]]
            big.sort(key=lambda r: (r["ts"], r["block_number"]), reverse=True)
            self._rows = big[:params[2]]
            return
        if s.startswith("SELECT COUNT(*) AS n FROM request_log"):
            self._rows = [{"n": len(self.db.requests)}]
            return
        if "AS challenges" in s:
            # Real PostgreSQL always returns ONE row for a bare SUM (NULLs on an
            # empty table); the fake must do the same instead of None.
            self._rows = [{"challenges": 0, "paid": 0}]
            return
        self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


def _install_fake_postgres(monkeypatch, db):
    from integrations.dashboard_store import HistoryStore

    class _Conn:
        def __init__(self, db_):
            self._db = db_

        @property
        def closed(self):
            return False

        def cursor(self):
            return _FakeCursor(self._db)

        def commit(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(HistoryStore, "_pg_connection", lambda self: _Conn(db))
    return db


def test_history_survives_a_restart_when_postgres_is_configured(
        tmp_path, monkeypatch):
    """THE acceptance criterion: with DATABASE_URL set, a deploy/restart must
    NOT drop the paid whale feed's history (all_time fell 20 478 -> 598 when the
    table lived on the ephemeral SQLite file)."""
    from integrations.dashboard_store import DashboardStore

    db = _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")
    monkeypatch.setenv("WHALE_THRESHOLD", "50000")

    now = datetime.now(timezone.utc).isoformat()
    first = DashboardStore(tmp_path / "a.db")
    assert first.history.backend == "postgresql"
    assert first.history.record_whale_event(
        "0x" + "ab" * 32, 0, now, "USDC", 250_000.0,
        "0x" + "cd" * 20, "0x" + "ef" * 20, 51_240_000) == 1
    first.record_request("GET", "/health", "api", 200)
    assert first.whaleflow_summary(window_hours=24)["all_time_count"] == 1

    # "restart": a brand-new store on a brand-new SQLite file, same database.
    second = DashboardStore(tmp_path / "b.db")
    assert second.history.backend == "postgresql"
    summary = second.whaleflow_summary(window_hours=24)
    assert summary["all_time_count"] == 1, "history did NOT survive the restart"
    assert summary["count"] == 1
    assert summary["state"] == "live_data"
    assert summary["whales"][0]["amount_usdc"] == 250_000.0
    assert second.requests_summary()["total"] == 1
    # The dialect actually used is PostgreSQL, not SQLite.
    joined = " ".join(db.sql)
    assert "ON CONFLICT (tx_hash, log_index) DO NOTHING" in joined
    assert "BIGSERIAL PRIMARY KEY" in joined
    assert "%s" in joined


def test_history_is_idempotent_and_uses_sqlite_without_database_url(
        tmp_path, monkeypatch):
    """Without DATABASE_URL nothing changes: same SQLite tables, same file —
    and the same duplicate protection as PostgreSQL's ON CONFLICT."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = DashboardStore(tmp_path / "d.db")
    assert store.history.backend == "sqlite"
    store.record_request("GET", "/health", "api", 200)
    assert store.requests_summary()["total"] == 1

    now = datetime.now(timezone.utc).isoformat()
    assert store.history.record_whale_event(
        "0x" + "11" * 32, 0, now, "USDC", 99_000.0,
        "0x" + "aa" * 20, "0x" + "bb" * 20, 1) == 1
    assert store.history.record_whale_event(
        "0x" + "11" * 32, 0, now, "USDC", 99_000.0,
        "0x" + "aa" * 20, "0x" + "bb" * 20, 1) == 0     # duplicate ignored
    assert store.whaleflow_summary(window_hours=24, threshold=50_000.0
                                   )["all_time_count"] == 1


def test_postgres_dialect_is_psycopg_safe():
    """The fake Postgres in this file cannot catch a SQL-dialect mistake, so the
    dialect is asserted DIRECTLY.

    Real bug (caught in production, not by the fake): psycopg reads `%` as a
    placeholder marker, so `user_agent LIKE 'Render/%'` raised
    psycopg.ProgrammingError("only '%s', '%b', '%t' are allowed as placeholders,
    got '%'") and turned /api/dashboard/data into HTTP 500 for everyone."""
    from integrations.dashboard_store import HistoryStore

    pg = HistoryStore.__new__(HistoryStore)
    pg.backend = "postgresql"
    pg._ph = "%s"

    like = pg._q("SELECT COUNT(*) AS n FROM request_log "
                 "WHERE user_agent LIKE 'Render/%'")
    assert "LIKE 'Render/%%'" in like, "a literal percent must be doubled"
    assert "?" not in like

    two = pg._q("SELECT SUM(CASE WHEN user_agent LIKE 'Render/%' THEN 1 "
                "ELSE 0 END) AS n FROM request_log "
                "WHERE substr(ts, 1, 10) = ? AND path = ?")
    assert two.count("%%") == 1          # only the literal one is doubled
    assert two.count("%s") == 2          # both parameters translated
    assert "?" not in two

    # SQLite is untouched: `%` stays a plain LIKE wildcard, `?` stays `?`.
    lite = HistoryStore.__new__(HistoryStore)
    lite.backend = "sqlite"
    lite._ph = "?"
    lite_sql = lite._q("SELECT COUNT(*) AS n FROM request_log "
                       "WHERE user_agent LIKE 'Render/%' AND path = ?")
    assert "LIKE 'Render/%'" in lite_sql
    assert lite_sql.endswith("= ?")


# ── 12. The seed reproduces the FULL chain truth (9 rows) ───────────────────

def test_seed_restores_all_nine_transfers_on_a_wiped_database(tmp_path,
                                                              monkeypatch):
    """On the next deploy the dashboard must read $0.031 / 9 IMMEDIATELY, not
    after hours of scanner catch-up.

    Why this test exists: an earlier audit concluded "$0.028 / 8 transfers / 2
    external" and RETIRED the 0xA19F payment, because the payer's history was
    read through a paginated query. The chain scan later found the missing
    transfer (block 51079970, $0.003, 2026-09-09) once the RPC host was fixed.
    The manifest now carries all nine rows, so a wiped filesystem is repaired
    from the chain truth without waiting for anyone.
    """
    from integrations.dashboard_store import DashboardStore
    from integrations.verified_sales import VERIFIED_SALES, expected_totals

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("KRISTO_DASHBOARD_DB", raising=False)

    # The manifest itself: nine rows, ascending blocks, full hashes.
    assert len(VERIFIED_SALES) == 9
    totals = expected_totals()
    assert totals["total_usdc"] == 0.031
    assert totals["total_count"] == 9
    blocks = [r["block_number"] for r in VERIFIED_SALES]
    assert blocks == sorted(blocks)
    assert 51079970 in blocks, "the recovered 0xA19F transfer is missing"
    recovered = [r for r in VERIFIED_SALES
                 if r["block_number"] == 51079970][0]
    assert recovered["tx_hash"] == (
        "0xb66077d16909973aa1a2d0492a3e18f2e90b34b288e584f6c5377353ad7ca8a2")
    assert recovered["sender"] == "0xa19f621581dbc851a21d6179868111709a52accc"
    assert recovered["amount_usdc"] == 0.003

    # A brand-new (deploy-wiped) database, repaired by the boot-time seed.
    store = DashboardStore(tmp_path / "wiped.db")
    assert store.seed_verified_sales()["inserted"] == 9
    summary = store.sales_summary()
    assert summary["total_usdc"] == 0.031
    assert summary["total_count"] == 9
    assert summary["external_payers"] == 3
    assert summary["by_class"]["external"] == {"count": 3,
                                               "total_usdc": 0.011}
    assert len(summary["history"]) == 9
    # Idempotent on the next boot: nothing inserted, nothing changed.
    assert store.seed_verified_sales()["inserted"] == 0
    assert store.sales_summary()["total_usdc"] == 0.031


def test_whales_section_is_honest_when_the_window_is_empty(client):
    test_client, _main, dash = client
    dash.set_meta("whaleflow_safe_scanned_block", "51234567")
    w = _sections(test_client)["whales"]
    assert w["count"] == 0
    assert w["state"] == "awaiting_whale"          # not "0", not "live"
    assert w["scanned_until_block"] == 51234567    # proof the scan IS running
    assert w["whales"] == []
    assert w["all_time_count"] == 0


def test_whales_section_reports_scan_not_started_before_the_first_cycle(client):
    test_client, _main, _dash = client
    w = _sections(test_client)["whales"]
    assert w["state"] == "scan_not_started"
    assert w["scanned_until_block"] is None


def test_whales_section_switches_to_live_data_with_a_real_event(client):
    test_client, _main, dash = client
    dash.set_meta("whaleflow_safe_scanned_block", "51234567")
    with dash._write_lock, dash._connect() as conn:
        conn.execute(
            """INSERT INTO whaleflow_events
                   (tx_hash, log_index, ts, token, amount_usdc, from_addr,
                    to_addr, block_number, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("0x" + "ab" * 32, 0, datetime.now(timezone.utc).isoformat(),
             "USDC", 250_000.0, "0x" + "cd" * 20, "0x" + "ef" * 20,
             51234000, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    w = _sections(test_client)["whales"]
    assert w["state"] == "live_data"
    assert w["count"] == 1
    assert w["all_time_count"] == 1
    whale = w["whales"][0]
    assert whale["amount_usdc"] == 250_000.0
    assert whale["from_label"] == "unknown" and whale["to_label"] == "unknown"
    assert whale["block"] == 51234000


# ── 4. СТАЖИ: the guards, proven alive on screen ────────────────────────────

def test_guards_section_probes_a_live_lock_and_shows_the_config(client):
    test_client, _main, _dash = client
    g = _sections(test_client)["guards"]
    assert g["lock_alive"] is True
    assert g["lock_probe_error"] is None
    assert g["config"]["c1_table"] == "payment_guards"
    assert g["config"]["c2_proof_confirmations"] == 12
    assert g["config"]["h2_endpoint_binding"] is True
    assert g["blocked_total"] == 0
    assert g["recent_blocks"] == []


def test_lock_probe_row_does_not_pollute_the_claim_count(client):
    test_client, _main, dash = client
    dash.claim_payment_tx("0x" + "aa" * 32, endpoint="/api/stats")
    g = _sections(test_client)["guards"]
    assert g["consumed_total"] == 1
    assert g["last_claim_endpoint"] == "/api/stats"
    assert g["last_claim_at"]


def test_a_blocked_replay_is_recorded_and_shown_in_the_guards_section(
        client, monkeypatch):
    """End-to-end: buy once with a proof, replay it, and the СТАЖИ block must
    show a real c1_replay row (durable, not a log-only claim)."""
    test_client, main, _dash = client
    tx = "0x" + "7c" * 32
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(main, "_paid_calls_usage", {})
    monkeypatch.setattr(main, "_verified_payments", set())
    monkeypatch.setattr(main, "_sales_history", [{
        "tx_hash": tx, "token": "USDC", "amount_usd": 0.05,
        "sender": "0x" + "11" * 20,
    }])
    header = base64.urlsafe_b64encode(json.dumps({
        "payer": "0x" + "11" * 20, "transaction_hash": tx,
        "amount_usdc": 0.05,
    }).encode()).decode().rstrip("=")

    first = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert first.status_code == 200
    replay = test_client.get("/api/stats", headers={"X-Payment-Proof": header})
    assert replay.status_code == 401

    g = _sections(test_client)["guards"]
    assert g["blocked_total"] >= 1
    assert g["by_kind"].get("c1_replay", 0) >= 1
    assert any(b["kind"] == "c1_replay" and b["endpoint"] == "/api/stats"
               for b in g["recent_blocks"])


# ── 5. ФЪНЪЛ: "днес" must NOT be the all-time total (regression) ─────────────

def test_funnel_today_is_not_the_all_time_total(client):
    test_client, _main, dash = client
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    today = datetime.now(timezone.utc).isoformat()
    with dash._write_lock, dash._connect() as conn:
        for ts in (yesterday, yesterday, yesterday, today):
            conn.execute(
                """INSERT INTO request_log
                       (ts, method, path, source, status_code, user_agent,
                        referer, funnel)
                   VALUES (?, 'GET', '/api/stats', 'api', 402, 'ua', '', NULL)""",
                (ts,),
            )
        conn.commit()
    funnel = _sections(test_client)["requests"]["funnel"]["/api/stats"]
    # 4 challenges in total, but only ONE happened today.
    assert funnel["challenges_total"] == 4
    assert funnel["challenges_today"] == 1
    assert funnel["challenges_today"] != funnel["challenges_total"]


def test_funnel_covers_every_paid_route(client):
    """A paid route missing from FUNNEL_ROUTES is invisible in the funnel —
    the whale flow was exactly that gap before Табло 2.0."""
    _test_client, main, _dash = client
    from integrations.dashboard_store import FUNNEL_ROUTES
    paid = set(main.X402_PAID_ENDPOINTS)
    assert set(FUNNEL_ROUTES) == paid, \
        f"funnel/paid-route drift: {paid ^ set(FUNNEL_ROUTES)}"


# ── 6. РЕАЛНИ МАРШРУТИ: the price on screen IS the price charged ────────────

def test_routes_section_price_matches_the_real_x402_challenge(client,
                                                             monkeypatch):
    """End-to-end: the price the vitrine promises must equal the price the
    live 402 body demands. This is the assertion that would have caught the
    $0.05-vs-$0.005 phantom before it reached the screen."""
    test_client, main, _dash = client
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    vitrine = {x["endpoint"]: x["price_usdc"]
               for x in _sections(test_client)["routes"]["routes"]}
    assert vitrine, "the vitrine must never be empty"
    for endpoint, price in vitrine.items():
        r = test_client.get(endpoint,
                            environ_base={"REMOTE_ADDR": "203.0.113.9"})
        assert r.status_code == 402, f"{endpoint} -> {r.status_code}"
        amount = int(r.get_json()["accepts"][0]["amount"])
        assert amount == round(float(price) * 1_000_000), \
            f"{endpoint}: 402 charges {amount} for the advertised ${price}"


def test_dashboard_page_no_longer_hardcodes_a_route_price(client):
    """The exact phantom that was live: /api/sales advertised at $0.05 while
    the 402 demanded $0.005. The routes table must ship no prices at all."""
    test_client, _main, _dash = client
    html = test_client.get("/dashboard").get_data(as_text=True)
    assert '<td class="num">0.05</td>' not in html
    assert '<td class="num">0.005</td>' not in html
    assert '<td class="num">0.003</td>' not in html


# ── 7. TWO LIVE SURFACES, ONE ANSWER ABOUT MONEY ────────────────────────────

def test_dashboard_stats_agrees_with_the_chain_backed_section(client):
    """AUDIT FIX: /api/dashboard-stats read RAM `_sales_history`, so a deploy
    left it at "0 sales / $0.00" while /api/dashboard/data reported the real
    9 on-chain transfers. Both public surfaces must report the same money."""
    test_client, _main, dash = client
    dash.seed_verified_sales()
    stats = test_client.get("/api/dashboard-stats").get_json()
    onchain = _sections(test_client)["onchain"]
    assert stats["total_volume_usd"] == onchain["total_usdc"] == 0.031
    assert stats["total_sales"] == onchain["total_count"] == 9
    assert stats["by_token"] == {"USDC": 0.031}
    # Legacy RAM key names stay available on every history row.
    assert len(stats["history"]) == 9
    for row in stats["history"]:
        assert row["amount_usd"] == row["amount_usdc"]
        assert row["timestamp"] == row["ts"]
        assert len(row["tx_hash"]) == 66


def test_dashboard_stats_still_reports_zero_on_an_empty_store(client):
    test_client, _main, _dash = client
    stats = test_client.get("/api/dashboard-stats").get_json()
    assert stats["total_volume_usd"] == 0.0
    assert stats["total_sales"] == 0


def test_dashboard_page_renders_all_the_new_sections(client):
    test_client, _main, _dash = client
    html = test_client.get("/dashboard").get_data(as_text=True)
    for element_id in ("sales-body", "clients-body", "whales-body",
                       "guard-body", "funnel-box", "routes-body"):
        assert f'id="{element_id}"' in html, f"missing section {element_id}"
    for fn in ("renderOnchain(", "renderClients(", "renderWhales(",
               "renderGuards(", "renderFunnel(", "renderRoutes("):
        assert fn in html, f"missing renderer {fn}"
    assert "setInterval(load, 45000)" in html  # "LIVE" really is live


