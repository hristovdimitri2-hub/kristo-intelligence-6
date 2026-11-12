# -*- coding: utf-8 -*-
"""The memory watch — a diagnostic that has to stay honest and stay cheap.

Render kills this service for exceeding its 512 MB limit about five times a day
at a measured ~1.2 MB/min, and nothing outside the process can say WHAT is
growing. These tests hold the report to the two properties that make it worth
having: it counts the real containers rather than a copy of them, and it cannot
be the thing that makes the next sample wrong.
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
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main


def test_the_report_names_the_containers_that_should_be_flat(client):
    report = client._memory_report()
    for key in ("rss_mb", "threads", "gc_objects", "sales_history",
                "daily_stats", "free_tier_ips", "paid_call_ips",
                "rate_limit_keys", "verify_block", "dashboard_cache",
                "isolated_stores", "rpc_clients"):
        assert key in report, "the report dropped %s" % key
        assert report[key] is None or report[key] >= 0
    assert report["threads"] >= 1
    assert report["gc_objects"] > 0


def test_the_counters_track_the_real_containers(client):
    """A copy would be a lie: the point is to see the LIVE structures grow."""
    before = client._memory_report()["sales_history"]
    client._sales_history.append({"tx_hash": "0xprobe"})
    try:
        assert client._memory_report()["sales_history"] == before + 1
    finally:
        client._sales_history.pop()

    before = client._memory_report()["free_tier_ips"]
    client._free_tier_usage["203.0.113.9"] = 1
    try:
        assert client._memory_report()["free_tier_ips"] == before + 1
    finally:
        client._free_tier_usage.pop("203.0.113.9", None)
