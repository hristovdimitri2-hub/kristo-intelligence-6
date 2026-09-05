# Kristo Intelligence — DeFi Signals API on Base

**Paid DeFi market intelligence for AI agents. x402-native: agents pay per
call in USDC, from $0.003 — no signup, no API keys, no subscriptions.**

Live API: https://kristo-intelligence-api.onrender.com
Marketplace listing (settlement-verified): https://payapi.market/api/kristo-intelligence-defi-signals-api

## What it is

Kristo Intelligence is a live trading-agent API on the Base network (Coinbase's
L2). Every call returns machine-readable market intelligence:

- **Trading-agent signals** — for ETH, ONDO, KAITO and DEGEN: action,
  0–1 confidence score, current USD price, and one-line reasoning
- **Whale flow** — large USDC transfer tracking on Base
- **Arbitrage radar** — cross-DEX spreads, refreshed every 60 seconds
- **Rug-risk checks** — pre-trade safety screening
- **Market stats** — aggregated activity (CoinGecko, DEXScreener,
  Fear & Greed)

## Payment (x402)

The API speaks the [x402](https://www.x402scan.com) payment standard. The
flow is three steps and works from any HTTP client:

1. `GET` any paid endpoint → **HTTP 402** with a self-describing challenge
   (exact USDC amount, receiver address, chain)
2. Send that USDC amount on Base to the listed receiver
3. Retry the call with the payment header → `200` with your data

No keys. No accounts. Prices from **$0.003 per call** (the cheapest route is
`GET /api/v1/signal`). Settled in USDC on Base (chain 8453).

## MCP (Model Context Protocol)

The API is exposed as an MCP server for Claude Desktop, Cursor, Continue,
LangChain and any MCP-compatible client:

- **SSE transport:** `https://kristo-intelligence-api.onrender.com/mcp/sse`
- **Streamable HTTP transport:** `POST https://kristo-intelligence-api.onrender.com/mcp`
  (JSON-RPC 2.0 — `initialize`, `tools/list`, `tools/call`, `ping`)

**MCP tools:**

| Tool | What it returns | Price (USDC/call) |
|---|---|---|
| `get_market_stats` | Market activity, daily stats, live market data | 0.005 |
| `get_onchain_sales` | Real on-chain sales history (USDC transfers) | 0.005 |
| `get_bot_status` | Telegram bot integration status | 0.005 |

Each tool advertises its x402 price inline, so an agent can decide and pay
without reading docs.

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
- Quickstart snippets (curl/Python/Node): `/api/v1/quickstart`
- Health: `/health`

## Repository layout

```
main.py                  # Flask app: API, x402 paywall, agents, transports
app/blueprints/discovery.py  # Discovery surfaces (.well-known, MCP, llms.txt)
services/                # CoinGecko client, DeFi signals, trading agent
blockchain/wallet.py     # Base wallet, USDC transfers, on-chain verification
scripts/                 # On-chain recon tools, demo agent, E2E helpers
examples/demo_agent/     # Public reference x402 client
docs/                    # Audit reports, recon findings, outreach docs
tests/                   # Test suite (152 tests)
```

## Verification

- **Settlement-verified** on [PayAPI Market](https://payapi.market/api/kristo-intelligence-defi-signals-api):
  4 independent paid canaries settled on-chain, zero payment incidents
- **x402 registered**: 11 resources on [x402scan](https://www.x402scan.com),
  canonical v2 challenges (CAIP-2 `eip155:8453`, atomic units, bazaar schema)
- **23/23 adversarial audit** (mystery-agent simulation, see `docs/`)
- **152 automated tests** in this repository

## Docs

- `docs/MARKET_WRITEUP.md` — on-chain audit of the machine-payments market
- `docs/PAYER_ORIGIN.md` — who actually pays on this market
- `docs/MYSTERY_AGENT_REPORT.md` — adversarial buyer simulation
- `docs/RECON_FINDINGS.md` — ongoing on-chain recon notes

## License

See the repository license file. The payment receiver and endpoint structure
are stable invariants — discovery surfaces and integrations depend on them.