# РЕГИСТРАЦИОНЕН ПАКЕТ — MCP каталоги (проверено на живо: 05.09)

**Какво ще регистрираме:** нашия MCP сървър в 3 публични каталога —
местата, където AI агентите реално търсят какво да купят. Всяка регистрация
= отваряш адрес, влизаш с GitHub профила си, поставяш готов текст.

**ПОЛЕТА ЗА КОПИ-ПЕЙСТ (еднакви за всичките три):**

| Поле | Текст |
|---|---|
| Име | `Kristo Intelligence — DeFi Signals API` |
| URL на сървъра | `https://kristo-intelligence-api.onrender.com/mcp/sse` |
| Листинг в PayAPI | `https://payapi.market/api/kristo-intelligence-defi-signals-api` |
| Описание | `Paid DeFi intelligence API on Base: trading-agent signals (action, confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native: agents pay per call in USDC, from $0.003 — no signup, no API keys.` |
| Тагове (ако пита) | `base, defi, x402, crypto, signals` |
| Категория (ако пита) | Finance / Market Data |
| GitHub | `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` |

---

## ── РЕГИСТРАЦИЯ 1: PulseMCP (~10 минути) ──

**Адрес за отваряне:** https://www.pulsemcp.com/submit-server
*(ако страницата не се отваря директно — отвори pulsemcp.com и търси
линк „Submit Server" долу/горе)*

**Как да вляза:**
1. Отваряш адреса.
2. Ако иска вход → **Sign in with GitHub** (пиши GitHub потребителя и
   паролата, после „Authorize").

**Полета (копи-пейст от таблицата горе):**
- Име → „Име"
- URL на сървъра → „URL на сървъра" (SSE адресът)
- Описание → „Описание"
- Категория → Finance / Market Data

**Бутон за изпращане:** „Submit" / „Submit Server" (долу на формата).

**Ако срещнеш проблем:**
- Страницата 403/не се отваря → пробвай в друг браузър или инкогнито;
  ако и тогава не — пропусни PulseMCP за днес и ми кажи.
- Ако пита за transport → избери **SSE**.

---

## ── РЕГИСТРАЦИЯ 2: Glama (~10 минути) ──

**Адрес за отваряне:** https://glama.ai/mcp/servers

**Как да вляза:**
1. Отваряш адреса (виждаш каталог с 81,000+ сървъра).
2. Горе има линк/бутон **„Add Server"** → кликаш го.
3. Искa вход → **Sign Up / Sign in with GitHub** (най-горният десен бутон
   „Sign Up").

**Полета (копи-пейст от таблицата горе):**
- Name → „Име"
- Server URL → „URL на сървъра" (SSE адресът); при transport избери **SSE**
- Description → „Описание"
- Tags → `base, defi, x402, crypto, signals`

**Бутон за изпращане:** „Submit" / „Add" (долу на формата).

**Ако срещнеш проблем:**
- Ако формата иска само GitHub repo (не URL) → постави
  `https://github.com/hristovdimitri2-hub/kristo-intelligence-6` и ми кажи
  „Glama иска repo" — ще подготвя каквото трябва.
- Ако проверката чака одобрение — нормално, те индексират ръчно.

---

## ── РЕГИСТРАЦИЯ 3: Smithery (~15 минути, УСЛОВНА) ──

⚠️ **ВАЖНО, променило се наскоро:** Smithery беше купена от Arcade.dev и
новият flow е различен. Не иска smithery.yaml (потвърдено в тяхната
документация — файлът вече не е нужен за remote сървъри). НО иска
**Streamable HTTP transport**, а нашият MCP endpoint е **SSE**. Пробвай —
може да мине, може да откаже. Ако откаже заради транспорта: СПри и ми кажи
„Smithery иска streamable HTTP" — това е малка промяна по API-то, която
изисква твоето съгласие (инвариантът payTo/endpoint НЕ се пипа; добавя се
само нов транспортен път).

**Адрес за отваряне:** https://smithery.ai/new

**Как да вляза:**
1. Отваряш адреса.
2. Ако иска вход → Login (горен десен ъгъл на smithery.ai) → влизаш.

**Полета (копи-пейст от таблицата горе):**
- Server URL → „URL на сървъра" (SSE адресът)
- Name/Namespace → ако пита за име: `kristo-intelligence`
- Description → „Описание"

**Бутон за изпращане:** „Publish" / „Create".

**Ако срещнеш проблем:**
- „Streamable HTTP required" / отказ за transport → СПри, ми кажи точната
  грешка и минаваме на следващата регистрация. Решаваме после дали добавяме
  новия транспорт.
- Ако иска CLI (`npx smithery ...`) → не го прави сам; кажи ми и ще подготвя
  точните команди.

---

## Финална таблица

| Регистрация | Адрес | Време | Ако заседна |
|---|---|---|---|
| PulseMCP | https://www.pulsemcp.com/submit-server | ~10 мин | Друг браузър/инкогнито; иначе пропусни за днес |
| Glama | https://glama.ai/mcp/servers → „Add Server" | ~10 мин | Ако иска repo вместо URL — ми кажи |
| Smithery | https://smithery.ai/new | ~15 мин | Ако отказа за transport — СПри, моя работа после |

**След всяка успешна регистрация кажи „готово [име]" — проверката в
каталога е моя работа.** (След 2–3 дни проверявам дали сървърът ни вече се
вижда в тяхното търсене и докладвам.)