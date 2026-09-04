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
