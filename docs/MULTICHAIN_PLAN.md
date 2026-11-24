# Multichain plan — what it would cost and when it is worth it

**Created:** 16.11.2026, on the owner's instruction: "we cannot stay behind in the
whole system… I want us to be one step ahead of everyone in whatever they do".

**Status:** plan. **Nothing on the payment path has been touched.**

---

## 1. Why this is on the table

The x402 protocol is becoming multichain and this is not a rumour — it is visible in
the foundation's working channel: XRPL, Hedera, Canton, TRON, Celo, Solana splits,
Midnight and Arc are adding schemes. We are only on Base (`eip155:8453`).

**But the chains are being added by foundations.** Ripple, Hedera, Canton Foundation,
Celo Core — each with a team. We are one worker. Competing on the number of chains is
a race we lose by definition.

---

## 2. What it would cost — measured, not judged

### 2.1. Our structure is ready for a second option

`accepts` in the 402 is a **list** (`main.py:2495`), not a single object. The
specification allows several entries and the client chooses. That is, announcing a
second chain is adding an element, not reworking the envelope.

### 2.2. The code, however, is tied to Base

| constant/string | in how many files |
|---|---|
| `eip155:8453` | 25 |
| `8453` | 35 |
| `BASE_USDC_CONTRACT` | 17 |
| `BASE_RPC_URL` | 5 |

`BASE_CHAIN_ID` and `BASE_USDC_CONTRACT` are env variables, but **in the singular**.
So a second chain is a structural change to the payment path, the audit, the registry
and the dashboard — not configuration.

### 2.3. The facilitator is solved, and it is cheap

PayAI (we are already in their catalogue) supports **Solana + 8 EVM chains**. The
price is per settlement, not a percentage of the amount:

```
network                   price/settlement
Sei (1329)                $0.00038
Solana (5eykt...)         $0.00093   ← svm_transfer
Base (8453)               $0.00156   ← for comparison only; we are via CDP
Avalanche                 $0.00218
Polygon                   $0.00303
```

Their margin is **3000 bps (30%)** on top of gas, and the rate is `1 credit =
$0.001`.

**The first 1000 credits are free and belong to the receiving address** — without
registration. At $0.00093 per settlement that is **~1075 free settlements**.

### 2.4. What the math comes out to

| route | price | settlement on Solana | left over |
|---|---|---|---|
| signal / whaleflow | $0.01 | $0.00093 | $0.00907 (91%) |
| verify-seller | $0.05 | $0.00093 | $0.04907 (98%) |

That is, **the price is not the obstacle.** The work is the obstacle.

---

## 3. The plan, in phases

### Phase 0 — now, free
This document. Nothing is touched. Two things are already clear and make the next
phases cheaper: `accepts` is a list, and the free credits are given to the receiving
address.

### Phase 1 — when a real buyer asks
**The trigger is demand, not ambition:** if a buyer asks "can I pay in USDC on
Solana", we build it in a day.

1. A new receiving wallet on Solana (ed25519, key held by us).
2. A second entry in `accepts`: `network: "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp"`,
   `asset: <USDC mint>`, `payTo: <our address>`.
3. Settlement for **this entry** goes through PayAI (`/verify` + `/settle`), not
   through CDP.
4. Verification of the proof via the manual rail on Solana (reading the Solana
   chain).
5. The registry and the dashboard to count Solana payments too.

**Risk:** point 3 is on the payment path — our riskiest place. Mandatory with tests
before deploy and with the ability to disable it via an env flag.

### Phase 2 — where we can be genuinely ahead
**Not on the number of chains. On the product that nobody else makes multichain.**

`/api/v1/verify-seller` is the only one of our things that is not a commodity: an
audit of a receiving address based on its incoming payments. Today it reads only
Base. Nobody in the ecosystem offers this for more than one chain.

Ernest measured that in the chain-data category the $0.02–$0.06 band yields on
average **$10.97 per route** — versus $0.02 below $0.005. That is, there is money
there, and that is where we are differentiated.

**The chain is the entry; the audit is the product.** If we have to choose where to
be first, it is the audit of a second chain, not the payment on it.

---

## 4. Where we are already ahead (and how to stay there)

Three things the ecosystem is discovering **now**, and we have had since today or
earlier:

| what | who is discovering it now | us |
|---|---|---|
| `settlement_pending` as a non-terminal code | the foundation, in the weekly release | we read it from §9; we **say it** in the 425 as of today |
| manual rail for smart wallets | Losbeto, in production | we have it (`X-Payment-Proof`) and we **announce** exactly those wallets |
| unredacted RPC key in an error body | x402-rs#115/#118 | fixed in 10 places today |
| "paid but reported as a failure" | x402-rs#136 | our 425 + the waiting |

**The way to stay ahead is not to count chains, but to turn operational lessons
into a product.** Each of the four above became part of the product on the day we
learned it. This is the thing that one worker can do and a foundation with a team
cannot — they add chains, they do not pay attention to the funnel.

---

## 5. What we must NOT do

* **Announce a second chain without being able to settle it.** An envelope that
  promises a payment we cannot accept is worse than its absence — just as
  `queryParams: {}` was worse than a missing input (see §52).
* **Touch the payment path without need.** It is the only thing that cannot fall,
  and today we have already touched it twice over real defects.
* **Chase the number of chains.** The foundations have teams; we have attention to
  detail. We compete with the second.

---

## 6. One sentence

**We are structurally ready (`accepts` is a list), the facilitator is cheap
($0.00093 on Solana, the first ~1075 free), but the code is tied to Base in 25–35
files — that is why the second chain is built on demand, and the first thing that
is worth being multichain is the audit, not the payment.**
