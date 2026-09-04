# RECON NOTES — first findings (04.09)

## Target 1: „Currency & Crypto API" (PayAPI first-party, $0.001/call)
payTo `0xFFc458dB291b4ABcE020fE3de4f91F2770E537b1` (obtained free via 402 challenge).
7d window: **159 txs / 0.287 USDC / 15 payers / avg $0.0018 / 11 repeat** → ~$1.2/month.
Raw report: `_recon_currency_api_7d.json`.

## Payer identity: 0/15 ENS-resolved (anonymous bots) — `payer_lookup.py`
So no personal outreach channel by name. BUT outgoing-transfer analysis of the
top payers (via `topics[from]=payer` scan) reveals who they actually are:

| Payer | Behavior | Verdict |
|---|---|---|
| `0xC59E…98DC` (48 tx) | paid **158 different receivers** in 7d | **ecosystem crawler/router** — probes every listing (x402scan-style verification or router) |
| `0x5f64…5a73` (42 tx) | exactly 42 txs to exactly 3 receivers | **benchmark/loop bot** |
| `0x6777…3986` (25 tx) | **386 different receivers** | broad crawler |

## ⚠️ Strategic correction to the „15 payers = live demand" thesis
Most repeat-payers on the market leader look like **infrastructure probes**,
not human operators: they pay EVERY x402 service, small amounts, at machine
cadence. Implication (better than outreach!): **if Kristo is inside the
crawl set (x402scan listing + discovery files), these wallets pay us
automatically.** First real revenue may arrive as crawler payments, which
will also validate our payment rail end-to-end for free.

## Fee thermometer: PayAPI takes NO on-chain cut (checked our canaries)
All 3 canary receipts (`0xb8a52dcd…`, `0xf5cff040…`, `0x0cc98ef9…`) are simple
1:1 USDC transfers payer→receiver; the only other log is an Approval. No
second-address fee split → PayAPI's take (if any) is off-chain. Market GMV
thermometer must be built by summing the top listings' payTo addresses instead.

## Standing recon protocol (monthly)
1. `competitor_recon.py` on 2–3 most visible listings, one at 30d window
2. `payer_lookup.py` + outgoing-transfer fingerprint on new repeat payers
3. Re-scan our own receiver — first `external_unique_payers > 0` is the launch signal

## Wave 2 (04.09 late): H1 measured, loop de-masked, taxonomy shipped

### H1 (listing age → first crawler payment): MEASURED — crawler is a LATE adopter
Five receivers of `0xC59E`, full incoming history over 30d:
| Receiver | First payment | Crawler arrived |
|---|---|---|
| `0xd6b5…` | 2026-08-05 (109 txs, 10 payers) | **+24.6d** |
| `0x110c…` | 2026-08-05 (384 txs, 48 payers) | **+21.8d** |
| `0x2740…` | 2026-08-05 (137 txs, 14 payers) | **+23.7d** |
| `0xd8ba…` | 2026-08-06 (1049 txs, 11 payers) | **+23.8d** |
| `0x0e84…` | 2026-08-05 (**7241 txs, 338 payers!**) | **+21.8d** |

Median lag ≈ **+23.7d** — the crawler is NOT the first payer on any sampled
receiver; it shows up ~3–4 weeks after a receiver is already being paid by
humans/other bots. H1 (we're just new) is STILL ALIVE at day ~8: we are
inside the observed 22–25d window. Verdict: wait to day ~30, then re-test H3/H4.
Also note `0x0e84…`: 338 distinct payers/30d — real demand exists somewhere
on this market; it's just concentrated in a few established APIs.

### Loop identity: `0x5f64` is NOT a benchmark — it's likely a TRADING agent
Fingerprinted the two loop partners:
- `0xcf92…` („loopA"): 14 payers, 117 txs, 0.472 USDC/7d — a real, modestly
  popular third-party API at ~$0.002/call.
- `0x480c…` („loopB"): **456 payers, 1022 txs, 131,142 USDC/7d** — that is a
  money-moving ROUTER contract (individual inflows of 951/2815/1123 USDC),
  NOT an API payTo. The 41 micro-payments from `0x5f64` (0.002 each) ride
  among institutional flows.

Revised read on `0x5f64`: api-call (house PayAPI) + api call (loopA) +
swap through a router = **a live trading agent**, the only confirmed one on
the entire observed market. That makes it BOTH the top outreach target AND
proof that the agent-trader archetype exists here. Its loop partners'
sellers: loopA's seller is contactable (real listing, real traffic) — the
„related APIs" alliance pitch applies to loopA only.

### Tooling shipped
- `fingerprint_payer()` in `competitor_recon.py`: automatic payer taxonomy
  (crawler ≥50 receivers/week; loop ≤10 receivers & ≥10 txs; human otherwise).
  Launch signal stays: `external_unique_payers > 0` in the HUMAN bucket.

## Wave 3 (04.09): Chet's market-intel answer → search index measured

### What Chet confirmed (email 04.09, 13:34)
- Agent discovery = `GET /agent/search?q=…` + MCP tools (search_apis/list_apis/
  get_api at payapi.market/mcp) — human category browsing is secondary
- No paid slot; marketplace defaults to settlement-verified only; first row is
  for independent providers, not the storefront
- **No seller-side analytics yet** (views/impressions don't exist; the
  "most-used" sort field is still zero in the catalog — his words)
- Offer on the table: he'll review a ONE-LINE title change

### Search index audit (live, /agent/search)
| Query | We appear? | Position |
|---|---|---|
| q=defi | ✅ | **#1** |
| q=signals | ✅ | #3 |
| q=eth | ❌ MISSING | — |
| q=kaito | ❌ (0 results — nobody lists KAITO!) | — |
| q=crypto | ❌ MISSING | — |

Root cause confirmed: search matches listing name/description text; our
description has ZERO tickers → we lose every token search (eth/ondo/kaito/
degen/crypto). Exactly what Chet predicted ("show the tickers in row one").

### New competitors discovered (q=signals top-3)
| Listing | Price | Endpoints | Verified |
|---|---|---|---|
| Crypto Snapshot Pro – AI Trading Signals | $0.025 | 1 | ✅ (onrender subdomain) |
| Trend Signals | $0.001–0.05 | 4 | ✅ (custom domain) |
| **Kristo Intelligence** | **$0.003–0.005** | **11** | ✅ 2 routes |

We are the cheapest signal entry with the deepest endpoint surface — but
invisible to token searches. Fix = title/description text, zero code.

### Proposed one-line title change (sent to Chet for review)
`Kristo Intelligence — DeFi Signals API (ETH, ONDO, KAITO, DEGEN on Base)`
Description line (if he takes it): "Trading-agent signals for ETH, ONDO,
KAITO and DEGEN on Base — action, confidence, price and reasoning per call.
Whale USDC tracking, cross-DEX arb spreads and rug checks included."

## Wave 4 (04.09 evening): full term map → finalized title draft

### Complete search-term map (live /agent/search, 15 queries)
| Term | Total results | Our position |
|---|---|---|
| defi | 3 | **#1** |
| whale | 1 | **#1** (we own the term) |
| rug | 2 | #2 |
| signals | 7 | #3 |
| eth | 2 | ❌ missing |
| ondo | 1 | ❌ missing |
| kaito / degen | 0 | ❌ EMPTY NICHE, we're missing |
| crypto | 7 | ❌ missing |
| **trading** | 4 | ❌ missing (Crypto Snapshot Pro #1) |
| **trading signals** | 1 | ❌ only Crypto Snapshot Pro |
| **ai signals** | 3 | ❌ missing |
| market data / price feed | 12 / 1 | ❌ missing (Trend Signals owns price feed) |

### Finalized title draft (merged from Chet's read + term map)
**Title:** `ETH ONDO KAITO DEGEN trading signals — whale flow, rug risk, arb`
(adds "trading" — currently owned by Crypto Snapshot Pro — plus all 4 tickers;
"signals" we already rank #3 on, "defi"/"whale" we own)

**Description:** "Kristo Intelligence DeFi Signals API: live trading-agent
signals for ETH, ONDO, KAITO and DEGEN on Base — action, confidence, price
and reasoning per call. Whale USDC tracking, cross-DEX arbitrage spreads and
rug risk checks. Pay per call, x402 USDC on Base. Route: GET /api/v1/signal."
(long brand name moves to description, for humans; "ai signals" term covered
by "trading-agent signals")

### Sweeps hypothesis (from the audit — pending cadence data)
Two red flags in the H1 table: (1) all five sampled "first payments" were
2026-08-05/06 — either a real launch cohort or the LEFT EDGE of our 30d
window; (2) the crawler arrived at all five within 2.8d (27–29.08) —
consistent with ONE catalog-wide sweep, not per-listing discovery.
If sweeps are real: our crawler payment depends on THEIR sweep schedule,
not our listing age. Tool shipped: `scripts/crawler_cadence.py`
(90d outgoing histogram of the crawlers + burst-gap → next-sweep date;
`--first-payment` mode re-checks the left edge).

## Wave 5 (04.09 night): cadence measured — both audit hypotheses answered

### Q2 (left edge): CONFIRMED — the H1 table measured from a false zero
True first payments (60d window, sequential scans):
- `0xd6b5…`: **2026-07-06**, 451 txs, 18 payers (not 05.08/109 txs!)
- `0x0e84…`: **2026-07-06**, **123,029 txs, 683 payers** — and with flows that
  size it is almost certainly ANOTHER ROUTER, not an API (like `0x480c`)
- → The "05.08 cohort" was the left edge of the 30d window. The crawler's
  arrival at d6b5 was ~54 days after its true first payment, not ~24.
  H1 („just wait") loses even more support: these receivers were long
  established before any crawler payment.

### Q1 (cadence): NOT sweeps — near-continuous indexing with a ramp
- `0xC59E` (60d): 2,948 txs; first burst 08-12 (125), GIANT ramp 08-23..08-30
  (~2,750 txs), then sparse (49 on 09-01, 3 on 09-03)
- `0x6777` (60d): 1,673 txs; **continuous, every single day 08-14 → 09-04**
  (124 txs today). Median burst gap ~1.1d. Still running.
- Verdict: no monthly sweep to wait for. One crawler (6777) indexes
  CONTINUOUSLY, every day, at 100–250 txs/day.

### The uncomfortable conclusion (H3/H4 promoted)
We have been live on PayAPI since ~02.09. A continuously-sweeping indexer
that paid 124–246 receivers per day has run 3 sessions since our listing —
and still has not paid us. H1 (lag) is nearly dead. The remaining hypotheses:
- **H4 (source directory):** the crawler's source list may not include PayAPI
  third-party listings at all (it pays mostly routers/first-party?) —
  testable: what share of 6777's daily payments go to known PayAPI listings?
- **H3 (format):** byte-diff of our challenge/manifest vs paid listings.
- Cheapest next test: pick 3 PayAPI third-party listings paid by 6777 in the
  last 24h and compare their challenge structure with ours. If identical
  structure → we're just not in the crawl source → H4.

### Tooling: `scripts/crawler_cadence.py` + a real debugging lesson
- Fixed a positional-topics bug in `collect_transfer_blocks` (missing `None`
  placeholder made "incoming" scans filter as FROM → false zeros; three
  RPCs agreeing on zero was the bug, not throttling — the 7d control test
  caught it). Lesson encoded: control test before trusting a zero.
