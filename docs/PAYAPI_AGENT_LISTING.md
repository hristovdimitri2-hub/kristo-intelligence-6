# PayAPI Agent marketplace — ready listing for `/api/v1/verify-seller`

**Why exactly this route.** PayAPI has two places: the **API catalog** (a single
call — lookup, feed) and the **Agent marketplace** (an agent that does a whole job,
at a price per job). `/api/v1/verify-seller` is our only route that is a **task**,
not data: it audits a seller along the chain and returns a verdict. Our other
routes are already in the API catalog.

**Status (14.11.2026):** in the API catalog we are at `endpoints_count: 11`,
`payment_verified: true`, 3 verified routes. In the Agent marketplace we are
**not yet** — it requires an email login, which the agent cannot perform (see the
steps).

## The steps (only you can do them)

1. Open <https://payapi.market/agent-marketplace/list>
2. Enter `<contact-email>` — the **same email** with which we are in the API
   catalog (otherwise a second provider account is created).
3. PayAPI sends a **login link** to that address. Open it.
4. In the dashboard add the agent with the fields below. One agent is included in
   the free plan.

## The fields

```json
{
  "name": "Kristo Seller Audit — verify an x402 seller before you pay",
  "task": "Audit an x402 seller's on-chain payment history and return a verdict before an agent pays it.",
  "category": "Verification",
  "tags": ["x402", "seller audit", "trust", "on-chain", "base", "usdc", "payTo"],
  "description": "Give a Base receiver address and get an evidence-based verdict on whether it actually sells. The route reads incoming USDC transfers to that exact address on Base and returns distinct external payers, repeat payers, average check size, total volume, and how much of the volume is treasury/exchange flow rather than per-call payments. It separates known reviewer and verification addresses so they cannot inflate the customer count, and it reports coverage honestly: when the block scan is incomplete the verdict says the figures are a floor rather than a zero. It counts distinct paying addresses, and says so: one operator can pay from several wallets and several agents can share one. No signup, no API key, x402 on Base.",
  "paid_route_url": "https://kristo-intelligence-api.onrender.com/api/v1/verify-seller",
  "paid_route_method": "GET",
  "sample_url": "https://kristo-intelligence-api.onrender.com/api/v1/verify-seller/sample",
  "price_usdc": 0.01,
  "price_unit": "per_job",
  "networks": ["base"],
  "payment_flow": "authorization",
  "settles_before_running": true,
  "typical_latency_seconds": 3,
  "max_latency_seconds": 30,
  "underlying_model": null,
  "example_input": "receiver=0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f&days=7",
  "input_schema": {
    "type": "object",
    "required": ["receiver"],
    "properties": {
      "receiver": {
        "type": "string",
        "description": "Base address to audit (0x + 40 hex). Required.",
        "pattern": "^0x[0-9a-fA-F]{40}$"
      },
      "days": {
        "type": "integer",
        "minimum": 1,
        "maximum": 30,
        "default": 7,
        "description": "Window in days. Optional."
      }
    }
  },
  "output_schema": {
    "type": "object",
    "properties": {
      "ok": {"type": "boolean"},
      "coverage": {
        "type": "object",
        "description": "complete=false means the figures are a floor, not a zero.",
        "properties": {
          "complete": {"type": "boolean"},
          "failed_ranges": {"type": "integer"},
          "lookback_days": {"type": "integer"},
          "scanned_blocks": {"type": "integer"},
          "split_retries": {"type": "integer"}
        }
      },
      "payer_analysis": {
        "type": "object",
        "properties": {
          "external_unique_payers": {"type": "integer"},
          "repeat_payers": {"type": "integer"},
          "total_txs": {"type": "integer"},
          "total_usd": {"type": "number"},
          "avg_check_usdc": {"type": "number"},
          "known_verification_txs": {"type": "integer"},
          "noise": {
            "type": "object",
            "properties": {
              "large_tx_count": {"type": "integer"},
              "large_txs": {"type": "number"}
            }
          }
        }
      },
      "notes": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

## Two things not to forget

**The price.** The fields say `0.01`, because that is the current **pilot** price.
On **11.12.2026** the pilot expires and the price goes back to **0.10** (reminder
`schedule-39d6abaf`). If the listing is made after that date, `price_usdc` must be
`0.10` — otherwise the listing lies about the price, which is exactly the defect we
were closing in `config.py`.

**Verification.** `verification_state` is filled in by PayAPI, not by us — they
verify by paying the route. Do not promise verified in the description.

## What the listing does not do (their own warning)

> It doesn't guarantee jobs. A listing is a place to be found, not demand.

That is, this is distribution, not demand. It matches the finding from
`df-data-agent`: our constraint is visibility, not price.
