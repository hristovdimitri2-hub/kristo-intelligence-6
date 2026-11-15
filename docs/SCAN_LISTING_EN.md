Title:
[Listing Request] Kristo Intelligence — live DeFi signals & whale-flow API (x402 v2, Base)

Body:

**Origin:** https://kristo-intelligence-api.onrender.com
**Spec:** https://kristo-intelligence-api.onrender.com/openapi.json
**Network / asset:** Base mainnet (eip155:8453), USDC
`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, x402 v2 `exact`
(payment-required base64 header, `x-402-version: 2`)
**payTo:** 0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f
**Discovery:** /openapi.json · /.well-known/x402 · /llms.txt ·
/api/mcp/manifest (MCP transports: POST /mcp, /mcp/sse)

**What it does:** Kristo Intelligence sells machine-readable crypto
intelligence to AI agents on demand: live DeFi trading signals (action,
confidence, one-line reasoning for ETH/ONDO/KAITO/DEGEN), whale tracking
(USDC transfers ≥ $5M on Base with labeled payers), cross-DEX arbitrage
opportunities and rug checks. No accounts, no API keys, no KYC — pay per
call in USDC on Base.

**Routes and prices:**

| Route | Price |
|---|---|
| GET /api/v1/signal — live DeFi signal | 0.003 USDC |
| GET /api/v1/whaleflow — whale-flow feed (transfers ≥ $5M) | 0.003 USDC |
| GET /api/arb/opportunities — cross-DEX arbitrage | 0.005 USDC |
| GET /api/bot-status — bot health status | 0.005 USDC |
| GET /api/sales — sales stats | 0.005 USDC |
| GET /api/stats — API stats | 0.005 USDC |

**Activity (30 days, public dashboard at /dashboard):**
* paid calls: `/api/v1/signal` — 9, `/api/v1/whaleflow` — 3
* unique payers: 5 (4 external + 1 our demo)
* Bazaar listings (PayAI): 2

Payments are single-use per EIP-3009 nonce, payment verification is
fail-closed (invalid proof → 401, never delivery), and every sale is
verifiable from the chain's Transfer logs. 471 automated tests.

**Ask:** please confirm that our paid routes are indexed correctly
(OpenAPI-first discovery + the 402 challenge are public on the origin), and
let us know if there is any additional requirement for searchable/featured
visibility — we will cover it.
