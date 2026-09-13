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
    assert o["total_usdc"] == 0.028
    assert o["total_count"] == 8
    assert o["external_payers"] == 2
    assert o["by_class"]["canary"] == {"count": 5, "total_usdc": 0.017}
    assert o["by_class"]["external"] == {"count": 2, "total_usdc": 0.008}
    assert o["by_class"]["sampler"] == {"count": 1, "total_usdc": 0.003}
    # FULL 66-char hashes + the real block numbers (no truncation, no zeros).
    assert len(o["history"]) == 8
    for row in o["history"]:
        assert len(row["tx_hash"]) == 66 and row["tx_hash"].startswith("0x")
        assert row["block_number"] > 50_000_000
        assert row["payer_class"] in {"canary", "sampler", "external"}


# ── 2. КЛИЕНТИ: external payers, with route honesty ─────────────────────────

def test_clients_section_lists_the_two_external_payers(client):
    test_client, _main, dash = client
    dash.seed_verified_sales()
    c = _sections(test_client)["clients"]
    assert c["count"] == 2
    by_wallet = {x["wallet"]: x for x in c["clients"]}
    assert set(by_wallet) == {
        "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7",
        "0x902dcf34e53695bdea2ffb354b1a2e58bd598256",
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
    8 on-chain transfers. Both public surfaces must report the same money."""
    test_client, _main, dash = client
    dash.seed_verified_sales()
    stats = test_client.get("/api/dashboard-stats").get_json()
    onchain = _sections(test_client)["onchain"]
    assert stats["total_volume_usd"] == onchain["total_usdc"] == 0.028
    assert stats["total_sales"] == onchain["total_count"] == 8
    assert stats["by_token"] == {"USDC": 0.028}
    # Legacy RAM key names stay available on every history row.
    assert len(stats["history"]) == 8
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


