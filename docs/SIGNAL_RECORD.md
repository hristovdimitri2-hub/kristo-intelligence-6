# The signal engine's full record

**Read from the live feed on 2026-11-26 at 05:29Z, not from notes.** Every number
below is reproducible with the two commands in *How to reproduce*. This document
exists because the record is a failure and a failure that is published on purpose
is worth more than one that is discovered.

`GET /public/signals/history` — free, no key, no payment. It has been public since
18.09.2026 and it is the same feed a buyer is pointed at from the paid response.

## The method

- **What is issued.** Two actions only, both bullish: `recommend_accumulate_on_dips`
  and `recommend_small_allocation_only`. Two confidence values in the corpus, 0.45
  and 0.78. There is no short signal and no neutral one in the feed.
- **Frozen rules.** Thresholds, the review schedule, the resolution plan and the
  unresolved reporting were frozen on **2026-09-18** (`frozen_on`) and have not been
  touched since. Checkpoints were declared at **30, 100 and 200** scored signals.
- **Resolution.** Each signal resolves 24 hours after issue against a public price
  source (`coingecko`, `dexscreener`) and is scored against a **per-signal volatility
  threshold** — 1.82% at the tightest, 10.75% at the widest, 2.66% at the median.
- **Outcome rule**, verified against the bytes rather than read from a description:
  a move beyond the threshold **in the recommended direction is a `hit`**, beyond it
  **against the call is a `miss`**, and inside it is a **`flat`**. Checked on all 99
  scored records: **0 violations**.
- **What is not in the feed.** Signals younger than 24 hours stay on the paid route.
  The feed is the proven past.

## The record

| | |
|---|---|
| issued, all time | **272** |
| carried by the public feed | **132** |
| scored | **99** |
| — hits | **1** |
| — misses | **12** |
| — flats | **86** |
| unresolved | **33** |
| reported as `not_scored_non_directional` | **138** |
| **hit rate, as published** | **1.0%** |
| average move on a hit | **+3.862%** |
| average move on a miss | **−5.625%** |
| mean 24h move over the 99 scored | **−0.570%** |
| median 24h move over the 99 scored | **−0.014%** |
| positive / negative moves | **49 / 50** |
| best / worst | **+8.213% / −12.019%** |
| first / last record | 2026-09-21 / 2026-11-25 |

The four published totals do not close exactly: 132 records plus 138 non-directional
is 270 against an `issued` of 272. The feed does not publish where the remaining two
are, so this document does not guess.

**The single hit** is `eth:2026-11-15`, confidence 0.78, +3.8621% against a 3.153%
threshold — a win by 0.7 of a percentage point. The twelve misses run from −3.08% to
−12.02%. The average loss is **larger than the average win**, so the direction of the
error is against the product twice over: it is wrong more often than it is right, and
it is wrong by more.

## By asset and by confidence

| asset | scored | hits | misses | flats | hit rate | unresolved |
|---|---|---|---|---|---|---|
| DEGEN | 63 | 0 | 2 | 61 | 0.0% | 3 |
| ETH | 36 | 1 | 10 | 25 | 2.8% | 30 |

| confidence band | scored | hits | hit rate |
|---|---|---|---|
| 0.4–0.6 | 63 | 0 | 0.0% |
| 0.6–0.8 | 36 | 1 | 2.8% |

Confidence does not sort the outcomes usefully: the higher band produced the only hit
and 10 of the 12 misses. Neither asset carries a hit rate that survives the sample.

## The same question asked without the frozen thresholds

If the volatility thresholds were the thing hiding an edge, removing them would show
it. It does not — counting raw 24h moves at fixed bars, in the recommended direction:

| bar | hits | misses |
|---|---|---|
| 0.5% | 25 | 28 |
| 1.0% | 14 | 21 |
| 2.0% | 8 | 18 |
| 3.0% | 3 | 16 |
| 5.0% | 1 | 7 |

Misses outnumber hits at every bar. At 0.5% the split is 25/28, which is a coin flip
with a fee attached. There is no bar at which this corpus turns into a signal.

## What this proves

1. **The measurement instrument is honest.** The rules were frozen before the results
   were known, the feed is free and public, the failures are published with the wins,
   and the paid route tells the buyer its own record is losing. An operator willing to
   publish this is an operator whose other numbers can be believed.
2. **A commodity feed is not an edge.** Of the seven endpoints sold, six return facts —
   market stats, whale flow, on-chain sales, arbitrage spreads, bot status, seller
   verification — which are either true or false and can be checked by the buyer. One
   sells a prediction, and the prediction scores 1.0%. That is the whole argument for
   leading with the six.

## What this does not prove

- **Not that the model is wrong.** 99 scored observations over two months is a small
  sample in one regime. It proves the product cannot *claim* an edge on this evidence.
- **Not that the direction is wrong.** Every signal is bullish, so there is no control
  group. A one-sided bet can demonstrate exposure, never skill.
- **Not a verdict on the unresolved 33.** They concentrate in ETH (30) and in thinner
  markets, and the feed says so itself. A smaller sample is not a worse model.

## The decision this forces

The prediction is not sold as edge. The product leads with the six endpoints that can
be proven, and the record travels with the product so that a buyer of the seventh sees
the number before acting on it. That is what is implemented today:

- the free feed above, unchanged and open;
- `track_record` inside the paid `/api/v1/signal` response, carrying these figures;
- the sentence *"Its own measured record is public and losing: /public/signals/history
  — read it before acting on a signal."* in the challenge that the CDP Bazaar index
  reads, on both the HTTP row and the MCP row.

## How to reproduce

```sh
curl -s https://kristo-intelligence-api.onrender.com/public/signals/history \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['totals']); print(d['generated_at'])"
```

The first checkpoint was recorded on 2026-11-18 at 1.2% over 84 scored signals. The
next declared checkpoint is **100 scored signals**; this document reports the state at
99 and will be superseded by that checkpoint rather than by an argument.
