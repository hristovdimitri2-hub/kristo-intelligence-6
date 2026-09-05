"""Regression tests for scripts/competitor_recon.py (pure logic only)."""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
recon = importlib.import_module("scripts.competitor_recon")


def _t(payer, amount, tx="0x" + "a" * 64):
    return {"tx_hash": tx, "payer": payer, "amount_usdc": amount, "block_number": 1}


def test_classify_empty_transfers():
    report = recon.classify_transfers([])
    assert report["total_txs"] == 0
    assert report["unique_payers"] == 0
    assert report["repeat_payers"] == []
    assert report["noise"]["large_tx_count"] == 0


def test_classify_payer_aggregation_and_repeat_payers():
    A = "0x" + "a" * 40
    B = "0x" + "b" * 40
    transfers = [
        _t(A, 0.005), _t(A, 0.003), _t(A, 0.005),   # operator: 3 txs
        _t(B, 0.003),                                # one-off buyer
    ]
    report = recon.classify_transfers(transfers)
    assert report["total_txs"] == 4
    assert report["total_usdc"] == 0.016
    assert report["unique_payers"] == 2
    assert report["avg_check_usdc"] == 0.004
    repeats = {e["payer"]: e for e in report["repeat_payers"]}
    assert list(repeats) == [A]                       # only A repeats
    assert repeats[A]["txs"] == 3
    assert repeats[A]["total_usdc"] == 0.013
    top = report["payers"][0]
    assert top["payer"] == A                          # sorted by total desc


def test_classify_large_transfers_flagged_as_noise_not_hidden():
    A = "0x" + "a" * 40
    WHALE = "0x" + "c" * 40
    transfers = [
        _t(A, 0.005),
        _t(WHALE, 2000.0, tx="0x" + "c" * 64),        # treasury flow, not a canary
    ]
    report = recon.classify_transfers(transfers)
    # Large tx must NOT pollute operator stats…
    assert report["total_txs"] == 1
    assert report["total_usdc"] == 0.005
    assert report["unique_payers"] == 1
    assert report["payers"][0]["payer"] == A
    # …but must stay visible in the noise bucket.
    assert report["noise"]["large_tx_count"] == 1
    assert report["noise"]["large_txs"][0]["payer"] == WHALE
    assert report["noise"]["large_txs"][0]["amount_usdc"] == 2000.0


def test_pad_topic_rejects_bad_address():
    try:
        recon._pad_topic("0x123")
        raised = False
    except ValueError:
        raised = True
    assert raised


def test_decode_amount_usdc_decimals():
    raw = (5000).to_bytes(32, "big")                  # 5000 raw units = 0.005 USDC
    assert recon._decode_amount(raw) == 0.005


def test_known_verifiers_split_from_operator_stats():
    """Market reviewers' canaries are real settlements but NOT customers —
    they must never inflate the external-operator numbers."""
    CHET = "0x7E6b6556322c4e26c567a867964ac793f5ee2b1c"   # case-check: label lookup is case-insensitive
    OPERATOR = "0x" + "d" * 40
    transfers = [
        _t(CHET, 0.003), _t(CHET, 0.003), _t(CHET, 0.005),  # would look like an operator...
        _t(OPERATOR, 0.003),
    ]
    report = recon.classify_transfers(transfers)
    assert report["unique_payers"] == 2
    assert report["known_verification_txs"] == 3
    assert report["external_unique_payers"] == 1
    assert report["total_txs"] == 1
    assert report["total_usdc"] == 0.003
    assert report["repeat_payers"] == []                  # canaries never appear as operators
    assert report["known_verifications"][0]["label"] == "chet_payapi_verification"


def test_known_payers_param_overrides_default():
    A = "0x" + "a" * 40
    transfers = [_t(A, 0.003)]
    report = recon.classify_transfers(transfers, known_payers={A.lower(): "test_reviewer"})
    assert report["external_unique_payers"] == 0
    assert report["known_verifications"][0]["label"] == "test_reviewer"


def test_market_samplers_are_heartbeat_never_launch_signal():
    """The two fingerprinted crawler wallets (RECON_FINDINGS) must be
    classified as known infrastructure: their payments are a heartbeat
    ('in the crawl set'), NEVER a launch signal."""
    C59E = "0xC59E74ED6386B2a12D892fff2509A6965a0498DC"   # 158 receivers/week
    C6777 = "0x6777E11fB0A7917b8110B7dab9188AA3F6D23986"  # 386 receivers/week
    transfers = [
        _t(C59E, 0.001), _t(C59E, 0.002),
        _t(C6777, 0.001),
    ]
    report = recon.classify_transfers(transfers)  # default KNOWN_PAYERS applies
    assert report["external_unique_payers"] == 0
    assert report["known_verification_txs"] == 3
    labels = {k["label"] for k in report["known_verifications"]}
    assert labels == {"market_sampler_c59e", "market_crawler_6777"}
    assert report["repeat_payers"] == []  # samplers never look like customers


def test_unknown_new_payer_still_fires_launch_signal():
    """A genuinely NEW payer (human or new infra) must count as external —
    the launch signal survives the sampler exclusion."""
    NEW = "0x" + "e" * 40
    transfers = [_t(NEW, 0.003), _t(NEW, 0.005)]
    report = recon.classify_transfers(transfers)
    assert report["external_unique_payers"] == 1
    assert report["repeat_payers"][0]["payer"] == NEW