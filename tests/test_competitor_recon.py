"""Regression tests for scripts/competitor_recon.py (pure logic only)."""

import importlib
import sys
import types
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


def test_known_payers_registry_contains_crawler_54e1():
    """0x54E1 (fingerprinted 08.09: 325 receivers / 1281 tx / $11.32 per 30d)
    is registered as market infrastructure."""
    assert "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0" in recon.KNOWN_PAYERS
    assert (recon.KNOWN_PAYERS["0x54e163e9b8edda194d83f46add921bfa5fc5f4e0"]
            == "market_crawler_54e1")


def test_crawler_54e1_is_heartbeat_not_customer():
    """0x54E1 must NOT count as external — external_unique_payers stays 1
    (only the human 0x4dB7); the crawler lands in the heartbeat bucket."""
    C54E1 = "0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0"
    HUMAN = "0x4dB7AAFbe797a39Cd6Cc4E7aa64d970F7F6E02B7"
    transfers = [_t(C54E1, 0.003, tx="0x" + "b" * 64), _t(HUMAN, 0.003)]
    report = recon.classify_transfers(transfers)
    assert report["external_unique_payers"] == 1
    assert report["total_txs"] == 1
    assert report["total_usdc"] == 0.003
    assert report["known_verification_txs"] == 1
    assert report["known_verifications"][0]["label"] == "market_crawler_54e1"
    assert report["repeat_payers"] == []


def test_filter_not_too_broad_new_payer_fires_alongside_crawler_54e1():
    """A brand-new unknown payer STILL fires the launch signal even when the
    crawler 0x54E1 pays at the same time — the filter only hides known infra."""
    BRAND_NEW = "0x" + "f" * 40
    transfers = [
        _t("0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0", 0.003),
        _t(BRAND_NEW, 0.003, tx="0x" + "f" * 64),
        _t(BRAND_NEW, 0.005, tx="0x" + "e" * 64),
    ]
    report = recon.classify_transfers(transfers)
    assert report["external_unique_payers"] == 1
    assert report["repeat_payers"][0]["payer"] == BRAND_NEW


def test_filter_not_too_broad_new_payer_fires_alongside_crawler_54e1():
    """A brand-new unknown payer STILL fires the launch signal even when the
    crawler 0x54E1 pays at the same time — the filter only hides known infra."""
    BRAND_NEW = "0x" + "f" * 40
    transfers = [
        _t("0x54E163e9B8eDDa194D83F46AdD921bfA5fc5f4E0", 0.003),
        _t(BRAND_NEW, 0.003, tx="0x" + "f" * 64),
        _t(BRAND_NEW, 0.005, tx="0x" + "e" * 64),
    ]
    report = recon.classify_transfers(transfers)
    assert report["external_unique_payers"] == 1
    assert report["repeat_payers"][0]["payer"] == BRAND_NEW


def test_watchlist_registry_has_operator_wallets():
    """0x4dB7 is a watchlisted OPERATOR (a real customer, must keep counting as
    external). 0xA19F is NOT: the 14.09 chain audit found 125 outgoing transfers
    to 98 distinct receivers, so it was promoted to known crawl infrastructure on
    17.09 — WATCHLIST labels are revisable, the chain is the judge.
    """
    A19F = "0xa19f621581dbc851a21d6179868111709a52accc"
    assert A19F in recon.KNOWN_PAYERS
    assert recon.KNOWN_PAYERS[A19F] == "market_crawler_a19f"
    assert A19F not in recon.WATCHLIST
    assert "0x4db7aafbe797a39cd6cc4e7aa64d970f7f6e02b7" in recon.WATCHLIST


def test_every_known_payer_label_has_a_dashboard_class():
    """The taxonomy lives in two files: `KNOWN_PAYERS` (labels) and the
    dashboard's `PAYER_CLASSES` (classes). A label without a class silently
    falls back to `sampler`, which is how a promotion can go half-done — pin
    that the two agree, and that the 17.09 promotion is covered on both sides.
    """
    from integrations.dashboard_store import PAYER_CLASSES

    for label in recon.KNOWN_PAYERS.values():
        assert label in PAYER_CLASSES, "%s has no dashboard class" % label
    assert PAYER_CLASSES["market_crawler_a19f"] == "sampler"


def test_promoted_crawler_a19f_is_a_heartbeat_not_a_customer():
    """After the promotion the machine can no longer masquerade as a launch
    signal: its payment lands in the heartbeat bucket (label + class `sampler`)
    and the totals stay honest."""
    A19F = "0xA19F621581DBc851a21D6179868111709a52aCCC"
    report = recon.classify_transfers([_t(A19F, 0.003)])
    assert report["external_unique_payers"] == 0
    assert report["total_txs"] == 0                # excluded from operator stats
    assert report["known_verification_txs"] == 1
    assert report["known_verifications"][0]["label"] == "market_crawler_a19f"
    assert report["known_verifications"][0]["total_usdc"] == 0.003  # still paid


def test_promoted_crawler_a19f_never_fires_the_operator_deal_trigger():
    """A second payment from the crawler is NOT a deal trigger — only 0x4dB7
    (the watchlisted human operator) can fire it now."""
    A19F = "0xA19F621581DBc851a21D6179868111709a52aCCC"
    twice = [_t(A19F, 0.003), _t(A19F, 0.003, tx="0x" + "c" * 64)]
    assert recon.operator_repeats(twice) == []


def test_operator_repeats_fires_on_second_payment():
    """First payment = first-touch (no trigger). Second payment from the
    SAME watchlisted wallet = OPERATOR REPEAT (the deal trigger)."""
    OP = "0x4dB7AAFbe797a39Cd6Cc4E7aa64d970F7F6E02B7"
    first = [_t(OP, 0.003)]
    assert recon.operator_repeats(first) == []          # first touch — silent

    second = first + [_t(OP, 0.003, tx="0x" + "b" * 64)]
    repeats = recon.operator_repeats(second)
    assert len(repeats) == 1
    assert repeats[0]["label"] == "operator_watch_4db7"
    assert repeats[0]["txs"] == 2
    assert repeats[0]["total_usdc"] == 0.006


def test_operator_repeats_ignores_non_watchlisted_payers():
    """Repeat detection is scoped to the watchlist — a random operator that
    pays twice is NOT flagged (only watchlisted wallets get the deal trigger)."""
    RANDOM = "0x" + "9" * 40
    transfers = [_t(RANDOM, 0.003), _t(RANDOM, 0.003, tx="0x" + "9" * 63 + "1")]
    assert recon.operator_repeats(transfers) == []


# ── 17.09: the public RPC answers 413 above ~1000 blocks for our filter ─────
# The old code dropped refused chunks and moved on, so the weekly monitor
# reported an EMPTY week. An unread window is not an empty one — these tests
# pin the fix: halve the range, read the whole window, and REPORT any gap.


class _FakeNode:
    """get_logs stub: refuses any range wider than `max_width` (like the RPC)."""

    def __init__(self, max_width, latest=10_000, logs=None):
        self.max_width = max_width
        self.block_number = latest
        self.logs = list(logs or [])
        self.calls = []
        self.eth = self

    def get_logs(self, query):
        width = query["toBlock"] - query["fromBlock"] + 1
        self.calls.append((query["fromBlock"], query["toBlock"]))
        if width > self.max_width:
            raise Exception("413 Client Error: Payload Too Large "
                            "for url: https://mainnet.base.org/")
        return list(self.logs)


def _install_fake_web3(monkeypatch, node):
    """Patch `sys.modules['web3']` — the module imports Web3 inside the call."""

    class FakeWeb3:
        HTTPProvider = staticmethod(lambda *a, **k: None)
        to_checksum_address = staticmethod(lambda a: a)
        to_hex = staticmethod(lambda b: "0x" + bytes(b).hex())

        def __init__(self, provider, request_kwargs=None):
            self.eth = node

        def is_connected(self):
            return True

    module = types.ModuleType("web3")
    module.Web3 = FakeWeb3
    monkeypatch.setitem(sys.modules, "web3", module)
    return node


def _log(payer_hex, amount_units, block=42):
    return {
        "topics": [bytes(32), bytes(12) + bytes.fromhex(payer_hex),
                   bytes(12) + bytes.fromhex("cd" * 20)],
        "transactionHash": bytes.fromhex("11" * 32),
        "data": amount_units.to_bytes(32, "big"),
        "blockNumber": block,
    }


def test_get_logs_splits_ranges_the_node_refuses_and_reads_the_whole_window(monkeypatch):
    """1000-block chunks get 413 → each is halved and retried, so a 10k-block
    window is read end to end instead of silently returning nothing."""
    node = _install_fake_web3(monkeypatch, _FakeNode(max_width=500, latest=10_000))
    stats = {}
    transfers = recon.fetch_incoming_transfers(
        "https://fake", recon.DEFAULT_RECEIVER, from_block=1, to_block=10_000,
        chunk_size=1000, pause_seconds=0, stats=stats)

    assert transfers == []
    assert stats["complete"] is True
    assert stats["scanned_blocks"] == stats["requested_blocks"] == 10_000
    assert stats["failed_ranges"] == []
    assert stats["split_retries"] == 10                 # every 1000-wide chunk split
    assert stats["chunks"] == 20                        # …into 2×500 that worked
    assert max(e - s + 1 for s, e in node.calls) == 1000  # started at the limit


def test_unreadable_window_is_reported_instead_of_looking_empty(monkeypatch):
    """A node that refuses everything must leave `complete=False` + the failed
    ranges — never a silent 'no payments' week."""
    _install_fake_web3(monkeypatch, _FakeNode(max_width=0, latest=1_000))
    stats = {}
    transfers = recon.fetch_incoming_transfers(
        "https://fake", recon.DEFAULT_RECEIVER, from_block=1, to_block=1_000,
        chunk_size=1000, pause_seconds=0, stats=stats)

    assert transfers == []
    assert stats["complete"] is False
    assert stats["scanned_blocks"] == 0
    assert stats["failed_ranges"]                       # the gap stays visible
    assert all(e - s + 1 <= recon.MIN_CHUNK_BLOCKS for s, e in stats["failed_ranges"])
    assert stats["split_retries"] >= 8                  # 1000 → … → 100 blocks


def test_fetch_decodes_transfers_and_reports_full_coverage(monkeypatch):
    """Happy path unchanged: a node that serves the range returns the payments
    with full coverage (no bogus split, no incomplete flag)."""
    node = _install_fake_web3(
        monkeypatch, _FakeNode(max_width=10_000, latest=500, logs=[_log("ab" * 20, 3000)]))
    stats = {}
    transfers = recon.fetch_incoming_transfers(
        "https://fake", recon.DEFAULT_RECEIVER, from_block=1, to_block=500,
        chunk_size=1000, pause_seconds=0, stats=stats)

    assert len(transfers) == 1
    assert transfers[0]["payer"] == "0x" + "ab" * 20
    assert transfers[0]["amount_usdc"] == 0.003
    assert transfers[0]["tx_hash"] == "0x" + "11" * 32
    assert stats["complete"] is True and stats["split_retries"] == 0
    assert stats["chunks"] == 1 and node.calls == [(1, 500)]


def test_fingerprint_never_calls_an_unread_payer_human(monkeypatch):
    """`human` feeds external_unique_payers (the launch signal) — so a window we
    could not read must classify as `unknown`, not as a human customer."""
    _install_fake_web3(monkeypatch, _FakeNode(max_width=0, latest=1_000))
    fp = recon.fingerprint_payer("https://fake", "0x" + "a" * 40, days=1,
                                 chunk_size=1000)

    assert fp["classification"] == "unknown"
    assert fp["scan_complete"] is False
    assert fp["scan_failed_ranges"]
    assert fp["distinct_receivers"] == 0
    assert fp["scan_blocks"] == "0/1000"