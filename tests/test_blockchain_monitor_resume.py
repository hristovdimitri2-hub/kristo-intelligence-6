# -*- coding: utf-8 -*-
"""The blockchain monitor must not skip the blocks it was down for.

F-39 in docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md: the monitor started at
`wallet.w3.eth.block_number`, so every transfer that landed while the worker was
down was skipped for good. Render restarts the worker on every deploy, so this was
not an unlucky-crash path — it was every deploy.

The dashboard scan had already solved the same problem (dashboard_store.
scan_increment, "deploy-safe" in its own docstring): it keeps last_scanned_block
durably and, with no watermark, refuses to mark the head as scanned, because that
would skip the history permanently. The monitor scans the same receiver and the
same topic, so the same watermark is a truthful resume point.

There was no test of the resume decision at all. _process_incoming_transfer is
covered (test_payment_proof_slow_path.py), but the loop that decides where to start
is a thread loop, and nothing held it to account - which is why the defect
survived. The decision is a pure function now so it can be tested without a chain,
a wallet or a thread.
"""
import inspect

import pytest


@pytest.fixture()
def main(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main as main_module
    return main_module


def test_a_durable_watermark_wins_over_the_head(main):
    """The whole point: resume behind the head, never at it."""
    from_block, reason = main._monitor_resume_block(
        head=1000, watermark=940, lookback=1800)

    assert from_block == 940, (
        "the monitor resumed at %d, not at the durable watermark 940 — transfers "
        "between them would be skipped" % from_block)
    assert from_block < 1000, "resuming at the head is the defect"
    assert "watermark" in reason


def test_no_watermark_never_claims_the_head_as_scanned(main):
    """With nothing to resume from, do not pretend the head was covered.

    Starting at the head here is exactly the old bug: everything before it is
    never scanned. dashboard_store.scan_increment takes the same line — with no
    watermark it returns without advancing, rather than marking the head.
    """
    head = 5_000_000
    from_block, reason = main._monitor_resume_block(
        head=head, watermark=0, lookback=1800)

    assert from_block < head, (
        "with no watermark the monitor started at the head %d, so any payment "
        "before it is invisible forever" % head)
    assert from_block == head - 1800
    assert from_block >= 1, "block 0 is not a valid start"
    assert "watermark" in reason and "lookback" in reason


def test_an_unknown_head_or_watermark_cannot_produce_a_negative_start(main):
    """An empty store or a failed RPC must not yield block 0 or a negative.

    With head 0 (an unreadable RPC) the honest answer is block 1: scan from the
    beginning rather than skip. That is safe, not clever - re-scanning is deduped -
    and it is why the "never start ahead of the head" rule below only applies when
    the head is a real block number. Asserting both at head 0 would contradict
    itself, which is what the first version of this test did.
    """
    for head, watermark, lookback in ((0, 0, 1800), (10, 0, 1800),
                                      (None, None, None), (100, 100, 1800)):
        from_block, _reason = main._monitor_resume_block(
            head=head, watermark=watermark, lookback=lookback)
        assert from_block >= 1, (head, watermark, lookback, from_block)
        if (head or 0) >= 1:
            assert from_block <= int(head), (
                "started ahead of a real head: %s"
                % ((head, watermark, lookback, from_block),))


def test_a_watermark_ahead_of_the_head_does_not_scan_the_future(main):
    """A reorg or a lagging RPC can put the watermark past the head."""
    from_block, reason = main._monitor_resume_block(
        head=500, watermark=900, lookback=1800)

    assert from_block == 500, (
        "the monitor tried to start at %d, which is ahead of the head 500" % from_block)
    assert "ahead" in reason


def test_the_loop_actually_consults_the_watermark(main):
    """The pure function is only worth testing if the loop calls it.

    The loop needs a chain and a thread, so this reads its source instead. It is a
    weaker check than the ones above and it is here for one reason: the defect was
    a single line, and the line must not come back.
    """
    source = inspect.getsource(main._blockchain_monitor_loop)

    assert "_monitor_resume_block(" in source, (
        "the monitor loop no longer consults the durable watermark")
    assert "last_scanned_block" in source, (
        "the monitor loop no longer reads the dashboard watermark")
    assert "last_block = wallet.w3.eth.block_number" not in source, (
        "the monitor starts at the head again — transfers that landed during a "
        "deploy are skipped for good, which is F-39")
