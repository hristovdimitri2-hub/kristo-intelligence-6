# OUTREACH KIT — свързване с платформената екосистема (29.08.2026)

Всичко по-долу е готово за изпращане. Копирай, попълни [ИМЕ], пращай от
hristovdimitri2@gmail.com. Редът е по приоритет.

---

## 1. BlockRun — "List a data source" (НАЙ-ВАЖНОТО)

**До:** контакта от blockrun.ai → "List a data source" (onboard-ват niche APIs седмично)
**Тема:** `Data source listing: DeFi signals API on Base (x402 v2, live)`

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

## 2. AgentCash router (дистрибуция през втората тръба)

**Тема:** `x402 server for your router: DeFi data on Base (v2-ready)`

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

## 3. PayAPI.market — resubmission (10 минути, направи го СИ)

1. Отиди на payapi.market → "List your API" (или resubmit от акаунта)
2. URL: `https://kristo-intelligence-api.onrender.com`
3. Receiver: `0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f`
4. Бележка към тях: *"Resubmission: strict-402 is live (every unpaid call
   returns the challenge) and challenges now follow the x402 v2 canonical
   format (CAIP-2, atomic units). Prior submission failed on the legacy
   format — fixed in commits 2b4d5ad..d6eeb12."*

---

## 4. MCP Registry (официалният регистър на Anthropic)

Регистрирай MCP сървъра на https://github.com/modelcontextprotocol/registry
(или през Claude → Settings → Connectors за директна употреба):
- Name: `kristo-intelligence`
- Transport: SSE, URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
- Manifest: `https://kristo-intelligence-api.onrender.com/api/mcp/manifest`
- Description: paid DeFi data tools (whale/arb/rug/stats) via x402

---

## 5. Петте персонални съобщения (dev общности — пращай 1/ден, персонализирай [X])

**a) GitHub (dev с Base trading бот):**
> Saw [X] — solid. I run a live DeFi signals API on Base (whale USDC flows,
> cross-DEX arb spreads, rug checks) — pay-per-call x402, from $0.003. One
> curl and you're in: https://kristo-intelligence-api.onrender.com/.well-known/x402

**b) Telegram crypto-dev канал:**
> Всеки, който строи бот за Base? Пуснах платено API: whale движения, arb
> спредове (обновяване на 60s), rug проверки. x402 плащане, от $0.003/заявка.
> Live: kristo-intelligence-api.onrender.com — ето discovery-то, пробвай с 1 curl.

**c) X/Twitter (агент builders):**
> Agents pay for LLM tokens. Why not for market data? DeFi signals on Base,
> x402-native, from $0.003/call, no signup. Discovery is one GET:
> https://kristo-intelligence-api.onrender.com/.well-known/x402

**d) r/BaseFi / Base ecosystem Discord:**
> Built a pay-per-call DeFi data API on Base (x402 protocol): whale USDC
> tracking, live arb spreads, rug scanners. Free discovery, paid data,
> from $0.003/call. Feedback welcome — especially from bot devs.

**e) Отговор на съответен въпрос в x402 Discord/форум (намери нишка за
"where to get market data for agents"):**
> Shameless plug: I run exactly that — DeFi signals API on Base via x402.
> Self-describing 402s, so any x402 client can consume it without reading
> docs: https://kristo-intelligence-api.onrender.com/.well-known/x402

---

## 6. PayAPI blurb за Chet Parker (@ParkerChet) — по негова покана (03.09)

Chet потвърди (email 14:15 UTC, 03.09): няма платено слот/newsletter; има (а) live каталог + agent search, (б) listing страницата, (в) окупационни X постове от @ParkerChet при ново verified нещо. Blurb „on file" е пожелателен — **tight: какво връща GET /api/v1/signal, цена, Base USDC**. Готов за paste в reply:

> **Kristo Intelligence — DeFi Signals API** (verified, PayAPI Market)
>
> GET /api/v1/signal returns the latest output of a live trading agent on Base: for each of ETH, ONDO, KAITO and DEGEN it gives an action (accumulate / monitor / small-allocation style), a 0–1 confidence score, the current USD price, and a one-line reasoning — sorted by confidence, refreshed continuously against live market data. No signup: standard x402 402 challenge, pay per call.
>
> Price: $0.003 per call, settled in Base USDC. Verified by two independent paid canaries on this route; discovery at /.well-known/x402.

Кратка версия (ако иска още по-тясна, 1 изречение):

> GET /api/v1/signal — live trading-agent calls (action + confidence + price + reasoning) for ETH/ONDO/KAITO/DEGEN on Base, $0.003/call in Base USDC via x402, no signup: https://payapi.market/api/kristo-intelligence-defi-signals-api

Правило от Chet: постне Kristo в X само ако маршрутът е полезен — не моли за пост, остави blurb-а да говори.

---

## 7. Outreach Дни 3–5 — конкретни текстове (03.09)

**Ден 3 — собствен X пост (НЕ чакаме Chet; merit-ът е наш):**
> Agents pay for LLM tokens. Why not for market data?
>
> Kristo Intelligence: live DeFi signals API on Base — trading-agent calls (action + confidence + price + reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX arb spreads, whale USDC tracking. x402-native, from $0.003/call, no signup.
>
> One GET to see everything: https://kristo-intelligence-api.onrender.com/.well-known/x402
> Verified: 4 paid canaries settled on-chain via @ParkerChet's PayAPI Market.

**Ден 4 — Telegram crypto-dev канал (шаблон b, персонализиран):**
> Всеки, който строи бот за Base? Пуснах платено API: trading сигнали (ETH/ONDO/KAITO/DEGEN с reasoning + confidence), arb спредове (60s), rug проверки. x402 плащане, от $0.003/заявка — без регистрация, агентът си плаща сам с USDC.
> Live: kristo-intelligence-api.onrender.com — discovery с 1 curl: /.well-known/x402

**Ден 5 (07.09) — BlockRun follow-up до @1bcmax (ако мълчи):**
> Hi Max — following up on the listing question from the other day. No rush on my side: if a data-source listing isn't a priority for BlockRun right now, just say so and I'll close the topic cleanly. If it is, the fastest path is the same endpoints we discussed (whale/arb/rug/signals, x402 v2 verified, 4 on-chain settlement proofs). Either answer works — I'd just rather not leave it hanging.

(Ако и това мълчи — затворена тема, усилието отива в MCP директориите.)

**X версия — data-story (актуализирана 04.09; статията е в repo-то):**
> I audited the on-chain economy of a machine-payments API marketplace.
>
> Every paid call settles publicly — so I mapped who pays whom, how ranking works, and when the platform's crawlers run.
>
> Findings: top listing = $0.29/week; most "payers" are sampling infrastructure, not customers; exactly ONE real agent-trader (buys data at $0.002/call, routes swaps through a DEX router). Whole observed market: ~$1.2/month.
>
> Full audit (no wallet addresses, numbers dated):
> github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/docs/MARKET_WRITEUP.md
>
> (I build one of the listings — DeFi signals, x402/USDC on Base. Demo agent: one command, watch an agent pay.)

*(Опционално — основният канал е линкът към Chet. Същата дисциплина: нула wallet адреси, неутрално към платформата.)*

---

## Правила на кампанията
- 1 съобщение/ден, персонализирано — спам-маскиране убива репутацията в малка екосистема
- Всеки отговор → отговори в рамките на час
- Всяко "не" → попитай "какво би те накарало да го листнеш?" — това е продуктово проучване
