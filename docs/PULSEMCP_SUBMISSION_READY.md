# PULSEMCP — готово за подаване (НЕ е подадено)

**Проверено на живо:** 2026-09-17 · read-only, нищо не е пращано.

## Статус (факти, не очаквания)

| проверка | резултат |
|---|---|
| Търсене `pulsemcp.com/servers?q=kristo` | **НЕ сме там** — 5 резултата, всички чужди (`kjozsa-git`, `kjozsa-jenkins`, `krzko-google-cloud`, `kristofferstrube-blazor-webmcp`, `agentcrush`) |
| `pulsemcp.com/submit` | **„submissions and changes are temporarily paused“** · *Last updated: September 3, 2026* |
| Банер на `/servers` | „New server submissions and listing changes are **still paused** while we rework how we ingest and manage listings.“ |
| Техният `/api` (източници на директорията) | Manual submissions · automated scraping · **„Integration with the Official MCP Registry“** |
| Нашият Registry запис (каналът, който те четат) | **v6.0.0 · isLatest=True · active** · `/mcp` + `/mcp/sse` · repo `kristo-intelligence-6` · pricing 0.003–0.005 USDC |
| Директорията им | 21 880 сървъра (Last Update на `/servers`) |

⇒ **Автоматично взимане от Registry-то все още не се е случило** (ние сме в Registry от
17.09). Формата им е затворена, затова **не се подава нищо** — готовата заявка чака.

## Какво прави собственикът (на ръка)

1. **Провери банера** на `pulsemcp.com/servers`: щом текстът „still paused" изчезне, формата
   е отворена. (Ако вече си получил съобщение, че са отворили — това е по-силен сигнал от
   кеширана страница; тогава мини направо на т.3.)
2. **Провери и Registry-то** (те взимат оттам): ако сме се появили в PulseMCP сами след
   връщането — **нищо не се подава**, само сверяваш данните (т.4).
3. **Отвори `pulsemcp.com/submit`** и попълни от блока по-долу (копи-пейст, полетата им
   може да са с други имена — текстът е един и същ).
4. **Сверка на данните** (след като се появим, автоматично или ръчно):
   - URL = `https://kristo-intelligence-api.onrender.com/mcp` ✅
   - tools = `get_market_stats`, `get_onchain_sales`, `get_bot_status` (3) ✅
   - цени = **$0.003–$0.005** (`X402_PRICE_MAP`; нула „$0.05", нула „1 free call") ✅
   - repo = `hristovdimitri2-hub/kristo-intelligence-6` ✅

---

## Копи-пейст блок за формата

**Name**
```
Kristo Intelligence
```

**URL (remote MCP endpoint)**
```
https://kristo-intelligence-api.onrender.com/mcp
```

**Repository**
```
https://github.com/hristovdimitri2-hub/kristo-intelligence-6
```

**Short description** (от готовия листинг, ≤160 знака)
```
DeFi market intelligence API for AI agents on Base. Six x402 endpoints, paid per call in USDC from $0.003: signals, whale flow, arbitrage, on-chain sales.
```

**Long description** (от готовия листинг `kristo-agentic-market-final.md`)
```
Machine-readable DeFi intelligence for AI agents that trade autonomously. MCP server (Streamable HTTP + SSE on /mcp) exposing three tools — get_market_stats, get_onchain_sales, get_bot_status — over six paid GET routes, JSON only:

- /api/v1/signal — action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN; 8-agent engine.
- /api/v1/whaleflow — USDC transfers >= $50k on Base with labeled counterparties and the scanned-block watermark.
- /api/stats — market snapshot (CoinGecko, DEXScreener, Fear & Greed) + daily aggregates.
- /api/sales — on-chain verified USDC sales history for this API (ERC-20 Transfer monitoring).
- /api/arb/opportunities — cross-DEX spreads on Base, 60s refresh.
- /api/bot-status — service and integration counters.

Payment is x402: no signup, no API keys. Unpaid calls return HTTP 402 with the exact USDC amount and receiver; the agent pays on Base (chain 8453) and retries. Prices: $0.003–$0.005 per call.

Chain-truth: sales figures come from the chain, not from RAM, and every number states the block it came from. If a scan has not run, the feed says so. No projections.
```

**Category**
```
Trading
```

**Transport / compatibility**
```
Streamable HTTP + SSE (MCP 2025-11-25)
```

**Tags**
```
defi, base, x402, usdc, market-data, payments, agents
```

**Contact**
```
hristovdimitri2@gmail.com
```

---

## Защо този текст (и защо е безопасен)

- Описанието е **същото**, което вече е стъпило на Glama и Smithery — без нови числа.
- Цените идват от `X402_PRICE_MAP` (единствен източник): `/api/v1/signal` и
  `/api/v1/whaleflow` = $0.003; `/api/stats`, `/api/sales`, `/api/arb/opportunities`,
  `/api/bot-status` = $0.005. **Нула фантоми**: без „$0.05/call", без „1 free call"
  (production работи с `KRISTO_FREE_TIER_LIMIT=0` — всяко неплатено извикване връща 402).
- Никакви wallet адреси, ключове или вътрешни детайли в текста за подаване.
- Sweep-тестът (`tests/test_price_sweep.py`) пази тези твърдения срещу регресия.