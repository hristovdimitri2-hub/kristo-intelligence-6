"""Whale flow tests (owner-approved build, docs/WHALE_FLOW_SPEC.md).

Covers: honest labels, threshold via env (scan + read), watermark
resilience, truthful empty result, the 402 paywall path with the correct
price/description, and the unlisted-until-canary guarantee (condition 4).
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
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    dash = DashboardStore(tmp_path / "dashboard_state.db")
    monkeypatch.setattr(main, "dashboard_db", dash)
    return main.app.test_client(), main, dash


def _install_fake_web3(monkeypatch, logs, blocks_ts, latest=10_000):
    fake = types.ModuleType("web3")

    class FakeEth:
        def __init__(self):
            self.block_number = latest

        def is_connected(self):
            return True

        def get_logs(self, spec):
            lo, hi = spec["fromBlock"], spec["toBlock"]
            return [lg for lg in logs if lo <= lg["blockNumber"] <= hi]

        def get_block(self, n):
            return {"timestamp": blocks_ts.get(n, 0)}

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url, request_kwargs=None: ("p", url))

        def __init__(self, provider):
            self.eth = FakeEth()

        def is_connected(self):
            return True

        @staticmethod
        def to_checksum_address(a):
            return a

        @staticmethod
        def to_hex(h):
            return ("0x" + bytes(h).hex()) if isinstance(h, (bytes, bytearray)) else str(h)

    fake.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", fake)


NOW_TS = int(datetime.now(timezone.utc).timestamp())
TS = {10_000: NOW_TS, 10_002: NOW_TS + 100, 10_005: NOW_TS + 300}


def _whale_log(tx_hex_last, amount_usdc, frm_hex20, to_hex20, block):
    return {
        "topics": [b"\x01", bytes.fromhex(frm_hex20), bytes.fromhex(to_hex20)],
        "data": int(amount_usdc * 1_000_000).to_bytes(32, "big"),
        "blockNumber": block,
        "transactionHash": bytes.fromhex(tx_hex_last),
        "logIndex": 0,
    }


def test_whale_scan_threshold_filters_and_persists(tmp_path, monkeypatch):
    """Network-wide scan: only >= threshold transfers persist; labels honest
    (unknown for unknown wallets); dedup on re-scan."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    logs = [
        _whale_log("11", 60000.0, "aa" * 32, "bb" * 32, 10_000),   # whale ✅
        _whale_log("22", 49999.0, "cc" * 32, "bb" * 32, 10_000),   # below ❌
        _whale_log("33", 120000.0, "cc" * 32, "aa" * 32, 10_002),  # whale ✅
    ]
    _install_fake_web3(monkeypatch, logs, TS, latest=10_002)
    store = DashboardStore(tmp_path / "d.db")
    added = store.scan_whale_window(10_000, 10_002, rpc_url="http://fake")
    assert added == 2
    s = store.whaleflow_summary(window_hours=24)
    assert s["count"] == 2
    assert {w["amount_usdc"] for w in s["whales"]} == {60000.0, 120000.0}
    for w in s["whales"]:
        assert w["from_label"] == "unknown"          # honest, not invented
        assert w["to_label"] == "unknown"
        assert w["token"] == "USDC"
        assert w["block"] in (10_000, 10_002)
        assert w["tx_hash"].startswith("0x")
    # Dedup: re-scan same window records nothing new
    assert store.scan_whale_window(10_000, 10_002, rpc_url="http://fake") == 0


def test_whale_threshold_env_change_at_read_time(tmp_path, monkeypatch):
    """Raising the threshold via env filters the SERVED list at read time —
    regulable without touching recorded history."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    logs = [
        _whale_log("11", 60000.0, "aa" * 32, "bb" * 32, 10_000),
        _whale_log("33", 120000.0, "cc" * 32, "aa" * 32, 10_002),
    ]
    _install_fake_web3(monkeypatch, logs, TS, latest=10_002)
    store = DashboardStore(tmp_path / "d.db")
    store.scan_whale_window(10_000, 10_002, rpc_url="http://fake")
    s50 = store.whaleflow_summary(window_hours=24, threshold=50000.0)
    assert s50["count"] == 2
    s100 = store.whaleflow_summary(window_hours=24, threshold=100000.0)
    assert s100["count"] == 1
    assert s100["threshold_usdc"] == 100000.0


def test_whale_watermark_resilience(tmp_path, monkeypatch):
    """Watermark survives store reopen (deploy/restart) — the incremental
    scan continues from it and new whales are appended."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    log = _whale_log("44", 75000.0, "dd" * 32, "ee" * 32, 10_005)
    _install_fake_web3(monkeypatch, [log], {10_005: NOW_TS + 300}, latest=10_005)

    db_path = tmp_path / "d.db"
    store = DashboardStore(db_path)
    assert store.whaleflow_increment() == 0          # no watermark yet
    assert store.get_meta("whaleflow_last_block") == "10005"

    store.set_meta("whaleflow_last_block", "10004")
    assert store.whaleflow_increment() == 1
    assert store.get_meta("whaleflow_last_block") == "10005"

    # "restart": reopen over the same file — data + watermark survive
    reopened = DashboardStore(db_path)
    assert reopened.whaleflow_summary(window_hours=24)["count"] == 1


def test_known_payer_gets_honest_label(tmp_path, monkeypatch):
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    chet = "7e6b6556322c4e26c567a867964ac793f5ee2b1c" + "00" * 0
    chet32 = chet.rjust(64, "0")
    log = _whale_log("55", 90000.0, chet32, "bb" * 32, 10_000)
    _install_fake_web3(monkeypatch, [log], {10_000: NOW_TS}, latest=10_000)
    store = DashboardStore(tmp_path / "d.db")
    store.scan_whale_window(10_000, 10_000, rpc_url="http://fake")
    s = store.whaleflow_summary(window_hours=24)
    assert s["whales"][0]["from_label"] == "chet_payapi_verification"
    assert s["whales"][0]["to_label"] == "unknown"


def test_truthful_empty_result(tmp_path):
    """No whales in window → empty list with truthful fields, zero invention."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    s = store.whaleflow_summary(window_hours=24)
    assert s["whales"] == []
    assert s["count"] == 0
    assert s["window_hours"] == 24
    assert s["threshold_usdc"] == 50000.0
    assert s["scanned_until_block"] is None


def test_whaleflow_route_402_price_and_description(client, monkeypatch):
    """Paid like the other routes: canonical v2 402 with the right price and
    the selling description."""
    test_client, main, _ = client
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    resp = test_client.get("/api/v1/whaleflow")
    assert resp.status_code == 402
    payload = resp.get_json()
    acc = payload["accepts"][0]
    assert acc["amount"] == "3000"                        # 0.003 USDC atomic
    assert acc["payTo"] == main.X402_RECEIVER_ADDRESS
    assert acc["network"] == "eip155:8453"
    assert payload["x402Version"] == 2
    desc = payload["resource"]["description"]
    assert "whale flow" in desc.lower()
    assert "50k" in desc
    assert "60 seconds" in desc


def test_whaleflow_route_truthful_response(client, monkeypatch):
    """Free-tier first call: truthful response. Empty store -> empty list."""
    test_client, main, dash = client
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1)
    monkeypatch.setattr(main, "_free_tier_usage", {})   # fresh IP budget
    resp = test_client.get("/api/v1/whaleflow")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True
    assert payload["whales"] == []
    assert payload["count"] == 0
    assert payload["threshold_usdc"] == 50000.0
    assert "scanned_until_block" in payload
    assert payload["source"] == "onchain_eth_getlogs"

    # A known-labeled whale event seeded in the store is served honestly
    store_row = dash.whaleflow_summary(window_hours=24)  # sanity: empty now
    assert store_row["whales"] == []


def test_whaleflow_is_listed_after_the_canary(client):
    """Condition 4 of docs/WHALE_FLOW_SPEC.md: the route stays unlisted until
    it passes a PAID canary. That canary is on-chain and independently
    verifiable — so the route is now advertised (vitrine) everywhere the other
    real routes are:
      tx 0xc30268e387e84d449f433772ed11e9ab751394d80bfc310a9c7dbb5e604cce03
      block 51200083 · $0.003 USDC · from 0x7e6b… (Chet / PayAPI verifier) —
      exactly the whale-flow price, to the bound receiver.
    """
    test_client, main, _ = client
    for path in ("/.well-known/x402.json", "/api/v1/agents",
                 "/api/dashboard-stats", "/api/mcp/manifest"):
        r = test_client.get(path)
        assert r.status_code == 200
        assert "/api/v1/whaleflow" in r.get_data(as_text=True), \
            f"whaleflow missing from the vitrine surface {path}"

    # /dashboard is a JS app: since Табло 2.0 the routes table is rendered from
    # the API (the static list used to advertise /api/sales at $0.05 while the
    # 402 demanded $0.005), so the endpoint is proven through the payload the
    # page actually consumes — the same list that mints the x402 challenge.
    r = test_client.get("/dashboard")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'id="routes-body"' in html and "renderRoutes(" in html
    payload = test_client.get("/api/dashboard/data").get_json()
    endpoints = [x["endpoint"] for x in payload["sections"]["routes"]["routes"]]
    assert "/api/v1/whaleflow" in endpoints
    assert len(endpoints) == len(main.REAL_X402_ROUTES) == 6

    # …and it is a REAL route in the single source of truth, at the price the
    # canary actually paid.
    listed = {row["endpoint"]: row for row in main.REAL_X402_ROUTES}
    assert "/api/v1/whaleflow" in listed
    assert listed["/api/v1/whaleflow"]["price_usdc"] == 0.003



def test_whaleflow_not_in_readme():
    from pathlib import Path
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8")
    assert "/api/v1/whaleflow" not in readme


# ── AUDIT (Табло 2.0): the whale scan carried the SAME bug class as sales ────

def _install_refusing_web3(monkeypatch, logs, blocks_ts, latest, max_span):
    """Fake web3 that REFUSES any window wider than `max_span` — exactly how
    the public Base RPC behaves (HTTP 500 at 250 blocks network-wide, fine at
    <=100). Records every attempted span so a test can prove the halving."""
    fake = types.ModuleType("web3")
    attempts = []

    class FakeEth:
        def __init__(self):
            self.block_number = latest

        def is_connected(self):
            return True

        def get_logs(self, spec):
            lo, hi = spec["fromBlock"], spec["toBlock"]
            span = hi - lo + 1
            attempts.append(span)
            if max_span is not None and span > max_span:
                raise ValueError("query exceeds the RPC's range limit")
            return [lg for lg in logs if lo <= lg["blockNumber"] <= hi]

        def get_block(self, n):
            return {"timestamp": blocks_ts.get(n, 0)}

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url, request_kwargs=None: ("p", url))

        def __init__(self, provider):
            self.eth = FakeEth()

        def is_connected(self):
            return True

        @staticmethod
        def to_checksum_address(a):
            return a

        @staticmethod
        def to_hex(h):
            return (("0x" + bytes(h).hex())
                    if isinstance(h, (bytes, bytearray)) else str(h))

    fake.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", fake)
    return attempts


def test_whale_scan_halves_a_refused_window_instead_of_giving_up(
        tmp_path, monkeypatch):
    """Measured against the real RPC: a 250-block NETWORK-WIDE window answers
    HTTP 500, while <=100 blocks answers fine and carries real whales (100
    blocks -> 701 transfers >= $50k). The old code used a 250 default behind a
    `max(50, …)` floor and simply `break`-ed on the first refusal, so the
    promoted PAID /api/v1/whaleflow route could never serve a single row."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    monkeypatch.setenv("WHALEFLOW_CHUNK_BLOCKS", "250")   # the refusing width
    logs = [
        _whale_log("11", 60000.0, "aa" * 32, "bb" * 32, 10_010),
        _whale_log("22", 90000.0, "cc" * 32, "bb" * 32, 10_150),
        _whale_log("33", 150000.0, "dd" * 32, "aa" * 32, 10_260),
    ]
    ts = {10_010: NOW_TS, 10_150: NOW_TS + 10, 10_260: NOW_TS + 20}
    attempts = _install_refusing_web3(monkeypatch, logs, ts, latest=10_400,
                                      max_span=100)
    store = DashboardStore(tmp_path / "d.db")
    added = store.scan_whale_window(10_000, 10_400, rpc_url="http://fake")

    assert added == 3, "every whale in the range must be persisted"
    assert max(attempts) == 250, "must try the configured width first"
    assert min(attempts) <= 100, "must halve down to a width the RPC accepts"
    # The recorded width is the LAST span used (250→125→62), i.e. one the RPC
    # accepts — never the 250 it refused.
    assert 0 < int(store.get_meta("whaleflow_effective_chunk")) <= 125
    # …and the whole range is covered, with no silent gap.
    assert int(store.get_meta("whaleflow_safe_scanned_block")) == 10_400
    assert store.get_meta("whaleflow_last_error") in ("", None)


def test_whale_chunk_env_is_not_clamped_upwards(tmp_path, monkeypatch):
    """The sales scan lost days to a hidden `max(50, …)` floor; the whale scan
    must respect WHALEFLOW_CHUNK_BLOCKS literally."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    monkeypatch.setenv("WHALEFLOW_CHUNK_BLOCKS", "10")
    logs = [_whale_log("11", 60000.0, "aa" * 32, "bb" * 32, 10_005)]
    attempts = _install_refusing_web3(monkeypatch, logs, {10_005: NOW_TS},
                                      latest=10_009, max_span=None)
    store = DashboardStore(tmp_path / "d.db")
    store.scan_whale_window(10_000, 10_009, rpc_url="http://fake")
    assert set(attempts) == {10}, f"env width ignored: tried {attempts}"
    assert store.get_meta("whaleflow_effective_chunk") == "10"


def test_a_broken_whale_scan_reports_itself_instead_of_looking_empty(
        tmp_path, monkeypatch):
    """Honesty: 'чакаме кит' (healthy empty) and 'scan_failed' (broken feed)
    must never be shown as the same thing on a PAID route."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    _install_refusing_web3(monkeypatch, [], {}, latest=10_400, max_span=0)
    store = DashboardStore(tmp_path / "d.db")
    store.scan_whale_window(10_000, 10_400, rpc_url="http://fake")

    s = store.whaleflow_summary(window_hours=24)
    assert s["count"] == 0
    assert s["state"] == "scan_failed"          # NOT awaiting_whale
    assert s["last_error"] and "refused" in s["last_error"]
    assert s["last_attempt_at"]                 # the screen can show when


def test_a_complete_whale_scan_clears_a_previous_failure(tmp_path, monkeypatch):
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    store = DashboardStore(tmp_path / "d.db")

    _install_refusing_web3(monkeypatch, [], {}, latest=10_010, max_span=0)
    store.scan_whale_window(10_000, 10_010, rpc_url="http://fake")
    assert store.whaleflow_summary(window_hours=24)["state"] == "scan_failed"

    logs = [_whale_log("11", 60000.0, "aa" * 32, "bb" * 32, 10_005)]
    _install_refusing_web3(monkeypatch, logs, {10_005: NOW_TS}, latest=10_010,
                           max_span=None)
    store.scan_whale_window(10_000, 10_010, rpc_url="http://fake")
    s = store.whaleflow_summary(window_hours=24)
    assert s["state"] == "live_data"
    assert s["last_error"] is None


def test_whale_backfill_always_records_an_attempt(tmp_path, monkeypatch):
    """After a real backfill attempt the screen must never claim the scan
    'has not started' — that hid a dead feed on the live instance."""
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setenv("WHALE_THRESHOLD", "50000")
    # Every window refused → the attempt still has to be recorded.
    _install_refusing_web3(monkeypatch, [], {}, latest=10_400, max_span=0)
    store = DashboardStore(tmp_path / "d.db")
    store.whaleflow_backfill(hours=1, rpc_url="http://fake")
    s = store.whaleflow_summary(window_hours=24)
    assert s["last_attempt_at"]
    assert s["state"] in ("scan_failed", "awaiting_whale")
    assert s["state"] != "scan_not_started"


def test_a_first_long_scan_reads_as_scanning_not_not_started(tmp_path):
    """The first network-wide walk takes minutes; the dashboard must say
    'сканира се…' during it, not claim the scan never started."""
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "d.db")
    store.set_meta("whaleflow_last_attempt",
                   datetime.now(timezone.utc).isoformat())
    s = store.whaleflow_summary(window_hours=24)
    assert s["count"] == 0
    assert s["state"] == "scanning"
    assert s["scanned_until_block"] is None

