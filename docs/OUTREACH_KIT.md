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

## Правила на кампанията
- 1 съобщение/ден, персонализирано — спам-маскиране убива репутацията в малка екосистема
- Всеки отговор → отговори в рамките на час
- Всяко "не" → попитай "какво би те накарало да го листнеш?" — това е продуктово проучване
