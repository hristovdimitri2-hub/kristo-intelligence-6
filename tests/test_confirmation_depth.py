# -*- coding: utf-8 -*-
"""The confirmation depth must mean a stated amount of TIME.

A block COUNT silently means less time when the chain changes its cadence, and
nothing in the code said so. Base moved from ~2 s blocks to ~0.2 s blocks, so:

  * "12 confirmations" quietly went from ~24 s to ~2.4 s — the number had been
    cut to 3 because 12 looked like a 24-second wait, which it no longer was;
  * the 3-block replacement bought ~0.6 s while every published sentence
    claimed ~6.

Both figures were wrong in the same direction, and the only reason it surfaced
was a stranger's weekly report (x402 Payability Report 13), not our own code.

These tests make the arithmetic explicit, so the next cadence change fails a test
here instead of being discovered in the wild.
"""
import main


def test_the_documented_cadence_is_sub_second():
    """Base produces sub-second blocks; a >=1s value means the assumption rotted."""
    assert main.BASE_BLOCK_SECONDS > 0, "the cadence must be a positive number"
    assert main.BASE_BLOCK_SECONDS < 1, (
        "BASE_BLOCK_SECONDS is %r — Base has produced sub-second blocks since "
        "2026, so this is the 2-second assumption creeping back"
        % main.BASE_BLOCK_SECONDS)


def test_the_proof_rail_asks_for_a_stated_amount_of_time():
    """The proof rail takes a CALLER-SUPPLIED hash, so depth is its main guard."""
    seconds = main.PAYMENT_CONFIRMATIONS_DEFAULT * main.BASE_BLOCK_SECONDS
    assert 1.5 <= seconds <= 5.0, (
        "the proof rail asks for %d blocks = %.1fs at the documented cadence; the "
        "intended range is 1.5-5s. Eight hours of facilitator outage is not the "
        "moment to discover this is 0.6s."
        % (main.PAYMENT_CONFIRMATIONS_DEFAULT, seconds))


def test_the_standard_rail_still_has_a_real_reorg_window():
    """1 block was chosen when a block was 2s; at 0.2s it is not a guard."""
    seconds = (main.STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT
               * main.BASE_BLOCK_SECONDS)
    assert seconds >= 0.5, (
        "the standard rail asks for %d blocks = %.1fs at the documented cadence; "
        "a window that short is not what 'we verify the settlement on chain' "
        "means to a reader"
        % (main.STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT, seconds))


def test_both_rails_stay_fast_enough_to_keep_their_published_promise():
    """Raising depth is only defensible while it stays cheap.

    The smart-wallet rail advertises a few seconds, and the standard rail's whole
    selling point is that it is the fast one. A depth that pushed either past
    ~5s would make the published numbers a lie again, in the other direction.
    """
    proof = main.PAYMENT_CONFIRMATIONS_DEFAULT * main.BASE_BLOCK_SECONDS
    standard = (main.STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT
                * main.BASE_BLOCK_SECONDS)
    assert proof <= 5.0, "the smart-wallet rail would wait %.1fs" % proof
    assert standard <= 2.0, "the standard rail would add %.1fs of its own" % standard
