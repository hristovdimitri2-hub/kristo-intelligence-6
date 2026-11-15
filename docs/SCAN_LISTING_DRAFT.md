# SCAN_LISTING_DRAFT — кандидатура за листинг в x402scan (чернова)

> ЛОКАЛНА ЧЕРНОВА — нищо не е публикувано/подадено. Проучване + числа + готов
> текст. При подаване текстът се превежда на EN и се пуска като issue в
> `Merit-Systems/x402scan` със заглавие `[Listing Request] …`.
> Дата на проучването: 08.10.2026.

---

## 1. Форматът — какво открихме

### Къде се подава
* **Практиката (по другите):** GitHub issue в `Merit-Systems/x402scan` със
  заглавие `[Listing Request] <Име> — <кратко>`. 44 отворени такива; актуални
  образци: **#1268** (Automaton-Sovereign), **#1249** (fitze-x402-seller),
  **#1244** (Livecheck).
* **Официалният път (README → „Add Resources"):**
  https://www.x402scan.com/resources/register — подава се URL; ако върне
  валиден x402 schema, ресурсът влиза автоматично в списъка.
* **Валидация преди подаване (по docs/DISCOVERY.md):**
  `npx -y @agentcash/discovery kristo-intelligence-api.onrender.com -v`

### Шаблон / правила в репото — **НЯМА**
* `.github/` съдържа **само** `workflows/` и `PULL_REQUEST_TEMPLATE.md` — и той
  е **само за нови facilitator-и** („DELETE THIS TEMPLATE IF YOU ARE NOT
  ADDING A NEW FACILITATOR!"). **Няма issue template за листинг.**
* **Няма CONTRIBUTING.md.** Правилата са в README (секция *Contributing*) и в
  `docs/DISCOVERY.md` („x402scan Discovery & Registration Spec" — 180 реда).

### Де факто формат на Listing Request (по #1244/#1249/#1268)
```
Заглавие: [Listing Request] <Име> — <едно изречение> (x402 v2, Base)
Origin:   <base URL>
Spec:     <openapi.json URL>
Network / asset: Base mainnet, USDC, x402 exact
Discovery: <URL-и на discovery документите>
What it does: 1–3 изречения
Route | Price   (таблица)
Ask: <какво искаме — напр. „потвърдете, че платените маршрути се индексират")
```
Бележки от образците: #1268 изрично казва „No accounts, no API keys, no KYC"
и дава как се прави неплатен test-probe; #1244 дава „Public stats at /stats".

### Какво гледат (docs/DISCOVERY.md — spec-а на индексирането)
* **OpenAPI-first** (препоръчано): `/openapi.json` с `x-payment-info` на всяка
  платена операция (`protocols: ["x402"]`, `price` fixed/dynamic), 402 в
  `responses`, security схеми; опционално `x-discovery.ownershipProofs`.
* Fallback: `/.well-known/x402`; endpoint-only (402 + parseable `accepts`,
  непразен, Bazaar input schema, **amount в token atomic units**).
* **Чести причини за отказ:** 404/405/429 вместо 402; празен `accepts[]`;
  липсващ input schema; сума в долари вместо atomic units; заявка, отхвърлена
  от валидация ПРЕДИ 402 challenge-а.

### Нашата discovery повърхност (проверено на живо, 08.10)
| Път | Статус |
|---|---|
| `/openapi.json` | 200 ✓ |
| `/.well-known/x402` | 200 ✓ |
| `/llms.txt` | 200 ✓ |
| `/api/mcp/manifest` | 200 ✓ (MCP: `POST /mcp`, `/mcp/sse`) |
| `/routes.md` | 404 — не се цитира |
| `/.well-known/agent-card.json` | 404 — не се цитира |

402 challenge-ът е v2 (`Payment-Required` base64 header), `scheme: exact`,
`network: eip155:8453`, `amount: "3000"` (atomic units ✓), Bazaar декларация
в `extensions.bazaar` ✓.

---

## 2. Нашите числа (30 дни, от дашборда `/api/dashboard/data`)

| Число | Стойност |
|---|---|
| **Платени обаждания** (плащане прието) | `/api/v1/signal` — **9** · `/api/v1/whaleflow` — **3** (12 общо) |
| **Уникални платци** | **5** портфейла (2 с повторна покупка — ретеншън 2/5) |
| **Листинги в Bazaar** | **2** |

* **Цена:** 0.003 USDC/обаждане и за двата endpoint-а
* **URL-и:**
  * https://kristo-intelligence-api.onrender.com/api/v1/signal
  * https://kristo-intelligence-api.onrender.com/api/v1/whaleflow
* **payTo:** `0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f` (Base, USDC
  `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, scheme `exact`, x402 v2)

### Как броим (само за нас — не е част от текста)
* „Платени обаждания" = редове в `payment_guards` (плащането е отключило
  доставка). 13 общо, от тях 1 е `/api/bot-status` (извън обхвата) → 12.
  Всички са в последните 30 дни (услугата е жива от 06.09, 32 дни).
* 2 от 12-те (06:13, 08.10) са с празна доставка заради закъснелия деплой —
  затова пишем „плащане прието", не „плащане → доставка". Числата 9/3 са
  потвърдени по DB.
* „Уникални платци" = `track_record.paying_strangers` от дашборда (5). Включва
  и demo wallet-а `0xe50c…5763` (наш, `demo_sponsored_pay.py`) — ако някой
  пита „колко са външните", честният отговор е 4. Трансакциите са реални USDC
  преводи на Base и са публично проверими, така че „5 платили портфейла" е
  вярно и проверимо.
* Плащанията на известната инфраструктура за сондиране/review също са реални
  външни плащания (клас `sampler`/`canary` в дашборда) — броят се в горните.

---

## 3. Готов текст на кандидатурата (български; при подаване → EN)

**Заглавие:**
`[Listing Request] Kristo Intelligence — live DeFi signals & whale-flow API (x402 v2, Base)`

**Тяло:**

> **Origin:** https://kristo-intelligence-api.onrender.com
> **Spec:** https://kristo-intelligence-api.onrender.com/openapi.json
> **Network / asset:** Base mainnet (eip155:8453), USDC
> `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`, x402 v2 `exact`
> (payment-required base64 header, `x-402-version: 2`)
> **payTo:** 0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f
> **Discovery:** /openapi.json · /.well-known/x402 · /llms.txt ·
> /api/mcp/manifest (MCP транспорти: POST /mcp, /mcp/sse)
>
> **Какво прави:** Kristo Intelligence продава на AI агенти машинно-четим
> крипто-интелект на заявка: жив DeFi trading signal (действие, увереност,
> едноредово обоснование за ETH/ONDO/KAITO/DEGEN), проследяване на китове
> (USDC трансфери ≥ $5M на Base с етикетирани платци), cross-DEX арбитражни
> възможности и rug-check-ове. Без акаунти, без API ключове, без KYC —
> плащане на обаждане в USDC на Base.
>
> **Маршрути и цени:**
>
> | Маршрут | Цена |
> |---|---|
> | GET /api/v1/signal — жив DeFi сигнал | 0.003 USDC |
> | GET /api/v1/whaleflow — whale-flow лента (трансфери ≥ $5M) | 0.003 USDC |
> | GET /api/arb/opportunities — cross-DEX арбитраж | 0.005 USDC |
> | GET /api/bot-status — здраве на бота | 0.005 USDC |
> | GET /api/sales — статистика продажби | 0.005 USDC |
> | GET /api/stats — статистика на API-то | 0.005 USDC |
>
> **Активност (30 дни, публичен дашборд на /dashboard):**
> * платени обаждания: `/api/v1/signal` — 9, `/api/v1/whaleflow` — 3
> * уникални платци: 5 (4 външни + 1 наш demo)
> * листинги в Bazaar (PayAI): 2
>
> Плащанията са еднократни по EIP-3009 nonce, проверката на плащането е
> fail-closed (невалиден proof → 401, никога доставка), а всяка продажба е
> проверима по Transfer-логовете на веригата. 471 автоматизирани теста.
>
> **Ask:** моля, потвърдете, че платените маршрути се индексират правилно
> (OpenAPI-first discovery + 402 challenge са публични на origin-а), и кажете
> ако има допълнително изискване за searchable/featured видимост — ще го
> покрием.

**Преди подаване (чеклист):**
1. Превод на EN на текста по-горе.
2. `npx -y @agentcash/discovery kristo-intelligence-api.onrender.com -v` —
   да излезе чисто (OpenAPI-first).
3. Подаване: issue в `Merit-Systems/x402scan` + (по желание) регистрация през
   https://www.x402scan.com/resources/register.
4. Регистрация/листинг да се добави в `docs/WATCH_LIST.md` за следене.
