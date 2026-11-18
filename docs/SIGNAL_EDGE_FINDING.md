# The signal has no measured edge

Measured 2026-11-18 from the public feed, no changes to production.

## What was measured

`GET /public/signals/history` — the free, public track record the product has
been publishing since 18.09. It returns 116 records; 84 are scored (outcome
`hit`, `miss` or `flat`) with both a signed 24h move and the per-signal
volatility threshold.

Every signal in the sample is bullish. The two actions present are
`recommend_accumulate_on_dips` and `recommend_small_allocation_only`; there is
no short signal and no neutral one. So the hit rate is, in effect, "how often
did the price go up".

## The numbers

    scored signals              84
    positive 24h moves          44  (52.4%)
    mean 24h move            -0.56%
    median 24h move          +0.03%
    best / worst        +3.86% / -12.02%

Hit rate at a fixed bar, same bullish direction:

    bar 0.5%   hit 20 / miss 20   23.8%
    bar 1.0%   hit 10 / miss 14   11.9%
    bar 2.0%   hit  5 / miss 14    6.0%
    bar 3.0%   hit  1 / miss 13    1.2%
    bar 5.0%   hit  0 / miss  5    0.0%

Published headline, by the frozen rules, at the reached checkpoint: **1.2%**.

## What this means

The published 1.2% is not an artefact of the threshold. At every bar tested,
misses outnumber hits. Lowering the bar to 1% gives 11.9% — still worse than a
coin flip once misses are counted. Lowering it to 0.5% gives 20 hits and 20
misses, exactly even.

A 52.4% positive rate is a coin flip. A mean 24h move of -0.56% means "buy"
lost money over the sample. The signal is not predictive on this evidence.

## What this does NOT mean

It does not prove the underlying model is wrong — 84 observations over about
two months is a small sample, and it covers one regime. It does prove that the
product cannot currently claim an edge, and that the public feed already says
so to anyone who reads it.

The measurement also cannot separate "no edge" from "wrong direction" — with
only bullish signals there is no control group. A one-sided bet cannot
demonstrate skill, only exposure.

## The decision this forces

The API sells seven endpoints. Six return facts: market stats, whale flow,
on-chain sales, arbitrage spreads, bot status, seller verification. Those are
either true or false and can be checked by the buyer.

One endpoint sells a prediction. That is the one that scores 1.2%.

Either the prediction is fixed to show a real edge on a proper sample, or the
product leads with the six that can be proven. Selling the unproven one first
is what makes the whole API look untrustworthy.

## Status

Nothing changed in production. The feed is honest and stays as it is. This
document exists so the number is not rediscovered as a surprise later.
