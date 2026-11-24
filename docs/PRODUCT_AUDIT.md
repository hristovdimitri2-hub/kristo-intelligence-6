# AUDIT: Product and competitor (07.09, read-only + tests)

Zero code changes. payTo/endpoint untouched. 164/164 PASS.

## PART A — The freshness of the bread

### A1. What we actually sell: two product categories

**Category 1 — THE REAL STUFF (5 paid x402 endpoints + MCP):**
`/api/stats`, `/api/sales`, `/api/bot-status`, `/api/arb/opportunities`,
`/api/v1/signal` + MCP (SSE + Streamable HTTP, 3 tools). This is where the real
data lives.

**Category 2 — the 8 catalog SKUs** (`integrations/catalog_store.py`):
whaleflow-radar, cross-venue-signal-divergence, token-launch-rug-risk-scanner,
defi-yield-risk-optimizer, gas-route-optimizer, ai-sentiment-narrative-pulse,
smart-contract-security-triage, signal-to-channel-publisher.

### A2. 🔴 THE MAIN FINDING: the 8 SKUs = a shop window with no product behind it

**Evidence (code):**
- `main.py:2440` — `_run_catalog_agent_demo(agent, user_input)` runs
  **UNCONDITIONALLY**, even when the client has paid and submitted a valid
  entitlement token (lines 2437–2440: the token is verified, but the result is
  still the demo; only the label becomes "active_entitlement").
- `main.py:1465–1492` — the demo returns a hash of the input + static steps:
  "Demo workflow completed… does not claim a live trading recommendation",
  `upgrade_required_for_live_access: true`.
- `main.py:2547–2572` — `/access` returns ONLY a signed token (entitlement), not
  live data. There is no other execution path for the SKUs.

**Verdict for the 8 SKUs: DEAD as a product.** Live as a source — not a single
one. A client who has paid $12–19 (Stripe) for any of them gets the same demo as
a free call. For the same money, our x402 endpoints buy real data.

### A3. Data source + last GENUINELY new signal — by real products

| Product | Source | Last GENUINELY new signal | Verdict |
|---|---|---|---|
| **/api/v1/signal** ($0.003) | CoinGecko (every 5 min, agent loop) + DeFiSignalGenerator (Base44-oriented) | Chet's 4th canary: price within 0.13% of CoinGecko, WITHOUT a stale note (05.09); the 0x4dB7 purchase (06.09) — signal route | **ALIVE** |
| **/api/stats** ($0.005) | CoinGecko + DEXScreener + Fear&Greed (cache TTL 15 min) | live market_data: CoinGecko age 290 sec, AERO $0.5667 +4.57%, F&G 71 "Greed" (07.09) | **ALIVE** |
| **/api/arb/opportunities** ($0.005) | DEXScreener cross-DEX scanner (scan every 60 sec, min_spread filter) | actively scanning (ARB_SCAN_INTERVAL=60s); bodies are not visible without payment | **ALIVE** (modestly — Base spreads are thin) |
| **/api/sales** ($0.05) | Real on-chain USDC Transfer scan (hard determinism) | 5 transfers in total, the last on 06.09 | **ALIVE** (albeit with a sparse history) |
| **/api/bot-status** ($0.005) | Internal bot state (webhook-only) | heartbeat/uptime — continuous | **ALIVE**, but it is statistics, not intelligence |
| **the 8 SKUs** | NO source — demo adapter | there is never a live signal | **DEAD** |

### A4. Route tests (07.09, live)

| Test | Result | Match with README |
|---|---|---|
| POST playground whaleflow-radar (free) | 200: `mode: playground_demo`, "Demo workflow completed… does not claim a live trading recommendation" | ❌ README/catalog describe "signals with confidence" — the actual response is a demo without data |
| POST playground gas-route-optimizer | 200: the same demo | ❌ the same mismatch |
| POST playground ai-sentiment-narrative-pulse | 200: the same demo | ❌ the same mismatch |
| GET /api/stats | 402 (strict x402 — KRISTO_FREE_TIER_LIMIT=0 on Render) | ✅ the semantics are correct |
| GET /api/v1/signal | 402, amount: 0.003 | ✅ the price matches |

### A5. FORENSICS: what 0x4dB7 received for $0.003 (06.09 06:41:03 UTC)

**What we know for sure:**
- Which endpoint: **GET /api/v1/signal** — the only one at $0.003 (SALE_DIAGNOSIS).
- Response format: {token, action, confidence, price_usd, reasoning, note}
  — verified 4 times by Chet's paid canaries (numeric price_usd,
  reasoning with a primary driver, no stale penalty after the fix).
- Freshness at the moment of purchase: the agent loop refreshes every 5 min from
  CoinGecko; on 06.09 the loop was active (the sale is recorded in the dashboard).
- The payer: a moderate multi-API operator (100 payTo/30d, 145 tx, $1.67) — knows
  what he is buying, not a random fish.

**What is lost (cannot be recovered):**
- **The exact body** of the response (which token, which price, which reasoning)
  — it was in RAM `_latest_signals`, zeroed by deploys during the day; response
  bodies are not logged. If 0x4dB7 comes back, next time we will be able to log
  bodies (by decision — PII-safe: token/price/confidence without anyone).

**Verdict:** the purchased product was LIVE and verifiable; the exact values are
irrecoverable, but the structure and the freshness are proven by the canaries.

## PART B — The neighbours' bread

### B1. Test purchases: BLOCKED — the hot wallet is empty

| Hot wallet `0x9c1eb9…750dd` balance (checked on-chain 07.09) | Value |
|---|---|
| ETH (gas on Base) | **0.000000** |
| USDC | **0.000000** |

For 1-2 purchases (Currency API $0.001 × 2 or loopA $0.021) we need:
**≥ $0.05 USDC + ~0.0001 ETH for gas** (~$0.03) in the hot wallet. After funding,
the recipe: GET → 402 → payment (EIP-3009 PAYMENT-SIGNATURE or tx-hash rail
depending on the challenge) → retry → record the tx. The script is 10 lines with
our web3 — waiting for a funded wallet. **Nothing was bought today.**

### B2. Neighbour #1 (studied without payment, read-only): Currency & Crypto API

| Field | Value |
|---|---|
| Who it is | **HOUSE listing** — provider_name: "PayAPI Market" |
| Price | **$0.001 flat** (5 endpoints: /rates/latest, /rates/convert, /rates/historical, /crypto/price, /crypto/prices) |
| Sources (from the free /health!) | fiat = Frankfurter (ECB), **crypto = CoinGecko — THE SAME source as ours** |
| Cache | 1h fiat / 30s crypto (their personal key) |
| Band | **established / score 57.8** — LOWER than our 69.7 |
| MCP | has /mcp/sse |
| Neighbour #2 | "Yahoo Finance Stock Data & Historical Prices API" — $0.01 (not studied deeply) |
| **loopA at $0.021** | ❌ **NOT FOUND** in PayAPI (0 results for "loopa"/"loop") — the listing does not exist or is under another name |

### B3. Comparison table (promises + verifiable facts, not measured bodies)

| Criterion | Us (Kristo Intelligence) | Currency & Crypto API (house) |
|---|---|---|
| Price per request | $0.003–0.05 | **$0.001** |
| Data about the money | CoinGecko + DEXScreener + F&G + **a real on-chain sales feed** | CoinGecko (crypto) + ECB/Frankfurter (fiat) |
| Breadth | 5 x402 endpoints + 3 MCP tools + 8 catalog SKUs (demo) | 5 endpoints, narrow focus (currencies/prices) |
| Unique | **on-chain verified sales + launch-signal taxonomy** (nobody else on the market has this) | historical fiat back to 1999 |
| Band / score | **established / 69.7** | established / 57.8 |
| Real paying clients | **1 (0x4dB7, 06.09)** | unknown (18 house tx do not mean our clients) |
| MCP transport | SSE + Streamable HTTP | SSE |

**Conclusion without a purchase:** the neighbour is a clean wrap of public APIs
(CoinGecko/ECB) with a lower score than ours. Our micro-economy is NOT worse:
for 5× the price we sell 5× broader logic + something they do not have —
on-chain provability. But today's finding (the 8 SKU demo) leaves us with the
smaller "real" catalog than their 5/5.

## PART C — Inventory of the 4 pillars

| Pillar | Evidence TODAY | What is missing | Strongest | Weakest |
|---|---|---|---|---|
| **Specialty** (unique product) | on-chain sales feed + launch-signal taxonomy (the only ones on the market); signals with reasoning (verified 4×) | the 8 SKUs have no real bread behind them — the shop window promises more than the product | /api/v1/signal + on-chain feed | the 8 SKUs (DEAD) |
| **Micro-economy** (prices/clients) | prices $0.003–0.05 + VIP; 1 real external payer; band 69.7 | a 2nd payment from 0x4dB7 (operator deal trigger); ZERO repeat clients yet | price discrimination (5 min loop → always fresh) | a single client in history |
| **Provability** (on-chain/verifiable) | 5 transfers, 4 canary verifications, tx hashes public; cache freshness public (age 290s); band 69.7 public | logging the bodies of paid responses (forensics impossible today); the manual timeout band recompute | everything connected to the Chet/PayAPI chain | proof of REAL user value (we have no feedback from 0x4dB7) |
| **Speed** (freshness/latency) | CoinGecko cache ≤15 min (observed: 290s), arb scan 60s, agent loop 5 min, MCP SSE + Streamable | latency measurement of paid requests (the last one we know from a canary: under the 60s timeout) | the 5 min agent loop is fresh enough for signals | the 8 SKUs: zero speed (they are not alive) |

**Final verdict of the audit:** the bread of the 5 real routes is ALIVE and
provable; the shop window of 8 SKUs is DEAD and is our biggest reputational risk
(a client who paid for a SKU gets a demo). The competition at the house level is
weaker than us in score and in depth, but cheaper and simpler for the agent. The
test purchases are waiting for the hot wallet to be funded (~$0.08).
