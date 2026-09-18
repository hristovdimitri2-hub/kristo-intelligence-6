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
    assert o["external_payers"] == 2
    assert o["by_class"]["canary"] == {"count": 5, "total_usdc": 0.017}
    # 17.09: 0xA19F (98 distinct receivers) moved external → sampler, so the
    # chain truth reads 2 humans / $0.008 and 2 heartbeats / $0.006.
    assert o["by_class"]["external"] == {"count": 2, "total_usdc": 0.008}
    assert o["by_class"]["sampler"] == {"count": 2, "total_usdc": 0.006}
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
    assert c["count"] == 2
    by_wallet = {x["wallet"]: x for x in c["clients"]}
    assert set(by_wallet) == {
        "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7",
        "0x902dcf34e53695bdea2ffb354b1a2e58bd598256",
    }
    # 0xA19F LEFT this list on 17.09: the chain verdict (125 outgoing transfers
    # to 98 distinct receivers) made it known crawl infrastructure. Its payment
    # row stays in the on-chain history — only its class changed (sampler).
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
        self.sales = []
        self.guards = {}
        self.guard_events = []
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
        # ── payment_guards + guard_events (durable since 14.09) ────────────
        if s.startswith("INSERT INTO payment_guards"):
            tx = params[0]
            if tx in self.db.guards:
                self.rowcount = 0                  # ON CONFLICT DO NOTHING
            else:
                self.db.guards[tx] = {
                    "endpoint": params[1], "payer": params[2],
                    "amount_usdc": params[3], "consumed_at": params[4]}
                self.rowcount = 1
            return
        if s.startswith("DELETE FROM payment_guards"):
            self.rowcount = 1 if self.db.guards.pop(params[0], None) else 0
            return
        if s.startswith("SELECT tx_hash, endpoint FROM payment_guards"):
            self._rows = [{"tx_hash": k, "endpoint": v["endpoint"]}
                          for k, v in self.db.guards.items()]
            return
        if s.startswith("SELECT endpoint, COUNT(*) AS n FROM payment_guards"):
            agg = {}
            for v in self.db.guards.values():
                agg[v["endpoint"]] = agg.get(v["endpoint"], 0) + 1
            self._rows = [{"endpoint": k, "n": n} for k, n in agg.items()]
            return
        if s.startswith("SELECT consumed_at, endpoint FROM payment_guards"):
            items = sorted(self.db.guards.values(),
                           key=lambda v: v["consumed_at"], reverse=True)
            self._rows = ([{"consumed_at": items[0]["consumed_at"],
                            "endpoint": items[0]["endpoint"]}] if items else [])
            return
        if s.startswith("SELECT COUNT(*) AS n FROM payment_guards WHERE"):
            self._rows = [{"n": 1 if params[0] in self.db.guards else 0}]
            return
        if s.startswith("SELECT COUNT(*) AS n FROM payment_guards"):
            self._rows = [{"n": len(self.db.guards)}]
            return
        if s.startswith("INSERT INTO guard_events"):
            self.db.guard_events.append({
                "ts": params[0], "kind": params[1], "endpoint": params[2],
                "tx_hash": params[3], "detail": params[4]})
            self.rowcount = 1
            return
        if s.startswith("SELECT kind, COUNT(*) AS n FROM guard_events"):
            agg = {}
            for e in self.db.guard_events:
                agg[e["kind"]] = agg.get(e["kind"], 0) + 1
            self._rows = [{"kind": k, "n": n}
                          for k, n in sorted(agg.items(),
                                             key=lambda kv: -kv[1])]
            return
        if (s.startswith("SELECT COUNT(*) AS n FROM guard_events")
                and "substr" in s):
            self._rows = [{"n": sum(1 for e in self.db.guard_events
                                    if e["ts"][:10] == params[0])}]
            return
        if s.startswith("SELECT COUNT(*) AS n FROM guard_events"):
            self._rows = [{"n": len(self.db.guard_events)}]
            return
        if s.startswith("SELECT ts, kind, endpoint, tx_hash, detail FROM guard_events"):
            self._rows = list(reversed(self.db.guard_events))[:params[0]]
            return
        # ── onchain_sales (the canonical MONEY table, durable since 14.09) ──
        if s.startswith("INSERT INTO onchain_sales"):
            tx = params[0]
            if any(r["tx_hash"] == tx for r in self.db.sales):
                self.rowcount = 0                      # ON CONFLICT DO NOTHING
            else:
                self.db.sales.append({
                    "tx_hash": tx, "block_number": params[1], "ts": params[2],
                    "sender": params[3], "amount_usdc": params[4],
                    "payer_class": params[5], "payer_label": params[6],
                    "source": params[7],
                })
                self.rowcount = 1
            return
        if s.startswith("UPDATE onchain_sales"):
            n = 0
            for r in self.db.sales:
                if ((r["sender"] or "").lower() == params[2]
                        and r["payer_label"] != params[3]):
                    r["payer_class"], r["payer_label"] = params[0], params[1]
                    n += 1
            self.rowcount = n
            return
        if "COUNT(DISTINCT sender) AS n FROM onchain_sales" in s:
            ext = {r["sender"] for r in self.db.sales
                   if r["payer_class"] == "external"}
            self._rows = [{"n": len(ext)}]
            return
        if "GROUP BY payer_class" in s:
            agg = {}
            for r in self.db.sales:
                c = agg.setdefault(r["payer_class"], {"n": 0, "total": 0.0})
                c["n"] += 1
                c["total"] += r["amount_usdc"]
            self._rows = [{"payer_class": k, "n": v["n"], "total": v["total"]}
                          for k, v in agg.items()]
            return
        if "MIN(ts) AS first_ts" in s:                 # client aggregates
            agg = {}
            for r in self.db.sales:
                if r["payer_class"] != "external":
                    continue
                c = agg.setdefault(r["sender"], {
                    "sender": r["sender"], "n": 0, "total": 0.0,
                    "first_ts": r["ts"], "last_ts": r["ts"]})
                c["n"] += 1
                c["total"] += r["amount_usdc"]
                c["first_ts"] = min(c["first_ts"], r["ts"])
                c["last_ts"] = max(c["last_ts"], r["ts"])
            self._rows = sorted(agg.values(),
                                key=lambda c: (-c["total"], c["last_ts"]))
            return
        if "SELECT tx_hash, sender, amount_usdc, ts, block_number" in s:
            self._rows = sorted(
                [r for r in self.db.sales if r["payer_class"] == "external"],
                key=lambda r: (r["ts"], r["block_number"]))
            return
        if "SELECT tx_hash, block_number, ts, sender, amount_usdc" in s:
            rows = sorted(self.db.sales,
                          key=lambda r: (r["ts"], r["tx_hash"]), reverse=True)
            self._rows = rows[:params[-1]]
            return
        if s.startswith("SELECT COUNT(*) AS n") and "FROM onchain_sales" in s:
            rows = self.db.sales
            if "WHERE substr(ts, 1, 10) = ?" in s:
                rows = [r for r in rows if r["ts"][:10] == params[0]]
            self._rows = [{
                "n": len(rows),
                "total": round(sum(r["amount_usdc"] for r in rows), 6),
            }]
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

    # The onchain_sales bodies translated for PostgreSQL too (14.09): the money
    # queries are the LAST place a placeholder mistake may hide, because they
    # decide the number on screen.
    money = [
        """SELECT COUNT(*) AS n,
                  COALESCE(SUM(amount_usdc), 0.0) AS total
           FROM onchain_sales WHERE substr(ts, 1, 10) = ?""",
        """SELECT tx_hash, block_number, ts, sender, amount_usdc,
                  payer_class, payer_label, source
           FROM onchain_sales ORDER BY ts DESC, tx_hash DESC LIMIT ?""",
        """INSERT INTO onchain_sales
               (tx_hash, block_number, ts, sender, amount_usdc,
                payer_class, payer_label, source, recorded_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (tx_hash) DO NOTHING""",
        """UPDATE onchain_sales
           SET payer_class = ?, payer_label = ?
           WHERE lower(sender) = ? AND payer_label <> ?""",
    ]
    for body in money:
        translated = pg._q(body)
        assert "?" not in translated, body
        assert "onchain_sales" in translated
        assert translated.count("%s") == body.count("?"), body
        assert "%%" not in translated, "no literal percent is expected here"


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
    assert summary["external_payers"] == 2
    assert summary["by_class"]["external"] == {"count": 2,
                                               "total_usdc": 0.008}
    assert len(summary["history"]) == 9
    # Idempotent on the next boot: nothing inserted, nothing changed.
    assert store.seed_verified_sales()["inserted"] == 0
    assert store.sales_summary()["total_usdc"] == 0.031


# ── 13. THE MONEY TABLE IS DURABLE: it never drops below $0.031 ────────────

def test_onchain_sales_survives_a_deploy_without_re_seeding(tmp_path,
                                                            monkeypatch):
    """With DATABASE_URL set, the on-chain numbers must PERSIST — not be
    re-created by the seed on every boot.

    Before 14.09 `onchain_sales` was the last table on Render's ephemeral disk:
    every deploy zeroed it and the boot-time seed had to put the manifest back.
    That worked, but the number was reconstructed rather than kept, so the
    dashboard served whatever the re-scan had crawled back so far. Here the
    "deploy" is a brand-new store on a brand-new (empty) SQLite file pointing at
    the SAME database: if the sales live in Postgres the numbers never move, not
    even for one request.
    """
    from integrations.dashboard_store import DashboardStore

    db = _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

    first = DashboardStore(tmp_path / "before.db")
    assert first.history.backend == "postgresql"
    seeded = first.seed_verified_sales()
    assert seeded["mode"] == "bootstrap"
    assert seeded["inserted"] == 9
    assert first.sales_summary()["total_usdc"] == 0.031

    # "deploy": new process, new ephemeral file, same database. NO re-seed.
    second = DashboardStore(tmp_path / "after.db")
    summary = second.sales_summary()
    assert summary["total_usdc"] == 0.031, "the money table did not survive"
    assert summary["total_count"] == 9
    assert summary["external_payers"] == 2
    assert summary["by_class"]["external"] == {"count": 2, "total_usdc": 0.008}
    assert second.seed_verified_sales()["inserted"] == 0
    # The money table really is on the PostgreSQL side, not on the local file
    # that the deploy wipes.
    joined = " ".join(db.sql)
    assert "CREATE TABLE IF NOT EXISTS onchain_sales" in joined
    assert "ON CONFLICT (tx_hash) DO NOTHING" in joined
    assert "block_number BIGINT" in joined


def test_the_seed_is_a_bootstrap_and_never_a_cover_up(tmp_path, monkeypatch):
    """THE acceptance criterion for the Postgres move.

    Deleted database -> the seed bootstraps 9 rows -> a live chain scan adds a
    10th WITHOUT resetting anything, and a later boot cannot undo it.

    This is the property that makes the seed safe to run on every boot: it is
    insert-only and never re-labels, overwrites or deletes a row, so what the
    chain says always beats what the hand-written manifest says.
    """
    from datetime import datetime, timezone

    from integrations.dashboard_store import DashboardStore

    _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")

    # 1. An empty (wiped) database: bootstrap.
    store = DashboardStore(tmp_path / "wiped.db")
    seeded = store.seed_verified_sales()
    assert seeded["mode"] == "bootstrap" and seeded["inserted"] == 9
    assert store.sales_summary()["total_usdc"] == 0.031

    # 2. A LIVE scan discovers a 10th transfer — a real customer, a new wallet.
    tenth = "0x" + "a1" * 32
    assert store.record_sale(
        tenth, 0.007, sender="0x" + "77" * 20, block_number=51_300_000,
        ts=datetime.now(timezone.utc), source="live") is True
    after_scan = store.sales_summary()
    assert after_scan["total_usdc"] == 0.038          # 0.031 + 0.007, no reset
    assert after_scan["total_count"] == 10
    assert after_scan["external_payers"] == 3       # 2 humans + this new wallet

    # 3. The next boot re-runs the seed: nothing is touched.
    assert store.seed_verified_sales()["mode"] == "already_complete"
    summary = store.sales_summary()
    assert summary["total_usdc"] == 0.038, "the seed rolled the chain back"
    assert summary["total_count"] == 10
    row = [h for h in summary["history"] if h["tx_hash"] == tenth][0]
    assert row["source"] == "live", "the seed relabelled a scan-discovered row"
    assert row["payer_class"] == "external"

    # 4. A duplicate seen twice (settle path + monitor) is still one row.
    assert store.record_sale(tenth, 0.007, "0x" + "77" * 20, 51_300_000) is False
    assert store.sales_summary()["total_count"] == 10


def test_the_seed_self_heals_partial_loss_without_overwriting(tmp_path,
                                                              monkeypatch):
    """A HALF-lost table is repaired, and the surviving rows stay untouched.

    Insert-only lets two properties coexist: a missing row is restored
    (self-heal) while a present one is left exactly as it is — including a row
    the chain scan found first, which the manifest may never override.
    """
    from datetime import datetime, timezone

    from integrations.dashboard_store import DashboardStore
    from integrations.verified_sales import VERIFIED_SALES

    monkeypatch.delenv("DATABASE_URL", raising=False)
    store = DashboardStore(tmp_path / "partial.db")

    newest = max(VERIFIED_SALES, key=lambda r: r["block_number"])
    assert store.record_sale(
        newest["tx_hash"], newest["amount_usdc"], sender=newest.get("sender"),
        block_number=newest["block_number"],
        ts=datetime.fromtimestamp(newest["ts_unix"], tz=timezone.utc),
        source="live") is True
    assert store.sales_summary()["total_count"] == 1

    healed = store.seed_verified_sales()
    assert healed["mode"] == "self_heal"
    assert healed["inserted"] == 8                    # the other eight rows
    assert healed["present"] == 9
    assert healed["total_usdc"] == 0.031
    summary = store.sales_summary()
    row = [h for h in summary["history"]
           if h["tx_hash"] == (newest["tx_hash"] or "").lower()][0]
    assert row["source"] == "live", "self-heal overwrote a scan row"
    # Idempotent: a third boot changes nothing at all.
    third = store.seed_verified_sales()
    assert third["inserted"] == 0 and third["mode"] == "already_complete"
    assert third["total_usdc"] == 0.031
    assert third["present"] == 9


def test_a_consumed_payment_proof_stays_consumed_after_a_restart(tmp_path,
                                                                monkeypatch):
    """Condition 3: a replay is still blocked AFTER a "restart".

    Hard-won history of this guard: the claim lived in an in-RAM set (gone on
    restart), then in the ephemeral SQLite file (gone on deploy — every consumed
    proof was reopened). It is now a row in the durable store, so the second
    process must refuse even though its OWN cache is empty. That emptiness is the
    point: it proves the database is the truth and the cache is only a fast path.
    """
    from integrations.dashboard_store import DashboardStore

    db = _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")
    tx = "0x" + "ab" * 32

    first = DashboardStore(tmp_path / "a.db")
    assert first.claim_payment_tx(tx, endpoint="/api/v1/signal",
                                  payer="0x" + "cd" * 20,
                                  amount_usdc=0.003) is True
    assert first.payment_guard_stats()["consumed_total"] == 1

    # "restart": a new process (cold cache) on a brand-new local file.
    second = DashboardStore(tmp_path / "b.db")
    assert second.history._claimed_cache == set(), "the cache must be cold here"
    assert second.claim_payment_tx(tx, endpoint="/api/v1/signal") is False
    # Re-pointed at a different route: the H2 binding violation, also refused.
    assert second.claim_payment_tx(tx, endpoint="/api/v1/whaleflow") is False
    # Nothing was re-consumed into a second row.
    assert second.payment_guard_stats()["consumed_total"] == 1
    assert len(db.guards) == 1
    # The lock refuses REPLAYS, not payments: a fresh hash still works.
    assert second.claim_payment_tx("0x" + "11" * 32) is True
    # And the dashboard is told WHERE the lock lives.
    stats = second.guard_stats()
    assert stats["lock_backend"] == "postgresql"
    assert stats["lock_durable"] is True
    assert stats["lock_alive"] is True


def test_an_unreachable_lock_refuses_the_payment_fail_closed(tmp_path,
                                                             monkeypatch):
    """Condition 4: database unreachable → REFUSE, never allow.

    A guard that fails OPEN is worse than no guard: it would hand paid content to
    a replay exactly when the lock cannot be checked. This asserts the safe
    direction, that the log shouts about it, and that the fast path never becomes
    a second door in.
    """
    import logging

    from integrations.dashboard_store import DashboardStore, HistoryStore

    _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")
    store = DashboardStore(tmp_path / "down.db")

    # Claim one hash while the lock is healthy (this also fills the fast path).
    warm = "0x" + "33" * 32
    assert store.claim_payment_tx(warm, endpoint="/api/v1/signal") is True

    def _boom(self):
        raise RuntimeError("database is down")
    monkeypatch.setattr(HistoryStore, "_pg_connection", _boom)

    messages = []

    class _Handler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = _Handler()
    logger = logging.getLogger("integrations.dashboard_store")
    logger.addHandler(handler)
    try:
        before = len([m for m in messages if "fail-closed" in m])
        # (a) A hash already claimed here is refused by the FAST PATH, without
        #     even trying the database — so no new fail-closed log line.
        assert store.claim_payment_tx(warm, endpoint="/api/v1/signal") is False
        assert len([m for m in messages
                    if "fail-closed" in m]) == before, \
            "the fast path should not need the database at all"
        # (b) A cold hash with the lock unreachable is REFUSED (fail-closed).
        assert store.claim_payment_tx("0x" + "44" * 32) is False
        assert len([m for m in messages
                    if "fail-closed" in m]) == before + 1, \
            "the refusal must be logged loudly"
        # (c) Telemetry must never raise, even with the database down.
        store.record_guard_event("replay_blocked", "/api/v1/signal",
                                 "0x" + "44" * 32, "lock unreachable")
        # (d) The dashboard reports the lock as DEAD instead of pretending.
        stats = store.guard_stats()
        assert stats["lock_alive"] is False
        assert stats["lock_probe_error"]
        assert stats["lock_durable"] is True
        # (e) Telemetry degrades HONESTLY instead of taking the dashboard down.
        stats = store.payment_guard_stats()
        assert stats["consumed_total"] is None
        assert stats["stats_error"]
        assert stats["lock_backend"] == "postgresql"
        assert stats["lock_durable"] is True
    finally:
        logger.removeHandler(handler)


def test_route_evidence_comes_from_the_same_backend_as_the_lock(tmp_path,
                                                                monkeypatch):
    """The CLIENTS section's route proof must be read from the LOCK's backend.

    Reading the sales rows from one database and the granted claims from another
    is how the section would silently lose its only honest route evidence and
    fall back to "the amount could be any of these routes". Both come from the
    durable store now, so a claimed payment is named by its guard row.
    """
    from integrations.dashboard_store import DashboardStore

    _install_fake_postgres(monkeypatch, _FakePostgres())
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake/db")
    store = DashboardStore(tmp_path / "evidence.db")

    buyer = "0x" + "9f" * 20
    tx = "0x" + "5a" * 32
    assert store.record_sale(tx, 0.003, sender=buyer, block_number=51_400_000,
                             source="live") is True
    # No claim yet → the section can only say "the price fits these routes".
    before = store.clients_summary(price_map={"/api/v1/signal": 0.003,
                                              "/api/v1/whaleflow": 0.003})
    assert before["count"] == 1
    assert before["clients"][0]["routes"][0]["evidence"] == "price_ambiguous"

    # The guard grants the proof on ONE route → that route is now FACT.
    assert store.claim_payment_tx(tx, endpoint="/api/v1/whaleflow",
                                  payer=buyer, amount_usdc=0.003) is True
    after = store.clients_summary(price_map={"/api/v1/signal": 0.003,
                                             "/api/v1/whaleflow": 0.003})
    route = after["clients"][0]["routes"][0]
    assert route["route"] == "/api/v1/whaleflow"
    assert route["evidence"] == "payment_guard"
    assert after["clients"][0]["tx_hashes"] == [tx]


def _group_by_violations(sql: str) -> list:
    """Columns selected bare while the query groups by something else.

    PostgreSQL rejects them (GroupingError); SQLite silently allows them. This
    is a pure SQL SEMANTICS check, which is exactly the kind of bug a
    Python-emulated fake database cannot catch — it never parses the SQL.
    """
    import re

    def split_top(text: str) -> list:
        """Split on commas at parenthesis depth 0 (COALESCE(SUM(x), 0.0) is ONE
        item — splitting naively turns it into two and invents a violation)."""
        parts, depth, cur = [], 0, ""
        for ch in text:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        return parts

    text = " ".join(sql.split())
    up = text.upper()
    # Only real query bodies: a docstring that merely MENTIONS the clause (as the
    # one documenting this very bug does) must not crash the checker.
    if not all(k in up for k in ("SELECT", "FROM", "GROUP BY")):
        return []
    if up.index("SELECT") > up.index("FROM"):
        return []
    selected = text[up.index("SELECT") + 6:up.index("FROM")]
    grouped_raw = text[up.index("GROUP BY") + 8:]
    for stop in ("ORDER BY", "LIMIT", "HAVING"):
        if stop in grouped_raw.upper():
            grouped_raw = grouped_raw[:grouped_raw.upper().index(stop)]
    grouped = {c.strip().strip('"').lower() for c in split_top(grouped_raw)}
    grouped_plain = {c.split("(")[0].strip().lower() for c in grouped}
    bad = []
    for item in split_top(selected):
        body = re.split(r"\s+as\s+", item.strip(), flags=re.I)[0].strip()
        low = body.lower()
        if any(fn in low for fn in ("count(", "sum(", "min(", "max(", "avg(")):
            continue
        col = low.split(".")[-1].strip().strip('"')
        if col in grouped or col in grouped_plain:
            continue
        bad.append(item.strip())
    return bad


def test_group_by_survives_both_dialects():
    """The move to PostgreSQL (14.09) exposed a query SQLite had always allowed.

    /api/dashboard/data returned HTTP 500 in production:
        psycopg.errors.GroupingError: column "onchain_sales.sender" must appear
        in the GROUP BY clause or be used in an aggregate function
    The body was `SELECT sender, COUNT(*) … GROUP BY lower(sender)` — fine on
    SQLite, illegal on PostgreSQL. The fake-Postgres tests could not see it (they
    execute the statement in Python, so they never enforce SQL validity), so the
    SQL itself is checked here, statically, for EVERY grouped query in the store.
    """
    import inspect
    import re

    from integrations import dashboard_store

    src = inspect.getsource(dashboard_store)
    bodies = [b for b in re.findall(r'"""(.*?)"""', src, re.S)
              if all(k in b.upper() for k in ("SELECT", "FROM", "GROUP BY"))]
    assert bodies, "no GROUP BY query found — did the store move?"
    # The external-payer aggregate MUST be among them (it is the 14.09 regression).
    assert any("onchain_sales" in b for b in bodies)
    bad = {b.strip()[:80]: _group_by_violations(b) for b in bodies}
    bad = {k: v for k, v in bad.items() if v}
    assert not bad, f"PostgreSQL would reject these: {bad}"

    # The specific regression, pinned: the external-payer aggregate selects the
    # raw `sender`, so it must group by the raw column.
    joined = " ".join(bodies)
    assert "GROUP BY sender" in joined
    assert "GROUP BY lower(sender)" not in joined
    # Sanity: the checker really does flag the old buggy form.
    buggy = ("SELECT sender, COUNT(*) AS n FROM onchain_sales "
             "GROUP BY lower(sender)")
    assert _group_by_violations(buggy) == ["sender"]


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
             "USDC", 6_000_000.0, "0x" + "cd" * 20, "0x" + "ef" * 20,
             51234000, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    w = _sections(test_client)["whales"]
    assert w["state"] == "live_data"
    assert w["count"] == 1
    assert w["all_time_count"] == 1
    whale = w["whales"][0]
    assert whale["amount_usdc"] == 6_000_000.0
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
    # The section must STATE where the lock lives (14.09: the lock moved to the
    # durable store). Without DATABASE_URL the test fixture is SQLite, so the
    # honest answer here is sqlite/False — a claim of durability would be a lie.
    assert g["lock_backend"] == "sqlite"
    assert g["lock_durable"] is False
    assert g["stats_error"] is None


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




# ── 9. THE GUARDS PANEL: "no data" must never look like "the guard is dead" ──

def test_a_missing_guards_section_is_not_painted_as_a_red_alarm(client):
    """The owner's screen showed a RED lamp, the word СПРЯЛ and "undefined" in
    every PAYMENT GUARDS card while the guards were provably alive
    (lock_alive=True, C1 in PostgreSQL, consumed_total=1 live).

    Cause: `renderGuards(s.guards || {})` — an ABSENT section became `{}`, and the
    renderer read `undefined` as "the lock is dead". No data and a measured
    failure must not look the same, and a numeric card must never print
    "undefined". The lock's storage is also named from the payload: the panel kept
    saying "SQLite" long after the lock moved to PostgreSQL.
    """
    test_client, _main, _dash = client
    html = test_client.get("/dashboard").get_data(as_text=True)

    # 1. the honest branch: unknown ⇒ amber + words, red ONLY for a failed probe
    assert "typeof g.lock_alive === 'boolean'" in html
    assert "НЯМА ДАННИ" in html
    # 2. numbers fall back to a dash instead of the string "undefined"
    assert "v === null || v === undefined ? '—'" in html
    # 3. the backend is read from the payload, never hardcoded
    assert "C1 replay-lock (SQLite " not in html
    assert "g.lock_backend" in html

    # the live payload still carries the real state (this is what "ЖИВ" renders)
    guards = _sections(test_client)["guards"]
    assert guards["lock_alive"] is True
    assert guards["lock_backend"] in ("postgresql", "sqlite")


# ── 10. THE STRIPE↔CRM LINK: cross-checked, never assumed ───────────────────

def _set_stripe_snapshot(main, monkeypatch, **snapshot):
    base = {"available": True, "payments": [], "state": "fresh",
            "fetched_at": None, "reason": None}
    base.update(snapshot)
    monkeypatch.setattr(main, "_stripe_snapshot", base)


def test_the_stripe_link_cross_checks_the_numbers(client, monkeypatch):
    """`source` must name the feed that produced the ROWS (the CRM), and the Stripe
    feed must be presented as a SECOND OPINION: its own list of paid sessions has
    to agree with the CRM records on screen.

    Until 17.09 nobody could tell whether they agreed, because one
    `metadata.get("plan")` on a StripeObject raised every 60 seconds and the feed
    reported `stripe_list_unavailable` — so the section showed "Stripe snapshot: не"
    and fell back silently. All three states are now visible in words:
    недостъпен / сверка ОК / РАЗЛИКА.
    """
    test_client, main, _dash = client

    _set_stripe_snapshot(main, monkeypatch, available=False,
                         reason="stripe_list_unavailable")
    crm = _sections(test_client)["crm_stripe"]
    assert crm["source"] == "crm_paid_events", "the label must name the CRM rows"
    assert crm["stripe_link"]["status"] == "unavailable"
    assert "недостъпен" in crm["stripe_link"]["detail"]

    # Stripe agrees with the CRM (built from whatever the CRM actually holds)
    _set_stripe_snapshot(main, monkeypatch, payments=[
        {"amount_usd": i["amount_usd"], "plan": i["plan"],
         "checkout_id": "cs_live_aligned", "provider": "stripe"}
        for i in crm["items"]])
    link = _sections(test_client)["crm_stripe"]["stripe_link"]
    assert link["status"] == "in_sync", link
    assert "съвпадат" in link["detail"]

    # Stripe holds money the CRM does not know about — never silent
    _set_stripe_snapshot(main, monkeypatch, payments=[
        {"amount_usd": 99.0, "plan": "pro", "checkout_id": "cs_live_ghost",
         "provider": "stripe"}])
    link = _sections(test_client)["crm_stripe"]["stripe_link"]
    assert link["status"] == "mismatch", link
    assert "РАЗЛИКА" in link["detail"]

    html = test_client.get("/dashboard").get_data(as_text=True)
    assert 'id="crm-note"' in html and "stripe_link" in html
# ── 11. REFUNDS ON SCREEN: paid, refunded and net are three numbers ─────────

def test_the_offchain_section_separates_paid_from_refunded(client, monkeypatch,
                                                           tmp_path):
    """A refunded sale must stay visible as a SALE while the return is its own
    number. Until 17.09 the section showed $34.80 "платено" and nothing else, even
    after the money was returned — the dashboard would have kept counting money that
    was no longer there.
    """
    test_client, main, _dash = client
    from integrations.crm_store import CRMStore

    store = CRMStore(tmp_path / "crm.db")
    monkeypatch.setattr(main, "crm_store", store)
    store.add_lead(main.LeadRecord(email="buyer@example.com", source="website",
                                   campaign="launch", plan="Starter"))
    store.mark_paid("buyer@example.com", 34.80, "starter",
                    checkout_id="cs_live_first_paid",
                    paid_at="2026-09-16T08:56:08+00:00")
    store.mark_refund("buyer@example.com", 34.80, "2026-09-17T06:23:30+00:00")

    crm = _sections(test_client)["crm_stripe"]
    assert crm["total_usd"] == 34.80, "the sale is what was charged"
    assert crm["refunded_usd"] == 34.80 and crm["refunded_count"] == 1
    assert crm["net_usd"] == 0.0, "net = paid − refunded"
    assert crm["refund_note"] == "върнати: $34.80 (1 от 1)"
    item = crm["items"][0]
    assert item["refunded_usd"] == 34.80 and item["refunded_at"]
    assert item["checkout_id"] == "cs_live_first_paid"

    html = test_client.get("/dashboard").get_data(as_text=True)
    assert "Върнато (" in html, "the refund card must be on the page"
    assert "refund_note" in html, "the note line must be rendered"
