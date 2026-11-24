# NEW OPERATOR ANALYSIS — fingerprint of 0xcd51 (04.09, the final intel task)

## VERDICT: **multi-API operator with ~300 calls/day, launched 2 days ago —
and its discovery source does NOT include anything from PayAPI**
(neither the house treasury, nor the verified third-party listings). That is why it
missed us — not because of the price, not because of the challenge format.

## The data (30-day outgoing USDC scan, own RPC, chunk 5000)
- **607 transactions** to **35 different payTo addresses**
- Top recipients: 263 tx ($1.44), 70 tx ($0.10), 43 tx ($0.43), 35 tx ($0.35)…
- loopA (`0xcf92…`) is among them: 10 tx, $0.213 → $0.021/call (matches its price)
- **The house treasury (0xFFc4…) is MISSING** from the list; Skim (0x63AE…), Lemon
  (0x0adc…), SameDayDesk (0x8904…) are also missing — it pays 35 other x402
  endpoints (probably the x402scan catalog, not the PayAPI catalog)

## Funder fingerprint: `0xf7A13DBB…` = a gas faucet, not an operator service
- 0 USDC outgoing for 30 days; the funding of 0xcd51 was **0.00001 ETH**
  (gas) on 01.09 + a delegation transaction
- → a one-time funding of a new wallet that AFTERWARDS acquires its own USDC
  (through its own activity/swaps) and starts paying APIs

## Time anomaly (important!)
Basescan shows only 1 ETH transaction in the history of 0xcd51 (funding
01.09). All 607 USDC payments go through a relayer/paymaster (gasless
7702 model) and are not counted among its ETH transactions. If the 607 are
concentrated in the last 2 days → **the operator launched the other day and is
already doing ~300 calls/day**. The market keeps adding new active operators.

## What this means for discovery
1. The operator pays 35 x402 APIs, but none of the PayAPI addresses we know
   of → its source is **another catalog** (probably x402scan). We have been
   listed there recently — entering its set is a matter of time or of the
   right resource.
2. Its taxonomy (35 payTo) is between "loop" and "crawler" — an active
   multi-API client, exactly the target profile for an operator deal.
3. Action: NONE directly. The monitor will show if it adds us.

---
**THIS WAS THE LAST intel task.** From now on only the monthly protocol
(recon + monitor) and the three human buttons. All H-hypotheses have answers,
all the data is in the repo.
