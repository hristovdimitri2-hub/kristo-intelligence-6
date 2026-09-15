# Kristo Intelligence — Marketing Kit

Ready-to-post content for every channel. Copy, paste, publish. The API is
live 24/7 at https://kristo-intelligence-api.onrender.com

---

## 1. Twitter/X post (EN)

```
🚀 Just launched Kristo Intelligence — an AI-powered DeFi trading signals API
that AI agents pay for autonomously via @coinbase x402 protocol.

⚡ From $0.003 USDC/call on Base. No API keys, no signup — the HTTP 402 response
IS the checkout.

1 free call. Then pay & retry. Live market data, on-chain sales history.

Agents: find us via llms.txt 👇
https://kristo-intelligence-api.onrender.com/llms.txt
```

## 2. Twitter/X post (follow-up, post after 3-5 days)

```
🔥 Our x402 DeFi intelligence API just ran its 1,000th trading-signal cycle.

What agents get:
• /api/stats — live market activity (CoinGecko + DEXScreener + Fear&Greed)
• /api/sales — real on-chain USDC transfer history
• /api/bot-status — bot integration status

curl https://kristo-intelligence-api.onrender.com/api/stats
```

## 3. Reddit r/LocalLLaMA / r/LangChain / r/Base (EN) — B2D target communities

**Title:** I built a pay-per-call DeFi trading signals API on Base — no API keys, agents pay via x402 (HTTP 402)

**Body:**
```
Hey everyone,

I just launched Kristo Intelligence — a DeFi trading signals and market
intelligence API running on Base. The interesting part: it uses the x402
protocol, so there are no API keys and no signup. You call the endpoint,
and if you haven't paid yet, you get HTTP 402 with the exact payment
details (USDC address, amount, chain) in the response body and headers.

Pricing:
- $0.003 USDC per call (/api/v1/signal, /api/v1/whaleflow); $0.005 per call (other routes)
- $29/month VIP — unlimited + Telegram group
- 1 free call to try it

What you get:
- /api/stats — live market activity from CoinGecko, DEXScreener, Fear & Greed index
- /api/sales — real on-chain USDC sales history
- /api/bot-status — Telegram bot status

Try it right now (no signup):
curl https://kristo-intelligence-api.onrender.com/api/stats

It's fully machine-readable too (OpenAPI, llms.txt, MCP manifest, x402
discovery), so AI agents can discover and pay for it autonomously:
https://kristo-intelligence-api.onrender.com/llms.txt

Happy to answer any questions!
```

## 4. Discord — x402 / Coinbase Base dev channels (EN)

```
We just shipped a pay-per-call DeFi intelligence API with x402 on Base 💙

• $0.003-$0.005 USDC/call (per route)
• Real-time market stats (CoinGecko, DEXScreener, Fear & Greed) + real on-chain sales history
• Full machine-readable discovery: x402.json / OpenAPI / MCP / llms.txt
• No API keys — 1 free call, then 402 = pay & retry

Try it: https://kristo-intelligence-api.onrender.com
llms.txt for agents: https://kristo-intelligence-api.onrender.com/llms.txt
```

## 5. Telegram groups (BG/EN mix)

```
🚀 Kristo Intelligence API — DeFi trading сигнали на Base

🤖 AI-powered сигнали + real-time пазарни данни
💰 from $0.003 USDC/call (x402 протокол — без API ключове!)
⭐ VIP: $29/мес — неограничен достъп

1 безплатно извикване:
curl https://kristo-intelligence-api.onrender.com/api/stats

Dashboard: https://kristo-intelligence-api.onrender.com/dashboard
```

## 6. Hacker News / dev.to angle

```
Show HN: An API where the HTTP 402 status code is the checkout

I built a DeFi market intelligence API on Base where payment is handled
entirely at the protocol level. Call the endpoint → get HTTP 402 with the
USDC payment details (receiver address, amount, chain, token contract) in
the response body AND standardized headers (X-Payment-Required,
X-Payment-Address, X-Payment-Amount-USDC). Send USDC on Base, wait ~2
seconds for confirmation, retry the call — you're in. The server watches
the chain via ERC-20 Transfer events; no accounts, no keys, no SaaS
billing. It also ships llms.txt / OpenAPI / an MCP manifest so LLM agents
can discover and transact with it autonomously.

https://kristo-intelligence-api.onrender.com
```

---

## Submission checklist (directories)

| Directory | Status | Link / Action |
|-----------|--------|---------------|
| awesome-x402 | ✅ PR #1308 open | https://github.com/xpaysh/awesome-x402/pull/1308 |
| awesome-mcp-servers | ✅ PR #13219 open (07.09: #12799 CLOSED 29.08 — multiple servers; #11557 CLOSED 07.09 — inactive) | https://github.com/punkpeye/awesome-mcp-servers/pull/13219 |
| Google Search Console | ⬜ manual | Add property → submit https://kristo-intelligence-api.onrender.com/sitemap.xml |
| Bing Webmaster | ⬜ manual | Same sitemap URL |
| CDP x402 Bazaar | ⬜ manual | Mention in Coinbase Base Discord #x402 channel |
| Product Hunt | ⬜ after first customers | Launch when there is social proof |

## Manual action items (only the owner can do these)

1. **Stripe live keys** — Render → Environment → replace `sk_test...` with `sk_live...`
   (unlocks the $29/month VIP card payments — the biggest revenue lever)
2. **Telegram bot token** — @BotFather → /revoke → new token → Render → Environment
   (VIP invite codes are delivered via Telegram)
3. Post items 1–6 above from your own accounts (authentic reach beats automation).
4. Submit the sitemap to Google Search Console.
