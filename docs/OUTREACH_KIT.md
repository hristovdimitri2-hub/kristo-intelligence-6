# OUTREACH KIT — connecting with the platform ecosystem (29.08.2026)

Everything below is ready to send. Copy it, fill in [NAME], send it from
<contact-email>. The order is by priority.

---

## 1. BlockRun — "List a data source" (THE MOST IMPORTANT ONE)

**To:** the contact from blockrun.ai → "List a data source" (they onboard
niche APIs weekly)
**Subject:** `Data source listing: DeFi signals API on Base (x402 v2, live)`

> Hi BlockRun team,
>
> I run Kristo Intelligence — a live DeFi data API on Base, settled via
> x402 v2 (canonical challenges, atomic-unit amounts, bazaar schema — your
> validator accepts all 3 paid routes).
>
> What I'd list as BlockRun data tools:
> - **Whale Flow** — large USDC transfer tracking on Base ($0.01/call)
> - **Arb Radar** — live cross-DEX arbitrage spreads, refreshed every 60s ($0.005/call)
> - **Rug/Tokens scanner** — pre-trade safety checks ($0.003/call)
> - **Market stats** — aggregated Base DeFi activity ($0.005/call)
>
> Endpoints are live at https://kristo-intelligence-api.onrender.com —
> discovery via /.well-known/x402 and /openapi.json, x402scan lists all
> 11 resources. An independent mystery-agent audit (23/23 checks) passed
> this week: https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/MYSTERY_AGENT_REPORT.md
>
> Happy to align on the integration shape you prefer (your data-tool
> contract, pricing split, or rev-share). We onboard fast.
>
> Dimitri — Kristo Intelligence

---

## 2. AgentCash router (distribution through the second pipe)

**Subject:** `x402 server for your router: DeFi data on Base (v2-ready)`

> Hi agentcash team,
>
> Kristo Intelligence (https://kristo-intelligence-api.onrender.com) is an
> x402 v2 server — DeFi signals, whale tracking and arb spreads on Base.
> Your discovery audit passes clean (11 routes, 3 paid, canonical v2
> challenges verified with @agentcash/discovery 1.7.5).
>
> Would you include it in the router's server pool? Paid routes: /api/stats,
> /api/sales, /api/bot-status — everything an agent needs to pay and retry
> is self-contained in the 402 body.
>
> — Dimitri, Kristo Intelligence

---

## 3. PayAPI.market — resubmission (10 minutes, do it YOURSELF)

1. Go to payapi.market → "List your API" (or resubmit from the account)
2. URL: `https://kristo-intelligence-api.onrender.com`
3. Receiver: `0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844`
4. Note to them: *"Resubmission: strict-402 is live (every unpaid call
   returns the challenge) and challenges now follow the x402 v2 canonical
   format (CAIP-2, atomic units). Prior submission failed on the legacy
   format — fixed in commits 2b4d5ad..d6eeb12."*

---

## 4. MCP Registry (Anthropic's official registry)

Register the MCP server at https://github.com/modelcontextprotocol/registry
(or via Claude → Settings → Connectors for direct use):
- Name: `kristo-intelligence`
- Transport: SSE, URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
- Manifest: `https://kristo-intelligence-api.onrender.com/api/mcp/manifest`
- Description: paid DeFi data tools (whale/arb/rug/stats) via x402

---

## 5. The five personal messages (dev communities — send 1/day, personalize [X])

**a) GitHub (dev with a Base trading bot):**
> Saw [X] — solid. I run a live DeFi signals API on Base (whale USDC flows,
> cross-DEX arb spreads, rug checks) — pay-per-call x402, from $0.003. One
> curl and you're in: https://kristo-intelligence-api.onrender.com/.well-known/x402

**b) Telegram crypto-dev channel:**
> Anyone building a bot for Base? I launched a paid API: whale movements, arb
> spreads (refreshed every 60s), rug checks. x402 payment, from
> $0.003/request. Live: kristo-intelligence-api.onrender.com — here's the
> discovery, try it with 1 curl.

**c) X/Twitter (agent builders):**
> Agents pay for LLM tokens. Why not for market data? DeFi signals on Base,
> x402-native, from $0.003/call, no signup. Discovery is one GET:
> https://kristo-intelligence-api.onrender.com/.well-known/x402

**d) r/BaseFi / Base ecosystem Discord:**
> Built a pay-per-call DeFi data API on Base (x402 protocol): whale USDC
> tracking, live arb spreads, rug scanners. Free discovery, paid data,
> from $0.003/call. Feedback welcome — especially from bot devs.

**e) Reply to a relevant question in the x402 Discord/forum (find a thread about
"where to get market data for agents"):**
> Shameless plug: I run exactly that — DeFi signals API on Base via x402.
> Self-describing 402s, so any x402 client can consume it without reading
> docs: https://kristo-intelligence-api.onrender.com/.well-known/x402

---

## 6. PayAPI blurb for Chet Parker (@ParkerChet) — at his invitation (03.09)

Chet confirmed (email 14:15 UTC, 03.09): there is no paid slot/newsletter;
there is (a) a live catalog + agent search, (b) the listing page, (c)
occasional X posts from @ParkerChet when something new is verified. A blurb
"on file" is desirable — **tight: what GET /api/v1/signal returns, price,
Base USDC**. Ready to paste in a reply:

> **Kristo Intelligence — DeFi Signals API** (verified, PayAPI Market)
>
> GET /api/v1/signal returns the latest output of a live trading agent on
> Base: for each of ETH, ONDO, KAITO and DEGEN it gives an action
> (accumulate / monitor / small-allocation style), a 0–1 confidence score,
> the current USD price, and a one-line reasoning — sorted by confidence,
> refreshed continuously against live market data. No signup: standard x402
> 402 challenge, pay per call.
>
> Price: $0.003 per call, settled in Base USDC. Verified by two independent
> paid canaries on this route; discovery at /.well-known/x402.

Short version (if he wants an even tighter one, 1 sentence):

> GET /api/v1/signal — live trading-agent calls (action + confidence + price
> + reasoning) for ETH/ONDO/KAITO/DEGEN on Base, $0.003/call in Base USDC
> via x402, no signup:
> https://payapi.market/api/kristo-intelligence-defi-signals-api

Rule from Chet: Kristo posts on X only if the route is useful — don't ask
for a post, let the blurb speak.

---

## 7. Outreach Days 3–5 — concrete texts (03.09)

**Day 3 — own X post (we are NOT waiting for Chet; the merit is ours):**
> Agents pay for LLM tokens. Why not for market data?
>
> Kristo Intelligence: live DeFi signals API on Base — trading-agent calls
> (action + confidence + price + reasoning for ETH/ONDO/KAITO/DEGEN),
> cross-DEX arb spreads, whale USDC tracking. x402-native, from $0.003/call,
> no signup.
>
> One GET to see everything: https://kristo-intelligence-api.onrender.com/.well-known/x402
> Verified: 4 paid canaries settled on-chain via @ParkerChet's PayAPI Market.

**Day 4 — Telegram crypto-dev channel (template b, personalized):**
> Anyone building a bot for Base? I launched a paid API: trading signals
> (ETH/ONDO/KAITO/DEGEN with reasoning + confidence), arb spreads (60s), rug
> checks. x402 payment, from $0.003/request — no registration, the agent
> pays on its own with USDC.
> Live: kristo-intelligence-api.onrender.com — discovery with 1 curl: /.well-known/x402

**Day 5 (07.09) — BlockRun follow-up to @1bcmax (if he stays silent):**
> Hi Max — following up on the listing question from the other day. No rush
> on my side: if a data-source listing isn't a priority for BlockRun right
> now, just say so and I'll close the topic cleanly. If it is, the fastest
> path is the same endpoints we discussed (whale/arb/rug/signals, x402 v2
> verified, 4 on-chain settlement proofs). Either answer works — I'd just
> rather not leave it hanging.

(If this one stays silent too — closed topic, the effort goes into the MCP
directories.)

**X version — data-story (updated 04.09; the article is in the repo):**
> I audited the on-chain economy of a machine-payments API marketplace.
>
> Every paid call settles publicly — so I mapped who pays whom, how ranking
> works, and when the platform's crawlers run.
>
> Findings: top listing = $0.29/week; most "payers" are sampling
> infrastructure, not customers; exactly ONE real agent-trader (buys data at
> $0.002/call, routes swaps through a DEX router). Whole observed market:
> ~$1.2/month.
>
> Full audit (no wallet addresses, numbers dated):
> github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/MARKET_WRITEUP.md
>
> (I build one of the listings — DeFi signals, x402/USDC on Base. Demo
> agent: one command, watch an agent pay.)

*(Optional — the main channel is the link to Chet. The same discipline:
zero wallet addresses, neutral toward the platform.)*

---

## Campaign rules
- 1 message/day, personalized — spam-masking kills reputation in a small
  ecosystem
- Every reply → answer within an hour
- Every "no" → ask "what would make you list it?" — that's product research
