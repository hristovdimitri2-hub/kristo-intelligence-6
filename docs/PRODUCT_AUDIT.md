# ОДИТ: Продукт и конкурент (07.09, read-only + тестове)

Нула промени по кода. payTo/endpoint недокоснати. 164/164 PASS.

## ЧАСТ A — Свежестта на хляба

### A1. Какво всъщност продаваме: две категории продукт

**Категория 1 — РЕАЛНИТО (5 платени x402 endpoints + MCP):**
`/api/stats`, `/api/sales`, `/api/bot-status`, `/api/arb/opportunities`,
`/api/v1/signal` + MCP (SSE + Streamable HTTP, 3 инструмента). Тук живеят
истинските данни.

**Категория 2 — 8-те каталог SKU** (`integrations/catalog_store.py`):
whaleflow-radar, cross-venue-signal-divergence, token-launch-rug-risk-scanner,
defi-yield-risk-optimizer, gas-route-optimizer, ai-sentiment-narrative-pulse,
smart-contract-security-triage, signal-to-channel-publisher.

### A2. 🔴 ГЛАВНАТА НАХОДКА: 8-те SKU = витрина без продукт зад нея

**Доказателство (код):**
- `main.py:2440` — `_run_catalog_agent_demo(agent, user_input)` се изпълнява
  **БЕЗУСЛОВНО**, дори когато клиентът е платил и е подал валиден entitlement
  token (редове 2437–2440: token се верифицира, но резултатът е пак демото;
  само етикетът става „active_entitlement").
- `main.py:1465–1492` — демото връща хеш на входа + статични стъпки:
  „Demo workflow completed… does not claim a live trading recommendation",
  `upgrade_required_for_live_access: true`.
- `main.py:2547–2572` — `/access` връща САМО подписан token (entitlement), не
  живи данни. Няма друг execution път за SKU-тата.

**Присъда за 8-те SKU: МЪРТВИ като продукт.** Живи като източник — нито един.
Клиент, платил $12–19 (Stripe) за каквото и да е от тях, получава същото демо
като безплатния вик. За същите пари в нашите x402 endpoints купува реални данни.

### A3. Източник на данни + последен РЕАЛНО нов сигнал — по реални продукти

| Продукт | Източник | Последен РЕАЛНО нов сигнал | Присъда |
|---|---|---|---|
| **/api/v1/signal** ($0.003) | CoinGecko (на 5 мин, агент loop) + DeFiSignalGenerator (Base44-насочен) | 4-та канарка на Chet: price в 0.13% от CoinGecko, БЕЗ stale бележка (05.09); покупката на 0x4dB7 (06.09) — сигнал route | **ЖИВ** |
| **/api/stats** ($0.005) | CoinGecko + DEXScreener + Fear&Greed (кеш TTL 15 мин) | market_data на живо: CoinGecko age 290 сек, AERO $0.5667 +4.57%, F&G 71 „Greed" (07.09) | **ЖИВ** |
| **/api/arb/opportunities** ($0.005) | DEXScreener крос-DEX скенер (scan на всеки 60 сек, min_spread филтър) | сканира активно (ARB_SCAN_INTERVAL=60s); тела не е видимо без плащане | **ЖИВ** (скромно — спредите на Base са тънки) |
| **/api/sales** ($0.05) | Реален on-chain USDC Transfer scan (твърд детерминизъм) | 5 транфера общо, последното 06.09 | **ЖИВ** (макар и с бедна история) |
| **/api/bot-status** ($0.005) | Вътрешно състояние на бота (webhook-only) | heartbeat/uptime — непрекъснато | **ЖИВ**, но е статystics, не intelligence |
| **8-те SKU** | НЯМА източник — демо адаптер | никога няма жив сигнал | **МЪРТВИ** |

### A4. Тестове на маршрути (07.09, живо)

| Тест | Резултат | Съответствие с README |
|---|---|---|
| POST playground whaleflow-radar (безплатен) | 200: `mode: playground_demo`, „Demo workflow completed… does not claim a live trading recommendation" | ❌ README/catalog описват „signals with confidence" — реалният отговор е демо без данни |
| POST playground gas-route-optimizer | 200: същото демо | ❌ същото разминаване |
| POST playground ai-sentiment-narrative-pulse | 200: същото демо | ❌ същото разминаване |
| GET /api/stats | 402 (строг x402 — KRISTO_FREE_TIER_LIMIT=0 на Render) | ✅ семантиката е коректна |
| GET /api/v1/signal | 402, amount: 0.003 | ✅ цената отговаря |

### A5. ФОРЕНЗИКА: какво получи 0x4dB7 за $0.003 (06.09 06:41:03 UTC)

**Какво знаем сигурно:**
- Кой endpoint: **GET /api/v1/signal** — единственият при $0.003 (SALE_DIAGNOSIS).
- Формат на отговора: {token, action, confidence, price_usd, reasoning, note}
  — верифициран 4 пъти от платените канарки на Chet (numeric price_usd,
  reasoning с основен драйвер, без stale penalty след фикс-а).
- Свежест в момента на покупката: агент loop-ът опреснява на всеки 5 мин от
  CoinGecko; на 06.09 loop-ът е бил активен (продажбата записана в dashboard).
- Платецът: умерен multi-API оператор (100 payTo/30d, 145 tx, $1.67) — знае
  какво купува, не е случайна рыбка.

**Какво е загубено (не може да се възстанови):**
- **Точното тяло** на отговора (кой токен, коя цена, кой reasoning) — беше в
  RAM `_latest_signals`, нулирано от deploys през деня; телата на отговорите
  не се логват. Ако 0x4dB7 се върне, следващия път ще можем да логваме
  тела (по решение — PII-безопасно: токен/цена/confidence без никого).

**Присъда:** купеният продукт беше ЖИВ и верифицируем; точните стойности са
невъзвратими, но структурата и свежестта са доказани от канарките.

## ЧАСТ B — Хлябът на съседите

### B1. Тест-покупки: БЛОКИРАНИ — hot wallet-ът е празен

| Баланс на hot wallet `0x9c1eb9…750dd` (проверено on-chain 07.09) | Стойност |
|---|---|
| ETH (gas на Base) | **0.000000** |
| USDC | **0.000000** |

За 1-2 покупки (Currency API $0.001 × 2 или loopA $0.021) трябва:
**≥ $0.05 USDC + ~0.0001 ETH за gas** (~$0.03) на hot wallet-а. След
зареждане рецептът: GET → 402 → плащане (EIP-3009 PAYMENT-SIGNATURE
или tx-hash rail според challenge-а) → retry → запис на tx. Скриптът е
10 реда с нашия web3 — чака funded wallet. **Нищо не е купено днес.**

### B2. Съсед #1 (проучен без плащане, read-only): Currency & Crypto API

| Поле | Стойност |
|---|---|
| Кой е | **HOUSE листинг** — provider_name: „PayAPI Market" |
| Цена | **$0.001 flat** (5 endpoints: /rates/latest, /rates/convert, /rates/historical, /crypto/price, /crypto/prices) |
| Източници (от безплатния /health!) | fiat = Frankfurter (ECB), **crypto = CoinGecko — СЪЩИЯТ източник като нашия** |
| Кеш | 1h fiat / 30s crypto (техен персонажен key) |
| Band | **established / score 57.8** — по-НИСЪК от нашия 69.7 |
| MCP | има /mcp/sse |
| Съсед #2 | „Yahoo Finance Stock Data & Historical Prices API" — $0.01 (не е проучен дълбоко) |
| **loopA на $0.021** | ❌ **НЕ Е НАМЕРЕН** в PayAPI (0 резултата за „loopa"/„loop") — листингът не съществува или е с друго име |

### B3. Сравнителна таблица (обещания + проверими факти, не измерени тела)

| Критерий | Ние (Kristo Intelligence) | Currency & Crypto API (house) |
|---|---|---|
| Цена за заявка | $0.003–0.05 | **$0.001** |
| Данни за парите | CoinGecko + DEXScreener + F&G + **реален on-chain sales feed** | CoinGecko (crypto) + ECB/Frankfurter (fiat) |
| Ширина | 5 x402 endpoints + 3 MCP инструмента + 8 каталожни SKU (демо) | 5 endpoints, тесен фокус (валути/цени) |
| Уникално | **on-chain верифицирани продажби + launch-signal таксономия** (никой друг на пазара няма това) | исторически фиат до 1999 |
| Band / score | **established / 69.7** | established / 57.8 |
| Реални платени клиенти | **1 (0x4dB7, 06.09)** | неизвестно (18 tx house не значи наши клиенти) |
| MCP транспорт | SSE + Streamable HTTP | SSE |

**Извод без покупка:** съседът е чист wrap на публични API (CoinGecko/ECB)
с по-нисък score от нашия. Нашата микро-икономика НЕ е по-зле: за 5× цената
ни продаваме 5× по-широка логика + нещо, което те нямат — on-chain
доказуемост. Но днешната находка (8-те SKU демо) ни оставя с по-малкия
„истински" каталог от техния 5/5.

## ЧАСТ C — Инвентар на 4-те стълба

| Стълб | Доказателство ДНЕС | Какво липсва | Най-силно | Най-слабо |
|---|---|---|---|---|
| **Специалитет** (уникален продукт) | on-chain sales feed + launch-signal таксономия (единствени на пазара); signals с reasoning (верифицирани 4×) | 8-те SKU нямат реална хлебна зад тях — витрината обещава повече от продукта | /api/v1/signal + on-chain feed | 8-те SKU (МЪРТВИ) |
| **Микро-икономика** (цени/клиенти) | цени $0.003–0.05 + VIP; 1 реален external платец; band 69.7 | 2-ро плащане от 0x4dB7 (operator deal тригер); ZERO repeat клиенти още | ценова дискриминация (5 мин loop → винаги свежо) | един-единствен клиент в историята |
| **Доказуемост** (on-chain/verifiable) | 5 трансфера, 4 canary verifications, tx hashes публични; кеш freshness публичен (age 290s); band 69.7 публичен | логване на тела на платени отговори (днес невъзможна форензика); ръчният timeout band recompute | всичко, свързано с Chet/PayAPI веригата | доказателство за РЕАЛНА потребителска стойност (нямаме feedback от 0x4dB7) |
| **Скорост** (свежест/latency) | CoinGecko кеш ≤15 мин (видяно: 290s), arb scan 60s, agent loop 5 мин, MCP SSE + Streamable | latency измерване на платени заявки (последният знаем от canary: под 60s timeout) | agent loop 5 мин е достатъчно свеж за signals | 8-те SKU: нулева скорост (не са живи) |

**Финална присъда на одита:** хлябът на 5-те реални маршрута е ЖИВ и
доказуем; витрината от 8 SKU е МЪРТВА и е нашият най-голям репутационен риск
(клиент, платил за SKU, получава демо). Конкуренцията на house ниво е
по-слаба от нас по score и по дълбочина, но по-евтина и по-проста за
агента. Тест-покупките чакат зареждане на hot wallet (~$0.08).