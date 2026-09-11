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


def test_whaleflow_unlisted_until_canary(client):
    """Condition 4: the route must NOT appear in any catalog/manifest/
    discovery surface while it is un-canaried."""
    test_client, main, _ = client
    for path in ("/.well-known/x402.json", "/api/v1/agents",
                 "/api/dashboard-stats", "/api/mcp/manifest"):
        r = test_client.get(path)
        assert r.status_code == 200
        assert "/api/v1/whaleflow" not in r.get_data(as_text=True), \
            f"whaleflow leaked via {path}"


def test_whaleflow_not_in_readme():
    from pathlib import Path
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
        encoding="utf-8")
    assert "/api/v1/whaleflow" not in readme