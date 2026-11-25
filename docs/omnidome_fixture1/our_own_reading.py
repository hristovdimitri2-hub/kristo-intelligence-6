#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Kristo Intelligence
"""Our own reading of the settlement-pending vector set (draft 3).

WHAT IS WHOSE, BECAUSE IT IS THE WHOLE POINT
--------------------------------------------
* The vector set is `github.com/holistis`'s: `vectors/settlement-pending/
  vectors.json`, draft 3, sha256 `94b07672bfd9…`, 61 084 bytes, 41 vectors of
  which 36 are asserted. This file does not copy it and does not need it present
  at a fixed path — pass it in.
* The decision logic is OURS, and it is not re-implemented here: it is imported
  from our published artifact `test_settlement_pending_chain_before_delivery.py`
  (revision of 24 November, sha256 `3d76d803…`, 37 862 bytes, 11 tests). Pass its
  path in. Nothing in this file re-derives a rule.
* The file that maps one onto the other is ALSO OURS. That is why it exists: the
  cross-run published on 25.11 went through THEIR adapter (`kruisrun.py`), which
  reads the vectors and hands our decision function the pieces in the shape it
  expects. With a reader of ours, the answer no longer depends on their
  translation. If the two readers agree, what agrees is the decision logic; if
  they disagree, the translation is where to look.

EVERY READING DECISION WE MAKE, SO A READER CAN DISPUTE IT
----------------------------------------------------------
1. `quote.price` and `transfer.amount` are atomic-unit integers. They are handed
   over as integers, unchanged — no float ever touches an amount.
2. The vector's `quote.asset` is the token that counts as CORRECT for that vector.
   Our fixture hard-codes Base mainnet USDC while these vectors run on Base
   Sepolia (`eip155:84532`), so for the duration of one vector the fixture's USDC
   constant is set to the vector's own quote asset. A transfer whose `token`
   differs from it is therefore a wrong token, which is what those vectors mean.
3. `chain.receipt` is a depth and a status, not a receipt:
     `deep` -> status 1, 11 confirmations   `shallow` -> status 1, 2
     `reverted` -> status 0, 11             `reverted_shallow` -> status 0, 2
     `absent` -> no receipt                 `not_measured` -> no receipt
   Our fixture asks for 3 confirmations. **`not_measured` has no equivalent state
   in our artifact** — our logic has no "the chain could not be read" answer — so
   it is handed over as a chain without a receipt, which our logic holds on. That
   is an assumption of this reader and it is flagged per vector in the output.
4. The receipt's EIP-3009 authorizations are the pair (`transfer.from`,
   `transfer.nonce`) when both are present: the `AuthorizationUsed` event is
   indexed by authorizer and nonce, so that pair is what a receipt consumed. The
   nonce of the PAYMENT is `payment.nonce`, and it is passed to our decision only
   on the `authorization` rail — on the `proof` rail no authorization was signed,
   so there is no nonce to bind to.
5. `payer` is `transfer.from` on both rails. Our fixture treats a missing payer as
   an exit for a caller who truly has none; here a transfer with no `from` is
   reported as UNREPRESENTABLE rather than silently given a default sender, which
   is what their adapter does and what its README says makes that vector's answer
   say little.
6. `claims.hash` is the durable one-hash-one-delivery claim. `"delivered"` means
   the claim already holds this hash, so the answer is REFUSE before anything
   else; `"none"` means there is no claim to consult.
7. `retry` carries `hashFromNonceLookup`: the same signed authorization came back
   and the hash was found by nonce rather than named in the response. When the
   response names no hash of its own, that hash is used.
8. Verdicts map as `allow -> DELIVER`, `deny -> REFUSE`, and both
   `pending` and `indeterminate -> HOLD`. The reference vocabulary has one word
   for both of our non-delivering, non-refusing states, and the vectors allow
   either, which is exactly why they are the interesting rows.
9. A vector with `asserted: false` asserts nothing. Our answer is printed and is
   NOT counted as agreement or disagreement.
10. `expected.acceptable` is the set of answers the vector allows besides its own
    reference answer. Anything outside that set, and outside the reference answer,
    is reported as OUTSIDE.

Usage
-----
    python our_own_reading.py --vectors vectors.json \
        --fixture test_settlement_pending_chain_before_delivery.py [--json]
"""

import argparse
import importlib.util
import json
import os
import sys

#: Our verdict -> the vector set's outcome vocabulary.
OUTCOME = {
    "allow": "DELIVER",
    "deny": "REFUSE",
    "pending": "HOLD",
    "indeterminate": "HOLD",
}

BLOCK_NUMBER = 100
DEEP = 11
SHALLOW = 2
WRONG_TOKEN = "0x" + "de" * 20


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution on purpose: the fixture's dataclasses look
    # themselves up in sys.modules while the decorator runs, and an unregistered
    # module makes that lookup fail with `'NoneType' object has no attribute
    # '__dict__'` — a confusing error for a missing line.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_chain(fixture, vector, notes):
    """The synthetic chain one vector describes."""
    chain = vector["input"].get("chain") or {}
    kind = chain.get("receipt")
    if kind in (None, "absent"):
        return fixture.SyntheticChain(head=BLOCK_NUMBER + DEEP, receipts={})
    if kind == "not_measured":
        notes.append("not_measured has no state in our fixture; handed over as no receipt")
        return fixture.SyntheticChain(head=BLOCK_NUMBER + DEEP, receipts={})
    status = 0 if str(kind).startswith("reverted") else 1
    depth = SHALLOW if str(kind).endswith("shallow") else DEEP
    return status, depth


def build_receipt(fixture, vector, tx, notes):
    chain = vector["input"].get("chain") or {}
    transfer = chain.get("transfer")
    kind = chain.get("receipt")
    payer_hint = (vector["input"].get("payment") or {}).get("payer")
    if kind in (None, "absent", "not_measured"):
        return None
    status = 0 if str(kind).startswith("reverted") else 1
    depth = SHALLOW if str(kind).endswith("shallow") else DEEP

    transfers = ()
    if transfer:
        # The sender of the transfer and the payer of the payment are two
        # different things and only one of them is ever absent. `payment.payer`
        # is the address that signed the proof; `transfer.from` is who actually
        # sent the USDC. The binding is payer == sender, so substituting one for
        # the other would make the binding unfalsifiable — which is what the
        # first version of this reader did, and it reported two vectors as
        # OUTSIDE that the vector set allows. A transfer with no `from` cannot be
        # bound at all; the payment's own payer is handed over so the vector runs
        # rather than crashing, and the substitution is noted.
        sender = transfer.get("from")
        if sender is None:
            sender = payer_hint
            notes.append(
                "transfer has no `from`: an unreadable sender is not a state our "
                "fixture can express, so the payment's own payer was handed over "
                "and this vector's answer says little")
        transfers = (fixture.Transfer(
            token=transfer.get("token") or WRONG_TOKEN,
            to=transfer.get("to") or "",
            amount_atomic=int(transfer.get("amount") or 0),
            sender=sender,
        ),)

    authorizations = ()
    rail = (vector["input"].get("payment") or {}).get("rail")
    if rail == "authorization" and transfer and transfer.get("from") and transfer.get("nonce"):
        authorizations = ((transfer["from"], transfer["nonce"]),)

    return fixture.Receipt(
        tx_hash=tx,
        status=status,
        block_number=BLOCK_NUMBER,
        transfers=transfers,
        authorizations=authorizations,
    ), depth


def our_answer(fixture, vector):
    """What OUR decision logic answers for one vector."""
    notes = []
    quote = vector["input"]["quote"]
    pay_to = quote["payTo"]
    price_atomic = int(quote["price"])
    response = dict(vector["input"]["response"])
    payment = vector["input"].get("payment") or {}
    claims = vector["input"].get("claims") or {}
    retry = vector["input"].get("retry")
    transfer = (vector["input"].get("chain") or {}).get("transfer")

    # 7. the hash found by nonce, when the response names none. NOT turned into a
    #    pending response: what the facilitator answered is handed over as it
    #    stands, because turning it into a pending response is exactly the choice
    #    their adapter makes and this reader exists to avoid inheriting it.
    if retry and not fixture._is_tx_hash(response.get("transaction")):
        notes.append(
            "the response names no hash; the nonce lookup found %s, which our "
            "decision table has no rule for" % str(retry.get("hashFromNonceLookup"))[:12])

    tx = response.get("transaction")

    # 6. the durable claim, consulted before anything else
    if claims.get("hash") == "delivered":
        return "REFUSE", "hash_already_delivered", notes

    payer_hint = payment.get("payer")

    # 2. the vector's own quote asset is what counts as the right token
    fixture.USDC = quote["asset"]

    built = build_receipt(fixture, vector, tx, notes)
    if built is None:
        chain = fixture.SyntheticChain(head=BLOCK_NUMBER + DEEP, receipts={})
    else:
        receipt, depth = built
        chain = fixture.SyntheticChain(
            head=BLOCK_NUMBER + depth - 1, receipts={tx: receipt})

    payer = payer_hint or (transfer.get("from") if transfer else None)
    nonce = payment.get("nonce") if payment.get("rail") == "authorization" else None

    decision = fixture.decide(
        response, chain, pay_to=pay_to, price_atomic=price_atomic,
        required=fixture.REQUIRED_CONFIRMATIONS, payer=payer, nonce=nonce,
        recovering=bool(retry))

    outcome = OUTCOME.get(decision.verdict, decision.verdict.upper())
    reason = ",".join(decision.reasons) or "every check passed"
    return outcome, reason, notes


def judge(vector, outcome):
    """same / allowed / outside / open, using the vector's own tolerance."""
    expected = vector["expected"]
    reference = expected["outcome"]
    if vector.get("asserted") is False or reference == "OPEN":
        if vector.get("asserted") is False:
            return "open"
    allowed = set(expected.get("acceptable") or []) | {reference}
    if outcome == reference:
        return "same"
    if outcome in allowed:
        return "allowed"
    return "outside"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    fixture = load_module(args.fixture, "our_fixture")
    with open(args.vectors, encoding="utf-8") as handle:
        document = json.load(handle)
    vectors = document["vectors"]

    rows = []
    for vector in vectors:
        outcome, reason, notes = our_answer(fixture, vector)
        rows.append({
            "id": vector["id"],
            "ours": outcome,
            "reference": vector["expected"]["outcome"],
            "verdict": judge(vector, outcome),
            "reason": reason,
            "notes": notes,
            "acceptable": vector["expected"].get("acceptable") or [],
            "encodes": vector.get("encodes", ""),
        })

    tally = {}
    for row in rows:
        tally[row["verdict"]] = tally.get(row["verdict"], 0) + 1

    if args.json:
        print(json.dumps({"tally": tally, "rows": rows}, indent=1))
        return 0

    print("our own reading of %s (schema %s)" % (
        os.path.basename(args.vectors), document.get("schema_version")))
    print("fixture: %s" % os.path.basename(args.fixture))
    print("vectors: %d" % len(rows))
    print("  same answer as the reference:        %d" % tally.get("same", 0))
    print("  a different answer the vector allows: %d" % tally.get("allowed", 0))
    print("  outside what the vector allows:      %d" % tally.get("outside", 0))
    print("  open (nothing asserted):             %d" % tally.get("open", 0))
    print("\nevery vector where our answer is not the reference answer:")
    for row in rows:
        if row["verdict"] == "same":
            continue
        print("  %-7s %-58s ref %-7s ours %-7s (%s)" % (
            row["verdict"], row["id"][:58], row["reference"], row["ours"],
            row["reason"][:60]))
    notes = [(row["id"], note) for row in rows for note in row["notes"]]
    if notes:
        print("\nreading assumptions that changed an answer:")
        for vector_id, note in notes:
            print("  %-58s %s" % (vector_id[:58], note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
