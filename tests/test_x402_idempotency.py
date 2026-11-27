"""The client half of the duplicate-settlement answer, pinned.

On x402-foundation/x402#4367 every double-settled intent turned out to be two distinct
nonces on the same payer — two authorizations signed about two seconds apart — rather
than one authorization replayed. So the nonce is the idempotency key, the token contract
records its consumption, and the missing piece is a client that remembers what it signed.

These tests work without a network: `is_consumed` is replaced with a stub, because the
rule being tested is about DECISIONS, not about Base.
"""
import pytest

from scripts import x402_idempotency as xid

PAYER = "0xE50c5212e8211639C49276dA190E248B83935763"
NONCE = "0x" + "ab" * 32
OTHER = "0x" + "cd" * 32


@pytest.fixture()
def store(tmp_path):
    return xid.NonceStore(tmp_path / "intents.db")


def _stub_consumed(monkeypatch, answer):
    calls = []

    def fake(payer, nonce, rpc_url=xid.DEFAULT_RPC, **kwargs):
        calls.append((payer, nonce))
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(xid, "is_consumed", fake)
    return calls


def test_an_unconsumed_nonce_is_safe_to_sign(store, monkeypatch):
    calls = _stub_consumed(monkeypatch, False)

    assert xid.decide(store, PAYER, NONCE, "buy-brief") == "sign"
    assert len(calls) == 1, "the chain must actually be asked"


def test_a_consumed_nonce_is_replayed_not_signed_again(store, monkeypatch):
    """The failure this exists for: a retry after a timeout, where the money moved
    and the response never arrived. Signing again pays a second time."""
    _stub_consumed(monkeypatch, True)
    store.claim(PAYER, NONCE, "buy-brief")
    store.mark_consumed(PAYER, NONCE, '{"ok": true, "value": 42}')

    assert xid.decide(store, PAYER, NONCE, "buy-brief") == "replay"
    assert store.result(PAYER, NONCE) == {"ok": True, "value": 42}


def test_a_settlement_failure_looks_like_a_free_retry(store, monkeypatch):
    """`invalid_exact_evm_transaction_failed` settles nothing, so the nonce stays
    unconsumed and the retry is genuinely safe — the case that makes the rule
    worth having rather than merely cautious."""
    _stub_consumed(monkeypatch, False)
    store.claim(PAYER, NONCE, "buy-brief")

    assert xid.decide(store, PAYER, NONCE, "buy-brief") == "sign"


def test_an_unreadable_chain_refuses_rather_than_guessing(store, monkeypatch):
    """A chain we could not read is not a licence to sign again."""
    _stub_consumed(monkeypatch, RuntimeError("rpc down"))

    assert xid.decide(store, PAYER, NONCE, "buy-brief") == "unknown"
    assert not store.known(PAYER, NONCE), (
        "a refused decision must not leave a claim behind that looks like a send")


def test_the_claim_is_written_before_the_send_and_is_idempotent(store):
    assert store.claim(PAYER, NONCE, "buy-brief") is True
    assert store.claim(PAYER, NONCE, "buy-brief") is False, (
        "claiming twice for one intent is exactly what must not happen")
    assert store.known(PAYER, NONCE)


def test_the_store_is_durable_across_processes(tmp_path):
    """The case it protects against is a process that died between signing and
    hearing back — so an in-memory set would fail precisely when it is needed."""
    first = xid.NonceStore(tmp_path / "intents.db")
    first.claim(PAYER, NONCE, "buy-brief")
    first.mark_consumed(PAYER, NONCE, '{"ok": true}')

    second = xid.NonceStore(tmp_path / "intents.db")
    assert second.known(PAYER, NONCE)
    assert second.result(PAYER, NONCE) == {"ok": True}


def test_two_nonces_are_two_intents(store, monkeypatch):
    """Two authorizations is what the stress test actually found. Persisting per
    nonce therefore cannot hide a genuine second purchase."""
    _stub_consumed(monkeypatch, False)
    store.claim(PAYER, NONCE, "buy-brief")
    store.claim(PAYER, OTHER, "buy-brief")

    assert xid.decide(store, PAYER, NONCE, "buy-brief") == "sign"
    assert xid.decide(store, PAYER, OTHER, "buy-brief") == "sign"
    assert store.known(PAYER, OTHER)


def test_a_short_nonce_is_rejected_before_any_rpc_call(monkeypatch):
    """A malformed nonce must fail here, not become a query for the wrong slot."""
    from web3 import Web3

    monkeypatch.setattr(Web3, "HTTPProvider", lambda *a, **k: None)
    with pytest.raises(ValueError):
        xid.is_consumed(PAYER, "0xdeadbeef")
