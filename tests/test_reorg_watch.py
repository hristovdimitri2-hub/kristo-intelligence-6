"""Hash-anchor / reorg watch on the standard rail (21.09, Miguel's audit).

The depth gate counts BLOCKS, so a reorg that replaces a block at the SAME
height passes it silently — same height, different hash. These tests pin the
fix: every standard-rail settlement stores the confirming block's number AND
hash, and a later re-read that finds a different hash is recorded as a VISIBLE
`c2_reorg_detected` guard event.

Equally important, they pin what must NOT change: the confirmation threshold
stays 1 on the standard rail (the hash check is an extra layer on top, never a
replacement for depth), a matching hash is never reported, and an unreadable
block is never mistaken for a detection.
"""

import sqlite3

import pytest


def _store(tmp_path, monkeypatch, name="guards.db"):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from integrations.dashboard_store import DashboardStore
    return DashboardStore(tmp_path / name)


def _main_with_store(monkeypatch, store):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    monkeypatch.setattr(main, "dashboard_db", store)
    return main


def _events(store):
    return store.guard_stats()["by_kind"]


def test_fresh_schema_has_the_finality_anchor(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    columns = {row[1] for row in sqlite3.connect(
        tmp_path / "guards.db").execute("PRAGMA table_info(payment_guards)")}
    assert {"block_number", "block_hash"} <= columns


def test_migration_adds_the_anchor_to_an_existing_table(tmp_path, monkeypatch):
    """A deploy on an OLD database must gain the columns, not crash."""
    path = tmp_path / "legacy.db"
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE payment_guards (
                        tx_hash TEXT PRIMARY KEY, endpoint TEXT, payer TEXT,
                        amount_usdc REAL, consumed_at TEXT)""")
    conn.execute("INSERT INTO payment_guards VALUES "
                 "('0xold', '/api/stats', '0xabc', 0.003, '2026-09-20T00:00:00')")
    conn.commit()
    conn.close()

    store = _store(tmp_path, monkeypatch, name="legacy.db")
    columns = {row[1] for row in sqlite3.connect(
        path).execute("PRAGMA table_info(payment_guards)")}
    assert {"block_number", "block_hash"} <= columns
    # The pre-existing row survives and simply carries no anchor.
    assert store.guard_claims_with_blocks() == []
    assert store.claim_payment_tx("0xnew") is True     # still usable


def test_a_confirmed_claim_stores_the_confirming_block(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    assert store.claim_payment_tx(
        "0xabc", endpoint="/api/v1/signal", payer="0xPayer", amount_usdc=0.003,
        block_number=51313253, block_hash="0x" + "AB" * 32,
    ) is True

    anchors = store.guard_claims_with_blocks()
    assert len(anchors) == 1
    assert anchors[0]["tx_hash"] == "0xabc"
    assert anchors[0]["block_number"] == 51313253
    # Normalised to lower case so a comparison never fails on formatting.
    assert anchors[0]["block_hash"] == "0x" + "ab" * 32


def test_a_claim_without_an_anchor_is_not_checked(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    store.claim_payment_tx("0xnoblock", endpoint="/api/stats")
    assert store.guard_claims_with_blocks() == []


def test_matching_hash_is_not_a_reorg(tmp_path, monkeypatch):
    store = _store(tmp_path, monkeypatch)
    stored = "0x" + "11" * 32
    store.claim_payment_tx("0xok", endpoint="/api/v1/signal",
                           block_number=500, block_hash=stored)
    main = _main_with_store(monkeypatch, store)

    detected = main._detect_reorgs(read_block=lambda height: stored)

    assert detected == 0
    assert "c2_reorg_detected" not in _events(store)


def test_mismatched_hash_is_detected_and_visible(tmp_path, monkeypatch):
    """Simulated reorg: same height, different hash → a VISIBLE guard event."""
    store = _store(tmp_path, monkeypatch)
    store.claim_payment_tx(
        "0xreorged", endpoint="/api/v1/signal", payer="0xPayer",
        amount_usdc=0.003, block_number=51313253, block_hash="0x" + "aa" * 32)
    main = _main_with_store(monkeypatch, store)

    detected = main._detect_reorgs(
        read_block=lambda height: "0x" + "bb" * 32)

    assert detected == 1
    assert _events(store).get("c2_reorg_detected") == 1
    event = store.guard_stats()["recent_blocks"][0]
    assert event["kind"] == "c2_reorg_detected"
    assert event["tx_hash"] == "0xreorged"
    assert "51313253" in event["detail"]
    # A detection is NOT a refusal: the blocked counter must not absorb it.
    assert store.guard_stats()["blocked_total"] == 0


def test_unreadable_block_is_not_reported_as_a_reorg(tmp_path, monkeypatch):
    """A failed CHECK must never look like a detection (fail-silent)."""
    store = _store(tmp_path, monkeypatch)
    store.claim_payment_tx("0xdark", block_number=900, block_hash="0x" + "cc" * 32)
    main = _main_with_store(monkeypatch, store)

    def boom(height):
        raise RuntimeError("rpc down")

    assert main._detect_reorgs(read_block=boom) == 0
    assert main._detect_reorgs(read_block=lambda height: "") == 0
    assert "c2_reorg_detected" not in _events(store)


def test_the_confirmation_threshold_is_untouched(monkeypatch):
    """The fix ADDS a check; it must not have replaced depth."""
    monkeypatch.delenv("MIN_STANDARD_PAYMENT_CONFIRMATIONS", raising=False)
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    assert main._required_standard_confirmations() == 1