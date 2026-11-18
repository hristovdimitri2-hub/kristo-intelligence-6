# DISCOVERY & TRAFFIC PLAN — Kristo Intelligence

**Съставен:** 03.11.2026 · **Основа:** живи проверки (Glama, официален MCP Registry, GitHub API) + Chatbox архива
**Статус:** чернова за одобрение — **нищо в репото не е променяно от този документ**

---

## §0 Резюме в три точки

1. **Glama не е счупен — объркана е вратата.** Живият ни запис е в **Connectors** (хоствани endpoint-и): ownership verified, **Healthy**, **100% uptime за 47 дни**, последен тест **03.11 11:13**, **TDQS A (4.7/5)** с 3 инструмента, всеки оценен A. Липсва само записът в **Servers** (изходен код) — а той е нужен единствено за баджа и за PR #13219.
2. **Регистърът е „обърнат".** В официалния MCP Registry `isLatest` сочи **v6.0.0 от 17.09**, а по-новият и по-богат **v1.0.0 от 10.10** е `isLatest: false` — защото 1.0.0 < 6.0.0 по semver. Всичко, което поема от регистъра (PulseMCP и др.), вижда старата версия.
3. **Реалната дупка е публичното търсене** — точно както собственикът каза на 03.11: „публично търсене — сега ни няма там. Това е най-голямата ни дупка." Директориите ни виждат; **търсачките и LLM-ите — почти не**.

---

## §1 Проверено на живо (03.11.2026)

| Проверка | Резултат | Доказателство |
|---|---|---|
| Glama **Connectors** — нашият запис | ✅ **LIVE** | `glama.ai/mcp/connectors/com.onrender.kristo-intelligence-api/kristo-intelligence` |
| … собственост | ✅ **Ownership verified** | на страницата |
| … здраве | ✅ **Healthy**, **100.0% uptime / 47 дни**, последен тест **2026-11-03 11:13** | |
| … качество | ✅ **TDQS A, 4.7/5.0**, 3 инструмента × **A** | Disambiguation 5/5 · Naming 5/5 · Tool Count 5/5 · Completeness 4/5 |
| … транспорт | Streamable HTTP · MCP 2025-11-25 · `https://kristo-intelligence-api.onrender.com/mcp` | |
| … празни полета | ❌ Documentation: *Not available* · Trust center: *Not available* · ChatGPT: `–` · Claude: `–` | |
| Glama **Servers** — нашият запис | ❌ **ОТСЪСТВА — потвърдено през API**: `GET /v1/servers/hristovdimitri2-hub/kristo-intelligence-6` → **HTTP 404 `not_found`**; търсене „kristo" връща Krimto, gmail-mcp, Safe Terminal, agentcrush — **не нас**. Не е скрит запис: наистина няма такъв | Glama Directory API |
| Glama **Connectors** — пълният запис | `id: oc4mkbcgg8` · `qualityScore 4.7` · `toolCount 3` · `healthy: true` · `lastTestedAt 2026-11-03T12:14:23Z` · `createdAt 2026-09-17` · attributes: `auth:none`, `status:healthy`, `capability:tools`, `category:developer-tools`, `category:finance` | Glama Directory API |
| Connector → repo връзка | ❌ **`repository: null`** — connector-ът не е свързан с repo-то; `documentationUrl: null` | Glama Directory API |
| **Badge на connector-а** | ✅ рендира **„A"**: *„MCP connector rated A … ownership verified, tool definitions rated A, 3 tools"* | `/mcp/connectors/…/badges/score.svg` |
| **Badge на server-а** | ❌ рендира **„F – A"**: *„claimed by its maintainer, remote-capable, maintenance rated A"* — лиценз **F**, качество **неоценено** | `/mcp/servers/…/badges/score.svg` |
| README ред 3 | Показва **и двата** badge-а → посетителят вижда червено „F" до чистото „A" | `README.md:3` |
| Glama размери | Servers **115 008** · Connectors **39 498** | |
| Официален MCP Registry | ⚠️ **v6.0.0 (17.09) = `isLatest: true`**; v1.0.0 (10.10) = `false` | `registry.modelcontextprotocol.io/v0/servers?search=kristo-intelligence` |
| PR **#13219** (punkpeye/awesome-mcp-servers) | 🟡 **open**, **20 коментара**, последна активност **01.11**, етикети `has-emoji`, `valid-name`, `has-glama` | GitHub API |
| PR **#1308** (xpaysh/awesome-x402) | 🟢 **open**, `mergeable_state: clean`, от 24.08, последна активност 28.09 | GitHub API |
| PR #1081 (същият списък, стар запис) | open — за `kristo-travel-api`, **не е текущият проект** | GitHub API |
| В репото | ✅ **има** `glama.json`, `glama-connector-claim.json`, `server.json` (**v6.0.0**), `smithery.yaml`, `.mcp.json`, `Dockerfile`, **`scripts/mcp_stdio_bridge.py`** + `tests/test_mcp_stdio_bridge.py` · ❌ **няма** `.github/`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, `render.yaml` | локален прочит |

---

## §2 Диагноза — какво точно е счупено

### 2.1 Glama има ДВЕ различни директории и ние кандидатстваме в грешната

| | **Servers** (`/mcp/servers`) | **Connectors** (`/mcp/connectors`) |
|---|---|---|
| Какво приема | „open-source servers that we build and run from source" | хоствани endpoint-и: „Only approved connectors reachable over **streamable HTTP** are listed" |
| Как се влиза | Glama билдва контейнера и го **стартира** — трябва да отговори на **introspection** | подаваш URL, те го health-check-ват |
| Ние | ❌ отсъстваме | ✅ **живи, verified, rated A** |
| Нужен за | бадж в README + merge на PR #13219 | **реална видимост пред клиенти** (бутон „Connect") |

**Ключът:** нашият `Dockerfile` вдига **gunicorn (HTTP)** — той не може да отговори на introspection в контейнера на Glama. Затова „Runs from source" се проваля. А „Add Server → Hosted endpoint" отказва, защото endpoint-ът **вече е регистриран като connector** → дубликат.

> **Ние не сме „отхвърлени". Ние чукаме на вратата, която не е наша — и през това време стояхме 6 седмици в тикет.**

### 2.2 Хронологията от PR #13219 (20 коментара) — как изтече времето

| Дата | Кой | Какво |
|---|---|---|
| 30.08 | PR отворен | 1 файл, 1 ред |
| 30.08 | бот | „добави Glama quality score" |
| 07.09 | **punkpeye** | „submit at glama.ai/mcp/servers, claim ownership, and ensure a quality score is set — **once that's done, I'll merge**" |
| 17.09 | бот | **ново изискване:** Dockerfile („we only need the server to start and respond to introspection requests"). P.S.: „If your server already has a hosted endpoint, you can also list it under /mcp/connectors" |
| 17.09 | ние | сочим connector-а; поправяме описанието ($0.05 → $0.003–0.005, „no free tier") |
| 21.09 | punkpeye | триаж-напомняне: бадж `OWNER/REPO` + „Submit at glama.ai/mcp/servers" — **без отговор на въпроса за connector** |
| 22.09 | ние | „и двете са готови"; после корекция: контейнерната introspection **НЕ** минава (регистриран по грешка като „Runs from source"); тикет **#135407945** |
| 23.10 | **punkpeye** | „**the quality score is still not evaluated** … without the score being set, the entry can't be merged" |
| 27.10 → 01.11 | ние | доказахме, че `/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` **не съществува** (404 → homepage), а формата го отказва като дубликат |
| 01.11 15:30 | **Glama Support** | **„не е одобрен — вече съществува MCP сървър за това репо"**; системата създава втори тикет **#151838421** |
| 03.11 14:37 | ние | пълното доказателство до Frank: 404 от API, badge **F** за лиценза, опции A/B, готовият stdio bridge. Пробата с `Dockerfile.glama` също е отказана („MCP server already exists for this repository"). Мълчание оттогава |

**Един-единствен блокер:** липсващ `Servers` запис, който **само Glama може да създаде** — освен ако не направим контейнера си годен за introspection.

---

## §3 Планът за Glama и Frank

> **Правило №1: СПИРАМЕ да подаваме.** Всяко ново подаване удря дубликата и харчи доверие. Нула нови submissions до избор на маршрут.

### Маршрут A — „Glama го създава" (бърз, без код) ← **препоръчан за стартиране веднага**

1. **Един-единствен ъпдейт в тикет #135407945** (не в чат, не в Discord), с пълното доказателство:
   - Connector URL + статус: *Ownership verified · Healthy · 100% uptime 47 days · TDQS A 4.7/5 · last tested 2026-11-03 11:13*
   - `https://glama.ai/mcp/servers/hristovdimitri2-hub/kristo-intelligence-6` → **404** (връща homepage)
   - търсене „kristo" в `/mcp/servers` → **нула наши резултата**
   - „Add Server → Hosted endpoint" → **отказва: endpoint-ът вече е connector**
   - **молбата, формулирана точно:** *type change на съществуващия запис към „Hosted endpoint", свързан с repo `hristovdimitri2-hub/kristo-intelligence-6`* — това създава `/mcp/servers/` записа и задейства quality score
2. **Кратък коментар в PR #13219** — само за да не изтече 32-дневният inactivity таймер (последен: 01.11; следващ ~17.11), с линк към тикета.
3. **Discord на Glama** — само напомняне с линк към тикета, **не** паралелен канал с нови искания.
4. **Запълване на празните полета** през **Admin** таба на connector-а: Documentation URL (repo `docs/` + `/llms.txt`) и Trust center (x402-trust профилът). Това са видими, безплатни подобрения на качеството на записа.

### Маршрут B — „ние правим контейнера годен" (в наша власт) ✅ **изпълнен**

Оказа се, че репото **вече беше предвидило този сценарий**. `scripts/mcp_stdio_bridge.py` (126 реда)
съществува като **„sleeping asset"** — умишлено НЕвключен в `Dockerfile`/`Procfile`, със собствен тест
`tests/test_mcp_stdio_bridge.py`, който дори **забранява** случайното му включване.

Дизайнът му е по-добър от прокси към Render: той подава всяко JSON-RPC съобщение на **истинското
Flask приложение в самия процес** (през test client), тоест работи **без мрежа** и без зависимост от
Render. Точно това трябва на контейнера на Glama.

**Какво беше добавено:** `Dockerfile.glama` — вдига **само моста**, не gunicorn; производственият
`Dockerfile` и `Procfile` остават недокоснати (затова и тестът продължава да минава).

**Доказателство (като отделен процес, точно както би го пуснал Glama):**

| Проверка | Резултат |
|---|---|
| 4 съобщения на stdin → кадри на stdout | **3** (notification-ът не се отговаря) ✅ |
| Валидни JSON редове | **3 / 3** ✅ |
| `initialize` | `kristo-intelligence`, протокол `2025-06-18`, capabilities `tools` ✅ |
| `tools/list` | **3 инструмента** с пълни схеми и описания ✅ |
| Логове на приложението | на **stderr** (182 B), stdout **чист** ✅ |
| Изходен код | **0** ✅ |

**Скрит капан №1, намерен при четене:** `.dockerignore` изключва `data/`, а импортирането на
приложението записва `data/agent_catalog.db`, без самата тя да създава папката. Без
`mkdir -p /app/data` контейнерът пада с „unable to open database file".

**Проверено и като истински контейнер** (`docker build -f Dockerfile.glama` ✅ + `docker run --rm -i` ✅):

| Проверка | Резултат |
|---|---|
| Изходен код на контейнера | **0** ✅ |
| Протоколни кадъра (initialize, tools/list, ping, платено tools/call) | **4 / 4** ✅ |
| Валидни JSON редове | **4 / 4** ✅ |
| `initialize` | `kristo-intelligence`, `2025-06-18` ✅ |
| `tools/list` | **3 инструмента** със схеми ✅ |
| Платен `tools/call` | връща x402 инструкцията (не изпълнява) ✅ |
| Общо време (старт на образа + 5 заявки) | **6.9 s** ✅ |
| stdout | само протокол; логовете на stderr ✅ |

**Скрит капан №2, намерен само от истински контейнер:** `python scripts/<файл>.py` слага
`scripts/` на `sys.path`, **не** `/app` — затова `from main import app` вътре в контейнера пада с
`ModuleNotFoundError: No module named 'main'`. На хост машината не се вижда, ако е подаден
`PYTHONPATH`. Поправено с `ENV PYTHONPATH=/app`.

**Следваща стъпка:** подаване „Runs from source" с този Dockerfile — **но едва след като Glama
махне остарелия запис за repo-то** (§2.2), иначе пак ще удари „already exists for this repository".

### Какво да НЕ правим

- Да не искаме от Frank ръчен merge без score — той вече обясни, че не може.
- Да не отваряме нов PR в awesome-mcp-servers (има инцидент с #31971, подаден от Cline без команда).
- Да не пипаме `kristo-travel-api` (#1081/#11557) — това е стар, различен проект; repo-то вече е private.
- Да не купуваме „featured" слот при Glama, преди да сме решили базовия запис.

---

## §4 MCP Registry / PulseMCP — най-евтината поправка в целия план

**Проблемът:** `isLatest` = **v6.0.0 (17.09)**, а v1.0.0 (10.10) е по-нова, но „по-ниска" по semver → регистърът я маркира като не-последна.

**Решението:** публикуване на версия **> 6.0.0** (напр. `6.1.0` или `7.0.0`) със същите богати метаданни: 6 платени endpoint-а с цени, 3 инструмента, `remotes` (`/mcp`, `/mcp/sse`), `icons`, `websiteUrl`, `discovery` блок.

**Ефектът:** всички консуматори на регистъра — **PulseMCP**, агрегатори, MCP клиенти — виждат актуалните данни вместо септемврийските.

**Нужно от собственика:** `mcp-publisher` **device flow** — едно оторизиране в браузър (~1 минута).
**Стойност:** нула пари, най-широко покритие на усилие.

---

## §5 Целеви директории — пет семейства

### Семейство 1 — MCP директории

| Канал | Статус | Действие | Цена |
|---|---|---|---|
| **Glama** | Connector ✅ A · Servers ❌ | Маршрут A/B от §3 | $0 |
| **Официален MCP Registry** | ⚠️ стара версия е `isLatest` | §4 — публикувай > 6.0.0 | $0 |
| **PulseMCP** | поема автоматично от регистъра | **оправя се сам** след §4 | $0 |
| **mcp.so** | ✅ запис, коментар #3441 | claim/верификация; актуализирай цените | $0 |
| **Smithery** | ❌ мъртъв (proxy спрян 31.10) | не инвестирай; провери за наследник | — |
| **mcpmarket.com** | не сме | беше отказан заради **$69** | $69 (решение) |
| **mcprush** | бадж в README | — | $0 |
| **Docker MCP Catalog** (`hub.docker.com/mcp`) | **непроверен** | провери изисквания — имаме Dockerfile | $0 |
| **Cline MCP Marketplace / Cursor Directory / OpenTools / mcp.directory** | **непроверени** | проучване + подаване където е свободно | $0 |

### Семейство 2 — x402 и агентни платежни каталози (там е платеният трафик)

| Канал | Статус | Действие |
|---|---|---|
| **x402scan** | ✅ регистриран (issue #1270, коментар #1283) | продължи диалога с Merit; виж дали `/sample` рутовете се виждат |
| **CDP Bazaar** | ✅ **1 индексиран ресурс** | задръж индексирането; активирай платения листинг ($0.25) от опашката |
| **x402-list.com** | ✅ LIVE, 14/14, **валиден до 05.11** | **поднови преди 05.11** |
| **x402-trust.com** | ✅ Grade A 81.2 | не купувай $0.005 доклада; поддържай uptime |
| **PayAPI Market** | ✅ LIVE + verified | каналът с реален човешки контакт (Chet) |
| **nohumans.directory** | ✅ **3 реални плащания на 30.10** | **PATCH-ни листинга** (`sample_query` / `has_sample`) — единственият канал с доказан външен трафик |
| **x402.org екосистемна страница / agentcash** | непроверено | проучване |

### Семейство 3 — интеграции в агентни framework-и ← **най-големият дългосрочен лост**

Тук не става дума за бадж, а за това нашият API да влезе в **кодовия път**, който агентите вече изпълняват. Заслужава отделен документ, но посоките:

- **Coinbase AgentKit** action provider
- **GOAT SDK** tools
- **elizaOS** plugin registry
- **LangChain / CrewAI** tool registries
- **Anthropic Claude connectors** + **ChatGPT apps/connectors** — Glama connector-ът ни показва `ChatGPT: –`, `Claude: –` (празни полета → вероятно се запълват от Admin таба)

Плюс: **Claude/ChatGPT конектор директориите** са мястото, където крайните потребители включват MCP сървъри.

### Семейство 4 — API каталози и обща dev видимост

API-то е и **OpenAPI 3.0** услуга — значи може да влезе в каталози, които не са MCP:
**APIs.guru**, **Postman API Network**, **Public APIs**, **RapidAPI** (провери дали приема x402 модел), **Product Hunt** (липсва изцяло в досегашната стратегия), **Hacker News / dev.to / Reddit**.

### Семейство 5 — Awesome списъци

| Списък | PR | Статус | Действие |
|---|---|---|---|
| `punkpeye/awesome-mcp-servers` | **#13219** | open, 20 коментара | блокиран на §3 |
| `xpaysh/awesome-x402` | **#1308** | **open, clean, mergeable** от 24.08 | учтив nudge (последна активност 28.09) |
| `wong2/awesome-mcp-servers`, `modelcontextprotocol/servers`, `awesome-ai-agents`, `awesome-web3` | — | непроверени | проучване: 1 сървър = 1 PR |

---

## §6 Техническият слой, който прави намирането възможно

Директориите ни виждат; **търсачките — не** (проверено: `site:kristo-intelligence-api.onrender.com` → **1 индексирана страница**). Това е и „най-голямата дупка" по думите на собственика. Накратко (детайли в `VISIBILITY_AND_TRAFFIC_STRATEGY.md` и в Блокове 8–9):

1. **Индексируема повърхност** — сега има 3 HTML страници, от които `/validation` е сираче, а `/dashboard` е `noindex`, но е в sitemap с приоритет 0.9.
2. **`llms.txt` документира само стария `X-Payment-Proof`** — не описва x402 v2 релсата, цените и `/sample` рутовете.
3. **Нула OG/Twitter/canonical/JSON-LD** в 9 темплейта → споделянията изглеждат като гол линк.
4. **Sitemap** съдържа 302 пренасочвания и пропуска `/validation`, `/api/v1/quickstart`, `/.well-known/x402`, `/sample/*`.
5. **Няма GSC/Bing верификация, няма IndexNow, няма аналитика.**
6. **`/sample` рутовете са невидими** — а точно те са „try before you pay" пътят, който nohumans маркира като задължителен (`has_sample`).

---

## §7 Измерване — иначе „трафик" е усещане

**Фунията, която трябва да мерим:**

```
директория/търсене → безплатен discovery (llms.txt, /mcp, /sample)
   → 402 предизвикателство → платено плащане → settled call → индексиране
```

**Минимален набор (седмично):**
- брой **discovery** попадения по канал (User-Agent / referrer)
- брой **402** срещу брой **settled** (конверсия)
- брой външни платци (различни от нашите кравпъри `0xA19F`, `0x54E1`, `0xe3ba`)
- позиция/присъствие в 6-те ключови директории (има `scripts/_listing_stats.py` и `listing_monitor.py`)
- брой индексирани страници в Google/Bing

**Каденс:** седмичен пулс (вече съществува като практика) + месечен преглед срещу този план.

---

## §8 Какво ми трябва от теб

**Репото е документирано изключително добре** (60+ документа в `docs/` + `PROJECT_STATUS.md` 272 KB) — **не ми трябва нищо от кода**, чета си го сам. Липсва ми това, което живее извън репото:

### A. Glama/GitHub артефакти (за да формулирам точния текст към Glama)
1. **Пълният текст на тикетите #135407945 и #130688574** — какво точно е отговорено последно и има ли назначен човек.
2. **Двата имейла за отказ дословно** (01.11 и 03.11) — за да се види кой запис/път отхвърлят (`kristo-intelligence-v3` подсказва име на подаване).
3. **Достъп/screenshot на Admin таба** на connector-а (Documentation, Trust center, ChatGPT/Claude полета).
4. *(по избор)* **Glama API ключ** (`glm_…`) — за авторитетна проверка на присъствието през `/api/mcp/v1/servers` вместо през търсенето.

### B. Състояние на текущата работа
5. **Какво е свършил Mimo по Блокове 2–7** след 03.11 11:20 (работното дърво показва `main.py`, `templates/dashboard.html`, `tests/test_dashboard_v2.py` — Блок 2 изглежда в ход).
6. **Пътят до `TRACKER.md`** (в Cline workspace) — за да не те питам всеки път.

### C. Решения, които само ти можеш да вземеш
7. Разрешаваш ли **Маршрут B** (нов `scripts/mcp_stdio_bridge.py` + `Dockerfile.glama`)? Това е единственото нещо в плана, което пипа репото.
8. Публикуваме ли **нова версия в MCP Registry** (> 6.0.0)? (§4)
9. **npm 1.0.1** — одобрен на 03.11 10:56, но още не е публикуван. Пускаме ли?
10. **Платени канали** — mcpmarket $69, Bazaar $0.25: да или не?
11. **GSC / Bing Webmaster** — имаш ли достъп/верификация, или да подготвя стъпките?

### D. Данни за трафика
12. **Логове с referrer/User-Agent** (Render dashboard или експорт) — без тях „кой ни намира" е догадка.

---

## §9 Ред на изпълнение

**Ден 1 (днес):**
- Тикет #135407945 с пълното доказателство (Маршрут A) — *текстът мога да го подготвя веднага*
- Запълване на Documentation + Trust center в Admin таба
- Публикуване на нова версия в MCP Registry (§4) → PulseMCP се оправя сам

**Ден 2–3:**
- Маршрут B паралелно (`mcp_stdio_bridge.py` + `Dockerfile.glama`) — ако е одобрен
- PATCH на nohumans листинга (`sample_query`)
- Подновяване на x402-list преди **05.11**

**Седмица 1:**
- Блокове 8–9 (README/`agents.json`/`llms.txt` + OG карти) — **задължителни преди следващо Glama подаване**
- Учтив nudge на PR #1308
- Проучване на Docker MCP Catalog, Cline/Cursor, OpenTools

**Седмица 2–3:**
- Семейство 3 (framework интеграции) — избор на първите 2
- Измерване: първи седмичен пулс срещу фунията от §7

---

## §10 Инварианти (не се пипат)

x402 хедъри и структура на 402 плика · цени (`X402_PRICE_MAP`) · `payTo`/RECEIVER · `/.well-known/x402-trust.txt` · commission · `secrets\` и `.env` (не се отварят) · **никакъв push без отделна врата** (push = автоматичен deploy на Render) · едно подаване = една изрична команда.
