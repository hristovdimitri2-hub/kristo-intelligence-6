# PROJECT STATUS (frozen 2026-08-27 — RESUMED 2026-08-29)
## 🏁 PHASE COMPLETE: product verified → GO-TO-MARKET (2026-09-03)


## 🖥️ ТАБЛО 2.0 (13.09) — истината на един екран + финален веригов одит

Живо: `https://kristo-intelligence-api.onrender.com/dashboard` (free `/api/dashboard/data`,
авто-refresh 45s). Линията „LIVE" значи live — при грешка badge-ът става червен.

### 1. Какво вече стои на екрана
| Секция | Източник (не статичен текст) |
|---|---|
| **On-Chain Sales** — $0.028 / 8 tx / 2 external, всяко плащане с **пълен 66-символен хеш**, блок, клас, timestamp | `onchain_sales` (SQLite) + seed от `integrations/verified_sales.py` |
| **КЛИЕНТИ** — всеки external платец: портфейл, брой плащания, общо, последна покупка, маршрути | `clients_summary()` върху `onchain_sales` |
| **КИТОВЕ** — последните whale записи ($, токен, време, от/до съкратени); празно = „**чакаме кит**" | `whaleflow_events` + watermark |
| **СТАЖИ** — лампа на C1 replay-lock-а (жив/спрял, реален probe), последен блокиран опит, C2 настройки | `payment_guards` + `guard_events` |
| **ФЪНЪЛ** — 402 → платени по **всеки** маршрут, днес/общо, винаги видим | `request_log` |
| **Реални маршрути** — 6-те, с цени от API-то | `REAL_X402_ROUTES` (същият списък, който издава 402) |
| Запазени непроменени | API Requests (чисти/шум), Listing & Ranking, CRM off-chain (скрит зад toggle) |

Маршрутът на клиент се твърди като **факт само** при записан `payment_guards` ред
(endpoint от C1/H2). Иначе се показват **всички кандидати по цена** — защото $0.003
покрива и `/api/v1/signal`, и `/api/v1/whaleflow`, а $0.005 покрива четири маршрута.
Да се изпише един от тях би било измислен факт на екрана, който трябва да държи само факти.

### 2. ОДИТ — находки (всяка: вярно ли е за НАШЕТО състояние днес?)

| # | Находка | Клас | Вярно днес? | Статус |
|---|---|---|---|---|
| 1 | **Фънълът „днес" = общото.** `challenges_today`/`paid_today` се пълнеха от TOTAL заявката (`cur`), а `cur_today` се изчисляваше и изхвърляше → колоната „Днес: 402 → платени" повтаряше all-time числата. Фантомно число. | **HIGH** | ✅ да (кодът беше точно такъв) | **ФИКСНАТО** |
| 2 | **Публикуван хеш = безплатна заявка.** Бързият път на proof рейла търсеше хеша в `_sales_history` **без проверка кой е платил**. Всичките 8 пълни хеша са публикувани на собственото ни табло → всеки, който ги прочете, можеше да представи чужд хеш със свой `payer` и да получи платена заявка безплатно. Доказва се с тест: `assert 200 != 200`. | **HIGH** | ✅ да (мониторът пълни `_sales_history` от веригата всеки цикъл) | **ФИКСНАТО** |
| 3 | **Две живи повърхности, две истини за парите.** `/api/dashboard-stats` четеше RAM `_sales_history`; след deploy тя е празна до следващия tick → **днес на живо връща `total_volume_usd=0`, `total_sales=0`**, докато `/api/dashboard/data` връща $0.028/8. Точно симптомът „0 продажби", още жив на втория екран. | **HIGH** | ✅ да (проверено на живо) | **ФИКСНАТО** |
| 4 | **Фантомна цена $0.05 на екрана.** Статичната таблица на `/dashboard` показваше `/api/sales` = **$0.05**, а живият 402 иска **$0.005** (10×). Платещ агент, чел таблото ни, щеше да надплати 10×. | **HIGH** | ✅ да (проверено: `accepts[0].amount = 5000`) | **ФИКСНАТО** |
| 5 | `FUNNEL_ROUTES` не съдържаше `/api/v1/whaleflow` → новият платен маршрут беше невидим във фънъла. | MED | ✅ да | **ФИКСНАТО** (в обхвата на Табло 2.0) |
| 6 | Стандартният рейл: при RPC грешка при `get_transaction_receipt` C2 проверката се **прескача** (fail-open), защото изключението излиза извън `try`. Днес е безобидно (facilitator-ът връща само вече минали транзакции, прагът е 1), но политиката е декларирана fail-closed. | MED | ⚠️ латентно (праг=1) | дълг |
| 7 | Ако `MIN_STANDARD_PAYMENT_CONFIRMATIONS` се вдигне >1, клиент, чиято EIP-3009 авторизация вече е похарчена, получава 401 при retry → платил е и не може да повтори. | MED | ⚠️ латентно (праг=1) | дълг |
| 8 | C1 записва `amount_usdc = price`, не реално платеното (стандартен рейл може да е надплатил). | LOW | ✅ да | дълг |
| 9 | `_get_dynamic_price` зависи от RAM `_paid_calls_usage` → след deploy обемната отстъпка се брои отначало. | LOW | ✅ да | дълг |
| 10 | `/api/dashboard-stats.total_requests` идва от RAM `_daily_stats` → след deploy показва 0, докато `/api/dashboard/data` показва реалните ~42k. Същият клас като #3, но за трафик (не за пари). | MED | ✅ да | дълг |
| 11 | `/api/v1/quickstart` съдържа твърдо `amount_usdc: 0.003` (днес съвпада с реалната цена на най-евтиния маршрут). | LOW | ✅ да (съвпада) | дълг |
| 12 | `request_log` живее на ефимерния диск на Render (единствената таблица, която deploy трие). | MED | ✅ да | дълг (решение на собственика) |
| 13 | Заседнало копие на проекта на диска: `Desktop\проекти\проекти\kristo-intelligence-6` (без `.git`, `main.py` с друг хеш) — риск да се редактира грешното дърво. | LOW | ✅ да | дълг (изтрий ръчно) |
| 14 | **Whale сканът носеше СЪЩИЯ бъг като sales.** `chunk_blocks = max(50, …)` + default 250 **без halving**. Измерено срещу публичния Base RPC: network-wide прозорец от **250 блока → HTTP 500**, а ≤100 минава и съдържа реални данни (**100 блока → 5 072 трансфера, 701 от тях ≥ $50k**). Т.е. всеки chunk гърмеше на първата заявка → **платеният** `/api/v1/whaleflow` не можеше да върне НИТО един ред. | **HIGH** | ✅ да (живо: 0 реда, watermark `null`) | **ФИКСНАТО** — 0 → **2 904 кита** за 360 блока |
| 15 | **Whale backfill-ът стоеше ЗАД `retro_scan(days=30)` в същия thread.** `retro_scan` пише watermark-а инкрементално, докато обхожда ~1.3M блока → след всеки deploy платеният whale маршрут стоеше в „сканът не е стартирал" с часове. | **HIGH** | ✅ да (живо: `scan_not_started`, watermark `null`) | **ФИКСНАТО** — собствен thread |
| 16 | Счупен whale скан беше **неразличим** от здраво празно („чакаме кит") — платена услуга, която мълчи за собствената си повреда. | MED | ✅ да | **ФИКСНАТО** — ново честно състояние `scan_failed` + последен опит/грешка на екрана |
| 17 | Whale сканът прави по един `eth_getBlockByNumber` на всеки блок-с-кит (за честен timestamp) → ~0.3s/блок; 24ч backfill = часове. | MED | ✅ да | смекчено (backfill ограничен на 1ч; live increment е ~30 блока/цикъл) — batch timestamp-и = дълг |

**Няма отворени CRITICAL/HIGH.** Всичките шест HIGH находки са фикснати в този deploy
(виж §3). Останалите 11 са в „дългове" — не са дупки в плащането.


### 3. Фиксовете в този deploy
- **Фънъл:** `challenges_today`/`paid_today` вече четат `cur_today`; `/api/v1/whaleflow`
  е добавен във `FUNNEL_ROUTES` (+ тест, че списъкът съвпада точно с `X402_PAID_ENDPOINTS`).
- **Payer binding (разширение на H2):** бързият път вече изисква
  `recorded_sender == proof.payer`. Ако продажбата е записана без платец (`unknown`),
  бързият път НЕ се ползва и се минава на on-chain проверка (`from_addr == payer`).
  Нов guard вид `h2_payer_mismatch` (+ тест с реален публикуван хеш).
- **`/api/dashboard-stats`** чете от persistent store-а (RAM само като fallback);
  history редовете носят и старите RAM ключове (`amount_usd`, `timestamp`), за да не
  се счупи никой консуматор.
- **Таблицата „Реални маршрути"** се рендира от API-то — цената на екрана вече е
  физически същият списък, който издава 402. Тест: за всеки маршрут реалният 402
  `amount` == обявената цена × 1e6.
- **Guard телеметрия:** нова durable таблица `guard_events` (C1 replay, C2 дълбочина,
  H2 binding/платец) — лампата в „СТАЖИ" показва последния блокиран опит от таблица,
  а `lock_alive` е реален write-probe на `payment_guards`.
- **Whale scanът** (находки #14–#16): махнат `max(50, …)` (env-ът вече важи буквално),
  default 100 блока (най-широкото измерено работещо), **адаптивно halving** при
  отказан прозорец (250→125→62→…→1, същият start блок, нула пропуснати диапазони),
  собствен background thread (`whaleflow-scan`), и durable телеметрия
  `whaleflow_effective_chunk` / `whaleflow_last_attempt` / `whaleflow_last_error`.
  Backfill-ът е ограничен на 1ч (живият increment е това, което прави потока live).
  Доказателство: `scripts/_t2_whale_fix_proof.py` → **2 904 кита за 360 блока**,
  `state=live_data`, `effective_chunk=100`, `last_error=None`.

### 4. Тестове
`205 → 228 PASS`. Нови: `tests/test_dashboard_v2.py` (17 теста за новите секции,
честното празно при китовете, фънъл регресията, съгласието на двете повърхности),
`test_a_published_tx_hash_cannot_be_claimed_by_another_payer` (находка #2) и 5 теста
за whale скана (halving при отказан прозорец, env-ът не се вдига, `scan_failed`,
изчистване след успешен скан, записан опит).
Локална пред-deploy проверка: `scripts/_t2_local_render_check.py` (node --check на
JS-а + всички section id-та + числата); одит-доказателства:
`scripts/_t2_routes_price_check.py` (фантомната $0.05), `scripts/_t2_whale_width_sweep.py`
(250 → HTTP 500, ≤100 → 701 кита), `scripts/_t2_whale_fix_proof.py` (0 → 2 904).

### 5. ЗАЩИТИ, спазени в този deploy
`payTo` / endpoint / цени / каноничният v2 challenge — НЕПОКЪСНАТИ. Логиката на
гардовете само се засили (payer binding е ново ограничение, не облекчение).
Всички числа на екрана излизат от таблица или от веригата; нула статични цени.





## 🔴 ДЕН НА ИСТИНАТА (13.09) — плътните хешове от веригата, 2 root-cause бъга, гардове C1/C2/H2

### 1. Веригата е единственият източник — 8 трансфера, $0.028 (НЕ $0.026)
Всички предишни бележки за продажбите бяха ЧАСТИЧНО РЕКОНСТРУИРАНИ (съкратени
хешове). Изтеглени са ПЪЛНИТЕ 66-символни хешове директно от веригата и всеки е
крос-верифициран срещу независим RPC receipt (`eth_getTransactionReceipt`,
status=1, block, amount) — `scripts/_verify_seed_chain.py` → **ALL 8 VERIFIED ✅**.

Източник (1 заявка, пълна история на получателя, нула пропуски):
`https://base.blockscout.com/api?module=account&action=tokentx&address=0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f&contractaddress=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
→ 8 реда, ВСИЧКИ входящи, ВСИЧКИ USDC, нула други токени по адреса.

| # | tx (пълен хеш) | $ | блок | плател | клас |
|---|---|---|---|---|---|
| 1 | `0xb8a52dcd61962af4b2d15d6f166b6c5038bbe9c40c171b37508a199bd40a45e6` | 0.005 | 50783187 | 0x7e6b…2b1c | canary |
| 2 | `0xf5cff040a181876efd3434f63c55cbafba970e3dd0860edd36c06c17e6993016` | 0.003 | 50787936 | 0x7e6b…2b1c | canary |
| 3 | `0x1cf2a51caa352a19435c682ff88a8bf3f4121929d9d22101329db243fc91f971` | 0.003 | 50798541 | 0x7e6b…2b1c | canary |
| 4 | `0x0cc98ef96e5e5d9a12f3021b77e2a67bba9439745b9eaf61efdb414491295a5f` | 0.003 | 50820464 | 0x7e6b…2b1c | canary |
| 5 | `0xb881f9dcdd0df72bf1853ebbf3328cf8d140ae8966871136b6cbe0cf852d5fc3` | 0.003 | 50943758 | 0x4db7…02b7 | **external** |
| 6 | `0x770d21789f4c5034bf923252fe97088b2c2475f856946e64e13dc36c271c0627` | 0.003 | 51033391 | 0x54e1…f4e0 | sampler (crawler) |
| 7 | `0xc30268e387e84d449f433772ed11e9ab751394d80bfc310a9c7dbb5e604cce03` | 0.003 | 51200083 | 0x7e6b…2b1c | canary (Chet whale) |
| 8 | `0x98f63a29c54255003405c270763734da127c95b21fc533ff79564be1e9d55e2a` | 0.005 | 51221690 | 0x902dcf34…9256 | **external** |

**ЧЕСТНАТА СУМА = $0.028 / 8 tx / 2 external платци** (canary 5 = $0.017,
external 2 = $0.008, sampler 1 = $0.003).

**РАЗМИНАВАНИЯ спрямо предишните бележки (докладвани веднага, без закръгляне):**
- ❌ очаквано $0.026 → ✅ реално **$0.028**: две от плащанията са **$0.005**, не
  $0.003 (tx #1 и tx #8; 0.005 е цената на `/api/stats` и `/api/bot-status`).
- ❌ очаквани **3 external** → ✅ реално **2** (0x4db7 + 0x902dcf34).
- ❌ `0xA19F` (09.09) **НЯМА плащане към нашия payTo** — проверени са всичките ѝ
  78 token трансфера: нула докосват получателя. Това е високочестотен
  арбитраж/sweeper профил (десетки USDC преводи към различни адреси), НЕ клиент.
  Записът „трети независим реален клиент“ по-долу е НЕВЕРЕН.
- ❌ `0x5f64…` — такъв плащащ адрес НЕ съществува във веригата за този
  получател; не е включен в манифеста.
- ✅ Твърдението „0x902dcf34 = първи път купувач“ се ПОТВЪРЖДАВА (tx #8, $0.005,
  блок 51221690) — това е истинският 2-ри external платец.

### 2. Двата root-cause бъга на „0 продажби“ (не един!)
Досегашната диагноза (dRPC филтрирани getLogs над 10 блока) беше само ПОЛОВИНАТА.
Намерен е и вторият, който сам по себе си нулираше таблото:
- **БЪГ 1 — `chunk_size = max(50, …)`** в `dashboard_store.scan_window`:
  твърдият под на 50 блока **поглъщаше** `SALES_CHUNK_BLOCKS=10` (env-ът се
  вдигаше до 50 = точно ширината, която free RPC-тата отказват) → всяка заявка
  гърмеше → `break` → watermark-ът засядаше.
- **БЪГ 2 — `NameError` в `_block_timestamps`**: функцията ползваше `Web3` без
  да го импортира в собствения си scope (`scan_window` го импортира само за
  своя frame). Т.е. **при първата реално намерена продажба** сканът гърмеше
  ПРЕДИ записа на watermark-а → „RPC-то връща трансфера, а таблото пак не
  записва и не мърда“. Това е точният механизъм на „0 sales при жив loop“.

**Фикс:** под 1 (env-ът вече важи буквално) + **адаптивно halving** (провален
chunk → същият start блок се повтаря с половината ширина: 5000→2500→…→9→1,
никога не се пропуска диапазон, никога фалшива дупка) + `from web3 import Web3`
в `_block_timestamps`. Телеметрия: `meta.sales_effective_chunk` (реално
приетата ширина).

### 3. Seed-възстановяване (deploy-устойчиво, приоритет 0)
`integrations/verified_sales.py` = манифестът с 8-те ПЪЛНИ хеша (единствен
източник на истина). `DashboardStore.seed_verified_sales()` ги вписва
идемпотентно (`INSERT OR IGNORE`) и **при всеки boot на приложението** — Render
файловата система е ефимерна, затова deploy вече НЕ може да нулира onchain
числата. Scan-намерен ред никога не се презаписва от seed-а; watermark НЕ се
пипа. Плюс admin рут за ремонт без deploy: `POST /api/admin/seed-sales`
(`X-Admin-Token`), който връща РЕЗУЛТИРАЩИТЕ числа за проверка.

### 4. Плащателни гардове C1 / C2 / H2
- **C1 — durable replay lock.** Досегашният guard беше RAM `set` →
  **рестарт/deploy възкръсяваше похарчено доказателство** (достъп без ново
  плащане). Сега таблица `payment_guards` в SQLite: `INSERT OR IGNORE` по
  `tx_hash` (PRIMARY KEY) = атомарен check-and-claim през процеси и нишки.
  Приложен и на двата рейла (X-Payment-Proof и стандартния PAYMENT-SIGNATURE).
- **C2 — 12 потвърждения.** `_confirmations_ok()`: доказателство в върха на
  веригата (1 conf) не е settlement — може да бъде реорганизирано. Fail-closed
  (неизвестен блок = невалидно). Env: `MIN_PAYMENT_CONFIRMATIONS` (default 12)
  за proof рейла; `MIN_STANDARD_PAYMENT_CONFIRMATIONS` (default 1) за синхронния
  facilitator рейл — 12 там би блокирало всеки spec-клиент за ~24 сек.
- **H2 — endpoint binding.** Proof с поле `endpoint` работи САМО на своя път:
  $0.003 за `/api/stats` не отключва `/api/v1/signal`. Legacy proof без полето
  остава валиден (със single-call семантиката на C1). Отказва се ПРЕДИ RPC и
  преди консумация (доказателството не се изгаря от погрешен път).
- Бонус: proof рейлът вече пише РЕАЛНИЯ блок в историята (не 0) — поправя
  забележката на PayAPI за `block_number: 0`.

### 5. Whale flow — ПРОМОТИРАН в публична витрина (условие 4 изпълнено)
`GET /api/v1/whaleflow` вече е в `REAL_X402_ROUTES` → появява се в
`/.well-known/x402.json`, `/api/v1/agents`, `/api/dashboard-stats`,
`/api/mcp/manifest` и в таблицата „Реални маршрути“ на таблото (6 маршрута).
Основание: **платеният canary МИНА** — tx
`0xc30268e387e84d449f433772ed11e9ab751394d80bfc310a9c7dbb5e604cce03`,
блок 51200083, **$0.003** (= точно цената на whale flow) от 0x7e6b… (Chet /
PayAPI верификатор) към bound-натия получател. Демо SKU-то `whaleflow-radar`
ОСТАВА извън публичните повърхности — затова SKU-гардът е стеснен до точната
SKU идентичност (`whaleflow-radar` / `WhaleFlow Radar`), за да не тригерва
реалния маршрут `…/whaleflow`. Публичното име на продукта е „Whale Flow
(Live Base Feed)“, за да не се бърка със SKU-то.

### 6. DeepSeek audit — бележка
Одиторските точки от DeepSeek се препокриват с горните гардове и вече са
адресирани в код: **replay/идемпотентност → C1** (SQLite, оцелява рестарт),
**reorg / непотвърдено плащане → C2** (12 conf, fail-closed), **обвързване на
плащането към ресурса → H2** (endpoint binding), **„deploy нулира числата“ →
seed манифест** (възстановяване от веригата при всеки boot). Остава отворено
(извън този обхват): persistent disk за `request_log` — решението е на
собственика; вариант (б) външен store е най-евтин.

### 7. Тестове
`tests/test_payment_guards.py` — 14 нови теста: C1 (два пъти същото
доказателство → 401; replay ОЦЕЛЯВА симулиран рестарт; атомарност на claim-а),
C2 (прагове 12/11/1 + отказ на receipt в върха + приемане на погребан),
H2 (bound proof на чужд път → 401 без консумация; legacy без поле работи),
**регресия за БЪГ 1** (`SALES_CHUNK_BLOCKS=10` не се вдига до 50) и **регресия
за БЪГ 2** (halving вместо засядане, `effective_chunk=9`), + seed манифестът
възпроизвежда $0.028/8 и е идемпотентен + admin рутът. Плюс изолация на
`dashboard_db` в `test_integration`/`test_connectors` (durable guard-ът вече иска
собствена база, за да не „изгаря“ фиктивни хешове между пусканията).
**Пълен пакет: 205/205 PASS.**


## 📌 ПОСТОЯННИ ОТБЕЛЕЖКИ (05.09, инструкция на собственика — валидни за цялата оставаща история на проекта)
- ✅ **ИЗПЪЛНЕНО И ПОТВЪРДЕНО:** разписката на Chet + линкът към статията — изпратени. НЕ се включват повече в „остава за човека".
- ❌ **ПРЕМАХНАТО:** X постът — обявен за мъртъв от собственика. Не се споменава в планове/табла.
- 🗄 **ПАРКИРАНО:** loopA мостът — готов текст в `LOOPEEMAIL_PACKAGE.md`, чака канал. Не е мъртъв, но не е активен ход.
- ✅ **ПУБЛИКУВАНО УСПЕШНО:** Smithery.
- ⏳ **Glama:** чака човешки преглед — билет **#130688574**.
- ⏳ **PulseMCP → 🛑 ПРИЕМА СПРЯНО (проверено на живо 07.09, pulsemcp.com/submit):** „Apologies, submissions and changes are temporarily paused… We are not accepting new MCP server or client submissions right now" (Last updated: September 3, 2026 — паузата е от 03.09). **Опция за БЪДЕЩЕ (без изпълнение, решение на собственика):** препоръката на сайта е да публикуваме в **Official MCP Registry** (registry.modelcontextprotocol.io) — „That is the best first step even when we are not paused, and we will pick it up automatically once we are back" — PulseMCP щяха да ни вземат автоматично при връщането си. Забележка: Registry вече е обвързан и с PayAPI потока („през PayAPI"), така че ръчното подаване е отделен, по-късен ход.
- 🐋 **Whale flow построен (09-10.09, ДАВАЙ на собственика) — чака canary.**
  `GET /api/v1/whaleflow` — жива лента с USDC трансфери ≥ WHALE_THRESHOLD
  (env, default $50k, прагът се чете при всяка заявка), honest labels
  (known/watchlist или „unknown", нула измислици), нова таблица
  `whaleflow_events` + watermarks в dashboard_state.db, 60s инкременти в
  scan loop-а, честен fail-retry (failed chunk → watermark спира до последен
  успешен). Цена $0.003, каноничен v2 challenge със selling description.
  **Условие 4 спазено: НЕ е в discovery/каталози/манифести/README** (тест
  guard). **Блокер за данните:** публичните Base RPC-та НЕ носят network-wide
  USDC логове (mainnet.base.org → 500, 1rpc/publicnode → 0 лога) — трябва
  `BASE_RPC_URL` с getLogs капацитет (напр. безплатен Alchemy/Infura/dRPC
  ключ) → env промяна на Render, БЕЗ deploy. До тогава маршрутът връща
  truthful празен списък. Canary: чака собственика (имейлът се пише заедно).
- ⚙️ **0x54E163e9… → market_crawler (08.09, fingerprint):** 325 различни получатели / 1281 tx / $11.32 за 30 дни — клас: непрекъснат индексатор (като 0x6777). Плати ни $0.003 на signal маршрута (08.09 08:28 UTC, tx 0x770d2178…) = **HEARTBEAT „в набора", НЕ launch сигнал**. Добавен в `KNOWN_PAYERS` като `market_crawler_54e1`; очаква се като редовен heartbeat. `external_unique_payers` остава честен = 1 (само човека 0x4dB7). Мониторът печата launch и heartbeat като отделни редове.
- 🐋 **ВЪЗСТАНОВЯВАНЕ НА ПРОДАЖБИТЕ (11.09) — диагноза и ускоряване.** dRPC free
  мълчаливо връща ПРАЗНО за recipient-филтрирани getLogs над ~10 блока
  (доказано живо: 1-блокова заявка → 1 лог ✅; 10-блокова → ✅; 250-блокова →
  400/празно). Затова watermark-ът вървеше с 0 намерени продажби.
  **Фикс:** SALES_CHUNK_BLOCKS=10 (env на Render) — chunk-овете вече са в
  лимита и реалните трансфери се намират (локално потвърдено: canary блок
  50783187 → 1 лог ✅ през drpc; pokt recipient 10-блок → 1 лог ✅).
  **Catch-up в ход:** 10-дневната история (43200 chunk-а по 10 блока) се
  сканира прогресивно от scan loop-а (~6-12 часа до пълното възстановяване
  на 7-те продажби: 4 canary + 2 external + 1 crawler heartbeat).
- 🎯 **НОВ ВЪНШЕН ПЛАТЕЦ (12.09 17:05 UTC):** wallet `0x902dcf34…` плати
  **$0.005** (= /api/stats цена) — **fingerprint: 0 изходящи USDC за 30 дни,
  класификация HUMAN** = **ПРЪВ ПЪТИ КУПУВАЧ** (не crawler, не sampler, не
  оператор-профил). Това е **трети независим реален клиент** след 0x4dB7 и
  0xA19F.
- 🗓 **МЕСЕЧЕН ПРОТОКОЛ (редове, в този ред):** 1. `python scripts/competitor_recon.py` (пазарен скен) · 2. `python scripts/listing_monitor.py` (band/рангове/касa/MCP) · **5. `python scripts/ap2_radar.py` (AP2 радар — след recon и listing_monitor)**. AP2 радарът гледа САМО публичните артефакти на Agent Payments Protocol (google-agentic-commerce/AP2 + a2a-x402: комити, релийзи, WG патерни, цензус серия) — изход: `docs/AP2_RADAR.md`. **AP2 Slack (wg-tax, wg-domain-discovery) е ЧАСТЕН и НЕ се сканира** — чете го собственикът на око, месечно; скриптът гледа само публичните GitHub артефакти, без идентичности.
- 🔄 **RPC РЕЖИМ (11.09): бавен безплатен — платен режим блокиран от платежен
  проблем, за препроба по-късно.** RPC bake-off (11.09): Alchemy free =
  **10 блока/getLogs** (неползваем за backfill); drpc free = wildcard getLogs
  работи на 250-блокови chunk-ове (61-154 лога) но flaky (408/500 на 1k+); pokt
  = макс 50 блока; publicnode/blastapi/meow = празни/400. **BASE_RPC_URL =
  base.drpc.org** на Render (без карта) + WHALEFLOW_CHUNK_BLOCKS=250.
  Урок: failed chunk НЕ се пропуска — watermark спира до последен успешен
  блок и се повтаря (и за продажбите, и за whale). Catch-up на 30-дневната
  история върви бавно (drpc free pace ~50-165 blk/min) — продажбите се
  доливат прогресивно; за production pace → Alchemy PAYG.
  Deploy-ът в 11:13 UTC изтри `data/` (без persistent disk контейнерът се
  създава наново). Резултат: request_log нулиран („чисти заявки" важат от
  последния deploy), НО **onchain_sales се само-възстанови за секунди**
  (retro scan 30 дни от веригата → 0.023/7tx с верните етикети, вкл. новия
  crawler клас). Значи: **onchain слоят е deploy-устойчив ПО ДИЗАЙН** (веригата
  е източникът на истината), request_log — не. **Опции за постоянен request
  log (решение на собственика):** (а) Render persistent disk (платен addon),
  (б) външен store (напр. Supabase free), (в) приемаме ефемерност — чистите
  дневни числа важат от последния deploy.
- 🔗 **PayAPI MCP bridge (08.09, по имейл на Chet):** README + demo README сочат
  PayAPI MCP входа (`payapi.market/mcp`, JSON блокът на Chet 1:1) — причина:
  **двупосочна откриваемост** (агентите в warehouse-а на пазара намират нашите
  маршрути, а нашият README сочи листинга). Kristo е live на PayAPI, discovery
  без такси, плащането върви директно на нашия payTo.
- ✅ **РЕШЕНИЕ (07.09, собственик): Whale flow feed — ОДОБРЕН за изграждане**
  като следващия (единствен) нов продукт. Условия: **(1)** тръба = съществуващият
  on-chain скенер (competitor_recon логика), без нови системи; **(2)** canary-доказан
  ПРЕДИ листинг; **(3)** един нов продукт на вълна; **(4)** НЕ влиза в нито един
  каталог/манифест, докато не е готов реално. Спецификация-чернова:
  `docs/WHALE_FLOW_SPEC.md` (чака „давай" от собственика — никакво строене преди това).
  Контекст: терминът whale е #1 от 1 (празна ниша), WhaleFlow Radar беше фалшивия
  SKU — сега строим реалната версия.
- 🗄 **kristo-travel-api → PRIVATE (07.09, изпълнено през GitHub API с owner
  акаунта):** причина — README със ГРЕШЕН wallet адрес (`0xd4cdA980…`),
  сосящ нашия Render API URL + стари цени → риск за марката преди листингите.
  Регистрирано и в `LISTING_CHANNELS_AUDIT.md`. Ако собственикът реше да го
  върне публично — ПЪРВО изчистване на README (верен wallet/линкове/цени),
  отделно решение тогава.
- **Правило за докладите:** под „остава за човека" се пишат САМО неща, които реално не са свършени.
- **LAUNCH SIGNAL дефиниция (в кода):** САМО нов/неизвестен платец. Известните sampler/crawler wallet-и (`0xC59E…`, `0x6777…`, канарките `0x7e6b…`) = HEARTBEAT „в набора", никога launch сигнал.
- 4th paid canary CLEAN: $0.003 on GET /api/v1/signal, tx `0x0cc98ef96e5e5d9a12f3021b77e2a67bba9439745b9eaf61efdb414491295a5f` — price_usd + reasoning confirmed in paid body on all 4 tokens, confidences back to 0.78/0.72/0.61/0.45, NO stale note. Fields noted on the existing verification row (not a new product). Listing stays live.
- Scoreboard: 4/4 paid canaries settled on-chain, 2 verified routes, ZERO payment-layer incidents across all four tests (every finding was data-layer, all fixed)
- Engineering phase CLOSED for signals route: no proactive work until a paying buyer asks. All effort → distribution (BlockRun decision pending, outreach days 2-5, MCP registry)

## 🗺 Планове при събития (пазят се предварително — при събитието се изпълняват, не се импровизира)

- **OPERATOR REPEAT протокол:** при второ плащане от 0x4dB7/0xA19F —
  1 час тишина (никакви имейли), после сигнал към стратегическия
  съветник, outreach план за operator deal ($0.01–0.05 tier,
  NEW_OPERATOR_ANALYSIS), мониторът логва честотата на връщане.


## Session 2026-09-08 UTC (awesome-remote-mcp-servers — PR ПОДАДЕН)
- 🚀 **PR #10 ПОДАДЕН:** https://github.com/punkpeye/awesome-remote-mcp-servers/pull/10 — „Add Kristo Intelligence — DeFi trading signals MCP server (x402 on Base)" (клон add-kristo-intelligence → main; един запис в 💰 Finance секцията, азбучно: Fruit Stand → Kristo → Octagon; markers ⚡ 🔓 💰; без Glama значка — следва в follow-up).
- 🟢 **CI ЗЕЛЕНО:** `check-submission: success` + бот етикет **`endpoint-ok`** (нашият /mcp е отговорил на initialize handshake проверката); втори етикет `missing-connector` — очаквано, с коментар да добавим Glama connector значка (план: след claim-а от #130688574).
- Канал: punkpeye/awesome-remote-mcp-servers (ново, 2⭐ — remote-only MCP списък; правилата: public URL + initialize + Streamable HTTP/SSE; т.нар. 🤖🤖🤖 fast-track НЕ е ползван).
- Чакаме: човешки преглед/merge. Следващи ходове по каналите непроменени (Glama claim, #1081 решение, whale flow чака „давай").

## Session 2026-09-07 (канали за листинг — одит + 3 действия)
### Канали — истински статуси (проверено през GitHub API на 07.09; детайли: docs/LISTING_CHANNELS_AUDIT.md)
| PR / канал | Истински статус |
|---|---|
| awesome-mcp-servers **#12799** | ❌ **ЗАТВОРЕН 29.08** (не merged) — причина на punkpeye: „adds multiple servers, one per PR". **Старите бележки „#12799 Open" бяха ГРЕШНИ** — коригирани в DISTRIBUTION_STATUS / VISIBILITY_PLAN / MARKETING_KIT |
| awesome-mcp-servers **#11557** (travel-api запис) | ❌ **ЗАТВОРЕН 07.09** (не merged) — неактивност (32 дни); изисквания: Glama submit + claim + quality score. С_PR-ът вече е безпредметен — travel-api е private |
| awesome-mcp-servers **#13219** | ✅ **ОТВОРЕН от 30.08** — НАШИЯТ чист PR (1 файл, 1 ред, Finance & Fintech). ⏰ **Дедлайн ~01.10** по 32-дневното правило за неактивност |
| awesome-x402 **#1308** (v6) | ✅ **ОТВОРЕН** от 24.08, без ревю |
| awesome-x402 **#1081** (travel-api запис) | ✅ **ОТВОРЕН** от 31.07 — ⚠️ РИСК: сочи repo-то, което днес стана private; PR-ът вероятно ще бъде затворен от maintainer-а сам или да го затворим ние ( решение на собственика) |
| Glama (билет **#130688574**) | ⏳ чака човешки преглед; НЕ сме листнати (проверено: 0 резултата); след одобрение → claim с GitHub → quality score → значка |
| PayAPI Market | ✅ LIVE, band unscored/baseline (compute чака Chet) |

- ✅ **Действие 1:** `kristo-travel-api` → **private** през GitHub API (gh, owner акаунт; 0 stars/forks — никой не е засегнат; анонимен GET → 404). Причина: грешен wallet в README, сочи нашия API URL.
- ✅ **Действие 2:** счетоводна поправка — този блок + корекции в DISTRIBUTION_STATUS.md, VISIBILITY_PLAN.md, MARKETING_KIT.md (махнати старите „#12799 Open" твърдения).
- ✅ **Действие 3:** GLAMA_REPLY.md — добавен абзацът от одобрената рамка (Streamable HTTP + „tell us exactly what" + awesome-mcp-servers зависимост) с бележка: Димитри го праща като follow-up коментар в отворения билет #130688574.
- **Остава за човека (обновено 07.09 вечерта):** (1) ~~Glama follow-up в #130688574~~ ✅ **ИЗПРАТЕН ДНЕС (07.09) — потвърдено от собственика**; (2) при Glama одобрение — claim в glama.ai с GitHub; (3) решение за #1081 (затваряме ли сами); (4) ~~PulseMCP ръчно подаване~~ 🛑 **ОТПАДА — приема спряно от 03.09** (опция за бъдеще: Official MCP Registry, без изпълнение).

### Финална проверка на човешките задачи (07.09)
| Задача | Статус | Доказателство |
|---|---|---|
| **Каталог чистка: 8 SKU премахнати от публичните повърхности (07.09)** | ✅ ИЗПЪЛНЕНО | причина: демо адаптер без реален execution (PRODUCT_AUDIT.md); изчистени: /.well-known/x402.json + /x402 (сега = 5-те реални маршрута), /api/v1/agents (същото), /agents → 302 към /dashboard, products в /api/dashboard-stats (5 реални маршрута), табло — нова секция „Реални маршрути". Демо адаптерът ОСТАВА в кода (main.py playground) но никъде не се обявява. Връщат се САМО като реални продукти (жив execution зад SKU). Вътрешната аналитика (catalog_store/admin metrics) е непокътната. payTo/платени endpoints/x402 логика — недокоснати. 171/171 теста (7 нови за чистката) |
| Разписка към Chet | ✅ ИЗПЪЛНЕНО | ПОСТОЯННИ ОТБЕЛЕЖКИ (горе): „разписката… изпратени. НЕ се включват повече в остава за човека" |
| Линк към статията за Chet | ✅ ИЗПЪЛНЕНО | същият ред — и двете изпратени |
| Follow-up към Glama (билет #130688574) | ✅ ИЗПРАТЕН ДНЕС (07.09) | по потвърждение на собственика в задачата (нотификацията/коментарът се виждат само в неговия Glama акаунт — от мен не е проверяем) |
| Smithery Publish | ✅ ИЗПЪЛНЕНО | ПОСТОЯННИ ОТБЕЛЕЖКИ: „ПУБЛИКУВАНО УСПЕШНО: Smithery" |
| travel-api → private | ✅ ИЗПЪЛНЕНО | GitHub API PATCH (07.09); анонимен GET → 404 |
| foresight-oracle weekly | ✅ ИЗКЛЮЧЕН | API: state = `disabled_manually` (потвърдено анонимно) |
| PulseMCP — сайтът отворен? | 🛑 **НЕ — приема СПРЯНО** | жива проверка 07.09: pulsemcp.com/submit → „submissions and changes are temporarily paused" (от 03.09). Формата съществува, но не приема. Опция за бъдеще (без изпълнение): Official MCP Registry по препоръка на сайта |
| $79.02 / Stripe | 🗑 отпаднало | собственик: фиктивни демонстрационни данни — не се проверява |
| X пост | 🗑 премахнато | собственик: мъртъв канал — не се проверява |

### Странични проекти
- 🏆 **BAND ПРИСТИГНА (седмичен монитор 07.09):** PayAPI compute-ът е пуснал оценка — **band = established, score = 69.7** (computed_at 06.09 19:31 UTC). Това затваря третия слой на подредбата (query match ✅ → verified routes ✅ → **band ✅**). Ранг q=signals: 3 → **2** от 7; q=defi остава **#1** от 3; whale #1. Receiver scan: LAUNCH сигналът 0x4dB7… остава единственият external (1 tx, $0.003, 7-дневен прозорец). Таблото на живо вече показва band/score (PayAPI секция). Състояние: docs/monitor_state.json.
- 🛑 **foresight-oracle: weekly workflow ИЗКЛЮЧЕН (07.09, през GitHub API с owner акаунта).** workflow `weekly` (id 345373591, `.github/workflows/weekly.yml`) → state **`disabled_manually`** (потвърдено анонимно през API). Причина: GLM балансът в bigmodel.cn е изчерпан — последните 2 седмични исполнения са failure (31.08 и 07.09), проектът е неактивен. **Начин за връщане:** `gh api -X PUT repos/hristovdimitri2-hub/foresight-oracle/actions/workflows/345373591/enable` + зареждане на баланс в bigmodel.cn. Файлът weekly.yml е запазен непокътнат.


## Session 2026-09-02 (second verified route + reviewer fixes)
- 🏆 PayAPI ran a SECOND paid canary on GET /api/v1/signal: 0.003 USDC settled on-chain, tx `0xf5cff040a181876efd3434f63c55cbafba970e3dd0860edd36c06c17e6993016` (block 50787936) → listing now has TWO verified routes (/api/stats + /api/v1/signal), status stays live
- Reviewer fixes shipped: `price_usd` was always null (publish layer read `d["price"]` instead of `d["price_usd"]`) and signals carried no `reasoning` (note only repeated the price)
- NEW: `TradingAgent.evaluate()` emits one-line `reasoning` per decision (narrative driver + live-data state + first risk flag); publish layer factored into `main._publish_agent_signals()` (numeric `price_usd`, `reasoning`, sorted by confidence) — 130/130 tests (3 new in tests/test_signal_route.py)
- Next: deploy to Render, reply to Chet (draft ready), confirm he re-runs the canary; x402scan re-index of /api/v1/signal still pending
- Ops complete (02.09): Render API keys ROTATED (old chat-exposed keys deleted; new key in secrets/render_api_key.txt, gitignored, verified via API); BlockRun founder contacted directly on Telegram (@1bcmax) with endpoint + on-chain proof; Outreach Day 1 done (GitHub Issue #1 on AnthonWinther/Trading_bot)
- Full Render audit passed: latest deploy fcb4f96 LIVE, service not_suspended, 20 env vars intact (incl. CDP pair, WALLET_PRIVATE_KEY, ADMIN_API_TOKEN), /health ok, /api/v1/signal 402-armed, openapi 11 paths
- 🏆 3rd paid canary (02.09): Chet paid another $0.003 — confirmed price_usd numeric + real reasoning ("the difference between a number and a signal"), prices within 0.13% of CoinGecko; listing stays live, route stays verified
- Reviewer found follow-up bug: every signal was taxed exactly 10% confidence with note "stale cached price, age=0s" — fresh (age 0) cache entries were labelled "stale". Root cause: get_prices exception-fallback labelled any allow_stale hit as stale without checking age; TradingAgent penalized on state alone. Fixed BOTH layers: coingecko.py now labels sub-TTL fallback entries "cached"; trading_agent has STALE_FLOOR_SECONDS=60 (age<60 is never stale) — 132/132 tests (2 new regression tests replicating his exact observation)
- Sentinel false-alarm bug found & fixed (2026-09-03, self-caught): every Render cold start sent bogus "New payment received +0.01" carrying the WHOLE receiver balance (baseline compared against 0.0; the 4 real canaries = 0.014 USDC made every wake-up "a payment"), duplicated per worker, and `:.2f` formatting hid micro-payments. Fixed in services/sentinel.py: silent baseline + state persisted to shared file (worker dedupe), 4-decimal formatting, startup announcement gated to once/UTC day. On-chain check confirmed the only real incoming transfer in the window was Chet's 4th canary (tx 0x0cc98ef9… from tester 0x7e6b…2b1c) — 134/134 tests (1 new regression test)
- CoinGecko demo key added by user (Render env COINGECKO_API_KEY) — but verification revealed market_data.py (bulletin/dashboard path) never attached the key (only the agent's client did) → still 429ing, stale age 997s post-deploy. FIXED in market_data.py: `_coingecko_headers()` attaches `x-cg-demo-api-key` — deployed 5e49cb0, verified live: dashboard-stats source=real_api, coingecko cached/ready after cold-cache fetch — 133/133 tests (1 new header regression test); Telegram bulletin now shows "CoinGecko: live данни" (user-confirmed screenshot)
## Session 2026-09-03 (verification + label semantics clarified — NO code changes)
- ✅ Verified live 14:23 EET: `/health` ok, wallet ready (last_block 50822926), receiver balance 0.014 USDC = exactly the 4 canaries (Sentinel fix holding — zero phantom payment alerts), dashboard trending/DEX pairs real
- ⚠️ LABEL SEMANTICS (не е регресия): Telegram bulletin редува „CoinGecko: live данни" (в секунда на успешен live fetch) и „🦎 кеширан snapshot (N мин.)" (всички bulletin-и в рамките на 15-мин TTL през кеша) — и двете са ЗДРАВИ. „Cached" тук е честното sub-TTL етикетиране от фикса за Chet, НЕ 429-fallback. Проблемът изглежда така: „⚠️ кеширани данни (N мин.); live обновяването е временно ограничено" (stale, >15 мин без успешен refresh) или възраст ≥10+ мин редовно. Демо ключът работи: bulletin-и на 03.09 показват age=1 мин. (предишно: 997 сек + stale предупреждение)
- ✉️ **Chet отговори (03.09, 14:15 UTC)** на въпроса за newsletter/X feed: НЯМА платено featured slot и НЯМА newsletter за individual листинги. Какво съществува: live каталог + agent search (това, което агентите реално куерят), listing страницата, окупационни X постове от @ParkerChet при ново verified нещо — „If I put Kristo in an X post it will be because the route is useful, not because a slot was bought". **Покани blurb on file** („tight: what GET /api/v1/signal returns, price, Base USDC") → blurb готов в OUTREACH_KIT.md §6, остава изпращането като reply. Билетът „чакане на отговор от Chet" ЗАТВОРЕН.
- 🔍 **Conversion одит (03.09) — 3 теча в слоя откриваемост, фикснати и LIVE (deploy 8fd0d82→ следващ):** `/.well-known/x402` обявяваше само 3 ресурса (version 1, легаси X-Payment-Address инструкции) — **липсваше /api/v1/signal** (= причината x402scan re-index да виси!); `/api/mcp/manifest` нямаше signal/arb; quickstart `cheapest_call` казваше 0.005/stats вместо 0.003/signal. FIX: 5 ресурса + реални rails инструкции, manifest с signal 0.003 + arb 0.005, cheapest_call коригиран — 135/135 теста (1 нов: test_well_known_x402_lists_flagship_signal_and_arb_routes). Комити: ca685a4 (фикс) + 8fd0d82 (docs). Верифицирано LIVE.
- 📦 **Колона B изпълнена:** docs/MCP_SUBMISSIONS.md (PulseMCP/Glama/Smithery готови пакети, ред: PulseMCP първи); OUTREACH_KIT §7 (Ден 3 X пост, Ден 4 Telegram, Ден 5 BlockRun follow-up с чисто затваряне).
- 🏁 **Нишка PayAPI/Chet НАПЪЛНО ЗАТВОРЕНА (03.09, 19:29 UTC):** blurb-ът е ИЗПРАТЕН (17:00) и ПРИЕТ на файл — „Blurb is on file. Listing stays [link]. No extra fee and no promised post. If I mention the route on X it will use this copy." → X пост от Chet е възможен, но merit-only и без обещание; НИКАКВО следване по тази нишка. Потребителят да прати само 1-редично thanks (Gmail quick reply) и толкова.
- 🛠 **Колона B+ (03.09 вечер, по потребителски мандат „имплементирай каквото прецениш") — 3 артифакта, 140/140 теста, push-нати:**
  - `scripts/competitor_recon.py` — on-chain разузнаване (web3/Basescan-RPC, без API ключ): входящи USDC трансфери към който и да е payTo адрес, агрегирани по платец, с noise-филтър (≥1000 USDC отделно) — отговор на „хилядите обаждания на конкурентите". Самотест срещу нашия receiver (7 дни, 302k блока): точно 4 канари/0.014 USDC от 0x7E6b…2b1c — съвпада 1:1 с on-chain записите (5 нови regression теста)
  - `examples/demo_agent/` — ПУБЛИЧЕН reference x402 клиент (discovery → 402 challenge → pay & retry с X-Payment-Proof; --pay = реален settle с test wallet). Smoke тестван live: discovery 200/5 ресурса, challenge = каноничен v2 (exact, eip155:8453, 3000 атомни). Двoен роля: trust-артефакт за билдъри + E2E self-paid тестът, който никога не беше завършен
  - Атрибуция в main.py: `_live_request_log` сега пази user_agent/referer/funnel; НОВА `/f/<канал>` route (302 → storefront, каналът се логва) — каналите започват да се разграничават от краулери шум
  - VIP $29 tier остана (корекция на одита): Stripe checkout flow реално grants 30-дневен unlimited — manifest-ът не лъже
- 🔬 **ПЪРВО ON-CHAIN РАЗУЗНАВАНЕ — изпълнено (04.09), цел: „Currency & Crypto API" (first-party PayAPI листинг, $0.001/call):**
  - payTo `0xFFc458dB291b4ABcE020fE3de4f91F2770E537b1` — получен БЕЗПЛАТНО през 402 challenge-а им (POST без плащане → каноничен v2 отговор с accepts[0].payTo). Техниката: „пътуване до касата без пазуване"
  - **Резултат (7 дни, ~302k блока): 159 микроплащания / 0.287 USDC общо / 15 уникални платци / среден чек $0.0018 / 11 repeat-payers.** Топ-3 платци (48+42+25 tx) = 72% от транзакциите — концентрационната хипотеза от одита потвърдена
  - **Големият извод: лидерът на PayAPI прави ~$1.2/МЕСЕЦ.** Микро-пазарът x402 на PayAPI е pre-PMF — реални платци има (15 wallet-а!), но в абсолютни стойности всички сме на нула. Извод: не оптимизирай микро-цени — целта остава 1-5 операторски сделки + позициониране за растежа на екосистемата; листингите са дистрибуционни експерименти, не revenue engine
  - Доклад: docs/_recon_currency_api_7d.json (публични верижни данни). Caveat: payTo може да облужва няколко first-party listing-а
- 🏷 **KNOWN_PAYERS в recon скрипта:** 0x7e6b…2b1c = `chet_payapi_verification` — канарките се отчитат отделно, `external_unique_payers` винаги показва само реални външни платци (2 нови теста, 142/142)
- 🔒 **ПЛАТФОРМЕН ИНВАРИАНТ (04.09, по инструкция на PayAPI оператора Chet Parker):** `payTo = 0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f` и endpoint структура — **НИКОГА не се променят**; reliability score-ът на PayAPI включва „payTo still matches" + health history, а downtime ТРИГЕРВА recompute (провалените samples влизат в band). Keep-alive ping на `/health` на 5–10 мин = постоянна инфраструктура. Всяка промяна по endpoint-а минава през въпроса „чупи ли score-а?"
- 📊 **`scripts/listing_monitor.py`** — седмичен пулс: reliability band (от `/agent/get`) + ранг по 8-те агенски термина; диф против `docs/monitor_state.json`; аларма при band/ранг/описание промяна. Baseline 04.09: band=unscored (compute за нас предстои), defi **#1**, whale #1, signals #3, eth/ondo/kaito/degen ABSENT (титлата чака Chet). Валидация на модела на Chet: query match доминира — unscored листинг бие scored-69.6 за q=defi благодарение на името
- 🚪 **Streamable HTTP транспорт ДОБАВЕН (05.09, разрешено от собственика):** POST /mcp (JSON-RPC: initialize/tools/list/tools/call/ping; DELETE=204 stateless) — ADDITIVE, SSE непокътнат, payTo/платежните пътища недокоснати (инвариант). Причина: Smithery (Arcade.dev) изисква Streamable HTTP. Живо проверено: POST initialize=200, tools/list=3 tools, SSE=200. README пренаписан на английски за каталоги (0 wallet адреса, regex), старото е в README.bg.md; GLAMA_REPLY.md готов. 152/152 теста (10 нови).
- ✍️ **Заглавна промяна приета от Chet** (тикери на първия ред); description fix — следващият compute ще ни сложи и band; с това трите слоя на подредбата (query match → verified → band) са адресирани, 2 от тях лично от оператора
- 🎉 **ПЪРВИ ВЪНШЕН ПЛАТЕЦ (06.09, 06:41 UTC):** wallet `0x4dB7AAFb…E02B7` плати **0.003 USDC** за GET /api/v1/signal (tx 0xb881f9dc…, блок 50943758) — ВЕРДИКТ C: LAUNCH SIGNAL. Fingerprint: умерен multi-API оператор (100 payTo/30d, 145 tx, $1.67), плаща и на house касата 18× → източникът му включва PayAPI. НЕ е Chet/сampler/crawler. Дашборд: 107 requests днес, продажбата записана (double-record козметиката потвърдена live). Band все още unscored. Пълен анализ: `SALE_DIAGNOSIS.md`. Следва: „Число" имейл към Chet (една линия) + наблюдение дали 0x4dB7 се връща (оператор deal тригер).


## Session 2026-08-29 (growth sprint)
- Storefront fixes LIVE: dashboard advertises receiver (not hot wallet), honest micro-prices, favicon
- x402scan: 11 resources registered; mystery-agent audit 23/23 (docs/MYSTERY_AGENT_REPORT.md)
- NEW: services/connectors.py — connector registry (9 connectors, 8 active) + STANDARD x402 EIP-3009 rail (X-PAYMENT via facilitator verify+settle) + L402 bridge parser + /api/connectors panel + /api/v1/quickstart onboarding (108/108 tests)
- PayAPI: resubmission IN REVIEW; extra.name fixed to "USD Coin" per validator
- Outreach kit ready: docs/OUTREACH_KIT.md (BlockRun data-source listing = top priority)
- ⚠️ COORDINATION: two AI sessions push to this repo — agree on one session at a time
## Resume checklist (in order)
1. Render → Resume service, verify /health = 200
2. CRITICAL: receiver wallet 0xd4cdA900...08f has NO confirmed private key owner → rotate BOUND_BASE_FEE_RECEIVER to owned MetaMask address + redeploy BEFORE accepting any payment
3. Re-verify all 3 directories (x402scan, nohumans, PayAPI) — x402 v1→v2 migration may have changed validator expectations
4. E2E self-paid test (external wallet → 0.005 USDC → X-Payment-Proof → 200) — never completed
5. Compare x402scan vs baseline below — if ecosystem 2x+ grown, open for business
# 🏆 MILESTONE — FIRST REAL SALE (2026-09-01)
- PayAPI Market canary PASSED: 0.005 USDC settled on-chain from external tester wallet `0x7e6b6556322c4e26c567a867964ac793f5ee2b1c`, tx `0xb8a52dcd61962af4b2d15d6f166b6c5038bbe9c40c171b37508a199bd40a45e6` (block 50783187)
- Root-cause chain fixed across 5 canaries: CDP JWT claims (kid/sub = bare key id + `uris` claim), CDP body schema (`paymentPayload`+`paymentRequirements`), v2 exact = signed-transaction payload (not EIP-3009)
- Server accepts BOTH client shapes: v2 transaction payloads (local signer recovery + broadcast) and EIP-3009 (self-broadcast transferWithAuthorization) — 124/124 tests
- Known minor: dashboard sales counter double-records settle+monitor for the same tx (dedupe pending — cosmetic)
- Pending: PayAPI listing approval + price drop to 0.005; BlockRun email; outreach campaign

## State at freeze
- Prices: single source config (stats/arb 0.005, rug 0.003, whale 0.01, sales 0.05) — verified live
- Directories: nohumans 3x VERIFIED, x402scan 11 resources (commits ebb993d..d6eeb12, 77/77 tests), PayAPI pending resubmit (ready)
- x402scan baseline 27.08.2026: $1.33M/30d volume, 21k sellers, 17.68M tx
- Known gaps: receiver key unconfirmed, E2E uncompleted, WALLET_PRIVATE_KEY in Render is burned/published address 0xd4cdA980 — replace with funded test wallet key ON RESUME, never fund 0xd4cdA980
- Env in Render: AGENT_AUTO_EXECUTE=false, KRISTO_FREE_TIER_LIMIT=0, BASE_FEE_AMOUNT_USDC=0.005
## Freeze decision
Income priority — freelance/CV track active. Project waits in Git at zero cost. All context for resume is in this file.
