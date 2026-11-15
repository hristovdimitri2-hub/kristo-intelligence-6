# Bazaar / Discovery + Session Pricing — проучване (2026-10-07)

> Само проучване. Без код, без публична регистрация.
> Регистрация/листинг в публичен каталог = публично действие → чака изрично „Да".
> Източници: docs.x402.org, docs.payai.network, docs.cdp.coinbase.com,
> specs/ в `x402-foundation/x402`, npm `@x402/extensions@2.28.0`, GitHub code search.

---

## 1. Какво се поддържа

### 1.1 Bazaar / Discovery разширение — ДА, поддържа се от всички

| Кой | Поддръжка | Evidence |
|---|---|---|
| **x402 спецификация** | ✅ официално разширение | `specs/extensions/bazaar.md` в `x402-foundation/x402`; docs: https://docs.x402.org/extensions/bazaar |
| **PayAI** (нашият facilitator) | ✅ пълна, автоматичен листинг | https://docs.payai.network/x402/facilitators/bazaar.md |
| **Coinbase CDP** | ✅ в SDK-а | `buildBazaarDeclaration(method, path)` в cdp-sdk (`server-extensions.ts:113`), константа `CDP_EXTENSION_BAZAAR` |

**Как работи (общата схема):**
1. Сървърът декларира в **402 body → `extensions.bazaar`** (точен JSON по-долу).
2. Клиентът **echo-ва** декларацията в payment payload-а (задължително поведение в x402 v2 — „the client must include at least the extension info it received").
3. Фасилитаторът индексира при `/verify` и `/settle` (PayAI: от 2026-07-29 и verify-ът записва, без нужда от сетълмент).
4. Фасилитаторът връща **`EXTENSION-RESPONSES`** header след плащане.

**`EXTENSION-RESPONSES` (HTTP header):**
- Стойност: base64 на JSON, key = името на разширението.
- `bazaar.status` ∈ `"success"` | `"processing"` | `"rejected"` (+ `rejectedReason` при reject).
- Пример: `EXTENSION-RESPONSES: eyJiYXphYXIiOnsic3RhdHVzIjoic3VjY2VzcyJ9fQ==` → `{"bazaar":{"status":"success"}}`.
- Отсъствието му **не е** сигнал за грешка („its absence carries no signal").

**`declareDiscoveryExtension`:**
- Helper в пакета **`@x402/extensions`** (npm, latest **2.28.0**), цитиран в PayAI docs:
  „The `@x402/extensions` package builds a valid declaration for you (`declareDiscoveryExtension`), including the JSON schema the facilitator validates against."
- Еквивалент в CDP SDK: `buildBazaarDeclaration(method, path)` (wire shape следва `go/extensions/bazaar`).
- Нашата реализация (Flask, чист Python) ползва **ръчно сглобен declaration** — валидният wire shape е един и същ; helper-ите са TS-only.

**Wire shape на декларацията (402 body):**
```json
{
  "x402Version": 2,
  "resource": { "url": "...", "description": "...", "mimeType": "application/json",
                "serviceName": "...", "tags": ["..."], "iconUrl": "..." },
  "accepts": [ ... ],
  "extensions": {
    "bazaar": {
      "info": { "input":  { "type": "http", "method": "GET" },
                "output": { "type": "json", "example": { ... } } },
      "schema": { "$schema": "https://json-schema.org/draft/2020-12/schema", ... }
    }
  }
}
```
- GET/HEAD/DELETE → `QueryInput` `{type, method}`; POST/PUT/PATCH → `BodyInput` `{type, method, bodyType:"json", body:{...}}` (`body` е задължителен за BodyDiscoveryInfo).
- **Опционални service-level полета:** `serviceName`, `tags`, `iconUrl` върху `resource`.
- Мрежи в каталога: `eip155:8453` (Base), `eip155:84532`, Solana mainnet/devnet — USDC.

**Листинг при PayAI:** автоматичен — „there is no registration form, account, or manual submission". Каталог: `GET /discovery/resources` (+ `/discovery/listing-status?resource=…` за дебъг).

### 1.2 Сесийно ценообразуване (`openSession` / `maxBudget`) — НЕ, няма го

Проверено **всичко**, 0 съвпадения:
- `x402-foundation` org (всички repos): `openSession` → **0**, `maxBudget` → **0**
- `coinbase` org: `openSession` → **0**, `maxBudget` → **0**
- `PayAINetwork` org: `openSession` → **0**, `maxBudget` → **0**
- `specs/x402-specification-v2.md`: няма `openSession`/`maxBudget`; „session" само като **application pattern**:
  - §12.2 „**Session-based access** (time-limited subscriptions)"
  - §12.6 „**Session management** for time-based access control"
  - изрично: *„Implementation details … (budget management, … session handling) are available in application notes and implementation guides"* — т.е. **извън протокола**.
- `@x402/extensions@2.28.0` tarball: 0 файлове с „session".

**Какво СЪЩЕСТВУВА като близки механизми:**

| Механизъм | Какво дава | Къде |
|---|---|---|
| **`upto` scheme** | „buyer authorizes a **maximum**, seller charges **actual usage**" — per-request ceiling, не сесия | docs.x402.org/schemes/upto |
| **`batch-settlement` scheme** | reusable on-chain **channel** (един депозит, off-chain ваучери per request, cumulative ceiling = „charged so far + this request's maximum", claim/sweep/refund) — **най-близкият аналог на сесия с бюджет**; PayAI го serviра на Base mainnet | docs.x402.org/schemes/batch-settlement; docs.payai.network/x402/servers/evm-batch-settlement |
| **`auth-capture` scheme** | escrow: hold → capture/void/refund след доставяне на ресурса | docs.x402.org/schemes/overview |

**Извод:** `openSession`/`maxBudget` **не са част от x402 v2** и нито PayAI, нито CDP го документират — вероятно вътрешен/черновиден термин или бъркане с `upto`/`batch-settlement`.

---

## 2. Какво трябва да променим в manifest-а / 402 декларацията

Нашето текущо състояние (`main.py`, `_x402_accepted_payment`, ~ред 1528-1560) **вече е валиден v2 Bazaar declaration**:
- ✅ `extensions.bazaar.info.input` = `{type:"http", method:"GET"}` (QueryInput — правилният shape за GET)
- ✅ `extensions.bazaar.schema` с `properties.input.queryParams` + `properties.output.example` (изискването на x402scan audit-а)
- ✅ `resource = {url, description, mimeType}` в 402 body

**Липсващи/за подобряване (по приоритет):**

| # | Промяна | Задължително? | Обхват |
|---|---|---|---|
| 1 | `resource.serviceName` (`"Kristo Intelligence"`), `resource.tags` (напр. `["signals","defi","base"]`), `resource.iconUrl` | Не, но входи по-богато в каталога (PayAI: „Entry shows null for serviceName, tags, iconUrl… if the declaration omits them") | ~1 ред в builder-а |
| 2 | Клиентът да echo-ва `extensions` в payment payload-а при `--send` (`scripts/demo_sponsored_pay.py`) — иначе фасилитаторът **никога не вижда** декларацията („Step 2 is where most 'my resource never appears' reports come from") | **Да** за листинг чрез плащане | ~15 реда в клиента |
| 3 | Диагностика: четене на `EXTENSION-RESPONSES` след сетълмент + лог на `bazaar.status` | Желателно | малък |
| 4 | Локална валидация на декларацията с JSON schema-та от `@x402/extensions` (тест/CI) — понеже сме Python, helper-ът не е наличен | Желателно | 1 тест |
| 5 | `resource.url` absolute public https URL | ✅ вече е така (от `request.host_url`) | — |
| — | Промени по `GET /api/mcp/manifest` (MCP manifest-а) | **Не** — Bazaar декларацията живее в 402 body-то, не в MCP manifest-а | — |

**Сесийно ценообразуване:** нищо за промяна — не съществува в спецификацията. Ако някога трябва budget/месечен модел → `upto` (per-request ceiling) или `batch-settlement` (reusable channel), не измисляне на `openSession`.

---

## 3. Колко работа е

| Стъпка | Труд | Забележка |
|---|---|---|
| (1) `serviceName`/`tags`/`iconUrl` в 402 builder-а | **~30 мин** | чисто добавяне, +1-2 теста |
| (2) Echo на `extensions` в `demo_sponsored_pay.py --send` | **~1–2 ч** | тества се срещу PayAI `/verify` (не движи пари) |
| (3) Четене на `EXTENSION-RESPONSES` в клиента | **~1 ч** | лог + отчет |
| (4) Schema-валидация в тест | **~1–2 ч** | schema JSON от `@x402/extensions` |
| **Общо за пълен Bazaar listing pathway** | **~½ ден** | без публична регистрация — листингът е автоматичен при първото носещо декларация плащане/verify |
| Сесийно ценообразуване | **0** | не съществува; при нужда separate spike за `upto`/`batch-settlement` (~1–2 дни) |

---

## 4. Рисове / забележки

- **Host policy (PayAI):** първият listing минава през read-only probe (`HEAD`/`GET` → очаква **402**); private/tunnel/preview хостове се отказват. Нашият production URL (`kristo-intelligence-api.onrender.com`) е публичен https → ок.
- **Opt-out по подразбиране (v2):** ако махнем `bazaar` от 402 → нищо не се индексира. Листингът е „opt-in by declaration".
- **`processing` ≠ провал:** индексирането е асинхронно; не приключваме при липса веднага.
- Нито едно от горните не е публикувано/регистрирано — само прочетено.

*Проверено на 2026-10-07. За въпроси: @murrlincoln (x402) / PayAI Discord.*
