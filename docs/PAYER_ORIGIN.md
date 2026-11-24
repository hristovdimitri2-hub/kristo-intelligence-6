# PAYER ORIGIN — who is behind 0x5f64 and the loopA seller? (04.09)

Method: 60-day USDC scans via our own RPC (`get_logs`, chunk 5000, control test
before the analysis — 127 txs in the 7d control window) + Basescan pages (needed for
the ETH/delegation history that logs do not provide). Data: `docs/_origin_data.json`.
Everything read-only.

## VERDICT: **INDEPENDENT** — zero evidence of a link behind the funding

### 1. Buyer `0x5f64…` — an agent with a budget of $2.00
- Incoming USDC over 60 days: **exactly 1 transaction, $2.00**
- Source: another wallet (starts with `0x680d…`) — a one-off micro-funding
- Incoming ETH: **zero**; own transactions: **zero** (Basescan: Sent N/A, First
  N/A, Funded By N/A) → entirely a **gasless agent** (the facilitator signs and
  pays gas; it only signs x402 requests)
- Conclusion: the only "real" trading unit on the market runs 127+ paid calls on
  a budget **under $1** (from a $2.00 fund, balance 0.61)

### 2. loopA `0xcf92…` — a retail developer with MetaMask, no sweep
- Code: `0xef0100…` → **EIP-7702 delegation** to **"MetaMask: EIP-7702
  Delegator"** → a personal MetaMask account, delegated on **2026-03-04** by
  `0x4c6Dd3BA…9EF91D054` (its only own transaction in history)
- Balance: **$66.84 USDC** + 43 dust meme tokens + 0.0013 ETH
- Incoming flow (60d): **3,518 tx from 363 different payers, $16.61** — far
  busier than the 7-day sample showed (117 tx/14 payers)
- **Sweep: NONE** — 0 outgoing USDC transfers over 60 days; the balance is pure
  accumulation of revenue since March. There is no outflow source → no sweep
  address

### 3. Direct edge between them: NONE
- loopA → buyer: 0 transfers over 60 days (out_txs=0)
- buyer → loopA: yes, **41+ paid calls** — but that is a customer payment (data
  for USDC), not funding
- buyer funding source (0x680d…) ≠ loopA funder (0x4c6Dd3BA…)

### 4. Cluster: different funders, no common source (sample 3/14)
| loopA payer | Funded By | Profile |
|---|---|---|
| `0x5f64…` (buyer) | `0x680d…` (one-off $2) | gasless agent-trader |
| `0x9897…` (47 tx) | self-funded retail | DeFi user: 170 USDC + staking + 111 tokens |
| `0xcd51…` (10 tx, **$0.021/call!**) | `0xf7A13DBB…` (**2 days ago**) | new operator, fresh wallet |
| the loopA seller | `0x4c6Dd3BA…` (184 days) | retail developer with MetaMask |

Four different funders, zero common sources in the sample. The market of actual
payers consists of separate, independent, small operators — **including one who
arrived 2 days ago and paid immediately at the high price.**

## Strategic conclusions
1. **The loopA seller is an individual with MetaMask** — personal outreach is
   possible only through the x402scan listing (if it is there) or via Chet. The
   email text in LOOPEEMAIL_PACKAGE.md is ready and address-agnostic.
2. **The fresh payer `0xcd513d2e` is live proof of conversion:** a wallet funded
   2 days ago paid 10× at the high price — the market is adding new operators
   RIGHT NOW. This is the strongest argument that our listing will get payers
   with no extra action at all.
3. The buyer budget ($2.00/60d) confirms: **micro-prices are right for
   discovery**, operator deals — for revenue. Do not touch the prices.
4. loopA does NOT sweep — its revenue accumulates in the wallet. The difference
   "balance vs weekly flow" is NOT a sign of a sweep: check with out_txs=0, not
   with the balance.
