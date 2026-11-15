# VISIBILITY & TRAFFIC STRATEGY — kristo-intelligence-6

**Дата на анализа:** 2026-11-03 · **Час:** 12:20–12:40 (Europe/Sofia) · **HEAD:** `66a0ce4` (2026-11-02)
**Обект:** `https://kristo-intelligence-api.onrender.com` · `https://github.com/hristovdimitri2-hub/kristo-intelligence-6`
**Тип на документа:** диагностика + план за дистрибуция. **Само за четене** — не е променен нито един файл по кода, x402 хедърите, цените, `payTo`, защитените конфигурации или `secrets/`. Няма `git add/commit/push`. Всяка стъпка по-долу е **предложение за изпълнение**, а не извършена промяна.

> **Защо това е отделен документ от техническия одит:** одитът отговори „стабилен ли е софтуерът". Този документ отговаря „вижда ли се и продава ли". Заключението е, че проблемът **не е в липсата на канали** — а в това, че каналите са много, но почти никой не е доведен до край, никой не е измерим и машинно-четимите спецификации, които агрегаторите всъщност четат, съдържат грешни данни.

---

## 0. Резюме за ръководството (прочети само това, ако имаш 2 минути)

**Платформата е технически стабилна и вече е „намерена" — но само от машини, които не купуват.**

Твърденията „нулева видимост" и „не сме в каталозите" са **частично неверни**. Проверено на живо на 03.11:

| Факт | Доказателство |
|---|---|
| Има реален, индексиран уеб присъствие | DuckDuckGo `site:` връща **1 страница** (началната), с извлечено точно meta описание |
| Има листинг в mcp.so | `mcp.so/servers/kristo-intelligence` е жив (но „Authentication: not confirmed" и остарели метаданни) |
| Има запис в официалния MCP Registry | 2 записа, `isLatest` = версия 6.0.0 |
| Има публикуван npm пакет | `kristo-x402-client@1.0.0`, **37 сваляния** за последните 30 дни (пик 119 в деня на публикуване) |
| BuiltWith е индексирал MCP инструментите ни | 3 отделни tool страници (`get_market_stats`, `get_onchain_sales`, …) |
| Има 1 потвърден merge в awesome списък | `awesome-remote-mcp-servers` PR #10 |
| Има **реален** платен трафик от външен източник | `nohumans.directory` → 3 × $0.005 от `nohumans-scout` на 30.10 |

**Истинската диагноза:** софтуерът е невидим за **купувачите**, защото:

1. **Платеният продукт е безплатен** на два други влеза — три от шестте SKU-та се получават без $0 (виж техническия одит, F-01/F-02). Всеки, който ни намери, няма причина да плати.
2. **Машинно-четимите спецификации лъжат** — `.well-known/x402` обявява 6 endpoint-а, `agents.json` — 5 (липсва `/api/v1/whaleflow`), README — „11 resources", кодът — 6. Агрегатор, който ни crawler-не, получава противоречиви данни и/или отпада при валидация.
3. **Няма нито един измерим канал** — нула third-party analytics в целия код; `/f/<channel>` съществува, но **нула** публикувани линка го използват. След ~350 комита никой не може да каже кой канал е довел купувач.
4. **Търговският път е блокиран от перфекционизъм** — 10 готови outreach съобщения стоят под ембарго заради „PR #13219 merged AND F1 gate", а F1 е просто funded demo wallet. Най-силният актив (готов текст) не е използван месеци.
5. **Най-добрият канал е подценен** — единственият потвърден външен платен трафик идва от **agent-facing директория**, а усилието е хвърлено в човешки канали (Reddit/HN/Product Hunt), които никога не са използвани.
6. **Няма Open Graph / Twitter Card / canonical / JSON-LD в нито един от 9-те шаблона** — всяко споделяне в X/Discord/Reddit/Telegram се визуализира като гол URL. Това убива CTR още преди да е започнал.
7. **Пазарът е микроскопичен** (self-measured: лидерът в PayAPI прави ~$1.2/месец; 2–4 купувача). Трафик сам по себе си не решава нищо — трябва **точното малко** трафик: агенти и оператори, които плащат.

**Реалистична цел за 90 дни:** не „масов трафик", а **10 външни платци**, **3 потвърдени листинга в директории, които агентите четат**, **1 органична страница в топ-50 за дълга заявка** и **пълен attribution** за всеки долар. Това е постижимо с ~20–30 часа работа и почти нула бюджет.

---

## 1. Методология и обхват на проверката

### 1.1 Какво е проверено на живо (03.11.2026)

| Проверка | Инструмент | Резултат |
|---|---|---|
| GitHub метаданни | `api.github.com/repos/...` | 2 stars, 0 forks, 0 issues, 10 topics, MIT, homepage зададен, **без** Pages/Wiki/Discussions/Releases, 351 комита, създаден 19.08.2026 |
| `robots.txt` | HTTP GET | `Allow: /`, `Disallow: /api/admin/`, `Sitemap:` — **ок** |
| `sitemap.xml` | HTTP GET | 11 URL-а, **без `lastmod`**, включва `/dashboard`, `/nexus`, `/launch` |
| `llms.txt` | HTTP GET | Жив; **документира само legacy `X-Payment-Proof` релса** |
| `/` (landing) | HTTP GET | Има `<title>`, `<meta description>`, `<h1>`; **няма OG/Twitter/canonical/JSON-LD** |
| 6 `/sample` route-а | HTTP GET | Връщат реален JSON schema пример (`/api/v1/signal/sample` = 200, ~600 B) |
| `.well-known/x402` | HTTP GET | 6 resources; споменава и `X-PAYMENT` (v2), и `X-Payment-Proof` |
| `agents.json` | HTTP GET | **5 endpoints** (без whaleflow); `free_tier_limit: 0`; `monthly_vip_usdc: 29.0` |
| `README.md` | локален файл | „11 resources on x402scan" (:112), „zero payment incidents" (:111), „Rug-risk checks" (:21) — **неверни/недоказани** |
| `templates/*.html` | grep | **0 съвпадения** за `og:`, `twitter:`, `canonical`, `application/ld+json` |
| npm downloads | `api.npmjs.org` | **37** за 30 дни (04.10–02.11); пик **119** на 25.08; после 0–5/ден |
| npm registry | `registry.npmjs.org` | Пакетът съществува; README вътре казва „$0.05", „1 free call", „$29 VIP" — **всичките остарели** |
| MCP Registry | `registry.modelcontextprotocol.io` | 2 записа; `isLatest` = 6.0.0; **активен** |
| mcp.so | HTTP GET | Листинг жив; „Authentication: not confirmed"; описание „whale-wallet signals" (старо позициониране) |
| CDP Bazaar | `api.cdp.coinbase.com/.../resources` | Първа страница: **46 resource записа, 12 доставчика**; **няма** kristo/onrender/нашия `payTo` |
| Търсачка | DuckDuckGo `site:` | **1 резултат** (само началната страница); „No more results found" |
| BuiltWith | DDG резултат | 3 MCP tool страници с наши инструменти → **crawler-ите ни намират** |
| Smithery | HTTP GET | Листинг **404**; Smithery proxy е спрян 31.10.2026 |
| Glama API | HTTP GET | `401` — изисква API ключ; не може да се провери программно без ключ |

### 1.2 Какво НЕ е проверено (и защо)

- **Google Search Console / Bing Webmaster** — няма достъп; индексацията е измерена само индиректно през DuckDuckGo (различен индекс от Google).
- **Пълният CDP Bazaar каталог** — API-то връща пагиниран списък; проверена е само първата страница (~100 KB, 46 записа). Липсата в нея **не доказва** липса в целия каталог.
- **Glama сървърния запис** — документацията казва „изтрит", живият badge казва „claimed, rated A". Двусмислено; изисква API ключ за категорична проверка.
- **Реални продажби и трафик в production** — няма достъп до Render логове, база или метрики. Всички числа за трафик идват от `docs/TRAFFIC_AUDIT.md` (11.09) и от кода.
- **Платено тестване на x402 пътя** — не е извършено (изисква портфейл с реални USDC); анализът е статичен + документален.

> **Правило за четене:** в документа са маркирани `[ПРОВЕРЕНО]` (аз го проверих на живо/в кода), `[ДОКУМЕНТИРАНО]` (идва от документ в репото, без независима проверка) и `[НЕПРОВЕРЕНО]` (не можах да потвърдя).

---

## 2. Диагностика: защо платформата е невидима

### 2.1 Търсачки — има техническа готовност, но почти нулево съдържание за индексиране

**Какво работи `[ПРОВЕРЕНО]`:**
- `robots.txt` е коректен и дори подсказва sitemap.
- `sitemap.xml` е валиден и се сервира с правилен Content-Type.
- Началната страница има `<title>`, `<meta name="description">` и `<h1>` — тоест **не е** „празна" страница.
- Има 6 безплатни `/sample` route-а, които връщат реален примерен JSON — потенциално индексируемо съдържание.
- BuiltWith е успял да обходи MCP endpoint-а и е създал tool страници → **crawlability-то на сървъра не е проблемът**.

**Какво липсва `[ПРОВЕРЕНО]`:**
1. **Нула Open Graph / Twitter Card / canonical / JSON-LD** във всички 9 шаблона (`grep` = 0 съвпадения). Всяко споделяне в X, Discord, Reddit, Telegram, LinkedIn показва гол URL без заглавие, описание и изображение. Това е най-евтината и най-влиятелна SEO/социална поправка.
2. **Няма нито една HTML страница със съдържание.** Целият продукт е JSON + един landing. Няма `/pricing`, `/docs`, `/api-reference`, `/how-it-works`, `/blog`, `/status`, `/use-cases`, `/compare`. Търсачката има какво да индексира само на 1 URL.
3. **Платените route-и връщат 402 на crawler** — това е правилно за paywall, но означава, че 6-те „продуктови" страници са **неиндексируеми по дефиниция**. Целият SEO потенциал трябва да дойде от безплатните повърхности (landing, `/dashboard`, `/agents`, `/launch`, `/llms.txt`, `/openapi.json`), а те са или вътрешни, или на български.
4. **Поддомейн на `onrender.com`** вместо собствен домейн — слаба бранд репутация, споделен домейн с безплатни/спам сайтове, никакъв brand search, никакъв имейл домейн за outreach.
5. **Sitemap без `lastmod`** и с приоритет 0.9 за `/dashboard` (оперативно табло, не маркетинг страница) — размива crawl budget.
6. **Смесен език:** `/dashboard` е с българско заглавие („Оперативно табло"), `/launch` е изцяло българска VIP страница за трейдъри — **друг продукт, друг ICP** — а началната е на английски за агенти. Crawler-ът вижда три несвързани оферти на един домейн.
7. **Няма GSC/Bing verification** — `MARKETING_KIT.md:127-128` ги води „⬜ manual"; нула meta verification тагове, нула `google-site-verification` файл.

**Ефект:** `site:kristo-intelligence-api.onrender.com` дава **1 резултат** `[ПРОВЕРЕНО]`. Тоест от 11 URL-а в sitemap-а е индексиран 1. Дори да приемем, че Google е по-благосклонен от DuckDuckGo, липсата на съдържание и на вътрешни връзки прави реалистичната индексация едноцифрена.

### 2.2 Агрегатори и x402 екосистема — листвани сме там, където не се купува

| Канал | Състояние | Доказателство |
|---|---|---|
| **CDP Bazaar** (Coinbase — основният x402 индекс) | **Непотвърдено присъствие** | `[ПРОВЕРЕНО]` първа страница на `/platform/v2/x402/discovery/resources` = 46 записа, 12 доставчика; нашият `payTo` липсва. `[ДОКУМЕНТИРАНО]` 15.09: индексът е имал 16 035 записа и **0 наши** (`AP2_RADAR.md:89`). Listing trigger комит е едва от 02.11 (`66a0ce4`) |
| **x402scan** | **Непотвърдено** | `[ДОКУМЕНТИРАНО]` „11 resources, 0 errors" (`DISTRIBUTION_STATUS.md:11,62`), но `AP2_RADAR.md:90` (15.09) казва „origin page exists, **0 resources shown**". Регистрацията иска SIWX подпис (`AP2_RADAR.md:93`) |
| **PayAPI Market** | **ЖИВ** | `[ДОКУМЕНТИРАНО]` blurb приет 03.09 19:29 UTC; band=established 69.7; **но** „PayAPI няма automatic recrawl" (`PROJECT_STATUS.md:599`) → класирането е замразено върху стар текст |
| **mcp.so** | **ЖИВ, но слаб** | `[ПРОВЕРЕНО]` страницата съществува; „Authentication: not confirmed"; описанието е старо („whale-wallet signals") |
| **MCP Registry** | **ЖИВ** | `[ПРОВЕРЕНО]` 2 записа, `isLatest` 6.0.0 — но това е индекс, не витрина; купувачи не го разглеждат |
| **Glama (connector)** | **ЖИВ** | `[ДОКУМЕНТИРАНО]` claimed, TDQS 4.7, 3 tools, lastTested 22.09 |
| **Glama (servers dir)** | **ДВУСМИСЛЕНО** | `[ДОКУМЕНТИРАНО]` записът е „изтрит" при „FIXED" на 23.09 (`PROJECT_STATUS.md:496-501`); `[ПРОВЕРЕНО]` badge-ът на живо твърди „claimed, rated A" |
| **Smithery** | **МЪРТЪВ** | `[ПРОВЕРЕНО]` листинг URL → **HTTP 404**; Smithery proxy е спрян 31.10.2026 |
| **PulseMCP** | **ЛИПСВА** | `[ДОКУМЕНТИРАНО]` „submissions temporarily paused" от 03.09 (`PROJECT_STATUS.md:2438`); 17.09 проверка „НЕ сме там"; `[НЕПРОВЕРЕНО]` 03.11 → Cloudflare 403 |
| **nohumans.directory** | **ЖИВ И РАБОТИ** | `[ДОКУМЕНТИРАНО]` 3× verified; **реален платен трафик 3 × 0.005 USDC на 30.10** (`discovery.py:340-342`) |
| **x402 Trust** | **ЖИВ** | `[ДОКУМЕНТИРАНО]` profile `/endpoint/139372`, **grade B, „proceed"** |
| **mcprush** | **ПРЕДПОЛАГАЕМО** | `[ПРОВЕРЕНО]` badge в `README.md:4`; `[ДОКУМЕНТИРАНО]` няма submission запис в репото |

**Изводът за агрегаторите:** присъстваме в 6+ каталога, но **нито един от тях не е мястото, където агент взема решение за покупка**. Агрегаторите, които реално водят до плащане (CDP Bazaar → x402scan; nohumans.directory), са точно тези, които са непотвърдени или току-що задействани.

### 2.3 MCP директории — 3 инструмента, но разминаващи се имена

- `[ПРОВЕРЕНО]` MCP сървърът е реален: 3 инструмента (`get_market_stats`, `get_onchain_sales`, `get_bot_status`) в `app/blueprints/discovery.py:522/541/561`, изложени през `/mcp` (streamable HTTP) и `/mcp/sse`.
- `[ДОКУМЕНТИРАНО]` Вторият каталог в `discovery.py:1061-1110` нарича същия инструмент **`get_sales_history`** вместо `get_onchain_sales` — разминаване, което обърква и агент, и каталог.
- `[ПРОВЕРЕНО]` `/mcp/sse` **не е в sitemap.xml** и не е споменат в `llms.txt`; `/mcp` също.
- `[ПРОВЕРЕНО]` `server.json` е коректен по схемата на MCP Registry (`io.github.hristovdimitri2-hub/kristo-intelligence`, v6.0.0, два remotes) — това е най-силният машинно-четим актив, който имаме.

### 2.4 Разработчици — почти никаква следа от човешка активност

`[ПРОВЕРЕНО]` 2 stars, 0 forks, 0 open issues, 0 releases, 0 discussions, 0 PR-и в repo-то. **Няма `.github/` директория** → няма CI badge, няма issue/PR шаблони, няма social preview, няма dependabot, няма SECURITY.md/CHANGELOG.md/CONTRIBUTING.md. Няма `CHANGELOG`, няма release с бележки.

`[ПРОВЕРЕНО]` npm пакетът има **37 сваляния/месец** и **119 в деня на публикуване** — тоест почти целият обем е от самото публикуване и от собствени проверки, не от органичен интерес. Пакетът **не е рекламиран никъде** освен в README и landing страницата; README-то вътре в пакета съдържа остарели цени ($0.05 вместо $0.003–0.005, „1 free call" при production free tier 0) — всеки, който го инсталира, получава грешна информация.

`[ПРОВЕРЕНО]` README-то на repo-то е 136 реда и започва с два badge-а и дълъг списък — няма screenshot/GIF на демото в първите 10 реда, няма „one-command" блок преди средата.

### 2.5 Липса на атрибуция — няма как да се разбере кой канал работи

`[ДОКУМЕНТИРАНО]`:
- `/f/<channel>` атрибуционен hop съществува от 03.09 (`main.py:2242-2252`), но **grep в цялото репо: нула публикувани линка го използват**. Каналната атрибуция е празна по конструкция.
- **Нула third-party analytics**: grep за `umami|plausible|googletagmanager|gtag(|analytics.js|matomo|posthog|mixpanel|segment` в всички `*.py` и `*.html` → **0 съвпадения**.
- UTM полета има само в legacy VIP/Stripe CRM таблицата (`main.py:4259-4261, 5234-5236`; `integrations/crm_store.py:27-29`), не в x402 API-то.
- Единствените реални измерения: persistent `request_log` в Postgres (`main.py:2208-2216`), `/api/dashboard/data` requests секция (`main.py:5454-5470`) и on-chain истина (`payment_guards`, `onchain_sales`, `external_payers`).
- `docs/TRAFFIC_AUDIT.md` (11.09): 13 792 заявки/ден, но `/health` = 42 097 е **собствен keep-alive шум**; „402 challenges → paid: **1 → 0**"; „Днес 100% от трафика е индексатори, монитори и собствен keep-alive шум" (`:58-61`). Два хита от `ClaudeBot/1.0`.

### 2.6 Човешките канали са блокирани от перфекционизъм

`[ДОКУМЕНТИРАНО]` `docs/OUTREACH_WAVE1.md:3-4` държи 10 готови съобщения под ембарго заради „PR #13219 merged AND F1 gate closed". F1 е „funded demo wallet" — едно човешко решение за няколко долара. Резултат: Reddit, HN, Product Hunt, dev.to, Discord постовете са написани и **никога не публикувани**, докато пазарът е ~$1.2/месец.

### 2.7 Пазарът е микроскопичен — това променя цялата стратегия

`[ДОКУМЕНТИРАНО]` `PROJECT_STATUS.md:50-54`: „Реалните причини плащанията да 'спрат' са микроскопичен пазар (2–4 купувача) + нулев outreach — не технически отказ". `PROJECT_STATUS.md:2596`: „лидерът на PayAPI прави ~$1.2/МЕСЕЦ … всички сме на нула". `docs/MARKET_WRITEUP.md:40-52` дава методологията за това измерване.

**Следствие:** стратегия за „масов трафик" е грешна рамка. Правилната цел е **да бъдем намерени от малкото агенти/оператори, които купуват**, и да имаме проверима следа за всеки долар. Затова приоритетът е машинно-четими повърхности + attribution, не viral кампании.

---

## 3. Стратегия за дистрибуция и листване

### 3.1 Принципи (за да не се повтори миналото)

1. **Един канал = една завършена задача.** Не отваряй втори PR, докато първият не е затворен/обединен.
2. **Никакъв листинг без машинно-четима коректност.** Първо оправи `agents.json`, `llms.txt`, `.well-known/x402`, `server.json` — после подай.
3. **Всеки публичен линк минава през `/f/<channel>`.** Иначе каналът е невидим завинаги.
4. **Никакъв листинг без вътрешен чек:** валидатор, който потвърждава, че endpoint-ът връща 402 с правилен challenge.
5. **Не повтаряй отхвърлена молба без да си отстранил причината.** #11557 е умрял заради липса на Glama quality score; #13219 е отворен **преди** score-а да съществува и умря по същото правило.
6. **Не записвай успех, преди да си го проверил.** „Smithery PUBLISHED 30.09" е днес 404. „#12799 Open" е било затворено на 29.08. Документите вече са задължение, не актив.

### 3.2 Приоритизирани канали (Tier 1 = прави пари / индексира)

#### TIER 1 — High priority. Правят пари или индексират за агенти.

| # | Канал | Какво точно да се направи | Очакван ефект | Усилие | Риск |
|---|---|---|---|---|---|
| 1 | **CDP Bazaar → x402scan** | 1) Потвърди, че `/api/stats` връща валиден v2 challenge с `extensions` echo (комитът от 02.11 го задейства). 2) Изчакай crawl (index-ът е pull-based). 3) Ако до 7 дни няма запис — отвори Listing Request #1270 с готовия текст от `SCAN_LISTING_EN.md`. 4) Провери присъствие с скрипт (Приложение B.1) | **Най-висок.** Това е индексът, който x402scan и повечето x402 агенти четат | 2–3 ч + 7 дни изчакване | Нисък |
| 2 | **nohumans.directory** | Вече работи. Задръж листинга, добави `/f/nohumans` към URL-а в профила и провери дали scout-ът пак плаща. Не пипай нищо друго | Потвърден платен трафик | 30 мин | Нисък |
| 3 | **Glama connector** | Жив е. Добави `/f/glama` в connector URL-а/описанието, ако полето го позволява; поддържай `lastTested` свеж | Индексиран MCP клиент | 20 мин | Нисък |
| 4 | **Glama servers dir** | 1) Оправи причината: лицензът е „F", защото след MIT текста има добавено „COMMERCIAL USE NOTICE" след `---` (`PROJECT_STATUS.md:576-579`) → махни го от `LICENSE` (или го сложи в отделен файл). 2) Увери се, че е регистриран като **Hosted endpoint**, не „Runs from source". 3) Подай наново с пълно README. 4) Не отваряй нов тикет, докато старият (#135407945) не е затворен | Възстановяване на #1 позиция за „defi" | 3–4 ч | Среден (зависи от Glama) |
| 5 | **mcp.so** | 1) Claim-ни листинга (бутонът „Claim" е на страницата). 2) Обнови описанието от „whale-wallet signals" на актуалното позициониране (6 route-а, x402, no signup). 3) Попълни „Authentication: x402 pay-per-call" вместо „not confirmed" | Коригира най-видимия MCP листинг | 30 мин | Нисък |
| 6 | **x402 Trust** | Жив, grade B. Подай отново за преоценка **след** като оправиш metadata разминаванията (виж §4) — grade-ът се влияе от тях | По-висок доверителен клас | 1 ч | Нисък |
| 7 | **PayAPI Market** | 1) Плати/поискай recrawl (листингът е замразен върху стар текст, `PROJECT_STATUS.md:599`). 2) Добави `/f/payapi` към URL-а. 3) Пусни 1 нов canary settlement, за да върнеш „settlement-verified" badge-а актуален | Връща „settlement-verified" доверие | 1–2 ч | Нисък |

#### TIER 2 — Medium. Ниско усилие, но изискват нещо преди това.

| # | Канал | Предусловие | Стъпки | Усилие |
|---|---|---|---|---|
| 8 | **PulseMCP** | Чакат да отворят (пауза от 03.09). Готовият пакет е в `PULSEMCP_SUBMISSION_READY.md` | 1) Настрой watcher (Приложение B.2), който проверява `/submit` за 200 и промяна на текста. 2) При отваряне — подаваш готовия пакет **след** като махнеш „1 free call"/„$0.05" фантомите (`:101-102`) | 1 ч + чакане |
| 9 | **awesome-x402** PR #1308 | Отворен от 24.08, нула коментара, deadline 08.10 е минал | 1) Коментирай вежлив nudge с 1 изречение и линк към `/llms.txt`. 2) Ако до 14 дни няма отговор — затвори сам и отвори нов PR с **едно** добавено устройство | 30 мин |
| 10 | **awesome-mcp-servers** PR #13219 | Отворен, labels `has-emoji`/`valid-name`/`has-glama`, rebased 22.09, deadline 01.10 минал | 1) Nudge коментар. 2) Увери се, че Glama score-ът съществува (иначе пак ще умре по 32-дневното правило) | 30 мин |
| 11 | **mcprush** | Badge в README, но няма submission запис | 1) Провери дали листингът е реален (fetch на badge URL). 2) Ако не — подай; ако да — добави `/f/mcprush` | 20 мин |
| 12 | **MCP Registry** | Вече активен | 1) Публикувай `server.json` v6.0.0 с **актуални** описания (сега са ок, но провери `paid_endpoints` дали съвпадат с 6-те). 2) Добави `websiteUrl` (има го) | 20 мин |

#### TIER 3 — Low/Medium. Човешки канали — само след като има какво да се покаже.

| # | Канал | Условие | Бележка |
|---|---|---|---|
| 13 | **Product Hunt** | Изисква ≥3 social proof точки (`VISIBILITY_PLAN.md:88`) | Пусни **след** 3-те външни платци/листинга. Иначе ще е тих провал |
| 14 | **Show HN** | Изисква „нещо ново и интересно" | Най-добрият ъгъл: „API, който се плаща сам с x402 — без ключове". Публикувай **след** като landing-ът има OG card |
| 15 | **dev.to статия** | Готов текст в `CONTENT_PACK_1.md` §A | Публикувай **след** като махнеш противоречието „free tier" (`:23-30` vs `:82`) |
| 16 | **Reddit** (r/LocalLLaMA, r/LangChain, r/Base, r/mcp, r/AI_Agents) | Готови текстове в `OUTREACH_WAVE1.md` §3.1/3.3 | **Само** като отговор на реален въпрос, не като нов пост. Иначе е спам и ще те баннат |
| 17 | **X/Twitter** | 6-tweet thread в `CONTENT_PACK_1.md` §B | Собственикът го е обявил за „мъртъв канал", но 1 пост с видео съществува. Пусни **само** с OG card + `/f/x` линк |
| 18 | **Discord** (CDP #agentkit, Base #developers) | Готови текстове в `OUTREACH_WAVE1.md` §1.1/1.3 | Един пост на общност, без cross-post. Най-добър ъгъл: техническа бележка за Bazaar listing |

### 3.3 Автоматизация на присъствието (конкретно)

**A. Скрипт за проверка на присъствие** (`scripts/distribution/check_presence.py`, ~120 реда):
- Чете списък от URL-и/API-та (CDP Bazaar, MCP Registry, mcp.so, Glama API, x402scan) и за всяко връща: `present: true/false`, `last_seen`, `metadata_match: true/false`.
- Пише `docs/distribution_state.json` — **един** източник на истина вместо 8 разпръснати документа.
- Пуска се от GitHub Action всеки понеделник 08:00 UTC; при промяна → отваря issue „Distribution drift detected".

**B. Sitemap/IndexNow ping** (`scripts/seo/ping_index.py`):
- `POST` към IndexNow (`https://api.indexnow.org/indexnow`) с ключ, който се сервира на `/<key>.txt`.
- Пинг към Google/Bing sitemap само след като `sitemap.xml` получи `lastmod`.
- Внимание: IndexNow изисква собствен домейн; на `onrender.com` може да не се приеме → предусловие е custom domain (§5, L1).

**C. Канална атрибуция:**
- Всички публични линка минават през `/f/<channel>` (вече съществува, `main.py:2242-2252`) — напр. `https://…/f/x`, `/f/discord`, `/f/reddit`, `/f/ph`, `/f/mcpso`.
- Всяко листинг поле, което позволява URL (Glama, mcp.so, PayAPI, nohumans), получава `/f/<channel>` варианта.
- **Без това стъпка 4 от принципите е неизпълнима.**

**D. UTM за имейл/директни:** `?utm_source=…&utm_medium=…&utm_campaign=…` — кодът вече чете `referer`/`funnel`; UTM полетата са само в CRM-а, така че за API пътя трябва разширение (виж §4, H7).

---

## 4. Технически стъпки в репото (High / Medium / Low)

> Всичко по-долу е **предложение**. Не е приложено. Спазва ограниченията: не пипа x402 хедъри/цени/`payTo`, не пипа `secrets/`, не пипа постовете от 27.10.

### HIGH — правят се първи (1–3 дни, ~8–12 ч работа)

**H1. Open Graph + Twitter Card + canonical + JSON-LD във всички 9 шаблона.**
- Файлове: `templates/landing.html`, `templates/launch_landing.html`, `templates/dashboard.html`, `templates/agent_playground.html`, `templates/public_activity.html`, `templates/checkout.html`, `templates/admin_dashboard.html`, `templates/admin_login.html`, `templates/admin_research.html`.
- Минимум за публичните (`landing`, `launch_landing`, `dashboard`, `agent_playground`, `public_activity`):
  ```html
  <meta property="og:title" content="…">
  <meta property="og:description" content="…">
  <meta property="og:image" content="{{ url_for('static', filename='og.png', _external=True) }}">
  <meta property="og:url" content="{{ request.url }}">
  <meta property="og:type" content="website">
  <meta name="twitter:card" content="summary_large_image">
  <link rel="canonical" href="{{ request.url }}">
  <script type="application/ld+json">{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Kristo Intelligence","applicationCategory":"FinanceApplication","operatingSystem":"Any","offers":{"@type":"Offer","price":"0.003","priceCurrency":"USDC"}}</script>
  ```
- **Задължително:** 1 OG изображение 1200×630 (`static/og.png`) — може да се генерира от `docs/glama_thumbnails/generate.py` (вече има 3 варианта).
- Ефект: всяко споделяне в X/Discord/Reddit/Telegram става карта с изображение → CTR скок без бюджет.

**H2. Корекция на машинно-четимите спецификации (най-важното за агрегаторите).**
- `agents.json` (`app/blueprints/discovery.py:1416`): добави липсващия `/api/v1/whaleflow` (6-ти route); махни `monthly_vip_usdc: 29.0` (VIP unlimited не е имплементиран — `[ДОКУМЕНТИРАНО]` само $0.10 Telegram invite) или го маркирай като `legacy`; поддържай `free_tier_limit: 0`.
- `llms.txt` (`discovery.py:1536`): документирай **стандартната** релса (`PAYMENT-SIGNATURE` / `X-PAYMENT`, x402 v2) като основна и legacy `X-Payment-Proof` като fallback. Сега `llms.txt` описва **само** legacy релсата — агент, който го чете, изпраща грешен хедър.
- `.well-known/x402` vs `.well-known/x402.json` (`discovery.py:914/922`): унифицирай броя resources (6) и описанията; сега единият дава 6, `agents.json` — 5.
- `server.json`: обнови `paid_endpoints` да съвпадат с 6-те; провери `_meta` дали не сочи старо.
- `README.md`: махни „Rug-risk checks" (:21 — няма такъв route), „zero payment incidents" (:111 — има INCIDENT 14.09), „11 resources" (:112 — кодът експонира 6). Замени с проверени числа.
- **Проверка след промяна:** един тест, който сравнява множеството от `X402_PAID_ENDPOINTS` с `REAL_X402_ROUTES` и с `agents.json`/`.well-known/x402` — в момента няма такъв тест и точно затова се разминават.

**H3. HTML страници със съдържание (индексируеми).**
- `/pricing` — HTML таблица с 6-те route-а и цените (данните ги има в `REAL_X402_ROUTES`); JSON-LD `Offer`.
- `/api-reference` — рендерира се от `openapi.json` (вече съществува на `/openapi.json`, `discovery.py:1127`); статичен HTML с anchor-и по route.
- `/how-x402-works` — кратък explainer (материалът е в `docs/GUARD_METHODOLOGY.md` + `docs/blog/2026-10-23-x401-x402-one-gate.md`).
- `/changelog` — от git log/ръчно; дава „freshness" сигнал на crawler-ите.
- `/status` — публична страница с `/health` + последно сканиране на блок; може да ползва съществуващия `/api/launch/health` (`main.py:5198`).
- Всички тези да влязат в `sitemap.xml` (`discovery.py:1387`) **с `lastmod`**.

**H4. `.github/` директория (5 файла, 1 час).**
- `.github/workflows/ci.yml` — `pytest` + `python -m compileall`; badge в README.
- `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`.
- `.github/SECURITY.md` — канал за докладване (имейл, не публичен issue).
- `.github/social-preview.png` — 1280×640 (същото OG изображение).
- `.github/FUNDING.yml` (по избор).
- Ефект: repo-то изглежда „живо" за разработчик; CI badge е безплатен доверителен сигнал.

**H5. npm пакетът — реален канал, не badge.**
- Публикувай `1.0.1` с поправено README (`packages/x402-client/README.md`): цени $0.003–0.005, **без** „1 free call", **без** „$0.05", **без** „$29 VIP unlimited".
- Добави `repository.directory` (има го), `keywords` (има ги), `homepage` (има го).
- Добави badge за сваляния в README на repo-то (`img.shields.io/npm/dm/kristo-x402-client`).
- **Опция с висок ефект:** Python клиент в PyPI (`kristo-x402`), защото `examples/demo_agent/demo_agent.py` вече е Python и агент-разработчиците са 50/50 JS/Python. Това удвоява адресируемата аудитория.

### MEDIUM — след HIGH (1–2 седмици)

**M1. Сравнителни и „рецепта" страници (органичен трафик от дълги заявки).**
- „How to call an x402 API from LangChain / CrewAI / Claude Code" — 3 отделни страници, всяка с работещ snippet от `packages/x402-client` и `examples/demo_agent`.
- „x402 vs API keys: кога pay-per-call печели" — позициониращ текст.
- „Base DeFi data for AI agents" — keyword-насочена.
- Всяка страница: 600–900 думи, 1 работещ пример, 1 CTA към `/f/<channel>`.

**M2. Публикуване на вече написаното съдържание.**
- `docs/MARKET_WRITEUP.md` → публичен пост (методологията е силна страна; тя е проверима).
- `docs/blog/2026-10-23-x401-x402-one-gate.md` → технически пост.
- `docs/CONTENT_PACK_1.md` §A → dev.to (след H2 корекциите).
- **Всичко с `/f/<channel>` линк и OG card.**

**M3. Автоматизация и мониторинг.**
- `scripts/distribution/check_presence.py` + GitHub Action (седмично).
- `scripts/seo/ping_index.py` (IndexNow, след custom domain).
- `scripts/listing_monitor.py` (вече съществува) → разшири да проверява и mcp.so/mcprush/Glama badge.

### LOW — nice to have

**L1. Собствен домейн** (напр. `kristo.xyz` / `kristo.dev`) с 301 от `onrender.com`.
- Причина: бранд search, имейл за outreach, IndexNow, доверие при листинг, независимост от Render.
- Усилие: 1–2 ч (DNS + Render custom domain + `ProxyFix` вече е настроен да следва `X-Forwarded-Host`, `main.py:174`).

**L2. README пренареждане:** първите 12 реда = 1 изречение + 1 работещ `curl` + 1 screenshot/GIF + 3 badge-а. Подробностите — в `docs/`.

**L3. Хигиена на repo-то:** премести `PROJECT_STATUS.md` (272 KB), diff-файловете, `temp_*.log`, `server_*.log` извън публичното repo; MP4 файловете (120 MB + 19.9 MB) → GitHub Release assets, не в git.

---

## 5. План за общностен маркетинг без спам рисков

### 5.1 Правила на ангажимента

1. **Само отговор на реален въпрос.** Ако някой не е попитал „как да платя на API без ключ" или „къде да намеря Base DeFi данни за агент", не пускай линк.
2. **Един канал = един пост на тема.** Без cross-posting на идентичен текст; всяка платформа има различен формат.
3. **Никакъв mass DM.** BlockRun DM-ът е бил изпратен веднъж и е останал без отговор — това е урок, не шаблон.
4. **Никакви фалшиви stars/fork-ове/отзиви.** Те са лесно разпознаваеми и убиват доверието завинаги.
5. **Винаги техническа стойност преди линк.** Формулата: 1 конкретен технически факт (напр. „Bazaar изисква echo на `extensions` от challenge-а") + 1 линк към `/llms.txt` или `/f/<channel>`.
6. **Прозрачност за пазара.** Числата от `MARKET_WRITEUP.md` са проверими — използвай ги; не измисляй „$X милиона пазар".

### 5.2 Къде и как (по приоритет)

| Общност | Тип намеса | Честота | Ъгъл |
|---|---|---|---|
| **x402 Slack #general** | Отговор на технически въпрос | 1–2/седмица | Receipt cross-check методологията (вече си приеман там) |
| **CDP Discord #agentkit** | 1 техническа бележка | веднъж | „Какво научихме от Bazaar listing trigger-а" |
| **Base Discord #developers** | 1 техническа бележка | веднъж | „x402 paywall върху Flask — 3 неща, които ни ухапаха" |
| **r/mcp** | Отговор на „как да намеря MCP сървър за финанси" | при реален въпрос | 3-те инструмента + `/llms.txt` |
| **r/LocalLLaMA / r/AI_Agents** | Отговор на „как агентите плащат за данни" | при реален въпрос | x402 vs API keys |
| **HN Show HN** | 1 пост | веднъж, след H1/H2 | „API, който се плаща сам" |
| **X/Twitter** | 1 thread | веднъж, след H1 | Демо видео + OG card + `/f/x` |
| **Product Hunt** | 1 launch | след ≥3 social proof | „Pay-per-call DeFi intelligence for AI agents" |

### 5.3 Какво да НЕ правим

- ❌ Да пускаме един и същ текст в 5 subreddit-а за един ден → shadowban.
- ❌ Да отваряме втори PR в awesome-* без отговор на първия → 32-дневното правило пак ще го затвори.
- ❌ Да обявяваме „PUBLISHED" без fetch проверка → документацията вече лъже за Smithery/mcp.so.
- ❌ Да плащаме за ads преди да имаме OG card и `/pricing` → скъп трафик към счупен funnel.
- ❌ Да правим „free tier" обещания, при положение че production е `KRISTO_FREE_TIER_LIMIT=0` (`main.py:130`).

---

## 6. 30/60/90 дни — изпълнение и KPI

### Седмица 1 (Дни 1–7) — „Да стане машинно вярно"
- [ ] H2: поправи `agents.json` (6 routes), `llms.txt` (v2 релса), README фалшивите твърдения. **Без това всякакъв листинг е вреден.**
- [ ] H1: OG/Twitter/canonical/JSON-LD + `static/og.png`.
- [ ] Провери CDP Bazaar присъствие (Приложение B.1); ако липсва → Listing Request #1270 с `SCAN_LISTING_EN.md`.
- [ ] mcp.so: claim + описание + „Authentication: x402".
- [ ] `/f/<channel>` линкове във всички листинги.

**KPI седмица 1:** `agents.json` == 6 routes; OG card валиден (проверка с opengraph.xyz); 1 листинг потвърден с fetch.

### Седмица 2–4 (Дни 8–30) — „Да стане намеримо"
- [ ] H3: `/pricing`, `/api-reference`, `/how-x402-works`, `/status`, `/changelog` + sitemap `lastmod`.
- [ ] H4: `.github/` + CI badge + social preview.
- [ ] H5: npm `1.0.1` с поправено README + downloads badge.
- [ ] Nudge PR #1308 и #13219; оправи Glama license F + hosted endpoint.
- [ ] GSC + Bing verification; подаване на sitemap.
- [ ] Активирай `/f/<channel>` във всеки публичен линк.

**KPI ден 30:** ≥3 потвърдени листинга (`check_presence.py`), ≥1 индексирана нова HTML страница в GSC, ≥5 външни посетители/ден с атрибуция, npm ≥60 сваляния/месец.

### Дни 31–60 — „Да стане проверимо"
- [ ] M1: 3 recipe/сравнителни страници.
- [ ] M2: публикувай MARKET_WRITEUP + 1 dev.to статия + 1 thread.
- [ ] M3: автоматизация + седмичен „distribution drift" issue.
- [ ] Product Hunt подготовка (≥3 social proof).

**KPI ден 60:** ≥1 органична класификация в топ-50 за дълга заявка; ≥1 външен платен клиент от нов канал; ≥100 npm сваляния/месец.

### Дни 61–90 — „Да стане приходи”
- [ ] Product Hunt launch; HN Show HN.
- [ ] 5 операторски разговора (по модела от `MARKET_WRITEUP.md:72-82`).
- [ ] Преоценка на x402 Trust; recrawl на PayAPI.
- [ ] Ревизия: кой канал е дал плащане → концентрирай 80% от усилието там.

**KPI ден 90:** ≥10 външни платци; ≥$0.05 средно/ден; ≥1 дългосрочен операторски договор; 100% от плащанията с атрибуция към канал.

---

## 7. Какво НЕ да пипаме (ограничения от собственика)

| Защитено | Защо |
|---|---|
| x402 хедъри и структура на 402 плика | Работещи и валидирани; промяна чупи съвместимост с facilitators |
| Цени ($0.003–$0.005) и `payTo`/fee receiver | Публично обявени и on-chain проверени; промяна чупи доверие |
| `GET /.well-known/x402-trust.txt` | Външен trust профил; премахване сваля grade |
| `secrets/` и `.env` | Никога не са отваряни; не се пипат |
| Постовете от 27.10 | Изрично забранени за редакция |
| Push към `main` | Auto-deploy на Render → всяка промяна е production |

**Правило:** всички промени по §4 минават през отделен PR + преглед, не директно в `main`.

---

## 8. Приложения

### Приложение A — Готови URL-и и контакти за листване

| Канал | Действие | URL |
|---|---|---|
| CDP Bazaar | Проверка на присъствие | `https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources` |
| x402scan | Listing Request #1270 | `https://github.com/x402scan/x402scan/issues/1270` (провери номера) |
| MCP Registry | Публикуване | `https://registry.modelcontextprotocol.io` |
| Glama | Connector (жив) | `https://glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` |
| Glama | Servers dir (проблем) | тикет #135407945 |
| mcp.so | Claim | `https://mcp.so/servers/kristo-intelligence` |
| PulseMCP | Watcher | `https://www.pulsemcp.com/submit` |
| awesome-x402 | PR #1308 | `https://github.com/coinbase/x402` (провери repo) |
| awesome-mcp-servers | PR #13219 | `https://github.com/punkpeye/awesome-mcp-servers` |
| PayAPI Market | Листинг | `https://payapi.market/api/kristo-intelligence-defi-signals-api` |
| x402 Trust | Профил | `https://x402-trust.com/endpoint/139372` |
| nohumans.directory | Листинг | (виж `discovery.py:340-342` за референтния запис) |

### Приложение B — Скриптове (псевдокод)

**B.1 `scripts/distribution/check_presence.py`**
```python
CHANNELS = {
  "cdp_bazaar": "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources",
  "mcp_registry": "https://registry.modelcontextprotocol.io/v0/servers?search=kristo",
  "mcpso": "https://mcp.so/servers/kristo-intelligence",
  "glama": "https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6",
}
# за всяко: GET, търси "kristo" / нашия payTo / нашия домейн
# записва docs/distribution_state.json с {present, checked_at, evidence_url}
# exit code 1 при промяна → GitHub Action отваря issue
```

**B.2 `scripts/seo/ping_index.py`**
```python
# 1) генерирай key (uuid) → сервирай на /<key>.txt
# 2) POST https://api.indexnow.org/indexnow  {"host": "...", "key": "...", "urlList": [...]}
# 3) изисква собствен домейн; на onrender.com може да върне 403
```

**B.3 `scripts/distribution/submit_payload.py`**
```python
# генерира готовия JSON/Markdown payload за всяка директория от един източник
# (server.json + REAL_X402_ROUTES) → избягва разминаването 5 vs 6 routes
```

### Приложение C — Измерване (без трети страни)

- **Сървърно:** `request_log` вече записва `path, source, referer, user_agent, funnel` — добави `channel` от `/f/<channel>` и `utm_*` query params.
- **Публично:** `/api/dashboard/data` вече има `by_channel` — стига линковете да минават през `/f/`.
- **Външно:** npm downloads API, MCP Registry search, CDP Bazaar page, `check_presence.py`.
- **Търсачки:** GSC + Bing (ръчно, еднократно).
- **On-chain:** `payment_guards` / `onchain_sales` — истината за приходите; всичко друго е шум.

---

## 9. Едно изречение

> Платформата не е невидима, защото липсват канали — а защото каналите са много, никой не е завършен, машинно-четимите спецификации лъжат, а платеният продукт се раздава безплатно на два влеза; затова следващите 90 дни не са „маркетинг кампания", а **завършване на 6 листинга, поправяне на 4 спецификации, добавяне на 1 OG card и 1 атрибуционен линк на всяко публично място** — и след това измерване на всеки долар.

---

*Документът е генериран на 2026-11-03 при HEAD `66a0ce4`. Всички URL-и са проверени на тази дата; външните състояния (Smithery, PulseMCP, CDP Bazaar) се променят — проверявай с `check_presence.py`, не вярвай на документа.*
