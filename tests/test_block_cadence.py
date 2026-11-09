"""Base is not a 2-second chain any more, and our arithmetic assumed it was.

Every window we walk is "N days × 86400 / seconds-per-block". With the divisor
stuck at 2.0 while the chain actually produces a block every 0.2 s, each window
covered a tenth of the time it promised — silently, because the resulting
numbers look perfectly reasonable in a log line.

Measured 09.11 19:11 UTC at head 55,269,652: the timestamps of head, head−1,000,
head−10,000 and head−100,000 all give exactly 0.2000 s/block.

These tests pin the arithmetic and, just as importantly, pin the HONESTY: when a
window cannot be afforded it must say which window it actually scanned instead of
reporting the one it was asked for.
"""

from __future__ import annotations

import logging
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from integrations import dashboard_store
from integrations.dashboard_store import (BLOCK_TIME_SECONDS,
                                          DashboardStore,
                                          blocks_for_seconds,
                                          measure_block_time_seconds)

# ── The measurement the whole file rests on ─────────────────────────────────


class _FakeEth:
    def __init__(self, latest: int, seconds_per_block: float):
        self.block_number = latest
        self._spb = seconds_per_block

    def get_block(self, number):
        # timestamp zeroes at block 0 so a "1,000 blocks = 200 s" chain is
        # unambiguous: 0.2 s/block exactly.
        return {"timestamp": int(number * self._spb)}


class _FakeW3:
    def __init__(self, latest: int = 100_000, seconds_per_block: float = 0.2):
        self.eth = _FakeEth(latest, seconds_per_block)


def test_cadence_is_measured_on_the_chain_we_are_connected_to():
    assert measure_block_time_seconds(_FakeW3(seconds_per_block=0.2)) == \
        pytest.approx(0.2)


def test_a_two_second_chain_is_reported_as_two_seconds_not_assumed_away():
    """The point is "derived from the chain", not "hardcoded to 0.2" — a
    fallback-chain, a testnet or the next Base upgrade must all be read from
    their own timestamps."""
    assert measure_block_time_seconds(_FakeW3(seconds_per_block=2.0)) == \
        pytest.approx(2.0)


def test_a_chain_that_cannot_be_measured_falls_back_to_the_constant(caplog):
    class _Broken:
        class eth:  # noqa: N801 — mirrors web3's attribute
            block_number = 100_000

            @staticmethod
            def get_block(_number):
                raise RuntimeError("rpc refused")

    with caplog.at_level(logging.DEBUG, logger=dashboard_store.log.name):
        assert measure_block_time_seconds(_Broken()) == BLOCK_TIME_SECONDS


def test_the_constant_is_the_measured_five_blocks_a_second():
    """A tripwire, deliberately. If Base changes cadence again this fails and
    forces a re-measurement — the failure mode we are fixing here is exactly a
    constant nobody re-checked. When it fails, update it AND the two constants
    named below, then re-measure with eth_getBlockByNumber timestamps."""
    from services import arb_radar

    assert BLOCK_TIME_SECONDS == pytest.approx(0.2)
    assert arb_radar.BASE_BLOCK_TIME_SECONDS == pytest.approx(BLOCK_TIME_SECONDS)


def test_the_window_arithmetic_covers_the_time_it_says():
    assert blocks_for_seconds(86400) == 432_000      # one day, at 5 blocks/s
    assert blocks_for_seconds(3600) == 18_000        # one hour
    assert blocks_for_seconds(0.0001) == 1           # never zero


# ── The two windows that were quietly short ─────────────────────────────────


def _install_fake_web3(monkeypatch, latest=100_000, seconds_per_block=0.2):
    fake = types.ModuleType("web3")

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda url, request_kwargs=None: ("p", url))

        def __init__(self, _provider):
            self.eth = _FakeEth(latest, seconds_per_block)

    fake.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", fake)


def test_the_whale_backfill_fills_the_hours_the_paid_route_promises(
        tmp_path, monkeypatch):
    """24 hours at 5 blocks/s is 432,000 blocks. It used to walk 43,200 —
    2.4 hours — while the paid feed advertised a day."""
    _install_fake_web3(monkeypatch, latest=1_000_000, seconds_per_block=0.2)
    store = DashboardStore(tmp_path / "w.db")
    seen = {}
    monkeypatch.setattr(store, "scan_whale_window",
                        lambda f, t, rpc_url="": seen.update(f=f, t=t) or 0)

    store.whaleflow_backfill(hours=24)
    assert seen["t"] == 1_000_000
    assert seen["f"] == 1_000_000 - 432_000


def test_the_sales_backfill_is_clamped_and_says_so(tmp_path, monkeypatch, caplog):
    """30 days is ~13,000,000 blocks at 5 blocks/s, and a recipient-filtered
    eth_getLogs is refused above ~1,000 blocks — that is an unaffordable cold
    boot. The window is clamped to a budget, and the warning must state the
    window that was really scanned: a "30 days" that means 3 must not read as
    30."""
    monkeypatch.setattr(dashboard_store, "SALES_RETRO_MAX_BLOCKS", 1_500_000)
    _install_fake_web3(monkeypatch, latest=20_000_000, seconds_per_block=0.2)
    store = DashboardStore(tmp_path / "s.db")
    seen = {}
    monkeypatch.setattr(store, "scan_window",
                        lambda f, t, rpc_url="": seen.update(f=f, t=t) or 0)

    with caplog.at_level(logging.WARNING, logger=dashboard_store.log.name):
        store.retro_scan(days=30)

    assert seen["f"] == 20_000_000 - 1_500_000
    assert seen["t"] == 20_000_000
    said = " ".join(r.getMessage() for r in caplog.records)
    assert "30 days requested" in said
    assert "scanning 3.47 days instead" in said
    assert "KRISTO_SALES_RETRO_MAX_BLOCKS" in said


def test_an_affordable_window_is_not_clamped_and_is_not_noisy(
        tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(dashboard_store, "SALES_RETRO_MAX_BLOCKS", 1_500_000)
    _install_fake_web3(monkeypatch, latest=20_000_000, seconds_per_block=0.2)
    store = DashboardStore(tmp_path / "s2.db")
    seen = {}
    monkeypatch.setattr(store, "scan_window",
                        lambda f, t, rpc_url="": seen.update(f=f, t=t) or 0)

    with caplog.at_level(logging.WARNING, logger=dashboard_store.log.name):
        store.retro_scan(days=2)

    assert seen["f"] == 20_000_000 - 864_000     # 2 days, honestly
    assert not [r for r in caplog.records if "requested" in r.getMessage()]


# ── The number a paying buyer is shown ──────────────────────────────────────


def test_the_arb_radar_counts_a_genuine_block_age(monkeypatch):
    """`data_age_blocks` is what a buyer reads to judge staleness. At the old
    2.0 it understated a five-minute-old scan by 10×: 150 blocks instead of
    1,500."""
    from services import arb_radar

    scanned = datetime.now(timezone.utc) - timedelta(seconds=300)
    monkeypatch.setattr(arb_radar, "_opportunities",
                        [{"scanned_at": scanned.isoformat()}])
    row = arb_radar.get_opportunities()[0]
    assert 1490 <= row["data_age_blocks"] <= 1510      # 300 s ÷ 0.2
