#!/usr/bin/env python3
"""settlement_pending acceptance + chain-before-delivery, as a runnable test.

FIXTURE 1 for OmniDome Agent Commons (issue #3, "chain-before-delivery").
Single file, standard library only, no network, no wallet, no keys.

WHAT THIS IS
------------
A redacted extraction of the decision logic in the Kristo Intelligence
production code, with the transport removed. It is not the production code:
it is the decision table those files implement, pinned so that a stranger can
run it and see what the rules are.

Production source this was extracted from (MIT):

    commit  aa2600429bfbf215cc377350f98736e3ddc179db
    blob    services/connectors.py  ba69d51a84a05f5cd557e15c35904dbaf604daca
    blob    main.py                  fda47ea312c2bd6fc9ee917dd85eb9028a66d6ca

    _adopt_settlement_pending          services/connectors.py:1119
    _adopt_already_settled             services/connectors.py:1147
    _verify_payment_onchain            main.py:4243
    _receipt_usdc_transfer             main.py:4199
    _confirmations_ok_with_lag_refresh main.py:3966
    _try_consume_payment_proof         main.py:4294
    _admit_undelivered_payment         main.py:4162

WHAT IT PINS
------------
1. A broadcast hash in an unsettled/pending state is NOT a failed payment,
   NOT a completed payment and NOT a delivered tool result. It is held, with
   an explicit pending/indeterminate verdict.
2. On retry with the original operation ID (the settlement's transaction
   hash), the seller checks the chain: the receipt exists, its status is 1,
   the USDC Transfer goes to the seller's own payTo, the amount is at least
   the price, and the receipt is buried deep enough. The presence of a hash
   is not enough.
3. When settlement is confirmed, at most one business-side effect happens,
   and a lost response is recovered without a second debit.
4. An unconfirmed or mismatched settlement is held with a verdict of
   pending/indeterminate — never "allow".
5. Matching is on the errorReason CODE, never on the message text; a terminal
   failure is never adopted, even when it carries a hash.

RUN IT
------
    python3 test_settlement_pending_chain_before_delivery.py
    python3 test_settlement_pending_chain_before_delivery.py --json
    pytest -q test_settlement_pending_chain_before_delivery.py

Exit code 0 means every assertion held. No dependency is installed and no
network call is made.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ── The decision vocabulary ───────────────────────────────────────────────
# These are the only four verdicts. "pending" and "indeterminate" are both
# HOLDS: the action is not allowed and not failed. "deny" is terminal.
ALLOW = "allow"
DENY = "deny"
PENDING = "pending"
INDETERMINATE = "indeterminate"

# ── Synthetic fixtures. Every address and hash below is invented. ─────────
SETTLEMENT_PENDING_CODE = "settlement_pending"

#: Spec §9 terminal codes. A response carrying one of these is a failure and
#: must never be adopted, even when it also carries a transaction hash.
TERMINAL_CODES = (
    "insufficient_funds",
    "invalid_exact_evm_payload_signature",
    "unexpected_settle_error",
    "invalid_transaction_state",
)

#: Base mainnet USDC. The only token a valid transfer may move.
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"

#: The seller's own receiving address. Synthetic.
PAY_TO = "0x00000000000000000000000000000000000000a1"

#: A different address, for the "paid someone else" case. Synthetic.
OTHER_PAY_TO = "0x00000000000000000000000000000000000000b2"

#: A different token, for the "wrong asset" case. Synthetic.
OTHER_TOKEN = "0x00000000000000000000000000000000000000d4"

#: The price of one call, in USDC. Synthetic.
PRICE = 0.05

#: How deep a receipt must be buried. Our production default is 3 on the
#: proof rail; the standard rail requires 1. 3 is the stricter case.
REQUIRED_CONFIRMATIONS = 3


# ── The chain, as a plain in-memory object ────────────────────────────────
@dataclass(frozen=True)
class Transfer:
    """One ERC-20 Transfer log, already decoded."""

    token: str
    to: str
    amount_usdc: float
    sender: str = "0x00000000000000000000000000000000000000c3"


@dataclass(frozen=True)
class Receipt:
    """A mined transaction receipt. status 1 = success, 0 = reverted."""

    tx_hash: str
    status: int
    block_number: int
    transfers: Tuple[Transfer, ...] = ()


class SyntheticChain:
    """A deterministic chain. No RPC, no clock, no network."""

    def __init__(self, head: int, receipts: Dict[str, Receipt]):
        self.head = head
        self._receipts = {k.lower(): v for k, v in receipts.items()}

    def receipt(self, tx: str) -> Optional[Receipt]:
        return self._receipts.get(tx.lower())

    def confirmations(self, tx: str) -> int:
        r = self.receipt(tx)
        if r is None:
            return 0
        return max(0, self.head - r.block_number + 1)


def _is_tx_hash(value: Any) -> bool:
    """A 32-byte hex string. Anything else is not a transaction."""
    if not isinstance(value, str):
        return False
    v = value.strip()
    if len(v) != 66 or not v.startswith("0x"):
        return False
    try:
        int(v[2:], 16)
    except ValueError:
        return False
    return True


def _is_usdc_transfer(t: Transfer, pay_to: str, price: float) -> bool:
    """The one rule for "this transfer is the payment": token, payTo, amount."""
    return (
        t.token.lower() == USDC.lower()
        and t.to.lower() == pay_to.lower()
        and t.amount_usdc + 1e-9 >= price
    )


# ── Rule 1: adopt a settlement_pending hash, never a terminal one ─────────
def adopt_settlement_pending(resp: Any) -> Optional[str]:
    """The tx hash from a NON-TERMINAL `settlement_pending` settle response.

    Spec §9: a facilitator that broadcast the transaction but could not
    confirm it answers `success: false` with `errorReason:
    "settlement_pending"` and the broadcast hash. It is NOT a failure — the
    transaction may still land — so the hash is adopted for reconciliation.

    Matching is on the CODE, never the message text. A facilitator may reword
    `errorMessage` in any release, and a rule that matched the word "pending"
    would adopt an unrelated terminal failure the moment somebody changed a
    sentence — and refuse a real one when they stopped using the word.
    """
    if not isinstance(resp, dict):
        return None
    if resp.get("success") is True:
        return None  # the regular success path handles it
    if str(resp.get("errorReason") or "").strip() != SETTLEMENT_PENDING_CODE:
        return None
    tx = resp.get("transaction")
    return tx if _is_tx_hash(tx) else None


# ── Rule 2: the chain decides, not the hash ───────────────────────────────
@dataclass
class ChainCheck:
    """What the chain says about one transaction hash."""

    found: bool
    status: Optional[int]
    confirmations: int
    matching_amount: Optional[float]
    reasons: List[str]


def check_chain(
    chain: SyntheticChain,
    tx: str,
    pay_to: str = PAY_TO,
    price: float = PRICE,
    required: int = REQUIRED_CONFIRMATIONS,
) -> ChainCheck:
    """Verify the transfer itself: USDC, payTo, amount, depth, status.

    Fail-closed throughout: an unknown transaction, a reverted one, a
    shallow one, or one that moved the wrong asset to the wrong address is
    never "verified".
    """
    r = chain.receipt(tx)
    if r is None:
        return ChainCheck(False, None, 0, None, ["no_receipt"])

    reasons: List[str] = []
    if r.status != 1:
        reasons.append("receipt_status_%s" % r.status)

    conf = chain.confirmations(tx)
    if conf < required:
        reasons.append("confirmations_%d_lt_%d" % (conf, required))

    matching = None
    for t in r.transfers:
        if _is_usdc_transfer(t, pay_to, price):
            matching = t.amount_usdc
            break
    if matching is None:
        reasons.append("no_matching_usdc_transfer")

    return ChainCheck(True, r.status, conf, matching, reasons)


# ── The decision table ────────────────────────────────────────────────────
@dataclass
class Decision:
    """One verdict for one settle response. `delivered` is set only on ALLOW."""

    verdict: str
    tx_hash: Optional[str]
    adopted: bool
    reasons: List[str]
    delivered: bool = False
    effect: Any = None


def _decide_on_chain(
    chain: SyntheticChain,
    tx: str,
    pay_to: str,
    price: float,
    required: int,
    adopted: bool,
) -> Decision:
    check = check_chain(chain, tx, pay_to, price, required)

    # Not mined yet: hold. The transaction may still land.
    if not check.found:
        return Decision(PENDING, tx, adopted, ["no_receipt"])

    # Mined and reverted: the money did not move. This is terminal.
    if check.status == 0:
        return Decision(DENY, tx, adopted, ["receipt_reverted"])

    # Mined but not deep enough to be settlement: hold.
    if check.status != 1:
        return Decision(PENDING, tx, adopted, ["receipt_status_%s" % check.status])
    if check.confirmations < required:
        return Decision(
            PENDING, tx, adopted,
            ["confirmations_%d_lt_%d" % (check.confirmations, required)],
        )

    # Mined, deep, but the transfer is not ours: hold, indeterminate.
    if check.matching_amount is None:
        return Decision(INDETERMINATE, tx, adopted, check.reasons)

    # Every check passed.
    return Decision(ALLOW, tx, adopted, [])


def decide(
    resp: Any,
    chain: SyntheticChain,
    pay_to: str = PAY_TO,
    price: float = PRICE,
    required: int = REQUIRED_CONFIRMATIONS,
) -> Decision:
    """Map one settle response to one verdict.

    `success: true`  -> verify the chain, then allow/deny/hold.
    `settlement_pending` -> adopt the hash, verify the chain, then allow/hold.
    terminal code    -> deny. Never adopted, even with a hash.
    anything else    -> deny. An unknown code is not a payment.
    """
    if not isinstance(resp, dict):
        return Decision(DENY, None, False, ["not_a_dict"])

    tx = resp.get("transaction")
    code = str(resp.get("errorReason") or "").strip()

    if resp.get("success") is True:
        if not _is_tx_hash(tx):
            return Decision(DENY, None, False, ["success_without_transaction"])
        return _decide_on_chain(chain, tx, pay_to, price, required, adopted=False)

    if code == SETTLEMENT_PENDING_CODE:
        if not _is_tx_hash(tx):
            return Decision(DENY, None, False, ["settlement_pending_without_transaction"])
        return _decide_on_chain(chain, tx, pay_to, price, required, adopted=True)

    if code in TERMINAL_CODES:
        return Decision(DENY, tx if _is_tx_hash(tx) else None, False, ["terminal:" + code])

    return Decision(DENY, tx if _is_tx_hash(tx) else None, False, ["unknown_error:" + code])


# ── Rule 3: one business-side effect, a lost response is recoverable ──────
class EffectStore:
    """Idempotent business-side effect, keyed by the settlement's tx hash.

    The claim is the gate: the first caller gets "new", a delivered one gets
    "replay" (refused), and one that was claimed but never delivered gets
    "recover" (the cached result is returned, the effect is not re-run).
    """

    def __init__(self) -> None:
        self._rows: Dict[str, Dict[str, Any]] = {}
        self.effects_applied = 0

    def claim(self, tx: str) -> str:
        row = self._rows.get(tx.lower())
        if row is None:
            self._rows[tx.lower()] = {"delivered": False, "result": None}
            return "new"
        if row["delivered"]:
            return "replay"
        return "recover"

    def mark_delivered(self, tx: str, result: Any) -> None:
        row = self._rows[tx.lower()]
        row["delivered"] = True
        row["result"] = result

    def result(self, tx: str) -> Any:
        return self._rows[tx.lower()]["result"]


def handle(
    resp: Any,
    chain: SyntheticChain,
    store: EffectStore,
    effect: Any = None,
    deliver_response: bool = True,
    **kwargs: Any,
) -> Decision:
    """Decide, then apply the business effect at most once.

    `deliver_response=False` simulates a response that was produced but never
    reached the buyer: the effect is applied and cached, the claim stays
    undelivered. The next call with the same tx hash recovers the cached
    result without a second effect.
    """
    d = decide(resp, chain, **kwargs)
    if d.verdict != ALLOW:
        return d

    tx = d.tx_hash
    mode = store.claim(tx)

    if mode == "replay":
        d.verdict = DENY
        d.reasons = ["replay_blocked"]
        d.delivered = True
        return d

    if mode == "recover":
        d.reasons = ["recovered_lost_response"]
        d.delivered = True
        d.effect = store.result(tx)
        # The recovery counts as the delivery: a second retry is a replay.
        store.mark_delivered(tx, d.effect)
        return d

    # "new": the first and only time the effect runs.
    d.effect = effect() if callable(effect) else {"ok": True}
    store._rows[tx.lower()]["result"] = d.effect
    store.effects_applied += 1
    if deliver_response:
        store.mark_delivered(tx, d.effect)
        d.delivered = True
    else:
        d.delivered = False  # the response was lost; the effect is not
    return d


# ── Fixtures ──────────────────────────────────────────────────────────────
TX = "0x" + "ab" * 32
TX2 = "0x" + "cd" * 32


def pending_resp(tx: str = TX, message: str = "node returned 503 while waiting for the receipt") -> Dict[str, Any]:
    return {
        "success": False,
        "errorReason": SETTLEMENT_PENDING_CODE,
        "errorMessage": message,
        "transaction": tx,
        "network": "eip155:8453",
    }


def chain_with(
    tx: str = TX,
    status: int = 1,
    block: int = 995,
    head: int = 997,
    to: str = PAY_TO,
    token: str = USDC,
    amount: float = PRICE,
) -> SyntheticChain:
    return SyntheticChain(
        head=head,
        receipts={
            tx: Receipt(
                tx_hash=tx,
                status=status,
                block_number=block,
                transfers=(Transfer(token=token, to=to, amount_usdc=amount),),
            )
        },
    )


# ── Tests. One per assertion in the request. ──────────────────────────────
def test_pending_is_not_failure_not_completion_not_delivery():
    """Assertion 1: a pending broadcast is held, not failed, not delivered."""
    d = decide(pending_resp(), SyntheticChain(head=1000, receipts={}))
    assert d.verdict == PENDING, d.verdict
    assert d.adopted is True, "the hash was not adopted"
    assert d.delivered is False, "a pending settlement was delivered"
    assert d.verdict != ALLOW, "a pending settlement was allowed"
    assert d.verdict != DENY, "a pending settlement was treated as a failure"
    assert d.tx_hash == TX, "the broadcast hash was not carried forward"


def test_retry_verifies_the_chain_not_just_the_hash():
    """Assertion 2: the same hash gets seven different verdicts by chain state."""
    # 1. Not mined yet -> hold.
    d = decide(pending_resp(), SyntheticChain(head=1000, receipts={}))
    assert d.verdict == PENDING, d.verdict

    # 2. Mined and reverted -> deny. The money did not move.
    d = decide(pending_resp(), chain_with(status=0, block=995))
    assert d.verdict == DENY, d.verdict

    # 3. Mined, status 1, but too shallow -> hold.
    d = decide(pending_resp(), chain_with(status=1, block=997, head=998))
    assert d.verdict == PENDING, d.verdict

    # 4. Mined, deep, but the transfer went to someone else -> indeterminate.
    d = decide(pending_resp(), chain_with(to=OTHER_PAY_TO))
    assert d.verdict == INDETERMINATE, d.verdict

    # 5. Mined, deep, but the wrong token -> indeterminate.
    d = decide(pending_resp(), chain_with(token=OTHER_TOKEN))
    assert d.verdict == INDETERMINATE, d.verdict

    # 6. Mined, deep, but underpaid -> indeterminate.
    d = decide(pending_resp(), chain_with(amount=0.01))
    assert d.verdict == INDETERMINATE, d.verdict

    # 7. Every check passes -> allow.
    d = decide(pending_resp(), chain_with())
    assert d.verdict == ALLOW, d.verdict


def test_confirmed_settles_exactly_one_effect_and_recovers_a_lost_response():
    """Assertion 3: one effect, and a lost response does not debit twice."""
    store = EffectStore()
    calls: List[int] = []

    def effect() -> Dict[str, Any]:
        calls.append(1)
        return {"tool": "get_whale_flow", "value": 42}

    # First delivery: one effect, delivered.
    d = handle(pending_resp(), chain_with(), store, effect=effect)
    assert d.verdict == ALLOW and d.delivered is True, d.verdict
    assert store.effects_applied == 1 and len(calls) == 1

    # Replay with the same tx: refused, no second effect.
    d = handle(pending_resp(), chain_with(), store, effect=effect)
    assert d.verdict == DENY, d.verdict
    assert store.effects_applied == 1 and len(calls) == 1, "a replay ran the effect again"

    # A lost response: the effect ran, the buyer never got the answer.
    d = handle(pending_resp(TX2), chain_with(tx=TX2), store, effect=effect, deliver_response=False)
    assert d.verdict == ALLOW and d.delivered is False, d.verdict
    assert store.effects_applied == 2 and len(calls) == 2

    # Retry with the original operation ID: recovered, no second effect.
    d = handle(pending_resp(TX2), chain_with(tx=TX2), store, effect=effect)
    assert d.verdict == ALLOW and d.delivered is True, d.verdict
    assert d.effect == {"tool": "get_whale_flow", "value": 42}, d.effect
    assert store.effects_applied == 2 and len(calls) == 2, "recovery ran the effect again"

    # A second retry: replay, refused.
    d = handle(pending_resp(TX2), chain_with(tx=TX2), store, effect=effect)
    assert d.verdict == DENY, d.verdict
    assert store.effects_applied == 2 and len(calls) == 2


def test_unconfirmed_or_mismatched_is_held_never_allow():
    """Assertion 4: the held verdicts are explicit, and never "allow"."""
    cases = [
        (SyntheticChain(head=1000, receipts={}), PENDING),
        (chain_with(status=1, block=997, head=998), PENDING),
        (chain_with(to=OTHER_PAY_TO), INDETERMINATE),
        (chain_with(token=OTHER_TOKEN), INDETERMINATE),
        (chain_with(amount=0.001), INDETERMINATE),
    ]
    for chain, expected in cases:
        d = decide(pending_resp(), chain)
        assert d.verdict == expected, (d.verdict, expected)
        assert d.verdict != ALLOW, "a held settlement was allowed"
        assert d.delivered is False, "a held settlement was delivered"


def test_adoption_matches_the_code_not_the_message():
    """Assertion 5a: the message text never decides adoption."""
    # The message says "pending", but the code is terminal -> not adopted.
    d = decide(
        {
            "success": False,
            "errorReason": "unexpected_settle_error",
            "errorMessage": "settlement is pending confirmation",
            "transaction": TX,
        },
        SyntheticChain(head=1000, receipts={}),
    )
    assert d.verdict == DENY and d.adopted is False, d.verdict

    # The code says pending, the message says 503 -> adopted.
    d = decide(pending_resp(), SyntheticChain(head=1000, receipts={}))
    assert d.verdict == PENDING and d.adopted is True, d.verdict


def test_terminal_failure_is_never_adopted_even_with_a_hash():
    """Assertion 5b: a terminal code is a failure, hash or no hash."""
    for code in TERMINAL_CODES:
        d = decide(
            {"success": False, "errorReason": code, "transaction": TX},
            SyntheticChain(head=1000, receipts={}),
        )
        assert d.verdict == DENY and d.adopted is False, code


def test_a_non_hash_is_never_adopted():
    """Assertion 5c: anything that is not a 32-byte hash is not a payment."""
    for bad in (None, "", "not-a-hash", "0x" + "cd" * 31, "0x" + "zz" * 32):
        d = decide(
            {"success": False, "errorReason": SETTLEMENT_PENDING_CODE, "transaction": bad},
            SyntheticChain(head=1000, receipts={}),
        )
        assert d.verdict == DENY and d.adopted is False, bad


# ── Synthetic input / expected output, as JSON ────────────────────────────
def fixture() -> Dict[str, Any]:
    """The one case a reader can diff without reading the code."""
    return {
        "synthetic_input": {
            "settle_response": {
                "success": False,
                "errorReason": SETTLEMENT_PENDING_CODE,
                "errorMessage": "node returned 503 while waiting for the receipt",
                "transaction": TX,
                "network": "eip155:8453",
            },
            "chain": {
                "head": 997,
                "receipt": {
                    "tx_hash": TX,
                    "status": 1,
                    "block_number": 995,
                    "transfers": [
                        {"token": USDC, "to": PAY_TO, "amount_usdc": PRICE}
                    ],
                },
            },
            "price": PRICE,
            "pay_to": PAY_TO,
            "required_confirmations": REQUIRED_CONFIRMATIONS,
        },
        "expected_output": {
            "verdict": ALLOW,
            "adopted": True,
            "tx_hash": TX,
            "delivered": True,
            "effect_count": 1,
        },
    }


# ── Runner: works with or without pytest ──────────────────────────────────
def _tests() -> List[Tuple[str, Any]]:
    return sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )


def run_all() -> int:
    failures = 0
    tests = _tests()
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print("FAIL  %s  %s" % (name, exc))
        else:
            print("PASS  %s" % name)
    print("\n%d passed, %d failed" % (len(tests) - failures, failures))
    return 1 if failures else 0


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(fixture(), indent=2))
        sys.exit(0)
    sys.exit(run_all())
