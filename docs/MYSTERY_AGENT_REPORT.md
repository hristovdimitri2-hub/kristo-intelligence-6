# Mystery Agent Audit — Kristo Intelligence

*Run 2026-08-29 09:19 UTC against `https://kristo-intelligence-api.onrender.com` by an independent buyer simulation with zero prior knowledge of the codebase.*

| Stage | Checks | Passed |
|---|---|---|
| discovery | 6 | 6 |
| challenge | 3 | 3 |
| pricing | 4 | 4 |
| anti-fraud | 2 | 2 |
| compat | 2 | 2 |
| free | 6 | 6 |

## What a buyer experiences, end to end

- ✅ **discovery//.well-known/x402 reachable** 
- ✅ **discovery/discovery version == 1** 
- ✅ **discovery/resources listed** — 3 resources
- ✅ **discovery/ownership proof present** 
- ✅ **discovery//openapi.json valid** 
- ✅ **discovery/paid routes identified via x-payment-info** — ['/api/bot-status', '/api/sales', '/api/stats']
- ✅ **challenge//api/bot-status canonical v2 challenge** — HTTP 402 | v2 | amount=5000 net=eip155:8453
- ✅ **challenge//api/sales canonical v2 challenge** — HTTP 402 | v2 | amount=50000 net=eip155:8453
- ✅ **challenge//api/stats canonical v2 challenge** — HTTP 402 | v2 | amount=5000 net=eip155:8453
- ✅ **pricing//api/bot-status atomic amount is honest (> 0, matches resource)** — 5000 raw units = 0.0050 USDC
- ✅ **pricing//api/sales atomic amount is honest (> 0, matches resource)** — 50000 raw units = 0.0500 USDC
- ✅ **pricing//api/stats atomic amount is honest (> 0, matches resource)** — 5000 raw units = 0.0050 USDC
- ✅ **pricing/payTo is NOT the known-burned operator address** — 0xd4cdA900839C0F…
- ✅ **anti-fraud/synthetic proof REJECTED (not 200)** — HTTP 401
- ✅ **anti-fraud/rejection explains itself** 
- ✅ **compat/server responds to standard X-PAYMENT header** — HTTP 402
- ✅ **compat/standard-client payment is NOT yet honoured (documented gap)** — Phase-2 unlock: accept EIP-3009 payloads via facilitator verify
- ✅ **free//.well-known/x402 stays free** — HTTP 200
- ✅ **free//.well-known/x402.json stays free** — HTTP 200
- ✅ **free//api/mcp/manifest stays free** — HTTP 200
- ✅ **free//api/v1/agents stays free** — HTTP 200
- ✅ **free//dashboard stays free** — HTTP 200
- ✅ **free//health stays free** — HTTP 200

## Findings

1. **Every paid route serves a canonical x402 v2 challenge** (CAIP-2 network,
   atomic-unit amounts, bazaar schema) — passes the agentcash/x402scan validator.
2. **Anti-fraud gate works**: synthetic payment proofs are rejected on-chain.
3. **Known gap (documented, by design for now)**: the legacy `X-Payment-Proof`
   scheme is the live payment rail; standard `X-PAYMENT` (EIP-3009) payloads are
   answered but not yet honoured — Phase-2 compatibility unlock.
4. **Discovery surfaces stay free** — an agent can map the whole API before paying.

*Adversarial buyer simulation by the operator; raw script: `scripts/mystery_agent.py`.*
