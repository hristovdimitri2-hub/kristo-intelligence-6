#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kristo Intelligence
#
# This file is MIT-licensed: run it, copy it, change it, ship it. The line
# "Production source this was extracted from (MIT)" further down is the licence
# of the code this was extracted FROM; this block is the licence of the file
# itself, so a stranger who runs it does not have to guess.

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
6. The transfer is BOUND to this payment, not merely to the seller's address:
   the transfer's sender must equal the payer that signed the proof. Without
   that binding, an old confirmed payment of ours, to our own payTo, for at
   least the price, is indistinguishable from this payment.
7. Amounts are compared in ATOMIC UNITS (integers), never as floats. A float
   comparison is exact for USDC at six decimals and silently wrong above
   2**53, which a token with 18 decimals reaches.

REVISIONS
---------
This file is a verification artifact, so its own history is part of what it has
to declare. Superseded revisions, and why each was superseded:

    v1  SHA-256 d76537a70102c6399deb9b8be9e8ceae3a90728e2e7d6004cef5840edc4b524e
        7 tests, 22 973 bytes. Verified independently on 23.11.2026 (fetched
        through the GitHub API, hash matched the declared one, exit 0). Two
        defects were found in it by a later external review: the decision
        function checked token, payTo and amount but never the SENDER, so run as
        written it delivered on an old confirmed payment; and it compared
        amounts as floats, which is exact for USDC at six decimals and wrong
        above 2**53 for a token with 18 decimals. Frozen in git as blob
        b0a6150a63cb2aedaa6b26eda85db2cf8cfb85a0 at commit 82ee482.

    v2  SHA-256 d3e0d11a6b3b912bf9db999df3600716ac9ba3ea6d16afb1a1ccfc82afde2c55
        9 tests, 29 522 bytes. Adds the payer binding (PAYER, the sender check,
        the payer_mismatch reason) and atomic-unit comparison.

    this revision adds this REVISIONS block and nothing else of substance, so
    its hash is the one a verifier computes from the bytes in front of them.
    Run it, hash it, and if the hash is not the one the thread names, say so -
    that is the whole point of shipping the bytes rather than the claim.

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

#: The address that signed the payment. The transfer's sender must be THIS
#: address, not merely a transfer to PAY_TO: without that binding an old
#: confirmed payment of ours satisfies every other check. Synthetic.
PAYER = "0x00000000000000000000000000000000000000c3"

#: A second payer, for the "somebody else's payment" case. Synthetic.
OTHER_PAYER = "0x00000000000000000000000000000000000000e5"

#: A different address, for the "paid someone else" case. Synthetic.
OTHER_PAY_TO = "0x00000000000000000000000000000000000000b2"

#: A different token, for the "wrong asset" case. Synthetic.
OTHER_TOKEN = "0x00000000000000000000000000000000000000d4"

#: USDC has six decimals. Amounts are compared in atomic units - integers -
#: never as floats. `0.1 + 0.2 != 0.3` is the small version of that; the large
#: version is that a float loses integer precision above 2**53, which an
#: 18-decimal token reaches at about nine tokens.
USDC_DECIMALS = 6
USDC_SCALE = 10 ** USDC_DECIMALS


def to_atomic(usdc: float) -> int:
    """A human USDC amount as exact atomic units."""
    return int(round(usdc * USDC_SCALE))


#: The price of one call, in atomic units (0.05 USDC). Synthetic.
PRICE_ATOMIC = 50_000

#: The same price for display and for the fixture JSON only. Never compared.
PRICE = PRICE_ATOMIC / USDC_SCALE

#: How deep a receipt must be buried. Our production default is 3 on the
#: proof rail; the standard rail requires 1. 3 is the stricter case.
REQUIRED_CONFIRMATIONS = 3


# ── The chain, as a plain in-memory object ────────────────────────────────
@dataclass(frozen=True)
class Transfer:
    """One ERC-20 Transfer log, already decoded.

    `amount_atomic` is the integer the chain actually carries; `amount_usdc` is
    derived for display only. Comparisons use the integer.
    """

    token: str
    to: str
    amount_atomic: int
    sender: str = PAYER

    @property
    def amount_usdc(self) -> float:
        return self.amount_atomic / USDC_SCALE


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


def _is_usdc_transfer(
    t: Transfer,
    pay_to: str,
    price_atomic: int,
    payer: Optional[str] = None,
) -> bool:
    """The one rule for "this transfer is THIS payment".

    Four things, not three: the token, the recipient, the amount in atomic
    units, and - when a payer is known - the sender. The sender is the binding
    that makes it *this* payment rather than any payment this seller ever
    received: a transfer to our own payTo, for at least the price, is otherwise
    satisfied by an old confirmed payment of ours.
    """
    if t.token.lower() != USDC.lower():
        return False
    if t.to.lower() != pay_to.lower():
        return False
    if not isinstance(t.amount_atomic, int) or t.amount_atomic < price_atomic:
        return False
    if payer is not None and t.sender.lower() != payer.lower():
        return False
    return True


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
    matching_amount: Optional[int]
    reasons: List[str]


def check_chain(
    chain: SyntheticChain,
    tx: str,
    pay_to: str = PAY_TO,
    price_atomic: int = PRICE_ATOMIC,
    required: int = REQUIRED_CONFIRMATIONS,
    payer: Optional[str] = PAYER,
) -> ChainCheck:
    """Verify the transfer itself: USDC, payTo, amount, sender, depth, status.

    Fail-closed throughout: an unknown transaction, a reverted one, a shallow
    one, one that moved the wrong asset to the wrong address, one that is short
    by a single atomic unit, or one sent by somebody other than the payer the
    proof named is never "verified".
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
    right_shape_wrong_sender = False
    for t in r.transfers:
        if _is_usdc_transfer(t, pay_to, price_atomic, payer):
            matching = t.amount_atomic
            break
        if (payer is not None
                and t.token.lower() == USDC.lower()
                and t.to.lower() == pay_to.lower()
                and isinstance(t.amount_atomic, int)
                and t.amount_atomic >= price_atomic
                and t.sender.lower() != payer.lower()):
            right_shape_wrong_sender = True
    if matching is None:
        reasons.append(
            "payer_mismatch" if right_shape_wrong_sender
            else "no_matching_usdc_transfer")

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
    price_atomic: int,
    required: int,
    adopted: bool,
    payer: Optional[str] = None,
) -> Decision:
    check = check_chain(chain, tx, pay_to, price_atomic, required, payer)

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
    price_atomic: int = PRICE_ATOMIC,
    required: int = REQUIRED_CONFIRMATIONS,
    payer: Optional[str] = PAYER,
) -> Decision:
    """Map one settle response to one verdict.

    `success: true`  -> verify the chain, then allow/deny/hold.
    `settlement_pending` -> adopt the hash, verify the chain, then allow/hold.
    terminal code    -> deny. Never adopted, even with a hash.
    anything else    -> deny. An unknown code is not a payment.

    `payer` is the address that signed the payment. It is passed into the chain
    check so the transfer is bound to THIS payment. Pass `payer=None` only when
    no payer is known - which is exactly when the proof rail has nothing to
    bind to, and the durable one-hash-one-delivery claim is doing the work.
    """
    if not isinstance(resp, dict):
        return Decision(DENY, None, False, ["not_a_dict"])

    tx = resp.get("transaction")
    code = str(resp.get("errorReason") or "").strip()

    if resp.get("success") is True:
        if not _is_tx_hash(tx):
            return Decision(DENY, None, False, ["success_without_transaction"])
        return _decide_on_chain(chain, tx, pay_to, price_atomic, required,
                               adopted=False, payer=payer)

    if code == SETTLEMENT_PENDING_CODE:
        if not _is_tx_hash(tx):
            return Decision(DENY, None, False, ["settlement_pending_without_transaction"])
        return _decide_on_chain(chain, tx, pay_to, price_atomic, required,
                               adopted=True, payer=payer)

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
    amount_atomic: int = PRICE_ATOMIC,
    sender: str = PAYER,
) -> SyntheticChain:
    return SyntheticChain(
        head=head,
        receipts={
            tx: Receipt(
                tx_hash=tx,
                status=status,
                block_number=block,
                transfers=(Transfer(token=token, to=to,
                                    amount_atomic=amount_atomic,
                                    sender=sender),),
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
    d = decide(pending_resp(), chain_with(amount_atomic=10_000))
    assert d.verdict == INDETERMINATE, d.verdict

    # 7. Every check passes -> allow.
    d = decide(pending_resp(), chain_with())
    assert d.verdict == ALLOW, d.verdict


def test_an_old_payment_from_another_payer_is_not_this_payment():
    """Assertion 6: payTo + amount is not enough; the sender must be the payer.

    This is the case a reader cannot see without the binding. A confirmed
    transfer to the seller's own payTo, for at least the price, sent by
    somebody else - an old payment of ours, or a payment for a different order
    - passes every check in assertions 2 and 4 and would be delivered.
    """
    # Same payTo, same token, same amount, status 1, deep. Different sender.
    d = decide(pending_resp(), chain_with(sender=OTHER_PAYER))
    assert d.verdict == INDETERMINATE, d.verdict
    assert "payer_mismatch" in d.reasons, d.reasons
    assert d.verdict != ALLOW, "a payment from another payer was delivered"

    # The same chain, sent by the payer the proof named -> allow.
    d = decide(pending_resp(), chain_with(sender=PAYER))
    assert d.verdict == ALLOW, d.verdict

    # With no payer known the binding cannot be checked, so it is not applied.
    d = decide(pending_resp(), chain_with(sender=OTHER_PAYER), payer=None)
    assert d.verdict == ALLOW, d.verdict


def test_amounts_are_compared_in_atomic_units_not_floats():
    """Assertion 7: the comparison is integer, so precision cannot drift.

    One atomic unit short is underpaid - a float comparison with an epsilon
    calls it paid. And because the amount is an int, a token with 18 decimals
    cannot silently lose precision above 2**53.
    """
    # Exactly the price -> paid.
    d = decide(pending_resp(), chain_with(amount_atomic=PRICE_ATOMIC))
    assert d.verdict == ALLOW, d.verdict

    # One atomic unit short -> not paid. No epsilon tolerance.
    d = decide(pending_resp(), chain_with(amount_atomic=PRICE_ATOMIC - 1))
    assert d.verdict == INDETERMINATE, d.verdict

    # One atomic unit over -> paid.
    d = decide(pending_resp(), chain_with(amount_atomic=PRICE_ATOMIC + 1))
    assert d.verdict == ALLOW, d.verdict

    # An integer above 2**53 is compared exactly, because it is an int.
    big = 2 ** 53 + 3
    t = Transfer(token=USDC, to=PAY_TO, amount_atomic=big, sender=PAYER)
    assert isinstance(t.amount_atomic, int) and t.amount_atomic == big
    assert _is_usdc_transfer(t, PAY_TO, big, PAYER) is True
    assert _is_usdc_transfer(t, PAY_TO, big + 1, PAYER) is False
    # The float view of the same integer is where precision used to be lost.
    assert to_atomic(PRICE) == PRICE_ATOMIC


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
        (chain_with(amount_atomic=1_000), INDETERMINATE),
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
                        {"token": USDC, "to": PAY_TO, "sender": PAYER,
                         "amount_atomic": PRICE_ATOMIC,
                         "amount_usdc": PRICE}
                    ],
                },
            },
            "price_atomic": PRICE_ATOMIC,
            "price_usdc": PRICE,
            "pay_to": PAY_TO,
            "payer": PAYER,
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
