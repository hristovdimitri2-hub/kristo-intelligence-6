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
