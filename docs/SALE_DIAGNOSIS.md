# SALE DIAGNOSIS — the first external payment (06.09)

## VERDICT: **C — LAUNCH SIGNAL. First external payer.** 🎉

A single payment of **0.003 USDC** (the exact price of our signal route) at
**06:41 UTC on 06.09.2026** — from a wallet that is NEITHER Chet NOR the known
sampler/crawler.

## 1. The monitor: `python scripts/listing_monitor.py` printed:

```
*** LAUNCH SIGNAL: external human/unknown payer detected ***
    external payers: 1  | payments: 1  | total 0.003 USDC
    0x4dB7AAFbe797a39Cd6Cc4E7aa64d970F7F6E02B7  1 txs, 0.003 USDC (avg 0.003)
```

The classification works exactly as designed: Chet's canaries
(`chet_payapi_verification`) and the known sampler/crawler wallets are excluded
→ everything else = launch signal.

## 2. The exact transaction (on-chain, 48h scan)

| Field | Value |
|---|---|
| Amount | **0.003 USDC** (= the price of GET /api/v1/signal) |
| From | wallet starting with `0x4dB7AAFb…E02B7` |
| Tx hash | `0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3` |
| Block | 50943758 |
| Time | **2026-09-06 06:41:03 UTC** |

It is not Chet (`0x7E6b…`), not the sampler `0xC59E…`, not the crawler `0x6777…`.

## 3. Fingerprint of the payer (30-day outgoing USDC scan)

| Metric | Value | Taxonomy |
|---|---|---|
| Distinct recipients | **100** | ~23/week → below crawler (50), above loop (≤10) |
| Total txs | 145 | moderate cadence |
| Total amount | 1.67 USDC | micro-range |
| ENS | none | anonymous |
| **PayAPI house treasury** | **18 tx, $0.06** | its source INCLUDES PayAPI listings |

**Profile: a moderate multi-API operator** — an agent that pays ~100 x402
endpoints a month, including PayAPI's house listings. It is NOT the crawler (145
tx/30d vs 150–390/week for the samplers). And today it **included us** in its
cycle — our first payment from the ecosystem.

## 4. Our logs (dashboard-stats, read-only)

- The sale is **recorded and confirmed** in `history` (status: confirmed, block
  50943758, tx hash matches) — two records for the same tx = the known cosmetic
  double-record (settle+monitor), not two payments
- The endpoint requested: **$0.003 = GET /api/v1/signal** (only it costs that
  much)
- Today (06.09): **107 requests, 2 recorded sales ($0.006)**; yesterday: 152
  requests
- User-Agent breakdown: it is NOT exposed publicly in dashboard-stats — it is
  logged internally (`_live_request_log`), but requires admin access to inspect

## 5. Band check: still unscored
`/agent/get` → reliability: score=null, band=unscored, computed_at=null. Chet's
compute has not been run for us (the title has not been changed either). The
payment from 0x4dB7 is independent of that.

## What follows according to the verdict
The **"number" email to Chet** (the thread's grammar — one line, zero questions):

> Subject: first external payer
>
> Hi Chet — first external payer landed on our listing: 0.003 USDC via x402,
> signal route, settled on-chain this morning. Since you asked to know when
> the route gets used — this is that number.
>
> — Dimitri

Plus: **watch 0x4dB7** — if it returns (a 2nd payment), that is an operator →
operator deal conversation ($0.01–0.05/call tier according to NEW_OPERATOR_ANALYSIS).
The monitor already classifies it automatically.
