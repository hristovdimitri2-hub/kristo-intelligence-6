"""F1/Miguel regression (01.10): hexbytes >= 1.0 returns `.hex()` WITHOUT the
`0x` prefix. Two production paths compared the raw `.hex()` against
`0x`-prefixed values, so the manual X-Payment-Proof rail answered a VALID
payment with a silent 401 `invalid_payment_proof`:

  * `_verify_payment_onchain` skipped the Transfer event (topic0 mismatch)
    -> returned None on every attempt (20/20 for tx 0xaced828…);
  * `_process_incoming_transfer` stored the RAM sale tx without `0x`, so the
    fast path could never match the proof's `0x…` tx hash.

Both tests are offline: stubbed web3 objects, RAM-only state, no DB writes.
"""

import copy

import pytest

TX = "0x" + "ab" * 32
PAYER = "0x" + "cd" * 20
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
BLOCK = 50_000_000


def _transfer_log(main, amount_atomic=3000):
    """One USDC Transfer receipt log with REAL HexBytes objects — the
    hexbytes 2.0.0 semantics that broke production (`.hex()` has no `0x`)."""
    from hexbytes import HexBytes

    return {
        "address": USDC,
        "topics": [
            HexBytes(main._TRANSFER_EVENT_TOPIC),
            HexBytes("0x" + "00" * 12 + PAYER[2:]),
            HexBytes("0x" + "00" * 12 + main.X402_RECEIVER_ADDRESS[2:]),
        ],
        "data": HexBytes(amount_atomic.to_bytes(32, "big")),
    }


class _StubEth:
    def __init__(self, receipt, head):
        self._receipt = receipt
        self._head = head

    @property
    def block_number(self):
        return self._head

    def get_transaction_receipt(self, tx):
        return self._receipt


class _StubW3:
    def __init__(self, receipt, head):
        self.eth = _StubEth(receipt, head)


def test_verify_payment_onchain_survives_hexbytes_topics_without_0x(monkeypatch):
    """Test A — the slow path must ACCEPT a real confirmed transfer even when
    topics are HexBytes whose .hex() lacks the 0x prefix."""
    import main

    receipt = {"status": 1, "blockNumber": BLOCK, "logs": [_transfer_log(main)]}
    monkeypatch.setattr(main, "_get_verify_web3", lambda: _StubW3(receipt, BLOCK + 500))
    try:
        result = main._verify_payment_onchain(TX, PAYER, 0.003)
        assert result == pytest.approx(0.003), (
            "on-chain verify must return the transfer amount for a deep, "
            "successful, correctly-addressed $0.003 Transfer"
        )
    finally:
        main._verify_block.pop(TX.lower(), None)


def test_process_incoming_transfer_stores_0x_prefixed_tx(monkeypatch):
    """Test B — the fast path key: a sale recorded from hexbytes-style data
    must end up in `_sales_history` with a 0x-prefixed tx hash, otherwise
    `tx != proof['tx_hash']` forever."""
    from hexbytes import HexBytes

    import main

    tx = HexBytes("0x" + "ef" * 32)
    assert not tx.hex().startswith("0x")  # hexbytes 2.x — the prod semantics

    class _Call:
        def __init__(self, value):
            self._value = value

        def call(self):
            return self._value

    class _Functions:
        def decimals(self):
            return _Call(6)

    class _USDCStub:
        functions = _Functions()

    class _W3StubEth:
        def get_block(self, number):
            return {"timestamp": 1767225600}  # 2026-01-01 UTC

    class _W3Stub:
        eth = _W3StubEth()

    class _Wallet:
        usdc = _USDCStub()
        w3 = _W3Stub()

    log_entry = dict(
        _transfer_log(main, amount_atomic=3000),
        transactionHash=tx,
        blockNumber=BLOCK,
    )

    history_snapshot = list(main._sales_history)
    daily_snapshot = copy.deepcopy(main._daily_stats)
    try:
        main._process_incoming_transfer(_Wallet(), log_entry)
        assert main._sales_history, "the transfer was not recorded as a sale"
        row = main._sales_history[-1]
        assert row["tx_hash"].startswith("0x"), (
            "RAM sale tx must carry the 0x prefix — without it the proof "
            "fast path ('0xaced…' vs 'aced…') never matches"
        )
        assert row["tx_hash"] == "0x" + tx.hex()
        assert row["sender"] == PAYER.lower()
        assert row["amount_usd"] == pytest.approx(0.003)
    finally:
        main._sales_history[:] = history_snapshot
        main._daily_stats.clear()
        main._daily_stats.update(daily_snapshot)
