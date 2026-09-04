# The On-Chain Economy of a Machine-Payments Marketplace: An Audit

*Dimitri Hristov — September 2026. All numbers below are measured on-chain
during early September 2026 (7- and 60-day windows), on Base mainnet.*

---

## Why an API marketplace can be audited at all

x402 is a payment standard where an AI agent pays per API call in USDC, on
Base, without an account or API key. The machine-payments thesis rests on a
property most people miss: **settlement is a public ERC-20 transfer.** Every
paid call leaves a permanent on-chain receipt — payer, receiver, amount,
timestamp.

That turns a marketplace into a measurable object. You don't have to trust a
dashboard; you can `eth_getLogs` the entire payment history of any settlement
address and reconstruct the economy from first principles. That is exactly
what we did, with read-only tooling committed to this repository
(`scripts/competitor_recon.py`, `scripts/crawler_cadence.py`,
`scripts/payer_lookup.py`) — no explorer API keys, no privileged access,
just a public RPC and ERC-20 Transfer topics.

Two data-hygiene rules the audit taught us, worth stating before the findings:

1. **Control-test every zero.** A silent `except` around an RPC call can turn
   a rate limit into a plausible-looking "0 transactions". Three different
   public RPCs agreeing on zero is not evidence — a 7-day window you already
   have receipts for is.
2. **Window edges create fake cohorts.** A 30-day scan reported five API
   endpoints all "first paid" on the same two days. Extending to 60 days
   showed the true first payments were a month earlier. Measure the edge
   before measuring the trend.
## Findings

### 1. The market is real, tiny, and a month old

The largest listing we measured (the settlement address for one platform-side
offering) recorded **159 paid calls in a 7-day window in early September,
totalling $0.29 USDC** — about $1.2/month. That address turned out to be
shared by roughly nine first-party listings, so the per-listing number is
smaller still. This is not a failure of the marketplace — the agent-payment
ecosystem around it is genuinely just starting. It is a measurement: **the
whole observed machine-payments economy is currently worth pocket change,
and that is the honest baseline** every future claim should be checked
against.

### 2. Most "payers" are infrastructure, not customers

Fingerprinting every payer's outgoing transfers (how many *distinct*
receivers they pay per week) separates three behavioural classes:

- **Crawlers/samplers** — wallets paying 150–390 different receivers per
  week, in the $0.001–0.05 range, continuously. Such wallets show up at a
  receiver ~3–4 weeks after the receiver is already being paid by others.
  These are measurement probes, not demand.
- **Loops** — wallets with ≤10 receivers at machine cadence.
- **Humans/unknown** — everything else.

On the busiest settlement address we sampled, **15 of 15 wallets were
anonymous (no ENS), and the most active ones paid 158–386 distinct receivers
per week** — infrastructure that samples every endpoint on the market,
arriving regardless of price (our price-filter hypothesis was refuted: the
sampler pays across the full range, $0.001 to $0.05+).

### 3. Exactly one real agent-trader — and its economics matter

One wallet stands out: it pays for data at **~$0.002 per call** in a steady
loop, and its other payments route through a DEX router contract that moves
**six figures of USDC per week**. The data budget is pocket change; the
pipeline it feeds is measured in thousands. That asymmetry — cents for the
signal, thousands for the action it feeds — is the strongest on-chain
argument that per-call data pricing is not where the money is. Operators
like this are the actual customer for paid market intelligence: the signal
is worth a rounding error of the trade, so its price can be a rounding error
of the salary.

(One honest methodological note: our first read of this wallet was
"benchmark bot". Fingerprinting its counterparties corrected us — one of its
three recurring payment targets turned out to be a money-moving router, not
an API. Measure counterparties before classifying anyone.)
### 4. An honest substring quirk

Search on the marketplace matches listing text by substring, not by token.
That is observable and charming: for the query "defi", the #2 result at
measurement time was a **nursing-home records API** — whose description
contains the word "de**fi**ciencies". Any revenue attribution on such a
market needs address-level filtering before it means anything.

## The ranking model — as documented by its author

The marketplace operator describes ranking in three layers, which we
validated against live data:

1. **Query match** — listing name and description text, matched loosely
   (substring, not token-exact).
2. **Settlement-verified** — the platform paid for one route from its own
   wallet and got real product back; the badge is enforced at database level.
3. **Reliability band** — computed in batches (the operator runs it when
   listings need a band or health history changes), from paid canaries,
   periodic health samples, and whether the settlement address still matches.
   MCP traffic does not affect it, and **new listings wait for the next
   compute** — visible in the API as `band: "unscored"` until then.

At measurement time the top result for "defi" was an *unscored* listing that
outranked one with a computed score of 69.6 — because the query matched its
name. The model is legible, and it applies **identically to the platform's
own first-party listings and to third-party ones.** That last part deserves
emphasis, because it is rare: ranking neutrality here is load-bearing
architecture, not a policy promise.

## What we take from it

A month-old machine-payments market with a self-auditable settlement layer
is the cleanest research substrate we have seen: every claim above can be
re-run with public tools in an afternoon. The machines are early, the
economy is small, and the rules are written down. That combination — small,
honest, and observable — is exactly where disciplined builders want to be
early.

---

**I build one of the listings.** [Kristo Intelligence — DeFi Signals API](https://payapi.market/api/kristo-intelligence-defi-signals-api)
is a settlement-verified, x402-native DeFi signals API on Base ($0.003/call
in USDC, no signup). If you want to see the payment path end-to-end, the
public reference client runs in one command:

```bash
python examples/demo_agent/demo_agent.py
```

Discovery (`/.well-known/x402`), a 402 challenge, and the paid retry are all
in the output — the same three steps every agent on the marketplace takes.
Recon tooling used for this audit lives in `scripts/` in the same repository.