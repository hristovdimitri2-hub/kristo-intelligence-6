# Kristo Intelligence — x402 API for AI agents on Base

[![Kristo Intelligence MCP connector — Glama score](https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence/badges/score.svg)](https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Kristo Intelligence MCP server](https://mcprush.com/badge/kristo-intelligence-mcp/card.svg)](https://mcprush.com/to/kristo-intelligence-mcp?ref=badge) [![Lumière PayCheck](https://lumierepaycheck.org/badge?url=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fv1%2Fverify-seller)](https://lumierepaycheck.org/e?url=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fv1%2Fverify-seller) [![x402 Doctor: payable](https://x402-doctor.fizzl.eu/badge.svg?url=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fv1%2Fverify-seller)](https://x402-doctor.fizzl.eu/trust?url=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fv1%2Fverify-seller)

**Check a seller before you pay it.** Paid API for AI agents on Base, x402-native:
agents pay per call in USDC, from $0.005 — no signup, no API keys, no
subscriptions.

The first question an agent has before paying an unfamiliar x402 seller is
whether that seller is real. `verify-seller` answers it from the chain — incoming
USDC transfers for any Base address, distinct paying addresses, repeat-payer
concentration, treasury-sized flows separated out. It is the one route here that
reads live chain logs per call, and the only one priced above the rest.

Live API: https://kristo-intelligence-api.onrender.com
Marketplace listing (settlement-verified): https://payapi.market/api/kristo-intelligence-defi-signals-api
Agent listing (settlement-verified, badged): https://payapi.market/agent-marketplace/kristo-seller-audit-verify-an-x402-seller-before-you-pay

## What it is

Kristo Intelligence is a live x402 API on the Base network (Coinbase's L2).
Every call returns machine-readable answers — the first one being whether a
seller is real:

- **Seller verification** — audit any Base receiver's incoming USDC before you
  pay it: distinct payers, repeat-payer concentration, treasury-sized flows,
  and the read's own coverage stated
- **Trading-agent signals** — for ETH, ONDO, KAITO and DEGEN: action,
  0–1 confidence score, current USD price, and one-line reasoning. **Its own
  measured record is published free at `/public/signals/history` and travels
  with every paid response — as scored to date it is a losing record, the
  average miss being larger than the average hit.**
- **Whale flow** — large USDC transfer tracking on Base (transfers ≥ $5M, labeled counterparties)
- **Arbitrage radar** — cross-DEX spreads, refreshed every 60 seconds
- **Market stats** — aggregated activity (CoinGecko, DEXScreener,
  Fear & Greed)

## Payment (x402)

The API speaks the [x402](https://www.x402scan.com) payment standard. The
flow is three steps and works from any HTTP client:

1. `GET` any paid endpoint → **HTTP 402** with a self-describing challenge
   (exact USDC amount, receiver address, chain)
2. Send that USDC amount on Base to the listed receiver
3. Retry the call with the payment header → `200` with your data

No keys. No accounts. Settled in USDC on Base (chain 8453). Prices start at
**$0.005 per call** — the complete list is below.

### Two payment rails

Prefer **rail 1**: it is what the x402 ecosystem (x402-fetch, x402scan,
facilitators) speaks.

- **Rail 1 — standard x402.** The 402 carries the canonical `PAYMENT-REQUIRED`
  header (base64) and a body whose `accepts[0]` states the exact atomic amount,
  `payTo`, `asset` and CAIP-2 network for that route. Sign an EIP-3009
  `transferWithAuthorization` for that amount (scheme `exact`) and retry the same
  request with the payload base64url-encoded in the **`PAYMENT-SIGNATURE`**
  header. Settlement runs through the facilitator automatically. Clients still
  on x402 v1 send the same payload in `X-PAYMENT`; both are accepted, and
  `PAYMENT-SIGNATURE` wins when both are present.
- **Rail 2 — smart wallets and exchange withdrawals.** Coinbase Smart Wallet,
  Binance Web3, passkey signers and exchange payouts cannot sign EIP-3009, so
  this is their normal path. Send the **atomic** amount yourself: take
  `accepts[0].amount` from the 402 body verbatim — `"5000"` means 0.005 USDC —
  transfer that many base units of USDC on Base (chain 8453), wait for 12
  confirmations (~2.5s), then retry with `X-Payment-Proof:
  base64url(JSON({payer, transaction_hash, amount_usdc}))`, whose `amount_usdc`
  is the same atomic value. If your wallet API wants a decimal amount, divide by
  `1e6` first. Do **not** send the decimal display price as if it were base
  units: the on-chain check is `amount >= price`, so a 1,000,000× overpayment is
  accepted rather than rejected. The 402 is the only authoritative amount, and
  the [`kristo-x402-client`](packages/x402-client) does this conversion for you.

A signed payload is single-use. **HTTP 425** means your payment already settled
on-chain but our node has not reached the confirming block yet — retry the same
request shortly and do **not** pay again. **HTTP 401** means a credential was
presented but is unusable (bad signature, wrong amount or receiver, expired
authorization window, or an already-used transaction).

### Prices

These eight routes are the complete paid surface. The table is checked against the
live price map by `tests/test_visibility_seo.py`, so the README cannot drift away
from the amounts the 402 challenges actually demand:

| Route | USDC per call |
|---|---|
| `GET /api/v1/signal` | 0.01 |
| `GET /api/v1/whaleflow` | 0.01 |
| `GET /api/stats` | 0.005 |
| `GET /api/sales` | 0.005 |
| `GET /api/bot-status` | 0.005 |
| `GET /api/arb/opportunities` | 0.005 |
| `GET /api/v1/verify-seller` | 0.05 |
| `GET /api/v1/demand-census` | 0.25 |

`/api/v1/verify-seller` is the one route that takes input: pass
`?receiver=0x…` to audit any Base address's incoming USDC before you pay it.
It is priced above the rest because it reads a live window of chain logs per
call rather than serving a cached snapshot.

`/api/v1/demand-census` is the dearest call here and the only one that sells a
**measurement rather than data**: the per-agent demand table behind this
service's own paywall — every user agent that reached a 402, when it first and
last arrived, how many requests it made and whether it ever paid, plus every
payment attempt by outcome. The aggregate and the method are public in
[`docs/X402_DEMAND_CENSUS.md`](docs/X402_DEMAND_CENSUS.md); the per-agent table
is the part that is sold.

Every one of them has a **free `/sample` twin** returning the real response
shape with example data — see the discovery list below. Try the shape before
spending anything.

[![x402 Trust: grade B, recommendation proceed](https://x402-trust.com/badge.svg?resource=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fstats)](https://x402-trust.com/endpoint/139372)

## MCP (Model Context Protocol)

The API is exposed as an MCP server for Claude Desktop, Cursor, Continue,
LangChain and any MCP-compatible client:

- **SSE transport:** `https://kristo-intelligence-api.onrender.com/mcp/sse`
- **Streamable HTTP transport:** `POST https://kristo-intelligence-api.onrender.com/mcp`
  (JSON-RPC 2.0 — `initialize`, `tools/list`, `tools/call`, `ping`)

**MCP tools:**

| Tool | What it returns | Price (USDC/call) |
|---|---|---|
| `verify_seller_receiver` | On-chain audit of any Base receiver: distinct payers, concentration, coverage | 0.05 |
| `get_trading_signal` | Trading signals for ETH, ONDO, KAITO, DEGEN | 0.01 |
| `get_whale_flow` | Network-wide USDC transfers ≥ $5M on Base | 0.01 |
| `get_market_stats` | Market activity, daily stats, live market data | 0.005 |
| `get_onchain_sales` | Real on-chain sales history (USDC transfers) | 0.005 |
| `get_bot_status` | Telegram bot integration status | 0.005 |
| `get_arbitrage_opportunities` | Cross-DEX arbitrage spreads on Base | 0.005 |

Each tool advertises its x402 price inline, so an agent can decide and pay
without reading docs.

## Discover via PayAPI

The listing lives on [PayAPI Market](https://payapi.market/api/kristo-intelligence-defi-signals-api)
and can be discovered through PayAPI's own MCP server — agents already
connected to the marketplace warehouse will find our routes from both sides:

```json
{
  "mcpServers": {
    "payapi": {
      "url": "https://payapi.market/mcp"
    }
  }
}
```

Listing: <https://payapi.market/api/kristo-intelligence-defi-signals-api>

**Agent listing (settlement-verified, badged).** The same marketplace carries the
agent form of this service — a job an agent can hire end to end, rather than an
API to call. PayAPI verified it with a real paid call on Base:

<https://payapi.market/agent-marketplace/kristo-seller-audit-verify-an-x402-seller-before-you-pay>

## Try it — one command

The public reference client walks the full payment path (discovery → 402
challenge → paid retry) with no wallet required in demo mode:

```bash
python examples/demo_agent/demo_agent.py --endpoint /api/v1/signal
```

Free discovery surfaces (no payment needed):

- x402 discovery: `/.well-known/x402`
- OpenAPI 3.0: `/openapi.json`
- MCP manifest: `/api/mcp/manifest`
- Agent manifest: `/agents.json`
- LLM-friendly API description: `/llms.txt`
- Quickstart snippets (curl/Python/Node): `/api/v1/quickstart`
- Checkable facts (status, uptime, on-chain history): `/validation`
- Health: `/health`

**A free sample of every paid route** — real response shape, example data, no
payment and no signup. Use these to build and test a client before spending
anything:

| Free sample | Mirrors |
|---|---|
| `GET /api/v1/signal/sample` | `/api/v1/signal` |
| `GET /api/v1/whaleflow/sample` | `/api/v1/whaleflow` |
| `GET /api/stats/sample` | `/api/stats` |
| `GET /api/sales/sample` | `/api/sales` |
| `GET /api/bot-status/sample` | `/api/bot-status` |
| `GET /api/arb/opportunities/sample` | `/api/arb/opportunities` |
| `GET /api/v1/verify-seller/sample` | `/api/v1/verify-seller` |
| `GET /api/v1/demand-census/sample` | `/api/v1/demand-census` |

## Repository layout

```
main.py                  # Flask app: API, x402 paywall, agents, transports
app/blueprints/discovery.py  # Discovery surfaces (.well-known, MCP, llms.txt)
services/                # CoinGecko client, DeFi signals, trading agent
blockchain/wallet.py     # Base wallet, USDC transfers, on-chain verification
scripts/                 # On-chain recon tools, demo agent, E2E helpers
examples/demo_agent/     # Public reference x402 client
docs/                    # Audit reports, recon findings, outreach docs
tests/                   # Test suite (1508 tests)
```

## Verification

- **Settlement-verified** on [PayAPI Market](https://payapi.market/api/kristo-intelligence-defi-signals-api):
  4 independent paid canaries settled on-chain, zero payment incidents
- **Agent listing live and badged** on PayAPI Market: verified with a real paid
  call on Base (block 58140667, $0.01 settled) —
  [kristo-seller-audit](https://payapi.market/agent-marketplace/kristo-seller-audit-verify-an-x402-seller-before-you-pay)
- **x402 registered**: 11 resources on [x402scan](https://www.x402scan.com),
  canonical v2 challenges (CAIP-2 `eip155:8453`, atomic units, bazaar schema)
- **23/23 adversarial audit** (mystery-agent simulation, 2026-08-29 — a dated
  snapshot; see the banner in `docs/MYSTERY_AGENT_REPORT.md`)
- **1508 automated tests** in this repository

## Docs

- `docs/MARKET_WRITEUP.md` — on-chain audit of the machine-payments market
- `docs/INDEXING_WRITEUP.md` — **how an x402 endpoint actually gets indexed**:
  measured field notes on the two catalogues, the shapes they accept, and the
  three things we got wrong finding out (17.11.2026)
- `docs/PAYER_ORIGIN.md` — who actually pays on this market
- `docs/MYSTERY_AGENT_REPORT.md` — adversarial buyer simulation (2026-08-29;
  its two price figures and its "standard rail not honoured" note are
  superseded — the file opens with a banner saying exactly what changed)
- `docs/RECON_FINDINGS.md` — ongoing on-chain recon notes

## License

**MIT** — the full standard text is in [LICENSE](LICENSE).

The payment receiver and endpoint structure are stable invariants — discovery
surfaces and integrations depend on them.

### Commercial use notice

This software executes real financial transactions on the Base blockchain
network when AGENT_AUTO_EXECUTE=true. The authors and copyright holders
assume no responsibility for financial losses resulting from the use of this
software. Always test on Base Sepolia testnet before mainnet deployment.