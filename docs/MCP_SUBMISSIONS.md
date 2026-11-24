# MCP SUBMISSIONS — ready packages for direct registration (03.09)

Goal: not to wait for the PayAPI approval — Smithery, Glama and PulseMCP accept
**direct** submissions. The server already answers everything needed: SSE
transport, manifest, paid tools. Submitter: <contact-email>.

**Common fields (for all forms):**
- Name: `kristo-intelligence`
- URL (SSE): `https://kristo-intelligence-api.onrender.com/mcp/sse`
- Manifest: `https://kristo-intelligence-api.onrender.com/api/mcp/manifest`
- OpenAPI: `https://kristo-intelligence-api.onrender.com/openapi.json`
- Description: `Paid DeFi intelligence API on Base: trading-agent signals (action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native: agents pay per call in USDC, from $0.003 — no signup, no API keys.`
- Category: Finance / Market Data
- Pricing note: pay-per-call via x402 protocol (HTTP 402 challenge), $0.003–$0.005

## 1. PulseMCP (the fastest — form, no PR)
1. Go to pulsemcp.com → "Add Server" / Submit
2. Server URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
3. The fields → copy from "Common fields" above
4. Note: they also index from the GitHub readme — link: https://github.com/hristovdimitri2-hub/kristo-intelligence-6

## 2. Glama (glama.ai/mcp/servers)
1. "Add your MCP server" → connect a GitHub account
2. Server endpoint: the SSE URL above; choose transport: SSE/streamable-http
3. Description → from "Common fields"; tags: `base`, `defi`, `x402`, `crypto`, `signals`

## 3. Smithery (smithery.ai)
1. "Publish server" → requires a GitHub repo link
2. If it wants `smithery.yaml` in the repo: transport: sse, the URL above — tell me and I will add it to the repo
3. Tools listing comes from `/api/mcp/manifest` (it already includes /api/v1/signal and /api/arb/opportunities)

## 4. Official MCP Registry (github.com/modelcontextprotocol/registry)
- A heavy procedure (PR + validation) → we do it AFTER 2–3 of the above go through;
  if a `server.json` is needed — tell me, I will generate it.

## Execution order
PulseMCP (5 min) → Glama (5 min) → Smithery (10 min, if it wants yaml — you come back to me) → Registry (later). One a day, if you want to track who indexes when.
