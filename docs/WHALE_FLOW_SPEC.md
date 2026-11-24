# WHALE FLOW — Draft specification (07.09, NO implementation)

Decision: **APPROVED** by the owner (07.09) — recorded in PROJECT_STATUS.md.
This document is the draft for review; building starts only after an explicit "go".

## 1. What it is

`GET /api/v1/whaleflow` — a live feed of the large USDC transfers on Base
(whales), for agents that trade/follow the smart-money flow.
The term **whale is #1 out of 1 in PayAPI** (empty niche) — the demand existed,
the product did not. The old "WhaleFlow Radar" SKU was a demo showcase; this is
the real version.

## 2. Source (condition 1: the existing pipe, no new systems)

- Scanner: **the same eth_getLogs mechanism from `competitor_recon` /
  dashboard_store.scan_window** — reads ERC-20 Transfer logs of USDC
  (0x8335…2913) on Base, **WITHOUT a recipient filter** (overall flow), chunked
  + paced, read-only public RPC.
- Filter: `amount ≥ WHALEFLOW_MIN_USDC` (default **$50 000**, env-adjustable).
- Storage: **a new table in the existing `dashboard_state.db`**
  (`whaleflow_events`, dedup by tx+logIndex), synced by the same
  background scan loop (watermark model — deploy-resilient, like sales).
- Window: rolling ~24–48 h (env `WHALEFLOW_WINDOW_HOURS`), cap ~200 events.

## 3. Response format (GET /api/v1/whaleflow)

```json
{
  "ok": true,
  "generated_at": "...",
  "window_hours": 24,
  "min_usdc": 50000,
  "events": [
    {
      "ts": "2026-09-07T14:03:11Z",
      "token": "USDC",
      "amount_usdc": 250000.0,
      "from": "0x…",
      "to": "0x…",
      "from_label": "exchange|wallet|unknown",   // see §4
      "to_label": "wallet|unknown",
      "tx_hash": "0x…",
      "block_number": 51001234
    }
  ],
  "count": 42
}
```

## 4. Labels (honest, no invented data)

- **known-set labels:** the addresses we know (chet_payapi_verification,
  market_sampler/crawler, our hot wallet/receiver) → "market_infra" /
  "kristo_internal".
- Everything else: **a raw address, truncated** (`0x1234…abcd`), label
  "unknown".
- ENS/Exchange tagging = a FUTURE add-on (not in v1 — zero invention).

## 5. Price

**$0.003** — like signal (our most-tested price; 5 successful canary
payments on that tier). Alternative $0.005 (stats tier) — the owner decides.
Recommendation: **$0.003**.

## 6. What it needs for a canary test (condition 2)

1. Code: route + scan integration + table (1 work session, ~30–60 min).
2. `X402_PRICE_MAP["/api/v1/whaleflow"] = 0.003` (one line) — only then does
   the endpoint become payable.
3. Tests: format/dedup/watermark/threshold (unit) + a live freshness test
   (the newest event ≤ 15 min old).
4. Canary: an invitation to Chet for a paid canary (the same protocol as
   signal — he has paid 4 times so far; the "launch signal" attribute is
   preserved).
5. Only AFTER a successful canary → **only then** entry into x402 discovery /
   /api/v1/agents / dashboard "Real routes" / manifest (condition 4).

## 7. Safeguards (immutable)

- payTo/the existing 5 routes — untouched.
- No change to the x402 logic — the new route uses the same paywall.
- It does not enter catalogs/manifests before canary proof.
- One new product per wave (condition 3) — after whale flow, the next product
  waits for a new decision.

## 8. Risks / notes

- A general scan of the USDC transfers on Base is heavier than the
  receiver-filtered one — that is why the scan has a watermark + cap and cuts
  by threshold before writing.
- RPC rate limits on the public endpoint: the same chunk/pause settings as
  competitor_recon (proven in production).
- If eth_getLogs for the overall flow turns out to be too heavy: fallback =
  a shorter window (6 h) or a higher threshold ($100k) — decided at build
  time, does NOT block the design.
