# RESEARCH — "verifier layer" (No. 5 from WATCH_LIST)

> Local document, 07.10.2026. No code changes — a plan and data for a decision.
> Context: `WATCH_LIST.md` line 5 (`Nikolife2016/pulsefeed-x402` issue #3) +
> `AP2_RADAR.md` THERMOMETERS (Trust layer = niche No. 2: Solvador, "402 Wall",
> Dr J / code402 + x402-conformance; PulseFeed = new player).

## What a "verifier layer" is

External verification of an x402 transaction/response **before the money or the
data goes through**. It differs from crypto-verification (EIP-712 is already
solved) — what is checked is the **value/safety**, not the signature.

Two directions (per the PulseFeed README — "Verify before you pay or install"):

| Direction | Who asks | Question |
|---|---|---|
| **pre-pay** (the buyer) | the agent before it pays | is the endpoint safe (liveness, 0–100 trust, scam flags: swapped receiver, catalog price ≠ challenge price, honeypot receiver, testnet as production) |
| **pre-delivery** (the seller = us) | our server before delivery | is what we are delivering correct (cross-checking the data against an independent source) |

---

## (a) Which source does the verifying

**Candidates for an independent source (cross-checking our data):**

1. **CoinGecko public API** — free, no key; already integrated
   (`services/coingecko.py`, cache + cooldown). Suitable for: the price of ETH/
   ONDO/KAITO/DEGEN against our signal.
2. **DexScreener** — free, no key; already in use
   (`fetch_dexscreener_implied` in `market_data.py`). Suitable for: cross-DEX
   price.
3. **Base on-chain (RPC)** — the receipt/block are already read on the settle
   path (`main.py:_try_consume_standard_payment`). Suitable for: payment
   finality.
4. **External guard for the incoming direction** — PulseFeed `GET
   https://pulsefeed.dev/verify?endpoint=<url>` (free, no key, CORS) returns a
   pay/avoid verdict + on-chain proof. Suitable for: when WE are the buyer
   (Bazaar/F1 tests).

**Recommendation:** a rule-based cross-check of No. 1 + No. 2 (± a threshold
against an independent feed) as the first line; LLM only for edge cases; No. 4 —
for our outgoing payments. Scanner catalogs (x402scan, discovery indexes) verify
the *declaration*, not the value — a different job.

## (b) Which cheap model says "yes/no" and what it costs per request

Prices: **OpenRouter `GET /api/v1/models`**, 07.10.2026 (public endpoint,
$/1M tokens). The estimate is for a verdict request: ~400 tokens input
(instruction + response fragment) + ~5 tokens output ("yes"/"no").

| Model | $/M in | $/M out | **$ per verdict** |
|---|---:|---:|---:|
| `qwen/qwen3.7-flash` | 0.03 | 0.13 | **~$0.000015** |
| `openai/gpt-5-nano` | 0.05 | 0.40 | ~$0.000022 |
| `google/gemini-2.5-flash-lite` | 0.10 | 0.40 | ~$0.000042 |
| `openai/gpt-4.1-nano` | 0.10 | 0.40 | ~$0.000042 |
| `z-ai/glm-4.5-air` | 0.13 | 0.85 | ~$0.000056 |
| `openai/gpt-4o-mini` | 0.15 | 0.60 | ~$0.000063 |
| `deepseek/deepseek-chat` | 0.257 | 1.029 | ~$0.00011 |

Notes: GLM-4.5-**Flash** is missing from OpenRouter (`glm-4.5-air` is available,
as is `glm-4.6` @ 0.43/1.75 — expensive for this job). The current `GLM_MODEL`
for bulletins is not mandatory here — a "yes/no" verdict does not need a large
model.

**Recommendation:** `qwen/qwen3.7-flash` (cheapest) or `openai/gpt-5-nano`
(a more familiar provider). Format: `max_tokens≈5`, the answer strictly `yes`/
`no`; incorrect format → treated as "no verdict" (does not block).

## (c) Where it enters the code (before delivery)

**One** barrier before "the product left the building" has been identified:

- **`main.py:_try_consume_standard_payment`** (the settlement path, ~lines
  2845–2988) — after verify + settle and **before** `g.x402_settlement` is
  stored.
- **`main.py:_emit_payment_response`** (`after_request`, ~lines 2991–3032) —
  the last point before `dashboard_db.mark_payment_delivered(tx)`: this is the
  place where F3 determines that delivery has happened.

**Proposed entry (when it gets built):**
1. **Rule-check (synchronous)** in `_try_consume_standard_payment` — checking
   the price/data against the cached independent feed; on a mismatch →
   `dashboard_db.record_guard_event("value_check_mismatch", …)` + a log entry.
2. **LLM verdict (asynchronous / on samples)** — a fire-and-forget thread (like
   `_detect_reorgs`) that records `yes`/`no` as a guard event.
3. **Fail-open, not fail-closed**: the payment has already gone through — the
   check brings visibility, it cannot return money. Blocking would harm the
   client who already paid.

## (d) Expected effect on price/speed

| Mode | Latency of a paid request | Cost |
|---|---|---|
| Rule-check (sync, cached feed) | +0–50 ms | $0 |
| LLM verdict **synchronous** | +0.4–1.5 s | $0.00002–0.00006 |
| LLM verdict **async/sampled** | +0 ms on the critical path | $0.00002–0.00006 per checked request |

Relative to our price of $0.003–0.005/request: even 100% LLM checking comes out
at **~0.5–2%** of revenue (1000 paid requests/month ≈ $0.02–0.06/month for
LLM). Latency, however, matters more: a synchronous LLM makes the $0.003
product respond more slowly — hence **async/sampling**.

**Limitation:** a yes/no verdict without an explanation is weak for our numeric
data — a rule-check of ±2% against an independent feed gives a stronger
guarantee than a cheap LLM. An LLM makes sense for non-numeric checks (e.g.
whether the textual argument of the signal contradicts the number).

## Sources
- PulseFeed README (`Nikolife2016/pulsefeed-x402`, read 07.10.2026):
  `check_x402_endpoint`, 0–100 trust score, scam flags, `GET /verify?endpoint=`
  (free, no key), nightly drift-diff of the MCP registry.
- OpenRouter `GET /api/v1/models` — prices as of 07.10.2026.
- Our code: `main.py` (2845, 2965, 2991–3032), `services/coingecko.py`,
  `services/market_data.py`, `AP2_RADAR.md` THERMOMETERS.
