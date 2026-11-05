"""The whale-feed indexes — the actual 40-second dashboard build (05.11).

`whale_rows` runs two reads against `whaleflow_events`, and the second one is
the expensive one:

    SELECT … FROM whaleflow_events
     WHERE ts >= ? AND amount_usdc >= ? ORDER BY ts DESC, block_number DESC LIMIT ?
    SELECT COUNT(*), MAX(ts), MAX(block_number)
      FROM whaleflow_events WHERE amount_usdc >= ?      <-- nothing indexed this

The only index was `(ts)`. A predicate on `amount_usdc` cannot use it, so
Postgres read the WHOLE table. This module already records that the table
reached 427 MB in under five days at the old $50k threshold — so the dashboard
was reading hundreds of MB to draw one panel, on every build, behind the one
shared Postgres link.

That is the 40 seconds, and it explains the shape of the outage precisely:
/health and the static `/` answered in ~400 ms because they never touch this
table. The audit had measured the same thing months earlier as F-22, "12
заявки / 5 пълни сканирания (~41 s live)".

These tests exist because the fix is an INDEX, and an index is invisible: drop
it and every other test in the suite still passes, while the dashboard silently
goes back to taking 40 seconds.
"""

from __future__ import annotations

import sqlite3
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A real store over a temp SQLite file (DATABASE_URL off).

    `HistoryStore.__init__` takes the sqlite connector and a write lock, so it
    is built the way production builds it — through DashboardStore — rather
    than by guessing the constructor.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from integrations.dashboard_store import DashboardStore

    return DashboardStore(tmp_path / "whale.db")


def _history(store):
    """The HistoryStore behind the store (the index DDL lives there)."""
    return getattr(store, "history", store)


def _indexes_on(store, table):
    """{index name: [columns, ...]} for one table, from the SQLite catalogue."""
    with sqlite3.connect(str(store.file_path)) as conn:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,))]
        out = {}
        for n in names:
            cols = [r[2] for r in conn.execute(f"PRAGMA index_info({n})")]
            out[n] = cols
        return out


# ── 1. the index that fixes the 40 seconds ─────────────────────────────────
def test_an_index_leads_with_amount_usdc(store):
    """`WHERE amount_usdc >= ?` needs amount_usdc as the LEADING column.

    An index that merely mentions amount_usdc somewhere is not enough: a
    composite index can only serve a range predicate on its first column.
    """
    idx = _indexes_on(store, "whaleflow_events")

    leading = {name: cols for name, cols in idx.items()
               if cols and cols[0] == "amount_usdc"}
    assert leading, (
        "no index on whaleflow_events leads with amount_usdc, so "
        "`WHERE amount_usdc >= ?` is back to a full scan of a table this "
        "module documents as hundreds of MB. Indexes present: %r" % idx)


def test_that_index_also_covers_ts_and_block_number(store):
    """So the aggregate is answered from the index, not the heap."""
    idx = _indexes_on(store, "whaleflow_events")
    covering = [cols for cols in idx.values()
                if cols and cols[0] == "amount_usdc"
                and "ts" in cols and "block_number" in cols]
    assert covering, (
        "the amount_usdc index does not include ts and block_number, so "
        "COUNT/MAX still have to visit every matching row. Indexes: %r" % idx)


def test_the_windowed_read_has_an_index_in_its_sort_order(store):
    """`ORDER BY ts DESC, block_number DESC LIMIT n` must not need a sort."""
    idx = _indexes_on(store, "whaleflow_events")
    ordered = [cols for cols in idx.values()
               if cols[:2] == ["ts", "block_number"]]
    assert ordered, (
        "no index on (ts, block_number), so the windowed whale read sorts the "
        "whole matching set to return 25 rows. Indexes: %r" % idx)


def test_the_pre_existing_ts_index_is_still_there(store):
    """The fix adds indexes; it must not have replaced the old one."""
    assert "idx_whaleflow_ts" in _indexes_on(store, "whaleflow_events")


# ── 2. idempotent, and safe on a table this size ───────────────────────────
def test_ensuring_the_indexes_twice_is_harmless(store):
    _history(store)._ensure_whaleflow_indexes()
    _history(store)._ensure_whaleflow_indexes()
    assert "idx_whaleflow_amount" in _indexes_on(store, "whaleflow_events")


def test_postgres_builds_them_concurrently(monkeypatch):
    """A plain CREATE INDEX takes a write lock; this table is hundreds of MB.

    Asserted on the SQL actually sent, not on the docstring — the docstring
    claiming CONCURRENTLY while the code sends a locking CREATE INDEX is
    exactly the defect class this repository keeps hitting.
    """
    from integrations import dashboard_store as ds

    sent = []

    class FakeConn:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, *a):
            sent.append(sql)

    monkeypatch.setitem(sys.modules, "psycopg",
                        SimpleNamespace(connect=lambda *a, **kw: FakeConn()))

    store = ds.HistoryStore.__new__(ds.HistoryStore)
    store.backend = "postgresql"
    store.database_url = "postgresql://example/db"
    store._ensure_whaleflow_indexes()

    assert sent, "no DDL was sent"
    for sql in sent:
        assert "CONCURRENTLY" in sql, (
            "this DDL would take a write lock on whaleflow_events: %s" % sql)
        assert "whaleflow_events" in sql


def test_a_postgres_failure_falls_back_instead_of_blocking_boot(monkeypatch):
    """An index problem must never stop the service from booting."""
    from integrations import dashboard_store as ds

    def boom(*a, **kw):
        raise RuntimeError("permission denied for schema public")

    monkeypatch.setitem(sys.modules, "psycopg",
                        SimpleNamespace(connect=boom))

    store = ds.HistoryStore.__new__(ds.HistoryStore)
    store.backend = "postgresql"
    store.database_url = "postgresql://example/db"
    ran = []
    store._run = lambda sql, params=(), fetch="": ran.append(sql)

    store._ensure_whaleflow_indexes()   # must not raise

    assert ran, "the transactional fallback never ran"
    for sql in ran:
        assert "whaleflow_events" in sql
        assert "CONCURRENTLY" not in sql, (
            "the transactional fallback cannot use CONCURRENTLY — it is "
            "illegal inside a transaction")
