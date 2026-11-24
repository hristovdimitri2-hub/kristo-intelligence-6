# Kristo Demo Agent — public reference x402 client

Demonstrates the COMPLETE path of a paid call in 3 steps — this is the entire
integration: no signup, no API keys, no libraries on our side.

```
python examples/demo_agent/demo_agent.py                      # discovery + 402 challenge (safe, without wallet)
python examples/demo_agent/demo_agent.py --endpoint /api/v1/signal
python examples/demo_agent/demo_agent.py --pay                # REAL payment: DEMO_PRIVATE_KEY=funded test wallet
```

## What it does
1. **Discovery** — GET `/.well-known/x402` (free): all paid resources
2. **Challenge** — GET paid endpoint → HTTP 402 with x402 v2 challenge
   (scheme, network, amount in atomic units, payTo, description)
3. **Pay & retry** — sends the exact amount of USDC on Base to `payTo`, waits for
   confirmations, retry with `X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))`
   → 200 with the data

> **Two payment rails — and one is faster.**
> The demo shows the **smart-wallet** rail because it is easiest to explain with a
> simple transfer. However, it requires **3 confirmations (≈6 seconds)** between the
> payment and the data.
> The **preferred** rail is standard x402: you sign EIP-3009
> `transferWithAuthorization` and retry with `PAYMENT-SIGNATURE` (x402 v2;
> `X-PAYMENT` for v1 clients). The facilitator settles — no waiting for a block.
> Both return the data; the choice is how fast you want it.

## Why it is public
- **Proof:** anyone can run the client and see a working
  payment from their own machine — trust through reproduction, not promises
- **E2E test:** step 3 with a real wallet is exactly the E2E self-paid test
- **Template:** agent builders copy `parse_challenge()` + the payment header
  directly into their code — both rails are described above

⚠️ Never use a production private key. `--pay` is for a funded test
wallet with micro-amounts (0.003–0.005 USDC; the 402 challenge states the exact amount).

**Listing:** [Kristo Intelligence — DeFi Signals API on PayAPI Market](https://payapi.market/api/kristo-intelligence-defi-signals-api) — settlement-verified, $0.003/call, USDC on Base.

**Discover via PayAPI MCP** - agents already connected to the market's
warehouse find our routes on both sides:

```json
{
  "mcpServers": {
    "payapi": {
      "url": "https://payapi.market/mcp"
    }
  }
}
```
