# CONTEXT & ROADMAP — kristo-intelligence-6

**Изготвен:** 2026-11-03 · **Час:** 13:10–13:35 (Europe/Sofia)
**Ревизия, за която е валиден:** `9089ba5` — „audit-b1: stop key leaks" (2026-11-03 12:56:40 +0200)
**Локален корен:** `C:\Users\AlienWare\Desktop\projects\kristo-intelligence-6`
**Отдалечено:** `github.com/hristovdimitri2-hub/kristo-intelligence-6` · `origin/main` = **`ae216f2`** (2026-11-01)
**Репозиториум:** 352 комита, първи `619f005` (2026-08-19) · 29 untracked записа · лиценз MIT

> **Обхват и ограничения:** документът е **само за четене** — консолидация на вече извършена работа. Не е променен нито един файл по кода, x402 хедърите, цените, `payTo`, защитените конфигурации или `secrets/`. Няма `git add/commit/push`. `secrets\` и `.env` не са отваряни. Всяка стъпка в §5 е **предложение**.
>
> **Защо това е важно:** `main` → авто-деплой на Render. Всяка промяна по `main` е продукционна промяна. Затова планът е разделен на вълни с изрични гейтове, а не на „списък със задачи".

---

## 0. Резюме за ръководството

**Проектът е технически зрял, но търговски неизправен по три независими причини — и трите са поправими.**

| # | Проблем | Същност | Тежест |
|---|---|---|---|
| 1 | **Платеното се раздава безплатно** | 3 от 6 платени SKU-та се получават с $0 през `/api/dashboard-stats` и `/api/dashboard/data`. Paywall-ът е декоративен. | 🔴 Блокиращ за бизнес модела |
| 2 | **Подписът по плащането не е авторитет** | `accepted.amount` (от клиента) замества подписаната `authorization.value` → подплащане; при нечетим receipt доставката минава **fail-open**. | 🔴 Финансов риск |
| 3 | **Продуктът не може да бъде намерен от купувач** | 3 индексируеми HTML страници в цялото приложение; нула OG/Twitter/canonical/JSON-LD; 0 analytics; `/f/<channel>` построен, но неизползван. | 🟠 Нулев органичен трафик |

**Три факта, които изискват решение днес:**

1. **Два комита не са в продукция.** `origin/main` = `ae216f2` (01.11), а HEAD = `9089ba5`. Непубликувани са:
   - `9089ba5` — **спира изтичането на ключове** (F-13/F-14/F-15/F-30);
   - `66a0ce4` — **CDP Bazaar listing trigger** (02.11), който е предусловието за попадане в основния x402 индекс.
   Тъй като `push` = авто-деплой, двете вървят заедно — решение на собственика, не автоматично действие.

2. **Има противоречие за продукционния сървър.** `Procfile:1` и `Dockerfile` казват `gunicorn --workers 1 --threads 8`; `TASK.md:107` (снимка от 30.09) твърди, че продукцията работи на **`python main.py`** (werkzeug dev сървър) и че Procfile/gunicorn **не се ползва**. И двете не могат да са верни. Това променя целия анализ на конкурентността (§3.4). Изисква проверка в Render dashboard.

3. **Финансовото състояние е ясно и малко.** Он-чейн: **16 реда / $0.052**; от тях **3 външни човешки портфейла / $0.011**, 7 sampler реда / $0.021, 6 canary реда / $0.020. Stripe: $34.80 върнато, **нетно $0.00**. Пазарът (самоизмерен): лидерът в PayAPI прави ~$1.2/месец при 2–4 купувача. **Трафик сам по себе си не решава нищо** — трябва точното малко трафик: агенти и оператори, които плащат.

**Най-важният извод от цялата история:** единственият **потвърден външен платен трафик** идва от **машинно-четима директория за агенти** (`nohumans.directory` → 3 × $0.005 от `nohumans-scout`, 30.10), докато усилието е било хвърляно в човешки канали (Reddit, HN, Product Hunt), които **никога не са използвани**. Стратегията следва да последва доказаното: **машинни повърхности + измеримост**, а човешките канали — едва след като има какво да се покаже.

---

## 1. Източници, обхват и методология

### 1.1 Използвани източници

| Източник | Обем | Състояние |
|---|---|---|
| `docs/PROJECT_CHRONOLOGY.md` | 264 реда / 23.5 KB | Прочетен. **Спира на 28.09** (маркер `<!-- CONT -->`) — не покрива последните ~5 седмици |
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | 573 реда / 98 KB | Прочетен изцяло (индекс F-01…F-40, §8 план, §9 ограничения, Приложение A) |
| `PROJECT_STATUS.md` | 2633 реда / 272 KB | Прочетени актуалните секции (02.10 MIGUEL, ПАЗАРНА РЕКОНСТРУКЦИЯ, CURRENT STATE, OPEN ITEMS). Останалото е HISTORY |
| `TASK.md` | 107 реда | Прочетен. **Снимка от 30.09** (`3661419`) — остарял |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | 457 реда / 54 KB | Прочетен (собствена изработка от 03.11) |
| `git log` / `git show` | 352 комита | Извлечена историята 27.09 → 03.11 (70 комита) + диффът на `9089ba5` |
| Технически SEO одит (паралелен агент) | — | Завършен; доказателства от кодовите генератори |

### 1.2 Какво НЕ можа да бъде направено

- **`C:\Users\AlienWare\AppData\Roaming\chatbox\` — директорията НЕ съществува.** Точка 3 от заявката (анализ на чат логове/експорт) е **неизпълнима** на тази машина: пътят не съществува, няма експорт. Алтернативата е използвана изцяло: `PROJECT_STATUS.md` + `docs/PROJECT_CHRONOLOGY.md` + `TASK.md` + `git log` дават същата информация с по-висока достоверност (правилото на архива: „при разминаване с чат историята вярва HISTORY").
- **Продукционна проверка.** Няма достъп до Render dashboard/логове/БД. Твърденията за продукцията са от документи и от кода, маркирани като `[ДОКУМЕНТИРАНО]`.
- **Платен E2E тест.** Не е извършван (изисква финансиран портфейл).

### 1.3 Правило за четене на този документ

- `[ПРОВЕРЕНО]` — проверено в кода/git/на живо на 03.11.
- `[ДОКУМЕНТИРАНО]` — идва от документ в репото, без независима проверка.
- `[ЗА ПРОВЕРКА]` — противоречие между източници; изисква човешко потвърждение.

---

## 2. Кратко обобщение на извършената историческа работа

### 2.1 Фази на проекта

| Период | Фаза | Какво е постигнато | Източник |
|---|---|---|---|
| **19.08** | Генезис | `619f005` „Initialize Kristo Intelligence Number 6" + внасяне на санитизиран snapshot като независим проект. Идеята: платен DeFi market-intelligence API за AI агенти на Base, плащане с x402 (402 → USDC → 200), без signup/абонамент/ключове | git, `TASK.md:11-21` |
| **27.08** | **FREEZE** | Проектът спира (приоритет: freelance/CV). Събира се `State at freeze` + `Resume checklist`. Известни дупки: receiver ключ непотвърден, E2E непровеждан, изгорен `WALLET_PRIVATE_KEY` | `CHRONOLOGY:12-21` |
| **29.08** | Growth sprint (resume) | Storefront фиксове LIVE (receiver, честни микро-цени, favicon); ново `services/connectors.py` — registry от 9 конектора + **STANDARD x402 EIP-3009 rail** през facilitator + L402 bridge + `/api/connectors` + quickstart. **108/108 теста**. Правило: две AI сесии не пушат едновременно | `CHRONOLOGY:23-31` |
| **02.09** | 🏁 **Първа реална продажба** | PayAPI canary: **0.005 USDC** от външен tester (`0x7e6b…2b1c`, блок 50783187, 13:28:41 UTC). Root-cause веригата закърпена през 5 canary-та (CDP JWT claims, CDP body schema, v2 exact). Сървърът приема и двете форми. **124/124 теста** | `CHRONOLOGY:33-44` |
| **03.09** | **ФАЗА ЗАВЪРШЕНА** | „Само проверка, нито една кодова промяна." Обявено: **product verified → GO-TO-MARKET**. Оттук започва търговската фаза, която е и настоящият проблем | `CHRONOLOGY:51-54` |
| **05–08.09** | Правила и канали | Записани „ПОСТОЯННИ ОТБЕЛЕЖКИ" + „Планове при събития" (валидни за цялата история). Пълен одит на листинг каналите (`LISTING_CHANNELS_AUDIT.md`). Подаден PR в `awesome-remote-mcp-servers` | `CHRONOLOGY:56-78` |
| **06.09** | Първи външен клиент | **`0x4dB7` плати 0.003 USDC** за `/api/v1/signal` — вердикт „LAUNCH SIGNAL", fingerprint = умерен multi-API оператор, не crawler | `CHRONOLOGY:62-68` |
| **13.09** | 🔴 „Ден на истината" | Плътни on-chain хешове, **2 root-cause бъга**, гардове **C1/C2/H2**. Публикувана `GUARD_METHODOLOGY`. Одит 2 (Stripe/CRM/entitlements). Табло 2.0 | `PROJECT_STATUS:2117-2303` |
| **14–15.09** | 🔴 **INCIDENT** | Платещ външен клиент (crawler `e3ba`) **отказан от C2 race → HTTP 401** след плащане (tx `0x06b4c8f2…58ce7`, блок 51313253, $0.003). Фикснат `8bdd45f` на 15.09. Гардовете никога не са отказвали **човешки** клиент; това е единственият отказ | `PROJECT_STATUS:34-46` |
| **16.09** | Първи човешки платец | Първо плащане от човек (Starter $29 през Stripe) — крайъгълен камък на търговската валидация | `[ДОКУМЕНТИРАНО]` |
| **20–25.09** | Одити и F1 гейт | Одити #4/#5; диагностициран и фикснат `c2_reorg_detected` loop (`8bdd45f`); дефиниран **F1 гейт** — „златната стъпка": реален E2E превод с demo портфейл. A1 живо, A2 no-pay E2E зелено, **липсва само финансиран ключ** | `PROJECT_STATUS:193-288` |
| **27–28.09** | 🔧 Стабилизация | Реструктуриране на `PROJECT_STATUS.md`. Три коренни фикса: **flaky тестове** (`a3d4362` — production нишки не стартират под pytest), **placeholder-hash** (`9418c8f` — лаг-claim никога не записва `000…0`, с регресионен тест), **env-guard** (`ad3f642` — спира двойния boot → край на дублираните Telegram alerts). **422/422 теста** | `PROJECT_STATUS:26`, `TASK.md:36-40` |
| **29.09–02.10** | 📊 Числата стават твърди | Корекции по дати (по production DB + блокови timestamps). **Miguel (ReturnCheck)** = **3-ти външен човешки платец** (01.10 17:46:35 UTC, 0.003 USDC, блок 52043724, директен ERC-20 transfer). Каса: **16 реда / $0.052** (on-chain баланс съвпада 1:1). Честна метрика: **3 души + 2 машини**. Първи бизнес диалог (обратен тест). **426/426 теста** | `PROJECT_STATUS:1-20` |
| **08.10** | 🔒 Сигурност | `54a7ba3` — **9 security hardening фикса** (durability на rejected_signals, coingecko кеш, demo nonce, XFF fallback, logging, sentinel atomic, adopt nonce check, arb boundary, pinning) | git |
| **11.10** | ⚡ Производителност | `858ad4c` — sargable day window + unified funnel scan + индекс `idx_request_log_path`: **cold build ~41 s → ~1 s**. `ecd2522` — 60 s TTL кеш за публичния dashboard payload. `4fb8c27` — A+ guards: poll receipt 4×2 s, след което fail-open override | git |
| **13–24.10** | 🔧 x402 коректност и доверие | `10a3be0` Cache-Control no-store + CORS само на 402; `137b85a` openapi без x402 securityScheme; `10a3be0`… `12192bb`/`db6c8fc` **envelope-body-mirror** (402 тялото не се сортира, за да съвпада с хедъра); `386dc07` каноничен EIP-55 `payTo`; `16a3791`/`4c61a8d` **x402 Trust профил, badge, claim 4/4**; `c99be97` Sentinel седмичен доклад с 6 пазарни числа; `a1eeb79`/`3279f56` certifi bump/pin; `e2dc7ea` mcprush badge; `1912350` блог пост x401/x402 | git |
| **30.10–01.11** | 📇 Листинги и валидация | `c1bbde4` README броят тестове 423 → **550**. `a6004bf` — validation labels (nohumans/organic), input schema в x402.json, 6 безплатни sample route-а, **550/550 зелени**. `648089c`/`6c46745`/`ae216f2` — временен `/.well-known/nohumans-claim` challenge (добавен, ротиран, премахнат след успешен claim) | git |
| **02.11** | 📇 **Bazaar trigger** | `66a0ce4` — „echo extensions + resource in x402 payment payload (CDP bazaar listing trigger)". **НЕ е в продукция** (виж §0) | git |
| **03.11** | 🔒 **audit-b1** | `9089ba5` — „stop key leaks": `.dockerignore` + `secrets/` + `*.mp4`; `redact_rpc()` на RPC грешките; `_redact_tg()` за Telegram токена; маскиране на env стойности в `_t2_render_env_check.py`. **НЕ е в продукция** | git |

### 2.2 Какво реално е постигнато (честната равносметка)

**Силни страни (реални, проверими):**
- Работещ x402 платежен рейл с **две релси** (v2 `PAYMENT-SIGNATURE`/`PAYMENT-REQUIRED` + legacy `X-Payment-Proof`), EIP-3009 `transferWithAuthorization`, facilitator верига PayAI→CDP със self-broadcast fallback.
- **Потвърдени реални плащания** от външни портфейли (5 различни външни адреса), с on-chain доказателства и блокови номера.
- Изградена **防护 срещу replay** (durable lock в `payment_guards`), изчисление на EIP-712 локално, проверки `auth.to == payTo` и `asset`.
- **550 теста**, покриващи платежния плик, гардовете, реорг-детекцията, secret hygiene.
- Изградени **машинно-четими повърхности**: `/.well-known/x402`, `/.well-known/x402.json`, `agents.json`, `/mcp.json`, `/openapi.json`, `/llms.txt`, `/robots.txt`, `/sitemap.xml`, `server.json` за официалния MCP Registry.
- **MCP сървър** с 3 инструмента, листване в официалния MCP Registry (active, v6.0.0) и Glama connector.
- Публикуван **npm пакет** `kristo-x402-client@1.0.0`.
- Няколко външни потвърждения: x402 Trust **grade B**, PayAPI Market листинг, 1 merge в awesome-списък.
- **Реален платен трафик от машина** през `nohumans.directory` (3 × $0.005).

**Слаби страни (също реални):**
- **Нулева търговска валидация.** 3 човешки платеца за 2.5 месеца, общо $0.011 от външни човешки адреси; Stripe нетно $0.00.
- **Продуктът се самоподкопава** — платените данни са налични безплатно (§4, F-01).
- **Видимост почти нулева** — 3 индексируеми HTML страници, 0 OG тагове, 0 analytics (§4.4).
- **Документацията изпреварва реалността.** „11 resources", „zero payment incidents", „Rug-risk checks", „$29 VIP unlimited" — всички са неверни или неизпълнени, а са в публични повърхности.
- **Многократно повторени грешки в процеса:** подаване на PR без изпълнено предусловие (Glama quality score), записване на успех преди проверка (Smithery днес е 404), блокиране на готов outreach зад инженерен гейт.

---

## 3. Текущо състояние

### 3.1 Проверени факти (03.11.2026)

| Показател | Стойност | Статус |
|---|---|---|
| HEAD | `9089ba5` (03.11 12:56) | `[ПРОВЕРЕНО]` |
| `origin/main` | `ae216f2` (01.11) | `[ПРОВЕРЕНО]` |
| Непубликувани комита | **2** (`66a0ce4` Bazaar trigger, `9089ba5` key-leak fixes) | `[ПРОВЕРЕНО]` |
| Общо комита | 352 (първи 19.08.2026) | `[ПРОВЕРЕНО]` |
| Untracked записи | 29 (вкл. двата нови одитни документа, diff-файлове, `kristo-intelligence/`) | `[ПРОВЕРЕНО]` |
| Тестове | **550 passed** (потвърден пълен прогон, 180.46 s, 1 DeprecationWarning) | `[ПРОВЕРЕНО]` |
| Платени рута | **6**: `/api/v1/signal`, `/api/stats`, `/api/arb/opportunities`, `/api/bot-status`, `/api/sales`, `/api/v1/whaleflow` | `[ПРОВЕРЕНО]` |
| Безплатни рута | 27 в allow-list + 6 `/sample` route-а | `[ПРОВЕРЕНО]` |
| Цени | signal 0.003 · whaleflow 0.003 · arb 0.005 · stats 0.005 · sales 0.005 · bot-status 0.005 (`config.py:75-83`) | `[ПРОВЕРЕНО]` |
| Free tier | `KRISTO_FREE_TIER_LIMIT` default **1** в кода; продукцията разчита на env **0** | `[ЗА ПРОВЕРКА]` |
| Приходи он-чейн | **16 реда / $0.052** — 3 външни човека / $0.011 · 7 sampler / $0.021 · 6 canary / $0.020 | `[ДОКУМЕНТИРАНО]` (02.10) |
| Stripe | $34.80 върнато, нетно **$0.00** | `[ДОКУМЕНТИРАНО]` |
| MCP инструменти | 3 (`get_market_stats`, `get_onchain_sales`, `get_bot_status`) | `[ПРОВЕРЕНО]` |
| Индексируеми HTML страници | **3** — `/` (en), `/launch` (bg), `/validation` (сирак) | `[ПРОВЕРЕНО]` |
| Open Graph / Twitter / canonical / JSON-LD | **0 от 9** шаблона | `[ПРОВЕРЕНО]` |
| Third-party analytics | **0** (няма gtag/plausible/umami/posthog и др.) | `[ПРОВЕРЕНО]` |
| npm сваляния | **37** / 30 дни (пик 119 в деня на публикуване) | `[ПРОВЕРЕНО]` |
| GitHub | 2 stars, 0 forks, 0 issues, 0 releases, **без `.github/`** | `[ПРОВЕРЕНО]` |
| Индексирани страници (DuckDuckGo `site:`) | **1** (началната) | `[ПРОВЕРЕНО]` |
| CDP Bazaar присъствие | **Непотвърдено** (първа страница: 46 записа, 12 доставчика, без нашия `payTo`) | `[ПРОВЕРЕНО]` |

### 3.2 Он-чейн и търговска картина

```
Приходи (он-чейн, 16 реда / $0.052)
├── Външни човешки платци:  3 портфейла / $0.011   ← реалната валидация
│     ├── 0x4dB7   06.09  $0.003  /api/v1/signal
│     ├── 0x902dcf (самостоятелен, без връзка с хъба)
│     └── 0xce4fbd 01.10  $0.003  (Miguel / ReturnCheck)
├── Sampler машини:         7 реда / $0.021
│     └── 0x4c29ec (промотиран, hub-fed 0x6302; 353 получатели/13 дни)
└── Canary (наши тестове): 6 реда / $0.020
```

- **Мигел (ReturnCheck)** е единственият **бизнес диалог** — предложи обратен тест (ние плащаме на негов endpoint), насрочен след финансиране на demo портфейла.
- **Клъстер хипотеза:** `0x6302` е hub-контракт, споделен фундър на `a19f`, `54e1`, `e3ba`, `4dB7` (седмични микросуми, двупосочни) → вероятно **един оператор зад клъстера**. Непотвърдено.
- **F1 гейтът** (реален E2E превод с demo портфейл `0xE50c5212…35763`) остава **отворен** от 25.09 — блокира го само човешко действие: депозит ≥ 0.003 USDC + газ.

### 3.3 Разминавания и остаряла информация `[ЗА ПРОВЕРКА]`

| Твърдение | Къде | Реалност |
|---|---|---|
| „Тестове 422/422" | `PROJECT_STATUS:26` | **550** (потвърдено) |
| „Тестове 423/423" | `TASK.md:31` | **550** |
| HEAD = `3661419`, 10 локални непушнати комита | `TASK.md:33` | HEAD = `9089ba5`, **2** непушнати |
| HEAD = `66a0ce4`, 351 комита, 29 untracked | одитен доклад:495 | HEAD = `9089ba5`, 352 комита |
| Продукцията работи на werkzeug dev сървър (`python main.py`), Procfile/gunicorn не се ползва | `TASK.md:107` | `Procfile:1` + `Dockerfile` CMD казват gunicorn. **Изисква проверка в Render** |
| „11 resources" | `README.md:112` | **6** в кода (`main.py:2183`) |
| „zero payment incidents" | `README.md:111` | Има INCIDENT 14.09 (401 след плащане) |
| „Rug-risk checks" | `README.md:21` | Няма такъв route (само неизползван import) |
| „$29 VIP — неограничен достъп" | `agents.json`, `/api/mcp/manifest`, npm README | **Не е имплементиран никъде**; има само $0.10 Telegram invite праг |
| „Free tier: 1 call per client" | npm README, `ai-plugin.json:1511` | Продукцията работи с `KRISTO_FREE_TIER_LIMIT=0` |
| „$0.05 USDC" / „USD 0.01" | npm README | Реално **0.003–0.005** |
| `settlement_status: "discovery_only"` + „settlement is not enabled in this preview" | `main.py:1944`, `main.py:2161`, `docs/x402-client-example.js:26-33` | Противоречи на „settled through the Coinbase x402 facilitator" (`main.py:4054-4058`, `discovery.py:1019-1020`) — **директно противоречие в публични повърхности** |
| „whaleflow sample = $0.005" | `discovery.py:440` | `config.py:83` = **0.003** |
| Порог за кит: $50k | `PROJECT_STATUS:2440`, `WHALE_FLOW_SPEC:19` | Кодът: **$5,000,000** (`dashboard_store.py:98`) |
| Хронология до „днес" | `PROJECT_CHRONOLOGY.md` | Спира на **28.09** (маркер `<!-- CONT -->`) |
| ICP: „retail crypto трейдъри" + Meta/Google ads | `marketing/offer-and-ad-strategy.md:6-11`, `launch/launch-plan-30d.md:43` | Различен продукт от agent-paid API-то |

### 3.4 Архитектурна топология (с отворения въпрос)

```
[ВАРИАНТ А — ако продукцията ползва Procfile/Dockerfile]
  1 процес · gunicorn --workers 1 --threads 8 --timeout 120
  → 8 нишки = ЦЯЛАТА HTTP способност (всяко блокиращо обаждане = −12.5%)
  → + ~11 background нишки в СЪЩИЯ процес

[ВАРИАНТ Б — ако продукцията ползва `python main.py` (твърдение в TASK.md:107)]
  1 процес · werkzeug dev server, app.run(host, port)
  → Flask подава threaded=True по подразбиране → НЕОГРАНИЧЕН брой нишки
  → dev сървър в продукция: без production hardening, слаба устойчивост
  → същите ~11 background нишки в процеса

И в двата случая: ЕДИН процес, споделено in-RAM състояние,
и ~11 фонови цикъла (monitor, dashboard scan, whale scan, agent, catalog,
stripe snapshot, arbitrage, sentinel, keep-alive, reorg-watch-per-call…).
```

**Последица:** и при двата варианта анализът за споделено състояние, глобален DB lock и блокиращи бюджети остава в сила. Разликата е в капацитета на HTTP слоя и в production-readiness на сървъра.

### 3.5 Инфраструктурен инвентар

- **Приложение:** Flask 3.1.3, 44 `@app.route` в `main.py` + 26 blueprint рута, 345 `.py` файла, `main.py` = 5859 реда.
- **Зависимости:** web3.py 7.16.0, psycopg[binary] 3.3.4 (Postgres, SQLite fallback), requests 2.34.2, `stripe==15.5.1`, `python-telegram-bot==22.8`, pytest 9.1.1, `cryptography>=42.0.0`.
- **Контейнер:** non-root потребител `kristo`, HEALTHCHECK на 30 s.
- **Документи:** `docs/` = 89 файла / ~0.57 MB (49 в SEO инвентара), 46 `.md`, 26 probe `.py`.
- **Отсъстващи артефакти:** `.github/` (изцяло), `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `render.yaml`, `docs/README.md` индекс, `scripts/seo/`.
- **Мъртви/неизползвани активи:** `templates/agent_playground.html` (наистина мъртъв — `/agents` прави 302 към `/dashboard` и никога не го рендерира); `docs/x402-client-example.js` (остарял и подвеждащ); `kristo-intelligence/` (untracked дубликат); `.kilo/worktrees/believed-dancer/` (пълен дублиращ worktree, игнориран само през `.git/info/exclude`).
  - **ПОПРАВЕНО (2026-11-12):** `templates/public_activity.html` НЕ е мъртъв и не бива да се трие. Рендерира се от `src/nexus/distribution.py:153` (`/api/public/activity?format=html`), а blueprint-ът се регистрира в `src/nexus/__init__.py:125`, извикан от `main.py:5408 mount_nexus_engine(app)`. Пропуснат е при одита, защото `grep render_template main.py` не вижда blueprint-ите.

---

## 4. Регистър на критичните дефекти

> Пълните доказателства (файл:ред) са в `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` §0 (индекс F-01…F-40).
> **Статус:** ✅ = адресиран в `9089ba5` (но **не е в продукция**); ⬜ = отворен.

### 4.1 🔴 P0 — блокиращи за бизнес модела (без тях таксуването е декоративно)

| ID | Дефект | Доказателство | Статус |
|---|---|---|---|
| **F-01** | **Платените данни се раздават безплатно.** `/api/dashboard-stats` се различава от платения `/api/stats` само по `recent_requests[-50:]`; `/api/dashboard/data` сервира история + китове + пълния `/api/sales` payload. **3 от 6 SKU-та са 100% заменими при $0** | `main.py:142-157, 3427-3428, 3986-3989, 5573-5582` | ⬜ |
| **F-02** | **`accepted.amount` засенчва подписаната `authorization.value`** → подплащане. Доказано: `accepted.amount=5000` + подписано `value=1` → precheck връща `[]`; нечислов amount прескача проверката | `services/connectors.py:195-200` | ⬜ |
| **F-03** | **Fail-open при нечетим receipt.** При грешка при четене на разписката платеното обаждане се **доставя**; `block_number`/`hash` остават `0`/`""`; `except` в confirmation проверката поглъща изключението и дава достъп | `main.py:3082-3110, 3132, 3158-3159` | ⬜ |
| **F-04** | **4 ЗАПИСА на безплатен GET.** `guard_stats()` прави INSERT/DELETE в `payment_guards` — таблицата на replay-заключването — на анонимно четящ рут, който dashboard-ът poll-ва на всеки 45 s, под **същия `_pg_lock`** като `claim_payment_tx` | `integrations/dashboard_store.py:1542-1555` | ⬜ |
| **F-05** | **Реорг никога не отменя кредитирано плащане** — `_detect_reorgs` само логва | `main.py:2631-2690`; `tests/test_reorg_watch.py` фиксира detection-only | ⬜ |
| **F-06** | **Приемане по nonce без проверка за дълбочина** (depth 1) | `main.py:2321-2435, 2484` | ⬜ |
| **F-07** | **Нула rate limit по платежния път**; газ-разходът се контролира от анонимен клиент; `maxFeePerGas = gas_price*2` без таван | `main.py:1406-1416, 3431-3523`; `connectors.py:350, 376` | ⬜ |

### 4.2 🟠 P1 — стабилност, производителност, изтичане на информация

| ID | Дефект | Доказателство | Статус |
|---|---|---|---|
| **F-08** | Един RPC доставчик (`https://mainnet.base.org`), без fallback, без cooldown при 429/`Retry-After` | `config.py:57` | ⬜ |
| **F-09** | Една споделена DB връзка под глобален lock, отваряна **без `connect_timeout`** | `dashboard_store.py:307, 334-340, 342-372` | ⬜ |
| **F-10** | `/health` зависи от DB → връща 503 → Render рестартира единствения worker → цикъл | `discovery.py:32-76` | ⬜ |
| **F-11** | `/mcp/sse` е безплатен и неограничен; пинира 1 от 8 нишки за ≥15 s → **пълен DoS с шепа заявки** | `discovery.py:665-717` | ⬜ |
| **F-12** | Неограничен thread-per-payment reorg watch + **нечанкнат `eth_getLogs(5000 блока)`** | `main.py:3217, 2321-2435, 2621-2628` | ⬜ |
| **F-13** | Суровият RPC текст (`rpc_error`) се публикува на **безплатен** рут | `main.py:643 → 3792 → 3986` | ✅ `redact_rpc()` приложен (`main.py:642/645/771/780/1143/1160/1230/1237`) — **в продукция: не** |
| **F-14** | Telegram bot token изтича в логовете през `requests` изключения (токенът е в URL-а) | `services/telegram_sales.py:72, 80-81, 198-212` | ✅ `_redact_tg()` приложен — **в продукция: не** |
| **F-15** | `secrets/` се bake-ва в Docker образа (`.dockerignore` без запис) | `Dockerfile:29` | ✅ `secrets/`, `*.mp4`, `kristo_paid_demo_clip*` добавени — **в продукция: не** |
| **F-22** | Статистическият агрегат: 12 заявки, 5 пълни сканирания; **528 ms при 46 301 реда** локално; в кода: „~783K реда, ~22 seq scans, измерени ~41 s на живо". Няма кеш на `/api/stats` и `/api/dashboard/data` | `main.py:3944-3945` | ⬜ |
| **F-23** | Бюджетите за блокиране по платения път надхвърлят `--timeout 120` | одит §4 | ⬜ |
| **F-24** | Stripe SDK: 80 s timeout × 3 retry-а на request пътя | одит §4 | ⬜ |
| **F-25** | `_stripe_payment_snapshot_loop` **без `try/except`** — едно изключение убива цикъла | одит §4 | ⬜ |
| **F-26** | `/api/launch/health` без auth | `main.py` | ⬜ |
| **F-27** | `/api/connectors` разкрива hot wallet адрес, `gas=` и вътрешен маршрут | `services/connectors.py:950-1034` | ⬜ |
| **F-28** | Render конфигурацията **не е версионирана** (`render.yaml` никога не е съществувал) | `git log --all -- render.yaml` → празно | ⬜ |
| **F-29** | Админ токенът пада към `SESSION_SECRET` при липса на собствен | одит §6 | ⬜ |
| **F-30** | Операторски скрипт принтира живи env стойности | `scripts/_t2_render_env_check.py` | ✅ маскиране добавено — **в продукция: не** |
| **F-31** | Липсващи индекси по `request_log(user_agent)`, `(source)`, `(funnel)`; неограничени in-RAM карти | одит §4/§7 | ⬜ |

### 4.3 🟡 P2 — документация, твърдения, хигиена

| ID | Дефект | Статус |
|---|---|---|
| **F-16** | `X-Payment-Proof` е препредаваем bearer токен върху публично публикувани данни | ⬜ |
| **F-17** | Едно плащане може да достави два пъти при конкурентност | ⬜ |
| **F-18** | `payment.amount_usdc` връща атомарни единици под име на USDC (5000 вместо 0.005) | ⬜ |
| **F-19** | Рекламираните цени дрейфват от 402 предизвикателството в **5+ повърхности** | ⬜ |
| **F-20** | „$29 VIP — неограничен достъп" не е имплементиран никъде | ⬜ |
| **F-21** | `FREE_TIER_LIMIT` по подразбиране 1; продукцията разчита на env променлива, която не е документирана | ⬜ |
| **F-32…F-40** | Дребни: количество/хигиена на документацията, противоречия между документи, мъртви активи | ⬜ |
| **F-33** | `/validation` публикува живи платени адреси и остаряло число `550/550` | ⬜ |

### 4.4 🟠 Видимост — констатации от техническия SEO одит

| ID | Дефект | Доказателство |
|---|---|---|
| **V-01** | **Само 3 индексируеми HTML страници** в цялото приложение. Няма `/pricing`, `/docs`, `/faq`, `/about`, `/mcp`, `/changelog`, `/guides`, `/blog`, нито per-route страници | SEO одит §8 |
| **V-02** | **0 Open Graph / Twitter Card / canonical / JSON-LD от 9 шаблона** — всяко споделяне е гол URL | `grep` = 0 съвпадения |
| **V-03** | **Sitemap-ът е счупен:** съдържа `/dashboard`, който има `<meta name="robots" content="noindex">` (приоритет 0.9, hourly!), и два 302 редиректа (`/agents`, `/nexus` → `/dashboard`); **пропуска** `/validation` и `/api/v1/quickstart`; няма `<lastmod>`; изброява `.txt`/`.json` като страници | `discovery.py:1387-1413`, `dashboard.html:6` |
| **V-04** | **`/validation` е сирак** — не е линкнат от нито един шаблон и липсва в sitemap-а | SEO одит §1 |
| **V-05** | **6 `/sample` route-а са невидими** — рекламирани само като `sample_url` в `/.well-known/x402.json`; липсват в sitemap, openapi, llms.txt и всички HTML | SEO одит §2 |
| **V-06** | `llms.txt` документира **само legacy `X-Payment-Proof`** релсата; списъкът с 402 хедъри пропуска `PAYMENT-REQUIRED`/`PAYMENT-SIGNATURE` | `discovery.py:1588-1596, 1617-1621` |
| **V-07** | **`settlement_status: "discovery_only"`** в две публични повърхности противоречи на „settled through the facilitator" в други две | `main.py:1944, 2161` vs `main.py:4054-4058`, `discovery.py:1019-1020` |
| **V-08** | `agents.json` изброява **5** endpoint-а (липсва `/api/v1/whaleflow`), `/.well-known/x402` — 6, README — „11" | `discovery.py:1416-1482` |
| **V-09** | `/mcp.json` дава **плоска цена 0.005** за всичките 6 инструмента → надтаксува signal/whaleflow (0.003) | `discovery.py:1026-1126` |
| **V-10** | `/api/mcp/manifest` съдържа **VIP $29** (човешки Stripe tier) в машинен manifest | `discovery.py:874-881` |
| **V-11** | **OPTIONS preflight на платените рута също получава 402** → счупва browser базирани x402 клиенти | `main.py:3379-3380` |
| **V-12** | npm README (в самия пакет) съдържа **остарели цени** ($0.05, $29 VIP, „1 free call") и само legacy релсата → „handles x402 paywalls automatically" е **невярно за spec клиенти** | `packages/x402-client/README.md` |
| **V-13** | `examples/demo_agent/demo_agent.py` е крехък: изисква 402, но при default `FREE_TIER_LIMIT=1` първото обаждане връща 200 → „UNEXPECTED status 200" и изгаря безплатното обаждане. Зависимостта от `KRISTO_FREE_TIER_LIMIT=0` е **недокументирана** | SEO одит §6 |
| **V-14** | Няма GSC/Bing verification, няма analytics, няма IndexNow/sitemap ping, няма `X-Robots-Tag` | SEO одит §9 |
| **V-15** | Един мъртъв шаблон (`agent_playground.html`; `public_activity.html` е ЖИВ — вж. бележката в инвентара по-горе) и един подвеждащ пример (`docs/x402-client-example.js`, твърди че сървърът не проверява proof хедъри — невярно) | SEO одит §1/§6 |

---

## 5. План за действие

> Всяка точка е **предложение**. Промени в продукция минават през вратата „push = авто-деплой".
> **Непокътнати инварианти** (виж §8): x402 хедъри и структура на плика, `payTo`/fee receiver, цените в `config.py`, `/.well-known/x402-trust.txt`, `secrets/` и `.env`.

### 5.1 🔒 Сигурност и платежна цялост

**Вълна S1 — P0, финансов риск (най-висок приоритет):**

1. **F-02 — подписът става авторитет.** Извличай сумата **само** от `auth.value`; отказвай при несъответствие с `accepted.amount`; отказвай **нечислови** amount-и, вместо да прескачаш проверката; препрочитай `Transfer` сумата от receipt-а преди грант (adoption пътят вече го прави правилно на `main.py:2419-2421`).
   - *Проверка:* тест, който подава `accepted.amount=5000` + подписано `value=1` → **трябва да върне 402/400**, не `[]`.
2. **F-03 — край на fail-open.** Една изрична политика: fail-closed след poll-а (401/425 с tx hash, както прави in-flight клонът `main.py:3144-3157`), или override **само** с независимо потвърждение. **Никога** изключение в confirmation проверката не бива да води до доставка.
   - *Проверка:* тест с mock receipt, който хвърля изключение → **не** трябва да има 200.
3. **F-07 — rate limit и бюджет по платежния път.** Лимит per IP **и** per signer; pre-check на USDC баланса на купувача преди broadcast; таван на `maxFeePerGas`; изнасяне на сетълмента извън request нишката.
4. **F-04 — махни записа от read пътя.** `guard_stats()` не трябва да прави INSERT/DELETE; пробата за живост се мести в background цикъл, а рутът чете последния резултат от кеширан read model.
5. **F-05 + F-06 — семантика на реорг.** Минимум: маркирай `onchain_sales` реда като `reorged` и го изключи от тоталите; добави проверка за дълбочина на adoption пътя по nonce.

**Вълна S2 — P1, изтичане на информация и защита:**

6. **F-26 + F-27** — админ guard за `/api/launch/health`; махни `payer wallet=`, `gas=` и CDP детайла от публичния `/api/connectors`.
7. **F-28 + F-29** — версионирай Render конфигурацията (или изрично документирай защо не); премахни fallback-а на админ токена към `SESSION_SECRET`.
8. **Разшири `tests/test_secret_hygiene.py`** да **открива** файлове по шаблон, вместо да проверява 5 поименно зададени (това е и препоръката на одита към комита `9089ba5`).
9. **F-16** — `X-Payment-Proof` е препредаваем; обмисли обвързване с IP/UA или къс TTL (продуктово решение).

**Вече адресирано (в `9089ba5`, но НЕ в продукция):** F-13 (redact RPC), F-14 (redact Telegram token), F-15 (`.dockerignore` + `secrets/`), F-30 (mask env).

### 5.2 ⚡ Производителност и устойчивост

**Вълна P1 — тесни места (по данни от одита):**

1. **F-22 + F-31** — един **кеширан read model с single-flight** за `/api/dashboard/data`, `/api/dashboard-stats` **и** платения `/api/stats`; индекси по `request_log(user_agent)`, `(source)`, `(funnel)`; агрегирай `payment_guards` в SQL и индексирай `consumed_at`.
   - *Контекст:* студеното изграждане е било ~41 s на живо при ~783K реда; локално 528 ms при 46 301 реда.
2. **F-09** — `psycopg_pool` + `connect_timeout` + `statement_timeout`; престани да държиш един глобален lock върху една споделена връзка (`dashboard_store.py:624` вече показва правилния модел).
3. **F-10** — `/health` да е **чисто liveness** (без DB); readiness — отделен рут. Това елиминира рестарт-цикъла.
4. **F-11** — изолирай и ограничи `/mcp/sse`: кап на едновременни сесии **+** rate limit. Безплатен неограничен SSE, който пинира нишка за 15 s, е най-евтиният DoS в проекта.
5. **F-23 + F-24 + F-25** — ограничи всеки блокиращ бюджет по платения път под `--timeout 120`; явни Stripe timeout-и и `max_network_retries=0` за request пътя; обвий тялото на `_stripe_payment_snapshot_loop` в `try/except`.
6. **F-08 + F-12** — списък от RPC доставчици с health ротация + process-wide cooldown с `Retry-After`; **един ограничен** reorg watcher с опашка вместо нишка на плащане; чанкни `getLogs` през вече съществуващия `_adaptive_get_logs`.
7. **Реши въпроса със сървъра** (§3.4): потвърди стартовата команда в Render. Ако продукцията наистина работи на werkzeug dev сървър → премини към gunicorn (Procfile вече е готов) **или** изрично документирай компромиса.

### 5.3 💰 Продукт и бизнес модел (коренът на проблема)

**F-01 е продуктово решение, не бъг — paywall-ът не може да се „поправи" при налично безплатно копие.**

1. **Реши кое поле реално се продава** и го махни от публичния read model на `/api/dashboard-stats` и `/api/dashboard/data`: история с `tx_hash`+`sender`, `whales`, market snapshot.
   - **Вариант А (препоръчан):** dashboard payload-ът остава агрегат (брой, сума, канали), а транзакционната история, самоличностите и whale feed-ът минават **само** през платените рута.
   - **Вариант Б:** dashboard payload-ът минава зад админ/session обхват.
   - **Вариант В:** приемеш, че dashboard-ът е маркетинг и не е SKU — но тогава махни `/api/sales`, `/api/stats` и `/api/v1/whaleflow` от платения allow-list, за да не е таксуването декоративно.
2. **F-19 — една цена, един източник.** Генерирай всички публични цени от `config.py`/`REAL_X402_ROUTES` вместо да ги дублираш в `agents.json`, `/mcp.json`, `ai-plugin.json`, openapi, npm README, `/.well-known/x402`.
3. **F-20 — махни фантомния VIP $29** от `agents.json`, `/api/mcp/manifest` и npm README (или го имплементирай — но не го рекламирай, докато не съществува).
4. **F-18** — преименувай `payment.amount_usdc` на `amount_atomic` или върни реални USDC.
5. **F-21** — документирай `KRISTO_FREE_TIER_LIMIT` в `.env.example` и реши стойността в продукция (0 заедно с работещ демо път, или 1 с честно описание).
6. **Затвори F1 гейта** — финансирай demo портфейла (≥0.003 USDC + газ) и пусни `python scripts/e2e_nopay_probe.py --pay`. Това е **единственото** нещо, което стои от 25.09 и блокира инженерната вълна по договорка.

### 5.4 📈 Видимост и трафик

> Пълният план е в `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md`. Тук е само кондензатът, подреден по зависимост.

**Вълна V1 — машинна коректност (преди всеки листинг):**

1. **V-07 — приведи `settlement_status` в съгласие.** Това е най-опасното противоречие: две публични повърхности казват „discovery_only", две — „settled through facilitator". Всеки агрегатор, който чете и двете, получава противоречие.
2. **V-08 — генерирай `agents.json` и `/mcp.json` от `REAL_X402_ROUTES`** (6 route-а, точни цени). В момента `agents.json` дава 5, `/mcp.json` — плоска цена 0.005.
3. **V-06 — `llms.txt` да документира и двете релси** (v2 `PAYMENT-SIGNATURE` като основна, legacy като fallback).
4. **V-10 — махни VIP $29 от `/api/mcp/manifest`.**
5. **V-03 — поправи sitemap-а:** махни `noindex` `/dashboard` и 302 редиректите; добави `/validation` и `/api/v1/quickstart`; добави `<lastmod>`.
6. **V-05/V-09 — добави 6-те sample route-а** в openapi и в безплатния списък на `llms.txt`; поправи `whaleflow sample = $0.005` → `0.003` (`discovery.py:440`).
7. **V-12 — поправи npm README** (цени, free tier, двете релси) и добави `scripts.test`, типове, `publishConfig`. Без това „handles x402 paywalls automatically" е подвеждащо.
8. **V-13 — направи demo пътя честен** при двата режима на free tier (не „UNEXPECTED status 200").
9. **V-11 — оправи OPTIONS preflight** на платените рута (402 на preflight чупи browser клиенти).

**Вълна V2 — човешка/органична повърхност:**

10. **V-02 — OG/Twitter/canonical/JSON-LD** в публичните шаблони + едно OG изображение 1200×630 (`static/og.png`). Най-евтината промяна с най-голям ефект върху CTR при споделяне.
11. **V-01 — добави индексируеми HTML страници:** `/pricing`, `/api-reference` (рендериран от openapi), `/how-x402-works`, `/status`, `/changelog`, + **6 per-route страници** (няма какво да се класира за самия продукт). Суровият материал е наличен: `CHALLENGE_DESCRIPTIONS` (`main.py:108+`), route метаданните (`main.py:2074-2135`), 6-те sample схеми (`discovery.py:356-505`), `/validation` фактите (`discovery.py:103-204`), `docs/QUICK_START.md`, `ARCHITECTURE.md`.
12. **V-04 — свържи `/validation`** от landing-а и го добави в sitemap-а (сега е сирак).
13. **V-14 — GSC + Bing verification, IndexNow ключ + `scripts/seo/ping_index.py`, sitemap ping.**
14. **Измеримост:** лек self-hosted analytics **или** разширяване на съществуващия `request_log` с `channel`/`utm_*`; **всеки** публичен линк през `/f/<channel>`.
15. **V-15 — изчисти мъртвите активи:** `agent_playground.html`, `docs/x402-client-example.js`. **НЕ трий `public_activity.html`** — жив е (вж. бележката в инвентара).

**Вълна V3 — дистрибуция (след V1):**

16. **Провери CDP Bazaar присъствие** (комитът `66a0ce4` е предусловието, но **не е в продукция**) → при липса, Listing Request с готовия текст от `docs/SCAN_LISTING_EN.md`.
17. **Завърши 6-те листинга:** mcp.so (claim + описание + „Authentication: x402"), Glama servers (оправи причината: `license: F` заради „COMMERCIAL USE NOTICE", добавен след MIT текста; регистрирай като **Hosted endpoint**), PulseMCP (чака отваряне на формата), PayAPI recrawl, nohumans.directory (работи — запази), x402 Trust преоценка.
18. **Nudge PR #1308 и #13219**; не отваряй нов, докато старият не е затворен.
19. **Пренареди README:** първите 12 реда = 1 изречение + 1 работещ `curl` + 1 screenshot/GIF + 3 badge-а.
20. **Човешките канали — само след V1/V2:** Product Hunt (изисква ≥3 social proof), Show HN, dev.to, Reddit (само отговор на реален въпрос), X thread — всички с OG card и `/f/<channel>`.
21. **Вдигни ембаргото** върху `docs/OUTREACH_WAVE1.md` — 10 готови съобщения стоят заключени зад инженерен гейт, докато пазарът е ~$1.2/месец. Освободи поне техническата част (x402 Slack, CDP Discord), която не изисква финансиран портфейл.

### 5.5 📚 Документация и хигиена

1. **Синхронизирай остарялото:** `PROJECT_CHRONOLOGY.md` (спира 28.09), `PROJECT_STATUS.md` CURRENT STATE (28.09) и OPEN ITEMS, `TASK.md` (30.09) — заменят се с актуалното състояние от §3.
2. **Поправи публичните твърдения:** `README.md` „11 resources" → 6; махни „Rug-risk checks" (:21); квалифицирай „zero payment incidents" (:111).
3. **Добави `.github/`:** CI workflow (`pytest`) + badge, issue/PR шаблони, `SECURITY.md`, `CODEOWNERS`, dependabot, social preview.
4. **Добави липсващите коренови файлове:** `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `docs/README.md` (индекс на 49-те плоски файла).
5. **Реши съдбата на 29-те untracked записа** — част са реални артефакти (двата одитни документа, `TASK.md`), част са шум (`main_py_diff.txt`, `commit_54a7ba3_full.txt`, `kristo-intelligence/`).
6. **MP4 файловете** (120 MB + 19.9 MB) — премести в GitHub Release assets, не в git.

---

## 6. Ред на изпълнение и гейтове

```
ГЕЙТ 0 — решение на собственика (днес, без код)
  ├── Публикуваме ли 2-та комита (9089ba5 key-leaks + 66a0ce4 Bazaar trigger)?
  ├── Потвърждаваме ли стартовата команда в Render (gunicorn vs python main.py)?
  └── Финансираме ли demo портфейла (F1 гейт, отворен от 25.09)?
        │
        ├── ако F1 се финансира → отваря се инженерната вълна по договорка
        └── ако не → P0 фиксовете пак могат да вървят (те не зависят от F1)

ВЪЛНА 1 — P0 платежна цялост (най-висок приоритет)
  F-02 → F-03 → F-07 → F-04 → F-05/F-06
  Гейт: тест „accepted.amount=5000 + value=1 → отказ"; тест „receipt изключение → не 200"
        │
ВЪЛНА 2 — P1 устойчивост
  F-10 (liveness) → F-11 (SSE) → F-09 (pool) → F-22/F-31 (кеш+индекси) → F-23/24/25 → F-08/F-12
  Гейт: /health не пипа DB; /mcp/sse има кап; студен dashboard build под 2 s
        │
ВЪЛНА 3 — продукт (F-01) + машинна коректност (V1)
  F-01 (решение какво се продава) → V-07 → V-08 → V-06 → V-03 → V-05/V-09 → V-12 → V-11
  Гейт: всички публични повърхности дават еднакъв брой рута и еднакви цени;
        няма „discovery_only" срещу „settled" противоречие
        │
ВЪЛНА 4 — видимост (V2)
  V-02 (OG) → V-01 (HTML страници) → V-04 → V-14 (GSC/IndexNow/analytics + /f/)
  Гейт: OG card валиден; ≥5 нови индексируеми страници; всеки линк с канал
        │
ВЪЛНА 5 — дистрибуция (V3) + хигиена (§5.5)
  Bazaar → 6 листинга → PR nudge → README → човешки канали
  Гейт: ≥3 потвърдени листинга (проверени с fetch), ≥1 органична страница в GSC
```

**Реалистични KPI (честни, при пазар ~$1.2/месец):**

| Хоризонт | KPI |
|---|---|
| 7 дни | 0 P0 дефекта с тест, който ги хваща; GSC/Bing потвърдени; OG card валиден |
| 30 дни | ≥3 потвърдени листинга; ≥5 нови индексируеми страници; npm ≥60 сваляния/месец; ≥5 външни посетители/ден с атрибуция |
| 60 дни | ≥1 органична класификация в топ-50 за дълга заявка; ≥1 външен платен клиент от нов канал; ≥100 npm сваляния |
| 90 дни | ≥10 външни платци; 100% от плащанията с атрибуция към канал; ≥1 операторски договор |

---

## 7. Отворени въпроси и рискове

| # | Въпрос | Защо е важен | Как се затваря |
|---|---|---|---|
| 1 | **`push` = авто-деплой, а 2 комита не са в продукция** | Единият спира изтичане на ключове; другият е предусловие за Bazaar индекса. Но деплойът носи и всичко останало в `main` | Решение на собственика; при нужда — отделен клон/cherry-pick |
| 2 | **gunicorn или `python main.py` в продукция?** | Променя капацитета на HTTP слоя и production-readiness; werkzeug dev сървър в продукция е самостоятелен риск | Проверка в Render dashboard |
| 3 | **`KRISTO_FREE_TIER_LIMIT` в продукция = 0 или 1?** | Влияе на демо пътя, на всички публични твърдения и на F-01 | Проверка в Render Environment (по ИМЕ на променливата) |
| 4 | **F-01 е продуктово решение** | Не може да се „поправи" технически; или продаваш нещо уникално, или таксуването е декоративно | Решение на собственика (§5.3, вариант А/Б/В) |
| 5 | **Пазарът е ~$1.2/месец при 2–4 купувача** | Трафик не решава структурен проблем с пазара; 90-дневните KPI трябва да са реалистични | Приемане + фокус върху машинни канали и операторски сделки |
| 6 | **F1 гейтът блокира инженерната вълна от 25.09** | Всеки фикс „след F1" чака едно човешко действие за ~$0.003 | Финансиране на demo портфейла |
| 7 | **Хронологията и статусът са с 5 седмици назад** | Всеки нов асистент/сесия чете остарял контекст и повтаря грешки | Синхронизация (§5.5) |
| 8 | **29 untracked записа, вкл. реални артефакти** | Работата съществува само локално; риск от загуба; замърсява `git status` | Класифициране: комит / изтриване / `.gitignore` |

---

## 8. Непокътнати инварианти (ограничения от собственика)

| Защитено | Защо |
|---|---|
| **x402 хедъри и структура на 402 плика** | Работещи и валидирани (envelope-body-mirror); промяна чупи съвместимост с facilitators и с тестовете за паритет |
| **Цени в `config.py`** | Публично обявени и on-chain проверени |
| **`payTo` / fee receiver / `BOUND_BASE_FEE_RECEIVER`** | On-chain адрес; промяна чупи доверие и приходи |
| **`GET /.well-known/x402-trust.txt`** | Външен trust профил (grade B); премахване сваля оценката |
| **`secrets/` и `.env`** | Никога не са отваряни; не се пипат |
| **Постовете от 27.10** | Изрично забранени за редакция |
| **`push` към `main`** | Auto-deploy на Render → всяка промяна е продукционна |
| **Повторно подаване на Base Builder Grant** | Изрично забранено |

**Допълнително правило от историята:** *две AI сесии не пушат едновременно в едно репо* (`CHRONOLOGY:30-31`).

---

## 9. Приложения

### 9.1 Карта на документите

| Документ | Роля | Състояние |
|---|---|---|
| `docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md` | Технически одит, F-01…F-40, P0/P1/P2 план | Актуален към `66a0ce4`; **F-13/14/15/30 вече са адресирани** в `9089ba5` |
| `docs/VISIBILITY_AND_TRAFFIC_STRATEGY.md` | Диагностика на каналите, листинги, 30/60/90 | Актуален |
| `docs/CONTEXT_AND_ROADMAP.md` | **Този документ** — консолидация | Актуален към `9089ba5` |
| `docs/PROJECT_CHRONOLOGY.md` | Хронология до 28.09 | **Остарял** — спира на 28.09 |
| `PROJECT_STATUS.md` | Книгата (CURRENT STATE / OPEN ITEMS / HISTORY) | CURRENT STATE = 28.09 → **остарял** |
| `TASK.md` | Снимка на задачите | **Остарял** (30.09) |
| `docs/LISTING_CHANNELS_AUDIT.md`, `docs/TRAFFIC_AUDIT.md`, `docs/SCAN_LISTING_DRAFT.md` | Предишна работа по видимост | Полезни, но частично дублирани |
| `docs/MARKET_WRITEUP.md`, `docs/GUARD_METHODOLOGY.md`, `docs/QUICK_START.md`, `ARCHITECTURE.md` | Суров материал за публични страници | Готови за използване |

### 9.2 Меродавни константи (за сверка)

`FREE_TIER_LIMIT` = `KRISTO_FREE_TIER_LIMIT` (default **1**) `main.py:134` · `X402_PAID_ENDPOINTS` **6** · `X402_FREE_ENDPOINTS` **27** · `STATS_CACHE_TTL_SECONDS` 60 `main.py:3951` · `BLOCKCHAIN_POLL_INTERVAL` 30 · `KRISTO_DASHBOARD_SCAN_INTERVAL` 60 · `WHALEFLOW_SCAN_INTERVAL` 60 · `AGENT_POLL_INTERVAL` 300 · `KEEPALIVE_INTERVAL_SECONDS` 600 · `SALES_CHUNK_BLOCKS` 5000 · `WHALEFLOW_CHUNK_BLOCKS` 100 · `WHALE_THRESHOLD_USDC` 5 000 000 · `C2_LAG_WAIT_SECONDS_DEFAULT` 2.5 · `FACILITATOR_TIMEOUT` 15 · `BASE_RPC_URL` default `https://mainnet.base.org` `config.py:57`.

### 9.3 Едно изречение

> Проектът има работещ платежен рейл и доказани плащания, но три независими дефекта — **безплатно копие на платения продукт**, **подпис, който не е авторитет**, и **продукт, който купувачът не може да намери** — държат приходите на $0.052, а най-важният фикс (спиране на изтичането на ключове) стои непубликуван в git.

---

*Документът е генериран на 2026-11-03 при HEAD `9089ba5`. Проверените факти са валидни за тази ревизия; `origin/main` е `ae216f2`. При следваща сесия първо се сверява `git log -3` и `git status`.*
