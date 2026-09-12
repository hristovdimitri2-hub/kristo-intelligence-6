"""Canonical dashboard (priority-0 invariants).

Covers:
  * SQLite persistence — a store "restart" (reopen) must NOT zero numbers
  * payer taxonomy: canary (Chet) / sampler (crawler) / external (real)
  * dedup by normalized tx hash (settle path + monitor see the same tx)
  * day-zero retro visibility of the first external payment
  * /api/dashboard/data sections; CRM/Stripe NEVER mixed into on-chain totals
  * /dashboard renders; /nexus redirects (simulated feed retired)
  * scan_window/scan_increment against a mocked Web3 (no live RPC in tests)
"""

import sys
import types
from datetime import datetime, timezone

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)
    return main.app.test_client(), main, dash


def test_store_persists_across_reopen(tmp_path):
    """Priority-0 invariant: deploy/restart must NOT reset dashboard numbers."""
    from integrations.dashboard_store import DashboardStore

    db_path = tmp_path / "dashboard_state.db"
    store = DashboardStore(db_path)
    assert store.record_sale(
        tx_hash="0xabc1", amount_usdc=0.003, sender="0x9999999999999999999999999999999999999999",
        block_number=100, source="scan",
    )
    store = None

    # "restart": a brand-new instance over the same file (what a deploy does)
    reopened = DashboardStore(db_path)
    summary = reopened.sales_summary()
    assert summary["total_count"] == 1
    assert summary["total_usdc"] == 0.003


def test_reclassify_known_payers_updates_stored_rows(tmp_path, monkeypatch):
    """A sale recorded BEFORE its payer is fingerprinted stays honest: the
    reclassify pass flips it to the heartbeat bucket once taxonomy evolves."""
    from integrations import dashboard_store as ds
    from scripts import competitor_recon as recon

    store = ds.DashboardStore(tmp_path / "d.db")
    # Production sequence: sale lands while the wallet is still unknown.
    monkeypatch.setattr(recon, "KNOWN_PAYERS", {})
    store.record_sale(
        tx_hash="0xrr1", amount_usdc=0.003,
        sender="0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0", block_number=1,
    )
    assert store.sales_summary()["external_payers"] == 1

    # Taxonomy evolves (08.09: crawler fingerprinted) → reclassify.
    monkeypatch.setattr(
        recon, "KNOWN_PAYERS",
        {"0x54e163e9b8edda194d83f46add921bfa5fc5f4e0": "market_crawler_54e1"},
    )
    assert store.reclassify_known_payers() == 1
    s = store.sales_summary()
    assert s["external_payers"] == 0
    assert s["by_class"]["sampler"]["count"] == 1
    assert s["history"][0]["payer_label"] == "market_crawler_54e1"


def test_payer_classification_canary_sampler_external():
    from integrations.dashboard_store import classify_payer

    chet = "0x7e6b6556322c4e26c567a867964ac793f5ee2b1c"
    sampler = "0xc59e74ed6386b2a12d892fff2509a6965a0498dc"
    assert classify_payer(chet)[0] == "canary"
    assert classify_payer(chet)[1] == "chet_payapi_verification"
    assert classify_payer(sampler)[0] == "sampler"
    assert classify_payer("0x4dB7" + "1" * 38)[0] == "external"
    assert classify_payer("")[0] == "external"


def test_record_sale_dedups_by_normalized_tx_hash(tmp_path):
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    first = store.record_sale(tx_hash="0xABC1", amount_usdc=0.005, sender="0x01" * 20)
    second = store.record_sale(tx_hash="0xabc1", amount_usdc=0.005, sender="0x01" * 20)
    assert first is True and second is False
    assert store.sales_summary()["total_count"] == 1


def test_first_external_payment_visible_from_day_zero(tmp_path):
    """The very first external payment (0x4dB7…, $0.003, 06.09 06:41 UTC)
    must appear in the history with the EXTERNAL label."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    when = datetime(2026, 9, 6, 6, 41, 0, tzinfo=timezone.utc)
    store.record_sale(
        tx_hash="0xext0001",
        amount_usdc=0.003,
        sender="0x4db7" + "1" * 38,
        block_number=42,
        ts=when,
        source="retro",
    )
    summary = store.sales_summary()
    assert summary["external_payers"] == 1
    top = summary["history"][0]
    assert top["payer_class"] == "external"
    assert top["amount_usdc"] == 0.003
    assert top["ts"].startswith("2026-09-06T06:41")


def test_request_log_persists_and_breaks_down_channels(tmp_path):
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    store.record_request("GET", "/", "web", 200, user_agent="TestBot/1.0", funnel="x")
    store.record_request("GET", "/api/stats", "api", 200, user_agent="agent", funnel="x")
    store.record_request("GET", "/api/stats", "api", 402, user_agent="agent")
    summary = store.requests_summary()
    assert summary["total"] == 3
    assert summary["by_channel"] == [{"channel": "x", "n": 2}]
    assert {"source": "api", "n": 2} in summary["by_source"]
    assert summary["top_paths"][0] == {"path": "/api/stats", "n": 2}


def test_internal_health_noise_counted_separately(tmp_path):
    """The keep-alive UA (Render/1.0) must NOT pollute the clean numbers —
    it is our own /health ping + Render health checks, not customer traffic."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    store.record_request("GET", "/health", "web", 200,
                         user_agent="Render/1.0")
    store.record_request("GET", "/health", "web", 200,
                         user_agent="Render/1.0")
    store.record_request("GET", "/api/v1/signal", "api", 200,
                         user_agent="x402-agent/1.0")
    summary = store.requests_summary()
    assert summary["total"] == 3
    assert summary["internal_noise"]["total"] == 2
    assert summary["total_clean"] == 1
    assert summary["by_source_clean"] == [{"source": "api", "n": 1}]


def test_payment_funnel_challenges_vs_paid(tmp_path):
    """Funnel per paid route: 402 challenges -> paid (200) follow-ups,
    today + total — the 'caught by the hand' metric."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    # signal: 3 challenges, 1 paid (today)
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 402, user_agent="node")
    store.record_request("GET", "/api/v1/signal", "api", 200, user_agent="node")
    # stats: 1 challenge, no paid
    store.record_request("GET", "/api/stats", "api", 402, user_agent="node")
    f = store.requests_summary()["funnel"]
    assert f["/api/v1/signal"]["challenges_today"] == 3
    assert f["/api/v1/signal"]["paid_today"] == 1
    assert f["/api/v1/signal"]["challenges_total"] == 3
    assert f["/api/stats"]["challenges_today"] == 1
    assert f["/api/stats"]["paid_today"] == 0
    # conversion formula used by monitor/dashboard: 1/3 -> 33.3%
    rate = round(100.0 * f["/api/v1/signal"]["paid_today"]
                 / f["/api/v1/signal"]["challenges_today"], 1)
    assert rate == 33.3


def test_top_user_agents_and_hourly_peaks(tmp_path):
    """Full-day UA top-10 (clean) + hourly aggregation for peak analysis."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    for _ in range(3):
        store.record_request("GET", "/api/v1/signal", "api", 402,
                             user_agent="CarbonMonitor/0.1 healthcheck")
    for _ in range(2):
        store.record_request("GET", "/openapi.json", "web", 200,
                             user_agent="Mozilla/5.0 (compatible; Agent402/1.0)")
    store.record_request("GET", "/health", "web", 200, user_agent="Render/1.0")
    s = store.requests_summary()
    uas = {u["user_agent"]: u["n"] for u in s["top_user_agents"]}
    assert uas["CarbonMonitor/0.1 healthcheck"] == 3
    assert uas["Mozilla/5.0 (compatible; Agent402/1.0)"] == 2
    assert "Render/1.0" not in uas                     # noise excluded
    assert isinstance(s["hourly"], list)
    total_hourly = sum(h["n"] for h in s["hourly"])
    assert total_hourly >= 6                            # today's rows
    assert all("noise" in h for h in s["hourly"])


def test_payapi_state_roundtrip_and_baseline(tmp_path):
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    baseline = store.get_payapi_state()
    assert baseline["available"] is False
    assert "baseline" in baseline["reason"]

    store.save_payapi_state({
        "reliability": {"band": None, "score": None, "computed_at": None},
        "ranks": {"eth": {"position": None, "total": 12}},
    })
    state = store.get_payapi_state()
    assert state["available"] is True
    assert state["reliability"]["band"] is None  # unscored baseline
    assert state["ranks"]["eth"]["position"] is None


def test_dashboard_data_sections_and_crm_never_in_onchain(client):
    """The (г) CRM/Stripe section must stay OUT of on-chain totals."""
    test_client, main, dash = client
    # Seed: one real on-chain sale + one off-chain CRM paid lead ($79.02).
    dash.record_sale(
        tx_hash="0xonsale1", amount_usdc=0.003,
        sender="0x4db7" + "1" * 38, block_number=7,
        ts=datetime(2026, 9, 6, 6, 41, 0, tzinfo=timezone.utc),
    )
    from integrations.crm_store import LeadRecord
    lead = LeadRecord(email="investor@crypto.io", source="test", campaign="vip",
                      amount_usd=79.02, payment_status="paid")
    main.crm_store.add_lead(lead)

    # Warmup request — its after_request hook persists it into the log store.
    test_client.get("/health")

    resp = test_client.get("/api/dashboard/data")
    assert resp.status_code == 200
    payload = resp.get_json()
    sections = payload["sections"]

    onchain = sections["onchain"]
    assert onchain["total_usdc"] == 0.003      # ONLY the chain transfer
    assert onchain["total_count"] == 1
    assert onchain["external_payers"] == 1
    assert onchain["by_class"]["external"]["total_usdc"] == 0.003

    crm = sections["crm_stripe"]
    assert crm["excluded_from_onchain"] is True
    assert crm["total_usd"] == 79.02           # visible only in its own section
    assert crm["items"][0]["customer"].startswith("in")  # masked, not the full email
    assert "investor@crypto.io" not in resp.get_data(as_text=True)

    assert sections["requests"]["total"] >= 1  # this very request is logged
    assert "invariant" in payload


def test_dashboard_page_renders_and_nexus_redirects(client):
    test_client, main, _ = client
    resp = test_client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "On-Chain Sales" in html
    assert "/api/dashboard/data" in html
    assert "OFF-CHAIN" in html  # CRM section labelled and toggle-hidden

    redir = test_client.get("/nexus")
    assert redir.status_code == 302
    assert redir.headers["Location"].endswith("/dashboard")


def test_signal_challenge_description_sells_and_v2_untouched(client, monkeypatch):
    """The 402 challenge description for /api/v1/signal now sells the product
    (what the agent gets, freshness) — while the canonical x402 v2 shape
    (scheme, network, atomic amount, payTo, asset) stays byte-identical."""
    test_client, main, _ = client
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)  # strict x402 for this test
    resp = test_client.get("/api/v1/signal")
    assert resp.status_code == 402
    payload = resp.get_json()

    desc = payload["resource"]["description"]
    assert "Live DeFi trading signal" in desc
    assert "confidence" in desc and "reasoning" in desc
    assert "under 5 minutes" in desc

    # Canonical v2 shape untouched
    acc = payload["accepts"][0]
    assert acc["scheme"] == "exact"
    assert acc["network"] == "eip155:8453"
    assert acc["amount"] == "3000"                  # atomic units
    assert acc["payTo"] == main.X402_RECEIVER_ADDRESS
    assert acc["asset"] == main.X402_USDC_CONTRACT
    assert acc["extra"] == {"name": "USD Coin", "version": "2"}
    assert payload["x402Version"] == 2
    assert payload["error"] == "payment_required"


# ── scan_window / scan_increment with a mocked Web3 (no live RPC) ─────────
def _install_fake_web3(monkeypatch, transfers, blocks_ts, latest=10_000):
    """Fake web3 module: Web3(Web3.HTTPProvider(url)) with canned get_logs."""
    fake = types.ModuleType("web3")

    class FakeEth:
        def __init__(self):
            self.block_number = latest

        def is_connected(self):
            return True

        def get_logs(self, spec):
            lo, hi = spec["fromBlock"], spec["toBlock"]
            return [t["log"] for t in transfers if lo <= t["log"]["blockNumber"] <= hi]

        def get_block(self, n):
            return {"timestamp": blocks_ts.get(n, 0)}

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url, request_kwargs=None: ("provider", url))

        def __init__(self, provider):
            self.eth = FakeEth()

        def is_connected(self):
            return True

        @staticmethod
        def is_address(a):
            return isinstance(a, str) and len(a) == 42

        @staticmethod
        def to_checksum_address(a):
            return a

        @staticmethod
        def to_hex(h):
            return ("0x" + bytes(h).hex()) if isinstance(h, (bytes, bytearray)) else str(h)

    fake.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", fake)
    return fake


def test_scan_window_persists_transfers_with_timestamps(tmp_path, monkeypatch):
    from integrations.dashboard_store import DashboardStore
    from datetime import datetime as _dt, timezone as _tz

    def fake_stamps(self, w3, blocks):
        return {b: _dt.fromtimestamp(blocks_ts.get(b, 0), tz=_tz.utc)
                for b in blocks}
    monkeypatch.setattr(DashboardStore, "_block_timestamps", fake_stamps)

    receiver = "0xd" + "0" * 39
    monkeypatch.setenv("BASE_FEE_RECEIVER", receiver)
    ts = 1757138460  # arbitrary block time
    blocks_ts = {9_999: ts, 10_000: ts + 2}
    def fake_stamps(self, w3, blocks):
        return {b: _dt.fromtimestamp(blocks_ts.get(b, 0), tz=_tz.utc)
                for b in blocks}
    monkeypatch.setattr(DashboardStore, "_block_timestamps", fake_stamps)
    log1 = {
        "topics": [b"\x01", bytes.fromhex("aa" * 32), bytes.fromhex("bb" * 32)],
        "data": (3_000).to_bytes(32, "big"),       # $0.003 external
        "blockNumber": 9_999,
        "transactionHash": bytes.fromhex("11" * 32),
    }
    log2 = {
        # Known canary (Chet) as sender → topics[1] = 32-byte padded address
        "topics": [b"\x01",
                   bytes.fromhex("00" * 12 + "7e6b6556322c4e26c567a867964ac793f5ee2b1c"),
                   bytes.fromhex("bb" * 32)],
        "data": (5_000).to_bytes(32, "big"),       # $0.005 canary
        "blockNumber": 10_000,
        "transactionHash": bytes.fromhex("22" * 32),
    }
    _install_fake_web3(
        monkeypatch,
        [{"log": log1}, {"log": log2}],
        {9_999: ts, 10_000: ts + 2},
    )
    store = DashboardStore(tmp_path / "d.db")
    added = store.scan_window(9_999, 10_000, rpc_url="http://fake")
    assert added == 2
    summary = store.sales_summary()
    assert summary["total_usdc"] == 0.008
    classes = {h["tx_hash"]: h["payer_class"] for h in summary["history"]}
    assert classes["0x" + "11" * 32] == "external"
    assert classes["0x" + "22" * 32] == "canary"


def test_scan_increment_uses_persisted_watermark(tmp_path, monkeypatch):
    from integrations.dashboard_store import DashboardStore
    from datetime import datetime as _dt, timezone as _tz

    def fake_stamps(self, w3, blocks):
        return {b: _dt.fromtimestamp(1757138460, tz=_tz.utc) for b in blocks}
    monkeypatch.setattr(DashboardStore, "_block_timestamps", fake_stamps)

    monkeypatch.setenv("BASE_FEE_RECEIVER", "0xd" + "0" * 39)
    log = {
        "topics": [b"\x01", bytes.fromhex("aa" * 32), bytes.fromhex("bb" * 32)],
        "data": (3_000).to_bytes(32, "big"),
        "blockNumber": 10_005,
        "transactionHash": bytes.fromhex("33" * 32),
    }
    _install_fake_web3(
        monkeypatch, [{"log": log}], {10_005: 1757138460}, latest=10_005
    )

    store = DashboardStore(tmp_path / "d.db")
    # No watermark → records nothing (retro_scan owns the backfill) and does
    # NOT mark latest as scanned — the watermark stays unset so the next
    # scan_increment retries (never silently skipping the history gap).
    assert store.scan_increment() == 0
    assert store.get_meta("last_scanned_block") is None

    store.set_meta("last_scanned_block", "10004")
    assert store.scan_increment() == 1
    assert store.get_meta("last_scanned_block") == "10005"
    assert store.sales_summary()["total_count"] == 1

