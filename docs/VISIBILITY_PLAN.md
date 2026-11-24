# 🌍 KRISTO INTELLIGENCE — 90-day plan for global visibility

> **Goal:** Get the world to discover the API. Every channel, every directory,
> every community.
> **Core:** https://kristo-intelligence-api.onrender.com
> **Motto:** "The bot that pays for DeFi intelligence with 2 HTTP requests."

---

## ⚡ PHASE 0 — FOUNDATION (✅ DONE)

| Asset | Status |
|-------|--------|
| Machine-readable discovery suite (x402.json, OpenAPI, MCP, llms.txt, agents.json) | ✅ Live |
| SEO (robots.txt, sitemap.xml, https URLs) | ✅ Live |
| PR → awesome-x402 (#1308) — 2,4k+ stars | 🟡 Open |
| PR → awesome-mcp-servers (#13219 — clean; #12799 CLOSED 29.08) — 60k+ stars | 🟡 Open |
| GitHub repo topics + description + homepage | ✅ Live |
| Discord webhook announcements | ✅ Sent |
| Marketing kit (docs/MARKETING_KIT.md) | ✅ Live |
| Telegram bot @kristointelbot | ✅ Active |
| Stripe LIVE + x402 on-chain payments | ✅ Active |

---

## 🔥 PHASE 1 (Days 1–14): DIRECTORY DOMINANCE

**Principle:** Every place where AI agents and devs look for paid APIs — we must be
there. This is the highest-converting traffic.

### Days 1–3 — Glama + MCP registries (CAN BE STARTED IMMEDIATELY)
| # | Channel | URL | Action | Who |
|---|-------|-----|----------|-----|
| 1 | **Glama.ai MCP** | https://glama.ai/mcp/servers | Submit server for evaluation → quality score badge. The Glama bot is already inviting us in PR #12799! | You (account) |
| 2 | **Smithery.ai** | https://smithery.ai | Registry for MCP servers — huge traffic from Claude/Cursor users | You (account) |
| 3 | **mcp.run** | https://mcp.run | MCP registry from the Cloudflare community | You (account) |
| 4 | **PulseMCP** | https://www.pulsemcp.com | MCP directory + newsletter (30k+ subscribers) | You (account) |

### Days 3–7 — the x402 ecosystem (the hottest traffic)
| # | Channel | Action | Who |
|---|-------|----------|-----|
| 5 | **CDP x402 Bazaar** (Coinbase) | The bot from the PR mentioned "Indexed on Bazaar" — we submit ourselves to the official Coinbase directory: https://www.cdp.ai / Bazaar listing via Base Discord #x402 | You + me (I'm preparing the text) |
| 6 | **agentic.market** | Agentic marketplace — other x402 services are there | You (account) |
| 7 | **Base Discord #x402 channel** | Post with a curl demo (the text is in MARKETING_KIT.md §4) | You (5 min) |
| 8 | **orbisapi.com** | API directory, seen in competitor entries | You (account) |

### Days 7–14 — First social waves
| # | Channel | Action | Who |
|---|-------|----------|-----|
| 9 | **Twitter/X** | Launch post (MARKETING_KIT §1) + tag @coinbasedev, @x402org | You |
| 10 | **Reddit r/LocalLLaMA** (300k+ AI devs) | The technical post (MARKETING_KIT §3) | You |
| 11 | **Reddit r/LangChain + r/Base** | The same post, adapted | You |
| 12 | **Reddit r/mcp** | The MCP community is looking for exactly such servers | You |

**KPI for the phase:** 12 directories/channels activated.

---

## 📝 PHASE 2 (Days 14–30): CONTENT ENGINE

**Principle:** Directories give the initial push; content sustains the flow.

| # | Asset | Format | Who |
|---|-------|--------|-----|
| 13 | DONE: published as npm package `kristo-x402-client` + demo repo | **dev.to article** | "How I built an API where HTTP 402 is the checkout" — technical deep-dive post (Ghost = HN prep). I write the draft IMMEDIATELY (see below). | I write → you publish |
| 14 | **Hacker News Show HN** | After 2-3 days of social proof → Show HN (MARKETING_KIT §6). Critical: honest tone, no marketing talk. | You |
| 15 | **Twitter thread (6 tweets)** | Breakdown of the architecture with diagrams: 402 flow, on-chain monitor, agent discovery. I write the thread. | I write → you post |
| 16 | **GitHub README badges** | Live status badge + x402 badge + Glama score (after registration) — makes the repo sellable at first glance | ✅ Me (done today) |
| 17 | **LinkedIn post** | B2B angle: "Monetizing APIs for the agentic web" | You |

---

## 🔄 PHASE 3 (Month 2): COMMUNITY ENGAGEMENT LOOP

**Principle:** No spam — presence. 30 minutes a day, every day.

| Asset | Cadence | Channels |
|-------|-------|--------|
| Answering questions about x402/MCP/Base | Daily | Base Discord, x402 Discord, r/BaseChain, r/mcp |
| "Built with x402" demo tweets | 2×/week | Twitter (short screen recordings of the dashboard) |
| Improvements based on user signals | Weekly | Git commits → show activity in the directories |
| Newsletter comments (Bankless, The Defiant) | On occasion | When the topic is x402/agents — we comment with experience |

---

## 🚀 PHASE 4 (Month 3): SCALING

| # | Asset | Condition |
|---|-------|---------|
| 18 | **Product Hunt launch** | After ≥3 social proof points (payment, stars, Reddit upvotes) |
| 19 | **Pitch to crypto media** (Bankless, The Defiant, CoinDesk) | After the first real revenue — we have a story |
| 20 | **Affiliate/referral program** | 20% for every referred VIP — code in main.py |
| 21 | **YouTube dev video** | "Adding x402 payments to your API in 10 minutes" with Kristo as an example |

---

## 📊 METRICS (we check every week)

| Metric | Source | Goal Month 1 | Goal Month 3 |
|---------|--------|-------------|-------------|
| External requests/day | Render logs (excluding keep-alive IPs) | 20+ | 200+ |
| Approved directories | PR merges + registrations | 5 | 12 |
| Telegram active chats | /api/bot-status | 3 | 30 |
| First payment | check_revenue.py + Stripe | 1 | 10+ |
| VIP subscribers | Stripe dashboard | 0–1 | 3–5 |

**Weekly check command:**
```
curl -s https://kristo-intelligence-api.onrender.com/api/stats
cd <local-path>
venv\Scripts\python.exe scripts\check_revenue.py
```

---

## ⚠️ IRON RULES

1. **We never spam** — one post per channel, then we answer the comments.
2. **Every mention of competitors is respectful** — the community is small,
   reputation is everything.
3. ** Every question from a bot/dev = priority №1** — the first paying client
   comes from a person we helped.
4. **Honesty at 402:** We always say that we are new and small — authenticity
   converts better than gloss.
