# Content Pack 1 — готови за публикуване

> Тези текстове са писани да се публикуват ТОЧНО така, както са.
> dev.to статията: публикувайте на вашия акаунт (30 сек copy-paste).
> Twitter thread: разпределете туитите един по един.

---

## A) dev.to статья (публикувайте веднага след одобрение на PR-овете)

**Title:** I built an API where the HTTP 402 status code IS the checkout
**Tags:** webdev, api, blockchain, ai

---

What if an API could charge for itself — no API keys, no signup page, no billing dashboard, no accounts? You just call the endpoint, and if you haven't paid, HTTP itself tells you how to pay.

That's exactly what I built: **Kristo Intelligence**, a DeFi trading-signals API on Base where payments happen entirely at the protocol level, using the x402 spec (the "402 Payment Required" HTTP status code, reborn for the agentic web).

## The 30-second demo

```bash
# First call — free tier:
curl https://kristo-intelligence-api.onrender.com/api/stats
# → 200 OK (market data)

# Second call — free tier exhausted:
curl https://kristo-intelligence-api.onrender.com/api/stats
# → 402 Payment Required
```

And here's the magic. The 402 response isn't just an error — it's a complete payment invoice:

```json
{
  "error": "payment_required",
  "payment": {
    "chain": "base",
    "chain_id": 8453,
    "currency": "USDC",
    "receiver_address": "0xd4cdA900...",
    "amount_usdc": 0.05
  }
}
```

Plus standardized headers: `X-Payment-Required`, `X-Payment-Address`, `X-Payment-Amount-USDC`.

Send 0.05 USDC on Base. Wait ~2 seconds. Retry the call. You get your data. That's the entire user experience.

## Why this matters now

AI agents are becoming API consumers. But agents can't fill in signup forms, manage API keys securely, or click through a Stripe checkout. They *can* hold a wallet and send USDC. x402 turns that capability into a complete machine-to-machine economy. My API doesn't know or care whether the caller is a human with curl or an autonomous trading agent — the payment flow is identical.

## The architecture (what's actually running)

The stack is deliberately boring:

- **Flask** app on Render, 1 worker + 8 threads
- **web3.py** for the Base chain integration
- A background thread that watches the fee receiver address via ERC-20 `Transfer` event logs, scanning new blocks every 30 seconds
- **SQLite** (Postgres-ready via env var) for the catalog and CRM

When a payment lands, the monitor decodes the transfer, records it as a sale, and unlocks the caller. Payments above the VIP threshold automatically generate a Telegram VIP invite code.

The interesting engineering problems weren't the payments — they were the operational edge cases:

1. **Flaky public RPC**: Base's public endpoint rate-limits with 429s. My first deploy failed because the health check depended on RPC connectivity. Lesson: liveness probes must check *your* service, not third parties. The monitor now retries forever and resumes from the last scanned block — no payment is ever missed during an RPC hiccup.

2. **Reverse proxies and HTTPS**: Render terminates TLS, so Flask built `http://` URLs in every discovery spec. Werkzeug's `ProxyFix` fixed it — but with `x_for=0`, because trusting client-controlled `X-Forwarded-For` would have broken the free-tier identity tracking.

3. **On-chain payment detection**: polling `eth_getLogs` for Transfer events to your address is simple; doing it reliably across restarts, deploys, and rate limits is the actual product.

## Discovery: teaching agents to find you

An API nobody can find makes no money. So the whole machine-readable surface ships with the app: `/.well-known/x402.json`, `/openapi.json`, `/llms.txt`, `/api/mcp/manifest`, `/agents.json`. An autonomous agent that knows only the domain can crawl these files and reconstruct everything: what it costs, how to pay, what it gets.

## The economics

- $0.05 per call, dropping to $0.01 after 10 paid calls (volume discount encoded in the API logic)
- $29/month VIP: unlimited calls + Telegram group, payable by card (Stripe) or USDC
- 1 free call per client — enough to evaluate, not enough to farm

Is it a business yet? Honestly — not yet. The x402 ecosystem is early. But the marginal cost of serving one more agent is near zero, and every piece of infrastructure is permanent. The bet is that machine-to-machine payments grow, and being early in the directories compounds.

## Try it

```bash
curl https://kristo-intelligence-api.onrender.com/llms.txt
```

The repo is MIT-licensed and documented end-to-end: [hristovdimitri2-hub/kristo-intelligence-6](https://github.com/hristovdimitri2-hub/kristo-intelligence-6)

If you're building on x402 — I'd genuinely love to compare notes. The hardest part isn't the tech; it's discovering what agents actually want to buy.

## B) Twitter thread (6 туита — пускате ден след статията)

**Туит 1 (hook):**
```
I built an API that charges for itself.

No API keys. No signup. No billing dashboard.

The HTTP 402 status code IS the checkout. 🧵
```

**Туит 2:**
```
How it works:

1. Call the endpoint
2. Get HTTP 402 back — with receiver address, amount, chain, token contract in the body
3. Send 0.05 USDC on Base
4. Wait ~2 seconds
5. Retry the call — you're in

That's it. That's the whole UX.
```

**Туит 3:**
```
Why? AI agents are becoming API consumers.

Agents can't:
❌ fill signup forms
❌ manage API keys
❌ click through Stripe checkout

Agents CAN:
✅ hold a wallet
✅ send USDC

x402 turns that into a machine-to-machine economy.
```

**Туит 4:**
```
The engineering that nobody warns you about:

• Public RPCs rate-limit with 429s → liveness probes must not depend on them
• Reverse proxies rewrite your URLs → ProxyFix (but x_for=0, or you break IP identity)
• On-chain detection across restarts → resume from last scanned block, always

Details in the dev.to article 👇
[LINK]
```

**Туит 5:**
```
For AI agents specifically, everything is machine-readable:

/.well-known/x402.json — payment spec
/openapi.json — API contract
/llms.txt — LLM-optimized description
/api/mcp/manifest — MCP integration

An agent that knows only the domain can figure out everything else.
```

**Туит 6 (CTA):**
```
Try it yourself — 1 free call:

curl https://kristo-intelligence-api.onrender.com/api/stats

MIT-licensed, full deployment guide in the repo.

If you're building on @coinbase x402 — let's compare notes. What are agents actually buying? 👇
```

---

## C) Показатели след публикуване (проследявайте 48 часа)

- dev.to: views, reactions, коментари (цел: 200+ views)
- Twitter: impressions, profile visits (цел: 1000+ impressions)
- Render логове: external requests (цел: +20 нови IP)
- Най-важното: първи въпроси/коментари — отговаряйте на ВСЕКИ в рамките на 1 час

---
