# ИНСТРУКЦИЯ: Регистрации в MCP директориите (ръчен български, без жаргон)

**Какво ще правим:** качваме нашия API в три публични каталога (телефонни
книжки за AI агенти). Всяка регистрация = отваряш сайт, създаваш безплатен
акаунт с твоя поща, поставяш готов текст (имам го аз). Общо ~30 минути.

**Преди да почнеш — подготы си тези три неща (ги пиши на лист):**
1. Твоята имейл адреса: `hristovdimitri2@gmail.com`
2. Твоя GitHub профил: `hristovdimitri2-hub` (ако нямаш парола за него —
   направи „Forgot password" от github.com)
3. Описание на API-то (копираш от `docs/MCP_SUBMISSIONS.md`, раздел „Общи
   полета" — или по-долу):
   > Paid DeFi intelligence API on Base: trading-agent signals (action,
   > confidence, price, reasoning for ETH/ONDO/KAITO/DEGEN), cross-DEX
   > arbitrage spreads, whale USDC tracking, rug-risk checks. x402-native:
   > agents pay per call in USDC, from $0.003 — no signup, no API keys.
   - URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
   - Листинг: `https://payapi.market/api/kristo-intelligence-defi-signals-api`

---

## СТОПЪКА 1 — PulseMCP (най-лесната, започни с нея)
1. Отвори в браузъра: **https://www.pulsemcp.com**
2. Търси бутон **„Submit a Server"** или **„Add your server"** (обикновено горе).
3. Ще те попита да влезеш → избери **Sign in with GitHub** (по-лесно от поща).
   Пиши GitHub потребителя и паролата си, натисни „Authorize".
4. Формата пита за име/URL/описание → поставяш от горния блок:
   - Name: `kristo-intelligence`
   - URL: `https://kristo-intelligence-api.onrender.com/mcp/sse`
   - Description: описанието горе
   - Category (ако пита): Finance / Market Data
5. Натисни **Submit**. Готово — те индексират за ден-два, нищо друго не искат.

## СТОПЪКА 2 — Glama
1. Отвори: **https://glama.ai/mcp/servers**
2. Търси **„Add server"** → пак **Sign in with GitHub**.
3. Поставяш същите полета. При въпрос за transport избери **SSE**.
4. При тагове (tags) напиши: `base, defi, x402, crypto, signals`
5. Submit → готово.

## СТОПЪКА 3 — Smithery
1. Отвори: **https://smithery.ai**
2. „Publish server" → **Sign in with GitHub**.
3. Техният формуляр може да поиска допълнителен файл в кода на проекта
   (нарича се `smithery.yaml`). Ако формата го иска — СПри тук и ми кажи
   „Smithery иска yaml файл" — аз го подготвям за 5 минути и връщаш да
   довършиш.
4. Ако не иска нищо специално — същите полета, Submit.

---

## След всяка регистрация — кажи ми само едно нещо:
„PulseMCP — пратено", „Glama — пратено", „Smithery — пратено" (или каква
грешка ти е дало). Аз проверявам след 2–3 дни дали сървърът вече се вижда
в каталога (това е моята работа, не твоя).

## Защо си струва 30-те минути
Това са каталогите, в които AI агентите (клиентите ни) реално търсят какво
да купят. Единственият канал, който един наш човек от платформата нарече
„пътят, който има значение". Една регистрация = нашето API става видимо за
цялата тази тълпа, завинаги и безплатно.

**ГРЕШКИ, КОИТО НЕ СА ПРОБЛЕМ:** ако сайтът не изглежда така, както описах
(менят се често) — търси бутоните „Submit"/„Add"/„Publish" и полетата ще са
същите. Ако нещо ти е неясно — направи screenshot и ми го покажи.