# Honest revenue — what our own numbers actually contain

Written 2026-11-19, before anyone else asked. The x402 market is starting to
police this itself: the term in circulation is "self-dealing", and a seller
publishing `/.well-known/honest-revenue.json` is the accepted answer. This is
ours, in prose, with the raw split.

## The split

The dashboard reports 171 settlements and $1.883 USDC. That figure is real but
it is not demand. Broken down by who paid:

| class | settlements | USDC | share of USDC | what it is |
|---|---:|---:|---:|---|
| `own_key` | 122 | 1.685 | 89.5% | our own demo key, paying our own routes |
| `canary` | 17 | 0.067 | 3.6% | our scheduled self-tests |
| `sampler` | 20 | 0.077 | 4.1% | the market sampler robot |
| **`external`** | **12** | **0.054** | **2.9%** | **real customers** |

**89.5% of the dollar volume is our own money.** 12 of 171 settlements came from
someone who is not us. The external 12 came from 9 wallets, one of which is the
auditor we paid (Ernest, `0xEe523a…`), so the real external count is 8 wallets
and $0.041.

## The label problem

The dashboard calls that block `all_time`. It is not all time. The store it
reads was rebuilt on 2026-11-09 and reports `days_live: 10`, `first_sale:
2026-11-09T19:25:45Z`. The product has been selling since September — there are
external payments from 6 September in the wider record that this store does not
contain.

So `all_time` means "since 9 November". Any figure quoted from it should say so.

## What is safe to say in public

- "171 settlements since 9 November, 12 of them from external buyers" — true.
- "171 settlements from 9 paying customers" — **false**, it mixes scopes. The
  count includes our own key and canaries; the payer count does not.
- "We have 12 external settlements worth $0.054" — true.
- "8 real external buyers, 1 repeat" — true, after removing the auditor.

## How to verify

`GET /api/dashboard/data` → `sections.onchain.by_class` carries the four classes
and their totals. The classification is done at write time by the sales ledger,
not by this document. `sections.summary.all_time` is the headline block and is
the one that needs the caveat.

## What follows

Nothing here is a criticism of the ledger — it classifies correctly. The problem
is the headline: `summary.all_time` reports a count that includes self-payments
next to a payer count that does not. Anyone reading only the summary gets a
number 14 times larger than the demand behind it.

The fix is either to rename the block or to split it. Until then, quote the
`by_class` numbers, not the summary.
