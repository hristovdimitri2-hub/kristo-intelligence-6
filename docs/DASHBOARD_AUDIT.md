# DASHBOARD AUDIT — табла, източници, NEXUS (06.09, read-only)

Одит само с четене на код + живи HTTP проверки. Нула промени по кода.
Защитите спазени: payTo/endpoint недокоснати, 154/154 PASS.

## 1. Таблица: табло → източник → вярно ли

| Табло | URL/път | Източник на данни | Вярно? | Защо |
|---|---|---|---|---|
| **Телефон (Replit инстанция)** | Replit URL (при теб) | Собствен on-chain watcher — директен RPC скан на payTo | ✅ **ВЯРНО** | Дълго-жив процес без рестарти: броячите не се нулират; чете веригата директно |
| **/dashboard** — уиджет „USDC обем / on-chain sales" (горе) | `/api/dashboard-stats` | **RAM** дневна статистика + wallet watcher (on-chain scan на payTo) | ⚠️ с лаг | watcher-ът показва веригата вярно, но броячите нулират при deploy (корекция на стария одит: НЕ е SQLite-backed) |
| **/dashboard** — секция „Real On-Chain Sales" (долу) | `/api/stats` + `/api/sales` (ПЛАТЕНИ endpoints) | **RAM** `_sales_history` | ❌ след deploy | `gunicorn` рестартира при всеки deploy → RAM се нулира → „$0.00 / 0 on-chain sales". Днес имахме 3 деплоя |
| **/nexus** | `/nexus` (nexus_dashboard.html) | ① `/api/dashboard-stats` (30s) ② `/api/nexus/strategy` (admin — 401 за посетители) ③ **СИМУЛИРАН feed** (random генератор на „открития") | ⚠️ смесено | Реални числа (①) + мъртъв widget за посетители (②) + **фалшиви данни, показани като жива активност** (③) |
| **/sales/admin** — „оперативното" табло ($79.02) | `/sales/admin` → `/api/admin/overview` | **CRM sqlite** (платени leads, `CRM_DATA_FILE`) + **Stripe snapshot** (ако STRIPE_API_KEY е set) + RAM `onchain_revenue` | ⚠️ смесено | $79.02 = CRM/Stripe приходи (**не on-chain**); onchain частта от RAM → нулирана |

### Хипотезите за днешното разминаване
- **(а) RAM броячи, нулирани от deploy-ите — ПОТВЪРДЕНО.** `_sales_history` е
  in-memory списък в main.py (пълни се от wallet watcher/settle пътя); всеки
  Render deploy рестартира gunicorn → нула. Днес: 3 деплоя (Streamable HTTP,
  README, status).
- **(б) Две живи инстанции — ПОТВЪРДЕНО архитектурно.** Replit инстанцията
  (телефонът ти) е дълго-жив процес със собствен watcher на payTo → показва
  веригата вярно. Render инстанцията е рестартирана 3× днес → RAM таблата са
  нулирани. URL-ът на Replit инстанцията не е в repo-то — той е при теб;
  логиката им е идентична (един и същ код, различен uptime на броячите).
- **(в) Различни източници между таблата — ПОТВЪРДЕНО.** Горната таблица:
  едни уиджети четат SQLite/watcher (вярно), други — RAM (нули), трети —
  CRM/Stripe ($79.02), четвърти — симулация.

## 2. Присъда за $79.02 и investor@crypto.io

- **$79.02 = сбор от CRM платени leads (+ Stripe snapshot, ако ключът е
  активен)** в `/sales/admin` — НЕ е on-chain приход. On-chain приходът е
  $0.017 (5 трансфера: 4 канарки + 1 външен платец днес).
- `investor@crypto.io` (17.08) е **запис в CRM базата** (sqlite, файлът е на
  Render disk), създаден през VIP/Stripe потока през август. **Live или test
  не мога да определя отвън** — зависи дали STRIPE_API_KEY в Render е
  `sk_live_…` или `sk_test_…`. **Проверка за теб (1 мин):** Stripe Dashboard →
  Payments → ако плащането е в Test mode списъка (или ключът започва со
  `sk_test`) → тестов запис; ако е в Live → реален. Тестовите данни НЕ бива
  да се бъркат с on-chain приходите в таблото.

## 3. Присъда за NEXUS

**Какво е:** визуално табло (`/nexus`, templates/nexus_dashboard.html) с три
източника: реален polling на `/api/dashboard-stats` (30s), admin
`/api/nexus/strategy` (401 за посетители) и **симулиран feed** — random
генератор на „открития" (шаблони с random протоколи/DEX-и/суми), показани
като жива активност. Това е рекламирано като „NEXUS Discovery Engine".

**Свързан ли е с Kristo Intelligence?** Частично: показва числата на
dashboard-stats (реални), но самият „Discovery Engine" е **`lib/agents/
market_evaluator.js`** — независим Node модул, който сканира CoinGecko
Trending / DeFiLlama / GitHub x402 репозитории и праща Telegram предложения.
**Не се стартира от main.py/Procfile** (пуска се ръчно с `node …`) → **не
работи на Render в момента**. Не пише в данните на API-то (само
`market_state.json` за агента след ръчно одобрение).

**MCP инструмент ли е?** НЕ — `tools/list` връща точно 3 инструмента
(get_market_stats, get_onchain_sales, get_bot_status). NEXUS/evaluator-ът
не е там.

**Работи ли в момента?** Страницата /nexus се отваря (200), но: strategy
widget-ът е 401 за посетители (мъртъв за тях), симулираният feed „работи"
(показва измислени данни), evaluator-ът не върви.

**Струва ли си като MCP инструмент?** Не в сегашния си вид. Еvaluator-ът
предлага идеи за услуги (не реални данни) и не върви на продукция. Ако някога
го оживиш — първо го направи да върви, после мисли за MCP. До тогава:
**не го предлагай на никого.**

## 4. Чернова-спецификация: ЕДНО професионално табло (без изпълнение)

**Принцип: парите и фактите имат ЕДИН източник — веригата.**

1. **Пари (един източник):** on-chain RPC скан на payTo — кодът вече съществува
   (`competitor_recon.fetch_incoming_transfers` + `classify_transfers`).
   Запис в **SQLite** (постоянно), не RAM. Колони: tx, платец, сума, време,
   класификация (canary / sampler / external-human).
2. **Платци:** от същия скан — `external_unique_payers` = launch метриката;
   известните sampler/crawler = heartbeat секция (вече имплементирано в
   `listing_monitor.receiver_scan`).
3. **Заявки:** от **постоянен лог** (sqlite: timestamp, endpoint, UA, канал,
   плащане?) — не RAM. Колоните вече се логват (`_live_request_log` има
   user_agent/referer/funnel) — липсва само persist-ването.
4. **Band/рангове:** от `listing_monitor.fetch_state()` (PayAPI agent/get +
   8-те термина) — вече написано.
5. **Автообновяване:** 30–60s (fetch на JSON, не пълно презареждане).
6. **Махни/redirect:** симулирания NEXUS feed, RAM-базираните уиджети в
   /dashboard, дублираните табла → едно канонично табло, останалите URL-и
   правят redirect към него.
7. **Фондове:** отдели секция „CRM/Stripe приходи" с етикет „off-chain, mode:
   live/test" — никога не ги смесвай с on-chain числата.

**Защити при бъдеща имплементация:** payTo/endpoint недокоснати; RAM
`_sales_history` остава за платежния слой (402 settle), но таблото чете от
persistent store; 154/154 теста трябва да продължат да минават.

## 5. ИМПЛЕМЕНТАЦИЯ (06.09, след одобрение) — ЕДНО канонично табло

**Изградено по спецификацията от секция 4. Нула промени по payTo/платените
endpoints. 164/164 теста PASS (154 стари + 10 нови).**

### Какво е изградено
- **`integrations/dashboard_store.py`** — persistent SQLite store
  (`data/dashboard_state.db`): `onchain_sales` (dedup по tx, класификация
  canary/sampler/external), `request_log` (UA/funnel), `payapi_state`,
  `meta` (block watermark). Един HTTP provider: публичен RPC, read-only
  eth_getLogs — същата логика като `competitor_recon`.
- **`main.py`**: `_record_real_sale` → пиша и в store (плащаният път никога
  не се чупи от това — try/except); `_capture_live_request` → пиша всяка
  заявка в store; нов background thread `dashboard-scan` (retro 30 дни при
  стартиране → инкрементален скан на всеки 60s от watermark-а → PayAPI
  refresh на всеки 15 мин); free endpoint **`GET /api/dashboard/data`**;
  `/dashboard` → новото табло; `/nexus` → 302 redirect към `/dashboard`.
- **`templates/dashboard.html`** — ново табло, 4 секции, авто-refresh 45s:
  (а) On-Chain Sales [истина], (б) API Requests [лог], (в) Listing & Ranking
  [PayAPI, "unscored/baseline" докато не светне първият скан], (г) CRM/Stripe
  [OFF-CHAIN, скрит с toggle, маскирани имейли, НИКОГА в обща сума].
- **Махнато:** старите RAM уиджети, симулираният NEXUS feed, мъртвият
  nexus_dashboard.html. Discovery модула (`lib/agents/market_evaluator.js`)
  остава в кода — без претенция за „жив" статус.
- **`scripts/validate_retro_scan.py`** — еднократна проверка: реален скан →
  сравнение с очакваното (5 трансфера / $0.017 / external 0x4dB7).

### Резултат от живата валидация след деплоя (06.09)
- **Deploy №1:** `/api/dashboard/data` → **$0.017 / 5 трансфера / 1 external**,
  историята съдържа `2026-09-06 06:41:03 · $0.003 · EXTERNAL (0xb881f9dcdd…)`.
  Retro-сканът се изпълни на Render (watermark блок 50960727).
- **Deploy №2 (= тестът „рестарт не нулира"):** СЛЕД пълен gunicorn рестарт
  числата са СЪЩИТЕ (5 / $0.017), watermark-ът напреднал (50961026) —
  persistent store-ът работи точно като crm_sales.db. **PASS ✅**
- `/nexus` → 302 към `/dashboard`; `/api/dashboard-stats` → 200 (инвариант).

### ВАЖНО откриттие за секция (г) CRM/Stripe
На Render инстанцията CRM базата (`data/crm_sales.db`) има **0 платени
записи** и Stripe snapshot-ът връща **празен списък с плащания** — затова
секция (г) показва $0.00. Това е честното състояние на Render.
**$79.02 / investor@crypto.io НЕ се вижда от Render** — той живее в CRM
базата на другата инстанция (Replit/телефонът), която е отделна машина с
отделен SQLite файл; между двете бази НЯМА синхронизация в кода.
=> Възможни действия (твое решение): (а) Replit остава източникът за
off-chain продажби и гледаш сумите там; (б) еднократен export/import на
платените записи към Render; (в) Stripe става единственият off-chain
източник — тогава провери в Stripe Dashboard дали ключът на Render е
live/test и защо списъкът е празен (тестови записи на друга инстанция?).

### Защо рестарт вече НЕ нулира числата
Данните са в `data/dashboard_state.db` (persistent disk, както crm_sales.db).
Watchdog-ът даже не разчита на паметта: сканът продължава от записания
watermark блок, а dedup-ът по tx хеш прави повторния запис невъможен.

### Какво да провериш като собственик (2 мин, след deploy)
1. Отвори **`/dashboard`** → секция On-Chain Sales трябва да показва
   **$0.017 / 5 плащания / 1 external**, а в историята — редът
   `2026-09-06 06:41:03 · $0.003 · EXTERNAL` с линк към BaseScan.
2. Отвори **Basescan** → адреса на приемника → сравни: последните
   трансфери трябва да са точно тези 5. Разминаване = бъг приоритет 0.
3. **Тест „рестарт не нулира"**: запиши си числата → направи deploy
   (или изчакай следващия) → отвори пак `/dashboard` → числата трябва да са
   СЪЩИТЕ или по-големи. Ако се нулират — бъг приоритет 0.
4. **`/nexus`** → трябва да те пренасочи към `/dashboard`.
5. CRM/Stripe секцията е скрита → „Покажи off-chain сумите" → виждаш
   $79.02 с етикет OFF-CHAIN; тя НЕ се събира с $0.017 никъде на таблото.
6. (Опционално) `python scripts/validate_retro_scan.py` локално → PASS.