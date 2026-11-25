# Our own reading of the draft-3 vector set — and the defect it found in our own artifact

**Date:** 25 November 2026.
**Vector set:** `94b07672bfd9be9335d52ac3bedd4f59bc663b30b2978d32f4bfcb1d83c1bbfe` —
`vectors/settlement-pending/vectors.json`, draft 3, 61 084 bytes, 41 vectors of
which 36 are asserted, from
[`holistis/agent-receipt-verify`](https://github.com/holistis/agent-receipt-verify).
**Our logic:** `test_settlement_pending_chain_before_delivery.py`, revision of
25 November, SHA-256
`ccdfea67502fd2204502dfe72b4bc5e83ed8ece67b1ed19c690d580e91d0d666`, 46 890 bytes,
13 tests.
**Our reader:** `our_own_reading.py`, in this gist, stdlib only.

```
python our_own_reading.py --vectors vectors.json \
    --fixture test_settlement_pending_chain_before_delivery.py
```

## The result

```
same answer as the reference:          22
a different answer the vector allows:  14
outside what the vector allows:         0
open (nothing asserted):                5
```

That matches the tally their adapter produces for the same pair. The point of a
second reader is that it matches **without their translation** — the answer now
depends on the decision logic rather than on one mapping of the vectors onto it.

## What the second reader caught, which the first could not

**Our first run of our own reader gave 19 / 14 / 3 / 5.** Three vectors came out
OUTSIDE what the set allows — our logic answered REFUSE where the set says
DELIVER, HOLD and HOLD:

| vector | reference | our v4 | why |
|---|---|---|---|
| `retry-adopted-by-nonce-deliver` | DELIVER | REFUSE | `terminal:invalid_transaction_state` |
| `retry-adopted-by-nonce-hold` | HOLD | REFUSE | same |
| `retry-chain-not-measured-hold` | HOLD | REFUSE | same |

All three are one case, and it is a case that matters: the facilitator answers
`success: false, errorReason: "invalid_transaction_state"`, *"authorization already
used"*, with **no hash**, because the buyer has re-presented the **same signed
authorization** after a lost response. Our artifact treated that code as terminal
and refused — which tells a buyer their payment failed when in fact it landed.

**Production has never done that.** `_find_settlement_by_nonce` (`main.py:3671`)
searches the chain for the transaction that consumed `(payer, nonce)` and then
requires the same receipt to carry the transfer to our `payTo`. The fixture did not
carry that rule, and the adapter had been hiding the gap by synthesising a *pending*
response for exactly those vectors — a translation choice that is reasonable in an
adapter and invisible in its output. That is the whole argument for a second reader,
and it is why this one was written.

## The fix, and the distinction that makes it safe

The rule now lives in the artifact (v5), and it is in the caller's hands on purpose:
`decide(..., recovering=True)` is passed by a caller that **knows** the same
authorization has come back, because it is the caller that performed the lookup.

- with the marker: an "already used" code asks the chain which receipt consumed
  `(payer, nonce)`. A receipt that did **is** this payment and the ordinary rules
  decide. Nothing found is a **HOLD, never a refusal** — the nonce tells us the
  authorization was spent, and refusing would assert more than we know.
- without the marker: the code stays terminal. The set's own
  `message-says-pending-code-does-not` vector is the *same code* with no retry, and
  it requires REFUSE. One flag separates the two, and both are pinned by tests.

Two tests were added (11 → 13), including the counter-case above, so the pair cannot
drift apart again.

## What this does not show

- **It is not independent of us.** The vectors are theirs; the decision logic is
  ours; this reader is ours. What it removes is one *translation*, not the
  author's stake.
- It is one dated revision of the artifact and one dated revision of the set.
- **Only one state of the reader was ever published.** Every gist revision that
  carries `our_own_reading.py` carries the same bytes (SHA-256
  `8980ceaab81d78e0d9be519f31dbb093da9247abaec72a9d84b9fb0aa3a6e8a9`, 13 234
  bytes), and those bytes cannot be run against v4 of the artifact at all: v5
  added the `recovering` marker and v4's `decide()` does not take it, so that run
  ends in `TypeError: decide() got an unexpected keyword argument 'recovering'`.
  The 19 / 14 / 3 / 5 above is therefore a number we report, not one a reader can
  reproduce from published bytes.
- **An earlier state of the reader was wrong as well, before anything was
  published.** It read the transfer's `from` instead of the payment's own payer,
  which made the binding unfalsifiable and answered **5** outside. The outside
  count moved 5 → 3 → 0 across our own fixes; 0 is the published pair's number.
- The reader makes ten reading decisions (listed at the top of the file, numbered,
  including the two where our artifact has no equivalent state at all:
  `not_measured` chains and transfers with no readable `from`). A reader who
  disagrees with one of them should say so — each is named so it can be disputed
  rather than discovered.
- The three divergences above are reported as **our** defect, not the set's. The
  set was right.
