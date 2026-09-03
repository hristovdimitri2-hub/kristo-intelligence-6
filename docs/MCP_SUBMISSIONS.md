# MCP SUBMISSIONS — готови пакети за директна регистрация (03.09)

Цел: да не чакаме PayAPI одобрението — Smithery, Glama и PulseMCP приемат
**директни** submissions. Сървърът вече отговаря на всичко нужно: SSE
транспорт, манифест, платени tools. Подателят: hristovdimitri2@gmail.com.

**Общи полета (за всички форми):**
- Name: `kristo-intelligence`
- URL (SSE): `https://kristo-intelligence-api.onrender.com/mcp/sse`
- Manifest: `https://kristo-intelligence-api.onrender.com/api/mcp/manifest`
- OpenAPI: `https://kristo-intelligence-api.onrender.com/openapi.json`
- Description: `Paid DeFi intelligence API on Base: trading-agent signals (action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native: agents pay per call in USDC, from $0.003 — no signup, no API keys.`
- Category: Finance / Market Data
- Pricing note: pay-per-call via x402 protocol (HTTP 402 challenge), $0.003–$0.05

## 1. PulseMCP (най-бързото — форма, без PR)
1. Отиди на pulsemcp.com → „Add Server" / Submit
2. Server URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
3. Полетата → копирай от „Общи полета" горе
4. Бележка: те индексират и от GitHub readme — линк: https://github.com/hristovdimitri2-hub/kristo-intelligence-6

## 2. Glama (glama.ai/mcp/servers)
1. „Add your MCP server" → свържи GitHub акаунт
2. Server endpoint: SSE URL горе; вибери transport: SSE/streamable-http
3. Description → от „Общи полета"; тагове: `base`, `defi`, `x402`, `crypto`, `signals`

## 3. Smithery (smithery.ai)
1. „Publish server" → изисква GitHub repo връзка
2. Ако иска `smithery.yaml` в репото: transport: sse, url горе — кажи ми и ще го добавя в repo-то
3. Tools listing идва от `/api/mcp/manifest` (вече включва /api/v1/signal и /api/arb/opportunities)

## 4. Официален MCP Registry (github.com/modelcontextprotocol/registry)
- Тежка процедура (PR + валидация) → правим я СЛЕД като 2–3 от горе минат;
  при нужда от `server.json` — кажи ми, генерирам го.

## Ред на изпълнение
PulseMCP (5 мин) → Glama (5 мин) → Smithery (10 мин, ако иска yaml — връщаш се при мен) → Registry (по-късно). Едно на ден, ако искаш да следиш кой кога индексира.
